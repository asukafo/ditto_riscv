# v31 同寄存器分支方向

当条件分支的两个源寄存器编号相同，比较结果可以从指令编码确定。BEQ、BGE、BGEU 恒成立，BNE、BLT、BLTU 恒不成立。v31 在两个取指解码槽使用这一规则，仍检查指令合法性和目标对齐。执行阶段继续检查实际结果与异常。普通分支仍用原预测器，窗口预取与历史训练规则保持 v30 的做法。关闭 `EQUAL_BRANCH` 恢复旧路径。

例如 `branch_alias` 中，PC=0x40 的 BEQ 预测到 0x80，后者的 BNE 预测顺序地址 0x84。这两个分支的方向与表项冲突无关。[真实波形采样](results/diagnosis/branch-alias-predictions.csv)

| 同条件指标 | v30 | v31 |
| --- | ---: | ---: |
| 60 组总周期 | 27,005 | 26,503 |
| 寄存器间最小时钟周期 | 10.8169 ns | 10.8984 ns |
| 映射面积 | 373,111.018 | 373,644.082 |
| 热区 960 条的周期数 | 576 | 576 |

六组变快、54 组持平。延迟 5、间隔 3 下，`branch_alias` 从 431 降到 271 周期，误判 34→1。`branch_forward` 从 343 降到 335，误判 4→1。合计周期降 1.86%，按寄存器间下限估计，合计执行时间约降 1.1%。映射面积增加约 0.14%。时序估计使用和 v30 相同的布局前条件。

本轮起点是 `branch_alternating` 的退步。在延迟 5、间隔 3 的 v29/v30 波形中，额外两次误判都在 PC=0x0c。初测发现，把 BHT 更新提前到执行完成能恢复那两次误判，但 `branch_correlated` 退步，整组 27,031 周期。仅旁路最新退休历史也需要 27,032 周期。最终选择可由编码确定的分支方向，交替分支保持 v30 的 439 周期。

[逐条退休和 RAM 对照的性能表](../../results/comparisons/v31-equal-branch/comparison.csv)

完整 ISA、特权、预测、异常、缓存和窗口回归通过。关闭优化后，60 组周期、请求、误判和退休数恢复 v30。

[验证记录](results/v31-equal-branch/validation.json) · [时序报告](results/v31-equal-branch/timing-report.txt)

从仓库根目录可运行 `make test VERSION=v31_equal_branch`、`make timing VERSION=v31_equal_branch CLOCK_NS=10` 及 `make compare BENCHMARK_ARGS="--versions v30_window_cursor v31_equal_branch"`。采样使用延迟 5、间隔 3 的 branch_alias 镜像与 `scripts/equal_branch_waveform.py`。
