"""探针共用的底座:开浏览器、登录、走菜单、**找元素**。

## 为什么这个文件必须存在

任务书里那条硬要求:「所有工具必须复用型号脚本同样会用的查找方式,否则
"工具说命中 1"就不能预测"脚本能找到"」。

这里的 `_pause` / `_find` / `_find_text` **和型号脚本里的那三个是同一份代码**
(只有 docstring 按各机情况写得不一样)。这条不是靠自觉维持的:

  * `make_facts.py` 生成新型号脚本时,是**整份拷贝一个已交付的同型号 UI 的
    脚本**再换掉 FACTS/MODES/NEEDS —— 拷来的自然带着这三个函数;
  * `check_model.py` 有一项**查找语义漂移**检查:把型号脚本里这三个函数的
    代码(剥掉 docstring 和注释)和这里的逐一比对,不一样就报出来。

所以「工具说这个选择器命中 1」能预测「脚本也命中 1」是**可验证的**,
不是一句承诺。改这里之后跑一遍 `check_model.py --all` 就知道哪几台漂了。

## 约定(七个工具都遵守)

  * stdout 只有结构化结果(JSON 或定长表格),给人看的诊断一律走 stderr;
  * 退出码 0 = 通过 / 1 = 未通过 / 2 = 用法错误;
  * 地址和密码默认从 config.yaml 取,--ip / --pass 可覆盖。
"""
from __future__ import annotations

import argparse
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from common import perf                                    # noqa: E402

PASS, FAIL, USAGE = 0, 1, 2

# 各步最多等多久(毫秒)。名字带下划线是为了和型号脚本里的那组**一模一样**
# —— 下面 _pause / _find 的函数体要能和型号脚本逐字节比对(见 check_model.py
# 的"查找语义漂移"那一项),常量名不一样就比不了。
_LOGIN_MS, _NAV_MS, _DIAL_MS, _FIELD_MS = 8000, 6000, 8000, 3000
_STEP_MS, _PAUSE_MS = 200, 300
# 工具自己用不带下划线的别名,读起来顺一点。
LOGIN_MS, NAV_MS, DIAL_MS, FIELD_MS = _LOGIN_MS, _NAV_MS, _DIAL_MS, _FIELD_MS
STEP_MS, PAUSE_MS = _STEP_MS, _PAUSE_MS


# ---------------------------------------------------------------------------
# 这两个函数会被原样抄进生成的型号脚本 —— 改动前先想清楚
# ---------------------------------------------------------------------------
def _pause(page, ms=_PAUSE_MS):
    """等一会儿,让页面消化上一步操作。"""
    try:
        page.wait_for_timeout(ms)
    except Exception:
        pass


def _find(page, sel, wait_ms=0, visible=True):
    """在**所有 frame** 里找一个元素;wait_ms 内没出现就返回 None。

    为什么要扫所有 frame:老式 frameset 固件(Cudy AX1500)的登录框在主文档、
    菜单在顶部帧、WAN 表单在子帧里,只看主文档什么都找不到。

    visible=False:连隐藏的也认。被美化插件藏起来的原生 <select> 是
    display:none 的,但它就是真控件。
    """
    waited = 0
    while True:
        for fr in list(page.frames):
            try:
                loc = fr.locator(sel)
                count = min(loc.count(), 25)
            except Exception:
                continue
            for i in range(count):
                el = loc.nth(i)
                try:
                    if el.is_visible():
                        return el
                except Exception:
                    continue
            if not visible and count:
                return loc.first
        if waited >= wait_ms:
            return None
        _pause(page, _STEP_MS)
        waited += _STEP_MS


def _find_text(page, text, wait_ms=0):
    """按**精确文字**找一个可见元素(菜单项用)。子串匹配会点错菜单。"""
    waited = 0
    while True:
        for fr in list(page.frames):
            try:
                loc = fr.get_by_text(text, exact=True)
                for i in range(min(loc.count(), 25)):
                    el = loc.nth(i)
                    if el.is_visible():
                        return el
            except Exception:
                continue
        if waited >= wait_ms:
            return None
        _pause(page, _STEP_MS)
        waited += _STEP_MS


