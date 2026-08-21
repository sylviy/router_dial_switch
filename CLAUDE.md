# CLAUDE.md — router_dial_switch

用 Playwright 通过 **Web UI** 操作路由器/设备(竞品没有 HTTP API,只能这么跟
DUT 对比)。现在是**两个场景 + 一套共用工具**:

- `Scene/router_dial_switch/` —— 切 WAN 拨号方式 + 逐档测吞吐出报告。人读它的
  `docs/README.md`。
- `Scene/web_action/` —— 单纯的 UI 重复操作(例:切 VPN Server 协议),
  **零性能代码**。

## 地图(第三列 = 改前该读的)

| 路径 | 是什么 | 改前读 |
|---|---|---|
| `Tools/*.py` | **通用探针**,两个场景共用,零 perf 代码。`_probe.py` 是底座,`act.py` 做动作+回读 | `Tools/probing.md` |
| `Tools/probing.md` | 给 agent 的技术细则:探测循环 / 找不到怎么办 / 控件形态表 / 产出契约 | 整个文件 |
| `Vendor/common/contract.py` | 判定与结果格式,**全仓库唯一**。`success` 只能由 `verify()` 算出来 | 整个文件(146 行) |
| `Vendor/common/discover.py` | 按**文件路径**找/加载型号脚本(编排侧专用;型号脚本自己不 import 它) | 文件头 |
| `Vendor/python/` | 故意提交的离线 Windows 运行时(97MB) | 别动,**别整个读** |
| `Scene/<场景>/SKILL.md` | **只有一张对照表**:适配新的时候该拷哪一台/哪个任务 | 整个文件(很短) |
| `Scene/router_dial_switch/Models/<型号>/SKILL.md` | 那台机的**全部**:填好的任务表 + 流程表 + 规矩 + 它的实际命令。**一台一份、各自自足** | 整个文件 |
| `Scene/router_dial_switch/Models/<型号>/<型号>.py` | **交付物**:一台机一个文件,**自足** —— FACTS + MODES + NEEDS + `switch(mode, cfg)`。彼此不 import,删掉任意一个其余照跑 | 文件头「这个文件怎么读」 |
| `Scene/router_dial_switch/common/perf.py` | 整轮时序(切→等 WAN→稳定→测→记)+ 读/校验 `config.yaml`。时序参数**只有一份**,型号脚本覆盖不了 | 文件头 |
| `Scene/router_dial_switch/config.yaml` | 这个场景的**唯一配置**。换被测机只改 `router.ip` 和 `run.dial_modes` | `docs/config.example.yaml` 的中文注释 |
| `Scene/router_dial_switch/matrix/` | 读侧:测吞吐 / 出报告 / 等 WAN 拨通 | 别改,除非真要动测量 |
| `Scene/router_dial_switch/tools/` | 这个场景专属的两个工具:`make_facts.py` / `check_model.py` | `SKILL.md` |
| `Models/TPLink_RouterCtrl/routerctrl_bridge.py` | TPLink 那条路线的 py2.6 桥接 | **别用 py3 语法改它** |

**别整个读** `Scene/router_dial_switch/docs/GOTCHAS.md`(39KB,给人看的历史)、
`Vendor/python/`、`artifacts/`、`*.png`。

## 目录为什么这么摆(动它之前先读这段)

根目录只有三样:`Tools/`(共用探针)、`Scene/`(各测试场景)、`Vendor/`(公共库)。
脚本**不数目录层级**:

- `ROOT` = 往上找到含 `Vendor/` 的那一层;
- `SCENE` = 往上找到含 `Models/` 的那一层(探针在 `Tools/` 里,它用的判据是
  "`Scene/` 下面那一层",因为不是每个场景都有 `Models/`);
- `sys.path` 同时加 `Vendor/` 和 `SCENE`,**`common` 是命名空间包** ——
  `from common import contract, perf` 一行同时拿到 `Vendor/common/contract.py`
  和 `<场景>/common/perf.py`。**两个 `common/` 都不许有 `__init__.py`**,
  有了就不再拼接,每个型号脚本当场断(`check_model.py` 在 import 前挡了一道)。

