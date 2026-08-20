# probing.md —— 给 agent 的技术细则

本文件配合各场景的 `SKILL.md` 使用。**人不需要读这份。**
`SKILL.md` 里那张任务表是唯一的输入,本文件说的是怎么把它变成能跑的东西。

---

## 运行环境

* 解释器固定 `Vendor\python\python.exe`。宿主机 PATH 上的是 Python 2.x,
  不能用,也不要动。
* **不要检查 python 版本、不要检查依赖包。** 库在仓库里,在就是能跑。
* 唯一要确认的:浏览器驱动能起来。跑一次 `Tools/env_check.py` 或
  `Tools/probe_dump.py` 能开出浏览器即可。
  起不来 = 环境问题,如实报告,不要改任何脚本。

## 这些工具在哪、怎么被找到

```
Tools/            通用探针 —— 所有场景共用,零 perf 代码
    _probe.py         底座:开浏览器 / 登录 / 走菜单 / **找元素**
    env_check.py      环境三项体检
    probe_dump.py     抄下当前页面所有控件
    probe_count.py    数某个选择器命中几个(必须恰好 1)
    list_modes.py     列一个选择控件的所有选项(抄界面原话)
    act.py            做一个动作 + 回读 + 刷新后再回读
Vendor/common/    contract.py(唯一判定)/ discover.py
Scene/<场景>/     每个场景自己的东西
```

工具**不数目录层级**:仓库根靠"往上找到 `Vendor/`"定位,场景根靠"`Scene/`
下面那一层"定位。所以搬目录不会让它们失灵,但有一条要记住 ——
**在哪个场景目录下跑,就算在哪个场景里**:
`cd Scene/router_dial_switch` 之后跑探针,它会顺手读到那个场景的
`config.yaml`、产物落进那个场景的 `artifacts/probes/`;在别处跑,两样都没有,
地址密码全靠 `--ip` / `--pass`,照样开工。

---

## 探测循环(核心)

页面是**逐步展开**的:很多控件初始态不存在,要点了前一个才出现。
所以不是"一次 dump 找齐所有控件",而是按任务表的步骤逐步推进:

```
for 每一步 in 任务表.步骤:
    A. probe_dump.py 看当前页面有什么
    B. 找不到目标 → 走下面「找不到怎么办」
    C. 找到了 → probe_count.py 确认恰好命中 1 → 记下选择器
    D. act.py 执行动作
    E. 用 --expect-after 确认这一步的「做完的样子」成立,才进入下一步
```

第 C 步命中 >1 但只有 1 个可见时:允许继续,但要在产出的注释里写明,
并且在生成的脚本里只取可见元素。

## 找不到怎么办(按顺序,不要跳)

1. **上一步的「做完的样子」成立了吗?** 不成立说明页面还没到那个状态,回退。

2. **dump 原始 HTML 看一眼。这是标准第二招,不是最后手段。**
   `probe_dump.py` 的清单只收表单元素(select / input / button)。
   真机上大量控件不是表单元素,例如 LuCI 的 Enable:

   ```html
   <div class="form-group" id="cbi-vpn-config-enabled">
     <label for="cbid.vpn.config.enabled">Enable</label>
     <input type="hidden" id="cbid.vpn.config.enabled" value="0">
     <i class="fa fa-toggle-off fa-2x" onclick="cbi_switch_toggle(...)"></i>
   </div>
   ```

   真正要点的是那个 `<i>` 图标,真实值在旁边的 hidden input 里
   (`act.py --kind toggle --sel <那个 i> --value-sel <那个 hidden input>`)。
   **清单里没有,不代表页面上没有。**

3. **看它是不是在 `class="hidden"` 的父容器里。** 是 = 前一步还没做。

4. **等 AJAX 挂载。** 选完某个值之后才渲染出来的区块,dump 太早就是空的。
   等待条件用 `--expect-after`(任务表里那一步的「做完的样子」),
   不要用固定 sleep。

5. 以上都不是 → **报告"真机与任务表不符",附 HTML 片段,请人改任务表。**
   不要推测"可能固件版本不同"然后自行绕路。

## 这个仓库已经踩过的三件事

* **元素可能不在主文档里。** 老式 frameset 固件(Cudy AX1500)登录框在主文档、
  菜单在顶部帧、WAN 表单在子帧。`_probe._find` 已经**扫所有 frame**,
  所以你不用自己遍历;但 `probe_dump.py` 的输出里那一列"所在文档"要看,
  它告诉你这个控件在哪个 frame。
