# v26 第二槽直接分支预测

基于 v25 的双包前端。在第一条预测顺序执行且剩余字节组成完整指令时，第二槽可以随第一槽发送条件分支或 JAL。条件分支使用同一提交历史和同一训练输入的独立 BHT 查询，JAL 直接从编码计算目标。第二包保存自己的预测后继和训练索引。预测跳转时，取指丢弃顺序尾部字节并转向目标。第二槽的 JALR、CSR、系统和栅栏仍走第一槽处理。

第二槽分支可以进入队列，执行时仍走原有的主执行槽。这样分离了取指带宽和双执行资格两个实验变量。使用 `SECOND_BRANCH=0` 可构建关闭该优化的对照。

## 逐周期定位

[采样数据](results/branch-diagnosis/cycles.csv)来自同一程序镜像、内存延迟 5、间隔 3 的 Verilator VCD。每个有效上升沿前采样一次。发射类、前端等待、访存等待、乘除等待及其余未发射周期互斥。分支误判与第二槽推迟是另计的事件。

| 程序 | v24 周期 | v25 周期 | v26 周期 |
| --- | ---: | ---: | ---: |
| branch_alternating | 475 | 635 | 439 |
| branch_phase | 451 | 551 | 407 |
| hot_alu | 1419 | 915 | 915 |
| pointer_chase | 1355 | 1371 | 1371 |

`branch_alternating` 在 v24 和 v25 都误判 5 次。v25 推迟 128 个已经完整的第二槽控制指令，在 X 完成但无指令可接续的周期从 39 增至 157。原型将该等待降至 7 周期，同时观察到 7 次误判。`pointer_chase` 的 v25 和原型均有 915 周期处于数据请求或响应等待。

四个原型运行均逐条核对退休记录及最终 64 KiB RAM。完整回归、Verilator lint 和 Yosys 结构检查均已通过。关闭 SECOND_BRANCH 后，60 组用例的周期、请求、误判和退休数量均恢复至 v25。

## 复现采样

从仓库根目录运行，先构建三个版本的 `build/full_obj/Vrv64_core`，并通过比较工具生成 v25 的公共程序镜像。

```sh
mkdir -p .local/v26
for v in v24_dual_alu v25_wide_frontend v26_second_branch; do
  for p in branch_alternating branch_phase hot_alu pointer_chase; do
    versions/$v/build/full_obj/Vrv64_core \
      versions/v25_wide_frontend/build/$p.bin 5 \
      .local/v26/$v-$p.vcd 3 .local/v26/$v-$p.jsonl
  done
done
python3 versions/v26_second_branch/scripts/bottlenecks.py .local/v26/v2[456]*.vcd
```

公共比较共 20 个程序、三种内存条件。相对 v25，15 组更快、42 组持平、3 组变慢，合计减少 1901 周期。热 ALU 循环仍以 576 周期退休 960 条指令。参见[完整比较](../../results/comparisons/v26-second-branch/comparison.csv)。

第二槽预测跳转前后的上升沿可用 `python3 versions/v26_second_branch/scripts/branch_window.py .local/v26/v26_second_branch-branch_alternating.vcd` 重新采样。地址列在对应 valid 有效时才表示请求或指令。[实际 VCD 采样](results/branch-diagnosis/branch-window.csv)