# ---------------------------------------------------------------------------
# 命令行 / 配置
# ---------------------------------------------------------------------------
def base_parser(description):
    ap = argparse.ArgumentParser(description=description)
    ap.add_argument("--ip", default=None, help="路由器地址(默认取 config.yaml 的 router.ip)")
    ap.add_argument("--pass", dest="password", default=None,
                    help="管理密码(默认取 config.yaml 的 router.pass)")
    ap.add_argument("--pw-sel", default=None,
                    help="登录密码框选择器(默认 input[type=password])")
    ap.add_argument("--login-btn", default=None,
                    help="登录按钮选择器(不给就填完按回车)")
    ap.add_argument("--menu", default="",
                    help="菜单路径,逗号分隔;前缀 sel: 表示用选择器,"
                         "否则按菜单文字精确匹配。例:"
                         "--menu 'sel:#Network,sel:#WAN' 或 --menu 'Internet Settings'")
    ap.add_argument("--show", action="store_true", help="别用无头模式,让我看见它点")
    return ap


def load_cfg(args):
    """读 config.yaml 并套上命令行覆盖。地址和密码缺一个都开不了工。"""
    cfg = perf.load()
    if args.ip:
        cfg.setdefault("router", {})["ip"] = args.ip
    if args.password is not None:
        cfg.setdefault("router", {})["pass"] = args.password
    if getattr(args, "show", False):
        cfg.setdefault("run", {})["headless"] = False
    else:
        cfg.setdefault("run", {})["headless"] = True
    return cfg


def url_of(cfg):
    url = str(cfg.at("router.ip") or "").strip()
    if url and not url.startswith("http"):
        url = "http://" + url
    return url


def say(*parts):
    """诊断信息一律走 stderr —— stdout 要留给结构化结果。"""
    sys.stderr.write(" ".join(str(p) for p in parts) + "\n")


# ---------------------------------------------------------------------------
# 浏览器
# ---------------------------------------------------------------------------
class Page:
    """开浏览器 + 打开地址 + 登录 + 走菜单,退出时收干净。

    启动优先级和型号脚本一致:config.yaml 写死的可执行文件 -> 系统装的
    Chrome -> Playwright 自带的 chromium。台架离线,不会去下载。
    """

    def __init__(self, cfg, args):
        self.cfg, self.args = cfg, args
        self.page = None
        self._pw = self._browser = self._ctx = None

    def __enter__(self):
        from playwright.sync_api import sync_playwright

        exe = (self.cfg.at("bench.browser_path")
               or os.environ.get("ROUTER_BROWSER_PATH"))
        browsers_dir = (self.cfg.at("bench.browsers_dir")
                        or os.environ.get("ROUTER_BROWSERS_DIR"))
        if browsers_dir:
            os.environ["PLAYWRIGHT_BROWSERS_PATH"] = str(browsers_dir)
        headless = bool(self.cfg.at("run.headless"))

        self._pw = sync_playwright().start()
        if exe:
            self._browser = self._pw.chromium.launch(executable_path=str(exe),
                                                     headless=headless)
        else:
            try:
                self._browser = self._pw.chromium.launch(channel="chrome",
                                                         headless=headless)
            except Exception as exc:
                say("[browser] 系统 Chrome 起不来(%s),改用自带 chromium" % exc)
                self._browser = self._pw.chromium.launch(headless=headless)
        self._ctx = self._browser.new_context(ignore_https_errors=True)
        self._ctx.set_default_timeout(15000)
        self._ctx.set_default_navigation_timeout(30000)
        self.page = self._ctx.new_page()
        self.page.goto(url_of(self.cfg), wait_until="domcontentloaded")
        return self

    def login(self):
        """填密码登录;返回是否**确实离开了登录页**。没有密码框 = 已在会话内。"""
        pw_sel = self.args.pw_sel or "input[type=password]"
        pwd = _find(self.page, pw_sel, wait_ms=LOGIN_MS)
        if not pwd:
            say("[login] 没看到密码框(%s),当作已经在会话里" % pw_sel)
            return True
        pwd.fill(str(self.cfg.at("router.pass") or ""))
        btn = (_find(self.page, self.args.login_btn, wait_ms=2000)
               if self.args.login_btn else None)
        if btn:
            btn.click()
        else:
            pwd.press("Enter")
        waited = 0
        while _find(self.page, pw_sel) is not None:
            if waited >= LOGIN_MS:
                say("[login] 填了密码但还停在登录页 —— 密码不对,或这台机只允许"
                    "一个 Web 会话(先关掉别的已登录页签)")
                return False
            _pause(self.page, STEP_MS)
            waited += STEP_MS
        return True

    def walk_menu(self):
        """按 --menu 逐个点过去。点不到的记一条 stderr,不中断。"""
        missed = []
        for item in [x.strip() for x in (self.args.menu or "").split(",") if x.strip()]:
            if item.startswith("sel:"):
                el = _find(self.page, item[4:], wait_ms=NAV_MS)
            else:
                el = _find_text(self.page, item, wait_ms=NAV_MS)
            if el:
                el.click()
                _pause(self.page)
            else:
                missed.append(item)
                say("[menu] 没找到:%r" % item)
        return missed

    def __exit__(self, *exc):
        for closer in (self._ctx, self._browser):
            try:
                if closer:
                    closer.close()
            except Exception:
                pass
        try:
            if self._pw:
                self._pw.stop()
        except Exception:
            pass
        return False


