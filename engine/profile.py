"""Optional per-brand profiles.

The engine runs on pure heuristics by default.  A profile is a *narrowing hint*
for models the heuristics can't handle unaided: it can pin the WAN-menu path or
override any concept's selector.  Missing keys simply fall back to heuristics,
so a profile can be as small as one line.

Profiles are matched loosely by brand/model/firmware so one file covers a family
of firmware revisions.  New brands are normally produced by `recorder.py`, not
hand-written.
"""
from __future__ import annotations

import glob
import os
from dataclasses import dataclass, field
from typing import Dict, Optional

try:
    import yaml
except Exception:  # pragma: no cover - yaml is a hard dep, guard for clarity
    yaml = None

PROFILE_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "profiles")


@dataclass
class Profile:
    brand: str = ""
    model: str = ""
    firmware: str = ""
    # optional CSS/text selector overrides, keyed by concept
    # e.g. {"dial_mode_select": "#wanType", "login_pass": "#pwd"}
    selectors: Dict[str, str] = field(default_factory=dict)
    # optional ordered list of menu labels to click to reach WAN settings
    wan_path: Optional[list] = None
    # map canonical mode -> the exact option label/value this model uses
    mode_labels: Dict[str, str] = field(default_factory=dict)
    source: str = ""  # file it came from

    def selector(self, concept: str) -> Optional[str]:
        return self.selectors.get(concept)


def _load_one(path: str) -> Optional[Profile]:
    if yaml is None:
        return None
    with open(path, "r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    if not isinstance(data, dict):
        return None
    return Profile(
        brand=str(data.get("brand", "")),
        model=str(data.get("model", "")),
        firmware=str(data.get("firmware", "")),
        selectors=dict(data.get("selectors", {}) or {}),
        wan_path=data.get("wan_path"),
        mode_labels=dict(data.get("mode_labels", {}) or {}),
        source=os.path.basename(path),
    )


def load_all(profile_dir: str = PROFILE_DIR):
    out = []
    # glob.escape the dir: real deployment paths can contain glob metacharacters
    # (e.g. a folder literally named "[Tool]..."), which would otherwise be
    # parsed as a character class and silently match nothing.
    pattern = os.path.join(glob.escape(profile_dir), "*.yaml")
    for path in sorted(glob.glob(pattern)):
        if os.path.basename(path).startswith("_"):
            continue  # skip _generic.yaml marker
        p = _load_one(path)
        if p:
            out.append(p)
    return out


def _score(p: Profile, brand: str, model: str, firmware: str) -> int:
    """Loose match score; higher wins.  Empty query fields don't penalise."""
    s = 0
    b, m, f = brand.lower(), model.lower(), firmware.lower()
    if b and p.brand and b in p.brand.lower():
        s += 4
    if m and p.model and m in p.model.lower():
        s += 2
    if f and p.firmware and f in p.firmware.lower():
        s += 1
    return s


def match(brand: str = "", model: str = "", firmware: str = "",
          profile_dir: str = PROFILE_DIR) -> Optional[Profile]:
    """Return the best-matching profile, or None to run pure heuristics."""
    candidates = load_all(profile_dir)
    best, best_score = None, 0
    for p in candidates:
        sc = _score(p, brand, model, firmware)
        if sc > best_score:
            best, best_score = p, sc
    return best


def _slug(text: str) -> str:
    return "".join(c if c.isalnum() else "_" for c in text).strip("_") or "auto"


def write_pin(brand: str, model: str, selectors: Dict[str, str],
              profile_dir: str = PROFILE_DIR,
              evidence: str = "") -> Optional[str]:
    """Write a minimal pin profile from verified diagnose selectors.

    This is the automated replacement for hand-editing profiles/*.yaml: the
    failing run's diagnose pass already produced selectors verified to match
    exactly one element, so the file can be generated instead of authored.

    Refuses to overwrite an existing file (it may be hand-tuned, with comments
    this dump would destroy) -- returns None in that case and the caller should
    show the snippet instead.
    """
    if yaml is None or not selectors:
        return None
    name = _slug(brand) + (("_" + _slug(model)) if model else "")
    path = os.path.join(profile_dir, name + ".yaml")
    if os.path.exists(path):
        return None
    os.makedirs(profile_dir, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("# Auto-generated pin profile (cli.py) -- selectors were "
                 "verified count==1 by diagnose\n")
        if evidence:
            fh.write("# evidence: %s\n" % evidence)
        fh.write("# The next run still read-backs the real control state; a "
                 "wrong pin fails honestly.\n")
        yaml.safe_dump({"brand": brand, "model": model,
                        "selectors": dict(selectors)},
                       fh, allow_unicode=True, sort_keys=False,
                       default_flow_style=False)
    return path
