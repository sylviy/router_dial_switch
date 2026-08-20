"""交互式入口 —— 双击 start.bat,选型号、选操作,没有别的要记。

    python app/start.py            (Windows 上双击根目录的 start.bat)

菜单按**危险程度**排:先"只看回读不下发",再"单档下发"(要输 yes),
最后才是整轮。配置只有一处 config.yaml,现场用记事本改;缺什么由菜单 5
连行号一起告诉你,所以这里一个密码都不问。

命令行等价物:
    python Models/<型号>/<型号>.py <档>            只切换看回读,不下发
    python Models/<型号>/<型号>.py <档> --apply    真下发
    python Models/<型号>/<型号>.py <档> --perf     整轮:逐档切 + 测吞吐 + 出报告
"""
from __future__ import annotations

import argparse
import os
import sys

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

from common import discover                                  # noqa: E402


def list_models():
    """Models/ 下的型号名。目录长什么样只有 discover.py 知道。"""
    return discover.list_models(SCENE)


def _ask(prompt: str, default: str = "") -> str:
    try:
        val = input(prompt).strip()
    except EOFError:
        val = ""
    return val or default


def _ask_secret(prompt: str, default: str = "") -> str:
    """密码:终端里不回显;stdin 被脚本接管(冒烟测试)时退回普通 input。"""
    if sys.stdin.isatty():
        import getpass
        try:
            return getpass.getpass(prompt).strip() or default
        except Exception:
            pass
    return _ask(prompt, default)


def _pick(prompt: str, n: int, default: int = 1) -> int:
    while True:
        raw = _ask("%s [1-%d](回车=%d): " % (prompt, n, default))
        if not raw:
            return default
        if raw.isdigit() and 1 <= int(raw) <= n:
            return int(raw)
        print("  请输入 1 到 %d 之间的数字。" % n)


def _empty(value) -> bool:
    return (value is None or not str(value).strip()
            or str(value).strip() == "FILL_ME")


def _is_chariot(cfg) -> bool:
    return str(cfg.at("run.backend") or "").lower() == "chariot"


def _bench_needs(cfg, planned) -> list:
    """整轮**测吞吐**还缺哪些台架接线。只切档(菜单 1/2)一项都不用。

    simulate 后端不碰仪表,所以整段跳过。chariot 才逐档核对:对端打谁、
    拨通后 ping 谁 —— 这两样猜错都不会报错,只会给一份打错了口、数字却很
    正常的报告,所以宁可开跑前拦住。写了全局的 public_ip/internet_ip
    (或 wan_up_host)就算有兜底,不再逐档要求。
    """
    if not _is_chariot(cfg):
        return []
    need = []
    # 注入机按频段要。对不上号的频段以前会悄悄改用 lan 那台 —— 测的是有线,
    # 报告上却写着 5GHz。所以逐个频段核对;共用一台时 injector_ip 兜底。
    has_injector_fallback = not _empty(cfg.at("bench.injector_ip"))
    for band in (cfg.at("perf.bands") or ["lan"]):
        if not has_injector_fallback and _empty(cfg.at("bench.injectors.%s" % band)):
            need.append("bench.injectors.%s" % band)
    if not need and not has_injector_fallback:
        need.append("bench.injector_ip")
    has_peer_fallback = not (_empty(cfg.at("bench.public_ip"))
                             or _empty(cfg.at("bench.internet_ip")))
    has_ping_fallback = not _empty(cfg.at("bench.wan_up_host"))
    for mode in planned:
        if not has_peer_fallback and _empty(cfg.at("bench.endpoints.%s" % mode)):
            need.append("bench.endpoints.%s" % mode)
        if not has_ping_fallback and _empty(cfg.at("bench.wan_up_hosts.%s" % mode)):
            need.append("bench.wan_up_hosts.%s" % mode)
    return need


