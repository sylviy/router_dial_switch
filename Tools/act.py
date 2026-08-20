"""**做一个动作,再证明它成了。** 选中 / 勾上 / 填进去 / 点下去,然后回读。

    python Tools/act.py --menu "sel:#Network,sel:#WAN" \\
        --sel "#wanType_id" --label "PPPoE"
    python Tools/act.py --menu "…" --sel "#enable" --kind checkbox --label on \\
        --apply-sel "input[name='save_apply']" --reload-verify

这是写脚本之前的最后一关:选择器对不对、措辞对不对,不用先写完一整个文件
才知道。探 → 列 → 数 → 做,全都发生在写文件之前。

## 判定只有一个出口

`Vendor/common/contract.py` 的 `verify()`,**和型号脚本、和整轮报告是同一把尺子**:
规整首尾空白与大小写后精确相等,空回读永远判假,绝不放宽成包含
("PPPoEv6" 里有 "PPPoE",放宽一次就等于允许一份测错对象的报告)。

## 两个开关值得单说

  * `--apply-sel` 给了就**真点保存**。适配台架是断网的、WAN 口不接出口,
    点错了也关不住人,所以这里没有"确认"环节 —— 不想保存就别给这个参数。
  * `--reload-verify` **刷新页面、重新登录走菜单、再读一遍**。不刷新的话,
    你读到的是自己刚填进去的值,等于自己给自己打分;真机上出过"回读通过、
    实际提交的是旧值"。要证明保存住了,就得带上它。

退出码:0 = 回读 == 目标 / 1 = 不等 / 2 = 用法错误
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

# 勾选类控件的回读一律归一化成这两个词,免得 "1"/"true"/"on" 各写各的。
ON, OFF = "on", "off"
_TRUE = ("1", "on", "true", "yes", "checked", "enabled")

KINDS = ("select", "dropdown", "radio", "checkbox", "toggle", "text", "button")
# 这几种的 --label 只能是 on / off
BOOLEAN_KINDS = ("checkbox", "toggle")


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


def _norm_bool(raw):
    return ON if str(raw or "").strip().lower() in _TRUE else OFF


# ---------------------------------------------------------------------------
# 回读:每种形态"现在是什么值"。--reload-verify 刷新之后也走这里。
# ---------------------------------------------------------------------------
def read_value(page, kind, sel, value_sel, label):
    """只读不动。读不到返回空串 —— 空回读一律判假,不会被当成"没变化所以对"。"""
    if kind == "select":
        el = _probe._find(page, sel, wait_ms=_probe.DIAL_MS, visible=False)
        if el is None:
            return ""
        try:
            return (el.evaluate("e => e.options[e.selectedIndex]"
                                " ? e.options[e.selectedIndex].text : ''")
                    or "").strip()
        except Exception:
            return ""
    if kind == "dropdown":
        el = _probe._find(page, value_sel or sel, wait_ms=_probe.DIAL_MS)
        if el is None:
            return ""
        try:
            got = (el.inner_text() or "").strip()
        except Exception:
            return ""
        return _value_match(got, label) or got
    if kind == "radio":
        el = _probe._find(page, sel, wait_ms=_probe.DIAL_MS, visible=False)
        if el is None:
            return ""
        try:
            return label if el.is_checked() else ""
        except Exception:
            return ""
    if kind == "checkbox":
        el = _probe._find(page, sel, wait_ms=_probe.DIAL_MS, visible=False)
        if el is None:
            return ""
        try:
            return ON if el.is_checked() else OFF
        except Exception:
            return ""
    if kind == "toggle":
        # 图标开关点的是 <i>,真实值在**旁边那个 hidden input** 里 —— 读图标
        # 的 class 也能猜出来,但那是猜皮肤,不是读值。所以要 --value-sel。
        el = _probe._find(page, value_sel or sel, wait_ms=_probe.DIAL_MS,
                          visible=False)
        if el is None:
            return ""
        try:
            return _norm_bool(el.input_value())
        except Exception:
            try:
                return _norm_bool(el.get_attribute("value"))
            except Exception:
                return ""
    if kind == "text":
        el = _probe._find(page, sel, wait_ms=_probe.FIELD_MS, visible=False)
        if el is None:
            return ""
        try:
            return (el.input_value() or "").strip()
        except Exception:
            return ""
    return ""                                   # button:没有值可读,见下面


# ---------------------------------------------------------------------------
# 动作:每种形态"怎么点"。返回 (回读值, 问题说明)
# ---------------------------------------------------------------------------
def _do_select(page, sel, label):
    el = _probe._find(page, sel, wait_ms=_probe.DIAL_MS, visible=False)
    if el is None:
        return "", "没找到控件:%s" % sel
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
    got = read_value(page, "select", sel, None, label)
    return got, ("" if got else "选完了但读不回来 —— 它可能不是原生 <select>")


def _do_dropdown(page, sel, label, value_sel, force):
    trigger = _probe._find(page, sel, wait_ms=_probe.DIAL_MS)
    if trigger is None:
        return "", "没找到控件:%s" % sel
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
    waited = 0
    while _value_match(read_value(page, "dropdown", sel, value_sel, label),
                       label) is None and waited < 2000:
        _probe._pause(page, _probe.STEP_MS)
        waited += _probe.STEP_MS
    return read_value(page, "dropdown", sel, value_sel, label), ""


def _do_radio(page, sel, label, force):
    el = _probe._find(page, sel, wait_ms=_probe.DIAL_MS)
    if el is None:
        return "", "没找到 radio:%s" % sel
    try:
        el.click(force=force)
    except Exception as exc:
        return "", ("点不动这个 radio:%s%s"
                    % (str(exc).splitlines()[0],
                       "" if force else "(被别的元素盖住时加 --force)"))
    _probe._pause(page)
    got = read_value(page, "radio", sel, None, label)
    # radio 的"措辞"是个选择器,报出来没有意义 —— 回读记 --label 那个名字。
    return got, ("" if got else "点了,但它不是可回读的 radio —— 选择器指错了")


def _do_checkbox(page, sel, label, force):
    el = _probe._find(page, sel, wait_ms=_probe.DIAL_MS, visible=False)
    if el is None:
        return "", "没找到复选框:%s" % sel
    try:
        if label == ON:
            el.check(force=force)
        else:
            el.uncheck(force=force)
    except Exception as exc:
        return "", ("勾不动这个复选框:%s%s"
                    % (str(exc).splitlines()[0],
                       "" if force else "(被别的元素盖住时加 --force)"))
    _probe._pause(page)
    return read_value(page, "checkbox", sel, None, label), ""


def _do_toggle(page, sel, label, value_sel, force):
    """图标开关:点 <i>,值在旁边的 hidden input 里。

    它没有"设成 on"这种 API,只有"翻一下"。所以先读现在是什么,已经是目标
    就**一下都不点** —— 点一下反而会把它翻走。
    """
    if not value_sel:
        return "", "kind=toggle 必须给 --value-sel(真实值所在的 hidden input)"
    now = read_value(page, "toggle", sel, value_sel, label)
    if now == label:
        return now, ""
    el = _probe._find(page, sel, wait_ms=_probe.DIAL_MS)
    if el is None:
        return "", "没找到开关图标:%s" % sel
    try:
        el.click(force=force)
    except Exception as exc:
        return "", ("点不动这个开关:%s%s"
                    % (str(exc).splitlines()[0],
                       "" if force else "(被别的元素盖住时加 --force)"))
    _probe._pause(page, 400)
    return read_value(page, "toggle", sel, value_sel, label), ""


def _do_text(page, sel, label, force):
    el = _probe._find(page, sel, wait_ms=_probe.FIELD_MS, visible=False)
    if el is None:
        return "", "没找到输入框:%s" % sel
    try:
        el.fill(label, force=force)
    except Exception as exc:
        return "", "填不进去:%s" % str(exc).splitlines()[0]
    _probe._pause(page)
    return read_value(page, "text", sel, None, label), ""


def _do_button(page, sel, force):
    """按钮没有值可读。它的判据是 `--expect-after`「做完的样子」出现,
    所以这里只负责点,成不成由外面那一步说了算。"""
    el = _probe._find(page, sel, wait_ms=_probe.FIELD_MS)
    if el is None:
        return "", "没找到按钮:%s" % sel
    try:
        el.click(force=force)
    except Exception as exc:
        return "", ("点不动这个按钮:%s%s"
                    % (str(exc).splitlines()[0],
                       "" if force else "(被别的元素盖住时加 --force)"))
    _probe._pause(page, 600)
    return "", ""


def act(page, args):
    """做这一步。返回 (回读值, 问题说明)。"""
    if args.kind == "select":
        return _do_select(page, args.sel, args.label)
    if args.kind == "dropdown":
        return _do_dropdown(page, args.sel, args.label, args.value_sel, args.force)
    if args.kind == "radio":
        return _do_radio(page, args.sel, args.label, args.force)
    if args.kind == "checkbox":
        return _do_checkbox(page, args.sel, args.label, args.force)
    if args.kind == "toggle":
        return _do_toggle(page, args.sel, args.label, args.value_sel, args.force)
    if args.kind == "text":
        return _do_text(page, args.sel, args.label, args.force)
    return _do_button(page, args.sel, args.force)


def wait_expect(page, selector):
    """等「做完的样子」出现。**这是固定 sleep 的替代品** —— 页面是逐步展开的,
    等多久没人说得准,但"那个东西出现了"是看得见的。"""
    return _probe._find(page, selector, wait_ms=_probe.DIAL_MS) is not None


def main(argv=None):
    ap = _probe.base_parser(__doc__.splitlines()[0])
    ap.add_argument("--sel", "--dial", dest="sel", required=True,
                    help="要操作的控件选择器(kind=radio 时是这一档自己的 radio)")
    ap.add_argument("--label", default=None,
                    help="目标:select/dropdown 逐字照抄界面原话;radio 写模式名;"
                         "checkbox/toggle 只能是 on 或 off;text 写要填的内容;"
                         "button 不用给")
    ap.add_argument("--kind", choices=list(KINDS), default="select",
                    help="控件形态(默认 select)")
    ap.add_argument("--value-sel", default=None,
                    help="真实值所在的元素:自定义下拉的显示区,或图标开关旁边的"
                         "隐藏 input(kind=toggle 时必给)")
    ap.add_argument("--expect-after", default=None,
                    help="「做完的样子」:做完之后这个选择器要出现,才算这一步成立")
    ap.add_argument("--force", action="store_true",
                    help="控件被别的元素盖住时强行点(Buffalo 那类)")
    ap.add_argument("--apply-sel", default=None,
                    help="保存键选择器。**给了就真点保存**;不想保存就别给")
    ap.add_argument("--reload-verify", action="store_true",
                    help="保存后刷新页面、重新登录走菜单、再读一遍 —— "
                         "不带它读到的只是自己刚填进去的值")
    ap.add_argument("--json", action="store_true", help="stdout 输出 JSON")
    args = ap.parse_args(argv)

    if args.kind == "button":
        if not args.expect_after:
            _probe.say("kind=button 没有值可回读,必须给 --expect-after 说明"
                       "「做完的样子」是什么,否则这一步无从判定。")
            return _probe.USAGE
        args.label = args.label or "出现"
    elif not args.label:
        _probe.say("--label 是必须的(kind=button 除外)。")
        return _probe.USAGE
    if args.kind in BOOLEAN_KINDS:
        args.label = str(args.label).strip().lower()
        if args.label not in (ON, OFF):
            _probe.say("kind=%s 的 --label 只能是 on 或 off,现在是 %r。"
                       % (args.kind, args.label))
            return _probe.USAGE
    if args.kind == "toggle" and not args.value_sel:
        _probe.say("kind=toggle 必须给 --value-sel:图标开关本身不带值,"
                   "真实值在旁边那个 hidden input 里。读图标的 class 是猜皮肤,"
                   "不是读值。")
        return _probe.USAGE

    cfg = _probe.load_cfg(args)
    applied = reloaded = False
    read_back, problem = "", ""

    with _probe.Page(cfg, args) as session:
        page = session.page
        if not session.login():
            return _probe.FAIL
        session.walk_menu()
        _probe._pause(page, 600)

        read_back, problem = act(page, args)

        if args.expect_after:
            if wait_expect(page, args.expect_after):
                if args.kind == "button":
                    read_back = args.label      # 「做完的样子」出现了 = 这一步成立
            else:
                read_back = ""                  # 空回读一律判假
                problem = (problem + " | " if problem else "") + \
                    ("做完之后没等到 %s —— 这一步没成立,别往下走"
                     % args.expect_after)

        if args.apply_sel and read_back:
            btn = _probe._find(page, args.apply_sel, wait_ms=_probe.FIELD_MS)
            if btn:
                btn.click(force=args.force)
                applied = True
                _probe._pause(page, 1500)
            else:
                problem = (problem + " | " if problem else "") + \
                    "保存键没找到:%s" % args.apply_sel

        if args.reload_verify:
            # 刷新 + 重新登录 + 重走菜单,然后再读一次。读到什么就是什么 ——
            # 这一步的回读**覆盖**上面那次,因为上面那次读的是自己刚填的值。
            try:
                page.goto(_probe.url_of(cfg), wait_until="domcontentloaded")
                session.login()
                session.walk_menu()
                _probe._pause(page, 600)
                read_back = read_value(page, args.kind, args.sel,
                                       args.value_sel, args.label)
                reloaded = True
            except Exception as exc:
                problem = (problem + " | " if problem else "") + \
                    "刷新后回读失败:%s" % str(exc).splitlines()[0]
                read_back = ""

        verdict = contract.verify(read_back, args.label)

        shot = ""
        try:
            probes = os.path.join(_probe.OUT_ROOT, "artifacts", "probes")
            os.makedirs(probes, exist_ok=True)
            # 文件名带上被测机地址:适配下一台机时不会把上一台的截图盖掉
            # (拿这些图给人看时,盖错了就是拿着 A 机的图说 B 机)。
            who = re.sub(r"[^A-Za-z0-9]+", "_",
                         _probe.url_of(cfg).split("//")[-1]).strip("_")
            shot = os.path.join(probes, "act_%s_%s.png"
                                % (who, re.sub(r"[^A-Za-z0-9]+", "_", args.label)))
            page.screenshot(path=shot, full_page=True)
        except Exception:
            shot = ""

    out = {"sel": args.sel, "kind": args.kind, "expected": args.label,
           "read_back": read_back, "match": bool(verdict), "applied": applied,
           "reloaded": reloaded, "screenshot": shot, "message": problem}
    if args.json:
        print(json.dumps(out, ensure_ascii=False, indent=2))
    else:
        print("%-12s %s" % ("目标", args.label))
        print("%-12s %r" % ("回读值", read_back))
        print("%-12s %s" % ("一致", "是" if verdict else "否"))
        print("%-12s %s" % ("已保存", "是" if applied else "否"))
        print("%-12s %s" % ("刷新后读", "是" if reloaded else "否 —— 读的是刚填的值"))

    if problem:
        _probe.say("[!] " + problem)
    if shot:
        _probe.say("截图:%s" % shot)
    if not verdict:
        _probe.say("**回读和目标不一致。** 常见原因,按可能性排:\n"
                   "  1. 措辞抄错了 —— 回 list_modes.py 看界面原话,连大小写和"
                   "括号都要一样;\n"
                   "  2. 选到的不是那个控件 —— 回 probe_dump.py 换一个;\n"
                   "  3. 控件被皮盖住,点了没生效 —— 加 --force;\n"
                   "  4. 值不在触发器上 —— 用 --value-sel 指到真正带值的元素;\n"
                   "  5. 页面还没展开到这一步 —— 用 --expect-after 卡住上一步。\n"
                   "都不是的话,dump 一眼原始 HTML(probing.md 的第 2 招)。")
        return _probe.FAIL
    _probe.say("回读和目标一致。**每一步都这么过一遍**,全对了再落成脚本。")
    if not args.reload_verify:
        _probe.say("(这次没刷新就回读 —— 读到的是自己刚填进去的值。要证明"
                   "保存住了,加 --reload-verify。)")
    return _probe.PASS


if __name__ == "__main__":
    sys.exit(main())
