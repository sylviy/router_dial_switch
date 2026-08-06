"""tools/check_model.py —— 型号脚本的离线体检。

新写完一个 models/<品牌>_<型号>.py,先过这一关再去碰路由器。它不需要路由器、
不需要网络,只回答一个问题:**这个脚本自己是否自洽**。

它能抓到的(全是真机上花过时间的坑):
  * FACTS 里还留着 TODO / 占位符 —— 骨架被当成成品交付了;
  * 某个模式在 mode_overrides 之后仍然缺 dial / apply / 该模式的措辞;
  * 模式要填的账密字段没有对应的 fields 选择器(跑到真机才发现,白切一次);
  * 两个模式的界面措辞一模一样 —— 回读判定分不开它俩;
  * 选择器语法本身就不合法(`:has-text(` 少个括号这类,装了浏览器时才验);
  * 脚本没有 CLI 入口 / start.py 和 run_matrix.py 发现不了它。

它**不能**抓的:选择器在真机上到底命中几个。那只有 tools/probe_router.py
(引擎实测)和真机跑一遍能回答 —— 体检通过 ≠ 可以验收。

用法:
    python tools/check_model.py Tenda_AX3000
    python tools/check_model.py --all           # 仓库里所有型号(冒烟测试用这个)
"""
from __future__ import annotations

import argparse
import importlib
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from models._driver import available_modes, facts_for
from modes import MODE_REQUIRED_FIELDS

PLACEHOLDER = re.compile(r"TODO|<品牌>|<型号>|<选择器>|FIXME|XXX|待填", re.I)
DIAL_KINDS = ("select", "dropdown", "radio")


class Report:
    def __init__(self, name: str):
        self.name = name
        self.errors = []
        self.warnings = []
        self.notes = []

    def err(self, msg):
        self.errors.append(msg)

    def warn(self, msg):
        self.warnings.append(msg)

    def note(self, msg):
        self.notes.append(msg)

    @property
    def ok(self) -> bool:
        return not self.errors

    def show(self) -> None:
        head = "[OK] " if self.ok else "[X]  "
        print("%s%s" % (head, self.name))
        for m in self.errors:
            print("       错误 %s" % m)
        for m in self.warnings:
            print("       警告 %s" % m)
        for m in self.notes:
            print("       说明 %s" % m)


def _walk_strings(obj, path=""):
    """把 FACTS 里所有字符串连同它的路径吐出来,用于找占位符。"""
    if isinstance(obj, str):
        yield path, obj
    elif isinstance(obj, dict):
        for k, v in obj.items():
            yield from _walk_strings(v, "%s.%s" % (path, k) if path else str(k))
    elif isinstance(obj, (list, tuple)):
        for i, v in enumerate(obj):
            yield from _walk_strings(v, "%s[%d]" % (path, i))


