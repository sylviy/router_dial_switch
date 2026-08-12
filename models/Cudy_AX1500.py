"""Cudy AX1500(测试台那台,192.168.10.1;固件 1.0.1-20240321,SSID Cudy-554C)
—— WAN 拨号方式切换脚本。

**注意台架上有两台 Cudy,UI 完全不同**:这台是 Realtek-SDK 的老式 **frameset**
固件;另一台 AX3000 是 **LuCI/OpenWrt**(见 models/Cudy_AX3000.py)。两份脚本
并存,别把选择器互相搬。

用法(默认只切换不保存;确认回读无误后加 --apply 才真正下发):
    python models/Cudy_AX1500.py dynamic
    python models/Cudy_AX1500.py pppoe
    python models/Cudy_AX1500.py pppoe --apply
    python models/Cudy_AX1500.py dynamic --perf      # 整轮:逐档切+测吞吐+出报告
账号密码全部取自 config.yaml,不用敲在命令行上。

事实来源:2026-07-18 真机取证(只读探针两轮;所有选择器命中数已用运行时
引擎验证)。**FACTS 是重构前原样搬过来的,一个字符没改。**
UI 形态:老式 **frameset** —— 登录在主文档,菜单和 WAN 表单在各自子 frame 里
(所以下面每个查找都全 frame 扫),控件是带 id/name 的原生 HTML,非常好伺候。

**IPv6:本固件构建里被关掉了,不是我没找到**(2026-07-18 穷尽核查):
  * 枚举固件引用的全部 49 个页面,逐个 GET 全文搜 ipv6 —— 没有任何 IPv6 配置页;
    `sub_menu_ipv6.htm` / `ipv6.htm` 等直接访问全部 404(页面根本没打包进来);
  * `navigation.js` 里**有完整的 IPv6 菜单代码**:
    `if(ipv6){ ... add_topMenuItem("sub_menu_ipv6.htm","ipv6"); }`;
  * 但服务端生成的 `top_menu.htm` 里写的是 `var ipv6 = 0;`(同批变量如
    `wlan_num = 2` 是按本机实际情况注入的),所以那段菜单永远不画;
  * WAN 页有个 `input[name='ipv6_passthru_enabled']`,但它所在的 `<tr>` 是
    `display:none`,五种拨号方式下都不显形 —— 死代码。
=> 这台机当前固件(1.0.1-20240321)**无法通过 Web UI 配置 IPv6**。若测试需要
v6,只能先升级/更换固件(升级后重新用 skill/tools/ 的探针复核)。

--------------------------------------------------------------------------
## 这个文件怎么读

从上往下就是台架上会发生的事,中间不跳到别的文件:

    FACTS / MODES / NEEDS   纯数据:这台机的选择器、能切哪几档、每档要哪些账密
    _pause / _find          两个小工具。**只有这两个要先看懂**
    switch()                主角。第 1~7 步依次是:查配置 → 开浏览器 → 登录 →
                            走菜单 → 选档并回读 → 填账密 → 保存
    _visible_buttons        出错时把页面上的按钮列出来当证据
    _screenshot / main()    截图、命令行

这个文件是**自足**的:除了 common/contract.py(判定)和 common/perf.py
(整轮节拍 + 读 config.yaml),不依赖仓库里任何别的代码。_pause / _find 在
别的型号脚本里也有一份几乎一样的 —— **那是故意的**。共用一层"动词库"的
代价是:改第六台机有可能悄悄弄坏前五台,而那种坏法是静默的(切了、看起来
成功、保存的是旧值)。重复换来的是:删掉任意一个型号文件,其余六个照跑。
"""
import argparse
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from common import contract, perf

FACTS = {
    "brand": "Cudy",
    "model": "AX1500",
    "url": "http://192.168.10.1",

    # 登录页在主文档:#pwd(name=password);登录键是 input[type=submit],
    # 文字在 value 里(真机实录)。
    "login": {"password": "#pwd", "button": "input[value='Login']"},

    # 导航:顶部菜单帧的 Network -> 左侧菜单帧的 WAN(锚点 id 即菜单文字,
    # 已验证唯一;登录后默认落在 Management/Status,必须点过去)。
    "wan_path": ["sel:#Network", "sel:#WAN"],

    # 拨号控件:原生 <select>,id 锚定,在 tcpipwan.htm 子 frame 里。
    "dial": {"kind": "select", "selector": "#wanType_id"},

    # 下拉选项逐字实录。注意 dynamic 在这台叫 "DHCP Client"。
    "modes": {"dynamic": "DHCP Client", "static": "Static IP",
              "pppoe": "PPPoE", "pptp": "PPTP", "l2tp": "L2TP"},

    # 选 PPPoE 后可见的账密框(name 锚定,真机实录)。
    "fields": {
        "pppoe_user": "input[name='pppUserName']",
        "pppoe_pass": "input[name='pppPassword']",
    },

    # 保存键:input[name='save_apply'](value "Save & Apply",可见且唯一)。
    # 千万别按文字 "Connect" 找 —— 该帧藏着 8 个隐藏的
    # ppp/pptp/l2tp/USB3G Connect/Disconnect 提交按钮,全是诱饵。
    "apply": "input[name='save_apply']",

    # PPTP / L2TP 各有一套 name 前缀不同的字段;vpn_server 用 IP 字段
    # (测试环境用 IP;要用域名时改成 *ServerDomainName)。
    "mode_overrides": {
        "pptp": {
            "fields": {
                "vpn_server": "input[name='pptpServerIpAddr']",
                "vpn_user":   "input[name='pptpUserName']",
                "vpn_pass":   "input[name='pptpPassword']",
            },
        },
        "l2tp": {
            "fields": {
                "vpn_server": "input[name='l2tpServerIpAddr']",
                "vpn_user":   "input[name='l2tpUserName']",
                "vpn_pass":   "input[name='l2tpPassword']",
            },
        },
    },
}

