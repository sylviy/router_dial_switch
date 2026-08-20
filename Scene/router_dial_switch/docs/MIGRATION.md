# 一次性迁移说明 —— 旧文件的每一项去了哪

重构前配置散在三处(`router.yaml` + `perf.yaml` + `perf_configs/<型号>.yaml`),
现在只有一个 **`config.yaml`**。这份说明只在"从旧版本升上来"时读一次,
以后不用管;日常填什么看 `config.example.yaml` 的中文注释。

**旧文件已经删掉了**,内容在下表里对号入座。台架上如果还留着旧的,
照表把值抄进新 `config.yaml` 就行,别再改旧的(没人读它们了)。

## 2026-08 那次重排:文件搬去了哪

仓库从"一个性能测试工具"拆成了**两个场景 + 一套共用工具**。根目录现在只有
`Tools/`(共用探针)、`Scene/`(各场景)、`Vendor/`(公共库)。
**代码里没有一处写死目录层级** —— 脚本靠"往上找到 `Vendor/`"和"`Scene/` 下面
那一层"定位,所以以后再搬也只是 `git mv`。

| 旧路径 | 新路径 |
|---|---|
| `start.bat`(仓库根) | `Scene/router_dial_switch/start.bat` |
| `config.yaml`(仓库根) | `Scene/router_dial_switch/config.yaml` |
| `models/<品牌>_<型号>.py` | `Scene/router_dial_switch/Models/<品牌>_<型号>/<品牌>_<型号>.py` |
| `common/contract.py` | `Vendor/common/contract.py`(两个场景共用) |
| `common/perf.py` | `Scene/router_dial_switch/common/perf.py`(场景专有) |
| `matrix/` `app/` `tests/` `docs/` `artifacts/` | `Scene/router_dial_switch/` 下同名目录 |
| `skill/SKILL.md` | `Scene/router_dial_switch/SKILL.md` |
| `skill/reference.md` | `Scene/router_dial_switch/reference.md` |
| `skill/tools/_probe.py` 等五个通用探针 | `Tools/` |
| `skill/tools/try_switch.py` | `Tools/act.py`(**泛化了**,见下) |
| `skill/tools/make_facts.py` / `check_model.py` | `Scene/router_dial_switch/tools/` |
| `tools/routerctrl_bridge.py` | `Scene/router_dial_switch/Models/TPLink_RouterCtrl/routerctrl_bridge.py` |
| `tools/make_offline_bundle.py` | `Vendor/make_offline_bundle.py` |
| `app/_py.bat` | `Vendor/py.bat`(两个场景共用) |
| `vendor/python/` | `Vendor/python/` |

命令行的变化:

| 旧 | 新 |
|---|---|
| `python models/Cudy_AX1500.py pppoe` | `python Models/Cudy_AX1500/Cudy_AX1500.py pppoe` |
| `python skill/tools/check_model.py --all` | `python tools/check_model.py --all` |
| `python skill/tools/try_switch.py --dial X --label Y` | `python ../../Tools/act.py --sel X --label Y` |
| `try_switch.py … --apply --apply-sel S` | `act.py … --apply-sel S`(**给了 `--apply-sel` 就保存**,`--apply` 这个开关没有了) |

`act.py` 比 `try_switch.py` 多的:`checkbox` / `toggle` / `text` / `button`
四种控件形态,`--expect-after`(等「做完的样子」出现,替代固定 sleep),
`--reload-verify`(刷新后再回读 —— 不刷新读到的是自己刚填进去的值)。

**所有命令都在场景目录下跑**(`cd Scene/router_dial_switch`)。探针靠"在哪个
目录跑"决定读哪份 `config.yaml`、产物往哪放;在场景外跑就全靠 `--ip` / `--pass`,
也能跑。

---

## router.yaml(管理密码和宽带账号)

| 旧 | 新 |
|---|---|
| `router_ip` | `router.ip` |
| `pass` | `router.pass` |
| `user` | `router.user`(多数机型不需要) |
| `params.pppoe_user` / `pppoe_pass` | `router.pppoe_user` / `router.pppoe_pass` |
| `params.l2tp.vpn_server` / `vpn_user` / `vpn_pass` | `router.l2tp.server` / `.user` / `.pass` |
| `params.pptp.vpn_server` / `vpn_user` / `vpn_pass` | `router.pptp.server` / `.user` / `.pass` |
| `headless` | `run.headless` |
| `no_apply` | **没有了**。要不要下发由命令决定:`Models/X/X.py <档>` 默认不下发,加 `--apply` 才下发;整轮必定下发。写在配置里的"下发开关"总有一天会有人忘了关。 |
| `brand` / `model`(profile 提示) | `run.model`(型号名,即 `Models/<这里>/<这里>.py`) |

**L2TP 和 PPTP 现在是两组独立的键**(旧版是共用 `vpn_*` 字段名再靠分块区分)。
台架给的是两套不同账号,分开写就不会互相覆盖。

