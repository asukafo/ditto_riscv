# ditto_riscv

通过可运行的 RTL、逐条参考对照、真实波形与性能实验学习 RISC-V core 设计。
当前开发版本是 **v7 单发射流水线、指令/数据缓存与数据提前重启**；v1–v6 独立冻结。
七版均支持 RV64IMAC、Zicsr/Zifencei、M/S/U、软件异常、中断与 Sv39/Svade。
后续目标是共享访存通路解耦、TLB、分支优化、双发射、乱序与双核，目前尚未实现这些功能。

## 快速开始

工具使用本机已配置的 Verilator、Surfer、Yosys、OpenSTA、riscv64-elf 工具链和 Python 3。
在仓库根目录执行：

```sh
make help
make check
make tools
make lint
make test
make test-icache
make test-fetch
make test-early
make test-dcache
make test-data-early
make diff PROGRAM=full_demo
make diagrams
make timing
```

根目录命令默认转发到 `versions/v7_dcache_early/`，输出位于该版的 `build/`。
`make diagrams` 导出真实流水线 VCD 的阶段采样图；`make wave PROGRAM=full_demo` 用 Surfer 打开波形。
选择旧版使用 `make test VERSION=v1_multicycle`，或进入该版本目录运行其 Makefile。
`PROGRAM`、`LATENCY`、`GAP`、`CROSS`、`LIB`、`CLOCK_NS` 等命令行参数会传给所选版本。
`make clean` 只清理当前所选版本的构建产物。

## 目录与版本

| 路径 | 内容 |
|---|---|
| [versions/v1_multicycle](versions/v1_multicycle/README.md) | 冻结的多周期核，源码对应提交 8adc22c |
| [versions/v2_single_issue](versions/v2_single_issue/README.md) | 冻结的 F / X / W 单发射流水线及其测试 |
| [versions/v3_icache](versions/v3_icache/README.md) | 冻结的物理指令缓存、合并取指、等待统计 |
| [versions/v4_fetch_buffer](versions/v4_fetch_buffer/README.md) | 冻结的半字复用、混合指令拼接与取指缓冲 |
| [versions/v5_early_restart](versions/v5_early_restart/README.md) | 冻结的关键字优先补齐与提前重启 |
| [versions/v6_dcache](versions/v6_dcache/README.md) | 冻结的256字节写穿透数据缓存 |
| [versions/v7_dcache_early](versions/v7_dcache_early/README.md) | 当前开发：D-cache关键数据优先与提前重启 |
| [benchmarks](benchmarks/README.md) | 两版执行相同二进制的公共基准程序 |
| [tools](tools/README.md) | 仓库检查与跨版本性能比较工具 |
| [results](results/README.md) | 跨版本对比记录，各版详细记录保留在各自 results/ |
| [docs](docs/README.md) | 文档导航、目录约定和历史教学实验 |

每版自带 RTL、仿真宿主、软件、测试脚本和构建配置，避免修改新版时改变旧版行为。
各版 F / X / W 实现与性能记录独立保存。架构演进创建新版本目录；代码直接提交到主分支 `main`。
具体规则见 [开发约定](CONTRIBUTING.md)。

## 每版为什么这样优化

先定位等待或重复工作，再改变硬件结构，用开关对照确认收益；每版保留源码、真实波形和测量。
下面的周期均来自对应版本的固定实验，内存延迟/背压条件同时注明，不能混用不同轮的时序估计。

| 版本 | 观察到的问题 | 设计思路 | 实测结果与代价 |
|---|---|---|---|
| v1 多周期 | 需要先建立可理解、可验证的指令执行基线 | 用状态机依次完成取指、执行、访存、提交，再补齐 ISA/特权功能 | 作为正确性与性能参照；同一时刻只推进一条指令 |
| v2 单发射流水线 | 一条指令等待时，其他执行资源闲置 | 拆分 F/X/W 状态与寄存器，重叠取指/执行/写回，用前递和冲刷处理依赖 | 低延迟独立 ALU：1339→1075 周期；高延迟求和因共享总线争用退步 |
| v3 I-cache | 循环反复从外部读取相同指令，阻塞数据访问 | 增加 256B 物理指令缓存，并合并对齐取指；MMU 先检查权限 | 延迟5/间隔3求和：6271→1371；包含取指合并贡献，冷行补齐也有开销 |
| v4 半字缓冲 | 一次读回32位后，压缩指令只消费16位，剩余半字被丢弃 | 保存高半字及其 PC，下条直接复用，普通指令跨字时拼接 | 低延迟压缩基准：345→279；缓存查询137→69，外部请求仍36 |
| v5 提前重启 | 所需指令已在第一笔数据中，却还在等整行补齐 | 优先读关键半行并提前响应，让执行与剩余补数重叠 | 低延迟压缩基准：279→245；面积约+0.38%，布局前周期仍4.32ns |
| v6 D-cache | 数据重复读取仍访问外部内存 | 增加256B物理数据缓存，读缺失分配、写穿透、写缺失不分配；原子/PTE/MMIO旁路 | 延迟5/间隔3重复读：2127→1627，外部请求136→10；同条件顺序求和1371→1499，完整补行增加等待 |
| v7 数据提前重启 | 数据缺失必须等整行补齐才能继续执行 | 优先读包含所需数据的8B并提前返回，背景补齐另一半；保持写穿透和阻塞式请求规则 | 无背压时顺序读取1054→1022周期；延迟5/间隔3仍1499，等待转移到共享通路上的取指 |

v6 首先建立写穿透 D-cache 的可验证基线。重复数据访问受益，顺序读取与冲突访问可能因完整补行变慢。
v6轮次的布局前最小周期估计为4.54ns（v5为4.32ns），面积约+21.2%；因此应同时检查周期数、时序和面积。
v7进一步降低load响应等待，但背景补数仍占用共享通路，不能保证总周期减少；布局前周期也变为4.66ns。
详细设计分别见上方版本 README，历史实验见 [性能记录](results/README.md)。

## 性能实验

```sh
make compare
# 每次使用新的 run-id；已存在时明确拒绝覆盖
make compare BENCHMARK_ARGS="--run-id my-experiment"
```

脚本检查两版程序二进制一致，逐条核对提交与最终内存，保存周期数、CPI、时序、面积和源码哈希。
合并表位于 `results/comparisons/<run-id>/`，单版记录位于 `versions/<version>/results/<run-id>/`。
[已有实验](results/README.md)包含改善和退步项；流水线不保证所有内存条件下都更快。
时序与面积使用研究用标准单元库进行布局前估计，不是硬件实测值。

## 功能与学习入口

程序通过已提交的退出邮箱存储结束；EBREAK、ECALL 由软件异常处理程序接收。
MMU 没有 TLB，采用 Svade 软件管理 A/D 位。尚无 F/D/V/H、PMP 或多核，未进行正式 ISA 合规认证或 Linux 启动验证。

- [单发射流水线、前递与精确异常](versions/v2_single_issue/README.md)
- [指令缓存、权限、FENCE.I 与等待测量](versions/v3_icache/README.md)
- [半字缓冲、混合指令与跨页拼接](versions/v4_fetch_buffer/README.md)
- [多周期核、握手、提交与波形教程](docs/README.md)
- [版本演进和实际性能分析](versions/README.md)
- [仓库结构及常用命令](docs/repository.md)
