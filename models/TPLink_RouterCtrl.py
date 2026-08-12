"""自家样机(TP-Link)—— 走 RouterCtrl,**不开浏览器**。

**一个文件管所有自家样机**,不是一台机一个:自家机器有内部库 `RouterCtrl`,
切档靠它的 HTTP API,而那套 API 各型号是一样的。所以这里的"事实"不是选择器,
是**模式名和回读串**;具体是哪台样机由运行时决定 —— IP 和密码在 config.yaml,
报告里的型号名取自 `get_wan_info()['hostName']`(台架那台回的是
`ArcherAX1800`),**没有写死**。

## 它和别的型号脚本哪里不一样

`RouterCtrl` 只装在台架那个 Python 2(ActivePython 2.6.5)里,py3 侧 import
不了。所以中间隔一个子进程:`tools/routerctrl_bridge.py`(**py2.6 语法,别用
py3 写法去"现代化"它**)负责下发 + 回读,只从 stdout 吐一行 JSON。本文件是
那条边界的 py3 这一侧。

跑它的 py2 解释器取自 config.yaml 的 `bench.python2` —— 台架已经为 Chariot
配好了那一行,**不再开第二处**。没配就明确报错说该填哪。

## 三条和别的机型不同的规矩(都在下面写死了)

  * **没有"只看不切"。** 别的机型不加 --apply 时只是选中控件、不点保存;这条
    路线一调用桥接就**真的下发了**,没有"预览"这种状态。所以不加 --apply 时
    它什么都不做,直接如实失败 —— 而不是假装看过一眼。
  * **回读和桥接必须都同意才算成功。** 桥接除了比对 wan_type,还查 WAN 有没有
    真拿到地址(空 / 0.0.0.0 都算没拨上)。少查一条就会出现"类型对了、其实
    没拨上"的绿格子。
  * **档名和别的六台机对齐**(dynamic / pppoe / pptp / l2tp),这样一份全局的
    run.dial_modes 七台机通用。桥接自己那套复合名(`pptp_dynamic_internet`
    这种)一个字符都没改 —— 翻译在下面的 BRIDGE_MODE 里,只发生在 py3 这一侧。

单跑:

    python models/TPLink_RouterCtrl.py dynamic --apply
    python models/TPLink_RouterCtrl.py pptp --apply

--------------------------------------------------------------------------
## 这个文件怎么读

从上往下就是台架上会发生的事:

    FACTS / MODES / NEEDS   纯数据:模式名 -> 回读串、每档要哪些账密
    switch()                主角。查配置 → 调桥接 → 比对回读 → 出结果
    main()                  命令行

自足:除了 common/contract.py(判定)和 common/perf.py(整轮节拍 +
读 config.yaml),不依赖仓库里任何别的代码。
"""
import argparse
import json
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from common import contract, perf

FACTS = {
    "brand": "TPLink",
    # 这个文件不绑定某一台样机。运行时会用 get_wan_info()['hostName'] 覆盖
    # 报告里的型号(台架那台是 ArcherAX1800)。
    "model": "RouterCtrl",
    "route": "bridge",                          # 不开浏览器,走 py2 桥接
    "bridge": "tools/routerctrl_bridge.py",
    # 档名和别的六台机对齐(2026-08-12 用户定):PPTP/L2TP 就是一档隧道拨号,
    # 不再拆 _internet / _public 两份。那两个后缀对**下发没有任何影响**
    # (桥接里同一支 elif 收下它们),只决定 Chariot 打哪个远端 —— 而那个现在
    # 由 config.yaml 的 bench.endpoints.<档> 说了算,隧道档统一打 203.1。
    # 值是 get_wan_info()['wan_type'] 的**回读串**,不是界面措辞。
    "modes": {
        "dynamic": "Dynamic IP",
        "static": "Static IP",
        "pppoe": "PPPoE",                       # 无第二连接
        "pptp": "PPTP",
        "l2tp": "L2TP",
    },
    # 下发后等多久再回读。老脚本(dial_perf.py)给 dynamic 的是 30+15=45 秒、
    # 其余 15 秒;这里统一 20 秒,dynamic 按老口径单独给 45 —— DHCP 拿地址是
    # 这几档里最慢的,等不够会读到空的 wan_ip,那会被判成"没拨上"。
    "bridge_settle": 20,
    "mode_overrides": {
        "dynamic": {"bridge_settle": 45},
    },
}

