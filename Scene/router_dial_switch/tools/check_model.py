"""第 6 步:型号脚本的**离线体检**。不碰路由器,只看这个文件自洽不自洽。

    python tools/check_model.py Cudy_AX1500
    python tools/check_model.py --all

**过了 ≠ 验收。** 它只能证明"这个文件自己没自相矛盾",证明不了选择器在真机上
点得中 —— 那要 act.py 到真机上跑。但它能在你上台架**之前**拦下一批
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
import inspect
import os
import sys

# 仓库根 / 场景根都靠**向上找标志物**定位,不数目录层级 —— 这个文件搬到哪一层
# 都照跑(Vendor/ 和 Tools/ 在仓库根,Models/ 在场景根)。
def _up_to(marker):
    d = os.path.dirname(os.path.abspath(__file__))
    while not os.path.isdir(os.path.join(d, marker)):
        parent = os.path.dirname(d)
        if parent == d:
            raise SystemExit("往上找不到 %s/ —— 这个文件被搬出仓库了?" % marker)
        d = parent
    return d


ROOT = _up_to("Vendor")           # 仓库根:Tools/ 和 Vendor/ 在这一层
SCENE = _up_to("Models")          # 场景根:config.yaml / Models/ 在这一层
for _p in (os.path.join(ROOT, "Tools"), os.path.join(ROOT, "Vendor"), SCENE):
    if _p not in sys.path:
        sys.path.insert(0, _p)

# 两个 common/ 都不许有 __init__.py:`from common import contract, perf` 一行
# 同时拿到 Vendor/common/contract.py 和 <场景>/common/perf.py,靠的是 py3 的
# **命名空间包**(同名目录分散在几个 sys.path 条目里会被拼成一个包)。任何一边
# 多出 __init__.py,拼接立刻停止,而报错长成 "cannot import name 'perf'",
# 看不出是这个原因。所以在 import **之前**挡一道,把话说清楚。
for _d in (os.path.join(ROOT, "Vendor", "common"), os.path.join(SCENE, "common")):
    if os.path.exists(os.path.join(_d, "__init__.py")):
        raise SystemExit(
            "%s 不该存在。\n"
            "  两个 common/ 是**命名空间包**,拼在一起才有 contract + perf;\n"
            "  有了 __init__.py 就不再拼,`from common import contract, perf`\n"
            "  会在每个型号脚本里当场断。删掉它。"
            % os.path.join(os.path.relpath(_d, ROOT), "__init__.py"))

import _probe                                              # noqa: E402
from common import discover, perf                          # noqa: E402

ERROR, WARN, NOTE = "error", "warn", "note"


def _norm_fn(node):
    """一个函数定义的**规范形态**:剥掉 docstring,只留结构。

    用 ast.dump 而不是 ast.unparse —— 台架上的离线运行时是 Python 3.8,
    ast.unparse 是 3.9 才有的。这道闸不能在最需要它的那台机器上失效。
    注释本来就不进 AST,所以比的是行为不是文风。
    """
    body = node.body
    if (body and isinstance(body[0], ast.Expr)
            and isinstance(body[0].value, ast.Constant)
            and isinstance(body[0].value.value, str)):
        node = ast.FunctionDef(name=node.name, args=node.args, body=body[1:],
                               decorator_list=node.decorator_list,
                               returns=node.returns,
                               type_comment=getattr(node, "type_comment", None))
    return ast.dump(node)


def _code_only(fn):
    """已导入的函数的规范形态。和 _norm_fn 同一个口径。"""
    return _norm_fn(ast.parse(inspect.getsource(fn)).body[0])


def _label_of(mod, mode):
    """这一档的目标措辞(已套 mode_overrides)。radio 机型记的是模式名。"""
    facts = dict(mod.FACTS)
    for key, value in (mod.FACTS.get("mode_overrides") or {}).get(mode, {}).items():
        facts[key] = value
    if (mod.FACTS.get("dial") or {}).get("kind") == "radio":
        return mode
    return (facts.get("modes") or {}).get(mode, "")


def _check_forked_probes(model_dir):
    """型号自己的 tools/ 里,fork 过去的探针有没有动到那三个查找函数。"""
    out = []
    forked = os.path.join(model_dir, "tools")
    if not os.path.isdir(forked):
        return out
    for fn in sorted(os.listdir(forked)):
        if not fn.endswith(".py"):
            continue
        try:
            src = open(os.path.join(forked, fn), encoding="utf-8").read()
            tree = ast.parse(src)
        except Exception as exc:
            out.append((NOTE, "tools/%s 读不了(%s)" % (fn, exc)))
            continue
        for node in tree.body:
            if not isinstance(node, ast.FunctionDef):
                continue
            if node.name not in ("_pause", "_find", "_find_text"):
                continue
            try:
                canon = _code_only(getattr(_probe, node.name))
            except Exception:
                continue
            if _norm_fn(node) != canon:
                out.append((ERROR,
                            "tools/%s 里的 %s() 被改过 —— 这三个函数是定死的,"
                            "fork 探针可以改命令行、输出、加控件形态,"
                            "**不能改它们**。" % (fn, node.name)))
    return out


def check(name):
    findings = []

    def add(level, text):
        findings.append((level, text))

    path = discover.model_path(SCENE, name)
    if not os.path.exists(path):
        return [(ERROR, "没有这个型号脚本:%s" % os.path.relpath(path, SCENE))]
    try:
        mod = discover.load_model(SCENE, name)
    except Exception as exc:
        return [(ERROR, "加载不进来:%s: %s" % (type(exc).__name__, exc))]

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
                           "只有 Vendor/common/contract.py 能造它" % node.lineno)
    if "contract.result(" not in src:
        add(ERROR, "没有调用 contract.result() —— 结果必须由它构造")
    if "contract.verify(" not in src:
        add(ERROR, "没有调用 contract.verify() —— success 只能由它算出来")

    # --- 查找语义有没有漂 ---------------------------------------------------
    # 这三个函数是**定死的**:全仓库唯一一份,型号脚本和探针逐字节一致。
    # 这是"工具说命中 1"能预测"脚本也命中 1"的唯一依据 —— 一旦允许各写各的,
    # 探针的结论就不再说明脚本的行为,前面那几步全部白做。所以是 error。
    for fn_name in ("_pause", "_find", "_find_text"):
        mine = getattr(mod, fn_name, None)
        if mine is None:
            continue
        try:
            if _code_only(mine) != _code_only(getattr(_probe, fn_name)):
                add(ERROR, "%s() 和 Tools/_probe.py 那份不一样了 —— "
                           "「工具说命中 1」就不再预测得了这个脚本。"
                           "把它改回原样;要加能力就加在别处。" % fn_name)
        except Exception as exc:
            add(NOTE, "%s() 比不了(%s)" % (fn_name, exc))

    # --- fork 出去的探针也得守同一条 -----------------------------------------
    # 允许 agent 把探针复制进 Models/<型号>/tools/ 自由编辑(命令行、输出、
    # 新控件形态都随便加),但那三个查找函数原样保留 —— 理由同上。
    for note in _check_forked_probes(os.path.dirname(path)):
        add(*note)

    if not findings:
        add(NOTE, "没有发现问题(但这只是离线体检 —— 真机上还得逐档 try_switch)")
    return findings


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("model", nargs="?", help="型号名(Models/<这里>/<这里>.py)")
    ap.add_argument("--all", action="store_true", help="体检所有型号")
    args = ap.parse_args(argv)
    if not args.model and not args.all:
        _probe.say("给一个型号名,或者 --all。")
        return _probe.USAGE

    if args.all:
        names = discover.list_models(SCENE)
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
               "act.py 看回读,全对了才谈 --apply。" % len(names))
    return _probe.PASS


if __name__ == "__main__":
    sys.exit(main())
