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
.PHONY: help sim diff test test-base test-full test-pipeline test-icache test-fetch test-early test-dcache test-data-early test-split test-predict test-ras test-tlb test-mapped test-alu test-rv64i sweep wave diagrams lint synth timing clean tools
help:
	@echo 'make sim / diff [PROGRAM=sum|c_demo|full_demo|machine_demo|...] [LATENCY=1] [GAP=0]'
	@echo 'make test / test-priority / test-issue / test-forward / test-path / test-window / test-ifetch / test-queue / test-btb / test-gshare / test-bht / test-tlb / test-ras / test-predict / test-split / test-data-early / test-dcache / test-early / test-fetch / test-icache / test-base / test-full / test-mapped / test-alu / test-rv64i / sweep / wave / diagrams / lint / synth / timing / tools / clean'
build:
	mkdir -p build
build/obj_dir/Vrv64_core: $(RTL) sim/main.cpp | build
	$(VERILATOR) --cc --exe --build --trace -Wall --top-module rv64_core -GEXTENSIONS=0 -GHOST_TRAPS=1 --Mdir build/obj_dir -CFLAGS '-std=c++17' $(RTL) $(abspath sim/main.cpp)
build/full_obj/Vrv64_core: $(RTL) sim/main.cpp | build
	$(VERILATOR) --cc --exe --build --trace -Wall --top-module rv64_core --Mdir build/full_obj -CFLAGS '-std=c++17' $(RTL) $(abspath sim/main.cpp)
build/noicache_obj/Vrv64_core: $(RTL) sim/main.cpp | build
	$(VERILATOR) --cc --exe --build --trace -Wall --top-module rv64_core -GICACHE_ENABLE=0 --Mdir build/noicache_obj -CFLAGS '-std=c++17' $(RTL) $(abspath sim/main.cpp)
build/nobuffer_obj/Vrv64_core: $(RTL) sim/main.cpp | build
	$(VERILATOR) --cc --exe --build --trace -Wall --top-module rv64_core -GFETCH_BUFFER_ENABLE=0 --Mdir build/nobuffer_obj -CFLAGS '-std=c++17' $(RTL) $(abspath sim/main.cpp)
build/noearly_obj/Vrv64_core: $(RTL) sim/main.cpp | build
	$(VERILATOR) --cc --exe --build --trace -Wall --top-module rv64_core -GEARLY_RESTART=0 --Mdir build/noearly_obj -CFLAGS '-std=c++17' $(RTL) $(abspath sim/main.cpp)
build/nodcache_obj/Vrv64_core: $(RTL) sim/main.cpp | build
	$(VERILATOR) --cc --exe --build --trace -Wall --top-module rv64_core -GDCACHE_ENABLE=0 --Mdir build/nodcache_obj -CFLAGS '-std=c++17' $(RTL) $(abspath sim/main.cpp)
build/nodataearly_obj/Vrv64_core: $(RTL) sim/main.cpp | build
	$(VERILATOR) --cc --exe --build --trace -Wall --top-module rv64_core -GDCACHE_EARLY_RESTART=0 --Mdir build/nodataearly_obj -CFLAGS '-std=c++17' $(RTL) $(abspath sim/main.cpp)
build/dcache_obj/Vrv64_dcache: rtl/rv64_dcache.sv sim/dcache_test.cpp | build
	$(VERILATOR) --cc --exe --build -Wall --top-module rv64_dcache -GEARLY_RESTART=0 --Mdir build/dcache_obj -CFLAGS '-std=c++17' rtl/rv64_dcache.sv $(abspath sim/dcache_test.cpp)
test-dcache: build/dcache_obj/Vrv64_dcache build/full_obj/Vrv64_core build/nodcache_obj/Vrv64_core
	./build/dcache_obj/Vrv64_dcache
	$(PYTHON) scripts/dcache_tests.py --cross '$(CROSS)'
build/dataearly_obj/Vrv64_dcache: rtl/rv64_dcache.sv sim/dcache_early_test.cpp sim/dcache_test.cpp | build
	$(VERILATOR) --cc --exe --build -Wall --top-module rv64_dcache --Mdir build/dataearly_obj -CFLAGS '-std=c++17' rtl/rv64_dcache.sv $(abspath sim/dcache_early_test.cpp)
test-data-early: build/dataearly_obj/Vrv64_dcache build/full_obj/Vrv64_core build/nodataearly_obj/Vrv64_core
	./build/dataearly_obj/Vrv64_dcache
	$(PYTHON) scripts/dcache_early_tests.py --cross '$(CROSS)'
build/unsplit_obj/Vrv64_core: $(RTL) sim/main.cpp | build
	$(VERILATOR) --cc --exe --build --trace -Wall --top-module rv64_core -GSPLIT_MEMORY=0 --Mdir build/unsplit_obj -CFLAGS '-std=c++17' $(RTL) $(abspath sim/main.cpp)
