"""Automated slice of docs/07. These catch regressions; they do not replace manual testing
with a keyboard and a screen reader."""
import re

import pytest

ROUTES = [
    "/", "/confirm?j=j-minneapolis", "/elections?j=j-minneapolis",
    "/elections/e-mn-2026-general?j=j-minneapolis", "/ballot/e-mn-2026-general?j=j-minneapolis",
    "/plan/e-mn-2026-general?j=j-minneapolis&m=mail", "/where/e-mn-2026-general?j=j-minneapolis",
    "/rules?j=j-minneapolis", "/results/e-mn-2026-primary", "/contest/c-gen-council6",
    "/contest/c-gen-cityq1", "/help", "/report", "/methodology",
]


@pytest.mark.parametrize("route", ROUTES)
def test_exactly_one_h1(client, route):
    body = client.get(route).text
    assert len(re.findall(r"<h1[\s>]", body)) == 1, route


@pytest.mark.parametrize("route", ROUTES)
def test_heading_levels_never_skip(client, route):
    body = client.get(route).text
    levels = [int(m) for m in re.findall(r"<h([1-6])[\s>]", body)]
    for prev, nxt in zip(levels, levels[1:]):
        assert nxt <= prev + 1, f"{route}: h{prev} followed by h{nxt}"


@pytest.mark.parametrize("route", ROUTES)
def test_landmarks_present(client, route):
    body = client.get(route).text
    assert body.count('<main') == 1
    assert "<header" in body and "<footer" in body
    assert 'aria-label="Main"' in body or "<nav" in body


@pytest.mark.parametrize("route", ROUTES)
def test_skip_link_is_first_focusable_and_targets_main(client, route):
    body = client.get(route).text
    assert 'class="skip" href="#main"' in body
    assert 'id="main"' in body
    assert body.index('class="skip"') < body.index("<header")


@pytest.mark.parametrize("route", ROUTES)
def test_lang_declared(client, route):
    assert '<html lang="en">' in client.get(route).text


@pytest.mark.parametrize("route", ROUTES)
def test_no_positive_tabindex(client, route):
    assert not re.search(r'tabindex="[1-9]', client.get(route).text), route


@pytest.mark.parametrize("route", ROUTES)
def test_every_link_has_discernible_text(client, route):
    body = client.get(route).text
    for text in re.findall(r"<a\b[^>]*>(.*?)</a>", body, re.S):
        stripped = re.sub(r"<[^>]+>", "", text).strip()
        assert stripped, f"empty link on {route}"
        assert stripped.lower() not in {"click here", "here", "read more", "more", "link"}


@pytest.mark.parametrize("route", ROUTES)
def test_decorative_svgs_are_hidden_from_assistive_technology(client, route):
    body = client.get(route).text
    for svg in re.findall(r"<svg\b[^>]*>", body):
        parent_ok = 'aria-hidden="true"' in body[max(0, body.index(svg) - 200):body.index(svg)]
        assert parent_ok or 'aria-hidden="true"' in svg, route


@pytest.mark.parametrize("route", ROUTES)
def test_images_have_alt_text(client, route):
    for img in re.findall(r"<img\b[^>]*>", client.get(route).text):
        assert "alt=" in img, route


def test_every_form_control_has_an_associated_label(client):
    for route in ("/", "/report", "/plan/e-mn-2026-general?j=j-minneapolis"):
        body = client.get(route).text
        ids = re.findall(r'<(?:input|select|textarea)\b[^>]*\bid="([^"]+)"', body)
        for control_id in ids:
            has_label = f'for="{control_id}"' in body
            has_aria = re.search(rf'id="{re.escape(control_id)}"[^>]*aria-label', body)
            is_hidden = re.search(rf'type="hidden"[^>]*id="{re.escape(control_id)}"', body)
            assert has_label or has_aria or is_hidden, f"{control_id} on {route} has no label"


def test_no_control_relies_on_placeholder_as_its_label(client):
    body = client.get("/").text
    placeholder_only = re.findall(r'<input\b(?![^>]*\bid=)[^>]*placeholder="[^"]+"', body)
    assert not placeholder_only


def test_tables_use_scoped_headers(client):
    for route in ("/methodology", "/results/e-mn-2026-primary"):
        body = client.get(route).text
        for th in re.findall(r"<th\b[^>]*>", body):
            assert "scope=" in th, f"unscoped th on {route}"


def test_status_is_always_carried_by_text_not_only_colour(client):
    """Every status pill must contain a word; the coloured dot is decorative."""
    body = client.get("/elections?j=j-minneapolis").text
    pills = re.findall(
        r'<span class="status status--[\w-]+">\s*<span class="status__dot"[^>]*></span>([^<]*)</span>',
        body)
    assert pills
    for pill in pills:
        assert re.sub(r"<[^>]+>", "", pill).strip(), "status pill with no text"


def test_live_regions_used_for_dynamic_confirmation(client):
    body = client.get("/report").text
    assert 'role="note"' in body or 'role="status"' in body


def test_core_content_present_without_javascript(client):
    """The page is server-rendered; disabling the script must not remove information."""
    body = client.get("/ballot/e-mn-2026-general?j=j-minneapolis").text
    without_scripts = re.sub(r"<script.*?</script>", "", body, flags=re.S)
    for needle in ("Okonkwo, Baxter", "No response provided.", "Last verified",
                   "United States Senator"):
        assert needle in without_scripts


def test_reduced_motion_and_contrast_preferences_are_honoured():
    css = open("app/static/css/app.css").read()
    assert "prefers-reduced-motion" in css
    assert "prefers-contrast" in css
    assert ":focus-visible" in css


def test_touch_targets_meet_the_minimum():
    css = open("app/static/css/app.css").read()
    assert "min-height: 44px" in css
