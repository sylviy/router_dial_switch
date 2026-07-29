"""tools/probe_router.py —— 适配新型号用的**只读取证探针**。

给适配 agent 用,不是给测试员用的日常入口。它做一件事:登录到路由器的 WAN
设置页,把整页(含所有子 frame)的控件抄下来,**并用 Playwright 引擎当场验证
每个候选选择器的命中数**,产出:

  * artifacts/probe_<地址>_<时间>.json —— 全部证据(选项原文、outerHTML、命中数)
  * 一份 FACTS 建议(--emit 可直接写成 models/<品牌>_<型号>.py 骨架)

为什么必须有它:浏览器控制台只能验 `document.querySelectorAll(sel).length`,
而 FACTS 里的选择器用的是 Playwright 语法(`:text-is()` / `:has()` / `:visible`),
控制台验不了。2026-07-18 台架实测:亲眼看到按钮文字是 "Connect",写下
`button:text-is("Connect")` 却命中 0 —— 文字在里层 <span> 上。**"看到了事实"
不等于"验证了选择器"**,这个差别只有真引擎数得出来,所以探针用的就是
models/_driver.py 本身的登录/导航/查找函数:探针跑通 = 交付脚本跑得通。

安全边界(不可放宽):
  * **绝不点保存/应用/Connect 类按钮** —— 只读。改路由器配置是 --apply 的事;
  * 只点两种东西:--nav 指定的菜单项,和 --open 指定的下拉触发器;
  * 产物含表单值和 URL,可能带会话 token,回传前先过一眼(artifacts/ 已 git 忽略)。

用法:
    python tools/probe_router.py --url http://192.168.0.1 --pass admin
    python tools/probe_router.py --url http://192.168.10.1 --pass admin \\
        --login-pass "#pwd" --login-btn "input[value='Login']" \\
        --nav "sel:#Network" --nav "sel:#WAN"
    # 抄完主页面再看下拉里的选项(会点开触发器,不改任何值):
    python tools/probe_router.py ... --open "div.v-select"
    # 直接落一个型号脚本骨架(未观察到的项写成 TODO,check_model.py 会拦):
    python tools/probe_router.py ... --brand Tenda --model AX3000 \\
        --emit models/Tenda_AX3000.py
"""
from __future__ import annotations

import argparse
import datetime
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from config import Config
from models._browser import Browser
from models import _driver
import settings as settings_mod

# ---------------------------------------------------------------------------
# 措辞表 —— 只用来给候选**归类**(猜 canonical key),FACTS 里的 modes 值一律
# 逐字照抄 DOM 原文。v6 必须排在 v4 前面:否则 "PPPoEv6" 会被 "pppoe" 抢走
# (heuristics 时代的 match_mode 就是这么翻的车)。
# ---------------------------------------------------------------------------
MODE_WORDS = [
    ("pppoev6", ["pppoev6", "pppoe v6", "pppoe ipv6"]),
    ("dhcpv6",  ["dhcpv6", "dhcp v6", "auto dhcpv6"]),
    ("staticv6", ["static ipv6", "static ipv6 address", "静态 ipv6"]),
    ("l2tp",    ["l2tp"]),
    ("pptp",    ["pptp"]),
    ("pppoe",   ["pppoe", "pppoe/adsl", "adsl", "宽带拨号", "pppoe拨号"]),
    ("dynamic", ["dynamic ip", "dhcp", "dhcp client", "dynamic",
                 "automatic ip", "auto ip", "动态ip", "自动获取ip地址",
                 "自动获取 ip", "dhcp(自动获取)"]),
    ("static",  ["static ip", "static", "static ip address", "静态ip",
                 "固定ip"]),
]

# 输入框归类:概念 -> (必须命中的词, 二选一命中的词)。按 name/id/label 匹配。
FIELD_HINTS = [
    ("pppoe_user", ["ppp"], ["user", "name", "acct", "account", "账号", "用户"]),
    ("pppoe_pass", ["ppp"], ["pass", "pwd", "密码"]),
    ("vpn_server", ["l2tp", "pptp", "vpn"],
     ["server", "ipaddr", "addr", "host", "domain", "地址", "服务器"]),
    ("vpn_user",   ["l2tp", "pptp", "vpn"],
     ["user", "name", "acct", "account", "账号", "用户"]),
    ("vpn_pass",   ["l2tp", "pptp", "vpn"], ["pass", "pwd", "密码"]),
    ("static_ip",  ["static", "wan"], ["ipaddr", "ip_addr", "ipaddress"]),
    ("static_mask", ["mask", "netmask", "子网掩码"], []),
    ("static_gateway", ["gateway", "gw", "网关"], []),
    ("static_dns", ["dns"], []),
]

