"""适配一台新路由器 —— 向导版,不用记任何命令、不用懂代码。

    python adapt.py            (Windows 上双击 adapt.bat)

它按顺序做四件事,每一步都会告诉你它在做什么、看到了什么:

    1. 探测页面   登录进去,把控件抄下来,并验证每个选择器到底命中几个
    2. 生成脚本   写出 models/<品牌>_<型号>.py —— 这就是交付物
    3. 离线体检   检查脚本自身是否自洽(不需要路由器)
    4. 逐个验证   每种拨号方式真的切一遍,看界面回读对不对

**前三步不会改路由器的任何配置**,第 4 步默认也只切换不保存。只有最后问你
"要不要真正保存"、你回答 y 之后,才会真正下发(那一步可能会断网)。

跑完之后,models/ 里那个文件就是成品:同事双击 start.bat 就能选到它。
"""
from __future__ import annotations

import os
import sys
import types

ROOT = os.path.dirname(os.path.abspath(__file__))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import settings as settings_mod
from modes import MODE_REQUIRED_FIELDS, merge_params
from tools import probe_router
from tools.check_model import check_facts, _open_engine

_FIELD_HINT = {
    "pppoe_user": "宽带账号", "pppoe_pass": "宽带密码",
    "vpn_server": "VPN 服务器地址", "vpn_user": "VPN 用户名",
    "vpn_pass": "VPN 密码",
}


def _ask(prompt: str, default: str = "") -> str:
    try:
        val = input(prompt).strip()
    except EOFError:
        val = ""
    return val or default


def _ask_secret(prompt: str, default: str = "") -> str:
    if sys.stdin.isatty():
        import getpass
        try:
            return getpass.getpass(prompt).strip() or default
        except Exception:
            pass
    return _ask(prompt, default)


def _yes(prompt: str, default: bool = False) -> bool:
    raw = _ask("%s [%s]: " % (prompt, "Y/n" if default else "y/N"))
    if not raw:
        return default
    return raw.lower().startswith("y")


def _progress(text: str) -> None:
    """原地刷新的进度行。管道/重定向里 \r 不会清行,会看到两遍 —— 那时就不打。"""
    if sys.stdout.isatty():
        print(text, end="", flush=True)


def _done(text: str) -> None:
    print(("\r" if sys.stdout.isatty() else "") + text)


def _rule(title: str) -> None:
    print("\n" + "=" * 60)
    print(title)
    print("=" * 60)


def _probe_args(**kw):
    """probe() 要的参数包。默认值和命令行入口保持一致。"""
    base = dict(url="", user="", password="", login_pass="input[type=password]",
                login_btn="", nav=[], open_sel="", brand="", model="",
                headless=False)
    base.update(kw)
    return types.SimpleNamespace(**base)


def _describe(facts: dict, report: dict) -> None:
    """把探测结果用人话说一遍 —— 用户不需要看 JSON,也不需要懂选择器。"""
    frames = report.get("frames") or []
    n_ctrl = sum(len(f.get("selects") or []) + len(f.get("dropdowns") or [])
                 for f in frames)
    print("  登录:%s" % ("成功" if report.get("login", {}).get("ok")
                          else "没做(没给密码)"
                          if report.get("login", {}).get("ok") is None
                          else "**失败**"))
    if len(frames) > 1:
        print("  页面结构:%d 个 frame(老式 frameset,菜单和表单分开)" % len(frames))
    print("  扫到 %d 个可能的下拉控件" % n_ctrl)
    for w in report.get("nav_warnings") or []:
        print("  [!] %s" % w)

    dial = facts.get("dial") or {}
    if str(dial.get("selector", "")).startswith("TODO"):
        print("  拨号控件:**没找到**")
    else:
        print("  拨号控件:找到了(%s)" % dial.get("kind"))
    modes = {k: v for k, v in (facts.get("modes") or {}).items() if k != "TODO"}
    if modes:
        print("  识别出的拨号方式:")
        for k, v in modes.items():
            print("      %-8s 界面上写作 %r" % (k, v))
    if "TODO" in (facts.get("modes") or {}):
        print("  [!] 其余拨号方式要点开下拉才看得到")
    if str(facts.get("apply", "")).startswith("TODO"):
        print("  保存键:**没找到**")
    else:
        print("  保存键:找到了")
    if facts.get("fields"):
        print("  账号密码输入框:%s" % ", ".join(facts["fields"]))
    if facts.get("mode_overrides"):
        print("  %s 有各自独立的输入框(已自动分开处理)"
              % "/".join(facts["mode_overrides"]))


