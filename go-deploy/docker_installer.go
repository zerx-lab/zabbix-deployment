package main

import (
	"fmt"
	"os"
	"path/filepath"
	"strings"
	"time"
)

// ─── systemd 服务文件模板 ─────────────────────────────────

const dockerServiceContent = `[Unit]
Description=Docker Application Container Engine
Documentation=https://docs.docker.com
After=network-online.target containerd.service
Wants=network-online.target
Requires=containerd.service

[Service]
Type=notify
ExecStart=/usr/local/bin/dockerd --host=unix:///var/run/docker.sock
ExecReload=/bin/kill -s HUP $MAINPID
TimeoutStartSec=0
RestartSec=2
Restart=always
LimitNOFILE=infinity
LimitNPROC=infinity
LimitCORE=infinity
TasksMax=infinity
Delegate=yes
KillMode=process
OOMScoreAdjust=-500

[Install]
WantedBy=multi-user.target
`

const containerdServiceContent = `[Unit]
Description=containerd container runtime
Documentation=https://containerd.io
After=network.target

[Service]
ExecStart=/usr/local/bin/containerd
ExecStartPre=-/sbin/modprobe overlay
Type=notify
Delegate=yes
KillMode=process
Restart=always
RestartSec=5
LimitNPROC=infinity
LimitCORE=infinity
LimitNOFILE=infinity
TasksMax=infinity
OOMScoreAdjust=-999

[Install]
WantedBy=multi-user.target
`

// ─── 检查函数 ─────────────────────────────────────────────

// checkDockerInstallation 检查当前 Docker 和 Docker Compose 安装状态
func checkDockerInstallation() DockerCheckResult {
	isRoot := os.Getuid() == 0
	arch := getSystemArch()

	// 检查 Docker CLI
	dockerResult := execCmd([]string{"docker", "version", "--format", "{{.Client.Version}}"})
	dockerInstalled := dockerResult.ExitCode == 0 && strings.TrimSpace(dockerResult.Stdout) != ""
	dockerVersion := ""
	if dockerInstalled {
		dockerVersion = strings.TrimSpace(dockerResult.Stdout)
	}

	// 检查 Docker 守护进程
	dockerInfoResult := execCmd([]string{"docker", "info"})
	dockerRunning := dockerInfoResult.ExitCode == 0

	// 检查 Docker Compose
	composeResult := execCmd([]string{"docker", "compose", "version", "--short"})
	composeInstalled := composeResult.ExitCode == 0 && strings.TrimSpace(composeResult.Stdout) != ""
	composeVersion := ""
	if composeInstalled {
		composeVersion = strings.TrimSpace(composeResult.Stdout)
	}

	return DockerCheckResult{
		DockerInstalled:  dockerInstalled,
		DockerRunning:    dockerRunning,
		DockerVersion:    dockerVersion,
		ComposeInstalled: composeInstalled,
		ComposeVersion:   composeVersion,
		IsRoot:           isRoot,
		Arch:             arch,
	}
}

// getSystemArch 获取系统架构
func getSystemArch() string {
	result := execCmd([]string{"uname", "-m"})
	return strings.TrimSpace(result.Stdout)
}

// scanDockerPackages 扫描离线安装包目录
func scanDockerPackages(packagesBaseDir string) DockerPackageScan {
	dockerDir := filepath.Join(packagesBaseDir, DockerPackagesDir)

	if !dirExists(dockerDir) {
		return DockerPackageScan{DirExists: false}
	}

	// 使用 ls 列出目录内容
	lsResult := execCmd([]string{"ls", "-1", dockerDir})

	var dockerTgzPath, dockerTgzName string
	var composeBinPath, composeBinName string

	if lsResult.ExitCode == 0 {
		for _, file := range strings.Split(lsResult.Stdout, "\n") {
			file = strings.TrimSpace(file)
			if file == "" {
				continue
			}
			if strings.HasPrefix(file, "docker-") && strings.HasSuffix(file, ".tgz") {
				dockerTgzPath = filepath.Join(dockerDir, file)
				dockerTgzName = file
			}
			if strings.HasPrefix(file, "docker-compose-") {
				composeBinPath = filepath.Join(dockerDir, file)
				composeBinName = file
			}
		}
	}

	return DockerPackageScan{
		HasDockerTgz:   dockerTgzPath != "",
		DockerTgzPath:  dockerTgzPath,
		DockerTgzName:  dockerTgzName,
		HasComposeBin:  composeBinPath != "",
		ComposeBinPath: composeBinPath,
		ComposeBinName: composeBinName,
		DirExists:      true,
	}
}

