---
name: adapt-router-model
description: 为一台新路由器型号产出专属拨号切换脚本 models/<品牌>_<型号>.py,并验证到能跑整轮性能测试。触发场景:适配新型号 / 接入新路由器 / 加一台 Buffalo(Huawei/…)/ onboard a new router model / add router model / 生成 Tenda_XXX.py 这类脚本 / 某型号登录不进去或切换不成功要修 FACTS。输入:一台能访问到的路由器(同局域网),或用户回传的一份控件清单。
---

# 适配一台新路由器型号

**产出**:一个文件 `models/<品牌>_<型号>.py`(只有这台机的 FACTS)。放进
`models/` 就完事,`start.py` / `run_matrix.py` 自动发现,没有注册表要改。

## ⚠ 开工第一件事:读进度文件

**你的上下文随时可能被压缩清空。进度存在磁盘上,不在你脑子里。**

**读这个文件**(用你手上的读文件工具即可,别纠结 shell 命令):

```
artifacts/progress_<品牌>_<型号>.md          # 不存在 = 全新开始
```

**每做完一步,立刻追加一行**(十几个字,几乎不花 token),格式固定:

```
# Mercusys MR80X  url=http://192.168.1.1  pass=见用户消息
nav=Internet
py=vendor/python/python.exe
dump=artifacts/inventory_Mercusys_MR80X.txt  OK
facts=已写入 models/Mercusys_MR80X.py
count=dial 1 / apply 1 / pppoe_user 1     全部==1
check=PASS
live=dynamic OK / pppoe OK / l2tp FAIL(read_back='')
next=修 l2tp 的措辞,其余已完成
```

被压缩之后:**读这个文件 → 从 `next=` 那一行继续,不要重新探测**。
已经 OK 的步骤**一律不重跑**,三个后果各不相同:

- 重跑 `--dump` —— 只是浪费时间;
- 重跑 **`--emit` —— 会无条件覆盖 `models/<品牌>_<型号>.py`,你手改过的 FACTS
  全部丢失**。进度文件里只要有 `facts=已写入`,就**永远不要再跑 `--emit`**;
- 重跑 `--apply` —— 会真的改设备配置。

**型号名从头到尾用同一个字符串**(`<品牌>_<型号>`,不含空格),进度文件、
清单文件、脚本文件名、`check_model` 的参数都用它 —— 不一致的话,压缩之后
你会找不到自己的进度。

## 第二件事:确定用哪个 python

**永远不要直接敲 `python`。** PATH 上那个在台架上是不能动的 Python 2,别处通常
也没装 Playwright —— 直接敲只会得到 `No module named 'playwright'`,而那**不是
适配问题**。

**一条一条试,谁先打印出版本号就用谁**(不要写 if/else —— 你可能在 cmd、
PowerShell 或 bash 里,分支语法各不相同):

```
vendor/python/python.exe -c "import playwright,sys;print(sys.version)"
.venv/Scripts/python.exe -c "import playwright,sys;print(sys.version)"
.venv/bin/python          -c "import playwright,sys;print(sys.version)"
python3                   -c "import playwright,sys;print(sys.version)"
```

选定后**把它记进进度文件的 `py=` 行**。下文所有命令里的 `<PY>` 都替换成它
(这是一个占位符,不是 shell 变量 —— 直接写全路径最保险)。

**「不要读 `vendor/`」指的是不要读它里面的文件(97 MB),但它的 `python.exe`
正是你要用的解释器** —— 两件事不冲突。四条都失败就如实报告,
**不要自己 pip install**(台架离线,装不上)。

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

**先判断走哪条**:长得像已知家族(Vue 类 / 老式 frameset / LuCI-CBI)就先白试一次
自动生成 —— 它不花 token,成了就直接跳到第 3 轮:

```
<PY> tools/probe_router.py --url http://<ip> --pass <密码> --nav "<菜单文字>" --probe-modes --brand <品牌> --model <型号> --emit models/<品牌>_<型号>.py
```

摘要里没有 `TODO` = 这台机不用你判断任何东西。**留了 TODO 就往下走,别去修它的
猜测逻辑。全新样子的 UI 直接跳过这条,从第 1 轮的 `--dump` 开始** —— 对没见过的
UI 猜测多半失败,再去修猜测结果是纯浪费。

