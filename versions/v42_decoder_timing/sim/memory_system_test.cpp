#include "Vrv64_memory_system.h"
#include "verilated.h"
#include <array>
#include <cstdint>
#include <iostream>
#include <stdexcept>
#include <vector>
static void check(bool x,const char* why){if(!x)throw std::runtime_error(why);}
struct Result{uint64_t data,cause;bool error;};
struct Edge{bool fa,da,fr,dr;Result f,d;};
class Memory{
public:
    VerilatedContext ctx;Vrv64_memory_system t{&ctx};std::array<uint8_t,65536> ram{};
    unsigned latency,gap,ticks=0,remaining=0,requests=0,ihits_dfill=0,dhits_ifill=0;
    bool pending=false,error=false,blocked=false,fp=false,dp=false;
    uint64_t response=0,held_addr=0,held_data=0,fail_address=~uint64_t(0);
    unsigned held_size=0;bool held_write=false,held_check=false;
    explicit Memory(unsigned l,unsigned g):latency(l),gap(g){
        for(unsigned i=0;i<ram.size();++i)ram[i]=uint8_t(i*37+3);
        t.tlb_invalidate=0;t.clk=0;t.reset=1;t.clear_reservation=0;t.reservation_invalidate=0;t.icache_invalidate=0;
        t.privilege=3;t.data_privilege=3;t.satp=0;t.sum=0;t.mxr=0;
        t.f_valid=0;t.f_addr=0;t.f_size=2;t.f_rsp_ready=1;
        t.d_valid=0;t.d_addr=0;t.d_data=0;t.d_size=3;t.d_write=0;t.d_atomic=0;t.d_amo=0;t.d_rsp_ready=1;
        t.req_ready=0;t.rsp_valid=0;t.rsp_rdata=0;t.rsp_error=0;
        t.eval();t.clk=1;t.eval();t.clk=0;t.eval();t.reset=0;
    }
    uint64_t read(uint64_t a,unsigned size){uint64_t v=0;for(unsigned i=0;i<(1u<<size);++i)v|=uint64_t(ram.at(a+i))<<(i*8);return v;}
    void put(uint64_t a,uint64_t v){for(unsigned i=0;i<8;++i)ram.at(a+i)=uint8_t(v>>(i*8));}
    Edge step(){
        t.clk=0;t.req_ready=!pending && ticks%(gap+1)==0;t.rsp_valid=pending && remaining==0;
        t.rsp_rdata=response;t.rsp_error=error;t.eval();
        if(blocked)check(t.req_valid && t.req_addr==held_addr && t.req_wdata==held_data && t.req_size==held_size && bool(t.req_write)==held_write && bool(t.req_store_check)==held_check,"external request changed under stall");
        blocked=t.req_valid&&!t.req_ready;held_addr=t.req_addr;held_data=t.req_wdata;held_size=t.req_size;held_write=t.req_write;held_check=t.req_store_check;
        Edge e{bool(t.f_valid&&t.f_ready),bool(t.d_valid&&t.d_ready),bool(t.f_rsp_valid&&t.f_rsp_ready),bool(t.d_rsp_valid&&t.d_rsp_ready),{t.f_rsp_data,t.f_rsp_cause,bool(t.f_rsp_error)},{t.d_rsp_data,t.d_rsp_cause,bool(t.d_rsp_error)}};
        if(e.fa){check(!fp,"second outstanding fetch");fp=true;}if(e.da){check(!dp,"second outstanding data request");dp=true;}
        if(e.fr){check(fp,"unsolicited fetch response");fp=false;}if(e.dr){check(dp,"unsolicited data response");dp=false;}
        ihits_dfill+=t.icache_hit_event && t.dcache_miss_wait;dhits_ifill+=t.dcache_hit_event && t.icache_miss_wait;
        bool accept=t.req_valid&&t.req_ready,consume=t.rsp_valid&&t.rsp_ready;
        uint64_t addr=t.req_addr,data=t.req_wdata;unsigned size=t.req_size;bool write=t.req_write;
        t.clk=1;t.eval();++ticks;
        if(consume)pending=false;
        if(accept){check(!pending,"more than one physical request");++requests;response=0;error=addr>ram.size()-(1u<<size) || addr==fail_address;
            if(!error){response=read(addr,size);if(write)for(unsigned i=0;i<(1u<<size);++i)ram.at(addr+i)=uint8_t(data>>(8*i));}
            pending=true;remaining=latency-1;
        }else if(pending && remaining)--remaining;
        return e;
    }
    std::array<Result,2> access(bool fetch,uint64_t fa,bool data,uint64_t da,bool write=false,uint64_t value=0){
        t.f_valid=fetch;t.f_addr=fa;t.f_size=2;t.d_valid=data;t.d_addr=da;t.d_size=3;t.d_write=write;t.d_data=value;t.d_atomic=0;
        bool fr=!fetch,dr=!data;std::array<Result,2> results{};
        for(unsigned i=0;i<10000 && (!fr||!dr);++i){auto e=step();if(e.fa)t.f_valid=0;if(e.da)t.d_valid=0;if(e.fr){fr=true;results[0]=e.f;}if(e.dr){dr=true;results[1]=e.d;}}
        check(fr&&dr,"memory system response timeout");return results;
    }
    void drain(){t.f_valid=0;t.d_valid=0;t.f_rsp_ready=1;t.d_rsp_ready=1;for(unsigned i=0;i<10000;++i){step();if(!t.busy)return;}throw std::runtime_error("memory system failed to drain");}
    void page_tables(){
        for(uint64_t a=0x6000;a<0x9000;a+=8)put(a,0);
        put(0x6008,0x1c01);put(0x7000,0x2001);put(0x8000,0x45b);put(0x8008,0x8d7);
        t.privilege=0;t.data_privilege=0;t.satp=(uint64_t(8)<<60)|6;
    }
};
int main(){try{unsigned checks=0;
    for(auto cfg:std::array<std::array<unsigned,2>,3>{{{{1,0}},{{5,3}},{{20,7}}}}){
        Memory m(cfg[0],cfg[1]);auto both=m.access(true,0x100,false,0);m.drain();check(!both[0].error&&both[0].data==m.read(0x100,2),"initial instruction fill wrong");++checks;
        both=m.access(false,0,true,0x3000);check(!both[1].error&&both[1].data==m.read(0x3000,3),"initial data fill wrong");++checks;
        both=m.access(true,0x104,false,0);m.drain();check(!both[0].error&&both[0].data==m.read(0x104,2),"hit during data refill wrong");++checks;
        if(cfg[0]>1){check(m.ihits_dfill>0,"instruction hit was blocked by data fill");++checks;}
        both=m.access(true,0x200,false,0);both=m.access(false,0,true,0x3008);m.drain();
        check(!both[1].error&&both[1].data==m.read(0x3008,3),"data hit during instruction fill wrong");++checks;
        if(cfg[0]>1){check(m.dhits_ifill>0,"data hit was blocked by instruction fill");++checks;}
        // Independent walkers simultaneously translate instruction and data pages.
        Memory p(cfg[0],cfg[1]);p.page_tables();both=p.access(true,0x40000000,true,0x40001000);p.drain();
        check(!both[0].error&&both[0].data==p.read(0x1000,2),"concurrent I walker returned wrong data");++checks;
        check(!both[1].error&&both[1].data==p.read(0x2000,3),"concurrent D walker returned wrong data");++checks;
        // Cached bytes must not bypass changed permissions on either side.
        p.t.tlb_invalidate=1;p.step();p.t.tlb_invalidate=0;p.put(0x8008,0x8c7);both=p.access(true,0x40000004,true,0x40001008);p.drain();
        check(!both[0].error&&both[0].data==p.read(0x1004,2),"D page fault damaged I response");++checks;
        check(both[1].error&&both[1].cause==13,"warm D line bypassed user permissions");++checks;
        p.t.tlb_invalidate=1;p.step();p.t.tlb_invalidate=0;p.put(0x8008,0x8d7);p.put(0x8000,0x44b);both=p.access(true,0x40000008,true,0x40001000);p.drain();
        check(both[0].error&&both[0].cause==12,"warm I line bypassed user execute permission");++checks;
        check(!both[1].error&&both[1].data==p.read(0x2000,3),"I page fault damaged D response");++checks;
        // Page walk bus error routing with the opposite cache path still active.
        p.t.tlb_invalidate=1;p.step();p.t.tlb_invalidate=0;p.put(0x8000,0x45b);p.fail_address=0x8008;both=p.access(true,0x40000000,true,0x40001000);p.drain();
        check(!both[0].error&&both[1].error&&both[1].cause==5,"walker access error misrouted");++checks;
        // Distinct physical tags after a mapping change must yield distinct bytes.
        p.t.tlb_invalidate=1;p.step();p.t.tlb_invalidate=0;p.fail_address=~uint64_t(0);p.put(0x8008,0xcd7);both=p.access(true,0x40000000,true,0x40001000);p.drain();
        check(!both[1].error&&both[1].data==p.read(0x3000,3),"mapping change reused stale physical tag");++checks;
        // Hold both return channels while memory makes progress.
        Memory held(cfg[0],cfg[1]);held.t.f_valid=1;held.t.f_addr=0x100;held.t.d_valid=1;held.t.d_addr=0x3000;held.t.f_rsp_ready=0;held.t.d_rsp_ready=0;
        for(unsigned i=0;i<1000;++i){auto e=held.step();if(e.fa)held.t.f_valid=0;if(e.da)held.t.d_valid=0;}
        check(held.t.f_rsp_valid&&held.t.d_rsp_valid,"held concurrent responses lost");++checks;
        check(held.t.f_rsp_data==held.read(0x100,2)&&held.t.d_rsp_data==held.read(0x3000,3),"held concurrent response data changed");++checks;
        held.t.f_rsp_ready=1;held.t.d_rsp_ready=1;auto e=held.step();check(e.fr&&e.dr,"independent responses did not retire together");++checks;held.drain();
    }
    std::cout<<"SPLIT MEMORY UNIT PASS: "<<checks<<" checks, concurrent hits/walkers/permissions/errors/backpressure\n";return 0;
}catch(const std::exception& e){std::cerr<<e.what()<<'\n';return 1;}}