// ─── 主安装入口 ───────────────────────────────────────────

// InstallDockerOptions controls the behaviour of installDocker.
type InstallDockerOptions struct {
	SkipExisting   bool
	AddUserToGroup bool
}

// installDocker 执行 Docker 离线安装的完整流程
//
// 步骤：
//  1. check-existing  — 检查现有安装
//  2. extract-binaries — 解压 Docker 静态二进制到 /usr/local/bin/
//  3. create-group    — 创建 docker 用户组并将当前用户加入
//  4. create-service  — 创建 systemd 服务文件
//  5. start-docker    — 启动并设置开机自启
//  6. install-compose — 安装 Docker Compose 插件
//  7. verify          — 验证安装结果
func installDocker(packagesBaseDir string, opts InstallDockerOptions, cb *DockerInstallCallbacks) DockerInstallResult {
	skipExisting := opts.SkipExisting
	addUserToGroup := opts.AddUserToGroup

	// ── 1. 检查现有安装 ────────────────────────────────────
	callStart(cb, StepCheckExisting, "检查现有 Docker 安装...")
	check := checkDockerInstallation()

	// 快速路径：Docker 已安装运行中
	if check.DockerInstalled && check.DockerRunning && skipExisting {
		return handleExistingDocker(check, packagesBaseDir, cb)
	}

	// 预检查
	preOk, scan, preResult := preInstallCheck(check, packagesBaseDir, cb)
	if !preOk {
		return preResult
	}

	var steps []DockerInstallStepResult
	needsRelogin := false

	var checkMsg string
	if check.DockerInstalled {
		checkMsg = fmt.Sprintf("检测到 Docker %s（未运行），将重新配置", check.DockerVersion)
	} else {
		checkMsg = "未检测到 Docker，准备全新安装"
	}
	checkStepResult := DockerInstallStepResult{
		Step:    StepCheckExisting,
		Success: true,
		Message: checkMsg,
	}
	steps = append(steps, checkStepResult)
	callDone(cb, StepCheckExisting, checkStepResult)

	// ── 2. 解压 Docker 二进制文件 ──────────────────────────
	callStart(cb, StepExtractBinaries, "解压 Docker 二进制文件...")
	extractResult := extractDockerBinaries(scan.DockerTgzPath)
	steps = append(steps, extractResult)
	if !extractResult.Success {
		callError(cb, StepExtractBinaries, extractResult.Message)
		return DockerInstallResult{Success: false, Steps: steps, NeedsRelogin: needsRelogin}
	}
	callDone(cb, StepExtractBinaries, extractResult)

	// ── 3. 创建 docker 用户组 ──────────────────────────────
	callStart(cb, StepCreateGroup, "配置 docker 用户组...")
	groupResult := createDockerGroup(addUserToGroup)
	steps = append(steps, groupResult)
	if strings.Contains(groupResult.Message, "需要重新登录") {
		needsRelogin = true
	}
	callDone(cb, StepCreateGroup, groupResult)

	// ── 4. 创建 systemd 服务文件 ──────────────────────────
	callStart(cb, StepCreateService, "创建 systemd 服务...")
	serviceResult := createSystemdServices()
	steps = append(steps, serviceResult)
	if !serviceResult.Success {
		callError(cb, StepCreateService, serviceResult.Message)
		return DockerInstallResult{Success: false, Steps: steps, NeedsRelogin: needsRelogin}
	}
	callDone(cb, StepCreateService, serviceResult)

	// ── 5. 启动 Docker 服务 ────────────────────────────────
	callStart(cb, StepStartDocker, "启动 Docker 服务...")
	startResult := startDockerService()
	steps = append(steps, startResult)
	if !startResult.Success {
		callError(cb, StepStartDocker, startResult.Message)
		return DockerInstallResult{Success: false, Steps: steps, NeedsRelogin: needsRelogin}
	}
	callDone(cb, StepStartDocker, startResult)

	// ── 6. 安装 Docker Compose ─────────────────────────────
	composeResult := installComposePlugin(packagesBaseDir, cb)
	steps = append(steps, composeResult)

	// ── 7. 验证安装 ────────────────────────────────────────
	verifyResult := verifyDockerInstallation(cb)
	steps = append(steps, verifyResult)

	// 只要非 install-compose 步骤全部成功即视为整体成功
	allCritical := true
	for _, s := range steps {
		if s.Step != StepInstallCompose && !s.Success {
			allCritical = false
			break
		}
	}

	return DockerInstallResult{Success: allCritical, Steps: steps, NeedsRelogin: needsRelogin}
}

