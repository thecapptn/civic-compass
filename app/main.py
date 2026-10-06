"""Civic Compass web application.

Every page is server-rendered and works with scripting disabled. JavaScript is used only for
optional conveniences (copy-to-clipboard, checklist ticking, print). Nothing essential depends on it,
because an instruction a person cannot receive is an instruction we did not publish.
"""
from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI, Form, Query, Request
from fastapi.responses import HTMLResponse, PlainTextResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from . import repo
from .db import audit, connect, init_schema, query
from .logic import (DEADLINE_LABELS, LEVEL_LABELS, METHOD_LABELS, ORDER_RULE_WORDS,
                    STATUS_EXPLANATIONS, STATUS_WORDS, build_ics, format_local, new_token,
                    utc_now, utc_now_iso)

APP_DIR = Path(__file__).resolve().parent
OPS_TOKEN = os.environ.get("CIVIC_COMPASS_OPS_TOKEN", "demo-ops-token")

app = FastAPI(title="Civic Compass", docs_url=None, redoc_url=None)
app.mount("/static", StaticFiles(directory=str(APP_DIR / "static")), name="static")
templates = Jinja2Templates(directory=str(APP_DIR / "templates"))
templates.env.globals.update(
    DEADLINE_LABELS=DEADLINE_LABELS, METHOD_LABELS=METHOD_LABELS, LEVEL_LABELS=LEVEL_LABELS,
    STATUS_WORDS=STATUS_WORDS, STATUS_EXPLANATIONS=STATUS_EXPLANATIONS,
    ORDER_RULE_WORDS=ORDER_RULE_WORDS, DEMO_MODE=True,
)


def db():
    conn = connect()
    init_schema(conn)
    return conn


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    # No referrer: a shared link must never carry a jurisdiction to a third party.
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; img-src 'self' data:; style-src 'self'; script-src 'self'; "
        "form-action 'self'; frame-ancestors 'none'; base-uri 'self'")
    return response


def ctx(request: Request, **kwargs) -> dict:
    base = {"request": request, "now": utc_now(), "js_url": "/static/js/app.js"}
    base.update(kwargs)
    return base


def jurisdiction_ids(conn, jid: str | None) -> list[str]:
    if not jid:
        return []
    return [j["id"] for j in repo.jurisdiction_chain(conn, jid)]


# --------------------------------------------------------------------------------------
# Home and location
# --------------------------------------------------------------------------------------

@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    conn = db()
    states = query(conn, "SELECT * FROM jurisdiction WHERE type = 'state' ORDER BY name")
    conn.close()
    return templates.TemplateResponse(request, "home.html", ctx(request, states=states))


@app.post("/resolve", response_class=HTMLResponse)
def resolve(request: Request, location: str = Form("")):
    """POST only. The submitted string is resolved to jurisdiction IDs inside this handler and is
    never placed in a URL, a log line, or a response body. See docs/04 T5."""
    conn = db()
    match = repo.resolve_location(conn, location)
    conn.close()
    return templates.TemplateResponse(request, "confirm.html", ctx(request, match=match, had_input=bool(location.strip())))


@app.get("/confirm", response_class=HTMLResponse)
def confirm(request: Request, j: str = Query("")):
    conn = db()
    chain = repo.jurisdiction_chain(conn, j) if j else []
    conn.close()
    if not chain:
        return RedirectResponse("/", status_code=303)
    return templates.TemplateResponse(request, "confirmed.html", ctx(request, chain=chain, jid=j))


# --------------------------------------------------------------------------------------
# Elections
# --------------------------------------------------------------------------------------

@app.get("/elections", response_class=HTMLResponse)
def elections(request: Request, j: str = Query(""), window: str = Query("all")):
    conn = db()
    jids = jurisdiction_ids(conn, j)
    chain = repo.jurisdiction_chain(conn, j) if j else []
    items = repo.elections_for_jurisdictions(conn, jids, window)
    coverage = repo.coverage_for(conn, j) if j else {}
    primary = chain[0] if chain else None
    conn.close()
    return templates.TemplateResponse(request, "elections.html", ctx(
        request, elections=items, jid=j, chain=chain, window=window, coverage=coverage,
        primary=primary))