build/arbiter_obj/Vrv64_physical_arbiter: rtl/rv64_physical_arbiter.sv sim/physical_arbiter_test.cpp | build
	$(VERILATOR) --cc --exe --build -Wall --top-module rv64_physical_arbiter --Mdir build/arbiter_obj -CFLAGS '-std=c++17' rtl/rv64_physical_arbiter.sv $(abspath sim/physical_arbiter_test.cpp)
build/memory_obj/Vrv64_memory_system: $(RTL) sim/memory_system_test.cpp | build
	$(VERILATOR) --cc --exe --build -Wall --top-module rv64_memory_system --Mdir build/memory_obj -CFLAGS '-std=c++17' $(RTL) $(abspath sim/memory_system_test.cpp)
test-split: build/arbiter_obj/Vrv64_physical_arbiter build/memory_obj/Vrv64_memory_system build/full_obj/Vrv64_core build/unsplit_obj/Vrv64_core
	./build/arbiter_obj/Vrv64_physical_arbiter
	./build/memory_obj/Vrv64_memory_system
	$(PYTHON) scripts/split_memory_tests.py --cross '$(CROSS)'
build/nopredict_obj/Vrv64_core: $(RTL) sim/main.cpp | build
	$(VERILATOR) --cc --exe --build --trace -Wall --top-module rv64_core -GPREDICT_ENABLE=0 --Mdir build/nopredict_obj -CFLAGS '-std=c++17' $(RTL) $(abspath sim/main.cpp)
build/predictor_obj/Vrv64_static_predictor: rtl/rv64_static_predictor.sv sim/predictor_test.cpp | build
	$(VERILATOR) --cc --exe --build -Wall --top-module rv64_static_predictor --Mdir build/predictor_obj -CFLAGS '-std=c++17' rtl/rv64_static_predictor.sv $(abspath sim/predictor_test.cpp)
build/predictori_obj/Vrv64_static_predictor: rtl/rv64_static_predictor.sv sim/predictor_test.cpp | build
	$(VERILATOR) --cc --exe --build -Wall --top-module rv64_static_predictor -GEXTENSIONS=0 --Mdir build/predictori_obj -CFLAGS '-std=c++17 -DEXPECT_C=0' rtl/rv64_static_predictor.sv $(abspath sim/predictor_test.cpp)
build/predictfetch_obj/Vrv64_fetch: rtl/rv64_btb.sv rtl/rv64_bht.sv rtl/rv64_fetch.sv rtl/rv64_decompress.sv rtl/rv64_static_predictor.sv sim/predict_fetch_test.cpp sim/fetch_test.cpp | build
	$(VERILATOR) --cc --exe --build -Wall --top-module rv64_fetch --Mdir build/predictfetch_obj -CFLAGS '-std=c++17' rtl/rv64_btb.sv rtl/rv64_bht.sv rtl/rv64_fetch.sv rtl/rv64_decompress.sv rtl/rv64_static_predictor.sv $(abspath sim/predict_fetch_test.cpp)
test-predict: build/predictor_obj/Vrv64_static_predictor build/predictori_obj/Vrv64_static_predictor build/predictfetch_obj/Vrv64_fetch build/full_obj/Vrv64_core build/nopredict_obj/Vrv64_core
	./build/predictor_obj/Vrv64_static_predictor
	./build/predictori_obj/Vrv64_static_predictor
	./build/predictfetch_obj/Vrv64_fetch
	$(PYTHON) scripts/prediction_tests.py --cross '$(CROSS)'
build/noras_obj/Vrv64_core: $(RTL) sim/main.cpp | build
	$(VERILATOR) --cc --exe --build --trace -Wall --top-module rv64_core -GRAS_ENABLE=0 --Mdir build/noras_obj -CFLAGS '-std=c++17' $(RTL) $(abspath sim/main.cpp)
build/ras_obj/Vrv64_return_stack: rtl/rv64_return_stack.sv sim/return_stack_test.cpp | build
	$(VERILATOR) --cc --exe --build -Wall --top-module rv64_return_stack --Mdir build/ras_obj -CFLAGS '-std=c++17' rtl/rv64_return_stack.sv $(abspath sim/return_stack_test.cpp)
build/norasunit_obj/Vrv64_return_stack: rtl/rv64_return_stack.sv sim/return_stack_test.cpp | build
	$(VERILATOR) --cc --exe --build -Wall --top-module rv64_return_stack -GENABLED=0 --Mdir build/norasunit_obj -CFLAGS '-std=c++17 -DEXPECT_ENABLE=0' rtl/rv64_return_stack.sv $(abspath sim/return_stack_test.cpp)
