# router_dial_switch(路由器拨号切换 + WAN 性能矩阵)

在**离线的 Windows 测试台**上,用浏览器驱动路由器的 Web UI **切换 WAN 拨号
方式**,逐档等 WAN 拨通、测吞吐、出 HTML/CSV 报告。

竞品路由器没有 HTTP API,只能这么跟自家 DUT 放在同一套口径下对比 ——
自家样机走内部库 `RouterCtrl`(见 `Models/TPLink_RouterCtrl/`),
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
python Models/Cudy_AX1500/Cudy_AX1500.py pppoe          # 只切换看回读,不下发
python Models/Cudy_AX1500/Cudy_AX1500.py pppoe --apply  # 真下发
python Models/Cudy_AX1500/Cudy_AX1500.py pppoe --perf   # 整轮
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

* **不能联网**:到现场没法 `pip install`。仓库自带 `Vendor/python/`
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
python tools/check_model.py --all # 型号脚本离线体检
```

自检拿仓库自带的假路由器页面(`tests/mock_router/`)把型号脚本从头到尾跑
一遍,覆盖四种 UI 原型 + 桥接路线。**上台架之前先跑它**:不过是代码问题,
不是接线问题。

## 项目结构

仓库根只有三样:`Tools/`(所有场景共用的探针)、`Scene/`(各测试场景)、
`Vendor/`(公共库 + 离线 Python)。**这个场景的东西全在 `Scene/router_dial_switch/`
里,整个目录复制走就能跑。**

```
<仓库根>/
  CLAUDE.md              给 AI 助手看的地图(Claude Code 只认根目录这个位置)
  Tools/                 通用探针,两个场景共用,零性能代码
    _probe.py              底座:开浏览器 / 登录 / 走菜单 / 找元素
    env_check.py  probe_dump.py  probe_count.py  list_modes.py
    act.py                 做一个动作 + 回读 + 刷新后再回读
    probing.md             给 agent 的技术细则
  Vendor/
    py.bat                 挑解释器(Vendor\python 还是 .venv)
    common/contract.py     判定与结果格式(全仓库唯一)
    common/discover.py     按文件路径找/加载型号脚本
    python/                离线运行时(别动)
  Scene/
    web_action/            另一个场景:单纯的 UI 重复操作
    router_dial_switch/    ← 就是本文档说的这个
      start.bat              入口 —— 双击它
      config.yaml            唯一要填的文件 —— 用记事本改
      reference.md           卡住了按现象查(按节读)
      app/                   程序入口和环境脚本
        start.py               向导本体
        setup.bat              没有 Vendor\python 时用它建 .venv
        smoke.bat              双击跑离线自检
        requirements.txt       重建 Vendor/python 时用
      docs/                  README.md WINDOWS.md MIGRATION.md GOTCHAS.md
                             config.example.yaml
      Models/<品牌>_<型号>/  交付物:一台机一个目录
        <品牌>_<型号>.py       脚本本体,**一个文件自足**
        SKILL.md               这台机的适配指南(任务表 + 规矩 + 工具介绍)
        tools/                 可选:按这台机改过的探针
      common/perf.py         整轮时序 + 读/校验 config.yaml
      matrix/                读侧:测吞吐 / 出报告 / 等 WAN 拨通
      tools/                 本场景专属:make_facts.py / check_model.py
      tests/                 离线自检 + 假路由器页面 + 假桥接
      artifacts/             跑动产物:reports/ shots/ probes/
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

**产出只有一个目录:`Models/<品牌>_<型号>/`,里面一个自足的脚本。** 拷进
`Models/` 就完事 —— 没有注册表要改,`start.bat` 的菜单自动认出它。已实测:
把这一个目录拷进一份干净的仓库,命令行、体检、菜单三样立刻都能用。

(唯一的例外:如果这台机有别人没有的档名 —— 比如 BUFFALO 的 `transix` ——
那么**测吞吐**时要在 `config.yaml` 的 `bench.endpoints` / `bench.wan_up_hosts`
里给那几档补上对端和 ping 目标。那是接线,不是代码;只切档不需要。)

**适配只有一步:从下表挑界面长得最像的那一台,把它整个目录拷成新型号,
照拷来的那份 `SKILL.md` 改第一部分。**

