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
  个别老 UI 的**操作序列**本身是特例(Buffalo 要先进 `advanced.html` 再让
  iframe 加载 `wan.html`,否则保存提交旧值),这种型号脚本可以自己实现
  `run()`(签名与 `_driver.run` 一致),`matrix/run.py` 的 `runner_for()` 会
  自动改用它,整轮和 `start.py` 照跑。**是最后手段**:能加通用键就加通用键。
- `tools/probe_router.py` —— **只读取证探针**:登录后抄下整页(含所有子
  frame)的控件,并**用 Playwright 引擎实测每个候选选择器的命中数**,产出
  证据 JSON + 一份 FACTS 建议(可 `--emit` 直接落成型号脚本骨架)。
- `tools/check_model.py` —— 型号脚本的**离线体检**,不需要路由器。
- `.claude/skills/` —— **让别人(和别的 agent)能接手**:
  `adapt-router-model/` 是适配一台新型号的完整方法论(+ `reference.md`:
  FACTS 逐键说明和选择器手册),`run-perf-round/` 是跑整轮和排查失败。
  不猜 DOM,每一条事实都来自真机观察。

### 已适配的型号

| 脚本 | 支持的模式 | 真机状态 |
|---|---|---|
| `models/Tenda_AX3000.py` | dynamic / pppoe / static / dhcpv6 / pppoev6(v6 精确到 flavor,无笼统 "ipv6") | **台架验收通过**(2026-07-18,含实际下发) |
| `models/Cudy_AX1500.py`(老式 frameset 固件,与 AX3000 不是同一台) | dynamic / pppoe / static / l2tp / pptp | **台架验收通过**(2026-07-18,含 `--apply` 实际下发) |
| `models/Cudy_AX3000.py` | dynamic / pppoe / l2tp / pptp | LuCI/OpenWrt 固件。选择器已在真机上引擎实测命中数==1;脚本机制已用 `cudy_luci.html` 离线验证(4 个 cbi.apply 的 form 锚定 / 含点号的 CBI id / XHR 重建 DOM)。**真机逐模式回读 + `--apply` 验收待做** |
| `models/Cudy_BE6500.py` | dynamic / pppoe / l2tp / pptp | 同为 LuCI/OpenWrt,与 AX3000 同家族(dynamic 的措辞是 `DHCP`)。字段选择器都按 form 收窄 |
| `models/BUFFALO_WSR6000AX8.py` | dynamic / pppoe / **transix / v6plus / ocnvc / v6connect**(日本 IPoE) | **真机六档 `--apply` 均已验过**(2026-07-31)。这台**自带 `run()`**,不走 `_driver`:`wan.html` 必须以 `advanced.html` 内 iframe 打开,否则保存提交旧值 |
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
- **不猜没见过的 DOM** → 每台型号的事实(FACTS)都来自真机上的**逐条观察**
  (每个选择器都验证过命中数 == 1);适配方法论固化在 skill 里。

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
python start.py --setup        # Windows 上:双击 start.bat,选菜单 4
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
  `perf_configs/<型号>.yaml`(一台机一份,向导可代生成);**密码**仍走
  `router.yaml`。开跑前会把参数逐条核对,配错的当场拦住并告诉你改哪一行。
- **两个性能后端**:`simulate`(纯 Python 模拟,给演示/CI/看报告长啥样)和
  `chariot`(真台架,子进程调用 `matrix/chariot_perf.py`,保持在它原生的
  Python 2 / Chariot 环境里)。
- **输出**:自包含、亮暗自适应的 **HTML 报告** + 一份 **CSV**(写到 `artifacts/`),
  一眼看清每个 拨号方式×频段×方向×协议 的吞吐、是否稳定、以及那档切换是否成功
  —— 取代旧脚本写死路径的 Excel 模板。

### 适配一台新型号

**最简单:一条命令,按提示答题。**

```bash
python adapt.py        # Windows 上双击 adapt.bat
```

它会问你品牌/型号/地址/密码,然后依次:探测页面 → 生成
`models/<品牌>_<型号>.py` → 离线体检 → **逐个拨号方式真机验证**,每一步都用
人话讲它在做什么、看到了什么。**前三步不改路由器任何配置**,第 4 步默认也只
切换不保存;只有最后问你"要不要真正保存"并回答 y 之后才会下发。

找不到拨号控件时它会停下来问你"设置页在哪个菜单",而不是猜。

想手动分步跑(或写脚本)时,下面这四条就是它内部做的事:

```bash
python tools/probe_router.py --url http://192.168.1.1 --pass <管理密码> \
    --nav "Internet Settings" --brand <品牌> --model <型号> \
    --emit models/<品牌>_<型号>.py        # 只读探测 + 生成骨架
python tools/check_model.py <品牌>_<型号>  # 离线体检
python models/<品牌>_<型号>.py dynamic     # 真机逐模式看回读,不保存
python models/<品牌>_<型号>.py pppoe --apply   # 全对了再验收
```

完整方法论(含判断"这台机到底有没有 IPv6"的穷尽核查法、各种诱饵陷阱)在
`.claude/skills/adapt-router-model/SKILL.md`,FACTS 每个键的说明在同目录的
`reference.md`。

产出物就是那**一个文件**,其它文件一律不用动 —— `_driver.py` 已经包含全部点击
逻辑,`start.py` 会自动把新型号列进菜单,`run_matrix.py` 会自动遍历它声明的
全部模式,**没有任何注册表要改**。

**不要靠猜写 FACTS。** 这个仓库里所有"假成功"的教训(点了个同名的诱饵元素、
把卡片条的第一张当成当前值、`:text-is()` 匹配不到文字在内层 span 的按钮)都是
因为选择器没在真机上验证过 —— 详见 `CLAUDE.md` 的 Validated 一节。

