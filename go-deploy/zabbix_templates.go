package main

import (
	"embed"
	"encoding/json"
	"errors"
	"fmt"
	"io/fs"
	"path/filepath"
	"strings"
	"time"
)

// ─── 嵌入模板文件 ──────────────────────────────────────────

//go:embed templates/*.yaml
var embeddedTemplates embed.FS

// ─── 模板信息 ──────────────────────────────────────────────

// TemplateFile 代表一个内嵌的模板文件
type TemplateFile struct {
	Name    string // 文件名（不含路径）
	Content []byte // YAML 内容
}

// listEmbeddedTemplates 列出所有内嵌的模板文件
func listEmbeddedTemplates() ([]TemplateFile, error) {
	var templates []TemplateFile

	err := fs.WalkDir(embeddedTemplates, "templates", func(path string, d fs.DirEntry, err error) error {
		if err != nil {
			return err
		}
		if d.IsDir() {
			return nil
		}
		if !strings.HasSuffix(path, ".yaml") && !strings.HasSuffix(path, ".yml") {
			return nil
		}
		content, err := embeddedTemplates.ReadFile(path)
		if err != nil {
			return fmt.Errorf("读取模板文件 %s 失败: %w", path, err)
		}
		templates = append(templates, TemplateFile{
			Name:    filepath.Base(path),
			Content: content,
		})
		return nil
	})

	if err != nil {
		return nil, err
	}
	return templates, nil
}

// ─── 导入结果 ──────────────────────────────────────────────

// TemplateImportResult 单个模板的导入结果
type TemplateImportResult struct {
	Name         string
	TemplateName string // Zabbix 中的模板 visible name（从 YAML 解析）
	Success      bool
	Skipped      bool   // 已存在且未指定 --force，跳过
	Error        string // 仅 Success=false && Skipped=false 时有值
}

// ImportTemplatesResult 整批导入结果
type ImportTemplatesResult struct {
	Total     int
	Succeeded int
	Skipped   int
	Failed    int
	Results   []TemplateImportResult
}

// ─── 导入选项 ──────────────────────────────────────────────

// ImportTemplatesOptions 控制导入行为
type ImportTemplatesOptions struct {
	// APIURL 形如 http://host:port/api_jsonrpc.php；若为空则根据 WebPort 自动构建
	APIURL string
	// WebPort 当 APIURL 为空时使用（默认 8080）
	WebPort int
	// Username Zabbix 登录用户名（默认 Admin）
	Username string
	// Password Zabbix 登录密码（默认 zabbix）
	Password string
	// Force 强制覆盖已存在的模板（对应 py 脚本的 --force）
	// false（默认）：已存在则跳过并标记 Skipped
	// true：无论是否已存在都执行导入覆盖
	Force bool
}

// ─── Zabbix configuration.import rules ────────────────────

// buildImportRules 构建 configuration.import 的 rules 参数。
//
// 字段集合和命名与 convert_snmp_templates.py 的 import_template() 保持一致，
// 经实测在 Zabbix 7.0 可用（snake_case 与 camelCase 混用是 Zabbix 的历史遗留）。
//
// templateLinkage 在 Zabbix 7.0 API 中只支持 createMissing + deleteMissing，
// 不支持 updateExisting，否则返回 -32602 Invalid params。
func buildImportRules() map[string]interface{} {
	return map[string]interface{}{
		// snake_case（Zabbix 7.0 实测可用）
		"template_groups": map[string]interface{}{
			"createMissing":  true,
			"updateExisting": false,
		},
		"templates": map[string]interface{}{
			"createMissing":  true,
			"updateExisting": true,
		},
		"items": map[string]interface{}{
			"createMissing":  true,
			"updateExisting": true,
			"deleteMissing":  false,
		},
		"triggers": map[string]interface{}{
			"createMissing":  true,
			"updateExisting": true,
			"deleteMissing":  false,
		},
		// camelCase（Zabbix 7.0 实测可用）
		"discoveryRules": map[string]interface{}{
			"createMissing":  true,
			"updateExisting": true,
			"deleteMissing":  false,
		},
		"valueMaps": map[string]interface{}{
			"createMissing":  true,
			"updateExisting": true,
		},
		"graphs": map[string]interface{}{
			"createMissing":  true,
			"updateExisting": true,
			"deleteMissing":  false,
		},
		// templateLinkage 仅支持 createMissing + deleteMissing，无 updateExisting
		"templateLinkage": map[string]interface{}{
			"createMissing": true,
			"deleteMissing": false,
		},
		"templateDashboards": map[string]interface{}{
			"createMissing":  false,
			"updateExisting": false,
			"deleteMissing":  false,
		},
	}
}

