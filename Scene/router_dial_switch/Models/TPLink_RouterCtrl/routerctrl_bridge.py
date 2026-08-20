# -*- coding: utf-8 -*-
#
# RouterCtrl 桥接 —— **这个文件是 Python 2.6**,整个仓库其余部分是 Python 3。
#
# 为什么存在:`RouterCtrl` 是公司内部库,只装在 PTT 台架 PATH 上那个 Python 2 里,
# py3 侧 import 不了。所以这里划一条语言边界:py3 用 subprocess 调它,
# **只解析 stdout 那一行 JSON**。stderr 随便打(RouterCtrl 自己很吵)。
#
#     python routerctrl_bridge.py <mode> --ip 192.168.0.1 --user admin
#         --pass admin123 [--param k=v ...] [--settle 20] [--debug]
#
# ─── 为什么全文没有一个非 ASCII 的字符串字面量 ──────────────────────────────
# 中文只出现在 `#` 注释里(docstring 也是字符串字面量,所以连模块 docstring 都
# 不用中文)。两个理由,都在这仓库出过事:
#   * 台架控制台是 GBK。GBK 编不出的字符一 print 就 UnicodeEncodeError,
#     而它偏偏会在"报告失败"这一步炸 —— 最不该崩的时候崩;
#   * py2 里 str 字面量是字节串,和 get_wan_info() 返回的 unicode 一混
#     (`'%s' % u'…'`)就可能 UnicodeDecodeError。
# 注释不进运行期,所以中文留在注释里是安全的。
#
# ─── 为什么没用 argparse(和最初的要求不一样,这里说清)──────────────────────
# **argparse 是 2.7 才进标准库的。** 2026-07-28 台架实测:PATH 上的 Python 是
# ActivePython 2.6.5,`import argparse` 直接 ImportError(见 docs/GOTCHAS.md 的
# Environment 一节,以及 matrix/chariot_perf.py 第 27 行的同一条教训)。
# 用 argparse 的话这个桥接会在台架上**连参数都没解析到就死在 import**,
# 而那看起来像"桥接坏了",其实是解释器少个模块。所以参数是手写解析的 ——
# 和 matrix/chariot_perf.py 一样,那是本仓库对 2.6 的既有答案。
#
# 其余 2.6 约束(全文遵守):不用字典/集合推导式、不用集合字面量、
# 不用 str.format(连 "{0}" 也不用,统一 %)、不用 OrderedDict。
#
# 刻意的取舍:
#   * 不 import 仓库里任何模块(也因此**不需要** `sys.path.insert(0, ROOT)` ——
#     别照别的入口脚本给它补一个,这里没有东西要 import);
#   * 只切档,不选对端 IP。`internet` / `public` 后缀对下发**完全没有影响**
#     (见 _dial 里的注释),它只决定 Chariot 打哪个远端,那是
#     `perf_configs/<型号>.yaml` 的 `wan_up.hosts` / `chariot.e2_ip` 管的事;
#   * **成败不看返回值** —— 所有下发方法都返回 None。只认 get_wan_info() 的回读。
#
# 退出码(py3 侧按这个分流):
#   0 = success 为 true,stdout 有一行 JSON
#   2 = 跑完了但判定失败,stdout 有一行 JSON(message 写了是哪一条不满足)
#   3 = 参数用错了,**stdout 是空的**(没有 JSON 可解析)。
#       --help 也走 stderr,同理:stdout 只在"真的切了一次档"时才有内容。
#
# ────────────────────────────────────────────────────────────────────────────
# 人工验证步骤(在台架上按顺序跑;`python` 就是 PATH 上那个 Python 2.6.5)
# ────────────────────────────────────────────────────────────────────────────
#
# 0) 先确认解释器吃得下这个文件 —— 2.6 上任何语法/import 问题都会在这一步暴露:
#
#      python -c "import compileall,sys; sys.exit(0 if compileall.compile_file('routerctrl_bridge.py') else 1)"
#
#    预期:不打印 SyntaxError。**这一步失败后面都不用看。**
#
# 1) 再确认 stdout 是干净的 —— py3 侧的全部依赖就是这一条:
#
#      python routerctrl_bridge.py dynamic --ip 192.168.0.1 --user admin \
#          --pass admin123 2>NUL | python -c "import json,sys; print json.load(sys.stdin)['read_back']"
#
#    预期:只打印 `Dynamic IP`,不报 JSON 解析错。失败说明有东西
#    (RouterCtrl 的 print,或我们自己的日志)漏进了 stdout。
#
# 2) 最简一档:
#
#      python routerctrl_bridge.py dynamic --ip 192.168.0.1 --user admin --pass admin123
#
#    预期:`"success": true`,`"read_back": "Dynamic IP"`,`wan_ip` 是台架网段的地址。
#    warnings 里会有一条 `status=poor_connected` —— **那是正常的**(见第 5 条)。
#    ⚠ 老脚本给 dynamic 留的是 30+15=45 秒,这里默认只有 20 秒。**如果 read_back
#    是空的或还是上一档的值,先加 `--settle 45` 再重试**,不要急着怀疑映射表。
#
# 3) PPPoE(会拿到隧道地址,掩码是 255.255.255.255,那是对的):
#
#      python routerctrl_bridge.py pppoe --ip 192.168.0.1 --user admin --pass admin123
#
#    预期:`"read_back": "PPPoE"`,`wan_ip` 变成 PPPoE 段的地址(不再是台架网段)。
#
# 4) 静态,顺便验 --param 真的透进去了:
#
#      python routerctrl_bridge.py static --ip 192.168.0.1 --user admin --pass admin123 \
#          --param static_gateway=192.168.202.253
#
#    预期:`"read_back": "Static IP"`,`filled` 里列出这一档实际下发的四个键。
#
# 5) 复合档各挑一个(覆盖三种 second_connection 和 is_using_static_ip 两支):
#
#      python routerctrl_bridge.py pppoe_dynamic_public  --ip … --user admin --pass admin123
#      python routerctrl_bridge.py pppoe_static_public   --ip … --user admin --pass admin123
#      python routerctrl_bridge.py pptp_dynamic_internet --ip … --user admin --pass admin123
#      python routerctrl_bridge.py l2tp_static_public    --ip … --user admin --pass admin123
#
#    预期 read_back 依次是 `PPPoE` / `PPPoE` / `PPTP` / `L2TP`。
#    ⚠ `pppoe_dynamic_public` 在老脚本里**从来没真正下发过**(见文件末尾的
#    「老脚本的一处拼写错误」),这是它第一次真的被执行 —— 请重点看它。
#
# 6) 失败长什么样(**必须验一次**,否则不知道失败是不是真的会报出来):
#
#      python routerctrl_bridge.py pppoe --ip 192.168.0.1 --user admin --pass 错密码
#
#    预期:`"success": false`,退出码 2,message 里带**异常类型名 + 完整信息**,
#    applied 是 false。绝不该看到 success true。
#
# 7) 参数用错时不该产出 JSON(py3 侧靠这个区分"我调错了"和"设备没拨上"):
#
#      python routerctrl_bridge.py pppoe --ip 192.168.0.1 --user admin --pass x --param nosuchkey=1
#
#    预期:退出码 3,**stdout 完全是空的**,stderr 上列出可用的键。
#
# 8) 想看 RouterCtrl 自己的日志时加 `--debug`(日志走 stderr,不污染 stdout)。
#
# 9) 收尾:把机器切回 dynamic,别让台架停在隧道档上。
#
# ────────────────────────────────────────────────────────────────────────────

