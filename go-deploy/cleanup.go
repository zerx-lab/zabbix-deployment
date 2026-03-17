package main

import (
	"fmt"
	"os"
	"path/filepath"
)

// ─── 资源探测 ─────────────────────────────────────────────

// getAllImageNames 返回所有项目相关的镜像名称（含可选的 SNMP Traps 镜像）
func getAllImageNames() []string {
	names := make([]string, 0, len(ZabbixImages)+1)
	names = append(names, ZabbixImages...)
	names = append(names, SnmpTrapsImage)
	return names
}

// getEnvironmentSnapshot 获取当前环境的资源快照，用于在清理前展示给用户
func getEnvironmentSnapshot(deployDir string) EnvironmentSnapshot {
	composeFile := filepath.Join(deployDir, ComposeFileName)
	composeExists := fileExists(composeFile)

	var containers []ContainerStatus
	if composeExists {
		containers = getComposeStatus(composeFile, ComposeProjectName)
	}

	volumes := listProjectVolumes(ComposeProjectName)
	images := listProjectImages(getAllImageNames())

	return EnvironmentSnapshot{
		Containers:        containers,
		Volumes:           volumes,
		Images:            images,
		ComposeFileExists: composeExists,
		DeployDirExists:   dirExists(deployDir),
		DeployDir:         deployDir,
	}
}

// formatImageLabel 将镜像名称格式化为友好名称
func formatImageLabel(imageName string) string {
	if label, ok := ImageLabels[imageName]; ok {
		return label
	}
	return imageName
}

// ─── 停止服务 ─────────────────────────────────────────────

// stopServices 仅停止服务（不删除卷和镜像）
func stopServices(deployDir string) CleanupStepResult {
	composeFile := filepath.Join(deployDir, ComposeFileName)

	if !fileExists(composeFile) {
		return CleanupStepResult{
			Step:    CleanupStepStopServices,
			Success: true,
			Message: "未找到 compose 文件，无需停止",
		}
	}

	ok := composeDown(composeFile, ComposeProjectName, ComposeDownOptions{})
	if ok {
		return CleanupStepResult{
			Step:    CleanupStepStopServices,
			Success: true,
			Message: "所有容器已停止并移除",
		}
	}
	return CleanupStepResult{
		Step:    CleanupStepStopServices,
		Success: false,
		Message: "停止服务失败",
	}
}

// ─── 完整清理 ─────────────────────────────────────────────

// stepStopContainers 停止容器子步骤
func stepStopContainers(deployDir string, opts CleanupOptions) CleanupStepResult {
	composeFile := filepath.Join(deployDir, ComposeFileName)

	if !fileExists(composeFile) {
		return CleanupStepResult{
			Step:    CleanupStepStopServices,
			Success: true,
			Message: "未找到 compose 文件，跳过",
		}
	}

	downOpts := ComposeDownOptions{
		RemoveVolumes: opts.RemoveVolumes,
		RemoveImages:  opts.RemoveImages,
	}
	ok := composeDown(composeFile, ComposeProjectName, downOpts)
	if ok {
		return CleanupStepResult{
			Step:    CleanupStepStopServices,
			Success: true,
			Message: "容器和网络已清理",
		}
	}
	return CleanupStepResult{
		Step:    CleanupStepStopServices,
		Success: false,
		Message: "停止服务失败",
	}
}

// stepRemoveVolumes 清理残留数据卷子步骤
func stepRemoveVolumes() CleanupStepResult {
	remaining := listProjectVolumes(ComposeProjectName)
	if len(remaining) == 0 {
		return CleanupStepResult{
			Step:    CleanupStepRemoveVolumes,
			Success: true,
			Message: "数据卷已全部清理",
		}
	}

	removed := removeVolumes(remaining)
	allDone := len(removed) == len(remaining)
	msg := fmt.Sprintf("已删除 %d 个数据卷", len(removed))
	if !allDone {
		msg = fmt.Sprintf("已删除 %d/%d 个数据卷", len(removed), len(remaining))
	}
	return CleanupStepResult{
		Step:    CleanupStepRemoveVolumes,
		Success: allDone,
		Message: msg,
		Details: removed,
	}
}