@app.get("/elections/{eid}", response_class=HTMLResponse)
def election_detail(request: Request, eid: str, j: str = Query("")):
    conn = db()
    election = repo.get_election(conn, eid)
    if not election:
        conn.close()
        return templates.TemplateResponse(request, "not_found.html", ctx(request), status_code=404)
    jids = jurisdiction_ids(conn, j)
    deadlines = repo.deadlines_for(conn, eid, jids or None)
    contests = repo.contests_for(conn, eid, jids or None)
    locations = repo.locations_for(conn, eid, jids or None)
    chain = repo.jurisdiction_chain(conn, j) if j else []
    conn.close()
    contest_count = sum(len(g["contests"]) for g in contests)
    return templates.TemplateResponse(request, "election.html", ctx(
        request, election=election, deadlines=deadlines, contests=contests, locations=locations,
        jid=j, chain=chain, contest_count=contest_count))


# --------------------------------------------------------------------------------------
# Plan
# --------------------------------------------------------------------------------------

@app.get("/plan/{eid}", response_class=HTMLResponse)
def plan(request: Request, eid: str, j: str = Query(""), m: str = Query("unsure")):
    conn = db()
    election = repo.get_election(conn, eid)
    if not election:
        conn.close()
        return templates.TemplateResponse(request, "not_found.html", ctx(request), status_code=404)
    jids = jurisdiction_ids(conn, j)
    deadlines = repo.deadlines_for(conn, eid, jids or None, method=m)
    locations = repo.locations_for(conn, eid, jids or None)
    chain = repo.jurisdiction_chain(conn, j) if j else []
    conn.close()
    return templates.TemplateResponse(request, "plan.html", ctx(
        request, election=election, deadlines=deadlines, locations=locations, jid=j, method=m,
        chain=chain, print_view=False))


@app.get("/plan/{eid}/print", response_class=HTMLResponse)
def plan_print(request: Request, eid: str, j: str = Query(""), m: str = Query("unsure")):
    conn = db()
    election = repo.get_election(conn, eid)
    jids = jurisdiction_ids(conn, j)
    deadlines = repo.deadlines_for(conn, eid, jids or None, method=m)
    locations = repo.locations_for(conn, eid, jids or None)
    chain = repo.jurisdiction_chain(conn, j) if j else []
    conn.close()
    return templates.TemplateResponse(request, "plan_print.html", ctx(
        request, election=election, deadlines=deadlines, locations=locations, jid=j, method=m,
        chain=chain, print_view=True))


@app.get("/plan/{eid}/calendar.ics")
def plan_calendar(eid: str, j: str = Query(""), m: str = Query("unsure")):
    conn = db()
    election = repo.get_election(conn, eid)
    jids = jurisdiction_ids(conn, j)
    deadlines = repo.deadlines_for(conn, eid, jids or None, method=m)
    conn.close()
    if not election:
        return PlainTextResponse("Not found", status_code=404)
    events = []
    for d in deadlines["items"]:
        label = DEADLINE_LABELS.get(d["action"], d["action"])
        events.append({
            "uid": d["id"],
            "occurs_at_utc": d["occurs_at_utc"],
            "summary": f"[Demonstration data] {label} — {election['name']}",
            "description": (
                f"{label} for {election['name']} ({election['date_display']}).\n"
                f"Source: {d['source']['organization']} — {d['source']['source_url']}\n"
                f"Status: {d['status'].word}.\n"
                "This calendar entry was generated from demonstration data and is not real "
                "election information. Verify every date with your election office."),
        })
    body = build_ics(events, f"Civic Compass — {election['name']} (demonstration data)")
    return Response(body, media_type="text/calendar",
                    headers={"Content-Disposition": f'attachment; filename="{eid}-demo.ics"'})


