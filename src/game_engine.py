"""GameEngine module for Griductive Solver.

Owns the full puzzle, hidden solution, and card reveal states.
Strictly isolates secret data from PublicState, provides board lifecycle methods
(load, restart), and verifies submitted verdicts via a Logic Agent.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from models import (
    Clue,
    EntailmentStatus,
    PublicState,
    Puzzle,
    PuzzleCell,
    Status,
    VerdictResponse,
    all_coords,
    coord_to_rc,
    rc_to_coord,
    resolve_region,
)


@runtime_checkable
class LogicAgentProtocol(Protocol):
    """Protocol for the deductive logic agent used to verify verdicts."""

    def classify_cell(self, public_state: PublicState, coord: str) -> EntailmentStatus:
        """Classify entailment of a target coordinate given current PublicState."""
        ...


class GameEngine:
    """Core Game Engine for Griductive.

    Maintains full puzzle data and hidden status.
    Exposes only PublicState to LogicAgent and GUI.
    """

    def __init__(
        self,
        puzzle: Puzzle | str | Path | dict[str, Any] | None = None,
        agent: Any = None,
    ) -> None:
        self._puzzle: Puzzle | None = None
        self._cell_map: dict[str, PuzzleCell] = {}
        self._revealed_coords: set[str] = set()
        self._proved_verdicts: dict[str, Status] = {}
        self._revealed_clues: list[Clue] = []
        self._unsolved_coords: list[str] = []
        self._agent: Any = agent

        if puzzle is not None:
            self.load_puzzle(puzzle)

    @property
    def puzzle_id(self) -> str | None:
        """Return ID of currently loaded puzzle, or None."""
        return self._puzzle.puzzle_id if self._puzzle else None

    @property
    def size(self) -> int:
        """Return grid dimension N of loaded puzzle, or 0."""
        return self._puzzle.size if self._puzzle else 0

    @property
    def total_cells(self) -> int:
        """Total number of cells on the grid (N x N)."""
        return (self._puzzle.size**2) if self._puzzle else 0

    @property
    def revealed_count(self) -> int:
        """Number of revealed/proved cells."""
        return len(self._revealed_coords)

    @property
    def unsolved_count(self) -> int:
        """Number of remaining face-down/unsolved cells."""
        return len(self._unsolved_coords)

    def set_agent(self, agent: Any) -> None:
        """Attach or update the Logic Agent used for entailment verification."""
        self._agent = agent

    def load_puzzle(self, puzzle_source: Puzzle | str | Path | dict[str, Any]) -> None:
        """Load and initialize a puzzle from a Puzzle object, JSON file path, or dict.

        Initializes the public state to contain only initial_revealed cards.
        """
        puzzle: Puzzle
        if isinstance(puzzle_source, Puzzle):
            puzzle = puzzle_source
        elif isinstance(puzzle_source, (str, Path)):
            path = Path(puzzle_source)
            if not path.is_file():
                raise FileNotFoundError(f"Puzzle file not found: {path}")
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            puzzle = Puzzle.from_dict(data)
        elif isinstance(puzzle_source, dict):
            puzzle = Puzzle.from_dict(puzzle_source)
        else:
            raise TypeError(f"Unsupported puzzle source type: {type(puzzle_source).__name__}")

        if puzzle.size <= 0:
            raise ValueError(f"Invalid puzzle size: {puzzle.size}")

        cell_map = puzzle.cell_map()
        expected_cells = puzzle.size**2
        if len(cell_map) != expected_cells:
            raise ValueError(
                f"Puzzle defines {len(cell_map)} cells, expected {expected_cells} for {puzzle.size}x{puzzle.size} grid."
            )

        for coord in puzzle.initial_revealed:
            if coord not in cell_map:
                raise ValueError(f"initial_revealed coordinate {coord!r} not in puzzle cells.")

        self._puzzle = puzzle
        self._cell_map = cell_map
        self.restart()

    def restart(self) -> None:
        """Reset the game state back to initial revealed cards."""
        if self._puzzle is None:
            raise RuntimeError("Cannot restart: no puzzle loaded.")

        self._revealed_coords = set(self._puzzle.initial_revealed)
        self._proved_verdicts = {
            coord: self._cell_map[coord].hidden_status
            for coord in self._puzzle.initial_revealed
        }
        self._revealed_clues = [
            self._cell_map[coord].clue
            for coord in self._puzzle.initial_revealed
        ]
        self._unsolved_coords = [
            coord for coord in all_coords(self._puzzle.size)
            if coord not in self._revealed_coords
        ]

    def get_public_state(self) -> PublicState:
        """Construct and return the public knowledge base state.

        Guarantees strict information hiding:
        - NEVER exposes hidden_status.
        - NEVER exposes clues belonging to unrevealed cards.
        - Returns copies of mutable containers to avoid external mutation.
        """
        if self._puzzle is None:
            raise RuntimeError("No puzzle is currently loaded in GameEngine.")

        ordered_coords = all_coords(self._puzzle.size)
        characters = [self._cell_map[coord].to_public_character() for coord in ordered_coords]

        return PublicState(
            size=self._puzzle.size,
            characters=characters,
            proved_verdicts=dict(self._proved_verdicts),
            revealed_clues=list(self._revealed_clues),
            unsolved_coords=list(self._unsolved_coords),
        )

    def submit_verdict(self, coord: str, verdict: Status) -> VerdictResponse:
        """Submit a verdict for a specific cell coordinate.

        The verdict is verified solely against the current public knowledge base
        via the attached Logic Agent (No-Guess principle).

        Returns:
            VerdictResponse:
            - accepted=True, reason="ENTAILED", revealed_clue=Clue if entailed.
            - accepted=False, reason="CONTRADICTED" if opposite is entailed.
            - accepted=False, reason="NOT_PROVABLE" if unforced (UNKNOWN).
            - accepted=False, reason="INCONSISTENT" if public KB is contradictory.
        """
        if self._puzzle is None:
            raise RuntimeError("No puzzle is currently loaded in GameEngine.")

        r, c = coord_to_rc(coord, self._puzzle.size)
        canonical_coord = rc_to_coord(r, c, self._puzzle.size)

        if verdict not in ("CRIMINAL", "INNOCENT"):
            raise ValueError(f"Invalid verdict: {verdict!r}. Must be 'CRIMINAL' or 'INNOCENT'.")

        if canonical_coord in self._proved_verdicts:
            raise ValueError(
                f"Cell {canonical_coord} is already solved with status {self._proved_verdicts[canonical_coord]}."
            )

        if self._agent is None:
            raise RuntimeError("No LogicAgent attached to GameEngine to evaluate verdict entailment.")

        entailment = self._query_agent(self.get_public_state(), canonical_coord)

        if entailment == verdict:
            # Move accepted! Reveal card and clue
            self._revealed_coords.add(canonical_coord)
            self._proved_verdicts[canonical_coord] = verdict
            cell = self._cell_map[canonical_coord]
            self._revealed_clues.append(cell.clue)
            if canonical_coord in self._unsolved_coords:
                self._unsolved_coords.remove(canonical_coord)

            return VerdictResponse(
                accepted=True,
                reason="ENTAILED",
                revealed_clue=cell.clue,
            )

        opposite: Status = "INNOCENT" if verdict == "CRIMINAL" else "CRIMINAL"
        if entailment == opposite:
            return VerdictResponse(accepted=False, reason="CONTRADICTED", revealed_clue=None)

        if entailment == "UNKNOWN":
            return VerdictResponse(accepted=False, reason="NOT_PROVABLE", revealed_clue=None)

        if entailment == "INCONSISTENT":
            return VerdictResponse(accepted=False, reason="INCONSISTENT", revealed_clue=None)

        raise ValueError(f"Unexpected entailment status from agent: {entailment!r}")

    def is_solved(self) -> bool:
        """Return True if all cells on the board have been proved/revealed."""
        if self._puzzle is None:
            return False
        return len(self._unsolved_coords) == 0

    def get_clue_highlight_cells(self, clue_id: str) -> list[str]:
        """Resolve cell coordinates referenced or counted by a REVEALED clue.

        Only revealed clues can be queried for highlighting (information hiding).
        """
        if self._puzzle is None:
            raise RuntimeError("No puzzle is currently loaded in GameEngine.")

        clue = next((c for c in self._revealed_clues if c.clue_id == clue_id), None)
        if clue is None:
            raise ValueError(f"Clue {clue_id!r} is not among currently revealed clues.")

        cells: list[str] = []
        size = self._puzzle.size

        if clue.type == "FACT" and clue.target:
            cells.append(clue.target)
        elif clue.type in ("SAME", "DIFFERENT"):
            if clue.a:
                cells.append(clue.a)
            if clue.b:
                cells.append(clue.b)
        elif clue.type in ("EXACTLY", "AT_LEAST", "AT_MOST", "PARITY"):
            if clue.region:
                cells.extend(resolve_region(clue.region, size))
        elif clue.type == "COMPARE_COUNT":
            if clue.r1:
                cells.extend(resolve_region(clue.r1, size))
            if clue.r2:
                cells.extend(resolve_region(clue.r2, size))

        # Deterministic deduplication
        seen: set[str] = set()
        unique_cells: list[str] = []
        for cell in cells:
            canonical = rc_to_coord(*coord_to_rc(cell, size), size)
            if canonical not in seen:
                seen.add(canonical)
                unique_cells.append(canonical)

        return unique_cells

    def get_revealed_clues(self) -> list[Clue]:
        """Return a copy of currently revealed clues."""
        return list(self._revealed_clues)

    def get_proved_verdicts(self) -> dict[str, Status]:
        """Return a copy of currently proved verdicts."""
        return dict(self._proved_verdicts)

    def get_solution_for_testing(self) -> dict[str, Status]:
        """Testing utility: return hidden ground truth for all cells.

        DO NOT USE in agent or gameplay logic.
        """
        if self._puzzle is None:
            raise RuntimeError("No puzzle loaded.")
        return {coord: cell.hidden_status for coord, cell in self._cell_map.items()}

    def _query_agent(self, public_state: PublicState, coord: str) -> EntailmentStatus:
        """Query attached logic agent with flexible dispatch."""
        if hasattr(self._agent, "classify_cell") and callable(self._agent.classify_cell):
            status = self._agent.classify_cell(public_state, coord)
        elif hasattr(self._agent, "check_entailment") and callable(self._agent.check_entailment):
            status = self._agent.check_entailment(public_state, coord)
        elif callable(self._agent):
            status = self._agent(public_state, coord)
        else:
            raise TypeError(
                f"Attached agent {self._agent!r} must implement classify_cell(public_state, coord) or be callable."
            )

        if status not in ("CRIMINAL", "INNOCENT", "UNKNOWN", "INCONSISTENT"):
            raise ValueError(f"Agent returned invalid entailment status: {status!r}")

        return status


# ---------------------------------------------------------------------------
# Direct Semantic Evaluator (Task 4 / Section 4.2)
# ---------------------------------------------------------------------------

def _infer_size(assignment: dict[str, Status]) -> int:
    """Infer grid dimension N from assignment cell coordinates."""
    n = len(assignment)
    if n > 0:
        root = math.isqrt(n)
        if root * root == n:
            return root

    # Fallback: scan maximum row/col index in coordinates
    max_r = 0
    max_c = 0
    for coord in assignment.keys():
        if len(coord) >= 2 and coord[0].isalpha() and coord[1:].isdigit():
            c_idx = ord(coord[0].upper()) - ord("A")
            r_idx = int(coord[1:]) - 1
            max_r = max(max_r, r_idx)
            max_c = max(max_c, c_idx)
    return max(max_r, max_c) + 1


def evaluate_clue(
    clue: Clue,
    assignment: dict[str, Status],
    size: int | None = None,
) -> bool:
    """Evaluate whether a Clue holds under a complete truth assignment.

    Acts as an independent semantic oracle without calling CNF encoder or SAT solver.

    Supported Clue Templates:
    - FACT: assignment[target] == status
    - SAME: assignment[a] == assignment[b]
    - DIFFERENT: assignment[a] != assignment[b]
    - EXACTLY: count(Criminals in region) == k
    - AT_LEAST: count(Criminals in region) >= k
    - AT_MOST: count(Criminals in region) <= k
    - PARITY: count(Criminals in region) % 2 == (0 if EVEN else 1)
    - COMPARE_COUNT: count(Criminals in r1) (op) count(Criminals in r2)

    Args:
        clue: Clue object (models.Clue).
        assignment: Complete mapping of cell coordinates to Status ("CRIMINAL" | "INNOCENT").
        size: Optional grid dimension. If omitted, inferred from assignment.

    Returns:
        bool: True if the clue's propositional condition is satisfied, False otherwise.

    Raises:
        KeyError: If a cell required to evaluate the clue is missing from assignment.
        ValueError: If clue fields or region definitions are malformed.
    """
    if not isinstance(clue, Clue):
        raise TypeError(f"Expected Clue object, got {type(clue).__name__}")

    if size is None:
        size = _infer_size(assignment)

    ctype = clue.type

    if ctype == "FACT":
        if clue.target is None or clue.status is None:
            raise ValueError(f"FACT clue {clue.clue_id!r} missing target or status.")
        if clue.target not in assignment:
            raise KeyError(f"Cell {clue.target!r} missing from assignment for FACT clue {clue.clue_id!r}.")
        return assignment[clue.target] == clue.status

    if ctype == "SAME":
        if clue.a is None or clue.b is None:
            raise ValueError(f"SAME clue {clue.clue_id!r} missing 'a' or 'b'.")
        if clue.a not in assignment:
            raise KeyError(f"Cell {clue.a!r} missing from assignment for SAME clue {clue.clue_id!r}.")
        if clue.b not in assignment:
            raise KeyError(f"Cell {clue.b!r} missing from assignment for SAME clue {clue.clue_id!r}.")
        return assignment[clue.a] == assignment[clue.b]

    if ctype == "DIFFERENT":
        if clue.a is None or clue.b is None:
            raise ValueError(f"DIFFERENT clue {clue.clue_id!r} missing 'a' or 'b'.")
        if clue.a not in assignment:
            raise KeyError(f"Cell {clue.a!r} missing from assignment for DIFFERENT clue {clue.clue_id!r}.")
        if clue.b not in assignment:
            raise KeyError(f"Cell {clue.b!r} missing from assignment for DIFFERENT clue {clue.clue_id!r}.")
        return assignment[clue.a] != assignment[clue.b]

    if ctype in ("EXACTLY", "AT_LEAST", "AT_MOST"):
        if clue.region is None or clue.k is None:
            raise ValueError(f"{ctype} clue {clue.clue_id!r} missing region or k.")
        cells = resolve_region(clue.region, size)
        for c in cells:
            if c not in assignment:
                raise KeyError(f"Cell {c!r} in region of clue {clue.clue_id!r} missing from assignment.")

        criminal_count = sum(1 for c in cells if assignment[c] == "CRIMINAL")
        if ctype == "EXACTLY":
            return criminal_count == clue.k
        elif ctype == "AT_LEAST":
            return criminal_count >= clue.k
        else:  # AT_MOST
            return criminal_count <= clue.k

    if ctype == "PARITY":
        if clue.region is None or clue.parity is None:
            raise ValueError(f"PARITY clue {clue.clue_id!r} missing region or parity.")
        cells = resolve_region(clue.region, size)
        for c in cells:
            if c not in assignment:
                raise KeyError(f"Cell {c!r} in region of clue {clue.clue_id!r} missing from assignment.")

        criminal_count = sum(1 for c in cells if assignment[c] == "CRIMINAL")
        expected_remainder = 0 if clue.parity == "EVEN" else 1
        return (criminal_count % 2) == expected_remainder

    if ctype == "COMPARE_COUNT":
        if clue.r1 is None or clue.op is None or clue.r2 is None:
            raise ValueError(f"COMPARE_COUNT clue {clue.clue_id!r} missing r1, op, or r2.")
        cells1 = resolve_region(clue.r1, size)
        cells2 = resolve_region(clue.r2, size)
        for c in cells1:
            if c not in assignment:
                raise KeyError(f"Cell {c!r} in r1 of clue {clue.clue_id!r} missing from assignment.")
        for c in cells2:
            if c not in assignment:
                raise KeyError(f"Cell {c!r} in r2 of clue {clue.clue_id!r} missing from assignment.")

        count1 = sum(1 for c in cells1 if assignment[c] == "CRIMINAL")
        count2 = sum(1 for c in cells2 if assignment[c] == "CRIMINAL")

        if clue.op == "GT":
            return count1 > count2
        elif clue.op == "LT":
            return count1 < count2
        elif clue.op == "EQ":
            return count1 == count2
        else:
            raise ValueError(f"Unsupported compare op: {clue.op!r}")

    raise ValueError(f"Unsupported clue type: {ctype!r}")


def evaluate_puzzle(puzzle: Puzzle, assignment: dict[str, Status]) -> bool:
    """Evaluate whether an entire puzzle's clues are satisfied by a complete assignment."""
    return all(evaluate_clue(cell.clue, assignment, puzzle.size) for cell in puzzle.cells)
