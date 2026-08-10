# FACTS 完整参考 + 选择器手册

`models/<品牌>_<型号>.py` 里那个 `FACTS` 字典的每一个键。运行时怎么用它们,
看 `models/_driver.py`;这里是写的时候的对照表。

## 顶层键

| 键 | 必填 | 说明 |
|---|---|---|
| `brand` / `model` | 是 | 只用于提示和报告文件名 |
| `url` | 是 | 管理地址,如 `http://192.168.0.1`。运行时可用 `--url` 覆盖 |
| `login` | 否 | 整个键可以不写(没有登录页的机型)。写了就**必须**给管理密码,驱动会在开跑前检查 |
| `wan_path` | 否 | 进 WAN 页要**依次点击**的菜单项 |
| `dial` | 是 | 拨号控件本身 |
| `modes` | 是 | canonical 模式名 → **界面上的原文** |
| `fields` | 否 | 参数概念名 → 输入框选择器 |
| `apply` | 是 | 保存/应用键 |
| `enable_toggle` | 否 | 整块表单被开关门控时才写 |
| `options` | 否 | 自定义弹层选项的容器选择器,默认 `[role='option'], [class*='opt']` |
| `mode_overrides` | 否 | 某个模式整页不同时,**按键整个替换** |

### `login`

```python
"login": {"password": "#pwd",                    # 密码框;默认 input[type=password]
          "user": "#username",                   # 需要用户名的机型才写
          "button": "input[value='Login']"},     # 不写就按回车
```

驱动会先**轮询等**密码框出现(SPA 是异步挂载的),填完点按钮,再确认密码框
消失才算登录成功 —— 否则直接报 `login failed`,不会带着未登录状态往下走。

### `wan_path`

```python
"wan_path": ["Internet Settings"],          # 默认:按菜单文字**精确**匹配
"wan_path": ["sel:#Network", "sel:#WAN"],   # sel: 前缀 = 用选择器点
```

菜单点不到只是 warning,不会中断 —— 因为有些机型登录后就已经在 WAN 页。

### `dial`

```python
"dial": {"kind": "select",   "selector": "#wanType_id"},
"dial": {"kind": "dropdown", "selector": "div.v-form-item:has-text(\"Internet Connection Type\") div.v-select",
                             "value": "[data-name='wanType']"},
"dial": {"kind": "radio",    "selector": "(不用,modes 的值就是各自的 radio 选择器)"},
```

- `kind: "select"` —— 原生 `<select>`。被美化插件藏起来(`display:none`)也行,
  驱动用 `force=True` 驱动它,并派发 input+change。回读读的是
  `options[selectedIndex].text`,最可信。
- `kind: "dropdown"` —— 自定义下拉(Vue/React 的 div 组合件)。点触发器 → 在
  弹层里点选项 → 重新定位读回值。`value` 是**可选的回读子选择器**:触发器的
  innerText 常混着下拉小箭头之类的杂质,指到干净的值节点上更稳。
- `kind: "radio"` —— 单选组。此时 `modes` 的值填**每个模式各自 radio 的选择器**
  (不是文字)。驱动只信真 radio 的 `is_checked()`;读不到状态就不许报成功。

### `modes`

```python
"modes": {"dynamic": "DHCP Client", "pppoe": "PPPoE", "static": "Static IP"},
```

值是**界面上一字不差的原文**(含大小写、空格)。回读判定是精确相等,多一个
字符就永远判不成功。canonical 键名固定用这套:

`dynamic` / `static` / `pppoe` / `l2tp` / `pptp` / `dhcpv6` / `pppoev6`

v6 按 flavor 命名,不要笼统的 `ipv6`。键名的顺序就是整轮的测试顺序。

### `fields`

键必须是 `modes.py` 里 `MODE_REQUIRED_FIELDS` 用的概念名:

| 概念名 | 哪些模式要 |
|---|---|
| `pppoe_user` / `pppoe_pass` | pppoe(以及 pppoev6,按需显式传) |
| `vpn_server` / `vpn_user` / `vpn_pass` | l2tp、pptp |
| `static_ip` / `static_mask` / `static_gateway` / `static_dns` | static(**目前 modes.py 里是空的**,见 GOTCHAS.md「Known gaps」) |

**L2TP 和 PPTP 字段名相同、DOM 字段不同**(Cudy 是 `l2tpUserName` vs
`pptpUserName`)—— 必须拆进 `mode_overrides`,放一层里其中一个模式必然填错地方。
账号也一样:`router.yaml` 的 `params` 要按模式分块存。

输入框是**选完模式才挂载**的,驱动会等它出现,不用自己加延时。

