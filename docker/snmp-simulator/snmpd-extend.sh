#!/bin/bash
# =============================================================================
# snmpd-extend.sh — SNMP Extend & Pass-Persist Handler
# =============================================================================
# Simulates H3C/HH3C Entity MIB data for out-of-band management testing.
#
# Usage:
#   snmpd-extend.sh <mode>
#
# Modes:
#   cpu_usage              — Print simulated CPU utilization (%)
#   mem_usage              — Print simulated memory utilization (%)
#   temperature            — Print simulated temperature (°C)
#   fan_speed              — Print simulated fan speed (RPM)
#   psu_status             — Print simulated PSU status
#   hw_health              — Print overall hardware health
#   pass_persist_h3c       — pass_persist handler for .1.3.6.1.4.1.25506
#   pass_persist_entity    — pass_persist handler for .1.3.6.1.2.1.47
# =============================================================================

set -euo pipefail

# ---------------------------------------------------------------------------
# Configuration: simulated entity indices and their properties
# ---------------------------------------------------------------------------
# Each entity represents a module/slot in a simulated H3C chassis switch.
# Index values mirror what a real H3C device would report.

ENTITY_INDICES=(1 2 3 4 5)

declare -A ENTITY_NAMES
ENTITY_NAMES[1]="Slot 0/CPU 0"
ENTITY_NAMES[2]="Slot 1/CPU 0"
ENTITY_NAMES[3]="Slot 0/Fan 1"
ENTITY_NAMES[4]="Slot 0/Power 1"
ENTITY_NAMES[5]="Slot 0/Sensor 1"

declare -A ENTITY_DESCR
ENTITY_DESCR[1]="Main Processing Unit - Slot 0"
ENTITY_DESCR[2]="Standby Processing Unit - Slot 1"
ENTITY_DESCR[3]="Cooling Fan Module 1"
ENTITY_DESCR[4]="Power Supply Module 1"
ENTITY_DESCR[5]="Environmental Sensor Module 1"

# entPhysicalClass values: 3=chassis, 5=container, 6=powerSupply, 7=fan, 8=sensor, 9=module, 10=port
declare -A ENTITY_CLASS
ENTITY_CLASS[1]=9   # module
ENTITY_CLASS[2]=9   # module
ENTITY_CLASS[3]=7   # fan
ENTITY_CLASS[4]=6   # powerSupply
ENTITY_CLASS[5]=8   # sensor

# Additional entity table columns
declare -A ENTITY_HWREV
ENTITY_HWREV[1]="REV.A"
ENTITY_HWREV[2]="REV.A"
ENTITY_HWREV[3]="REV.B"
ENTITY_HWREV[4]="REV.C"
ENTITY_HWREV[5]="REV.A"

declare -A ENTITY_FWREV
ENTITY_FWREV[1]="7.1.075"
ENTITY_FWREV[2]="7.1.075"
ENTITY_FWREV[3]=""
ENTITY_FWREV[4]=""
ENTITY_FWREV[5]=""

declare -A ENTITY_SERIAL
ENTITY_SERIAL[1]="SIM0000000001"
ENTITY_SERIAL[2]="SIM0000000002"
ENTITY_SERIAL[3]="SIM0000000003"
ENTITY_SERIAL[4]="SIM0000000004"
ENTITY_SERIAL[5]="SIM0000000005"

declare -A ENTITY_MODEL
ENTITY_MODEL[1]="SR8800-MPU"
ENTITY_MODEL[2]="SR8800-MPU"
ENTITY_MODEL[3]="SR8800-FAN"
ENTITY_MODEL[4]="SR8800-PSU"
ENTITY_MODEL[5]="SR8800-SENSOR"

# ---------------------------------------------------------------------------
# Sensor value generation
# ---------------------------------------------------------------------------
# Produces slightly varying values each call to simulate realistic fluctuation.
# Uses /dev/urandom for portability (no $RANDOM in all shells).

_rand_range() {
    local min=$1 max=$2
    local range=$(( max - min + 1 ))
    local raw
    raw=$(od -An -tu2 -N2 /dev/urandom 2>/dev/null | tr -d ' ')
    echo $(( min + raw % range ))
}

get_cpu_usage() {
    local idx=${1:-0}
    case $idx in
        1) _rand_range 15 45 ;;   # primary CPU moderate load
        2) _rand_range 5 20 ;;    # standby CPU low load
        *) _rand_range 10 35 ;;
    esac
}

