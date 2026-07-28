"""Command-line entry point -- the ADAPTATION toolbox.

Daily switching on an already-adapted model goes through its own script
(`python models/Tenda_AX3000.py pppoe`).  This CLI is what you use on a device
that has no script yet: a heuristic attempt, and `diagnose` to dump the
evidence a new model script is written from (see
.claude/skills/adapt-router-model/SKILL.md).

    python cli.py diagnose       # evidence dump -> artifacts/diagnose_*.json
    python cli.py pppoe          # heuristic attempt; mode is just the first word
    python cli.py dynamic

Everything else (IP, passwords, per-mode credentials) comes from router.yaml
(one-time `python cli.py setup`); any flag still overrides it.  Long form:

    python cli.py --router-ip 192.168.1.1 --pass admin123 \
        --mode pppoe --param pppoe_user=test --param pppoe_pass=test123

When a run fails because the dial control wasn't recognised, the diagnose pass
runs automatically and -- new -- if it verified a unique selector, the CLI
offers to write the pin profile for you (no hand-edited YAML):

    [pin] 1. widget-leaf text='PPPoE' label='Internet Connection Type'
    write profiles/auto_192_168_0_1.yaml with candidate 1? [Y/n]
"""
from __future__ import annotations

import argparse
import json
import os
import sys

# 仓库根必须在 sys.path 上。平时"脚本所在目录"是 Python 自动加的,但仓库自带的
# 嵌入式解释器(vendor\python,带 ._pth)跑在隔离模式下,**不会**加脚本目录 ——
# 2026-07-28 台架实测:run.bat setup 直接 ModuleNotFoundError: No module named
# 'settings'。其它入口(start.py / run_matrix.py / models/*.py / smoke_test.py)
# 早就自己插了这一行,只有 cli.py 漏了。
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import settings as settings_mod
from config import Config
from engine.browser import Browser
from engine.adapter import RouterAdapter, MODE_REQUIRED_FIELDS
from engine import profile as profile_mod

MODES = ["dynamic", "static", "pppoe", "l2tp", "pptp", "ipv6"]
COMMANDS = MODES + ["setup", "diagnose"]


def _parse_params(pairs):
    out = {}
    for item in pairs or []:
        if "=" not in item:
            raise SystemExit("bad --param '%s' (expected key=value)" % item)
        k, v = item.split("=", 1)
        out[k.strip()] = v
    return out


def merge_params(mode: str, saved: dict, explicit: dict) -> dict:
    """本次运行要用的参数。router.yaml 里的凭据**按模式挑**(只取该模式需要
    的字段,所以 PPPoE 账密绝不会漏进 dynamic/ipv6 的运行),而命令行显式给的
    --param 是用户意图,永远直通。

    router.yaml 的 params: 支持两层,后者覆盖前者 ——

        params:
          pppoe_user: adsl            # 扁平写法:所有模式共用
          pppoe_pass: adsl
          l2tp:                       # 按模式写法:只对这个模式生效
            vpn_server: 192.168.202.254
            vpn_user: l2tp_account
            vpn_pass: l2tp_secret
          pptp:
            vpn_server: 192.168.202.254
            vpn_user: pptp_account    # 和 L2TP 是不同的账号
            vpn_pass: pptp_secret

    L2TP 和 PPTP 共用 vpn_user/vpn_pass 这套字段名(界面上就是同一个概念),
    但台架给它们发的是两套账号,所以必须能分开存 —— 只有扁平一层的话,
    后填的那套会把先填的覆盖掉。
    """
    out = {}
    needed = MODE_REQUIRED_FIELDS.get(mode, [])
    saved = saved or {}
    per_mode = saved.get(mode)
    per_mode = per_mode if isinstance(per_mode, dict) else {}
    for src in (saved, per_mode):          # 按模式的块优先级更高
        for k, v in src.items():
            if k in needed and v is not None:
                out[k] = str(v)
    out.update(explicit)
    return out


def build_config(args, saved: dict) -> Config:
    cfg = Config()
    cfg.headless = args.headless or bool(saved.get("headless"))
    if args.chrome_path:
        cfg.executable_path = args.chrome_path
    if args.bundled_chromium:
        cfg.channel = None
    if args.browsers_path:
        cfg.browsers_path = args.browsers_path
    if args.screenshot_dir:
        cfg.screenshot_dir = args.screenshot_dir
    return cfg


