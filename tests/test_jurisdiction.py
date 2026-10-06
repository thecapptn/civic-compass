"""Jurisdiction matching. Getting this wrong sends a person to the wrong ballot, so the tests
lean on the cases that actually go wrong in practice: ZIPs that straddle boundaries, ZIPs we do
not cover, and the chain of overlapping jurisdictions a single address sits inside."""
from app import repo
from app.logic import classify_query


def test_zip_is_classified_as_postal():
    assert classify_query("55418") == ("postal", "55418")
    assert classify_query("Minneapolis, MN 55418")[0] == "postal"
    assert classify_query("55418-1234") == ("postal", "55418")


def test_city_state_and_state_classification():
    assert classify_query("Minneapolis, MN")[0] == "city_state"
    assert classify_query("MN") == ("state", "MN")
    assert classify_query("") == ("none", "")


def test_known_zip_resolves_to_jurisdictions(conn):
    match = repo.resolve_location(conn, "55418")
    names = {j["name"] for j in match.jurisdictions}
    assert "City of Minneapolis" in names
    assert "Hennepin County" in names
    assert "Minnesota" in names


def test_zip_straddling_two_cities_is_ambiguous_not_guessed(conn):
    match = repo.resolve_location(conn, "55429")
    assert match.confidence == "ambiguous"
    assert "more than one city" in match.explanation


def test_uncovered_zip_returns_no_match_rather_than_a_wrong_one(conn):
    match = repo.resolve_location(conn, "99999")
    assert match.confidence == "none"
    assert match.jurisdictions == []


def test_jurisdiction_chain_includes_parents_and_school_district(conn):
    chain = repo.jurisdiction_chain(conn, "j-minneapolis")
    ids = [j["id"] for j in chain]
    assert ids[0] == "j-minneapolis"
    for expected in ("j-hennepin", "j-mn", "j-us", "j-mps"):
        assert expected in ids, f"{expected} missing from chain"


def test_resolve_never_returns_the_raw_input(conn):
    """The submitted string must not survive resolution in any field of the result."""
    match = repo.resolve_location(conn, "1234 Demonstration Ave, Minneapolis, MN 55418")
    blob = repr(match)
    assert "1234 Demonstration Ave" not in blob


def test_address_is_not_accepted_over_get(client):
    """A GET route for address entry would put the address in logs and referrers."""
    assert client.get("/resolve").status_code in (404, 405)
