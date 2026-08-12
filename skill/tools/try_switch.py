"""第 4 步:**真去试切一档**,把回读值打出来。这是写型号脚本之前的最后一关。

    python skill/tools/try_switch.py --menu "sel:#Network,sel:#WAN" \\
        --dial "#wanType_id" --label "PPPoE"
    python skill/tools/try_switch.py ... --label "PPPoE" --apply \\
        --apply-sel "input[name='save_apply']"

为什么要有这个工具:以前必须**先写完型号文件**才能试切一档,顺序是反的 ——
选择器对不对、措辞对不对,要等写完一整个文件才知道。有了它,探 → 列 → 验 →
试切全都发生在写文件之前,make_facts.py 只负责把已经验过的东西打印成骨架。

**默认只选中、不点保存**(和型号脚本默认行为一致)。加 --apply 才真下发,
而且要连 --apply-sel 一起给 —— 保存键必须是你自己验过命中 1 的那个,
工具不猜。

判定用的是 common/contract.py 的 verify(),**和型号脚本、和整轮报告是同一把
尺子**:规整首尾空白与大小写后精确相等,空回读永远判假,绝不放宽成包含
("PPPoEv6" 里有 "PPPoE",放宽一次就等于允许一份测错对象的报告)。

退出码:0 = 回读 == 目标措辞 / 1 = 不等 / 2 = 用法错误
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
from common import contract                                # noqa: E402

OPTION_CONTAINERS = "[role='option'], [class*='opt']"


def _value_match(text, label):
    """触发器上现在显示的是不是 label?整体精确相等,或**某一行**精确相等
    (trigger 里常混着下拉小图标等杂质文本)。逐行仍是精确匹配。"""
    norm = lambda s: " ".join((s or "").split()).lower()
    if norm(text) == norm(label):
        return (text or "").strip()
    for line in (text or "").splitlines():
        if norm(line) == norm(label):
            return line.strip()
    return None


def _switch_select(page, dial, label):
    el = _probe._find(page, dial, wait_ms=_probe.DIAL_MS, visible=False)
    if el is None:
        return "", "没找到拨号控件:%s" % dial
    try:
        el.select_option(label=label, force=True)
    except Exception as exc:
        try:
            seen = el.evaluate("e => Array.from(e.options).map(o => o.text).join(' / ')")
        except Exception:
            seen = ""
        return "", ("select_option(%r) 失败:%s%s"
                    % (label, str(exc).splitlines()[0],
                       "(选项有:%s)" % seen if seen else ""))
    _probe._pause(page)
    try:
        return (el.evaluate("e => e.options[e.selectedIndex]"
                            " ? e.options[e.selectedIndex].text : ''")
                or "").strip(), ""
    except Exception:
        return "", "选完了但读不回来 —— 它可能不是原生 <select>"


def _switch_dropdown(page, dial, label, value_sel, force):
    trigger = _probe._find(page, dial, wait_ms=_probe.DIAL_MS)
    if trigger is None:
        return "", "没找到拨号控件:%s" % dial
    try:
        current = trigger.inner_text()
    except Exception:
        current = ""
    hit = _value_match(current, label)
    if hit is not None:
        return hit, ""            # 已经就是目标:控件自己显示的值即真实回读
    trigger.click(force=force)
    _probe._pause(page)
    rx = re.compile(r"^\s*%s\s*$" % re.escape(label), re.IGNORECASE)
    option, waited = None, 0
    while option is None and waited < 3000:
        for fr in list(page.frames):
            try:
                loc = fr.locator(OPTION_CONTAINERS).filter(has_text=rx)
                for i in range(min(loc.count(), 25)):
                    if loc.nth(i).is_visible():
                        option = loc.nth(i)
                        break
            except Exception:
                continue
            if option is not None:
                break
        if option is None:
            _probe._pause(page, _probe.STEP_MS)
            waited += _probe.STEP_MS
    if option is None:
        option = _probe._find_text(page, label)
    if option is None:
        seen = []
        for fr in list(page.frames):
            try:
                loc = fr.locator(OPTION_CONTAINERS)
                for i in range(min(loc.count(), 12)):
                    t = (loc.nth(i).inner_text() or "").strip()
                    if t and len(t) < 30 and t not in seen:
                        seen.append(t)
            except Exception:
                continue
        return "", ("下拉打开了,但没找到选项 %r%s"
                    % (label, "(看到:%s)" % " / ".join(seen) if seen else ""))
    option.click(force=force)
    _probe._pause(page, 400)

    def read_now():
        el = _probe._find(page, value_sel or dial)
        try:
            return (el.inner_text() or "").strip() if el else ""
        except Exception:
            return ""

    waited = 0
    while _value_match(read_now(), label) is None and waited < 2000:
        _probe._pause(page, _probe.STEP_MS)
        waited += _probe.STEP_MS
    got = read_now()
    return (_value_match(got, label) or got), ""


def _switch_radio(page, radio_sel, mode, force):
    el = _probe._find(page, radio_sel, wait_ms=_probe.DIAL_MS)
    if el is None:
        return "", "没找到模式 radio:%s" % radio_sel
    try:
        el.click(force=force)
    except Exception as exc:
        return "", ("点不动这个 radio:%s%s"
                    % (str(exc).splitlines()[0],
                       "" if force else "(被别的元素盖住时加 --force)"))
    _probe._pause(page)
    try:
        checked = el.is_checked()
    except Exception:
        return "", "点了,但它不是可回读的 radio —— 选择器指错了"
    # radio 的"措辞"是个选择器,报出来没有意义 —— 回读记模式名。
    return (mode if checked else ""), ""


def main(argv=None):
    ap = _probe.base_parser(__doc__.splitlines()[0])
    ap.add_argument("--dial", required=True,
                    help="拨号控件的选择器;kind=radio 时是这一档自己的 radio 选择器")
    ap.add_argument("--label", required=True,
                    help="目标措辞,逐字照抄界面(kind=radio 时写模式名,如 v6plus)")
    ap.add_argument("--kind", choices=["select", "dropdown", "radio"],
                    default="select", help="控件形态(默认 select)")
    ap.add_argument("--value-sel", default=None,
                    help="回读值所在的子元素(自定义下拉常用,不给就读整个触发器)")
    ap.add_argument("--force", action="store_true",
                    help="控件被别的元素盖住时强行点(Buffalo 那类)")
    ap.add_argument("--apply", action="store_true",
                    help="**真正点保存**(默认只选中不下发)")
    ap.add_argument("--apply-sel", default=None, help="保存键选择器,--apply 时必须给")
    ap.add_argument("--json", action="store_true", help="stdout 输出 JSON")
    args = ap.parse_args(argv)
    if args.apply and not args.apply_sel:
        _probe.say("--apply 必须连 --apply-sel 一起给:保存键得是你自己用 "
                   "probe_count.py 验过命中 1 的那个,工具不猜。")
        return _probe.USAGE
    cfg = _probe.load_cfg(args)

    applied = False
    with _probe.Page(cfg, args) as session:
        page = session.page
        if not session.login():
            return _probe.FAIL
        session.walk_menu()
        _probe._pause(page, 600)

        if args.kind == "select":
            read_back, problem = _switch_select(page, args.dial, args.label)
        elif args.kind == "radio":
            read_back, problem = _switch_radio(page, args.dial, args.label,
                                               args.force)
        else:
            read_back, problem = _switch_dropdown(page, args.dial, args.label,
                                                  args.value_sel, args.force)

        verdict = contract.verify(read_back, args.label)
        if verdict and args.apply:
            btn = _probe._find(page, args.apply_sel, wait_ms=_probe.FIELD_MS)
            if btn:
                btn.click(force=args.force)
                applied = True
                _probe._pause(page, 1500)
            else:
                problem = (problem + " | " if problem else "") + \
                    "保存键没找到:%s" % args.apply_sel
        shot = ""
        try:
            os.makedirs(os.path.join(_probe.ROOT, "artifacts"), exist_ok=True)
            shot = os.path.join(_probe.ROOT, "artifacts",
                                "try_switch_%s.png"
                                % re.sub(r"[^A-Za-z0-9]+", "_", args.label))
            page.screenshot(path=shot, full_page=True)
        except Exception:
            shot = ""

    out = {"dial": args.dial, "kind": args.kind, "expected": args.label,
           "read_back": read_back, "match": bool(verdict), "applied": applied,
           "screenshot": shot, "message": problem}
    if args.json:
        print(json.dumps(out, ensure_ascii=False, indent=2))
    else:
        print("%-12s %s" % ("目标措辞", args.label))
        print("%-12s %r" % ("回读值", read_back))
        print("%-12s %s" % ("一致", "是" if verdict else "否"))
        print("%-12s %s" % ("已下发", "是" if applied else "否"))

    if problem:
        _probe.say("[!] " + problem)
    if shot:
        _probe.say("截图:%s" % shot)
    if not verdict:
        _probe.say("**回读和目标不一致。** 常见原因,按可能性排:\n"
                   "  1. 措辞抄错了 —— 回 list_modes.py 看界面原话,连大小写和"
                   "括号都要一样;\n"
                   "  2. 选到的不是拨号控件 —— 回 probe_dump.py 换一个;\n"
                   "  3. 控件被皮盖住,点了没生效 —— 加 --force;\n"
                   "  4. 自定义下拉的值不在触发器上 —— 用 --value-sel 指到"
                   "真正显示值的那个子元素。")
        return _probe.FAIL
    _probe.say("回读和目标一致。**每一档都这么过一遍**,全对了再 make_facts.py。")
    if not args.apply:
        _probe.say("(这次只选中没下发。要真下发得加 --apply --apply-sel,"
                   "而且按规矩要先给人看回读值和截图。)")
    return _probe.PASS


if __name__ == "__main__":
    sys.exit(main())