# ---------------------------------------------------------------------------
# setup wizard: asks the few things every run needs and writes router.yaml,
# so the everyday command becomes `python cli.py <mode>`.
# ---------------------------------------------------------------------------
def run_setup() -> int:
    old = settings_mod.load()

    def ask(label, key, default=""):
        cur = str(old.get(key, default) or default)
        shown = (" [%s]" % cur) if cur else ""
        val = input("%s%s: " % (label, shown)).strip()
        return val or cur

    print("一次性配置(写入 router.yaml,已被 .gitignore 忽略)/ one-time setup")
    data = dict(old)
    data["router_ip"] = ask("路由器 IP (router IP)", "router_ip", "192.168.1.1")
    data["user"] = ask("管理员用户名,通常留空 (admin user)", "user")
    data["pass"] = ask("管理员密码 (admin password)", "pass")
    params = dict(old.get("params") or {})

    def ask_field(store, key, label):
        """问一个凭据字段,回车沿用已存的。store 是要写进去的那层 dict。"""
        cur = str(store.get(key, "") or "")
        val = input("  %s%s: " % (label, (" [%s]" % cur) if cur else "")).strip()
        if val or cur:
            store[key] = val or cur

    print("-- 拨号凭据,只在对应模式时使用;留空跳过 --")
    print("[PPPoE]")
    ask_field(params, "pppoe_user", "宽带账号 (pppoe_user)")
    ask_field(params, "pppoe_pass", "宽带密码 (pppoe_pass)")

    # L2TP 和 PPTP 分开问:界面上是同一套字段名,但台架给的是两套账号,
    # 存在一层里后填的会覆盖先填的(2026-07-28 用户反馈)。各自存进
    # params[模式] 的子块,merge_params 会按模式取。
    for mode, title in (("l2tp", "[L2TP]"), ("pptp", "[PPTP]")):
        blk = params.get(mode)
        blk = dict(blk) if isinstance(blk, dict) else {}
        print("%s(这台机没有就直接回车跳过)" % title)
        ask_field(blk, "vpn_server", "服务器地址 (vpn_server)")
        ask_field(blk, "vpn_user", "用户名 (vpn_user)")
        ask_field(blk, "vpn_pass", "密码 (vpn_pass)")
        if blk:
            params[mode] = blk
    if params:
        data["params"] = params
    ans = input("默认不点保存(--no-apply,先试跑更安全)?[Y/n]: ").strip().lower()
    data["no_apply"] = ans not in ("n", "no")
    path = settings_mod.save(data)
    print("已写入 %s" % path)
    print("现在可以直接运行:  python cli.py pppoe   (或 dynamic / l2tp / ...)")
    if data["no_apply"]:
        print("注意:当前默认只切换不保存;确认无误后用 --apply 真正下发,"
              "或重跑 setup 关掉该默认。")
    return 0


# ---------------------------------------------------------------------------
# auto-pin: turn a failing run's diagnose evidence into a profile file,
# so nobody has to read the JSON artifact and hand-write YAML.  Two concepts
# are pinnable: dial_mode_select (control seen but not driveable) and
# enable_toggle (nothing seen -- an OFF switch may gate the whole section,
# e.g. TP-Link/Tenda IPv6 pages).
# ---------------------------------------------------------------------------
def _ask_choice(n: int, concept: str, assume_yes: bool) -> int:
    """Return the 1-based candidate index, or 0 to skip."""
    if sys.stdin.isatty() and not assume_yes:
        raw = input("[pin] 写入哪一个?回车=1,数字选择,n=跳过: ").strip().lower()
        if raw in ("n", "no"):
            print("[pin] 跳过;推荐选择器已在上方,可手动填入 "
                  "profiles/*.yaml 的 selectors.%s。" % concept)
            return 0
        if raw.isdigit() and 1 <= int(raw) <= n:
            return int(raw)
        return 1
    if n > 1 and not assume_yes:
        print("[pin] 非交互环境且候选不止一个,不自动写入。重跑时加 --pin 采用第 1 个,"
              "或手动挑选上面的选择器。")
        return 0
    return 1


def _write_pin(concept: str, sel: str, brand: str, model: str, host: str,
               evidence: str, profile_dir: str, settings_path: str) -> None:
    brand = brand or "auto_" + profile_mod._slug(host)
    path = profile_mod.write_pin(brand, model, {concept: sel},
                                 profile_dir=profile_dir, evidence=evidence)
    if path is None:
        print("[pin] profiles/ 下已有同名文件,不覆盖。把下面一段合并进去即可:\n"
              "selectors:\n  %s: '%s'" % (concept, sel.replace("'", "''")))
        return
    print("[pin] 已生成 %s" % path)

    # remember the brand hint so the next bare run picks the profile up
    saved = settings_mod.load(settings_path)
    if not saved.get("brand"):
        saved["brand"] = brand
        saved.setdefault("router_ip", host)
        settings_mod.save(saved, settings_path)
        print("[pin] 已把 brand: %s 记入 router.yaml —— 直接重跑同一条命令即可。"
              % brand)
    else:
        print("[pin] 重跑时加 --brand %s 以启用该 profile。" % brand)


