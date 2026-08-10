"""开跑前检查:这台机的参数配对了没,配错了会怎样,该去改哪一行。

为什么要有:整轮要几十分钟,而且**每一档都会真正切一次路由器的拨号方式**。
参数配错的典型下场不是报错,是:
  * 打错了对端口 —— 数字照样出得来,只是测的不是那条路(最难发现的一种);
  * `wan_up` 没配这一档的 host —— 每档白等满 timeout 再测;
  * 账密缺一个 —— 整轮把路由器切成一个空账号的 PPPoE,WAN 直接断。
所以宁可开跑前一秒钟就说清楚,而不是半小时后拿到一份"看起来正常"的报告。

分三级:
  X  错误 —— 会挡住这一轮(或者一定测出错的数),必须改;
  !  警告 —— 能跑,但结果或耗时会不对劲,你得知道;
  i  信息 —— 把工具**实际解析出来的结果**摊开给人看(尤其是每一档打谁),
     让人用眼睛过一遍。这一条比前两条更重要:检查器只能发现"没填",
     发现不了"填成了另一个真实存在的 IP"。
"""
from __future__ import annotations

import os
import re
from typing import List, NamedTuple

from matrix import config as perf_config

# 模板里没改的占位值。填了真 IP 才算配好 —— 留着占位值跑,Chariot 会连不上
# 那台机,一整轮全是 err。
_PLACEHOLDER = re.compile(r"FILL_ME|_HERE\b|x\.x\.x\.x|TODO|<[^>]*>")


class Finding(NamedTuple):
    level: str          # "X" | "!" | "i"
    msg: str
    fix: str = ""       # 该怎么改(人话,带文件名和键名)

    @property
    def blocking(self) -> bool:
        return self.level == "X"


def _placeholder(value) -> bool:
    return bool(_PLACEHOLDER.search(str(value or "")))


