// Byte formatting is independent of address translation and bus arbitration.
module rv64_lsu (
    input wire [63:0] raw_data, store_data,
    input wire [1:0] size,
    input wire unsigned_load,
    output reg [63:0] load_result, raw_value, store_value
);
    always @* begin
        case (size)
            0: begin
                raw_value={56'd0,raw_data[7:0]}; store_value={56'd0,store_data[7:0]};
                load_result={{56{!unsigned_load && raw_data[7]}},raw_data[7:0]};
            end
            1: begin
                raw_value={48'd0,raw_data[15:0]}; store_value={48'd0,store_data[15:0]};
                load_result={{48{!unsigned_load && raw_data[15]}},raw_data[15:0]};
            end
            2: begin
                raw_value={32'd0,raw_data[31:0]}; store_value={32'd0,store_data[31:0]};
                load_result={{32{!unsigned_load && raw_data[31]}},raw_data[31:0]};
            end
            default: begin raw_value=raw_data; store_value=store_data; load_result=raw_data; end
        endcase
    end
endmodule
