"""Framework-free geo helpers shared across modules."""

from __future__ import annotations

from restaurante.shared.geo.simplify import douglas_peucker_indices, simplify

__all__ = ["douglas_peucker_indices", "simplify"]
