# 仓库工具

| 工具 | 入口 | 输出 |
|---|---|---|
| check_repo.py | `make check` | 检查目录、文档链接、v1 冻结源码和历史对比表的一致性 |
| benchmark.py | `make compare` | 创建新的跨版本实验记录，拒绝覆盖已有 run-id |

版本自己的仿真、参考模型、指令测试与时序脚本保留在 `versions/<version>/scripts/`。
公共比较器使用 v1 冻结的独立参考模型核对两版提交；硬件版本并不共享可变 RTL。
`--help` 可查看比较器参数，例如 `python3 tools/benchmark.py --help`。
