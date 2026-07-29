"""Offline end-to-end smoke test against the bundled mock router page.

Serves tests/mock_router/ on localhost and drives every dial mode through the
real engine -- proving the login -> nav -> select -> fill -> read-back path
works with no physical router.  Run:

    python tests/smoke_test.py            # headless
    python tests/smoke_test.py --show     # watch it click
"""
from __future__ import annotations

import os
import sys
import threading
import yaml
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from config import Config

MOCK_DIR = os.path.join(ROOT, "tests", "mock_router")

def _serve():
    handler = partial(SimpleHTTPRequestHandler, directory=MOCK_DIR)
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd, httpd.server_address[1]


def main():
    show = "--show" in sys.argv
    httpd, port = _serve()
    url = "http://127.0.0.1:%d/index.html" % port
    cfg = Config()
    cfg.headless = not show
    # Drive the installed Chrome (channel="chrome") -- same path the field
    # bench uses, and avoids relying on a separately-staged chromium bundle.
    cfg.channel = "chrome"
    cfg.settle_ms = 300

    passed, failed = 0, 0
    # --- 凭据处理(离线,不开浏览器)------------------------------------------
    # router.yaml 的读写,以及"按模式挑参数" —— PPPoE 账密绝不能漏进 dynamic。
    print("\n=== 凭据 (router.yaml / merge_params) ===")
    import tempfile
    import settings as settings_mod
    from modes import merge_params

    with tempfile.TemporaryDirectory() as td:
        spath = os.path.join(td, "router.yaml")
        settings_mod.save({"router_ip": "192.168.0.1", "pass": "pw",
                           "no_apply": True,
                           "params": {"pppoe_user": "acc", "pppoe_pass": "s3"}},
                          path=spath)
        loaded = settings_mod.load(spath)
        ok = (loaded.get("router_ip") == "192.168.0.1"
              and loaded.get("no_apply") is True
              and loaded.get("params", {}).get("pppoe_user") == "acc")
        print("[%s] settings round-trip: %s" % ("PASS" if ok else "FAIL", loaded))
        passed += ok
        failed += not ok

        # saved creds must reach their own mode only; explicit params always pass
        p_pppoe = merge_params("pppoe", loaded["params"], {})
        p_dyn = merge_params("dynamic", loaded["params"], {"mtu": "1480"})
        ok = (p_pppoe == {"pppoe_user": "acc", "pppoe_pass": "s3"}
              and "pppoe_user" not in p_dyn and p_dyn.get("mtu") == "1480")
        print("[%s] merge_params: pppoe=%s dynamic=%s"
              % ("PASS" if ok else "FAIL", p_pppoe, p_dyn))
        passed += ok
        failed += not ok

    # --- models/ 层:FACTS + _driver(2026-07-16 起的交付形态) ----------------
    # 每台型号一个脚本、事实全显式、运行期零猜测。这里用真实脚本里的 FACTS
    # 驱动对应的 mock,证明"照探针产物填 FACTS -> 直接能跑"这条交付路成立。
    print("\n=== models/ (FACTS + _driver, per-model delivery layer) ===")
    from models import _driver as model_driver
    from models.Tenda_AX3000 import FACTS as TENDA_FACTS
    from models.Mercusys_BE3600 import FACTS as MERCUSYS_FACTS
    from models.Cudy_AX1500 import FACTS as CUDY_FACTS
    from models.Cudy_AX3000 import FACTS as CUDY3K_FACTS

    def read_toast(page, _res):
        # 跨 frame 找 toast(Cudy mock 的 toast 在 WAN 子 frame 里)
        el = model_driver._locate(page, "#toast")
        try:
            return el.inner_text().strip() if el else ""
        except Exception:
            return ""

    model_cases = [
        # (name, facts, page, mode, params, apply, expected)
        ("tenda pppoe+Connect", TENDA_FACTS, "tenda.html", "pppoe",
         {"pppoe_user": "acc", "pppoe_pass": "s3"}, True,
         dict(read_back="PPPoE", filled={"pppoe_user", "pppoe_pass"},
              applied=True, verify="Connected: PPPoE")),
        # 触发器初始就是 Dynamic IP:走"已是目标"的可信短路;默认不点保存。
        ("tenda dynamic no-apply", TENDA_FACTS, "tenda.html", "dynamic",
         {}, False,
         dict(read_back="Dynamic IP", filled=set(), applied=False, verify="")),
        # vpn 字段填写换 Mercusys 盖(台架那台 Tenda 的 v4 列表没有 L2TP/PPTP,
        # 2026-07-18 确认后已从其 FACTS 移除)。
        ("mercusys l2tp fields", MERCUSYS_FACTS, "custom.html", "l2tp",
         {"vpn_server": "10.0.0.1", "vpn_user": "u", "vpn_pass": "p"}, True,
         dict(read_back="L2TP",
              filled={"vpn_server", "vpn_user", "vpn_pass"},
              applied=True, verify="Saved: L2TP")),
        # IPv6 独立页:mode_overrides 换页 + enable_toggle 开门 + v6 flavor;
        # 模式名精确到 flavor(dhcpv6,不叫笼统的 "ipv6" —— 2026-07-23 用户定);
        # LAN 区的同名 "DHCPv6" radio 诱饵绝不能被点到(点到 = read_back 错)。
        ("tenda dhcpv6 gated page", TENDA_FACTS, "tenda_ipv6.html", "dhcpv6",
         {}, True,
         dict(read_back="DHCPv6", filled=set(), applied=True,
              verify="Saved: DHCPv6")),
        # 测试轮次要遍历两个 v6 flavor:pppoev6 是独立可运行模式,带宽带账密。
        ("tenda pppoev6 flavor", TENDA_FACTS, "tenda_ipv6.html", "pppoev6",
         {"pppoe_user": "u6", "pppoe_pass": "p6"}, True,
         dict(read_back="PPPoEv6", filled={"pppoe_user", "pppoe_pass"},
              applied=True, verify="Saved: PPPoEv6")),
        ("mercusys pppoe+Save", MERCUSYS_FACTS, "custom.html", "pppoe",
         {"pppoe_user": "acc", "pppoe_pass": "s3"}, True,
         dict(read_back="PPPoE", filled={"pppoe_user", "pppoe_pass"},
              applied=True, verify="Saved: PPPoE")),
        # Cudy AX1500:老式 frameset UI —— 登录在主文档,菜单/WAN 表单在各自子
        # frame 里,驱动必须全 frame 查找;保存键旁埋着隐藏的 Connect/
        # Disconnect 诱饵。(另一台 Cudy 是 LuCI,见下面 cudy-ax3000)
        ("cudy-ax1500 dynamic no-apply", CUDY_FACTS, "cudy.html", "dynamic",
         {}, False,
         dict(read_back="DHCP Client", filled=set(), applied=False, verify="")),
        ("cudy-ax1500 pppoe frames", CUDY_FACTS, "cudy.html", "pppoe",
         {"pppoe_user": "acc", "pppoe_pass": "s3"}, True,
         dict(read_back="PPPoE", filled={"pppoe_user", "pppoe_pass"},
              applied=True, verify="Saved & Applied: PPPoE")),
        ("cudy-ax1500 l2tp fields", CUDY_FACTS, "cudy.html", "l2tp",
         {"vpn_server": "10.0.0.9", "vpn_user": "u", "vpn_pass": "p"}, True,
         dict(read_back="L2TP",
              filled={"vpn_server", "vpn_user", "vpn_pass"},
              applied=True, verify="Saved & Applied: L2TP")),
        # Cudy AX3000 = LuCI/OpenWrt,和上面那台 frameset 的 Cudy 完全两种 UI。
        # 这两条守的是 LuCI 特有的三个坑:CBI 的 id 含点号(只能 [id='...'],
        # 用 #... 会被当成 id+class 命中 0)、页面上 4 个 name=cbi.apply 必须靠
        # form:has(拨号控件) 锚定(点错 form 的话 toast 会喊 WRONG FORM)、
        # 以及选完 proto 后整段 DOM 被 XHR 重建(旧句柄失效,回读得重新解析)。
        ("cudy-ax3000 pppoe (LuCI, 4 个 cbi.apply)", CUDY3K_FACTS,
         "cudy_luci.html", "pppoe", {"pppoe_user": "u", "pppoe_pass": "p"}, True,
         dict(read_back="PPPoE", filled={"pppoe_user", "pppoe_pass"},
              applied=True, verify="Saved & Applied: PPPoE")),
        ("cudy-ax3000 l2tp (AJAX 挂载的字段)", CUDY3K_FACTS,
         "cudy_luci.html", "l2tp",
         {"vpn_server": "10.0.0.9", "vpn_user": "vu", "vpn_pass": "vp"}, True,
         dict(read_back="L2TP", filled={"vpn_server", "vpn_user", "vpn_pass"},
              applied=True, verify="Saved & Applied: L2TP")),
    ]
    for name, facts, page_file, mode, params, do_apply, want in model_cases:
        res = model_driver.run(
            facts, mode, params=params, apply=do_apply,
            admin_pass="admin123",
            url="http://127.0.0.1:%d/%s" % (port, page_file),
            config=cfg, verify_hook=read_toast)
        ok = (res["success"]
              and res["read_back"].strip() == want["read_back"]
              and want["filled"] <= set(res["filled"])
              and res["applied"] == want["applied"]
              and (res.get("verify") or "") == want["verify"])
        status = "PASS" if ok else "FAIL"
        print("[%s] %-24s read_back=%-12r filled=%s applied=%s verify=%r"
              % (status, name, res["read_back"], res["filled"],
                 res["applied"], res.get("verify")))
        if not ok:
            print("        message: %s warnings: %s"
                  % (res["message"], res["warnings"]))
        passed += ok
        failed += not ok

    # 事实对不上的页面必须诚实失败(而不是零交互的假成功):拿 Mercusys 的
    # FACTS 去跑 Tenda 页,菜单/控件都对不上 -> success=False + 明确 message。
    res = model_driver.run(MERCUSYS_FACTS, "dynamic", apply=False,
                           admin_pass="admin123",
                           url="http://127.0.0.1:%d/tenda.html" % port,
                           config=cfg)
    ok = (not res["success"]) and not res["applied"] and bool(res["message"])
    print("[%s] wrong-page guard: success=%s message=%r"
          % ("PASS" if ok else "FAIL", res["success"], res["message"]))
    passed += ok
    failed += not ok

    # --- run_matrix(matrix/ 编排层)-----------------------------------------
    # ① --demo 离线整轮:读 perf.yaml -> 主循环 -> simulate 后端 -> HTML+CSV
    #    报告落盘。不碰路由器、不需要 Playwright,验证的是编排层本身。
    print("\n=== run_matrix (matrix/ orchestration) ===")
    import glob as glob_mod
    from matrix.run import main as matrix_main
    with tempfile.TemporaryDirectory() as td:
        pcfg = os.path.join(td, "perf.yaml")
        with open(pcfg, "w", encoding="utf-8") as fh:
            yaml.safe_dump({"model": "Tenda_AX3000", "backend": "simulate",
                            "bands": ["lan", "2GHz"], "protocols": ["TCP"],
                            "report": {"dir": td}}, fh, allow_unicode=True)
        rc = matrix_main(["--demo", "--config", pcfg])
        htmls = glob_mod.glob(os.path.join(td, "wanperf_*.html"))
        csvs = glob_mod.glob(os.path.join(td, "wanperf_*.csv"))
        csv_text = open(csvs[0], encoding="utf-8").read() if csvs else ""
        # 默认矩阵 dynamic+pppoe × 2 频段 × 3 方向 × TCP = 12 行测量
        ok = (rc == 0 and len(htmls) == 1 and len(csvs) == 1
              and os.path.getsize(htmls[0]) > 1000
              and csv_text.count("\n") == 13    # 表头 + 12 行
              and "2GHz" in csv_text)
        print("[%s] run_matrix --demo: rc=%s html=%d csv_rows=%d"
              % ("PASS" if ok else "FAIL", rc, len(htmls),
                 max(csv_text.count("\n") - 1, 0)))
        passed += ok
        failed += not ok

    # ② chariot_perf._judge:判稳纯函数 == 旧脚本 result_judge 的语义
    #    (跳过前 10s 爬坡窗;min < 0.9*max 即判不稳)。
    from matrix.chariot_perf import _judge

    class _FakeChariot:
        """duration=20 时 _judge 应取 get_throughput(10,15) 和 (15,20) 两窗。"""
        def __init__(self, windows, total):
            self._w, self._t = windows, total

        def get_throughput(self, time_1=None, time_2=None):
            return self._t if time_1 is None else self._w[time_1]

    t1, s1, ok1 = _judge(_FakeChariot({10: 95.0, 15: 92.0}, 100.0), 20, 0.9)
    t2, s2, ok2 = _judge(_FakeChariot({10: 100.0, 15: 89.0}, 99.0), 20, 0.9)
    ok = (t1 == 100.0 and s1 == [95.0, 92.0] and ok1 is True   # 92 >= 90
          and t2 == 99.0 and ok2 is False)                     # 89 < 90
    print("[%s] chariot_perf._judge == original result_judge semantics"
          % ("PASS" if ok else "FAIL"))
    passed += ok
    failed += not ok

    # ③ start.py 交互式入口:管道喂按键,选型号→操作2(单切)→选模式→切换。
    #    台架语义(2026-07-23 用户定):切了就真正下发 —— 断言 apply 发生了。
    print("\n=== start.py (interactive wizard) ===")
    import subprocess
    from matrix.run import list_models, all_modes as matrix_all_modes
    model_idx = list_models().index("Tenda_AX3000") + 1
    mode_idx = matrix_all_modes(TENDA_FACTS).index("pppoe") + 1
    answers = "%d\n2\n%d\nadmin123\nacc\ns3\nn\n" % (model_idx, mode_idx)
    swp = subprocess.run(
        [sys.executable, os.path.join(ROOT, "start.py"),
         "--url", "http://127.0.0.1:%d/tenda.html" % port]
        + (["--headless"] if cfg.headless else []),
        input=answers, capture_output=True, text=True, timeout=240)
    ok = (swp.returncode == 0
          and "已切到 pppoe" in swp.stdout
          and "'PPPoE'" in swp.stdout
          and "已下发保存" in swp.stdout)
    print("[%s] start.py wizard: rc=%s pick=模型%d/模式%d"
          % ("PASS" if ok else "FAIL", swp.returncode, model_idx, mode_idx))
    if not ok:
        print(swp.stdout[-800:])
        print(swp.stderr[-400:])
    passed += ok
    failed += not ok

    # ④ 型号脚本体检:仓库里每个 models/*.py 都必须自洽(没有残留 TODO、
    #    每个模式覆盖后都有 dial/apply、要填的字段有选择器、措辞不撞车、
    #    选择器语法合法)。适配新型号时这一条会先于真机拦下低级错误。
    print("\n=== tools/check_model.py (每个型号脚本自洽) ===")
    from tools.check_model import main as check_main
    ok = check_main(["--all"]) == 0
    print("[%s] check_model --all" % ("PASS" if ok else "FAIL"))
    passed += ok
    failed += not ok

    httpd.shutdown()
    print("\n%d passed, %d failed" % (passed, failed))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