// ─── 快速路径：Docker 已安装运行中 ───────────────────────

func handleExistingDocker(check DockerCheckResult, packagesBaseDir string, cb *DockerInstallCallbacks) DockerInstallResult {
	var steps []DockerInstallStepResult

	skipResult := DockerInstallStepResult{
		Step:    StepCheckExisting,
		Success: true,
		Message: fmt.Sprintf("Docker %s 已安装且正在运行", check.DockerVersion),
		Skipped: true,
	}
	steps = append(steps, skipResult)
	callDone(cb, StepCheckExisting, skipResult)

	if !check.ComposeInstalled {
		composeResult := installComposePlugin(packagesBaseDir, cb)
		steps = append(steps, composeResult)
		if !composeResult.Success {
			return DockerInstallResult{Success: false, Steps: steps, NeedsRelogin: false}
		}
		verifyResult := verifyDockerInstallation(cb)
		steps = append(steps, verifyResult)
	} else {
		composeSkip := DockerInstallStepResult{
			Step:    StepInstallCompose,
			Success: true,
			Message: fmt.Sprintf("Docker Compose %s 已安装", check.ComposeVersion),
			Skipped: true,
		}
		steps = append(steps, composeSkip)
		callDone(cb, StepInstallCompose, composeSkip)
	}

	return DockerInstallResult{Success: true, Steps: steps, NeedsRelogin: false}
}

// ─── 预检查 ───────────────────────────────────────────────

// preInstallCheck verifies root privileges and that the offline packages exist.
// Returns (ok, scan, emptyResult) — when ok==false the caller should return emptyResult.
func preInstallCheck(check DockerCheckResult, packagesBaseDir string, cb *DockerInstallCallbacks) (bool, DockerPackageScan, DockerInstallResult) {
	empty := DockerInstallResult{}

	if !check.IsRoot {
		r := DockerInstallStepResult{
			Step:    StepCheckExisting,
			Success: false,
			Message: "安装 Docker 需要 root 权限，请使用 sudo 运行",
		}
		callError(cb, StepCheckExisting, r.Message)
		empty.Steps = []DockerInstallStepResult{r}
		return false, DockerPackageScan{}, empty
	}

	scan := scanDockerPackages(packagesBaseDir)
	if !scan.DirExists {
		r := DockerInstallStepResult{
			Step:    StepCheckExisting,
			Success: false,
			Message: fmt.Sprintf("离线安装包目录不存在: %s", filepath.Join(packagesBaseDir, DockerPackagesDir)),
		}
		callError(cb, StepCheckExisting, r.Message)
		empty.Steps = []DockerInstallStepResult{r}
		return false, DockerPackageScan{}, empty
	}

	if !scan.HasDockerTgz {
		r := DockerInstallStepResult{
			Step:    StepCheckExisting,
			Success: false,
			Message: "未找到 Docker 离线安装包 (docker-*.tgz)，请先运行 scripts/download-docker.sh",
		}
		callError(cb, StepCheckExisting, r.Message)
		empty.Steps = []DockerInstallStepResult{r}
		return false, DockerPackageScan{}, empty
	}

	return true, scan, empty
}

// ─── 步骤实现 ─────────────────────────────────────────────

// extractDockerBinaries 解压 Docker 静态二进制到 /usr/local/bin/
func extractDockerBinaries(tgzPath string) DockerInstallStepResult {
	result := execCmd([]string{
		"tar", "xzf", tgzPath,
		"-C", DockerBinDir,
		"--strip-components=1",
	})
	if result.ExitCode != 0 {
		return DockerInstallStepResult{
			Step:    StepExtractBinaries,
			Success: false,
			Message: fmt.Sprintf("解压失败: %s", result.Stderr),
		}
	}
	return DockerInstallStepResult{
		Step:    StepExtractBinaries,
		Success: true,
		Message: fmt.Sprintf("已安装到 %s", DockerBinDir),
	}
}

