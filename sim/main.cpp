#include "Vrv64_core.h"
#include "verilated.h"
#include "verilated_vcd_c.h"
#include <algorithm>
#include <cstdint>
#include <fstream>
#include <iostream>
#include <iterator>
#include <memory>
#include <stdexcept>
#include <string>
#include <vector>

int main(int argc, char** argv) {
    try {
        if (argc < 3) throw std::runtime_error("usage: sim image.bin latency [wave.vcd] [request_gap]");
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
        top.rsp_error=0; top.rsp_rdata=0;
        evaluate(0); evaluate(1); evaluate(0);
        top.reset=0;
        bool pending=false, error=false;
        uint64_t response=0, requests=0, reads=0, writes=0;
        int remaining=0;
        uint64_t snapshot_addr=0, snapshot_data=0;
        bool was_blocked=false, snapshot_write=false;
        for (uint64_t tick=0; tick<1000000 && !top.halted; ++tick) {
            top.req_ready=!pending && (gap==0 || tick % (gap+1)==0);
            top.rsp_valid=pending && remaining==0;
            top.rsp_rdata=response; top.rsp_error=error;
            evaluate(0);
            if (was_blocked && (!top.req_valid || top.req_addr!=snapshot_addr ||
                top.req_write!=snapshot_write || top.req_wdata!=snapshot_data))
                throw std::runtime_error("request changed under backpressure");
            was_blocked=top.req_valid && !top.req_ready;
            snapshot_addr=top.req_addr; snapshot_data=top.req_wdata; snapshot_write=top.req_write;
            const bool accept=top.req_valid && top.req_ready;
            const bool consume=top.rsp_valid && top.rsp_ready;
            const uint64_t addr=top.req_addr, data=top.req_wdata;
            const bool write=top.req_write;
            evaluate(1);
            if (consume) pending=false;
            if (accept) {
                if (pending) throw std::runtime_error("more than one outstanding request");
                ++requests; if (write) ++writes; else ++reads;
                error=addr > ram.size()-8;
                response=0;
                if (!error) for (unsigned j=0; j<8; ++j) {
                    if (write) ram[size_t(addr)+j]=uint8_t(data>>(8*j));
                    else response |= uint64_t(ram[size_t(addr)+j])<<(8*j);
                }
                pending=true; remaining=latency-1;
            } else if (pending && remaining>0) --remaining;
        }
        top.final(); if (wave) wave->close();
        if (!top.halted) throw std::runtime_error("simulation timeout");
        uint64_t result=0;
        for (unsigned j=0; j<8; ++j) result |= uint64_t(ram[0x200+j])<<(8*j);
        std::cout << "{\"cycles\":" << top.cycles << ",\"instret\":" << top.instret
                  << ",\"fetch_wait\":" << top.fetch_wait << ",\"data_wait\":" << top.data_wait
                  << ",\"requests\":" << requests << ",\"reads\":" << reads
                  << ",\"writes\":" << writes << ",\"result\":" << result
                  << ",\"fault\":" << unsigned(top.fault) << "}\n";
        return top.fault ? 2 : 0;
    } catch (const std::exception& e) { std::cerr << e.what() << '\n'; return 1; }
}
