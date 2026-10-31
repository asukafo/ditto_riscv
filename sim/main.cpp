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
                      << ",\"pc\":" << top.commit_pc << ",\"insn\":" << top.commit_insn
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
                  << ",\"fetch_wait\":" << top.fetch_wait << ",\"data_wait\":" << top.data_wait
                  << ",\"requests\":" << requests << ",\"reads\":" << reads
                  << ",\"writes\":" << writes << ",\"result\":" << result
                  << ",\"fault\":" << unsigned(top.fault) << "}\n";
        return top.fault ? 2 : exit_status ? 3 : 0;
    } catch (const std::exception& e) { std::cerr << e.what() << '\n'; return 1; }
}
