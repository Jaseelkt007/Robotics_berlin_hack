"""Quick sanity tests for gridmap.py — pure logic, no hardware. Run: python test_gridmap.py"""
from gridmap import GridMap, _convex_hull, _point_in_hull

# A 2x2 grid over a 600x400 frame. grasp joints vary with x (motor 1) and y (motor 2);
# hover_delta lifts motor 3 by 150 everywhere.
WP = {
    "arm_motor_ids": [1, 2, 3],
    "gripper": {"open_step": 1200, "closed_step": 2400, "grasp_current_threshold_ma": 250},
    "grasp_offsets": {"box": {"3": 30}, "bottle": {"3": -120}},
    "home": {"1": 2048, "2": 2048, "3": 2048},
    "drop_zone": {"hover": {"1": 1600, "2": 1900, "3": 2200}, "grasp": {"1": 1600, "2": 1900, "3": 2050}},
    "nudge": {"default_step_px": 25},
    "grid": [
        {"id": "a", "pixel": [100, 100], "grasp": {"1": 1500, "2": 1700, "3": 2400}, "hover_delta": {"3": -150}},
        {"id": "b", "pixel": [500, 100], "grasp": {"1": 2500, "2": 1700, "3": 2400}, "hover_delta": {"3": -150}},
        {"id": "c", "pixel": [100, 300], "grasp": {"1": 1500, "2": 2300, "3": 2400}, "hover_delta": {"3": -150}},
        {"id": "d", "pixel": [500, 300], "grasp": {"1": 2500, "2": 2300, "3": 2400}, "hover_delta": {"3": -150}},
    ],
}


def almost(a, b, tol=2):
    assert abs(a - b) <= tol, f"{a} != {b} (tol {tol})"


def main():
    gm = GridMap(WP)
    assert gm.ready

    # 1) exact hit returns the taught sample verbatim (grasp height)
    j, ext = gm.interp(100, 100, "grasp")
    assert j == {1: 1500, 2: 1700, 3: 2400}, j
    assert ext is False

    # 2) center interpolates to the mean of the four corners
    j, ext = gm.interp(300, 200, "grasp")
    almost(j[1], 2000)   # mean of 1500/2500
    almost(j[2], 2000)   # mean of 1700/2300
    almost(j[3], 2400)
    assert ext is False

    # 3) hover = grasp + hover_delta (motor 3 lifted by -150)
    jg, _ = gm.interp(300, 200, "grasp")
    jh, _ = gm.interp(300, 200, "hover")
    almost(jh[3], jg[3] - 150)
    almost(jh[1], jg[1])  # motors without a delta are unchanged

    # 4) extrapolation flag fires outside the hull
    _, ext = gm.interp(590, 390, "grasp")
    assert ext is True, "point outside the 4-corner hull should be extrapolated"
    _, ext = gm.interp(300, 200, "grasp")
    assert ext is False

    # 5) per-class grasp offset
    assert gm.grasp_offset("box") == {3: 30}
    assert gm.grasp_offset("bottle") == {3: -120}
    assert gm.grasp_offset(None) == {}
    assert gm.grasp_offset("unknown") == {}

    # 6) fixed-pose accessors
    assert gm.home() == {1: 2048, 2: 2048, 3: 2048}
    assert gm.drop_zone("hover") == {1: 1600, 2: 1900, 3: 2200}
    assert gm.nudge_step_px() == 25

    # 7) hull helpers directly
    hull = _convex_hull([(0, 0), (4, 0), (4, 4), (0, 4), (2, 2)])
    assert _point_in_hull(2, 2, hull) is True
    assert _point_in_hull(5, 5, hull) is False

    print("all gridmap tests passed")


if __name__ == "__main__":
    main()
