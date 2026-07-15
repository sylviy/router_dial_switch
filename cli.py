"""Command-line entry point.

Examples
--------
Switch a router (heuristics only) to PPPoE and read back the result:

    python cli.py --router-ip 192.168.1.1 --pass admin123 \
        --mode pppoe --param pppoe_user=test --param pppoe_pass=test123

Onboard a new brand by recording a manual click-through:

    python cli.py --record --router-ip 192.168.1.1 --brand acme --model r1
"""
from __future__ import annotations

import argparse
import json
import sys

from config import Config
from engine.browser import Browser
from engine.adapter import RouterAdapter
from engine import profile as profile_mod


def _parse_params(pairs):
    out = {}
    for item in pairs or []:
        if "=" not in item:
            raise SystemExit("bad --param '%s' (expected key=value)" % item)
        k, v = item.split("=", 1)
        out[k.strip()] = v
    return out


def build_config(args) -> Config:
    cfg = Config()
    cfg.headless = args.headless
    if args.chrome_path:
        cfg.executable_path = args.chrome_path
    if args.bundled_chromium:
        cfg.channel = None
    if args.browsers_path:
        cfg.browsers_path = args.browsers_path
    if args.screenshot_dir:
        cfg.screenshot_dir = args.screenshot_dir
    return cfg


def main(argv=None):
    ap = argparse.ArgumentParser(description="Generic router dial-mode switcher")
    ap.add_argument("--router-ip", default="192.168.1.1",
                    help="router LAN IP or full URL (default 192.168.1.1)")
    ap.add_argument("--user", default="", help="admin username (if required)")
    ap.add_argument("--pass", dest="password", default="",
                    help="admin password")
    ap.add_argument("--mode", choices=["dynamic", "static", "pppoe", "l2tp",
                                       "pptp", "ipv6"],
                    help="target dial mode")
    ap.add_argument("--param", action="append", metavar="key=value",
                    help="mode field, e.g. pppoe_user=xxx (repeatable)")
    ap.add_argument("--brand", default="", help="brand hint for profile match")
    ap.add_argument("--model", default="", help="model hint for profile match")
    ap.add_argument("--firmware", default="", help="firmware hint")
    ap.add_argument("--no-apply", action="store_true",
                    help="select the mode but don't click Save/Apply")
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

    url = args.router_ip
    if not url.startswith("http"):
        url = "http://" + url

    cfg = build_config(args)

    if args.record:
        from engine.recorder import record
        record(url, brand=args.brand or "unknown",
               model=args.model or "model", config=cfg)
        return 0

    prof = profile_mod.match(args.brand, args.model, args.firmware)
    if prof:
        print("[cli] using profile: %s" % prof.source)
    else:
        print("[cli] no profile matched -> pure heuristics")

    # --diagnose: login, reach the WAN page, dump one evidence artifact, exit.
    # No --mode needed -- this is the onboarding / triage path.
    if args.diagnose:
        from engine import diagnose
        with Browser(cfg) as br:
            br.goto(url)
            adapter = RouterAdapter(br.page, config=cfg, profile=prof)
            if not adapter.login(args.user, args.password):
                print("[cli] warning: login may have failed; "
                      "diagnosing the current page anyway")
            adapter.goto_wan_settings()
            adapter._ensure_enabled()
            diagnose.run(br.page, cfg.screenshot_dir, label="manual")
        return 0

    if not args.mode:
        ap.error("--mode is required unless --record or --diagnose is used")

    params = _parse_params(args.param)

    with Browser(cfg) as br:
        br.goto(url)
        adapter = RouterAdapter(br.page, config=cfg, profile=prof)
        result = adapter.run(args.mode, params,
                             admin_user=args.user, admin_pass=args.password,
                             do_apply=not args.no_apply)
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
            except Exception as exc:
                print("[cli] diagnose failed: %s" % exc)

    print(json.dumps(result.as_dict(), ensure_ascii=False, indent=2))
    return 0 if result.success else 2


if __name__ == "__main__":
    sys.exit(main())
