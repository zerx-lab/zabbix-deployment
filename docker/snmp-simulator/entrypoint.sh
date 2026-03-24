#!/bin/bash
# =============================================================================
# entrypoint.sh — SNMP Simulator Container Entrypoint
# =============================================================================
# Starts snmpd with proper configuration for OBM (out-of-band management)
# simulation testing with Zabbix.
# =============================================================================

set -euo pipefail

# ---------------------------------------------------------------------------
# Configuration (overridable via environment variables)
# ---------------------------------------------------------------------------
SNMPD_CONF="${SNMPD_CONF:-/etc/snmp/snmpd.conf}"
SNMPD_LISTEN="${SNMPD_LISTEN:-}"
SNMPD_LOG_LEVEL="${SNMPD_LOG_LEVEL:-6}"  # 0=emerg..7=debug; 6=info
COMMUNITY="${COMMUNITY:-public}"

# ---------------------------------------------------------------------------
# Banner
# ---------------------------------------------------------------------------
echo "============================================================"
echo "  SNMP Simulator for Out-of-Band Management Testing"
echo "============================================================"
echo "  Container started at: $(date -Iseconds 2>/dev/null || date)"
echo "  Hostname:             $(hostname)"
echo "  Listen address:       ${SNMPD_LISTEN:-udp:161 (default)}"
echo "  Config file:          ${SNMPD_CONF}"
echo "  Log level:            ${SNMPD_LOG_LEVEL}"
echo "  SNMPv2c community:    ${COMMUNITY}"
echo "============================================================"

# ---------------------------------------------------------------------------
# Dynamic community override
# ---------------------------------------------------------------------------
# If the COMMUNITY env var is set to something other than 'public',
# patch the snmpd.conf to add that community.
if [[ "${COMMUNITY}" != "public" ]]; then
    echo "  → Adding custom community '${COMMUNITY}' to snmpd.conf"
    sed -i "/^com2sec.*public$/a com2sec  AllUser    default    ${COMMUNITY}" "${SNMPD_CONF}"
fi

# ---------------------------------------------------------------------------
# Validate configuration
# ---------------------------------------------------------------------------
echo ""
echo "[init] Validating snmpd configuration..."

if [[ ! -f "${SNMPD_CONF}" ]]; then
    echo "[ERROR] snmpd.conf not found at ${SNMPD_CONF}" >&2
    exit 1
fi

# Ensure extend script is executable (may fail if volume is mounted read-only,
# which is fine since the image already has +x from the build step)
if [[ -f /usr/local/bin/snmpd-extend.sh ]]; then
    chmod +x /usr/local/bin/snmpd-extend.sh 2>/dev/null || true
    echo "[init] snmpd-extend.sh is ready"
else
    echo "[WARN] snmpd-extend.sh not found — H3C MIB simulation will not work" >&2
fi

# Ensure required directories exist
mkdir -p /var/lib/net-snmp
mkdir -p /var/run/net-snmp
mkdir -p /var/log/snmp

echo "[init] Directories verified"

# ---------------------------------------------------------------------------
# Pre-flight config validation (file-level only — no snmpd launch)
# ---------------------------------------------------------------------------
echo "[init] Checking snmpd.conf directives..."
directive_count=$(grep -cE '^\s*(com2sec|group|view|access|sysDescr|sysName|pass_persist|extend)\b' "${SNMPD_CONF}" || true)
if [[ "$directive_count" -gt 0 ]]; then
    echo "[init] Config looks valid (${directive_count} key directives found)"
else
    echo "[WARN] Config may be incomplete — no key directives found" >&2
fi

# ---------------------------------------------------------------------------
# Print simulated device summary
# ---------------------------------------------------------------------------
echo ""
echo "[info] Simulated Device Profile:"
echo "  sysDescr:    $(grep '^sysDescr' "${SNMPD_CONF}" | sed 's/^sysDescr\s*//' | head -1)"
echo "  sysName:     $(grep '^sysName' "${SNMPD_CONF}" | sed 's/^sysName\s*//' | head -1)"
echo "  sysLocation: $(grep '^sysLocation' "${SNMPD_CONF}" | sed 's/^sysLocation\s*//' | head -1)"
echo "  sysContact:  $(grep '^sysContact' "${SNMPD_CONF}" | sed 's/^sysContact\s*//' | head -1)"
echo ""
echo "[info] Simulated H3C Entity Modules:"
echo "  Index 1: Slot 0/CPU 0       (CPU + Memory + Temperature)"
echo "  Index 2: Slot 1/CPU 0       (CPU + Memory + Temperature)"
echo "  Index 3: Slot 0/Fan 1       (Temperature)"
echo "  Index 4: Slot 0/Power 1     (Temperature)"
echo "  Index 5: Slot 0/Sensor 1    (Temperature)"
echo ""
echo "[info] Key OIDs available for testing:"
echo "  System Name:         1.3.6.1.2.1.1.5.0"
echo "  System Description:  1.3.6.1.2.1.1.1.0"
echo "  System Uptime:       1.3.6.1.2.1.1.3.0"
echo "  System Contact:      1.3.6.1.2.1.1.4.0"
echo "  System Location:     1.3.6.1.2.1.1.6.0"
echo "  IF-MIB (interfaces): 1.3.6.1.2.1.2.2 (walk)"
echo "  Entity Physical:     1.3.6.1.2.1.47.1.1.1 (walk)"
echo "  HH3C CPU Usage:      1.3.6.1.4.1.25506.2.6.1.1.1.1.6.{idx}"
echo "  HH3C Memory Usage:   1.3.6.1.4.1.25506.2.6.1.1.1.1.8.{idx}"
echo "  HH3C Temperature:    1.3.6.1.4.1.25506.2.6.1.1.1.1.12.{idx}"
echo "  HH3C Error Status:   1.3.6.1.4.1.25506.2.6.1.1.1.1.19.{idx}"
echo ""

