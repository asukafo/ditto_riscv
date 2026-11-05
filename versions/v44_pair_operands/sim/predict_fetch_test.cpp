#define main legacy_fetch_test_main
#include "fetch_test.cpp"
#undef main
int main(){try{unsigned checks=0;
    for(auto cfg:std::array<std::array<unsigned,2>,3>{{{{1,0}},{{5,3}},{{20,7}}}}){
        // Compressed C.J in the low half must discard the sequential high half.
        Memory low(cfg[0],cfg[1]);low.put16(0,0xa011);low.put16(2,0x451d);low.put16(4,0x4509);low.collect(2);
        check(low.instructions[0].pc==0 && low.instructions[0].prediction==4 && low.instructions[1].pc==4,"low-half compressed jump reused wrong half");++checks;
        // The same jump can come from the saved upper half.
        Memory high(cfg[0],cfg[1]);high.put16(2,0xa011);high.put16(4,0x451d);high.put16(6,0x4509);high.collect(3);
        check(high.instructions[1].pc==2 && high.instructions[1].prediction==6 && high.instructions[2].pc==6,"saved compressed jump prediction wrong");++checks;
        // Halfword-aligned JAL crosses a word; predict only after assembling all 32 bits.
        Memory word(cfg[0],cfg[1]);word.put32(2,0x0080006f);word.put16(10,0x4509);word.collect(3);
        check(word.instructions[1].pc==2 && word.instructions[1].prediction==10 && word.instructions[2].pc==10,"assembled JAL target wrong");++checks;
        // A predicted wrong target response must still drain after EX redirect.
        Memory killed(cfg[0],cfg[1]);killed.put32(0,0x0400006f);killed.put16(0x80,0x451d);killed.top.ready=1;
        for(unsigned i=0;i<1000 && !(killed.pending && killed.requests.back().address==0x40);++i)killed.step();
        check(killed.pending && killed.requests.back().address==0x40,"predicted target not requested");
        killed.redirect(0x80);killed.collect(1);
        check(killed.instructions[0].pc==0x80 && killed.discards==1,"wrong target response survived redirect");++checks;
        // A target on the next page faults separately; its metadata carries that target PC.
        Memory fault(cfg[0],cfg[1]);fault.put32(0,0x0000106f);fault.fail_address=0x1000;fault.collect(2);
        check(fault.instructions[0].prediction==0x1000 && fault.instructions[1].fault && fault.instructions[1].pc==0x1000,"predicted target fault attribution wrong");++checks;
    }
    std::cout<<"PREDICT FETCH UNIT PASS: "<<checks<<" checks with memory/output backpressure\n";return 0;
}catch(const std::exception& e){std::cerr<<e.what()<<'\n';return 1;}}
