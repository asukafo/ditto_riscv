# v43 在退休阶段判定 store 记录

v42 分层映射已满足含端口的 10 ns 约束，但展平最慢路径仍到 `wb_mem_write`。v43 在 X/W 交界处锁存指令的写请求类型，W 阶段结合 `wb_mem_valid` 判断该访问是否有效，并从 `wb_result` 检查 SC 的返回码。成功的 SC 才在退休记录中标记内存写入，失败的 SC 继续报告零写入数据。实际写请求仍由原子适配器负责。

| 10 ns 下的分层 setup 裕量 | v41 复核 | v42 | v43 |
| --- | ---: | ---: | ---: |
| 全部约束 | −0.1179 ns | +0.2661 ns | +0.1522 ns |
| 寄存器到寄存器 | +0.6030 ns | +0.9204 ns | +0.8066 ns |
| 输入到寄存器 | +1.9466 ns | +1.7309 ns | +1.7156 ns |
| 到内存协议输出 | +0.2291 ns | +0.5465 ns | +0.4327 ns |

分层含端口的时钟下限为 9.8478 ns。v41 的复核结果及此前时序数字更正在 v42 的记录中。

| 展平映射指标 | v41 | v42 | v43 |
| --- | ---: | ---: | ---: |
| 寄存器间 setup 下限 | 7.0482 ns | 7.3391 ns | 7.2236 ns |
| 含端口约束的 setup 下限 | 7.8034 ns | 7.9923 ns | 7.8248 ns |
| 标准单元面积 | 268,668.246 | 266,863.170 | 268,187.584 |

60 组公共用例的总周期保持 26,312。v43 的展平整组估计时间比 v41 长 2.49%，比 v42 短约 1.57%。分层含端口的 10 ns 目标达成，保住 v41 展平性能的目标尚未达成，因此默认仍选 v41。当前展平最慢路径从 `frontend.next_pc[36]` 到第二发射槽的 `xp_a[38]`。[展平报告](results/v43-retire-store/flat-timing.txt) · [分层报告](results/v43-retire-store/hierarchical-timing.txt) · [分组路径](results/v43-retire-store/io-paths.txt) · [时序与哈希](results/v43-retire-store/timing-summary.json)

Verilator 完整回归通过。60 组公共用例的计数、退休日志和最终 RAM 与 v41 和 v42 相同。展平网表的 60 组公共用例和 17 组原子专项也通过了零延迟门级逐字节对照，覆盖 SC 成功、失败和缓存竞争。[公共用例](../../results/comparisons/v43-retire-store/comparison.csv) · [门级公共对照](results/v43-retire-store/gate-equivalence.csv) · [原子专项](results/v43-retire-store/native-atomic-equivalence.json)

```sh
make test VERSION=v43_retire_store
make timing VERSION=v43_retire_store CLOCK_NS=10
python3 tools/flat_timing.py v43_retire_store --output .local/timing/v43-flat
```
