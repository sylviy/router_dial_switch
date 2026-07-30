---
name: adapt-router-model
description: 为一台新路由器型号产出专属拨号切换脚本 models/<品牌>_<型号>.py,并验收到能跑整轮性能测试。触发场景:适配新型号 / 接入新路由器 / 加一台 Buffalo(Huawei/…)/ onboard a new router model / add router model / 生成 Tenda_XXX.py 这类脚本 / 拿到一份 probe 产物要写脚本 / 某型号切换失败要修 FACTS。输入:一台能访问到的路由器(同局域网),或一份 artifacts/probe_*.json。
---

# 适配一台新路由器型号

## 产出什么

**一个自包含的文件**:`models/<品牌>_<型号>.py`。里面只有这台机的"事实"
(FACTS:登录、菜单路径、控件选择器、各模式界面措辞、保存键),点击逻辑一律
在共用的 `models/_driver.py` 里 —— **不要为某一台机改驱动**。

放进 `models/` 就完事了:`start.py`、`run_matrix.py`、`dial.bat` 都是扫目录
自动发现的,**没有任何注册表要改**。

同事拿到后的用法:`python models/<品牌>_<型号>.py pppoe`,或直接双击
`start.bat` 选型号跑整轮。

## 铁律(违反任何一条 = 返工)

1. **不猜没观察过的 DOM。** 每个选择器都要有出处:probe 产物、真机页面、或
   用户回传的控制台输出。宁可留 `TODO` 让它诚实地失败,也不写"大概是这样"
   —— 猜出来的"成功"在真机上坑过两次(小米假成功、误点"应用")。
   `tools/check_model.py` 会把残留的 TODO 当错误拦下,别绕过它。
2. **只有真实回读 == 目标措辞才算成功。** 驱动已内置这条判定(整体或逐行
   精确相等)。**永远不要**把任何判定放宽成子串 —— "PPPoEv6" 会被认成
   "PPPoE"。
3. **默认不点保存。** 验证阶段一律不带 `--apply`;所有模式回读都对了,才带
   `--apply` 验收。切错模式会断网 —— 别在承载真实上网的路由器上做验收。
4. **凭据不进仓库。** 管理密码/宽带账号进 `router.yaml`(git 已忽略)。
   probe 产物含表单值和 URL,可能带会话 token,回传前先过一眼。

## 先省钱:这条流程的大部分不需要 agent

`probe_router.py --emit` 和 `check_model.py` 是**确定性命令**,产出跟谁来跑没有
关系。**型号脚本由工具写出来,不要让模型逐字生成**(那是纯粹的输出 token 浪费,
而且更容易写错选择器)。

agent 真正该介入的只有三处:探针留下的 `TODO`、需要 `mode_overrides` 的模式
(某档住在自己的页面上)、以及真机跑失败后的判断。其余照着命令跑就行。

**永远不要整份读进上下文的东西**(读一次就可能吃掉几万 token):

| 别读 | 改用 |
|---|---|
| `artifacts/probe_*.json`(完整证据,给人存档的) | 探针 **stdout 的摘要**,已经含 FACTS 建议 |
| `artifacts/*.png`(每次运行都会截图) | 只在失败且文字信息不够时才看 |
| `models/_driver.py`(574 行) | 不用读。它的行为本文件已经写全 |
| `vendor/`(97 MB 运行时) | 永远不要 |
| `CLAUDE.md` 全文 | 只在需要历史结论时查特定一节 |

某个选择器有疑问时,从 JSON 里**取那一段**,不要整份读:

```bash
python -c "import json;d=json.load(open('artifacts/probe_x.json'));\
print(json.dumps([b for f in d['frames'] for b in f.get('buttons',[])],ensure_ascii=False,indent=1))"
```

## 流程

### 第 0 步:准备

```bash
python start.py --setup      # 存路由器 IP / 管理密码 -> router.yaml(git 忽略)
```

