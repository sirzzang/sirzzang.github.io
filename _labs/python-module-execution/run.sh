#!/usr/bin/env bash
# 호스트에서 실행하는 래퍼.
# 로컬 파이썬을 쓰지 않고 python:3.12-slim 컨테이너 안에서 lab.sh를 돌린다.
set -euo pipefail

cd "$(dirname "$0")"

docker run --rm -v "$PWD":/lab -w /lab python:3.12-slim bash lab.sh
