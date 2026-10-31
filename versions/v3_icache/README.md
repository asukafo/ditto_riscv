# v3：单发射流水线与物理指令缓存

沿用 v2 的 F / X / W 顺序流水线，增加指令缓存、对齐指令合并取指和等待原因统计。
v1、v2 的实现独立冻结。保留 RV64IMAC、Zicsr/Zifencei、M/S/U、精确异常、中断与 Sv39/Svade。

## 数据路径与权限

```text
+---------+             +------------------+
| F fetch |-----------> | one-port arbiter | <---- X load/store/atomic
+---------+             +------------------+
                                  |
                              MMU / Sv39
                         permissions checked first
                                  |
                     physical instruction cache
                     PTE / data / MMIO bypass
                                  |
                         atomic adapter / lock
                                  |
                           physical memory
```

缓存放在 MMU 之后，使用物理地址索引和标记，命中也不能绕过虚拟地址翻译与执行权限检查。
MMU 为真正的指令数据读取输出 d_execute，页表读取始终为数据访问，因此页表不会被 I-cache 缓存。
虚拟别名共享同一个物理缓存行；重新映射到不同物理页时，物理标记决定命中与替换。
本版没有 TLB，Sv39 每次取指仍可能产生页表读取，缓存不能消除这部分流量。

## 第一版缓存的具体配置

| 项目 | 实现 |
|---|---|
| 容量 | 256 字节指令数据 |
| 组织 | 16 行，直接映射，每行 16 字节 |
| 可缓存区域 | 当前平台的物理 RAM 0x0000–0xffff |
| 地址划分 | 偏移 [3:0]，索引 [7:4]，标记 [15:8]；更高地址全部旁路 |
| 缺失补齐 | 两次连续的 8 字节普通读取 |
| 命中 | 接收请求后，下一周期提供寄存的响应 |
| 在途数量 | 阻塞式，一次只处理一个上游请求 |
| 存储器实现 | 可综合寄存器数组，尚未映射为 SRAM 宏 |

缓存区域是本仿真平台的显式属性：整行都处于无副作用、权限均匀的 RAM 中。
不能直接把该条件套到新的 SoC 地址图。扩展到外部 DDR/ROM 或 PMP 时需要配套更新 PMA/权限设计。
PTE、Load/Store、原子和 MMIO 访问均按原始字段旁路，原子适配器继续负责 LR/SC、AMO 与 bus_lock。
数据访问不会隐式更新缓存中的指令字节，软件修改代码需要执行 FENCE.I。

缺失时先使目标行无效，最后一个补齐响应成功后才发布整行。任一补齐出错都会向 MMU 返回访问错误，
失败的行不会成为命中。请求和响应均支持背压；失效发生在补齐期间时，旧补齐仍收完，但不能重新置有效。

## 取指与 FENCE.I

首地址按 4 字节对齐时读取一个 32 位字，普通指令无需再读取两个半字。
压缩指令仍按实际长度 2 字节推进。半字对齐的普通指令继续分两次读取；
因此从页面或缓存行最后两个字节开始的普通指令仍能分别检查后半部分的翻译、权限与访问错误。
当前没有保存对齐读取中未消费的上半字，连续压缩指令仍有进一步优化空间。

FENCE.I 在 W 提交前等待旧事务排空，在提交沿清空缓存有效位，并重定向、清除前端预取。
这样后续取指会重新获得先前已可见的代码存储。该做法符合
[RISC-V Zifencei 的本 hart 指令流同步要求](https://docs.riscv.org/reference/isa/unpriv/zifencei.html)。
分支冲刷不会清空整个缓存；错误路径请求收完后丢弃，其缓存行可能保留。

## 如何测量瓶颈

仿真宿主在上升沿之前采样事件，在 C++ 中计数，避免把额外的 64 位统计计数器接入关键控制路径。
以下计数并非互斥，不能直接相加当成总周期数：

| 指标 | 含义 |
|---|---|
| icache_hits / icache_misses | MMU 后实际接收的可缓存指令请求，包含之后被冲刷的请求 |
| icache_refill_requests | 已被外部内存接受的 8 字节补齐读取次数 |
| icache_miss_wait | 处于补齐请求/等待响应状态的周期数 |
| frontend_starved_cycles | X 为空、F 无完整指令，且不处于系统串行化或中断暂停 |
| data_blocked_by_fetch_cycles | 数据请求等待当前取指事务占用的仲裁器 |
| fetch_blocked_by_data_cycles | 取指请求因数据优先或正在处理数据事务而等待 |
| discarded_fetch_responses | 分支/系统重定向后丢弃的取指响应次数 |

v2 的同类指标从原始 VCD 中采样，使用 tools/profile_stalls.py，不修改冻结 RTL。
公共比较器对求和 latency=5、gap=3 的 v2/v3 同时保存 stall-profile.json，
并检查 v3 的 VCD 统计和宿主统计一致。未采集的旧版指标在 CSV 中留空。

## 验证与实验

```sh
# 仓库根目录默认选 v3
make lint test
make test-icache
make test-mapped
make diagrams
make diff PROGRAM=full_demo LATENCY=5 GAP=3
make compare
# 只比较流水线两版
make compare BENCHMARK_ARGS="--versions v2_single_issue v3_icache"
```

- 保留基础指令、M/A/C、CSR、异常、中断、Sv39 与流水线回归。
- 单元测试使用真实缓存 RTL，检查冲突替换、大小与偏移、旁路、首/末补齐错误、失效、背压与高地址不别名。
- 集成测试覆盖跨行普通指令、热代码修改后 FENCE.I、热缓存仍拒绝 U 权限访问、物理别名与不同物理页。
- ICACHE_ENABLE=0 的独立仿真器保留同样的 v3 取指优化，用于分离缓存和取指合并的收益。
- 公共比较器保存 27 组缓存开关对照到本版 results/<run-id>/icache-ablation.csv；只比较周期数，不套用启用缓存的时序估计到关闭配置。

[冷缺失采样图](docs/waveforms/icache-cold.svg)、[热命中采样图](docs/waveforms/icache-warm.svg)
和 [流水线采样图](docs/waveforms/pipeline.svg) 都由实际 VCD 导出。
原始 VCD 位于 build/icache.vcd，命令 `surfer versions/v3_icache/build/icache.vcd` 可从仓库根目录打开。

性能改善、低延迟下的退步与面积代价见 [实验分析](../../results/README.md)。
本版仍没有 D-cache、TLB、非阻塞缺失处理、分支预测器、乱序或多核，也未进行正式 ISA 合规认证。
