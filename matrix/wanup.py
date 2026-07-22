"""切完拨号方式后,等 WAN 真正拨通再开测。

旧 Dial.py 只是 time.sleep(15~30) 硬等。这里给一个更靠谱的判据:
method=ping 就 ping 台架的公网/内网地址直到通(或超时),再多等 settle_s 秒
让链路稳定;method=wait(或没配 host)就退回固定等待。

这也是将来接"真·WAN 拨通"验证的位置(旧方案里预留的 verify_hook)。
"""
from __future__ import annotations

import platform
import subprocess
import time


def _ping_once(host: str, timeout_s: int = 2) -> bool:
    win = platform.system().lower().startswith("win")
    count = "-n" if win else "-c"
    # Windows 用毫秒(-w),*nix 用秒(-W)
    wait = ["-w", str(timeout_s * 1000)] if win else ["-W", str(timeout_s)]
    cmd = ["ping", count, "1"] + wait + [host]
    try:
        return subprocess.run(cmd, capture_output=True,
                              timeout=timeout_s + 2).returncode == 0
    except Exception:
        return False


def wait_wan_up(cfg, log=print) -> bool:
    """cfg 为 config.WanUpCfg。返回是否判定为已拨通。"""
    if cfg.method == "ping" and cfg.host:
        deadline = time.time() + max(cfg.timeout_s, 1)
        while time.time() < deadline:
            if _ping_once(cfg.host):
                log("    WAN 已拨通(ping %s 通),稳定 %ds..." % (cfg.host,
                                                                cfg.settle_s))
                time.sleep(cfg.settle_s)
                return True
            time.sleep(2)
        log("    ⚠ 等 WAN 拨通超时(%ds ping 不通 %s),仍继续测量。"
            % (cfg.timeout_s, cfg.host))
        time.sleep(cfg.settle_s)
        return False
    # 没有 ping 判据:固定等待
    log("    等待 WAN 建链 %ds(未配 ping 判据)..." % cfg.settle_s)
    time.sleep(cfg.settle_s)
    return True