build/rasfetch_obj/Vrv64_fetch: rtl/rv64_btb.sv rtl/rv64_bht.sv rtl/rv64_fetch.sv rtl/rv64_decompress.sv rtl/rv64_static_predictor.sv sim/ras_fetch_test.cpp sim/fetch_test.cpp | build
	$(VERILATOR) --cc --exe --build -Wall --top-module rv64_fetch --Mdir build/rasfetch_obj -CFLAGS '-std=c++17' rtl/rv64_btb.sv rtl/rv64_bht.sv rtl/rv64_fetch.sv rtl/rv64_decompress.sv rtl/rv64_static_predictor.sv $(abspath sim/ras_fetch_test.cpp)
test-ras: build/ras_obj/Vrv64_return_stack build/norasunit_obj/Vrv64_return_stack build/rasfetch_obj/Vrv64_fetch build/full_obj/Vrv64_core build/noras_obj/Vrv64_core
	./build/ras_obj/Vrv64_return_stack
	./build/norasunit_obj/Vrv64_return_stack
	./build/rasfetch_obj/Vrv64_fetch
	$(PYTHON) scripts/ras_tests.py --cross '$(CROSS)'
build/notlb_obj/Vrv64_core: $(RTL) sim/main.cpp | build
	$(VERILATOR) --cc --exe --build --trace -Wall --top-module rv64_core -GTLB_ENABLE=0 --Mdir build/notlb_obj -CFLAGS '-std=c++17' $(RTL) $(abspath sim/main.cpp)
build/tlb_obj/Vrv64_tlb: rtl/rv64_tlb.sv sim/tlb_test.cpp | build
	$(VERILATOR) --cc --exe --build -Wall --top-module rv64_tlb --Mdir build/tlb_obj -CFLAGS '-std=c++17' rtl/rv64_tlb.sv $(abspath sim/tlb_test.cpp)
build/mmu_obj/Vrv64_mmu: rtl/rv64_mmu.sv rtl/rv64_tlb.sv sim/mmu_test.cpp | build
	$(VERILATOR) --cc --exe --build -Wall --top-module rv64_mmu --Mdir build/mmu_obj -CFLAGS '-std=c++17' rtl/rv64_mmu.sv rtl/rv64_tlb.sv $(abspath sim/mmu_test.cpp)
test-tlb: build/tlb_obj/Vrv64_tlb build/mmu_obj/Vrv64_mmu build/full_obj/Vrv64_core build/notlb_obj/Vrv64_core
	./build/tlb_obj/Vrv64_tlb
	./build/mmu_obj/Vrv64_mmu
	$(PYTHON) scripts/tlb_tests.py --cross '$(CROSS)'
build/icache_obj/Vrv64_icache: rtl/rv64_icache.sv sim/icache_test.cpp | build
	$(VERILATOR) --cc --exe --build -Wall --top-module rv64_icache -GEARLY_RESTART=0 --Mdir build/icache_obj -CFLAGS '-std=c++17' rtl/rv64_icache.sv $(abspath sim/icache_test.cpp)
build/early_obj/Vrv64_icache: rtl/rv64_icache.sv sim/early_restart_test.cpp sim/icache_test.cpp | build
	$(VERILATOR) --cc --exe --build -Wall --top-module rv64_icache --Mdir build/early_obj -CFLAGS '-std=c++17' rtl/rv64_icache.sv $(abspath sim/early_restart_test.cpp)
test-early: build/early_obj/Vrv64_icache
	./build/early_obj/Vrv64_icache
build/fetch_obj/Vrv64_fetch: rtl/rv64_btb.sv rtl/rv64_bht.sv rtl/rv64_fetch.sv rtl/rv64_decompress.sv rtl/rv64_static_predictor.sv sim/fetch_test.cpp | build
	$(VERILATOR) --cc --exe --build -Wall --top-module rv64_fetch --Mdir build/fetch_obj -CFLAGS '-std=c++17' rtl/rv64_btb.sv rtl/rv64_bht.sv rtl/rv64_fetch.sv rtl/rv64_decompress.sv rtl/rv64_static_predictor.sv $(abspath sim/fetch_test.cpp)
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
test: test-queue test-btb test-gshare test-bht test-base test-full test-pipeline test-icache test-fetch test-early test-dcache test-data-early test-split test-predict test-ras test-tlb
test-fetch: build/fetch_obj/Vrv64_fetch build/full_obj/Vrv64_core build/nobuffer_obj/Vrv64_core
	./build/fetch_obj/Vrv64_fetch
	$(PYTHON) scripts/fetch_buffer_tests.py --cross '$(CROSS)'
