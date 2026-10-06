"""Read layer.

Nothing here returns a bare row. Every fact comes back wrapped with its computed status and its
source record, because a template must not be able to render a fact and forget the provenance.
"""
from __future__ import annotations

import sqlite3
from datetime import datetime

from .logic import (LEVEL_LABELS, LocationMatch, Status, classify_query, days_until,
                    effective_status, format_local, neutral_order, parse_iso, utc_now)

LEVEL_ORDER = ["federal", "state", "judicial", "county", "municipal", "education", "special",
               "measure"]


def _row(r: sqlite3.Row) -> dict:
    return dict(r) if r is not None else {}


def _source(conn: sqlite3.Connection, source_id: str) -> dict:
    r = conn.execute("SELECT * FROM source_record WHERE id = ?", (source_id,)).fetchone()
    return _row(r)


def wrap(conn: sqlite3.Connection, row: sqlite3.Row, data_class: str,
         election_date: str | None = None, now: datetime | None = None) -> dict:
    """Attach the source record and the computed status to a fact row."""
    d = _row(row)
    src = _source(conn, d["source_record_id"])
    d["source"] = src
    d["status"] = effective_status(
        src.get("claimed_status", "official"), src.get("trust_tier", 4),
        src.get("last_verified_at"), data_class, election_date, now=now)
    return d


# --------------------------------------------------------------------------------------
# Jurisdictions and location
# --------------------------------------------------------------------------------------

def get_jurisdiction(conn: sqlite3.Connection, jid: str) -> dict:
    return wrap(conn, conn.execute("SELECT * FROM jurisdiction WHERE id = ?", (jid,)).fetchone(),
                "ADMIN") if conn.execute(
        "SELECT 1 FROM jurisdiction WHERE id = ?", (jid,)).fetchone() else {}


def jurisdiction_chain(conn: sqlite3.Connection, jid: str) -> list[dict]:
    """The jurisdiction plus everything it sits inside, most local first, plus any child
    school/special districts. This is what a voter's ballot is actually assembled from."""
    chain: list[dict] = []
    seen: set[str] = set()
    current = jid
    while current and current not in seen:
        seen.add(current)
        j = get_jurisdiction(conn, current)
        if not j:
            break
        chain.append(j)
        current = j.get("parent_id")
    for r in conn.execute(
            "SELECT * FROM jurisdiction WHERE parent_id = ? AND type IN ('school','special')",
            (jid,)):
        j = wrap(conn, r, "ADMIN")
        if j["id"] not in seen:
            seen.add(j["id"])
            chain.insert(1, j)
    return chain


def resolve_location(conn: sqlite3.Connection, raw: str) -> LocationMatch:
    """Turn a user-entered location into jurisdictions, then forget the input.

    The raw string is classified and matched here and is never returned, logged, or written.
    Callers receive jurisdiction IDs only. See docs/04 T5.
    """
    kind, value = classify_query(raw)
    if kind == "none":
        return LocationMatch([], "none", "Enter a ZIP code, a city and state, or choose a state.",
                             "none")

    if kind == "postal":
        rows = conn.execute(
            "SELECT j.*, h.confidence FROM postal_hint h JOIN jurisdiction j"
            " ON j.id = h.jurisdiction_id WHERE h.postal_code = ?", (value,)).fetchall()
        if not rows:
            return LocationMatch([], "none",
                                 "We do not have jurisdiction data for this ZIP code yet.",
                                 "postal")
        js = [wrap(conn, r, "ADMIN") for r in rows]
        ambiguous = any(r["confidence"] == "ambiguous" for r in rows)
        if ambiguous:
            return LocationMatch(
                js, "ambiguous",
                "This ZIP code covers more than one city. Choose the one where you are registered, "
                "or confirm with your election office.", "postal")
        return LocationMatch(
            js, "likely",
            "A ZIP code is a mailing boundary, not a voting boundary. Confirm these jurisdictions "
            "before viewing your ballot.", "postal")

    if kind == "state":
        rows = conn.execute("SELECT * FROM jurisdiction WHERE state_code = ? AND type = 'state'",
                            (value,)).fetchall()
        js = [wrap(conn, r, "ADMIN") for r in rows]
        return LocationMatch(js, "likely" if js else "none",
                             "Statewide match only. Add a city or ZIP code for local elections.",
                             "state")

    # city_state
    text = value.lower()
    rows = conn.execute(
        "SELECT * FROM jurisdiction WHERE type IN ('municipality','county','state')").fetchall()
    hits = [r for r in rows if r["name"].lower().split(",")[0].replace("city of ", "") in text
            or r["name"].lower() in text]
    if not hits:
        return LocationMatch([], "none",
                             "We could not match that place. Choose a state to continue, or use "
                             "your election office directly.", "city_state")
    js = [wrap(conn, r, "ADMIN") for r in hits]
    return LocationMatch(js, "likely",
                         "We found these jurisdictions for this location. Confirm before viewing "
                         "your ballot.", "city_state")


