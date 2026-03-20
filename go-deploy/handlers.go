package main

import (
	"errors"
	"fmt"
	"os"
	"strings"

	"github.com/charmbracelet/huh"
)

// ─── 通用：带 autoConfirm 的确认对话框 ────────────────────

// doConfirm 执行确认操作：
// - autoConfirm=true 时直接返回 true
// - 否则使用交互式 confirm
func doConfirm(ctx CliContext, message string, initialValue bool) bool {
	if ctx.AutoConfirm {
		logInfo(fmt.Sprintf("%s %s (自动确认)", greenText("✓"), message))
		return true
	}
	result := initialValue
	form := huh.NewForm(
		huh.NewGroup(
			huh.NewConfirm().
				Title(message).
				Value(&result),
		),
	)
	err := form.Run()
	if err != nil {
		if errors.Is(err, huh.ErrUserAborted) {
			printCancel("操作已取消")
		}
		return false
	}
	return result
}

// ─── Install Docker ────────────────────────────────────────

// formatDockerStatus 格式化 Docker 状态文本
func formatDockerStatus(installed, running bool, version string) string {
	if !installed {
		return redText("未安装")
	}
	if running {
		return greenText(fmt.Sprintf("%s (运行中)", version))
	}
	return yellowText(fmt.Sprintf("%s (未运行)", version))
}

// showDockerCheckStatus 展示当前 Docker 环境状态
func showDockerCheckStatus(check DockerCheckResult) {
	logInfo(boldText("--- 当前环境 ---"))
	logInfo(fmt.Sprintf("  Docker:         %s", formatDockerStatus(check.DockerInstalled, check.DockerRunning, check.DockerVersion)))
	composeStatus := ""
	if check.ComposeInstalled {
		v := check.ComposeVersion
		if v == "" {
			v = "已安装"
		}
		composeStatus = greenText(v)
	} else {
		composeStatus = redText("未安装")
	}
	logInfo(fmt.Sprintf("  Docker Compose: %s", composeStatus))
	logInfo(fmt.Sprintf("  系统架构:       %s", check.Arch))
	logInfo(fmt.Sprintf("  Root 权限:      %s", formatBool(check.IsRoot, "是", "否")))
	logInfo("")
}

// showDockerPackageScan 展示离线安装包扫描结果
func showDockerPackageScan(scan DockerPackageScan) {
	logInfo(boldText("--- 离线安装包 ---"))
	if scan.HasDockerTgz {
		name := scan.DockerTgzName
		if name == "" {
			name = "已找到"
		}
		logInfo(fmt.Sprintf("  Docker 安装包:   %s", greenText(name)))
	} else {
		logInfo(fmt.Sprintf("  Docker 安装包:   %s", redText("未找到 (docker-*.tgz)")))
	}
	if scan.HasComposeBin {
		name := scan.ComposeBinName
		if name == "" {
			name = "已找到"
		}
		logInfo(fmt.Sprintf("  Compose 插件:    %s", greenText(name)))
	} else {
		logInfo(fmt.Sprintf("  Compose 插件:    %s", redText("未找到 (docker-compose-*)")))
	}
	logInfo("")
}

// buildInstallPlan 构建安装计划列表
func buildInstallPlan(check DockerCheckResult, scan DockerPackageScan) []string {
	var items []string
	if !check.DockerInstalled || !check.DockerRunning {
		items = append(items, "解压 Docker 二进制文件到 /usr/local/bin/")
		items = append(items, "创建 docker 用户组")
		items = append(items, "创建 systemd 服务（containerd + docker）")
		items = append(items, "启动 Docker 服务并设置开机自启")
	}
	if !check.ComposeInstalled && scan.HasComposeBin {
		items = append(items, "安装 Docker Compose 插件")
	}
	items = append(items, "验证安装结果")
	numbered := make([]string, len(items))
	for i, item := range items {
		numbered[i] = fmt.Sprintf("%d. %s", i+1, item)
	}
	return numbered
}