def _collect_creds(modes, saved: dict) -> dict:
    """逐档问这一档要的账号密码。只用于第 4 步把输入框真的填一遍。"""
    need = [m for m in modes if MODE_REQUIRED_FIELDS.get(m)]
    if not need:
        return saved
    params_saved = dict(saved.get("params") or {})
    print("\n下面这几档要账号密码才能验证填表:%s" % "/".join(need))
    print("(不想填就一路回车 —— 那几档只验证'切换'这一半)")
    last = {}
    changed = False
    for m in need:
        blk = params_saved.get(m)
        blk = dict(blk) if isinstance(blk, dict) else {}
        print("  [%s]" % m)
        for f in MODE_REQUIRED_FIELDS[m]:
            cur = str(blk.get(f) or last.get(f) or params_saved.get(f) or "")
            val = _ask("    %s%s: " % (_FIELD_HINT.get(f, f),
                                       "(回车=%s)" % cur if cur else ""), cur)
            if val:
                last[f] = val
                blk[f] = val
                changed = True
        if blk:
            params_saved[m] = blk
    if changed:
        saved["params"] = params_saved
        settings_mod.save(saved)
        print("  已存进 router.yaml(仅本机,不会进仓库)。")
    return saved


def main(argv=None) -> int:
    import argparse
    from models._driver import _console_safe, run as driver_run
    _console_safe()
    ap = argparse.ArgumentParser(add_help=False)
    ap.add_argument("--headless", action="store_true",
                    help=argparse.SUPPRESS)   # 隐藏参数,仅冒烟测试用
    cli = ap.parse_args(argv)
    saved = settings_mod.load()

    _rule("适配一台新路由器")
    print("这个向导会:探测页面 → 生成脚本 → 体检 → 逐个模式验证。")
    print("前面几步都**不会改路由器的配置**;最后会问你要不要真正保存一次。")
    print("过程中会打开 Chrome,别去动那个窗口。\n")

    brand = _ask("品牌(如 Cudy): ")
    model = _ask("型号(如 AX3000): ")
    if not brand or not model:
        print("[X] 品牌和型号都要填 —— 它们决定文件名。")
        return 2
    default_url = "http://%s" % (saved.get("router_ip") or "192.168.1.1")
    url = _ask("路由器地址 [%s]: " % default_url, default_url)
    if not url.startswith("http"):
        url = "http://" + url
    password = _ask_secret("管理密码%s: "
                           % ("(回车=用 router.yaml 存的)" if saved.get("pass") else ""),
                           str(saved.get("pass") or ""))
    if not password:
        print("[!] 没有密码就没法登录进去看设置页;继续也行,但多半探不到东西。")

    name = "%s_%s" % (brand.strip(), model.strip().replace(" ", ""))
    target = os.path.join(ROOT, "models", "%s.py" % name)

    # ---- 第 1 步:探测 ----------------------------------------------------
    nav: list = []
    facts = report = None
    while True:
        _rule("[1/4] 探测页面(只看不改)")
        print("正在登录并抄下页面控件…(会开 Chrome,别动它)")
        args = _probe_args(url=url, user=saved.get("user", ""), password=password,
                           nav=list(nav), brand=brand, model=model,
                           headless=cli.headless)
        try:
            report, facts = probe_router.probe(args)
        except Exception as exc:
            # 只给第一行:Playwright 失败时会吐几十行浏览器日志,对测试员没用,
            # 淹掉了真正该看的那句话。
            print("[X] 探测失败:%s" % str(exc).strip().splitlines()[0])
            print("    常见原因:地址不对、这台机器连不到路由器、Chrome 没装。")
            print("    完整报错可以贴给 agent 看。")
            return 2
        _describe(facts, report)

        if not str((facts.get("dial") or {}).get("selector", "")).startswith("TODO"):
            break
        print("\n没找到拨号控件。最常见的原因是:**还停在首页,没进到 WAN 设置页**。")
        print("请看着刚才那个 Chrome 窗口(或自己用浏览器登进去),找到设置")
        print("拨号方式的那个页面,把要点的菜单名字**一字不差**地告诉我。")
        print("例:Internet Settings / 上网设置 / Network(多级菜单就一层一层加)")
        item = _ask("要点的菜单名(直接回车 = 放弃,先去问 agent): ")
        if not item:
            print("\n把上面这段摘要贴给 agent,问它下一步该怎么点。")
            print("**不要**让它去读 artifacts/ 里的 JSON —— 那很贵,摘要就够了。")
            return 1
        nav.append(item)

    # 自定义下拉:再点开一次抄全部选项原文
    if "TODO" in (facts.get("modes") or {}):
        print("\n再点开一次下拉,把其余拨号方式的原文抄下来…")
        args = _probe_args(url=url, user=saved.get("user", ""), password=password,
                           nav=list(nav), brand=brand, model=model,
                           open_sel=facts["dial"]["selector"],
                           headless=cli.headless)
        try:
            report, facts = probe_router.probe(args)
            _describe(facts, report)
        except Exception as exc:
            print("[!] 点开下拉失败(%s),先按已知的模式继续。" % exc)

    out = os.path.join(ROOT, "artifacts", "probe_%s.json" % name)
    os.makedirs(os.path.dirname(out), exist_ok=True)
    import json
    with open(out, "w", encoding="utf-8") as fh:
        json.dump(report, fh, ensure_ascii=False, indent=2)

    # ---- 第 2 步:生成脚本 ------------------------------------------------
    _rule("[2/4] 生成型号脚本")
    if os.path.exists(target):
        if not _yes("models/%s.py 已经存在,覆盖它?" % name):
            print("没有覆盖。想改名就重跑一次,型号填别的。")
            return 1
    probe_router.emit_script(target, facts, out)
    print("已写出:models/%s.py" % name)
    print("(证据存档在 %s —— 存着备查,平时不用打开)"
          % os.path.relpath(out, ROOT))

    # ---- 第 3 步:体检 ----------------------------------------------------
    _rule("[3/4] 离线体检(不碰路由器)")
    with open(target, "r", encoding="utf-8") as fh:
        source = fh.read()
    import importlib
    mod = importlib.import_module("models.%s" % name)
    importlib.reload(mod)
    engine, holder = _open_engine()
    try:
        rep = check_facts(name, mod.FACTS, source, engine)
    finally:
        if holder is not None:
            try:
                holder.__exit__(None, None, None)
            except Exception:
                pass
    rep.show()
    if not rep.ok:
        print("\n还有没填全的地方。把上面这几行错误贴给 agent(**只贴这几行**),")
        print("问它该怎么补;补完重跑 python adapt.py 即可。")
        return 1

    # ---- 第 4 步:逐个模式真机验证 ----------------------------------------
    from matrix.run import all_modes
    modes = all_modes(mod.FACTS)
    saved = _collect_creds(modes, settings_mod.load())

    _rule("[4/4] 逐个拨号方式验证(只切换,不保存)")
    print("每一档都会真的在界面上切一次,然后读回界面显示的值。")
    print("只有**读回来的值 == 目标措辞**才算这一档过了。\n")
    results = {}
    for m in modes:
        params = merge_params(m, saved.get("params") or {}, {})
        _progress("  %-9s 切换中…" % m)
        try:
            res = driver_run(mod.FACTS, m, params=params, apply=False,
                             admin_user=saved.get("user", ""),
                             admin_pass=password, headless=cli.headless)
        except Exception as exc:
            _done("  %-9s [X] 跑不起来:%s" % (m, str(exc).splitlines()[0]))
            results[m] = False
            continue
        if res["success"]:
            extra = (",已填 %s" % "/".join(res["filled"])) if res["filled"] else ""
            _done("  %-9s [OK] 界面回读 = %r%s" % (m, res["read_back"], extra))
        else:
            _done("  %-9s [X] %s" % (m, res["message"] or "没成功"))
            for w in res["warnings"]:
                print("               [!] %s" % w)
        results[m] = res["success"]

    ok_modes = [m for m, v in results.items() if v]
    bad_modes = [m for m, v in results.items() if not v]
    print("\n%d/%d 档通过。" % (len(ok_modes), len(modes)))
    if bad_modes:
        print("没过的:%s" % "/".join(bad_modes))
        print("把上面那几行 [X] 贴给 agent(**只贴那几行**),问它改哪个选择器。")
        print("常见原因:那一档的界面措辞抄得不完全一样,或者它在另一个页面上。")
        return 1

    # ---- 收尾:真正下发一次 ----------------------------------------------
    _rule("最后一步:真正保存一次(验收)")
    print("到这里只证明了'能切换'。要证明'能保存',得真正下发一次。")
    print("**这会改路由器配置,可能让它断网** —— 确认这台不是你正在上网的出口。")
    if not _yes("现在做验收(每档真正保存一次)?"):
        print("\n没做验收。想做的时候,单档命令是:")
        print("    python models/%s.py <拨号方式> --apply" % name)
        print("整轮性能测试(会自动逐档下发)是:python start.py")
        return 0

    for m in modes:
        params = merge_params(m, saved.get("params") or {}, {})
        _progress("  %-9s 下发中…" % m)
        res = driver_run(mod.FACTS, m, params=params, apply=True,
                         admin_user=saved.get("user", ""), admin_pass=password,
                         headless=cli.headless)
        state = ("[OK] 已保存" if res["success"] and res["applied"]
                 else "[!] 切了但保存键没点到" if res["success"]
                 else "[X] %s" % (res["message"] or "失败"))
        _done("  %-9s %s" % (m, state))
        for w in res["warnings"]:
            print("               [!] %s" % w)

    _rule("完成")
    print("models/%s.py 已经可用。" % name)
    print("现在双击 start.bat(或 python start.py)就能选到这台机跑整轮性能测试。")
    print("\n还差一件事需要在 perf.yaml 里配(整轮才准):")
    print("  wan_up.hosts —— 每档拨号方式各自 ping 哪个地址")
    print("  static 如果在列表里,记得从 dial_modes 里去掉(它不填任何地址)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
