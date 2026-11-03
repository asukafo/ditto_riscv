# 分版本演进与性能对比

| 目录 | 架构 | 用途 |
|---|---|---|
| [v1_multicycle](v1_multicycle/README.md) | 多周期顺序核 | 冻结提交 8adc22c 的基线 |
| [v2_single_issue](v2_single_issue/README.md) | F / X / W 单发射顺序流水线 | 冻结的流水线基线 |
| [v3_icache](v3_icache/README.md) | 流水线、256 字节物理指令缓存 | 冻结的指令缓存基线 |
| [v4_fetch_buffer](v4_fetch_buffer/README.md) | 指令缓存与半字取指缓冲 | 冻结的半字缓冲基线 |
| [v5_early_restart](v5_early_restart/README.md) | 关键字优先补齐与提前重启 | 冻结的提前重启基线 |
| [v6_dcache](v6_dcache/README.md) | 256B物理数据缓存，写穿透 | 冻结的数据缓存基线 |
| [v7_dcache_early](v7_dcache_early/README.md) | D-cache关键数据优先与提前重启 | 冻结的数据提前重启基线 |
| [v8_split_memory](v8_split_memory/README.md) | 独立I/D MMU与缓存路径，共享物理仲裁 | 冻结的分离访存路径基线 |
| [v9_static_predict](v9_static_predict/README.md) | BTFNT静态分支预测，JAL目标预测 | 冻结的静态预测基线 |
| [v10_return_stack](v10_return_stack/README.md) | 8项返回地址栈，提交时更新 | 冻结的提交RAS基线 |
| [v11_tlb](v11_tlb/README.md) | I/D各8项全相联4KiB TLB | 冻结的翻译缓存基线 |
| [v12_dynamic_predict](v12_dynamic_predict/README.md) | 32项两位BHT，提交时训练 | 冻结的bimodal预测基线 |
| [v13_gshare](v13_gshare/README.md) | 4位GHR与32项PHT，提交历史和保存索引 | 冻结的全局历史预测基线 |
| [v14_btb](v14_btb/README.md) | 请求时查询32项带标签目标缓存 | 冻结的BTB基线 |
| [v15_fetch_queue](v15_fetch_queue/README.md) | 四项完整包FIFO、空队列旁路 | 冻结的取指队列基线 |
| [v16_ifetch_pipeline](v16_ifetch_pipeline/README.md) | 命中通路响应/请求交接 | 冻结的单笔流水交接 |
| [v17_fetch_window](v17_fetch_window/README.md) | 四槽请求窗口、完成令牌与失效标记 | 冻结；整核实测2笔I侧在途 |
| [v18_btb_window](v18_btb_window/README.md) | BTB/gshare/RAS引导预取、保存与复核槽内预测 | 冻结的预测路径窗口 |
| [v19_window_forward](v19_window_forward/README.md) | 当前需求的返回旁路、反压存储与同拍交接 | 冻结的响应旁路窗口 |
| [v20_demand_issue](v20_demand_issue/README.md) | 新需求当拍发送与令牌登记，背压缓冲重试 | 冻结的新需求发送窗口 |
| [v21_demand_priority](v21_demand_priority/README.md) | 匹配未发送槽的需求当拍优先，保留实际发送所有权 | 冻结的需求优先窗口 |
| [v22_hit_under_refill](v22_hit_under_refill/README.md) | 背景补行期间命中服务与有序响应，单个缺失保留 | 冻结的补行下命中 |
| [v23_fill_forward](v23_fill_forward/README.md) | 已返回8B补行缓冲复用 | 冻结，热区1.00 IPC单发射基线 |
| [v24_dual_alu](v24_dual_alu/README.md) | 简单ALU双发射、有序双提交，前端单包 | 当前开发与实验 |

每版有独立的 rtl、sim、sw、scripts、Makefile、build 和 results。

仓库根目录的 Makefile 默认转发至 v24；用 VERSION=<目录名> 选择其他版本。后续新架构使用新目录，旧架构不随之修改。
公共比较脚本只负责运行实验，不在不同版本之间共用会变化的 RTL。