"""RouterCtrl bridge (Python 2.6). Switch one WAN dial mode, print one JSON
line on stdout. See the comment block above for why every string literal here
is ASCII and why argparse is not used."""

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
# 所以不给任何 --param 时行为和老脚本一致(唯一的例外是 settle,见 usage)。
# 键名跟仓库 py3 侧 modes.py 的概念名对齐(pppoe_user / vpn_server / …),
# 这样将来 py3 调它时不需要再翻译一层。
PARAM_SPEC = [
    ('pppoe_user',     'pppoe',           'PPPoE username (old script hardcoded: pppoe)'),
    ('pppoe_pass',     'pppoe',           'PPPoE password (old script hardcoded: pppoe)'),
    ('vpn_server',     '192.168.202.254', 'PPTP/L2TP server host (old: 192.168.202.254)'),
    ('vpn_user',       None,              'PPTP/L2TP username (default follows mode: pptp_* -> pptp, l2tp_* -> l2tp)'),
    ('vpn_pass',       None,              'PPTP/L2TP password (default follows mode, same as above)'),
    ('static_ip',      '192.168.202.1',   'static mode WAN IP (old: 192.168.202.1)'),
    ('static_mask',    '255.255.255.0',   'static mode netmask (old: 255.255.255.0)'),
    ('static_gateway', '192.168.202.253', 'static mode gateway (old: 192.168.202.253)'),
    ('static_dns1',    '192.168.202.254', 'static mode DNS1 (old: 192.168.202.254)'),
    ('second_ip',      '192.168.202.1',   'pppoe_static_* second-connection IP (old: 192.168.202.1)'),
    ('second_mask',    '255.255.255.0',   'pppoe_static_* second-connection mask (old: 255.255.255.0)'),
    ('eth_ip',         '192.168.202.1',   'pptp/l2tp_static_* ethernet IP (old: 192.168.202.1)'),
    ('eth_mask',       '255.255.255.0',   'pptp/l2tp_static_* ethernet mask (old: 255.255.255.0)'),
    ('eth_gateway',    '192.168.202.99',  'pptp/l2tp_static_* ethernet gateway (old: 192.168.202.99'
                                          ' -- NOTE this is not the same value as static_gateway .253)'),
    ('eth_dns1',       '192.168.202.254', 'pptp/l2tp_static_* ethernet DNS1 (old: 192.168.202.254)'),
]
# 2.6:不能用列表推导以外的推导式,列表推导本身是 2.0 起就有的,可以用。
PARAM_KEYS = [_spec[0] for _spec in PARAM_SPEC]

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

