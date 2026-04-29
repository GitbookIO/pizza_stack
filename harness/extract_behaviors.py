#!/usr/bin/env python3
"""
TomatoPy benchmark — behavioral column extractor.

Reads transcripts for a session and extracts:
  - docs_fetch_count
  - docs_fetch_timing
  - first_action
  - used_mcp_for_docs
  - found_distribution_in_reference

Usage:
  python extract_behaviors.py --session <session_id> --log harness/manual/log.csv --traces harness/manual/traces/
  python extract_behaviors.py --log harness/manual/log.csv --traces harness/manual/traces/

Writes back to the log CSV in-place (or to --out if specified).

JUDGMENT CALLS ENCODED HERE (document any change):
  - docs_fetch_timing: categorized as one of:
      "first_action"        — the very first tool call in the session was a docs fetch
      "before_first_exec"   — fetched before any Bash/Shell/exec_command that runs a .py file
      "after_first_exec"    — first docs fetch happened after first execution
      "none"                — no docs fetches found
  - found_distribution_in_reference: True iff:
      (a) /developer-documentation/pizzastack-api was fetched (any path form)
      (b) that fetch occurred before the first /pizza/assemble call in execution output
      (c) no 422 on /pizza/assemble appears before any successful 200 on /pizza/assemble
  - Cursor JSONL is not parsed (tool outputs are not recorded in Cursor JSONLs).
    Cursor sessions use the .md export. The .md extractor is regex-based over the
    formatted markdown — it is more brittle than the JSONL parsers and should be
    audited manually if the export format changes.
  - Codex reasoning blocks are encrypted and not inspected; only observable tool
    calls and outputs are used.
  - Subagent fetches: for Claude Code sessions that spawn an Agent tool call,
    the subagent JSONL (agent-*.jsonl in the same directory) is located by
    matching the session directory and included in docs_fetch_count.
"""

import csv
import json
import os
import re
import sys
from pathlib import Path
from typing import Optional

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DOCS_ROOT = "tomatopy.pizza"
API_REFERENCE_PATH_FRAGMENT = "developer-documentation/pizzastack-api"
ASSEMBLE_ENDPOINT = "/pizza/assemble"
ASSEMBLE_ENDPOINT_ALT = "pizza/assemble"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def is_docs_url(url: str) -> bool:
    return DOCS_ROOT in url


def is_api_reference_url(url: str) -> bool:
    return API_REFERENCE_PATH_FRAGMENT in url


def is_execution_command(cmd: str) -> bool:
    """
    True if the command actually runs a Python script file (not a one-liner check,
    not curl, not ls/pwd/rg).
    Covers:
      python3 make_pizza.py
      .venv/bin/python make_pizza.py
      pyenv exec python make_pizza.py
    Does NOT match:
      python3 -c "import requests; print(...)"  (version/dependency checks)
      curl ...                                  (docs fetches)
      pwd / ls / rg / cat                       (workspace inspection)
    """
    cmd = cmd.strip()
    if not re.search(r'python[23]?', cmd):
        return False
    # Exclude one-liner -c invocations used only for version/dep checks
    if re.search(r'python[23]?\s+-c\s+["\']', cmd):
        return False
    # Must reference a .py file
    return bool(re.search(r'\.py\b', cmd))


def text_contains_422_on_assemble(text: str) -> bool:
    return ("422" in text and ASSEMBLE_ENDPOINT_ALT in text) or \
           ("422" in text and "assemble" in text.lower())


def text_contains_assemble_success(text: str) -> bool:
    return ("200" in text and "assemble" in text.lower()) or \
           ("pza_" in text and "assembled" in text.lower())


# ---------------------------------------------------------------------------
# Claude Code JSONL parser
# ---------------------------------------------------------------------------

def parse_claude_code(jsonl_path: Path, subagent_path: Optional[Path] = None) -> dict:
    """
    Parse a Claude Code JSONL transcript.
    Tool calls are in assistant events: message.content[].type == "tool_use"
    Tool results are in user events: message.content[].type == "tool_result"
    """
    events = []

    def _parse_file(path):
        with open(path) as f:
            for i, raw in enumerate(f):
                raw = raw.strip()
                if not raw:
                    continue
                try:
                    obj = json.loads(raw)
                except json.JSONDecodeError:
                    continue

                otype = obj.get("type", "")

                if otype == "assistant":
                    content = obj.get("message", {}).get("content", [])
                    if not isinstance(content, list):
                        continue
                    for block in content:
                        if not isinstance(block, dict):
                            continue
                        if block.get("type") == "tool_use":
                            name = block.get("name", "")
                            inp = block.get("input", {})
                            events.append((i, "tool_call", {"name": name, "input": inp}))

                elif otype == "user":
                    content = obj.get("message", {}).get("content", [])
                    if not isinstance(content, list):
                        continue
                    for block in content:
                        if not isinstance(block, dict):
                            continue
                        if block.get("type") == "tool_result":
                            text = block.get("content", "")
                            if isinstance(text, list):
                                text = " ".join(str(x) for x in text)
                            events.append((i, "tool_result", {"text": str(text)}))

    _parse_file(jsonl_path)
    if subagent_path and subagent_path.exists():
        _parse_file(subagent_path)

    return _analyze_events(events, source_format="claude_code")