SAVE_WORDS = ["save & apply", "save and apply", "save", "apply", "connect",
              "ok", "保存", "应用", "连接", "确定", "提交"]
# 诱饵:Cudy 的 WAN 帧里藏着 8 个 *Connect/*Disconnect 提交键,Tenda 连接态
# 也有 Disconnect。子串匹配 "connect" 一定会误伤,必须先排除。
SAVE_EXCLUDE = ["disconnect", "断开", "cancel", "取消", "release", "renew",
                "refresh", "reset", "重启", "恢复"]


def _norm(text) -> str:
    return re.sub(r"\s+", " ", (text or "")).strip().lower()


def classify_mode(text: str):
    """把一句界面原文归到 canonical 模式名。精确相等优先,再退整词包含。
    返回 (key, exact) 或 (None, False)。"""
    n = _norm(text)
    if not n:
        return None, False
    for key, words in MODE_WORDS:
        if n in words:
            return key, True
    for key, words in MODE_WORDS:
        for w in words:
            if re.search(r"(^|[^a-z0-9])%s([^a-z0-9]|$)" % re.escape(w), n):
                return key, False
    return None, False


def classify_field(name: str, ident: str, label: str):
    """输入框归到 FACTS.fields 的概念名;拿不准返回 None(留给人填)。"""
    hay = _norm(" ".join([name or "", ident or "", label or ""]))
    if not hay:
        return None
    for concept, must, any_of in FIELD_HINTS:
        if not any(m in hay for m in must):
            continue
        if any_of and not any(a in hay for a in any_of):
            continue
        return concept
    return None


