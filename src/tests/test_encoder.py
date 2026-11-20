import json
from pathlib import Path

import pytest

from src.encoder import build_var_map, validate_clue
from src.models import (
    CharacterInfo,
    Clue,
    ClueType,
    CompareOp,
    ParityKind,
    PublicState,
    Puzzle,
    Region,
)


@pytest.fixture(params=["sample_3x3", "sample_4x4"])
def sample_puzzle(request: pytest.FixtureRequest) -> Puzzle:
    puzzle_path = Path(__file__).resolve().parents[1] / "puzzles" / f"{request.param}.json"
    return Puzzle.from_dict(json.loads(puzzle_path.read_text(encoding="utf-8")))


def test_variable_map_is_row_major_and_reversible(sample_puzzle: Puzzle) -> None:
    characters = [cell.to_public_character() for cell in sample_puzzle.cells]
    state = PublicState(size=sample_puzzle.size, characters=characters)
    var_map, coord_by_var = build_var_map(state)

    assert var_map["A1"] == 1
    assert var_map["B1"] == 2
    assert var_map["A2"] == state.size + 1
    assert list(var_map.values()) == list(range(1, state.size**2 + 1))
    assert [coord_by_var[var_id] for var_id in var_map.values()] == list(var_map)

    state.characters.reverse()
    assert build_var_map(state) == (var_map, coord_by_var)


@pytest.mark.parametrize(
    "coords", [("A1",), ("A1", "B1", "A2", "A2"), ("A1", "B1", "A2", "C2")]
)
def test_variable_map_rejects_invalid_character_coordinates(coords: tuple[str, ...]) -> None:
    state = PublicState(size=2, characters=[CharacterInfo(coord, coord, "") for coord in coords])
    with pytest.raises(ValueError, match="one character per grid cell"):
        build_var_map(state)


def test_sample_clues_pass_validation(sample_puzzle: Puzzle) -> None:
    for cell in sample_puzzle.cells:
        assert validate_clue(cell.clue, sample_puzzle.size) is True


@pytest.mark.parametrize("clue_type", ["EXACTLY", "AT_LEAST", "AT_MOST"])
@pytest.mark.parametrize("k", [0, 3])
def test_counting_clues_accept_bounds(clue_type: ClueType, k: int) -> None:
    region = Region(kind="NEIGHBORS", target="A1")
    clue = Clue(clue_id="count", type=clue_type, region=region, k=k)
    assert validate_clue(clue, size=3) is True


@pytest.mark.parametrize("parity", ["EVEN", "ODD"])
def test_parity_accepts_supported_values(parity: ParityKind) -> None:
    region = Region(kind="EXPLICIT", cells=("A1", "B2"))
    clue = Clue(clue_id="parity", type="PARITY", region=region, parity=parity)
    assert validate_clue(clue, size=3) is True


@pytest.mark.parametrize("op", ["GT", "LT", "EQ"])
def test_compare_count_accepts_supported_operators(op: CompareOp) -> None:
    r1 = Region(kind="ROW", target=0)
    r2 = Region(kind="COL", target="B")
    clue = Clue(clue_id="compare", type="COMPARE_COUNT", r1=r1, op=op, r2=r2)
    assert validate_clue(clue, size=3) is True


@pytest.mark.parametrize(
    ("fields", "message"),
    [
        ({"type": "UNKNOWN"}, "unsupported clue type"),
        ({"type": "FACT", "status": "CRIMINAL"}, "target"),
        ({"type": "FACT", "target": "D1", "status": "CRIMINAL"}, "target:.*out of bounds"),
        ({"type": "FACT", "target": "A1", "status": "UNKNOWN"}, "status"),
        ({"type": "SAME", "a": "A1"}, "b"),
        ({"type": "DIFFERENT", "a": "A0", "b": "B1"}, "a:.*out of bounds"),
        ({"type": "EXACTLY", "k": 0}, "region"),
        (
            {"type": "EXACTLY", "region": {"kind": "ROW", "target": 3}, "k": 0},
            "region:.*out of bounds",
        ),
        (
            {"type": "PARITY", "region": {"kind": "COL", "target": "D"}, "parity": "EVEN"},
            "region:.*out of bounds",
        ),
        (
            {"type": "PARITY", "region": {"kind": "NEIGHBORS", "target": "C4"}, "parity": "EVEN"},
            "region:.*out of bounds",
        ),
        (
            {"type": "PARITY", "region": {"kind": "EXPLICIT", "cells": []}, "parity": "EVEN"},
            "region:.*at least one cell",
        ),
        (
            {
                "type": "PARITY",
                "region": {"kind": "EXPLICIT", "cells": ["A1", "A1"]},
                "parity": "EVEN",
            },
            "region:.*Duplicate cell",
        ),
        ({"type": "PARITY", "region": {"kind": "ROW", "target": 0}, "parity": "BOTH"}, "parity"),
        ({"type": "COMPARE_COUNT", "op": "EQ", "r2": {"kind": "COL", "target": "A"}}, "r1"),
        ({"type": "COMPARE_COUNT", "op": "EQ", "r1": {"kind": "COL", "target": "A"}}, "r2"),
        (
            {
                "type": "COMPARE_COUNT",
                "op": "GE",
                "r1": {"kind": "ROW", "target": 0},
                "r2": {"kind": "COL", "target": "A"},
            },
            "op",
        ),
    ],
)
def test_invalid_clues_identify_the_clue_and_field(fields: dict[str, object], message: str) -> None:
    clue = Clue.from_dict({"clue_id": "invalid", **fields})
    with pytest.raises(ValueError, match=rf"^Clue 'invalid': {message}"):
        validate_clue(clue, size=3)


@pytest.mark.parametrize("k", [-1, 4, 1.0, True, None])
def test_counting_clues_reject_invalid_counts(k: object) -> None:
    clue = Clue.from_dict(
        {"clue_id": "count", "type": "EXACTLY", "region": {"kind": "ROW", "target": 0}, "k": k}
    )
    with pytest.raises(ValueError, match="^Clue 'count': k must be an integer from 0 to 3"):
        validate_clue(clue, size=3)


def test_validation_rejects_empty_resolved_region() -> None:
    region = Region(kind="NEIGHBORS", target="A1")
    clue = Clue(clue_id="count", type="EXACTLY", region=region, k=0)
    with pytest.raises(ValueError, match="^Clue 'count': region must contain at least one cell"):
        validate_clue(clue, size=1)
