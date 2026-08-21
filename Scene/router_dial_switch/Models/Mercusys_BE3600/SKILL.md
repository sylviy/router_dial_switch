# Mercusys BE3600 —— 拨号切换适配

**这一个文件就是这台机的全部。** 上面填这台机的事实,下面是通用流程和规矩。
不用跳到别处读另一半。

**适配下一台机:把这个文件整个拷进 `Models/<新型号>/`,只改第一部分。**
挑哪一台来拷 —— 按 UI 形态挑最像的,对照表在 `../../SKILL.md`。
这台机是:**自定义下拉(role=combobox),账密框靠标签文字锚定**。

重复是**刻意的**,和型号脚本一个道理:换来的是"改第八台绝不可能弄坏前七台"。
技术细则(探测循环 / 找不到怎么办 / 控件形态表)在 `../../../../Tools/probing.md`,
卡在具体现象上按节查 `../../reference.md`(**按节读,别整篇读**)。

---

## 第一部分 · 这台机的任务表(拷过去只改这一部分)

下面每个值都是**从 `Mercusys_BE3600.py` 的 FACTS 抄下来的**。真相以 FACTS 为准 ——
两边对不上时信 FACTS,并把这张表改过来。

```yaml
设备:
  品牌: Mercusys
  型号: BE3600
  管理地址: http://192.168.1.1          # 出厂默认;实际填 config.yaml 的 router.ip
  密码: 见 config.yaml 的 router.pass    # 别写在这里,也别写进命令行

# ============ 第一段 · 前置 ============
前置:
  - 怎么做: 登录页密码框 "input[type=password]" 填 config.yaml 的 router.pass,再点 "button:text-is("Log In")"
    做完的样子: 密码框消失
  - 怎么做: 依次点菜单 "Internet"
    做完的样子: 页面上出现下面这几个控件

# ---- 这一页上的控件(每个都 probe_count.py 数过恰好 1)----
控件:
  拨号控件:
    形态: 自定义下拉(div 模拟)        # act.py 的 --kind dropdown
    选择器: [role='combobox']
  保存键: button:text-is("Save")
  账密框:
    pppoe_user(宽带账号): div.row:has-text("Username") input:visible
    pppoe_pass(宽带密码): div.row:has-text("Password") input:visible
    vpn_user(隧道账号): div.row:has-text("Username") input:visible
    vpn_pass(隧道密码): div.row:has-text("Password") input:visible
    vpn_server(隧道对端地址): div.row:has-text("VPN Server") input:visible

# ============ 第二段 · 状态表(一档一行)============
状态表:
  - 状态名: dynamic
    界面原话: Dynamic IP
    刷新后回读: Dynamic IP
    要填什么: (无)
  - 状态名: static
    界面原话: Static IP
    刷新后回读: Static IP
    要填什么: (无)
  - 状态名: pppoe
    界面原话: PPPoE
    刷新后回读: PPPoE
    要填什么:
      pppoe_user(宽带账号)← config.yaml 的 router.pppoe_user,填进 div.row:has-text("Username") input:visible
      pppoe_pass(宽带密码)← config.yaml 的 router.pppoe_pass,填进 div.row:has-text("Password") input:visible
  - 状态名: l2tp
    界面原话: L2TP
    刷新后回读: L2TP
    要填什么:
      vpn_server(隧道对端地址)← config.yaml 的 router.l2tp.server,填进 div.row:has-text("VPN Server") input:visible
      vpn_user(隧道账号)← config.yaml 的 router.l2tp.user,填进 div.row:has-text("Username") input:visible
      vpn_pass(隧道密码)← config.yaml 的 router.l2tp.pass,填进 div.row:has-text("Password") input:visible
  - 状态名: pptp
    界面原话: PPTP
    刷新后回读: PPTP
    要填什么:
      vpn_server(隧道对端地址)← config.yaml 的 router.pptp.server,填进 div.row:has-text("VPN Server") input:visible
      vpn_user(隧道账号)← config.yaml 的 router.pptp.user,填进 div.row:has-text("Username") input:visible
      vpn_pass(隧道密码)← config.yaml 的 router.pptp.pass,填进 div.row:has-text("Password") input:visible

# ============ 第三段 · 收尾(每一档都走一遍)============
收尾:
  - 怎么做: 点保存键 "button:text-is("Save")"
    做完的样子: 页面刷新完成
  - 怎么做: 刷新管理页,重新登录、重走一遍菜单
    做完的样子: 拨号控件显示的值 == 这一档的「刷新后回读」

# ============ 安全 ============
会不会让我连不上这台设备: 否(台架断网,WAN 口不接出口)
每一档都会真正保存: 加了 --apply 才会
```

