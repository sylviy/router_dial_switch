"""Brand-agnostic, language-agnostic DOM heuristics.

This module is what lets one engine adapt to *many* router UIs without a
per-brand script.  Nothing here knows about a specific vendor: it recognises
concepts ("this is the PPPoE mode option", "this is the login password field")
by matching visible text / labels / attribute names against multilingual
synonym tables.

Add a language or a vendor's odd wording by extending the tables below -- no
engine code changes required.
"""
from __future__ import annotations

import re
from typing import Dict, List, Optional

# --------------------------------------------------------------------------
# Synonym tables.  Keys are canonical concepts; values are lowercase substrings
# matched against normalised text.  Order within a list does not matter; match
# is "any substring present".  Extend freely (zh / en today; add more).
# --------------------------------------------------------------------------

DIAL_MODE_SYNONYMS: Dict[str, List[str]] = {
    # canonical -> synonyms (checked as substrings of normalised option text)
    "pppoe":   ["pppoe", "ppperoe", "宽带拨号", "adsl拨号", "adsl", "虚拟拨号",
                "pppoe拨号", "宽带连接", "拨号上网"],
    "l2tp":    ["l2tp"],
    "pptp":    ["pptp"],
    # v6 WAN *flavors* (Tenda's IPv6 page offers PPPoEv6/DHCPv6...) count as
    # ipv6, NOT as pppoe/dynamic -- match_mode checks ipv6 before pppoe/dynamic
    # so the "pppoe"/"dhcp" substrings inside them can't misclassify.
    "ipv6":    ["ipv6", "ipv6连接", "ipv6上网", "ip v6", "pppoev6", "dhcpv6"],
    # NOTE: do NOT add generic "自动配置"/"手动配置" here -- those are the *IP
    # config* sub-radios (and IPv6 "自动配置DNS") inside a PPPoE form, NOT the
    # connection type.  They caused the radio fallback to grab the wrong control
    # on Xiaomi and falsely report success. Keep synonyms specific to the
    # connection TYPE.
    "dynamic": ["dynamic ip", "dynamic", "dhcp", "自动获取ip", "自动获取 ip",
                "动态ip", "动态 ip", "动态地址", "automatic"],
    "static":  ["static ip", "static", "静态ip", "静态 ip", "固定ip",
                "手动设置ip", "手动配置ip"],
}

# Concept -> label/placeholder synonyms (regex-joined) + attribute keywords
# (matched against name/id, ascii only since attributes are usually english).
FIELD_CONCEPTS: Dict[str, Dict[str, List[str]]] = {
    "login_user": {
        "text": ["用户名", "帐号", "账号", "登录名", "user name", "username", "user"],
        "attr": ["user", "account", "login", "name"],
    },
    "login_pass": {
        "text": ["密码", "口令", "登录密码", "password", "passwd"],
        "attr": ["pass", "pwd", "passwd"],
    },
    "pppoe_user": {
        "text": ["宽带账号", "宽带帐号", "上网账号", "pppoe用户名", "pppoe账号",
                 "connection user", "account", "用户名", "user name", "username"],
        "attr": ["user", "account", "pppoe", "acc"],
    },
    "pppoe_pass": {
        "text": ["宽带密码", "上网密码", "pppoe密码", "connection password",
                 "密码", "password"],
        "attr": ["pass", "pwd"],
    },
    "vpn_server": {
        "text": ["服务器地址", "服务器", "vpn服务器", "server address", "server ip",
                 "server", "gateway", "网关地址"],
        "attr": ["server", "srv", "host", "addr", "gateway"],
    },
    "vpn_user": {
        "text": ["用户名", "账号", "user name", "username", "user"],
        "attr": ["user", "account"],
    },
    "vpn_pass": {
        "text": ["密码", "password", "passwd"],
        "attr": ["pass", "pwd"],
    },
}

# Strong WAN-menu terms: unambiguous, tried first.
MENU_WAN_STRONG: List[str] = [
    "wan", "internet", "上网设置", "上网方式", "广域网", "联网设置", "wan设置",
    "internet settings", "接入设置", "外网设置", "wan口设置", "拨号设置",
]
# Weak terms: only tried if no strong match, and skipped when the text is
# clearly something else (e.g. "Network Map"/"Network Status" -- the first nav
# item on real Mercusys/TP-Link UIs, which must NOT be taken for WAN settings).
MENU_WAN_WEAK: List[str] = ["network settings", "network", "网络设置", "网络"]
MENU_WAN_WEAK_EXCLUDE: List[str] = ["map", "status", "映射", "状态", "topology"]

