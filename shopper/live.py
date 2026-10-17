"""Browser Use agent path.

Claude Haiku (``SHOPPER_MODEL``) shops through the open-source library. Before
a click that can change the cart or pay, the guarded mode reads the page with
the gym extractor and posts it to the guard. A block skips the click and puts
the guard instruction into the agent's memory.
"""

from __future__ import annotations

from shopper.browser import ShopChrome
from shopper.cost import BudgetedLLM, CostLedger
from shopper.guard import GuardClient
from shopper.page_text import read_compact
from shopper.prompt import SYSTEM_LINE, task_text
from shopper.replay import RunLog, guard_record, redact, target_from
from shopper.risky import classify_click


def _node_text(node) -> str:
    text = ""
    getter = getattr(node, "get_all_children_text", None)
    if callable(getter):
        text = getter() or ""
    if not text:
        getter = getattr(node, "get_meaningful_text_for_llm", None)
        if callable(getter):
            text = getter() or ""
    return " ".join(str(text).split())[:240]


def _node_href(node) -> str:
    return str((getattr(node, "attributes", None) or {}).get("href") or "")


def _node_primary(node) -> bool:
    classes = str((getattr(node, "attributes", None) or {}).get("class") or "")
    return "primary" in classes.split()


def _node_in_dialog(node) -> bool:
    current = node
    while current is not None:
        attrs = getattr(current, "attributes", None) or {}
        role = str(attrs.get("role") or "").lower()
        if role == "dialog" or str(attrs.get("aria-modal") or "").lower() == "true":
            return True
        current = getattr(current, "parent_node", None)
    return False


def _bbox(node) -> list[int] | None:
    rect = getattr(node, "absolute_position", None)
    if rect is None and getattr(node, "snapshot_node", None) is not None:
        rect = node.snapshot_node.bounds
    if rect is None:
        return None
    values = [getattr(rect, name, None) for name in ("x", "y", "width", "height")]
    if any(value is None for value in values):
        return None
    return [round(float(value)) for value in values]


def _selector(node) -> str:
    attrs = getattr(node, "attributes", None) or {}
    if attrs.get("id"):
        return "#" + str(attrs["id"])
    tag = getattr(node, "tag_name", None) or "element"
    if attrs.get("name"):
        return f"{tag}[name={attrs['name']}]"
    return str(tag)


def _risky_node(node) -> str | None:
    if node is None:
        return None
    return classify_click(
        _node_text(node),
        _node_href(node),
        in_dialog=_node_in_dialog(node),
        primary=_node_primary(node),
    )


class _StepTape:
    """Stash the guard result from a click so the action recorder can attach it."""

    def __init__(self) -> None:
        self.guard: dict | None = None
        self.blocked = False

    def reset(self) -> None:
        self.guard = None
        self.blocked = False


def install_guard(tools, tape: _StepTape, *, mode: str, guard: GuardClient | None) -> None:
    """Wrap Browser Use's click so a block never reaches the page."""
    original = tools._click_by_index

    async def _click_by_index(params, browser_session):
        node = None
        try:
            node = await browser_session.get_element_by_index(params.index)
        except Exception:
            node = None
        risky = _risky_node(node) if mode == "guarded" else None
        if risky and guard is not None:
            page = await browser_session.must_get_current_page()
            text = await read_compact(page)
            url = await page.get_url()
            response, latency = await guard.check(text, url=url, action=risky, target=_node_text(node))
            tape.guard = guard_record(
                endpoint=guard.endpoint,
                backend=guard.backend,
                latency_ms=latency,
                action=risky,
                response=response,
            )
            if response["verdict"] == "block":
                tape.blocked = True
                from browser_use.agent.views import ActionResult

                instruction = response.get("instruction") or "Do not take that action."
                return ActionResult(
                    long_term_memory=(
                        "A checkout guard blocked that click. Follow this instruction: " + instruction
                    )
                )
        return await original(params, browser_session)

    tools._click_by_index = _click_by_index
    tools._register_click_action()


def install_recorder(tools, tape: _StepTape, log: RunLog) -> None:
    """Record every Browser Use action with a screenshot and the page text."""
    original = tools.act

    async def act(action, browser_session, *args, **kwargs):
        tape.reset()
        page = await browser_session.must_get_current_page()
        url = ""
        text = ""
        try:
            url = await page.get_url()
        except Exception:
            url = ""
        try:
            text = await read_compact(page)
        except Exception:
            text = ""
        shot = await log.screenshot(page)
        described, target = await _describe(action, browser_session)
        result = await original(action, browser_session, *args, **kwargs)
        log.add(
            url=url,
            action=described,
            page_text=text,
            screenshot=shot,
            target=target,
            guard=tape.guard,
            blocked=tape.blocked,
        )
        return result

    tools.act = act


async def _describe(action, browser_session) -> tuple[str, dict | None]:
    data = action.model_dump(exclude_unset=True)
    if not data:
        return "action", None
    name = next(iter(data))
    params = data[name] if isinstance(data[name], dict) else {}
    index = params.get("index") if isinstance(params, dict) else None
    node = None
    if index:
        try:
            node = await browser_session.get_element_by_index(index)
        except Exception:
            node = None
    if name == "input":
        field = ""
        if node is not None:
            field = str((getattr(node, "attributes", None) or {}).get("name") or "")
        label = field or "field"
        target = target_from(_selector(node) if node is not None else "", label, _bbox(node) if node is not None else None)
        return f"fill {label}", target
    if name == "click" and node is not None:
        text = redact(_node_text(node))
        return f"click {text}".strip(), target_from(_selector(node), text, _bbox(node))
    if name == "click":
        return "click", None
    return name, None


async def drive_live(
    chrome: ShopChrome,
    log: RunLog,
    *,
    start_url: str,
    instruction: str,
    mode: str,
    guard: GuardClient | None,
    model: str,
    api_key: str,
    ledger: CostLedger,
    max_steps: int,
) -> None:
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY is required unless --mock is set")
    from browser_use import Agent, ChatAnthropic, Tools

    from shopper.browser import quiet_library_logs

    quiet_library_logs()

    tools = Tools()
    tape = _StepTape()
    install_guard(tools, tape, mode=mode, guard=guard)
    install_recorder(tools, tape, log)
    llm = BudgetedLLM(
        ChatAnthropic(model=model, api_key=api_key, max_tokens=4096),
        ledger,
    )

    async def should_stop() -> bool:
        if ledger.exceeded:
            ledger.tripped = True
            return True
        return False

    agent = Agent(
        task=task_text(instruction, start_url),
        llm=llm,
        browser_session=chrome.session,
        tools=tools,
        use_vision=False,
        use_judge=False,
        calculate_cost=False,
        extend_system_message=SYSTEM_LINE,
        enable_planning=False,
        use_thinking=False,
        enable_signal_handler=False,
        directly_open_url=True,
        generate_gif=False,
        max_actions_per_step=3,
        register_should_stop_callback=should_stop,
    )
    await agent.run(max_steps=max_steps)