---

## 第二部分 · 规矩(拷过去别改)

1. **不猜没观察过的 DOM。** 每个选择器都要 `probe_count.py` 数过恰好 1。
2. **只有回读 == 界面原话才算成功**,永不放宽成子串("PPPoEv6" 含 "PPPoE")。
   判定只有一个出口:`Vendor/common/contract.py` 的 `verify()`。
3. **点完不算数,刷新之后读回来才算数。** 不刷新读到的是自己刚填进去的值,
   等于自己给自己打分。工具里对应 `act.py --reload-verify`。
   **这一步 agent 自己做,不用等人。**
4. **命中 1 ≠ 选对了。** 页面上只有一个,不代表它是拨号控件。
5. **可以直接下发。** 台架断网、WAN 口不接出口,切错档不会把人关在门外。
6. **`_pause` / `_find` / `_find_text` 三个函数定死。** 在 `Tools/_probe.py`,
   全仓库唯一一份。探针可以整个复制到本目录的 `tools/` 下自由编辑(加控件
   形态、改输出都行),但这三个原样保留 —— 它们是"工具说命中 1"能预测"脚本
   也命中 1"的唯一依据。`tools/check_model.py` 逐字节比对,不一样报 error。
7. **凭据只在 `config.yaml`。** 别写进型号脚本,别写进命令行历史。

先跑一次 `python ../../../../Tools/env_check.py`;**下面所有命令里的 `python`
用它打印出来的那个解释器**(台架上是 `Vendor\python\python.exe`,系统那个是
不能动的 Python 2)。所有命令都在**场景目录下**跑(`cd Scene/router_dial_switch`)
—— 探针靠"在哪个目录跑"决定读哪份 config.yaml、产物往哪放。

---

## 第三部分 · 流程表(拷过去别改,只换里面的参数)

`<IP>` `<密码>` 从 `config.yaml` 取,不用每条都写。

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
| 8 | 把这台的经验写回 `../../reference.md` | | |

第 1~4 步**一档都不会改路由器**(只读 + 选中,不点保存)。第 5 步起才真下发,
**从最安全的那一档开始**(通常是 dynamic)。

**这台机的实际命令**(拷去新机型时就是改这几行):

```
python ../../Tools/probe_dump.py  --menu "Internet"
python ../../Tools/list_modes.py  --menu "Internet" --dial "[role='combobox']"
python ../../Tools/probe_count.py --menu "Internet" \
    --sel "[role='combobox']" --sel 'button:text-is("Save")'
python ../../Tools/act.py         --menu "Internet" --kind dropdown \
    --sel "[role='combobox']" --label "Dynamic IP"
python ../../Tools/act.py         --menu "Internet" --kind dropdown \
    --sel "[role='combobox']" --label "Dynamic IP" \
    --apply-sel 'button:text-is("Save")' --reload-verify
```

---

## 第四部分 · 按需询问(拷过去别改)

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

## 第五部分 · 怎么跑这一台

```
cd Scene/router_dial_switch
python Models/Mercusys_BE3600/Mercusys_BE3600.py dynamic            # 只切,看回读,不下发
python Models/Mercusys_BE3600/Mercusys_BE3600.py dynamic --apply    # 真下发
python Models/Mercusys_BE3600/Mercusys_BE3600.py dynamic --perf     # 整轮:逐档切 + 测吞吐 + 出报告
python tools/check_model.py Mercusys_BE3600       # 离线体检(过了 ≠ 验收)
```

这台机支持的档:dynamic / static / pppoe / l2tp / pptp。
这轮测哪几档由 `config.yaml` 的 `run.dial_modes` 决定;**换被测机只改**
`router.ip` 和 `run.dial_modes` 两处。

产出就是这个目录:

```
Models/Mercusys_BE3600/
    Mercusys_BE3600.py     交付物本体,**一个文件自足**
    SKILL.md           就是本文件
    tools/               可选:从 Tools/ 复制来、按这台机改过的探针
```

---

## 第六部分 · 做完之后必须做的两件事(拷过去别改)

1. **把路由器恢复默认,再让脚本从头跑一遍。**
   第一次跑通时,机器往往已经被你手工点到目标状态附近了,这时候的"成功"
   可能是假的 —— 脚本其实什么都没做对,只是状态本来就对。
   从干净状态跑通,是唯一能区分这两者的办法。跑不过就是还没做完。

2. **把新踩到的坑写进 `../../reference.md`** 对应的节(没有就新开一节,按 UI
   家族)。下一个人少花的时间就是从这里省的。

`../../docs/GOTCHAS.md` 是给人看的历史记录,**不要加载它**。