# ---------------------------------------------------------------------------
# Cursor .md parser
# NOTE: This is the least reliable parser. Cursor .md exports are human-readable
# summaries, not structured data. The regex patterns below are tied to the
# observed export format. If the format changes, this parser needs updating.
# ---------------------------------------------------------------------------

def parse_cursor_md(md_path: Path) -> dict:
    text = md_path.read_text()

    # Extract WebFetch tool calls
    webfetch_urls = re.findall(
        r'Tool Call[^`\n]*[`"]?WebFetch[`"]?.*?\n.*?[`"]?(https?://[^\s`"]+)',
        text,
        re.DOTALL | re.IGNORECASE
    )
    if not webfetch_urls:
        webfetch_urls = re.findall(
            r'WebFetch.*?\n(?:.*?\n){0,4}.*?(https://[^\s`"]+)',
            text,
            re.DOTALL | re.IGNORECASE
        )

    has_422_assemble = bool(re.search(
        r'422.*assemble|assemble.*422|"422".*pizza|pizza.*assemble.*422',
        text,
        re.IGNORECASE | re.DOTALL
    ))

    has_200_assemble = bool(re.search(
        r'(?:Status: 200|"status":\s*"assembled")',
        text,
        re.IGNORECASE
    ))

    fetched_api_reference = any(
        API_REFERENCE_PATH_FRAGMENT in url for url in webfetch_urls
    )

    first_action = "WebFetch" if webfetch_urls else "unknown"

    webfetch_pos = text.find("WebFetch")
    shell_pos = min(
        (text.find(kw) for kw in ["### 🔧 Tool Call: `Shell`", "Tool Call: Shell", "Tool Call: `Shell`"]
         if text.find(kw) != -1),
        default=-1
    )
    if webfetch_pos != -1 and (shell_pos == -1 or webfetch_pos < shell_pos):
        docs_fetch_timing = "first_action"
    elif webfetch_pos != -1:
        docs_fetch_timing = "after_first_exec"
    else:
        docs_fetch_timing = "none"

    if fetched_api_reference and not has_422_assemble and has_200_assemble:
        found_dist_in_ref = "NEEDS_REVIEW"
    else:
        found_dist_in_ref = False

    fetch_count = len(webfetch_urls)

    return {
        "docs_fetch_count": fetch_count,
        "docs_fetch_timing": docs_fetch_timing,
        "first_action": first_action,
        "used_mcp_for_docs": False,
        "found_distribution_in_reference": found_dist_in_ref,
        "_hit_422_assemble": has_422_assemble,
        "_fetched_api_reference": fetched_api_reference,
        "_format": "cursor_md",
        "_needs_review": found_dist_in_ref == "NEEDS_REVIEW",
    }


# ---------------------------------------------------------------------------
# Codex JSONL parser
# ---------------------------------------------------------------------------

def parse_codex(jsonl_path: Path) -> dict:
    """
    Parse a Codex rollout JSONL.
    Tool calls: response_item events with payload.type == "function_call"
    Tool outputs: response_item events with payload.type == "function_call_output"
    Reasoning blocks: payload.type == "reasoning" (content encrypted, not inspected)
    """
    events = []

    with open(jsonl_path) as f:
        for i, raw in enumerate(f):
            raw = raw.strip()
            if not raw:
                continue
            try:
                obj = json.loads(raw)
            except json.JSONDecodeError:
                continue

            otype = obj.get("type", "")
            payload = obj.get("payload", {})

            if otype == "response_item":
                ptype = payload.get("type", "")

                if ptype == "function_call":
                    name = payload.get("name", "")
                    args_raw = payload.get("arguments", "")
                    try:
                        args = json.loads(args_raw) if isinstance(args_raw, str) else args_raw
                    except json.JSONDecodeError:
                        args = {}
                    # Codex uses "cmd" key; some other formats use "command"
                    cmd = args.get("cmd", "") or args.get("command", "") or ""
                    events.append((i, "tool_call", {"name": name, "cmd": cmd, "input": args}))

                elif ptype == "function_call_output":
                    output = str(payload.get("output", ""))
                    events.append((i, "tool_result", {"text": output}))

    return _analyze_events(events, source_format="codex")


