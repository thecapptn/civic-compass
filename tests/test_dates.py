"""Date and timezone handling. Deadlines are legal facts about a jurisdiction, so they are
computed in the jurisdiction's zone, not the reader's."""
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from app.logic import build_ics, days_until, format_local, parse_iso

CHI = "America/Chicago"


def test_deadline_counted_in_jurisdiction_timezone_not_utc():
    """8:00 PM Central on Nov 3 is 02:00 UTC on Nov 4. Counting in UTC would report the wrong day."""
    deadline = "2026-11-04T02:00:00+00:00"
    now = datetime(2026, 11, 3, 23, 0, tzinfo=timezone.utc)  # 5 PM Central, same local day
    assert days_until(deadline, CHI, now) == 0


def test_days_until_counts_calendar_days_not_elapsed_hours():
    now = datetime(2026, 11, 2, 23, 30, tzinfo=ZoneInfo(CHI))
    assert days_until("2026-11-04T02:00:00+00:00", CHI, now) == 1


def test_past_deadline_is_negative():
    now = datetime(2026, 12, 1, tzinfo=timezone.utc)
    assert days_until("2026-11-04T02:00:00+00:00", CHI, now) < 0


def test_format_names_the_timezone_in_words():
    out = format_local("2026-11-04T02:00:00+00:00", CHI)
    assert "November 3, 2026" in out
    assert "8:00 p.m." in out
    assert "CST" in out or "CDT" in out


def test_all_day_deadline_omits_a_misleading_clock_time():
    out = format_local("2026-10-14T04:59:00+00:00", CHI, all_day=True)
    assert ":" not in out.split(",")[-1]
    assert "October 13, 2026" in out


def test_date_is_written_out_so_it_cannot_be_misread():
    out = format_local("2026-11-04T02:00:00+00:00", CHI, all_day=True)
    assert "11/3" not in out and "03/11" not in out


def test_parse_accepts_date_only_and_z_suffix():
    assert parse_iso("2026-11-03").year == 2026
    assert parse_iso("2026-11-03T12:00:00Z").hour == 12


def test_ics_export_is_wellformed_and_labels_demo_data():
    body = build_ics([{
        "uid": "x1", "occurs_at_utc": "2026-11-04T02:00:00+00:00",
        "summary": "[Demonstration data] Election Day",
        "description": "Source: Example, semicolons; and, commas",
    }], "Test calendar")
    assert body.startswith("BEGIN:VCALENDAR") and body.rstrip().endswith("END:VCALENDAR")
    assert "DTSTART:20261104T020000Z" in body
    assert r"\;" in body and r"\," in body  # escaped per RFC 5545
    assert "Demonstration data" in body


def test_calendar_route_marks_every_event_as_demonstration(client):
    r = client.get("/plan/e-mn-2026-general/calendar.ics?j=j-minneapolis")
    assert r.status_code == 200
    assert "text/calendar" in r.headers["content-type"]
    for line in r.text.splitlines():
        if line.startswith("SUMMARY:"):
            assert "Demonstration data" in line


def test_date_only_election_date_does_not_shift_a_day_backwards():
    """Regression: parsing a bare election date as midnight UTC and converting to Central time
    rendered a Tuesday election as the preceding Monday."""
    assert "Tuesday, November 3, 2026" == format_local("2026-11-03", CHI, all_day=True)


def test_date_only_values_hold_across_timezones():
    for zone in ("America/Chicago", "America/Los_Angeles", "America/New_York", "Pacific/Honolulu"):
        assert "November 3, 2026" in format_local("2026-11-03", zone, all_day=True)


def test_days_until_an_election_date_is_counted_from_the_calendar_date():
    now = datetime(2026, 8, 16, 12, tzinfo=timezone.utc)
    assert days_until("2026-11-03", CHI, now) == 79


def test_election_page_shows_the_correct_weekday(client):
    body = client.get("/elections/e-mn-2026-general?j=j-minneapolis").text
    assert "Tuesday, November 3, 2026" in body
    # The weekday must match the date on every rendered date, not only the election date.
    import re
    for weekday, day in re.findall(r"(\w+day), November (\d+), 2026", body):
        expected = datetime(2026, 11, int(day)).strftime("%A")
        assert weekday == expected, f"rendered {weekday} for November {day}"
