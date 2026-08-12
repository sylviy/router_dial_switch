# reference.md —— 卡住时**按节读**,不要整篇读

`SKILL.md` 的「不过往哪查」那一列指的就是这里的节名。每一节都是真机上踩出来的,
不是推测。新踩到的坑请追加到对应节末尾。

---

## § 登录

`probe_dump.py` 的 stderr 里那行 `[login]` 说明发生了什么。

**「没看到密码框」** —— 多半是好事(已在会话里)。但如果同时又找不到任何控件,
那可能是这台机用 **HTTP Basic**:登录是浏览器原生弹窗,DOM 里根本没有密码框,
任何选择器都救不了。首个响应是 401 就是铁证。这条路线现在的型号脚本没覆盖,
遇到了如实说,别硬试。

**「填了密码但还停在登录页」** —— 按可能性排:

1. 密码不对(`config.yaml` 的 `router.pass`);
2. **这台机同一时间只允许一个 Web 会话**(Tenda / Mercusys 实测):浏览器里
   开着的已登录页签会把工具踢回登录页 —— 先关掉;
3. 密码框选择器指错了 → `--pw-sel`;
4. 登录键要点而不是回车 → `--login-btn`(反过来也有:LuCI **不能**点按钮,
   它靠 `onsubmit` 的 JS 把密码加盐哈希后填进隐藏域再提交,填完按回车才对,
   所以 `FACTS.login` 里**不给** button)。

---

## § 认错控件

`list_modes.py` 说选项 < 2,或者列出来的根本不是拨号方式。

同一页上长得一样的下拉常常有好几个:**MTU、DNS、MAC 克隆、无线频宽**。Tenda
那台 WAN 页就有 4 个一模一样的 `<div class="v-select">`。分辨办法:

* 看 `probe_dump.py` 清单里那一行的 **`选项`** —— 拨号控件的选项一定是
  Dynamic/Static/PPPoE/PPTP/L2TP 这类词;
* 看它的 **`id` / `name` / `data-name`** —— `wanType` / `proto` / `WanMethod`
  这种名字基本可以确定;
* 实在分不出来,**问人**(关卡一),别自己赌。

**radio 形态的机型**(Buffalo)没有"下拉选项"可列:每一档是各自独立的
radio,`FACTS.modes` 的值就是各档的 radio 选择器,回读记的是模式名。
这种机型跳过 `list_modes.py`,直接对每个 radio 跑 `probe_count.py`。

---

## § 收窄选择器

`probe_count.py` 说命中 0 或 ≥2。

**命中 0**:

* 菜单没走到位 → 补 `--menu`;
* **LuCI 的 id 含点号**(`cbid.network.wan.proto`):CSS 里 `#cbid.network.wan.proto`
  会被解析成"id=cbid + 三个 class",命中 0。**一律用属性选择器**
  `[id='cbid.network.wan.proto']`;
* 控件是隐藏的原生 `<select>`(被美化插件盖住,`display:none`)—— 这种
  `probe_count` 会数到,但"其中可见"是 0,那是正常的,型号脚本用
  `visible=False` 找它。

**命中 ≥2**:脚本会点**第一个**,而第一个不一定是你要的 —— 这种错不会报错,
只会切错东西。收窄的办法,按优先级:

1. **用它所在的表单锚定**(LuCI 的 4 个 `cbi.apply` 就是这么解决的):
   `form:has([id='cbid.network.wan.proto']) button[name='cbi.apply']`
2. 用 `name` 而不是文字:Cudy AX1500 的保存键旁边埋着 **8 个隐藏的
   `Connect`/`Disconnect` 提交按钮**,按文字找必中诱饵,只能认
   `input[name='save_apply']`;
3. 用旁边的标签文字:`div.row:has-text("VPN Server") input:visible`。

---

## § 试切不过

`try_switch.py` 说回读和目标不一致。按可能性排:

1. **措辞抄错了。** 回 `list_modes.py` 看界面原话 —— 大小写、空格、括号
   都要一样。判定是精确相等,`"PPPoE "` 和 `"PPPoE"` 也算一样(首尾空白会
   规整),但 `"PPPoE(推荐)"` 和 `"PPPoE"` 不一样。
2. **控件被 CSS 盖住,点了没生效。** 报错里会有
   `... intercepts pointer events` → 加 `--force`。Buffalo 的 radio 和保存键
   都要 force。
3. **自定义下拉的值不显示在触发器上。** 触发器里常混着下拉小箭头之类的杂质
   文字 → 用 `--value-sel` 指到真正显示值的那个子元素(Tenda 那台是
   `[data-name='wanType']`)。
4. **选完之后整段 DOM 被重建**(LuCI 选完 proto 会走一次 XHR 重渲染):
   旧句柄失效,回读要**重新定位再读** —— 工具已经这么做了,但如果你自己写了
   变体,别把它省掉。
5. **点到了页面别处的同名文字。** Tenda 的 IPv6 页,LAN 区有一个同样叫
   "DHCPv6" 的 radio 标签。所以选项**只在 option 形态的容器里找**
   (`[role='option'], [class*='opt']`),找不到才退回全页同名文字。

