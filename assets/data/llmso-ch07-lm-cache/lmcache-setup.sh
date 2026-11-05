#!/usr/bin/env bash
# LMCache 실습 환경. setup.sh 가 만든 .venv 에 얹는다 (venv 를 새로 만들지 않는다).
#
# setup.sh 와 같은 원칙: 27.5GB 받기 전에 싼 것부터 깨뜨린다.
#   RAM 확인 -> lmcache 설치 -> 0.6B 로 커넥터 스모크 -> 그 다음에 14B
# LMCache 는 vLLM 내부 KVConnector API 에 물려 있어서, 버전이 어긋나면
# "설치는 되는데 서버 기동에서 죽는" 실패가 난다. 0.6B 로 먼저 밟아본다.
set -euo pipefail

GPU="${GPU:-1}"
PORT="${PORT:-8112}"          # SpecDecode(8111) 와 겹치지 않게
# 작업 폴더 = 이 스크립트가 놓인 곳. ~/specdecode 든 ~/lm-cache 든 스크립트를 넣고 실행하면 된다.
WORKDIR="${WORKDIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)}"

export CUDA_DEVICE_ORDER=PCI_BUS_ID
export CUDA_VISIBLE_DEVICES="$GPU"
# 워크스페이스 *밖*이다. $WORKDIR 를 통째로 지워도 모델 64GB 는 살아남고,
# VS Code 도 크롤링하지 않는다. (2026-08-23 에 워크스페이스를 지워 모델까지 날렸다)
export HF_HOME="${HF_HOME:-$HOME/hf-cache}"

cd "$WORKDIR"
[ -x ./.venv/bin/vllm ] || { echo "이 폴더($WORKDIR)에 .venv 가 없다. 같은 폴더에서 ./setup.sh 를 먼저 돌릴 것"; exit 1; }
export PATH="$PWD/.venv/bin:$PATH"

say() { printf '\n\033[1m== %s ==\033[0m\n' "$*"; }
dump_failure() {
  echo "!! $1 -- lmcache-smoke.log $(wc -l < lmcache-smoke.log)줄"
  echo "----- EngineCore -----"; grep -E "EngineCore" lmcache-smoke.log | head -60
  echo "----- 첫 Traceback -----"; sed -n '/Traceback/,$p' lmcache-smoke.log | head -80
  echo "----- LMCache 관련 -----"; grep -iE "lmcache|kv_connector|kv transfer" lmcache-smoke.log | head -30
  echo "(전문: $PWD/lmcache-smoke.log)"
}

# VPN 이 끊기면 포그라운드 SSH 작업은 SIGHUP 으로 죽는다 (2026-08-23 에 3단계에서 끊겼다).
# 이 스크립트는 몇 분이면 끝나지만, 실습 본편(수십 분)은 반드시 tmux 안에서 돌릴 것.
[ -z "${TMUX:-}" ] && [ -n "${SSH_CONNECTION:-}" ] \
  && echo "  .. tmux 밖이다. VPN 이 끊기면 중단된다: tmux new -s lmcache"

say "0. 자원 예산"
free -g | awk 'NR<=2'
TOTAL_RAM=$(free -g | awk 'NR==2{print $2}')
# upstream 은 150GB pinned CPU 를 잡는다. pinned 메모리는 스왑이 안 되고,
# 공용 노드에서 과하게 잡으면 남의 작업까지 같이 죽는다. RAM 의 40% 를 상한으로 둔다.
CPU_GB="${LMCACHE_CPU_GB:-$(( TOTAL_RAM * 40 / 100 ))}"
[ "$CPU_GB" -gt 150 ] && CPU_GB=150
echo "  RAM ${TOTAL_RAM}G -> LMCache CPU 캐시 ${CPU_GB}G (LMCACHE_CPU_GB 로 덮어쓰기 가능)"
WORKING_SET=125   # 프롬프트 30개 x 약 26k 토큰 x 160KiB/토큰
if [ "$CPU_GB" -ge "$WORKING_SET" ]; then
  echo "  워킹셋 약 ${WORKING_SET}G <= 캐시 ${CPU_GB}G -> warm 구간이 전부 적중한다. 이득을 온전히 본다."
else
  echo "  워킹셋 약 ${WORKING_SET}G > 캐시 ${CPU_GB}G -> warm 구간이 일부만 적중한다."
  echo "  => LMCache 이득이 실제보다 작게 나온다. 결과 해석 시 반드시 명시할 것."
fi
nvidia-smi -i "$GPU" --query-compute-apps=pid,used_gpu_memory --format=csv
df -h "$WORKDIR" | tail -1

