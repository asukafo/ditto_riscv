# 文档导航

## 当前工程

- [仓库结构、入口与产物位置](repository.md)
- [版本清单与实际性能分析](../versions/README.md)
- [v2 单发射流水线：阶段、前递、异常和仲裁](../versions/v2_single_issue/README.md)
- [v2 真实 VCD 阶段采样图](../versions/v2_single_issue/docs/waveforms/pipeline.svg)
- [v1 冻结的多周期基线](../versions/v1_multicycle/README.md)
- [永久性能实验记录](../results/README.md)

## v1 与早期教学实验

以下资料对应多周期核及其早期配置，命令以 `versions/v1_multicycle/` 为工作目录，
其中的周期数和状态机不能套到 v2 流水线上。

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