// showDockerGroupHint 提示用户如何让 docker 组权限立即生效
func showDockerGroupHint(needsRelogin bool) {
	if needsRelogin {
		sudoUser := os.Getenv("SUDO_USER")
		if sudoUser != "" {
			logWarn(fmt.Sprintf(
				"提示: 用户 %s 已加入 docker 组，需要刷新组权限后才能免 sudo 使用 docker 命令。\n"+
					"请在当前终端执行以下命令立即生效:\n\n%s\n\n或者重新登录当前用户。",
				sudoUser, cyanText("  newgrp docker"),
			))
		} else {
			logWarn("提示: 当前用户已加入 docker 组，需要重新登录后才能免 sudo 使用 docker 命令。")
		}
		return
	}
	// 非 root 用户未通过 sudo 运行时，提示手动加入 docker 组
	if os.Getuid() != 0 {
		currentUser := os.Getenv("USER")
		if currentUser == "" {
			currentUser = os.Getenv("LOGNAME")
		}
		if currentUser != "" && currentUser != "root" {
			logWarn(fmt.Sprintf(
				"提示: 当前用户不在 docker 组中，若需免 sudo 使用 docker，请执行:\n\n%s",
				cyanText(fmt.Sprintf("  sudo usermod -aG docker %s && newgrp docker", currentUser)),
			))
		}
	}
}

// showDockerInstallResult 展示 Docker 安装结果
func showDockerInstallResult(result DockerInstallResult) {
	logInfo("")
	if result.Success {
		logSuccess(greenText("Docker 安装完成！"))
		showDockerGroupHint(result.NeedsRelogin)
		for _, step := range result.Steps {
			if !step.Success && step.Step == StepInstallCompose {
				logWarn(fmt.Sprintf("Docker Compose 未安装: %s", step.Message))
			}
		}
	} else {
		logError(redText("Docker 安装失败，请检查上方错误信息"))
		for _, step := range result.Steps {
			if !step.Success {
				label := DockerInstallStepLabels[step.Step]
				logError(fmt.Sprintf("  %s: %s", label, step.Message))
			}
		}
	}
}

// handleInstallDocker 处理 Docker 离线安装流程
func handleInstallDocker(ctx CliContext) {
	packagesDir := getPackagesDir()

	// 1. 检查当前 Docker 状态
	s := newProgress()
	s.Start("检查 Docker 安装状态...")
	check := checkDockerInstallation()
	s.Stop("检查完成")

	showDockerCheckStatus(check)

	// 如果 Docker 和 Compose 都已安装且运行中
	if check.DockerInstalled && check.DockerRunning && check.ComposeInstalled {
		logSuccess("Docker 和 Docker Compose 已安装且正常运行，无需额外操作")
		if !doConfirm(ctx, "是否仍要重新安装/覆盖？", false) {
			return
		}
	}

	// 2. 检查离线安装包
	s.Start("扫描离线安装包...")
	scan := scanDockerPackages(packagesDir)
	s.Stop("扫描完成")

	if !scan.DirExists {
		logError(redText(
			"packages/docker/ 目录不存在。\n" +
				"请先在有网络的机器上运行:\n" +
				"  bash scripts/download-docker.sh\n" +
				"然后将 packages/docker/ 目录拷贝到离线机器。",
		))
		return
	}

	showDockerPackageScan(scan)

	if !scan.HasDockerTgz {
		logError("缺少 Docker 安装包，请先运行 scripts/download-docker.sh 下载")
		return
	}

	if !check.IsRoot && !(check.DockerInstalled && check.DockerRunning) {
		logError(redText(
			"安装 Docker 需要 root 权限。\n" +
				"请使用 sudo 运行本工具:\n" +
				"  sudo ./zabbix-deploy",
		))
		return
	}

	// 3. 展示安装计划并确认
	plan := buildInstallPlan(check, scan)
	logNote(strings.Join(plan, "\n"), "安装计划")

	if !doConfirm(ctx, "确认开始安装？", true) {
		return
	}

	// 4. 执行安装
	installProgress := newProgress()

	result := installDocker(packagesDir, InstallDockerOptions{
		SkipExisting:   true,
		AddUserToGroup: true,
	}, &DockerInstallCallbacks{
		OnStepStart: func(step DockerInstallStep, msg string) {
			installProgress.Start(msg)
		},
		OnStepDone: func(step DockerInstallStep, stepResult DockerInstallStepResult) {
			label := DockerInstallStepLabels[step]
			if stepResult.Skipped {
				installProgress.Stop(dimText(fmt.Sprintf("⊘ %s: %s", label, stepResult.Message)))
			} else {
				installProgress.Stop(greenText(fmt.Sprintf("✓ %s: %s", label, stepResult.Message)))
			}
		},
		OnStepError: func(step DockerInstallStep, errMsg string) {
			label := DockerInstallStepLabels[step]
			installProgress.Stop(redText(fmt.Sprintf("✗ %s: %s", label, errMsg)))
		},
	})

	// 5. 展示结果
	showDockerInstallResult(result)
}

