#include "Vrv64_fetch.h"
#include "verilated.h"
#include <array>
#include <cstdint>
#include <iostream>
#include <stdexcept>
#include <vector>

static void check(bool value,const char* message) { if (!value) throw std::runtime_error(message); }
struct Instruction {uint64_t pc,value,cause;uint32_t raw,expanded;unsigned bytes;bool fault,illegal;uint64_t prediction;bool from_ras;unsigned index;bool dynamic;};
struct Request {uint64_t address;unsigned size;};

class Memory {
public:
    VerilatedContext context;
    Vrv64_fetch top{&context};
    std::array<uint8_t,0x2000> ram{};
    std::vector<Request> requests;
    std::vector<Instruction> instructions;
    unsigned ticks=0,reuses=0,discards=0,flushes=0;
    unsigned latency,gap,remaining=0;
    bool pending=false,hold_output=false;
    uint64_t response=0,fail_address=~uint64_t(0);
    bool response_error=false;
    Instruction held{};
    explicit Memory(unsigned delay,unsigned blocked):latency(delay),gap(blocked) {
        for (unsigned i=0;i<ram.size();i+=2) put16(i,1);
        top.bht_clear=0;top.bht_train=0;top.bht_train_taken=0;top.bht_train_pc=0;top.bht_train_index=0;
        top.ras_valid=0;top.ras_target=0;
        top.clk=0;top.reset=1;top.redirect=0;top.redirect_pc=0;top.ready=0;
        top.req_ready=0;top.rsp_valid=0;top.rsp_data=0;top.rsp_error=0;top.rsp_cause=12;
        top.eval();top.clk=1;top.eval();top.clk=0;top.eval();top.reset=0;
    }
    void put16(unsigned address,unsigned value) {ram.at(address)=uint8_t(value);ram.at(address+1)=uint8_t(value>>8);}
    void put32(unsigned address,uint32_t value) {put16(address,value);put16(address+2,value>>16);}
    bool step() {
        top.clk=0;top.req_ready=!pending && ticks%(gap+1)==0;
        top.rsp_valid=pending && remaining==0;top.rsp_data=response;
        top.rsp_error=response_error;top.rsp_cause=12;top.eval();
        Instruction now{top.pc,top.fault_value,top.fault_cause,top.raw_insn,top.insn,top.bytes,bool(top.fetch_fault),bool(top.illegal),top.predicted_next,bool(top.predicted_return),unsigned(top.predicted_index),bool(top.predicted_dynamic)};
        if (hold_output && !top.redirect) check(top.valid && now.pc==held.pc && now.raw==held.raw && now.expanded==held.expanded &&
            now.bytes==held.bytes && now.fault==held.fault && now.value==held.value && now.cause==held.cause && now.illegal==held.illegal && now.prediction==held.prediction && now.from_ras==held.from_ras && now.index==held.index && now.dynamic==held.dynamic,
            "instruction changed while output stalled");
        hold_output=top.valid && !top.ready && !top.redirect;held=now;
        bool consumed=top.valid && top.ready && !top.redirect;
        if (consumed) instructions.push_back(now);
        bool accept=top.req_valid && top.req_ready;
        bool returned=top.rsp_valid && top.rsp_ready;
        Request request{top.req_addr,top.req_size};
        reuses+=top.reuse_event;discards+=top.discard_event;flushes+=top.buffer_flush_event;
        top.clk=1;top.eval();++ticks;
        if (returned) pending=false;
        if (accept) {
            check(!pending,"multiple outstanding fetches");requests.push_back(request);
            response=0;response_error=request.address==fail_address;
            for (unsigned i=0;i<(1u<<request.size);++i) response|=uint64_t(ram.at(size_t(request.address)+i))<<(i*8);
            pending=true;remaining=latency-1;
        } else if (pending && remaining>0) --remaining;
        return consumed;
    }
    void collect(unsigned count) {
        for (unsigned i=0;i<10000 && instructions.size()<count;++i) {
            // Force instruction backpressure independently of memory backpressure.
            top.ready=ticks%11>=4;step();
        }
        check(instructions.size()==count,"instruction collection timeout");
    }
    void redirect(uint64_t target) {top.redirect_pc=target;top.redirect=1;step();top.redirect=0;instructions.clear();}
};

