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
        self.last_response = None

    def __enter__(self):
        self.cfg.apply_env()
        self._pw = sync_playwright().start()
        self._browser = self._launch()
        ctx_kwargs = {"ignore_https_errors": True}
        if self.cfg.http_pass:
            # 老机型的登录可能是 HTTP Basic(浏览器原生弹窗,DOM 里没有密码框)。
            # 带上凭据后 Playwright 会自动应答 401;不是 Basic 的机器不受影响。
            ctx_kwargs["http_credentials"] = {
                "username": self.cfg.http_user or "admin",
                "password": self.cfg.http_pass}
        self._context = self._browser.new_context(**ctx_kwargs)
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
        # 记住首个响应:HTTP 401 是"这台机用 Basic 认证"的铁证,而那种页面
        # DOM 里不会有任何密码框 —— 不记下来的话排查时只会看到"没有密码框"。
        self.last_response = self.page.goto(url, wait_until="domcontentloaded")
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