// ─── Deploy ───────────────────────────────────────────────

// checkPackages 检查离线包状态，返回 false 表示用户取消或包缺失
func checkPackages(packagesDir string, ctx CliContext) bool {
	s := newProgress()
	s.Start("检查离线镜像包...")
	summary := getPackagesSummary(packagesDir)
	s.Stop("离线镜像包检查完成")

	if summary.Available == 0 {
		logWarn(yellowText(
			"packages/ 目录中没有找到任何离线镜像包。\n" +
				"请先在有网络的机器上运行 scripts/save-images.sh 下载镜像，\n" +
				"然后将 tar 文件拷贝到 packages/ 目录。",
		))
		logInfo("所需镜像文件:")
		for _, name := range summary.Missing {
			logInfo(fmt.Sprintf("  - %s", name))
		}
		return doConfirm(ctx, "是否仍然继续？（如果 Docker 中已有镜像可以跳过加载）", false)
	}

	if len(summary.Missing) > 0 {
		logWarn(yellowText(fmt.Sprintf(
			"找到 %d/%d 个镜像包，缺少 %d 个:",
			summary.Available, summary.Total, len(summary.Missing),
		)))
		for _, name := range summary.Missing {
			logWarn(fmt.Sprintf("  - %s", name))
		}
		return doConfirm(ctx, "部分镜像缺失，是否继续？", false)
	}

	logSuccess(fmt.Sprintf("所有 %d 个离线镜像包已就绪", summary.Total))
	return true
}

// confirmConfig 展示配置摘要并确认
func confirmConfig(config DeployConfig, options DeployOptions, ctx CliContext) bool {
	masked := strings.Repeat("*", len(config.Database.Password))
	configSummary := strings.Join([]string{
		fmt.Sprintf("部署目录:     %s", options.DeployDir),
		fmt.Sprintf("数据库密码:   %s", masked),
		fmt.Sprintf("Web 端口:     %d", config.Web.HTTPPort),
		fmt.Sprintf("Server 端口:  %d", config.Server.ListenPort),
		fmt.Sprintf("时区:         %s", config.Web.Timezone),
		fmt.Sprintf("缓存大小:     %s", config.Server.CacheSize),
		fmt.Sprintf("Poller 数量:  %d", config.Server.StartPollers),
	}, "\n")

	logNote(configSummary, "部署配置确认")
	return doConfirm(ctx, "确认以上配置并开始部署？", true)
}

// executeDeploy 执行部署并返回部署结果
func executeDeploy(config DeployConfig, options DeployOptions, packagesDir string) DeployResult {
	deployProgress := newProgress()

	return deployZabbix(config, DeployOptions{
		DeployDir:          options.DeployDir,
		PackagesDir:        packagesDir,
		SkipExistingImages: options.SkipExistingImages,
	}, &DeployCallbacks{
		OnStepStart: func(step DeployStep, msg string) {
			deployProgress.Start(msg)
		},
		OnStepDone: func(step DeployStep, msg string) {
			label := DeployStepMessages[step]
			deployProgress.Stop(greenText(fmt.Sprintf("✓ %s: %s", label, msg)))
		},
		OnStepError: func(step DeployStep, errMsg string) {
			label := DeployStepMessages[step]
			deployProgress.Stop(redText(fmt.Sprintf("✗ %s: %s", label, errMsg)))
		},
		OnImageProgress: func(result LoadResult, index int, total int) {
			if result.Skipped {
				logInfo(dimText(fmt.Sprintf("  [%d/%d] %s - 已存在，跳过", index+1, total, result.Label)))
			} else if result.Success {
				logSuccess(fmt.Sprintf("  [%d/%d] %s - 加载成功", index+1, total, result.Label))
			} else {
				logError(fmt.Sprintf("  [%d/%d] %s - %s", index+1, total, result.Label, result.Error))
			}
		},
		OnHealthTick: func(services []ServiceHealth, elapsed int64) {
			readyCount := 0
			for _, s := range services {
				if s.Healthy {
					readyCount++
				}
			}
			elapsedSec := elapsed / 1000
			deployProgress.Message(fmt.Sprintf("等待服务就绪... %d/%d (%ds)", readyCount, len(services), elapsedSec))
		},
	})
}

