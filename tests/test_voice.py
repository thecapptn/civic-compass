"""Product-authored copy must stay out of persuasion. docs/06 and docs/08 check N9."""
import re

import pytest

from app.logic import BANNED_TERMS

ROUTES = ["/", "/elections?j=j-minneapolis", "/elections/e-mn-2026-general?j=j-minneapolis",
          "/ballot/e-mn-2026-general?j=j-minneapolis", "/plan/e-mn-2026-general?j=j-minneapolis",
          "/where/e-mn-2026-general?j=j-minneapolis", "/rules?j=j-minneapolis",
          "/results/e-mn-2026-primary", "/help", "/methodology", "/report"]


def visible_text(html: str) -> str:
    html = re.sub(r"<(script|style).*?</\1>", " ", html, flags=re.S)
    return re.sub(r"<[^>]+>", " ", html).lower()


@pytest.mark.parametrize("route", ROUTES)
def test_no_banned_persuasive_vocabulary(client, route):
    text = visible_text(client.get(route).text)
    for term in BANNED_TERMS:
        assert term not in text, f"{term!r} appears on {route}"


def test_uses_may_be_eligible_not_are_eligible(client):
    text = visible_text(client.get("/rules?j=j-minneapolis").text)
    assert "you are eligible" not in text


def test_attributes_rules_to_the_election_office(client):
    text = visible_text(client.get("/rules?j=j-minneapolis").text)
    assert "election office reports" in text or "office lists" in text


def test_non_response_is_never_described_as_refusal(client):
    text = visible_text(client.get("/contest/c-gen-council6").text)
    assert "no response provided" in text
    assert "refused" not in text
    assert "declined to answer" not in text


def test_endorsement_disclaimer_present_on_candidate_information(client):
    text = visible_text(client.get("/contest/c-gen-council6").text)
    assert "does not represent an endorsement" in text


def test_demo_banner_on_every_page(client):
    for route in ROUTES:
        assert "Demonstration data." in client.get(route).text, route


def test_demo_banner_cannot_be_dismissed(client):
    """A dismissible banner would let demo data render as real information."""
    body = client.get("/").text
    assert "dismiss" not in body.lower()
    css = open("app/static/css/app.css").read()
    assert ".demobar" in css


def test_missing_data_copy_matches_the_specified_wording(client):
    body = client.get("/ballot/e-mn-2026-general?j=j-minneapolis").text
    assert "We do not yet have reliable data for this contest" in body
