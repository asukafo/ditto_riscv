VERILATOR ?= verilator
YOSYS ?= yosys
STA ?= sta
LIB ?= $(HOME)/.local/opt/opensta/share/lib/NangateOpenCellLibrary_typical.lib
CLOCK_NS ?= 10
ABC_OPTIONS ?= -constr scripts/abc.constr
CROSS ?= riscv64-elf-
PYTHON ?= python3
PROGRAM ?= sum
LATENCY ?= 1
GAP ?= 0
PROGRAMS := sum dependency pointer_chase load_add_store bit_ops c_demo
IMAGES := $(addprefix build/,$(addsuffix .bin,$(PROGRAMS)))
RTL := $(sort $(wildcard rtl/*.sv))
SIMULATOR ?= build/full_obj/Vrv64_core
.DEFAULT_GOAL := help
.PHONY: help sim diff test test-base test-full test-pipeline test-mapped test-alu test-rv64i sweep wave diagrams lint synth timing clean tools
help:
	@echo 'make sim / diff [PROGRAM=sum|c_demo|full_demo|machine_demo|...] [LATENCY=1] [GAP=0]'
	@echo 'make test / test-base / test-full / test-mapped / test-alu / test-rv64i / sweep / wave / diagrams / lint / synth / timing / tools / clean'
build:
	mkdir -p build
build/obj_dir/Vrv64_core: $(RTL) sim/main.cpp | build
	$(VERILATOR) --cc --exe --build --trace -Wall --top-module rv64_core -GEXTENSIONS=0 -GHOST_TRAPS=1 --Mdir build/obj_dir -CFLAGS '-std=c++17' $(RTL) $(abspath sim/main.cpp)
build/full_obj/Vrv64_core: $(RTL) sim/main.cpp | build
	$(VERILATOR) --cc --exe --build --trace -Wall --top-module rv64_core --Mdir build/full_obj -CFLAGS '-std=c++17' $(RTL) $(abspath sim/main.cpp)
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
build/full_demo.elf: sw/full_demo.c sw/start.S sw/link.ld | build
	$(CROSS)gcc $(filter-out -march=rv64i,$(CFLAGS_RV64I)) -march=rv64imac_zicsr_zifencei -O2 -nostdlib -nostartfiles -Wl,-T,sw/link.ld,--no-relax -o $@ sw/start.S sw/full_demo.c
build/full_demo_o0.elf: sw/full_demo.c sw/start.S sw/link.ld | build
	$(CROSS)gcc $(filter-out -march=rv64i,$(CFLAGS_RV64I)) -march=rv64imac_zicsr_zifencei -O0 -nostdlib -nostartfiles -Wl,-T,sw/link.ld,--no-relax -o $@ sw/start.S sw/full_demo.c
build/full_demo.bin: build/full_demo.elf
	$(CROSS)objcopy -O binary $< $@
build/full_demo_o0.bin: build/full_demo_o0.elf
	$(CROSS)objcopy -O binary $< $@
build/machine_demo.elf: sw/machine_demo.S sw/finish.inc | build
	$(CROSS)gcc -march=rv64imac_zicsr_zifencei -mabi=lp64 -nostdlib -nostartfiles -Wl,-Ttext=0,-e,_start,--no-relax -o $@ $<
sim: $(SIMULATOR) build/$(PROGRAM).bin
	./$(SIMULATOR) build/$(PROGRAM).bin $(LATENCY) build/$(PROGRAM).vcd $(GAP) build/$(PROGRAM).trace.jsonl
diff: sim
	$(PYTHON) scripts/reference.py --image build/$(PROGRAM).bin --trace build/$(PROGRAM).trace.jsonl --show 16
test: test-base test-full test-pipeline
test-pipeline: build/full_obj/Vrv64_core
	$(PYTHON) scripts/pipeline_tests.py --cross '$(CROSS)'
test-base: build/obj_dir/Vrv64_core $(IMAGES) build/c_demo_o0.bin
	$(PYTHON) scripts/experiments.py --test --cross '$(CROSS)'
	$(PYTHON) scripts/test_reference.py
	$(PYTHON) scripts/alu_tests.py --cross '$(CROSS)'
	$(PYTHON) scripts/rv64i_tests.py --cross '$(CROSS)'
test-full: build/full_obj/Vrv64_core build/full_demo.bin build/full_demo_o0.bin build/machine_demo.bin
	$(PYTHON) scripts/extension_tests.py --cross '$(CROSS)'
	$(PYTHON) scripts/privileged_tests.py --cross '$(CROSS)'
	$(PYTHON) scripts/test_full_reference.py
# Functional gate simulation: Liberty supplies Boolean/FF models, not SDF delays.
# Always remap so this target cannot silently simulate a stale netlist.
test-mapped: timing build/full_demo.bin build/full_demo_o0.bin build/machine_demo.bin
	$(YOSYS) -Q -T -p 'read_liberty -ignore_miss_func "$(LIB)"; proc; opt; write_verilog -noattr build/cell_models.v' > build/cell_models.log
	$(VERILATOR) --cc --exe --build --trace --top-module rv64_core --Mdir build/mapped_obj -CFLAGS '-std=c++17' build/core_mapped.v build/cell_models.v $(abspath sim/main.cpp)
	SIMULATOR=build/mapped_obj/Vrv64_core $(PYTHON) scripts/extension_tests.py --cross '$(CROSS)'
	SIMULATOR=build/mapped_obj/Vrv64_core $(PYTHON) scripts/privileged_tests.py --cross '$(CROSS)'
	SIMULATOR=build/mapped_obj/Vrv64_core $(PYTHON) scripts/pipeline_tests.py --cross '$(CROSS)'
	$(PYTHON) scripts/test_full_reference.py
test-alu: build/obj_dir/Vrv64_core
	$(PYTHON) scripts/alu_tests.py --cross '$(CROSS)'
test-rv64i: test-alu build/c_demo.bin build/c_demo_o0.bin
	$(PYTHON) scripts/rv64i_tests.py --cross '$(CROSS)'
sweep: build/obj_dir/Vrv64_core $(IMAGES)
	$(PYTHON) scripts/experiments.py
wave: sim
	surfer build/$(PROGRAM).vcd
diagrams: test-pipeline
	$(PYTHON) scripts/pipeline_waveforms.py
lint:
	$(VERILATOR) --lint-only -Wall --top-module rv64_core $(RTL)
synth: | build
	$(YOSYS) -Q -T -p 'read_verilog -sv $(RTL); synth -top rv64_core; check -assert; stat; write_verilog -noattr build/core_netlist.v' > build/synthesis.log
timing: | build
	test -f "$(LIB)"
	$(YOSYS) -Q -T -p 'read_verilog -sv $(RTL); synth -top rv64_core; dfflibmap -liberty "$(LIB)"; abc -liberty "$(LIB)" $(ABC_OPTIONS); read_liberty -lib "$(LIB)"; clean; check -assert; stat -liberty "$(LIB)"; write_verilog -noattr -noexpr build/core_mapped.v' > build/mapping.log
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
