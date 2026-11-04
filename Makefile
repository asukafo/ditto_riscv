# Repository entry point; each hardware version owns its build directory.
VERSION ?= v37_onehot_tlb
PYTHON ?= python3
BENCHMARK_ARGS ?=
VERSIONS := v1_multicycle v2_single_issue v3_icache v4_fetch_buffer v5_early_restart v6_dcache v7_dcache_early v8_split_memory v9_static_predict v10_return_stack v11_tlb v12_dynamic_predict v13_gshare v14_btb v15_fetch_queue v16_ifetch_pipeline v17_fetch_window v18_btb_window v19_window_forward v20_demand_issue v21_demand_priority v22_hit_under_refill v23_fill_forward v24_dual_alu v25_wide_frontend v26_second_branch v27_integer_pair v28_data_turnover v29_ifill_turnover v30_window_cursor v31_equal_branch v32_data_under_refill v33_onehot_arbiter v34_retire_amo v35_prefetch_redirect v36_walker_response v37_onehot_tlb v38_page_cursor v39_compact_forecast v40_store_trace
VERSION_DIR := versions/$(VERSION)

ifeq ($(filter $(VERSION),$(VERSIONS)),)
$(error Unknown VERSION '$(VERSION)'; choose one of: $(VERSIONS))
endif

.DEFAULT_GOAL := help
FORWARDED := tools lint test test-base test-full test-pipeline test-icache test-fetch test-early test-dcache test-data-early test-split test-predict test-ras test-tlb test-bht test-gshare test-btb test-queue test-ifetch test-window test-path test-forward test-issue test-priority test-under test-fill test-dual test-wide test-integer-pair test-data-turnover test-ifill-turnover test-equal-branch test-data-under-refill test-mapped test-alu test-rv64i sim diff wave sweep diagrams synth timing clean
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

	@echo 'v15_fetch_queue   frozen complete-instruction queue'

	@echo 'v16_ifetch_pipeline   frozen single-outstanding hit turnover'
	@echo 'v17_fetch_window   frozen sequential request window'

	@echo 'v18_btb_window   frozen BTB/gshare/RAS-guided request window'

	@echo 'v19_window_forward   frozen demand-response forwarding in request window'

	@echo 'v20_demand_issue   frozen same-cycle new-demand issue'

	@echo 'v21_demand_priority   frozen matched-demand issue priority'

	@echo 'v22_hit_under_refill   frozen cached hits during background refill'

	@echo 'v23_fill_forward   frozen refill-half forwarding, one-IPC warm baseline'
	@echo 'v24_dual_alu   frozen conservative dual ALU issue and ordered dual retirement'

	@echo 'v25_wide_frontend   two-packet fetch, six-entry dual-port queue, sustained warm IPC > 1'

	@echo 'v26_second_branch   second-slot direct branch prediction'

	@echo 'v27_integer_pair     expanded RV64I dual issue'

	@echo 'v28_data_turnover    execute-stage data launch and D-cache refill turnover'
	@echo 'v29_ifill_turnover   I-cache refill turnover'

	@echo 'v30_window_cursor    page-offset lookahead for allocated fetch slots'

	@echo 'v31_equal_branch     decode-proven same-register branch direction'

	@echo 'v32_data_under_refill experimental D-cache load overlap'

	@echo 'v33_onehot_arbiter   parallel one-hot physical arbitration'
	@echo 'v34_retire_amo       optimized atomic retirement data'
	@echo 'v35_prefetch_redirect page-local prefetch redirect'
	@echo 'v36_walker_response  split page-walker response path'
	@echo 'v37_onehot_tlb       parallel TLB lookup and replacement (default)'
	@echo 'v38_page_cursor      page-local speculative fetch cursor'
	@echo 'v39_compact_forecast page-local per-slot forecasts'
	@echo 'v40_store_trace      load result reuse in retirement'

$(FORWARDED):
	$(MAKE) -C "$(VERSION_DIR)" $@

check:
	$(PYTHON) tools/check_repo.py

compare:
	$(PYTHON) tools/ifetch_experiments.py $(BENCHMARK_ARGS)

benchmark: compare
