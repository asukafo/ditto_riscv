# ditto_riscv

通过 RTL、仿真数据和波形学习 RISC-V core 设计。
最终目标是双发射乱序核、双核、私有 L1 和共享 L2。
当前默认配置为 **模块化 RV64IMAC + Zicsr/Zifencei，M/S/U 特权、软件异常处理、中断与 Sv39/Svade MMU**。
使用多周期顺序执行、可调延迟 RAM、逐条参考模型对照与裸机 C 环境。尚未进行正式 ISA 合规认证。

工具沿用本机已配置环境：**Verilator + Surfer + Yosys + OpenSTA**。
软件使用 `riscv64-elf-gcc` / `objcopy`，实验脚本使用 Python 3，无额外 Python 依赖。

```bash
make tools
make lint
make test
make diff PROGRAM=load_add_store LATENCY=5 GAP=3
make diff PROGRAM=bit_ops
make diff PROGRAM=c_demo
make diff PROGRAM=machine_demo
make diff PROGRAM=full_demo
make test-full
make test-base
make test-alu
make test-rv64i
make sim PROGRAM=sum LATENCY=5
make wave PROGRAM=sum LATENCY=5
make sweep
make diagrams
make synth
make timing
make test-mapped
```

`make sim` 生成 VCD、`build/<program>.trace.jsonl` 提交记录及其 `.ram` 内存快照，并输出 JSON 统计。
`make diff` 进一步独立执行同一个程序，逐条核对提交和最终内存，显示前 16 条记录。
`make test` 运行 RV64I 兼容回归和默认扩展配置的全部测试。
`make test-base` 保留旧配置，覆盖 52 条 RV64I、876 组 ALU/555 组 W 向量和原周期计数。
`make test-full` 验证 M/A/C、CSR、软件异常返回、IRQ、Sv39、跨页取指及扩展 C 程序；另外检查故意损坏的执行记录。
`make test-alu` / `make test-rv64i` 可单独运行对应测试；`make sweep` 生成 `build/results.csv`。
`make timing` 默认使用之前安装的 Nangate45 typical 库；可覆盖 `LIB=/path/to/library.lib CLOCK_NS=10`。
映射默认加入缓冲与单元尺寸优化，时序报告同时显示扇出、电容和转换时间。
`make test-mapped` 重新映射并用 Liberty 生成的功能模型运行扩展/特权门级回归；不含 SDF 延迟。
本次最小周期估计从 19.64 ns 改善到 4.32 ns，原理、代价和复现方法见 [时序优化实验](docs/timing-optimization.md)。
`CROSS` 可覆盖交叉工具前缀，例如 Linux 上用 `CROSS=riscv64-unknown-elf-`。

| 实验 | 命令参数 | 正确结果（RAM 0x200） |
|---|---|---|
| 64 个整数求和 | `PROGRAM=sum` | 2080 |
| 寄存器依赖链 | `PROGRAM=dependency` | 128 |
| 打乱地址的指针追踪 | `PROGRAM=pointer_chase` | 2016 |
| 读、加法、写回、循环分支 | `PROGRAM=load_add_store` | 14 |
| 位运算、移位与比较 | `PROGRAM=bit_ops` | `0x7ffffffffffffffc` |
| C 函数调用、栈、全局数据和混合宽度读写 | `PROGRAM=c_demo` | 1488 |
| 连续处理非法指令、ECALL、EBREAK 后 MRET 返回 | `PROGRAM=machine_demo` | 3 |
| M 乘除法、A 原子操作、C 压缩代码和 CSR 的 C 程序 | `PROGRAM=full_demo` | 949 |

RV64I 的 52 条基础指令已执行覆盖；扩展配置增加完整整数 M、A、RV64C 整数压缩指令、六条 CSR 操作及 FENCE.I。
程序正常退出使用 `sw/finish.inc` 的仿真邮箱协议；**EBREAK 现在产生断点异常，不再作为成功提交的结束标记**。
默认由 mtvec/stvec 指向的软件处理异常，中断在指令边界精确进入；MRET/SRET 返回。
Sv39 采用无 TLB 遍历和 Svade 软件管理 A/D 位。原子适配器提供 bus_lock 和外部 reservation_invalidate 接口，接共享互连时必须正确连接。
未实现 F/D/V/H、PMP 项、缓存、乱序或多核；没有经过 Linux 启动验证。详细范围见 [模块与特权系统](docs/modular-core.md)。

`make sim/diff/wave` 默认使用 build/full_obj/Vrv64_core。
旧配置可显式指定 `SIMULATOR=build/obj_dir/Vrv64_core`；`make sweep/diagrams` 固定使用旧 RV64I 配置，保持性能与波形基线可比。

- [当前结构、接口与目标架构](docs/architecture.md)
- [模块拆分、CSR、中断、M/A/C 与 Sv39 的实现边界](docs/modular-core.md)
- [架构设计与真实波形逐周期讲解](docs/design-walkthrough.md)
- [逐条提交跟踪与参考模型验证](docs/commit-trace.md)
- [整数位运算、移位与比较实验](docs/integer-alu.md)
- [52 条 RV64I、异常、窄访存和裸机 C](docs/rv64i.md)
- [实验方法、实际结果与波形阅读](docs/experiments.md)
- [工具和工程目录](docs/tools.md)

RTL 位于 `rtl/`，C++ 主存模型与仿真驱动位于 `sim/`，汇编程序位于 `sw/`。
构建产物保留在 `build/`，不提交到 Git。
