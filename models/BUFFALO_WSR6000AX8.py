"""BUFFALO WSR-6000AX8(url=http://192.168.11.1,管理密码见 router.yaml)

WAN 拨号切换脚本。**这台是特例:它自己实现 run(),不走 models/_driver.py。**

为什么是特例(三条都在真机上验过,少一条保存就不生效):
  * wan.html 必须**以 advanced.html 里的 iframe 形式**打开。直接开
    wan.html 页面能显示、radio 也能点,但配置对象 CA 不会被加载,apply()
    提交的是旧值 —— 也就是"切换看起来成功了,其实没保存"。
  * 左侧菜单点不动(dt.WAN 默认隐藏、iconDisable 与异步初始化都会挡),
    所以脚本直接改 iframe#content_main 的 contentWindow.location.href,
    改完还要重试:页面脚本有时会把它改回 info。
  * radio 和保存键在 iframe 里被 CSS 遮住,Playwright 的可操作性检查会超时,
    必须 force=True 点真实 input。

这些都不是"再加一个 FACTS 键"能表达的形状,塞进 _driver.py 会让另外五台机
背上一份 Buffalo 的特例。所以流程写在这里 —— 代价是本文件要自己负责
run()/run_cli() 的签名与 _driver 一致,整轮编排器(matrix/run.py 的
runner_for)才认得它。改签名前先看那个函数的注释。

IPv4 拨号方式全部以 radio 列在 wan.html 同一页,包含日本的 IPoE 各档
(transix / v6プラス / OCN バーチャルコネクト / v6 コネクト)。
PPPoE 账号密码在独立页 pppoe_reg.html:本脚本只切模式,账密要预先在 Web UI
里配好(见下面 fields 的注释)。

事实来源:2026-07-31 真机取证(probe_router.py --dump/--count),六档模式
的 --apply 均已在真机验过(artifacts/progress_BUFFALO_WSR6000AX8.md)。

用法(默认只切换不保存;确认回读无误后加 --apply 才真正下发):
    python models/BUFFALO_WSR6000AX8.py dynamic
    python models/BUFFALO_WSR6000AX8.py v6plus --apply
"""
import argparse
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import Config
from models._browser import Browser
from models._driver import available_modes, run_cli, screenshot
import settings as settings_mod

