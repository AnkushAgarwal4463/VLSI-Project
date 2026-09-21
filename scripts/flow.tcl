# ==============================================================================
# 1. Read variables from environment with safe defaults
# ==============================================================================
if {[info exists ::env(UTIL)] && $::env(UTIL) != ""} {
    set UTIL $::env(UTIL)
} else {
    set UTIL 50
}

if {[info exists ::env(CLK_PERIOD)] && $::env(CLK_PERIOD) != ""} {
    set CLK_PERIOD $::env(CLK_PERIOD)
} else {
    set CLK_PERIOD 10.0
}

if {[info exists ::env(SITE)] && $::env(SITE) != ""} {
    set site_name $::env(SITE)
} else {
    set site_name "unithd"
}

# Target density configuration (Fixed for GPL-0302)
set TARGET_DENSITY 0.72

# ==============================================================================
# 2. Define Sky130 PDK Paths
# ==============================================================================
set pdk_dir "./conda-env/share/pdk/sky130A"
set tech_lef "${pdk_dir}/libs.ref/sky130_fd_sc_hd/techlef/sky130_fd_sc_hd__nom.tlef"
set std_cell_lef "${pdk_dir}/libs.ref/sky130_fd_sc_hd/lef/sky130_fd_sc_hd.lef"
set lib_file "${pdk_dir}/libs.ref/sky130_fd_sc_hd/lib/sky130_fd_sc_hd__tt_025C_1v80.lib"
set netlist_verilog "systolic_project/synth/systolic_netlist.v"

# ==============================================================================
# 3. Read Liberty, LEFs, and Netlist
# ==============================================================================
puts "Reading Liberty and LEF files..."
read_liberty $lib_file
read_lef $tech_lef
read_lef $std_cell_lef

puts "Reading synthesized netlist..."
read_verilog $netlist_verilog
link_design "systolic_array"

# ==============================================================================
# 4. Initialize Expanded Floorplan & Make Routing Tracks
# ==============================================================================
# Expanded Die Dimensions for 15,000+ cells (1000um x 1000um die area)
set die_x0 0.0
set die_y0 0.0
set die_x1 1000.0
set die_y1 1000.0

# 35um margin on each side for core placement
set core_margin 35.0
set core_x0 [expr {$die_x0 + $core_margin}]
set core_y0 [expr {$die_y0 + $core_margin}]
set core_x1 [expr {$die_x1 - $core_margin}]
set core_y1 [expr {$die_y1 - $core_margin}]

puts "Initializing expanded floorplan..."
puts " Die Area : $die_x0 $die_y0 $die_x1 $die_y1"
puts " Core Area: $core_x0 $core_y0 $core_x1 $core_y1"

initialize_floorplan \
    -die_area "$die_x0 $die_y0 $die_x1 $die_y1" \
    -core_area "$core_x0 $core_y0 $core_x1 $core_y1" \
    -site $site_name

# Generate routing tracks across all metal layers for pin grid snapping
make_tracks

# ==============================================================================
# 5. Define Clock & Timing Constraints
# ==============================================================================
create_clock -name clk -period $CLK_PERIOD [get_ports clk]

# Get all inputs except clock
set in_ports [get_ports * -filter "direction == input && name != clk"]
if {[llength $in_ports] > 0} {
    set_input_delay -clock clk 0.2 $in_ports
}

set_output_delay -clock clk 0.2 [all_outputs]

# ==============================================================================
# 6. Global Placement, Multi-Layer Pin Placement & Detailed Placement
# ==============================================================================
puts "Running global placement with target density $TARGET_DENSITY..."

if {$UTIL >= 60} {
    set_placement_padding -global -left 1 -right 1
}

# Run global placement with increased target density parameter
global_placement -density $TARGET_DENSITY

puts "Running pin placement (Multi-layer allocation)..."
set io_hor_layers [list met3 met5]
set io_ver_layers [list met2 met4]

if {[catch {
    place_pins -hor_layers $io_hor_layers \
               -ver_layers $io_ver_layers
} err]} {
    puts "\[WARNING\] Pin placement failed: $err"
}

puts "Running detailed placement..."
detailed_placement
check_placement

# ==============================================================================
# 7. Create Output Directory and Save Database
# ==============================================================================
if {[info exists ::env(RUN_TAG)] && $::env(RUN_TAG) != ""} {
    set run_dir "systolic_project/runs/$::env(RUN_TAG)"
} else {
    set run_dir "systolic_project/runs/smoke_test"
}

file mkdir $run_dir
write_db "${run_dir}/final.odb"
puts "Successfully saved database to ${run_dir}/final.odb"
