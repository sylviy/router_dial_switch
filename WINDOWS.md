# 在 Windows 电脑上安装和使用

**仓库自带一套 Python 3.8**(`vendor\python\`,约 97 MB,已经装好全部依赖),
所以离线台架上**没有任何安装步骤**:下载 → 拷贝 → 双击 `start.bat`。
台架自己那套 Python 2 从头到尾没被碰过。

---

## 方式 A:离线台架(最常见 —— 不能联网,而且只有不能动的 Python 2)

在**联网的那台机**上:

1. 打开仓库 → 绿色 **Code** 按钮 → **Download ZIP**;
   (或者 `git clone https://github.com/sylviy/router_dial_switch.git`)
2. **右键解压**出来,例如 `D:\router_dial_switch\`;
   ⚠️ 别在压缩包里直接双击运行 —— 一定要先解压。
3. 确认解压后有 **`vendor\python\python.exe`**。没有它就说明包不完整
   (比如从别人手里拿的裁剪版),别往台架搬。

拷到台架(U 盘/内网盘都行,**整个文件夹一起拷**),然后:

4. 确认台架装了 **Chrome**。工具驱动的是系统里已装好的 Chrome
   (`channel="chrome"`),仓库里**不带**浏览器内核 —— 没有就从联网机带一个
   **Chrome 离线完整安装包**过去(官网默认下的那个是在线下载器,离线机上没用)。
5. **双击 `start.bat`**,直接开始用。

不需要 `setup.bat`,不需要联网,不需要管理员权限,也不会新增系统级 Python。
想确认环境没问题的话,双击一次 `setup.bat` —— 它认出自带运行时后只做校验、
不装任何东西,打印 `imports OK` + `SETUP COMPLETE` 就走人。

> **为什么台架的 Python 2 不碍事:** 需要 Python 3.8 的只有"点浏览器切拨号"
> 这半边,它跑在 `vendor\python\` 里。而整轮里跑 Chariot 吞吐的那半边**本来
> 就要 Python 2**(`perf.yaml` 的 `chariot.python2`,指向台架自己的
> `python.exe`)。两个解释器各干各的,互不打扰。

## 方式 B:自己的开发机(联网、已有 Python 3.8+)

也可以不用自带运行时,建一个标准 venv:

1. 装 **Python 3.8 或更新**(<https://www.python.org/downloads/windows/>,
   安装第一屏勾上 "Add python.exe to PATH");
2. 删掉或改名 `vendor\python\`(否则 `setup.bat` 认为已经就绪,直接跳过);
3. **双击 `setup.bat`** —— 用系统 Python 建 `.venv` 并联网装依赖。

`.venv` 存在时所有 `.bat` 都优先用它,没有才回落到 `vendor\python\`
(这个优先级写在 `_py.bat` 里)。

> 依赖或 Python 版本要升级时,在联网机上跑
> `python3 tools/make_offline_bundle.py` 重建 `vendor\python\` 再提交,
> 台架那边照旧"下载即用"。细节见 `vendor\README.md`。

---

## 日常使用

**最简单:双击 `start.bat`。** 它列出支持的型号,按数字选一台,回车 ——
默认就是整轮:**遍历该型号的全部拨号方式,每档真切换 → 等 WAN → 测吞吐 →
出报告**(台架语义,不问"要不要保存")。密码/宽带账号问一次存进
`router.yaml`,以后全程回车。**不需要提前准备任何文件。**

命令行版(想脚本化/传参数时):

```bat
run.bat setup                        :: 一次性:存路由器 IP / 管理密码 / 宽带账号
                                     ::   (写进 router.yaml,本机文件,不进仓库)

dial.bat Tenda_AX3000 dynamic        :: 切模式,只切换不保存(先看回读)
dial.bat Tenda_AX3000 pppoe --apply  :: 确认无误后,真正下发保存
dial.bat Cudy_AX l2tp --apply

dial.bat                             :: 不带参数 = 列出有哪些已适配的型号

matrix.bat --demo                    :: 整轮演示:不碰路由器,出样例 HTML 报告
matrix.bat --model Tenda_AX3000      :: 整轮真跑:自动遍历该型号的全部拨号方式,
                                     ::   每档真正下发并测吞吐(整轮没有 --apply)
```

- **`dial.bat` 是命令行版切模式**:第一个参数是型号脚本名(`models\` 里的
  文件名去掉 `.py`),后面的参数原样传给它。
- **`matrix.bat` 是整轮命令**(组里性能脚本已合并进来):对配置里的每档拨号
  方式,切模式 → ping 等 WAN 拨通 → 跑吞吐并判稳 → 出自包含 HTML + CSV 报告
  (落在 `artifacts\`)。测什么写在 `perf.yaml`(复制 `perf.example.yaml` 改,
  git 忽略);真跑 Chariot 吞吐要在装了 IxChariot 的台架上,并在 `perf.yaml`
  的 `chariot.python2` 指定台架的 Python 2 解释器;没有台架就用默认的
  `simulate` 后端(离线模拟值,报告里会标明非实测)。
- **`dial.bat` 不加 `--apply` 就不会点保存** —— 单模式调试期这样跑,不会把在
  用的网切断。整轮(`start.bat` / `matrix.bat`)是台架语义:每档都真正下发。
- 输出是一段 JSON:看 `success` 和 `read_back`(界面回读到的实际值)是否等于
  你要的模式;失败时 `message` / `warnings` 会指出卡在哪一步。

### 还没适配过的路由器

```bat
run.bat diagnose                     :: 生成证据产物 artifacts\diagnose_*.json
run.bat pppoe                        :: 纯启发式碰运气,常见 UI 能直接成
```

把产物交给 Claude(或照 `.claude\skills\adapt-router-model\SKILL.md` 自己来),
产出该型号的 `models\<品牌>_<型号>.py`,之后就能用 `dial.bat` 了。

### 自检(可选,不需要路由器)

```bat
smoke.bat
```
在本机起模拟路由器页跑完整流程,预期结尾 `40 passed, 0 failed`。需要装 Chrome。

---

## 常见问题

| 现象 | 原因 / 解决 |
|---|---|
| 台架上只有 Python 2,而且不让动 | **不用管它。** 走方式 A:仓库自带的 `vendor\python\` 是 3.8,和系统那套 2.x 完全无关;Chariot 那半边反而正好要 Py2。 |
| 双击 `setup.bat` 报 `No usable Python found` | 说明 `vendor\python\` 也不在了(拷贝时漏了)。重新拷完整文件夹;或者装个系统 Python 3.8+ 并勾 "Add python.exe to PATH"。 |
| `setup.bat` 装依赖失败(联网机) | 公司代理拦了 pip。设 `HTTP_PROXY`/`HTTPS_PROXY` 后重试,或直接用自带运行时(方式 A,根本不装)。 |
| `.bat` 报 `No Python 3 runtime found` | 文件夹是**不带 `vendor\`** 拷过来的。重新拷整个文件夹,或双击 `setup.bat` 建 `.venv`。 |
| 报 `imports OK` 之外的导入错误 | `vendor\` 拷坏了(常见于用杀毒软件"清理"过 `node.exe`,或压缩包只解压了一部分)。删掉 `vendor\` 重拷一份。 |
| `dial.bat` 报 `No such model script` | 型号名拼错了。不带参数跑 `dial.bat` 看可用列表。 |
| 运行后卡在登录页 / `login failed` | ① 管理密码不对;② 有些机型(Tenda/Mercusys)**同一时间只允许一个 Web 会话** —— 先把浏览器里登录着的路由器页签退出。 |
| 提示缺少宽带账号密码 | 先 `run.bat setup` 存进 router.yaml,或本次加 `--param pppoe_user=账号 --param pppoe_pass=密码`。 |
| `matrix.bat` 真跑时吞吐格全是 `err` | 台架没装 IxChariot / `perf.yaml` 的 `chariot.python2` 没指到台架的 Python 2。先用 `--demo` 或 `simulate` 后端确认链路,再配台架。 |
| 换一台 Windows | 整个文件夹拷过去直接双击 `start.bat`(自带运行时是可搬的)。**但 `.venv` 不要跨机拷** —— 里面写死了原机器的绝对路径,拷过去反而会被优先选中然后失败;删掉它即可。 |

## 安全提示

- `router.yaml` 存着管理密码和宽带账号,`perf.yaml` 的 `dial_modes.params`
  里也可能有宽带账密 —— **都已被 git 忽略**,不要提交、不要贴进工单。
- `artifacts\diagnose_*.json` 可能含会话 token 和表单值,也已被 git 忽略;
  回传给别人前先过一眼。
