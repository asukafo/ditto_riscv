# v38 页内推测游标

取指窗口只有在推测游标留在当前页时才会继续分配表项。v38 用 `spec_page` 和 `spec_offset` 组成当前页内地址，并用 `spec_in_page` 记录更新是否越界。跨页时暂停推测分配，收到下一笔需求取指后可以重新开始。波形回放检查偏移和页内标志，也核对预测表项与响应归属。

| 布局布线前指标 | v35 | v37 | v38 |
| --- | ---: | ---: | ---: |
| 60 组合计周期 | 26,312 | 26,312 | 26,312 |
| 展平寄存器间 setup 下限 | 7.4950 ns | 7.1730 ns | 7.1341 ns |
| 展平含端口约束的 setup 下限 | 8.2523 ns | 7.5358 ns | 7.7135 ns |
| 分层寄存器间 setup 下限 | 10.7328 ns | 9.9814 ns | 9.7575 ns |
| 分层含端口约束的 setup 下限 | 11.5256 ns | 10.4193 ns | 10.4784 ns |
| 展平标准单元面积 | 277,037.404 | 275,975.798 | 273,318.990 |

相对 v35，按展平寄存器间下限估计，整组时间缩短 4.82%。全核展平最慢寄存器路径从 `frontend.next_pc[33]` 到 `forecast_next[0][62]`。端口约束下的时序相对 v37 略退步，根目录仍默认 v37。另两个原型仅在 v36 上改写窗口槽位选择或改用页内游标，展平寄存器路径分别为 7.6926 ns 和 7.8663 ns。[时序及原型记录](results/v38-page-cursor/timing-summary.json) · [展平报告](results/v38-page-cursor/flat-timing.txt) · [分层报告](results/v38-page-cursor/hierarchical-timing.txt)

完整 Verilator 回归及 60 组零延迟门级对照通过。60 组公共用例的周期、退休日志和最终 RAM 与 v37 一致。[公共对照](../../results/comparisons/v38-page-cursor/comparison.csv) · [门级对照](results/v38-page-cursor/gate-equivalence.csv) · [验证记录](results/v38-page-cursor/validation.json)

```sh
make test VERSION=v38_page_cursor
make timing VERSION=v38_page_cursor CLOCK_NS=10
python3 tools/flat_timing.py v38_page_cursor --output .local/timing/v38-flat
```