# ---------------------------------------------------------------------------
# 页内采集 —— 一次 evaluate 抄回整个 frame 的控件形态
# ---------------------------------------------------------------------------
HARVEST_JS = r"""
() => {
  const txt = el => (el.innerText || el.textContent || '').replace(/\s+/g,' ').trim();
  const vis = el => {
    const r = el.getBoundingClientRect();
    const s = getComputedStyle(el);
    return !!(r.width && r.height) && s.visibility !== 'hidden' && s.display !== 'none';
  };
  const attrs = el => {
    const o = {};
    for (const a of el.attributes) o[a.name] = a.value;
    return o;
  };
  // 表单行标签:优先 <label for>,再向上找"表单行大小"的祖先里的文字。
  // 上限 120 字符是硬教训:再大就会把侧边栏 "IPv6" 导航、开关标题一起算进来,
  // 让它们冒充拨号控件(tenda_ipv6 mock 就是为此写的)。
  const labelOf = el => {
    if (el.id) {
      const l = document.querySelector(`label[for="${CSS.escape(el.id)}"]`);
      if (l) return txt(l);
    }
    const l2 = el.closest('label');
    if (l2) return txt(l2);
    let p = el.parentElement, hops = 0;
    while (p && hops++ < 5) {
      const t = txt(p);
      if (t && t.length < 120) {
        const own = txt(el);
        const rest = own ? t.replace(own, '').trim() : t;
        if (rest) return rest;
      }
      p = p.parentElement;
    }
    return '';
  };
  // 表单行祖先(给 label 锚定选择器用)。关键:要找的是**同时包含标签文字和
  // 控件本身**的那一层,不是紧包着值的那层。Tenda 的正解是
  //   div.v-form-item:has-text("Internet Connection Type") div.v-select
  // 而 div.v-form-item__content 只裹着值文本,拿它去 :has-text(标签) 命中 0。
  // 所以判据是"这一层的文字比控件自己的文字多出点东西"(多出来的就是标签)。
  // 仍然卡 120 字符:再往上就会把侧边栏导航、开关标题算进来冒充控件。
  const rowOf = el => {
    const own = txt(el);
    let p = el.parentElement, hops = 0;
    while (p && hops++ < 6) {
      const t = txt(p);
      if (p.className && typeof p.className === 'string' && t && t.length < 120) {
        const extra = (own ? t.replace(own, '') : t).trim();
        if (extra) {
          return {cls: p.className.trim().split(/\s+/)[0],
                  tag: p.tagName.toLowerCase(), text: t, label: extra};
        }
      }
      p = p.parentElement;
    }
    return null;
  };

  const out = {selects: [], inputs: [], buttons: [], dropdowns: [], toggles: []};

  for (const el of document.querySelectorAll('select')) {
    out.selects.push({
      id: el.id || '', name: el.name || '', visible: vis(el),
      label: labelOf(el),
      options: Array.from(el.options).map(o => o.text.trim()),
      attrs: attrs(el),
    });
  }

  for (const el of document.querySelectorAll('input, textarea')) {
    const type = (el.getAttribute('type') || 'text').toLowerCase();
    if (['submit','button','reset','image'].includes(type)) continue;
    out.inputs.push({
      type, id: el.id || '', name: el.name || '', visible: vis(el),
      placeholder: el.getAttribute('placeholder') || '',
      label: labelOf(el), attrs: attrs(el),
    });
  }

  for (const el of document.querySelectorAll(
        'button, input[type=submit], input[type=button], a[role=button]')) {
    out.buttons.push({
      tag: el.tagName.toLowerCase(),
      text: txt(el), value: el.getAttribute('value') || '',
      visible: vis(el), id: el.id || '', name: el.name || '',
      // outerHTML 是关键证据:文字到底在按钮自己身上,还是在里层 <span>。
      // :text-is() 只匹配"直接拥有该文本节点"的元素 —— 这一条判断全靠它。
      outer: el.outerHTML.slice(0, 400),
      nested_text: (() => {
        for (const c of el.children) {
          const t = txt(c);
          if (t && t === txt(el)) return {tag: c.tagName.toLowerCase(), text: t};
        }
        return null;
      })(),
      attrs: attrs(el),
    });
  }

  // 自定义下拉候选:有 combobox 语义的,或 class 像 select/dropdown 的,
  // 或文字本身就是一个拨号方式措辞的小元素。
  const seen = new Set();
  const push = el => {
    if (seen.has(el)) return;
    seen.add(el);
    const t = txt(el);
    if (t.length > 60) return;                 // 整包 wrapper,不是控件
    out.dropdowns.push({
      tag: el.tagName.toLowerCase(),
      cls: (typeof el.className === 'string' ? el.className.trim() : ''),
      role: el.getAttribute('role') || '', text: t,
      visible: vis(el), label: labelOf(el), row: rowOf(el),
      outer: el.outerHTML.slice(0, 400), attrs: attrs(el),
      // 值文本所在的稳定锚点:后代里带 data-* 的那个(Tenda 的 data-name=wanType)
      data_children: Array.from(el.querySelectorAll('*')).slice(0, 40)
        .map(c => {
          const d = Object.keys(attrs(c)).filter(k => k.startsWith('data-'));
          return d.length ? {sel: `[${d[0]}='${c.getAttribute(d[0])}']`,
                             text: txt(c)} : null;
        }).filter(Boolean).slice(0, 5),
    });
  };
  for (const el of document.querySelectorAll(
        "[role=combobox], [role=listbox], [class*='select'], [class*='dropdown']," +
        "[class*='combo'], [class*='picker']")) push(el);

  for (const el of document.querySelectorAll(
        "[role=switch], input[type=checkbox], [class*='switch'], [class*='toggle']")) {
    if (seen.has(el)) continue;
    out.toggles.push({
      tag: el.tagName.toLowerCase(),
      cls: (typeof el.className === 'string' ? el.className.trim() : ''),
      role: el.getAttribute('role') || '', id: el.id || '', name: el.name || '',
      checked: el.tagName === 'INPUT' ? !!el.checked : null,
      aria: el.getAttribute('aria-checked'),
      visible: vis(el), label: labelOf(el), outer: el.outerHTML.slice(0, 300),
      attrs: attrs(el),
    });
  }
  return out;
}
"""


# ---------------------------------------------------------------------------
# 选择器建议 + 命中数验证
# ---------------------------------------------------------------------------
def _candidates(info: dict, kind: str):
    """按"属性锚点优先于文字锚点"的顺序给出候选选择器。"""
    a = info.get("attrs") or {}
    out = []
    if info.get("id"):
        out.append("#%s" % info["id"])
    if a.get("name"):
        out.append("[name='%s']" % a["name"])
    for k, v in a.items():
        if k.startswith("data-") and v:
            out.append("[%s='%s']" % (k, v))
    tag = info.get("tag") or kind
    cls = (info.get("cls") or a.get("class") or "").split()
    if cls:
        out.append("%s.%s" % (tag, ".".join(cls[:2])))
    row = info.get("row")
    if row and (row.get("label") or row.get("text")):
        # label 锚定 —— 类名不唯一时的正解(Tenda 页上 5 个同类 v-select
        # 靠标签才分得开)。锚点用"行里除控件自身文字以外的部分"= 标签。
        anchor = (row.get("label") or info.get("label") or "").strip()
        anchor = anchor.split("\n")[0][:40].replace('"', "")
        if anchor and cls:
            out.append('%s.%s:has-text("%s") %s.%s'
                       % (row["tag"], row["cls"], anchor, tag, cls[0]))
    return [s for s in dict.fromkeys(out) if s]


