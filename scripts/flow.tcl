# ==============================================================================
# OpenROAD Automated Physical Design Flow - Matrix Benchmark
# ==============================================================================

# Thread safety & logging performance
set_thread_count 4
suppress_message "GPL" 1
suppress_message "GRT" 1

# Extract matrix parameters from shell environment with fallbacks
set RUN_TAG $::env(RUN_TAG)
set UTIL $::env(UTIL)
set CLK_PERIOD $::env(CLK_PERIOD)
set ARRAY_SIZE $::env(ARRAY_SIZE)
set DATA_WIDTH $::env(DATA_WIDTH)

set OUT_DIR "systolic_project/runs/$RUN_TAG"
file mkdir $OUT_DIR

# ------------------------------------------------------------------------------
# 1. Tech & Liberty Setup (Nangate45)
# ------------------------------------------------------------------------------
read_lef "pdk/Nangate45/NangateOpenCellLibrary.tech.lef"
read_lef "pdk/Nangate45/NangateOpenCellLibrary.macro.lef"
read_liberty "pdk/Nangate45/NangateOpenCellLibrary_typical.lib"

# Load synthesized netlist
read_verilog "systolic_project/netlists/systolic_array.v"
link_design "systolic_array"

# ------------------------------------------------------------------------------
# 2. Constraints & Floorplanning
# ------------------------------------------------------------------------------
create_clock -name clk -period $CLK_PERIOD [get_ports clk]
set_input_delay -clock clk 0.2 [all_inputs]
set_output_delay -clock clk 0.2 [all_outputs]

# Site definition and core utilization floorplan
initialize_floorplan -utilization $UTIL -aspect_ratio 1.0 -core_space 10.0 -site FreePDK45_38x28_10g_2800

# ------------------------------------------------------------------------------
# 3. Placement & Clock Tree Synthesis (CTS)
# ------------------------------------------------------------------------------
place_pins -hor_layers metal3 -ver_layers metal2
global_placement -density 0.6
detailed_placement
optimize_mirroring

clock_tree_synthesis -root_buf CLKBUF_X3 -buf_list "CLKBUF_X1 CLKBUF_X2 CLKBUF_X3"

# ------------------------------------------------------------------------------
# 4. Routing & Detailed Extraction
# ------------------------------------------------------------------------------
global_route
detail_route -max_it 8

# Save final physical database
write_db "$OUT_DIR/final.odb"

# Report timing and global routing congestion
report_checks -path_delay max -fields {slack cap cell fanout line} -digits 4 > "$OUT_DIR/timing.rpt"
report_congestion "$OUT_DIR/congestion.rpt"

exit
