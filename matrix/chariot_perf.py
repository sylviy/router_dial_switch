# -*- coding: utf-8 -*-
"""chariot_perf.py —— 单次吞吐测量,给 matrix 的 ChariotBackend 用子进程调用。

这是旧 Dial.py 里 run_up/down/bi_thr + result_judge 的**清理版**:
  * 不再有写死的 IP / 脚本名 / 对数 —— 全部从 --json 传进来的拓扑里取;
  * 不再直接切拨号方式、不写 Excel —— 切模式交给 models/ 的 Web 驱动,
    出报告交给 matrix/report.py;这个文件只负责"测一格并打印 JSON";
  * 保持在它原生的 **Python 2 / Windows / Chariot** 环境里跑
    (import Chariot 放到真正测量时才做,这样别的机器 import 本文件不会炸)。

用法(由 ChariotBackend 自动拼好,一般不手敲):
    python chariot_perf.py --json '{"mode":"pppoe","band":"lan",
        "direction":"up","proto":"TCP","duration_s":20, ...}'
输出:最后一行是 {"mbps": <float>, "stable": <bool>, "samples": [...]},
      失败则 {"error": "..."} 且退出码非 0。

兼容 Python 2/3 写法:from __future__ print_function、不用 except X, e。
"""
from __future__ import print_function

import argparse
import json
import sys

TCP, UDP = "TCP", "UDP"


def _e1_ip(topo, band):
    """客户端侧注入机:按频段取。"""
    return topo["endpoints"].get(band, topo["endpoints"].get("lan"))


def _e2_ip(topo, mode):
    """对端:动态/静态/带 public 的组合走公网口,其余走内网口 —— 照搬旧逻辑。"""
    if mode in ("dynamic", "static") or ("public" in mode):
        return topo["public_ip"]
    return topo["internet_ip"]


def _add_pairs(chr_obj, e1, e2, proto_const, script, pairs, half=False):
    from PyChariot import Chariot  # noqa: F401  (仅为文档;实际类型由调用方给)
    n = pairs // 2 if half else pairs
    # UDP 非分片场景旧脚本会限制发送缓冲(send_buffer_size=1300),这里保留
    if proto_const == UDP:
        chr_obj.add_pair(e1_addr=e1, e2_addr=e2, script_name=script,
                         protocol=proto_const, pair_number=n,
                         script_variable={"send_buffer_size": "1300"})
    else:
        chr_obj.add_pair(e1_addr=e1, e2_addr=e2, script_name=script,
                         protocol=proto_const, pair_number=n)


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
    proto = topo["proto"].upper()
    proto_const = UDP if proto == UDP else TCP

    e1, e2 = _e1_ip(topo, band), _e2_ip(topo, mode)
    pairs = int(topo["pairs"].get(proto, 50))
    up_scr = topo["scripts"]["up"]
    down_scr = topo["scripts"]["down"]

    chr_obj = Chariot()
    if direction == "up":
        _add_pairs(chr_obj, e1, e2, proto_const, up_scr, pairs)
    elif direction == "down":
        _add_pairs(chr_obj, e1, e2, proto_const, down_scr, pairs)
    else:  # bi:上下行各占一半对数
        _add_pairs(chr_obj, e1, e2, proto_const, up_scr, pairs, half=True)
        _add_pairs(chr_obj, e1, e2, proto_const, down_scr, pairs, half=True)

    chr_obj.set_run_option(duration=topo["duration_s"])
    chr_obj.set_filename("%s_%s_%s_%s.tst" % (mode, band, proto, direction))
    chr_obj.run()
    chr_obj.save_test()

    total, samples, stable = _judge(chr_obj, topo["duration_s"],
                                    float(topo["stability_ratio"]))
    return {"mbps": round(float(total), 2), "stable": stable,
            "samples": [round(float(s), 2) for s in samples]}


def main(argv=None):
    ap = argparse.ArgumentParser(description="single Chariot throughput sample")
    ap.add_argument("--json", required=True, help="拓扑 + 本格参数(JSON)")
    args = ap.parse_args(argv)
    try:
        topo = json.loads(args.json)
        result = measure(topo)
    except Exception as exc:                 # noqa: BLE001  收敛成 JSON 错误
        print(json.dumps({"error": str(exc)}))
        return 2
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    sys.exit(main())
