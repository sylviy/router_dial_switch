# router_dial_switch(路由器拨号切换 + WAN 性能矩阵)

在**离线的 Windows 测试台**上,用浏览器驱动路由器的 Web UI **切换 WAN 拨号
方式**,逐档等 WAN 拨通、测吞吐、出 HTML/CSV 报告。

竞品路由器没有 HTTP API,只能这么跟自家 DUT 放在同一套口径下对比 ——
自家样机走内部库 `RouterCtrl`(见 `models/TPLink_RouterCtrl.py`),
两条路线的判定标准和报告格式完全一样。

## 五分钟上手

台架上**双击 `start.bat`**,选型号、选操作,没有别的要记:

```
支持的型号(括号里 = 该型号声明的拨号方式,按轮次顺序):
  1. BUFFALO_WSR6000AX8  (dynamic/pppoe/transix/v6plus/ocnvc/v6connect)
  2. Cudy_AX1500         (dynamic/static/pppoe/pptp/l2tp)
  …
要做什么:
  1. 只切一档,只看回读不下发   ← 最安全,上台架第一步该做这个
  2. 只切一档,并真正下发       ← 会改路由器,要输 yes 确认
  3. 整轮性能测试               ← 逐档切换 → 等 WAN → 测吞吐 → 出报告
  4. 离线自检                   ← 拿假路由器页面跑一遍,不碰真机
  5. 看看 config.yaml 还差什么   ← 缺什么、在第几行
```

菜单按**危险程度**排。第一次上台架请按 1 → 1 → …(逐档看回读)→ 2 → 3。

命令行等价物:

```bash
python models/Cudy_AX1500.py pppoe            # 只切换看回读,不下发
python models/Cudy_AX1500.py pppoe --apply    # 真下发
python models/Cudy_AX1500.py pppoe --perf     # 整轮
```

## 配置只有一个文件

`config.yaml`,现场用记事本改。**换被测机只改两处**:`router.ip`,和
`run.dial_modes`(这轮测哪几档)。

每一项该填什么见 `config.example.yaml` 的中文注释(和本文件同目录);缺什么**不用猜** ——
菜单 5 会把缺的项连**行号**一起列出来,而且分两段:先是"切档要用的",
再是"整轮测吞吐才要的"(`bench` 段只有 `backend: chariot` 的整轮才用得到)。

台架接线是按**拨号方式**走的 —— pppoe 拨通后的对端就是那个隧道网段,
换哪台路由器都一样 —— 所以 `bench` 段配一次七台机共用。

> 从旧版本升上来:旧的 `router.yaml` / `perf.yaml` / `perf_configs/*.yaml`
> 已经并进 `config.yaml`,哪一项去了哪一节见 **`MIGRATION.md`**。

## 环境(离线 Windows 测试台)

* **不能联网**:到现场没法 `pip install`。仓库自带 `vendor/python/`
  (Python 3.8 + playwright + PyYAML,解压即用,**故意提交进仓库**)。
  `start.bat` 会自己挑解释器,不要直接敲 `python` —— 台架 PATH 上那个是
  不能动的 Python 2。
* **台架必须装 Chrome**(vendor 里没有浏览器内核)。装在非默认位置就填
  `config.yaml` 的 `bench.browser_path`。
* **Chariot 那套只在 Python 2.6.5 里**:测吞吐的子进程用
  `config.yaml` 的 `bench.python2` 指过去。确认办法:
  `<那个python> -c "import PyChariot"`。

## 怎么验证(不用真机)

```bash
python tests/mock_test.py              # 26 条离线自检,必须 "0 failed"
python skill/tools/check_model.py --all # 型号脚本离线体检
```

自检拿仓库自带的假路由器页面(`tests/mock_router/`)把型号脚本从头到尾跑
一遍,覆盖四种 UI 原型 + 桥接路线。**上台架之前先跑它**:不过是代码问题,
不是接线问题。

## 项目结构

```
start.bat                唯一入口 —— 双击它
config.yaml              唯一要填的文件 —— 用记事本改
CLAUDE.md                给 AI 助手看的地图(Claude Code 只认根目录这个位置)

app/                     程序入口和环境脚本
  start.py                 向导本体
  _py.bat                  挑解释器(vendor\python 还是 .venv)
  setup.bat                没有 vendor\ 时用它建 .venv
  smoke.bat                双击跑离线自检
  requirements.txt         重建 vendor/ 时用
docs/                    文档
  README.md  WINDOWS.md  MIGRATION.md  GOTCHAS.md  config.example.yaml
models/<品牌>_<型号>.py    交付物:一台机一个文件,自足
common/contract.py       判定与结果格式(全仓库唯一)
common/perf.py           整轮时序 + 读/校验 config.yaml
matrix/                  读侧:测吞吐 / 出报告 / 等 WAN 拨通
skill/                   适配新机型:SKILL.md + reference.md + tools/(七个工具)
tools/routerctrl_bridge.py   TPLink 那条路线的 py2.6 桥接
tests/                   离线自检 + 假路由器页面 + 假桥接
artifacts/               跑动产物:reports/ 报告、shots/ 截图、probes/ 探针产物
vendor/python/           离线运行时(别动)
```

