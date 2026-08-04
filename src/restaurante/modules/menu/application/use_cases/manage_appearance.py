"""Application service for the public-carta appearance config.

The config is a single JSONB document per tenant mirroring the frontend
``MenuAppearanceConfig`` contract (camelCase keys — the storefront reads the same
object the admin editor writes). Validation of the shape happens at the API layer
(Pydantic → 422); this service only decides "saved-or-default" and upserts.
"""

from __future__ import annotations

import uuid
from typing import Any

from restaurante.modules.menu.domain.ports import MenuRepository


def _block(
    block_id: str, visible: bool, x: int, y: int, size: str
) -> dict[str, Any]:
    return {"id": block_id, "visible": visible, "position": {"x": x, "y": y}, "size": size}


def default_appearance_config() -> dict[str, Any]:
    """Computed default returned when a tenant has never saved an appearance.

    Mirrors the frontend defaults (``lib/menuAppearance.ts`` DEFAULT_THEME /
    DEFAULT_DISH_CARD / DEFAULT_DISH_DETAIL and the seeded block layout + content in
    ``mock/menuAppearance.ts``): the 4 presentation blocks (promo/hours/gallery/
    testimonials) start hidden for the admin to place. camelCase to match the
    persisted contract.
    """
    return {
        "theme": {
            "primaryColor": "#c0392b",
            "secondaryColor": "#e67e22",
            "backgroundColor": "#fbf7f0",
            "textColor": "#2a2320",
            "accentColor": "#1e8449",
            "fontFamily": "Poppins",
        },
        "brand": {
            "logoUrl": "",
            "bannerUrl": "",
            "restaurantName": "",
        },
        "blocks": [
            _block("banner", True, 0, 0, "large"),
            _block("featured_categories", True, 2, 0, "medium"),
            _block("search", True, 2, 1, "medium"),
            _block("full_menu", True, 0, 2, "large"),
            _block("footer", True, 2, 2, "medium"),
            _block("promo", False, 0, 0, "medium"),
            _block("hours", False, 0, 0, "small"),
            _block("gallery", False, 0, 0, "large"),
            _block("testimonials", False, 0, 0, "medium"),
        ],
        "dishCard": {
            "style": "card",
            "show": {
                "image": True,
                "description": True,
                "price": True,
                "addonHint": True,
                "removableHint": False,
            },
        },
        "dishDetail": {
            "sections": [
                {"id": "photo", "visible": True},
                {"id": "description", "visible": True},
                {"id": "variants", "visible": True},
                {"id": "addons", "visible": True},
                {"id": "remove", "visible": True},
                {"id": "note", "visible": True},
            ],
        },
        "blockContent": {
            "promo": {
                "title": "Plato del día",
                "body": "Cazuela de mariscos con arroz de coco — solo hoy.",
                "imageUrl": "",
            },
            "hours": {
                "rows": [
                    {"label": "Lun–Jue", "value": "11:00 – 21:00"},
                    {"label": "Vie–Sáb", "value": "11:00 – 23:00"},
                    {"label": "Dom", "value": "11:00 – 18:00"},
                ],
            },
            "testimonials": {
                "items": [
                    {"author": "María P.", "quote": "El mejor ceviche de Riohacha, sin discusión."},
                    {"author": "Andrés G.", "quote": "Porciones generosas y todo bien fresco."},
                ],
            },
            "gallery": {"imageUrls": []},
        },
    }


class AppearanceService:
    def __init__(self, repo: MenuRepository) -> None:
        self._repo = repo

    async def get_appearance(self, tenant_id: uuid.UUID) -> dict[str, Any]:
        """The tenant's saved config, or the computed default when none exists."""
        saved = await self._repo.get_appearance(tenant_id)
        return saved if saved is not None else default_appearance_config()

    async def save_appearance(
        self, tenant_id: uuid.UUID, config: dict[str, Any]
    ) -> dict[str, Any]:
        """Persist (insert or overwrite) the validated config and return it."""
        return await self._repo.upsert_appearance(tenant_id, config)
