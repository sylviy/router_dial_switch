---
name: run-perf-round
description: 在测试台上跑一整轮 WAN 性能矩阵(逐档切拨号方式 → 等 WAN 拨通 → 测吞吐 → 出 HTML/CSV 报告),以及排查这一轮里的失败。触发场景:跑整轮 / 跑性能测试 / run the matrix / run_matrix.py 报错 / 某一格吞吐是 err / 报告里有 err / Chariot 跑不起来 / 配 perf.yaml / 切换成功但吞吐没数 / WAN 一直等不到拨通。
---

# 跑一整轮 WAN 性能矩阵

## 这一轮到底在做什么

`run_matrix.py`(包 `matrix/`)对**每一档拨号方式**做同一件事:

```
切换拨号方式(真正下发保存) → ping 等 WAN 拨通 → 逐个 频段×方向×协议 测吞吐
```

全部跑完写一份自包含 HTML + CSV 到 `artifacts/`。矩阵是四个轴的笛卡尔积:
**拨号方式 × 频段(lan/2GHz/5GHz)× 方向(up/down/bi)× 协议(TCP/UDP[-nofrag])**。

**台架语义:整轮里每档切换都真正下发,没有"只切不保存"的选项** —— 不下发,
吞吐测的就不是这档模式。想只切不保存,那是单模式入口
`python models/<型号>.py <mode>`(不加 `--apply`)。

## 怎么起

```bash
python start.py                    # 交互式:选型号 → 回车 = 整轮(推荐给测试员)
python run_matrix.py --model Tenda_AX3000       # 命令行整轮
python run_matrix.py --demo                     # 离线演示,不碰路由器,出样例报告
```

Windows 上是 `start.bat` / `matrix.bat`。解释器选择在 `_py.bat` 里:
先 `.venv\Scripts\python.exe`,再 `vendor\python\python.exe`,**不回落到 PATH 上
的裸 `python`**(台架上那个是 Python 2)。

## 配置分工(改错地方是最常见的浪费)

| 文件 | 管什么 | 谁写 |
|---|---|---|
| `perf.yaml` | 测什么、怎么测:矩阵、台架拓扑、WAN 拨通判据、报告位置 | 复制 `perf.example.yaml` 改 |
| `router.yaml` | 密码:管理密码、各模式的宽带/VPN 账号 | `python start.py --setup` |

两个都被 git 忽略。`perf.yaml` 不存在也能跑(全默认 + 遍历该型号全部模式)。

### 必须按模式分开配的三件事

1. **`wan_up.hosts`** —— 直连档和隧道档对端在不同网段。台架实测:`dynamic`
   打 `192.168.202.99`,`pppoe/l2tp/pptp` 拨通后要打 `192.168.203.1`。只配一个
   全局 `host`,另一半会白等满 `timeout_s` 才开测(不失败,但一档浪费一分钟)。
2. **`router.yaml` 的 `params[<模式>]`** —— L2TP 和 PPTP 字段名相同
   (`vpn_user`/`vpn_pass`)但台架发的是**两套账号**。存一层里后填的会覆盖先填的。
3. **`chariot.nofrag_bytes`** —— 只有测 `UDP-nofrag` 那档要。按拨号方式给 MTU
   (dynamic 1460 / pppoe 1440 / l2tp、pptp 1383)。没配的模式跑 `-nofrag` 会
   **明确报错而不是随便挑个值**:猜错了流量照样跑、数字照样漂亮,但其实分了片,
   一份标着"不分片"的分片数据最难被发现。

### 矩阵规模要先算一遍

`模式数 × 频段数 × 方向数 × 协议数` 就是测量格数,每格约 `duration_s` 秒外加
切换和拨通的时间。4 模式 × 3 频段 × 3 方向 × 2 协议 = **72 格,1.5~2 小时**。
先用 `bands: [lan]` 跑一轮确认链路,再放开频段。

## 排查

### 开跑前就被拦下:`性能后端 chariot 还不能用,整轮不开始`

这是**故意的**:后端没配好时,整轮会变成"把路由器来回真切一遍,拿回一份全是
err 的报告"(2026-07-28 台架真这么浪费过一轮)。照它给的原因修:

