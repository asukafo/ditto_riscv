# ditto_riscv

通过 RTL、仿真数据和波形学习 RISC-V core 设计。
最终目标是双发射乱序核、双核、私有 L1 和共享 L2。
当前已实现 **52 条 RV64I 基础指令的执行行为**，使用多周期顺序单核、可调延迟 RAM、逐条提交对照和裸机 C 运行环境。
ECALL/EBREAK 及错误访问交给宿主终止异常环境处理；尚无机器态 CSR、异常处理程序或正式 ISA 合规认证。

工具沿用本机已配置环境：**Verilator + Surfer + Yosys + OpenSTA**。
软件使用 `riscv64-elf-gcc` / `objcopy`，实验脚本使用 Python 3，无额外 Python 依赖。

```bash
make tools
make lint
make test
make diff PROGRAM=load_add_store LATENCY=5 GAP=3
make diff PROGRAM=bit_ops
make diff PROGRAM=c_demo
make test-alu
make test-rv64i
make sim PROGRAM=sum LATENCY=5
make wave PROGRAM=sum LATENCY=5
make sweep
make diagrams
make synth
make timing
```

`make sim` 生成 VCD、`build/<program>.trace.jsonl` 提交记录及其 `.ram` 内存快照，并输出 JSON 统计。
`make diff` 进一步独立执行同一个程序，逐条核对提交和最终内存，显示前 16 条记录。
`make test` 自动运行基础回归、检查器测试、876 组 ALU 向量和 RV64I 专项测试。
专项测试覆盖全部 52 条基础指令、555 组 W 运算、58 组不同宽度读取，以及 C 程序的 -O0/-O2 编译结果。
`make test-alu` / `make test-rv64i` 可单独运行对应测试；`make sweep` 生成 `build/results.csv`。
`make timing` 默认使用之前安装的 Nangate45 typical 库；可覆盖 `LIB=/path/to/library.lib CLOCK_NS=10`。
`CROSS` 可覆盖交叉工具前缀，例如 Linux 上用 `CROSS=riscv64-unknown-elf-`。

| 实验 | 命令参数 | 正确结果（RAM 0x200） |
|---|---|---|
| 64 个整数求和 | `PROGRAM=sum` | 2080 |
| 寄存器依赖链 | `PROGRAM=dependency` | 128 |
| 打乱地址的指针追踪 | `PROGRAM=pointer_chase` | 2016 |
| 读、加法、写回、循环分支 | `PROGRAM=load_add_store` | 14 |
| 位运算、移位与比较 | `PROGRAM=bit_ops` | `0x7ffffffffffffffc` |
| C 函数调用、栈、全局数据和混合宽度读写 | `PROGRAM=c_demo` | 1488 |

支持：19 条普通整数计算、9 条 W 运算、7 种读取、4 种写入、6 种分支、LUI/AUIPC/JAL/JALR、FENCE、ECALL/EBREAK。
程序正常退出使用 `sw/finish.inc` 的仿真邮箱协议；**EBREAK 现在产生断点异常，不再作为成功提交的结束标记**。
不支持 M/A/C/F/D 等扩展、Zicsr/Zifencei、MMU、缓存、流水线重叠或多核，不能运行 Linux。
`-march=rv64i -mabi=lp64` 的无 libc 小型裸机 C 程序已验证，完整说明见 [RV64I 执行与环境](docs/rv64i.md)。

- [当前结构、接口与目标架构](docs/architecture.md)
- [架构设计与真实波形逐周期讲解](docs/design-walkthrough.md)
- [逐条提交跟踪与参考模型验证](docs/commit-trace.md)
- [整数位运算、移位与比较实验](docs/integer-alu.md)
- [52 条 RV64I、异常、窄访存和裸机 C](docs/rv64i.md)
- [实验方法、实际结果与波形阅读](docs/experiments.md)
- [工具和工程目录](docs/tools.md)

RTL 位于 `rtl/`，C++ 主存模型与仿真驱动位于 `sim/`，汇编程序位于 `sw/`。
构建产物保留在 `build/`，不提交到 Git。