### `apply`

```python
"apply": "input[name='save_apply']",                                  # 最稳:属性锚定
"apply": 'button[data-name=\'submit\']:has(span:text-is("Connect"))', # 文字在里层 span
"apply": 'button:text-is("Save")',                                    # 文字在按钮自己身上
```

`:text-is()` **只匹配直接拥有该文本节点的元素**。真机上 `<button><span>Connect
</span></button>` 会让 `button:text-is("Connect")` 命中 0 —— 这是 2026-07-18
Tenda 的实测教训。找不到保存键时,驱动会在 warning 里列出它看到的所有可见按钮。

### `enable_toggle`

```python
"enable_toggle": "[data-name='ipv6En']",
```

只在**看不到拨号控件**时才会被点(否则会把已启用的页面点关)。选择器要指到
**真正带状态的那个节点**:Tenda 的外层 `div.v-switch` 没有状态标记,状态在内芯
`[data-name='ipv6En']` 上(ON 时带 `v-switch__icon--active`)。驱动读状态的顺序:
`is_checked()` → `aria-checked`/`aria-pressed` → class 词元
(`checked/on/active/open/enabled`)。

### `mode_overrides`

```python
"mode_overrides": {
    "dhcpv6": {
        "wan_path": ["More", "IPv6"],
        "enable_toggle": "[data-name='ipv6En']",
        "dial": {...}, "modes": {"dhcpv6": "DHCPv6"},
        "apply": 'button[data-name=\'submit\']:has(span:text-is("Save"))',
    },
},
```

**按键整个替换**(不是深合并)。所以覆盖 `modes` 时,那一块里必须含这个模式
自己的措辞;覆盖 `fields` 时,要把该模式需要的字段写全。

出现在 `mode_overrides` 里的键,即使不在 `modes` 里,也算这台机支持的一个模式
(整轮会遍历到)。

## 选择器手册(引擎是 Playwright,比纯 CSS 强)

| 写法 | 用在哪 |
|---|---|
| `#someid` | 首选 |
| `[name='wan_type']` / `[data-name='wanType']` | 次选,属性锚点不随界面语言变 |
| `div.v-form-item:has-text("Internet Connection Type") div.v-select` | **类名不唯一时的正解**:用标签所在的表单行锚定 |
| `button:text-is("Connect")` | 按钮文字**精确**匹配(子串碰不到 "Disconnect") |
| `X:has(span:text-is("Connect"))` | 文字在里层元素时的双锚定 |
| `input:visible` | 两组同名字段只渲染一组时 |

**优先级:属性锚点 > 表单行锚定 > 文字锚定。** 界面语言一变,文字锚定就全废。

验证方法(只有第二条能验 Playwright 专有语法):

```javascript
// 浏览器控制台:只能验纯 CSS
document.querySelectorAll("<选择器>").length === 1
```

```bash
# 真引擎:probe 会把每个候选试过的命中数记进 artifacts/probe_*.json 的 pin.tried
python tools/probe_router.py --url ... --pass ...
python tools/check_model.py <型号>       # 至少能验语法合法性
```

### 在命令行上传选择器:一律内单引号、外双引号

```
--count "div.v-form-item:has-text('Internet Connection Type') div.v-select"
```

`:has-text('...')` / `:text-is('...')` 用单引号是合法的(已实测)。**别在命令行
里用内层双引号** —— PowerShell 会把它吃掉,你会得到语法错或**错误的命中数**,
而这仓库以前就为同一个原因栽过(所以 `chariot_perf.py` 才有 `--json-file`)。
写进 `models/*.py` 时用哪种引号都行,那是 Python 字符串,不过 shell。

## 一次运行的返回值

```json
{"success": true, "read_back": "PPPoE", "filled": ["pppoe_user", "pppoe_pass"],
 "applied": false, "message": "", "warnings": [], "screenshot": "artifacts/..."}
```

- `success` —— **只在真实回读 == 目标措辞时为 true**。别的都不算。
- `read_back` —— 界面回读到的实际值。失败排查先看它。
- `applied` —— 是否真的点了保存(只有 `--apply` 才可能是 true)。
- `message` / `warnings` —— 卡在哪一步,以及**当时实际看到的东西**
  (下拉里有哪些选项 / 页面上有哪些按钮)。照着改,别重新猜。
- 失败时会存一张全页截图。

## 陷阱清单(每一条都是真机上产生过的假成功)

- **登录是异步渲染的。** 扫一次找不到密码框不等于没有登录页;驱动在轮询等,
  别改成一次性扫描。部分机型(Tenda / Mercusys)**同时只允许一个 Web 会话**
  —— 跑之前先把浏览器里登录着的页签退掉,否则会被踢回登录页。
