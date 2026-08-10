# -*- coding: utf-8 -*-
"""RouterCtrl 桥接 —— **这个文件是 Python 2.7**,整个仓库其余部分是 Python 3。

为什么存在:`RouterCtrl` 是公司内部库,只装在 PTT 台架 PATH 上那个 Python 2 里,
py3 侧 import 不了。所以这里划一条语言边界:py3 用 subprocess 调它,
**只解析 stdout 那一行 JSON**。stderr 随便打(RouterCtrl 自己很吵)。

    python tools/routerctrl_bridge.py <mode> --ip 192.168.0.1 --user admin
        --pass admin123 [--param k=v ...] [--settle 20] [--debug]

刻意的取舍:
  * 不 import 仓库里任何模块(也因此**不需要** `sys.path.insert(0, ROOT)` ——
    别照别的入口脚本给它补一个,这里没有东西要 import);
  * 只切档,不选对端 IP。`internet` / `public` 后缀对下发**完全没有影响**
    (见 _dial 里的注释),它只决定 Chariot 打哪个远端,那是
    `perf_configs/<型号>.yaml` 的 `wan_up.hosts` / `chariot.e2_ip` 管的事;
  * **成败不看返回值** —— 所有下发方法都返回 None。只认 get_wan_info() 的回读。

────────────────────────────────────────────────────────────────────────────
人工验证步骤(在台架上按顺序跑;`python` 就是 PATH 上那个 Python 2)
────────────────────────────────────────────────────────────────────────────

0) 先确认 stdout 是干净的 —— py3 侧的全部依赖就是这一条:

     python tools/routerctrl_bridge.py dynamic --ip 192.168.0.1 --user admin \
         --pass admin123 2>NUL | python -c "import json,sys;d=json.load(sys.stdin);print d['read_back']"

   预期:只打印 `Dynamic IP`,不报 JSON 解析错。**这一步失败后面都不用看** ——
   说明有东西(RouterCtrl 的 print 或我们自己的日志)漏进了 stdout。

1) 最简一档:

     python tools/routerctrl_bridge.py dynamic --ip 192.168.0.1 --user admin --pass admin123

   预期:`"success": true`,`"read_back": "Dynamic IP"`,`wan_ip` 是台架网段的地址。
   `warnings` 里会有一条 `status=poor_connected` —— **那是正常的**(见下面第 5 条)。
   ⚠ 老脚本给 dynamic 留的是 30+15=45 秒,这里默认只有 20 秒。**如果 read_back
   是空的或还是上一档的值,先加 `--settle 45` 再重试**,不要急着怀疑映射表。

2) PPPoE(会拿到隧道地址,掩码是 255.255.255.255,那是对的):

     python tools/routerctrl_bridge.py pppoe --ip 192.168.0.1 --user admin --pass admin123

   预期:`"read_back": "PPPoE"`,`wan_ip` 变成 PPPoE 段的地址(不再是台架网段)。

3) 静态,顺便验 --param 真的透进去了(故意改个网关,看它是否被采纳):

     python tools/routerctrl_bridge.py static --ip 192.168.0.1 --user admin --pass admin123 \
         --param static_gateway=192.168.202.253

   预期:`"read_back": "Static IP"`,`filled` 里列出这一档实际下发的四个键。

4) 复合档各挑一个(这四条覆盖了三种 second_connection 和 is_using_static_ip 两支):

     python tools/routerctrl_bridge.py pppoe_dynamic_public  --ip … --user admin --pass admin123
     python tools/routerctrl_bridge.py pppoe_static_public   --ip … --user admin --pass admin123
     python tools/routerctrl_bridge.py pptp_dynamic_internet --ip … --user admin --pass admin123
     python tools/routerctrl_bridge.py l2tp_static_public    --ip … --user admin --pass admin123

   预期 read_back 依次是 `PPPoE` / `PPPoE` / `PPTP` / `L2TP`。
   ⚠ `pppoe_dynamic_public` 在老脚本里**从来没真正下发过**(见文件末尾的
   「老脚本的一处拼写错误」),这是它第一次真的被执行 —— 请重点看它。

5) 失败长什么样(**必须验一次**,否则不知道失败是不是真的会报出来):

     python tools/routerctrl_bridge.py pppoe --ip 192.168.0.1 --user admin --pass 错密码

   预期:`"success": false`,`message` 里带**异常类型名 + 完整信息**,
   `applied` 是 false。绝不该看到 success true。

6) 想看 RouterCtrl 自己的日志时加 `--debug`(日志走 stderr,不污染 stdout):

     python tools/routerctrl_bridge.py dynamic --ip … --user admin --pass admin123 --debug

7) 收尾:把机器切回 dynamic,别让台架停在隧道档上。

────────────────────────────────────────────────────────────────────────────
"""

