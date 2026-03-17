package main

import (
	"strings"
	"testing"
)

// ─── helpers ──────────────────────────────────────────────

func testConfig() DeployConfig {
	cfg := DefaultDeployConfig()
	cfg.Database.Password = "testpassword"
	return cfg
}

func testConfigWithSNMP() DeployConfig {
	cfg := testConfig()
	cfg.Server.EnableSnmpTrapper = true
	cfg.Server.SnmpTrapperPort = 162
	return cfg
}

// ─── generateComposeYAML ──────────────────────────────────

func TestGenerateComposeYAML_BasicServices(t *testing.T) {
	yaml := generateComposeYAML(testConfig())

	requiredServices := []string{
		"  postgres:",
		"  zabbix-server:",
		"  zabbix-web:",
		"  zabbix-agent:",
	}
	for _, svc := range requiredServices {
		if !strings.Contains(yaml, svc) {
			t.Errorf("expected service block %q in YAML output", svc)
		}
	}
}

func TestGenerateComposeYAML_NoSnmpTrapsWithoutFlag(t *testing.T) {
	yaml := generateComposeYAML(testConfig())

	if strings.Contains(yaml, "zabbix-snmptraps:") {
		t.Error("snmptraps service should NOT appear when EnableSnmpTrapper=false")
	}
	if strings.Contains(yaml, "snmptraps:") {
		t.Error("snmptraps volume should NOT appear when EnableSnmpTrapper=false")
	}
}

func TestGenerateComposeYAML_SnmpTrapsWithFlag(t *testing.T) {
	yaml := generateComposeYAML(testConfigWithSNMP())

	if !strings.Contains(yaml, "  zabbix-snmptraps:") {
		t.Error("snmptraps service block should appear when EnableSnmpTrapper=true")
	}
	if !strings.Contains(yaml, "  snmptraps:") {
		t.Error("snmptraps volume should appear when EnableSnmpTrapper=true")
	}
	if !strings.Contains(yaml, "  snmp-mibs:") {
		t.Error("snmp-mibs volume should appear when EnableSnmpTrapper=true")
	}
}

// ─── snmptraps service: environment: {} requirement ──────
// TS compose-generator outputs `environment: {}` for the snmptraps service.
// We must match this to keep the generated compose files identical.

func TestGenerateComposeYAML_SnmpTrapsHasEnvironmentField(t *testing.T) {
	yaml := generateComposeYAML(testConfigWithSNMP())

	// Extract the snmptraps service block
	lines := strings.Split(yaml, "\n")
	inSnmpBlock := false
	foundEnvironment := false

	for _, line := range lines {
		if line == "  zabbix-snmptraps:" {
			inSnmpBlock = true
			continue
		}
		// A new top-level service starts at "  <name>:" indentation
		if inSnmpBlock && strings.HasPrefix(line, "  ") && strings.HasSuffix(strings.TrimSpace(line), ":") &&
			!strings.HasPrefix(line, "    ") {
			// we've left the snmptraps block
			break
		}
		if inSnmpBlock && strings.TrimSpace(line) == "environment: {}" {
			foundEnvironment = true
		}
	}

	if !foundEnvironment {
		t.Errorf("snmptraps service must contain 'environment: {}' to match TS output.\nFull YAML:\n%s", yaml)
	}
}

// ─── postgres service ─────────────────────────────────────

func TestGenerateComposeYAML_PostgresService(t *testing.T) {
	cfg := testConfig()
	yaml := generateComposeYAML(cfg)

	checks := []string{
		"    image: postgres:16-alpine",
		"    container_name: " + ContainerPostgres,
		"    restart: unless-stopped",
		"      POSTGRES_USER: " + cfg.Database.User,
		"      POSTGRES_PASSWORD: " + cfg.Database.Password,
		"      POSTGRES_DB: " + cfg.Database.Name,
		"      - postgres-data:/var/lib/postgresql/data",
		"      - zabbix-net",
		"      interval: 10s",
		"      timeout: 5s",
	}
	for _, c := range checks {
		if !strings.Contains(yaml, c) {
			t.Errorf("postgres service: expected %q in YAML", c)
		}
	}
}

func TestGenerateComposeYAML_PostgresHealthcheck(t *testing.T) {
	cfg := testConfig()
	yaml := generateComposeYAML(cfg)

	expected := `pg_isready -U ` + cfg.Database.User
	if !strings.Contains(yaml, expected) {
		t.Errorf("postgres healthcheck should use pg_isready with user %q", cfg.Database.User)
	}
}

