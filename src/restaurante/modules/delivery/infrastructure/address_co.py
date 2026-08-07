"""Colombian address nomenclature, reduced to what a map can actually find.

`Calle 41A #12C-48` reads: on Calle 41A, 48 metres past Carrera 12C. OpenStreetMap holds
Riohacha's street geometry but not its addressed buildings, so the `-48` matches nothing — it
is noise to a geocoder and the whole point to the driver. The house number stays in the stored
address.

What IS queryable is the pair of streets: `Calle 41A` and the cross it is measured from,
`Carrera 12C`. Alone, the cross street is a bad answer — a geocoder returns its representative
point, measured 1.48 km from the address in Riohacha. As the other half of an **intersection**
it is the difference between the right corner and a segment 555 m away.

Framework-free and provider-free on purpose: this is Colombian domain knowledge, not Nominatim
trivia, and it is testable without a network.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# Street types as people actually type them. Longest spellings first so `cll` wins over `cl`
# and `carrera` over `cra` — the regex alternation is first-match, not longest-match.
_CALLE_WORDS = ("calle", "cll", "cl")
_CARRERA_WORDS = ("carrera", "cra", "kra", "krr", "car", "kr", "cr", "k")
_OTHER_WORDS: dict[str, tuple[str, ...]] = {
    "Avenida": ("avenida", "av"),
    "Diagonal": ("diagonal", "diag", "dg"),
    "Transversal": ("transversal", "transv", "tv"),
    "Circular": ("circular", "circ"),
}

_CANON: dict[str, str] = {}
for _w in _CALLE_WORDS:
    _CANON[_w] = "Calle"
for _w in _CARRERA_WORDS:
    _CANON[_w] = "Carrera"
for _canon, _words in _OTHER_WORDS.items():
    for _w in _words:
        _CANON[_w] = _canon

# Longest first, so "calle" is not shadowed by "cl".
_TYPE_ALT = "|".join(sorted(_CANON, key=len, reverse=True))

# A Calle is crossed by Carreras and vice versa. The other types (Avenida, Diagonal,
# Transversal) have no such dual, so their cross street is left unguessed: a wrong street name
# is a missed intersection, and a missed intersection costs a request against a flaky service.
_CROSS_TYPE = {"Calle": "Carrera", "Carrera": "Calle"}

# "calle 41A #12C - 48" -> type "calle", number "41A", (the rest is the cross + house)
# The number may carry a letter suffix (41A) and be spaced ("41 A").
_ADDRESS = re.compile(
    rf"^\s*(?P<type>{_TYPE_ALT})\s*\.?\s*(?P<num>\d+\s*[a-zA-Z]?)\b",
    re.IGNORECASE,
)
# What follows the street: the cross number, then the dash that separates it from the house.
# "#12C-48", "# 8 - 22", "No. 8-22" — the marker people type varies, the dash does not, and it
# is the dash that proves this is nomenclature rather than a number that happens to be next.
_CROSS = re.compile(
    r"^\s*(?:#|n[°ºo]?\.?|nro\.?)?\s*(?P<num>\d+\s*[a-zA-Z]?)\s*[-–]",
    re.IGNORECASE,
)
_SUFFIXED = re.compile(r"^(?P<base>\d+)\s*(?P<letter>[a-zA-Z])$")


@dataclass(frozen=True)
class StreetQuery:
    """The queryable parts of an address: the street, the cross, and each one's fallback."""

    street: str
    """e.g. "Calle 41A" — canonical type, no house number."""

    base_street: str | None
    """e.g. "Calle 41" when the street carries a letter suffix, else None.

    The nomenclature defines 41A as the block beside 41, which is why it is a sane fallback
    when OSM does not hold the suffixed street.
    """

    cross: str | None = None
    """e.g. "Carrera 12C" — the street the house number is measured from, else None.

    Only ever half of an intersection query. Resolved ALONE it is a wrong answer, not a
    fallback: a geocoder returns the street's representative point, which bears no defined
    relation to the address (measured 1.48 km away in Riohacha).
    """

    base_cross: str | None = None
    """e.g. "Carrera 12" when the cross carries a letter suffix, else None.

    Same reasoning as `base_street`, applied to the other half of the corner.
    """


def parse_street(address: str) -> StreetQuery | None:
    """Pull the queryable street out of a Colombian address.

    Returns None when the text does not look like nomenclature this knows — the caller then
    queries the address as written, which is the pre-existing behaviour. Parsing may only add
    resolutions, never take the raw attempt away.
    """
    match = _ADDRESS.match(address)
    if match is None:
        return None

    street_type = _CANON[match.group("type").lower()]
    number = _number(match.group("num"))

    cross = base_cross = None
    cross_type = _CROSS_TYPE.get(street_type)
    if cross_type is not None:
        cross_match = _CROSS.match(address[match.end() :])
        if cross_match is not None:
            cross_number = _number(cross_match.group("num"))
            cross = f"{cross_type} {cross_number}"
            base_cross = _base(cross_type, cross_number)

    return StreetQuery(
        street=f"{street_type} {number}",
        base_street=_base(street_type, number),
        cross=cross,
        base_cross=base_cross,
    )


def _number(raw: str) -> str:
    """ "41 A" and "41a" are both 41A — people space and case these freely."""
    return re.sub(r"\s+", "", raw).upper()


def _base(street_type: str, number: str) -> str | None:
    """ "Calle 41A" -> "Calle 41"; a street with no letter suffix has no base to fall back to."""
    suffixed = _SUFFIXED.match(number)
    if suffixed is None:
        return None
    return f"{street_type} {suffixed.group('base')}"


def road_matches(asked: str, returned: str | None) -> bool:
    """Does the provider's `address.road` name the street we asked for?

    Asked for a street it does not hold, Nominatim would rather be wrong than empty: asked for
    `Calle 41A` it answered with a house whose *number* contains "41a", standing on Calle 44.
    An approximate pin is fine; a confident wrong one is not, because nothing downstream can
    tell them apart. No road at all (a suburb or POI match) is unverifiable, so it fails.
    """
    if not returned:
        return False
    return _normalize(asked) == _normalize(returned)


def _normalize(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip().casefold()
