# vendor/ — 随仓库发布的 Windows 运行时(**不要手改**)

`Vendor/python/` 是一整套**解压即用的 Python 3.8**,依赖已经装在里面。
它被**故意提交进仓库**,因为台架机器有两条硬约束:

1. **不能联网** —— 到了现场没法 `pip install`;
2. **自带的 Python 是 2.x,且不能动** —— 公司自动化和 Chariot 都指着它,
   所以我们不装、不改、不注册任何系统级 Python,只在这个文件夹里活着。

于是使用流程被压到最短:**联网机上从 GitHub 下载 → 拷到台架 → 双击 `start.bat`**。
中间没有安装步骤。

## 里面是什么

| 路径 | 来源 |
|---|---|
| `python/python.exe` 等 | python.org 官方 **embeddable** 包 `python-3.8.10-embed-amd64.zip`(原样解压) |
| `python/python38._pth` | 我们改过:加了 `Lib\site-packages` 和 `import site`,否则嵌入式解释器根本不看装进去的包 |
| `python/Lib/site-packages/` | `requirements.txt` 的依赖(playwright 1.40 / PyYAML / greenlet / pyee / typing_extensions),按 **win_amd64 + cp38** 装的 |

体积约 97 MB,绝大部分是 `playwright/driver/node.exe`(66 MB)—— Playwright 的
驱动是 Node 写的,少了它连不上浏览器。

**注意这里没有浏览器内核。** 工具用 `channel="chrome"` 驱动台架上**已经装好的
Chrome**(见 `engine/browser.py`),所以台架必须有 Chrome;没有的话要单独带
Chrome 的**离线完整安装包**过去,这一条是 Python 怎么摆弄都替代不了的。

## 选 3.8 不是随手选的

3.8 是最后一个还支持 Windows 7 的 CPython;台架是老机器(Chrome 锁在 114),
往上跳版本可能直接起不来。

## 怎么重建

改了 `requirements.txt`、要换 Python 版本、或者台架是 32 位时:

```bash
python3 tools/make_offline_bundle.py                  # 默认 3.8.10 / amd64
python3 tools/make_offline_bundle.py --arch win32     # 32 位台架
```

在**联网**的机器上跑,什么系统都行(脚本用 `pip --platform win_amd64` 抓
Windows 的包,不是本机的),跑完提交 `vendor/`。

## 别做的事

- **别用 Git LFS 存它。** GitHub 的 "Download ZIP" 对 LFS 文件只给指针文件,
  正好会毁掉"下载即用"这个唯一目的。
- **别把 `.venv` 拷进来**(里面写死了原机器的绝对路径)。
- 别手动往 `site-packages` 里塞包 —— 改 `requirements.txt` 然后重建。
