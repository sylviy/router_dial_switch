"""One-shot diagnostic evidence for an unknown router UI.

When the engine fails on a new model, the expensive part has always been the
*manual* archaeology: drive the browser by hand, count widgets, notice the one
whose value reads as a mode, spot that the apply button is labelled "Connect"
rather than "Save".  This module does all of that in a single pass and writes a
structured artifact, so a failing run *is* the diagnostic run.

Design: **the in-page scan only PROPOSES; Python VERIFIES.**  The scan gathers
raw facts (tags, classes, nearby labels, structural paths) but decides nothing
about selector uniqueness.  Python assembles selector strings and checks each
with `frame.locator(sel).count()` -- the very engine `adapter._locate_by_selector`
uses at runtime -- so a reported `unique: true` is a promise about the real code
path, and Playwright-only syntax (`:has-text()`, `>>`) is validated too.  That is
exactly what the old `tools/find_dial_selector.js` got wrong: it emitted
`tag.class` selectors and never counted them.

All vocabulary (mode words, connection-type labels, save-button words) is pulled
from `engine.heuristics`, never re-copied -- extend the tables there and this
follows automatically.
"""
from __future__ import annotations

import json
import os
import re
import time
from typing import List

from engine import heuristics as H


# --------------------------------------------------------------------------
# In-page scan: gathers raw facts about one frame.  Proposes NOTHING about
# uniqueness -- it only reports what it sees.  Python turns this into verified
# selectors afterwards.
# --------------------------------------------------------------------------
_SCAN_JS = r"""
(args) => {
  const groups = Object.keys(args.modeGroups).map(
    k => ({mode: k, rx: new RegExp(args.modeGroups[k], 'i')}));
  const anyModeRx = new RegExp(args.modeRx, 'i');
  const connRx = new RegExp(args.connRx, 'i');
  const norm = s => (s || '').replace(/\s+/g, ' ').trim();
  const visible = el => !!(el.offsetParent || el.getClientRects().length);
  const classify = t => { for (const g of groups) if (g.rx.test(t)) return g.mode;
                          return null; };
  // A stable-ish class chain: drop hash-looking classes (any digit) so we don't
  // pin on a build hash.  Returns e.g. ".v-select.v-select--medium" or "".
  const classChain = el => {
    const cls = (el.className || '').toString().trim().split(/\s+/)
      .filter(c => c && !/[0-9]/.test(c));
    return cls.length ? '.' + cls.join('.') : '';
  };
  const tagClass = el => el.tagName.toLowerCase() + classChain(el);
  // value text: custom selects often render the current value into a readonly
  // <input>, whose innerText is empty -- read .value in that case.
  const valueText = el => el.tagName.toLowerCase() === 'input'
    ? norm(el.value) : norm(el.innerText);
  // A structural path (nth-of-type chain) -- always unique, always fragile.
  const structural = el => {
    const parts = [];
    let e = el;
    while (e && e.nodeType === 1 && e.tagName.toLowerCase() !== 'html') {
      let sel = e.tagName.toLowerCase();
      if (e.id) { parts.unshift('#' + e.id); break; }
      const par = e.parentElement;
      if (par) {
        const same = [...par.children].filter(c => c.tagName === e.tagName);
        if (same.length > 1) sel += ':nth-of-type(' + (same.indexOf(e) + 1) + ')';
      }
      parts.unshift(sel);
      e = e.parentElement;
    }
    return parts.join(' > ');
  };
  // The nearest connection-type-ish label text near an element, plus the chain
  // of ancestors (with class chains) up to it -- Python turns these into
  // label-anchored selectors and verifies which is unique.
  const nearby = el => {
    let p = el, label = '', ancestors = [];
    for (let i = 0; i < 6 && p; i++) {
      const tc = tagClass(p);
      ancestors.push({tagClass: tc, hasClass: classChain(p).length > 0});
      if (!label) {
        for (const d of p.querySelectorAll('*')) {
          const t = norm(d.innerText);
          if (t && t.length < 40 && connRx.test(t)) { label = t; break; }
        }
      }
      p = p.parentElement;
    }
    return {label: label, ancestors: ancestors};
  };

  const isModeLeaf = el => {
    const t = valueText(el);
    if (!(t.length > 0 && t.length < 24 && anyModeRx.test(t))) return false;
    for (const c of el.children) {
      const ct = norm(c.innerText);
      if (ct.length > 0 && ct.length < 24 && anyModeRx.test(ct)) return false;
    }
    return true;
  };

  // ---- counts + shadow DOM presence ----
  let shadowHosts = 0;
  document.querySelectorAll('*').forEach(e => { if (e.shadowRoot) shadowHosts++; });
  const selects = document.querySelectorAll('select').length;
  const comboboxes = document.querySelectorAll('[role="combobox"]').length;

  // ---- dial-control candidates ----
  const cands = [];
  const pushCand = (el, kind) => {
    const info = nearby(el);
    cands.push({
      kind: kind, tag: el.tagName.toLowerCase(),
      id: el.id || null, name: el.getAttribute('name') || null,
      className: (el.className || '').toString(),
      tagClass: tagClass(el), text: valueText(el),
      mode: classify(valueText(el)),
      nearbyLabel: info.label, ancestors: info.ancestors,
      structural: structural(el),
    });
  };
  // native <select> with >=2 recognisable modes (incl. hidden/beautified ones)
  document.querySelectorAll('select').forEach(s => {
    const modes = new Set();
    [...s.options].forEach(o => { const m = classify(norm(o.textContent));
                                  if (m) modes.add(m); });
    if (modes.size >= 2) pushCand(s, 'select');
  });
  // role=combobox
  document.querySelectorAll('[role="combobox"]').forEach(c => {
    if (visible(c)) pushCand(c, 'combobox');
  });
  // role-less value-is-a-mode leaves (Tenda) + a card-strip flag
  const leaves = [...document.querySelectorAll('div,span,a,button,li,p,input')]
    .filter(el => visible(el) && isModeLeaf(el));
  const byParent = new Map();
  leaves.forEach(el => {
    const m = classify(valueText(el)), p = el.parentElement;
    if (!p) return;
    let set = byParent.get(p); if (!set) { set = new Set(); byParent.set(p, set); }
    if (m) set.add(m);
  });
  let cardStrip = false;
  byParent.forEach(set => { if (set.size >= 2) cardStrip = true; });
  leaves.forEach(el => pushCand(el, 'widget-leaf'));

  // ---- readonly inputs whose value reads as a mode (widget scan can't see
  //      these via innerText -- flag so the user knows to pin) ----
  const readonlyModeInputs = [];
  document.querySelectorAll('input').forEach(el => {
    if (!visible(el)) return;
    const v = norm(el.value);
    if (v && v.length < 24 && anyModeRx.test(v))
      readonlyModeInputs.push({value: v, id: el.id || null,
                               name: el.getAttribute('name') || null,
                               structural: structural(el)});
  });

  // ---- enable-switch-ish elements (a section may only render once a toggle
  //      is ON, e.g. Tenda's IPv6 switch -- pin selectors.enable_toggle) ----
  const toggles = [];
  const seenT = new Set();
  document.querySelectorAll(
    "input[type=checkbox], [role=switch], [role=checkbox], [aria-checked], " +
    "[aria-pressed], [class*='switch'], [class*='toggle'], [class*='slider'], " +
    "[class*='onoff'], [class*='enable']"
  ).forEach(el => {
    if (!visible(el) || seenT.has(el)) return;
    seenT.add(el);
    let state = null;
    if (el.tagName.toLowerCase() === 'input') state = !!el.checked;
    else {
      const ac = el.getAttribute('aria-checked') ?? el.getAttribute('aria-pressed');
      if (ac !== null) state = (ac === 'true');
      else {
        const toks = ((el.className || '') + '').toLowerCase().split(/[^a-z0-9]+/);
        if (['checked', 'on', 'active', 'open', 'enabled']
            .some(t => toks.includes(t))) state = true;
      }
    }
    let label = '', p = el.parentElement;
    for (let i = 0; i < 3 && p && !label; i++) {
      const t = norm(p.innerText);
      if (t && t.length < 30) label = t;
      p = p.parentElement;
    }
    toggles.push({tag: el.tagName.toLowerCase(), id: el.id || null,
                  name: el.getAttribute('name') || null,
                  className: (el.className || '') + '', tagClass: tagClass(el),
                  state: state, label: label, structural: structural(el)});
  });

  // ---- visible clickables (for save-button triage) ----
  const clicks = [];
  const seen = new Set();
  document.querySelectorAll(
    "button, input[type=submit], input[type=button], a, [role=button]"
  ).forEach(el => {
    if (!visible(el) || seen.has(el)) return;
    seen.add(el);
    const t = el.tagName.toLowerCase() === 'input' ? norm(el.value) : norm(el.innerText);
    if (!t || t.length > 40) return;
    clicks.push({tag: el.tagName.toLowerCase(), text: t,
                 id: el.id || null, name: el.getAttribute('name') || null,
                 structural: structural(el)});
  });

  return {url: location.href, selects: selects, comboboxes: comboboxes,
          shadowHosts: shadowHosts, cardStrip: cardStrip, leafCount: leaves.length,
          candidates: cands, clickables: clicks, toggles: toggles,
          readonlyModeInputs: readonlyModeInputs};
}
"""


