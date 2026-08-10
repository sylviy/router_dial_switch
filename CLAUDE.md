# CLAUDE.md — router_dial_switch

Playwright 通过 Web UI **切换路由器 WAN 拨号方式** + 逐档测吞吐出报告
(竞品路由器没有 HTTP API,只能这么跟 DUT 对比)。人读 `README.md`。

## 地图(第三列 = 改前该读的,`G` = `GOTCHAS.md`)

| 路径 | 是什么 | 改前读 |
|---|---|---|
| `models/<品牌>_<型号>.py` | **交付物**:这台机的 FACTS + 几行 `run()` | G→Validated |
| `models/_driver.py` | 动词库 + 默认配方;**成功只由 `apply_and_verify()` 判定** | G→Gotchas |
| `matrix/` `run_matrix.py` | 读侧:整轮编排(切档→等 WAN→测吞吐→报告) | G→Architecture |
| `tools/probe_router.py` | 只读取证,引擎实测选择器命中数 | G→Architecture |
| `perf_configs/*.yaml` | 每台机一份接线(已提交);密码在 `router.yaml` | G→Environment |

其余:`start.py`/`adapt.py` 是给人的向导,`check_model.py` 离线体检
(**过了 ≠ 验收**),`tests/` 冒烟(mock 按原型组织,不按机型)。

**别整个读** `GOTCHAS.md`、`vendor/`(97MB)、`artifacts/probe_*.json`、`*.png`。

## 跑 / 验

```bash
python tests/smoke_test.py            # 必须 "0 failed"
python tools/check_model.py --all
python run_matrix.py --demo           # 离线整轮,出样例报告
python models/Tenda_AX3000.py pppoe   # 单档;加 --apply 才真下发
python models/_driver.py --verbs      # 动词清单(从 docstring 生成)
```

## 四条地雷(理由见 G)

- 仓库路径含 `[Tool]` = glob 的字符类 → 用 `os.listdir`,别用 `glob`。
- `vendor/python/` 是**故意提交**的离线运行时(`.bat` 都走它),
  **绝不进 Git LFS**。
- `matrix/chariot_perf.py` 要在台架 **Python 2.6** 下跑:别用 f-string/argparse。
- 台架控制台是 GBK;新的顶层入口脚本都要自己 `sys.path.insert(0, ROOT)`。

## 两个 skill(都在 `.claude/skills/`)

- **适配新机型** → `adapt-router-model/SKILL.md`(FACTS 逐键说明见
  同目录 `reference.md`)
- **跑整轮 / 排查 `err`** → `run-perf-round/SKILL.md`
