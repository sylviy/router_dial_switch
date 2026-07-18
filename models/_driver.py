"""每个型号脚本(models/<品牌>_<型号>.py)共用的小运行时。

分层(2026-07-16 起,按导师定的交付形态):
  * models/<品牌>_<型号>.py —— **交付物**。一个文件 = 一台型号的全部"事实"
    (FACTS:登录、菜单路径、控件选择器、各模式措辞、保存按钮),直接运行:
        python models/Tenda_AX3000.py pppoe
  * models/_driver.py(本文件)—— 唯一的点击逻辑,所有型号共用。事实全部
    显式给出、运行期零猜测,因此能直接吃 Playwright 的自动等待,不需要
    engine/ 的启发式;修一个 bug,所有型号脚本同时受益。
  * engine/ —— "适配期工具箱":面对新型号先用 `python cli.py diagnose`
    取证,再照 .claude/skills/adapt-router-model 的流程产出新的型号脚本。

从 engine 沿用的硬教训(删改前先读 CLAUDE.md 的 Gotchas):
  * 只有真实回读(控件自己显示的当前值)等于目标措辞才算 success;
  * enable_toggle 只在看不到拨号控件时才碰 —— 绝不会把已开启的页面点关;
  * 弹层选项优先按 option 形态容器匹配,防止点到页面别处的同名文字
    (Tenda IPv6 页的 LAN 区就有一个同叫 "DHCPv6" 的 radio 标签);
  * 默认不点保存 —— 加 --apply 才真正下发(工具曾在真机上误点过"应用")。

FACTS 的完整结构和每个键的含义见 models/_template.py。
"""
from __future__ import annotations

import argparse
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
from engine.browser import Browser
from engine.adapter import MODE_REQUIRED_FIELDS
from cli import merge_params
import settings as settings_mod

_STEP_MS = 200
# 弹层选项的容器形态:role=option,或 class 里带 opt/option 的元素
# (v-select__option / .opt / MuiOption ...)。精确文本过滤会把"整包 wrapper"
# (如 .v-select__options,text 是所有选项拼一起)自然排除掉。
_OPTION_CONTAINERS = "[role='option'], [class*='opt']"


def _norm(text: Optional[str]) -> str:
    return re.sub(r"\s+", " ", (text or "")).strip().lower()


def _poll(page, fn, timeout_ms: int, step_ms: int = _STEP_MS):
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


def _settle(page, ms: int = 300):
    try:
        page.wait_for_timeout(ms)
    except Exception:
        pass


def _frames(page):
    """主文档 + 所有子 frame。老式 frameset UI(如 Cudy)的菜单、拨号控件、
    保存键分散在不同的子 frame 里,所有查找都必须全 frame 扫。"""
    try:
        return list(page.frames)
    except Exception:
        return []


def _locate(page, sel, require_visible=True):
    """跨所有 frame 找第一个可见匹配;require_visible=False 时也接受隐藏
    元素(被美化插件藏起来的原生 <select> 是 display:none 的)。"""
    for fr in _frames(page):
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


def _locate_text(page, text):
    for fr in _frames(page):
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
# 步骤
# ---------------------------------------------------------------------------
def _login(page, facts: dict, admin_user: str, admin_pass: str) -> bool:
    lg = facts.get("login") or {}
    pw_sel = lg.get("password") or "input[type=password]"
    # SPA 的登录框是异步挂载的:等它出现,而不是扫一次就放弃。
    pwd = _poll(page, lambda: _locate(page, pw_sel), 8000)
    if not pwd:
        return True  # 没出现登录框:当作已在会话内
    if admin_user and lg.get("user"):
        user_el = _locate(page, lg["user"])
        if user_el:
            user_el.fill(admin_user)
    pwd.fill(admin_pass)
    btn = None
    if lg.get("button"):
        btn = _poll(page, lambda: _locate(page, lg["button"]), 2000)
    if btn:
        btn.click()
    else:
        pwd.press("Enter")
    # 确认真的离开了登录页(密码框消失);失败就如实报 login failed,
    # 不能带着未登录状态往下走再误报"找不到拨号控件"。
    gone = _poll(page, lambda: _locate(page, pw_sel) is None, 8000)
    return bool(gone)


def _navigate(page, facts: dict, result: dict) -> None:
    for item in facts.get("wan_path") or []:
        if item.startswith("sel:"):        # 前缀 sel: 表示用选择器点菜单
            el = _poll(page, lambda s=item[4:]: _locate(page, s), 6000)
        else:                              # 默认按菜单文字精确匹配
            el = _poll(page, lambda t=item: _locate_text(page, t), 6000)
        if el:
            el.click()
            _settle(page)
        else:
            result["warnings"].append("菜单没找到:%r" % item)


