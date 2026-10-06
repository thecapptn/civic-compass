"""Domain logic that must not live in templates or in the database.

Three rules drive this module:
  1. Effective status is *computed* on read from tier agreement + freshness. Stored status is only
     the ingest-time claim. Stale data becomes `pending`; it is never served as if fresh.
  2. Candidate ordering is computed from `order_rule` at render time. There is no stored order to
     tamper with, and no input to this function other than the candidates themselves.
  3. Deadline math happens in the *jurisdiction's* timezone. A 8:00 PM local deadline is a fact about
     the jurisdiction, not about where the reader happens to be.
"""
from __future__ import annotations

import hashlib
import os
import re
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

# --------------------------------------------------------------------------------------
# Time
# --------------------------------------------------------------------------------------

UTC = timezone.utc


def utc_now() -> datetime:
    """Current time, with a test and demonstration seam.

    Setting CIVIC_COMPASS_NOW to an ISO timestamp freezes the clock. The test suite uses this so
    that assertions about freshness, staleness, and days-until-election are decided by the data
    rather than by the day the suite happens to run — otherwise tests about expiry quietly begin
    failing weeks later, which is how a stale-data bug hides. It is ignored unless explicitly set.
    """
    pinned = os.environ.get("CIVIC_COMPASS_NOW")
    if pinned:
        return datetime.fromisoformat(pinned).astimezone(UTC)
    return datetime.now(UTC)


def utc_now_iso() -> str:
    return utc_now().replace(microsecond=0).isoformat()


def parse_iso(value: str) -> datetime:
    """Parse an ISO timestamp or plain date; always returns an aware UTC datetime."""
    if not value:
        raise ValueError("empty timestamp")
    v = value.strip().replace("Z", "+00:00")
    if len(v) == 10:
        dt = datetime.fromisoformat(v + "T00:00:00+00:00")
    else:
        dt = datetime.fromisoformat(v)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def parse_in_zone(value: str, tz_name: str) -> datetime:
    """Interpret a timestamp in the jurisdiction's zone.

    A date-only value such as an election date is a *calendar date* in that jurisdiction, not an
    instant. Parsing it as midnight UTC and converting would shift a Tuesday election to the
    preceding Monday everywhere west of Greenwich, which is the single most damaging off-by-one
    this product could ship.
    """
    tz = ZoneInfo(tz_name)
    v = value.strip()
    if len(v) == 10:
        return datetime.fromisoformat(v + "T00:00:00").replace(tzinfo=tz)
    return parse_iso(v).astimezone(tz)


def to_local(value: str, tz_name: str) -> datetime:
    return parse_in_zone(value, tz_name)


def format_local(value: str, tz_name: str, all_day: bool = False) -> str:
    """Human date/time in the jurisdiction's zone. Dates are always written out in full so they
    cannot be misread as day/month, and the timezone is always named in words."""
    local = to_local(value, tz_name)
    day = local.strftime("%A, %B %-d, %Y")
    if all_day:
        return day
    clock = local.strftime("%-I:%M %p").replace("AM", "a.m.").replace("PM", "p.m.")
    return f"{day} at {clock} {local.tzname()}"


def days_until(value: str, tz_name: str, now: datetime | None = None) -> int:
    """Whole days remaining, counted by calendar day in the jurisdiction's zone.

    Counting by calendar day rather than by 24-hour blocks is deliberate: a voter asking
    "how many days do I have" means days on a calendar, not elapsed hours.
    """
    tz = ZoneInfo(tz_name)
    now_local = (now or utc_now()).astimezone(tz)
    target_local = parse_in_zone(value, tz_name)
    return (target_local.date() - now_local.date()).days


# --------------------------------------------------------------------------------------
# Freshness and status
# --------------------------------------------------------------------------------------

# Days a record of each class may go unverified, by proximity to election day.
# Keys: (>60 days out, <=60, <=14, election week). See docs/02.
FRESHNESS_WINDOWS: dict[str, tuple[int, int, int, int]] = {
    "ELECTION": (90, 30, 14, 3),
    "DEADLINE": (45, 14, 7, 1),
    "LOCATION": (45, 14, 3, 1),
    "RULES": (90, 30, 14, 7),
    "CONTEST": (60, 21, 7, 3),
    "CANDIDATE": (60, 21, 7, 3),
    "MEASURE": (60, 21, 7, 3),
    "ADMIN": (90, 90, 90, 90),
}

HIGH_RISK_CLASSES = {"DEADLINE", "LOCATION", "RULES", "RESULT"}

# Records attached to an election that has already happened. Generous, because the facts no longer
# move; it is not unlimited, because a source that has gone dark should still eventually surface.
PAST_ELECTION_WINDOW_DAYS = 365

STATUS_WORDS = {
    "official": "Official",
    "verified": "Verified",
    "aggregated": "Aggregated",
    "pending": "Not yet confirmed",
    "conflicting": "Sources disagree",
    "historical": "Past election",
    "unofficial": "Reported, not certified",
    "certified": "Certified",
    "demo": "Demonstration data",
}

