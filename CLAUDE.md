# CLAUDE.md — router_dial_switch

Context for any Claude session (terminal Claude Code, VS Code, or app) opening
this repo. Read this first, then `README.md`.

## What this is
Automation to **switch a router's WAN dial mode** (dynamic / PPPoE / L2TP /
PPTP / IPv6) via its web UI, so we can compare our DUT against competitor
routers we can't drive by HTTP API. Built with **Playwright (Python)**.

**Delivery shape (pivoted 2026-07-16, mentor's direction — outcome over
generality):** one self-contained script per model, `models/<Brand>_<Model>.py`
(all of that device's FACTS: login, nav path, control selector, per-mode
wording, apply button) + a tiny shared runtime `models/_driver.py`. Colleagues
run `python models/Tenda_AX3000.py pppoe` — no engine knowledge needed. Target
brands are just the group's bench: **Cudy / Tenda / Buffalo / Huawei** (done:
Tenda, Mercusys). The heuristics engine + `cli.py diagnose` are demoted to the
**adaptation toolbox**, and the adaptation methodology is codified as a skill
(`.claude/skills/adapt-router-model/SKILL.md`) so ANY Claude session can
produce a new model script from a diagnose artifact. Don't build further
"universal tool" surface; invest in per-model scripts + the skill.

**Current scope:** confirm the dial control is *located and changed* (read-back
== target). It does NOT verify WAN actually dials up — the existing
single-machine perf scripts own connectivity/throughput and plug in later via a
`verify_hook`.

## How it fits the test workflow
The tool is ONE step ("change the dial way"). The full run is a loop:
`set dynamic → perf-test → set pppoe → perf-test → set l2tp → … `. The perf test
is the existing single-machine scripts. See `examples/run_test_matrix.py` for
the orchestrator skeleton (switch = this tool, perf = placeholder to wire up).

## Architecture (how the files work together)
- `models/` — **the delivery layer.** `<Brand>_<Model>.py` = a FACTS dict
  (explicit selectors/wordings, zero runtime guessing) + `run_cli(FACTS)`.
  `_driver.py` is the only click logic (login → nav → enable_toggle guard →
  set mode → read-back → fill → apply); it inherits the hard-won rules:
  success ONLY on real read-back == target wording (whole-text or exact
  per-line match — never substring, "PPPoEv6" must not pass for "pppoe"),
  enable_toggle never touched while a dial control is visible, popup options
  matched via option-shaped containers first (`[role='option'], [class*='opt']`)
  so a same-text decoy elsewhere on the page can't be clicked, apply only with
  `--apply`. `dial.kind`: select | dropdown | radio; `dial.value` optional
  read-back sub-selector; `mode_overrides` swaps whole keys per mode (Tenda
  ipv6 page). Facts lines not yet re-verified on the physical device are
  commented `[待真机复核]`. `verify_hook(page, result)` is the future WAN-up
  integration point. Creds come from router.yaml via `cli.merge_params`.
- `.claude/skills/adapt-router-model/SKILL.md` — the onboarding methodology as
  a skill: diagnose artifact → FACTS mapping table, selector cookbook, the
  four iron rules, verification checklist. New models go through this, never
  through guessed DOM.
- `engine/heuristics.py` — **core of the adaptation toolbox.** Multilingual keyword dicts + semantic
  locators. Finds the dial control three ways: native `<select>`; a custom
  `<div role="combobox">` (Mercusys/TP-Link); or a **role-less** custom widget
  with no id/name/role whose class repeats across fields (Tenda's Vue
  `<div class="v-select">`) via `find_dial_mode_widget` — an in-page scan that
  tags the one field whose *value* text reads as a dial mode. Edit here = all
  brands benefit.
- `engine/adapter.py` — orchestrates: login → WAN nav → set mode → fill params →
  read-back → apply. Tries heuristics first, uses profile overrides when present.