get_mem_usage() {
    local idx=${1:-0}
    case $idx in
        1) _rand_range 40 70 ;;
        2) _rand_range 25 45 ;;
        *) _rand_range 30 55 ;;
    esac
}

get_temperature() {
    local idx=${1:-0}
    case $idx in
        1) _rand_range 38 52 ;;   # CPU module runs warm
        2) _rand_range 35 48 ;;
        3) _rand_range 25 30 ;;   # fan module cooler
        4) _rand_range 30 42 ;;   # PSU
        5) _rand_range 28 36 ;;   # ambient sensor
        *) _rand_range 30 45 ;;
    esac
}

get_fan_speed() {
    _rand_range 3500 5200
}

get_psu_status() {
    # 1 = normal, 2 = abnormal
    echo 1
}

get_hw_health() {
    # 0 = normal (no error)
    echo 0
}

get_error_status() {
    # hh3cEntityExtErrorStatus: 0 = normal
    echo 0
}

# ---------------------------------------------------------------------------
# Simple extend modes (called directly by snmpd extend directive)
# ---------------------------------------------------------------------------

case "${1:-}" in
    cpu_usage)
        get_cpu_usage 1
        exit 0
        ;;
    mem_usage)
        get_mem_usage 1
        exit 0
        ;;
    temperature)
        get_temperature 5
        exit 0
        ;;
    fan_speed)
        get_fan_speed
        exit 0
        ;;
    psu_status)
        get_psu_status
        exit 0
        ;;
    hw_health)
        get_hw_health
        exit 0
        ;;
esac

# ---------------------------------------------------------------------------
# pass_persist protocol helpers
# ---------------------------------------------------------------------------
# Protocol: snmpd writes commands to stdin, we reply on stdout.
#   PING          → PONG
#   get\n<OID>    → <OID>\n<type>\n<value>     (or NONE if unknown)
#   getnext\n<OID>→ <OID>\n<type>\n<value>     (next OID in tree)
#   set\n...      → not-writable
#
# Types recognised by pass_persist:
#   integer, gauge, counter, counter64, timeticks, octet, string, objectid, ipaddress

# Logging (writes to stderr → Docker logs)
log() {
    echo "[snmpd-extend] $*" >&2
}

# Reply with a value triple
reply_value() {
    local oid="$1"
    local type="$2"
    local value="$3"
    echo "$oid"
    echo "$type"
    echo "$value"
}

reply_none() {
    echo "NONE"
}

# ---------------------------------------------------------------------------
# H3C pass_persist handler (.1.3.6.1.4.1.25506)
# ---------------------------------------------------------------------------
# OID tree we simulate:
#
# .1.3.6.1.4.1.25506.2.6.1.1.1.1.6.<idx>   hh3cEntityExtCpuUsage       integer
# .1.3.6.1.4.1.25506.2.6.1.1.1.1.8.<idx>   hh3cEntityExtMemUsage       integer
# .1.3.6.1.4.1.25506.2.6.1.1.1.1.12.<idx>  hh3cEntityExtTemperature    integer
# .1.3.6.1.4.1.25506.2.6.1.1.1.1.19.<idx>  hh3cEntityExtErrorStatus    integer
# .1.3.6.1.4.1.25506.2.6.1.1.1.1.22.<idx>  hh3cEntityExtCpuUsageThreshold integer (80)
#
# For entity discovery walk:
# .1.3.6.1.4.1.25506.2.6.1.1.1.1.1.<idx>   hh3cEntityExtPhysicalIndex  integer (= idx)

H3C_BASE=".1.3.6.1.4.1.25506.2.6.1.1.1.1"

# Build sorted list of all H3C OIDs we serve
declare -a H3C_OIDS=()
for idx in "${ENTITY_INDICES[@]}"; do
    H3C_OIDS+=("${H3C_BASE}.1.${idx}")    # PhysicalIndex
    H3C_OIDS+=("${H3C_BASE}.6.${idx}")    # CpuUsage
    H3C_OIDS+=("${H3C_BASE}.8.${idx}")    # MemUsage
    H3C_OIDS+=("${H3C_BASE}.12.${idx}")   # Temperature
    H3C_OIDS+=("${H3C_BASE}.19.${idx}")   # ErrorStatus
    H3C_OIDS+=("${H3C_BASE}.22.${idx}")   # CpuUsageThreshold
done

