"""Generate benchmark summary tables and charts from benchmark_results.csv (Khoa — Section 4.5).

Covers all six required metric groups:
1. Primary & auxiliary variables
2. CNF clauses
3. SAT calls
4. DPLL decisions, propagations, and backtracks
5. Deduction steps / reveal waves
6. Runtime (ms)

Preserves and clearly visualizes failure and timeout rows without counting them
as successful solves.

Usage:
    python src/experiments/plot_results.py --input benchmark_results.csv --output assets
"""

from __future__ import annotations

import argparse
import csv
import math
import statistics
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any


SUCCESS_STATUSES = {"SOLVED", "SUCCESS", "OK", "UNIQUE_SOLVED", "PASSED"}
TIMEOUT_STATUSES = {"TIMEOUT", "TIMED_OUT", "TIME_LIMIT"}


@dataclass(frozen=True)
class BenchmarkRow:
    """Normalized benchmark record covering all six required metric groups."""

    puzzle_id: str
    size: int
    status: str  # Canonicalized: "SOLVED", "TIMEOUT", or failure label (e.g. "UNKNOWN", "INCONSISTENT", "FAILED")
    num_primary_vars: float | None
    num_aux_vars: float | None
    num_clauses: float | None
    sat_calls: float | None
    decisions: float | None
    propagations: float | None
    backtracks: float | None
    deduction_steps: float | None
    reveal_waves: float | None
    runtime_ms: float | None
    notes: str = ""

    @property
    def outcome_bucket(self) -> str:
        upper = self.status.upper()
        if upper in SUCCESS_STATUSES:
            return "SOLVED"
        if upper in TIMEOUT_STATUSES:
            return "TIMEOUT"
        return "FAILED"


COLUMN_ALIASES: dict[str, tuple[str, ...]] = {
    "puzzle_id": ("puzzle_id", "puzzle", "name", "id"),
    "size": ("size", "grid_size", "n", "board_size"),
    "status": ("status", "outcome", "result", "terminal_state"),
    "num_primary_vars": ("num_primary_vars", "primary_vars", "primary_variables"),
    "num_aux_vars": ("num_aux_vars", "aux_vars", "auxiliary_vars", "auxiliary_variables"),
    "num_clauses": ("num_clauses", "clauses", "cnf_clauses", "max_clauses"),
    "sat_calls": ("sat_calls", "num_sat_calls", "total_sat_calls"),
    "decisions": ("decisions", "total_decisions", "num_decisions"),
    "propagations": ("propagations", "total_propagations", "num_propagations"),
    "backtracks": ("backtracks", "total_backtracks", "num_backtracks"),
    "deduction_steps": ("deduction_steps", "steps", "num_steps", "total_steps"),
    "reveal_waves": ("reveal_waves", "waves", "num_waves"),
    "runtime_ms": ("runtime_ms", "total_runtime_ms", "elapsed_ms", "time_ms"),
    "runtime_s": ("runtime_s", "runtime_sec", "elapsed_s", "time_s"),
    "notes": ("notes", "error", "reason", "message"),
}


def _pick_column(row: dict[str, str], field: str) -> str | None:
    lowered = {k.strip().lower(): v for k, v in row.items() if k is not None}
    for alias in COLUMN_ALIASES[field]:
        if alias in lowered:
            raw = lowered[alias]
            if raw is not None and str(raw).strip() != "":
                return str(raw).strip()
    return None


def _parse_float(value: str | None) -> float | None:
    if value is None:
        return None
    text = value.strip()
    if not text or text.lower() in {"na", "n/a", "none", "null", "-", "nan"}:
        return None
    val = float(text)
    if math.isnan(val) or math.isinf(val):
        return None
    return val


def _parse_size(raw_size: str | None, puzzle_id: str) -> int:
    if raw_size is not None:
        cleaned = raw_size.lower().split("x")[0].strip()
        try:
            return int(float(cleaned))
        except ValueError:
            pass
    # Infer from puzzle_id like "grid_4x4_01" if size column missing
    lower = puzzle_id.lower()
    for n in (3, 4, 5, 6):
        if f"{n}x{n}" in lower:
            return n
    return 0