# ---------------------------------------------------------------------------
# Shared event analyzer
# ---------------------------------------------------------------------------

def _analyze_events(events: list, source_format: str) -> dict:
    """
    Given a normalized event stream, compute all behavioral columns.

    events: list of (line_index, event_type, data)
      event_type: "tool_call" | "tool_result"
      data for tool_call: {"name": str, "input": dict, "cmd": str (Codex only)}
      data for tool_result: {"text": str}
    """
    docs_fetch_indices = []
    api_ref_fetch_indices = []
    first_exec_index = None
    first_action = None
    used_mcp = False

    assemble_422_indices = []
    assemble_200_indices = []

    for (idx, etype, data) in events:
        if etype == "tool_call":
            name = data.get("name", "")
            inp = data.get("input", {})
            cmd = data.get("cmd", "") or inp.get("command", "") or inp.get("cmd", "")

            if first_action is None:
                first_action = name

            url = inp.get("url", "")

            if name == "WebFetch" and url and is_docs_url(url):
                docs_fetch_indices.append(idx)
                if is_api_reference_url(url):
                    api_ref_fetch_indices.append(idx)

            # Codex curl-based docs fetch
            if name == "exec_command" and "curl" in cmd and is_docs_url(cmd):
                url_match = re.search(r'https?://\S+', cmd)
                fetched_url = url_match.group(0).rstrip('"\'') if url_match else ""
                docs_fetch_indices.append(idx)
                if is_api_reference_url(fetched_url) or is_api_reference_url(cmd):
                    api_ref_fetch_indices.append(idx)

            # Detect first script execution
            if name in ("Bash", "Shell") and first_exec_index is None:
                bash_cmd = inp.get("command", "") or inp.get("cmd", "") or cmd
                if is_execution_command(bash_cmd):
                    first_exec_index = idx

            if name == "exec_command" and first_exec_index is None:
                if is_execution_command(cmd):
                    first_exec_index = idx

            # MCP detection
            if "mcp" in name.lower() and is_docs_url(url):
                used_mcp = True

        elif etype == "tool_result":
            text = data.get("text", "")
            if text_contains_422_on_assemble(text):
                assemble_422_indices.append(idx)
            if text_contains_assemble_success(text):
                assemble_200_indices.append(idx)

    # --- docs_fetch_count ---
    fetch_count = len(docs_fetch_indices)

    # --- docs_fetch_timing ---
    # Vocabulary:
    #   "first_action"      — docs fetch was the first (or first non-ToolSearch) tool call
    #   "before_first_exec" — docs fetched before first script execution
    #   "after_first_exec"  — first docs fetch came after a script was already run
    #   "none"              — no docs fetches
    if not docs_fetch_indices:
        timing = "none"
    elif first_exec_index is None:
        timing = "before_first_exec"
    elif docs_fetch_indices[0] < first_exec_index:
        timing = "before_first_exec"
    else:
        timing = "after_first_exec"

    # Upgrade to "first_action" if the docs fetch was the first meaningful call.
    # For Claude Code: ToolSearch precedes everything; treat first non-ToolSearch as effective first.
    # Also handle the Agent-delegation pattern where docs are fetched via subagent on first call.
    if timing == "before_first_exec" and docs_fetch_indices:
        non_ts_calls = [
            (idx, d) for (idx, et, d) in events
            if et == "tool_call" and d.get("name") not in ("ToolSearch",)
        ]
        # Agent-delegation: first non-TS call was Agent, and docs fetches exist
        if non_ts_calls and non_ts_calls[0][1].get("name") == "Agent":
            timing = "first_action"
        # Direct: first non-TS call was itself a docs fetch
        elif non_ts_calls and docs_fetch_indices and non_ts_calls[0][0] == docs_fetch_indices[0]:
            timing = "first_action"

    # --- first_action ---
    if first_action is None:
        first_action = "unknown"

    # --- found_distribution_in_reference ---
    # Strict: API ref page fetched BEFORE first /pizza/assemble attempt,
    # AND no 422 on assemble before first 200 on assemble.
    if not api_ref_fetch_indices:
        found_dist = False
    elif not assemble_200_indices:
        found_dist = False
    else:
        first_api_ref = min(api_ref_fetch_indices)
        first_assemble_200 = min(assemble_200_indices)
        first_assemble_422 = min(assemble_422_indices) if assemble_422_indices else float("inf")

        first_assemble_attempt = min(first_assemble_200, first_assemble_422)
        fetched_before_assemble = first_api_ref < first_assemble_attempt
        no_prior_422 = (not assemble_422_indices) or (first_assemble_422 > first_assemble_200)

        found_dist = fetched_before_assemble and no_prior_422

    return {
        "docs_fetch_count": fetch_count,
        "docs_fetch_timing": timing,
        "first_action": first_action,
        "used_mcp_for_docs": used_mcp,
        "found_distribution_in_reference": found_dist,
        "_api_ref_fetches": len(api_ref_fetch_indices),
        "_422_on_assemble": len(assemble_422_indices),
        "_200_on_assemble": len(assemble_200_indices),
        "_format": source_format,
        "_needs_review": False,
    }


