"""Neutrality checks N1-N14 from docs/08. A failure here blocks release."""
import re
import sqlite3

from app import repo
from app.logic import neutral_order, sort_key_for

BANNED_COLUMNS = {"rank", "score", "featured", "priority", "promoted", "match", "weight",
                  "relevance", "popularity", "endorsement"}


def test_n3_no_ranking_columns_exist_in_the_schema(conn):
    """The prohibited product should be impossible to build without a migration."""
    for table in ("candidate", "measure", "contest"):
        cols = {r[1].lower() for r in conn.execute(f"PRAGMA table_info({table})")}
        assert not (cols & BANNED_COLUMNS), f"{table} has a ranking column"


def test_n12_no_table_can_store_a_political_preference(conn):
    tables = [r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'")]
    forbidden = {"preference", "affinity", "ideology", "leaning", "party_preference",
                 "candidate_view", "click"}
    for t in tables:
        cols = {r[1].lower() for r in conn.execute(f"PRAGMA table_info({t})")}
        assert not (cols & forbidden), f"{t} can store political inference"


def test_n1_alphabetical_order_ignores_ballot_position(conn):
    contest = repo.get_contest(conn, "c-gen-ussenate")
    assert contest["order_rule"] == "alphabetical"
    names = [c["ballot_name"] for c in contest["candidates"]]
    assert names == sorted(names, key=sort_key_for)


def test_n1_official_ballot_order_is_used_only_when_declared(conn):
    contest = repo.get_contest(conn, "c-gen-ushouse5")
    assert contest["order_rule"] == "official_ballot"
    positions = [c["ballot_position"] for c in contest["candidates"]]
    assert positions == sorted(p for p in positions if p is not None)


def test_n2_ordering_is_independent_of_input_order():
    people = [{"id": "c", "ballot_name": "Zeta, A", "sort_key": sort_key_for("Zeta, A")},
              {"id": "a", "ballot_name": "Alpha, B", "sort_key": sort_key_for("Alpha, B")},
              {"id": "b", "ballot_name": "Mid, C", "sort_key": sort_key_for("Mid, C")}]
    forward = [c["id"] for c in neutral_order(people)]
    reverse = [c["id"] for c in neutral_order(list(reversed(people)))]
    assert forward == reverse == ["a", "b", "c"]


def test_n2_identical_names_still_order_deterministically():
    dupes = [{"id": "z", "ballot_name": "Same, Name", "sort_key": sort_key_for("Same, Name")},
             {"id": "a", "ballot_name": "Same, Name", "sort_key": sort_key_for("Same, Name")}]
    assert [c["id"] for c in neutral_order(dupes)] == ["a", "z"]
    assert [c["id"] for c in neutral_order(list(reversed(dupes)))] == ["a", "z"]


def test_n4_every_candidate_in_a_contest_renders_the_same_field_labels(client):
    body = client.get("/contest/c-gen-council6").text
    cards = re.findall(r'<li class="cand">.*?</li>', body, re.S)
    assert len(cards) >= 2
    labelsets = [tuple(re.findall(r"<dt>(.*?)</dt>", card, re.S)) for card in cards]
    assert len(set(labelsets)) == 1, "candidate cards do not share one field set"


def test_n5_every_candidate_card_uses_identical_markup_classes(client):
    body = client.get("/ballot/e-mn-2026-general?j=j-minneapolis").text
    wrappers = re.findall(r'<li class="([^"]*cand[^"]*)">', body)
    assert wrappers, "no candidate cards rendered"
    assert len(set(wrappers)) == 1, f"candidate wrappers vary: {set(wrappers)}"


def test_n6_unanswered_questions_are_shown_not_hidden(client):
    """One demo candidate answered none of the three questions. All three must still render."""
    body = client.get("/contest/c-gen-council6").text
    cards = re.findall(r'<li class="cand">.*?</li>', body, re.S)
    whitfield = [c for c in cards if "Whitfield, Cyrus" in c][0]
    assert whitfield.count("No response provided.") >= 3


def test_n7_measure_arguments_get_equal_treatment(conn):
    contest = repo.get_contest(conn, "c-gen-cityq1")
    m = contest["measure"]
    assert len(m["arguments_for"]) == len(m["arguments_against"])


def test_n7_missing_argument_side_is_named_not_silently_dropped(client):
    body = client.get("/contest/c-gen-cityq1").text
    assert "In favor" in body and "In opposition" in body


def test_n8_no_party_derived_colour_or_class_anywhere(client):
    for url in ("/ballot/e-mn-2026-general?j=j-minneapolis", "/contest/c-gen-ussenate"):
        body = client.get(url).text
        assert not re.search(r'class="[^"]*\b(dem|rep|gop|blue|red)\b', body, re.I)
        assert not re.search(r'style="[^"]*background[^"]*(red|blue|#f00|#00f)', body, re.I)


def test_n10_no_persuasive_calls_to_action(client):
    banned = ["donate", "chip in", "volunteer for", "join the campaign", "pledge",
              "support this candidate"]
    for url in ("/", "/ballot/e-mn-2026-general?j=j-minneapolis", "/contest/c-gen-council6"):
        body = client.get(url).text.lower()
        for phrase in banned:
            assert phrase not in body, f"{phrase!r} on {url}"


def test_n11_every_candidate_card_carries_a_source_strip(client):
    body = client.get("/ballot/e-mn-2026-general?j=j-minneapolis").text
    cards = re.findall(r'<li class="cand">.*?</article>', body, re.S)
    assert cards
    for card in cards:
        assert 'class="srcstrip"' in card, "a candidate rendered without provenance"


def test_n13_withdrawn_candidates_are_marked_not_removed(client):
    body = client.get("/ballot/e-mn-2026-general?j=j-minneapolis").text
    assert "Calloway, Dennis P." in body
    assert "Withdrawn" in body


def test_n14_uncovered_contest_states_the_gap_instead_of_rendering_empty(client):
    body = client.get("/ballot/e-mn-2026-general?j=j-minneapolis").text
    assert "Soil and Water Conservation District Supervisor" in body
    assert "We do not yet have reliable data for this contest" in body
