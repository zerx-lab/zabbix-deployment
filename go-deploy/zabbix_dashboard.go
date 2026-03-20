package main

import (
	"encoding/json"
	"fmt"
)

// ─── 仪表盘 Widget Field 辅助构造 ─────────────────────────

// widgetField 构建一个 widget field 对象
func widgetField(fieldType int, name string, value interface{}) map[string]interface{} {
	return map[string]interface{}{
		"type":  fieldType,
		"name":  name,
		"value": value,
	}
}

// ─── TopHosts Widget 通用列构建 ────────────────────────────

// thColumn 构建 tophosts widget 的一列配置
type thColumn struct {
	name              string
	itemName          string
	data              int    // 1=item, 2=host name
	display           int    // 1=plain, 3=bar
	min               string // 仅 bar 模式需要
	max               string // 仅 bar 模式需要
	decimalPlaces     int
	baseColor         string
	thresholds        []thThreshold // 颜色阈值
	aggregateFunction int
	history           int // 1=history, 2=trend
}

type thThreshold struct {
	color     string
	threshold string
}

// buildTopHostsFields 将 thColumn 列表转换为 tophosts widget fields
func buildTopHostsFields(cols []thColumn) []map[string]interface{} {
	fields := []map[string]interface{}{}
	for i, col := range cols {
		idx := fmt.Sprintf("%d", i)
		fields = append(fields,
			widgetField(1, "columns."+idx+".name", col.name),
			widgetField(0, "columns."+idx+".data", col.data),
		)
		if col.data == 1 {
			fields = append(fields,
				widgetField(1, "columns."+idx+".item", col.itemName),
				widgetField(0, "columns."+idx+".aggregate_function", col.aggregateFunction),
			)
			if col.min != "" {
				fields = append(fields, widgetField(1, "columns."+idx+".min", col.min))
			}
			if col.max != "" {
				fields = append(fields, widgetField(1, "columns."+idx+".max", col.max))
			}
			fields = append(fields,
				widgetField(0, "columns."+idx+".decimal_places", col.decimalPlaces),
				widgetField(0, "columns."+idx+".display", col.display),
				widgetField(0, "columns."+idx+".history", col.history),
			)
		} else {
			// data=2 host name 列
			fields = append(fields,
				widgetField(0, "columns."+idx+".aggregate_function", 0),
				widgetField(0, "columns."+idx+".decimal_places", col.decimalPlaces),
			)
		}
		fields = append(fields, widgetField(1, "columns."+idx+".base_color", col.baseColor))

		// 颜色阈值
		for ti, th := range col.thresholds {
			tidx := fmt.Sprintf("%d", ti)
			fields = append(fields,
				widgetField(1, fmt.Sprintf("columnsthresholds.%s.color.%s", idx, tidx), th.color),
				widgetField(1, fmt.Sprintf("columnsthresholds.%s.threshold.%s", idx, tidx), th.threshold),
			)
		}
	}
	fields = append(fields, widgetField(0, "column", 1))
	return fields
}

// ─── 仪表盘页面 / Widget 结构 ──────────────────────────────

// dashboardWidget 描述一个仪表盘组件
type dashboardWidget struct {
	Type     string                   `json:"type"`
	Name     string                   `json:"name"`
	X        int                      `json:"x"`
	Y        int                      `json:"y"`
	Width    int                      `json:"width"`
	Height   int                      `json:"height"`
	ViewMode int                      `json:"view_mode"`
	Fields   []map[string]interface{} `json:"fields"`
}

// dashboardPage 描述一个仪表盘页面
type dashboardPage struct {
	Name    string            `json:"name"`
	Widgets []dashboardWidget `json:"widgets"`
}

// ─── 仪表盘创建选项 ────────────────────────────────────────

