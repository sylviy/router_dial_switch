"""编排器:一条命令跑完整套 WAN 性能矩阵。

主循环(照旧 Dial.py 的骨架,但拨号方式改由 Web 驱动、竞品路由器也能切):
    for 每档拨号方式:
        用型号脚本(models/<品牌>_<型号>.py)切到该模式  → 记录是否切成功
        等 WAN 拨通
        for 频段 × 方向 × 协议:测吞吐(simulate 或 chariot 后端)
    出报告(HTML + CSV)+ 终端汇总

用法:
    python run_matrix.py --list                       列出已适配型号
    python run_matrix.py --demo                       离线演示(不碰路由器,模拟数据)
    python run_matrix.py --model Tenda_AX3000         真跑(默认只切换不点保存)
    python run_matrix.py --model Tenda_AX3000 --apply 真跑并真正下发保存
    python run_matrix.py --config my.yaml --backend chariot --apply

凭据(管理密码/宽带账密)取自 router.yaml(python cli.py setup 生成),
按模式过滤 —— PPPoE 账密不会带进 dynamic 运行。
"""
from __future__ import annotations

import argparse
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import settings as settings_mod
from matrix import config as perf_config
from matrix import report as report_mod
from matrix.perf_backends import make_backend
from matrix.wanup import wait_wan_up

_C_OK, _C_BAD, _C_DIM, _C_RST = "\033[32m", "\033[31m", "\033[90m", "\033[0m"


def _color(txt, code):
    return code + txt + _C_RST if sys.stdout.isatty() else txt


def list_models() -> list:
    # 注意:不能用 glob —— 本仓库路径里有 "[Tool]",glob 会把方括号当字符类,
    # 静默返回空列表(CLAUDE.md 的老坑,这里也踩过)。
    out = []
    mdir = os.path.join(ROOT, "models")
    for fn in sorted(os.listdir(mdir)):
        name, ext = os.path.splitext(fn)
        if ext == ".py" and not name.startswith("_"):
            out.append(name)
    return out


def _load_facts(model: str) -> dict:
    """按型号脚本名(models/<name>.py)取它的 FACTS。"""
    path = os.path.join(ROOT, "models", model + ".py")
    if not os.path.exists(path):
        raise SystemExit("没有这个型号脚本:models/%s.py(可用:%s)"
                         % (model, ", ".join(list_models())))
    import importlib
    mod = importlib.import_module("models.%s" % model)
    facts = getattr(mod, "FACTS", None)
    if not isinstance(facts, dict):
        raise SystemExit("models/%s.py 里没有 FACTS 字典。" % model)
    return facts


def _switch(facts, mode, params, apply, admin_user, admin_pass, headless):
    """真正切一次拨号方式。延迟 import _driver:它会拉起 Playwright,
    --demo 时根本不 import,好让工具在没装 playwright 的机器上也能演示。"""
    from cli import merge_params
    from models import _driver
    merged = merge_params(mode, params.get("saved") or {}, params.get("explicit") or {})
    return _driver.run(facts, mode, params=merged, apply=apply,
                       admin_user=admin_user, admin_pass=admin_pass,
                       headless=headless)