def _dial_present(page, dial: dict) -> bool:
    # 美化过的原生 <select> 被有意隐藏(display:none),存在即算在。
    require_visible = dial.get("kind") != "select"
    return _locate(page, dial["selector"],
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


def _ensure_enabled(page, facts: dict) -> None:
    sel = facts.get("enable_toggle")
    if not sel:
        return
    if _dial_present(page, facts["dial"]):
        return  # 拨号控件已在:绝不碰开关(防止把已启用的页面点关)
    el = _poll(page, lambda: _locate(page, sel), 4000)
    if el and _toggle_state(el) is not True:
        el.click()
        _settle(page)


def _set_mode_select(page, facts: dict, label: str, result: dict) -> None:
    css = facts["dial"]["selector"]
    sel = _poll(page, lambda: _locate(page, css, require_visible=False), 8000)
    if not sel:
        result["message"] = "没找到拨号控件:%s" % css
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
        result["message"] = ("select_option(%r) 失败:%s%s"
                             % (label, exc,
                                "(选项有:%s)" % seen if seen else ""))
        return
    _settle(page)
    try:
        read = sel.evaluate(
            "el => el.options[el.selectedIndex]"
            " ? el.options[el.selectedIndex].text : ''") or ""
    except Exception:
        read = ""
    result["read_back"] = read.strip()
    result["success"] = _norm(read) == _norm(label)


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


def _set_mode_dropdown(page, facts: dict, label: str, result: dict) -> None:
    dial_sel = facts["dial"]["selector"]
    # dial.value:可选的回读选择器(值文本所在的子元素);不填就读整个 trigger。
    value_sel = facts["dial"].get("value") or dial_sel
    trigger = _poll(page, lambda: _locate(page, dial_sel), 8000)
    if not trigger:
        result["message"] = "没找到拨号控件:%s" % dial_sel
        return
    cur = ""
    try:
        cur = trigger.inner_text()
    except Exception:
        pass
    hit = _value_match(cur, label)
    if hit is not None:
        # 选择器钉住的就是真控件,它显示的当前值即真实回读,可信。
        result["read_back"] = hit
        result["success"] = True
        return
    trigger.click()
    _settle(page)
    rx = re.compile(r"^\s*%s\s*$" % re.escape(label), re.IGNORECASE)
    containers = facts.get("options") or _OPTION_CONTAINERS
    # 先只认 option 形态的容器(弹层是异步挂载的,轮询等它);实在没有,
    # 最后才退回"页面上任何精确同文字"——这一步放在轮询之外,防止弹层
    # 还没渲染时就抓走页面别处的同名文字(IPv6 页的 DHCPv6 radio 教训)。
    def find_option():
        for fr in _frames(page):
            try:
                el = _first_visible(fr.locator(containers).filter(has_text=rx))
                if el:
                    return el
            except Exception:
                continue
        return None

    opt = _poll(page, find_option, 3000)
    if not opt:
        opt = _locate_text(page, label)
    if not opt:
        seen = []
        for fr in _frames(page):
            try:
                loc = fr.locator(containers)
                for i in range(min(loc.count(), 12)):
                    t = (loc.nth(i).inner_text() or "").strip()
                    if t and len(t) < 30 and t not in seen:
                        seen.append(t)
            except Exception:
                continue
        result["message"] = ("下拉打开了,但没找到选项 %r%s"
                             % (label,
                                "(看到:%s)" % " / ".join(seen) if seen else ""))
        return
    opt.click()
    _settle(page, 400)

    def read_now() -> str:
        el = _locate(page, value_sel)
        try:
            return (el.inner_text() or "").strip() if el else ""
        except Exception:
            return ""

    # 重新定位再读:框架可能在变更时整个重渲染 trigger,旧句柄不可靠。
    _poll(page, lambda: _value_match(read_now(), label) is not None, 2000)
    hit = _value_match(read_now(), label)
    result["read_back"] = hit if hit is not None else read_now()
    result["success"] = hit is not None


def _set_mode_radio(page, facts: dict, label: str, result: dict) -> None:
    """kind=radio:modes 的值是每个模式各自 radio 的选择器。
    只信真 radio 的 is_checked();读不到状态就不许报成功。"""
    el = _poll(page, lambda: _locate(page, label), 8000)
    if not el:
        result["message"] = "没找到模式 radio:%s" % label
        return
    el.click()
    _settle(page)
    try:
        checked = el.is_checked()
    except Exception:
        result["message"] = ("点了 %s 但它不是可回读的 radio —— "
                             "换 kind=dropdown/select 或修正选择器。" % label)
        return
    result["read_back"] = label if checked else ""
    result["success"] = bool(checked)


def _fill_params(page, facts: dict, mode: str, params: Dict[str, str],
                 result: dict) -> None:
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
        el = _poll(page, lambda s=sel: _locate(page, s), 3000)
        if el:
            el.fill(str(value))
            result["filled"].append(concept)
        else:
            result["warnings"].append("输入框没出现:%s -> %s" % (concept, sel))


def _apply(page, facts: dict, result: dict) -> None:
    sel = facts.get("apply")
    if not sel:
        result["warnings"].append("FACTS 没写 apply(保存键)选择器")
        return
    el = _poll(page, lambda: _locate(page, sel), 3000)
    if el:
        el.click()
        result["applied"] = True
        _settle(page, 500)
    else:
        # 证据优先:把页面上实际可见的按钮列出来,失败信息自己就能定位问题
        # (例:真机按钮文字在里层 span,:text-is 会漏 —— 得换锚定写法)。
        seen = []
        for fr in _frames(page):
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


def _screenshot(page, cfg: Config, facts: dict, mode: str) -> str:
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
# 入口
# ---------------------------------------------------------------------------
def run(facts: dict, mode: str, params: Optional[Dict[str, str]] = None,
        apply: bool = False, admin_user: str = "", admin_pass: str = "",
        url: Optional[str] = None, headless: Optional[bool] = None,
        config: Optional[Config] = None, verify_hook=None) -> dict:
    """切换一次拨号方式。返回 dict:success 只在真实回读==目标措辞时为 True。

    apply=False(默认)= 只定位+选择+填参,不点保存;apply=True 才真正下发。
    verify_hook: 可选 callable(page, result),在关浏览器前调用,返回值存进
    result["verify"] —— 冒烟测试用它读页面状态,将来接"WAN 真拨通"验证也在这。
    """
    mode = mode.lower()
    facts = facts_for(facts, mode)
    result = {"brand": facts.get("brand", ""), "model": facts.get("model", ""),
              "mode": mode, "success": False, "read_back": "",
              "filled": [], "applied": False, "message": "",
              "warnings": [], "screenshot": ""}
    modes = facts.get("modes") or {}
    if mode not in modes:
        result["message"] = ("此型号脚本未定义模式 %r(可用:%s)"
                             % (mode, ", ".join(available_modes(facts))))
        return result
    label = modes[mode]

    cfg = config or Config()
    if headless is not None:
        cfg.headless = headless
    with Browser(cfg) as br:
        page = br.goto(url or facts["url"])
        if not _login(page, facts, admin_user, admin_pass):
            result["message"] = ("login failed —— 仍停在登录页。检查管理密码;"
                                 "注意部分机型(如 Tenda/Mercusys)同一时间只"
                                 "允许一个 Web 会话,先关掉其他已登录的页签。")
            result["screenshot"] = _screenshot(page, cfg, facts, mode)
            return result
        _navigate(page, facts, result)
        _ensure_enabled(page, facts)

        kind = (facts.get("dial") or {}).get("kind", "dropdown")
        if kind == "select":
            _set_mode_select(page, facts, label, result)
        elif kind == "radio":
            _set_mode_radio(page, facts, label, result)
        else:
            _set_mode_dropdown(page, facts, label, result)

        if result["success"]:
            _fill_params(page, facts, mode, params or {}, result)
            if apply:
                _apply(page, facts, result)
        if verify_hook:
            try:
                result["verify"] = verify_hook(page, result)
            except Exception as exc:
                result["warnings"].append("verify_hook: %s" % exc)
        result["screenshot"] = _screenshot(page, cfg, facts, mode)
    return result


def run_cli(facts: dict, argv: Optional[List[str]] = None) -> int:
    """型号脚本的 main:python models/<型号>.py <mode> [--apply] [--param k=v]。

    管理密码 / 宽带账密默认取 router.yaml(python cli.py setup 生成),
    并按模式过滤 —— PPPoE 账密绝不会带进 dynamic 运行。
    """
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
            "没有管理密码:先跑一次 `python cli.py setup` 把路由器 IP/密码存进 "
            "router.yaml(git 已忽略,不会进仓库),或本次直接加 --pass <管理密码>。")

    explicit: Dict[str, str] = {}
    for item in args.param:
        if "=" in item:
            k, v = item.split("=", 1)
            explicit[k.strip()] = v
    params = merge_params(args.mode, saved.get("params") or {}, explicit)
    missing = [f for f in MODE_REQUIRED_FIELDS.get(args.mode, [])
               if f not in params]
    if missing:
        parser.error("模式 %s 还缺参数:%s(用 --param k=v 提供,"
                     "或先跑 python cli.py setup 存进 router.yaml)"
                     % (args.mode, ", ".join(missing)))

    res = run(facts, args.mode, params=params, apply=args.apply,
              admin_user=args.user, admin_pass=args.password,
              url=args.url,
              headless=args.headless or bool(saved.get("headless")))
    print(json.dumps(res, ensure_ascii=False, indent=2))
    if res["success"] and not args.apply:
        print("[hint] 已确认切换(回读=%r)但未点保存;加 --apply 真正下发。"
              % res["read_back"])
    return 0 if res["success"] else 2
