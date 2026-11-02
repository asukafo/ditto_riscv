# Repository entry point; each hardware version owns its build directory.
VERSION ?= v15_fetch_queue
PYTHON ?= python3
BENCHMARK_ARGS ?=
VERSIONS := v1_multicycle v2_single_issue v3_icache v4_fetch_buffer v5_early_restart v6_dcache v7_dcache_early v8_split_memory v9_static_predict v10_return_stack v11_tlb v12_dynamic_predict v13_gshare v14_btb v15_fetch_queue
VERSION_DIR := versions/$(VERSION)

ifeq ($(filter $(VERSION),$(VERSIONS)),)
$(error Unknown VERSION '$(VERSION)'; choose one of: $(VERSIONS))
endif

.DEFAULT_GOAL := help
FORWARDED := tools lint test test-base test-full test-pipeline test-icache test-fetch test-early test-dcache test-data-early test-split test-predict test-ras test-tlb test-bht test-gshare test-btb test-queue test-mapped test-alu test-rv64i sim diff wave sweep diagrams synth timing clean
.PHONY: help versions check compare benchmark $(FORWARDED)

help:
	@echo 'ditto_riscv — selected version: $(VERSION)'
	@echo 'make lint / test / diff PROGRAM=full_demo / timing / diagrams'
	@echo 'make test VERSION=v1_multicycle    # frozen baseline'
	@echo 'make check                       # layout, links, frozen files, result archives'
	@echo 'make compare [BENCHMARK_ARGS="--run-id my-experiment"]'
	@echo 'make versions                    # available architectures'
	@echo 'Build outputs: $(VERSION_DIR)/build/; clean affects only the selected version.'

versions:
	@echo 'v1_multicycle   frozen multicycle baseline (8adc22c)'
	@echo 'v2_single_issue   frozen single-issue F/X/W pipeline'
	@echo 'v3_icache   frozen physical instruction cache baseline'
	@echo 'v4_fetch_buffer   frozen instruction cache with halfword reuse'
	@echo 'v5_early_restart   frozen critical-word-first refill and early restart'
	@echo 'v6_dcache   frozen write-through physical data cache'
	@echo 'v7_dcache_early   frozen critical-word-first data cache'
	@echo 'v8_split_memory   frozen independent I/D translation and cache paths'
	@echo 'v9_static_predict   frozen static branch and direct jump prediction'
	@echo 'v10_return_stack   frozen committed return-address stack'
	@echo 'v11_tlb   frozen independent I/D translation caches'

	@echo 'v12_dynamic_predict   frozen bimodal conditional branch prediction'

	@echo 'v13_gshare   frozen committed-history gshare'

	@echo 'v14_btb   frozen request-time target prediction'

	@echo 'v15_fetch_queue   four-entry complete-instruction queue (default)'

$(FORWARDED):
	$(MAKE) -C "$(VERSION_DIR)" $@

check:
	$(PYTHON) tools/check_repo.py

compare:
	$(PYTHON) tools/benchmark.py $(BENCHMARK_ARGS)

benchmark: compare
