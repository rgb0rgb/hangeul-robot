"""Validate recovery evidence; receiving a command is not recovery success."""
from __future__ import annotations


def fault_errors(result: dict, enabled_joints: list[str]) -> list[str]:
    errors = []
    for key, value in result.items():
        if value and (key.endswith("_failed") or key in ("error", "link_reopen_skipped")):
            errors.append(f"{key}: {value}")
        if isinstance(value, dict) and "hardware_error_before" in value:
            for field in ("read_before_error", "read_after_error", "reboot_error"):
                if value.get(field):
                    errors.append(f"J{key} {field}: {value[field]}")
            before, after = value.get("hardware_error_before"), value.get("hardware_error_after")
            if before is None:
                errors.append(f"J{key}: hardware error status unknown")
            if after not in (None, 0) or (before and after is None):
                errors.append(f"J{key}: hardware error remains ({after})")
            if before and (value.get("rebooted") is not True or value.get("reboot_packet_error", 0)):
                errors.append(f"J{key}: REBOOT was not acknowledged")
    after = result.get("error_information_after", result.get("error_information_before", 0))
    if after not in (0, [], {}):
        errors.append(f"controller error: {after}")
    dead = set(map(str, result.get("servo_not_responding") or [])) & set(enabled_joints)
    if dead:
        errors.append("servos not responding: " + ", ".join(sorted(dead)))
    if result.get("link_recovered") is False:
        errors.append("serial connection was not recovered")
    return errors


def hold_verified(result) -> bool:
    if not isinstance(result, dict):
        return False
    if any(result.get(key) is False for key in ("success", "settled", "result_ok", "sent")):
        return False
    if result.get("canceled") or result.get("timed_out") or result.get("error"):
        return False
    return any(result.get(key) is True for key in ("success", "settled", "result_ok"))
