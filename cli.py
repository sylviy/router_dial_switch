"""Command-line entry point.

Daily use (after one-time `python cli.py setup` wrote router.yaml):

    python cli.py pppoe          # mode is just the first word
    python cli.py dynamic
    python cli.py l2tp

Everything else (IP, passwords, per-mode credentials) comes from router.yaml;
any flag still overrides it.  Long form remains supported:

    python cli.py --router-ip 192.168.1.1 --pass admin123 \
        --mode pppoe --param pppoe_user=test --param pppoe_pass=test123

When a run fails because the dial control wasn't recognised, the diagnose pass
runs automatically and -- new -- if it verified a unique selector, the CLI
offers to write the pin profile for you (no hand-edited YAML):

    [pin] 1. widget-leaf text='PPPoE' label='Internet Connection Type'
    write profiles/auto_192_168_0_1.yaml with candidate 1? [Y/n]

Onboard a stubborn model by recording a manual click-through:

    python cli.py record --router-ip 192.168.1.1 --brand acme --model r1
"""
from __future__ import annotations

import argparse
import json
import sys

import settings as settings_mod
from config import Config
from engine.browser import Browser
from engine.adapter import RouterAdapter, MODE_REQUIRED_FIELDS
from engine import profile as profile_mod

MODES = ["dynamic", "static", "pppoe", "l2tp", "pptp", "ipv6"]
COMMANDS = MODES + ["setup", "record", "diagnose"]


def _parse_params(pairs):
    out = {}
    for item in pairs or []:
        if "=" not in item:
            raise SystemExit("bad --param '%s' (expected key=value)" % item)
        k, v = item.split("=", 1)
        out[k.strip()] = v
    return out


def merge_params(mode: str, saved: dict, explicit: dict) -> dict:
    """Params for this run: router.yaml credentials are picked *per mode*
    (only the fields the mode needs, so PPPoE creds stored in router.yaml
    don't leak into a dynamic/ipv6 run), while an explicit --param is user
    intent and always passes through."""
    out = {}
    needed = MODE_REQUIRED_FIELDS.get(mode, [])
    for k, v in (saved or {}).items():
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
    print("-- 拨号凭据,只在对应模式时使用;留空跳过 --")
    for key, label in (("pppoe_user", "宽带账号 (pppoe_user)"),
                       ("pppoe_pass", "宽带密码 (pppoe_pass)"),
                       ("vpn_server", "L2TP/PPTP 服务器 (vpn_server)"),
                       ("vpn_user", "VPN 用户名 (vpn_user)"),
                       ("vpn_pass", "VPN 密码 (vpn_pass)")):
        cur = str(params.get(key, "") or "")
        val = input("%s%s: " % (label, (" [%s]" % cur) if cur else "")).strip()
        if val or cur:
            params[key] = val or cur
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
# so nobody has to read the JSON artifact and hand-write YAML.
# ---------------------------------------------------------------------------
def offer_pin(data: dict, brand: str, model: str, host: str,
              assume_yes: bool = False) -> None:
    from urllib.parse import urlsplit
    host = urlsplit(host if "://" in host else "//" + host).hostname or host
    verdict = data.get("verdict", {})
    if any(s.get("fired") for s in data.get("strategies", [])):
        return  # a strategy found the control; the failure is elsewhere
    if "card-strip" in str(verdict.get("dial_control", "")):
        return  # a single pin can't drive a card strip; diagnose already said so
    cands, seen = [], set()
    for c in data.get("dial_candidates", []):
        pin = c.get("pin") or {}
        sel = pin.get("recommended")
        if pin.get("available") and sel and sel not in seen:
            seen.add(sel)
            cands.append(c)
    if not cands:
        return

    print("\n[pin] 识别失败,但诊断已验证出唯一选择器 —— 可自动生成 profile:")
    for i, c in enumerate(cands, 1):
        print("[pin] %d. %s text=%r label=%r\n        -> %s"
              % (i, c.get("kind"), c.get("text"), c.get("nearby_label"),
                 c["pin"]["recommended"]))

    choice = 1
    if sys.stdin.isatty() and not assume_yes:
        raw = input("[pin] 写入哪一个?回车=1,数字选择,n=跳过: ").strip().lower()
        if raw in ("n", "no"):
            print("[pin] 跳过;推荐选择器已在上方,可手动填入 "
                  "profiles/*.yaml 的 selectors.dial_mode_select。")
            return
        if raw.isdigit() and 1 <= int(raw) <= len(cands):
            choice = int(raw)
    elif len(cands) > 1 and not assume_yes:
        print("[pin] 非交互环境且候选不止一个,不自动写入。重跑时加 --pin 采用第 1 个,"
              "或手动挑选上面的选择器。")
        return

    sel = cands[choice - 1]["pin"]["recommended"]
    brand = brand or "auto_" + profile_mod._slug(host)
    path = profile_mod.write_pin(brand, model,
                                 {"dial_mode_select": sel},
                                 evidence=data.get("artifact", ""))
    if path is None:
        print("[pin] profiles/ 下已有同名文件,不覆盖。把下面一段合并进去即可:\n"
              "selectors:\n  dial_mode_select: '%s'" % sel.replace("'", "''"))
        return
    print("[pin] 已生成 %s" % path)

    # remember the brand hint so the next bare run picks the profile up
    saved = settings_mod.load()
    if not saved.get("brand"):
        saved["brand"] = brand
        saved.setdefault("router_ip", host)
        settings_mod.save(saved)
        print("[pin] 已把 brand: %s 记入 router.yaml —— 直接重跑同一条命令即可。"
              % brand)
    else:
        print("[pin] 重跑时加 --brand %s 以启用该 profile。" % brand)


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Generic router dial-mode switcher",
        epilog="short form: `python cli.py pppoe` -- IP/passwords come from "
               "router.yaml (create it with `python cli.py setup`)")
    ap.add_argument("command", nargs="?", metavar="mode",
                    help="dial mode (%s) or: setup / record / diagnose"
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
    ap.add_argument("--record", action="store_true",
                    help="record mode: manual click-through -> HAR + profile draft")
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
        if cmd == "record":
            args.record = True
        elif cmd == "diagnose":
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

    if args.record:
        from engine.recorder import record
        record(url, brand=brand or "unknown", model=model or "model", config=cfg)
        return 0

    if not args.mode and not args.diagnose:
        ap.error("give a dial mode, e.g. `python cli.py pppoe` "
                 "(or setup / record / diagnose)")

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
