"""Mercusys BE3600(Wi-Fi 7)—— WAN 拨号方式切换脚本。

用法(默认只切换不保存;确认回读无误后加 --apply 才真正下发):
    python models/Mercusys_BE3600.py pppoe
    python models/Mercusys_BE3600.py l2tp --apply
账号密码全部取自 config.yaml,不用敲在命令行上。

事实来源:2026-07-11 真机验证。标注 [待真机复核] 的行当时由启发式自动搞定、
没记下精确选择器 —— 失败时用 skill/tools 的探针取证后修正。
**FACTS 是重构前原样搬过来的,一个字符没改。**

拨号控件是自定义 `<div role="combobox">`,不是原生 `<select>`(真机确认:
form_input 曾报 "DIV is not a supported form input"),所以下面第 5 步走
"点开触发器 → 在弹层里点选项 → 重新定位再读值"这条路。

**注意:该机型只允许一个 Web 会话**,另一个已登录页签会把工具踢回登录页。
--------------------------------------------------------------------------
## 这个文件怎么读

从上往下就是台架上会发生的事,中间不跳到别的文件:

    FACTS / MODES / NEEDS   纯数据:这台机的选择器、能切哪几档、每档要哪些账密
    _pause / _find / ...    几个小工具。**只有它们要先看懂**
    switch()                主角。第 1~7 步依次是:查配置 → 开浏览器 → 登录 →
                            走菜单 → 选档并回读 → 填账密 → 保存
    _screenshot / main()    截图、命令行

这个文件是**自足**的:除了 common/contract.py(判定)和 common/perf.py
(整轮节拍 + 读 config.yaml),不依赖仓库里任何别的代码。这几个小工具在别的
型号脚本里也有一份几乎一样的 —— **那是故意的**。共用一层"动词库"的代价是:
改第六台机有可能悄悄弄坏前五台,而那种坏法是静默的(切了、看起来成功、
保存的是旧值)。重复换来的是:删掉任意一个型号文件,其余六个照跑。
"""
import argparse
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from common import contract, perf

FACTS = {
    "brand": "Mercusys",
    "model": "BE3600",
    "url": "http://192.168.1.1",   # [待真机复核] 当时未记录 IP;这是出厂默认

    # 登录只要密码。按钮措辞 [待真机复核];找不到时驱动自动退回按回车。
    # 注意:该机型只允许一个 Web 会话,另一个已登录页签会把工具踢回登录页。
    "login": {"password": "input[type=password]",
              "button": 'button:text-is("Log In")'},

    # 英文顶部导航:Network Map | Internet | Wireless | Advanced(真机确认);
    # 拨号控件在 "Internet" 页。
    "wan_path": ["Internet"],

    # 拨号控件:自定义 <div role="combobox">,不是原生 <select>(真机确认;
    # form_input 曾报 "DIV is not a supported form input")。
    "dial": {"kind": "dropdown", "selector": "[role='combobox']"},

    # 真机下拉选项原文。
    "modes": {"dynamic": "Dynamic IP", "static": "Static IP",
              "pppoe": "PPPoE", "l2tp": "L2TP", "pptp": "PPTP"},

    # L2TP/PPTP 字段:Username / Password / "VPN Server IP/Domain Name"
    # (真机确认措辞)。行容器的 class [待真机复核 —— 真机跑通时走的是启发式]。
    "fields": {
        "pppoe_user": 'div.row:has-text("Username") input:visible',
        "pppoe_pass": 'div.row:has-text("Password") input:visible',
        "vpn_user":   'div.row:has-text("Username") input:visible',
        "vpn_pass":   'div.row:has-text("Password") input:visible',
        "vpn_server": 'div.row:has-text("VPN Server") input:visible',
    },

    # 保存键:"Save"(真机确认)。
    "apply": 'button:text-is("Save")',

    # IPv6:在 Advanced → IPv6 独立分区,真机 DOM 还没观察过 —— 按项目规矩
    # 不猜没见过的页面,所以本脚本不含 ipv6。等在真机跑一次
    # skill/tools 的探针取证后,照 Tenda_AX3000.py 的 mode_overrides 补上。
}

# 这台机能切哪几档,按台架轮次的顺序。
MODES = ["dynamic", "static", "pppoe", "l2tp", "pptp"]