// CreateDashboardOptions 控制仪表盘创建行为
type CreateDashboardOptions struct {
	// APIURL 形如 http://host:port/api_jsonrpc.php；若为空则根据 WebPort 自动构建
	APIURL string
	// WebPort 当 APIURL 为空时使用（默认 8080）
	WebPort int
	// Username Zabbix 登录用户名（默认 Admin）
	Username string
	// Password Zabbix 登录密码（默认 zabbix）
	Password string
	// Force 若仪表盘已存在则先删除再创建（默认 false：已存在则跳过）
	Force bool
}

// CreateDashboardResult 仪表盘创建结果
type CreateDashboardResult struct {
	Success     bool
	Skipped     bool   // 已存在且未设 Force，跳过
	DashboardID string // 创建成功时的 ID
	Error       string
}

// ─── 预设仪表盘定义 ────────────────────────────────────────

const serverDashboardName = "服务器硬件巡检总览"

// buildServerDashboardPages 构建「服务器硬件巡检总览」仪表盘的所有页面
func buildServerDashboardPages() []dashboardPage {
	return []dashboardPage{
		buildOverviewPage(),
		buildCPUMemoryPage(),
		buildNetworkPage(),
		buildDiskPage(),
		buildPowerFanPage(),
	}
}

// ─── 第1页：综合概览 ───────────────────────────────────────

func buildOverviewPage() dashboardPage {
	return dashboardPage{
		Name: "综合概览",
		Widgets: []dashboardWidget{
			{
				Type: "systeminfo", Name: "Zabbix 系统信息",
				X: 0, Y: 0, Width: 24, Height: 3, ViewMode: 0,
				Fields: []map[string]interface{}{},
			},
			{
				Type: "clock", Name: "当前时间",
				X: 24, Y: 0, Width: 12, Height: 3, ViewMode: 0,
				Fields: []map[string]interface{}{
					widgetField(0, "time_type", 0),
				},
			},
			{
				Type: "problems", Name: "当前告警事件",
				X: 36, Y: 0, Width: 36, Height: 6, ViewMode: 0,
				Fields: []map[string]interface{}{
					widgetField(0, "show", 3),
					widgetField(0, "show_lines", 10),
					widgetField(0, "show_suppressed", 0),
				},
			},
			{
				Type: "hostavail", Name: "主机可用性状态",
				X: 0, Y: 3, Width: 36, Height: 3, ViewMode: 0,
				Fields: []map[string]interface{}{
					widgetField(0, "layout", 0),
				},
			},
			{
				Type: "tophosts", Name: "CPU & 内存利用率 Top 主机",
				X: 0, Y: 6, Width: 72, Height: 6, ViewMode: 0,
				Fields: buildTopHostsFields([]thColumn{
					{
						name: "主机名", data: 2, decimalPlaces: 2, baseColor: "",
					},
					{
						name: "CPU利用率", itemName: "CPU 总利用率",
						data: 1, display: 3, min: "0", max: "100",
						decimalPlaces: 2, history: 1, baseColor: "4CAF50",
						thresholds: []thThreshold{
							{"FFFF00", "60"}, {"FF8000", "80"}, {"FF0000", "90"},
						},
					},
					{
						name: "内存利用率", itemName: "内存利用率",
						data: 1, display: 3, min: "0", max: "100",
						decimalPlaces: 2, history: 1, baseColor: "2196F3",
						thresholds: []thThreshold{
							{"FFFF00", "70"}, {"FF0000", "90"},
						},
					},
					{
						name: "SNMP状态", itemName: "SNMP availability",
						data: 1, display: 1, decimalPlaces: 0, history: 1, baseColor: "",
					},
					{
						name: "ICMP丢包率", itemName: "ICMP ping loss",
						data: 1, display: 3, min: "0", max: "100",
						decimalPlaces: 1, history: 1, baseColor: "4CAF50",
						thresholds: []thThreshold{
							{"FFFF00", "10"}, {"FF0000", "30"},
						},
					},
					{
						name: "运行时长", itemName: "Uptime (hardware)",
						data: 1, display: 1, decimalPlaces: 0, history: 1, baseColor: "",
					},
				}),
			},
			{
				Type: "problemhosts", Name: "存在问题的主机",
				X: 0, Y: 12, Width: 36, Height: 4, ViewMode: 0,
				Fields: []map[string]interface{}{
					widgetField(0, "show_suppressed", 0),
				},
			},
			{
				Type: "problemsbysv", Name: "告警严重性分布",
				X: 36, Y: 12, Width: 36, Height: 4, ViewMode: 0,
				Fields: []map[string]interface{}{
					widgetField(0, "show_type", 0),
					widgetField(0, "show_suppressed", 0),
				},
			},
		},
	}
}