def coverage_for(conn: sqlite3.Connection, jid: str) -> dict[str, str]:
    return {r["data_class"]: r["level"] for r in conn.execute(
        "SELECT data_class, level FROM coverage_cell WHERE jurisdiction_id = ?", (jid,))}


def full_coverage_matrix(conn: sqlite3.Connection) -> list[dict]:
    out = []
    for j in conn.execute("SELECT * FROM jurisdiction ORDER BY type, name"):
        out.append({"jurisdiction": _row(j), "cells": coverage_for(conn, j["id"])})
    return out


# --------------------------------------------------------------------------------------
# Elections
# --------------------------------------------------------------------------------------

def elections_for_jurisdictions(conn: sqlite3.Connection, jids: list[str],
                                window: str = "all", now: datetime | None = None) -> list[dict]:
    if not jids:
        return []
    now = now or utc_now()
    placeholders = ",".join("?" * len(jids))
    # One row per election, not one per matching jurisdiction. A location resolves to a chain of
    # five or more jurisdictions, and an election attached to several of them would otherwise be
    # listed once per attachment — the reader would see the same election four times and have no
    # way to tell whether that meant four separate elections.
    rows = conn.execute(
        f"SELECT e.*, group_concat(ej.relevance_note, '\n') AS relevance_notes FROM election e"
        f" JOIN election_jurisdiction ej ON ej.election_id = e.id"
        f" WHERE ej.jurisdiction_id IN ({placeholders})"
        f" GROUP BY e.id"
        f" ORDER BY e.election_date, e.id", tuple(jids)).fetchall()
    out = []
    for r in rows:
        e = wrap(conn, r, "ELECTION", r["election_date"], now=now)
        # Every reason this election reached the reader, de-duplicated and order-stable, so the
        # "why am I seeing this?" answer names all the jurisdictions involved rather than one.
        notes = [n for n in (r["relevance_notes"] or "").split("\n") if n.strip()]
        e["relevance_notes"] = list(dict.fromkeys(notes))
        e["relevance_note"] = e["relevance_notes"][0] if e["relevance_notes"] else None
        e["days_away"] = days_until(r["election_date"], r["timezone"], now)
        e["is_past"] = e["days_away"] < 0
        e["date_display"] = format_local(r["election_date"], r["timezone"], all_day=True)
        if e["is_past"]:
            e["status"] = Status("historical", "Past election",
                                 "This applies to a past election and should not be used for a "
                                 "current one.")
        out.append(e)

    if window == "30":
        out = [e for e in out if 0 <= e["days_away"] <= 30]
    elif window == "upcoming":
        out = [e for e in out if not e["is_past"]]
    elif window == "past":
        out = [e for e in out if e["is_past"]]
    elif window == "registration_open":
        out = [e for e in out if not e["is_past"] and any(
            d["action"] == "register" and d["days_away"] >= 0
            for d in deadlines_for(conn, e["id"], jids, now=now)["items"])]
    elif window == "voting_now":
        out = [e for e in out if not e["is_past"] and _voting_open(conn, e["id"], jids, now)]
    return out


