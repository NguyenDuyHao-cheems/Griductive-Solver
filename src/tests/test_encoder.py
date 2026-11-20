import json
import sys
from dataclasses import replace
from itertools import product
from pathlib import Path

import pytest

SRC_DIR = Path(__file__).resolve().parents[1]
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from encoder import build_var_map, encode_clues, encode_public_state, validate_clue
from game_engine import GameEngine, evaluate_clue
from models import (
    CharacterInfo,
    Clue,
    ClueType,
    CNFFormula,
    CompareOp,
    ParityKind,
    PublicState,
    Puzzle,
    Region,
    Status,
    all_coords,
)


@pytest.fixture(params=["sample_3x3", "sample_4x4"])
def sample_puzzle(request: pytest.FixtureRequest) -> Puzzle:
    puzzle_path = SRC_DIR / "puzzles" / f"{request.param}.json"
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


def _allows_assignment(formula: CNFFormula, assignment: dict[str, Status]) -> bool:
    """With all primaries fixed, unit clauses determine each auxiliary gate."""
    true_literals = {
        var_id if assignment[coord] == "CRIMINAL" else -var_id
        for coord, var_id in formula.var_map.items()
    }
    pending = formula.clauses
    while pending:
        remaining = []
        units: set[int] = set()
        for clause in pending:
            if any(literal in true_literals for literal in clause):
                continue
            unresolved = [literal for literal in clause if -literal not in true_literals]
            if not unresolved:
                return False
            if len(unresolved) == 1:
                units.add(unresolved[0])
            else:
                remaining.append(unresolved)
        if any(-literal in units for literal in units):
            return False
        assert units or not remaining, "Fixed primary variables should determine all gates."
        true_literals.update(units)
        pending = remaining
    assert len(true_literals) == formula.total_vars
    return True


def _assert_formula_stats(formula: CNFFormula, size: int) -> None:
    assert formula.num_primary_vars == len(formula.var_map) == size**2
    assert set(formula.var_map.values()) == set(range(1, size**2 + 1))
    assert formula.num_clauses == len(formula.clauses)
    variables = {abs(literal) for clause in formula.clauses for literal in clause}
    assert 0 not in variables
    auxiliary = variables.difference(formula.var_map.values())
    assert auxiliary == set(range(size**2 + 1, size**2 + formula.num_aux_vars + 1))


ROW = Region(kind="ROW", target=1)
COLUMN = Region(kind="COL", target="A")
NEIGHBORS = Region(kind="NEIGHBORS", target="B2")
SINGLE_CELL = Region(kind="EXPLICIT", cells=("A1",))


@pytest.mark.parametrize(
    "clue",
    [
        Clue("fact_criminal", "FACT", target="A1", status="CRIMINAL"),
        Clue("fact_innocent", "FACT", target="A1", status="INNOCENT"),
        Clue("same", "SAME", a="A1", b="B2"),
        Clue("same_self", "SAME", a="A1", b="A1"),
        Clue("different", "DIFFERENT", a="A1", b="B2"),
        Clue("different_self", "DIFFERENT", a="A1", b="A1"),
        Clue("exactly_none", "EXACTLY", region=ROW, k=0),
        Clue("exactly_all", "EXACTLY", region=ROW, k=3),
        Clue("exactly_interior", "EXACTLY", region=NEIGHBORS, k=4),
        Clue("at_least_none", "AT_LEAST", region=ROW, k=0),
        Clue("at_least_interior", "AT_LEAST", region=ROW, k=2),
        Clue("at_most_all", "AT_MOST", region=ROW, k=3),
        Clue("at_most_interior", "AT_MOST", region=ROW, k=1),
        Clue("parity_even", "PARITY", region=NEIGHBORS, parity="EVEN"),
        Clue("parity_odd", "PARITY", region=NEIGHBORS, parity="ODD"),
        Clue("parity_single", "PARITY", region=SINGLE_CELL, parity="EVEN"),
        Clue("count_gt", "COMPARE_COUNT", r1=ROW, op="GT", r2=COLUMN),
        Clue("count_lt", "COMPARE_COUNT", r1=ROW, op="LT", r2=COLUMN),
        Clue("count_equal", "COMPARE_COUNT", r1=ROW, op="EQ", r2=COLUMN),
        Clue("count_gt_unequal_regions", "COMPARE_COUNT", r1=SINGLE_CELL, op="GT", r2=ROW),
        Clue("count_lt_unequal_regions", "COMPARE_COUNT", r1=SINGLE_CELL, op="LT", r2=COLUMN),
        Clue("count_eq_unequal_regions", "COMPARE_COUNT", r1=COLUMN, op="EQ", r2=SINGLE_CELL),
    ],
    ids=lambda clue: clue.clue_id,
)
def test_cnf_matches_semantic_evaluator_for_every_3x3_assignment(clue: Clue) -> None:
    formula = encode_clues([clue], size=3)
    _assert_formula_stats(formula, size=3)
    for values in product(("INNOCENT", "CRIMINAL"), repeat=9):
        assignment = dict(zip(formula.var_map, values, strict=True))
        assert _allows_assignment(formula, assignment) == evaluate_clue(clue, assignment, 3)


