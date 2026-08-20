"""按**文件路径**找到并加载型号脚本 —— 编排侧唯一知道 `Models/` 长什么样的地方。

## 为什么不用 `import models.Cudy_AX1500`

包名把目录布局钉死了:`models/` 一旦改名或者多套一层,四处 import 同时失效,
而且失效方式是 `ModuleNotFoundError`,看不出是布局问题。改成按路径加载之后,
`Models/<型号>/<型号>.py` 搬到哪一层、叫什么,编排侧一个字都不用改。

型号脚本**自己不 import 这个文件** —— 它们必须保持一个文件自足(整个
`Models/<型号>/` 目录复制走就能跑)。这里只给 `app/start.py`、`tests/`、
`tools/check_model.py` 这类"要遍历所有型号"的编排侧用。

## 一台机一个目录

    Models/Cudy_AX1500/
        Cudy_AX1500.py      交付物本体(目录名 == 文件名 == 型号名)
        SKILL.md            这台机的任务表
        tools/              可选:agent fork 的探针

目录名和文件名必须同名 —— 这样"型号名"只有一个来源,不会出现目录叫
`Cudy_AX1500`、文件叫 `cudy_ax1500.py` 这种一半对得上一半对不上的状态。
"""
from __future__ import annotations

import importlib.util
import os


def models_dir(scene):
    return os.path.join(scene, "Models")


def model_path(scene, name):
    """型号脚本的绝对路径。不检查存不存在 —— 调用方要拿它去报错。"""
    return os.path.join(models_dir(scene), name, name + ".py")


def list_models(scene):
    """`Models/` 下所有型号名,按字母序。

    **不能用 glob** —— 本仓库路径里可能有 "[Tool]" 这种方括号,glob 会把它
    当字符类,静默返回空列表。所以一律 os.listdir。
    """
    root = models_dir(scene)
    if not os.path.isdir(root):
        return []
    out = []
    for name in sorted(os.listdir(root)):
        if name.startswith("_") or name.startswith("."):
            continue
        if os.path.isfile(model_path(scene, name)):
            out.append(name)
    return out


def load_model(scene, name):
    """把 `Models/<name>/<name>.py` 当模块加载进来。

    找不到就抛 ImportError,消息里带绝对路径 —— "型号名拼错了"和"目录搬走了"
    这两种情况,看路径一眼就能分开。
    """
    path = model_path(scene, name)
    if not os.path.isfile(path):
        raise ImportError("找不到型号脚本:%s" % path)
    spec = importlib.util.spec_from_file_location("model_" + name, path)
    if spec is None or spec.loader is None:
        raise ImportError("加载不了型号脚本:%s" % path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod
