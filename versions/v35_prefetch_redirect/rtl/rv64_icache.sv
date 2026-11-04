// 256-byte direct-mapped, physically indexed/tagged instruction cache.
// Only the platform's uniform 64 KiB executable RAM is cacheable. Each 16-byte
// line is refilled with two 8-byte reads; PTE/data/atomic/MMIO traffic bypasses.
module rv64_icache # (parameter ENABLED=1, parameter EARLY_RESTART=1, I_PIPELINE=0, HIT_UNDER_REFILL=1, FILL_FORWARD=1, WIDE_READ=0, REFILL_TURNOVER=0) (
    input wire clk,reset,invalidate,
    input wire u_valid,output wire u_ready,
    input wire [63:0] u_addr,u_data,input wire [1:0] u_size,
    input wire u_write,u_execute,u_atomic,input wire [4:0] u_amo,
    output wire u_rsp_valid,input wire u_rsp_ready,
    output wire [63:0] u_rsp_data,output wire u_rsp_error,
    output wire d_valid,input wire d_ready,
    output wire [63:0] d_addr,d_data,output wire [1:0] d_size,
    output wire d_write,d_atomic,output wire [4:0] d_amo,
    input wire d_rsp_valid,output wire d_rsp_ready,
    input wire [63:0] d_rsp_data,input wire d_rsp_error,
    output wire hit_event,miss_event,refill_event,miss_wait,bypass_event,refill_hit_event,fill_hit_event
);
    localparam [2:0] IDLE=0,BYPASS=1,REFILL_REQ=2,REFILL_RSP=3,RESPONSE=4;
    reg [2:0] state;
    reg [15:0] valid;
    reg [7:0] tags [0:15];
    reg [127:0] lines [0:15];
    reg [63:0] address,fill_low,response;
    reg [1:0] size;
    reg beat,response_error,poisoned,response_available,early;
    wire fill_high=early ? (address[3] ^ beat) : beat;
    wire first_fits=({1'b0,u_addr[2:0]}+(4'd1<<u_size))<=8;
    wire [3:0] index=u_addr[7:4];
    wire [4:0] end_offset={1'b0,u_addr[3:0]}+(5'd1<<u_size);
    wire cacheable=ENABLED!=0 && u_execute && !u_write && !u_atomic &&
        u_addr[63:16]==0 && (WIDE_READ!=0 || u_size<=2'd2) && end_offset<=16;
    wire hit=cacheable && valid[index] && tags[index]==u_addr[15:8] && !invalidate;
    wire [127:0] complete_line=early && address[3] ? {fill_low,d_rsp_data} : {d_rsp_data,fill_low};
    function automatic [63:0] extract(input [127:0] line_data,input [3:0] offset,input [1:0] bytes_log2);
        reg [63:0] shifted;
        begin
            shifted=64'(line_data>>{offset,3'b0});
            case (bytes_log2)
                0:extract=shifted&64'hff;
                1:extract=shifted&64'hffff;
                2:extract=shifted&64'hffffffff;
                default:extract=shifted;
            endcase
        end
    endfunction
    wire slot=state==IDLE || (I_PIPELINE!=0 && state==RESPONSE && u_rsp_ready);
    // The miss's critical response must precede all younger hit responses.
    // The single response register either drains this edge or is already empty.
    wire background=state==REFILL_REQ || state==REFILL_RSP;
    wire fill_match=FILL_FORWARD!=0 && background && early && beat && cacheable && first_fits &&
        u_addr[63:3]==address[63:3] && !invalidate;
    wire background_slot=I_PIPELINE!=0 && background && early && beat &&
        !poisoned && ((HIT_UNDER_REFILL!=0 && hit) || fill_match) && (!response_available || u_rsp_ready);
    wire background_accept=!reset && background_slot && u_valid;
    wire direct_refill=REFILL_TURNOVER!=0 && slot && u_valid && cacheable && !hit;
    wire direct_high=EARLY_RESTART!=0 && first_fits && u_addr[3];
    wire forward_critical=REFILL_TURNOVER!=0 && state==REFILL_RSP && early && !beat &&
        d_rsp_valid && !d_rsp_error;
    wire [63:0] critical_data=extract({64'd0,d_rsp_data},{1'b0,address[2:0]},size);
    assign u_ready=!reset && ((slot && (cacheable || d_ready)) || background_slot);
    assign d_valid=!reset && ((slot && u_valid && !cacheable) || direct_refill || state==REFILL_REQ);
    assign d_addr=direct_refill ? {u_addr[63:4],direct_high,3'b0} :
        slot ? u_addr : {address[63:4],fill_high,3'b0};
    assign d_data=slot && !direct_refill ? u_data : 64'd0;
    assign d_size=slot && !direct_refill ? u_size : 2'd3;
    assign d_write=slot && u_write;
    assign d_atomic=slot && u_atomic;
    assign d_amo=slot ? u_amo : 5'd0;
    assign u_rsp_valid=response_available || forward_critical || (state==BYPASS && d_rsp_valid);
    assign u_rsp_data=state==BYPASS ? d_rsp_data : forward_critical ? critical_data : response;
    assign u_rsp_error=state==BYPASS ? d_rsp_error : response_error;
    assign d_rsp_ready=state==REFILL_RSP || (state==BYPASS && u_rsp_ready);
    // Events are counted by the host, keeping observation counters off RTL paths.
    assign refill_hit_event=background_accept && hit;
    assign fill_hit_event=background_accept && fill_match;
    assign hit_event=u_valid && u_ready && hit;
    assign miss_event=u_valid && u_ready && cacheable && !hit && !fill_match;
    assign bypass_event=u_valid && u_ready && !cacheable && u_execute;
    assign refill_event=(state==REFILL_REQ || direct_refill) && d_ready;
    assign miss_wait=state==REFILL_REQ || state==REFILL_RSP;
    always @(posedge clk) begin
        if (reset) begin
            state<=IDLE; valid<=0; address<=0; fill_low<=0; response<=0;
            size<=0; beat<=0; response_error<=0; poisoned<=0;
            response_available<=0; early<=0;
        end else begin
            if (response_available && u_rsp_ready) response_available<=0;
            if (invalidate) begin
                valid<=0;
                if (state==REFILL_REQ || state==REFILL_RSP) poisoned<=1;
            end
            if (slot && u_valid && u_ready) begin
                    response_error<=0;
                    if (!cacheable) state<=BYPASS;
                    else if (hit) begin
                        response<=extract(lines[index],u_addr[3:0],u_size); response_available<=1; state<=RESPONSE;
                    end else begin
                        address<=u_addr; size<=u_size; beat<=0; poisoned<=invalidate;
                        early<=EARLY_RESTART!=0 && first_fits;
                        valid[index]<=0; state<=direct_refill && d_ready ? REFILL_RSP : REFILL_REQ;
                    end
                end
            else case (state)
                IDLE:;
                BYPASS: if (d_rsp_valid && u_rsp_ready) state<=IDLE;
                REFILL_REQ: if (d_ready) state<=REFILL_RSP;
                REFILL_RSP: if (d_rsp_valid) begin
                    if (d_rsp_error) begin
                        // A failed speculative remainder never faults an already returned word.
                        // Keep the line invalid so a later access retries the missing bytes.
                        if (!early || !beat) begin
                            response<=0; response_error<=1; response_available<=1; state<=RESPONSE;
                        end else state<=(response_available && !u_rsp_ready) || background_accept ? RESPONSE : IDLE;
                    end else if (!beat) begin
                        fill_low<=d_rsp_data; beat<=1; state<=REFILL_REQ;
                        if (early) begin
                            response<=critical_data;
                            response_available<=!(forward_critical && u_rsp_ready);
                        end
                    end else begin
                        lines[address[7:4]]<=complete_line;
                        tags[address[7:4]]<=address[15:8];
                        if (!poisoned && !invalidate) valid[address[7:4]]<=1;
                        if (!early) begin
                            response<=extract(complete_line,address[3:0],size);
                            response_available<=1; state<=RESPONSE;
                        end else state<=(response_available && !u_rsp_ready) || background_accept ? RESPONSE : IDLE;
                    end
                end
                RESPONSE: if (u_rsp_ready) state<=IDLE;
                default: state<=IDLE;
            endcase
            // Refill state/address/beat are independent of this younger hit.
            // This write also wins over draining the previous response this edge.
            if (background_accept) begin
                response<=fill_match ? extract({64'd0,fill_low},{1'b0,u_addr[2:0]},u_size) : extract(lines[index],u_addr[3:0],u_size);
                response_error<=0; response_available<=1;
            end
        end
    end
endmodule
