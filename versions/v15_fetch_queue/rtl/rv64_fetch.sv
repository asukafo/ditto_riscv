// One complete instruction buffer; outstanding speculative reads are always drained.
// Faults travel with the instruction and only become architectural at commit.
module rv64_fetch # (parameter EXTENSIONS=1, BUFFER_ENABLE=1, PREDICT_ENABLE=1, RAS_ENABLE=1, BHT_ENABLE=1, GSHARE_ENABLE=1, BTB_ENABLE=1) (
    input wire clk,reset,redirect,
    input wire [63:0] redirect_pc,
    input wire ras_valid,input wire [63:0] ras_target,
    input wire btb_train,input wire [63:0] btb_train_pc,btb_train_next,
    input wire [31:0] btb_train_insn,input wire [2:0] btb_train_bytes,
    output reg predicted_btb,
    output wire btb_lookup_event,btb_hit_event,btb_reject_event,
    output wire [63:0] btb_lookup_pc,
    input wire bht_clear,bht_train,bht_train_taken,
    input wire [63:0] bht_train_pc,
    input wire [4:0] bht_train_index,
    output reg [4:0] predicted_index,
    output wire [3:0] global_history,
    output reg predicted_dynamic,
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
    wire [63:0] candidate_next,static_next,decoded_prediction;
    wire canonical_return=candidate_insn[6:0]==7'h67 && candidate_insn[14:12]==0 &&
        candidate_insn[11:7]==0 && (candidate_insn[19:15]==1 || candidate_insn[19:15]==5) && candidate_insn[31:20]==0;
    wire ras_aligned=EXTENSIONS!=0 ? !ras_target[0] : ras_target[1:0]==0;
    wire candidate_return=RAS_ENABLE!=0 && PREDICT_ENABLE!=0 && ras_valid && ras_aligned &&
        canonical_return && !candidate_illegal;
    wire bht_hit,bht_taken;
    wire [4:0] lookup_index;
    wire [63:0] branch_offset={{51{candidate_insn[31]}},candidate_insn[31],candidate_insn[7],candidate_insn[30:25],candidate_insn[11:8],1'b0};
    wire [63:0] branch_target=next_pc+branch_offset;
    wire branch_aligned=EXTENSIONS!=0 ? !branch_target[0] : branch_target[1:0]==0;
    wire candidate_dynamic=PREDICT_ENABLE!=0 && BHT_ENABLE!=0 && bht_hit && !candidate_illegal &&
        candidate_insn[6:0]==7'h63 && (candidate_insn[14:12]<=1 || candidate_insn[14:12]>=4) && branch_aligned;
    wire [63:0] branch_next=bht_taken ? branch_target : next_pc+{61'd0,candidate_bytes};
    rv64_bht #(.ENABLED(BHT_ENABLE!=0 && PREDICT_ENABLE!=0),.GSHARE_ENABLE(GSHARE_ENABLE)) history(
        .clk(clk),.reset(reset),.clear(bht_clear),.lookup_pc(next_pc),.hit(bht_hit),.taken(bht_taken),
        .lookup_index(lookup_index),.global_history(global_history),.train_index(bht_train_index),
        .train(bht_train),.train_pc(bht_train_pc),.train_taken(bht_train_taken));
    assign decoded_prediction=candidate_return ? ras_target : candidate_dynamic ? branch_next : static_next;
    wire table_hit,table_backward;
    wire [2:0] table_kind,table_bytes;
    wire [63:0] table_target;
    wire [2:0] candidate_kind=candidate_insn[6:0]==7'h63 && (candidate_insn[14:12]<=1 || candidate_insn[14:12]>=4) ? 3'd1 :
        candidate_insn[6:0]==7'h6f ? 3'd2 : candidate_insn[6:0]==7'h67 && candidate_insn[14:12]==0 ? (canonical_return ? 3'd3 : 3'd4) : 3'd0;
    wire [63:0] jump_offset={{43{candidate_insn[31]}},candidate_insn[31],candidate_insn[19:12],candidate_insn[20],candidate_insn[30:21],1'b0};
    wire table_ras=table_kind==3 && RAS_ENABLE!=0 && ras_valid && ras_aligned;
    wire table_dynamic=table_kind==1 && BHT_ENABLE!=0 && bht_hit;
    wire table_taken=table_dynamic ? bht_taken : table_backward;
    wire [63:0] table_next=table_kind==1 ? (table_taken ? table_target : next_pc+{61'd0,table_bytes}) : table_ras ? ras_target : table_target;
    reg early_hit,early_dynamic,early_return;
    reg [2:0] early_kind,early_bytes;
    reg [4:0] early_index;
    reg [63:0] early_next,early_target;
    wire live=reuse_complete;
    wire prediction_hit=live ? table_hit : early_hit;
    wire [2:0] prediction_kind=live ? table_kind : early_kind,prediction_bytes=live ? table_bytes : early_bytes;
    wire [63:0] prediction_target=live ? table_target : early_target;
    wire [63:0] prediction_next=live ? table_next : early_next;
    wire prediction_dynamic=live ? table_dynamic : early_dynamic,prediction_return=live ? table_ras : early_return;
    wire [4:0] prediction_index=live ? lookup_index : early_index;
    wire prediction_aligned=EXTENSIONS!=0 ? !prediction_next[0] : prediction_next[1:0]==0;
    // Check type, instruction length and direct target after the bytes arrive.
    // A changing indirect target is resolved by X, using this saved prediction.
    wire candidate_btb=prediction_hit && !candidate_illegal && prediction_kind!=0 &&
        prediction_kind==candidate_kind && prediction_bytes==candidate_bytes && prediction_aligned &&
        (prediction_kind!=1 || prediction_target==branch_target) &&
        (prediction_kind!=2 || prediction_target==next_pc+jump_offset);
    // The blocking interface has not issued the successor yet. Refresh branch
    // direction and RAS at decode instead of paying for stale request-time history.
    wire refine_branch=candidate_btb && prediction_kind==1;
    wire refine_return=candidate_btb && prediction_kind==3 && candidate_return;
    wire packet_dynamic=refine_branch ? candidate_dynamic : candidate_btb ? prediction_dynamic : candidate_dynamic;
    wire packet_return=refine_return ? candidate_return : candidate_btb ? prediction_return : candidate_return;
    wire [4:0] packet_index=refine_branch ? lookup_index : candidate_btb ? prediction_index : lookup_index;
    assign candidate_next=refine_branch || refine_return ? decoded_prediction : candidate_btb ? prediction_next : decoded_prediction;
    assign btb_lookup_pc=next_pc;
    assign btb_lookup_event=BTB_ENABLE!=0 && PREDICT_ENABLE!=0 && !reset && !redirect &&
        ((state==REQUEST && req_valid && req_ready) || reuse_event);
    assign btb_hit_event=btb_lookup_event && table_hit;
    wire complete=!reset && !redirect && (reuse_complete && reuse_event ||
        ((state==RESPONSE || state==HIGH_RESPONSE) && rsp_valid && !rsp_error && !killed &&
         !(state==RESPONSE && EXTENSIONS!=0 && rsp_data[1:0]==3 && next_pc[1:0]!=0)));
    assign btb_reject_event=complete && prediction_hit && !candidate_btb;
    rv64_btb #(.ENABLED(BTB_ENABLE!=0 && PREDICT_ENABLE!=0)) target_table(
        .clk(clk),.reset(reset),.clear(bht_clear),.lookup_pc(next_pc),.hit(table_hit),.kind(table_kind),.bytes(table_bytes),
        .target(table_target),.backward(table_backward),.train(btb_train),.train_pc(btb_train_pc),.train_insn(btb_train_insn),
        .train_bytes(btb_train_bytes),.train_next(btb_train_next));
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
            pc<=0; predicted_next<=0; predicted_return<=0; predicted_dynamic<=0; predicted_index<=0; insn<=0; raw_insn<=0; bytes<=4; illegal<=0;
            fetch_fault<=0; fault_cause<=0; fault_value<=0;
            predicted_btb<=0; early_hit<=0; early_dynamic<=0; early_return<=0; early_kind<=0; early_bytes<=0; early_index<=0; early_next<=0; early_target<=0;
        end else if (redirect) begin
            valid<=0; next_pc<=redirect_pc; low_half<=0; spare_valid<=0;
            // Once accepted by the arbiter, a read cannot be withdrawn.
            if (rsp_ready && !rsp_valid) killed<=1;
            else begin state<=REQUEST; killed<=0; end
        end else begin
            if (btb_lookup_event) begin
                early_hit<=table_hit; early_kind<=table_kind; early_bytes<=table_bytes; early_target<=table_target;
                early_next<=table_next; early_index<=lookup_index; early_dynamic<=table_dynamic; early_return<=table_ras;
            end
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
                            next_pc<=candidate_next; predicted_next<=candidate_next; predicted_return<=packet_return; predicted_dynamic<=packet_dynamic; predicted_index<=packet_index; predicted_btb<=candidate_btb;
                        end
                    end else if (req_valid && req_ready) begin state<=RESPONSE; spare_valid<=0; end
                end
                HIGH_REQUEST: if (req_valid && req_ready) state<=HIGH_RESPONSE;
                RESPONSE,HIGH_RESPONSE: if (rsp_valid) begin
                    if (killed) begin killed<=0; state<=REQUEST; end
                    else if (rsp_error) begin
                        spare_valid<=0; predicted_btb<=0; predicted_return<=0; predicted_dynamic<=0; predicted_index<=0; predicted_next<=next_pc+(state==HIGH_RESPONSE || EXTENSIONS==0 ? 64'd4 : 64'd2);
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
                            bytes<=4; illegal<=0; next_pc<=candidate_next; predicted_next<=candidate_next; predicted_return<=packet_return; predicted_dynamic<=packet_dynamic; predicted_index<=packet_index; predicted_btb<=candidate_btb;
                            if (BUFFER_ENABLE!=0 && EXTENSIONS!=0 && state==HIGH_RESPONSE && candidate_next==next_pc+4) begin
                                spare_valid<=1; spare_half<=rsp_data[31:16]; spare_pc<=next_pc+4;
                            end
                        end else begin
                            insn<=EXTENSIONS!=0 ? expanded : rsp_data[31:0];
                            raw_insn<=EXTENSIONS!=0 ? {16'd0,rsp_data[15:0]} : rsp_data[31:0];
                            bytes<=EXTENSIONS!=0 ? 3'd2 : 3'd4;
                            illegal<=EXTENSIONS!=0 && bad_compressed;
                            next_pc<=candidate_next; predicted_next<=candidate_next; predicted_return<=packet_return; predicted_dynamic<=packet_dynamic; predicted_index<=packet_index; predicted_btb<=candidate_btb;
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
