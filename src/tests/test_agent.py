"""Tests for the Deductive Logic Agent (src/agent.py): entailment, uniqueness,
deduction loop + trace, and hint.

The reference oracle enumerates every board assignment and checks clues with
the Direct Semantic Evaluator (game_engine.evaluate_clue), which never touches
the CNF encoder, so agent results are cross-checked independently.
"""

import json
import random
import sys
from itertools import product
from pathlib import Path

import pytest

SRC_DIR = Path(__file__).resolve().parents[1]
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from agent import LogicAgent, SolveReport, _classify
from dpll import DPLLSolver
from game_engine import GameEngine, LogicAgentProtocol, evaluate_clue
from models import CharacterInfo, Clue, PublicState, Puzzle, Region, all_coords, resolve_region

PUZZLES = sorted((SRC_DIR / "puzzles").glob("*.json"))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_state(size, clues=(), verdicts=None):
    verdicts = dict(verdicts or {})
    coords = all_coords(size)
    return PublicState(
        size=size,
        characters=[CharacterInfo(c, f"P{c}", "X") for c in coords],
        proved_verdicts=verdicts,
        revealed_clues=list(clues),
        unsolved_coords=[c for c in coords if c not in verdicts],
    )


def brute_models(size, clues, verdicts=None):
    coords = all_coords(size)
    models = []
    for bits in product(("INNOCENT", "CRIMINAL"), repeat=len(coords)):
        assignment = dict(zip(coords, bits))
        if all(assignment[c] == s for c, s in (verdicts or {}).items()) and all(
            evaluate_clue(clue, assignment, size) for clue in clues
        ):
            models.append(assignment)
    return models


def expected_status(models, coord):
    if not models:
        return "INCONSISTENT"
    values = {m[coord] for m in models}
    return values.pop() if len(values) == 1 else "UNKNOWN"


def random_region(rng, size):
    coords = all_coords(size)
    kind = rng.choice(["ROW", "COL", "NEIGHBORS", "EXPLICIT"])
    if kind == "ROW":
        return Region("ROW", target=rng.randrange(size))
    if kind == "COL":
        return Region("COL", target=chr(ord("A") + rng.randrange(size)))
    if kind == "NEIGHBORS":
        return Region("NEIGHBORS", target=rng.choice(coords))
    return Region("EXPLICIT", cells=tuple(rng.sample(coords, rng.randint(1, len(coords)))))


def random_clue(rng, size, index):
    coords = all_coords(size)
    cid = f"c{index}"
    kind = rng.choice(["FACT", "SAME", "DIFFERENT", "EXACTLY", "AT_LEAST", "AT_MOST",
                       "PARITY", "COMPARE_COUNT"])
    if kind == "FACT":
        return Clue(cid, "FACT", target=rng.choice(coords),
                    status=rng.choice(["CRIMINAL", "INNOCENT"]))
    if kind in ("SAME", "DIFFERENT"):
        a, b = rng.sample(coords, 2)
        return Clue(cid, kind, a=a, b=b)
    if kind == "PARITY":
        return Clue(cid, kind, region=random_region(rng, size),
                    parity=rng.choice(["EVEN", "ODD"]))
    if kind == "COMPARE_COUNT":
        return Clue(cid, kind, r1=random_region(rng, size), op=rng.choice(["GT", "LT", "EQ"]),
                    r2=random_region(rng, size))
    region = random_region(rng, size)
    return Clue(cid, kind, region=region, k=rng.randint(0, len(resolve_region(region, size))))


def random_case(seed, size=3):
    rng = random.Random(seed)
    clues = [random_clue(rng, size, i) for i in range(rng.randint(1, 4))]
    revealed = rng.sample(all_coords(size), rng.randint(0, 2))
    verdicts = {c: rng.choice(["CRIMINAL", "INNOCENT"]) for c in revealed}
    return clues, verdicts


# ---------------------------------------------------------------------------
# Task 1: entailment classification
# ---------------------------------------------------------------------------

def test_agent_satisfies_engine_protocol():
    assert isinstance(LogicAgent(), LogicAgentProtocol)


def test_spec_section_3_4_example():
    # KB = (C_A ∨ C_B) ∧ (¬C_A ∨ C_B), A = 1, B = 2.
    solver = DPLLSolver([[1, 2], [-1, 2]])
    assert _classify(lambda lit: solver.solve([lit]).status == "UNSAT", 2) == "CRIMINAL"
    assert _classify(lambda lit: solver.solve([lit]).status == "UNSAT", 1) == "UNKNOWN"


