#include "Vrv64_mmu.h"
#include "verilated.h"
#include <array>
#include <cstdint>
#include <iostream>
#include <stdexcept>
static void check(bool x,const char* why){if(!x)throw std::runtime_error(why);}
struct Result{uint64_t data,cause;bool error;};
class Memory{
public:
    VerilatedContext ctx;Vrv64_mmu t{&ctx};std::array<uint8_t,65536> ram{};
    unsigned latency,gap,ticks=0,remaining=0,walks=0,hits=0,fills=0;
    bool pending=false,error=false;uint64_t response=0,fail=~uint64_t(0);
    Memory(unsigned l,unsigned g):latency(l),gap(g){
        t.clk=0;t.reset=1;t.tlb_invalidate=0;t.privilege=1;t.data_privilege=1;t.satp=(uint64_t(8)<<60)|6;t.sum=0;t.mxr=0;
        t.u_valid=0;t.u_addr=0;t.u_data=0;t.u_size=3;t.u_write=0;t.u_execute=0;t.u_atomic=0;t.u_amo=0;t.u_rsp_ready=1;
        t.d_ready=0;t.d_rsp_valid=0;t.d_rsp_data=0;t.d_rsp_error=0;t.eval();t.clk=1;t.eval();t.clk=0;t.eval();t.reset=0;
        put(0x6008,0x1c01);put(0x7000,0x2001);put(0x8000,0x8c7);put(0x2000,42);put(0x3000,99);
    }
    void put(uint64_t a,uint64_t v){for(unsigned i=0;i<8;++i)ram.at(a+i)=uint8_t(v>>(i*8));}
    uint64_t get(uint64_t a,unsigned s){uint64_t v=0;for(unsigned i=0;i<(1u<<s);++i)v|=uint64_t(ram.at(a+i))<<(8*i);return v;}
    struct Edge{bool accepted,returned;Result result;};
    Edge step(){
        t.clk=0;t.d_ready=!pending&&ticks%(gap+1)==0;t.d_rsp_valid=pending&&remaining==0;t.d_rsp_data=response;t.d_rsp_error=error;t.eval();
        Edge e{bool(t.u_valid&&t.u_ready),bool(t.u_rsp_valid&&t.u_rsp_ready),{t.u_rsp_data,t.u_rsp_cause,bool(t.u_rsp_error)}};
        bool a=t.d_valid&&t.d_ready,c=t.d_rsp_valid&&t.d_rsp_ready;uint64_t addr=t.d_addr,data=t.d_data;unsigned size=t.d_size;bool write=t.d_write;
        walks+=t.walk_event;hits+=t.tlb_hit_event;fills+=t.tlb_fill_event;t.clk=1;t.eval();++ticks;
        if(c)pending=false;
        if(a){check(!pending,"multiple outstanding MMU reads");error=addr>ram.size()-(1u<<size)||addr==fail;response=0;
            if(!error){response=get(addr,size);if(write)for(unsigned i=0;i<(1u<<size);++i)ram.at(addr+i)=uint8_t(data>>(8*i));}
            pending=true;remaining=latency-1;
        }else if(pending&&remaining)--remaining;
        return e;
    }
    void flush(){t.tlb_invalidate=1;step();t.tlb_invalidate=0;}
    Result access(uint64_t addr=0x40000000,bool write=false,bool execute=false,bool poison=false){
        t.u_addr=addr;t.u_write=write;t.u_execute=execute;t.u_data=77;t.u_valid=1;
        bool accepted=false,poisoned=false;unsigned before=walks;
        for(unsigned i=0;i<10000;++i){
            t.tlb_invalidate=poison&&!poisoned&&walks>before;
            if(t.tlb_invalidate)poisoned=true;
            auto e=step();t.tlb_invalidate=0;if(e.accepted){accepted=true;t.u_valid=0;}
            if(e.returned){check(accepted,"unsolicited MMU response");return e.result;}
        }throw std::runtime_error("MMU request timeout");
    }
};
int main(){try{unsigned checks=0;
    for(auto cfg:std::array<std::array<unsigned,2>,3>{{{{1,0}},{{5,3}},{{20,7}}}}){
        Memory m(cfg[0],cfg[1]);auto r=m.access();check(!r.error&&r.data==42&&m.walks==3&&m.fills==1,"initial walk failed");++checks;
        r=m.access();check(!r.error&&r.data==42&&m.walks==3&&m.hits==1,"TLB hit walked again");++checks;
        m.t.data_privilege=0;r=m.access();check(r.error&&r.cause==13&&m.walks==3,"cached S page allowed U access");++checks;
        m.t.data_privilege=1;m.put(0x8000,0xcc7);m.flush();r=m.access();check(!r.error&&r.data==99,"fence did not remove stale mapping");++checks;
        // Same ASID, different root; then a different ASID. No external flush is needed for full-context tag isolation.
        m.put(0x9008,0x2801);m.put(0xa000,0x2c01);m.put(0xb000,0x8c7);m.t.satp=(uint64_t(8)<<60)|9;
        unsigned w=m.walks;r=m.access();check(!r.error&&r.data==42&&m.walks==w+3,"root context aliased");++checks;
        m.t.satp=(uint64_t(8)<<60)|(uint64_t(1)<<44)|9;w=m.walks;r=m.access();check(!r.error&&m.walks==w+3,"ASID context aliased");++checks;
        // SUM changes apply to an already filled U page without a fence.
        Memory sum(cfg[0],cfg[1]);sum.put(0x8000,0x8d7);sum.t.sum=1;r=sum.access();check(!r.error,"SUM warm load failed");++checks;
        sum.t.sum=0;w=sum.walks;r=sum.access();check(r.error&&r.cause==13&&sum.walks==w,"SUM change ignored on hit");++checks;
        sum.t.sum=1;r=sum.access(0x40000000,false,true);check(r.error&&r.cause==12,"S executed U page with SUM");++checks;
        // MXR and Svade D-bit are checked on each hit too.
        Memory mxr(cfg[0],cfg[1]);mxr.put(0x8000,0x8c9);mxr.t.mxr=1;r=mxr.access();check(!r.error,"MXR warm failed");++checks;
        mxr.t.mxr=0;w=mxr.walks;r=mxr.access();check(r.error&&r.cause==13&&mxr.walks==w,"MXR change ignored");++checks;
        Memory dirty(cfg[0],cfg[1]);dirty.put(0x8000,0x847);r=dirty.access();check(!r.error,"read-only A/D warm failed");++checks;
        w=dirty.walks;r=dirty.access(0x40000000,true);check(r.error&&r.cause==15&&dirty.walks==w,"cached D=0 allowed store");++checks;
        dirty.t.u_atomic=1;dirty.t.u_amo=3;w=dirty.walks;r=dirty.access(0x40000000,true);
        check(r.error&&r.cause==15&&dirty.walks==w,"cached D=0 allowed failed-SC permission probe");++checks;
        dirty.t.u_atomic=0;
        dirty.put(0x8000,0x8c7);dirty.flush();r=dirty.access(0x40000000,true);check(!r.error&&dirty.get(0x2000,3)==77,"D-bit repair/fence failed");++checks;
        // Invalid/noncanonical/bus-fault walks must not allocate successful translations.
        Memory bad(cfg[0],cfg[1]);bad.put(0x8000,0);r=bad.access();check(r.error&&r.cause==13&&bad.fills==0,"invalid PTE allocated");++checks;
        bad.put(0x8000,0x8c7);r=bad.access();check(!r.error,"invalid PTE repair stayed cached");++checks;
        w=bad.walks;r=bad.access(0x8040000000ull);check(r.error&&r.cause==13&&bad.walks==w,"noncanonical alias used TLB");++checks;
        bad.flush();bad.fail=0x8000;r=bad.access();check(r.error&&r.cause==5,"walk access error lost");++checks;
        // Invalidation during a walk prevents its later successful leaf from repopulating the TLB.
        Memory poison(cfg[0],cfg[1]);r=poison.access(0x40000000,false,false,true);check(!r.error&&poison.fills==0,"invalidated walk refilled TLB");++checks;
        w=poison.walks;r=poison.access();check(!r.error&&poison.walks==w+3&&poison.fills==1,"poisoned walk retry wrong");++checks;
        // Valid level-1 superpages work via walker and are deliberately not allocated.
        Memory large(cfg[0],cfg[1]);large.put(0x7000,0xc7);r=large.access(0x40002000);check(!r.error&&r.data==42&&large.fills==0,"superpage fallback failed");++checks;
        w=large.walks;r=large.access(0x40002000);check(!r.error&&large.walks==w+2,"superpage accidentally cached as 4K");++checks;
    }
    std::cout<<"MMU TLB UNIT PASS: "<<checks<<" permission/context/flush/error/poison/superpage checks\n";return 0;
}catch(const std::exception& e){std::cerr<<e.what()<<'\n';return 1;}}
