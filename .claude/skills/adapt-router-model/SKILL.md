---
name: adapt-router-model
description: 为一台新路由器型号产出专属拨号切换脚本 models/<品牌>_<型号>.py,并验证到能跑整轮性能测试。触发场景:适配新型号 / 接入新路由器 / 加一台 Buffalo(Huawei/…)/ onboard a new router model / add router model / 生成 Tenda_XXX.py 这类脚本 / 某型号登录不进去或切换不成功要修 FACTS。输入:一台能访问到的路由器(同局域网),或用户回传的一份控件清单。
---

# 适配一台新路由器型号

产出一个 `models/<品牌>_<型号>.py`(FACTS + 转调默认配方的三行 `run()`)。
放进 `models/` 就完事,没有注册表要改。逐键说明见 `reference.md`。

## 铁律

1. **不猜没观察过的 DOM**,每个选择器 `--count` 实测 ==1。宁可留 `TODO`。
2. **只有回读 == 目标措辞才算成功**,永不放宽成子串("PPPoEv6" 会被认成 "PPPoE")。
3. **命中 1 ≠ 选对了** —— 唯一命中的诱饵照样是诱饵,见下面两个 ⛔。
4. **默认不点保存**;用户点头才 `--apply`。切错会断网。
5. **凭据不进仓库**(走 `router.yaml`,已 git 忽略)。

## 开工两件事

**一、读 `artifacts/progress_<品牌>_<型号>.md`**(不存在 = 全新开始)。上下文随时
被压缩,进度在磁盘上。每步追加一行:`nav= py= dump= facts= count= check= live=
next=`。压缩后**从 `next=` 继续,别重新探测**。**重跑 `--emit` 会覆盖你手改的
FACTS**;重跑 `--apply` 会真改设备。型号名全程同一个字符串。

**二、定 python。别直接敲 `python`** —— 台架那个是不能动的 Python 2,只会得到
`No module named 'playwright'`,而那不是适配问题。逐条试,谁先打印版本号就用谁,
记进 `py=`(下文 `<PY>` 换成它);四条全败就如实报告,**别自己 pip install**:

```
vendor/python/python.exe -c "import playwright,sys;print(sys.version)"
.venv/Scripts/python.exe -c "import playwright,sys;print(sys.version)"
.venv/bin/python -c "import playwright,sys;print(sys.version)"
python3 -c "import playwright,sys;print(sys.version)"
```

## 三轮命令

**先在 `reference.md` 的「各 UI 家族特有的坑」里找最像的一行** —— 它告诉你抄哪个
脚本、会踩什么。像已知家族就先白试一次自动生成(不花 token,成了跳第 3 轮);
都不像就直接从第 1 轮开始,别在自动生成上浪费时间。每条命令写成一行。

**第 1 轮:探到页面 + 抄下来**

```
curl -m 4 http://<ip>
<PY> tools/probe_router.py --dump --url http://<ip> --pass <密码> --nav "<设置页菜单文字>" > artifacts/inventory_<品牌>_<型号>.txt
```

- **读那个清单**(一行一个控件),**别看页面源码**;存盘不能省,压缩后只剩它。
- 拨号控件没出现 = 还停在首页,补 `--nav`(前缀 `sel:` = 用选择器)重跑。
- 登录不上 → `--login-pass` / `--login-btn`,从探针打的登录页诊断里挑,别猜。
- **账密框看不到是正常的**(很多 UI 选完档才挂载);看得见的输入框也未必是拨号
  用的(同页 VPN/无线也有 Username/Password,**填错就是假成功**)→ 用
  `--probe-modes --emit` 逐档抄。

**第 2 轮:写 FACTS,一次验完所有选择器**

```
<PY> tools/probe_router.py --url http://<ip> --pass <密码> --nav "..." --count "<拨号控件>" --count "<保存键>" --count "<账密框1>" --count "<账密框2>"
```

命令行上的选择器**内单引号、外双引号**(理由见 `reference.md`)。
**命中数不是 1 就不能用**,不唯一先试这两条收窄法:

```
form:has(<拨号控件>) <按钮>                     # 一页多段、每段一个保存键
div.<行class>:has-text("<标签文字>") <控件>     # 类名不唯一,用标签锚定
```

### ⛔ 停下来问(命中 1 之后,写死 FACTS 之前)

`--count` 只证明「页面上只有这一个」,**不证明「这一个是对的」**。你读的是可访问
性树不是像素,它三处骗你:无 role 的自绘下拉分不清拨号方式和 MTU;隐藏但存在的
诱饵;懒渲染(没展开的下拉在树里不存在 → 误判成「这台机没这功能」)。

**用路由器语言问,不要用选择器语言问。** ❌「`div.v-select` 命中 1,是否采用?」
—— 用户答不了。✅ 这样问:

> 我在 Internet Settings 页面看到一个下拉框,当前显示 **Dynamic IP**,展开后有
> PPPoE / Dynamic IP / Static IP。同页还有 4 个长得一样的下拉框:MTU、MAC
> Clone、DNS。我认定第一个是拨号方式选择器。
> 保存按钮我认定是右下角的「Save」;页面上另有一个「Connect」,我判断那是手动
> 重连、不是保存。**这两条对吗?**

「同页还有几个长得一样的」从第 1 轮的清单里数,不用再跑命令。

**第 3 轮:体检 + 逐模式真机验证**

```
<PY> tools/check_model.py <品牌>_<型号>
<PY> models/<品牌>_<型号>.py dynamic
<PY> models/<品牌>_<型号>.py pppoe
```

`success:true` 且 `read_back` 正是目标措辞才算过。失败信息会列出它当时看到的
选项和按钮 —— 照着改,别重新猜。

### ⛔ 真机验收也是关卡

**逐模式把「回读值 + 截图」摆给用户,等他确认,才允许 `--apply`。** 别自己判断
"看起来对了就下发"。之后告诉用户还要配 `perf_configs/<型号>.yaml` 的
`dial_modes`(**排除 `static`**)、`wan_up.hosts`(按模式)、`nofrag_bytes`,
以及 `router.yaml` 的 `params[<模式>]`(L2TP/PPTP 字段名相同、账号不同,
**必须分模式存**)。

## 卡住了 / 收尾

**卡住了先分四类** —— 崩溃、登录、**定位**(便宜)、**形态**(贵)。分诊表、
探针吃不下什么、以及怎么加新动词,都在 `reference.md`。
**验收通过后要把这台的坑写回 `reference.md`** —— 那是唯一会累积的东西,
规矩也在那一节。

## 成本纪律

一台设备预算:输入 ~1500 token,输出 ~500。**不要读** `models/_driver.py`、
`GOTCHAS.md` 全文、`probe_*.json`、`*.png`、`reference.md` 全文(只读要的那节)。
只输出 FACTS dict,别逐行打印脚本。**`adapt.py` 是给人的向导,别调用也别改。**
每轮多跑几条命令再汇报。
