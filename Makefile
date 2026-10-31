VERILATOR ?= verilator
YOSYS ?= yosys
STA ?= sta
LIB ?= $(HOME)/.local/opt/opensta/share/lib/NangateOpenCellLibrary_typical.lib
CLOCK_NS ?= 10
CROSS ?= riscv64-elf-
PYTHON ?= python3
PROGRAM ?= sum
LATENCY ?= 1
GAP ?= 0
PROGRAMS := sum dependency pointer_chase load_add_store bit_ops c_demo
IMAGES := $(addprefix build/,$(addsuffix .bin,$(PROGRAMS)))
.DEFAULT_GOAL := help
.PHONY: help sim diff test test-alu test-rv64i sweep wave diagrams lint synth timing clean tools
help:
	@echo 'make sim / diff [PROGRAM=sum|dependency|pointer_chase|load_add_store|bit_ops|c_demo] [LATENCY=1] [GAP=0]'
	@echo 'make test / test-alu / test-rv64i / sweep / wave / diagrams / lint / synth / timing / tools / clean'
build:
	mkdir -p build
build/obj_dir/Vrv64_core: rtl/rv64_core.sv sim/main.cpp | build
	$(VERILATOR) --cc --exe --build --trace -Wall --top-module rv64_core --Mdir build/obj_dir -CFLAGS '-std=c++17' rtl/rv64_core.sv $(abspath sim/main.cpp)
build/pointers.bin: scripts/pointers.py | build
	$(PYTHON) $<
build/%.elf: sw/%.S sw/finish.inc build/pointers.bin
	$(CROSS)gcc -march=rv64i -mabi=lp64 -nostdlib -nostartfiles -Wl,-Ttext=0,-e,_start,--no-relax -o $@ $<
build/%.bin: build/%.elf
	$(CROSS)objcopy -O binary -j .text $< $@
CFLAGS_RV64I := -march=rv64i -mabi=lp64 -ffreestanding -fno-builtin -fno-stack-protector -fno-pic -fno-pie -msmall-data-limit=0 -mno-relax -Wall -Wextra -Werror
build/c_demo.elf: sw/c_demo.c sw/start.S sw/link.ld | build
	$(CROSS)gcc $(CFLAGS_RV64I) -O2 -nostdlib -nostartfiles -Wl,-T,sw/link.ld,--no-relax -o $@ sw/start.S sw/c_demo.c
build/c_demo.bin: build/c_demo.elf
	$(CROSS)objcopy -O binary $< $@
build/c_demo_o0.elf: sw/c_demo.c sw/start.S sw/link.ld | build
	$(CROSS)gcc $(CFLAGS_RV64I) -O0 -nostdlib -nostartfiles -Wl,-T,sw/link.ld,--no-relax -o $@ sw/start.S sw/c_demo.c
build/c_demo_o0.bin: build/c_demo_o0.elf
	$(CROSS)objcopy -O binary $< $@
sim: build/obj_dir/Vrv64_core build/$(PROGRAM).bin
	./build/obj_dir/Vrv64_core build/$(PROGRAM).bin $(LATENCY) build/$(PROGRAM).vcd $(GAP) build/$(PROGRAM).trace.jsonl
diff: sim
	$(PYTHON) scripts/reference.py --image build/$(PROGRAM).bin --trace build/$(PROGRAM).trace.jsonl --show 16
test: build/obj_dir/Vrv64_core $(IMAGES) build/c_demo_o0.bin
	$(PYTHON) scripts/experiments.py --test --cross '$(CROSS)'
	$(PYTHON) scripts/test_reference.py
	$(PYTHON) scripts/alu_tests.py --cross '$(CROSS)'
	$(PYTHON) scripts/rv64i_tests.py --cross '$(CROSS)'
test-alu: build/obj_dir/Vrv64_core
	$(PYTHON) scripts/alu_tests.py --cross '$(CROSS)'
test-rv64i: test-alu build/c_demo.bin build/c_demo_o0.bin
	$(PYTHON) scripts/rv64i_tests.py --cross '$(CROSS)'
sweep: build/obj_dir/Vrv64_core $(IMAGES)
	$(PYTHON) scripts/experiments.py
wave: sim
	surfer build/$(PROGRAM).vcd
diagrams: build/obj_dir/Vrv64_core build/sum.bin
	./build/obj_dir/Vrv64_core build/sum.bin 1 build/load-l1.vcd 0
	./build/obj_dir/Vrv64_core build/sum.bin 5 build/load-l5.vcd 0
	./build/obj_dir/Vrv64_core build/sum.bin 1 build/load-gap3.vcd 3
	$(PYTHON) scripts/waveforms.py
lint:
	$(VERILATOR) --lint-only -Wall --top-module rv64_core rtl/rv64_core.sv
synth: | build
	$(YOSYS) -Q -T -p 'read_verilog -sv rtl/rv64_core.sv; synth -top rv64_core; check -assert; stat; write_verilog -noattr build/core_netlist.v' > build/synthesis.log
timing: | build
	test -f "$(LIB)"
	$(YOSYS) -Q -T -p 'read_verilog -sv rtl/rv64_core.sv; synth -top rv64_core; dfflibmap -liberty "$(LIB)"; abc -liberty "$(LIB)"; read_liberty -lib "$(LIB)"; clean; check -assert; stat -liberty "$(LIB)"; write_verilog -noattr -noexpr build/core_mapped.v' > build/mapping.log
	LIB="$(LIB)" CLOCK_NS="$(CLOCK_NS)" $(STA) -exit scripts/timing.tcl > build/timing.log
tools:
	$(VERILATOR) --version
	surfer --version
	$(YOSYS) -V
	$(CROSS)gcc --version
	@command -v sta
clean:
	rm -rf build
.SECONDARY:
