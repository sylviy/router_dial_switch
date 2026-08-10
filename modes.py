"""拨号方式的公共知识:每种模式要哪些参数,以及怎么从 router.yaml 里取。

只有两样东西,但 start.py / models/_driver.py / matrix/run.py 三个入口都要用,
所以放在根目录单独一个文件,而不是塞进其中任何一个。
"""
from __future__ import annotations

from typing import Dict, List

# 切到某个模式必须提供的参数。没有的模式就是空表 —— 比如 dynamic 只要选中
# 就行,static 的 IP/掩码/网关各家差异太大,还没建模(整轮里请避开 static)。
MODE_REQUIRED_FIELDS: Dict[str, List[str]] = {
    "dynamic": [],
    "static": [],
    "pppoe": ["pppoe_user", "pppoe_pass"],
    "l2tp": ["vpn_server", "vpn_user", "vpn_pass"],
    "pptp": ["vpn_server", "vpn_user", "vpn_pass"],
    # v6 的模式名精确到 flavor(dhcpv6 / pppoev6),不用笼统的 "ipv6"。
    "dhcpv6": [],
    "pppoev6": ["pppoe_user", "pppoe_pass"],
}

# 复合模式名 `<家族>_<第二连接>_<对端>` —— tools/routerctrl_bridge.py 认的那套
# (历史 Excel 按这些名字对行,一个字符都不能改)。要填的参数和家族一样:
# `internet`/`public` 后缀只决定 Chariot 打哪个远端,对拨号没有影响。
#
# **这几行是承重的。** 少一个键会静默出事两次:merge_params 只保留 needed 里的
# 字段,所以 router.yaml 里那个模式的账密会被整块丢掉,而桥接有自己的历史默认
# 账号 —— 于是拿默认账号拨上去、报告照样绿;matrix/run.py 开跑前那道"账密不全
# 就别碰路由器"的检查查的也是这张表,漏了就等于没检查。
for _family, _fields in (("pppoe", ["pppoe_user", "pppoe_pass"]),
                         ("pptp", ["vpn_server", "vpn_user", "vpn_pass"]),
                         ("l2tp", ["vpn_server", "vpn_user", "vpn_pass"])):
    for _second in ("dynamic", "static"):
        for _peer in ("internet", "public"):
            MODE_REQUIRED_FIELDS.setdefault(
                "%s_%s_%s" % (_family, _second, _peer), list(_fields))
del _family, _fields, _second, _peer


def merge_params(mode: str, saved: dict, explicit: dict) -> dict:
    """本次运行要用的参数。router.yaml 里的凭据**按模式挑**(只取该模式需要
    的字段,所以 PPPoE 账密绝不会漏进 dynamic 的运行),而命令行显式给的
    --param 是用户意图,永远直通。

    router.yaml 的 params: 支持两层,按模式的块优先 ——

        params:
          pppoe_user: adsl            # 扁平写法:所有模式共用
          pppoe_pass: adsl
          l2tp:                       # 按模式写法:只对这个模式生效
            vpn_server: 192.168.202.254
            vpn_user: l2tp_account
            vpn_pass: l2tp_secret
          pptp:
            vpn_server: 192.168.202.254
            vpn_user: pptp_account    # 和 L2TP 是不同的账号
            vpn_pass: pptp_secret

    L2TP 和 PPTP 共用 vpn_user/vpn_pass 这套字段名(界面上就是同一个概念),
    但台架给它们发的是两套账号,所以必须能分开存 —— 只有扁平一层的话,
    后填的那套会把先填的覆盖掉。
    """
    out: Dict[str, str] = {}
    needed = MODE_REQUIRED_FIELDS.get(mode, [])
    saved = saved or {}
    per_mode = saved.get(mode)
    if not isinstance(per_mode, dict):
        # 复合模式名(pptp_dynamic_internet)回落到家族块(pptp:)—— 否则
        # PPTP/L2TP 那两套不同的账号又分不开了,而分开存正是这个块的用途。
        per_mode = saved.get(str(mode).split("_")[0])
    per_mode = per_mode if isinstance(per_mode, dict) else {}
    for src in (saved, per_mode):          # 按模式的块优先级更高
        for k, v in src.items():
            if k in needed and v is not None:
                out[k] = str(v)
    out.update(explicit)
    return out
