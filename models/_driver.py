"""每个型号脚本(models/<品牌>_<型号>.py)共用的**动词库**加一份默认配方。

分层:
  * models/<品牌>_<型号>.py —— **交付物**。一个文件 = 一台型号的全部"事实"
    (FACTS:登录、菜单路径、控件选择器、各模式措辞、保存按钮)+ 几行 run()
    说明这台机的**操作顺序**。直接运行:
        python models/Tenda_AX3000.py pppoe
  * models/_driver.py(本文件)—— 所有点击逻辑。它是**库**,不是框架:
    型号脚本调它,而不是它调型号脚本。事实全部显式给出、运行期零猜测,
    因此能直接吃 Playwright 的自动等待;修一个 bug,所有型号同时受益。
  * 适配一台新机型:`tools/probe_router.py`(只读取证 + 引擎实测命中数)
    和 `adapt.py`(给人用的向导),流程见
    .claude/skills/adapt-router-model/SKILL.md。

## 怎么用(型号脚本视角)

规矩机型直接用默认配方,一行就够:

    def run(facts=None, mode="dynamic", **kw):
        return default_run(facts or FACTS, mode, **kw)

操作**顺序**本身是特例的机型(例:WAN 页必须以 iframe 打开),自己拼动词:

    def run(facts=None, mode="dynamic", **kw):
        with session(facts or FACTS, mode, **kw) as s:
            if not s.login():
                return s.fail("登录失败:仍停在登录页")
            s.navigate()
            s.set_mode(force=True)
            s.fill_params()
            return s.apply_and_verify(force=True)

动词清单:`python models/_driver.py --verbs`(从各动词的 docstring 生成,
不会和文档漂移)。

根本不走 Web UI 的机型(有 HTTP API,或只能靠 py2 桥接)用 `browser=False`:
不开浏览器、`s.page` 是 None,回读自己读回来交给 `record_verified()`,
判定出口一个字没变:

    with session(facts or FACTS, mode, browser=False, **kw) as s:
        got = my_http_dial(mode)             # 型号脚本自己下发 + 自己回读
        s.record_verified(got, s.label)      # 精确相等才算通过
        return s.apply_and_verify()

## 回读守卫:success 只有一个出口

`apply_and_verify()` 是**唯一**能产出 `success=True` 的地方,`fail()` 是唯一
的失败出口;裸的"点保存"动词不对外导出。型号脚本永远拿不到写 `success` 的笔
(`_verified` 只有 `set_mode()` 和 `record_verified()` 写得动,两个都强制
一次真实回读、都精确相等比对)。
理由:切错模式这类错误**失败得静默** —— 报 success、截图正常、数据照进报告,
只是那一格测的不是这个模式。别的动词写错会当场报错,这个不会。

## 硬教训(删改前先读 GOTCHAS.md 的 Gotchas 一节;每条都是真机上的假成功)

  * 只有真实回读(控件自己显示的当前值)等于目标措辞才算 success,永远不放宽
    成子串 —— "PPPoEv6" 绝不能被认成 "PPPoE";
  * enable_toggle 只在看不到拨号控件时才碰 —— 绝不会把已开启的页面点关;
  * 弹层选项优先按 option 形态容器匹配,防止点到页面别处的同名文字
    (Tenda IPv6 页的 LAN 区就有一个同叫 "DHCPv6" 的 radio 标签);
  * 所有查找都全 frame 扫 —— 老式 frameset UI(Cudy)的菜单和 WAN 表单在
    不同子 frame 里;
  * 默认不点保存 —— 加 --apply 才真正下发(工具曾在真机上误点过"应用")。

FACTS 的完整结构和每个键的含义见 models/_template.py。
"""
from __future__ import annotations

import argparse
import contextlib
import copy
import json
import os
import re
import sys
from typing import Dict, List, Optional

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from config import Config
from models._browser import Browser
from modes import MODE_REQUIRED_FIELDS, merge_params
import settings as settings_mod

_STEP_MS = 200
# 弹层选项的容器形态:role=option,或 class 里带 opt/option 的元素
# (v-select__option / .opt / MuiOption ...)。精确文本过滤会把"整包 wrapper"
# (如 .v-select__options,text 是所有选项拼一起)自然排除掉。
OPTION_CONTAINERS = "[role='option'], [class*='opt']"


def _norm(text: Optional[str]) -> str:
    return re.sub(r"\s+", " ", (text or "")).strip().lower()


def poll(page, fn, timeout_ms: int, step_ms: int = _STEP_MS):
    """反复执行 fn 直到返回真值或超时;fn 抛异常按'还没好'处理。"""
    waited = 0
    while True:
        try:
            res = fn()
        except Exception:
            res = None
        if res:
            return res
        if waited >= timeout_ms:
            return None
        try:
            page.wait_for_timeout(step_ms)
        except Exception:
            pass
        waited += step_ms


def _first_visible(locator):
    try:
        n = min(locator.count(), 25)
    except Exception:
        return None
    for i in range(n):
        el = locator.nth(i)
        try:
            if el.is_visible():
                return el
        except Exception:
            continue
    return None