def offer_pin(data: dict, brand: str, model: str, host: str,
              assume_yes: bool = False,
              profile_dir: str = profile_mod.PROFILE_DIR,
              settings_path: str = settings_mod.SETTINGS_PATH) -> None:
    from urllib.parse import urlsplit
    host = urlsplit(host if "://" in host else "//" + host).hostname or host
    verdict = data.get("verdict", {})
    if any(s.get("fired") for s in data.get("strategies", [])):
        return  # a strategy found the control; the failure is elsewhere
    if "card-strip" in str(verdict.get("dial_control", "")):
        return  # a single pin can't drive a card strip; diagnose already said so
    evidence = data.get("artifact", "")

    # 1) a dial control was seen and has a verified-unique selector
    cands, seen = [], set()
    for c in data.get("dial_candidates", []):
        pin = c.get("pin") or {}
        sel = pin.get("recommended")
        if pin.get("available") and sel and sel not in seen:
            seen.add(sel)
            cands.append(c)
    if cands:
        print("\n[pin] 识别失败,但诊断已验证出唯一选择器 —— 可自动生成 profile:")
        for i, c in enumerate(cands, 1):
            print("[pin] %d. %s text=%r label=%r\n        -> %s"
                  % (i, c.get("kind"), c.get("text"), c.get("nearby_label"),
                     c["pin"]["recommended"]))
        choice = _ask_choice(len(cands), "dial_mode_select", assume_yes)
        if choice:
            _write_pin("dial_mode_select", cands[choice - 1]["pin"]["recommended"],
                       brand, model, host, evidence, profile_dir, settings_path)
            return
        # skipped (e.g. every candidate is just a nav link whose text happens to
        # read as a mode) -- fall through and offer the enable-toggle pin too

    # 2) nothing dial-like on the page, but an OFF switch might gate the whole
    #    section (IPv6 pages often render only after their enable switch is ON)
    toggles = [t for t in data.get("toggles", [])
               if t.get("selector") and t.get("state") is not True]
    if not toggles:
        return
    import re as _re
    enable_rx = _re.compile(r"ipv6|enable|启用|开启|使能", _re.I)
    toggles.sort(key=lambda t: 0 if enable_rx.search(t.get("label") or "") else 1)
    print("\n[pin] 页面上没看到拨号控件,但发现了未打开的开关 —— 整个设置区块"
          "可能要等某个开关打开才渲染(如 IPv6 总开关)。可自动 pin 为 "
          "selectors.enable_toggle:")
    for i, t in enumerate(toggles, 1):
        print("[pin] %d. label=%r state=%s\n        -> %s"
              % (i, t.get("label"), t.get("state"), t["selector"]))
    print("[pin] 说明:引擎只在找不到拨号控件时才去拨该开关,绝不会把已开启的"
          "开关点关;写入后重跑,若区块渲染出来即生效。")
    choice = _ask_choice(len(toggles), "enable_toggle", assume_yes)
    if choice:
        _write_pin("enable_toggle", toggles[choice - 1]["selector"],
                   brand, model, host, evidence, profile_dir, settings_path)


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Generic router dial-mode switcher",
        epilog="short form: `python cli.py pppoe` -- IP/passwords come from "
               "router.yaml (create it with `python cli.py setup`)")
    ap.add_argument("command", nargs="?", metavar="mode",
                    help="dial mode (%s) or: setup / diagnose"
                         % "/".join(MODES))
    ap.add_argument("--router-ip", default=None,
                    help="router LAN IP or full URL (default: router.yaml "
                         "value, else 192.168.1.1)")
    ap.add_argument("--user", default=None, help="admin username (if required)")
    ap.add_argument("--pass", dest="password", default=None,
                    help="admin password (default: router.yaml value)")
    ap.add_argument("--mode", choices=MODES,
                    help="target dial mode (same as the positional word)")
    ap.add_argument("--param", action="append", metavar="key=value",
                    help="mode field, e.g. pppoe_user=xxx (repeatable; "
                         "overrides router.yaml params)")
    ap.add_argument("--brand", default=None, help="brand hint for profile match")
    ap.add_argument("--model", default=None, help="model hint for profile match")
    ap.add_argument("--firmware", default="", help="firmware hint")
    ap.add_argument("--no-apply", action="store_true",
                    help="select the mode but don't click Save/Apply")
    ap.add_argument("--apply", action="store_true",
                    help="click Save even if router.yaml sets no_apply: true")
    ap.add_argument("--pin", action="store_true",
                    help="on failure, write the recommended pin profile "
                         "without asking (non-interactive relay runs)")
    ap.add_argument("--diagnose", action="store_true",
                    help="after login+WAN nav, dump a one-shot evidence artifact "
                         "(candidate controls + verified selectors + save-button "
                         "triage) and exit; also auto-written on any failure")

    # environment / browser knobs
    ap.add_argument("--headless", action="store_true")
    ap.add_argument("--chrome-path", default="",
                    help="explicit Chrome/Chromium binary path")
    ap.add_argument("--bundled-chromium", action="store_true",
                    help="use Playwright's bundled chromium instead of channel=chrome")
    ap.add_argument("--browsers-path", default="",
                    help="PLAYWRIGHT_BROWSERS_PATH for offline bundled browsers")
    ap.add_argument("--screenshot-dir", default="")
    args = ap.parse_args(argv)

    # positional word: a dial mode, or a sub-command
    if args.command:
        cmd = args.command.lower()
        if cmd not in COMMANDS:
            ap.error("unknown command %r -- expected one of: %s"
                     % (args.command, ", ".join(COMMANDS)))
        if cmd == "setup":
            return run_setup()
        if cmd == "diagnose":
            args.diagnose = True
        else:
            args.mode = cmd

    saved = settings_mod.load()
    router_ip = args.router_ip or saved.get("router_ip") or "192.168.1.1"
    admin_user = args.user if args.user is not None else str(saved.get("user", "") or "")
    admin_pass = (args.password if args.password is not None
                  else str(saved.get("pass", "") or ""))
    brand = args.brand if args.brand is not None else str(saved.get("brand", "") or "")
    model = args.model if args.model is not None else str(saved.get("model", "") or "")
    no_apply = args.no_apply or (bool(saved.get("no_apply")) and not args.apply)

    url = router_ip
    if not url.startswith("http"):
        url = "http://" + url

    cfg = build_config(args, saved)

    if not args.mode and not args.diagnose:
        ap.error("give a dial mode, e.g. `python cli.py pppoe` "
                 "(or setup / diagnose)")

    prof = profile_mod.match(brand, model, args.firmware)
    if prof:
        print("[cli] using profile: %s" % prof.source)
    else:
        print("[cli] no profile matched -> pure heuristics")

    # diagnose: login, reach the WAN page, dump one evidence artifact, exit.
    # No mode needed -- this is the onboarding / triage path.
    if args.diagnose:
        from engine import diagnose
        with Browser(cfg) as br:
            br.goto(url)
            adapter = RouterAdapter(br.page, config=cfg, profile=prof)
            if not adapter.login(admin_user, admin_pass):
                print("[cli] warning: login may have failed; "
                      "diagnosing the current page anyway")
            adapter.goto_wan_settings()
            adapter._ensure_enabled()
            data = diagnose.run(br.page, cfg.screenshot_dir, label="manual")
            offer_pin(data, brand, model, router_ip, assume_yes=args.pin)
        return 0

    params = merge_params(args.mode, saved.get("params"), _parse_params(args.param))
    if no_apply:
        print("[cli] no-apply: 只切换、不点保存 (use --apply to really save)")

    with Browser(cfg) as br:
        br.goto(url)
        adapter = RouterAdapter(br.page, config=cfg, profile=prof)
        result = adapter.run(args.mode, params,
                             admin_user=admin_user, admin_pass=admin_pass,
                             do_apply=not no_apply)
        # A failing run IS the diagnostic run: dump evidence while the page is
        # still open, so the user need not know --diagnose exists or re-run.
        if not result.success:
            try:
                from engine import diagnose
                data = diagnose.run(br.page, cfg.screenshot_dir, label=args.mode,
                                    to_stdout=False)
                result.diagnostic = data.get("artifact", "")
                print("[cli] run failed -> evidence written to: %s\n%s"
                      % (result.diagnostic, diagnose.render_text(data)))
                offer_pin(data, brand, model, router_ip, assume_yes=args.pin)
            except Exception as exc:
                print("[cli] diagnose failed: %s" % exc)

    print(json.dumps(result.as_dict(), ensure_ascii=False, indent=2))
    return 0 if result.success else 2


if __name__ == "__main__":
    sys.exit(main())
