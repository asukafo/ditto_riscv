# v42 译码器有符号地址加法

在 10 ns 时钟、1 ns 输入延迟和 1 ns 输出延迟下，复核 v41 的分层网表得到 −0.1179 ns 的最差 setup 裕量，终点为 `dtlb_hit_event`。因此 v41 含端口的时钟下限应为 10.1179 ns，旧版 README 记录的 10.3188 ns 与归档报告不一致。v41 最慢的内存协议输出 `req_store_check` 有 +0.2291 ns 裕量。[v41 基线路径](results/v42-decoder-timing/v41-io-paths.txt)

先试过寄存四个 TLB 命中与未命中观测信号。仿真逐沿核对了寄存前后事件计数，但重新分层映射后最差端口变成 `d_walk_event`，裕量为 −0.3304 ns，内存协议端口也出现违例。继续沿路径定位到 `insn[31]` 和译码器里的多个符号扩展加法。

v42 把有效地址计算拆为低 12 位相加和高 52 位修正。低位进位等于立即数符号位时，高位保持。否则正偏移使高位加一，负偏移使高位减一。高位的两个候选与低位相加并行计算。JALR 复用有效地址并清零 bit 0。直接跳转目标用同样的拆分方法，并让条件分支和 JAL 共用一套目标地址加法。取指、访存握手和顶层观测端口均沿用 v41 的采样规则。

例如，基址 `0x1000` 加偏移 `-4`，低位和为 `0xffc`，没有进位而符号位为 1，高位减一，得到 `0x0ffc`。译码器组合等价检查覆盖所有输入位，分别验证了扩展开启和关闭两种配置。

## 分层映射

| 10 ns 下的 setup 裕量 | v41 复核 | v42 |
| --- | ---: | ---: |
| 全部约束 | −0.1179 ns | +0.2661 ns |
| 寄存器到寄存器 | +0.6030 ns | +0.9204 ns |
| 输入到寄存器 | +1.9466 ns | +1.7309 ns |
| 到内存协议输出 | +0.2291 ns | +0.5465 ns |

v42 含端口的布局前时钟下限为 9.7339 ns。最慢端口是 `itlb_hit_event`，最慢的内存协议端口是 `req_store_check`。[v42 分组路径](results/v42-decoder-timing/v42-io-paths.txt)

```sh
make test VERSION=v42_decoder_timing
make timing VERSION=v42_decoder_timing CLOCK_NS=10
python3 tools/flat_timing.py v42_decoder_timing --output .local/timing/v42-flat
python3 tools/ifetch_experiments.py --versions v41_page_target v42_decoder_timing --run-id v42-recheck
```

## 展平映射

60 组公共用例的总周期都是 26,312。v42 展平寄存器间下限为 7.3391 ns，v41 为 7.0482 ns，整组布局前估计时间增加 4.13%。最慢寄存器路径从 `frontend.next_pc[2]` 到 `wb_mem_write`。v42 保留为分层时序版本，根目录默认仍选 v41。[展平报告](results/v42-decoder-timing/flat-timing.txt) · [分层报告](results/v42-decoder-timing/hierarchical-timing.txt) · [测量与哈希](results/v42-decoder-timing/timing-summary.json)

完整 Verilator 回归通过，60 组公共用例的周期、退休记录及最终 RAM 与 v41 相同，展平网表也通过逐字节对照。[门级对照](results/v42-decoder-timing/gate-equivalence.csv) · [组合等价记录](results/v42-decoder-timing/decoder-equivalence.json)