def settle(page, ms: int = 300):
    """等页面消化上一步操作(SPA 的重渲染、老 UI 的整页刷新)。"""
    try:
        page.wait_for_timeout(ms)
    except Exception:
        pass


def frames(page):
    """主文档 + 所有子 frame。老式 frameset UI(如 Cudy)的菜单、拨号控件、
    保存键分散在不同的子 frame 里,所有查找都必须全 frame 扫。"""
    try:
        return list(page.frames)
    except Exception:
        return []


def locate(page, sel, require_visible=True):
    """跨所有 frame 找第一个可见匹配;require_visible=False 时也接受隐藏
    元素(被美化插件藏起来的原生 <select> 是 display:none 的)。"""
    for fr in frames(page):
        try:
            loc = fr.locator(sel)
        except Exception:
            continue
        el = _first_visible(loc)
        if el:
            return el
        if not require_visible:
            try:
                if loc.count() > 0:
                    return loc.first
            except Exception:
                pass
    return None


def locate_text(page, text):
    """跨所有 frame 找第一个可见的、文字**精确等于** text 的元素。"""
    for fr in frames(page):
        try:
            el = _first_visible(fr.get_by_text(text, exact=True))
            if el:
                return el
        except Exception:
            continue
    return None


# ---------------------------------------------------------------------------
# facts 处理
# ---------------------------------------------------------------------------
def facts_for(facts: dict, mode: str) -> dict:
    """应用 mode_overrides:被覆盖的键整个替换(含 "modes" / "fields")。"""
    merged = copy.deepcopy(facts)
    override = (facts.get("mode_overrides") or {}).get(mode) or {}
    for key, value in override.items():
        merged[key] = value
    return merged


def available_modes(facts: dict) -> List[str]:
    modes = set((facts.get("modes") or {}).keys())
    modes.update((facts.get("mode_overrides") or {}).keys())
    return sorted(modes)


# ---------------------------------------------------------------------------
# 动词(型号脚本通过 Session 调用;这里的模块级函数供 tools/probe_router.py
# 复用同一套查找语义 —— 探针跑通 = 交付脚本跑得通)
# ---------------------------------------------------------------------------
def login(page, facts: dict, admin_user: str, admin_pass: str) -> bool:
    """填管理密码并登录;返回是否**确实离开了登录页**。

    没出现密码框 = 当作已在会话内(True)。填了却还停在登录页 = False,
    调用方要如实报"登录失败",不能带着未登录状态往下走再误报"找不到拨号控件"。
    """
    lg = facts.get("login") or {}
    pw_sel = lg.get("password") or "input[type=password]"
    # SPA 的登录框是异步挂载的:等它出现,而不是扫一次就放弃。
    pwd = poll(page, lambda: locate(page, pw_sel), 8000)
    if not pwd:
        return True  # 没出现登录框:当作已在会话内
    if admin_user and lg.get("user"):
        user_el = locate(page, lg["user"])
        if user_el:
            user_el.fill(admin_user)
    pwd.fill(admin_pass)
    btn = None
    if lg.get("button"):
        btn = poll(page, lambda: locate(page, lg["button"]), 2000)
    if btn:
        btn.click()
    else:
        pwd.press("Enter")
    # 确认真的离开了登录页(密码框消失);失败就如实报 login failed,
    # 不能带着未登录状态往下走再误报"找不到拨号控件"。
    gone = poll(page, lambda: locate(page, pw_sel) is None, 8000)
    return bool(gone)


def navigate(page, facts: dict, result: dict) -> None:
    """按 FACTS.wan_path 逐个点菜单走到设置页(前缀 sel: 表示用选择器)。"""
    for item in facts.get("wan_path") or []:
        if item.startswith("sel:"):        # 前缀 sel: 表示用选择器点菜单
            el = poll(page, lambda s=item[4:]: locate(page, s), 6000)
        else:                              # 默认按菜单文字精确匹配
            el = poll(page, lambda t=item: locate_text(page, t), 6000)
        if el:
            el.click()
            settle(page)
        else:
            result["warnings"].append("菜单没找到:%r" % item)


def _dial_present(page, dial: dict) -> bool:
    # 美化过的原生 <select> 被有意隐藏(display:none),存在即算在。
    require_visible = dial.get("kind") != "select"
    return locate(page, dial["selector"],
                  require_visible=require_visible) is not None


def _toggle_state(el):
    """开关状态:真 checkbox -> aria-checked/pressed -> class 词元;未知返回 None。"""
    try:
        return el.is_checked()
    except Exception:
        pass
    try:
        ac = el.get_attribute("aria-checked")
        if ac is None:
            ac = el.get_attribute("aria-pressed")
        if ac is not None:
            return ac == "true"
        cls = (el.get_attribute("class") or "").lower()
        tokens = re.split(r"[^a-z0-9]+", cls)
        if any(t in ("checked", "on", "active", "open", "enabled")
               for t in tokens):
            return True
    except Exception:
        pass
    return None


def ensure_enabled(page, facts: dict) -> None:
    """整块表单被一个开关门控时(Tenda 的 IPv6 页)把它打开。

    守卫:**拨号控件已经可见就绝不碰开关** —— 否则会把已启用的页面点关。
    """
    sel = facts.get("enable_toggle")
    if not sel:
        return
    if _dial_present(page, facts["dial"]):
        return  # 拨号控件已在:绝不碰开关(防止把已启用的页面点关)
    el = poll(page, lambda: locate(page, sel), 4000)
    if el and _toggle_state(el) is not True:
        el.click()
        settle(page)