def _count(frame, sel: str):
    try:
        return frame.locator(sel).count()
    except Exception:
        return -1           # 选择器语法都不合法


def _pin(frame, page, info: dict, kind: str) -> dict:
    """挑一个**引擎实测命中数==1**的选择器。同时数一遍全页(所有 frame)的
    命中数:_driver 是跨 frame 找第一个可见的,别的 frame 里有同名元素照样翻车。"""
    tried = []
    best = None
    for sel in _candidates(info, kind):
        n = _count(frame, sel)
        total = sum(max(_count(f, sel), 0) for f in page.frames)
        tried.append({"selector": sel, "frame_count": n, "page_count": total})
        if n == 1 and best is None:
            best = {"selector": sel, "frame_count": n, "page_count": total}
    return {"recommended": (best or {}).get("selector", ""),
            "unique": bool(best), "tried": tried}


def _apply_selector(btn: dict) -> str:
    """从一个按钮的证据推出保存键选择器。

    文字在里层 <span> 时必须双锚定 —— `button:text-is("Connect")` 会命中 0
    (2026-07-18 Tenda 真机实测)。有 name/id 的走属性,最稳。
    """
    a = btn.get("attrs") or {}
    text = (btn.get("text") or btn.get("value") or "").strip()
    anchor = ""
    if btn.get("id"):
        anchor = "#%s" % btn["id"]
    elif a.get("name"):
        anchor = "%s[name='%s']" % (btn["tag"], a["name"])
    else:
        for k, v in a.items():
            if k.startswith("data-") and v:
                anchor = "%s[%s='%s']" % (btn["tag"], k, v)
                break
    nested = btn.get("nested_text")
    if anchor and nested:
        return '%s:has(%s:text-is("%s"))' % (anchor, nested["tag"], nested["text"])
    if anchor and btn["tag"] == "input" and btn.get("value"):
        return "%s" % anchor
    if anchor:
        return anchor
    if btn["tag"] == "input" and btn.get("value"):
        return "input[value='%s']" % btn["value"]
    if nested:
        return '%s:has(%s:text-is("%s"))' % (btn["tag"], nested["tag"],
                                             nested["text"])
    return '%s:text-is("%s")' % (btn["tag"], text)


LOGIN_WORDS = ["login", "log in", "sign in", "signin", "登录", "登 录",
               "确定", "进入"]


def do_login(page, args, report: dict) -> None:
    """登录,并把**真正用上的**登录选择器记进 FACTS 建议。

    --login-btn 不给时不是直接放弃:先按回车(不少机型够了),不行就在页面上
    找一个文字像"登录"的可见按钮点一下。这一步的产出是硬证据 —— 交付脚本的
    login 段落直接用它,不用再猜(Tenda 的登录键就是个没有 id 的
    button.login-form__submit,Cudy 的则是 input[value='Login'])。
    """
    login = {"password": args.login_pass}
    if args.login_btn:
        login["button"] = args.login_btn
    if not args.password:
        # 没给密码就完全不碰登录:_login 会把密码填进"第一个 password 框",
        # 而 WAN 页上的 PPPoE 密码框也是 password 框 —— 空跑一趟就把管理密码
        # 打进了宽带密码格。只读探针不该有这种副作用。
        report["login"] = dict(login, ok=None, skipped="没给 --pass,跳过登录")
        return login

    # 先抄一遍登录页本身:登录成功后它就消失了,而交付脚本的 login 段落
    # 需要**属性锚点**(Cudy 是 #pwd,Tenda 是 button.login-form__submit),
    # 光靠默认的 input[type=password] 在有多个密码框的页面上不够稳。
    report["login_page"] = harvest(page)
    for fr in report["login_page"]:
        for inp in fr.get("inputs") or []:
            if inp.get("type") == "password" and inp["pin"]["unique"] \
                    and inp.get("visible"):
                login["password"] = inp["pin"]["recommended"]
                break

    ok = _driver._login(page, {"login": login}, args.user, args.password)
    if not ok and not args.login_btn:
        for sel in _login_button_candidates(page):
            el = _driver._locate(page, sel)
            if not el:
                continue
            try:
                el.click()
            except Exception:
                continue
            gone = _driver._poll(
                page, lambda: _driver._locate(page, args.login_pass) is None, 8000)
            if gone:
                login["button"] = sel
                ok = True
                print("[i] 登录键是 %s(探针自己找到的,已写进 FACTS 建议)" % sel)
                break
    report["login"] = dict(login, ok=ok)
    if not ok:
        print("[X] 还停在登录页 —— 密码不对、登录键没找对(用 --login-btn 指定),"
              "或这台机只允许一个 Web 会话(先关掉浏览器里登录着的页签)。")
    return login


