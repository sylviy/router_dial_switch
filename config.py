"""Runtime configuration for the router dial-switch tool.

All OS / environment specific knobs live here so the same engine code runs
unchanged on macOS (development / logic verification) and Windows (the real
offline test bench).  See README.md for the offline packaging story.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Config:
    # --- browser ------------------------------------------------------------
    # Prefer driving the already-installed, version-locked Chrome (offline,
    # no extra download).  Set to None to use Playwright's bundled chromium.
    channel: Optional[str] = "chrome"
    headless: bool = False
    # Optional explicit path to a Chrome/Chromium binary (overrides `channel`).
    executable_path: Optional[str] = None
    # Folder holding a pre-staged Playwright browser bundle for fully-offline
    # installs.  When set, exported as PLAYWRIGHT_BROWSERS_PATH before launch.
    browsers_path: Optional[str] = None
    # HTTP Basic 认证(老机型常见:登录是浏览器原生弹窗,**DOM 里根本没有
    # 密码框**,所以任何选择器都救不了)。填了就交给 Playwright 应答 401 挑战;
    # 服务器不要求认证时它不会发出去,填了也无害。
    http_user: Optional[str] = None
    http_pass: Optional[str] = None

    # --- timing (milliseconds) ---------------------------------------------
    default_timeout_ms: int = 15000     # per-action auto-wait ceiling
    nav_timeout_ms: int = 30000         # page.goto ceiling
    settle_ms: int = 1200               # small pause after "apply" before read-back

    # --- artefacts ----------------------------------------------------------
    screenshot_dir: str = "artifacts"

    def __post_init__(self) -> None:
        # 环境变量兜底:台架/CI 上 Chrome 不在标准位置时,不必改代码。
        # ROUTER_BROWSER_PATH 指向 chrome/chromium 可执行文件,优先于 channel。
        self.executable_path = self.executable_path or os.environ.get(
            "ROUTER_BROWSER_PATH") or None
        self.browsers_path = self.browsers_path or os.environ.get(
            "ROUTER_BROWSERS_DIR") or None

    def apply_env(self) -> None:
        """Export env vars Playwright reads at launch time."""
        if self.browsers_path:
            os.environ["PLAYWRIGHT_BROWSERS_PATH"] = self.browsers_path


DEFAULT = Config()
