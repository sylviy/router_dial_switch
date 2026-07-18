# router_dial_switch（路由器拨号方式切换)

自动化**通过路由器 Web 界面切换 WAN 拨号方式**(动态IP / PPPoE / L2TP / PPTP /
IPv6)——用于把我们的 DUT 与那些无法用 HTTP API 驱动的竞品路由器做对比测试。

**交付形态(2026-07-16 起):每台型号一个脚本。**

```bash
python models/Tenda_AX3000.py pppoe          # 就这一条,切完看回读
```

- `models/<品牌>_<型号>.py` —— **交付物**。一个文件 = 这台机的全部"事实"
  (登录、菜单路径、控件选择器、各模式措辞、保存按钮),同事直接运行即可,
  不需要理解引擎。组内目标品牌:Cudy / Tenda / Buffalo / Huawei。
- `models/_driver.py` —— 所有型号共用的点击逻辑(约 500 行,修一处全体受益)。
- `engine/` + `cli.py` —— **适配期工具箱**:面对新型号先 `python cli.py diagnose`
  取证,再照 `.claude/skills/adapt-router-model` 的方法论产出新的型号脚本
  (任何 Claude 会话都能按这个 skill 干活)。启发式引擎不再追求"通吃所有品牌",
  它的职责是把适配一台新机的成本压到"跑一次诊断 + 抄几个选择器"。

当前范围(按方案约定):只确认拨号控件被**定位并成功改动**(回读值 == 目标)。
**不验证 WAN 是否真正拨通**——连通性/性能由已有的单机脚本负责。

> **已在真机 Mercusys BE3600(Wi-Fi 7)上实测通过,2026-07-11。** 它的
> "Internet Connection Type"(上网方式)控件是一个自定义 `<div role="combobox">`,
> 而非原生 `<select>`——所以引擎同时具备"原生 select 路径"和"自定义 combobox
> 路径(DOM 级点击选项)"。这次实测还暴露并已修复两个 bug:WAN 菜单启发式原本会
> 误点 "Network Map"(Mercusys 的首个导航项);以及当路径含 `[Tool]` 这类 glob
> 元字符时 profile 加载会失效。详见 `profiles/mercusys_be3600.yaml`。

---

## 为什么这样设计

| 分层 | 与品牌相关? | 由谁负责 |
|------|-------------|----------|
| 改拨号方式(写操作) | **是** —— 本工具 | Playwright DOM 自动化 |
| 验证连通性 / 吞吐(读操作) | 否 | 已有单机脚本(后续接入) |

- **逆向每个品牌的 HTTP 接口** → 全球海量品牌下每型号都逆向成本太高,仅作为
  *兜底*(录制模式会顺带把每个型号的 HTTP 请求抓下来)。
- **按像素点击** → 太脆弱。我们用 **DOM 语义**(`get_by_role` / `get_by_label`
  / `get_by_text`)点击 → 跨品牌、跨固件都稳。
- **不靠 AI 的通用性** → 关键词字典启发式覆盖常规 UI;录制模式让每个新品牌只需
  几分钟;profile 库随用随长。

现实边界:纯规则不可能覆盖世界上 100% 的路由器(验证码登录、全 canvas 自绘 UI、
重度混淆 SPA)。这些走录制 profile 或人工——见*已知限制*。

---

## 环境(离线 Windows 测试台)

- **Python 3.8+**,**隔离安装在本文件夹内**(Windows embeddable zip 或 venv),
  从而完全不碰公司默认的 3.7 自动化环境和单机脚本。
- **浏览器**:用 `channel="chrome"`(默认)驱动已装好的、版本锁定的 **Chrome 114**
  —— 无需额外下载,完全离线。
- **离线安装依赖包**:
  ```
  # 在联网机上
  pip download -r requirements.txt -d wheels
  # 把 ./wheels 拷到测试台,在隔离的 3.8 里:
  pip install --no-index --find-links=wheels -r requirements.txt
  ```
- **如果必须用 Playwright 自带的 Chromium(而非系统 Chrome)**:在联网机上
  `playwright install chromium`,拷贝浏览器缓存目录,运行时用 `--browsers-path`
  (PLAYWRIGHT_BROWSERS_PATH)指向它,并加 `--bundled-chromium`。