@app.post("/plan/{eid}/save")
def plan_save(eid: str, j: str = Form(""), m: str = Form("unsure")):
    """Server-side saved plan: an opaque token with a hard expiry and no identity attached."""
    conn = db()
    token = new_token()
    election = repo.get_election(conn, eid)
    if not election or not j:
        conn.close()
        return RedirectResponse(f"/plan/{eid}?j={j}&m={m}", status_code=303)
    from datetime import timedelta
    expires = (utc_now() + timedelta(days=120)).replace(microsecond=0).isoformat()
    conn.execute(
        "INSERT INTO saved_plan (token, created_at, expires_at, jurisdiction_id, election_id,"
        " method_pref, checklist_state_json) VALUES (?,?,?,?,?,?,?)",
        (token, utc_now_iso(), expires, j, eid, m, "{}"))
    conn.commit()
    audit(conn, "public", "saved_plan_created", "saved_plan", token, None, None)
    conn.close()
    return RedirectResponse(f"/plan/{eid}?j={j}&m={m}&saved={token}", status_code=303)


@app.post("/plan/forget")
def plan_forget(token: str = Form("")):
    conn = db()
    conn.execute("DELETE FROM saved_plan WHERE token = ?", (token,))
    conn.commit()
    audit(conn, "public", "saved_plan_deleted", "saved_plan", token, None, None)
    conn.close()
    return RedirectResponse("/?forgot=1", status_code=303)


# --------------------------------------------------------------------------------------
# Ballot
# --------------------------------------------------------------------------------------

@app.get("/ballot/{eid}", response_class=HTMLResponse)
def ballot(request: Request, eid: str, j: str = Query("")):
    conn = db()
    election = repo.get_election(conn, eid)
    if not election:
        conn.close()
        return templates.TemplateResponse(request, "not_found.html", ctx(request), status_code=404)
    jids = jurisdiction_ids(conn, j)
    groups = repo.contests_for(conn, eid, jids or None)
    chain = repo.jurisdiction_chain(conn, j) if j else []
    conn.close()
    return templates.TemplateResponse(request, "ballot.html", ctx(
        request, election=election, groups=groups, jid=j, chain=chain))


@app.get("/contest/{cid}", response_class=HTMLResponse)
def contest_detail(request: Request, cid: str, j: str = Query("")):
    conn = db()
    contest = repo.get_contest(conn, cid)
    conn.close()
    if not contest:
        return templates.TemplateResponse(request, "not_found.html", ctx(request), status_code=404)
    template = "measure.html" if contest["level"] == "measure" else "contest.html"
    return templates.TemplateResponse(request, template, ctx(request, contest=contest, jid=j))


# --------------------------------------------------------------------------------------
# Where to vote, rules, results
# --------------------------------------------------------------------------------------

@app.get("/where/{eid}", response_class=HTMLResponse)
def where(request: Request, eid: str, j: str = Query("")):
    conn = db()
    election = repo.get_election(conn, eid)
    if not election:
        conn.close()
        return templates.TemplateResponse(request, "not_found.html", ctx(request), status_code=404)
    jids = jurisdiction_ids(conn, j)
    groups = repo.locations_for(conn, eid, jids or None)
    chain = repo.jurisdiction_chain(conn, j) if j else []
    conn.close()
    return templates.TemplateResponse(request, "where.html", ctx(
        request, election=election, groups=groups, jid=j, chain=chain))


@app.get("/rules", response_class=HTMLResponse)
def rules(request: Request, j: str = Query("")):
    conn = db()
    jids = jurisdiction_ids(conn, j)
    groups = repo.rules_for(conn, jids)
    chain = repo.jurisdiction_chain(conn, j) if j else []
    conn.close()
    return templates.TemplateResponse(request, "rules.html", ctx(
        request, groups=groups, jid=j, chain=chain))


@app.get("/results/{eid}", response_class=HTMLResponse)
def results(request: Request, eid: str, j: str = Query("")):
    conn = db()
    election = repo.get_election(conn, eid)
    if not election:
        conn.close()
        return templates.TemplateResponse(request, "not_found.html", ctx(request), status_code=404)
    items = repo.results_for(conn, eid)
    conn.close()
    return templates.TemplateResponse(request, "results.html", ctx(
        request, election=election, results=items, jid=j))


