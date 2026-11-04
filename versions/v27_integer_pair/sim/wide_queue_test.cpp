#include "Vrv64_wide_packet_queue.h"
#include "verilated.h"
#include <deque>
#include <random>
#include <stdexcept>
#include <iostream>
int main(){Vrv64_wide_packet_queue d;std::deque<unsigned> q;std::mt19937 r(25);unsigned seq=1,full=0,partial=0,dual=0;auto ck=[](bool v){if(!v)throw std::runtime_error("wide queue mismatch");};
for(unsigned n=0;n<50000;n++){d.clk=0;d.reset=n==0;d.flush=n>0&&r()%71==0;d.u_count=r()%3;d.u_packet0=seq;d.u_packet1=seq+1;d.pop_count=(d.reset||d.flush)?0:r()%(std::min<size_t>(2,q.size()+d.u_count)+1);d.eval();bool run=!d.reset&&!d.flush;unsigned take=run?std::min<unsigned>(d.u_count,6-q.size()+d.pop_count):0;ck(d.occupancy==q.size());ck(d.u_take==take);ck(bool(d.d_valid)==(run&&(!q.empty()||d.u_count)));ck(bool(d.second_valid)==(run&&q.size()+d.u_count>=2));if(d.d_valid)ck(d.d_packet==(q.empty()?seq:q[0]));if(d.second_valid)ck(d.second_packet==(q.size()>=2?q[1]:q.size()==1?seq:seq+1));full+=q.size()==6&&take==2&&d.pop_count==2;partial+=take==1&&d.u_count==2;dual+=take==2;
if(!run)q.clear();else{for(unsigned j=0;j<take;j++)q.push_back(seq+j);for(unsigned j=0;j<d.pop_count;j++)q.pop_front();}seq+=take;d.clk=1;d.eval();ck(d.occupancy==q.size());}
ck(full&&partial&&dual);std::cout<<"WIDE QUEUE PASS: 50000 cycles, full pop2/push2="<<full<<", partial="<<partial<<", push2="<<dual<<"\n";}
