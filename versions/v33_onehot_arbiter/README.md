# v33 并行独热物理仲裁

v32 的 D-cache 补行重叠节省了周期，但分层映射的关键路径变长。v33 保留 v32 的访存交接，改写四路物理仲裁器的组合授权与请求选择。四种轮转优先顺序并行形成候选授权，当前轮转起点选中其中一组，独热位直接选择地址、数据和控制字段。响应所有权与阻塞时的请求保持仍由原状态机管理。

`ONEHOT_ARBITER=0` 可切回 v32 的索引选择。仲裁器测试覆盖 4 个轮转起点 × 16 种请求掩码，以及 144 笔含反压的事务。指针追踪的第 20 拍，I-cache 和 D-cache 同时请求，轮转起点为 1，因此授权 D-cache。第 25 拍响应只交给 D-cache。[上升沿采样](results/diagnosis/pointer-arbitration.csv)

## 同约束的分层映射

| 指标 | v31 | v32 | v33 |
| --- | ---: | ---: | ---: |
| 60 组合计周期 | 26,503 | 26,312 | 26,312 |
| 寄存器间 setup 下限 | 10.8984 ns | 11.0570 ns | 10.7748 ns |
| 含端口约束的 setup 下限 | 11.6912 ns | 11.8498 ns | 11.7697 ns |
| 总周期 × 寄存器间下限 | 288.84 µs | 290.93 µs | 283.51 µs |
| 总映射面积 | 373,644.082 | 374,580.136 | 373,609.502 |

按寄存器间估计，v33 的整组时间比 v31 缩短 1.85%。纳入本实验的全部端口约束时，两者的整组估计时间接近，约相差 0.05%。以上为布局前估计，10 ns 约束仍有 setup 违例。

## 复现

```sh
make test VERSION=v33_onehot_arbiter
make timing VERSION=v33_onehot_arbiter CLOCK_NS=10
make compare BENCHMARK_ARGS="--versions v31_equal_branch v32_data_under_refill v33_onehot_arbiter"
```

用 v33 运行 `pointer_chase`，延迟 5、间隔 0。在本版本目录执行 `python3 scripts/arbiter_waveform.py <VCD>` 可重新生成上升沿采样。

完整 ISA、特权、原子、缓存和窗口回归通过。与 v32 对照，60 组周期、物理请求、控制误判和退休数逐组相同，每条退休记录与最终 RAM 通过独立核对。热区保持 960 条 / 576 周期。[公共比较](../../results/comparisons/v33-onehot-arbiter/comparison.csv) · [验证记录](results/v33-onehot-arbiter/validation.json) · [分层时序](results/v33-onehot-arbiter/timing-report.txt)

## 展平映射对照

保留相同库、ABC 驱动/负载及 STA 约束，仅将 v31、v32 的 Yosys `synth` 改成 `synth -flatten`。两版寄存器间时钟估计分别约为 7.77 ns、8.16 ns，映射面积约为 281,966、282,726。展平降低了两版的绝对时钟估计，但 v32 的布局前整组时间仍比展平后的 v31 长。v33 的表格使用分层映射对照。[展平数据与网表哈希](results/v33-onehot-arbiter/flat-comparison.json) · [v31 展平报告](results/v33-onehot-arbiter/v31_equal_branch-flat-timing.txt) · [v32 展平报告](results/v33-onehot-arbiter/v32_data_under_refill-flat-timing.txt)

复现展平实验时，复制对应版本 `make -n timing CLOCK_NS=10` 输出的 Yosys 和 OpenSTA 命令到独立工作目录，改用绝对 RTL、约束及 Tcl 路径，在综合子命令加入 `-flatten`，并在工作目录创建 `build/`。

后续实验补齐了 v33 展平时序及 60 组零延迟门级核对。[v31 至 v33 展平对照](../../results/timing/v31-v33-flat/README.md)