// showHealthResult 展示健康检查结果
func showHealthResult(result HealthCheckResult, config DeployConfig, options DeployOptions) {
	if result.AllHealthy {
		elapsedSec := result.Elapsed / 1000
		logNote(strings.Join([]string{
			fmt.Sprintf("Zabbix Web:    http://localhost:%d", config.Web.HTTPPort),
			"默认用户名:    Admin",
			"默认密码:      zabbix",
			"",
			fmt.Sprintf("启动耗时:      %d 秒", elapsedSec),
			fmt.Sprintf("部署目录:      %s", options.DeployDir),
		}, "\n"), "部署成功")
		return
	}
	if result.TimedOut {
		logWarn("服务可能仍在启动中，请稍后使用「检查状态」功能确认")
	} else {
		logError("请检查容器日志: docker compose -f <compose-file> logs")
	}
	for _, svc := range result.Services {
		icon := checkMark(svc.Healthy)
		logInfo(fmt.Sprintf("  %s %s: %s", icon, svc.Name, svc.State))
	}
}

// buildConfigFromArgs 从 CLI 参数构建部署配置
func buildConfigFromArgs(args DeployArgs) (*struct {
	Config  DeployConfig
	Options DeployOptions
}, bool) {
	if args.DBPassword == "" {
		logError("CLI 模式下 deploy 命令需要 --db-password 参数")
		logError("示例: ./zabbix-deploy deploy -y --db-password mypassword123")
		return nil, false
	}
	if len(args.DBPassword) < 8 {
		logError("数据库密码至少 8 位")
		return nil, false
	}

	cfg := DefaultDeployConfig()
	cfg.Database.Password = args.DBPassword
	cfg.Server.ListenPort = args.ServerPort
	cfg.Server.CacheSize = args.CacheSize
	cfg.Server.StartPollers = args.StartPollers
	cfg.Server.EnableSnmpTrapper = args.EnableSnmpTrapper
	cfg.Server.SnmpTrapperPort = args.SnmpTrapperPort
	cfg.Web.HTTPPort = args.WebPort
	cfg.Web.Timezone = args.Timezone

	options := DeployOptions{
		DeployDir:          args.DeployDir,
		SkipExistingImages: true,
	}

	return &struct {
		Config  DeployConfig
		Options DeployOptions
	}{Config: cfg, Options: options}, true
}

// handleDeploy 处理部署流程
func handleDeploy(ctx CliContext) {
	var collected *struct {
		Config  DeployConfig
		Options DeployOptions
	}

	// CLI 模式：从参数构建配置；TUI 模式：交互式收集
	// 与 TS 保持一致：autoConfirm=true 或任意 deploy 参数被显式传入时走 CLI 模式
	if ctx.AutoConfirm || ctx.HasDeployArgs {
		result, ok := buildConfigFromArgs(ctx.DeployArgs)
		if !ok {
			return
		}
		collected = result
	} else {
		result, err := collectDeployConfig()
		if err != nil {
			logError(fmt.Sprintf("收集配置失败: %v", err))
			return
		}
		if result == nil {
			return // user cancelled
		}
		collected = result
	}

	packagesDir := getPackagesDir()

	if !checkPackages(packagesDir, ctx) {
		return
	}
	if !confirmConfig(collected.Config, collected.Options, ctx) {
		return
	}

	result := executeDeploy(collected.Config, collected.Options, packagesDir)
	if !result.Success {
		logError(redText("部署失败，请检查上方错误信息"))
		return
	}

	if result.HealthCheck != nil {
		showHealthResult(*result.HealthCheck, collected.Config, collected.Options)
	}
}

// ─── Status ───────────────────────────────────────────────

// showImageStatus 展示镜像状态
func showImageStatus(status EnvironmentStatus) {
	logInfo(boldText("--- Docker 镜像 ---"))
	for _, image := range ZabbixImages {
		label := image
		if l, ok := ImageLabels[image]; ok {
			label = l
		}
		loaded := true
		for _, m := range status.Images.Missing {
			if m == image {
				loaded = false
				break
			}
		}
		icon := checkMark(loaded)
		logInfo(fmt.Sprintf("  %s %s", icon, label))
	}
	logInfo("")
}

// containerIcon 返回容器状态图标
func containerIcon(c ContainerStatus) string {
	if c.State == "running" {
		if c.Health == "healthy" || c.Health == "" {
			return greenText("✓")
		}
		return yellowText("⏳")
	}
	return redText("✗")
}

// showContainerStatus 展示容器状态
func showContainerStatus(containers []ContainerStatus) {
	logInfo(boldText("--- 容器状态 ---"))
	if len(containers) == 0 {
		logInfo("  没有运行中的容器")
	} else {
		for _, c := range containers {
			icon := containerIcon(c)
			healthTag := ""
			if c.Health != "" {
				healthTag = fmt.Sprintf(" [%s]", c.Health)
			}
			logInfo(fmt.Sprintf("  %s %s: %s%s", icon, c.Name, c.State, healthTag))
		}
	}
	logInfo("")
}

// handleStatus 处理状态查看
func handleStatus() {
	s := newProgress()
	s.Start("正在获取环境状态...")
	status := getEnvironmentStatus(DefaultDeployDir)
	s.Stop("状态获取完成")

	showImageStatus(status)
	showContainerStatus(status.Containers)

	logInfo(boldText("--- 部署信息 ---"))
	if status.DeployDirExists {
		logInfo(fmt.Sprintf("  部署目录: %s", greenText(DefaultDeployDir)))
	} else {
		logInfo(fmt.Sprintf("  部署目录: %s", redText("未创建")))
	}
	if status.ComposeFileExists {
		logInfo(fmt.Sprintf("  Compose 文件: %s", greenText("已生成")))
	} else {
		logInfo(fmt.Sprintf("  Compose 文件: %s", redText("未生成")))
	}
}

// ─── Stop ─────────────────────────────────────────────────

// showSnapshotContainers 展示快照中的容器列表
func showSnapshotContainers(containers []ContainerStatus) {
	logInfo(boldText("--- 容器 ---"))
	if len(containers) == 0 {
		logInfo("  没有运行中的容器")
		return
	}
	for _, c := range containers {
		icon := bulletIcon(c.State == "running")
		healthTag := ""
		if c.Health != "" {
			healthTag = fmt.Sprintf(" [%s]", c.Health)
		}
		logInfo(fmt.Sprintf("  %s %s: %s%s", icon, c.Name, c.State, healthTag))
	}
}

// showSnapshotVolumes 展示快照中的数据卷列表
func showSnapshotVolumes(volumes []string) {
	logInfo(boldText("--- 数据卷 ---"))
	if len(volumes) == 0 {
		logInfo("  没有关联的数据卷")
		return
	}
	for _, v := range volumes {
		logInfo(fmt.Sprintf("  - %s", v))
	}
}

// showSnapshotImages 展示快照中的镜像列表
func showSnapshotImages(images []ImageInfo) {
	logInfo(boldText("--- 镜像 ---"))
	if len(images) == 0 {
		logInfo("  没有已加载的镜像")
		return
	}
	for _, img := range images {
		label := formatImageLabel(img.Name)
		logInfo(fmt.Sprintf("  - %s (%s)", label, img.Size))
	}
}

// showSnapshot 展示环境资源快照
func showSnapshot(snapshot EnvironmentSnapshot) {
	showSnapshotContainers(snapshot.Containers)
	showSnapshotVolumes(snapshot.Volumes)
	showSnapshotImages(snapshot.Images)

	logInfo(boldText("--- 部署目录 ---"))
	dirStatus := dimText("不存在")
	if snapshot.DeployDirExists {
		dirStatus = greenText("存在")
	}
	fileStatus := dimText("不存在")
	if snapshot.ComposeFileExists {
		fileStatus = greenText("存在")
	}
	logInfo(fmt.Sprintf("  %s: %s", snapshot.DeployDir, dirStatus))
	logInfo(fmt.Sprintf("  compose 文件: %s", fileStatus))
	logInfo("")
}

// handleStop 处理停止服务（仅停止容器，保留数据和镜像）
func handleStop(ctx CliContext) {
	// 1. 先获取并展示当前状态
	s := newProgress()
	s.Start("正在获取服务状态...")
	snapshot := getEnvironmentSnapshot(DefaultDeployDir)
	s.Stop("状态获取完成")

	runningContainers := make([]ContainerStatus, 0)
	for _, c := range snapshot.Containers {
		if c.State == "running" {
			runningContainers = append(runningContainers, c)
		}
	}

	if len(runningContainers) == 0 && !snapshot.ComposeFileExists {
		logInfo("当前没有运行中的 Zabbix 服务")
		return
	}

	// 展示容器列表
	if len(runningContainers) > 0 {
		logInfo(boldText("当前运行中的容器:"))
		for _, c := range runningContainers {
			healthTag := ""
			if c.Health != "" {
				healthTag = fmt.Sprintf(" [%s]", c.Health)
			}
			logInfo(fmt.Sprintf("  %s %s%s", greenText("●"), c.Name, healthTag))
		}
		logInfo("")
	}

	// 2. 确认停止
	if !doConfirm(ctx, "确认停止所有 Zabbix 服务？（数据和镜像将保留，可随时重新启动）", true) {
		return
	}

	// 3. 执行停止
	s.Start("正在停止服务...")
	result := stopServices(DefaultDeployDir)
	if result.Success {
		s.Stop(greenText(fmt.Sprintf("✓ %s", result.Message)))
		logInfo(dimText("数据卷和镜像已保留，使用「部署 Zabbix」可重新启动服务"))
	} else {
		s.Stop(redText(fmt.Sprintf("✗ %s", result.Message)))
		logError("请手动检查: docker compose -f /opt/zabbix/docker-compose.yml down")
	}
}

// ─── Uninstall ────────────────────────────────────────────

// handleUninstall 处理彻底清理环境：删除所有容器、数据卷、镜像和部署目录
func handleUninstall(ctx CliContext) {
	// 1. 扫描环境资源
	s := newProgress()
	s.Start("正在扫描环境资源...")
	snapshot := getEnvironmentSnapshot(DefaultDeployDir)
	s.Stop("扫描完成")

	hasResource := len(snapshot.Containers) > 0 ||
		len(snapshot.Volumes) > 0 ||
		len(snapshot.Images) > 0 ||
		snapshot.ComposeFileExists ||
		snapshot.DeployDirExists

	if !hasResource {
		logInfo("环境已是干净状态，无需清理")
		return
	}

	// 2. 展示将要清理的资源
	showSnapshot(snapshot)

	logNote(strings.Join([]string{
		"1. 停止并移除所有容器和网络",
		yellowText("2. 删除所有数据卷（数据库数据将丢失！）"),
		"3. 删除所有 Docker 镜像",
		fmt.Sprintf("4. 删除部署目录 %s", DefaultDeployDir),
	}, "\n"), "即将执行的操作")

	// 3. 确认（破坏性操作）
	if !doConfirm(ctx, redText("此操作不可逆，将删除所有 Zabbix 相关资源，确认继续？"), false) {
		return
	}

	// 4. 执行全量清理
	cleanupProgress := newProgress()
	opts := CleanupOptions{
		RemoveVolumes:   true,
		RemoveImages:    true,
		RemoveDeployDir: true,
	}

	result := cleanupAll(DefaultDeployDir, opts, &CleanupCallbacks{
		OnStepStart: func(step CleanupStep, msg string) {
			cleanupProgress.Start(msg)
		},
		OnStepDone: func(step CleanupStep, stepResult CleanupStepResult) {
			label := CleanupStepLabels[step]
			if stepResult.Success {
				cleanupProgress.Stop(greenText(fmt.Sprintf("✓ %s: %s", label, stepResult.Message)))
				for _, detail := range stepResult.Details {
					logInfo(dimText(fmt.Sprintf("    %s", detail)))
				}
			} else {
				cleanupProgress.Stop(redText(fmt.Sprintf("✗ %s: %s", label, stepResult.Message)))
			}
		},
	})

	// 5. 结果
	logInfo("")
	if result.AllSuccess {
		logSuccess(greenText("环境已完全卸载"))
	} else {
		logWarn("部分清理步骤未完成，请手动检查残留资源")
		for _, st := range result.Steps {
			if !st.Success {
				label := CleanupStepLabels[st.Step]
				logError(fmt.Sprintf("  %s: %s", label, st.Message))
			}
		}
	}
}