## perf_configs/<型号>.yaml + perf.yaml(台架接线)

**不再按型号分文件。** 台架接线是按**拨号方式**走的 —— pppoe 拨通后的对端就是
那个隧道网段,换哪台路由器都一样 —— 所以一份 `bench` 段七台机共用。
换被测机只改两处:`router.ip` 和 `run.dial_modes`。

| 旧 | 新 |
|---|---|
| `model` | `run.model` |
| `backend` | `run.backend` |
| `dial_modes[].mode` | `run.dial_modes`(就是一串档名) |
| `dial_modes[].params` | **没有了** —— 账密统一从 `router.*` 按档取(见各型号脚本的 `NEEDS`) |
| `bands` / `directions` / `protocols` | `perf.bands` / `perf.directions` / `perf.protocols` |
| `wan_up.method` | `bench.wan_up_method` |
| `wan_up.host` | `bench.wan_up_host` |
| `wan_up.hosts.<档>` | `bench.wan_up_hosts.<档>` |
| `wan_up.timeout_s` | `perf.wan_up_timeout_sec` |
| `wan_up.settle_s` | `perf.settle_sec` |
| `chariot.duration_s` | `perf.duration_sec` |
| `chariot.endpoints.<频段>` | `bench.injectors.<频段>`(所有频段共用一台就填 `bench.injector_ip`) |
| `chariot.e2_ip.<档>` | `bench.endpoints.<档>` |
| `chariot.public_ip` / `internet_ip` | `bench.public_ip` / `bench.internet_ip` |
| `chariot.scripts` / `pairs` / `nofrag_bytes` / `stability_ratio` / `save_tests` | `bench.` 下同名 |
| `chariot.python`(旧键名 `python2`) | `bench.python2` |
| `reset_mode` | `run.reset_mode` |
| `report.dir` / `report.title` | `report.dir` / `report.title` |

**注意三处改了名字的**,它们最容易抄错:

* `chariot.endpoints` 是**按频段**的注入机(e1)→ 新名字 `bench.injectors`;
* `chariot.e2_ip` 是**按档**的对端(e2)→ 新名字 `bench.endpoints`;
  (旧名字里 endpoints/e2_ip 谁是谁一直容易记反,所以借这次换成"注入机/对端"。)
* 时序三项(`settle_s` / `duration_s` / `timeout_s`)从 `chariot` / `wan_up`
  段挪到了 `perf` 段 —— 因为它们**全仓库只能有一份**,型号脚本覆盖不了。

## 档名

TPLink 那台的复合档名改成和别的机型一样了:

| 旧 | 新 |
|---|---|
| `pptp_dynamic_internet` / `pptp_dynamic_public` | 都是 `pptp` |
| `l2tp_dynamic_internet` / `l2tp_dynamic_public` | 都是 `l2tp` |

后缀原本只决定 Chariot 打哪个远端,现在那件事由 `bench.endpoints.<档>` 说了算。
**桥接文件 `tools/routerctrl_bridge.py` 一个字没动**,翻译在
`Models/TPLink_RouterCtrl/TPLink_RouterCtrl.py` 的 `BRIDGE_MODE` 里。

> 影响报告:那台机的 CSV/HTML 里档名从 `pptp_dynamic_internet` 变成 `pptp`。
> 如果有历史 Excel 按老名字对行,那边要跟着改。

## 命令怎么变

| 旧 | 新 |
|---|---|
| `python start.py` / `start.bat` | 一样(菜单换了,见下) |
| `python start.py --setup` | **没有了** —— 用记事本改 `config.yaml`;`start.bat` 菜单 5 会告诉你还差什么、在第几行 |
| `python run_matrix.py --model X` | `python Models/X/X.py <档> --perf`,或 `start.bat` 菜单 3 |
| `python run_matrix.py --demo` | `start.bat` 菜单 3,把 `run.backend` 设成 `simulate` |
| `python models/X.py <档> --apply` | `python Models/X/X.py <档> --apply` |
| `python Models/X/X.py <档> --param k=v` | **没有了** —— 账密从 `config.yaml` 取 |
| `python tests/smoke_test.py` | `python tests/mock_test.py`,或 `start.bat` 菜单 4 |
| `python tools/check_model.py --all` | `python tools/check_model.py --all` |
| `python tools/probe_router.py --dump …` | `python Tools/probe_dump.py …`(拆成了探/列/验/试切四个工具) |
| `python adapt.py` | 照 `SKILL.md` 那张表跑 `Tools/` 里的工具 |

## 还留着的旧概念

* `tools/routerctrl_bridge.py` —— **py2.6 语法,不要用 py3 写法改它**;
* `Vendor/python/` —— 离线运行时,故意提交进仓库,别动;
* `matrix/` —— 读侧(测吞吐、出报告、等 WAN 拨通),这次重构没碰它的逻辑。
