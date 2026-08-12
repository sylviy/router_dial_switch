"""离线自检:拿仓库自带的假路由器页面,把型号脚本从头到尾跑一遍。

**不碰真路由器、不碰仪表、不需要台架。** 上台架之前先跑这个:它证明
"登录 → 走菜单 → 选档 → 回读 → 填账密 → 保存"这条路是通的,以及成功判定
没有被放宽。跑不过就别上台架 —— 那是代码的问题,不是接线的问题。

    python tests/mock_test.py            # 无窗口
    python tests/mock_test.py --show     # 看着它点

每条用例的期望值(回读什么、填了哪几个框、有没有点保存、页面回了什么)
逐字抄自重构前的 tests/smoke_test.py —— 它们是**行为基准**,不是新写的。
"""
from __future__ import annotations

import os
import sys
import threading
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from common import perf

MOCK_DIR = os.path.join(ROOT, "tests", "mock_router")

# mock 页面认的账密。真机上这些来自 config.yaml,这里写死是为了让自检
# 不依赖现场填了什么。
CREDS = {
    "pass": "admin123",
    "pppoe_user": "acc", "pppoe_pass": "s3",
    "pptp": {"server": "10.0.0.9", "user": "u", "pass": "p"},
    "l2tp": {"server": "10.0.0.9", "user": "u", "pass": "p"},
}

# 某几条用例要用和默认不一样的账密(逐条抄自重构前的 smoke_test)
CRED_OVERRIDE = {
    "mercusys l2tp 填字段": {"l2tp": {"server": "10.0.0.1", "user": "u", "pass": "p"}},
    "tenda pppoev6(IPv6 页)": {"pppoe_user": "u6", "pppoe_pass": "p6"},
    "cudy-ax3000 pppoe(LuCI)": {"pppoe_user": "u", "pppoe_pass": "p"},
    "cudy-ax3000 l2tp(AJAX 挂的字段)": {"l2tp": {"server": "10.0.0.9",
                                                 "user": "vu", "pass": "vp"}},
    "buffalo pppoe 账密在别页": {"pppoe_user": "u", "pppoe_pass": "p"},
}

