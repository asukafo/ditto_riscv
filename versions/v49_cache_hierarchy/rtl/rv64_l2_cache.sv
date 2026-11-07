// Shared 4 KiB, two-way physical cache with two independently valid 8 B
// sectors per 16 B line. Writes go to RAM; successful writes drop a copy.
module rv64_l2_cache (
    input wire clk, reset,
    input wire u_valid, output wire u_ready,
    input wire [63:0] u_addr, u_wdata,
    input wire [1:0] u_size,
    input wire u_write, u_store_check, u_uncached,
    output wire u_rsp_valid, input wire u_rsp_ready,
    output wire [63:0] u_rsp_data, output wire u_rsp_error,
    output wire d_valid, input wire d_ready,
    output wire [63:0] d_addr, d_wdata,
    output wire [1:0] d_size,
    output wire d_write, d_store_check,
    input wire d_rsp_valid, output wire d_rsp_ready,
    input wire [63:0] d_rsp_data, input wire d_rsp_error,
    output wire hit_event, fill_event
);
    localparam [1:0] IDLE=0, WAIT=1, HIT_RESP=2;
    reg [1:0] state;
    reg [255:0] valid_low, valid_high;
    reg [127:0] victim;
    reg [4:0] tags [0:255];
    reg [63:0] low [0:255];
    reg [63:0] high [0:255];
    reg allocate, replace_line, write_hit;
    reg [7:0] saved_entry;
    reg [4:0] saved_tag;
    reg saved_high;
    reg [63:0] hit_data;

    wire [6:0] set_index=u_addr[10:4];
    wire [7:0] way0={1'b0,set_index}, way1={1'b1,set_index};
    wire occupied0=valid_low[way0] || valid_high[way0];
    wire occupied1=valid_low[way1] || valid_high[way1];
    wire tag0=occupied0 && tags[way0]==u_addr[15:11];
    wire tag1=occupied1 && tags[way1]==u_addr[15:11];
    wire [7:0] entry=tag0 ? way0 : tag1 ? way1 :
        !occupied0 ? way0 : !occupied1 ? way1 : {victim[set_index],set_index};
    wire ram=u_addr[63:16]==0 && u_addr[15:4]!=12'hfff;
    wire fits=({1'b0,u_addr[2:0]}+(4'd1<<u_size))<=8;
    wire cache_read=ram && fits && !u_write && !u_store_check && !u_uncached;
    wire hit=cache_read && (tag0 || tag1) && (u_addr[3] ? valid_high[entry] : valid_low[entry]);
    wire [63:0] sector=u_addr[3] ? high[entry] : low[entry];
    wire [63:0] shifted=sector>>{u_addr[2:0],3'b0};
    wire [63:0] load_data=u_size==0 ? {56'd0,shifted[7:0]} :
                          u_size==1 ? {48'd0,shifted[15:0]} :
                          u_size==2 ? {32'd0,shifted[31:0]} : shifted;

    // On a miss or bypass, handshake directly with RAM. The arbiter
    // holds its selected request until acceptance; WAIT retains metadata.
    assign u_ready=!reset && state==IDLE && (hit || d_ready);
    assign u_rsp_valid=!reset && (state==HIT_RESP || (state==WAIT && d_rsp_valid));
    assign u_rsp_data=state==HIT_RESP ? hit_data : d_rsp_data;
    assign u_rsp_error=state==WAIT && d_rsp_error;
    assign d_valid=!reset && state==IDLE && u_valid && !hit;
    assign d_addr=u_addr;
    assign d_wdata=u_wdata;
    assign d_size=u_size;
    assign d_write=u_write;
    assign d_store_check=u_store_check;
    assign d_rsp_ready=!reset && state==WAIT && u_rsp_ready;
    assign hit_event=u_valid && u_ready && hit;
    assign fill_event=d_rsp_valid && d_rsp_ready && !d_rsp_error && allocate;

    always @(posedge clk) begin
        if(reset) begin
            state<=IDLE;
            valid_low<=0;
            valid_high<=0;
            victim<=0;
            allocate<=0;
            replace_line<=0;
            write_hit<=0;
            saved_entry<=0;
            saved_tag<=0;
            saved_high<=0;
            hit_data<=0;
        end else case(state)
            IDLE: if(u_valid && u_ready) begin
                if(hit) begin
                    hit_data<=load_data;
                    victim[set_index]<=!entry[7];
                    state<=HIT_RESP;
                end else begin
                    // Fill only from the exact requested access. A subword
                    // miss bypasses so it cannot cause a wider fault/access.
                    allocate<=cache_read && u_size==3 && u_addr[2:0]==0;
                    replace_line<=!(tag0 || tag1);
                    write_hit<=ram && u_write && (tag0 || tag1);
                    saved_entry<=entry;
                    saved_tag<=u_addr[15:11];
                    saved_high<=u_addr[3];
                    state<=WAIT;
                end
            end
            WAIT: if(d_rsp_valid && d_rsp_ready) begin
                if(fill_event) begin
                    tags[saved_entry]<=saved_tag;
                    victim[saved_entry[6:0]]<=!saved_entry[7];
                    if(saved_high) begin
                        high[saved_entry]<=d_rsp_data;
                        valid_high[saved_entry]<=1;
                        if(replace_line) valid_low[saved_entry]<=0;
                    end else begin
                        low[saved_entry]<=d_rsp_data;
                        valid_low[saved_entry]<=1;
                        if(replace_line) valid_high[saved_entry]<=0;
                    end
                end
                if(write_hit && !d_rsp_error) begin
                    if(saved_high) valid_high[saved_entry]<=0;
                    else valid_low[saved_entry]<=0;
                end
                state<=IDLE;
            end
            HIT_RESP: if(u_rsp_ready) state<=IDLE;
            default: state<=IDLE;
        endcase
    end
endmodule
