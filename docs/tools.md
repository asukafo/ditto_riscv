# 工具与目录

本项目按“在这个电脑上安装verilator”对话中配置的工具开发。
不依赖 Icarus Verilog 或 GTKWave。用 `make tools` 检查本机命令。

| 工具 | 本机已确认 | 用途 |
|---|---|---|
| Verilator | 5.052 | lint、RTL 转 C++、周期仿真、VCD |
| Surfer | 0.7.0 | 打开生成的 VCD |
| Yosys | 0.70+post | 综合、逻辑映射、网表导出 |
| OpenSTA | 已安装，先前验证为 3.1.0 | 网表静态时序分析 |
| riscv64-elf-gcc | 15.1.0 | RV64I 汇编与链接 |
| Python 3 | 系统提供 | 生成数据、回归、CSV |

本机源码构建 OpenSTA 的示例与 Nangate45 库位于 `~/.local/opt/opensta/share/`。
项目不复制整个外部工具或工艺库；其他机器可用 `make timing LIB=/path/to/file.lib`。

`make synth` 执行 Yosys 通用综合、`check -assert` 并导出 `build/core_netlist.v`。
`make timing` 额外执行标准单元映射，生成 `build/core_mapped.v`、`mapping.log` 与 `timing.log`。
时钟默认 10 ns，输入/输出延迟假设 1 ns，输入 transition 为 0.1、输出 load 为 0.01，单位依赖库。
目前使用 Nangate45 typical 时分别为 ns 和 pF；换库必须重新审视约束。

这只是布局前探索：没有实际布线寄生、时钟树、PVT 多角分析或 SRAM 宏映射。
寄存器堆和调试计数器也计入综合。不能把结果当作真实芯片最高频率、面积或功耗签核。
本阶段未接活动标注与功耗回归；OpenSTA 的平均功耗流程留待有代表性负载和映射活动后加入。

初版 M0（提交 4b40c85）已实际跑通通用综合、Nangate45 映射与 OpenSTA 报告。
该版本默认 10 ns 约束下 setup 未满足，报告的最小时钟周期约 26.89 ns。
提交跟踪信号也会计入后续综合；修改 RTL 后以重新生成的 build/timing.log 为准。
这表明当前多周期教学 RTL 还需要时序优化；该数字仅对应此映射和约束，不能作为硅片频率承诺。
特别是高扇出控制网络还没有经过物理优化。后续应比较流水线划分、扇出与关键路径，
并区分“工具成功生成报告”和“设计满足时序约束”。

```text
rtl/rv64_core.sv       可综合单核、状态机、寄存器堆、计数器
sim/main.cpp          时钟、复位、事务主存、超时与波形
sw/*.S                五个独立裸机汇编实验
scripts/pointers.py   可重复的指针数据
scripts/experiments.py 结果、反压、错误路径与性能回归
scripts/reference.py  独立指令语义、逐条提交和完整内存对照
scripts/test_reference.py 检查器的正常与故意损坏输入测试
scripts/alu_tests.py   汇编编码的 ALU 边界/随机/别名向量与单独数学结果检查
scripts/timing.tcl    OpenSTA 时序约束和报告
docs/                 架构、实验方法、工具说明
build/                自动生成，不提交 Git
```