# --------------------------------------------------------------------------------------
# Help, corrections, methodology
# --------------------------------------------------------------------------------------

@app.get("/help", response_class=HTMLResponse)
def help_page(request: Request, j: str = Query("")):
    conn = db()
    chain = repo.jurisdiction_chain(conn, j) if j else []
    conn.close()
    return templates.TemplateResponse(request, "help.html", ctx(request, chain=chain, jid=j))


@app.get("/report", response_class=HTMLResponse)
def report_form(request: Request, entity_table: str = Query(""), entity_id: str = Query(""),
                j: str = Query("")):
    return templates.TemplateResponse(request, "report.html", ctx(
        request, entity_table=entity_table, entity_id=entity_id, jid=j, submitted=None))


@app.post("/report", response_class=HTMLResponse)
def report_submit(request: Request, issue_type: str = Form("other"), body_text: str = Form(""),
                  entity_table: str = Form(""), entity_id: str = Form(""),
                  contact_optional: str = Form("")):
    conn = db()
    rid = new_token()[:10]
    conn.execute(
        "INSERT INTO correction_report (id, submitted_at, entity_table, entity_id, issue_type,"
        " body_text, contact_optional, moderation_status) VALUES (?,?,?,?,?,?,?, 'new')",
        (rid, utc_now_iso(), entity_table or None, entity_id or None, issue_type,
         body_text.strip(), contact_optional.strip() or None))
    conn.commit()
    audit(conn, "public", "correction_submitted", "correction_report", rid, None,
          f"about {entity_table or 'no record'}/{entity_id or '-'}")
    conn.close()
    return templates.TemplateResponse(request, "report.html", ctx(
        request, entity_table=entity_table, entity_id=entity_id, jid="", submitted=rid))


@app.get("/report/{rid}", response_class=HTMLResponse)
def report_status(request: Request, rid: str):
    conn = db()
    r = conn.execute(
        "SELECT id, submitted_at, issue_type, moderation_status, resolution_note, resolved_at,"
        " entity_table, entity_id FROM correction_report WHERE id = ?", (rid,)).fetchone()
    conn.close()
    if not r:
        return templates.TemplateResponse(request, "not_found.html", ctx(request), status_code=404)
    return templates.TemplateResponse(request, "report_status.html", ctx(request, report=dict(r)))


@app.get("/methodology", response_class=HTMLResponse)
def methodology(request: Request):
    conn = db()
    matrix = repo.full_coverage_matrix(conn)
    health = repo.source_health(conn)
    conn.close()
    classes = ["ELECTION", "DEADLINE", "LOCATION", "RULES", "CONTEST", "CANDIDATE", "MEASURE",
               "RESULT", "ADMIN"]
    return templates.TemplateResponse(request, "methodology.html", ctx(
        request, matrix=matrix, classes=classes, health=health))


# --------------------------------------------------------------------------------------
# Operations console
# --------------------------------------------------------------------------------------

@app.get("/ops", response_class=HTMLResponse)
def ops(request: Request, token: str = Query("")):
    if token != OPS_TOKEN:
        return templates.TemplateResponse(request, "ops_locked.html", ctx(request), status_code=401)
    conn = db()
    data = {
        "health": repo.source_health(conn),
        "stale": repo.stale_records(conn),
        "conflicts": repo.conflicts(conn),
        "reports": [dict(r) for r in query(
            conn, "SELECT * FROM correction_report ORDER BY submitted_at DESC LIMIT 50")],
        "audit": [dict(r) for r in query(
            conn, "SELECT * FROM audit_log ORDER BY id DESC LIMIT 50")],
        "withdrawals": [dict(r) for r in query(
            conn, "SELECT c.*, ct.office_name FROM candidate c JOIN contest ct"
                  " ON ct.id = c.contest_id WHERE c.filing_status IN ('withdrawn','disqualified')")],
    }
    conn.close()
    return templates.TemplateResponse(request, "ops.html", ctx(request, token=token, **data))


