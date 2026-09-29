from __future__ import annotations

from enum import StrEnum


class AdminActorType(StrEnum):
    PRIMARY = "primary"
    BACKUP = "backup"


class AdminMode(StrEnum):
    NORMAL = "normal"
    EMERGENCY = "emergency"


class AdminCapability(StrEnum):
    VIEW_ORDERS = "order.view"
    VIEW_CUSTOMERS = "customer.view"
    REVIEW_IDENTITY = "identity.review"
    REVIEW_RECEIPT = "payment.receipt.review"
    REQUEST_RECHECK = "payment.recheck"
    CLAIM_FULFILLMENT = "fulfillment.claim"
    COMPLETE_FULFILLMENT = "fulfillment.complete"
    HOLD_ORDER = "order.hold"
    QUARANTINE_ORDER = "order.quarantine"
    CANCEL_ORDER = "order.cancel"
    FORCE_EXPIRE_ORDER = "order.force_expire"
    FREEZE_USER = "customer.freeze"
    UNFREEZE_USER = "customer.unfreeze"
    PAYMENT_INVESTIGATE = "payment.investigate"
    PAYMENT_CONFIRM = "payment.confirm"
    PAYMENT_REJECT = "payment.reject"
    REFUND_REQUIRED = "payment.refund_required"
    REFUND_WORKFLOW = "payment.refund"
    RECOVERY = "recovery.execute"
    CUSTOMER_COMPENSATION = "customer.compensate"
    INCIDENT_CREATE = "incident.create"
    INCIDENT_MANAGE = "incident.manage"
    FULFILLMENT_INCIDENT = "fulfillment.incident"
    NEW_ORDERS_KILL_SWITCH = "guard.new_orders_kill_switch"
    PAYMENT_CONFIRMATION_KILL_SWITCH = "guard.payment_confirmation_kill_switch"
    FULFILLMENT_KILL_SWITCH = "guard.fulfillment_kill_switch"
    EMERGENCY_ACTIVATE = "guard.emergency.activate"
    EMERGENCY_DEACTIVATE = "guard.emergency.deactivate"


# Permissions are deliberately fixed in source code. They are not user-configurable
# and must be checked before every sensitive operation.
_PRIMARY_CAPABILITIES = frozenset(AdminCapability)

_BACKUP_NORMAL_CAPABILITIES = frozenset(
    {
        AdminCapability.VIEW_ORDERS,
        AdminCapability.VIEW_CUSTOMERS,
        AdminCapability.REVIEW_IDENTITY,
        AdminCapability.REVIEW_RECEIPT,
        AdminCapability.REQUEST_RECHECK,
        AdminCapability.CLAIM_FULFILLMENT,
        AdminCapability.COMPLETE_FULFILLMENT,
        AdminCapability.HOLD_ORDER,
        AdminCapability.QUARANTINE_ORDER,
        AdminCapability.PAYMENT_INVESTIGATE,
        AdminCapability.PAYMENT_REJECT,
        AdminCapability.REFUND_REQUIRED,
        AdminCapability.RECOVERY,
        AdminCapability.INCIDENT_CREATE,
        AdminCapability.INCIDENT_MANAGE,
        AdminCapability.FULFILLMENT_INCIDENT,
        AdminCapability.EMERGENCY_ACTIVATE,
        AdminCapability.EMERGENCY_DEACTIVATE,
    }
)

_BACKUP_EMERGENCY_CAPABILITIES = frozenset(
    {
        *(_BACKUP_NORMAL_CAPABILITIES),
        AdminCapability.CANCEL_ORDER,
        AdminCapability.FORCE_EXPIRE_ORDER,
        AdminCapability.FREEZE_USER,
        AdminCapability.UNFREEZE_USER,
        AdminCapability.PAYMENT_CONFIRM,
        AdminCapability.REFUND_WORKFLOW,
        AdminCapability.CUSTOMER_COMPENSATION,
        AdminCapability.NEW_ORDERS_KILL_SWITCH,
        AdminCapability.PAYMENT_CONFIRMATION_KILL_SWITCH,
        AdminCapability.FULFILLMENT_KILL_SWITCH,
    }
)

# These are security invariants, not permissions. They cannot be granted by
# Emergency Mode and therefore intentionally do not appear in any capability set.
ALWAYS_FORBIDDEN_IN_EMERGENCY = frozenset(
    {
        "admin.identity.change",
        "admin.permissions.change",
        "secrets.change",
        "blockchain.verification.bypass",
        "fulfillment.force_complete",
        "fulfillment.ownership.bypass",
        "audit.delete",
        "two_man_rule.bypass",
    }
)


def capabilities_for(actor_type: AdminActorType, mode: AdminMode) -> frozenset[AdminCapability]:
    if actor_type is AdminActorType.PRIMARY:
        return _PRIMARY_CAPABILITIES
    if actor_type is AdminActorType.BACKUP and mode is AdminMode.EMERGENCY:
        return _BACKUP_EMERGENCY_CAPABILITIES
    if actor_type is AdminActorType.BACKUP and mode is AdminMode.NORMAL:
        return _BACKUP_NORMAL_CAPABILITIES
    raise ValueError("unsupported admin actor type or mode")


def has_capability(
    actor_type: AdminActorType,
    mode: AdminMode,
    capability: AdminCapability,
) -> bool:
    return capability in capabilities_for(actor_type, mode)


def is_emergency_capability(capability: AdminCapability) -> bool:
    return capability in (
        _BACKUP_EMERGENCY_CAPABILITIES - _BACKUP_NORMAL_CAPABILITIES
    )
