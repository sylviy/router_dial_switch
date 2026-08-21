---
name: web-action
description: 为一台设备的一个 Web 界面操作产出一个可重复执行的动作单元(不是性能测试)。触发场景:开启某个功能 / 切换 VPN Server 协议 / 改某个设置再证明改成了 / 让某个界面操作可重复跑 / web action / UI 动作脚本。输入:一台同局域网可访问的设备 + 填好的任务表。
---

# 做一个 Web 操作动作单元

**产出是一个动作,不是一套测试。** 它只负责"把设备切到某个状态,并且证明真的
切到了"。

**做一个新的只有一步:找一份最像的 `SKILL.md` 拷过来,改第一部分。**
拷来的那份是自足的 —— 任务表、规矩、工具介绍、推进顺序、按需询问、产出契约,
全在里面。

从哪拷:

  * `Scene/web_action/Devices/<品牌>_<型号>/<任务名>/SKILL.md` —— 已经做过的
    任务,拷最像的那个(它是**填好的**,最省事);
  * `Devices/` 还是空的(现在就是)→ 拷空白模版 `Tools/SKILL_TEMPLATE.md`;
  * 要找一个填好的样子参考,`Scene/router_dial_switch/Models/*/SKILL.md`
    是同一个骨架的另一批实例。

## 别的东西在哪

  * 技术细则 + **产出契约**(`action.py` 的命令行、末行 JSON、退出码 0/2/3)
    → `Tools/probing.md`
  * 通用探针 → `Tools/`(`--help` 都可用;退出码 0=过 1=不过 2=用法错)
  * 工具本身有没有坏 → `python Scene/web_action/tests/mock_test.py`(不需要设备)

**这个场景不碰性能测试。** 逐档测吞吐、出报告那一套在
`Scene/router_dial_switch/`,是另一个场景,两边只共用 `Tools/` 和 `Vendor/`。