// createDockerGroup 创建 docker 用户组并将当前用户加入
func createDockerGroup(addUser bool) DockerInstallStepResult {
	// 创建 docker 组（如果不存在）
	groupResult := execCmd([]string{"groupadd", "-f", "docker"})
	if groupResult.ExitCode != 0 {
		return DockerInstallStepResult{
			Step:    StepCreateGroup,
			Success: false,
			Message: fmt.Sprintf("创建 docker 组失败: %s", groupResult.Stderr),
		}
	}

	if !addUser {
		return DockerInstallStepResult{
			Step:    StepCreateGroup,
			Success: true,
			Message: "docker 用户组已创建",
		}
	}

	// 获取 SUDO_USER（如果通过 sudo 运行）
	sudoUser := os.Getenv("SUDO_USER")
	if sudoUser != "" {
		usermodResult := execCmd([]string{"usermod", "-aG", "docker", sudoUser})
		if usermodResult.ExitCode != 0 {
			return DockerInstallStepResult{
				Step:    StepCreateGroup,
				Success: true,
				Message: fmt.Sprintf("docker 组已创建，但将用户 %s 加入组失败: %s", sudoUser, usermodResult.Stderr),
			}
		}
		return DockerInstallStepResult{
			Step:    StepCreateGroup,
			Success: true,
			Message: fmt.Sprintf("用户 %s 已加入 docker 组（需要重新登录生效）", sudoUser),
		}
	}

	return DockerInstallStepResult{
		Step:    StepCreateGroup,
		Success: true,
		Message: "docker 用户组已创建",
	}
}

// createSystemdServices 创建 containerd 和 docker 的 systemd 服务文件
func createSystemdServices() DockerInstallStepResult {
	if err := os.WriteFile(ContainerdServicePath, []byte(containerdServiceContent), 0644); err != nil {
		return DockerInstallStepResult{
			Step:    StepCreateService,
			Success: false,
			Message: fmt.Sprintf("写入 containerd 服务文件失败: %v", err),
		}
	}

	if err := os.WriteFile(DockerServicePath, []byte(dockerServiceContent), 0644); err != nil {
		return DockerInstallStepResult{
			Step:    StepCreateService,
			Success: false,
			Message: fmt.Sprintf("写入 docker 服务文件失败: %v", err),
		}
	}

	reloadResult := execCmd([]string{"systemctl", "daemon-reload"})
	if reloadResult.ExitCode != 0 {
		return DockerInstallStepResult{
			Step:    StepCreateService,
			Success: false,
			Message: fmt.Sprintf("systemctl daemon-reload 失败: %s", reloadResult.Stderr),
		}
	}

	return DockerInstallStepResult{
		Step:    StepCreateService,
		Success: true,
		Message: "containerd 和 docker 服务已创建",
	}
}

// startDockerService 启动 Docker 服务并设置开机自启
func startDockerService() DockerInstallStepResult {
	// 先启动 containerd
	containerdStart := execCmd([]string{"systemctl", "start", "containerd"})
	if containerdStart.ExitCode != 0 {
		return DockerInstallStepResult{
			Step:    StepStartDocker,
			Success: false,
			Message: fmt.Sprintf("启动 containerd 失败: %s", containerdStart.Stderr),
		}
	}
	execCmd([]string{"systemctl", "enable", "containerd"})

	// 启动 docker
	dockerStart := execCmd([]string{"systemctl", "start", "docker"})
	if dockerStart.ExitCode != 0 {
		return DockerInstallStepResult{
			Step:    StepStartDocker,
			Success: false,
			Message: fmt.Sprintf("启动 Docker 失败: %s", dockerStart.Stderr),
		}
	}
	execCmd([]string{"systemctl", "enable", "docker"})

	// 等待 Docker socket 就绪（最多 15 秒）
	maxWait := 15
	for i := 0; i < maxWait; i++ {
		if fileExists(DockerSocketPath) {
			infoResult := execCmd([]string{"docker", "info"})
			if infoResult.ExitCode == 0 {
				return DockerInstallStepResult{
					Step:    StepStartDocker,
					Success: true,
					Message: "Docker 服务已启动并设置开机自启",
				}
			}
		}
		time.Sleep(1 * time.Second)
	}

	return DockerInstallStepResult{
		Step:    StepStartDocker,
		Success: false,
		Message: "Docker 服务已启动但守护进程未就绪，请检查 journalctl -u docker",
	}
}

