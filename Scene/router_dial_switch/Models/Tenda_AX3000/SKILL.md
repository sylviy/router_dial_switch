# Tenda AX3000 —— 这台机的任务表

**通用流程、规矩、按需询问的三种情况在 `../../SKILL.md`。**
这里只有这台机的具体值。

这张表是**从 `Tenda_AX3000.py` 的 FACTS 抄下来的,给人读的对照**。真相以 FACTS 为准 —— 两边对不上时,信 FACTS,并把这张表改过来。

```yaml
设备:
  品牌: Tenda
  型号: AX3000
  管理地址: http://192.168.0.1          # 出厂默认;实际填 config.yaml 的 router.ip
  密码: 见 config.yaml 的 router.pass    # 别写在这里,也别写进命令行

# ============ 第一段 · 前置 ============
前置:
  - 怎么做: 登录页密码框 "input[type=password]" 填 config.yaml 的 router.pass,再点 "button.login-form__submit"
    做完的样子: 密码框消失
  - 怎么做: 依次点菜单 "Internet Settings"
    做完的样子: 页面上出现拨号控件和保存键(见下)

# ---- 这一页上的控件(每个都 probe_count.py 数过恰好 1)----
控件:
  拨号控件:
    形态: 自定义下拉(div 模拟)
    选择器: div.v-form-item:has-text("Internet Connection Type") div.v-select
    回读值在: [data-name='wanType']        # 不读下拉小图标,读这个
  保存键: button[data-name='submit']:has(span:text-is("Connect"))
  账密框:
    pppoe_user(宽带账号): input[data-name='wanPPPoEUser']
    pppoe_pass(宽带密码): input[data-name='wanPPPoEPwd']

# ============ 第二段 · 状态表(一档一行)============
状态表:
  - 状态名: dynamic
    界面原话: Dynamic IP
    刷新后回读: Dynamic IP
    要填什么: (无)
  - 状态名: pppoe
    界面原话: PPPoE
    刷新后回读: PPPoE
    要填什么:
      pppoe_user(宽带账号)← config.yaml 的 router.pppoe_user,填进 input[data-name='wanPPPoEUser']
      pppoe_pass(宽带密码)← config.yaml 的 router.pppoe_pass,填进 input[data-name='wanPPPoEPwd']
  - 状态名: static
    界面原话: Static IP
    刷新后回读: Static IP
    要填什么: (无)
  - 状态名: dhcpv6
    界面原话: DHCPv6
    刷新后回读: DHCPv6
    这一档在别的页: 菜单走 "More" → "IPv6"
    先要打开的开关: [data-name='ipv6En']
    这一档的保存键不一样: button[data-name='submit']:has(span:text-is("Save"))
    要填什么: (无)
  - 状态名: pppoev6
    界面原话: PPPoEv6
    刷新后回读: PPPoEv6
    这一档在别的页: 菜单走 "More" → "IPv6"
    先要打开的开关: [data-name='ipv6En']
    这一档的保存键不一样: button[data-name='submit']:has(span:text-is("Save"))
    要填什么:
      pppoe_user(宽带账号)← config.yaml 的 router.pppoe_user,填进 input[data-name='wanPPPoEUser']
      pppoe_pass(宽带密码)← config.yaml 的 router.pppoe_pass,填进 input[data-name='wanPPPoEPwd']

# ============ 第三段 · 收尾(每一档都走一遍)============
收尾:
  - 怎么做: 点保存键 "button[data-name='submit']:has(span:text-is("Connect"))"
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
python Models/Tenda_AX3000/Tenda_AX3000.py dynamic            # 只切,看回读,不下发
python Models/Tenda_AX3000/Tenda_AX3000.py dynamic --apply    # 真下发
python tools/check_model.py Tenda_AX3000       # 离线体检
```

这台机支持的档:dynamic / pppoe / static / dhcpv6 / pppoev6。这轮测哪几档由 `config.yaml` 的 `run.dial_modes` 决定。