def test_basic_statuses():
    agent = LogicAgent()
    state = make_state(3, [
        Clue("f", "FACT", target="A1", status="CRIMINAL"),
        Clue("d", "DIFFERENT", a="A1", b="B1"),
    ])
    assert agent.classify_cell(state, "A1") == "CRIMINAL"
    assert agent.classify_cell(state, "b1") == "INNOCENT"  # coordinate is canonicalised
    assert agent.classify_cell(state, "C3") == "UNKNOWN"


def test_inconsistent_kb():
    agent = LogicAgent()
    state = make_state(3, [Clue("f", "FACT", target="A1", status="CRIMINAL")],
                       verdicts={"A1": "INNOCENT"})
    assert agent.classify_cell(state, "B2") == "INCONSISTENT"
    assert set(agent.classify_all(state).values()) == {"INCONSISTENT"}


def test_classify_all_row_major_and_only_unsolved():
    state = make_state(3, [Clue("f", "FACT", target="C1", status="CRIMINAL")],
                       verdicts={"A1": "INNOCENT", "B2": "CRIMINAL"})
    result = LogicAgent().classify_all(state)
    assert list(result) == [c for c in all_coords(3) if c not in ("A1", "B2")]
    assert result["C1"] == "CRIMINAL"


def test_classification_does_not_mutate_state():
    clues = [Clue("e", "EXACTLY", region=Region("ROW", target=0), k=1)]
    state = make_state(3, clues, verdicts={"A1": "INNOCENT"})
    before = state.to_dict()
    LogicAgent().classify_all(state)
    assert state.to_dict() == before


@pytest.mark.parametrize("seed", range(60))
def test_classification_matches_semantic_oracle(seed):
    clues, verdicts = random_case(seed)
    state = make_state(3, clues, verdicts)
    models = brute_models(3, clues, verdicts)
    agent = LogicAgent()
    result = agent.classify_all(state)
    for coord in state.unsolved_coords:
        assert result[coord] == expected_status(models, coord), coord
        assert agent.classify_cell(state, coord) == result[coord]


# ---------------------------------------------------------------------------
# Task 2: uniqueness check
# ---------------------------------------------------------------------------

def test_uniqueness_three_outcomes():
    agent = LogicAgent()
    all_criminal = [Clue("a", "AT_LEAST", region=Region("EXPLICIT", cells=tuple(all_coords(2))), k=4)]
    assert agent.check_uniqueness(all_criminal, 2) == "UNIQUE"
    assert agent.check_uniqueness([Clue("f", "FACT", target="A1", status="CRIMINAL")], 2) == "MULTIPLE"
    assert agent.check_uniqueness([], 2) == "MULTIPLE"
    contradiction = [Clue("f", "FACT", target="A1", status="CRIMINAL"),
                     Clue("g", "FACT", target="A1", status="INNOCENT")]
    assert agent.check_uniqueness(contradiction, 2) == "UNSAT"


def test_uniqueness_ignores_auxiliary_variables():
    # Counting clues add many aux vars; exactly one board assignment exists.
    clues = [Clue("e", "EXACTLY", region=Region("ROW", target=r), k=0) for r in range(3)]
    clues.append(Clue("p", "PARITY", region=Region("COL", target="A"), parity="EVEN"))
    assert LogicAgent().check_uniqueness(clues, 3) == "UNIQUE"


@pytest.mark.parametrize("seed", range(60))
def test_uniqueness_matches_semantic_oracle(seed):
    rng = random.Random(1000 + seed)
    clues = [random_clue(rng, 3, i) for i in range(rng.randint(2, 7))]
    count = len(brute_models(3, clues))
    expected = "UNSAT" if count == 0 else "UNIQUE" if count == 1 else "MULTIPLE"
    assert LogicAgent().check_uniqueness(clues, 3) == expected


# ---------------------------------------------------------------------------
# Integration with GameEngine and sample puzzles
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("path", PUZZLES, ids=lambda p: p.stem)
def test_sample_puzzles_are_unique(path):

    puzzle = Puzzle.from_dict(json.loads(path.read_text(encoding="utf-8")))
    assert LogicAgent().check_uniqueness([cell.clue for cell in puzzle.cells], puzzle.size) == "UNIQUE"


@pytest.mark.parametrize("path", PUZZLES, ids=lambda p: p.stem)
def test_forced_verdicts_are_accepted_and_correct(path):
    agent = LogicAgent()
    engine = GameEngine(path, agent=agent)
    solution = engine.get_solution_for_testing()  # test-only ground truth
    for _ in range(engine.total_cells):
        statuses = agent.classify_all(engine.get_public_state())
        forced = [(c, s) for c, s in statuses.items() if s in ("CRIMINAL", "INNOCENT")]
        if not forced:
            break
        for coord, status in statuses.items():
            opposite = "INNOCENT" if status == "CRIMINAL" else "CRIMINAL"
            if status == "UNKNOWN":
                assert engine.submit_verdict(coord, "CRIMINAL").reason == "NOT_PROVABLE"
            elif status != "INCONSISTENT":
                assert status == solution[coord]  # soundness: a forced verdict is never wrong
                assert engine.submit_verdict(coord, opposite).reason == "CONTRADICTED"
        coord, status = forced[0]
        response = engine.submit_verdict(coord, status)
        assert response.accepted and response.reason == "ENTAILED"


