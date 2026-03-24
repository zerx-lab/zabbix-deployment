#!/bin/bash
# =============================================================================
# test-snmp-simulator.sh — Comprehensive SNMP Simulator Verification
# =============================================================================
# Validates that the SNMP simulator container is running and returning
# expected monitoring data across all supported MIB trees.
#
# Usage:
#   ./scripts/test-snmp-simulator.sh [OPTIONS]
#
# Options:
#   -h, --host HOST        Target host/IP (default: snmp-sim or localhost)
#   -p, --port PORT        Target SNMP port (default: 161 for container, 10161 for host)
#   -c, --community STR    SNMPv2c community string (default: public)
#   -v, --verbose          Show full SNMP output for each test
#   -q, --quiet            Only show pass/fail summary
#   --from-host            Run tests from host machine (uses localhost:10161)
#   --skip-v3              Skip SNMPv3 tests
#   --skip-h3c             Skip H3C private MIB tests
#   --help                 Show this help
#
# Exit codes:
#   0  All tests passed
#   1  One or more tests failed
#   2  Prerequisites not met (snmp tools missing, container not running)
# =============================================================================

set -euo pipefail

# ---------------------------------------------------------------------------
# Default configuration
# ---------------------------------------------------------------------------
TARGET_HOST="${SNMP_TEST_HOST:-snmp-sim}"
TARGET_PORT="${SNMP_TEST_PORT:-161}"
COMMUNITY="${SNMP_TEST_COMMUNITY:-public}"
VERBOSE=0
QUIET=0
FROM_HOST=0
SKIP_V3=0
SKIP_H3C=0
TIMEOUT=5
RETRIES=1

# SNMPv3 credentials (must match snmpd.conf createUser)
V3_USER="zabbixuser"
V3_AUTH_PROTO="SHA"
V3_AUTH_PASS="myauthpass"
V3_PRIV_PROTO="AES"
V3_PRIV_PASS="myprivpass"

# ---------------------------------------------------------------------------
# Counters
# ---------------------------------------------------------------------------
TESTS_TOTAL=0
TESTS_PASSED=0
TESTS_FAILED=0
TESTS_SKIPPED=0

# ---------------------------------------------------------------------------
# Colors (auto-detect terminal support)
# ---------------------------------------------------------------------------
if [[ -t 1 ]] && command -v tput &>/dev/null && [[ "$(tput colors 2>/dev/null || echo 0)" -ge 8 ]]; then
    RED=$(tput setaf 1)
    GREEN=$(tput setaf 2)
    YELLOW=$(tput setaf 3)
    BLUE=$(tput setaf 4)
    CYAN=$(tput setaf 6)
    BOLD=$(tput bold)
    DIM=$(tput dim)
    RESET=$(tput sgr0)
else
    RED="" GREEN="" YELLOW="" BLUE="" CYAN="" BOLD="" DIM="" RESET=""
fi

# ---------------------------------------------------------------------------
# Parse arguments
# ---------------------------------------------------------------------------
while [[ $# -gt 0 ]]; do
    case "$1" in
        -h|--host)
            TARGET_HOST="$2"; shift 2 ;;
        -p|--port)
            TARGET_PORT="$2"; shift 2 ;;
        -c|--community)
            COMMUNITY="$2"; shift 2 ;;
        -v|--verbose)
            VERBOSE=1; shift ;;
        -q|--quiet)
            QUIET=1; shift ;;
        --from-host)
            FROM_HOST=1; shift ;;
        --skip-v3)
            SKIP_V3=1; shift ;;
        --skip-h3c)
            SKIP_H3C=1; shift ;;
        --help)
            head -30 "$0" | grep '^#' | sed 's/^# \?//'
            exit 0 ;;
        *)
            echo "${RED}Unknown option: $1${RESET}" >&2
            echo "Use --help for usage information" >&2
            exit 2 ;;
    esac
done

# Adjust defaults for host-mode testing
if [[ $FROM_HOST -eq 1 ]]; then
    TARGET_HOST="${SNMP_TEST_HOST:-localhost}"
    TARGET_PORT="${SNMP_TEST_PORT:-10161}"
fi

# Build the target address string for snmp commands
if [[ "$TARGET_PORT" != "161" ]]; then
    SNMP_TARGET="${TARGET_HOST}:${TARGET_PORT}"
else
    SNMP_TARGET="${TARGET_HOST}"
fi

# ---------------------------------------------------------------------------
# Logging helpers
# ---------------------------------------------------------------------------
log_info() {
    [[ $QUIET -eq 1 ]] && return
    echo "${BLUE}[INFO]${RESET} $*"
}

log_section() {
    [[ $QUIET -eq 1 ]] && return
    echo ""
    echo "${BOLD}${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${RESET}"
    echo "${BOLD}${CYAN}  $*${RESET}"
    echo "${BOLD}${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${RESET}"
}

log_subsection() {
    [[ $QUIET -eq 1 ]] && return
    echo ""
    echo "  ${BOLD}── $* ──${RESET}"
}

log_verbose() {
    if [[ $VERBOSE -eq 1 ]] && [[ $QUIET -eq 0 ]]; then
        echo "${DIM}    $*${RESET}"
    fi
}

# ---------------------------------------------------------------------------
# Test assertion helpers
# ---------------------------------------------------------------------------

