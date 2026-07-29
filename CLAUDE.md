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
Tenda, Mercusys, Cudy). **The heuristics engine was DELETED 2026-07-28** (user:
"for the testers, the simpler the better") — `engine/adapter.py`,
`heuristics.py`, `diagnose.py`, `profile.py`, `profiles/*.yaml`,
`dial_modes/*.yaml` and `cli.py`, ~2300 lines, all gone. They were the earlier
"one tool drives every brand" route, and they left the repo with TWO competing
"profile" concepts (`models/*.py` FACTS vs `profiles/*.yaml`), which was the
real source of the perceived complexity. A new model is adapted by connecting
Claude to the live device (Claude in Chrome) and following the skill
(`.claude/skills/adapt-router-model/SKILL.md`). Don't rebuild a "universal
tool" surface; invest in per-model scripts + the skill.

**Current scope:** a model script confirms the dial control is *located and
changed* (read-back == target). WAN-up + throughput belong to the full-round
runner (`run_matrix.py` / `matrix/` — see next section); the legacy
single-machine perf script is merged there, no longer a separate future hook.

## How it fits the test workflow
The dial switch is ONE step ("change the dial way"). The full run is a loop:
`set dynamic → perf-test → set pppoe → perf-test → set l2tp → … `. That loop is
now a real command — `run_matrix.py` (package `matrix/`) — which stitches this
tool (web-UI switching, works on competitor routers) to the perf half ported
from the legacy `Dial.py`. The perf side is a pluggable backend: `simulate`
(pure-Python offline/CI/demo) or `chariot` (the real bench, kept in its native
Python-2/Chariot world behind a subprocess to `matrix/chariot_perf.py`). Output
is a friendly self-contained HTML + CSV report (replaces the old hardcoded-path
Excel template). Config split: `perf.yaml` = what/how to test (matrix, topology,
wan-up), `router.yaml` = passwords. `python run_matrix.py --demo` runs the whole
chain with no router/Chariot present.

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
  `--apply`, and every lookup sweeps ALL frames — old frameset UIs (Cudy) keep
  the menus and the WAN form in separate child frames. `dial.kind`: select | dropdown | radio; `dial.value` optional
  read-back sub-selector; `mode_overrides` swaps whole keys per mode (Tenda
  ipv6 page). Facts lines not yet re-verified on the physical device are
  commented `[待真机复核]`. `verify_hook(page, result)` is the future WAN-up
  integration point. Creds come from router.yaml via `modes.merge_params`.
