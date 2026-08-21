# TPLink RouterCtrl —— 拨号切换适配

**这一个文件就是这台机的全部。** 上面填这台机的事实,下面是通用流程和规矩。
不用跳到别处读另一半。

**适配下一台机:把这个文件整个拷进 `Models/<新型号>/`,只改第一部分。**
挑哪一台来拷 —— 按 UI 形态挑最像的,对照表在 `../../SKILL.md`。
这台机是:**不走浏览器 —— py2.6 桥接子进程**。

重复是**刻意的**,和型号脚本一个道理:换来的是"改第八台绝不可能弄坏前七台"。
技术细则(探测循环 / 找不到怎么办 / 控件形态表)在 `../../../../Tools/probing.md`,
卡在具体现象上按节查 `../../reference.md`(**按节读,别整篇读**)。

---

## 第一部分 · 这台机的任务表(拷过去只改这一部分)

下面每个值都是**从 `TPLink_RouterCtrl.py` 的 FACTS 抄下来的**。真相以 FACTS 为准 ——
两边对不上时信 FACTS,并把这张表改过来。

```yaml
设备:
  品牌: TPLink
  型号: RouterCtrl
  走哪条路: 内部库 RouterCtrl(py2.6 桥接子进程,**不开浏览器**)
  桥接脚本: routerctrl_bridge.py(和本文件同目录)
  py2 解释器: config.yaml 的 bench.python2

# ============ 第一段 · 前置 ============
前置:
  - 怎么做: 把档名翻成桥接认的复合名(见 BRIDGE_MODE),当子进程调桥接
    做完的样子: 退出码 0,stdout 最后一行 JSON 里 wan_type 和 dialed_up 都在

# ============ 第二段 · 状态表(一档一行)============
状态表:
  - 状态名: dynamic
    界面原话: Dynamic IP
    刷新后回读: Dynamic IP
    这一档下发后要等: 45 秒(DHCP 拿地址是最慢的)
    要填什么: (无)
  - 状态名: pppoe
    界面原话: PPPoE
    刷新后回读: PPPoE
    要填什么:
      pppoe_user(宽带账号)← config.yaml 的 router.pppoe_user
      pppoe_pass(宽带密码)← config.yaml 的 router.pppoe_pass
  - 状态名: pptp
    界面原话: PPTP
    刷新后回读: PPTP
    要填什么:
      vpn_server(隧道对端地址)← config.yaml 的 router.pptp.server
      vpn_user(隧道账号)← config.yaml 的 router.pptp.user
      vpn_pass(隧道密码)← config.yaml 的 router.pptp.pass
  - 状态名: l2tp
    界面原话: L2TP
    刷新后回读: L2TP
    要填什么:
      vpn_server(隧道对端地址)← config.yaml 的 router.l2tp.server
      vpn_user(隧道账号)← config.yaml 的 router.l2tp.user
      vpn_pass(隧道密码)← config.yaml 的 router.l2tp.pass

# ============ 第三段 · 收尾(每一档都走一遍)============
收尾:
  - 怎么做: 桥接自己下发并回读,py3 这一侧不点任何东西
    做完的样子: JSON 里 wan_type == 这一档的界面原话,**而且 dialed_up 是真**
               —— 只对上 wan_type 不算。真机上出过「类型对了但根本没拨上」,
               那一轮报告里那几格数字是假的。

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

这条路线**不开浏览器**,探针那几步用不上。流程是:

| 步 | 跑什么 | 通过条件 | 不过往哪查 |
|---|---|---|---|
| 0 | 确认 `config.yaml` 的 `bench.python2` 指到装了 RouterCtrl 的那个 py2 | `<那个 python> -c "import PyChariot; print('ok')"` | 没配就明确报错说该填哪 |
| 1 | 单跑桥接:`<py2> routerctrl_bridge.py <复合档名> --ip … --user admin --pass …` | 退出码 0,末行 JSON | 退出码 3 = 用法错(**档名必须是复合名**);2 = 设备侧失败 |
| 2 | `python Models/TPLink_RouterCtrl/TPLink_RouterCtrl.py <档>` | 回读 == 界面原话 **且** dialed_up 为真 | 只对上 wan_type 不算 —— 见收尾那一段 |
| 3 | `python tools/check_model.py TPLink_RouterCtrl` | 无 error | 照工具打的那几行补 |
| 4 | 把这台的经验写回 `../../reference.md` | | |

**桥接文件一个字都别用 py3 语法改**(它是 py2.6)。档名翻译只发生在 py3 这一侧的
`BRIDGE_MODE` 里。

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
python Models/TPLink_RouterCtrl/TPLink_RouterCtrl.py dynamic            # 只切,看回读,不下发
python Models/TPLink_RouterCtrl/TPLink_RouterCtrl.py dynamic --apply    # 真下发
python Models/TPLink_RouterCtrl/TPLink_RouterCtrl.py dynamic --perf     # 整轮:逐档切 + 测吞吐 + 出报告
python tools/check_model.py TPLink_RouterCtrl       # 离线体检(过了 ≠ 验收)
```

这台机支持的档:dynamic / pppoe / pptp / l2tp。
这轮测哪几档由 `config.yaml` 的 `run.dial_modes` 决定;**换被测机只改**
`router.ip` 和 `run.dial_modes` 两处。

产出就是这个目录:

```
Models/TPLink_RouterCtrl/
    TPLink_RouterCtrl.py     交付物本体,**一个文件自足**
    routerctrl_bridge.py       py2.6 桥接,只这台用
    SKILL.md             就是本文件
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
