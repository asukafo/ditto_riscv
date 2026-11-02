# 文档导航

## 当前工程

- [v17 多笔I侧在途、完成令牌、失效槽位与真实波形](../versions/v17_fetch_window/README.md)
- [v16 命中通路交接、背压与提前排空](../versions/v16_ifetch_pipeline/README.md)

- [v15 取指队列、完整指令包与冲刷波形](../versions/v15_fetch_queue/README.md)

- [v14 BTB、提前目标查询与间接调用](../versions/v14_btb/README.md)

- [v13 gshare全局历史预测、保存索引与学习波形](../versions/v13_gshare/README.md)

- [v12 动态条件分支预测、提交训练与表项冲突](../versions/v12_dynamic_predict/README.md)

- [v11 I/D TLB、分页性能、权限与IMEM/DMEM区别](../versions/v11_tlb/README.md)
- [v10 提交时返回地址栈、错误预测恢复与时序代价](../versions/v10_return_stack/README.md)
- [v9 静态分支预测、错误路径恢复与循环退出波形](../versions/v9_static_predict/README.md)
- [v8 独立翻译/缓存路径、响应归属与并发波形](../versions/v8_split_memory/README.md)
- [v7 数据提前重启与共享通路瓶颈](../versions/v7_dcache_early/README.md)

- [v6 写穿透数据缓存、旁路规则与性能取舍](../versions/v6_dcache/README.md)

- [v5 关键字优先补齐、提前重启与真实波形](../versions/v5_early_restart/README.md)

- [仓库结构、入口与产物位置](repository.md)
- [版本清单与实际性能分析](../versions/README.md)
- [v2 单发射流水线：阶段、前递、异常和仲裁](../versions/v2_single_issue/README.md)
- [v3 物理指令缓存、FENCE.I 和性能诊断](../versions/v3_icache/README.md)
- [v4 半字取指缓冲、拼接、冲刷与开关对照](../versions/v4_fetch_buffer/README.md)
- [v2 真实 VCD 阶段采样图](../versions/v2_single_issue/docs/waveforms/pipeline.svg)
- [v1 冻结的多周期基线](../versions/v1_multicycle/README.md)
- [永久性能实验记录](../results/README.md)

## v1 与早期教学实验

以下资料对应多周期核及其早期配置，命令以 `versions/v1_multicycle/` 为工作目录，
其中的周期数和状态机不能套到后续流水线上。

- [多周期数据通路与架构目标](baseline/architecture.md)
- [握手、Load 执行与真实波形逐周期讲解](baseline/design-walkthrough.md)
- [commit 信号与逐条参考对照](baseline/commit-trace.md)
- [整数 ALU、移位和比较](baseline/integer-alu.md)
- [RV64I 指令、W 运算、访存与 C 程序](baseline/rv64i.md)
- [模块拆分、CSR、中断、原子与 Sv39](baseline/modular-core.md)
- [早期实验与周期公式](baseline/experiments.md)
- [静态时序数字如何计算](baseline/timing-explained.md)
- [缓冲、驱动尺寸与时序优化实验](baseline/timing-optimization.md)
- [工具、约束和 v1 文件说明](baseline/tools.md)
