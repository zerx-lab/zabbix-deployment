package main

import (
	"fmt"
	"strings"
)

// generateComposeYAML 根据部署配置生成 docker-compose.yml 内容
func generateComposeYAML(config DeployConfig) string {
	var sb strings.Builder

	writeServicesSection(&sb, config)
	writeVolumesSection(&sb, config)
	writeNetworksSection(&sb)

	return sb.String()
}

// ─── 各段生成 ──────────────────────────────────────────────

func writeServicesSection(sb *strings.Builder, config DeployConfig) {
	sb.WriteString("services:\n")
	writePostgresService(sb, config)
	writeServerService(sb, config)
	writeWebService(sb, config)
	writeAgentService(sb, config)
	if config.Server.EnableSnmpTrapper {
		writeSnmpTrapsService(sb, config)
	}
}

func writeVolumesSection(sb *strings.Builder, config DeployConfig) {
	sb.WriteString("\nvolumes:\n")
	sb.WriteString("  postgres-data:\n")
	sb.WriteString("  zabbix-server-data:\n")
	if config.Server.EnableSnmpTrapper {
		sb.WriteString("  snmptraps:\n")
		sb.WriteString("  snmp-mibs:\n")
	}
}

func writeNetworksSection(sb *strings.Builder) {
	sb.WriteString("\nnetworks:\n")
	sb.WriteString("  zabbix-net:\n")
	sb.WriteString("    driver: bridge\n")
}

// ─── postgres 服务 ─────────────────────────────────────────

func writePostgresService(sb *strings.Builder, config DeployConfig) {
	sb.WriteString("  postgres:\n")
	sb.WriteString("    image: postgres:16-alpine\n")
	sb.WriteString(fmt.Sprintf("    container_name: %s\n", ContainerPostgres))
	sb.WriteString("    restart: unless-stopped\n")
	sb.WriteString("    environment:\n")
	sb.WriteString(fmt.Sprintf("      POSTGRES_USER: %s\n", config.Database.User))
	sb.WriteString(fmt.Sprintf("      POSTGRES_PASSWORD: %s\n", config.Database.Password))
	sb.WriteString(fmt.Sprintf("      POSTGRES_DB: %s\n", config.Database.Name))
	sb.WriteString("    volumes:\n")
	sb.WriteString("      - postgres-data:/var/lib/postgresql/data\n")
	sb.WriteString("    networks:\n")
	sb.WriteString("      - zabbix-net\n")
	sb.WriteString("    healthcheck:\n")
	sb.WriteString(fmt.Sprintf("      test: [\"CMD-SHELL\", \"pg_isready -U %s\"]\n", config.Database.User))
	sb.WriteString("      interval: 10s\n")
	sb.WriteString("      timeout: 5s\n")
	sb.WriteString("      retries: 5\n")
}

// ─── zabbix-server 服务 ────────────────────────────────────

func writeServerService(sb *strings.Builder, config DeployConfig) {
	sb.WriteString("  zabbix-server:\n")
	sb.WriteString("    image: zabbix/zabbix-server-pgsql:alpine-7.0-latest\n")
	sb.WriteString(fmt.Sprintf("    container_name: %s\n", ContainerServer))
	sb.WriteString("    restart: unless-stopped\n")
	sb.WriteString("    environment:\n")
	sb.WriteString("      DB_SERVER_HOST: postgres\n")
	sb.WriteString(fmt.Sprintf("      POSTGRES_USER: %s\n", config.Database.User))
	sb.WriteString(fmt.Sprintf("      POSTGRES_PASSWORD: %s\n", config.Database.Password))
	sb.WriteString(fmt.Sprintf("      POSTGRES_DB: %s\n", config.Database.Name))
	sb.WriteString(fmt.Sprintf("      ZBX_CACHESIZE: %s\n", config.Server.CacheSize))
	sb.WriteString(fmt.Sprintf("      ZBX_STARTPOLLERS: %d\n", config.Server.StartPollers))
	if config.Server.EnableSnmpTrapper {
		sb.WriteString("      ZBX_ENABLE_SNMP_TRAPPER: \"true\"\n")
	}
	sb.WriteString("    ports:\n")
	sb.WriteString(fmt.Sprintf("      - \"%d:10051\"\n", config.Server.ListenPort))
	sb.WriteString("    volumes:\n")
	sb.WriteString("      - zabbix-server-data:/var/lib/zabbix\n")
	if config.Server.EnableSnmpTrapper {
		sb.WriteString("      - snmptraps:/var/lib/zabbix/snmptraps\n")
		sb.WriteString("      - snmp-mibs:/var/lib/zabbix/mibs\n")
	}
	sb.WriteString("    networks:\n")
	sb.WriteString("      - zabbix-net\n")
	sb.WriteString("    depends_on:\n")
	sb.WriteString("      postgres:\n")
	sb.WriteString("        condition: service_healthy\n")
}

// ─── zabbix-web 服务 ───────────────────────────────────────