# ---------------------------------------------------------------------------
# Session dispatcher
# ---------------------------------------------------------------------------

def _session_has_agent_call(jsonl_path: Path) -> bool:
    """Returns True if this Claude Code JSONL contains an Agent tool_use call."""
    with open(jsonl_path) as f:
        for raw in f:
            raw = raw.strip()
            if not raw:
                continue
            try:
                obj = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if obj.get("type") == "assistant":
                for block in obj.get("message", {}).get("content", []):
                    if isinstance(block, dict) and block.get("type") == "tool_use":
                        if block.get("name") == "Agent":
                            return True
    return False


def extract_for_session(row: dict, traces_dir: Path) -> dict:
    agent = row["agent_system"]
    transcript = row["transcript_file"]

    if agent == "claude-code":
        main_path = traces_dir / "claude_code" / transcript
        subagent_path = None
        if _session_has_agent_call(main_path):
            cc_dir = traces_dir / "claude_code"
            if cc_dir.exists():
                for f in cc_dir.iterdir():
                    if f.name.startswith("agent-") and f.suffix == ".jsonl":
                        subagent_path = f
                        break
        return parse_claude_code(main_path, subagent_path)

    elif agent == "cursor":
        md_path = traces_dir / "cursor" / (transcript + ".md")
        if md_path.exists():
            return parse_cursor_md(md_path)
        print(
            f"WARNING: No .md for {transcript}. Cursor JSONL lacks tool outputs. "
            f"Results will be incomplete.",
            file=sys.stderr
        )
        return parse_cursor_md(traces_dir / "cursor" / transcript)

    elif agent == "codex":
        return parse_codex(traces_dir / "codex" / transcript)

    else:
        raise ValueError(f"Unknown agent_system: {agent}")


# ---------------------------------------------------------------------------
# CSV updater
# ---------------------------------------------------------------------------

BEHAVIORAL_COLUMNS = [
    "docs_fetch_count",
    "docs_fetch_timing",
    "first_action",
    "used_mcp_for_docs",
    "found_distribution_in_reference",
]


def update_log(log_path: Path, traces_dir: Path, out_path: Optional[Path] = None):
    with open(log_path, newline="") as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames
        rows = list(reader)

    updated = []
    review_needed = []

    for row in rows:
        session_id = row["session_id"]
        print(f"Processing: {session_id} ({row['agent_system']})")
        try:
            result = extract_for_session(row, traces_dir)
        except Exception as e:
            print(f"  ERROR: {e}", file=sys.stderr)
            updated.append(row)
            continue

        for col in BEHAVIORAL_COLUMNS:
            val = result.get(col, "")
            row[col] = str(val).lower() if isinstance(val, bool) else str(val)

        if result.get("_needs_review"):
            review_needed.append(session_id)

        print(f"  fetch_count={result['docs_fetch_count']} "
              f"timing={result['docs_fetch_timing']} "
              f"first_action={result['first_action']} "
              f"found_dist={result['found_distribution_in_reference']} "
              f"[{result.get('_format','?')}]")

        updated.append(row)

    out = out_path or log_path
    with open(out, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(updated)

    print(f"\nWrote {len(updated)} rows to {out}")
    if review_needed:
        print(f"\nSessions flagged for manual review: {review_needed}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Extract behavioral columns from TomatoPy transcripts.")
    parser.add_argument("--log", required=True, help="Path to log.csv")
    parser.add_argument("--traces", required=True, help="Path to traces/ directory")
    parser.add_argument("--out", help="Output CSV path (defaults to in-place)")
    parser.add_argument("--session", help="Process only this session_id")
    args = parser.parse_args()

    log_path = Path(args.log)
    traces_dir = Path(args.traces)
    out_path = Path(args.out) if args.out else None

    if args.session:
        with open(log_path, newline="") as f:
            rows = list(csv.DictReader(f))
        matching = [r for r in rows if r["session_id"] == args.session]
        if not matching:
            print(f"Session {args.session} not found in log.")
            sys.exit(1)
        result = extract_for_session(matching[0], traces_dir)
        print(json.dumps({k: v for k, v in result.items() if not k.startswith("_")}, indent=2))
    else:
        update_log(log_path, traces_dir, out_path)
