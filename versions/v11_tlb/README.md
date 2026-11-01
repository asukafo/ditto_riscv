# v11：独立I-TLB与D-TLB

目标是减少Sv39开启后的重复页表读取。在v10中，即使I/D-cache命中，每次翻译仍需访问页表。
v11给两侧MMU各增加8项全相联4KiB TLB，继承原有缓存、预测、RAS及特权/中断功能。
v1–v10分别冻结，所有版本的优化动机与成本见[根README](../../README.md)。

## IMEM/DMEM、cache、TLB分别是什么

IMEM/DMEM通常是指令/数据存储器或接口的名称。教学核可能直接连接两块预装程序/数据的RAM或ROM，
也可能用这个名字指缓存接口；名字本身不保证具备缓存机制，要看实现。
I-cache/D-cache明确表示自动保存底层内存部分内容的缓存，带tag、命中/缺失、替换与补数。
TLB保存的是地址翻译与权限信息，不保存指令或数据内容。

```text
教学例子： Fetch -> IMEM       Load/store -> DMEM

本工程： Fetch -> I-TLB / I页表遍历 -> I-cache --+
                                             +-> 仲裁/原子适配 -> 共享64KiB RAM与MMIO
         Data  -> D-TLB / D页表遍历 -> D-cache --+
```

I/D-cache各256B；I/D TLB各8项，每项描述一个4KiB页。8项翻译不意味着保存了32KiB数据。
双取指/访存接口也不要求底层必须是两块独立物理内存。外部仍只允许一笔事务在途。

## 结构与查找

`rtl/rv64_tlb.sv`是通用8项全相联翻译存储，两套`rtl/rv64_mmu.sv`分别实例化它。
每项保存VPN[38:12]、44位物理PPN、PTE低8位权限及完整64位satp上下文标签。
完整标签包含MODE、ASID、页表根PPN，避免同VPN在不同地址空间/根下误命中。
G映射也保守绑定上下文，不做跨ASID的全局项复用。

```text
accepted virtual request
        |
  Bare/M-mode? -> 原旁路
        |
  检查Sv39规范地址
        |
  TLB查VPN+完整satp
      /       \
   命中       缺失
    |           |
 按当前权限    原三层页表遍历
    |           |
 物理访问     成功4KiB叶子 -> 填入 -> 物理访问
```

填入优先更新同键项，其次使用无效槽，满时轮转替换；不缓存无效PTE或页错误结果。
只分配level=0的4KiB叶子。2MiB/1GiB大页仍由原遍历器正确处理，不误当作4KiB缓存。
成功翻译可先缓存，即使随后物理访问发生访问错误；TLB不代替物理存储器的访问错误检查。
Bare访问保持原时序路径，不增加翻译拍数；TLB命中经已有ACCESS_REQ阶段发出物理请求。

## 命中不等于有权访问

每次命中都重新使用当前effective privilege、SUM、MXR、读/写/取指类型检查缓存的R/W/X/U/A/D。
S态仍不能借SUM执行U页；MXR只放宽数据读取。Svade下A=0或写入D=0仍产生对应页错误，包含SC写权限探测。
MPRV由已有CSR模块给出的data_privilege进入同一检查，取指仍使用实际privilege。
非规范地址在使用命中项之前拒绝，不能利用VPN低位相同绕过检查。

