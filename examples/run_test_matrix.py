"""编排示例:按 拨号方式 循环 —— 切模式(本工具) → 等WAN → 跑性能(你们的脚本)。

这就是"整套自动化"的主循环。本工具只负责"切拨号方式"这一步;真正的性能/WLAN
测试用你们已有的单机脚本,替换下面 run_perf_tests() 里的占位命令即可。

运行(在隔离的 3.8 + 已装依赖环境下):
    python examples/run_test_matrix.py
"""
from __future__ import annotations

import os
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from config import Config
from engine.browser import Browser
from engine.adapter import RouterAdapter
from engine import profile as profile_mod

# ---------------------------------------------------------------------------
# 1) 被测路由器 + 登录信息(每台陌生路由器改这里)
# ---------------------------------------------------------------------------
ROUTER_URL = "http://192.168.1.1"
ADMIN_USER = ""            # 若只需密码就留空
ADMIN_PASS = "admin123"
BRAND, MODEL = "", ""      # 有 profile 时填,用于匹配;没有就留空走纯启发式

# ---------------------------------------------------------------------------
# 2) 测试矩阵:拨号方式 + 各自参数(账密/服务器)——按你的例子填好了
# ---------------------------------------------------------------------------
VPN_SERVER = "192.168.202.254"
DIAL_MATRIX = [
    ("dynamic", {}),
    ("pppoe", {"pppoe_user": "pppoe", "pppoe_pass": "pppoe"}),
    ("l2tp",  {"vpn_server": VPN_SERVER, "vpn_user": "l2tp", "vpn_pass": "l2tp"}),
    ("pptp",  {"vpn_server": VPN_SERVER, "vpn_user": "pptp", "vpn_pass": "pptp"}),
    # IPv6 通常在另一个页面(如 Mercusys 的 Advanced→IPv6),等确认后再加进来
]


# ---------------------------------------------------------------------------
# 3) 切拨号方式(本工具):返回是否切换成功
# ---------------------------------------------------------------------------
def switch_dial_mode(mode: str, params: dict) -> dict:
    cfg = Config()
    cfg.channel = "chrome"          # 复用系统 Chrome(离线);测试台 Windows 用 114
    prof = profile_mod.match(BRAND, MODEL)
    with Browser(cfg) as br:
        br.goto(ROUTER_URL)
        adapter = RouterAdapter(br.page, config=cfg, profile=prof)
        res = adapter.run(mode, params,
                          admin_user=ADMIN_USER, admin_pass=ADMIN_PASS)
    return res.as_dict()


# ---------------------------------------------------------------------------
# 4) 等 WAN 拨通(占位)—— 本地无拨号台架时可跳过;有台架时接你们的判据
# ---------------------------------------------------------------------------
def wait_wan_up(mode: str, timeout_s: int = 60) -> bool:
    # TODO: 换成真实判据,例如 ping WAN 网关 / 调用单机脚本的 "WAN up?" 检查。
    # 现在只做固定等待,保证界面 apply 后拨号有时间建立。
    time.sleep(8)
    return True


# ---------------------------------------------------------------------------
# 5) 跑性能/WLAN 测试(占位)—— 换成你们的单机脚本命令
# ---------------------------------------------------------------------------
def run_perf_tests(mode: str) -> dict:
    # 例:调用你们已有的单机脚本(可传入当前拨号方式做记录/命名)
    #   cmd = ["python", r"C:\perf\ipv4_and_wlan.py", "--label", mode]
    #   out = subprocess.run(cmd, capture_output=True, text=True, timeout=1800)
    #   return {"ok": out.returncode == 0, "log": out.stdout}
    print("    [perf] 这里跑你们的单机脚本:IPv4 性能 + 2.4G/5G WLAN↔LAN 上下行 ...")
    return {"ok": True, "log": "(placeholder)"}


# ---------------------------------------------------------------------------
# 主循环:切模式 → 等WAN → 测试 → 收集
# ---------------------------------------------------------------------------
def main():
    results = []
    for mode, params in DIAL_MATRIX:
        print("\n=== 切到 %s ===" % mode)
        sw = switch_dial_mode(mode, params)
        print("    切换: success=%s via=%s read_back=%r needs_recording=%s"
              % (sw["success"], sw["detected_via"], sw["read_back"],
                 sw["needs_recording"]))
        if not sw["success"]:
            print("    ✗ 切换失败,跳过该模式测试。message=%s" % sw["message"])
            results.append({"mode": mode, "switched": False, "perf": None})
            continue
        wait_wan_up(mode)
        perf = run_perf_tests(mode)
        results.append({"mode": mode, "switched": True, "perf": perf})

    print("\n===== 汇总 =====")
    for r in results:
        print("  %-8s 切换=%s 测试=%s"
              % (r["mode"], "OK" if r["switched"] else "FAIL",
                 (r["perf"] or {}).get("ok") if r["switched"] else "-"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
