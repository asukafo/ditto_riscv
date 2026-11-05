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
    reg [7:0] replacement;
    wire [7:0] lookup_match,fill_match,first_duplicate,first_free;
    wire unused_offsets=^{lookup_vaddr[63:39],lookup_vaddr[11:0],fill_vaddr[63:39],fill_vaddr[11:0]};
    for(genvar i=0;i<8;i=i+1) begin: entry
        assign lookup_match[i]=ENABLED!=0 && !invalidate && valid[i] &&
            vpns[i]==lookup_vaddr[38:12] && contexts[i]==lookup_context;
        assign fill_match[i]=valid[i] && vpns[i]==fill_vaddr[38:12] && contexts[i]==fill_context;
        if(i==0) begin: first_entry
            assign first_duplicate[i]=fill_match[i];
            assign first_free[i]=!valid[i];
        end else begin: later_entry
            assign first_duplicate[i]=fill_match[i] && !(|fill_match[i-1:0]);
            assign first_free[i]=!valid[i] && (&valid[i-1:0]);
        end
    end
    wire duplicate=|fill_match;
    wire [7:0] destination=duplicate ? first_duplicate : (&valid) ? replacement : first_free;
    // Filling an existing VPN/context updates it in place, so lookups are one-hot.
    always @* begin
        hit=|lookup_match;ppn=0;flags=0;
        for(integer i=0;i<8;i=i+1) begin
            ppn=ppn | ({44{lookup_match[i]}} & ppns[i]);
            flags=flags | ({8{lookup_match[i]}} & permissions[i]);
        end
    end
    assign hit_event=lookup_valid && hit;
    assign miss_event=ENABLED!=0 && lookup_valid && !hit;
    assign fill_event=ENABLED!=0 && fill_valid && !reset && !invalidate;
    always @(posedge clk) begin
        if(reset || invalidate || ENABLED==0) begin
            valid<=0;replacement<=8'b00000001;
        end else if(fill_valid) begin
            valid<=valid | destination;
            if(!duplicate) replacement<={destination[6:0],destination[7]};
            for(integer i=0;i<8;i=i+1) if(destination[i]) begin
                vpns[i]<=fill_vaddr[38:12];contexts[i]<=fill_context;
                ppns[i]<=fill_ppn;permissions[i]<=fill_flags;
            end
        end
    end
endmodule
