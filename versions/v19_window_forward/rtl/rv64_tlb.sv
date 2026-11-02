// Eight fully associative 4 KiB translations. Full satp context tags avoid ASID/root aliasing.
// Global PTEs are conservatively context-tagged too. Invalidation is always full flush.
module rv64_tlb #(parameter ENABLED=1) (
    input wire clk,reset,invalidate,lookup_valid,
    input wire [63:0] lookup_vaddr,lookup_context,
    output reg hit,output reg [43:0] ppn,output reg [7:0] flags,
    input wire fill_valid,input wire [63:0] fill_vaddr,fill_context,
    input wire [43:0] fill_ppn,input wire [7:0] fill_flags,
    output wire hit_event,miss_event,fill_event
);
    reg [7:0] valid;
    reg [26:0] vpns [0:7];
    reg [63:0] contexts [0:7];
    reg [43:0] ppns [0:7];
    reg [7:0] permissions [0:7];
    reg [2:0] replacement;
    reg [2:0] destination;
    reg duplicate,free_slot;
    wire unused_offsets=^{lookup_vaddr[63:39],lookup_vaddr[11:0],fill_vaddr[63:39],fill_vaddr[11:0]};
    always @* begin
        hit=0;ppn=0;flags=0;
        for(integer i=0;i<8;i=i+1)
            if(ENABLED!=0 && !invalidate && valid[i] && vpns[i]==lookup_vaddr[38:12] && contexts[i]==lookup_context) begin
                hit=1;ppn=ppns[i];flags=permissions[i];
            end
        destination=replacement;duplicate=0;free_slot=0;
        for(integer i=0;i<8;i=i+1) begin
            if(!duplicate && valid[i] && vpns[i]==fill_vaddr[38:12] && contexts[i]==fill_context) begin destination=3'(i);duplicate=1;end
        end
        if(!duplicate) for(integer i=0;i<8;i=i+1)
            if(!free_slot && !valid[i]) begin destination=3'(i);free_slot=1;end
    end
    assign hit_event=lookup_valid && hit;
    assign miss_event=ENABLED!=0 && lookup_valid && !hit;
    assign fill_event=ENABLED!=0 && fill_valid && !reset && !invalidate;
    always @(posedge clk) begin
        if(reset || invalidate || ENABLED==0) begin valid<=0;replacement<=0;end
        else if(fill_valid) begin
            valid[destination]<=1;vpns[destination]<=fill_vaddr[38:12];contexts[destination]<=fill_context;
            ppns[destination]<=fill_ppn;permissions[destination]<=fill_flags;
            if(!duplicate) replacement<=destination+1'b1;
        end
    end
endmodule