**如果操作者是人而不是 agent,直接让他跑 `python adapt.py`(Windows 双击
`adapt.bat`)** —— 那是同一条流程的向导版:问品牌/型号/地址/密码,然后自动
走完探测 → 生成 → 体检 → 逐模式验证,每步用人话解释,找不到控件时会停下来问
"设置页在哪个菜单"。下面这些分步命令是它内部做的事,agent 需要精细控制
(补 `--nav`、`--open`、改选择器)时才手动用。

必须在**能访问到路由器的机器**上跑(和路由器同一局域网)。沙箱环境常常能上
互联网但到不了路由器的内网 —— 先 `curl -m 4 http://<ip>` 探一下,别凭旧结论
下判断。真连不上就走「拿不到真机时」那一节。

### 第 1 步:取证(唯一的信息来源)

```bash
python tools/probe_router.py --url http://192.168.1.1 --pass <管理密码>
```

这是个**只读探针**:登录 → 抄下整页(含所有子 frame)的控件 → **用
Playwright 引擎当场验证每个候选选择器的命中数** → 产出
`artifacts/probe_*.json` + 一份 FACTS 建议。它绝不会点保存/应用/Connect。

为什么非它不可:浏览器控制台只能验 `document.querySelectorAll(sel).length`,
而 FACTS 用的是 Playwright 语法(`:text-is()` / `:has()` / `:visible`),控制台
验不了。2026-07-18 台架实测:亲眼看到按钮文字是 "Connect",写下
`button:text-is("Connect")` 却命中 0 —— 文字在里层 `<span>` 上。
**"看到了事实" ≠ "验证了选择器"。** 探针用的就是 `_driver.py` 自己的登录/
导航/查找函数,所以探针跑通 ≈ 交付脚本跑得通。

常用参数:

```bash
# 登录后落在别的页,要点菜单才到 WAN 页(文字精确匹配;sel: 前缀表示用选择器)
python tools/probe_router.py --url ... --pass ... --nav "Internet Settings"
python tools/probe_router.py --url ... --pass ... --nav "sel:#Network" --nav "sel:#WAN"

# 自定义下拉:只有点开才看得到其余模式的原文(只点触发器,不碰保存键)
python tools/probe_router.py --url ... --pass ... --open 'div.v-form-item:has-text("Internet Connection Type") div.v-select'

# 直接落一个骨架文件(未观察到的项写成 TODO,check_model.py 会拦)
python tools/probe_router.py --url ... --pass ... --brand Tenda --model AX3000 \
    --emit models/Tenda_AX3000.py
```

典型节奏:**先裸跑一次** → 看摘要里 `dial` 有没有找到 → 没找到就补 `--nav`
→ 找到了但 modes 只有一个,就用它给出的选择器 `--open` 再跑一次 → `--emit`。

读摘要时重点看两件事:

- 每个 frame 的控件计数(老式 frameset 的表单在子 frame 里,这里能看出来);
- FACTS 建议里还剩几个 `TODO`(那就是还没拿到的证据)。

改某个具体选择器时,JSON 里每个候选都记了 `pin.tried`(**试过哪些写法、各自
命中几个**),照着挑,不要自己现编 —— 但**按上面「先省钱」那节的办法只取那
一段**,别把整份读进来。

### 第 2 步:补全 FACTS

探针能自动填对的:`login` / `wan_path` / `dial`(含 `value` 回读锚点)/
原生 `<select>` 的全部 `modes` / `fields` / `apply` / PPTP 与 L2TP 的
`mode_overrides` 拆分。**需要人判断的**通常是这几件:

| 情况 | 怎么办 |
|---|---|
| `modes` 里还有 `TODO` | 用 `--open <dial.selector>` 再跑一次抄选项原文 |
| 某模式整页不同(IPv6 最常见) | 加 `mode_overrides`,照 `models/Tenda_AX3000.py` |
| 整块表单被"使能开关"挡着,页面空空如也 | `enable_toggle`(见下方陷阱) |
| 探针把 `dial` 指到了别的下拉(ISP Type / MTU / DNS) | 从 `pin.tried` 里挑 label 锚定那条 |
| 界面语言会变(中/英切换) | 优先属性锚点(id / name / data-\*),别用文字 |