# ---------------------------------------------------------------------------
# Quick-test commands hint
# ---------------------------------------------------------------------------
echo "[info] Quick-test commands (run from host or another container):"
echo ""
echo "  # SNMPv2c — basic system info"
echo "  snmpget -v2c -c ${COMMUNITY} <container_ip> 1.3.6.1.2.1.1.5.0"
echo "  snmpget -v2c -c ${COMMUNITY} <container_ip> 1.3.6.1.2.1.1.1.0"
echo ""
echo "  # SNMPv2c — walk system tree"
echo "  snmpwalk -v2c -c ${COMMUNITY} <container_ip> 1.3.6.1.2.1.1"
echo ""
echo "  # SNMPv2c — walk interfaces"
echo "  snmpwalk -v2c -c ${COMMUNITY} <container_ip> 1.3.6.1.2.1.2.2"
echo ""
echo "  # SNMPv2c — H3C Entity CPU/Mem/Temp (index 1)"
echo "  snmpget -v2c -c ${COMMUNITY} <container_ip> 1.3.6.1.4.1.25506.2.6.1.1.1.1.6.1"
echo "  snmpget -v2c -c ${COMMUNITY} <container_ip> 1.3.6.1.4.1.25506.2.6.1.1.1.1.8.1"
echo "  snmpget -v2c -c ${COMMUNITY} <container_ip> 1.3.6.1.4.1.25506.2.6.1.1.1.1.12.1"
echo ""
echo "  # SNMPv2c — walk H3C entity tree"
echo "  snmpwalk -v2c -c ${COMMUNITY} <container_ip> 1.3.6.1.4.1.25506.2.6.1.1.1"
echo ""
echo "  # SNMPv2c — walk Entity Physical table"
echo "  snmpwalk -v2c -c ${COMMUNITY} <container_ip> 1.3.6.1.2.1.47.1.1.1"
echo ""
echo "  # SNMPv3 (authPriv)"
echo "  snmpget -v3 -u zabbixuser -l authPriv -a SHA -A myauthpass -x AES -X myprivpass <container_ip> 1.3.6.1.2.1.1.5.0"
echo ""
echo "============================================================"

# ---------------------------------------------------------------------------
# Signal handling for graceful shutdown
# ---------------------------------------------------------------------------
cleanup() {
    echo ""
    echo "[shutdown] Received signal, stopping snmpd..."
    if [[ -n "${SNMPD_PID:-}" ]]; then
        kill -TERM "$SNMPD_PID" 2>/dev/null || true
        wait "$SNMPD_PID" 2>/dev/null || true
    fi
    echo "[shutdown] SNMP simulator stopped"
    exit 0
}

trap cleanup SIGTERM SIGINT SIGQUIT

# ---------------------------------------------------------------------------
# Start snmpd
# ---------------------------------------------------------------------------
echo "[start] Launching snmpd (foreground, log level ${SNMPD_LOG_LEVEL})..."
echo ""

# -f = foreground (don't fork)
# -L = log to stdout/stderr
# -Lo = log to stdout
# -Le = log to stderr
# -c = config file path
# -C = don't read default config locations, only -c
# Only append listen address if explicitly set (snmpd defaults to udp:161)
if [[ -n "${SNMPD_LISTEN}" ]]; then
    exec_cmd="snmpd -f -Lo -C -c ${SNMPD_CONF} ${SNMPD_LISTEN}"
else
    exec_cmd="snmpd -f -Lo -C -c ${SNMPD_CONF}"
fi

echo "[start] Exec: ${exec_cmd}"
echo ""

# Run snmpd in background so we can trap signals
${exec_cmd} &
SNMPD_PID=$!

echo "[start] snmpd running with PID ${SNMPD_PID}"
echo ""

# Wait for snmpd — if it exits, we exit with its code
wait "$SNMPD_PID"
exit_code=$?

echo "[exit] snmpd exited with code ${exit_code}"
exit ${exit_code}
