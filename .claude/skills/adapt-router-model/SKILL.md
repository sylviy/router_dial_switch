---
name: adapt-router-model
description: 为一台新路由器型号产出专属拨号切换脚本 models/<品牌>_<型号>.py,并验证到能跑整轮性能测试。触发场景:适配新型号 / 接入新路由器 / 加一台 Buffalo(Huawei/…)/ onboard a new router model / add router model / 生成 Tenda_XXX.py 这类脚本 / 某型号登录不进去或切换不成功要修 FACTS。输入:一台能访问到的路由器(同局域网),或用户回传的一份控件清单。
---

# 适配一台新路由器型号

**产出**:一个文件 `models/<品牌>_<型号>.py` —— 只有这台机的事实(FACTS),
点击逻辑全在共用的 `models/_driver.py` 里。放进 `models/` 就完事,
`start.py` / `run_matrix.py` 扫目录自动发现,**没有注册表要改**。

## 成本纪律(先读这一节)

**一台设备的预算:输入 ~1500 token,输出 ~500。** 超出说明走错路了。

**不要做**(这些是真实烧掉过用户余额的动作):

- **不要探索。** 别为了"搞清楚驱动怎么工作"去读 `models/_driver.py`(574 行)
  —— 它的行为下面和 `reference.md` 已经写全。
- **不要整份读**:`artifacts/probe_*.json`(真机上几百 KB)、`artifacts/*.png`、
  `vendor/`(97 MB)、`CLAUDE.md` 全文。要查某一段就 `python -c` 切出来。
- **不要写 mock、不要改 `tools/`、不要改 `_driver.py`。** 那些是真机验收之后
  才谈的事,不属于适配一台机器。
- **不要逐行生成代码。** 脚本要么由 `--emit` 写出来,要么你只输出一个
  FACTS dict —— 别把 100 行脚本一个字一个字打出来。

## 铁律(违反任何一条 = 返工)

1. **不猜没观察过的 DOM。** 每个选择器都要有出处,而且**命中数必须实测==1**
   (`--count`)。宁可留 `TODO` 让它诚实失败,也不写"大概是这样"。
2. **只有真实回读 == 目标措辞才算成功。** 驱动已内置(精确相等)。
   **永远不要**放宽成子串 —— "PPPoEv6" 会被认成 "PPPoE"。
3. **默认不点保存。** 验证阶段不带 `--apply`;全部回读正确才验收。
   切错模式会断网,别在承载真实上网的路由器上验收。
4. **凭据不进仓库。** 密码走 `router.yaml`(git 已忽略)。

## 流程 A:你能连到这台路由器(主路)

```bash
curl -m 4 http://<ip>            # 先确认真连得上,别凭旧结论
```

**第 1 步:先白试一次自动生成(0 token)。**

```bash
python tools/probe_router.py --url http://<ip> --pass <密码> \
    --nav "<设置页菜单文字>" --probe-modes \
    --brand <品牌> --model <型号> --emit models/<品牌>_<型号>.py
```

摘要里没有 `TODO` 就直接跳到第 4 步 —— 这台机不需要你判断任何东西。
**留了 TODO 就不要去改探针的猜测逻辑**,往下走。

**第 2 步:让它把页面抄给你(约 300 token)。**

```bash
python tools/probe_router.py --dump --url http://<ip> --pass <密码> \
    --nav "<设置页菜单文字>"
```

每行一个控件(`vis=` 是否可见),没有任何猜测。原始 HTML 几十万字符,这份
清单一千字符出头 —— **只读这份,不要去看页面源码**。

看不到拨号控件时:大概率还停在首页,补 `--nav "<菜单文字>"` 再抄一次
(前缀 `sel:` 表示用选择器点)。

**第 3 步:自己写 FACTS,然后让引擎判对错。**

照 `reference.md` 的键写(或复制 `models/Cudy_AX3000.py` 改)。写完把每个
选择器都数一遍:

```bash
python tools/probe_router.py --url http://<ip> --pass <密码> --nav "..." \
    --count "<拨号控件>" --count "<保存键>" --count "<账密框>"
```

**命中数不是 1 就不能用。** 这一步是本仓库所有"假成功"的唯一防线 ——
`button:text-is("Connect")` 看着没错但命中 0(文字在里层 span);
`#cbid.network.wan.proto` 看着没错但命中 0(id 含点号);
`button[name='cbi.apply']` 看着没错但命中 4。**只有真引擎数得出来。**

不唯一时的两条常用收窄法(先试这两个,再想别的):

```
form:has(<拨号控件>) <按钮>                        # 一页多段、每段一个保存键
div.<行class>:has-text("<标签文字>") <控件>        # 类名不唯一,用标签锚定
```

**第 4 步:体检 + 真机逐模式验证(0 token)。**

```bash
python tools/check_model.py <品牌>_<型号>     # 残留 TODO / 缺字段 / 措辞撞车
python models/<品牌>_<型号>.py <每一个模式>    # 看 success + read_back
```

`success:true` 且 `read_back` 正是目标措辞才算过。失败信息会**列出它当时
实际看到的东西**(下拉里有哪些选项、页面上有哪些按钮)—— 照着改,别重新猜。

**第 5 步:验收 + 交待。** 全部过了,每档带 `--apply` 跑一次确认
`applied:true`。然后告诉用户台架还要在 `perf.yaml` 配:`dial_modes`
(**排除 `static`**,它没有字段映射)、`wan_up.hosts`(按模式配 ping 目标)、
`chariot.nofrag_bytes`(测 UDP 不分片档才要),以及 `router.yaml` 的
`params[<模式>]`(L2TP / PPTP 字段名相同但账号不同,必须分模式存)。

## 流程 B:你连不到这台路由器

让用户在能访问的机器上跑第 2 步那条 `--dump`,把输出贴给你;你出 FACTS,
再让用户跑第 3 步的 `--count` 把命中数贴回来。**其余完全一样。**
提醒用户产物里可能有会话 token,回传前过一眼。

## 卡住了:先分三类

| 症状 | 类别 | 怎么办 |
|---|---|---|
| 抛异常退出 | **崩溃** | 看 `artifacts/crash_*.txt`(20 行,已滤掉浏览器日志)。多数是环境问题,`tools/crashlog.py` 直接给结论 |
| 登录不进去 | **登录** | 探针会打印登录页诊断:密码框/文本框/按钮/可点元素 + 截图。老 UI 的登录键常是 `<a>`/`<div>`,不是 `<button>` |
| `--dump` 里看得见控件,但选择器不唯一/回读不对 | **定位** | 便宜。用上面两条收窄法,`--count` 验证。**修法必须通用 —— `_driver.py` 和 `probe_router.py` 里没有一行按品牌分支的代码,保持这样** |
| 页面上明明有,`--dump` 却压根没有这个形态 | **形态** | 贵。见「边界」:要给 `_driver.py` 加新 `dial.kind` + 配 mock,那是单独立项的功能开发,**不是适配某台机的顺手活** |

## 边界(现有三种 `dial.kind` 吃不下的)

卡片条 / 分段选择器(一排 `动态IP | 静态IP | PPPoE` 方块)、值文本不是模式词的
控件、保存前的确认弹窗、closed shadow DOM、验证码登录、canvas 自绘 UI。

遇到**先如实报告**它长什么样,不要硬凑一个 FACTS 交差。

## 要更细的东西时再看 `reference.md`

FACTS 逐键说明、选择器手册、**陷阱清单**(每条都是真机上的假成功)、
定位问题的通用修法实例、判定"这台机真的没有某功能"的穷尽核查法、参考实现对照表。