## 如何验证(离线,无需真机)

```bash
python tests/smoke_test.py          # 无头,驱动内置模拟路由器页
python tests/smoke_test.py --show   # 观看它点完所有模式
```

它在 localhost 起模拟路由器页,用**真实的型号脚本 + 真实的驱动**跑完整条路:
登录 → 进 WAN 设置 → 定位控件 → 选中 → 填参数 → 回读 → 保存。看结尾的
**`0 failed`**。覆盖:

- **models/ 交付层**:用 `Tenda_AX3000.py` / `Cudy_AX1500.py` / `Cudy_AX3000.py` / `Mercusys_BE3600.py`
  里的**真实 FACTS** 驱动对应 mock —— 原生 `<select>`、无 role 的 Vue widget
  (含 "Connect" 保存键)、IPv6 使能开关门控页、`cudy*.htm` 的老式 frameset
  (登录在主文档、菜单和表单各在子 frame,还有隐藏的 Connect/Disconnect 诱饵),
  以及**"事实对不上的页面必须诚实失败"**这条守卫;
- **凭据层**:`router.yaml` 读写、按模式挑参数(PPPoE 账密不得漏进 dynamic);
- **run_matrix 编排层**:`--demo` 离线整轮(配置 → 主循环 → simulate 后端 →
  HTML+CSV 落盘),以及 `chariot_perf._judge` 判稳纯函数 == 旧脚本
  `result_judge` 语义的守卫;
- **start.py 交互向导**:管道喂按键走通 选型号 → 选操作 → 选模式 → 切换 整条流程。

## 项目结构

```
router_dial_switch/
  start.bat / start.py   **日常入口**:列型号按数字选,回车即整轮;
                         菜单 4 = 存 IP/密码/宽带账号到 router.yaml
  adapt.bat / adapt.py   **适配新机器的向导**:探测 -> 生成脚本 -> 体检 -> 验证
  run_matrix.py          整套性能矩阵:切模式 → 等WAN → 测吞吐 → 出报告
  perf_configs/          **每台机一份测试参数**:<型号>.yaml(注入机/对端 IP、
                         每档打谁、测多久)。选到哪台就自动用哪份;没有的话
                         向导会问你要不要生成。密码不在这里。
  perf.example.yaml      全局配置模板(老写法,作为没有按型号配时的回落)
  models/                **交付层:每台型号一个脚本**
    Tenda_AX3000.py      事实(FACTS)+ 入口;直接运行
    Mercusys_BE3600.py
    Cudy_AX1500.py      老式 frameset 固件
    Cudy_AX3000.py       LuCI/OpenWrt 固件(与上面不是同一台)
    Cudy_BE6500.py       同为 LuCI/OpenWrt
    BUFFALO_WSR6000AX8.py 日本 IPoE 六档;**自带 run()**(iframe 特例)
    _template.py         新型号照抄的注释模板
    _driver.py           所有型号共用的点击逻辑(零猜测,只吃显式事实)
    _browser.py          Playwright 启动(channel=chrome / 离线)
  matrix/                性能矩阵编排层
    run.py               主循环 + CLI(--list / --demo / --model;整轮必下发)
    config.py            按型号找参数文件(perf_configs/<型号>.yaml 优先)
    check_config.py      开跑前把参数核一遍:错的拦住,并摊开每档打谁
    perf_backends.py     simulate(离线模拟)/ chariot(真台架,子进程)后端
    chariot_perf.py      旧 Dial.py 的 Chariot 逻辑清理版(Py2/台架用,单次测量)
    wanup.py             切完模式后等 WAN 拨通(ping 判据,可按模式配目标)
    report.py            自包含 HTML + CSV 报告
  modes.py               每种拨号方式要哪些参数 + 按模式挑凭据
  settings.py            router.yaml 本机默认值(IP/密码/凭据;git 忽略)
  config.py              浏览器 / 超时 / 路径 等开关(处理 OS 差异)
  tests/                 离线冒烟:mock 路由器页 + 端到端断言
  tools/                 probe_router.py:只读取证探针(适配新型号用)
                         check_model.py:型号脚本离线体检
                         make_offline_bundle.py:重建 vendor/python
  vendor/python/         **随仓库发布的 Python 3.8 运行时**(台架零安装)
  .claude/skills/
    adapt-router-model/  适配新型号:取证 -> 填 FACTS -> 体检 -> 真机验收
    run-perf-round/      跑整轮性能矩阵 + 失败排查
  *.bat                  Windows 双击入口(_py.bat 决定用哪个解释器)
```

## 已知限制 / 后续

- WAN 拨通验证:`run_matrix.py` 已内置一个 ping 判据(参数文件的 `wan_up`),
  切完模式后 ping 通台架地址再开测;更强的"真·拨通"判据(调单机脚本)可从
  `matrix/wanup.py` 扩展,或用 `_driver.run(verify_hook=...)`。
- WLAN(2.4G/5G、多 SSID)切换:后续结合单机脚本;引擎已预留无线客户端钩子。
- 验证码登录、全 canvas 自绘 UI、重度混淆 SPA:需录制 profile 或人工——不强求全自动。
- IPv6 位置因厂商而异:Tenda 和 Mercusys 上它**不在**主"上网方式"列表里,而是
  独立的一页(More → IPv6 / Advanced → IPv6),而且整块 WAN 区要等使能开关打开
  才渲染。这类差异写在型号脚本的 `mode_overrides` 里(换 `wan_path`、加
  `enable_toggle`、换保存键),不需要改任何公共代码。
- v6 吞吐:目前 v6 那几档只验证"**切换**成功";要真测 v6 吞吐,注入机和对端
  得填 IPv6 地址、协议写成 `TCP6`/`UDP6`(代码已认这两个名字)。
