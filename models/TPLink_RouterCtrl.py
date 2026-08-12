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
  * **模式名一个字符都不要改** —— 桥接和历史 Excel 都按这些名字对行。

单跑:

    python models/TPLink_RouterCtrl.py dynamic --apply
    python models/TPLink_RouterCtrl.py pptp_dynamic_public --apply

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
    "route": "bridge",                          # 不开浏览器,见 _driver.session
    "bridge": "tools/routerctrl_bridge.py",
    "modes": {
        "dynamic": "Dynamic IP",
        "static": "Static IP",
        "pppoe": "PPPoE",                       # 无第二连接
        "pptp_dynamic_internet": "PPTP",
        "pptp_dynamic_public": "PPTP",
        "l2tp_dynamic_internet": "L2TP",
        "l2tp_dynamic_public": "L2TP",
    },
    # 下发后等多久再回读。老脚本(dial_perf.py)给 dynamic 的是 30+15=45 秒、
    # 其余 15 秒;这里统一 20 秒,dynamic 按老口径单独给 45 —— DHCP 拿地址是
    # 这几档里最慢的,等不够会读到空的 wan_ip,那会被判成"没拨上"。
    "bridge_settle": 20,
    "mode_overrides": {
        "dynamic": {"bridge_settle": 45},
    },
}

# 整轮实际会跑的档,按台架轮次的顺序。**只列实测接线跑过的**(2026-08-10
# 用户口径):PPPoE 只测无第二连接那档;PPTP/L2TP 只测第二连接为动态的,
# 没有"第二连接为静态"的接线。多列一档就等于让整轮去切一个没人验过的组合。
# static 也故意不列:切过去会是静态 IP 且不填任何地址(要测请手动单跑)。
MODES = ["dynamic", "pppoe",
         "pptp_dynamic_internet", "pptp_dynamic_public",
         "l2tp_dynamic_internet", "l2tp_dynamic_public"]

# 每档要 config.yaml 里的哪几项 -> 填进哪个概念(概念名和桥接的 --param 键
# 一一对应)。**碰路由器之前**核对:桥接一调用就真下发了,缺账密再去调用,
# 等于拿桥接自己的历史默认账号拨上去 —— 报告照样绿,测的却不是你配的账号。
NEEDS = {
    "dynamic": {},
    "pppoe": {"pppoe_user": "router.pppoe_user",
              "pppoe_pass": "router.pppoe_pass"},
    "pptp_dynamic_internet": {"vpn_server": "router.pptp.server",
                              "vpn_user": "router.pptp.user",
                              "vpn_pass": "router.pptp.pass"},
    "pptp_dynamic_public": {"vpn_server": "router.pptp.server",
                            "vpn_user": "router.pptp.user",
                            "vpn_pass": "router.pptp.pass"},
    "l2tp_dynamic_internet": {"vpn_server": "router.l2tp.server",
                              "vpn_user": "router.l2tp.user",
                              "vpn_pass": "router.l2tp.pass"},
    "l2tp_dynamic_public": {"vpn_server": "router.l2tp.server",
                            "vpn_user": "router.l2tp.user",
                            "vpn_pass": "router.l2tp.pass"},
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

    def done(read_back, message="", applied=False, model=""):
        """这个函数唯一的出口。success 只能由 contract.verify() 算出来 ——
        桥接回读的 wan_type 等于目标串才算数,空回读永远判假。"""
        res = contract.result(contract.verify(read_back, label), read_back,
                              label, message=message, applied=applied,
                              warnings=warnings, **ident)
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
    argv = [py2, script, mode, "--ip", ip, "--pass", admin_pass,
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
        return done(read_back,
                    out.get("message") or "桥接判定不通过,但没给原因(退出码 %s)"
                                          % proc.returncode,
                    applied=bool(out.get("applied")), model=host)
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
