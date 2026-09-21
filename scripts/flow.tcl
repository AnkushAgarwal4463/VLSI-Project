# ==============================================================================
# OpenROAD Automated TCL Flow
# ==============================================================================

# 1. Read Technology LEF & Cell LEF
read_lef ./conda-env/share/pdk/sky130A/libs.ref/sky130_fd_sc_hd/techlef/sky130_fd_sc_hd__nom.tlef
read_lef ./conda-env/share/pdk/sky130A/libs.ref/sky130_fd_sc_hd/lef/sky130_fd_sc_hd.lef

# Read Liberty File & Design Netlist
read_liberty ./conda-env/share/pdk/sky130A/libs.ref/sky130_fd_sc_hd/lib/sky130_fd_sc_hd__tt_025C_1v80.lib
read_verilog $::env(SYNTH_NETLIST)
link_design $::env(DESIGN_NAME)

# Set Timing Constraints
read_sdc $::env(SDC_FILE)

# Variables setup
set util_decimal [expr {$UTIL / 100.0}]
set site_name "unithd"

# ==============================================================================
# 2. Dynamic Floorplan Calculation with Safety Buffer
# ==============================================================================
# Compute total standard cell area from netlist in um^2
set total_cell_area 0.0

foreach inst [get_cells *] {
    # Catch errors when inspecting top-level ports/pins that lack lib_cell
    if {![catch {get_property -quiet $inst lib_cell} cell_master] && $cell_master != ""} {
        set area [get_property $cell_master area]
        set total_cell_area [expr {$total_cell_area + $area}]
    }
}

puts "\[INFO\] Total Standard Cell Area: ${total_cell_area} um^2"

# Apply a 1.08x safety buffer (8% extra core room) to absorb cell padding & site alignment loss
set area_buffer 1.08
set buffered_cell_area [expr {$total_cell_area * $area_buffer}]

# Calculate required core area based on target utilization
set required_core_area [expr {$buffered_cell_area / $util_decimal}]

# Calculate core dimensions (square aspect ratio)
set core_dim [expr {sqrt($required_core_area)}]

# Set margin for I/O pins and power routing (scaled up for high-pin count/utilization)
if {$UTIL >= 60} {
    set core_margin 45.0
} else {
    set core_margin 30.0
}

# Calculate total die dimensions
set die_dim [expr {$core_dim + (2 * $core_margin)}]

set die_x0 0.0
set die_y0 0.0
set die_x1 [expr {ceil($die_dim)}]
set die_y1 [expr {ceil($die_dim)}]

set core_x0 $core_margin
set core_y0 $core_margin
set core_x1 [expr {$die_x1 - $core_margin}]
set core_y1 [expr {$die_y1 - $core_margin}]

puts "\[INFO\] Dynamic Floorplan Sizing (with 8% safety buffer):"
puts "       Die  Area : $die_x0 $die_y0 $die_x1 $die_y1"
puts "       Core Area : $core_x0 $core_y0 $core_x1 $core_y1"

initialize_floorplan \
    -die_area "$die_x0 $die_y0 $die_x1 $die_y1" \
    -core_area "$core_x0 $core_y0 $core_x1 $core_y1" \
    -site $site_name

make_tracks

# ==============================================================================
# 3. Placement & Routing Steps
# ==============================================================================
# Place I/O Pins
place_pins -hor_layers met3 -ver_layers met2

# Global Placement
global_placement -density $util_decimal

# Detailed Placement
detailed_placement

# Clock Tree Synthesis
clock_tree_synthesis -root_buf sky130_fd_sc_hd__clkbuf_16

# Global Routing
global_route

# Detailed Routing
detailed_route

# ==============================================================================
# 4. Feature Extraction & Reporting
# ==============================================================================
# 1. Total Die Area & Core Area
set die_area [expr {($die_x1 - $die_x0) * ($die_y1 - $die_y0)}]
set core_area [expr {($core_x1 - $core_x0) * ($core_y1 - $core_y0)}]

# 2. Total Cell Count (Leaf standard cells only)
set num_cells 0
foreach inst [get_cells *] {
    if {![catch {get_property -quiet $inst lib_cell} cell_master] && $cell_master != ""} {
        incr num_cells
    }
}

# 3. Pin Count & Net Count
set num_pins [llength [get_ports *]]
set num_nets [llength [get_nets *]]

# 4. Final Achieved Utilization
set final_util [expr {($total_cell_area / $core_area) * 100.0}]

# 5. Timing & Wirelength Metrics
set total_wirelength [groute_wire_length]
set wns [sta::worst_slack -max]
set tns [sta::total_negative_slack -max]

puts "\n=================================================================="
puts "                     DESIGN METRICS SUMMARY                       "
puts "=================================================================="
puts [format "Die Area            : %.2f um^2" $die_area]
puts [format "Core Area           : %.2f um^2" $core_area]
puts [format "Total Cell Area     : %.2f um^2" $total_cell_area]
puts [format "Target Utilization  : %.2f%%" $UTIL]
puts [format "Achieved Utilization: %.2f%%" $final_util]
puts "Total Cell Count    : $num_cells"
puts "Total Net Count     : $num_nets"
puts "Total IO Pin Count  : $num_pins"
puts [format "Total Wirelength    : %.2f um" $total_wirelength]
puts [format "Worst Negative Slack: %.3f ns" $wns]
puts [format "Total Negative Slack: %.3f ns" $tns]
puts "==================================================================\n"

exit
