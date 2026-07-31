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
import sys
from dataclasses import dataclass, field
from typing import Dict, List, Optional

try:
    import yaml
except Exception:  # pragma: no cover - yaml 是硬依赖,这里只是防御
    yaml = None

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_PATH = os.path.join(ROOT, "perf.yaml")
EXAMPLE_PATH = os.path.join(ROOT, "perf.example.yaml")
# 每台机一份参数:perf_configs/<型号脚本名>.yaml。选了型号就自动用它,
# 不用再复制/改一个全局 perf.yaml —— 台架上有六台机,一个全局文件意味着
# 换机就得重改一遍,改错了还看不出来(用户 2026-07-31)。
CONFIG_DIR = os.path.join(ROOT, "perf_configs")
TEMPLATE_PATH = os.path.join(CONFIG_DIR, "_template.yaml")


@dataclass
class DialStep:
    """矩阵里的一档拨号方式:mode 必须是该型号脚本声明过的模式;
    params 是切它需要的账密/服务器(会传给 _driver.run)。"""
    mode: str
    params: Dict[str, str] = field(default_factory=dict)


@dataclass
class WanUpCfg:
    """切完模式后等 WAN 拨通的判据。method=ping 就 ping host 到通为止,
    否则只做固定等待。拨通后再多等 settle_s 秒让链路稳定(旧脚本睡 15s)。

    `hosts` 是按拨号方式覆盖 `host`。台架上直连段和隧道段是**两个不同网段**
    (2026-07-28 实测:dynamic 打 192.168.202.99,pppoe 走隧道后要打
    192.168.203.1),单一个全局 host 必然有几档 ping 不通 —— 那几档不会失败,
    但会白等满 timeout_s 再测,一档浪费一分钟。
    """
    method: str = "wait"          # ping | wait
    host: str = ""
    hosts: Dict[str, str] = field(default_factory=dict)   # 模式 -> 地址
    timeout_s: int = 60
    settle_s: int = 15

    def host_for(self, mode):
        """该模式该 ping 谁:先看 hosts 里的按模式覆盖,再退回全局 host。"""
        return (self.hosts or {}).get(mode) or self.host


@dataclass
class ChariotCfg:
    """Chariot 后端参数,逐项对应旧 Dial.py 里的常量(仅台架用,离线模拟忽略)。"""
    duration_s: int = 20
    internet_ip: str = "192.168.203.1"
    public_ip: str = "192.168.202.99"
    # 按拨号方式**显式指定**对端(e2)。不写的模式才回落到"动态/静态走
    # public_ip,其余走 internet_ip"那条从名字猜路的老规则 —— 而日本 IPoE
    # 四档(transix/v6plus/ocnvc/v6connect)会被那条规则猜成隧道档,打错口
    # 却照样出一份漂亮数字。见 chariot_perf._e2_ip 的注释。
    e2_ip: Dict[str, str] = field(default_factory=dict)
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
    # 不分片档(协议写成 UDP-nofrag)要设的 send_buffer_size,按拨号方式取 ——
    # 它是各自封装开销算出来的 MTU。没配的模式会明确报错,不猜。
    nofrag_bytes: Dict[str, int] = field(default_factory=dict)
    stability_ratio: float = 0.9   # min < ratio*max 即判为"不稳"
    save_tests: bool = True        # 是否保留 Chariot 的 .tst 原始记录
    tst_dir: str = ""              # 运行时由 run.py 填(每轮一个目录)
    # 跑 chariot_perf.py 的解释器。**留空 = 用跑本工具的这个解释器**
    # (Python 3 的 Chariot 台架:PyChariot 就装在同一个 python 里,不用配)。
    # 老台架的 PyChariot 只在 Python 2 里(ActivePython 2.6.5),那里必须写
    # 绝对路径,如 C:\Python26\python.exe —— 那台机上 Playwright 要 3.8,
    # 两个 python 世界只能靠子进程隔开。旧键名 python2: 仍然认。
    python: str = ""
    script: str = ""               # chariot_perf.py 路径(默认取包内同目录)

    @property
    def interpreter(self) -> str:
        """真正会被执行的解释器路径。没配就是当前解释器。

        默认值曾经是裸的 "python",它跟着 PATH 走 —— 在 Python 2 台架上
        PATH 上那个正好**是** Python 2,于是配错了也能跑通,直到某天 PATH
        变了才炸;在 Python 3 台架上它又可能落到一个没装 PyChariot 的
        python 上。用 sys.executable 兜底至少是确定的:要么就是本工具这个
        python,要么就是你显式写的那个。"""
        return self.python or sys.executable


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
    source: str = ""                   # 实际读的是哪个文件(开跑前检查会打出来)


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


