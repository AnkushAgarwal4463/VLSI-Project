# Read technology and cell LEFs from environment variables
read_lef $env(TECH_LEF_FILE)
read_lef $env(CELL_LEF_FILE)
read_liberty $env(LIB_FILE)

# Read synthesized netlist
read_verilog systolic_project/synth/systolic_netlist.v
link_design systolic_array

# Read clock constraint
read_sdc scripts/constraint.sdc

# Floorplanning & Placement
initialize_floorplan -utilization $env(UTIL) -aspect_ratio 1.0 -core_space 10.0
place_pins
global_placement
detailed_placement

# Clock Tree Synthesis & Routing
clock_tree_synthesis
global_route
detail_route

# Write outputs for feature extraction
write_def $env(RUN_DIR)/output.def
report_checks > $env(RUN_DIR)/timing.log
report_power > $env(RUN_DIR)/power.log