# 这台机能切哪几档 —— 和别的六台机同一套档名。
# static 故意不列:切过去会是静态 IP 且不填任何地址(要测请手动单跑)。
MODES = ["dynamic", "pppoe", "pptp", "l2tp"]

# 每档要 config.yaml 里的哪几项 -> 填进哪个概念(概念名和桥接的 --param 键
# 一一对应)。**碰路由器之前**核对:桥接一调用就真下发了,缺账密再去调用,
# 等于拿桥接自己的历史默认账号拨上去 —— 报告照样绿,测的却不是你配的账号。
NEEDS = {
    "dynamic": {},
    "pppoe": {"pppoe_user": "router.pppoe_user",
              "pppoe_pass": "router.pppoe_pass"},
    "pptp": {"vpn_server": "router.pptp.server", "vpn_user": "router.pptp.user",
             "vpn_pass": "router.pptp.pass"},
    "l2tp": {"vpn_server": "router.l2tp.server", "vpn_user": "router.l2tp.user",
             "vpn_pass": "router.l2tp.pass"},
}

# 上面这套档名 -> 桥接认的档名。**桥接只认复合名**(它的 MODES 里根本没有裸的
# pptp/l2tp,传裸名会被当用法错误挡掉,退出码 3),而复合名的两个后缀是:
#   <家族>_<第二连接>_<对端>
# 台架上只有"第二连接为动态"这一种接线,所以第二段固定 dynamic;第三段
# (internet/public)对**下发没有任何影响** —— 桥接里同一支 elif 收下它们 ——
# 只决定 Chariot 打哪个远端,而那个现在由 config.yaml 的 bench.endpoints.<档>
# 说了算。所以这里各留一个就够,报告里的档名和别的机型对得上。
#
# **桥接文件一个字没动**(它是 py2.6),翻译只发生在这一侧。
BRIDGE_MODE = {
    "dynamic": "dynamic",
    "static": "static",
    "pppoe": "pppoe",                       # 无第二连接
    "pptp": "pptp_dynamic_internet",
    "l2tp": "l2tp_dynamic_internet",
}

BRIDGE = "tools/routerctrl_bridge.py"

_PY2_HINT = """没配 py2 解释器,桥接跑不起来(RouterCtrl 只装在台架那个
Python 2.6.5 里)。在 %s 里填这一行:

  bench:
    python2: C:\\Python26\\python.exe

那是台架上装了 PyChariot / RouterCtrl 的那个 python 的绝对路径。**只配这一处**
—— 整轮跑 Chariot 用的也是它。确认:该 python -c "import RouterCtrl" """


def _host_only(text):
    """从 IP 或 URL 里取出主机部分 —— 桥接的 --ip 要的是地址,不是 URL。"""
    text = (text or "").strip()
    for prefix in ("http://", "https://"):
        if text.lower().startswith(prefix):
            text = text[len(prefix):]
    return text.split("/")[0].split(":")[0].strip()


def _host_name(detail):
    """样机自己报的型号(get_wan_info()['hostName'],台架实测 ArcherAX1800)。"""
    if not isinstance(detail, dict):
        return ""
    for key in detail:
        if str(key).replace("_", "").lower() == "hostname":
            return str(detail[key] or "").strip()
    return ""


