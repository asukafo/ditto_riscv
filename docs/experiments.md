# M0 实验说明

配套阅读：[架构设计与真实波形逐周期讲解](design-walkthrough.md)。

## 可重复运行

```bash
make test
make sweep
make sim PROGRAM=pointer_chase LATENCY=20 GAP=3
make wave PROGRAM=pointer_chase LATENCY=20 GAP=3
```

LATENCY=N 表示请求在某上升沿接收后，在第 N 个后续上升沿返回响应，N 至少为 1。
取指、读数据、写数据均使用同一延迟。GAP=K 表示只在 tick 为 K+1 的倍数时允许接收请求；
GAP=0 时没有额外请求反压。该规则是确定性流控实验，不是 DRAM 带宽模型。
模型只有单个未完成请求，没有 bank、刷新、行命中、带宽调度或缓存。

五个程序均由真实 RISC-V 工具链汇编，不使用手写机器码作为性能负载。
pointer_chase 的 64 个节点通过固定种子 20261030 打乱，形成从节点 0 出发的单环，正好遍历一遍。
这是不连续地址的依赖访存，不表示硬件随机源或覆盖完整 DRAM 的随机访问。

## 已验证的结果

Verilator 5.052，当前 M0，GAP=0，cycles 从复位释放后的第一个有效时钟计至 EBREAK 完成为止：

| 程序 | instret | 延迟 1 的周期 | 延迟 5 的周期 | 延迟 20 的周期 | 结果 |
|---|---:|---:|---:|---:|---:|
| sum | 325 | 1105 | 2665 | 8515 | 2080 |
| dependency | 260 | 782 | 1826 | 5741 | 128 |
| pointer_chase | 325 | 1233 | 3049 | 9859 | 2016 |
| load_add_store | 30 | 110 | 270 | 870 | 14 |
| bit_ops | 20 | 76 | 188 | 608 | `0x7ffffffffffffffc` |

`instret` 包含教学结束标记 EBREAK。`fetch_wait` / `data_wait` 仅累计等待响应且响应未就绪的周期；
不包含请求反压或接收响应的周期。`requests` 包含取指和数据访问，`reads` 也包含取指。
IPC 可由 instret/cycles 计算；它不能跨不同程序直接用于判断谁的实现更好。

当前全部串行，所以 GAP=0 时严格满足：

```text
cycles(N) = cycles(1) + requests × (N - 1)
fetch_wait = instret × (N - 1)         # 正常结束的现有负载
data_wait = (requests-instret) × (N - 1)
```

这个关系是回归断言。未来流水线、缓存和多请求系统可以重叠访问，应改用对应的新性能模型。
dependency 也随 RAM 延迟显著变慢，因为当前每一条指令都需要从 RAM 取出。
这提供了加入 I-Cache 的直接动机；目前不能凭这些实验判断乱序执行或缓存的收益。

## 回归覆盖与限制

`make test` 检查 25 次负载/延迟/反压组合，以及 42 次定向运行。
每次运行都用独立 Python 模型核对全部提交、停止状态与完整 RAM，再运行 12 项检查器测试：

- 真实程序的结果签名、提交数、精确的延迟周期关系。
- ADDI 负立即数、ADD/SUB、x0 写入丢弃、LUI 符号扩展、LD/SD 回读。
- 有符号/无符号分支、跳转链接值、后向循环与不跳转。
- 非法编码、未实现指令、取指/数据越界、数据与跳转地址未对齐。
- 请求反压期间 valid、地址、写标记和写数据保持稳定。
- 每条提交的 PC、机器码、下一 PC、寄存器写回和数据访存。
- 完整 64 KiB 最终 RAM，避免只核对事件记录而漏掉实际内存更新错误。
- 故意损坏 trace 的字段、顺序、终止记录和 RAM，确认检查器拒绝错误并定位第一处分歧。

另外执行 876 组 ALU 向量 × 5 种时序配置，核对 26295 次提交，并用单独的数学结果计算检查内存输出。
测试包括 64 位边界、移位 0/1/31/32/63 位、寄存器移位量的低六位截取、立即数符号扩展与寄存器别名。
完整说明见 [整数 ALU 实验](integer-alu.md)。

这些是阶段性定向测试，不是完整 ISA 合规验证、随机验证或形式证明。
当前参考模型只覆盖教学指令子集，不依赖 RTL 或其运行时数据执行指令，
但仍由本项目维护；后续需引入 Spike 等成熟模型交叉验证并补齐指令覆盖。
M5 需要专门的多核内存顺序测试。

## 如何读波形

在 Surfer 中展开顶层，优先观察：

1. `clk/reset`：确认有效执行区间。
2. `pc/insn/state`：当前指令及六个状态，编码见 RTL localparam。
3. `req_valid/req_ready/req_addr/req_write`：请求接收与反压。
4. `rsp_valid/rsp_ready/rsp_rdata`：从请求到响应的距离。
5. `commit_valid/commit_pc/commit_insn`：真正完成的指令。
   新增的 `commit_rd_wen/commit_rd/commit_wdata` 给出寄存器写回，`commit_next_pc` 给出后继地址。
   `commit_mem_*` 给出数据访问；详见 [提交记录说明](commit-trace.md)。
6. `cycles/instret/fetch_wait/data_wait/halted/fault`：性能与结束状态。

最先比较同一条 LD 在 LATENCY=1 与 20 的波形：状态机会在 FETCH_RSP 和 DATA_RSP 多停留。
后续加入缓存后，对比命中与缺失路径，再讨论多个请求如何隐藏延迟。
