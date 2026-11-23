"""Benchmark runner for the Griductive Solver (Bao — Section 4.5).

Runs the whole pipeline (GameEngine -> CNF encoder -> DPLL -> LogicAgent) on
every puzzle in ``src/puzzles/`` and writes one CSV row per puzzle with the six
metric groups required by Section 4.5:

1. Primary and auxiliary variables  -> ``num_primary_vars``, ``num_aux_vars``
2. CNF clauses                      -> ``num_clauses`` (+ ``initial_clauses``,
                                       ``full_kb_clauses``)
3. SAT calls                        -> ``sat_calls``
4. Decisions / propagations / backtracks
                                    -> ``decisions``, ``propagations``, ``backtracks``
5. Deduction steps and reveal waves -> ``deduction_steps``, ``reveal_waves``
6. Runtime                          -> ``runtime_ms`` (median over ``--repeats``)

Failures and timeouts are written to the CSV like any other row (Section 4.5:
"report failures and timeouts instead of dropping them").

Timeout guard has two layers:

- Soft: ``LogicAgent.solve_puzzle(time_limit_ms=...)`` stops the deduction loop
  and returns ``TIMEOUT`` with the partial metrics collected so far.
- Hard: each puzzle runs in its own child process; if it has not finished after
  ``--hard-timeout`` seconds the process is killed and a ``TIMEOUT`` row is
  written. This also covers work the soft limit cannot interrupt (the
  GameEngine's own verdict re-check, reveal-wave measurement, uniqueness check).

Metric definitions (all measured on the same puzzle set):

- ``num_primary_vars`` = N^2 cell variables C_i.
- ``num_aux_vars`` / ``num_clauses``: the largest knowledge base KB_t the agent
  queried, i.e. the KB at the last deduction step (KB only grows while clues
  are revealed). ``initial_clauses`` is KB_0 and ``full_kb_clauses`` encodes
  every clue of the puzzle (the formula used by the uniqueness check).
- ``sat_calls``, ``decisions``, ``propagations``, ``backtracks``, ``runtime_ms``
  come from the agent's ``SolveReport`` (agent queries only; the GameEngine's
  re-verification inside ``submit_verdict`` is not counted, see docs/DTUAN.md).
- ``deduction_steps``: accepted forced verdicts (one per step, row-major).
- ``reveal_waves``: number of rounds when the board is played wave by wave:
  classify every unsolved cell on KB_t, submit *all* forced verdicts together,
  reveal their clues, repeat. Measured on a fresh engine, separately from the
  metrics above.

Usage (from the repository root)::

    python src/experiments/run_experiments.py
    python src/experiments/run_experiments.py --output benchmark_results.csv \
        --time-limit-ms 60000 --hard-timeout 120 --repeats 3

The CSV is consumed by ``src/experiments/plot_results.py`` (Khoa).
"""

from __future__ import annotations

import argparse
import csv
import multiprocessing as mp
import platform
import statistics
import sys
import traceback
from dataclasses import asdict, dataclass, fields
from pathlib import Path
from time import perf_counter
from typing import Any

SRC_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = SRC_DIR.parent
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from agent import LogicAgent  # noqa: E402
from encoder import encode_clues, encode_public_state  # noqa: E402
from game_engine import GameEngine, evaluate_puzzle  # noqa: E402
from models import Puzzle  # noqa: E402

DEFAULT_PUZZLE_DIR = SRC_DIR / "puzzles"
DEFAULT_OUTPUT = REPO_ROOT / "benchmark_results.csv"
DEFAULT_TIME_LIMIT_MS = 60_000.0
DEFAULT_HARD_TIMEOUT_S = 180.0