// installComposePlugin 安装 Docker Compose 插件
func installComposePlugin(packagesBaseDir string, cb *DockerInstallCallbacks) DockerInstallStepResult {
	callStart(cb, StepInstallCompose, "安装 Docker Compose 插件...")

	scan := scanDockerPackages(packagesBaseDir)
	if !scan.HasComposeBin {
		r := DockerInstallStepResult{
			Step:    StepInstallCompose,
			Success: false,
			Message: "未找到 Docker Compose 离线包，跳过安装。可稍后手动安装",
		}
		callDone(cb, StepInstallCompose, r)
		return r
	}

	// 创建插件目录
	if err := os.MkdirAll(DockerCLIPluginsDir, 0755); err != nil {
		r := DockerInstallStepResult{
			Step:    StepInstallCompose,
			Success: false,
			Message: fmt.Sprintf("创建插件目录失败: %v", err),
		}
		callError(cb, StepInstallCompose, r.Message)
		return r
	}

	// 复制二进制文件
	destPath := filepath.Join(DockerCLIPluginsDir, "docker-compose")
	cpResult := execCmd([]string{"cp", scan.ComposeBinPath, destPath})
	if cpResult.ExitCode != 0 {
		r := DockerInstallStepResult{
			Step:    StepInstallCompose,
			Success: false,
			Message: fmt.Sprintf("复制 Docker Compose 失败: %s", cpResult.Stderr),
		}
		callError(cb, StepInstallCompose, r.Message)
		return r
	}

	// 设置可执行权限
	chmodResult := execCmd([]string{"chmod", "+x", destPath})
	if chmodResult.ExitCode != 0 {
		r := DockerInstallStepResult{
			Step:    StepInstallCompose,
			Success: false,
			Message: fmt.Sprintf("设置权限失败: %s", chmodResult.Stderr),
		}
		callError(cb, StepInstallCompose, r.Message)
		return r
	}

	r := DockerInstallStepResult{
		Step:    StepInstallCompose,
		Success: true,
		Message: fmt.Sprintf("已安装到 %s", destPath),
	}
	callDone(cb, StepInstallCompose, r)
	return r
}

// verifyDockerInstallation 验证 Docker 和 Docker Compose 安装
func verifyDockerInstallation(cb *DockerInstallCallbacks) DockerInstallStepResult {
	callStart(cb, StepVerify, "验证安装...")

	check := checkDockerInstallation()

	var details []string
	if check.DockerInstalled {
		details = append(details, fmt.Sprintf("Docker: %s", check.DockerVersion))
	} else {
		details = append(details, "Docker: 未检测到")
	}
	if check.DockerRunning {
		details = append(details, "Docker 守护进程: 运行中")
	} else {
		details = append(details, "Docker 守护进程: 未运行")
	}
	if check.ComposeInstalled {
		details = append(details, fmt.Sprintf("Docker Compose: %s", check.ComposeVersion))
	} else {
		details = append(details, "Docker Compose: 未安装")
	}

	success := check.DockerInstalled && check.DockerRunning
	composeStr := check.ComposeVersion
	if composeStr == "" {
		composeStr = "未安装"
	}

	var msg string
	if success {
		msg = fmt.Sprintf("Docker %s + Compose %s 验证通过", check.DockerVersion, composeStr)
	} else {
		msg = fmt.Sprintf("验证失败: %s", strings.Join(details, ", "))
	}

	r := DockerInstallStepResult{
		Step:    StepVerify,
		Success: success,
		Message: msg,
	}
	callDone(cb, StepVerify, r)
	return r
}

// ─── 回调辅助函数 ─────────────────────────────────────────

func callStart(cb *DockerInstallCallbacks, step DockerInstallStep, msg string) {
	if cb != nil && cb.OnStepStart != nil {
		cb.OnStepStart(step, msg)
	}
}

func callDone(cb *DockerInstallCallbacks, step DockerInstallStep, r DockerInstallStepResult) {
	if cb != nil && cb.OnStepDone != nil {
		cb.OnStepDone(step, r)
	}
}

func callError(cb *DockerInstallCallbacks, step DockerInstallStep, errMsg string) {
	if cb != nil && cb.OnStepError != nil {
		cb.OnStepError(step, errMsg)
	}
}