def _set_mode_select(page, facts: dict, label: str, out: dict,
                     force: bool = False) -> None:
    css = facts["dial"]["selector"]
    sel = poll(page, lambda: locate(page, css, require_visible=False), 8000)
    if not sel:
        out["message"] = "没找到拨号控件:%s" % css
        return
    try:
        # force=True:美化隐藏的原生 select 也能驱动;select_option 会派发
        # input+change,美化皮和路由器自己的 JS 都监听得到。
        sel.select_option(label=label, force=True)
    except Exception as exc:
        try:
            seen = sel.evaluate(
                "el => Array.from(el.options).map(o => o.text).join(' / ')")
        except Exception:
            seen = ""
        out["message"] = ("select_option(%r) 失败:%s%s"
                          % (label, exc,
                             "(选项有:%s)" % seen if seen else ""))
        return
    settle(page)
    try:
        read = sel.evaluate(
            "el => el.options[el.selectedIndex]"
            " ? el.options[el.selectedIndex].text : ''") or ""
    except Exception:
        read = ""
    out["read_back"] = read.strip()
    out["verified"] = _norm(read) == _norm(label)


def _value_match(text: str, label: str) -> Optional[str]:
    """触发器文本是否显示着 label:整体精确相等,或某一"行"精确相等
    (trigger 里常混着下拉小图标等杂质文本)。逐行仍是精确匹配 ——
    子串匹配会把 "PPPoEv6" 认成 "PPPoE",这里绝不用 contains。
    命中返回规整后的那段文本,未命中返回 None。"""
    if _norm(text) == _norm(label):
        return text.strip()
    for line in (text or "").splitlines():
        if _norm(line) == _norm(label):
            return line.strip()
    return None


def _set_mode_dropdown(page, facts: dict, label: str, out: dict,
                       force: bool = False) -> None:
    dial_sel = facts["dial"]["selector"]
    # dial.value:可选的回读选择器(值文本所在的子元素);不填就读整个 trigger。
    value_sel = facts["dial"].get("value") or dial_sel
    trigger = poll(page, lambda: locate(page, dial_sel), 8000)
    if not trigger:
        out["message"] = "没找到拨号控件:%s" % dial_sel
        return
    cur = ""
    try:
        cur = trigger.inner_text()
    except Exception:
        pass
    hit = _value_match(cur, label)
    if hit is not None:
        # 选择器钉住的就是真控件,它显示的当前值即真实回读,可信。
        out["read_back"] = hit
        out["verified"] = True
        return
    trigger.click(force=force)
    settle(page)
    rx = re.compile(r"^\s*%s\s*$" % re.escape(label), re.IGNORECASE)
    containers = facts.get("options") or OPTION_CONTAINERS
    # 先只认 option 形态的容器(弹层是异步挂载的,轮询等它);实在没有,
    # 最后才退回"页面上任何精确同文字"——这一步放在轮询之外,防止弹层
    # 还没渲染时就抓走页面别处的同名文字(IPv6 页的 DHCPv6 radio 教训)。
    def find_option():
        for fr in frames(page):
            try:
                el = _first_visible(fr.locator(containers).filter(has_text=rx))
                if el:
                    return el
            except Exception:
                continue
        return None

    opt = poll(page, find_option, 3000)
    if not opt:
        opt = locate_text(page, label)
    if not opt:
        seen = []
        for fr in frames(page):
            try:
                loc = fr.locator(containers)
                for i in range(min(loc.count(), 12)):
                    t = (loc.nth(i).inner_text() or "").strip()
                    if t and len(t) < 30 and t not in seen:
                        seen.append(t)
            except Exception:
                continue
        out["message"] = ("下拉打开了,但没找到选项 %r%s"
                          % (label,
                             "(看到:%s)" % " / ".join(seen) if seen else ""))
        return
    opt.click(force=force)
    settle(page, 400)

    def read_now() -> str:
        el = locate(page, value_sel)
        try:
            return (el.inner_text() or "").strip() if el else ""
        except Exception:
            return ""

    # 重新定位再读:框架可能在变更时整个重渲染 trigger,旧句柄不可靠。
    poll(page, lambda: _value_match(read_now(), label) is not None, 2000)
    hit = _value_match(read_now(), label)
    out["read_back"] = hit if hit is not None else read_now()
    out["verified"] = hit is not None


