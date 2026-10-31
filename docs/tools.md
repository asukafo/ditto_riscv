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
ABC 通过 `-constr scripts/abc.constr` 开启缓冲与驱动尺寸优化，默认驱动单元为 BUF_X1。
换工艺库时还应通过 `ABC_OPTIONS='-constr /path/to/abc.constr'` 指定匹配的单元和负载；
`ABC_OPTIONS=` 可复现未开启该优化的映射流程。OpenSTA 的接口约束另在 scripts/timing.tcl 中维护。
时钟默认 10 ns，输入/输出延迟假设 1 ns，输入 transition 为 0.1、输出 load 为 0.01，单位依赖库。
目前使用 Nangate45 typical 时分别为 ns 和 fF；因此 set_load 0.01 是 0.01 fF，并非 0.01 pF。
这些 I/O 数值只是初始假设，换库或确定实际接口后必须重新审视约束。

这只是布局前探索：没有实际布线寄生、时钟树、PVT 多角分析或 SRAM 宏映射。
寄存器堆和调试计数器也计入综合。不能把结果当作真实芯片最高频率、面积或功耗签核。
本阶段未接活动标注与功耗回归；OpenSTA 的平均功耗流程留待有代表性负载和映射活动后加入。

初版 M0（提交 4b40c85）已实际跑通通用综合、Nangate45 映射与 OpenSTA 报告。
该版本默认 10 ns 约束下 setup 未满足，报告的最小时钟周期约 26.89 ns。
提交跟踪信号也会计入后续综合；修改 RTL 后以重新生成的 build/timing.log 为准。
这表明当前多周期教学 RTL 还需要时序优化；该数字仅对应此映射和约束，不能作为硅片频率承诺。
特别是高扇出控制网络还没有经过物理优化。后续应比较流水线划分、扇出与关键路径，
并区分“工具成功生成报告”和“设计满足时序约束”。
当前已加入逻辑映射阶段的缓冲与尺寸优化，仍未进行实际物理优化。
默认扩展核本轮估计为 4.32 ns，具体对照见 [时序优化实验](timing-optimization.md)。

```text
rtl/rv64_core.sv       顶层连接、取指状态与提交控制
rtl/rv64_*.sv          独立译码、ALU、寄存器堆、乘除、LSU、原子、CSR、压缩、MMU
sim/main.cpp          时钟、复位、事务主存、超时与波形
sw/*.S                五个汇编示例及 C 启动代码
sw/c_demo.c           含栈、间接调用和混合宽度数据的裸机 C 示例
sw/full_demo.c        M/A/C/CSR 的原生 C 示例，预期 949
sw/machine_demo.S     软件处理三次异常并 MRET 返回，预期 3
sw/link.ld            启动/正文/数据/BSS/栈布局
sw/finish.inc         仿真退出邮箱宏
scripts/pointers.py   可重复的指针数据
scripts/experiments.py 结果、反压、错误路径与性能回归
scripts/reference.py  独立指令语义、逐条提交和完整内存对照
scripts/test_reference.py 检查器的正常与故意损坏输入测试
scripts/alu_tests.py   汇编编码的 ALU 边界/随机/别名向量与单独数学结果检查
scripts/rv64i_tests.py 52 条指令覆盖、W/访存/控制/异常与 C 集成回归
scripts/full_reference.py 原生压缩、M/A、CSR、M/S/U、IRQ 与 Sv39 独立语义模型
scripts/extension_tests.py M/A/C/CSR 和扩展 C 程序回归
scripts/privileged_tests.py 特权、异常/中断、页表/权限/跨页和 Svade 重试回归
scripts/test_full_reference.py 扩展检查器的故意损坏输入测试
scripts/timing.tcl    OpenSTA 时序约束和报告
docs/                 架构、实验方法、工具说明
build/                自动生成，不提交 Git
```

默认可执行文件为 build/full_obj/Vrv64_core；build/obj_dir/Vrv64_core 保留原 RV64I 配置。
make synth/timing 综合默认扩展配置，需对真实内存互连正确实现 bus_lock、req_store_check 和保留失效输入。
当前默认配置已重新综合与映射，结构检查为零问题；布局前时钟周期估计约 19.64 ns，仍未达到 10 ns。
