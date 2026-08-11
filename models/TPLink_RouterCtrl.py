"""自家样机(TP-Link)—— 走 RouterCtrl,不走 Web UI。

**一个文件管所有自家样机**,不是一台机一个:自家机器有内部库 `RouterCtrl`,
切档靠它的 HTTP API,而那套 API 各型号是一样的。所以这里的"事实"不是选择器,
是**模式名和回读串**;具体是哪台样机由运行时决定 —— IP 和凭据在
`router.yaml`(git 已忽略),报告里的型号名取自 `get_wan_info()['hostName']`
(台架那台回的是 `ArcherAX1800`),**没有写死**。

## 它和别的型号脚本哪里不一样

`RouterCtrl` 只装在台架 PATH 上那个 Python 2(ActivePython 2.6.5)里,py3 侧
import 不了。所以中间隔一个子进程:`tools/routerctrl_bridge.py`(py2.6 语法)
负责下发 + 回读,**只从 stdout 吐一行 JSON**。本文件是那条边界的 py3 这一侧。

跑它的 py2 解释器取自 `perf_configs/TPLink_RouterCtrl.yaml` 的 `chariot.python`
—— 台架已经为 Chariot 配好了那一行,**不再开第二处**。没配就明确报错说该填哪。

## 两条和别的机型不同的规矩(都在下面的 run() 里写死了)

  * **没有"只看不切"。** 别的机型 `--apply` 之前只是选中控件、不点保存;这条
    路线一调用桥接就**真的下发了**,没有"预览"这种状态。所以不加 `--apply`
    时它什么都不做,直接如实失败 —— 而不是假装看过一眼。
  * **回读和桥接必须都同意才算成功。** 桥接除了比对 `wan_type`,还查 WAN 有没
    有真拿到地址(空 / `0.0.0.0` 都算没拨上)。所以这里两件事都要满足:
    `record_verified()` 的精确相等 **且** 桥接自己判定通过。少查一条就会出现
    "类型对了、其实没拨上"的绿格子。

单跑:

    python models/TPLink_RouterCtrl.py dynamic --apply
    python models/TPLink_RouterCtrl.py pptp_dynamic_public --apply

模式名一个字符都不要改 —— 桥接和历史 Excel 都按这些名字对行。
"""
from __future__ import annotations

import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

# 参数文件是按**脚本名**存的(perf_configs/<脚本名>.yaml),不是按 FACTS["model"]
# —— 后者运行时会被样机自己报的型号覆盖。从文件名取,改名也不会指错。
SCRIPT_NAME = os.path.splitext(os.path.basename(os.path.abspath(__file__)))[0]

from models._driver import run_cli, session

# ---------------------------------------------------------------------------
# FACTS —— 这条路线没有任何选择器。modes 的值是 **get_wan_info()['wan_type']
# 的回读串**(桥接的 WAN_TYPE_BY_MODE,台架实测确认),不是界面措辞。
#
# 只声明**实测跑过的档**(2026-08-10 用户口径):PPPoE 只测无第二连接的那档;
# PPTP/L2TP 只测第二连接为动态的,没有"第二连接为静态"的接线。多声明一档就等
# 于让整轮去切一个没人验过的组合。
#
# `_internet` / `_public` 两个后缀对**下发完全没有影响**(桥接里收在同一支
# elif),只决定 Chariot 打哪个远端 —— 所以它们的回读串一样是正常的,分别在
# perf_configs 的 wan_up.hosts / chariot.e2_ip 里区分。
# ---------------------------------------------------------------------------
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

_PY2_HINT = """没配 py2 解释器,桥接跑不起来(RouterCtrl 只装在台架那个
Python 2.6.5 里)。在 %s 里加这两行:

  chariot:
    python: C:\\Python26\\python.exe

那是台架上装了 PyChariot / RouterCtrl 的那个 python 的绝对路径。**只配这一处**
—— 整轮跑 Chariot 用的也是它。旧键名 python2: 同样认。"""


def _perf_python(model: str):
    """py2 解释器路径 + 参数文件路径,取自 perf_configs/<型号>.yaml。

    只认**显式配过**的值:`ChariotCfg.interpreter` 没配时会兜底成当前解释器
    (py3),拿它去跑桥接会死在 `import RouterCtrl`,而那看起来像"桥接坏了"。
    所以这里读原始的 chariot.python,空就是空。
    """
    from matrix.config import load, path_for_model
    cfg = load(model=model)
    return (cfg.chariot.python or "").strip(), path_for_model(model)


def _ip_of(text: str) -> str:
    """从 IP 或 URL 里取出主机部分 —— 桥接的 --ip 要的是地址,不是 URL。"""
    text = (text or "").strip()
    for prefix in ("http://", "https://"):
        if text.lower().startswith(prefix):
            text = text[len(prefix):]
    return text.split("/")[0].split(":")[0].strip()


def _host_name(detail) -> str:
    """样机自己报的型号(get_wan_info()['hostName'],台架实测 ArcherAX1800)。"""
    if not isinstance(detail, dict):
        return ""
    for key in detail:
        if str(key).replace("_", "").lower() == "hostname":
            return str(detail[key] or "").strip()
    return ""


