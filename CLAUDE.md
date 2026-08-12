# CLAUDE.md — router_dial_switch

Playwright 通过 Web UI **切换路由器 WAN 拨号方式** + 逐档测吞吐出报告
(竞品路由器没有 HTTP API,只能这么跟 DUT 对比)。人读 `README.md`。

## 地图(第三列 = 改前该读的)

| 路径 | 是什么 | 改前读 |
|---|---|---|
| `models/<品牌>_<型号>.py` | **交付物**:一台机一个文件,**自足** —— FACTS + MODES + NEEDS + `switch(mode, cfg)`。彼此不 import,删掉任意一个其余照跑 | 文件头「这个文件怎么读」 |
| `common/contract.py` | 判定与结果格式,**全仓库唯一**。`success` 只能由 `verify()` 算出来 | 整个文件(146 行) |
| `common/perf.py` | 整轮时序(切→等 WAN→稳定→测→记)+ 读/校验 `config.yaml`。时序参数**只有一份**,型号脚本覆盖不了 | 文件头 |
| `config.yaml` | **唯一配置**。换被测机只改 `router.ip` 和 `run.dial_modes` | `config.example.yaml` 的中文注释 |
| `matrix/` | 读侧:测吞吐 / 出报告 / 等 WAN 拨通。这次重构没碰它的逻辑 | 别改,除非真要动测量 |
| `skill/tools/*.py` | 适配新机型的七个探针工具,退出码 0=过 1=不过 2=用法错 | `skill/SKILL.md` |
| `tools/routerctrl_bridge.py` | TPLink 那条路线的 py2.6 桥接 | **别用 py3 语法改它** |

**别整个读** `GOTCHAS.md`(39KB,给人看的历史)、`vendor/`(97MB)、
`artifacts/`、`*.png`。

## 跑 / 验

```bash
python tests/mock_test.py                 # 离线自检,26 条,必须 "0 failed"
python skill/tools/check_model.py --all    # 型号脚本离线体检(过了 ≠ 验收)
python models/Cudy_AX1500.py pppoe         # 单档,只看回读不下发
python models/Cudy_AX1500.py pppoe --apply # 真下发
python models/Cudy_AX1500.py pppoe --perf  # 整轮
python start.py                            # 向导(台架上双击 start.bat)
```

## 四条铁律

- **`success` 只有一个出口**:`contract.verify()` 精确相等 → `contract.result()`。
  永不放宽成子串("PPPoEv6" 含 "PPPoE")。别处不许拼带 `success` 的字典。
- **型号脚本之间的重复是刻意的。** 不要抽公共函数 —— 换来的是"改第六台绝不
  可能弄坏前五台"。`common/` 下**只准有那两个文件**。
- **默认不下发。** 加 `--apply` 才点保存;切错档当场断网。
- `vendor/python/` 是**故意提交**的离线运行时,**绝不进 Git LFS**;
  `matrix/chariot_perf.py` 要在台架 **Python 2.6** 下跑(别用 f-string/argparse);
  台架控制台是 GBK;仓库路径可能含 `[Tool]` → 用 `os.listdir`,别用 `glob`。

## 两个 skill

正文在 `skill/`(`.claude/skills/` 下只是指过去的壳):

- **适配新机型** → `skill/SKILL.md`(一张表 + 两处要停下来问人的关卡)
- **卡住了按节查** → `skill/reference.md`(**按节读,别整篇读**)

从旧版本升上来 → `MIGRATION.md`(旧的 `router.yaml` / `perf_configs/*.yaml`
哪一项去了新文件哪一节)。
