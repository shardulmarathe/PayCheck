"""Compact page text for the guard.

``read_page`` is the entry point for a live URL. Batch rendering uses the same
extractor on an already open Playwright page.
"""

from __future__ import annotations

from gym.taxonomy import VIEWPORT

# Rough budget: 4 characters per token, 2,000 tokens.
MAX_CHARS = 8000

EXTRACT_JS = r"""
() => {
  const vw = window.innerWidth;
  const vh = window.innerHeight;

  function parseRgb(value) {
    const match = String(value).match(/rgba?\((\d+),\s*(\d+),\s*(\d+)(?:,\s*([\d.]+))?\)/);
    if (!match) return null;
    const alpha = match[4] === undefined ? 1 : parseFloat(match[4]);
    if (alpha < 0.5) return null;
    return [Number(match[1]), Number(match[2]), Number(match[3])];
  }

  function luminance(rgb) {
    const parts = rgb.map((channel) => {
      const value = channel / 255;
      return value <= 0.03928 ? value / 12.92 : Math.pow((value + 0.055) / 1.055, 2.4);
    });
    return 0.2126 * parts[0] + 0.7152 * parts[1] + 0.0722 * parts[2];
  }

  function contrast(a, b) {
    const left = luminance(a);
    const right = luminance(b);
    const lighter = Math.max(left, right);
    const darker = Math.min(left, right);
    return (lighter + 0.05) / (darker + 0.05);
  }

  function effectiveBg(el) {
    let node = el;
    while (node) {
      const parsed = parseRgb(getComputedStyle(node).backgroundColor);
      if (parsed) return parsed;
      node = node.parentElement;
    }
    return [255, 255, 255];
  }

  function clippedAway(el) {
    const rect = el.getBoundingClientRect();
    let node = el.parentElement;
    while (node) {
      const style = getComputedStyle(node);
      const overflow = `${style.overflow} ${style.overflowX} ${style.overflowY}`;
      if (overflow.includes("hidden") || overflow.includes("clip")) {
        const parent = node.getBoundingClientRect();
        const width = Math.min(rect.right, parent.right) - Math.max(rect.left, parent.left);
        const height = Math.min(rect.bottom, parent.bottom) - Math.max(rect.top, parent.top);
        if (width <= 0 || height <= 0) return true;
      }
      node = node.parentElement;
    }
    return false;
  }

  function hiddenReason(el) {
    const style = getComputedStyle(el);
    if (style.display === "none" || style.visibility === "hidden" || Number(style.opacity) === 0) {
      return "css-hidden";
    }
    if (el.getAttribute("aria-hidden") === "true") return "aria-hidden";
    if (parseFloat(style.fontSize) === 0) return "font-size-0";
    const rect = el.getBoundingClientRect();
    if (rect.width === 0 || rect.height === 0) return "empty-box";
    if (rect.right < 0 || rect.bottom < 0 || rect.left >= vw) return "offscreen";
    if (clippedAway(el)) return "clipped";
    const fg = parseRgb(style.color);
    if (fg) {
      const ratio = contrast(fg, effectiveBg(el));
      if (ratio < 1.15) return "low-contrast";
    }
    return "";
  }

  function clean(value) {
    return String(value || "").replace(/\s+/g, " ").trim();
  }

  function struck(el) {
    let node = el;
    while (node && node.nodeType === 1) {
      const tag = node.tagName;
      if (tag === "S" || tag === "DEL" || tag === "STRIKE") return true;
      if (node.classList && node.classList.contains("was")) return true;
      const style = getComputedStyle(node);
      const line = String(style.textDecorationLine || "") + " " + String(style.textDecoration || "");
      if (line.indexOf("line-through") !== -1) return true;
      node = node.parentElement;
    }
    return false;
  }

  function markWas(el, value) {
    const text = clean(value);
    if (!text) return "";
    if (struck(el) && !/^was\b/i.test(text)) return "was " + text;
    return text;
  }

  function selectorOf(el) {
    if (el.id) return "#" + el.id;
    const name = el.getAttribute("name");
    const tag = el.tagName.toLowerCase();
    if (name) return tag + "[name=\"" + name + "\"]";
    return tag;
  }

  const skipTags = new Set(["SCRIPT", "STYLE", "NOSCRIPT", "TEMPLATE"]);

  function hiddenBlocks(root) {
    const found = [];
    function walk(el) {
      if (skipTags.has(el.tagName)) return;
      const reason = hiddenReason(el);
      const text = clean(el.textContent);
      if (reason && text) {
        found.push({ reason, selector: selectorOf(el), text: text.slice(0, 1500) });
        return;
      }
      for (const child of el.children) walk(child);
    }
    walk(root);
    return found;
  }

  function visibleLines(root) {
    const lines = [];
    function walk(el) {
      if (skipTags.has(el.tagName)) return;
      if (hiddenReason(el)) return;
      let direct = "";
      for (const node of el.childNodes) {
        if (node.nodeType === Node.TEXT_NODE) direct += node.textContent;
      }
      if (el.id && el.children.length) {
        const full = markWas(el, el.textContent);
        if (full) lines.push(full);
        return;
      }
      direct = markWas(el, direct);
      if (direct) lines.push(direct);
      for (const child of el.children) walk(child);
    }
    walk(root);
    return lines;
  }

  function controlLabel(el) {
    if (el.id) {
      const label = document.querySelector('label[for="' + CSS.escape(el.id) + '"]');
      if (label) return clean(label.innerText || label.textContent);
    }
    const wrap = el.closest("label");
    if (wrap) return clean(wrap.innerText || wrap.textContent);
    return clean(el.getAttribute("aria-label") || el.getAttribute("value") || el.innerText || el.textContent || "");
  }

  const controls = [];
  for (const el of document.querySelectorAll("input, select, textarea, button")) {
    const type = (el.getAttribute("type") || el.tagName).toLowerCase();
    const entry = {
      kind: el.tagName.toLowerCase() === "input" ? type : el.tagName.toLowerCase(),
      id: el.id || "",
      name: el.getAttribute("name") || "",
      checked: null,
      label: controlLabel(el).slice(0, 240),
    };
    if (type === "checkbox" || type === "radio") entry.checked = Boolean(el.checked);
    controls.push(entry);
  }

  const prices = [];
  for (const el of document.querySelectorAll("[data-price]")) {
    prices.push({
      text: markWas(el, el.innerText || el.textContent),
      label: el.getAttribute("data-price-label") || "",
    });
  }
  const totalEl = document.querySelector("[data-total]");
  const modals = [];
  for (const el of document.querySelectorAll("dialog[open], [role=dialog], [aria-modal=true]")) {
    modals.push({
      id: el.id || "",
      text: clean(el.innerText || el.textContent).slice(0, 800),
    });
  }

  const comments = [];
  const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_COMMENT);
  let comment = walker.nextNode();
  while (comment) {
    const text = clean(comment.textContent);
    if (text) comments.push(text.slice(0, 500));
    comment = walker.nextNode();
  }

  return {
    url: location.href,
    domain: location.hostname,
    storefront_domain: document.body.getAttribute("data-store-domain") || "",
    title: document.title || "",
    kind: document.body.getAttribute("data-page-kind") || "",
    prices,
    total: totalEl ? clean(totalEl.innerText || totalEl.textContent) : "",
    controls,
    modals,
    visible: visibleLines(document.body),
    hidden: hiddenBlocks(document.body),
    comments,
  };
}
"""


