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
| `static_ip` / `static_mask` / `static_gateway` / `static_dns` | static(**目前 modes.py 里是空的**,见 CLAUDE.md「Known gaps」) |

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

## 参考实现

| 文件 | 看它学什么 |
|---|---|
| `models/Tenda_AX3000.py` | Vue SPA、role-less 下拉、表单行锚定、`dial.value`、IPv6 独立页 + `enable_toggle` + `mode_overrides`、嵌套 span 的保存键 |
| `models/Cudy_AX.py` | 老式 frameset、原生 `<select>`、PPTP/L2TP 字段拆分、一堆隐藏诱饵按钮里挑保存键、"这台机没有 IPv6"的定案过程 |
| `models/_template.py` | 空白模板 |

Tenda 和 Cudy 都已在物理设备上通过验收(含 `--apply` 真实下发),照它们抄。
