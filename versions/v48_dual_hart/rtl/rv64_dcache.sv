// Blocking 256-byte physical data cache, 16-byte lines, write-through/no-write-allocate.
// Only normal RAM data reads allocate. PTW, instruction, atomic, MMIO and mailbox bypass.
module rv64_dcache #(parameter ENABLED=1, parameter EARLY_RESTART=1, REFILL_FORWARD=0, HIT_UNDER_REFILL=0) (
    input wire clk,reset,invalidate,
    input wire u_valid,output wire u_ready,
    input wire [63:0] u_addr,u_data,input wire [1:0] u_size,
    input wire u_write,u_execute,u_cache_data,u_atomic,input wire [4:0] u_amo,
    output wire u_rsp_valid,input wire u_rsp_ready,
    output wire [63:0] u_rsp_data,output wire u_rsp_error,
    output wire d_valid,input wire d_ready,
    output wire [63:0] d_addr,d_data,output wire [1:0] d_size,
    output wire d_write,d_execute,d_atomic,output wire [4:0] d_amo,
    input wire d_rsp_valid,output wire d_rsp_ready,
    input wire [63:0] d_rsp_data,input wire d_rsp_error,
    output wire hit_event,miss_event,refill_event,miss_wait,write_event,bypass_event
);
    localparam [2:0] IDLE=0,BYPASS=1,REFILL_REQ=2,REFILL_RSP=3,RESPONSE=4;
    reg [2:0] state;
    reg [15:0] valid;
    reg [7:0] tags [0:15];
    reg [127:0] lines [0:15];
    reg [63:0] address,fill_low,response,store_data;
    reg [1:0] size;
    reg beat,response_error,poisoned,store_hit,response_available,early;
    wire fill_high=early ? (address[3] ^ beat) : beat;
    wire first_fits=({1'b0,u_addr[2:0]}+(4'd1<<u_size))<=8;
    wire [3:0] index=u_addr[7:4];
    wire [4:0] end_offset={1'b0,u_addr[3:0]}+(5'd1<<u_size);
    wire ram_line=u_addr[63:16]==0 && u_addr[15:4]<12'hfff && end_offset<=16;
    wire eligible=ENABLED!=0 && u_cache_data && !u_execute && !u_atomic && ram_line;
    wire hit=eligible && valid[index] && tags[index]==u_addr[15:8] && !invalidate;
    wire allocate=eligible && !u_write;
    wire [127:0] complete_line=early && address[3] ? {fill_low,d_rsp_data} : {d_rsp_data,fill_low};
    function automatic [63:0] extract(input [127:0] line_data,input [3:0] offset,input [1:0] bytes_log2);
        reg [63:0] shifted;
        begin
            shifted=64'(line_data>>{offset,3'b0});
            case(bytes_log2)
                0:extract=shifted&64'hff;
                1:extract=shifted&64'hffff;
                2:extract=shifted&64'hffffffff;
                default:extract=shifted;
            endcase
        end
    endfunction
    wire direct_refill=REFILL_FORWARD!=0 && state==IDLE && u_valid && allocate && !hit;
    wire direct_high=EARLY_RESTART!=0 && first_fits && u_addr[3];
    wire forward_critical=REFILL_FORWARD!=0 && state==REFILL_RSP && early && !beat &&
        d_rsp_valid && !d_rsp_error;
    wire [63:0] critical_data=extract({64'd0,d_rsp_data},{1'b0,address[2:0]},size);
    wire tail_pending=(state==REFILL_REQ || state==REFILL_RSP) && early && beat;
    // Both the accepted refill and a cache-eligible demand are in RAM.
    wire same_line=u_addr[15:4]==address[15:4];
    wire buffered_half=same_line && first_fits && u_addr[3]==address[3];
    wire returned_half=same_line && first_fits && u_addr[3]!=address[3] &&
        state==REFILL_RSP && d_rsp_valid && !d_rsp_error;
    wire background_ready=HIT_UNDER_REFILL!=0 && tail_pending && allocate &&
        !poisoned && !invalidate && !response_available &&
        (hit || buffered_half || returned_half);
    wire background_accept=!reset && u_valid && background_ready;
    assign u_ready=!reset && ((state==IDLE && (allocate || d_ready)) || background_ready);
    assign d_valid=!reset && ((state==IDLE && u_valid && !allocate) || direct_refill || state==REFILL_REQ);
    assign d_addr=direct_refill ? {u_addr[63:4],direct_high,3'b0} :
        state==IDLE ? u_addr : {address[63:4],fill_high,3'b0};
    assign d_data=state==IDLE && !direct_refill ? u_data : 64'd0;
    assign d_size=state==IDLE && !direct_refill ? u_size : 2'd3;
    assign d_write=state==IDLE && u_write;
    assign d_execute=state==IDLE && u_execute;
    assign d_atomic=state==IDLE && u_atomic;
    assign d_amo=state==IDLE ? u_amo : 5'd0;
    assign u_rsp_valid=response_available || forward_critical || (state==BYPASS && d_rsp_valid);
    assign u_rsp_data=state==BYPASS ? d_rsp_data : forward_critical ? critical_data : response;
    assign u_rsp_error=state==BYPASS ? d_rsp_error : response_error;
    assign d_rsp_ready=state==REFILL_RSP || (state==BYPASS && u_rsp_ready);
    assign hit_event=u_valid && u_ready && allocate && (hit || background_accept);
    assign miss_event=u_valid && u_ready && allocate && !hit && !background_accept;
    assign refill_event=(state==REFILL_REQ || direct_refill) && d_ready;
    assign miss_wait=state==REFILL_REQ || state==REFILL_RSP;
    assign write_event=u_valid && u_ready && eligible && u_write;
    assign bypass_event=u_valid && u_ready && u_cache_data && !eligible;
    always @(posedge clk) begin
        if(reset) begin
            state<=IDLE;valid<=0;address<=0;fill_low<=0;response<=0;store_data<=0;
            size<=0;beat<=0;response_error<=0;poisoned<=0;store_hit<=0;response_available<=0;early<=0;
        end else begin
            if(response_available && u_rsp_ready) response_available<=0;
            if(invalidate) begin
                valid<=0;
                if(state==REFILL_REQ || state==REFILL_RSP || state==BYPASS) poisoned<=1;
            end
            case(state)
                IDLE: if(u_valid && u_ready) begin
                    address<=u_addr;size<=u_size;store_data<=u_data;
                    poisoned<=invalidate;store_hit<=hit && u_write;response_error<=0;
                    if(!allocate) begin
                        state<=BYPASS;
                        // Atomic results bypass cache; discard any old normal-load copy.
                        // Other bypass writes also invalidate an alias defensively.
                        if(u_atomic || (u_write && !eligible))
                            if(valid[index] && tags[index]==u_addr[15:8]) valid[index]<=0;
                    end else if(hit) begin
                        response<=extract(lines[index],u_addr[3:0],u_size);response_available<=1;state<=RESPONSE;
                    end else begin
                        valid[index]<=0;beat<=0;early<=EARLY_RESTART!=0 && first_fits;
                        state<=direct_refill && d_ready ? REFILL_RSP : REFILL_REQ;
                    end
                end
                BYPASS: if(d_rsp_valid && u_rsp_ready) begin
                    if(store_hit && !poisoned && !invalidate) begin
                        if(d_rsp_error) valid[address[7:4]]<=0;
                        else for(integer byte_index=0;byte_index<16;byte_index=byte_index+1)
                            if(byte_index>=int'({1'b0,address[3:0]}) &&
                               byte_index<int'({1'b0,address[3:0]})+(1<<size))
                                lines[address[7:4]][byte_index*8+:8]<=8'(store_data>>((byte_index-int'({1'b0,address[3:0]}))*8));
                    end
                    state<=IDLE;
                end
                REFILL_REQ: if(d_ready) state<=REFILL_RSP;
                REFILL_RSP: if(d_rsp_valid) begin
                    if(d_rsp_error) begin
                        // Only the requested bytes can cause this load's exception.
                        // A failed speculative remainder leaves the line invalid for retry.
                        if(!early || !beat) begin
                            response<=0;response_error<=1;response_available<=1;state<=RESPONSE;
                        end else state<=(response_available && !u_rsp_ready) || background_accept ? RESPONSE : IDLE;
                    end else if(!beat) begin
                        fill_low<=d_rsp_data;beat<=1;state<=REFILL_REQ;
                        if(early) begin
                            response<=critical_data;
                            response_available<=!(forward_critical && u_rsp_ready);
                        end
                    end else begin
                        lines[address[7:4]]<=complete_line;tags[address[7:4]]<=address[15:8];
                        if(!poisoned && !invalidate) valid[address[7:4]]<=1;
                        if(!early) begin
                            response<=extract(complete_line,address[3:0],size);
                            response_available<=1;state<=RESPONSE;
                        end else state<=(response_available && !u_rsp_ready) || background_accept ? RESPONSE : IDLE;
                    end
                end
                RESPONSE: if(u_rsp_ready) state<=IDLE;
                default:state<=IDLE;
            endcase
            if(background_accept) begin
                response<=hit ? extract(lines[index],u_addr[3:0],u_size) :
                    extract({64'd0,buffered_half ? fill_low : d_rsp_data},{1'b0,u_addr[2:0]},u_size);
                response_available<=1;
                response_error<=0;
            end
        end
    end
endmodule
