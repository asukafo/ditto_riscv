#include "Vrv64_dcache.h"
#include "verilated.h"
#include <array>
#include <cstdint>
#include <iostream>
#include <stdexcept>
#include <string>
#include <vector>

static void check(bool value,const std::string& why) {
    if (!value) throw std::runtime_error(why);
}
struct Request {uint64_t address,data; unsigned size,amo; bool write,atomic;};
struct Result {uint64_t data;bool error;};

class Memory {
public:
    VerilatedContext context;
    Vrv64_dcache top{&context};
    std::array<uint8_t,65536> ram{};
    std::vector<Request> requests;
    uint64_t fail_address=~uint64_t(0);
    unsigned ticks=0,hits=0,misses=0;
    int latency,gap,remaining=0;
    bool pending=false,error=false,blocked=false,response_blocked=false;
    uint64_t response=0,held_response=0;
    bool held_error=false;
    Request held{};
    explicit Memory(int latency_,int gap_):latency(latency_),gap(gap_) {
        for (unsigned i=0;i<ram.size();++i) ram[i]=uint8_t(i*37+3);
        top.clk=0;top.reset=1;top.invalidate=0;top.u_valid=0;top.u_rsp_ready=1;
        top.u_addr=0;top.u_data=0;top.u_size=2;top.u_write=0;top.u_execute=0;top.u_cache_data=1;top.u_atomic=0;top.u_amo=0;
        top.d_ready=0;top.d_rsp_valid=0;top.d_rsp_data=0;top.d_rsp_error=0;
        top.eval();top.clk=1;top.eval();top.clk=0;top.eval();top.reset=0;
    }
    uint64_t read(uint64_t address,unsigned size) {
        if (address>=ram.size()) return 0xfeed1234;
        uint64_t value=0;
        for (unsigned i=0;i<(1u<<size);++i) value|=uint64_t(ram.at(size_t(address)+i))<<(8*i);
        return value;
    }
    struct Edge {bool accepted,returned;Result result;};
    Edge step() {
        top.clk=0;top.d_ready=!pending && ticks%unsigned(gap+1)==0;
        top.d_rsp_valid=pending && remaining==0;top.d_rsp_data=response;top.d_rsp_error=error;top.eval();
        Request now{top.d_addr,top.d_data,top.d_size,top.d_amo,bool(top.d_write),bool(top.d_atomic)};
        if (blocked) check(top.d_valid && now.address==held.address && now.data==held.data && now.size==held.size &&
                           now.amo==held.amo && now.write==held.write && now.atomic==held.atomic,"request changed under backpressure");
        if (response_blocked) check(top.u_rsp_valid && top.u_rsp_data==held_response && bool(top.u_rsp_error)==held_error,
                                    "response changed under backpressure");
        blocked=top.d_valid && !top.d_ready;held=now;
        response_blocked=top.u_rsp_valid && !top.u_rsp_ready;held_response=top.u_rsp_data;held_error=top.u_rsp_error;
        Edge result{bool(top.u_valid && top.u_ready),bool(top.u_rsp_valid && top.u_rsp_ready),{top.u_rsp_data,bool(top.u_rsp_error)}};
        bool accept=top.d_valid && top.d_ready,consume=top.d_rsp_valid && top.d_rsp_ready;
        hits+=top.hit_event;misses+=top.miss_event;
        top.clk=1;top.eval();++ticks;
        if (consume) pending=false;
        if (accept) {
            check(!pending,"multiple outstanding downstream requests");requests.push_back(now);
            response=read(now.address,now.size);error=now.address==fail_address;
            if (now.write && !error && now.address<ram.size())
                for (unsigned i=0;i<(1u<<now.size);++i) ram.at(size_t(now.address)+i)=uint8_t(now.data>>(8*i));
            pending=true;remaining=latency-1;
        } else if (pending && remaining>0) --remaining;
        return result;
    }
    Result access(uint64_t address,unsigned size=2,bool cache_data=true,bool write=false,uint64_t data=0,
                  bool atomic=false,unsigned amo=0,bool invalidate_fill=false) {
        top.u_addr=address;top.u_data=data;top.u_size=size;top.u_execute=0;top.u_cache_data=cache_data;
        top.u_write=write;top.u_atomic=atomic;top.u_amo=amo;top.u_valid=1;top.u_rsp_ready=0;
        bool accepted=false;
        for (unsigned i=0;i<1000 && !accepted;++i) accepted=step().accepted;
        check(accepted,"upstream request timeout");top.u_valid=0;
        top.u_addr=0xdeadbeef;top.u_data=0xbaadf00d; // accepted metadata must be held internally
        size_t before=requests.size();bool invalidated=false;
        for (unsigned i=0;i<1000;++i) {
            top.invalidate=invalidate_fill && !invalidated && requests.size()>before;
            invalidated=invalidated || top.invalidate;
            top.u_rsp_ready=i>=3;
            Edge edge=step();top.invalidate=0;
            if (edge.returned) return edge.result;
        }
        throw std::runtime_error("upstream response timeout");
    }
    void invalidate() {top.invalidate=1;step();top.invalidate=0;}
};

