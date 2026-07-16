"""Local run defaults (router.yaml) so the daily command shrinks to
`python cli.py pppoe`.

router.yaml lives next to this file, is created by `python cli.py setup`
(or by hand) and is git-ignored -- it holds the router's admin password and
broadband credentials, which must never be committed.

Recognised keys (all optional):

    router_ip: 192.168.1.1
    user: ""                 # admin username, if the router asks for one
    pass: admin123           # admin password
    brand: tenda             # profile hint, same as --brand
    model: ""                # profile hint, same as --model
    no_apply: false          # true = never click Save (safe default for tryout)
    headless: false
    params:                  # credentials picked per mode automatically
      pppoe_user: myaccount
      pppoe_pass: mypassword
      vpn_server: 1.2.3.4
      vpn_user: u
      vpn_pass: p

CLI flags always override these values.
"""
from __future__ import annotations

import os

try:
    import yaml
except Exception:  # pragma: no cover - yaml is a hard dep, guard for clarity
    yaml = None

SETTINGS_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                             "router.yaml")

_HEADER = (
    "# router.yaml -- local run defaults for cli.py (created by `cli.py setup`).\n"
    "# Contains credentials: git-ignored, do NOT commit or paste into tickets.\n"
    "# Any CLI flag overrides the value here.\n"
)


def load(path: str = SETTINGS_PATH) -> dict:
    """Return the settings dict, or {} when the file is missing/unreadable."""
    if yaml is None or not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = yaml.safe_load(fh) or {}
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def save(data: dict, path: str = SETTINGS_PATH) -> str:
    """Write (or rewrite) router.yaml; returns the path."""
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(_HEADER)
        yaml.safe_dump(data, fh, allow_unicode=True, sort_keys=False,
                       default_flow_style=False)
    return path