def main(argv=None) -> int:
    saved = settings_mod.load()
    ap = argparse.ArgumentParser(
        description="WAN 性能矩阵:切拨号方式(Web 驱动)→ 等 WAN → 测吞吐 → 出报告")
    ap.add_argument("--config", default=perf_config.DEFAULT_PATH,
                    help="perf.yaml 路径(默认仓库根;缺失则用 perf.example.yaml)")
    ap.add_argument("--model", default=None,
                    help="型号脚本名(models/<name>.py);覆盖 perf.yaml 的 model")
    ap.add_argument("--backend", choices=["simulate", "chariot"], default=None,
                    help="性能后端;覆盖 perf.yaml")
    ap.add_argument("--apply", action="store_true",
                    help="切模式时真正点保存/连接(默认只切换看回读)")
    ap.add_argument("--demo", action="store_true",
                    help="离线演示:不驱动路由器、强制 simulate 后端,直接出样例报告")
    ap.add_argument("--headless", action="store_true", help="无窗口驱动浏览器")
    ap.add_argument("--user", default=saved.get("user", ""), help="管理用户名")
    ap.add_argument("--pass", dest="password", default=saved.get("pass", ""),
                    help="管理密码(默认取 router.yaml)")
    ap.add_argument("--list", action="store_true", help="列出已适配型号后退出")
    args = ap.parse_args(argv)

    if args.list:
        print("已适配型号(models/*.py):")
        for m in list_models():
            print("  " + m)
        return 0

    cfg = perf_config.load(args.config)
    if args.model:
        cfg.model = args.model
    if args.backend:
        cfg.backend = args.backend
    if args.demo:
        cfg.backend = "simulate"

    if not cfg.model and not args.demo:
        raise SystemExit("没指定型号:--model <名字>,或在 perf.yaml 里写 model:。"
                         "(想先看样例报告?加 --demo)")

    # --demo 不驱动路由器,连型号脚本都不 import(避免拉起 Playwright)
    facts = _load_facts(cfg.model) if (cfg.model and not args.demo) else None
    if facts and cfg.model and not args.demo and facts.get("login") \
            and not args.password:
        raise SystemExit("缺管理密码:先 `python cli.py setup` 存进 router.yaml,"
                         "或本次加 --pass <密码>。(只想看样例报告加 --demo)")

    backend = make_backend(cfg)
    print(_color("===== WAN 性能矩阵 =====", _C_DIM))
    print("型号=%s  后端=%s  模式=%s  频段=%s  方向=%s  协议=%s%s"
          % (cfg.model or "(demo)", cfg.backend,
             "/".join(s.mode for s in cfg.dial_modes), "/".join(cfg.bands),
             "/".join(cfg.directions), "/".join(cfg.protocols),
             "  [demo]" if args.demo else ("" if args.apply else "  [不点保存]")))

    rows = []            # 扁平结果(给报告 + CSV)
    switch_log = []      # 每档模式的切换状态

    for step in cfg.dial_modes:
        mode = step.mode
        print("\n=== 切到 %s ===" % mode)
        applied = False
        if args.demo:
            switched, read_back, message = True, "(demo)", "离线模拟,未驱动路由器"
        else:
            res = _switch(facts, mode,
                          {"saved": saved.get("params") or {},
                           "explicit": step.params},
                          args.apply, args.user, args.password, args.headless)
            switched = bool(res.get("success"))
            read_back = res.get("read_back") or ""
            applied = bool(res.get("applied"))
            message = res.get("message") or ""
            for w in res.get("warnings") or []:
                message = (message + " | " + w) if message else w
        tag = _color("OK", _C_OK) if switched else _color("FAIL", _C_BAD)
        print("    切换 %s  回读=%r%s" % (tag, read_back,
                                         "  已保存" if applied else ""))
        switch_log.append({"mode": mode, "switched": switched,
                           "read_back": read_back, "message": message})
        if not switched:
            print(_color("    ✗ 切换失败,跳过该模式的吞吐测量。", _C_BAD)
                  + ("  %s" % message if message else ""))
            rows.append({"mode": mode, "switched": False, "read_back": read_back,
                         "band": "", "direction": "", "proto": "",
                         "mbps": None, "stable": None,
                         "error": message or "switch failed"})
            continue

        if not args.demo:
            wait_wan_up(cfg.wan_up)

        for band in cfg.bands:
            for proto in cfg.protocols:
                for direction in cfg.directions:
                    m = backend.measure(mode, band, direction, proto)
                    flag = (_color("err", _C_BAD) if m.error else
                            (_color("%.1f" % m.mbps, _C_OK) if m.stable
                             else _color("%.1f ⚠" % m.mbps, _C_BAD)))
                    print("    %-4s %-4s %-3s  %s Mbps%s"
                          % (band, direction, proto, flag,
                             "  " + m.error if m.error else ""))
                    rows.append({"mode": mode, "switched": True,
                                 "read_back": read_back, "band": band,
                                 "direction": direction, "proto": proto,
                                 "mbps": m.mbps, "stable": m.stable,
                                 "error": m.error})

    # 收尾:切回安全模式(可选)
    if cfg.reset_mode and not args.demo and facts:
        print("\n=== 收尾:切回 %s ===" % cfg.reset_mode)
        try:
            _switch(facts, cfg.reset_mode,
                    {"saved": saved.get("params") or {}, "explicit": {}},
                    args.apply, args.user, args.password, args.headless)
        except Exception as exc:
            print(_color("    收尾切换出错(忽略):%s" % exc, _C_DIM))

    # 出报告
    import datetime
    ctx = {"title": cfg.report_title, "model": cfg.model,
           "backend": cfg.backend,
           "timestamp": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
           "bands": cfg.bands, "directions": cfg.directions,
           "protocols": cfg.protocols, "rows": rows, "switch": switch_log}
    paths = report_mod.write_reports(ctx, os.path.join(ROOT, cfg.report_dir)
                                     if not os.path.isabs(cfg.report_dir)
                                     else cfg.report_dir)

    print(_color("\n===== 汇总 =====", _C_DIM))
    for s in switch_log:
        print("  %-10s 切换=%s" % (s["mode"],
              _color("OK", _C_OK) if s["switched"] else _color("FAIL", _C_BAD)))
    print("\n报告已生成:")
    print("  HTML: %s" % paths["html"])
    print("  CSV : %s" % paths["csv"])
    # 全部模式都切成功才算整体成功
    return 0 if all(s["switched"] for s in switch_log) else 2


if __name__ == "__main__":
    sys.exit(main())
