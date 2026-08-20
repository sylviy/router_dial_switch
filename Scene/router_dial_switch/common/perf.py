"""性能测试的**时序** —— 全仓库唯一的一份,外加 config.yaml 的读取与校验。

## 这个文件管什么

一件事:整轮的**节拍**。

    对每个 mode:  switch_fn(mode, cfg) → 等 WAN 拨通 → 稳定 → 测 → 记

节拍里的每个数字(稳定多久、测多久、等拨通等多久、测哪些频段/方向/协议)
**一律取自 config.yaml 的 perf 段,型号脚本覆盖不了**。

理由:切换过程各机不同,可以各写各的;但报告要能**跨机型横向比较**,时序
就必须只有一份。A 机稳定等 15 秒、B 机等 5 秒,两张表放在一起没有意义 ——
而且这种偏差在报告上完全看不出来,只会让人以为 B 机慢。

## 这个文件不管什么

**不管怎么测、怎么出报告**(读侧)。吞吐测量仍然是 matrix/perf_backends.py
(simulate / chariot),报告仍然是 matrix/report.py,等 WAN 拨通仍然是
matrix/wanup.py。这里只按节拍调用它们。

## 顺带管 config.yaml

配置只能在台架现场用记事本改,所以缺项/错项必须在**碰路由器之前**就报错,
并指出改哪个文件的哪一行。这份读取+校验放在这里(而不是 common/ 下的第三个
文件),因为 perf 段本来就是它的管辖范围;型号脚本单跑时也从这里取配置:

    from common import perf
    cfg = perf.load(model="Cudy_AX1500")
    cfg.require("router.ip", "router.pass")     # 缺了当场报错,不开浏览器
"""
from __future__ import annotations

import datetime
import os
import sys
from typing import Dict, List

# 仓库根 / 场景根都靠**向上找标志物**定位,不数目录层级 —— 这个文件搬到哪一层
# 都照跑(Vendor/ 公共库在仓库根,Models/ 在场景根)。
def _up_to(marker):
    d = os.path.dirname(os.path.abspath(__file__))
    while not os.path.isdir(os.path.join(d, marker)):
        parent = os.path.dirname(d)
        if parent == d:
            raise SystemExit("往上找不到 %s/ —— 这个文件被搬出仓库了?" % marker)
        d = parent
    return d


ROOT = _up_to("Vendor")           # 仓库根:Vendor/ 在这一层
SCENE = _up_to("Models")          # 场景根:config.yaml / artifacts / docs 在这一层
# `common` 是**命名空间包**,拼在这两处之上:contract.py / discover.py 在
# Vendor/common/(所有场景共用一把尺子),perf.py 在 <场景>/common/(这个场景
# 专有的时序)。所以 `from common import contract, perf` 一行同时拿到两边。
# 前提:两个 common/ 都**没有 __init__.py**(有了就不再合并;check_model.py 会查)。
for _p in (os.path.join(ROOT, "Vendor"), SCENE):
    if _p not in sys.path:
        sys.path.insert(0, _p)

try:
    import yaml
except Exception:                      # pragma: no cover - yaml 是硬依赖
    yaml = None

CONFIG_PATH = os.path.join(SCENE, "config.yaml")
EXAMPLE_PATH = os.path.join(SCENE, "docs", "config.example.yaml")


# ---------------------------------------------------------------------------
# config.yaml:读取 + 校验(碰路由器之前)
# ---------------------------------------------------------------------------
class ConfigError(SystemExit):
    """配置缺项/错项。继承 SystemExit:入口脚本不用 try,直接把话打给人看。

    消息一律是「config.yaml 第 N 行:X 没填 —— 该填什么」的形状。
    """


def _line_map(text: str) -> Dict[str, int]:
    """把 YAML 原文扫成 {点分键: 行号}。给报错指路用,不是解析器。

    只认最常见的 `缩进 + key:` 写法(config.yaml 就是人手写的这种)。认不出
    的键不会报错,只是拿不到行号,报错里就少一句"第 N 行"。
    """
    out: Dict[str, int] = {}
    stack: List[tuple] = []                 # [(indent, key)]
    for no, raw in enumerate((text or "").splitlines(), 1):
        line = raw.rstrip()
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        indent = len(line) - len(line.lstrip())
        body = line.strip()
        if body.startswith("- ") or ":" not in body:
            continue
        key = body.split(":", 1)[0].strip().strip("'\"")
        if not key:
            continue
        while stack and stack[-1][0] >= indent:
            stack.pop()
        stack.append((indent, key))
        out[".".join(k for _i, k in stack)] = no
    return out


