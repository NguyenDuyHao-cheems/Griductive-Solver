"""Pure-Python DPLL SAT solver for Griductive knowledge bases (Section 4.3).

Implements the Davis-Putnam-Logemann-Loveland procedure from scratch:

1. Unit propagation driven by literal occurrence lists.
2. Conflict detection (a clause whose literals are all false).
3. Deterministic variable selection (smallest unassigned variable ID;
   primary variables C_i come first because the encoder numbers them 1..N^2).
4. Recursive branching (True before False) with chronological backtracking.
5. Returns SAT with a complete assignment over every variable, or UNSAT.
6. Records decisions, propagations, backtracks and runtime_ms per call.

Assumptions (temporary unit literals such as +C_i / -C_i) are applied only to
the per-call search state, so the KB_t passed in is never mutated and repeated
queries on the same solver are fully independent.

No external SAT/CSP library is used here.
"""

from __future__ import annotations

import sys
from collections.abc import Iterable, Mapping, Sequence
from time import perf_counter

if __package__:
    from .models import CNFFormula, SolverResult
else:
    from models import CNFFormula, SolverResult

__all__ = [
    "DPLLSolver",
    "SolverTimeout",
    "solve",
    "verify_assignment",
]

# Value encoding inside the solver: 0 = unassigned, 1 = True, -1 = False.
_UNASSIGNED = 0


class SolverTimeout(RuntimeError):
    """Raised when a solve call exceeds its ``time_limit_ms``.

    ``partial`` carries the metrics collected before the limit was hit, so a
    benchmark can still report the failed case instead of discarding it. Its
    ``status`` is ``"TIMEOUT"``: an interrupted search proves neither SAT nor
    UNSAT.

    The limit is soft: the deadline is checked at the start of each recursive
    DPLL call, not inside unit propagation, so a call may overrun it slightly.
    """

    def __init__(self, partial: SolverResult) -> None:
        super().__init__(f"DPLL exceeded its time limit after {partial.runtime_ms:.3f} ms.")
        self.partial = partial


class DPLLSolver:
    """Reusable DPLL solver bound to one CNF formula (e.g. KB_t).

    The constructor normalises the clauses and builds occurrence lists once.
    Each :meth:`solve` call creates fresh search state, so a Logic Agent can
    ask ``KB_t ∧ ¬C_i`` and ``KB_t ∧ C_i`` for many cells on the same instance
    without any state leaking between queries.
    """

    def __init__(
        self,
        formula: CNFFormula | Iterable[Iterable[int]],
        num_vars: int | None = None,
    ) -> None:
        if isinstance(formula, CNFFormula):
            raw_clauses: Iterable[Iterable[int]] = formula.clauses
            declared_vars = formula.total_vars
        else:
            raw_clauses = formula
            declared_vars = 0

        clauses: list[tuple[int, ...]] = []
        has_empty_clause = False
        max_var = 0
        for raw in raw_clauses:
            clause = _normalise_clause(raw)
            if clause is None:  # tautology: always satisfied, never constrains
                continue
            if not clause:
                has_empty_clause = True
            for lit in clause:
                max_var = max(max_var, abs(lit))
            clauses.append(clause)

        if num_vars is not None and (not isinstance(num_vars, int) or num_vars < 0):
            raise ValueError(f"num_vars must be a non-negative int, got {num_vars!r}.")

        self._clauses: tuple[tuple[int, ...], ...] = tuple(clauses)
        self._has_empty_clause = has_empty_clause
        self._num_vars = max(declared_vars, num_vars or 0, max_var)

        # occurrences[_lit_index(l)] -> indices of clauses containing literal l.
        occurrences: list[list[int]] = [[] for _ in range(2 * self._num_vars + 2)]
        for index, clause in enumerate(self._clauses):
            for lit in clause:
                occurrences[_lit_index(lit)].append(index)
        self._occurrences: tuple[tuple[int, ...], ...] = tuple(tuple(o) for o in occurrences)

        # Deterministic branching order: ascending variable ID among variables
        # that actually appear in some clause. Others are set to False at the end.
        used = sorted({abs(lit) for clause in self._clauses for lit in clause})
        self._branch_order: tuple[int, ...] = tuple(used)

    @property
    def num_vars(self) -> int:
        return self._num_vars

    @property
    def num_clauses(self) -> int:
        return len(self._clauses)

    def solve(
        self,
        assumptions: Iterable[int] = (),
        *,
        time_limit_ms: float | None = None,
    ) -> SolverResult:
        """Decide satisfiability of the formula under the given assumptions.

        ``assumptions`` are signed literals (``+v`` = True, ``-v`` = False)
        treated exactly like temporary unit clauses: they are assigned before
        search and counted as propagations, so ``solve([l])`` reports the same
        metrics as solving the formula with an extra unit clause ``[l]``.
        """
        assumption_list = [_check_literal(lit) for lit in assumptions]
        if time_limit_ms is not None and time_limit_ms < 0:
            raise ValueError(f"time_limit_ms must be non-negative, got {time_limit_ms!r}.")
        return _Search(self, assumption_list, time_limit_ms).run()


