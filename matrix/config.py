"""加载 perf.yaml —— WAN 性能矩阵的全部可调项。

分工:
  * perf.yaml   描述 **测什么、怎么测**(测试矩阵、后端、拨号台架拓扑、
                WAN 拨通判据、报告位置);可提交模板是 perf.example.yaml。
  * router.yaml 存 **密码**(管理密码 / 宽带账密),由 settings.py 读,git 忽略。

两者分开:换台架拓扑改 perf.yaml,换密码改 router.yaml,互不干扰。
perf.yaml 缺项一律回落到下面的默认值 —— 一个空文件也能跑(内置 dynamic+pppoe 矩阵)。
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Dict, List, Optional

try:
    import yaml
except Exception:  # pragma: no cover - yaml 是硬依赖,这里只是防御
    yaml = None

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_PATH = os.path.join(ROOT, "perf.yaml")
EXAMPLE_PATH = os.path.join(ROOT, "perf.example.yaml")


@dataclass
class DialStep:
    """矩阵里的一档拨号方式:mode 必须是该型号脚本声明过的模式;
    params 是切它需要的账密/服务器(会传给 _driver.run)。"""
    mode: str
    params: Dict[str, str] = field(default_factory=dict)


@dataclass
class WanUpCfg:
    """切完模式后等 WAN 拨通的判据。method=ping 就 ping host 到通为止,
    否则只做固定等待。拨通后再多等 settle_s 秒让链路稳定(旧脚本睡 15s)。"""
    method: str = "wait"          # ping | wait
    host: str = ""
    timeout_s: int = 60
    settle_s: int = 15


@dataclass
class ChariotCfg:
    """Chariot 后端参数,逐项对应旧 Dial.py 里的常量(仅台架用,离线模拟忽略)。"""
    duration_s: int = 20
    internet_ip: str = "192.168.203.1"
    public_ip: str = "192.168.202.99"
    # 客户端侧(e1)每个频段用哪台注入机
    endpoints: Dict[str, str] = field(
        default_factory=lambda: {"lan": "192.168.0.79",
                                 "2GHz": "192.168.0.132",
                                 "5GHz": "192.168.0.132"})
    # 上行/下行各自的 Chariot 脚本
    scripts: Dict[str, str] = field(
        default_factory=lambda: {"up": "Throughput.scr",
                                 "down": "Throughput_w2l.scr"})
    pairs: Dict[str, int] = field(
        default_factory=lambda: {"TCP": 50, "UDP": 100})
    stability_ratio: float = 0.9   # min < ratio*max 即判为"不稳"
    python2: str = "python"        # 跑 chariot_perf.py 的解释器(台架多为 py2)
    script: str = ""               # chariot_perf.py 路径(默认取包内同目录)


@dataclass
class PerfConfig:
    model: str = ""
    backend: str = "simulate"      # simulate(离线模拟) | chariot(真台架)
    dial_modes: List[DialStep] = field(default_factory=list)
    bands: List[str] = field(default_factory=lambda: ["lan"])
    directions: List[str] = field(default_factory=lambda: ["up", "down", "bi"])
    protocols: List[str] = field(default_factory=lambda: ["TCP"])
    wan_up: WanUpCfg = field(default_factory=WanUpCfg)
    chariot: ChariotCfg = field(default_factory=ChariotCfg)
    report_dir: str = "artifacts"
    report_title: str = "WAN Performance Matrix"
    reset_mode: Optional[str] = None   # 全部跑完后切回的安全模式(旧脚本切回 dynamic)


# --------------------------------------------------------------------------
_DEFAULT_MATRIX = [DialStep("dynamic"),
                   DialStep("pppoe", {"pppoe_user": "pppoe",
                                      "pppoe_pass": "pppoe"})]


def _dial_steps(raw) -> List[DialStep]:
    steps: List[DialStep] = []
    for item in raw or []:
        if isinstance(item, str):
            steps.append(DialStep(item))
        elif isinstance(item, dict):
            steps.append(DialStep(str(item.get("mode", "")).strip(),
                                  dict(item.get("params") or {})))
    return [s for s in steps if s.mode]


def load(path: str = DEFAULT_PATH) -> PerfConfig:
    """读 perf.yaml -> PerfConfig。文件缺失/为空 -> 全默认(仍可 --demo 跑通)。"""
    data: dict = {}
    if yaml is not None:
        for p in (path, EXAMPLE_PATH if path == DEFAULT_PATH else None):
            if p and os.path.exists(p):
                try:
                    with open(p, "r", encoding="utf-8") as fh:
                        data = yaml.safe_load(fh) or {}
                    break
                except Exception:
                    data = {}
    if not isinstance(data, dict):
        data = {}

    cfg = PerfConfig()
    cfg.model = str(data.get("model", "") or "")
    cfg.backend = str(data.get("backend", cfg.backend) or cfg.backend).lower()
    cfg.dial_modes = _dial_steps(data.get("dial_modes")) or list(_DEFAULT_MATRIX)
    cfg.bands = list(data.get("bands") or cfg.bands)
    cfg.directions = list(data.get("directions") or cfg.directions)
    cfg.protocols = [str(p).upper() for p in (data.get("protocols")
                                              or cfg.protocols)]
    cfg.report_dir = str(data.get("report", {}).get("dir")
                         or data.get("report_dir") or cfg.report_dir)
    cfg.report_title = str(data.get("report", {}).get("title")
                           or cfg.report_title)
    cfg.reset_mode = data.get("reset_mode") or None

    wu = data.get("wan_up") or {}
    cfg.wan_up = WanUpCfg(method=str(wu.get("method", cfg.wan_up.method)),
                          host=str(wu.get("host", "") or ""),
                          timeout_s=int(wu.get("timeout_s", cfg.wan_up.timeout_s)),
                          settle_s=int(wu.get("settle_s", cfg.wan_up.settle_s)))

    ch = data.get("chariot") or {}
    base = ChariotCfg()
    cfg.chariot = ChariotCfg(
        duration_s=int(ch.get("duration_s", base.duration_s)),
        internet_ip=str(ch.get("internet_ip", base.internet_ip)),
        public_ip=str(ch.get("public_ip", base.public_ip)),
        endpoints=dict(ch.get("endpoints") or base.endpoints),
        scripts=dict(ch.get("scripts") or base.scripts),
        pairs={str(k).upper(): int(v)
               for k, v in (ch.get("pairs") or base.pairs).items()},
        stability_ratio=float(ch.get("stability_ratio", base.stability_ratio)),
        python2=str(ch.get("python2", base.python2)),
        script=str(ch.get("script", "") or ""))
    return cfg