@app.post("/ops/report/{rid}")
def ops_update_report(rid: str, token: str = Form(""), status: str = Form("triage"),
                      note: str = Form("")):
    if token != OPS_TOKEN:
        return RedirectResponse("/ops", status_code=303)
    conn = db()
    prev = conn.execute("SELECT moderation_status FROM correction_report WHERE id = ?",
                        (rid,)).fetchone()
    conn.execute(
        "UPDATE correction_report SET moderation_status = ?, resolution_note = ?, resolved_at = ?"
        " WHERE id = ?",
        (status, note or None, utc_now_iso() if status in ("fixed", "rejected") else None, rid))
    conn.execute(
        "INSERT INTO record_version (entity_table, entity_id, changed_at, changed_by,"
        " change_reason, previous_value_json, new_value_json) VALUES (?,?,?,?,?,?,?)",
        ("correction_report", rid, utc_now_iso(), "ops-console", note or "status change",
         f'{{"moderation_status": "{prev["moderation_status"] if prev else ""}"}}',
         f'{{"moderation_status": "{status}"}}'))
    conn.commit()
    audit(conn, "ops-console", "correction_status_changed", "correction_report", rid, None, status)
    conn.close()
    return RedirectResponse(f"/ops?token={token}", status_code=303)


# --------------------------------------------------------------------------------------
# JSON read API
# --------------------------------------------------------------------------------------

def _status_json(s) -> dict:
    return {"code": s.code, "word": s.word, "explanation": s.explanation, "stale": s.stale}


def _fact_json(d: dict, fields: list[str]) -> dict:
    out = {k: d.get(k) for k in fields}
    out["status"] = _status_json(d["status"])
    out["source"] = {
        "organization": d["source"]["organization"], "url": d["source"]["source_url"],
        "trust_tier": d["source"]["trust_tier"], "retrieved_at": d["source"]["retrieved_at"],
        "last_verified_at": d["source"]["last_verified_at"],
    }
    out["is_demonstration_data"] = True
    return out


@app.get("/api/elections")
def api_elections(j: str = Query("")):
    conn = db()
    jids = jurisdiction_ids(conn, j)
    items = repo.elections_for_jurisdictions(conn, jids)
    conn.close()
    return {"notice": "All records are demonstration data and are not real election information.",
            "elections": [_fact_json(e, ["id", "name", "type", "election_date", "jurisdiction_id",
                                         "days_away", "relevance_note"]) for e in items]}


@app.get("/api/elections/{eid}/ballot")
def api_ballot(eid: str, j: str = Query("")):
    conn = db()
    jids = jurisdiction_ids(conn, j)
    groups = repo.contests_for(conn, eid, jids or None)
    conn.close()
    return {
        "notice": "All records are demonstration data and are not real election information.",
        "groups": [{
            "level": g["level"], "label": g["label"],
            "contests": [{
                **_fact_json(c, ["id", "office_name", "seats", "term_text", "classification",
                                 "order_rule", "coverage", "coverage_note", "why_relevant"]),
                "order_rule_explanation": ORDER_RULE_WORDS[c["order_rule"]],
                "candidates": [_fact_json(cd, ["id", "ballot_name", "filing_status",
                                               "party_label_official", "website_url"])
                               for cd in c["candidates"]],
                "measure": _fact_json(c["measure"], ["id", "official_title", "ballot_text",
                                                     "full_text_url"]) if c["measure"] else None,
            } for c in g["contests"]],
        } for g in groups],
    }


@app.get("/api/coverage")
def api_coverage():
    conn = db()
    matrix = repo.full_coverage_matrix(conn)
    conn.close()
    return {"coverage": [{"jurisdiction_id": m["jurisdiction"]["id"],
                          "name": m["jurisdiction"]["name"], "cells": m["cells"]} for m in matrix]}


@app.get("/healthz")
def healthz():
    return {"ok": True, "at": utc_now_iso()}
