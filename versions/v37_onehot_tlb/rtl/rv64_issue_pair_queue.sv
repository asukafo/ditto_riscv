// Registered two-packet lookahead. Scalar bypass restores the parent datapath.
module rv64_issue_pair_queue #(parameter ENABLED=1, WIDTH=333)(
 input wire clk,reset,flush,u_valid,output wire u_ready,input wire [WIDTH-1:0] u_packet,
 output wire d_valid,second_valid,input wire [1:0] pop_count,
 output wire [WIDTH-1:0] d_packet,second_packet,output wire [1:0] occupancy
);
 reg [WIDTH-1:0] entries[0:1];reg head,tail;reg [1:0] count;
 wire running=!reset && !flush;
 assign u_ready=running && (ENABLED==0 ? pop_count!=0 : count<2 || pop_count!=0);
 assign d_valid=running && (ENABLED==0 ? u_valid : count!=0 || u_valid);
 assign d_packet=ENABLED==0 || count==0 ? u_packet : entries[head];
 assign second_valid=running && ENABLED!=0 && (count==2 || (count==1 && u_valid));
 assign second_packet=count==2 ? entries[!head] : u_packet;assign occupancy=ENABLED==0 ? 2'd0 : count;
 wire push=u_valid && u_ready && !((count==0 && pop_count!=0) || (count==1 && pop_count==2));
 wire [1:0] stored_pop=pop_count>count ? count : pop_count;
 always @(posedge clk)begin
  if(reset || flush || ENABLED==0)begin head<=0;tail<=0;count<=0;entries[0]<=0;entries[1]<=0;end
  else begin
   if(push)begin entries[tail]<=u_packet;tail<=!tail;end
   if(stored_pop[0])head<=!head;
   count<=count+2'(push)-stored_pop;
  end
 end
endmodule
