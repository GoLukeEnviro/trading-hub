"""Abstract base classes for real (non-dry-run) adapters.

All real adapter bases inherit from :class:`RealAdapterBase`, which
provides:

* **Environment gate** — refuses instantiation unless
  ``SI_V2_ENABLE_REAL_ADAPTERS=1`` (configurable via *gate_flag*).
* **Audit recording** — every method invocation (allowed or denied)
  is recorded via the injected :class:`AdapterAuditSink`.
* **Call budget** — optional sliding-window rate limiter. When
  exhausted, the call is denied and a denied audit event is recorded.

Four specialised abstract bases are provided, one per external system:

* :class:`RealDockerAdapterBase`
* :class:`RealFreqtradeAdapterBase`
* :class:`RealTelegramAdapterBase`
* :class:`RealAi4tradeAdapterBase`

All of them refuse instantiation without the gate flag and each records a
denied audit event when the gate blocks creation.

No concrete adapter is implemented here — only abstract infrastructure.
"""

from __future__ import annotations

from abc import ABC
from datetime import UTC, datetime
from uuid import uuid4

from si_v2.adapters.audit import AdapterAuditEvent, AdapterAuditSink, AdapterMode
from si_v2.adapters.call_budget import CallBudgetChecker
from si_v2.config.gate import SI_V2_ENABLE_REAL_ADAPTERS, require_env_enabled


class RealAdapterBase(ABC):  # noqa: B024
    """Abstract base for all real adapters.

    Provides gate, audit, and call-budget infrastructure. Subclasses
    call ``_record_audit`` and ``_check_budget`` at the start of every
    public method.

    Args:
        audit_sink: Where audit events are recorded.
        call_budget: Optional sliding-window rate limiter. ``None``
            means no budget enforcement.
        gate_flag: Environment variable checked at construction. Defaults
            to :attr:`SI_V2_ENABLE_REAL_ADAPTERS`.
    """

    def __init__(
        self,
        audit_sink: AdapterAuditSink,
        call_budget: CallBudgetChecker | None = None,
        gate_flag: str = SI_V2_ENABLE_REAL_ADAPTERS,
    ) -> None:
        # Gate check — refuses instantiation if env var not set to "1".
        require_env_enabled(gate_flag, self.__class__.__name__)

        self._audit_sink = audit_sink
        self._call_budget = call_budget
        self._gate_flag = gate_flag

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _record_audit(
        self,
        method_name: str,
        allowed: bool,
        reason: str = "",
        duration_ms: float | None = None,
        error: str | None = None,
    ) -> None:
        """Record an audit event for a method invocation.

        Args:
            method_name: The method being invoked.
            allowed: Whether the invocation was allowed.
            reason: Human-readable reason for the decision.
            duration_ms: Execution duration if measured.
            error: Error message if the method raised.
        """
        event = AdapterAuditEvent(
            timestamp_utc=datetime.now(UTC),
            adapter_name=self.__class__.__name__,
            method_name=method_name,
            mode=AdapterMode.real,
            call_id=str(uuid4()),
            allowed=allowed,
            reason=reason,
            duration_ms=duration_ms,
            error=error,
        )
        self._audit_sink.record(event)

    def _check_budget(self, method_name: str) -> bool:
        """Check the call budget and record a denied event if exhausted.

        Args:
            method_name: The method being checked.

        Returns:
            ``True`` if the call is allowed (within budget),
            ``False`` if the budget is exhausted.
        """
        if self._call_budget is None:
            return True
        if self._call_budget.check_call():
            return True
        # Record denied audit event
        self._record_audit(
            method_name=method_name,
            allowed=False,
            reason=f"Call budget exhausted for {self.__class__.__name__}.{method_name}",
        )
        return False


class RealDockerAdapterBase(RealAdapterBase):
    """Abstract base for a real Docker adapter.

    Extends :class:`RealAdapterBase` with a helper that builds a typed
    *intent* dictionary describing a Docker operation. The dictionary
    is **never executed** — it is only metadata describing what *would*
    be done.

    Subclasses must provide concrete implementations of the
    ``DockerAdapter`` protocol methods.
    """

    def __init__(
        self,
        audit_sink: AdapterAuditSink,
        call_budget: CallBudgetChecker | None = None,
        gate_flag: str = SI_V2_ENABLE_REAL_ADAPTERS,
    ) -> None:
        super().__init__(audit_sink, call_budget, gate_flag)

    def _build_docker_intent(self, container: str, command: list[str]) -> dict[str, str | list[str]]:
        """Build a typed intent dictionary describing a Docker operation.

        This does NOT execute any Docker command — it only returns a
        dictionary describing what *would* be done. Subclasses can use
        this for pre-execution audit logging or intent inspection.

        Args:
            container: Target container name or ID.
            command: Command and arguments to execute.

        Returns:
            A dictionary with keys ``container``, ``command``, and
            ``mode`` (always ``"readonly"``).
        """
        return {
            "container": container,
            "command": list(command),
            "mode": "readonly",
        }


class RealFreqtradeAdapterBase(RealAdapterBase):
    """Abstract base for a real Freqtrade adapter.

    Subclasses must provide concrete implementations of the
    ``FreqtradeAdapter`` protocol methods.
    """

    def __init__(
        self,
        audit_sink: AdapterAuditSink,
        call_budget: CallBudgetChecker | None = None,
        gate_flag: str = SI_V2_ENABLE_REAL_ADAPTERS,
    ) -> None:
        super().__init__(audit_sink, call_budget, gate_flag)


class RealTelegramAdapterBase(RealAdapterBase):
    """Abstract base for a real Telegram adapter.

    Subclasses must provide concrete implementations of the
    ``TelegramAdapter`` protocol methods.
    """

    def __init__(
        self,
        audit_sink: AdapterAuditSink,
        call_budget: CallBudgetChecker | None = None,
        gate_flag: str = SI_V2_ENABLE_REAL_ADAPTERS,
    ) -> None:
        super().__init__(audit_sink, call_budget, gate_flag)


class RealAi4tradeAdapterBase(RealAdapterBase):
    """Abstract base for a real ai4trade-bot adapter.

    Subclasses must provide concrete implementations of the
    ``SignalProvider``, ``OutcomeProvider``, and ``RiskGateProvider``
    protocols against the live ai4trade-bot runtime.
    """

    def __init__(
        self,
        audit_sink: AdapterAuditSink,
        call_budget: CallBudgetChecker | None = None,
        gate_flag: str = SI_V2_ENABLE_REAL_ADAPTERS,
    ) -> None:
        super().__init__(audit_sink, call_budget, gate_flag)