# run_test <test_name> <expected_pattern> <snmp_command...>
#
# Executes the given snmp command, checks the output matches the expected
# pattern (grep -qE), and records pass/fail.
run_test() {
    local test_name="$1"
    local expected_pattern="$2"
    shift 2
    local cmd=("$@")

    TESTS_TOTAL=$((TESTS_TOTAL + 1))

    local output
    local exit_code=0
    output=$("${cmd[@]}" 2>&1) || exit_code=$?

    log_verbose "CMD: ${cmd[*]}"

    if [[ $exit_code -ne 0 ]]; then
        TESTS_FAILED=$((TESTS_FAILED + 1))
        if [[ $QUIET -eq 0 ]]; then
            echo "  ${RED}✗${RESET} ${test_name}"
            echo "    ${DIM}Command exited with code ${exit_code}${RESET}"
            echo "    ${DIM}Output: ${output:0:200}${RESET}"
        fi
        return 1
    fi

    if echo "$output" | grep -qE "$expected_pattern"; then
        TESTS_PASSED=$((TESTS_PASSED + 1))
        if [[ $QUIET -eq 0 ]]; then
            echo "  ${GREEN}✓${RESET} ${test_name}"
        fi
        log_verbose "Output: ${output:0:200}"
        return 0
    else
        TESTS_FAILED=$((TESTS_FAILED + 1))
        if [[ $QUIET -eq 0 ]]; then
            echo "  ${RED}✗${RESET} ${test_name}"
            echo "    ${DIM}Expected pattern: ${expected_pattern}${RESET}"
            echo "    ${DIM}Got: ${output:0:300}${RESET}"
        fi
        return 1
    fi
}

# run_walk_test <test_name> <min_lines> <snmp_walk_command...>
#
# Executes an snmpwalk, verifies it returns at least min_lines of output.
run_walk_test() {
    local test_name="$1"
    local min_lines="$2"
    shift 2
    local cmd=("$@")

    TESTS_TOTAL=$((TESTS_TOTAL + 1))

    local output
    local exit_code=0
    output=$("${cmd[@]}" 2>&1) || exit_code=$?

    log_verbose "CMD: ${cmd[*]}"

    if [[ $exit_code -ne 0 ]]; then
        TESTS_FAILED=$((TESTS_FAILED + 1))
        if [[ $QUIET -eq 0 ]]; then
            echo "  ${RED}✗${RESET} ${test_name}"
            echo "    ${DIM}Walk command failed (exit code ${exit_code})${RESET}"
            echo "    ${DIM}Output: ${output:0:200}${RESET}"
        fi
        return 1
    fi

    local line_count
    line_count=$(echo "$output" | grep -c '.' || true)

    if [[ $line_count -ge $min_lines ]]; then
        TESTS_PASSED=$((TESTS_PASSED + 1))
        if [[ $QUIET -eq 0 ]]; then
            echo "  ${GREEN}✓${RESET} ${test_name} (${line_count} entries)"
        fi
        log_verbose "First 5 lines:"
        if [[ $VERBOSE -eq 1 ]]; then
            echo "$output" | head -5 | while IFS= read -r line; do
                log_verbose "  $line"
            done
        fi
        return 0
    else
        TESTS_FAILED=$((TESTS_FAILED + 1))
        if [[ $QUIET -eq 0 ]]; then
            echo "  ${RED}✗${RESET} ${test_name} (got ${line_count} entries, expected >= ${min_lines})"
            echo "    ${DIM}Output: ${output:0:300}${RESET}"
        fi
        return 1
    fi
}

# skip_test <test_name> <reason>
skip_test() {
    local test_name="$1"
    local reason="$2"
    TESTS_TOTAL=$((TESTS_TOTAL + 1))
    TESTS_SKIPPED=$((TESTS_SKIPPED + 1))
    if [[ $QUIET -eq 0 ]]; then
        echo "  ${YELLOW}⊘${RESET} ${test_name} ${DIM}(skipped: ${reason})${RESET}"
    fi
}

# ---------------------------------------------------------------------------
# Common snmp command builders
# ---------------------------------------------------------------------------
snmpget_v2() {
    snmpget -v2c -c "$COMMUNITY" -t "$TIMEOUT" -r "$RETRIES" "$SNMP_TARGET" "$@"
}

snmpwalk_v2() {
    snmpwalk -v2c -c "$COMMUNITY" -t "$TIMEOUT" -r "$RETRIES" "$SNMP_TARGET" "$@"
}

snmpget_v3() {
    snmpget -v3 -u "$V3_USER" -l authPriv \
        -a "$V3_AUTH_PROTO" -A "$V3_AUTH_PASS" \
        -x "$V3_PRIV_PROTO" -X "$V3_PRIV_PASS" \
        -t "$TIMEOUT" -r "$RETRIES" \
        "$SNMP_TARGET" "$@"
}

snmpwalk_v3() {
    snmpwalk -v3 -u "$V3_USER" -l authPriv \
        -a "$V3_AUTH_PROTO" -A "$V3_AUTH_PASS" \
        -x "$V3_PRIV_PROTO" -X "$V3_PRIV_PASS" \
        -t "$TIMEOUT" -r "$RETRIES" \
        "$SNMP_TARGET" "$@"
}

