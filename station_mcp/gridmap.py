"""Pixel -> joint-vector mapping for the reliable (grid) track.

This replaces Stage-2 IK entirely. Instead of pixel -> 3D pose -> inverse
kinematics, we teach a set of {top-cam pixel -> joint vector} samples by
hand-posing the arm (see `calibrate.py`), then interpolate at run time. The
brain Claude's own vision supplies the object's pixel; this module turns that
pixel into joints. The top camera supplies XY only — height (Z) is baked into
the taught grasp poses, so the camera's slight tilt never has to be modelled.

Key design points (see docs / the plan):
  - Taught points are hand-posed, so their pixels are NOT an axis-aligned
    lattice. We use inverse-distance weighting (IDW), which is robust to an
    irregular layout, needs no SciPy, and returns a taught sample verbatim on an
    exact hit.
  - Each grid point stores a `grasp` joint vector plus a `hover_delta`
    (hover_joints - grasp_joints). `grasp` and `hover_delta` are interpolated
    with the SAME weights, so hover = interp(grasp) + interp(hover_delta). This
    guarantees the hover->grasp descent is just the (near-vertical) delta and is
    monotonic by construction — no sideways drift on final approach.
  - `extrapolated` is flagged (not refused) when a query falls outside the
    convex hull of taught points, so the caller can ask the user to move the
    object inward instead of trusting a wild extrapolation.
"""
from __future__ import annotations

import json
import os

ARM_DEFAULT_IDS = [1, 2, 3, 4, 5, 6, 7]


def _to_int_joints(d: dict) -> dict[int, int]:
    """JSON object keys are strings; normalize to {int motor_id: int step}."""
    return {int(k): int(round(float(v))) for k, v in d.items()}


def load_waypoints(path: str) -> dict | None:
    """Load and lightly validate waypoints.json. Returns None if the file is absent."""
    if not path or not os.path.exists(path):
        return None
    with open(path) as f:
        return json.load(f)


def default_waypoints_path() -> str:
    """Env override (WAYPOINTS_PATH) else waypoints.json next to this module."""
    env = os.environ.get("WAYPOINTS_PATH", "").strip()
    if env:
        return env
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "waypoints.json")


# ----------------------------- geometry helpers -----------------------------
def _convex_hull(points: list[tuple[float, float]]) -> list[tuple[float, float]]:
    """Andrew's monotone chain. Returns hull vertices CCW. Dependency-free."""
    pts = sorted(set(points))
    if len(pts) <= 2:
        return pts

    def cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    lower = []
    for p in pts:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], p) <= 0:
            lower.pop()
        lower.append(p)
    upper = []
    for p in reversed(pts):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], p) <= 0:
            upper.pop()
        upper.append(p)
    return lower[:-1] + upper[:-1]


def _point_in_hull(px: float, py: float, hull: list[tuple[float, float]]) -> bool:
    """True if (px,py) is inside/on the CCW convex polygon `hull`."""
    n = len(hull)
    if n < 3:
        return False
    for i in range(n):
        ax, ay = hull[i]
        bx, by = hull[(i + 1) % n]
        # CCW hull: point must be left of / on every edge.
        if (bx - ax) * (py - ay) - (by - ay) * (px - ax) < -1e-9:
            return False
    return True


# ----------------------------- grid map -----------------------------
class GridMap:
    """Interpolates taught {pixel -> joints} samples into joint targets."""

    def __init__(self, wp: dict, power: float = 2.0):
        self.wp = wp
        self.power = power
        self.arm_ids: list[int] = wp.get("arm_motor_ids", ARM_DEFAULT_IDS)

        self._pixels: list[tuple[float, float]] = []
        self._grasp: list[dict[int, int]] = []
        self._hover_delta: list[dict[int, int]] = []
        for g in wp.get("grid", []):
            if g.get("pixel") is None:
                continue  # not yet pixel-clicked
            self._pixels.append((float(g["pixel"][0]), float(g["pixel"][1])))
            self._grasp.append(_to_int_joints(g.get("grasp", {})))
            self._hover_delta.append(_to_int_joints(g.get("hover_delta", {})))

        self._hull = _convex_hull(self._pixels) if len(self._pixels) >= 3 else []

    # -- core ----------------------------------------------------------------
    @property
    def ready(self) -> bool:
        return len(self._pixels) >= 3

    def grid_pixels(self) -> list[tuple[float, float]]:
        return list(self._pixels)

    def _weights(self, px: float, py: float) -> list[float] | int:
        """IDW weights, or the index of an exact (<1px) hit."""
        weights = []
        for i, (sx, sy) in enumerate(self._pixels):
            dx, dy = px - sx, py - sy
            d2 = dx * dx + dy * dy
            if d2 < 1.0:
                return i  # exact hit -> return its index
            weights.append(1.0 / (d2 ** (self.power / 2.0)))
        return weights

    def _blend(self, samples: list[dict[int, int]], weights) -> dict[int, int]:
        if isinstance(weights, int):  # exact hit
            return dict(samples[weights])
        acc: dict[int, float] = {}
        wsum: dict[int, float] = {}
        for w, joints in zip(weights, samples):
            for mid, val in joints.items():
                acc[mid] = acc.get(mid, 0.0) + w * val
                wsum[mid] = wsum.get(mid, 0.0) + w
        return {mid: int(round(acc[mid] / wsum[mid])) for mid in acc if wsum[mid] > 0}

    def interp(self, px: float, py: float, height: str = "hover") -> tuple[dict[int, int], bool]:
        """Joint vector at pixel (px,py). height in {"hover","grasp"}.

        Returns (joints, extrapolated). `extrapolated` is True when the query
        lies outside the convex hull of taught points (the result is still
        returned — caller decides whether to act).
        """
        if not self.ready:
            raise ValueError("grid not calibrated — need >=3 pixel-clicked points (run calibrate.py)")
        if height not in ("hover", "grasp"):
            raise ValueError(f"height must be 'hover' or 'grasp', got {height!r}")

        weights = self._weights(px, py)
        grasp = self._blend(self._grasp, weights)
        if height == "grasp":
            joints = grasp
        else:
            delta = self._blend(self._hover_delta, weights)
            joints = {mid: grasp[mid] + delta.get(mid, 0) for mid in grasp}

        extrapolated = not _point_in_hull(px, py, self._hull)
        return joints, extrapolated

    # -- taught fixed poses / params -----------------------------------------
    def grasp_offset(self, object_class: str | None) -> dict[int, int]:
        """Per-object-class vertical offset applied at grasp (closed vocabulary)."""
        if not object_class:
            return {}
        offsets = self.wp.get("grasp_offsets", {})
        return _to_int_joints(offsets.get(object_class, {}))

    def home(self) -> dict[int, int]:
        return _to_int_joints(self.wp.get("home", {}))

    def drop_zone(self, height: str = "hover") -> dict[int, int]:
        dz = self.wp.get("drop_zone", {})
        return _to_int_joints(dz.get(height, {}))

    def nudge_step_px(self) -> int:
        return int(self.wp.get("nudge", {}).get("default_step_px", 25))

    def gripper(self) -> dict:
        return self.wp.get("gripper", {})
