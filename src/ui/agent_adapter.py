"""Thin adapter isolating GUI calls to LogicAgent.

Follows the project's strict information-hiding and non-fabrication rules:
- Never guesses or fakes LogicAgent reasoning when src/agent.py is unimplemented.
- Never inspects hidden_status, PuzzleCell, or get_solution_for_testing().
- Exposes explicit capability flags so the GUI disables Agent-dependent actions
  (verdict verification, Hint, Auto Solve) until a real LogicAgent is available.
"""

from __future__ import annotations

import importlib
import inspect
from dataclasses import dataclass
from typing import Any, Literal

from game_engine import GameEngine
from models import DeductionStep, HintResponse, PublicState, VerdictResponse


AutoSolveOutcome = Literal["STEP", "SOLVED", "UNKNOWN", "INCONSISTENT", "UNAVAILABLE", "ERROR"]


@dataclass(frozen=True)
class AutoSolveStepResult:
    """Normalized outcome of a single GUI Auto Solve tick."""

    status: AutoSolveOutcome
    step: DeductionStep | None = None
    verdict_response: VerdictResponse | None = None
    message: str = ""


def discover_default_agent() -> tuple[Any | None, str]:
    """Attempt to import and instantiate LogicAgent from ``src/agent.py``.

    Returns ``(agent_instance, status_message)``. If ``src/agent.py`` is empty
    or does not expose a usable agent class yet, returns ``(None, reason)``.
    """
    try:
        agent_module = importlib.import_module("agent")
    except Exception as exc:
        return None, f"Khong the nap src/agent.py: {exc}"

    for attr_name in ("LogicAgent", "DeductiveLogicAgent", "Agent"):
        candidate = getattr(agent_module, attr_name, None)
        if inspect.isclass(candidate):
            try:
                instance = candidate()
            except TypeError as exc:
                return None, f"LogicAgent ({attr_name}) can tham so khoi tao: {exc}"
            except Exception as exc:
                return None, f"Loi khoi tao {attr_name}: {exc}"
            return instance, f"Da ket noi {attr_name} tu src/agent.py."

    return None, "LogicAgent chua san sang (src/agent.py chua co implementation)."


