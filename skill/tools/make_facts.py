"""第 5 步:把**已经验过的东西**打印成 FACTS 骨架;--write 直接生成型号脚本。

    python skill/tools/make_facts.py --brand Cudy --model AX1500 \\
        --menu "sel:#Network,sel:#WAN" --dial "#wanType_id" --kind select \\
        --mode dynamic="DHCP Client" --mode pppoe="PPPoE" \\
        --field pppoe_user="input[name='pppUserName']" \\
        --field pppoe_pass="input[name='pppPassword']" \\
        --apply-sel "input[name='save_apply']" \\
        --login-pw "#pwd" --login-btn "input[value='Login']"

**这个工具不探测、不猜。** 它只是把前四步的产出排版成骨架 —— 每个措辞都该是
list_modes.py 抄下来的原话,每个选择器都该是 probe_count.py 数过恰好 1 的,
每一档都该是 try_switch.py 试切过、回读对上的。少了哪一步,骨架里就会留下
TODO,而留着 TODO 就不算过。

--write 会**整份拷贝一个已交付的同 UI 原型脚本**再换掉 FACTS/MODES/NEEDS。
这样新脚本的查找方式和探针工具是同一份代码(check_model.py 会验这一点),
不是重新写一遍。

退出码:0 = 骨架里没有 TODO / 1 = 还有 TODO / 2 = 用法错误
"""
from __future__ import annotations

import argparse
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import _probe                                              # noqa: E402

# 四种 UI 原型各有一台已经交付、真机验过的脚本。新机型照最像的那台抄。
LIKE = {
    "select": ("Cudy_AX1500", "原生 <select>,老式 frameset / 普通单文档"),
    "luci": ("Cudy_AX3000", "LuCI(CBI):id 含点号,保存键要用表单收窄"),
    "dropdown": ("Tenda_AX3000", "自定义下拉(Vue / role=combobox)"),
    "radio": ("BUFFALO_WSR6000AX8", "radio 组,而且设置页要以 iframe 打开"),
}

NEED_BY_CONCEPT = {
    "pppoe_user": "router.pppoe_user", "pppoe_pass": "router.pppoe_pass",
    "vpn_server": None,        # 按 l2tp / pptp 分开,见下面 _needs()
    "vpn_user": None, "vpn_pass": None,
}


def _pairs(items, what):
    out = []
    for item in items or []:
        if "=" not in item:
            _probe.say("--%s 要写成 名字=值 的形式,收到的是 %r" % (what, item))
            raise SystemExit(_probe.USAGE)
        key, value = item.split("=", 1)
        out.append((key.strip(), value.strip().strip('"').strip("'")))
    return out


def _needs(modes, fields):
    """每档要 config.yaml 里的哪几项。**按档取,不合并** —— PPPoE 账密绝不
    能漏进 dynamic,L2TP 和 PPTP 的账号在台架上也是两套。"""
    have = {k for k, _ in fields}
    out = {}
    for mode in modes:
        need = {}
        if mode.startswith("pppoe") and "pppoe_user" in have:
            need = {"pppoe_user": "router.pppoe_user",
                    "pppoe_pass": "router.pppoe_pass"}
        elif mode.startswith(("l2tp", "pptp")) and "vpn_server" in have:
            family = "l2tp" if mode.startswith("l2tp") else "pptp"
            need = {"vpn_server": "router.%s.server" % family,
                    "vpn_user": "router.%s.user" % family,
                    "vpn_pass": "router.%s.pass" % family}
        out[mode] = need
    return out


