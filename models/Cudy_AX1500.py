"""Cudy AX1500(测试台那台,192.168.10.1;固件 1.0.1-20240321,SSID Cudy-554C)
—— WAN 拨号方式切换脚本。

**注意台架上有两台 Cudy,UI 完全不同**:这台是 Realtek-SDK 的老式 **frameset**
固件;另一台 AX3000 是 **LuCI/OpenWrt**(见 models/Cudy_AX3000.py)。两份脚本
并存,别把选择器互相搬。

用法(默认只切换不保存;确认回读无误后加 --apply 才真正下发):
    python models/Cudy_AX1500.py dynamic
    python models/Cudy_AX1500.py pppoe --param pppoe_user=x --param pppoe_pass=y
    python models/Cudy_AX1500.py l2tp --param vpn_server=1.2.3.4 \
        --param vpn_user=u --param vpn_pass=p

事实来源:2026-07-18 真机取证(只读探针两轮,现在的等价工具是
`python tools/probe_router.py`;
所有选择器命中数已用运行时引擎验证)。
UI 形态:老式 **frameset** —— 登录在主文档,菜单和 WAN 表单在各自子 frame 里
(_driver 全 frame 查找),控件是带 id/name 的原生 HTML,非常好伺候。

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
v6,只能先升级/更换固件(升级后重跑 `python tools/probe_router.py` 复核),届时照
Tenda_AX3000.py 的 mode_overrides 补一个 ipv6 模式即可。
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from models._driver import default_run, run_cli

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


def run(facts=None, mode="dynamic", **kw):
    """这台机的操作配方:标准流程(登录 → 走菜单 → 选模式 → 回读 →
    填账密 → 保存)。逐步说明见 models/_driver.default_run。"""
    return default_run(facts or FACTS, mode, **kw)


if __name__ == "__main__":
    sys.exit(run_cli(FACTS, runner=run))
