"""交互式入口 —— 什么都不用记、不用先准备任何文件:

    python start.py            (Windows 上双击 start.bat)

启动后它自己列出支持的型号,按数字选:型号 → 操作 → 模式,一路回车就是
最常用的默认(只切换、不点保存)。密码/宽带账号会先取 router.yaml 里存过的,
没有才问你,问完还可以顺手存起来 —— 下次就真的只剩按回车了。

想用参数化/脚本化的方式跑,老入口都还在:
    python models/<型号>.py <mode> [--apply]     单条命令切模式
    python run_matrix.py --demo / --model ...    整轮性能矩阵
"""
from __future__ import annotations

import argparse
import os
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import settings as settings_mod
from cli import merge_params
from engine.adapter import MODE_REQUIRED_FIELDS
from matrix.run import list_models

# 字段问起来时给同事看的中文说明
_FIELD_HINT = {
    "pppoe_user": "宽带账号", "pppoe_pass": "宽带密码",
    "vpn_server": "VPN 服务器地址", "vpn_user": "VPN 用户名",
    "vpn_pass": "VPN 密码",
    "static_ip": "静态 IP", "static_mask": "子网掩码",
    "static_gateway": "网关", "static_dns": "DNS",
}


def _ask(prompt: str, default: str = "") -> str:
    try:
        val = input(prompt).strip()
    except EOFError:
        val = ""
    return val or default


def _ask_secret(prompt: str, default: str = "") -> str:
    """密码:终端里不回显;stdin 被脚本接管(冒烟测试)时退回普通 input。"""
    if sys.stdin.isatty():
        import getpass
        try:
            return getpass.getpass(prompt).strip() or default
        except Exception:
            pass
    return _ask(prompt, default)


def _pick(prompt: str, n: int, default: int = 1) -> int:
    while True:
        raw = _ask("%s [1-%d](回车=%d): " % (prompt, n, default))
        if not raw:
            return default
        if raw.isdigit() and 1 <= int(raw) <= n:
            return int(raw)
        print("  请输入 1 到 %d 之间的数字。" % n)


def _load_facts(name: str) -> dict:
    import importlib
    return importlib.import_module("models.%s" % name).FACTS


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(add_help=False)   # 隐藏参数,仅冒烟测试用
    ap.add_argument("--url", default=None, help=argparse.SUPPRESS)
    ap.add_argument("--headless", action="store_true", help=argparse.SUPPRESS)
    args = ap.parse_args(argv)

    from models import _driver as model_driver

    print("==== 路由器拨号切换 / WAN 性能测试 ====")
    names = list_models()
    if not names:
        print("models/ 里没有型号脚本 —— 先按 skill 适配一台(见 README)。")
        return 1

    print("支持的型号:")
    facts_all = {}
    for i, name in enumerate(names, 1):
        facts_all[name] = _load_facts(name)
        print("  %d. %-18s (%s)"
              % (i, name,
                 "/".join(model_driver.available_modes(facts_all[name]))))
    name = names[_pick("选型号", len(names)) - 1]
    facts = facts_all[name]

    print("要做什么:")
    print("  1. 切拨号方式(只切换看回读,不点保存 —— 最常用)")
    print("  2. 切拨号方式并真正保存(会改动路由器配置!)")
    print("  3. 整轮性能矩阵 · 离线演示(不碰路由器,出样例报告)")
    print("  4. 整轮性能矩阵 · 真跑(切换+吞吐+报告,需测试台架)")
    action = _pick("选操作", 4)

    saved = settings_mod.load()

    # ---- 3/4:整轮矩阵交给 run_matrix --------------------------------------
    if action in (3, 4):
        from matrix.run import main as matrix_main
        if action == 3:
            return matrix_main(["--demo"])
        pw = ""
        if facts.get("login"):
            pw = _ask_secret("管理密码%s: " % ("(回车=用 router.yaml 存的)"
                                              if saved.get("pass") else ""),
                             str(saved.get("pass") or ""))
        do_apply = _ask("吞吐前的切换要真正保存吗?(整轮一般要)[Y/n]: ",
                        "y").lower().startswith("y")
        print("提示:各模式的宽带账号取 router.yaml / perf.yaml;频段与台架"
              "拓扑在 perf.yaml(没有就用内置默认)。")
        cmd = ["--model", name, "--pass", pw]
        if do_apply:
            cmd.append("--apply")
        if args.headless:
            cmd.append("--headless")
        return matrix_main(cmd)

    # ---- 1/2:切一次拨号方式 ------------------------------------------------
    modes = model_driver.available_modes(facts)
    print("该型号支持的模式:")
    for i, m in enumerate(modes, 1):
        print("  %d. %s" % (i, m))
    mode = modes[_pick("选模式", len(modes)) - 1]

    pw = ""
    if facts.get("login"):
        pw = _ask_secret("管理密码%s: " % ("(回车=用 router.yaml 存的)"
                                          if saved.get("pass") else ""),
                         str(saved.get("pass") or ""))
        if not pw:
            print("✗ 这台机要登录,必须给管理密码。")
            return 2

    params = merge_params(mode, saved.get("params") or {}, {})
    typed_params = {}
    for field in MODE_REQUIRED_FIELDS.get(mode, []):
        hint = _FIELD_HINT.get(field, field)
        cur = params.get(field, "")
        val = _ask("%s %s%s: " % (field, hint,
                                  "(回车=用已存的)" if cur else ""), cur)
        if val:
            params[field] = val
            if val != cur:
                typed_params[field] = val

    do_apply = action == 2
    if do_apply:
        sure = _ask("确认真正保存到路由器?[y/N]: ", "n")
        if not sure.lower().startswith("y"):
            do_apply = False
            print("好 —— 这次只切换不保存。")

    print("运行中(会打开 Chrome,别动它)...")
    res = model_driver.run(facts, mode, params=params, apply=do_apply,
                           admin_pass=pw, url=args.url,
                           headless=args.headless)

    if res["success"]:
        print("✓ 已切到 %s(界面回读 %r)%s"
              % (mode, res["read_back"],
                 ",并已点保存" if res["applied"]
                 else ";未点保存(演练)。要真正下发:重跑选操作 2"))
        if res["filled"]:
            print("  已填参数:%s" % ", ".join(res["filled"]))
    else:
        print("✗ 失败:%s" % (res["message"] or "未知原因"))
        for w in res["warnings"]:
            print("  ⚠ %s" % w)
        if res.get("screenshot"):
            print("  截图:%s" % res["screenshot"])

    # 顺手把这次手输的凭据存进 router.yaml,下次全程回车
    typed_pw = pw and pw != str(saved.get("pass") or "")
    if res["success"] and (typed_pw or typed_params):
        if _ask("把这次输入的密码/账号存进 router.yaml(仅本机,git 忽略,"
                "下次不用再输)?[y/N]: ", "n").lower().startswith("y"):
            if typed_pw:
                saved["pass"] = pw
            saved.setdefault("params", {}).update(typed_params)
            settings_mod.save(saved)
            print("已存到 router.yaml。")

    return 0 if res["success"] else 2


if __name__ == "__main__":
    sys.exit(main())
