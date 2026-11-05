#!/usr/bin/env bash
# RTX PRO 6000 Blackwell / sm_120 GPU 1 에서 ch07  환경 세팅.
#
# 순서 원칙: 싼 게 먼저 깨지게 한다.
#   드라이버 확인(0초) -> venv(1분) -> torch sm_120 커널(3초) -> 0.6B vLLM 스모크(2분) -> 32B 62GB 다운로드
# Blackwell 은 "설치는 되는데 커널이 없어서 실행이 안 되는" 실패가 흔해서,
# 62GB 받은 다음에 알게 되면 반나절이 날아간다.
set -euo pipefail

GPU="${GPU:-1}"
PORT="${PORT:-8111}"
# 작업 폴더 = 이 스크립트가 놓인 곳
WORKDIR="${WORKDIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)}"

export CUDA_DEVICE_ORDER=PCI_BUS_ID   # CUDA 인덱스를 nvidia-smi 인덱스와 일치시킨다
export CUDA_VISIBLE_DEVICES="$GPU"
# 워크스페이스 *밖*이다. $WORKDIR 를 통째로 지워도 모델 64GB 는 살아남고,
# VS Code 도 크롤링하지 않는다. (2026-08-23 에 워크스페이스를 지워 모델까지 날렸다)
export HF_HOME="${HF_HOME:-$HOME/hf-cache}"

mkdir -p "$WORKDIR"; cd "$WORKDIR"

say() { printf '\n\033[1m== %s ==\033[0m\n' "$*"; }

# vLLM 은 EngineCore 서브프로세스에서 죽고, 최상위 traceback 은 "See root cause above" 만 남긴다.
# 진짜 원인은 그 *위* 라서 tail 로 보면 잘린다.
dump_failure() {
  echo "!! $1 -- smoke.log $(wc -l < smoke.log)줄"
  echo "----- EngineCore 출력 -----"; grep -E "EngineCore" smoke.log | head -60
  echo "----- 첫 Traceback 부터 -----"; sed -n '/Traceback/,$p' smoke.log | head -80
  echo "(전문: $PWD/smoke.log)"
}

say "0. 노드 상태"
nvidia-smi --query-gpu=index,name,driver_version,memory.total,memory.used --format=csv
echo "-- GPU $GPU 를 지금 쓰고 있는 프로세스 (비어 있어야 함) --"
nvidia-smi -i "$GPU" --query-compute-apps=pid,process_name,used_memory --format=csv
echo "-- 디스크 (HF_HOME=$HF_HOME, 최소 80G 여유) --"
df -h "$WORKDIR" | tail -1

say "1. venv (Python 3.12)"
# 3.12 를 고정하는 이유:
#   flashinfer 0.6.16.post3 의 comm/fd_exchange.py 가 `array.array[int]` 를 어노테이션에 쓰는데
#   그 모듈에 `from __future__ import annotations` 가 없어서 import 시점에 평가된다.
#   array.array 가 subscriptable 해진 건 Python 3.12 부터(CPython gh-98658) -> 3.10/3.11 은 즉사:
#     TypeError: 'type' object is not subscriptable
#   vLLM 은 torch.compile 백엔드 초기화에서 flashinfer.comm 을 import 하므로 엔진이 아예 못 뜬다.
#   flashinfer 는 requires_python >=3.10 이라고 "선언만" 한다. 시스템 python3 가 3.10 이면 그대로 밟는다.
rm -rf .venv .bootstrap                      # 재실행 시 3.10 잔재 제거 (uv 캐시가 있어 재설치는 빠르다)
python3 -m venv .bootstrap                   # uv 부트스트랩 전용, 버리는 venv
./.bootstrap/bin/pip -q install --upgrade pip uv
UV="$PWD/.bootstrap/bin/uv"
"$UV" venv --python 3.12 .venv               # 시스템에 3.12 가 없으면 uv 가 관리형 CPython 을 받아온다 (root 불필요)

# 위 버그의 회귀 테스트. 3.11 이하면 여기서 죽고, 62GB 받기 전에 끝난다.
./.venv/bin/python -c "import sys, array; array.array[int]; print('python', '.'.join(map(str, sys.version_info[:3])), 'ok')"

say "2. vLLM 설치"
# --torch-backend=auto 가 드라이버를 보고 cu128/cu129/cu130 중 맞는 torch 를 고른다.
# 노트북 원본의 vllm==0.11.0 은 쓰지 않는다: 2025-10 릴리스라 sm_120 커널 공백이 가장 심하고,
# GPU 가 A100 이 아니라 어차피 책의 절대 수치는 재현되지 않는다. 재현할 건 "변형 간 상대 차이".
# vllm[bench]: `vllm bench serve` 는 extra 다. 맨 vllm 만 깔면 서버는 멀쩡히 뜨는데
#   벤치가 "ImportError: Please install vllm[bench]" 로 죽는다 (2026-08-23 에 밟음).
#   extra 내용 = pandas, matplotlib, seaborn, datasets, scipy, plotly -> matplotlib 도 여기 포함.
# ipykernel: 없으면 VS Code 가 이 venv 를 커널로 띄우지 못한다 (vLLM 이 안 끌고 온다).
# uv: .bootstrap 을 지운 뒤에도 재설치를 할 수 있게 venv 안으로 옮겨둔다.
"$UV" pip install --python "$PWD/.venv/bin/python" --torch-backend=auto \
  "vllm[bench]" ipykernel uv

