#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
TARGET_DIR="${1:-${REPO_ROOT}}"

if [[ ! -d "${TARGET_DIR}" ]]; then
  echo "目录不存在: ${TARGET_DIR}" >&2
  exit 1
fi

CODE_GLOBS=(
  "*.py"
  "*.js"
  "*.cjs"
  "*.mjs"
  "*.ts"
  "*.tsx"
  "*.jsx"
  "*.sh"
  "*.bash"
  "*.zsh"
  "*.java"
  "*.kt"
  "*.swift"
  "*.go"
  "*.rs"
  "*.rb"
  "*.php"
  "*.scala"
  "*.sql"
  "*.html"
  "*.css"
  "*.scss"
  "*.less"
  "*.vue"
  "*.toml"
  "*.yaml"
  "*.yml"
)

collect_files_with_rg() {
  (
    cd "${TARGET_DIR}"
    local args=()
    local glob
    for glob in "${CODE_GLOBS[@]}"; do
      args+=(-g "${glob}")
    done
    rg --files "${args[@]}"
  )
}

collect_files_with_find() {
  local expr=()
  local glob
  for glob in "${CODE_GLOBS[@]}"; do
    expr+=(-name "${glob}" -o)
  done
  unset 'expr[${#expr[@]}-1]'

  find "${TARGET_DIR}" \
    \( -path "*/.git/*" -o -path "*/node_modules/*" -o -path "*/dist/*" -o -path "*/build/*" -o -path "*/.venv/*" -o -path "*/venv/*" \) -prune -o \
    -type f \( "${expr[@]}" \) -print | sed "s#^${TARGET_DIR}/##"
}

FILES=()
if command -v rg >/dev/null 2>&1; then
  while IFS= read -r line; do
    FILES+=("${line}")
  done < <(collect_files_with_rg)
else
  while IFS= read -r line; do
    FILES+=("${line}")
  done < <(collect_files_with_find)
fi

if [[ ${#FILES[@]} -eq 0 ]]; then
  echo "未找到代码文件: ${TARGET_DIR}"
  exit 0
fi

TMP_COUNTS="$(mktemp)"
trap 'rm -f "${TMP_COUNTS}"' EXIT

for rel_path in "${FILES[@]}"; do
  abs_path="${TARGET_DIR}/${rel_path}"
  [[ -f "${abs_path}" ]] || continue

  line_count="$(wc -l < "${abs_path}" | tr -d ' ')"
  extension="${rel_path##*.}"
  if [[ "${rel_path}" == "${extension}" ]]; then
    extension="(none)"
  fi

  printf "%s\t%s\t%s\n" "${extension}" "${line_count}" "${rel_path}" >> "${TMP_COUNTS}"
done

TOTAL_FILES="$(wc -l < "${TMP_COUNTS}" | tr -d ' ')"
TOTAL_LINES="$(awk -F '\t' '{sum += $2} END {print sum + 0}' "${TMP_COUNTS}")"

echo "代码目录: ${TARGET_DIR}"
echo "代码文件: ${TOTAL_FILES}"
echo "总代码行: ${TOTAL_LINES}"
echo
printf "%-10s %10s %12s\n" "扩展名" "文件数" "代码行"
printf "%-10s %10s %12s\n" "--------" "------" "------"
awk -F '\t' '
  {
    files[$1] += 1
    lines[$1] += $2
  }
  END {
    for (ext in lines) {
      printf "%s\t%s\t%s\n", lines[ext], files[ext], ext
    }
  }
' "${TMP_COUNTS}" | sort -rn -k1,1 | while IFS=$'\t' read -r lines files extension; do
  printf "%-10s %10s %12s\n" "${extension}" "${files}" "${lines}"
done

echo
echo "Top 20 大文件:"
printf "%10s  %s\n" "代码行" "文件"
printf "%10s  %s\n" "------" "----"
sort -rn -k2,2 "${TMP_COUNTS}" | head -n 20 | while IFS=$'\t' read -r extension lines rel_path; do
  printf "%10s  %s\n" "${lines}" "${rel_path}"
done
