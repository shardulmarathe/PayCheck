# Signed agent check (Visa Trusted Agent Protocol)

SureShop's payment step for the Visa challenge, The Future of Shopping: Powered by AI, Secured by Visa.

The agent signs each HTTP request with Visa's open-source [Trusted Agent Protocol](https://github.com/visa/trusted-agent-protocol). The demo store checks that signature and rejects unsigned or tampered requests. `pay()` then calls the guard at `SURESHOP_CHECK_URL`. An allow submits one payment. A block logs the trick type and evidence and does not submit a payment.

The name of this step is Signed agent check (Visa Trusted Agent Protocol).

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
SURESHOP_CHECK_URL=http://127.0.0.1:8787 python -m visa.demo --check-url http://127.0.0.1:8787/check
```

`SURESHOP_CHECK_URL` may be the origin or the full `/check` URL. `pay()` POSTs JSON:

```json
{"html": "<!DOCTYPE html>...", "url": "http://store/checkout?order=clean", "amount_cents": 1149, "currency": "USD", "order_id": "ord-clean"}
```

A decision is `verdict` of `allow` or `block`, plus `attack_type` (the trick type) and `evidence`. The gym guard's `pass` is treated as allow. Anything else, including a down guard, does not submit a payment.

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

`pay(page, processor)` calls the guard first. Only an allow reaches `processor.charge`.

| `SURESHOP_PAYMENT_BACKEND` | Adapter | What a result says |
| --- | --- | --- |
| `mock` (default) | `MockProcessor` | `provenance: mock` |
| `visa-sandbox` | `VisaSandboxProcessor` | `provenance: visa-sandbox` |

`MockProcessor` is what the demo runs. It approves locally and does not contact a card network.

`VisaSandboxProcessor` is a stub for the Visa Intelligent Commerce developer sandbox. `charge()` does not open a socket. With any required variable unset it raises `VisaSandboxNotConfigured` and names the missing variables. With every variable set it still returns `status: not_sent`, because this build does not submit a live charge.

## Switching to the Visa developer sandbox

The demo keeps using the mock until you select the stub:

```bash
export SURESHOP_PAYMENT_BACKEND=visa-sandbox
```

Create a Visa Developer account, open a project, and add **Visa Intelligent Commerce**. Sandbox access is the credential source. Nothing in this package calls `https://sandbox.api.visa.com` until a later change replaces `VisaSandboxProcessor.charge`, and that method still refuses to run unless every variable below is set.

Set these from the project's Sandbox credentials. Paths are files on disk. Do not commit them.

| Variable | Required | Where it comes from |
| --- | --- | --- |
| `VISA_USER_ID` | yes | Project → Sandbox → Credentials. Two-way SSL user id (HTTP basic auth). |
| `VISA_PASSWORD` | yes | Same panel. Two-way SSL password. |
| `VISA_CERT_PATH` | yes | Client certificate PEM (`cert.pem`) downloaded after Visa signs your certificate request. |
| `VISA_KEY_PATH` | yes | Private key created when you generated that certificate request. Visa does not have this key. |
| `VISA_KEY_PASSPHRASE` | only if that key is encrypted | The passphrase you chose for the key. |
| `VISA_MLE_KEY_ID` | yes | Project → Sandbox → Message-Level Encryption → Generate Key ID. Sent as the `keyId` header on encrypted calls. |
| `VISA_MLE_PRIVATE_KEY_PATH` | yes | Private key for the MLE certificate request. Used to decrypt sandbox responses. |
| `VISA_MLE_SERVER_CERT_PATH` | yes | Visa's MLE server certificate for that key id. Used to encrypt request payloads. |
| `VISA_SANDBOX_BASE_URL` | no | Defaults to `https://sandbox.api.visa.com`. Certification is `https://cert.api.visa.com`. Production is `https://api.visa.com`. This stub accepts only the sandbox host. |

Two-way SSL and message-level encryption are documented at:

- https://developer.visa.com/capabilities/visa-intelligent-commerce
- https://developer.visa.com/pages/working-with-visa-apis/two-way-ssl
- https://developer.visa.com/docs/message-level-encryption

A sandbox project also needs a certificate signing request whose UID matches the project, the Visa Developer Platform sandbox CA installed next to the client certificate, and the MLE key id embedded in the MLE certificate request. Those files are how `VISA_CERT_PATH`, `VISA_KEY_PATH`, `VISA_MLE_PRIVATE_KEY_PATH`, and `VISA_MLE_SERVER_CERT_PATH` get their contents.

Visa Acceptance Intelligent Commerce is a different product (`https://apitest.visaacceptance.com`, paths under `/acp/v1/instructions`). It uses a merchant or organization id, a REST shared-secret key, a token requester id, and a relationship id from a Visa Acceptance account manager, plus TMS Passkey setup. This stub does not call that host. Those credentials are not a substitute for the Developer Center variables above.

## Tests

```bash
python -m pytest tests/test_visa.py
```

A valid signature is accepted. A moved path, a flipped signature byte, a missing header, a bad tag, an unknown key, a replayed nonce, and an 8-minute window violation are rejected. A guard block submits no payment. A guard allow submits exactly one.
