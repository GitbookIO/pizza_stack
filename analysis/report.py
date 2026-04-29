#!/usr/bin/env python3
"""Generate a Markdown summary report from TomatoPy benchmark results.

Reads result JSON files, computes the full scoring matrix, and writes
analysis/report.md.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from analysis.score import load_results, load_manual_results


def _pct(hits: int, total: int) -> str:
    if total == 0:
        return "--"
    return f"{hits / total * 100:.0f}%"


def _avg(values: list[float | int]) -> float:
    if not values:
        return 0.0
    return sum(values) / len(values)


def _check_llms_txt(result: dict[str, Any]) -> bool:
    return any("llms.txt" in url.lower() for url in result.get("docs_pages_fetched", []))


def _check_md_variant(result: dict[str, Any]) -> bool:
    return any(url.lower().endswith(".md") or ".md?" in url.lower() for url in result.get("docs_pages_fetched", []))


def generate_report(results: list[dict[str, Any]], output_path: Path) -> None:
    """Generate a Markdown report and write it to output_path."""
    if not results:
        output_path.write_text("# TomatoPy Benchmark Report\n\nNo results found.\n")
        return

    models = sorted({r["model"] for r in results})
    platforms = sorted({r["platform"] for r in results})

    lines: list[str] = []
    lines.append("# TomatoPy Benchmark Report")
    lines.append("")
    lines.append(f"Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
    lines.append(f"Total runs: {len(results)}")
    lines.append("")

    # --- Pass Rate Matrix ---
    lines.append("## Pass Rate Matrix")
    lines.append("")
    header = "| Model |" + " | ".join(platforms) + " | Overall |"
    separator = "|" + "---|" * (len(platforms) + 2)
    lines.append(header)
    lines.append(separator)

    model_pass_rates: dict[str, float] = {}
    for model in models:
        cells: list[str] = []
        model_runs = [r for r in results if r["model"] == model]
        model_passes = sum(1 for r in model_runs if r["passed"])
        model_pass_rates[model] = model_passes / len(model_runs) if model_runs else 0
        for platform in platforms:
            runs = [r for r in results if r["model"] == model and r["platform"] == platform]
            passes = sum(1 for r in runs if r["passed"])
            cells.append(_pct(passes, len(runs)))
        cells.append(_pct(model_passes, len(model_runs)))
        lines.append(f"| {model} | " + " | ".join(cells) + " |")

    # Platform totals row
    cells = []
    for platform in platforms:
        runs = [r for r in results if r["platform"] == platform]
        passes = sum(1 for r in runs if r["passed"])
        cells.append(_pct(passes, len(runs)))
    total_passes = sum(1 for r in results if r["passed"])
    cells.append(_pct(total_passes, len(results)))
    lines.append(f"| **Overall** | " + " | ".join(cells) + " |")
    lines.append("")

    # --- Key Findings ---
    lines.append("## Key Findings")
    lines.append("")

    # Best model
    best_model = max(models, key=lambda m: model_pass_rates.get(m, 0))
    lines.append(f"- **Best model**: {best_model} ({model_pass_rates[best_model]*100:.0f}% pass rate)")

    # Best platform
    platform_pass_rates: dict[str, float] = {}
    for platform in platforms:
        runs = [r for r in results if r["platform"] == platform]
        passes = sum(1 for r in runs if r["passed"])
        platform_pass_rates[platform] = passes / len(runs) if runs else 0
    best_platform = max(platforms, key=lambda p: platform_pass_rates.get(p, 0))
    lines.append(f"- **Best platform**: {best_platform} ({platform_pass_rates[best_platform]*100:.0f}% pass rate)")

    # Pipeline correctness
    pipeline_ok = sum(1 for r in results if r.get("correct_pipeline"))
    lines.append(f"- **Pipeline correctness**: {_pct(pipeline_ok, len(results))}")

    # llms.txt discovery
    llms_found = sum(1 for r in results if _check_llms_txt(r))
    lines.append(f"- **llms.txt discovery rate**: {_pct(llms_found, len(results))}")

    # Markdown variant usage
    md_found = sum(1 for r in results if _check_md_variant(r))
    lines.append(f"- **Markdown variant usage rate**: {_pct(md_found, len(results))}")

    # Average API calls
    avg_api = _avg([len(r.get("api_calls_made", [])) for r in results])
    lines.append(f"- **Average API calls per run**: {avg_api:.1f}")

    # Average docs pages
    avg_docs = _avg([len(r.get("docs_pages_fetched", [])) for r in results])
    lines.append(f"- **Average docs pages fetched per run**: {avg_docs:.1f}")
    lines.append("")

    # --- Behavioral Analysis (manual runs only) ---
    manual_runs = [r for r in results if r.get("source") == "manual"]
    if manual_runs:
        agent_systems = sorted({r.get("agent_system", "") for r in manual_runs})
        lines.append("## Behavioral Analysis")
        lines.append("")
        lines.append("| Agent System | Avg Docs Fetches | First Action: Docs% | Fetch Timing: Before% | MCP Used% |")
        lines.append("|---|---|---|---|---|")
        for agent in agent_systems:
            runs = [r for r in manual_runs if r.get("agent_system") == agent]
            avg_df = _avg([r.get("docs_fetch_count", 0) for r in runs])
            first_docs = sum(1 for r in runs if r.get("first_action") == "docs_fetch")
            before = sum(1 for r in runs if r.get("docs_fetch_timing") == "before_first_api_call")
            mcp = sum(1 for r in runs if r.get("used_mcp_for_docs"))
            lines.append(
                f"| {agent} | {avg_df:.1f} | {_pct(first_docs, len(runs))} | {_pct(before, len(runs))} | {_pct(mcp, len(runs))} |"
            )
        lines.append("")

    # --- Detailed Per-Run Breakdown ---
    lines.append("## Detailed Per-Run Breakdown")
    lines.append("")
    lines.append("| Source | Agent System | Model | Platform | Run | Passed | Score | Pipeline OK |")
    lines.append("|---|---|---|---|---|---|---|---|")

    for r in sorted(results, key=lambda x: (x.get("source", ""), x["model"], x["platform"], x["run_index"])):
        source = r.get("source", "automated")
        agent_system = r.get("agent_system", "--")
        passed_str = "PASS" if r["passed"] else "FAIL"
        score_str = f"{r['final_score']:.2f}" if r.get("final_score") is not None else "--"
        pipeline_str = "Yes" if r.get("correct_pipeline") else "No"
        lines.append(
            f"| {source} | {agent_system} | {r['model']} | {r['platform']} | {r['run_index']} | "
            f"{passed_str} | {score_str} | {pipeline_str} |"
        )

    lines.append("")

    report_text = "\n".join(lines)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(report_text)
    print(f"Report written to {output_path}")


def main() -> None:
    base = Path(__file__).resolve().parent.parent
    results_dir = base / "harness" / "results"
    manual_log = base / "harness" / "manual" / "log.csv"
    output_path = Path(__file__).resolve().parent / "report.md"

    automated = load_results(results_dir)
    manual = load_manual_results(manual_log)
    results = automated + manual
    print(f"Loaded {len(automated)} automated + {len(manual)} manual = {len(results)} total result(s)")
    generate_report(results, output_path)


if __name__ == "__main__":
    main()