class Cfg(dict):
    """config.yaml 的内容(已套好本型号的覆盖),外加它的出处和行号表。"""

    def __init__(self, data: dict, source: str = "", lines=None,
                 model: str = ""):
        super().__init__(data or {})
        self.source = source
        self.lines = lines or {}
        self.model = model

    # -- 取值 ---------------------------------------------------------------
    def at(self, dotted: str, default=None):
        """按点分路径取值,取不到给 default。`cfg.at("perf.settle_sec")`。"""
        node = self
        for part in dotted.split("."):
            if not isinstance(node, dict) or part not in node:
                return default
            node = node[part]
        return node

    def where(self, dotted: str) -> str:
        """这一项在配置文件的哪一行(说不出就只说文件名)。"""
        no = self.lines.get(dotted)
        name = os.path.basename(self.source or CONFIG_PATH)
        return "%s 第 %d 行" % (name, no) if no else name

    # -- 校验 ---------------------------------------------------------------
    def require(self, *dotted: str) -> None:
        """这几项必须有值,否则**当场报错退出**(还没碰路由器)。

        一次把缺的全报出来 —— 台架上改一项跑一趟、再报下一项,是在烧时间。
        """
        missing = [d for d in dotted if _blank(self.at(d))]
        if not missing:
            return
        raise ConfigError("\n".join(
            ["配置没填全,这一轮没有开始(没有碰路由器):"]
            + ["  * %s:%s 没填 —— %s" % (self.where(d), d, _hint(d))
               for d in missing]
            + ["", "用记事本打开 %s 补上;每一项该填什么见 %s。"
               % (self.source or CONFIG_PATH, os.path.relpath(EXAMPLE_PATH, SCENE))]))


def _blank(value) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return not value.strip() or value.strip() == "FILL_ME"
    if isinstance(value, (list, dict)):
        return len(value) == 0
    return False


# 每一项该填什么。校验报错时直接打给现场的人看,所以写"去哪里找",
# 不写"字段类型是 string"。
_HINTS = {
    "router.ip": "路由器管理页地址,浏览器里打得开的那个,如 192.168.0.1",
    "router.pass": "路由器管理密码(登录 Web UI 用的那个)",
    "router.pppoe_user": "宽带账号,测 pppoe 档要用",
    "router.pppoe_pass": "宽带密码,测 pppoe 档要用",
    "router.pptp.server": "PPTP 服务器地址(台架给的那台)",
    "router.pptp.user": "PPTP 账号(和 L2TP 不是同一个)",
    "router.pptp.pass": "PPTP 密码",
    "router.l2tp.server": "L2TP 服务器地址",
    "router.l2tp.user": "L2TP 账号(和 PPTP 不是同一个)",
    "router.l2tp.pass": "L2TP 密码",
    "bench.python2": "装了 PyChariot 的那个 python 的绝对路径,如 "
                     "C:\\Python26\\python.exe。所有机型测吞吐都用它,"
                     "不是只有 TPLink(确认:该 python -c \"import PyChariot\")",
    "bench.injector_ip": "注入机 IP:接在被测机 LAN 口上、装了 Chariot "
                         "Endpoint 的那台电脑(所有频段共用一台时填它)",
    "bench.injectors": "这个频段的注入机 IP:连在该频段上、装了 Chariot "
                       "Endpoint 的那台电脑",
    "bench.endpoints": "这一档的对端(e2)IP —— 切到这一档之后,Chariot 打哪台",
    "bench.wan_up_hosts": "这一档拨通后 ping 谁算通(直连档和隧道档不在同一网段)",
}


def _hint(dotted: str) -> str:
    """这一项该填什么。按档写的项(bench.endpoints.pppoe)回落到父级说明,
    这样每加一档都不用再补一条提示。"""
    if dotted in _HINTS:
        return _HINTS[dotted]
    parent, _, leaf = dotted.rpartition(".")
    if parent in _HINTS:
        return "%s —— 这一条是 %s 的" % (_HINTS[parent], leaf)
    return ""


