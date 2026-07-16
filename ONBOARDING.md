# 接入一台全新路由器（自助流程）

> **2026-07-16 起,首选路径变了:** 适配的最终产出是一个**型号脚本**
> `models/<品牌>_<型号>.py`(照 `.claude/skills/adapt-router-model/SKILL.md`
> 的流程:diagnose 取证 → 复制 `models/_template.py` 填 FACTS → 验证回读)。
> 本文档描述的是底层的启发式引擎 + profile 玩法 —— 它仍然是**取证和兜底**的
> 工具(diagnose 的产物就是 FACTS 的信息来源),但日常交付请写型号脚本,
> 不再以 profile 为最终形态。

拿到一台没见过的竞品路由器,想让本工具支持它切拨号方式,照这份走即可。
**核心理念**:引擎默认用启发式(多语言关键词)自动认控件;认不出时,你只需在一个
`profiles/<品牌>_<型号>.yaml` 里补几行"提示",告诉它"这个控件用这个 CSS / 这条菜单
路径 / 这个精确措辞"。**每一项都是可选的,只补启发式没搞定的那一项;单个型号全程不改
代码。**

---

## 第 0 步:一次性配置(可选但推荐)

```bash
python cli.py setup      # 交互式问 IP/密码/宽带账号,写入 router.yaml(git 已忽略)
```

之后所有命令都缩成一个词:`python cli.py dynamic` / `python cli.py pppoe`。
下文长命令均可用短形式替代。

## 第 1 步:先裸跑一次(不带 profile)

```bash
python cli.py dynamic          # 已 setup;向导默认 no_apply=true,不会点保存
# 或长形式:
python cli.py --router-ip 192.168.x.1 --pass <管理密码> --mode dynamic --no-apply
```

- `--no-apply` = 只定位+选择+填参,**不点保存**(接入调试期一直加着,别断网)。
- 看返回 JSON 的 `success`:
  - `true` → 恭喜,这台机**开箱即用**,不用做任何事。
  - `false` → 看 `detected_via` 和 `message`,它会告诉你**卡在哪一步**。

---

## 第 2 步:看诊断 → 对号入座,知道要补什么

**最快的路:失败的那次运行会自动生成一份证据产物**(`artifacts/diagnose_*.json`),
终端也会打印一段紧凑结论。它一次就告诉你:三条检测策略各自**是否触发、为何没触发**、
每个候选控件**已验证命中数**的选择器(含能 pin 的 `:has-text()` 写法)、以及每个可点
按钮**是否被认作保存键**(所以像 Tenda "Connect" 这种保存键不用截图也能发现)。
想主动生成同一份产物:`python cli.py --diagnose --router-ip 192.168.x.1 --pass <密码>`。

产物 `verdict.next_actions` 通常直接写明「该 pin 什么 / 该加哪个同义词」。若想手动对号入座,
`message` 尾部那段 `(all frames: N <select>, M role=combobox, ...)` 也能对照下表:

| message / 现象 | 卡在哪一步 | 在 profile 里补这一项 |
|---|---|---|
| URL 里有 `#/login`,或 `login failed ...` | **登录**没成功 | 先核对 `--pass`;仍不行 → `selectors.login_pass` / `selectors.login_button`;并确认没有别的浏览器占着会话(有些机型单会话) |
| URL 停在**首页/状态页**,`0 <select>, 0 role=combobox` | **导航**没走到 WAN 页 | `wan_path: [...]`(按顺序要点的菜单文字) |
| URL 已到 WAN 页,但 `0 <select>, 0 role=combobox` | 控件是**自造 widget**,认不出 | `selectors.dial_mode_select`(看产物 `pin.recommended`) |
| 产物 `verdict.dial_control: card-strip (unsupported)` | 控件是**卡片条/分段选择器**,现有策略都吃不下 | 暂无低成本修法(单个 pin 无效)→ 记为功能需求;详见 CLAUDE.md「Known gaps」 |
| 功能页(常见于 IPv6)**空空如也**,产物 `toggles` 里有 state=False 的开关 | 整个区块要等**使能开关**打开才渲染 | `selectors.enable_toggle`(失败运行会自动列出开关候选、一键写入;手动排查用 `tools/find_enable_toggle.js` 贴进控制台) |
| `dropdown found but has no 'pppoe' option` | 认出控件了,但**模式措辞**没匹配上 | `mode_labels:`(把规范名映射到界面原文) |
| `success:true` 但 `filled: []`(本该填账密) | **参数字段**认不出 | `selectors.pppoe_user` / `pppoe_pass` / `vpn_server` 等 |
| 选对了但 `applied:false`;产物 `save_button: NO-MATCH` | **保存按钮**认不出(如 Tenda 的 "Connect") | 把该按钮措辞加进 `heuristics.BUTTON_SAVE_SYNONYMS`,或 `selectors.save_button` |