# 认识的开关。带值的写 --k v 或 --k=v 都行。
_VALUE_OPTS = ['--ip', '--user', '--pass', '--settle', '--brand', '--model']
_FLAG_OPTS = ['--debug', '--help', '-h']

EXIT_OK = 0
EXIT_FAIL = 2       # 跑完了,判定不过
EXIT_USAGE = 3      # 参数用错了,stdout 不会有 JSON


def usage():
    """Usage text. Goes to stderr on purpose: stdout carries JSON only, so a
    wrapper that accidentally passes --help gets empty stdout (instantly
    diagnosable) instead of a wall of text that fails json.loads."""
    lines = []
    lines.append('usage: python routerctrl_bridge.py <mode> --ip IP '
                 '--pass PASSWORD [--user admin]')
    lines.append('           [--param k=v ...] [--settle N] [--brand B] '
                 '[--model M] [--debug]')
    lines.append('')
    lines.append('Switch one WAN dial mode via RouterCtrl and print one JSON '
                 'line on stdout.')
    lines.append('Exit codes: 0 = success, 2 = ran but read-back failed '
                 '(JSON on stdout), 3 = bad usage (no JSON).')
    lines.append('')
    lines.append('modes:')
    for name in MODES:
        lines.append('  %s' % name)
    lines.append('')
    lines.append('--settle N   seconds to wait after dialing before reading '
                 'back (default 20).')
    lines.append('             The old dial_perf.py gave dynamic 30+15=45s and '
                 'other modes 15s;')
    lines.append('             if dynamic reads back empty, try --settle 45.')
    lines.append('')
    lines.append('--param k=v  dial parameters. Every default below is the old '
                 'hardcoded value from')
    lines.append('             dial_perf.py, so passing no --param reproduces '
                 'the old behaviour.')
    lines.append('             An unknown key is a hard error before the router '
                 'is touched.')
    for spec in PARAM_SPEC:
        key, default, help_text = spec
        if default is None:
            shown = '(per mode)'
        else:
            shown = default
        lines.append('  %-15s default %-18s %s' % (key, shown, help_text))
    return '\n'.join(lines)