# 每档要 config.yaml 里的哪几项 -> 填进哪个概念。**碰路由器之前**核对。
NEEDS = {
    "dynamic": {},
    "static": {},
    "pppoe": {"pppoe_user": "router.pppoe_user",
              "pppoe_pass": "router.pppoe_pass"},
    "l2tp": {"vpn_server": "router.l2tp.server", "vpn_user": "router.l2tp.user",
             "vpn_pass": "router.l2tp.pass"},
    "pptp": {"vpn_server": "router.pptp.server", "vpn_user": "router.pptp.user",
             "vpn_pass": "router.pptp.pass"},
}

# 各步最多等多久(毫秒)
_LOGIN_MS, _NAV_MS, _DIAL_MS, _FIELD_MS = 8000, 6000, 8000, 3000
_STEP_MS, _PAUSE_MS = 200, 300


class _Stop(Exception):
    """半路走不下去了(没找到控件、登录没进去……)。

    用异常而不是 return:失败也要**先截图再关浏览器**,那张截图正是排查
    要用的东西。switch() 在一个地方接住它,截完图再把原因写进结果。
    """


# ---------------------------------------------------------------------------
# 小工具。别的型号脚本里会有几乎一样的几份 —— 那是故意的,见文件头。
# ---------------------------------------------------------------------------
def _pause(page, ms=_PAUSE_MS):
    """等一会儿,让页面消化上一步操作。"""
    try:
        page.wait_for_timeout(ms)
    except Exception:
        pass


def _find(page, sel, wait_ms=0, visible=True):
    """在**所有 frame** 里找一个元素;wait_ms 内没出现就返回 None。

    visible=False:连隐藏的也认 —— 被美化插件藏起来的原生 <select> 是
    display:none 的,但它就是真控件。
    """
    waited = 0
    while True:
        for fr in list(page.frames):
            try:
                loc = fr.locator(sel)
                count = min(loc.count(), 25)
            except Exception:
                continue
            for i in range(count):
                el = loc.nth(i)
                try:
                    if el.is_visible():
                        return el
                except Exception:
                    continue
            if not visible and count:
                return loc.first
        if waited >= wait_ms:
            return None
        _pause(page, _STEP_MS)
        waited += _STEP_MS


def _find_text(page, text, wait_ms=0):
    """按**精确文字**找一个可见元素(菜单项用)。子串匹配会点错菜单。"""
    waited = 0
    while True:
        for fr in list(page.frames):
            try:
                loc = fr.get_by_text(text, exact=True)
                for i in range(min(loc.count(), 25)):
                    el = loc.nth(i)
                    if el.is_visible():
                        return el
            except Exception:
                continue
        if waited >= wait_ms:
            return None
        _pause(page, _STEP_MS)
        waited += _STEP_MS


# 弹层选项的容器形态:role=option,或 class 里带 opt/option 的元素。
OPTION_CONTAINERS = "[role='option'], [class*='opt']"


def _value_match(text, label):
    """触发器上现在显示的是不是 label?

    整体精确相等,或**某一行**精确相等(trigger 里常混着下拉小图标等杂质
    文本)。逐行仍是精确匹配 —— 子串匹配会把 "PPPoEv6" 认成 "PPPoE",
    这里绝不用 contains。命中返回那段文字,没命中返回 None。
    """
    norm = lambda s: " ".join((s or "").split()).lower()
    if norm(text) == norm(label):
        return (text or "").strip()
    for line in (text or "").splitlines():
        if norm(line) == norm(label):
            return line.strip()
    return None


def _find_option(page, label, containers, wait_ms):
    """在弹出的选项层里找措辞精确等于 label 的那一项。

    **先只认 option 形态的容器**(弹层是异步挂载的,轮询等它);实在没有,
    最后才退回"页面上任何精确同文字"—— 这一步放在轮询之外,防止弹层还没
    渲染就抓走页面别处的同名文字(Tenda IPv6 页的 LAN 区就有一个同叫
    "DHCPv6" 的 radio 诱饵)。
    """
    rx = re.compile(r"^\s*%s\s*$" % re.escape(label), re.IGNORECASE)
    waited = 0
    while True:
        for fr in list(page.frames):
            try:
                loc = fr.locator(containers).filter(has_text=rx)
                for i in range(min(loc.count(), 25)):
                    el = loc.nth(i)
                    if el.is_visible():
                        return el
            except Exception:
                continue
        if waited >= wait_ms:
            return _find_text(page, label)
        _pause(page, _STEP_MS)
        waited += _STEP_MS


