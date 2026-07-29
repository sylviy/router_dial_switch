"""Mercusys BE3600(Wi-Fi 7)—— WAN 拨号方式切换脚本。

用法(默认只切换不保存;确认回读无误后加 --apply 才真正下发):
    python models/Mercusys_BE3600.py pppoe --param pppoe_user=x --param pppoe_pass=y
    python models/Mercusys_BE3600.py l2tp --param vpn_server=1.2.3.4 \
        --param vpn_user=u --param vpn_pass=p

事实来源:2026-07-11 真机验证(详见 CLAUDE.md「Validated」)。标注 [待真机复核]
的行当时由启发式自动搞定、没记下精确选择器 —— 失败时跑
`python tools/probe_router.py` 取证后修正。
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from models._driver import run_cli

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
    # `python tools/probe_router.py` 取证后,照 Tenda_AX3000.py 的 mode_overrides 补上。
}

if __name__ == "__main__":
    sys.exit(run_cli(FACTS))