STATUS_EXPLANATIONS = {
    "official": "Published or confirmed by the election office responsible for this information.",
    "verified": "Checked against an authoritative source within our freshness window.",
    "aggregated": "Supplied by a third-party data partner and not yet confirmed against the "
                  "election office.",
    "pending": "We expected this information but have not confirmed it. Check with the election "
               "office before acting on it.",
    "conflicting": "Two sources show different information. Check the official election office "
                   "before acting.",
    "historical": "This applies to a past election and should not be used for a current one.",
    "unofficial": "These results are reported but not certified. Numbers may change during canvass.",
    "certified": "Final results published by the responsible authority.",
    "demo": "Demonstration data. Not real election information.",
}


def freshness_window_days(data_class: str, election_date: str | None,
                          now: datetime | None = None) -> int:
    windows = FRESHNESS_WINDOWS.get(data_class, (60, 21, 7, 3))
    if not election_date:
        return windows[0]
    now = now or utc_now()
    days_out = (parse_iso(election_date).date() - now.astimezone(UTC).date()).days
    if days_out < 0:
        # The election has happened. Freshness windows exist because facts about an *upcoming*
        # election change — a polling place moves, a candidate withdraws. Once it is over, the
        # candidate list and contest list are settled history, and demanding daily
        # re-verification of them floods the operations queue with records nobody can act on,
        # burying the lapsed sources that still matter. Results are governed separately, by
        # certification status rather than by this window.
        return PAST_ELECTION_WINDOW_DAYS
    if days_out > 60:
        return windows[0]
    if days_out > 14:
        return windows[1]
    if days_out > 7:
        return windows[2]
    return windows[3]


def is_stale(last_verified_at: str, data_class: str, election_date: str | None,
             now: datetime | None = None) -> bool:
    now = now or utc_now()
    window = freshness_window_days(data_class, election_date, now)
    return parse_iso(last_verified_at) < now - timedelta(days=window)


@dataclass
class Status:
    """The computed, user-facing state of a fact."""
    code: str
    word: str
    explanation: str
    stale: bool = False
    conflict_sources: tuple = ()

    @property
    def needs_office_referral(self) -> bool:
        return self.code in {"pending", "conflicting", "aggregated"}


def effective_status(claimed: str, trust_tier: int, last_verified_at: str, data_class: str,
                     election_date: str | None = None, is_demo: bool = False,
                     now: datetime | None = None) -> Status:
    """Compute what a fact's status actually is right now.

    Demo beats everything, because mislabelling demo data as real is the single worst failure
    this product can commit. Staleness then downgrades to `pending` regardless of the claim:
    an expired verification is not a weaker form of verified, it is an absence of one.
    """
    if is_demo:
        return Status("demo", STATUS_WORDS["demo"], STATUS_EXPLANATIONS["demo"])
    if claimed == "conflicting":
        return Status("conflicting", STATUS_WORDS["conflicting"], STATUS_EXPLANATIONS["conflicting"])
    stale = is_stale(last_verified_at, data_class, election_date, now)
    if stale:
        return Status("pending", STATUS_WORDS["pending"], STATUS_EXPLANATIONS["pending"], stale=True)
    if trust_tier == 1 and claimed == "official":
        code = "official"
    elif trust_tier <= 2:
        code = "verified"
    elif trust_tier == 3:
        code = "aggregated"
    else:
        code = "pending"
    return Status(code, STATUS_WORDS[code], STATUS_EXPLANATIONS[code])


def reconcile(records: list[dict], data_class: str, election_date: str | None = None,
              now: datetime | None = None) -> Status:
    """Resolve several source records covering the same fact. See docs/02 resolution order.

    A lower-tier source is never allowed to cast doubt on a tier-1 authority: that disagreement
    goes to the ops queue, not to the reader. Only tier-1 disagreeing with tier-1 is a public
    conflict, because only then do we genuinely not know.
    """
    if not records:
        return Status("pending", STATUS_WORDS["pending"], STATUS_EXPLANATIONS["pending"])
    tier1 = [r for r in records if r["trust_tier"] == 1]
    if len(tier1) > 1:
        values = {str(r.get("value")) for r in tier1}
        if len(values) > 1:
            return Status(
                "conflicting", STATUS_WORDS["conflicting"], STATUS_EXPLANATIONS["conflicting"],
                conflict_sources=tuple(r["source_url"] for r in tier1),
            )
    best = min(records, key=lambda r: r["trust_tier"])
    return effective_status(
        best.get("claimed_status", "official"), best["trust_tier"],
        best["last_verified_at"], data_class, election_date, now=now,
    )


# --------------------------------------------------------------------------------------
# Neutral ordering
# --------------------------------------------------------------------------------------

def sort_key_for(ballot_name: str) -> str:
    """Derive a stable sort key. Demo names are stored 'Last, First', which is also how ballots
    are usually printed; if a name has no comma we fall back to the whole string rather than
    guessing at a surname."""
    normalized = re.sub(r"\s+", " ", ballot_name.strip()).lower()
    if "," in normalized:
        last, _, first = normalized.partition(",")
        return f"{last.strip()}\u0000{first.strip()}"
    return normalized


