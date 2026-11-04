# v36 独立页表响应通路

v35 展平后的最慢寄存器路径从取指 PC 到 ITLB 上下文寄存器。分离访存配置下，PTE 读取走物理仲裁器的专用通道，普通取指和访存则可以走各自的缓存。旧实现先把缓存响应和物理通道响应合并，MMU 再在等待 PTE 时从合并后的接口取出 PTE。

v36 让等待 PTE 的指令和数据 MMU 直接读取各自物理通道的响应有效位、数据和错误位。只有 PTE 请求握手后，MMU 才进入 `PTE_WAIT`。此时对应请求的缓存归属位为 0，既有响应反压仍送到同一物理通道。因此页面错误、访问错误及失效阻止填充都沿用原规则。设置 `WALKER_RESPONSE=0` 恢复合并响应，统一访存配置也沿用合并接口。

| 布局布线前指标 | v35 | v36 |
| --- | ---: | ---: |
| 60 组合计周期 | 26,312 | 26,312 |
| 分层寄存器间 setup 下限 | 10.7328 ns | 9.7779 ns |
| 分层含端口约束的 setup 下限 | 11.5256 ns | 10.5105 ns |
| 展平寄存器间 setup 下限 | 7.4950 ns | 7.5925 ns |
| 展平含端口约束的 setup 下限 | 8.2523 ns | 7.8152 ns |
| 展平标准单元面积 | 277,037.404 | 277,172.266 |

单独测量展平网表原终点 `fmmu.tlb.contexts[1][3]`，v36 到该终点的最慢寄存器路径为 1.1834 ns，v35 为 7.4950 ns。全核展平瓶颈迁移到 `frontend.next_pc[8]` → `request_window.window.spec_pc[61]`。分层寄存器路径已满足 10 ns，计入端口约束后仍有 setup 违例。[时序与工具记录](results/v36-walker-response/timing-summary.json) · [展平报告](results/v36-walker-response/flat-timing.txt) · [分层报告](results/v36-walker-response/hierarchical-timing.txt) · [原终点报告](results/v36-walker-response/itlb-context-path.txt)

完整 Verilator 回归通过。60 组公共用例与 v35 的周期、退休日志和最终 RAM 一致，45 组分页专项用例的日志和 RAM 也一致。用独立页表响应配置运行分离访存测试，开启和关闭取指交接各通过 49 项检查。展平网表通过 60 组零延迟门级对照。[公共用例](../../results/comparisons/v36-walker-response/comparison.csv) · [分页专项](results/v36-walker-response/native-tlb-equivalence.json) · [门级对照](results/v36-walker-response/gate-equivalence.csv)

```sh
make test VERSION=v36_walker_response
make timing VERSION=v36_walker_response CLOCK_NS=10
python3 tools/flat_timing.py v36_walker_response --output .local/timing/v36-flat
```
