#!/usr/bin/env bash
# ==============================================================================
# fetch-monitor-templates.sh
# 从统一运维管理平台抓取所有监控模板及指标信息，保存到本地文件
#
# 用法: bash scripts/fetch-monitor-templates.sh
#
# 输出:
#   output/monitor-templates/
#   ├── templates_summary.json       # 所有模板基础信息列表
#   ├── templates_all_details.json   # 所有模板完整详情（含指标）
#   ├── templates_index.json         # 轻量索引（模板概览）
#   ├── metrics_flat.csv             # 指标扁平化 CSV（可用 Excel 打开）
#   ├── monitor_templates_report.md  # 可读 Markdown 报告
#   ├── details/                     # 每个模板单独的 JSON 文件
#   └── fetch.log                    # 运行日志
# ==============================================================================

set -euo pipefail

# ------------------------------------------------------------------------------
# 配置区域 - 按需修改
# ------------------------------------------------------------------------------
BASE_URL="http://172.32.13.2:30000"
USERNAME="admin"
PASSWORD='!Yunxing@2025'

OUTPUT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/output/monitor-templates"
LOG_FILE="${OUTPUT_DIR}/fetch.log"

# 每页获取数量（模板列表）
PAGE_SIZE=50

# 请求间隔（秒），避免请求过快
REQUEST_DELAY=0.3

# 从浏览器提取的有效 Cookie（若 Session 过期会自动尝试重新登录）
JSESSIONID="52FFB3600BA9C80B1AEF27A7CBD01EE1"
X_SUBJECT_TOKEN="Online.21232f297a57a5a743894a0e4a801fc3.411ab8450804faba3d828cb13324f84b.eyJhbGciOiJIUzUxMiJ9.eyJzdWIiOiJtQUtleUoxYzJWeVRtRnRaU0k2SW1Ga2JXbHVJaXdpYVdRaU9pSXhJaXdpY21WbmFXOXVTV1FpT2lJd0lpd2lhWEJCWkdSeVpYTnpJam9pTVRjeUxqTXlMamd1TVRBd0luMD04WjZWIiwianRpIjoiMTk3ODUxIiwiaWF0IjoxNzczOTc0Nzk5fQ.xmHHPC2go8qJNbZ4iKZPJZ4MXimqoqtN9cQp8lSnHIOf2kds0MYISkognm8tUuudik3RS88rD-8XEQHoiXlfbA"

# 全局变量：用于函数间传递结果路径（避免 $() 捕获 stderr/stdout 混污问题）
G_SUMMARY_FILE=""
G_ALL_DETAILS_FILE=""

# ------------------------------------------------------------------------------
# 日志函数 —— 全部输出到 stderr + 日志文件，不污染 stdout
# ------------------------------------------------------------------------------
log() {
  local level="$1"
  shift
  local msg="$*"
  local ts
  ts="$(date '+%Y-%m-%d %H:%M:%S')"
  local line="[${ts}] [${level}] ${msg}"
  # 同时写 stderr 和日志文件
  echo "${line}" >&2
  echo "${line}" >> "${LOG_FILE}"
}

info()  { log "INFO " "$@"; }
warn()  { log "WARN " "$@"; }
error() { log "ERROR" "$@"; }
die()   { error "$@"; exit 1; }