def _scan_args() -> dict:
    return {
        "modeRx": "|".join(re.escape(w) for w in H._all_mode_synonyms()),
        "connRx": "|".join(re.escape(w) for w in H.CONNECTION_TYPE_SYNONYMS),
        "modeGroups": {canon: "|".join(re.escape(w) for w in syns)
                       for canon, syns in H.DIAL_MODE_SYNONYMS.items()},
    }


def _q(text: str) -> str:
    """Quote a label for a Playwright :has-text("...") clause."""
    return text.replace("\\", "").replace('"', "").strip()


def _candidate_selectors(cand: dict) -> List[str]:
    """Assemble selector strings for a raw candidate, most-stable first.

    Includes label-anchored Playwright selectors (`:has-text()`) -- the form that
    pins Tenda's role-less widget, which has NO unique plain-CSS selector.  Python
    verifies each; the caller keeps every count, never a bare selector.
    """
    sels: List[str] = []
    tag = cand.get("tag") or "*"
    tag_class = cand.get("tagClass") or tag
    if cand.get("id"):
        sels.append("#" + cand["id"])
    if cand.get("name"):
        sels.append("%s[name='%s']" % (tag, cand["name"]))
    if tag_class != tag:                       # has a class chain
        sels.append(tag_class)
    label = cand.get("nearbyLabel")
    if label:
        anchor = _q(label)
        for anc in cand.get("ancestors", []):
            if anc.get("hasClass") and anc.get("tagClass"):
                sels.append('%s:has-text("%s") %s'
                            % (anc["tagClass"], anchor, tag_class))
    if cand.get("structural"):
        sels.append(cand["structural"])
    # de-dup, preserve order
    out, seen = [], set()
    for s in sels:
        if s not in seen:
            seen.add(s)
            out.append(s)
    return out


