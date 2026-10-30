# ditto_riscv

通过 RTL、仿真数据和波形学习 RISC-V core 设计。
最终目标是双发射乱序核、双核、私有 L1 和共享 L2；当前完成 **M0：多周期单核 + 可调延迟 RAM**。
已加入逐条提交跟踪和独立 Python 指令参考模型，作为下一阶段扩展的验证基础。

工具沿用本机已配置环境：**Verilator + Surfer + Yosys + OpenSTA**。
软件使用 `riscv64-elf-gcc` / `objcopy`，实验脚本使用 Python 3，无额外 Python 依赖。

```bash
make tools
make lint
make test
make diff PROGRAM=load_add_store LATENCY=5 GAP=3
make sim PROGRAM=sum LATENCY=5
make wave PROGRAM=sum LATENCY=5
make sweep
make diagrams
make synth
make timing
```

`make sim` 生成 VCD、`build/<program>.trace.jsonl` 提交记录及其 `.ram` 内存快照，并输出 JSON 统计。
`make diff` 进一步独立执行同一个程序，逐条核对提交和最终内存，显示前 16 条记录。
`make test` 自动完成 50 次仿真对照和 12 项检查器测试；`make sweep` 生成 `build/results.csv`。
`make timing` 默认使用之前安装的 Nangate45 typical 库；可覆盖 `LIB=/path/to/library.lib CLOCK_NS=10`。
`CROSS` 可覆盖交叉工具前缀，例如 Linux 上用 `CROSS=riscv64-unknown-elf-`。

| 实验 | 命令参数 | 正确结果（RAM 0x200） |
|---|---|---|
| 64 个整数求和 | `PROGRAM=sum` | 2080 |
| 寄存器依赖链 | `PROGRAM=dependency` | 128 |
| 打乱地址的指针追踪 | `PROGRAM=pointer_chase` | 2016 |
| 读、加法、写回、循环分支 | `PROGRAM=load_add_store` | 14 |

当前只是 RV64 整数指令子集：ADDI、ADD、SUB、LUI、JAL、六种条件分支、LD、SD。
`EBREAK` 暂作仿真结束标记；未实现完整异常处理和特权架构，不宣称符合 RV64I。
不支持 C/M/A、CSR、MMU、缓存、流水线重叠或多核，也还不能运行通用 C 程序或 Linux。

- [当前结构、接口与目标架构](docs/architecture.md)
- [架构设计与真实波形逐周期讲解](docs/design-walkthrough.md)
- [逐条提交跟踪与参考模型验证](docs/commit-trace.md)
- [实验方法、实际结果与波形阅读](docs/experiments.md)
- [工具和工程目录](docs/tools.md)

RTL 位于 `rtl/`，C++ 主存模型与仿真驱动位于 `sim/`，汇编程序位于 `sw/`。
构建产物保留在 `build/`，不提交到 Git。
