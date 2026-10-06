"""Two structural guarantees: no fact without provenance, and no address anywhere it could leak."""
import re


def test_no_fact_table_allows_a_null_source(conn):
    fact_tables = ["election", "deadline", "voting_location", "rule", "contest", "candidate",
                   "measure", "measure_argument", "result", "district", "jurisdiction"]
    for table in fact_tables:
        cols = {r[1]: r for r in conn.execute(f"PRAGMA table_info({table})")}
        assert "source_record_id" in cols, f"{table} has no source column"
        assert cols["source_record_id"][3] == 1, f"{table}.source_record_id is nullable"


def test_source_insert_without_a_url_is_rejected(conn):
    import sqlite3
    try:
        conn.execute(
            "INSERT INTO source_record (id, organization, source_url, source_type, trust_tier,"
            " retrieved_at, last_verified_at) VALUES ('bad','Org','','x',1,'2026-01-01','2026-01-01')")
        conn.commit()
        raised = False
    except sqlite3.IntegrityError:
        raised = True
    finally:
        conn.rollback()
    assert raised, "a source without a usable URL was accepted"


def test_every_seeded_source_has_an_organisation_and_url(conn):
    for r in conn.execute("SELECT * FROM source_record"):
        assert r["organization"].strip()
        assert r["source_url"].startswith("http")
        assert r["last_verified_at"]


def test_no_saved_plan_column_can_hold_an_address_or_identity(conn):
    cols = {r[1].lower() for r in conn.execute("PRAGMA table_info(saved_plan)")}
    for forbidden in ("address", "email", "name", "user_id", "ip", "phone", "postal_code"):
        assert forbidden not in cols


def test_saved_plans_expire(client, conn):
    client.post("/plan/e-mn-2026-general/save", data={"j": "j-minneapolis", "m": "mail"},
                follow_redirects=False)
    row = conn.execute("SELECT * FROM saved_plan ORDER BY created_at DESC LIMIT 1").fetchone()
    assert row["expires_at"] > row["created_at"]
    assert row["jurisdiction_id"] == "j-minneapolis"


def test_saved_plan_can_be_deleted_in_one_action(client, conn):
    client.post("/plan/e-mn-2026-general/save", data={"j": "j-minneapolis", "m": "mail"},
                follow_redirects=False)
    token = conn.execute(
        "SELECT token FROM saved_plan ORDER BY created_at DESC LIMIT 1").fetchone()["token"]
    client.post("/plan/forget", data={"token": token}, follow_redirects=False)
    assert conn.execute("SELECT 1 FROM saved_plan WHERE token = ?", (token,)).fetchone() is None


def test_address_never_appears_in_a_redirect_or_url(client):
    r = client.post("/resolve", data={"location": "1234 Demonstration Ave, Minneapolis, MN 55418"},
                    follow_redirects=False)
    assert "1234 Demonstration Ave" not in str(r.headers)
    assert "1234 Demonstration Ave" not in r.text


def test_security_headers_are_set(client):
    h = client.get("/").headers
    assert h["Referrer-Policy"] == "no-referrer"
    assert h["X-Content-Type-Options"] == "nosniff"
    assert "frame-ancestors 'none'" in h["Content-Security-Policy"]


def test_no_third_party_resources_are_loaded(client):
    """No analytics, no fonts, no CDNs: nothing that would tell another party who is here."""
    for route in ("/", "/ballot/e-mn-2026-general?j=j-minneapolis", "/methodology"):
        body = client.get(route).text
        for attr in re.findall(r'(?:src|href)="(https?://[^"]+)"', body):
            assert not re.search(r"\.(js|css|woff2?)(\?|$)", attr), f"third-party asset: {attr}"


def test_api_marks_every_record_as_demonstration_data(client):
    payload = client.get("/api/elections?j=j-minneapolis").json()
    assert "demonstration data" in payload["notice"].lower()
    for e in payload["elections"]:
        assert e["is_demonstration_data"] is True
        assert e["source"]["url"].startswith("http")
        assert e["status"]["code"]