**第 1 轮:探到页面 + 抄下来**(一次跑完这几条,一起汇报)

**每条命令写成一行**(别用 `^` 或 `\` 续行 —— 各 shell 不一样):

```
curl -m 4 http://<ip>
<PY> tools/probe_router.py --dump --url http://<ip> --pass <密码> --nav "<设置页菜单文字>" > artifacts/inventory_<品牌>_<型号>.txt
```

然后**读** `artifacts/inventory_<品牌>_<型号>.txt`。
(重定向不好使就照常打到屏幕上,再用写文件工具存成同名文件 —— 存盘这一步
不能省,它是被压缩之后唯一的依据。)

清单每行一个控件(`vis=` 是否可见),**只读这份,别去看页面源码**。
拨号控件没出现 = 多半还停在首页,补 `--nav "<菜单文字>"`(前缀 `sel:` 表示用
选择器)重跑这一轮。

**登录不上时加这两个参数**(老 UI 常见:密码框不是标准的,或登录键只认鼠标
点击、回车不提交):

```
--login-pass "<密码框选择器>"    --login-btn "<登录键选择器>"
```

不给 `--login-btn` 时探针会按回车、并自己找像登录键的元素(含 `<a>`/`<div>`);
失败会打印登录页诊断(密码框/文本框/按钮/可点元素 + 截图),**从那份诊断里挑
一个再传进来**,别猜。

**账密框在清单里看不到是正常的** —— 很多 UI 要**选完拨号方式才挂载**它们
(LuCI 就是:`wan.username` 在初始的 DHCP 档下根本不存在)。而清单里那些**看得见
的输入框未必是拨号用的**:同一页别的段(VPN Server、无线)也有 Username/Password,
**填错了就是假成功**。所以字段这样拿:

```
<PY> tools/probe_router.py --url http://<ip> --pass <密码> --nav "<菜单文字>" --probe-modes --brand <品牌> --model <型号> --emit models/<品牌>_<型号>.py
```

`--probe-modes` 会逐档选一次(**只切换,不保存**),把每档真正挂载出来的框抄下来,
并按"当前是哪一档"定概念。摘要里会写清每档要填什么。
它不适用于自定义下拉(非原生 `<select>`)——那种就自己在页面上切一档再 `--dump`
一次,对比多出来哪些框。

**存进度**:`dump=... OK` 和 `nav=...`。

**第 2 轮:写 FACTS + 一次性验证全部选择器**

照 `reference.md` 的键写(或复制 `models/Cudy_AX3000.py` 改),写进
`models/<品牌>_<型号>.py`,然后**一条命令验完所有选择器**:

```
<PY> tools/probe_router.py --url http://<ip> --pass <密码> --nav "..." --count "<拨号控件>" --count "<保存键>" --count "<账密框1>" --count "<账密框2>"
```

**在命令行上,Playwright 的文本匹配一律写单引号、外层用双引号包**:

```
--count "div.v-form-item:has-text('Internet Connection Type') div.v-select"
```

`:has-text('...')` / `:text-is('...')` 单引号是合法的(已实测)。**别在命令行里
用内层双引号** —— PowerShell 会把它吃掉,你会得到语法错或错误的命中数,而这
仓库以前就为同一个原因栽过(所以 `chariot_perf.py` 才有 `--json-file`)。
写进 `models/*.py` 时用哪种引号都行,那是 Python 字符串,不过 shell。

**命中数不是 1 就不能用**(`button:text-is('Connect')` 常命中 0,文字在里层
span;含点号的 id 只能写 `[id='...']`;`cbi.apply` 那类常命中 4)。不唯一时先试
这两条收窄法:

```
form:has(<拨号控件>) <按钮>                     # 一页多段、每段一个保存键
div.<行class>:has-text("<标签文字>") <控件>     # 类名不唯一,用标签锚定
```

**存进度**:`facts=...` 和 `count=... 全部==1`。

**第 3 轮:体检 + 逐模式真机验证**

```
<PY> tools/check_model.py <品牌>_<型号>
<PY> models/<品牌>_<型号>.py dynamic
<PY> models/<品牌>_<型号>.py pppoe
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