| 这台新机长什么样 | 拷这一台 |
|---|---|
| 原生下拉,老式 frameset / 普通单文档 | `Cudy_AX1500` |
| LuCI(OpenWrt) | `Cudy_AX3000` |
| LuCI,而且同一页有好几个长得一样的控件 | `Cudy_BE6500` |
| 自绘的下拉,另外 IPv6 那几档在单独一页 | `Tenda_AX3000` |
| 自绘的下拉,账密框只能靠旁边的标签文字认 | `Mercusys_BE3600` |
| 一组单选按钮,设置页套在框架里打开 | `BUFFALO_WSR6000AX8` |
| 不走浏览器(内部库 / 命令行) | `TPLink_RouterCtrl` |

拷来的那份 `SKILL.md` 是**填好的、自足的**:任务表(用界面上的话写的,不是
选择器)、七条规矩、每个工具是干什么的、照表推进的顺序,全在里面。
它跑的是 `Tools/` 里的探针:

```
env_check → probe_dump → list_modes → probe_count → act.py(只选中)
          → act.py(下发 + 刷新后回读)→ make_facts → check_model → 逐档实跑
```

每一步都有明确的通过条件(退出码 0),前面几步**一档都不改路由器**。
`make_facts.py --write` 会照最像的那台已交付脚本生成新目录。
卡住了按现象查 `reference.md`,**按节读,别整篇读**。

### 让 AI 助手来做:把下面这段整段发给它

助手要能**从它运行的那台机器访问到路由器**(同一局域网)。整段复制,把
尖括号里的三样换成实际值:

```
适配一台新路由器型号:<品牌> <型号>,管理页地址 <IP>。
管理密码我已经填在 Scene/router_dial_switch/config.yaml 的 router.pass 里,
你直接用,别问我要。

先看 .claude/skills/adapt-router-model/SKILL.md 那张对照表,按界面长相挑一台
最像的已交付机型,把 Models/<那台>/ 整个拷成 Models/<品牌>_<型号>/ 并改名
(tools/make_facts.py --write 也能替你做这一步)。然后 cd 到
Scene/router_dial_switch 下,照**拷来的那份 SKILL.md** 做 —— 任务表、规矩、
工具介绍、推进顺序都在里面,技术细则看 Tools/probing.md:
- 每一步都用 Tools/ 里的现成工具,不要自己另写探测脚本;覆盖不到的控件形态
  就加进 Tools/act.py,别复制一份工具出来;
- 每一步把工具的 stdout 原样给我看,退出码不是 0 就先按那一列去
  reference.md 查对应的节,别跳过去继续;
- 台架是断网的、WAN 口不接出口,所以**下发不用问我**,--apply / --apply-sel
  该给就给;但每一档都要用 --reload-verify 刷新后回读,自己确认不是假成功;
- 只有这三种情况停下来问我:同名控件好几个且都可见、真机和任务表对不上、
  一个动作可能改到别的设置。

产出只要一个目录 Models/<品牌>_<型号>/。里面的 SKILL.md 第一部分要逐项换成
这台机的(拷来时那一段还是原型机的,有 TODO 标着),**用界面上的话写** ——
按钮上写什么字、点完出现什么;选择器写进 FACTS,不要抄进 SKILL.md。
界面原文没看清的标"待真机确认",别猜。
不要改 Vendor/、不要改别的型号脚本、不要改 config.yaml 里我填好的值。
最后跑 python tools/check_model.py <品牌>_<型号> 把结果给我。
```

两个常见的坑:

* **"回读通过"本身不算数。** 不刷新就回读,读到的是它自己刚填进去的值 ——
  等于自己给自己打分。真机上出过回读通过、实际提交的是旧值。所以每一档都要
  `--reload-verify`;这一步它自己做,不用你盯。
* **上下文断了不要紧。** 让它重新读那台机的 `SKILL.md`,从"上一步跑到哪个工具"
  接着做;探测那几步都是只读的,重跑一遍不会有副作用。

## 已知限制

* **HTTP Basic 登录**的老机型(登录是浏览器原生弹窗,DOM 里没有密码框)
  现有型号脚本没覆盖;
* **多步向导式**的设置页(下一步→下一步→完成)没覆盖,现有都是单页表单;
* `static` 档各家的 IP/掩码/网关差异太大,还没建模,整轮里请避开;
* IPv6 只有 Tenda 那台建了模(`dhcpv6` / `pppoev6`),Cudy AX1500 的固件
  把 IPv6 整个关掉了(见该脚本文件头的核查记录)。

`GOTCHAS.md` 是历史记录:每条结论**当初是怎么得出来的**(哪天、哪台机、
什么现象)。出争议时翻它,日常用不到。