- **老 UI 的登录键常常不是 `<button>`** —— `<a class="button">`、
  `<div onclick=...>` 都见过,而且回车不提交。探针会把"可点元素"一并列出来。
- **HTTP Basic 认证的登录是浏览器原生弹窗,DOM 里没有密码框** —— 任何选择器
  都救不了。管理密码会同时当 `http_credentials` 用;首个响应是 401/403 就是它。
- **`:text-is()` 只匹配直接拥有该文本节点的元素。** 文字在里层 `<span>` 时必须
  双锚定:`button[data-name='submit']:has(span:text-is("Connect"))`。
  2026-07-18 Tenda 真机实测:单锚定命中 0。
- **按钮别用子串匹配。** Cudy AX1500 的 WAN 帧里藏着 8 个
  `*Connect`/`*Disconnect` 提交键,Tenda 连接态也有 Disconnect。
- **CBI/LuCI 的 id 含点号**(`cbid.network.wan.proto`):`#...` 会被解析成
  "id=cbid + 三个 class",命中 0。**一律用 `[id='...']`。**
- **`enable_toggle` 只在看不到拨号控件时才会被点**(否则会把已启用的页面点关)。
  选择器要指到**真正带状态的那个节点**:Tenda 外层 `div.v-switch` 没有状态标记,
  状态在内芯 `[data-name='ipv6En']` 上。
- **同名诱饵。** Tenda 的 IPv6 页 LAN 区有个同叫 "DHCPv6" 的 radio;LuCI 的
  VPN 段有个 PPTP/L2TP 的 Server Type 下拉。驱动优先在 option 形态容器
  (`[role='option'], [class*='opt']`)里找选项,别改成"页面上任意同名文字"。
- **隐藏的 `<select>` 也会被 `count()` 数到。** 没导航到设置页时整个面板是
  `display:none`,那时照样能"找到"拨号控件 —— 但保存键和账密框全在隐藏面板里,
  一个都认不出来。所以 `--dump` 里的 `vis=` 要看。
- **选完模式才挂载的字段**(LuCI 走 XHR 重建整段 DOM,连 `<select>` 一起换掉):
  回读能活下来是因为 `_locate` 返回的是 Locator(每次重新解析);
  ElementHandle 会失效。字段用 `--probe-modes` 或逐档手工看。
- **v6 模式按 flavor 命名**(`dhcpv6` / `pppoev6`),不要笼统的 `ipv6`。
- **全 frame 扫描。** 老式 frameset 的菜单、表单、保存键在不同子 frame 里。
- **仓库路径里有 `[Tool]`,是 glob 的字符类。** 扫目录用 `os.listdir`。

## 定位问题的修法必须是通用的

2026-07-29 适配 LuCI 那台时冒出四个问题,**没有一个是"LuCI 支持"**:

| 当时的症状 | 真正的毛病 | 修完谁受益 |
|---|---|---|
| 没问菜单就往下走,保存键和字段全认不出 | 隐藏的 `<select>` 被当成"找到了" | 任何没导航到位的页面 |
| `#cbid.network.wan.proto` 命中 0 | 只试了 `#id`,而这 id 含点号 | 任何 id 带点/冒号的 UI |
| `button[name='cbi.apply']` 命中 4 | 不唯一就放弃了,没想到用容器收窄 | 任何"一页多段、每段一个保存键"的 UI |
| `fields` 永远是空的 | 字段选完模式才挂载,且名字里没有协议字样 | 任何"选完模式才渲染表单"的 UI(现代 SPA 全是) |

如果你正要写 `if brand == ...`,或者往 FACTS 里塞一个只对这台机成立的特判,
**停下来** —— 说明毛病没找准。正确的修法读起来永远是一条通用规则
(「可见的优先」「不唯一就用容器收窄」「按当前模式定概念」)。

## 判定"这台机没有某功能"(如 IPv6)—— 别只看菜单

可见菜单里没有链接**不算证据**。三步穷尽核查(Cudy AX1500 就是这么定案的):

1. **枚举固件实际引用的所有页面**:正则抓各 frame HTML 里的 `*.htm`,逐个 GET
   全文搜关键词(那台翻出 49 个页面);
2. **直接访问候选页面**(`ipv6.htm` / `sub_menu_ipv6.htm` …):404 = 没打包;
3. **翻导航 JS**:很多 SDK 型 UI 是 `if(flag){ 画这个菜单 }`,而 flag 由服务端
   注入(那台的 `top_menu.htm` 写死 `var ipv6 = 0;`)。这一步能区分
   **"固件没做"** 和 **"这台机的构建关掉了"** —— 后者升级固件就有。

