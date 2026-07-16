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
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from config import Config
from engine.browser import Browser
from engine.adapter import RouterAdapter
from engine.profile import Profile

MOCK_DIR = os.path.join(ROOT, "tests", "mock_router")

# A profile whose `selectors:` overrides drive xiaomi.html -- a mock whose dial
# control / fields / save button are invisible to the heuristics on purpose.
# Proves profile selector overrides are actually wired into the engine.
XIAOMI_PROFILE = Profile(
    brand="xiaomi", model="mock",
    selectors={
        "dial_mode_select": "#xmWan",
        "pppoe_user": "#xmField1",
        "pppoe_pass": "#xmField2",
        "save_button": "#xmSave",
    },
)

# (page, expected detected_via, [modes]) -- index.html is a native <select>,
# custom.html replicates the live Mercusys <div role=combobox> widget.
CASES = [
    ("dynamic", {}),
    ("pppoe", {"pppoe_user": "wan_test", "pppoe_pass": "secret123"}),
    ("l2tp", {"vpn_server": "10.0.0.1", "vpn_user": "u", "vpn_pass": "p"}),
    ("pptp", {"vpn_server": "10.0.0.2", "vpn_user": "u2", "vpn_pass": "p2"}),
    ("ipv6", {}),
]

PAGES = [
    ("index.html", "select", ["dynamic", "pppoe", "l2tp", "pptp", "ipv6"]),
    ("custom.html", "combobox", ["dynamic", "pppoe", "l2tp", "pptp"]),
    # Tenda-style: role-less <div class="v-select"> (no <select>, no
    # role=combobox, no unique selector; class shared with ISP/MTU/DNS decoys).
    ("tenda.html", "widget", ["dynamic", "pppoe", "l2tp", "pptp"]),
]


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
    for page, expect_via, modes in PAGES:
        print("\n=== %s (expect detected_via=%s) ===" % (page, expect_via))
        for mode, params in CASES:
            if mode not in modes:
                continue
            toast = ""
            with Browser(cfg) as br:
                br.goto("http://127.0.0.1:%d/%s" % (port, page))
                adapter = RouterAdapter(br.page, config=cfg)
                res = adapter.run(mode, params, admin_pass="admin123")
                if page == "tenda.html":
                    try:
                        toast = br.page.locator("#toast").inner_text().strip()
                    except Exception:
                        toast = ""
            ok = (res.success and res.detected_via == expect_via
                  and (mode != "pppoe" or "pppoe_user" in res.filled))
            if page == "tenda.html":
                # the apply button is "Connect"; must be found AND must not have
                # hit the "Disconnect" decoy.
                ok = ok and res.applied and toast.lower().startswith("connected")
            status = "PASS" if ok else "FAIL"
            print("[%s] mode=%-8s via=%-8s read_back=%-16r filled=%s applied=%s"
                  % (status, mode, res.detected_via, res.read_back, res.filled,
                     res.applied))
            if not ok:
                print("        message: %s" % res.message)
            passed += ok
            failed += not ok

    # --- profile selector-override path (xiaomi.html, heuristics-hostile) ---
    print("\n=== xiaomi.html (profile selectors override heuristics) ===")
    for mode, params in CASES:
        if mode not in ("dynamic", "pppoe"):
            continue  # two modes are enough to exercise the override path
        with Browser(cfg) as br:
            br.goto("http://127.0.0.1:%d/xiaomi.html" % port)
            adapter = RouterAdapter(br.page, config=cfg, profile=XIAOMI_PROFILE)
            res = adapter.run(mode, params, admin_pass="admin123")
        ok = (res.success and res.detected_via == "combobox"
              and (mode != "pppoe"
                   or {"pppoe_user", "pppoe_pass"} <= set(res.filled)))
        status = "PASS" if ok else "FAIL"
        print("[%s] mode=%-8s via=%-8s read_back=%-10r filled=%s applied=%s"
              % (status, mode, res.detected_via, res.read_back, res.filled,
                 res.applied))
        if not ok:
            print("        message: %s" % res.message)
        passed += ok
        failed += not ok

    # --- beautified hidden <select> (Xiaomi-style) driven by a pinned selector ---
    print("\n=== beautify.html (hidden native <select> via selectors) ===")
    beautify_profile = Profile(brand="mi", model="beauty",
                               selectors={"dial_mode_select": "#wantypeselect"})
    for mode in ("dynamic", "pppoe", "static"):
        with Browser(cfg) as br:
            br.goto("http://127.0.0.1:%d/beautify.html" % port)
            adapter = RouterAdapter(br.page, config=cfg, profile=beautify_profile)
            res = adapter.run(mode, {"pppoe_user": "u", "pppoe_pass": "p"},
                              admin_pass="admin123")
        ok = res.success and res.detected_via == "select"
        status = "PASS" if ok else "FAIL"
        print("[%s] mode=%-8s via=%-8s read_back=%r"
              % (status, mode, res.detected_via, res.read_back))
        if not ok:
            print("        message: %s" % res.message)
        passed += ok
        failed += not ok

    # --- profile mode_labels on the combobox/widget path -----------------------
    # A pinned exact label must beat the synonym tables (parity with the native
    # <select> path).  "ipv6 -> L2TP" is semantically odd on purpose: it proves
    # the MECHANISM (the pin decides which option is clicked and the read-back
    # accepts the pinned wording), which is what Tenda's IPv6 page needs
    # (options are PPPoEv6/DHCPv6 flavors, not a literal "IPv6").
    print("\n=== tenda.html (mode_labels pin drives the widget path) ===")
    pin_profile = Profile(brand="tenda", model="pin",
                          mode_labels={"ipv6": "L2TP"})
    with Browser(cfg) as br:
        br.goto("http://127.0.0.1:%d/tenda.html" % port)
        adapter = RouterAdapter(br.page, config=cfg, profile=pin_profile)
        res = adapter.run("ipv6", {}, admin_pass="admin123")
    ok = (res.success and res.detected_via == "widget"
          and res.read_back.strip() == "L2TP")
    status = "PASS" if ok else "FAIL"
    print("[%s] mode=ipv6 via=%-8s read_back=%r applied=%s"
          % (status, res.detected_via, res.read_back, res.applied))
    if not ok:
        print("        message: %s" % res.message)
    passed += ok
    failed += not ok

    # --- Tenda-style IPv6 page: enable switch gates the section ---------------
    # The whole IPv6 WAN block (dropdown + Save) only renders once the IPv6
    # switch (a role-less div, class-modifier state) is ON.  The profile pins
    # enable_toggle; the engine must flip it, then drive the v6-flavor dropdown
    # via mode_labels.  A LAN radio labeled "DHCPv6" decoys the pinned-option
    # locator (popup option must win).  PPPoEv6 additionally proves explicit
    # --param values are filled even though mode "ipv6" requires none.
    print("\n=== tenda_ipv6.html (enable_toggle + v6 flavor via mode_labels) ===")
    for flavor, extra, want_filled in (
            ("DHCPv6", {}, []),
            ("PPPoEv6", {"pppoe_user": "u6", "pppoe_pass": "p6"},
             ["pppoe_user", "pppoe_pass"])):
        ipv6_profile = Profile(
            brand="tenda", model="ipv6mock",
            wan_path=["More", "IPv6"],
            selectors={"enable_toggle": "div.v-switch"},
            mode_labels={"ipv6": flavor},
        )
        toast = ""
        with Browser(cfg) as br:
            br.goto("http://127.0.0.1:%d/tenda_ipv6.html" % port)
            adapter = RouterAdapter(br.page, config=cfg, profile=ipv6_profile)
            res = adapter.run("ipv6", extra, admin_pass="admin123")
            try:
                toast = br.page.locator("#toast").inner_text().strip()
            except Exception:
                toast = ""
        ok = (res.success and res.detected_via == "widget"
              and res.read_back.strip() == flavor and res.applied
              and toast == "Saved: %s" % flavor
              and set(want_filled) <= set(res.filled))
        status = "PASS" if ok else "FAIL"
        print("[%s] flavor=%-8s via=%-8s read_back=%r filled=%s toast=%r"
              % (status, flavor, res.detected_via, res.read_back, res.filled,
                 toast))
        if not ok:
            print("        message: %s" % res.message)
        passed += ok
        failed += not ok

    # --- false-positive guard (noctrl.html: mode text but no real control) ---
    print("\n=== noctrl.html (must NOT report a false success) ===")
    with Browser(cfg) as br:
        br.goto("http://127.0.0.1:%d/noctrl.html" % port)
        adapter = RouterAdapter(br.page, config=cfg)
        res = adapter.run("dynamic", {}, admin_pass="admin123")
    ok = (not res.success) and res.needs_recording and res.detected_via == ""
    status = "PASS" if ok else "FAIL"
    print("[%s] success=%s needs_recording=%s via=%r"
          % (status, res.success, res.needs_recording, res.detected_via))
    if not ok:
        print("        message: %s" % res.message)
    passed += ok
    failed += not ok

    # --- false-positive guard (cardstrip.html: a row of clickable mode cards) ---
    # Every card's text reads as a dial mode, so the value-text widget heuristic
    # would grab the first card ("Dynamic IP"), never click, and report a
    # zero-interaction success for mode=dynamic.  The engine must DECLINE this
    # shape (it's an option list, not a value display) -> needs_recording.
    print("\n=== cardstrip.html (card strip must NOT report a false success) ===")
    with Browser(cfg) as br:
        br.goto("http://127.0.0.1:%d/cardstrip.html" % port)
        adapter = RouterAdapter(br.page, config=cfg)
        res = adapter.run("dynamic", {}, admin_pass="admin123")
    ok = (not res.success) and res.needs_recording and res.detected_via == ""
    status = "PASS" if ok else "FAIL"
    print("[%s] success=%s needs_recording=%s via=%r"
          % (status, res.success, res.needs_recording, res.detected_via))
    if not ok:
        print("        message: %s" % res.message)
    passed += ok
    failed += not ok

    # --- CLI conveniences (offline, no browser) -------------------------------
    # router.yaml settings, per-mode param filtering, and the auto-pin profile
    # writer that replaces hand-editing profiles/*.yaml after a failed run.
    print("\n=== cli conveniences (router.yaml / merge_params / auto-pin) ===")
    import tempfile
    import settings as settings_mod
    from cli import merge_params
    from engine import profile as profile_lib

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

        # auto-pin writes a profile that load/match actually picks up
        sel = 'div.v-form-item:has-text("Internet Connection Type") div.v-select'
        ppath = profile_lib.write_pin("auto_192_168_0_1", "",
                                      {"dial_mode_select": sel}, profile_dir=td)
        prof = profile_lib.match(brand="auto_192_168_0_1", profile_dir=td)
        ok = (ppath is not None and prof is not None
              and prof.selector("dial_mode_select") == sel)
        print("[%s] write_pin -> match: %s" % ("PASS" if ok else "FAIL", ppath))
        passed += ok
        failed += not ok

        # never clobber an existing (possibly hand-tuned) profile
        again = profile_lib.write_pin("auto_192_168_0_1", "",
                                      {"dial_mode_select": "#other"},
                                      profile_dir=td)
        still = profile_lib.match(brand="auto_192_168_0_1", profile_dir=td)
        ok = again is None and still.selector("dial_mode_select") == sel
        print("[%s] write_pin refuses overwrite" % ("PASS" if ok else "FAIL"))
        passed += ok
        failed += not ok

    httpd.shutdown()
    print("\n%d passed, %d failed" % (passed, failed))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