test-icache: build/icache_obj/Vrv64_icache build/full_obj/Vrv64_core build/noicache_obj/Vrv64_core
	./build/icache_obj/Vrv64_icache
	$(PYTHON) scripts/icache_tests.py --cross '$(CROSS)'
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
test-mapped: build/noqueue_obj/Vrv64_core build/nobtb_obj/Vrv64_core build/bimodal_obj/Vrv64_core build/nobht_obj/Vrv64_core timing build/notlb_obj/Vrv64_core build/noras_obj/Vrv64_core build/nopredict_obj/Vrv64_core build/unsplit_obj/Vrv64_core build/nodataearly_obj/Vrv64_core build/nodcache_obj/Vrv64_core build/noicache_obj/Vrv64_core build/nobuffer_obj/Vrv64_core build/full_demo.bin build/full_demo_o0.bin build/machine_demo.bin
	$(YOSYS) -Q -T -p 'read_liberty -ignore_miss_func "$(LIB)"; proc; opt; write_verilog -noattr build/cell_models.v' > build/cell_models.log
	cp build/core_mapped.v build/gate_input.v
	$(VERILATOR) --cc --exe --build --trace --top-module rv64_core --Mdir build/mapped_obj -CFLAGS '-std=c++17' build/gate_input.v build/cell_models.v $(abspath sim/main.cpp)
	SIMULATOR=build/mapped_obj/Vrv64_core $(PYTHON) scripts/extension_tests.py --cross '$(CROSS)'
	SIMULATOR=build/mapped_obj/Vrv64_core $(PYTHON) scripts/privileged_tests.py --cross '$(CROSS)'
	SIMULATOR=build/mapped_obj/Vrv64_core $(PYTHON) scripts/pipeline_tests.py --cross '$(CROSS)'
	SIMULATOR=build/mapped_obj/Vrv64_core $(PYTHON) scripts/icache_tests.py --cross '$(CROSS)'
	SIMULATOR=build/mapped_obj/Vrv64_core $(PYTHON) scripts/fetch_buffer_tests.py --cross '$(CROSS)'
	SIMULATOR=build/mapped_obj/Vrv64_core $(PYTHON) scripts/dcache_tests.py --cross '$(CROSS)'
	SIMULATOR=build/mapped_obj/Vrv64_core $(PYTHON) scripts/dcache_early_tests.py --cross '$(CROSS)'
	SIMULATOR=build/mapped_obj/Vrv64_core $(PYTHON) scripts/split_memory_tests.py --cross '$(CROSS)'
	SIMULATOR=build/mapped_obj/Vrv64_core $(PYTHON) scripts/prediction_tests.py --cross '$(CROSS)'
	SIMULATOR=build/mapped_obj/Vrv64_core $(PYTHON) scripts/ras_tests.py --cross '$(CROSS)'
	SIMULATOR=build/mapped_obj/Vrv64_core $(PYTHON) scripts/tlb_tests.py --cross '$(CROSS)'
	SIMULATOR=build/mapped_obj/Vrv64_core $(PYTHON) scripts/bht_tests.py --cross '$(CROSS)'
	SIMULATOR=build/mapped_obj/Vrv64_core $(PYTHON) scripts/gshare_tests.py --cross '$(CROSS)'
	SIMULATOR=build/mapped_obj/Vrv64_core $(PYTHON) scripts/btb_tests.py --cross '$(CROSS)'
	SIMULATOR=build/mapped_obj/Vrv64_core $(PYTHON) scripts/fetch_queue_tests.py --cross '$(CROSS)'
	$(PYTHON) scripts/test_full_reference.py
test-alu: build/obj_dir/Vrv64_core
	$(PYTHON) scripts/alu_tests.py --cross '$(CROSS)'
test-rv64i: test-alu build/c_demo.bin build/c_demo_o0.bin
	$(PYTHON) scripts/rv64i_tests.py --cross '$(CROSS)'
sweep: build/obj_dir/Vrv64_core $(IMAGES)
	$(PYTHON) scripts/experiments.py
wave: sim
	surfer build/$(PROGRAM).vcd
diagrams: test-queue test-btb test-gshare test-bht test-pipeline test-icache test-fetch test-dcache test-split test-predict test-ras test-tlb
	$(PYTHON) scripts/pipeline_waveforms.py
	$(PYTHON) scripts/icache_waveforms.py
	$(PYTHON) scripts/fetch_buffer_waveforms.py
	$(PYTHON) scripts/dcache_waveforms.py
	$(PYTHON) scripts/split_memory_waveforms.py
	$(PYTHON) scripts/prediction_waveforms.py
	$(PYTHON) scripts/ras_waveforms.py
	$(PYTHON) scripts/tlb_waveforms.py
	$(PYTHON) scripts/bht_waveforms.py
	$(PYTHON) scripts/gshare_waveforms.py
	$(PYTHON) scripts/btb_waveforms.py
	$(PYTHON) scripts/fetch_queue_waveforms.py
	$(PYTHON) scripts/window_waveforms.py
	$(PYTHON) scripts/path_waveforms.py
	$(PYTHON) scripts/forward_waveforms.py
	$(PYTHON) scripts/issue_waveforms.py
	$(PYTHON) scripts/priority_waveforms.py
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