# ------------------------------------------------------------------------------
# 依赖检查
# ------------------------------------------------------------------------------
check_deps() {
  local missing=()
  for cmd in curl jq; do
    command -v "${cmd}" &>/dev/null || missing+=("${cmd}")
  done
  if [[ ${#missing[@]} -gt 0 ]]; then
    die "缺少依赖工具: ${missing[*]}，请先安装后再运行。"
  fi
}

# ------------------------------------------------------------------------------
# Cookie 管理
# ------------------------------------------------------------------------------
get_cookie_header() {
  echo "JSESSIONID=${JSESSIONID}; X-Subject-Token=${X_SUBJECT_TOKEN}; _language=zh; currentLanguage=zh"
}

# ------------------------------------------------------------------------------
# 通用 GET 请求，响应写入指定文件
# 用法: api_get <url> <output_file>
# ------------------------------------------------------------------------------
api_get() {
  local url="$1"
  local out_file="$2"
  local cookie_str
  cookie_str=$(get_cookie_header)

  curl -s \
    -H "Accept: application/json, text/plain, */*" \
    -H "Accept-Language: zh-CN,zh;q=0.9" \
    -H "User-Agent: Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36" \
    -H "Referer: ${BASE_URL}/monitortemplateui/view/monitor-template/template-list.html" \
    -H "Cookie: ${cookie_str}" \
    --connect-timeout 15 \
    --max-time 60 \
    "${url}" \
    -o "${out_file}"
}

# ------------------------------------------------------------------------------
# 尝试重新登录刷新 Cookie
# ------------------------------------------------------------------------------
try_login() {
  info "尝试重新登录获取新的会话 Cookie..."

  local cookie_file="${OUTPUT_DIR}/.cookies.txt"

  # 先访问首页触发 Session 初始化
  curl -s -o /dev/null \
    -c "${cookie_file}" \
    -H "User-Agent: Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36" \
    --connect-timeout 10 \
    --max-time 30 \
    "${BASE_URL}/central/index.html" 2>/dev/null || true

  # 提取初始 JSESSIONID
  local new_jsession
  new_jsession=$(grep -i "JSESSIONID" "${cookie_file}" 2>/dev/null | awk '{print $NF}' | head -1 || true)
  if [[ -n "${new_jsession}" ]]; then
    JSESSIONID="${new_jsession}"
    info "  获取到初始 JSESSIONID: ${JSESSIONID:0:16}..."
  fi

  # 尝试 JSON 方式登录
  local login_resp_file="${OUTPUT_DIR}/.login_resp.json"
  local login_cookie="JSESSIONID=${JSESSIONID}; _language=zh; currentLanguage=zh"

  curl -s \
    -c "${cookie_file}" \
    -b "${cookie_file}" \
    -X POST \
    -H "Content-Type: application/json;charset=UTF-8" \
    -H "User-Agent: Mozilla/5.0" \
    -H "Accept: application/json, text/plain, */*" \
    -H "Referer: ${BASE_URL}/central/index.html" \
    -H "Cookie: ${login_cookie}" \
    -d "{\"loginName\":\"${USERNAME}\",\"loginPassword\":\"${PASSWORD}\",\"verifyCode\":\"\"}" \
    --connect-timeout 10 \
    --max-time 30 \
    "${BASE_URL}/operator/login" \
    -o "${login_resp_file}" 2>/dev/null || true

  info "  登录响应: $(head -c 200 "${login_resp_file}" 2>/dev/null || echo '(空)')"

  # 从 Cookie 文件中提取新 Token
  local new_token
  new_token=$(grep -i "X-Subject-Token" "${cookie_file}" 2>/dev/null | awk '{print $NF}' | tail -1 || true)
  if [[ -n "${new_token}" && "${new_token}" != "${X_SUBJECT_TOKEN}" ]]; then
    X_SUBJECT_TOKEN="${new_token}"
    info "  Token 已更新: ${X_SUBJECT_TOKEN:0:20}..."
  fi

  rm -f "${login_resp_file}"
}

# ------------------------------------------------------------------------------
# 验证 Cookie 是否有效
# ------------------------------------------------------------------------------
verify_auth() {
  info "验证认证状态..."
  local test_file
  test_file=$(mktemp)

  api_get "${BASE_URL}/monitortemplaters/monitorTemplatesSummary?size=1&start=0&regionId=-1" "${test_file}"

  local total
  total=$(jq -r '.totalElements // empty' "${test_file}" 2>/dev/null || true)
  rm -f "${test_file}"

  if [[ -n "${total}" ]]; then
    info "  认证有效，平台共 ${total} 个模板。"
    return 0
  else
    warn "  认证验证失败。"
    return 1
  fi
}

# ------------------------------------------------------------------------------
# 获取所有模板汇总列表（分页）
# 结果文件路径存入全局变量 G_SUMMARY_FILE
# ------------------------------------------------------------------------------
fetch_all_templates() {
  G_SUMMARY_FILE="${OUTPUT_DIR}/templates_summary.json"
  local tmp_dir
  tmp_dir=$(mktemp -d)

  info "开始获取所有监控模板列表..."

  local page=0
  local total_pages=1
  local total_count=0
  local page_resp_file="${tmp_dir}/page_resp.json"

  while [[ ${page} -lt ${total_pages} ]]; do
    local start=$(( page * PAGE_SIZE ))
    local url="${BASE_URL}/monitortemplaters/monitorTemplatesSummary?size=${PAGE_SIZE}&start=${start}&regionId=-1"

    info "  获取模板列表第 $(( page + 1 )) 页 (start=${start}, size=${PAGE_SIZE})..."
    api_get "${url}" "${page_resp_file}"

    # 首次解析总页数
    if [[ ${page} -eq 0 ]]; then
      total_count=$(jq -r '.totalElements // 0' "${page_resp_file}")
      total_pages=$(jq -r '.totalPages // 1' "${page_resp_file}")
      info "  共 ${total_count} 个模板，${total_pages} 页。"

      # 检查响应是否有效
      if ! jq -e '.content' "${page_resp_file}" &>/dev/null 2>&1; then
        rm -rf "${tmp_dir}"
        die "响应格式异常，无法解析模板列表。请检查认证状态。内容: $(head -c 200 "${page_resp_file}")"
      fi
    fi

    local page_size_actual
    page_size_actual=$(jq '.content | length' "${page_resp_file}")
    info "  第 $(( page + 1 )) 页获取到 ${page_size_actual} 条。"

    # 将当前页 content 存为独立文件
    jq '.content' "${page_resp_file}" > "${tmp_dir}/page_${page}.json"

    page=$(( page + 1 ))
    if [[ ${page} -lt ${total_pages} ]]; then
      sleep "${REQUEST_DELAY}"
    fi
  done

  # 合并所有分页文件为一个 JSON 数组
  local merge_args=()
  for f in "${tmp_dir}"/page_*.json; do
    merge_args+=("${f}")
  done
  jq -n '[inputs[]]' "${merge_args[@]}" > "${G_SUMMARY_FILE}"

  local actual_count
  actual_count=$(jq 'length' "${G_SUMMARY_FILE}")
  info "模板汇总列表已保存: ${G_SUMMARY_FILE}（共 ${actual_count} 条）"

  rm -rf "${tmp_dir}"
}

# ------------------------------------------------------------------------------
# 获取单个模板的完整详情（含指标 unitList）
# 成功时将格式化 JSON 写入 out_file，返回 0；失败返回 1
# ------------------------------------------------------------------------------
fetch_template_detail() {
  local template_id="$1"
  local template_name="$2"
  local out_file="$3"

  local url="${BASE_URL}/monitortemplaters/monitorTemplate/${template_id}"
  local resp_file
  resp_file=$(mktemp)

  api_get "${url}" "${resp_file}"

  # 检查是否有平台级错误
  local has_error
  has_error=$(jq -r 'if has("Error-Code") then "yes" else "no" end' "${resp_file}" 2>/dev/null || echo "no")
  if [[ "${has_error}" == "yes" ]]; then
    local err_code err_msg
    err_code=$(jq -r '."Error-Code" // "unknown"' "${resp_file}")
    err_msg=$(jq -r '."Error-Message" // "unknown"' "${resp_file}")
    warn "  [${template_name}](${template_id}) 请求出错: ${err_code} - ${err_msg}"
    rm -f "${resp_file}"
    return 1
  fi

  # 检查是否包含 unitList 字段（基本完整性验证）
  local has_unit_list
  has_unit_list=$(jq -r 'if has("unitList") then "yes" else "no" end' "${resp_file}" 2>/dev/null || echo "no")
  if [[ "${has_unit_list}" == "no" ]]; then
    warn "  [${template_name}](${template_id}) 响应缺少 unitList: $(head -c 100 "${resp_file}")"
    rm -f "${resp_file}"
    return 1
  fi

  # 格式化后写入目标文件
  jq '.' "${resp_file}" > "${out_file}"
  rm -f "${resp_file}"
  return 0
}

# ------------------------------------------------------------------------------
# 批量获取所有模板详情（含指标），结果存入全局变量 G_ALL_DETAILS_FILE
# 同时在 details/ 目录存储每个模板的单独文件
# ------------------------------------------------------------------------------
fetch_all_template_details() {
  G_ALL_DETAILS_FILE="${OUTPUT_DIR}/templates_all_details.json"
  local details_dir="${OUTPUT_DIR}/details"
  local tmp_detail_dir
  tmp_detail_dir=$(mktemp -d)

  mkdir -p "${details_dir}"

  local total
  total=$(jq 'length' "${G_SUMMARY_FILE}")
  info "开始逐个获取 ${total} 个模板的详情（含指标）..."

  local idx=0
  local success=0
  local failed=0

  # 用有序文件列表跟踪成功的详情
  local order_file="${tmp_detail_dir}/success_order.txt"
  : > "${order_file}"

  while IFS= read -r template; do
    local template_id template_name template_type
    template_id=$(echo "${template}" | jq -r '.templateId')
    template_name=$(echo "${template}" | jq -r '.name // "unknown"')
    template_type=$(echo "${template}" | jq -r '.type // "unknown"')

    idx=$(( idx + 1 ))
    info "  [${idx}/${total}] ${template_name} (id=${template_id}, type=${template_type})"

    local detail_tmp="${tmp_detail_dir}/${idx}.json"

    if fetch_template_detail "${template_id}" "${template_name}" "${detail_tmp}"; then
      success=$(( success + 1 ))

      # 记录成功顺序（用于后续合并）
      echo "${detail_tmp}" >> "${order_file}"

      # 同时保存命名友好的单独文件
      local safe_name
      safe_name=$(echo "${template_name}" | tr '/' '_' | tr ' ' '_' | sed 's/[\\:*?<>|"'\''&]/_/g')
      local named_file="${details_dir}/${template_id}_${template_type}_${safe_name}.json"
      cp "${detail_tmp}" "${named_file}"
      info "    已保存: $(basename "${named_file}")"
    else
      failed=$(( failed + 1 ))
      warn "    跳过: ${template_name}（获取失败）"
    fi

    if [[ ${idx} -lt ${total} ]]; then
      sleep "${REQUEST_DELAY}"
    fi
  done < <(jq -c '.[]' "${G_SUMMARY_FILE}")

  info "模板详情获取完成: 成功=${success}, 失败=${failed}"

  # 把所有成功的详情文件合并为一个 JSON 数组
  if [[ ${success} -gt 0 ]]; then
    local merge_files=()
    while IFS= read -r f; do
      [[ -f "${f}" ]] && merge_files+=("${f}")
    done < "${order_file}"

    jq -n '[inputs]' "${merge_files[@]}" > "${G_ALL_DETAILS_FILE}"
    info "全量详情已保存: ${G_ALL_DETAILS_FILE}（${success} 条）"
  else
    echo "[]" > "${G_ALL_DETAILS_FILE}"
    warn "所有模板详情获取均失败，请检查认证或接口。"
  fi

  rm -rf "${tmp_detail_dir}"
}

# ------------------------------------------------------------------------------
# 生成模板轻量索引 JSON
# ------------------------------------------------------------------------------
generate_index_json() {
  local all_details_file="${G_ALL_DETAILS_FILE}"
  local index_file="${OUTPUT_DIR}/templates_index.json"

  info "生成模板轻量索引..."
  jq '[.[] | {
    templateId,
    name,
    nameEn,
    type,
    typeLabel,
    custom,
    describe,
    unitCount: (.unitList | length),
    fieldCount: ([.unitList[]?.fields[]?] | length),
    unitKeys: [.unitList[]?.unit],
    units: [.unitList[]? | {
      key: .unit,
      nameZh: .nameZh,
      nameEn: .nameEn,
      collectTime,
      dataType,
      fieldCount: (.fields | length),
      fields: [.fields[]? | {
        key: .field,
        nameZh,
        nameEn,
        fieldUnit,
        valueType: (if .valueType == 0 then "数值" elif .valueType == 1 then "字符串" else (.valueType | tostring) end),
        enableThreshold
      }]
    }]
  }]' "${all_details_file}" > "${index_file}"

  local count
  count=$(jq 'length' "${index_file}")
  info "模板索引已生成: ${index_file}（${count} 个模板）"
}

# ------------------------------------------------------------------------------
# 生成 Markdown 报告
# ------------------------------------------------------------------------------
generate_markdown_report() {
  local all_details_file="${G_ALL_DETAILS_FILE}"
  local report_file="${OUTPUT_DIR}/monitor_templates_report.md"

  info "正在生成 Markdown 报告..."

  local total
  total=$(jq 'length' "${all_details_file}")

  {
    echo "# 监控模板与指标汇总报告"
    echo ""
    echo "> **数据来源**: ${BASE_URL}"
    echo ">"
    echo "> **生成时间**: $(date '+%Y-%m-%d %H:%M:%S')"
    echo ">"
    echo "> **模板总数**: ${total}"
    echo ""
    echo "---"
    echo ""
    echo "## 类型统计"
    echo ""
    echo "| 类型（中文）| 类型（英文）| 类型 Key | 模板数 |"
    echo "|------------|------------|---------|-------|"
    jq -r '
      group_by(.type) |
      sort_by(.[0].typeLabel.zh) |
      .[] |
      "| " + (.[0].typeLabel.zh // .[0].type // "-") +
      " | " + (.[0].typeLabel.en // .[0].type // "-") +
      " | `" + (.[0].type // "") + "`" +
      " | " + (length | tostring) + " |"
    ' "${all_details_file}"
    echo ""
    echo "---"
    echo ""
    echo "## 模板详情"
    echo ""

    local idx=0
    while IFS= read -r template; do
      idx=$(( idx + 1 ))

      local name type_zh type_en type_key template_id is_custom describe
      name=$(echo "${template}" | jq -r '.name // ""')
      type_zh=$(echo "${template}" | jq -r '.typeLabel.zh // .type // ""')
      type_en=$(echo "${template}" | jq -r '.typeLabel.en // .type // ""')
      type_key=$(echo "${template}" | jq -r '.type // ""')
      template_id=$(echo "${template}" | jq -r '.templateId // ""')
      is_custom=$(echo "${template}" | jq -r 'if .custom then "是（用户自定义）" else "否（系统内置）" end')
      describe=$(echo "${template}" | jq -r '.describe // ""')

      echo "### ${idx}. ${name}"
      echo ""
      echo "| 属性 | 值 |"
      echo "|------|----|"
      echo "| 模板 ID | \`${template_id}\` |"
      echo "| 类型（中文）| ${type_zh} |"
      echo "| 类型（英文）| ${type_en} |"
      echo "| 类型 Key | \`${type_key}\` |"
      echo "| 自定义 | ${is_custom} |"
      if [[ -n "${describe}" && "${describe}" != "null" ]]; then
        echo "| 描述 | ${describe} |"
      fi
      echo ""

      local unit_count
      unit_count=$(echo "${template}" | jq '.unitList | length')

      if [[ "${unit_count}" -gt 0 ]]; then
        echo "#### 指标单元（共 ${unit_count} 个）"
        echo ""

        local unit_idx=0
        while IFS= read -r unit; do
          unit_idx=$(( unit_idx + 1 ))

          local u_zh u_en u_key u_ct u_dt u_scope
          u_zh=$(echo "${unit}" | jq -r '.nameZh // ""')
          u_en=$(echo "${unit}" | jq -r '.nameEn // ""')
          u_key=$(echo "${unit}" | jq -r '.unit // ""')
          u_ct=$(echo "${unit}" | jq -r '.collectTime // "-"')
          u_dt=$(echo "${unit}" | jq -r 'if (.dataType == "" or .dataType == null) then "-" else .dataType end')
          u_scope=$(echo "${unit}" | jq -r '.scope // "-"')

          echo "##### ${unit_idx}. ${u_zh}（${u_en}）"
          echo ""
          echo "| 属性 | 值 |"
          echo "|------|----|"
          echo "| 单元 Key | \`${u_key}\` |"
          echo "| 采集间隔 | ${u_ct} 秒 |"
          echo "| 数据类型 | ${u_dt} |"
          echo "| 采集范围 | ${u_scope} |"
          echo ""

          local field_count
          field_count=$(echo "${unit}" | jq '.fields | length')

          if [[ "${field_count}" -gt 0 ]]; then
            echo "| 字段 Key | 中文名 | 英文名 | 单位 | 值类型 | 支持告警 | 中文说明 |"
            echo "|----------|--------|--------|------|--------|---------|---------|"

            while IFS= read -r field; do
              local fk fzh fen fu fvt fth fexp
              fk=$(echo "${field}" | jq -r '.field // ""')
              fzh=$(echo "${field}" | jq -r '.nameZh // ""')
              fen=$(echo "${field}" | jq -r '.nameEn // ""')
              fu=$(echo "${field}" | jq -r '.fieldUnit // ""')
              fvt=$(echo "${field}" | jq -r 'if .valueType == 0 then "数值" elif .valueType == 1 then "字符串" else (.valueType | tostring) end')
              fth=$(echo "${field}" | jq -r 'if .enableThreshold then "✓" else "✗" end')
              fexp=$(echo "${field}" | jq -r '.explainZh // ""' | tr '\n' ' ' | sed 's/|/｜/g')
              echo "| \`${fk}\` | ${fzh} | ${fen} | ${fu} | ${fvt} | ${fth} | ${fexp} |"
            done < <(echo "${unit}" | jq -c '.fields[]?')

            echo ""
          else
            echo "> 该单元无字段数据。"
            echo ""
          fi
        done < <(echo "${template}" | jq -c '.unitList[]?')
      else
        echo "> 该模板无指标单元数据。"
        echo ""
      fi

      echo "---"
      echo ""
    done < <(jq -c '.[]' "${all_details_file}")

  } > "${report_file}"

  info "Markdown 报告已生成: ${report_file}"
}

# ------------------------------------------------------------------------------
# 生成扁平化 CSV（带 UTF-8 BOM，可直接用 Excel 打开中文）
# ------------------------------------------------------------------------------
generate_csv_metrics() {
  local all_details_file="${G_ALL_DETAILS_FILE}"
  local csv_file="${OUTPUT_DIR}/metrics_flat.csv"

  info "正在生成指标扁平化 CSV..."

  {
    # UTF-8 BOM，方便 Excel 直接打开中文
    printf '\xEF\xBB\xBF'
    echo "模板名称,模板类型(中),模板类型(英),模板类型Key,模板ID,是否自定义,单元Key,单元中文名,单元英文名,采集间隔(s),数据类型,采集范围,字段Key,字段中文名,字段英文名,字段单位,值类型,支持告警阈值,说明(中文)"

    while IFS= read -r template; do
      local tn tt_zh tt_en tt_key tid tcustom
      tn=$(echo "${template}" | jq -r '.name // ""')
      tt_zh=$(echo "${template}" | jq -r '.typeLabel.zh // .type // ""')
      tt_en=$(echo "${template}" | jq -r '.typeLabel.en // .type // ""')
      tt_key=$(echo "${template}" | jq -r '.type // ""')
      tid=$(echo "${template}" | jq -r '.templateId // ""')
      tcustom=$(echo "${template}" | jq -r 'if .custom then "是" else "否" end')

      while IFS= read -r unit; do
        local uk uzh uen uct udt uscope
        uk=$(echo "${unit}" | jq -r '.unit // ""')
        uzh=$(echo "${unit}" | jq -r '.nameZh // ""')
        uen=$(echo "${unit}" | jq -r '.nameEn // ""')
        uct=$(echo "${unit}" | jq -r '.collectTime // ""')
        udt=$(echo "${unit}" | jq -r '.dataType // ""')
        uscope=$(echo "${unit}" | jq -r '.scope // ""')

        while IFS= read -r field; do
          local fk fzh fen fu fvt fth fexp
          fk=$(echo "${field}" | jq -r '.field // ""')
          fzh=$(echo "${field}" | jq -r '.nameZh // ""')
          fen=$(echo "${field}" | jq -r '.nameEn // ""')
          fu=$(echo "${field}" | jq -r '.fieldUnit // ""')
          fvt=$(echo "${field}" | jq -r 'if .valueType == 0 then "数值" elif .valueType == 1 then "字符串" else (.valueType | tostring) end')
          fth=$(echo "${field}" | jq -r 'if .enableThreshold then "是" else "否" end')
          # CSV 转义：双引号替换为两个双引号，逗号替换为中文逗号，去除换行
          fexp=$(echo "${field}" | jq -r '.explainZh // ""' | tr '\n' ' ' | sed 's/"/""/g' | sed 's/,/，/g')

          printf '"%s","%s","%s","%s","%s","%s","%s","%s","%s","%s","%s","%s","%s","%s","%s","%s","%s","%s","%s"\n' \
            "${tn}" "${tt_zh}" "${tt_en}" "${tt_key}" "${tid}" "${tcustom}" \
            "${uk}" "${uzh}" "${uen}" "${uct}" "${udt}" "${uscope}" \
            "${fk}" "${fzh}" "${fen}" "${fu}" "${fvt}" "${fth}" "${fexp}"
        done < <(echo "${unit}" | jq -c '.fields[]?')
      done < <(echo "${template}" | jq -c '.unitList[]?')
    done < <(jq -c '.[]' "${all_details_file}")

  } > "${csv_file}"

  local row_count
  row_count=$(wc -l < "${csv_file}")
  info "指标 CSV 已生成: ${csv_file}（含表头共 ${row_count} 行）"
}

# ------------------------------------------------------------------------------
# 主流程
# ------------------------------------------------------------------------------
main() {
  echo "============================================================" >&2
  echo "  监控模板与指标数据抓取脚本" >&2
  echo "  目标: ${BASE_URL}" >&2
  echo "  输出: ${OUTPUT_DIR}" >&2
  echo "============================================================" >&2
  echo "" >&2

  check_deps

  mkdir -p "${OUTPUT_DIR}"
  : > "${LOG_FILE}"  # 清空/创建日志文件

  info "输出目录: ${OUTPUT_DIR}"

  # Step 1: 验证认证，失败则尝试重新登录
  if ! verify_auth; then
    warn "内置 Cookie 已过期，尝试重新登录..."
    try_login
    if ! verify_auth; then
      die "认证失败。请从浏览器重新提取 JSESSIONID 和 X_SUBJECT_TOKEN 后更新脚本顶部的配置。"
    fi
  fi

  # Step 2: 获取所有模板列表（分页），结果存入 G_SUMMARY_FILE
  fetch_all_templates

  local template_count
  template_count=$(jq 'length' "${G_SUMMARY_FILE}")
  if [[ "${template_count}" -eq 0 ]]; then
    die "未获取到任何模板，请检查认证状态或接口地址。"
  fi
  info "共获取到 ${template_count} 个模板基础信息。"

  # Step 3: 逐个获取模板详情（含指标 unitList），结果存入 G_ALL_DETAILS_FILE
  fetch_all_template_details

  local detail_count
  detail_count=$(jq 'length' "${G_ALL_DETAILS_FILE}")
  info "成功获取 ${detail_count} 个模板的完整详情。"

  # Step 4: 生成轻量索引
  generate_index_json

  # Step 5: 生成 Markdown 报告
  generate_markdown_report

  # Step 6: 生成指标扁平化 CSV
  generate_csv_metrics

  echo "" >&2
  echo "============================================================" >&2
  info "全部完成！输出文件一览:"
  ls -lh "${OUTPUT_DIR}/" >&2
  if [[ -d "${OUTPUT_DIR}/details" ]]; then
    local detail_file_count
    detail_file_count=$(ls "${OUTPUT_DIR}/details/" | wc -l)
    info "单模板详情文件目录: ${OUTPUT_DIR}/details/（共 ${detail_file_count} 个文件）"
  fi
  echo "============================================================" >&2
}

main "$@"
