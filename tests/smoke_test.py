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

    # --- models/ 层:FACTS + 动词库(交付形态)---------------------------------
    # 每台型号一个脚本、事实全显式、运行期零猜测。这里用真实脚本里的 FACTS
    # 驱动对应的 mock,证明"照探针产物填 FACTS -> 直接能跑"这条交付路成立。
    # **走型号脚本自己的 run()**(经 runner_for),而不是直接调驱动 —— 测的
    # 就是同事和整轮实际走的那条路。
    print("\n=== models/ (FACTS + 动词库, per-model delivery layer) ===")
    from models import _driver as model_driver
    from matrix.run import runner_for
    from models.Tenda_AX3000 import FACTS as TENDA_FACTS
    from models.Mercusys_BE3600 import FACTS as MERCUSYS_FACTS
    from models.Cudy_AX1500 import FACTS as CUDY_FACTS
    from models.Cudy_AX3000 import FACTS as CUDY3K_FACTS

    # 哪份 FACTS 属于哪个型号脚本 —— 用来取它自己的 run()
    SCRIPT_OF = {id(TENDA_FACTS): "Tenda_AX3000",
                 id(MERCUSYS_FACTS): "Mercusys_BE3600",
                 id(CUDY_FACTS): "Cudy_AX1500",
                 id(CUDY3K_FACTS): "Cudy_AX3000"}

    def read_toast(page, _res):
        # 跨 frame 找 toast(Cudy mock 的 toast 在 WAN 子 frame 里)
        el = model_driver.locate(page, "#toast")
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
        res = runner_for(SCRIPT_OF[id(facts)])(
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
    res = runner_for("Mercusys_BE3600")(MERCUSYS_FACTS, "dynamic", apply=False,
                                        admin_pass="admin123",
                                        url="http://127.0.0.1:%d/tenda.html" % port,
                                        config=cfg)
    ok = (not res["success"]) and not res["applied"] and bool(res["message"])
    print("[%s] wrong-page guard: success=%s message=%r"
          % ("PASS" if ok else "FAIL", res["success"], res["message"]))
    passed += ok
    failed += not ok

    # --- 第 5 个 UI 原型:外壳页 + iframe(BUFFALO)---------------------------
    # 这台机的三条真机事实,以前一条也没有离线覆盖 —— 改动 _driver 可能悄悄
    # 弄坏它而冒烟毫无反应(GOTCHAS.md 曾把这个记成已知缺口)。现在都覆盖上了:
    #   ① 设置页必须以 iframe 打开,且要等它的配置对象 CA 加载完;
    #   ② 页面脚本会把 iframe 地址改回去一次 -> 必须重试;
    #   ③ radio 和保存键被皮盖住 -> 必须 force 点。
    print("\n=== BUFFALO (第 5 原型:外壳页 + iframe) ===")
    from models.BUFFALO_WSR6000AX8 import FACTS as BUF_FACTS

    def buf_facts(**over):
        f = dict(BUF_FACTS)
        f["url"] = "http://127.0.0.1:%d/buffalo_advanced.html" % port
        f["iframe_target"] = "buffalo_wan.html"      # mock 的文件名
        f.update(over)
        return f

    buf_run = runner_for("BUFFALO_WSR6000AX8")
    buf_cases = [
        # (名字, facts, 模式, 下发?, 期望 success, 期望 verify)
        ("iframe + CA 就绪 + force 点", buf_facts(), "v6plus", False,
         True, ""),
        ("真的保存(CA 已就绪,不是 STALE)", buf_facts(), "dynamic", True,
         True, "Saved & Applied: dynamic"),
    ]
    for name, f, mode, do_apply, want_ok, want_verify in buf_cases:
        res = buf_run(f, mode, params={}, apply=do_apply,
                      admin_pass="admin123", config=cfg, verify_hook=read_toast)
        ok = (res["success"] is want_ok
              and res["read_back"] == mode
              and (res.get("verify") or "") == want_verify)
        print("[%s] %-32s success=%s read_back=%r verify=%r"
              % ("PASS" if ok else "FAIL", name, res["success"],
                 res["read_back"], res.get("verify")))
        if not ok:
            print("        message: %s warnings: %s"
                  % (res["message"], res["warnings"]))
        passed += ok
        failed += not ok

    # 账密框在别的页(fields_page):必须发警告,绝不静默装作填过了。
    res = buf_run(buf_facts(), "pppoe",
                  params={"pppoe_user": "u", "pppoe_pass": "p"}, apply=False,
                  admin_pass="admin123", config=cfg)
    ok = (res["success"] and not res["filled"]
          and len(res["warnings"]) == 2
          and all("pppoe_reg.html" in w for w in res["warnings"]))
    print("[%s] fields_page:账密在别页 -> 警告而非静默(filled=%s warnings=%d)"
          % ("PASS" if ok else "FAIL", res["filled"], len(res["warnings"])))
    passed += ok
    failed += not ok

    # 直接打开设置页(没有外壳 iframe):必须诚实失败。真机上这条路径最危险 ——
    # 页面照样渲染、radio 照样点、回读照样通过,保存提交的却是旧值。
    res = buf_run(buf_facts(url="http://127.0.0.1:%d/buffalo_wan.html" % port),
                  "dynamic", params={}, apply=True, admin_pass="admin123",
                  config=cfg, verify_hook=read_toast)
    ok = (not res["success"]) and not res["applied"] and bool(res["message"])
    print("[%s] 没有外壳页时诚实失败:success=%s applied=%s"
          % ("PASS" if ok else "FAIL", res["success"], res["applied"]))
    passed += ok
    failed += not ok

    # 就绪判据是**承重的**,不是装饰:拆掉 iframe_ready_js 就会在 CA 加载完
    # 之前保存 —— 切换照样成功、success 照样 true,只有 mock 的 toast 会喊
    # STALE。这一条钉住那个差别,免得哪天有人"简化"掉那道判据。
    stale = dict(buf_facts())
    stale.pop("iframe_ready_js")
    res = buf_run(stale, "dynamic", params={}, apply=True,
                  admin_pass="admin123", config=cfg, verify_hook=read_toast)
    ok = res["success"] and "STALE" in (res.get("verify") or "")
    print("[%s] 拆掉 iframe_ready_js -> 假成功(success=%s verify=%r)"
          % ("PASS" if ok else "FAIL", res["success"], res.get("verify")))
    if not ok:
        print("        本条期望的就是「假成功」。它变红意味着 mock 不再能复现"
              "那个陷阱了,而不是代码变好了 —— 先查 mock 的 CA 延迟。")
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

    # ②b chariot_perf.py 用**当前解释器**当子进程跑一次 --dry-run。
    #     它要同时活在两个 Python 世界里(老台架的 ActivePython 2.6.5,和跑
    #     日本 IPoE 拓扑的 Python 3),而这里只跑得到 Py3 那一侧 —— 所以这格
    #     守的是"Py2 兼容写法没把 Py3 跑坏",以及 ChariotBackend 真正的调用
    #     形态(子进程 + 末行 JSON)在这个解释器上成立。Py2 侧只能靠台架。
    import subprocess as _sp
    cell = os.path.join(ROOT, "matrix", "cell.example.json")
    dry = _sp.run([sys.executable, os.path.join(ROOT, "matrix", "chariot_perf.py"),
                   "--json-file", cell, "--dry-run"],
                  capture_output=True, text=True, errors="replace", timeout=60)
    from matrix.perf_backends import _last_json
    data = _last_json(dry.stdout or "")
    ok = (dry.returncode == 0 and isinstance(data, dict)
          and data.get("dry_run") is True and data.get("pairs") == 50)
    print("[%s] chariot_perf.py runs under this interpreter (py%d, --dry-run)"
          % ("PASS" if ok else "FAIL", sys.version_info[0]))
    if not ok:
        print("    rc=%s stdout=%r stderr=%r"
              % (dry.returncode, (dry.stdout or "")[-200:],
                 (dry.stderr or "")[-200:]))
    passed += ok
    failed += not ok

    # ②c 跑 chariot_perf.py 的解释器怎么选 + runner_for 的分派。
    #     两处都是"配错了不会报错,只会静默跑到别的东西上"的接线:
    #       - chariot.python 留空要落到当前解释器(Py3 台架不用配),旧键名
    #         python2: 还得继续认,否则老台架升级后会悄悄回到跟着 PATH 走;
    #       - **每个**型号都必须由它自己的 run() 驱动。少一个 run() 就会有一台
    #         机器被别的流程驱动,而那种失败是静默的(切了、看着成功、保存的
    #         是旧值)—— 所以这里遍历 models/ 全部型号,不是抽查两台。
    from matrix.config import ChariotCfg, load as _perf_load
    from matrix.run import list_models as _list_models
    import tempfile as _tf
    import importlib as _il
    with _tf.NamedTemporaryFile("w", suffix=".yaml", delete=False,
                                encoding="utf-8") as fh:
        fh.write("backend: chariot\nchariot:\n  python2: /legacy/py26\n")
        legacy_yaml = fh.name
    own_run = {}
    for _m in _list_models():
        _mod = _il.import_module("models.%s" % _m)
        own_run[_m] = (callable(getattr(_mod, "run", None))
                       and runner_for(_m) is _mod.run)
    ok = (ChariotCfg().interpreter == sys.executable
          and ChariotCfg(python="/x/py").interpreter == "/x/py"
          and _perf_load(legacy_yaml).chariot.interpreter == "/legacy/py26"
          and all(own_run.values()))
    os.unlink(legacy_yaml)
    print("[%s] chariot.python resolution + runner_for -> 型号自己的 run()(%d 台)"
          % ("PASS" if ok else "FAIL", len(own_run)))
    if not ok:
        print("        缺 run() 的型号:%s"
              % [m for m, good in own_run.items() if not good])
    passed += ok
    failed += not ok

    # ②c2 回读守卫的**结构性**保证(方案的硬约束 ①)。
    #      切错模式这类错误失败得静默 —— 报 success、截图正常、数据照进报告,
    #      只是那一格测的不是这个模式。所以 success 必须只有一个出口:
    #        - 驱动不导出裸的"点保存"动词,拿不到"点了就算成功"这条路;
    #        - fail() 产出的结果 success 恒 False;
    #        - Session 没有别的公开方法能把一轮标成成功。
    from models._driver import Session as _Sess
    _s = _Sess({"brand": "b", "model": "m", "modes": {"dynamic": "Dynamic"}},
               "dynamic")
    _failed_result = _s.fail("刻意失败")
    _public = [n for n in dir(_Sess) if not n.startswith("_")]
    ok = (not hasattr(model_driver, "apply")          # 没有裸 apply 动词
          and not hasattr(model_driver, "run")        # 老的成功出口已改名
          and hasattr(model_driver, "default_run")
          and _failed_result["success"] is False
          # 公开动词就这 10 个。新增一个"成功判定类"动词必须让这条先红:
          # 那是方案里唯一"永远不许新增"的一类。record_verified 不是成功出口 ——
          # 它和 set_mode 一样只写 _verified(**这两个是唯一的两个写者**),
          # success 仍旧只能从 apply_and_verify 出来。
          and sorted(_public) == ["apply_and_verify", "ensure_enabled", "fail",
                                  "fill_params", "goto_iframe", "login",
                                  "navigate", "record_verified", "set_mode",
                                  "warn"])
    print("[%s] 回读守卫:success 只有 apply_and_verify 一个出口" % ("PASS" if ok else "FAIL"))
    if not ok:
        print("        Session 公开成员=%s" % sorted(_public))
    passed += ok
    failed += not ok

    # ②c3 动词清单是从 docstring 生成的(方案 §6:根治文档漂移)。
    _verbs = model_driver.verbs()
    ok = (len(_verbs) >= 8 and all(doc.strip() for _n, doc in _verbs))
    print("[%s] 动词清单自动生成(%d 个动词,每个都有说明)"
          % ("PASS" if ok else "FAIL", len(_verbs)))
    if not ok:
        print("        缺 docstring 的动词:%s"
              % [n for n, d in _verbs if not d.strip()])
    passed += ok
    failed += not ok

    # ②c4 browser=False:根本不走 Web UI 的路线(有 HTTP API,或只能靠 py2
    #      桥接的机型)。这条路线是假成功的新入口候选,三件事必须同时成立:
    #        ① 真的不开浏览器(把 Browser 换成炸弹来证明),但 mode_overrides
    #           合并、凭据、result、_aborted 全照旧,退出时不截图;
    #        ② 浏览器动词一个都不许静默通过 —— page 是 None,静默 return 会让
    #           run() 带着别处写的 _verified 一路走到 apply_and_verify();
    #        ③ record_verified 精确相等:"PPPoEv6" 绝不能算成 "PPPoE",空回读
    #           绝不算通过(两边都空时 _norm 是相等的 —— 那是什么都没读到)。
    print("\n=== browser=False(不开浏览器的路线)===")
    HTTP_FACTS = {"brand": "X", "model": "Y", "url": "http://10.0.0.1",
                  "modes": {"pppoe": "PPPoE", "dynamic": "Dynamic IP"},
                  "mode_overrides": {"pppoe": {"apply": "#save-v2"}}}

    class _Boom:
        def __init__(self, *a, **kw):
            raise AssertionError("browser=False 时不该实例化 Browser")

    _real_browser = model_driver.Browser
    model_driver.Browser = _Boom
    try:
        # ① 骨架照旧,只少了浏览器;没记回读就不许成功
        with model_driver.session(HTTP_FACTS, "pppoe", apply=True,
                                  admin_pass="pw", browser=False) as s:
            skeleton = (s.page is None
                        and s.facts["apply"] == "#save-v2"   # overrides 合并了
                        and s.label == "PPPoE"
                        and s._admin_pass == "pw")           # 凭据带进来了
            r_bare = s.apply_and_verify()
        # 模式名没声明:browser=False 也照样 abort,原因保留
        with model_driver.session(HTTP_FACTS, "nosuch", browser=False) as s:
            r_abort = s.fail("这条不该盖掉 abort 的原因")
        ok = (skeleton and r_bare["success"] is False
              and r_bare["applied"] is False        # 没有保存键可点
              and r_bare["screenshot"] == ""        # 没有页面可截
              and bool(r_bare["message"])
              and "nosuch" in r_abort["message"])
        print("[%s] browser=False:不开浏览器,骨架照旧(page=%s screenshot=%r)"
              % ("PASS" if ok else "FAIL", None, r_bare["screenshot"]))
        if not ok:
            print("        skeleton=%s bare=%s abort=%r"
                  % (skeleton, r_bare, r_abort["message"]))
        passed += ok
        failed += not ok

        # ② 六个浏览器动词全都必须当场报错
        raised = {}
        with model_driver.session(HTTP_FACTS, "pppoe", browser=False) as s:
            for vname in ("login", "navigate", "goto_iframe", "ensure_enabled",
                          "set_mode", "fill_params"):
                try:
                    getattr(s, vname)()
                    raised[vname] = "静默通过了"
                except RuntimeError as exc:
                    raised[vname] = ("browser=False" in str(exc)
                                     and vname in str(exc))
        ok = all(v is True for v in raised.values())
        print("[%s] browser=False:浏览器动词全部当场报错(%d/6)"
              % ("PASS" if ok else "FAIL",
                 sum(1 for v in raised.values() if v is True)))
        if not ok:
            print("        没报错/文案不对的动词:%s"
                  % {k: v for k, v in raised.items() if v is not True})
        passed += ok
        failed += not ok

        # ③ record_verified:精确相等,且它写不出 success
        with model_driver.session(HTTP_FACTS, "pppoe", apply=True,
                                  browser=False) as s:
            v6 = s.record_verified("PPPoEv6", s.label)      # 子串诱饵
            after_v6 = dict(s._result)
            empty = s.record_verified("", "")               # 什么都没读到
            good = s.record_verified("  pppoe ", "PPPoE")   # 空白/大小写不计
            r_http = s.apply_and_verify()
        ok = (v6 is False and empty is False and good is True
              and after_v6["read_back"] == "PPPoEv6"   # 不对也记,那是证据
              and after_v6["success"] is False         # 它写不出 success
              and r_http["success"] is True            # 判定仍走唯一出口
              and r_http["read_back"] == "pppoe"
              and r_http["applied"] is False           # HTTP 路线不点保存
              and r_http["message"] == "")             # 上一次的失败话术已清掉
        print("[%s] record_verified:PPPoEv6/空回读都不算通过,精确相等才算"
              % ("PASS" if ok else "FAIL"))
        if not ok:
            print("        v6=%s empty=%s good=%s result=%s"
                  % (v6, empty, good, r_http))
        passed += ok
        failed += not ok
    finally:
        model_driver.Browser = _real_browser

    # ②d 每台机一份参数(perf_configs/<型号>.yaml)+ 开跑前检查。
    #     两件事都属于"配错了不报错,只是测的不是那条路":
    #       - JP 四档(transix/v6plus/…)不叫 dynamic 也不含 public,老规则会
    #         把它们猜成隧道档打到内网口;chariot.e2_ip 是那条显式出口;
    #       - 参数文件里留着 FILL_ME 就开跑,只会拿回一份全是 err 的报告,
    #         而路由器已经被真切了一遍 —— 所以必须在碰路由器之前拦住。
    from matrix import check_config
    from matrix import config as perf_config
    from matrix.chariot_perf import _e2_ip
    from matrix.run import _load_facts as _mfacts, all_modes as _mall
    bcfg = perf_config.load(model="BUFFALO_WSR6000AX8")
    bfacts = _mfacts("BUFFALO_WSR6000AX8")
    btopo = {"public_ip": bcfg.chariot.public_ip,
             "internet_ip": bcfg.chariot.internet_ip,
             "e2_ip": bcfg.chariot.e2_ip}
    found = check_config.check(bcfg, bfacts, _mall(bfacts))
    ok = (bcfg.source == perf_config.path_for_model("BUFFALO_WSR6000AX8")
          # JP 档走直连侧,pppoe 走隧道侧 —— 前者只有 e2_ip 覆盖才成立
          and _e2_ip(btopo, "v6plus") == "192.168.202.66"
          and _e2_ip(btopo, "pppoe") == "192.168.203.1"
          and _e2_ip({"public_ip": "1.1.1.1", "internet_ip": "2.2.2.2"},
                     "v6plus") == "2.2.2.2"      # 没覆盖就是老规则(猜错的那种)
          # FILL_ME 的注入机必须是 blocking,不能只是提醒
          and any(f.blocking and "FILL_ME" in f.msg for f in found)
          and bcfg.wan_up.host_for("v6plus") == "192.168.202.66"
          and bcfg.wan_up.host_for("pppoe") == "192.168.203.1")
    print("[%s] perf_configs/<model>.yaml + e2_ip override + preflight check"
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