- `engine/profile.py` + `profiles/*.yaml` — optional per-model hints
  (wan_path / selector overrides / mode_labels). One profile per model, covers
  all its dial modes. `profiles/_example.yaml` is an annotated template.
  **`selectors:` overrides are wired** (adapter: `_profile_sel` /
  `_locate_by_selector` / `_profile_dial_control`): a profile CSS selector wins
  over heuristics, falling back when absent, for login_user/login_pass/
  login_button, dial_mode_select (native <select> or custom <div>, classified by
  tag), pppoe_user/pppoe_pass/vpn_*, save_button. This is the main lever for
  divergent UIs (e.g. Xiaomi). Covered by the xiaomi.html smoke case.
- `engine/browser.py` — Playwright launch (default `channel="chrome"`).
- `engine/recorder.py` — `--record`: manual click-through → HAR + profile draft.
- `engine/diagnose.py` — **onboarding/triage.** One-shot evidence dump for an
  unknown UI: all-frames inventory, per-strategy fired/why, dial-control
  candidates each with **verified** selectors (JS proposes, Python counts via
  `frame.locator().count()` — the same engine used at runtime — so `unique:true`
  is real, and `:has-text()` label-anchored selectors are validated), and every
  clickable flagged against the save-button vocab. Vocab is imported from
  `heuristics`, never re-copied. `--diagnose` runs it on demand; a failing
  `run()` writes the same artifact automatically. `adapter._diag()` delegates to
  its `summarize()` (all-frames, incl. a save-button-seen flag).