// ─── 从 YAML 解析模板 visible name ────────────────────────

// parseTemplateName 从 YAML 内容中提取模板的 visible name（name 字段）。
// YAML 结构片段：
//
//	zabbix_export:
//	  templates:
//	    - uuid: ...
//	      template: H3C_LINUX_by_SNMP
//	      name: 'H3C Linux by SNMP'   ← 这个
//
// 采用简单的行扫描，不引入 YAML 解析库，避免增加依赖。
func parseTemplateName(content []byte) string {
	lines := strings.Split(string(content), "\n")
	inTemplates := false
	for _, line := range lines {
		trimmed := strings.TrimSpace(line)
		// 进入 templates: 块
		if trimmed == "templates:" {
			inTemplates = true
			continue
		}
		if !inTemplates {
			continue
		}
		// 遇到同级其他块则退出
		if len(line) > 0 && line[0] != ' ' && trimmed != "" {
			break
		}
		// 匹配 "      name: '...'" 或 `      name: ...`
		if strings.HasPrefix(trimmed, "name:") {
			val := strings.TrimPrefix(trimmed, "name:")
			val = strings.TrimSpace(val)
			val = strings.Trim(val, "'\"")
			if val != "" {
				return val
			}
		}
	}
	return ""
}

// ─── 检查模板是否已存在 ────────────────────────────────────

// templateExists 通过 template.get 检查指定 visible name 的模板是否已存在于 Zabbix。
func templateExists(apiURL, authToken, templateName string) (bool, error) {
	if templateName == "" {
		// 无法解析名称，当作不存在，让 import 自行处理
		return false, nil
	}
	resp, err := rpcCall(apiURL, "template.get", map[string]interface{}{
		"output":      []string{"templateid"},
		"filter":      map[string]interface{}{"name": templateName},
		"searchByAny": false,
		"limit":       1,
	}, authToken)
	if err != nil {
		return false, fmt.Errorf("template.get 请求失败: %w", err)
	}
	if resp.Error != nil {
		return false, fmt.Errorf("template.get 错误 (code=%d): %s", resp.Error.Code, resp.Error.Data)
	}
	// result 是数组，非空即存在
	var rows []json.RawMessage
	if err := json.Unmarshal(resp.Result, &rows); err != nil {
		return false, fmt.Errorf("解析 template.get 响应失败: %w", err)
	}
	return len(rows) > 0, nil
}

// ─── 已存在类错误 ──────────────────────────────────────────

// ErrAlreadyExists 表示导入因目标已存在而冲突（非真正的失败）。
// 调用方可通过 errors.As 或 errors.Is 判断。
type ErrAlreadyExists struct {
	Detail string // Zabbix 返回的 data 字段原文
}

func (e *ErrAlreadyExists) Error() string {
	return e.Detail
}

// alreadyExistsPhrases 列出 Zabbix API 在"已存在"场景下 data 字段可能包含的关键词。
// 只要 data 中含有其中之一，即视为"已存在类"冲突，而非真正的导入错误。
var alreadyExistsPhrases = []string{
	"already exists",     // Template/valuemap/... with ... already exists
	"already been added", // Template has already been added
}

// isAlreadyExistsError 判断 Zabbix RPC 错误是否属于"已存在类"冲突。
func isAlreadyExistsError(rpcErr *zabbixRPCError) bool {
	if rpcErr == nil {
		return false
	}
	// Zabbix 对此类错误统一使用 -32602（Invalid params）
	if rpcErr.Code != -32602 {
		return false
	}
	for _, phrase := range alreadyExistsPhrases {
		if strings.Contains(rpcErr.Data, phrase) {
			return true
		}
	}
	return false
}

// ─── 单模板导入 ────────────────────────────────────────────