// ─── 第2页：CPU & 内存 ─────────────────────────────────────

func buildCPUMemoryPage() dashboardPage {
	return dashboardPage{
		Name: "CPU & 内存",
		Widgets: []dashboardWidget{
			{
				Type: "tophosts", Name: "CPU 详细利用率",
				X: 0, Y: 0, Width: 72, Height: 7, ViewMode: 0,
				Fields: buildTopHostsFields([]thColumn{
					{name: "主机名", data: 2, decimalPlaces: 2, baseColor: ""},
					{
						name: "总利用率", itemName: "CPU 总利用率",
						data: 1, display: 3, min: "0", max: "100",
						decimalPlaces: 2, history: 1, baseColor: "4CAF50",
						thresholds: []thThreshold{{"FFFF00", "60"}, {"FF0000", "85"}},
					},
					{
						name: "用户态", itemName: "CPU 利用率（用户态）",
						data: 1, display: 3, min: "0", max: "100",
						decimalPlaces: 2, history: 1, baseColor: "03A9F4",
					},
					{
						name: "系统态", itemName: "CPU 利用率（系统态）",
						data: 1, display: 3, min: "0", max: "100",
						decimalPlaces: 2, history: 1, baseColor: "FF9800",
					},
					{
						name: "IO等待", itemName: "CPU 利用率（I/O 等待）",
						data: 1, display: 3, min: "0", max: "100",
						decimalPlaces: 2, history: 1, baseColor: "F44336",
					},
					{
						name: "负载(1m)", itemName: "CPU 负载（1分钟）",
						data: 1, display: 1, decimalPlaces: 2, history: 1, baseColor: "",
					},
					{
						name: "负载(5m)", itemName: "CPU 负载（5分钟）",
						data: 1, display: 1, decimalPlaces: 2, history: 1, baseColor: "",
					},
					{
						name: "负载(15m)", itemName: "CPU 负载（15分钟）",
						data: 1, display: 1, decimalPlaces: 2, history: 1, baseColor: "",
					},
				}),
			},
			{
				Type: "tophosts", Name: "内存详细状态",
				X: 0, Y: 7, Width: 72, Height: 6, ViewMode: 0,
				Fields: buildTopHostsFields([]thColumn{
					{name: "主机名", data: 2, decimalPlaces: 2, baseColor: ""},
					{
						name: "内存利用率", itemName: "内存利用率",
						data: 1, display: 3, min: "0", max: "100",
						decimalPlaces: 2, history: 1, baseColor: "2196F3",
						thresholds: []thThreshold{{"FFFF00", "70"}, {"FF0000", "90"}},
					},
					{
						name: "内存总量", itemName: "内存总量",
						data: 1, display: 1, decimalPlaces: 2, history: 1, baseColor: "",
					},
					{
						name: "可用内存", itemName: "可用内存",
						data: 1, display: 1, decimalPlaces: 2, history: 1, baseColor: "",
					},
					{
						name: "Swap总量", itemName: "Swap 总量",
						data: 1, display: 1, decimalPlaces: 2, history: 1, baseColor: "",
					},
					{
						name: "Swap剩余", itemName: "Swap 剩余",
						data: 1, display: 1, decimalPlaces: 2, history: 1, baseColor: "",
					},
				}),
			},
		},
	}
}

// ─── 第3页：网络 & PING & SNMP ────────────────────────────

