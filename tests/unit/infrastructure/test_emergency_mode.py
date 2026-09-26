import pytest

from app.infrastructure.emergency_mode import EmergencyModeConfig


@pytest.mark.parametrize("value", ["1", "true", "TRUE", "on", "On"])
def test_emergency_mode_accepts_enabled_values(value):
    assert EmergencyModeConfig.from_environment({"AL_MANARA_EMERGENCY_MODE": value}).enabled is True


@pytest.mark.parametrize("value", ["", "0", "false", "FALSE", "off", "Off"])
def test_emergency_mode_defaults_disabled(value):
    assert EmergencyModeConfig.from_environment({"AL_MANARA_EMERGENCY_MODE": value}).enabled is False


def test_emergency_mode_rejects_ambiguous_value():
    with pytest.raises(RuntimeError):
        EmergencyModeConfig.from_environment({"AL_MANARA_EMERGENCY_MODE": "yes"})