// importSingleTemplate 通过 configuration.import 导入单个 YAML 模板。
// rules 固定使用 buildImportRules()，与 py 脚本行为一致。
//
// 返回值：
//   - nil                → 导入成功
//   - *ErrAlreadyExists  → 模板或其子对象（valuemap 等）已存在，属于可忽略冲突
//   - 其他 error         → 真正的导入失败
func importSingleTemplate(apiURL, authToken string, tmpl TemplateFile) error {
	resp, err := rpcCall(apiURL, "configuration.import", map[string]interface{}{
		"format": "yaml",
		"rules":  buildImportRules(),
		"source": string(tmpl.Content),
	}, authToken)
	if err != nil {
		return fmt.Errorf("API 请求失败: %w", err)
	}
	if resp.Error != nil {
		if isAlreadyExistsError(resp.Error) {
			return &ErrAlreadyExists{Detail: resp.Error.Data}
		}
		return fmt.Errorf("导入失败 (code=%d): %s — %s",
			resp.Error.Code, resp.Error.Message, resp.Error.Data)
	}
	// 成功时 result 为 true
	var ok bool
	if err := json.Unmarshal(resp.Result, &ok); err != nil || !ok {
		return fmt.Errorf("API 返回非预期结果: %s", string(resp.Result))
	}
	return nil
}

// ─── 进度回调 ──────────────────────────────────────────────

// ImportTemplatesCallbacks 各阶段的进度回调
type ImportTemplatesCallbacks struct {
	// OnStart 开始前调用，传入模板总数
	OnStart func(total int)
	// OnTemplateDone 每个模板处理完成后调用（无论成功/跳过/失败）
	OnTemplateDone func(result TemplateImportResult, index int, total int)
	// OnDone 全部处理完成后调用
	OnDone func(result ImportTemplatesResult)
}

// ─── 主入口：批量导入 ──────────────────────────────────────

// ImportEmbeddedTemplates 将二进制中内嵌的全部 YAML 模板导入到目标 Zabbix。
//
// 行为与 convert_snmp_templates.py 的 convert_all() 保持一致：
//   - Force=false（默认）：若模板已存在则跳过（Skipped），不报错
//   - Force=true：无论是否已存在都执行导入（覆盖）
func ImportEmbeddedTemplates(opts ImportTemplatesOptions, cb *ImportTemplatesCallbacks) ImportTemplatesResult {
	// ── 1. 列出内嵌模板 ───────────────────────────────────
	templates, err := listEmbeddedTemplates()
	if err != nil {
		r := ImportTemplatesResult{
			Total:  0,
			Failed: 1,
			Results: []TemplateImportResult{
				{Name: "<embed>", Success: false, Error: err.Error()},
			},
		}
		if cb != nil && cb.OnDone != nil {
			cb.OnDone(r)
		}
		return r
	}

	total := len(templates)
	result := ImportTemplatesResult{
		Total:   total,
		Results: make([]TemplateImportResult, 0, total),
	}

	if cb != nil && cb.OnStart != nil {
		cb.OnStart(total)
	}

	// ── 2. 构建 API URL ───────────────────────────────────
	apiURL := opts.APIURL
	if apiURL == "" {
		if opts.WebPort == 0 {
			opts.WebPort = 8080
		}
		apiURL = buildAPIURL(opts.WebPort)
	}

	// ── 3. 等待 API 就绪（最多 60s） ─────────────────────
	apiURL = waitForAPIWithTimeout(apiURL, 60_000)
	if apiURL == "" {
		errMsg := "Zabbix API 不可达（超时 60s）"
		for _, tmpl := range templates {
			result.Results = append(result.Results, TemplateImportResult{
				Name:  tmpl.Name,
				Error: errMsg,
			})
		}
		result.Failed = total
		if cb != nil && cb.OnDone != nil {
			cb.OnDone(result)
		}
		return result
	}

	// ── 4. 登录 ───────────────────────────────────────────
	username := opts.Username
	if username == "" {
		username = defaultZabbixUsername
	}
	password := opts.Password
	if password == "" {
		password = defaultZabbixPassword
	}

	authToken, err := zabbixLoginWithCredentials(apiURL, username, password)
	if err != nil {
		errMsg := fmt.Sprintf("登录失败: %v", err)
		for _, tmpl := range templates {
			result.Results = append(result.Results, TemplateImportResult{
				Name:  tmpl.Name,
				Error: errMsg,
			})
		}
		result.Failed = total
		if cb != nil && cb.OnDone != nil {
			cb.OnDone(result)
		}
		return result
	}

	// ── 5. 逐个处理 ───────────────────────────────────────
	for i, tmpl := range templates {
		tr := TemplateImportResult{Name: tmpl.Name}

		// 从 YAML 内容解析 visible name，用于存在性检查
		tplVisibleName := parseTemplateName(tmpl.Content)
		tr.TemplateName = tplVisibleName

		if !opts.Force {
			// 检查是否已存在
			exists, checkErr := templateExists(apiURL, authToken, tplVisibleName)
			if checkErr != nil {
				// 检查本身失败：降级为直接尝试导入，不跳过
				// （与 py 脚本遇到 API 异常时的行为一致）
			} else if exists {
				tr.Skipped = true
				tr.Success = false // 跳过不算成功，由调用方区分显示
				result.Skipped++
				result.Results = append(result.Results, tr)
				if cb != nil && cb.OnTemplateDone != nil {
					cb.OnTemplateDone(tr, i+1, total)
				}
				continue
			}
		}

		// 执行导入
		if importErr := importSingleTemplate(apiURL, authToken, tmpl); importErr != nil {
			var existsErr *ErrAlreadyExists
			if !opts.Force && errors.As(importErr, &existsErr) {
				// Force=false 时，"已存在类"冲突等同于跳过，不计为失败
				tr.Skipped = true
				tr.Success = false
				result.Skipped++
			} else {
				tr.Success = false
				tr.Error = importErr.Error()
				result.Failed++
			}
		} else {
			tr.Success = true
			result.Succeeded++
		}

		result.Results = append(result.Results, tr)
		if cb != nil && cb.OnTemplateDone != nil {
			cb.OnTemplateDone(tr, i+1, total)
		}
	}

	if cb != nil && cb.OnDone != nil {
		cb.OnDone(result)
	}
	return result
}

