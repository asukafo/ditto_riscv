#include "Vrv64_dual_hart.h"

#include <array>
#include <cstdint>
#include <fstream>
#include <iostream>
#include <stdexcept>

#ifndef EXPECT_L1D
#define EXPECT_L1D 1
#endif
#ifndef EXPECT_L2
#define EXPECT_L2 1
#endif

struct Request {
    uint64_t addr, data;
    unsigned bytes;
    bool write, store_check;

    bool operator==(const Request& rhs) const {
        return addr == rhs.addr && data == rhs.data && bytes == rhs.bytes &&
               write == rhs.write && store_check == rhs.store_check;
    }
};

int main(int argc, char** argv) try {
    if (argc != 4) throw std::runtime_error("usage: simulator image latency gap");
    const unsigned latency = std::stoul(argv[2]);
    const unsigned gap = std::stoul(argv[3]);
    if (!latency) throw std::runtime_error("latency must be positive");

    constexpr unsigned base = 0x4000;
    constexpr unsigned counter = 0x4400;
    std::array<uint8_t, 0x10000> ram{};
    std::ifstream image(argv[1], std::ios::binary);
    if (!image.read(reinterpret_cast<char*>(ram.data()), base) && !image.eof())
        throw std::runtime_error("cannot read image");
    if (!image.gcount() || image.gcount() >= base)
        throw std::runtime_error("invalid image size");
    auto load = [&](uint64_t addr, unsigned bytes) {
        uint64_t value = 0;
        for (unsigned i = 0; i < bytes; ++i) value |= uint64_t(ram[addr+i]) << (8*i);
        return value;
    };
    auto store = [&](uint64_t addr, unsigned bytes, uint64_t value) {
        for (unsigned i = 0; i < bytes; ++i) ram[addr+i] = uint8_t(value >> (8*i));
    };

    Vrv64_dual_hart top;
    top.irq_pending[0] = top.irq_pending[1] = top.irq_pending[2] = top.irq_pending[3] = 0;
    top.time_value = 0;
    top.mem_ready = top.mem_rsp_valid = top.mem_rsp_error = 0;
    top.mem_rsp_data = 0;
    top.clk = 0;
    top.reset = 1;
    top.eval();
    top.clk = 1;
    top.eval();
    top.reset = 0;

    bool pending = false, stalled = false, response_error = false, amo_read = false;
    uint64_t response_data = 0, response_cycle = 0, next_request = 0;
    unsigned lr_count = 0, requests = 0, both_retire = 0, request_stalls = 0;
    std::array<unsigned, 2> l1_hits{}, l1_misses{};
    unsigned l2_hits = 0, l2_fills = 0;
    Request previous{};
    for (uint64_t cycle = 1; cycle <= 100000; ++cycle) {
        top.clk = 0;
        top.time_value = cycle;
        top.mem_ready = !pending && cycle >= next_request;
        top.mem_rsp_valid = pending && cycle >= response_cycle;
        top.mem_rsp_error = top.mem_rsp_valid && response_error;
        top.mem_rsp_data = response_data;
        top.eval();

        for (unsigned hart = 0; hart < 2; ++hart) {
            l1_hits[hart] += (top.l1d_hit >> hart) & 1;
            l1_misses[hart] += (top.l1d_miss >> hart) & 1;
        }
        l2_hits += top.l2_hit;
        l2_fills += top.l2_fill;

        const Request req{top.mem_addr, top.mem_wdata, 1u << top.mem_size,
                          bool(top.mem_write), bool(top.mem_store_check)};
        if (stalled && (!top.mem_valid || !(req == previous)))
            throw std::runtime_error("request changed during backpressure");
        stalled = top.mem_valid && !top.mem_ready;
        if (stalled) ++request_stalls;
        previous = req;
        if (top.mem_rsp_valid && top.mem_rsp_ready) pending = false;
        if (top.mem_valid && top.mem_ready) {
            ++requests;
            response_error = req.addr > ram.size() - req.bytes || (req.addr & (req.bytes-1));
            response_data = 0;
            if (!response_error) {
                if (amo_read && (!req.write || req.addr != counter))
                    throw std::runtime_error("another request split an AMO");
                if (req.addr == counter) {
                    if (req.write != amo_read || req.store_check || req.bytes != 8)
                        throw std::runtime_error("invalid counter transaction");
                    amo_read = !req.write;
                }
                if (req.write) store(req.addr, req.bytes, req.data);
                else if (!req.store_check) response_data = load(req.addr, req.bytes);
            }
            pending = true;
            response_cycle = cycle + latency;
            next_request = response_cycle + gap;
        }

        top.clk = 1;
        top.eval();
        if (top.trap_valid) throw std::runtime_error("unexpected trap");
        if ((top.commit_valid | top.commit2_valid) == 3) ++both_retire;
        if ((top.commit_valid & 1) && (uint32_t(top.commit_insn) & 0xf800007f) == 0x1000002f) {
            store(0xfff8, 8, ++lr_count);
        }
        if (!pending && load(base+32, 8) == 1 && load(base+40, 8) == 2) {
            if (load(counter, 8) != 128 || load(base+8, 8) != 99 || lr_count != 2 ||
                amo_read || !both_retire || (gap > 1 && !request_stalls))
                throw std::runtime_error("incorrect shared memory or missing overlap");
            if ((EXPECT_L1D && (!l1_hits[0] || !l1_hits[1] || !l1_misses[0] || !l1_misses[1])) ||
                (!EXPECT_L1D && (l1_hits[0] || l1_hits[1] || l1_misses[0] || l1_misses[1])) ||
                (EXPECT_L2 && (!l2_hits || !l2_fills)) || (!EXPECT_L2 && (l2_hits || l2_fills)))
                throw std::runtime_error("cache events do not match configuration");
            std::cout << "PASS l1d=" << EXPECT_L1D << " l2=" << EXPECT_L2 << " latency=" << latency << " gap=" << gap << " cycles=" << cycle
                      << " instret=" << uint64_t(top.instret[0]) + (uint64_t(top.instret[1]) << 32)
                      << "/" << uint64_t(top.instret[2]) + (uint64_t(top.instret[3]) << 32)
                      << " both_retire=" << both_retire << " requests=" << requests
                      << " request_stalls=" << request_stalls
                      << " l1_hits=" << l1_hits[0] << "/" << l1_hits[1]
                      << " l1_misses=" << l1_misses[0] << "/" << l1_misses[1]
                      << " l2_hits=" << l2_hits << " l2_fills=" << l2_fills
                      << " counter=128 LR/SC=fail,pass coherence=pass\n";
            top.final();
            return 0;
        }
    }
    throw std::runtime_error("timeout");
} catch (const std::exception& e) {
    std::cerr << "FAIL " << e.what() << '\n';
    return 1;
}
