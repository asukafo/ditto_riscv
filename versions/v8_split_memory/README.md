# v8：独立I/D翻译与缓存命中路径

v7已经提前返回load数据，但D-cache背景补数仍阻塞共享串行路径上的取指，甚至I-cache命中也要等。
v8把取指与数据的地址翻译/缓存访问分开，让两侧命中能够独立推进。
F/X/W仍是单发射、顺序执行。本版现已冻结，默认开发入口为v9；所有版本的优化动机见[根README](../../README.md)。

## 结构：把仲裁放到真正访问外部内存的位置

```text
                   +-- I-MMU -- final instruction --> I-cache --+
Fetch ------------+                                           |
                   +--------- I page-table reads ---------------+--+
                                                               |  |
                   +-- D-MMU -- final data --------> D-cache --+  |
Execute data -----+                                           |  |
                   +--------- D page-table reads --------------+--+
                                                               |
                                           four-lane round-robin arbiter
                                                               |
                                           atomic adapter (LR/SC/AMO)
                                                               |
                                           one external memory port
```

两套MMU共用satp、特权与权限配置，但有独立的请求地址、遍历级数和响应状态；本版仍没有TLB。
物理事务有四个来源：lane0=I-cache、lane1=D-cache、lane2=I页表读取、lane3=D页表读取。
页表读取绕过缓存。缓存每次命中之前仍由各自MMU检查权限。

- `rtl/rv64_memory_system.sv`封装连接，并提供旧串行路径作为编译期开关对照。
- `rtl/rv64_physical_arbiter.sv`采用轮转选择，只有真正访问外部的请求需要争用。
- `rtl/rv64_mmu.sv`增加busy输出；翻译规则与Sv39/Svade权限判断不变。
- I-cache/D-cache的数据组织、写穿透、提前重启和失效规则沿用v7。

同一时刻可以有一个逻辑取指请求和一个逻辑数据请求，缓存命中可与另一侧补数重叠。
外部仍最多一笔事务；缓存同时缺失和并发页表读取仍会排队。没有增加发射宽度或外部端口。

## 响应归属、背压与原子顺序

每套MMU在物理请求握手时记录这笔请求进入缓存还是页表旁路，响应依据寄存的路由返回。
不能用响应时刻的d_execute/d_cache_data组合值选择来源，因为MMU在等待响应时这些请求信号可能已改变。
I/D各自的返回数据、错误和cause分别连接到前端与执行级，避免数据或故障串线。

物理仲裁器把选中请求接受到保持寄存器，即使下游还不ready，也保持地址、写数据、大小和原子元数据稳定。
选中来源一直持有所有权，直到原子适配器向其完成响应；AMO的读和写不能被另一来源插入。
轮转指针在一笔适配器事务响应完成后更新，连续请求不会永久饿死另一侧页表遍历。

串行化提交、异常、中断与返回必须等待两套MMU、缓存背景补数及物理仲裁在途事务排空。
因此CSR/satp/特权上下文更新不会与旧翻译请求混用。分支重定向仍排空并丢弃已接受的错误路径取指。
FENCE.I继续失效I-cache和半字缓冲，数据侧写穿透保证已完成的代码存储到达内存。
LR/SC/AMO仍旁路D-cache，bus_lock与reservation_invalidate规则保留；没有多核一致性协议。

`SPLIT_MEMORY=0`恢复v7的虚拟请求仲裁和串行MMU→D-cache→I-cache连接。
本轮30组关闭路径分离后的周期数、外部请求数与同轮v7完全一致。
其他缓存开关现在都是在各自版本连接结构内做对照，不能把v8关闭D-cache当作v5。

## 实测：解除命中路径阻塞

[本轮90组主对照](../../results/comparisons/20261101T103746277794Z/comparison.csv)
比较v5/v7/v8，程序二进制一致，每条提交与最终64KiB RAM通过独立模型校验。
[30组路径分离开关对照](results/20261101T103746277794Z/split-memory-ablation.csv)
与其他缓存/缓冲开关结果分别保留；旧实验未覆盖。