# (名字, 型号脚本, mock 页面, 模式, 下发?, 期望)
CASES = [
    ("cudy-ax1500 dynamic 不下发", "Cudy_AX1500", "cudy.html", "dynamic", False,
     dict(success=True, read_back="DHCP Client", filled=set(), applied=False,
          verify="")),
    ("cudy-ax1500 pppoe 跨 frame", "Cudy_AX1500", "cudy.html", "pppoe", True,
     dict(success=True, read_back="PPPoE",
          filled={"pppoe_user", "pppoe_pass"}, applied=True,
          verify="Saved & Applied: PPPoE")),
    ("cudy-ax1500 l2tp 填字段", "Cudy_AX1500", "cudy.html", "l2tp", True,
     dict(success=True, read_back="L2TP",
          filled={"vpn_server", "vpn_user", "vpn_pass"}, applied=True,
          verify="Saved & Applied: L2TP")),
    ("cudy-ax1500 pptp 另一套字段", "Cudy_AX1500", "cudy.html", "pptp", True,
     dict(success=True, read_back="PPTP",
          filled={"vpn_server", "vpn_user", "vpn_pass"}, applied=True,
          verify="Saved & Applied: PPTP")),
    ("cudy-ax1500 static 不下发", "Cudy_AX1500", "cudy.html", "static", False,
     dict(success=True, read_back="Static IP", filled=set(), applied=False,
          verify="")),
    # 事实对不上的页面必须**诚实失败**,而不是零交互的假成功:
    # 拿 Cudy 的 FACTS 去跑 Tenda 页,控件全对不上 -> success=False + 有原因。
    ("cudy-ax1500 错页守卫", "Cudy_AX1500", "tenda.html", "dynamic", False,
     dict(success=False, read_back="", filled=set(), applied=False,
          verify="")),

    # --- 第 2 种 UI:Vue 自定义下拉(Tenda / Mercusys)-----------------------
    ("tenda pppoe+Connect", "Tenda_AX3000", "tenda.html", "pppoe", True,
     dict(success=True, read_back="PPPoE",
          filled={"pppoe_user", "pppoe_pass"}, applied=True,
          verify="Connected: PPPoE")),
    # 触发器初始就是 Dynamic IP:走"已是目标"的可信短路;默认不点保存。
    ("tenda dynamic 已是目标", "Tenda_AX3000", "tenda.html", "dynamic", False,
     dict(success=True, read_back="Dynamic IP", filled=set(), applied=False,
          verify="")),
    # IPv6 独立页:换菜单路径 + 使能开关门控 + v6 flavor;
    # LAN 区那个同名 "DHCPv6" radio 诱饵绝不能被点到(点到 = 回读错)。
    ("tenda dhcpv6(门控页)", "Tenda_AX3000", "tenda_ipv6.html", "dhcpv6", True,
     dict(success=True, read_back="DHCPv6", filled=set(), applied=True,
          verify="Saved: DHCPv6")),
    ("tenda pppoev6(IPv6 页)", "Tenda_AX3000", "tenda_ipv6.html", "pppoev6",
     True, dict(success=True, read_back="PPPoEv6",
                filled={"pppoe_user", "pppoe_pass"}, applied=True,
                verify="Saved: PPPoEv6")),
    ("mercusys pppoe+Save", "Mercusys_BE3600", "custom.html", "pppoe", True,
     dict(success=True, read_back="PPPoE",
          filled={"pppoe_user", "pppoe_pass"}, applied=True,
          verify="Saved: PPPoE")),
    ("mercusys l2tp 填字段", "Mercusys_BE3600", "custom.html", "l2tp", True,
     dict(success=True, read_back="L2TP",
          filled={"vpn_server", "vpn_user", "vpn_pass"}, applied=True,
          verify="Saved: L2TP")),

    # --- 第 3 种 UI:LuCI / CBI(Cudy AX3000)--------------------------------
    # 守的是 LuCI 特有的三个坑:CBI 的 id 含点号(只能 [id='...'])、页面上
    # 4 个 name=cbi.apply 必须靠 form:has(拨号控件) 锚定(点错 form 的话
    # mock 的 toast 会喊 WRONG FORM)、选完 proto 后整段 DOM 被 XHR 重建。
    ("cudy-ax3000 pppoe(LuCI)", "Cudy_AX3000", "cudy_luci.html", "pppoe", True,
     dict(success=True, read_back="PPPoE",
          filled={"pppoe_user", "pppoe_pass"}, applied=True,
          verify="Saved & Applied: PPPoE")),
    ("cudy-ax3000 l2tp(AJAX 挂的字段)", "Cudy_AX3000", "cudy_luci.html", "l2tp",
     True, dict(success=True, read_back="L2TP",
                filled={"vpn_server", "vpn_user", "vpn_pass"}, applied=True,
                verify="Saved & Applied: L2TP")),

    # --- 第 4 种 UI:外壳页 + iframe(BUFFALO)-------------------------------
    # 这三条守的是这台机的三条真机事实:设置页必须以 iframe 打开且要等它的
    # 配置对象 CA 加载完;页面脚本会把 iframe 地址改回去一次(要重试);
    # radio 和保存键被皮盖住(要 force 点)。
    ("buffalo v6plus 不下发", "BUFFALO_WSR6000AX8", "buffalo_advanced.html",
     "v6plus", False,
     dict(success=True, read_back="v6plus", filled=set(), applied=False,
          verify="")),
    ("buffalo dynamic 真保存", "BUFFALO_WSR6000AX8", "buffalo_advanced.html",
     "dynamic", True,
     dict(success=True, read_back="dynamic", filled=set(), applied=True,
          verify="Saved & Applied: dynamic")),
    # 账密框在别页(pppoe_reg.html):必须逐条发警告,绝不静默装作填过了。
    ("buffalo pppoe 账密在别页", "BUFFALO_WSR6000AX8", "buffalo_advanced.html",
     "pppoe", False,
     dict(success=True, read_back="pppoe", filled=set(), applied=False,
          verify="", warnings=2, warn_has="pppoe_reg.html")),
    # 直接打开设置页(没有外壳 iframe)必须**诚实失败**。真机上这条路径最危险:
    # 页面照样渲染、radio 照样点、回读照样通过,保存提交的却是旧值。
    ("buffalo 没有外壳页时诚实失败", "BUFFALO_WSR6000AX8", "buffalo_wan.html",
     "dynamic", True,
     dict(success=False, read_back="", filled=set(), applied=False,
          verify="")),
]


