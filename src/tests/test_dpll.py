"""Unit and integration tests for the pure-Python DPLL SAT solver (src/dpll.py).

A brute-force enumerator defined in this file serves as the reference oracle;
it is test-only code and never imported by runtime modules.
"""

import copy
import json
import random
import sys
from itertools import product
from pathlib import Path

import pytest

SRC_DIR = Path(__file__).resolve().parents[1]
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from dpll import DPLLSolver, SolverTimeout, solve, verify_assignment
from encoder import encode_clues, encode_public_state
from game_engine import GameEngine, evaluate_puzzle
from models import CNFFormula, Puzzle, SolverResult


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def brute_force_sat(clauses: list[list[int]], num_vars: int) -> bool:
    """Reference oracle: enumerate every assignment over 1..num_vars."""
    for bits in product((False, True), repeat=num_vars):
        assignment = {var: bits[var - 1] for var in range(1, num_vars + 1)}
        if verify_assignment(clauses, assignment):
            return True
    return False


def random_cnf(rng: random.Random, num_vars: int, num_clauses: int) -> list[list[int]]:
    clauses = []
    for _ in range(num_clauses):
        width = rng.randint(1, 3)
        clause = [rng.randint(1, num_vars) * rng.choice((1, -1)) for _ in range(width)]
        clauses.append(clause)
    return clauses


def load_puzzle(name: str) -> Puzzle:
    path = SRC_DIR / "puzzles" / f"{name}.json"
    return Puzzle.from_dict(json.loads(path.read_text(encoding="utf-8")))


def assert_metrics_valid(result: SolverResult) -> None:
    for name in ("decisions", "propagations", "backtracks"):
        value = getattr(result, name)
        assert isinstance(value, int) and value >= 0, name
    assert isinstance(result.runtime_ms, float) and result.runtime_ms >= 0.0


def pigeonhole(holes: int) -> tuple[list[list[int]], int]:
    """PHP(holes+1, holes): classic small UNSAT instance requiring search."""
    pigeons = holes + 1

    def var(p: int, h: int) -> int:
        return p * holes + h + 1

    clauses = [[var(p, h) for h in range(holes)] for p in range(pigeons)]
    for h in range(holes):
        for p1 in range(pigeons):
            for p2 in range(p1 + 1, pigeons):
                clauses.append([-var(p1, h), -var(p2, h)])
    return clauses, pigeons * holes


# ---------------------------------------------------------------------------
# Task 1 — Core DPLL
# ---------------------------------------------------------------------------

def test_simple_sat_returns_complete_satisfying_assignment() -> None:
    clauses = [[1, 2], [-1, 3], [-2, -3]]
    result = solve(clauses)
    assert result.status == "SAT"
    assert result.assignment is not None
    assert set(result.assignment) == {1, 2, 3}
    assert verify_assignment(clauses, result.assignment)
    assert_metrics_valid(result)


def test_simple_unsat() -> None:
    result = solve([[1, 2], [1, -2], [-1, 2], [-1, -2]])
    assert result.status == "UNSAT"
    assert result.assignment is None
    assert result.backtracks > 0
    assert_metrics_valid(result)


def test_empty_formula_is_sat() -> None:
    result = solve([])
    assert result.status == "SAT"
    assert result.assignment == {}
    assert (result.decisions, result.propagations, result.backtracks) == (0, 0, 0)


def test_empty_clause_is_unsat_without_search() -> None:
    result = solve([[1, 2], []])
    assert result.status == "UNSAT"
    assert result.decisions == 0


def test_unit_chain_is_solved_by_propagation_only() -> None:
    # x1, x1->x2, x2->x3, ..., x9->x10
    clauses = [[1]] + [[-i, i + 1] for i in range(1, 10)]
    result = solve(clauses)
    assert result.status == "SAT"
    assert result.assignment == {i: True for i in range(1, 11)}
    assert result.decisions == 0
    assert result.backtracks == 0
    assert result.propagations == 10


