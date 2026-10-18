"""Signed agent check (Visa Trusted Agent Protocol)."""

import base64
import json
import threading
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from visa.demo import run_demo
from visa.guard import call_check, guard_timeout, parse_decision
from visa.keys import AgentKey, KeyDirectory
from visa.pay import pay
from visa.processors import (
    MockProcessor,
    PaymentRequest,
    VisaSandboxNotConfigured,
    VisaSandboxProcessor,
)
from visa.store import (
    ADVERTISED_ITEM,
    ADVERTISED_PRICE,
    FEE_EVIDENCE,
    make_server,
    page_for,
)
from visa.tap import (
    TAG_BROWSER,
    TAG_PAYER,
    Verifier,
    build_signature_base,
    sign,
)

NOW = 1_700_000_000
ROOT = Path(__file__).resolve().parents[1]


class BoomProcessor:
    def __init__(self) -> None:
        self.calls = 0

    def charge(self, payment: PaymentRequest):
        self.calls += 1
        raise AssertionError("payment was submitted")


class CheckServer(ThreadingHTTPServer):
    verdict = "allow"
    calls = 0
    last_body: dict | None = None


class CheckHandler(BaseHTTPRequestHandler):
    def log_message(self, fmt: str, *args) -> None:
        return

    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length)
        server: CheckServer = self.server  # type: ignore[assignment]
        server.calls += 1
        server.last_body = json.loads(raw.decode()) if raw else {}
        if server.verdict == "block":
            body = {
                "verdict": "block",
                "attack_type": "hidden_fees",
                "evidence": FEE_EVIDENCE,
                "instruction": "Remove the Care & handling fee before paying.",
            }
        elif server.verdict == "pass":
            body = {
                "verdict": "pass",
                "attack_type": "none",
                "evidence": "",
                "instruction": "",
            }
        elif server.verdict == "down":
            data = b"no"
            self.send_response(500)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return
        else:
            body = {
                "verdict": "allow",
                "attack_type": "none",
                "evidence": "",
                "instruction": "",
            }
        data = json.dumps(body).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


def _serve(httpd: ThreadingHTTPServer):
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    return httpd


def _check_url(httpd: ThreadingHTTPServer) -> str:
    host, port = httpd.server_address[:2]
    return f"http://{host}:{port}/check"


def _page() -> dict:
    return {
        "text": "Total $11.49",
        "url": "http://store.example/checkout",
        "action": "place_order",
        "target": "Pay now",
        "html": "<p>ignored</p>",
        "amount_cents": 1149,
        "currency": "USD",
        "order_id": "ord-1",
        "merchant": "SureShop",
        "description": "AA batteries",
    }


def _verifier(key: AgentKey, now: int = NOW) -> Verifier:
    directory = KeyDirectory()
    directory.register(key)
    return Verifier(directory, clock=lambda: now)


def _signed(key: AgentKey, path: str = "/checkout", tag: str = TAG_PAYER, **kwargs):
    return sign(
        key,
        authority="store.example",
        path=path,
        tag=tag,
        created=kwargs.pop("created", NOW),
        expires=kwargs.pop("expires", NOW + 480),
        **kwargs,
    )


def test_signature_base_matches_the_reference_format():
    params = (
        '("@authority" "@path"); created=1735689600; expires=1735690080; '
        'keyId="primary-ed25519"; alg="ed25519"; nonce="abc"; tag="agent-payer-auth"'
    )
    base = build_signature_base("example.com", "/checkout", params)
    assert base == (
        '"@authority": example.com\n'
        '"@path": /checkout\n'
        '"@signature-params": ("@authority" "@path"); created=1735689600; '
        'expires=1735690080; keyId="primary-ed25519"; alg="ed25519"; '
        'nonce="abc"; tag="agent-payer-auth"'
    )


def test_signed_request_verifies():
    key = AgentKey.generate()
    verifier = _verifier(key)
    signed = _signed(key)
    result = verifier.verify(
        authority="store.example",
        path="/checkout",
        signature_input=signed.signature_input,
        signature=signed.signature,
        expected_tag=TAG_PAYER,
    )
    assert result.ok
    assert result.reason == "signature accepted"
    assert result.key_id == key.key_id
    assert result.tag == TAG_PAYER
    assert result.nonce == signed.nonce


