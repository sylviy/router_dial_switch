"""第 1 步:登录 → 走菜单 → 把这一页上的**控件全抄下来**。只读,不点任何设置。

    python Tools/probe_dump.py --menu "sel:#Network,sel:#WAN"
    python Tools/probe_dump.py --menu "Internet Settings" --show

stdout 一行一个控件:类型 | 可见文字 | 关键属性 | 所在文档。
同一份内容(带完整属性和下拉选项)存进 artifacts/probe_<地址>.json,
后面 make_facts.py 直接读它。

通过条件:清单里**存在拨号类控件**(有 ≥2 个选项的 <select>,或 radio,
或自定义下拉)。没有 = 多半还停在首页,补 --menu 把菜单路径走到 WAN 设置页。

退出码:0 = 找到了拨号类控件 / 1 = 没找到 / 2 = 用法错误
"""
from __future__ import annotations

import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import _probe                                              # noqa: E402


def _short(row):
    """一行摘要:类型 | 可见文字 | 关键属性 | 所在文档。"""
    attrs = row.get("attrs") or {}
    keys = [k for k in ("id", "name", "data-name", "role", "type", "class")
            if k in attrs]
    attr_text = " ".join("%s=%s" % (k, attrs[k]) for k in keys[:3])
    doc = (row.get("frame") or "").rsplit("/", 1)[-1] or "(主文档)"
    text = row.get("text") or ""
    if row.get("options"):
        text = "选项: " + " / ".join(row["options"][:6])
    return "%-9s %-34s %-46s %s" % (row["kind"], text[:34], attr_text[:46], doc)


def main(argv=None):
    ap = _probe.base_parser(__doc__.splitlines()[0])
    ap.add_argument("--out", default=None, help="存盘路径(默认 artifacts/probe_<地址>.json)")
    ap.add_argument("--all", action="store_true",
                    help="连隐藏控件也列出来(默认只列看得见的)")
    args = ap.parse_args(argv)
    cfg = _probe.load_cfg(args)
    if not _probe.url_of(cfg):
        _probe.say("没有地址:config.yaml 的 router.ip 没填,也没给 --ip。")
        return _probe.USAGE

    with _probe.Page(cfg, args) as session:
        if not session.login():
            return _probe.FAIL
        session.walk_menu()
        _probe._pause(session.page, 600)
        rows = _probe.dump_controls(session.page)
        page_url = session.page.url

    shown = [r for r in rows if r.get("visible") or args.all]
    print("%-9s %-34s %-46s %s" % ("类型", "可见文字 / 选项", "关键属性", "所在文档"))
    for row in shown:
        print(_short(row))

    dial = [r for r in rows if _probe.looks_like_dial(r)]
    out = args.out or os.path.join(
        _probe.OUT_ROOT, "artifacts", "probes",
        "probe_%s.json" % re.sub(r"[^A-Za-z0-9]+", "_",
                                 _probe.url_of(cfg)).strip("_"))
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", encoding="utf-8") as fh:
        json.dump({"url": page_url, "menu": args.menu, "controls": rows},
                  fh, ensure_ascii=False, indent=2)
    _probe.say("\n共 %d 个控件(看得见的 %d 个),已存 %s"
               % (len(rows), len(shown), out))

    if not dial:
        _probe.say("**没有看到拨号类控件。** 十有八九还停在首页 —— 用 --menu 把"
                   "菜单路径走到 WAN 设置页(文字菜单直接写文字,要用选择器就加"
                   " sel: 前缀)。也可能这页的控件在 iframe 里而登录没成功,"
                   "看上面 [login] 那行。")
        return _probe.FAIL
    _probe.say("像拨号控件的有 %d 个:" % len(dial))
    for row in dial:
        _probe.say("   " + _short(row))
    _probe.say("下一步:挑一个,用 list_modes.py 看它的选项是不是拨号方式。")
    return _probe.PASS


if __name__ == "__main__":
    sys.exit(main())
