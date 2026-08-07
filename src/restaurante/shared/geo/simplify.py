"""Douglas–Peucker polyline simplification (pure, framework-free).

Used to bound a driver's trail before it is sent to the dispatcher: a long shift's
breadcrumb collapses to the few points that actually change direction, while the
endpoints (start and current position) are always kept. Distances are computed on raw
lat/lng degrees — a planar approximation that is more than accurate enough over a single
city, where the trail lives.
"""

from __future__ import annotations

import math
from collections.abc import Sequence

Point = tuple[float, float]


def _perpendicular_distance(point: Point, start: Point, end: Point) -> float:
    """Distance from `point` to the segment start–end (degenerate segment → point dist)."""
    (px, py), (sx, sy), (ex, ey) = point, start, end
    dx, dy = ex - sx, ey - sy
    if dx == 0.0 and dy == 0.0:
        return math.hypot(px - sx, py - sy)
    # Twice the triangle area over the base length = the perpendicular height.
    numerator = abs(dy * px - dx * py + ex * sy - ey * sx)
    return numerator / math.hypot(dx, dy)


def douglas_peucker_indices(points: Sequence[Point], epsilon: float) -> list[int]:
    """Indices of the points kept by Douglas–Peucker at tolerance `epsilon` (ascending).

    Always keeps the first and last index. A run of collinear points (a straight line)
    collapses to just those two, since every interior point has perpendicular distance 0.
    """
    n = len(points)
    if n <= 2:
        return list(range(n))

    keep = [False] * n
    keep[0] = keep[n - 1] = True
    stack: list[tuple[int, int]] = [(0, n - 1)]
    while stack:
        start, end = stack.pop()
        dmax, index = 0.0, -1
        for i in range(start + 1, end):
            dist = _perpendicular_distance(points[i], points[start], points[end])
            if dist > dmax:
                dmax, index = dist, i
        if dmax > epsilon and index != -1:
            keep[index] = True
            stack.append((start, index))
            stack.append((index, end))
    return [i for i in range(n) if keep[i]]


def simplify(points: Sequence[Point], epsilon: float) -> list[Point]:
    """The subset of `points` kept by Douglas–Peucker at tolerance `epsilon` (in order)."""
    return [points[i] for i in douglas_peucker_indices(points, epsilon)]
