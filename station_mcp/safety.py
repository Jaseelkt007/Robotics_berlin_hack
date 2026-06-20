"""Safety layer — clamp motor targets to calibrated ranges before anything reaches the arm.

This is intentionally in the MCP server (not in Claude): the LLM must never write raw values
straight to the motors. Every joint target passes through here.
"""
from __future__ import annotations

ENCODER_MIN = 0
ENCODER_MAX = 4095


def clamp_targets(
    targets: dict[int, int],
    ranges: dict[int, tuple[int, int]] | None = None,
) -> dict[int, int]:
    """Clamp each motor target to its calibrated [min, max] (fallback: full encoder range).

    targets : {motor_id: raw_position}
    ranges  : {motor_id: (range_min, range_max)} from get_state(); optional.
    """
    ranges = ranges or {}
    safe: dict[int, int] = {}
    for motor_id, value in targets.items():
        lo, hi = ranges.get(motor_id, (ENCODER_MIN, ENCODER_MAX))
        if lo > hi:  # wrap-around arc — fall back to full range, log upstream
            lo, hi = ENCODER_MIN, ENCODER_MAX
        safe[motor_id] = max(lo, min(hi, int(value)))
    return safe
