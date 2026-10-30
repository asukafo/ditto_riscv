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
PROGRAMS := sum dependency pointer_chase load_add_store
IMAGES := $(addprefix build/,$(addsuffix .bin,$(PROGRAMS)))
.DEFAULT_GOAL := help
.PHONY: help sim diff test sweep wave diagrams lint synth timing clean tools
help:
	@echo 'make sim / diff [PROGRAM=sum|dependency|pointer_chase|load_add_store] [LATENCY=1] [GAP=0]'
	@echo 'make test / sweep / wave / diagrams / lint / synth / timing / tools / clean'
build:
	mkdir -p build
build/obj_dir/Vrv64_core: rtl/rv64_core.sv sim/main.cpp | build
	$(VERILATOR) --cc --exe --build --trace -Wall --top-module rv64_core --Mdir build/obj_dir -CFLAGS '-std=c++17' rtl/rv64_core.sv $(abspath sim/main.cpp)
build/pointers.bin: scripts/pointers.py | build
	$(PYTHON) $<
build/%.elf: sw/%.S build/pointers.bin
	$(CROSS)gcc -march=rv64i -mabi=lp64 -nostdlib -nostartfiles -Wl,-Ttext=0,-e,_start,--no-relax -o $@ $<
build/%.bin: build/%.elf
	$(CROSS)objcopy -O binary -j .text $< $@
sim: build/obj_dir/Vrv64_core build/$(PROGRAM).bin
	./build/obj_dir/Vrv64_core build/$(PROGRAM).bin $(LATENCY) build/$(PROGRAM).vcd $(GAP) build/$(PROGRAM).trace.jsonl
diff: sim
	$(PYTHON) scripts/reference.py --image build/$(PROGRAM).bin --trace build/$(PROGRAM).trace.jsonl --show 16
test: build/obj_dir/Vrv64_core $(IMAGES)
	$(PYTHON) scripts/experiments.py --test --cross '$(CROSS)'
	$(PYTHON) scripts/test_reference.py
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
