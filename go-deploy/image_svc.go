package main

import (
	"fmt"
	"path/filepath"
)

// ─── 镜像扫描 ──────────────────────────────────────────────

// scanImageStatus 扫描所有必需镜像的状态
func scanImageStatus(packagesDir string, extraImages []string) []ImageStatus {
	allImages := append([]string{}, ZabbixImages...)
	allImages = append(allImages, extraImages...)

	var results []ImageStatus
	for _, image := range allImages {
		tarName := ImageToTarName(image)
		tarPath := filepath.Join(packagesDir, tarName)
		tarExists := fileExists(tarPath)
		loaded := imageExists(image)

		label := image
		if l, ok := ImageLabels[image]; ok {
			label = l
		}

		results = append(results, ImageStatus{
			Image:     image,
			Label:     label,
			TarName:   tarName,
			TarExists: tarExists,
			Loaded:    loaded,
		})
	}
	return results
}

// ─── 批量加载镜像 ──────────────────────────────────────────

// loadAllImages 批量加载离线镜像
func loadAllImages(
	packagesDir string,
	skipExisting bool,
	onProgress func(result LoadResult, index int, total int),
	extraImages []string,
) []LoadResult {
	statuses := scanImageStatus(packagesDir, extraImages)
	var results []LoadResult

	for i, entry := range statuses {
		tarPath := filepath.Join(packagesDir, entry.TarName)

		// 已加载且配置跳过
		if entry.Loaded && skipExisting {
			r := LoadResult{
				Image:   entry.Image,
				Label:   entry.Label,
				Success: true,
				Skipped: true,
			}
			results = append(results, r)
			if onProgress != nil {
				onProgress(r, i, len(statuses))
			}
			continue
		}

		// tar 文件不存在
		if !entry.TarExists {
			r := LoadResult{
				Image:   entry.Image,
				Label:   entry.Label,
				Success: false,
				Skipped: false,
				Error:   fmt.Sprintf("离线包不存在: %s", entry.TarName),
			}
			results = append(results, r)
			if onProgress != nil {
				onProgress(r, i, len(statuses))
			}
			continue
		}

		// 加载镜像
		ok := loadImage(tarPath)
		r := LoadResult{
			Image:   entry.Image,
			Label:   entry.Label,
			Success: ok,
			Skipped: false,
		}
		if !ok {
			r.Error = fmt.Sprintf("加载失败: %s", entry.TarName)
		}
		results = append(results, r)
		if onProgress != nil {
			onProgress(r, i, len(statuses))
		}
	}

	return results
}

// ─── 检查所有镜像是否就绪 ──────────────────────────────────

// checkAllImagesReady 检查所有必需镜像是否已加载到 Docker
func checkAllImagesReady() ImageReadiness {
	var missing []string
	for _, image := range ZabbixImages {
		if !imageExists(image) {
			missing = append(missing, image)
		}
	}
	return ImageReadiness{
		Ready:   len(missing) == 0,
		Missing: missing,
	}
}

// ─── packages 目录摘要 ─────────────────────────────────────

type PackagesSummary struct {
	Total     int
	Available int
	Missing   []string
}

// getPackagesSummary 获取 packages 目录下可用的 tar 文件数量摘要
func getPackagesSummary(packagesDir string) PackagesSummary {
	var missing []string
	available := 0

	for _, image := range ZabbixImages {
		tarName := ImageToTarName(image)
		tarPath := filepath.Join(packagesDir, tarName)
		if fileExists(tarPath) {
			available++
		} else {
			missing = append(missing, tarName)
		}
	}

	return PackagesSummary{
		Total:     len(ZabbixImages),
		Available: available,
		Missing:   missing,
	}
}
