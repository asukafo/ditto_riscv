# v35 页内预取重定向

v34 展平映射的最慢寄存器路径从 `frontend.next_pc[38]` 到 `request_window.window.spec_pc[3]`。取指窗口可以根据预测更新下一笔预取地址。双指令取指包有两个预测槽，低槽跳离自身顺序地址时优先，否则才看高槽。

v34 在各槽先生成 64 位下一地址，再比较它是否等于该槽的顺序地址。v35 利用预取预测只接受同页且四字节对齐的跳转，把重定向判断改成 10 位页内字索引比较。顺序地址跨页时，同页目标一定与它不同。高槽查询只有在包起点的 bit 2 为 0 时有效，这时把 bit 2 置 1 就得到高槽地址。低槽跳到下一包起点时仍保留低槽优先级，包重定向计数保持原有定义。设置 `PREFETCH_REDIRECT=0` 可切回 v34 的判断逻辑。

最终采用的方案还把下一地址拆成页号与页内偏移。预测命中时沿用当前页号。只有顺序地址的页内偏移产生进位时，才选择递增后的页号。预测选择、请求握手和写入 `spec_pc` 都在原来的周期完成。

## 布局前时序

| 指标 | v31 | v33 | v34 | v35 仅改重定向原型 | v35 选定方案 |
| --- | ---: | ---: | ---: | ---: | ---: |
| 公共用例合计周期 | 26,503 | 26,312 | 26,312 | 26,312 | 26,312 |
| 展平寄存器间 setup 下限 | 7.7666 ns | 9.0083 ns | 7.8704 ns | 7.4493 ns | 7.4950 ns |
| 展平含端口约束的 setup 下限 | 8.7200 ns | 9.7106 ns | 8.7906 ns | 8.1746 ns | 8.2523 ns |
| 周期 × 展平寄存器间下限 | 205.84 µs | 237.03 µs | 207.09 µs | 196.01 µs | 197.21 µs |
| 展平标准单元面积 | 281,965.852 | 283,604.412 | 280,487.956 | 278,771.990 | 277,037.404 |
| 分层寄存器间 setup 下限 | 10.8984 ns | 10.7748 ns | 10.8365 ns | 11.1222 ns | 10.7328 ns |
| 分层含端口约束的 setup 下限 | 11.6912 ns | 11.7697 ns | 11.8315 ns | 11.9149 ns | 11.5256 ns |
| 分层标准单元面积 | 373,644.082 | 373,609.502 | 372,224.706 | 372,055.530 | 372,419.152 |

选定方案的分层时序优于 v33，展平的整组估计时间比 v31 短 4.19%，因此根目录默认切到 v35。只测旧终点 `spec_pc[3]` 时，展平寄存器路径从 v34 的 7.8704 ns 降到 6.8070 ns。全核展平最慢寄存器路径迁移到 `frontend.next_pc[28]` → `memory_system.split.fmmu.tlb.contexts[1][3]`。时序使用 Nangate45 typical 单元库、同一 ABC 负载与 OpenSTA 约束。分层映射仍有 10 ns setup 违例。[展平报告](results/v35-prefetch-redirect/flat-timing.txt) · [旧终点报告](results/v35-prefetch-redirect/spec-pc-path.txt) · [分层报告](results/v35-prefetch-redirect/hierarchical-timing.txt) · [两种原型数据](results/v35-prefetch-redirect/timing-summary.json)

## 验证与复现

完整 Verilator 回归通过，热区为 960 条指令、576 个周期。60 组公共用例的周期、请求数、退休日志和最终 64 KiB RAM 与 v34 一致，关闭优化时也一致。展平网表的 60 组公共用例也通过零延迟门级对照。新增的双槽定向用例覆盖低槽优先级、跳到顺序地址、最后一个页内字和跨页阻止。[公共用例](../../results/comparisons/v35-prefetch-redirect/comparison.csv) · [门级对照](results/v35-prefetch-redirect/gate-equivalence.csv) · [验证记录](results/v35-prefetch-redirect/validation.json)

```sh
make test VERSION=v35_prefetch_redirect
make timing VERSION=v35_prefetch_redirect CLOCK_NS=10
python3 tools/flat_timing.py v35_prefetch_redirect --output .local/timing/v35-flat
python3 tools/ifetch_experiments.py --versions v34_retire_amo v35_prefetch_redirect --run-id v35-recheck
```
