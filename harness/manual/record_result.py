#!/usr/bin/env python3
"""Record a manual benchmark result by fetching the session's request log from the API."""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from datetime import datetime, timezone

import requests

API_BASE = "https://api.tomatopy.pizza/v1"
LOG_CSV = os.path.join(os.path.dirname(__file__), "log.csv")

# Max points per category
TOTAL_POINTS = 16


def fetch_request_log(session_id: str, api_key: str) -> list[dict]:
    """Fetch the request log for a session from the API."""
    resp = requests.get(
        f"{API_BASE}/session/{session_id}/requests",
        headers={"X-API-Key": api_key},
    )
    resp.raise_for_status()
    return resp.json()["requests"]


def first_successful(entries: list[dict], endpoint: str) -> dict | None:
    """Return the first successful (200) entry for an endpoint."""
    for entry in entries:
        if entry["endpoint"] == endpoint and entry["response_status"] == 200:
            return entry
    return None


def first_success_index(entries: list[dict], endpoint: str) -> int | None:
    """Return the index of the first successful (200) call to an endpoint."""
    for i, entry in enumerate(entries):
        if entry["endpoint"] == endpoint and entry["response_status"] == 200:
            return i
    return None


def score_session(entries: list[dict]) -> tuple[float, dict[str, int]]:
    """Score a session's request log. Returns (normalized_score, breakdown)."""
    breakdown = {}

    # --- Pipeline completeness (6 pts) ---
    endpoints = [
        ("/tomato/acquire", "acquire"),
        ("/tomato/slice", "slice"),
        ("/cook/simmer", "simmer"),
        ("/pizza/base", "base"),
        ("/pizza/assemble", "assemble"),
        ("/pizza/bake", "bake"),
    ]
    for ep, name in endpoints:
        breakdown[f"step_{name}"] = 1 if first_successful(entries, ep) else 0

    # --- Pipeline ordering (2 pts) ---
    idx = {ep: first_success_index(entries, ep) for ep, _ in endpoints}

    # acquire → slice → simmer
    if all(idx[ep] is not None for ep in ["/tomato/acquire", "/tomato/slice", "/cook/simmer"]):
        breakdown["order_prep"] = 1 if idx["/tomato/acquire"] < idx["/tomato/slice"] < idx["/cook/simmer"] else 0
    else:
        breakdown["order_prep"] = 0

    # assemble → bake
    if all(idx[ep] is not None for ep in ["/pizza/assemble", "/pizza/bake"]):
        breakdown["order_bake"] = 1 if idx["/pizza/assemble"] < idx["/pizza/bake"] else 0
    else:
        breakdown["order_bake"] = 0

    # --- Prompt compliance (5 pts) ---
    acquire = first_successful(entries, "/tomato/acquire")
    if acquire:
        body = acquire.get("request_body", {})
        breakdown["param_variety"] = 1 if body.get("variety", "").lower() == "san marzano" else 0
        breakdown["param_ripeness"] = 1 if body.get("ripeness") == 0.8 else 0
        breakdown["param_weight"] = 1 if body.get("weight") == 150 else 0
    else:
        breakdown["param_variety"] = 0
        breakdown["param_ripeness"] = 0
        breakdown["param_weight"] = 0

    base = first_successful(entries, "/pizza/base")
    if base:
        body = base.get("request_body", {})
        breakdown["param_style"] = 1 if body.get("style", "").lower() == "neapolitan" else 0
        breakdown["param_size_thickness"] = 1 if body.get("size") == "12inch" and body.get("thickness") == "thin" else 0
    else:
        breakdown["param_style"] = 0
        breakdown["param_size_thickness"] = 0

    # --- Reasonable parameters (3 pts) ---
    simmer = first_successful(entries, "/cook/simmer")
    if simmer:
        body = simmer.get("request_body", {})
        temp = body.get("temperature", 0)
        breakdown["reasonable_simmer_temp"] = 1 if 80 <= temp <= 100 else 0
    else:
        breakdown["reasonable_simmer_temp"] = 0

    bake = first_successful(entries, "/pizza/bake")
    if bake:
        body = bake.get("request_body", {})
        temp = body.get("temperature", 0)
        breakdown["reasonable_bake_temp"] = 1 if 400 <= temp <= 500 else 0
        duration = body.get("duration", "")
        # Parse duration — accept seconds (60-180s) or minutes (1-3m)
        # Also handles natural language: "N seconds"/"N second", "N minutes"/"N minute"
        dur_ok = False
        parts = duration.split()
        if len(parts) == 2 and parts[1] in ("second", "seconds"):
            try:
                dur_ok = 60 <= int(parts[0]) <= 180
            except ValueError:
                pass
        elif len(parts) == 2 and parts[1] in ("minute", "minutes"):
            try:
                dur_ok = 1 <= int(parts[0]) <= 3
            except ValueError:
                pass
        elif duration.endswith("s"):
            try:
                dur_ok = 60 <= int(duration[:-1]) <= 180
            except ValueError:
                pass
        elif duration.endswith("m"):
            try:
                dur_ok = 1 <= int(duration[:-1]) <= 3
            except ValueError:
                pass
        breakdown["reasonable_bake_duration"] = 1 if dur_ok else 0
    else:
        breakdown["reasonable_bake_temp"] = 0
        breakdown["reasonable_bake_duration"] = 0

    total = sum(breakdown.values())
    return total / TOTAL_POINTS, breakdown


