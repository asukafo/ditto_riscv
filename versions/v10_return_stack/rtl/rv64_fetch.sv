// One complete instruction buffer; outstanding speculative reads are always drained.
// Faults travel with the instruction and only become architectural at commit.
module rv64_fetch # (parameter EXTENSIONS=1, BUFFER_ENABLE=1, PREDICT_ENABLE=1, RAS_ENABLE=1) (
    input wire clk,reset,redirect,
    input wire [63:0] redirect_pc,
    input wire ras_valid,input wire [63:0] ras_target,
    output wire req_valid,input wire req_ready,
    output wire [63:0] req_addr,output wire [1:0] req_size,
    input wire rsp_valid,output wire rsp_ready,
    input wire [63:0] rsp_data,rsp_cause,input wire rsp_error,
    output reg valid,input wire ready,
    output reg [63:0] pc,fault_cause,fault_value,predicted_next,
    output reg [31:0] insn,raw_insn,
    output reg [2:0] bytes,
    output reg illegal,fetch_fault,predicted_return,
    output wire waiting,active,discard_event,reuse_event,buffer_flush_event
);
    localparam [2:0] REQUEST=0,RESPONSE=1,HIGH_REQUEST=2,HIGH_RESPONSE=3,HOLD=4;
    reg [2:0] state;
    reg [63:0] next_pc;
    reg [15:0] low_half;
    reg spare_valid;
    reg [15:0] spare_half;
    reg [63:0] spare_pc;
    reg killed;
    wire [31:0] expanded;
    wire bad_compressed;
    wire unused_response=^rsp_data[63:32];
    wire spare_match=BUFFER_ENABLE!=0 && EXTENSIONS!=0 && spare_valid && spare_pc==next_pc;
    wire [15:0] decode_half=state==REQUEST && spare_match ? spare_half : rsp_data[15:0];
    rv64_decompress decompress(.c(decode_half),.instruction(expanded),.illegal(bad_compressed));
    // A predictor sees a complete expanded instruction; no prediction on a low-half prefix.
    wire reuse_complete=state==REQUEST && spare_match && spare_half[1:0]!=3;
    wire candidate_word=state==HIGH_RESPONSE || EXTENSIONS==0 || rsp_data[1:0]==3;
    wire [31:0] candidate_insn=reuse_complete || !candidate_word ? expanded :
        state==HIGH_RESPONSE ? {rsp_data[15:0],low_half} : rsp_data[31:0];
    wire [2:0] candidate_bytes=reuse_complete || !candidate_word ? 3'd2 : 3'd4;
    wire candidate_illegal=(reuse_complete || !candidate_word) && bad_compressed;
    wire [63:0] candidate_next,static_next;
    wire canonical_return=candidate_insn[6:0]==7'h67 && candidate_insn[14:12]==0 &&
        candidate_insn[11:7]==0 && (candidate_insn[19:15]==1 || candidate_insn[19:15]==5) && candidate_insn[31:20]==0;
    wire ras_aligned=EXTENSIONS!=0 ? !ras_target[0] : ras_target[1:0]==0;
    wire candidate_return=RAS_ENABLE!=0 && PREDICT_ENABLE!=0 && ras_valid && ras_aligned &&
        canonical_return && !candidate_illegal;
    assign candidate_next=candidate_return ? ras_target : static_next;
    rv64_static_predictor #(.ENABLED(PREDICT_ENABLE),.EXTENSIONS(EXTENSIONS)) predictor(
        .pc(next_pc),.insn(candidate_insn),.bytes(candidate_bytes),.legal(!candidate_illegal),.predicted_next(static_next));
    assign req_valid=!reset && !redirect && ((state==REQUEST && (!valid || ready) && !spare_match) || state==HIGH_REQUEST);
    assign req_addr=next_pc+(state==HIGH_REQUEST ? 64'd2 : 64'd0);
    // The high half of an unaligned instruction starts an aligned word. Its
    // unused upper half can seed the following instruction, but a new page
    // always goes through a separate request and permission check.
    assign req_size=EXTENSIONS==0 || (state==REQUEST && next_pc[1:0]==0) ||
        (BUFFER_ENABLE!=0 && state==HIGH_REQUEST) ? 2'd2 : 2'd1;
    assign rsp_ready=state==RESPONSE || state==HIGH_RESPONSE;
    assign waiting=rsp_ready && !rsp_valid;
    assign discard_event=rsp_ready && rsp_valid && (killed || redirect);
    assign reuse_event=!reset && !redirect && state==REQUEST && spare_match && (!valid || ready);
    assign buffer_flush_event=!reset && redirect && spare_valid;
    // Occupancy is registered state, not request gating through branch/CSR logic.
    // HIGH_REQUEST also owns a partially assembled instruction.
    assign active=valid || spare_valid || state==RESPONSE || state==HIGH_REQUEST || state==HIGH_RESPONSE;
    always @(posedge clk) begin
        if (reset) begin
            state<=REQUEST; next_pc<=0; low_half<=0; killed<=0; valid<=0;
            spare_valid<=0; spare_half<=0; spare_pc<=0;
            pc<=0; predicted_next<=0; predicted_return<=0; insn<=0; raw_insn<=0; bytes<=4; illegal<=0;
            fetch_fault<=0; fault_cause<=0; fault_value<=0;
        end else if (redirect) begin
            valid<=0; next_pc<=redirect_pc; low_half<=0; spare_valid<=0;
            // Once accepted by the arbiter, a read cannot be withdrawn.
            if (rsp_ready && !rsp_valid) killed<=1;
            else begin state<=REQUEST; killed<=0; end
        end else begin
            if (valid && ready) valid<=0;
            case (state)
                REQUEST: begin
                    if (reuse_event) begin
                        spare_valid<=0;
                        if (spare_half[1:0]==3) begin
                            low_half<=spare_half; state<=HIGH_REQUEST;
                        end else begin
                            valid<=1; pc<=next_pc; insn<=expanded; raw_insn<={16'd0,spare_half};
                            bytes<=2; illegal<=bad_compressed; fetch_fault<=0; fault_cause<=0; fault_value<=0;
                            next_pc<=candidate_next; predicted_next<=candidate_next; predicted_return<=candidate_return;
                        end
                    end else if (req_valid && req_ready) begin state<=RESPONSE; spare_valid<=0; end
                end
                HIGH_REQUEST: if (req_valid && req_ready) state<=HIGH_RESPONSE;
                RESPONSE,HIGH_RESPONSE: if (rsp_valid) begin
                    if (killed) begin killed<=0; state<=REQUEST; end
                    else if (rsp_error) begin
                        spare_valid<=0; predicted_return<=0; predicted_next<=next_pc+(state==HIGH_RESPONSE || EXTENSIONS==0 ? 64'd4 : 64'd2);
                        valid<=1; state<=HOLD; pc<=next_pc; insn<=0; raw_insn<=0;
                        bytes<=state==HIGH_RESPONSE ? 3'd4 : EXTENSIONS!=0 ? 3'd2 : 3'd4;
                        illegal<=0; fetch_fault<=1; fault_cause<=rsp_cause;
                        fault_value<=next_pc+(state==HIGH_RESPONSE ? 64'd2 : 64'd0);
                    end else if (state==RESPONSE && EXTENSIONS!=0 && rsp_data[1:0]==3 && next_pc[1:0]!=0) begin
                        low_half<=rsp_data[15:0]; state<=HIGH_REQUEST;
                    end else begin
                        valid<=1; state<=REQUEST; pc<=next_pc; spare_valid<=0; fetch_fault<=0; fault_cause<=0; fault_value<=0;
                        if (state==HIGH_RESPONSE || (EXTENSIONS!=0 && rsp_data[1:0]==3)) begin
                            insn<=state==HIGH_RESPONSE ? {rsp_data[15:0],low_half} : rsp_data[31:0];
                            raw_insn<=state==HIGH_RESPONSE ? {rsp_data[15:0],low_half} : rsp_data[31:0];
                            bytes<=4; illegal<=0; next_pc<=candidate_next; predicted_next<=candidate_next; predicted_return<=candidate_return;
                            if (BUFFER_ENABLE!=0 && EXTENSIONS!=0 && state==HIGH_RESPONSE && candidate_next==next_pc+4) begin
                                spare_valid<=1; spare_half<=rsp_data[31:16]; spare_pc<=next_pc+4;
                            end
                        end else begin
                            insn<=EXTENSIONS!=0 ? expanded : rsp_data[31:0];
                            raw_insn<=EXTENSIONS!=0 ? {16'd0,rsp_data[15:0]} : rsp_data[31:0];
                            bytes<=EXTENSIONS!=0 ? 3'd2 : 3'd4;
                            illegal<=EXTENSIONS!=0 && bad_compressed;
                            next_pc<=candidate_next; predicted_next<=candidate_next; predicted_return<=candidate_return;
                            if (BUFFER_ENABLE!=0 && EXTENSIONS!=0 && next_pc[1:0]==0 && candidate_next==next_pc+2) begin
                                spare_valid<=1; spare_half<=rsp_data[31:16]; spare_pc<=next_pc+2;
                            end
                        end
                    end
                end
                HOLD: if (valid && ready) state<=REQUEST;
                default: state<=REQUEST;
            endcase
        end
    end
endmodule