> 小米 4A 的真实例子:裸跑后 URL 停在 `web/home#router`(路由状态首页)、`saw 0,0` →
> 属于第 2 行"导航没走到"。因为小米顶栏是"常用设置/高级设置"这种泛化词、不在 WAN 同义
> 词表里,而"上网设置"是二级菜单。对策就是 `wan_path: ["常用设置", "上网设置"]`。

---

## 第 3 步:建 profile 文件

**先看自动的路:失败的那次运行,若诊断验证出了唯一选择器,终端会直接列出候选并
问一句「写入哪一个?」——回车即生成 `profiles/auto_<IP>.yaml` 并把 brand 记入
router.yaml,重跑同一条命令就能用上。** 页面上什么拨号控件都没有、但有**关着的
开关**时(IPv6 页常见),同一流程会改为提供 `enable_toggle` 候选(ipv6/启用类
label 排最前)。非交互环境(脚本/中继)加 `--pin` 采用第 1 个候选。多数
「控件认不出」的机型到这里就结束了,无需手写任何 YAML。
自动路走不通时(要补的是 wan_path / mode_labels / 保存按钮等),再手动建,两种方式任选:

- **手写**:在 `profiles/` 下新建 `<品牌>_<型号>.yaml`,照 `profiles/_example.yaml`(带
  完整中文注释的模板)填。
- **录制生成草稿**:
  ```bash
  python cli.py --record --router-ip 192.168.x.1 --brand xiaomi --model 4a
  ```
  弹出浏览器,你手动把拨号方式点一遍再关窗口,会生成:
  - `recordings/xiaomi_4a.har`(全部 HTTP 请求,留作"逆向接口"兜底资产)
  - `profiles/xiaomi_4a.yaml`(**草稿**,再按第 2 步补齐)

profile 至少要有 `brand`(+`model`),这样第 5 步用 `--brand/--model` 才能匹配到它。

---

## 第 4 步:取 `dial_mode_select` 选择器(照做即可)

> **最省事:直接跑 `--diagnose`。** 产物 `dial_candidates[].pin.recommended` 会给出
> **已验证命中数==1** 的选择器,照抄进 profile 即可,不用自己数、不用自己试。下面这套
> 控制台脚本流程仅在你**跑不了 CLI**(如手头只有浏览器、机器上没 Python/进不了内网)时用。
>
> **重要:选择器不止 `#id`/`.class`。** 引擎用 Playwright 的 `frame.locator()`,支持
> `:has-text()`。当一个控件**没有唯一纯 CSS 选择器**时(如 Tenda 的 `<div class="v-select">`
> 重复 5 次),用 **label 锚定**就唯一了:
> ```yaml
> dial_mode_select: 'div.v-form-item:has-text("Internet Connection Type") div.v-select'
> ```
> 这也是当年 Tenda「以为没法 pin」的正解 —— 纯 CSS 不行,Playwright 选择器一直行。

### 先搞懂一句话:选择器是什么

"选择器(selector)"就是**一小段文字,用来在网页上精确指向某一个元素**。三种常用写法:

- `#wantypeselect` —— 指向 **id** 是 `wantypeselect` 的元素(最稳,首选)
- `[name='wantypeselect']` —— 按 **name** 指向(次选)
- `.beautify` —— 按 **class** 指向(class 可能重复或是随机哈希,最后才用)

你要做的,就是找出"上网方式"那个控件的选择器,填进 profile。**不用手写、不用右键**——
用下面这个脚本自动吐出来。

### 三步拿到它(用查找器脚本)

1. **浏览器里点到「上网设置 / WAN」那一页**(就是有"上网方式"下拉的那页)。
2. **打开控制台**:Chrome/Edge 按 `F12` → Console;Safari:菜单「开发」→「显示 Web 检查器」→「控制台」
   (若没有「开发」菜单:Safari 设置 → 高级 → 勾"在菜单栏中显示‘开发’菜单")。
