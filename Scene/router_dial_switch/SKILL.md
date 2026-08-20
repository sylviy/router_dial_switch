---
name: adapt-router-model
description: 为一台新路由器型号产出专属拨号切换脚本 Models/<品牌>_<型号>/<品牌>_<型号>.py,并验证到能跑整轮性能测试。触发场景:适配新型号 / 接入新路由器 / 加一台 Buffalo(Huawei/…)/ onboard a new router model / add router model / 生成 Tenda_XXX.py 这类脚本 / 某型号登录不进去或切换不成功要修 FACTS。输入:一台能访问到的路由器(同局域网)。
---

# 适配一台新路由器型号

**产出只有一个目录**:`Models/<品牌>_<型号>/`,里面一个自足的脚本。
放进 `Models/` 就完事 —— 没有注册表要改,菜单自动认出它。别的文件一个都不要
动:不改 `Vendor/`、不改别的型号脚本、不改 `config.yaml` 里人填好的值。

技术细则(探测循环、找不到怎么办、控件形态表、这仓库踩过的坑)在
`Tools/probing.md`。卡在具体某个现象上时,按节查 `reference.md`,**别整篇读**。

---

## 第一部分 · 任务表(适配的时候填这里)

**这张表就是适配本身。** 填完它,下面第二部分那串命令就都有参数可填了;
填不出来的格子,就是还没探明白的地方。

```yaml
设备:
  品牌: Cudy
  型号: AX1500
  管理地址: http://192.168.10.1     # 填进 config.yaml 的 router.ip
  密码: 见 config.yaml 的 router.pass    # 不要写在这里,也不要写进命令行

# ============ 第一段 · 前置 ============
前置:
  - 怎么做: 登录页密码框 "#pwd" 填密码,点 "Login" 按钮
    做完的样子: 密码框消失,顶部出现菜单
  - 怎么做: 点菜单 "Network" → "WAN"
    做完的样子: 页面上出现"拨号方式"下拉,和右下角的 "Save & Apply"

# ============ 第二段 · 状态表(一档一行) ============
状态表:
  - 状态名: dynamic
    界面原话: DHCP Client        # list_modes.py 抄下来的,连大小写括号都一样
    要填什么: (无)
    刷新后回读: DHCP Client
  - 状态名: pppoe
    界面原话: PPPoE
    要填什么: 宽带账号 → input[name='pppUserName'](取 config.yaml 的
              router.pppoe_user);宽带密码 → input[name='pppPassword']
    刷新后回读: PPPoE
  # pptp / l2tp / …:照抄上面这两行的形状

# ============ 第三段 · 收尾(每一档都走一遍) ============
收尾:
  - 怎么做: 点右下角 "Save & Apply"(选择器 input[name='save_apply'])
    做完的样子: 页面刷新完成
  - 怎么做: 刷新管理页,重新走一遍菜单
    做完的样子: 拨号方式显示的值 == 这一档的「刷新后回读」

# ============ 安全 ============
会不会让我连不上这台路由器: 否(台架断网,WAN 口不接出口)
每一档都会真正保存: 是
```

---

## 第二部分 · 规矩(不要改)

1. **不猜没观察过的 DOM。** 每个选择器都要 `probe_count.py` 数过恰好 1。
2. **只有回读 == 目标措辞才算成功**,永不放宽成子串("PPPoEv6" 含 "PPPoE")。
   判定只有一个出口:`Vendor/common/contract.py` 的 `verify()`。
3. **点完不算数,刷新之后读回来才算数。** 不刷新读到的是自己刚填进去的值。
   工具里对应 `act.py --reload-verify`。**这一步 agent 自己做,不用等人。**
4. **命中 1 ≠ 选对了。** 页面上只有一个,不代表它是拨号控件。
5. **可以直接下发。** 适配台架断网、WAN 口不接出口,切错档不会把人关在门外。
6. **`_pause` / `_find` / `_find_text` 三个函数定死。** 在 `Tools/_probe.py`,
   全仓库唯一一份。探针可以整个复制到 `Models/<型号>/tools/` 自由编辑,
   但这三个原样保留 —— 它们是"工具说命中 1"能预测"脚本也命中 1"的唯一依据。
   `tools/check_model.py` 逐字节比对,不一样报 error。
7. **凭据只在 `config.yaml`。** 别写进型号脚本,别写进命令行历史。

先跑一次 `python Tools/env_check.py`;**下面所有命令里的 `python` 用它打印出来
的那个解释器**(台架上是 `Vendor\python\python.exe`,系统那个是不能动的
Python 2)。所有命令都在**这个场景目录下**跑(`cd Scene/router_dial_switch`)
—— 探针靠"在哪个目录跑"决定读哪份 config.yaml、产物往哪放。

---

## 第三部分 · 流程表

`<IP>` `<密码>` 从 `config.yaml` 取,不用每条都写;`--menu` 是走到 WAN 设置页
要点的菜单,逗号分隔,`sel:` 前缀表示用选择器、否则按菜单文字精确匹配。