# python3.10 부트스트랩 venv 제거. 남겨두면 VS Code 커널 피커에 3.10 이 같이 떠서
# 잘못 고르는 순간 flashinfer import 에러를 그대로 다시 밟는다.
rm -rf .bootstrap
UV="$PWD/.venv/bin/uv"
# venv/bin 을 PATH 에 올린다. 노트북 첫 셀이 하는 것과 동일하게 맞춰서, 스모크가 실제 실행 환경을 테스트하게 한다.
# (FlashInfer 는 JIT 컴파일이고 ninja/gcc 를 shutil.which 로 찾는다. ninja 는 uv 가 venv 에 넣어준다.)
export PATH="$PWD/.venv/bin:$PATH"
for b in gcc nvcc ninja; do
  command -v "$b" >/dev/null || echo "  !! $b 없음 -> FlashInfer JIT 실패 가능 (sudo apt install gcc python3-dev ninja-build cuda-toolkit)"
done

# 노트북이 실제로 import 하는 것들. 여기서 걸리면 커널 붙이고 나서 알게 되는 것보다 낫다.
./.venv/bin/python -c "import ipykernel, matplotlib, openai, requests, numpy; print('notebook deps ok')"

say "3. torch 가 sm_120 커널을 실제로 갖고 있나 (3초)"
./.venv/bin/python - <<'PY'
import torch
cc = torch.cuda.get_device_capability(0)
print("torch", torch.__version__, "/ cuda", torch.version.cuda)
print("device", torch.cuda.get_device_name(0), "cc", cc)
assert torch.cuda.device_count() == 1, "CUDA_VISIBLE_DEVICES 가 안 먹었다"
# import 만으로는 안 잡힌다. 커널을 실제로 띄워봐야 'no kernel image' 가 나온다.
a = torch.randn(2048, 2048, device="cuda", dtype=torch.bfloat16)
print("bf16 matmul ok", (a @ a).sum().item() is not None)
print("arch list", torch.cuda.get_arch_list())
assert f"sm_{cc[0]}{cc[1]}" in torch.cuda.get_arch_list(), "wheel 에 sm_120 커널 없음"
PY

say "4. vLLM 스모크 — Qwen3-0.6B + ngram (1.2GB)"
# 32B 를 받기 전에, 이 노트북이 쓰는 경로(서빙 + speculative-config + OpenAI API)를 싸게 통과시킨다.
./.venv/bin/vllm serve Qwen/Qwen3-0.6B \
  --port "$PORT" --max-model-len 2048 --gpu-memory-utilization 0.15 \
  --speculative-config '{"method":"ngram","num_speculative_tokens":4,"prompt_lookup_min":2,"prompt_lookup_max":8}' \
  > smoke.log 2>&1 &
SMOKE_PID=$!
trap 'kill $SMOKE_PID 2>/dev/null || true' EXIT

for i in $(seq 60); do
  curl -sf "http://127.0.0.1:$PORT/health" >/dev/null && break
  kill -0 $SMOKE_PID 2>/dev/null || { dump_failure "서버가 죽었다"; exit 1; }
  sleep 5
done
curl -sf "http://127.0.0.1:$PORT/health" >/dev/null || { dump_failure "타임아웃"; exit 1; }

echo "-- 출력이 깨지지 않는지 (Blackwell 은 커널이 있어도 garbage 를 뱉는 경우가 있다) --"
curl -s "http://127.0.0.1:$PORT/v1/completions" -H 'Content-Type: application/json' \
  -d "{\"model\":\"Qwen/Qwen3-0.6B\",\"prompt\":\"The capital of France is\",\"max_tokens\":20,\"temperature\":0}"
echo

# 노트북이 실제로 실행하는 명령을 쳐본다. 위의 `import` 검사는 이 부류를 못 잡는다
# (모듈은 다 있는데 CLI 하위명령이 extra 라서 죽는 경우).
echo "-- vllm bench serve 가 되는지 (노트북 벤치 셀과 같은 경로) --"
./.venv/bin/vllm bench serve --backend vllm --base-url "http://localhost:$PORT" \
  --endpoint /v1/completions --model Qwen/Qwen3-0.6B \
  --dataset-name random --num-prompts 4 --max-concurrency 1 \
  --random-input-len 32 --random-output-len 16 2>&1 | tail -20

grep -iE "spec|draft|acceptance" smoke.log | tail -5 || true
kill $SMOKE_PID 2>/dev/null || true; trap - EXIT; sleep 5

cat <<MSG

== 여기까지 통과했으면 다음 ==
  export HF_HOME=$HF_HOME
  ./.venv/bin/hf download Qwen/Qwen3-32B                        # 61.0 GiB
  ./.venv/bin/hf download RedHatAI/Qwen3-32B-speculator.eagle3  #  2.9 GiB
  git clone --depth 1 https://github.com/hemingkx/Spec-Bench.git

  # 셋 다 gated 아님 -> 토큰 불필요. 단 다운로드 중 429 (Too Many Requests) 가 나면
  # HF 익명 rate limit 을 IP 단위로 맞은 것이다 (사내망 NAT 라 남의 트래픽까지 합산됨).
  #   ./.venv/bin/hf auth login   # 또는 export HF_TOKEN=hf_xxx
  # 토큰은 read 권한이면 충분하고, 이어받기가 되므로 그 자리에서 붙이고 재실행하면 된다.
그 다음 VS Code Remote-SSH 로 $WORKDIR 를 열고 LMCache.ipynb 의 커널을 아래로 선택:
  $WORKDIR/.venv/bin/python
  (커널 피커에 다른 python 이 보이면 그건 시스템 3.10 이다. 위 경로인지 확인할 것.
   노트북 첫 셀의 sys.executable 출력이 이 경로와 같아야 한다.)

== 3번에서 'no kernel image' / arch list 에 sm_120 없음 이면 ==
  ./.venv/bin/uv pip install --python ./.venv/bin/python -U --pre vllm \\
    --extra-index-url https://wheels.vllm.ai/nightly/cu129
MSG
