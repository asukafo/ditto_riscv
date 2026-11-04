# v37 独热 TLB 查找和填充

每个表项独立比较 VPN 和完整的 `satp` 上下文，再用匹配位对物理页号和权限逐位与或。相同 VPN 和上下文的填充会更新原表项，因此有效表项的查找匹配最多一位。填充依次选择重复项、首个空位和轮转位置，直接用独热向量使能表项写入。轮转指针改用独热环，重复填充时保持。

v37 保留 v36 的独立页表响应通路。

| 布局布线前指标 | v35 | v36 | v37 |
| --- | ---: | ---: | ---: |
| 60 组合计周期 | 26,312 | 26,312 | 26,312 |
| 展平寄存器间 setup 下限 | 7.4950 ns | 7.5925 ns | 7.1730 ns |
| 展平含端口约束的 setup 下限 | 8.2523 ns | 7.8152 ns | 7.5358 ns |
| 分层寄存器间 setup 下限 | 10.7328 ns | 9.7779 ns | 9.9814 ns |
| 分层含端口约束的 setup 下限 | 11.5256 ns | 10.5105 ns | 10.4193 ns |
| 展平标准单元面积 | 277,037.404 | 277,172.266 | 275,975.798 |
| 分层标准单元面积 | 372,419.152 | 372,331.106 | 368,857.412 |

整组周期保持 26,312，按展平寄存器间下限估计，比 v35 缩短 4.30%。分层寄存器路径满足 10 ns，含端口的约束仍有违例。展平最慢寄存器路径从 `frontend.spare_pc[36]` 到 `request_window.window.spec_pc[59]`。[展平报告](results/v37-onehot-tlb/flat-timing.txt) · [分层报告](results/v37-onehot-tlb/hierarchical-timing.txt) · [工具与输入哈希](results/v37-onehot-tlb/timing-summary.json)

完整 Verilator 回归和 60 组零延迟门级对照通过。公共用例的周期、退休日志及 RAM 与 v36 一致，另有 45 组分页专项与 v35 的日志和 RAM 一致。[公共用例](../../results/comparisons/v37-onehot-tlb/comparison.csv) · [门级对照](results/v37-onehot-tlb/gate-equivalence.csv) · [分页专项](results/v37-onehot-tlb/native-tlb-equivalence.json)

```sh
make test VERSION=v37_onehot_tlb
make timing VERSION=v37_onehot_tlb CLOCK_NS=10
python3 tools/flat_timing.py v37_onehot_tlb --output .local/timing/v37-flat
```