import argparse
import json
import logging
import sys
import time

import RouterCtrl


# 模式 -> get_wan_info()['wan_type'] 的期望值。五个值全部真机实测确认过,
# 大小写和空格照抄,**不要"顺手规范化"**(回读判定是精确相等)。
#
# ⚠ 回读只认 get_wan_info()['wan_type'] 这一个来源。RouterCtrl 还有个看起来
# 更贴切的 get_dial_type() —— **别用它**:实测它返回的是 IPv6 的拨号类型
# (例 'Pass Through'),和 IPv4 的 WAN 类型没有关系。拿它判定会每一档都不匹配。
WAN_TYPE_BY_MODE = {
    'dynamic': 'Dynamic IP',
    'static':  'Static IP',
    'pppoe':   'PPPoE',
    'pptp':    'PPTP',
    'l2tp':    'L2TP',
}

# 全部支持的模式名。**一个字符都不要改** —— 历史 Excel 报告按这些名字对行
# (老脚本 CONN_TYPE_INDEX 里 static=1, dynamic=4, pppoe=7, … 每档占 3 行)。
MODES = [
    'dynamic',
    'static',
    'pppoe',
    'pppoe_dynamic_internet',
    'pppoe_dynamic_public',
    'pppoe_static_internet',
    'pppoe_static_public',
    'pptp_dynamic_internet',
    'pptp_dynamic_public',
    'pptp_static_internet',
    'pptp_static_public',
    'l2tp_dynamic_internet',
    'l2tp_dynamic_public',
    'l2tp_static_internet',
    'l2tp_static_public',
]

# --param 认识的键 -> (默认值, 说明)。默认值**全部是 dial_perf.py 里的老硬编码值**,
# 所以不给任何 --param 时行为和老脚本一致(唯一的例外是 settle,见 --settle 的帮助)。
# 键名跟仓库 py3 侧 modes.py 的概念名对齐(pppoe_user / vpn_server / …),
# 这样将来 py3 调它时不需要再翻译一层。
PARAM_SPEC = [
    ('pppoe_user',     'pppoe',           'PPPoE 账号(老脚本硬编码 pppoe)'),
    ('pppoe_pass',     'pppoe',           'PPPoE 密码(老脚本硬编码 pppoe)'),
    ('vpn_server',     '192.168.202.254', 'PPTP/L2TP 服务器地址(老脚本 192.168.202.254)'),
    ('vpn_user',       None,              'PPTP/L2TP 账号(默认随模式:pptp_* -> pptp,l2tp_* -> l2tp)'),
    ('vpn_pass',       None,              'PPTP/L2TP 密码(默认随模式,同上)'),
    ('static_ip',      '192.168.202.1',   'static 档的 WAN IP(老脚本 192.168.202.1)'),
    ('static_mask',    '255.255.255.0',   'static 档的掩码(老脚本 255.255.255.0)'),
    ('static_gateway', '192.168.202.253', 'static 档的网关(老脚本 192.168.202.253)'),
    ('static_dns1',    '192.168.202.254', 'static 档的 DNS1(老脚本 192.168.202.254)'),
    ('second_ip',      '192.168.202.1',   'pppoe_static_* 的第二连接 IP(老脚本 192.168.202.1)'),
    ('second_mask',    '255.255.255.0',   'pppoe_static_* 的第二连接掩码(老脚本 255.255.255.0)'),
    ('eth_ip',         '192.168.202.1',   'pptp/l2tp_static_* 的以太网 IP(老脚本 192.168.202.1)'),
    ('eth_mask',       '255.255.255.0',   'pptp/l2tp_static_* 的以太网掩码(老脚本 255.255.255.0)'),
    ('eth_gateway',    '192.168.202.99',  'pptp/l2tp_static_* 的以太网网关(老脚本 192.168.202.99'
                                          ',注意和 static_gateway 的 .253 不是一个值)'),
    ('eth_dns1',       '192.168.202.254', 'pptp/l2tp_static_* 的以太网 DNS1(老脚本 192.168.202.254)'),
]
PARAM_KEYS = [k for (k, _d, _h) in PARAM_SPEC]

