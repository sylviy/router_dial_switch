# -*- coding: utf-8 -*-
"""chariot_perf.py —— 单次吞吐测量,给 matrix 的 ChariotBackend 用子进程调用。

这是旧 Dial.py 里 run_up/down/bi_thr + result_judge 的**清理版**:
  * 不再有写死的 IP / 脚本名 / 对数 —— 全部从 --json 传进来的拓扑里取;
  * 不再直接切拨号方式、不写 Excel —— 切模式交给 models/ 的 Web 驱动,
    出报告交给 matrix/report.py;这个文件只负责"测一格并打印 JSON";
  * 保持在它原生的 **Python 2 / Windows / Chariot** 环境里跑
    (import Chariot 放到真正测量时才做,这样别的机器 import 本文件不会炸)。

用法。程序调用(ChariotBackend 自动拼好,不经人手):
    python chariot_perf.py --json '{"mode":"pppoe","band":"lan", ...}'
人在台架上手动调试,用文件版(**别在 PowerShell 里手敲内联 JSON**,它会把
双引号吃掉):把 matrix/cell.example.json 复制一份改好,然后
    python chariot_perf.py --json-file cell.json --dry-run
输出:最后一行是 {"mbps": <float>, "stable": <bool>, "samples": [...]},
      失败则 {"error": "类型: 说明"} 且退出码非 0,**完整 traceback 打在
      stderr** 上(stdout 要留给 JSON)。
加 --dry-run:只解析拓扑并打印它要打给谁、用哪个脚本、多少对,不碰 PyChariot
      —— 台架接线对不对,一眼就能看出来,不用真跑一轮。

兼容 Python 2/3 写法:from __future__ print_function、不用 except X, e、
**不用 argparse**(标准库 2.7 才收它;2026-07-28 台架实测 PATH 上的 Python
是 2.6.5,import argparse 直接 ImportError)。
"""
from __future__ import print_function

import json
import sys
import traceback

USAGE = ("usage: chariot_perf.py (--json '<topology json>'"
         " | --json-file <path>) [--dry-run]")

TCP, UDP = "TCP", "UDP"


def _to_native(obj):
    """Py2 上把 json.loads 出来的 unicode 递归转成 str(字节串)。

    PyChariot 是 ctypes 包的 C API,绝大多数入参要的是 str;而 Py2 的
    json.loads **所有**字符串都给 unicode。不转的话,IP、脚本名、甚至 dict 的
    键全是 unicode,踩雷只是早晚问题。Py3 上原样返回。
    """
    if sys.version_info[0] >= 3:
        return obj
    if isinstance(obj, unicode):            # noqa: F821  仅 Py2 存在
        return obj.encode("utf-8")
    if isinstance(obj, dict):
        return dict((_to_native(k), _to_native(v)) for k, v in obj.items())
    if isinstance(obj, list):
        return [_to_native(v) for v in obj]
    return obj


def _call(what, fn, *args, **kwargs):
    """调 PyChariot 的一步,失败时把**每个参数的值和类型**一起报出来。

    ctypes 的 "an integer is required" 不说是哪个参数出的问题,而这台机器
    我看不见、每问一轮都要人跑一趟机架。所以让错误自己带上证据:一行报错
    就能定位到是哪个参数、它当时是什么类型。
    """
    try:
        return fn(*args, **kwargs)
    except Exception as exc:
        detail = ", ".join(
            ["%r(%s)" % (a, type(a).__name__) for a in args]
            + ["%s=%r(%s)" % (k, v, type(v).__name__)
               for k, v in sorted(kwargs.items())])
        # 消息保持纯 ASCII:它会被 json.dumps 打出来,中文会变成一串
        # \uXXXX 转义,现场读报错时反而更费劲。
        raise RuntimeError("%s(%s) -> %s: %s"
                           % (what, detail, type(exc).__name__, exc))


def _e1_ip(topo, band):
    """客户端侧注入机:按频段取。"""
    return topo["endpoints"].get(band, topo["endpoints"].get("lan"))