def test_tampered_path_and_signature_bytes_fail():
    key = AgentKey.generate()
    verifier = _verifier(key)
    signed = _signed(key, path="/checkout?order=clean")
    moved = verifier.verify(
        authority="store.example",
        path="/checkout?order=fee",
        signature_input=signed.signature_input,
        signature=signed.signature,
    )
    assert not moved.ok
    assert moved.reason == "invalid signature"

    inner = signed.signature[len("sig2=") + 1 : -1]
    raw = bytearray(base64.b64decode(inner))
    raw[0] ^= 0x01
    flipped = "sig2=:" + base64.b64encode(bytes(raw)).decode("ascii") + ":"
    forged = verifier.verify(
        authority="store.example",
        path="/checkout?order=clean",
        signature_input=signed.signature_input,
        signature=flipped,
    )
    assert not forged.ok
    assert forged.reason == "invalid signature"


def test_missing_headers_bad_tag_unknown_key_and_replay():
    key = AgentKey.generate()
    verifier = _verifier(key)
    missing = verifier.verify(
        authority="store.example",
        path="/checkout",
        signature_input=None,
        signature=None,
    )
    assert not missing.ok
    assert "missing" in missing.reason

    wrong_tag = _signed(key, tag="agent-payment-auth", nonce="nonce-tag")
    rejected = verifier.verify(
        authority="store.example",
        path="/checkout",
        signature_input=wrong_tag.signature_input,
        signature=wrong_tag.signature,
    )
    assert not rejected.ok
    assert "agent-payer-auth" in rejected.reason

    stranger = AgentKey.generate(key_id="somebody-else")
    foreign = _signed(stranger, nonce="nonce-foreign")
    unknown = verifier.verify(
        authority="store.example",
        path="/checkout",
        signature_input=foreign.signature_input,
        signature=foreign.signature,
    )
    assert not unknown.ok
    assert unknown.reason == "unknown keyId"

    first = _signed(key, nonce="nonce-replay")
    assert verifier.verify(
        authority="store.example",
        path="/checkout",
        signature_input=first.signature_input,
        signature=first.signature,
    ).ok
    again = verifier.verify(
        authority="store.example",
        path="/checkout",
        signature_input=first.signature_input,
        signature=first.signature,
    )
    assert not again.ok
    assert again.reason == "nonce was already used"


def test_timestamps_must_fall_inside_eight_minutes():
    key = AgentKey.generate()
    verifier = _verifier(key, now=NOW)

    wide = _signed(key, expires=NOW + 481, nonce="wide")
    wide_result = verifier.verify(
        authority="store.example",
        path="/checkout",
        signature_input=wide.signature_input,
        signature=wide.signature,
    )
    assert not wide_result.ok
    assert "8 minutes" in wide_result.reason

    future = _signed(key, created=NOW + 1, expires=NOW + 60, nonce="future")
    future_result = verifier.verify(
        authority="store.example",
        path="/checkout",
        signature_input=future.signature_input,
        signature=future.signature,
    )
    assert not future_result.ok
    assert "future" in future_result.reason

    expired = _signed(key, created=NOW - 30, expires=NOW, nonce="expired")
    expired_result = verifier.verify(
        authority="store.example",
        path="/checkout",
        signature_input=expired.signature_input,
        signature=expired.signature,
    )
    assert not expired_result.ok
    assert "expired" in expired_result.reason

    edge = _signed(key, expires=NOW + 480, nonce="edge")
    assert verifier.verify(
        authority="store.example",
        path="/checkout",
        signature_input=edge.signature_input,
        signature=edge.signature,
    ).ok


