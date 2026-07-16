"""型号脚本模板 —— 复制成 models/<品牌>_<型号>.py 后逐项填 FACTS。

产出流程(完整方法论见 .claude/skills/adapt-router-model/SKILL.md):
  1. 在能访问路由器的机器上跑 `python cli.py diagnose`(或一次失败的裸跑,
     会自动生成同样的产物)→ artifacts/diagnose_*.json;
  2. 从产物抄"已验证命中数==1"的选择器进下面的 FACTS;
  3. `python models/<新型号>.py dynamic`(默认不点保存)验证回读;
  4. 每个模式过一遍,最后带 --apply 验收。

铁律(别删):
  * 只有真实回读==目标措辞才算 success —— 驱动已内置,别绕过它;
  * 没在真机/产物里观察到的 DOM 不要写进来(宁可留 TODO 让运行失败,
    失败是诚实的;猜出来的"成功"坑过我们两次);
  * 默认不点保存,--apply 才真正下发。

选择器速查(引擎是 Playwright,比纯 CSS 强):
  #someid                      按 id(首选)
  [name='wan_type']            按 name
  button:text-is("Connect")    按钮文字精确匹配(子串碰不到 "Disconnect")
  div.form-row:has-text("Internet Connection Type") div.v-select
                               label 锚定 —— 类名不唯一时的正解(Tenda)
  input:visible                只匹配可见的(两组同名字段只渲染一组时用)
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from models._driver import run_cli

FACTS = {
    "brand": "<品牌>",
    "model": "<型号>",
    "url": "http://192.168.1.1",          # 路由器管理地址

    # -- 登录(整个键可删:没有登录页就不填)---------------------------------
    "login": {
        "password": "input[type=password]",   # 密码框;默认值通常就够
        # "user": "#username",                # 需要用户名的机型才填
        "button": 'button:text-is("Log In")', # 登录按钮;找不到会自动按回车
    },

    # -- 导航:按顺序点击的菜单(默认按"精确文字",前缀 sel: 表示用选择器)---
    "wan_path": ["Internet"],                 # 例:["常用设置", "上网设置"]

    # -- 拨号控件 -------------------------------------------------------------
    # kind: "select"   原生 <select>(被美化插件隐藏也行,驱动会 force)
    #       "dropdown" 自定义下拉:点 trigger 弹出选项再点(combobox/Vue 皆是)
    #       "radio"    单选组:此时 modes 的值填每个模式各自 radio 的选择器
    "dial": {"kind": "dropdown",
             "selector": "<diagnose 产物 pin.recommended 里的选择器>"},

    # -- 各模式在界面上的原文(逐字照抄,失败信息会列出它看到的选项)---------
    "modes": {
        "dynamic": "Dynamic IP",
        "static":  "Static IP",
        "pppoe":   "PPPoE",
        "l2tp":    "L2TP",
        "pptp":    "PPTP",
    },

    # -- 参数输入框(选完模式才挂载,驱动会等)-------------------------------
    "fields": {
        "pppoe_user": "<选择器>",
        "pppoe_pass": "<选择器>",
        "vpn_user":   "<选择器>",
        "vpn_pass":   "<选择器>",
        "vpn_server": "<选择器>",
    },

    # -- 保存/应用按钮(注意 Tenda 叫 "Connect";用 :text-is 精确匹配)-------
    "apply": 'button:text-is("Save")',

    # -- 可选:整个区块被"使能开关"门控时(常见于 IPv6 页)才填 --------------
    # "enable_toggle": "div.v-switch",

    # -- 可选:弹层选项容器的自定义选择器(默认 [role='option'], [class*='opt'])
    # "options": ".my-dropdown-item",

    # -- 可选:某个模式整页不同(IPv6 独立页最常见):按键整个覆盖 ----------
    # "mode_overrides": {
    #     "ipv6": {
    #         "wan_path": ["More", "IPv6"],
    #         "enable_toggle": "div.v-switch",
    #         "dial": {"kind": "dropdown", "selector": "<该页的控件>"},
    #         "modes": {"ipv6": "DHCPv6"},      # v6 flavor 的精确措辞
    #         "apply": 'button:text-is("Save")',
    #     },
    # },
}

if __name__ == "__main__":
    sys.exit(run_cli(FACTS))
