# v28 数据请求与补行交接

v27 的 60 组取指与发射波形只有 11 个周期满足双发射的全部条件却被同对 RAW 阻止，其中 9 次的第一槽是 ADD 或 ADDI。按每次省一拍估算，离 5% 的目标仍有很大差距。实验优先减少每次访存都可能经过的交接等待。[RAW 统计](results/diagnosis/raw-only.csv)

- `DATA_LAUNCH` 允许 X 阶段在无异常、较老 W 可退休时直接向数据侧 MMU 发送请求。当拍没接收则把同一组地址、数据与访问类型存入寄存器，由 DATA_REQ 重试。
- `DATA_REFILL_FORWARD` 允许 D-cache 接收缺失需求时就发送第一笔补行。关键 8B 成功返回时，同拍交给 MMU。上游反压时先把响应存住，未请求的另一半继续补齐。两种动作由同一开关控制。

| 60 组配置 | 总周期 |
| --- | ---: |
| 两项关闭 | 28937 |
| 仅 X 直接发送 | 28045 |
| 仅补行交接 | 28556 |
| 两项启用 | 27794 |

相对 v27 合计下降 3.95%，慢于 v24 的用例从 26 组降到 9 组。以延迟 5、间隔 3 为例，求和 859→731，数据复用 743→679，指针追踪仍为 1371。两项收益存在重叠，不能把两次独立降幅相加。[四配置完整对照](results/diagnosis/data-ablation.csv)

`make test-data-turnover` 覆盖直接请求、关键字当拍返回、反压保持、后台补行失效、请求拍和尾拍错误、以及后续 store/atomic 的顺序。当前实验比较模拟周期，时钟频率需要单独评估。

## 复现

从仓库根目录运行比较，生成相同的程序镜像并逐条核对退休和最终 RAM。

```sh
make compare BENCHMARK_ARGS="--versions v24_dual_alu v27_integer_pair v28_data_turnover"
cd versions/v28_data_turnover
make build/full_obj/Vrv64_core build/nodataturn_obj/Vrv64_core build/launchonly_obj/Vrv64_core build/refillonly_obj/Vrv64_core
python3 scripts/data_ablation.py ../v27_integer_pair/results/v27-integer-pair/performance.csv ../v27_integer_pair/build
```

RAW 统计使用 v27 的真实波形。按 v27 公共性能表的程序和内存条件采样，每个 VCD 文件名为 `程序-延迟-间隔.vcd`。运行 `python3 scripts/raw_only.py ../v27_integer_pair/results/v27-integer-pair/performance.csv 波形目录` 重新计数。

完整 ISA/特权回归、Verilator lint 与 Yosys 结构检查通过。两项关闭时，60 组周期、请求、控制流误判和退休数均与 v27 一致。[验证记录](results/v28-data-turnover/validation.json) · [逐条对照的公共比较](../../results/comparisons/v28-data-turnover/comparison.csv)