def _e2_ip(topo, mode):
    """对端:动态/静态/带 public 的组合走公网口,其余走内网口 —— 照搬旧逻辑。"""
    if mode in ("dynamic", "static") or ("public" in mode):
        return topo["public_ip"]
    return topo["internet_ip"]


def _protocol(proto):
    """协议名 -> add_pair 要的协议值。名字直接对应 PyChariot 的常量,所以
    TCP / UDP / TCP6 / UDP6 都认(v6 那两个还需要 e1/e2 填 IPv6 地址)。

    台架 2026-07-28 实测定案:`CHR_PROTOCOL_TCP` **不是整数 2,是 c_byte(2)**
    (PyChariot 自己的日志打的就是 `protocol:c_byte(2)`),而它内部又会拿它去
    构造一次 c_byte —— 等于 c_byte(c_byte(2)),ctypes 报
    `TypeError: an integer is required`。所以必须取 .value 再 int()。
    传字符串 "TCP" 同样不行(第一版就是这么错的)。

    名字不认识就**报错**,不猜。以前 measure() 会把任何非 UDP 的写法悄悄当成
    TCP —— 那样 `protocols: [TCP6]` 会安安静静地测出一份 v4 的数据,还标着
    TCP6,比直接失败坏得多。
    """
    import PyChariot
    raw = getattr(PyChariot, "CHR_PROTOCOL_" + proto, None)
    if raw is None:
        known = sorted(n[len("CHR_PROTOCOL_"):] for n in dir(PyChariot)
                       if n.startswith("CHR_PROTOCOL_"))
        raise ValueError("PyChariot 不认识协议 %r;它支持的是:%s"
                         % (proto, ", ".join(known)))
    raw = getattr(raw, "value", raw)    # 常量可能是 c_byte/c_int 之类的包装
    try:
        return int(raw)
    except (TypeError, ValueError):
        return raw


def _pairs_for(topo, proto):
    """该协议用多少对。TCP6/UDP6 没单独配就沿用同族的 TCP/UDP 配置。"""
    table = topo["pairs"]
    if proto in table:
        return int(table[proto])
    base = proto[:-1] if proto.endswith("6") else proto
    return int(table.get(base, 50))


def _add_pairs(chr_obj, e1, e2, proto, script, pairs, half=False):
    """proto 是 'TCP'/'UDP' 字符串。

    add_pair 的签名 2026-07-28 在台架上核对过:
      add_pair(e1_addr, e2_addr, script_name, protocol, pair_number,   <- 必填
               comment=None, qos_name=None, console_e1_addr=None,
               console_e1_protocol=2, console_e1_qos_name=None,
               e1_e2_addr=None, script_variable={})
    我们用到的五个关键字全部对得上。
    """
    n = pairs // 2 if half else pairs
    kwargs = {"e1_addr": e1, "e2_addr": e2, "script_name": script,
              "protocol": _protocol(proto), "pair_number": n}
    if proto.startswith(UDP):      # UDP 和 UDP6 都算
        # UDP 非分片场景旧脚本会限制发送缓冲(send_buffer_size=1300),这里保留
        kwargs["script_variable"] = {"send_buffer_size": "1300"}
    _call("add_pair", chr_obj.add_pair, **kwargs)