def _set_mode_radio(page, facts: dict, mode: str, label: str, out: dict,
                    force: bool = False) -> None:
    """kind=radio:modes 的值是每个模式各自 radio 的选择器。
    只信真 radio 的 is_checked();读不到状态就不许报成功。"""
    el = poll(page, lambda: locate(page, label), 8000)
    if not el:
        out["message"] = "没找到模式 radio:%s" % label
        return
    try:
        el.click(force=force)
    except Exception as exc:
        # 最常见的原因:radio 被皮/遮罩盖住,Playwright 的可操作性检查超时
        # (报 "... intercepts pointer events")。那是 set_mode(force=True)
        # 解决的问题,不该以一条 traceback 收场。
        out["message"] = ("点 %s 的 radio 失败:%s%s"
                          % (mode, str(exc).splitlines()[0],
                             "" if force else
                             "(控件被别的元素盖住时,run() 里改成 "
                             "set_mode(force=True))"))
        return
    settle(page)
    try:
        checked = el.is_checked()
    except Exception:
        out["message"] = ("点了 %s 但它不是可回读的 radio —— "
                          "换 kind=dropdown/select 或修正选择器。" % label)
        return
    # radio 的"措辞"是个选择器,报出来没有意义 —— 回读记模式名。
    out["read_back"] = mode if checked else ""
    out["verified"] = bool(checked)


def fill_params(page, facts: dict, mode: str, params: Dict[str, str],
                result: dict) -> None:
    """按模式填账密/服务器地址;只填这个模式要的概念,PPPoE 账密不会漏进 dynamic。"""
    fields = facts.get("fields") or {}
    concepts = list(MODE_REQUIRED_FIELDS.get(mode, []))
    for k in params:              # 显式给的参数永远尝试填(如 PPPoEv6 账密)
        if k not in concepts:
            concepts.append(k)
    for concept in concepts:
        value = params.get(concept)
        if value is None:
            continue
        sel = fields.get(concept)
        if not sel:
            result["warnings"].append("FACTS.fields 缺 %r 的选择器" % concept)
            continue
        # 账密输入框在选完模式后才挂载,等它出现。
        el = poll(page, lambda s=sel: locate(page, s), 3000)
        if el:
            el.fill(str(value))
            result["filled"].append(concept)
        else:
            result["warnings"].append("输入框没出现:%s -> %s" % (concept, sel))


def _apply(page, facts: dict, result: dict, force: bool = False) -> None:
    """点保存键。**私有** —— 只有 Session.apply_and_verify() 能调它,
    这样"点了保存"永远伴随一次真实回读判定,不会各自为政。"""
    sel = facts.get("apply")
    if not sel:
        result["warnings"].append("FACTS 没写 apply(保存键)选择器")
        return
    el = poll(page, lambda: locate(page, sel), 3000)
    if el:
        el.click(force=force)
        result["applied"] = True
        # 保存后要等多久由型号说了算:多数机型 0.5 秒就够,Buffalo 是 iframe
        # 里异步提交 + 轮询,点完立刻关浏览器等于把保存打断(FACTS 里配 15 秒)。
        settle(page, facts.get("apply_settle_ms", 500))
    else:
        # 证据优先:把页面上实际可见的按钮列出来,失败信息自己就能定位问题
        # (例:真机按钮文字在里层 span,:text-is 会漏 —— 得换锚定写法)。
        seen = []
        for fr in frames(page):
            try:
                loc = fr.locator("button, input[type=submit], input[type=button]")
                for i in range(min(loc.count(), 12)):
                    b = loc.nth(i)
                    try:
                        if not b.is_visible():
                            continue
                        t = (b.inner_text() or "").strip()
                        if not t:      # input[type=submit] 的文字在 value 里
                            try:
                                t = (b.input_value() or "").strip()
                            except Exception:
                                t = ""
                    except Exception:
                        continue
                    if t and t not in seen:
                        seen.append(t)
            except Exception:
                continue
        result["warnings"].append(
            "保存键没找到:%s%s"
            % (sel, "(页面可见按钮:%s)" % " / ".join(seen) if seen else ""))


def screenshot(page, cfg: Config, facts: dict, mode: str) -> str:
    """整页截图存进 artifacts/,返回路径(失败返回空串,绝不因此中断一轮)。"""
    try:
        os.makedirs(cfg.screenshot_dir, exist_ok=True)
        slug = re.sub(r"[^A-Za-z0-9]+", "_", "%s_%s" % (
            facts.get("brand", ""), facts.get("model", ""))).strip("_").lower()
        path = os.path.join(cfg.screenshot_dir,
                            "model_%s_%s.png" % (slug or "unknown", mode))
        page.screenshot(path=path, full_page=True)
        return path
    except Exception:
        return ""