| 程序 | 延迟1/间隔0：v7→v8周期 | 延迟5/间隔3：v7→v8周期 |
|---|---:|---:|
| 顺序求和 | 1022→923 | 1499→1111 |
| 指针追踪 | 1246→1051 | 2135→1871 |
| 裸机C | 517→451 | 1055→963 |
| M/A/C C | 499→470 | 883→843 |
| 重复读同一数据 | 1566→1437 | 1627→1491 |
| 独立ALU | 742→742 | 1623→1623 |

高延迟有背压求和的frontend_starved从449降到168，观察到127次I-cache命中与D-cache补数状态重叠。
同条件v5求和为1371周期，v8已减少到1111；但指针追踪v5为1631周期，v8的1871仍较高。
不同程序的最优版本不同。v8也移除了缓存命中前的虚拟端统一仲裁交接，部分改善来自这项固定等待减少。

外部请求的主要数据补数策略没有改变。统计截至退出存储提交，包含推测取指和未结束的补数：
例如高延迟求和74→73次、低延迟压缩程序36→37次，尾部进度会改变一笔请求，不能把它当成数据带宽优化。

相同Nangate45 typical约束下，布局前最小周期4.66→4.83ns，单元面积126613.872→129741.500，
分别增加约3.65%和2.47%。高延迟有背压求和的时间模型从6985.34ns降到5366.13ns，约改善23.18%；
相对v5的5922.72ns约改善9.40%。独立ALU总周期不变，估计时间则因时钟周期更长而退步。
这些是布局前估计，不是硬件实测；关闭配置未独立测量时序，不套用默认周期计算其时间。

## 观察信号与指标范围

instruction_hits_during_data_fill统计I-cache请求命中且D-cache处于补数请求/响应状态的次数；
data_hits_during_instruction_fill是反方向计数。宿主在沿前采样，不增加新的RTL64位反馈计数器。
补数状态包含等待物理仲裁的阶段，不等于每个计数时刻都已有外部读取在途。

frontend_starved和data_wait的定义沿用旧版，可用于对照。
v8的data_blocked_by_fetch/fetch_blocked_by_data统计物理四路仲裁等待；旧版统计虚拟端统一仲裁等待，
范围不同，不把它们直接当作同口径的停顿改善。比较器优先采样顶层事件与宿主计数交叉验证。

## 实际波形与验证

[并发采样图](docs/waveforms/split-memory.svg)来自真实build/split-memory.vcd，latency=5、gap=3。
C51、C53、C55的I-cache命中发生在D-cache补数期间；C52/C54/C56有取指响应，
C53/C55/C57继续发射，C55/C57/C59继续提交。地址0x3008的剩余数据直到C58才返回。
这直接显示了取指和执行在背景补数期间继续推进。控制采沿前，commit采沿后；CSV同步保存。

仲裁器单元测试检查144笔事务的元数据、唯一响应归属、请求背压和轮转公平性。
独立内存子系统49项检查覆盖双侧同时页表遍历、双向命中与补数重叠、暖行后的权限拒绝、
一侧故障时另一侧正常返回、页表总线错误、重映射与双侧返回背压。
新增25组整核测试检查顺序读、写穿透、AMO竞争、FENCE.I代码更新和精确访问故障，另有6组新旧路径对照。
原有整数/特权/原子/MMU/缓存回归全部保留。311组整核测试在RTL与门级分别通过，
622份提交/最终内存文件逐字节一致。门级使用标准单元逻辑模型，不含SDF延迟。

```sh
# 仓库根目录，明确选择冻结的v8
make lint test VERSION=v8_split_memory
make test-split VERSION=v8_split_memory
make test-mapped VERSION=v8_split_memory
make diagrams VERSION=v8_split_memory
make compare BENCHMARK_ARGS="--versions v5_early_restart v7_dcache_early v8_split_memory"
make test VERSION=v7_dcache_early
```