def _login_button_candidates(page):
    """页面上文字像"登录"的可见按钮,按"属性锚点优先"给出选择器(命中数==1)。"""
    out = []
    for fr in page.frames:
        try:
            data = fr.evaluate(HARVEST_JS)
        except Exception:
            continue
        for b in data.get("buttons") or []:
            t = _norm("%s %s" % (b.get("text") or "", b.get("value") or ""))
            if not b.get("visible") or not any(w in t for w in LOGIN_WORDS):
                continue
            sel = _apply_selector(b)
            if _count(fr, sel) == 1 and sel not in out:
                out.append(sel)
    return out


def _is_save(btn: dict) -> bool:
    t = _norm("%s %s" % (btn.get("text") or "", btn.get("value") or ""))
    if not t or any(x in t for x in SAVE_EXCLUDE):
        return False
    return any(w in t for w in SAVE_WORDS)


# ---------------------------------------------------------------------------
def harvest(page) -> list:
    """逐 frame 采集 + 逐候选验证命中数。老式 frameset(Cudy)的菜单、表单、
    保存键分散在不同 frame,所以必须全 frame 扫 —— 和 _driver 的行为一致。"""
    frames = []
    for i, fr in enumerate(page.frames):
        try:
            data = fr.evaluate(HARVEST_JS)
        except Exception as exc:
            frames.append({"index": i, "url": getattr(fr, "url", ""),
                           "error": "采集失败: %s" % exc})
            continue
        for s in data["selects"]:
            s["pin"] = _pin(fr, page, s, "select")
            s["modes"] = [{"text": o, "key": classify_mode(o)[0],
                           "exact": classify_mode(o)[1]} for o in s["options"]]
        for inp in data["inputs"]:
            inp["concept"] = classify_field(inp.get("name"), inp.get("id"),
                                            inp.get("label"))
            inp["pin"] = _pin(fr, page, inp, "input")
        for b in data["buttons"]:
            b["is_save_candidate"] = _is_save(b)
            b["suggested"] = _apply_selector(b)
            b["suggested_count"] = _count(fr, b["suggested"])
            b["suggested_page_count"] = sum(max(_count(f, b["suggested"]), 0)
                                            for f in page.frames)
        for d in data["dropdowns"]:
            d["mode_key"] = classify_mode(d.get("text"))[0]
            d["pin"] = _pin(fr, page, d, d.get("tag") or "div")
            for dc in d.get("data_children") or []:
                dc["count"] = _count(fr, dc["sel"])
        for t in data["toggles"]:
            t["pin"] = _pin(fr, page, t, t.get("tag") or "div")
        frames.append({"index": i, "url": getattr(fr, "url", ""),
                       "name": getattr(fr, "name", ""), **data})
    return frames