- `start.py` (+ `start.bat`) — **the zero-knowledge entry** (user ask
  2026-07-23: "python script.py → list models → choose → run, no prep").
  Interactive wizard; the DEFAULT action (plain Enter) is the tool's whole
  point: the FULL ROUND — every mode the chosen model script declares, each
  really applied, then throughput, then report. Menu: 1 full round (default) /
  2 single-mode switch (also applies directly) / 3 offline demo. **Bench
  semantics (user decision 2026-07-23): no apply-or-not question anywhere in
  the wizard or matrix — switching that isn't applied makes the throughput
  meaningless.** The no-apply safety default survives ONLY in the per-model
  CLI (`models/<X>.py <mode>`, `--apply` to save) for home/dev environments.
  The full-round path prompts **per mode** (not the union of required fields:
  L2TP and PPTP share the field names but get different accounts) and MUST save
  typed creds to router.yaml, under `params[<mode>]`, since the matrix pulls
  creds per mode from there. Menu 4 = `run_setup()`, moved here from the
  deleted cli.py so testers have exactly one entry point. Friendly verdict lines instead of raw JSON.
  Hidden `--url`/`--headless` exist ONLY so the smoke test can drive it over
  piped stdin (indexes computed, not hardcoded, so new models don't break it).
- `matrix/` + `run_matrix.py` — **the orchestration layer (the full test loop).**
  `run.py` is the main loop: for each dial mode → `_driver.run()` switch (lazy
  import, so `--demo` needs no Playwright) → `wanup.wait_wan_up` → for each
  band×direction×proto call `perf_backends.PerfBackend.measure` → `report.py`
  writes HTML+CSV. **Default matrix = `all_modes(facts)` — every mode the
  model script declares, in declaration order — and every switch applies for
  real; there is NO --apply flag (removed 2026-07-23, user decision: on the
  bench you always apply, or the throughput isn't measuring that mode).**
  `config.py` reads `perf.yaml` (optional; `dial_modes:` only to subset/
  reorder/add params). `perf_backends.py`: `SimulatorBackend` (deterministic
  offline numbers) and `ChariotBackend` (subprocess → `chariot_perf.py`).
  `chariot_perf.py` is the cleaned, parameterized port of the legacy `Dial.py`
  throughput+judge logic, Py2/3-compatible and bench-only (imports Chariot
  lazily). A failed switch skips that mode's measurements and is recorded, not
  silently swallowed (the legacy script's bare `except: continue` even had its
  error write commented out).
- `.claude/skills/adapt-router-model/SKILL.md` — the onboarding methodology as
  a skill: diagnose artifact → FACTS mapping table, selector cookbook, the
  four iron rules, verification checklist. New models go through this, never
  through guessed DOM.
- `models/_browser.py` — Playwright launch (default `channel="chrome"`).
- `modes.py` — `MODE_REQUIRED_FIELDS` (which params each dial mode needs) and
  `merge_params` (pull creds out of router.yaml **per mode**, so PPPoE
  credentials can never leak into a dynamic run). `params:` in router.yaml
  takes an optional per-mode block that wins over the flat keys — L2TP and PPTP
  share the field NAMES (`vpn_user`/`vpn_pass`) but the bench issues two
  different accounts, so one flat layer silently loses one of them.
- `settings.py` — `router.yaml` local defaults (IP/passwords/per-mode creds;
  git-ignored). Written by `start.py --setup` (menu 4).
- `tests/smoke_test.py` — offline e2e vs mock pages.

## Run / verify
```bash
# offline logic test (no router needed) — must stay green:
python tests/smoke_test.py            # expect "0 failed" (count shrank when
                                      # the engine cases went with the engine)

# the zero-knowledge entry (colleagues): interactive wizard, pick by number;
# default action = FULL ROUND (all declared modes, really applied, + perf)
python start.py                       # Windows: double-click start.bat

# daily use on an adapted model (run on a machine ON the router's LAN):
python start.py --setup               # one time -> router.yaml (git-ignored)
python models/Tenda_AX3000.py pppoe   # add --apply to really save
# full performance round (switch + WAN-up + throughput + HTML/CSV report):
python run_matrix.py --demo           # offline sample report, no router needed
python run_matrix.py --model Tenda_AX3000           # real round (perf.yaml)
# a new device: connect Claude in Chrome to it and follow the skill —
# there is no heuristic fallback any more, and that is deliberate.
```

## Environment
- **`vendor/python/` is COMMITTED (~97 MB) and that is deliberate** (user
  constraint 2026-07-28: the bench is offline AND its only Python is a 2.x that
  cannot be touched). It is an unpacked Windows embeddable CPython 3.8.10 with
  the deps pre-installed into `Lib/site-packages`, so the bench does zero
  installing: download the repo on an online PC → copy the folder → double-click
  `start.bat`. `python38._pth` is patched (`Lib\site-packages` + `import site`)
  or the embeddable ignores those packages. 3.8 because it is the last CPython
  supporting Win7. Rebuild via `tools/make_offline_bundle.py` (runs on any OS —
  `pip --platform win_amd64`), never by hand-editing site-packages. **Never put
  it in Git LFS**: GitHub's "Download ZIP" would hand out pointer files and kill
  the whole point. `.gitattributes` has `vendor/** -text` so nothing is
  line-ending-mangled.
- **A `._pth` file puts the interpreter in isolated mode, which does NOT prepend
  the script's directory to `sys.path`** (bench, 2026-07-28: `run.bat setup` ->
  `ModuleNotFoundError: No module named 'settings'`). Every entry point except
  every other entry self-bootstrapped with `sys.path.insert(0, ROOT)`, which is
  why `smoke.bat` passed while the (now deleted) `run.bat`/`cli.py` path died.
  Fixed twice over: the entry inserted ROOT, and `python38._pth` carries a
  `..\..` line. **Any new top-level entry script needs that insert** — never
  rely on the script directory being on sys.path.
- The bench's Python 2 is an asset, not a problem: `matrix/chariot_perf.py` is
  meant to run under it (`chariot.python2`). Only the Playwright half needs 3.8.
  **That Python is ActivePython 2.6.5 (32-bit), not 2.7** (bench, 2026-07-28,
  `import PyChariot` confirmed working on it), so `chariot_perf.py` must avoid
  `argparse` (stdlib only since 2.7) — it hand-parses `--json`. Keep anything
  that runs under it to 2.6-safe stdlib. **PyChariot is chatty**: it configures
  logging and prints `DEBUG:ChariotApi:...` lines (some containing Chinese) from
  `import` onwards, so `ChariotBackend` reads the last line that *parses* as
  JSON (`_last_json`) rather than the last line, and decodes the subprocess with
  `errors="replace"`. **Its `CHR_PROTOCOL_*` constants are `c_byte` objects,
  not ints** (bench 2026-07-28: its own log prints `protocol:c_byte(2)`), and
  `CHR_pair_set_protocol` re-wraps them → `TypeError: an integer is required`.
  Pass `.value`. Assume every PyChariot constant may be a ctypes object.
- Interpreter choice lives in `_py.bat`, `call`ed by every other `.bat`:
  `.venv\Scripts\python.exe` first, else `vendor\python\python.exe`. No fallback
  to a bare `python` on PATH — on those benches that IS the Python 2, and the
  failure would look like a random SyntaxError. `setup.bat` detects a
  ready-to-run `vendor/python` and only verifies imports (installs nothing).
- Chrome via `channel="chrome"` (offline). Windows bench: locked Chrome 114 +
  chromedriver 114. The repo ships NO browser binary — an offline bench needs
  Chrome's full offline installer carried over.
- Cross-platform: code is OS-independent; only the browser binary differs.

## Gotchas (learned the hard way)
> Several entries below were learned inside the heuristics engine, which is
> gone. They are kept because they are **why `models/_driver.py` behaves the
> way it does** — every one of them is a false-success this tool once produced
> on a real router. Delete a rule only with evidence, not with tidiness.
- The repo path contains `[Tool]`, a glob character class. Use `glob.escape()`
  in Python and quote paths in shell, or matching silently returns nothing.
  (Fixed in `profile.py`; bit AGAIN in `matrix/run.py list_models` — PR #1
  shipped it returning `[]` on this path; now os.listdir. Prefer os.listdir
  over glob for in-repo scans.)
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

**Bench acceptance status (2026-07-19, user-confirmed):**
`models/Tenda_AX3000.py` and `models/Cudy_AX.py` both **pass on the physical
devices, including the real `--apply` round** — dial mode changes and saves for
every mode they declare. They are the reference examples; copy their shape.
`models/Mercusys_BE3600.py` still carries `[待真机复核]` field selectors (the
2026-07-11 live run went through heuristics, not the script).

Live on a **Mercusys BE3600** (2026-07-11): custom `<div>`-combobox connection
type; Save button; L2TP fields Username/Password/"VPN Server IP/Domain Name";
IPv6 lives under Advanced→IPv6 (not the main list).

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
the mode requires none (PPPoEv6 creds under mode ipv6). All of this now lives
in `models/Tenda_AX3000.py`'s `mode_overrides` (the old
`profiles/tenda_ipv6.yaml`, and its `--brand` footgun, are gone).
**2026-07-23 rename (user decision, precision):** the model-script mode key
`ipv6` → `dhcpv6` — v6 modes are named by their exact flavor (`dhcpv6` /
`pppoev6`), never a vague "ipv6". The canonical `ipv6` class survives only
inside the heuristics engine (cli.py adaptation runs, match_mode ordering). Hard-learned
in the mock: a leaf only counts for the widget
scan if a connection-type label sits in a *form-row-sized* ancestor (<120
chars) — otherwise the sidebar "IPv6" nav link and the "IPv6" switch label
masquerade as the control (both exist on the real page), hijacking detection
and defeating the enable_toggle safety check.