def _verify(frame, selectors: List[str]) -> List[dict]:
    """Count matches for each proposed selector via the real Playwright engine."""
    tried = []
    for sel in selectors:
        try:
            tried.append({"selector": sel, "count": frame.locator(sel).count()})
        except Exception as exc:
            tried.append({"selector": sel, "count": None, "error": str(exc)[:80]})
    return tried


def _pin_for(tried: List[dict], cand: dict) -> dict:
    """Decide whether a pinnable unique selector exists, and recommend one."""
    unique = next((t for t in tried if t.get("count") == 1), None)
    if unique:
        # prefer a label-anchored / id / name selector over a fragile structural
        # path when more than one is unique
        uniques = [t for t in tried if t.get("count") == 1]
        stable = next((t for t in uniques if ":has-text(" in t["selector"]
                       or t["selector"].startswith("#")
                       or "[name=" in t["selector"]), None)
        rec = (stable or unique)["selector"]
        note = ("Pin selectors.dial_mode_select to this (verified count==1). "
                "Plain-CSS forms that matched >1 are listed above.")
        return {"available": True, "recommended": rec, "note": note}
    return {
        "available": False, "recommended": None,
        "note": ("selectors.dial_mode_select CANNOT be used for this candidate -- "
                 "no proposed selector matched exactly one element. The widget "
                 "heuristic (value-text) is the only path, or add a label to the "
                 "page structure."),
    }