---

## § 各 UI 家族(照哪台抄)

`make_facts.py --write` 的 `--like` 就是这一列。

| 家族 | 抄哪台 | 特征 / 坑 |
|---|---|---|
| 原生 `<select>` | `Cudy_AX1500` | 老式 frameset:登录在主文档、菜单在顶部帧、表单在子帧 → **全 frame 扫**。保存键旁 8 个隐藏 Connect 诱饵 |
| LuCI / CBI | `Cudy_AX3000` | id 含点号只能 `[id='…']`;4 个 `cbi.apply` 要用表单收窄;登录走回车;选完 proto 后 DOM 被 XHR 重建 |
| 自定义下拉 | `Tenda_AX3000` | Vue `v-select` / `role=combobox`;同页多个同款下拉;回读要 `dial.value` 单独指;IPv6 是独立页且被使能开关门控 |
| radio + iframe | `BUFFALO_WSR6000AX8` | 设置页**必须以 iframe 打开**且要等配置对象就绪;radio 和保存键都要 force;保存后要等 15 秒 |
| 不走 Web UI | `TPLink_RouterCtrl` | 走 py2.6 桥接子进程;没有"只看不切";回读和桥接判定**两道关**都要过 |

---

## § FACTS 每个键是什么

| 键 | 是什么 | 备注 |
|---|---|---|
| `brand` / `model` | 报告里显示的品牌型号 | 纯展示 |
| `url` | 管理页地址 | 现场以 `config.yaml` 的 `router.ip` 为准,这里是默认值 |
| `login.password` / `login.button` | 密码框 / 登录键 | 不给 button = 填完按回车 |
| `wan_path` | 走到设置页点哪几下 | `sel:` 前缀 = 用选择器,否则按菜单文字**精确**匹配 |
| `dial.kind` | `select` / `dropdown` / `radio` | 决定用哪套选中办法 |
| `dial.selector` | 拨号控件 | 必须命中 1 |
| `dial.value` | 回读值所在的子元素 | 只有自定义下拉常用 |
| `modes` | 模式名 → **界面原话** | radio 机型:模式名 → 该档的 radio 选择器 |
| `fields` | 概念 → 账密框选择器 | 概念名和 `NEEDS` 对应 |
| `fields_page` | 账密框在**别的页** | 写了就只发警告、不填(Buffalo 的 pppoe_reg.html) |
| `apply` | 保存键 | 必须命中 1 |
| `apply_settle_ms` | 点完保存等多久 | 异步提交的机型要给足(Buffalo 15 秒) |
| `enable_toggle` | 整块表单的使能开关 | **拨号控件已可见就绝不碰它**,否则会把已启用的页面点关 |
| `mode_overrides` | 某几档要换页/换保存键 | 被覆盖的键**整个替换** |
| `iframe_selector` / `iframe_target` / `iframe_ready_js` | 设置页要以 iframe 打开 | 就绪 = url + 配置对象 + 拨号控件三条同时成立 |

`MODES` 是这台机声明能切的档(整轮和菜单都以它为准);`NEEDS` 是每档要
`config.yaml` 里的哪几项 —— **按档写,别合并**:PPPoE 账密不能漏进 dynamic,
L2TP 和 PPTP 在台架上是两套不同账号。

---

## § 整轮跑不起来 / 报告里有 err

**开跑前就被拦下**:照报错里那句改 `config.yaml`,它会指出**第几行**。
常见三种:管理密码没填;这台机切不了 `run.dial_modes` 里的某几档(删掉它们);
`backend: chariot` 但那个 python 里没有 PyChariot(填 `bench.python2`,
用 `<那个python> -c "import PyChariot"` 确认)。

**某一档切换失败,整档被跳过**:先单跑 `python models/X.py <档>`(不加
`--apply`)看回读和截图 —— 这一步不改路由器。

**某些格是 `err`**:测量层的错原样进报告,看那格的 error 文字。
`nofrag_bytes` 缺哪一档,那几格就会 err(**故意的,不猜 MTU**:猜错的话
流量照跑、数字照出,其实分了片)。

**WAN 一直等不到拨通**:`bench.wan_up_hosts` 里那一档 ping 谁写对了吗?
直连档和隧道档不在同一网段。ping 不通不会判失败,只是白等满
`perf.wan_up_timeout_sec` 再开测。

**换了频段数字却没变**:`bench.injectors` 里那个频段的注入机 IP 填了吗?
而且那台机器要**事先连在对应频段上** —— 工具只负责按频段挑注入机,
换 SSID 是人做的,查不出来。

---

## § 探针吃不下的东西(遇到不是你没弄对)

* **Canvas / 图片里的控件**:DOM 里没有可点的东西,探针看不见;
* **需要二次确认弹窗**才真正生效的保存:目前只点一次保存键;
* **HTTP Basic 登录**(见 `§ 登录`);
* **同一页多步向导**(下一步→下一步→完成):现有型号脚本都是单页表单。

这四类遇到了如实报告,别反复试 —— 反复试只会烧台架时间。
