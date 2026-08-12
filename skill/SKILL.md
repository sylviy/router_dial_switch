---
name: adapt-router-model
description: 为一台新路由器型号产出专属拨号切换脚本 models/<品牌>_<型号>.py,并验证到能跑整轮性能测试。触发场景:适配新型号 / 接入新路由器 / 加一台 Buffalo(Huawei/…)/ onboard a new router model / add router model / 生成 Tenda_XXX.py 这类脚本 / 某型号登录不进去或切换不成功要修 FACTS。输入:一台能访问到的路由器(同局域网)。
---

# 适配一台新路由器型号

产出一个 `models/<品牌>_<型号>.py`。放进 `models/` 就完事,没有注册表要改。

**按下面这张表**一步步跑,每步都有明确的通过条件(退出码 0 = 过)。不过就照
「不过往哪查」那一列去 `reference.md` 读**那一节**,别整篇读。

## 五条铁律

1. **不猜没观察过的 DOM。** 每个选择器都要 `probe_count.py` 数过恰好 1。
2. **只有回读 == 目标措辞才算成功**,永不放宽成子串("PPPoEv6" 含 "PPPoE")。
3. **命中 1 ≠ 选对了。** 页面上只有一个,不代表它是拨号控件 —— 见关卡一。
4. **默认不点保存。** 人点头才 `--apply`。切错档当场断网,台架上没人能远程救。
5. **凭据只在 `config.yaml`。** 别写进型号脚本,别写进命令行历史。

先跑一次 `python skill/tools/env_check.py`;**下面所有命令里的 `python` 用它
打印出来的那个解释器**(台架上是 `vendor\python\python.exe`,系统那个是不能动
的 Python 2)。

## 流程表

`<IP>` `<密码>` 从 `config.yaml` 取,不用每条都写;`--menu` 是走到 WAN 设置页
要点的菜单,逗号分隔,`sel:` 前缀表示用选择器、否则按菜单文字精确匹配。

| 步 | 跑什么 | 通过条件 | 不过往哪查 |
|---|---|---|---|
| 0 | `env_check.py` | 三项全绿 | **环境问题,不是适配问题** —— 如实报告,别改型号脚本 |
| 1 | `probe_dump.py --menu "…"` | 清单里有拨号类控件 | 没有 = 还停在首页,补 `--menu`;登录没进去看 `[login]` 那行 → `§ 登录` |
| 2 | `list_modes.py --dial "…"` | 选项数 ≥ 2 | 选到的可能不是拨号控件,回第 1 步换一个 → `§ 认错控件` |
| 3 | `probe_count.py --sel "…" …` | **每个恰好 1** | 用它所在的表单或旁边的标签文字收窄 → `§ 收窄选择器` |
| ⛔ | **停下问人**(关卡一,见下) | 人认定了 | |
| 4 | `try_switch.py --dial "…" --label "…"` 逐档 | 回读 == 目标措辞 | 措辞抄错 / 控件被盖住 / 值不在触发器上 → `§ 试切不过` |
| 5 | `make_facts.py … --write models/X.py` 再 `check_model.py X` | 无 TODO、无 error | 照工具打的那几行补 |
| ⛔ | **停下问人**(关卡二,见下) | 人点头 | |
| 6 | 把这台的经验写回 `reference.md` | | |

第 1~4 步**一档都不会改路由器**(只读 + 选中,不点保存)。

一条完整的例子(Cudy AX1500 那台就是这么出来的):

```
python skill/tools/probe_dump.py  --menu "sel:#Network,sel:#WAN"
python skill/tools/list_modes.py  --menu "sel:#Network,sel:#WAN" --dial "#wanType_id"
python skill/tools/probe_count.py --menu "sel:#Network,sel:#WAN" \
    --sel "#wanType_id" --sel "input[name='save_apply']"
python skill/tools/try_switch.py  --menu "sel:#Network,sel:#WAN" \
    --dial "#wanType_id" --label "PPPoE"
```

`--kind` 三选一:`select`(原生下拉)/ `dropdown`(自定义下拉)/ `radio`(单选)。
不确定就先看 `probe_dump` 清单里那一行的"类型"。

## ⛔ 关卡一:选择器认定(第 3 步之后)

命中 1 只说明**页面上只有一个**,不说明它是对的。真机上出过:同一页 4 个
`name=cbi.apply`、8 个隐藏的 Connect 提交按钮、IPv6 页 LAN 区一个同名的
"DHCPv6" 诱饵。

**用路由器语言问,不能用选择器语言问。** 照这个形状:

> 我在「网络 → WAN」页上看到一个下拉,现在显示的是「DHCP Client」,
> 展开有 5 项:Static IP / DHCP Client / PPPoE / PPTP / L2TP。
> 同一页另外还有 2 个长得像的下拉(一个在 MTU 旁边,一个在 DNS 旁边)。
> 保存按钮我认的是右下角那个「Save & Apply」。
> **请确认:拨号方式选的是不是这一个?保存是不是按这一个?**

等人明确回答,再往下。

## ⛔ 关卡二:下发确认(第 5 步之后)

**逐档**把回读值和截图摆给人看,人点头才允许 `--apply`:

> dynamic → 回读 'DHCP Client' ✅ 截图 artifacts/probes/try_switch_DHCP_Client.png
> pppoe   → 回读 'PPPoE'       ✅ 截图 artifacts/probes/try_switch_PPPoE.png
> 六档全部回读一致。**要我真正下发吗?** 下发会改路由器配置,切错会断网。

人点头后才:

```
python skill/tools/try_switch.py --dial "…" --label "…" --apply --apply-sel "…"
python models/<品牌>_<型号>.py <档> --apply
```

从**最安全的那一档开始**(通常是 dynamic:切错也不至于连不上)。

## 第 6 步:把经验写回去

新踩到的坑写进 `reference.md` 对应的节(没有就新开一节,按 UI 家族)。
下一个人少花的时间就是从这里省的。

`docs/GOTCHAS.md` 是给人看的历史记录,**不要加载它**,也不要把它的内容搬进本文件。