def suggest_facts(probe: dict, brand: str, model: str, url: str,
                  nav: list, login: dict) -> dict:
    """把证据整理成一份 FACTS 建议。**只写观察到且命中数==1 的东西**;
    其余一律留 "TODO: ..." —— tools/check_model.py 会把 TODO 当错误拦下,
    所以骨架永远不会伪装成"已经填好了"。"""
    facts = {
        "brand": brand or "TODO: 品牌",
        "model": model or "TODO: 型号",
        "url": url,
        "login": dict(login) if login else None,
        "wan_path": list(nav),
        "dial": {"kind": "TODO", "selector": "TODO: 没有找到唯一的拨号控件"},
        "modes": {},
        "fields": {},
        "apply": "TODO: 没有找到保存键",
    }

    # --- 拨号控件:先看原生 <select>(选项能归到 >=2 个模式的那个)---------
    best_sel, best_hits = None, 0
    for fr in probe:
        for s in fr.get("selects") or []:
            keys = {m["key"] for m in s.get("modes") or [] if m["key"]}
            if len(keys) >= 2 and len(keys) > best_hits and s["pin"]["unique"]:
                best_sel, best_hits = s, len(keys)
    if best_sel:
        facts["dial"] = {"kind": "select",
                         "selector": best_sel["pin"]["recommended"]}
        for m in best_sel["modes"]:
            if m["key"] and m["key"] not in facts["modes"]:
                facts["modes"][m["key"]] = m["text"]       # 逐字照抄原文
    else:
        # --- 自定义下拉:值文本就是某个模式措辞的那个候选 -----------------
        for fr in probe:
            for d in fr.get("dropdowns") or []:
                if not (d.get("mode_key") and d["pin"]["unique"] and d["visible"]):
                    continue
                dial = {"kind": "dropdown", "selector": d["pin"]["recommended"]}
                # 触发器的 innerText 常常带着下拉小箭头之类的杂质
                # ("Dynamic IP v")。带 data-* 的值节点给的才是干净原文,
                # 而 modes 的值必须是**一字不差**的界面措辞 —— 回读判定是精确
                # 相等,多一个字符就永远判不成功。顺便它就是 dial.value。
                value = next((dc for dc in d.get("data_children") or []
                              if dc.get("count") == 1 and dc.get("text")), None)
                if value:
                    dial["value"] = value["sel"]
                text = (value or {}).get("text") or d.get("text") or ""
                key, exact = classify_mode(text)
                facts["dial"] = dial
                if key and exact:
                    facts["modes"][key] = text.strip()
                else:
                    facts["modes"]["TODO"] = (
                        "看到的当前值是 %r,不是干净的模式措辞 —— 点开下拉抄原文:"
                        "--open '%s'" % (text, d["pin"]["recommended"]))
                facts["modes"].setdefault(
                    "TODO", "其余模式的原文要点开下拉才看得到:用 --open '%s' "
                            "再跑一次" % d["pin"]["recommended"])
                break
            if facts["dial"]["kind"] != "TODO":
                break

    # --- 参数输入框 -------------------------------------------------------
    for fr in probe:
        for inp in fr.get("inputs") or []:
            c = inp.get("concept")
            if c and c not in facts["fields"] and inp["pin"]["unique"]:
                facts["fields"][c] = inp["pin"]["recommended"]

    # --- PPTP / L2TP 各有一套自己的输入框时,必须拆进 mode_overrides -------
    # 概念名是共用的(vpn_user/vpn_pass/vpn_server),DOM 字段却不是
    # (Cudy:pptpUserName vs l2tpUserName)。放在一层 fields 里,两个模式
    # 会往同一组框里填 —— 其中一个模式必然填错地方。
    overrides = {}
    vpn_concepts = ("vpn_server", "vpn_user", "vpn_pass")
    for mode in ("pptp", "l2tp"):
        if mode not in facts["modes"]:
            continue
        blk = {}
        for fr in probe:
            for inp in fr.get("inputs") or []:
                c = inp.get("concept")
                ident = _norm("%s %s" % (inp.get("name") or "", inp.get("id") or ""))
                if c in vpn_concepts and mode in ident and inp["pin"]["unique"]:
                    blk.setdefault(c, inp["pin"]["recommended"])
        if blk:
            overrides[mode] = {"fields": blk}
    if overrides:
        # 拆出去之后,扁平层里那份就是误导 —— 删掉,别让它悄悄生效
        for c in vpn_concepts:
            facts["fields"].pop(c, None)
        facts["mode_overrides"] = overrides

    # --- 保存键 -----------------------------------------------------------
    for fr in probe:
        for b in fr.get("buttons") or []:
            if b.get("is_save_candidate") and b.get("visible") \
                    and b.get("suggested_count") == 1:
                facts["apply"] = b["suggested"]
                break
        if not str(facts["apply"]).startswith("TODO"):
            break

    # --- 使能开关(整页空空如也时才需要)---------------------------------
    if str(facts["dial"]["selector"]).startswith("TODO"):
        for fr in probe:
            for t in fr.get("toggles") or []:
                if t["pin"]["unique"] and t.get("visible"):
                    facts["enable_toggle"] = t["pin"]["recommended"]
                    break
    return facts