def load(path: str = CONFIG_PATH, model: str = "") -> Cfg:
    """读 config.yaml,返回 Cfg。

    **一份全局配置,没有按型号分段。** 台架接线是按**拨号方式**走的 ——
    pppoe 拨通后的对端就是那个隧道网段,换哪台路由器都一样 —— 所以
    bench 段一次配好、七台机共用。换被测机时操作员只改两处:router.ip,
    和 run.dial_modes(这轮测哪几档)。

    model:调用方(--model / 向导里选的)指定的型号,盖过 run.model。它只
    决定驱动哪个型号脚本和报告文件名,不改变任何配置值。

    文件不存在 / 读不动 = 当场报错。**不静默回落到默认值** —— 那样只会让
    一轮拿着一堆默认 IP 在台架上跑,最后给出一份打错了口的报告。
    """
    if yaml is None:
        raise ConfigError("没有 PyYAML,读不了 config.yaml。"
                          "台架上用 Vendor/python 那个解释器跑(它自带)。")
    if not os.path.exists(path):
        raise ConfigError(
            "找不到 %s。把 %s 复制成 config.yaml,用记事本按里面的中文注释"
            "填一遍。" % (path, os.path.relpath(EXAMPLE_PATH, SCENE)))
    with open(path, "r", encoding="utf-8") as fh:
        text = fh.read()
    try:
        data = yaml.safe_load(text) or {}
    except Exception as exc:
        raise ConfigError("%s 读不了(YAML 语法错):%s\n"
                          "多半是缩进用了 Tab、或中文冒号。" % (path, exc))
    if not isinstance(data, dict):
        raise ConfigError("%s 的内容不是一组 `键: 值`。" % path)

    model = model or str(data.get("run", {}).get("model") or "")
    return Cfg(data, source=path, lines=_line_map(text), model=model)


# ---------------------------------------------------------------------------
# 时序:一轮 = 逐档(切 → 等 WAN → 稳定 → 测 → 记)
# ---------------------------------------------------------------------------
def _perf_config(cfg: Cfg):
    """把 config.yaml 翻成读侧(matrix/)认的那几个对象。

    读侧一个字没动:测量仍是 matrix/perf_backends.py,报告仍是
    matrix/report.py。这里只是把新配置接到它们的老接口上。
    """
    from matrix import config as perf_config

    perf = cfg.get("perf") or {}
    bench = cfg.get("bench") or {}
    run = cfg.get("run") or {}
    report = cfg.get("report") or {}

    # 注入机(e1):按频段。injectors 里没写到的频段回落到单台的 injector_ip;
    # 两个都没有的频段就是**没有注入机** —— 由 run() 在开跑前拦住,不猜。
    # (以前这里空着会回落到代码里写死的历史 IP,那等于拿一个来路不明的地址
    #  测出一份看起来很正常的报告。)
    injectors = {str(k): str(v) for k, v in (bench.get("injectors") or {}).items()
                 if str(v or "").strip() and str(v).strip() != "FILL_ME"}
    if str(bench.get("injector_ip") or "").strip():
        for band in perf.get("bands") or ["lan"]:
            injectors.setdefault(str(band), str(bench["injector_ip"]).strip())

    pc = perf_config.PerfConfig()
    pc.model = cfg.model
    pc.backend = str(run.get("backend") or "simulate").lower()
    pc.bands = [str(b) for b in (perf.get("bands") or ["lan"])]
    pc.directions = [str(d) for d in (perf.get("directions") or ["up", "down", "bi"])]
    pc.protocols = [str(p).upper() for p in (perf.get("protocols") or ["TCP"])]
    pc.report_dir = str(report.get("dir") or "artifacts")
    pc.report_title = str(report.get("title") or "WAN Performance Matrix")
    pc.reset_mode = run.get("reset_mode") or None
    pc.source = cfg.source

    pc.wan_up = perf_config.WanUpCfg(
        method=str(bench.get("wan_up_method") or "ping"),
        host=str(bench.get("wan_up_host") or ""),
        hosts={str(k): str(v) for k, v in (bench.get("wan_up_hosts") or {}).items()},
        # 时序参数只从 perf 段来 —— bench 段里写不了,型号脚本更覆盖不了。
        timeout_s=int(perf.get("wan_up_timeout_sec", 60)),
        settle_s=int(perf.get("settle_sec", 15)))

    base = perf_config.ChariotCfg()
    pc.chariot = perf_config.ChariotCfg(
        duration_s=int(perf.get("duration_sec", 20)),
        internet_ip=str(bench.get("internet_ip") or base.internet_ip),
        public_ip=str(bench.get("public_ip") or base.public_ip),
        e2_ip={str(k): str(v) for k, v in (bench.get("endpoints") or {}).items()},
        endpoints=injectors,
        scripts=dict(bench.get("scripts") or base.scripts),
        pairs={str(k).upper(): int(v)
               for k, v in (bench.get("pairs") or base.pairs).items()},
        nofrag_bytes={str(k): int(v)
                      for k, v in (bench.get("nofrag_bytes") or {}).items()},
        stability_ratio=float(bench.get("stability_ratio", base.stability_ratio)),
        save_tests=bool(bench.get("save_tests", base.save_tests)),
        python=str(bench.get("python2") or ""),
        script=str(bench.get("chariot_script") or ""))
    return pc