def _exc_text(exc):
    """Exception type name plus full message, passed through verbatim."""
    # 异常信息原样带出去,不吞。py2 里 str(exc) 遇到 unicode 消息会抛
    # UnicodeEncodeError —— 那会把"报告失败"这一步本身弄崩,所以逐级退让,
    # 最后一步 repr 保证一定拿得到东西。
    name = type(exc).__name__
    try:
        detail = str(exc)
    except Exception:
        try:
            detail = unicode(exc).encode('ascii', 'backslashreplace')  # noqa: F821
        except Exception:
            detail = repr(exc)
    return '%s: %s' % (name, detail)


def _ascii(value):
    """Coerce a read-back value into a pure-ASCII str, safe to put in a message."""
    # 台架控制台是 GBK,而 wan_ip 这类值是 unicode。直接 '%s' 拼进消息再 print,
    # GBK 编不出的字符会在**打印失败信息的那一刻**抛 UnicodeEncodeError。
    try:
        if isinstance(value, unicode):                    # noqa: F821 (py2)
            return value.encode('ascii', 'backslashreplace')
        return str(value)
    except Exception:
        return repr(value)


def _base_mode(mode):
    """pppoe_dynamic_internet -> pppoe; dynamic -> dynamic."""
    # 复合模式取前缀,用来查 WAN_TYPE_BY_MODE。
    return mode.split('_')[0]


def _defaults_for(mode):
    """Parameter defaults for one mode; vpn_user/vpn_pass follow the family."""
    # 老脚本给 PPTP 和 L2TP 发的是两套账号('pptp'/'pptp' 与 'l2tp'/'l2tp'),
    # 所以这两个键的默认值必须随模式家族走,不能写死一个。
    out = {}
    for spec in PARAM_SPEC:
        out[spec[0]] = spec[1]
    base = _base_mode(mode)
    if base == 'pptp' or base == 'l2tp':
        out['vpn_user'] = base
        out['vpn_pass'] = base
    return out


