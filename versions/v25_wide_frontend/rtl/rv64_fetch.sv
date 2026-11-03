// One complete instruction buffer; outstanding speculative reads are always drained.
// Faults travel with the instruction and only become architectural at commit.
module rv64_fetch # (parameter EXTENSIONS=1, BUFFER_ENABLE=1, PREDICT_ENABLE=1, RAS_ENABLE=1, BHT_ENABLE=1, GSHARE_ENABLE=1, BTB_ENABLE=1, I_PIPELINE=0, WIDE_FETCH=0) (
    input wire clk,reset,redirect,
    input wire [1:0] ready_slots,output reg second_valid,output reg [332:0] second_packet,output wire decode_pair_event,
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
    reg [63:0] spare_data;reg [3:0] spare_count;reg [1:0] request_size;
    wire [15:0] spare_half=spare_data[15:0];
    reg [63:0] spare_pc;
    reg killed;
    wire [31:0] expanded;
    wire bad_compressed;
    wire output_space=!valid || (ready && (WIDE_FETCH==0 || !second_valid || ready_slots==2));
    wire [63:0] source_data=state==REQUEST && spare_match ? spare_data : rsp_data;
    wire [3:0] source_count=state==REQUEST && spare_match ? spare_count : (4'd1<<request_size);
    wire spare_match=BUFFER_ENABLE!=0 && EXTENSIONS!=0 && spare_valid && spare_pc==next_pc;
    wire [15:0] decode_half=source_data[15:0];
    rv64_decompress decompress(.c(decode_half),.instruction(expanded),.illegal(bad_compressed));
    // A predictor sees a complete expanded instruction; no prediction on a low-half prefix.
    wire reuse_complete=state==REQUEST && spare_match && (spare_half[1:0]!=3 || (WIDE_FETCH!=0 && spare_count>=4));
    wire candidate_word=state==HIGH_RESPONSE || EXTENSIONS==0 || source_data[1:0]==3;
    wire [31:0] candidate_insn=!candidate_word ? expanded :
        state==HIGH_RESPONSE ? {rsp_data[15:0],low_half} : source_data[31:0];
    wire [2:0] candidate_bytes=!candidate_word ? 3'd2 : 3'd4;
    wire candidate_illegal=!candidate_word && bad_compressed;
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
    wire live=reuse_complete || chained;
    reg chained;
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
        ((state==REQUEST && req_valid && req_ready) || reuse_event || (chained && complete));
    assign btb_hit_event=btb_lookup_event && table_hit;
    wire complete=!reset && !redirect && (reuse_complete && reuse_event ||
        ((state==RESPONSE || state==HIGH_RESPONSE) && rsp_valid && rsp_ready && !rsp_error && !killed &&
         !(state==RESPONSE && EXTENSIONS!=0 && rsp_data[1:0]==3 && next_pc[1:0]!=0)));
    assign btb_reject_event=complete && prediction_hit && !candidate_btb;
    rv64_btb #(.ENABLED(BTB_ENABLE!=0 && PREDICT_ENABLE!=0)) target_table(
        .clk(clk),.reset(reset),.clear(bht_clear),.lookup_pc(next_pc),.hit(table_hit),.kind(table_kind),.bytes(table_bytes),
        .target(table_target),.backward(table_backward),.train(btb_train),.train_pc(btb_train_pc),.train_insn(btb_train_insn),
        .train_bytes(btb_train_bytes),.train_next(btb_train_next));
    rv64_static_predictor #(.ENABLED(PREDICT_ENABLE),.EXTENSIONS(EXTENSIONS)) predictor(
        .pc(next_pc),.insn(candidate_insn),.bytes(candidate_bytes),.legal(!candidate_illegal),.predicted_next(static_next));
    wire [3:0] first_used=state==HIGH_RESPONSE ? 4'd2 : {1'b0,candidate_bytes};
    wire [3:0] tail_count=source_count-first_used;
    wire [63:0] tail_data=source_data>>{first_used,3'b0};
    wire unused_tail_high=^tail_data[63:32];
    wire second_word=EXTENSIONS==0 || tail_data[1:0]==3;
    wire [2:0] second_bytes=second_word ? 3'd4 : 3'd2;
    wire [31:0] second_expanded;wire second_bad;
    rv64_decompress second_decode(.c(tail_data[15:0]),.instruction(second_expanded),.illegal(second_bad));
    wire [31:0] second_insn=second_word ? tail_data[31:0] : second_expanded;
    wire second_control=second_insn[6:0]==7'h63 || second_insn[6:0]==7'h6f || second_insn[6:0]==7'h67 || second_insn[6:0]==7'h73 || second_insn[6:0]==7'h0f;
    wire emit_second=WIDE_FETCH!=0 && !candidate_illegal && candidate_next==next_pc+{61'd0,candidate_bytes} && tail_count>={1'b0,second_bytes} && !second_control;
    wire [63:0] stream_next=emit_second ? candidate_next+{61'd0,second_bytes} : candidate_next;
    wire [3:0] used=first_used+(emit_second ? {1'b0,second_bytes} : 4'd0);
    wire [3:0] remaining=source_count-used;
    wire contiguous=candidate_next==next_pc+{61'd0,candidate_bytes};
    wire turnover=I_PIPELINE!=0 && !reset && !redirect && state==RESPONSE && rsp_valid && !rsp_error && !killed && output_space &&
        (WIDE_FETCH!=0 ? (next_pc[1:0]==0 && (!contiguous || remaining==0)) :
         (next_pc[1:0]==0 && (EXTENSIONS==0 || rsp_data[1:0]==3) && candidate_next[1:0]==0));
    assign req_valid=!reset && !redirect && (((state==REQUEST && output_space && !spare_match) || state==HIGH_REQUEST) || turnover);
    assign req_addr=turnover ? stream_next : next_pc+(state==HIGH_REQUEST ? 64'd2 : 64'd0);
    assign req_size=WIDE_FETCH!=0 ? (state==HIGH_REQUEST ? (BUFFER_ENABLE!=0 ? 2'd2 : 2'd1) :
       req_addr[2:0]==0 ? 2'd3 : (EXTENSIONS==0 || req_addr[1:0]==0) ? 2'd2 : 2'd1) :
       turnover || EXTENSIONS==0 || (state==REQUEST && next_pc[1:0]==0) || (BUFFER_ENABLE!=0 && state==HIGH_REQUEST) ? 2'd2 : 2'd1;
    assign rsp_ready=(state==RESPONSE || state==HIGH_RESPONSE) && (output_space || redirect || killed);
    assign decode_pair_event=complete && emit_second;
    assign waiting=rsp_ready && !rsp_valid;
    assign discard_event=rsp_ready && rsp_valid && (killed || redirect);
    assign reuse_event=!reset && !redirect && state==REQUEST && spare_match && output_space;
    assign buffer_flush_event=!reset && redirect && spare_valid;
    // Occupancy is registered state, not request gating through branch/CSR logic.
    // HIGH_REQUEST also owns a partially assembled instruction.
    assign active=valid || spare_valid || state==RESPONSE || state==HIGH_REQUEST || state==HIGH_RESPONSE;
    always @(posedge clk) begin
        if(reset)begin
            state<=REQUEST;next_pc<=0;low_half<=0;killed<=0;valid<=0;second_valid<=0;second_packet<=0;
            spare_valid<=0;spare_data<=0;spare_count<=0;spare_pc<=0;request_size<=2;
            pc<=0;predicted_next<=0;predicted_return<=0;predicted_dynamic<=0;predicted_index<=0;insn<=0;raw_insn<=0;bytes<=4;illegal<=0;
            fetch_fault<=0;fault_cause<=0;fault_value<=0;predicted_btb<=0;chained<=0;
            early_hit<=0;early_dynamic<=0;early_return<=0;early_kind<=0;early_bytes<=0;early_index<=0;early_next<=0;early_target<=0;
        end else if(redirect)begin
            valid<=0;second_valid<=0;next_pc<=redirect_pc;low_half<=0;spare_valid<=0;spare_count<=0;
            if(rsp_ready && !rsp_valid)killed<=1;else begin state<=REQUEST;killed<=0;end
        end else begin
            if(req_valid && req_ready)request_size<=req_size;
            if(turnover && req_ready)chained<=1;else if(state==REQUEST && (reuse_event || req_valid && req_ready))chained<=0;
            if(btb_lookup_event)begin early_hit<=table_hit;early_kind<=table_kind;early_bytes<=table_bytes;early_target<=table_target;early_next<=table_next;early_index<=lookup_index;early_dynamic<=table_dynamic;early_return<=table_ras;end
            if(valid && ready)begin
                if(WIDE_FETCH!=0 && second_valid && ready_slots==1)begin
                    {pc,predicted_next,fault_cause,fault_value,insn,raw_insn,bytes,illegal,fetch_fault,predicted_return,predicted_dynamic,predicted_btb,predicted_index}<=second_packet;
                    valid<=1;second_valid<=0;
                end else begin valid<=0;second_valid<=0;end
            end
            case(state)
              REQUEST: if(reuse_event)begin
                  spare_valid<=0;
                  if(!reuse_complete)begin low_half<=spare_half;state<=HIGH_REQUEST;end
                end else if(req_valid && req_ready)begin state<=RESPONSE;spare_valid<=0;end
              HIGH_REQUEST:if(req_valid && req_ready)state<=HIGH_RESPONSE;
              RESPONSE,HIGH_RESPONSE:if(rsp_valid && rsp_ready)begin
                if(killed)begin killed<=0;state<=REQUEST;end
                else if(rsp_error)begin
                  spare_valid<=0;second_valid<=0;predicted_btb<=0;predicted_return<=0;predicted_dynamic<=0;predicted_index<=0;
                  predicted_next<=next_pc+(state==HIGH_RESPONSE || EXTENSIONS==0 ? 64'd4 : 64'd2);
                  valid<=1;state<=HOLD;pc<=next_pc;insn<=0;raw_insn<=0;bytes<=state==HIGH_RESPONSE ? 3'd4 : EXTENSIONS!=0 ? 3'd2 : 3'd4;
                  illegal<=0;fetch_fault<=1;fault_cause<=rsp_cause;fault_value<=next_pc+(state==HIGH_RESPONSE ? 64'd2 : 64'd0);
                end else if(state==RESPONSE && EXTENSIONS!=0 && source_data[1:0]==3 && next_pc[1:0]!=0)begin low_half<=rsp_data[15:0];state<=HIGH_REQUEST;end
              end
              HOLD:if(valid && ready)state<=REQUEST;
              default:state<=REQUEST;
            endcase
            if(complete)begin
                valid<=1;state<=turnover && req_ready ? RESPONSE : REQUEST;pc<=next_pc;spare_valid<=0;fetch_fault<=0;fault_cause<=0;fault_value<=0;
                insn<=candidate_insn;raw_insn<=candidate_word ? candidate_insn : {16'd0,decode_half};bytes<=candidate_bytes;illegal<=candidate_illegal;
                next_pc<=stream_next;predicted_next<=candidate_next;predicted_return<=packet_return;predicted_dynamic<=packet_dynamic;predicted_index<=packet_index;predicted_btb<=candidate_btb;
                second_valid<=emit_second;
                second_packet<={candidate_next,candidate_next+{61'd0,second_bytes},64'd0,64'd0,second_insn,second_word ? second_insn : {16'd0,tail_data[15:0]},second_bytes,!second_word && second_bad,1'b0,1'b0,1'b0,1'b0,5'd0};
                if(BUFFER_ENABLE!=0 && contiguous && remaining!=0)begin spare_valid<=1;spare_data<=source_data>>{used,3'b0};spare_count<=remaining;spare_pc<=stream_next;end
            end
        end
    end
endmodule
