package main

import (
	"path/filepath"
)

// getEnvironmentStatus 获取当前部署环境的完整状态
func getEnvironmentStatus(deployDir string) EnvironmentStatus {
	deployDirOk := dirExists(deployDir)
	composeFile := filepath.Join(deployDir, ComposeFileName)
	composeOk := fileExists(composeFile)

	images := checkAllImagesReady()

	var containers []ContainerStatus
	if composeOk {
		containers = getComposeStatus(composeFile, ComposeProjectName)
	}

	return EnvironmentStatus{
		DeployDirExists:   deployDirOk,
		ComposeFileExists: composeOk,
		Images:            images,
		Containers:        containers,
	}
}
