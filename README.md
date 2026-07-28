# router_dial_switch（路由器拨号切换 + WAN 性能矩阵)

自动化**通过路由器 Web 界面切换 WAN 拨号方式**(动态IP / PPPoE / L2TP / PPTP /
IPv6)——用于把我们的 DUT 与那些无法用 HTTP API 驱动的竞品路由器做对比测试;
组里的 **Chariot 吞吐脚本**也已合并进来,一条命令跑完
「切模式 → 等 WAN → 测吞吐 → 出报告」的整轮。

**最简单的用法:一条命令,按数字选。**

```bash
python start.py        # Windows 上双击 start.bat
```

它自己列出支持的型号,按数字选一台,回车 —— **默认就是工具的本体:遍历这台
型号支持的全部拨号方式,每档真切换 → 等 WAN → 测吞吐 → 出报告**(台架语义,
不问"要不要保存")。也可以选"只切一个模式"做单步调试。密码和宽带账号先取
`router.yaml` 里存过的,没有才问你,问完顺手存起来 —— 下次全程回车。

**交付形态(2026-07-16 起):每台型号一个脚本。** 脚本化/参数化的入口也都在:

```bash
python models/Tenda_AX3000.py pppoe          # 只切拨号:一条命令,切完看回读
python run_matrix.py --demo                  # 整轮性能矩阵:先离线看个样例报告
```

- `models/<品牌>_<型号>.py` —— **交付物**。一个文件 = 这台机的全部"事实"
  (登录、菜单路径、控件选择器、各模式措辞、保存按钮),同事直接运行即可,
  不需要理解引擎。组内目标品牌:Cudy / Tenda / Buffalo / Huawei。
- `models/_driver.py` —— 所有型号共用的点击逻辑(约 500 行,修一处全体受益)。
- `engine/` + `cli.py` —— **适配期工具箱**:面对新型号先 `python cli.py diagnose`
  取证,再照 `.claude/skills/adapt-router-model` 的方法论产出新的型号脚本
  (任何 Claude 会话都能按这个 skill 干活)。启发式引擎不再追求"通吃所有品牌",
  它的职责是把适配一台新机的成本压到"跑一次诊断 + 抄几个选择器"。

型号脚本本身只确认拨号控件被**定位并成功改动**(回读值 == 目标);
「WAN 是否拨通、吞吐多少」由 `run_matrix.py` 的整轮流程负责(见下文
"跑整套 WAN 性能矩阵" —— 组里原来的 Chariot 单机脚本已合并进来)。

### 已适配的型号

| 脚本 | 支持的模式 | 真机状态 |
|---|---|---|
| `models/Tenda_AX3000.py` | dynamic / pppoe / static / dhcpv6 / pppoev6(v6 精确到 flavor,无笼统 "ipv6") | **台架验收通过**(2026-07-18,含实际下发) |
| `models/Cudy_AX.py` | dynamic / pppoe / static / l2tp / pptp | **台架验收通过**(2026-07-18,含 `--apply` 实际下发) |
| `models/Mercusys_BE3600.py` | dynamic / pppoe / static / l2tp / pptp | 2026-07-11 真机跑通(当时走启发式);脚本形态的字段选择器仍标 `[待真机复核]` |

各机型的具体怪癖(Tenda 的嵌套 span 按钮、Cudy 的 frameset + 隐藏诱饵按钮、
Cudy 固件关掉了 IPv6 的证据链)都记在 `CLAUDE.md` 的 **Validated** 一节。

---

## 为什么这样设计

| 分层 | 与品牌相关? | 由谁负责 |
|------|-------------|----------|
| 改拨号方式(写操作) | **是** —— models/ 型号脚本 | Playwright DOM 自动化 |
| 验证连通性 / 吞吐(读操作) | 否 | `matrix/`(组里 Chariot 脚本的移植),由 `run_matrix.py` 编排 |

- **逆向每个品牌的 HTTP 接口** → 每型号都逆向成本太高(组里旧性能脚本用
  RouterCtrl HTTP API,只能驱动自家 DUT —— 这正是本工具要补的缺口)。
- **按像素点击** → 太脆弱。我们用 **DOM 语义**(`get_by_role` / `get_by_label`
  / `get_by_text`)点击 → 跨品牌、跨固件都稳。
- **不猜没见过的 DOM** → 每台型号的事实(FACTS)都来自 diagnose 取证或真机
  直接观察;适配方法论固化在 skill 里,任何 Claude 会话都能照做。

现实边界:纯规则不可能覆盖世界上 100% 的路由器(验证码登录、全 canvas 自绘 UI、
重度混淆 SPA)。这些走人工——见*已知限制*。

---

## 环境(离线 Windows 测试台)