def _call_bridge(py2: str, script: str, mode: str, ip: str, user: str,
                 password: str, settle: int, params: dict, facts: dict):
    """跑一次桥接,返回 (JSON dict 或 None, 退出码, stderr 尾巴)。

    契约(见桥接文件顶部):stdout 只有一行 JSON;退出码 0=成功、2=跑完了但
    判定不过(仍有 JSON)、3=参数用错了(**stdout 是空的**)。
    """
    argv = [py2, script, mode, "--ip", ip, "--pass", password,
            "--settle", str(settle), "--brand", facts.get("brand", ""),
            "--model", facts.get("model", "")]
    if user:
        argv += ["--user", user]
    for key in sorted(params or {}):
        argv += ["--param", "%s=%s" % (key, params[key])]
    try:
        # 下发 + settle + 回读:给足余量,但绝不无限等。
        proc = subprocess.run(argv, capture_output=True, text=True,
                              errors="replace", timeout=settle + 240)
    except Exception as exc:
        return None, -1, "%s: %s" % (type(exc).__name__, exc)
    # 用 matrix 那个现成的解析器:台架上 stdout 可能混进别的行,它从后往前找
    # 第一行能解析的 JSON(和 chariot_perf.py 那条边界同一个问题)。
    from matrix.perf_backends import _last_json
    return _last_json(proc.stdout or ""), proc.returncode, \
        (proc.stderr or "")[-400:]


def run(facts=None, mode="dynamic", params=None, apply=False, admin_user="",
        admin_pass="", url=None, **kw):
    """这台机的操作配方:不开浏览器,切档交给 py2 侧的 RouterCtrl 桥接。

    成败判定一条没绕:回读由 record_verified() 精确比对,success 仍然只从
    apply_and_verify() 出来,而且桥接自己判定不过时一律走 fail()。
    """
    facts = facts or FACTS
    with session(facts, mode, params=params, apply=apply,
                 admin_user=admin_user, admin_pass=admin_pass,
                 browser=False, **kw) as s:
        # --- 开跑前:三样东西缺一个都别碰路由器 ----------------------------
        if not apply:
            return s.fail(
                "这条路线没有「只看不切」:桥接一调用就真的下发了(它先切档、"
                "再回读)。所以本次什么都没做 —— 要真切请加 --apply。")
        py2, cfg_path = _perf_python(SCRIPT_NAME)
        if not py2:
            return s.fail(_PY2_HINT % cfg_path)
        script = os.path.join(ROOT, s.facts.get("bridge") or "")
        if not os.path.exists(script):
            return s.fail("找不到桥接脚本:%s(FACTS.bridge 指错了?)" % script)
        ip = _ip_of(url or _saved_ip())
        if not ip:
            return s.fail("没有路由器地址:在 router.yaml 里写 "
                          "router_ip: <样机 IP>(python start.py --setup 会"
                          "帮你写),或本次加 --url http://<样机 IP>。")
        if not admin_pass:
            return s.fail("没有管理密码:在 router.yaml 里写 pass: <密码>,"
                          "或本次加 --pass <密码>。凭据不进仓库。")

        # --- 真的切一次 ---------------------------------------------------
        out, rc, err = _call_bridge(
            py2, script, mode, ip, admin_user, admin_pass,
            int(s.facts.get("bridge_settle") or 20), params or {}, s.facts)
        if out is None:
            # 退出码 3 = 参数用错了,stdout 本来就是空的;别的情况说明桥接没能
            # 正常收尾。两种都不能猜"可能切成功了"。
            return s.fail("桥接没有吐出 JSON(退出码 %s)。它要么参数用错了"
                          "(退出码 3),要么没跑起来 —— 检查 %s 这个解释器,"
                          "以及 RouterCtrl 是否装在它里面。stderr 尾部:%s"
                          % (rc, py2, err.strip() or "(空)"))
        for warning in out.get("warnings") or []:
            s.warn(warning)
        if out.get("applied"):
            s.record_applied()          # 只写 applied,对判定没有权力
        s.record_verified(out.get("read_back") or "", s.label)
        if not out.get("success"):
            # 桥接看得比回读串多(它还查 WAN 有没有真拿到地址)。它说不行就
            # 不行 —— 哪怕 wan_type 正好对上,那也是"类型对了、没拨上"。
            return _stamp(s.fail(out.get("message")
                                 or "桥接判定不通过,但没给原因(退出码 %s)" % rc),
                          out)
        return _stamp(s.apply_and_verify(), out)


def _saved_ip() -> str:
    """router.yaml 的 router_ip。IP 和凭据都只住在那里(git 已忽略)。"""
    import settings
    return str((settings.load() or {}).get("router_ip") or "")


def _stamp(result: dict, out: dict) -> dict:
    """把报告里的型号换成样机自己报的那个(hostName)。

    **只改 model 这一个报告字段。** success / read_back / applied 一律由
    Session 写 —— 别在这里加第二行赋值,那就绕开回读守卫了(冒烟测试有一条
    专门扫 models/*.py,发现谁给 success/read_back 赋值就变红)。
    """
    host = _host_name(out.get("detail"))
    if host:
        result["model"] = host
    return result


if __name__ == "__main__":
    sys.exit(run_cli(FACTS, runner=run))