# 每档实际会用到哪些 --param 键 —— 进输出的 filled,让人一眼看到这次下发了什么。
PARAMS_USED = {
    'dynamic': [],
    'static': ['static_ip', 'static_mask', 'static_gateway', 'static_dns1'],
    'pppoe': ['pppoe_user', 'pppoe_pass'],
    'pppoe_dynamic': ['pppoe_user', 'pppoe_pass'],
    'pppoe_static': ['pppoe_user', 'pppoe_pass', 'second_ip', 'second_mask'],
    'vpn_dynamic': ['vpn_user', 'vpn_pass', 'vpn_server'],
    'vpn_static': ['vpn_user', 'vpn_pass', 'vpn_server',
                   'eth_ip', 'eth_mask', 'eth_gateway', 'eth_dns1'],
}


def _exc_text(exc):
    """异常的类型名 + 完整信息,原样带出去,不吞。

    py2 里 str(exc) 遇到 unicode 消息会抛 UnicodeEncodeError —— 那会把"报告
    失败"这一步本身弄崩,所以逐级退让到 repr。
    """
    name = type(exc).__name__
    try:
        detail = str(exc)
    except Exception:
        try:
            detail = unicode(exc).encode('utf-8', 'replace')   # noqa: F821 (py2)
        except Exception:
            detail = repr(exc)
    return '%s: %s' % (name, detail)


def _base_mode(mode):
    """复合模式取前缀:pppoe_dynamic_internet -> pppoe;dynamic -> dynamic。"""
    return mode.split('_')[0]


def _defaults_for(mode):
    """这一档的参数默认值。vpn_user/vpn_pass 的默认值随模式家族走 ——
    老脚本给 PPTP 和 L2TP 发的是两套账号('pptp'/'pptp' 与 'l2tp'/'l2tp')。"""
    out = {}
    for key, default, _help in PARAM_SPEC:
        out[key] = default
    base = _base_mode(mode)
    if base in ('pptp', 'l2tp'):
        out['vpn_user'] = base
        out['vpn_pass'] = base
    return out