- `解释器 'python' 里没有 PyChariot` → `perf.yaml` 的 `chariot.python2` 要写
  **装了 PyChariot 的那个解释器的绝对路径**(台架是 `C:\Python26\python.exe`,
  YAML 里不要加双引号,`\P` 会被当转义)。
- 报错里出现 **`ModuleNotFoundError`** → 那是 **Python 3 才有的异常类**
  (Python 2.6 说的是 `ImportError: No module named PyChariot`),等于直接证明
  跑它的不是台架那套 Python 2。
- 自己确认一次:`C:\Python26\python.exe -c "import PyChariot; print('ok')"`

### 报告里某些格是 `err`

先看是不是**整档**都 err(那多半是切换/拨通的问题,往下看)还是零星几格。
`Measurement.error` 的文字会说明是哪一类:

- `chariot_perf.py 退出码 N` → 子进程自己崩了,尾部有它的 stderr。
  `chariot_perf.py` 会打完整 traceback,并在异常信息里带上**每个参数的值和类型**。
- `输出里没有 JSON 结果` → PyChariot 很吵,`import` 起就打 `DEBUG:ChariotApi:...`
  (还带中文)。后端是**从后往前找第一行能解析成 JSON 的**,不是取最后一行。
  真出现这条,说明脚本根本没走到打结果那步。
- `TypeError: an integer is required` → PyChariot 的 `CHR_PROTOCOL_*` 常量是
  **`c_byte` 对象不是 int**,要传 `.value`。假设它每个常量都可能是 ctypes 对象。

### 某一档"切换失败",整档被跳过

失败的切换**会被记录,不会被静默吞掉**(旧脚本的 `except: continue` 连错误
都注释掉了)。看那一行的 `message`:

- `login failed` → 管理密码;部分机型(Tenda/Mercusys)同时只允许一个 Web
  会话,先关掉浏览器里登录着的页签。
- `缺参数` → `router.yaml` 里该模式的账号没存。整轮**不会**拿着空账号去下发。
- `没找到拨号控件` / `没找到选项` → FACTS 该修了,走 `adapt-router-model` skill。

### `WAN 一直等不到拨通`

`wan_up.hosts` 里这一档配的地址对不对?能手工 `ping` 通吗?隧道档要等拨号
建立,`timeout_s` 默认 60 秒可能不够。确认不了就先 `method: wait`。

### 控制台报 `UnicodeEncodeError`

台架 Windows 控制台是 GBK(cp936),路由器回读的文字里有 GBK 编不出的字符就会
在最不该崩的时候崩。所有入口都做了 `reconfigure(errors="replace")` ——
**新加的顶层入口脚本别忘了这一条**,顺便也别忘了 `sys.path.insert(0, ROOT)`
(`vendor/python` 带 `._pth`,是隔离模式,不会把脚本目录放进 `sys.path`)。

## 结果怎么读

- HTML/CSV 在 `artifacts/wanperf_<型号>_<时间戳>.{html,csv}`;
- Chariot 的 `.tst` 原始记录在**同名同戳**的
  `artifacts/wanperf_<型号>_<时间戳>_tst/`,出争议时翻它;不想要就
  `chariot.save_tests: false`;
- `stable` 列 —— 中段采样 `min < stability_ratio × max` 判为不稳(默认 0.9)。
  不稳的数字别直接拿去对比,先看 `.tst`。
- UDP **只报吞吐**,没有丢包/抖动(和旧 `result_judge` 一致)。PyChariot 有
  `CHR_RESULTS_MLR` / `_JITTER`,要的话是新功能。

## 已知空档(别当 bug 查)

- **IPv6 吞吐还没测**。`dhcpv6`/`pppoev6` 只证明**切换**成功,Chariot 那边仍用
  IPv4 端点地址。缺的是台架的 v6 编址(endpoints + peers)和 `ping -6`,
  不是代码 —— `_protocol()` 已经能解析 `TCP6`/`UDP6`。
- **`static` 没有字段映射**:切过去但不填任何地址。`perf.yaml` 的 `dial_modes`
  里要排除它,否则那一档必然测了个断网。
- **无线频段不会自动切换**。`bands` 只决定用哪台注入机,没有任何东西去重新
  关联客户端。一轮里测两个频段 = 两台无线客户端、两个 IP。
