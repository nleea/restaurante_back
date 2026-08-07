"""Dónde vive la API dentro del dominio: bajo `/api`, no en la raíz.

No es cosmético y no es configurable a propósito. El tenant se resuelve por el subdominio
del Host (`<slug>.<BASE_DOMAIN>`), así que el front de un tenant y su API **tienen que
compartir hostname** — y compartir hostname sin prefijo es imposible: catorce rutas del SPA
(`/menu`, `/orders`, `/inventory`, `/cash`, …) se llaman igual que catorce prefijos de la
API. Con `/api` delante, un solo nombre sirve las dos cosas, sin CORS y con un solo
certificado.

Configurable sería peor: el prefijo aparece en la URL del webhook que registramos en el
puente de WhatsApp y en el enlace de la carta. Dos despliegues con prefijos distintos serían
dos contratos distintos hacia fuera.
"""

from __future__ import annotations

API_PREFIX = "/api"


def api_path(path: str) -> str:
    """`/health` → `/api/health`. Para componer rutas absolutas sin repetir el prefijo."""
    return f"{API_PREFIX}{path}"
