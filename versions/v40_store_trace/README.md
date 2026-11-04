# v40 复用 Load 写回结果生成访存日志

v39 的展平最慢路径回到了访存退休数据寄存器。v40 只用这个寄存器保存普通 store 或原子读改写的实际写入值。普通 load 和 LR 所需的原始字节取自已锁存的写回结果，退休时按访问宽度屏蔽高位。SC 失败时仍报告零内存写入数据。目标寄存器值、实际访存握手和提交时序保持原有语义。

| 布局布线前指标 | v35 | v39 | v40 |
| --- | ---: | ---: | ---: |
| 60 组合计周期 | 26,312 | 26,312 | 26,312 |
| 展平寄存器间 setup 下限 | 7.4950 ns | 7.5406 ns | 7.1240 ns |
| 展平含端口约束的 setup 下限 | 8.2523 ns | 7.9361 ns | 7.6422 ns |
| 展平标准单元面积 | 277,037.404 | 270,629.464 | 270,037.614 |
| 分层寄存器间 setup 下限 | 10.7328 ns | 9.7444 ns | 9.5255 ns |
| 分层含端口约束的 setup 下限 | 11.5256 ns | 10.4300 ns | 10.2111 ns |

按展平寄存器间下限估计，整组时间比 v35 缩短 4.95%。展平瓶颈改为到 `wb_mem_write` 的路径。只在 v38 上复用 load 结果的原型保留了每个预测记录的高位地址，展平寄存器下限为 7.4040 ns。[时序与工具记录](results/v40-store-trace/timing-summary.json) · [展平报告](results/v40-store-trace/flat-timing.txt) · [分层报告](results/v40-store-trace/hierarchical-timing.txt)

完整 Verilator 回归通过。60 组公共用例和 17 组原子用例均与上一版逐字节核对，并通过零延迟门级对照。[公共用例](../../results/comparisons/v40-store-trace/comparison.csv) · [公共门级对照](results/v40-store-trace/gate-equivalence.csv) · [原子专项](results/v40-store-trace/native-atomic-equivalence.json)

```sh
make test VERSION=v40_store_trace
make timing VERSION=v40_store_trace CLOCK_NS=10
python3 tools/flat_timing.py v40_store_trace --output .local/timing/v40-flat
```