def test_sample_cnf_matches_clues_and_public_knowledge_base(sample_puzzle: Puzzle) -> None:
    size = sample_puzzle.size
    state = GameEngine(sample_puzzle).get_public_state()
    formula = encode_public_state(state)
    revealed_formula = encode_clues(state.revealed_clues, size)
    all_clues = [cell.clue for cell in sample_puzzle.cells]
    full_formula = encode_clues(all_clues, size)
    units = [
        [formula.var_map[coord] if status == "CRIMINAL" else -formula.var_map[coord]]
        for coord, status in sorted(state.proved_verdicts.items())
    ]
    assert formula.clauses == revealed_formula.clauses + units
    assert formula.num_aux_vars == revealed_formula.num_aux_vars
    for candidate_formula in (formula, full_formula):
        _assert_formula_stats(candidate_formula, size)

    # Include the solution, each one-cell variation, and both extreme counts.
    solution = {cell.coord: cell.hidden_status for cell in sample_puzzle.cells}
    assignments = [solution]
    for coord, status in solution.items():
        assignments.append({**solution, coord: "CRIMINAL" if status == "INNOCENT" else "INNOCENT"})
    assignments.extend(dict.fromkeys(solution, status) for status in ("INNOCENT", "CRIMINAL"))

    for assignment in assignments:
        expected_full = all(evaluate_clue(clue, assignment, size) for clue in all_clues)
        expected_public = all(evaluate_clue(clue, assignment, size) for clue in state.revealed_clues)
        expected_public &= all(assignment[coord] == status for coord, status in state.proved_verdicts.items())
        assert _allows_assignment(full_formula, assignment) == expected_full
        assert _allows_assignment(formula, assignment) == expected_public

    for clue in all_clues:
        individual_formula = encode_clues([clue], size)
        for assignment in assignments:
            assert _allows_assignment(individual_formula, assignment) == evaluate_clue(clue, assignment, size)


def test_encoding_rebuilds_cnf_and_stats_from_current_state() -> None:
    characters = [CharacterInfo(coord, coord, "") for coord in all_coords(3)]
    initial = PublicState(size=3, characters=characters, proved_verdicts={"A1": "INNOCENT"})
    initial_formula = encode_public_state(initial)
    assert initial_formula.clauses == [[-1]]
    assert initial_formula.num_aux_vars == 0

    clue = Clue("revealed", "PARITY", region=ROW, parity="ODD")
    later = replace(initial, revealed_clues=[clue], proved_verdicts={"B1": "CRIMINAL", "A1": "INNOCENT"})
    later_formula = encode_public_state(later)
    _assert_formula_stats(later_formula, size=3)
    assert later_formula.num_aux_vars == 2
    assert later_formula.clauses[-2:] == [[-1], [2]]
    assert encode_public_state(initial) == initial_formula
    assert encode_public_state(later) == later_formula


def test_large_explicit_count_has_polynomial_clause_count() -> None:
    coords = all_coords(5)
    region = Region(kind="EXPLICIT", cells=tuple(coords))
    clue = Clue("large_count", "EXACTLY", region=region, k=12)
    formula = encode_clues([clue], size=5)
    _assert_formula_stats(formula, size=5)
    assert formula.num_clauses <= 4 * len(coords) * 13 + 2
    for count in (11, 12, 13):
        assignment = {
            coord: "CRIMINAL" if index < count else "INNOCENT"
            for index, coord in enumerate(coords)
        }
        assert _allows_assignment(formula, assignment) == evaluate_clue(clue, assignment, 5)


def test_encoder_reports_invalid_clue_before_adding_clauses() -> None:
    clue = Clue("invalid", "AT_LEAST", region=ROW, k=4)
    with pytest.raises(ValueError, match="^Clue 'invalid': k"):
        encode_clues([clue], size=3)