def check_facts(name: str, facts: dict, source: str, engine=None) -> Report:
    rep = Report(name)

    # --- 1. 基本形状 -------------------------------------------------------
    for key in ("brand", "model", "url", "dial", "modes", "apply"):
        if not facts.get(key):
            rep.err("FACTS 缺 %r" % key)
    if not isinstance(facts.get("modes"), dict) or not facts.get("modes"):
        rep.err("FACTS.modes 必须是非空 dict")
        return rep

    # --- 2. 占位符没清干净 = 骨架当成品 -----------------------------------
    for path, text in _walk_strings(facts):
        if PLACEHOLDER.search(text):
            rep.err("%s 还是占位符:%r —— 补证据或删掉这一项,别留着猜"
                    % (path, text[:70]))

    # --- 3. 逐模式检查(必须用 facts_for,和运行时同一条路)---------------
    # 同一个毛病常常每个模式各报一遍(dial 是共用的)—— 按问题聚合,
    # 一条错误配一串模式名,比十条一模一样的行好读。
    labels = {}
    problems = {}

    def flag(msg, mode):
        problems.setdefault(msg, []).append(mode)

    for mode in available_modes(facts):
        m = facts_for(facts, mode)
        if mode not in (m.get("modes") or {}):
            rep.err("模式 %r 在 mode_overrides 里,但覆盖后的 modes 没有它的措辞"
                    "(运行时会直接报'未定义模式')" % mode)
            continue
        label = m["modes"][mode]
        dial = m.get("dial") or {}
        kind = dial.get("kind", "dropdown")
        if kind not in DIAL_KINDS:
            flag("dial.kind=%r 不认识(只能是 %s)"
                 % (kind, "/".join(DIAL_KINDS)), mode)
        if not dial.get("selector"):
            flag("没有 dial.selector", mode)
        if not m.get("apply"):
            flag("没有 apply(保存键)—— 整轮会切了不保存,吞吐测的就不是这档", mode)
        if not str(label).strip():
            flag("界面措辞是空的", mode)
        labels.setdefault(str(label).strip().lower(), []).append(mode)

        # 该模式要填的参数,fields 里必须有对应选择器
        fields = m.get("fields") or {}
        missing = [f for f in MODE_REQUIRED_FIELDS.get(mode, [])
                   if f not in fields]
        if missing:
            flag("要填 %s,但 fields 里没有它们的选择器 —— 真机上会切成功、"
                 "参数空着" % "/".join(missing), mode)

    for msg, modes in problems.items():
        rep.err("模式 %s:%s" % ("/".join(modes), msg))

    # --- 4. 措辞撞车:回读判定是精确相等,两个模式同词就分不开 -------------
    for label, modes in labels.items():
        if len(modes) > 1:
            rep.err("模式 %s 的界面措辞都是 %r —— 回读判定分不开它们"
                    % ("/".join(modes), label))

    # --- 5. 子串关系:驱动用精确匹配,所以安全,但值得点名 -----------------
    words = sorted(labels)
    for a in words:
        for b in words:
            if a != b and a in b:
                rep.note("措辞 %r 是 %r 的子串 —— 驱动用精确相等,不会认错;"
                         "别把任何判定改成子串匹配" % (a, b))

    # --- 6. static 的已知空档(CLAUDE.md「Known gaps」)--------------------
    if "static" in available_modes(facts) and not MODE_REQUIRED_FIELDS.get("static"):
        rep.warn("声明了 static,但 modes.py 里 static 没有字段映射 —— "
                 "整轮会切到静态 IP 且不填任何地址,记得在 perf.yaml 的 "
                 "dial_modes 里排除它")

    # --- 7. 交付形态:CLI 入口 + 能被发现 ---------------------------------
    # 尾行必须把这台机自己的 run() 传进去。少了 runner=run,单跑会静默退回
    # 默认配方 —— 对操作顺序特殊的机型(Buffalo)就是"切了、看着成功、保存的
    # 是旧值",而 matrix/run.py 走的又是 run(),两条入口行为不一致。
    if "run_cli(FACTS, runner=run)" not in source:
        rep.err("脚本末尾要写 `sys.exit(run_cli(FACTS, runner=run))` —— "
                "少了 runner=run,python models/%s.py 会退回默认配方,"
                "和整轮走的不是同一条流程" % name)
    if not re.search(r"^\s*def\s+run\s*\(", source, re.M):
        rep.err("没有 run() —— 型号脚本必须自己定义入口(规矩机型照 "
                "models/_template.py 抄三行:return default_run(facts or FACTS, "
                "mode, **kw)),否则 start.py / run_matrix.py 驱动不了它")
    if not re.search(r"^\s*FACTS\s*=", source, re.M):
        rep.err("找不到顶层 FACTS = {...}")

    # --- 8. 选择器语法(装了浏览器才验;命中数只有真机能答)---------------
    if engine is not None:
        seen = set()
        for path, sel in _selectors(facts):
            if sel in seen:          # 同一个选择器被多个模式共用,报一次就够
                continue
            seen.add(sel)
            try:
                engine.locator(sel).count()
            except Exception as exc:
                rep.err("%s 的选择器语法不合法:%s\n              %s"
                        % (path, sel, str(exc).splitlines()[0]))
    else:
        rep.note("没有可用浏览器,跳过了选择器语法检查"
                 "(装了 Chrome 的机器上再跑一次)")
    return rep