# Sort OIDs numerically by dotted components
IFS=$'\n' H3C_OIDS_SORTED=($(printf '%s\n' "${H3C_OIDS[@]}" | sort -t. -k1,1n -k2,2n -k3,3n -k4,4n -k5,5n -k6,6n -k7,7n -k8,8n -k9,9n -k10,10n -k11,11n -k12,12n -k13,13n)); unset IFS

h3c_get_value() {
    local oid="$1"

    # Parse: .1.3.6.1.4.1.25506.2.6.1.1.1.1.<sub>.<idx>
    local sub idx
    sub=$(echo "$oid" | awk -F. '{print $(NF-1)}')
    idx=$(echo "$oid" | awk -F. '{print $NF}')

    # Validate index is in our list
    local valid=0
    for i in "${ENTITY_INDICES[@]}"; do
        if [[ "$idx" == "$i" ]]; then valid=1; break; fi
    done
    if [[ $valid -eq 0 ]]; then
        reply_none
        return
    fi

    case "$sub" in
        1)   reply_value "$oid" "integer" "$idx" ;;                           # PhysicalIndex
        6)   reply_value "$oid" "integer" "$(get_cpu_usage "$idx")" ;;        # CpuUsage
        8)   reply_value "$oid" "integer" "$(get_mem_usage "$idx")" ;;        # MemUsage
        12)  reply_value "$oid" "integer" "$(get_temperature "$idx")" ;;      # Temperature
        19)  reply_value "$oid" "integer" "$(get_error_status)" ;;            # ErrorStatus
        22)  reply_value "$oid" "integer" "80" ;;                             # CpuUsageThreshold
        *)   reply_none ;;
    esac
}

h3c_get_next() {
    local requested="$1"

    for candidate in "${H3C_OIDS_SORTED[@]}"; do
        if _oid_gt "$candidate" "$requested"; then
            h3c_get_value "$candidate"
            return
        fi
    done
    reply_none
}

# ---------------------------------------------------------------------------
# Entity MIB pass_persist handler (.1.3.6.1.2.1.47)
# ---------------------------------------------------------------------------
# OID tree:
# .1.3.6.1.2.1.47.1.1.1.1.2.<idx>   entPhysicalDescr      string
# .1.3.6.1.2.1.47.1.1.1.1.5.<idx>   entPhysicalClass      integer
# .1.3.6.1.2.1.47.1.1.1.1.7.<idx>   entPhysicalName       string
# .1.3.6.1.2.1.47.1.1.1.1.8.<idx>   entPhysicalHardwareRev string
# .1.3.6.1.2.1.47.1.1.1.1.9.<idx>   entPhysicalFirmwareRev string
# .1.3.6.1.2.1.47.1.1.1.1.11.<idx>  entPhysicalSerialNum  string
# .1.3.6.1.2.1.47.1.1.1.1.13.<idx>  entPhysicalModelName  string

ENT_BASE=".1.3.6.1.2.1.47.1.1.1.1"

declare -a ENT_OIDS=()
for idx in "${ENTITY_INDICES[@]}"; do
    ENT_OIDS+=("${ENT_BASE}.2.${idx}")    # Descr
    ENT_OIDS+=("${ENT_BASE}.5.${idx}")    # Class
    ENT_OIDS+=("${ENT_BASE}.7.${idx}")    # Name
    ENT_OIDS+=("${ENT_BASE}.8.${idx}")    # HardwareRev
    ENT_OIDS+=("${ENT_BASE}.9.${idx}")    # FirmwareRev
    ENT_OIDS+=("${ENT_BASE}.11.${idx}")   # SerialNum
    ENT_OIDS+=("${ENT_BASE}.13.${idx}")   # ModelName
done

IFS=$'\n' ENT_OIDS_SORTED=($(printf '%s\n' "${ENT_OIDS[@]}" | sort -t. -k1,1n -k2,2n -k3,3n -k4,4n -k5,5n -k6,6n -k7,7n -k8,8n -k9,9n -k10,10n -k11,11n -k12,12n)); unset IFS

