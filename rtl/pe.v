// pe.v -- Single Systolic Processing Element (Multiply-Accumulate)
`default_nettype none

module pe #(
    parameter int WIDTH = 8
) (
    input  wire                   clk,
    input  wire                   rst_n,
    input  wire  [WIDTH-1:0]      a_in,
    input  wire  [WIDTH-1:0]      b_in,
    output logic [WIDTH-1:0]      a_out,
    output logic [WIDTH-1:0]      b_out,
    output logic [2*WIDTH-1:0]    acc_out
);

    // Synchronous Pipeline & Accumulation Logic
    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            a_out   <= '0;
            b_out   <= '0;
            acc_out <= '0;
        end else begin
            a_out   <= a_in;
            b_out   <= b_in;
            acc_out <= acc_out + (a_in * b_in);
        end
    end

endmodule

`default_nettype wire