// ─── TUI 主菜单 ────────────────────────────────────────────

// runCli 启动交互式 TUI 主菜单
func runCli() {
	var action string
	form := huh.NewForm(
		huh.NewGroup(
			huh.NewSelect[string]().
				Title("请选择操作:").
				Options(
					huh.NewOption("安装 Docker     从离线包安装 Docker 和 Docker Compose", string(ActionInstallDocker)),
					huh.NewOption("部署 Zabbix     全新安装或更新", string(ActionDeploy)),
					huh.NewOption("检查状态        查看服务运行状态与镜像", string(ActionStatus)),
					huh.NewOption("停止服务        停止所有容器，保留数据和镜像", string(ActionStop)),
					huh.NewOption("彻底清理        停止服务并删除所有数据、镜像、部署文件", string(ActionUninstall)),
					huh.NewOption("导入监控模板    将内嵌模板导入到 Zabbix", string(ActionImportTemplates)),
					huh.NewOption("列出内嵌模板    显示二进制中内嵌的所有监控模板", string(ActionListTemplates)),
					huh.NewOption("退出", string(ActionQuit)),
				).
				Value(&action),
		),
	)

	err := form.Run()
	if err != nil {
		if errors.Is(err, huh.ErrUserAborted) {
			printCancel("操作已取消")
			os.Exit(0)
		}
		logError(fmt.Sprintf("TUI 错误: %v", err))
		os.Exit(1)
	}

	if Action(action) == ActionQuit {
		return
	}

	runAction(Action(action), CliContext{AutoConfirm: false})
}

// ─── Action 派发 ───────────────────────────────────────────

// runAction 直接执行指定操作（CLI 模式）
func runAction(action Action, ctx CliContext) {
	switch action {
	case ActionInstallDocker:
		handleInstallDocker(ctx)
	case ActionDeploy:
		handleDeploy(ctx)
	case ActionStatus:
		handleStatus()
	case ActionStop:
		handleStop(ctx)
	case ActionUninstall:
		handleUninstall(ctx)
	case ActionImportTemplates:
		handleImportTemplates(ctx)
	case ActionListTemplates:
		handleListTemplates()
	case ActionQuit:
		// nothing
	}
}

// ─── 模板导入 ──────────────────────────────────────────────

// handleListTemplates 列出二进制中内嵌的所有监控模板
func handleListTemplates() {
	PrintEmbeddedTemplateList()
}

