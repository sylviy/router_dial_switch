"""判定与结果格式 —— **全仓库唯一的一份**。

这个文件只回答两个问题:

  1. 一次切换算不算成功?  -> verify()
  2. 成功/失败怎么写下来?  -> result()

型号脚本(models/<品牌>_<型号>.py)怎么点、怎么等、怎么找控件,一律自由;
但**success 这支笔在这里,不在型号脚本手上**。

## 为什么这两件事必须只有一份

切错拨号方式这类错误**失败得静默**:页面照样渲染、截图照样正常、报告照样
出数字,只是那一格测的不是这个模式。别的错(找不到控件、点不动)会当场
报错,这个不会。所以判定放宽一点点(`in` / `startswith` / 忽略大小写的
"包含"),代价不是一条报错,而是一份看起来完全正常、其实测错了对象的报告。

真机上踩过的那一条:`"PPPoEv6"` 里包含 `"PPPoE"`。用子串判定时,一台
只切到 PPPoEv6 的机器会被判成 PPPoE 切换成功。

## 用法(型号脚本视角)

    from common import contract

    got = read_back_from_the_page()          # 控件自己显示的当前值
    return contract.result(contract.verify(got, want), got, want)

失败路径同样只能走 verify():

    return contract.result(contract.verify("", want), "", want,
                           message="登录失败:仍停在登录页")

`verify("", ...)` 永远是假 —— 空回读不是通过,是"什么都没读到"。
"""
from __future__ import annotations

from typing import Optional

__all__ = ["Verdict", "verify", "result", "ContractError"]


class ContractError(TypeError):
    """把 success 写成字面量、或 success 与回读对不上时抛出。"""


class Verdict(int):
    """`verify()` 的返回值:一个能当布尔用、但**不是**字面量 True 的判定。

    `bool` 不能被继承,所以这里用 int 子类。它在 `if` / `and` / `==` 里的
    行为和 True/False 完全一样,唯一的区别是 `result()` 能认出它 ——
    于是"success 只能由一次真实回读算出来"变成**类型系统拦得住**的规矩,
    而不是一句只能靠人自觉的注释。
    """

    __slots__ = ()

    def __repr__(self) -> str:            # pragma: no cover - 只为可读性
        return "Verdict(%s)" % bool(self)

    def __str__(self) -> str:             # pragma: no cover
        return str(bool(self))


def _norm(text: Optional[str]) -> str:
    """规整空白与大小写:首尾去掉,内部的连续空白/换行折成一个空格。

    折叠内部空白是**重构前就在真机上跑了几个月的行为**(旧的
    引擎里那个 _norm),这里原样保留 —— 界面措辞里带个换行或双空格的
    机型(`"PPPoE  拨号"`),严格按首尾规整会把它判成失败,而那种失败只有
    重上台架才发现得了。

    折叠的是空白,不是把判定放宽:`"PPPoEv6"` 和 `"PPPoE"` 折完还是两个不同
    的串,照样判假。危险的方向一步都没让。
    """
    return " ".join((text or "").split()).lower()


def verify(read_back, expected) -> Verdict:
    """回读值等于目标措辞吗?**唯一的判定**,全仓库只有这一处。

    规整首尾空白与大小写后【精确相等】。

    空 read_back 永远返回假 —— 两个空串规整后也相等,但那是"什么都没读到",
    不是通过。绝不放宽成 in / startswith / 模糊匹配:`"PPPoEv6"` 包含
    `"PPPoE"`,放宽一次就等于允许一份测错对象的报告。
    """
    got = _norm(read_back)
    if not got:
        return Verdict(0)
    return Verdict(got == _norm(expected))


def result(success, read_back, expected, message: str = "",
           screenshot: Optional[str] = None,
           brand: str = "", model: str = "", mode: str = "",
           applied: bool = False, filled=None, warnings=None) -> dict:
    """**唯一的结果构造器。** 别处不许再拼带 success 的字典。

    success 只接受 `verify()` 的返回值(Verdict),外加字面量 `False`
    —— 后者是给"还没碰到回读就已经失败"的路径用的(登录失败、缺账密),
    它只会把结果判成失败,伪造不出成功。传字面量 `True` 直接抛
    ContractError。

    还会再核一次:success 为真时,`verify(read_back, expected)` 必须同样为真。
    这挡住"拿 A 的回读算判定、把 B 写进报告"这种手滑。

    返回的字段和重构前那份结果字典一致(报告读的就是
    它):brand / model / mode / success / read_back / filled / applied /
    message / warnings / screenshot,另加一个 expected(失败时的证据,报告
    不读它)。
    """
    if isinstance(success, Verdict):
        ok = bool(success)
    elif success is False:
        ok = False
    else:
        raise ContractError(
            "result(success=%r):success 只能是 contract.verify() 的返回值"
            "(或字面量 False)。写 True 就等于绕过回读判定 —— 这正是这个"
            "文件存在的理由。改成 contract.result(contract.verify(got, want),"
            " got, want, ...)。" % (success,))

    if ok and not verify(read_back, expected):
        raise ContractError(
            "result():success 为真,但 read_back=%r 和 expected=%r 对不上。"
            "判定用的回读和写进报告的回读必须是同一个。"
            % (read_back, expected))

    got = "" if read_back is None else str(read_back)
    want = "" if expected is None else str(expected)
    if not ok and not message:
        message = ("回读没通过:控件当前显示 %r,目标是 %r"
                   "(精确相等比对,不放宽成包含)" % (got.strip(), want))
    return {
        "brand": brand,
        "model": model,
        "mode": mode,
        "success": ok,
        "read_back": got.strip(),
        "expected": want,
        "filled": list(filled or []),
        "applied": bool(applied),
        "message": message,
        "warnings": list(warnings or []),
        "screenshot": screenshot or "",
    }