所以搬目录是纯 `git mv`,不用改 import。

## 跑 / 验

```bash
cd Scene/router_dial_switch
python tests/mock_test.py                       # 离线自检,26 条,必须 "0 failed"
python tools/check_model.py --all               # 型号脚本离线体检(过了 ≠ 验收)
python Models/Cudy_AX1500/Cudy_AX1500.py pppoe          # 单档,只看回读不下发
python Models/Cudy_AX1500/Cudy_AX1500.py pppoe --apply  # 真下发
python Models/Cudy_AX1500/Cudy_AX1500.py pppoe --perf   # 整轮
python app/start.py                             # 向导(台架上双击 start.bat)

cd ../web_action
python tests/mock_test.py                       # 11 条,证明 act.py 各控件形态没坏
```

## 五条铁律

- **`success` 只有一个出口**:`contract.verify()` 精确相等 → `contract.result()`。
  永不放宽成子串("PPPoEv6" 含 "PPPoE")。别处不许拼带 `success` 的字典。
- **型号脚本之间的重复是刻意的。** 不要抽公共函数 —— 换来的是"改第六台绝不
  可能弄坏前五台"。`Vendor/common/` 下只准有 `contract.py` + `discover.py`;
  `perf.py` 归场景。
- **`_pause` / `_find` / `_find_text` 三个函数定死。** 在 `Tools/_probe.py`,
  全仓库唯一一份。探针可以整个复制到 `Models/<型号>/tools/` 自由编辑
  (加控件形态、改输出都行),但这三个原样保留 —— 它们是"工具说命中 1"能预测
  "脚本也命中 1"的唯一依据。`check_model.py` 逐字节比对,不一样报 **error**。
- **适配时可以直接下发,不用等人点头。** 台架断网、WAN 口不接出口,切错档
  不会把人关在门外。`--apply` / `--commit` / `--apply-sel` 该给就给。
  (`app/start.py` 里那个"输入 yes"是给**台架上的人**的,别去掉。)
- `Vendor/python/` 是**故意提交**的离线运行时,**绝不进 Git LFS**;
  `matrix/chariot_perf.py` 要在台架 **Python 2.6** 下跑(别用 f-string/argparse);
  台架控制台是 GBK;仓库路径可能含 `[Tool]` → 用 `os.listdir`,别用 `glob`。

## SKILL 怎么组织(和型号脚本同一个取舍)

`.claude/skills/` 下只是指过去的壳。正文**跟着交付物走,一份一台机 / 一个任务**:

- **适配新机型(拨号+性能)**:先看 `Scene/router_dial_switch/SKILL.md`(只有一张
  "按 UI 形态挑哪一台"的对照表),再读 `Models/<那台>/SKILL.md` —— 流程、规矩、
  按需询问、连那台机的实际命令都在里面。**适配 = 把那个目录整个拷成新型号,
  只改第一部分**(`tools/make_facts.py --write` 干的就是这件事)。
- **做一个 UI 动作单元** → `Scene/web_action/Devices/<…>/<任务>/SKILL.md`;
  `Devices/` 还空着的时候,从模板 `Scene/web_action/SKILL.md` 拷。
- **卡住了按节查** → `Scene/router_dial_switch/reference.md`(**按节读,别整篇读**)

**为什么不抽公共 SKILL**:和型号脚本之间的重复是同一个取舍 —— 拷一份改一份,
换来的是"改第八台绝不可能弄坏前七台",而且拷过去的那份**自足**,不用跳到上一层
读另一半。全场景唯一写在场景层的规矩是三个查找函数定死那一条。

每份 SKILL 都是**任务表驱动**:把流程和控件填进第一部分那张表,agent 照表推进,
只在"再探测也解决不了"的三种情况下才停下来问人。

从旧版本升上来 → `Scene/router_dial_switch/docs/MIGRATION.md`。
