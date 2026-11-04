# v27 与 v29 布局前时序对照

相同 Yosys、OpenSTA、Nangate45 typical Liberty、ABC 驱动/负载与 OpenSTA 约束。两版均用 10 ns 时钟约束、1 ns 输入和输出延迟。映射后结构检查通过。报告使用理想时钟、标准单元延迟与工具估计负载，未纳入布局布线寄生或时钟树。[工具、库哈希与数值](summary.json)

| 指标 | v27 | v29 | 变化 |
| --- | ---: | ---: | ---: |
| 60 组总周期 | 28,937 | 27,294 | −5.68% |
| 寄存器间 setup 下限 | 10.4353 ns | 10.8690 ns | +4.16% |
| 含全部约束端口的 setup 下限 | 11.4229 ns | 11.6173 ns | +1.70% |
| 标准单元映射面积 | 369,441.016 | 370,905.612 | +0.40% |
| 总周期 × 寄存器间下限 | 301.97 µs | 296.66 µs | −1.76% |
| 总周期 × 全端口下限 | 330.54 µs | 317.08 µs | −4.07% |

两版在 10 ns 约束下都存在 setup 违例。全端口下限由 10 ns 减去最差 setup slack 得到，包括事件输出的 1 ns 延迟约束。面积是同一 Liberty 的单元面积总和。表中的时间是同条件估计，尚无物理实现测量。

两版寄存器间最差路径都起于 X 阶段 `insn[31]`。v27 终止于取指窗口 `spec_pc[19]`，v29 终止于 I-TLB 的 `permissions[2][0]`。包含输出端口时，最差终点分别为 `prefetch_path_redirect_event` 与 `itlb_fill_event`。

单独筛选接口路径时，v29 经数据请求 valid 的最差 slack 为 +4.2954 ns，经 I-cache 响应 valid 为 +5.0576 ns，经 D-cache 响应 valid 为 −0.0744 ns。外部请求地址/valid 路径最差 slack 从 −0.5674 ns 到 −0.5720 ns。各筛选组可有不同的起终点。它们描述穿过该接口的完整路径，不能直接当作新增逻辑自身的延迟。

[v27 全约束报告](v27_integer_pair-timing.txt) · [v29 全约束报告](v29_ifill_turnover-timing.txt) · [v27 接口分组](v27_integer_pair-path-groups.txt) · [v29 接口分组](v29_ifill_turnover-path-groups.txt)

## branch_forward 对照

同一镜像在延迟 5、间隔 3 下，v24 用 347 周期，v29 用 371 周期。两版均通过 262 条退休和全部 64 KiB RAM 对照。控制流误判均为 4、物理请求均为 9、I-cache 缺失均为 4。取指窗口丢弃数从 9 增到 55，X 当拍完成但前端无可接续指令的采样从 6 增到 96。下一阶段应检查窗口重定向和可用返回的衔接。丢弃数是事件计数，不能直接换算成损失周期。

[上升沿分类](branch-forward-cycles.csv) · [接口事件](branch-forward-events.json)

## 复现

从仓库根目录运行两版 `make timing VERSION=版本名 CLOCK_NS=10`。接口分组复用该版时序脚本的读库、链路和约束段。在版本目录运行下列命令。

```sh
sed '/check_setup/,$d' scripts/timing.tcl > build/path-groups.tcl
cat ../../results/timing/v27-v29/path-groups.tcl >> build/path-groups.tcl
LIB="$HOME/.local/opt/opensta/share/lib/NangateOpenCellLibrary_typical.lib" \
  CLOCK_NS=10 sta -exit build/path-groups.tcl
```