def test_early_conflict_from_contradictory_units() -> None:
    result = solve([[1], [-1], [2, 3]])
    assert result.status == "UNSAT"
    assert result.decisions == 0
    assert result.backtracks == 0


def test_conflict_detected_through_propagation_chain() -> None:
    # x1 forces x2, x2 forces x3, x3 forces ~x1  -> conflict at level 0
    result = solve([[1], [-1, 2], [-2, 3], [-3, -1]])
    assert result.status == "UNSAT"
    assert result.decisions == 0


def test_spec_example_section_3_4() -> None:
    """KB = (C_A ∨ C_B) ∧ (¬C_A ∨ C_B): B is CRIMINAL, A is UNKNOWN."""
    solver = DPLLSolver([[1, 2], [-1, 2]])
    assert solver.solve().status == "SAT"
    assert solver.solve([-2]).status == "UNSAT"  # KB ∧ ¬C_B -> KB ⊨ C_B
    assert solver.solve([2]).status == "SAT"
    assert solver.solve([1]).status == "SAT"
    assert solver.solve([-1]).status == "SAT"  # A undetermined


def test_tautologies_and_duplicate_literals_are_handled() -> None:
    clauses = [[1, -1], [2, 2, 2], [-2, 3, 3]]
    result = solve(clauses)
    assert result.status == "SAT"
    assert result.assignment is not None
    assert result.assignment[2] is True and result.assignment[3] is True
    assert set(result.assignment) == {1, 2, 3}


def test_pigeonhole_unsat_requires_backtracking() -> None:
    clauses, num_vars = pigeonhole(3)
    result = solve(clauses, num_vars=num_vars)
    assert result.status == "UNSAT"
    assert result.decisions > 0
    assert result.backtracks > 0
    assert_metrics_valid(result)


def test_declared_variables_are_included_in_assignment() -> None:
    formula = CNFFormula(num_primary_vars=4, num_aux_vars=2, var_map={}, clauses=[[1, -2]])
    result = solve(formula)
    assert result.status == "SAT"
    assert result.assignment is not None
    assert set(result.assignment) == set(range(1, 7))
    assert verify_assignment(formula.clauses, result.assignment)


def test_deterministic_variable_selection_lowest_id_true_first() -> None:
    # No units: the first decision must be x1 = True, which satisfies everything.
    result = solve([[1, 2], [1, 3], [2, 3]])
    assert result.status == "SAT"
    assert result.assignment is not None
    assert result.assignment[1] is True
    assert result.decisions >= 1


@pytest.mark.parametrize("seed", range(5))
def test_results_are_deterministic_across_runs(seed: int) -> None:
    rng = random.Random(seed)
    clauses = random_cnf(rng, num_vars=12, num_clauses=40)
    runs = [solve(clauses) for _ in range(5)]
    first = runs[0]
    for other in runs[1:]:
        assert other.status == first.status
        assert other.assignment == first.assignment
        assert (other.decisions, other.propagations, other.backtracks) == (
            first.decisions,
            first.propagations,
            first.backtracks,
        )


@pytest.mark.parametrize("seed", range(200))
def test_matches_brute_force_oracle_on_random_cnf(seed: int) -> None:
    rng = random.Random(1000 + seed)
    num_vars = rng.randint(1, 8)
    clauses = random_cnf(rng, num_vars, rng.randint(1, 4 * num_vars))
    result = solve(clauses, num_vars=num_vars)
    expected = brute_force_sat(clauses, num_vars)
    assert (result.status == "SAT") == expected
    if expected:
        assert result.assignment is not None
        assert set(result.assignment) == set(range(1, num_vars + 1))
        assert verify_assignment(clauses, result.assignment)
    else:
        assert result.assignment is None
    assert_metrics_valid(result)


@pytest.mark.parametrize("bad", [[[0]], [[1, "2"]], [[True]], [[1.5]]])
def test_invalid_literals_are_rejected(bad: list) -> None:
    with pytest.raises(ValueError):
        solve(bad)


