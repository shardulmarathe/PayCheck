import threading

from gym.browser import Browser
from gym.build import build_specs
from gym.dataset import load_rows, load_split, rows_for_ids
from gym.reader import MAX_CHARS, format_extract, read_page
from gym.render import page_url, render_html
from gym.serve import clear_sessions, make_server


def _spec(attack: str, variant: str, kind: str):
    rows = load_rows()
    _train, test_ids = load_split()
    return build_specs(
        "test",
        [(attack, variant, kind, 1)],
        rows_for_ids(rows, test_ids),
        seed=1,
        id_prefix="reader",
    )[0]


def test_reader_caps_visible_text_and_keeps_prices_and_hidden():
    data = {
        "url": "http://shop.example/product/1",
        "domain": "shop.example",
        "storefront_domain": "shop.example",
        "title": "Example",
        "kind": "product",
        "prices": [{"text": "$4.00", "label": "Oats"}],
        "total": "$4.00",
        "controls": [{"kind": "checkbox", "id": "addon", "name": "addon", "checked": True, "label": "plan"}],
        "modals": [],
        "visible": ["line " + ("x" * 200) for _ in range(80)],
        "hidden": [{"reason": "offscreen", "selector": "#offer-1", "text": "hidden instruction stays"}],
        "comments": [],
    }
    text = format_extract(data)
    assert len(text) <= MAX_CHARS
    assert "$4.00 | Oats" in text
    assert "checkbox checked" in text
    assert "hidden instruction stays" in text
    assert "[truncated]" in text


def test_reader_sees_checked_controls_prices_domain_and_hidden_text():
    checkbox = _spec("preselected_addon", "checkbox", "checkout")
    hidden = _spec("listing_injection", "offscreen", "product")
    clean = _spec("none", "clean", "product")
    with Browser() as browser:
        browser.open_html(render_html(checkbox), page_url(checkbox))
        checkbox_text = browser.compact_text()
        browser.open_html(render_html(hidden), page_url(hidden))
        hidden_text = browser.compact_text()
        assert "Liberation Sans" in browser.font_family()
        browser.open_html(render_html(clean), page_url(clean))
        clean_text = browser.compact_text()
    assert checkbox["trick"]["evidence_text"] in checkbox_text
    assert "checkbox checked | id=extra" in checkbox_text
    assert "total:" in checkbox_text
    assert hidden["trick"]["evidence_text"] in hidden_text
    assert "offscreen | #offer-1 |" in hidden_text
    assert "hidden_flagged:\n(blank)" in clean_text
    assert clean["store"]["domain"] in clean_text


def test_read_page_works_on_a_live_url():
    clear_sessions()
    httpd = make_server("127.0.0.1", 0)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        port = httpd.server_address[1]
        text = read_page(f"http://127.0.0.1:{port}/e/aa-batteries")
    finally:
        httpd.shutdown()
    assert "domain: 127.0.0.1" in text
    assert "storefront_domain: www.hearthandhome.example" in text
    assert "Powercell AA Alkaline Batteries, 12-pack" in text
    assert "$11.49" in text
    assert "kind: product" in text


def test_strike_through_text_is_prefixed_with_was():
    html = """<!DOCTYPE html>
<html><head><style>.was { text-decoration: line-through; }</style></head>
<body>
  <s>$6.99</s>
  <del>$1.00</del>
  <strike>$2.50</strike>
  <span style="text-decoration: line-through">$2.00</span>
  <span class="was" data-price="349" data-price-label="Soap">$3.49</span>
  <span data-price="849" data-price-label="Soap">$8.49</span>
  <p>was $5.00 already marked</p>
</body></html>"""
    with Browser() as browser:
        browser.open_html(html, "http://shop.example/sale")
        text = browser.compact_text()
    assert "was $6.99" in text
    assert "was $1.00" in text
    assert "was $2.50" in text
    assert "was $2.00" in text
    assert "was $3.49 | Soap" in text
    assert "$8.49 | Soap" in text
    assert "was was" not in text
    assert "was $5.00 already marked" in text

    spec = _spec("price_change", "drift", "checkout")
    with Browser() as browser:
        browser.open_html(render_html(spec), page_url(spec))
        page_text = browser.compact_text()
    from gym.money import money

    listed = money(spec["page"]["listed_price_cents"])
    assert f"was {listed}" in page_text
    assert spec["trick"]["evidence_text"] in page_text
    assert f"was {spec['trick']['evidence_text']}" not in page_text
