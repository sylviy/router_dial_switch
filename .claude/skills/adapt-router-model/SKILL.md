---
name: adapt-router-model
description: 为一台新路由器型号产出专属拨号切换脚本 models/<品牌>_<型号>.py,并验证到能跑整轮性能测试。触发场景:适配新型号 / 接入新路由器 / 加一台 Buffalo(Huawei/…)/ onboard a new router model / add router model / 生成 Tenda_XXX.py 这类脚本 / 某型号登录不进去或切换不成功要修 FACTS。输入:一台能访问到的路由器(同局域网),或用户回传的一份控件清单。
---

# 适配一台新路由器型号

**产出**:一个文件 `models/<品牌>_<型号>.py`(只有这台机的 FACTS)。放进
`models/` 就完事,`start.py` / `run_matrix.py` 自动发现,没有注册表要改。

## ⚠ 开工第一件事:读进度文件

**你的上下文随时可能被压缩清空。进度存在磁盘上,不在你脑子里。**

```bash
cat artifacts/progress_<品牌>_<型号>.md      # 没有就是全新开始
```

**每做完一步,立刻追加一行**(十几个字,几乎不花 token),格式固定:

```
# Mercusys MR80X  url=http://192.168.1.1  pass=见用户消息
nav=Internet
py=vendor\python\python.exe
dump=artifacts/inventory_Mercusys_MR80X.txt  OK
facts=已写入 models/Mercusys_MR80X.py
count=dial 1 / apply 1 / pppoe_user 1     全部==1
check=PASS
live=dynamic OK / pppoe OK / l2tp FAIL(read_back='')
next=修 l2tp 的措辞,其余已完成
```

被压缩之后:**读这个文件 → 从 `next=` 那一行继续,不要重新探测**。
已经 OK 的步骤**一律不重跑**(重跑 `--dump` 只是浪费,重跑 `--apply` 会改设备)。

## 第二件事:确定用哪个 python

**永远不要直接敲 `python`。** PATH 上那个在台架上是不能动的 Python 2,别处通常
也没装 Playwright —— 直接敲只会得到 `No module named 'playwright'`,而那**不是
适配问题**。

```bash
# Windows(优先 .venv,否则用仓库自带的)
if exist ".venv\Scripts\python.exe" (set PY=.venv\Scripts\python.exe) ^
else (set PY=vendor\python\python.exe)
%PY% -c "import playwright, sys; print(sys.version)"
# Linux/macOS:  PY=$([ -x .venv/bin/python ] && echo .venv/bin/python || echo python3)
```

打印出版本号才算就绪,并把 `py=` 记进进度文件。下面所有 `python xxx` 都用 `%PY%`
/ `$PY` 代替。**「不要读 `vendor/`」指的是不要读它里面的文件(97 MB),
但它的 `python.exe` 正是你要用的解释器** —— 两件事不冲突。
两个都没有就如实报告,**不要自己 pip install**(台架离线,装不上)。

## 成本纪律

**一台设备预算:输入 ~1500 token,输出 ~500。超了就是走错路。**

不要探索、不要整份读(`artifacts/*.json`、`*.png`、`vendor/` 里的文件、
`CLAUDE.md`、`models/_driver.py`)、不要写 mock、不要改 `tools/` 或 `_driver.py`、
不要逐行打印脚本(只输出 FACTS dict)。**`adapt.py` 是给人用的向导,不是给你的
—— 别调用它,也别去修它。**

**每轮尽量多跑几条命令再汇报**,别一条一问 —— 轮数越少,被压缩的机会越小。

## 铁律(违反 = 返工)

1. **不猜没观察过的 DOM**,每个选择器都要 `--count` 实测 ==1。宁可留 `TODO`。
2. **只有真实回读 == 目标措辞才算成功**,永远不放宽成子串
   ("PPPoEv6" 会被认成 "PPPoE")。
3. **默认不点保存**,全部回读正确才 `--apply`;切错会断网。
4. **凭据不进仓库**(走 `router.yaml`,已 git 忽略)。

## 流程(合并成三轮命令跑完)