- **Python 3.8:仓库自带,不用装。** `vendor/python/` 是一份解压即用的 Windows
  embeddable 3.8,依赖已经装在里面(约 97 MB,已提交)。台架上**零安装**:
  下载 → 拷贝 → 双击 `start.bat`。公司那套锁死的 Python(2.x / 3.7)完全没被
  碰过 —— 而且整轮里跑 Chariot 吞吐的那半边本来就要 Python 2,两者各跑各的。
  依赖或版本要升级时,在联网机上 `python3 tools/make_offline_bundle.py` 重建后
  提交;细节见 `vendor/README.md`,操作步骤见 `WINDOWS.md`。
- **浏览器**:用 `channel="chrome"`(默认)驱动已装好的、版本锁定的 **Chrome 114**
  —— 仓库不带浏览器内核,所以**台架必须先装好 Chrome**(离线机要带完整安装包)。
- **如果必须用 Playwright 自带的 Chromium(而非系统 Chrome)**:在联网机上
  `playwright install chromium`,拷贝浏览器缓存目录,运行时用 `--browsers-path`
  (PLAYWRIGHT_BROWSERS_PATH)指向它,并加 `--bundled-chromium`。

跨平台:Python 代码与操作系统无关——只有浏览器二进制分平台。可在 macOS 上开发/
验证(本仓库正是如此),同一份代码部署到 Windows。

---

## 使用方法

### 最简:交互式向导(推荐给所有人)

```bash
python start.py        # Windows 双击 start.bat
```

不用记任何参数、不用先建任何文件:列出型号按数字选,回车即整轮
(遍历全部拨号方式 + 吞吐 + 报告)。单步调试选操作 2;想"只切换不保存"
地演练,用 `python models/<型号>.py <mode>`(不带 `--apply`)。

### 日常使用(已适配的型号,命令行版)

第一次,把 IP / 管理密码 / 宽带账号交互式写进本机的 `router.yaml`
(该文件已被 `.gitignore` 忽略,不会进仓库;`start.py` 里存过就不用再跑):

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

### 跑整套 WAN 性能矩阵(切模式 → 等 WAN → 测吞吐 → 出报告)

日常切模式只是**一步**;完整测试是一个循环:每档拨号方式都切过去、等 WAN 拨通、
跑一遍吞吐,再换下一档。这条主循环现在是一条命令 `run_matrix.py`——它把本工具
(Web 界面切拨号,竞品路由器也能驱动)和已有的 Chariot 性能脚本(旧 `Dial.py`
的逻辑,已参数化)拼在一起:

```bash
python run_matrix.py --list                # 列出已适配型号
python run_matrix.py --demo                # 离线演示:不碰路由器,出样例报告
python run_matrix.py --model Tenda_AX3000  # 整轮:遍历该型号的全部拨号方式
```

**台架语义:整轮 = 自动遍历型号脚本里声明的全部拨号方式**(Tenda 就是
dynamic → pppoe → static → dhcpv6 → pppoev6),每档切换**必定真正下发**再测
吞吐 —— 不下发,吞吐测的就不是这档模式,所以整轮没有 `--apply` 开关。
"只切换不保存"的安全演练留在单模式入口(`models/<型号>.py`)。

- **测什么、怎么测**(拨号方式矩阵、频段/方向/协议、台架拓扑、WAN 拨通判据)写在
  `perf.yaml`(复制 `perf.example.yaml` 改;git 忽略);**密码**仍走 `router.yaml`。
- **两个性能后端**:`simulate`(纯 Python 模拟,给演示/CI/看报告长啥样)和
  `chariot`(真台架,子进程调用 `matrix/chariot_perf.py`,保持在它原生的
  Python 2 / Chariot 环境里)。
- **输出**:自包含、亮暗自适应的 **HTML 报告** + 一份 **CSV**(写到 `artifacts/`),
  一眼看清每个 拨号方式×频段×方向×协议 的吞吐、是否稳定、以及那档切换是否成功
  —— 取代旧脚本写死路径的 Excel 模板。

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

---

## 适配是如何做到的

面对一台**还没有脚本**的路由器,流程是:`python cli.py diagnose` 取证 →
照证据填 `models/_template.py` → 每个模式验证回读 → `--apply` 验收。
完整方法论(含"怎么判定这台机真的没有某功能"这类坑)见
[.claude/skills/adapt-router-model/SKILL.md](.claude/skills/adapt-router-model/SKILL.md)
—— 在 Claude 会话里说"适配新型号"即可触发。

支撑这套流程的部件:

- `engine/diagnose.py` —— **取证主力**:全 frame 清点、三条检测策略各自是否触发、
  每个候选控件给出**已验证命中数**的选择器、每个可点按钮是否被认作保存键。
- `engine/heuristics.py` —— 多语言同义词表(中/英)+ 语义定位器,让常见 UI
  不用写脚本也能碰对。**要加新说法或新语言 = 在这里加字符串,不改引擎。**
