# v47 Nangate45 物理时序实验

输入是 v47 的归档展平网表，时钟保持 10 ns，输入和输出延迟保持 1 ns。起点网表的 SHA-256 为 `19504ec21c67caa8a5e6028a58173f597628dcffca9fdb60cbb0c9a93552cf87`。Liberty 与原展平报告一致。实验使用 35% 核心利用率、Nangate45 电源网格和传播时钟，保留布局修复和时钟树综合。首次自动时序修复在 658 个违例端点的首轮处理期间中止，物理基线跳过了该步骤。

## 原始网表基线

| 阶段 | 寄生来源 | Setup 最差裕量 | Setup TNS | Hold 最差裕量 |
|---|---|---:|---:|---:|
| 展平映射 | 单元库，无布线寄生 | +2.1812 ns | 0.0000 ns | +0.0793 ns |
| 时钟树后 | 按布局估算 | −2.1502 ns | −281.6985 ns | +0.0826 ns |
| CUGR 全局布线 | 按布线导引估算，仍有拥塞 | −2.9048 ns | −770.5608 ns | +0.0828 ns |

布局使用约 895.18 µm 见方的 die，输入网表有 164,682 个实例和 2,350 个顶层端口。时钟树综合插入 2,327 个时钟缓冲器。时钟树后 hold TNS 为 0 ns。

时钟树后的三组最差 setup 路径都从触发器 `_319857_` 出发。最差顶层端点为 `prefetch_path_redirect_event`。寄存器到寄存器路径结束于取指窗口的 `forecast_target[3][2]`，裕量为 −1.1155 ns。内存接口输出最差端点为 `req_addr[32]`，裕量为 −0.6370 ns。这些路径共享一段长缓冲链，说明即使单独评估功能路径，10 ns 约束下也已有违例。报告中的时钟树阶段仍按布局估算线网寄生。

到三组路径的分叉点为止，共经过 36 个缓冲单元。按实例名核对，33 个已存在于布局输入网表。这些缓冲级的报告增量延迟合计 3.9156 ns，包含各级估算线网负载的影响。下一轮可以保持 RTL 和约束一致，对比改变映射或布局前缓冲策略后的 setup、拥塞与周期数。

详细布线首次启动时报告 `DRT-0305`。OpenDB 把归档 Verilog 中的直接常量赋值归到 `one_` 和 `zero_`，分别挂有 22 和 142 个顶层端口，两条网都没有单元驱动。复现脚本先用 Yosys `hilomap` 将常量连接落实为库里的 `LOGIC1_X1` 和 `LOGIC0_X1`。

原始网表的 FastRoute 对照运行在约 20 分钟时中止，表中的全局布线结果来自 CUGR。[原始网表时序报告](initial-timing.txt)

## 加入 tie cell 后

Yosys 结构检查通过。Verilator 使用加 tie cell 后的布局输入网表跑完 60 组公开用例，提交轨迹和最终 RAM 都与 RTL 逐字节一致。[输入哈希与验证记录](inputs.json)

| 阶段 | Setup 最差裕量 | Setup TNS | Hold 最差裕量 |
|---|---:|---:|---:|
| 展平映射 | +2.1812 ns | 0.0000 ns | +0.0793 ns |
| 时钟树后 | −2.3574 ns | −376.3066 ns | +0.0825 ns |
| CUGR 全局布线，仍有拥塞 | −3.1976 ns | −2011.1841 ns | +0.0713 ns |

时钟树后最差寄存器路径到取指窗口的 `forecast_bytes[1][0]`，setup 裕量为 −1.3648 ns。最差内存输出 `bus_lock` 的 setup 裕量为 −0.9070 ns。全局布线估算下，最差内部路径到 `forecast_target[1][1]`，裕量为 −2.0955 ns，最差内存输出变为 `req_addr[33]`，裕量为 −1.8086 ns。[加 tie cell 后的时序报告](tie-cell-timing.txt)

加 tie cell 后导入器仍留下一个没有端口和单元端子的 `zero_` 占位网。详细布线前删除这条空网，保留连接到电源网格的 `VDD` 和 `VSS`。