**先判断走哪条**:已知 UI 家族(Vue 类 / 老式 frameset / LuCI-CBI)可以碰运气用
`--emit`;**全新样子的 UI 直接跳过它,从 `--dump` 开始** —— 对新 UI 猜测多半失败,
再去修猜测结果是纯浪费。

**第 1 轮:探到页面 + 抄下来**(一次跑完这几条,一起汇报)

```bash
curl -m 4 http://<ip>
%PY% tools\probe_router.py --dump --url http://<ip> --pass <密码> ^
    --nav "<设置页菜单文字>" > artifacts\inventory_<品牌>_<型号>.txt
type artifacts\inventory_<品牌>_<型号>.txt
```

清单每行一个控件(`vis=` 是否可见),**只读这份,别去看页面源码**。
拨号控件没出现 = 多半还停在首页,补 `--nav "<菜单文字>"`(前缀 `sel:` 表示用
选择器)重跑这一轮。登录失败见下面「卡住了」。

**存进度**:`dump=... OK` 和 `nav=...`。

**第 2 轮:写 FACTS + 一次性验证全部选择器**

照 `reference.md` 的键写(或复制 `models/Cudy_AX3000.py` 改),写进
`models/<品牌>_<型号>.py`,然后**一条命令验完所有选择器**:

```bash
%PY% tools\probe_router.py --url http://<ip> --pass <密码> --nav "..." ^
    --count "<拨号控件>" --count "<保存键>" --count "<账密框1>" --count "<账密框2>"
```

**命中数不是 1 就不能用**(`button:text-is("Connect")` 常命中 0,文字在里层
span;含点号的 id 只能写 `[id='...']`;`cbi.apply` 那类常命中 4)。不唯一时先试
这两条收窄法:

```
form:has(<拨号控件>) <按钮>                     # 一页多段、每段一个保存键
div.<行class>:has-text("<标签文字>") <控件>     # 类名不唯一,用标签锚定
```

**存进度**:`facts=...` 和 `count=... 全部==1`。

**第 3 轮:体检 + 逐模式真机验证**

```bash
%PY% tools\check_model.py <品牌>_<型号>
%PY% models\<品牌>_<型号>.py dynamic
%PY% models\<品牌>_<型号>.py pppoe
```

`success:true` 且 `read_back` 正是目标措辞才算过。失败信息里会**列出它当时看到
的东西**(有哪些选项、有哪些按钮)—— 照着改,别重新猜。

**存进度**:`check=` 和 `live=每档结果`。

**收尾**:全过之后问用户是否验收,同意再逐档 `--apply`。然后告诉用户
`perf.yaml` 还要配 `dial_modes`(**排除 `static`**)、`wan_up.hosts`(按模式配
ping 目标)、`chariot.nofrag_bytes`,以及 `router.yaml` 的 `params[<模式>]`
(L2TP/PPTP 字段名相同但账号不同,必须分模式存)。

## 卡住了:先分四类

| 症状 | 类别 | 怎么办 |
|---|---|---|
| 抛异常退出 | 崩溃 | 看 `artifacts/crash_*.txt`(20 行)。多数是环境问题 |
| 登录不进去 | 登录 | 探针会打印登录页诊断 + 截图。老 UI 的登录键常是 `<a>`/`<div>` 而非 `<button>`,且回车不提交 |
| 清单里看得见控件,但选择器不唯一/回读不对 | 定位 | 便宜。用上面两条收窄法 + `--count`。**修法必须通用,`_driver.py` 和 `probe_router.py` 里没有一行按品牌分支的代码** |
| 页面上有,但清单里压根没有这种形态 | 形态 | 贵。卡片条/分段选择器/确认弹窗/shadow DOM/验证码/canvas —— 现有三种 `dial.kind` 吃不下,**如实报告,别硬凑 FACTS** |

**任何一条命令崩了都不要卡住**:五条命令彼此独立,而且你**永远不需要工具替你
生成脚本** —— 有 `--dump` 的清单 + `reference.md` 的格式,自己写 dict 就行,
这条路没有环节会崩。只要清单存过盘,前面就没有白跑。

## 更细的东西在 `reference.md`(按需读,别预加载)

FACTS 逐键说明、选择器手册、陷阱清单、定位问题的通用修法、判定"这台机真的没有
某功能"的穷尽核查法、参考实现对照表。