def _voting_open(conn: sqlite3.Connection, eid: str, jids: list[str],
                 now: datetime | None) -> bool:
    items = deadlines_for(conn, eid, jids, now=now)["items"]
    start = next((d for d in items if d["action"] == "early_vote_start"), None)
    end = next((d for d in items if d["action"] in ("early_vote_end", "election_day")), None)
    if not start:
        return False
    return start["days_away"] <= 0 and (end is None or end["days_away"] >= 0)


def get_election(conn: sqlite3.Connection, eid: str, now: datetime | None = None) -> dict:
    r = conn.execute("SELECT * FROM election WHERE id = ?", (eid,)).fetchone()
    if not r:
        return {}
    e = wrap(conn, r, "ELECTION", r["election_date"], now=now)
    e["days_away"] = days_until(r["election_date"], r["timezone"], now)
    e["is_past"] = e["days_away"] < 0
    e["date_display"] = format_local(r["election_date"], r["timezone"], all_day=True)
    e["jurisdictions"] = [dict(x) for x in conn.execute(
        "SELECT j.*, ej.relevance_note FROM election_jurisdiction ej"
        " JOIN jurisdiction j ON j.id = ej.jurisdiction_id WHERE ej.election_id = ?", (eid,))]
    return e


# --------------------------------------------------------------------------------------
# Deadlines, with conflict detection
# --------------------------------------------------------------------------------------

ACTION_ORDER = ["register", "request_ballot", "early_vote_start", "early_vote_end",
                "return_postmark", "return_receipt", "cure", "election_day"]

METHOD_ACTIONS = {
    "election_day": ["register", "election_day"],
    "early": ["register", "early_vote_start", "early_vote_end"],
    "mail": ["register", "request_ballot", "return_postmark", "return_receipt", "cure"],
    "drop_off": ["register", "request_ballot", "return_receipt", "cure", "election_day"],
    "uocava": ["register", "request_ballot", "return_postmark", "return_receipt"],
    "unsure": ACTION_ORDER,
}


def deadlines_for(conn: sqlite3.Connection, eid: str, jids: list[str] | None = None,
                  method: str = "unsure", now: datetime | None = None) -> dict:
    """Return deadlines plus any tier-1 conflicts.

    Where two tier-1 authorities disagree on the same action, we surface both and route the reader
    to the election office. We do not silently pick the earlier or later one — an unearned choice
    here is precisely how a voter misses a deadline.
    """
    election = get_election(conn, eid, now=now)
    if not election:
        return {"items": [], "conflicts": []}
    params: list = [eid]
    sql = "SELECT * FROM deadline WHERE election_id = ?"
    if jids:
        sql += f" AND jurisdiction_id IN ({','.join('?' * len(jids))})"
        params += jids
    rows = conn.execute(sql, tuple(params)).fetchall()

    by_action: dict[str, list[dict]] = {}
    for r in rows:
        d = wrap(conn, r, "DEADLINE", election["election_date"], now=now)
        d["days_away"] = days_until(r["occurs_at_utc"], r["timezone"], now)
        d["display"] = format_local(r["occurs_at_utc"], r["timezone"], bool(r["is_all_day"]))
        d["is_past"] = d["days_away"] < 0
        by_action.setdefault(r["action"], []).append(d)

    allowed = METHOD_ACTIONS.get(method, ACTION_ORDER)
    items, conflicts = [], []
    for action in ACTION_ORDER:
        group = by_action.get(action, [])
        if not group:
            continue
        tier1 = [d for d in group if d["source"]["trust_tier"] == 1]
        distinct = {d["occurs_at_utc"] for d in tier1}
        if len(distinct) > 1:
            conflict = {
                "action": action,
                "options": sorted(group, key=lambda d: d["occurs_at_utc"]),
                "status": Status("conflicting", "Sources disagree",
                                 "Two sources show different information. Check the official "
                                 "election office before acting."),
            }
            conflicts.append(conflict)
            chosen = min(group, key=lambda d: d["occurs_at_utc"])
            chosen = dict(chosen)
            chosen["status"] = conflict["status"]
            chosen["conflict"] = conflict
            if action in allowed:
                items.append(chosen)
            continue
        chosen = group[0]
        if action in allowed:
            items.append(chosen)
    items.sort(key=lambda d: d["occurs_at_utc"])
    return {"items": items, "conflicts": conflicts}