.PHONY: test-bht
build/nobht_obj/Vrv64_core: $(RTL) sim/main.cpp | build
	$(VERILATOR) --cc --exe --build --trace -Wall --top-module rv64_core -GBHT_ENABLE=0 --Mdir build/nobht_obj -CFLAGS '-std=c++17' $(RTL) $(abspath sim/main.cpp)
build/bht_obj/Vrv64_bht: rtl/rv64_bht.sv sim/bht_test.cpp | build
	$(VERILATOR) --cc --exe --build -Wall --top-module rv64_bht --Mdir build/bht_obj -CFLAGS '-std=c++17' rtl/rv64_bht.sv $(abspath sim/bht_test.cpp)
build/nobhtunit_obj/Vrv64_bht: rtl/rv64_bht.sv sim/bht_test.cpp | build
	$(VERILATOR) --cc --exe --build -Wall --top-module rv64_bht -GENABLED=0 --Mdir build/nobhtunit_obj -CFLAGS '-std=c++17 -DEXPECT_ENABLE=0' rtl/rv64_bht.sv $(abspath sim/bht_test.cpp)
test-bht: build/bht_obj/Vrv64_bht build/nobhtunit_obj/Vrv64_bht build/full_obj/Vrv64_core build/nobht_obj/Vrv64_core
	./build/bht_obj/Vrv64_bht
	./build/nobhtunit_obj/Vrv64_bht
	$(PYTHON) scripts/bht_tests.py --cross '$(CROSS)'

.PHONY: test-gshare
build/bimodal_obj/Vrv64_core: $(RTL) sim/main.cpp | build
	$(VERILATOR) --cc --exe --build --trace -Wall --top-module rv64_core -GGSHARE_ENABLE=0 --Mdir build/bimodal_obj -CFLAGS '-std=c++17' $(RTL) $(abspath sim/main.cpp)
build/bimodalunit_obj/Vrv64_bht: rtl/rv64_bht.sv sim/bht_test.cpp | build
	$(VERILATOR) --cc --exe --build -Wall --top-module rv64_bht -GGSHARE_ENABLE=0 --Mdir build/bimodalunit_obj -CFLAGS '-std=c++17 -DEXPECT_GSHARE=0' rtl/rv64_bht.sv $(abspath sim/bht_test.cpp)
build/gsharefetch_obj/Vrv64_fetch: rtl/rv64_btb.sv rtl/rv64_bht.sv rtl/rv64_fetch.sv rtl/rv64_decompress.sv rtl/rv64_static_predictor.sv sim/gshare_fetch_test.cpp sim/fetch_test.cpp | build
	$(VERILATOR) --cc --exe --build -Wall --top-module rv64_fetch --Mdir build/gsharefetch_obj -CFLAGS '-std=c++17' rtl/rv64_btb.sv rtl/rv64_bht.sv rtl/rv64_fetch.sv rtl/rv64_decompress.sv rtl/rv64_static_predictor.sv $(abspath sim/gshare_fetch_test.cpp)
test-gshare: build/bht_obj/Vrv64_bht build/nobhtunit_obj/Vrv64_bht build/bimodalunit_obj/Vrv64_bht build/gsharefetch_obj/Vrv64_fetch build/full_obj/Vrv64_core build/bimodal_obj/Vrv64_core
	./build/bht_obj/Vrv64_bht
	./build/nobhtunit_obj/Vrv64_bht
	./build/bimodalunit_obj/Vrv64_bht
	./build/gsharefetch_obj/Vrv64_fetch
	$(PYTHON) scripts/gshare_tests.py --cross '$(CROSS)'

.PHONY: test-btb
build/nobtb_obj/Vrv64_core: $(RTL) sim/main.cpp | build
	$(VERILATOR) --cc --exe --build --trace -Wall --top-module rv64_core -GBTB_ENABLE=0 --Mdir build/nobtb_obj -CFLAGS '-std=c++17' $(RTL) $(abspath sim/main.cpp)
build/btb_obj/Vrv64_btb: rtl/rv64_btb.sv sim/btb_test.cpp | build
	$(VERILATOR) --cc --exe --build -Wall --top-module rv64_btb --Mdir build/btb_obj -CFLAGS '-std=c++17' rtl/rv64_btb.sv $(abspath sim/btb_test.cpp)
build/nobtbunit_obj/Vrv64_btb: rtl/rv64_btb.sv sim/btb_test.cpp | build
	$(VERILATOR) --cc --exe --build -Wall --top-module rv64_btb -GENABLED=0 --Mdir build/nobtbunit_obj -CFLAGS '-std=c++17 -DEXPECT_ENABLE=0' rtl/rv64_btb.sv $(abspath sim/btb_test.cpp)
