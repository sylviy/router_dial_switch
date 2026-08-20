"""性能测量后端 —— 编排器只认一个接口 measure(mode, band, direction, proto)。

两个实现:
  * SimulatorBackend  纯 Python、无外部依赖:算出一个可复现的"看起来真实"的
                      吞吐数。让整条链路(切模式 → 测 → 出报告)在没有 Chariot、
                      没有路由器的机器上也能跑通(--demo、CI、演示)。
  * ChariotBackend    真台架:把每次测量交给 matrix/chariot_perf.py(旧 Dial.py
                      的 Chariot 逻辑),用子进程隔开跑它的那个解释器,读它
                      打印的 JSON。那个解释器由 config.yaml 的 bench.python2
                      决定:PyChariot 装在同一个 python 里就留空,老台架
                      (只在 Python 2.6.5 里)写 C:\\Python26\\python.exe。

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

    def preflight(self) -> str:
        """开跑前自检。返回空串 = 就绪;返回文字 = 不能跑的原因。

        整轮要几十分钟,而且每一格失败前都会**真正切一次拨号方式**。后端根本
        没配好的话,那就是花半小时把路由器来回切一遍、拿回一份全是 err 的报告
        (台架 2026-07-28 实测就这么浪费了一轮)。宁可开跑前一秒钟就拦住。
        """
        return ""


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
        if proto.startswith("UDP"):
            base *= 1.05                              # UDP 略高于 TCP
        if proto.endswith("-NOFRAG"):
            base *= 0.88            # 不分片:包更小,包头开销占比更高
        mbps = round(base * self._jitter(mode, band, direction, proto), 1)
        # 造 4 个 5 秒采样点,和 result_judge 的稳定性判据同形态
        j = self._jitter(band, direction, proto, mode)
        samples = [round(mbps * s, 1) for s in (0.99, 1.0, 0.98 * j + 0.02, 1.0)]
        return Measurement(mode, band, direction, proto, mbps=mbps,
                           stable=True, samples=samples)


# --------------------------------------------------------------------------
def _last_json(text: str) -> Optional[dict]:
    """从后往前找第一个能解析成 JSON 对象的片段,没有就 None。

    不能直接取最后一行:台架实测 PyChariot 自己带 logging,一 import 就打
    `DEBUG:ChariotApi:...` 之类的行,收尾时也可能再吐几行。结果 JSON 是
    chariot_perf.py 打的最后一条**有效**输出,不一定是最后一条输出。

    也不能要求 JSON **正好起一行**:Chariot 的错误是它自己的原生库直接写
    stdout 的,不走 Python 的缓冲、而且末尾**没有换行**,于是我们那行 JSON 会
    被接在它后面:

        Error was detected at M{"mbps": 283.63, "samples": [...]}

    2026-08-10 台架实测:PPTP 那一格明明测到了 283.63 Mbps,却因为这一条被
    记成 `err`("输出里没有 JSON 结果")—— 一次**成功的测量被报成失败**。
    所以这里改成:每一行从任意 `{` 开始试着解析,并容忍后面还有别的字符。
    """
    decoder = json.JSONDecoder()
    for line in reversed((text or "").strip().splitlines()):
        at = line.find("{")
        while at >= 0:
            try:
                data, _end = decoder.raw_decode(line[at:])
            except ValueError:
                data = None
            if isinstance(data, dict):
                return data
            at = line.find("{", at + 1)
    return None


_PY_HINT = """
  chariot_perf.py 在 **Python 2 和 Python 3 上都能跑**(它的语法两边通用),
  但 PyChariot 是装在**某一个具体解释器**里的库 —— 装在哪就只能在哪 import。
  决定它跑在哪个 python 里的是:
    config.yaml 的 bench.python2。怎么填:
    * 留空(默认)= 用跑本工具的这个 python。**PyChariot 装在同一个 python
      里的台架(日本 IPoE 那套是 Python 3)才留空。**
    * 台架自带的 vendor\\python 是 3.8,里面**没有** PyChariot;老台架的
      PyChariot 只在 ActivePython 2.6.5 里,那就要写绝对路径:
          bench.python2: C:\\Python26\\python.exe
      (同一台机的 Playwright 要 3.8,两个 python 只能靠子进程隔开。)
  确认办法:<你写的那个 python> -c "import PyChariot; print('ok')" """


class ChariotBackend(PerfBackend):
    """真台架:子进程调用 chariot_perf.py(内部才 import Chariot)。
    每次测量传入拓扑(内外网 IP、注入机、脚本、对数、时长)作为一个 JSON,
    读回 {mbps, stable, samples}。任何失败(缺 Chariot、超时、非零退出)都
    收敛成 Measurement.error,让某一格坏掉不至于拖垮整轮矩阵。"""
    name = "chariot"

    def __init__(self, chariot_cfg):
        self.cfg = chariot_cfg
        self.script = chariot_cfg.script or os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "chariot_perf.py")

    def preflight(self) -> str:
        py = self.cfg.interpreter
        try:
            out = subprocess.run([py, "-c", "import PyChariot"],
                                 capture_output=True, text=True,
                                 errors="replace", timeout=120)
        except Exception as exc:
            return ("解释器 %r 跑不起来:%s" % (py, exc)) + _PY_HINT
        if out.returncode != 0:
            lines = (out.stderr or out.stdout or "").strip().splitlines()
            return ("解释器 %r 里没有 PyChariot:%s"
                    % (py, lines[-1] if lines else "(无输出)")) + _PY_HINT
        return ""

    def measure(self, mode, band, direction, proto) -> Measurement:
        payload = {
            "mode": mode, "band": band, "direction": direction, "proto": proto,
            "duration_s": self.cfg.duration_s,
            "internet_ip": self.cfg.internet_ip,
            "public_ip": self.cfg.public_ip,
            "e2_ip": self.cfg.e2_ip,
            "endpoints": self.cfg.endpoints,
            "scripts": self.cfg.scripts,
            "pairs": self.cfg.pairs,
            "nofrag_bytes": self.cfg.nofrag_bytes,
            "tst_dir": self.cfg.tst_dir if self.cfg.save_tests else "",
            "stability_ratio": self.cfg.stability_ratio,
        }
        cmd = [self.cfg.interpreter, self.script, "--json", json.dumps(payload)]
        try:
            # errors="replace":台架实测 PyChariot 一 import 就往外打 DEBUG 行,
            # 里面还有中文;子进程按 GBK 写、父进程按 GBK 读本来是对的,但只要
            # 有一个字节对不上,UnicodeDecodeError 就会连这一格的测量一起打掉。
            # 宁可把那个字符显示成 ?,也不能丢一格数据。
            out = subprocess.run(cmd, capture_output=True, text=True,
                                 errors="replace",
                                 timeout=self.cfg.duration_s * 6 + 120)
        except Exception as exc:
            return Measurement(mode, band, direction, proto,
                               error="启动 chariot_perf.py 失败: %s" % exc)
        if out.returncode != 0:
            msg = (out.stderr or out.stdout or "").strip()[-300:]
            return Measurement(mode, band, direction, proto,
                               error="chariot_perf.py 退出码 %d: %s"
                                     % (out.returncode, msg))
        data = _last_json(out.stdout or "")
        if data is None:
            tail = (out.stdout or out.stderr or "").strip()[-300:]
            return Measurement(mode, band, direction, proto,
                               error="chariot_perf.py 输出里没有 JSON 结果: %s"
                                     % tail)
        return Measurement(mode, band, direction, proto,
                           mbps=data.get("mbps"), stable=data.get("stable"),
                           samples=list(data.get("samples") or []),
                           error=str(data.get("error") or ""))


def make_backend(cfg) -> PerfBackend:
    if cfg.backend == "chariot":
        return ChariotBackend(cfg.chariot)
    return SimulatorBackend()
