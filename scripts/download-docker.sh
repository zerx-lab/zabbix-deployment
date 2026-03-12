#!/usr/bin/env bash
# ============================================================
# Docker & Docker Compose 离线安装包下载脚本
#
# 在有网络的机器上运行此脚本，下载 Docker 静态二进制文件和
# Docker Compose 插件，然后将 packages/docker/ 目录拷贝到离线机器。
#
# 用法:
#   bash scripts/download-docker.sh [--arch x86_64|aarch64]
#
# 支持架构: x86_64 (amd64), aarch64 (arm64)
# ============================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DOCKER_PKG_DIR="${SCRIPT_DIR}/../packages/docker"

# Docker 版本（静态二进制）
DOCKER_VERSION="27.5.1"
# Docker Compose 版本
COMPOSE_VERSION="v2.35.1"

# ─── 架构检测 ──────────────────────────────────────────────

detect_arch() {
  local arch
  arch="$(uname -m)"
  case "${arch}" in
    x86_64|amd64)   echo "x86_64" ;;
    aarch64|arm64)   echo "aarch64" ;;
    *)
      echo "错误: 不支持的架构 '${arch}'，仅支持 x86_64 和 aarch64" >&2
      exit 1
      ;;
  esac
}

# 解析命令行参数
ARCH=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --arch)
      ARCH="$2"
      shift 2
      ;;
    -h|--help)
      echo "用法: $0 [--arch x86_64|aarch64]"
      echo ""
      echo "选项:"
      echo "  --arch    指定目标架构（默认自动检测）"
      echo "            可选值: x86_64, aarch64"
      exit 0
      ;;
    *)
      echo "未知参数: $1" >&2
      exit 1
      ;;
  esac
done

if [ -z "${ARCH}" ]; then
  ARCH="$(detect_arch)"
fi

# 验证架构参数
case "${ARCH}" in
  x86_64|aarch64) ;;
  *)
    echo "错误: 不支持的架构 '${ARCH}'，仅支持 x86_64 和 aarch64" >&2
    exit 1
    ;;
esac

# Docker Compose 的架构名称映射
compose_arch() {
  case "${ARCH}" in
    x86_64)  echo "x86_64" ;;
    aarch64) echo "aarch64" ;;
  esac
}

COMPOSE_ARCH="$(compose_arch)"

# ─── 下载 URL ─────────────────────────────────────────────

DOCKER_URL="https://download.docker.com/linux/static/stable/${ARCH}/docker-${DOCKER_VERSION}.tgz"
COMPOSE_URL="https://github.com/docker/compose/releases/download/${COMPOSE_VERSION}/docker-compose-linux-${COMPOSE_ARCH}"

# ─── 输出信息 ─────────────────────────────────────────────

echo "========================================"
echo "  Docker 离线安装包下载工具"
echo "========================================"
echo ""
echo "目标架构:          ${ARCH}"
echo "Docker 版本:       ${DOCKER_VERSION}"
echo "Docker Compose:    ${COMPOSE_VERSION}"
echo "保存目录:          ${DOCKER_PKG_DIR}"
echo ""

# ─── 前置检查 ─────────────────────────────────────────────

# 检查下载工具
DOWNLOADER=""
if command -v curl &> /dev/null; then
  DOWNLOADER="curl"
elif command -v wget &> /dev/null; then
  DOWNLOADER="wget"
else
  echo "错误: 需要 curl 或 wget，请先安装其中之一"
  exit 1
fi

echo "使用下载工具: ${DOWNLOADER}"
echo ""

# 创建目标目录
mkdir -p "${DOCKER_PKG_DIR}"

# ─── 下载函数 ─────────────────────────────────────────────

download_file() {
  local url="$1"
  local output="$2"
  local desc="$3"

  echo "--- ${desc} ---"
  echo "  URL: ${url}"
  echo "  保存: ${output}"

  if [ -f "${output}" ]; then
    echo "  文件已存在，跳过下载"
    echo ""
    return 0
  fi

  echo "  下载中..."

  if [ "${DOWNLOADER}" = "curl" ]; then
    if ! curl -fSL --progress-bar -o "${output}" "${url}"; then
      echo "  ✗ 下载失败"
      rm -f "${output}"
      return 1
    fi
  else
    if ! wget --show-progress -q -O "${output}" "${url}"; then
      echo "  ✗ 下载失败"
      rm -f "${output}"
      return 1
    fi
  fi

  local size
  size=$(du -h "${output}" | cut -f1)
  echo "  ✓ 完成 (${size})"
  echo ""
  return 0
}

# ─── 执行下载 ─────────────────────────────────────────────

FAILED=()

echo "开始下载..."
echo ""

# 1. Docker 静态二进制包
DOCKER_TGZ="${DOCKER_PKG_DIR}/docker-${DOCKER_VERSION}-${ARCH}.tgz"
if ! download_file "${DOCKER_URL}" "${DOCKER_TGZ}" "Docker ${DOCKER_VERSION} (${ARCH})"; then
  FAILED+=("Docker ${DOCKER_VERSION}")
fi

# 2. Docker Compose 插件
COMPOSE_BIN="${DOCKER_PKG_DIR}/docker-compose-${COMPOSE_VERSION}-linux-${COMPOSE_ARCH}"
if ! download_file "${COMPOSE_URL}" "${COMPOSE_BIN}" "Docker Compose ${COMPOSE_VERSION} (${COMPOSE_ARCH})"; then
  FAILED+=("Docker Compose ${COMPOSE_VERSION}")
else
  # 确保可执行权限
  chmod +x "${COMPOSE_BIN}"
fi

# ─── 生成版本信息文件 ─────────────────────────────────────

VERSION_FILE="${DOCKER_PKG_DIR}/VERSION"
cat > "${VERSION_FILE}" << EOF
# Docker 离线安装包版本信息
# 由 download-docker.sh 自动生成

DOCKER_VERSION=${DOCKER_VERSION}
COMPOSE_VERSION=${COMPOSE_VERSION}
ARCH=${ARCH}
DOWNLOAD_DATE=$(date '+%Y-%m-%d %H:%M:%S')
EOF

# ─── 结果输出 ─────────────────────────────────────────────

echo "========================================"

if [ ${#FAILED[@]} -eq 0 ]; then
  echo "✓ 全部下载完成！"
  echo ""
  echo "已下载的文件:"
  ls -lh "${DOCKER_PKG_DIR}/" | grep -v "^total" | grep -v "^d" | awk '{print "  " $NF " (" $5 ")"}'
  echo ""
  echo "请将 packages/docker/ 目录整体拷贝到离线机器，"
  echo "然后运行 TUI 工具选择「安装 Docker」完成安装。"
  echo ""
  echo "手动安装方式:"
  echo "  # 解压 Docker 二进制文件"
  echo "  tar xzf packages/docker/docker-${DOCKER_VERSION}-${ARCH}.tgz -C /usr/local/bin/ --strip-components=1"
  echo "  # 复制 Docker Compose 插件"
  echo "  mkdir -p /usr/local/lib/docker/cli-plugins"
  echo "  cp packages/docker/docker-compose-${COMPOSE_VERSION}-linux-${COMPOSE_ARCH} /usr/local/lib/docker/cli-plugins/docker-compose"
else
  echo "✗ 部分下载失败 (${#FAILED[@]}):"
  for item in "${FAILED[@]}"; do
    echo "  - ${item}"
  done
  exit 1
fi

echo ""
echo "总大小:"
du -sh "${DOCKER_PKG_DIR}" | cut -f1
