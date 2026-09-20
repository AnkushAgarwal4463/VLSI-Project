# ==============================================================================
# OpenROAD Physical Design Automation Script (scripts/flow.tcl)
# ==============================================================================

# Ingest Environment Variables set by CI/CD Matrix
set util        [expr {[info exists ::env(UTIL)] ? $::env(UTIL) : 50}]
set clk_period  [expr {[info exists ::env(CLK_PERIOD)] ? $::env(CLK_PERIOD) : 10.0}]
set run_dir     [expr {[info exists ::env(RUN_DIR)] ? $::env(RUN_DIR) : "systolic_project/runs/test_run"}]

file mkdir $run_dir

# ------------------------------------------------------------------------------
# 1. Load PDK Technology LEF, Macro LEF, and Liberty Files
# ------------------------------------------------------------------------------
read_lef pdk/Nangate45/NangateOpenCellLibrary.tech.lef
read_lef pdk/Nangate45/NangateOpenCellLibrary.macro.mod.lef
read_liberty pdk/Nangate45/NangateOpenCellLibrary_typical.lib

# ------------------------------------------------------------------------------
# 2. Read Structural Netlist and Initialize Design
# ------------------------------------------------------------------------------
read_verilog systolic_project/synth/systolic_netlist.v
link_design systolic_array

# Load SDC constraints if file exists
if {[file exists constraints.sdc]} {
    read_sdc constraints.sdc
}

# Dynamically apply clock period from CI matrix
create_clock -name clk -period $clk_period [get_ports clk]

# ------------------------------------------------------------------------------
# 3. Floorplanning & Power Grid Generation
# ------------------------------------------------------------------------------
# Parameterized utilization dynamically injected per matrix run
initialize_floorplan -utilization $util -aspect_ratio 1.0 -core_space 10

# Place primary I/O pins automatically around perimeter
place_pins -hor_layers metal3 -ver_layers metal2

# Generate Power/Ground connections and tracks
make_tracks
add_global_connection -net VDD -inst_pattern .* -pin_pattern VDD -power
add_global_connection -net VSS -inst_pattern .* -pin_pattern VSS -ground

# ------------------------------------------------------------------------------
# 4. Placement Stage
# ------------------------------------------------------------------------------
# Insert well-taps and end-caps
tapcell -endcap_master TAPCELL_X1 -distance 14

# Global and detailed placement legalization
global_placement
detailed_placement

# ------------------------------------------------------------------------------
# 5. Clock Tree Synthesis (CTS)
# ------------------------------------------------------------------------------
configure_cts -buf_list {BUF_X1 BUF_X2 BUF_X4}
clock_tree_synthesis

# Re-legalize placement following CTS buffer insertion
detailed_placement

# ------------------------------------------------------------------------------
# 6. Routing & Congestion Analysis
# ------------------------------------------------------------------------------
# Global routing
global_route

# Export congestion report for extract_features.py
set congestion_file [file join $run_dir "congestion.rpt"]
report_congestion -file $congestion_file

# Detailed routing using TritonRoute
detailed_route

# Insert filler cells to eliminate layout gaps after detailed route
filler_placement -filler_masters {FILLCELL_X1 FILLCELL_X2 FILLCELL_X4 FILLCELL_X8}
detailed_placement

# ------------------------------------------------------------------------------
# 7. Final STA, Database Save & Export Output Artifacts
# ------------------------------------------------------------------------------
# Estimate Parasitics for post-route STA accuracy
estimate_parasitics -global_routing

# Static Timing Analysis checks
report_checks -path_delay min_max -fields {slew cap input fanout} -digits 3
report_power

# Export DEF and Verilog artifacts
write_def [file join $run_dir "systolic_array.def"]
write_verilog [file join $run_dir "systolic_array_pnr.v"]

# Save OpenDB database required by extract_features.py
write_db [file join $run_dir "final.odb"]

puts "=== OpenROAD Flow Completed Successfully for $run_dir ==="
exit
