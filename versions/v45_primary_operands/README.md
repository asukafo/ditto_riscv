# v45 第一发射槽操作数提前锁存

v44 的展平最慢路径终点迁移到第一槽的 `b[18]`。v45 把第一槽的 `a`、`b` 操作数锁存从 `issue_fire` 接收条件中拆开，在 X 槽空闲或本拍 X 完成时采样。执行、访存和除法等待期间保持原操作数。只有实际接收的候选指令会成为下一条 X 指令。

设置 `PRIMARY_OPERAND_CAPTURE=0` 恢复 v44 的锁存使能。新增波形断言核对每次主槽接收的前递值，以及主槽忙且未完成时的两个操作数保持。

展平寄存器间时钟下限为 7.2125 ns，v44 为 7.2037 ns。分层含端口下限为 10.0660 ns，10 ns 下仍有 −0.0660 ns setup 违例。这版保留为提前锁存第一槽操作数的对照实验，根目录默认仍为 v41。[时序与哈希](results/v45-primary-operands/timing-summary.json) · [展平报告](results/v45-primary-operands/flat-timing.txt) · [分层 I/O 路径](results/v45-primary-operands/io-paths.txt)

完整 Verilator 回归及 60 组公共门级对照通过，启用和关闭提前锁存的退休记录与 RAM 均与 v44 一致。[公共比较](../../results/comparisons/v45-primary-operands/comparison.csv) · [门级对照](results/v45-primary-operands/gate-equivalence.csv)