func buildNetworkPage() dashboardPage {
	return dashboardPage{
		Name: "网络 & PING & SNMP",
		Widgets: []dashboardWidget{
			{
				Type: "tophosts", Name: "PING状态 & SNMP连通性",
				X: 0, Y: 0, Width: 72, Height: 7, ViewMode: 0,
				Fields: buildTopHostsFields([]thColumn{
					{name: "主机名", data: 2, decimalPlaces: 2, baseColor: ""},
					{
						name: "ICMP Ping", itemName: "ICMP ping",
						data: 1, display: 1, decimalPlaces: 0, history: 1, baseColor: "4CAF50",
						thresholds: []thThreshold{{"FF0000", "0.5"}},
					},
					{
						name: "丢包率(%)", itemName: "ICMP ping loss",
						data: 1, display: 3, min: "0", max: "100",
						decimalPlaces: 1, history: 1, baseColor: "4CAF50",
						thresholds: []thThreshold{{"FFFF00", "5"}, {"FF0000", "20"}},
					},
					{
						name: "响应时间", itemName: "ICMP response time",
						data: 1, display: 1, decimalPlaces: 4, history: 1, baseColor: "",
					},
					{
						name: "SNMP可用性", itemName: "SNMP availability",
						data: 1, display: 1, decimalPlaces: 0, history: 1, baseColor: "",
					},
					{
						name: "网络运行时长", itemName: "Uptime (network)",
						data: 1, display: 1, decimalPlaces: 0, history: 1, baseColor: "",
					},
					{
						name: "硬件运行时长", itemName: "Uptime (hardware)",
						data: 1, display: 1, decimalPlaces: 0, history: 1, baseColor: "",
					},
				}),
			},
			{
				Type: "tophosts", Name: "主机基本信息",
				X: 0, Y: 7, Width: 72, Height: 6, ViewMode: 0,
				Fields: buildTopHostsFields([]thColumn{
					{name: "主机名", data: 2, decimalPlaces: 2, baseColor: ""},
					{
						name: "系统名称", itemName: "System name",
						data: 1, display: 1, decimalPlaces: 0, history: 1, baseColor: "",
					},
					{
						name: "系统描述", itemName: "System description",
						data: 1, display: 1, decimalPlaces: 0, history: 1, baseColor: "",
					},
					{
						name: "系统位置", itemName: "System location",
						data: 1, display: 1, decimalPlaces: 0, history: 1, baseColor: "",
					},
					{
						name: "联系人", itemName: "System contact details",
						data: 1, display: 1, decimalPlaces: 0, history: 1, baseColor: "",
					},
				}),
			},
		},
	}
}

// ─── 第4页：硬盘 & 文件系统 ───────────────────────────────

func buildDiskPage() dashboardPage {
	return dashboardPage{
		Name: "硬盘 & 文件系统",
		Widgets: []dashboardWidget{
			{
				Type: "tophosts", Name: "服务器硬件信息（型号/序列号/BIOS）",
				X: 0, Y: 0, Width: 72, Height: 5, ViewMode: 0,
				Fields: buildTopHostsFields([]thColumn{
					{name: "主机名", data: 2, decimalPlaces: 2, baseColor: ""},
					{
						name: "整体健康状态", itemName: "Overall system health status",
						data: 1, display: 1, decimalPlaces: 0, history: 1, baseColor: "",
					},
					{
						name: "硬件型号", itemName: "Hardware model name",
						data: 1, display: 1, decimalPlaces: 0, history: 1, baseColor: "",
					},
					{
						name: "序列号", itemName: "Hardware serial number",
						data: 1, display: 1, decimalPlaces: 0, history: 1, baseColor: "",
					},
					{
						name: "BIOS版本", itemName: "BIOS version",
						data: 1, display: 1, decimalPlaces: 0, history: 1, baseColor: "",
					},
					{
						name: "固件版本", itemName: "Firmware version",
						data: 1, display: 1, decimalPlaces: 0, history: 1, baseColor: "",
					},
				}),
			},
			{
				Type: "problems", Name: "硬盘 & 存储相关告警",
				X: 0, Y: 5, Width: 72, Height: 6, ViewMode: 0,
				Fields: []map[string]interface{}{
					widgetField(0, "show", 3),
					widgetField(0, "show_lines", 15),
					widgetField(1, "tags.0.tag", "component"),
					widgetField(0, "tags.0.operator", 0),
					widgetField(1, "tags.0.value", "storage"),
					widgetField(0, "show_suppressed", 0),
				},
			},
		},
	}
}

