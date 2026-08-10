"""型号脚本模板 —— 复制成 models/<品牌>_<型号>.py 后逐项填 FACTS。

**多数情况下不用手抄这个模板**:探针能直接生成填好的骨架 ——
    python tools/probe_router.py --url http://<ip> --pass <管理密码> \\
        --brand <品牌> --model <型号> --emit models/<品牌>_<型号>.py
手写时照下面逐项填。完整方法论见 .claude/skills/adapt-router-model/SKILL.md,
每个键的详细说明见同目录的 reference.md。

产出流程:
  1. `python tools/probe_router.py ...` 取证 → artifacts/probe_*.json
     (只读:登录、抄控件、**用 Playwright 引擎实测每个候选选择器的命中数**,
      绝不点保存);
  2. 从产物抄"命中数==1"的选择器进下面的 FACTS;
  3. `python tools/check_model.py <型号>` 离线体检(残留 TODO、缺字段、
     措辞撞车、选择器语法错都会被拦下);
  4. `python models/<新型号>.py dynamic`(默认不点保存)验证回读;
  5. 每个模式过一遍,最后带 --apply 验收。

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

# 这一行每个型号脚本都要自己写一遍,**不能抽成共享模块** —— 它要解决的正是
# "还没法 import 仓库里的东西"这个状态:直接 `python models/X.py` 时 Python 把
# models/ 加进 sys.path,不是仓库根;而台架的 vendor/python 带 ._pth,解释器处于
# isolated 模式,连脚本目录都不加。两种情况都要求 insert 写在本文件、import 之前。
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from models._driver import default_run, run_cli

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
    #       value: 可选的回读子选择器(触发器文字常混着下拉小箭头等杂质)
    "dial": {"kind": "dropdown",
             "selector": "<探针产物 pin.recommended 里的选择器>"},

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

    # -- 根本不走 Web UI 的机型(有 HTTP API / 只能靠 py2 桥接)------------
    # 这个模板剩下的键**一个都不填**(它们全是选择器),换成三样:
    #     "route": "bridge",                       # 不开浏览器
    #     "bridge": "tools/routerctrl_bridge.py",  # 下发+回读的那个子进程
    #     "modes": {"dynamic": "Dynamic IP", ...}  # 值是**回读串**,不是措辞
    # 地址和凭据不写在这里(router.yaml)。run() 自己拼动词:
    # 桥接下发 → record_applied() → record_verified(回读, s.label) →
    # apply_and_verify()。完整的一台见 models/TPLink_RouterCtrl.py,
    # 判定规矩没变:success 仍然只从 apply_and_verify() 出来。
}


def run(facts=None, mode="dynamic", **kw):
    """这台机的操作配方:标准流程(登录 → 走菜单 → 选模式 → 回读 →
    填账密 → 保存)。逐步说明见 models/_driver.default_run。"""
    return default_run(facts or FACTS, mode, **kw)


if __name__ == "__main__":
    sys.exit(run_cli(FACTS, runner=run))
