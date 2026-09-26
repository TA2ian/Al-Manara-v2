import pytest

from app.application.admin_capabilities import AdminActorType, AdminCapabilityPolicy, AdminPermission
from app.application.admin_operation_guards import (
    AdminOperationGuard,
    GuardCode,
    OperationGuardContext,
)


@pytest.fixture
def policy():
    return AdminCapabilityPolicy()


def test_primary_has_full_fixed_capability_set(policy):
    assert policy.allows(AdminActorType.PRIMARY, AdminPermission.ADMIN_MANAGE)
    assert policy.allows(AdminActorType.PRIMARY, AdminPermission.GUARD_FULFILLMENT_KILL_SWITCH)
    assert policy.allows(AdminActorType.PRIMARY, AdminPermission.PAYMENT_CONFIRM)


def test_backup_is_limited_in_normal_mode(policy):
    assert policy.allows(AdminActorType.BACKUP, AdminPermission.ORDER_CANCEL)
    assert policy.allows(AdminActorType.BACKUP, AdminPermission.FULFILLMENT_COMPLETE)
    assert not policy.allows(AdminActorType.BACKUP, AdminPermission.PAYMENT_CONFIRM)
    assert not policy.allows(AdminActorType.BACKUP, AdminPermission.ADMIN_MANAGE)


def test_backup_expands_in_emergency_but_cannot_manage_admin(policy):
    assert policy.allows(AdminActorType.BACKUP, AdminPermission.PAYMENT_CONFIRM, emergency_mode=True)
    assert policy.allows(AdminActorType.BACKUP, AdminPermission.GUARD_FULFILLMENT_KILL_SWITCH, emergency_mode=True)
    assert not policy.allows(AdminActorType.BACKUP, AdminPermission.ADMIN_MANAGE, emergency_mode=True)


def test_invalid_actor_or_permission_fails_closed(policy):
    assert not policy.allows("unknown", AdminPermission.ORDER_VIEW)
    assert not policy.allows(AdminActorType.PRIMARY, "admin.nonexistent")


def test_sensitive_operation_requires_recent_session_and_confirmation(policy):
    guard = AdminOperationGuard(policy)
    base = dict(
        actor_type="primary",
        permission=AdminPermission.ORDER_CANCEL,
        sensitive_operation=True,
    )
    assert guard.check(OperationGuardContext(**base)).code == GuardCode.SESSION_REQUIRED
    assert guard.check(OperationGuardContext(**base, recent_session_valid=True)).code == GuardCode.CONFIRMATION_REQUIRED
    assert guard.check(
        OperationGuardContext(**base, recent_session_valid=True, confirmation_valid=True)
    ).allowed


def test_non_sensitive_read_can_pass_without_session(policy):
    guard = AdminOperationGuard(policy)
    decision = guard.check(
        OperationGuardContext(
            actor_type="backup",
            permission=AdminPermission.ORDER_VIEW,
            sensitive_operation=False,
        )
    )
    assert decision.allowed


def test_kill_switch_state_and_ownership_remain_independent(policy):
    guard = AdminOperationGuard(policy)
    kwargs = dict(
        actor_type="primary",
        permission=AdminPermission.ORDER_CANCEL,
        recent_session_valid=True,
        confirmation_valid=True,
    )
    assert guard.check(OperationGuardContext(**kwargs, kill_switch_active=True)).code == GuardCode.KILL_SWITCH_ACTIVE
    assert guard.check(OperationGuardContext(**kwargs, state_allowed=False)).code == GuardCode.INVALID_OPERATION_STATE
    assert guard.check(OperationGuardContext(**kwargs, ownership_allowed=False)).code == GuardCode.OWNERSHIP_REQUIRED


def test_two_man_rule_cannot_be_bypassed_by_first_admin(policy):
    guard = AdminOperationGuard(policy)
    decision = guard.check(
        OperationGuardContext(
            actor_type="primary",
            permission=AdminPermission.PAYMENT_REFUND_REQUIRED,
            recent_session_valid=True,
            confirmation_valid=True,
            two_man_required=True,
        )
    )
    assert decision.code == GuardCode.TWO_MAN_REQUIRED

    approved = guard.check(
        OperationGuardContext(
            actor_type="primary",
            permission=AdminPermission.PAYMENT_REFUND_REQUIRED,
            recent_session_valid=True,
            confirmation_valid=True,
            two_man_required=True,
            second_admin_confirmed=True,
        )
    )
    assert approved.allowed