// ─── 辅助：带超时的 API 可达性探测 ────────────────────────

// waitForAPIWithTimeout 轮询直到 API 可达或超时，返回可用 URL；超时返回空串。
func waitForAPIWithTimeout(apiURL string, timeoutMs int) string {
	deadline := time.Now().Add(time.Duration(timeoutMs) * time.Millisecond)
	interval := 3 * time.Second
	for time.Now().Before(deadline) {
		resp, err := rpcCall(apiURL, "apiinfo.version", map[string]interface{}{}, "")
		if err == nil && resp != nil && resp.Result != nil {
			return apiURL
		}
		time.Sleep(interval)
	}
	return ""
}

// ─── 辅助：带自定义凭据登录 ───────────────────────────────

// zabbixLoginWithCredentials 使用指定用户名密码登录，返回认证令牌。
func zabbixLoginWithCredentials(apiURL, username, password string) (string, error) {
	resp, err := rpcCall(apiURL, "user.login", map[string]interface{}{
		"username": username,
		"password": password,
	}, "")
	if err != nil {
		return "", err
	}
	if resp.Error != nil {
		return "", fmt.Errorf("Zabbix 登录失败 (code=%d): %s", resp.Error.Code, resp.Error.Data)
	}
	var token string
	if err := json.Unmarshal(resp.Result, &token); err != nil {
		return "", fmt.Errorf("解析登录令牌失败: %w", err)
	}
	return token, nil
}

// ─── 列出内嵌模板（CLI 用） ────────────────────────────────

// PrintEmbeddedTemplateList 打印内嵌模板列表，供 list-templates 子命令使用。
func PrintEmbeddedTemplateList() {
	templates, err := listEmbeddedTemplates()
	if err != nil {
		logError(fmt.Sprintf("列出模板失败: %v", err))
		return
	}
	if len(templates) == 0 {
		logWarn("未找到任何内嵌模板")
		return
	}
	logInfo(fmt.Sprintf("内嵌模板列表（共 %d 个）:", len(templates)))
	for i, tmpl := range templates {
		visibleName := parseTemplateName(tmpl.Content)
		nameHint := ""
		if visibleName != "" {
			nameHint = fmt.Sprintf("  [%s]", visibleName)
		}
		logInfo(fmt.Sprintf("  %2d. %s%s  (%d 字节)", i+1, tmpl.Name, nameHint, len(tmpl.Content)))
	}
}