# ---------------------------------------------------------------------------
# Session:一次切换的上下文。型号脚本按自己的顺序调这些动词。
# ---------------------------------------------------------------------------
class Session:
    """一次拨号切换的上下文:page + 这台机的 FACTS(已套 mode_overrides)+
    正在累积的结果。

    **success 只能由 apply_and_verify() 从一次真实回读算出来**,型号脚本没有
    别的路子把一轮标成成功;失败一律走 fail()。见本文件顶部「回读守卫」。
    """

    def __init__(self, facts: dict, mode: str, params=None, apply=False,
                 admin_user="", admin_pass="", verify_hook=None,
                 browser=True):
        self.facts = facts
        self.mode = mode
        self.label = (facts.get("modes") or {}).get(mode, "")
        self.page = None
        self.cfg = None
        self._params = params or {}
        self._apply_requested = bool(apply)
        self._verify_hook = verify_hook
        self._admin_user = admin_user
        self._admin_pass = admin_pass
        # browser=False:HTTP/CLI 路线,page 恒为 None。浏览器动词一律当场报错,
        # 回读改由 record_verified() 写 —— 见 session() 的 browser 参数。
        self._has_browser = bool(browser)
        self._verified = False          # 只有 set_mode()/record_verified() 能写
        self._aborted = False
        self._result = {
            "brand": facts.get("brand", ""), "model": facts.get("model", ""),
            "mode": mode, "success": False, "read_back": "",
            "filled": [], "applied": False, "message": "",
            "warnings": [], "screenshot": "",
        }

    # -- 内部 ---------------------------------------------------------------
    def _bind(self, page, cfg) -> None:
        self.page = page
        self.cfg = cfg

    def _abort(self, message: str) -> None:
        """开浏览器之前就判定这一轮跑不了(例:型号脚本没声明这个模式)。
        之后所有动词都是空操作,fail()/apply_and_verify() 保留这条原因。"""
        self._aborted = True
        self._result["message"] = message

    def _needs_browser(self, verb: str) -> None:
        """browser=False 的会话里调浏览器动词 = 接线写错了,当场抛异常。

        不能静默返回:page 是 None,静默 return 会让 run() 一路走到
        apply_and_verify() —— 而 _verified 可能是别处写的,于是报出一个
        "那一步根本没做过"的成功。这不是设备状况(设备状况要如实 fail()),
        是型号脚本写错了路线,必须当场炸掉。
        """
        if not self._has_browser:
            raise RuntimeError(
                "%s() 需要浏览器,当前 session 是 browser=False"
                "(HTTP/CLI 路线不开浏览器,self.page 是 None)。"
                "这条路线用 record_verified(read_back, expected) 记回读,"
                "再走 apply_and_verify();要用浏览器就别传 browser=False。"
                % verb)

    def _shot(self) -> None:
        if self.page is not None and self.cfg is not None:
            self._result["screenshot"] = screenshot(
                self.page, self.cfg, self.facts, self.mode)

    # -- 动词 ---------------------------------------------------------------
    def warn(self, message: str) -> None:
        """记一条警告(不影响成败判定,但会进报告)。"""
        self._result["warnings"].append(message)

    def login(self) -> bool:
        """按 FACTS.login 登录;返回是否确实离开了登录页。"""
        if self._aborted:
            return False
        self._needs_browser("login")
        return login(self.page, self.facts, self._admin_user, self._admin_pass)

    def navigate(self) -> None:
        """按 FACTS.wan_path 点菜单走到设置页;找不到的菜单记成警告。"""
        if self._aborted:
            return
        self._needs_browser("navigate")
        navigate(self.page, self.facts, self._result)

    def goto_iframe(self, target: Optional[str] = None,
                    ready_js: Optional[str] = None,
                    parent_url: Optional[str] = None,
                    attempts: int = 10) -> bool:
        """把设置页**以 iframe 的形式**打开,并确认它真的就绪才返回 True。

        有的机型(Buffalo)的设置页直接打开也能渲染、控件也能点、回读也通过,
        但页面的配置对象没加载,保存提交的是**旧值** —— 一次 DOM 上完全看不
        出来的假成功。所以就绪 = 三个条件同时成立:url 到位、配置对象到位
        (FACTS.iframe_ready_js)、拨号控件已出现。只看 url 是不够的。

        菜单点不动的机型才用它(能点菜单就用 navigate)。要重试是因为页面自己
        的脚本有时会把 iframe 的地址改回去。
        """
        if self._aborted:
            return False
        self._needs_browser("goto_iframe")
        sel = self.facts.get("iframe_selector")
        target = target or self.facts.get("iframe_target")
        ready_js = ready_js or self.facts.get("iframe_ready_js")
        parent = parent_url or self.facts.get("url")
        if not sel or not target:
            self.warn("goto_iframe 需要 FACTS 里的 iframe_selector 和 "
                      "iframe_target(当前:%r / %r)" % (sel, target))
            return False

        # 登录后可能被跳到别的页:先确保主文档回到外壳页,否则 iframe 不在。
        leaf = (parent or "").rstrip("/").split("/")[-1].split("?")[0]
        if leaf and leaf not in (self.page.url or ""):
            try:
                self.page.goto(parent, wait_until="domcontentloaded")
            except Exception as exc:
                self.warn("回到外壳页 %s 失败:%s" % (parent, exc))
        settle(self.page)

        dial_sel = (self.facts.get("dial") or {}).get("selector") or ""
        seen_url = ""

        def ready():
            fl = self.page.frame_locator(sel)
            root = fl.locator(":root")
            here = root.evaluate("() => location.href") or ""
            if target.split("?")[0] not in here:
                return False
            if ready_js:
                # 配置对象可能还没赋值 —— 求值抛异常按"还没好"处理。
                good = root.evaluate(
                    "() => { try { return !!(%s); } catch (e) { return false; } }"
                    % ready_js)
                if not good:
                    return False
            if dial_sel and fl.locator(dial_sel).count() < 1:
                return False
            return here

        for _ in range(max(1, attempts)):
            try:
                self.page.evaluate(
                    """([sel, target]) => {
                        var frm = document.querySelector(sel);
                        if (!frm) throw new Error("iframe not found: " + sel);
                        var rnd = parseInt(Math.random() * 100000000);
                        frm.contentWindow.location.href =
                            target + (target.indexOf('?') < 0 ? '?' : '&')
                            + 'rnd=' + rnd;
                    }""", [sel, target])
            except Exception as exc:
                self.warn("设置 iframe 地址失败:%s" % exc)
                return False
            settle(self.page, 500)
            hit = poll(self.page, ready, 8000)
            if hit:
                return True
            try:
                seen_url = self.page.frame_locator(sel).locator(
                    ":root").evaluate("() => location.href") or ""
            except Exception:
                pass
            # 页面脚本把地址改回去了 / 配置还没到位:再来一轮。
        self._result["message"] = (
            "%s 没在 iframe 里就绪(试了 %d 轮)。iframe 当前 url=%r;"
            "就绪判据 %r 未成立 —— 这一步不通过就绝不能往下走,"
            "否则保存下去的是旧值。" % (target, attempts, seen_url, ready_js))
        return False

    def ensure_enabled(self) -> None:
        """整块表单被开关门控时打开它;拨号控件已可见就绝不碰(防止点关)。"""
        if self._aborted:
            return
        self._needs_browser("ensure_enabled")
        ensure_enabled(self.page, self.facts)

    def set_mode(self, force: bool = False) -> bool:
        """选到目标拨号方式,**并当场真实回读**。回读==目标措辞才算验证通过。

        force=True 用于被 CSS 遮住的控件(Playwright 的可操作性检查会超时)。
        """
        if self._aborted:
            return False
        self._needs_browser("set_mode")
        kind = (self.facts.get("dial") or {}).get("kind", "dropdown")
        out = {"read_back": "", "verified": False, "message": ""}
        if kind == "select":
            _set_mode_select(self.page, self.facts, self.label, out, force)
        elif kind == "radio":
            _set_mode_radio(self.page, self.facts, self.mode, self.label,
                            out, force)
        else:
            _set_mode_dropdown(self.page, self.facts, self.label, out, force)
        self._result["read_back"] = out["read_back"]
        if out["message"]:
            self._result["message"] = out["message"]
        self._verified = bool(out["verified"])
        return self._verified

    def record_verified(self, read_back: str, expected: str) -> bool:
        """非浏览器路线(HTTP/CLI)记一次**真实回读**,并据此写 _verified。

        比对是**精确相等**(只规整空白和大小写,和 set_mode() 同一把尺子),
        永不放宽成包含 —— 否则 "PPPoEv6" 会被认成 "PPPoE"。空回读永不算通过。
        read_back 对不对都记进结果:不对的时候它就是失败信息里的那份证据。

        这是 set_mode() 之外**唯一**能写 _verified 的地方(别开第三个);
        success 仍然只能由 apply_and_verify() 产出。
        """
        if self._aborted:
            return False
        got = ("" if read_back is None else str(read_back)).strip()
        self._result["read_back"] = got
        # bool(got):回读和目标同时为空时 _norm 相等 —— 那是"什么都没读到",
        # 绝不是通过。
        self._verified = bool(got) and _norm(got) == _norm(expected)
        if not self._verified:
            self._result["message"] = (
                "回读没通过:设备回读 %r,目标是 %r(精确相等比对,不放宽成包含)"
                % (got, expected))
        elif self._result["message"].startswith("回读没通过:"):
            # 重试的第二次读通过了:把上一次那条清掉,别让一轮成功的结果里
            # 挂着一句"回读没通过"(只清我们自己写的那句,别人的原样留着)。
            self._result["message"] = ""
        return self._verified

    def fill_params(self, params: Optional[Dict[str, str]] = None) -> None:
        """填这个模式要的账密/服务器地址。**回读没通过就不填** —— 页面状态
        还不明,填进去等于往未知表单里打字。"""
        if self._aborted:
            return
        self._needs_browser("fill_params")
        if not self._verified:
            return
        use = self._params if params is None else params
        page_of_fields = self.facts.get("fields_page")
        if page_of_fields:
            # 账密框在别的页面:说出来,绝不静默装作填过了。
            for key in sorted(use or {}):
                if (use or {})[key]:
                    self.warn("参数 %s 没有填:它的输入框在 %s,和拨号页不是"
                              "同一页。请先在路由器 Web UI 里配好。"
                              % (key, page_of_fields))
            return
        fill_params(self.page, self.facts, self.mode, use or {}, self._result)

    def apply_and_verify(self, force: bool = False) -> dict:
        """**唯一的成功出口。** 用 set_mode() 那次真实回读判定 success;
        只有验证通过且这一轮要求下发时才点保存,然后跑 verify_hook + 截图。

        browser=False 时跳过"点保存"(HTTP 路线没有保存键,下发即生效),
        判定照旧只看回读 —— 这条路线的回读由 record_verified() 写。
        """
        self._result["success"] = bool(self._verified) and not self._aborted
        if (self._result["success"] and self._apply_requested
                and self._has_browser):
            _apply(self.page, self.facts, self._result, force=force)
        if not self._result["success"] and not self._result["message"]:
            self._result["message"] = (
                "回读没通过:控件当前显示 %r,目标是 %r"
                % (self._result["read_back"], self.label))
        if self._verify_hook and self.page is not None:
            try:
                self._result["verify"] = self._verify_hook(self.page,
                                                           self._result)
            except Exception as exc:
                self.warn("verify_hook: %s" % exc)
        self._shot()
        return self._result

    def fail(self, message: str) -> dict:
        """**唯一的失败出口。** success 恒为 False;截图留证。
        _abort() 已经写下原因时保留原因(那条更贴近真正的病因)。"""
        self._result["success"] = False
        if not self._aborted:
            self._result["message"] = message
        self._shot()
        return self._result