3. **把 `tools/find_dial_selector.js` 整个文件内容复制,粘贴进控制台,回车。**

它会**直接打印出该填的那一行**,例如小米打印的是:
```
✓ 找到原生下拉(可能是隐藏的美化控件):
   选项: PPPoE  /  DHCP  /  静态IP
→ 把这一行填进 profile 的 selectors: 下面:
     dial_mode_select: "#wantypeselect"
```
把绿色那行照抄进 `profiles/<品牌>_<型号>.yaml` 即可(见下方"填进 profile"示例)。

> 找不到 `tools/find_dial_selector.js`?它是本仓库里的一个文件,用编辑器打开、全选复制就行。
> 脚本里已内置逻辑:优先找"选项含 PPPoE/DHCP/静态"的原生 `<select>`(哪怕它被隐藏),
> 找不到再列出可见的自定义控件候选。

### 填进 profile

```yaml
brand: "xiaomi"
model: "ac1200"
selectors:
  dial_mode_select: "#wantypeselect"   # ← 脚本打印的那行,照抄
```

### 验证选择器对不对(可选,10 秒)

在同一个控制台里粘贴运行(把引号里换成你的选择器):
```js
document.querySelectorAll("#wantypeselect").length   // 结果应为 1
```
返回 `1` = 正好指向一个元素,对了;`0` = 没指到(选择器写错/不在这页);`>1` = 指到多个,
换更精确的写法(加 id 或 `[name=...]`)。

### 为什么"美化/隐藏"控件也能行

很多路由器(尤其国产)用 jQuery 美化插件(beautify / select2 / chosen):**底层有个真正的
原生 `<select>`,被 `display:none` 藏起来,外面套层好看的皮**。所以工具裸跑会报 `saw 0
<select>`,让你以为没有。但查找器会**连隐藏的 select 一起找出来**;pin 上它的 `#id` 后,
引擎用 `force` 驱动隐藏 select 并触发 change,美化层和路由器 JS 会自动同步。这就是小米那台
一行 `dial_mode_select: "#wantypeselect"` 就通的原因。

---

## 第 5 步:带 profile 重跑,迭代到通

```bash
python cli.py --router-ip 192.168.x.1 --pass <密码> \
    --brand xiaomi --model 4a --mode dynamic --no-apply
```

**每跑一次,诊断就指向下一个还没补的环节** —— 补一项、再跑、再看,直到:
- `success: true`、`detected_via` 有值(select/combobox)、`read_back` 显示已变成目标模式。

确认 `read_back` 对了之后,再**去掉 `--no-apply`** 让它真正点保存(注意:如果是承载真实
上网的机器,切错模式会断网——务必先在测试台或用 `--no-apply` 验证)。

各模式要带的参数:
- PPPoE:`--param pppoe_user=<账号> --param pppoe_pass=<密码>`
- L2TP / PPTP:`--param vpn_server=<服务器> --param vpn_user=<账号> --param vpn_pass=<密码>`
- 动态/IPv6:无需参数

---

## 第 6 步:提交 profile,永久接入

把跑通的 `profiles/<品牌>_<型号>.yaml` 留在 `profiles/` 里。以后**任何人**对这台型号跑,
`--brand/--model` 一匹配就自动带上,开箱即用。配置库随用随长。

---

## 一个判断:改字典 vs 写 profile

- 遇到的是**通用新说法**(又一种"上网方式"/"PPPoE"的叫法)→ 加进 `engine/heuristics.py`
  的同义词表 → **所有未来品牌都受益**。
- 遇到的是**某型号独有的结构**(具体 CSS、二级菜单路径、怪异措辞)→ 写进**该型号的
  profile** → 不污染通用逻辑。

这就是"低成本适配越来越多品牌"的机制:常见的沉淀进字典,独有的隔离进 profile。

---

## 安全提示:诊断产物可能含敏感数据

`--diagnose` / 失败自动生成的 `artifacts/diagnose_*.json`,以及 `--record` 的
`recordings/*.har`,可能包含**会话 token、表单里的账号/密码值**等。贴进工单、群里或
提交仓库前先过一眼、必要时脱敏。(反过来,这些逐 frame 的 HTML/JSON 也是现成的素材:
可以直接改成 `tests/mock_router/<品牌>.html`,让这台新机型变成一条永久回归用例。)