def _dial(dut, mode, p):
    """按 mode 下发。分支结构照搬 dial_perf.py 第 270-300 行,模式名一字未改。

    **`internet` 和 `public` 两个后缀对下发没有任何影响** —— 同一支 elif 同时
    收下它们,老脚本也是这样。区别只在 Chariot 打哪个远端(老脚本的
    `e2_ip = PUBLIC_IP if 'public' in dial_mode else INTERNET_IP`),那是读侧的事,
    桥接不碰。所以这里看起来"两个模式做同一件事"是对的,不是漏写。

    全部方法返回 None,**不能靠返回值判断成败**;成败只由 get_wan_info() 的回读定。
    """
    if mode == 'dynamic':
        dut.set_wan_dynamic_ip()

    elif mode == 'static':
        dut.set_wan_static_ip(ip=p['static_ip'], mask=p['static_mask'],
                              gateway=p['static_gateway'], dns1=p['static_dns1'])

    elif mode == 'pppoe':
        dut.connect_wan_pppoe(username=p['pppoe_user'], password=p['pppoe_pass'],
                              connection_mode=dut.PPP_CONNECT_AUTO,
                              second_connection=dut.SECOND_CONN_DISABLED)

    elif mode in ('pppoe_dynamic_internet', 'pppoe_dynamic_public'):
        dut.connect_wan_pppoe(username=p['pppoe_user'], password=p['pppoe_pass'],
                              connection_mode=dut.PPP_CONNECT_AUTO,
                              second_connection=dut.SECOND_CONN_DYNAMIC_IP)

    elif mode in ('pppoe_static_internet', 'pppoe_static_public'):
        dut.connect_wan_pppoe(username=p['pppoe_user'], password=p['pppoe_pass'],
                              connection_mode=dut.PPP_CONNECT_AUTO,
                              second_connection=dut.SECOND_CONN_STATIC_IP,
                              second_connection_ip=p['second_ip'],
                              second_connection_mask=p['second_mask'])

    elif mode in ('pptp_dynamic_internet', 'pptp_dynamic_public'):
        dut.connect_wan_pptp(ppp_username=p['vpn_user'], ppp_password=p['vpn_pass'],
                             pptp_host=p['vpn_server'], is_using_static_ip=None,
                             connection_mode=dut.PPP_CONNECT_AUTO)

    elif mode in ('pptp_static_internet', 'pptp_static_public'):
        dut.connect_wan_pptp(ppp_username=p['vpn_user'], ppp_password=p['vpn_pass'],
                             pptp_host=p['vpn_server'], is_using_static_ip=True,
                             eth_ip=p['eth_ip'], eth_mask=p['eth_mask'],
                             eth_gateway=p['eth_gateway'], eth_dns1=p['eth_dns1'],
                             connection_mode=dut.PPP_CONNECT_AUTO)

    elif mode in ('l2tp_dynamic_internet', 'l2tp_dynamic_public'):
        dut.connect_wan_l2tp(ppp_username=p['vpn_user'], ppp_password=p['vpn_pass'],
                             l2tp_host=p['vpn_server'], is_using_static_ip=None,
                             connection_mode=dut.PPP_CONNECT_AUTO)

    elif mode in ('l2tp_static_internet', 'l2tp_static_public'):
        dut.connect_wan_l2tp(ppp_username=p['vpn_user'], ppp_password=p['vpn_pass'],
                             l2tp_host=p['vpn_server'], is_using_static_ip=True,
                             eth_ip=p['eth_ip'], eth_mask=p['eth_mask'],
                             eth_gateway=p['eth_gateway'], eth_dns1=p['eth_dns1'],
                             connection_mode=dut.PPP_CONNECT_AUTO)

    else:
        raise ValueError('没有这个模式的下发分支:%r' % mode)


def _filled_keys(mode):
    base = _base_mode(mode)
    if mode in ('dynamic', 'static', 'pppoe'):
        return list(PARAMS_USED[mode])
    if base == 'pppoe':
        kind = 'pppoe_static' if '_static_' in mode else 'pppoe_dynamic'
        return list(PARAMS_USED[kind])
    kind = 'vpn_static' if '_static_' in mode else 'vpn_dynamic'
    return list(PARAMS_USED[kind])


def _jsonable(obj):
    """get_wan_info() 的返回里混着 str 和 unicode。json 能吃,但万一有别的
    类型(比如 ctypes 的东西)就退成字符串,别让整份 detail 序列化失败。"""
    try:
        json.dumps(obj)
        return obj
    except Exception:
        if isinstance(obj, dict):
            return dict(('%s' % k, _jsonable(v)) for (k, v) in obj.items())
        if isinstance(obj, (list, tuple)):
            return [_jsonable(v) for v in obj]
        return repr(obj)


