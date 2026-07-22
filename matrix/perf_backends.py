"""性能测量后端 —— 编排器只认一个接口 measure(mode, band, direction, proto)。

两个实现:
  * SimulatorBackend  纯 Python、无外部依赖:算出一个可复现的"看起来真实"的
                      吞吐数。让整条链路(切模式 → 测 → 出报告)在没有 Chariot、
                      没有路由器的机器上也能跑通(--demo、CI、演示)。
  * ChariotBackend    真台架:把每次测量交给 matrix/chariot_perf.py(旧 Dial.py
                      的 Chariot 逻辑,保持在它原生的 Py2/Windows 环境里),
                      用子进程隔开两个 Python 世界,读它打印的 JSON。

新增后端 = 继承 PerfBackend、实现 measure 即可,编排器和报告都不用改。
"""
from __future__ import annotations

import json
import os
import subprocess
from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class Measurement:
    mode: str
    band: str
    direction: str          # up | down | bi
    proto: str              # TCP | UDP
    mbps: Optional[float] = None
    stable: Optional[bool] = None
    samples: List[float] = field(default_factory=list)
    error: str = ""

    @property
    def ok(self) -> bool:
        return self.mbps is not None and not self.error


class PerfBackend:
    name = "base"

    def measure(self, mode: str, band: str, direction: str,
                proto: str) -> Measurement:
        raise NotImplementedError


# --------------------------------------------------------------------------
class SimulatorBackend(PerfBackend):
    """离线模拟:数字由 (频段/方向/协议/模式) 决定 + 轻微可复现抖动。
    不接触任何路由器或仪表 —— 仅用于让工具在任何机器上演示/自检。"""
    name = "simulate"

    # 频段基准吞吐(Mbps),贴近千兆有线 / Wi-Fi 实测量级
    _BAND = {"lan": 940.0, "5GHz": 700.0, "2GHz": 260.0}
    # 拨号方式的封装开销(相对系数):PPPoE/VPN 比动态IP略低
    _MODE = {"pppoe": 0.95, "pppoev6": 0.93, "l2tp": 0.82, "pptp": 0.80}

    def _jitter(self, *parts) -> float:
        # 稳定的伪随机:同样的输入永远给同样的数,报告可复现
        h = abs(hash("|".join(str(p) for p in parts)))
        return 0.94 + (h % 1000) / 1000.0 * 0.06     # 0.94 ~ 1.00

    def measure(self, mode, band, direction, proto) -> Measurement:
        base = self._BAND.get(band, 500.0)
        base *= self._MODE.get(mode, 1.0)
        if direction == "bi":
            base *= 1.35                              # 双向合计更高
        elif direction == "down":
            base *= 1.02
        if proto == "UDP":
            base *= 1.05                              # UDP 略高于 TCP
        mbps = round(base * self._jitter(mode, band, direction, proto), 1)
        # 造 4 个 5 秒采样点,和 result_judge 的稳定性判据同形态
        j = self._jitter(band, direction, proto, mode)
        samples = [round(mbps * s, 1) for s in (0.99, 1.0, 0.98 * j + 0.02, 1.0)]
        return Measurement(mode, band, direction, proto, mbps=mbps,
                           stable=True, samples=samples)


# --------------------------------------------------------------------------
class ChariotBackend(PerfBackend):
    """真台架:子进程调用 chariot_perf.py(Py2/Windows,内部 import Chariot)。
    每次测量传入拓扑(内外网 IP、注入机、脚本、对数、时长)作为一个 JSON,
    读回 {mbps, stable, samples}。任何失败(缺 Chariot、超时、非零退出)都
    收敛成 Measurement.error,让某一格坏掉不至于拖垮整轮矩阵。"""
    name = "chariot"

    def __init__(self, chariot_cfg):
        self.cfg = chariot_cfg
        self.script = chariot_cfg.script or os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "chariot_perf.py")

    def measure(self, mode, band, direction, proto) -> Measurement:
        payload = {
            "mode": mode, "band": band, "direction": direction, "proto": proto,
            "duration_s": self.cfg.duration_s,
            "internet_ip": self.cfg.internet_ip,
            "public_ip": self.cfg.public_ip,
            "endpoints": self.cfg.endpoints,
            "scripts": self.cfg.scripts,
            "pairs": self.cfg.pairs,
            "stability_ratio": self.cfg.stability_ratio,
        }
        cmd = [self.cfg.python2, self.script, "--json", json.dumps(payload)]
        try:
            out = subprocess.run(cmd, capture_output=True, text=True,
                                 timeout=self.cfg.duration_s * 6 + 120)
        except Exception as exc:
            return Measurement(mode, band, direction, proto,
                               error="启动 chariot_perf.py 失败: %s" % exc)
        if out.returncode != 0:
            msg = (out.stderr or out.stdout or "").strip()[-300:]
            return Measurement(mode, band, direction, proto,
                               error="chariot_perf.py 退出码 %d: %s"
                                     % (out.returncode, msg))
        try:
            data = json.loads((out.stdout or "").strip().splitlines()[-1])
        except Exception as exc:
            return Measurement(mode, band, direction, proto,
                               error="无法解析 chariot_perf.py 输出: %s" % exc)
        return Measurement(mode, band, direction, proto,
                           mbps=data.get("mbps"), stable=data.get("stable"),
                           samples=list(data.get("samples") or []),
                           error=str(data.get("error") or ""))


def make_backend(cfg) -> PerfBackend:
    if cfg.backend == "chariot":
        return ChariotBackend(cfg.chariot)
    return SimulatorBackend()
