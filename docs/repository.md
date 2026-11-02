# 仓库结构与命令入口

```text
ditto_riscv/
├── Makefile                  统一入口，默认选择 v15
├── README.md                 快速开始
├── CONTRIBUTING.md           开发、冻结和记录约定
├── versions/
│   ├── v1_multicycle/        冻结基线
│   ├── v2_single_issue/      冻结的流水线基线
│   ├── v3_icache/            冻结的流水线与指令缓存
│   ├── v4_fetch_buffer/      冻结的半字取指缓冲
│   ├── v5_early_restart/     冻结的关键字优先补齐
│   ├── v6_dcache/            冻结的写穿透数据缓存
│   ├── v7_dcache_early/      冻结的数据缓存提前重启
│   ├── v8_split_memory/      冻结的独立I/D翻译和缓存命中路径
│   ├── v9_static_predict/    冻结的静态分支与直接跳转预测
│   ├── v10_return_stack/    冻结的提交时返回地址栈
│   ├── v11_tlb/            冻结的独立I/D翻译缓存
│   ├── v12_dynamic_predict/ 冻结的32项两位分支预测
│   ├── v13_gshare/          冻结的提交历史gshare
│   ├── v14_btb/             冻结的请求时目标预测
│   └── v15_fetch_queue/     四项完整指令队列与前端解耦
├── benchmarks/              公共比较程序
├── tools/                   仓库检查、跨版本比较
├── results/comparisons/     不覆盖的历史对比表
└── docs/
    ├── README.md            文档导航
    └── baseline/            v1 和早期教学资料
```

每个硬件版本独立拥有：

| 路径 | 内容 |
|---|---|
| rtl/ | SystemVerilog 模块 |
| sim/ | C++ 仿真宿主和事务内存模型 |
| sw/ | 汇编、C、链接脚本与仿真退出协议 |
| scripts/ | 参考模型、指令/特权回归、综合约束与波形导出 |
| Makefile | 本版本构建和测试入口 |
| build/ | 可再生成的本地输出，不提交 Git |
| results/ | 永久实验数据、哈希、工具版本和验证记录 |

## 根目录命令

```sh
make lint                         # 默认 v15
make test
make diff PROGRAM=full_demo LATENCY=5 GAP=3
make timing
make test VERSION=v1_multicycle
make diff VERSION=v1_multicycle PROGRAM=sum
make check
make compare BENCHMARK_ARGS="--run-id my-experiment"
```

递归 make 在所选版本目录执行，因此仿真输出为 `versions/<version>/build/`。
`make clean VERSION=v2_single_issue` 只清理 v2 的 build，不触碰其他版本或任何 results。
直接进入版本目录运行命令仍受支持，v1 的原 Makefile 保持冻结。
`test-pipeline` 从 v2 开始提供，`test-icache` 从 v3 开始提供，`test-early` 从 v5 开始提供；`test-fetch` 为 v4 的半字缓冲专项测试。

## 源码与记录保护

根目录不再复制一套硬件源码。各版内部的重复模块是版本快照的一部分，
不会抽成可变的公共 RTL，以免修改新版时改变旧版。
v1–v14的frozen-files.json记录各版冻结源码/构建文件哈希；`make check`会校验。
各版的历史 results 和公共对比表迁移时保持内容不变，历史 manifest 中的原始信息仍有效。

旧根目录的本地 build 已移入忽略目录 `.local/legacy-root-build-<timestamp>/`，未删除。
它只用于保留此前的本机产物，不参与当前构建，也不提交 Git。

`test-dcache` 从 v6 开始提供，包含数据缓存单元测试与整核访存/权限/原子对照。

`test-data-early`从v7开始提供，检查数据缓存提前响应与后续store/atomic的顺序。

`test-split`从v8开始提供，检查物理仲裁、并发MMU/缓存路径以及整核串行化。

`test-predict`从v9开始提供，覆盖静态方向/目标计算、压缩指令预测、失误恢复与错误路径故障。

`test-ras`从v10开始提供，检查提交提示、容量边界、取指元数据、嵌套和错误返回恢复。

`test-tlb`从v11开始提供，检查翻译存储、MMU命中权限、失效、分页容量及整核对照。

`test-bht`从v12开始提供。仅比较周期、暂不分析时序：

```sh
python3 tools/benchmark.py --versions v14_btb v15_fetch_queue --cycles-only
```

`test-gshare`从v13开始提供，包含保存索引的单元测试及整核VCD审计。

`test-btb`从v14开始提供，包含标签/目标模型、指令元数据验证及整核提前查询审计。

`test-queue`从v15开始提供，检查333位包的FIFO、整核冲刷、精确异常及单笔在途取指约束。