def _facts_for(mode):
    """套 mode_overrides:被覆盖的键整个替换。"""
    merged = dict(FACTS)
    for key, value in (FACTS.get("mode_overrides") or {}).get(mode, {}).items():
        merged[key] = value
    return merged


# ---------------------------------------------------------------------------
# 切换:登录 → 走菜单 → 选档(当场回读)→ 填账密 → 保存
# ---------------------------------------------------------------------------
def switch(mode, cfg, hook=None):
    """把这台机的 WAN 拨号方式切成 mode,返回 contract.result(...)。

    从上往下读就是这台机在浏览器里被点了些什么,中间没有跳转到别的文件。

    要不要真的点保存看 cfg["run"]["apply"](命令行的 --apply / 整轮时恒为
    真)。默认**只切换不下发** —— 切错档会当场断网,台架上没人能远程救回来。

    hook: 可选 callable(page),关浏览器前调用,返回值存进 result["verify"]。
    冒烟测试用它读页面上的 toast(证明保存键真的按下去了、而且按的是对的
    那个);将来接"WAN 真拨通"验证也在这。
    """
    # --- 0. 这一档要用的事实和账密 -----------------------------------------
    facts = _facts_for(mode)
    label = (facts.get("modes") or {}).get(mode, "")
    ident = {"brand": FACTS["brand"], "model": FACTS["model"], "mode": mode}
    warnings, filled = [], []

    def done(read_back, message="", applied=False, screenshot="", verify=None):
        """这个函数唯一的出口。success 只能由 contract.verify() 算出来 ——
        回读值等于目标措辞才算数,空回读永远判假。"""
        res = contract.result(contract.verify(read_back, label), read_back,
                              label, message=message, screenshot=screenshot,
                              applied=applied, filled=filled,
                              warnings=warnings, **ident)
        if hook is not None:
            res["verify"] = verify
        return res

    # --- 1. 碰路由器之前:档位对不对、配置齐不齐 -----------------------------
    if mode not in MODES:
        return done("", "这台机不支持 %r(支持:%s)" % (mode, ", ".join(MODES)))

    params, missing = {}, []
    for concept, where in NEEDS.get(mode, {}).items():
        value = cfg.at(where)              # 只取这一档要的:PPPoE 账密绝不
        if value is None or not str(value).strip():   # 会漏进 dynamic 的运行
            missing.append("%s(%s)" % (where, cfg.where(where)))
        else:
            params[concept] = str(value)
    if missing:
        return done("", "切 %s 缺配置:%s。用记事本补上,这一档没有碰路由器。"
                        % (mode, "、".join(missing)))

    admin_pass = str(cfg.at("router.pass") or "")
    if not admin_pass:
        return done("", "没有管理密码:%s 的 router.pass 没填。"
                        % cfg.where("router.pass"))

    url = str(cfg.at("router.ip") or FACTS["url"]).strip()
    if not url.startswith("http"):
        url = "http://" + url
    apply_it = bool(cfg.at("run.apply"))

    # --- 2. 开浏览器 --------------------------------------------------------
    # 离线优先级:config.yaml 写死的可执行文件 -> 系统装的 Chrome ->
    # Playwright 自带的 chromium(要预置浏览器包)。台架离线,不会去下载。
    from playwright.sync_api import sync_playwright

    exe = cfg.at("bench.browser_path") or os.environ.get("ROUTER_BROWSER_PATH")
    browsers_dir = (cfg.at("bench.browsers_dir")
                    or os.environ.get("ROUTER_BROWSERS_DIR"))
    if browsers_dir:
        os.environ["PLAYWRIGHT_BROWSERS_PATH"] = str(browsers_dir)
    headless = bool(cfg.at("run.headless"))

    pw = sync_playwright().start()
    if exe:
        browser = pw.chromium.launch(executable_path=str(exe), headless=headless)
    else:
        try:
            browser = pw.chromium.launch(channel="chrome", headless=headless)
        except Exception as exc:
            print("[browser] 系统 Chrome 起不来(%s),改用自带 chromium" % exc)
            browser = pw.chromium.launch(headless=headless)
    context = browser.new_context(ignore_https_errors=True)
    context.set_default_timeout(15000)
    context.set_default_navigation_timeout(30000)
    page = context.new_page()

    read_back, message, applied = "", "", False
    try:
        page.goto(url, wait_until="domcontentloaded")

        # --- 3. 登录 --------------------------------------------------------
        # 密码框没出现 = 已经在会话里,直接往下走。填了却还停在登录页 =
        # 如实报登录失败,不能带着未登录状态往下走再误报"找不到拨号控件"。
        pw_sel = (facts.get("login") or {}).get("password") or "input[type=password]"
        pwd = _find(page, pw_sel, wait_ms=_LOGIN_MS)
        if pwd:
            pwd.fill(admin_pass)
            btn_sel = (facts.get("login") or {}).get("button")
            btn = _find(page, btn_sel, wait_ms=2000) if btn_sel else None
            if btn:
                btn.click()
            else:
                pwd.press("Enter")     # 没有登录键就回车提交
            waited = 0
            while _find(page, pw_sel) is not None:      # 等密码框消失
                if waited >= _LOGIN_MS:
                    raise _Stop("登录失败 —— 仍停在登录页。检查 %s 的管理密码。"
                                "%s" % (cfg.where("router.pass"), "另外这台机只允许一个 Web 会话,先关掉其他已登录的页签。"))
                _pause(page, _STEP_MS)
                waited += _STEP_MS

        # --- 4. 走菜单 -------------------------------------------------------
        for item in facts.get("wan_path") or []:
            if item.startswith("sel:"):
                el = _find(page, item[4:], wait_ms=_NAV_MS)
            else:
                el = _find_text(page, item, wait_ms=_NAV_MS)   # 菜单按文字精确匹配
            if el:
                el.click()
                _pause(page)
            else:
                warnings.append("菜单没找到:%r" % item)

        # --- 5. 选档,当场真实回读 -------------------------------------------
        # 自定义下拉(不是原生 <select>):点开触发器 → 在弹层里点选项 →
        # 重新定位再读值(框架可能在变更时整个重渲染 trigger,旧句柄不可靠)。
        dial_sel = facts["dial"]["selector"]
        value_sel = facts["dial"].get("value") or dial_sel
        trigger = _find(page, dial_sel, wait_ms=_DIAL_MS)
        if not trigger:
            raise _Stop("没找到拨号控件:%s" % dial_sel)
        try:
            current = trigger.inner_text()
        except Exception:
            current = ""
        hit = _value_match(current, label)
        if hit is not None:
            # 选择器钉住的就是真控件,它显示的当前值即真实回读,可信。
            read_back = hit
        else:
            trigger.click()
            _pause(page)
            option = _find_option(page, label,
                                  facts.get("options") or OPTION_CONTAINERS,
                                  3000)
            if not option:
                seen = []
                for fr in list(page.frames):
                    try:
                        loc = fr.locator(facts.get("options")
                                         or OPTION_CONTAINERS)
                        for i in range(min(loc.count(), 12)):
                            t = (loc.nth(i).inner_text() or "").strip()
                            if t and len(t) < 30 and t not in seen:
                                seen.append(t)
                    except Exception:
                        continue
                raise _Stop("下拉打开了,但没找到选项 %r%s"
                            % (label,
                               "(看到:%s)" % " / ".join(seen) if seen else ""))
            option.click()
            _pause(page, 400)

            def read_now():
                el = _find(page, value_sel)
                try:
                    return (el.inner_text() or "").strip() if el else ""
                except Exception:
                    return ""

            waited = 0
            while _value_match(read_now(), label) is None and waited < 2000:
                _pause(page, _STEP_MS)
                waited += _STEP_MS
            got = read_now()
            read_back = _value_match(got, label) or got

        # --- 6. 填账密 --------------------------------------------------------
        # **回读没通过就不填**:页面状态还不明,填进去等于往未知表单里打字。
        if contract.verify(read_back, label):
            for concept in NEEDS.get(mode, {}):
                field_sel = (facts.get("fields") or {}).get(concept)
                if not field_sel:
                    warnings.append("FACTS.fields 缺 %r 的选择器" % concept)
                    continue
                # 账密框在选完模式后才挂载(有的机型还是 AJAX 挂的),等它出现。
                el = _find(page, field_sel, wait_ms=_FIELD_MS)
                if el:
                    el.fill(params[concept])
                    filled.append(concept)
                else:
                    warnings.append("输入框没出现:%s -> %s" % (concept, field_sel))

            # --- 7. 保存(只有回读通过、且这一轮要求下发时才点)---------------
            if apply_it:
                btn = _find(page, facts["apply"], wait_ms=_FIELD_MS)
                if btn:
                    btn.click()
                    applied = True
                    _pause(page, facts.get("apply_settle_ms", 500))
                else:
                    warnings.append("保存键没找到:%s%s"
                                    % (facts["apply"], _visible_buttons(page)))
    except _Stop as stop:
        message = str(stop)
    finally:
        # 成败都走到这:失败时的截图正是排查要用的证据。
        verify_out = None
        if hook is not None:
            try:
                verify_out = hook(page)
            except Exception as exc:
                warnings.append("hook: %s" % exc)
        shot = _screenshot(page, cfg, mode)
        for closer in (context, browser):
            try:
                closer.close()
            except Exception:
                pass
        try:
            pw.stop()
        except Exception:
            pass

    return done(read_back, message, applied=applied, screenshot=shot,
                verify=verify_out)


