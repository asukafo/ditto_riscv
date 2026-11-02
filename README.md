# ditto_riscv

通过可运行的 RTL、逐条参考对照、真实波形与性能实验学习 RISC-V core 设计。
当前开发版本是 **v19 需求响应旁路、沿BTB/gshare/RAS预测路径预取、多笔I侧在途取指、4项指令FIFO、BTB/gshare、独立I/D TLB与缓存**；v1–v18 独立冻结。
十九版均支持 RV64IMAC、Zicsr/Zifencei、M/S/U、软件异常、中断与 Sv39/Svade。
后续目标是共享总线等待优化、大页TLB、双发射、乱序与双核，目前尚未实现这些功能。

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
make test-split
make test-predict
make test-ras
make test-tlb
make test-bht
make test-gshare
make test-btb
make test-queue
make test-ifetch
make test-window
make test-path
make test-forward
make diff PROGRAM=full_demo
make diagrams
make timing
```

根目录命令默认转发到 `versions/v19_window_forward/`，输出位于该版的 `build/`。
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
| [versions/v7_dcache_early](versions/v7_dcache_early/README.md) | 冻结的D-cache关键数据优先与提前重启 |
| [versions/v8_split_memory](versions/v8_split_memory/README.md) | 冻结的独立I/D翻译、缓存命中与共享物理仲裁 |
| [versions/v9_static_predict](versions/v9_static_predict/README.md) | 冻结的向后分支预测跳转与JAL目标预测 |
| [versions/v10_return_stack](versions/v10_return_stack/README.md) | 冻结的8项提交时维护的返回地址栈 |
| [versions/v11_tlb](versions/v11_tlb/README.md) | 冻结的各8项I/D TLB、权限复查与失效 |
| [versions/v12_dynamic_predict](versions/v12_dynamic_predict/README.md) | 冻结的32项两位BHT，提交训练与静态冷启动 |
| [versions/v13_gshare](versions/v13_gshare/README.md) | 冻结的4位提交历史、32项计数器、保存索引训练 |
| [versions/v14_btb](versions/v14_btb/README.md) | 冻结的32项带标签BTB、请求时目标预测、提交训练 |
| [versions/v15_fetch_queue](versions/v15_fetch_queue/README.md) | 冻结的4项完整指令FIFO |
| [versions/v16_ifetch_pipeline](versions/v16_ifetch_pipeline/README.md) | 冻结的I-cache/TLB命中交接、响应背压与提前排空 |
| [versions/v17_fetch_window](versions/v17_fetch_window/README.md) | 冻结的4请求槽位、失效响应归属，整核2笔I侧在途 |
| [versions/v18_btb_window](versions/v18_btb_window/README.md) | 冻结的预测路径读取窗口、槽内预测保存及字节复核 |
| [versions/v19_window_forward](versions/v19_window_forward/README.md) | 当前开发：需求响应旁路、反压存储与同拍后继需求 |
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
| v8 分离I/D路径 | D-cache补数期间，I-cache命中也被串行路径阻塞 | 独立MMU/缓存路径，仅页表读取与外部缺失请求经四路轮转仲裁；外部仍单笔事务 | 延迟5/间隔3求和1499→1111，前端等待449→168；面积约+2.47%，布局前周期4.66→4.83ns |
| v9 静态分支预测 | 循环向后跳转反复冲刷顺序取指，求和64条分支产生63次冲刷 | 完整指令在F预测下一PC，向后条件分支预测跳转、向前不跳、JAL直接预测；预测随指令送X核对 | 延迟5/间隔3求和1111→983、冲刷63→1；面积约+1.71%，本轮布局前周期4.83→4.64ns；短访存程序195→199周期 |
| v10 返回地址栈 | v9仍不预测函数返回，裸机C有6次返回失误 | 8项RAS在调用/返回提交时更新，F用栈顶预测常见ret；异常和串行化时清空，错误预测仍由X恢复 | 延迟5/间隔3调用基准379→343、返回失误16→0；裸机C955→943，但布局前周期4.64→4.86ns，C程序估计时间反而退步，面积约+3.70% |
| v11 I/D TLB | 分页访问即使缓存命中，也要重复读取多级页表 | 两侧各8项全相联4KiB翻译，保存VPN/物理页/权限/完整satp标签；命中复查权限，SFENCE.VMA全部失效 | 分页循环延迟5/间隔3：8859→1131周期，页表读取978→6，外部请求1003→31；裸地址程序周期不变；面积约+19.75% |
| v12 动态分支预测 | 向前长期跳转仍被静态规则反复预测错误 | 增加32项两位BHT，冷索引回退BTFNT；只在提交时用真实方向训练，保留X核对恢复 | 延迟5/间隔3向前恒跳719→591、阶段变化851→791；交替851→915、冲突479→547；本轮只测周期，暂不分析时序/面积 |
| v13 gshare | v12对交替方向反复猜错，索引冲突相互干扰 | 将4位提交历史与PC索引异或，仍用32项两位计数器；查询索引随F/X/W保存，提交时精确更新 | 延迟5/间隔3交替915→791、冲突547→423、相关分支1115→871；向前恒跳591→595、阶段变化791→795；只测周期 |
| v14 BTB | 重复寄存器间接调用仍等待X算目标 | 32项带完整高位PC标签BTB，请求时查询并保存目标，完整指令复核类型/长度/直接目标；方向及时刷新 | 延迟5/间隔3间接调用379→351、间接目标失误16→1；旧17程序51组周期/请求/控制失误不变；单笔取指仍限制吞吐 |
| v15 取指队列 | X等待load/div时，F只有一个完整指令寄存器，随之停取指 | 增加4项333位FIFO，空时旁路、满时可同时出入，重定向清空；仍单笔在途取指 | 延迟5/间隔3求和983→855、除法后独立指令515→463、C程序943→887；位操作199→207、压缩依赖427→431；只测周期 |
| v16 命中交接 | 命中访问返回后仍有请求气泡 | 缓存/MMU响应与新请求同周期交接，合法ITLB命中直送物理访问，F可连发完整对齐指令 | 延迟5/间隔3直线ALU1623→1359、分页1059→735；仍单笔在途 |
| v17 请求窗口 | 需要多个尚未返回的取指地址和严格响应归属 | 4槽地址窗口、注册响应级、完成令牌与poison；旧响应返回前不复用槽位 | 整核实测2笔I侧在途、外部总线仍1笔；压缩431→411，但C847→927、间接调用223→383，尚未全面跑赢v16 |
| v18 预测路径窗口 | v17顺序预取浪费调用/返回后的槽位 | 独立BTB/gshare查询副本与提交RAS引导读取，保存槽内预测并复核返回字节 | 延迟5/间隔3间接调用383→251、调用367→235；冲突495→499，仍未全面超过v16；只测周期 |
| v19 需求返回旁路 | 返回必须先写窗口寄存器，下一拍F才可接收 | 当前未完成需求按令牌匹配返回直接送F，反压时继续保存，支持同拍后继 | 延迟5/间隔3重复读999→867、交替559→487、压缩411→379；相关559→563，仍未全面超过v16；只测周期 |

v6 首先建立写穿透 D-cache 的可验证基线。重复数据访问受益，顺序读取与冲突访问可能因完整补行变慢。
v6轮次的布局前最小周期估计为4.54ns（v5为4.32ns），面积约+21.2%；因此应同时检查周期数、时序和面积。
v7降低load响应等待，v8再解除命中路径间的阻塞；两侧同时缺失时仍争用单个外部端口。
各版需同时比较总周期和布局前时钟周期，不保证所有程序、所有内存条件都更快。
详细设计分别见上方版本 README，历史实验见 [性能记录](results/README.md)。

## 性能实验

```sh
make compare BENCHMARK_ARGS="--versions v16_ifetch_pipeline v18_btb_window v19_window_forward --cycles-only"
# 每次使用新的 run-id；已存在时明确拒绝覆盖
make compare BENCHMARK_ARGS="--run-id my-experiment"
```

当前`make compare`使用`tools/ifetch_experiments.py`，检查三版二进制一致、逐条提交和最终内存，只测周期及请求行为。旧的`tools/benchmark.py`保留v1–v15的时序/面积实验入口。
合并表位于 `results/comparisons/<run-id>/`，单版记录位于 `versions/<version>/results/<run-id>/`。
[已有实验](results/README.md)包含改善和退步项；流水线不保证所有内存条件下都更快。
时序与面积使用研究用标准单元库进行布局前估计，不是硬件实测值。

## 功能与学习入口

程序通过已提交的退出邮箱存储结束；EBREAK、ECALL 由软件异常处理程序接收。
MMU 配有各8项I/D TLB，只缓存4KiB映射，采用Svade软件管理A/D位；大页仍由遍历器处理。尚无F/D/V/H、PMP或多核，未进行正式ISA合规认证或Linux启动验证。

- [单发射流水线、前递与精确异常](versions/v2_single_issue/README.md)
- [指令缓存、权限、FENCE.I 与等待测量](versions/v3_icache/README.md)
- [半字缓冲、混合指令与跨页拼接](versions/v4_fetch_buffer/README.md)
- [多周期核、握手、提交与波形教程](docs/README.md)
- [版本演进和实际性能分析](versions/README.md)
- [仓库结构及常用命令](docs/repository.md)