- `profiles/*.yaml` —— 适配期的临时提示(auto-pin 会自动生成),不是交付物;
  交付物永远是 `models/` 里的型号脚本。
- `dial_modes/*.yaml` —— 每种模式需要哪些参数。

## 如何验证(离线,无需真机)

```bash
python tests/smoke_test.py          # 无头,驱动内置模拟路由器页
python tests/smoke_test.py --show   # 观看它点完所有模式
```

它在 localhost 起模拟路由器页并跑真实引擎:登录 → 进 WAN 设置 → 识别控件 →
选中 → 填参数 → 回读 → 保存。当前共 **40 个用例**,覆盖:
- `index.html` 原生 `<select>` / `custom.html` 自定义 `<div role="combobox">`
  (复刻真机 Mercusys)/ `tenda.html` 无 role 的 Vue widget(含 "Connect" 保存键);
- `xiaomi.html` **故意做成启发式认不出**,用带 `selectors:` 的 profile 驱动,
  验证选择器覆盖已接入;`beautify.html` 美化隐藏的原生 select;
- `tenda_ipv6.html` IPv6 使能开关(enable_toggle)+ v6 flavor(mode_labels),
  以及"开关还关着时诊断必须能看见它"+ auto-pin 自动写 enable_toggle;
- `noctrl.html` / `cardstrip.html` 两个**假阳性守卫**(绝不允许零交互的 success);
- `cudy*.htm` **frameset 老式 UI**(登录在主文档、菜单和表单各在子 frame),
  复刻真机 Cudy,含隐藏的 Connect/Disconnect 诱饵按钮;
- CLI 便利层:`router.yaml` 读写、按模式过滤凭据、auto-pin 生成 profile 且不覆盖已有文件;
- **models/ 交付层**:用 `Tenda_AX3000.py` / `Cudy_AX.py` / `Mercusys_BE3600.py`
  里的**真实 FACTS** 驱动对应 mock(含 IPv6 门控页、"Connect" 保存键、跨 frame
  查找、按模式填参、默认不点保存),以及"事实对不上的页面必须诚实失败"守卫;
- **run_matrix 编排层**:`--demo` 离线整轮(配置 → 主循环 → simulate 后端 →
  HTML+CSV 落盘),以及 `chariot_perf._judge` 判稳纯函数 == 旧脚本
  `result_judge` 语义的守卫;
- **start.py 交互向导**:管道喂按键走通 选型号→选操作→选模式→切换 整条流程
  (默认操作必须不点保存)。

## 项目结构

```
router_dial_switch/
  start.py               **交互式向导(最简入口)**:列型号按数字选,回车即默认
  run_matrix.py          整套性能矩阵入口:切模式 → 等WAN → 测吞吐 → 出报告
  perf.example.yaml      矩阵配置模板(复制成 perf.yaml;测什么/怎么测/台架拓扑)
  matrix/                性能矩阵编排层
    run.py               主循环 + CLI(--list / --demo / --model;整轮必下发)
    config.py            读 perf.yaml
    perf_backends.py     simulate(离线模拟)/ chariot(真台架,子进程)后端
    chariot_perf.py      旧 Dial.py 的 Chariot 逻辑清理版(Py2/台架用,单次测量)
    wanup.py             切完模式后等 WAN 拨通(ping 判据 / 固定等待)
    report.py            自包含 HTML + CSV 报告
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
    profile.py           适配期提示加载器(宽松匹配;auto-pin 写入)
  profiles/              适配期的临时 yaml 提示(非交付物)
  dial_modes/            每模式所需字段模板
  tools/                 控制台粘贴用的查找脚本(手上只有浏览器时的兜底)
  tests/                 模拟路由器页 + 离线冒烟测试(40 用例)
  setup.bat start.bat    Windows:一次安装 + 双击即用的交互向导(见 WINDOWS.md)
  dial.bat matrix.bat    Windows:命令行版 切模式 / 整套性能矩阵
  run.bat smoke.bat      Windows:适配期 cli.py + 离线自检
```

## 已知限制 / 后续

- WAN 拨通验证:`run_matrix.py` 已内置一个 ping 判据(`perf.yaml` 的 `wan_up`),
  切完模式后 ping 通台架地址再开测;更强的"真·拨通"判据(调单机脚本)可从
  `matrix/wanup.py` 扩展,或用 `_driver.run(verify_hook=...)`。
- WLAN(2.4G/5G、多 SSID)切换:后续结合单机脚本;引擎已预留无线客户端钩子。
- 验证码登录、全 canvas 自绘 UI、重度混淆 SPA:需录制 profile 或人工——不强求全自动。
- IPv6 位置因厂商而异:Mercusys BE3600 上它**不在**主"上网方式"列表里,而是在
  Advanced → IPv6 独立分区。这类每厂商结构差异,通过在该品牌 profile 里指定
  `wan_path` 来处理。