* **LuCI 的 id 含点号**(`cbid.vpn.config.enabled`)。CSS 里点号是 class
  分隔符,`#cbid.vpn...` 会被解析成一堆 class。用 `[id='cbid.vpn.config.enabled']`。
* **命中多个时用所在表单收窄。** 真机上出过同一页 4 个 `name=cbi.apply`。
  `form:has(...) button[...]` 或 `div.v-form-item:has-text("…") …` 这种
  "用旁边的标签文字锚定"最稳,因为它跟着界面语义走,不跟着皮肤走。

## 已知的控件形态

`act.py --kind` 就是这一列:

| 形态 | `--kind` | 怎么点 | 怎么回读 |
|---|---|---|---|
| 原生 `<select>` | `select` | `select_option` | 选中项文字 |
| 自定义下拉(div 模拟) | `dropdown` | 点开 + 点选项文字 | `--value-sel` 指到的显示区,不要读下拉图标 |
| radio | `radio` | `click()` | `is_checked()` → 记模式名 |
| checkbox | `checkbox` | `check()` / `uncheck()` | `is_checked()` → `on` / `off` |
| 图标开关(`<i class="fa-toggle-*">`) | `toggle` | 点 `<i>` | `--value-sel` 那个 hidden input 的 value → 归一化成 `on`/`off` |
| 文本框 | `text` | `fill()` | `input_value()` |
| 按钮 | `button` | `click()` | 没有值可读 —— 判据是 `--expect-after` 出现 |

覆盖不到的形态,**加进 `act.py` 里**(多一个 `--kind` 分支),
不要为此复制一份工具出来。

## 不许做的事

* **`_pause` / `_find` / `_find_text` 这三个函数是定死的。**
  全仓库唯一一份,在 `Tools/_probe.py` 里。你可以把探针复制进
  `Models/<型号>/tools/` 或 `Devices/<…>/tools/` 自由编辑 —— 改命令行、改输出、
  加控件形态都随便 —— 但这三个函数**原样保留**。
  理由:它们是"工具说这个选择器命中 1"能预测"脚本也命中 1"的**唯一**依据。
  一旦各写各的,前面探测那几步的结论就不再说明脚本的行为,全部白做。
  `Scene/router_dial_switch/tools/check_model.py` 会逐字节比对,不一样报 error。
* 不许为了用上 `make_facts.py` 去掰任务形状。它只覆盖拨号那一类。
  别的任务照下面的契约手写。
* 生成的动作脚本不许 import 任何编排 / 性能 / 报告相关模块。

---

## 产出契约(唯一的解耦边界)

```
Scene/web_action/Devices/<品牌>_<型号>/<任务名>/
    action.py
    facts.yaml
```

### action.py

**只允许 import 一样东西:`Vendor/common/contract.py`。**
IP、密码等一律从命令行参数进来,不许去读任何全局配置加载器。

命令行:

```
action.py <状态> [--commit] --ip <IP> --pass <密码> [--out <目录>]
```

stdout **最后一行**是一行 JSON,前面可以打人看的日志:

```json
{"success": true, "state": "on", "read_back": "OpenVPN Server",
 "committed": true, "artifacts": ["client.ovpn"], "message": ""}
```

退出码:`0` 成功 / `2` 设备侧失败(没切成、回读不符)/ `3` 用法或环境错。

> 这就是 `Models/TPLink_RouterCtrl/routerctrl_bridge.py` 已经在用的协议。
> 沿用它,编排方不需要 import 动作单元,当子进程调即可,彻底解耦。

必须满足:

* `STATES` 声明有哪些状态;`apply(state, commit=False)` 是主角
* 成功判定走 `Vendor/common/contract.py`,**刷新之后回读,精确相等**
* 产物类判据检查文件存在且非空
* `--commit` 才真保存(默认演练一遍不落盘)。适配台架断网、WAN 口不接出口,
  所以**要不要 commit 你自己定,不用等人点头**
* 顶部注释写清:设备、任务、真机验证日期、**与任务表不符的地方**

### facts.yaml

* 顶部原样保留 `SKILL.md` 里那张任务表
* 每个选择器旁一行注释:哪一步得到的、命中几个、怎么确认它是对的那一个