build/btbfetch_obj/Vrv64_fetch: rtl/rv64_btb.sv rtl/rv64_bht.sv rtl/rv64_fetch.sv rtl/rv64_decompress.sv rtl/rv64_static_predictor.sv sim/btb_fetch_test.cpp sim/fetch_test.cpp | build
	$(VERILATOR) --cc --exe --build -Wall --top-module rv64_fetch --Mdir build/btbfetch_obj -CFLAGS '-std=c++17' rtl/rv64_btb.sv rtl/rv64_bht.sv rtl/rv64_fetch.sv rtl/rv64_decompress.sv rtl/rv64_static_predictor.sv $(abspath sim/btb_fetch_test.cpp)
test-btb: build/btb_obj/Vrv64_btb build/nobtbunit_obj/Vrv64_btb build/btbfetch_obj/Vrv64_fetch build/full_obj/Vrv64_core build/nobtb_obj/Vrv64_core
	./build/btb_obj/Vrv64_btb
	./build/nobtbunit_obj/Vrv64_btb
	./build/btbfetch_obj/Vrv64_fetch
	$(PYTHON) scripts/btb_tests.py --cross '$(CROSS)'

.PHONY: test-queue
build/noqueue_obj/Vrv64_core: $(RTL) sim/main.cpp | build
	$(VERILATOR) --cc --exe --build --trace -Wall --top-module rv64_core -GFETCH_QUEUE_ENABLE=0 --Mdir build/noqueue_obj -CFLAGS '-std=c++17' $(RTL) $(abspath sim/main.cpp)
build/queue_obj/Vrv64_fetch_queue: rtl/rv64_fetch_queue.sv sim/fetch_queue_test.cpp | build
	$(VERILATOR) --cc --exe --build -Wall --top-module rv64_fetch_queue --Mdir build/queue_obj -CFLAGS '-std=c++17' rtl/rv64_fetch_queue.sv $(abspath sim/fetch_queue_test.cpp)
build/noqueueunit_obj/Vrv64_fetch_queue: rtl/rv64_fetch_queue.sv sim/fetch_queue_test.cpp | build
	$(VERILATOR) --cc --exe --build -Wall --top-module rv64_fetch_queue -GENABLED=0 --Mdir build/noqueueunit_obj -CFLAGS '-std=c++17 -DEXPECT_ENABLE=0' rtl/rv64_fetch_queue.sv $(abspath sim/fetch_queue_test.cpp)
test-queue: build/queue_obj/Vrv64_fetch_queue build/noqueueunit_obj/Vrv64_fetch_queue build/full_obj/Vrv64_core build/noqueue_obj/Vrv64_core
	./build/queue_obj/Vrv64_fetch_queue
	./build/noqueueunit_obj/Vrv64_fetch_queue
	$(PYTHON) scripts/fetch_queue_tests.py --cross '$(CROSS)'

build/nopipe_obj/Vrv64_core: $(RTL) sim/main.cpp | build
	$(VERILATOR) --cc --exe --build --trace -Wall --top-module rv64_core -GI_PIPELINE=0 --Mdir build/nopipe_obj -CFLAGS '-std=c++17' $(RTL) $(abspath sim/main.cpp)
.PHONY: test-ifetch
test: test-ifetch
build/pipefetch_obj/Vrv64_fetch: rtl/rv64_btb.sv rtl/rv64_bht.sv rtl/rv64_fetch.sv rtl/rv64_decompress.sv rtl/rv64_static_predictor.sv sim/fetch_test.cpp | build
	$(VERILATOR) --cc --exe --build -Wall --top-module rv64_fetch -GI_PIPELINE=1 --Mdir build/pipefetch_obj -CFLAGS '-std=c++17' rtl/rv64_btb.sv rtl/rv64_bht.sv rtl/rv64_fetch.sv rtl/rv64_decompress.sv rtl/rv64_static_predictor.sv $(abspath sim/fetch_test.cpp)
test-ifetch: build/pipefetch_obj/Vrv64_fetch
	./build/pipefetch_obj/Vrv64_fetch

build/nowindow_obj/Vrv64_core: $(RTL) sim/main.cpp | build
	$(VERILATOR) --cc --exe --build --trace -Wall --top-module rv64_core -GFETCH_WINDOW=0 --Mdir build/nowindow_obj -CFLAGS '-std=c++17' $(RTL) $(abspath sim/main.cpp)
.PHONY: test-window
test: test-window
build/window_obj/Vrv64_fetch_window: $(RTL) sim/fetch_window_test.cpp | build
	$(VERILATOR) --cc --exe --build -Wall --top-module rv64_fetch_window --Mdir build/window_obj -CFLAGS '-std=c++17' $(RTL) $(abspath sim/fetch_window_test.cpp)
