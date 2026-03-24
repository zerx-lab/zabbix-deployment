#!/bin/bash
# =============================================================================
# snmp_pass_entity.sh — One-shot `pass` handler for Entity Physical MIB
# =============================================================================
# Called by snmpd via the `pass` directive for OID tree .1.3.6.1.2.1.47
#
# Protocol (pass mode):
#   script -g <OID>           → GET:     print OID\ntype\nvalue  (or exit 1)
#   script -n <OID>           → GETNEXT: print next OID\ntype\nvalue
#   script -s <OID> <T> <V>  → SET:     not supported
#
# Simulated OID tree (ENTITY-MIB entPhysicalTable):
#   Base: .1.3.6.1.2.1.47.1.1.1.1
#     .2.{idx}   entPhysicalDescr         string
#     .5.{idx}   entPhysicalClass         integer
#     .7.{idx}   entPhysicalName          string
#     .8.{idx}   entPhysicalHardwareRev   string
#     .9.{idx}   entPhysicalFirmwareRev   string
#     .11.{idx}  entPhysicalSerialNum     string
#     .13.{idx}  entPhysicalModelName     string
#
# Entity indices: 1 2 3 4 5
#
# entPhysicalClass values:
#   3=chassis, 5=container, 6=powerSupply, 7=fan, 8=sensor, 9=module, 10=port
# =============================================================================

set -euo pipefail

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
BASE=".1.3.6.1.2.1.47.1.1.1.1"

# Sub-OID column identifiers within entPhysicalEntry — sorted numerically
SUBS=(2 5 7 8 9 11 13)

# Entity row indices (simulated modules/slots)
INDICES=(1 2 3 4 5)

# ---------------------------------------------------------------------------
# Static entity data (associative arrays)
# ---------------------------------------------------------------------------
declare -A ENT_DESCR=(
    [1]="Main Processing Unit - Slot 0"
    [2]="Standby Processing Unit - Slot 1"
    [3]="Cooling Fan Module 1"
    [4]="Power Supply Module 1"
    [5]="Environmental Sensor Module 1"
)

declare -A ENT_CLASS=(
    [1]=9    # module
    [2]=9    # module
    [3]=7    # fan
    [4]=6    # powerSupply
    [5]=8    # sensor
)

declare -A ENT_NAME=(
    [1]="Slot 0/CPU 0"
    [2]="Slot 1/CPU 0"
    [3]="Slot 0/Fan 1"
    [4]="Slot 0/Power 1"
    [5]="Slot 0/Sensor 1"
)

declare -A ENT_HWREV=(
    [1]="REV.A"
    [2]="REV.A"
    [3]="REV.B"
    [4]="REV.C"
    [5]="REV.A"
)

declare -A ENT_FWREV=(
    [1]="7.1.075"
    [2]="7.1.075"
    [3]=""
    [4]=""
    [5]=""
)

declare -A ENT_SERIAL=(
    [1]="SIM0000000001"
    [2]="SIM0000000002"
    [3]="SIM0000000003"
    [4]="SIM0000000004"
    [5]="SIM0000000005"
)

declare -A ENT_MODEL=(
    [1]="SR8800-MPU"
    [2]="SR8800-MPU"
    [3]="SR8800-FAN"
    [4]="SR8800-PSU"
    [5]="SR8800-SENSOR"
)

# ---------------------------------------------------------------------------
# Build the full sorted OID list
# ---------------------------------------------------------------------------
# Columns are iterated first (sub), then rows within each column (idx).
# This matches SNMP lexicographic column-major ordering for tabular objects.

ALL_OIDS=()
for sub in "${SUBS[@]}"; do
    for idx in "${INDICES[@]}"; do
        ALL_OIDS+=("${BASE}.${sub}.${idx}")
    done
done

