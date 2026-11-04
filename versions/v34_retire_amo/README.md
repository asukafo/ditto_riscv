# v34 AMO 退休数据路径实验

v33 展平网表的最慢寄存器路径落在 `wb_mem_data[63]`。原子读改写指令（AMO）的新值由总线适配器计算并送往内存。v33 核心再用响应旧值和指令源操作数算一遍，把结果记入 `commit_mem_data`。这个日志字段表示实际写入内存的值，AMO 写回目标通用寄存器的则是原来的值。

本实验对照两种方案。一种把日志用的 AMO 算术放到 W 阶段，X 阶段将操作数锁存进写回级。另一种沿内部响应携带适配器已算出的写入值，消除核心里的第二次计算。两种方案都保持 AMO 原有的读改写顺序和响应握手。

v34 采用第二种方案。适配器在内存读响应到达时锁存 `new_data`，下一步用它发出写请求，并将它保持到写响应握手。核心用 `wb_mem_data` 锁存这个值，成功退休的原子读改写将它输出为 `commit_mem_data`。访存异常沿用已有的退休有效位判断。LR 和 SC 仍走各自的记录逻辑。设置 `ADAPTER_AMO_DATA=0` 可恢复 v33 的计算方式。

## 展平映射

| 指标 | v31 | v33 | W 阶段重算原型 | v34 复用适配器结果 |
| --- | ---: | ---: | ---: | ---: |
| 60 组合计周期 | 26,503 | 26,312 | 26,312 | 26,312 |
| 寄存器间 setup 下限 | 7.7666 ns | 9.0083 ns | 8.0908 ns | 7.8704 ns |
| 含端口约束的 setup 下限 | 8.7200 ns | 9.7106 ns | 8.9967 ns | 8.7906 ns |
| 周期 × 寄存器间下限 | 205.84 µs | 237.03 µs | 212.89 µs | 207.09 µs |
| 标准单元面积 | 281,965.852 | 283,604.412 | 284,679.584 | 280,487.956 |

单独约束 `wb_mem_data[63]` 为终点时，v34 的最慢寄存器路径为 7.6608 ns，v33 为 9.0083 ns。v34 的全核最慢寄存器路径迁移到 `frontend.next_pc[38]` → `request_window.window.spec_pc[3]`，从取指 PC 到请求窗口的推测 PC。v34 按寄存器间时钟下限估计的整组时间比 v33 短 12.63%，比 v31 长 0.61%。[v31 至 v33 展平数据](../../results/timing/v31-v33-flat/README.md) · [v34 展平报告](results/v34-retire-amo/flat-timing.txt) · [原写回终点报告](results/v34-retire-amo/wb-mem-data-path.txt)

## 分层映射

| 指标 | v33 | W 阶段重算原型 | v34 复用适配器结果 |
| --- | ---: | ---: | ---: |
| 寄存器间 setup 下限 | 10.7748 ns | 10.8181 ns | 10.8365 ns |
| 含端口约束的 setup 下限 | 11.7697 ns | 11.8131 ns | 11.8315 ns |
| 周期 × 寄存器间下限 | 283.51 µs | 284.65 µs | 285.13 µs |
| 标准单元面积 | 373,609.502 | 373,700.474 | 372,224.706 |

根目录默认仍选 v33，v34 可单独运行。两种映射均使用相同的 Nangate45 typical 单元库和 I/O 约束。以上是布局布线前的估计，分层映射仍有 10 ns setup 违例。[时序和工具记录](results/v34-retire-amo/timing-summary.json) · [v34 分层报告](results/v34-retire-amo/hierarchical-timing.txt)

## 验证与复现

60 组公共用例在 v33 和 v34 上的周期、退休日志和最终 64 KiB RAM 一致。另有 17 组原子指令及缓存竞争测试，逐字节比对退休日志与 RAM，覆盖两种候选方案。关闭分离访存的配置也在两组延迟下核对了原子程序。Verilator 完整回归通过，选定展平网表的 60 组公共用例及 17 组原子用例也通过了零延迟门级对照。[公共对照](../../results/comparisons/v34-retire-amo/comparison.csv) · [原子用例核对](results/v34-retire-amo/native-atomic-equivalence.json) · [门级公共对照](results/v34-retire-amo/gate-equivalence.csv) · [验证记录](results/v34-retire-amo/validation.json)

```sh
make test VERSION=v34_retire_amo
make timing VERSION=v34_retire_amo CLOCK_NS=10
python3 tools/flat_timing.py v34_retire_amo --output .local/timing/v34-flat
python3 tools/ifetch_experiments.py --versions v33_onehot_arbiter v34_retire_amo --run-id v34-recheck
```