test-window: build/window_obj/Vrv64_fetch_window build/full_obj/Vrv64_core
	./build/window_obj/Vrv64_fetch_window
	./build/pipememory_obj/Vrv64_memory_system
	$(PYTHON) scripts/window_tests.py --cross '$(CROSS)'
build/pipememory_obj/Vrv64_memory_system: $(RTL) sim/memory_system_test.cpp | build
	$(VERILATOR) --cc --exe --build -Wall --top-module rv64_memory_system -GI_PIPELINE=1 --Mdir build/pipememory_obj -CFLAGS '-std=c++17' $(RTL) $(abspath sim/memory_system_test.cpp)
test-window: build/pipememory_obj/Vrv64_memory_system
diagrams: test-window

build/nopath_obj/Vrv64_core: $(RTL) sim/main.cpp | build
	$(VERILATOR) --cc --exe --build --trace -Wall --top-module rv64_core -GPREFETCH_PATH=0 --Mdir build/nopath_obj -CFLAGS '-std=c++17' $(RTL) $(abspath sim/main.cpp)
.PHONY: test-path
test: test-path
build/path_obj/Vrv64_prefetch_predictor: rtl/rv64_prefetch_predictor.sv rtl/rv64_btb.sv rtl/rv64_bht.sv sim/prefetch_predictor_test.cpp | build
	$(VERILATOR) --cc --exe --build -Wall --top-module rv64_prefetch_predictor --Mdir build/path_obj -CFLAGS '-std=c++17' rtl/rv64_prefetch_predictor.sv rtl/rv64_btb.sv rtl/rv64_bht.sv $(abspath sim/prefetch_predictor_test.cpp)
build/nopathunit_obj/Vrv64_prefetch_predictor: rtl/rv64_prefetch_predictor.sv rtl/rv64_btb.sv rtl/rv64_bht.sv sim/prefetch_predictor_test.cpp | build
	$(VERILATOR) --cc --exe --build -Wall --top-module rv64_prefetch_predictor -GENABLED=0 --Mdir build/nopathunit_obj -CFLAGS '-std=c++17 -DEXPECT_ENABLE=0' rtl/rv64_prefetch_predictor.sv rtl/rv64_btb.sv rtl/rv64_bht.sv $(abspath sim/prefetch_predictor_test.cpp)
test-path: build/full_obj/Vrv64_core build/nopath_obj/Vrv64_core build/path_obj/Vrv64_prefetch_predictor build/nopathunit_obj/Vrv64_prefetch_predictor
	./build/path_obj/Vrv64_prefetch_predictor
	./build/nopathunit_obj/Vrv64_prefetch_predictor
	./build/pathwindow_obj/Vrv64_fetch_window
	$(PYTHON) scripts/path_tests.py --cross '$(CROSS)'
build/pathwindow_obj/Vrv64_fetch_window: $(RTL) sim/path_window_test.cpp | build
	$(VERILATOR) --cc --exe --build -Wall --top-module rv64_fetch_window --Mdir build/pathwindow_obj -CFLAGS '-std=c++17' $(RTL) $(abspath sim/path_window_test.cpp)
test-path: build/pathwindow_obj/Vrv64_fetch_window

diagrams: test-path

# Component ablation: later optimizations remain enabled.
build/noforward_obj/Vrv64_core: $(RTL) sim/main.cpp | build
	$(VERILATOR) --cc --exe --build --trace -Wall --top-module rv64_core -GWINDOW_FORWARD=0 --Mdir build/noforward_obj -CFLAGS '-std=c++17' $(RTL) $(abspath sim/main.cpp)
.PHONY: test-forward
test: test-forward
build/forward_obj/Vrv64_fetch_window: $(RTL) sim/window_forward_test.cpp | build
	$(VERILATOR) --cc --exe --build -Wall --top-module rv64_fetch_window --Mdir build/forward_obj -CFLAGS '-std=c++17' $(RTL) $(abspath sim/window_forward_test.cpp)
build/noforwardunit_obj/Vrv64_fetch_window: $(RTL) sim/window_forward_test.cpp | build
	$(VERILATOR) --cc --exe --build -Wall --top-module rv64_fetch_window -GWINDOW_FORWARD=0 --Mdir build/noforwardunit_obj -CFLAGS '-std=c++17 -DEXPECT_FORWARD=0' $(RTL) $(abspath sim/window_forward_test.cpp)
build/noforwardmodel_obj/Vrv64_fetch_window: $(RTL) sim/fetch_window_test.cpp | build
	$(VERILATOR) --cc --exe --build -Wall --top-module rv64_fetch_window -GWINDOW_FORWARD=0 --Mdir build/noforwardmodel_obj -CFLAGS '-std=c++17' $(RTL) $(abspath sim/fetch_window_test.cpp)