func writeWebService(sb *strings.Builder, config DeployConfig) {
	sb.WriteString("  zabbix-web:\n")
	sb.WriteString("    image: zabbix/zabbix-web-nginx-pgsql:alpine-7.0-latest\n")
	sb.WriteString(fmt.Sprintf("    container_name: %s\n", ContainerWeb))
	sb.WriteString("    restart: unless-stopped\n")
	sb.WriteString("    environment:\n")
	sb.WriteString("      ZBX_SERVER_HOST: zabbix-server\n")
	sb.WriteString("      DB_SERVER_HOST: postgres\n")
	sb.WriteString(fmt.Sprintf("      POSTGRES_USER: %s\n", config.Database.User))
	sb.WriteString(fmt.Sprintf("      POSTGRES_PASSWORD: %s\n", config.Database.Password))
	sb.WriteString(fmt.Sprintf("      POSTGRES_DB: %s\n", config.Database.Name))
	sb.WriteString(fmt.Sprintf("      PHP_TZ: %s\n", config.Web.Timezone))
	sb.WriteString("    ports:\n")
	sb.WriteString(fmt.Sprintf("      - \"%d:8080\"\n", config.Web.HTTPPort))
	sb.WriteString(fmt.Sprintf("      - \"%d:8443\"\n", config.Web.HTTPSPort))
	sb.WriteString("    networks:\n")
	sb.WriteString("      - zabbix-net\n")
	sb.WriteString("    depends_on:\n")
	sb.WriteString("      - zabbix-server\n")
}

// ─── zabbix-agent 服务 ─────────────────────────────────────

func writeAgentService(sb *strings.Builder, config DeployConfig) {
	sb.WriteString("  zabbix-agent:\n")
	sb.WriteString("    image: zabbix/zabbix-agent2:alpine-7.0-latest\n")
	sb.WriteString(fmt.Sprintf("    container_name: %s\n", ContainerAgent))
	sb.WriteString("    restart: unless-stopped\n")
	sb.WriteString("    environment:\n")
	sb.WriteString("      ZBX_SERVER_HOST: zabbix-server\n")
	sb.WriteString(fmt.Sprintf("      ZBX_HOSTNAME: %s\n", yamlQuoteIfNeeded(config.Agent.Hostname)))
	sb.WriteString("    ports:\n")
	sb.WriteString(fmt.Sprintf("      - \"%d:10050\"\n", config.Agent.ListenPort))
	sb.WriteString("    networks:\n")
	sb.WriteString("      - zabbix-net\n")
	sb.WriteString("    depends_on:\n")
	sb.WriteString("      - zabbix-server\n")
}

// ─── zabbix-snmptraps 服务 ─────────────────────────────────

func writeSnmpTrapsService(sb *strings.Builder, config DeployConfig) {
	sb.WriteString("  zabbix-snmptraps:\n")
	sb.WriteString("    image: zabbix/zabbix-snmptraps:alpine-7.0-latest\n")
	sb.WriteString(fmt.Sprintf("    container_name: %s\n", ContainerSnmptraps))
	sb.WriteString("    restart: unless-stopped\n")
	// environment 为空 map，与 TS compose-generator 的 environment: {} 保持一致
	sb.WriteString("    environment: {}\n")
	sb.WriteString("    ports:\n")
	sb.WriteString(fmt.Sprintf("      - \"%d:1162/udp\"\n", config.Server.SnmpTrapperPort))
	sb.WriteString("    volumes:\n")
	sb.WriteString("      - snmptraps:/var/lib/zabbix/snmptraps\n")
	sb.WriteString("      - snmp-mibs:/var/lib/zabbix/mibs\n")
	sb.WriteString("    networks:\n")
	sb.WriteString("      - zabbix-net\n")
}

// ─── 辅助函数 ──────────────────────────────────────────────

// yamlQuoteIfNeeded 当字符串包含需要引号的 YAML 字符时，用双引号包裹。
// 主要用于 ZBX_HOSTNAME 等可能含有空格或特殊字符的值。
func yamlQuoteIfNeeded(s string) string {
	if s == "" {
		return s
	}

	// 含有以下字符时需要引号
	for _, c := range s {
		if c == ':' || c == '#' || c == '{' || c == '}' ||
			c == '[' || c == ']' || c == ',' || c == '&' ||
			c == '*' || c == '?' || c == '|' || c == '<' ||
			c == '>' || c == '=' || c == '!' || c == '%' ||
			c == '@' || c == '`' || c == '\'' || c == '"' ||
			c == '\\' {
			escaped := strings.ReplaceAll(s, `"`, `\"`)
			return fmt.Sprintf(`"%s"`, escaped)
		}
	}

	// 看起来像布尔/null 关键字时也需要引号
	lower := strings.ToLower(s)
	if lower == "true" || lower == "false" || lower == "yes" || lower == "no" ||
		lower == "on" || lower == "off" || lower == "null" || lower == "~" {
		return fmt.Sprintf(`"%s"`, s)
	}

	return s
}
