---
title: "[EKS] EKS GPU 트러블슈팅: 3. 장애 재현 - 2. vLLM 기동 실패"
excerpt: "A10G 24GB에 vLLM 14B-AWQ를 올려 vLLM 기동 실패 시나리오 4가지를 재현하고, kubectl logs --previous 중심의 디버깅 경로를 짚어 보자."
categories:
  - Kubernetes
toc: true
header:
  teaser: /assets/images/blog-Dev.jpg
tags:
  - Kubernetes
  - AWS
  - EKS
  - GPU
  - vLLM
  - LLM-Serving
  - KV-Cache
  - Troubleshooting
  - AWS-EKS-Workshop-Study
  - AWS-EKS-Workshop-Study-Week-5
---

*정영준님의 AWS EKS Workshop Study(AEWS) [5주차 학습 내용](https://devfloor9.github.io/engineering-playbook/slides/eks-debugging/)을 기반으로 합니다.*

<br>

# TL;DR

[이전 글]({% post_url 2026-04-09-Kubernetes-EKS-GPU-TroubleShooting-03-01-GPU-Pod-Pending %})에서 Device Plugin 비활성화로 **인프라 계층** 장애를 재현했다면, 이번에는 같은 GPU 환경(g5.xlarge × 2, gpu-operator v26.3.1, ClusterPolicy `ready`) 위에서 **어플리케이션 계층** 장애를 재현한다. vLLM(v0.19.1)으로 [Qwen2.5-14B-Instruct-AWQ](https://huggingface.co/Qwen/Qwen2.5-14B-Instruct-AWQ)(Alibaba Cloud의 14B 파라미터 instruction-tuned 모델을 AWQ 4-bit 양자화한 버전)를 서빙하면서, 기동 실패 시나리오 4가지를 재현하고 디버깅한다.

- **시나리오 0 (예상치 못한 장애)**: Service 이름 `vllm` → K8s가 `VLLM_PORT=tcp://...` env 주입 → vLLM의 `VLLM_PORT` env와 이름 충돌 → `ValueError`. 해결: `enableServiceLinks: false`
- **시나리오 1 (KV cache 부족)**: `gpu-memory-utilization=0.5` + `max-model-len=16384` → weights 로딩 후 KV 할당 단계에서 실패. `3.0 GiB needed, 0.18 GiB available, estimated max_model_len=976`
- **시나리오 2 (context window 초과)**: `max-model-len=131072` → config 검증 단계에서 즉시 실패(<30s). `max_position_embeddings=32768` 초과
- **시나리오 3 (TP 불일치)**: `tensor-parallel-size=2`, GPU 1개 → config 검증 단계에서 즉시 실패. `World size (2) > available GPUs (1)`
- **핵심 디버깅 도구**: `kubectl logs --previous`. 현재 컨테이너는 재시작 중이므로 에러는 직전 컨테이너 로그에 있다
- **운영 함정 3가지**: 1. Service 이름과 앱 env 충돌, 2. `connect refused`를 probe 문제로 오해, 3. 양자화 성공 ≠ 서빙 성공

<br>

# 배경

이 글에서 등장하는 주요 용어를 먼저 짚고 가자.

## vLLM과 LLM 서빙 개념

- **KV cache**: Transformer의 attention 연산에서, 이전 토큰의 Key/Value 벡터를 GPU 메모리에 캐싱한 것. 요청 수가 많을수록, 시퀀스가 길수록 더 많은 VRAM을 소비한다. 기존 서빙 시스템은 요청마다 최대 시퀀스 길이만큼 연속 메모리를 미리 할당해서 fragmentation 낭비가 컸다
- **vLLM**: LLM 추론 서빙 엔진. OS의 virtual memory paging 기법을 차용한 **PagedAttention**으로 KV cache를 고정 크기 블록 단위로 관리하여, 위 fragmentation 문제를 해결했다. OpenAI 호환 API(`/v1/chat/completions`)를 제공한다
- **AWQ**: Activation-aware Weight Quantization. 모델 weights를 4-bit로 양자화하여 VRAM 사용량을 줄이는 기법이다. 14B 모델 기준 FP16 ~28 GiB → AWQ 4-bit ~9.4 GiB
- **RoPE** (Rotary Position Embedding): Transformer가 토큰의 위치 정보를 인코딩하는 방식. 원래 Transformer([Positional Encoding 정리]({% post_url 2020-08-13-AI-Transformer-02 %}))는 sin/cos 기반의 고정 벡터를 임베딩에 **더했지만**, RoPE는 attention의 Query/Key 벡터 자체를 위치에 따른 **회전 행렬**로 변환한다. 예를 들어 Qwen2.5의 `max_position_embeddings=32768`은 위치 0~32767까지의 회전 패턴으로 학습했다는 뜻이다. `max-model-len=131072`처럼 이 범위를 벗어나는 위치를 넣으면, 모델이 한 번도 본 적 없는 회전 각도를 만나 수치적으로 NaN이 터지고 출력이 쓰레기가 된다. Qwen2.5, LLaMA, Mistral 등 최근 주요 LLM 대부분이 RoPE를 사용한다

## vLLM 기동 파라미터

- **`gpu-memory-utilization`**: vLLM이 전체 GPU 메모리 중 자신의 예산으로 확보할 비율(기본값 0.9). vLLM은 이 예산 안에서 weights, KV cache, CUDA graph을 할당한다. 예산 밖에 남겨두는 나머지(0.9면 10%)는 PyTorch CUDA context, 임시 activation 텐서, fragmentation 등 **vLLM이 직접 제어하지 못하는** GPU 메모리 소비를 위한 여유분이다. 1.0으로 올리면 이 여유분이 사라져 런타임 CUDA OOM이 발생할 수 있으므로, 0.85~0.95 범위에서 조정한다
- **`max-model-len`**: vLLM이 단일 요청에서 처리할 수 있는 최대 토큰 수(입력 프롬프트 + 생성 출력 합산). attention 연산에서 토큰마다 Key/Value 벡터를 KV cache에 저장해야 하므로, 이 값이 클수록 단일 요청에 필요한 KV 메모리가 늘어난다. vLLM은 기동 시 **최소 1개 요청의 `max-model-len`분 KV를 할당할 여유가 있는지** 검증하고, 부족하면 기동을 거부한다
- **`tensor-parallel-size` (TP)**: 하나의 레이어 안에서 weight 행렬을 열(column) 또는 행(row) 방향으로 **쪼개** 여러 GPU에 나눠 싣는 병렬화 방식. 예를 들어 TP=2면 하나의 linear layer weight를 절반씩 2개 GPU가 나눠 가지고, 각자 부분 연산 후 all-reduce로 합산한다. TP 수는 **해당 노드(Pod)에서 보이는 GPU 수 이하**여야 한다. 단일 노드에 GPU 1개인 환경에서 TP=2를 설정하면 vLLM이 기동을 거부한다
- **`max_position_embeddings`**: 모델이 학습 시 사용한 최대 위치 인코딩 길이. 모델의 `config.json`에 정의되어 있으며, 이를 초과하는 `max-model-len`은 RoPE NaN 등의 문제를 일으킬 수 있다

## Kubernetes 설정

- **`enableServiceLinks`**: K8s Pod spec 필드. `true`(기본값)이면 같은 namespace의 모든 Service에 대해 `{SVC_NAME}_PORT`, `{SVC_NAME}_SERVICE_HOST` 등의 환경 변수를 Pod에 자동 주입한다

<br>

# 전제 환경

[이전 글]({% post_url 2026-04-09-Kubernetes-EKS-GPU-TroubleShooting-03-01-GPU-Pod-Pending %})에서 구성한 환경을 그대로 이어받는다. GPU 노드 2대에 GPU Operator가 설치되어 ClusterPolicy가 `ready` 상태인 시점이다.

| 항목 | 값 |
| --- | --- |
| GPU 노드 | g5.xlarge × 2, NVIDIA A10G 23,028 MiB |
| ephemeral-storage Allocatable | ~89 GiB |
| GPU Operator | v26.3.1, ClusterPolicy `status.state: ready` |
| Device Plugin DS | 2/2/2 Ready |
| GPU taint | `nvidia.com/gpu=true:NoSchedule` |

## vLLM baseline 매니페스트

장애 재현과 검증에 사용할 baseline 매니페스트다. Qwen2.5-14B-Instruct-AWQ를 A10G 1장에 올리는 설정이다. 핵심 부분만 발췌한다.

```yaml
# vllm-baseline.yaml (발췌) — 장애 시나리오에서 변경되는 핵심 설정
apiVersion: apps/v1
kind: Deployment
metadata:
  name: vllm
  namespace: vllm
spec:
  strategy:
    type: Recreate          # GPU 1개를 두 Pod가 동시에 요청하면 한 쪽은 Pending. RollingUpdate 불가
  template:
    spec:
      enableServiceLinks: false  # Service 이름 vllm과 VLLM_PORT env 충돌 방지 (후술)
      containers:
        - name: vllm
          image: vllm/vllm-openai:v0.19.1
          args:
            - --model
            - Qwen/Qwen2.5-14B-Instruct-AWQ
            - --gpu-memory-utilization
            - "0.9"         # ← 시나리오 1에서 0.5로 변경
            - --max-model-len
            - "4096"        # ← 시나리오 1에서 16384, 시나리오 2에서 131072로 변경
            # 시나리오 3에서 --tensor-parallel-size 2 추가
          resources:
            limits:
              nvidia.com/gpu: "1"
```

| 설정 | 값 | 이유 |
| --- | --- | --- |
| `strategy: Recreate` | Recreate | GPU 1개를 두 Pod가 동시에 요청하면 한 쪽은 Pending. RollingUpdate 불가 |
| `enableServiceLinks: false` | false | Service 이름 `vllm`과 vLLM의 `VLLM_PORT` env 충돌 방지. [후술](#예상치-못한-장애--vllm_port-env-충돌) |
| `startupProbe` | period 10s × threshold 60 = 600s | 모델 로딩 수 분 + cold pull 시간을 고려한 여유값. 실측 결과는 [아래](#정상-기동-로그-확인) 참고 |
| `emptyDir: hf-cache` | 20Gi | HF 모델 weights 다운로드 경로. Pod 재시작 시 재다운로드 |
| `emptyDir: dshm` | Memory, 4Gi | PyTorch shared memory. `/dev/shm` 기본 64MiB는 부족 |

<details markdown="1">
<summary><b>전체 매니페스트 (Namespace + Deployment + Service)</b></summary>

```yaml
# vllm-baseline.yaml
apiVersion: v1
kind: Namespace
metadata:
  name: vllm
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: vllm
  namespace: vllm
spec:
  replicas: 1
  selector:
    matchLabels:
      app: vllm
  strategy:
    type: Recreate
  template:
    metadata:
      labels:
        app: vllm
    spec:
      enableServiceLinks: false
      tolerations:                       # GPU 노드 taint toleration
        - key: nvidia.com/gpu
          operator: Equal
          value: "true"
          effect: NoSchedule
      nodeSelector:                      # NFD 라벨로 GPU 노드에만 스케줄
        nvidia.com/gpu.present: "true"
      containers:
        - name: vllm
          image: vllm/vllm-openai:v0.19.1
          args:
            - --model
            - Qwen/Qwen2.5-14B-Instruct-AWQ
            - --gpu-memory-utilization
            - "0.9"
            - --max-model-len
            - "4096"
            - --host
            - 0.0.0.0
            - --port
            - "8000"
          env:
            - name: HF_HOME              # HF 모델 weights 다운로드 경로
              value: /root/.cache/huggingface
            - name: VLLM_WORKER_MULTIPROC_METHOD
              value: spawn
          ports:
            - name: http
              containerPort: 8000
          resources:
            requests:
              cpu: "2"
              memory: 12Gi
              nvidia.com/gpu: "1"
              ephemeral-storage: 20Gi    # 이미지 9.6GB + weights 9.4GB
            limits:
              nvidia.com/gpu: "1"
              ephemeral-storage: 30Gi
          startupProbe:                  # 모델 로딩 수 분 + cold pull 시간 고려
            httpGet:
              path: /health
              port: http
            periodSeconds: 10
            failureThreshold: 60         # 10s × 60 = 600s 허용
          readinessProbe:
            httpGet:
              path: /health
              port: http
            periodSeconds: 10
            failureThreshold: 3
          volumeMounts:
            - name: hf-cache
              mountPath: /root/.cache/huggingface
            - name: dshm
              mountPath: /dev/shm
      volumes:
        - name: hf-cache
          emptyDir:                      # Pod 재시작 시 weights 재다운로드
            sizeLimit: 20Gi
        - name: dshm
          emptyDir:                      # PyTorch shared memory. 기본 64MiB는 부족
            medium: Memory
            sizeLimit: 4Gi
---
apiVersion: v1
kind: Service
metadata:
  name: vllm                             # 이 이름이 VLLM_PORT env 충돌의 원인
  namespace: vllm
spec:
  type: ClusterIP
  selector:
    app: vllm
  ports:
    - name: http
      port: 8000
      targetPort: http
```

</details>

<br>

# 정상 서빙 Baseline

장애를 재현하기 전에, 정상 상태의 서빙 기준선을 먼저 확보한다. 이후 장애 시나리오의 결과를 해석하는 비교 기준이 된다.

## 배포

```bash
kubectl apply -f vllm-baseline.yaml
```

```
namespace/vllm created
deployment.apps/vllm created
service/vllm created
```

## 예상치 못한 장애 — VLLM_PORT env 충돌

첫 배포에서 Pod가 기동 직후 죽었다. `kubectl logs --previous`로 직전 컨테이너의 로그를 확인하면 다음과 같은 에러가 보인다.

```
(EngineCore pid=81) ValueError: VLLM_PORT 'tcp://10.100.xxx.xx:8000' appears to be a URI.
This may be caused by a Kubernetes service discovery issue,
check the warning in: https://docs.vllm.ai/en/stable/serving/env_vars.html
```

원인은 Kubernetes의 Service 환경 변수 자동 주입(Service Links) 메커니즘에 있다.

Kubernetes는 `enableServiceLinks: true`(기본값)일 때, 같은 namespace의 모든 Service에 대해 환경 변수를 Pod에 주입한다. Pod 내부 환경 변수의 출처와 주입 메커니즘에 대한 상세 내용은 [Kubernetes Application Config — Command, Args, Env]({% post_url 2026-04-05-Kubernetes-Application-Config-01-Command-Args-Env %})를 참고한다. Service 이름이 `vllm`이면 다음 변수들이 생긴다.

| 주입되는 환경 변수 | 값 예시 |
| --- | --- |
| `VLLM_PORT` | `tcp://10.100.xxx.xx:8000` |
| `VLLM_SERVICE_HOST` | `10.100.xxx.xx` |
| `VLLM_SERVICE_PORT` | `8000` |
| `VLLM_PORT_8000_TCP_ADDR` | `10.100.xxx.xx` |

vLLM은 자체적으로 `VLLM_PORT` 환경 변수를 **포트 번호**(정수)로 읽는다. 그런데 K8s가 주입한 값은 `tcp://10.100.xxx.xx:8000`이라는 URI 문자열이다. vLLM이 이 값을 정수로 파싱하려다 실패하고, `ValueError`를 던지며 Engine core 초기화에 실패한 것이다.

<details markdown="1">
<summary><b>vLLM 기동 로그 — VLLM_PORT 충돌 전문</b></summary>

```
WARNING 04-19 10:45:24 [argparse_utils.py:191] With `vllm serve`, you should provide
the model as a positional argument or in a config file instead of via the `--model` option.
(APIServer pid=1) INFO 04-19 10:45:24 [utils.py:233] non-default args:
{'model_tag': 'Qwen/Qwen2.5-14B-Instruct-AWQ', 'host': '0.0.0.0',
 'model': 'Qwen/Qwen2.5-14B-Instruct-AWQ', 'max_model_len': 4096}
(APIServer pid=1) WARNING 04-19 10:45:24 [envs.py:1744] Unknown vLLM environment
variable detected: VLLM_PORT_8000_TCP_PORT
(APIServer pid=1) WARNING 04-19 10:45:24 [envs.py:1744] Unknown vLLM environment
variable detected: VLLM_SERVICE_HOST
(APIServer pid=1) WARNING 04-19 10:45:24 [envs.py:1744] Unknown vLLM environment
variable detected: VLLM_PORT_8000_TCP_PROTO
(APIServer pid=1) WARNING 04-19 10:45:24 [envs.py:1744] Unknown vLLM environment
variable detected: VLLM_SERVICE_PORT_HTTP
(APIServer pid=1) WARNING 04-19 10:45:24 [envs.py:1744] Unknown vLLM environment
variable detected: VLLM_SERVICE_PORT
(APIServer pid=1) WARNING 04-19 10:45:24 [envs.py:1744] Unknown vLLM environment
variable detected: VLLM_PORT_8000_TCP
(APIServer pid=1) WARNING 04-19 10:45:24 [envs.py:1744] Unknown vLLM environment
variable detected: VLLM_PORT_8000_TCP_ADDR
...
(EngineCore pid=81) ERROR 04-19 10:45:43 [core.py:1108] EngineCore failed to start.
(EngineCore pid=81) ValueError: VLLM_PORT 'tcp://10.100.xxx.xx:8000' appears to be a URI.
This may be caused by a Kubernetes service discovery issue,
check the warning in: https://docs.vllm.ai/en/stable/serving/env_vars.html
```

</details>

vLLM v0.19.1은 `Unknown vLLM environment variable detected` 경고를 먼저 출력한다. K8s가 주입한 `VLLM_SERVICE_HOST`, `VLLM_PORT_8000_TCP` 등을 감지한 것이다. `VLLM_PORT` 자체는 vLLM이 알고 있는 변수이므로 "Unknown" 경고 대신 바로 파싱을 시도하고, URI를 받아 실패한다.

해결은 Pod spec에 `enableServiceLinks: false` 한 줄을 추가하는 것이다. 위 baseline 매니페스트에는 이미 반영되어 있다. K8s 1.13부터 존재하는 이 필드의 기본값이 `true`인 것이, **Service 이름과 같은 대문자 prefix의 env를 쓰는 런타임**과 정면충돌하는 구조적 함정이다. vLLM [공식 env_vars 문서](https://docs.vllm.ai/en/latest/configuration/env_vars/)에도 *"please do not name the service as `vllm`"*이라는 경고가 명시되어 있을 정도로, 이미 많은 사람이 밟은 문제다.

> **참고**: 에러 메시지에 포함된 `https://docs.vllm.ai/en/stable/serving/env_vars.html` 링크는 현재 404다. docs 구조 변경으로 경로가 `/en/latest/configuration/env_vars/`로 바뀌었다.

## 정상 기동

`enableServiceLinks: false`를 추가하고 재배포하면 정상적으로 기동한다. 기동 로그에서 핵심 타이밍을 발췌한다.

```
(EngineCore pid=81) INFO 04-19 10:50:01 [default_loader.py:384]
  Loading weights took 71.20 seconds
(EngineCore pid=81) INFO 04-19 10:50:03 [gpu_model_runner.py:4820]
  Model loading took 9.38 GiB memory and 141.542131 seconds
(EngineCore pid=81) INFO 04-19 10:50:43 [gpu_worker.py:436]
  Available KV cache memory: 9.1 GiB
(EngineCore pid=81) INFO 04-19 10:50:43 [kv_cache_utils.py:1319]
  GPU KV cache size: 49,696 tokens
(EngineCore pid=81) INFO 04-19 10:50:43 [kv_cache_utils.py:1324]
  Maximum concurrency for 4,096 tokens per request: 12.13x
```

vLLM의 GPU 메모리 사용 구성이 로그에서 읽힌다. A10G 24 GiB(23,028 MiB) 중 `gpu-memory-utilization=0.9`로 ~20.7 GiB를 예산으로 잡고, 그 안에 weights(9.38 GiB) + KV cache(9.1 GiB) + CUDA graph(0.79 GiB) + overhead가 들어간 것이다.

```
총 VRAM 예산:    23,028 MiB × 0.9 ≈ 20,725 MiB
- Weights:       9.38 GiB  (AWQ 4-bit, 14B params)
- CUDA graph:    0.79 GiB
- KV cache:      9.1  GiB  → 49,696 tokens
- Overhead:      ~1.5 GiB
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
실측 점유:       20,762 MiB / 23,028 MiB
```

`max-model-len=4096` 기준 12.13x concurrency는, 4,096 토큰짜리 요청을 **동시에 약 12개** 처리할 수 있는 KV cache 용량이라는 뜻이다.

## API 검증

vLLM이 실제로 추론 요청을 처리할 수 있는지 확인한다. health check → 모델 목록 → chat completion 순서로 검증하며, 정상이면 모델이 응답을 생성하고 `finish_reason: stop`으로 끝난다.

```bash
# port-forward 후 API 검증
kubectl -n vllm port-forward svc/vllm 8000:8000 &

# health check
curl -sS http://localhost:8000/health
# HTTP 200

# 모델 목록
curl -sS http://localhost:8000/v1/models | jq '.data[0].id'
# "Qwen/Qwen2.5-14B-Instruct-AWQ"

# 실제 추론 요청
curl -sS -X POST http://localhost:8000/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{"model":"Qwen/Qwen2.5-14B-Instruct-AWQ",
       "messages":[{"role":"user","content":"한 문장으로 자기소개 해줘"}],
       "max_tokens":128,"temperature":0.7}'
```

```json
{
  "choices": [{
    "message": {
      "content": "저는 Alibaba Cloud에서 만든 대화형 인공지능 어시스턴트 Qwen입니다."
    },
    "finish_reason": "stop"
  }],
  "usage": {"prompt_tokens": 38, "completion_tokens": 23, "total_tokens": 61}
}
```

## nvidia-smi

vLLM이 GPU 메모리를 실제로 얼마나 점유했는지 확인한다. vLLM Pod가 배치된 노드의 dcgm-exporter Pod에서 `nvidia-smi`를 실행하면, `gpu-memory-utilization=0.9` 설정에 부합하는 점유량을 볼 수 있다.

```bash
# dcgm-exporter Pod에서 nvidia-smi 실행
DCGM_POD=$(kubectl -n gpu-operator get pod -l app=nvidia-dcgm-exporter \
  --field-selector spec.nodeName=$(kubectl -n vllm get pod -l app=vllm \
    -o jsonpath='{.items[0].spec.nodeName}') -o jsonpath='{.items[0].metadata.name}')
kubectl -n gpu-operator exec "$DCGM_POD" -- nvidia-smi
```

```
+-----------------------------------------------------------------------------------------+
| NVIDIA-SMI 580.126.09             Driver Version: 580.126.09     CUDA Version: 13.0     |
+-----------------------------------------+------------------------+----------------------+
| GPU  Name                 Persistence-M | Bus-Id          Disp.A | Volatile Uncorr. ECC |
|   0  NVIDIA A10G                    Off |   00000000:00:1E.0 Off |                    0 |
|  0%   38C    P0             94W /  300W |   20762MiB /  23028MiB |      0%      Default |
+-----------------------------------------+------------------------+----------------------+
```

20,762 MiB / 23,028 MiB — 위 메모리 구성과 일치한다.

## Baseline 요약

| 항목 | Baseline 값 |
| --- | --- |
| 모델 | Qwen/Qwen2.5-14B-Instruct-AWQ (AWQ 4-bit) |
| vLLM 이미지 | `vllm/vllm-openai:v0.19.1` |
| Weights 로딩 | **71.20s**, 9.38 GiB |
| Model 총 로딩 | **141.54s** (weights + torch.compile 26s + warmup) |
| KV cache | **9.1 GiB**, 49,696 tokens |
| GPU 메모리 | **20,762 / 23,028 MiB** |
| `/v1/chat/completions` | 정상 응답 (38 → 23 tokens, finish=stop) |

<br>

# 장애 재현

Baseline이 확보된 상태에서, vLLM 기동 파라미터를 의도적으로 잘못 설정해 장애를 재현한다. 3가지 시나리오 모두 baseline 매니페스트에서 `args` 부분만 변경한 Deployment를 apply하는 방식이다.

## 시나리오 1: KV cache 부족

### 주입

`gpu-memory-utilization`을 0.9 → **0.5**로 낮추고, `max-model-len`을 4096 → **16384**로 높인다. VRAM 예산을 줄이면서 요구량은 늘린 것이다.

```yaml
# baseline 대비 변경점
args:
  - --gpu-memory-utilization
  - "0.5"       # 0.9 → 0.5
  - --max-model-len
  - "16384"     # 4096 → 16384
```

```bash
kubectl apply -f vllm-c6b-1-kv-shortage.yaml
```

### 결과

Pod가 CrashLoopBackOff에 빠진다. `kubectl logs --previous`로 직전 컨테이너의 에러를 확인한다.

```bash
kubectl -n vllm logs deploy/vllm --previous --tail=20
```

```
(EngineCore pid=81) INFO 04-19 10:59:54 [gpu_worker.py:436]
  Available KV cache memory: 0.18 GiB
(EngineCore pid=81) ERROR 04-19 10:59:54 [core.py:1108] EngineCore failed to start.
(EngineCore pid=81) ValueError: To serve at least one request with the models's max seq len
  (16384), (3.0 GiB KV cache is needed, which is larger than the available KV cache memory
  (0.18 GiB). Based on the available memory, the estimated maximum model length is 976.
  Try increasing `gpu_memory_utilization` or decreasing `max_model_len` when initializing
  the engine.
```

**실패 지점**: weights 로딩 후 KV cache 할당 단계. weights(9.38 GiB)는 정상 로드되었지만, `util=0.5`로 줄인 VRAM 예산에서 weights + CUDA graph + overhead를 빼면 KV에 남은 여유가 **0.18 GiB**밖에 안 된다. `max-model-len=16384`의 단일 요청에 필요한 KV는 3.0 GiB이므로, 기동 자체를 거부한 것이다.

```
총 VRAM 예산:    23,028 MiB × 0.5 ≈ 11,514 MiB  (baseline 대비 절반)
- Weights:       9.38 GiB  (AWQ 4-bit, baseline과 동일 — 모델은 안 바뀜)
- CUDA graph:    0.79 GiB  (baseline과 동일)
- Overhead:      ~0.9 GiB
- KV cache:      0.18 GiB  ← 예산 대부분을 weights가 소진
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
필요한 KV:       3.0  GiB  (max-model-len=16384 기준 단일 요청)
부족분:          2.82 GiB  → 기동 거부
```

vLLM이 `estimated maximum model length is 976`이라는 튜닝 힌트를 에러 메시지에 포함하고 있다. 0.18 GiB KV로 처리 가능한 최대 시퀀스 길이가 976 토큰이라는 뜻이다. Baseline과 비교하면 예산 구성의 차이가 명확하다.

```
Baseline (util=0.9):  VRAM 예산 20.7 GiB → KV  9.1  GiB → 49,696 tokens
시나리오 1 (util=0.5):  VRAM 예산 11.2 GiB → KV  0.18 GiB → est. 976 tokens
                                               ↑ weights 9.38 GiB는 그대로인데 예산만 줄어 KV 붕괴
```

## 시나리오 2: max-model-len > context window

### 주입

`max-model-len`을 모델의 `max_position_embeddings`(32,768)을 크게 초과하는 **131,072**로 설정한다.

```yaml
# baseline 대비 변경점
args:
  - --max-model-len
  - "131072"    # 4096 → 131072
```

```bash
kubectl apply -f vllm-c6b-2-max-model-len-over.yaml
```

### 결과

이번에는 weights 로딩도 하지 않고 **30초 이내에 즉시 실패**한다.

```bash
kubectl -n vllm logs deploy/vllm --previous --tail=10
```

```
(APIServer pid=1) pydantic_core._pydantic_core.ValidationError:
  1 validation error for ModelConfig
  Value error, User-specified max_model_len (131072) is greater than the derived
  max_model_len (max_position_embeddings=32768.0 or model_max_length=None in model's
  config.json). To allow overriding this maximum, set the env var
  VLLM_ALLOW_LONG_MAX_MODEL_LEN=1. VLLM_ALLOW_LONG_MAX_MODEL_LEN must be used with
  extreme caution. If the model uses relative position encoding (RoPE), positions
  exceeding derived_max_model_len lead to nan.
```

**실패 지점**: config 검증 단계 (pydantic validation). vLLM v0.19.1은 모델의 `config.json`에서 `max_position_embeddings=32768`을 읽고, 사용자가 지정한 `max_model_len=131072`가 이를 초과하면 weights 로딩 전에 즉시 reject한다.

로그에서 이를 직접 확인할 수 있다. 시나리오 1의 로그에는 `(EngineCore pid=81)`로 시작하는 라인이 대량으로 출력되었다 — weights 다운로드, 모델 로딩, KV cache 계산, CUDA graph 프로파일링이 모두 EngineCore 프로세스 안에서 수행되기 때문이다. 반면 시나리오 2의 로그에는 **`(EngineCore pid=...)` 라인이 단 하나도 없다**. `(APIServer pid=1)`만 출력되고, `create_model_config()` → pydantic `ModelConfig` 생성에서 곧바로 `ValidationError`가 터진다. EngineCore 프로세스가 spawn되기 전에 죽은 것이다.

```
시나리오 2 실행 타임라인 (실측 로그 타임스탬프)

11:03:50  컨테이너 시작 → Python 프로세스 기동, CLI args 파싱
          non-default args: {max_model_len: 131072}
11:03:59  Resolved architecture: Qwen2ForCausalLM
          → pydantic ModelConfig validator: 131072 > 32768 → ValidationError
          → Python 프로세스 exit 1 → CrashLoopBackOff

전체 수명: 9초
```

이 과정에서 **일어나지 않은 것**이 중요하다. 시나리오 1에서 수행되었던 다음 단계들이 전부 스킵되었다.

- EngineCore 프로세스 spawn
- ~71s 걸리는 weights 다운로드/로딩
- `torch.cuda.set_device` GPU context 초기화
- KV cache 블록 플래닝
- GPU VRAM 할당 시도

GPU를 *스치지도 못하고* 죽은 것이다. `nvidia-smi`에서도 VRAM 점유 변화가 없고, `DCGM_FI_DEV_FB_USED` 그래프는 평평하다. 증상은 Pod status(CrashLoopBackOff) + Python traceback뿐이다.

`VLLM_ALLOW_LONG_MAX_MODEL_LEN=1` 환경 변수로 이 검증을 우회할 수 있지만, 에러 메시지가 경고하듯("If the model uses relative position encoding (RoPE), positions
  exceeding derived_max_model_len lead to nan.") RoPE 기반 모델에서는 위치 인코딩 범위를 벗어나 NaN이 발생할 수 있다. 운영 환경에서의 우회는 금기다.

## 시나리오 3: TP 불일치

### 주입

`tensor-parallel-size`를 **2**로 설정한다. 하지만 Pod에 할당된 GPU는 1개다.

```yaml
# baseline 대비 변경점
args:
  - --tensor-parallel-size
  - "2"         # 추가
```

```bash
kubectl apply -f vllm-c6b-3-tp-mismatch.yaml
```

### 결과

이것도 config 검증 단계에서 즉시 실패한다.

```bash
kubectl -n vllm logs deploy/vllm --previous --tail=10
```

```
(APIServer pid=1) pydantic_core._pydantic_core.ValidationError:
  1 validation error for ParallelConfig
  Value error, World size (2) is larger than the number of available GPUs (1) in this
  node. If this is intentional and you are using:
  - ray, set '--distributed-executor-backend ray'.
  - multiprocessing, set '--nnodes' appropriately.
```

**실패 지점**: config 검증 단계 (pydantic validation). `tensor-parallel-size=2`는 2개 GPU가 필요한데, Pod의 `nvidia.com/gpu` limits가 1이므로 컨테이너에 GPU가 1개만 보인다. vLLM이 이를 감지하고 즉시 실패한다.

에러 메시지에 Ray 또는 multi-node 설정으로의 에스케이프 경로가 포함되어 있지만, 단일 노드에 GPU 1개인 환경에서는 TP=2가 물리적으로 불가능하다.

## 예상 vs 실측

| # | 시나리오 | 실패 지점 | 실패 시간 | 핵심 에러 메시지 |
| --- | --- | --- | --- | --- |
| 0 | VLLM_PORT env 충돌 | Engine core init | ~10s | `VLLM_PORT 'tcp://...' appears to be a URI` |
| 1 | KV cache 부족 | KV 할당 (weights 로딩 후) | ~2-3min | `3.0 GiB KV needed, 0.18 GiB available` |
| 2 | context window 초과 | config 검증 (weights 로딩 전) | <30s | `max_model_len (131072) > max_position_embeddings (32768)` |
| 3 | TP 불일치 | config 검증 (weights 로딩 전) | <30s | `World size (2) > available GPUs (1)` |

실패 시간의 차이가 운영 관점에서 중요하다. 시나리오 2, 3은 config 검증에서 **즉시** 실패하므로 CrashLoopBackOff가 빠르게 나타나지만, 시나리오 1은 weights 로딩(71s)까지 성공한 뒤 KV 할당에서 실패하므로 **2~3분 후**에야 장애가 드러난다.

## `max-model-len`의 두 개의 벽

시나리오 1과 2의 실패 경로가 다른 이유를 이해하려면, `max-model-len` 설정이 **두 개의 독립된 벽**을 차례로 넘어야 한다는 것을 알아야 한다.

| 벽 | 단계 | 시점 | 원리 | 실패 예시 |
| --- | --- | --- | --- | --- |
| **#1 Config 벽** | pydantic validation | 프로세스 시작 ~10s (weights 로딩 전) | `max_model_len ≤ max_position_embeddings` 강제. RoPE가 학습된 범위 밖에서 NaN을 생성하므로 하드 블록 | 시나리오 2 (131072 > 32768) |
| **#2 KV VRAM 벽** | 엔진 초기화 | weights 로딩 후 (~71s 지점) | `KV_required = f(max_model_len, layers, heads, dtype)`를 `VRAM × util − weights`와 비교. 부족하면 `estimated max_model_len=N` 힌트 제공 | 시나리오 1 (util=0.5 → KV 0.18 GiB 부족) |

사용자가 `max-model-len`을 올리면 **먼저 #1에 걸린다**. #1을 통과해야 #2가 검증된다. 131072는 #1에서 즉사했고, 16384는 #1은 통과(32768 이하)했지만 #2에서 VRAM 부족으로 죽었다.

```
131072  ──→ #1 Config 벽에서 즉사 (9s)        GPU 접근 없음
16384   ──→ #1 통과 → #2 KV VRAM 벽에서 실패 (2~3min)  GPU weights 로딩까지 진행
4096    ──→ #1 통과 → #2 통과 → 정상 서빙     GPU 20,762 MiB 점유
```

이 구분이 운영상 중요한 이유가 세 가지 있다.

1. **디버깅 시그널이 다르다**. #1은 Python traceback에 pydantic 필드명이 명확히 나오므로 "config 문제"로 바로 식별된다. #2는 vLLM 엔진 초기화 로그 안에 파묻혀 있고, `estimated max_model_len=N` 힌트를 grep해야 원인이 보인다.
2. **실패까지 걸리는 시간이 다르다**. #1은 <30s fail-fast, #2는 weights 로딩(14B AWQ 기준 71s)을 다 기다려야 한다. 파라미터 튜닝 반복 속도에 직결된다.
3. **우회 플래그가 #1에만 존재한다**. `VLLM_ALLOW_LONG_MAX_MODEL_LEN=1`은 #1 벽을 건너뛰게 하지만, 건너뛰면 RoPE가 학습 범위 밖의 position을 만나 NaN → 쓰레기 출력이 된다. 조용히 망가지기 때문에 운영 환경에서의 우회는 금기다.

어차피 실패할 설정이라면 빨리 죽는 편이 낫다. #1의 config 검증은 `max_position_embeddings`라는 모델 메타데이터만 읽으면 되기 때문에, weights 로딩 없이도 즉시 판단할 수 있고 실제로 그렇게 구현되어 있다. 반면 #2의 KV 여유 검증은 `VRAM × util − 실제 weights 크기`를 계산해야 하는데, 양자화 방식(AWQ, GPTQ, FP16 등)에 따라 weights가 GPU에 올라간 뒤의 실제 점유 크기가 달라지므로 weights를 로딩하기 전에는 정확한 계산이 불가능하다. #2가 느린 것은 설계 미비가 아니라 **정보 의존성의 차이**다. #1은 config.json 한 줄로 판단할 수 있지만, #2는 GPU에 weights를 실제로 올려봐야 답이 나온다.

<br>

# 디버깅 경로

[이전 글]({% post_url 2026-04-09-Kubernetes-EKS-GPU-TroubleShooting-03-01-GPU-Pod-Pending %})에서는 Pod → Node → DaemonSet → ClusterPolicy → 노드 내부 순으로 **인프라 층**을 좁혀갔다. 이번에는 GPU 인프라는 정상이고, **앱 프로세스가 기동 중 죽는** 패턴이다. 디버깅 funnel이 다르다.

> **"Pod STATUS → `describe` Events → `logs --previous`"** 순서가 vLLM 같은 Python 서빙 프로세스 트러블슈팅의 정석이다.

## 1단계: Pod STATUS 확인

```bash
kubectl -n vllm get pod -l app=vllm
```

```
NAME                    READY   STATUS             RESTARTS      AGE
vllm-xxxxxxxxx-xxxxx    0/1     CrashLoopBackOff   5 (30s ago)   8m
```

`CrashLoopBackOff` — 컨테이너가 반복적으로 죽고 있다. `RESTARTS` 수가 증가하면서 backoff 시간이 늘어나는 패턴이다.

## 2단계: describe Events — 2차 신호 확인

```bash
kubectl -n vllm describe pod -l app=vllm | tail -15
```

```
Events:
  Type     Reason     Age                From     Message
  ----     ------     ----               ----     -------
  Warning  Unhealthy  3m (x8 over 8m)    kubelet  Startup probe failed:
                                                  Get "http://10.244.x.x:8000/health":
                                                  dial tcp 10.244.x.x:8000: connect refused
  Warning  BackOff    30s (x12 over 7m)  kubelet  Back-off restarting failed container
```

`Startup probe failed: connect refused`를 보면 probe 설정이 잘못된 것처럼 보인다. 하지만 **이건 2차 신호다.** `connect refused`의 의미는 "8000 포트가 열린 적이 없다" — 즉 **vLLM 프로세스가 이미 죽어서 HTTP 서버가 시작되지 못한 것**이다. probe `periodSeconds`나 `failureThreshold`를 아무리 늘려도 해결되지 않는다.

## 3단계: logs --previous — 근본 원인

```bash
kubectl -n vllm logs deploy/vllm --previous --tail=500
```

현재 컨테이너는 재시작 중(아직 기동 안 됐거나 이미 죽은 상태)이므로, `--previous` 플래그로 **직전에 죽은 컨테이너**의 로그를 봐야 한다. vLLM이 던지는 `ValueError`/`ValidationError`는 이 로그에만 존재한다.

3개 시나리오 모두 이 한 줄에서 근본 원인이 드러났다.

| 시나리오 | `logs --previous`에서 보이는 근본 원인 |
| --- | --- |
| KV cache 부족 | `ValueError: ... 3.0 GiB KV cache needed ... 0.18 GiB available` |
| context window 초과 | `Value error, ... max_model_len (131072) > max_position_embeddings (32768)` |
| TP 불일치 | `Value error, World size (2) > available GPUs (1)` |

개인적으로 이번 트러블슈팅 실습을 구성하면서 vLLM을 처음 써봤는데, 에러 메시지가 예상보다 훨씬 자세했다. 단순히 "실패했다"가 아니라, KV 부족 시 `estimated maximum model length is 976`이라는 튜닝 힌트를 주고, context window 초과 시 우회 플래그(`VLLM_ALLOW_LONG_MAX_MODEL_LEN=1`)와 그 위험성(RoPE NaN)을 함께 알려주고, TP 불일치 시 Ray나 multi-node라는 대안 경로까지 제시한다. **에러 메시지 자체가 디버깅 가이드** 역할을 하고 있어서, stack trace만 보고 넘기지 않고 메시지 본문을 끝까지 읽는 습관이 중요하다는 것을 체감했다.

## 4단계: 인프라 배제 확인

앱 층 문제임이 확인되면 GPU 인프라가 정상인지 추가 확인하여 완전히 배제한다.

```bash
# dcgm-exporter Pod에서 nvidia-smi로 GPU 상태 확인
kubectl -n gpu-operator exec "$DCGM_POD" -- nvidia-smi -L
```

```
GPU 0: NVIDIA A10G (UUID: GPU-xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx)
```

GPU는 정상이다. 인프라 문제가 아니라 **vLLM 파라미터 설정 오류**가 원인임이 확정된다.

<br>

# 해결

## baseline 매니페스트 rollback

3개 시나리오 모두 동일한 해결 방법이다. 정상 파라미터가 들어간 baseline 매니페스트를 다시 apply한다.

```bash
kubectl apply -f vllm-baseline.yaml
```

Deployment의 `strategy: Recreate` 덕에 기존 Pod가 먼저 종료되고 새 Pod가 생성된다. 이미지는 노드에 캐시되어 있어 pull이 생략(`IfNotPresent`)되지만, HF 모델 weights는 emptyDir이 새로 할당되므로 재다운로드(~71s)된다.

## 복구 검증

```bash
# health check
curl -sS http://localhost:8000/health
# HTTP 200

# 추론 요청
curl -sS -X POST http://localhost:8000/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{"model":"Qwen/Qwen2.5-14B-Instruct-AWQ",
       "messages":[{"role":"user","content":"rollback 검증. OK 라고만 답해"}],
       "max_tokens":16}'
```

```json
{
  "choices": [{
    "message": {"content": "OK"},
    "finish_reason": "stop"
  }],
  "usage": {"prompt_tokens": 40, "completion_tokens": 2, "total_tokens": 42}
}
```

| 항목 | Baseline 값 | 복구 후 값 |
| --- | --- | --- |
| Pod Ready | 1/1 Ready=True | 1/1 Ready=True |
| `/health` | HTTP 200 | HTTP 200 |
| `/v1/chat/completions` | 정상 응답 (finish=stop) | `"OK"` (40 → 2 tokens, finish=stop) |

Baseline과 동일한 정상 상태로 복구되었다.

<br>

# 실무 운영 주의 사항

## 운영 함정 3가지

### 1. Service 이름과 앱 env 충돌

Kubernetes의 `enableServiceLinks: true`(기본값)가 Service 이름 기반으로 환경 변수를 주입한다. Service 이름이 `vllm`이면 `VLLM_PORT=tcp://...`가 주입되고, vLLM 자체의 `VLLM_PORT` 환경 변수와 충돌한다.

이 함정은 vLLM에만 해당하는 것이 아니다. **Service 이름의 대문자 변환이 앱의 환경 변수와 겹치는 모든 경우**에 발생할 수 있다. 예를 들어 Service 이름이 `redis`이면 `REDIS_PORT`가 주입되는데, Redis 클라이언트가 `REDIS_PORT`를 포트 번호로 읽으려 하면 동일한 충돌이 발생한다.

방어 방법은 Pod spec에 `enableServiceLinks: false`를 기본으로 넣는 것이다. Helm base나 Kustomize base에 고정해 두면 된다.

### 2. connect refused를 probe 문제로 오해

`Startup probe failed: connect refused`를 보고 probe `periodSeconds`나 `failureThreshold`를 늘리는 것은 9할 오진이다. `connect refused`는 **프로세스가 이미 죽어 포트가 열린 적 없다**는 신호다. probe 설정이 아니라 **`kubectl logs --previous`**를 먼저 확인해야 한다.

### 3. weights 로딩 성공 ≠ 서빙 성공

weights가 GPU에 올라갔다고 서빙이 되는 것이 아니다. KV cache 할당과 config 검증(`max_position_embeddings`, TP 수)까지 통과해야 비로소 서빙이 시작된다. 시나리오 1에서 weights 9.38 GiB는 정상 로드되었지만 KV 할당에서 죽었고, 시나리오 2는 weights 로딩 자체에 도달하지도 못했다.

양자화(AWQ 4-bit)로 weights를 28 GiB → 9.38 GiB로 줄여 "올라가는" 단계를 쉽게 만들 수 있지만, KV cache 메모리와 모델 config의 제약은 양자화와 무관하다. A10G 24 GiB 같은 작은 GPU에서는 `gpu-memory-utilization`과 `max-model-len`의 **메모리 수학을 미리 풀어야** 한다.

"그러면 `gpu-memory-utilization`을 높이고 `max-model-len`을 낮추면 해결 아닌가?"라고 생각할 수 있지만, 두 파라미터는 각각 반대 방향의 리스크를 안고 있다.

- **`gpu-memory-utilization`을 높이면**: 예산은 커지지만 PyTorch CUDA context, 임시 텐서 등을 위한 여유분이 줄어든다. 0.95 이상에서는 기동은 되지만 런타임 피크 시 예측 불가능한 CUDA OOM이 터질 수 있다. 기동 실패보다 운영 중 장애가 더 위험하다.
- **`max-model-len`을 낮추면**: KV 요구량은 줄지만 모델이 처리할 수 있는 최대 토큰 수가 줄어든다. RAG로 긴 문서를 넣거나, 긴 대화 히스토리를 유지해야 하는 서비스라면 4096으로는 부족하다.

실무에서 전형적으로 벌어지는 시나리오가 있다.

1. "RAG 파이프라인에서 context가 잘리니까 `max-model-len`을 올려주세요" → 16384로 올림
2. KV 부족으로 기동 실패 → "`gpu-memory-utilization`도 올리면 되지 않나?" → 0.95로 올림
3. 기동은 되지만 피크 시간에 CUDA OOM → 기동 실패보다 더 위험한 장애
4. "GPU를 더 달거나 모델을 더 작은 걸로 바꿔야..." → 비용/품질 트레이드오프

결국 `util`, `max-model-len`, GPU 수 세 변수가 서로 맞물려 있어서 하나만 조정하면 해결되지 않는다. 이 균형점을 못 찾아서 운영 실수가 나오는 것이고, 검증된 조합을 ConfigMap 매트릭스로 관리해야 하는 이유다.

## vLLM 기동 실패 패턴 분류

| 실패 지점 | 실패 시간 | 대표 에러 | 해법 |
| --- | --- | --- | --- |
| env 충돌 | ~10s | `VLLM_PORT appears to be a URI` | `enableServiceLinks: false` |
| config 검증 | <30s | `max_position_embeddings`, `World size` | 파라미터 수정 |
| KV 할당 | 2~3min | `KV cache needed > available` | `gpu-memory-utilization`↑ 또는 `max-model-len`↓ |

실패 시간의 차이를 알아두면 CrashLoopBackOff가 발생했을 때 원인을 빠르게 좁힐 수 있다. 컨테이너가 **10초 이내에 죽으면** env 충돌이나 config 검증 문제, **2~3분 후에 죽으면** KV 할당 문제를 먼저 의심한다.

## Prometheus alert 예시

이번 글에서 재현한 장애를 사후에 자동으로 감지하기 위한 alert 예시다. vLLM 메트릭 이름을 쓰고 있지만, CrashLoopBackOff 감지나 KV cache 포화 감지는 LLM 서빙 워크로드 전반에 적용 가능한 패턴이다.

```yaml
# vLLM Pod CrashLoopBackOff 감지
- alert: VllmPodCrashLoopBackOff
  expr: |
    kube_pod_container_status_waiting_reason{
      namespace="vllm", reason="CrashLoopBackOff"
    } == 1
  for: 2m
  labels:
    severity: page
  annotations:
    summary: "vLLM Pod {{ $labels.pod }} is in CrashLoopBackOff"
    runbook: "kubectl -n vllm logs deploy/vllm --previous --tail=100"
```

```yaml
# vLLM KV cache 포화 — 서빙 중 OOM 직전 신호
- alert: VllmKvCacheNearFull
  expr: |
    avg_over_time(vllm:kv_cache_usage_perc[5m]) > 0.95
  for: 5m
  labels:
    severity: warning
  annotations:
    summary: "vLLM KV cache usage > 95% for 5 minutes"
    runbook: "max-model-len 감소 또는 gpu-memory-utilization 증가 검토"
```

## 재발 방지

- **Helm/Kustomize base에 `enableServiceLinks: false` 고정**: vLLM뿐 아니라, 환경 변수 이름 충돌이 가능한 모든 워크로드에 기본 적용
- **모델별 파라미터 매트릭스 관리**: `gpu-memory-utilization`, `max-model-len`, `tensor-parallel-size`의 검증된 조합을 ConfigMap으로 관리하여 운영자의 수동 튜닝 실수를 방지
- **HF cache PVC 전환 권장**: 현재 emptyDir은 Pod 재시작마다 9.4 GiB weights를 재다운로드한다. `ReadWriteOnce` PVC(gp3 50 GiB)로 전환하면 2번째 Pod부터 로딩 시간이 71s → ~10s로 단축된다

<br>

# 정리

## 요약

| 시나리오 | 트리거 | 실패 지점 | 핵심 에러 | 해법 |
| --- | --- | --- | --- | --- |
| VLLM_PORT 충돌 | Service 이름 `vllm` + `enableServiceLinks: true` | Engine core init (~10s) | `VLLM_PORT appears to be a URI` | `enableServiceLinks: false` |
| KV cache 부족 | `util=0.5` + `max-model-len=16384` | KV 할당 (~2-3min) | `3.0 GiB needed, 0.18 GiB available` | `gpu-memory-utilization`↑ 또는 `max-model-len`↓ |
| context window 초과 | `max-model-len=131072` | config 검증 (<30s) | `max_position_embeddings=32768` 초과 | `max-model-len` ≤ `max_position_embeddings` |
| TP 불일치 | `tensor-parallel-size=2`, GPU 1개 | config 검증 (<30s) | `World size (2) > available GPUs (1)` | TP ≤ GPU 수 |

## 03-01 vs 03-02 디버깅 경로 비교

| | [03-01: Device Plugin 비활성화]({% post_url 2026-04-09-Kubernetes-EKS-GPU-TroubleShooting-03-01-GPU-Pod-Pending %}) | 03-02: vLLM 기동 실패 (이번 글) |
| --- | --- | --- |
| 장애 층 | **인프라 층** (GPU Operator/Device Plugin) | **앱 층** (vLLM 프로세스) |
| Pod STATUS | Pending | CrashLoopBackOff |
| 디버깅 경로 | Pod → Node → DaemonSet → ClusterPolicy → 노드 내부 | Pod STATUS → describe Events → `logs --previous` |
| 핵심 도구 | `kubectl get/describe` (인프라 리소스 순회) | `kubectl logs --previous` (앱 에러 로그) |
| GPU 인프라 | **비정상** (Allocatable 0, DS 삭제됨) | **정상** (nvidia-smi OK) |

같은 "GPU Pod가 안 뜬다"는 증상이지만, Pod STATUS(`Pending` vs `CrashLoopBackOff`)가 디버깅 경로의 첫 번째 분기점이 된다. Pending이면 인프라 층, CrashLoopBackOff면 앱 층을 먼저 의심한다.

## 다음 단계

이번 글까지 인프라 층(03-01)과 앱 층(03-02) 장애를 각각 재현했다. 다음 글에서는 노드 간 **네트워크 층** 장애를 재현한다. 보안그룹 차단으로 NCCL 통신이 끊기는 시나리오를 다룬다.

<br>