# Back-compat alias (strong + weak) for any external callers.
MENU_WAN_SYNONYMS: List[str] = MENU_WAN_STRONG + MENU_WAN_WEAK

# Accessible-name / label wording for the dial-mode control itself. Used to
# pick the right combobox on pages that have several (e.g. Mercusys/TP-Link put
# "Internet Connection Type" next to a "MAC Clone" combobox).
CONNECTION_TYPE_SYNONYMS: List[str] = [
    "connection type", "internet connection type", "wan connection type",
    "wan type", "上网方式", "接入方式", "拨号方式", "连接类型", "wan口连接类型",
]

BUTTON_SAVE_SYNONYMS: List[str] = [
    "保存", "应用", "确定", "提交", "save", "apply", "submit", "ok", "确认",
    "保存设置", "保存并应用",
    # Some UIs label the apply-the-WAN-settings button "Connect" (e.g. Tenda's
    # orange "Connect") / "连接" instead of Save.  See BUTTON_SAVE_EXCLUDE -- the
    # substring "connect" must NOT match "Disconnect"/"断开连接".
    "connect", "连接", "连接网络",
]

# Words that look like a save synonym by substring but are the OPPOSITE action.
# A save-button match whose text contains any of these is rejected.
BUTTON_SAVE_EXCLUDE: List[str] = ["disconnect", "断开"]

BUTTON_LOGIN_SYNONYMS: List[str] = [
    "登录", "登陆", "确定", "login", "log in", "sign in", "进入",
]


# --------------------------------------------------------------------------
# Text utilities
# --------------------------------------------------------------------------

def normalize(text: Optional[str]) -> str:
    if not text:
        return ""
    return re.sub(r"\s+", " ", text.strip().lower())


def match_mode(text: str) -> Optional[str]:
    """Return the canonical dial-mode a piece of option text refers to, or None.

    Specific multi-protocol names (pppoe/l2tp/pptp/ipv6) are checked before the
    looser dynamic/static families so that e.g. "PPPoE" is never mis-read as
    "dynamic" just because both mention IP.
    """
    t = normalize(text)
    if not t:
        return None
    # ipv6 before pppoe/dynamic: "PPPoEv6"/"DHCPv6" are IPv6 flavors and must
    # not be swallowed by their "pppoe"/"dhcp" substrings.
    for mode in ("ipv6", "pppoe", "l2tp", "pptp", "static", "dynamic"):
        for syn in DIAL_MODE_SYNONYMS[mode]:
            if syn in t:
                return mode
    return None


def _regex_for(words: List[str]) -> "re.Pattern[str]":
    return re.compile("|".join(re.escape(w) for w in words), re.IGNORECASE)


def _all_mode_synonyms() -> List[str]:
    """Every dial-mode synonym flattened -- used to spot a control whose *value*
    text is itself a mode (the signal for role-less custom dropdowns)."""
    words: List[str] = []
    for syns in DIAL_MODE_SYNONYMS.values():
        words.extend(syns)
    return words


# --------------------------------------------------------------------------
# Locator helpers.  `ctx` is a Playwright Frame (page.main_frame or a child
# frame) -- everything is frame-scoped so iframe-heavy router UIs just work by
# iterating page.frames in the adapter.
# --------------------------------------------------------------------------

def first_visible(locator):
    """Return the first visible match of a Playwright locator, or None."""
    try:
        count = locator.count()
    except Exception:
        return None
    for i in range(count):
        el = locator.nth(i)
        try:
            if el.is_visible():
                return el
        except Exception:
            continue
    return None


def find_password_input(ctx):
    """The single most reliable cross-brand signal: <input type=password>."""
    return first_visible(ctx.locator("input[type='password']"))


def find_input(ctx, concept: str):
    """Best-effort locate an <input> for a semantic concept (see FIELD_CONCEPTS).

    Tries, in order: accessible <label>, placeholder, name/id attribute
    substrings.  Returns a visible Locator or None.
    """
    spec = FIELD_CONCEPTS.get(concept, {})
    text_words = spec.get("text", [])
    attr_words = spec.get("attr", [])

    # 1) associated <label>
    if text_words:
        rx = _regex_for(text_words)
        try:
            el = first_visible(ctx.get_by_label(rx))
            if el:
                return el
        except Exception:
            pass
        # 2) placeholder
        try:
            el = first_visible(ctx.get_by_placeholder(rx))
            if el:
                return el
        except Exception:
            pass

    # 3) name / id attribute contains an (english) keyword, case-insensitive
    for kw in attr_words:
        css = "input[name*='{k}' i], input[id*='{k}' i]".format(k=kw)
        el = first_visible(ctx.locator(css))
        if el:
            return el
    return None


