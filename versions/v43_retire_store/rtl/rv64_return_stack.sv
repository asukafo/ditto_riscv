// Eight committed return addresses. No speculative updates or rollback state.
// JAL/JALR x1/x5 push/pop hints follow the unprivileged ISA's RAS hint table.
module rv64_return_stack #(parameter ENABLED=1) (
    input wire clk,reset,clear,retire,input wire [31:0] insn,
    input wire [63:0] pc,input wire [2:0] bytes,
    output wire valid,output wire [63:0] target,
    output wire push_event,pop_event,overflow_event,underflow_event,
    output wire [3:0] occupancy
);
    reg [63:0] entries [0:7];
    reg [3:0] count;
    wire unused_immediate=^insn[31:20];
    wire rd_link=insn[11:7]==1 || insn[11:7]==5;
    wire rs_link=insn[19:15]==1 || insn[19:15]==5;
    wire jal=insn[6:0]==7'h6f;
    wire jalr=insn[6:0]==7'h67 && insn[14:12]==0;
    wire push=(jal || jalr) && rd_link;
    wire pop=jalr && rs_link && (!rd_link || insn[11:7]!=insn[19:15]);
    wire update=ENABLED!=0 && retire && !reset && !clear;
    assign valid=ENABLED!=0 && count!=0;
    assign target=count!=0 ? entries[0] : 64'd0;
    assign occupancy=count;
    assign push_event=update && push;
    assign pop_event=update && pop;
    assign overflow_event=push_event && !pop && count==8;
    assign underflow_event=pop_event && count==0;
    always @(posedge clk) begin
        if(reset || clear || ENABLED==0) count<=0;
        else if(update) begin
            if(push && pop) begin
                entries[0]<=pc+{61'd0,bytes};
                if(count==0) count<=1;
            end else if(push) begin
                for(integer i=7;i>0;i=i-1) entries[i]<=entries[i-1];
                entries[0]<=pc+{61'd0,bytes};
                if(count<8) count<=count+1'b1;
            end else if(pop && count!=0) begin
                for(integer i=0;i<7;i=i+1) entries[i]<=entries[i+1];
                count<=count-1'b1;
            end
        end
    end
endmodule