def _judge(chr_obj, duration_s, ratio):
    """稳定性判据(照搬 result_judge):看中段各 5s 采样是否 min >= ratio*max。
    返回 (总吞吐 float, 采样 list, 是否稳定 bool)。"""
    n = max(duration_s // 5, 3)
    samples = []
    for i in range(2, n):
        samples.append(_call("get_throughput", chr_obj.get_throughput,
                             time_1=5 * i, time_2=5 * (i + 1)))
    total = _call("get_throughput", chr_obj.get_throughput)
    stable = bool(samples) and (min(samples) >= ratio * max(samples))
    return total, samples, stable


def measure(topo):
    """真正跑一次 Chariot 测量;只有这里才 import Chariot(台架才有)。"""
    from PyChariot import Chariot          # noqa: E402  台架环境专属

    mode = topo["mode"]
    band = topo["band"]
    direction = topo["direction"]          # up | down | bi
    proto = topo["proto"].upper()          # TCP / UDP / TCP6 / UDP6

    e1, e2 = _e1_ip(topo, band), _e2_ip(topo, mode)
    pairs = _pairs_for(topo, proto)
    up_scr = topo["scripts"]["up"]
    down_scr = topo["scripts"]["down"]

    chr_obj = _call("Chariot()", Chariot)
    if direction == "up":
        _add_pairs(chr_obj, e1, e2, proto, up_scr, pairs)
    elif direction == "down":
        _add_pairs(chr_obj, e1, e2, proto, down_scr, pairs)
    else:  # bi:上下行各占一半对数
        _add_pairs(chr_obj, e1, e2, proto, up_scr, pairs, half=True)
        _add_pairs(chr_obj, e1, e2, proto, down_scr, pairs, half=True)

    _call("set_run_option", chr_obj.set_run_option,
          duration=int(topo["duration_s"]))
    _call("set_filename", chr_obj.set_filename,
          "%s_%s_%s_%s.tst" % (mode, band, proto, direction))
    _call("run", chr_obj.run)
    _call("save_test", chr_obj.save_test)

    total, samples, stable = _judge(chr_obj, topo["duration_s"],
                                    float(topo["stability_ratio"]))
    return {"mbps": round(float(total), 2), "stable": stable,
            "samples": [round(float(s), 2) for s in samples]}


def plan(topo):
    """--dry-run:把拓扑解析出来给人看,**完全不碰 PyChariot**。

    真跑一格之前先跑这个,能当场看出 e1/e2/脚本/对数有没有指错 —— 这类错
    (注入机 IP 写错、隧道模式却打到直连口)靠看真实测量结果是看不出来的,
    数字照样出得来,只是测的不是你以为的那条路。
    """
    mode, band = topo["mode"], topo["band"]
    proto = topo["proto"].upper()
    public = _e2_ip(topo, mode) == topo.get("public_ip")
    return {"dry_run": True,
            "mode": mode, "band": band,
            "direction": topo["direction"], "proto": proto,
            "e1_client_side": _e1_ip(topo, band),
            "e2_wan_side": _e2_ip(topo, mode),
            "e2_source": "public_ip (direct)" if public
                         else "internet_ip (tunnel)",
            "scripts": topo["scripts"],
            "pairs": _pairs_for(topo, proto),
            "duration_s": topo["duration_s"]}


def _payload_from_argv(args):
    """取要解析的 JSON 文本。手写解析,不依赖 argparse。两种给法:

      --json '<内联 JSON>'   ChariotBackend 用这个(程序拼的,引号不经人手);
      --json-file <路径>     人在台架上用这个。PowerShell 传参给外部程序时会
                             把字符串里的双引号吃掉,内联 JSON 会变成一堆
                             {mode:dynamic} 这样的残骸 —— 那是个纯粹浪费时间
                             的坑,放文件里编辑既没这问题,也方便反复改。
    """
    if "--json-file" in args:
        i = args.index("--json-file")
        if i + 1 >= len(args):
            raise ValueError("--json-file needs a path after it")
        with open(args[i + 1]) as fh:
            return fh.read()
    if "--json" not in args:
        raise ValueError(USAGE)
    i = args.index("--json")
    if i + 1 >= len(args):
        raise ValueError("--json needs a JSON string after it")
    return args[i + 1]


def main(argv=None):
    args = list(sys.argv[1:] if argv is None else argv)
    try:
        topo = _to_native(json.loads(_payload_from_argv(args)))
        result = plan(topo) if "--dry-run" in args else measure(topo)
    except Exception as exc:                 # noqa: BLE001  收敛成 JSON 错误
        # 完整 traceback 打到 stderr:stdout 要留给 JSON(ChariotBackend 解析
        # 它),stderr 则被原样收进错误信息。这样出事时一次就能看全,不用再
        # 来回问"能不能再跑一遍加个 -v" —— 现场只有一个人,往返很贵。
        traceback.print_exc()
        print(json.dumps({"error": "%s: %s" % (type(exc).__name__, exc)}))
        return 2
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    sys.exit(main())