# ---------------------------------------------------------------------------
# Prerequisites check
# ---------------------------------------------------------------------------
check_prerequisites() {
    log_section "Prerequisites Check"

    local ok=1

    # Check for snmp tools
    for tool in snmpget snmpwalk snmpbulkwalk; do
        if command -v "$tool" &>/dev/null; then
            log_info "$tool found: $(command -v "$tool")"
        else
            echo "${RED}[ERROR]${RESET} $tool not found. Install net-snmp-tools / net-snmp-utils"
            ok=0
        fi
    done

    if [[ $ok -eq 0 ]]; then
        echo ""
        echo "${YELLOW}Hint: Install SNMP tools with:${RESET}"
        echo "  Alpine:  apk add net-snmp-tools"
        echo "  Debian:  apt-get install snmp"
        echo "  RHEL:    dnf install net-snmp-utils"
        echo "  macOS:   brew install net-snmp"
        echo ""
        echo "Or run this script inside the snmp-test-client container:"
        echo "  docker exec -it snmp-test-client bash /app/scripts/test-snmp-simulator.sh"
        exit 2
    fi

    # Quick connectivity test
    log_info "Testing SNMP connectivity to ${SNMP_TARGET}..."
    local probe_output
    local probe_exit=0
    probe_output=$(snmpget -v2c -c "$COMMUNITY" -t 3 -r 2 "$SNMP_TARGET" 1.3.6.1.2.1.1.1.0 2>&1) || probe_exit=$?

    if [[ $probe_exit -ne 0 ]]; then
        echo ""
        echo "${RED}[ERROR]${RESET} Cannot reach SNMP agent at ${SNMP_TARGET}"
        echo "${DIM}Output: ${probe_output}${RESET}"
        echo ""
        echo "${YELLOW}Troubleshooting:${RESET}"
        echo "  1. Check if the snmp-simulator container is running:"
        echo "     docker ps | grep snmp-simulator"
        echo ""
        echo "  2. Check container logs:"
        echo "     docker logs snmp-simulator"
        echo ""
        echo "  3. If running from host, use --from-host flag (maps to localhost:10161)"
        echo ""
        echo "  4. Start the SNMP test stack:"
        echo "     docker compose -f docker/docker-compose.snmp-test.yml up -d"
        exit 2
    fi

    log_info "${GREEN}SNMP agent reachable${RESET} — ${probe_output:0:100}"
}

# =============================================================================
# TEST SUITES
# =============================================================================

# ---------------------------------------------------------------------------
# 1. SNMPv2-MIB System Group (1.3.6.1.2.1.1)
# ---------------------------------------------------------------------------
test_system_mib() {
    log_section "1. SNMPv2-MIB — System Group"

    log_subsection "Individual System OIDs"

    run_test "sysDescr.0 — System description contains device info" \
        "(H3C|Simulated|Switch|SR8800)" \
        snmpget_v2 1.3.6.1.2.1.1.1.0 \
        || true

    run_test "sysObjectID.0 — Returns valid OID" \
        "OID.*1\.3\.6\.1\.4\.1\." \
        snmpget_v2 1.3.6.1.2.1.1.2.0 \
        || true

    run_test "sysUpTime.0 — Returns timeticks value" \
        "(Timeticks|timeticks|[0-9]+)" \
        snmpget_v2 1.3.6.1.2.1.1.3.0 \
        || true

    run_test "sysContact.0 — Returns contact info" \
        "(NOC|noc|contact|admin|Team)" \
        snmpget_v2 1.3.6.1.2.1.1.4.0 \
        || true

    run_test "sysName.0 — Returns device hostname" \
        "(H3C|OBM|SIM|h3c)" \
        snmpget_v2 1.3.6.1.2.1.1.5.0 \
        || true

    run_test "sysLocation.0 — Returns location string" \
        "(DC|Beijing|Rack|Simulated|rack)" \
        snmpget_v2 1.3.6.1.2.1.1.6.0 \
        || true

    run_test "sysServices.0 — Returns integer value" \
        "(INTEGER|integer|[0-9]+)" \
        snmpget_v2 1.3.6.1.2.1.1.7.0 \
        || true

    log_subsection "System Group Walk"

    run_walk_test "Walk system tree (1.3.6.1.2.1.1) — at least 7 entries" 7 \
        snmpwalk_v2 1.3.6.1.2.1.1 \
        || true
}

# ---------------------------------------------------------------------------
# 2. IF-MIB — Interfaces (1.3.6.1.2.1.2 and 1.3.6.1.2.1.31)
# ---------------------------------------------------------------------------
test_if_mib() {
    log_section "2. IF-MIB — Network Interfaces"

    log_subsection "Interface Table (ifTable)"

    run_test "ifNumber.0 — Number of interfaces present" \
        "(INTEGER|integer|[0-9]+)" \
        snmpget_v2 1.3.6.1.2.1.2.1.0 \
        || true

    run_walk_test "Walk ifTable (1.3.6.1.2.1.2.2) — at least 1 interface" 1 \
        snmpwalk_v2 1.3.6.1.2.1.2.2 \
        || true

    log_subsection "Interface Details (per-interface OIDs)"

    # ifDescr for index 1
    run_test "ifDescr.1 — First interface has a description" \
        "(STRING|string|eth|lo|[a-zA-Z])" \
        snmpget_v2 1.3.6.1.2.1.2.2.1.2.1 \
        || true

    # ifType for index 1
    run_test "ifType.1 — Interface type is valid" \
        "(INTEGER|integer|[0-9]+)" \
        snmpget_v2 1.3.6.1.2.1.2.2.1.3.1 \
        || true

    # ifAdminStatus for index 1
    run_test "ifAdminStatus.1 — Admin status (1=up)" \
        "(INTEGER|integer|[0-9]+)" \
        snmpget_v2 1.3.6.1.2.1.2.2.1.7.1 \
        || true

    # ifOperStatus for index 1
    run_test "ifOperStatus.1 — Operational status" \
        "(INTEGER|integer|[0-9]+)" \
        snmpget_v2 1.3.6.1.2.1.2.2.1.8.1 \
        || true

    # ifInOctets for index 1
    run_test "ifInOctets.1 — Inbound traffic counter" \
        "(Counter|counter|Counter32|[0-9]+)" \
        snmpget_v2 1.3.6.1.2.1.2.2.1.10.1 \
        || true

    # ifOutOctets for index 1
    run_test "ifOutOctets.1 — Outbound traffic counter" \
        "(Counter|counter|Counter32|[0-9]+)" \
        snmpget_v2 1.3.6.1.2.1.2.2.1.16.1 \
        || true

    # ifInErrors for index 1
    run_test "ifInErrors.1 — Inbound error counter" \
        "(Counter|counter|Counter32|[0-9]+)" \
        snmpget_v2 1.3.6.1.2.1.2.2.1.14.1 \
        || true

    # ifOutErrors for index 1
    run_test "ifOutErrors.1 — Outbound error counter" \
        "(Counter|counter|Counter32|[0-9]+)" \
        snmpget_v2 1.3.6.1.2.1.2.2.1.20.1 \
        || true

    # ifInDiscards for index 1
    run_test "ifInDiscards.1 — Inbound discard counter" \
        "(Counter|counter|Counter32|[0-9]+)" \
        snmpget_v2 1.3.6.1.2.1.2.2.1.13.1 \
        || true

    # ifOutDiscards for index 1
    run_test "ifOutDiscards.1 — Outbound discard counter" \
        "(Counter|counter|Counter32|[0-9]+)" \
        snmpget_v2 1.3.6.1.2.1.2.2.1.19.1 \
        || true

    log_subsection "IF-MIB Extended (ifXTable — 64-bit counters)"

    run_walk_test "Walk ifXTable (1.3.6.1.2.1.31.1.1) — HC counters for LLD" 1 \
        snmpwalk_v2 1.3.6.1.2.1.31.1.1 \
        || true
}

