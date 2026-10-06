"""Freshness. An expired verification is an absence of verification, not a weaker kind of it."""
from datetime import datetime, timedelta, timezone

from app import repo
from app.logic import effective_status, freshness_window_days, is_stale

UTC = timezone.utc
NOW = datetime(2026, 8, 16, 12, tzinfo=UTC)


def test_window_shortens_as_election_approaches():
    far = freshness_window_days("LOCATION", "2026-12-25", NOW)
    near = freshness_window_days("LOCATION", "2026-09-01", NOW)
    closer = freshness_window_days("LOCATION", "2026-08-25", NOW)
    week = freshness_window_days("LOCATION", "2026-08-18", NOW)
    assert far > near > closer > week


def test_high_risk_classes_have_tighter_windows_than_explanatory_ones():
    assert (freshness_window_days("DEADLINE", "2026-09-01", NOW)
            < freshness_window_days("RULES", "2026-09-01", NOW))


def test_stale_record_downgrades_to_pending_regardless_of_tier():
    old = (NOW - timedelta(days=200)).isoformat()
    status = effective_status("official", 1, old, "LOCATION", "2026-11-03", now=NOW)
    assert status.code == "pending"
    assert status.stale is True


def test_fresh_tier_one_record_is_official():
    recent = (NOW - timedelta(days=2)).isoformat()
    assert effective_status("official", 1, recent, "LOCATION", "2026-11-03", now=NOW).code == "official"


def test_tier_three_never_reaches_official():
    recent = (NOW - timedelta(days=1)).isoformat()
    assert effective_status("aggregated", 3, recent, "CANDIDATE", "2026-11-03",
                            now=NOW).code == "aggregated"


def test_demo_flag_overrides_every_other_status():
    recent = (NOW - timedelta(days=1)).isoformat()
    assert effective_status("official", 1, recent, "ELECTION", "2026-11-03", is_demo=True,
                            now=NOW).code == "demo"


def test_is_stale_boundary():
    window = freshness_window_days("DEADLINE", "2026-11-03", NOW)
    just_inside = (NOW - timedelta(days=window - 1)).isoformat()
    just_outside = (NOW - timedelta(days=window + 1)).isoformat()
    assert not is_stale(just_inside, "DEADLINE", "2026-11-03", NOW)
    assert is_stale(just_outside, "DEADLINE", "2026-11-03", NOW)


def test_seeded_stale_location_is_reported_by_the_ops_queue(conn):
    stale = repo.stale_records(conn, now=NOW)
    ids = {s["id"] for s in stale}
    assert "loc-mpls-eday-2" in ids, "the deliberately stale demo location should surface"


def test_stale_record_renders_as_not_yet_confirmed(client):
    body = client.get("/where/e-mn-2026-general?j=j-minneapolis").text
    assert "Not yet confirmed" in body


def test_source_health_flags_the_lapsed_source(conn):
    health = {h["id"]: h for h in repo.source_health(conn, now=NOW)}
    assert health["src-mpls-stale"]["alert"] is True
    assert health["src-mpls"]["alert"] is False


def test_a_concluded_election_is_not_subject_to_the_tightening_window():
    """Windows tighten as an election nears because facts move. After it, they are settled.
    Applying the three-day pre-election window to a finished contest floods the operations
    queue with records nobody can act on, hiding the lapsed sources that still matter."""
    day_before = freshness_window_days("CANDIDATE", "2026-08-18",
                                       datetime(2026, 8, 16, tzinfo=timezone.utc))
    day_after = freshness_window_days("CANDIDATE", "2026-08-14",
                                      datetime(2026, 8, 16, tzinfo=timezone.utc))
    assert day_before <= 3
    assert day_after > 90


def test_the_operations_queue_is_not_flooded_by_a_past_election(conn):
    """The seeded primary is over. Only the deliberately lapsed polling-place source should
    be queued for attention."""
    stale = repo.stale_records(conn)
    assert len(stale) == 1
    assert stale[0]["source"]["id"] == "src-mpls-stale"


def test_a_past_election_source_that_goes_dark_still_surfaces_eventually():
    """Generous is not unlimited; a source nobody has checked in over a year is still a problem."""
    long_gone = freshness_window_days("CANDIDATE", "2026-08-14",
                                      datetime(2026, 8, 16, tzinfo=timezone.utc))
    assert is_stale("2024-01-01T00:00:00+00:00", "CANDIDATE", "2026-08-14",
                    datetime(2026, 8, 16, tzinfo=timezone.utc))
    assert long_gone < 10_000