字段名(`fields` 的键)必须用 `modes.py` 里 `MODE_REQUIRED_FIELDS` 的概念名,
否则整轮取不到账号密码。完整 FACTS 键说明见同目录 `reference.md`。

### 第 3 步:离线体检

```bash
python tools/check_model.py <品牌>_<型号>
```

不需要路由器。它拦下的都是真机上花过时间的坑:残留 TODO、某模式覆盖后缺
`dial`/`apply`、要填的账密字段没有选择器、两个模式措辞一样(回读分不开)、
选择器语法本身不合法、没有 CLI 入口。

**体检通过 ≠ 可以验收** —— 它答不了"这个选择器在真机上命中几个"。

### 第 4 步:真机逐模式验证(不点保存)

```bash
python models/<品牌>_<型号>.py dynamic          # 看 JSON 的 success + read_back
python models/<品牌>_<型号>.py pppoe            # 账密自动从 router.yaml 按模式取
# ... modes 里每一档都过一遍
```

`success:true` 且 `read_back` 就是你要的措辞,才算这一档过了。失败时
`message` / `warnings` 会指明卡在哪一步(菜单没找到 / 控件没找到 / 选项措辞
不对 / 输入框没出现),并且会**列出它当时实际看到的东西**(下拉里有哪些选项、
页面上有哪些按钮)—— 照着改 FACTS,不要重新猜。

**这一步由 agent 自己跑完再交付**,别把第一次运行留给用户。这是唯一会用运行时
引擎逐个吃掉 FACTS 选择器的环节。

### 第 5 步:验收(真正下发)

全部模式回读正确后,每档带 `--apply` 各跑一次,确认 `applied:true`。
断网风险自负 —— 确认这台机不是当前在用的上网出口。

### 第 6 步:固化成离线回归(强烈建议)

把真机页面的结构做成 `tests/mock_router/<品牌>.html`(frameset 机型照
`cudy*.htm` 那套做),在 `tests/smoke_test.py` 的 `model_cases` 里加一条。
这台型号从此有离线回归,别人改驱动不会悄悄弄坏它。

```bash
python tests/smoke_test.py        # 必须 0 failed
```

做 mock 时**要把诱饵一起做进去**(同名的 radio、隐藏的 Disconnect 按钮),
不然这条用例证明不了驱动没点错东西。

### 第 7 步:告诉用户台架还要配什么

型号脚本本身不管这些,但不配整轮跑不起来:

- `perf.yaml` → `dial_modes`:这台机要测哪几档(不写 = 脚本声明的全部)。
  **`static` 记得排除** —— 它没有字段映射,会切过去且不填任何地址。
- `perf.yaml` → `wan_up.hosts`:**按模式**配 ping 目标(直连段和隧道段是两个
  网段,配一个全局 host 会让另一半白等满超时)。
- `perf.yaml` → `chariot.nofrag_bytes`:要测 UDP 不分片档才需要,按模式给
  MTU;没配的模式会明确报错,不猜。
- `router.yaml` → `params[<模式>]`:L2TP 和 PPTP 字段名相同但账号不同,
  必须分模式存。

## 卡住了:先分清「定位问题」还是「形态问题」

**这是排查时最省事的一个判断,先做它,再做别的。** 两类的成本差一个数量级,
处理方式也完全不同。