# --------------------------------------------------------------------------------------
# Locations
# --------------------------------------------------------------------------------------

LOCATION_TYPES = [
    ("election_day", "Election Day voting locations"),
    ("early", "Early voting locations"),
    ("drop_box", "Ballot drop-off locations"),
    ("office", "Election offices"),
]


def locations_for(conn: sqlite3.Connection, eid: str, jids: list[str] | None = None,
                  now: datetime | None = None) -> list[dict]:
    election = get_election(conn, eid, now=now)
    params: list = [eid]
    sql = "SELECT * FROM voting_location WHERE election_id = ?"
    if jids:
        sql += f" AND jurisdiction_id IN ({','.join('?' * len(jids))})"
        params += jids
    rows = conn.execute(sql + " ORDER BY name", tuple(params)).fetchall()
    grouped: dict[str, list[dict]] = {}
    for r in rows:
        grouped.setdefault(r["type"], []).append(
            wrap(conn, r, "LOCATION", election.get("election_date"), now=now))
    return [{"type": t, "label": label, "items": grouped.get(t, [])}
            for t, label in LOCATION_TYPES]


# --------------------------------------------------------------------------------------
# Ballot
# --------------------------------------------------------------------------------------

def candidates_for(conn: sqlite3.Connection, contest: dict,
                   now: datetime | None = None) -> list[dict]:
    rows = conn.execute("SELECT * FROM candidate WHERE contest_id = ?", (contest["id"],)).fetchall()
    cands = [wrap(conn, r, "CANDIDATE", contest.get("_election_date"), now=now) for r in rows]
    ordered = neutral_order(cands, contest.get("order_rule", "alphabetical"))
    items = [dict(x) for x in conn.execute(
        "SELECT * FROM questionnaire_item WHERE contest_id = ? ORDER BY position",
        (contest["id"],))]
    for c in ordered:
        responses = {r["item_id"]: dict(r) for r in conn.execute(
            "SELECT * FROM questionnaire_response WHERE candidate_id = ?", (c["id"],))}
        # Every item is rendered for every candidate. An unanswered item becomes an explicit
        # "No response provided" row, never an absent row. See docs/08 check N6.
        c["questionnaire"] = [
            {"prompt": it["prompt"],
             "response": responses.get(it["id"], {}).get("response_text"),
             "answered": it["id"] in responses}
            for it in items
        ]
        c["is_withdrawn"] = c["filing_status"] in ("withdrawn", "disqualified")
    return ordered


def contests_for(conn: sqlite3.Connection, eid: str, jids: list[str] | None = None,
                 now: datetime | None = None) -> list[dict]:
    election = get_election(conn, eid, now=now)
    params: list = [eid]
    sql = "SELECT * FROM contest WHERE election_id = ?"
    if jids:
        sql += f" AND jurisdiction_id IN ({','.join('?' * len(jids))})"
        params += jids
    rows = conn.execute(sql, tuple(params)).fetchall()
    contests = []
    for r in rows:
        c = wrap(conn, r, "CONTEST", election.get("election_date"), now=now)
        c["_election_date"] = election.get("election_date")
        c["jurisdiction"] = _row(conn.execute(
            "SELECT * FROM jurisdiction WHERE id = ?", (r["jurisdiction_id"],)).fetchone())
        c["district"] = _row(conn.execute(
            "SELECT * FROM district WHERE id = ?", (r["district_id"],)).fetchone()) \
            if r["district_id"] else {}
        if r["level"] == "measure":
            m = conn.execute("SELECT * FROM measure WHERE contest_id = ?", (r["id"],)).fetchone()
            c["measure"] = wrap(conn, m, "MEASURE", election.get("election_date"), now=now) if m \
                else {}
            c["candidates"] = []
        else:
            c["measure"] = {}
            c["candidates"] = candidates_for(conn, c, now=now)
        c["has_data"] = bool(c["candidates"] or c["measure"])
        contests.append(c)
    groups = []
    for level in LEVEL_ORDER:
        items = [c for c in contests if c["level"] == level]
        if items:
            items.sort(key=lambda c: c["office_name"])
            groups.append({"level": level, "label": LEVEL_LABELS[level], "contests": items})
    return groups


