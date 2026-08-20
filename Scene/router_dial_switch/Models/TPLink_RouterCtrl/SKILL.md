# TPLink RouterCtrl —— 这台机的任务表

**通用流程、规矩、按需询问的三种情况在 `../../SKILL.md`。**
这里只有这台机的具体值。

这张表是**从 `TPLink_RouterCtrl.py` 的 FACTS 抄下来的,给人读的对照**。真相以 FACTS 为准 —— 两边对不上时,信 FACTS,并把这张表改过来。

```yaml
设备:
  品牌: TPLink
  型号: RouterCtrl
  走哪条路: 内部库 RouterCtrl(py2.6 桥接,不开浏览器)
  桥接脚本: routerctrl_bridge.py(和本文件同目录)
  py2 解释器: config.yaml 的 bench.python2

# ============ 第一段 · 前置 ============
前置:
  - 怎么做: 不开浏览器。py3 这一侧把档名翻成桥接认的复合名(见 BRIDGE_MODE),
            当子进程调桥接,读它 stdout 那一行 JSON
    做完的样子: 退出码 0,JSON 里 wan_type 和 dialed_up 都有

# ============ 第二段 · 状态表(一档一行)============
状态表:
  - 状态名: dynamic
    界面原话: Dynamic IP
    刷新后回读: Dynamic IP
    这一档下发后要等: 45 秒(DHCP 拿地址最慢)
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
    做完的样子: JSON 里 wan_type == 这一档的界面原话,**而且 dialed_up 是真** —— 只对上 wan_type 不算,
               真机上出过「类型对了但根本没拨上」

# ============ 安全 ============
会不会让我连不上这台设备: 否(台架断网,WAN 口不接出口)
每一档都会真正保存: 加了 --apply 才会
```

## 怎么跑这一台

```
cd Scene/router_dial_switch
python Models/TPLink_RouterCtrl/TPLink_RouterCtrl.py dynamic            # 只切,看回读,不下发
python Models/TPLink_RouterCtrl/TPLink_RouterCtrl.py dynamic --apply    # 真下发
python tools/check_model.py TPLink_RouterCtrl       # 离线体检
```

这台机支持的档:dynamic / pppoe / pptp / l2tp。这轮测哪几档由 `config.yaml` 的 `run.dial_modes` 决定。
