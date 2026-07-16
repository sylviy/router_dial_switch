---
name: adapt-router-model
description: 为一台新路由器型号产出专属拨号切换脚本 models/<品牌>_<型号>.py。触发场景:适配新型号 / 接入新路由器 / onboard a new router model / 生成 Tenda_XXX.py 这类脚本 / 拿到一份 diagnose 产物要写脚本。输入:能访问路由器的测试台,或一份 artifacts/diagnose_*.json。
---

# 适配一台新路由器型号

## 目标与产出

产出**一个自包含的型号脚本** `models/<品牌>_<型号>.py`:文件顶部是这台机的全部
"事实"(FACTS:登录、菜单路径、控件选择器、各模式措辞、保存按钮),同事拿到后
`python models/<品牌>_<型号>.py pppoe` 即可切拨号方式。点击逻辑在共用的
`models/_driver.py` 里,**不要**为单个型号改驱动。

组内目标品牌:Cudy / Tenda / Buffalo / Huawei(已完成:Tenda、Mercusys,照它们抄)。

## 铁律(先读,违反任何一条 = 返工)

1. **不猜没观察过的 DOM。** 每个选择器必须来自 diagnose 产物、真机页面或用户
   回传的控制台输出。宁可留 TODO 让运行诚实地失败,也不写"大概是这样"的选择器
   ——猜出来的"成功"在真机上坑过我们两次(小米假成功、误点"应用")。
2. **只有真实回读==目标措辞才算成功。** 驱动已内置该判定,不要绕过、不要放宽成
   子串匹配("PPPoEv6" 会被认成 "PPPoE")。
3. **默认不点保存。** 验证阶段一律不带 `--apply`;所有模式回读都对了,才带
   `--apply` 做最后验收。切错模式会断网,别在承载真实上网的路由器上验收。
4. **凭据不进仓库。** 管理/宽带密码放 router.yaml(git 已忽略);diagnose 产物和
   HAR 可能含会话 token,回传/贴工单前先脱敏。

## 流程

### 第 1 步:取证(唯一的信息来源)

能访问路由器时,在测试台上:

```bash
python cli.py setup        # 一次性:IP/密码写进 router.yaml
python cli.py diagnose     # -> artifacts/diagnose_*.json
```

**中继模式**(你拿不到路由器):请用户跑上面两条并回传
`artifacts/diagnose_*.json`(提醒脱敏);用户连 Python 都没有时,让其把
`tools/find_dial_selector.js` / `tools/find_enable_toggle.js` 贴进浏览器控制台,
回传输出。在此之前**不要动笔写 FACTS**。

### 第 2 步:读产物,对号入座

产物里可直接抄的字段:

| 产物里看什么 | 写进 FACTS 哪里 |
|---|---|
| `dial_candidates[].pin.recommended`(已验证命中数==1) | `dial.selector`;native `<select>` → `kind: "select"`,其余 → `"dropdown"` |
| 候选控件的 options / 页面模式措辞 | `modes:`(逐字照抄,含大小写空格) |
| `save_button` 命中的按钮文字 | `apply: 'button:text-is("<原文>")'`(精确匹配,防 "Disconnect" 类诱饵) |
| `toggles[]` 里 state=False 的开关(页面空空如也时) | `enable_toggle`(常见于 IPv6 独立页,配 `mode_overrides`) |
| 登录页密码框/按钮 | `login:`(默认 `input[type=password]` 通常够用) |
| URL 停在首页 / 0 控件 | 缺导航:`wan_path: ["菜单文字", ...]` |

选择器写法速查(Playwright 语法,比纯 CSS 强):`#id` 首选;类名不唯一时用
label 锚定 `div.form-row:has-text("Internet Connection Type") div.v-select`
(Tenda 正解);两组同名字段只渲染一组时加 `input:visible`;按钮一律
`:text-is()` 精确匹配。

### 第 3 步:写脚本

```bash
cp models/_template.py models/<品牌>_<型号>.py
```

照模板注释逐项填;某模式整页不同(IPv6 最常见)用 `mode_overrides`。没证据的
项**留 TODO 注释**,不要编。凡是"按截图/同源结构建模、未二次确认"的行,标
`[待真机复核]`(参考 Tenda_AX3000.py 的写法)。

### 第 4 步:验证(默认不点保存)

```bash
python models/<品牌>_<型号>.py dynamic          # 看 JSON:success + read_back
python models/<品牌>_<型号>.py pppoe            # 账密来自 router.yaml
# ... 每个 modes 里的模式都过一遍
```

失败时 `message`/`warnings` 会指明卡在哪一项(菜单没找到 / 控件没找到 / 选项
措辞不对 / 输入框没出现);回到产物修正对应 FACTS 项再跑。全部回读正确后,带
`--apply` 验收一次。

### 第 5 步:固化(可选但推荐)

把 diagnose 产物里的页面结构做成 `tests/mock_router/<品牌>.html`,在
`tests/smoke_test.py` 的 models 段加一条用例 —— 这台型号从此有离线回归,
别人改驱动不会悄悄弄坏它。跑 `python tests/smoke_test.py` 必须全绿。

## 边界

- 卡片条/分段选择器、值文本不是模式词的控件、确认弹窗、closed shadow DOM:
  现有 `_driver.py` 吃不下,见 CLAUDE.md「Known gaps」。遇到先如实报告,
  不要硬造 FACTS;真需要时在 `_driver.py` 加新 `kind` 并配 mock 用例。
- 本 skill 只管"切拨号方式";连通性/吞吐验证走 `verify_hook`(接口已留)。
