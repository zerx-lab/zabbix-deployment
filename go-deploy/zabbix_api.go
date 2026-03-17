package main

import (
	"bufio"
	"bytes"
	"encoding/json"
	"fmt"
	"net/http"
	"os"
	"strings"
	"time"
)

// ─── JSON-RPC 结构体 ───────────────────────────────────────

type zabbixRPCRequest struct {
	JSONRPC string                 `json:"jsonrpc"`
	Method  string                 `json:"method"`
	Params  map[string]interface{} `json:"params"`
	ID      int                    `json:"id"`
	Auth    string                 `json:"auth,omitempty"`
}

type zabbixRPCError struct {
	Code    int    `json:"code"`
	Message string `json:"message"`
	Data    string `json:"data"`
}

type zabbixRPCResponse struct {
	JSONRPC string          `json:"jsonrpc"`
	Result  json.RawMessage `json:"result"`
	Error   *zabbixRPCError `json:"error"`
	ID      int             `json:"id"`
}

// ─── 主机 / 接口结构体 ─────────────────────────────────────

type hostInterface struct {
	InterfaceID string `json:"interfaceid"`
	HostID      string `json:"hostid"`
	IP          string `json:"ip"`
	DNS         string `json:"dns"`
	UseIP       string `json:"useip"`
	Port        string `json:"port"`
	Type        string `json:"type"`
}

type zabbixHost struct {
	HostID     string          `json:"hostid"`
	Host       string          `json:"host"`
	Interfaces []hostInterface `json:"interfaces"`
}

// ─── 默认凭据 ──────────────────────────────────────────────

const (
	defaultZabbixUsername = "Admin"
	defaultZabbixPassword = "zabbix"

	// 首次部署时 Zabbix Server 需要初始化数据库 schema，可能需要 3-5 分钟
	apiWaitTimeoutMs  = 300_000
	apiPollIntervalMs = 5_000
)

// ─── 核心 RPC 调用 ─────────────────────────────────────────