def _dial(dut, mode, p):
    """Dial one mode. Branch structure ported from dial_perf.py lines 270-300."""
    # 模式名一字未改(历史 Excel 按它们对行)。
    #
    # **`internet` 和 `public` 两个后缀对下发没有任何影响** —— 同一支 elif 同时
    # 收下它们,老脚本也是这样。区别只在 Chariot 打哪个远端(老脚本的
    # `e2_ip = PUBLIC_IP if 'public' in dial_mode else INTERNET_IP`),那是读侧的
    # 事,桥接不碰。所以这里看起来"两个模式做同一件事"是对的,不是漏写。
    #
    # 全部方法返回 None,**不能靠返回值判断成败**;成败只由回读定。
    if mode == 'dynamic':
        dut.set_wan_dynamic_ip()

    elif mode == 'static':
        dut.set_wan_static_ip(ip=p['static_ip'], mask=p['static_mask'],
                              gateway=p['static_gateway'], dns1=p['static_dns1'])

    elif mode == 'pppoe':
        dut.connect_wan_pppoe(username=p['pppoe_user'], password=p['pppoe_pass'],
                              connection_mode=dut.PPP_CONNECT_AUTO,
                              second_connection=dut.SECOND_CONN_DISABLED)

    elif mode == 'pppoe_dynamic_internet' or mode == 'pppoe_dynamic_public':
        dut.connect_wan_pppoe(username=p['pppoe_user'], password=p['pppoe_pass'],
                              connection_mode=dut.PPP_CONNECT_AUTO,
                              second_connection=dut.SECOND_CONN_DYNAMIC_IP)

    elif mode == 'pppoe_static_internet' or mode == 'pppoe_static_public':
        dut.connect_wan_pppoe(username=p['pppoe_user'], password=p['pppoe_pass'],
                              connection_mode=dut.PPP_CONNECT_AUTO,
                              second_connection=dut.SECOND_CONN_STATIC_IP,
                              second_connection_ip=p['second_ip'],
                              second_connection_mask=p['second_mask'])

    elif mode == 'pptp_dynamic_internet' or mode == 'pptp_dynamic_public':
        dut.connect_wan_pptp(ppp_username=p['vpn_user'], ppp_password=p['vpn_pass'],
                             pptp_host=p['vpn_server'], is_using_static_ip=None,
                             connection_mode=dut.PPP_CONNECT_AUTO)

    elif mode == 'pptp_static_internet' or mode == 'pptp_static_public':
        dut.connect_wan_pptp(ppp_username=p['vpn_user'], ppp_password=p['vpn_pass'],
                             pptp_host=p['vpn_server'], is_using_static_ip=True,
                             eth_ip=p['eth_ip'], eth_mask=p['eth_mask'],
                             eth_gateway=p['eth_gateway'], eth_dns1=p['eth_dns1'],
                             connection_mode=dut.PPP_CONNECT_AUTO)

    elif mode == 'l2tp_dynamic_internet' or mode == 'l2tp_dynamic_public':
        dut.connect_wan_l2tp(ppp_username=p['vpn_user'], ppp_password=p['vpn_pass'],
                             l2tp_host=p['vpn_server'], is_using_static_ip=None,
                             connection_mode=dut.PPP_CONNECT_AUTO)

    elif mode == 'l2tp_static_internet' or mode == 'l2tp_static_public':
        dut.connect_wan_l2tp(ppp_username=p['vpn_user'], ppp_password=p['vpn_pass'],
                             l2tp_host=p['vpn_server'], is_using_static_ip=True,
                             eth_ip=p['eth_ip'], eth_mask=p['eth_mask'],
                             eth_gateway=p['eth_gateway'], eth_dns1=p['eth_dns1'],
                             connection_mode=dut.PPP_CONNECT_AUTO)

    else:
        raise ValueError('no dial branch for mode %r' % mode)


def _filled_keys(mode):
    base = _base_mode(mode)
    if mode == 'dynamic' or mode == 'static' or mode == 'pppoe':
        return list(PARAMS_USED[mode])
    if base == 'pppoe':
        if mode.find('_static_') >= 0:
            return list(PARAMS_USED['pppoe_static'])
        return list(PARAMS_USED['pppoe_dynamic'])
    if mode.find('_static_') >= 0:
        return list(PARAMS_USED['vpn_static'])
    return list(PARAMS_USED['vpn_dynamic'])


def _jsonable(obj):
    """Make get_wan_info()'s return JSON-serialisable, degrading to repr()."""
    # 返回里混着 str 和 unicode,json 都能吃;但万一有别的类型(比如 ctypes 的
    # 东西)就退成字符串 —— 别让一个字段把整份 detail 的序列化拖崩。
    try:
        json.dumps(obj)
        return obj
    except Exception:
        pass
    if isinstance(obj, dict):
        out = {}
        for key in obj.keys():
            out[_ascii(key)] = _jsonable(obj[key])
        return out
    if isinstance(obj, list) or isinstance(obj, tuple):
        out = []
        for item in obj:
            out.append(_jsonable(item))
        return out
    return repr(obj)