def build_facts(args, modes, fields):
    todo = []

    def val(value, hint):
        if value:
            return repr(value)
        todo.append(hint)
        return '"TODO:%s"' % hint

    lines = ["FACTS = {"]
    lines.append('    "brand": %s,' % val(args.brand, "brand"))
    lines.append('    "model": %s,' % val(args.model, "model"))
    lines.append('    "url": %s,' % val(args.url or _probe.url_of(_probe.perf.load()),
                                        "url"))
    lines.append("")
    lines.append("    # 登录页:密码框 + 登录键(不给 button 就填完按回车)")
    login = ['"password": %s' % val(args.login_pw or "input[type=password]",
                                    "login.password")]
    if args.login_btn:
        login.append('"button": %r' % args.login_btn)
    lines.append('    "login": {%s},' % ", ".join(login))
    lines.append("")
    menu = [x.strip() for x in (args.menu or "").split(",") if x.strip()]
    lines.append("    # 走到 WAN 设置页要点哪几下(sel: 前缀 = 用选择器,否则按文字)")
    lines.append('    "wan_path": %r,' % (menu,))
    lines.append("")
    lines.append("    # 拨号控件(probe_count.py 数过:恰好命中 1)")
    dial = ['"kind": %r' % args.kind, '"selector": %s' % val(args.dial, "dial.selector")]
    if args.value_sel:
        dial.append('"value": %r' % args.value_sel)
    lines.append('    "dial": {%s},' % ", ".join(dial))
    lines.append("")
    lines.append("    # 下拉选项逐字实录(list_modes.py 抄的界面原话,"
                 "回读是精确相等比对)")
    if not modes:
        todo.append("modes")
        lines.append('    "modes": {"TODO:modes": ""},')
    else:
        lines.append('    "modes": {')
        for name, label in modes:
            lines.append('        %r: %r,' % (name, label))
        lines.append("    },")
    if fields:
        lines.append("")
        lines.append("    # 选完模式后才挂载的账密框")
        lines.append('    "fields": {')
        for name, sel in fields:
            lines.append('        %r: %r,' % (name, sel))
        lines.append("    },")
    lines.append("")
    lines.append("    # 保存键(probe_count.py 数过:恰好命中 1)")
    lines.append('    "apply": %s,' % val(args.apply_sel, "apply"))
    if args.toggle:
        lines.append("")
        lines.append("    # 整块表单被使能开关门控时才要(拨号控件已可见就绝不碰它)")
        lines.append('    "enable_toggle": %r,' % args.toggle)
    lines.append("}")
    return "\n".join(lines), todo


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--brand", default="")
    ap.add_argument("--model", default="")
    ap.add_argument("--url", default="")
    ap.add_argument("--login-pw", default="")
    ap.add_argument("--login-btn", default="")
    ap.add_argument("--menu", default="")
    ap.add_argument("--dial", default="")
    ap.add_argument("--kind", choices=["select", "dropdown", "radio"],
                    default="select")
    ap.add_argument("--value-sel", default="")
    ap.add_argument("--toggle", default="")
    ap.add_argument("--apply-sel", default="")
    ap.add_argument("--mode", action="append", default=[], metavar="名字=界面措辞",
                    help="一档一个,可给多次。如 --mode pppoe=\"PPPoE\"")
    ap.add_argument("--field", action="append", default=[], metavar="概念=选择器",
                    help="账密框,可给多次。如 --field pppoe_user=\"input[name='u']\"")
    ap.add_argument("--like", default=None, choices=sorted(LIKE),
                    help="照哪种 UI 原型生成(--write 时用;默认按 --kind 选)")
    ap.add_argument("--write", default=None, metavar="models/X.py",
                    help="**直接生成型号脚本**(拷贝同原型的已交付脚本再换 FACTS)")
    args = ap.parse_args(argv)

    modes = _pairs(args.mode, "mode")
    fields = _pairs(args.field, "field")
    facts_text, todo = build_facts(args, modes, fields)
    needs = _needs([m for m, _ in modes], fields)

    print(facts_text)
    print("")
    print("MODES = %r" % [m for m, _ in modes])
    print("")
    print("NEEDS = {")
    for mode in [m for m, _ in modes]:
        print("    %r: %r," % (mode, needs[mode]))
    print("}")

    if todo:
        _probe.say("\n**还有 %d 处 TODO:%s**" % (len(todo), ", ".join(todo)))
        _probe.say("每一项都该是前四步的产出,不是猜出来的:")
        _probe.say("  measure/modes -> list_modes.py 抄界面原话")
        _probe.say("  选择器        -> probe_count.py 数过恰好 1")
        _probe.say("  每一档        -> try_switch.py 试切过、回读对上")
        return _probe.FAIL

    if args.write:
        like = args.like or ("radio" if args.kind == "radio"
                             else "dropdown" if args.kind == "dropdown"
                             else "select")
        src_name, why = LIKE[like]
        src = os.path.join(_probe.ROOT, "models", src_name + ".py")
        if not os.path.exists(src):
            _probe.say("照抄的样板不在:%s" % src)
            return _probe.FAIL
        text = open(src, encoding="utf-8").read()
        stem = os.path.splitext(os.path.basename(args.write))[0]
        title = ("%s %s" % (args.brand, args.model)).strip()

        # 把抄来的那台机的说明换成这台机的。**"这个文件怎么读"那一段是通用的,
        # 留着**;上面讲事实来源和 UI 形态的部分只有原机成立,必须换掉,
        # 否则新脚本会带着一份说的是别人的文档。
        old_doc = re.match(r'"""(.*?)"""', text, re.S)
        keep = ""
        if old_doc:
            at = old_doc.group(1).find("## 这个文件怎么读")
            if at >= 0:
                keep = "\n" + old_doc.group(1)[at:].rstrip()
        new_doc = '"""%s —— WAN 拨号方式切换脚本。\n\n' % title
        new_doc += ("用法(默认只切换不保存;确认回读无误后加 --apply 才真正下发):\n"
                    "    python models/%s.py %s\n"
                    "    python models/%s.py %s --apply\n"
                    "账号密码全部取自 config.yaml,不用敲在命令行上。\n\n"
                    % (stem, modes[0][0] if modes else "dynamic",
                       stem, modes[0][0] if modes else "dynamic"))
        new_doc += ("事实来源:skill/tools 的探针(probe_dump / list_modes /\n"
                    "probe_count / try_switch)在真机上跑出来的 —— 每个选择器都数过\n"
                    "恰好命中 1,每一档都试切过、回读对上。**照 %s 生成,\n"
                    "UI 形态是「%s」。**\n\n"
                    "TODO:把这台机的固件版本、UI 形态、以及踩过的坑写在这儿。\n"
                    % (src_name, why))
        new_doc += keep + '\n"""'
        text = re.sub(r'^""".*?"""', lambda _m: new_doc, text, count=1, flags=re.S)

        text = re.sub(r"^FACTS = \{.*?^\}", facts_text, text,
                      count=1, flags=re.S | re.M)
        # 这两处不换的话:命令行帮助里写着别人的型号,而且整轮会**按别人的名字**
        # 去读配置、命名报告文件。
        text = re.sub(r'description="[^"]*—— WAN 拨号方式切换',
                      'description="%s —— WAN 拨号方式切换' % title, text, count=1)
        text = re.sub(r'perf\.load\(model="[^"]*"\)',
                      'perf.load(model="%s")' % stem, text, count=1)
        text = re.sub(r"^MODES = \[.*?\]", "MODES = %r" % [m for m, _ in modes],
                      text, count=1, flags=re.S | re.M)
        needs_text = "NEEDS = {\n" + "".join(
            "    %r: %r,\n" % (m, needs[m]) for m, _ in modes) + "}"
        text = re.sub(r"^NEEDS = \{.*?^\}", needs_text, text,
                      count=1, flags=re.S | re.M)
        slug = re.sub(r"[^a-z0-9]+", "_",
                      ("%s_%s" % (args.brand, args.model)).lower()).strip("_")
        text = re.sub(r'"model_[a-z0-9_]+_%s\.png"', '"model_%s_%%s.png"' % slug,
                      text)
        text = re.sub(r'model_[a-z0-9_]+_%s\.png', "model_%s_%%s.png" % slug, text)
        dest = args.write if os.path.isabs(args.write) else os.path.join(
            _probe.ROOT, args.write)
        if os.path.exists(dest):
            _probe.say("%s 已经存在,不覆盖 —— 换个名字,或先把旧的挪走。" % dest)
            return _probe.FAIL
        with open(dest, "w", encoding="utf-8") as fh:
            fh.write(text)
        _probe.say("\n照 %s(%s)生成了 %s" % (src_name, why, dest))
        _probe.say("**文件头那段说明还是照抄来的,记得改成这台机的事实。**")
        _probe.say("然后:python skill/tools/check_model.py %s"
                   % os.path.splitext(os.path.basename(dest))[0])
    else:
        _probe.say("\n骨架里没有 TODO。--write models/<品牌>_<型号>.py 可以直接"
                   "生成脚本(照已交付的同原型脚本拷,查找方式和探针一致)。")
    return _probe.PASS


if __name__ == "__main__":
    sys.exit(main())
