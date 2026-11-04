#!/usr/bin/env bash
# 가짜 GPU 1장을 두고 세션 회수 시나리오를 차례로 돌린다.
#   kind create cluster --config kind.yaml --kubeconfig ./kubeconfig
#   KUBECONFIG=$PWD/kubeconfig bash run_stage1.sh | tee results/stage1.txt
# 시나리오 5는 실제 브라우저 접속을 쓴다. CHROME에 Chrome 실행 파일을 지정한다.
set -euo pipefail
cd "$(dirname "$0")"
NS=sessions
IDLE=${IDLE:-90}   # 실험용 유휴 기준(초)
PY=${PYTHON:-python3}
CHROME=${CHROME:-/Applications/Google Chrome.app/Contents/MacOS/Google Chrome}
export NS

say() { printf '\n=== [%s] %s\n' "$(date +%H:%M:%S)" "$*"; }
run() { printf '$ %s\n' "$*"; "$@"; }
k() { kubectl -n "$NS" "$@"; }
apply_session() { sed "s/__NAME__/$1/g" session.yaml | k apply -f -; }
pods() { printf '$ kubectl -n %s get pods\n' "$NS"; k get pods -o wide --no-headers | awk '{print $1, $2, $3}'; }
wait_ready() {
  for _ in $(seq 1 60); do
    [ "$(k get pods -l "app=$1" --no-headers 2>/dev/null | wc -l)" -gt 0 ] && break
    sleep 1
  done
  k wait --for=condition=Ready pod -l "app=$1" --timeout=180s >/dev/null
}
reclaim() { printf '$ python3 reclaim.py --idle-limit %s %s\n' "$IDLE" "$*"; "$PY" reclaim.py --idle-limit "$IDLE" "$@"; }
health() { kubectl get --raw "/api/v1/namespaces/$NS/services/$1:8080/proxy/healthz"; echo; }
metric() { mkdir -p metrics; printf '%s\n' "$2" > "metrics/$1.json"; printf 'metrics/%s.json = %s\n' "$1" "$2"; }

say "준비: 노드에 가짜 GPU 1장을 광고한다"
node=$(kubectl get nodes -o name | head -1)
run kubectl patch "$node" --subresource=status --type=json \
  -p '[{"op":"add","path":"/status/capacity/nvidia.com~1gpu","value":"1"}]'
for _ in $(seq 1 30); do
  [ "$(kubectl get "$node" -o jsonpath='{.status.allocatable.nvidia\.com/gpu}')" = "1" ] && break
  sleep 1
done
printf 'allocatable nvidia.com/gpu = %s\n' "$(kubectl get "$node" -o jsonpath='{.status.allocatable.nvidia\.com/gpu}')"
kubectl create namespace "$NS" >/dev/null
rm -rf metrics

say "시나리오 1: 세션 A가 GPU를 잡으면 세션 B는 대기한다"
apply_session session-a
wait_ready session-a
k exec deploy/session-a -- sh -c 'echo keep > /home/coder/keep.txt; echo gone > /tmp/gone.txt'
apply_session session-b
sleep 5
pods
run kubectl -n "$NS" get events --field-selector reason=FailedScheduling -o custom-columns=MESSAGE:.message --no-headers | tail -1

say "시나리오 2: A에 접속이 없고 GPU 지표가 0이면 회수되고 B가 뜬다"
metric session-a '{"gpu_util": 0, "fb_mib": 0, "sm_active": 0.0, "cpu_cores": 0.0}'
health session-a
sleep "$((IDLE + 5))"
t0=$(date +%s)
reclaim
wait_ready session-b
printf '회수부터 세션 B Ready까지 %s초\n' "$(($(date +%s) - t0))"
pods

say "시나리오 3: A를 다시 올리면 GPU가 없어 대기한다. 사용률 100%지만 메모리가 빈 B(phantom)가 회수되면 A가 뜬다"
run kubectl -n "$NS" scale deploy/session-a --replicas=1
sleep 5
pods
metric session-b '{"gpu_util": 100, "fb_mib": 0, "sm_active": null, "cpu_cores": 0.0}'
sleep "$((IDLE + 5))"
t0=$(date +%s)
reclaim
wait_ready session-a
printf '회수부터 세션 A Ready까지 %s초\n' "$(($(date +%s) - t0))"
pods
printf '$ cat /home/coder/keep.txt; cat /tmp/gone.txt\n'
k exec deploy/session-a -- sh -c 'cat /home/coder/keep.txt; cat /tmp/gone.txt 2>&1 || true'

say "시나리오 4a: 대기 세션이 없을 때 파드만 지우면 새 파드가 GPU를 다시 잡는다"
pods
run kubectl -n "$NS" delete pod -l app=session-a --wait=true
wait_ready session-a
pods

say "시나리오 4b: 대기 세션이 있을 때 파드만 지우면 누가 GPU를 받는가"
run kubectl -n "$NS" scale deploy/session-b --replicas=1
sleep 5
pods
run kubectl -n "$NS" delete pod -l app=session-a --wait=true
for _ in 1 2 3 4 5 6; do sleep 5; done
pods

say "정리: B를 내리고 A만 남긴다"
k scale deploy/session-b --replicas=0 >/dev/null
k scale deploy/session-a --replicas=1 >/dev/null
wait_ready session-a
pods

say "시나리오 5: 브라우저 접속만 열어 두면 지표가 0이어도 회수되지 않는다"
metric session-a '{"gpu_util": 0, "fb_mib": 0, "sm_active": 0.0, "cpu_cores": 0.0}'
k port-forward svc/session-a 18080:8080 >/dev/null 2>&1 &
pf=$!
# /healthz 조회는 heartbeat를 올리지 않는다. 포트가 열릴 때까지만 기다린다
curl -s -o /dev/null --retry 30 --retry-connrefused --retry-delay 1 http://127.0.0.1:18080/healthz
profile=$(mktemp -d)
"$CHROME" --headless=new --disable-gpu --no-first-run --no-default-browser-check --user-data-dir="$profile" \
  "http://127.0.0.1:18080/?folder=/home/coder" >/dev/null 2>&1 &
chrome=$!
trap 'kill $chrome $pf 2>/dev/null || true; rm -rf "$profile"' EXIT
for _ in $(seq 1 60); do  # 브라우저가 접속할 때까지 기다린다
  health session-a | grep -q '"alive"' && break
  sleep 1
done
for t in 30 60 60 60; do
  sleep "$t"
  health session-a
  reclaim --dry-run
done
say "시나리오 5 계속: 브라우저를 닫으면 heartbeat가 끊기고 기준 시간 뒤 회수된다"
kill "$chrome" "$pf" 2>/dev/null || true
wait "$chrome" "$pf" 2>/dev/null || true
trap 'rm -rf "$profile"' EXIT
sleep 70
health session-a
reclaim --dry-run
sleep "$IDLE"
health session-a
reclaim
pods