def _serve():
    handler = partial(SimpleHTTPRequestHandler, directory=MOCK_DIR)
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd.server_address[1]


def _toast(page):
    """读 mock 页面上的 toast —— 它证明保存键**真的**按下去了,而且按的是
    对的那个(applied=True 只能说明点了个东西)。跨 frame 找:Cudy 的 toast
    在 WAN 子帧里。"""
    for fr in list(page.frames):
        try:
            loc = fr.locator("#toast")
            if loc.count() and loc.first.is_visible():
                return (loc.first.inner_text() or "").strip()
        except Exception:
            continue
    return ""


def _cfg_for(url, apply_it, headless, creds=None):
    """一份指向 mock 的 config —— 除了地址和账密,和现场那份是同一个结构。"""
    router = dict(CREDS)
    for key, value in (creds or {}).items():
        router[key] = dict(router.get(key), **value) if isinstance(value, dict) \
            else value
    cfg = perf.load()
    cfg["router"] = dict(router, ip=url)
    cfg.setdefault("run", {})
    cfg["run"]["apply"] = apply_it
    cfg["run"]["headless"] = headless
    return cfg


def _bridge_cases():
    """TPLink 那条路线:不开浏览器,下发和回读都在 py2 侧的桥接里。

    这里用 tests/mock_bridge.py 顶替真桥接 —— 它**只复现命令行契约**
    (stdout 一行 JSON;退出码 0/2/3),不模拟 RouterCtrl。被测的是 py3 这一
    侧:档名有没有翻译对、桥接说"不行"的时候会不会仍然报成功。
    """
    import os

    import models.TPLink_RouterCtrl as tp

    print("\n==== TPLink 桥接路线(假桥接,不碰真机)====")
    real_bridge, tp.BRIDGE = tp.BRIDGE, "tests/mock_bridge.py"
    cfg = perf.load()
    cfg["router"] = {"ip": "192.168.0.1", "pass": "pw",
                     "pppoe_user": "acc", "pppoe_pass": "s3",
                     "pptp": {"server": "1.2.3.4", "user": "u", "pass": "p"},
                     "l2tp": {"server": "1.2.3.4", "user": "u", "pass": "p"}}
    cfg["bench"]["python2"] = sys.executable
    cfg.setdefault("run", {})["apply"] = True

    cases = [
        # (名字, 场景, 模式, 期望 success, 期望回读)
        ("桥接 dynamic", "ok", "dynamic", True, "Dynamic IP"),
        ("桥接 pppoe", "ok", "pppoe", True, "PPPoE"),
        # 档名翻译:这一侧说 pptp,桥接收到的必须是它认得的复合名
        ("桥接 pptp(档名翻译)", "ok", "pptp", True, "PPTP"),
        ("桥接 l2tp(档名翻译)", "ok", "l2tp", True, "L2TP"),
        # **这一条是重点**:wan_type 回读完全正确,只有桥接知道 WAN 没拿到
        # 地址。少查桥接那道关就会出现"类型对了、其实没拨上"的绿格子。
        ("类型对了但没拨上 -> 必须判失败", "readback_fail", "pptp", False, "PPTP"),
        # 桥接没吐 JSON:不许猜"可能切成功了"
        ("桥接没吐 JSON -> 诚实失败", "usage", "l2tp", False, ""),
        # RouterCtrl 自己很吵,JSON 不一定是唯一的那行
        ("JSON 前面混日志行", "noisy", "dynamic", True, "Dynamic IP"),
    ]
    passed = failed = 0
    for name, scenario, mode, want_ok, want_read in cases:
        os.environ["MOCK_BRIDGE"] = scenario
        res = tp.switch(mode, cfg)
        ok = (res["success"] is want_ok and res["read_back"] == want_read
              and tp.BRIDGE_MODE[mode] in tp.BRIDGE_MODE.values())
        if not want_ok:
            ok = ok and bool(res["message"])
        print("[%s] %-32s success=%-6s 回读=%-11r 桥接收到=%s"
              % ("PASS" if ok else "FAIL", name, res["success"],
                 res["read_back"], tp.BRIDGE_MODE[mode]))
        if not ok:
            print("      期望 success=%s 回读=%r" % (want_ok, want_read))
            print("      message: %s" % res["message"])
        passed += ok
        failed += not ok

    # 不加 --apply 时这条路线什么都不做(它没有"只看不切")
    cfg["run"]["apply"] = False
    res = tp.switch("pppoe", cfg)
    ok = (not res["success"]) and not res["applied"] and bool(res["message"])
    print("[%s] %-32s success=%s" % ("PASS" if ok else "FAIL",
                                     "不加 --apply 时什么都不做", res["success"]))
    passed += ok
    failed += not ok

    os.environ.pop("MOCK_BRIDGE", None)
    tp.BRIDGE = real_bridge
    return passed, failed


