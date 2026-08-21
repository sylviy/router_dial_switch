---
name: adapt-router-model
description: 为一台新路由器型号产出专属拨号切换脚本 Models/<品牌>_<型号>/<品牌>_<型号>.py,并验证到能跑整轮性能测试。触发场景:适配新型号 / 接入新路由器 / 加一台 Buffalo(Huawei/…)/ onboard a new router model / add router model / 生成 Tenda_XXX.py 这类脚本 / 某型号登录不进去或切换不成功要修 FACTS。输入:一台能访问到的路由器(同局域网)。
---

# 适配一台新路由器型号 —— 从这里挑一台开始

**这个文件不是流程。流程在每台机自己的 `Models/<型号>/SKILL.md` 里,一台一份、
各自自足。** 适配新机型只有一步:

> **从下表挑 UI 形态最像的那一台,把它整个 `Models/<那台>/` 拷成
> `Models/<新型号>/`,改名,然后照拷来的那份 `SKILL.md` 第一部分往里填。**

拷来的 SKILL.md 里已经有:通用流程表、七条规矩、按需询问的三种情况、
以及**那台机的实际命令**(改几个选择器就是新机的命令)。不用再回到这里。

这和型号脚本之间的重复是**同一个取舍**:换来的是"改第八台绝不可能弄坏前七台"。

## 挑哪一台来拷

| 这台新机长什么样 | 拷这一台 | 它踩过的坑 |
|---|---|---|
| 原生 `<select>`,老式 frameset / 普通单文档 | `Cudy_AX1500` | 登录框、菜单、表单在三个不同 frame 里 |
| LuCI(CBI)—— id 长成 `cbid.network.wan.proto` | `Cudy_AX3000` | id 含点号,只能用 `[id='…']`;保存键要用表单收窄 |
| LuCI,但同一页有好几个同名控件 | `Cudy_BE6500` | 选择器**全部**用 `form:has(…)` 收窄 |
| 自定义下拉(Vue / `role=combobox`),还有 IPv6 独立页 | `Tenda_AX3000` | 值不在触发器上,要 `--value-sel`;IPv6 那两档在别的页,还得先开开关 |
| 自定义下拉,账密框只能靠标签文字锚定 | `Mercusys_BE3600` | `div.row:has-text("Username") input:visible` |
| radio 组,设置页要以 iframe 打开 | `BUFFALO_WSR6000AX8` | 账密在另一页;要等 iframe 里的 JS 就绪才算加载完 |
| 不走浏览器 —— 内部库 / 命令行 | `TPLink_RouterCtrl` | py2.6 桥接子进程;**回读对上 ≠ 拨上了** |

拿不准就先 `python ../../Tools/probe_dump.py --menu "…"` 看一眼清单里那一行的
"类型",再回来对号。

`tools/make_facts.py --write` 干的也是这件事:照你 `--like` 指定(或按 `--kind`
自动挑)的那台,把脚本和 SKILL.md 一起拷进新型号目录。

## 这个场景里还有什么

| 要什么 | 去哪 |
|---|---|
| 某台机的适配流程 / 规矩 / 它的实际命令 | `Models/<型号>/SKILL.md`(**每台一份,自足**) |
| 探测循环 / 找不到怎么办 / 控件形态表 / `act.py` 各 `--kind` | `../../Tools/probing.md` |
| 卡在具体现象上(登录不进、认错控件、试切不过、整轮跑不起来) | `reference.md`(**按节读,别整篇读**) |
| 配置每一项填什么 | `docs/config.example.yaml` 的中文注释 |
| 台架操作(双击、菜单、报告) | `docs/README.md` / `docs/WINDOWS.md` |

`docs/GOTCHAS.md` 是给人看的历史记录,**不要加载它**。

## 全场景只有一条规矩写在这里

**`_pause` / `_find` / `_find_text` 三个函数定死。** 它们在 `../../Tools/_probe.py`,
全仓库唯一一份。探针可以整个复制到 `Models/<型号>/tools/` 自由编辑 —— 加控件
形态、改输出都行 —— 但这三个原样保留。它们是"工具说命中 1"能预测"脚本也命中 1"
的唯一依据;`tools/check_model.py` 对型号脚本和 fork 出去的探针都逐字节比对,
不一样报 **error**。

其余六条规矩在每份 `Models/<型号>/SKILL.md` 的第二部分,拷过去别改。
