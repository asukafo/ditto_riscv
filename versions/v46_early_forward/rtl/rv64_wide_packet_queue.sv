// Ordered fall-through packet queue: up to two pushes and two pops each edge.
module rv64_wide_packet_queue #(parameter WIDTH=333, DEPTH=6)(
 input wire clk,reset,flush,input wire [1:0] u_count,output wire [1:0] u_take,
 input wire [WIDTH-1:0] u_packet0,u_packet1,
 output wire d_valid,second_valid,input wire [1:0] pop_count,
 output wire [WIDTH-1:0] d_packet,second_packet,output wire [2:0] occupancy
);
 reg [WIDTH-1:0] entries[0:DEPTH-1];reg [2:0] head,tail,count;
 function automatic [2:0] advance(input [2:0] ptr,input [1:0] n);
  reg [3:0] sum;begin sum={1'b0,ptr}+{2'd0,n};advance=sum>=4'(DEPTH) ? 3'(sum-4'(DEPTH)) : sum[2:0];end
 endfunction
 wire running=!reset && !flush;
 wire [3:0] space=4'(DEPTH)-{1'b0,count}+{2'd0,pop_count};
 assign u_take=!running ? 2'd0 : space>={2'd0,u_count} ? u_count : space[1:0];
 assign d_valid=running && (count!=0 || u_count!=0);
 assign second_valid=running && ({1'b0,count}+{2'd0,u_count})>=2;
 assign d_packet=count!=0 ? entries[head] : u_packet0;
 assign second_packet=count>=2 ? entries[advance(head,1)] : count==1 ? u_packet0 : u_packet1;
 assign occupancy=count;
 wire [1:0] old_pop={1'b0,pop_count}>count ? count[1:0] : pop_count;
 wire [1:0] direct_pop=pop_count-old_pop,stored=u_take-direct_pop;
 integer i;
 always @(posedge clk)begin
  if(reset || flush)begin head<=0;tail<=0;count<=0;for(i=0;i<DEPTH;i=i+1)entries[i]<=0;end
  else begin
   if(stored!=0)entries[tail]<=direct_pop!=0 ? u_packet1 : u_packet0;
   if(stored==2)entries[advance(tail,1)]<=u_packet1;
   head<=advance(head,old_pop);tail<=advance(tail,stored);count<=count+{1'b0,u_take}-{1'b0,pop_count};
  end
 end
endmodule