def collect(page) -> dict:
    """Gather one structured evidence bundle across ALL frames.

    Reuses the real heuristics (`find_dial_mode_*`) to report which detection
    strategy fires and why -- so this can never drift from actual behaviour.
    """
    args = _scan_args()
    save_rx = H._regex_for(H.BUTTON_SAVE_SYNONYMS)
    excl_rx = H._regex_for(H.BUTTON_SAVE_EXCLUDE)

    frames_out: List[dict] = []
    dial_candidates: List[dict] = []
    clickables: List[dict] = []
    toggles: List[dict] = []
    readonly_inputs: List[dict] = []
    total_selects = total_comboboxes = total_shadow = 0
    save_match_found = False

    for idx, fr in enumerate(page.frames):
        try:
            data = fr.evaluate(_SCAN_JS, args)
        except Exception as exc:
            frames_out.append({"index": idx, "error": str(exc)[:120]})
            continue
        total_selects += data.get("selects", 0)
        total_comboboxes += data.get("comboboxes", 0)
        total_shadow += data.get("shadowHosts", 0)

        for cand in data.get("candidates", []):
            tried = _verify(fr, _candidate_selectors(cand))
            dial_candidates.append({
                "frame": idx, "kind": cand.get("kind"), "tag": cand.get("tag"),
                "id": cand.get("id"), "name": cand.get("name"),
                "class": cand.get("className"), "text": cand.get("text"),
                "matched_mode": cand.get("mode"),
                "nearby_label": cand.get("nearbyLabel"),
                "selectors": tried, "pin": _pin_for(tried, cand),
            })
        for clk in data.get("clickables", []):
            txt = H.normalize(clk.get("text") or "")
            ms = bool(txt and save_rx.search(txt))
            mx = bool(txt and excl_rx and excl_rx.search(txt))
            if ms and not mx:
                save_match_found = True
            sel = None
            if clk.get("id"):
                sel = "#" + clk["id"]
            elif clk.get("name"):
                sel = "%s[name='%s']" % (clk.get("tag") or "*", clk["name"])
            elif clk.get("structural"):
                sel = clk["structural"]
            count = None
            if sel:
                try:
                    count = fr.locator(sel).count()
                except Exception:
                    count = None
            clickables.append({
                "frame": idx, "tag": clk.get("tag"), "text": clk.get("text"),
                "matched_save": ms, "matched_exclude": mx,
                "selector": sel, "count": count,
            })
        for tg in data.get("toggles", []):
            tried = _verify(fr, _candidate_selectors(tg))
            unique = next((t["selector"] for t in tried
                           if t.get("count") == 1), None)
            toggles.append({
                "frame": idx, "tag": tg.get("tag"), "label": tg.get("label"),
                "state": tg.get("state"), "class": tg.get("className"),
                "selector": unique, "selectors": tried,
            })
        for ri in data.get("readonlyModeInputs", []):
            readonly_inputs.append({"frame": idx, **ri})

        frames_out.append({
            "index": idx, "url": data.get("url"),
            "selects": data.get("selects"), "comboboxes": data.get("comboboxes"),
            "shadow_hosts": data.get("shadowHosts"),
            "mode_leaves": data.get("leafCount"), "card_strip": data.get("cardStrip"),
            "clickables": len(data.get("clickables", [])),
        })

    strategies = _strategies(page)
    pin_available = any(c["pin"]["available"] for c in dial_candidates)
    dial_found = next((s for s in strategies if s["fired"]), None)
    card_strip = any(f.get("card_strip") for f in frames_out)

    verdict = {
        "dial_control": ("found-by-%s" % dial_found["name"]) if dial_found
                        else ("card-strip (unsupported)" if card_strip
                              else "NOT-FOUND"),
        "pin_available": pin_available,
        "save_button": "OK" if save_match_found else "NO-MATCH",
        "next_actions": _next_actions(dial_found, pin_available, save_match_found,
                                      clickables, dial_candidates, readonly_inputs,
                                      total_shadow, card_strip, toggles),
    }
    return {
        "url": page.url, "verdict": verdict, "frames": frames_out,
        "strategies": strategies, "dial_candidates": dial_candidates,
        "clickables": clickables, "toggles": toggles,
        "readonly_mode_inputs": readonly_inputs,
    }