def _reachable(cfg, name, mod) -> str:
    """被测机地址打得开吗?打不开就返回一句人话,打得开返回空串。

    **换了被测机但 router.ip 忘了改**是现场最常见的那个错(上一台还在
    192.168.0.1,这一台在 192.168.10.1)。不先查这一下的话,菜单 3 会开着
    浏览器一档一档去超时,几分钟后才发现;查一下只花几秒。

    **绕开系统代理**:代理会把这一下变成"问代理服务器通不通",而不是"问那台
    路由器在不在" —— 台架直连没有代理,但办公网的机器上有,那会给出相反的答案。
    """
    import urllib.error
    import urllib.request

    url = str(cfg.at("router.ip") or "").strip()
    if url and not url.startswith("http"):
        url = "http://" + url
    if not url:
        return "%s 的 router.ip 没填。" % cfg.where("router.ip")
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        opener.open(url, timeout=8)
    except urllib.error.HTTPError:
        return ""          # 401/403 也算通:机器在,只是要认证
    except Exception as exc:
        return ("打不开 %s(%s)。\n"
                "  router.ip(%s)现在写的是这个地址,而 %s 的默认地址是 %s。\n"
                "  换被测机要改两处:router.ip,和 run.dial_modes(这轮测哪几档)。"
                % (url, exc, cfg.where("router.ip"), name,
                   (getattr(mod, "FACTS", {}) or {}).get("url", "(这条路线没有 url)")))
    return ""


def _run_new_shape(name: str) -> int:
    """新形状型号的向导。**不问密码** —— 配置只有 config.yaml 一处,
    缺什么会指到具体哪一行,用记事本补完再来。"""
    from common import perf as perf_mod

    mod = discover.load_model(SCENE, name)
    modes = list(getattr(mod, "MODES", []))
    try:
        cfg = perf_mod.load(model=name)
    except SystemExit as exc:                 # config.yaml 不在 / 语法坏了
        print(exc)
        return 1

    planned = [m for m in (cfg.at("run.dial_modes") or modes)]
    unknown = [m for m in planned if m not in modes]
    print("\n型号:%s" % name)
    print("这台机支持:%s" % " / ".join(modes))
    print("这轮要测(config.yaml 的 run.dial_modes):%s" % " / ".join(planned))
    if unknown:
        print("  [!] %s 这台机切不了,整轮会被拦住 —— 把它从 run.dial_modes"
              " 里删掉(%s)。" % ("/".join(unknown), cfg.where("run.dial_modes")))
    print("\n要做什么:")
    print("  1. 只切一档,**只看回读不下发**(最安全,台架第一步该做这个)")
    print("  2. 只切一档,并**真正下发**(会改路由器,切错档当场断网)")
    print("  3. 整轮性能测试:逐档切换 → 等 WAN → 测吞吐 → 出报告(必定下发)")
    print("  4. 离线自检:拿假路由器页面跑一遍,不碰真机")
    print("  5. 看看 config.yaml 还差什么")
    action = _pick("选操作", 5)

    if action == 4:
        from tests import mock_test
        return mock_test.main([])

    # 这轮要用到的配置项 = 每档要的账密(型号脚本自己声明的 NEEDS)+ 地址密码
    needs = ["router.ip", "router.pass"]
    for m in (planned if action == 3 else modes):
        needs += list((getattr(mod, "NEEDS", {}) or {}).get(m, {}).values())
    if action == 5:
        # 只切档(菜单 1/2)用不到 bench 段,所以分开说 —— 免得同事以为
        # "还没填注入机 IP 就不能试切"。
        try:
            cfg.require(*sorted(set(needs)))
            print("切换要用的配置都填好了(%s)。" % cfg.source)
        except SystemExit as exc:
            print(exc)
        bench = _bench_needs(cfg, planned)
        if bench:
            print("\n---- 以上够用来切档了。下面这些只有整轮测吞吐(菜单 3)才要 ----")
            try:
                cfg.require(*bench)
            except SystemExit as exc:
                print(exc)
        else:
            print("整轮测吞吐要用的台架接线也齐了。" if _is_chariot(cfg) else
                  "backend 现在是 simulate(离线模拟),bench 段不用填 —— "
                  "要出真数字时改成 chariot,再回来看这一项。")
        return 0

    # 菜单 1/2/3 都要碰路由器 —— 先花几秒确认地址打得开,别开着浏览器去超时。
    problem = _reachable(cfg, name, mod)
    if problem:
        print("\n这一步没有开始(没有碰路由器):\n  " + problem)
        print("\n用记事本打开 %s 改掉,再回来。" % cfg.source)
        return 1

    if action == 3:
        try:
            cfg.require("router.ip", "router.pass", *_bench_needs(cfg, planned))
        except SystemExit as exc:
            print(exc)
            return 1
        print("\n开始整轮:每档都会**真正下发**。缺账密的档会被记成失败并跳过,"
              "不会拿空账号去覆盖路由器配置。")
        cfg.setdefault("run", {})["apply"] = True
        return 0 if perf_mod.run(mod.switch, modes, cfg)["ok"] else 2

    # ---- 1 / 2:只切一档 ----------------------------------------------------
    print("\n该型号支持的模式:")
    for i, m in enumerate(modes, 1):
        print("  %d. %s" % (i, m))
    mode = modes[_pick("选模式", len(modes)) - 1]

    if action == 2:
        print("\n[!] 这一步会**真的改路由器**。切错档会当场断网,"
              "台架上没人能远程救回来。")
        print("    建议先用操作 1 看一眼回读值对不对,再回来下发。")
        if _ask("确认下发 %s?输入 yes 继续: " % mode).lower() != "yes":
            print("已取消,没有碰路由器。")
            return 0

    cfg.setdefault("run", {})["apply"] = (action == 2)
    res = mod.switch(mode, cfg)
    print("\n==== 结果 ====")
    print("  切换   : %s" % ("成功" if res["success"] else "失败"))
    print("  回读值 : %r   (目标措辞:%r)" % (res["read_back"], res["expected"]))
    print("  已下发 : %s" % ("是" if res["applied"] else "否"))
    if res["filled"]:
        print("  填了   : %s" % "、".join(res["filled"]))
    if res["message"]:
        print("  说明   : %s" % res["message"])
    for w in res["warnings"]:
        print("  提醒   : %s" % w)
    if res["screenshot"]:
        print("  截图   : %s" % res["screenshot"])
    if res["success"] and not res["applied"]:
        print("\n回读值和目标一致 = 这一档切对了。确认无误后回来选操作 2 下发。")
    return 0 if res["success"] else 2


