"""假桥接 —— 只复现 tools/routerctrl_bridge.py 的**命令行契约**,离线用。

它**不是** RouterCtrl 的模拟,也不能用来验证桥接本身:那个文件是 py2.6,只有
台架能验(它自己顶部写了 10 步人工验证)。这里假的只有那条边界:

    stdout 只有一行 JSON;退出码 0=成功 / 2=跑完了但判定不过 / 3=参数用错了
    (stdout 完全空)

被测的是 py3 那一侧 —— models/TPLink_RouterCtrl.py 会不会正确解析、会不会在
桥接说"不行"的时候仍然报成功。场景用环境变量 MOCK_BRIDGE 选:

    ok             回读对上、WAN 有地址 -> success true,退出 0
    readback_fail  回读对上但没拨上(wan_ip 空)-> success false,退出 2
                   **这一格是重点**:wan_type 是对的,只有桥接知道它没拨上
    usage          参数用错 -> stdout 什么都不打,退出 3
    noisy          正确的 JSON 前面混几行日志 -> py3 侧必须仍能解析出来
"""
import json
import os
import sys

WAN_TYPE = {"dynamic": "Dynamic IP", "static": "Static IP", "pppoe": "PPPoE",
            "pptp": "PPTP", "l2tp": "L2TP"}


def main():
    argv = sys.argv[1:]
    mode = argv[0] if argv and not argv[0].startswith("-") else ""
    scenario = os.environ.get("MOCK_BRIDGE", "ok")
    if scenario == "usage":
        sys.stderr.write("usage: mode is required\n")
        return 3

    wan_type = WAN_TYPE.get(mode.split("_")[0], "")
    result = {
        "brand": "TPLink", "model": "", "mode": mode,
        "success": False, "read_back": wan_type, "applied": True,
        "filled": ["pppoe_user", "pppoe_pass"], "message": "",
        "warnings": ["status=poor_connected -- informational only."],
        # 型号名就藏在这里:py3 侧要把它填进报告的 model 字段。
        "detail": {"wan_type": wan_type, "wan_ip": "10.11.12.13",
                   "status": "poor_connected", "hostName": "ArcherAX1800"},
    }
    if scenario == "readback_fail":
        result["detail"]["wan_ip"] = ""
        result["message"] = ("read-back failed: wan_ip is empty (no address "
                             "obtained). full get_wan_info() is in detail")
        sys.stdout.write(json.dumps(result, sort_keys=True) + "\n")
        return 2

    result["success"] = True
    if scenario == "noisy":
        # 台架实测:RouterCtrl 自己很吵,JSON 不一定是最后一行之外唯一的行。
        sys.stdout.write("INFO:RouterCtrl:logging in\n")
    sys.stdout.write(json.dumps(result, sort_keys=True) + "\n")
    if scenario == "noisy":
        sys.stdout.write("")
    return 0


if __name__ == "__main__":
    sys.exit(main())