## 为什么这样设计

**一台机 = 一个文件,自足。** 七个型号脚本之间**不 import 彼此**,共用的只有
两样东西:怎么算成功(`contract.py`)、整轮的节拍(`perf.py`)。文件之间允许
大段重复,**那是刻意的** —— 换来的是"改第六台绝不可能弄坏前五台",而那种坏法
是静默的(切了、看起来成功、保存的是旧值)。删掉任意一个型号文件,其余六个
照跑。

**成功只有一个出口。** 切错拨号方式这类错误**失败得静默**:页面照渲染、截图
照正常、报告照出数字,只是那一格测的不是这个模式。所以判定只认一件事 ——
控件自己显示的当前值**精确等于**目标措辞。永不放宽成子串:真机上
`"PPPoEv6"` 里就含着 `"PPPoE"`。

**默认不下发。** 切错档当场断网,台架上没人能远程救回来。

## 适配一台新型号

**产出只有一个文件:`models/<品牌>_<型号>.py`。** 拷进 `models/` 就完事 ——
没有注册表要改,`start.bat` 的菜单自动认出它。已实测:把这一个文件拷进一份
干净的仓库,命令行、体检、菜单三样立刻都能用。

(唯一的例外:如果这台机有别人没有的档名 —— 比如 BUFFALO 的 `transix` ——
那么**测吞吐**时要在 `config.yaml` 的 `bench.endpoints` / `bench.wan_up_hosts`
里给那几档补上对端和 ping 目标。那是接线,不是代码;只切档不需要。)

流程照 `skill/SKILL.md` 那张表跑 `skill/tools/` 里的七个工具:

```
env_check → probe_dump → list_modes → probe_count → ⛔问人 → try_switch → make_facts → check_model → ⛔问人
```

每一步都有明确的通过条件(退出码 0),前四步**一档都不改路由器**。
`make_facts.py --write` 会照最像的那台已交付脚本生成新文件。
卡住了按现象查 `skill/reference.md`,**按节读,别整篇读**。

### 让 AI 助手来做:把下面这段整段发给它

助手要能**从它运行的那台机器访问到路由器**(同一局域网)。整段复制,把
尖括号里的三样换成实际值:

```
适配一台新路由器型号:<品牌> <型号>,管理页地址 <IP>。
管理密码我已经填在 config.yaml 的 router.pass 里,你直接用,别问我要。

照 skill/SKILL.md 那张流程表做,从第 0 步开始,一步一步来:
- 每一步都用 skill/tools/ 里的现成工具,**不要自己另写探测脚本**;
- 每一步把工具的 stdout 原样给我看,退出码不是 0 就先按那一列去
  skill/reference.md 查对应的节,别跳过去继续;
- **两处 ⛔ 关卡必须停下来等我回答**:选择器认定、下发确认。没有我的
  明确答复不许往下走,更不许 --apply。

产出只要一个文件 models/<品牌>_<型号>.py。
不要改 common/、不要改别的型号脚本、不要改 config.yaml 里我填好的值。
最后跑 python skill/tools/check_model.py <品牌>_<型号> 把结果给我。
```

两个常见的坑:

* **别催它"一次做完"。** 那两处关卡是流程里唯一需要人的地方 —— 命中 1 只
  说明页面上只有一个控件,不说明它是对的;而切错档会当场断网。催它跳过关卡,
  等于把这两件事交给概率。
* **上下文断了不要紧。** 让它重新读 `skill/SKILL.md`,从"上一步跑到哪个工具"
  接着做;前四步都是只读的,重跑一遍不会有副作用。

## 已知限制

* **HTTP Basic 登录**的老机型(登录是浏览器原生弹窗,DOM 里没有密码框)
  现有型号脚本没覆盖;
* **多步向导式**的设置页(下一步→下一步→完成)没覆盖,现有都是单页表单;
* `static` 档各家的 IP/掩码/网关差异太大,还没建模,整轮里请避开;
* IPv6 只有 Tenda 那台建了模(`dhcpv6` / `pppoev6`),Cudy AX1500 的固件
  把 IPv6 整个关掉了(见该脚本文件头的核查记录)。

`GOTCHAS.md` 是历史记录:每条结论**当初是怎么得出来的**(哪天、哪台机、
什么现象)。出争议时翻它,日常用不到。