跨平台:Python 代码与操作系统无关——只有浏览器二进制分平台。可在 macOS 上开发/
验证(本仓库正是如此),同一份代码部署到 Windows。

---

## 使用方法

### 日常使用(已适配的型号)

第一次,把 IP / 管理密码 / 宽带账号交互式写进本机的 `router.yaml`
(该文件已被 `.gitignore` 忽略,不会进仓库):

```bash
python cli.py setup
```

之后切换一台**已适配**的机器只要一条命令(凭据按模式自动取用,PPPoE 账号
不会带进 dynamic 运行;默认只切换不点保存,加 `--apply` 才真正下发):

```bash
python models/Tenda_AX3000.py dynamic
python models/Tenda_AX3000.py pppoe --apply
python models/Mercusys_BE3600.py l2tp
```

整个测试矩阵(切模式 → 等 WAN → 跑性能)见 `examples/run_test_matrix.py`。

### 适配一台新型号

照 `.claude/skills/adapt-router-model/SKILL.md` 的流程:`python cli.py diagnose`
取证 → 复制 `models/_template.py` 填 FACTS → 每模式验证回读 → `--apply` 验收。
Claude 会话里说"适配新型号"即可触发该 skill。下面的 cli.py 用法都属于这个
适配阶段。

### 适配期:cli.py(启发式引擎)

启发式引擎也可以直接驱动一台没写过脚本的机器(碰运气,常见 UI 能直接成):

```bash
python cli.py pppoe
python cli.py dynamic
python cli.py l2tp
```

识别失败时会自动跑诊断;若诊断验证出了唯一选择器,终端会直接问一句
「写入哪一个?」——**回车即自动生成 profile 并记住品牌**,重跑同一条命令即可,
不需要手写 YAML。非交互脚本加 `--pin` 自动采用第 1 个候选。

> setup 向导默认 `no_apply: true`(只切换、不点保存,试跑更安全);确认无误后
> 用 `python cli.py pppoe --apply` 真正下发,或重跑 setup 关掉该默认。

### 完整命令(不想用 router.yaml 时)

切到 PPPoE(纯启发式,无需 profile):

```bash
python cli.py --router-ip 192.168.1.1 --pass admin123 \
    --mode pppoe --param pppoe_user=宽带账号 --param pppoe_pass=宽带密码
```

L2TP / PPTP:

```bash
python cli.py --router-ip 192.168.1.1 --pass admin123 --mode l2tp \
    --param vpn_server=1.2.3.4 --param vpn_user=u --param vpn_pass=p
```

动态IP / IPv6(无需参数):

```bash
python cli.py --router-ip 192.168.1.1 --pass admin123 --mode dynamic
```

输出为 JSON:`success`、`detected_via`(select/combobox/radio)、`read_back`、
`filled`、`applied`、`needs_recording`,并在 `artifacts/` 存截图。退出码
`0` = 成功,`2` = 未确认拨号控件。

常用参数:`--brand`/`--model`(挑选 profile)、`--no-apply`(只选不保存)、
`--headless`、`--chrome-path`、`--bundled-chromium`。

### 接入新的/难缠的品牌

> **完整自助流程见 [ONBOARDING.md](ONBOARDING.md)**:裸跑 → 看诊断对号入座 →
> 建 profile → 取 CSS 选择器 → 带 profile 迭代 → 提交。下面是其中的录制模式。

```bash
python cli.py record --brand acme --model r1        # 已 setup 时
python cli.py record --router-ip 192.168.1.1 --brand acme --model r1
```

会弹出一个 Chrome 窗口;你手动把拨号方式切一遍,然后关闭窗口。得到:
- `recordings/acme_r1.har` —— 全部 HTTP 请求(接口兜底资产),以及
- `profiles/acme_r1.yaml` —— profile **草稿**;只需补上启发式没识别到的选择器,
  每一项都是可选的。

想要更完整的选择器录制,也可以用 Playwright 自带录制器:
`python -m playwright codegen http://192.168.1.1`。

---

## 适配是如何做到的

- `engine/heuristics.py` —— 多语言同义词表(目前中/英)+ 语义定位器。
  **要加新说法或新语言 = 在这里加字符串,不改引擎。** 拨号控件有两种通用识别方式:
  (1) 原生 `<select>`——选项能映射到最多不同拨号方式的那个;或 (2) 自定义
  `<div role="combobox">`——按其 "connection type" 标签定位,再用 DOM 定位器点击其
  选项(Mercusys/TP-Link 等真机就是这种)。
