---
name: adapt-router-model
description: 为一台新路由器型号产出专属拨号切换脚本 Models/<品牌>_<型号>/<品牌>_<型号>.py,并验证到能跑整轮性能测试。触发场景:适配新型号 / 接入新路由器 / 加一台 Buffalo(Huawei/…)/ onboard a new router model / add router model / 生成 Tenda_XXX.py 这类脚本 / 某型号登录不进去或切换不成功要修 FACTS。输入:一台能访问到的路由器(同局域网)。
---

# 适配一台新路由器型号

**适配只有一步:从下表挑界面长得最像的那一台,把它整个目录拷成新型号,
然后照拷来的那份 `SKILL.md` 改第一部分。**

拷来的那份是**填好的、自足的** —— 任务表、规矩、工具介绍、推进顺序、按需询问、
产出形状,全在里面。**现在去读那一份**,别在这里等更多指示。

## 挑哪一台来拷

| 这台新机长什么样 | 拷这一台 | 它踩过的坑 |
|---|---|---|
| 原生下拉,老式 frameset / 普通单文档 | `Cudy_AX1500` | 登录框、菜单、表单在三个不同的文档里 |
| LuCI(OpenWrt),元素名长成 `cbid.network.wan.proto` | `Cudy_AX3000` | 名字里带点号,写选择器只能用属性形式;保存键要用它所在的表单收窄 |
| LuCI,而且同一页有好几个长得一样的控件 | `Cudy_BE6500` | 选择器**全部**用所在表单收窄 |
| 自绘的下拉,另外 IPv6 那几档在单独一页 | `Tenda_AX3000` | 值不显示在触发器上,要单独指到带值的那个元素;IPv6 页还得先开总开关 |
| 自绘的下拉,账密框只能靠旁边的标签文字认 | `Mercusys_BE3600` | 靠 "Username" / "Password" 这种标签文字锚定 |
| 一组单选按钮,设置页套在框架里打开 | `BUFFALO_WSR6000AX8` | 账密在另一页;要等框架里的内容真的就绪才算加载完 |
| 不走浏览器(内部库 / 命令行) | `TPLink_RouterCtrl` | 子进程通气;**回读对上 ≠ 拨上了** |

都在 `Scene/router_dial_switch/Models/` 下。拿不准就先 `probe_dump.py` 看一眼
清单里那一行写的是什么类型,再回来对号。

`Scene/router_dial_switch/tools/make_facts.py --write` 干的也是这件事:照你
`--like` 指定(或按 `--kind` 自动挑)的那台,把脚本和 SKILL.md 一起拷进新目录。

## 别的东西在哪

  * 技术细则(探测循环 / 找不到怎么办 / 控件形态表 / 产出契约)
    → `Tools/probing.md`
  * 卡在具体现象上(登录不进、认错控件、选择器收不窄、试切不过、整轮跑不起来)
    → `Scene/router_dial_switch/reference.md`(**按节读,别整篇读**)
  * 空白模版(通常用不上 —— 拷一台填好的更省事)→ `Tools/SKILL_TEMPLATE.md`

命令都在场景目录下跑(`cd Scene/router_dial_switch`)—— 探针靠"在哪个目录跑"
决定读哪份 config.yaml、产物往哪放。

`Scene/router_dial_switch/docs/GOTCHAS.md` 是给人看的历史记录,**不要加载**。