@contextlib.contextmanager
def session(facts: dict, mode: str, params: Optional[Dict[str, str]] = None,
            apply: bool = False, admin_user: str = "", admin_pass: str = "",
            url: Optional[str] = None, headless: Optional[bool] = None,
            config: Optional[Config] = None, verify_hook=None,
            browser: bool = True):
    """开浏览器、套 mode_overrides、落在设置页的起点,yield 一个 Session。

    型号脚本 run() 的标准开头。模式名型号脚本没声明时**不开浏览器**就短路
    (打错一个模式名不该弹出一个 Chrome)。

    browser=False:**不开浏览器、不开页面**,`s.page` 恒为 None。给"根本不走
    Web UI"的路线用(有 HTTP API / 只能靠 py2 桥接的机型)。除浏览器之外一切
    照旧:mode_overrides 已合并、凭据已带进来(调用方从 router.yaml 取,和
    浏览器路线同一条)、result 已构造、_aborted 照样判。浏览器动词一律抛
    RuntimeError,回读改用 `record_verified()`,判定仍然只有
    `apply_and_verify()` 一个出口;退出时不截图(screenshot 留空串)。
    """
    mode = (mode or "").lower()
    merged = facts_for(facts, mode)
    sess = Session(merged, mode, params=params, apply=apply,
                   admin_user=admin_user, admin_pass=admin_pass,
                   verify_hook=verify_hook, browser=browser)
    if mode not in (merged.get("modes") or {}):
        sess._abort("此型号脚本未定义模式 %r(可用:%s)"
                    % (mode, ", ".join(available_modes(merged))))
        yield sess
        return

    if not browser:
        # 不建 Config、不动 http_pass、不进 Browser 的 with:没有浏览器可配,
        # 碰了只是副作用(config 是调用方的对象)。
        if url:
            # 说出来,别悄悄丢:没有浏览器可导航,这条路线要换地址得由 run()
            # 自己接 url 参数,否则人以为切了机器、其实还在打老地址。
            sess.warn("browser=False:url=%r 被忽略(没有浏览器可导航)。"
                      "这条路线的目标地址由型号脚本自己处理。" % url)
        yield sess
        return

    cfg = config or Config()
    if headless is not None:
        cfg.headless = headless
    # 管理密码同时给 HTTP Basic 用:老机型的登录可能是浏览器原生弹窗
    # (DOM 里没有密码框,填选择器永远填不到)。不是 Basic 的机器不受影响。
    if admin_pass and not cfg.http_pass:
        cfg.http_user, cfg.http_pass = (admin_user or "admin"), admin_pass
    with Browser(cfg) as br:
        sess._bind(br.goto(url or merged["url"]), cfg)
        yield sess


