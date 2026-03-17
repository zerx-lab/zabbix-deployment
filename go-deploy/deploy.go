package main

import (
	"fmt"
	"os"
	"path/filepath"
	"strings"
)

// ─── 部署前检查 ────────────────────────────────────────────

// preflightCheck 执行部署前的环境检查
func preflightCheck() bool {
	if !checkDocker() {
		return false
	}
	if !checkDockerCompose() {
		return false
	}
	return true
}

// ─── 健康检查步骤 ──────────────────────────────────────────

func runHealthCheckStep(deployDir string, cb *DeployCallbacks) (bool, HealthCheckResult) {
	if cb != nil && cb.OnStepStart != nil {
		cb.OnStepStart(DeployStepHealthCheck, "等待服务就绪（最长 3 分钟）...")
	}

	var onTick func(services []ServiceHealth, elapsed int64)
	if cb != nil && cb.OnHealthTick != nil {
		onTick = cb.OnHealthTick
	}

	healthResult := waitForHealthy(deployDir, onTick)

	if !healthResult.AllHealthy {
		var failedNames []string
		for _, s := range healthResult.Services {
			if !s.Healthy {
				failedNames = append(failedNames, fmt.Sprintf("%s(%s)", s.Name, s.State))
			}
		}
		joined := joinStrings(failedNames, ", ")
		reason := "部分服务异常"
		if healthResult.TimedOut {
			reason = "健康检查超时"
		}
		if cb != nil && cb.OnStepError != nil {
			cb.OnStepError(DeployStepHealthCheck, fmt.Sprintf("%s: %s", reason, joined))
		}
		return false, healthResult
	}

	elapsedSec := healthResult.Elapsed / 1000
	if cb != nil && cb.OnStepDone != nil {
		cb.OnStepDone(DeployStepHealthCheck, fmt.Sprintf("所有服务已就绪（耗时 %d 秒）", elapsedSec))
	}
	return true, healthResult
}

// ─── 部署后初始化步骤 ──────────────────────────────────────

func runPostInitStep(webPort int, cb *DeployCallbacks) *PostInitResult {
	if cb != nil && cb.OnStepStart != nil {
		cb.OnStepStart(DeployStepPostInit, "等待 Zabbix API 就绪（首次部署可能需要 3-5 分钟）...")
	}

	apiURL := waitForZabbixAPI(webPort)
	if apiURL == "" {
		if cb != nil && cb.OnStepError != nil {
			cb.OnStepError(DeployStepPostInit,
				"Zabbix API 未就绪（超时 5 分钟），请稍后手动修改默认主机 Agent 接口地址为 \"zabbix-agent\"")
		}
		return nil
	}

	result := postInitZabbix(apiURL)
	if !result.Success {
		if cb != nil && cb.OnStepError != nil {
			cb.OnStepError(DeployStepPostInit,
				fmt.Sprintf("自动配置失败: %s，请手动修改默认主机 Agent 接口地址", result.Error))
		}
		return &result
	}

	if result.AgentInterfaceFixed {
		if cb != nil && cb.OnStepDone != nil {
			cb.OnStepDone(DeployStepPostInit, "已自动修正 Agent 接口地址为容器名 \"zabbix-agent\"")
		}
	} else {
		if cb != nil && cb.OnStepDone != nil {
			cb.OnStepDone(DeployStepPostInit, "Agent 接口配置正常，无需修正")
		}
	}
	return &result
}

// ─── 主部署流程 ────────────────────────────────────────────

