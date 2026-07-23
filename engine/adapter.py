"""The generic engine: login -> reach WAN settings -> set dial mode -> read back.

Scope (per approved plan): confirm the dial-mode control was *located and
changed* (read-back == target).  It deliberately does NOT verify the WAN
actually dials up -- the local bench has no upstream dial servers, and the
single-machine scripts own connectivity/perf checks.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from config import Config, DEFAULT
from engine import heuristics as H
from engine.profile import Profile

# canonical dial mode -> the field concepts that mode needs the caller to supply
MODE_REQUIRED_FIELDS: Dict[str, List[str]] = {
    "dynamic": [],
    "static": [],  # ip/mask/gw vary too much; handled via profile if needed
    "pppoe": ["pppoe_user", "pppoe_pass"],
    "l2tp": ["vpn_server", "vpn_user", "vpn_pass"],
    "pptp": ["vpn_server", "vpn_user", "vpn_pass"],
    "ipv6": [],
    # v6 flavors exposed as their own runnable modes by models/ scripts (the
    # Tenda test round iterates DHCPv6 then PPPoEv6 -- named precisely, never
    # a vague "ipv6"); not cli.py modes.
    "dhcpv6": [],
    "pppoev6": ["pppoe_user", "pppoe_pass"],
}


@dataclass
class Result:
    mode: str
    success: bool = False
    detected_via: str = ""          # "select" | "radio" | "profile" | ""
    read_back: str = ""             # what the control reported after change
    filled: List[str] = field(default_factory=list)
    applied: bool = False
    needs_recording: bool = False   # heuristics failed -> onboard via --record
    message: str = ""
    screenshot: str = ""
    diagnostic: str = ""            # path to a diagnose artifact (auto-written on failure)

    def as_dict(self) -> dict:
        return self.__dict__


class RouterAdapter:
    def __init__(self, page, config: Optional[Config] = None,
                 profile: Optional[Profile] = None):
        self.page = page
        self.cfg = config or DEFAULT
        self.profile = profile

    # -- frame helpers -----------------------------------------------------
    def _frames(self):
        return list(self.page.frames)

    def _search(self, fn):
        """Run fn(frame) across every frame; return (frame, result) on first hit."""
        for fr in self._frames():
            try:
                res = fn(fr)
            except Exception:
                res = None
            if res:
                return fr, res
        return None, None

    def _search_wait(self, fn, timeout_ms: Optional[int] = None):
        """Like _search, but poll until fn hits or timeout_ms elapses.

        Playwright's count()/is_visible() (used by the heuristics via
        first_visible) take an *instant* snapshot -- they do NOT auto-wait.  On
        a real router the UI is a React SPA whose controls mount asynchronously
        after login / route changes, so a one-shot scan often runs too early.
        Waiting lives here in the adapter (which owns the page/timing) so the
        heuristics stay pure, stateless locators.
        """
        timeout_ms = self.cfg.default_timeout_ms if timeout_ms is None else timeout_ms
        waited, step = 0, 250
        while True:
            frame, res = self._search(fn)
            if res:
                return frame, res
            if waited >= timeout_ms:
                return None, None
            try:
                self.page.wait_for_timeout(step)
            except Exception:
                pass
            waited += step

    def _find_dial_control(self, timeout_ms: Optional[int] = None):
        """Poll for the dial-mode control -- native <select>, an ARIA combobox,
        or a role-less custom widget, whichever appears first.  Returns
        (kind, frame, obj):
            kind "select"   -> obj is the find_dial_mode_select() dict
            kind "combobox" -> obj is an ARIA combobox trigger Locator
            kind "widget"   -> obj is a role-less custom dropdown trigger Locator
            (None, None, None) on timeout.

        All kinds are checked in every poll iteration so a device that uses only
        one of them (e.g. Mercusys combobox, Tenda widget) isn't blocked waiting
        out the full timeout on <select>.
        """
        timeout_ms = self.cfg.default_timeout_ms if timeout_ms is None else timeout_ms
        waited, step = 0, 250
        while True:
            _, info = self._search(H.find_dial_mode_select)
            if info:
                return "select", _, info
            frame, trigger = self._search(H.find_dial_mode_combobox)
            if trigger:
                return "combobox", frame, trigger
            # role-less custom dropdown (no <select>, no role=combobox, no unique
            # selector) -- e.g. Tenda's Vue <div class="v-select">.
            frame, trigger = self._search(H.find_dial_mode_widget)
            if trigger:
                return "widget", frame, trigger
            if waited >= timeout_ms:
                return None, None, None
            try:
                self.page.wait_for_timeout(step)
            except Exception:
                pass
            waited += step

    # -- profile selector overrides ---------------------------------------
    # A profile may pin a CSS/text selector for any concept when the heuristics
    # can't handle an idiosyncratic UI (e.g. Xiaomi, whose layout differs wildly
    # from TP-Link/Mercusys).  These helpers make those overrides authoritative,
    # falling back to heuristics when a concept has no override.
    def _profile_sel(self, concept: str) -> Optional[str]:
        return self.profile.selector(concept) if self.profile else None

    def _locate_by_selector(self, css: str, timeout_ms: Optional[int] = None,
                            require_visible: bool = True):
        """Locate an element matching a profile CSS selector, across all frames,
        waiting for it to render.

        require_visible=False returns the first *attached* match even if it's
        hidden -- needed for "beautified" native <select>s (Xiaomi/jQuery
        selectbox plugins hide the real <select> and render a pretty widget over
        it; the real form field, which we drive, is display:none)."""
        def fn(fr):
            try:
                loc = fr.locator(css)
                vis = H.first_visible(loc)
                if vis:
                    return vis
                if not require_visible:
                    try:
                        if loc.count() > 0:
                            return loc.first
                    except Exception:
                        return None
                return None
            except Exception:
                return None
        return self._search_wait(fn, timeout_ms=timeout_ms)

    def _profile_dial_control(self):
        """If the profile pins the dial-mode control, locate it and classify it
        as a native <select> or a custom combobox trigger, matching the
        (kind, frame, obj) shape of _find_dial_control.  (None, None, None) if
        no override or it isn't found."""
        css = self._profile_sel("dial_mode_select")
        if not css:
            return None, None, None
        # require_visible=False: a beautified native <select> is hidden by design.
        frame, el = self._locate_by_selector(
            css, timeout_ms=self.cfg.default_timeout_ms, require_visible=False)
        if not el:
            return None, None, None
        try:
            tag = (el.evaluate("e => e.tagName") or "").lower()
        except Exception:
            tag = ""
        if tag == "select":
            modes: Dict[str, dict] = {}
            try:
                options = el.locator("option")
                for j in range(options.count()):
                    opt = options.nth(j)
                    txt = opt.text_content() or ""
                    val = opt.get_attribute("value")
                    m = H.match_mode(txt)
                    if m and m not in modes:
                        modes[m] = {"text": txt.strip(),
                                    "value": val if val is not None else "",
                                    "index": j}
            except Exception:
                pass
            return "select", frame, {"locator": el, "modes": modes}
        return "combobox", frame, el

    def _diag(self) -> str:
        """A short 'what did we actually see' note, appended to the failure
        message so a real-device run that still fails is diagnosable.

        Delegates to diagnose.summarize -- which scans ALL frames (the old
        main-frame-only version lied on iframe UIs) and also reports whether any
        clickable looks like a save button (so a "Connect"-style apply button no
        longer goes unnoticed)."""
        try:
            from engine import diagnose
            return diagnose.summarize(self.page)
        except Exception:
            return ""

    def _settle(self):
        try:
            self.page.wait_for_timeout(self.cfg.settle_ms)
        except Exception:
            pass

    # -- steps -------------------------------------------------------------
    def _logged_in(self) -> bool:
        """We've left the login screen once no password field is visible in any
        frame (login page shows one; the dashboard doesn't)."""
        _, pwd = self._search(H.find_password_input)
        return pwd is None

    def _wait_logged_in(self, timeout_ms: Optional[int] = None) -> bool:
        timeout_ms = self.cfg.default_timeout_ms if timeout_ms is None else timeout_ms
        waited, step = 0, 250
        while True:
            if self._logged_in():
                return True
            if waited >= timeout_ms:
                return False
            try:
                self.page.wait_for_timeout(step)
            except Exception:
                pass
            waited += step

    def login(self, admin_user: str = "", admin_pass: str = "") -> bool:
        """Fill and submit the admin login, then CONFIRM we actually got in.

        The login form on a real router is a React SPA that mounts *after* the
        page loads, so we WAIT for the password field rather than scanning once
        and giving up (the old one-shot search silently skipped login when it
        ran before the form rendered -- Chrome just sat on the login page).

        Returns True if authenticated (no form present, or we submitted and left
        the login screen); False if a password field is still showing after we
        tried -- so the caller can report a real 'login failed', not a
        misleading 'no dial-mode control'.
        """
        pw_css = self._profile_sel("login_pass")
        if pw_css:
            _, pwd = self._locate_by_selector(pw_css, timeout_ms=8000)
        else:
            _, pwd = self._search_wait(H.find_password_input, timeout_ms=8000)
        if not pwd:
            # no login form appeared at all -> assume already authenticated
            return self._logged_in()
        if admin_user:
            u_css = self._profile_sel("login_user")
            if u_css:
                _, user = self._locate_by_selector(u_css)
            else:
                _, user = self._search(lambda fr: H.find_input(fr, "login_user"))
            if user:
                try:
                    user.fill(admin_user)
                except Exception:
                    pass
        try:
            pwd.fill(admin_pass)
        except Exception:
            pass
        login_css = self._profile_sel("login_button")
        if login_css:
            _, btn = self._locate_by_selector(login_css, timeout_ms=3000)
        else:
            _, btn = self._search(
                lambda fr: H.find_button(fr, H.BUTTON_LOGIN_SYNONYMS))
        if btn:
            try:
                btn.click()
            except Exception:
                try:
                    pwd.press("Enter")
                except Exception:
                    pass
        else:
            try:
                pwd.press("Enter")
            except Exception:
                pass
        self._settle()
        return self._wait_logged_in(timeout_ms=8000)

    def goto_wan_settings(self) -> bool:
        """Navigate to the WAN/internet settings screen.

        Uses profile.wan_path when given, else clicks a heuristically-found WAN
        menu entry (twice if needed for menu -> submenu layouts).
        """
        if self.profile and self.profile.wan_path:
            for label in self.profile.wan_path:
                # WAIT for each menu label: multi-level menus (e.g. Xiaomi's
                # 常用设置 -> 上网设置) reveal the next level asynchronously, so a
                # one-shot search would miss the submenu item.
                _, el = self._search_wait(
                    lambda fr, lbl=label: H.first_visible(
                        fr.get_by_text(lbl, exact=False)),
                    timeout_ms=6000)
                if el:
                    try:
                        el.click()
                        self._settle()
                    except Exception:
                        pass
            return True

        # heuristic: click a WAN menu entry, then WAIT for a dial control (native
        # <select> or custom combobox) to render.  Real router UIs are React
        # SPAs: the control mounts asynchronously after the route change, so we
        # poll rather than assume it's present right after the click.  The old
        # code only checked for a native <select>, so combobox-only devices
        # (Mercusys/TP-Link) never registered as "arrived".
        for _ in range(2):
            if self._find_dial_control(timeout_ms=0)[0]:
                return True
            _, menu = self._search(H.find_wan_menu)
            if not menu:
                break
            try:
                menu.click()
            except Exception:
                break
            if self._find_dial_control(timeout_ms=4000)[0]:
                return True
        return True  # best-effort; set_dial_mode re-scans with its own wait

    def _ensure_enabled(self) -> None:
        """If the profile pins an enable switch (`selectors.enable_toggle`) --
        a toggle that must be ON before the WAN section renders at all (e.g.
        Tenda's IPv6 page: the connection-type dropdown only mounts once the
        IPv6 switch is on) -- switch it on.

        Safety: never touched while a dial control is already present, so a run
        on an already-enabled page cannot accidentally switch it OFF.  Click
        only when the state reads off/unknown; whether the section actually
        appeared is verified by the normal control wait downstream."""
        css = self._profile_sel("enable_toggle")
        if not css:
            return
        if self._find_dial_control(timeout_ms=0)[0]:
            return  # section already rendered -- do not touch the switch
        frame, el = self._locate_by_selector(css, timeout_ms=4000)
        if not el:
            return
        state = None
        try:
            state = el.is_checked()            # real <input type=checkbox>
        except Exception:
            try:
                ac = el.get_attribute("aria-checked")
                if ac is None:
                    ac = el.get_attribute("aria-pressed")
                if ac is not None:
                    state = (ac == "true")
                else:
                    # class-token sniff for styled div switches (Vue/React)
                    cls = (el.get_attribute("class") or "").lower()
                    tokens = re.split(r"[^a-z0-9]+", cls)
                    if any(t in ("checked", "on", "active", "open", "enabled")
                           for t in tokens):
                        state = True
            except Exception:
                pass
        if state is True:
            return  # already on; the control is missing for another reason
        try:
            el.click()
            self._settle()
        except Exception:
            pass

    def set_dial_mode(self, mode: str, params: Dict[str, str], result: Result) -> None:
        mode = mode.lower()
        # Locate the dial-mode control.  A profile selector override wins; else
        # wait for the SPA to mount it, probing native <select> and custom
        # combobox together so a combobox-only device isn't blocked waiting out
        # the timeout on <select>.
        kind, frame, obj = self._profile_dial_control()
        if kind is None:
            kind, frame, obj = self._find_dial_control()

        # 1) native <select> dropdown (most common on older/simple UIs)
        if kind == "select":
            info = obj
            if mode in info["modes"]:
                sel = info["locator"]
                opt = info["modes"][mode]
                # profile may pin an exact option label/value for this model
                pinned = (self.profile.mode_labels.get(mode)
                          if self.profile else None)
                # force=True so a *hidden* beautified <select> can still be set;
                # select_option dispatches input+change, which the pretty widget
                # (and the router's own JS) listens to. Harmless for visible ones.
                try:
                    if pinned:
                        sel.select_option(label=pinned, force=True)
                    elif opt["value"]:
                        sel.select_option(value=opt["value"], force=True)
                    else:
                        sel.select_option(index=opt["index"], force=True)
                    result.detected_via = "select"
                except Exception as exc:
                    result.message = "select_option failed: %s" % exc
                self._settle()
                self._fill_params(mode, params, result)
                result.read_back = self._read_back_select(sel)
                result.success = H.match_mode(result.read_back) == mode
                return
            # a <select> that lacks this mode won't also be a combobox; the only
            # sensible next try is a radio group.
            result.message = ("dial-mode dropdown found but has no '%s' option "
                              "(has: %s)" % (mode, ", ".join(info["modes"])))

        # 2) custom dropdown opened by clicking a trigger, then picking a popup
        # option.  Two shapes share this path:
        #   "combobox" -> React <div role=combobox> (e.g. Mercusys / TP-Link;
        #                 verified live on a Mercusys BE3600).
        #   "widget"   -> role-less custom widget with no unique selector
        #                 (e.g. Tenda's Vue <div class="v-select">).
        elif kind in ("combobox", "widget"):
            trigger = obj
            if self._select_via_combobox(frame, trigger, mode, result):
                self._fill_params(mode, params, result)
                # Widget read-back re-scans for the control's current value: the
                # tagged trigger element can be replaced by the framework on
                # change, so re-finding it is more reliable than the stale handle.
                if kind == "widget":
                    result.read_back = self._read_widget_mode(frame)
                if not result.read_back:
                    try:
                        result.read_back = trigger.inner_text().strip()
                    except Exception:
                        result.read_back = ""
                result.detected_via = kind
                pinned = (self.profile.mode_labels.get(mode)
                          if self.profile else None)
                result.success = (
                    H.match_mode(result.read_back) == mode
                    or (pinned is not None
                        and H.normalize(result.read_back) == H.normalize(pinned)))
                return

        # 3) radio-button fallback -- ONLY trusted when it's a genuine radio we
        # can read back via is_checked().  The text-match fallback inside
        # find_dial_mode_radio can otherwise latch onto a plain label / help
        # string (e.g. Xiaomi's "动态IP" description), and clicking that changes
        # nothing -- so we must NOT report success unless the control's own state
        # confirms the target mode.  (This was a real false-positive: radio
        # detected, is_checked() threw on a non-radio, and the code assumed the
        # click "took".)
        frame, radio = self._search_wait(
            lambda fr: H.find_dial_mode_radio(fr, mode), timeout_ms=2000)
        if radio:
            try:
                radio.click()
                self._settle()
                try:
                    checked = radio.is_checked()   # real read-back for a radio
                except Exception:
                    checked = None                 # not a real radio -> unverifiable
                if checked is not None:
                    result.detected_via = "radio"
                    self._fill_params(mode, params, result)
                    result.read_back = mode if checked else ""
                    result.success = bool(checked)
                    return
                # matched by text but couldn't verify a real control changed:
                # fall through to needs_recording with an actionable message.
                result.message = (
                    "matched dial mode '%s' by text but no verifiable control "
                    "changed -- pin selectors.dial_mode_select in the profile."
                    % mode)
            except Exception as exc:
                result.message = "radio click failed: %s" % exc

        # 4) nothing worked -> flag for recording
        result.needs_recording = True
        if not result.message:
            result.message = "no dial-mode control located by heuristics"
        result.message += self._diag()

    def _select_via_combobox(self, frame, trigger, mode: str, result: Result) -> bool:
        """Open a custom combobox and click the option for `mode`.

        Uses a DOM-level `option.click()` (via a Playwright locator), which
        dispatches trusted events inside the page -- so it reliably triggers the
        React onClick even when raw OS-level clicks on the portaled list don't.

        Honors profile `mode_labels` (parity with the native-<select> path): a
        pinned exact label beats the synonym tables -- needed when the canonical
        mode doesn't map 1:1 to an option (e.g. Tenda's IPv6 page offers
        PPPoEv6/DHCPv6 flavors; pin `ipv6: "DHCPv6"` to pick one
        deterministically).
        """
        pinned = (self.profile.mode_labels.get(mode) if self.profile else None)
        try:
            cur = trigger.inner_text()
            if pinned is not None:
                if H.normalize(cur) == H.normalize(pinned):
                    return True  # already showing the pinned label
            elif H.match_mode(cur) == mode:
                return True  # already showing target
        except Exception:
            pass
        try:
            trigger.click()
            self._settle()
        except Exception as exc:
            result.message = "combobox open failed: %s" % exc
            return False
        # the option popup is portaled and mounts asynchronously -- poll for it
        # instead of taking a single snapshot right after the open click.
        option, waited, step = None, 0, 200
        while waited <= 3000:
            option = (self._find_pinned_option(frame, pinned) if pinned
                      else H.find_mode_option(frame, mode))
            if option:
                break
            try:
                self.page.wait_for_timeout(step)
            except Exception:
                pass
            waited += step
        if not option:
            seen = self._visible_option_texts(frame)
            result.message = ("combobox opened but no '%s' option found%s"
                              % (pinned or mode,
                                 " (saw options: %s)" % ", ".join(seen)
                                 if seen else ""))
            return False
        try:
            option.click()
            self._settle()
            return True
        except Exception as exc:
            result.message = "combobox option click failed: %s" % exc
            return False

    def _find_pinned_option(self, frame, label: str):
        """Locate a popup option by its exact profile-pinned text.

        Option-shaped containers first: the same text can legitimately exist
        elsewhere on the page (e.g. Tenda's IPv6 LAN has a "DHCPv6" radio label
        while the WAN popup offers a "DHCPv6" option) -- a bare text match could
        click the wrong one.
        """
        rx = re.compile(r"^\s*%s\s*$" % re.escape(label), re.IGNORECASE)
        for sel in ("[role='option']", "[class*='option']"):
            try:
                el = H.first_visible(frame.locator(sel).filter(has_text=rx))
                if el:
                    return el
            except Exception:
                continue
        try:
            return H.first_visible(frame.get_by_text(label, exact=True))
        except Exception:
            return None

    def _visible_option_texts(self, frame) -> List[str]:
        """Texts of the currently-open popup's options, for failure messages
        (mirrors the native-select path's "has: ..." listing)."""
        texts: List[str] = []
        for sel in ("[role='option']", "[class*='option']"):
            try:
                loc = frame.locator(sel)
                for i in range(min(loc.count(), 12)):
                    el = loc.nth(i)
                    try:
                        if not el.is_visible():
                            continue
                        t = (el.inner_text() or "").strip()
                    except Exception:
                        continue
                    if t and len(t) < 30 and t not in texts:
                        texts.append(t)
                if texts:
                    break
            except Exception:
                continue
        return texts

    def _read_widget_mode(self, frame) -> str:
        """Read back a role-less custom dropdown's current value by re-scanning
        for it (the trigger element may have been re-rendered on change).  Tries
        the frame we changed first, then any frame."""
        for fr in ([frame] if frame else []) + self._frames():
            try:
                trg = H.find_dial_mode_widget(fr)
                if trg:
                    return trg.inner_text().strip()
            except Exception:
                continue
        return ""

    def _read_back_select(self, sel) -> str:
        try:
            return sel.evaluate(
                "el => el.options[el.selectedIndex] "
                "? el.options[el.selectedIndex].text : ''") or ""
        except Exception:
            try:
                return sel.input_value()
            except Exception:
                return ""

    def _fill_params(self, mode: str, params: Dict[str, str], result: Result) -> None:
        # The mode's required fields, plus any explicitly-provided params: an
        # explicit --param is user intent even when the canonical mode doesn't
        # list it (e.g. PPPoEv6 on an IPv6 page needs pppoe_user/pppoe_pass
        # although mode "ipv6" requires nothing by itself).
        concepts = list(MODE_REQUIRED_FIELDS.get(mode, []))
        for k in params:
            if k not in concepts:
                concepts.append(k)
        for concept in concepts:
            value = params.get(concept)
            if value is None:
                continue
            # PPPoE/VPN fields only mount *after* the mode is selected, so wait.
            css = self._profile_sel(concept)
            if css:
                _, field_el = self._locate_by_selector(css, timeout_ms=3000)
            else:
                _, field_el = self._search_wait(
                    lambda fr, c=concept: H.find_input(fr, c), timeout_ms=3000)
            if field_el:
                try:
                    field_el.fill(str(value))
                    result.filled.append(concept)
                except Exception:
                    pass

    def apply(self, result: Result) -> None:
        css = self._profile_sel("save_button")
        if css:
            _, btn = self._locate_by_selector(css, timeout_ms=3000)
        else:
            _, btn = self._search_wait(
                lambda fr: H.find_button(fr, H.BUTTON_SAVE_SYNONYMS,
                                         exclude=H.BUTTON_SAVE_EXCLUDE),
                timeout_ms=3000)
        if btn:
            try:
                btn.click()
                result.applied = True
                self._settle()
            except Exception:
                pass

    # -- top level ---------------------------------------------------------
    def run(self, mode: str, params: Dict[str, str],
            admin_user: str = "", admin_pass: str = "",
            do_apply: bool = True) -> Result:
        result = Result(mode=mode.lower())
        if not self.login(admin_user, admin_pass):
            # still on the login page -> don't march on and misreport it as a
            # missing dial control.
            result.message = (
                "login failed -- still on the login page. Check --pass (admin "
                "password), and note this router may allow only one web session "
                "at a time (close other logged-in browser tabs)." + self._diag())
            result.screenshot = self._screenshot(mode)
            return result
        self.goto_wan_settings()
        self._ensure_enabled()
        self.set_dial_mode(mode, params, result)
        if do_apply and result.success:
            self.apply(result)
        result.screenshot = self._screenshot(mode)
        return result

    def _screenshot(self, mode: str) -> str:
        try:
            os.makedirs(self.cfg.screenshot_dir, exist_ok=True)
            path = os.path.join(self.cfg.screenshot_dir, "dial_%s.png" % mode.lower())
            self.page.screenshot(path=path, full_page=True)
            return path
        except Exception:
            return ""
