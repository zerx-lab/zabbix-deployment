#!/bin/bash
# =============================================================================
# snmp_pass_h3c.sh — One-shot `pass` handler for H3C Entity Extension MIB
# =============================================================================
# Called by snmpd via the `pass` directive for OID tree .1.3.6.1.4.1.25506
#
# Protocol (pass mode):
#   script -g <OID>           → GET:     print OID\ntype\nvalue  (or exit 1)
#   script -n <OID>           → GETNEXT: print next OID\ntype\nvalue
#   script -s <OID> <T> <V>  → SET:     not supported
#
# Simulated OID tree (HH3C-ENTITY-EXT-MIB):
#   Base: .1.3.6.1.4.1.25506.2.6.1.1.1.1
#     .1.{idx}   hh3cEntityExtPhysicalIndex     integer
#     .6.{idx}   hh3cEntityExtCpuUsage          integer (0-100 %)
#     .8.{idx}   hh3cEntityExtMemUsage          integer (0-100 %)
#     .12.{idx}  hh3cEntityExtTemperature        integer (°C)
#     .19.{idx}  hh3cEntityExtErrorStatus        integer (0=normal)
#     .22.{idx}  hh3cEntityExtCpuUsageThreshold  integer (default 80)
#
# Entity indices: 1 2 3 4 5
# =============================================================================

set -euo pipefail

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
BASE=".1.3.6.1.4.1.25506.2.6.1.1.1.1"

# Sub-OID identifiers within the table row entry
SUBS=(1 6 8 12 19 22)

# Entity indices (simulated modules/slots)
INDICES=(1 2 3 4 5)

# ---------------------------------------------------------------------------
# Build the full sorted OID list
# ---------------------------------------------------------------------------
# We build the list in the correct numerical order:
#   base.sub.idx  sorted by sub (ascending) then idx (ascending)
# This matches SNMP lexicographic ordering for a columnar table.

ALL_OIDS=()
for sub in "${SUBS[@]}"; do
    for idx in "${INDICES[@]}"; do
        ALL_OIDS+=("${BASE}.${sub}.${idx}")
    done
done

# ---------------------------------------------------------------------------
# Sensor value generators (slightly randomised per call)
# ---------------------------------------------------------------------------
_rand() {
    local min=$1 max=$2
    local range=$(( max - min + 1 ))
    local raw
    raw=$(od -An -tu2 -N2 /dev/urandom 2>/dev/null | tr -d ' ')
    echo $(( min + raw % range ))
}

get_cpu() {
    local idx=$1
    case $idx in
        1) _rand 15 45 ;;
        2) _rand  5 20 ;;
        3) _rand  2 10 ;;
        4) _rand  1  5 ;;
        5) _rand  3 12 ;;
        *) _rand 10 35 ;;
    esac
}

get_mem() {
    local idx=$1
    case $idx in
        1) _rand 40 70 ;;
        2) _rand 25 45 ;;
        3) _rand 15 30 ;;
        4) _rand 10 25 ;;
        5) _rand 20 40 ;;
        *) _rand 30 55 ;;
    esac
}

get_temp() {
    local idx=$1
    case $idx in
        1) _rand 38 52 ;;
        2) _rand 35 48 ;;
        3) _rand 25 30 ;;
        4) _rand 30 42 ;;
        5) _rand 28 36 ;;
        *) _rand 30 45 ;;
    esac
}

# ---------------------------------------------------------------------------
# Resolve an exact OID to its type and value
# Returns 0 on success (prints type\nvalue), 1 if OID not in our tree
# ---------------------------------------------------------------------------
resolve_oid() {
    local oid="$1"

    # Strip the base prefix to get .sub.idx
    local suffix="${oid#${BASE}}"
    # suffix should be like ".6.1"

    # Parse sub and idx
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

    # Generate the value based on sub-OID
    local type="integer"
    local value=""

    case "$sub" in
        1)  value="$idx" ;;                    # PhysicalIndex = idx itself
        6)  value="$(get_cpu "$idx")" ;;       # CpuUsage
        8)  value="$(get_mem "$idx")" ;;       # MemUsage
        12) value="$(get_temp "$idx")" ;;      # Temperature
        19) value="0" ;;                       # ErrorStatus (0 = normal)
        22) value="80" ;;                      # CpuUsageThreshold
        *)  return 1 ;;
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

    # They are equal
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