顺带留意 `display:none` 行里的死控件(`ipv6_passthru_enabled`):
**存在 ≠ 可用**,别写进 FACTS。

## 参考实现

| 文件 | 看它学什么 |
|---|---|
| `models/Tenda_AX3000.py` | Vue SPA、role-less 下拉、表单行锚定、`dial.value`、IPv6 独立页 + `enable_toggle` + `mode_overrides`、嵌套 span 的保存键 |
| `models/Cudy_AX1500.py` | 老式 frameset、原生 `<select>`、PPTP/L2TP 字段拆分、一堆隐藏诱饵按钮里挑保存键、"这台机没有 IPv6"的定案过程 |
| `models/Cudy_AX3000.py` | LuCI/CBI、含点号的 id、`form:has()` 收窄保存键、XHR 重建 DOM、三个模式共用一对输入框 |
| `models/BUFFALO_WSR6000AX8.py` | **操作顺序特殊**的机器怎么写:外壳页 + iframe、`goto_iframe`、被皮盖住的控件要 `force` |
| `models/_template.py` | 空白模板 |

Tenda / Cudy / Buffalo 都已在物理设备上通过验收(含 `--apply` 真实下发),
照它们抄。

## 各 UI 家族特有的坑(SKILL.md 的登记册只留「抄哪个」)

| 家族 | 坑 |
|---|---|
| Vue SPA,role-less `div` 下拉(Tenda) | 保存键文字在里层 `<span>`,`:text-is()` 命中 0 —— 必须 `button[data-name='submit']:has(span:text-is("Connect"))` 双锚定;IPv6 在独立页,靠 `enable_toggle` 开门;同页 5 个同 class 的下拉,只能用标签锚定 |
| 老式 frameset,Realtek SDK(Cudy AX1500) | 登录在主文档、菜单和 WAN 表单在不同子 frame(驱动全 frame 扫);藏着 8 个 `*Connect`/`*Disconnect` 诱饵,**这个牌子绝不能按文字 "Connect" 找保存键**;PPTP 与 L2TP 字段分家(`pptp*` / `l2tp*`) |
| LuCI / CBI,OpenWrt(Cudy AX3000 / BE6500) | CBI 的 id 含点号,`#cbid.network.wan.proto` 会被当成 id+3 个 class 而命中 0 → 只能 `[id='...']`;`button[name='cbi.apply']` 一页命中 4,要 `form:has(<拨号控件>)` 收窄;选完 proto 后整段 DOM 被 XHR 重建,账密框那时才挂上;登录是加盐挑战,填可见密码框按回车让页面自己算 |
| 外壳页 + iframe(Buffalo) | 设置页必须以外壳页里的 iframe 打开,直接开也能渲染、能点、能回读,但配置对象没加载,保存提交**旧值**;菜单点不动,只能改 iframe 的 location 且要重试;控件被 `<label>` 皮盖住 → 普通 click 报 "intercepts pointer events" 超时,要 `force` |
| Vue 类,`role=combobox`(Mercusys) | `dial` 只写 `[role='combobox']` **太松**,同页多个下拉时会驱动错控件 —— 一定要加标签锚定 |

## 卡住了:先分四类(成本差一个数量级)

- **崩溃**(抛异常退出)→ 看 `artifacts/crash_*.txt`(20 行),多数是环境问题;
- **登录**进不去 → 看探针打印的登录页诊断(密码框/文本框/按钮/可点元素 + 截图),
  **从那份诊断里挑一个** `--login-pass` / `--login-btn` 传进来,别猜;
- **定位**(清单里看得见控件,但选择器不唯一/回读不对)→ **便宜**,用两条收窄法
  + `--count`。**修法必须通用**:`_driver.py` 和 `probe_router.py` 里没有一行按
  品牌分支的代码,别加第一行;
- **形态**(页面上有、清单里压根没有这种控件)→ **贵**,见下面两节。

## 收尾:把这次学到的写回来

**验收通过之后**(真机逐档回读全对)做两件小事 —— 这是下一个人少走弯路的唯一
来源:

1. 这台特有的坑加进本文件「各 UI 家族特有的坑」;是个**新家族**就同时在
   `SKILL.md` 的家族表里加一行(写清抄哪个脚本、`--emit` 行不行);
2. 踩到通用的新坑,加进本文件「陷阱清单」。

约束(别把登记册写坏):

- **只加,不改写已有内容**;一次最多加一行 + 一条陷阱;
- **只写实测过的**。没跑通就不要加行,可以写"(进行中)"并注明卡在哪 —— 那比
  空着有用;