def check(cfg, facts: dict, modes: List[str]) -> List[Finding]:
    """cfg=PerfConfig,facts=型号脚本的 FACTS,modes=这一轮实际要跑的档。"""
    out: List[Finding] = []
    rel = os.path.relpath(cfg.source or "", perf_config.ROOT) or "(默认值)"
    out.append(Finding("i", "参数文件:%s" % rel))

    if not os.path.exists(cfg.source or ""):
        out.append(Finding(
            "!", "没有参数文件,这一轮全走内置默认值 —— 台架拓扑几乎肯定不对",
            "跑 `python start.py` 选这台机时会问你要不要生成 "
            "perf_configs/%s.yaml(模板 perf_configs/_template.yaml),"
            "生成后把 IP 改成你台架的。" % (cfg.model or "<型号>")))

    # --- 拨号方式 ---------------------------------------------------------
    declared = set((facts.get("modes") or {}).keys())
    declared.update((facts.get("mode_overrides") or {}).keys())
    unknown = [m for m in modes if m not in declared]
    if unknown:
        out.append(Finding(
            "X", "这些档 models/%s.py 没声明:%s"
                 % (cfg.model, ", ".join(unknown)),
            "改 %s 的 dial_modes:,只写这台机支持的档(它支持:%s)"
            % (rel, ", ".join(sorted(declared)))))
    if not modes:
        out.append(Finding("X", "一档拨号方式都没有,这一轮没东西可跑",
                           "删掉 %s 里的 dial_modes: 就是跑全部档" % rel))

    # --- 频段 → 注入机 ----------------------------------------------------
    for band in cfg.bands:
        ip = (cfg.chariot.endpoints or {}).get(band)
        if not ip:
            out.append(Finding(
                "X", "频段 %s 没有对应的注入机(e1)" % band,
                "在 %s 的 chariot.endpoints 里加一行 %s: <那台电脑的 IP>"
                % (rel, band)))
        elif _placeholder(ip):
            out.append(Finding(
                "X", "频段 %s 的注入机还是占位值 %r" % (band, ip),
                "改成 %s 那台装了 Chariot Endpoint 的电脑的真实 IP(%s 的 "
                "chariot.endpoints.%s)" % (band, rel, band)))

    # --- 每档:对端、拨通判据、账密 ---------------------------------------
    from modes import MODE_REQUIRED_FIELDS, merge_params
    import settings as settings_mod
    saved = settings_mod.load()
    from matrix.chariot_perf import _e2_ip, _e2_source
    topo = {"public_ip": cfg.chariot.public_ip,
            "internet_ip": cfg.chariot.internet_ip,
            "e2_ip": cfg.chariot.e2_ip}
    explicit = {s.mode: s.params for s in cfg.dial_modes}

    nofrag = [p for p in cfg.protocols if p.upper().endswith("-NOFRAG")]

    for mode in modes:
        # 对端:把解析结果摊开。检查器分辨不出"填成了另一个真 IP",人能。
        e2 = _e2_ip(topo, mode)
        out.append(Finding("i", "  %-10s 对端(e2)= %-15s  <- %s"
                                % (mode, e2, _e2_source(topo, mode))))
        if _placeholder(e2):
            out.append(Finding("X", "  %s 的对端还是占位值 %r" % (mode, e2),
                               "改 %s 的 chariot.public_ip / internet_ip / "
                               "e2_ip" % rel))

        # 拨通判据
        if cfg.wan_up.method == "ping" and not cfg.wan_up.host_for(mode):
            out.append(Finding(
                "!", "  %s 没配 wan_up 的 ping 目标" % mode,
                "在 %s 的 wan_up.hosts 里加 %s: <这一档拨通后打得通的地址>;"
                "不加不会失败,但每档要白等满 %d 秒才开测"
                % (rel, mode, cfg.wan_up.timeout_s)))

        # 账密:整轮**必定下发**,缺参数等于拿空账号覆盖掉现有配置
        params = merge_params(mode, saved.get("params") or {},
                              explicit.get(mode) or {})
        missing = [f for f in MODE_REQUIRED_FIELDS.get(mode, [])
                   if not params.get(f)]
        if missing:
            out.append(Finding(
                "X", "  %s 缺参数:%s" % (mode, ", ".join(missing)),
                "存进 router.yaml(start.bat 菜单 4),或写在 %s 的 "
                "dial_modes[].params 里。整轮是必定下发的,空账号会把 WAN 切断。"
                % rel))
        elif not MODE_REQUIRED_FIELDS.get(mode) and mode == "static":
            out.append(Finding(
                "!", "  static 这一档没有任何地址可填",
                "modes.py 还没有 static 的字段映射,这一档会切成静态 IP 却不填"
                "地址 —— 从 %s 的 dial_modes 里去掉它" % rel))

        # 账密框不在拨号页上的机型(Buffalo 的 PPPoE 在 pppoe_reg.html)
        if params and facts.get("fields_page"):
            out.append(Finding(
                "!", "  %s 的账密框在 %s,脚本不去那页" % (mode,
                                                       facts["fields_page"]),
                "先在路由器 Web UI 的 %s 里把账号建好,再跑这一轮"
                % facts["fields_page"]))

        # 不分片档要 MTU
        if nofrag and mode not in (cfg.chariot.nofrag_bytes or {}):
            out.append(Finding(
                "X", "  %s 没配不分片的 send_buffer_size(协议里有 %s)"
                     % (mode, ", ".join(nofrag)),
                "在 %s 的 chariot.nofrag_bytes 里加 %s: <该档的 MTU>;"
                "不配会直接报错而不是瞎猜 —— 猜错的话流量照跑、数字照出,"
                "其实分了片" % (rel, mode)))

    # --- 规模提醒 ---------------------------------------------------------
    cells = len(modes) * len(cfg.bands) * len(cfg.protocols) * len(cfg.directions)
    minutes = cells * cfg.chariot.duration_s / 60.0
    out.append(Finding(
        "i", "规模:%d 档 × %d 频段 × %d 协议 × %d 方向 = %d 格,"
             "光测量约 %.0f 分钟(不含切换和等拨通)"
             % (len(modes), len(cfg.bands), len(cfg.protocols),
                len(cfg.directions), cells, minutes)))
    if len(cfg.bands) > 1:
        out.append(Finding(
            "!", "选了 %d 个频段,但**换频段不会自动换客户端**" % len(cfg.bands),
            "chariot.endpoints 里每个频段得是**各自那台**已经连在该频段上的"
            "注入机;同一个 IP 写两遍等于测了两遍同一条路"))

    return out


def format_report(findings: List[Finding], color=lambda s, c: s) -> str:
    """排成人看的样子:信息在前(摊开事实),然后警告,最后错误 + 怎么改。"""
    lines = []
    for f in findings:
        if f.level == "i":
            lines.append("  " + f.msg)
    warns = [f for f in findings if f.level == "!"]
    errs = [f for f in findings if f.level == "X"]
    for f in warns:
        lines.append("  [!] " + f.msg)
        if f.fix:
            lines.append("      -> " + f.fix)
    for f in errs:
        lines.append("  [X] " + f.msg)
        if f.fix:
            lines.append("      -> " + f.fix)
    if not warns and not errs:
        lines.append("  [OK] 没发现问题。")
    return "\n".join(lines)


def blocking(findings: List[Finding]) -> List[Finding]:
    return [f for f in findings if f.blocking]