详细布线通过引脚访问分析和轨道分配。首轮推进到 30% 时累计报告 50,352 处设计规则违规，随后手动停止运行。该计数是首轮中途值。当前最晚的时序数据来自有拥塞的全局布线估算，尚无详细布线后提取的 SPEF 和 setup / hold 数据。实验只使用 Nangate45 typical 库。

## 重缓冲对照

在同一物理输入网表、同一 die 和时钟约束下，布局前用 `remove_buffers` 清除 16,410 个缓冲器，再由 `repair_design` 根据布局估算的负载插入缓冲。HPWL 取全局布局后、修复前。时序取时钟树后。

| 指标 | 保留映射缓冲 | 清除后重缓冲 |
|---|---:|---:|
| HPWL | 5,610,309.87 µm | 2,900,266.27 µm |
| Setup 最差裕量 | −2.3574 ns | −2.2268 ns |
| Setup TNS | −376.3066 ns | −3250.7937 ns |
| 寄存器到寄存器最差 setup 裕量 | −1.3648 ns | −1.6099 ns |
| Hold 最差裕量 | +0.0825 ns | +0.0829 ns |

全量重缓冲缩短了估算线长，最差顶层端点从预取重定向输出转到 `req_wdata[51]`。内部最差路径和 setup TNS 均恶化，保留原缓冲配置作为基线。[重缓冲时序报告](rebuffer-timing.txt)

## 复现

先准备归档对应的网表及 Liberty。可以用现有 `tools/flat_timing.py` 复建网表，再核对哈希。工作目录中的 `constraints.tcl` 从 v47 原时序脚本提取时钟、端口延迟、输入转换和负载约束。

```sh
work="$PWD/.local/physical/recheck"
mkdir -p "$work"
# Set mapped_netlist and liberty to the input files verified above.
cp "$mapped_netlist" "$work/core_mapped.v"
cp "$liberty" "$work/NangateOpenCellLibrary_typical.lib"
cp tools/physical_timing.tcl "$work/"
awk '/^create_clock / {emit=1} /^check_setup / {emit=0} emit' \
  versions/v47_forward_candidates/scripts/timing.tcl > "$work/constraints.tcl"
(cd "$work" && yosys -Q -T -p '
  read_liberty -lib NangateOpenCellLibrary_typical.lib
  read_verilog core_mapped.v
  hilomap -hicell LOGIC1_X1 Z -locell LOGIC0_X1 Z
  check -assert
  write_verilog -noattr -noexpr physical.v
') > "$work/ties.log" 2>&1 || exit
image=openroad/orfs@sha256:f55910bed183e4d14bded571e777000ae2892138d3412a90c262ac6e699ac11f
for stage in global detail; do
  docker run --rm --platform linux/amd64 --network none \
    --mount "type=bind,source=$work,target=/work" -w /work \
    -e PLATFORM_DIR=/OpenROAD-flow-scripts/flow/platforms/nangate45 \
    -e CLOCK_NS=10 -e ROUTER=cugr -e STAGE="$stage" \
    --entrypoint /OpenROAD-flow-scripts/tools/install/OpenROAD/bin/openroad \
    "$image" -no_init -exit physical_timing.tcl > "$work/$stage.log" 2>&1 || exit
done
```

用 `STAGE=clock_tree` 可以从 `clock_tree.odb` 复查按布局估算的三组路径。在独立目录里设 `STAGE=place` 和 `REMOVE_MAPPED_BUFFERS=1` 可复现重缓冲对照。省略 `ROUTER` 可用 FastRoute 对比。原始网表、数据库、布线导引和工具日志保存在本地工作目录。

本次使用独立的 Colima 配置，Docker 命令通过 `--context colima-riscv-physical` 指定该环境。[Nangate45 平台设置](https://github.com/The-OpenROAD-Project/OpenROAD-flow-scripts/blob/master/flow/platforms/nangate45/config.mk) · [OpenRCX 提取说明](https://openroad.readthedocs.io/en/latest/main/src/rcx/README.html)