def _strategies(page) -> List[dict]:
    """Report, per strategy, whether it fires on this page and (if not) why --
    by calling the REAL heuristics across all frames."""
    out = []
    # select
    hit = _first_frame(page, H.find_dial_mode_select)
    out.append({"name": "select", "fired": bool(hit),
                "why": "native <select> with >=2 recognisable modes"
                       if hit else "no <select> with >=2 recognisable mode options"})
    # combobox
    hit = _first_frame(page, H.find_dial_mode_combobox)
    out.append({"name": "combobox", "fired": bool(hit),
                "why": "role=combobox whose label/value reads as connection type"
                       if hit else "no role=combobox found (both branches of "
                       "find_dial_mode_combobox gate on role=combobox)"})
    # widget (with card-strip reason)
    hit = _first_frame(page, H.find_dial_mode_widget)
    why = "exactly one element whose value text reads as a dial mode"
    if not hit:
        inv = None
        for fr in page.frames:
            inv = H._dial_widget_scan(fr)
            if inv and (inv.get("leafCount") or inv.get("cardStrip")):
                break
        if inv and inv.get("cardStrip"):
            why = ("declined: %d mode-leaves show %d distinct modes under one "
                   "parent -> looks like a card strip / option list, not a value "
                   "display" % (inv.get("leafCount", 0),
                                len(inv.get("distinctModes", []))))
        else:
            why = "no element whose value text reads as a dial mode"
    out.append({"name": "widget", "fired": bool(hit), "why": why})
    return out


def _first_frame(page, fn):
    for fr in page.frames:
        try:
            if fn(fr):
                return True
        except Exception:
            continue
    return False


def _next_actions(dial_found, pin_available, save_ok, clickables,
                  dial_candidates, readonly_inputs, shadow_hosts,
                  card_strip=False, toggles=None) -> List[str]:
    acts: List[str] = []
    if not dial_found:
        off = [t for t in (toggles or []) if t.get("state") is not True]
        if off:
            acts.append("An enable switch may gate this section (%s). If the "
                        "page only renders its settings once a switch is ON, "
                        "pin selectors.enable_toggle to it -- the engine flips "
                        "it on (only when the dial control is absent)."
                        % "; ".join("'%s' state=%s selector=%s"
                                    % (t.get("label"), t.get("state"),
                                       t.get("selector")) for t in off[:3]))
        if card_strip:
            # A single dial_mode_select pin canNOT drive a card strip -- each mode
            # is a separate clickable card. Be honest rather than recommend a pin
            # that won't work.
            acts.append("This is a card strip / segmented picker (a row of "
                        "clickable mode cards). No current strategy handles it, "
                        "and a single selectors.dial_mode_select pin will NOT work "
                        "(each mode is its own card). This needs new "
                        "'selected-among-siblings' heuristic support -- file it as "
                        "a feature request. The per-card selectors below are for "
                        "reference only.")
        elif pin_available:
            rec = next((c["pin"]["recommended"] for c in dial_candidates
                        if c["pin"]["available"]), None)
            acts.append("No detection strategy fired, but a unique selector "
                        "exists. Pin it: selectors.dial_mode_select: '%s'" % rec)
        elif dial_candidates:
            acts.append("A dial-mode value was seen but NO unique selector exists "
                        "(see dial_candidates[].pin). This model needs the widget "
                        "heuristic or a page-structure label; plain pinning is "
                        "unavailable.")
        else:
            acts.append("No dial-mode control seen on this page. Check you reached "
                        "the WAN page (add wan_path:) or that it isn't in a closed "
                        "shadow root.")
    if not save_ok:
        cand = ", ".join('"%s"' % c["text"] for c in clickables
                         if not c["matched_exclude"])[:200]
        acts.append("No visible clickable matched BUTTON_SAVE_SYNONYMS. Candidates: "
                    "[%s]. If one of these applies the WAN change, add its wording "
                    "to heuristics.BUTTON_SAVE_SYNONYMS (all brands benefit) or pin "
                    "selectors.save_button." % cand)
    if readonly_inputs:
        acts.append("A readonly <input> shows a mode value (%s) -- the widget scan "
                    "reads innerText and can miss this; pin selectors.dial_mode_"
                    "select if it's the control."
                    % ", ".join('"%s"' % r["value"] for r in readonly_inputs))
    if shadow_hosts:
        acts.append("%d shadow-DOM host(s) present. Playwright locators pierce OPEN "
                    "shadow roots (pinning still works); closed roots are opaque."
                    % shadow_hosts)
    return acts


