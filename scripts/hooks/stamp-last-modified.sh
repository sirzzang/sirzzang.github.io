#!/usr/bin/env bash
#
# stamp-last-modified.sh
#
# 스테이징된 블로그 포스트(_posts/*.md)의 front matter에
# `last_modified_at: <오늘(YYYY-MM-DD)>`를 박아 넣는다.
#   - 이미 있으면 오늘 날짜로 갱신, 없으면 front matter 끝(닫는 --- 앞)에 삽입
#   - 값이 이미 오늘이면 파일을 건드리지 않음(불필요한 diff 방지)
#   - 변경한 파일은 다시 `git add`로 재스테이징
#
# .git/hooks/pre-commit 에서 호출한다. _posts/ 밖의 파일·비-md·front matter가
# 없는 파일은 건너뛴다.
#
# NOTE: macOS 기본 bash(3.2) 호환을 위해 mapfile 대신 while-read 를 쓴다.

set -euo pipefail

# 훅은 보통 저장소 최상위에서 실행되지만, 경로를 확실히 하기 위해 이동한다.
cd "$(git rev-parse --show-toplevel)"

TODAY=$(date +%F)   # YYYY-MM-DD (로컬 타임존)

while IFS= read -r f; do
  [ -n "$f" ] || continue
  case "$f" in
    *.md) ;;      # 마크다운만
    *) continue ;;
  esac
  [ -f "$f" ] || continue   # 삭제(D)된 파일 등은 제외 (필터에서도 걸러지지만 방어)

  # front matter(첫 줄 "---" + 뒤쪽 닫는 "---")가 있어야 한다.
  [ "$(head -n1 "$f")" = "---" ] || { echo "skip (no front matter): $f"; continue; }
  if ! awk 'NR>1 && $0=="---"{found=1; exit} END{exit !found}' "$f"; then
    echo "skip (unterminated front matter): $f"
    continue
  fi

  tmp=$(mktemp)
  awk -v today="$TODAY" '
    BEGIN { state=0; have=0 }         # 0=FM 이전, 1=FM 내부, 2=FM 이후
    state==0 { print; if ($0=="---") state=1; next }
    state==1 {
      if ($0=="---") {                # FM 닫힘 — 없었으면 여기서 삽입
        if (!have) print "last_modified_at: " today
        print; state=2; next
      }
      if ($0 ~ /^last_modified_at:[[:space:]]*/) {   # 기존 값 → 오늘로 교체
        print "last_modified_at: " today; have=1; next
      }
      print; next
    }
    { print }                         # FM 이후는 그대로
  ' "$f" > "$tmp"

  if ! cmp -s "$f" "$tmp"; then
    cat "$tmp" > "$f"
    git add -- "$f"
    echo "stamped last_modified_at: $TODAY -> $f"
  fi
  rm -f "$tmp"
done < <(git diff --cached --name-only --diff-filter=ACM -- '_posts/')

exit 0
