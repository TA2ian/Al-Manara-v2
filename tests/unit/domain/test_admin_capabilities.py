from app.domain.admin_capabilities import (
    ALWAYS_FORBIDDEN_IN_EMERGENCY,
    AdminActorType,
    AdminCapability,
    AdminMode,
    capabilities_for,
    has_capability,
    is_emergency_capability,
)


def test_primary_has_full_fixed_capability_set_in_normal_mode() -> None:
    capabilities = capabilities_for(AdminActorType.PRIMARY, AdminMode.NORMAL)

    assert capabilities == frozenset(AdminCapability)


def test_primary_remains_full_in_emergency_mode() -> None:
    assert capabilities_for(AdminActorType.PRIMARY, AdminMode.EMERGENCY) == frozenset(
        AdminCapability
    )


def test_backup_normal_is_limited() -> None:
    assert not has_capability(
        AdminActorType.BACKUP,
        AdminMode.NORMAL,
        AdminCapability.CANCEL_ORDER,
    )
    assert not has_capability(
        AdminActorType.BACKUP,
        AdminMode.NORMAL,
        AdminCapability.PAYMENT_CONFIRM,
    )
    assert not has_capability(
        AdminActorType.BACKUP,
        AdminMode.NORMAL,
        AdminCapability.FULFILLMENT_KILL_SWITCH,
    )
    assert has_capability(
        AdminActorType.BACKUP,
        AdminMode.NORMAL,
        AdminCapability.HOLD_ORDER,
    )
    assert has_capability(
        AdminActorType.BACKUP,
        AdminMode.NORMAL,
        AdminCapability.COMPLETE_FULFILLMENT,
    )


def test_backup_emergency_expands_only_the_defined_operational_scope() -> None:
    emergency = capabilities_for(AdminActorType.BACKUP, AdminMode.EMERGENCY)
    normal = capabilities_for(AdminActorType.BACKUP, AdminMode.NORMAL)

    assert normal < emergency
    assert AdminCapability.CANCEL_ORDER in emergency
    assert AdminCapability.FORCE_EXPIRE_ORDER in emergency
    assert AdminCapability.FREEZE_USER in emergency
    assert AdminCapability.PAYMENT_CONFIRM in emergency
    assert AdminCapability.REFUND_WORKFLOW in emergency
    assert AdminCapability.CUSTOMER_COMPENSATION in emergency
    assert AdminCapability.FULFILLMENT_KILL_SWITCH in emergency


def test_emergency_expansion_is_explicitly_identifiable() -> None:
    assert is_emergency_capability(AdminCapability.CANCEL_ORDER)
    assert is_emergency_capability(AdminCapability.PAYMENT_CONFIRM)
    assert not is_emergency_capability(AdminCapability.HOLD_ORDER)


def test_security_invariants_are_not_capabilities() -> None:
    capabilities = capabilities_for(AdminActorType.BACKUP, AdminMode.EMERGENCY)

    assert not ALWAYS_FORBIDDEN_IN_EMERGENCY.intersection(capabilities)
    assert "fulfillment.force_complete" in ALWAYS_FORBIDDEN_IN_EMERGENCY
    assert "blockchain.verification.bypass" in ALWAYS_FORBIDDEN_IN_EMERGENCY
    assert "admin.permissions.change" in ALWAYS_FORBIDDEN_IN_EMERGENCY
    assert "audit.delete" in ALWAYS_FORBIDDEN_IN_EMERGENCY