先分出**第三类:崩溃**。工具直接抛异常退出(浏览器窗口被关、地址不通、超时、
Chrome 找不到)—— 那既不是定位也不是形态问题,是**运行环境**的事。
`tools/crashlog.py` 会先认已知病症并直接给人话结论(这几种占绝大多数,
**根本不用问 agent**);认不出来才落一份 `artifacts/crash_<时间>.txt` ——
二十行左右,只含本仓库的调用栈,浏览器日志已滤掉,密码已脱敏。
**贴那个文件,不要贴终端上几十行的 Playwright 原始报错。**

驱动只认**三种控件形态**:`dial.kind` = `select` / `dropdown` / `radio`。

| | 定位问题 | 形态问题 |
|---|---|---|
| 症状 | 探针**认出了**控件(`拨号控件:找到了(select/dropdown)`),但选择器不唯一、按钮找不到、字段没挂出来、回读对不上 | 探针反复说 `没找到`,而你在页面上**明明看得见**那个控件 |
| 本质 | 这三种形态之一,只是没定位准 | 根本不是这三种 |
| 成本 | 便宜。改探针的候选生成或 FACTS 里的一两行 | 贵。要给 `_driver.py` 加一个新 `kind` + 配 mock |
| 谁来 | 自己跑命令多半就行,或问 agent「改哪一行」 | 一次真正的功能开发,当成一件事单独做 |

**怎么一眼分辨**:看探针摘要里 `拨号控件:` 那一行。写着"找到了"就是定位问题
——哪怕后面全是错的。反复"没找到"、而页面上你看得见控件,再看它长什么样:
**一排可点的方块**(`动态IP | 静态IP | PPPoE` 卡片条)、分段按钮、或者点开后
选项在 closed shadow DOM 里 —— 那是形态问题,见「边界」。

### 定位问题:修法必须是通用的

2026-07-29 适配 LuCI 那台时冒出来四个问题,**没有一个是"LuCI 支持"**:

| 当时的症状 | 真正的毛病 | 修完谁受益 |
|---|---|---|
| 没问菜单就往下走,保存键和字段全认不出 | 隐藏的 `<select>` 被当成"找到了"(`count()` 数得到 `display:none`) | 任何没导航到位的页面 |
| `#cbid.network.wan.proto` 命中 0 | 只试了 `#id`,而这 id 含点号,被解析成 id+class | 任何 id 带点/冒号的 UI |
| `button[name='cbi.apply']` 命中 4 | 不唯一就放弃了,没想到用容器收窄 | 任何"一页多段、每段一个保存键"的 UI |
| `fields` 永远是空的 | 字段选完模式才挂载,且名字里没有协议字样 | 任何"选完模式才渲染表单"的 UI(现代 SPA 全是) |

**`models/_driver.py` 和 `tools/probe_router.py` 里没有一行按品牌分支的代码,
保持这样。** 修定位问题时,如果你正要写 `if brand == ...` 或者往 FACTS 里塞一个
只对这台机成立的特判,**停下来** —— 说明毛病没找准。正确的修法读起来永远是
一条通用规则(「可见的优先」「不唯一就用容器收窄」「按当前模式定概念」)。

顺带:每加一个 UI 家族,就在 `tests/mock_router/` 留一份永久回归(见第 6 步)。
这就是为什么定位问题可以放心大胆改 —— 改坏了已验收的机型会当场红。

### 形态问题:先如实报告,别硬造

现有三种形态吃不下的东西列在「边界」里。遇到了:

1. **先说清楚**它是什么形态、页面上长什么样,不要为了交差硬凑一个 FACTS;
2. 真要支持,是**改驱动**:加一个新 `dial.kind`,配一份 mock 用例,冒烟必须全绿;
3. 那是一次功能开发,要和用户单独确认 —— 不是适配某一台机的顺手活。

## 陷阱(每一条都是真机上翻过的车)

- **登录是异步渲染的。** 扫一次找不到密码框不等于没有登录页。驱动已经在轮询
  等待,别改成一次性扫描。部分机型(Tenda / Mercusys)**同时只允许一个 Web
  会话** —— 跑之前先把浏览器里登录着的页签退掉,否则会被踢回登录页。