def test_store_rejects_unsigned_and_tampered_requests():
    key = AgentKey.generate()
    directory = KeyDirectory()
    directory.register(key)
    httpd = _serve(make_server(Verifier(directory)))
    host, port = httpd.server_address[:2]
    base = f"http://{host}:{port}"
    try:
        unsigned = urllib.request.Request(base + "/checkout?order=clean")
        with pytest.raises(urllib.error.HTTPError) as unsigned_error:
            urllib.request.urlopen(unsigned, timeout=5)
        assert unsigned_error.value.code == 403
        body = json.loads(unsigned_error.value.read().decode())
        assert body["accepted"] is False
        assert "missing" in body["reason"]

        signed = sign(
            key,
            authority=f"{host}:{port}",
            path="/checkout?order=clean",
            tag=TAG_PAYER,
        )
        tampered = urllib.request.Request(
            base + "/checkout?order=fee",
            headers=signed.as_http(),
        )
        with pytest.raises(urllib.error.HTTPError) as tampered_error:
            urllib.request.urlopen(tampered, timeout=5)
        assert tampered_error.value.code == 403
        tampered_body = json.loads(tampered_error.value.read().decode())
        assert tampered_body["reason"] == "invalid signature"

        accepted = urllib.request.Request(
            base + "/checkout?order=clean",
            headers=signed.as_http(),
        )
        with urllib.request.urlopen(accepted, timeout=5) as response:
            page = response.read().decode()
        assert response.status == 200
        assert "Total $11.49" in page
        assert FEE_EVIDENCE not in page

        browse = sign(
            key,
            authority=f"{host}:{port}",
            path="/product/1",
            tag=TAG_BROWSER,
        )
        with urllib.request.urlopen(
            urllib.request.Request(base + "/product/1", headers=browse.as_http()),
            timeout=5,
        ) as response:
            assert "Powercell" in response.read().decode()
    finally:
        httpd.shutdown()
        httpd.server_close()


def test_block_sends_no_payment_and_logs_the_reason(caplog):
    httpd = _serve(CheckServer(("127.0.0.1", 0), CheckHandler))
    httpd.verdict = "block"
    processor = BoomProcessor()
    try:
        with caplog.at_level("WARNING", logger="visa.pay"):
            result = pay(_page(), processor, check_url=_check_url(httpd))
    finally:
        httpd.shutdown()
        httpd.server_close()
    assert processor.calls == 0
    assert result.payment_calls == 0
    assert result.paid is False
    assert result.verdict == "block"
    assert result.outcome == "blocked"
    assert result.attack_type == "hidden_fees"
    assert result.evidence == FEE_EVIDENCE
    assert FEE_EVIDENCE in caplog.text
    assert "hidden_fees" in caplog.text
    assert httpd.calls == 1


def test_allow_submits_exactly_one_payment():
    httpd = _serve(CheckServer(("127.0.0.1", 0), CheckHandler))
    httpd.verdict = "allow"
    processor = MockProcessor()
    try:
        result = pay(_page(), processor, check_url=_check_url(httpd))
    finally:
        httpd.shutdown()
        httpd.server_close()
    assert httpd.calls == 1
    assert len(processor.payments) == 1
    assert result.payment_calls == 1
    assert result.paid is True
    assert result.outcome == "allowed"
    assert result.payment is not None
    assert result.payment.provenance == "mock"
    assert result.payment.status == "approved"
    assert result.payment.amount_cents == 1149
    assert "4111" not in json.dumps(result.to_dict())
    assert httpd.last_body == {
        "text": "Total $11.49",
        "url": "http://store.example/checkout",
        "action": "place_order",
        "target": "Pay now",
    }


def test_guard_pass_is_allow_and_a_down_guard_sends_nothing():
    httpd = _serve(CheckServer(("127.0.0.1", 0), CheckHandler))
    httpd.verdict = "pass"
    processor = MockProcessor()
    try:
        allowed = pay(_page(), processor, check_url=_check_url(httpd))
        httpd.verdict = "down"
        blocked = pay(_page(), BoomProcessor(), check_url=_check_url(httpd))
    finally:
        httpd.shutdown()
        httpd.server_close()
    assert allowed.verdict == "allow"
    assert len(processor.payments) == 1
    assert blocked.payment_calls == 0
    assert blocked.paid is False
    assert blocked.outcome == "guard error"
    assert blocked.outcome != "blocked"
    assert "guard error:" in blocked.reason
    assert "HTTP 500" in blocked.reason


