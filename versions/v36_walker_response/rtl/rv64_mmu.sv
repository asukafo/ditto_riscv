// Sv39 walker with optional eight-entry 4 KiB TLB; Svade software-managed A/D bits.
module rv64_mmu #(parameter TLB_ENABLE=1, I_PIPELINE=0, WALKER_RESPONSE=0) (
    input wire clk,reset,tlb_invalidate,
    input wire [1:0] privilege, data_privilege,
    input wire [63:0] satp, input wire sum,mxr,
    input wire u_valid, output wire u_ready,
    input wire [63:0] u_addr,u_data, input wire [1:0] u_size,
    input wire u_write,u_execute,u_atomic, input wire [4:0] u_amo,
    output wire u_rsp_valid, input wire u_rsp_ready,
    output wire [63:0] u_rsp_data, output wire u_rsp_error,
    output wire [63:0] u_rsp_cause, output wire busy,
    output wire tlb_hit_event,tlb_miss_event,tlb_fill_event,walk_event,
    output wire d_valid, input wire d_ready,
    output wire [63:0] d_addr,d_data, output wire [1:0] d_size,
    output wire d_write,d_atomic,d_execute,d_cache_data, output wire [4:0] d_amo,
    input wire d_rsp_valid, output wire d_rsp_ready,
    input wire [63:0] d_rsp_data, input wire d_rsp_error,
    input wire pte_rsp_valid, pte_rsp_error, input wire [63:0] pte_rsp_data
);
    localparam [2:0] IDLE=0,BYPASS=1,PTE_REQ=2,PTE_WAIT=3,ACCESS_REQ=4,ACCESS_WAIT=5,FAULT=6;
    reg [2:0] state;
    reg [63:0] address,data,pte_address,physical,cause,walk_context;
    reg walk_poisoned;
    reg [1:0] size,level,effective_priv;
    reg write_access,execute_access,atomic_access,allow_sum,allow_mxr;
    reg [4:0] amo;
    wire [1:0] request_priv=u_execute ? privilege : data_privilege;
    wire translate=satp[63:60]==8 && request_priv!=3;
    wire canonical=u_addr[63:39]=={25{u_addr[38]}};
    wire [63:0] page_cause=execute_access ? 64'd12 : write_access ? 64'd15 : 64'd13;
    wire [63:0] access_cause=execute_access ? 64'd1 : write_access ? 64'd7 : 64'd5;
    // Split walkers always bypass their cache for PTE reads. Use the
    // corresponding physical lane response directly while in PTE_WAIT.
    wire pte_valid=WALKER_RESPONSE!=0 ? pte_rsp_valid : d_rsp_valid;
    wire pte_error=WALKER_RESPONSE!=0 ? pte_rsp_error : d_rsp_error;
    wire [63:0] pte=WALKER_RESPONSE!=0 ? pte_rsp_data : d_rsp_data;
    // G is conservatively tagged with full satp too; RSW is software-owned.
    wire unused_translation_bits=^{address[63:30],pte[9:8],pte[5]};
    wire leaf=pte[1] || pte[3];
    wire bad_pte=!pte[0] || (!pte[1] && pte[2]) || pte[63:54]!=0;
    wire bad_superpage=(level==2 && pte[27:10]!=0) || (level==1 && pte[18:10]!=0);
    wire user_denied=(effective_priv==0 && !pte[4]) || (effective_priv==1 && pte[4] && (execute_access || !allow_sum));
    wire operation_denied=execute_access ? !pte[3] : write_access ? !pte[2] : !(pte[1] || (allow_mxr && pte[3]));
    wire bad_ad=!pte[6] || (write_access && !pte[7]);
    wire [63:0] leaf_address=level==2 ? {8'd0,pte[53:28],address[29:0]} : level==1 ? {8'd0,pte[53:19],address[20:0]} : {8'd0,pte[53:10],address[11:0]};
    wire [8:0] next_vpn=level==2 ? address[29:21] : address[20:12];
    wire tlb_hit;
    wire [43:0] tlb_ppn;
    wire [7:0] tlb_flags;
    wire unused_tlb_flags=^{tlb_flags[5],tlb_flags[0]};
    wire tlb_user_denied=(request_priv==0 && !tlb_flags[4]) ||
        (request_priv==1 && tlb_flags[4] && (u_execute || !sum));
    wire tlb_operation_denied=u_execute ? !tlb_flags[3] : u_write ? !tlb_flags[2] : !(tlb_flags[1] || (mxr && tlb_flags[3]));
    wire tlb_ad_denied=!tlb_flags[6] || (u_write && !tlb_flags[7]);
    wire fill_ok=state==PTE_WAIT && pte_valid && !pte_error && !bad_pte && leaf && level==0 &&
        !bad_superpage && !user_denied && !operation_denied && !bad_ad && !walk_poisoned && !tlb_invalidate;
    rv64_tlb #(.ENABLED(TLB_ENABLE)) tlb(.clk(clk),.reset(reset),.invalidate(tlb_invalidate),
        .lookup_valid(u_valid && u_ready && translate && canonical),.lookup_vaddr(u_addr),.lookup_context(satp),
        .hit(tlb_hit),.ppn(tlb_ppn),.flags(tlb_flags),
        .fill_valid(fill_ok),.fill_vaddr(address),.fill_context(walk_context),.fill_ppn(pte[53:10]),.fill_flags(pte[7:0]),
        .hit_event(tlb_hit_event),.miss_event(tlb_miss_event),.fill_event(tlb_fill_event));
    assign walk_event=state==PTE_REQ && d_ready;
    wire slot=state==IDLE || (I_PIPELINE!=0 && (state==BYPASS || state==ACCESS_WAIT) && d_rsp_valid && u_rsp_ready);
    wire fast=I_PIPELINE!=0 && u_execute && translate && canonical && tlb_hit &&
        !tlb_user_denied && !tlb_operation_denied && !tlb_ad_denied && !tlb_invalidate;
    wire pass=slot && (!translate || fast);
    assign busy=state!=IDLE;
    assign u_ready=slot && ((translate && !fast) || d_ready);
    assign d_valid=(pass && u_valid) || state==PTE_REQ || state==ACCESS_REQ;
    assign d_addr=pass ? (fast ? {8'd0,tlb_ppn,u_addr[11:0]} : u_addr) : state==PTE_REQ ? pte_address : physical;
    assign d_data=pass ? u_data : data;
    assign d_size=pass ? u_size : state==PTE_REQ ? 2'd3 : size;
    assign d_write=pass ? u_write : state==ACCESS_REQ && write_access;
    assign d_atomic=pass ? u_atomic : state==ACCESS_REQ && atomic_access;
    assign d_execute=pass ? u_execute : state==ACCESS_REQ && execute_access;
    assign d_cache_data=pass ? !u_execute : state==ACCESS_REQ && !execute_access;
    assign d_amo=pass ? u_amo : amo;
    assign d_rsp_ready=state==PTE_WAIT || ((state==BYPASS || state==ACCESS_WAIT) && u_rsp_ready);
    assign u_rsp_valid=state==FAULT || ((state==BYPASS || state==ACCESS_WAIT) && d_rsp_valid);
    assign u_rsp_data=d_rsp_data;
    assign u_rsp_error=state==FAULT || d_rsp_error;
    assign u_rsp_cause=state==FAULT ? cause : access_cause;
    always @(posedge clk) begin
        if (reset) begin
            state<=IDLE; walk_context<=0;walk_poisoned<=0;address<=0; data<=0; pte_address<=0; physical<=0; cause<=0;
            size<=0; level<=0; effective_priv<=3; write_access<=0; execute_access<=0;
            atomic_access<=0; amo<=0; allow_sum<=0; allow_mxr<=0;
        end else begin
            if(tlb_invalidate && state!=IDLE) walk_poisoned<=1;
            if (slot && u_valid && u_ready) begin
                walk_context<=satp;walk_poisoned<=tlb_invalidate;
                address<=u_addr; data<=u_data; size<=u_size; write_access<=u_write;
                execute_access<=u_execute; effective_priv<=request_priv; atomic_access<=u_atomic; amo<=u_amo;
                allow_sum<=sum; allow_mxr<=mxr;
                if (!translate || fast) state<=BYPASS;
                else if (!canonical) begin
                    cause<=u_execute ? 64'd12 : u_write ? 64'd15 : 64'd13; state<=FAULT;
                end else if(tlb_hit) begin
                    if(tlb_user_denied || tlb_operation_denied || tlb_ad_denied) begin
                        cause<=u_execute ? 64'd12 : u_write ? 64'd15 : 64'd13;state<=FAULT;
                    end else begin physical<={8'd0,tlb_ppn,u_addr[11:0]};state<=ACCESS_REQ;end
                end else begin
                    level<=2; pte_address<={8'd0,satp[43:0],12'd0}+{52'd0,u_addr[38:30],3'd0}; state<=PTE_REQ;
                end
            end
            else case (state)
            IDLE:;
            PTE_REQ: if (d_ready) state<=PTE_WAIT;
            PTE_WAIT: if (pte_valid) begin
                if (pte_error) begin cause<=access_cause; state<=FAULT; end
                else if (bad_pte) begin cause<=page_cause; state<=FAULT; end
                else if (leaf) begin
                    if (bad_superpage || user_denied || operation_denied || bad_ad) begin cause<=page_cause; state<=FAULT; end
                    else begin physical<=leaf_address; state<=ACCESS_REQ; end
                end else if (level==0 || pte[4] || pte[6] || pte[7]) begin cause<=page_cause; state<=FAULT; end
                else begin
                    pte_address<={8'd0,pte[53:10],12'd0}+{52'd0,next_vpn,3'd0}; level<=level-1; state<=PTE_REQ;
                end
            end
            ACCESS_REQ: if (d_ready) state<=ACCESS_WAIT;
            ACCESS_WAIT,BYPASS: if (d_rsp_valid && u_rsp_ready) state<=IDLE;
            FAULT: if (u_rsp_ready) state<=IDLE;
            default: state<=IDLE;
            endcase
        end
    end
endmodule