# ---------------------------------------------------------------------------
# 3. HOST-RESOURCES-MIB (1.3.6.1.2.1.25)
# ---------------------------------------------------------------------------
test_host_resources_mib() {
    log_section "3. HOST-RESOURCES-MIB"

    run_test "hrSystemUptime.0 — Host uptime in hundredths of seconds" \
        "(Timeticks|timeticks|INTEGER|integer|[0-9]+)" \
        snmpget_v2 1.3.6.1.2.1.25.1.1.0 \
        || true

    run_walk_test "Walk hrStorage (1.3.6.1.2.1.25.2) — Storage entries" 1 \
        snmpwalk_v2 1.3.6.1.2.1.25.2 \
        || true

    run_walk_test "Walk hrDevice (1.3.6.1.2.1.25.3) — Device entries" 1 \
        snmpwalk_v2 1.3.6.1.2.1.25.3 \
        || true
}

# ---------------------------------------------------------------------------
# 4. Entity Physical MIB (1.3.6.1.2.1.47) — via pass_persist
# ---------------------------------------------------------------------------
test_entity_mib() {
    log_section "4. Entity Physical MIB (entPhysicalTable)"

    log_subsection "Entity Physical Entries (index 1-5)"

    for idx in 1 2 3 4 5; do
        run_test "entPhysicalName.${idx} — Entity name for index ${idx}" \
            "(STRING|string|Slot|CPU|Fan|Power|Sensor)" \
            snmpget_v2 "1.3.6.1.2.1.47.1.1.1.1.7.${idx}" \
            || true
    done

    run_test "entPhysicalDescr.1 — Description for index 1" \
        "(STRING|string|Processing|Module)" \
        snmpget_v2 1.3.6.1.2.1.47.1.1.1.1.2.1 \
        || true

    run_test "entPhysicalClass.1 — Physical class (integer)" \
        "(INTEGER|integer|[0-9]+)" \
        snmpget_v2 1.3.6.1.2.1.47.1.1.1.1.5.1 \
        || true

    run_test "entPhysicalSerialNum.1 — Serial number" \
        "(STRING|string|SIM)" \
        snmpget_v2 1.3.6.1.2.1.47.1.1.1.1.11.1 \
        || true

    run_test "entPhysicalModelName.1 — Model name" \
        "(STRING|string|SR8800)" \
        snmpget_v2 1.3.6.1.2.1.47.1.1.1.1.13.1 \
        || true

    log_subsection "Entity Table Walk (for Zabbix LLD)"

    run_walk_test "Walk entPhysicalTable (1.3.6.1.2.1.47.1.1.1) — all entity entries" 5 \
        snmpwalk_v2 1.3.6.1.2.1.47.1.1.1 \
        || true
}