# ---------------------------------------------------------------------------
# 默认配方 + 入口
# ---------------------------------------------------------------------------
def default_run(facts: dict, mode: str, params: Optional[Dict[str, str]] = None,
                apply: bool = False, admin_user: str = "", admin_pass: str = "",
                url: Optional[str] = None, headless: Optional[bool] = None,
                config: Optional[Config] = None, verify_hook=None) -> dict:
    """**默认配方**:规矩机型的操作顺序 —— 登录 → 走菜单 → 开门控开关 →
    选模式(含真实回读)→ 填账密 → 保存。

    绝大多数型号的 run() 就是转调这一个函数。顺序本身是特例的机型自己拼动词
    (见本文件顶部的用法),但成败判定仍然只能走 apply_and_verify()。

    apply=False(默认)= 只定位+选择+填参,不点保存;apply=True 才真正下发。
    verify_hook: 可选 callable(page, result),在关浏览器前调用,返回值存进
    result["verify"] —— 冒烟测试用它读页面状态,将来接"WAN 真拨通"验证也在这。
    """
    with session(facts, mode, params=params, apply=apply,
                 admin_user=admin_user, admin_pass=admin_pass, url=url,
                 headless=headless, config=config,
                 verify_hook=verify_hook) as s:
        if not s.login():
            return s.fail("login failed —— 仍停在登录页。检查管理密码;"
                          "注意部分机型(如 Tenda/Mercusys)同一时间只"
                          "允许一个 Web 会话,先关掉其他已登录的页签。")
        s.navigate()
        s.ensure_enabled()
        s.set_mode()
        s.fill_params()
        return s.apply_and_verify()


def console_safe() -> None:
    """台架 Windows 控制台是 GBK(cp936),管道时 Python 也按 GBK 编码输出。
    路由器回读的文字里只要有一个 GBK 编不出的字符,print 就会抛
    UnicodeEncodeError 把整轮打断 —— 在最不该崩的时候崩。改成用 ? 顶掉。
    (2026-07-28 台架实测:start.py 打印 U+2713 时就这么炸过。)"""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors="replace")
        except Exception:                      # 老 Python / 非标准流:忽略
            pass


