"""BUFFALO WSR-6000AX8(url=http://192.168.11.1/advanced.html)—— WAN 拨号方式
切换脚本。

这台机存在的理由是**日本 IPoE 的拨号对比**:transix / v6プラス /
OCN バーチャルコネクト / v6 コネクト,四档和 DHCP/PPPoE 一起以 radio 列在
wan.html 同一页上。

用法(默认只切换不保存;确认回读无误后加 --apply 才真正下发):
    python models/BUFFALO_WSR6000AX8.py dynamic
    python models/BUFFALO_WSR6000AX8.py v6plus --apply
管理密码取自 config.yaml,不用敲在命令行上。

事实来源:2026-07-31 真机取证,六档模式的 --apply 均已在真机验过;
2026-08-06 换了登录和导航的实现后又在真机复验通过(六档逐个回读正确并下发)。
**FACTS 是重构前原样搬过来的,一个字符没改。**

**和别的机型差三步(都在下面写死了):**
  1. 设置页必须以 **iframe** 打开。直接打开 wan.html 也能渲染、radio 也点得动、
     回读也通过,但页面的配置对象 CA 没加载,保存提交的是**旧值** —— 一次 DOM
     上完全看不出来的假成功。所以"就绪"= url 到位 + CA 到位 + 拨号控件已出现,
     三条同时成立才算数,而且页面脚本有时会把 iframe 地址改回去,要重试。
  2. radio 和保存键都被 CSS 遮住,两处都得 force 点(Playwright 的可操作性
     检查会超时,报 "... intercepts pointer events")。
  3. 点完保存要等 15 秒:它是 iframe 里异步提交 + 轮询,点完立刻关浏览器等于
     把保存打断(FACTS 的 apply_settle_ms)。

**PPPoE 账密在另一页**(pppoe_reg.html),本脚本不去那页:要跑 PPPoE 吞吐,
先在路由器 Web UI 里把宽带账号建好。
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
    "brand": "BUFFALO",
    "model": "WSR-6000AX8",
    # 必须先进 advanced.html 框架,再让 iframe 加载 wan.html,
    # 这样 wan.html 才能获得完整的配置对象 CA。
    "url": "http://192.168.11.1/advanced.html",

    # 登录页:用户名通常已预填,只需填密码后点登录按钮。
    # #login_base 初始 display:none,由 JS 显示 —— 驱动会轮询等它可见再填。
    "login": {
        "password": "#form_PASSWORD",
        "button": "input.button_login",
    },

    # 拨号页在 advanced.html 的菜单中:詳細設定 -> Internet -> Internet。
    # 左侧菜单点不动(dt.WAN 默认隐藏、iconDisable 与异步初始化都会挡),
    # 所以不走 wan_path,而是让 goto_iframe 直接把 iframe 导过去。
    "menu_selector": "p.CONNECT[data-main='wan.html']",   # 事实记录,不点它
    "iframe_selector": "iframe#content_main",
    "iframe_target": "wan.html",
    # 「配置到位了吗」的判据。CA 是 wan.html 自己的配置对象:直接打开这一页
    # 时它不会被加载,而页面照样渲染、radio 照样点得动、回读照样通过,保存却
    # 提交旧值 —— 一次 DOM 上看不出来的假成功。所以就绪必须查它。
    "iframe_ready_js": "CA.length > 0",

    # 拨号控件:原生 radio 组。radio 被 CSS 遮住,run() 里用 force 点。
    "dial": {"kind": "radio", "selector": "input[name='WanMethod']"},

    # 各模式在 wan.html 上对应的 radio 选择器(已用 --count 验证唯一)。
    # 键名用 dynamic 而不是 dhcp:模式名是**跨层的**,matrix/chariot_perf.py
    # 的 _e2_ip() 按它决定这一格打公网口还是内网口,modes.py 按它决定这档要
    # 哪些参数。叫 dhcp 的话,这台机的直连档会被当成隧道档打到内网口 ——
    # 数字照样出得来,测的却不是那条路。
    "modes": {
        "dynamic":   "input#id_method2",   # DHCP
        "pppoe":     "input#id_method3",   # PPPoE
        "transix":   "input#id_method5",   # v4overv6 / transix
        "v6plus":    "input#id_method6",   # v6プラス
        "ocnvc":     "input#id_method8",   # OCN バーチャルコネクト
        "v6connect": "input#id_method10",  # v6 コネクト
    },

    # PPPoE 账密框在 pppoe_reg.html,和拨号页不是同一页,本脚本不去那页。
    # 选择器留在这里是事实记录;真要跑 PPPoE 吞吐,账号得先在 Web UI 的
    # pppoe_reg.html 里建好。fields_page 一写,给了 --param 只会得到一条
    # warning,绝不会静默装作填过了。
    "fields": {
        "pppoe_user": "input#id_PUsername",
        "pppoe_pass": "input#id_PPassword",
    },
    "fields_page": "pppoe_reg.html",

    # wan.html 保存键(在 iframe 内,被遮挡,force 点)。
    "apply": "div#button_1",

    # Buffalo 用 iframe 异步提交,点保存后需要等提交/轮询完成 —— 点完立刻
    # 关浏览器等于把保存打断。
    "apply_settle_ms": 15000,
}

# 这台机能切哪几档,按台架轮次的顺序:DHCP + PPPoE + 日本 IPoE 四档。
# 键名用 dynamic 而不是 dhcp:模式名是**跨层的** —— matrix/chariot_perf.py 的
# _e2_ip() 按它决定这一格打公网口还是内网口。叫 dhcp 的话,这台机的直连档会被
# 当成隧道档打到内网口:数字照样出得来,测的却不是那条路。
MODES = ["dynamic", "pppoe", "transix", "v6plus", "ocnvc", "v6connect"]

# 每档要 config.yaml 里的哪几项 -> 填进哪个概念。
# **全是空的,这台机是特例**:PPPoE 的账密框在另一页(pppoe_reg.html),本脚本
# 不去那页,所以要人先在路由器 Web UI 里把宽带账号建好。既然工具填不了,就
# 不该拦着不让切 —— 那是把工具的短板变成使用者的错。第 6 步会为此发一条警告。
NEEDS = {
    "dynamic": {}, "pppoe": {}, "transix": {}, "v6plus": {}, "ocnvc": {},
    "v6connect": {},
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
# 切换:登录 → iframe 打开设置页 → 选档(当场回读)→ 填账密 → 保存
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
    label = mode
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
    if "/" not in url.split("//", 1)[-1]:
        # config.yaml 里只写了 IP,但这台机必须从 advanced.html 外壳页进
        # (直接打开 wan.html 的话配置对象 CA 不会加载)。把 FACTS 里那条路径
        # 接上去;router.ip 自己带了路径就尊重它。
        url = url.rstrip("/") + "/" + FACTS["url"].rsplit("/", 1)[-1]
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
                                "%s" % (cfg.where("router.pass"), "#login_base 初始是隐藏的,由页面 JS 显示 —— 上面已经等过它。"))
                _pause(page, _STEP_MS)
                waited += _STEP_MS

        # --- 4. 把设置页**以 iframe 打开**,并确认它真的就绪 -------------------
        # 左侧菜单点不动(dt.WAN 默认隐藏、iconDisable 和异步初始化都会挡),
        # 所以不走菜单,直接把 iframe 的地址导过去。
        # 就绪 = url 到位 + 配置对象 CA 到位 + 拨号控件已出现,三条同时成立。
        # 只看 url 是不够的:CA 没加载时页面照样渲染、回读照样通过,保存下去的
        # 却是旧值。要重试是因为页面自己的脚本有时会把 iframe 地址改回去。
        iframe_sel = facts["iframe_selector"]
        target = facts["iframe_target"]
        ready_js = facts.get("iframe_ready_js")
        dial_sel = (facts.get("dial") or {}).get("selector") or ""
        seen_url = ""

        def iframe_ready():
            fl = page.frame_locator(iframe_sel)
            root = fl.locator(":root")
            here = root.evaluate("() => location.href") or ""
            if target.split("?")[0] not in here:
                return ""
            if ready_js:
                # 配置对象可能还没赋值 —— 求值抛异常按"还没好"处理。
                good = root.evaluate(
                    "() => { try { return !!(%s); } catch (e) { return false; } }"
                    % ready_js)
                if not good:
                    return ""
            if dial_sel and fl.locator(dial_sel).count() < 1:
                return ""
            return here

        for _attempt in range(10):
            try:
                page.evaluate(
                    """([sel, dest]) => {
                        var frm = document.querySelector(sel);
                        if (!frm) throw new Error("iframe not found: " + sel);
                        var rnd = parseInt(Math.random() * 100000000);
                        frm.contentWindow.location.href =
                            dest + (dest.indexOf('?') < 0 ? '?' : '&')
                            + 'rnd=' + rnd;
                    }""", [iframe_sel, target])
            except Exception as exc:
                # 外壳页根本没打开时就是这一条(页面上没有那个 iframe)。
                # 前半句说"哪一步没过",后半句是原始报错 —— 两个都要:
                # 只有前半句查不出原因,只有后半句看不出这一步是承重的。
                raise _Stop("设置页没在 iframe 里就绪:设置 iframe 地址失败:%s"
                            % exc)
            _pause(page, 500)
            waited, hit = 0, ""
            while waited < 8000:
                try:
                    hit = iframe_ready()
                except Exception:
                    hit = ""
                if hit:
                    break
                _pause(page, _STEP_MS)
                waited += _STEP_MS
            if hit:
                break
            try:
                seen_url = page.frame_locator(iframe_sel).locator(
                    ":root").evaluate("() => location.href") or ""
            except Exception:
                pass
        else:
            raise _Stop(
                "%s 没在 iframe 里就绪(试了 10 轮)。iframe 当前 url=%r;"
                "就绪判据 %r 未成立 —— 这一步不通过就绝不能往下走,"
                "否则保存下去的是旧值。" % (target, seen_url, ready_js))

        # --- 5. 选档(radio),当场真实回读 -----------------------------------
        # radio 被皮盖住,必须 force 点。只信真 radio 的 is_checked() ——
        # 读不出状态就不许报成功。
        radio_sel = (facts.get("modes") or {}).get(mode, "")
        radio = _find(page, radio_sel, wait_ms=_DIAL_MS)
        if not radio:
            raise _Stop("没找到模式 radio:%s" % radio_sel)
        try:
            radio.click(force=True)
        except Exception as exc:
            raise _Stop("点 %s 的 radio 失败:%s" % (mode, str(exc).splitlines()[0]))
        _pause(page)
        try:
            checked = radio.is_checked()
        except Exception:
            raise _Stop("点了 %s,但 %s 不是一个可回读的 radio —— 选择器指错了。"
                        % (mode, radio_sel))
        # radio 的"措辞"是个选择器,报出来没有意义 —— 回读记模式名,
        # 目标措辞(label)也就是模式名,两边同一把尺子。
        read_back = mode if checked else ""

        # --- 6. 账密:这台机填不了 ---------------------------------------------
        # PPPoE 的账密框在 pppoe_reg.html,和拨号页不是同一页,本脚本不去那页。
        # **逐个说出来,绝不静默装作填过了** —— config.yaml 里填了宽带账号的人
        # 会以为工具替他填了,然后拿一个没建过的账号去拨,现象是"切换成功但
        # 拨不上",最难查。
        if contract.verify(read_back, label) and mode == "pppoe":
            for concept, where in (("pppoe_user", "router.pppoe_user"),
                                   ("pppoe_pass", "router.pppoe_pass")):
                if str(cfg.at(where) or "").strip():
                    warnings.append(
                        "参数 %s 没有填:它的输入框在 %s,和拨号页不是同一页。"
                        "请先在路由器 Web UI 里配好。"
                        % (concept, facts.get("fields_page", "另一个页面")))

        # --- 7. 保存(只有回读通过、且这一轮要求下发时才点)---------------------
        # 保存键也被遮住,同样 force 点;点完要等 15 秒(FACTS.apply_settle_ms)
        # —— 它是 iframe 里异步提交 + 轮询,点完立刻关浏览器等于把保存打断。
        if contract.verify(read_back, label) and apply_it:
            btn = _find(page, facts["apply"], wait_ms=_FIELD_MS)
            if btn:
                btn.click(force=True)
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
        path = os.path.join(out_dir, "model_buffalo_wsr6000ax8_%s.png" % mode)
        page.screenshot(path=path, full_page=True)
        return path
    except Exception:
        return ""


# ---------------------------------------------------------------------------
def main(argv=None):
    parser = argparse.ArgumentParser(
        description="BUFFALO WSR-6000AX8 —— WAN 拨号方式切换"
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

    cfg = perf.load(model="BUFFALO_WSR6000AX8")
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
