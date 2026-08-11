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
这个文件是**自足**的:除了 common/contract.py(判定)和 common/perf.py
(整轮节拍 + 读 config.yaml),不依赖仓库里任何别的代码。下面那几个 _find /
_poll 小工具在别的型号脚本里也有一份几乎一样的 —— **那是故意的**。共用一层
"动词库"的代价是:改第六台机有可能悄悄弄坏前五台,而那种坏法是静默的
(切了、看起来成功、保存的是旧值)。重复换来的是:删掉任意一个型号文件,
其余六个照跑。
"""
import argparse
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

_NAV_MS, _DIAL_MS, _FIELD_MS, _LOGIN_MS = 6000, 8000, 3000, 8000
_STEP_MS, _SETTLE_MS = 200, 300


# ---------------------------------------------------------------------------
# 这台机自己的几个小工具(和别的型号脚本重复是故意的,见文件头)
# ---------------------------------------------------------------------------
def _settle(page, ms=_SETTLE_MS):
    """等页面消化上一步操作(这台机是整页刷新的老 UI)。"""
    try:
        page.wait_for_timeout(ms)
    except Exception:
        pass


def _poll(page, fn, timeout_ms, step_ms=_STEP_MS):
    """反复执行 fn 直到返回真值或超时;fn 抛异常按"还没好"处理。"""
    waited = 0
    while True:
        try:
            res = fn()
        except Exception:
            res = None
        if res:
            return res
        if waited >= timeout_ms:
            return None
        _settle(page, step_ms)
        waited += step_ms


def _first_visible(locator):
    try:
        n = min(locator.count(), 25)
    except Exception:
        return None
    for i in range(n):
        el = locator.nth(i)
        try:
            if el.is_visible():
                return el
        except Exception:
            continue
    return None


def _find(page, sel, require_visible=True):
    """跨**所有 frame** 找第一个可见匹配。

    这台机是老式 frameset:登录在主文档、菜单在 top frame、WAN 表单在
    tcpipwan.htm 子 frame —— 只扫主文档的话什么都找不到。
    require_visible=False 时也接受隐藏元素(被美化插件藏起来的原生 <select>
    是 display:none 的)。
    """
    try:
        frames = list(page.frames)
    except Exception:
        frames = []
    for fr in frames:
        try:
            loc = fr.locator(sel)
        except Exception:
            continue
        el = _first_visible(loc)
        if el:
            return el
        if not require_visible:
            try:
                if loc.count() > 0:
                    return loc.first
            except Exception:
                pass
    return None


def _facts_for(mode):
    """套 mode_overrides:被覆盖的键整个替换(PPTP/L2TP 各有一套 fields)。"""
    merged = dict(FACTS)
    for key, value in (FACTS.get("mode_overrides") or {}).get(mode, {}).items():
        merged[key] = value
    return merged


def _params_for(mode, cfg):
    """这一档要填的账密,从 config.yaml 取。返回 (参数, 缺了哪几项)。

    **只取这一档要的**:PPPoE 账密绝不会漏进 dynamic 的运行。
    """
    params, missing = {}, []
    for concept, where in NEEDS.get(mode, {}).items():
        value = cfg.at(where)
        if value is None or not str(value).strip():
            missing.append(where)
        else:
            params[concept] = str(value)
    return params, missing


def _launch(cfg):
    """开浏览器,返回 (playwright, browser, context, page)。

    离线优先级:config.yaml 写死的可执行文件 -> 系统装的 Chrome(channel)
    -> Playwright 自带的 chromium(要预置浏览器包)。台架是离线的,不会去下载。
    """
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
    return pw, browser, context, context.new_page()


def _shot(page, cfg, mode):
    """整页截图存进 artifacts/;失败返回空串,绝不因此中断一轮。"""
    try:
        out_dir = cfg.at("report.dir") or "artifacts"
        if not os.path.isabs(out_dir):
            out_dir = os.path.join(ROOT, out_dir)
        os.makedirs(out_dir, exist_ok=True)
        path = os.path.join(out_dir, "model_cudy_ax1500_%s.png" % mode)
        page.screenshot(path=path, full_page=True)
        return path
    except Exception:
        return ""


# ---------------------------------------------------------------------------
# 切换:登录 → 走菜单 → 选档(当场回读)→ 填账密 → 保存
# ---------------------------------------------------------------------------
def switch(mode, cfg, hook=None):
    """把这台机的 WAN 拨号方式切成 mode,返回 contract.result(...)。

    要不要真的点保存看 cfg["run"]["apply"](CLI 的 --apply / 整轮时恒为真)。
    默认**只切换不下发** —— 切错档会当场断网,台架上没人能远程救回来。

    hook: 可选 callable(page),关浏览器前调用,返回值存进 result["verify"]。
    冒烟测试用它读页面上的 toast(证明保存键真的按下去了、而且按的是对的
    那个);将来接"WAN 真拨通"验证也在这。
    """
    facts = _facts_for(mode)
    label = (facts.get("modes") or {}).get(mode, "")
    ident = {"brand": FACTS["brand"], "model": FACTS["model"], "mode": mode}
    warnings = []

    def failed(message, read_back=""):
        # 失败也只能走 verify():空回读永远判假,伪造不出成功。
        return contract.result(contract.verify(read_back, label), read_back,
                               label, message=message, warnings=warnings, **ident)

    if mode not in MODES:
        return failed("这台机不支持 %r(支持:%s)" % (mode, ", ".join(MODES)))

    # --- 碰路由器之前:配置齐不齐 -------------------------------------------
    params, missing = _params_for(mode, cfg)
    if missing:
        return failed(
            "切 %s 缺配置:%s。用记事本补 %s,这一档没有碰路由器。"
            % (mode, "、".join("%s(%s)" % (m, cfg.where(m)) for m in missing),
               cfg.source or "config.yaml"))
    admin_pass = str(cfg.at("router.pass") or "")
    if not admin_pass:
        return failed("没有管理密码:%s 的 router.pass 没填。"
                      % cfg.where("router.pass"))
    url = str(cfg.at("router.ip") or FACTS["url"]).strip()
    if not url.startswith("http"):
        url = "http://" + url

    apply_it = bool(cfg.at("run.apply"))
    pw = browser = context = page = None
    read_back, verdict, message, applied, filled = "", None, "", False, []
    verify_out, shot = None, ""

    def drive(page):
        """开着浏览器的那一段。返回失败原因(空串 = 走完了)。

        **中途失败不 return 出去**,而是把原因交回给外面 —— 外面统一截图 +
        跑 hook 再关浏览器。失败时那张截图正是排查要用的东西,早退就没有了。
        """
        nonlocal read_back, verdict, applied, filled

        # --- 登录 -----------------------------------------------------------
        # 登录框是主文档里的 #pwd。没出现 = 已经在会话里(直接往下走);
        # 填了却还停在登录页 = 如实报登录失败,不能带着未登录状态往下走再
        # 误报"找不到拨号控件"。
        pw_sel = facts["login"]["password"]
        pwd = _poll(page, lambda: _find(page, pw_sel), _LOGIN_MS)
        if pwd:
            pwd.fill(admin_pass)
            btn = _poll(page, lambda: _find(page, facts["login"]["button"]), 2000)
            if btn:
                btn.click()
            else:
                pwd.press("Enter")
            if not _poll(page, lambda: _find(page, pw_sel) is None, _LOGIN_MS):
                return ("登录失败 —— 仍停在登录页。检查 %s 的管理密码;"
                        "另外这台机同一时间只允许一个 Web 会话,"
                        "先关掉其他已登录的页签。" % cfg.where("router.pass"))

        # --- 走菜单:Network -> WAN ------------------------------------------
        # 登录后默认落在 Management/Status,必须点过去。两个锚点分别在顶部
        # 菜单帧和左侧菜单帧里 —— 所以 _find 是全 frame 扫的。
        for item in facts["wan_path"]:
            sel = item[4:] if item.startswith("sel:") else item
            el = _poll(page, lambda s=sel: _find(page, s), _NAV_MS)
            if el:
                el.click()
                _settle(page)
            else:
                warnings.append("菜单没找到:%r" % item)

        # --- 选档 + 当场真实回读 ---------------------------------------------
        # 原生 <select>,可能被美化插件藏起来(display:none),所以
        # require_visible=False + select_option(force=True):它会派发
        # input+change,美化皮和路由器自己的 JS 都监听得到。
        css = facts["dial"]["selector"]
        sel_el = _poll(page, lambda: _find(page, css, require_visible=False),
                       _DIAL_MS)
        if not sel_el:
            return "没找到拨号控件:%s" % css
        try:
            sel_el.select_option(label=label, force=True)
        except Exception as exc:
            try:
                seen = sel_el.evaluate(
                    "el => Array.from(el.options).map(o => o.text).join(' / ')")
            except Exception:
                seen = ""
            return ("select_option(%r) 失败:%s%s"
                    % (label, exc, "(选项有:%s)" % seen if seen else ""))
        _settle(page)
        try:
            read_back = (sel_el.evaluate(
                "el => el.options[el.selectedIndex]"
                " ? el.options[el.selectedIndex].text : ''") or "").strip()
        except Exception:
            read_back = ""
        # **这一行是这个脚本唯一的判定**:控件自己显示的当前值 == 目标措辞。
        verdict = contract.verify(read_back, label)

        # --- 填账密(回读没过就不填:页面状态还不明,填进去等于往未知表单
        #     里打字)----------------------------------------------------------
        if verdict:
            for concept in NEEDS.get(mode, {}):
                field_sel = (facts.get("fields") or {}).get(concept)
                if not field_sel:
                    warnings.append("FACTS.fields 缺 %r 的选择器" % concept)
                    continue
                # 账密框在选完模式后才挂载,等它出现。
                el = _poll(page, lambda s=field_sel: _find(page, s), _FIELD_MS)
                if el:
                    el.fill(params[concept])
                    filled.append(concept)
                else:
                    warnings.append("输入框没出现:%s -> %s"
                                    % (concept, field_sel))

        # --- 保存(只有回读通过、且这一轮要求下发时才点)---------------------
        # 保存键旁边埋着 8 个隐藏的 Connect/Disconnect 提交按钮,全是诱饵 ——
        # 只认 input[name='save_apply'],绝不按文字 "Connect" 找。
        if verdict and apply_it:
            btn = _poll(page, lambda: _find(page, facts["apply"]), _FIELD_MS)
            if btn:
                btn.click()
                applied = True
                _settle(page, FACTS.get("apply_settle_ms", 500))
            else:
                # 证据优先:把页面上真正可见的按钮列出来。真机上出过一次
                # "按钮文字在里层 span,选择器漏了"—— 有这张清单就不用为了
                # 看一眼页面再上一次台架。input[type=submit] 的文字在 value 里。
                seen = []
                for fr in page.frames:
                    try:
                        loc = fr.locator(
                            "button, input[type=submit], input[type=button]")
                        for i in range(min(loc.count(), 12)):
                            b = loc.nth(i)
                            if not b.is_visible():
                                continue
                            txt = (b.inner_text() or "").strip()
                            if not txt:
                                txt = (b.input_value() or "").strip()
                            if txt and txt not in seen:
                                seen.append(txt)
                    except Exception:
                        continue
                warnings.append(
                    "保存键没找到:%s%s"
                    % (facts["apply"],
                       "(页面可见按钮:%s)" % " / ".join(seen) if seen else ""))
        return ""

    try:
        pw, browser, context, page = _launch(cfg)
        page.goto(url, wait_until="domcontentloaded")
        message = drive(page)
        # 成败都跑到这:失败时的截图正是排查要用的证据。
        if hook is not None:
            try:
                verify_out = hook(page)
            except Exception as exc:
                warnings.append("hook: %s" % exc)
        shot = _shot(page, cfg, mode)
    finally:
        for closer in (context, browser):
            try:
                if closer:
                    closer.close()
            except Exception:
                pass
        try:
            if pw:
                pw.stop()
        except Exception:
            pass

    res = contract.result(verdict if verdict is not None
                          else contract.verify(read_back, label),
                          read_back, label, message=message, screenshot=shot,
                          applied=applied, filled=filled, warnings=warnings,
                          **ident)
    if hook is not None:
        res["verify"] = verify_out
    return res


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
        cfg.setdefault("run", {})["apply"] = True    # 整轮必定下发
        return 0 if perf.run(switch, MODES, cfg)["ok"] else 2

    cfg.setdefault("run", {})["apply"] = bool(args.apply)
    res = switch(args.mode, cfg)
    import json
    print(json.dumps(res, ensure_ascii=False, indent=2))
    if res["success"] and not args.apply:
        print("[hint] 已确认切换(回读=%r)但未点保存;加 --apply 真正下发。"
              % res["read_back"])
    return 0 if res["success"] else 2


if __name__ == "__main__":
    sys.exit(main())