def _visible_buttons(page):
    """页面上真正可见的按钮清单,拼进"保存键没找到"的警告里。

    证据优先:真机上出过一次"按钮文字在里层 span,选择器漏了"—— 有这张
    清单就不用为了看一眼页面再上一次台架。
    input[type=submit] 的文字在 value 里,所以两种都读。
    """
    seen = []
    for fr in list(page.frames):
        try:
            loc = fr.locator("button, input[type=submit], input[type=button]")
            for i in range(min(loc.count(), 12)):
                b = loc.nth(i)
                if not b.is_visible():
                    continue
                txt = (b.inner_text() or "").strip() or (b.input_value() or "").strip()
                if txt and txt not in seen:
                    seen.append(txt)
        except Exception:
            continue
    return "(页面可见按钮:%s)" % " / ".join(seen) if seen else ""


def _screenshot(page, cfg, mode):
    """整页截图存进 artifacts/;失败返回空串,绝不因此中断一轮。"""
    try:
        out_dir = cfg.at("report.dir") or "artifacts"
        if not os.path.isabs(out_dir):
            out_dir = os.path.join(ROOT, out_dir)
        os.makedirs(out_dir, exist_ok=True)
        path = os.path.join(out_dir, "model_mercusys_be3600_%s.png" % mode)
        page.screenshot(path=path, full_page=True)
        return path
    except Exception:
        return ""


