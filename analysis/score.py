#!/usr/bin/env python3
"""Score aggregation for TomatoPy benchmark results.

Reads JSON result files from harness/results/ and prints summary tables.
"""

from __future__ import annotations

import csv
import json
from collections import defaultdict
from pathlib import Path
from typing import Any


def load_results(results_dir: Path) -> list[dict[str, Any]]:
    """Load all JSON result files from the results directory."""
    results: list[dict[str, Any]] = []
    if not results_dir.exists():
        print(f"Results directory not found: {results_dir}")
        return results
    for path in sorted(results_dir.glob("*.json")):
        with open(path) as f:
            data = json.load(f)
            data["source"] = "automated"
            results.append(data)
    return results


def load_manual_results(log_path: Path) -> list[dict[str, Any]]:
    """Load manual run results from log.csv."""
    results: list[dict[str, Any]] = []
    if not log_path.exists():
        return results
    with open(log_path) as f:
        reader = csv.DictReader(f)
        for row in reader:
            if not row.get("session_id"):
                continue
            score = None
            try:
                score = float(row.get("final_score", ""))
            except (ValueError, TypeError):
                pass
            # Parse behavioral fields
            docs_fetch_count = 0
            try:
                docs_fetch_count = int(row.get("docs_fetch_count", "") or 0)
            except (ValueError, TypeError):
                pass

            results.append({
                "model": row.get("model", ""),
                "platform": row.get("platform", ""),
                "run_index": int(row.get("run_index", 0)),
                "session_id": row.get("session_id", ""),
                "passed": row.get("passed", "").lower() == "true",
                "final_score": score,
                "correct_pipeline": row.get("correct_pipeline", "").lower() == "true",
                "agent_system": row.get("agent_system", ""),
                "source": "manual",
                "tool_calls": [],
                "docs_pages_fetched": [],
                "api_calls_made": [],
                "timestamp": row.get("timestamp", ""),
                "prompt_framing": row.get("prompt_framing", ""),
                "docs_fetch_count": docs_fetch_count,
                "docs_fetch_timing": row.get("docs_fetch_timing", ""),
                "first_action": row.get("first_action", ""),
                "used_mcp_for_docs": row.get("used_mcp_for_docs", "").lower() == "true",
            })
    return results


def _rate(hits: int, total: int) -> str:
    """Format a rate as 'hits/total (pct%)'."""
    if total == 0:
        return "0/0 (--)"
    pct = hits / total * 100
    return f"{hits}/{total} ({pct:.0f}%)"


def _avg(values: list[float | int]) -> str:
    if not values:
        return "--"
    return f"{sum(values) / len(values):.1f}"


def _check_llms_txt_discovery(result: dict[str, Any]) -> bool:
    """Check whether the model fetched an llms.txt file."""
    for url in result.get("docs_pages_fetched", []):
        if "llms.txt" in url.lower():
            return True
    return False


def _check_markdown_variant(result: dict[str, Any]) -> bool:
    """Check whether the model fetched a .md variant of documentation."""
    for url in result.get("docs_pages_fetched", []):
        if url.lower().endswith(".md") or ".md?" in url.lower():
            return True
    return False