def run(switch_fn, modes, cfg: Cfg, log=print) -> dict:
    """跑完一轮:逐档 切 → 等 WAN 拨通 → 稳定 → 测 → 记,最后出报告。

    switch_fn(mode, cfg) -> contract.result(...) 的那个字典。切换失败的档
    **不测吞吐**:那一格记成 error,继续下一档(一台机坏一档不该拖垮整轮)。

    modes:要跑哪几档。run.dial_modes 写了就以它为准,没写 = 传进来的全部。
    返回 {"rows", "switch", "paths", "ok"}。
    """
    from matrix import report as report_mod
    from matrix.perf_backends import make_backend
    from matrix.wanup import wait_wan_up

    pc = _perf_config(cfg)
    wanted = [str(m) for m in (cfg.at("run.dial_modes") or [])] or list(modes)
    unknown = [m for m in wanted if m not in modes]
    if unknown:
        # 配置里写了这台机切不了的档。**开跑前就拦住**,别等整轮跑到那一档
        # 才发现 —— 台架时间稀缺,而且默认的 dial_modes 是四种常见拨号方式,
        # 遇上只支持其中两种的机器(Tenda 的 v4 列表没有 PPTP/L2TP)必然撞上。
        # 措辞里**不带型号名**:能切哪几档是型号脚本的 MODES 说了算,而型号名
        # 来自 config.yaml 的 run.model —— 万一两者对不上(调用方传了另一台机
        # 的 MODES),带上型号名就会指着 A 机说 B 机的档,把人往错路上带。
        raise ConfigError(
            "这一轮没有开始(没有碰路由器):\n"
            "  %s:run.dial_modes 里有几档是这台机切不了的 —— %s\n"
            "  这台机支持:%s\n\n"
            "用记事本打开 %s,把上面那几档从 run.dial_modes 里删掉。"
            % (cfg.where("run.dial_modes"), ", ".join(unknown),
               ", ".join(modes), cfg.source or CONFIG_PATH))

    if pc.backend == "chariot":
        # 每个频段都得有自己的注入机。**对不上号的频段以前会悄悄改用 lan
        # 那台** —— 于是测的是有线,报告上却写着 5GHz,数字还很正常。
        blind = [b for b in pc.bands if not pc.chariot.endpoints.get(b)]
        if blind:
            raise ConfigError(
                "这一轮没有开始(没有碰路由器):\n"
                + "\n".join(
                    "  %s:%s 频段没有注入机 —— 填 bench.injectors.%s"
                    "(接在被测机 %s 上、装了 Chariot Endpoint 的那台电脑的 IP)"
                    % (cfg.where("bench.injectors.%s" % b), b, b,
                       "LAN 口" if b == "lan" else "%s 无线" % b)
                    for b in blind)
                + "\n\n所有频段共用一台就填 bench.injector_ip。"
                  "频段名要和 perf.bands 里写的一模一样(大小写也是)。")
        # lan 和无线共用一个 IP 基本是填错了(一台机的有线和无线是两个地址);
        # 2GHz 和 5GHz 共用是正常的 —— 同一块网卡换 SSID 连。
        lan_ip = pc.chariot.endpoints.get("lan")
        same = [b for b in pc.bands
                if b != "lan" and lan_ip and pc.chariot.endpoints.get(b) == lan_ip]
        if same:
            log("[!] %s 和 lan 用的是同一台注入机(%s)—— 确认一下不是填错:"
                "同一台电脑的有线和无线是两个不同的地址,写成一个的话这几个"
                "频段测的其实是同一条路。" % ("/".join(same), lan_ip))

    backend = make_backend(pc)
    problem = backend.preflight()
    if problem:
        raise ConfigError("性能后端 %s 还不能用,整轮不开始:\n  %s"
                          % (pc.backend, problem))

    stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    # 报告和这一轮的 .tst 原始记录都归到 artifacts/reports/
    out_dir = (pc.report_dir if os.path.isabs(pc.report_dir)
               else os.path.join(SCENE, pc.report_dir))
    out_dir = os.path.join(out_dir, "reports")
    if pc.chariot.save_tests:
        pc.chariot.tst_dir = os.path.join(
            out_dir, "wanperf_%s_%s_tst"
            % (report_mod.report_slug(pc.model), stamp))

    rows: List[dict] = []
    switch_log: List[dict] = []

    for mode in wanted:
        log("\n=== 切到 %s ===" % mode)
        res = switch_fn(mode, cfg)
        switched = bool(res.get("success"))
        read_back = res.get("read_back") or ""
        message = res.get("message") or ""
        for w in res.get("warnings") or []:
            message = (message + " | " + w) if message else w
        log("    切换 %s  回读=%r%s"
            % ("OK" if switched else "FAIL", read_back,
               "  已保存" if res.get("applied") else ""))
        switch_log.append({"mode": mode, "switched": switched,
                           "read_back": read_back, "message": message})
        if not switched:
            log("    [X] 切换失败,跳过该档的吞吐测量。"
                + ("  %s" % message if message else ""))
            rows.append({"mode": mode, "switched": False, "read_back": read_back,
                         "band": "", "direction": "", "proto": "",
                         "mbps": None, "stable": None,
                         "error": message or "switch failed"})
            continue

        # 等 WAN 拨通 + 稳定。两个数字都只从 perf 段来(见 _perf_config)。
        wait_wan_up(pc.wan_up, mode, log=log)

        for band in pc.bands:
            for proto in pc.protocols:
                for direction in pc.directions:
                    m = backend.measure(mode, band, direction, proto)
                    log("    %-4s %-4s %-3s  %s Mbps%s"
                        % (band, direction, proto,
                           "err" if m.error else ("%.1f" % m.mbps
                                                  + ("" if m.stable else " !")),
                           "  " + m.error if m.error else ""))
                    rows.append({"mode": mode, "switched": True,
                                 "read_back": read_back, "band": band,
                                 "direction": direction, "proto": proto,
                                 "mbps": m.mbps, "stable": m.stable,
                                 "error": m.error})

    if pc.reset_mode:
        log("\n=== 收尾:切回 %s ===" % pc.reset_mode)
        try:
            switch_fn(pc.reset_mode, cfg)
        except Exception as exc:                # 收尾出错不该改写这一轮的结论
            log("    收尾切换出错(忽略):%s" % exc)

    ctx = {"title": pc.report_title, "model": pc.model, "backend": pc.backend,
           "timestamp": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
           "bands": pc.bands, "directions": pc.directions,
           "protocols": pc.protocols, "rows": rows, "switch": switch_log}
    paths = report_mod.write_reports(ctx, out_dir, stamp=stamp)

    log("\n===== 汇总 =====")
    for s in switch_log:
        log("  %-22s 切换=%s" % (s["mode"], "OK" if s["switched"] else "FAIL"))
    log("\n报告已生成:\n  HTML: %s\n  CSV : %s" % (paths["html"], paths["csv"]))
    return {"rows": rows, "switch": switch_log, "paths": paths,
            "ok": all(s["switched"] for s in switch_log)}
