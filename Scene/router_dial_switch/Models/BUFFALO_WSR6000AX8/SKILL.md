# BUFFALO WSR-6000AX8 —— 这台机的任务表

**通用流程、规矩、按需询问的三种情况在 `../../SKILL.md`。**
这里只有这台机的具体值。

这张表是**从 `BUFFALO_WSR6000AX8.py` 的 FACTS 抄下来的,给人读的对照**。真相以 FACTS 为准 —— 两边对不上时,信 FACTS,并把这张表改过来。

```yaml
设备:
  品牌: BUFFALO
  型号: WSR-6000AX8
  管理地址: http://192.168.11.1/advanced.html          # 出厂默认;实际填 config.yaml 的 router.ip
  密码: 见 config.yaml 的 router.pass    # 别写在这里,也别写进命令行

# ============ 第一段 · 前置 ============
前置:
  - 怎么做: 登录页密码框 "#form_PASSWORD" 填 config.yaml 的 router.pass,再点 "input.button_login"
    做完的样子: 密码框消失
  - 怎么做: 点 "p.CONNECT[data-main='wan.html']"
    做完的样子: iframe#content_main 里加载出 wan.html,而且 CA.length > 0

# ---- 这一页上的控件(每个都 probe_count.py 数过恰好 1)----
控件:
  拨号控件:
    形态: radio 组
    选择器: input[name='WanMethod']
  保存键: div#button_1
  保存后要等: 15000 毫秒
  账密框:
    pppoe_user(宽带账号): input#id_PUsername
    pppoe_pass(宽带密码): input#id_PPassword
  账密不在这一页: 要先切到 pppoe_reg.html 再填

# ============ 第二段 · 状态表(一档一行)============
状态表:
  - 状态名: dynamic
    要点哪个 radio: input#id_method2
    刷新后回读: 这个 radio 是选中的
    要填什么: (无)
  - 状态名: pppoe
    要点哪个 radio: input#id_method3
    刷新后回读: 这个 radio 是选中的
    要填什么: (无)
  - 状态名: transix
    要点哪个 radio: input#id_method5
    刷新后回读: 这个 radio 是选中的
    要填什么: (无)
  - 状态名: v6plus
    要点哪个 radio: input#id_method6
    刷新后回读: 这个 radio 是选中的
    要填什么: (无)
  - 状态名: ocnvc
    要点哪个 radio: input#id_method8
    刷新后回读: 这个 radio 是选中的
    要填什么: (无)
  - 状态名: v6connect
    要点哪个 radio: input#id_method10
    刷新后回读: 这个 radio 是选中的
    要填什么: (无)

# ============ 第三段 · 收尾(每一档都走一遍)============
收尾:
  - 怎么做: 点保存键 "div#button_1"
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
python Models/BUFFALO_WSR6000AX8/BUFFALO_WSR6000AX8.py dynamic            # 只切,看回读,不下发
python Models/BUFFALO_WSR6000AX8/BUFFALO_WSR6000AX8.py dynamic --apply    # 真下发
python tools/check_model.py BUFFALO_WSR6000AX8       # 离线体检
```

这台机支持的档:dynamic / pppoe / transix / v6plus / ocnvc / v6connect。这轮测哪几档由 `config.yaml` 的 `run.dial_modes` 决定。
