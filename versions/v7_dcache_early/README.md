# v7：数据缓存关键字优先与提前重启

本版针对v6“每次数据缺失必须等完整16B缓存行”的等待，让load先拿到所需数据并继续执行。
继承v6的F/X/W单发射流水线、256B I-cache与256B写穿透D-cache、MMU/特权/原子功能。
本版现已冻结，当前默认开发入口为v8。整体演进动机见[根README](../../README.md)，缓存基本策略见[v6设计](../v6_dcache/README.md)。

## 从完整补行到提前响应

v6按低8B、高8B的顺序读取，最后才响应。v7根据原物理地址bit3选择先读哪一个8B；
当请求的1/2/4/8B全部落在该半行时，第一笔成功后就登记响应，同时读取另一半。
若请求跨8B边界，保留原先的完整补行响应路径；跨16B行仍旁路。
正常对齐的RV64整数load都落在一个8B半行内。

```text
v6: read low 8B -> read high 8B -> load response -> dependent instruction
v7: read critical 8B -> load response -> dependent instruction
                    -> read remainder 8B -> complete valid cache line
```

`rtl/rv64_dcache.sv`增加early、response_available，并分开管理补数状态与上游响应握手：

- early记录本次能否提前返回；beat表示第一/第二笔；fill_high决定读取物理行的高/低半部。
- fill_low沿用原寄存器名字，现在保存“第一次回来的8B”，最后根据原偏移正确组装整行。
- response_available保存响应是否尚未接收，数据和错误位在ready=0时保持稳定。
- 第二笔补数和上游响应可以按任意先后完成；两者都完成后才回到IDLE。
- 仅完整成功且未被失效毒化的行才置valid，不把半行当成整行命中。

它仍是阻塞式缓存。load可以提前完成，但剩余补数期间不接收下一笔请求，后续store/atomic也要等待。
主通路仍是arbiter → MMU → D-cache → I-cache → atomic adapter → external RAM。
D-cache阻塞时，后续取指即使可能命中I-cache，也可能暂时无法通过这条共享路径。
本版没有hit-under-miss、多笔在途请求或独立I/D物理通路。

## 错误、失效与写入顺序

第一笔关键数据失败：返回load访问错误，缓存行无效。
关键数据成功、第二笔无关字节失败：保持已返回的load成功，行无效；后续访问重新读取并检查错误。
若响应还在等待ready，第二笔错误也不能把这份成功响应改成错误。
跨8B的完整补行路径中，任一笔失败仍导致本次请求失败。
这只用于平台普通RAM；MMIO、页表、指令、原子和退出邮箱继续使用v6旁路规则。

后续普通store不能越过未完成的补数。背景补齐结束后，store照常写穿透，成功响应后更新行。
后续LR/SC/AMO仍先使对应数据行失效，再经原子适配器执行，避免缓存留有旧副本。
外部reservation_invalidate继续清空有效位并毒化在途补数/写更新。
MMU仍在D-cache之前检查每笔请求的权限；FENCE/FENCE.I的既有串行化和I-cache失效规则保留。

`DCACHE_EARLY_RESTART=0`恢复v6的数据补齐和响应行为；不改变I-cache的提前重启。
本轮30组关闭优化后的周期数和外部请求数，逐项与同轮v6一致。

## 实测结果：响应更早，整机收益受供指限制

[本轮90组主对照](../../results/comparisons/20261101T102336052192Z/comparison.csv)
包含v5/v6/v7，程序二进制一致，提交与最终RAM由独立模型校验。
[30组数据提前重启开关对照](results/20261101T102336052192Z/dcache-early-ablation.csv)
同时保存data_wait和frontend_starved。另保留I-cache、半字缓冲、取指提前重启、D-cache开关实验。

| 程序 | 延迟1/间隔0：v6→v7周期 | 延迟5/间隔3：v6→v7周期 |
|---|---:|---:|
| 顺序求和 | 1054→1022 | 1499→1499 |
| 指针追踪 | 1310→1246 | 2135→2135 |
| 裸机C | 527→517 | 1059→1055 |
| M/A/C C | 508→499 | 887→883 |
| 重复读取同一数据 | 1567→1566 | 1627→1627 |

这些测试的外部请求数全部不变。重复读大部分已命中，提前重启只优化第一次缺失，所以收益很小。
延迟5/间隔3的求和中，data_wait从537降到312，但frontend_starved从224增到449，总周期仍1499。
原因是执行提前腾空后，没有足够后续指令可执行；背景补数继续阻塞共享的取指路径。
两个计数描述不同等待条件，通常不能相加当成总周期；本例相同差值是该程序本轮实际观测。
数据等待提前结束不等于所有下游资源都已释放，也不保证整个程序同比例提速。

对照更早的v5，延迟5/间隔3求和仍是1371→1499，尚未消除v6引入的顺序读取退步。
下一步应实验分离I/D命中路径或允许更有选择的请求并行，并继续检查原子、失效和异常顺序。

相同Nangate45 typical约束下，布局前最小周期4.54→4.66ns，单元面积125400.646→126613.872，
面积增加约0.97%，周期增加约2.64%。总时间估计仍应使用cycles×period。
例如低延迟求和从4785.16ns到4762.52ns，改善约0.47%；高延迟有背压时总周期不变，估计时间反而增长。
这些是布局前模型值，不是硬件实测。关闭开关的配置未独立测量时序，不套用默认时钟周期推算其时间。

## 真波形与验证

[真实冷缺失采样图](docs/waveforms/dcache-cold.svg)来自build/dcache.vcd，latency=5、gap=3。
控制采沿前，commit采沿后：

| 周期 | 事件 |
|---|---|
| C45 | 外部接受关键8B，地址0x3000 |
| C50 | 关键8B返回 |
| C51 | D-cache向MMU返回load数据，依赖指令同时进入X |
| C52 | PC=0x0c的load提交，背景补数尚未完成 |
| C53 | 外部接受另一半，地址0x3008 |
| C58 | 另一半返回，缓存行随后变为有效 |

p_rsp_valid是D-cache向MMU的响应，rsp_valid是外部共享内存的响应。
req_addr在req_valid=0时没有事务含义。miss_wait包含提前响应后的背景补数，并不等于load本身等待周期。

新增111项单元检查覆盖低/高半行优先、重排序、请求跨8B回退、首笔/尾笔错误、
成功响应被阻塞时的尾笔错误、在途失效、后续store/atomic不能越过补数以及字节数据正确性。
原558项D-cache单元测试用关闭提前重启的配置运行，保留完整补行行为的检查。
新增25组整核测试覆盖顺序读、高半行优先、load后store/AMO、load后代码更新与FENCE.I，
另有12组开关对照。原有完整ISA、特权、Sv39、原子和缓存回归保留。
286组整核测试在RTL和标准单元门级各执行一次，572份提交/最终内存文件逐字节一致。
门级逻辑仿真无SDF延迟，不能替代时序签核。

```sh
# From repository root, explicitly select frozen v7
make lint test VERSION=v7_dcache_early
make test-data-early VERSION=v7_dcache_early
make test-mapped VERSION=v7_dcache_early
make diagrams VERSION=v7_dcache_early
make compare BENCHMARK_ARGS="--versions v5_early_restart v6_dcache v7_dcache_early"
# 旧版保持独立
make test VERSION=v6_dcache
```
