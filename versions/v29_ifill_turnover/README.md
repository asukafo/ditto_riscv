# v29 指令补行交接

在 v28 数据通路优化基础上，I-cache 可在接收缺失的当拍提交第一笔 8B 补行。关键字成功返回时直接送给 I 侧响应流水寄存器。若上游反压，I-cache 继续使用原响应寄存器保持数据，补行的尾拍照常排空。关闭 `IFILL_TURNOVER` 可复现 v28。

延迟 5、间隔 3 的求和波形中，第 1 拍的指令需求与第一笔补行同时握手。第 6 拍物理响应返回，关键字同拍被上游接收，第 7 拍发出尾拍。数据侧采样采用同一镜像和条件。[I-cache 采样](results/diagnosis/icache-sum.csv) · [D-cache 采样](results/diagnosis/dcache-sum.csv)

`scripts/refill_waveform.py` 可从 VCD 重新生成采样。读取地址列时以相应的 valid/ready 为准。

## 公共用例验收

同一套 20 程序、3 种内存条件下，四个版本使用字节一致的镜像。全部运行逐条核对退休与最终 64 KiB RAM。

| 版本 | 60 组合计周期 | 慢于 v24 的组数 |
| --- | ---: | ---: |
| v24 | 30927 | 0 |
| v27 | 28937 | 26 |
| v28 | 27794 | 9 |
| v29 | 27294 | 5 |

v29 相对 v27 合计减少 1643 周期，下降 **5.68%**。热循环稳定区间保持 **960 条 / 576 周期 = 1.67 IPC**。关闭 I-cache 改动后，60 组的周期、物理请求、控制流误判和退休数与 v28 一致。[公共比较](../../results/comparisons/v29-ifill-turnover/comparison.csv) · [热区波形](docs/waveforms/wide-hot.svg)

仍慢于 v24 的五组包括三组 `branch_forward`，以及延迟 5、间隔 3 下的 `pointer_chase` 与 `independent`。在该条件下，后两者分别从 v27 的 1371、1107 周期降到 1363、1103。物理总线仍只有一笔在途事务，连续首次补行及指针依赖仍会限制收益。性能指标为模拟周期，综合仅做结构检查。

完整 Verilator 回归覆盖 ISA、Sv39、特权级、中断、原子锁和两类缓存的交接、反压与错误。更早的数据发送让年轻原子握手可与旧原子退休同拍，仿真宿主先检查退休指令的锁计数，再登记当拍新握手。Verilator lint 和 Yosys 结构检查通过。[验证记录](results/v29-ifill-turnover/validation.json)

```sh
# 仓库根目录
make test VERSION=v29_ifill_turnover
make lint synth VERSION=v29_ifill_turnover
make compare BENCHMARK_ARGS="--versions v24_dual_alu v27_integer_pair v28_data_turnover v29_ifill_turnover"
```

在本版本目录运行 `python3 scripts/wide_waveforms.py` 可从回归生成的 VCD 重建热区波形。缓存采样由 `python3 scripts/refill_waveform.py <VCD> icache` 或 `dcache` 重建，使用求和镜像和延迟 5、间隔 3。
