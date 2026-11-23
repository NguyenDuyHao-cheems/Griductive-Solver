"""Tests for the benchmark runner (src/experiments/run_experiments.py, Bao task 5)."""

import csv
import json
import sys
from pathlib import Path

import pytest

SRC_DIR = Path(__file__).resolve().parents[1]
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from agent import LogicAgent
from encoder import encode_clues, encode_public_state
from experiments import run_experiments as rx
from experiments.plot_results import load_benchmark_csv
from game_engine import GameEngine

PUZZLE_DIR = SRC_DIR / "puzzles"
SAMPLE_3X3 = PUZZLE_DIR / "sample_3x3.json"

SIX_GROUP_COLUMNS = [
    "num_primary_vars", "num_aux_vars",            # 1
    "num_clauses",                                  # 2
    "sat_calls",                                    # 3
    "decisions", "propagations", "backtracks",      # 4
    "deduction_steps", "reveal_waves",              # 5
    "runtime_ms",                                   # 6
]


def test_measure_matches_agent_report():
    record = rx.measure_puzzle(SAMPLE_3X3, time_limit_ms=None, repeats=2)
    engine = GameEngine(SAMPLE_3X3, LogicAgent())
    report = LogicAgent().solve_puzzle(engine)

    assert record.status == "SOLVED" == report.status
    assert record.size == 3 and record.num_primary_vars == 9
    assert record.sat_calls == report.sat_calls
    assert record.decisions == report.decisions
    assert record.propagations == report.propagations
    assert record.backtracks == report.backtracks
    assert record.deduction_steps == len(report.steps)
    assert record.uniqueness == "UNIQUE"
    assert record.solution_verified is True
    assert record.repeats == 2
    assert record.runtime_ms_min <= record.runtime_ms <= record.runtime_ms_max
    assert record.notes == ""


def test_kb_sizes_are_consistent():
    record = rx.measure_puzzle(SAMPLE_3X3, time_limit_ms=None, repeats=1)
    puzzle = rx._load_puzzle(SAMPLE_3X3)
    engine = GameEngine(puzzle, LogicAgent())
    assert record.initial_clauses == encode_public_state(engine.get_public_state()).num_clauses
    assert record.full_kb_clauses == encode_clues([c.clue for c in puzzle.cells], 3).num_clauses
    # KB_t only grows, so the largest queried KB is at least KB_0.
    assert record.num_clauses >= record.initial_clauses
    assert record.num_aux_vars >= 0


def test_reveal_waves_bounded_by_steps():
    for path in rx.discover_puzzles(PUZZLE_DIR):
        record = rx.measure_puzzle(path, time_limit_ms=None, repeats=1)
        assert record.status == "SOLVED", record.notes
        assert 1 <= record.reveal_waves <= record.deduction_steps
        assert record.deduction_steps == record.size ** 2 - record.initial_revealed


def test_measurement_is_deterministic():
    a = rx.measure_puzzle(SAMPLE_3X3, time_limit_ms=None, repeats=1)
    b = rx.measure_puzzle(SAMPLE_3X3, time_limit_ms=None, repeats=1)
    keys = [c for c in SIX_GROUP_COLUMNS if c != "runtime_ms"] + ["num_clauses", "initial_clauses"]
    assert [getattr(a, k) for k in keys] == [getattr(b, k) for k in keys]


def test_soft_timeout_row_is_kept():
    record = rx.measure_puzzle(SAMPLE_3X3, time_limit_ms=0.0, repeats=3)
    assert record.status == "TIMEOUT"
    assert record.repeats == 1  # timed-out runs are not repeated
    assert record.runtime_ms is not None and record.sat_calls >= 1
    assert "soft timeout" in record.notes


def test_invalid_puzzle_becomes_failed_row(tmp_path):
    bad = tmp_path / "broken_3x3.json"
    bad.write_text(json.dumps({"puzzle_id": "broken_3x3", "size": 3,
                               "initial_revealed": [], "cells": []}), encoding="utf-8")
    record = rx.measure_puzzle(bad, time_limit_ms=None, repeats=1)
    assert record.status == "FAILED"
    assert record.puzzle_id == "broken_3x3" and record.size == 3
    assert "ValueError" in record.notes


def test_hard_timeout_kills_worker():
    record = rx.run_isolated(SAMPLE_3X3, time_limit_ms=None, repeats=1, hard_timeout_s=0.001)
    assert record.status == "TIMEOUT"
    assert "hard timeout" in record.notes
    assert record.size == 3


def test_isolated_run_returns_full_record():
    record = rx.run_isolated(SAMPLE_3X3, time_limit_ms=None, repeats=1, hard_timeout_s=120)
    assert record.status == "SOLVED"
    assert record.deduction_steps == 7


def test_csv_round_trip_with_plot_results(tmp_path):
    paths = [SAMPLE_3X3, PUZZLE_DIR / "sample_4x4.json"]
    records = rx.run_benchmark(paths, time_limit_ms=None, repeats=1, isolate=False, log=None)
    records.append(rx.measure_puzzle(SAMPLE_3X3, time_limit_ms=0.0, repeats=1))
    out = tmp_path / "benchmark_results.csv"
    rx.write_csv(records, out)

    with open(out, encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert list(rows[0].keys()) == rx.CSV_COLUMNS
    for column in SIX_GROUP_COLUMNS:
        assert rows[0][column] != ""

    parsed = load_benchmark_csv(out)
    assert [r.outcome_bucket for r in parsed] == ["SOLVED", "SOLVED", "TIMEOUT"]
    assert parsed[0].sat_calls == records[0].sat_calls
    assert parsed[1].reveal_waves == records[1].reveal_waves


def test_cli_writes_csv(tmp_path):
    out = tmp_path / "out.csv"
    code = rx.main(["--puzzles", str(PUZZLE_DIR), "--pattern", "sample_3x3.json",
                    "--output", str(out), "--repeats", "1", "--no-isolation"])
    assert code == 0
    assert len(load_benchmark_csv(out)) == 1


def test_cli_missing_puzzles(tmp_path):
    assert rx.main(["--puzzles", str(tmp_path), "--output", str(tmp_path / "x.csv")]) == 1
