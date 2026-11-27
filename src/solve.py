"""CLI for running LogicAgent with full deduction trace export and uniqueness checking.

Satisfies Section 4.4 requirements for user-facing output:
- Full no-guess deduction trace: step number, active clue IDs, SAT queries,
  chosen verdict, and newly revealed clue ID.
- Separate puzzle-level uniqueness check over the full clue set
  (``UNIQUE`` / ``MULTIPLE`` / ``UNSAT``).
- Optional JSON export via ``--json``.

Usage (from repository root):
    python src/solve.py --puzzle src/puzzles/sample_3x3.json
    python src/solve.py --puzzle src/puzzles/sample_4x4.json --json trace_4x4.json
    python src/solve.py --all

Usage (from src/ or Source/):
    python solve.py --puzzle puzzles/sample_3x3.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

SRC_DIR = Path(__file__).resolve().parent
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from agent import LogicAgent, SolveReport
from game_engine import GameEngine
from models import DeductionStep, Puzzle, UniquenessStatus

DEFAULT_PUZZLES_DIR = SRC_DIR / "puzzles"


def _step_to_dict(step: DeductionStep) -> dict[str, Any]:
    return {
        "step": step.step,
        "active_clue_ids": list(step.active_clue_ids),
        "sat_queries": list(step.sat_queries),
        "sat_calls": step.sat_calls,
        "target_coord": step.target_coord,
        "verdict": step.verdict,
        "newly_revealed_clue_id": step.newly_revealed_clue_id,
    }


def solve_puzzle_file(
    puzzle_path: Path | str,
    *,
    time_limit_ms: float | None = None,
    check_uniqueness: bool = True,
) -> dict[str, Any]:
    """Run no-guess deduction and (separately) full-clue uniqueness check on a puzzle JSON.

    Strict information hiding is preserved:
    - ``LogicAgent.solve_puzzle()`` receives only ``GameEngine`` (exposing ``PublicState``).
    - ``LogicAgent.check_uniqueness()`` runs as a separate puzzle validation step over
      the clue set and board size only (never inspects ``hidden_status``).
    """
    path = Path(puzzle_path)
    if not path.is_file():
        raise FileNotFoundError(f"Puzzle file not found: {path}")

    with open(path, "r", encoding="utf-8") as handle:
        raw_data = json.load(handle)
    puzzle = Puzzle.from_dict(raw_data)

    agent = LogicAgent()
    uniqueness: UniquenessStatus | None = None
    if check_uniqueness:
        uniqueness = agent.check_uniqueness([cell.clue for cell in puzzle.cells], puzzle.size)

    engine = GameEngine(puzzle, agent=agent)
    report: SolveReport = agent.solve_puzzle(engine, time_limit_ms=time_limit_ms)

    return {
        "puzzle_id": puzzle.puzzle_id,
        "puzzle_file": str(path),
        "size": puzzle.size,
        "initial_revealed": list(puzzle.initial_revealed),
        "uniqueness": uniqueness,
        "status": report.status,
        "metrics": {
            "steps_count": len(report.steps),
            "sat_calls": report.sat_calls,
            "decisions": report.decisions,
            "propagations": report.propagations,
            "backtracks": report.backtracks,
            "runtime_ms": round(report.runtime_ms, 3),
        },
        "trace": [_step_to_dict(step) for step in report.steps],
    }


def format_result_text(result: dict[str, Any]) -> str:
    """Render a puzzle solve result and full deduction trace as readable text."""
    metrics = result["metrics"]
    lines: list[str] = [
        f"Puzzle: {result['puzzle_id']} ({result['size']}x{result['size']}) | File: {result['puzzle_file']}",
        f"Initial revealed ({len(result['initial_revealed'])}): {', '.join(result['initial_revealed']) or '-'}",
    ]
    if result["uniqueness"] is not None:
        lines.append(f"Uniqueness check (full clue set): {result['uniqueness']}")
    lines.append(
        "Summary: "
        f"status={result['status']} | "
        f"steps={metrics['steps_count']} | "
        f"sat_calls={metrics['sat_calls']} | "
        f"decisions={metrics['decisions']} | "
        f"propagations={metrics['propagations']} | "
        f"backtracks={metrics['backtracks']} | "
        f"runtime_ms={metrics['runtime_ms']:.3f}"
    )

    trace: list[dict[str, Any]] = result["trace"]
    lines.append(f"Deduction Trace ({len(trace)} steps):")
    if not trace:
        lines.append("  (no forced deduction steps recorded)")
    else:
        for step in trace:
            active = ", ".join(step["active_clue_ids"]) if step["active_clue_ids"] else "-"
            revealed = step["newly_revealed_clue_id"] or "-"
            lines.append(f"  Step {step['step']}: {step['target_coord']} -> {step['verdict']}")
            lines.append(f"    Active clues ({len(step['active_clue_ids'])}): {active}")
            lines.append(f"    SAT queries ({step['sat_calls']}):")
            for query in step["sat_queries"]:
                lines.append(f"      - {query}")
            lines.append(f"    Newly revealed clue: {revealed}")

    return "\n".join(lines)


def _discover_puzzles(puzzles_dir: Path) -> list[Path]:
    if not puzzles_dir.is_dir():
        return []
    return sorted(puzzles_dir.glob("*.json"), key=lambda p: p.name.lower())


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Run Griductive LogicAgent no-guess solver, print the full deduction trace "
            "(steps, active clues, SAT queries, verdicts, newly revealed clues), "
            "and perform a separate full-clue uniqueness check."
        )
    )
    parser.add_argument(
        "--puzzle",
        type=Path,
        action="append",
        help="Path to a puzzle JSON file (may be specified multiple times).",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help=f"Run on all JSON puzzles in {DEFAULT_PUZZLES_DIR.name}/.",
    )
    parser.add_argument(
        "--puzzles-dir",
        type=Path,
        default=DEFAULT_PUZZLES_DIR,
        help="Puzzle directory used with --all (default: src/puzzles).",
    )
    parser.add_argument(
        "--json",
        dest="json_out",
        type=Path,
        default=None,
        help="Optional output path to export the full trace and uniqueness check as JSON.",
    )
    parser.add_argument(
        "--time-limit-ms",
        type=float,
        default=None,
        help="Optional soft time budget in milliseconds for LogicAgent.solve_puzzle().",
    )
    parser.add_argument(
        "--skip-uniqueness",
        action="store_true",
        help="Skip the separate full-clue check_uniqueness() call.",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress human-readable stdout output (useful with --json).",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    targets: list[Path] = []
    if args.puzzle:
        targets.extend(args.puzzle)
    if args.all:
        targets.extend(_discover_puzzles(args.puzzles_dir))

    if not targets:
        parser.error("Provide at least one --puzzle <file> or pass --all.")

    results: list[dict[str, Any]] = []
    for index, puzzle_path in enumerate(targets):
        result = solve_puzzle_file(
            puzzle_path,
            time_limit_ms=args.time_limit_ms,
            check_uniqueness=not args.skip_uniqueness,
        )
        results.append(result)
        if not args.quiet:
            if index > 0:
                print("\n" + "=" * 72 + "\n")
            print(format_result_text(result))

    if args.json_out is not None:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        payload: Any = results[0] if (len(results) == 1 and not args.all) else {"puzzles": results}
        args.json_out.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        if not args.quiet:
            print(f"\nExported JSON trace to: {args.json_out}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
