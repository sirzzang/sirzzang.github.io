#!/usr/bin/env bash
# 컨테이너(python:3.12-slim) 안에서 실행되는 실험 본체.
# 실험 A~D를 순서대로 수행하고, 섹션 구분자를 출력해 결과를 발췌하기 쉽게 한다.
set -uo pipefail

section() {
  echo                                                        # 여백 한 줄
  echo "================================================================"
  echo "$1"                                                   # 호출 시 넘긴 제목 인자 출력
  echo "================================================================"
}

run() {
  # 실행할 명령을 먼저 보여 주고 실행한다 (실패해도 계속 진행)
  echo                                                         # 여백 한 줄
  echo "\$ $*"                                                 # 실행할 명령을 "$ cmd args..." 형태로 미리 출력 (터미널 프롬프트 흉내)
  "$@" 2>&1                                                    # 실제 실행. $@로 인자를 개별 보존, stderr를 stdout에 합쳐서 함께 출력
  echo "(exit: $?)"                                            # 직전 명령의 종료 코드 출력 (set -e 없이 실패를 눈으로 확인하기 위함)
}

export PIP_DISABLE_PIP_VERSION_CHECK=1                         # pip 버전 체크(최신 버전 안내 메시지) 비활성화 — 노이즈 제거용
export PIP_ROOT_USER_ACTION=ignore                              # root로 pip 실행 시 뜨는 경고 메시지 비활성화 — 컨테이너가 기본 root라서 발생

section "환경 정보"
run python3 --version
run which python3

section "실험 A: 실행 방식별 sys.path[0]"

echo
echo "--- A-1. 스크립트 경로 실행: sys.path[0] = 스크립트가 있는 디렉터리"
cd /lab
run python3 show_syspath.py
cd /tmp
run python3 /lab/show_syspath.py   # cwd(/tmp)와 스크립트 디렉터리(/lab)가 다른 상황

echo
echo "--- A-2. -m 실행: sys.path[0] = 현재 작업 디렉터리(cwd)"
cd /lab
run python3 -m show_syspath
cd /tmp
run python3 -m show_syspath        # cwd(/tmp)에 모듈이 없으므로 실패 예상

echo
echo "--- A-3. -c 실행: sys.path[0] = '' (cwd 의미)"
cd /lab
run python3 -c 'import os, sys; print(f"cwd={os.getcwd()}, sys.path[0]={sys.path[0]!r}")'

echo
echo "--- A-4. -P (safe path, 3.11+): sys.path[0] 자동 삽입 안 함"
cd /lab
run python3 -P show_syspath.py
run python3 -P -m show_syspath     # cwd가 sys.path에 없으므로 실패 예상

section "실험 B: pytest app/ vs python3 -m pytest app/"
run python3 -m pip install -q pytest

echo
echo "--- B-1. python3 -m pytest app/ (repo 루트에서)"
cd /lab
run python3 -m pytest app/ -q -s

echo
echo "--- B-2. pytest app/ (repo 루트에서, -m 없이)"
cd /lab
run pytest app/ -q -s

echo
echo "--- B-3. 다른 cwd(/tmp)에서 절대 경로로"
cd /tmp
run pytest /lab/app/ -q -s
run python3 -m pytest /lab/app/ -q -s

echo
echo "--- B-4. tests/ 분리 레이아웃: -m 여부가 import 성패를 가르는 경우"
cd /lab/proj
run pytest tests/ -q          # 프로젝트 루트가 sys.path에 없어 import mylib 실패 예상
run python3 -m pytest tests/ -q   # -m이 cwd(프로젝트 루트)를 sys.path에 추가 → 성공 예상

section "실험 C: pytest 런처의 정체와 인터프리터 결속"

echo
echo "--- C-0. pip install이 만든 산출물: 패키지 코드 / dist-info / 런처"
run ls /usr/local/lib/python3.12/site-packages
run ls /usr/local/lib/python3.12/site-packages/pytest
run cat /usr/local/lib/python3.12/site-packages/pytest-*.dist-info/entry_points.txt
# 대조: console_scripts 선언이 없는 import 전용 라이브러리는 런처가 생기지 않는다
run python3 -m pip install -q requests
run ls /usr/local/lib/python3.12/site-packages/requests-*.dist-info/

echo
echo "--- C-1. pytest 실행 파일의 위치와 내용(셔뱅)"
run which pytest
run cat /usr/local/bin/pytest

echo
echo "--- C-2. venv에 다른 버전 pytest 설치 후 PATH 순서 관찰"
run python3 -m venv /opt/venv
run /opt/venv/bin/pip install -q pytest==7.4.4
export PATH=/opt/venv/bin:$PATH
run which pytest
run which python3
run pytest --version                          # PATH 우선순위: venv의 pytest
run python3 -m pytest --version               # PATH 우선순위: venv의 python3 → venv의 pytest
run /usr/local/bin/python3 -m pytest --version  # 인터프리터를 명시하면 그 파이썬의 pytest

echo
echo "--- C-3. pytest 패키지 안의 __main__.py"
run /usr/local/bin/python3 -c 'import pytest, os; print(os.path.dirname(pytest.__file__))'
run cat "$(/usr/local/bin/python3 -c 'import pytest, os; print(os.path.dirname(pytest.__file__))')/__main__.py"

section "실험 D: -m과 __main__"
cd /lab

echo
echo "--- D-1. 패키지를 -m으로 실행: __main__.py가 진입점"
run python3 -m mypkg

echo
echo "--- D-2. 패키지 내 단일 모듈을 -m으로 실행"
run python3 -m mypkg.tool

echo
echo "--- D-3. 같은 파일을 경로로 직접 실행 (대조)"
run python3 mypkg/tool.py

section "정리: 캐시 파일 삭제"
find /lab -type d \( -name __pycache__ -o -name .pytest_cache \) -exec rm -rf {} + 2>/dev/null
echo "done"
