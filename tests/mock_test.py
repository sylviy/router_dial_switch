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


def _cfg_for(url, apply_it, headless):
    """一份指向 mock 的 config —— 除了地址和账密,和现场那份是同一个结构。"""
    cfg = perf.load()
    cfg["router"] = dict(CREDS, ip=url)
    cfg.setdefault("run", {})
    cfg["run"]["apply"] = apply_it
    cfg["run"]["headless"] = headless
    return cfg


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
        cfg = _cfg_for("http://127.0.0.1:%d/%s" % (port, page_file), apply_it,
                       not show)
        res = mod.switch(mode, cfg, hook=_toast)
        ok = (res["success"] is want["success"]
              and res["read_back"] == want["read_back"]
              and want["filled"] <= set(res["filled"])
              and res["applied"] is want["applied"]
              and (res.get("verify") or "") == want["verify"])
        # 失败的用例必须给得出原因,不能只是静静地不成功
        if not want["success"]:
            ok = ok and bool(res["message"])
        print("[%s] %-28s 回读=%-12r 填了=%s 已保存=%s 页面回应=%r"
              % ("PASS" if ok else "FAIL", name, res["read_back"],
                 res["filled"], res["applied"], res.get("verify")))
        if not ok:
            print("      期望 %s" % want)
            print("      message: %s" % res["message"])
            print("      warnings: %s" % res["warnings"])
        passed += ok
        failed += not ok

    print("\n%d passed, %d failed" % (passed, failed))
    if failed:
        print("自检没过 —— 这是代码的问题,先别上台架。")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
