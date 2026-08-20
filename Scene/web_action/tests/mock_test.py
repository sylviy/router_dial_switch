"""UI 动作场景的离线自检 —— 拿假设备页跑 `Tools/act.py`,不碰真机。

    python Scene/web_action/tests/mock_test.py
    python Scene/web_action/tests/mock_test.py --show      # 看着它点

每条用例都是**一次独立的 act.py**,浏览器每次都是新的(localStorage 是空的),
所以每条从同一个初始状态出发,互不影响。

它证明的是**工具本身**能干活,不是某台设备适配对了:

  * 七种控件形态里,拨号场景用不到的那四种(checkbox / toggle / text /
    button)在真的浏览器里真的点得动、读得回;
  * `--expect-after` 能卡住"这一步还没成立"(不等到就判失败);
  * `--reload-verify` 能**抓出假成功** —— 不点 Save 就刷新,回读必须变回旧值。
    最后这一条是整个场景的地基:没有它,"回读通过"证明不了任何事。

退出码:0 = 全过 / 1 = 有不过的
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import threading


# 仓库根靠**向上找标志物**定位,不数目录层级。
def _up_to(marker):
    d = os.path.dirname(os.path.abspath(__file__))
    while not os.path.isdir(os.path.join(d, marker)):
        parent = os.path.dirname(d)
        if parent == d:
            raise SystemExit("往上找不到 %s/ —— 这个文件被搬出仓库了?" % marker)
        d = parent
    return d


ROOT = _up_to("Vendor")
HERE = os.path.dirname(os.path.abspath(__file__))
# 场景根 = tests/ 的上一层。act.py 一律在这里跑 —— 它靠"在哪个目录跑"
# 决定产物往哪放,不这么钉住的话,截图会跟着谁调用它而到处乱落。
SCENE = os.path.dirname(HERE)
ACT = os.path.join(ROOT, "Tools", "act.py")
MOCK_DIR = os.path.join(HERE, "mock_router")

PW = "admin123"
LOGIN_BTN = "#loginBtn"
MENU = "sel:#m_adv,sel:#vpn_server"
SAVE = "#save"
IPSEC_VALUE = "[id='cbid.vpn.config.ipsec']"


def _serve():
    """本地起个静态服务器伺候假页面。端口交给系统挑,免得撞车。"""
    import functools
    import http.server

    class Quiet(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *_a):      # 每个请求打一行会把结果淹掉
            pass

    handler = functools.partial(Quiet, directory=MOCK_DIR)
    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd.server_port


def run_act(port, *extra, **kw):
    """跑一次 act.py,返回 (退出码, 解析出来的 JSON)。"""
    cmd = [sys.executable, ACT,
           "--ip", "127.0.0.1:%d/vpn_server.html?%s" % (port, kw.get("bust", "")),
           "--pass", PW, "--login-btn", LOGIN_BTN, "--menu", MENU, "--json"]
    cmd += list(extra)
    if kw.get("show"):
        cmd.append("--show")
    proc = subprocess.run(cmd, cwd=SCENE,
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    out = proc.stdout.decode("utf-8", "replace")
    try:
        data = json.loads(out[out.index("{"):])
    except Exception:
        data = {"read_back": "", "match": False,
                "message": out.strip() + proc.stderr.decode("utf-8", "replace")}
    return proc.returncode, data


CASES = [
    # (名字, act.py 的参数, 期望退出码, 期望回读)
    ("checkbox 勾上 + 保存 + 刷新后回读",
     ["--kind", "checkbox", "--sel", "#enable", "--label", "on",
      "--apply-sel", SAVE, "--reload-verify"], 0, "on"),

    ("checkbox 取消勾选 + 保存 + 刷新后回读",
     ["--kind", "checkbox", "--sel", "#enable", "--label", "off",
      "--apply-sel", SAVE, "--reload-verify"], 0, "off"),

    ("toggle 图标开关(值在隐藏 input 里)+ 保存",
     ["--kind", "toggle", "--sel", "#ipsec_icon", "--value-sel", IPSEC_VALUE,
      "--label", "on", "--apply-sel", SAVE, "--reload-verify"], 0, "on"),

    # 页面初始就是 off,所以这一条走的是"已经是目标,一下都不点"那条分支 ——
    # 图标开关只有"翻一下"没有"设成 off",点了反而会翻走。
    ("toggle 已经是目标就一下都不点",
     ["--kind", "toggle", "--sel", "#ipsec_icon", "--value-sel", IPSEC_VALUE,
      "--label", "off", "--apply-sel", SAVE, "--reload-verify"], 0, "off"),

    ("text 填进去 + 保存 + 刷新后回读",
     ["--kind", "text", "--sel", "#psk", "--label", "test",
      "--apply-sel", SAVE, "--reload-verify"], 0, "test"),

    ("button 点开弹框,--expect-after 看见弹框才算成立",
     ["--kind", "button", "--sel", "#addBtn", "--expect-after", "#dlg_add"],
     0, "出现"),

    ("button 的 --expect-after 等不到就判失败",
     ["--kind", "button", "--sel", "#addBtn", "--expect-after", "#nope"],
     1, ""),

    ("select 原生下拉",
     ["--kind", "select", "--sel", "#proto", "--label", "L2TP/IPSec",
      "--apply-sel", SAVE, "--reload-verify"], 0, "L2TP/IPSec"),

    ("选择器指错了就判失败,不会当成没变化",
     ["--kind", "checkbox", "--sel", "#no_such_box", "--label", "on"], 1, ""),

    # ---- 地基那一条:不保存 + 刷新 = 必须抓出来 --------------------------
    ("**不点保存**就刷新回读 —— 假成功必须被抓出来",
     ["--kind", "text", "--sel", "#psk", "--label", "假的没保存",
      "--reload-verify"], 1, ""),

    ("同一步不刷新就回读 —— 读到的是刚填的值,会\"过\"(所以才必须刷新)",
     ["--kind", "text", "--sel", "#psk", "--label", "假的没保存"], 0, "假的没保存"),
]


def main(argv=None):
    argv = argv if argv is not None else sys.argv[1:]
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--show", action="store_true", help="别用无头模式")
    args = ap.parse_args(argv)

    for stream in (sys.stdout, sys.stderr):        # 台架控制台是 GBK
        try:
            stream.reconfigure(errors="replace")
        except Exception:
            pass

    port = _serve()
    print("==== UI 动作场景 · 离线自检(假设备页,不碰真机)====")
    passed = failed = 0
    for i, (name, extra, want_rc, want_read) in enumerate(CASES):
        rc, data = run_act(port, *extra, show=args.show, bust="n=%d" % i)
        got = data.get("read_back", "")
        ok = (rc == want_rc) and (got == want_read)
        print("[%s] %-46s 退出码=%s 回读=%r"
              % ("PASS" if ok else "FAIL", name, rc, got))
        if not ok:
            print("       期望 退出码=%s 回读=%r  %s"
                  % (want_rc, want_read, data.get("message", "")))
        passed += ok
        failed += not ok

    print("\n%d passed, %d failed" % (passed, failed))
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
