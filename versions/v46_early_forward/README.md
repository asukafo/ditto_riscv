# v46 以前端接收前的 X 占用状态选择前递

v45 使用 `ex_finish` 同时限定 X 槽的前递数据和新指令的接收。v46 提前按 `state != EMPTY` 形成 X 槽前递候选。有效接收只发生于 X 空闲或 X 完成的周期，因此在被接收的指令上，两种选择相同。空闲采样的中间值由原有有效位管理，忙且未完成时操作数保持。

分层含端口时钟下限为 9.7466 ns，展平寄存器间下限为 7.4886 ns。分层满足 10 ns，但展平性能退步，保留为独立对照版本，默认仍为 v41。[时序记录](results/v46-early-forward/timing-summary.json) · [I/O 路径](results/v46-early-forward/io-paths.txt)

完整 Verilator 回归和 60 组公共门级对照通过。波形核对接收时的主槽和第二槽操作数，并检查 `ex_finish` 对应非空 X 槽。组合等价检查仅覆盖合法接收条件下的前递选择。[公共比较](../../results/comparisons/v46-early-forward/comparison.csv) · [门级对照](results/v46-early-forward/gate-equivalence.csv) · [条件等价记录](results/v46-early-forward/forward-equivalence.json)