def _parse_args(argv):
    """Hand-rolled option parsing; 2.6 has no argparse (see the file header).

    Returns (opts, params, error). A non-empty error means bad usage: the
    caller must exit EXIT_USAGE and print no JSON at all.
    """
    opts = {
        'mode': None,
        'ip': None,
        'user': 'admin',
        'password': None,
        'settle': 20,
        'brand': 'TPLink',
        'model': '',
        'debug': False,
        'help': False,
    }
    raw_params = []

    dest_of = {
        '--ip': 'ip',
        '--user': 'user',
        '--pass': 'password',
        '--settle': 'settle',
        '--brand': 'brand',
        '--model': 'model',
    }

    i = 0
    while i < len(argv):
        token = argv[i]
        if token == '--help' or token == '-h':
            opts['help'] = True
            return (opts, {}, '')
        if token == '--debug':
            opts['debug'] = True
            i += 1
            continue

        name = token
        inline = None
        eq = token.find('=')
        if token[:2] == '--' and eq > 0:
            name = token[:eq]
            inline = token[eq + 1:]

        if name == '--param':
            if inline is None:
                if i + 1 >= len(argv):
                    return (opts, {}, '--param needs a k=v argument')
                inline = argv[i + 1]
                i += 2
            else:
                i += 1
            raw_params.append(inline)
            continue

        if name in dest_of:
            if inline is None:
                if i + 1 >= len(argv):
                    return (opts, {}, '%s needs a value' % name)
                inline = argv[i + 1]
                i += 2
            else:
                i += 1
            if name == '--settle':
                try:
                    opts['settle'] = int(inline)
                except ValueError:
                    return (opts, {},
                            '--settle wants an integer, got %r' % inline)
            else:
                opts[dest_of[name]] = inline
            continue

        if token[:1] == '-':
            return (opts, {}, 'unknown option %r' % token)

        # 位置参数:只收一个,就是 mode
        if opts['mode'] is not None:
            return (opts, {},
                    'unexpected extra argument %r (mode already set to %r)'
                    % (token, opts['mode']))
        opts['mode'] = token
        i += 1

    if opts['mode'] is None:
        return (opts, {}, 'missing <mode>')
    if opts['mode'] not in MODES:
        return (opts, {},
                'unknown mode %r; valid modes: %s'
                % (opts['mode'], ', '.join(MODES)))
    if not opts['ip']:
        return (opts, {}, '--ip is required')
    if opts['password'] is None:
        return (opts, {}, '--pass is required')

    params = _defaults_for(opts['mode'])
    for item in raw_params:
        if item.find('=') < 0:
            return (opts, {}, '--param wants k=v, got %r' % item)
        pos = item.find('=')
        key = item[:pos].strip()
        value = item[pos + 1:]
        # 键名打错了就当场停下。**不能只警告** —— 默认值恰好就是台架的值,
        # 静默忽略一个打错的键会拿默认值跑完并报 success,那是最难查的一种错。
        if key not in PARAM_KEYS:
            return (opts, {},
                    'unknown --param key %r; valid keys: %s'
                    % (key, ', '.join(PARAM_KEYS)))
        params[key] = value

    return (opts, params, '')