def get_contest(conn: sqlite3.Connection, cid: str, now: datetime | None = None) -> dict:
    r = conn.execute("SELECT * FROM contest WHERE id = ?", (cid,)).fetchone()
    if not r:
        return {}
    election = get_election(conn, r["election_id"], now=now)
    c = wrap(conn, r, "CONTEST", election.get("election_date"), now=now)
    c["_election_date"] = election.get("election_date")
    c["election"] = election
    c["jurisdiction"] = _row(conn.execute(
        "SELECT * FROM jurisdiction WHERE id = ?", (r["jurisdiction_id"],)).fetchone())
    c["district"] = _row(conn.execute(
        "SELECT * FROM district WHERE id = ?", (r["district_id"],)).fetchone()) \
        if r["district_id"] else {}
    c["candidates"] = candidates_for(conn, c, now=now)
    m = conn.execute("SELECT * FROM measure WHERE contest_id = ?", (cid,)).fetchone()
    c["measure"] = wrap(conn, m, "MEASURE", election.get("election_date"), now=now) if m else {}
    if c["measure"]:
        c["measure"]["arguments_for"] = [
            wrap(conn, a, "MEASURE", election.get("election_date"), now=now) for a in conn.execute(
                "SELECT * FROM measure_argument WHERE measure_id = ? AND stance = 'for'",
                (c["measure"]["id"],))]
        c["measure"]["arguments_against"] = [
            wrap(conn, a, "MEASURE", election.get("election_date"), now=now) for a in conn.execute(
                "SELECT * FROM measure_argument WHERE measure_id = ? AND stance = 'against'",
                (c["measure"]["id"],))]
    return c


# --------------------------------------------------------------------------------------
# Rules and results
# --------------------------------------------------------------------------------------

RULE_CATEGORIES = [
    ("eligibility", "Who can vote"), ("registration", "Registering"), ("id", "Identification"),
    ("party", "Party participation"), ("mail", "Voting by mail"),
    ("provisional", "If there is a question about your ballot"),
    ("assistance", "Help with voting"), ("language", "Language assistance"),
    ("uocava", "Military and overseas voting"),
]


def rules_for(conn: sqlite3.Connection, jids: list[str], now: datetime | None = None) -> list[dict]:
    if not jids:
        return []
    rows = conn.execute(
        f"SELECT * FROM rule WHERE jurisdiction_id IN ({','.join('?' * len(jids))})",
        tuple(jids)).fetchall()
    wrapped = [wrap(conn, r, "RULES", None, now=now) for r in rows]
    out = []
    for cat, label in RULE_CATEGORIES:
        items = [r for r in wrapped if r["category"] == cat]
        if items:
            out.append({"category": cat, "label": label, "items": items})
    return out


