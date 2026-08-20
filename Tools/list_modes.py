"""第 2 步:把拨号控件的**所有选项按界面原话**列出来。只读,不选中任何一项。

    python Tools/list_modes.py --menu "sel:#Network,sel:#WAN" --dial "#wanType_id"

stdout 一行一个选项,**逐字照抄界面**(大小写、空格、括号都不许动)——
那些字后面要原样写进 FACTS.modes,回读比对是精确相等,差一个字符就判失败。

通过条件:选项数 ≥ 2。只有一个选项的控件不可能是拨号方式选择器,
多半选到了别的下拉(MTU / DNS / 克隆 MAC 之类)。

退出码:0 = 选项数 ≥2 / 1 = 少于 2 或没找到控件 / 2 = 用法错误
"""
from __future__ import annotations

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import _probe                                              # noqa: E402


def main(argv=None):
    ap = _probe.base_parser(__doc__.splitlines()[0])
    ap.add_argument("--dial", required=True, help="拨号控件的选择器")
    ap.add_argument("--kind", choices=["select", "dropdown"], default=None,
                    help="控件形态;不给就自己判断(原生 <select> vs 自定义下拉)")
    ap.add_argument("--json", action="store_true", help="stdout 输出 JSON")
    args = ap.parse_args(argv)
    cfg = _probe.load_cfg(args)

    with _probe.Page(cfg, args) as session:
        page = session.page
        if not session.login():
            return _probe.FAIL
        session.walk_menu()
        _probe._pause(page, 600)

        # 原生 <select> 可能被美化插件藏起来(display:none),所以 visible=False
        el = _probe._find(page, args.dial, wait_ms=_probe.DIAL_MS, visible=False)
        if el is None:
            _probe.say("没找到这个控件:%s —— 先用 probe_dump.py 看清单里它长什么样。"
                       % args.dial)
            return _probe.FAIL

        kind = args.kind
        if kind is None:
            try:
                kind = "select" if el.evaluate(
                    "e => e.tagName.toLowerCase()") == "select" else "dropdown"
            except Exception:
                kind = "dropdown"

        if kind == "select":
            try:
                options = el.evaluate(
                    "e => Array.from(e.options).map(o => o.text)")
            except Exception as exc:
                _probe.say("读不出选项(%s)—— 它可能不是原生 <select>,"
                           "试试 --kind dropdown。" % exc)
                return _probe.FAIL
        else:
            # 自定义下拉:得**点开**才能看到选项层。只点开、不选中。
            try:
                el.click()
            except Exception as exc:
                _probe.say("点不开这个下拉:%s" % str(exc).splitlines()[0])
                return _probe.FAIL
            _probe._pause(page, 500)
            options = []
            for fr in list(page.frames):
                try:
                    loc = fr.locator("[role='option'], [class*='opt']")
                    for i in range(min(loc.count(), 40)):
                        item = loc.nth(i)
                        if not item.is_visible():
                            continue
                        text = (item.inner_text() or "").strip()
                        # 整包 wrapper 的 text 是所有选项拼一起,靠长度和换行排除
                        if text and "\n" not in text and len(text) < 40 \
                                and text not in options:
                            options.append(text)
                except Exception:
                    continue

    options = [o.strip() for o in options if o and o.strip()]
    if args.json:
        print(json.dumps({"dial": args.dial, "kind": kind,
                          "options": options}, ensure_ascii=False, indent=2))
    else:
        for opt in options:
            print(opt)

    _probe.say("\n控件形态:%s,选项 %d 个。" % (kind, len(options)))
    if len(options) < 2:
        _probe.say("**选项少于 2 个,这多半不是拨号方式选择器。** 回 "
                   "probe_dump.py 的清单里换一个 —— 同一页上 MTU / DNS / "
                   "MAC 克隆常常也是下拉,长得一模一样。")
        return _probe.FAIL
    _probe.say("这几个字**要逐字**写进 FACTS.modes(回读是精确相等比对)。")
    _probe.say("下一步:probe_count.py 确认这个选择器在页面上只命中 1 个。")
    return _probe.PASS


if __name__ == "__main__":
    sys.exit(main())