// deploy 执行 Zabbix 完整部署流程（7 个步骤）
//
//  1. preflight        — 环境预检（Docker/Compose 可用性）
//  2. load-images      — 加载离线镜像
//  3. create-dir       — 创建部署目录
//  4. generate-compose — 生成 docker-compose.yml
//  5. start-services   — 启动所有容器
//  6. health-check     — 等待所有服务就绪
//  7. post-init        — 部署后初始化（修正 Agent 接口地址等）
func deployZabbix(config DeployConfig, options DeployOptions, cb *DeployCallbacks) DeployResult {
	deployDir := options.DeployDir
	packagesDir := options.PackagesDir
	if packagesDir == "" {
		packagesDir = getPackagesDir()
	}
	composeFile := filepath.Join(deployDir, ComposeFileName)

	// ── 1. 环境预检 ────────────────────────────────────────
	if cb != nil && cb.OnStepStart != nil {
		cb.OnStepStart(DeployStepPreflight, "检查 Docker 环境...")
	}
	if !preflightCheck() {
		if cb != nil && cb.OnStepError != nil {
			cb.OnStepError(DeployStepPreflight, "Docker 环境检查未通过")
		}
		return DeployResult{Success: false}
	}
	if cb != nil && cb.OnStepDone != nil {
		cb.OnStepDone(DeployStepPreflight, "Docker 环境检查通过")
	}

	// ── 2. 加载离线镜像 ────────────────────────────────────
	if cb != nil && cb.OnStepStart != nil {
		cb.OnStepStart(DeployStepLoadImages, "加载离线镜像...")
	}
	var extraImages []string
	if config.Server.EnableSnmpTrapper {
		extraImages = []string{SnmpTrapsImage}
	}

	var onImageProgress func(result LoadResult, index int, total int)
	if cb != nil && cb.OnImageProgress != nil {
		onImageProgress = cb.OnImageProgress
	}

	loadResults := loadAllImages(packagesDir, options.SkipExistingImages, onImageProgress, extraImages)

	var failedImages []string
	for _, r := range loadResults {
		if !r.Success {
			failedImages = append(failedImages, r.Label)
		}
	}
	if len(failedImages) > 0 {
		if cb != nil && cb.OnStepError != nil {
			cb.OnStepError(DeployStepLoadImages,
				fmt.Sprintf("以下镜像加载失败: %s", joinStrings(failedImages, ", ")))
		}
		return DeployResult{Success: false}
	}

	skippedCount := 0
	loadedCount := 0
	for _, r := range loadResults {
		if r.Skipped {
			skippedCount++
		} else if r.Success {
			loadedCount++
		}
	}
	if cb != nil && cb.OnStepDone != nil {
		cb.OnStepDone(DeployStepLoadImages,
			fmt.Sprintf("镜像就绪（加载 %d 个，跳过 %d 个已存在）", loadedCount, skippedCount))
	}

	// ── 3. 创建部署目录 ────────────────────────────────────
	if cb != nil && cb.OnStepStart != nil {
		cb.OnStepStart(DeployStepCreateDir, fmt.Sprintf("创建部署目录: %s", deployDir))
	}
	if err := os.MkdirAll(deployDir, 0755); err != nil {
		if cb != nil && cb.OnStepError != nil {
			cb.OnStepError(DeployStepCreateDir, fmt.Sprintf("创建目录失败: %v", err))
		}
		return DeployResult{Success: false}
	}
	if cb != nil && cb.OnStepDone != nil {
		cb.OnStepDone(DeployStepCreateDir, "部署目录已就绪")
	}

	// ── 4. 生成 docker-compose.yml ─────────────────────────
	if cb != nil && cb.OnStepStart != nil {
		cb.OnStepStart(DeployStepGenerateCompose, "生成 docker-compose.yml...")
	}
	yamlContent := generateComposeYAML(config)
	if err := os.WriteFile(composeFile, []byte(yamlContent), 0644); err != nil {
		if cb != nil && cb.OnStepError != nil {
			cb.OnStepError(DeployStepGenerateCompose, fmt.Sprintf("写入配置文件失败: %v", err))
		}
		return DeployResult{Success: false}
	}
	if cb != nil && cb.OnStepDone != nil {
		cb.OnStepDone(DeployStepGenerateCompose, fmt.Sprintf("已写入 %s", composeFile))
	}

	// ── 5. 启动服务 ────────────────────────────────────────
	if cb != nil && cb.OnStepStart != nil {
		cb.OnStepStart(DeployStepStartServices, "启动 Zabbix 服务...")
	}
	if !composeUp(composeFile, ComposeProjectName) {
		if cb != nil && cb.OnStepError != nil {
			cb.OnStepError(DeployStepStartServices, "服务启动失败")
		}
		return DeployResult{Success: false}
	}
	if cb != nil && cb.OnStepDone != nil {
		cb.OnStepDone(DeployStepStartServices, "所有容器已启动")
	}

	// ── 6. 健康检查 ────────────────────────────────────────
	healthOk, healthResult := runHealthCheckStep(deployDir, cb)
	if !healthOk {
		return DeployResult{Success: false, HealthCheck: &healthResult}
	}

	// ── 7. 部署后初始化 ────────────────────────────────────
	postInitResult := runPostInitStep(config.Web.HTTPPort, cb)

	return DeployResult{
		Success:     true,
		HealthCheck: &healthResult,
		PostInit:    postInitResult,
	}
}

// ─── 辅助函数 ──────────────────────────────────────────────

// joinStrings joins a slice of strings with a separator.
func joinStrings(ss []string, sep string) string {
	return strings.Join(ss, sep)
}