test-forward: build/forward_obj/Vrv64_fetch_window build/noforwardunit_obj/Vrv64_fetch_window build/noforwardmodel_obj/Vrv64_fetch_window
	./build/forward_obj/Vrv64_fetch_window
	./build/noforwardunit_obj/Vrv64_fetch_window
	./build/noforwardmodel_obj/Vrv64_fetch_window
	$(PYTHON) scripts/forward_tests.py
test-forward: test-window test-path

diagrams: test-forward build/noforward_obj/Vrv64_core

# Component ablation of new-demand issue; matched-demand priority remains enabled.
build/noissue_obj/Vrv64_core: $(RTL) sim/main.cpp | build
	$(VERILATOR) --cc --exe --build --trace -Wall --top-module rv64_core -GDEMAND_ISSUE=0 --Mdir build/noissue_obj -CFLAGS '-std=c++17' $(RTL) $(abspath sim/main.cpp)
.PHONY: test-issue
test: test-issue
build/issue_obj/Vrv64_fetch_window: $(RTL) sim/demand_issue_test.cpp | build
	$(VERILATOR) --cc --exe --build -Wall --top-module rv64_fetch_window --Mdir build/issue_obj -CFLAGS '-std=c++17' $(RTL) $(abspath sim/demand_issue_test.cpp)
build/noissueunit_obj/Vrv64_fetch_window: $(RTL) sim/demand_issue_test.cpp | build
	$(VERILATOR) --cc --exe --build -Wall --top-module rv64_fetch_window -GDEMAND_ISSUE=0 --Mdir build/noissueunit_obj -CFLAGS '-std=c++17 -DEXPECT_ISSUE=0' $(RTL) $(abspath sim/demand_issue_test.cpp)
build/noissuemodel_obj/Vrv64_fetch_window: $(RTL) sim/fetch_window_test.cpp | build
	$(VERILATOR) --cc --exe --build -Wall --top-module rv64_fetch_window -GDEMAND_ISSUE=0 --Mdir build/noissuemodel_obj -CFLAGS '-std=c++17' $(RTL) $(abspath sim/fetch_window_test.cpp)
test-issue: build/issue_obj/Vrv64_fetch_window build/noissueunit_obj/Vrv64_fetch_window build/noissuemodel_obj/Vrv64_fetch_window
	./build/issue_obj/Vrv64_fetch_window
	./build/noissueunit_obj/Vrv64_fetch_window
	./build/noissuemodel_obj/Vrv64_fetch_window
	$(PYTHON) scripts/issue_tests.py

test-issue: test-forward

diagrams: test-issue build/noissue_obj/Vrv64_core

# Disable only matched-demand selection to restore v20.
build/nopriority_obj/Vrv64_core: $(RTL) sim/main.cpp | build
	$(VERILATOR) --cc --exe --build --trace -Wall --top-module rv64_core -GDEMAND_PRIORITY=0 --Mdir build/nopriority_obj -CFLAGS '-std=c++17' $(RTL) $(abspath sim/main.cpp)
.PHONY: test-priority
test: test-priority
build/priority_obj/Vrv64_fetch_window: $(RTL) sim/demand_priority_test.cpp | build
	$(VERILATOR) --cc --exe --build -Wall --top-module rv64_fetch_window --Mdir build/priority_obj -CFLAGS '-std=c++17' $(RTL) $(abspath sim/demand_priority_test.cpp)
build/nopriorityunit_obj/Vrv64_fetch_window: $(RTL) sim/demand_priority_test.cpp | build
	$(VERILATOR) --cc --exe --build -Wall --top-module rv64_fetch_window -GDEMAND_PRIORITY=0 --Mdir build/nopriorityunit_obj -CFLAGS '-std=c++17 -DEXPECT_PRIORITY=0' $(RTL) $(abspath sim/demand_priority_test.cpp)
build/noprioritymodel_obj/Vrv64_fetch_window: $(RTL) sim/fetch_window_test.cpp | build
	$(VERILATOR) --cc --exe --build -Wall --top-module rv64_fetch_window -GDEMAND_PRIORITY=0 --Mdir build/noprioritymodel_obj -CFLAGS '-std=c++17' $(RTL) $(abspath sim/fetch_window_test.cpp)
test-priority: build/priority_obj/Vrv64_fetch_window build/nopriorityunit_obj/Vrv64_fetch_window build/noprioritymodel_obj/Vrv64_fetch_window
	./build/priority_obj/Vrv64_fetch_window
	./build/nopriorityunit_obj/Vrv64_fetch_window
	./build/noprioritymodel_obj/Vrv64_fetch_window
	$(PYTHON) scripts/priority_tests.py --cross '$(CROSS)'

test-priority: test-issue build/nopriority_obj/Vrv64_core build/c_demo.bin

diagrams: test-priority