def score_results(results: list[dict[str, Any]]) -> None:
    """Compute and print all scoring tables."""
    if not results:
        print("No results to score.")
        return

    # Collect unique models and platforms
    models = sorted({r["model"] for r in results})
    platforms = sorted({r["platform"] for r in results})

    # --- Pass rate per model ---
    print("\n=== Pass Rate per Model ===")
    print(f"{'Model':<30} {'Pass Rate':<20}")
    print("-" * 50)
    for model in models:
        runs = [r for r in results if r["model"] == model]
        passes = sum(1 for r in runs if r["passed"])
        print(f"{model:<30} {_rate(passes, len(runs)):<20}")

    # --- Pass rate per platform ---
    print("\n=== Pass Rate per Platform ===")
    print(f"{'Platform':<20} {'Pass Rate':<20}")
    print("-" * 40)
    for platform in platforms:
        runs = [r for r in results if r["platform"] == platform]
        passes = sum(1 for r in runs if r["passed"])
        print(f"{platform:<20} {_rate(passes, len(runs)):<20}")

    # --- Pass rate per model x platform ---
    print("\n=== Pass Rate per Model x Platform ===")
    header = f"{'Model':<30}" + "".join(f"{p:<18}" for p in platforms)
    print(header)
    print("-" * len(header))
    for model in models:
        row = f"{model:<30}"
        for platform in platforms:
            runs = [r for r in results if r["model"] == model and r["platform"] == platform]
            passes = sum(1 for r in runs if r["passed"])
            row += f"{_rate(passes, len(runs)):<18}"
        print(row)

    # --- Averages ---
    print("\n=== Average Metrics per Model ===")
    print(f"{'Model':<30} {'Avg API Calls':<16} {'Avg Docs Pages':<16} {'Pipeline OK':<16} {'llms.txt':<14} {'MD Variant':<14}")
    print("-" * 106)
    for model in models:
        runs = [r for r in results if r["model"] == model]
        api_counts = [len(r.get("api_calls_made", [])) for r in runs]
        doc_counts = [len(r.get("docs_pages_fetched", [])) for r in runs]
        pipeline_ok = sum(1 for r in runs if r.get("correct_pipeline"))
        llms_txt = sum(1 for r in runs if _check_llms_txt_discovery(r))
        md_variant = sum(1 for r in runs if _check_markdown_variant(r))
        print(
            f"{model:<30} "
            f"{_avg(api_counts):<16} "
            f"{_avg(doc_counts):<16} "
            f"{_rate(pipeline_ok, len(runs)):<16} "
            f"{_rate(llms_txt, len(runs)):<14} "
            f"{_rate(md_variant, len(runs)):<14}"
        )

    # --- Averages per platform ---
    print("\n=== Average Metrics per Platform ===")
    print(f"{'Platform':<20} {'Avg API Calls':<16} {'Avg Docs Pages':<16} {'Pipeline OK':<16} {'llms.txt':<14} {'MD Variant':<14}")
    print("-" * 96)
    for platform in platforms:
        runs = [r for r in results if r["platform"] == platform]
        api_counts = [len(r.get("api_calls_made", [])) for r in runs]
        doc_counts = [len(r.get("docs_pages_fetched", [])) for r in runs]
        pipeline_ok = sum(1 for r in runs if r.get("correct_pipeline"))
        llms_txt = sum(1 for r in runs if _check_llms_txt_discovery(r))
        md_variant = sum(1 for r in runs if _check_markdown_variant(r))
        print(
            f"{platform:<20} "
            f"{_avg(api_counts):<16} "
            f"{_avg(doc_counts):<16} "
            f"{_rate(pipeline_ok, len(runs)):<16} "
            f"{_rate(llms_txt, len(runs)):<14} "
            f"{_rate(md_variant, len(runs)):<14}"
        )

    # --- Behavioral Metrics per Agent System (manual runs only) ---
    manual_runs = [r for r in results if r.get("source") == "manual"]
    if manual_runs:
        agent_systems = sorted({r.get("agent_system", "") for r in manual_runs})
        print("\n=== Behavioral Metrics per Agent System ===")
        print(f"{'Agent System':<20} {'Avg Docs Fetches':<20} {'First Action: Docs%':<22} {'Fetch Timing: Before%':<24} {'MCP Used%':<14}")
        print("-" * 100)
        for agent in agent_systems:
            runs = [r for r in manual_runs if r.get("agent_system") == agent]
            avg_docs = _avg([r.get("docs_fetch_count", 0) for r in runs])
            first_docs = sum(1 for r in runs if r.get("first_action") == "docs_fetch")
            before = sum(1 for r in runs if r.get("docs_fetch_timing") == "before_first_api_call")
            mcp = sum(1 for r in runs if r.get("used_mcp_for_docs"))
            print(
                f"{agent:<20} "
                f"{avg_docs:<20} "
                f"{_rate(first_docs, len(runs)):<22} "
                f"{_rate(before, len(runs)):<24} "
                f"{_rate(mcp, len(runs)):<14}"
            )


def main() -> None:
    base = Path(__file__).resolve().parent.parent
    results_dir = base / "harness" / "results"
    manual_log = base / "harness" / "manual" / "log.csv"

    automated = load_results(results_dir)
    manual = load_manual_results(manual_log)
    results = automated + manual

    print(f"Loaded {len(automated)} automated + {len(manual)} manual = {len(results)} total result(s)")
    score_results(results)


if __name__ == "__main__":
    main()
