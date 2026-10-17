"""Run one errand and write its replay.

``--mock`` follows :mod:`shopper.policy`: the prominent path, with no errand
special cases. Guarded mode asks the guard before every risky click and, on
block, appends the guard instruction for the next choice. The live path is the
same recording and scoring wrapped around a Browser Use agent.
"""

from __future__ import annotations

from pathlib import Path

from shopper.browser import ShopChrome
from shopper.cost import CostCapExceeded, CostLedger
from shopper.guard import GuardClient
from shopper.page_text import read_compact
from shopper.policy import Action, choose
from shopper.prompt import TEST_CARD_CVV, TEST_CARD_EXPIRY, TEST_CARD_NUMBER
from shopper.replay import RunLog, assemble, guard_record, now_iso, relpath, target_from, write_json
from shopper.score import empty_score, score_result
from shopper.snapshot import Control, read_controls

# Filled only when the payment page itself shows the field. Not part of the prompt.
_BANK_PASSWORD = "hunter2"
_PAYMENT_FIELDS = (
    ("card_number", TEST_CARD_NUMBER),
    ("exp", TEST_CARD_EXPIRY),
    ("cvv", TEST_CARD_CVV),
    ("bank_password", _BANK_PASSWORD),
)


def _field(controls: list[Control], name: str) -> Control | None:
    for control in controls:
        if control.tag == "input" and control.name == name:
            return control
    return None


def _action_label(action: Action) -> str:
    if action.kind == "pay":
        return f"click {action.text}"
    if action.kind == "click":
        return f"click {action.text}"
    return f"{action.kind} {action.text}".strip()


async def _record(log: RunLog, page, *, url: str, action: str, page_text: str, target: dict | None, guard: dict | None, blocked: bool) -> None:
    shot = await log.screenshot(page)
    log.add(url=url, action=action, page_text=page_text, screenshot=shot, target=target, guard=guard, blocked=blocked)


async def _fill_payment(chrome: ShopChrome, log: RunLog, controls: list[Control]) -> None:
    for name, value in _PAYMENT_FIELDS:
        control = _field(controls, name)
        if control is None or control.value:
            continue
        page = await chrome.page()
        url = await page.get_url()
        text = await read_compact(page)
        await _record(
            log,
            page,
            url=url,
            action=f"fill {name}",
            page_text=text,
            target=target_from(control.selector, name, control.bbox),
            guard=None,
            blocked=False,
        )
        await chrome.fill(control.selector, value)


async def drive_mock(
    chrome: ShopChrome,
    log: RunLog,
    *,
    start_url: str,
    mode: str,
    guard: GuardClient | None,
    max_steps: int,
) -> None:
    await chrome.goto(start_url)
    page = await chrome.page()
    url = await page.get_url()
    text = await read_compact(page)
    await _record(log, page, url=url, action="navigate", page_text=text, target=None, guard=None, blocked=False)

    instructions: list[str] = []
    last_signature: tuple | None = None
    repeats = 0
    for _ in range(max_steps):
        page = await chrome.page()
        url = await page.get_url()
        controls = await read_controls(page)
        text = await read_compact(page)
        action = choose(controls, url, instructions)
        if action is None or action.kind == "done":
            await _record(log, page, url=url, action="done", page_text=text, target=None, guard=None, blocked=False)
            return
        signature = (url, action.signature())
        if signature == last_signature:
            repeats += 1
        else:
            repeats = 0
            last_signature = signature
        if repeats >= 2:
            await _record(log, page, url=url, action="stall", page_text=text, target=None, guard=None, blocked=False)
            return

        guard_payload = None
        blocked = False
        if action.risky and mode == "guarded":
            if guard is None:
                raise RuntimeError("guarded mode requires a guard client")
            response, latency = await guard.check(text, url=url, action=action.risky, target=action.text)
            guard_payload = guard_record(
                endpoint=guard.endpoint,
                backend=guard.backend,
                latency_ms=latency,
                action=action.risky,
                response=response,
            )
            blocked = response["verdict"] == "block"
        target = target_from(action.selector, action.text, action.bbox)
        if blocked:
            await _record(
                log,
                page,
                url=url,
                action=_action_label(action),
                page_text=text,
                target=target,
                guard=guard_payload,
                blocked=True,
            )
            instruction = (guard_payload or {}).get("response", {}).get("instruction") or ""
            if instruction and (not instructions or instructions[-1] != instruction):
                instructions.append(instruction)
            continue
        if action.kind == "pay":
            await _fill_payment(chrome, log, controls)
            page = await chrome.page()
            await _record(
                log,
                page,
                url=url,
                action=_action_label(action),
                page_text=text,
                target=target,
                guard=guard_payload,
                blocked=False,
            )
            await chrome.click(action.selector)
        else:
            await _record(
                log,
                page,
                url=url,
                action=_action_label(action),
                page_text=text,
                target=target,
                guard=guard_payload if action.risky else None,
                blocked=False,
            )
            await chrome.perform(action)
        if action.corrective and instructions:
            instructions.pop()
    page = await chrome.page()
    url = await page.get_url()
    text = await read_compact(page)
    await _record(log, page, url=url, action="stop", page_text=text, target=None, guard=None, blocked=False)


