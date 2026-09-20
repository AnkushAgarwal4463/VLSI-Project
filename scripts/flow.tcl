# OpenROAD Place & Route Flow Script for Systolic Array

# ------------------------------------------------------------------
# 1. Load Technology LEF and Macro LEF
# ------------------------------------------------------------------
if {[info exists ::env(TECH_LEF_FILE)] && [file exists $::env(TECH_LEF_FILE)]} {
    read_lef $::env(TECH_LEF_FILE)
} else {
    puts "ERROR: TECH_LEF_FILE environment variable not set or file missing!"
    exit 1
}

if {[info exists ::env(CELL_LEF_FILE)] && [file exists $::env(CELL_LEF_FILE)]} {
    read_lef $::env(CELL_LEF_FILE)
} else {
    puts "ERROR: CELL_LEF_FILE environment variable not set or file missing!"
    exit 1
}

# ------------------------------------------------------------------
# 2. Load Liberty File & Synthesized Gate-Level Netlist
# ------------------------------------------------------------------
if {[info exists ::env(LIB_FILE)] && [file exists $::env(LIB_FILE)]} {
    read_liberty $::env(LIB_FILE)
} else {
    puts "ERROR: LIB_FILE environment variable not set or file missing!"
    exit 1
}

set netlist_path "systolic_project/synth/systolic_netlist.v"
if {[file exists $netlist_path]} {
    read_verilog $netlist_path
} else {
    puts "ERROR: Netlist file $netlist_path not found!"
    exit 1
}

link_design systolic_array

# ------------------------------------------------------------------
# 3. Load Timing Constraints (SDC) with Multi-Path Fallback
# ------------------------------------------------------------------
set sdc_found 0

if {[info exists ::env(SDC_FILE)] && [file exists $::env(SDC_FILE)]} {
    puts "Reading SDC from environment variable: $::env(SDC_FILE)"
    read_sdc $::env(SDC_FILE)
    set sdc_found 1
} elseif {[file exists "constraints.sdc"]} {
    puts "Reading SDC from local repo file: constraints.sdc"
    read_sdc "constraints.sdc"
    set sdc_found 1
} elseif {[file exists "scripts/constraint.sdc"]} {
    puts "Reading SDC from scripts directory: scripts/constraint.sdc"
    read_sdc "scripts/constraint.sdc"
    set sdc_found 1
}

if {!$sdc_found} {
    puts "ERROR: Could not locate a valid SDC file!"
    exit 1
}

# ------------------------------------------------------------------
# 4. Floorplan Initialization (Dynamically query site name)
# ------------------------------------------------------------------
set util 50.0
if {[info exists ::env(UTIL)]} {
    set util $::env(UTIL)
}

set site_name "Nangate45_site"
set db [ord::get_db]
if {$db != ""} {
    set tech [$db getTech]
    if {$tech != ""} {
        set sites [$tech getSites]
        if {[llength $sites] > 0} {
            set site_name [[lindex $sites 0] getName]
        }
    }
}

puts "Initializing floorplan with utilization: $util%, site: $site_name"

initialize_floorplan -utilization $util \
                     -aspect_ratio 1.0 \
                     -core_space 10.0 \
                     -site $site_name

# ------------------------------------------------------------------
# 5. IO Pin Placement & Global Placement
# ------------------------------------------------------------------
place_pins -hor_layers metal3 -ver_layers metal2
global_placement

# Exit successfully
exit