def main(argv=None):
    epilog = ('所有 --param 的默认值都是 dial_perf.py 里的老硬编码值,'
              '不给 --param 时行为与老脚本一致。可用的 k:\n'
              + '\n'.join(['  %-15s 默认 %-17s %s'
                           % (k, repr(d) if d is not None else '(随模式)', h)
                           for (k, d, h) in PARAM_SPEC]))
    ap = argparse.ArgumentParser(
        description='RouterCtrl 桥接(Python 2):切一档 WAN 拨号方式,'
                    'stdout 输出一行 JSON。',
        epilog=epilog,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('mode', choices=MODES, help='目标拨号方式')
    ap.add_argument('--ip', required=True, help='路由器管理地址,如 192.168.0.1')
    ap.add_argument('--user', default='admin', help='管理用户名(默认 admin)')
    ap.add_argument('--pass', dest='password', required=True, help='管理密码')
    ap.add_argument('--param', action='append', default=[], metavar='k=v',
                    help='下发参数,可重复。见下面的清单')
    ap.add_argument('--settle', type=int, default=20, metavar='N',
                    help='下发后等几秒再回读(默认 20)。注意老脚本给 dynamic 留的是'
                         ' 30+15=45 秒,别的档 15 秒 —— dynamic 回读不到就试 --settle 45')
    ap.add_argument('--brand', default='TPLink', help='只写进输出,不影响行为')
    ap.add_argument('--model', default='', help='只写进输出,不影响行为')
    ap.add_argument('--debug', action='store_true',
                    help='放开 RouterCtrl 的 INFO/DEBUG 日志(走 stderr,不污染 stdout)')
    args = ap.parse_args(argv)

    # RouterCtrl 往根 logger 打大量 INFO/DEBUG。默认压到 WARNING,
    # 否则台架上一屏全是它的日志,真正的失败信息反而被埋掉。
    logging.getLogger().setLevel(logging.DEBUG if args.debug else logging.WARNING)

    params = _defaults_for(args.mode)
    for item in args.param:
        if '=' not in item:
            ap.error('--param 要写成 k=v,收到的是 %r' % item)
        key, value = item.split('=', 1)
        key = key.strip()
        # 键名打错了就当场停下。**不能只警告** —— 默认值恰好就是台架的值,
        # 静默忽略一个打错的键会拿默认值跑完并报 success,那是最难查的一种错。
        if key not in PARAM_KEYS:
            ap.error('不认识的 --param 键 %r。可用:%s'
                     % (key, ', '.join(PARAM_KEYS)))
        params[key] = value

    result = {
        'brand': args.brand,
        'model': args.model,
        'mode': args.mode,
        'success': False,
        'read_back': '',
        'detail': {},
        'applied': False,
        'filled': [],
        'message': '',
        'warnings': [],
    }

    # stdout 的契约:**只有最后那一行 JSON**。RouterCtrl 里万一有 print,
    # 会把 py3 侧的 json.loads 弄崩,所以干活期间把 sys.stdout 顶到 stderr,
    # 最后才换回真的 stdout 写 JSON。
    real_stdout = sys.stdout
    sys.stdout = sys.stderr
    try:
        try:
            dut = RouterCtrl.SohoRouterCtrl(args.ip, args.user, args.password)
        except Exception as exc:
            result['message'] = ('连不上路由器(SohoRouterCtrl 构造失败):%s'
                                 % _exc_text(exc))
            return _emit(real_stdout, result)

        try:
            _dial(dut, args.mode, params)
            result['applied'] = True
            result['filled'] = _filled_keys(args.mode)
        except Exception as exc:
            result['message'] = ('下发 %s 时抛异常:%s'
                                 % (args.mode, _exc_text(exc)))
            return _emit(real_stdout, result)

        time.sleep(args.settle)

        try:
            info = dut.get_wan_info()
        except Exception as exc:
            result['message'] = ('已下发,但 get_wan_info() 抛异常,回读不到:%s'
                                 % _exc_text(exc))
            return _emit(real_stdout, result)

        info = info or {}
        result['detail'] = _jsonable(info)
        wan_type = info.get('wan_type') or ''
        wan_ip = info.get('wan_ip') or ''
        status = info.get('status') or ''
        result['read_back'] = wan_type

        # status 只作参考,**绝不参与判定**:PTT 拓扑的对端是内网服务器,联网
        # 检测的 DNS 请求没人回应,所以 status 常年是 'poor_connected'。实测
        # PPPoE 已经拿到隧道地址时 status 仍然是它 —— 拿它判定会把成功判成失败。
        result['warnings'].append(
            'status=%s(仅供参考。PTT 拓扑下 poor_connected 是正常的,'
            '不代表没拨通)' % (status or '(空)'))

        expect = WAN_TYPE_BY_MODE[_base_mode(args.mode)]
        problems = []
        if wan_type != expect:
            problems.append('wan_type 不对:期望 %r,实际读到 %r'
                            % (expect, wan_type))
        # 只看 wan_ip 有没有拿到。**不校验 wan_mask** —— PPPoE/PPTP/L2TP 这类
        # 点对点链路的掩码就是 255.255.255.255,那是正常的。
        if not wan_ip:
            problems.append('wan_ip 是空的(没拿到地址)')
        elif ('%s' % wan_ip).startswith('0.0.0.0'):
            # 用 '%s' % 而不是 str():wan_ip 是 unicode,str() 碰到非 ASCII 会抛
            # UnicodeEncodeError,那会让"报告失败"这一步自己崩掉。
            problems.append('wan_ip 是 %r(0.0.0.0 开头 = 没拨上)' % wan_ip)

        if problems:
            result['message'] = ('回读没通过:' + ';'.join(problems)
                                 + '。完整回读见 detail')
        else:
            result['success'] = True
        return _emit(real_stdout, result)
    finally:
        sys.stdout = real_stdout


def _emit(stream, result):
    """把结果写成一行 JSON。ensure_ascii=True(默认):get_wan_info() 里混着
    unicode,转成纯 ASCII 的 \\uXXXX 最不容易在 py2 的 stdout 上炸编码,
    py3 侧 json.loads 照样还原。返回进程退出码。"""
    stream.write(json.dumps(result, sort_keys=True) + '\n')
    try:
        stream.flush()
    except Exception:
        pass
    return 0 if result.get('success') else 2


if __name__ == '__main__':
    sys.exit(main())


# ───────────────────────────────────────────────────────────────────────────
# 老脚本的一处拼写错误(移植时发现,值得知道,因为它污染过历史数据)
# ───────────────────────────────────────────────────────────────────────────
# dial_perf.py 第 280 行:
#
#     elif dial_mode == 'pppoe_dynamic_internet' or dial_mode == 'pppoe_dyanamic_public':
#                                                                     ^^^^^^^^^
# 'dyanamic' —— a 和 n 写反了。而第 27 行的 Excel 行号表里是正确的
# 'pppoe_dynamic_public'。后果:**只要 test_conn 里出现过 pppoe_dynamic_public,
# 它就会穿过所有 elif,一次下发都不做**,然后拿上一档遗留的配置去跑吞吐,
# 把数字写进 Excel 第 13 行,标签写着 pppoe_dynamic_public。
#
# 不是崩溃,是一份看起来完全正常、测的却是另一档的报告。老脚本注释掉的那几行
# test_conn 里没有它(第 43-47 行),所以可能一直没触发;但只要有人把它加回
# test_conn,这一格的历史数据就不可信。
#
# 本文件按用户给的清单用正确拼写 'pppoe_dynamic_public',并且上面那套静态检查
# 会保证 MODES 里的每个名字都真的有下发分支 —— 同一类错误不会再悄悄发生。
# 台架验证时请重点看这一档(人工验证步骤第 4 条)。
