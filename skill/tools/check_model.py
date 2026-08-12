"""第 6 步:型号脚本的**离线体检**。不碰路由器,只看这个文件自洽不自洽。

    python skill/tools/check_model.py Cudy_AX1500
    python skill/tools/check_model.py --all

**过了 ≠ 验收。** 它只能证明"这个文件自己没自相矛盾",证明不了选择器在真机上
点得中 —— 那要 try_switch.py 到真机上跑。但它能在你上台架**之前**拦下一批
本来要浪费一趟机架时间的错。

查这几项:
  * 形状      —— FACTS / MODES / NEEDS / switch() / main() 齐不齐
  * 措辞      —— MODES 里每一档都能查到目标措辞(查不到 = 一定失败)
  * 子串陷阱  —— 两档措辞互为子串时提醒一句(判定是精确相等,不会认错,
                 但别有人哪天"顺手"把它改成包含)
  * 配置      —— NEEDS 指到的 config.yaml 路径确实存在
  * 判定出口  —— 除了 contract.py,没有人自己拼带 success 的结果字典
  * 查找语义  —— 这个文件里的 _pause/_find/_find_text,和探针工具用的是不是
                 同一份代码(不一样的话,"工具说命中 1"就不再预测得了脚本)

退出码:0 = 没有 error / 1 = 有 error / 2 = 用法错误
"""
from __future__ import annotations

import argparse
import ast
import importlib
import inspect
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import _probe                                              # noqa: E402
from common import perf                                    # noqa: E402

ERROR, WARN, NOTE = "error", "warn", "note"


def _code_only(fn):
    """函数的代码,剥掉 docstring 和注释 —— 比的是行为,不是文风。"""
    node = ast.parse(inspect.getsource(fn)).body[0]
    if (node.body and isinstance(node.body[0], ast.Expr)
            and isinstance(node.body[0].value, ast.Constant)
            and isinstance(node.body[0].value.value, str)):
        node.body = node.body[1:]
    return ast.dump(ast.parse(ast.unparse(node)))


def _label_of(mod, mode):
    """这一档的目标措辞(已套 mode_overrides)。radio 机型记的是模式名。"""
    facts = dict(mod.FACTS)
    for key, value in (mod.FACTS.get("mode_overrides") or {}).get(mode, {}).items():
        facts[key] = value
    if (mod.FACTS.get("dial") or {}).get("kind") == "radio":
        return mode
    return (facts.get("modes") or {}).get(mode, "")


