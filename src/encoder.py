"""Encode structured Griductive clues and public verdicts as CNF."""

from __future__ import annotations

from collections.abc import Iterable, Mapping

if __package__:
    from .models import (
        Clue, CNFFormula, PublicState, Region, Status,
        all_coords, coord_to_rc, rc_to_coord, resolve_region,
    )
else:
    from models import (
        Clue, CNFFormula, PublicState, Region, Status,
        all_coords, coord_to_rc, rc_to_coord, resolve_region,
    )


def build_var_map(state: PublicState) -> tuple[dict[str, int], dict[int, str]]:
    """Return coordinate-to-ID and ID-to-coordinate maps in row-major order.

    For a complete board, primary IDs are 1 through size**2. Auxiliary IDs
    start above that range.
    """
    var_map = _primary_var_map(state.size)
    character_coords = [character.coord for character in state.characters]
    if len(character_coords) != len(var_map) or set(character_coords) != var_map.keys():
        raise ValueError("PublicState.characters must contain one character per grid cell.")

    coord_by_var = {var_id: coord for coord, var_id in var_map.items()}
    return var_map, coord_by_var


def encode_public_state(state: PublicState) -> CNFFormula:
    """Build the current knowledge base from revealed clues and proved verdicts."""
    var_map, _ = build_var_map(state)
    return _encode(state.revealed_clues, state.size, var_map, state.proved_verdicts)


def encode_clues(clues: Iterable[Clue], size: int) -> CNFFormula:
    """Encode an explicit clue set over the board, e.g. for uniqueness checking."""
    return _encode(clues, size, _primary_var_map(size), {})


def validate_clue(clue: Clue, size: int) -> bool:
    """Return True for a well-formed clue or raise ValueError with its ID."""
    try:
        _validate_grid_size(size)
        match clue.type:
            case "FACT":
                _validate_coord(clue.target, size, "target")
                if clue.status not in ("CRIMINAL", "INNOCENT"):
                    raise ValueError(f"status must be CRIMINAL or INNOCENT, got {clue.status!r}.")
            case "SAME" | "DIFFERENT":
                _validate_coord(clue.a, size, "a")
                _validate_coord(clue.b, size, "b")
            case "EXACTLY" | "AT_LEAST" | "AT_MOST":
                region_size = _region_size(clue.region, size, "region")
                k = clue.k
                if not isinstance(k, int) or isinstance(k, bool) or not 0 <= k <= region_size:
                    raise ValueError(f"k must be an integer from 0 to {region_size}, got {k!r}.")
            case "PARITY":
                _region_size(clue.region, size, "region")
                if clue.parity not in ("EVEN", "ODD"):
                    raise ValueError(f"parity must be EVEN or ODD, got {clue.parity!r}.")
            case "COMPARE_COUNT":
                _region_size(clue.r1, size, "r1")
                _region_size(clue.r2, size, "r2")
                if clue.op not in ("GT", "LT", "EQ"):
                    raise ValueError(f"op must be GT, LT, or EQ, got {clue.op!r}.")
            case _:
                raise ValueError(f"unsupported clue type {clue.type!r}.")
    except ValueError as error:
        raise ValueError(f"Clue {clue.clue_id!r}: {error}") from error
    return True


def _validate_grid_size(size: int) -> None:
    if not isinstance(size, int) or isinstance(size, bool) or size <= 0:
        raise ValueError(f"Grid size must be a positive integer, got {size!r}.")


def _primary_var_map(size: int) -> dict[str, int]:
    _validate_grid_size(size)
    return {coord: var_id for var_id, coord in enumerate(all_coords(size), start=1)}


def _validate_coord(coord: str | None, size: int, field: str) -> None:
    if not isinstance(coord, str):
        raise ValueError(f"{field} must be a cell coordinate, got {coord!r}.")
    try:
        coord_to_rc(coord, size)
    except (TypeError, ValueError) as error:
        raise ValueError(f"{field}: {error}") from error


def _region_size(region: Region | None, size: int, field: str) -> int:
    if not isinstance(region, Region):
        raise ValueError(f"{field} must be a Region, got {region!r}.")
    try:
        coords = resolve_region(region, size)
    except (TypeError, ValueError) as error:
        raise ValueError(f"{field}: {error}") from error
    if not coords:
        raise ValueError(f"{field} must contain at least one cell.")
    return len(coords)


def _encode(
    clues: Iterable[Clue],
    size: int,
    var_map: dict[str, int],
    proved_verdicts: Mapping[str, Status],
) -> CNFFormula:
    encoder = _ClueEncoder(size, var_map)
    for clue in clues:
        encoder.add_clue(clue)

    for coord, status in sorted(proved_verdicts.items()):
        if coord not in var_map or status not in ("CRIMINAL", "INNOCENT"):
            raise ValueError(f"Invalid proved verdict for {coord!r}: {status!r}.")
        variable = var_map[coord]
        encoder.clauses.append([variable if status == "CRIMINAL" else -variable])

    return CNFFormula(
        num_primary_vars=len(var_map),
        num_aux_vars=encoder.last_var - len(var_map),
        var_map=var_map,
        clauses=encoder.clauses,
    )


