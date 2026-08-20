# Cudy AX1500 —— 这台机的任务表

**通用流程、规矩、按需询问的三种情况在 `../../SKILL.md`。**
这里只有这台机的具体值。

这张表是**从 `Cudy_AX1500.py` 的 FACTS 抄下来的,给人读的对照**。真相以 FACTS 为准 —— 两边对不上时,信 FACTS,并把这张表改过来。

```yaml
设备:
  品牌: Cudy
  型号: AX1500
  管理地址: http://192.168.10.1          # 出厂默认;实际填 config.yaml 的 router.ip
  密码: 见 config.yaml 的 router.pass    # 别写在这里,也别写进命令行

# ============ 第一段 · 前置 ============
前置:
  - 怎么做: 登录页密码框 "#pwd" 填 config.yaml 的 router.pass,再点 "input[value='Login']"
    做完的样子: 密码框消失
  - 怎么做: 依次点菜单 "sel:#Network" → "sel:#WAN"
    做完的样子: 页面上出现拨号控件和保存键(见下)

# ---- 这一页上的控件(每个都 probe_count.py 数过恰好 1)----
控件:
  拨号控件:
    形态: 原生下拉 <select>
    选择器: #wanType_id
  保存键: input[name='save_apply']
  账密框:
    pppoe_user(宽带账号): input[name='pppUserName']
    pppoe_pass(宽带密码): input[name='pppPassword']

# ============ 第二段 · 状态表(一档一行)============
状态表:
  - 状态名: dynamic
    界面原话: DHCP Client
    刷新后回读: DHCP Client
    要填什么: (无)
  - 状态名: static
    界面原话: Static IP
    刷新后回读: Static IP
    要填什么: (无)
  - 状态名: pppoe
    界面原话: PPPoE
    刷新后回读: PPPoE
    要填什么:
      pppoe_user(宽带账号)← config.yaml 的 router.pppoe_user,填进 input[name='pppUserName']
      pppoe_pass(宽带密码)← config.yaml 的 router.pppoe_pass,填进 input[name='pppPassword']
  - 状态名: pptp
    界面原话: PPTP
    刷新后回读: PPTP
    要填什么:
      vpn_server(隧道对端地址)← config.yaml 的 router.pptp.server,填进 input[name='pptpServerIpAddr']
      vpn_user(隧道账号)← config.yaml 的 router.pptp.user,填进 input[name='pptpUserName']
      vpn_pass(隧道密码)← config.yaml 的 router.pptp.pass,填进 input[name='pptpPassword']
  - 状态名: l2tp
    界面原话: L2TP
    刷新后回读: L2TP
    要填什么:
      vpn_server(隧道对端地址)← config.yaml 的 router.l2tp.server,填进 input[name='l2tpServerIpAddr']
      vpn_user(隧道账号)← config.yaml 的 router.l2tp.user,填进 input[name='l2tpUserName']
      vpn_pass(隧道密码)← config.yaml 的 router.l2tp.pass,填进 input[name='l2tpPassword']

# ============ 第三段 · 收尾(每一档都走一遍)============
收尾:
  - 怎么做: 点保存键 "input[name='save_apply']"
    做完的样子: 页面刷新完成
  - 怎么做: 刷新管理页,重新登录走一遍菜单
    做完的样子: 拨号控件显示的值 == 这一档的「刷新后回读」

# ============ 安全 ============
会不会让我连不上这台设备: 否(台架断网,WAN 口不接出口)
每一档都会真正保存: 加了 --apply 才会
```

## 怎么跑这一台

```
cd Scene/router_dial_switch
python Models/Cudy_AX1500/Cudy_AX1500.py dynamic            # 只切,看回读,不下发
python Models/Cudy_AX1500/Cudy_AX1500.py dynamic --apply    # 真下发
python tools/check_model.py Cudy_AX1500       # 离线体检
```

这台机支持的档:dynamic / static / pppoe / pptp / l2tp。这轮测哪几档由 `config.yaml` 的 `run.dial_modes` 决定。