FACTS = {
    "brand": "BUFFALO",
    "model": "WSR-6000AX8",
    # 必须先进 advanced.html 框架,再让 iframe 加载 wan.html,
    # 这样 wan.html 才能获得完整的配置对象 CA。
    "url": "http://192.168.11.1/advanced.html",

    # 登录页:用户名通常已预填,只需填密码后点登录按钮。
    # #login_base 初始 display:none,由 JS 显示 —— 要轮询等它可见再填。
    "login": {
        "password": "#form_PASSWORD",
        "button": "input.button_login",
    },

    # 拨号页在 advanced.html 的菜单中:詳細設定 -> Internet -> Internet。
    # 菜单点不动,脚本改 iframe 的 location;这两个键留作事实记录。
    "menu_selector": "p.CONNECT[data-main='wan.html']",
    "iframe_selector": "iframe#content_main",

    # 拨号控件:原生 radio 组。
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

    # PPPoE 账密框在 pppoe_reg.html,和 wan.html 不是同一页,本脚本不去那页。
    # 选择器留在这里是事实记录;真要跑 PPPoE 吞吐,账号得先在 Web UI 的
    # pppoe_reg.html 里建好。给了 --param 也只会得到一条 warning,不会静默
    # 装作填过了。
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


def _do_login(page, password):
    pwd = page.locator(FACTS["login"]["password"])
    # 登录框(#login_base)初始 display:none,由 JS 显示,轮询等它可见。
    for _ in range(20):
        if pwd.count() and pwd.is_visible():
            break
        time.sleep(0.5)
    else:
        return False        # 没出现登录框:可能已在会话内,交给调用方判断
    pwd.fill(password)
    page.locator(FACTS["login"]["button"]).click()
    time.sleep(2)
    return True


def _enter_wan_iframe(page):
    """把 iframe#content_main 导到 wan.html,并等它真的就绪。

    就绪 = 三个条件同时成立:url 是 wan.html、CA 配置对象已加载、拨号 radio
    已出现。只看 url 不够 —— CA 没加载时页面照样渲染,保存却会提交旧值。
    """
    actual_url = ""
    for _attempt in range(10):
        page.evaluate("""()=>{
            var frm = document.querySelector("iframe#content_main");
            if (!frm) throw new Error("iframe#content_main not found");
            var rnd = parseInt(Math.random()*100000000);
            frm.contentWindow.location.href = "wan.html?rnd=" + rnd;
        }""")
        time.sleep(2)
        iframe = page.frame_locator(FACTS["iframe_selector"])
        for _ in range(20):
            try:
                actual_url = iframe.locator(":root").evaluate(
                    "()=>location.href") or ""
                if ("wan.html" in actual_url and
                        iframe.locator(":root").evaluate(
                            "()=>{try{return CA.length;}catch(e){return 0;}}") > 0 and
                        iframe.locator("input[name='WanMethod']").count() > 0):
                    return iframe
            except Exception:
                pass
            time.sleep(0.5)
        # 页面脚本把 location 改回去了:再来一轮。
    raise Exception("wan.html 未加载(或 CA 未就绪),当前 iframe url=%s"
                    % actual_url)


def run(facts=None, mode="dynamic", params=None, apply=False,
        admin_user="", admin_pass="", url=None, headless=None,
        config=None, verify_hook=None):
    """切换一次拨号方式。签名与 models/_driver.run 一致,整轮编排器才能调它。

    facts 参数是为了签名对齐而收下的,本脚本只用模块级的 FACTS —— 这台机的
    流程和它的 FACTS 是绑死的,换一份 facts 进来也驱动不了别的机器。
    """
    mode = (mode or "").lower()
    result = {
        "brand": FACTS["brand"], "model": FACTS["model"], "mode": mode,
        "success": False, "read_back": "", "filled": [], "applied": False,
        "message": "", "warnings": [], "screenshot": "",
    }
    if mode not in FACTS["modes"]:
        result["message"] = ("此型号脚本未定义模式 %r(可用:%s)"
                             % (mode, ", ".join(available_modes(FACTS))))
        return result

    # 账密在另一页,本脚本填不了 —— 说出来,不要让整轮以为它填过了。
    for key in sorted(params or {}):
        if (params or {})[key]:
            result["warnings"].append(
                "参数 %s 没有填:它的输入框在 %s,和拨号页不是同一页。"
                "PPPoE 账号请先在路由器 Web UI 里建好。"
                % (key, FACTS["fields_page"]))

    cfg = config or Config()
    if headless is not None:
        cfg.headless = headless
    if admin_pass and not cfg.http_pass:
        cfg.http_user, cfg.http_pass = (admin_user or "admin"), admin_pass

    with Browser(cfg) as br:
        page = br.goto(url or FACTS["url"])
        if not _do_login(page, admin_pass):
            result["warnings"].append(
                "没等到登录框(#form_PASSWORD)—— 当作已在会话内继续。")
        # 登录后可能跳到非 advanced.html 的页面,确保回到高级设置页。
        if "advanced.html" not in page.url:
            page = br.goto(url or FACTS["url"])

        try:
            _enter_wan_iframe(page)
        except Exception as exc:
            result["message"] = "进入 wan.html iframe 失败:%s" % exc
            result["screenshot"] = screenshot(page, cfg, FACTS, mode)
            return result

        target = FACTS["modes"][mode]
        # iframe 可能在切换后重新加载,每次操作前重新定位,避免旧句柄超时。
        iframe = page.frame_locator(FACTS["iframe_selector"])
        try:
            # radio 被 CSS 遮住,Playwright 默认的可操作性检查会超时:
            # force=True 直接点真实 input。
            iframe.locator(target).click(force=True)
            time.sleep(1)
        except Exception as exc:
            result["message"] = "点击 %s radio 失败:%s" % (mode, exc)
            result["screenshot"] = screenshot(page, cfg, FACTS, mode)
            return result

        # 只信真 radio 的 is_checked():点了不等于选上了。
        iframe = page.frame_locator(FACTS["iframe_selector"])
        checked = iframe.locator(target).is_checked()
        result["success"] = bool(checked)
        result["read_back"] = mode if checked else ""
        if not checked:
            result["message"] = "回读失败:%s 的 radio 未被选中" % mode
            result["screenshot"] = screenshot(page, cfg, FACTS, mode)
            return result

        if apply:
            iframe = page.frame_locator(FACTS["iframe_selector"])
            iframe.locator(FACTS["apply"]).click(force=True)
            result["applied"] = True
            # 异步提交 + 轮询:等满再关浏览器,否则保存被打断。
            time.sleep(FACTS.get("apply_settle_ms", 500) / 1000.0)

        if verify_hook:
            try:
                result["verify"] = verify_hook(page, result)
            except Exception as exc:
                result["warnings"].append("verify_hook: %s" % exc)
        result["screenshot"] = screenshot(page, cfg, FACTS, mode)
    return result


if __name__ == "__main__":
    sys.exit(run_cli(FACTS, runner=run))