class _ClueEncoder:
    def __init__(self, size: int, var_map: dict[str, int]) -> None:
        self.size = size
        self.var_map = var_map
        self.last_var = len(var_map)
        self.clauses: list[list[int]] = []

    def add_clue(self, clue: Clue) -> None:
        validate_clue(clue, self.size)
        match clue.type:
            case "FACT":
                variable = self._cell_var(clue.target)
                self.clauses.append([variable if clue.status == "CRIMINAL" else -variable])
            case "SAME" | "DIFFERENT":
                a, b = self._cell_var(clue.a), self._cell_var(clue.b)
                if a == b:
                    if clue.type == "DIFFERENT":
                        self.clauses.append([])
                elif clue.type == "SAME":
                    self.clauses.extend([[-a, b], [a, -b]])
                else:
                    self.clauses.extend([[a, b], [-a, -b]])
            case "EXACTLY" | "AT_LEAST" | "AT_MOST":
                assert clue.k is not None  # Checked by validate_clue.
                variables = self._region_vars(clue.region)
                lower = 0 if clue.type == "AT_MOST" else clue.k
                upper = len(variables) if clue.type == "AT_LEAST" else clue.k
                self._add_count_bounds(variables, lower, upper)
            case "PARITY":
                variables = self._region_vars(clue.region)
                odd = variables[0]
                for variable in variables[1:]:
                    odd = self._xor(odd, variable)
                self.clauses.append([odd if clue.parity == "ODD" else -odd])
            case "COMPARE_COUNT":
                left = self._region_vars(clue.r1)
                right = self._region_vars(clue.r2)
                left_thresholds = self._thresholds(left, len(left))
                right_thresholds = self._thresholds(right, len(right))
                if clue.op == "EQ":
                    self._add_count_comparison(left_thresholds, right_thresholds, strict=False)
                    self._add_count_comparison(right_thresholds, left_thresholds, strict=False)
                elif clue.op == "GT":
                    self._add_count_comparison(left_thresholds, right_thresholds, strict=True)
                else:
                    self._add_count_comparison(right_thresholds, left_thresholds, strict=True)

    def _cell_var(self, coord: str | None) -> int:
        assert coord is not None  # Checked by validate_clue.
        canonical = rc_to_coord(*coord_to_rc(coord, self.size), self.size)
        return self.var_map[canonical]

    def _region_vars(self, region: Region | None) -> list[int]:
        assert region is not None  # Checked by validate_clue.
        return [self.var_map[coord] for coord in resolve_region(region, self.size)]

    def _new_var(self) -> int:
        self.last_var += 1
        return self.last_var

    def _add_count_bounds(self, variables: list[int], lower: int, upper: int) -> None:
        size = len(variables)
        if upper == 0:
            self.clauses.extend([-variable] for variable in variables)
        elif lower == size:
            self.clauses.extend([variable] for variable in variables)
        elif lower > 0 or upper < size:
            limit = upper + 1 if upper < size else lower
            thresholds = self._thresholds(variables, limit)
            if lower > 0:
                self.clauses.append([thresholds[lower - 1]])
            if upper < size:
                self.clauses.append([-thresholds[upper]])

    def _thresholds(self, variables: list[int], limit: int) -> list[int]:
        """Return literals for count >= 1 through count >= limit.

        For each prefix, the next threshold is true if the preceding prefix
        already reached it, or if the new variable raises the preceding count
        by one. The number of clauses is O(len(variables) * limit).
        """
        previous = [variables[0]]
        for index, variable in enumerate(variables[1:], start=2):
            current = []
            for count in range(1, min(index, limit) + 1):
                threshold = self._new_var()
                if count == 1:
                    # threshold <-> (previous[0] OR variable)
                    at_least_one = previous[0]
                    self.clauses.extend([
                        [-at_least_one, threshold], [-variable, threshold],
                        [at_least_one, variable, -threshold],
                    ])
                elif count == index:
                    # All variables in this prefix must be true.
                    all_previous = previous[-1]
                    self.clauses.extend([
                        [-all_previous, -variable, threshold],
                        [all_previous, -threshold], [variable, -threshold],
                    ])
                else:
                    same_count, one_less = previous[count - 1], previous[count - 2]
                    # threshold <-> (same_count OR (one_less AND variable))
                    self.clauses.extend([
                        [-same_count, threshold], [-one_less, -variable, threshold],
                        [same_count, one_less, -threshold], [same_count, variable, -threshold],
                    ])
                current.append(threshold)
            previous = current
        return previous

    def _xor(self, a: int, b: int) -> int:
        result = self._new_var()
        self.clauses.extend([
            [a, b, -result], [-a, -b, -result], [a, -b, result], [-a, b, result],
        ])
        return result

    def _add_count_comparison(self, left: list[int], right: list[int], *, strict: bool) -> None:
        """Assert left count >= right count, shifted by one for strict comparison."""
        if strict:
            self.clauses.append([left[0]])
        for index, right_threshold in enumerate(right, start=int(strict)):
            clause = [-right_threshold]
            if index < len(left):
                clause.append(left[index])
            self.clauses.append(clause)
