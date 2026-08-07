---
name: adapt-router-model
description: 为一台新路由器型号产出专属拨号切换脚本 models/<品牌>_<型号>.py,并验证到能跑整轮性能测试。触发场景:适配新型号 / 接入新路由器 / 加一台 Buffalo(Huawei/…)/ onboard a new router model / add router model / 生成 Tenda_XXX.py 这类脚本 / 某型号登录不进去或切换不成功要修 FACTS。输入:一台能访问到的路由器(同局域网),或用户回传的一份控件清单。
---

# 适配一台新路由器型号

**产出**:一个文件 `models/<品牌>_<型号>.py` —— 这台机的 FACTS,加一个 `run()`
说明操作顺序(规矩机型就是转调默认配方的那三行)。放进 `models/` 就完事,
`start.py` / `run_matrix.py` 自动发现,没有注册表要改。

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

**可以读**(便宜且直接有用):

| 文件 | ≈token | 什么时候读 |
|---|---|---|
| 和这台机最像的那个参考脚本(见下面登记册) | 600–1600 | **写 FACTS 之前读一个**,它就是产出物的样板 |
| `artifacts/inventory_*.txt` / `progress_*.md` / `crash_*.txt` | 20–400 | 随时 |
| `reference.md` 的**某一节** | 按节 | 拿不准某个键怎么写时 |

**不要读**(读一次就烧掉整轮预算):`models/_driver.py`(5000–7000)、
`GOTCHAS.md` 全文(1.4 万+)、`artifacts/probe_*.json`(真机上几百 KB)、
`*.png`、`vendor/` 里的文件、`reference.md` 全文。

不要逐行打印脚本(只输出 FACTS dict)。改 `_driver.py` 不再是禁区,但要按下面
「需要一个新动词时」的三步走,而且**得配 mock**;`tools/` 不用动。
**`adapt.py` 是给人用的向导 —— 别调用它,也别去修它。**

**每轮尽量多跑几条命令再汇报**,别一条一问 —— 轮数越少,被压缩的机会越小。

## 铁律(违反 = 返工)

1. **不猜没观察过的 DOM**,每个选择器都要 `--count` 实测 ==1。宁可留 `TODO`。
2. **只有真实回读 == 目标措辞才算成功**,永远不放宽成子串
   ("PPPoEv6" 会被认成 "PPPoE")。
3. **默认不点保存**,全部回读正确才 `--apply`;切错会断网。
4. **凭据不进仓库**(走 `router.yaml`,已 git 忽略)。

## 已支持的型号 / UI 家族(先在这里找最像的)

**面对新机器,先看它像哪一行** —— 这决定了自动生成能不能成,也告诉你会踩什么坑。

| 型号脚本 | UI 家族 | `--emit` 能自动生成? | 这台特有的坑 |
|---|---|---|---|
| `Tenda_AX3000.py` | Vue SPA,role-less `div` 下拉 | 能(实测重建一致) | 保存键文字在里层 `<span>`,必须双锚定;IPv6 在独立页,靠 `enable_toggle` 开门 |
| `Cudy_AX1500.py` | 老式 **frameset**(Realtek SDK) | 能 | 菜单/表单在不同子 frame;藏着 8 个 `*Connect` 诱饵;PPTP 与 L2TP 字段分家 |
| `Cudy_AX3000.py` | **LuCI / CBI**(OpenWrt) | 能 | id 含点号只能 `[id='...']`;4 个 `cbi.apply` 要按 form 收窄;选完 proto 才用 XHR 挂载字段 |
| `Cudy_BE6500.py` | LuCI / CBI,同上 | 能 | 与 AX3000 同家族,**照它改十分钟就好**;差别只有 dynamic 的措辞是 `DHCP`(AX3000 是 `DHCP(Dynamic IP)`)。字段选择器都用 `form:has(...)` 收窄过,比 AX3000 更稳,新 LuCI 机照这份抄 |
| `BUFFALO_WSR6000AX8.py` | Buffalo 老 UI,**外壳页里套 iframe** | **不能** | **操作顺序特殊的参考实现,已真机验收** —— 遇到「顺序不对就保存旧值」这类机器照它的 `run()` 抄 |
| `Mercusys_BE3600.py` | Vue 类,`role=combobox` | 未验 | `dial` 写的是 `[role='combobox']`,**太松**,同页多个下拉时会驱动错控件 |
| (进行中)`Mercusys_MR80X` | 老 UI,与 BE3600 不同 | — | **登录进不去**是当前卡点;BE3600 的登录 FACTS 能登进它,说明差别在登录键 |

三个"能"的家族覆盖了目前见过的大部分路由器 UI。**长得都不像,就直接从第 1 轮
的 `--dump` 开始,别浪费时间在自动生成上。**

### 每个型号脚本都有一个 `run()`(2026-08-06 起)