def main(argv=None):
    if argv is None:
        argv = sys.argv[1:]
    opts, params, error = _parse_args(argv)

    if opts['help']:
        sys.stderr.write(usage() + '\n')
        return EXIT_OK
    if error:
        sys.stderr.write('error: %s\n\n' % error)
        sys.stderr.write(usage() + '\n')
        return EXIT_USAGE

    # RouterCtrl 往根 logger 打大量 INFO/DEBUG。默认压到 WARNING,
    # 否则台架上一屏全是它的日志,真正的失败信息反而被埋掉。
    if opts['debug']:
        logging.getLogger().setLevel(logging.DEBUG)
    else:
        logging.getLogger().setLevel(logging.WARNING)

    mode = opts['mode']
    result = {
        'brand': opts['brand'],
        'model': opts['model'],
        'mode': mode,
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
            dut = RouterCtrl.SohoRouterCtrl(opts['ip'], opts['user'],
                                            opts['password'])
        except Exception as exc:
            result['message'] = ('cannot reach router (SohoRouterCtrl '
                                 'constructor failed): %s' % _exc_text(exc))
            return _emit(real_stdout, result)

        try:
            _dial(dut, mode, params)
            result['applied'] = True
            result['filled'] = _filled_keys(mode)
        except Exception as exc:
            result['message'] = ('dial call for mode %s raised: %s'
                                 % (mode, _exc_text(exc)))
            return _emit(real_stdout, result)

        time.sleep(opts['settle'])

        try:
            info = dut.get_wan_info()
        except Exception as exc:
            result['message'] = ('dialed, but get_wan_info() raised so there '
                                 'is no read-back: %s' % _exc_text(exc))
            return _emit(real_stdout, result)

        if not info:
            info = {}
        result['detail'] = _jsonable(info)
        wan_type = _ascii(info.get('wan_type') or '')
        wan_ip = _ascii(info.get('wan_ip') or '')
        status = _ascii(info.get('status') or '')
        result['read_back'] = wan_type

        # status 只作参考,**绝不参与判定**:PTT 拓扑的对端是内网服务器,联网
        # 检测的 DNS 请求没人回应,所以 status 常年是 'poor_connected'。实测
        # PPPoE 已经拿到隧道地址时 status 仍然是它 —— 拿它判定会把成功判成失败。
        if status:
            shown_status = status
        else:
            shown_status = '(empty)'
        result['warnings'].append(
            'status=%s -- informational only. poor_connected is NORMAL on the '
            'PTT bench (the far end is an internal server, so the connectivity '
            'probe gets no DNS answer) and does not mean the link is down.'
            % shown_status)

        expect = WAN_TYPE_BY_MODE[_base_mode(mode)]
        problems = []
        if wan_type != expect:
            problems.append('wan_type mismatch: expected %r, got %r'
                            % (expect, wan_type))
        # 只看 wan_ip 有没有拿到。**不校验 wan_mask** —— PPPoE/PPTP/L2TP 这类
        # 点对点链路的掩码就是 255.255.255.255,那是正常的。
        if not wan_ip:
            problems.append('wan_ip is empty (no address obtained)')
        elif wan_ip[:7] == '0.0.0.0':
            problems.append('wan_ip is %r (starts with 0.0.0.0 = not dialed up)'
                            % wan_ip)

        if problems:
            result['message'] = ('read-back failed: %s. full get_wan_info() '
                                 'is in detail' % '; '.join(problems))
        else:
            result['success'] = True
        return _emit(real_stdout, result)
    finally:
        sys.stdout = real_stdout


def _emit(stream, result):
    """Write the result as one JSON line; return the process exit code."""
    # ensure_ascii 用默认的 True:get_wan_info() 里混着 unicode,转成纯 ASCII 的
    # \uXXXX 最不容易在 py2 的 stdout(台架是 GBK)上炸编码,py3 侧 json.loads
    # 照样还原。sort_keys 只为让人肉眼比对两次运行时稳定 —— py3 侧解析成 dict,
    # 顺序无所谓。
    stream.write(json.dumps(result, sort_keys=True) + '\n')
    try:
        stream.flush()
    except Exception:
        pass
    if result.get('success'):
        return EXIT_OK
    return EXIT_FAIL


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
# 本文件按用户给的清单用正确拼写 'pppoe_dynamic_public',而且 _parse_args 会把
# 不在 MODES 里的模式名当用法错误挡掉(退出码 3),_dial 的兜底 else 也会抛
# ValueError —— 同一类错误不会再悄悄发生。
# 台架验证时请重点看这一档(人工验证步骤第 5 条)。
