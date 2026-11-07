#include "Vrv64_l2_cache.h"

#include <cstdint>
#include <iostream>
#include <stdexcept>

static void check(bool ok, const char* why) {
    if (!ok) throw std::runtime_error(why);
}

class CacheTest {
public:
    Vrv64_l2_cache top;

    CacheTest() {
        top.reset = 1;
        top.u_valid = top.u_rsp_ready = 0;
        top.u_addr = top.u_wdata = top.u_size = 0;
        top.u_write = top.u_store_check = top.u_uncached = 0;
        top.d_ready = top.d_rsp_valid = top.d_rsp_error = 0;
        top.d_rsp_data = 0;
        tick();
        top.reset = 0;
    }

    void tick() {
        top.clk = 0;
        top.eval();
        top.clk = 1;
        top.eval();
    }

    void request(uint64_t addr, uint64_t expected, bool hit, unsigned size = 3,
                 bool write = false, bool error = false, bool uncached = false,
                 bool store_check = false) {
        top.clk = 0;
        top.u_valid = 1;
        top.u_addr = addr;
        top.u_size = size;
        top.u_write = write;
        top.u_store_check = store_check;
        top.u_uncached = uncached;
        top.u_wdata = 0x5a;
        top.u_rsp_ready = 0;
        top.d_ready = 0;
        top.eval();
        check(bool(top.hit_event) == hit && bool(top.d_valid) != hit, "wrong L2 hit/miss");
        if (!hit) {
            check(!top.u_ready && top.d_addr == addr && top.d_size == size &&
                  bool(top.d_store_check) == store_check && bool(top.d_write) == write &&
                  top.d_wdata == 0x5a, "miss/bypass metadata changed under backpressure");
            tick();
            top.d_ready = 1;
        }
        tick();
        top.u_valid = 0;
        top.u_addr = 0xdeadbeef;
        top.d_rsp_data = expected;
        top.d_rsp_error = error;
        top.d_rsp_valid = !hit;
        for (unsigned i = 0; i < 3; ++i) {
            tick();
            check(top.u_rsp_valid && top.u_rsp_data == expected && bool(top.u_rsp_error) == error &&
                  !top.d_rsp_ready && !top.u_ready, "held response corrupted");
        }
        top.u_rsp_ready = 1;
        tick();
        top.d_rsp_valid = top.d_rsp_error = 0;
    }
};

int main() try {
    CacheTest c;
    c.request(0x100, 0x123456789abcdef0ull, false);
    c.request(0x103, 0x9a, true, 0);          // byte hit from the low sector
    c.request(0x108, 42, false);             // high sector was still invalid
    c.request(0x900, 77, false);             // another way in the same set
    c.request(0x108, 42, true);
    c.request(0x900, 77, true);
    c.request(0x100, 0, false, 3, false, true, true); // atomic read must go to RAM
    c.request(0x100, 0, false, 3, false, false, true, true); // SC probe
    c.request(0x100, 0, false, 0, true, true); // failed write preserves data
    c.request(0x103, 0x9a, true, 0);
    c.request(0x103, 0, false, 0, true);      // successful byte store drops low sector
    c.request(0x108, 42, true);              // high sector still valid
    c.request(0x103, 0x5a, false, 0);        // subword misses do not allocate
    c.request(0x103, 0x5a, false, 0);
    c.request(0x100, 0x123456785abcdef0ull, false);
    c.request(0x103, 0x5a, true, 0);
    c.request(0xfff8, 1, false);
    c.request(0xfff8, 2, false);             // uncached mailbox can change
    c.request(0x1100, 99, false);            // replace least recently used way
    c.request(0x900, 77, false);
    c.request(0x1100, 99, true);
    c.request(0x1900, 0, false, 3, false, true);
    c.request(0x1900, 1, false);             // error cannot allocate
    std::cout << "L2 CACHE UNIT PASS: ways, sectors, exact-size bypass, error, backpressure\n";
    return 0;
} catch (const std::exception& e) {
    std::cerr << "FAIL " << e.what() << '\n';
    return 1;
}