def summarize(page) -> str:
    """A short, all-frames 'what did we see' note for adapter failure messages.

    Replaces the old main-frame-only _diag(): counts every frame, and reports
    whether any clickable looks like a save button (which the old note never
    did -- that is why Tenda's "Connect" button went unnoticed)."""
    args = _scan_args()
    save_rx = H._regex_for(H.BUTTON_SAVE_SYNONYMS)
    excl_rx = H._regex_for(H.BUTTON_SAVE_EXCLUDE)
    selects = comboboxes = shadow = 0
    widget = save = False
    for fr in page.frames:
        try:
            data = fr.evaluate(_SCAN_JS, args)
        except Exception:
            continue
        selects += data.get("selects", 0)
        comboboxes += data.get("comboboxes", 0)
        shadow += data.get("shadowHosts", 0)
        # ask the REAL heuristic, so this note can't drift from behaviour (the
        # raw leaf count includes unlabeled matches the heuristic rejects,
        # e.g. a sidebar "IPv6" nav link)
        try:
            if H.find_dial_mode_widget(fr):
                widget = True
        except Exception:
            pass
        for clk in data.get("clickables", []):
            txt = H.normalize(clk.get("text") or "")
            if txt and save_rx.search(txt) and not (excl_rx and excl_rx.search(txt)):
                save = True
    return (" (all frames: %d <select>, %d role=combobox, value-mode widget: %s, "
            "save-button match: %s, shadow hosts: %d, at %s)"
            % (selects, comboboxes, "yes" if widget else "no",
               "yes" if save else "no", shadow, page.url))


def write_artifact(data: dict, out_dir: str, label: str = "") -> str:
    """Write the JSON evidence bundle (+ per-frame HTML) and return the JSON path.

    NOTE: the per-frame HTML dumps and the JSON can contain session tokens or
    form values -- treat them as sensitive before pasting into a ticket."""
    os.makedirs(out_dir, exist_ok=True)
    stamp = time.strftime("%Y%m%d_%H%M%S")
    base = "diagnose_%s%s" % (stamp, ("_" + label) if label else "")
    json_path = os.path.join(out_dir, base + ".json")
    with open(json_path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2)
    return json_path


def render_text(data: dict) -> str:
    """A compact human-readable verdict for stdout (no need to open the JSON)."""
    v = data["verdict"]
    lines = ["=== diagnose: %s ===" % data.get("url", "")]
    lines.append("dial control : %s   pin available: %s   save button: %s"
                 % (v["dial_control"], v["pin_available"], v["save_button"]))
    for s in data["strategies"]:
        lines.append("  strategy %-9s fired=%-5s  %s"
                     % (s["name"], str(s["fired"]).lower(), s["why"]))
    for c in data["dial_candidates"]:
        uniq = next((t["selector"] for t in c["selectors"]
                     if t.get("count") == 1), None)
        lines.append("  candidate [%s] text=%r label=%r pin=%s"
                     % (c["kind"], c["text"], c["nearby_label"],
                        uniq or "NONE-UNIQUE"))
    saves = [c for c in data["clickables"] if c["matched_save"]
             and not c["matched_exclude"]]
    if not saves:
        cand = ", ".join('%r' % c["text"] for c in data["clickables"])
        lines.append("  save button  : NO MATCH among clickables [%s]" % cand)
    for t in data.get("toggles", []):
        lines.append("  toggle       : %r state=%s selector=%s"
                     % (t.get("label"), t.get("state"), t.get("selector")))
    lines.append("next actions:")
    for a in v["next_actions"]:
        lines.append("  - " + a)
    return "\n".join(lines)


def run(page, out_dir: str, label: str = "", to_stdout: bool = True) -> dict:
    """Collect + write the artifact; optionally print the compact verdict."""
    data = collect(page)
    path = write_artifact(data, out_dir, label=label)
    data["artifact"] = path
    if to_stdout:
        print(render_text(data))
        print("evidence written to: %s" % path)
    return data