def _selectors(facts: dict):
    """FACTS 里所有"会被当成选择器用"的字符串。modes 的值除外 —— 那是措辞,
    只有 kind=radio 时才是选择器。"""
    for mode in available_modes(facts):
        m = facts_for(facts, mode)
        dial = m.get("dial") or {}
        for key in ("selector", "value"):
            if dial.get(key):
                yield "%s.dial.%s" % (mode, key), dial[key]
        if m.get("apply"):
            yield "%s.apply" % mode, m["apply"]
        if m.get("enable_toggle"):
            yield "%s.enable_toggle" % mode, m["enable_toggle"]
        if m.get("options"):
            yield "%s.options" % mode, m["options"]
        for k, v in (m.get("fields") or {}).items():
            yield "%s.fields.%s" % (mode, k), v
        if (dial.get("kind") == "radio") and m.get("modes", {}).get(mode):
            yield "%s.modes.%s" % (mode, mode), m["modes"][mode]
    for k, v in (facts.get("login") or {}).items():
        yield "login.%s" % k, v
    for item in facts.get("wan_path") or []:
        if item.startswith("sel:"):
            yield "wan_path", item[4:]


def list_model_names():
    """os.listdir 而不是 glob:仓库路径里有 [Tool],是个字符类,glob 会静悄悄
    返回空(CLAUDE.md 的老坑,PR #1 在 list_models 上又踩过一次)。"""
    d = os.path.join(ROOT, "models")
    return sorted(f[:-3] for f in os.listdir(d)
                  if f.endswith(".py") and not f.startswith("_"))


def _open_engine():
    """借一个空白页当选择器语法校验器。没有浏览器就返回 (None, None)。"""
    try:
        from config import Config
        from models._browser import Browser
        cfg = Config()
        cfg.headless = True
        br = Browser(cfg).__enter__()
        br.page.set_content("<html><body></body></html>")
        return br.page, br
    except Exception:
        return None, None


def main(argv=None) -> int:
    from models._driver import console_safe
    console_safe()
    ap = argparse.ArgumentParser(description="型号脚本离线体检(不需要路由器)")
    ap.add_argument("name", nargs="?", help="型号脚本名,如 Tenda_AX3000")
    ap.add_argument("--all", action="store_true", help="检查 models/ 下全部型号")
    ap.add_argument("--no-browser", action="store_true",
                    help="跳过选择器语法检查(不起浏览器)")
    args = ap.parse_args(argv)

    names = list_model_names() if args.all else ([args.name] if args.name else [])
    if not names:
        ap.error("给个型号名,或用 --all。可用:%s" % ", ".join(list_model_names()))

    engine, holder = (None, None) if args.no_browser else _open_engine()
    try:
        reports = []
        for name in names:
            path = os.path.join(ROOT, "models", name + ".py")
            if not os.path.exists(path):
                rep = Report(name)
                rep.err("没有这个文件:models/%s.py(可用:%s)"
                        % (name, ", ".join(list_model_names())))
                reports.append(rep)
                continue
            with open(path, "r", encoding="utf-8") as fh:
                source = fh.read()
            try:
                facts = importlib.import_module("models.%s" % name).FACTS
            except Exception as exc:
                rep = Report(name)
                rep.err("import 失败:%s" % exc)
                reports.append(rep)
                continue
            rep = check_facts(name, facts, source, engine)
            # 只数 FACTS 里的标记:模块 docstring 里常有"此前的 [待真机复核]
            # 已全部清除"这类叙述,把它算成待办就成了永远消不掉的假警告。
            body = source.split("FACTS", 1)[-1]
            pending = body.count("[待真机复核]")
            if pending:
                rep.warn("FACTS 里有 %d 处 [待真机复核] —— 真机验过就把标记删掉"
                         % pending)
            reports.append(rep)
    finally:
        if holder is not None:
            try:
                holder.__exit__(None, None, None)
            except Exception:
                pass

    print("==== 型号脚本体检 ====")
    for rep in reports:
        rep.show()
    bad = [r.name for r in reports if not r.ok]
    print("\n%d 个通过,%d 个有错误%s"
          % (len(reports) - len(bad), len(bad),
             ":" + ", ".join(bad) if bad else ""))
    if not bad:
        print("下一步(体检 ≠ 验收):真机上逐个模式跑 "
              "`python models/<型号>.py <mode>` 看 read_back,全对了再 --apply。")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