```sh
# 仓库根目录，分别构建两版、同约束综合和逐条参考校验
python3 tools/benchmark.py
# 指定名称，已存在时明确失败，不覆盖结果
python3 tools/benchmark.py --run-id my-experiment
```

当前`make compare`比较v16/v23/v24的20个程序，在(latency,gap)=(1,0)、(5,0)、(5,3)下各跑一次，每版60次。v1–v15历史全功能比较仍用`tools/benchmark.py`。
包括求和、依赖链、指针追踪、访存、位操作、C、M/A/C C、直线 ALU 、压缩指令依赖链和重复数据读取。
脚本检查各版二进制 SHA-256 一致、退休指令数一致，且逐条提交和最终内存通过独立参考模型。
v3/v4 另有关闭缓存的对照；v4 另有 27 组关闭取指缓冲的对照，分别隔离不同改动的收益。

每版的 `results/<run-id>/` 保存性能 CSV、RTL/程序哈希、工具版本、时序报告及构建摘要。
合并表保存在 `results/comparisons/<run-id>/comparison.csv`。
最小周期 × 总周期得到的 estimated_time_ns 是模型推算，实际芯片仍需布局布线和硬件验证。

## 第一版流水线的实际结果

当前最终记录是 [20261031T055411878848Z](../results/comparisons/20261031T055411878848Z/comparison.csv)。
以下为延迟 1、无背压时的总周期数；两版退休指令数相同：

| 程序 | v1 多周期 | v2 单发射 | 周期数比值 v1/v2 |
|---|---:|---:|---:|
| 求和 | 1767 | 1569 | 1.126 |
| 寄存器依赖链 | 1314 | 1181 | 1.113 |
| 指针追踪 | 1895 | 1697 | 1.117 |
| 裸机 C | 779 | 685 | 1.137 |
| 独立 ALU | 1339 | 1075 | 1.246 |
| 压缩指令依赖链 | 407 | 277 | 1.469 |

同库布局前最小周期估计为 v1 4.32 ns、v2 4.33 ns；单元面积为 65643.746 与 80896.718，
增加约 23.24%。收益主要来自重叠执行，不是时钟频率提高。

高延迟/背压下并非全部改善：例如 latency=5、gap=3 时，求和从 5758 增加到 6271 周期，
依赖链从 4206 增加到 4719 周期。单个阻塞总线上的错误路径取指与取指/数据争用增加了等待。
这些结果说明第一版流水线已经能重叠执行，但进一步提速需要改善供指、分支处理及存储访问，
不能只凭“用了流水线”宣称所有程序更快。

中间实验 [20261031T054659297887Z](../results/comparisons/20261031T054659297887Z/comparison.csv)
和 [20261031T055205935167Z](../results/comparisons/20261031T055205935167Z/comparison.csv) 也保留。
第一轮统计只覆盖部分阶段重叠；第二轮完整统计的组合条件将关键路径拉长到 4.87 ns。
最终版本直接读取各级寄存的有效/在途状态，恢复至约 4.33 ns。
各轮 manifest 中记录的 RTL 哈希可以区分这些测量，不能把不同轮的面积/周期估计混用。

v5 增加 EARLY_RESTART=0 对照；同轮包含 v4 时检查关闭优化后的周期数与请求数完全一致。

v6 增加 DCACHE_ENABLE=0 对照；同轮包含 v5 时检查关闭 D-cache 后周期数与请求数完全一致。各版优化动机和代价汇总见 [根 README](../README.md)。

v7增加DCACHE_EARLY_RESTART=0对照，同轮包含v6时检查关闭优化后的周期数/外部请求数完全一致。

v8增加SPLIT_MEMORY=0对照，同轮包含v7时检查恢复串行连接后的周期数/外部请求数一致。

v9增加PREDICT_ENABLE=0对照，恢复v8的顺序取指与跳转冲刷；同轮30组周期数/请求数逐项核对。

v10增加RAS_ENABLE=0对照，33组周期数/请求数与同轮v9逐项核对；新增公共calls.S基准。

v11增加TLB_ENABLE=0对照，36组周期数/请求数与同轮v10核对；新增公共分页基准，旧实验表保持不变。

使用`--cycles-only`跳过映射和STA，时序/面积字段留空，不能据此宣称芯片频率或真实时间改善。
