import pytest

from kosha_domain.geography import IndianState, is_valid_pincode, state_for_pincode

S = IndianState


@pytest.mark.parametrize(
    ("pincode", "state"),
    [
        ("110001", S.DELHI),
        ("122001", S.HARYANA),  # Gurugram
        ("141001", S.PUNJAB),  # Ludhiana
        ("160017", S.CHANDIGARH),
        ("171001", S.HIMACHAL_PRADESH),  # Shimla
        ("190001", S.JAMMU_AND_KASHMIR),  # Srinagar
        ("194101", S.LADAKH),  # Leh
        ("226001", S.UTTAR_PRADESH),  # Lucknow
        ("248001", S.UTTARAKHAND),  # Dehradun
        ("302001", S.RAJASTHAN),  # Jaipur
        ("380001", S.GUJARAT),  # Ahmedabad
        ("400001", S.MAHARASHTRA),  # Mumbai
        ("403001", S.GOA),  # Panaji
        ("411001", S.MAHARASHTRA),  # Pune
        ("452001", S.MADHYA_PRADESH),  # Indore
        ("492001", S.CHHATTISGARH),  # Raipur
        ("500001", S.TELANGANA),  # Hyderabad
        ("520001", S.ANDHRA_PRADESH),  # Vijayawada
        ("560001", S.KARNATAKA),  # Bengaluru
        ("600001", S.TAMIL_NADU),  # Chennai
        ("605001", S.PUDUCHERRY),
        ("682001", S.KERALA),  # Kochi
        ("700001", S.WEST_BENGAL),  # Kolkata
        ("737101", S.SIKKIM),  # Gangtok
        ("744101", S.ANDAMAN_AND_NICOBAR_ISLANDS),  # Port Blair
        ("751001", S.ODISHA),  # Bhubaneswar
        ("781001", S.ASSAM),  # Guwahati
        ("793001", S.MEGHALAYA),  # Shillong
        ("800001", S.BIHAR),  # Patna
        ("834001", S.JHARKHAND),  # Ranchi
    ],
)
def test_pincode_resolves_to_its_postal_state(pincode: str, state: IndianState) -> None:
    assert state_for_pincode(pincode) is state
    assert is_valid_pincode(pincode)


@pytest.mark.parametrize(
    "pincode",
    ["012345", "11000", "1100011", "11000A", "", "999999"],  # 9xxxxx is the Army Postal Service
)
def test_malformed_or_non_civilian_pincodes_have_no_state(pincode: str) -> None:
    assert state_for_pincode(pincode) is None
    assert not is_valid_pincode(pincode)


@pytest.mark.parametrize(
    ("state", "code"),
    [
        (S.JAMMU_AND_KASHMIR, "01"),
        (S.DELHI, "07"),
        (S.MAHARASHTRA, "27"),
        (S.KARNATAKA, "29"),
        (S.TELANGANA, "36"),
        (S.LADAKH, "38"),
    ],
)
def test_states_carry_their_gst_state_code(state: IndianState, code: str) -> None:
    assert state.gst_code == code


def test_every_state_and_union_territory_is_listed_once() -> None:
    assert len(IndianState) == 36
    assert len({s.gst_code for s in IndianState}) == 36