async def run_errand(
    *,
    errand: dict,
    mode: str,
    base_url: str,
    out_dir: Path,
    guard: GuardClient | None,
    mock: bool,
    model: str,
    ledger: CostLedger,
    video: bool,
    max_steps: int,
    api_key: str | None,
) -> dict:
    """Drive one errand in one mode and write ``<errand>_<mode>.json``."""
    errand_id = errand["id"]
    harness = errand.get("harness") or {}
    attack_type = harness.get("attack_type") or "none"
    instruction = errand.get("instruction") or ""
    start_url = base_url.rstrip("/") + "/" + str(errand.get("start_url") or f"/e/{errand_id}").lstrip("/")
    started_at = now_iso()
    spent_before = ledger.usd
    log = RunLog(out_dir, errand_id, mode)
    error: str | None = None
    result: dict | None = None
    tripped = False
    video_rel: str | None = None
    chrome: ShopChrome | None = None
    try:
        if ledger.exceeded:
            ledger.tripped = True
            tripped = True
            raise CostCapExceeded(ledger.usd, ledger.max_usd)
        chrome = ShopChrome(record_video=video)
        await chrome.__aenter__()
        try:
            if mock:
                await drive_mock(chrome, log, start_url=start_url, mode=mode, guard=guard, max_steps=max_steps)
            else:
                from shopper.live import drive_live

                await drive_live(
                    chrome,
                    log,
                    start_url=start_url,
                    instruction=instruction,
                    mode=mode,
                    guard=guard,
                    model=model,
                    api_key=api_key or "",
                    ledger=ledger,
                    max_steps=max_steps,
                )
        except CostCapExceeded as exc:
            tripped = True
            error = str(exc)
        except Exception as exc:
            error = f"{type(exc).__name__}: {exc}"
        if chrome.session is not None:
            try:
                result = await chrome.fetch_result(errand_id)
            except Exception as exc:
                if error is None:
                    error = f"{type(exc).__name__}: {exc}"
    except CostCapExceeded as exc:
        tripped = True
        error = str(exc)
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"
    finally:
        if chrome is not None:
            await chrome.__aexit__(None, None, None)
            if video:
                dest = out_dir / "shots" / f"{errand_id}_{mode}.webm"
                moved = chrome.consume_video(dest)
                if moved is not None:
                    video_rel = relpath(moved, out_dir)
            else:
                chrome.consume_video(None)
    if ledger.tripped:
        tripped = True
    if result is not None:
        if error and not tripped:
            result = dict(result)
            result["error"] = error
        scored = score_result(result, mode=mode, attack_type=attack_type, tripped=tripped)
    else:
        scored = empty_score(mode=mode, tripped=tripped, error=error)
    if tripped and scored["outcome"] != "stopped":
        scored = dict(scored)
        scored["outcome"] = "stopped"
    document = assemble(
        errand_id=errand_id,
        mode=mode,
        mock=mock,
        model="mock" if mock else model,
        instruction=instruction,
        start_url=start_url,
        guard_backend=(guard.backend if guard is not None and mode == "guarded" else None),
        attack_type=attack_type,
        started_at=started_at,
        steps=log.steps,
        scored=scored,
        usd_spent=max(0.0, ledger.usd - spent_before),
        video=video_rel,
        error=error if scored["outcome"] in {"error", "stopped"} else None,
    )
    write_json(out_dir / f"{errand_id}_{mode}.json", document)
    return document
