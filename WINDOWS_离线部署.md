# 在公司 Windows 电脑上离线运行（免装 Python、免联网）

这个文件夹已经打包成**自带 Python 3.8 + 所有依赖**的整套东西，
公司电脑上那套被锁定的旧 Python（3.7）完全不用碰、也碰不到。

## 为什么不是直接拷 `.venv`

`.venv` 里写死了**这台 Mac 的绝对路径**，而且装的是 macOS 的二进制文件，
拷到 Windows 根本跑不起来。所以这里改成：把「可搬动的 Python + 离线安装包」
放进文件夹，到了公司电脑上**双击一次 `setup.bat`**，由它在本机现场生成
正确的 `.venv`。生成出来的就是你要的那个 `.venv`，只是由脚本在目标机上建，
而不是从 Mac 拷过去。

## 三步走

1. **整个文件夹拷到公司电脑**（U 盘/共享盘都行）。
   一定要**连 `vendor\` 子文件夹一起拷**——Python 和离线安装包都在里面。
   整包约 **150 MB**。

2. **双击 `setup.bat`**（只需一次）。它会：
   - 用 `vendor\python\` 里自带的 Python 3.8 建一个隔离的 `.venv`；
   - 从 `vendor\wheels\` **离线**装好 playwright、PyYAML 等依赖；
   - 自检导入，打印 `imports OK` 和 `SETUP COMPLETE`。
   全程不联网、不动系统 Python。看到 `SETUP COMPLETE` 就成了。

3. **用 `run.bat` 跑工具**，参数原样传给 `cli.py`。例如：
   ```bat
   run.bat --router-ip 192.168.1.1 --pass 你的管理密码 --mode pppoe ^
           --param pppoe_user=账号 --param pppoe_pass=密码 --no-apply
   ```
   （`--no-apply` = 只定位并切换、**不点保存**，接入调试期一直带着，别断网。）

## 自检（可选）

装好后双击 `smoke.bat` 跑离线端到端自测（需要电脑装了 Chrome）。
预期输出结尾是 `15 passed, 0 failed`。

## 关于浏览器

工具用 `channel="chrome"` 直接驱动**电脑上已安装的 Chrome**，
所以**不需要** `playwright install`、不需要额外下载浏览器内核。
公司机上有 Chrome（你们锁的是 Chrome 114）即可。

## 常见问题

- **双击 `setup.bat` 一闪而过 / 报错**：多半是没把 `vendor\` 一起拷过来。
  重新完整拷贝整个文件夹再试。脚本失败不会动系统环境，修好重跑即可。
- **`run.bat` 说找不到 `.venv`**：先双击一次 `setup.bat`。
- **换一台 Windows 还想用**：把整个文件夹（含 `vendor\`，`.venv` 可删可留）
  再拷过去，重新双击 `setup.bat` 即可。`.venv` 是每台机现场生成的，不要跨机拷。
- **能不能换 64 位以外的机器**：这套 Python 是 Windows 64 位（x86_64）。
  绝大多数公司机都是。如果是 ARM 版 Windows 需另配，找我重打。