def _normalize_status(raw_status: str | None) -> str:
    if raw_status is None:
        # Missing outcome data must never be silently counted as a success.
        return "MISSING_STATUS"
    upper = raw_status.strip().upper()
    if upper in SUCCESS_STATUSES:
        return "SOLVED"
    if upper in TIMEOUT_STATUSES:
        return "TIMEOUT"
    return upper or "FAILED"


def load_benchmark_csv(csv_path: Path) -> list[BenchmarkRow]:
    """Read benchmark CSV into normalized ``BenchmarkRow`` objects without dropping failures/timeouts."""
    if not csv_path.is_file():
        raise FileNotFoundError(f"Benchmark CSV not found: {csv_path}")

    rows: list[BenchmarkRow] = []
    with open(csv_path, "r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames:
            raise ValueError(f"Benchmark CSV has no header row: {csv_path}")

        for idx, raw in enumerate(reader, start=1):
            if not any((v or "").strip() for v in raw.values()):
                continue
            puzzle_id = _pick_column(raw, "puzzle_id") or f"puzzle_{idx}"
            size = _parse_size(_pick_column(raw, "size"), puzzle_id)
            status = _normalize_status(_pick_column(raw, "status"))

            runtime_ms = _parse_float(_pick_column(raw, "runtime_ms"))
            if runtime_ms is None:
                runtime_s = _parse_float(_pick_column(raw, "runtime_s"))
                if runtime_s is not None:
                    runtime_ms = runtime_s * 1000.0

            rows.append(
                BenchmarkRow(
                    puzzle_id=puzzle_id,
                    size=size,
                    status=status,
                    num_primary_vars=_parse_float(_pick_column(raw, "num_primary_vars")),
                    num_aux_vars=_parse_float(_pick_column(raw, "num_aux_vars")),
                    num_clauses=_parse_float(_pick_column(raw, "num_clauses")),
                    sat_calls=_parse_float(_pick_column(raw, "sat_calls")),
                    decisions=_parse_float(_pick_column(raw, "decisions")),
                    propagations=_parse_float(_pick_column(raw, "propagations")),
                    backtracks=_parse_float(_pick_column(raw, "backtracks")),
                    deduction_steps=_parse_float(_pick_column(raw, "deduction_steps")),
                    reveal_waves=_parse_float(_pick_column(raw, "reveal_waves")),
                    runtime_ms=runtime_ms,
                    notes=_pick_column(raw, "notes") or "",
                )
            )

    if not rows:
        raise ValueError(f"Benchmark CSV contains no data rows: {csv_path}")
    return rows


def summarize_by_size(rows: list[BenchmarkRow]) -> list[dict[str, Any]]:
    """Aggregate benchmark metrics by grid size, excluding timeout/failure from success means."""
    sizes = sorted({r.size for r in rows})
    summary: list[dict[str, Any]] = []

    def mean_of(items: list[BenchmarkRow], attr: str) -> float | None:
        vals = [getattr(r, attr) for r in items if getattr(r, attr) is not None]
        return statistics.mean(vals) if vals else None

    for size in sizes:
        group = [r for r in rows if r.size == size]
        solved = [r for r in group if r.outcome_bucket == "SOLVED"]
        timeouts = [r for r in group if r.outcome_bucket == "TIMEOUT"]
        failed = [r for r in group if r.outcome_bucket == "FAILED"]

        summary.append(
            {
                "size": size,
                "size_label": f"{size}x{size}" if size > 0 else "Unknown",
                "total": len(group),
                "solved": len(solved),
                "timeout": len(timeouts),
                "failed": len(failed),
                "avg_primary_vars": mean_of(solved, "num_primary_vars"),
                "avg_aux_vars": mean_of(solved, "num_aux_vars"),
                "avg_clauses": mean_of(solved, "num_clauses"),
                "avg_sat_calls": mean_of(solved, "sat_calls"),
                "avg_decisions": mean_of(solved, "decisions"),
                "avg_propagations": mean_of(solved, "propagations"),
                "avg_backtracks": mean_of(solved, "backtracks"),
                "avg_deduction_steps": mean_of(solved, "deduction_steps"),
                "avg_reveal_waves": mean_of(solved, "reveal_waves"),
                "avg_runtime_ms": mean_of(solved, "runtime_ms"),
            }
        )
    return summary


def _fmt_num(val: float | None, decimals: int = 1) -> str:
    if val is None:
        return "-"
    if decimals == 0 or float(val).is_integer():
        return f"{val:.0f}"
    return f"{val:.{decimals}f}"


def build_markdown_summary(rows: list[BenchmarkRow]) -> str:
    """Create Markdown tables preserving every puzzle (including failures/timeouts)."""
    size_summary = summarize_by_size(rows)
    total = len(rows)
    solved_count = sum(1 for r in rows if r.outcome_bucket == "SOLVED")
    timeout_count = sum(1 for r in rows if r.outcome_bucket == "TIMEOUT")
    failed_count = sum(1 for r in rows if r.outcome_bucket == "FAILED")

    lines: list[str] = [
        "# Benchmark Summary (6 Metric Groups)",
        "",
        f"- Total puzzles: **{total}** (Solved: **{solved_count}**, Timeout: **{timeout_count}**, Failed/Other: **{failed_count}**)",
        "- Note: Average metrics by grid size are computed over **SOLVED** puzzles only; timeout and failure cases are retained in full below and never counted as successes.",
        "- Missing or unavailable numeric measurements are shown as `-` in tables and left blank in charts; they are not treated as zero.",
        "",
        "## 1. Per-Puzzle Results (All Cases Retained)",
        "",
        "| Puzzle | Size | Status | Primary Vars | Aux Vars | Clauses | SAT Calls | Decisions | Propagations | Backtracks | Steps | Waves | Runtime (ms) |",
        "| :--- | :---: | :---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]

    for r in rows:
        size_str = f"{r.size}x{r.size}" if r.size > 0 else "-"
        lines.append(
            f"| {r.puzzle_id} | {size_str} | {r.status} | "
            f"{_fmt_num(r.num_primary_vars, 0)} | {_fmt_num(r.num_aux_vars, 0)} | "
            f"{_fmt_num(r.num_clauses, 0)} | {_fmt_num(r.sat_calls, 0)} | "
            f"{_fmt_num(r.decisions, 0)} | {_fmt_num(r.propagations, 0)} | {_fmt_num(r.backtracks, 0)} | "
            f"{_fmt_num(r.deduction_steps, 0)} | {_fmt_num(r.reveal_waves, 0)} | {_fmt_num(r.runtime_ms, 2)} |"
        )

    lines.extend(
        [
            "",
            "## 2. Aggregated Summary by Grid Size (Success Averages + Non-Success Counts)",
            "",
            "| Size | Total | Solved | Timeout | Failed | Avg Primary | Avg Aux | Avg Clauses | Avg SAT Calls | Avg Decisions | Avg Propagations | Avg Backtracks | Avg Steps | Avg Waves | Avg Runtime (ms) |",
            "| :---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
    )

    for s in size_summary:
        lines.append(
            f"| {s['size_label']} | {s['total']} | {s['solved']} | {s['timeout']} | {s['failed']} | "
            f"{_fmt_num(s['avg_primary_vars'])} | {_fmt_num(s['avg_aux_vars'])} | {_fmt_num(s['avg_clauses'])} | "
            f"{_fmt_num(s['avg_sat_calls'])} | {_fmt_num(s['avg_decisions'])} | {_fmt_num(s['avg_propagations'])} | "
            f"{_fmt_num(s['avg_backtracks'])} | {_fmt_num(s['avg_deduction_steps'])} | "
            f"{_fmt_num(s['avg_reveal_waves'])} | {_fmt_num(s['avg_runtime_ms'], 2)} |"
        )

    non_success = [r for r in rows if r.outcome_bucket != "SOLVED"]
    if non_success:
        lines.extend(["", "## 3. Failure & Timeout Cases", ""])
        for r in non_success:
            note = f" — {r.notes}" if r.notes else ""
            lines.append(
                f"- **{r.puzzle_id}** ({r.size}x{r.size}): `{r.status}` "
                f"(steps={_fmt_num(r.deduction_steps, 0)}, sat_calls={_fmt_num(r.sat_calls, 0)}, "
                f"runtime={_fmt_num(r.runtime_ms, 2)} ms){note}"
            )

    return "\n".join(lines) + "\n"


def _status_bar_style(bucket: str) -> tuple[str, str | None]:
    if bucket == "SOLVED":
        return "#2E8B57", None
    if bucket == "TIMEOUT":
        return "#D97706", "//"
    return "#DC2626", "xx"


def _chart_value(value: float | None) -> float:
    """Leave unavailable measurements blank instead of drawing them as zero."""
    return value if value is not None else math.nan


def _finite_peak(*values: float) -> float:
    """Choose a valid label height when some plotted metrics are unavailable."""
    finite = [value for value in values if math.isfinite(value)]
    return max(finite, default=0.0)


def generate_charts(rows: list[BenchmarkRow], output_dir: Path) -> list[Path]:
    """Render report-ready charts for all 6 metric groups into ``output_dir``."""
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        from matplotlib.patches import Patch
    except ImportError as exc:
        raise RuntimeError(
            "matplotlib is required to generate benchmark charts. "
            "Install it with: pip install -r requirements.txt"
        ) from exc

    output_dir.mkdir(parents=True, exist_ok=True)
    generated: list[Path] = []

    labels = [
        f"{r.puzzle_id}\n({r.size}x{r.size})" if r.size > 0 else r.puzzle_id
        for r in rows
    ]
    x = list(range(len(rows)))
    fig_w = max(9.0, min(18.0, 1.35 * len(rows) + 3.0))

    legend_handles = [
        Patch(facecolor="#2E8B57", label="SOLVED"),
        Patch(facecolor="#D97706", hatch="//", edgecolor="black", label="TIMEOUT"),
        Patch(facecolor="#DC2626", hatch="xx", edgecolor="black", label="FAILED / OTHER"),
    ]

    # ------------------------------------------------------------------
    # Chart 1: CNF Size — Primary/Aux Variables & Clauses (Groups 1 & 2)
    # ------------------------------------------------------------------
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(fig_w, 8.2), sharex=True)
    primary_vals = [_chart_value(r.num_primary_vars) for r in rows]
    aux_vals = [_chart_value(r.num_aux_vars) for r in rows]
    clause_vals = [_chart_value(r.num_clauses) for r in rows]

    bars_p = ax1.bar(x, primary_vals, label="Primary Vars", color="#2563EB")
    bars_a = ax1.bar(x, aux_vals, bottom=primary_vals, label="Auxiliary Vars", color="#60A5FA")
    for idx, r in enumerate(rows):
        if r.outcome_bucket != "SOLVED":
            hatch = "//" if r.outcome_bucket == "TIMEOUT" else "xx"
            bars_p[idx].set_hatch(hatch)
            bars_a[idx].set_hatch(hatch)
            total_v = _finite_peak(primary_vals[idx], primary_vals[idx] + aux_vals[idx])
            ax1.text(idx, total_v, r.status, ha="center", va="bottom", fontsize=8, fontweight="bold", color="#B91C1C")
    ax1.set_ylabel("Variables")
    ax1.set_title("Group 1 & 2: CNF Encoding Size (Primary/Auxiliary Variables & Clauses)")
    ax1.legend(loc="upper left")
    ax1.grid(axis="y", linestyle="--", alpha=0.4)

    bars_c = ax2.bar(x, clause_vals)
    for idx, r in enumerate(rows):
        color, hatch = _status_bar_style(r.outcome_bucket)
        bars_c[idx].set_facecolor(color)
        if hatch:
            bars_c[idx].set_hatch(hatch)
            bars_c[idx].set_edgecolor("black")
            ax2.text(idx, _finite_peak(clause_vals[idx]), r.status, ha="center", va="bottom", fontsize=8, fontweight="bold", color="#B91C1C")
    ax2.set_ylabel("CNF Clauses")
    ax2.set_xticks(x)
    ax2.set_xticklabels(labels, rotation=20, ha="right")
    ax2.legend(handles=legend_handles, loc="upper left")
    ax2.grid(axis="y", linestyle="--", alpha=0.4)

    fig.tight_layout()
    chart1 = output_dir / "chart_1_cnf_size.png"
    fig.savefig(chart1, dpi=180)
    plt.close(fig)
    generated.append(chart1)

    # ------------------------------------------------------------------
    # Chart 2: SAT Calls & DPLL Search Metrics (Groups 3 & 4)
    # ------------------------------------------------------------------
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(fig_w, 8.4), sharex=True)
    sat_vals = [_chart_value(r.sat_calls) for r in rows]
    bars_s = ax1.bar(x, sat_vals)
    for idx, r in enumerate(rows):
        color, hatch = _status_bar_style(r.outcome_bucket)
        bars_s[idx].set_facecolor(color)
        if hatch:
            bars_s[idx].set_hatch(hatch)
            bars_s[idx].set_edgecolor("black")
            ax1.text(idx, _finite_peak(sat_vals[idx]), r.status, ha="center", va="bottom", fontsize=8, fontweight="bold", color="#B91C1C")
    ax1.set_ylabel("SAT Calls")
    ax1.set_title("Group 3 & 4: SAT Calls and DPLL Metrics (Decisions, Propagations, Backtracks)")
    ax1.legend(handles=legend_handles, loc="upper left")
    ax1.grid(axis="y", linestyle="--", alpha=0.4)

    width = 0.26
    dec_vals = [_chart_value(r.decisions) for r in rows]
    prop_vals = [_chart_value(r.propagations) for r in rows]
    bt_vals = [_chart_value(r.backtracks) for r in rows]
    ax2.bar([i - width for i in x], dec_vals, width=width, label="Decisions", color="#7C3AED")
    ax2.bar(x, prop_vals, width=width, label="Propagations", color="#0EA5E9")
    ax2.bar([i + width for i in x], bt_vals, width=width, label="Backtracks", color="#F97316")
    for idx, r in enumerate(rows):
        if r.outcome_bucket != "SOLVED":
            peak = _finite_peak(dec_vals[idx], prop_vals[idx], bt_vals[idx])
            ax2.text(idx, peak, r.status, ha="center", va="bottom", fontsize=8, fontweight="bold", color="#B91C1C")
    ax2.set_ylabel("Count")
    ax2.set_xticks(x)
    ax2.set_xticklabels(labels, rotation=20, ha="right")
    ax2.legend(loc="upper left")
    ax2.grid(axis="y", linestyle="--", alpha=0.4)

    fig.tight_layout()
    chart2 = output_dir / "chart_2_dpll_metrics.png"
    fig.savefig(chart2, dpi=180)
    plt.close(fig)
    generated.append(chart2)

    # ------------------------------------------------------------------
    # Chart 3: Deduction Steps / Reveal Waves & Runtime (Groups 5 & 6)
    # ------------------------------------------------------------------
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(fig_w, 8.4), sharex=True)
    steps_vals = [_chart_value(r.deduction_steps) for r in rows]
    waves_vals = [_chart_value(r.reveal_waves) for r in rows]
    has_waves = any(r.reveal_waves is not None for r in rows)

    if has_waves:
        w = 0.36
        ax1.bar([i - w / 2 for i in x], steps_vals, width=w, label="Deduction Steps", color="#0D9488")
        ax1.bar([i + w / 2 for i in x], waves_vals, width=w, label="Reveal Waves", color="#6366F1")
    else:
        ax1.bar(x, steps_vals, label="Deduction Steps", color="#0D9488")
    for idx, r in enumerate(rows):
        if r.outcome_bucket != "SOLVED":
            peak = _finite_peak(steps_vals[idx], waves_vals[idx] if has_waves else 0.0)
            ax1.text(idx, peak, r.status, ha="center", va="bottom", fontsize=8, fontweight="bold", color="#B91C1C")
    ax1.set_ylabel("Steps / Waves")
    ax1.set_title("Group 5 & 6: Deduction Steps, Reveal Waves & Runtime (ms)")
    ax1.legend(loc="upper left")
    ax1.grid(axis="y", linestyle="--", alpha=0.4)

    rt_vals = [_chart_value(r.runtime_ms) for r in rows]
    bars_rt = ax2.bar(x, rt_vals)
    for idx, r in enumerate(rows):
        color, hatch = _status_bar_style(r.outcome_bucket)
        bars_rt[idx].set_facecolor(color)
        if hatch:
            bars_rt[idx].set_hatch(hatch)
            bars_rt[idx].set_edgecolor("black")
            ax2.text(idx, _finite_peak(rt_vals[idx]), r.status, ha="center", va="bottom", fontsize=8, fontweight="bold", color="#B91C1C")
    ax2.set_ylabel("Runtime (ms)")
    ax2.set_xticks(x)
    ax2.set_xticklabels(labels, rotation=20, ha="right")
    ax2.legend(handles=legend_handles, loc="upper left")
    ax2.grid(axis="y", linestyle="--", alpha=0.4)

    fig.tight_layout()
    chart3 = output_dir / "chart_3_deduction_runtime.png"
    fig.savefig(chart3, dpi=180)
    plt.close(fig)
    generated.append(chart3)

    # ------------------------------------------------------------------
    # Chart 4: Scaling by Grid Size (Success Averages + Outcomes)
    # ------------------------------------------------------------------
    size_summary = summarize_by_size(rows)
    s_labels = [s["size_label"] for s in size_summary]
    sx = list(range(len(size_summary)))

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(11.5, 4.8))
    solved_counts = [s["solved"] for s in size_summary]
    timeout_counts = [s["timeout"] for s in size_summary]
    failed_counts = [s["failed"] for s in size_summary]

    ax1.bar(sx, solved_counts, label="SOLVED", color="#2E8B57")
    ax1.bar(sx, timeout_counts, bottom=solved_counts, label="TIMEOUT", color="#D97706", hatch="//", edgecolor="black")
    bottom2 = [a + b for a, b in zip(solved_counts, timeout_counts)]
    ax1.bar(sx, failed_counts, bottom=bottom2, label="FAILED", color="#DC2626", hatch="xx", edgecolor="black")
    ax1.set_xticks(sx)
    ax1.set_xticklabels(s_labels)
    ax1.set_ylabel("Puzzle Count")
    ax1.set_title("Outcomes by Grid Size")
    ax1.legend(loc="upper right")
    ax1.grid(axis="y", linestyle="--", alpha=0.4)

    avg_rt = [_chart_value(s["avg_runtime_ms"]) for s in size_summary]
    avg_calls = [_chart_value(s["avg_sat_calls"]) for s in size_summary]
    ax2.plot(sx, avg_rt, marker="o", linewidth=2, color="#2563EB", label="Avg Runtime (ms, solved only)")
    ax2.set_xticks(sx)
    ax2.set_xticklabels(s_labels)
    ax2.set_ylabel("Avg Runtime (ms)", color="#2563EB")
    ax2.set_title("Scaling Across Grid Sizes (Solved Only)")
    ax2.grid(axis="y", linestyle="--", alpha=0.4)

    ax2_r = ax2.twinx()
    ax2_r.plot(sx, avg_calls, marker="s", linestyle="--", linewidth=2, color="#7C3AED", label="Avg SAT Calls (solved only)")
    ax2_r.set_ylabel("Avg SAT Calls", color="#7C3AED")

    h1, l1 = ax2.get_legend_handles_labels()
    h2, l2 = ax2_r.get_legend_handles_labels()
    ax2.legend(h1 + h2, l1 + l2, loc="upper left", fontsize=8)

    fig.tight_layout()
    chart4 = output_dir / "chart_4_size_scaling.png"
    fig.savefig(chart4, dpi=180)
    plt.close(fig)
    generated.append(chart4)

    return generated


def generate_report_artifacts(csv_path: Path, output_dir: Path) -> tuple[Path, list[Path]]:
    """Load CSV, write Markdown summary table, and generate all benchmark charts."""
    rows = load_benchmark_csv(csv_path)
    output_dir.mkdir(parents=True, exist_ok=True)
    summary_md = output_dir / "benchmark_summary.md"
    summary_md.write_text(build_markdown_summary(rows), encoding="utf-8")
    charts = generate_charts(rows, output_dir)
    return summary_md, charts


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Plot Griductive Solver benchmark charts and summary tables from CSV."
    )
    parser.add_argument(
        "--input",
        "-i",
        type=Path,
        required=True,
        help="Path to benchmark_results.csv generated by Bao's benchmark runner.",
    )
    parser.add_argument(
        "--output",
        "-o",
        type=Path,
        default=Path("assets"),
        help="Output directory for PNG charts and Markdown summary (default: assets).",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    try:
        summary_path, chart_paths = generate_report_artifacts(args.input, args.output)
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    print(f"Wrote summary table: {summary_path}")
    for path in chart_paths:
        print(f"Wrote chart: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
