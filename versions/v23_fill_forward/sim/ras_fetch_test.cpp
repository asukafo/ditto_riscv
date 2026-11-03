#define main legacy_fetch_test_main
#include "fetch_test.cpp"
#undef main
int main(){try{unsigned checks=0;
    for(auto cfg:std::array<std::array<unsigned,2>,3>{{{{1,0}},{{5,3}},{{20,7}}}}){
        for(uint32_t ret:{0x00008067u,0x00028067u}){
            Memory m(cfg[0],cfg[1]);m.put32(0,ret);m.top.ras_valid=1;m.top.ras_target=0x80;m.top.ready=0;
            for(unsigned i=0;i<1000&&!m.top.valid;++i)m.step();
            check(m.top.valid&&m.top.predicted_return&&m.top.predicted_next==0x80,"return not predicted from RAS");++checks;
            m.top.ras_target=0x100;m.top.ras_valid=0;
            for(unsigned i=0;i<20;++i)m.step();
            m.collect(2);check(m.instructions[0].prediction==0x80&&m.instructions[0].from_ras&&m.instructions[1].pc==0x80,"RAS update changed a held prediction");++checks;
        }
        for(uint32_t ins:{0x00408067u,0x000080e7u,0x00010067u}){
            Memory m(cfg[0],cfg[1]);m.put32(0,ins);m.top.ras_valid=1;m.top.ras_target=0x80;m.collect(1);
            check(!m.instructions[0].from_ras&&m.instructions[0].prediction==4,"noncanonical return incorrectly used RAS");++checks;
        }
        Memory empty(cfg[0],cfg[1]);empty.put32(0,0x8067);empty.collect(1);
        check(!empty.instructions[0].from_ras&&empty.instructions[0].prediction==4,"empty RAS did not fall back");++checks;
        Memory compressed(cfg[0],cfg[1]);compressed.put16(0,0x8082);compressed.top.ras_valid=1;compressed.top.ras_target=0x80;compressed.collect(2);
        check(compressed.instructions[0].from_ras&&compressed.instructions[0].bytes==2&&compressed.instructions[1].pc==0x80,"compressed return prediction wrong");++checks;
    }
    std::cout<<"RAS FETCH UNIT PASS: "<<checks<<" checks with memory/output backpressure\n";return 0;
}catch(const std::exception& e){std::cerr<<e.what()<<'\n';return 1;}}
