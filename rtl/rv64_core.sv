// Educational multi-cycle RV64 integer subset. See docs/architecture.md.
module rv64_core (
    input wire clk, input wire reset,
    output wire req_valid, input wire req_ready,
    output wire [63:0] req_addr, output wire req_write,
    output wire [63:0] req_wdata,
    input wire rsp_valid, output wire rsp_ready,
    input wire [63:0] rsp_rdata, input wire rsp_error,
    output reg halted, output reg [2:0] fault,
    output reg [63:0] cycles, output reg [63:0] instret,
    output reg [63:0] fetch_wait, output reg [63:0] data_wait,
    output reg commit_valid, output reg [63:0] commit_pc,
    output reg [31:0] commit_insn,
    output reg commit_rd_wen, output reg [4:0] commit_rd,
    output reg [63:0] commit_wdata, output reg [63:0] commit_next_pc,
    output reg commit_mem_valid, output reg commit_mem_write,
    output reg [63:0] commit_mem_addr, output reg [63:0] commit_mem_data
);
    localparam [2:0] FETCH_REQ=0, FETCH_RSP=1, EXEC=2,
                     DATA_REQ=3, DATA_RSP=4, STOP=5;
    reg [2:0] state;
    reg [63:0] pc;
    reg [31:0] insn;
    reg [63:0] regs [0:31];
    reg [63:0] mem_addr, mem_wdata;
    reg mem_write;
    reg [4:0] mem_rd;
    wire [4:0] rd = insn[11:7];
    wire [4:0] rs1 = insn[19:15];
    wire [4:0] rs2 = insn[24:20];
    wire [63:0] a = (rs1 == 0) ? 64'd0 : regs[rs1];
    wire [63:0] b = (rs2 == 0) ? 64'd0 : regs[rs2];
    wire [63:0] imm_i = {{52{insn[31]}}, insn[31:20]};
    wire [63:0] imm_s = {{52{insn[31]}}, insn[31:25], insn[11:7]};
    wire [63:0] imm_b = {{51{insn[31]}}, insn[31], insn[7], insn[30:25], insn[11:8], 1'b0};
    wire [63:0] imm_j = {{43{insn[31]}}, insn[31], insn[19:12], insn[20], insn[30:21], 1'b0};
    wire [63:0] effective_addr = a + (insn[6:0] == 7'h23 ? imm_s : imm_i);
    reg legal, write_rd, memory_op, stop_op, branch_taken;
    reg [63:0] result, next_pc;
    integer i;

    assign req_valid = !reset && (state == FETCH_REQ || state == DATA_REQ);
    assign req_addr = (state == FETCH_REQ) ? pc : mem_addr;
    assign req_write = state == DATA_REQ && mem_write;
    assign req_wdata = mem_wdata;
    assign rsp_ready = !reset && (state == FETCH_RSP || state == DATA_RSP);

    // Decode only the documented subset; unsupported encodings fail explicitly.
    always @* begin
        legal=1; write_rd=0; memory_op=0; stop_op=0; branch_taken=0;
        result=0; next_pc=pc+64'd4;
        case (insn[6:0])
            7'h13: begin // RV64 OP-IMM: shift amount is six bits, not five.
                write_rd=1;
                case (insn[14:12])
                    3'b000: result=a+imm_i;
                    3'b010: result=($signed(a)<$signed(imm_i)) ? 64'd1 : 64'd0;
                    3'b011: result=(a<imm_i) ? 64'd1 : 64'd0;
                    3'b100: result=a^imm_i;
                    3'b110: result=a|imm_i;
                    3'b111: result=a&imm_i;
                    3'b001: begin
                        legal=insn[31:26]==6'b000000;
                        result=a<<insn[25:20];
                    end
                    3'b101: begin
                        legal=insn[31:26]==6'b000000 || insn[31:26]==6'b010000;
                        if (insn[30]) result=$signed(a)>>>insn[25:20];
                        else result=a>>insn[25:20];
                    end
                    default: legal=0;
                endcase
            end
            7'h33: begin // RV64 OP: only rs2[5:0] is used as a shift amount.
                write_rd=1;
                legal=insn[31:25]==0;
                case (insn[14:12])
                    3'b000: begin
                        legal=insn[31:25]==0 || insn[31:25]==7'h20;
                        result=insn[30] ? a-b : a+b;
                    end
                    3'b001: result=a<<b[5:0];
                    3'b010: result=($signed(a)<$signed(b)) ? 64'd1 : 64'd0;
                    3'b011: result=(a<b) ? 64'd1 : 64'd0;
                    3'b100: result=a^b;
                    3'b101: begin
                        legal=insn[31:25]==0 || insn[31:25]==7'h20;
                        if (insn[30]) result=$signed(a)>>>b[5:0];
                        else result=a>>b[5:0];
                    end
                    3'b110: result=a|b;
                    3'b111: result=a&b;
                    default: legal=0;
                endcase
            end
            7'h37: begin // LUI, sign extended to XLEN
                write_rd=1; result={{32{insn[31]}}, insn[31:12], 12'b0};
            end
            7'h6f: begin // JAL
                write_rd=1; result=pc+64'd4; next_pc=pc+imm_j;
            end
            7'h63: begin
                case (insn[14:12])
                    3'b000: branch_taken=a==b;
                    3'b001: branch_taken=a!=b;
                    3'b100: branch_taken=$signed(a)<$signed(b);
                    3'b101: branch_taken=$signed(a)>=$signed(b);
                    3'b110: branch_taken=a<b;
                    3'b111: branch_taken=a>=b;
                    default: legal=0;
                endcase
                if (branch_taken) next_pc=pc+imm_b;
            end
            7'h03, 7'h23: begin // aligned LD / SD only
                legal=insn[14:12]==3'b011; memory_op=1;
            end
            7'h73: begin legal=insn==32'h00100073; stop_op=1; end
            default: legal=0;
        endcase
    end

    always @(posedge clk) begin
        if (reset) begin
            state<=FETCH_REQ; pc<=0; insn<=0; halted<=0; fault<=0;
            cycles<=0; instret<=0; fetch_wait<=0; data_wait<=0;
            commit_valid<=0; commit_pc<=0; commit_insn<=0;
            commit_rd_wen<=0; commit_rd<=0; commit_wdata<=0; commit_next_pc<=0;
            commit_mem_valid<=0; commit_mem_write<=0; commit_mem_addr<=0; commit_mem_data<=0;
            mem_addr<=0; mem_wdata<=0; mem_write<=0; mem_rd<=0;
            for (i=0; i<32; i=i+1) regs[i]<=0;
        end else begin
            commit_valid<=0;
            commit_rd_wen<=0; commit_rd<=0; commit_wdata<=0;
            commit_mem_valid<=0; commit_mem_write<=0; commit_mem_addr<=0; commit_mem_data<=0;
            regs[0]<=0;
            if (!halted) cycles<=cycles+1;
            case (state)
                FETCH_REQ: if (req_valid && req_ready) state<=FETCH_RSP;
                FETCH_RSP: begin
                    if (rsp_valid) begin
                        if (rsp_error) begin halted<=1; fault<=3; state<=STOP; end
                        else begin insn<=rsp_rdata[31:0]; state<=EXEC; end
                    end else fetch_wait<=fetch_wait+1;
                end
                EXEC: begin
                    if (!legal) begin halted<=1; fault<=1; state<=STOP; end
                    else if (next_pc[1:0]!=0 || (memory_op && effective_addr[2:0]!=0)) begin
                        halted<=1; fault<=2; state<=STOP;
                    end else if (memory_op) begin
                        mem_addr<=effective_addr; mem_wdata<=b;
                        mem_write<=insn[6:0]==7'h23; mem_rd<=rd; state<=DATA_REQ;
                    end else begin
                        if (write_rd && rd!=0) regs[rd]<=result;
                        pc<=next_pc; instret<=instret+1;
                        commit_valid<=1; commit_pc<=pc; commit_insn<=insn;
                        commit_next_pc<=next_pc;
                        commit_rd_wen<=write_rd && rd!=0;
                        commit_rd<=(write_rd && rd!=0) ? rd : 5'd0;
                        commit_wdata<=(write_rd && rd!=0) ? result : 64'd0;
                        if (stop_op) begin halted<=1; state<=STOP; end
                        else state<=FETCH_REQ;
                    end
                end
                DATA_REQ: if (req_valid && req_ready) state<=DATA_RSP;
                DATA_RSP: begin
                    if (rsp_valid) begin
                        if (rsp_error) begin halted<=1; fault<=3; state<=STOP; end
                        else begin
                            if (!mem_write && mem_rd!=0) regs[mem_rd]<=rsp_rdata;
                            pc<=pc+4; state<=FETCH_REQ; instret<=instret+1;
                            commit_valid<=1; commit_pc<=pc; commit_insn<=insn;
                            commit_next_pc<=pc+4;
                            commit_rd_wen<=!mem_write && mem_rd!=0;
                            commit_rd<=(!mem_write && mem_rd!=0) ? mem_rd : 5'd0;
                            commit_wdata<=(!mem_write && mem_rd!=0) ? rsp_rdata : 64'd0;
                            commit_mem_valid<=1; commit_mem_write<=mem_write;
                            commit_mem_addr<=mem_addr;
                            commit_mem_data<=mem_write ? mem_wdata : rsp_rdata;
                        end
                    end else data_wait<=data_wait+1;
                end
                default: state<=STOP;
            endcase
        end
    end
endmodule
