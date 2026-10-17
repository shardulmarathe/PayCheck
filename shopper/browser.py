"""Headless Chrome for one errand.

Playwright launches the browser so an optional video can be recorded. Browser
Use attaches to that same Chrome over the DevTools port and drives the page.
``use_cloud`` stays off: this is the open-source library and a local browser.
"""

from __future__ import annotations

import asyncio
import os
import shutil
import socket
import tempfile
import time
from pathlib import Path

from shopper.gate import PurchaseGate, classify_purchase
from shopper.policy import Action

VIEWPORT = {"width": 1280, "height": 800}

_CHROME_CANDIDATES = (
    os.environ.get("SHOPPER_CHROME") or "",
    "/usr/local/bin/google-chrome",
    "/usr/bin/google-chrome",
    "/usr/bin/chromium",
    "/usr/bin/chromium-browser",
)


def quiet_library_logs() -> None:
    """Browser Use configures its own handler at INFO. Keep the shopper transcript readable."""
    import logging

    for name in ("browser_use", "bubus", "cdp_use"):
        logging.getLogger(name).setLevel(logging.WARNING)


def chrome_executable() -> str:
    for candidate in _CHROME_CANDIDATES:
        if candidate and Path(candidate).is_file():
            return candidate
    found = shutil.which("google-chrome") or shutil.which("chromium") or shutil.which("chromium-browser")
    if found:
        return found
    raise RuntimeError("google-chrome was not found; set SHOPPER_CHROME to the executable")


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


