# 逐条提交跟踪与自动对照

## 本阶段实现什么

core 的指令集与执行结构保持原有教学子集，增加提交观察接口。
仿真驱动在每个上升沿执行完成之后采样，把成功提交的指令写入 JSONL。
独立 Python 模型从相同程序镜像开始，自行维护 PC、32 个寄存器和 64 KiB 内存，
不读取 RTL 的运行时寄存器、状态机或内存响应来决定指令结果。
它以指令为单位执行，不模拟等待周期。不同 LATENCY/GAP 应产生相同架构提交序列，周期可不同。

这是本项目维护的小型子集模型，不是 Spike，不代表完整 RISC-V 合规验证。
它明确包含当前环境的教学约定：PC 从 0 开始、8 字节事务边界、EBREAK 正常停止并计入提交、
非法指令/未对齐/越界分别以 fault=1/2/3 停止。尚无特权异常或中断。

## 如何运行

```bash
make diff PROGRAM=load_add_store
make diff PROGRAM=load_add_store LATENCY=5 GAP=3
make test
```

`make diff` 自动仿真、显示前 16 次提交并核对全部记录。输出末尾的 DIFF PASS 表示：
全部提交、正常/错误停止状态和最终 65536 个内存字节都与参考模型一致。
生成文件全部位于 build/，不提交到仓库：

```text
load_add_store.vcd                  实际周期波形
load_add_store.trace.jsonl          逐条提交与最后一条 halt 记录
load_add_store.trace.jsonl.ram      最终完整 RAM 快照
```

驱动的完整命令行为：
`Vrv64_core image.bin latency [wave.vcd|-] [request_gap] [trace.jsonl]`。
不提供 trace 参数时保留原有行为。trace 开启时会自动写 RAM 快照。

## 每条记录的含义

以下新 RTL 输出均在 commit_valid=1 时有效：

| RTL 信号 | JSON 字段 | 含义 |
|---|---|---|
| commit_pc / commit_insn | pc / insn | 刚完成的指令地址与机器码 |
| commit_next_pc | next_pc | 执行该指令后架构上的后继地址，包含分支结果 |
| commit_rd_wen | rd_wen | 是否实际写入非 x0 寄存器 |
| commit_rd / commit_wdata | rd / wdata | 目的寄存器和写回数值 |
| commit_mem_valid | mem_valid | 是否为数据访存，取指不算 |
| commit_mem_write | mem_write | 数据访问是 SD 还是 LD |
| commit_mem_addr / commit_mem_data | mem_addr / mem_data | 数据地址和写入/读回的完整 64 位数据 |

JSON 另外记录 kind=commit，以及采样时的全局有效周期数 cycle。
无寄存器写回时 rd/wdata 统一为 0；无数据访存时 mem_* 统一为 0。
LD x0 仍然产生有效内存读，但 rd_wen=0，绝不能跳过访存检查。
SD、分支、EBREAK 没有整数寄存器写回。
JSON 数字为十进制，命令行展示使用十六进制；64 位数值不能用会丢失精度的 JavaScript Number 处理。

当前执行结构中写回与提交发生在同一时钟沿。未来乱序核中的执行结果写回和架构提交需要分开，
此接口届时应只报告真正提交的指令，不能直接连接任意执行完成事件。

正常或 fault 停止时，驱动最后写 kind=halt，包含 fault、instret、cycles。
非法/错误指令不产生成功提交。检查器会自行执行下一条，确认确实应发生对应错误。
缺少 halt、丢失/重复提交、EBREAK 后多余记录或不匹配字段都会失败。

## LD → ADD → SD → 分支实验

新程序把数组 `[1,2,3,4]` 的每个元素加 10 并原地保存，最后回读 14 放到结果地址 0x200。
它与 sum 是两个独立程序；这里 t2 初始化为 10，而 sum 中 t2 初始化为 0 用于累加。

```asm
loop:
    ld t3, 0(t0)
    add t3, t3, t2
    sd t3, 0(t0)
    addi t0, t0, 8
    addi t1, t1, -1
    bne t1, zero, loop
```

LATENCY=1、GAP=0 下的实际输出片段如下，周期是从复位释放后累计的全局周期：

```text
#004 C14 PC=0x000c ld   x28=0x1; load [0x1000]=0x1; next=0x10
#005 C17 PC=0x0010 add  x28=0xb; next=0x14
#006 C22 PC=0x0014 sd   no register write; store [0x1000]=0xb; next=0x18
#009 C31 PC=0x0020 bne  no register write; next=0xc
```

第一轮读到 1，加 10 得到 11（0xb），写回地址 0x1000，然后分支回到 LD。
分支的 next_pc 依次为 `0x0c,0x0c,0x0c,0x24`，最后一次退出循环。
回归同时直接检查最终数组为 `[11,12,13,14]`。
这个程序共提交 30 条指令，有 10 次数据访问；L=1/5/20 时分别为 110/270/870 周期。

## 检查器是否真的能发现错误

`make test` 会运行 50 次正常/错误路径仿真，再运行 12 项检查器测试。
检查器测试覆盖所有架构字段的篡改、错误 store 数据、丢失/重复/乱序提交、错误 halt、
缺失字段、周期顺序错误、完整内存损坏及已知的 x0/64 位回绕语义。
其中每个字段测试还有多个子用例。

例如把第一条 LD 的 wdata 从 1 改为 99，将定位到：

```text
commit #4 PC=0xc (ld): wdata: RTL=99, reference=1 (0x1)
```

目前采用仿真结束后的离线对照，能报告第一处差异，但不会在差异发生的那个周期停止 RTL。
后续可以扩展为在线协同仿真，并引入成熟 ISS 做第三方交叉验证。
