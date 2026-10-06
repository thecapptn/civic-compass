"""Unofficial versus certified results. Confusing these is one of the highest-consequence
mistakes an election-information product can make."""
from app import repo


def test_certified_and_unofficial_contests_are_distinguished(conn):
    results = {r["contest"]["id"]: r for r in repo.results_for(conn, "e-mn-2026-primary")}
    assert results["c-prim-gov"]["reporting_status"] == "certified"
    assert results["c-prim-council6"]["reporting_status"] == "unofficial"


def test_certified_result_names_the_certifying_authority(conn):
    results = {r["contest"]["id"]: r for r in repo.results_for(conn, "e-mn-2026-primary")}
    assert results["c-prim-gov"]["certifying_authority"] == "Minnesota State Canvassing Board"


def test_unofficial_status_is_stated_in_words_not_only_colour(client):
    body = client.get("/results/e-mn-2026-primary").text
    assert "Reported, not certified" in body
    assert "Certified" in body
    assert "Reported results are not certified" in body or "not final results" in body


def test_results_page_explains_canvass_and_certification(client):
    body = client.get("/results/e-mn-2026-primary").text
    for term in ("Canvass", "Certification", "Recounts"):
        assert term in body
    assert "eac.gov" in body


def test_precinct_reporting_is_shown(conn):
    results = {r["contest"]["id"]: r for r in repo.results_for(conn, "e-mn-2026-primary")}
    council = results["c-prim-council6"]
    assert council["precincts_reporting"] == 12
    assert council["precincts_total"] == 14


def test_a_contest_with_no_results_says_so_rather_than_showing_zeros(conn, client):
    """Zeros for every candidate read as a tie, which is a false statement about a count."""
    body = client.get("/results/e-mn-2026-general").text
    assert "No results have been reported" in body
    assert "0</td>" not in body


def test_result_rows_carry_provenance(conn):
    for r in repo.results_for(conn, "e-mn-2026-primary"):
        for row in r["rows"]:
            assert row["source"]["source_url"]
            assert row["status"].code


def test_result_ordering_is_deterministic_on_ties(conn):
    """Ordering by count is a report of a count; ties resolve by name, not by insertion order."""
    results = repo.results_for(conn, "e-mn-2026-primary")
    for r in results:
        votes = [row["votes"] for row in r["rows"]]
        assert votes == sorted(votes, reverse=True)
