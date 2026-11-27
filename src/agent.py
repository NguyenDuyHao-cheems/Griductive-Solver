"""Deductive Logic Agent for Griductive (Section 4.4).

Reasons only over ``PublicState`` (revealed clues + proved verdicts). It never
sees hidden statuses or unrevealed clues.

Entailment classification (Section 3.4), for an unresolved character i:

- KB_t ⊨ C_i   ⇔  KB_t ∧ ¬C_i is UNSAT  -> CRIMINAL
- KB_t ⊨ ¬C_i  ⇔  KB_t ∧ C_i  is UNSAT  -> INNOCENT
- both SAT                              -> UNKNOWN
- both UNSAT                            -> INCONSISTENT

Since KB_t ≡ (KB_t ∧ C_i) ∨ (KB_t ∧ ¬C_i), "both queries UNSAT" is exactly
"KB_t is UNSAT", so two SAT calls per cell are enough to detect INCONSISTENT.

No-guess deduction loop: at step t, scan unsolved cells in row-major order,
submit the first forced verdict to the GameEngine, receive the revealed clue
(KB_{t+1}) and repeat until solved or no verdict is forced.

Uniqueness check: solve the full clue set, block the primary part of the
model found, solve again (UNSAT / UNIQUE / MULTIPLE).
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass, field, replace
from time import perf_counter
from typing import Literal

if __package__:
    from .dpll import DPLLSolver, SolverTimeout
    from .encoder import encode_clues, encode_public_state
    from .models import (
        Clue, DeductionStep, EntailmentStatus, HintResponse, PublicState,
        SolverResult, Status, UniquenessStatus, all_coords, coord_to_rc, rc_to_coord,
    )
else:
    from dpll import DPLLSolver, SolverTimeout
    from encoder import encode_clues, encode_public_state
    from models import (
        Clue, DeductionStep, EntailmentStatus, HintResponse, PublicState,
        SolverResult, Status, UniquenessStatus, all_coords, coord_to_rc, rc_to_coord,
    )

SolveStatus = Literal["SOLVED", "UNKNOWN", "INCONSISTENT", "TIMEOUT"]

# record(coord, assumed_literal, result) is called after every SAT query.
_Recorder = Callable[[str, int, SolverResult], None]


@dataclass
class SolveReport:
    """Outcome of :meth:`LogicAgent.solve_puzzle`: terminal status, trace, metrics.

    Metrics cover the agent's own deduction queries (not the GameEngine's
    re-verification inside ``submit_verdict``), including queries of the final
    scan that found no forced verdict.
    """

    status: SolveStatus
    steps: list[DeductionStep] = field(default_factory=list)
    sat_calls: int = 0
    decisions: int = 0
    propagations: int = 0
    backtracks: int = 0
    runtime_ms: float = 0.0

    def _add(self, result: SolverResult) -> None:
        self.sat_calls += 1
        self.decisions += result.decisions
        self.propagations += result.propagations
        self.backtracks += result.backtracks


class LogicAgent:
    """No-guess agent backed by the from-scratch CNF encoder and DPLL solver.

    Implements ``game_engine.LogicAgentProtocol`` via :meth:`classify_cell`.
    """

    # -- Task 1: entailment classification ---------------------------------

    def classify_cell(self, public_state: PublicState, coord: str) -> EntailmentStatus:
        """Classify one cell as CRIMINAL / INNOCENT / UNKNOWN / INCONSISTENT."""
        size = public_state.size
        canonical = rc_to_coord(*coord_to_rc(coord, size), size)
        formula = encode_public_state(public_state)
        solver = DPLLSolver(formula)
        return _classify(lambda lit: solver.solve([lit]).status == "UNSAT", formula.var_map[canonical])

    def classify_all(self, public_state: PublicState) -> dict[str, EntailmentStatus]:
        """Classify every unsolved cell, in deterministic row-major order.

        KB_t is encoded once and the same solver answers every query.
        """
        formula = encode_public_state(public_state)
        solver = DPLLSolver(formula)
        unsolved = set(public_state.unsolved_coords)
        return {
            coord: _classify(lambda lit: solver.solve([lit]).status == "UNSAT", formula.var_map[coord])
            for coord in all_coords(public_state.size)
            if coord in unsolved
        }

    # -- Task 2: uniqueness check ------------------------------------------

    def check_uniqueness(self, clues: Iterable[Clue], size: int) -> UniquenessStatus:
        """Return UNIQUE / MULTIPLE / UNSAT for the models of a full clue set.

        Only primary variables C_i count: two models differing only in
        auxiliary variables are the same board assignment.
        """
        formula = encode_clues(clues, size)
        first = DPLLSolver(formula).solve()
        if first.status == "UNSAT":
            return "UNSAT"

        primary = range(1, formula.num_primary_vars + 1)
        blocking = [-var if first.assignment[var] else var for var in primary]
        second = DPLLSolver([*formula.clauses, blocking], num_vars=formula.total_vars).solve()
        return "UNIQUE" if second.status == "UNSAT" else "MULTIPLE"

    # -- Tasks 3 & 4: no-guess deduction loop with trace --------------------

    def solve_puzzle(self, engine, *, time_limit_ms: float | None = None) -> SolveReport:
        """Auto Solve: play forced verdicts on ``engine`` until a terminal state.

        Uses only ``engine.get_public_state()`` and ``engine.submit_verdict()``;
        the engine must have a Logic Agent attached to verify verdicts.
        Terminal status: SOLVED, UNKNOWN (nothing forced, never guesses),
        INCONSISTENT (KB_t unsatisfiable) or TIMEOUT (``time_limit_ms`` over
        the whole run; the partial trace and metrics are kept).
        """
        start = perf_counter()
        deadline = None if time_limit_ms is None else start + time_limit_ms / 1000.0
        report = SolveReport(status="UNKNOWN")
        try:
            while True:
                state = engine.get_public_state()
                step_num = len(report.steps) + 1
                status, step_obj = _deduce_one_step(
                    state,
                    step_num=step_num,
                    on_result=report._add,
                    deadline=deadline,
                )
                if status == "SOLVED":
                    report.status = "SOLVED"
                    break
                if step_obj is None:
                    report.status = status
                    break

                response = engine.submit_verdict(step_obj.target_coord, step_obj.verdict)
                if not response.accepted:
                    raise RuntimeError(
                        f"GameEngine rejected entailed verdict {step_obj.verdict} "
                        f"for {step_obj.target_coord}: {response.reason}."
                    )
                report.steps.append(
                    replace(
                        step_obj,
                        newly_revealed_clue_id=(
                            response.revealed_clue.clue_id if response.revealed_clue else None
                        ),
                    )
                )
        except SolverTimeout as timeout:
            report._add(timeout.partial)
            report.status = "TIMEOUT"
        report.runtime_ms = (perf_counter() - start) * 1000.0
        return report

    def deduce_step(
        self,
        public_state: PublicState,
        *,
        step_num: int = 1,
    ) -> DeductionStep | str:
        """Perform a single forced deduction step on ``public_state`` without guessing.

        Uses the same single-step deduction core and 1-based ``step_num`` /
        ``KB_{step_num}`` labeling as :meth:`solve_puzzle`.

        Returns:
            - ``DeductionStep`` if a cell's verdict is logically forced.
            - ``"SOLVED"`` if all cells are already resolved.
            - ``"INCONSISTENT"`` if KB_t is unsatisfiable.
            - ``"UNKNOWN"`` if no unresolved cell has a forced verdict.
        """
        if step_num < 1:
            raise ValueError(f"step_num must be >= 1, got {step_num}.")

        status, step_obj = _deduce_one_step(public_state, step_num=step_num)
        if step_obj is None:
            return status
        return step_obj

    # -- Task 5: hint --------------------------------------------------------

    def hint(self, public_state: PublicState) -> HintResponse:
        """Return the first forced cell (row-major) and the clues that prove it.

        ``relevant_clue_ids`` is an irreducible subset of revealed clues that,
        together with the proved verdicts, still entails the hinted verdict:
        each clue is dropped in turn (deterministic, revealed order) whenever
        the verdict stays entailed without it. Empty hint if nothing is forced
        or KB_t is inconsistent.
        """
        status, coord = _first_forced(public_state)
        if status not in ("CRIMINAL", "INNOCENT"):
            return HintResponse()

        kept = list(public_state.revealed_clues)
        for clue in public_state.revealed_clues:
            trial = [c for c in kept if c is not clue]
            formula = encode_public_state(replace(public_state, revealed_clues=trial))
            var = formula.var_map[coord]
            if DPLLSolver(formula).solve([-var if status == "CRIMINAL" else var]).status == "UNSAT":
                kept = trial
        return HintResponse(hint_coord=coord, verdict=status,
                            relevant_clue_ids=[clue.clue_id for clue in kept])


def _deduce_one_step(
    state: PublicState,
    *,
    step_num: int,
    on_result: Callable[[SolverResult], None] | None = None,
    deadline: float | None = None,
) -> tuple[Literal["SOLVED", "UNKNOWN", "INCONSISTENT", "CRIMINAL", "INNOCENT"], DeductionStep | None]:
    """Run one deterministic no-guess deduction scan on ``state``.

    Shared by both :meth:`LogicAgent.solve_puzzle` and :meth:`LogicAgent.deduce_step`
    so step numbers and ``KB_{step_num}`` SAT query labels are always identical.
    """
    if not state.unsolved_coords:
        return "SOLVED", None

    queries: list[str] = []

    def record(coord: str, literal: int, result: SolverResult) -> None:
        if on_result is not None:
            on_result(result)
        sign = "~" if literal < 0 else ""
        queries.append(f"KB_{step_num} ^ {sign}C_{coord}: {result.status}")

    status, coord = _first_forced(state, record, deadline)
    if status not in ("CRIMINAL", "INNOCENT"):
        return status, None

    return status, DeductionStep(
        step=step_num,
        active_clue_ids=[clue.clue_id for clue in state.revealed_clues],
        sat_queries=queries,
        sat_calls=len(queries),
        target_coord=coord,
        verdict=status,
        newly_revealed_clue_id=None,
    )


def _classify(is_unsat: Callable[[int], bool], var: int) -> EntailmentStatus:
    """Classify C_var given ``is_unsat(literal)`` = "KB_t ∧ literal is UNSAT"."""
    criminal_forced = is_unsat(-var)  # KB_t ∧ ¬C_i
    innocent_forced = is_unsat(var)   # KB_t ∧ C_i
    if criminal_forced and innocent_forced:
        return "INCONSISTENT"
    if criminal_forced:
        return "CRIMINAL"
    if innocent_forced:
        return "INNOCENT"
    return "UNKNOWN"


def _first_forced(
    state: PublicState,
    record: _Recorder | None = None,
    deadline: float | None = None,
) -> tuple[EntailmentStatus, str | None]:
    """Scan unsolved cells row-major; return the first non-UNKNOWN status.

    INCONSISTENT surfaces on the first cell scanned, since it is a property of
    KB_t itself. Returns ("UNKNOWN", None) when no verdict is forced.
    """
    formula = encode_public_state(state)
    solver = DPLLSolver(formula)
    unsolved = set(state.unsolved_coords)
    for coord in all_coords(state.size):
        if coord not in unsolved:
            continue

        def is_unsat(literal: int, coord: str = coord) -> bool:
            limit = None if deadline is None else max(0.0, (deadline - perf_counter()) * 1000.0)
            result = solver.solve([literal], time_limit_ms=limit)
            if record is not None:
                record(coord, literal, result)
            return result.status == "UNSAT"

        status = _classify(is_unsat, formula.var_map[coord])
        if status != "UNKNOWN":
            return status, coord
    return "UNKNOWN", None