**Tenda direct-observation pass (2026-07-18, Claude in Chrome on the live
device at 192.168.1.1** — LAN IP moved off the 192.168.0.1 default to avoid
clashing with the user's home router; firmware V16.03.68.15, HW V3.0).  Every
FACTS line in `models/Tenda_AX3000.py` was verified in-page (querySelectorAll
count==1): login button `button.login-form__submit` (text "Login" on
login.html), dial value node `[data-name='wanType']` (present on BOTH #/wan and
#/advance/ipv6, unique per page), PPPoE inputs
`input[data-name='wanPPPoEUser'/'wanPPPoEPwd']` (labels are "PPPoE Username" /
"PPPoE Password", NOT bare Username/Password), apply = "Connect" on #/wan and
"Save" on the IPv6 page (both also carry `[data-name='submit']`, but text-is
is used because the connected-state Disconnect button was not observed), IPv6
enable switch state lives on the inner icon `[data-name='ipv6En']`
(ON = `v-switch__icon--active`; the OUTER div.v-switch has no state token, so
pin the icon).  The v4 list is ONLY PPPoE / Dynamic IP / Static IP — no
L2TP/PPTP on this model (removed from FACTS and mock); v6 flavors are
DHCPv6 / PPPoEv6 / "Static IPv6 Address"; the same-text "DHCPv6" LAN radio
decoy is real.  Mocks (tenda.html / tenda_ipv6.html) were updated to mirror
all of this.  First live `--apply` (2026-07-18, `dynamic --pass ... --apply`)
exposed a matcher lesson: the real button is
`<button data-name="submit"><span class="v-button__item">Connect</span></button>`
— **`:text-is()` matches the element that directly owns the text node**, so
`button:text-is("Connect")` hits 0 (the span owns it; same for the IPv6 "Save").
Fixed by double-anchoring `button[data-name='submit']:has(span:text-is("..."))`
(count==1 verified on both pages), mocks now replicate the nested-span DOM
(Disconnect decoy carries data-name=submit as hypothetical worst case), and
`_apply`'s failure warning now lists the visible buttons it saw.  Connect click
verified live end-to-end (`applied:true`).  Still pending: the rest of the
user's `--apply` round (pppoe → ipv6/DHCPv6 → pppoev6, i.e. the "Save" click).

**Cudy (2026-07-18, live at 192.168.10.1; FW 1.0.1-20240321, SSID Cudy-554C —
shell-label model name still to be read, script is `models/Cudy_AX.py`).**
Old-school **frameset** UI: login in the main document (`#pwd` +
`input[value='Login']` — an input, text in `value=`), menus and the WAN form in
separate child frames (`top_menu.htm` / `sub_menu_*.htm` / `tcpipwan.htm`), which
is why `models/_driver.py` sweeps all frames.  Post-login landing is
Management/Status: nav is `#Network` then `#WAN` (anchor ids == menu texts).
Dial control is a native `select#wanType_id`; options verbatim: Static IP /
DHCP Client / PPPoE / PPTP / L2TP (dynamic == "DHCP Client" here).  Per-mode
name-anchored fields (`pppUserName/pppPassword`, `pptp*`, `l2tp*` — vpn_server
maps to `*ServerIpAddr`, DomainName variant exists).  Apply is
`input[name='save_apply']` ("Save & Apply", visible+unique); the frame also
hides EIGHT `*Connect`/`*Disconnect` submits — never match apply by the text
"Connect" on this brand.  All four modes validated live via the script itself
(read_back + fills, no-apply); `--apply` acceptance still pending.  Mock:
`cudy*.htm` frameset set.

**IPv6 is compiled OFF on this Cudy build — proven, not assumed** (the first
pass only checked visible menu links, which was under-evidenced; the user
pushed back and the exhaustive re-check confirmed the conclusion but found the
real reason).  Method worth reusing on any Realtek-SDK-style UI: harvest every
`*.htm` referenced by the loaded frames (49 pages here), GET each and grep for
the feature.  Findings: no IPv6 config page exists and `sub_menu_ipv6.htm` /
`ipv6.htm` 404 (not shipped); `navigation.js` DOES contain the menu code
(`if(ipv6){ ... add_topMenuItem("sub_menu_ipv6.htm","ipv6"); }`), but the
server-generated `top_menu.htm` emits `var ipv6 = 0;` (sibling vars like
`wlan_num = 2` are injected per-device), so it never draws; the WAN page's
`input[name='ipv6_passthru_enabled']` sits in a `display:none` row in all five
modes (dead code).  => v6 needs a firmware upgrade/replacement on this unit;
re-observe the UI (Claude in Chrome) afterwards before adding an ipv6
mode_override.

## Known gaps
- **IPv6 throughput is not measured yet.** The v6 modes (`dhcpv6`/`pppoev6`)
  only prove the *switch* works: Chariot pairs still use the IPv4 endpoint
  addresses. `_protocol()` already resolves `TCP6`/`UDP6` off PyChariot's own
  constants, so what is missing is the bench's IPv6 addressing (endpoints +
  peers), not code. `wan_up` would also need `ping -6`.
- **`static` has no field mapping** (`modes.py`: empty required list, and no
  model script maps ip/mask/gateway). It is in Tenda's `modes` so
  `all_modes()` includes it — keep it out of `dial_modes` in perf.yaml or the
  round will switch to Static IP and fill nothing.
- **WLAN band switching is manual.** `bands` only selects which endpoint
  injects; nothing re-associates a client. Two bands in one round means two
  wireless clients with different IPs.
- **UDP reports throughput only** — no loss/jitter, matching the legacy
  `result_judge`. PyChariot exposes `CHR_RESULTS_MLR` / `_JITTER` if that is
  ever wanted.
- Captcha logins, canvas-drawn UIs and heavily obfuscated SPAs are out of
  scope: adapt by hand through the skill, or don't.

## Next steps
- Produce `models/` scripts for the remaining group brands — **Buffalo, Huawei**
  — via the adapt-router-model skill (Claude in Chrome on the live device;
  never guess their DOM). Tenda + Cudy are done and accepted.
- Read the Cudy shell label and rename `Cudy_AX.py` / its `model:` to the real
  model name (currently a placeholder).
- Re-verify on the bench the `[待真机复核]` lines in
  `models/Mercusys_BE3600.py` (field selectors, apply click, login button).
- The `.bat` wrappers (`setup.bat` dual online/offline, `dial.bat`,
  `matrix.bat`) were written on macOS and **have not been executed on
  Windows** — first Windows run should confirm them (see WINDOWS.md).
- `run_matrix.py` is the orchestrator (replaced the old `examples/run_test_matrix.py`
  skeleton). **`matrix/chariot_perf.py` now runs for real** (bench 2026-07-28:
  one cell, dynamic/lan/up/TCP, 947.98 Mbps, `stable:true`, self-consistent with
  the driver's own `sent_bytes_e1 / elapsed_time`) — the port is no longer
  UNRUN. `chariot.python2` = `C:\Python26\python.exe`. Remaining: (1) the
  orchestration layer end-to-end (`run_matrix.py` driving switch + measure in
  one loop) has NOT been run on the bench yet, only its two halves separately;
  (2) confirm one `wan_up` ping host that answers in every mode — 202.99
  answers in dynamic, 203.1 in the tunnel modes, and `wan_up.host` is global,
  not per-mode.
- Mercusys IPv6 (Advanced→IPv6): diagnose first, then add a `mode_overrides`
  block to its model script.
- (History note) The perf merge was implemented twice in parallel on
  2026-07-23; the subprocess/Py2 design (PR #1) won because PyChariot is a
  Python-2-era library. The other attempt — an in-process py3 port with an
  optional `wan_perf.xls` template writer (the old CONN_TYPE_INDEX cell map) —
  lives on local branch `keep/perf-py3-parallel-impl` (never pushed). If the
  team wants results written into the group's wan_perf.xls template again,
  lift `perf/report.py` from that branch into `matrix/report.py`.
- WLAN 2.4G/5G switching later.
