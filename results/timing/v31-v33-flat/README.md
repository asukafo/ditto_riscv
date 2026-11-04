# v31 至 v33 展平映射对照

Yosys 综合在同一 Nangate45 typical Liberty、ABC 负载和 OpenSTA 约束下使用 `synth -flatten`。时钟约束 10 ns，输入和输出延迟各 1 ns。各版的 60 组周期来自相同程序、相同内存条件的正式比较。[工具、输入哈希与网表哈希](summary.json) · [周期对照](../../comparisons/v33-onehot-arbiter/comparison.csv)

| 指标 | v31 | v32 | v33 |
| --- | ---: | ---: | ---: |
| 总周期 | 26,503 | 26,312 | 26,312 |
| 寄存器间 setup 下限 | 7.7666 ns | 8.1628 ns | 9.0083 ns |
| 含端口约束 setup 下限 | 8.7200 ns | 9.1191 ns | 9.7106 ns |
| 总周期 × 寄存器间下限 | 205.84 µs | 214.78 µs | 237.03 µs |
| 总周期 × 含端口下限 | 231.11 µs | 239.94 µs | 255.51 µs |
| 标准单元面积 | 281,965.852 | 282,726.080 | 283,604.412 |

v33 展平后的最差寄存器路径终止于 `wb_mem_data[63]`，与分层映射终止在取指窗口的路径不同。三版均满足本次布局前 10 ns 的 setup 检查。v31 在此次展平对照中估计时间最短，v33 比它长 15.15%。同一 v33 展平后的时钟下限比自己的分层结果短约 16.4%。这些数字反映特定的映射、负载和约束，尚无布局布线或物理时钟测量。

[v31 展平报告](v31_equal_branch-timing.txt) · [v32 展平报告](v32_data_under_refill-timing.txt) · [v33 展平报告](v33_onehot_arbiter-timing.txt) · [v33 分层对照](../../../versions/v33_onehot_arbiter/README.md)

## 复现

```sh
python3 tools/flat_timing.py v33_onehot_arbiter --output .local/timing/v33-flat
```

把版本名与输出目录替换为 v31 或 v32 即可重跑对应配置。工具使用该版的 `abc.constr` 和 `timing.tcl`，并额外报告寄存器间最差 setup 路径。

### 功能门级对照

v33 展平网表的 60 组门级运行与 RTL 的周期、外部请求、误判、退休数一致，JSONL 及最终 64 KiB RAM 逐字节相同。[逐组核对](v33-gate-equivalence.csv)

先保留正式 RTL 公共运行生成的镜像、trace 和 RAM。构建零延迟单元模型及门级仿真程序后，使用同一组镜像核对 trace 与最终 RAM 的字节。该检查验证功能，延迟仍由 OpenSTA 单独估计。

```sh
repo="$PWD"
lib="$HOME/.local/opt/opensta/share/lib/NangateOpenCellLibrary_typical.lib"
cd .local/timing/v33-flat
yosys -Q -T -p "read_liberty -ignore_miss_func \"$lib\"; proc; opt; write_verilog -noattr build/cell_models.v"
verilator --cc --exe --top-module rv64_core -Wno-UNOPTFLAT \
  --Mdir build/mapped_obj -CFLAGS '-std=c++17' build/core_mapped.v build/cell_models.v \
  "$repo/versions/v33_onehot_arbiter/sim/main.cpp"
make -C build/mapped_obj -f Vrv64_core.mk -j3 'VM_USER_CLASSES=main verilated_vcd_c'
cd "$repo"
python3 tools/verify_mapped_public.py v33_onehot_arbiter v33-onehot-arbiter \
  .local/timing/v33-flat/build/mapped_obj/Vrv64_core --output .local/timing/v33-flat-gates
```

展平网表有一处 `frontend.second_packet` 向量别名。右侧引用与左侧写入互不重叠的位，Verilator 按整向量报告 `UNOPTFLAT`。上述门级命令仅在生成网表的编译中抑制该告警，RTL lint 设置保持原样。

本次 Verilator 5.052 为展平网表生成 VCD 插桩时遇到内部名称映射错误。复现命令关闭 VCD 插桩，并单独链接宿主引用的 VCD 库。公共用例使用 `-` 关闭波形，JSONL 退休和 RAM 核对仍启用。
