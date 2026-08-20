"""读侧那几个**参数对象**的定义(时序、台架拓扑、报告位置)。

现在只剩数据类:值由 `common/perf.py` 从 `config.yaml` 翻译过来填进去
(见那边的 `_perf_config`)。以前这里还负责读 `perf.yaml` /
`perf_configs/<型号>.yaml`,那两个文件已经并进 `config.yaml` 并删掉了
(对照表见 docs/MIGRATION.md)。

`matrix/` 是**读侧**:测吞吐(perf_backends / chariot_perf)、等 WAN 拨通
(wanup)、出报告(report)。这次重构没有改它们的逻辑。
"""
from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from typing import Dict, List, Optional

# 换机就得重改一遍,改错了还看不出来(用户 2026-07-31)。


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