int main() {
    try {
        unsigned checks=0;
        for (auto config:std::array<std::array<unsigned,2>,3>{{{{1,0}},{{5,3}},{{20,7}}}}) {
            auto verify=[&](const Instruction& i,uint64_t pc,uint32_t raw,uint32_t expanded,unsigned bytes) {
                check(!i.fault && !i.illegal && i.pc==pc && i.raw==raw && i.expanded==expanded && i.bytes==bytes,"wrong instruction assembly");++checks;
            };
            {
                Memory m(config[0],config[1]);m.collect(8);
                for (unsigned i=0;i<8;++i) verify(m.instructions[i],i*2,1,0x13,2);
                unsigned count=0;for (auto r:m.requests) if (r.address<16) {
                    check(r.address%4==0 && r.size==2,"compressed upper half fetched twice");++count;
                }
                check(count==4 && m.reuses==4,"missing compressed reuse");++checks;
            }
            {
                Memory m(config[0],config[1]);
                for (unsigned i=0;i<4;++i) m.put32(2+i*4,0x00150513+i*0x100000);
                m.collect(6);verify(m.instructions[0],0,1,0x13,2);
                for (unsigned i=0;i<4;++i) verify(m.instructions[i+1],2+i*4,0x00150513+i*0x100000,0x00150513+i*0x100000,4);
                verify(m.instructions[5],18,1,0x13,2);
                for (auto r:m.requests) check(r.address%4==0 && r.size==2,"unaligned chain re-read a saved halfword");++checks;
            }
            for (bool fault: {false,true}) {
                Memory m(config[0],config[1]);m.put32(0xffe,0x02a00513);
                if (fault) m.fail_address=0x1000;
                m.redirect(0xffc);m.collect(fault ? 2 : 3);
                verify(m.instructions[0],0xffc,1,0x13,2);
                check(m.requests[0].address==0xffc && m.requests[0].size==2 &&
                      m.requests[1].address==0x1000 && m.requests[1].size==2,"cross-page fetch was not separately requested");++checks;
                if (fault) {
                    auto i=m.instructions[1];check(i.fault && i.pc==0xffe && i.cause==12 && i.value==0x1000 && i.bytes==4,"wrong cross-page fault attribution");++checks;
                } else {
                    verify(m.instructions[1],0xffe,0x02a00513,0x02a00513,4);
                    verify(m.instructions[2],0x1002,1,0x13,2);
                }
            }
            {
                Memory m(config[0],config[1]);m.put16(2,0x4509);m.top.ready=0;
                for (unsigned i=0;i<1000 && !m.top.valid;++i) m.step();
                check(m.top.valid,"failed to fill first instruction");
                m.put16(2,0x450d);m.redirect(2);m.collect(1);
                verify(m.instructions[0],2,0x450d,0x00300513,2);
                check(m.flushes==1,"redirect did not invalidate saved halfword");++checks;
            }
            {
                Memory m(config[0],config[1]);m.put16(0x40,0x451d);
                for (unsigned i=0;i<100 && !m.pending;++i) m.step();
                check(m.pending,"no fetch to redirect");m.redirect(0x40);m.collect(2);
                verify(m.instructions[0],0x40,0x451d,0x00700513,2);
                verify(m.instructions[1],0x42,1,0x13,2);
                check(m.discards==1,"redirected response was not discarded exactly once");++checks;
            }
        }
        std::cout<<"FETCH UNIT PASS: "<<checks<<" checks across 3 memory/output backpressure configurations\n";
        return 0;
    } catch (const std::exception& e) {std::cerr<<e.what()<<'\n';return 1;}
}
