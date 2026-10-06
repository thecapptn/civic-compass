"""Two regressions found when the project was redeployed seven weeks after it was built.

Both were invisible on the day of the build and both would have been visible to a beta user.
"""
import os
import re
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from app import repo


def test_an_election_is_listed_once_per_election_not_once_per_jurisdiction(conn):
    """A location resolves to five jurisdictions; an election attached to four of them was being
    listed four times, which reads as four separate elections."""
    ids = [j["id"] for j in repo.jurisdiction_chain(conn, "j-minneapolis")]
    elections = repo.elections_for_jurisdictions(conn, ids)
    seen = [e["id"] for e in elections]
    assert len(seen) == len(set(seen)), f"duplicate elections: {seen}"


def test_elections_page_shows_each_election_once(client):
    body = client.get("/elections?j=j-minneapolis").text
    assert body.count("State General Election") == 1


def test_every_reason_an_election_applies_is_kept(conn):
    ids = [j["id"] for j in repo.jurisdiction_chain(conn, "j-minneapolis")]
    general = [e for e in repo.elections_for_jurisdictions(conn, ids)
               if e["id"] == "e-mn-2026-general"][0]
    assert len(general["relevance_notes"]) > 1
    assert len(general["relevance_notes"]) == len(set(general["relevance_notes"]))


def test_all_reasons_are_rendered_not_just_the_first(client):
    body = client.get("/elections?j=j-minneapolis").text
    assert "Your school district has contests on this ballot." in body
    assert "This is a statewide election in Minnesota." in body


# ----------------------------------------------------------------------------------------------
# Seed currency
# ----------------------------------------------------------------------------------------------

def _seed_at(run_date: str) -> Path:
    """Seed a fresh database as though today were run_date, and return its path."""
    anchor = datetime(2026, 8, 16, tzinfo=timezone.utc).date()
    today = datetime.fromisoformat(run_date).date()
    offset = max(0, (today - anchor).days // 7 * 7)
    path = Path(tempfile.mkdtemp()) / "shifted.sqlite3"
    env = dict(os.environ,
               CIVIC_COMPASS_DB=str(path),
               CIVIC_COMPASS_SEED_OFFSET_DAYS=str(offset),
               CIVIC_COMPASS_NOW=f"{run_date}T12:00:00+00:00")
    subprocess.run([sys.executable, "-m", "app.seed"], env=env, check=True,
                   capture_output=True)
    return path


@pytest.mark.parametrize("run_date", ["2026-08-16", "2026-10-05", "2027-03-01", "2029-01-15"])
def test_demonstration_data_stays_current_whenever_it_is_seeded(run_date):
    """A demo pinned to fixed dates ages into a site that reports it is unsure of everything.
    Seeding must place the dataset relative to the day it runs."""
    path = _seed_at(run_date)
    env = dict(os.environ, CIVIC_COMPASS_DB=str(path),
               CIVIC_COMPASS_NOW=f"{run_date}T12:00:00+00:00")
    out = subprocess.run(
        [sys.executable, "-c",
         "from app import db, repo;"
         "c = db.connect();"
         "ids = [j['id'] for j in repo.jurisdiction_chain(c, 'j-minneapolis')];"
         "e = [x for x in repo.elections_for_jurisdictions(c, ids) if not x['is_past']];"
         "print(len(e), min(x['days_away'] for x in e), max(x['days_away'] for x in e));"
         "g = repo.contests_for(c, e[-1]['id'], ids);"
         "cs = [x for grp in g for x in grp['contests']];"
         "print(sum(1 for x in cs if x['status'].code == 'official'))"],
        env=env, check=True, capture_output=True, text=True).stdout.split()
    upcoming, soonest, furthest, official = (int(x) for x in out)
    assert upcoming >= 2, f"{run_date}: no upcoming elections in the demo set"
    assert 0 <= soonest <= 45, f"{run_date}: nearest election {soonest} days away"
    assert furthest <= 120, f"{run_date}: furthest election {furthest} days away"
    assert official >= 3, f"{run_date}: only {official} contests still read as official"


@pytest.mark.parametrize("run_date", ["2026-10-05", "2027-03-01"])
def test_shifting_preserves_weekdays(run_date):
    """US elections fall on Tuesdays. A shift that moved them to a Thursday would make every
    date in the demo quietly wrong in a way a reader would notice before we did."""
    path = _seed_at(run_date)
    env = dict(os.environ, CIVIC_COMPASS_DB=str(path))
    dates = subprocess.run(
        [sys.executable, "-c",
         "from app import db;"
         "c = db.connect();"
         "print(' '.join(r[0] for r in c.execute('SELECT election_date FROM election')))"],
        env=env, check=True, capture_output=True, text=True).stdout.split()
    for d in dates:
        assert datetime.fromisoformat(d).strftime("%A") == "Tuesday", f"{d} is not a Tuesday"


def test_shifting_preserves_local_clock_times():
    """Polls close at 8 p.m. local. A sub-day shift would turn that into an arbitrary hour."""
    path = _seed_at("2026-10-05")
    env = dict(os.environ, CIVIC_COMPASS_DB=str(path),
               CIVIC_COMPASS_NOW="2026-10-05T12:00:00+00:00")
    rendered = subprocess.run(
        [sys.executable, "-c",
         "from app import db, logic;"
         "c = db.connect();"
         "r = c.execute(\"SELECT occurs_at_utc FROM deadline WHERE id='dl-gen-eday'\").fetchone();"
         "print(logic.format_local(r[0], 'America/Chicago'))"],
        env=env, check=True, capture_output=True, text=True).stdout
    assert "8:00 p.m." in rendered, rendered


def test_the_deliberately_stale_record_is_still_stale_after_shifting():
    """The demo includes one lapsed source on purpose. Shifting must not quietly repair it,
    or the staleness behaviour stops being demonstrated."""
    path = _seed_at("2026-10-05")
    env = dict(os.environ, CIVIC_COMPASS_DB=str(path),
               CIVIC_COMPASS_NOW="2026-10-05T12:00:00+00:00")
    out = subprocess.run(
        [sys.executable, "-c",
         "from app import db, repo;"
         "print(len(repo.stale_records(db.connect())))"],
        env=env, check=True, capture_output=True, text=True).stdout
    assert int(out) >= 1


def test_the_seeded_conflict_survives_shifting():
    path = _seed_at("2026-10-05")
    env = dict(os.environ, CIVIC_COMPASS_DB=str(path),
               CIVIC_COMPASS_NOW="2026-10-05T12:00:00+00:00")
    out = subprocess.run(
        [sys.executable, "-c",
         "from app import db, repo;"
         "print(len(repo.conflicts(db.connect())))"],
        env=env, check=True, capture_output=True, text=True).stdout
    assert int(out) == 1
