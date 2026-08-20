---
name: adapt-router-model
description: 为一台新路由器型号产出专属拨号切换脚本 Models/<品牌>_<型号>/<品牌>_<型号>.py,并验证到能跑整轮性能测试。触发场景:适配新型号 / 接入新路由器 / 加一台 Buffalo(Huawei/…)/ onboard a new router model / add router model / 生成 Tenda_XXX.py 这类脚本 / 某型号登录不进去或切换不成功要修 FACTS。输入:一台能访问到的路由器(同局域网)。
---

# 适配一台新路由器型号

**正文在 `Scene/router_dial_switch/SKILL.md`,不是这里。现在去读它,
照它那张任务表和流程表做。**

这里只是一个壳:Claude Code 只会自动发现 `.claude/skills/` 下的技能,而正文跟着
它所属的场景放。两处都有,内容只有一份。

  * 任务表 + 流程表 → `Scene/router_dial_switch/SKILL.md`(先完整读完)
  * 技术细则        → `Tools/probing.md`(探测循环 / 找不到怎么办 / 控件形态表)
  * 卡住了按节查    → `Scene/router_dial_switch/reference.md`(**按节读,别整篇读**)
  * 通用探针        → `Tools/`(`--help` 都可用;退出码 0=过 1=不过 2=用法错)
  * 这个场景专属的两个工具 → `Scene/router_dial_switch/tools/`

命令都在场景目录下跑(`cd Scene/router_dial_switch`)—— 探针靠"在哪个目录跑"
决定读哪份 config.yaml、产物往哪放。

`Scene/router_dial_switch/docs/GOTCHAS.md` 是给人看的历史记录,**不要加载**。
