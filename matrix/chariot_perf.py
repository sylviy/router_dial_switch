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


def _e1_ip(topo, band):
    """客户端侧注入机:按频段取。"""
    return topo["endpoints"].get(band, topo["endpoints"].get("lan"))


def _e2_ip(topo, mode):
    """对端:动态/静态/带 public 的组合走公网口,其余走内网口 —— 照搬旧逻辑。"""
    if mode in ("dynamic", "static") or ("public" in mode):
        return topo["public_ip"]
    return topo["internet_ip"]


def _protocol(proto):
    """'TCP'/'UDP' -> add_pair 要的协议值。

    台架 2026-07-28 实录:PyChariot 里有 CHR_PROTOCOL_TCP / CHR_PROTOCOL_UDP,
    而 add_pair 的 console_e1_protocol 默认值是整数 2 —— 说明 protocol 收的是
    整数常量,不是字符串。所以优先取库自己的常量;取不到才退回字符串(老包装
    器有可能自己做映射)。这样不用赌。
    """
    import PyChariot
    return getattr(PyChariot, "CHR_PROTOCOL_" + proto, proto)


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
    if proto == UDP:
        # UDP 非分片场景旧脚本会限制发送缓冲(send_buffer_size=1300),这里保留
        kwargs["script_variable"] = {"send_buffer_size": "1300"}
    chr_obj.add_pair(**kwargs)


def _judge(chr_obj, duration_s, ratio):
    """稳定性判据(照搬 result_judge):看中段各 5s 采样是否 min >= ratio*max。
    返回 (总吞吐 float, 采样 list, 是否稳定 bool)。"""
    n = max(duration_s // 5, 3)
    samples = []
    for i in range(2, n):
        samples.append(chr_obj.get_throughput(time_1=5 * i, time_2=5 * (i + 1)))
    total = chr_obj.get_throughput()
    stable = bool(samples) and (min(samples) >= ratio * max(samples))
    return total, samples, stable


def measure(topo):
    """真正跑一次 Chariot 测量;只有这里才 import Chariot(台架才有)。"""
    from PyChariot import Chariot          # noqa: E402  台架环境专属

    mode = topo["mode"]
    band = topo["band"]
    direction = topo["direction"]          # up | down | bi
    proto = UDP if topo["proto"].upper() == UDP else TCP

    e1, e2 = _e1_ip(topo, band), _e2_ip(topo, mode)
    pairs = int(topo["pairs"].get(proto, 50))
    up_scr = topo["scripts"]["up"]
    down_scr = topo["scripts"]["down"]

    chr_obj = Chariot()
    if direction == "up":
        _add_pairs(chr_obj, e1, e2, proto, up_scr, pairs)
    elif direction == "down":
        _add_pairs(chr_obj, e1, e2, proto, down_scr, pairs)
    else:  # bi:上下行各占一半对数
        _add_pairs(chr_obj, e1, e2, proto, up_scr, pairs, half=True)
        _add_pairs(chr_obj, e1, e2, proto, down_scr, pairs, half=True)

    chr_obj.set_run_option(duration=topo["duration_s"])
    chr_obj.set_filename("%s_%s_%s_%s.tst" % (mode, band, proto, direction))
    chr_obj.run()
    chr_obj.save_test()

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
    proto = UDP if topo["proto"].upper() == UDP else TCP
    public = _e2_ip(topo, mode) == topo.get("public_ip")
    return {"dry_run": True,
            "mode": mode, "band": band,
            "direction": topo["direction"], "proto": proto,
            "e1_client_side": _e1_ip(topo, band),
            "e2_wan_side": _e2_ip(topo, mode),
            "e2_source": "public_ip (direct)" if public
                         else "internet_ip (tunnel)",
            "scripts": topo["scripts"],
            "pairs": int(topo["pairs"].get(proto, 50)),
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
        topo = json.loads(_payload_from_argv(args))
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
