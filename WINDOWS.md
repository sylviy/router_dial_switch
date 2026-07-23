# 在 Windows 电脑上安装和使用

两种拿到工具的方式,**装法都是双击 `setup.bat`**,它会自动判断该走哪条路。

---

## 方式 A:从 GitHub 下载(联网机,最常用)

1. 打开仓库 → 绿色 **Code** 按钮 → **Download ZIP**;
   (或者装了 git 就 `git clone https://github.com/sylviy/router_dial_switch.git`)
2. **右键解压**到任意目录,例如 `D:\router_dial_switch\`;
   ⚠️ 别直接在压缩包里双击运行 —— 一定要先解压出来。
3. 确认电脑上有 **Python 3.8 或更新**。没有就去
   <https://www.python.org/downloads/windows/> 装一个,
   安装第一屏**务必勾上 "Add python.exe to PATH"**。
4. 确认装了 **Chrome**(工具直接驱动系统 Chrome,不额外下浏览器内核)。
5. **双击 `setup.bat`**。它会用系统 Python 建一个隔离的 `.venv`,
   再用 pip 联网装依赖(playwright、PyYAML)。看到 `SETUP COMPLETE` 就成了。

## 方式 B:离线 U 盘整包(公司内网机,不能联网)

整包约 150 MB,自带 Python 3.8 和所有依赖,**不碰**公司锁定的旧 Python(3.7)。

1. 整个文件夹拷到目标机,**必须连 `vendor\` 子文件夹一起拷**
   (自带的 Python 和离线安装包都在里面);
2. **双击 `setup.bat`** —— 检测到 `vendor\` 就自动走离线路:用 `vendor\python`
   建 `.venv`,从 `vendor\wheels` 装依赖,全程不联网;
3. 同样看到 `SETUP COMPLETE` 即可。

> 整包怎么做:在一台联网的 Windows 上把 Python 3.8 embeddable 解压进
> `vendor\python\`,再 `pip download -r requirements.txt -d vendor\wheels`。
> `vendor\` 不进 git(150 MB),所以从 GitHub 下载的版本自然没有它 —— 这时
> `setup.bat` 会自动改走方式 A 的联网路。

---

## 日常使用

**最简单:双击 `start.bat`。** 它列出支持的型号,按数字选型号 → 选操作 →
选模式,一路回车就是"只切换不保存"的安全默认;密码/宽带账号问一次可以存进
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
matrix.bat --model Tenda_AX3000      :: 整轮真跑(默认只切换不点保存)
matrix.bat --model Tenda_AX3000 --apply  :: 整轮真跑并真正下发保存
```

- **`dial.bat` 是命令行版切模式**:第一个参数是型号脚本名(`models\` 里的
  文件名去掉 `.py`),后面的参数原样传给它。
- **`matrix.bat` 是整轮命令**(组里性能脚本已合并进来):对配置里的每档拨号
  方式,切模式 → ping 等 WAN 拨通 → 跑吞吐并判稳 → 出自包含 HTML + CSV 报告
  (落在 `artifacts\`)。测什么写在 `perf.yaml`(复制 `perf.example.yaml` 改,
  git 忽略);真跑 Chariot 吞吐要在装了 IxChariot 的台架上,并在 `perf.yaml`
  的 `chariot.python2` 指定台架的 Python 2 解释器;没有台架就用默认的
  `simulate` 后端(离线模拟值,报告里会标明非实测)。
- **不加 `--apply` 就不会点保存** —— 接入调试期一直这样跑,不会把在用的网切断。
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
| 双击 `setup.bat` 报 `No usable Python found` | 没装 Python 或装时没勾 "Add python.exe to PATH"。重装并勾上,或改用离线整包(方式 B)。 |
| `setup.bat` 装依赖失败(联网机) | 公司代理拦了 pip。设 `HTTP_PROXY`/`HTTPS_PROXY` 后重试,或改用离线整包。 |
| `dial.bat` / `run.bat` 说找不到 `.venv` | 先双击一次 `setup.bat`。 |
| `dial.bat` 报 `No such model script` | 型号名拼错了。不带参数跑 `dial.bat` 看可用列表。 |
| 运行后卡在登录页 / `login failed` | ① 管理密码不对;② 有些机型(Tenda/Mercusys)**同一时间只允许一个 Web 会话** —— 先把浏览器里登录着的路由器页签退出。 |
| 提示缺少宽带账号密码 | 先 `run.bat setup` 存进 router.yaml,或本次加 `--param pppoe_user=账号 --param pppoe_pass=密码`。 |
| `matrix.bat` 真跑时吞吐格全是 `err` | 台架没装 IxChariot / `perf.yaml` 的 `chariot.python2` 没指到台架的 Python 2。先用 `--demo` 或 `simulate` 后端确认链路,再配台架。 |
| 换一台 Windows | 整个文件夹拷过去重新双击 `setup.bat`。**`.venv` 不要跨机拷**(里面写死了本机路径),删掉重建即可。 |

## 安全提示

- `router.yaml` 存着管理密码和宽带账号,`perf.yaml` 的 `dial_modes.params`
  里也可能有宽带账密 —— **都已被 git 忽略**,不要提交、不要贴进工单。
- `artifacts\diagnose_*.json` 可能含会话 token 和表单值,也已被 git 忽略;
  回传给别人前先过一眼。