# ---------------------------------------------------------------------------
# 5. HH3C Entity Extension MIB (1.3.6.1.4.1.25506) — via pass_persist
# ---------------------------------------------------------------------------
test_h3c_entity_ext_mib() {
    if [[ $SKIP_H3C -eq 1 ]]; then
        log_section "5. HH3C Entity Extension MIB (SKIPPED)"
        skip_test "H3C Entity Extension MIB" "--skip-h3c flag set"
        return
    fi

    log_section "5. HH3C Entity Extension MIB"

    local h3c_base="1.3.6.1.4.1.25506.2.6.1.1.1.1"

    log_subsection "CPU Utilization (hh3cEntityExtCpuUsage)"

    for idx in 1 2; do
        run_test "hh3cEntityExtCpuUsage.${idx} — CPU usage for entity ${idx} (0-100%)" \
            "(INTEGER|integer|[0-9]+)" \
            snmpget_v2 "${h3c_base}.6.${idx}" \
            || true
    done

    log_subsection "Memory Utilization (hh3cEntityExtMemUsage)"

    for idx in 1 2; do
        run_test "hh3cEntityExtMemUsage.${idx} — Memory usage for entity ${idx} (0-100%)" \
            "(INTEGER|integer|[0-9]+)" \
            snmpget_v2 "${h3c_base}.8.${idx}" \
            || true
    done

    log_subsection "Temperature (hh3cEntityExtTemperature)"

    for idx in 1 2 3 4 5; do
        run_test "hh3cEntityExtTemperature.${idx} — Temperature for entity ${idx} (°C)" \
            "(INTEGER|integer|[0-9]+)" \
            snmpget_v2 "${h3c_base}.12.${idx}" \
            || true
    done

    log_subsection "Error Status (hh3cEntityExtErrorStatus)"

    for idx in 1 2; do
        run_test "hh3cEntityExtErrorStatus.${idx} — Error status for entity ${idx} (0=normal)" \
            "(INTEGER|integer|0)" \
            snmpget_v2 "${h3c_base}.19.${idx}" \
            || true
    done

    log_subsection "Physical Index (hh3cEntityExtPhysicalIndex)"

    run_test "hh3cEntityExtPhysicalIndex.1 — Physical index reference" \
        "(INTEGER|integer|1)" \
        snmpget_v2 "${h3c_base}.1.1" \
        || true

    log_subsection "CPU Usage Threshold"

    run_test "hh3cEntityExtCpuUsageThreshold.1 — Threshold value (80)" \
        "(INTEGER|integer|80)" \
        snmpget_v2 "${h3c_base}.22.1" \
        || true

    log_subsection "H3C Entity Walk (for Zabbix LLD entity.discovery)"

    run_walk_test "Walk HH3C Entity Ext (1.3.6.1.4.1.25506.2.6.1.1.1) — full entity tree" 5 \
        snmpwalk_v2 1.3.6.1.4.1.25506.2.6.1.1.1 \
        || true
}

# ---------------------------------------------------------------------------
# 6. NET-SNMP-EXTEND-MIB (1.3.6.1.4.1.8072.1.3.2) — extend scripts
# ---------------------------------------------------------------------------
test_extend_mib() {
    log_section "6. NET-SNMP-EXTEND-MIB (Extend Scripts)"

    run_walk_test "Walk extend table (1.3.6.1.4.1.8072.1.3.2) — all extend outputs" 1 \
        snmpwalk_v2 1.3.6.1.4.1.8072.1.3.2 \
        || true

    # The extend scripts register under predictable sub-OIDs.
    # nsExtendOutput1Line: .1.3.6.1.4.1.8072.1.3.2.3.1.1
    # nsExtendOutputFull:  .1.3.6.1.4.1.8072.1.3.2.3.1.2
    # The index is the ASCII of the extend name.

    log_subsection "Extend Output Verification"

    # Walk the nsExtendOutput1Line table to find all extend outputs
    local extend_output
    extend_output=$(snmpwalk -v2c -c "$COMMUNITY" -t "$TIMEOUT" -r "$RETRIES" "$SNMP_TARGET" \
        1.3.6.1.4.1.8072.1.3.2.3.1.1 2>&1) || true

    if [[ -n "$extend_output" ]] && ! echo "$extend_output" | grep -qi "error\|timeout\|no such"; then
        TESTS_TOTAL=$((TESTS_TOTAL + 1))
        local extend_count
        extend_count=$(echo "$extend_output" | grep -c "STRING" || true)
        if [[ $extend_count -ge 1 ]]; then
            TESTS_PASSED=$((TESTS_PASSED + 1))
            if [[ $QUIET -eq 0 ]]; then
                echo "  ${GREEN}✓${RESET} Extend scripts produced ${extend_count} output(s)"
            fi
            if [[ $VERBOSE -eq 1 ]]; then
                echo "$extend_output" | while IFS= read -r line; do
                    log_verbose "$line"
                done
            fi
        else
            TESTS_FAILED=$((TESTS_FAILED + 1))
            if [[ $QUIET -eq 0 ]]; then
                echo "  ${RED}✗${RESET} No extend script outputs found"
            fi
        fi
    else
        TESTS_TOTAL=$((TESTS_TOTAL + 1))
        TESTS_FAILED=$((TESTS_FAILED + 1))
        if [[ $QUIET -eq 0 ]]; then
            echo "  ${RED}✗${RESET} Extend table walk failed"
            echo "    ${DIM}${extend_output:0:200}${RESET}"
        fi
    fi
}

# ---------------------------------------------------------------------------
# 7. SNMPv3 (authPriv)
# ---------------------------------------------------------------------------
test_snmpv3() {
    if [[ $SKIP_V3 -eq 1 ]]; then
        log_section "7. SNMPv3 Authentication (SKIPPED)"
        skip_test "SNMPv3 authPriv" "--skip-v3 flag set"
        return
    fi

    log_section "7. SNMPv3 Authentication (authPriv)"

    log_subsection "SNMPv3 GET Operations"

    run_test "SNMPv3 sysName.0 — authPriv (SHA/AES)" \
        "(H3C|OBM|SIM|STRING|string)" \
        snmpget_v3 1.3.6.1.2.1.1.5.0 \
        || true

    run_test "SNMPv3 sysDescr.0 — authPriv (SHA/AES)" \
        "(H3C|Simulated|Switch|STRING|string)" \
        snmpget_v3 1.3.6.1.2.1.1.1.0 \
        || true

    run_test "SNMPv3 sysUpTime.0 — authPriv (SHA/AES)" \
        "(Timeticks|timeticks|[0-9]+)" \
        snmpget_v3 1.3.6.1.2.1.1.3.0 \
        || true

    log_subsection "SNMPv3 WALK Operations"

    run_walk_test "SNMPv3 Walk system tree — authPriv" 5 \
        snmpwalk_v3 1.3.6.1.2.1.1 \
        || true

    log_subsection "SNMPv3 Authentication Failure (negative test)"

    TESTS_TOTAL=$((TESTS_TOTAL + 1))
    local bad_output
    local bad_exit=0
    bad_output=$(snmpget -v3 -u baduser -l authPriv \
        -a SHA -A wrongpassword \
        -x AES -X wrongpassword \
        -t 2 -r 0 \
        "$SNMP_TARGET" 1.3.6.1.2.1.1.5.0 2>&1) || bad_exit=$?

    if [[ $bad_exit -ne 0 ]] || echo "$bad_output" | grep -qiE "(error|timeout|unknown|authentication)"; then
        TESTS_PASSED=$((TESTS_PASSED + 1))
        if [[ $QUIET -eq 0 ]]; then
            echo "  ${GREEN}✓${RESET} Bad credentials correctly rejected"
        fi
    else
        TESTS_FAILED=$((TESTS_FAILED + 1))
        if [[ $QUIET -eq 0 ]]; then
            echo "  ${RED}✗${RESET} Bad credentials were NOT rejected — security issue!"
            echo "    ${DIM}Output: ${bad_output:0:200}${RESET}"
        fi
    fi
}