# ---------------------------------------------------------------------------
# Task 2 — Assumptions / temporary unit clauses
# ---------------------------------------------------------------------------

def test_assumptions_do_not_mutate_formula() -> None:
    formula = CNFFormula(
        num_primary_vars=3,
        num_aux_vars=0,
        var_map={"A1": 1, "B1": 2, "C1": 3},
        clauses=[[1, 2], [-1, 3]],
    )
    snapshot = copy.deepcopy(formula)
    solver = DPLLSolver(formula)
    solver.solve([-2])
    solver.solve([1, -3])
    solve(formula, [2, -1])
    assert formula == snapshot


def test_assumption_equivalent_to_temporary_unit_clause() -> None:
    clauses = [[1, 2, 3], [-1, -2], [-2, -3], [2, 4], [-4, 5]]
    for literal in (1, -1, 2, -2, 3, -3, 4, -4, 5, -5):
        with_assumption = solve(clauses, [literal])
        with_unit = solve(clauses + [[literal]])
        assert with_assumption.status == with_unit.status
        assert with_assumption.assignment == with_unit.assignment
        assert (
            with_assumption.decisions,
            with_assumption.propagations,
            with_assumption.backtracks,
        ) == (with_unit.decisions, with_unit.propagations, with_unit.backtracks)


def test_consecutive_queries_are_independent() -> None:
    clauses, num_vars = pigeonhole(3)
    clauses = clauses[1:]  # drop pigeon 0's clause -> SAT (pigeon 0 may sit nowhere)
    solver = DPLLSolver(clauses, num_vars=num_vars)
    baseline = solver.solve()
    queries = [[1], [-1], [2, 6], [-5], [1, 5], []]
    first_pass = [solver.solve(q) for q in queries]
    second_pass = [solver.solve(q) for q in reversed(queries)][::-1]
    for a, b in zip(first_pass, second_pass):
        assert a.status == b.status
        assert a.assignment == b.assignment
        assert (a.decisions, a.propagations, a.backtracks) == (
            b.decisions,
            b.propagations,
            b.backtracks,
        )
    again = solver.solve()
    assert again.assignment == baseline.assignment
    assert again.decisions == baseline.decisions


def test_conflicting_assumptions_are_unsat() -> None:
    solver = DPLLSolver([[1, 2]])
    result = solver.solve([1, -1])
    assert result.status == "UNSAT"
    assert result.decisions == 0
    assert solver.solve().status == "SAT"


def test_assumption_on_variable_outside_formula() -> None:
    result = solve([[1, 2]], [-4])
    assert result.status == "SAT"
    assert result.assignment is not None
    assert result.assignment[4] is False
    assert set(result.assignment) == {1, 2, 3, 4}


def test_assumption_forcing_conflict_via_propagation() -> None:
    solver = DPLLSolver([[-1, 2], [-2, 3], [-3, -1]])
    assert solver.solve([1]).status == "UNSAT"
    result = solver.solve([-1])
    assert result.status == "SAT"
    assert result.assignment is not None and result.assignment[1] is False


@pytest.mark.parametrize("bad", [[0], ["1"], [None]])
def test_invalid_assumptions_are_rejected(bad: list) -> None:
    with pytest.raises(ValueError):
        DPLLSolver([[1]]).solve(bad)


# ---------------------------------------------------------------------------
# Task 3 — Metrics logging
# ---------------------------------------------------------------------------

def test_metrics_count_decisions_and_backtracks_exactly() -> None:
    # Decision 1: x1=T -> propagate x2=T, x3=T (2 props) -> conflict on (-2 ∨ -3).
    # Backtrack 1. Decision 2: x1=F -> propagate x4=T (1 prop).
    # Decision 3: x2=T (lowest unassigned) -> propagate x3=F (1 prop). SAT.
    clauses = [[-1, 2], [-1, 3], [-2, -3], [1, 4]]
    result = solve(clauses)
    assert result.status == "SAT"
    assert (result.decisions, result.propagations, result.backtracks) == (3, 4, 1)
    assert result.assignment == {1: False, 2: True, 3: False, 4: True}


