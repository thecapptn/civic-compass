"""Correction workflow, end to end: submit, look up publicly, triage in ops, audit."""
import re


def _submit(client, **kw):
    payload = {"issue_type": "wrong_location", "body_text": "Demonstration report body.",
               "entity_table": "voting_location", "entity_id": "loc-mpls-eday-1"}
    payload.update(kw)
    return client.post("/report", data=payload)


def test_report_can_be_submitted_without_any_personal_details(client):
    r = _submit(client, contact_optional="")
    assert r.status_code == 200
    assert "Report received" in r.text


def test_report_returns_a_public_reference_number(client):
    body = _submit(client).text
    ref = re.search(r"<code>([A-Za-z0-9_-]{6,})</code>", body)
    assert ref, "no reference number issued"
    status = client.get(f"/report/{ref.group(1)}")
    assert status.status_code == 200
    assert "Received, not yet reviewed" in status.text


def test_report_prefilled_from_a_record_keeps_the_reference(client):
    body = client.get("/report?entity_table=candidate&entity_id=cd-sen-1").text
    assert 'value="candidate"' in body and 'value="cd-sen-1"' in body


def test_every_fact_offers_a_route_to_report_it(client):
    body = client.get("/ballot/e-mn-2026-general?j=j-minneapolis").text
    assert body.count("Report a problem with this information") > 5


def test_ops_console_requires_a_token(client):
    assert client.get("/ops").status_code == 401
    assert client.get("/ops?token=wrong").status_code == 401
    assert client.get("/ops?token=demo-ops-token").status_code == 200


def test_ops_triage_updates_public_status_and_writes_a_version_row(client, conn):
    ref = re.search(r"<code>([A-Za-z0-9_-]{6,})</code>", _submit(client).text).group(1)
    client.post(f"/ops/report/{ref}",
                data={"token": "demo-ops-token", "status": "confirmed",
                      "note": "Confirmed against the county source."}, follow_redirects=False)
    public = client.get(f"/report/{ref}").text
    assert "Confirmed" in public
    assert "Confirmed against the county source." in public
    versions = conn.execute(
        "SELECT * FROM record_version WHERE entity_id = ?", (ref,)).fetchall()
    assert versions, "no version row written for the change"
    assert "moderation_status" in versions[-1]["previous_value_json"]


def test_ops_actions_are_audited(client, conn):
    ref = re.search(r"<code>([A-Za-z0-9_-]{6,})</code>", _submit(client).text).group(1)
    client.post(f"/ops/report/{ref}", data={"token": "demo-ops-token", "status": "fixed",
                                            "note": "Corrected."}, follow_redirects=False)
    rows = conn.execute(
        "SELECT * FROM audit_log WHERE entity_id = ? ORDER BY id", (ref,)).fetchall()
    actions = {r["action"] for r in rows}
    assert "correction_submitted" in actions
    assert "correction_status_changed" in actions


def test_ops_write_is_rejected_without_the_token(client, conn):
    ref = re.search(r"<code>([A-Za-z0-9_-]{6,})</code>", _submit(client).text).group(1)
    client.post(f"/ops/report/{ref}", data={"token": "nope", "status": "fixed"},
                follow_redirects=False)
    row = conn.execute("SELECT moderation_status FROM correction_report WHERE id = ?",
                       (ref,)).fetchone()
    assert row["moderation_status"] == "new"
