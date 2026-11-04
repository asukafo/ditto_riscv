#include "Vrv64_core.h"
#include "verilated.h"
#include "verilated_vcd_c.h"
#include <algorithm>
#include <cstdint>
#include <fstream>
#include <iostream>
#include <iterator>
#include <memory>
#include <map>
#include <sstream>
#include <stdexcept>
#include <string>
#include <vector>

int main(int argc, char** argv) {
    try {
        if (argc < 3) throw std::runtime_error("usage: sim image.bin latency [wave.vcd|-] [request_gap] [trace.jsonl] [irq_events.txt|-]");
        const int latency = std::stoi(argv[2]);
        const unsigned gap = argc > 4 ? unsigned(std::stoul(argv[4])) : 0;
        if (latency < 1 || latency > 10000 || gap > 10000) throw std::runtime_error("invalid latency/gap");
        std::ifstream file(argv[1], std::ios::binary);
        if (!file) throw std::runtime_error("cannot open image");
        std::vector<uint8_t> image((std::istreambuf_iterator<char>(file)), {});
        std::vector<uint8_t> ram(65536, 0);
        if (image.size() > ram.size()) throw std::runtime_error("image exceeds RAM");
        std::copy(image.begin(), image.end(), ram.begin());
        VerilatedContext context;
        context.commandArgs(argc, argv);
        context.traceEverOn(true);
        Vrv64_core top{&context};
        std::ofstream trace;
        const std::string trace_path=argc > 5 ? argv[5] : "";
        if (!trace_path.empty()) {
            trace.open(trace_path);
            if (!trace) throw std::runtime_error("cannot open commit trace");
        }
        std::unique_ptr<VerilatedVcdC> wave;
        if (argc > 3 && std::string(argv[3]) != "-") {
            wave = std::make_unique<VerilatedVcdC>();
            top.trace(wave.get(), 8); wave->open(argv[3]);
        }
        auto evaluate = [&](int clk) {
            top.clk = clk; top.eval();
            if (wave) wave->dump(context.time());
            context.timeInc(5);
        };
        top.reset=1; top.req_ready=0; top.rsp_valid=0;
        top.irq_pending=0; top.time_value=0; top.reservation_invalidate=0;
        top.rsp_error=0; top.rsp_rdata=0;
        evaluate(0); evaluate(1); evaluate(0);
        top.reset=0;
        const bool extended=top.extended_mode;
        if (trace.is_open() && extended) trace << "{\"kind\":\"config\",\"extended\":1,\"host_traps\":" << unsigned(top.host_traps_enabled) << "}\n";
        std::map<uint64_t,uint64_t> events;
        if (argc>6 && std::string(argv[6])!="-") {
            std::ifstream event_file(argv[6]);
            if (!event_file) throw std::runtime_error("cannot open IRQ event file");
            std::string line;
            while (std::getline(event_file,line)) {
                if (line.empty() || line[0]=='#') continue;
                std::istringstream input(line);
                std::string cycle,mask;
                if (!(input>>cycle>>mask)) throw std::runtime_error("IRQ event expects cycle mask");
                events[std::stoull(cycle,nullptr,0)]=std::stoull(mask,nullptr,0);
            }
        }
        uint64_t external_irq=0,last_irq=~uint64_t(0),mtimecmp=~uint64_t(0);
        bool last_invalidate=false;
        uint32_t msip=0;
        bool pending=false, error=false, host_exit=false;
        bool mailbox_pending=false;
        uint64_t exit_status=0;
        uint64_t response=0, requests=0, reads=0, writes=0;
        uint64_t icache_hits=0,icache_misses=0,icache_refills=0,icache_wait=0,icache_bypasses=0,icache_invalidations=0;
        uint64_t frontend_starved=0,data_fetch_contention=0,fetch_data_contention=0,discarded_fetches=0;
        uint64_t fetch_buffer_reuses=0,fetch_buffer_flushes=0;
        uint64_t dcache_hits=0,dcache_misses=0,dcache_refills=0,dcache_wait=0,dcache_writes=0,dcache_bypasses=0;
        uint64_t instruction_hits_during_data_fill=0,data_hits_during_instruction_fill=0;
        uint64_t control_resolved=0,conditional_branches=0,direct_jumps=0,indirect_jumps=0,control_misses=0,predicted_redirects=0,conditional_misses=0,direct_misses=0,indirect_misses=0;
        uint64_t refill_hits=0,fill_hits=0,wide_pairs=0;
        uint64_t path_queries=0,path_redirects=0,path_rejects=0,path_page_blocks=0;
        uint64_t window_peak=0,window_hits=0,window_drops=0;
        uint64_t fq_pushes=0,fq_pops=0,fq_bypasses=0,fq_full_cycles=0,fq_flushes=0,fq_flushed_packets=0,fq_peak=0,fq_fill_while_x_busy=0;
        uint64_t btb_lookups=0,btb_hits=0,btb_trains=0,btb_rejects=0,btb_predictions=0,btb_misses=0;
        uint64_t bht_trains=0,bht_taken=0,bht_predictions=0,bht_misses=0;
        uint64_t ras_predictions=0,ras_misses=0,ras_pushes=0,ras_pops=0,ras_overflows=0,ras_underflows=0;
        uint64_t itlb_hits=0,itlb_misses=0,itlb_fills=0,dtlb_hits=0,dtlb_misses=0,dtlb_fills=0,i_walk_reads=0,d_walk_reads=0,tlb_invalidations=0;
        unsigned locked_requests=0;
        int remaining=0;
        uint64_t snapshot_addr=0, snapshot_data=0;
        bool was_blocked=false, snapshot_write=false, snapshot_store_check=false;
        unsigned snapshot_size=0;
        for (uint64_t tick=0; tick<1000000 && !top.halted && !host_exit; ++tick) {
            top.time_value=tick+1;
            if (events.count(tick+1)) external_irq=events[tick+1];
            top.irq_pending=(external_irq&0xaaa) | (msip ? 8u : 0u) | (tick+1>=mtimecmp ? 128u : 0u);
            top.reservation_invalidate=unsigned(external_irq>>63);
            if (trace.is_open() && extended && (top.irq_pending!=last_irq || bool(top.reservation_invalidate)!=last_invalidate))
                trace << "{\"kind\":\"input\",\"cycle\":" << tick+1 << ",\"irq\":" << top.irq_pending
                      << ",\"invalidate\":" << unsigned(top.reservation_invalidate) << "}\n";
            last_irq=top.irq_pending;
            last_invalidate=top.reservation_invalidate;
            top.req_ready=!pending && (gap==0 || tick % (gap+1)==0);
            top.rsp_valid=pending && remaining==0;
            top.rsp_rdata=response; top.rsp_error=error;
            evaluate(0);
            dcache_hits+=top.dcache_hit_event;dcache_misses+=top.dcache_miss_event;
            dcache_refills+=top.dcache_refill_event;dcache_wait+=top.dcache_miss_wait;
            dcache_writes+=top.dcache_write_event;dcache_bypasses+=top.dcache_bypass_event;
            instruction_hits_during_data_fill+=top.icache_hit_during_data_fill;
            data_hits_during_instruction_fill+=top.dcache_hit_during_instruction_fill;
            control_resolved+=top.control_resolve_event;conditional_branches+=top.conditional_resolve_event;
            direct_jumps+=top.direct_jump_resolve_event;indirect_jumps+=top.indirect_jump_resolve_event;
            control_misses+=top.control_miss_event;predicted_redirects+=top.predicted_redirect_event;
            conditional_misses+=top.control_miss_event && top.conditional_resolve_event;
            direct_misses+=top.control_miss_event && top.direct_jump_resolve_event;
            indirect_misses+=top.control_miss_event && top.indirect_jump_resolve_event;
            wide_pairs+=top.wide_decode_pair_event;fill_hits+=top.icache_fill_hit_event;refill_hits+=top.icache_refill_hit_event;
            path_queries+=top.prefetch_path_query_event;path_redirects+=top.prefetch_path_redirect_event;
            path_rejects+=top.prefetch_path_reject_event;path_page_blocks+=top.prefetch_path_page_block_event;
            if(top.ifetch_window_pending>window_peak)window_peak=top.ifetch_window_pending;
            window_hits+=top.ifetch_window_hit_event;window_drops+=top.ifetch_window_drop_event;
            fq_pushes+=top.fetch_queue_push_event;fq_pops+=top.fetch_queue_pop_event;fq_bypasses+=top.fetch_queue_bypass_event;
            fq_full_cycles+=top.fetch_queue_full_stall;fq_flushes+=top.fetch_queue_flush_event;
            if(top.fetch_queue_flush_event)fq_flushed_packets+=top.fetch_queue_occupancy;
            if(top.fetch_queue_occupancy>fq_peak)fq_peak=top.fetch_queue_occupancy;
            fq_fill_while_x_busy+=top.fetch_queue_fill_while_x_busy;
            btb_lookups+=top.btb_lookup_event;btb_hits+=top.btb_hit_event;btb_trains+=top.btb_train_event;
            btb_rejects+=top.btb_reject_event;btb_predictions+=top.btb_prediction_event;btb_misses+=top.btb_miss_event;
            bht_trains+=top.bht_train_event;bht_taken+=top.bht_taken_event;
            bht_predictions+=top.bht_prediction_event;bht_misses+=top.bht_miss_event;
            ras_predictions+=top.ras_prediction_event;ras_misses+=top.ras_miss_event;
            ras_pushes+=top.ras_push_event;ras_pops+=top.ras_pop_event;
            ras_overflows+=top.ras_overflow_event;ras_underflows+=top.ras_underflow_event;
            itlb_hits+=top.itlb_hit_event;itlb_misses+=top.itlb_miss_event;itlb_fills+=top.itlb_fill_event;
            dtlb_hits+=top.dtlb_hit_event;dtlb_misses+=top.dtlb_miss_event;dtlb_fills+=top.dtlb_fill_event;
            i_walk_reads+=top.i_walk_event;d_walk_reads+=top.d_walk_event;tlb_invalidations+=top.tlb_invalidate_event;
            icache_hits+=top.icache_hit_event;
            icache_misses+=top.icache_miss_event;
            icache_refills+=top.icache_refill_event;
            icache_wait+=top.icache_miss_wait;
            icache_bypasses+=top.icache_bypass_event;
            icache_invalidations+=top.icache_invalidate_event;
            frontend_starved+=top.frontend_starved;
            data_fetch_contention+=top.data_blocked_by_fetch;
            fetch_data_contention+=top.fetch_blocked_by_data;
            discarded_fetches+=top.fetch_discard_event;
            fetch_buffer_reuses+=top.fetch_buffer_reuse_event;
            fetch_buffer_flushes+=top.fetch_buffer_flush_event;
            if (was_blocked && (!top.req_valid || top.req_addr!=snapshot_addr ||
                top.req_write!=snapshot_write || top.req_wdata!=snapshot_data || top.req_size!=snapshot_size ||
                bool(top.req_store_check)!=snapshot_store_check))
                throw std::runtime_error("request changed under backpressure");
            was_blocked=top.req_valid && !top.req_ready;
            snapshot_addr=top.req_addr; snapshot_data=top.req_wdata; snapshot_write=top.req_write;
            snapshot_size=top.req_size;
            snapshot_store_check=top.req_store_check;
            const bool accept=top.req_valid && top.req_ready;
            const bool consume=top.rsp_valid && top.rsp_ready;
            const uint64_t addr=top.req_addr, data=top.req_wdata;
            const bool write=top.req_write;
            const bool locked=top.bus_lock;
            const bool check_store=top.req_store_check;
            const unsigned bytes=1u << top.req_size;
            evaluate(1);
            if (accept && locked) ++locked_requests;
            if (extended && top.trap_valid) locked_requests=0;
            if (top.commit_valid && top.commit_mem_atomic) {
                const unsigned expected=top.commit_mem_amo==2 ? 1 : top.commit_mem_amo==3 ? (top.commit_mem_write ? 2 : 1) : 2;
                if (locked_requests!=expected) throw std::runtime_error("atomic transaction lost bus lock");
                locked_requests=0;
            }
            if (trace.is_open() && extended && top.trap_valid)
                trace << "{\"kind\":\"trap\",\"cycle\":" << tick+1 << ",\"pc\":" << top.trap_pc
                      << ",\"cause\":" << top.trap_cause << ",\"value\":" << top.trap_value
                      << ",\"target\":" << top.trap_target << ",\"privilege\":" << unsigned(top.current_privilege) << "}\n";
            // The simulation exit mailbox is observed only after its SD commits.
            if (top.commit_valid && top.commit_mem_valid && mailbox_pending) {
                if (top.commit_mem_write && !top.commit_mem_atomic && top.commit_mem_size==3) {
                    host_exit=true; exit_status=top.commit_mem_data;
                }
                mailbox_pending=false;
            }
            // Sample AFTER the rising edge so this record describes this edge's commit.
            if (trace.is_open() && top.commit_valid) {
                trace << "{\"kind\":\"commit\",\"cycle\":" << tick+1
                      << ",\"retire_slot\":0,\"pc\":" << top.commit_pc << ",\"insn\":" << top.commit_insn
                      << ",\"next_pc\":" << top.commit_next_pc
                      << ",\"rd_wen\":" << unsigned(top.commit_rd_wen)
                      << ",\"rd\":" << unsigned(top.commit_rd) << ",\"wdata\":" << top.commit_wdata
                      << ",\"mem_valid\":" << unsigned(top.commit_mem_valid)
                      << ",\"mem_write\":" << unsigned(top.commit_mem_write)
                      << ",\"mem_addr\":" << top.commit_mem_addr << ",\"mem_data\":" << top.commit_mem_data
                      << ",\"mem_size\":" << unsigned(top.commit_mem_size)
                      << ",\"bytes\":" << unsigned(top.commit_bytes) << ",\"privilege\":" << unsigned(top.commit_privilege)
                      << ",\"mem_atomic\":" << unsigned(top.commit_mem_atomic) << ",\"mem_amo\":" << unsigned(top.commit_mem_amo)
                      << "}\n";
            }
            if (trace.is_open() && top.commit2_valid) {
                trace << "{\"kind\":\"commit\",\"cycle\":" << tick+1
                      << ",\"retire_slot\":1,\"pc\":" << top.commit2_pc << ",\"insn\":" << top.commit2_insn
                      << ",\"next_pc\":" << top.commit2_next_pc << ",\"rd_wen\":" << unsigned(top.commit2_rd_wen)
                      << ",\"rd\":" << unsigned(top.commit2_rd) << ",\"wdata\":" << top.commit2_wdata
                      << ",\"mem_valid\":0,\"mem_write\":0,\"mem_addr\":0,\"mem_data\":0,\"mem_size\":0"
                      << ",\"bytes\":" << unsigned(top.commit2_bytes) << ",\"privilege\":" << unsigned(top.commit2_privilege)
                      << ",\"mem_atomic\":0,\"mem_amo\":0}\n";
            }
            if (consume) pending=false;
            if (accept) {
                if (pending) throw std::runtime_error("more than one outstanding request");
                ++requests; if (write) ++writes; else ++reads;
                const bool clint=extended && ((addr==0x02000000 && bytes<=4) || ((addr==0x02004000 || addr==0x0200bff8) && bytes<=8));
                error=addr > ram.size()-bytes && !clint;
                if (clint && (locked || check_store)) error=true;
                response=0;
                if (!error && clint) {
                    const uint64_t mask=bytes==8 ? ~uint64_t(0) : (uint64_t(1)<<(8*bytes))-1;
                    if (write) {
                        if (addr==0x02000000) msip=uint32_t(data)&1;
                        else if (addr==0x02004000) mtimecmp=(mtimecmp&~mask)|(data&mask);
                        else error=true; // mtime is driven by simulation time
                    } else {
                        response=(addr==0x02000000 ? msip : addr==0x02004000 ? mtimecmp : tick+1)&mask;
                        if (trace.is_open()) trace << "{\"kind\":\"mmio_read\",\"cycle\":" << tick+1 << ",\"address\":" << addr << ",\"size\":" << bytes << "}\n";
                    }
                } else if (!error) for (unsigned j=0; j<bytes; ++j) {
                    if (write) ram[size_t(addr)+j]=uint8_t(data>>(8*j));
                    else response |= uint64_t(ram[size_t(addr)+j])<<(8*j);
                }
                if (!error && write && addr==0xfff0 && bytes==8) mailbox_pending=true;
                pending=true; remaining=latency-1;
            } else if (pending && remaining>0) --remaining;
        }
        top.final(); if (wave) wave->close();
        if (!top.halted && !host_exit) throw std::runtime_error("simulation timeout");
        if (trace.is_open()) {
            trace << "{\"kind\":\"halt\",\"fault\":" << unsigned(top.fault)
                  << ",\"instret\":" << top.instret << ",\"cycles\":" << top.cycles
                  << ",\"trap_pc\":" << top.trap_pc << ",\"trap_cause\":" << top.trap_cause
                  << ",\"trap_value\":" << top.trap_value << ",\"exit_status\":" << exit_status << "}\n";
            trace.close();
            if (!trace) throw std::runtime_error("cannot write commit trace");
            std::ofstream snapshot(trace_path + ".ram", std::ios::binary);
            snapshot.write(reinterpret_cast<const char*>(ram.data()), std::streamsize(ram.size()));
            snapshot.close();
            if (!snapshot) throw std::runtime_error("cannot write RAM snapshot");
        }
        uint64_t result=0;
        for (unsigned j=0; j<8; ++j) result |= uint64_t(ram[0x200+j])<<(8*j);
        std::cout << "{\"cycles\":" << top.cycles << ",\"instret\":" << top.instret
                  << ",\"overlap_cycles\":" << top.overlap_cycles << ",\"issue_count\":" << top.issue_count
                  << ",\"xw_overlap_cycles\":" << top.xw_overlap_cycles
                  << ",\"bypass_count\":" << top.bypass_count << ",\"flush_count\":" << top.flush_count
                  << ",\"icache_enabled\":" << unsigned(top.icache_enabled)
                  << ",\"icache_hits\":" << icache_hits << ",\"icache_misses\":" << icache_misses
                  << ",\"icache_refill_requests\":" << icache_refills << ",\"icache_miss_wait\":" << icache_wait
                  << ",\"icache_bypasses\":" << icache_bypasses << ",\"icache_invalidations\":" << icache_invalidations
                  << ",\"frontend_starved_cycles\":" << frontend_starved
                  << ",\"data_blocked_by_fetch_cycles\":" << data_fetch_contention
                  << ",\"fetch_blocked_by_data_cycles\":" << fetch_data_contention
                  << ",\"discarded_fetch_responses\":" << discarded_fetches
                  << ",\"fetch_buffer_enabled\":" << unsigned(top.fetch_buffer_enabled)
                  << ",\"fetch_buffer_reuses\":" << fetch_buffer_reuses << ",\"fetch_buffer_flushes\":" << fetch_buffer_flushes
                  << ",\"dcache_enabled\":" << unsigned(top.dcache_enabled)
                  << ",\"dcache_hits\":" << dcache_hits << ",\"dcache_misses\":" << dcache_misses
                  << ",\"dcache_refill_requests\":" << dcache_refills << ",\"dcache_miss_wait\":" << dcache_wait
                  << ",\"dcache_writes\":" << dcache_writes << ",\"dcache_bypasses\":" << dcache_bypasses
                  << ",\"split_memory_enabled\":" << unsigned(top.split_memory_enabled)
                  << ",\"instruction_hits_during_data_fill\":" << instruction_hits_during_data_fill
                  << ",\"data_hits_during_instruction_fill\":" << data_hits_during_instruction_fill
                  << ",\"predictor_enabled\":" << unsigned(top.predictor_enabled)
                  << ",\"control_resolved\":" << control_resolved << ",\"conditional_branches\":" << conditional_branches
                  << ",\"direct_jumps\":" << direct_jumps << ",\"indirect_jumps\":" << indirect_jumps
                  << ",\"control_misses\":" << control_misses << ",\"predicted_redirects\":" << predicted_redirects
                  << ",\"conditional_misses\":" << conditional_misses << ",\"direct_misses\":" << direct_misses << ",\"indirect_misses\":" << indirect_misses
                  << ",\"wide_fetch_enabled\":" << unsigned(top.wide_fetch_enabled)
                  << ",\"wide_decode_pairs\":" << wide_pairs
                  << ",\"issue_lookahead_enabled\":" << unsigned(top.issue_lookahead_enabled)
                  << ",\"dual_issue_enabled\":" << unsigned(top.dual_issue_enabled)
                  << ",\"dual_issue_pairs\":" << top.dual_issue_pairs
                  << ",\"icache_fill_forward_enabled\":" << unsigned(top.icache_fill_forward_enabled)
                  << ",\"icache_fill_hits\":" << fill_hits
                  << ",\"icache_refill_hits_enabled\":" << unsigned(top.icache_refill_hits_enabled)
                  << ",\"icache_refill_hits\":" << refill_hits
                  << ",\"demand_priority_enabled\":" << unsigned(top.demand_priority_enabled)
                  << ",\"demand_issue_enabled\":" << unsigned(top.demand_issue_enabled)
                  << ",\"window_forward_enabled\":" << unsigned(top.window_forward_enabled)
                  << ",\"prefetch_path_enabled\":" << unsigned(top.prefetch_path_enabled)
                  << ",\"prefetch_path_queries\":" << path_queries << ",\"prefetch_path_redirects\":" << path_redirects
                  << ",\"prefetch_path_rejects\":" << path_rejects << ",\"prefetch_path_page_blocks\":" << path_page_blocks
                  << ",\"ifetch_window_enabled\":" << unsigned(top.ifetch_window_enabled)
                  << ",\"ifetch_window_peak\":" << window_peak << ",\"ifetch_window_hits\":" << window_hits << ",\"ifetch_window_drops\":" << window_drops
                  << ",\"fetch_queue_enabled\":" << unsigned(top.fetch_queue_enabled)
                  << ",\"fetch_queue_pushes\":" << fq_pushes << ",\"fetch_queue_pops\":" << fq_pops
                  << ",\"fetch_queue_bypasses\":" << fq_bypasses << ",\"fetch_queue_full_cycles\":" << fq_full_cycles
                  << ",\"fetch_queue_flushes\":" << fq_flushes << ",\"fetch_queue_flushed_packets\":" << fq_flushed_packets
                  << ",\"fetch_queue_peak\":" << fq_peak << ",\"fetch_queue_fill_while_x_busy\":" << fq_fill_while_x_busy
                  << ",\"btb_enabled\":" << unsigned(top.btb_enabled)
                  << ",\"btb_lookups\":" << btb_lookups << ",\"btb_hits\":" << btb_hits
                  << ",\"btb_trains\":" << btb_trains << ",\"btb_rejects\":" << btb_rejects
                  << ",\"btb_predictions\":" << btb_predictions << ",\"btb_misses\":" << btb_misses
                  << ",\"gshare_enabled\":" << unsigned(top.gshare_enabled)
                  << ",\"bht_enabled\":" << unsigned(top.bht_enabled)
                  << ",\"bht_trains\":" << bht_trains << ",\"bht_taken\":" << bht_taken
                  << ",\"bht_predictions\":" << bht_predictions << ",\"bht_misses\":" << bht_misses
                  << ",\"ras_enabled\":" << unsigned(top.ras_enabled)
                  << ",\"ras_predictions\":" << ras_predictions << ",\"ras_misses\":" << ras_misses
                  << ",\"ras_pushes\":" << ras_pushes << ",\"ras_pops\":" << ras_pops
                  << ",\"ras_overflows\":" << ras_overflows << ",\"ras_underflows\":" << ras_underflows
                  << ",\"tlb_enabled\":" << unsigned(top.tlb_enabled)
                  << ",\"itlb_hits\":" << itlb_hits << ",\"itlb_misses\":" << itlb_misses << ",\"itlb_fills\":" << itlb_fills
                  << ",\"dtlb_hits\":" << dtlb_hits << ",\"dtlb_misses\":" << dtlb_misses << ",\"dtlb_fills\":" << dtlb_fills
                  << ",\"i_walk_reads\":" << i_walk_reads << ",\"d_walk_reads\":" << d_walk_reads << ",\"tlb_invalidations\":" << tlb_invalidations
                  << ",\"fetch_wait\":" << top.fetch_wait << ",\"data_wait\":" << top.data_wait
                  << ",\"requests\":" << requests << ",\"reads\":" << reads
                  << ",\"writes\":" << writes << ",\"result\":" << result
                  << ",\"fault\":" << unsigned(top.fault) << "}\n";
        return top.fault ? 2 : exit_status ? 3 : 0;
    } catch (const std::exception& e) { std::cerr << e.what() << '\n'; return 1; }
}