def path_for_model(model: str) -> str:
    """这台机的参数文件路径(可能还不存在)。"""
    return os.path.join(CONFIG_DIR, "%s.yaml" % model)


def resolve_path(path: str = DEFAULT_PATH, model: str = "") -> str:
    """决定这一轮**实际读哪个文件**,并把它记在 PerfConfig.source 上。

    优先级(从高到低):
      1. --config 显式给的路径 —— 说了算,不再猜;
      2. perf_configs/<型号>.yaml —— 每台机一份,选了型号就自动用它;
      3. perf.yaml —— 老的全局配置,已经配好的台架不用动;
      4. perf.example.yaml —— 谁都没有时的示例(会被开跑前检查警告)。
    """
    if path and path != DEFAULT_PATH:
        return path
    if model:
        per_model = path_for_model(model)
        if os.path.exists(per_model):
            return per_model
    if os.path.exists(DEFAULT_PATH):
        return DEFAULT_PATH
    return EXAMPLE_PATH


def load(path: str = DEFAULT_PATH, model: str = "") -> PerfConfig:
    """读参数文件 -> PerfConfig。缺失/为空 -> 全默认(仍可 --demo 跑通)。

    model 给了就优先用 perf_configs/<model>.yaml(见 resolve_path)。
    """
    path = resolve_path(path, model)
    data: dict = {}
    if yaml is not None and os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as fh:
                data = yaml.safe_load(fh) or {}
        except Exception:
            data = {}
    if not isinstance(data, dict):
        data = {}

    cfg = PerfConfig()
    cfg.source = path
    # 型号:调用方给的(--model / 向导里选的)优先,它决定了读哪个文件;
    # 没给才用文件里写的。
    cfg.model = model or str(data.get("model", "") or "")
    cfg.backend = str(data.get("backend", cfg.backend) or cfg.backend).lower()
    # dial_modes 不写 = 留空,由 run.py 用"该型号声明的全部模式"补齐
    # (工具的本意:跑一次遍历所有支持的拨号方式)。--demo 无型号时才用
    # _DEFAULT_MATRIX。
    cfg.dial_modes = _dial_steps(data.get("dial_modes"))
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
                          hosts=dict((str(k), str(v)) for k, v
                                     in (wu.get("hosts") or {}).items()),
                          timeout_s=int(wu.get("timeout_s", cfg.wan_up.timeout_s)),
                          settle_s=int(wu.get("settle_s", cfg.wan_up.settle_s)))

    ch = data.get("chariot") or {}
    base = ChariotCfg()
    cfg.chariot = ChariotCfg(
        duration_s=int(ch.get("duration_s", base.duration_s)),
        internet_ip=str(ch.get("internet_ip", base.internet_ip)),
        public_ip=str(ch.get("public_ip", base.public_ip)),
        e2_ip=dict((str(k), str(v))
                   for k, v in (ch.get("e2_ip") or {}).items()),
        endpoints=dict(ch.get("endpoints") or base.endpoints),
        scripts=dict(ch.get("scripts") or base.scripts),
        pairs={str(k).upper(): int(v)
               for k, v in (ch.get("pairs") or base.pairs).items()},
        nofrag_bytes={str(k): int(v)
                      for k, v in (ch.get("nofrag_bytes") or {}).items()},
        stability_ratio=float(ch.get("stability_ratio", base.stability_ratio)),
        save_tests=bool(ch.get("save_tests", base.save_tests)),
        # python2: 是 2026-07 之前的键名(那时只有 Py2 台架)。仍然认它,
        # 免得已经配好的台架升级后突然回到"跟着 PATH 走"。
        python=str(ch.get("python", ch.get("python2", base.python)) or ""),
        script=str(ch.get("script", "") or ""))
    return cfg