// handleImportTemplates 将内嵌的 Zabbix 监控模板导入到目标 Zabbix 实例
func handleImportTemplates(ctx CliContext) {
	itArgs := ctx.ImportTemplatesArgs

	// 构建导入选项
	opts := ImportTemplatesOptions{
		APIURL:   itArgs.APIURL,
		WebPort:  itArgs.WebPort,
		Username: itArgs.Username,
		Password: itArgs.Password,
		Force:    itArgs.Force,
	}

	// 补全默认值
	if opts.WebPort == 0 {
		opts.WebPort = 8080
	}
	if opts.Username == "" {
		opts.Username = defaultZabbixUsername
	}
	if opts.Password == "" {
		opts.Password = defaultZabbixPassword
	}

	// 在 TUI 模式下交互式收集 API 地址和凭据
	if !ctx.AutoConfirm && opts.APIURL == "" {
		collected, err := collectImportTemplatesConfig(opts)
		if err != nil {
			logError(fmt.Sprintf("收集配置失败: %v", err))
			return
		}
		if collected == nil {
			printCancel("操作已取消")
			return
		}
		opts = *collected
	}

	// 打印目标信息
	apiDisplay := opts.APIURL
	if apiDisplay == "" {
		apiDisplay = fmt.Sprintf("http://localhost:%d/api_jsonrpc.php（自动构建）", opts.WebPort)
	}
	logInfo(fmt.Sprintf("目标 Zabbix API : %s", apiDisplay))
	logInfo(fmt.Sprintf("登录用户        : %s", opts.Username))
	if opts.Force {
		logInfo("导入模式        : 强制覆盖（--force）")
	} else {
		logInfo("导入模式        : 跳过已存在（使用 --force 强制覆盖）")
	}
	fmt.Println()

	progress := newProgress()
	progress.Start("正在连接 Zabbix API...")

	cb := &ImportTemplatesCallbacks{
		OnStart: func(total int) {
			progress.Message(fmt.Sprintf("准备导入 %d 个模板...", total))
		},
		OnTemplateDone: func(r TemplateImportResult, index int, total int) {
			switch {
			case r.Skipped:
				progress.Message(fmt.Sprintf("[%d/%d] ⏭  %s（已存在）", index, total, r.Name))
			case r.Success:
				progress.Message(fmt.Sprintf("[%d/%d] ✓ %s", index, total, r.Name))
			default:
				progress.Message(fmt.Sprintf("[%d/%d] ✗ %s", index, total, r.Name))
			}
		},
		OnDone: func(_ ImportTemplatesResult) {},
	}

	result := ImportEmbeddedTemplates(opts, cb)

	if result.Total == 0 {
		progress.Stop(yellowText("⚠  未找到任何内嵌模板"))
		return
	}

	// 汇总行
	switch {
	case result.Failed == 0 && result.Skipped == 0:
		progress.Stop(greenText(fmt.Sprintf("✓  全部 %d 个模板导入成功", result.Succeeded)))
	case result.Failed == 0:
		progress.Stop(greenText(fmt.Sprintf(
			"✓  导入完成：%d 成功，%d 跳过（已存在）",
			result.Succeeded, result.Skipped)))
	default:
		progress.Stop(yellowText(fmt.Sprintf(
			"⚠  导入完成：%d 成功，%d 跳过，%d 失败（共 %d 个）",
			result.Succeeded, result.Skipped, result.Failed, result.Total)))
	}

	// 逐条详情
	fmt.Println()
	for _, r := range result.Results {
		switch {
		case r.Skipped:
			nameHint := r.Name
			if r.TemplateName != "" {
				nameHint = fmt.Sprintf("%s  [%s]", r.Name, r.TemplateName)
			}
			logWarn(fmt.Sprintf("  ⏭  %s", nameHint))
		case r.Success:
			logSuccess(fmt.Sprintf("  ✓ %s", r.Name))
		default:
			logError(fmt.Sprintf("  ✗ %s", r.Name))
			if r.Error != "" {
				logError(fmt.Sprintf("      %s", r.Error))
			}
		}
	}

	fmt.Println()
	if result.Failed > 0 {
		logError(redText(fmt.Sprintf("导入失败 %d 个，请检查上方错误信息", result.Failed)))
	}
	if result.Skipped > 0 && !opts.Force {
		logWarn(fmt.Sprintf("已跳过 %d 个已存在模板，如需覆盖请使用 --force 参数重新导入", result.Skipped))
	}
	if result.Failed == 0 && result.Skipped == 0 {
		logSuccess(greenText("所有模板已成功导入！"))
	}
}

// collectImportTemplatesConfig 在 TUI 模式下交互式收集导入配置
func collectImportTemplatesConfig(defaults ImportTemplatesOptions) (*ImportTemplatesOptions, error) {
	apiURL := defaults.APIURL
	username := defaults.Username
	password := defaults.Password

	defaultAPIURL := fmt.Sprintf("http://localhost:%d/api_jsonrpc.php", defaults.WebPort)
	if apiURL == "" {
		apiURL = defaultAPIURL
	}

	form := huh.NewForm(
		huh.NewGroup(
			huh.NewInput().
				Title("Zabbix API 地址").
				Description("例如: http://192.168.1.10:8080/api_jsonrpc.php").
				Placeholder(defaultAPIURL).
				Value(&apiURL),
			huh.NewInput().
				Title("登录用户名").
				Placeholder(defaultZabbixUsername).
				Value(&username),
			huh.NewInput().
				Title("登录密码").
				EchoMode(huh.EchoModePassword).
				Placeholder("（留空使用默认值 zabbix）").
				Value(&password),
		),
	)

	if err := form.Run(); err != nil {
		if errors.Is(err, huh.ErrUserAborted) {
			return nil, nil
		}
		return nil, err
	}

	if apiURL == "" {
		apiURL = defaultAPIURL
	}
	if username == "" {
		username = defaultZabbixUsername
	}
	if password == "" {
		password = defaultZabbixPassword
	}

	return &ImportTemplatesOptions{
		APIURL:   apiURL,
		WebPort:  defaults.WebPort,
		Username: username,
		Password: password,
		Force:    defaults.Force,
	}, nil
}
