---
name: adapt-router-model
description: 为一台新路由器型号产出专属拨号切换脚本 models/<品牌>_<型号>.py,并验证到能跑整轮性能测试。触发场景:适配新型号 / 接入新路由器 / 加一台 Buffalo(Huawei/…)/ onboard a new router model / add router model / 生成 Tenda_XXX.py 这类脚本 / 某型号登录不进去或切换不成功要修 FACTS。输入:一台能访问到的路由器(同局域网)。
---

# 适配一台新路由器型号

**正文在 `skill/SKILL.md`(仓库根目录下的 `skill/`,不是这里)。现在去读它,
照它那张流程表做。**

这里只是一个壳:Claude Code 只会自动发现 `.claude/skills/` 下的技能,而任务书
要求正文放在仓库根的 `skill/` 里(和 `skill/tools/` 那七个工具放在一起)。
两处都有,内容只有一份。

  * 流程和两处关卡 → `skill/SKILL.md`(≤6KB,先完整读完)
  * 卡住了按节查   → `skill/reference.md`(**按节读,别整篇读**)
  * 七个工具       → `skill/tools/`(`--help` 都可用;退出码 0=过 1=不过 2=用法错)

`GOTCHAS.md` 是给人看的历史记录,**不要加载**。
