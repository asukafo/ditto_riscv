# 仓库工具

| 工具 | 入口 | 输出 |
|---|---|---|
| check_repo.py | `make check` | 检查目录、文档链接、v1 冻结源码和历史对比表的一致性 |
| benchmark.py | `make compare` | 创建新的跨版本实验记录，拒绝覆盖已有 run-id |
| profile_stalls.py | `python3 tools/profile_stalls.py wave.vcd` | 从上升沿前 VCD 采样统计等待，无需修改冻结 RTL |

版本自己的仿真、参考模型、指令测试与时序脚本保留在 `versions/<version>/scripts/`。
公共比较器使用 v1 冻结的独立参考模型核对各版提交；硬件版本并不共享可变 RTL。
`--help` 可查看比较器参数，例如 `python3 tools/benchmark.py --help`。
默认比较 v1/v2/v3；`--versions v2_single_issue v3_icache` 可选择子集。
v3 额外保存同取指前端下的 ICACHE_ENABLE=0 对照，以分离缓存的贡献。