def _first_visible_matching(locator, exclude_rx=None):
    """First visible match whose text/value does NOT hit exclude_rx.

    Guards against a synonym that is a substring of its opposite -- e.g. a
    "connect" save button vs a "Disconnect" button on the same page.
    """
    try:
        count = locator.count()
    except Exception:
        return None
    for i in range(count):
        el = locator.nth(i)
        try:
            if not el.is_visible():
                continue
            if exclude_rx is not None:
                txt = normalize(el.inner_text() or "")
                if not txt:
                    txt = normalize(el.get_attribute("value") or "")
                if txt and exclude_rx.search(txt):
                    continue
            return el
        except Exception:
            continue
    return None


def find_button(ctx, synonyms: List[str], exclude: Optional[List[str]] = None):
    """Locate a clickable control (button / input[submit] / link) by text.

    `exclude`: reject a match whose text contains one of these (so "connect"
    doesn't select "Disconnect").
    """
    rx = _regex_for(synonyms)
    ex = _regex_for(exclude) if exclude else None
    # role=button covers <button> and role-annotated elements
    try:
        el = _first_visible_matching(ctx.get_by_role("button", name=rx), ex)
        if el:
            return el
    except Exception:
        pass
    # submit / button inputs (match value attribute)
    for word in synonyms:
        css = ("input[type='submit'][value*='{w}' i], "
               "input[type='button'][value*='{w}' i]").format(w=word)
        el = _first_visible_matching(ctx.locator(css), ex)
        if el:
            return el
    # any element with matching visible text (last resort)
    try:
        el = _first_visible_matching(ctx.get_by_text(rx), ex)
        if el:
            return el
    except Exception:
        pass
    return None


def _first_menu_hit(ctx, rx):
    for role in ("link", "menuitem", "tab", "button"):
        try:
            el = first_visible(ctx.get_by_role(role, name=rx))
            if el:
                return el
        except Exception:
            continue
    try:
        return first_visible(ctx.get_by_text(rx))
    except Exception:
        return None


def find_wan_menu(ctx):
    """Locate a nav entry that leads to WAN / internet settings.

    Two-tier: unambiguous terms (wan / internet / 上网设置) first; only then the
    generic "network", and even then skip "Network Map"/"Network Status" which
    is the landing page on Mercusys/TP-Link, not the WAN config.
    """
    hit = _first_menu_hit(ctx, _regex_for(MENU_WAN_STRONG))
    if hit:
        return hit
    weak = _first_menu_hit(ctx, _regex_for(MENU_WAN_WEAK))
    if weak:
        try:
            txt = normalize(weak.inner_text())
            if not any(x in txt for x in MENU_WAN_WEAK_EXCLUDE):
                return weak
        except Exception:
            return weak
    return None


# --------------------------------------------------------------------------
# Dial-mode control detection (the crux)
# --------------------------------------------------------------------------

def find_dial_mode_select(ctx):
    """Find the <select> that chooses the dial mode.

    Heuristic: the dial-mode dropdown is the <select> whose option texts map to
    the largest number of distinct dial modes (>=2).  Returns a dict:
        {"locator": <select Locator>,
         "modes": {canonical_mode: {"text","value","index"}}}
    or None.
    """
    best = None
    best_modes: Dict[str, dict] = {}
    selects = ctx.locator("select")
    try:
        n = selects.count()
    except Exception:
        return None
    for i in range(n):
        sel = selects.nth(i)
        try:
            if not sel.is_visible():
                continue
            options = sel.locator("option")
            opt_count = options.count()
        except Exception:
            continue
        modes: Dict[str, dict] = {}
        for j in range(opt_count):
            opt = options.nth(j)
            try:
                txt = opt.text_content() or ""
                val = opt.get_attribute("value")
            except Exception:
                continue
            m = match_mode(txt)
            if m and m not in modes:
                modes[m] = {"text": txt.strip(),
                            "value": val if val is not None else "",
                            "index": j}
        if len(modes) >= 2 and len(modes) > len(best_modes):
            best, best_modes = sel, modes
    if best is None:
        return None
    return {"locator": best, "modes": best_modes}


