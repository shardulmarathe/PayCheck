"""Local fake-store server for a Browser Use shopper.

Run ``python -m gym.serve --port 8765``. Card fields are discarded and never
stored. Errand answer keys are on ``/errands.json`` for the harness; give the
agent the instruction and the start URL only.
"""

from __future__ import annotations

import argparse
import json
import re
import secrets
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from gym.errands import (
    ERRAND_BY_ID,
    ShopState,
    add_to_cart,
    apply_checkout_form,
    evaluate,
    public_catalog,
    remove_sku,
    spec_for,
)
from gym.paths import testset_dir
from gym.render import render_html

_SESSIONS: dict[str, ShopState] = {}
_LOCK = threading.Lock()
_PAGE_ID = re.compile(r"^[a-z0-9][a-z0-9_-]{0,80}$")
_ERRAND_PATH = re.compile(r"^/e/([a-z0-9-]+)(?:/(.*))?$")


def clear_sessions() -> None:
    with _LOCK:
        _SESSIONS.clear()


def _session(token: str, errand_id: str) -> ShopState:
    with _LOCK:
        state = _SESSIONS.get(token)
        if state is None or state.errand_id != errand_id:
            state = ShopState(errand_id=errand_id)
            _SESSIONS[token] = state
        return state


class Handler(BaseHTTPRequestHandler):
    server_version = "checkout-guard-gym/0.1"

    def log_message(self, fmt: str, *args) -> None:
        # Keep the demo terminal quiet. Tests assert on responses, not logs.
        return

    def do_GET(self) -> None:
        self._route("GET")

    def do_POST(self) -> None:
        self._route("POST")

    def _route(self, method: str) -> None:
        parsed = urlparse(self.path)
        path = parsed.path
        if path == "/health" and method == "GET":
            self._text(200, "ok\n")
            return
        if path == "/" and method == "GET":
            self._html(200, _index())
            return
        if path == "/errands.json" and method == "GET":
            self._json(200, {"errands": public_catalog()})
            return
        if path.startswith("/snapshot/") and method == "GET":
            self._snapshot(path[len("/snapshot/") :])
            return
        if path.startswith("/labels/") and method == "GET":
            self._label(path[len("/labels/") :])
            return
        match = _ERRAND_PATH.match(path)
        if match:
            self._errand(method, match.group(1), match.group(2) or "")
            return
        self._text(404, "Not found\n")

    def _errand(self, method: str, errand_id: str, rest: str) -> None:
        errand = ERRAND_BY_ID.get(errand_id)
        if errand is None:
            self._text(404, "Unknown errand\n")
            return
        token = self._token()
        state = _session(token, errand_id)
        form = _form(self) if method == "POST" else {}
        if method == "POST" and rest == "add":
            add_to_cart(state, errand)
            self._redirect(f"/e/{errand_id}/cart", token)
            return
        if method == "POST" and rest == "cart/remove":
            remove_sku(state, form.get("sku", ""))
            self._redirect(f"/e/{errand_id}/cart", token)
            return
        if method == "POST" and rest == "update":
            apply_checkout_form(state, form)
            self._redirect(f"/e/{errand_id}/checkout", token)
            return
        if method == "POST" and rest == "continue":
            apply_checkout_form(state, form)
            self._redirect(f"/e/{errand_id}/payment", token)
            return
        if method == "POST" and rest == "pay":
            # Card numbers, CVV, and bank passwords are not stored.
            state.submitted_payment = True
            state.paid = True
            state.aborted = False
            self._redirect(f"/e/{errand_id}/done", token)
            return
        if method == "POST" and rest == "abort":
            state.aborted = True
            state.paid = False
            self._redirect(f"/e/{errand_id}/done", token)
            return
        if method == "GET" and rest == "result":
            self._json(200, evaluate(errand, state), token)
            return
        if method != "GET":
            self._text(405, "Method not allowed\n", token)
            return
        if rest == "":
            kind = "product"
        elif rest == "cart":
            kind = "cart"
        elif rest == "checkout":
            kind = "checkout"
        elif rest == "payment":
            kind = "payment"
        elif rest == "done":
            self._html(200, _done(errand, state), token)
            return
        else:
            self._text(404, "Not found\n", token)
            return
        html = render_html(spec_for(errand, state, kind))
        self._html(200, html, token)

    def _token(self) -> str:
        cookie = self.headers.get("Cookie", "")
        for part in cookie.split(";"):
            name, _, value = part.strip().partition("=")
            if name == "cg_session" and value:
                return value
        return secrets.token_hex(16)

    def _snapshot(self, page_id: str) -> None:
        if not _PAGE_ID.fullmatch(page_id):
            self._text(404, "Not found\n")
            return
        path = testset_dir() / "html" / f"{page_id}.html"
        if not path.is_file():
            self._text(404, "Unknown snapshot\n")
            return
        self._html(200, path.read_text(encoding="utf-8"))

    def _label(self, page_id: str) -> None:
        if not _PAGE_ID.fullmatch(page_id):
            self._text(404, "Not found\n")
            return
        labels = testset_dir() / "labels.jsonl"
        if not labels.is_file():
            self._text(404, "No labels\n")
            return
        for line in labels.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            if row["page_id"] == page_id:
                self._json(200, row)
                return
        self._text(404, "Unknown label\n")

    def _redirect(self, location: str, token: str) -> None:
        self.send_response(303)
        self._cookie(token)
        self.send_header("Location", location)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def _html(self, status: int, body: str, token: str | None = None) -> None:
        data = body.encode("utf-8")
        self.send_response(status)
        if token:
            self._cookie(token)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def _text(self, status: int, body: str, token: str | None = None) -> None:
        data = body.encode("utf-8")
        self.send_response(status)
        if token:
            self._cookie(token)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _json(self, status: int, payload: dict, token: str | None = None) -> None:
        data = (json.dumps(payload, indent=2) + "\n").encode("utf-8")
        self.send_response(status)
        if token:
            self._cookie(token)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _cookie(self, token: str) -> None:
        self.send_header("Set-Cookie", f"cg_session={token}; Path=/; HttpOnly; SameSite=Lax")