# 这台机能切哪几档,按台架轮次的顺序。
MODES = ["dynamic", "static", "pppoe", "pptp", "l2tp"]

# 每档要 config.yaml 里的哪几项 -> 填进哪个概念。**碰路由器之前**核对,
# 缺了就记成这一档失败,不开浏览器(拿空账号下发 PPPoE = 当场断网)。
# static 故意是空的:各家的 IP/掩码/网关差异太大,还没建模,整轮里请避开它。
NEEDS = {
    "dynamic": {},
    "static": {},
    "pppoe": {"pppoe_user": "router.pppoe_user",
              "pppoe_pass": "router.pppoe_pass"},
    "pptp": {"vpn_server": "router.pptp.server", "vpn_user": "router.pptp.user",
             "vpn_pass": "router.pptp.pass"},
    "l2tp": {"vpn_server": "router.l2tp.server", "vpn_user": "router.l2tp.user",
             "vpn_pass": "router.l2tp.pass"},
}

# 各步最多等多久(毫秒)。老 UI 是整页刷新,给得比 SPA 宽一点。
_LOGIN_MS, _NAV_MS, _DIAL_MS, _FIELD_MS = 8000, 6000, 8000, 3000
_STEP_MS, _PAUSE_MS = 200, 300


class _Stop(Exception):
    """半路走不下去了(没找到控件、登录没进去……)。

    用异常而不是 return:失败也要**先截图再关浏览器**,那张截图正是排查
    要用的东西。switch() 在一个地方接住它,截完图再把原因写进结果。
    """


# ---------------------------------------------------------------------------
# 两个小工具。整个文件只有这两个需要先看懂,别的都是照着流程念下来的。
# 别的型号脚本里会有几乎一样的两份 —— 那是故意的,见文件头。
# ---------------------------------------------------------------------------
def _pause(page, ms=_PAUSE_MS):
    """等一会儿,让页面消化上一步操作(这台机是整页刷新的老 UI)。"""
    try:
        page.wait_for_timeout(ms)
    except Exception:
        pass


def _find(page, sel, wait_ms=0, visible=True):
    """在**所有 frame** 里找一个元素;wait_ms 内没出现就返回 None。

    为什么要扫所有 frame:这台机是老式 frameset —— 登录框在主文档、菜单在
    顶部帧、WAN 表单在 tcpipwan.htm 子帧里。只看主文档的话什么都找不到。

    visible=False:连隐藏的也认。被美化插件藏起来的原生 <select> 是
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
    facts = dict(FACTS)
    for key, value in (FACTS.get("mode_overrides") or {}).get(mode, {}).items():
        facts[key] = value                  # PPTP/L2TP 各有一套 fields
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
        value = cfg.at(where)               # 只取这一档要的:PPPoE 账密绝不
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
        pw_sel = facts["login"]["password"]
        pwd = _find(page, pw_sel, wait_ms=_LOGIN_MS)
        if pwd:
            pwd.fill(admin_pass)
            btn = _find(page, facts["login"]["button"], wait_ms=2000)
            if btn:
                btn.click()
            else:
                pwd.press("Enter")
            waited = 0
            while _find(page, pw_sel) is not None:      # 等密码框消失
                if waited >= _LOGIN_MS:
                    raise _Stop("登录失败 —— 仍停在登录页。检查 %s 的管理密码;"
                                "另外这台机同一时间只允许一个 Web 会话,"
                                "先关掉其他已登录的页签。"
                                % cfg.where("router.pass"))
                _pause(page, _STEP_MS)
                waited += _STEP_MS

        # --- 4. 走菜单:Network -> WAN ---------------------------------------
        # 登录后默认落在 Management/Status,必须点过去。两个锚点分别在顶部
        # 菜单帧和左侧菜单帧里(所以 _find 是全 frame 扫的)。
        for item in facts["wan_path"]:
            el = _find(page, item[4:], wait_ms=_NAV_MS)    # "sel:" 前缀
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
                # 账密框在选完模式后才挂载,等它出现。
                el = _find(page, field_sel, wait_ms=_FIELD_MS)
                if el:
                    el.fill(params[concept])
                    filled.append(concept)
                else:
                    warnings.append("输入框没出现:%s -> %s" % (concept, field_sel))

            # --- 7. 保存(只有回读通过、且这一轮要求下发时才点)---------------
            # 保存键旁边埋着 8 个隐藏的 Connect/Disconnect 提交按钮,全是诱饵
            # —— 只认 input[name='save_apply'],绝不按文字 "Connect" 找。
            if apply_it:
                btn = _find(page, facts["apply"], wait_ms=_FIELD_MS)
                if btn:
                    btn.click()
                    applied = True
                    _pause(page, FACTS.get("apply_settle_ms", 500))
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
        path = os.path.join(out_dir, "model_cudy_ax1500_%s.png" % mode)
        page.screenshot(path=path, full_page=True)
        return path
    except Exception:
        return ""


# ---------------------------------------------------------------------------
def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Cudy AX1500 —— WAN 拨号方式切换"
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

    cfg = perf.load(model="Cudy_AX1500")
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