def main(argv=None):
    import importlib
    show = "--show" in (argv if argv is not None else sys.argv[1:])
    for stream in (sys.stdout, sys.stderr):        # 台架控制台是 GBK
        try:
            stream.reconfigure(errors="replace")
        except Exception:
            pass

    port = _serve()
    passed = failed = 0
    print("==== 离线自检(假路由器,不碰真机)====")
    for name, model, page_file, mode, apply_it, want in CASES:
        mod = importlib.import_module("models.%s" % model)
        if model == "BUFFALO_WSR6000AX8":
            # mock 里那一页叫 buffalo_wan.html,真机上叫 wan.html。**只改这
            # 一处**,别的事实原样用。
            mod.FACTS["iframe_target"] = "buffalo_wan.html"
        cfg = _cfg_for("http://127.0.0.1:%d/%s" % (port, page_file), apply_it,
                       not show, CRED_OVERRIDE.get(name))
        res = mod.switch(mode, cfg, hook=_toast)
        ok = (res["success"] is want["success"]
              and res["read_back"] == want["read_back"]
              and want["filled"] <= set(res["filled"])
              and res["applied"] is want["applied"]
              and (res.get("verify") or "") == want["verify"])
        # 失败的用例必须给得出原因,不能只是静静地不成功
        if not want["success"]:
            ok = ok and bool(res["message"])
        # 该发几条警告就发几条(少一条 = 少报了一个问题)
        if want.get("warnings") is not None:
            ok = ok and len(res["warnings"]) == want["warnings"] and all(
                want["warn_has"] in w for w in res["warnings"])
        print("[%s] %-28s 回读=%-12r 填了=%s 已保存=%s 页面回应=%r"
              % ("PASS" if ok else "FAIL", name, res["read_back"],
                 res["filled"], res["applied"], res.get("verify")))
        if not ok:
            print("      期望 %s" % want)
            print("      message: %s" % res["message"])
            print("      warnings: %s" % res["warnings"])
        passed += ok
        failed += not ok

    # --- TPLink 那条桥接路线(不开浏览器,用假桥接)-------------------------
    p, f = _bridge_cases()
    passed += p
    failed += f

    print("\n%d passed, %d failed" % (passed, failed))
    if failed:
        print("自检没过 —— 这是代码的问题,先别上台架。")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
