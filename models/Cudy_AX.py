"""Cudy(测试台那台,192.168.10.1;固件 1.0.1-20240321,SSID Cudy-554C,
具体型号名待看壳体标签后改文件名/model)—— WAN 拨号方式切换脚本。

用法(默认只切换不保存;确认回读无误后加 --apply 才真正下发):
    python models/Cudy_AX.py dynamic
    python models/Cudy_AX.py pppoe --param pppoe_user=x --param pppoe_pass=y
    python models/Cudy_AX.py l2tp --param vpn_server=1.2.3.4 \
        --param vpn_user=u --param vpn_pass=p

事实来源:2026-07-18 真机取证(cli.py diagnose + 两轮 Playwright 只读探针,
所有选择器命中数已用运行时引擎验证)。
UI 形态:老式 **frameset** —— 登录在主文档,菜单和 WAN 表单在各自子 frame 里
(_driver 全 frame 查找),控件是带 id/name 的原生 HTML,非常好伺候。
本固件 **没有 IPv6 设置页**(菜单里无入口);v6 需求等固件/型号确认后再说。
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from models._driver import run_cli

FACTS = {
    "brand": "Cudy",
    "model": "AX",
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

if __name__ == "__main__":
    sys.exit(run_cli(FACTS))