@dataclass
class BenchmarkRecord:
    """One CSV row. Field order is the CSV column order."""

    puzzle_id: str
    file: str
    size: int
    status: str  # SOLVED | UNKNOWN | INCONSISTENT | TIMEOUT | FAILED
    # Group 1 & 2: encoding size
    num_primary_vars: int | None = None
    num_aux_vars: int | None = None
    num_clauses: int | None = None
    initial_clauses: int | None = None
    full_kb_clauses: int | None = None
    # Group 3 & 4: SAT calls and DPLL search metrics
    sat_calls: int | None = None
    decisions: int | None = None
    propagations: int | None = None
    backtracks: int | None = None
    # Group 5: deduction steps / reveal waves
    deduction_steps: int | None = None
    reveal_waves: int | None = None
    # Group 6: runtime
    runtime_ms: float | None = None
    runtime_ms_min: float | None = None
    runtime_ms_max: float | None = None
    repeats: int = 0
    # Sanity checks / context
    initial_revealed: int | None = None
    uniqueness: str | None = None
    solution_verified: bool | None = None
    notes: str = ""


CSV_COLUMNS = [f.name for f in fields(BenchmarkRecord)]


# ---------------------------------------------------------------------------
# Single-puzzle measurement (runs inside the worker process)
# ---------------------------------------------------------------------------

def _load_puzzle(path: Path) -> Puzzle:
    import json

    with open(path, "r", encoding="utf-8") as handle:
        return Puzzle.from_dict(json.load(handle))


def _count_reveal_waves(puzzle: Puzzle) -> tuple[int, str]:
    """Play the puzzle wave by wave on a fresh engine; return (waves, terminal)."""
    agent = LogicAgent()
    engine = GameEngine(puzzle, agent)
    waves = 0
    while True:
        state = engine.get_public_state()
        if not state.unsolved_coords:
            return waves, "SOLVED"
        verdicts = agent.classify_all(state)
        if any(v == "INCONSISTENT" for v in verdicts.values()):
            return waves, "INCONSISTENT"
        forced = [(c, v) for c, v in verdicts.items() if v in ("CRIMINAL", "INNOCENT")]
        if not forced:
            return waves, "UNKNOWN"
        for coord, verdict in forced:  # row-major order (classify_all is ordered)
            response = engine.submit_verdict(coord, verdict)
            if not response.accepted:
                return waves, f"REJECTED({coord}:{response.reason})"
        waves += 1


def _largest_kb_size(puzzle: Puzzle, report) -> tuple[int, int]:
    """Return (aux vars, clauses) of the largest KB_t the agent queried.

    KB_t only grows, so this is the KB of the last scan: before the last step
    when the board was solved, or after every step when the agent stopped
    early. Rebuilt by replaying the trace on a fresh engine, outside the timed
    run, so it does not inflate ``runtime_ms``.
    """
    steps = report.steps[:-1] if report.status == "SOLVED" else report.steps
    engine = GameEngine(puzzle, LogicAgent())
    for step in steps:
        response = engine.submit_verdict(step.target_coord, step.verdict)
        if not response.accepted:
            raise RuntimeError(f"trace replay rejected {step.target_coord}: {response.reason}")
    formula = encode_public_state(engine.get_public_state())
    return formula.num_aux_vars, formula.num_clauses


