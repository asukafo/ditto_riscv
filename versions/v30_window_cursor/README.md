# v30 取指窗口页内游标

在 `branch_forward` 的热循环里，取指反复经过 0x08、0x10 和 0x18。v29 的游标每拍只走过一个已登记槽位。在前端连续消耗返回时，游标可能花掉分配下一槽所需的一拍，下一条需求因此重新定向。旧版计数的 55 次丢弃有 50 次恰好也是当前需求的旁路消费，不能把这些返回都视作浪费。

v30 可沿已登记的预测后继先走两步，再决定分配位置。把槽位所在页的比较提前并行完成，串行查找只经过 12 位页内偏移。只允许同页、有效、未毒化、宽度匹配的槽参与查找，任何预测后继越页则回退到原游标。需求地址匹配、冲刷、令牌与响应归属沿用 v29。关掉 `CURSOR_SKIP` 可对照。

[真实波形采样](results/diagnosis/branch-forward-window.csv)中，第 58 拍游标从 0x18 沿两个已有后继找到 0x10。选中的槽也已存在，硬件读取它登记的下一地址。第 59 拍可以分配 0x18，下一拍真实需求到来时已经命中该槽。独立回放模型从原始槽位和预测记录重算游标。

## 周期与时序

| 同条件指标 | v29 | v30 |
| --- | ---: | ---: |
| 60 组合计周期 | 27,294 | 27,005 |
| 寄存器间最小时钟周期 | 10.8690 ns | 10.8169 ns |
| 总周期 × 寄存器间时钟下限 | 296.66 µs | 292.11 µs |
| 标准单元映射面积 | 370,905.612 | 373,111.018 |

相同 Nangate45 typical、Yosys 和 OpenSTA 约束下，估计合计执行时间降低 1.53%，面积增加 0.59%。早期试验用完整地址串行查找，同样省 289 周期，但最小时钟周期升至约 11.14 ns。页内偏移改写保住了周期收益。以上时序均为布局前估计。

60 组有 9 组更快、48 组持平、3 组更慢。延迟 5、间隔 3 时，`branch_forward` 从 371 降到 343，低于 v24 的 347。X 完成但前端无指令可接续从 96 拍降到 66 拍。误判仍为 4 次，外部请求仍为 9 次。相同条件下，`data_reuse` 从 667 降到 607，`branch_alternating` 从 431 增到 439。热循环稳定区间保持 960 条 / 576 周期。

[逐条退休和 RAM 对照后的周期表](results/diagnosis/verified-cycles.csv)

完整回归、逐条退休与 RAM 对照、Verilator lint、映射结构检查均通过。关闭游标优化后，60 组周期、物理请求数、误判数和退休数均恢复到 v29。[公共比较](../../results/comparisons/v30-window-cursor/comparison.csv) · [验证记录](results/v30-window-cursor/validation.json) · [时序报告](results/v30-window-cursor/timing-report.txt)

从仓库根目录运行以下命令复现。

```sh
make test VERSION=v30_window_cursor
make timing VERSION=v30_window_cursor CLOCK_NS=10
make compare BENCHMARK_ARGS="--versions v24_dual_alu v29_ifill_turnover v30_window_cursor"
```

使用 v30 整核模拟器运行 `branch_forward` 镜像并记录 VCD，内存延迟 5、间隔 3。在本版本目录运行 `python3 scripts/cursor_waveform.py <VCD>` 可重建采样。
