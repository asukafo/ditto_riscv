# 当前时序估计从哪里来

19.64 ns 来自 Yosys 标准单元映射后的 OpenSTA 静态时序分析，不是 Verilator 运行程序测出的延迟。
程序仿真回答用了多少周期，STA 回答当前网表与约束下一个周期至少需要多长。

## 实际执行流程

```text
rtl/*.sv
   ↓ Yosys synth、dfflibmap、ABC
标准单元网表 build/core_mapped.v
   + NangateOpenCellLibrary_typical.lib
   + scripts/timing.tcl 中的时钟与接口约束
   ↓ OpenSTA
build/timing.log
```

RTL 本身只有逻辑关系。综合将它转换为触发器、与或门、多路选择器等单元。
Liberty 文件给出各单元的延迟和建立/保持时间表，延迟随输入转换时间、输出电容等变化。
当前库的 time_unit 是 1 ns、capacitive_load_unit 是 1 fF，名义条件为 1.10 V、25 °C、typical process。

## 目标与结果是两个不同的数

Makefile 的 CLOCK_NS 默认值为 10，通过 create_clock 设置目标周期，即 100 MHz。
它是输入约束，不是分析结果。
当前还假定输入/输出延迟为 1 ns、输入转换时间为 0.1 ns、输出负载为 0.01 fF。
这些接口数值是初始假设，应由真实接口环境取代。

## 本次最差路径的实际报告

起点 `_10695_` 的 Q 连接 `insn[20]`，终点 `_11094_` 的 Q 连接 `instret[62]`。
路径经过寄存器堆、译码及顶层控制逻辑，最后进入计数器的 D 端。
这些单元编号属于当前映射结果，重新综合可能改变。

```text
clock launch                            0.00 ns
data arrival time                      19.60 ns
next capture edge                      10.00 ns
library setup time                      0.04 ns
data required time                      9.96 ns
slack                                  -9.64 ns (VIOLATED)

core_clk period_min = 19.64, fmax = 50.91
```

按报告舍入后的数字：

```text
所需最小周期 ≈ 数据路径到达时间 + 建立时间
             ≈ 19.60 + 0.04 = 19.64 ns

10 ns 目标下的 slack ≈ (10.00 - 0.04) - 19.60 = -9.64 ns
```

19.60 ns 中已经包括起点触发器 clk→Q 和后续组合逻辑的传播延迟。
最差路径并不一定落在“主 ALU”；控制信号、读选择和调试计数器同样可能限制时钟。
报告不是说一条指令总共只用 19.64 ns；指令可能需要许多这样的时钟周期。

## 结果的实际边界

当前时钟是 ideal，没有实际时钟树、skew/uncertainty、布局布线或提取的线网寄生。
使用研究用标准单元库，未做真实 FPGA 器件映射，也未做多工艺角签核。
报告里部分单元延迟很大，还需检查扇出、电容、转换时间、查表外推与缓冲/尺寸优化。
因此 50.91 MHz 只是当前模型的计算结果，不能当作芯片或 FPGA 的实际最高频率。

核采用多周期状态机，也不意味着可以任意把组合路径标记为 multicycle。
只有实际设计允许跨多个时钟采样的路径，才有依据设置相应例外。

重现命令：make timing，随后查看 build/timing.log。

## 参考

[OpenSTA 官方说明](https://openroad.readthedocs.io/en/latest/main/src/sta/README.html)