class AgentAdapter:
    """Adapter between the GUI and an optional LogicAgent implementation."""

    def __init__(self, agent: Any | None = None, *, auto_discover: bool = True) -> None:
        if agent is not None:
            self._agent: Any | None = agent
            self._status_message = f"Da ket noi {type(agent).__name__}."
        elif auto_discover:
            self._agent, self._status_message = discover_default_agent()
        else:
            self._agent = None
            self._status_message = "LogicAgent chua duoc gan."

    @property
    def raw_agent(self) -> Any | None:
        return self._agent

    @property
    def status_message(self) -> str:
        return self._status_message

    @property
    def can_verify_verdict(self) -> bool:
        """True if the agent satisfies GameEngine's entailment check interface."""
        if self._agent is None:
            return False
        return (
            callable(getattr(self._agent, "classify_cell", None))
            or callable(getattr(self._agent, "check_entailment", None))
            or callable(self._agent)
        )

    @property
    def can_hint(self) -> bool:
        """True if the agent exposes a Hint API returning HintResponse."""
        return self._resolve_hint_callable() is not None

    @property
    def can_auto_solve(self) -> bool:
        """True if the agent exposes a single-step deduction API."""
        return self._resolve_step_callable() is not None

    @property
    def is_ready(self) -> bool:
        return self.can_verify_verdict

    def attach_to_engine(self, engine: GameEngine) -> bool:
        """Attach the real agent to ``engine`` when capable; otherwise clear it."""
        if self.can_verify_verdict:
            engine.set_agent(self._agent)
            return True
        engine.set_agent(None)
        return False

    def request_hint(self, public_state: PublicState) -> HintResponse:
        """Request a HintResponse derived strictly from ``public_state``."""
        hint_fn = self._resolve_hint_callable()
        if hint_fn is None:
            raise RuntimeError("Hint chua san sang: LogicAgent chua cai dat API get_hint().")

        result = hint_fn(public_state)
        if not isinstance(result, HintResponse):
            raise TypeError(
                f"Agent hint API must return HintResponse, got {type(result).__name__}."
            )
        return result

    def run_auto_solve_step(
        self,
        engine: GameEngine,
        *,
        step_num: int | None = None,
    ) -> AutoSolveStepResult:
        """Execute a single no-guess deduction step via the attached LogicAgent.

        Calls the agent with ``PublicState`` only. If the step returns a
        ``DeductionStep`` without having
        submitted the verdict to ``engine`` yet, this adapter submits it through
        ``engine.submit_verdict()`` so the engine retains sole ownership of card
        reveals.
        """
        if engine.is_solved():
            return AutoSolveStepResult(status="SOLVED", message="Ban choi da duoc giai hoan toan.")

        step_fn = self._resolve_step_callable()
        if step_fn is None:
            return AutoSolveStepResult(
                status="UNAVAILABLE",
                message="Auto Solve chua san sang: LogicAgent chua cai dat API step.",
            )

        resolved_step = (
            step_num
            if step_num is not None
            else max(1, engine.revealed_count - engine.initial_revealed_count + 1)
        )
        public_state = engine.get_public_state()
        try:
            raw_result = self._invoke_step_callable(step_fn, public_state, step_num=resolved_step)
        except Exception as exc:
            return AutoSolveStepResult(status="ERROR", message=f"Loi khi chay Auto Solve: {exc}")

        if raw_result is None:
            if engine.is_solved():
                return AutoSolveStepResult(status="SOLVED", message="Da giai xong ban choi.")
            return AutoSolveStepResult(
                status="UNKNOWN",
                message="Auto Solve dung: khong co o nao bi bat buoc (UNKNOWN).",
            )

        if isinstance(raw_result, str):
            upper = raw_result.upper()
            if upper == "INCONSISTENT":
                return AutoSolveStepResult(
                    status="INCONSISTENT",
                    message="Auto Solve dung: co so tri thuc mau thuan (INCONSISTENT).",
                )
            if upper == "UNKNOWN":
                return AutoSolveStepResult(
                    status="UNKNOWN",
                    message="Auto Solve dung: khong co phan quyet bi bat buoc (UNKNOWN).",
                )
            if upper == "SOLVED":
                return AutoSolveStepResult(status="SOLVED", message="Da giai xong ban choi.")

        if not isinstance(raw_result, DeductionStep):
            return AutoSolveStepResult(
                status="ERROR",
                message=f"Agent step tra ve kieu khong hop le: {type(raw_result).__name__}.",
            )

        step = raw_result
        already_applied = step.target_coord in engine.get_proved_verdicts()
        verdict_response: VerdictResponse | None = None

        if not already_applied:
            if not self.can_verify_verdict:
                return AutoSolveStepResult(
                    status="UNAVAILABLE",
                    message="LogicAgent chua ho tro xac nhan verdict voi GameEngine.",
                )
            verdict_response = engine.submit_verdict(step.target_coord, step.verdict)
            if not verdict_response.accepted:
                if verdict_response.reason == "INCONSISTENT":
                    return AutoSolveStepResult(
                        status="INCONSISTENT",
                        step=step,
                        verdict_response=verdict_response,
                        message="Auto Solve dung: KB bi mau thuan (INCONSISTENT).",
                    )
                return AutoSolveStepResult(
                    status="UNKNOWN",
                    step=step,
                    verdict_response=verdict_response,
                    message=f"Auto Solve dung: Engine tu choi phan quyet ({verdict_response.reason}).",
                )
            if step.newly_revealed_clue_id is None and verdict_response.revealed_clue is not None:
                step = DeductionStep(
                    step=step.step,
                    active_clue_ids=list(step.active_clue_ids),
                    sat_queries=list(step.sat_queries),
                    sat_calls=step.sat_calls,
                    target_coord=step.target_coord,
                    verdict=step.verdict,
                    newly_revealed_clue_id=verdict_response.revealed_clue.clue_id,
                )

        return AutoSolveStepResult(
            status="STEP",
            step=step,
            verdict_response=verdict_response,
            message=f"Buoc {step.step}: {step.target_coord} -> {step.verdict}",
        )

    def _resolve_hint_callable(self) -> Any | None:
        if self._agent is None:
            return None
        for name in ("get_hint", "hint", "suggest_hint"):
            fn = getattr(self._agent, name, None)
            if callable(fn):
                return fn
        return None

    def _resolve_step_callable(self) -> Any | None:
        if self._agent is None:
            return None
        for name in ("step", "deduce_step", "solve_step", "next_step"):
            fn = getattr(self._agent, name, None)
            if callable(fn):
                return fn
        return None

    def _invoke_step_callable(
        self,
        step_fn: Any,
        public_state: PublicState,
        *,
        step_num: int | None = None,
    ) -> Any:
        """Invoke the Agent using the public knowledge state only."""
        if step_num is not None:
            try:
                params = inspect.signature(step_fn).parameters
                accepts_step_num = "step_num" in params or any(
                    param.kind == inspect.Parameter.VAR_KEYWORD for param in params.values()
                )
            except (TypeError, ValueError):
                accepts_step_num = False
            if accepts_step_num:
                return step_fn(public_state, step_num=step_num)
        return step_fn(public_state)
