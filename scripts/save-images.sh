#!/usr/bin/env bash
# ============================================================
# Zabbix 离线镜像下载保存脚本
# 在有网络的机器上运行此脚本，下载所有必需的 Docker 镜像并保存为 tar 文件
# 然后将 packages/ 目录下的 tar 文件拷贝到离线机器
# ============================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PACKAGES_DIR="${SCRIPT_DIR}/../packages"

# Zabbix 7.0 LTS 所需镜像列表
IMAGES=(
  "postgres:16-alpine"
  "zabbix/zabbix-server-pgsql:alpine-7.0-latest"
  "zabbix/zabbix-web-nginx-pgsql:alpine-7.0-latest"
  "zabbix/zabbix-agent2:alpine-7.0-latest"
)

# 镜像名称转换为文件名（替换 / 和 : 为 -）
image_to_filename() {
  local image="$1"
  echo "${image//\//-}" | sed 's/:/-/g'
}

echo "========================================"
echo "  Zabbix 离线镜像下载工具"
echo "========================================"
echo ""
echo "目标目录: ${PACKAGES_DIR}"
echo "镜像数量: ${#IMAGES[@]}"
echo ""

# 确保目标目录存在
mkdir -p "${PACKAGES_DIR}"

# 检查 Docker 是否可用
if ! docker info > /dev/null 2>&1; then
  echo "错误: Docker 不可用，请确认 Docker 已安装并正在运行"
  exit 1
fi

echo "开始下载镜像..."
echo ""

FAILED=()

for image in "${IMAGES[@]}"; do
  filename="$(image_to_filename "${image}").tar"
  filepath="${PACKAGES_DIR}/${filename}"

  echo "--- ${image} ---"

  # 拉取镜像
  echo "  [1/2] 拉取镜像..."
  if ! docker pull "${image}"; then
    echo "  ✗ 拉取失败: ${image}"
    FAILED+=("${image}")
    echo ""
    continue
  fi

  # 保存为 tar
  echo "  [2/2] 保存为 ${filename}..."
  if ! docker save -o "${filepath}" "${image}"; then
    echo "  ✗ 保存失败: ${image}"
    FAILED+=("${image}")
    echo ""
    continue
  fi

  size=$(du -h "${filepath}" | cut -f1)
  echo "  ✓ 完成 (${size})"
  echo ""
done

echo "========================================"

if [ ${#FAILED[@]} -eq 0 ]; then
  echo "✓ 全部完成！共 ${#IMAGES[@]} 个镜像已保存到:"
  echo "  ${PACKAGES_DIR}"
  echo ""
  echo "请将以下文件拷贝到离线机器的 packages/ 目录:"
  for image in "${IMAGES[@]}"; do
    filename="$(image_to_filename "${image}").tar"
    echo "  - ${filename}"
  done
else
  echo "✗ 部分镜像下载失败 (${#FAILED[@]}/${#IMAGES[@]}):"
  for image in "${FAILED[@]}"; do
    echo "  - ${image}"
  done
  exit 1
fi

echo ""
echo "总大小:"
du -sh "${PACKAGES_DIR}" | cut -f1