// stepRemoveImages 清理残留镜像子步骤
func stepRemoveImages() CleanupStepResult {
	existing := listProjectImages(getAllImageNames())
	if len(existing) == 0 {
		return CleanupStepResult{
			Step:    CleanupStepRemoveImages,
			Success: true,
			Message: "镜像已全部清理",
		}
	}

	imageNames := make([]string, 0, len(existing))
	for _, img := range existing {
		imageNames = append(imageNames, img.Name)
	}

	removed := removeImages(imageNames)
	allDone := len(removed) == len(existing)
	msg := fmt.Sprintf("已删除 %d 个镜像", len(removed))
	if !allDone {
		msg = fmt.Sprintf("已删除 %d/%d 个镜像", len(removed), len(existing))
	}

	details := make([]string, 0, len(removed))
	for _, name := range removed {
		details = append(details, formatImageLabel(name))
	}

	return CleanupStepResult{
		Step:    CleanupStepRemoveImages,
		Success: allDone,
		Message: msg,
		Details: details,
	}
}

// stepRemoveDeployDir 删除部署目录子步骤
func stepRemoveDeployDir(deployDir string) CleanupStepResult {
	if err := os.RemoveAll(deployDir); err != nil {
		return CleanupStepResult{
			Step:    CleanupStepRemoveDir,
			Success: false,
			Message: fmt.Sprintf("删除目录失败: %v", err),
		}
	}
	return CleanupStepResult{
		Step:    CleanupStepRemoveDir,
		Success: true,
		Message: fmt.Sprintf("已删除 %s", deployDir),
	}
}

// runCleanupStep executes a cleanup step and fires the callbacks.
func runCleanupStep(
	step CleanupStep,
	label string,
	fn func() CleanupStepResult,
	cb *CleanupCallbacks,
) CleanupStepResult {
	if cb != nil && cb.OnStepStart != nil {
		cb.OnStepStart(step, label)
	}
	result := fn()
	if cb != nil && cb.OnStepDone != nil {
		cb.OnStepDone(step, result)
	}
	return result
}

// cleanupAll 执行完整的环境清理流程
//
// 按顺序执行：停止容器 → 删除数据卷 → 删除镜像 → 删除部署目录
// 每一步都可通过 opts 开关控制是否执行。
func cleanupAll(deployDir string, opts CleanupOptions, cb *CleanupCallbacks) CleanupResult {
	var steps []CleanupStepResult

	// 1. 停止并移除容器（始终执行）
	stopResult := runCleanupStep(
		CleanupStepStopServices,
		"停止并移除容器...",
		func() CleanupStepResult { return stepStopContainers(deployDir, opts) },
		cb,
	)
	steps = append(steps, stopResult)

	if !stopResult.Success {
		return CleanupResult{Steps: steps, AllSuccess: false}
	}

	// 2. 清理残留数据卷
	if opts.RemoveVolumes {
		result := runCleanupStep(
			CleanupStepRemoveVolumes,
			"清理数据卷...",
			stepRemoveVolumes,
			cb,
		)
		steps = append(steps, result)
	}

	// 3. 清理残留镜像
	if opts.RemoveImages {
		result := runCleanupStep(
			CleanupStepRemoveImages,
			"清理 Docker 镜像...",
			stepRemoveImages,
			cb,
		)
		steps = append(steps, result)
	}

	// 4. 删除部署目录
	if opts.RemoveDeployDir {
		result := runCleanupStep(
			CleanupStepRemoveDir,
			fmt.Sprintf("删除部署目录: %s", deployDir),
			func() CleanupStepResult { return stepRemoveDeployDir(deployDir) },
			cb,
		)
		steps = append(steps, result)
	}

	allSuccess := true
	for _, s := range steps {
		if !s.Success {
			allSuccess = false
			break
		}
	}

	return CleanupResult{Steps: steps, AllSuccess: allSuccess}
}
