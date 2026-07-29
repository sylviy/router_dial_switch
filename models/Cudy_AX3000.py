"""Cudy AX3000(192.168.10.1;LuCI / OpenWrt 固件,git-25.272.36397;
主机名 WR3000)—— WAN 拨号方式切换脚本。

用法(默认只切换不保存;确认回读无误后加 --apply 才真正下发):
    python models/Cudy_AX3000.py dynamic
    python models/Cudy_AX3000.py pppoe --param pppoe_user=x --param pppoe_pass=y
    python models/Cudy_AX3000.py l2tp --param vpn_server=1.2.3.4 \
        --param vpn_user=u --param vpn_pass=p

事实来源:2026-07-29 真机只读取证(登录页 curl + Playwright 控件抄录 + 逐 proto
字段发现 + 选择器命中数引擎验证)。每个选择器都由 Playwright 引擎实测命中数==1。

UI 形态:**LuCI(CBI)**,单文档无 frameset。路由:主页面 → 顶部菜单
"General Settings"(/admin/setup)→ 该页 "WAN Mode" 段默认展开 → Protocol 是个
原生 <select>。PPPoE/L2TP/PPTP 的账密框在选完 proto 后由 LuCI AJAX 挂载,
驱动 _fill_params 会轮询等它们出现。

与旧 models/Cudy_AX.py(老式 frameset 固件,192.168.10.1 旧机)不是同一台/
同一固件 —— 那台是 Realtek-SDK frameset UI,这台是 LuCI。两份脚本并存。

**LuCI CBI 的两个坑(写进 FACTS 的原因):**
  * CBI 的 id 形如 `cbid.network.wan.proto`,**含点号**。CSS 里 `#cbid.network.wan.proto`
    会被解析成"id=cbid + 三个 class",命中 0。所以这里**一律用属性选择器**
    `[id='...']`,不用 `#...`。
  * 保存键 `button[name='cbi.apply']` 在 /admin/setup 上有 4 个(WAN / 2.4G / VPN /
    其它各一个),不唯一。必须锚定到"包含拨号控件的那个 form"才命中 1:
    `form:has([id='cbid.network.wan.proto']) button[name='cbi.apply']`。

**登录**:LuCI 用加盐哈希挑战(_csrf/token/salt 隐藏域 + JS 把可见密码框的值
哈希后填进隐藏的 luci_password 再提交)。纯 curl 发不出去,但 Playwright 填
可见的 #luci_password2 后按回车,onsubmit 的 JS 会完成哈希提交 —— 已实测
login 成功。不给 login.button,驱动走回车。

**IPv6**:本脚本只覆盖用户要求的 dynamic/pppoe/l2tp/pptp。LuCI 的 IPv6 在
/admin/setup 上没作为 proto 选项出现(选项就那 5 个);VPN 段另有 PPTP/L2TP
Server 等,与本脚本无关。
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from models._driver import run_cli

FACTS = {
    "brand": "Cudy",
    "model": "AX3000",
    "url": "http://192.168.10.1",

    # 登录:#luci_password2 是登录页那个可见密码框(隐藏的 luci_password 是
    # type=hidden,不会被 input[type=password] 之外的精确 id 误中)。不给 button
    # —— 驱动填完按回车,LuCI 的 onsubmit JS 哈希后提交。
    "login": {"password": "#luci_password2"},

    # 导航:登录后落在 System Status,点顶部菜单 "General Settings"(唯一可见
    # 链接,文字精确匹配)进 /admin/setup,WAN Mode 段默认展开。
    "wan_path": ["General Settings"],

    # 拨号控件:原生 <select>。id 含点号,必须用属性选择器(见上文)。
    "dial": {"kind": "select", "selector": "[id='cbid.network.wan.proto']"},

    # 下拉选项逐字实录(真机)。dynamic 在这台叫 "DHCP(Dynamic IP)"。
    "modes": {"dynamic": "DHCP(Dynamic IP)", "pppoe": "PPPoE",
              "l2tp": "L2TP", "pptp": "PPTP"},

    # 字段:三种模式共用同一组 DOM id —— PPPoE 的 username/password 与 L2TP/PPTP
    # 的是同一个输入框,server 只在 L2TP/PPTP 出现。驱动按模式填,不会串。
    # 这些输入框在选完 proto 后才由 LuCI AJAX 挂载,_fill_params 会轮询等。
    "fields": {
        "pppoe_user": "[id='cbid.network.wan.username']",
        "pppoe_pass": "[id='cbid.network.wan.password']",
        "vpn_server": "[id='cbid.network.wan.server']",
        "vpn_user":   "[id='cbid.network.wan.username']",
        "vpn_pass":   "[id='cbid.network.wan.password']",
    },

    # 保存键:页面上有 4 个 name=cbi.apply 的 "Save & Apply",必须锚定到包含
    # 拨号控件的 form,否则会点到 2.4G/VPN 等其它段。引擎实测命中 1。
    "apply": "form:has([id='cbid.network.wan.proto']) button[name='cbi.apply']",
}

if __name__ == "__main__":
    sys.exit(run_cli(FACTS))