# ---------------------------------------------------------------------------
# 控件抄录
# ---------------------------------------------------------------------------
_DUMP_JS = """
() => {
  const out = [];
  const push = (el, kind) => {
    const attrs = {};
    for (const name of ['id', 'name', 'class', 'type', 'role', 'data-name',
                        'value', 'placeholder', 'aria-label']) {
      const v = el.getAttribute && el.getAttribute(name);
      if (v) attrs[name] = v.length > 60 ? v.slice(0, 60) + '…' : v;
    }
    let text = (el.innerText || '').trim().replace(/\\s+/g, ' ');
    if (!text && el.value) text = String(el.value).trim();
    if (text.length > 60) text = text.slice(0, 60) + '…';
    let options = null;
    if (el.tagName === 'SELECT') {
      options = Array.from(el.options).map(o => (o.text || '').trim());
    }
    const box = el.getBoundingClientRect ? el.getBoundingClientRect() : null;
    out.push({kind: kind, tag: el.tagName.toLowerCase(), text: text,
              attrs: attrs, options: options,
              visible: !!(box && box.width > 0 && box.height > 0)});
  };
  document.querySelectorAll('select').forEach(el => push(el, 'select'));
  document.querySelectorAll("input[type=radio]").forEach(el => push(el, 'radio'));
  document.querySelectorAll("[role=combobox], [class*='v-select'], [class*='select']")
          .forEach(el => push(el, 'dropdown'));
  document.querySelectorAll("input[type=text], input[type=password]")
          .forEach(el => push(el, 'input'));
  document.querySelectorAll("button, input[type=submit], input[type=button]")
          .forEach(el => push(el, 'button'));
  return out;
}
"""


def dump_controls(page):
    """把**每个 frame** 里的控件抄下来。返回一维列表,每条带 frame 出处。"""
    rows = []
    for fr in list(page.frames):
        try:
            items = fr.evaluate(_DUMP_JS)
        except Exception as exc:
            say("[dump] 这个 frame 读不了(%s):%s" % (fr.url, exc))
            continue
        for item in items or []:
            item["frame"] = fr.url
            rows.append(item)
    return rows


def looks_like_dial(row):
    """这条控件像不像"拨号方式选择器"?

    判据只有一条**保守**的:它得是个能选的东西,而且至少有两个选项 ——
    只有一个选项的下拉不可能是拨号方式。radio 单独一个也算(它成组出现)。
    像不像**不等于**是不是,最终认定必须由人来做(SKILL.md 的关卡一)。
    """
    if row["kind"] == "select":
        return len(row.get("options") or []) >= 2
    return row["kind"] in ("radio", "dropdown")
