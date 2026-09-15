// pe.v -- Single systolic processing element
module pe #(
    parameter WIDTH = 8
) (
    input  wire                    clk,
    input  wire                    rst_n,
    input  wire [WIDTH-1:0]        a_in,
    input  wire [WIDTH-1:0]        b_in,
    output reg  [WIDTH-1:0]        a_out,
    output reg  [WIDTH-1:0]        b_out,
    output reg  [2*WIDTH-1:0]      acc_out
);
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            a_out   <= {WIDTH{1'b0}};
            b_out   <= {WIDTH{1'b0}};
            acc_out <= {(2*WIDTH){1'b0}};
        end else begin
            a_out   <= a_in;
            b_out   <= b_in;
            acc_out <= acc_out + (a_in * b_in);
        end
    end
endmodule
