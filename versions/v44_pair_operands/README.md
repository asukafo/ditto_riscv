# v44 第二发射槽操作数提前锁存

v43 的展平最慢寄存器路径从 `frontend.next_pc[36]` 到 `xp_a[38]`。第二发射槽操作数原先由 `issue_fire` 使能锁存，这使候选指令和接收条件都可能进入操作数寄存器的输入路径。

v44 在第二槽空闲或本拍 X 阶段完成时锁存候选操作数。只有 `xp_valid` 使这些操作数参与执行。有效指令停顿时，两个操作数都保持。配对被接受的时钟沿，操作数仍从当拍候选指令读取，并按第二槽 X、主槽 X、第二槽 W、主槽 W、寄存器堆的顺序前递。设置 `PAIR_OPERAND_CAPTURE=0` 恢复 v43 的接收使能。

波形回放对每次配对独立计算前递结果，并检查有效第二槽停顿时的操作数保持。原有 RAW、WAW、冲刷和退休顺序检查继续运行。

| 布局布线前指标 | v41 | v43 | v44 |
| --- | ---: | ---: | ---: |
| 公共用例合计周期 | 26,312 | 26,312 | 26,312 |
| 展平寄存器间 setup 下限 | 7.0482 ns | 7.2236 ns | 7.2037 ns |
| 展平含端口 setup 下限 | 7.8034 ns | 7.8248 ns | 7.9265 ns |
| 分层寄存器间 setup 下限 | 9.3970 ns | 9.1934 ns | 9.1002 ns |
| 分层含端口 setup 下限 | 10.1179 ns | 9.8478 ns | 9.8063 ns |
| 展平标准单元面积 | 268,668.246 | 268,187.584 | 267,827.420 |

原终点 `xp_a[38]` 的展平寄存器路径缩到 7.1840 ns。全核最慢寄存器路径迁移到 `frontend.next_pc[6]` → 第一槽的 `b[18]`。v44 的展平寄存器间估计比 v43 短约 0.28%，比 v41 长约 2.21%。分层含 I/O 的 10 ns 约束满足，但保住 v41 展平性能的目标尚未达成，因此根目录默认仍选 v41。另一种互斥与或前递写法虽然通过组合等价检查，展平寄存器路径却为 7.4373 ns，未采用。[时序记录](results/v44-pair-operands/timing-summary.json) · [展平路径](results/v44-pair-operands/flat-timing.txt) · [原终点路径](results/v44-pair-operands/operand-path.txt) · [分层 I/O 路径](results/v44-pair-operands/io-paths.txt)

完整 Verilator 回归通过，新增波形断言核对第二槽的前递值及有效停顿时的操作数保持。60 组公共用例的周期、退休记录和 RAM 与 v41、v43 及关闭提前锁存的配置一致。展平网表另外通过 60 组公共用例和 59 组双发射专项的逐字节对照，覆盖 RAW、WAW、WAR、零寄存器、前递、load、压缩指令、异常与冲刷。[公共比较](../../results/comparisons/v44-pair-operands/comparison.csv) · [公共门级对照](results/v44-pair-operands/gate-equivalence.csv) · [双发射门级对照](results/v44-pair-operands/pair-gate-equivalence.json)

```sh
make test VERSION=v44_pair_operands
make timing VERSION=v44_pair_operands CLOCK_NS=10
python3 tools/flat_timing.py v44_pair_operands --output .local/timing/v44-flat
python3 tools/ifetch_experiments.py --versions v43_retire_store v44_pair_operands --run-id v44-recheck
```