def _form(handler: BaseHTTPRequestHandler) -> dict[str, str]:
    length = int(handler.headers.get("Content-Length") or 0)
    raw = handler.rfile.read(length).decode("utf-8") if length else ""
    parsed = parse_qs(raw, keep_blank_values=True)
    return {key: values[0] for key, values in parsed.items()}


def _index() -> str:
    rows = []
    for errand in public_catalog():
        harness = errand["harness"]
        rows.append(
            "<tr>"
            f"<td><a href=\"{errand['start_url']}\">{errand['id']}</a></td>"
            f"<td>{errand['instruction']}</td>"
            f"<td>{harness['attack_type']}</td>"
            f"<td>{', '.join(harness['trick_steps'])}</td>"
            f"<td>{harness['correct']['action']}</td>"
            f"<td>{harness['correct']['total_cents'] if harness['correct']['total_cents'] is not None else '—'}</td>"
            "</tr>"
        )
    body = "\n".join(rows)
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>Checkout guard gym</title>
  <style>
    body {{ font-family: "Liberation Sans", sans-serif; margin: 32px; color: #1c1c1c; }}
    table {{ border-collapse: collapse; width: 100%; }}
    td, th {{ border-bottom: 1px solid #ddd; text-align: left; padding: 8px; vertical-align: top; }}
    code {{ background: #f4f4f0; padding: 2px 4px; }}
  </style>
</head>
<body>
  <h1>Checkout guard gym</h1>
  <p>Fake stores for a shopping agent. Give the agent the instruction and the start URL. The trick type and the correct cart are for the harness, not the shopper.</p>
  <p>Machine-readable list: <a href="/errands.json"><code>/errands.json</code></a>. Frozen pages: <code>/snapshot/&lt;page_id&gt;</code>.</p>
  <table>
    <tr><th>Errand</th><th>Instruction</th><th>Trick</th><th>Step</th><th>Correct action</th><th>Correct total (cents)</th></tr>
    {body}
  </table>
</body>
</html>
"""


def _done(errand: dict, state: ShopState) -> str:
    if state.aborted and not state.paid:
        message = "You left without paying."
    elif state.paid:
        message = "Order placed."
    else:
        message = "No order was placed."
    return f"""<!DOCTYPE html>
<html lang="en">
<head><meta charset="utf-8"><title>Done | {errand['store']['brand']}</title></head>
<body style="font-family: Liberation Sans, sans-serif; margin: 32px;">
  <h1>{message}</h1>
  <p><a href="/e/{errand['id']}">Back to the product</a></p>
</body>
</html>
"""


def make_server(host: str = "127.0.0.1", port: int = 8765) -> ThreadingHTTPServer:
    return ThreadingHTTPServer((host, port), Handler)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Serve fake stores for the shopper.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args(argv)
    httpd = make_server(args.host, args.port)
    print(f"serving http://{args.host}:{args.port}")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("stopping")
    finally:
        httpd.server_close()


if __name__ == "__main__":
    main()