def measure_puzzle(path: Path, time_limit_ms: float | None, repeats: int) -> BenchmarkRecord:
    """Run the agent on one puzzle and collect all six metric groups.

    Never raises: any exception becomes a ``FAILED`` row with the error in
    ``notes``.
    """
    record = BenchmarkRecord(puzzle_id=path.stem, file=path.name, size=0, status="FAILED")
    notes: list[str] = []
    try:
        puzzle = _load_puzzle(path)
        record.puzzle_id = puzzle.puzzle_id
        record.size = puzzle.size
        record.initial_revealed = len(puzzle.initial_revealed)
        record.num_primary_vars = puzzle.size * puzzle.size

        full = encode_clues([cell.clue for cell in puzzle.cells], puzzle.size)
        record.full_kb_clauses = full.num_clauses
        record.uniqueness = LogicAgent().check_uniqueness(
            [cell.clue for cell in puzzle.cells], puzzle.size
        )
        if record.uniqueness != "UNIQUE":
            notes.append(f"uniqueness={record.uniqueness}")

        runtimes: list[float] = []
        reference: tuple[Any, ...] | None = None
        for run in range(max(1, repeats)):
            agent = LogicAgent()
            engine = GameEngine(puzzle, agent)
            record.initial_clauses = encode_public_state(engine.get_public_state()).num_clauses

            report = agent.solve_puzzle(engine, time_limit_ms=time_limit_ms)

            signature = (
                report.status, len(report.steps), report.sat_calls, report.decisions,
                report.propagations, report.backtracks,
                [(s.target_coord, s.verdict) for s in report.steps],
            )
            if reference is None:
                reference = signature
                record.status = report.status
                record.num_aux_vars, record.num_clauses = _largest_kb_size(puzzle, report)
                record.sat_calls = report.sat_calls
                record.decisions = report.decisions
                record.propagations = report.propagations
                record.backtracks = report.backtracks
                record.deduction_steps = len(report.steps)
                if report.status == "SOLVED":
                    proved = engine.get_proved_verdicts()
                    # Benchmark-side validation only; the agent never sees this.
                    record.solution_verified = (
                        proved == engine.get_solution_for_testing()
                        and evaluate_puzzle(puzzle, proved)
                    )
                    if not record.solution_verified:
                        notes.append("solution mismatch")
            elif signature != reference and report.status != "TIMEOUT":
                notes.append(f"non-deterministic metrics on repeat {run + 1}")
            runtimes.append(report.runtime_ms)
            if report.status == "TIMEOUT":
                notes.append(f"soft timeout after {report.runtime_ms:.1f} ms "
                             f"(limit {time_limit_ms:.0f} ms)")
                break  # no point repeating a timed-out run

        record.repeats = len(runtimes)
        record.runtime_ms = round(statistics.median(runtimes), 3)
        record.runtime_ms_min = round(min(runtimes), 3)
        record.runtime_ms_max = round(max(runtimes), 3)

        if record.status != "TIMEOUT":
            waves, wave_terminal = _count_reveal_waves(puzzle)
            record.reveal_waves = waves
            if wave_terminal != record.status:
                notes.append(f"wave run ended {wave_terminal}")
        if record.status in ("UNKNOWN", "INCONSISTENT"):
            notes.append(f"agent stopped: {record.status} after {record.deduction_steps} steps")
    except Exception as exc:  # report the failure instead of dropping the puzzle
        record.status = "FAILED"
        notes.append(f"{type(exc).__name__}: {exc}".replace("\n", " "))
        traceback.print_exc(file=sys.stderr)

    record.notes = "; ".join(notes)
    return record


def _worker(conn, path: str, time_limit_ms: float | None, repeats: int) -> None:
    try:
        conn.send(asdict(measure_puzzle(Path(path), time_limit_ms, repeats)))
    finally:
        conn.close()


def run_isolated(path: Path, time_limit_ms: float | None, repeats: int,
                 hard_timeout_s: float) -> BenchmarkRecord:
    """Run ``measure_puzzle`` in a child process killed after ``hard_timeout_s``."""
    ctx = mp.get_context("spawn")
    parent_conn, child_conn = ctx.Pipe(duplex=False)
    proc = ctx.Process(target=_worker, args=(child_conn, str(path), time_limit_ms, repeats),
                       daemon=True)
    start = perf_counter()
    proc.start()
    child_conn.close()
    payload: dict[str, Any] | None = None
    if parent_conn.poll(hard_timeout_s):
        try:
            payload = parent_conn.recv()
        except EOFError:
            payload = None
    elapsed_ms = (perf_counter() - start) * 1000.0
    if proc.is_alive():
        proc.terminate()
    proc.join(5)

    if payload is not None:
        return BenchmarkRecord(**payload)
    record = BenchmarkRecord(puzzle_id=path.stem, file=path.name, size=0, status="FAILED",
                             runtime_ms=round(elapsed_ms, 3))
    try:
        puzzle = _load_puzzle(path)
        record.puzzle_id, record.size = puzzle.puzzle_id, puzzle.size
        record.num_primary_vars = puzzle.size * puzzle.size
    except Exception:
        pass
    if elapsed_ms >= hard_timeout_s * 1000.0:
        record.status = "TIMEOUT"
        record.notes = f"hard timeout: process killed after {hard_timeout_s:g} s"
    else:
        record.notes = f"worker process exited with code {proc.exitcode} without a result"
    return record