`models/_driver.py` 是**动词库 + 一份默认配方**,不是框架:型号脚本调它。
所以每个脚本末尾都有这三行,规矩机型一个字都不用改:

```python
def run(facts=None, mode="dynamic", **kw):
    return default_run(facts or FACTS, mode, **kw)
```

**操作顺序**本身是特例的机型,就自己拼动词 —— 不再需要重写整条流程。
动词清单:`python models/_driver.py --verbs`。例(Buffalo,全文见它的脚本):

```python
with session(facts or FACTS, mode, **kw) as s:
    if not s.login():        return s.fail("登录失败")
    if not s.goto_iframe():  return s.fail("设置页没在 iframe 里就绪")
    s.set_mode(force=True)   # 控件被皮盖住,force 点
    s.fill_params()
    return s.apply_and_verify(force=True)
```

**成功判定只有一个出口。** `apply_and_verify()` 是唯一能产出 `success=True`
的动词(判据是 `set_mode()` 那次真实回读),`fail()` 是唯一的失败出口,裸的
"点保存"不对外导出。**成功判定类的动词,永远不许新增。**

### 需要一个新动词时(替换了旧的「禁止编辑 driver」)

1. **先试参数化**:多数"新动词"其实是老动词加参数(`force=True`、换等待
   策略)。能用参数表达就不算新形态。
2. **确实是没见过的形态** → 写进**动词库**(`_driver.py`),配一个复现该形态的
   mock,并且既有 mock 全绿。
3. **绝不允许**在 `models/*.py` 里写私有辅助函数(`_enter_frame()` 那种)——
   十台机之后就是六份几乎一样的私有导航函数,比一个特例脚本更难发现。

默认仍是**先提出需求 + 说明老动词为什么不够**(driver 里"Vue 重渲染要等"、
"某些控件必须 force 点"这些教训是一台台踩出来的,新写的原语不会自带),
但这是默认,不是禁令:证据充分且 mock 已配,就做完它。

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

- **崩溃**(抛异常退出)→ 看 `artifacts/crash_*.txt`(20 行),多数是环境问题;
- **登录**进不去 → 看探针打印的登录页诊断,按第 1 轮那两个参数重试;
- **定位**(清单里看得见控件,但选择器不唯一/回读不对)→ 便宜,用两条收窄法
  + `--count`。**修法必须通用**,`_driver.py` 和 `probe_router.py` 里没有一行按
  品牌分支的代码;
- **形态**(页面上有、清单里压根没有这种控件)→ 贵,见下。

**探针本来就吃不下的东西**(遇到不是你没弄对,别反复试):

- `--probe-modes` **只支持原生 `<select>`** —— 自定义下拉要自己在页面上切一档
  再 `--dump` 一次,对比多出来哪些框;
- closed shadow DOM / canvas 自绘 / 验证码登录 —— 抄不到,如实报告;
- 保存前要确认弹窗的机型 —— 驱动点完保存不会去点弹窗,`--apply` 会报"已点但
  没生效",如实报告;
- 卡片条 / 分段选择器 —— 现有三种 `dial.kind` 都不是它,**别硬套**。

**任何一条命令崩了都不要卡住**:五条命令彼此独立,而且你**永远不需要工具替你
生成脚本** —— 有 `--dump` 的清单 + `reference.md` 的格式,自己写 dict 就行,
这条路没有环节会崩。只要清单存过盘,前面就没有白跑。

## 最后一步:把这次学到的写回本文件

**验收通过之后**(真机逐档回读全对),做两件小事 —— 这是下一个人少走弯路的
唯一来源:

1. 在上面「已支持的型号」表里**加一行**:型号脚本 / UI 家族 / `--emit` 行不行 /
   **这台特有的坑**(一句话)。
2. 如果踩到了表里没有的新坑,在 `reference.md` 的「陷阱清单」**加一条**。

约束(别把登记册写坏):

- **只加,不改写已有内容**;一次最多加一行 + 一条陷阱;
- **只写实测过的**。没跑通就不要加行,可以在型号那格写"(进行中)"并注明卡在哪
  —— 像上面 MR80X 那样,那比空着有用;
- 坑要写成**别人能照做的一句话**(「id 含点号只能用 `[id='...']`」),
  不是感想(「这个 UI 很奇怪」)。

**改不了这个文件**(skill 是只读的 / 你是被粘贴进来的)?那就把要加的那一行
**原样输出给用户**,让他自己粘进去 —— 别因为写不了就跳过这一步,这是整套
流程里唯一会累积的东西。

## 更细的东西在 `reference.md`(按需读,别预加载)

FACTS 逐键说明、选择器手册、陷阱清单、定位问题的通用修法、判定"这台机真的没有
某功能"的穷尽核查法、参考实现对照表。
