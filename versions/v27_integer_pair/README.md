# v27 常用整数指令配对

第二执行槽复用 RV64I ALU，支持整数算术、逻辑、比较、移位和 32 位结果符号扩展，并支持 LUI 和 AUIPC。发射前复用 ALU 的编码合法性判定。RAW 检查按源操作数类型判断，LUI 和 AUIPC 的立即数位不参与寄存器比较。WAW、连续 PC 和精确退休约束继续生效。


## 同条件比较

20 个程序各用三种内存条件运行，所有配置使用相同镜像，逐条对照退休记录和最终 64 KiB RAM。关闭 `INTEGER_PAIR` 后，60 组的周期、请求数、控制流误判和退休数均与 v26 一致。[完整比较](../../results/comparisons/v27-integer-pair/comparison.csv)

| v27 相对版本 | 更快 | 持平 | 更慢 | 总周期差 |
| --- | ---: | ---: | ---: | ---: |
| v24 | 32 | 2 | 26 | −1990 |
| v25 | 18 | 39 | 3 | −1918 |
| v26 | 3 | 57 | 0 | −17 |

相对 v26，改善都来自 `bit_ops`。在延迟 5、间隔 3 下，四次实际双发射使周期从 203 降至 195，访存等待也随调度变化从 123 降至 117。交替分支保留 v26 的 439 周期，阶段分支保留 407 周期。指针追踪仍为 1371 周期，其中 915 周期是数据请求或响应等待。[逐周期分类](results/cycle-diagnosis/cycles.csv)

热循环稳定区间以 576 周期退休 960 条指令，保持 **1.67 IPC**。发射波形按上升沿前采样，退休按沿后采样。[热区波形](docs/waveforms/wide-hot.svg) · [第二槽分支跳转采样](../v26_second_branch/results/branch-diagnosis/branch-window.csv)

## 验证与限制

`make test` 覆盖基础整数、压缩、乘除、原子、CSR、中断和分页等整核测试。`make test-integer-pair` 在四种内存条件下逐一核对 30 种操作的第二槽退休结果。Verilator lint 和 Yosys 结构检查通过。综合结构检查只验证设计结构，周期比较未测量最高频率或面积。

第二执行槽覆盖无访存副作用的整数操作。两条间有 RAW 或 WAW 时仍单发射，控制流、访存、系统指令和乘除仍走主槽。公共对照中相对 v24 仍有 26 组更慢。

```sh
# 从仓库根目录
make test VERSION=v27_integer_pair
make test-integer-pair VERSION=v27_integer_pair
make lint synth VERSION=v27_integer_pair
make compare BENCHMARK_ARGS="--versions v24_dual_alu v25_wide_frontend v26_second_branch v27_integer_pair"
```

运行回归后，可在本版本目录执行 `python3 scripts/wide_waveforms.py` 重建热区波形。逐周期分类使用 `scripts/bottlenecks.py`，取样方法见 [v26 复现说明](../v26_second_branch/README.md)。