# ---------------------------------------------------------------------------
SCRIPT_TEMPLATE = '''"""{brand} {model} —— WAN 拨号方式切换脚本(探针骨架,**尚未验收**)。

用法(默认只切换不保存;确认回读无误后加 --apply 才真正下发):
    python models/{fname} dynamic
    python models/{fname} pppoe --param pppoe_user=x --param pppoe_pass=y

事实来源:{stamp} tools/probe_router.py 只读取证({probe_file});
下面每个选择器都由 Playwright 引擎实测命中数==1,但**还没有一次真机运行验证**。
交付前必须:
    python tools/check_model.py {name}          # 离线体检,TODO 会被拦下
    python models/{fname} <每个模式>            # 真机逐个跑,看 read_back
    python models/{fname} <模式> --apply        # 全对了才验收
未观察到的项写成 TODO,不要猜 —— 猜出来的"成功"在真机上坑过两次。
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from models._driver import run_cli

FACTS = {facts}

if __name__ == "__main__":
    sys.exit(run_cli(FACTS))
'''


def _fmt_facts(facts: dict) -> str:
    """按仓库里 Tenda/Cudy 的排版手写出 FACTS(json.dumps 的引号风格不一致)。"""
    lines = ["{"]
    for key in ("brand", "model", "url"):
        lines.append("    %r: %r," % (key, facts[key]))
    if facts.get("login"):
        lines.append("    'login': {%s},"
                     % ", ".join("%r: %r" % (k, v)
                                 for k, v in facts["login"].items()))
    lines.append("    'wan_path': %r," % (facts.get("wan_path") or []))
    lines.append("    'dial': {%s},"
                 % ", ".join("%r: %r" % (k, v) for k, v in facts["dial"].items()))
    lines.append("    'modes': {")
    for k, v in (facts.get("modes") or {}).items():
        lines.append("        %r: %r," % (k, v))
    lines.append("    },")
    lines.append("    'fields': {")
    for k, v in (facts.get("fields") or {}).items():
        lines.append("        %r: %r," % (k, v))
    lines.append("    },")
    lines.append("    'apply': %r," % facts["apply"])
    if facts.get("enable_toggle"):
        lines.append("    'enable_toggle': %r," % facts["enable_toggle"])
    if facts.get("mode_overrides"):
        lines.append("    'mode_overrides': {")
        for mode, blk in facts["mode_overrides"].items():
            lines.append("        %r: {" % mode)
            for key, val in blk.items():
                if isinstance(val, dict):
                    lines.append("            %r: {" % key)
                    for k, v in val.items():
                        lines.append("                %r: %r," % (k, v))
                    lines.append("            },")
                else:
                    lines.append("            %r: %r," % (key, val))
            lines.append("        },")
        lines.append("    },")
    lines.append("}")
    return "\n".join(lines)


def emit_script(path: str, facts: dict, probe_file: str) -> None:
    name = os.path.splitext(os.path.basename(path))[0]
    text = SCRIPT_TEMPLATE.format(
        brand=facts["brand"], model=facts["model"], name=name,
        fname=os.path.basename(path), facts=_fmt_facts(facts),
        probe_file=os.path.basename(probe_file),
        stamp=datetime.date.today().isoformat())
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)


# ---------------------------------------------------------------------------
def probe(args):
    """跑一次取证,返回 (完整证据, FACTS 建议)。

    命令行入口和 adapt.py 向导都走这里 —— 两条路的探测行为必须完全一致,
    否则"向导能过、命令行不过"这种问题没法排查。
    """
    cfg = Config()
    cfg.headless = args.headless
    report = {"url": args.url, "generated_at": datetime.datetime.now().isoformat(),
              "nav": list(args.nav), "opened": args.open_sel}

    with Browser(cfg) as br:
        page = br.goto(args.url)
        login = do_login(page, args, report)
        facts_stub = {"login": login, "wan_path": list(args.nav)}
        nav_result = {"warnings": []}
        _driver._navigate(page, facts_stub, nav_result)
        report["nav_warnings"] = nav_result["warnings"]
        _driver._settle(page, 800)
        report["final_url"] = page.url
        report["frames"] = harvest(page)
        if args.open_sel:
            # 点开下拉抄选项原文。只点触发器 —— 保存键永远不碰。
            trig = _driver._locate(page, args.open_sel)
            if trig:
                trig.click()
                _driver._settle(page, 600)
                report["opened_options"] = _harvest_options(page)
            else:
                report["opened_options"] = {"error": "没找到 %s" % args.open_sel}

    facts = suggest_facts(report["frames"], args.brand, args.model, args.url,
                          args.nav, login)
    if report.get("opened_options"):
        for opt in report["opened_options"].get("options", []):
            key = classify_mode(opt)[0]
            if key and key not in facts["modes"]:
                facts["modes"][key] = opt
        facts["modes"].pop("TODO", None)
    report["suggested_facts"] = facts
    return report, facts


