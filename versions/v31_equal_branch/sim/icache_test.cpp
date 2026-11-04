#include "Vrv64_icache.h"
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
    Vrv64_icache top{&context};
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
        top.u_addr=0;top.u_data=0;top.u_size=2;top.u_write=0;top.u_execute=1;top.u_atomic=0;top.u_amo=0;
        top.d_ready=0;top.d_rsp_valid=0;top.d_rsp_data=0;top.d_rsp_error=0;
        top.eval();top.clk=1;top.eval();top.clk=0;top.eval();top.reset=0;
    }
    uint64_t read(uint64_t address,unsigned size) {
        if (address>=ram.size()) return 0xfeed1234;
        uint64_t value=0;
        for (unsigned i=0;i<(1u<<size);++i) value|=uint64_t(ram.at(size_t(address)+i))<<(8*i);
        return value;
    }
    struct Edge {bool accepted,returned;Result result;bool refill_hit,fill_hit;};
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
        Edge result{bool(top.u_valid && top.u_ready),bool(top.u_rsp_valid && top.u_rsp_ready),{top.u_rsp_data,bool(top.u_rsp_error)},bool(top.refill_hit_event),bool(top.fill_hit_event)};
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
    Result access(uint64_t address,unsigned size=2,bool execute=true,bool write=false,uint64_t data=0,
                  bool atomic=false,unsigned amo=0,bool invalidate_fill=false) {
        top.u_addr=address;top.u_data=data;top.u_size=size;top.u_execute=execute;
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
        unsigned scenarios=0;
        for (auto config:std::array<std::array<int,2>,3>{{{{1,0}},{{5,3}},{{20,7}}}}) {
            Memory m(config[0],config[1]);
            auto expect=[&](uint64_t address,unsigned size,bool execute=true) {
                uint64_t expected=m.read(address,size);Result r=m.access(address,size,execute);
                check(!r.error && r.data==expected,"incorrect read data");++scenarios;
            };
            expect(0x20,2);check(m.requests.size()==2,"cold miss must use two beats");
            check(m.requests[0].address==0x20 && m.requests[1].address==0x28 && m.requests[0].size==3,"wrong refill geometry");
            expect(0x24,2);expect(0x2e,1);check(m.requests.size()==2,"same-line reads missed");
            expect(0x120,2);expect(0x20,2);check(m.requests.size()==6,"direct-mapped conflict was not replaced");
            expect(0x20,2,false);check(m.requests.size()==7 && m.requests.back().size==2,"data access incorrectly cached");
            uint64_t old=m.read(0x20,2);m.access(0x20,2,false,true,0x11223344);++scenarios;
            size_t count=m.requests.size();auto stale=m.access(0x20);++scenarios;
            check(stale.data==old && m.requests.size()==count,"store unexpectedly changed cached instruction bytes");
            m.invalidate();expect(0x20,2);check(m.read(0x20,2)==0x11223344,"store did not reach memory");
            expect(0x6000,3,false);check(m.requests.back().size==3,"PTE access not bypassed");
            count=m.requests.size();expect(0x0200bff8,2);expect(0x0200bff8,2);
            check(m.requests.size()==count+2,"MMIO instruction reads incorrectly cached");
            m.access(0x500,3,false,true,0xabc,true,0x1c);++scenarios;
            check(m.requests.back().atomic && m.requests.back().write && m.requests.back().amo==0x1c &&
                  m.requests.back().data==0xabc,"atomic metadata altered by bypass");
            m.fail_address=0x78;count=m.requests.size();auto failed=m.access(0x70);++scenarios;
            check(failed.error && m.requests.size()==count+2,"second-beat error lost");
            m.fail_address=~uint64_t(0);expect(0x70,2);check(m.requests.size()==count+4,"failed refill became valid");
            expect(0x70,2);check(m.requests.size()==count+4,"successful retry did not allocate");
            m.fail_address=0x80;count=m.requests.size();failed=m.access(0x80);++scenarios;
            check(failed.error && m.requests.size()==count+1,"first-beat error lost");
            m.fail_address=~uint64_t(0);expect(0x80,2);
            count=m.requests.size();auto poisoned=m.access(0x90,2,true,false,0,false,0,true);++scenarios;
            check(!poisoned.error && poisoned.data==m.read(0x90,2),"invalidated refill response lost");
            expect(0x90,2);check(m.requests.size()==count+4,"in-flight invalidated refill revalidated old data");
            count=m.requests.size();expect(0x2e,2);
            check(m.requests.size()==count+1 && m.requests.back().size==2,"cross-line read was truncated instead of bypassed");
            count=m.requests.size();expect(0x10020,2);expect(0x10020,2);
            check(m.requests.size()==count+2,"high physical address aliased cacheable RAM");
        }
        std::cout<<"ICACHE UNIT PASS: "<<scenarios<<" checks across 3 latency/backpressure configurations\n";
        return 0;
    } catch (const std::exception& e) {std::cerr<<e.what()<<'\n';return 1;}
}