def _control_line(control: dict) -> str:
    kind = control.get("kind") or "control"
    if control.get("checked") is True:
        state = " checked"
    elif control.get("checked") is False:
        state = " unchecked"
    else:
        state = ""
    return (
        f"{kind}{state} | id={control.get('id') or ''} | "
        f"name={control.get('name') or ''} | {control.get('label') or ''}"
    )


def _assemble(data: dict, visible: list[str], hidden: list[dict], truncated: bool) -> str:
    lines = [
        f"url: {data.get('url') or ''}",
        f"domain: {data.get('domain') or ''}",
        f"storefront_domain: {data.get('storefront_domain') or ''}",
        f"title: {data.get('title') or ''}",
        f"kind: {data.get('kind') or ''}",
        "",
        "prices:",
    ]
    prices = data.get("prices") or []
    if prices:
        for price in prices:
            label = price.get("label") or ""
            text = price.get("text") or ""
            lines.append(f"{text} | {label}" if label else text)
    else:
        lines.append("(blank)")
    if data.get("total"):
        lines.append(f"total: {data['total']}")
    lines.append("")
    lines.append("controls:")
    controls = data.get("controls") or []
    if controls:
        lines.extend(_control_line(control) for control in controls)
    else:
        lines.append("(blank)")
    lines.append("")
    lines.append("modals:")
    modals = data.get("modals") or []
    if modals:
        for modal in modals:
            lines.append(f"open | id={modal.get('id') or ''} | {modal.get('text') or ''}")
    else:
        lines.append("(blank)")
    lines.append("")
    lines.append("visible:")
    if visible:
        lines.extend(visible)
    else:
        lines.append("(blank)")
    if truncated:
        lines.append("[truncated]")
    lines.append("")
    lines.append("hidden_flagged:")
    if hidden or data.get("comments"):
        for item in hidden:
            lines.append(f"{item.get('reason') or 'hidden'} | {item.get('selector') or ''} | {item.get('text') or ''}")
        for comment in data.get("comments") or []:
            lines.append(f"comment | | {comment}")
    else:
        lines.append("(blank)")
    return "\n".join(lines) + "\n"


def format_extract(data: dict) -> str:
    """Turn extractor JSON into the guard's text view, capped near 2,000 tokens."""
    visible = [line for line in (data.get("visible") or []) if line]
    hidden = [dict(item) for item in (data.get("hidden") or [])]
    for item in hidden:
        text = item.get("text") or ""
        if len(text) > 1500:
            item["text"] = text[:1500]
    truncated = False
    while True:
        text = _assemble(data, visible, hidden, truncated)
        if len(text) <= MAX_CHARS:
            return text
        if visible:
            visible.pop()
            truncated = True
            continue
        if len(hidden) > 1:
            hidden.pop()
            truncated = True
            continue
        break
    clipped = text[: MAX_CHARS - 12].rstrip() + "\n[truncated]\n"
    return clipped


def extract_page(page) -> str:
    """Format whatever document is currently loaded in a Playwright page."""
    data = page.evaluate(EXTRACT_JS)
    return format_extract(data)


def read_page(url: str, *, viewport: tuple[int, int] = VIEWPORT, timeout_ms: int = 30000) -> str:
    """Read a live URL the same way batch pages are read.

    Later shopper runs can pass any http(s) URL. The viewport default matches
    the frozen-set measurement, 1280 by 800.
    """
    from playwright.sync_api import sync_playwright

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True, args=_launch_args())
        context = browser.new_context(
            viewport={"width": viewport[0], "height": viewport[1]},
            device_scale_factor=1,
            locale="en-US",
        )
        page = context.new_page()
        page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
        page.evaluate("() => document.fonts.ready.then(() => true)")
        text = extract_page(page)
        browser.close()
        return text


def _launch_args() -> list[str]:
    return [
        "--no-sandbox",
        "--disable-dev-shm-usage",
        "--font-render-hinting=none",
        "--disable-lcd-text",
        "--disable-gpu",
    ]