# ---------------------------------------------------------------------------
# Tasks 3 & 4: no-guess deduction loop + trace
# ---------------------------------------------------------------------------

def tiny_puzzle(revealed_clue, revealed_status="INNOCENT"):
    """2x2 puzzle, A1 face-up with ``revealed_clue``; other clues are inert."""
    cells = []
    for coord in all_coords(2):
        clue = revealed_clue if coord == "A1" else {
            "clue_id": f"clue_{coord}", "type": "AT_MOST",
            "region": {"kind": "ROW", "target": 0}, "k": 2}
        cells.append({"coord": coord, "row": int(coord[1]) - 1, "col": ord(coord[0]) - 65,
                      "name": coord, "occupation": "X",
                      "hidden_status": revealed_status if coord == "A1" else "INNOCENT",
                      "clue": clue})
    return {"puzzle_id": "tiny", "size": 2, "initial_revealed": ["A1"], "cells": cells}


def first_forced(statuses):
    return next(((c, s) for c, s in statuses.items() if s != "UNKNOWN"), (None, None))


@pytest.mark.parametrize("path", PUZZLES, ids=lambda p: p.stem)
def test_solve_puzzle_solves_samples(path):
    agent = LogicAgent()
    engine = GameEngine(path, agent=agent)
    unsolved = engine.unsolved_count
    report = agent.solve_puzzle(engine)

    assert report.status == "SOLVED" and engine.is_solved()
    assert engine.get_proved_verdicts() == engine.get_solution_for_testing()
    assert [s.step for s in report.steps] == list(range(1, unsolved + 1))
    assert report.sat_calls == sum(s.sat_calls for s in report.steps)
    assert min(report.decisions, report.propagations, report.backtracks) >= 0
    assert report.runtime_ms > 0


@pytest.mark.parametrize("path", PUZZLES, ids=lambda p: p.stem)
def test_trace_replays_row_major_forced_choices(path):
    report = LogicAgent().solve_puzzle(GameEngine(path, agent=LogicAgent()))
    agent = LogicAgent()
    replay = GameEngine(path, agent=agent)
    for step in report.steps:
        state = replay.get_public_state()
        assert step.active_clue_ids == [c.clue_id for c in state.revealed_clues]
        assert (step.target_coord, step.verdict) == first_forced(agent.classify_all(state))
        assert step.sat_calls == len(step.sat_queries) and step.sat_calls % 2 == 0
        prefix = f"KB_{step.step} ^ "
        assert all(q.startswith(prefix) for q in step.sat_queries)
        # The last pair of queries proves the chosen verdict by refutation.
        refuted = "~" if step.verdict == "CRIMINAL" else ""
        assert f"{prefix}{refuted}C_{step.target_coord}: UNSAT" in step.sat_queries[-2:]
        hint = agent.hint(state)
        assert (hint.hint_coord, hint.verdict) == (step.target_coord, step.verdict)
        response = replay.submit_verdict(step.target_coord, step.verdict)
        assert response.revealed_clue.clue_id == step.newly_revealed_clue_id
    assert replay.is_solved()


@pytest.mark.parametrize("path", PUZZLES, ids=lambda p: p.stem)
def test_solve_puzzle_is_deterministic(path):
    def trace():
        return LogicAgent().solve_puzzle(GameEngine(path, agent=LogicAgent())).steps
    assert trace() == trace()


def test_solve_puzzle_stops_on_unknown_without_guessing():
    inert = {"clue_id": "clue_A1", "type": "AT_LEAST", "region": {"kind": "ROW", "target": 0}, "k": 0}
    agent = LogicAgent()
    engine = GameEngine(tiny_puzzle(inert), agent=agent)
    before = engine.get_public_state().to_dict()
    report = agent.solve_puzzle(engine)
    assert report.status == "UNKNOWN" and report.steps == []
    assert report.sat_calls == 2 * 3  # every unsolved cell was checked both ways
    assert engine.get_public_state().to_dict() == before


