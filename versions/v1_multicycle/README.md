# v1：冻结的多周期基线

此目录的 RTL、仿真宿主、测试、软件与 Makefile 是提交 `8adc22c` 的逐字节快照。
保留 RV64IMAC、Zicsr/Zifencei、M/S/U、异常、中断和 Sv39/Svade。
后续架构修改写入其他版本目录，本目录用于重新测试与性能对照。

```sh
cd versions/v1_multicycle
make lint test
make timing
make diff PROGRAM=full_demo
```

所有构建文件位于本目录的 `build/`。永久性能记录位于 `results/<run-id>/`，
同一 run-id 不允许再次写入。跨版本比较从仓库根目录执行 `python3 tools/benchmark.py`。
实验使用的标准单元库在本机外部安装目录，路径可用 LIB 覆盖。