- `profiles/*.yaml` —— 可选的每型号提示(WAN 菜单路径、选择器覆盖、精确选项标签),
  按 品牌/型号/固件 宽松匹配,一个文件覆盖一个固件家族。
- `dial_modes/*.yaml` —— 每种模式需要哪些参数。

## 如何验证(离线,无需真机)

```bash
python tests/smoke_test.py          # 无头,驱动内置模拟路由器页
python tests/smoke_test.py --show   # 观看它点完所有模式
```

它在 localhost 起模拟路由器页并跑真实引擎:登录 → 进 WAN 设置 → 识别控件 →
选中 → 填参数 → 回读 → 保存。当前共 **37 个用例**,覆盖:
- `index.html` 原生 `<select>` / `custom.html` 自定义 `<div role="combobox">`
  (复刻真机 Mercusys)/ `tenda.html` 无 role 的 Vue widget(含 "Connect" 保存键);
- `xiaomi.html` **故意做成启发式认不出**,用带 `selectors:` 的 profile 驱动,
  验证选择器覆盖已接入;`beautify.html` 美化隐藏的原生 select;
- `tenda_ipv6.html` IPv6 使能开关(enable_toggle)+ v6 flavor(mode_labels),
  以及"开关还关着时诊断必须能看见它"+ auto-pin 自动写 enable_toggle;
- `noctrl.html` / `cardstrip.html` 两个**假阳性守卫**(绝不允许零交互的 success);
- CLI 便利层:`router.yaml` 读写、按模式过滤凭据、auto-pin 生成 profile 且不覆盖已有文件;
- **models/ 交付层**:用 `Tenda_AX3000.py` / `Mercusys_BE3600.py` 里的真实 FACTS
  驱动对应 mock(含 IPv6 门控页、"Connect" 保存键、按模式填参、默认不点保存),
  以及"事实对不上的页面必须诚实失败"守卫。

## 项目结构

```
router_dial_switch/
  models/                **交付层:每台型号一个脚本**
    Tenda_AX3000.py      事实(FACTS)+ 入口;直接运行
    Mercusys_BE3600.py
    Cudy_AX.py
    _template.py         新型号照抄的注释模板
    _driver.py           所有型号共用的点击逻辑(零猜测,只吃显式事实)
  .claude/skills/
    adapt-router-model/  适配方法论 skill:diagnose 取证 -> 填 FACTS -> 验证
  cli.py                 适配期入口(diagnose / setup 向导 / 失败时 auto-pin)
  settings.py            router.yaml 本机默认值(IP/密码/凭据;git 忽略)
  config.py              浏览器 / 超时 / 路径 等开关(处理 OS 差异)
  engine/                适配期工具箱(启发式引擎)
    browser.py           Playwright 启动(channel=chrome / 离线)
    heuristics.py        多语言关键词字典 + 语义定位器
    adapter.py           登录 -> 进 WAN 设置 -> 设模式 -> 回读
    diagnose.py          一键取证:已验证选择器 / 控件形态 / 保存键
    profile.py           可选的每品牌提示加载器(宽松匹配)
    recorder.py          录制模式:抓 HAR + 生成 profile 草稿
  profiles/              适配期的每品牌 yaml 提示
  dial_modes/            每模式所需字段模板
  tests/                 模拟路由器页 + 离线冒烟测试(37 用例)
```

## 已知限制 / 后续

- 尚未做 WAN 拨通验证(本地无拨号服务器)—— 等有拨号台架后,加 `verify_hook.py`
  封装单机脚本即可。
- WLAN(2.4G/5G、多 SSID)切换:后续结合单机脚本;引擎已预留无线客户端钩子。
- 验证码登录、全 canvas 自绘 UI、重度混淆 SPA:需录制 profile 或人工——不强求全自动。
- IPv6 位置因厂商而异:Mercusys BE3600 上它**不在**主"上网方式"列表里,而是在
  Advanced → IPv6 独立分区。这类每厂商结构差异,通过在该品牌 profile 里指定
  `wan_path` 来处理。
