"""BUFFALO WSR-6000AX8(url=http://192.168.11.1,管理密码见 router.yaml)

WAN 拨号切换脚本。和别的型号只差**一步**:设置页必须以 advanced.html 里的
iframe 形式打开(见下面 run())。其余全走共享动词库。

IPv4 拨号方式全部以 radio 列在 wan.html 同一页,包含日本的 IPoE 各档
(transix / v6プラス / OCN バーチャルコネクト / v6 コネクト)—— 这台机就是为
那组对比才上台架的。
PPPoE 账号密码在独立页 pppoe_reg.html:本脚本只切模式,账密要预先在 Web UI
里配好(见下面 fields_page 的注释)。

事实来源:2026-07-31 真机取证(probe_router.py --dump/--count),六档模式
的 --apply 均已在真机验过(artifacts/progress_BUFFALO_WSR6000AX8.md)。
2026-08-06 重构成动词组合(登录和导航换了实现)后**已在真机复验通过**:
六档逐个回读正确,并下发保存过。

用法(默认只切换不保存;确认回读无误后加 --apply 才真正下发):
    python models/BUFFALO_WSR6000AX8.py dynamic
    python models/BUFFALO_WSR6000AX8.py v6plus --apply
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from models._driver import run_cli, session

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


def run(facts=None, mode="dynamic", **kw):
    """这台机的操作配方。和规矩机型只差一步:**设置页要以 iframe 打开**,
    因为直接打开它保存下去的是旧值(看起来却像成功了)。

    radio 和保存键被 CSS 遮住,所以两处都 force 点。
    """
    with session(facts or FACTS, mode, **kw) as s:
        if not s.login():
            return s.fail("登录失败:仍停在登录页,检查管理密码")
        if not s.goto_iframe():          # 进 advanced.html,再把 iframe 开到 wan.html
            return s.fail("设置页没在 iframe 里就绪")
        s.set_mode(force=True)
        s.fill_params()                  # 账密在 pppoe_reg.html,只会 warn
        return s.apply_and_verify(force=True)


if __name__ == "__main__":
    sys.exit(run_cli(FACTS, runner=run))
