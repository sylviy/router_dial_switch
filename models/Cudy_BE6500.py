"""Cudy BE6500 —— WAN 拨号方式切换脚本。

UI 形态:LuCI / CBI(OpenWrt)。原生 <select>,id 含点号,保存键需用表单收窄,
PPPoE/L2TP/PPTP 的 username/password 共用同一对输入框(仅 server 不同)。

用法(默认只切换不保存;确认回读无误后加 --apply 才真正下发):
    python models/Cudy_BE6500.py dynamic
    python models/Cudy_BE6500.py pppoe --param pppoe_user=x --param pppoe_pass=y
    python models/Cudy_BE6500.py l2tp --param vpn_server=1.2.3.4 \
        --param vpn_user=u --param vpn_pass=p
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from models._driver import default_run, run_cli

FACTS = {
    "brand": "Cudy",
    "model": "BE6500",
    "url": "http://192.168.10.1",

    # 登录页:LuCI 默认只需密码,按回车即可提交。
    "login": {"password": "input[type=password]"},

    # 导航:登录后默认不在 WAN 设置页,需点 General Settings。
    "wan_path": ["General Settings"],

    # 拨号控件:原生 <select>,id 含点号必须用 [id='...']。
    "dial": {"kind": "select", "selector": "[id='cbid.network.wan.proto']"},

    # 下拉选项逐字实录。
    "modes": {"dynamic": "DHCP", "pppoe": "PPPoE", "l2tp": "L2TP", "pptp": "PPTP"},

    # 账密框:选完模式后挂载,PPPoE/L2TP/PPTP 共用 username/password。
    "fields": {
        "pppoe_user": "form:has([id='cbid.network.wan.proto']) [id='cbid.network.wan.username']",
        "pppoe_pass": "form:has([id='cbid.network.wan.proto']) [id='cbid.network.wan.password']",
        "vpn_server": "form:has([id='cbid.network.wan.proto']) [id='cbid.network.wan.server']",
        "vpn_user":   "form:has([id='cbid.network.wan.proto']) [id='cbid.network.wan.username']",
        "vpn_pass":   "form:has([id='cbid.network.wan.proto']) [id='cbid.network.wan.password']",
    },

    # 保存键:同一页多个 cbi.apply,用拨号控件所在表单收窄。
    "apply": "form:has([id='cbid.network.wan.proto']) button[name='cbi.apply']",
}


def run(facts=None, mode="dynamic", **kw):
    """这台机的操作配方:标准流程(登录 → 走菜单 → 选模式 → 回读 →
    填账密 → 保存)。逐步说明见 models/_driver.default_run。"""
    return default_run(facts or FACTS, mode, **kw)


if __name__ == "__main__":
    sys.exit(run_cli(FACTS, runner=run))