# 动词清单:从 docstring 首行生成,不用手工维护第二份文档。
_VERB_NAMES = ("login", "navigate", "goto_iframe", "ensure_enabled", "set_mode",
               "record_verified", "fill_params", "apply_and_verify", "fail",
               "warn")


def verbs() -> List[tuple]:
    """返回 [(动词名, docstring 首行)] —— `python models/_driver.py --verbs`
    打的就是它。文档从代码生成,不会漂移。"""
    out = []
    for name in _VERB_NAMES:
        fn = getattr(Session, name, None)
        doc = ((fn.__doc__ or "").strip().splitlines() or [""])[0]
        out.append((name, doc))
    return out


def run_cli(facts: dict, argv: Optional[List[str]] = None, runner=None) -> int:
    """型号脚本的 main:python models/<型号>.py <mode> [--apply] [--param k=v]。

    runner: 这台机的 run()。型号脚本尾行写 `run_cli(FACTS, runner=run)`,
    这样单跑和整轮(matrix/run.py 的 runner_for)走的是同一条流程 ——
    忘了传会退回默认配方,`tools/check_model.py` 会离线拦下。

    管理密码 / 宽带账密默认取 router.yaml(python start.py --setup 生成),
    并按模式过滤 —— PPPoE 账密绝不会带进 dynamic 运行。
    """
    console_safe()
    saved = settings_mod.load()
    parser = argparse.ArgumentParser(
        description="%s %s —— WAN 拨号方式切换(默认只切换不保存,"
                    "加 --apply 才真正下发)"
                    % (facts.get("brand", ""), facts.get("model", "")))
    parser.add_argument("mode", choices=available_modes(facts),
                        help="目标拨号方式")
    parser.add_argument("--apply", action="store_true",
                        help="真正点保存/连接(默认不点,先看回读)")
    parser.add_argument("--url", default=None,
                        help="覆盖脚本里的路由器地址(默认 %s)"
                             % facts.get("url", ""))
    parser.add_argument("--user", default=saved.get("user", ""),
                        help="管理用户名(多数机型不需要)")
    parser.add_argument("--pass", dest="password",
                        default=saved.get("pass", ""),
                        help="管理密码(默认取 router.yaml)")
    parser.add_argument("--param", action="append", default=[], metavar="k=v",
                        help="模式参数,如 pppoe_user=xxx(默认按模式从 "
                             "router.yaml 取)")
    parser.add_argument("--headless", action="store_true", help="无窗口运行")
    args = parser.parse_args(argv)

    # FACTS 声明了登录页 => 必须有管理密码,否则开跑前就报错,
    # 不要开着浏览器白跑一趟再"卡在登录页"。
    if facts.get("login") and not args.password:
        parser.error(
            "没有管理密码:先跑一次 `python start.py --setup` 把路由器 IP/密码存进 "
            "router.yaml(git 已忽略,不会进仓库),或本次直接加 --pass <管理密码>。")

    explicit: Dict[str, str] = {}
    for item in args.param:
        if "=" in item:
            k, v = item.split("=", 1)
            explicit[k.strip()] = v
    params = merge_params(args.mode, saved.get("params") or {}, explicit)
    missing = [f for f in MODE_REQUIRED_FIELDS.get(args.mode, [])
               if f not in params]
    # fields_page = 这台机的账密框在**别的页面**,本脚本填不了(Buffalo 的
    # pppoe_reg.html)。那就不该拦着不让切 —— 要人补一个工具根本填不进去的
    # 参数,是把 tool 的短板变成用户的错。run() 会为此发一条警告。
    if missing and not facts.get("fields_page"):
        parser.error("模式 %s 还缺参数:%s(用 --param k=v 提供,"
                     "或先跑 python start.py --setup 存进 router.yaml)"
                     % (args.mode, ", ".join(missing)))

    res = (runner or default_run)(
        facts, args.mode, params=params, apply=args.apply,
        admin_user=args.user, admin_pass=args.password, url=args.url,
        headless=args.headless or bool(saved.get("headless")))
    print(json.dumps(res, ensure_ascii=False, indent=2))
    if res["success"] and not args.apply:
        print("[hint] 已确认切换(回读=%r)但未点保存;加 --apply 真正下发。"
              % res["read_back"])
    return 0 if res["success"] else 2


if __name__ == "__main__":
    console_safe()
    if "--verbs" in sys.argv:
        print("Session 的动词(型号脚本的 run() 按自己的顺序调它们):\n")
        for name, doc in verbs():
            print("  %-18s %s" % (name, doc))
        print("\n默认配方(规矩机型直接用):default_run(FACTS, mode, ...)")
        print("成功判定只有一个出口:apply_and_verify();失败只有 fail()。")
        sys.exit(0)
    sys.exit("models/_driver.py 是库,不是入口。\n"
             "  看动词清单:python models/_driver.py --verbs\n"
             "  切一次拨号:python models/<品牌>_<型号>.py <mode>")
