"""One Chromium session for measuring a batch of rendered pages."""

from __future__ import annotations

from playwright.sync_api import sync_playwright

from gym.reader import EXTRACT_JS, _launch_args, format_extract
from gym.taxonomy import VIEWPORT


class Browser:
    def __init__(self, viewport: tuple[int, int] = VIEWPORT) -> None:
        self.viewport = viewport
        self._playwright = None
        self._browser = None
        self._context = None
        self._page = None

    def __enter__(self) -> "Browser":
        self._playwright = sync_playwright().start()
        self._browser = self._playwright.chromium.launch(headless=True, args=_launch_args())
        self._context = self._browser.new_context(
            viewport={"width": self.viewport[0], "height": self.viewport[1]},
            device_scale_factor=1,
            locale="en-US",
        )
        self._page = self._context.new_page()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        if self._browser is not None:
            self._browser.close()
        if self._playwright is not None:
            self._playwright.stop()

    def open_html(self, html: str, url: str) -> None:
        page = self._page
        assert page is not None
        page.unroute_all(behavior="ignoreErrors")
        target = url

        def handle(route) -> None:
            if route.request.url.split("#", 1)[0] == target:
                route.fulfill(
                    status=200,
                    content_type="text/html; charset=utf-8",
                    body=html,
                )
            else:
                route.abort()

        page.route("**/*", handle)
        page.goto(target, wait_until="domcontentloaded", timeout=20000)
        page.evaluate("() => document.fonts.ready.then(() => true)")

    def font_family(self) -> str:
        assert self._page is not None
        return self._page.evaluate("() => getComputedStyle(document.body).fontFamily")

    def text_content(self, selector: str) -> str | None:
        assert self._page is not None
        return self._page.locator(selector).text_content()

    def bbox(self, selector: str) -> list[int] | None:
        assert self._page is not None
        locator = self._page.locator(selector)
        if locator.count() == 0:
            return None
        box = locator.bounding_box()
        if box is None:
            box = locator.evaluate(
                """(el) => {
                    const rect = el.getBoundingClientRect();
                    return {x: rect.x, y: rect.y, width: rect.width, height: rect.height};
                }"""
            )
        if not box or box.get("width") is None:
            return None
        return [
            int(round(box["x"])),
            int(round(box["y"])),
            int(round(box["width"])),
            int(round(box["height"])),
        ]

    def compact_text(self) -> str:
        assert self._page is not None
        return format_extract(self._page.evaluate(EXTRACT_JS))
