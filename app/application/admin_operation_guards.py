from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from app.application.admin_capabilities import AdminCapabilityPolicy, AdminPermission


class GuardCode(StrEnum):
    ALLOWED = "allowed"
    UNAUTHORIZED = "unauthorized"
    SESSION_REQUIRED = "session_required"
    CONFIRMATION_REQUIRED = "confirmation_required"
    KILL_SWITCH_ACTIVE = "kill_switch_active"
    INVALID_OPERATION_STATE = "invalid_operation_state"
    OWNERSHIP_REQUIRED = "ownership_required"
    TWO_MAN_REQUIRED = "two_man_required"


@dataclass(frozen=True, slots=True)
class OperationGuardContext:
    actor_type: str
    permission: AdminPermission | str
    emergency_mode: bool = False
    sensitive_operation: bool = True
    recent_session_valid: bool = False
    confirmation_valid: bool = False
    kill_switch_active: bool = False
    state_allowed: bool = True
    ownership_allowed: bool = True
    two_man_required: bool = False
    second_admin_confirmed: bool = False


@dataclass(frozen=True, slots=True)
class GuardDecision:
    allowed: bool
    code: GuardCode


class AdminOperationGuard:
    """Central precondition evaluator; it does not mutate state or authorize identity."""

    def __init__(self, policy: AdminCapabilityPolicy | None = None) -> None:
        self._policy = policy or AdminCapabilityPolicy()

    def check(self, context: OperationGuardContext) -> GuardDecision:
        if not self._policy.allows(
            context.actor_type,
            context.permission,
            emergency_mode=context.emergency_mode,
        ):
            return GuardDecision(False, GuardCode.UNAUTHORIZED)
        if context.sensitive_operation and not context.recent_session_valid:
            return GuardDecision(False, GuardCode.SESSION_REQUIRED)
        if context.sensitive_operation and not context.confirmation_valid:
            return GuardDecision(False, GuardCode.CONFIRMATION_REQUIRED)
        if context.kill_switch_active:
            return GuardDecision(False, GuardCode.KILL_SWITCH_ACTIVE)
        if not context.state_allowed:
            return GuardDecision(False, GuardCode.INVALID_OPERATION_STATE)
        if not context.ownership_allowed:
            return GuardDecision(False, GuardCode.OWNERSHIP_REQUIRED)
        if context.two_man_required and not context.second_admin_confirmed:
            return GuardDecision(False, GuardCode.TWO_MAN_REQUIRED)
        return GuardDecision(True, GuardCode.ALLOWED)