def _last_json(text):
    """从后往前找第一段能解析成 JSON 对象的片段。

    不能直接取最后一行:台架上 stdout 可能混进别的库打的日志行,而且 Chariot
    那类原生库写 stdout 时**末尾没有换行**,我们这行 JSON 会被接在它后面。
    所以每一行都从任意 `{` 开始试着解析,并容忍后面还有别的字符。
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


# ---------------------------------------------------------------------------
# 切换:查配置 → 调桥接(它自己下发 + 回读)→ 比对回读
# ---------------------------------------------------------------------------
def switch(mode, cfg, hook=None):
    """把这台样机的 WAN 拨号方式切成 mode,返回 contract.result(...)。

    不开浏览器:下发和回读都由 py2 侧的桥接完成,这里只负责查配置、调它、
    比对回读。hook 参数只为和别的型号脚本同形,这条路线没有页面可看。
    """
    label = (FACTS.get("modes") or {}).get(mode, "")
    ident = {"brand": FACTS["brand"], "model": FACTS["model"], "mode": mode}
    warnings = []

    def done(read_back, message="", applied=False, model="", bridge_ok=True):
        """这个函数唯一的出口。**两道关都过了才算成功:**

          ① 回读 —— 桥接读回的 wan_type 精确等于目标串(contract.verify);
          ② 桥接自己的判定 —— 它看得比回读串多,还查 WAN 有没有真拿到地址
             (空 / 0.0.0.0 都算没拨上)。

        少查第二条就会出现"**类型对了、其实没拨上**"的绿格子:wan_type 明明
        写着 PPTP、回读也对得上,可这一档根本没连上,吞吐照测、报告照绿。
        桥接说不行时这里传 bridge_ok=False,success 直接判负 —— contract 只
        接受字面量 False 这一种"不用回读就判负"的写法,伪造不出成功。
        """
        verdict = contract.verify(read_back, label) if bridge_ok else False
        res = contract.result(verdict, read_back, label, message=message,
                              applied=applied, warnings=warnings, **ident)
        if model:
            # **只改 model 这一个报告字段**(换成样机自己报的 hostName)。
            # success / read_back 一律由上面那行算出来 —— 在这里补第二次赋值
            # 就等于绕开回读判定。
            res["model"] = model
        return res

    # --- 1. 调桥接之前:缺一样都别碰路由器 -----------------------------------
    if mode not in MODES:
        return done("", "这台机不支持 %r(支持:%s)" % (mode, ", ".join(MODES)))

    if not bool(cfg.at("run.apply")):
        return done("", "这条路线没有「只看不切」:桥接一调用就真的下发了"
                        "(它先切档、再回读)。所以本次什么都没做 —— "
                        "要真切请加 --apply(整轮里恒为真)。")

    params, missing = {}, []
    for concept, where in NEEDS.get(mode, {}).items():
        value = cfg.at(where)
        if value is None or not str(value).strip():
            missing.append("%s(%s)" % (where, cfg.where(where)))
        else:
            params[concept] = str(value)
    if missing:
        return done("", "切 %s 缺配置:%s。用记事本补上,这一档没有碰路由器。"
                        % (mode, "、".join(missing)))

    py2 = str(cfg.at("bench.python2") or "").strip()
    if not py2:
        return done("", _PY2_HINT % (cfg.source or "config.yaml"))
    script = os.path.join(ROOT, BRIDGE)
    if not os.path.exists(script):
        return done("", "找不到桥接脚本:%s" % script)
    ip = _host_only(str(cfg.at("router.ip") or ""))
    if not ip:
        return done("", "没有样机地址:%s 的 router.ip 没填。"
                        % cfg.where("router.ip"))
    admin_pass = str(cfg.at("router.pass") or "")
    if not admin_pass:
        return done("", "没有管理密码:%s 的 router.pass 没填。"
                        % cfg.where("router.pass"))

    # 下发后等多久再回读。DHCP 拿地址是这几档里最慢的,等不够会读到空的
    # wan_ip —— 那会被判成"没拨上"。所以 dynamic 单独给 45 秒(老脚本口径)。
    settle = int((FACTS.get("mode_overrides") or {}).get(mode, {}).get(
        "bridge_settle") or FACTS.get("bridge_settle") or 20)

    # --- 2. 真的切一次 -------------------------------------------------------
    # 契约(见桥接文件顶部):stdout 只有一行 JSON;退出码 0=成功、
    # 2=跑完了但判定不过(仍有 JSON)、3=参数用错了(**stdout 是空的**)。
    argv = [py2, script, BRIDGE_MODE[mode], "--ip", ip, "--pass", admin_pass,
            "--settle", str(settle), "--brand", FACTS.get("brand", ""),
            "--model", FACTS.get("model", "")]
    user = str(cfg.at("router.user") or "").strip()
    if user:
        argv += ["--user", user]
    for key in sorted(params):
        argv += ["--param", "%s=%s" % (key, params[key])]
    try:
        # 下发 + settle + 回读:给足余量,但绝不无限等。
        proc = subprocess.run(argv, capture_output=True, text=True,
                              errors="replace", timeout=settle + 240)
    except Exception as exc:
        return done("", "桥接没跑起来:%s: %s(解释器 %s)"
                        % (type(exc).__name__, exc, py2))

    out = _last_json(proc.stdout or "")
    if out is None:
        # 退出码 3 = 参数用错了,stdout 本来就是空的;别的情况说明桥接没能
        # 正常收尾。两种都不能猜"可能切成功了"。
        return done("", "桥接没有吐出 JSON(退出码 %s)。它要么参数用错了"
                        "(退出码 3),要么没跑起来 —— 检查 %s 这个解释器,"
                        "以及 RouterCtrl 是否装在它里面。stderr 尾部:%s"
                        % (proc.returncode, py2,
                           (proc.stderr or "")[-400:].strip() or "(空)"))

    for warning in out.get("warnings") or []:
        warnings.append(warning)
    read_back = str(out.get("read_back") or "")
    host = _host_name(out.get("detail"))

    # --- 3. 两道关都过了才算成功 ---------------------------------------------
    # 桥接看得比回读串多(它还查 WAN 有没有真拿到地址)。它说不行就不行 ——
    # 哪怕 wan_type 正好对上,那也是"类型对了、没拨上"。
    if not out.get("success"):
        # **bridge_ok=False 这个参数是承重的**:这条路径上 read_back 往往和目标
        # 完全一致(wan_type 就是 PPTP),只有桥接知道 WAN 根本没拿到地址。
        # 不传它,success 会被回读算成 True —— 一个"类型对了、其实没拨上"的
        # 绿格子,吞吐照测、报告照绿。
        return done(read_back,
                    out.get("message") or "桥接判定不通过,但没给原因(退出码 %s)"
                                          % proc.returncode,
                    applied=bool(out.get("applied")), model=host,
                    bridge_ok=False)
    return done(read_back, "", applied=bool(out.get("applied")), model=host)


# ---------------------------------------------------------------------------
def main(argv=None):
    parser = argparse.ArgumentParser(
        description="TP-Link 自家样机(RouterCtrl 桥接)—— WAN 拨号方式切换"
                    "(一调用就真下发,必须加 --apply;这条路线没有「只看不切」)")
    parser.add_argument("mode", choices=MODES, help="目标拨号方式")
    parser.add_argument("--apply", action="store_true",
                        help="真正下发(这条路线不加它什么都不做)")
    parser.add_argument("--perf", action="store_true",
                        help="跑整轮:逐档切换 + 测吞吐 + 出报告(必定下发)")
    args = parser.parse_args(argv)

    # 台架 Windows 控制台是 GBK:回读里只要有一个 GBK 编不出的字符,print
    # 就会抛 UnicodeEncodeError 把整轮打断。用 ? 顶掉。
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors="replace")
        except Exception:
            pass

    cfg = perf.load(model="TPLink_RouterCtrl")
    cfg.require("router.ip", "router.pass", "bench.python2")

    if args.perf:
        cfg.setdefault("run", {})["apply"] = True        # 整轮必定下发
        return 0 if perf.run(switch, MODES, cfg)["ok"] else 2

    cfg.setdefault("run", {})["apply"] = bool(args.apply)
    res = switch(args.mode, cfg)
    print(json.dumps(res, ensure_ascii=False, indent=2))
    return 0 if res["success"] else 2


if __name__ == "__main__":
    sys.exit(main())
