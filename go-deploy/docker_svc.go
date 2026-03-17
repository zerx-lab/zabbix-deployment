package main

import (
	"encoding/json"
	"fmt"
	"strconv"
	"strings"
)

// ─── Docker 可用性检查 ─────────────────────────────────────

// checkDocker 检查 Docker 守护进程是否可用
func checkDocker() bool {
	result := execCmd([]string{"docker", "info"})
	if result.ExitCode != 0 {
		logError("Docker 不可用，请确认 Docker 已安装并正在运行")
		return false
	}
	return true
}

// checkDockerCompose 检查 Docker Compose 是否可用
func checkDockerCompose() bool {
	result := execCmd([]string{"docker", "compose", "version"})
	if result.ExitCode != 0 {
		logError("Docker Compose 不可用")
		return false
	}
	return true
}

// ─── 镜像操作 ──────────────────────────────────────────────

// imageExists 检查本地是否已存在指定镜像
func imageExists(imageName string) bool {
	result := execCmd([]string{"docker", "image", "inspect", imageName})
	return result.ExitCode == 0
}

// loadImage 从 tar 文件加载 Docker 镜像
func loadImage(tarPath string) bool {
	result := execCmd([]string{"docker", "load", "-i", tarPath})
	if result.ExitCode != 0 {
		logError(fmt.Sprintf("加载镜像失败: %s", result.Stderr))
		return false
	}
	return true
}

// saveImage 将 Docker 镜像保存为 tar 文件
func saveImage(imageName, outputPath string) bool {
	result := execCmd([]string{"docker", "save", "-o", outputPath, imageName})
	if result.ExitCode != 0 {
		logError(fmt.Sprintf("保存镜像失败: %s", result.Stderr))
		return false
	}
	return true
}

// ─── Compose 状态查询 ──────────────────────────────────────

// composeJSONLine is used for parsing `docker compose ps --format json` output.
// Each line is a separate JSON object.
type composeJSONLine struct {
	Name   string `json:"Name"`
	State  string `json:"State"`
	Status string `json:"Status"`
	Health string `json:"Health"`
}

// getComposeStatus 获取 compose 项目中所有容器的状态
func getComposeStatus(composeFile, projectName string) []ContainerStatus {
	result := execCmd([]string{
		"docker", "compose",
		"-f", composeFile,
		"-p", projectName,
		"ps", "--format", "json",
	})

	if result.ExitCode != 0 {
		return nil
	}

	var containers []ContainerStatus
	for _, line := range strings.Split(result.Stdout, "\n") {
		line = strings.TrimSpace(line)
		if line == "" {
			continue
		}
		var obj composeJSONLine
		if err := json.Unmarshal([]byte(line), &obj); err != nil {
			continue
		}
		containers = append(containers, ContainerStatus{
			Name:   obj.Name,
			State:  obj.State,
			Status: obj.Status,
			Health: obj.Health,
		})
	}
	return containers
}

// ─── Compose 生命周期 ──────────────────────────────────────

// composeUp 以后台模式启动 compose 服务
func composeUp(composeFile, projectName string) bool {
	result := execCmd([]string{
		"docker", "compose",
		"-f", composeFile,
		"-p", projectName,
		"up", "-d",
		"--pull", "never",
		"--remove-orphans",
	})
	if result.ExitCode != 0 {
		logError(fmt.Sprintf("启动服务失败: %s", result.Stderr))
		return false
	}
	return true
}

// composeDown 停止并清理 compose 服务
func composeDown(composeFile, projectName string, opts ComposeDownOptions) bool {
	args := []string{
		"docker", "compose",
		"-f", composeFile,
		"-p", projectName,
		"down",
	}
	if opts.RemoveVolumes {
		args = append(args, "-v")
	}
	if opts.RemoveImages {
		args = append(args, "--rmi", "all")
	}
	args = append(args, "--remove-orphans")

	result := execCmd(args)
	if result.ExitCode != 0 {
		logError(fmt.Sprintf("停止服务失败: %s", result.Stderr))
		return false
	}
	return true
}

// ─── 数据卷操作 ────────────────────────────────────────────

// listProjectVolumes 列出 compose 项目关联的 Docker 数据卷
func listProjectVolumes(projectName string) []string {
	result := execCmd([]string{
		"docker", "volume", "ls",
		"--filter", fmt.Sprintf("label=com.docker.compose.project=%s", projectName),
		"--format", "{{.Name}}",
	})
	if result.ExitCode != 0 || result.Stdout == "" {
		return nil
	}
	var volumes []string
	for _, v := range strings.Split(result.Stdout, "\n") {
		v = strings.TrimSpace(v)
		if v != "" {
			volumes = append(volumes, v)
		}
	}
	return volumes
}

// removeVolumes 删除指定的 Docker 数据卷，返回成功删除的卷名列表
func removeVolumes(volumeNames []string) []string {
	if len(volumeNames) == 0 {
		return nil
	}
	var removed []string
	for _, name := range volumeNames {
		result := execCmd([]string{"docker", "volume", "rm", "-f", name})
		if result.ExitCode == 0 {
			removed = append(removed, name)
		}
	}
	return removed
}

// ─── 镜像列表 / 删除 ───────────────────────────────────────

// listProjectImages 获取已加载的项目相关镜像信息
func listProjectImages(imageNames []string) []ImageInfo {
	var images []ImageInfo
	for _, name := range imageNames {
		result := execCmd([]string{
			"docker", "image", "inspect", name,
			"--format", "{{.ID}}\t{{.Size}}",
		})
		if result.ExitCode == 0 && result.Stdout != "" {
			parts := strings.SplitN(result.Stdout, "\t", 2)
			id := ""
			size := ""
			if len(parts) >= 1 {
				fullID := parts[0]
				// 去掉 "sha256:" 前缀，取前 12 位短 ID
				fullID = strings.TrimPrefix(fullID, "sha256:")
				if len(fullID) > 12 {
					id = fullID[:12]
				} else {
					id = fullID
				}
			}
			if len(parts) >= 2 {
				bytes, err := strconv.ParseInt(strings.TrimSpace(parts[1]), 10, 64)
				if err == nil {
					size = formatBytes(bytes)
				}
			}
			images = append(images, ImageInfo{Name: name, ID: id, Size: size})
		}
	}
	return images
}

// removeImages 删除指定的 Docker 镜像，返回成功删除的镜像名列表
func removeImages(imageNames []string) []string {
	if len(imageNames) == 0 {
		return nil
	}
	var removed []string
	for _, name := range imageNames {
		result := execCmd([]string{"docker", "rmi", "-f", name})
		if result.ExitCode == 0 {
			removed = append(removed, name)
		}
	}
	return removed
}

// ─── 辅助：字节格式化 ──────────────────────────────────────

// formatBytes 将字节数格式化为可读字符串
func formatBytes(bytes int64) string {
	if bytes == 0 {
		return "0 B"
	}
	units := []string{"B", "KB", "MB", "GB"}
	val := float64(bytes)
	i := 0
	for val >= 1024 && i < len(units)-1 {
		val /= 1024
		i++
	}
	return fmt.Sprintf("%.1f %s", val, units[i])
}
