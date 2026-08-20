---
name: web-action
description: 为一台设备的一个 Web 界面操作产出一个可重复执行的动作单元(不是性能测试)。触发场景:开启某个功能 / 切换 VPN Server 协议 / 改某个设置再证明改成了 / 让某个界面操作可重复跑 / web action / UI 动作脚本。输入:一台同局域网可访问的设备 + 填好的任务表。
---

# 做一个 Web 操作动作单元

**正文在 `Scene/web_action/SKILL.md`,不是这里。现在去读它,照它那张任务表做。**

这里只是一个壳:Claude Code 只会自动发现 `.claude/skills/` 下的技能,而正文跟着
它所属的场景放。两处都有,内容只有一份。

  * 任务表 + 规矩 → `Scene/web_action/SKILL.md`(先完整读完)
  * 技术细则      → `Tools/probing.md`(探测循环 / 找不到怎么办 / 控件形态表 /
    **产出契约**:`action.py` 的命令行、末行 JSON、退出码 0/2/3)
  * 通用探针      → `Tools/`(`--help` 都可用;退出码 0=过 1=不过 2=用法错)
  * 工具本身有没有坏 → `python Scene/web_action/tests/mock_test.py`(不需要设备)

**这个场景不碰性能测试。** 逐档测吞吐、出报告那一套在
`Scene/router_dial_switch/`,是另一个场景,两边只共用 `Tools/` 和 `Vendor/`。
