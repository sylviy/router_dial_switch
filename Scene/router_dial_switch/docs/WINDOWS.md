# 在 Windows 电脑上安装和使用

**仓库自带一套 Python 3.8**(`Vendor\python\`,约 97 MB,已经装好全部依赖),
所以离线台架上**没有任何安装步骤**:下载 → 拷贝 → 双击 `start.bat`。
台架自己那套 Python 2 从头到尾没被碰过。

---

## 方式 A:离线台架(最常见 —— 不能联网,而且只有不能动的 Python 2)

在**联网的那台机**上:

1. 打开仓库 → 绿色 **Code** 按钮 → **Download ZIP**;
   (或者 `git clone https://github.com/sylviy/router_dial_switch.git`)
2. **右键解压**出来,例如 `D:\router_dial_switch\`;
   ⚠️ 别在压缩包里直接双击运行 —— 一定要先解压。
3. 确认解压后有 **`Vendor\python\python.exe`**。没有它就说明包不完整
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
> 这半边,它跑在 `Vendor\python\` 里。而整轮里跑 Chariot 吞吐的那半边在**那台
> 老台架上**只有 Python 2 能跑(PyChariot 就装在那儿),用 `config.yaml` 的
> `chariot.python` 指向它自己的 `python.exe` 即可。两个解释器各干各的,互不
> 打扰。测吞吐的 `matrix\chariot_perf.py` 本身 Py2 / Py3 都能跑 —— 换成
> Python 3 的台架(日本 IPoE 那套)时 `chariot.python` 留空就行。

## 方式 B:自己的开发机(联网、已有 Python 3.8+)

也可以不用自带运行时,建一个标准 venv:

1. 装 **Python 3.8 或更新**(<https://www.python.org/downloads/windows/>,
   安装第一屏勾上 "Add python.exe to PATH");
2. 删掉或改名 `Vendor\python\`(否则 `setup.bat` 认为已经就绪,直接跳过);
3. **双击 `setup.bat`** —— 用系统 Python 建 `.venv` 并联网装依赖。

`.venv` 存在时所有 `.bat` 都优先用它,没有才回落到 `Vendor\python\`
(这个优先级写在 `_py.bat` 里)。

> 依赖或 Python 版本要升级时,在联网机上跑
> `python3 tools/make_offline_bundle.py` 重建 `Vendor\python\` 再提交,
> 台架那边照旧"下载即用"。细节见 `vendor\README.md`。

---

## 日常怎么用

**双击 `start.bat`**,选型号、选操作。菜单按危险程度排:
1 只看回读不下发 / 2 单档下发(要输 yes)/ 3 整轮 / 4 离线自检 /
5 看看 config.yaml 还差什么。

配置只有一个文件 `config.yaml`,现场用记事本改 —— 换被测机只改
`router.ip` 和 `run.dial_modes`。**不需要提前准备任何别的文件**,
缺什么菜单 5 会连行号一起告诉你。

命令行版(不想走菜单时):

```bat
..\..\Vendor\python\python.exe Models\Cudy_AX1500\Cudy_AX1500.py pppoe          :: 只看回读,不下发
..\..\Vendor\python\python.exe Models\Cudy_AX1500\Cudy_AX1500.py pppoe --apply  :: 真下发
..\..\Vendor\python\python.exe Models\Cudy_AX1500\Cudy_AX1500.py pppoe --perf   :: 整轮
```

- **不加 `--apply` 就不会点保存** —— 调试期这样跑,不会把台架上正在用的
  拨号方式改掉;
- **整轮必定下发**:不下发的话吞吐测的就不是这档模式;
- 报告和截图落在 `artifacts\`。

### 还没适配过的路由器

**双击 `adapt.bat`**,按提示答题即可:它会探测页面 → 生成
`Models\<品牌>_<型号>\` → 离线体检 → 逐个拨号方式真机验证。前几步不改路由器
任何配置,最后才问你要不要真正保存一次。

想手动分步跑(每步都有明确的通过条件;先 `cd Scene\router_dial_switch`):

```bat
call ..\..\Vendor\py.bat & %PY% ..\..\Tools\env_check.py
call ..\..\Vendor\py.bat & %PY% ..\..\Tools\probe_dump.py  --menu "sel:#Network,sel:#WAN"
call ..\..\Vendor\py.bat & %PY% ..\..\Tools\list_modes.py  --menu "..." --dial "#wanType_id"
call ..\..\Vendor\py.bat & %PY% ..\..\Tools\probe_count.py --menu "..." --sel "#wanType_id"
call ..\..\Vendor\py.bat & %PY% ..\..\Tools\act.py  --menu "..." --sel "#wanType_id" --label "PPPoE"
call ..\..\Vendor\py.bat & %PY% ..\..\Tools\act.py  --menu "..." --sel "#wanType_id" --label "PPPoE" --apply-sel "..." --reload-verify
call ..\..\Vendor\py.bat & %PY% tools\make_facts.py  ... --write
call ..\..\Vendor\py.bat & %PY% tools\check_model.py <品牌>_<型号>
```

完整方法论照 `SKILL.md`(把 Claude 接到那台
机上走一遍也行)。产出就是**一个目录**:`Models\<品牌>_<型号>\`,写清这台机
的全部事实(登录、菜单路径、控件选择器、各模式措辞、保存按钮)。拷进
`Models\` 就能用 `start.bat` 了,不需要改任何其它文件。

### 自检(可选,不需要路由器)

```bat
smoke.bat
```
在本机起模拟路由器页跑完整流程,**看结尾的 `0 failed`**(通过数会随用例增减)。需要装 Chrome。

---

## 常见问题

| 现象 | 原因 / 解决 |
|---|---|
| 台架上只有 Python 2,而且不让动 | **不用管它。** 走方式 A:仓库自带的 `Vendor\python\` 是 3.8,和系统那套 2.x 完全无关;Chariot 那半边反而正好要 Py2。 |
| 双击 `setup.bat` 报 `No usable Python found` | 说明 `Vendor\python\` 也不在了(拷贝时漏了)。重新拷完整文件夹;或者装个系统 Python 3.8+ 并勾 "Add python.exe to PATH"。 |
| `setup.bat` 装依赖失败(联网机) | 公司代理拦了 pip。设 `HTTP_PROXY`/`HTTPS_PROXY` 后重试,或直接用自带运行时(方式 A,根本不装)。 |
| `.bat` 报 `No Python 3 runtime found` | 文件夹是**不带 `vendor\`** 拷过来的。重新拷整个文件夹,或双击 `setup.bat` 建 `.venv`。 |
| 报 `imports OK` 之外的导入错误 | `vendor\` 拷坏了(常见于用杀毒软件"清理"过 `node.exe`,或压缩包只解压了一部分)。删掉 `vendor\` 重拷一份。 |
| 菜单里没有你要的型号 | `Models\` 里没有那个型号目录 —— 照 `SKILL.md` 适配一台。 |
| 运行后卡在登录页 / `login failed` | ① 管理密码不对;② 有些机型(Tenda/Mercusys)**同一时间只允许一个 Web 会话** —— 先把浏览器里登录着的路由器页签退出。 |
| 提示缺少宽带账号密码 | 用记事本填 `config.yaml` 的 `router.pppoe_user` / `pppoe_pass`。跑 `start.bat` 菜单 5 会告诉你缺哪几项、在第几行。 |
| 整轮真跑时吞吐格全是 `err` | 台架没装 IxChariot,或 `config.yaml` 的 `bench.python2` 没指到装了 PyChariot 的那个解释器。先把 `run.backend` 设成 `simulate` 确认链路,再配台架。 |
| 换一台 Windows | 整个文件夹拷过去直接双击 `start.bat`(自带运行时是可搬的)。**但 `.venv` 不要跨机拷** —— 里面写死了原机器的绝对路径,拷过去反而会被优先选中然后失败;删掉它即可。 |

## 安全提示

- `config.yaml` 里有管理密码和宽带账号。仓库里那份是**空值模板**;
  台架上填了真密码之后别再提交它。