def solve(
    formula: CNFFormula | Iterable[Iterable[int]],
    assumptions: Iterable[int] = (),
    *,
    num_vars: int | None = None,
    time_limit_ms: float | None = None,
) -> SolverResult:
    """One-shot convenience wrapper around :class:`DPLLSolver`."""
    return DPLLSolver(formula, num_vars=num_vars).solve(
        assumptions, time_limit_ms=time_limit_ms
    )


def verify_assignment(
    clauses: Iterable[Sequence[int]],
    assignment: Mapping[int, bool],
) -> bool:
    """Return True iff every clause has at least one literal true under ``assignment``."""
    for clause in clauses:
        if not any(assignment.get(abs(lit), False) == (lit > 0) for lit in clause):
            return False
    return True


# ---------------------------------------------------------------------------
# Internal search state (one instance per solve call)
# ---------------------------------------------------------------------------

class _Search:
    def __init__(
        self,
        solver: DPLLSolver,
        assumptions: list[int],
        time_limit_ms: float | None,
    ) -> None:
        self._clauses = solver._clauses
        self._occurrences = solver._occurrences
        self._branch_order = solver._branch_order
        self._has_empty_clause = solver._has_empty_clause
        self._assumptions = assumptions

        # Assumptions may mention variables outside the formula; they still
        # belong to the returned complete assignment.
        self._num_vars = max([solver._num_vars, *(abs(lit) for lit in assumptions)])
        missing = 2 * self._num_vars + 2 - len(self._occurrences)
        if missing > 0:  # such variables occur in no clause
            self._occurrences = self._occurrences + ((),) * missing
        self._values: list[int] = [_UNASSIGNED] * (self._num_vars + 1)
        self._trail: list[int] = []
        self._queue_head = 0

        self._decisions = 0
        self._propagations = 0
        self._backtracks = 0

        self._time_limit_ms = time_limit_ms
        self._start = 0.0
        self._deadline: float | None = None

    # -- driver -------------------------------------------------------------

    def run(self) -> SolverResult:
        self._start = perf_counter()
        if self._time_limit_ms is not None:
            self._deadline = self._start + self._time_limit_ms / 1000.0

        satisfiable = (
            not self._has_empty_clause
            and self._apply_root_units()
            and self._dpll_with_depth_guard()
        )

        runtime_ms = (perf_counter() - self._start) * 1000.0
        assignment = None
        if satisfiable:
            assignment = {var: self._values[var] == 1 for var in range(1, self._num_vars + 1)}
        return SolverResult(
            status="SAT" if satisfiable else "UNSAT",
            assignment=assignment,
            decisions=self._decisions,
            propagations=self._propagations,
            backtracks=self._backtracks,
            runtime_ms=runtime_ms,
        )

    def _apply_root_units(self) -> bool:
        """Assign assumptions and original unit clauses at decision level 0."""
        for lit in self._assumptions:
            if not self._enqueue(lit):
                return False
        for clause in self._clauses:
            if len(clause) == 1 and not self._enqueue(clause[0]):
                return False
        return True

    def _dpll_with_depth_guard(self) -> bool:
        # Recursion depth grows by one per decision, bounded by the number of
        # branch variables; make sure larger KBs cannot hit Python's limit.
        needed = len(self._branch_order) + 200
        previous = sys.getrecursionlimit()
        if needed > previous:
            sys.setrecursionlimit(needed)
        try:
            return self._dpll()
        finally:
            if needed > previous:
                sys.setrecursionlimit(previous)

    # -- DPLL core ------------------------------------------------------------

    def _dpll(self) -> bool:
        self._check_deadline()
        if not self._propagate():
            return False  # conflict detected under the current partial assignment

        var = self._select_variable()
        if var is None:
            return True  # every clause variable assigned with no conflict -> SAT

        for literal in (var, -var):  # deterministic polarity: True first
            self._decisions += 1
            mark = len(self._trail)
            self._enqueue(literal, decision=True)  # var is unassigned: no conflict
            if self._dpll():
                return True
            self._undo(mark)
            self._backtracks += 1
        return False

    def _propagate(self) -> bool:
        """Unit propagation. Returns False on conflict.

        Only clauses containing the negation of a newly assigned literal can
        become unit or empty, so each trail literal is examined once.
        """
        values = self._values
        while self._queue_head < len(self._trail):
            falsified = -self._trail[self._queue_head]
            self._queue_head += 1
            for clause_index in self._occurrences[_lit_index(falsified)]:
                unit_literal = 0
                unassigned = 0
                satisfied = False
                for lit in self._clauses[clause_index]:
                    value = values[abs(lit)]
                    if value == _UNASSIGNED:
                        unassigned += 1
                        unit_literal = lit
                        if unassigned > 1:
                            break
                    elif (value == 1) == (lit > 0):
                        satisfied = True
                        break
                if satisfied or unassigned > 1:
                    continue
                if unassigned == 0:
                    return False  # conflict: every literal of the clause is false
                self._enqueue(unit_literal)
        return True

    def _select_variable(self) -> int | None:
        values = self._values
        for var in self._branch_order:
            if values[var] == _UNASSIGNED:
                return var
        return None

    # -- trail management -------------------------------------------------------

    def _enqueue(self, literal: int, *, decision: bool = False) -> bool:
        """Assign ``literal``; returns False if it contradicts the current value.

        Every assignment not made by a branching decision is counted as a
        propagation (assumptions, original unit clauses, derived units).
        """
        var = abs(literal)
        wanted = 1 if literal > 0 else -1
        current = self._values[var]
        if current != _UNASSIGNED:
            return current == wanted
        self._values[var] = wanted
        self._trail.append(literal)
        if not decision:
            self._propagations += 1
        return True

    def _undo(self, mark: int) -> None:
        values = self._values
        while len(self._trail) > mark:
            values[abs(self._trail.pop())] = _UNASSIGNED
        self._queue_head = mark

    def _check_deadline(self) -> None:
        if self._deadline is not None and perf_counter() > self._deadline:
            raise SolverTimeout(
                SolverResult(
                    status="TIMEOUT",
                    assignment=None,
                    decisions=self._decisions,
                    propagations=self._propagations,
                    backtracks=self._backtracks,
                    runtime_ms=(perf_counter() - self._start) * 1000.0,
                )
            )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _lit_index(literal: int) -> int:
    return 2 * abs(literal) + (1 if literal < 0 else 0)


def _check_literal(literal: object) -> int:
    if not isinstance(literal, int) or isinstance(literal, bool) or literal == 0:
        raise ValueError(f"Literals must be non-zero ints, got {literal!r}.")
    return literal


def _normalise_clause(raw: Iterable[int]) -> tuple[int, ...] | None:
    """Validate literals, drop duplicates (order-preserving); None for tautologies."""
    seen: set[int] = set()
    clause: list[int] = []
    for lit in raw:
        _check_literal(lit)
        if -lit in seen:
            return None
        if lit not in seen:
            seen.add(lit)
            clause.append(lit)
    return tuple(clause)