def check(name):
    findings = []

    def add(level, text):
        findings.append((level, text))

    path = os.path.join(_probe.ROOT, "models", name + ".py")
    if not os.path.exists(path):
        return [(ERROR, "没有这个型号脚本:models/%s.py" % name)]
    try:
        mod = importlib.import_module("models." + name)
    except Exception as exc:
        return [(ERROR, "import 不进来:%s: %s" % (type(exc).__name__, exc))]

    # --- 形状 ---------------------------------------------------------------
    for attr, kind in (("FACTS", dict), ("MODES", list), ("NEEDS", dict)):
        if not isinstance(getattr(mod, attr, None), kind):
            add(ERROR, "缺 %s(应该是 %s)" % (attr, kind.__name__))
    for fn in ("switch", "main"):
        if not callable(getattr(mod, fn, None)):
            add(ERROR, "缺 %s()" % fn)
    if findings:
        return findings
    try:
        sig = list(inspect.signature(mod.switch).parameters)
        if sig[:2] != ["mode", "cfg"]:
            add(ERROR, "switch() 的前两个参数应该是 (mode, cfg),现在是 %s" % sig[:2])
    except Exception:
        pass

    # --- 措辞 ---------------------------------------------------------------
    labels = {}
    for mode in mod.MODES:
        label = _label_of(mod, mode)
        if not label:
            add(ERROR, "模式 %r 查不到目标措辞 —— 它一定会失败(空回读永远判假)"
                % mode)
        else:
            labels[mode] = label
    for a in labels:
        for b in labels:
            if a != b and labels[a] and labels[a].lower() in labels[b].lower() \
                    and labels[a].lower() != labels[b].lower():
                add(NOTE, "措辞 %r 是 %r 的子串 —— 判定是精确相等,不会认错;"
                          "别把任何判定改成包含匹配。" % (labels[a], labels[b]))

    # --- NEEDS 指到的配置项存不存在 -----------------------------------------
    try:
        cfg = perf.load()
    except SystemExit:
        cfg = None
        add(WARN, "读不到 config.yaml,跳过配置项检查")
    if cfg is not None:
        for mode, needs in (mod.NEEDS or {}).items():
            if mode not in mod.MODES:
                add(WARN, "NEEDS 里有 %r,但 MODES 里没有 —— 多余的" % mode)
            for concept, where in (needs or {}).items():
                node, ok = cfg, True
                for part in str(where).split("."):
                    if not isinstance(node, dict) or part not in node:
                        ok = False
                        break
                    node = node[part]
                if not ok:
                    add(ERROR, "NEEDS[%r][%r] 指到 config.yaml 的 %s,"
                               "而那一项不存在" % (mode, concept, where))
        for mode in mod.MODES:
            if mode not in (mod.NEEDS or {}):
                add(WARN, "NEEDS 里没有 %r —— 那一档会被当成不需要任何账密" % mode)

    # --- 判定出口 -----------------------------------------------------------
    src = open(path, encoding="utf-8").read()
    for node in ast.walk(ast.parse(src)):
        if isinstance(node, ast.Dict):
            keys = [k.value for k in node.keys
                    if isinstance(k, ast.Constant) and isinstance(k.value, str)]
            if "success" in keys:
                add(ERROR, "第 %d 行自己拼了一个带 success 的结果字典 —— "
                           "只有 common/contract.py 能造它" % node.lineno)
    if "contract.result(" not in src:
        add(ERROR, "没有调用 contract.result() —— 结果必须由它构造")
    if "contract.verify(" not in src:
        add(ERROR, "没有调用 contract.verify() —— success 只能由它算出来")

    # --- 查找语义有没有漂 ---------------------------------------------------
    for fn_name in ("_pause", "_find", "_find_text"):
        mine = getattr(mod, fn_name, None)
        if mine is None:
            continue
        try:
            if _code_only(mine) != _code_only(getattr(_probe, fn_name)):
                add(WARN, "%s() 和探针工具用的那份不一样了 —— "
                          "「工具说命中 1」就不再预测得了这个脚本。"
                          "对一下 skill/tools/_probe.py。" % fn_name)
        except Exception as exc:
            add(NOTE, "%s() 比不了(%s)" % (fn_name, exc))

    if not findings:
        add(NOTE, "没有发现问题(但这只是离线体检 —— 真机上还得逐档 try_switch)")
    return findings


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("model", nargs="?", help="型号脚本名(models/<这里>.py)")
    ap.add_argument("--all", action="store_true", help="体检所有型号")
    args = ap.parse_args(argv)
    if not args.model and not args.all:
        _probe.say("给一个型号名,或者 --all。")
        return _probe.USAGE

    if args.all:
        names = sorted(os.path.splitext(f)[0]
                       for f in os.listdir(os.path.join(_probe.ROOT, "models"))
                       if f.endswith(".py") and not f.startswith("_"))
    else:
        names = [args.model]

    bad = 0
    for name in names:
        findings = check(name)
        errors = [f for f in findings if f[0] == ERROR]
        bad += bool(errors)
        print("%-6s %s" % ("ERROR" if errors else "OK", name))
        for level, text in findings:
            if level == NOTE and not errors:
                _probe.say("       说明 " + text)
            elif level == WARN:
                _probe.say("       警告 " + text)
            elif level == ERROR:
                _probe.say("       错误 " + text)
    if bad:
        _probe.say("\n%d 个型号有 error。" % bad)
        return _probe.FAIL
    _probe.say("\n%d 个型号,没有 error。**体检 ≠ 验收** —— 真机上还要逐档 "
               "try_switch.py 看回读,全对了才谈 --apply。" % len(names))
    return _probe.PASS


if __name__ == "__main__":
    sys.exit(main())