def _console_safe() -> None:
    """台架 Windows 控制台是 GBK(cp936),管道时 Python 也按 GBK 编码输出。
    路由器回读的文字里只要有一个 GBK 编不出的字符,print 就会抛
    UnicodeEncodeError 把整轮打断 —— 在最不该崩的时候崩。改成用 ? 顶掉。
    (2026-07-28 台架实测:start.py 打印 U+2713 时就这么炸过。)"""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors="replace")
        except Exception:                      # 老 Python / 非标准流:忽略
            pass


def main(argv=None) -> int:
    _console_safe()
    argparse.ArgumentParser(description="路由器拨号切换 / WAN 性能测试").parse_args(
        argv if argv is not None else [])

    print("==== 路由器拨号切换 / WAN 性能测试 ====")
    names = list_models()
    if not names:
        print("Models/ 里没有型号脚本 —— 照 SKILL.md 适配一台。")
        return 1

    print("支持的型号(括号里 = 该型号声明的拨号方式,按轮次顺序):")
    for i, name in enumerate(names, 1):
        modes = getattr(discover.load_model(SCENE, name), "MODES", [])
        print("  %d. %-18s (%s)" % (i, name, "/".join(modes)))
    return _run_new_shape(names[_pick("选型号", len(names)) - 1])


if __name__ == "__main__":
    sys.exit(main())