- 坑要写成**别人能照做的一句话**(「id 含点号只能用 `[id='...']`」),不是感想
  (「这个 UI 很奇怪」)。

**改不了 skill 文件**(只读 / 你是被粘贴进来的)?把要加的那一行**原样输出给
用户**让他自己粘 —— 别因为写不了就跳过,这是整套流程里唯一会累积的东西。

## 需要一个新动词时(改 `_driver.py` 的门槛)

`_driver.py` 是**动词库 + 一份默认配方**,不是框架 —— 改它不是禁区(2026-08-06
起;旧的"禁止编辑 driver"那条规则已经取消,它当年把成本放大成了 Buffalo 那
268 行)。但按顺序走这三步:

1. **先试参数化。** 多数"新动词"其实是老动词加一个参数(`force=True`、换等待
   策略、加一个 FACTS 键)。能用参数表达就不算新形态 —— `apply_settle_ms` 就是
   这么加的:一行,所有型号受益。
2. **确实是没见过的形态** → 写进**动词库**,并**配一个复现该形态的 mock**,
   既有 mock 全绿。mock 不是用来验新机型的(真机更强),它是"允许改 driver"的
   入场券:它回答真机回答不了的问题 —— *为适配这台改了下拉定位,另外五台还
   好使吗?* 真机要回答就得把六台重接一遍,几小时;mock 几秒。
3. **成功判定类的动词,永远不许新增。** `apply_and_verify()` 是唯一能产出
   `success=True` 的地方,`fail()` 是唯一的失败出口。

**绝不允许**在 `models/*.py` 里写私有辅助函数(`_enter_frame()` 那种)——
十台机之后就是六份几乎一样的私有导航函数,比一个特例脚本更难发现。

操作**顺序**特殊的机型就自己拼动词(动词清单:`python models/_driver.py
--verbs`)。Buffalo 的全文长这样:

```python
def run(facts=None, mode="dynamic", **kw):
    with session(facts or FACTS, mode, **kw) as s:
        if not s.login():
            return s.fail("登录失败:仍停在登录页,检查管理密码")
        if not s.goto_iframe():      # 进外壳页,再把 iframe 开到设置页
            return s.fail("设置页没在 iframe 里就绪")
        s.set_mode(force=True)       # 控件被皮盖住,force 点
        s.fill_params()
        return s.apply_and_verify(force=True)
```

### 改动分级(哪些能碰)

| 层级 | 规则 |
|---|---|
| `poll` / `locate` / `frames` / `settle` | **禁止改** —— 全机型地基。确实需要,先停下来向用户说明理由并等确认 |
| `login` / `navigate` / `ensure_enabled` / `set_mode` / `fill_params` | 可**新增**;改已有的必须在报告里写清影响哪些机型 |
| `Session` 的 `_verified` / `_aborted` 流转 | **禁止改** |
| `apply_and_verify` / `fail` | **禁止改** —— 成功判定唯一出口 |

**改之前**:`cp models/_driver.py models/_driver.py.bak`。改完不通过就还原,
**不要在坏掉的基础上继续改**(改坏了再往上叠,下一次失败就分不清是谁造成的)。
通过之后把 `.bak` 删掉 —— 仓库没有 `*.bak` 的忽略规则,留着会被提交进去。

**改完必须跑**(不是可选):

```
<PY> tests/smoke_test.py
```

这条是唯一的回归防线,通过 = 没弄坏另外五台。**不跑就不算改完。**

**改完必须报告**,格式:

> 改了 `_driver.py` 的 `<函数名>`,影响范围:`<哪些 kind / 哪些机型>`。
> smoke_test 全绿。**mock 全绿不等于真机没事**,建议在 `<具体机型>` 上各跑一次
> 确认。

## 探针吃不下的东西(遇到不是你没弄对,别反复试)

- `--probe-modes` **只支持原生 `<select>`** —— 自定义下拉要自己在页面上切一档
  再 `--dump` 一次,对比多出来哪些框;
- closed shadow DOM / canvas 自绘 / 验证码登录 —— 抄不到,如实报告;
- 保存前要确认弹窗的机型 —— 驱动点完保存不会去点弹窗,`--apply` 会报"已点但
  没生效",如实报告;
- 卡片条 / 分段选择器 —— 现有三种 `dial.kind` 都不是它,**别硬套**。

**任何一条命令崩了都不要卡住**:那几条命令彼此独立,而且你**永远不需要工具替你
生成脚本** —— 有 `--dump` 的清单 + 本文件的格式,自己写 dict 就行,这条路没有
环节会崩。只要清单存过盘,前面就没有白跑。
