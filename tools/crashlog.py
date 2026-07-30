"""tools/crashlog.py —— 崩溃时写一份**小而准**的报告。

为什么单独做这件事:工具崩掉时,Playwright 会吐几十上百行浏览器日志
(启动参数、dbus 警告、call log),里面真正有用的通常就两行。用户要么截屏、
要么把上百行贴给别人 —— 前者看不清,后者又贵又淹没重点。

所以这里做两件事:

  1. **先认已知病症**。绝大多数崩溃是那几种老面孔(窗口被关掉、地址不通、
     Chrome 没装、超时)。认出来就直接给人话结论和下一步,**根本不用问别人**。
  2. 认不出来时,写一份 artifacts/crash_<时间>.txt:异常类型 + 首行 +
     **只保留本仓库文件的调用栈**(site-packages / playwright 内部帧全部滤掉)
     + 环境信息。二十行左右,贴给谁都够。

**绝不写入密码**:调用方传进来的上下文会过一遍脱敏。
"""
from __future__ import annotations

import datetime
import os
import platform
import re
import sys
import traceback

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# 已知病症 -> 人话解释 + 下一步。命中就不用问 agent 了。
HINTS = [
    (r"Target page, context or browser has been closed|Browser closed|"
     r"browser has been closed",
     "那个 Chrome 窗口在跑到一半时被关掉了。\n"
     "  常见原因:手工点了窗口的 X;机器内存不够被系统杀掉;\n"
     "  或者屏幕锁屏/远程桌面断开把它带走了。\n"
     "  下一步:重跑一次,跑的过程中别碰那个窗口。"),
    (r"net::ERR_CONNECTION_REFUSED|net::ERR_ADDRESS_UNREACHABLE|"
     r"net::ERR_NAME_NOT_RESOLVED",
     "连不上这个地址 —— 不是工具的问题。\n"
     "  下一步:先在浏览器里打开同一个地址确认能通;确认这台电脑\n"
     "  和路由器在同一个网段(沙箱/VPN 环境常常到不了路由器内网)。"),
    (r"net::ERR_EMPTY_RESPONSE|net::ERR_CONNECTION_RESET|"
     r"net::ERR_CONNECTION_CLOSED",
     "路由器把连接掐断了。\n"
     "  常见原因:同一时间只允许一个 Web 会话(先把浏览器里登录着的\n"
     "  页签全部退掉);或者这台机对短时间内的连续请求有限制,等一分钟再跑。"),
    (r"Executable doesn't exist|Chromium distribution .* is not found|"
     r"channel=chrome",
     "找不到 Chrome。\n"
     "  下一步:装好 Chrome(离线机要带完整安装包过去);\n"
     "  或者用环境变量 ROUTER_BROWSER_PATH 指向 chrome.exe。"),
    (r"Timeout .* exceeded|TimeoutError",
     "等某个东西超时了。\n"
     "  如果是登录/导航阶段:这台机可能反应特别慢,或者页面压根没渲染出来。\n"
     "  下一步:看 artifacts/ 里那张截图,确认当时页面停在哪。"),
    (r"No module named 'playwright'",
     "这个 Python 里没装 Playwright。\n"
     "  下一步:Windows 上用 start.bat / adapt.bat 启动(它们会挑对解释器),\n"
     "  别直接用系统 python。"),
]

_SECRET_KEYS = re.compile(r"(pass|pwd|secret|token|密码)", re.I)


def explain(exc) -> str:
    """认得出来的病症就给人话结论;认不出来返回空串。"""
    text = "%s: %s" % (type(exc).__name__, exc)
    for pattern, hint in HINTS:
        if re.search(pattern, text, re.I):
            return hint
    return ""


def _repo_frames(exc) -> list:
    """只留本仓库文件的调用栈 —— playwright / site-packages 的内部帧对排查
    没用,却占了报告的九成篇幅。"""
    out = []
    for fr in traceback.extract_tb(exc.__traceback__):
        path = fr.filename or ""
        if "site-packages" in path or "playwright" in path.lower():
            continue
        try:
            rel = os.path.relpath(path, ROOT)
        except Exception:
            rel = path
        if rel.startswith(".."):        # 仓库外的文件(标准库等)也跳过
            continue
        out.append("  %s:%s in %s\n      %s"
                   % (rel, fr.lineno, fr.name, (fr.line or "").strip()))
    return out


def _safe_context(context: dict) -> list:
    out = []
    for k, v in (context or {}).items():
        if _SECRET_KEYS.search(str(k)):
            v = "(已隐去)"
        out.append("  %s = %s" % (k, v))
    return out


def write(exc, step: str, context: dict = None) -> str:
    """写 artifacts/crash_<时间>.txt,返回路径(写不出来就返回空串)。"""
    stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    path = os.path.join(ROOT, "artifacts", "crash_%s.txt" % stamp)
    lines = [
        "router_dial_switch 崩溃报告",
        "时间: %s" % datetime.datetime.now().isoformat(timespec="seconds"),
        "卡在: %s" % step,
        "",
        "异常: %s" % type(exc).__name__,
        "首行: %s" % (str(exc).strip().splitlines() or [""])[0],
        "",
        "调用栈(只留本仓库的文件):",
    ]
    lines += _repo_frames(exc) or ["  (没有本仓库的帧 —— 异常来自库内部)"]
    lines += ["", "环境:",
              "  python = %s" % sys.version.split()[0],
              "  平台   = %s" % platform.platform(),
              "  ROUTER_BROWSER_PATH = %s"
              % (os.environ.get("ROUTER_BROWSER_PATH") or "(未设置)")]
    if context:
        lines += ["", "上下文:"] + _safe_context(context)
    hint = explain(exc)
    if hint:
        lines += ["", "已知病症:", "  " + hint.replace("\n", "\n  ")]
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8", errors="replace") as fh:
            fh.write("\n".join(lines) + "\n")
        return path
    except Exception:
        return ""


def report(exc, step: str, context: dict = None, log=print) -> str:
    """崩溃时的统一出口:先认病症,认不出来就落一份报告并告诉用户贴哪个文件。"""
    first = (str(exc).strip().splitlines() or [""])[0]
    log("[X] %s 时出错:%s" % (step, first))
    hint = explain(exc)
    if hint:
        log("    " + hint.replace("\n", "\n    "))
    path = write(exc, step, context)
    if path:
        rel = os.path.relpath(path, ROOT)
        if hint:
            log("    (细节已存到 %s,按上面做完还不行再贴它)" % rel)
        else:
            log("    这个报错没见过。把 **%s** 贴给 agent —— 它只有二十来行,"
                "\n    已经滤掉了浏览器日志,也不含密码。" % rel)
    return path
