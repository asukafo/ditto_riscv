# v41 页内预测目标校验

双槽预取只有在预测目标仍在当前页时才使用该预测。v41 用回包指令的页内 PC 加带符号的分支或 JAL 偏移，并同时检查结果仍在页内、低 12 位与预测一致。预测后回包指令改变时，即使新目标的低 12 位相同，只要跨页就拒绝旧预测。上半槽的 PC 由当前包地址将 bit 2 置 1 得到。窄取指和关闭页内重定向的配置保留完整地址校验。

## 布局布线前时序

| 指标 | v35 | v40 | v41 |
| --- | ---: | ---: | ---: |
| 60 组合计周期 | 26,312 | 26,312 | 26,312 |
| 展平寄存器间 setup 下限 | 7.4950 ns | 7.1240 ns | 7.0482 ns |
| 展平含端口约束的 setup 下限 | 8.2523 ns | 7.6422 ns | 7.8034 ns |
| 周期 × 展平寄存器间下限 | 197.21 µs | 187.45 µs | 185.45 µs |
| 展平标准单元面积 | 277,037.404 | 270,037.614 | 268,668.246 |
| 分层寄存器间 setup 下限 | 10.7328 ns | 9.5255 ns | 9.3970 ns |
| 分层含端口约束的 setup 下限 | 11.5256 ns | 10.2111 ns | 10.3188 ns |
| 分层标准单元面积 | 372,419.152 | 364,372.918 | 362,499.746 |

相对 v35，同一套公共用例的布局前估计时间缩短 5.96%，分层寄存器间 setup 下限低于 10 ns。v41 作为默认版本。含端口约束的两项时序比 v40 略慢，分层映射仍有 10 ns setup 违例。展平最慢寄存器路径从 `frontend.next_pc[62]` 到 `wb_mem_write`。报告使用同一 Nangate45 typical 单元库、ABC 负载和 OpenSTA 约束。[展平报告](results/v41-page-target/flat-timing.txt) · [分层报告](results/v41-page-target/hierarchical-timing.txt) · [时序与工具记录](results/v41-page-target/timing-summary.json)

## 验证

完整 Verilator 回归通过。60 组公共用例的计数、退休日志和最终 64 KiB RAM 与 v35 逐组一致。展平网表通过 60 组公共及 17 组原子用例的零延迟对照。新增定向测试覆盖实际跳转到不同页但低 12 位相同的情况。

[公共用例](../../results/comparisons/v41-page-target/comparison.csv) · [门级对照](results/v41-page-target/gate-equivalence.csv) · [原子专项](results/v41-page-target/native-atomic-equivalence.json) · [验证记录](results/v41-page-target/validation.json)

## 复现

```sh
make test VERSION=v41_page_target
make timing VERSION=v41_page_target CLOCK_NS=10
python3 tools/flat_timing.py v41_page_target --output .local/timing/v41-flat
python3 tools/ifetch_experiments.py --versions v40_store_trace v41_page_target --run-id v41-recheck
```
