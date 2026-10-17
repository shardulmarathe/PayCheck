"""End-to-end demo of Signed agent check (Visa Trusted Agent Protocol).

A signed agent request hits the demo store. The store checks the signature.
``pay`` then calls the guard. Allow submits one mock payment. Block logs the
trick and evidence and does not.

The guard in this command is a local stand-in so the trace runs without the
trained model. Point ``--check-url`` at a real ``/check`` to use the model.
Keys are generated in memory and are not written to disk.

    python -m visa.demo
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import threading
import traceback
import urllib.error
import urllib.request
from contextlib import contextmanager
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Iterator
from urllib.parse import urlparse

from visa.keys import AgentKey, KeyDirectory
from visa.pay import pay
from visa.processors import MockProcessor, PaymentProcessor
from visa.store import (
    CHECK_NAME,
    FEE_EVIDENCE,
    StoreServer,
    make_server,
    page_for,
)
from visa.tap import TAG_BROWSER, TAG_PAYER, SignedRequest, Verifier, sign

ROOT = Path(__file__).resolve().parents[1]
LINE = "-" * 72
_print = print


def _say(*parts: object) -> None:
    _print(*parts, flush=True)


class _GuardHandler(BaseHTTPRequestHandler):
    """Local stand-in for the trained model at ``/check``."""

    calls = 0

    def log_message(self, fmt: str, *args) -> None:
        return

    def do_POST(self) -> None:
        if self.path != "/check":
            self._send(404, {"verdict": "block", "attack_type": "none", "evidence": ""})
            return
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length)
        try:
            page = json.loads(raw.decode("utf-8"))
        except json.JSONDecodeError:
            page = {}
        html = str(page.get("html", ""))
        type(self).calls += 1
        if FEE_EVIDENCE in html:
            body = {
                "verdict": "block",
                "attack_type": "hidden_fees",
                "evidence": FEE_EVIDENCE,
                "instruction": "Remove the Care & handling fee before paying.",
            }
        else:
            body = {
                "verdict": "allow",
                "attack_type": "none",
                "evidence": "",
                "instruction": "",
            }
        self._send(200, body)

    def _send(self, status: int, body: dict[str, str]) -> None:
        data = json.dumps(body).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


def _guard_server() -> ThreadingHTTPServer:
    return ThreadingHTTPServer(("127.0.0.1", 0), _GuardHandler)


@contextmanager
def _serving(httpd: ThreadingHTTPServer) -> Iterator[ThreadingHTTPServer]:
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        yield httpd
    finally:
        httpd.shutdown()
        httpd.server_close()


def _base(httpd: ThreadingHTTPServer) -> str:
    host, port = httpd.server_address[:2]
    return f"http://{host}:{port}"


def _fetch(url: str, signed: SignedRequest | None) -> tuple[int, str]:
    headers = {} if signed is None else signed.as_http()
    request = urllib.request.Request(url, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            return response.status, response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode("utf-8")


def _scenario_browse(key: AgentKey, store: StoreServer) -> dict[str, object]:
    base = _base(store)
    authority = _authority(base)
    signed = sign(
        key,
        authority=authority,
        path="/product/1",
        tag=TAG_BROWSER,
    )
    status, body = _fetch(base + "/product/1", signed)
    return {
        "name": "browse",
        "request": _request_view(signed, "GET", "/product/1"),
        "store_status": status,
        "store_accepted": status == 200 and "Powercell" in body,
        "guard_called": False,
        "payment_calls": 0,
        "payment": None,
    }


def _scenario_checkout(
    name: str,
    order: str,
    key: AgentKey,
    store: StoreServer,
    processor: PaymentProcessor,
    check_url: str,
    *,
    echo: bool = False,
) -> dict[str, object]:
    base = _base(store)
    authority = _authority(base)
    path = f"/checkout?order={order}"
    signed = sign(key, authority=authority, path=path, tag=TAG_PAYER)
    if echo:
        _say()
        _say(f"scenario: {name}")
        _print_signed_request(signed, "GET", path)
    status, body = _fetch(base + path, signed)
    accepted = status == 200
    if echo:
        _say(
            f"  2. store signature check: {'accept' if accepted else 'reject'} (HTTP {status})"
        )
        if accepted:
            _say("  3. guard /check")
    payment_calls_before = _call_count(processor)
    pay_result = None
    if accepted:
        page = page_for(order)
        page["html"] = body
        page["url"] = base + path
        pay_result = pay(page, processor, check_url=check_url)
    payment_calls = _call_count(processor) - payment_calls_before
    record = {
        "name": name,
        "request": _request_view(signed, "GET", path),
        "store_status": status,
        "store_accepted": accepted,
        "store_body": None if accepted else _maybe_json(body),
        "guard": None if pay_result is None else {
            "verdict": pay_result.verdict,
            "attack_type": pay_result.attack_type,
            "evidence": pay_result.evidence,
            "instruction": pay_result.instruction,
            "reason": pay_result.reason,
        },
        "payment_calls": payment_calls,
        "payment": None if pay_result is None or pay_result.payment is None else pay_result.payment.to_dict(),
        "paid": False if pay_result is None else pay_result.paid,
    }
    if echo:
        _print_guard_and_payment(record)
    return record


def _scenario_tampered(key: AgentKey, store: StoreServer, processor: PaymentProcessor) -> dict[str, object]:
    base = _base(store)
    authority = _authority(base)
    signed = sign(
        key,
        authority=authority,
        path="/checkout?order=clean",
        tag=TAG_PAYER,
    )
    before = _call_count(processor)
    status, body = _fetch(base + "/checkout?order=fee", signed)
    return {
        "name": "tampered path",
        "request": _request_view(signed, "GET", "/checkout?order=clean"),
        "sent_path": "/checkout?order=fee",
        "store_status": status,
        "store_accepted": False,
        "store_body": _maybe_json(body),
        "guard_called": False,
        "payment_calls": _call_count(processor) - before,
        "payment": None,
        "paid": False,
    }


def _scenario_unsigned(store: StoreServer, processor: PaymentProcessor) -> dict[str, object]:
    base = _base(store)
    before = _call_count(processor)
    status, body = _fetch(base + "/checkout?order=clean", None)
    return {
        "name": "unsigned",
        "request": None,
        "store_status": status,
        "store_accepted": False,
        "store_body": _maybe_json(body),
        "guard_called": False,
        "payment_calls": _call_count(processor) - before,
        "payment": None,
        "paid": False,
    }


def _call_count(processor: PaymentProcessor) -> int:
    payments = getattr(processor, "payments", None)
    if payments is None:
        return 0
    return len(payments)


def _request_view(signed: SignedRequest, method: str, path: str) -> dict[str, object]:
    return {
        "method": method,
        "path": path,
        "authority": signed.authority,
        "key_id": signed.key_id,
        "alg": signed.alg,
        "tag": signed.tag,
        "nonce": signed.nonce,
        "created": signed.created,
        "expires": signed.expires,
        "signature_input": signed.signature_input,
        "signature": signed.signature,
    }


def _maybe_json(body: str) -> object:
    try:
        return json.loads(body)
    except json.JSONDecodeError:
        return body


def _authority(base: str) -> str:
    return urlparse(base).netloc


def run_demo(
    *,
    out_dir: Path | None = None,
    check_url: str | None = None,
    echo: bool = True,
) -> dict[str, object]:
    key = AgentKey.generate()
    directory = KeyDirectory()
    directory.register(key)
    verifier = Verifier(directory)
    processor = MockProcessor()
    store = make_server(verifier)
    own_guard = check_url is None
    guard = _guard_server() if own_guard else None

    def _run(active_check: str) -> dict[str, object]:
        guard_label = "local stand-in" if own_guard else active_check
        if echo:
            _print_banner(key.key_id, guard_label)
        browse = _scenario_browse(key, store)
        if echo:
            _echo_scenario(browse)
        clean = _scenario_checkout(
            "allow", "clean", key, store, processor, active_check, echo=echo
        )
        blocked = _scenario_checkout(
            "block", "fee", key, store, processor, active_check, echo=echo
        )
        tampered = _scenario_tampered(key, store, processor)
        if echo:
            _echo_scenario(tampered)
        unsigned = _scenario_unsigned(store, processor)
        if echo:
            _echo_scenario(unsigned)
        trace = {
            "title": CHECK_NAME,
            "challenge": "The Future of Shopping: Powered by AI, Secured by Visa",
            "protocol": "https://github.com/visa/trusted-agent-protocol",
            "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "agent_key_id": key.key_id,
            "agent_public_key_b64": key.public_key_b64,
            "payment_backend": "mock",
            "guard": guard_label,
            "scenarios": [browse, clean, blocked, tampered, unsigned],
        }
        destination = _write(trace, out_dir)
        trace["wrote"] = str(destination)
        if echo:
            _say(LINE)
            _say(f"wrote {destination}")
            _say(LINE)
        return trace

    with _serving(store):
        if guard is None:
            assert check_url is not None
            return _run(check_url)
        with _serving(guard):
            return _run(_base(guard) + "/check")


def _write(trace: dict[str, object], out_dir: Path | None) -> Path:
    directory = out_dir if out_dir is not None else ROOT / "runs" / "visa"
    directory.mkdir(parents=True, exist_ok=True)
    stamp = str(trace["generated_at"]).replace(":", "").replace("-", "")
    path = directory / f"{stamp}.json"
    encoded = json.dumps(trace, indent=2) + "\n"
    path.write_text(encoded, encoding="utf-8")
    (directory / "latest.json").write_text(encoded, encoding="utf-8")
    return path


def _print_banner(key_id: str, guard_label: str) -> None:
    _say(LINE)
    _say(CHECK_NAME)
    _say("The Future of Shopping: Powered by AI, Secured by Visa")
    _say("protocol: https://github.com/visa/trusted-agent-protocol")
    _say(f"agent keyId: {key_id}  (private key stayed in memory)")
    _say(f"guard: {guard_label}")
    _say("payment backend: mock  (provenance: mock)")
    _say(LINE)


def _print_signed_request(signed: SignedRequest, method: str, path: str) -> None:
    _say(f"  1. agent signed {method} {path}")
    _say(f"     keyId: {signed.key_id}")
    _say(f"     alg: {signed.alg}   tag: {signed.tag}")
    _say(f"     nonce: {signed.nonce}")
    _say(f"     created: {signed.created}   expires: {signed.expires}")
    _say(f"     Signature-Input: {signed.signature_input}")


def _print_guard_and_payment(scenario: dict[str, object]) -> None:
    guard = scenario.get("guard")
    if isinstance(guard, dict):
        _say(f"     verdict: {guard['verdict']}")
        _say(f"     trick: {guard['attack_type']}")
        _say(f"     evidence: {guard['evidence']!r}")
        if guard.get("reason"):
            _say(f"     logged: {guard['reason']}")
    payment = scenario.get("payment")
    calls = scenario.get("payment_calls")
    if isinstance(payment, dict):
        _say("  4. payment")
        _say(f"     status: {payment['status']}")
        _say(f"     provenance: {payment['provenance']}")
        _say(f"     reference: {payment['reference']}")
        _say(f"     amount_cents: {payment['amount_cents']}")
        _say(f"     calls: {calls}")
    else:
        _say("  4. payment: not sent")
        _say(f"     calls: {calls}")


def _echo_scenario(scenario: dict[str, object]) -> None:
    _say()
    _say(f"scenario: {scenario['name']}")
    request = scenario.get("request")
    if isinstance(request, dict):
        _say(f"  1. agent signed {request['method']} {request['path']}")
        _say(f"     keyId: {request['key_id']}")
        _say(f"     alg: {request['alg']}   tag: {request['tag']}")
        _say(f"     nonce: {request['nonce']}")
        _say(f"     created: {request['created']}   expires: {request['expires']}")
        _say(f"     Signature-Input: {request['signature_input']}")
    else:
        _say("  1. agent sent no signature")
    sent = scenario.get("sent_path")
    if sent:
        _say(f"     request path was changed to {sent} after signing")
    status = scenario["store_status"]
    accepted = scenario["store_accepted"]
    _say(f"  2. store signature check: {'accept' if accepted else 'reject'} (HTTP {status})")
    body = scenario.get("store_body")
    if isinstance(body, dict) and body.get("reason"):
        _say(f"     reason: {body['reason']}")
    guard = scenario.get("guard")
    if isinstance(guard, dict):
        _say("  3. guard /check")
        _say(f"     verdict: {guard['verdict']}")
        _say(f"     trick: {guard['attack_type']}")
        _say(f"     evidence: {guard['evidence']!r}")
        if guard.get("reason"):
            _say(f"     logged: {guard['reason']}")
    elif scenario.get("guard_called") is False and scenario["name"] != "browse":
        _say("  3. guard /check: not called")
    if scenario["name"] == "browse":
        _say("  3. guard /check: skipped (browsing is not a payment)")
        _say("  4. payment: not sent")
        return
    payment = scenario.get("payment")
    calls = scenario.get("payment_calls")
    if isinstance(payment, dict):
        _say("  4. payment")
        _say(f"     status: {payment['status']}")
        _say(f"     provenance: {payment['provenance']}")
        _say(f"     reference: {payment['reference']}")
        _say(f"     amount_cents: {payment['amount_cents']}")
        _say(f"     calls: {calls}")
    else:
        _say("  4. payment: not sent")
        _say(f"     calls: {calls}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=CHECK_NAME)
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="directory for the JSON trace (default: runs/visa)",
    )
    parser.add_argument(
        "--check-url",
        default=None,
        help="guard /check URL. Default: a local stand-in started by this command",
    )
    args = parser.parse_args(argv)
    logging.basicConfig(
        level=logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
        stream=sys.stdout,
    )
    try:
        run_demo(out_dir=args.out, check_url=args.check_url, echo=True)
    except Exception:
        traceback.print_exc()
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
