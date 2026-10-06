"""Conflicting sources and missing data. These are the cases where the honest answer is
'we do not know', and the product has to say so rather than pick."""
from app import repo


def test_two_tier_one_sources_produce_a_public_conflict(conn):
    result = repo.deadlines_for(conn, "e-mn-2026-general", ["j-mn", "j-hennepin"])
    conflicts = result["conflicts"]
    assert len(conflicts) == 1
    assert conflicts[0]["action"] == "return_receipt"
    assert len(conflicts[0]["options"]) == 2


def test_conflicting_deadline_shows_both_sources(conn):
    conflict = repo.deadlines_for(conn, "e-mn-2026-general", ["j-mn", "j-hennepin"])["conflicts"][0]
    orgs = {o["source"]["organization"] for o in conflict["options"]}
    assert len(orgs) == 2


def test_conflict_selects_the_earlier_date_and_says_so(conn, client):
    result = repo.deadlines_for(conn, "e-mn-2026-general", ["j-mn", "j-hennepin"], method="mail")
    chosen = [d for d in result["items"] if d["action"] == "return_receipt"][0]
    others = [o["occurs_at_utc"] for o in chosen["conflict"]["options"]]
    assert chosen["occurs_at_utc"] == min(others)
    body = client.get("/plan/e-mn-2026-general?j=j-minneapolis&m=mail").text
    assert "earlier date" in body


def test_conflict_status_is_carried_on_the_record_itself(conn):
    result = repo.deadlines_for(conn, "e-mn-2026-general", ["j-mn", "j-hennepin"], method="mail")
    chosen = [d for d in result["items"] if d["action"] == "return_receipt"][0]
    assert chosen["status"].code == "conflicting"
    assert chosen["status"].needs_office_referral


def test_lower_tier_disagreement_does_not_create_a_public_conflict():
    """A data partner disagreeing with a state authority is an ops problem, not a public doubt."""
    from app.logic import reconcile
    records = [
        {"trust_tier": 1, "value": "A", "last_verified_at": "2026-08-14T00:00:00+00:00",
         "source_url": "https://example.gov", "claimed_status": "official"},
        {"trust_tier": 3, "value": "B", "last_verified_at": "2026-08-15T00:00:00+00:00",
         "source_url": "https://example.org", "claimed_status": "aggregated"},
    ]
    from datetime import datetime, timezone
    status = reconcile(records, "DEADLINE", "2026-11-03",
                       now=datetime(2026, 8, 16, tzinfo=timezone.utc))
    assert status.code != "conflicting"


def test_ops_console_lists_the_conflict(conn):
    assert any(c["action"] == "return_receipt" for c in repo.conflicts(conn))


def test_missing_contest_data_never_renders_as_an_empty_list(client):
    body = client.get("/ballot/e-mn-2026-general?j=j-minneapolis").text
    idx = body.find("Soil and Water Conservation District Supervisor")
    assert idx > -1
    segment = body[idx:idx + 3000]
    assert "We do not yet have reliable data for this contest" in segment
    assert "Contact" in segment or "election office" in segment


def test_empty_location_category_is_named(client):
    """Ramsey County has no locations on file; the category must be stated as empty."""
    body = client.get("/where/e-stpaul-2026-general?j=j-stpaul").text
    assert "We do not have" in body
    assert "election office" in body.lower()


def test_uncovered_jurisdiction_still_gets_an_office_referral(client):
    body = client.get("/elections?j=j-wi").text
    assert "Wisconsin Elections Commission" in body
    assert "elections.wi.gov" in body


def test_aggregated_data_is_labelled_not_presented_as_official(conn):
    contest = repo.get_contest(conn, "c-stp-council2")
    assert contest["status"].code == "aggregated"
    for c in contest["candidates"]:
        assert c["status"].code == "aggregated"


def test_partial_coverage_warns_the_list_may_be_incomplete(client):
    body = client.get("/ballot/e-mn-2026-general?j=j-minneapolis").text
    assert "This list may be incomplete" in body