# ---------------------------------------------------------------------------
# Batch driver & CSV output
# ---------------------------------------------------------------------------

def discover_puzzles(puzzle_dir: Path, pattern: str = "*.json") -> list[Path]:
    """Return puzzle files ordered by grid size, then file name (deterministic)."""
    paths = sorted(puzzle_dir.glob(pattern))
    if not paths:
        raise FileNotFoundError(f"No puzzle files matching {pattern!r} in {puzzle_dir}")

    def key(p: Path) -> tuple[int, str]:
        try:
            return _load_puzzle(p).size, p.name
        except Exception:
            return 99, p.name

    return sorted(paths, key=key)


def run_benchmark(
    puzzle_paths: list[Path],
    *,
    time_limit_ms: float | None = DEFAULT_TIME_LIMIT_MS,
    hard_timeout_s: float | None = DEFAULT_HARD_TIMEOUT_S,
    repeats: int = 3,
    isolate: bool = True,
    log=print,
) -> list[BenchmarkRecord]:
    records: list[BenchmarkRecord] = []
    for index, path in enumerate(puzzle_paths, start=1):
        if isolate and hard_timeout_s:
            record = run_isolated(path, time_limit_ms, repeats, hard_timeout_s)
        else:
            record = measure_puzzle(path, time_limit_ms, repeats)
        records.append(record)
        if log:
            log(f"[{index}/{len(puzzle_paths)}] {record.puzzle_id:<16} {record.status:<12} "
                f"steps={record.deduction_steps} waves={record.reveal_waves} "
                f"sat_calls={record.sat_calls} runtime={record.runtime_ms} ms"
                + (f"  ({record.notes})" if record.notes else ""))
    return records


def _csv_value(value: Any) -> Any:
    if value is None:
        return ""
    return value


def write_csv(records: list[BenchmarkRecord], output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    with open(output, "w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        for record in records:
            writer.writerow({k: _csv_value(v) for k, v in asdict(record).items()})


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run the Griductive benchmark and export the six Section 4.5 metric groups to CSV."
    )
    parser.add_argument("--puzzles", "-p", type=Path, default=DEFAULT_PUZZLE_DIR,
                        help="Directory with puzzle JSON files (default: src/puzzles).")
    parser.add_argument("--pattern", default="*.json",
                        help="Glob pattern for puzzle files (default: *.json).")
    parser.add_argument("--output", "-o", type=Path, default=DEFAULT_OUTPUT,
                        help="Output CSV path (default: benchmark_results.csv at repo root).")
    parser.add_argument("--time-limit-ms", type=float, default=DEFAULT_TIME_LIMIT_MS,
                        help="Soft per-puzzle time limit for the agent's deduction loop "
                             "(default: 60000; <= 0 disables).")
    parser.add_argument("--hard-timeout", type=float, default=DEFAULT_HARD_TIMEOUT_S,
                        help="Hard per-puzzle wall-clock limit in seconds; the worker "
                             "process is killed after it (default: 180).")
    parser.add_argument("--repeats", "-r", type=int, default=3,
                        help="Runs per puzzle; runtime_ms is the median (default: 3).")
    parser.add_argument("--no-isolation", action="store_true",
                        help="Run in-process (disables the hard timeout guard).")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    time_limit = args.time_limit_ms if args.time_limit_ms and args.time_limit_ms > 0 else None
    try:
        paths = discover_puzzles(args.puzzles, args.pattern)
    except FileNotFoundError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    print(f"Griductive benchmark: {len(paths)} puzzles | Python {platform.python_version()} "
          f"| soft limit {time_limit} ms | hard limit {args.hard_timeout} s | repeats {args.repeats}")
    records = run_benchmark(
        paths,
        time_limit_ms=time_limit,
        hard_timeout_s=None if args.no_isolation else args.hard_timeout,
        repeats=args.repeats,
        isolate=not args.no_isolation,
    )
    write_csv(records, args.output)
    solved = sum(r.status == "SOLVED" for r in records)
    print(f"Wrote {len(records)} rows to {args.output} "
          f"(SOLVED {solved}, other {len(records) - solved}).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