// ─── 第5页：电源 & 风扇 & 温度 ────────────────────────────

func buildPowerFanPage() dashboardPage {
	return dashboardPage{
		Name: "电源 & 风扇 & 温度",
		Widgets: []dashboardWidget{
			{
				Type: "problems", Name: "电源 & 风扇 & 温度告警",
				X: 0, Y: 0, Width: 72, Height: 8, ViewMode: 0,
				Fields: []map[string]interface{}{
					widgetField(0, "show", 3),
					widgetField(0, "show_lines", 20),
					widgetField(0, "show_suppressed", 0),
				},
			},
			{
				Type: "tophosts", Name: "服务器综合硬件状态",
				X: 0, Y: 8, Width: 72, Height: 6, ViewMode: 0,
				Fields: buildTopHostsFields([]thColumn{
					{name: "主机名", data: 2, decimalPlaces: 2, baseColor: ""},
					{
						name: "整体健康", itemName: "Overall system health status",
						data: 1, display: 1, decimalPlaces: 0, history: 1, baseColor: "",
					},
					{
						name: "操作系统", itemName: "Operating system",
						data: 1, display: 1, decimalPlaces: 0, history: 1, baseColor: "",
					},
					{
						name: "系统联系人", itemName: "System contact details",
						data: 1, display: 1, decimalPlaces: 0, history: 1, baseColor: "",
					},
				}),
			},
		},
	}
}

// ─── 仪表盘查询与删除 ──────────────────────────────────────

// getDashboardIDByName 按名称查找仪表盘 ID，未找到返回空字符串
func getDashboardIDByName(apiURL, authToken, name string) (string, error) {
	resp, err := rpcCall(apiURL, "dashboard.get", map[string]interface{}{
		"output": []string{"dashboardid", "name"},
		"filter": map[string]interface{}{"name": []string{name}},
	}, authToken)
	if err != nil {
		return "", err
	}
	if resp.Error != nil {
		return "", fmt.Errorf("查询仪表盘失败: %s", resp.Error.Data)
	}

	var dashboards []struct {
		DashboardID string `json:"dashboardid"`
		Name        string `json:"name"`
	}
	if err := json.Unmarshal(resp.Result, &dashboards); err != nil {
		return "", fmt.Errorf("解析仪表盘列表失败: %w", err)
	}
	if len(dashboards) == 0 {
		return "", nil
	}
	return dashboards[0].DashboardID, nil
}

// deleteDashboard 按 ID 删除仪表盘
func deleteDashboard(apiURL, authToken, dashboardID string) error {
	resp, err := rpcCall(apiURL, "dashboard.delete", map[string]interface{}{
		"dashboardids": []string{dashboardID},
	}, authToken)
	if err != nil {
		return err
	}
	if resp.Error != nil {
		return fmt.Errorf("删除仪表盘失败: %s", resp.Error.Data)
	}
	return nil
}

// ─── 仪表盘创建 ────────────────────────────────────────────