# ---------------------------------------------------------------------------
# 8. Zabbix Template OID Compatibility Check
# ---------------------------------------------------------------------------
test_zabbix_template_oids() {
    log_section "8. Zabbix H3C Template OID Compatibility"
    echo "  ${DIM}Verifying that all OIDs referenced in H3C_NETWORK_by_SNMP template are queryable${RESET}"

    log_subsection "Template: H3C_NETWORK_by_SNMP — Static Items"

    # These are the exact OIDs used in the Zabbix template
    run_test "[template] system.name — get[1.3.6.1.2.1.1.5.0]" \
        "." \
        snmpget_v2 1.3.6.1.2.1.1.5.0 \
        || true

    run_test "[template] system.descr — get[1.3.6.1.2.1.1.1.0]" \
        "." \
        snmpget_v2 1.3.6.1.2.1.1.1.0 \
        || true

    run_test "[template] system.contact — get[1.3.6.1.2.1.1.4.0]" \
        "." \
        snmpget_v2 1.3.6.1.2.1.1.4.0 \
        || true

    run_test "[template] system.location — get[1.3.6.1.2.1.1.6.0]" \
        "." \
        snmpget_v2 1.3.6.1.2.1.1.6.0 \
        || true

    run_test "[template] system.net.uptime — get[1.3.6.1.2.1.1.3.0]" \
        "." \
        snmpget_v2 1.3.6.1.2.1.1.3.0 \
        || true

    run_test "[template] system.hw.uptime — get[1.3.6.1.2.1.25.1.1.0]" \
        "." \
        snmpget_v2 1.3.6.1.2.1.25.1.1.0 \
        || true

    log_subsection "Template: H3C_NETWORK_by_SNMP — LLD Discovery Walks"

    run_walk_test "[template] net.if.discovery — walk[1.3.6.1.2.1.2.2] (ifTable)" 1 \
        snmpwalk_v2 1.3.6.1.2.1.2.2 \
        || true

    if [[ $SKIP_H3C -eq 0 ]]; then
        run_walk_test "[template] entity.discovery — walk[1.3.6.1.4.1.25506.2.6.1.1.1] (H3C entities)" 1 \
            snmpwalk_v2 1.3.6.1.4.1.25506.2.6.1.1.1 \
            || true
    fi

    log_subsection "Template: H3C_NETWORK_by_SNMP — Interface Item Prototypes (index 1)"

    # These use {#SNMPINDEX} which maps to the interface index. We test with index 1.
    run_test "[template] net.if.in[ifHCInOctets.1] — get[1.3.6.1.2.1.31.1.1.1.6.1]" \
        "." \
        snmpget_v2 1.3.6.1.2.1.31.1.1.1.6.1 \
        || true

    run_test "[template] net.if.out[ifHCOutOctets.1] — get[1.3.6.1.2.1.31.1.1.1.10.1]" \
        "." \
        snmpget_v2 1.3.6.1.2.1.31.1.1.1.10.1 \
        || true

    run_test "[template] net.if.speed[ifHighSpeed.1] — get[1.3.6.1.2.1.31.1.1.1.15.1]" \
        "." \
        snmpget_v2 1.3.6.1.2.1.31.1.1.1.15.1 \
        || true

    run_test "[template] net.if.status[ifOperStatus.1] — get[1.3.6.1.2.1.2.2.1.8.1]" \
        "." \
        snmpget_v2 1.3.6.1.2.1.2.2.1.8.1 \
        || true

    if [[ $SKIP_H3C -eq 0 ]]; then
        log_subsection "Template: H3C_NETWORK_by_SNMP — Entity Item Prototypes (index 1)"

        run_test "[template] system.cpu.util[hh3cEntityExtCpuUsage.1]" \
            "(INTEGER|integer|[0-9]+)" \
            snmpget_v2 1.3.6.1.4.1.25506.2.6.1.1.1.1.6.1 \
            || true

        run_test "[template] vm.memory.util[hh3cEntityExtMemUsage.1]" \
            "(INTEGER|integer|[0-9]+)" \
            snmpget_v2 1.3.6.1.4.1.25506.2.6.1.1.1.1.8.1 \
            || true

        run_test "[template] sensor.temp.value[hh3cEntityExtTemperature.1]" \
            "(INTEGER|integer|[0-9]+)" \
            snmpget_v2 1.3.6.1.4.1.25506.2.6.1.1.1.1.12.1 \
            || true

        run_test "[template] sensor.status[hh3cEntityExtErrorStatus.1]" \
            "(INTEGER|integer|[0-9]+)" \
            snmpget_v2 1.3.6.1.4.1.25506.2.6.1.1.1.1.19.1 \
            || true
    fi
}

