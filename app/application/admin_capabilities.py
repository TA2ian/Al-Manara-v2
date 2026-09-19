from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class AdminActorType(StrEnum):
    PRIMARY = "primary"
    BACKUP = "backup"


class AdminPermission(StrEnum):
    ORDER_VIEW = "order.view"
    ORDER_CANCEL = "order.cancel"
    ORDER_HOLD = "order.hold"
    ORDER_FORCE_EXPIRE = "order.force_expire"
    ORDER_QUARANTINE = "order.quarantine"
    ORDER_RECOVER = "order.recover"
    CUSTOMER_VIEW = "customer.view"
    CUSTOMER_FREEZE = "customer.freeze"
    CUSTOMER_UNFREEZE = "customer.unfreeze"
    CUSTOMER_RECOVER = "customer.recover"
    CUSTOMER_COMPENSATE = "customer.compensate"
    PAYMENT_VIEW = "payment.view"
    PAYMENT_CONFIRM = "payment.confirm"
    PAYMENT_REJECT = "payment.reject"
    PAYMENT_RECHECK = "payment.recheck"
    PAYMENT_REFUND_REQUIRED = "payment.refund_required"
    FULFILLMENT_VIEW = "fulfillment.view"
    FULFILLMENT_CLAIM = "fulfillment.claim"
    FULFILLMENT_COMPLETE = "fulfillment.complete"
    FULFILLMENT_RECOVER = "fulfillment.recover"
    FULFILLMENT_INCIDENT = "fulfillment.incident"
    GUARD_FULFILLMENT_KILL_SWITCH = "guard.fulfillment_kill_switch"
    GUARD_NEW_ORDERS_KILL_SWITCH = "guard.new_orders_kill_switch"
    GUARD_PAYMENT_CONFIRMATION_KILL_SWITCH = "guard.payment_confirmation_kill_switch"
    INCIDENT_CREATE = "incident.create"
    INCIDENT_VIEW = "incident.view"
    INCIDENT_ASSIGN = "incident.assign"
    INCIDENT_RESOLVE = "incident.resolve"
    INCIDENT_CLOSE = "incident.close"
    ADMIN_VIEW = "admin.view"
    ADMIN_MANAGE = "admin.manage"
    AUDIT_VIEW = "audit.view"
    ADMIN_ACTION_HISTORY_VIEW = "admin_action_history.view"


# Fixed policy: permissions are code-owned, not editable from Telegram or the DB.
# Backup receives the operational subset in normal mode and the expanded subset only
# when Emergency Mode has been authoritatively enabled by a separate guard.
_PRIMARY_PERMISSIONS = frozenset(AdminPermission)
_BACKUP_NORMAL_PERMISSIONS = frozenset(
    {
        AdminPermission.ORDER_VIEW,
        AdminPermission.ORDER_CANCEL,
        AdminPermission.ORDER_HOLD,
        AdminPermission.ORDER_FORCE_EXPIRE,
        AdminPermission.ORDER_QUARANTINE,
        AdminPermission.ORDER_RECOVER,
        AdminPermission.CUSTOMER_VIEW,
        AdminPermission.CUSTOMER_FREEZE,
        AdminPermission.CUSTOMER_UNFREEZE,
        AdminPermission.CUSTOMER_RECOVER,
        AdminPermission.PAYMENT_VIEW,
        AdminPermission.PAYMENT_REJECT,
        AdminPermission.PAYMENT_RECHECK,
        AdminPermission.FULFILLMENT_VIEW,
        AdminPermission.FULFILLMENT_CLAIM,
        AdminPermission.FULFILLMENT_COMPLETE,
        AdminPermission.FULFILLMENT_RECOVER,
        AdminPermission.FULFILLMENT_INCIDENT,
        AdminPermission.INCIDENT_CREATE,
        AdminPermission.INCIDENT_VIEW,
        AdminPermission.INCIDENT_ASSIGN,
        AdminPermission.INCIDENT_RESOLVE,
        AdminPermission.INCIDENT_CLOSE,
        AdminPermission.ADMIN_VIEW,
        AdminPermission.AUDIT_VIEW,
        AdminPermission.ADMIN_ACTION_HISTORY_VIEW,
    }
)
_BACKUP_EMERGENCY_PERMISSIONS = _PRIMARY_PERMISSIONS - {
    AdminPermission.ADMIN_MANAGE,
}


@dataclass(frozen=True, slots=True)
class AdminCapabilityPolicy:
    """Deterministic fixed permission policy for authoritative admin actors."""

    def permissions_for(self, actor_type: str, *, emergency_mode: bool = False) -> frozenset[AdminPermission]:
        normalized = actor_type.strip().lower() if isinstance(actor_type, str) else ""
        if normalized == AdminActorType.PRIMARY:
            return _PRIMARY_PERMISSIONS
        if normalized == AdminActorType.BACKUP:
            return _BACKUP_EMERGENCY_PERMISSIONS if emergency_mode else _BACKUP_NORMAL_PERMISSIONS
        return frozenset()

    def allows(self, actor_type: str, permission: AdminPermission | str, *, emergency_mode: bool = False) -> bool:
        try:
            requested = permission if isinstance(permission, AdminPermission) else AdminPermission(permission)
        except (TypeError, ValueError):
            return False
        return requested in self.permissions_for(actor_type, emergency_mode=emergency_mode)
