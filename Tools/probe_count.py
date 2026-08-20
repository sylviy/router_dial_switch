"""第 3 步:一批选择器,各命中几个。**每个恰好 1 才算过。**

    python Tools/probe_count.py --menu "sel:#Network,sel:#WAN" \\
        --sel "#wanType_id" --sel "input[name='save_apply']" \\
        --sel "input[name='pppUserName']"

为什么非要恰好 1:命中 0 = 脚本跑起来会说"没找到";命中 2 以上 = 脚本会点
**第一个**,而第一个不一定是你要的那个 —— 那种错不会报错,只会切错东西。
真机上踩过:同一页 4 个 name=cbi.apply(LuCI),8 个隐藏的 Connect 提交按钮
(Cudy)。收窄的办法是用它**所在的表单**或**旁边的标签文字**锚定,例如
`form:has([id='cbid.network.wan.proto']) button[name='cbi.apply']`。

数的是**所有 frame 加起来**的命中数,和型号脚本查找的范围一致。

退出码:0 = 每个都恰好 1 / 1 = 有不是 1 的 / 2 = 用法错误
"""
from __future__ import annotations

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import _probe                                              # noqa: E402


def count_all(page, sel):
    """所有 frame 里的命中数,外加"其中看得见几个"。"""
    total = visible = 0
    where = []
    for fr in list(page.frames):
        try:
            loc = fr.locator(sel)
            n = loc.count()
        except Exception:
            continue
        if not n:
            continue
        total += n
        for i in range(min(n, 25)):
            try:
                if loc.nth(i).is_visible():
                    visible += 1
            except Exception:
                pass
        where.append((fr.url.rsplit("/", 1)[-1] or "(主文档)", n))
    return total, visible, where


def main(argv=None):
    ap = _probe.base_parser(__doc__.splitlines()[0])
    ap.add_argument("--sel", action="append", default=[], metavar="选择器",
                    help="要数的选择器,可以给多次")
    ap.add_argument("--json", action="store_true", help="stdout 输出 JSON")
    args = ap.parse_args(argv)
    if not args.sel:
        _probe.say("至少给一个 --sel。")
        return _probe.USAGE
    cfg = _probe.load_cfg(args)

    rows = []
    with _probe.Page(cfg, args) as session:
        if not session.login():
            return _probe.FAIL
        session.walk_menu()
        _probe._pause(session.page, 600)
        for sel in args.sel:
            total, visible, where = count_all(session.page, sel)
            rows.append({"selector": sel, "count": total, "visible": visible,
                         "frames": where, "ok": total == 1})

    if args.json:
        print(json.dumps(rows, ensure_ascii=False, indent=2))
    else:
        print("%-6s %-7s %-9s %s" % ("命中", "其中可见", "结果", "选择器"))
        for row in rows:
            print("%-6d %-9d %-7s %s" % (row["count"], row["visible"],
                                         "OK" if row["ok"] else "BAD",
                                         row["selector"]))

    bad = [r for r in rows if not r["ok"]]
    for row in bad:
        if row["count"] == 0:
            _probe.say("[0] %s —— 没找到。可能菜单没走到位(--menu),"
                       "也可能选择器写错了(LuCI 的 id 含点号,只能用 "
                       "[id='...'],用 #... 会命中 0)。" % row["selector"])
        else:
            spread = ", ".join("%s×%d" % (f, n) for f, n in row["frames"])
            _probe.say("[%d] %s —— 命中多个(%s)。脚本会点**第一个**,而第一个"
                       "不一定是你要的。用它所在的表单或旁边的标签文字收窄,例:"
                       "form:has(<拨号控件>) <这个选择器>。"
                       % (row["count"], row["selector"], spread))
    if bad:
        return _probe.FAIL
    _probe.say("每个都恰好命中 1。下一步:act.py 真去试切一档。")
    return _probe.PASS


if __name__ == "__main__":
    sys.exit(main())