def results_for(conn: sqlite3.Connection, eid: str, now: datetime | None = None) -> list[dict]:
    election = get_election(conn, eid, now=now)
    contests = conn.execute("SELECT * FROM contest WHERE election_id = ?", (eid,)).fetchall()
    out = []
    for cr in contests:
        rows = conn.execute(
            "SELECT r.*, c.ballot_name FROM result r LEFT JOIN candidate c ON c.id = r.candidate_id"
            " WHERE r.contest_id = ?", (cr["id"],)).fetchall()
        if not rows:
            out.append({"contest": _row(cr), "rows": [], "reporting_status": None,
                        "total_votes": 0})
            continue
        wrapped = []
        for r in rows:
            item = wrap(conn, r, "RESULT", election.get("election_date"), now=now)
            item["label"] = r["ballot_name"] or r["option_label"] or "Option"
            wrapped.append(item)
        total = sum(w["votes"] for w in wrapped) or 1
        for w in wrapped:
            w["share"] = round(100.0 * w["votes"] / total, 1)
        # Ordered by votes because this is a report of a count, not a ranking of people.
        # Ties are broken by name so the order is deterministic.
        wrapped.sort(key=lambda w: (-w["votes"], w["label"]))
        status = wrapped[0]["reporting_status"]
        out.append({
            "contest": _row(cr), "rows": wrapped, "reporting_status": status,
            "certifying_authority": wrapped[0].get("certifying_authority"),
            "precincts_reporting": wrapped[0].get("precincts_reporting"),
            "precincts_total": wrapped[0].get("precincts_total"),
            "reported_at": wrapped[0].get("reported_at"),
            "total_votes": sum(w["votes"] for w in wrapped),
        })
    return out


# --------------------------------------------------------------------------------------
# Operations
# --------------------------------------------------------------------------------------

def source_health(conn: sqlite3.Connection, now: datetime | None = None) -> list[dict]:
    now = now or utc_now()
    out = []
    for r in conn.execute(
            "SELECT s.*, h.last_check_at, h.last_success_at, h.consecutive_failures, h.note"
            " FROM source_record s LEFT JOIN source_health h ON h.source_record_id = s.id"
            " ORDER BY s.trust_tier, s.organization"):
        d = _row(r)
        age = (now - parse_iso(d["last_verified_at"])).days
        d["age_days"] = age
        d["alert"] = age > 45 or (d.get("consecutive_failures") or 0) > 0
        out.append(d)
    return out


def stale_records(conn: sqlite3.Connection, now: datetime | None = None) -> list[dict]:
    """Every fact whose verification has expired for its class. This is the ops queue that
    matters most in the final 60 days."""
    now = now or utc_now()
    checks = [("voting_location", "LOCATION"), ("deadline", "DEADLINE"), ("contest", "CONTEST"),
              ("candidate", "CANDIDATE"), ("rule", "RULES"), ("election", "ELECTION")]
    out = []
    for table, data_class in checks:
        for r in conn.execute(f"SELECT * FROM {table}"):
            d = _row(r)
            election_date = None
            if "election_id" in d:
                er = conn.execute("SELECT election_date FROM election WHERE id = ?",
                                  (d["election_id"],)).fetchone()
                election_date = er["election_date"] if er else None
            elif table == "election":
                election_date = d["election_date"]
            elif table == "candidate":
                er = conn.execute(
                    "SELECT e.election_date FROM candidate c JOIN contest ct ON ct.id = c.contest_id"
                    " JOIN election e ON e.id = ct.election_id WHERE c.id = ?", (d["id"],)
                ).fetchone()
                election_date = er["election_date"] if er else None
            w = wrap(conn, r, data_class, election_date, now=now)
            if w["status"].code == "pending" and w["status"].stale:
                out.append({"table": table, "id": d["id"],
                            "name": d.get("name") or d.get("office_name") or d.get("title")
                            or d.get("ballot_name") or d.get("action"),
                            "source": w["source"], "data_class": data_class})
    return out


def conflicts(conn: sqlite3.Connection, now: datetime | None = None) -> list[dict]:
    out = []
    for e in conn.execute("SELECT id FROM election"):
        found = deadlines_for(conn, e["id"], now=now)["conflicts"]
        for f in found:
            out.append({"election_id": e["id"], **f})
    return out
