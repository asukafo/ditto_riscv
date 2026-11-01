module rv64_regfile (
    input wire clk, reset, write_enable,
    input wire [4:0] rs1, rs2, rd,
    input wire [63:0] write_data,
    output wire [63:0] a, b, debug_t3
);
    reg [63:0] regs [0:31];
    integer i;
    assign a=rs1==0 ? 64'd0 : regs[rs1];
    assign b=rs2==0 ? 64'd0 : regs[rs2];
    assign debug_t3=regs[28];
    always @(posedge clk) begin
        if (reset) for (i=0;i<32;i=i+1) regs[i]<=0;
        else if (write_enable && rd!=0) regs[rd]<=write_data;
    end
endmodule