entity_get_value() {
    local oid="$1"
    local sub idx
    sub=$(echo "$oid" | awk -F. '{print $(NF-1)}')
    idx=$(echo "$oid" | awk -F. '{print $NF}')

    local valid=0
    for i in "${ENTITY_INDICES[@]}"; do
        if [[ "$idx" == "$i" ]]; then valid=1; break; fi
    done
    if [[ $valid -eq 0 ]]; then
        reply_none
        return
    fi

    case "$sub" in
        2)   reply_value "$oid" "string" "${ENTITY_DESCR[$idx]}" ;;
        5)   reply_value "$oid" "integer" "${ENTITY_CLASS[$idx]}" ;;
        7)   reply_value "$oid" "string" "${ENTITY_NAMES[$idx]}" ;;
        8)   reply_value "$oid" "string" "${ENTITY_HWREV[$idx]}" ;;
        9)   reply_value "$oid" "string" "${ENTITY_FWREV[$idx]}" ;;
        11)  reply_value "$oid" "string" "${ENTITY_SERIAL[$idx]}" ;;
        13)  reply_value "$oid" "string" "${ENTITY_MODEL[$idx]}" ;;
        *)   reply_none ;;
    esac
}

entity_get_next() {
    local requested="$1"

    for candidate in "${ENT_OIDS_SORTED[@]}"; do
        if _oid_gt "$candidate" "$requested"; then
            entity_get_value "$candidate"
            return
        fi
    done
    reply_none
}

# ---------------------------------------------------------------------------
# OID comparison utility
# ---------------------------------------------------------------------------
# Returns 0 (true) if oid_a > oid_b in numeric dotted notation.

_oid_gt() {
    local a="$1" b="$2"

    # Strip leading dots for comparison
    a="${a#.}"
    b="${b#.}"

    IFS='.' read -ra partsA <<< "$a"
    IFS='.' read -ra partsB <<< "$b"

    local len=${#partsA[@]}
    local lenB=${#partsB[@]}
    if (( lenB > len )); then
        len=$lenB
    fi

    for (( i=0; i<len; i++ )); do
        local va=${partsA[$i]:-0}
        local vb=${partsB[$i]:-0}

        # If B ran out of components but A hasn't, A is longer → A > B only if
        # all prior components are equal (which they are if we got here)
        if (( i >= ${#partsB[@]} )); then
            return 0   # a > b (a is deeper in tree)
        fi
        if (( i >= ${#partsA[@]} )); then
            return 1   # a < b
        fi

        if (( va > vb )); then
            return 0
        elif (( va < vb )); then
            return 1
        fi
    done

    # Equal — not strictly greater
    return 1
}

# ---------------------------------------------------------------------------
# pass_persist main loops
# ---------------------------------------------------------------------------

run_h3c_persist() {
    log "H3C pass_persist handler started (PID $$)"
    while read -r cmd; do
        cmd=$(echo "$cmd" | tr -d '\r\n')
        case "$cmd" in
            PING)
                echo "PONG"
                ;;
            get)
                read -r oid
                oid=$(echo "$oid" | tr -d '\r\n')
                h3c_get_value "$oid"
                ;;
            getnext)
                read -r oid
                oid=$(echo "$oid" | tr -d '\r\n')
                h3c_get_next "$oid"
                ;;
            set)
                # Read the OID line
                read -r _setoid
                # Read the type+value line
                read -r _setval
                echo "not-writable"
                ;;
            "")
                # Blank line; ignore
                ;;
            *)
                log "H3C: unknown command '$cmd'"
                echo "NONE"
                ;;
        esac
    done
    log "H3C pass_persist handler exiting"
}

run_entity_persist() {
    log "Entity MIB pass_persist handler started (PID $$)"
    while read -r cmd; do
        cmd=$(echo "$cmd" | tr -d '\r\n')
        case "$cmd" in
            PING)
                echo "PONG"
                ;;
            get)
                read -r oid
                oid=$(echo "$oid" | tr -d '\r\n')
                entity_get_value "$oid"
                ;;
            getnext)
                read -r oid
                oid=$(echo "$oid" | tr -d '\r\n')
                entity_get_next "$oid"
                ;;
            set)
                read -r _setoid
                read -r _setval
                echo "not-writable"
                ;;
            "")
                ;;
            *)
                log "Entity: unknown command '$cmd'"
                echo "NONE"
                ;;
        esac
    done
    log "Entity MIB pass_persist handler exiting"
}

# ---------------------------------------------------------------------------
# Dispatch pass_persist modes
# ---------------------------------------------------------------------------

case "${1:-}" in
    pass_persist_h3c)
        run_h3c_persist
        ;;
    pass_persist_entity)
        run_entity_persist
        ;;
    *)
        echo "Usage: $0 {cpu_usage|mem_usage|temperature|fan_speed|psu_status|hw_health|pass_persist_h3c|pass_persist_entity}" >&2
        exit 1
        ;;
esac