# ---------------------------------------------------------------------------
def main(argv=None) -> int:
    _driver._console_safe()
    saved = settings_mod.load()
    ap = argparse.ArgumentParser(
        description="只读取证探针:抄下路由器 WAN 页的控件并验证选择器命中数")
    ap.add_argument("--url", default=saved.get("router_ip") and
                    "http://%s" % saved["router_ip"],
                    help="路由器地址(默认取 router.yaml 的 router_ip)")
    ap.add_argument("--user", default=saved.get("user", ""), help="管理用户名")
    ap.add_argument("--pass", dest="password", default=saved.get("pass", ""),
                    help="管理密码(默认取 router.yaml)")
    ap.add_argument("--login-pass", default="input[type=password]",
                    help="登录密码框选择器")
    ap.add_argument("--login-btn", default="",
                    help="登录按钮选择器(不填就按回车)")
    ap.add_argument("--nav", action="append", default=[], metavar="ITEM",
                    help="进 WAN 页要点的菜单,可重复;前缀 sel: 表示用选择器")
    ap.add_argument("--open", dest="open_sel", default="",
                    help="额外点开这个下拉触发器,再抄一次(只点它,不点保存)")
    ap.add_argument("--brand", default="", help="写进 FACTS 的品牌")
    ap.add_argument("--model", default="", help="写进 FACTS 的型号")
    ap.add_argument("--emit", default="",
                    help="把 FACTS 建议写成型号脚本,如 models/Tenda_AX3000.py")
    ap.add_argument("--out", default="", help="产物 JSON 路径(默认 artifacts/)")
    ap.add_argument("--headless", action="store_true", help="无窗口运行")
    args = ap.parse_args(argv)

    if not args.url:
        ap.error("没有地址:--url http://192.168.1.1,"
                 "或先跑 python start.py --setup 存进 router.yaml")

    report, facts = probe(args)

    out = args.out or os.path.join(
        ROOT, "artifacts", "probe_%s_%s.json"
        % (re.sub(r"[^A-Za-z0-9]+", "_", args.url).strip("_"),
           datetime.datetime.now().strftime("%Y%m%d_%H%M%S")))
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", encoding="utf-8") as fh:
        json.dump(report, fh, ensure_ascii=False, indent=2)

    _summary(report, out)
    if args.emit:
        emit_script(args.emit, facts, out)
        print("已写出骨架:%s" % args.emit)
        print("下一步:python tools/check_model.py %s"
              % os.path.splitext(os.path.basename(args.emit))[0])
    return 0


def _harvest_options(page) -> dict:
    """下拉点开后,抄弹层里的选项原文(和 _driver 用同一套 option 容器形态)。"""
    seen = []
    for fr in page.frames:
        try:
            loc = fr.locator(_driver._OPTION_CONTAINERS)
            for i in range(min(loc.count(), 40)):
                el = loc.nth(i)
                if not el.is_visible():
                    continue
                t = (el.inner_text() or "").strip()
                # 换行 = 抓到了"整包 wrapper"(.v-select__options 的 innerText
                # 是所有选项拼在一起),不是一个选项。_driver 靠精确文本过滤
                # 天然排除它;这里没有目标文本可比,就按"单行"筛。
                if "\n" in t or not t or len(t) >= 40 or t in seen:
                    continue
                seen.append(t)
        except Exception:
            continue
    return {"options": seen, "container": _driver._OPTION_CONTAINERS}


def _summary(report: dict, out: str) -> None:
    print("\n===== 取证摘要 =====")
    print("落点 URL:%s" % report.get("final_url", ""))
    for w in report.get("nav_warnings") or []:
        print("  [!] %s" % w)
    for fr in report.get("frames") or []:
        bits = []
        for key in ("selects", "inputs", "buttons", "dropdowns", "toggles"):
            n = len(fr.get(key) or [])
            if n:
                bits.append("%s=%d" % (key, n))
        print("  frame#%s %s  %s" % (fr["index"], fr.get("url", "")[:60],
                                     " ".join(bits) or "(空)"))
    facts = report.get("suggested_facts") or {}
    print("\n----- FACTS 建议(TODO = 没观察到,别猜,补证据)-----")
    print(_fmt_facts(facts))
    print("\n完整证据:%s" % out)
    print("  (存档用,给人查的。**agent 不要整份读进上下文** —— 上面这份摘要"
          "已经够写 FACTS 了;\n   只查某个选择器时用 python -c 取那一段。)")


if __name__ == "__main__":
    sys.exit(main())
