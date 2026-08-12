"""Cudy AX3000(192.168.10.1;LuCI / OpenWrt 固件,git-25.272.36397;
主机名 WR3000)—— WAN 拨号方式切换脚本。

用法(默认只切换不保存;确认回读无误后加 --apply 才真正下发):
    python models/Cudy_AX3000.py dynamic
    python models/Cudy_AX3000.py pppoe --apply
账号密码全部取自 config.yaml,不用敲在命令行上。

事实来源:2026-07-29 真机只读取证(登录页 curl + Playwright 控件抄录 + 逐 proto
字段发现 + 选择器命中数引擎验证)。每个选择器都由 Playwright 引擎实测命中数==1。
**FACTS 是重构前原样搬过来的,一个字符没改。**

UI 形态:**LuCI(CBI)**,单文档无 frameset。路由:主页面 → 顶部菜单
"General Settings"(/admin/setup)→ 该页 "WAN Mode" 段默认展开 → Protocol 是个
原生 <select>。PPPoE/L2TP/PPTP 的账密框在选完 proto 后由 LuCI AJAX 挂载,
下面第 6 步会轮询等它们出现。

与 models/Cudy_AX1500.py(老式 frameset 固件)不是同一台/同一固件 —— 那台是
Realtek-SDK frameset UI,这台是 LuCI。两份脚本并存,别把选择器互相搬。

**LuCI CBI 的两个坑(写进 FACTS 的原因):**
  * CBI 的 id 形如 `cbid.network.wan.proto`,**含点号**。CSS 里
    `#cbid.network.wan.proto` 会被解析成"id=cbid + 三个 class",命中 0。
    所以这里**一律用属性选择器** `[id='...']`,不用 `#...`。
  * 保存键 `button[name='cbi.apply']` 在 /admin/setup 上有 4 个(WAN / 2.4G /
    VPN / 其它各一个),不唯一。必须锚定到"包含拨号控件的那个 form"才命中 1。

**登录**:LuCI 用加盐哈希挑战(_csrf/token/salt 隐藏域 + JS 把可见密码框的值
哈希后填进隐藏的 luci_password 再提交)。纯 curl 发不出去,但填可见的
#luci_password2 后按回车,onsubmit 的 JS 会完成哈希提交 —— 已实测 login 成功。
FACTS 不给 login.button,所以下面第 3 步走回车。

**IPv6**:本脚本只覆盖 dynamic/pppoe/l2tp/pptp。LuCI 的 IPv6 在 /admin/setup
上没作为 proto 选项出现(选项就那 5 个)。
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
    "brand": "Cudy",
    "model": "AX3000",
    "url": "http://192.168.10.1",

    # 登录:#luci_password2 是登录页那个可见密码框(隐藏的 luci_password 是
    # type=hidden,不会被 input[type=password] 之外的精确 id 误中)。不给 button
    # —— 驱动填完按回车,LuCI 的 onsubmit JS 哈希后提交。
    "login": {"password": "#luci_password2"},

    # 导航:登录后落在 System Status,点顶部菜单 "General Settings"(唯一可见
    # 链接,文字精确匹配)进 /admin/setup,WAN Mode 段默认展开。
    "wan_path": ["General Settings"],

    # 拨号控件:原生 <select>。id 含点号,必须用属性选择器(见上文)。
    "dial": {"kind": "select", "selector": "[id='cbid.network.wan.proto']"},

    # 下拉选项逐字实录(真机)。dynamic 在这台叫 "DHCP(Dynamic IP)"。
    "modes": {"dynamic": "DHCP(Dynamic IP)", "pppoe": "PPPoE",
              "l2tp": "L2TP", "pptp": "PPTP"},

    # 字段:三种模式共用同一组 DOM id —— PPPoE 的 username/password 与 L2TP/PPTP
    # 的是同一个输入框,server 只在 L2TP/PPTP 出现。驱动按模式填,不会串。
    # 这些输入框在选完 proto 后才由 LuCI AJAX 挂载,_fill_params 会轮询等。
    "fields": {
        "pppoe_user": "[id='cbid.network.wan.username']",
        "pppoe_pass": "[id='cbid.network.wan.password']",
        "vpn_server": "[id='cbid.network.wan.server']",
        "vpn_user":   "[id='cbid.network.wan.username']",
        "vpn_pass":   "[id='cbid.network.wan.password']",
    },

    # 保存键:页面上有 4 个 name=cbi.apply 的 "Save & Apply",必须锚定到包含
    # 拨号控件的 form,否则会点到 2.4G/VPN 等其它段。引擎实测命中 1。
    "apply": "form:has([id='cbid.network.wan.proto']) button[name='cbi.apply']",
}

# 这台机能切哪几档,按台架轮次的顺序。
MODES = ["dynamic", "pppoe", "l2tp", "pptp"]

# 每档要 config.yaml 里的哪几项 -> 填进哪个概念。**碰路由器之前**核对,
# 缺了就记成这一档失败,不开浏览器(拿空账号下发 PPPoE = 当场断网)。
# 三种模式共用同一对 username/password 输入框,只有 server 是 L2TP/PPTP 才有;
# 按档取值就不会串。
NEEDS = {
    "dynamic": {},
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
                                "%s" % (cfg.where("router.pass"), "LuCI 的登录是加盐哈希挑战,由页面自己的 JS 完成提交。"))
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
        # 原生 <select>,可能被美化插件藏起来,所以 visible=False +
        # select_option(force=True):它会派发 input+change,美化皮和路由器
        # 自己的 JS 都监听得到。
        css = facts["dial"]["selector"]
        dial = _find(page, css, wait_ms=_DIAL_MS, visible=False)
        if not dial:
            raise _Stop("没找到拨号控件:%s" % css)
        try:
            dial.select_option(label=label, force=True)
        except Exception as exc:
            try:
                seen = dial.evaluate(
                    "el => Array.from(el.options).map(o => o.text).join(' / ')")
            except Exception:
                seen = ""
            raise _Stop("select_option(%r) 失败:%s%s"
                        % (label, exc, "(选项有:%s)" % seen if seen else ""))
        _pause(page)
        try:
            read_back = (dial.evaluate(
                "el => el.options[el.selectedIndex]"
                " ? el.options[el.selectedIndex].text : ''") or "").strip()
        except Exception:
            read_back = ""

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
        # 截图归到 artifacts/shots/,和报告分开放(artifacts/ 下三个子目录:
        # reports 报告、shots 截图、probes 探针产物)。
        out_dir = cfg.at("report.dir") or "artifacts"
        if not os.path.isabs(out_dir):
            out_dir = os.path.join(ROOT, out_dir)
        out_dir = os.path.join(out_dir, "shots")
        os.makedirs(out_dir, exist_ok=True)
        path = os.path.join(out_dir, "model_cudy_ax3000_%s.png" % mode)
        page.screenshot(path=path, full_page=True)
        return path
    except Exception:
        return ""


# ---------------------------------------------------------------------------
def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Cudy AX3000 —— WAN 拨号方式切换"
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

    cfg = perf.load(model="Cudy_AX3000")
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