def find_dial_mode_combobox(ctx):
    """Find a *custom* dial-mode dropdown (ARIA combobox / `<div>` widget).

    Real routers (Mercusys, TP-Link, many others) render the connection-type
    picker as a React `<div role="combobox">`, not a native `<select>`, with the
    options in a detached popup that only exists while open.  `find_dial_mode_
    select` can't see those, so we locate the trigger here and the adapter opens
    it to pick an option.

    Strategy: prefer a combobox whose accessible name says "connection type";
    else fall back to any combobox whose current text already reads as a dial
    mode.  Returns the trigger Locator or None.
    """
    # 1) by label / accessible name
    rx = _regex_for(CONNECTION_TYPE_SYNONYMS)
    try:
        el = first_visible(ctx.get_by_role("combobox", name=rx))
        if el:
            return el
    except Exception:
        pass
    # 2) any combobox whose displayed value is itself a dial mode
    try:
        boxes = ctx.get_by_role("combobox")
        n = boxes.count()
    except Exception:
        return None
    for i in range(n):
        box = boxes.nth(i)
        try:
            if not box.is_visible():
                continue
            if match_mode(box.inner_text()):
                return box
        except Exception:
            continue
    return None


# In-page scan for a role-less custom dropdown.  Runs inside the router page via
# frame.evaluate.  It tags the chosen trigger with a data-attribute and returns
# an inventory object (NOT a bare bool), so the Python side can both hand back a
# normal Playwright Locator (these widgets have no id/name and share a class
# across several fields, so there is no unique CSS selector to build from
# outside) AND apply the card-strip guard below.
#
# args.modeGroups maps each canonical mode -> its regex source, so the scan can
# CLASSIFY each mode-leaf (dynamic vs pppoe vs ...).  That classification is
# what separates a *value display* (one mode word = the current value) from an
# *option list / card strip* (several distinct mode words as clickable
# siblings).  Reporting a card strip as a value would be a false positive: the
# adapter would see "already showing the target" and report success without
# clicking anything.  See find_dial_mode_widget.
_DIAL_WIDGET_JS = r"""
(args) => {
  const groups = Object.keys(args.modeGroups).map(
    k => ({mode: k, rx: new RegExp(args.modeGroups[k], 'i')}));
  const anyModeRx = new RegExp(args.modeRx, 'i');
  const connRx = new RegExp(args.connRx, 'i');
  const TAG = 'data-dialsw-trigger';
  document.querySelectorAll('[' + TAG + ']').forEach(e => e.removeAttribute(TAG));
  const norm = s => (s || '').replace(/\s+/g, ' ').trim();
  const visible = el => !!(el.offsetParent || el.getClientRects().length);
  const classify = t => { for (const g of groups) if (g.rx.test(t)) return g.mode;
                          return null; };
  // A "mode widget leaf": a compact element whose OWN visible text reads as a
  // dial mode, with no child that also does (so we take the innermost text
  // holder, e.g. Tenda's <div class="v-select__label--text">PPPoE</div>).  The
  // sibling widgets on the page show "Normal"/"1480"/"Auto" and never match.
  const isModeLeaf = el => {
    const t = norm(el.innerText);
    if (!(t.length > 0 && t.length < 24 && anyModeRx.test(t))) return false;
    for (const c of el.children) {
      const ct = norm(c.innerText);
      if (ct.length > 0 && ct.length < 24 && anyModeRx.test(ct)) return false;
    }
    return true;
  };
  const rawLeaves = [...document.querySelectorAll('div,span,a,button,li,p')]
    .filter(el => visible(el) && isModeLeaf(el));
  // REQUIRED: a genuine value display sits near a "connection type"-ish label.
  // Without this gate, any nav link / section header whose text is a mode word
  // (Tenda's sidebar "IPv6" entry, an "IPv6" form label next to an enable
  // switch) masquerades as the widget -- which both hijacks detection and
  // defeats the enable_toggle safety check.  A leaf with no such label nearby
  // is navigation or decoration, not the control.
  const labelScore = el => {
    let p = el;
    for (let i = 0; i < 5 && p; i++) {
      p = p.parentElement;
      if (!p) break;
      const t = norm(p.innerText);
      // the matching ancestor must be a form-ROW (label + value), not a whole
      // panel: a panel's aggregated innerText contains every label on the page
      // (incl. "connection type"), which would wave through unrelated leaves.
      if (t.length < 120 && connRx.test(t)) return 1;
    }
    return 0;
  };
  const leaves = rawLeaves.filter(el => labelScore(el) > 0);
  if (!leaves.length) return {tagged: false, leafCount: rawLeaves.length,
                              labeledCount: 0, cardStrip: false,
                              distinctModes: []};
  // Card-strip / segmented / radio-card detection: group leaves by their
  // immediate parent; if any parent holds >=2 leaves showing DISTINCT modes,
  // this is a picker of options, not a single value display.
  const byParent = new Map();
  const allModes = new Set();
  leaves.forEach(el => {
    const m = classify(norm(el.innerText));
    if (m) allModes.add(m);
    const p = el.parentElement;
    if (!p) return;
    let set = byParent.get(p);
    if (!set) { set = new Set(); byParent.set(p, set); }
    if (m) set.add(m);
  });
  let cardStrip = false;
  byParent.forEach(set => { if (set.size >= 2) cardStrip = true; });
  const chosen = leaves[0];
  const inv = {tagged: false, leafCount: rawLeaves.length,
               labeledCount: leaves.length, cardStrip: cardStrip,
               distinctModes: [...allModes],
               chosenText: norm(chosen.innerText),
               chosenMode: classify(norm(chosen.innerText))};
  // Only tag (hand back a Locator) when it's a genuine value display.  A card
  // strip is reported but NOT tagged -- the adapter must decline it.
  if (!cardStrip) { chosen.setAttribute(TAG, '1'); inv.tagged = true; }
  return inv;
}
"""