# ---------------------------------------------------------------------------
# 9. Performance / Bulk Walk Test
# ---------------------------------------------------------------------------
test_performance() {
    log_section "9. Performance — Bulk Walk"

    log_subsection "Full OID Tree Walk (bounded)"

    TESTS_TOTAL=$((TESTS_TOTAL + 1))
    local start_time
    start_time=$(date +%s%N 2>/dev/null || date +%s)

    local full_output
    local full_exit=0
    full_output=$(snmpwalk -v2c -c "$COMMUNITY" -t "$TIMEOUT" -r "$RETRIES" "$SNMP_TARGET" \
        .1 2>&1 | head -500) || full_exit=$?

    local end_time
    end_time=$(date +%s%N 2>/dev/null || date +%s)

    local line_count
    line_count=$(echo "$full_output" | grep -c '.' || true)

    # Calculate duration (handle both nanosecond and second precision)
    local duration_display
    if [[ ${#start_time} -gt 12 ]]; then
        local duration_ns=$(( end_time - start_time ))
        local duration_ms=$(( duration_ns / 1000000 ))
        duration_display="${duration_ms}ms"
    else
        local duration_s=$(( end_time - start_time ))
        duration_display="${duration_s}s"
    fi

    if [[ $line_count -ge 10 ]]; then
        TESTS_PASSED=$((TESTS_PASSED + 1))
        if [[ $QUIET -eq 0 ]]; then
            echo "  ${GREEN}✓${RESET} Full tree walk returned ${line_count} OIDs in ${duration_display}"
        fi
    else
        TESTS_FAILED=$((TESTS_FAILED + 1))
        if [[ $QUIET -eq 0 ]]; then
            echo "  ${RED}✗${RESET} Full tree walk returned only ${line_count} OIDs (expected >= 10)"
        fi
    fi

    # Bulk walk test (SNMPv2c bulk)
    if command -v snmpbulkwalk &>/dev/null; then
        log_subsection "SNMP Bulk Walk (snmpbulkwalk)"

        run_walk_test "Bulk walk ifTable — efficient retrieval" 1 \
            snmpbulkwalk -v2c -c "$COMMUNITY" -Cr10 -t "$TIMEOUT" -r "$RETRIES" "$SNMP_TARGET" 1.3.6.1.2.1.2.2 \
            || true
    fi
}

# ---------------------------------------------------------------------------
# 10. Data Validity Checks
# ---------------------------------------------------------------------------
test_data_validity() {
    log_section "10. Data Validity — Sensor Value Range Checks"

    if [[ $SKIP_H3C -eq 1 ]]; then
        skip_test "H3C sensor value validation" "--skip-h3c flag set"
        return
    fi

    log_subsection "CPU Usage Range (0-100%)"

    for idx in 1 2; do
        TESTS_TOTAL=$((TESTS_TOTAL + 1))
        local cpu_output
        cpu_output=$(snmpget_v2 "1.3.6.1.4.1.25506.2.6.1.1.1.1.6.${idx}" 2>&1) || true

        local cpu_val
        cpu_val=$(echo "$cpu_output" | grep -oE '[0-9]+$' | tail -1)

        if [[ -n "$cpu_val" ]] && [[ "$cpu_val" -ge 0 ]] && [[ "$cpu_val" -le 100 ]]; then
            TESTS_PASSED=$((TESTS_PASSED + 1))
            if [[ $QUIET -eq 0 ]]; then
                echo "  ${GREEN}✓${RESET} Entity ${idx} CPU: ${cpu_val}% (valid range)"
            fi
        else
            TESTS_FAILED=$((TESTS_FAILED + 1))
            if [[ $QUIET -eq 0 ]]; then
                echo "  ${RED}✗${RESET} Entity ${idx} CPU: '${cpu_val:-N/A}' (out of range or parse error)"
            fi
        fi
    done

    log_subsection "Memory Usage Range (0-100%)"

    for idx in 1 2; do
        TESTS_TOTAL=$((TESTS_TOTAL + 1))
        local mem_output
        mem_output=$(snmpget_v2 "1.3.6.1.4.1.25506.2.6.1.1.1.1.8.${idx}" 2>&1) || true

        local mem_val
        mem_val=$(echo "$mem_output" | grep -oE '[0-9]+$' | tail -1)

        if [[ -n "$mem_val" ]] && [[ "$mem_val" -ge 0 ]] && [[ "$mem_val" -le 100 ]]; then
            TESTS_PASSED=$((TESTS_PASSED + 1))
            if [[ $QUIET -eq 0 ]]; then
                echo "  ${GREEN}✓${RESET} Entity ${idx} Memory: ${mem_val}% (valid range)"
            fi
        else
            TESTS_FAILED=$((TESTS_FAILED + 1))
            if [[ $QUIET -eq 0 ]]; then
                echo "  ${RED}✗${RESET} Entity ${idx} Memory: '${mem_val:-N/A}' (out of range or parse error)"
            fi
        fi
    done

    log_subsection "Temperature Range (0-120°C)"

    for idx in 1 2 3 4 5; do
        TESTS_TOTAL=$((TESTS_TOTAL + 1))
        local temp_output
        temp_output=$(snmpget_v2 "1.3.6.1.4.1.25506.2.6.1.1.1.1.12.${idx}" 2>&1) || true

        local temp_val
        temp_val=$(echo "$temp_output" | grep -oE '[0-9]+$' | tail -1)

        if [[ -n "$temp_val" ]] && [[ "$temp_val" -ge 0 ]] && [[ "$temp_val" -le 120 ]]; then
            TESTS_PASSED=$((TESTS_PASSED + 1))
            if [[ $QUIET -eq 0 ]]; then
                echo "  ${GREEN}✓${RESET} Entity ${idx} Temperature: ${temp_val}°C (valid range)"
            fi
        else
            TESTS_FAILED=$((TESTS_FAILED + 1))
            if [[ $QUIET -eq 0 ]]; then
                echo "  ${RED}✗${RESET} Entity ${idx} Temperature: '${temp_val:-N/A}' (out of range or parse error)"
            fi
        fi
    done

    log_subsection "Error Status (0 = normal)"

    for idx in 1 2; do
        TESTS_TOTAL=$((TESTS_TOTAL + 1))
        local err_output
        err_output=$(snmpget_v2 "1.3.6.1.4.1.25506.2.6.1.1.1.1.19.${idx}" 2>&1) || true

        local err_val
        err_val=$(echo "$err_output" | grep -oE '[0-9]+$' | tail -1)

        if [[ -n "$err_val" ]] && [[ "$err_val" -eq 0 ]]; then
            TESTS_PASSED=$((TESTS_PASSED + 1))
            if [[ $QUIET -eq 0 ]]; then
                echo "  ${GREEN}✓${RESET} Entity ${idx} ErrorStatus: ${err_val} (normal)"
            fi
        else
            TESTS_FAILED=$((TESTS_FAILED + 1))
            if [[ $QUIET -eq 0 ]]; then
                echo "  ${RED}✗${RESET} Entity ${idx} ErrorStatus: '${err_val:-N/A}' (expected 0)"
            fi
        fi
    done
}

# =============================================================================
# MAIN
# =============================================================================

main() {
    local start_time
    start_time=$(date +%s)

    if [[ $QUIET -eq 0 ]]; then
        echo ""
        echo "${BOLD}╔══════════════════════════════════════════════════════════════╗${RESET}"
        echo "${BOLD}║   SNMP Simulator — Comprehensive Verification Suite        ║${RESET}"
        echo "${BOLD}╚══════════════════════════════════════════════════════════════╝${RESET}"
        echo ""
        echo "  Target:     ${BOLD}${SNMP_TARGET}${RESET}"
        echo "  Community:  ${COMMUNITY}"
        echo "  SNMPv3:     ${V3_USER} ($(if [[ $SKIP_V3 -eq 1 ]]; then echo 'skipped'; else echo 'enabled'; fi))"
        echo "  H3C MIBs:   $(if [[ $SKIP_H3C -eq 1 ]]; then echo 'skipped'; else echo 'enabled'; fi)"
        echo "  Verbose:    $(if [[ $VERBOSE -eq 1 ]]; then echo 'yes'; else echo 'no'; fi)"
    fi

    # Prerequisites
    check_prerequisites

    # Run all test suites
    test_system_mib
    test_if_mib
    test_host_resources_mib
    test_entity_mib
    test_h3c_entity_ext_mib
    test_extend_mib
    test_snmpv3
    test_zabbix_template_oids
    test_performance
    test_data_validity

    # Summary
    local end_time
    end_time=$(date +%s)
    local duration=$(( end_time - start_time ))

    echo ""
    echo "${BOLD}╔══════════════════════════════════════════════════════════════╗${RESET}"
    echo "${BOLD}║   Test Results Summary                                     ║${RESET}"
    echo "${BOLD}╚══════════════════════════════════════════════════════════════╝${RESET}"
    echo ""
    echo "  Total:    ${BOLD}${TESTS_TOTAL}${RESET}"
    echo "  Passed:   ${GREEN}${BOLD}${TESTS_PASSED}${RESET}"
    echo "  Failed:   ${RED}${BOLD}${TESTS_FAILED}${RESET}"
    echo "  Skipped:  ${YELLOW}${BOLD}${TESTS_SKIPPED}${RESET}"
    echo "  Duration: ${duration}s"
    echo ""

    if [[ $TESTS_FAILED -eq 0 ]]; then
        echo "  ${GREEN}${BOLD}▶ ALL TESTS PASSED ✓${RESET}"
        echo ""
        echo "  The SNMP simulator is fully operational and compatible with"
        echo "  the H3C_NETWORK_by_SNMP Zabbix template."
        echo ""
        echo "  ${DIM}Next steps:${RESET}"
        echo "  ${DIM}  1. Add snmp-simulator as a host in Zabbix (IP: 172.28.0.10)${RESET}"
        echo "  ${DIM}  2. Assign the H3C_NETWORK_by_SNMP template${RESET}"
        echo "  ${DIM}  3. Set SNMP interface: community=public, port=161${RESET}"
        echo "  ${DIM}  4. Wait for LLD to discover interfaces and entities${RESET}"
    else
        echo "  ${RED}${BOLD}▶ ${TESTS_FAILED} TEST(S) FAILED ✗${RESET}"
        echo ""
        echo "  ${DIM}Check the output above for details. Common issues:${RESET}"
        echo "  ${DIM}  - Container not fully started (pass_persist scripts may need a few seconds)${RESET}"
        echo "  ${DIM}  - snmpd.conf syntax issues (check: docker logs snmp-simulator)${RESET}"
        echo "  ${DIM}  - Network connectivity between containers${RESET}"
    fi
    echo ""

    if [[ $TESTS_FAILED -gt 0 ]]; then
        exit 1
    fi
    exit 0
}

main "$@"
