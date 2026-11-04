# v39 页内窗口预测记录

v38 的展平关键路径从取指 PC 到取指窗口表项保存的后继预测地址高位。取指窗口在使用一个表项的预测之前，已经确认表项地址与当前推测页相同。因此后继地址只需保存 12 位页内偏移与一个同页标志。v39 把四个表项的 64 位后继预测地址换成这两项，保留跨页时停止推测的行为。回放测试分别核对表项偏移、同页标志和响应令牌。

| 布局布线前指标 | v38 | v39 |
| --- | ---: | ---: |
| 60 组合计周期 | 26,312 | 26,312 |
| 展平寄存器间 setup 下限 | 7.1341 ns | 7.5406 ns |
| 展平含端口约束的 setup 下限 | 7.7135 ns | 7.9361 ns |
| 展平标准单元面积 | 273,318.990 | 270,629.464 |
| 分层寄存器间 setup 下限 | 9.7575 ns | 9.7444 ns |
| 分层含端口约束的 setup 下限 | 10.4784 ns | 10.4300 ns |
| 分层标准单元面积 | 367,586.996 | 364,338.870 |

分层时序和面积均改善。展平后全核最慢寄存器路径迁移到 `frontend.next_pc[27]` → `wb_mem_data[10]`，整组估计时间回升。v39 保留为独立的面积和分层时序实验。[时序与工具记录](results/v39-compact-forecast/timing-summary.json) · [展平报告](results/v39-compact-forecast/flat-timing.txt) · [分层报告](results/v39-compact-forecast/hierarchical-timing.txt)

Verilator 完整回归及 60 组零延迟门级对照通过，60 组公共用例的计数、退休日志及最终 RAM 与 v38 一致。[公共用例](../../results/comparisons/v39-compact-forecast/comparison.csv) · [门级对照](results/v39-compact-forecast/gate-equivalence.csv)

```sh
make test VERSION=v39_compact_forecast
make timing VERSION=v39_compact_forecast CLOCK_NS=10
python3 tools/flat_timing.py v39_compact_forecast --output .local/timing/v39-flat
```