int main() {
    try {
        unsigned checks=0;
        for(auto cfg:std::array<std::array<int,2>,3>{{{{1,0}},{{5,3}},{{20,7}}}}) {
            Memory m(cfg[0],cfg[1]);
            auto expect=[&](uint64_t a,unsigned size=3,bool cache_data=true) {
                auto r=m.access(a,size,cache_data);check(!r.error && r.data==m.read(a,size),"wrong cached data");++checks;
            };
            expect(0x20);check(m.requests.size()==2,"miss must refill 16 bytes");++checks;
            for(unsigned size=0;size<4;++size) for(unsigned off=0;off+(1u<<size)<=16;off+=(1u<<size))
                expect(0x20+off,size);
            check(m.requests.size()==2,"same line did not hit");++checks;
            // Every supported store width and byte lane must preserve neighbors.
            for(unsigned size=0;size<4;++size) for(unsigned off=0;off+(1u<<size)<=16;off+=(1u<<size)) {
                size_t before=m.requests.size();auto r=m.access(0x20+off,size,true,true,0xfedcba9876543210ull+off);
                check(!r.error && m.requests.size()==before+1 && m.requests.back().write && m.requests.back().size==size,"write-through altered request");++checks;
                expect(0x20);expect(0x28);check(m.requests.size()==before+1,"write hit lost line");++checks;
            }
            size_t n=m.requests.size();m.access(0x120,3,true,true,0x1234);expect(0x20);
            check(m.requests.size()==n+1,"write miss allocated or evicted unrelated tag");++checks;
            expect(0x120);expect(0x20);check(m.requests.size()==n+5,"direct-mapped conflict wrong");++checks;
            // Uncached normal alias, atomics and reads for page walks must bypass.
            n=m.requests.size();expect(0x20,3,false);check(m.requests.size()==n+1,"PTW incorrectly cached");++checks;
            m.access(0x20,3,true,true,0xabcd,true,0);expect(0x20);
            check(m.requests.size()==n+4 && m.requests[n+1].atomic,"atomic did not bypass and invalidate");++checks;
            m.access(0x20,3,false,true,0x3344);expect(0x20);
            check(m.requests.size()==n+7,"bypass write did not invalidate cached alias");++checks;
            // Failed writes cannot leave a cached value valid.
            m.fail_address=0x20;auto r=m.access(0x20,3,true,true,0x5555);check(r.error,"write fault lost");++checks;
            m.fail_address=~uint64_t(0);n=m.requests.size();expect(0x20);check(m.requests.size()==n+2,"failed store left cached line valid");++checks;
            for(uint64_t fail:{0x60ull,0x68ull}) {
                m.fail_address=fail;n=m.requests.size();r=m.access(0x60);check(r.error,"refill fault lost");++checks;
                m.fail_address=~uint64_t(0);n=m.requests.size();expect(0x60);check(m.requests.size()==n+2,"failed fill became valid");++checks;m.invalidate();
            }
            n=m.requests.size();r=m.access(0x80,3,true,false,0,false,0,true);check(!r.error,"poisoned fill failed request");++checks;
            expect(0x80);check(m.requests.size()==n+4,"invalidation did not poison refill");++checks;
            n=m.requests.size();expect(0xfff0);expect(0xfff0);expect(0x0200bff8);expect(0x0200bff8);expect(0x10020);expect(0x10020);
            check(m.requests.size()==n+6,"mailbox/MMIO/high alias cached");++checks;
            n=m.requests.size();expect(0x2e,2);check(m.requests.size()==n+1 && m.requests.back().size==2,"cross-line read truncated");++checks;
            // Explicit instruction traffic is not a data read.
            m.top.u_addr=0x200;m.top.u_size=2;m.top.u_execute=1;m.top.u_cache_data=0;m.top.u_write=0;m.top.u_atomic=0;m.top.u_valid=1;
            bool accepted=false;for(unsigned i=0;i<1000&&!accepted;++i) accepted=m.step().accepted;
            check(accepted,"instruction bypass timeout");m.top.u_valid=0;
            bool returned=false;for(unsigned i=0;i<1000&&!returned;++i) returned=m.step().returned;
            check(returned && m.requests.back().address==0x200 && m.requests.back().size==2,"instruction bypass metadata lost");++checks;
        }
        std::cout<<"DCACHE UNIT PASS: "<<checks<<" checks across 3 latency/backpressure configurations\n";return 0;
    } catch(const std::exception& e) {std::cerr<<e.what()<<'\n';return 1;}
}