class ShopChrome:
    """One persistent Chrome. Use as an async context manager."""

    def __init__(self, *, record_video: bool = False) -> None:
        self.record_video = record_video
        self.session = None
        self.saved_video: Path | None = None
        self._user_dir: str | None = None
        self._video_dir: str | None = None
        self._playwright = None
        self._context = None
        self._pw_page = None
        self._port = 0
        self.gate: PurchaseGate | None = None

    async def __aenter__(self) -> "ShopChrome":
        try:
            await self._launch()
        except Exception:
            await self._shutdown()
            raise
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        video_path = None
        if self._pw_page is not None and getattr(self._pw_page, "video", None):
            try:
                video_path = await self._pw_page.video.path()
            except Exception:
                video_path = None
        await self._shutdown()
        path = Path(video_path) if video_path else None
        if path is None or not path.is_file():
            if self._video_dir:
                webms = sorted(Path(self._video_dir).glob("*.webm"))
                path = webms[0] if webms else None
        self.saved_video = path if path and path.is_file() else None

    async def _launch(self) -> None:
        from playwright.async_api import async_playwright

        from browser_use import BrowserSession

        quiet_library_logs()
        self._user_dir = tempfile.mkdtemp(prefix="shopper-chrome-")
        if self.record_video:
            self._video_dir = tempfile.mkdtemp(prefix="shopper-video-")
        self._port = _free_port()
        self._playwright = await async_playwright().start()
        kwargs = {
            "user_data_dir": self._user_dir,
            "executable_path": chrome_executable(),
            "headless": True,
            "viewport": VIEWPORT,
            "device_scale_factor": 1,
            "locale": "en-US",
            "args": [
                f"--remote-debugging-port={self._port}",
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--disable-gpu",
            ],
        }
        if self._video_dir:
            kwargs["record_video_dir"] = self._video_dir
            kwargs["record_video_size"] = VIEWPORT
        self._context = await self._playwright.chromium.launch_persistent_context(**kwargs)
        self._pw_page = self._context.pages[0] if self._context.pages else await self._context.new_page()
        self.session = BrowserSession(
            cdp_url=f"http://127.0.0.1:{self._port}",
            headless=True,
            use_cloud=False,
            keep_alive=True,
            enable_default_extensions=False,
            viewport=VIEWPORT,
            highlight_elements=False,
            dom_highlight_elements=False,
        )
        await asyncio.wait_for(self.session.start(), timeout=30)

    async def _shutdown(self) -> None:
        if self.session is not None:
            try:
                await asyncio.wait_for(self.session.stop(), timeout=8)
            except Exception:
                pass
            self.session = None
        if self._context is not None:
            try:
                await asyncio.wait_for(self._context.close(), timeout=15)
            except Exception:
                pass
            self._context = None
        if self._playwright is not None:
            try:
                await asyncio.wait_for(self._playwright.stop(), timeout=10)
            except Exception:
                pass
            self._playwright = None
        if self._user_dir:
            shutil.rmtree(self._user_dir, ignore_errors=True)
            self._user_dir = None

    def consume_video(self, dest: Path | None) -> Path | None:
        """Move the Playwright video to ``dest`` and drop the temp directory."""
        saved = self.saved_video
        self.saved_video = None
        moved = None
        try:
            if dest is not None and saved and saved.is_file() and saved.stat().st_size > 0:
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(saved), dest)
                moved = dest
        finally:
            if self._video_dir:
                shutil.rmtree(self._video_dir, ignore_errors=True)
                self._video_dir = None
        return moved

    async def install_gate(self, gate: PurchaseGate) -> None:
        """Refuse gym purchase requests unless ``gate`` already approved that step."""
        if self._context is None:
            raise RuntimeError("browser is not started")
        self.gate = gate
        await self._context.route("**/*", self._on_route)

    async def _on_route(self, route) -> None:
        gate = self.gate
        try:
            if gate is None or not gate.armed:
                await route.continue_()
                return
            kind = classify_purchase(route.request.url, route.request.method)
            if kind is None or gate.consume(kind):
                await route.continue_()
                return
            gate.note_refusal(route.request.url, kind)
            await route.abort()
        except Exception:
            if gate is not None and gate.armed:
                try:
                    await route.abort()
                except Exception:
                    pass
            else:
                try:
                    await route.continue_()
                except Exception:
                    pass

    async def page(self):
        if self.session is None:
            raise RuntimeError("browser is not started")
        return await self.session.must_get_current_page()

    async def goto(self, url: str) -> None:
        page = await self.page()
        await page.goto(url)
        await self.wait_ready()

    async def wait_ready(self, timeout: float = 4.0) -> None:
        """Wait until the document is complete and has stopped changing."""
        page = await self.page()
        deadline = time.monotonic() + timeout
        last = None
        stable = 0
        while time.monotonic() < deadline:
            try:
                state = await page.evaluate(
                    "() => (document.readyState || '') + '|' + location.href + '|' + "
                    "(document.body ? document.body.innerText.length : 0)"
                )
            except Exception:
                state = ""
            if state and state == last and str(state).startswith("complete|") and "about:blank" not in str(state):
                stable += 1
                if stable >= 2:
                    return
            else:
                stable = 0
            last = state
            await asyncio.sleep(0.15)

    async def _element(self, selector: str):
        page = await self.page()
        elements = await page.get_elements_by_css_selector(selector)
        if not elements:
            await asyncio.sleep(0.2)
            elements = await page.get_elements_by_css_selector(selector)
        if not elements:
            raise RuntimeError(f"no element matches {selector}")
        return elements[0]

    async def click(self, selector: str) -> None:
        element = await self._element(selector)
        try:
            await element.click()
        except Exception:
            page = await self.page()
            await page.evaluate(
                """(selector) => {
                  const el = document.querySelector(selector);
                  if (!el) throw new Error('missing ' + selector);
                  el.click();
                }""",
                selector,
            )
        await self.wait_ready()

    async def check(self, selector: str) -> None:
        element = await self._element(selector)
        await element.check()
        await self.wait_ready()

    async def fill(self, selector: str, value: str) -> None:
        element = await self._element(selector)
        await element.fill(value, clear=True)

    async def perform(self, action: Action) -> None:
        if action.kind == "check":
            await self.check(action.selector)
            return
        if action.kind == "fill":
            await self.fill(action.selector, action.value)
            return
        if action.kind in {"click", "uncheck", "pay"}:
            await self.click(action.selector)
            return
        raise RuntimeError(f"cannot perform {action.kind}")

    async def fetch_result(self, errand_id: str) -> dict:
        import json

        page = await self.page()
        raw = await page.evaluate(
            """(path) => fetch(path, {credentials: 'same-origin'}).then((response) => {
              if (!response.ok) throw new Error('result ' + response.status);
              return response.text();
            })""",
            f"/e/{errand_id}/result",
        )
        return json.loads(raw)