def _dial_widget_scan(ctx):
    """Run the in-page widget scan; returns the raw inventory dict or None."""
    mode_rx = "|".join(re.escape(w) for w in _all_mode_synonyms())
    conn_rx = "|".join(re.escape(w) for w in CONNECTION_TYPE_SYNONYMS)
    mode_groups = {canon: "|".join(re.escape(w) for w in syns)
                   for canon, syns in DIAL_MODE_SYNONYMS.items()}
    try:
        return ctx.evaluate(_DIAL_WIDGET_JS, {"modeRx": mode_rx, "connRx": conn_rx,
                                              "modeGroups": mode_groups})
    except Exception:
        return None


def find_dial_mode_widget(ctx):
    """Find a *role-less* custom dial-mode dropdown.

    Some UIs (e.g. Tenda's Vue `<div class="v-select">`) render the
    connection-type picker as a plain `<div>` with NO `<select>`, NO
    `role="combobox"`, and NO id/name -- and reuse the same class across several
    fields (ISP type, MTU, DNS...), so there's no unique CSS selector to pin.
    `find_dial_mode_select` and `find_dial_mode_combobox` both miss it entirely.

    We identify it *in-page* instead: only the connection-type widget displays a
    dial-mode word as its value ("PPPoE"/"DHCP"/...) *near a connection-type
    label*, whereas the siblings show "Normal"/"1480"/"Auto" and nav links /
    section headers whose text is a mode word (a sidebar "IPv6" entry) have no
    such label nearby.  The scan tags that element and we return a Locator to
    it.  The adapter opens it like any combobox.  Returns a Locator or None.

    Declines a *card strip / segmented picker* (a row of clickable cards, each
    showing a distinct mode) -- there the "value" is a whole option list, so
    treating the first card as the current value would be a zero-click false
    positive.  Such shapes report needs_recording instead (pin a selector).
    """
    inv = _dial_widget_scan(ctx)
    if not inv or not inv.get("tagged"):
        return None
    try:
        return first_visible(ctx.locator("[data-dialsw-trigger='1']"))
    except Exception:
        return None


def find_mode_option(ctx, mode: str):
    """Locate the popup option for `mode` after a combobox has been opened."""
    rx = _regex_for(DIAL_MODE_SYNONYMS[mode])
    try:
        el = first_visible(ctx.get_by_role("option", name=rx))
        if el:
            return el
    except Exception:
        pass
    # portaled `<li>`/`<div>` options without an option role: match exact text
    try:
        return first_visible(ctx.get_by_text(rx, exact=False))
    except Exception:
        return None


def find_dial_mode_radio(ctx, mode: str):
    """Fallback: a radio button / label whose text names the target mode."""
    rx = _regex_for(DIAL_MODE_SYNONYMS[mode])
    try:
        el = first_visible(ctx.get_by_role("radio", name=rx))
        if el:
            return el
    except Exception:
        pass
    # label text that sits next to a radio input
    try:
        return first_visible(ctx.get_by_text(rx))
    except Exception:
        return None