say "1. lmcache 설치"
# vllm[bench] 는 setup.sh 가 넣지만, 이 스크립트만 따로 돌리는 경우를 대비해 같이 확인한다.
./.venv/bin/uv pip install --python ./.venv/bin/python --torch-backend=auto lmcache "vllm[bench]"
./.venv/bin/python -c "
from importlib.metadata import version
import lmcache
print('lmcache', version('lmcache'), '/ vllm', version('vllm'))
import lmcache.integration.vllm.lmcache_connector_v1 as m   # 커넥터 모듈이 실제로 import 되나
print('connector module ok:', m.__name__)
"

# lmcache 설치는 numpy(2.3.5 -> 2.2.6), opentelemetry, prometheus-client 를 끌어내린다.
# 다운그레이드가 vllm/bench 를 깨뜨리지 않았는지 여기서 확인한다 (전에 extra 누락을 늦게 발견한 전례).
./.venv/bin/python -c "
import numpy, pandas, datasets, matplotlib, ipykernel, vllm
from importlib.metadata import version
print('numpy', numpy.__version__, '/ pandas', pandas.__version__, '/ vllm', version('vllm'))
print('post-lmcache deps ok')
"

say "2. LMCache 설정 파일"
cat > lmcache.yaml <<YAML
# upstream 의 LMCACHE_* env 대신 YAML. 현재 LMCache 문서 방식이고,
# 설정이 파일로 남아 results/ 에 그대로 증적이 된다.
chunk_size: 256
local_cpu: true
max_local_cpu_size: ${CPU_GB}
YAML
cat lmcache.yaml

say "3. 커넥터 스모크 — Qwen3-0.6B (이미 받아둔 모델)"
# PYTHONHASHSEED: LMCache 가 builtin hash 로 청크 키를 만든다. 프로세스마다 시드가 다르면
# 같은 프롬프트가 다른 키가 되어 캐시를 조용히 못 찾는다 (LMCache 자체 경고).
PYTHONHASHSEED=0 LMCACHE_CONFIG_FILE="$PWD/lmcache.yaml" \
./.venv/bin/vllm serve Qwen/Qwen3-0.6B \
  --port "$PORT" --max-model-len 2048 --gpu-memory-utilization 0.15 \
  --kv-transfer-config '{"kv_connector":"LMCacheConnectorV1Dynamic","kv_role":"kv_both","kv_connector_module_path":"lmcache.integration.vllm.lmcache_connector_v1"}' \
  > lmcache-smoke.log 2>&1 &
PID=$!
trap 'kill $PID 2>/dev/null || true' EXIT

for _ in $(seq 60); do
  curl -sf "http://127.0.0.1:$PORT/health" >/dev/null && break
  kill -0 $PID 2>/dev/null || { dump_failure "서버가 죽었다"; exit 1; }
  sleep 5
done
curl -sf "http://127.0.0.1:$PORT/health" >/dev/null || { dump_failure "타임아웃"; exit 1; }

# 같은 프롬프트를 두 번. 두 번째에 LMCache 가 KV 를 되쓰는 로그가 나와야 한다.
for n in 1 2; do
  echo "-- 요청 $n --"
  curl -s "http://127.0.0.1:$PORT/v1/completions" -H 'Content-Type: application/json' \
    -d "{\"model\":\"Qwen/Qwen3-0.6B\",\"prompt\":\"$(python3 -c 'print("The capital of France is Paris. " * 60)')Question: what is the capital?\",\"max_tokens\":10,\"temperature\":0}" \
    | head -c 300; echo
done

echo "-- LMCache 가 실제로 KV 를 저장/재사용했나 --"
grep -iE "lmcache" lmcache-smoke.log | grep -iE "stor|retriev|hit|reus|token" | tail -8 \
  || { echo "  !! LMCache 로그가 없다. 커넥터가 안 붙었을 수 있다:"; grep -iE "kv_connector|kv transfer" lmcache-smoke.log | tail -5; }

kill $PID 2>/dev/null || true; trap - EXIT; sleep 5

cat <<MSG

== 통과했으면 ==
  export HF_HOME=$HF_HOME
  nohup ./.venv/bin/hf download Qwen/Qwen3-14B > dl14b.log 2>&1 &   # 27.5 GiB

  VS Code 에서 LMCache.ipynb, 커널 = $WORKDIR/.venv/bin/python

== "Storing KV cache" 류 로그가 안 나오면 ==
  커넥터는 붙었지만 동작을 안 하는 것. lmcache 버전을 내려본다:
    ./.venv/bin/uv pip install --python ./.venv/bin/python 'lmcache<0.5'
  그래도 안 되면 vllm 0.27.1 과 안 맞는 것 -> LMCache 실습은 보류하고 이슈만 기록.
MSG
