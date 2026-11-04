module rv64_regfile (
    input wire clk, reset, write_enable,write2_enable,
    input wire [4:0] rs1, rs2, rd,rs3,rs4,rd2,
    input wire [63:0] write_data,write2_data,
    output wire [63:0] a, b,c,d, debug_t3
);
    reg [63:0] regs [0:31];
    integer i;
    assign a=rs1==0 ? 64'd0 : regs[rs1];
    assign b=rs2==0 ? 64'd0 : regs[rs2];
    assign c=rs3==0 ? 64'd0 : regs[rs3];
    assign d=rs4==0 ? 64'd0 : regs[rs4];
    assign debug_t3=regs[28];
    always @(posedge clk) begin
        if (reset) for (i=0;i<32;i=i+1) regs[i]<=0;
        else begin
            if (write_enable && rd!=0) regs[rd]<=write_data;
            if (write2_enable && rd2!=0) regs[rd2]<=write2_data;
        end
    end
endmodule
