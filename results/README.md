# 性能实验记录

合并对比表位于 `comparisons/<run-id>/comparison.csv`，每个版本的完整记录仍保留在
`versions/<version>/results/<run-id>/`。run-id 使用 UTC 时间或显式名称，同名实验不允许覆盖。

| 记录 | 内容 |
|---|---|
| [20261031T054659297887Z](comparisons/20261031T054659297887Z/comparison.csv) | 首轮流水线比较，部分阶段重叠统计 |
| [20261031T055205935167Z](comparisons/20261031T055205935167Z/comparison.csv) | 统计逻辑引入关键路径，v2 约 4.87 ns |
| [20261031T055411878848Z](comparisons/20261031T055411878848Z/comparison.csv) | 修正统计后的对照，v1 4.32 ns、v2 4.33 ns |
| [20261031T064104311469Z](comparisons/20261031T064104311469Z/comparison.csv) | 整理仓库后重跑 54 组，数据与前一轮完全一致 |

上述文件迁移前后内容保持一致。历史 README 中的 `python3 versions/benchmark.py` 是当时实际运行的旧入口，
当前入口为仓库根目录的 `make compare` 或 `python3 tools/benchmark.py`。

每版 CSV 记录周期数、CPI、时序估计、面积和请求数；manifest 保存 RTL/二进制哈希与工具版本。
布局前时序和面积不等于实际芯片指标。性能改善与退步项见 [版本对比分析](../versions/README.md)。
`make check` 会核对合并表和单版记录是否一致，不会重写结果。