这遵循[特权规范中SUM/MXR即时生效、Svade与地址翻译缓存的规则](https://docs.riscv.org/reference/isa/priv/supervisor.html)。
因此TLB hit计数可以包含被权限拒绝的请求，不能把它解释成成功访问数。

## 失效、上下文与在途遍历

已提交SFENCE.VMA使I/D TLB全部失效，不优化rs1/rs2范围；这是规范允许的保守over-fence。
已提交satp CSR访问也清空两侧，包含只读访问的保守清空；写satp改变地址空间前，核心原有串行化已排空在途访存。
普通SUM/MXR等CSR变化不清空TLB，必须依靠命中权限复查立即生效。
ASID和根标签可区分条目，但本版核心切换satp会清空，不声称保留切换前的热项。

遍历开始时保存原satp上下文，避免用后来的satp给旧结果打标签。
失效脉冲若发生在遍历中，会毒化该次填入，旧叶子结果不得在失效后重新置valid。
它不撤销已接受请求的响应；正常核心在SFENCE.VMA/satp串行化提交前已经排空两侧请求。
软件修改PTE后用SFENCE.VMA建立可见性；不依赖“TLB每次都重新读取PTE”。

`TLB_ENABLE=0`恢复原页表遍历路径。本轮36组周期数和外部请求数与同轮v10完全一致。
SPLIT_MEMORY=0配置保留单MMU/统一TLB路径，默认则是独立I/D TLB；其他开关保留各版本默认翻译配置。

## 分页实验与成本

新增公共paged_loop.S：S态、Sv39、64次同页load与循环取指，最终结果448。
[本轮72组主对照](../../results/comparisons/20261101T120125908358Z/comparison.csv)使用同一二进制，
每条提交与最终64KiB RAM都经独立模型验证。[36组TLB开关对照](results/20261101T120125908358Z/tlb-ablation.csv)
保留I/D页表读取与命中指标。旧实验的软件集合和CSV未覆盖。

| 分页同页循环 | v10无TLB周期 | v11周期 | 外部请求：v10→v11 |
|---|---:|---:|---:|
| 延迟1/间隔0 | 2781 | 964 | 1004→32 |
| 延迟5/间隔0 | 6790 | 1081 | 1004→32 |
| 延迟5/间隔3 | 8859 | 1131 | 1003→31 |

三种条件下，I页表读取均786→3，D页表读取均192→3：978次降为6次。
D-TLB有63次命中、1次缺失；高延迟有背压总周期减少约87.23%。
容量实验中4个数据页循环能命中，10个数据页轮转超过8项容量时持续替换；I-TLB不被D页挤出。
既有11个裸地址基准的总周期和外部请求均保持不变，不能把分页收益推广到Bare访问。

同Nangate45 typical约束下，标准单元面积136837.050→163863.980，约+19.75%；
布局前最小周期估计4.86→4.85ns。高延迟分页时间模型43054.74→5485.35ns。
TLB比较器和翻译存储有硬件成本；时钟估计的微小变化是整核映射结果，不是Bare访问获得了翻译命中收益。
这些是布局前估计，不是硬件实测；关闭配置未单独测量时序，不套用默认周期计算时间。

## 指标、波形与验证

itlb/dtlb的hits、misses只统计启用TLB后的已接受、规范Sv39请求；关闭TLB时这些指标为零。
fills统计成功4KiB翻译分配；i_walk_reads/d_walk_reads统计实际接受的PTE读取，不含最终数据访问。
tlb_invalidations统计核心提交的失效请求脉冲，关闭TLB时也可能观察到该脉冲。
所有统计由宿主沿前采样，不增加RTL64位反馈计数器。

[首次翻译缺失波形](docs/waveforms/tlb-miss.svg)与[热TLB命中波形](docs/waveforms/tlb-hit.svg)
来自实际build/tlb.vcd（延迟5/间隔3），控制沿前、commit沿后采样，CSV同时保存。
命中时仍可能发生I/D-cache缺失，req_addr也可能是取指、数据或PTE地址；结合walk_event和TLB事件判断。

12000步翻译存储模型检查覆盖上下文、替换、同键更新及失效；69项MMU检查覆盖权限、SUM/MXR即时变化、
Svade D位、SC探测、根/ASID隔离、非规范别名、PTE总线错误、在途失效和大页旁路。
新增45组整核检查覆盖分页局部性、4/10页容量、命中权限变化、定向SFENCE全清空、satp/ASID切换、
非连续物理页上的跨页指令与缺页异常；另有6组开关对照。旧并发MMU单元测试在直接修改PTE后显式发送失效，
使其符合有TLB时的同步约定，而不是继续依赖原来“每次都遍历”的行为。
原有整数、特权、中断、原子、缓存及预测回归保留；461组整核测试在RTL与门级分别通过，
922份提交/最终内存文件逐字节一致。门级采用无SDF的标准单元逻辑模型。

```sh
# 根目录默认v11
make lint test
make test-tlb
make test-mapped
make diagrams
make compare BENCHMARK_ARGS="--versions v10_return_stack v11_tlb"
make test VERSION=v10_return_stack
```
