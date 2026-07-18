"""Tenda(测试台那台;固件 V16.03.68.15 / 硬件 V3.0)—— WAN 拨号方式切换脚本。

用法(默认只切换不保存;确认回读无误后加 --apply 才真正下发):
    python models/Tenda_AX3000.py dynamic
    python models/Tenda_AX3000.py pppoe --param pppoe_user=x --param pppoe_pass=y
    python models/Tenda_AX3000.py ipv6 --apply          # IPv6 页,选 DHCPv6
    python models/Tenda_AX3000.py pppoev6 --apply       # IPv6 页,选 PPPoEv6

测试轮次(2026-07-18 与台架约定):复位后默认即 dynamic,先确认 → pppoe
→ IPv6 页遍历 DHCPv6 / PPPoEv6(带 --apply 保存)。
管理密码/宽带账密可先 `python cli.py setup` 写进 router.yaml,之后不用带参数。
注意:这台机同一时间只允许一个 Web 会话 —— 跑脚本前先退出浏览器里登录着的页签。

事实来源:2026-07-18 真机直连逐项核验(Claude in Chrome,192.168.1.1;
选择器命中数均已在页内验证 ==1)。此前的 [待真机复核] 已全部清除;唯一
未实测的是"真的点下保存"(Connect/Save 的按钮本身已确认,点击留给
--apply 验收跑)。
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from models._driver import run_cli

FACTS = {
    "brand": "Tenda",
    "model": "AX3000",
    # 出厂默认是 192.168.0.1;台架上为避免与在线路由器网段冲突,LAN IP 已改成
    # 192.168.1.1(2026-07-18)。复位路由器会回到 192.168.0.1 —— 记得重新改回,
    # 或临时用 --url http://192.168.0.1 跑。
    "url": "http://192.168.1.1",

    # 登录页 login.html:裸密码框(无 id/name)+ class 锚定的登录按钮
    # (文字 "Login";class 不随界面语言变,命中数==1)。
    "login": {"password": "input[type=password]",
              "button": "button.login-form__submit"},

    # 主 WAN 页:顶部导航 "Internet Settings" -> #/wan。
    "wan_path": ["Internet Settings"],

    # 拨号控件:role-less 的 Vue <div class="v-select">,页面上同类控件 5 个
    # (ISP Type/MTU/MAC Clone/DNS),必须 label 锚定(命中数==1)。
    # value:值文本节点自带稳定锚点 data-name="wanType"(主页和 IPv6 页同名,
    # 各自页内唯一),回读用它,不沾下拉小图标的杂质。
    "dial": {"kind": "dropdown",
             "selector": 'div.v-form-item:has-text("Internet Connection Type")'
                         ' div.v-select',
             "value": "[data-name='wanType']"},

    # v4 下拉选项逐字实录:PPPoE / Dynamic IP / Static IP —— 没有 L2TP/PPTP。
    # static 不在测试轮次里,但措辞已实测,留着备用。
    "modes": {"dynamic": "Dynamic IP", "pppoe": "PPPoE", "static": "Static IP"},

    # 账密输入框:data-name 直接标在 <input> 上(页内唯一;界面 label 是
    # "PPPoE Username" / "PPPoE Password")。
    "fields": {
        "pppoe_user": "input[data-name='wanPPPoEUser']",
        "pppoe_pass": "input[data-name='wanPPPoEPwd']",
    },

    # 保存键(2026-07-18 真机 DOM 实录):
    #   <button data-name="submit"><span class="v-button__item">Connect</span></button>
    # 文字在里层 <span> 上,所以 button:text-is("Connect") 命中 0(真机实测)——
    # 必须用 属性 + 内层精确文字 双锚定。就算连接态的 Disconnect 也带
    # data-name="submit",内层文字不同也绝不会误触。
    "apply": 'button[data-name=\'submit\']:has(span:text-is("Connect"))',

    # IPv6:独立页 More -> #/advance/ipv6,WAN 区被 "IPv6" 使能开关门控。
    # 开关状态读内芯 [data-name='ipv6En'](开启时带 v-switch__icon--active,
    # 驱动能读出"已开"而绝不多点;找不到拨号控件时点它即可展开)。
    # v6 flavor 逐字实录:DHCPv6 / PPPoEv6 / Static IPv6 Address。
    # LAN 区有一个同名 "DHCPv6" 的 radio 诱饵 —— 驱动按 option 容器匹配,
    # 不会点到它。两个被测 flavor 各占一个可运行模式:
    "mode_overrides": {
        "ipv6": {
            "wan_path": ["More", "IPv6"],
            "enable_toggle": "[data-name='ipv6En']",
            "dial": {"kind": "dropdown",
                     "selector": 'div.v-form-item:'
                                 'has-text("Internet Connection Type")'
                                 ' div.v-select',
                     "value": "[data-name='wanType']"},
            "modes": {"ipv6": "DHCPv6"},
            # IPv6 页的保存键是 "Save"(同样是文字在里层 span 的嵌套结构)。
            "apply": 'button[data-name=\'submit\']:has(span:text-is("Save"))',
        },
        "pppoev6": {
            "wan_path": ["More", "IPv6"],
            "enable_toggle": "[data-name='ipv6En']",
            "dial": {"kind": "dropdown",
                     "selector": 'div.v-form-item:'
                                 'has-text("Internet Connection Type")'
                                 ' div.v-select',
                     "value": "[data-name='wanType']"},
            "modes": {"pppoev6": "PPPoEv6"},
            # 与主页同一对 data-name(本页内唯一;label 同为 PPPoE Username/Password)
            "fields": {
                "pppoe_user": "input[data-name='wanPPPoEUser']",
                "pppoe_pass": "input[data-name='wanPPPoEPwd']",
            },
            "apply": 'button[data-name=\'submit\']:has(span:text-is("Save"))',
        },
    },
}

if __name__ == "__main__":
    sys.exit(run_cli(FACTS))