def test_guard_error_sends_no_payment():
    refused = pay(_page(), BoomProcessor(), check_url="http://127.0.0.1:9/check")
    assert refused.payment_calls == 0
    assert refused.paid is False
    assert refused.payment is None
    assert refused.outcome == "guard error"
    assert refused.verdict == ""
    assert "guard error:" in refused.reason

    class GarbageHandler(CheckHandler):
        def do_POST(self) -> None:
            length = int(self.headers.get("Content-Length", "0"))
            self.rfile.read(length)
            data = b'{"error":"nope"}'
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

    broken = _serve(CheckServer(("127.0.0.1", 0), GarbageHandler))
    processor = BoomProcessor()
    try:
        result = pay(_page(), processor, check_url=_check_url(broken))
    finally:
        broken.shutdown()
        broken.server_close()
    assert processor.calls == 0
    assert result.payment_calls == 0
    assert result.paid is False
    assert result.outcome == "guard error"


def test_checkout_text_is_reader_format_with_the_advertised_price():
    advertised = f"advertised: {ADVERTISED_ITEM} | {ADVERTISED_PRICE}"
    fee = page_for("fee")
    text = str(fee["text"])
    assert text.startswith("url:")
    assert "prices:" in text
    assert "visible:" in text
    assert "hidden_flagged:" in text
    assert advertised in text
    assert f"{ADVERTISED_PRICE} | advertised {ADVERTISED_ITEM}" in text
    assert FEE_EVIDENCE in text
    assert "Total $14.48" in text
    assert "<!DOCTYPE" not in text
    assert "<html" not in text
    assert "kind: checkout" in text
    clean = str(page_for("clean")["text"])
    assert advertised in clean
    assert FEE_EVIDENCE not in clean
    assert "Total $11.49" in clean


def test_guard_timeout_defaults_to_sixty_seconds(monkeypatch):
    monkeypatch.delenv("SURESHOP_GUARD_TIMEOUT_S", raising=False)
    assert guard_timeout() == 60

    seen: dict[str, float] = {}

    class _Response:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self):
            return b'{"verdict":"allow","attack_type":"none","evidence":"","instruction":""}'

    def fake_urlopen(request, timeout):
        seen["timeout"] = timeout
        return _Response()

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setenv("SURESHOP_GUARD_TIMEOUT_S", "33")
    call_check(_page(), "http://guard.example/check")
    assert seen["timeout"] == 33
    assert guard_timeout() == 33
    monkeypatch.setenv("SURESHOP_GUARD_TIMEOUT_S", "0")
    assert guard_timeout() == 60
    monkeypatch.setenv("SURESHOP_GUARD_TIMEOUT_S", "nope")
    assert guard_timeout() == 60


def test_guard_timeout_is_a_guard_error_and_sends_no_payment(monkeypatch):
    class SlowHandler(CheckHandler):
        def do_POST(self) -> None:
            length = int(self.headers.get("Content-Length", "0"))
            self.rfile.read(length)
            time.sleep(0.4)
            data = b'{"verdict":"allow","attack_type":"none","evidence":"","instruction":""}'
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

    monkeypatch.setenv("SURESHOP_GUARD_TIMEOUT_S", "0.1")
    httpd = _serve(CheckServer(("127.0.0.1", 0), SlowHandler))
    processor = BoomProcessor()
    try:
        result = pay(_page(), processor, check_url=_check_url(httpd))
    finally:
        httpd.shutdown()
        httpd.server_close()
    assert processor.calls == 0
    assert result.payment_calls == 0
    assert result.paid is False
    assert result.outcome == "guard error"
    assert result.outcome != "blocked"
    assert result.verdict == ""
    assert "guard error:" in result.reason


def test_unusable_verdict_is_not_an_allow():
    with pytest.raises(Exception):
        parse_decision(b'{"verdict":"yes","attack_type":"none","evidence":""}')