# ---------------------------------------------------------------------------
# Resolve an exact OID to its type and value
# Returns 0 on success (prints oid\ntype\nvalue), 1 if OID not in our tree
# ---------------------------------------------------------------------------
resolve_oid() {
    local oid="$1"

    # Strip the base prefix to get .sub.idx
    local suffix="${oid#${BASE}}"
    # suffix should look like ".7.3"

    local sub idx
    sub=$(echo "$suffix" | awk -F. '{print $2}')
    idx=$(echo "$suffix" | awk -F. '{print $3}')

    # Validate sub is one we handle
    local valid_sub=0
    for s in "${SUBS[@]}"; do
        if [[ "$sub" == "$s" ]]; then valid_sub=1; break; fi
    done
    [[ $valid_sub -eq 0 ]] && return 1

    # Validate idx is in our entity list
    local valid_idx=0
    for i in "${INDICES[@]}"; do
        if [[ "$idx" == "$i" ]]; then valid_idx=1; break; fi
    done
    [[ $valid_idx -eq 0 ]] && return 1

    local type=""
    local value=""

    case "$sub" in
        2)
            type="string"
            value="${ENT_DESCR[$idx]}"
            ;;
        5)
            type="integer"
            value="${ENT_CLASS[$idx]}"
            ;;
        7)
            type="string"
            value="${ENT_NAME[$idx]}"
            ;;
        8)
            type="string"
            value="${ENT_HWREV[$idx]}"
            ;;
        9)
            type="string"
            value="${ENT_FWREV[$idx]}"
            ;;
        11)
            type="string"
            value="${ENT_SERIAL[$idx]}"
            ;;
        13)
            type="string"
            value="${ENT_MODEL[$idx]}"
            ;;
        *)
            return 1
            ;;
    esac

    echo "$oid"
    echo "$type"
    echo "$value"
    return 0
}

# ---------------------------------------------------------------------------
# OID numerical comparison
# Returns true (0) if oid_a > oid_b in SNMP lexicographic order
# ---------------------------------------------------------------------------
oid_gt() {
    local a="${1#.}" b="${2#.}"

    IFS='.' read -ra pa <<< "$a"
    IFS='.' read -ra pb <<< "$b"

    local len_a=${#pa[@]}
    local len_b=${#pb[@]}
    local max_len=$(( len_a > len_b ? len_a : len_b ))

    for (( i = 0; i < max_len; i++ )); do
        local va=${pa[$i]:-}
        local vb=${pb[$i]:-}

        # If a ran out of components first, a < b (a is a prefix of b)
        if [[ -z "$va" ]]; then return 1; fi
        # If b ran out of components first, a > b
        if [[ -z "$vb" ]]; then return 0; fi

        if (( va > vb )); then return 0; fi
        if (( va < vb )); then return 1; fi
    done

    # They are equal — not strictly greater
    return 1
}

# ---------------------------------------------------------------------------
# Handle GETNEXT — find the lexicographically next OID after the requested one
# ---------------------------------------------------------------------------
do_getnext() {
    local requested="$1"

    for candidate in "${ALL_OIDS[@]}"; do
        if oid_gt "$candidate" "$requested"; then
            resolve_oid "$candidate"
            return $?
        fi
    done

    # No next OID — end of our subtree
    return 1
}

# ---------------------------------------------------------------------------
# Handle GET — exact match only
# ---------------------------------------------------------------------------
do_get() {
    local oid="$1"
    resolve_oid "$oid"
    return $?
}

# ---------------------------------------------------------------------------
# Main dispatch
# ---------------------------------------------------------------------------
case "${1:-}" in
    -g)
        # GET request
        do_get "${2:-}" || exit 1
        ;;
    -n)
        # GETNEXT request
        do_getnext "${2:-}" || exit 1
        ;;
    -s)
        # SET request — not supported
        echo "not-writable"
        exit 0
        ;;
    *)
        echo "Usage: $0 {-g OID | -n OID | -s OID TYPE VALUE}" >&2
        exit 1
        ;;
esac

exit 0
