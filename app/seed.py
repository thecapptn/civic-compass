"""Seed the database with DEMONSTRATION data.

Every candidate name here is fictional. Real officeholders are deliberately not used, even for
jurisdictions that exist, because a fabricated contest attached to a real person's name is exactly
the "demo data presented as current election information" failure the design bible prohibits.

Jurisdictions, election offices, and source URLs *are* real, because the office-referral floor must
send people somewhere that actually helps them. Elections, dates, contests, candidates, measures,
locations, and results are invented and are labeled as demonstration data everywhere they render.
"""
from __future__ import annotations

import os
import re
import sqlite3
import sys
from datetime import datetime, timedelta, timezone

from .db import connect, init_schema
from .logic import sort_key_for

UTC = timezone.utc

# Every date literal below is written relative to this anchor: the primary sits five days before
# it, the special election thirty days after, the general seventy-nine days after, and each source
# carries a verification date a few days back. Those intervals are the point of the dataset.
SEED_ANCHOR = datetime(2026, 8, 16, 12, 0, tzinfo=UTC)
SEED_NOW = SEED_ANCHOR  # literals in this module are anchor-relative; the shift happens on write.


def _offset() -> timedelta:
    """How far forward to move the whole dataset so it stays meaningful whenever it is seeded.

    A demonstration set pinned to fixed dates rots: run it two months later and every source has
    aged past its verification window, so the product correctly but uselessly reports that it is
    unsure of everything. Shifting the entire set preserves every interval instead.

    The shift is a whole number of weeks so that weekdays survive it. Elections land on Tuesdays,
    early voting has weekend patterns, and 'polls close Tuesday at 8 p.m.' has to stay true.
    """
    override = os.environ.get("CIVIC_COMPASS_SEED_OFFSET_DAYS")
    if override is not None:
        return timedelta(days=int(override))
    elapsed = (datetime.now(UTC).date() - SEED_ANCHOR.date()).days
    return timedelta(days=max(0, elapsed // 7 * 7))


OFFSET = _offset()

_DATE_ONLY = re.compile(r"\d{4}-\d{2}-\d{2}")
_TIMESTAMP = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:[+-]\d{2}:\d{2}|Z)?")


def _shift(value):
    """Move one ISO date or timestamp forward by OFFSET, leaving everything else untouched."""
    if not isinstance(value, str) or not OFFSET:
        return value
    if _TIMESTAMP.fullmatch(value):
        return (datetime.fromisoformat(value.replace("Z", "+00:00")) + OFFSET).isoformat()
    if _DATE_ONLY.fullmatch(value):
        return (datetime.fromisoformat(value) + OFFSET).date().isoformat()
    return value


class _ShiftingCursor:
    """Applies the dataset shift to every value written, so no insert site can forget it."""

    def __init__(self, cursor):
        self._cursor = cursor

    def execute(self, sql, params=()):
        return self._cursor.execute(sql, tuple(_shift(v) for v in params))

    def executemany(self, sql, rows):
        return self._cursor.executemany(sql, [tuple(_shift(v) for v in r) for r in rows])

    def __getattr__(self, name):
        return getattr(self._cursor, name)


def iso(dt: datetime) -> str:
    return dt.replace(microsecond=0).isoformat()


def ago(days: int) -> str:
    return iso(SEED_NOW - timedelta(days=days))


# --------------------------------------------------------------------------------------
# Sources
# --------------------------------------------------------------------------------------

SOURCES = [
    # id, org, url, type, tier, retrieved_days_ago, verified_days_ago, claimed
    ("src-mnsos", "Minnesota Secretary of State",
     "https://www.sos.mn.gov/elections-voting/", "state_election_authority", 1, 4, 4, "official"),
    ("src-mnsos-cal", "Minnesota Secretary of State",
     "https://www.sos.mn.gov/elections-voting/upcoming-elections/",
     "state_election_authority", 1, 4, 4, "official"),
    ("src-hennepin", "Hennepin County Elections",
     "https://www.hennepin.us/residents/election-voting", "county_election_authority", 1, 3, 3,
     "official"),
    ("src-mpls", "City of Minneapolis Elections & Voter Services",
     "https://vote.minneapolismn.gov/", "municipal_election_authority", 1, 3, 3, "official"),
    ("src-mps", "Minneapolis Public Schools",
     "https://mpschools.org/", "school_authority", 1, 9, 9, "official"),
    ("src-ramsey", "Ramsey County Elections",
     "https://www.ramseycounty.us/residents/elections-voting", "county_election_authority", 1, 5, 5,
     "official"),
    ("src-stpaul", "City of Saint Paul Elections",
     "https://www.stpaul.gov/departments/city-clerk/elections-voting",
     "municipal_election_authority", 1, 6, 6, "official"),
    ("src-wi", "Wisconsin Elections Commission",
     "https://elections.wi.gov/", "state_election_authority", 1, 7, 7, "official"),
    ("src-usagov", "USA.gov", "https://www.usa.gov/how-to-vote", "federal_reference", 2, 5, 5,
     "official"),
    ("src-usagov-offices", "USA.gov", "https://www.usa.gov/state-election-office",
     "federal_reference", 2, 5, 5, "official"),
    ("src-eac-access", "U.S. Election Assistance Commission",
     "https://www.eac.gov/voting-accessibility", "federal_reference", 2, 6, 6, "official"),
    ("src-eac-canvass", "U.S. Election Assistance Commission",
     "https://www.eac.gov/election-officials/election-results-canvass-and-certification",
     "federal_reference", 2, 6, 6, "official"),
    ("src-nass", "National Association of Secretaries of State",
     "https://www.nass.org/initiatives/trustedinfo", "office_directory", 2, 8, 8, "official"),
    ("src-canivote", "CanIVote.org", "https://www.canivote.org", "office_directory", 2, 8, 8,
     "official"),
    ("src-fvap", "Federal Voting Assistance Program", "https://www.fvap.gov/",
     "federal_reference", 2, 8, 8, "official"),
    # Tier 3 aggregator: renders as `aggregated`, never as official.
    ("src-partner", "Demonstration Civic Data Partner",
     "https://example.org/civic-data/demo", "civic_data_partner", 3, 2, 2, "aggregated"),
    # Deliberately stale: last verified 76 days ago, which exceeds the 45-day LOCATION window.
    # This record must render as "Not yet confirmed" rather than as fresh.
    ("src-mpls-stale", "City of Minneapolis Elections & Voter Services",
     "https://vote.minneapolismn.gov/voters/where-to-vote/", "municipal_election_authority",
     1, 76, 76, "official"),
    # Conflicting pair: two tier-1 authorities showing different mail-return rules.
    ("src-conflict-a", "Minnesota Secretary of State",
     "https://www.sos.mn.gov/elections-voting/other-ways-to-vote/vote-early-by-mail/",
     "state_election_authority", 1, 2, 2, "official"),
    ("src-conflict-b", "Hennepin County Elections",
     "https://www.hennepin.us/residents/election-voting/absentee-voting",
     "county_election_authority", 1, 2, 2, "official"),
]

# --------------------------------------------------------------------------------------
# Jurisdictions
# --------------------------------------------------------------------------------------

JURISDICTIONS = [
    ("j-us", "United States", "federal", None, None, "ocd-division/country:us", "America/Chicago",
     "U.S. Election Assistance Commission", "https://www.eac.gov/", "1-866-747-1471",
     "clearinghouse@eac.gov", "633 3rd Street NW, Suite 200, Washington, DC 20001", "src-usagov"),
    ("j-mn", "Minnesota", "state", "j-us", "MN", "ocd-division/country:us/state:mn",
     "America/Chicago", "Minnesota Secretary of State — Elections Division",
     "https://www.sos.mn.gov/elections-voting/", "1-877-600-8683", "elections.dept@state.mn.us",
     "180 State Office Building, 100 Rev. Dr. Martin Luther King Jr. Blvd., Saint Paul, MN 55155",
     "src-mnsos"),
    ("j-hennepin", "Hennepin County", "county", "j-mn", "MN",
     "ocd-division/country:us/state:mn/county:hennepin", "America/Chicago",
     "Hennepin County Elections", "https://www.hennepin.us/residents/election-voting",
     "612-348-5151", "elections@hennepin.us",
     "Hennepin County Government Center, 300 South 6th Street, Minneapolis, MN 55487",
     "src-hennepin"),
    ("j-minneapolis", "City of Minneapolis", "municipality", "j-hennepin", "MN",
     "ocd-division/country:us/state:mn/place:minneapolis", "America/Chicago",
     "Minneapolis Elections & Voter Services", "https://vote.minneapolismn.gov/",
     "612-673-8683", "elections@minneapolismn.gov",
     "980 East Hennepin Avenue, Minneapolis, MN 55414", "src-mpls"),
    ("j-mps", "Minneapolis Public Schools (Special School District No. 1)", "school",
     "j-minneapolis", "MN", "ocd-division/country:us/state:mn/school_district:minneapolis",
     "America/Chicago", "Minneapolis Elections & Voter Services",
     "https://vote.minneapolismn.gov/", "612-673-8683", "elections@minneapolismn.gov",
     "980 East Hennepin Avenue, Minneapolis, MN 55414", "src-mps"),
    ("j-ramsey", "Ramsey County", "county", "j-mn", "MN",
     "ocd-division/country:us/state:mn/county:ramsey", "America/Chicago",
     "Ramsey County Elections", "https://www.ramseycounty.us/residents/elections-voting",
     "651-266-2171", "elections@ramseycounty.us",
     "90 Plato Boulevard West, Suite 160, Saint Paul, MN 55107", "src-ramsey"),
    ("j-stpaul", "City of Saint Paul", "municipality", "j-ramsey", "MN",
     "ocd-division/country:us/state:mn/place:saint_paul", "America/Chicago",
     "Saint Paul City Clerk — Elections",
     "https://www.stpaul.gov/departments/city-clerk/elections-voting", "651-266-8683",
     "elections@ci.stpaul.mn.us", "15 West Kellogg Boulevard, Saint Paul, MN 55102", "src-stpaul"),
    ("j-wi", "Wisconsin", "state", "j-us", "WI", "ocd-division/country:us/state:wi",
     "America/Chicago", "Wisconsin Elections Commission", "https://elections.wi.gov/",
     "608-261-2028", "elections@wi.gov", "201 West Washington Avenue, Madison, WI 53703", "src-wi"),
]

POSTAL_HINTS = [
    ("55418", "j-minneapolis", "likely"), ("55418", "j-hennepin", "likely"),
    ("55418", "j-mn", "exact"), ("55418", "j-mps", "likely"),
    ("55407", "j-minneapolis", "likely"), ("55407", "j-hennepin", "likely"),
    ("55407", "j-mn", "exact"), ("55407", "j-mps", "likely"),
    ("55106", "j-stpaul", "likely"), ("55106", "j-ramsey", "likely"),
    ("55106", "j-mn", "exact"),
    # A ZIP that genuinely straddles two municipalities: must resolve as ambiguous, not guessed.
    ("55429", "j-minneapolis", "ambiguous"), ("55429", "j-hennepin", "likely"),
    ("55429", "j-mn", "exact"),
]

DISTRICTS = [
    ("d-us-house-5", "j-mn", "us_house", "U.S. House District 5", "5", "src-mnsos"),
    ("d-mn-house-61b", "j-mn", "state_house", "State House District 61B", "61B", "src-mnsos"),
    ("d-mn-senate-61", "j-mn", "state_senate", "State Senate District 61", "61", "src-mnsos"),
    ("d-hen-comm-3", "j-hennepin", "county_commissioner", "County Commissioner District 3", "3",
     "src-hennepin"),
    ("d-mpls-ward-6", "j-minneapolis", "city_ward", "Minneapolis Ward 6", "6", "src-mpls"),
    ("d-mps-atlarge", "j-mps", "school_at_large", "School Board At-Large", None, "src-mps"),
    ("d-stp-ward-2", "j-stpaul", "city_ward", "Saint Paul Ward 2", "2", "src-stpaul"),
]

# --------------------------------------------------------------------------------------
# Elections
# --------------------------------------------------------------------------------------

ELECTIONS = [
    ("e-mn-2026-primary", "State Primary Election", "primary", "2026-08-11", "j-mn", "2026",
     "src-mnsos-cal"),
    ("e-mpls-ward6-special", "Special Election — Minneapolis Ward 6 City Council", "special",
     "2026-09-15", "j-minneapolis", "2026", "src-mpls"),
    ("e-mn-2026-general", "State General Election", "general", "2026-11-03", "j-mn", "2026",
     "src-mnsos-cal"),
    ("e-stpaul-2026-general", "Saint Paul Municipal General Election", "municipal", "2026-11-03",
     "j-stpaul", "2026", "src-stpaul"),
]

ELECTION_JURISDICTIONS = [
    ("e-mn-2026-primary", "j-mn", "This is a statewide election in Minnesota."),
    ("e-mn-2026-primary", "j-hennepin", "Your county administers this election for your address."),
    ("e-mn-2026-primary", "j-minneapolis", "Your city administers polling places for this election."),
    ("e-mpls-ward6-special", "j-minneapolis",
     "This special election covers Minneapolis Ward 6, which includes this address."),
    ("e-mpls-ward6-special", "j-hennepin", "Your county administers ballots for this election."),
    ("e-mn-2026-general", "j-mn", "This is a statewide election in Minnesota."),
    ("e-mn-2026-general", "j-hennepin", "Your county has contests on this ballot."),
    ("e-mn-2026-general", "j-minneapolis", "Your city has contests on this ballot."),
    ("e-mn-2026-general", "j-mps", "Your school district has contests on this ballot."),
    ("e-mn-2026-general", "j-ramsey", "Your county has contests on this ballot."),
    ("e-stpaul-2026-general", "j-stpaul", "Your city administers this municipal election."),
    ("e-stpaul-2026-general", "j-ramsey", "Your county administers ballots for this election."),
]

# --------------------------------------------------------------------------------------
# Deadlines
# --------------------------------------------------------------------------------------
# (id, election, jurisdiction, action, occurs_at_utc, all_day, methods, scope, exception, source)
D = "2026"
DEADLINES = [
    ("dl-gen-reg", "e-mn-2026-general", "j-mn", "register", "2026-10-14T04:59:00+00:00", 1, "all",
     "Applies to registration submitted in advance.",
     "Minnesota also reports Election Day registration at the polling place with proof of residence.",
     "src-mnsos"),
    ("dl-gen-request", "e-mn-2026-general", "j-hennepin", "request_ballot",
     "2026-11-03T19:00:00+00:00", 0, "mail",
     "Applies to requests for a mail ballot to be sent by mail.", None, "src-hennepin"),
    ("dl-gen-early-start", "e-mn-2026-general", "j-mn", "early_vote_start",
     "2026-09-18T13:00:00+00:00", 0, "early", "Early in-person voting begins.", None, "src-mnsos"),
    ("dl-gen-early-end", "e-mn-2026-general", "j-mn", "early_vote_end",
     "2026-11-02T22:00:00+00:00", 0, "early", "Last day of early in-person voting.", None,
     "src-mnsos"),
    # Two tier-1 authorities disagree here on the mail-return rule. Rendered as a conflict.
    ("dl-gen-return-a", "e-mn-2026-general", "j-mn", "return_receipt",
     "2026-11-04T02:00:00+00:00", 0, "mail",
     "State source: mail ballots must be received by the close of polls on Election Day.", None,
     "src-conflict-a"),
    ("dl-gen-return-b", "e-mn-2026-general", "j-hennepin", "return_receipt",
     "2026-11-06T02:00:00+00:00", 0, "mail",
     "County source: shows a later receipt deadline for ballots postmarked by Election Day.", None,
     "src-conflict-b"),
    ("dl-gen-eday", "e-mn-2026-general", "j-mn", "election_day", "2026-11-04T02:00:00+00:00", 0,
     "all", "Polls close.", None, "src-mnsos"),
    ("dl-spec-reg", "e-mpls-ward6-special", "j-mn", "register", "2026-08-26T04:59:00+00:00", 1,
     "all", "Applies to registration submitted in advance.", None, "src-mnsos"),
    ("dl-spec-early", "e-mpls-ward6-special", "j-minneapolis", "early_vote_start",
     "2026-07-31T13:00:00+00:00", 0, "early", "Early in-person voting begins.", None, "src-mpls"),
    ("dl-spec-eday", "e-mpls-ward6-special", "j-minneapolis", "election_day",
     "2026-09-16T02:00:00+00:00", 0, "all", "Polls close.", None, "src-mpls"),
    ("dl-stp-reg", "e-stpaul-2026-general", "j-mn", "register", "2026-10-14T04:59:00+00:00", 1,
     "all", "Applies to registration submitted in advance.", None, "src-mnsos"),
    ("dl-stp-eday", "e-stpaul-2026-general", "j-stpaul", "election_day",
     "2026-11-04T02:00:00+00:00", 0, "all", "Polls close.", None, "src-stpaul"),
]

# --------------------------------------------------------------------------------------
# Locations
# --------------------------------------------------------------------------------------

LOCATIONS = [
    ("loc-mpls-early-1", "e-mn-2026-general", "j-minneapolis", "early",
     "Minneapolis Early Vote Center", "980 East Hennepin Avenue", "Minneapolis", "MN", "55414",
     "Monday–Friday, 8:00 a.m. to 4:30 p.m. Extended hours in the final week.",
     "September 18, 2026 through November 2, 2026",
     "Step-free entrance on the east side. Accessible parking available. Accessible voting "
     "equipment reported available.", "English, Spanish, Somali, Hmong reported",
     "Metro Transit routes serve East Hennepin Avenue.", "src-mpls"),
    ("loc-mpls-eday-1", "e-mn-2026-general", "j-minneapolis", "election_day",
     "Demonstration Precinct 6-2 — Community Recreation Center", "2100 Demonstration Avenue NE",
     "Minneapolis", "MN", "55418", "7:00 a.m. to 8:00 p.m. on Election Day",
     "Election Day only", "Step-free entrance. Curbside voting reported available.",
     "English reported", None, "src-mpls"),
    # Attached to the deliberately stale source: renders as "Not yet confirmed".
    ("loc-mpls-eday-2", "e-mn-2026-general", "j-minneapolis", "election_day",
     "Demonstration Precinct 6-5 — Neighborhood Library", "3400 Demonstration Street NE",
     "Minneapolis", "MN", "55418", "7:00 a.m. to 8:00 p.m. on Election Day", "Election Day only",
     "Accessibility details not confirmed for this election.", None, None, "src-mpls-stale"),
    ("loc-mpls-drop-1", "e-mn-2026-general", "j-hennepin", "drop_box",
     "Hennepin County Government Center ballot drop-off", "300 South 6th Street", "Minneapolis",
     "MN", "55487", "Staffed drop-off during business hours; check before travelling.",
     "Through 3:00 p.m. on Election Day", "Step-free entrance from South 6th Street.", None,
     "Accessible by light rail and multiple bus routes.", "src-hennepin"),
    ("loc-hen-office", "e-mn-2026-general", "j-hennepin", "office",
     "Hennepin County Elections office", "300 South 6th Street", "Minneapolis", "MN", "55487",
     "Monday–Friday, 8:00 a.m. to 4:30 p.m.", "Year-round", "Step-free entrance.", None, None,
     "src-hennepin"),
    ("loc-spec-early", "e-mpls-ward6-special", "j-minneapolis", "early",
     "Minneapolis Early Vote Center", "980 East Hennepin Avenue", "Minneapolis", "MN", "55414",
     "Monday–Friday, 8:00 a.m. to 4:30 p.m.", "July 31, 2026 through September 14, 2026",
     "Step-free entrance on the east side.", "English, Spanish, Somali, Hmong reported", None,
     "src-mpls"),
]

# --------------------------------------------------------------------------------------
# Rules
# --------------------------------------------------------------------------------------

RULES = [
    ("r-mn-elig", "j-mn", "eligibility", "Who may register in Minnesota",
     "The state election office reports that a person may register if they are a U.S. citizen, will "
     "be at least 18 years old on Election Day, and will have lived in Minnesota for at least 20 "
     "days. It also reports conditions related to felony convictions and guardianship. You may be "
     "eligible even if you are unsure — confirm with the election office.", "2026-01-01", "src-mnsos"),
    ("r-mn-id", "j-mn", "id", "Identification reported for registration and voting",
     "The state election office reports that identification requirements differ between registering "
     "in advance, registering at the polling place on Election Day, and voting once registered. "
     "Check the linked official page for the current list of accepted documents before you go.",
     "2026-01-01", "src-mnsos"),
    ("r-mn-reg", "j-mn", "registration", "How registration is reported to work",
     "The state election office reports registration online, by mail, and in person, and reports "
     "that a voter may also register at the polling place on Election Day with proof of residence.",
     "2026-01-01", "src-mnsos"),
    ("r-mn-party", "j-mn", "party", "Party participation in a primary",
     "The state election office reports how a voter participates in a party primary. Rules for "
     "primaries vary by state. Check your election office for how it works where you vote.",
     "2026-01-01", "src-mnsos"),
    ("r-mn-mail", "j-mn", "mail", "Voting by mail",
     "The state election office reports that any eligible voter may request a mail ballot without "
     "giving a reason, and reports separate instructions for completing and returning the ballot. "
     "Two sources currently show different return deadlines for this election — see the deadline "
     "notice on the election page.", "2026-01-01", "src-mnsos"),
    ("r-mn-prov", "j-mn", "provisional", "If there is a question about your ballot",
     "Procedures for resolving a question about a ballot vary by state, and not every state uses a "
     "provisional ballot. Ask the election judges at your polling place, or contact the election "
     "office.", "2026-01-01", "src-mnsos"),
    ("r-mn-assist", "j-mn", "assistance", "Help with voting",
     "The U.S. Election Assistance Commission publishes guidance on accessible registration, "
     "accessible in-person voting, accessible vote-by-mail, and assistance for voters with "
     "disabilities. Your local election office can confirm what is available at your location.",
     "2026-01-01", "src-eac-access"),
    ("r-mn-lang", "j-mn", "language", "Language assistance",
     "Language assistance available at a polling place is reported by the local election office. "
     "Where this product shows a translation of official text, the original official text remains "
     "the authority.", "2026-01-01", "src-eac-access"),
    ("r-mn-uocava", "j-mn", "uocava", "Military and overseas voting",
     "The Federal Voting Assistance Program publishes registration and ballot-return information for "
     "military and overseas voters, including state-specific instructions.", "2026-01-01",
     "src-fvap"),
    ("r-wi-elig", "j-wi", "eligibility", "Who may register in Wisconsin",
     "The state election office publishes eligibility requirements. We have not yet reviewed local "
     "coverage for Wisconsin, so use the official link below.", "2026-01-01", "src-wi"),
]

# --------------------------------------------------------------------------------------
# Contests, candidates, measures
# --------------------------------------------------------------------------------------
# (id, election, jurisdiction, district, level, office, seats, term, classification,
#  order_rule, coverage, coverage_note, why_relevant, source)

CONTESTS = [
    ("c-gen-ussenate", "e-mn-2026-general", "j-mn", None, "federal", "United States Senator", 1,
     "6-year term", "partisan", "alphabetical", "official", None,
     "This office is elected statewide, and your address is in Minnesota.", "src-mnsos"),
    ("c-gen-ushouse5", "e-mn-2026-general", "j-mn", "d-us-house-5", "federal",
     "United States Representative, District 5", 1, "2-year term", "partisan", "official_ballot",
     "official", None, "Your address is in U.S. House District 5.", "src-mnsos"),
    ("c-gen-gov", "e-mn-2026-general", "j-mn", None, "state", "Governor and Lieutenant Governor", 1,
     "4-year term", "partisan", "alphabetical", "official", None,
     "This office is elected statewide, and your address is in Minnesota.", "src-mnsos"),
    ("c-gen-house61b", "e-mn-2026-general", "j-mn", "d-mn-house-61b", "state",
     "State Representative, District 61B", 1, "2-year term", "partisan", "alphabetical", "official",
     None, "Your address is in State House District 61B.", "src-mnsos"),
    ("c-gen-supreme", "e-mn-2026-general", "j-mn", None, "judicial",
     "Associate Justice, Minnesota Supreme Court, Seat 3", 1, "6-year term", "nonpartisan",
     "alphabetical", "official", None,
     "Judicial seats on this court are elected statewide.", "src-mnsos"),
    ("c-gen-commissioner", "e-mn-2026-general", "j-hennepin", "d-hen-comm-3", "county",
     "County Commissioner, District 3", 1, "4-year term", "nonpartisan", "alphabetical", "official",
     None, "Your address is in Hennepin County Commissioner District 3.", "src-hennepin"),
    ("c-gen-council6", "e-mn-2026-general", "j-minneapolis", "d-mpls-ward-6", "municipal",
     "Minneapolis City Council, Ward 6", 1, "4-year term", "nonpartisan", "alphabetical", "official",
     None, "Your address is in Minneapolis Ward 6.", "src-mpls"),
    ("c-gen-school", "e-mn-2026-general", "j-mps", "d-mps-atlarge", "education",
     "Minneapolis School Board, At-Large", 2, "4-year term", "nonpartisan", "alphabetical",
     "official", None, "Your address is in Minneapolis Public Schools.", "src-mps"),
    ("c-gen-park", "e-mn-2026-general", "j-minneapolis", None, "special",
     "Park and Recreation Board, At-Large", 3, "4-year term", "nonpartisan", "alphabetical",
     "partial",
     "Filing for this contest was still open when this data was retrieved. This list may be "
     "incomplete.", "This board is elected across the City of Minneapolis.", "src-mpls"),
    ("c-gen-cityq1", "e-mn-2026-general", "j-minneapolis", None, "measure",
     "City Question 1", 1, None, "measure", "alphabetical", "official", None,
     "This question appears on ballots in the City of Minneapolis.", "src-mpls"),
    ("c-gen-schoolq1", "e-mn-2026-general", "j-mps", None, "measure",
     "School District Question 1", 1, None, "measure", "alphabetical", "official", None,
     "This question appears on ballots in Minneapolis Public Schools.", "src-mps"),
    # A contest we know exists but have no candidate data for. Must not render as an empty list.
    ("c-gen-soil", "e-mn-2026-general", "j-hennepin", None, "special",
     "Soil and Water Conservation District Supervisor, District 2", 1, "4-year term", "nonpartisan",
     "alphabetical", "pending",
     "We do not yet have reliable candidate data for this contest.",
     "This district covers part of Hennepin County, including your address.", "src-hennepin"),
    ("c-spec-council6", "e-mpls-ward6-special", "j-minneapolis", "d-mpls-ward-6", "municipal",
     "Minneapolis City Council, Ward 6 (unexpired term)", 1, "Unexpired term ending January 2028",
     "nonpartisan", "alphabetical", "official", None,
     "This special election covers Minneapolis Ward 6.", "src-mpls"),
    ("c-prim-gov", "e-mn-2026-primary", "j-mn", None, "state",
     "Governor and Lieutenant Governor — party nomination", 1, None, "partisan", "alphabetical",
     "official", None, "This nomination was decided statewide.", "src-mnsos"),
    ("c-prim-council6", "e-mn-2026-primary", "j-minneapolis", "d-mpls-ward-6", "municipal",
     "Minneapolis City Council, Ward 6 — primary", 1, None, "nonpartisan", "alphabetical",
     "official", None, "Your address is in Minneapolis Ward 6.", "src-mpls"),
    ("c-stp-council2", "e-stpaul-2026-general", "j-stpaul", "d-stp-ward-2", "municipal",
     "Saint Paul City Council, Ward 2", 1, "4-year term", "nonpartisan", "alphabetical",
     "aggregated",
     "This list comes from a third-party data partner and has not yet been confirmed against the "
     "Saint Paul City Clerk.", "Your address is in Saint Paul Ward 2.", "src-partner"),
]

# (id, contest, ballot_name, ballot_position, filing_status, party, incumbent_source,
#  website, filing_url, bio, bio_by, source)
CANDIDATES = [
    ("cd-sen-1", "c-gen-ussenate", "Aldridge, Marion T.", 2, "qualified",
     "Demonstration Party A", None, "https://example.org/demo/aldridge",
     "https://www.fec.gov/data/", "Provided biography not supplied for this demonstration record.",
     None, "src-mnsos"),
    ("cd-sen-2", "c-gen-ussenate", "Okonkwo, Baxter", 1, "qualified", "Demonstration Party B",
     "Minnesota Secretary of State candidate filing list",
     "https://example.org/demo/okonkwo", "https://www.fec.gov/data/",
     "Demonstration biography supplied by the campaign for this sample record.", "Candidate",
     "src-mnsos"),
    ("cd-sen-3", "c-gen-ussenate", "Vashti, Corliss J.", 3, "qualified", "Demonstration Party C",
     None, None, "https://www.fec.gov/data/", None, None, "src-mnsos"),
    ("cd-h5-1", "c-gen-ushouse5", "Brennerman, Sofia", 1, "qualified", "Demonstration Party B",
     None, "https://example.org/demo/brennerman", "https://www.fec.gov/data/", None, None,
     "src-mnsos"),
    ("cd-h5-2", "c-gen-ushouse5", "Zaleski, Ruth Ann", 2, "qualified", "Demonstration Party A",
     None, None, "https://www.fec.gov/data/", None, None, "src-mnsos"),
    # Withdrawn candidate: retained and marked, never deleted.
    ("cd-h5-3", "c-gen-ushouse5", "Calloway, Dennis P.", 3, "withdrawn", "Demonstration Party C",
     None, None, "https://www.fec.gov/data/", None, None, "src-mnsos"),
    ("cd-gov-1", "c-gen-gov", "Fairbanks, Louise / Ortega, Ramon", None, "qualified",
     "Demonstration Party A", None, None, None, None, None, "src-mnsos"),
    ("cd-gov-2", "c-gen-gov", "Nakamura, Grace / Boyd, Terrell", None, "qualified",
     "Demonstration Party B", "Minnesota Secretary of State candidate filing list", None, None,
     None, None, "src-mnsos"),
    ("cd-61b-1", "c-gen-house61b", "Iverson, Hollis", None, "qualified", "Demonstration Party B",
     None, None, None, None, None, "src-mnsos"),
    ("cd-61b-2", "c-gen-house61b", "Petrov, Anya K.", None, "qualified", "Demonstration Party A",
     None, None, None, None, None, "src-mnsos"),
    ("cd-sup-1", "c-gen-supreme", "Harrow, Beatrice", None, "qualified", None,
     "Minnesota Secretary of State candidate filing list", None, None, None, None, "src-mnsos"),
    ("cd-sup-2", "c-gen-supreme", "Ellingson, Marcus", None, "qualified", None, None, None, None,
     None, None, "src-mnsos"),
    ("cd-com-1", "c-gen-commissioner", "Duval, Priya", None, "qualified", None, None, None, None,
     None, None, "src-hennepin"),
    ("cd-com-2", "c-gen-commissioner", "Stallworth, Odell", None, "qualified", None, None, None,
     None, None, None, "src-hennepin"),
    ("cd-cc6-1", "c-gen-council6", "Achebe, Nnamdi", None, "qualified", None, None,
     "https://example.org/demo/achebe", None, None, None, "src-mpls"),
    ("cd-cc6-2", "c-gen-council6", "Lindqvist, Marta", None, "qualified", None,
     "Minneapolis Elections & Voter Services filing list", None, None, None, None, "src-mpls"),
    ("cd-cc6-3", "c-gen-council6", "Whitfield, Cyrus", None, "qualified", None, None, None, None,
     None, None, "src-mpls"),
    ("cd-sch-1", "c-gen-school", "Boateng, Adwoa", None, "qualified", None, None, None, None, None,
     None, "src-mps"),
    ("cd-sch-2", "c-gen-school", "Kovalenko, Iryna", None, "qualified", None, None, None, None,
     None, None, "src-mps"),
    ("cd-sch-3", "c-gen-school", "Reyes-Ortiz, Dolores", None, "qualified", None, None, None, None,
     None, None, "src-mps"),
    ("cd-sch-4", "c-gen-school", "Tomlinson, Reginald", None, "qualified", None, None, None, None,
     None, None, "src-mps"),
    ("cd-park-1", "c-gen-park", "Dunmore, Hattie", None, "filed", None, None, None, None, None,
     None, "src-mpls"),
    ("cd-park-2", "c-gen-park", "Yusuf, Idris", None, "filed", None, None, None, None, None, None,
     "src-mpls"),
    ("cd-spec-1", "c-spec-council6", "Achebe, Nnamdi", None, "qualified", None, None, None, None,
     None, None, "src-mpls"),
    ("cd-spec-2", "c-spec-council6", "Lindqvist, Marta", None, "qualified", None, None, None, None,
     None, None, "src-mpls"),
    ("cd-prim-gov-1", "c-prim-gov", "Fairbanks, Louise", None, "qualified", "Demonstration Party A",
     None, None, None, None, None, "src-mnsos"),
    ("cd-prim-gov-2", "c-prim-gov", "Underhill, Josiah", None, "qualified", "Demonstration Party A",
     None, None, None, None, None, "src-mnsos"),
    ("cd-prim-cc6-1", "c-prim-council6", "Achebe, Nnamdi", None, "qualified", None, None, None,
     None, None, None, "src-mpls"),
    ("cd-prim-cc6-2", "c-prim-council6", "Lindqvist, Marta", None, "qualified", None, None, None,
     None, None, None, "src-mpls"),
    ("cd-prim-cc6-3", "c-prim-council6", "Whitfield, Cyrus", None, "qualified", None, None, None,
     None, None, None, "src-mpls"),
    ("cd-stp-1", "c-stp-council2", "Halvorsen, Ingrid", None, "filed", None, None, None, None,
     None, None, "src-partner"),
    ("cd-stp-2", "c-stp-council2", "Mbeki, Thandiwe", None, "filed", None, None, None, None, None,
     None, "src-partner"),
]

QUESTIONNAIRE_ITEMS = [
    ("qi-cc6-1", "c-gen-council6", 1,
     "What are your top three priorities for this office, in your own words?"),
    ("qi-cc6-2", "c-gen-council6", 2,
     "What experience do you consider most relevant to this office?"),
    ("qi-cc6-3", "c-gen-council6", 3,
     "How can constituents contact you or your campaign?"),
]

# Deliberately partial: one candidate answers all, one answers some, one answers none.
# The unanswered items must still render, as "No response provided".
QUESTIONNAIRE_RESPONSES = [
    ("qr-1", "cd-cc6-1", "qi-cc6-1",
     "Demonstration response supplied by the candidate for this sample record.", "src-mpls"),
    ("qr-2", "cd-cc6-1", "qi-cc6-2",
     "Demonstration response supplied by the candidate for this sample record.", "src-mpls"),
    ("qr-3", "cd-cc6-1", "qi-cc6-3",
     "Demonstration response supplied by the candidate for this sample record.", "src-mpls"),
    ("qr-4", "cd-cc6-2", "qi-cc6-1",
     "Demonstration response supplied by the candidate for this sample record.", "src-mpls"),
]

MEASURES = [
    ("m-cityq1", "c-gen-cityq1",
     "City Question 1: Demonstration Charter Amendment",
     "Shall the demonstration city charter be amended to establish a demonstration department, as "
     "set out in the full text of the proposed amendment? This is sample ballot text created for a "
     "demonstration and is not a real ballot question.",
     "Charter amendment",
     "Demonstration explanatory note prepared by the demonstration city clerk.",
     "Demonstration city clerk",
     "The demonstration fiscal note reports no immediate change to the property tax levy.",
     "https://vote.minneapolismn.gov/", "src-mpls"),
    ("m-schoolq1", "c-gen-schoolq1",
     "School District Question 1: Demonstration Operating Referendum",
     "Shall the demonstration school district's operating referendum revenue authorization be "
     "renewed as proposed? This is sample ballot text created for a demonstration and is not a real "
     "ballot question.",
     "Operating referendum",
     "Demonstration explanatory note prepared by the demonstration school district.",
     "Demonstration school district",
     "The demonstration fiscal note reports a renewal of an existing authorization.",
     "https://mpschools.org/", "src-mps"),
]

# Equal counts, equal treatment, both attributed.
MEASURE_ARGUMENTS = [
    ("ma-1", "m-cityq1", "for",
     "Demonstration argument in favor, reproduced as submitted to the demonstration voter guide.",
     "Demonstration committee in favor", "src-mpls"),
    ("ma-2", "m-cityq1", "against",
     "Demonstration argument in opposition, reproduced as submitted to the demonstration voter "
     "guide.", "Demonstration committee in opposition", "src-mpls"),
    ("ma-3", "m-schoolq1", "for",
     "Demonstration argument in favor, reproduced as submitted to the demonstration voter guide.",
     "Demonstration committee in favor", "src-mps"),
    ("ma-4", "m-schoolq1", "against",
     "Demonstration argument in opposition, reproduced as submitted to the demonstration voter "
     "guide.", "Demonstration committee in opposition", "src-mps"),
]

# Past primary: a certified contest and an uncertified one, so both states are demonstrable.
RESULTS = [
    ("rs-1", "c-prim-gov", "cd-prim-gov-1", None, 184203, 4128, 4128, "certified",
     "Minnesota State Canvassing Board", "2026-08-25T16:00:00+00:00",
     "2026-08-25T16:00:00+00:00", "src-mnsos"),
    ("rs-2", "c-prim-gov", "cd-prim-gov-2", None, 121887, 4128, 4128, "certified",
     "Minnesota State Canvassing Board", "2026-08-25T16:00:00+00:00",
     "2026-08-25T16:00:00+00:00", "src-mnsos"),
    ("rs-3", "c-prim-council6", "cd-prim-cc6-1", None, 3120, 12, 14, "unofficial", None, None,
     "2026-08-12T04:30:00+00:00", "src-mpls"),
    ("rs-4", "c-prim-council6", "cd-prim-cc6-2", None, 2984, 12, 14, "unofficial", None, None,
     "2026-08-12T04:30:00+00:00", "src-mpls"),
    ("rs-5", "c-prim-council6", "cd-prim-cc6-3", None, 1105, 12, 14, "unofficial", None, None,
     "2026-08-12T04:30:00+00:00", "src-mpls"),
]

COVERAGE = {
    "j-mn": {"ELECTION": "official", "DEADLINE": "official", "LOCATION": "partial",
             "RULES": "official", "CONTEST": "official", "CANDIDATE": "official",
             "MEASURE": "official", "RESULT": "pending", "ADMIN": "official"},
    "j-hennepin": {"ELECTION": "official", "DEADLINE": "official", "LOCATION": "official",
                   "RULES": "official", "CONTEST": "official", "CANDIDATE": "official",
                   "MEASURE": "none", "RESULT": "pending", "ADMIN": "official"},
    "j-minneapolis": {"ELECTION": "official", "DEADLINE": "official", "LOCATION": "official",
                      "RULES": "verified", "CONTEST": "official", "CANDIDATE": "official",
                      "MEASURE": "official", "RESULT": "pending", "ADMIN": "official"},
    "j-mps": {"ELECTION": "official", "DEADLINE": "official", "LOCATION": "partial",
              "RULES": "verified", "CONTEST": "official", "CANDIDATE": "official",
              "MEASURE": "none", "RESULT": "pending", "ADMIN": "official"},
    "j-ramsey": {"ELECTION": "official", "DEADLINE": "official", "LOCATION": "pending",
                 "RULES": "official", "CONTEST": "partial", "CANDIDATE": "aggregated",
                 "MEASURE": "none", "RESULT": "pending", "ADMIN": "official"},
    "j-stpaul": {"ELECTION": "official", "DEADLINE": "official", "LOCATION": "pending",
                 "RULES": "verified", "CONTEST": "partial", "CANDIDATE": "aggregated",
                 "MEASURE": "none", "RESULT": "pending", "ADMIN": "official"},
    "j-wi": {"ELECTION": "none", "DEADLINE": "partial", "LOCATION": "none", "RULES": "official",
             "CONTEST": "none", "CANDIDATE": "none", "MEASURE": "none", "RESULT": "none",
             "ADMIN": "official"},
    "j-us": {"ELECTION": "none", "DEADLINE": "none", "LOCATION": "none", "RULES": "official",
             "CONTEST": "none", "CANDIDATE": "none", "MEASURE": "none", "RESULT": "none",
             "ADMIN": "official"},
}


def seed(conn: sqlite3.Connection) -> None:
    c = _ShiftingCursor(conn.cursor())
    for (sid, org, url, stype, tier, ret, ver, claimed) in SOURCES:
        c.execute(
            "INSERT OR REPLACE INTO source_record (id, organization, source_url, source_type,"
            " trust_tier, retrieved_at, published_at, last_verified_at, effective_date,"
            " content_hash, claimed_status) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (sid, org, url, stype, tier, ago(ret), ago(ret), ago(ver), "2026-01-01",
             f"demo-{sid}", claimed),
        )
        c.execute(
            "INSERT OR REPLACE INTO source_health (source_record_id, last_check_at,"
            " last_success_at, consecutive_failures, note) VALUES (?,?,?,?,?)",
            (sid, ago(min(ret, 1)), ago(ret), 0 if ret < 30 else 3,
             None if ret < 30 else "No successful check within the freshness window."),
        )

    c.executemany(
        "INSERT OR REPLACE INTO jurisdiction (id, name, type, parent_id, state_code, ocd_id,"
        " timezone, office_name, official_url, office_phone, office_email, office_address,"
        " source_record_id) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)", JURISDICTIONS)
    c.executemany(
        "INSERT OR REPLACE INTO postal_hint (postal_code, jurisdiction_id, confidence)"
        " VALUES (?,?,?)", POSTAL_HINTS)
    c.executemany(
        "INSERT OR REPLACE INTO district (id, jurisdiction_id, type, name, number,"
        " source_record_id) VALUES (?,?,?,?,?,?)", DISTRICTS)
    c.executemany(
        "INSERT OR REPLACE INTO election (id, name, type, election_date, timezone,"
        " jurisdiction_id, cycle, is_demo, status, source_record_id)"
        " VALUES (?,?,?,?,'America/Chicago',?,?,1,'official',?)", ELECTIONS)
    c.executemany(
        "INSERT OR REPLACE INTO election_jurisdiction (election_id, jurisdiction_id,"
        " relevance_note) VALUES (?,?,?)", ELECTION_JURISDICTIONS)
    c.executemany(
        "INSERT OR REPLACE INTO deadline (id, election_id, jurisdiction_id, action, occurs_at_utc,"
        " timezone, is_all_day, methods, scope_note, exception_text, source_record_id)"
        " VALUES (?,?,?,?,?,'America/Chicago',?,?,?,?,?)", DEADLINES)
    c.executemany(
        "INSERT OR REPLACE INTO voting_location (id, election_id, jurisdiction_id, type, name,"
        " address_line, city, state_code, postal_code, hours_text, date_range_text,"
        " accessibility_text, languages_text, transit_text, source_record_id)"
        " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", LOCATIONS)
    c.executemany(
        "INSERT OR REPLACE INTO rule (id, jurisdiction_id, category, title, body_text,"
        " effective_date, source_record_id) VALUES (?,?,?,?,?,?,?)", RULES)
    c.executemany(
        "INSERT OR REPLACE INTO contest (id, election_id, jurisdiction_id, district_id, level,"
        " office_name, seats, term_text, classification, order_rule, coverage, coverage_note,"
        " why_relevant, source_record_id) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)", CONTESTS)

    for (cid, contest, name, pos, filing, party, incumbent, site, filing_url, bio, bio_by,
         src) in CANDIDATES:
        c.execute(
            "INSERT OR REPLACE INTO candidate (id, contest_id, ballot_name, sort_key,"
            " ballot_position, filing_status, party_label_official, incumbent_source, website_url,"
            " filing_url, bio_text, bio_provided_by, source_record_id)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (cid, contest, name, sort_key_for(name), pos, filing, party, incumbent, site,
             filing_url, bio, bio_by, src),
        )

    c.executemany(
        "INSERT OR REPLACE INTO questionnaire_item (id, contest_id, position, prompt)"
        " VALUES (?,?,?,?)", QUESTIONNAIRE_ITEMS)
    for (qid, cand, item, text, src) in QUESTIONNAIRE_RESPONSES:
        c.execute(
            "INSERT OR REPLACE INTO questionnaire_response (id, candidate_id, item_id,"
            " response_text, responded_at, source_record_id) VALUES (?,?,?,?,?,?)",
            (qid, cand, item, text, ago(10), src))
    c.executemany(
        "INSERT OR REPLACE INTO measure (id, contest_id, official_title, ballot_text, measure_type,"
        " summary_text, summary_author, fiscal_note, full_text_url, source_record_id)"
        " VALUES (?,?,?,?,?,?,?,?,?,?)", MEASURES)
    c.executemany(
        "INSERT OR REPLACE INTO measure_argument (id, measure_id, stance, body_text, submitted_by,"
        " source_record_id) VALUES (?,?,?,?,?,?)", MEASURE_ARGUMENTS)
    c.executemany(
        "INSERT OR REPLACE INTO result (id, contest_id, candidate_id, option_label, votes,"
        " precincts_reporting, precincts_total, reporting_status, certifying_authority,"
        " certified_at, reported_at, source_record_id) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", RESULTS)

    for jid, cells in COVERAGE.items():
        for data_class, level in cells.items():
            c.execute(
                "INSERT OR REPLACE INTO coverage_cell (jurisdiction_id, data_class, level)"
                " VALUES (?,?,?)", (jid, data_class, level))

    c.execute(
        "INSERT INTO audit_log (at, actor, action, entity_table, entity_id, note)"
        " VALUES (?,?,?,?,?,?)",
        (iso(SEED_NOW), "seed-script", "seed_demo_data", None, None,
         "Loaded demonstration dataset. All elections flagged is_demo = 1."))
    conn.commit()


def main() -> None:
    conn = connect()
    init_schema(conn)
    # --if-empty is what the container runs on start. Re-seeding unconditionally would use
    # INSERT OR REPLACE against the seeded ids, silently reverting anything changed through the
    # operations console since the last restart.
    if "--if-empty" in sys.argv:
        existing = conn.execute("SELECT count(*) FROM election").fetchone()[0]
        if existing:
            print(f"Database already holds {existing} elections; leaving it alone.")
            conn.close()
            return
    seed(conn)
    counts = {t: conn.execute(f"SELECT count(*) FROM {t}").fetchone()[0]
              for t in ("jurisdiction", "election", "contest", "candidate", "measure",
                        "deadline", "voting_location", "result", "source_record")}
    conn.close()
    print("Seeded demonstration data:", counts)


if __name__ == "__main__":
    main()