- `dial_modes/*.yaml` — which params each mode needs.
- `cli.py` — entry point. Short UX: positional mode (`python cli.py pppoe`),
  `setup` wizard, and **auto-pin** — on a failed run, if diagnose verified a
  unique selector, the CLI offers (TTY prompt; `--pin` = non-interactive yes)
  to write `profiles/auto_<ip>.yaml` + remember `brand:` in router.yaml, so
  nobody hand-writes YAML for the common "control not recognised" case.
  Two concepts are offered: `dial_mode_select` (control seen, pinnable), and —
  when NOTHING dial-like is on the page but diagnose saw OFF switches —
  `enable_toggle` (the TP-Link/Tenda IPv6 shape: section renders only after
  its switch is ON; candidates sorted so ipv6/enable-labeled ones come first).
  Skipping the dial offer falls through to the toggle offer (nav links whose
  text reads as a mode can pollute the dial candidates). `write_pin`
  (profile.py) never overwrites an existing profile. Card strips are excluded
  (a single pin can't drive them). `tools/find_enable_toggle.js` is the
  console-paste equivalent for finding the switch by hand (verifies plain-CSS
  counts in-page; defers Playwright-syntax cases to `cli.py diagnose`).
- `settings.py` — `router.yaml` local defaults (IP/passwords/per-mode creds;
  git-ignored). CLI flags override; saved creds are filtered per mode
  (`cli.merge_params`) so PPPoE creds never leak into a dynamic run. Wizard
  defaults `no_apply: true`; `--apply` overrides.
- `tests/smoke_test.py` — offline e2e vs mock pages.

## Run / verify
```bash
# offline logic test (no router needed) — must stay green:
python tests/smoke_test.py            # 35/35 pass expected

# daily use on an adapted model (run on a machine ON the router's LAN):
python cli.py setup                   # one time -> router.yaml (git-ignored)
python models/Tenda_AX3000.py pppoe   # add --apply to really save
# adaptation phase (new/unscripted device): heuristics + evidence dump
python cli.py pppoe                   # heuristic attempt
python cli.py diagnose                # -> artifacts/diagnose_*.json
# long form (no router.yaml needed):
python cli.py --router-ip 192.168.1.1 --pass <pw> --mode pppoe \
    --param pppoe_user=x --param pppoe_pass=y --no-apply   # --no-apply = don't click Save
```

## Environment
- Python 3.8+ (isolated in-folder venv/embeddable; keep off the company 3.7).
- Chrome via `channel="chrome"` (offline). Windows bench: locked Chrome 114 +
  chromedriver 114. `pip install -r requirements.txt` (offline: pip download →
  `--no-index --find-links`).
- Cross-platform: code is OS-independent; only the browser binary differs.

## Gotchas (learned the hard way)
- The repo path contains `[Tool]`, a glob character class. Use `glob.escape()`
  in Python and quote paths in shell, or matching silently returns nothing.
  (Already fixed in `profile.py`.)
- A network-sandboxed environment can reach the internet but NOT the router's
  LAN. To drive a real router, run where Chrome can reach it (your machine), or
  via the Claude-in-Chrome extension.
- Custom React comboboxes: click the option via a DOM locator (Playwright
  dispatches trusted events); raw OS-level pixel clicks on portaled lists are
  unreliable.
- **Detection must WAIT for the SPA to render.** `first_visible` in
  `heuristics.py` uses `locator.count()`/`is_visible()`, which take an *instant*
  snapshot — Playwright's auto-wait only applies to click/fill/wait_for, not
  count(). Static mock pages render instantly so smoke passes, but on a real
  React router the control mounts after login/route changes; a one-shot scan
  runs too early → "no dial-mode control located" / needs_recording. The adapter
  now polls via `_search_wait` / `_find_dial_control` (waiting lives in the
  adapter; heuristics stay pure locators). Keep new detection paths behind those
  waiters, not a bare `_search`. A `_diag()` note is appended to the failure
  message ("saw N <select>, M role=combobox at <url>") for real-device triage.
  This bit `login()` too: it scanned for the password field once, before the
  login SPA had rendered it, so it silently skipped login and Chrome just sat on
  `#/login`. `login()` now `_search_wait`s for the password field, then
  `_wait_logged_in()` confirms the login screen is gone (no password field);
  `run()` short-circuits with a real "login failed" message instead of a
  misleading "no dial-mode control". This router (Mercusys) also allows only ONE
  web session — a second logged-in client can bounce the tool back to login.

- **Never report success without a real read-back.** The radio fallback used to
  latch onto plain mode *text* (via `find_dial_mode_radio`'s get_by_text), click
  it (a no-op), and — because `is_checked()` throws on a non-radio — assume the
  click "took", yielding `success:true` while nothing changed (seen live on
  Xiaomi's 上网设置). The radio path now trusts ONLY a genuine radio's
  `is_checked()`; an unverifiable text match reports `needs_recording` with
  "pin selectors.dial_mode_select". Bias: a false negative (asks for a selector
  it might not have needed) is far safer than a false positive. `noctrl.html`
  smoke-tests this. select/combobox paths read back the real control state and
  are trustworthy.
- **The widget (value-is-a-mode) path must DECLINE a card strip.** A row of
  clickable cards (`Dynamic | Static | PPPoE | L2TP`) makes *every* card a
  "mode leaf"; the scan would tag the first ("Dynamic IP"), and
  `_select_via_combobox` sees "trigger text already == target" → returns True
  **without clicking** → `success:true` with zero interaction (the Xiaomi
  false-positive reborn on the newest path, and it fires on the common `dynamic`
  target). `find_dial_mode_widget` now declines when any parent holds ≥2
  distinct-mode leaves (an option list, not a value display). `cardstrip.html`
  smoke-tests this. There is no strategy that *handles* a card strip yet — see
  Validated.
- **Keep dial-mode synonyms specific to the connection TYPE.** "自动配置"/"手动配置"
  were in the dynamic/static lists but on Xiaomi those are the *IP-config* and
  *IPv6 DNS* sub-radios inside a PPPoE form. The radio fallback matched a real
  (wrong) radio, is_checked() passed, and it falsely succeeded — then, run
  without --no-apply, clicked 应用 on a live home router. Fixed by removing those
  greedy synonyms. The real Xiaomi connection-type control is a custom `<div>`
  dropdown (no role, no <select>) → it MUST be pinned via
  `selectors.dial_mode_select`; heuristics correctly report needs_recording
  otherwise.

## Validated
Live on a **Mercusys BE3600** (2026-07-11): custom `<div>`-combobox connection
type; Save button; L2TP fields Username/Password/"VPN Server IP/Domain Name";
IPv6 lives under Advanced→IPv6 (not the main list). See
`profiles/mercusys_be3600.yaml`.

**Tenda** (2026-07-15, 192.168.0.1, Vue UI): connection type is a role-less
`<div class="v-select">` — NO `<select>`, NO `role`, NO id/name, and the class
repeats across 5 fields (ISP Type / Internet Connection Type / MTU / MAC Clone /
DNS), so there's no unique selector. Detection + selection confirmed live (the
control switched to Dynamic IP); the apply button is **"Connect"** (not
Save/Apply), so it went unclicked until "connect"/"连接" was added to
`BUTTON_SAVE_SYNONYMS` — guarded by `BUTTON_SAVE_EXCLUDE` (disconnect/断开) so the
substring "connect" can't grab a "Disconnect" button. Covered by `tenda.html`
smoke (detected_via=widget; asserts the "Connect" button, not "Disconnect", is
clicked). NOTE: live re-validation of the "Connect" apply on the physical device
still pending (screenshot pre-dates the fix); Tenda also enforces a short login
session timeout.

**Tenda IPv6 page** (2026-07-15, live nav confirmed; rest offline-validated via
`tenda_ipv6.html`): IPv6 is NOT in the main connection-type list — it's a
separate page (More → IPv6) whose entire WAN block only renders once the IPv6
*enable switch* (a role-less div, class-modifier state) is ON. New profile
concept `selectors.enable_toggle` flips it — guarded: never touched while a
dial control is visible, so it can't switch an enabled page off. The page's
connection types are v6 *flavors* (PPPoEv6/DHCPv6/…): those classify as
canonical `ipv6` (match_mode checks ipv6 before pppoe/dynamic so the
"pppoe"/"dhcp" substrings can't misclassify), and a specific flavor is chosen
via `mode_labels` — now honored on the combobox/widget path too, with read-back
accepting the pinned wording. Explicit `--param` values are filled even when
the mode requires none (PPPoEv6 creds under mode ipv6). See
`profiles/tenda_ipv6.yaml` (WARNING inside: pass `--brand tenda --model ipv6`
only for IPv6 runs; IPv4 runs must pass no --brand or loose matching drags them
to the IPv6 page). Hard-learned in the mock: a leaf only counts for the widget
scan if a connection-type label sits in a *form-row-sized* ancestor (<120
chars) — otherwise the sidebar "IPv6" nav link and the "IPv6" switch label
masquerade as the control (both exist on the real page), hijacking detection
and defeating the enable_toggle safety check.

**Tenda was always pinnable (we got this wrong at the time).** We concluded "no
unique selector exists → the profile escape hatch is unusable" because plain CSS
`div.v-select` matches 5 fields. But `_locate_by_selector` uses `frame.locator()`
— Playwright's selector engine — which supports `:has-text()`. A label-anchored
`selectors.dial_mode_select: 'div.v-form-item:has-text("Internet Connection Type")
div.v-select'` is unique and stable. `--diagnose` now emits exactly this,
pre-verified. Only plain-CSS pinning was impossible; Playwright-syntax pinning
was always available. `_example.yaml` documents it.

## Known gaps (shapes the current strategies can't drive)
- **Card strip / segmented / radio-card picker** (no `<select>`, no role, no
  popup; selection is a CSS class on one card). The widget path *declines* it
  safely (see gotcha above) but nothing *handles* it — needs a new
  "selected-among-siblings" heuristic (read `aria-checked`/`.active`/`.selected`,
  read back by selectedness not text presence). `--diagnose` names it precisely.
  Deferred until a real device shows up (don't guess its DOM).
- **Widget whose value text isn't a mode word** (shows "Connected"/an icon/a
  code): the widget scan has no signal; pin is the only route.
- **Save-then-confirm modal**, **multi-step wizard**, **closed shadow roots**,
  **canvas UIs**: out of scope for this change set; `--diagnose` reports what it
  can (open shadow roots, readonly-input mode values) so the gap is visible.

## Next steps
- Re-verify on the bench the `[待真机复核]` lines in `models/Tenda_AX3000.py`
  and `models/Mercusys_BE3600.py` (field selectors, apply click, login button).
- Produce `models/` scripts for the remaining group brands — Cudy, Buffalo,
  Huawei — via the adapt-router-model skill (needs one `cli.py diagnose` run
  per device; never guess their DOM).
- Wire `examples/run_test_matrix.py` `run_perf_tests()`/`wait_wan_up()` to the
  real single-machine scripts (or plug them into `_driver.run(verify_hook=...)`).
- Mercusys IPv6 (Advanced→IPv6): diagnose first, then add a `mode_overrides`
  block to its model script.
- WLAN 2.4G/5G switching later.