def test_metrics_counted_per_call_not_accumulated() -> None:
    clauses, num_vars = pigeonhole(3)
    solver = DPLLSolver(clauses, num_vars=num_vars)
    first = solver.solve()
    second = solver.solve()
    assert (first.decisions, first.propagations, first.backtracks) == (
        second.decisions,
        second.propagations,
        second.backtracks,
    )


def test_runtime_measured_with_perf_counter(monkeypatch: pytest.MonkeyPatch) -> None:
    import dpll

    ticks = iter([10.0, 10.25])
    monkeypatch.setattr(dpll, "perf_counter", lambda: next(ticks))
    result = solve([[1]])
    assert result.runtime_ms == pytest.approx(250.0)


def test_time_limit_raises_with_partial_metrics() -> None:
    clauses, num_vars = pigeonhole(7)
    with pytest.raises(SolverTimeout) as info:
        solve(clauses, num_vars=num_vars, time_limit_ms=0.0)
    partial = info.value.partial
    assert isinstance(partial, SolverResult)
    assert partial.status == "TIMEOUT"  # interrupted search is neither SAT nor UNSAT
    assert partial.assignment is None
    assert_metrics_valid(partial)


def test_negative_time_limit_rejected() -> None:
    with pytest.raises(ValueError):
        solve([[1]], time_limit_ms=-1)


# ---------------------------------------------------------------------------
# Integration with encoder / game engine (sample puzzles)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("name", ["sample_3x3", "sample_4x4"])
def test_full_clue_set_solution_matches_semantic_evaluator(name: str) -> None:
    puzzle = load_puzzle(name)
    formula = encode_clues([cell.clue for cell in puzzle.cells], puzzle.size)
    result = solve(formula)
    assert result.status == "SAT"
    assert result.assignment is not None
    assert verify_assignment(formula.clauses, result.assignment)

    statuses = {
        coord: "CRIMINAL" if result.assignment[var] else "INNOCENT"
        for coord, var in formula.var_map.items()
    }
    assert evaluate_puzzle(puzzle, statuses)  # independent of the CNF encoder


@pytest.mark.parametrize("name", ["sample_3x3", "sample_4x4"])
def test_full_clue_set_has_unique_model_via_blocking_clause(name: str) -> None:
    puzzle = load_puzzle(name)
    formula = encode_clues([cell.clue for cell in puzzle.cells], puzzle.size)
    first = solve(formula)
    assert first.status == "SAT" and first.assignment is not None
    blocking = [-var if first.assignment[var] else var for var in formula.var_map.values()]
    second = solve(formula.clauses + [blocking], num_vars=formula.total_vars)
    assert second.status == "UNSAT"
    hidden = {cell.coord: cell.hidden_status for cell in puzzle.cells}
    for coord, var in formula.var_map.items():
        assert first.assignment[var] == (hidden[coord] == "CRIMINAL")


@pytest.mark.parametrize("name", ["sample_3x3", "sample_4x4"])
def test_entailment_queries_on_initial_public_state(name: str) -> None:
    """Forced verdicts from KB_t ∧ ¬C_i / KB_t ∧ C_i never contradict the hidden solution."""
    puzzle = load_puzzle(name)
    engine = GameEngine()
    engine.load_puzzle(puzzle)
    state = engine.get_public_state()
    formula = encode_public_state(state)
    solver = DPLLSolver(formula)

    assert solver.solve().status == "SAT"
    snapshot = copy.deepcopy(formula)
    for coord, var in formula.var_map.items():
        neg = solver.solve([-var]).status
        pos = solver.solve([var]).status
        assert not (neg == "UNSAT" and pos == "UNSAT")
        if neg == "UNSAT":
            assert next(c.hidden_status for c in puzzle.cells if c.coord == coord) == "CRIMINAL"
        if pos == "UNSAT":
            assert next(c.hidden_status for c in puzzle.cells if c.coord == coord) == "INNOCENT"
    assert formula == snapshot
