"""Tenda(测试台那台,192.168.0.1,Vue UI)—— WAN 拨号方式切换脚本。

用法(默认只切换不保存;确认回读无误后加 --apply 才真正下发):
    python models/Tenda_AX3000.py dynamic
    python models/Tenda_AX3000.py pppoe --param pppoe_user=x --param pppoe_pass=y
    python models/Tenda_AX3000.py ipv6 --apply

管理密码/宽带账密可先 `python cli.py setup` 写进 router.yaml,之后不用带参数。
实际型号若不是 AX3000,把文件名和下面的 model 改掉即可。

事实来源:2026-07-15 真机验证(CLAUDE.md「Validated」)+ profiles/tenda_ipv6.yaml。
标注 [待真机复核] 的行按真机截图/同源 UI 结构建模,还没在物理设备上二次确认 ——
运行失败先怀疑这些行:跑 `python cli.py diagnose` 取证,照产物修正选择器。
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from models._driver import run_cli

FACTS = {
    "brand": "Tenda",
    "model": "AX3000",
    "url": "http://192.168.0.1",

    # 登录:裸密码框(无 id/name,真机确认)。按钮措辞 [待真机复核] ——
    # 若真机不叫 "Log In",驱动会自动退回在密码框按回车。
    # 注意:Tenda 会话超时很短,且同一时间只允许一个已登录页签。
    "login": {"password": "input[type=password]",
              "button": 'button:text-is("Log In")'},

    # 主 WAN 页:顶部导航 "Internet Settings"(真机确认)。
    "wan_path": ["Internet Settings"],

    # 拨号控件:role-less 的 Vue <div class="v-select">,纯 CSS 不唯一
    # (ISP Type/MTU/DNS 同类同名),必须 label 锚定 —— 真机验证过的选择器。
    "dial": {"kind": "dropdown",
             "selector": 'div.v-form-item:has-text("Internet Connection Type")'
                         ' div.v-select'},

    # 各模式在界面上的原文(真机下拉选项)。
    "modes": {"dynamic": "Dynamic IP", "static": "Static IP",
              "pppoe": "PPPoE", "l2tp": "L2TP", "pptp": "PPTP"},

    # 参数输入框:label 锚定 + :visible(PPPoE 与 VPN 的 Username/Password
    # 同名,但同一时刻只渲染一组)。[待真机复核 —— 真机跑通时走的是启发式]
    "fields": {
        "pppoe_user": 'div.v-form-item:has-text("Username") input:visible',
        "pppoe_pass": 'div.v-form-item:has-text("Password") input:visible',
        "vpn_user":   'div.v-form-item:has-text("Username") input:visible',
        "vpn_pass":   'div.v-form-item:has-text("Password") input:visible',
        "vpn_server": 'div.v-form-item:has-text("VPN Server") input:visible',
    },

    # 保存键叫 "Connect"(不是 Save/Apply),旁边有 "Disconnect" 诱饵:
    # 用 :text-is() 精确匹配,子串永远碰不到 Disconnect。措辞来自真机截图;
    # 实际点击 [待真机复核]。
    "apply": 'button:text-is("Connect")',

    # IPv6 不在主列表里:独立页 More → IPv6,整个 WAN 区被使能开关门控
    # (开关是 role-less div,状态是 class 修饰符;驱动只在看不到拨号控件时
    # 才碰它,绝不会把已开启的页面点关)。导航真机确认,其余按截图建模。
    "mode_overrides": {
        "ipv6": {
            "wan_path": ["More", "IPv6"],
            "enable_toggle": "div.v-switch",
            "dial": {"kind": "dropdown",
                     "selector": 'div.v-form-item:'
                                 'has-text("Internet Connection Type")'
                                 ' div.v-select'},
            # 该页提供的是 v6 flavor(PPPoEv6/DHCPv6/...),默认选 DHCPv6;
            # 要 PPPoEv6 就改这行,并带 --param pppoe_user=... pppoe_pass=...
            "modes": {"ipv6": "DHCPv6"},
            "fields": {
                "pppoe_user": 'div.v-form-item:has-text("PPPoE Username")'
                              ' input:visible',
                "pppoe_pass": 'div.v-form-item:has-text("PPPoE Password")'
                              ' input:visible',
            },
            # IPv6 页的保存键是 "Save",不是主页的 "Connect"。
            "apply": 'button:text-is("Save")',
        },
    },
}

if __name__ == "__main__":
    sys.exit(run_cli(FACTS))
