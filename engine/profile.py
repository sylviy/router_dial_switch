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