# ---------------------------------------------------------------------------
def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Mercusys BE3600 —— WAN 拨号方式切换"
                    "(默认只切换不保存,加 --apply 才真正下发)")
    parser.add_argument("mode", choices=MODES, help="目标拨号方式")
    parser.add_argument("--apply", action="store_true",
                        help="真正点保存(默认不点,先看回读)")
    parser.add_argument("--perf", action="store_true",
                        help="跑整轮:逐档切换 + 测吞吐 + 出报告(必定下发)")
    args = parser.parse_args(argv)

    # 台架 Windows 控制台是 GBK:回读里只要有一个 GBK 编不出的字符,print
    # 就会抛 UnicodeEncodeError 把整轮打断 —— 在最不该崩的时候崩。用 ? 顶掉。
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors="replace")
        except Exception:
            pass

    cfg = perf.load(model="Mercusys_BE3600")
    cfg.require("router.ip", "router.pass")

    if args.perf:
        cfg.setdefault("run", {})["apply"] = True        # 整轮必定下发
        return 0 if perf.run(switch, MODES, cfg)["ok"] else 2

    cfg.setdefault("run", {})["apply"] = bool(args.apply)
    res = switch(args.mode, cfg)
    print(json.dumps(res, ensure_ascii=False, indent=2))
    if res["success"] and not args.apply:
        print("[hint] 已确认切换(回读=%r)但未点保存;加 --apply 真正下发。"
              % res["read_back"])
    return 0 if res["success"] else 2


if __name__ == "__main__":
    sys.exit(main())