// rpcCall 向 Zabbix API 发送一次 JSON-RPC 请求
func rpcCall(apiURL, method string, params map[string]interface{}, authToken string) (*zabbixRPCResponse, error) {
	body := zabbixRPCRequest{
		JSONRPC: "2.0",
		Method:  method,
		Params:  params,
		ID:      1,
		Auth:    authToken,
	}

	data, err := json.Marshal(body)
	if err != nil {
		return nil, fmt.Errorf("序列化请求失败: %w", err)
	}

	req, err := http.NewRequest(http.MethodPost, apiURL, bytes.NewReader(data))
	if err != nil {
		return nil, fmt.Errorf("创建 HTTP 请求失败: %w", err)
	}
	req.Header.Set("Content-Type", "application/json-rpc")

	client := &http.Client{Timeout: 10 * time.Second}
	resp, err := client.Do(req)
	if err != nil {
		return nil, fmt.Errorf("HTTP 请求失败: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		return nil, fmt.Errorf("Zabbix API HTTP 错误: %d %s", resp.StatusCode, resp.Status)
	}

	var rpcResp zabbixRPCResponse
	if err := json.NewDecoder(resp.Body).Decode(&rpcResp); err != nil {
		return nil, fmt.Errorf("解析响应失败: %w", err)
	}

	return &rpcResp, nil
}

// ─── 登录 ──────────────────────────────────────────────────

// zabbixLogin 登录 Zabbix API，返回认证令牌
func zabbixLogin(apiURL string) (string, error) {
	resp, err := rpcCall(apiURL, "user.login", map[string]interface{}{
		"username": defaultZabbixUsername,
		"password": defaultZabbixPassword,
	}, "")
	if err != nil {
		return "", err
	}
	if resp.Error != nil {
		return "", fmt.Errorf("Zabbix 登录失败: %s", resp.Error.Data)
	}

	var token string
	if err := json.Unmarshal(resp.Result, &token); err != nil {
		return "", fmt.Errorf("解析登录令牌失败: %w", err)
	}
	return token, nil
}

// ─── 获取默认主机 ──────────────────────────────────────────

// getDefaultHost 获取 "Zabbix server" 默认主机及其接口列表
func getDefaultHost(apiURL, authToken string) (*zabbixHost, error) {
	resp, err := rpcCall(apiURL, "host.get", map[string]interface{}{
		"filter":           map[string]interface{}{"host": []string{"Zabbix server"}},
		"selectInterfaces": "extend",
	}, authToken)
	if err != nil {
		return nil, err
	}
	if resp.Error != nil {
		return nil, fmt.Errorf("获取主机信息失败: %s", resp.Error.Data)
	}

	var hosts []zabbixHost
	if err := json.Unmarshal(resp.Result, &hosts); err != nil {
		return nil, fmt.Errorf("解析主机列表失败: %w", err)
	}
	if len(hosts) == 0 {
		return nil, nil
	}
	return &hosts[0], nil
}

// ─── 修正 Agent 接口地址 ───────────────────────────────────

// fixAgentInterface 将主机接口从 IP 模式切换为 DNS 模式（容器名 zabbix-agent）
func fixAgentInterface(apiURL, authToken, interfaceID string) error {
	resp, err := rpcCall(apiURL, "hostinterface.update", map[string]interface{}{
		"interfaceid": interfaceID,
		"useip":       "0", // 使用 DNS 而非 IP
		"dns":         ContainerAgent,
		"port":        "10050",
	}, authToken)
	if err != nil {
		return err
	}
	if resp.Error != nil {
		return fmt.Errorf("修改 Agent 接口失败: %s", resp.Error.Data)
	}
	return nil
}

// ─── 部署后初始化 ──────────────────────────────────────────

// postInitZabbix 自动修正 Zabbix 默认主机的 Agent 接口地址
//
// Zabbix 默认创建的 "Zabbix server" 主机，其 Agent 接口指向 127.0.0.1，
// 在容器化部署中 Agent 运行在独立容器，需要将接口地址改为 Agent 容器的 DNS 名称。
func postInitZabbix(apiURL string) PostInitResult {
	// 1. 登录
	authToken, err := zabbixLogin(apiURL)
	if err != nil {
		return PostInitResult{Success: false, Error: err.Error()}
	}

	// 2. 获取默认主机
	host, err := getDefaultHost(apiURL, authToken)
	if err != nil {
		return PostInitResult{Success: false, Error: err.Error()}
	}
	if host == nil {
		return PostInitResult{
			Success:             true,
			AgentInterfaceFixed: false,
			Error:               `未找到默认主机 "Zabbix server"，跳过接口修正`,
		}
	}

	// 3. 查找 Agent 类型接口（type=1）
	var agentIface *hostInterface
	for i := range host.Interfaces {
		if host.Interfaces[i].Type == "1" {
			agentIface = &host.Interfaces[i]
			break
		}
	}
	if agentIface == nil {
		return PostInitResult{
			Success:             true,
			AgentInterfaceFixed: false,
			Error:               "默认主机没有 Agent 类型接口，跳过修正",
		}
	}

	// 4. 检查是否已经是正确的 DNS 模式
	if agentIface.UseIP == "0" && agentIface.DNS == ContainerAgent {
		return PostInitResult{Success: true, AgentInterfaceFixed: false}
	}

	// 5. 修正接口地址
	if err := fixAgentInterface(apiURL, authToken, agentIface.InterfaceID); err != nil {
		return PostInitResult{Success: false, Error: err.Error()}
	}

	return PostInitResult{Success: true, AgentInterfaceFixed: true}
}

// ─── 等待 Zabbix API 就绪 ──────────────────────────────────

// waitForZabbixAPI 轮询等待 Zabbix API 可用
//
// 根据运行环境自动选择正确的 API 地址（宿主机 vs 容器内）。
// 返回可用的 API URL；超时返回空字符串。
func waitForZabbixAPI(webPort int) string {
	apiURL := buildAPIURL(webPort)
	startTime := time.Now()
	timeout := time.Duration(apiWaitTimeoutMs) * time.Millisecond
	interval := time.Duration(apiPollIntervalMs) * time.Millisecond

	for time.Since(startTime) < timeout {
		resp, err := rpcCall(apiURL, "apiinfo.version", map[string]interface{}{}, "")
		if err == nil && resp.Result != nil {
			return apiURL
		}
		time.Sleep(interval)
	}
	return ""
}

// ─── API 地址构建 ──────────────────────────────────────────

// buildAPIURL 根据运行环境构建 Zabbix API 完整地址
//   - 宿主机运行：直接用 localhost:{webPort}
//   - 容器内运行：通过宿主机网关 IP 访问端口映射
func buildAPIURL(webPort int) string {
	if !isRunningInContainer() {
		return fmt.Sprintf("http://localhost:%d/api_jsonrpc.php", webPort)
	}

	gatewayIP := getHostGatewayIP()
	if gatewayIP != "" {
		return fmt.Sprintf("http://%s:%d/api_jsonrpc.php", gatewayIP, webPort)
	}

	// 回退：使用常见的 Docker bridge 默认网关
	return fmt.Sprintf("http://172.17.0.1:%d/api_jsonrpc.php", webPort)
}

// ─── 容器环境检测 ──────────────────────────────────────────

// isRunningInContainer 检测当前进程是否运行在 Docker 容器内
// 通过检查 /.dockerenv 文件判断（Docker 创建容器时自动生成）
func isRunningInContainer() bool {
	_, err := os.Stat("/.dockerenv")
	return err == nil
}

// getHostGatewayIP 从容器内读取宿主机网关 IP
//
// 在 Linux 容器中，/proc/net/route 的默认路由（Destination=00000000）
// 的 Gateway 字段是小端序十六进制，解析后即为宿主机网关 IP。
func getHostGatewayIP() string {
	f, err := os.Open("/proc/net/route")
	if err != nil {
		return ""
	}
	defer f.Close()

	scanner := bufio.NewScanner(f)
	// 跳过标题行
	if !scanner.Scan() {
		return ""
	}

	for scanner.Scan() {
		fields := strings.Fields(scanner.Text())
		if len(fields) < 3 {
			continue
		}
		// Destination == 00000000 表示默认路由
		if fields[1] == "00000000" && fields[2] != "00000000" {
			hex := fields[2]
			if len(hex) != 8 {
				continue
			}
			// Gateway 字段是小端序十六进制，需逐字节反转后转为点分十进制
			ip := fmt.Sprintf("%d.%d.%d.%d",
				hexByte(hex[6:8]),
				hexByte(hex[4:6]),
				hexByte(hex[2:4]),
				hexByte(hex[0:2]),
			)
			return ip
		}
	}
	return ""
}

// hexByte 将两位十六进制字符串转换为整数
func hexByte(h string) int {
	val := 0
	for _, c := range h {
		val <<= 4
		switch {
		case c >= '0' && c <= '9':
			val += int(c - '0')
		case c >= 'a' && c <= 'f':
			val += int(c-'a') + 10
		case c >= 'A' && c <= 'F':
			val += int(c-'A') + 10
		}
	}
	return val
}