// createDashboardViaAPI 通过 Zabbix API 创建仪表盘，返回新 dashboardid
func createDashboardViaAPI(apiURL, authToken string, pages []dashboardPage) (string, error) {
	// 将强类型页面转换为 interface{} 切片（rpcCall 需要 map[string]interface{}）
	pagesRaw := make([]interface{}, len(pages))
	for i, p := range pages {
		widgetsRaw := make([]interface{}, len(p.Widgets))
		for j, w := range p.Widgets {
			widgetsRaw[j] = map[string]interface{}{
				"type":      w.Type,
				"name":      w.Name,
				"x":         w.X,
				"y":         w.Y,
				"width":     w.Width,
				"height":    w.Height,
				"view_mode": w.ViewMode,
				"fields":    w.Fields,
			}
		}
		pagesRaw[i] = map[string]interface{}{
			"name":    p.Name,
			"widgets": widgetsRaw,
		}
	}

	resp, err := rpcCall(apiURL, "dashboard.create", map[string]interface{}{
		"name":           serverDashboardName,
		"display_period": 30,
		"auto_start":     0,
		"private":        0,
		"pages":          pagesRaw,
	}, authToken)
	if err != nil {
		return "", err
	}
	if resp.Error != nil {
		return "", fmt.Errorf("创建仪表盘失败: %s", resp.Error.Data)
	}

	var result struct {
		DashboardIDs []string `json:"dashboardids"`
	}
	if err := json.Unmarshal(resp.Result, &result); err != nil {
		return "", fmt.Errorf("解析创建结果失败: %w", err)
	}
	if len(result.DashboardIDs) == 0 {
		return "", fmt.Errorf("创建仪表盘返回了空 ID 列表")
	}
	return result.DashboardIDs[0], nil
}

// ─── 对外公开入口 ──────────────────────────────────────────

// CreateServerDashboard 创建「服务器硬件巡检总览」仪表盘
//
// 流程：
//  1. 登录获取 authToken
//  2. 检查同名仪表盘是否已存在
//  3. 若已存在且未设 Force → 返回 Skipped
//  4. 若已存在且设 Force → 先删除旧仪表盘
//  5. 创建新仪表盘并返回 DashboardID
func CreateServerDashboard(opts CreateDashboardOptions) CreateDashboardResult {
	// 补全默认值
	apiURL := opts.APIURL
	if apiURL == "" {
		apiURL = buildAPIURL(opts.WebPort)
	}
	username := opts.Username
	if username == "" {
		username = defaultZabbixUsername
	}
	password := opts.Password
	if password == "" {
		password = defaultZabbixPassword
	}

	// 1. 登录
	resp, err := rpcCall(apiURL, "user.login", map[string]interface{}{
		"username": username,
		"password": password,
	}, "")
	if err != nil {
		return CreateDashboardResult{Error: fmt.Sprintf("登录失败: %v", err)}
	}
	if resp.Error != nil {
		return CreateDashboardResult{Error: fmt.Sprintf("登录失败: %s", resp.Error.Data)}
	}
	var authToken string
	if err := json.Unmarshal(resp.Result, &authToken); err != nil {
		return CreateDashboardResult{Error: fmt.Sprintf("解析 Token 失败: %v", err)}
	}

	// 2. 检查同名仪表盘
	existingID, err := getDashboardIDByName(apiURL, authToken, serverDashboardName)
	if err != nil {
		return CreateDashboardResult{Error: fmt.Sprintf("查询仪表盘失败: %v", err)}
	}

	if existingID != "" {
		if !opts.Force {
			// 已存在，不强制 → 跳过
			return CreateDashboardResult{
				Success:     true,
				Skipped:     true,
				DashboardID: existingID,
			}
		}
		// 已存在且强制 → 删除旧仪表盘
		if err := deleteDashboard(apiURL, authToken, existingID); err != nil {
			return CreateDashboardResult{Error: fmt.Sprintf("删除旧仪表盘失败: %v", err)}
		}
	}

	// 3. 构建并创建仪表盘
	pages := buildServerDashboardPages()
	dashboardID, err := createDashboardViaAPI(apiURL, authToken, pages)
	if err != nil {
		return CreateDashboardResult{Error: err.Error()}
	}

	return CreateDashboardResult{
		Success:     true,
		Skipped:     false,
		DashboardID: dashboardID,
	}
}