def neutral_order(candidates: list[dict], order_rule: str = "alphabetical") -> list[dict]:
    """Order candidates for display.

    The only permitted inputs are the candidates and the contest's declared order rule. There is
    deliberately no parameter for relevance, popularity, incumbency, or party. `id` is the final
    tiebreaker purely for determinism, so identical names cannot render in random order.
    """
    if order_rule == "official_ballot":
        return sorted(
            candidates,
            key=lambda c: (c.get("ballot_position") is None,
                           c.get("ballot_position") or 0,
                           c["id"]),
        )
    return sorted(
        candidates,
        key=lambda c: (c.get("sort_key") or sort_key_for(c["ballot_name"]), c["id"]),
    )


ORDER_RULE_WORDS = {
    "alphabetical": "Listed alphabetically by ballot name. This order is not a ranking.",
    "official_ballot": "Listed in the official ballot order published by the election office. "
                       "This order is not a ranking.",
}


# --------------------------------------------------------------------------------------
# Jurisdiction resolution
# --------------------------------------------------------------------------------------

STATE_CODES = {
    "minnesota": "MN", "mn": "MN", "wisconsin": "WI", "wi": "WI",
}


@dataclass
class LocationMatch:
    jurisdictions: list[dict]
    confidence: str          # exact | likely | ambiguous | none
    explanation: str
    query_kind: str          # postal | city_state | state | none


def classify_query(raw: str) -> tuple[str, str]:
    """Classify a location string without retaining it.

    The raw string never leaves this function's caller frame: routes resolve it to jurisdiction IDs
    and discard it before responding. See docs/04 T5.
    """
    q = re.sub(r"\s+", " ", (raw or "").strip())
    if not q:
        return "none", ""
    zip_match = re.search(r"\b(\d{5})(?:-\d{4})?\b", q)
    if zip_match:
        return "postal", zip_match.group(1)
    if "," in q:
        return "city_state", q
    if q.lower() in STATE_CODES:
        return "state", STATE_CODES[q.lower()]
    return "city_state", q


def digest(value: str) -> str:
    """Non-reversible digest, used only for de-duplicating correction reports."""
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]


def new_token() -> str:
    return secrets.token_urlsafe(18)


# --------------------------------------------------------------------------------------
# Calendar export
# --------------------------------------------------------------------------------------

def ics_escape(text: str) -> str:
    return (text.replace("\\", "\\\\").replace(";", r"\;")
                .replace(",", r"\,").replace("\n", r"\n"))


def build_ics(events: list[dict], calendar_name: str) -> str:
    """Build an .ics file. Generated per request and never stored, so a downloaded reminder
    leaves no server-side record of who is voting where."""
    lines = [
        "BEGIN:VCALENDAR", "VERSION:2.0",
        "PRODID:-//Civic Compass//Election Reminders//EN",
        "CALSCALE:GREGORIAN", "METHOD:PUBLISH",
        f"X-WR-CALNAME:{ics_escape(calendar_name)}",
    ]
    for ev in events:
        start = parse_iso(ev["occurs_at_utc"]).strftime("%Y%m%dT%H%M%SZ")
        end = (parse_iso(ev["occurs_at_utc"]) + timedelta(hours=1)).strftime("%Y%m%dT%H%M%SZ")
        lines += [
            "BEGIN:VEVENT",
            f"UID:{ev['uid']}@civic-compass.invalid",
            f"DTSTAMP:{utc_now().strftime('%Y%m%dT%H%M%SZ')}",
            f"DTSTART:{start}", f"DTEND:{end}",
            f"SUMMARY:{ics_escape(ev['summary'])}",
            f"DESCRIPTION:{ics_escape(ev['description'])}",
            "END:VEVENT",
        ]
    lines.append("END:VCALENDAR")
    return "\r\n".join(lines) + "\r\n"


# --------------------------------------------------------------------------------------
# Voice guard (see docs/06 and tests/test_voice.py)
# --------------------------------------------------------------------------------------

BANNED_TERMS = [
    "save democracy", "take back", "extreme", "radical", "common sense", "real voters",
    "patriots", "high-stakes", "must-win", "battleground", "refused to answer",
    "cut through the noise", "crucial", "make your voice heard", "every vote counts",
]

DEADLINE_LABELS = {
    "register": "Register to vote",
    "request_ballot": "Request a mail ballot",
    "early_vote_start": "Early voting begins",
    "early_vote_end": "Early voting ends",
    "return_postmark": "Mail ballot postmark deadline",
    "return_receipt": "Mail ballot must be received",
    "cure": "Deadline to fix a ballot problem",
    "election_day": "Election Day",
}

METHOD_LABELS = {
    "election_day": "Vote on Election Day",
    "early": "Vote early in person",
    "mail": "Vote by mail",
    "drop_off": "Drop off a mail ballot",
    "uocava": "Military or overseas voting",
    "unsure": "Not sure yet",
}

LEVEL_LABELS = {
    "federal": "Federal", "state": "State", "judicial": "Judicial", "county": "County",
    "municipal": "City", "education": "School", "special": "Special district",
    "measure": "Ballot measures",
}
