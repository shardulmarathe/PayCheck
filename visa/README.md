# Signed agent check (Visa Trusted Agent Protocol)

The agent signs each HTTP request with the open-source [Trusted Agent Protocol](https://github.com/visa/trusted-agent-protocol). The demo store checks that signature and rejects unsigned or tampered requests. `pay()` then calls the guard at `SURESHOP_CHECK_URL`. An allow submits one payment. A block logs the trick type and evidence and does not submit a payment. A guard error does not submit a payment.

## Demo

```bash
python -m visa.demo
```

The command generates an Ed25519 agent key in memory, starts the demo store, and runs five requests:

1. A signed browse (`tag="agent-browser-auth"`) of `/product/1`.
2. A signed checkout of a clean page, a guard allow, and one mock payment.
3. A signed checkout of a page with a handling fee, a guard block, and no payment.
4. The same signature sent to a different path. The store rejects it.
5. A checkout with no signature. The store rejects it.

The trace is printed and written to `runs/visa/<timestamp>.json` and `runs/visa/latest.json`.

The guard in that command is a local stand-in, so the demo runs without the trained model. To use the model instead:

```bash
python -m visa.demo --check-url "$SURESHOP_CHECK_URL"
```

`SURESHOP_CHECK_URL` may be the origin or the full `/check` URL. `pay()` POSTs the same JSON body as the shopper guard client. `text` is gym reader text from `gym.reader.format_extract` (the `url` / `prices` / `total` / `visible` / `hidden_flagged` view), not raw HTML. The checkout text also includes the item and price the product page advertised, so a fee added on this page is visible here:

```text
advertised: Powercell AA Alkaline Batteries, 12-pack | $11.49
```

```json
{"text": "url: ...\nprices:\n$11.49 | advertised Powercell AA Alkaline Batteries, 12-pack\n...", "url": "http://store/checkout?order=clean", "action": "place_order", "target": "Pay now"}
```

The client waits `SURESHOP_GUARD_TIMEOUT_S` seconds (default 60). A decision is `verdict` of `allow` or `block`, plus `attack_type` (the trick type) and `evidence`. The shopper guard's `pass` is treated as allow. A timeout, an HTTP error, or any other unusable response is a guard error: no payment is submitted, and the trace records `guard error` separately from `blocked`.

## Signature

The wire format matches the reference signer `create_ed25519_signature` in `tap-agent/agent_app.py` and the reference verifier `buildRFC9421SignatureString` in `cdn-proxy/server.js` of [visa/trusted-agent-protocol](https://github.com/visa/trusted-agent-protocol).

Covered components are `@authority` and `@path` (path plus query). The signature base is three lines, values not quoted, no trailing newline:

```text
"@authority": store.example
"@path": /checkout?order=clean
"@signature-params": ("@authority" "@path"); created=1700000000; expires=1700000480; keyId="sureshop-ab"; alg="ed25519"; nonce="<uuid>"; tag="agent-payer-auth"
```

Headers:

```text
Signature-Input: sig2=("@authority" "@path"); created=...; expires=...; keyId="..."; alg="ed25519"; nonce="..."; tag="agent-payer-auth"
Signature: sig2=:<standard base64>:
```

`agent-browser-auth` is the browse tag. `agent-payer-auth` is the checkout tag. The reference agent spells the parameter `keyId` and the algorithm `ed25519`, and this package does too.

On top of that base, the store applies the protocol's verification rules:

- `Signature-Input` and `Signature` are both required.
- `created` and `expires` are unix seconds, `created` is not in the future, `expires` is in the future, and the gap is at most 8 minutes.
- A nonce that already succeeded in that window is a replay.
- The public key for `keyId` has to be in the store's directory.
- The Ed25519 signature has to match the request's authority and path. A changed path or a flipped signature byte is rejected.

Demo keys are generated at runtime with `AgentKey.generate()`. The private key stays in process memory. The store is given only the public key. Do not commit private keys, `.pem` files, or `.p12` files.

Production merchants retrieve the public key from the scheme directory (Visa publishes keys at `https://mcp.visa.com/.well-known/jwks`). This demo registers the runtime public key instead of calling that directory.

## Payment backends

`pay(page, processor)` calls the guard first. Only an allow reaches `processor.charge`. The demo runs `MockProcessor`, and its results say `provenance: mock`. `VisaSandboxProcessor` is an unused placeholder and does not call a payment network.

## Tests

```bash
python -m pytest tests/test_visa.py
```

A valid signature is accepted. A moved path, a flipped signature byte, a missing header, a bad tag, an unknown key, a replayed nonce, and an 8-minute window violation are rejected. A guard block submits no payment. A guard allow submits exactly one.
