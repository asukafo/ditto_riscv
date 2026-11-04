# v32 D-cache 补行期间的 load 命中实验

默认发布版本仍是 v31。v32 提供独立的构建入口，适合对比以指针追踪为主的工作负载。

D-cache 已返回关键 8B、正在补齐另一半时，可以接收一个数据已可用的后续 load。来源可以是另一条已有效的缓存行、当前行已缓冲的关键半行，或同拍成功返回的尾半行。只有旧响应槽为空时才接受，结果写入原响应寄存器。写入和原子操作继续等待。读取正在补行的那条缓存行时，跨半行或所需尾拍尚未成功返回的请求也继续等待。失效会阻止背景接收，尾拍失败的需求按正常缺失路径重试并获得对应错误。

两个地址已通过可缓存 RAM 范围约束，因此行号只需比较位 15:4。关闭 `DATA_UNDER_REFILL` 可以恢复 v31。

## 性能取舍

| 指标 | v31 | v32 |
| --- | ---: | ---: |
| 60 组总周期 | 26,503 | 26,312 |
| 寄存器间最小时钟周期估计 | 10.8984 ns | 11.0570 ns |
| 映射面积 | 373,644.082 | 374,580.136 |

11 组周期下降、49 组持平。计入相同条件下的寄存器间时钟估计，整组执行时间增加约 0.72%，面积增加约 0.25%。指针追踪在延迟 5、间隔 0 时从 1091 降到 1028 周期，外部请求均为 139 次，计入时钟估计仍约快 4.4%。延迟 5、间隔 3 时仅从 1363 降到 1359，收益受请求间隔限制。

[真实上升沿采样](results/diagnosis/pointer-tail.csv)中的第 67 拍，load 和成功的尾拍同时到达，D-cache 在这一拍接收需求，第 68 拍交付 load 响应。采样来自 `pointer_chase`，延迟 5、间隔 0。

此前也验证了让预取窗口直接使用同寄存器分支方向，60 组只省 1 周期。D-cache 的完整地址试验省 191 周期但时钟估计为 11.22 ns，仅开放尾拍的试验省 166 周期但时钟估计为 12.71 ns。最终实验采用页内行号比较，保留原来 191 周期的收益。

## 复现

从仓库根目录运行：

```sh
make test VERSION=v32_data_under_refill
make timing VERSION=v32_data_under_refill CLOCK_NS=10
make compare BENCHMARK_ARGS="--versions v31_equal_branch v32_data_under_refill"
```

在版本目录用 `scripts/data_under_waveform.py` 从实际 VCD 重建尾拍采样。定向单元覆盖三种成功数据来源、响应反压及尾拍失败后重试。

完整 ISA/特权回归、逐条退休与全部 RAM 核对、Verilator lint 和映射结构检查通过。关闭功能后，60 组的周期、请求、控制流误判和退休数与 v31 一致。热区仍以 576 周期退休 960 条指令。

[公共比较](../../results/comparisons/v32-data-under-refill/comparison.csv) · [验证记录](results/v32-data-under-refill/validation.json) · [时序报告](results/v32-data-under-refill/timing-report.txt)
