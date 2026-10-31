# ditto_riscv

通过可运行的 RTL、逐条参考对照、真实波形与性能实验学习 RISC-V core 设计。
当前开发版本是 **v2 单发射顺序流水线**；v1 多周期核作为冻结基线独立保留。
两版均支持 RV64IMAC、Zicsr/Zifencei、M/S/U、软件异常、中断与 Sv39/Svade。
后续目标是缓存、双发射、乱序与双核，目前尚未实现这些功能。

## 快速开始

工具使用本机已配置的 Verilator、Surfer、Yosys、OpenSTA、riscv64-elf 工具链和 Python 3。
在仓库根目录执行：

```sh
make help
make check
make tools
make lint
make test
make diff PROGRAM=full_demo
make diagrams
make timing
```

根目录命令默认转发到 `versions/v2_single_issue/`，输出位于该版的 `build/`。
`make diagrams` 导出真实流水线 VCD 的阶段采样图；`make wave PROGRAM=full_demo` 用 Surfer 打开波形。
选择旧版使用 `make test VERSION=v1_multicycle`，或进入该版本目录运行其 Makefile。
`PROGRAM`、`LATENCY`、`GAP`、`CROSS`、`LIB`、`CLOCK_NS` 等命令行参数会传给所选版本。
`make clean` 只清理当前所选版本的构建产物。

## 目录与版本

| 路径 | 内容 |
|---|---|
| [versions/v1_multicycle](versions/v1_multicycle/README.md) | 冻结的多周期核，源码对应提交 8adc22c |
| [versions/v2_single_issue](versions/v2_single_issue/README.md) | 当前 F / X / W 单发射流水线及其测试 |
| [benchmarks](benchmarks/README.md) | 两版执行相同二进制的公共基准程序 |
| [tools](tools/README.md) | 仓库检查与跨版本性能比较工具 |
| [results](results/README.md) | 跨版本对比记录，各版详细记录保留在各自 results/ |
| [docs](docs/README.md) | 文档导航、目录约定和历史教学实验 |

每版自带 RTL、仿真宿主、软件、测试脚本和构建配置，避免修改新版时改变旧版行为。
架构演进创建新版本目录；代码直接提交到主分支 `main`。
具体规则见 [开发约定](CONTRIBUTING.md)。

## 性能实验

```sh
make compare
# 每次使用新的 run-id；已存在时明确拒绝覆盖
make compare BENCHMARK_ARGS="--run-id my-experiment"
```

脚本检查两版程序二进制一致，逐条核对提交与最终内存，保存周期数、CPI、时序、面积和源码哈希。
合并表位于 `results/comparisons/<run-id>/`，单版记录位于 `versions/<version>/results/<run-id>/`。
[已有实验](results/README.md)包含改善和退步项；流水线不保证所有内存条件下都更快。
时序与面积使用研究用标准单元库进行布局前估计，不是硬件实测值。

## 功能与学习入口

程序通过已提交的退出邮箱存储结束；EBREAK、ECALL 由软件异常处理程序接收。
MMU 没有 TLB，采用 Svade 软件管理 A/D 位。尚无 F/D/V/H、PMP、缓存或多核，未进行正式 ISA 合规认证或 Linux 启动验证。

- [单发射流水线、前递与精确异常](versions/v2_single_issue/README.md)
- [多周期核、握手、提交与波形教程](docs/README.md)
- [版本演进和实际性能分析](versions/README.md)
- [仓库结构及常用命令](docs/repository.md)
