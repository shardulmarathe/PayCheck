"""Interactive controls on the live page, for the mock shopper and for bboxes."""

from __future__ import annotations

from dataclasses import dataclass

# Returns a JSON list. Playwright evaluates the function in the page.
CONTROLS_JS = r"""
() => {
  function selectorOf(el) {
    if (el.id) return "#" + CSS.escape(el.id);
    const parts = [];
    let node = el;
    while (node && node.nodeType === 1 && node !== document.body) {
      const tag = node.tagName.toLowerCase();
      const parent = node.parentElement;
      if (!parent) break;
      const same = [...parent.children].filter((child) => child.tagName === node.tagName);
      const index = same.indexOf(node) + 1;
      parts.unshift(same.length > 1 ? tag + ":nth-of-type(" + index + ")" : tag);
      node = parent;
    }
    return parts.join(" > ");
  }

  const nodes = [...document.querySelectorAll("a, button, input, textarea, select")];
  return nodes.map((el) => {
    const rect = el.getBoundingClientRect();
    const type = (el.getAttribute("type") || "").toLowerCase();
    const style = getComputedStyle(el);
    const hidden = type === "hidden" || style.visibility === "hidden" || style.display === "none";
    const dialog = el.closest("[role=dialog], dialog[open], [aria-modal=true]");
    let text = (el.innerText || el.getAttribute("aria-label") || el.getAttribute("value") || "").replace(/\s+/g, " ").trim();
    if (!text && el.id) {
      const label = document.querySelector('label[for="' + CSS.escape(el.id) + '"]');
      if (label) text = (label.innerText || "").replace(/\s+/g, " ").trim();
    }
    return {
      tag: el.tagName.toLowerCase(),
      type: type,
      id: el.id || "",
      name: el.getAttribute("name") || "",
      text: text.slice(0, 240),
      href: el.getAttribute("href") || "",
      classes: typeof el.className === "string" ? el.className : "",
      checked: (type === "checkbox" || type === "radio") ? Boolean(el.checked) : null,
      value: (el.value || "").slice(0, 80),
      in_dialog: Boolean(dialog),
      primary: typeof el.className === "string" && el.className.split(/\s+/).includes("primary"),
      selector: selectorOf(el),
      x: rect.x,
      y: rect.y,
      w: rect.width,
      h: rect.height,
      hidden: hidden,
    };
  }).filter((entry) => !entry.hidden && entry.w > 0 && entry.h > 0);
}
"""


@dataclass
class Control:
    tag: str
    type: str
    id: str
    name: str
    text: str
    href: str
    classes: str
    checked: bool | None
    value: str
    in_dialog: bool
    primary: bool
    selector: str
    bbox: list[int]

    @property
    def label(self) -> str:
        return " ".join(self.text.split())


def _bbox(raw: dict) -> list[int]:
    return [round(float(raw.get("x") or 0)), round(float(raw.get("y") or 0)), round(float(raw.get("w") or 0)), round(float(raw.get("h") or 0))]


def parse_controls(raw: list[dict]) -> list[Control]:
    controls = []
    for item in raw:
        checked = item.get("checked")
        controls.append(
            Control(
                tag=item.get("tag") or "",
                type=item.get("type") or "",
                id=item.get("id") or "",
                name=item.get("name") or "",
                text=item.get("text") or "",
                href=item.get("href") or "",
                classes=item.get("classes") or "",
                checked=None if checked is None else bool(checked),
                value=item.get("value") or "",
                in_dialog=bool(item.get("in_dialog")),
                primary=bool(item.get("primary")),
                selector=item.get("selector") or "",
                bbox=_bbox(item),
            )
        )
    return controls


GEOMETRY_JS = r"""
(evidence) => {
  const viewport = {width: window.innerWidth, height: window.innerHeight};
  function boxOf(el) {
    if (!el) return null;
    const rect = el.getBoundingClientRect();
    if (rect.width <= 0 || rect.height <= 0) return null;
    return [Math.round(rect.x), Math.round(rect.y), Math.round(rect.width), Math.round(rect.height)];
  }
  if (!evidence) return {viewport: viewport, evidence_bbox: null};
  const nodes = document.body ? document.body.querySelectorAll("*") : [];
  let best = null;
  let bestArea = Infinity;
  for (const node of nodes) {
    const text = (node.innerText || node.textContent || "").replace(/\s+/g, " ").trim();
    if (!text || text.indexOf(evidence) === -1) continue;
    const box = boxOf(node);
    if (!box) continue;
    const area = box[2] * box[3];
    if (area < bestArea) {
      best = box;
      bestArea = area;
    }
  }
  return {viewport: viewport, evidence_bbox: best};
}
"""


async def read_geometry(page, evidence: str = "") -> tuple[dict, list[int] | None]:
    """Viewport size and the on-page box of the guard's evidence string."""
    import json

    fallback = {"width": 1280, "height": 800}
    try:
        raw = await page.evaluate(GEOMETRY_JS, evidence or "")
    except Exception:
        return fallback, None
    if isinstance(raw, str):
        raw = json.loads(raw) if raw else {}
    if not isinstance(raw, dict):
        return fallback, None
    viewport = raw.get("viewport") or {}
    width = int(viewport.get("width") or 1280)
    height = int(viewport.get("height") or 800)
    box = raw.get("evidence_bbox")
    if isinstance(box, list) and len(box) == 4:
        return {"width": width, "height": height}, [int(value) for value in box]
    return {"width": width, "height": height}, None


async def read_controls(page) -> list[Control]:
    raw = await page.evaluate(CONTROLS_JS)
    if isinstance(raw, str):
        import json

        raw = json.loads(raw)
    return parse_controls(list(raw or []))
