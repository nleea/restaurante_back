"""The Colombian address parser, on its own — no network, no provider.

Every case here is text a person actually types into the comanda while on the phone.
"""

from __future__ import annotations

import pytest

from restaurante.modules.delivery.infrastructure.address_co import (
    parse_street,
    road_matches,
)


class TestParseStreet:
    def test_the_address_that_failed_for_real(self) -> None:
        """`calle 41A #12C - 48, Riohacha` pinned 555 m off: the cross street was dropped."""
        q = parse_street("calle 41A #12C - 48, Riohacha")
        assert q is not None
        assert q.street == "Calle 41A"
        # OSM has no Calle 41A, so the fallback is the block beside it.
        assert q.base_street == "Calle 41"
        # The half of the address that puts the pin on the right corner.
        assert q.cross == "Carrera 12C"
        assert q.base_cross == "Carrera 12"

    @pytest.mark.parametrize(
        ("address", "street"),
        [
            ("Calle 15 #10-20", "Calle 15"),
            ("Calle 15 # 10 - 20", "Calle 15"),
            ("Carrera 7 #12-30", "Carrera 7"),
            ("Cra 15 # 8 - 22", "Carrera 15"),
            ("cra. 15 #8-22", "Carrera 15"),
            ("KR 15 No. 8-22", "Carrera 15"),
            ("k 15 #8-22", "Carrera 15"),
            ("cll 41 #12-48", "Calle 41"),
            ("CL 41 #12-48", "Calle 41"),
            ("Av 19 #4-50", "Avenida 19"),
            ("Diagonal 8 #3-21", "Diagonal 8"),
            ("Transversal 12 #5-9", "Transversal 12"),
        ],
    )
    def test_canonicalises_the_type_people_type(self, address: str, street: str) -> None:
        q = parse_street(address)
        assert q is not None
        assert q.street == street

    def test_a_spaced_letter_suffix_is_still_a_suffix(self) -> None:
        q = parse_street("calle 41 A #12C-48")
        assert q is not None
        assert q.street == "Calle 41A"
        assert q.base_street == "Calle 41"

    def test_a_plain_street_has_no_fallback(self) -> None:
        """Nothing to fall back to — Calle 41 IS the base street."""
        q = parse_street("Calle 41 #13-15")
        assert q is not None
        assert q.street == "Calle 41"
        assert q.base_street is None

    def test_an_address_with_no_house_number_still_parses(self) -> None:
        q = parse_street("Calle 20, Riohacha")
        assert q is not None
        assert q.street == "Calle 20"

    @pytest.mark.parametrize(
        "address",
        [
            "",
            "   ",
            "la casa de la reja verde",
            "barrio San Martín, casa esquinera",
            "#12C-48",  # a house number with no street
            "Riohacha, La Guajira",
        ],
    )
    def test_unparseable_input_returns_none_rather_than_guessing(
        self, address: str
    ) -> None:
        """The caller then queries the address as written — parsing may only ADD resolutions."""
        assert parse_street(address) is None

    def test_never_raises_on_junk(self) -> None:
        """Geocoding is a side lookup: it must never break taking an order."""
        for junk in ("!!!", "calle", "###", "cra", "1234567890" * 30):
            parse_street(junk)  # no exception


class TestCrossStreet:
    """The other half of the corner — dropped until now, and the reason pins landed off."""

    @pytest.mark.parametrize(
        ("address", "street", "cross"),
        [
            ("Calle 15 #10-20", "Calle 15", "Carrera 10"),
            ("Calle 15 # 10 - 20", "Calle 15", "Carrera 10"),
            # A Carrera is crossed by Calles — the inversion runs both ways.
            ("Carrera 7 #12-30", "Carrera 7", "Calle 12"),
            ("KR 15 No. 8-22", "Carrera 15", "Calle 8"),
            ("cra. 15 #8-22", "Carrera 15", "Calle 8"),
            ("cll 41 #12-48", "Calle 41", "Carrera 12"),
        ],
    )
    def test_the_cross_is_the_dual_of_the_street_type(
        self, address: str, street: str, cross: str
    ) -> None:
        q = parse_street(address)
        assert q is not None
        assert q.street == street
        assert q.cross == cross

    def test_a_suffixed_cross_has_its_own_fallback(self) -> None:
        """OSM may hold Carrera 12 but not Carrera 12C — the corner needs a way down too."""
        q = parse_street("Calle 41A #12C-48")
        assert q is not None
        assert q.cross == "Carrera 12C"
        assert q.base_cross == "Carrera 12"

    def test_a_plain_cross_has_no_fallback(self) -> None:
        q = parse_street("Calle 41 #12-48")
        assert q is not None
        assert q.cross == "Carrera 12"
        assert q.base_cross is None

    def test_no_cross_when_the_address_names_only_a_street(self) -> None:
        """"Calle 20, Riohacha" has no corner to find — the street pin is all there is."""
        q = parse_street("Calle 20, Riohacha")
        assert q is not None
        assert q.cross is None
        assert q.base_cross is None

    def test_a_number_with_no_dash_is_not_a_cross(self) -> None:
        """The dash is what proves nomenclature; without it this is just a nearby number."""
        q = parse_street("Calle 20 local 3, Riohacha")
        assert q is not None
        assert q.cross is None

    @pytest.mark.parametrize(
        "address",
        ["Av 19 #4-50", "Diagonal 8 #3-21", "Transversal 12 #5-9"],
    )
    def test_types_with_no_dual_leave_the_cross_unguessed(self, address: str) -> None:
        """An Avenida is not crossed by any one type. Guessing costs a wasted lookup."""
        q = parse_street(address)
        assert q is not None
        assert q.cross is None


class TestRoadMatches:
    def test_the_confident_wrong_pin_is_rejected(self) -> None:
        """Asked for Calle 41A, Nominatim answered with a house standing on Calle 44."""
        assert road_matches("Calle 41A", "Calle 44") is False

    @pytest.mark.parametrize(
        ("asked", "returned"),
        [
            ("Calle 41", "Calle 41"),
            ("Calle 41", "calle 41"),
            ("Carrera 12C", "Carrera 12C"),
            ("Calle 15", "  Calle   15 "),
        ],
    )
    def test_the_same_street_matches_regardless_of_case_and_spacing(
        self, asked: str, returned: str
    ) -> None:
        assert road_matches(asked, returned) is True

    @pytest.mark.parametrize("returned", [None, ""])
    def test_no_road_is_unverifiable_and_therefore_a_miss(self, returned) -> None:
        """A suburb or POI match carries no road — strict by design."""
        assert road_matches("Calle 41", returned) is False

    def test_a_letter_suffix_is_not_the_base_street(self) -> None:
        """41A and 41 are different streets; only the fallback may substitute one."""
        assert road_matches("Calle 41A", "Calle 41") is False
