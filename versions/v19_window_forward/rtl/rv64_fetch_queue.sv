// Four complete packets, empty fall-through, one producer and one consumer.
// The fetcher's existing output register is separate from these four slots.
module rv64_fetch_queue #(parameter ENABLED=1, WIDTH=333) (
    input wire clk,reset,flush,
    input wire u_valid,output wire u_ready,input wire [WIDTH-1:0] u_packet,
    output wire d_valid,input wire d_ready,output wire [WIDTH-1:0] d_packet,
    output wire [2:0] occupancy,
    output wire push_event,pop_event,bypass_event,full_stall,flush_event
);
    reg [WIDTH-1:0] entries [0:3];
    reg [1:0] head,tail;
    reg [2:0] count;
    wire running=!reset && !flush;
    assign u_ready=running && (ENABLED==0 ? d_ready : count<4 || d_ready);
    assign d_valid=running && (ENABLED==0 ? u_valid : count!=0 || u_valid);
    assign d_packet=ENABLED!=0 && count!=0 ? entries[head] : u_packet;
    assign occupancy=ENABLED!=0 ? count : 3'd0;
    assign push_event=ENABLED!=0 && u_valid && u_ready && !(count==0 && d_ready);
    assign pop_event=ENABLED!=0 && running && count!=0 && d_ready;
    assign bypass_event=ENABLED!=0 && running && count==0 && u_valid && d_ready;
    assign full_stall=ENABLED!=0 && running && count==4 && u_valid && !d_ready;
    assign flush_event=ENABLED!=0 && !reset && flush && count!=0;
    integer i;
    always @(posedge clk) begin
        if (reset || flush || ENABLED==0) begin
            head<=0;tail<=0;count<=0;
            for(i=0;i<4;i=i+1)entries[i]<=0;
        end else begin
            if(push_event)begin entries[tail]<=u_packet;tail<=tail+1'b1;end
            if(pop_event)head<=head+1'b1;
            case({push_event,pop_event})
                2'b10:count<=count+1'b1;
                2'b01:count<=count-1'b1;
                default:;
            endcase
        end
    end
endmodule
