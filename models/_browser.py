"""Thin Playwright wrapper.

Isolates every OS / offline concern (which Chrome, bundled browsers, timeouts)
so the rest of the engine only ever sees a ready-to-drive `page`.
"""
from __future__ import annotations

from typing import Optional

from playwright.sync_api import sync_playwright

from config import Config, DEFAULT


class Browser:
    """Context manager yielding a Playwright `page`.

    Launch strategy (all offline-friendly):
      1. explicit `executable_path` if given, else
      2. `channel="chrome"` -> drive the already-installed, version-locked Chrome
      3. plain bundled chromium (needs a pre-staged browser bundle offline)
    """

    def __init__(self, config: Optional[Config] = None):
        self.cfg = config or DEFAULT
        self._pw = None
        self._browser = None
        self._context = None
        self.page = None

    def __enter__(self):
        self.cfg.apply_env()
        self._pw = sync_playwright().start()
        self._browser = self._launch()
        self._context = self._browser.new_context(ignore_https_errors=True)
        self._context.set_default_timeout(self.cfg.default_timeout_ms)
        self._context.set_default_navigation_timeout(self.cfg.nav_timeout_ms)
        self.page = self._context.new_page()
        return self

    def _launch(self):
        chromium = self._pw.chromium
        launch_kwargs = {"headless": self.cfg.headless}
        # 1) explicit binary
        if self.cfg.executable_path:
            return chromium.launch(executable_path=self.cfg.executable_path,
                                   **launch_kwargs)
        # 2) system Chrome by channel
        if self.cfg.channel:
            try:
                return chromium.launch(channel=self.cfg.channel, **launch_kwargs)
            except Exception as exc:  # fall through to bundled chromium
                print("[browser] channel=%s launch failed (%s); "
                      "falling back to bundled chromium" % (self.cfg.channel, exc))
        # 3) bundled chromium
        return chromium.launch(**launch_kwargs)

    def goto(self, url: str):
        self.page.goto(url, wait_until="domcontentloaded")
        return self.page

    def __exit__(self, exc_type, exc, tb):
        for closer in (self._context, self._browser):
            try:
                if closer:
                    closer.close()
            except Exception:
                pass
        try:
            if self._pw:
                self._pw.stop()
        except Exception:
            pass
        return False
