"""Unit and integration tests for src/solve.py (C2: full deduction trace & uniqueness CLI)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

SRC_DIR = Path(__file__).resolve().parent.parent
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from agent import LogicAgent
from game_engine import GameEngine
from models import all_coords
from solve import format_result_text, main, solve_puzzle_file

PUZZLES_DIR = SRC_DIR / "puzzles"


@pytest.mark.parametrize("name", ["sample_3x3.json", "sample_4x4.json", "puzzle_5x5_01.json"])
def test_solve_puzzle_file_matches_agent_and_checks_uniqueness(name: str) -> None:
    path = PUZZLES_DIR / name
    result = solve_puzzle_file(path)

    assert result["uniqueness"] == "UNIQUE"
    assert result["status"] == "SOLVED"

    agent = LogicAgent()
    engine = GameEngine(path, agent=agent)
    report = agent.solve_puzzle(engine)

    assert result["metrics"]["steps_count"] == len(report.steps)
    assert result["metrics"]["sat_calls"] == report.sat_calls
    assert [s["step"] for s in result["trace"]] == list(range(1, len(report.steps) + 1))

    for exported, expected in zip(result["trace"], report.steps, strict=True):
        assert exported["step"] == expected.step
        assert exported["active_clue_ids"] == expected.active_clue_ids
        assert exported["sat_queries"] == expected.sat_queries
        assert exported["sat_calls"] == expected.sat_calls == len(exported["sat_queries"])
        assert exported["target_coord"] == expected.target_coord
        assert exported["verdict"] == expected.verdict
        assert exported["newly_revealed_clue_id"] == expected.newly_revealed_clue_id


def test_format_result_text_includes_all_required_trace_fields() -> None:
    result = solve_puzzle_file(PUZZLES_DIR / "sample_3x3.json")
    rendered = format_result_text(result)

    assert "Uniqueness check (full clue set): UNIQUE" in rendered
    assert "Step 1: A2 -> CRIMINAL" in rendered
    assert "Active clues (2): clue_A1, clue_B2" in rendered
    assert "KB_1 ^ ~C_A2: UNSAT" in rendered
    assert "Newly revealed clue: clue_A2" in rendered


def test_cli_single_puzzle_stdout_and_json_export(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    out_json = tmp_path / "trace_3x3.json"
    exit_code = main(["--puzzle", str(PUZZLES_DIR / "sample_3x3.json"), "--json", str(out_json)])
    assert exit_code == 0

    stdout = capsys.readouterr().out
    assert "Uniqueness check (full clue set): UNIQUE" in stdout
    assert "KB_1 ^ ~C_A2: UNSAT" in stdout
    assert out_json.is_file()

    payload = json.loads(out_json.read_text(encoding="utf-8"))
    assert payload["puzzle_id"] == "sample_3x3"
    assert payload["uniqueness"] == "UNIQUE"
    assert payload["status"] == "SOLVED"
    assert len(payload["trace"]) == 7
    assert payload["trace"][0]["step"] == 1
    assert payload["trace"][0]["active_clue_ids"] == ["clue_A1", "clue_B2"]
    assert "KB_1 ^ ~C_A2: UNSAT" in payload["trace"][0]["sat_queries"]


def test_cli_all_puzzles_quiet_json_and_skip_uniqueness(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    out_json = tmp_path / "all_traces.json"
    exit_code = main(["--all", "--quiet", "--skip-uniqueness", "--json", str(out_json)])
    assert exit_code == 0
    assert capsys.readouterr().out == ""

    payload = json.loads(out_json.read_text(encoding="utf-8"))
    assert "puzzles" in payload
    assert len(payload["puzzles"]) == len(list(PUZZLES_DIR.glob("*.json")))
    assert all(p["uniqueness"] is None for p in payload["puzzles"])
    assert all(p["status"] == "SOLVED" for p in payload["puzzles"])


def test_solve_puzzle_file_reports_multiple_uniqueness_and_unknown_status(tmp_path: Path) -> None:
    cells = []
    for coord in all_coords(2):
        cells.append(
            {
                "coord": coord,
                "row": int(coord[1]) - 1,
                "col": ord(coord[0]) - ord("A"),
                "name": coord,
                "occupation": "X",
                "hidden_status": "INNOCENT",
                "clue": {
                    "clue_id": f"clue_{coord}",
                    "type": "AT_LEAST",
                    "region": {"kind": "ROW", "target": 0},
                    "k": 0,
                },
            }
        )
    puzzle_path = tmp_path / "ambiguous_2x2.json"
    puzzle_path.write_text(
        json.dumps({"puzzle_id": "ambiguous_2x2", "size": 2, "initial_revealed": ["A1"], "cells": cells}),
        encoding="utf-8",
    )

    result = solve_puzzle_file(puzzle_path)
    assert result["uniqueness"] == "MULTIPLE"
    assert result["status"] == "UNKNOWN"
    assert result["trace"] == []


def test_solve_puzzle_file_missing_file_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        solve_puzzle_file(tmp_path / "does_not_exist.json")