// ─── zabbix-server service ────────────────────────────────

func TestGenerateComposeYAML_ServerService(t *testing.T) {
	cfg := testConfig()
	yaml := generateComposeYAML(cfg)

	checks := []string{
		"    image: zabbix/zabbix-server-pgsql:alpine-7.0-latest",
		"    container_name: " + ContainerServer,
		"      DB_SERVER_HOST: postgres",
		"      ZBX_CACHESIZE: " + cfg.Server.CacheSize,
		"      - zabbix-server-data:/var/lib/zabbix",
		"      postgres:",
		"        condition: service_healthy",
	}
	for _, c := range checks {
		if !strings.Contains(yaml, c) {
			t.Errorf("zabbix-server service: expected %q in YAML", c)
		}
	}
}

func TestGenerateComposeYAML_ServerPortMapping(t *testing.T) {
	cfg := testConfig()
	cfg.Server.ListenPort = 10051
	yaml := generateComposeYAML(cfg)

	if !strings.Contains(yaml, `"10051:10051"`) {
		t.Errorf("server port mapping should be 10051:10051")
	}
}

func TestGenerateComposeYAML_ServerSnmpEnvVar(t *testing.T) {
	cfg := testConfigWithSNMP()
	yaml := generateComposeYAML(cfg)

	if !strings.Contains(yaml, `ZBX_ENABLE_SNMP_TRAPPER: "true"`) {
		t.Error("ZBX_ENABLE_SNMP_TRAPPER should be set when snmp trapper is enabled")
	}
}

func TestGenerateComposeYAML_ServerSnmpVolumes(t *testing.T) {
	cfg := testConfigWithSNMP()
	yaml := generateComposeYAML(cfg)

	if !strings.Contains(yaml, "snmptraps:/var/lib/zabbix/snmptraps") {
		t.Error("server should mount snmptraps volume when snmp trapper is enabled")
	}
	if !strings.Contains(yaml, "snmp-mibs:/var/lib/zabbix/mibs") {
		t.Error("server should mount snmp-mibs volume when snmp trapper is enabled")
	}
}

// ─── zabbix-web service ───────────────────────────────────

func TestGenerateComposeYAML_WebService(t *testing.T) {
	cfg := testConfig()
	yaml := generateComposeYAML(cfg)

	checks := []string{
		"    image: zabbix/zabbix-web-nginx-pgsql:alpine-7.0-latest",
		"    container_name: " + ContainerWeb,
		"      ZBX_SERVER_HOST: zabbix-server",
		"      PHP_TZ: " + cfg.Web.Timezone,
		"      - zabbix-server",
	}
	for _, c := range checks {
		if !strings.Contains(yaml, c) {
			t.Errorf("zabbix-web service: expected %q in YAML", c)
		}
	}
}

func TestGenerateComposeYAML_WebPortMapping(t *testing.T) {
	cfg := testConfig()
	cfg.Web.HTTPPort = 8080
	cfg.Web.HTTPSPort = 8443
	yaml := generateComposeYAML(cfg)

	if !strings.Contains(yaml, `"8080:8080"`) {
		t.Errorf("web HTTP port mapping should be 8080:8080")
	}
	if !strings.Contains(yaml, `"8443:8443"`) {
		t.Errorf("web HTTPS port mapping should be 8443:8443")
	}
}

// ─── zabbix-agent service ─────────────────────────────────

func TestGenerateComposeYAML_AgentService(t *testing.T) {
	cfg := testConfig()
	yaml := generateComposeYAML(cfg)

	checks := []string{
		"    image: zabbix/zabbix-agent2:alpine-7.0-latest",
		"    container_name: " + ContainerAgent,
		"      ZBX_SERVER_HOST: zabbix-server",
		"      - zabbix-server",
	}
	for _, c := range checks {
		if !strings.Contains(yaml, c) {
			t.Errorf("zabbix-agent service: expected %q in YAML", c)
		}
	}
}

func TestGenerateComposeYAML_AgentHostname(t *testing.T) {
	cfg := testConfig()
	// Default hostname is "Zabbix server" (contains space — must appear correctly)
	yaml := generateComposeYAML(cfg)

	if !strings.Contains(yaml, "ZBX_HOSTNAME: Zabbix server") {
		t.Errorf("agent ZBX_HOSTNAME should be 'Zabbix server', YAML:\n%s", yaml)
	}
}

