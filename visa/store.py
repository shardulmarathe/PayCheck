"""Demo store server.

Every product and checkout request must carry a Signed agent check
(Visa Trusted Agent Protocol). Unsigned and tampered requests are rejected
before a page is served.
"""

from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from visa.reader_text import checkout_reader_text
from visa.tap import TAG_BROWSER, TAG_PAYER, Verifier

FEE_EVIDENCE = "Care & handling $2.99"
CHECK_NAME = "Signed agent check (Visa Trusted Agent Protocol)"
ADVERTISED_ITEM = "Powercell AA Alkaline Batteries, 12-pack"
ADVERTISED_PRICE = "$11.49"
STORE_DOMAIN = "sureshop.example"

CLEAN_HTML = f"""<!DOCTYPE html>
<html lang="en">
<head><meta charset="utf-8"><title>SureShop checkout</title></head>
<body data-store-domain="{STORE_DOMAIN}" data-page-kind="checkout">
  <h1>SureShop</h1>
  <p>{ADVERTISED_ITEM}</p>
  <p data-price="1149" data-price-label="{ADVERTISED_ITEM}">Item {ADVERTISED_PRICE}</p>
  <p data-total="1149">Total {ADVERTISED_PRICE}</p>
  <button type="submit">Pay now</button>
</body>
</html>
"""

FEE_HTML = f"""<!DOCTYPE html>
<html lang="en">
<head><meta charset="utf-8"><title>SureShop checkout</title></head>
<body data-store-domain="{STORE_DOMAIN}" data-page-kind="checkout">
  <h1>SureShop</h1>
  <p>{ADVERTISED_ITEM}</p>
  <p data-price="1149" data-price-label="{ADVERTISED_ITEM}">Item {ADVERTISED_PRICE}</p>
  <p data-price="299" data-price-label="Care &amp; handling">Care &amp; handling $2.99</p>
  <p data-total="1448">Total $14.48</p>
  <button type="submit">Pay now</button>
</body>
</html>
"""

PRODUCT_HTML = f"""<!DOCTYPE html>
<html lang="en">
<head><meta charset="utf-8"><title>SureShop</title></head>
<body data-store-domain="{STORE_DOMAIN}" data-page-kind="product">
  <h1>SureShop</h1>
  <p>{ADVERTISED_ITEM}</p>
  <p data-price="1149" data-price-label="{ADVERTISED_ITEM}">{ADVERTISED_PRICE}</p>
</body>
</html>
"""


def page_for(order: str) -> dict[str, object]:
    """Checkout page the agent will hand to the guard after the store accepts it.

    ``text`` is gym reader text, including the item and price the product
    page advertised. ``html`` is what the store returns to the browser.
    """

    if order == "fee":
        html = FEE_HTML
        path = "/checkout?order=fee"
        return {
            "order_id": "ord-fee",
            "amount_cents": 1448,
            "currency": "USD",
            "merchant": "SureShop",
            "description": "AA batteries with a handling line",
            "html": html,
            "text": _reader_text(html, path),
            "url_path": path,
            "action": "place_order",
            "target": "Pay now",
        }
    if order == "clean":
        html = CLEAN_HTML
        path = "/checkout?order=clean"
        return {
            "order_id": "ord-clean",
            "amount_cents": 1149,
            "currency": "USD",
            "merchant": "SureShop",
            "description": "AA batteries",
            "html": html,
            "text": _reader_text(html, path),
            "url_path": path,
            "action": "place_order",
            "target": "Pay now",
        }
    raise KeyError(order)


def _reader_text(html: str, path: str) -> str:
    return checkout_reader_text(
        html,
        "http://store.example" + path,
        item=ADVERTISED_ITEM,
        price=ADVERTISED_PRICE,
    )


def expected_tag(method: str, path: str) -> str | None:
    target = urlparse(path).path
    if method == "GET" and target.startswith("/product/"):
        return TAG_BROWSER
    if method == "GET" and target == "/checkout":
        return TAG_PAYER
    return None


class StoreServer(ThreadingHTTPServer):
    verifier: Verifier


class StoreHandler(BaseHTTPRequestHandler):
    server_version = "sureshop-visa/0.1"

    def log_message(self, fmt: str, *args) -> None:
        return

    def do_GET(self) -> None:
        self._dispatch("GET")

    def do_POST(self) -> None:
        self._dispatch("POST")

    def _dispatch(self, method: str) -> None:
        verifier: Verifier = self.server.verifier  # type: ignore[attr-defined]
        tag = expected_tag(method, self.path)
        result = verifier.verify(
            authority=self.headers.get("Host", ""),
            path=self.path,
            signature_input=self.headers.get("Signature-Input"),
            signature=self.headers.get("Signature"),
            expected_tag=tag,
        )
        if not result.ok:
            self._json(
                403,
                {
                    "check": CHECK_NAME,
                    "accepted": False,
                    "reason": result.reason,
                    "key_id": result.key_id,
                    "tag": result.tag,
                    "nonce": result.nonce,
                },
            )
            return
        if tag is None:
            self._json(
                404,
                {"check": CHECK_NAME, "accepted": False, "reason": "not found"},
            )
            return
        if method == "GET" and urlparse(self.path).path.startswith("/product/"):
            self._html(200, PRODUCT_HTML)
            return
        order = parse_qs(urlparse(self.path).query).get("order", ["clean"])[0]
        try:
            page = page_for(order)
        except KeyError:
            self._json(
                404,
                {"check": CHECK_NAME, "accepted": False, "reason": "unknown order"},
            )
            return
        self._html(200, str(page["html"]))

    def _html(self, status: int, body: str) -> None:
        data = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-SureShop-Check", CHECK_NAME)
        self.end_headers()
        self.wfile.write(data)

    def _json(self, status: int, payload: dict[str, object]) -> None:
        data = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)


def make_server(verifier: Verifier, host: str = "127.0.0.1", port: int = 0) -> StoreServer:
    httpd = StoreServer((host, port), StoreHandler)
    httpd.verifier = verifier
    return httpd