def test_sandbox_stub_does_not_call_visa(monkeypatch, tmp_path):
    def explode(*args, **kwargs):
        raise AssertionError("a Visa API was called")

    monkeypatch.setattr(urllib.request, "urlopen", explode)
    payment = PaymentRequest(1149, "USD", "ord-1", "SureShop", "AA batteries")
    bare = VisaSandboxProcessor.from_env()
    with pytest.raises(VisaSandboxNotConfigured) as missing:
        bare.charge(payment)
    assert "VISA_USER_ID" in missing.value.missing
    assert bare.network_calls == 0

    for name in (
        "cert.pem",
        "key.pem",
        "mle-private.pem",
        "mle-server.pem",
    ):
        (tmp_path / name).write_text("not-a-real-key\n", encoding="utf-8")
    monkeypatch.setenv("VISA_USER_ID", "sandbox-user")
    monkeypatch.setenv("VISA_PASSWORD", "sandbox-password")
    monkeypatch.setenv("VISA_CERT_PATH", str(tmp_path / "cert.pem"))
    monkeypatch.setenv("VISA_KEY_PATH", str(tmp_path / "key.pem"))
    monkeypatch.setenv("VISA_MLE_KEY_ID", "mle-key")
    monkeypatch.setenv("VISA_MLE_PRIVATE_KEY_PATH", str(tmp_path / "mle-private.pem"))
    monkeypatch.setenv("VISA_MLE_SERVER_CERT_PATH", str(tmp_path / "mle-server.pem"))
    armed = VisaSandboxProcessor.from_env()
    result = armed.charge(payment)
    assert result.provenance == "visa-sandbox"
    assert result.status == "not_sent"
    assert armed.network_calls == 0
    assert "sandbox-password" not in result.detail


def test_demo_trace_allow_block_and_rejects(tmp_path):
    trace = run_demo(out_dir=tmp_path, echo=False)
    scenarios = {item["name"]: item for item in trace["scenarios"]}
    assert scenarios["browse"]["store_accepted"] is True
    assert scenarios["allow"]["paid"] is True
    assert scenarios["allow"]["payment_calls"] == 1
    assert scenarios["allow"]["payment"]["provenance"] == "mock"
    assert scenarios["block"]["paid"] is False
    assert scenarios["block"]["payment_calls"] == 0
    assert scenarios["block"]["guard"]["verdict"] == "block"
    assert scenarios["block"]["guard"]["outcome"] == "blocked"
    assert scenarios["block"]["guard"]["evidence"] == FEE_EVIDENCE
    assert scenarios["block"]["payment"] is None
    advertised = f"advertised: {ADVERTISED_ITEM} | {ADVERTISED_PRICE}"
    block_text = scenarios["block"]["guard_text"]
    allow_text = scenarios["allow"]["guard_text"]
    assert block_text.startswith("url:")
    assert "prices:" in block_text
    assert "visible:" in block_text
    assert advertised in block_text
    assert FEE_EVIDENCE in block_text
    assert not block_text.lstrip().startswith("<!DOCTYPE")
    assert advertised in allow_text
    assert FEE_EVIDENCE not in allow_text
    assert scenarios["allow"]["guard"]["outcome"] == "allowed"
    assert scenarios["tampered path"]["store_status"] == 403
    assert scenarios["tampered path"]["payment_calls"] == 0
    assert scenarios["unsigned"]["store_status"] == 403
    assert scenarios["unsigned"]["payment_calls"] == 0

    written = (tmp_path / "latest.json").read_text(encoding="utf-8")
    assert "Signed agent check (Visa Trusted Agent Protocol)" in written
    assert "verified by Visa" not in written
    assert "verified by visa" not in written.lower()
    assert "The Future of Shopping" not in written
    assert "BEGIN PRIVATE" not in written
    assert list(tmp_path.glob("*.pem")) == []
    assert list(tmp_path.glob("*.key")) == []


def test_copy_does_not_say_verified_by_visa():
    files = list((ROOT / "visa").rglob("*.py")) + list((ROOT / "visa").rglob("*.md"))
    files.append(ROOT / "README.md")
    for path in files:
        text = path.read_text(encoding="utf-8").lower()
        assert "verified by visa" not in text, path
        assert "the future of shopping" not in text, path
        assert "secured by visa" not in text, path
