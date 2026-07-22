#!/usr/bin/env python3
"""WAN 性能矩阵 —— 一条命令跑完"切拨号方式 → 等 WAN → 测吞吐 → 出报告"。

    python run_matrix.py --list                        列出已适配型号
    python run_matrix.py --demo                         离线演示(不碰路由器)
    python run_matrix.py --model Tenda_AX3000           真跑(默认只切换不点保存)
    python run_matrix.py --model Tenda_AX3000 --apply   真跑并真正下发保存

细节见 matrix/run.py 和 perf.example.yaml。
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from matrix.run import main

if __name__ == "__main__":
    sys.exit(main())
