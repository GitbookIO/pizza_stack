#!/usr/bin/env python3
"""Parse a Claude Code JSONL session transcript and extract behavioral metrics.

Claude Code JSONL format: each line is an entry with a "type" field.
Tool calls appear in entries with type "assistant", inside message.content,
as blocks with type "tool_use". The tool name is in block["name"] and
the input is in block["input"].

NOTE ON api_call_count: For Claude Code sessions, this will always be 0.
Claude Code executes API calls inside Bash subprocesses (e.g. running a
Python script), not as discrete tool calls visible in the transcript.
The server-side request log (requests.jsonl) is the source of truth for
API call behavior. The transcript is the source of truth for docs reading
behavior. The two complement each other.

NOTE ON TRANSCRIPT FILE LOCATION: Claude Code stores session transcripts at:
  ~/.claude/projects/<encoded-working-dir>/<session-uuid>.jsonl
The working directory path is encoded with hyphens replacing slashes and
other special characters. For example, a session run from:
  /private/var/folders/.../pizza_bench_<uuid>/
would be stored under:
  ~/.claude/projects/-private-var-folders-...-pizza-bench-<uuid>/
Use `ls ~/.claude/projects/` to find the right directory, then find the
.jsonl file whose name matches the Claude Code session UUID (visible in
the Claude Code terminal header).
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from typing import Any


DOCS_URL_PATTERNS = ["tomatopy.pizza/docs", "llms.txt"]
API_URL_PATTERN = "api.tomatopy.pizza"

# Internal Claude Code housekeeping tools — excluded from behavioral analysis
SKIP_TOOLS = {"ToolSearch"}


def _classify_intent(url: str | None) -> str:
    """Classify a URL as docs_fetch, api_call, or other."""
    if url is None:
        return "other"
    url_lower = url.lower()
    for pattern in DOCS_URL_PATTERNS:
        if pattern in url_lower:
            return "docs_fetch"
    if API_URL_PATTERN in url_lower:
        return "api_call"
    return "other"


def _extract_url(tool_name: str, tool_input: dict[str, Any]) -> str | None:
    """Extract a URL from a tool call's input."""
    # WebFetch and most tools: check "url" field directly
    if "url" in tool_input and isinstance(tool_input["url"], str):
        return tool_input["url"]
    # Bash: scan the command string for http URLs
    if tool_name == "Bash":
        command = tool_input.get("command", "")
        for word in command.split():
            if word.startswith("http://") or word.startswith("https://"):
                return word.rstrip("'\",;:)")
    return None


def parse_transcript(transcript_path: str, session_id: str) -> dict[str, Any]:
    """Parse a Claude Code JSONL transcript and return structured behavioral metrics."""
    events: list[dict[str, Any]] = []
    first_timestamp: datetime | None = None
    turn = 0

    with open(transcript_path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue

            # Tool calls only appear in assistant entries
            if entry.get("type") != "assistant":
                continue

            timestamp_str = entry.get("timestamp", "")
            ts = None
            if timestamp_str:
                try:
                    ts = datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
                except (ValueError, TypeError):
                    pass

            content = entry.get("message", {}).get("content", [])
            if not isinstance(content, list):
                continue

            for block in content:
                if block.get("type") != "tool_use":
                    continue

                tool_name = block.get("name", "")

                # Skip internal housekeeping tools
                if tool_name in SKIP_TOOLS:
                    continue

                tool_input = block.get("input", {})
                if not isinstance(tool_input, dict):
                    tool_input = {}

                url = _extract_url(tool_name, tool_input)
                intent = _classify_intent(url)

                if first_timestamp is None and ts:
                    first_timestamp = ts

                elapsed_ms = 0
                if ts and first_timestamp:
                    elapsed_ms = int((ts - first_timestamp).total_seconds() * 1000)

                events.append({
                    "turn": turn,
                    "tool": tool_name,
                    "url": url,
                    "intent": intent,
                    "timestamp": timestamp_str,
                    "elapsed_ms": elapsed_ms,
                })
                turn += 1

    # Summary metrics
    docs_fetch_count = sum(1 for e in events if e["intent"] == "docs_fetch")
    api_call_count = sum(1 for e in events if e["intent"] == "api_call")
    docs_pages_fetched = list(dict.fromkeys(
        e["url"] for e in events if e["intent"] == "docs_fetch" and e["url"]
    ))

    # first_action: intent of the first meaningful tool call (ToolSearch already excluded)
    first_action = events[0]["intent"] if events else ""

    first_api_turn = next((e["turn"] for e in events if e["intent"] == "api_call"), None)
    first_docs_turn = next((e["turn"] for e in events if e["intent"] == "docs_fetch"), None)

    if first_docs_turn is None:
        docs_fetch_timing = "never"
    elif first_api_turn is None or first_docs_turn < first_api_turn:
        docs_fetch_timing = "before_first_api_call"
    else:
        docs_fetch_timing = "after_first_api_call"

    used_mcp_for_docs = any(
        ("gitbook" in e["tool"].lower() or "mcp" in e["tool"].lower())
        and e["intent"] == "docs_fetch"
        for e in events
    )
    used_webfetch_for_docs = any(
        e["tool"] == "WebFetch" and e["intent"] == "docs_fetch"
        for e in events
    )

    return {
        "session_id": session_id,
        "transcript_file": transcript_path,
        "events": events,
        "docs_fetch_count": docs_fetch_count,
        "api_call_count": api_call_count,
        "docs_pages_fetched": docs_pages_fetched,
        "first_action": first_action,
        "docs_fetch_timing": docs_fetch_timing,
        "used_mcp_for_docs": used_mcp_for_docs,
        "used_webfetch_for_docs": used_webfetch_for_docs,
    }


def main():
    parser = argparse.ArgumentParser(
        description="Parse a Claude Code JSONL transcript and extract behavioral metrics"
    )
    parser.add_argument("--transcript", required=True,
                        help="Path to a Claude Code .jsonl session transcript")
    parser.add_argument("--session-id", required=True,
                        help="Benchmark session UUID (used to label output)")
    parser.add_argument("--output", default=None,
                        help="Path to write full JSON output; if omitted, prints summary to stdout")
    args = parser.parse_args()

    result = parse_transcript(args.transcript, args.session_id)

    if args.output:
        with open(args.output, "w") as f:
            json.dump(result, f, indent=2)
            f.write("\n")
        print(f"Full output written to {args.output}")

    # Always print a readable summary to stdout
    summary = {k: v for k, v in result.items() if k != "events"}
    summary["event_count"] = len(result["events"])
    summary["events_sample"] = result["events"][:5]
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
