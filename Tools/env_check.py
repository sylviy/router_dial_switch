"""第 0 步:这台电脑能不能干活。**不碰路由器的配置,只看得见摸得着的三样。**

    python Tools/env_check.py

三项全绿才算过:
  * python      —— 跑本工具的解释器路径(台架上应该是 vendor\\python\\python.exe)
  * playwright  —— 装了没有、什么版本、浏览器起不起得来
  * dut         —— config.yaml 里那个地址通不通(HTTP 打得开)

不过的话**是环境问题,不是适配问题** —— 照 stderr 里那句提示修,别去改型号脚本。

退出码:0 = 三项全绿 / 1 = 有项不绿 / 2 = 用法错误
"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import _probe                                              # noqa: E402


def check_python():
    return {"item": "python", "ok": True, "value": sys.executable,
            "note": "%d.%d.%d" % sys.version_info[:3]}


def check_playwright(cfg):
    try:
        import playwright                                  # noqa: F401
        from playwright.sync_api import sync_playwright
    except Exception as exc:
        return {"item": "playwright", "ok": False, "value": "(没装)",
                "note": "%s —— 台架上要用 Vendor/python 那个解释器跑"
                        "(它自带 playwright);别 pip install,台架不联网。" % exc}
    try:
        version = __import__("importlib.metadata", fromlist=["x"]).version(
            "playwright")
    except Exception:
        version = "?"
    exe = cfg.at("bench.browser_path")
    exe_from = "config.yaml 的 bench.browser_path"
    if not exe:
        exe = os.environ.get("ROUTER_BROWSER_PATH")
        exe_from = "环境变量 ROUTER_BROWSER_PATH"
    browsers_dir = (cfg.at("bench.browsers_dir")
                    or os.environ.get("ROUTER_BROWSERS_DIR"))
    if browsers_dir:
        os.environ["PLAYWRIGHT_BROWSERS_PATH"] = str(browsers_dir)
    try:
        with sync_playwright() as pw:
            if exe:
                browser = pw.chromium.launch(executable_path=str(exe),
                                             headless=True)
                how = exe_from
            else:
                try:
                    browser = pw.chromium.launch(channel="chrome", headless=True)
                    how = "系统装的 Chrome"
                except Exception:
                    browser = pw.chromium.launch(headless=True)
                    how = "Playwright 自带的 chromium"
            browser.close()
    except Exception as exc:
        return {"item": "playwright", "ok": False, "value": version,
                "note": "浏览器起不来:%s —— 台架上要装 Chrome,或者把 "
                        "chrome.exe 的路径填进 config.yaml 的 "
                        "bench.browser_path。" % str(exc).splitlines()[0]}
    return {"item": "playwright", "ok": True, "value": version,
            "note": "浏览器:" + how}


def check_dut(cfg):
    url = _probe.url_of(cfg)
    if not url:
        return {"item": "dut", "ok": False, "value": "(没填)",
                "note": "config.yaml 的 router.ip 没填 —— 填被测机管理页地址。"}
    try:
        with urllib.request.urlopen(url, timeout=8) as resp:
            code = resp.getcode()
    except urllib.error.HTTPError as exc:
        # 401/403 也算通:说明那台机在,只是要认证(HTTP Basic 的老机型)
        code = exc.code
    except Exception as exc:
        return {"item": "dut", "ok": False, "value": url,
                "note": "打不开:%s —— 检查网线、网段,以及这台电脑的 IP 是不是"
                        "和路由器同一网段。" % exc}
    return {"item": "dut", "ok": True, "value": url, "note": "HTTP %s" % code}


def main(argv=None):
    ap = _probe.base_parser(__doc__.splitlines()[0])
    ap.add_argument("--json", action="store_true", help="stdout 输出 JSON")
    args = ap.parse_args(argv)
    cfg = _probe.load_cfg(args)

    rows = [check_python(), check_playwright(cfg), check_dut(cfg)]
    if args.json:
        print(json.dumps(rows, ensure_ascii=False, indent=2))
    else:
        print("%-12s %-6s %s" % ("项", "结果", "值"))
        for row in rows:
            print("%-12s %-6s %s" % (row["item"], "OK" if row["ok"] else "BAD",
                                     row["value"]))
    for row in rows:
        if not row["ok"]:
            _probe.say("[%s] %s" % (row["item"], row["note"]))
        elif row["note"]:
            _probe.say("[%s] %s" % (row["item"], row["note"]))
    bad = [r["item"] for r in rows if not r["ok"]]
    if bad:
        _probe.say("\n不过的项:%s。**这是环境问题,不是适配问题** —— "
                   "照上面的提示修,别改型号脚本。" % ", ".join(bad))
        return _probe.FAIL
    return _probe.PASS


if __name__ == "__main__":
    sys.exit(main())