| 步 | 跑什么 | 通过条件 | 不过往哪查 |
|---|---|---|---|
| 0 | `Tools/env_check.py` | 三项全绿 | **环境问题,不是适配问题** —— 如实报告,别改型号脚本 |
| 1 | `Tools/probe_dump.py --menu "…"` | 清单里有拨号类控件 | 没有 = 还停在首页,补 `--menu`;登录没进去看 `[login]` 那行 → `§ 登录`;清单里没有 ≠ 页面上没有 → `probing.md` 第 2 招 |
| 2 | `Tools/list_modes.py --dial "…"` | 选项数 ≥ 2 | 选到的可能不是拨号控件,回第 1 步换一个 → `§ 认错控件` |
| 3 | `Tools/probe_count.py --sel "…" …` | **每个恰好 1** | 用它所在的表单或旁边的标签文字收窄 → `§ 收窄选择器` |
| 4 | `Tools/act.py --sel "…" --label "…"` 逐档 | 回读 == 界面原话 | 措辞抄错 / 控件被盖住 / 值不在触发器上 → `§ 试切不过` |
| 5 | 同上加 `--apply-sel "…" --reload-verify` 逐档 | **刷新后**回读仍 == 界面原话 | 回读变回旧值 = 保存键认错了,回第 3 步 |
| 6 | `tools/make_facts.py … --write` 再 `tools/check_model.py <型号>` | 无 TODO、无 error | 照工具打的那几行补 |
| 7 | `python Models/<型号>/<型号>.py <档> --apply` 逐档 | 和第 5 步同样的回读 | 脚本和探针结果不一致 = 有东西没抄进 FACTS |
| 8 | 把这台的经验写回 `reference.md` | | |

第 1~4 步**一档都不会改路由器**(只读 + 选中,不点保存)。第 5 步起才真下发,
**从最安全的那一档开始**(通常是 dynamic)。

一条完整的例子(Cudy AX1500 那台就是这么出来的):

```
python Tools/probe_dump.py  --menu "sel:#Network,sel:#WAN"
python Tools/list_modes.py  --menu "sel:#Network,sel:#WAN" --dial "#wanType_id"
python Tools/probe_count.py --menu "sel:#Network,sel:#WAN" \
    --sel "#wanType_id" --sel "input[name='save_apply']"
python Tools/act.py         --menu "sel:#Network,sel:#WAN" \
    --sel "#wanType_id" --label "PPPoE"
python Tools/act.py         --menu "sel:#Network,sel:#WAN" \
    --sel "#wanType_id" --label "PPPoE" \
    --apply-sel "input[name='save_apply']" --reload-verify
```

`--kind` 见 `probing.md` 的控件形态表。不确定就先看 `probe_dump` 清单里那一行
的"类型"。

---

## 第四部分 · 按需询问(不是关卡)

**默认自己往下走。** 每一步都有能自己验证的通过条件,不必逐步等人点头。

只有下面这三种情况停下来问 —— 它们**再探测也解决不了**:

* 同名控件有好几个而且都可见,任务表里没有能区分它们的话
  (真机上出过:同一页 4 个 `name=cbi.apply`、8 个隐藏的 Connect 提交按钮、
  IPv6 页 LAN 区一个同名的 "DHCPv6" 诱饵);
* 真机和任务表对不上(那一档根本不存在、或者选项文字不一样);
* 一个动作可能顺带改到任务表没提的别的设置。

问的时候**用路由器的话问,不要用选择器语言问**:

> 我在「网络 → WAN」页上看到一个下拉,现在显示 "DHCP Client",展开有 5 项:
> Static IP / DHCP Client / PPPoE / PPTP / L2TP。同一页另外还有 2 个长得像的
> 下拉(一个在 MTU 旁边,一个在 DNS 旁边)。保存我认的是右下角那个
> "Save & Apply"。**请确认:拨号方式选的是不是这一个?保存是不是按这一个?**

---

## 第五部分 · 产出是什么

```
Models/<品牌>_<型号>/
    <品牌>_<型号>.py     交付物本体,**一个文件自足**,整个目录复制走就能跑
    SKILL.md             这台机填好的任务表(make_facts --write 会拷一份过来)
    tools/               可选:从 Tools/ 复制过来、按这台机改过的探针
```

目录名 == 文件名 == 型号名。`config.yaml` 里 `run.dial_modes` 写这轮测哪几档,
`router.ip` 写这台机的地址 —— **换被测机就改这两处**。

---

## 第六部分 · 做完之后必须做的两件事

1. **把路由器恢复默认,再让脚本从头跑一遍。**
   第一次跑通时,机器往往已经被你手工点到目标状态附近了,这时候的"成功"
   可能是假的 —— 脚本其实什么都没做对,只是状态本来就对。
   从干净状态跑通,是唯一能区分这两者的办法。跑不过就是还没做完。

2. **把新踩到的坑写进 `reference.md`** 对应的节(没有就新开一节,按 UI 家族)。
   下一个人少花的时间就是从这里省的。

`docs/GOTCHAS.md` 是给人看的历史记录,**不要加载它**,也不要把它的内容搬进
本文件。