def test_solve_puzzle_stops_on_inconsistent_kb():
    lie = {"clue_id": "clue_A1", "type": "FACT", "target": "A1", "status": "CRIMINAL"}
    agent = LogicAgent()
    engine = GameEngine(tiny_puzzle(lie, revealed_status="INNOCENT"), agent=agent)
    report = agent.solve_puzzle(engine)
    assert report.status == "INCONSISTENT" and report.steps == []
    assert report.sat_calls == 2


def test_solve_puzzle_timeout_keeps_partial_report():
    engine = GameEngine(PUZZLES[-1], agent=LogicAgent())
    report = LogicAgent().solve_puzzle(engine, time_limit_ms=0)
    assert report.status == "TIMEOUT" and report.steps == []
    assert report.sat_calls == 1


def test_solve_puzzle_raises_if_engine_rejects_forced_verdict():
    class AlwaysUnknown:
        def classify_cell(self, public_state, coord):
            return "UNKNOWN"

    engine = GameEngine(PUZZLES[0], agent=AlwaysUnknown())
    with pytest.raises(RuntimeError, match="rejected"):
        LogicAgent().solve_puzzle(engine)


# ---------------------------------------------------------------------------
# Task 5: hint
# ---------------------------------------------------------------------------

def entails(state, clue_ids, coord, verdict):
    subset = [c for c in state.revealed_clues if c.clue_id in clue_ids]
    trimmed = PublicState(state.size, state.characters, state.proved_verdicts, subset,
                          state.unsolved_coords)
    return LogicAgent().classify_cell(trimmed, coord) == verdict


@pytest.mark.parametrize("path", PUZZLES, ids=lambda p: p.stem)
def test_hint_clues_are_sufficient_and_irreducible(path):
    agent = LogicAgent()
    engine = GameEngine(path, agent=agent)
    while not engine.is_solved():
        state = engine.get_public_state()
        before = state.to_dict()
        hint = agent.hint(state)
        assert state.to_dict() == before
        assert hint.hint_coord in state.unsolved_coords
        ids = hint.relevant_clue_ids
        revealed = [c.clue_id for c in state.revealed_clues]
        assert ids == [i for i in revealed if i in ids]  # subset, revealed order
        assert entails(state, ids, hint.hint_coord, hint.verdict)
        for dropped in ids:
            assert not entails(state, set(ids) - {dropped}, hint.hint_coord, hint.verdict)
        assert engine.submit_verdict(hint.hint_coord, hint.verdict).accepted


@pytest.mark.parametrize("seed", range(40))
def test_hint_matches_semantic_oracle(seed):
    clues, verdicts = random_case(seed)
    state = make_state(3, clues, verdicts)
    models = brute_models(3, clues, verdicts)
    hint = LogicAgent().hint(state)
    expected = {c: expected_status(models, c) for c in state.unsolved_coords}
    coord, status = first_forced(expected)
    if status in ("CRIMINAL", "INNOCENT"):
        assert (hint.hint_coord, hint.verdict) == (coord, status)
    else:
        assert hint.hint_coord is None and hint.verdict is None and hint.relevant_clue_ids == []


@pytest.mark.parametrize("path", PUZZLES[:4], ids=lambda p: p.stem)
def test_deduce_step_numbering_matches_solve_puzzle(path):
    """C3 regression: deduce_step must use 1-based step numbering identical to solve_puzzle."""
    agent = LogicAgent()
    full_report = agent.solve_puzzle(GameEngine(path, agent=agent))

    step_engine = GameEngine(path, agent=agent)
    step_trace = []
    while not step_engine.is_solved():
        step_num = len(step_trace) + 1
        step = agent.deduce_step(step_engine.get_public_state(), step_num=step_num)
        assert not isinstance(step, str)
        resp = step_engine.submit_verdict(step.target_coord, step.verdict)
        assert resp.accepted
        step_trace.append((
            step.step,
            step.active_clue_ids,
            step.sat_queries,
            step.sat_calls,
            step.target_coord,
            step.verdict,
            resp.revealed_clue.clue_id if resp.revealed_clue else None,
        ))

    expected = [
        (
            s.step,
            s.active_clue_ids,
            s.sat_queries,
            s.sat_calls,
            s.target_coord,
            s.verdict,
            s.newly_revealed_clue_id,
        )
        for s in full_report.steps
    ]
    assert step_trace == expected


def test_deduce_step_defaults_to_step_1_and_validates_step_num():
    agent = LogicAgent()
    engine = GameEngine(PUZZLES[0], agent=agent)
    first = agent.deduce_step(engine.get_public_state())
    assert not isinstance(first, str)
    assert first.step == 1
    assert all(q.startswith("KB_1 ^ ") for q in first.sat_queries)

    with pytest.raises(ValueError, match="step_num"):
        agent.deduce_step(engine.get_public_state(), step_num=0)