func TestGenerateComposeYAML_AgentPortMapping(t *testing.T) {
	cfg := testConfig()
	cfg.Agent.ListenPort = 10050
	yaml := generateComposeYAML(cfg)

	if !strings.Contains(yaml, `"10050:10050"`) {
		t.Errorf("agent port mapping should be 10050:10050")
	}
}

// ─── volumes & networks ───────────────────────────────────

func TestGenerateComposeYAML_BaseVolumes(t *testing.T) {
	yaml := generateComposeYAML(testConfig())

	if !strings.Contains(yaml, "  postgres-data:") {
		t.Error("postgres-data volume missing")
	}
	if !strings.Contains(yaml, "  zabbix-server-data:") {
		t.Error("zabbix-server-data volume missing")
	}
}

func TestGenerateComposeYAML_Network(t *testing.T) {
	yaml := generateComposeYAML(testConfig())

	if !strings.Contains(yaml, "  zabbix-net:") {
		t.Error("zabbix-net network definition missing")
	}
	if !strings.Contains(yaml, "    driver: bridge") {
		t.Error("network driver should be bridge")
	}
}

// ─── snmptraps service detail ─────────────────────────────

func TestGenerateComposeYAML_SnmpTrapsService(t *testing.T) {
	cfg := testConfigWithSNMP()
	cfg.Server.SnmpTrapperPort = 162
	yaml := generateComposeYAML(cfg)

	checks := []string{
		"    image: zabbix/zabbix-snmptraps:alpine-7.0-latest",
		"    container_name: " + ContainerSnmptraps,
		"    restart: unless-stopped",
		`"162:1162/udp"`,
		"      - snmptraps:/var/lib/zabbix/snmptraps",
		"      - snmp-mibs:/var/lib/zabbix/mibs",
		"      - zabbix-net",
	}
	for _, c := range checks {
		if !strings.Contains(yaml, c) {
			t.Errorf("snmptraps service: expected %q in YAML", c)
		}
	}
}

// ─── ImageToTarName ───────────────────────────────────────

func TestImageToTarName(t *testing.T) {
	cases := []struct {
		image   string
		wantTar string
	}{
		{"postgres:16-alpine", "postgres-16-alpine.tar"},
		{"zabbix/zabbix-server-pgsql:alpine-7.0-latest", "zabbix-zabbix-server-pgsql-alpine-7.0-latest.tar"},
		{"zabbix/zabbix-web-nginx-pgsql:alpine-7.0-latest", "zabbix-zabbix-web-nginx-pgsql-alpine-7.0-latest.tar"},
		{"zabbix/zabbix-agent2:alpine-7.0-latest", "zabbix-zabbix-agent2-alpine-7.0-latest.tar"},
		{"zabbix/zabbix-snmptraps:alpine-7.0-latest", "zabbix-zabbix-snmptraps-alpine-7.0-latest.tar"},
	}
	for _, tc := range cases {
		got := ImageToTarName(tc.image)
		if got != tc.wantTar {
			t.Errorf("ImageToTarName(%q) = %q, want %q", tc.image, got, tc.wantTar)
		}
	}
}

// ─── yamlQuoteIfNeeded ────────────────────────────────────

func TestYamlQuoteIfNeeded(t *testing.T) {
	cases := []struct {
		input    string
		wantQuot bool
	}{
		{"simple", false},
		{"Zabbix server", false},   // space alone does NOT require quoting in YAML plain scalars
		{"value:with:colon", true}, // colon triggers quoting
		{"true", true},             // boolean keyword
		{"false", true},
		{"yes", true},
		{"no", true},
		{"null", true},
		{"~", true},
		{"normal-value", false}, // hyphen alone is fine as a value (not a list indicator)
		{"has#hash", true},      // hash triggers quoting
		{"", false},             // empty stays empty
	}
	for _, tc := range cases {
		got := yamlQuoteIfNeeded(tc.input)
		isQuoted := strings.HasPrefix(got, `"`) && strings.HasSuffix(got, `"`)
		if isQuoted != tc.wantQuot {
			t.Errorf("yamlQuoteIfNeeded(%q) = %q, wantQuoted=%v", tc.input, got, tc.wantQuot)
		}
	}
}