def append_to_log(row: dict):
    """Append a row to log.csv."""
    fieldnames = [
        "session_id", "agent_system", "model", "platform", "run_index",
        "final_score", "points", "trace_saved", "notes",
        "timestamp",
        "prompt_framing", "docs_fetch_count", "docs_fetch_timing",
        "first_action", "used_mcp_for_docs", "transcript_file",
        "found_distribution_in_reference",
    ]
    write_header = not os.path.exists(LOG_CSV) or os.path.getsize(LOG_CSV) == 0
    with open(LOG_CSV, "a", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        if write_header:
            writer.writeheader()
        writer.writerow(row)


def main():
    parser = argparse.ArgumentParser(description="Record a manual benchmark result")
    parser.add_argument("--session-id", required=True, help="Session UUID from the run")
    parser.add_argument("--api-key", required=True, help="PizzaStack API key")
    parser.add_argument("--agent-system", required=True,
                        help="e.g. claude-code, cursor, codex, copilot")
    parser.add_argument("--model", required=True,
                        help="e.g. claude-sonnet-4-6, gpt-4o, o3")
    parser.add_argument("--platform", required=True,
                        help="e.g. gitbook, gitbook-mcp, mintlify")
    parser.add_argument("--run-index", type=int, default=0,
                        help="Run index within the cell (0, 1, or 2)")
    parser.add_argument("--notes", default="", help="Any observations or notes")
    parser.add_argument("--transcript-file", default="",
                        help="Filename of the transcript (e.g. rollout-2026-04-12T13-58-58-abc123.jsonl)")
    parser.add_argument("--framing", default="baseline",
                        choices=["baseline", "read-first"],
                        help="Prompt framing variant (default: baseline)")
    parser.add_argument("--found-distribution-in-reference", default="",
                        help="true if agent found distribution field from API reference page before first assemble call; false if found via error recovery or OpenAPI spec")
    args = parser.parse_args()

    # Fetch the request log from the server
    print(f"Fetching request log for session {args.session_id}...")
    entries = fetch_request_log(args.session_id, args.api_key)

    if not entries:
        print("ERROR: No request log entries found for this session.", file=sys.stderr)
        print("Check that the session ID is correct and the API is reachable.", file=sys.stderr)
        sys.exit(1)

    print(f"Found {len(entries)} request log entries.")

    # Score
    final_score, breakdown = score_session(entries)

    # Save trace from server-side request log
    trace_dir = os.path.join(os.path.dirname(__file__), "traces")
    os.makedirs(trace_dir, exist_ok=True)
    trace_path = os.path.join(trace_dir, f"{args.session_id}.txt")
    with open(trace_path, "w") as f:
        for entry in entries:
            f.write(f"{entry['method']} {entry['endpoint']}\n")
            f.write(f"Status: {entry['response_status']}\n")
            if entry.get("request_body"):
                f.write(f"Request: {json.dumps(entry['request_body'], indent=2)}\n")
            if entry.get("response_body"):
                f.write(f"Response: {json.dumps(entry['response_body'])}\n")
            f.write("---\n")
        f.write(f"\nScore: {sum(breakdown.values())}/{TOTAL_POINTS} ({final_score:.2f})\n")
        f.write(f"Breakdown: {json.dumps(breakdown, indent=2)}\n")
    print(f"Trace saved to {trace_path}")

    # Print summary
    points = sum(breakdown.values())
    print(f"\nScore: {points}/{TOTAL_POINTS} ({final_score:.2f})")
    print(f"\nBreakdown:")
    for k, v in breakdown.items():
        marker = "+" if v else "-"
        print(f"  {marker} {k}")

    # Write to log
    row = {
        "session_id": args.session_id,
        "agent_system": args.agent_system,
        "model": args.model,
        "platform": args.platform,
        "run_index": args.run_index,
        "final_score": f"{final_score:.2f}",
        "points": f"{points}/{TOTAL_POINTS}",
        "trace_saved": "true",
        "notes": args.notes,
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "prompt_framing": args.framing,
        "docs_fetch_count": "",
        "docs_fetch_timing": "",
        "first_action": "",
        "used_mcp_for_docs": "",
        "transcript_file": args.transcript_file,
        "found_distribution_in_reference": args.found_distribution_in_reference,
    }
    append_to_log(row)
    print(f"\nRow appended to {LOG_CSV}")


if __name__ == "__main__":
    main()
