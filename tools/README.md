# 仓库工具

| 工具 | 入口 | 输出 |
|---|---|---|
| check_repo.py | `make check` | 检查目录、文档链接、v1 冻结源码和历史对比表的一致性 |
| benchmark.py | `make compare` | 创建新的跨版本实验记录，拒绝覆盖已有 run-id |
| profile_stalls.py | `python3 tools/profile_stalls.py wave.vcd` | 从上升沿前 VCD 采样统计等待，无需修改冻结 RTL |

版本自己的仿真、参考模型、指令测试与时序脚本保留在 `versions/<version>/scripts/`。
公共比较器使用 v1 冻结的独立参考模型核对各版提交；硬件版本并不共享可变 RTL。
`--help` 可查看比较器参数，例如 `python3 tools/benchmark.py --help`。
默认比较v1–v11；`--versions v3_icache v4_fetch_buffer`可选择子集。
v3/v4 额外保存同取指前端下的 ICACHE_ENABLE=0 对照，以分离缓存的贡献。
v4 另保存 FETCH_BUFFER_ENABLE=0 对照；当同轮包含 v3 时，检查禁用缓冲的周期数/请求数与 v3 一致。

v5 另保存 EARLY_RESTART=0 对照；同轮包含 v4 时，检查禁用提前重启后的周期数和请求数与 v4 一致。

v6 保存 DCACHE_ENABLE=0 的30组对照；同轮包含v5时，检查关闭D-cache的周期数/请求数与v5一致。
新比较记录还保存data_wait、读写请求和D-cache事件数；旧实验CSV保持原样。

v7保存DCACHE_EARLY_RESTART=0的30组对照，同轮包含v6时检查周期数/请求数一致，并同时记录数据等待与前端等待。

v8保存SPLIT_MEMORY=0的30组对照，与同轮v7核对周期数/请求数；新增I命中与D补数重叠、D命中与I补数重叠计数。
profile_stalls.py优先采样顶层等待信号；旧版无该信号时保留原仲裁器推导方式。
v8的data_blocked_by_fetch/fetch_blocked_by_data统计物理仲裁等待，旧版统计虚拟请求仲裁等待，范围不同。

v9保存PREDICT_ENABLE=0的30组对照，与同轮v8核对周期数/请求数；新增控制流解析、条件/直接/间接跳转及各自失误计数。
旧版没有该观测接口时CSV留空，不把缺少指标误报成零。其他开关对照仍保留当前版的预测设置。

v10保存RAS_ENABLE=0的33组对照，与同轮v9核对周期数/请求数。新增calls.S调用基准；旧实验程序集合和CSV不变。
新增RAS预测、失误、提交push/pop、溢出/下溢计数，旧版没有观测接口时留空。

v11保存TLB_ENABLE=0的36组对照，与同轮v10核对周期数/请求数；新增paged_loop.S分页基准。
新增I/D TLB命中/缺失/填入、I/D页表读取和失效事件；旧版缺少指标时留空。

只测周期、不运行综合/STA：

```sh
python3 tools/benchmark.py --versions v11_tlb v12_dynamic_predict --cycles-only
```

v12额外关闭BHT，并检查周期、外部请求和控制失误与v11完全一致。
