# v10：提交时维护的返回地址栈

目标是改善v9未预测的函数返回。v9裸机C有12次间接跳转失误，其中包括6次间接调用和6次返回，
不能把12次都叫作返回。v10加入8项返回地址栈（RAS），用已提交调用的返回地址预测常见ret。
v1–v9分别冻结；所有版本的动机、结果与成本见[根README](../../README.md)。

## 保存什么、何时更新

`rtl/rv64_return_stack.sv`保存8个64位虚拟返回地址，entries[0]为栈顶，count记录0–8项。
调用返回地址是提交指令自身PC+实际长度，压缩JALR保存PC+2，普通JAL/JALR保存PC+4。
它是预测用硬件状态，不代替架构寄存器ra或软件内存栈。

提交提示遵循[RISC-V非特权规范的RAS提示规则](https://docs.riscv.org/reference/isa/unpriv/rv32.html)，
链接寄存器为x1/x5：

| 已提交指令 | 更新 |
|---|---|
| JAL，rd为链接寄存器 | push返回地址 |
| JALR，rs1为链接寄存器、rd不是链接寄存器 | pop |
| JALR，rd为链接寄存器、rs1不是链接寄存器 | push |
| JALR，rd/rs1都是链接寄存器且相同 | 只push |
| JALR，rd/rs1是不同的链接寄存器 | 先pop再push |
| 其他指令 | 不改变 |

满栈push丢弃最老项，保留最新8个；空栈pop无数据可取，记录下溢；pop+push替换栈顶，空栈时生成一项。
输入retire=0的错误路径调用/返回不更新。clear优先于当周期push/pop。
核心在异常/中断进入和所有串行化提交（含CSR、FENCE、MRET/SRET等）时保守清空历史，避免旧上下文/代码混用。
这也会损失部分可用预测，故不是所有函数返回都能命中RAS。

## 预测与恢复

```text
committed call -> push (call PC + bytes)
                         |
                  current RAS top
                         |
F sees jalr x0,0(x1/x5) -> predicted_next + predicted_return packet
                         |
X computes actual target -> compare saved prediction -> correct or redirect
                         |
committed return -> pop
```

仅在RAS有效、目标对齐、指令合法且识别为jalr x0,0(x1/x5)时使用栈顶；C.JR解压后走同一路径。
普通间接调用、非零立即数JALR及其他寄存器形式继续按v9的顺序预测，静态条件分支/JAL规则不变。
F把predicted_return与predicted_next一起寄存，暂停时保持；RAS随后变化不能修改已经输出的预测。
X依旧通过真实下一PC纠正错误，所以软件修改ra、非标准返回或陈旧栈顶都不影响ISA正确性。
错误目标上的store/异常不能提交，原有取指响应排空、MMU权限检查和串行化规则保留。

本版只用提交历史，不在F推测push/pop，也不需要栈回滚检查点。
很短的调用、紧邻的返回或同周期提交尚未更新栈时，F可能看不到最新项或看到旧栈顶，允许回退/失误后恢复。
这是有意保留的简化，不声称具备完整推测RAS性能；没有返回地址栈的逐上下文保存恢复。

`RAS_ENABLE=0`关闭RAS，保留v9静态预测；本轮33组周期数和外部请求数与同轮v9完全一致。
`PREDICT_ENABLE=0`同时关闭静态预测与RAS。其他开关对照继续使用各版本默认的RAS配置。

## 实测结果与时序取舍

[本轮66组主对照](../../results/comparisons/20261101T112830714269Z/comparison.csv)
执行相同二进制，提交与最终64KiB RAM通过独立模型验证。
[33组RAS开关对照](results/20261101T112830714269Z/ras-ablation.csv)分别记录预测与间接跳转失误。
新增公共calls.S基准观察调用密集情形，旧实验的软件集合和CSV未覆盖。

| 程序 | 延迟1/间隔0：v9→v10周期 | 延迟5/间隔3：v9→v10周期 | 间接跳转失误：v9→v10 |
|---|---:|---:|---:|
| 16次函数调用 | 320→288 | 379→343 | 16→0 |
| 裸机C | 440→429 | 955→943 | 12→6 |
| M/A/C C | 472→466 | 843→835 | 8→5 |
| 求和 | 798→798 | 983→983 | 0→0 |
| 独立ALU | 742→742 | 1623→1623 | 0→0 |

调用基准有16次RAS预测，全部正确；裸机C有6次返回预测，全部正确，剩余6次间接调用仍失误。
M/A/C C只有3次返回使用RAS，剩余失误包含未预测的调用和失去历史后的返回。
收益来自减少返回冲刷，不减少普通数据请求；本轮主基准外部请求数均保持不变。

代价同样明确：Nangate45 typical、相同约束下，布局前最小周期4.64→4.86ns，
标准单元面积131956.748→136837.050，面积约+3.70%，周期约+4.74%。
调用基准高延迟时间模型1758.56→1666.98ns，改善约5.21%；
裸机C则4431.20→4582.98ns，M/A/C C为3911.52→4058.10ns，周期数减少仍不足抵消时钟周期增大。
没有调用的程序总周期不变，模型时间也会随时钟周期变长。
因此v10是可验证的提交RAS基线，不是所有程序都更快的版本；可按工作负载选择保留的旧版进行比较。
这些是整核布局前映射估计，不是硬件实测；关闭开关配置未独立测量时序，不套用默认周期估算其时间。

## 观测、波形与验证

ras_predictions/ras_misses在X解析时统计使用RAS的预测及失误；
ras_pushes/ras_pops在提交更新时统计，ras_overflows/ras_underflows记录边界事件。
计数由宿主沿前采样，不增加RTL64位反馈计数器；预测数和提交更新数不要求逐周期相同。

[提交push波形](docs/waveforms/return-stack-push.svg)与[返回预测/pop波形](docs/waveforms/return-stack.svg)
来自实际build/ras.vcd（延迟5/间隔3）。控制沿前、commit沿后采样，CSV同时保存。
栈顶是已提交历史，fe_predicted_next是F所属指令已保存的目标，二者属于不同时间点，不能混为一个PC。

| 周期 | 本轮波形中的动作 |
|---|---|
| C25 | 提交PC=0x08的调用，保存返回地址0x0c；C26沿前可见count=1 |
| C61 | F中的PC=0x34返回指令携带预测目标0x0c |
| C62 | X解析该返回，使用RAS且未失误，无redirect |
| C63 | 返回提交，commit_next_pc=0x0c，同时pop；C64沿前可见count=0 |

24866步单元测试分别运行启用/关闭RAS，覆盖rd/rs1提示组合、2/4字节链接值、PC回绕、
提交禁止、清空优先、满栈丢弃、下溢和pop+push；27项取指检查覆盖x1/x5返回、C.JR、
暂停时改变外部栈顶、空栈回退及非标准JALR不使用RAS。
新增50组整核测试覆盖重复/嵌套/压缩调用、替代链接寄存器、12层溢出、下溢、错误路径调用不污染历史、
修改ra后的预测错误、CSR清空和异常/MRET清空，另有12组开关对照。
原有整数、M/A/C、特权、中断、Sv39、缓存与预测回归保留；416组整核测试在RTL与门级分别通过，
832份提交/最终内存文件逐字节一致。门级使用无SDF的标准单元逻辑模型。

```sh
# 仓库根目录默认v10
make lint test
make test-ras
make test-mapped
make diagrams
make compare BENCHMARK_ARGS="--versions v9_static_predict v10_return_stack"
make test VERSION=v9_static_predict
```