- **`:text-is()` 只匹配"直接拥有该文本节点"的元素。** 文字在里层 `<span>` 时
  必须双锚定:`button[data-name='submit']:has(span:text-is("Connect"))`。
  探针已经会自动生成这种写法 —— 别手工改回单锚定。
- **按钮别用子串匹配。** Cudy 的 WAN 帧里藏着 8 个 `*Connect`/`*Disconnect`
  提交键,Tenda 连接态也有 Disconnect。优先按 `name`/`id` 锚定。
- **`enable_toggle` 只在看不到拨号控件时才碰。** 驱动已保证这一点(否则会把
  已经开着的页面点关)。开关状态要读**真正带状态的那个节点** —— Tenda 的外层
  `div.v-switch` 没有状态标记,状态在内芯 `[data-name='ipv6En']` 上。
- **同名诱饵。** Tenda 的 IPv6 页 LAN 区有一个同叫 "DHCPv6" 的 radio。驱动优先
  在 option 形态容器(`[role='option'], [class*='opt']`)里找选项,所以不会点
  错;别把选项匹配改成"页面上任意同名文字"。
- **v6 模式按 flavor 命名**(`dhcpv6` / `pppoev6`),不要用笼统的 `ipv6`。
- **全 frame 扫描。** 老式 frameset 的菜单、表单、保存键在不同子 frame 里。
- **仓库路径里有 `[Tool]`,是 glob 的字符类。** 扫目录用 `os.listdir`,别用
  `glob`(用了会静悄悄返回空)。

## 判定"这台机没有某功能"(如 IPv6)—— 别只看菜单

用户问"真的没有?"时,**可见菜单里没有链接不算证据**。三步穷尽核查(Cudy
就是这么定案的):

1. **枚举固件实际引用的所有页面**:正则抓各 frame HTML 里的 `*.htm`,逐个 GET
   全文搜关键词(Cudy 这样翻出 49 个页面);
2. **直接访问候选页面**(`ipv6.htm` / `sub_menu_ipv6.htm` …):404 = 没打包;
3. **翻导航 JS**:很多 SDK 型 UI 是 `if(flag){ 画这个菜单 }`,而 flag 由服务端
   注入(Cudy 的 `top_menu.htm` 写死 `var ipv6 = 0;`)。这一步能区分
   **"固件没做"** 和 **"这台机的构建关掉了"** —— 结论完全不同,后者升级固件就有。

顺带留意 `display:none` 行里的死控件(Cudy 的 `ipv6_passthru_enabled`):
**存在 ≠ 可用**,别写进 FACTS。

## 拿不到真机时

- 让用户在能访问路由器的机器上跑第 1 步,回传 `artifacts/probe_*.json`
  (提醒脱敏),你照产物写 FACTS;
- 用户机器上连 Python 都没有:让其在浏览器控制台跑
  `document.querySelectorAll("<选择器>").length` 回报数字 —— 但记住这**验不了**
  Playwright 专有语法,那部分必须留到第 4 步兜底;
- 无论哪条路,**拿到证据之前不要动笔写 FACTS**。

## 边界(现在吃不下的)

这一节列的都是**形态问题**(见上面「卡住了」那节):不是选择器没写对,是
`_driver.py` 的三种 `kind` 都套不上。

- 卡片条 / 分段选择器(一排 `Dynamic | Static | PPPoE` 卡片)、值文本不是模式
  词的控件、保存前的确认弹窗、closed shadow DOM、captcha 登录、canvas 画的 UI。
  遇到先**如实报告**,不要硬造 FACTS。真要支持,是在 `_driver.py` 加一个新的
  `dial.kind` 并配 mock 用例 —— 那是改驱动,要单独讨论。
- 本 skill 只管"切拨号方式"。连通性/吞吐是整轮(`run_matrix.py`)的事,
  型号脚本里的 `verify_hook(page, result)` 是留给它的接口。
