---
title: "[GenAI] GenAI on K8s: 10.6 - Ch10 실습 코드 분석: time-slicing과 Llama 워크로드"
excerpt: "Ch10 hands-on의 nvidia-ts.yaml, aiml-addons.tf, llama32-deploy.yaml을 읽고 upstream 결함과 수정 포인트를 정리해 보자."
categories:
  - Kubernetes
toc: true
header:
  teaser: /assets/images/blog-Dev.jpg
tags:
  - Kubernetes
  - GenAI
  - GPU
  - NVIDIA
  - Time-Slicing
  - EKS
  - Llama
  - Device-Plugin
  - Bottlerocket
use_math: false
---

*[Kubernetes for Generative AI Solutions(Packt 2025, ISBN 978-1-83620-993-5, 저자 Ashok Srirama / Sukirti Gupta)](https://github.com/PacktPublishing/Kubernetes-for-Generative-AI-Solutions) 10장 hands-on 코드를 바탕으로 합니다*

<br>

[10.4]({% post_url 2026-06-07-Kubernetes-GenAI-on-K8s-10-04-GPU-Sharing-MPS-and-Time-Slicing %})에서 time-slicing 개념을 다뤘다. 이번 글은 Ch10 실습 코드를 읽기 전 단계다 — `terraform apply` 전에 **무엇이 어떻게 연결되는지**, upstream 대비 **무엇을 고쳤는지**를 정리한다. 실제 배포·검증·트러블슈팅은 [10.7]({% post_url 2026-06-07-Kubernetes-GenAI-on-K8s-10-07-Ch10-Lab-Deploy-Time-Slicing-Verification %})에서 이어진다.

# TL;DR

- Ch10 upstream은 overlay(`aiml-addons.tf`, `nvidia-ts.yaml`, `llama32-inf/`)만 있어 self-contained 실행본으로 ch3 토대 + ch9 베이스를 복사해 맞췄다
- `nvidia-ts.yaml`의 `replicas: 10`은 물리 L4 1장을 10 슬롯으로 광고한다. OFF는 `replicas: 1`이 아니라 `sharing` 블록 제거다
- `llama32-deploy.yaml`은 `replicas: 5 × gpu: 2 = 10`으로 슬롯을 정확히 소진한다 — time-slicing 없으면 Pending, OOM은 사용자 책임
- upstream 결함: `deviceListStrategy=envvar`(기본값) × Bottlerocket 비특권 ENV 차단 → env 차단 확인, CDI 미검증, **`volume-mounts` 실측 통과**로 수정

<br>

<br>

# 실습 구조

Ch10은 ch9 베이스 위에 GPU 최적화를 얹는 챕터다. upstream `ch10/`에는 클러스터 토대가 없고 overlay만 있다.

| 레이어 | 파일 | 역할 |
|---|---|---|
| **인프라 overlay** | `aiml-addons.tf` | NVIDIA device plugin(GFD/NFD) + time-slicing 연결 + JupyterHub + DCGM-Exporter |
| | `nvidia-ts.yaml` | `time-slicing-config` ConfigMap — L4 1장 → 10 슬롯 |
| **워크로드** | `llama32-inf/llama32-deploy.yaml` | `replicas 5 × gpu 2 = 10` 추론 Deployment |
| | `llama32-inf/main.py` | FastAPI `/generate` 추론 서버 |
| | `llama32-inf/Dockerfile` | CUDA 런타임 이미지 (upstream `main2.py` 버그 있음) |

실행본 `week04/hands-on/ch10/`은 ch9처럼 **self-contained** — `locals/vpc/providers/versions` + `eks/addons/iam/ecr` + GPU 노드그룹(`eks-gpu-mng`, g6.2xlarge, L4 24GB, `/dev/xvdb` 100GB).

<br>

# upstream 대비 변경점

실습을 위해 hands-on 복사본에 가한 변경과, 진행 중 만난 문제·해결을 정리한다. upstream 원본은 미수정.

| 변경 | 파일 | 이유 |
|---|---|---|
| ch3 토대 + ch9 베이스 복사 | `locals`, `vpc`, `eks`, `addons` 등 | overlay만 있으면 `local.*`·`module.eks` 미해결 |
| `random`·`http` provider 선언 | `versions.tf` | `aiml-addons.tf`의 `random_password`·`data.http` 사용 |
| IRSA 모듈 v5 핀 | `aiml-addons.tf` | v6 수신 시 서브모듈 구조 변경으로 깨짐 방지 |
| **`serviceAccount: my-llama-sa`** | `llama32-deploy.yaml` | upstream 누락 — 없으면 CSI secret mount AccessDenied |
| **`deviceListStrategy: volume-mounts`** | `aiml-addons.tf` | envvar 차단 확인·CDI 미검증 후, volume-mounts 실측 통과로 Bottlerocket 비특권 GPU 주입 보정 |
| kubecost 블록 주석 | `addons.tf` | `clusterId is required`로 apply 실패 |

> GPU 노드 On-Demand(Spot 쿼터 0), `xvdb` 100GB(Ch9 18GB eviction 해결), CPU 인스턴스 서울 가용 타입 등 베이스 변경은 Ch9 실습에서 이미 반영됐다.

<br>

# `nvidia-ts.yaml` — time-slicing ConfigMap

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: time-slicing-config
  namespace: nvidia-device-plugin    # device plugin namespace와 일치해야 함
data:
  any: |-                            # catch-all — 라벨·default 없는 노드에 자동 적용
    version: v1
    flags:
      migStrategy: none              # L4는 MIG 미지원
    sharing:
      timeSlicing:
        resources:
        - name: nvidia.com/gpu
          replicas: 10
```

## `replicas: 10` 시분할 슬롯, 물리 GPU 10개가 아님

device plugin이 이 설정을 읽으면 **물리 GPU 1장을 `nvidia.com/gpu: 10`으로 광고**한다. [10.4]({% post_url 2026-06-07-Kubernetes-GenAI-on-K8s-10-04-GPU-Sharing-MPS-and-Time-Slicing %})에서 다룬 것처럼, 슬롯은 스케줄 토큰이지 VRAM 분할이 아니다.

> **`replicas: 1`은 OFF가 아니다.** time-slicing `replicas` 최소값은 2다. `replicas: 1`로 patch하면 plugin이 `number of replicas must be >= 2`로 크래시하고, 노드 광고량이 **0**으로 떨어진다. OFF(광고 1)는 **`sharing` 블록 자체를 제거**하는 것이다. 자세한 배경은 [time-slicing 적용·검증 — replicas 값 제한]({% post_url 2025-11-22-Kubernetes-GPU-Time-Slicing-3 %}#replicas-값-제한)을, 실습 대조는 [10.7 Step 6]({% post_url 2026-06-07-Kubernetes-GenAI-on-K8s-10-07-Ch10-Lab-Deploy-Time-Slicing-Verification %})을 참조.

## `migStrategy: none`

L4는 MIG 미지원이라 `none`이 유일한 선택이다. MIG 지원 GPU에서 time-slicing과 MIG를 조합할 때만 `single`/`mixed`를 쓴다 — [10.3]({% post_url 2026-06-07-Kubernetes-GenAI-on-K8s-10-03-GPU-Partitioning-MIG %}) 참조.

## ConfigMap과 device plugin 연결

ConfigMap만 apply해도 광고량은 바뀌지 않는다. `aiml-addons.tf`의 **`config.name = time-slicing-config`** 가 plugin이 이 ConfigMap을 마운트하게 하는 고리다. `config.name`을 참조하는데 ConfigMap이 없으면 plugin init이 `FailedMount: configmap "time-slicing-config" not found`로 `Init:0/1`에 멈춘다 — [10.7]({% post_url 2026-06-07-Kubernetes-GenAI-on-K8s-10-07-Ch10-Lab-Deploy-Time-Slicing-Verification %}) Step 2.

## `data.any` 키 — 필수 단어가 아닌 catch-all

`data` 아래 키 이름(`any`)은 ConfigMap 안의 **설정 프로파일 이름**이다. `any`는 NVIDIA device plugin config-manager가 **예약한 catch-all 키**로, 노드에 `nvidia.com/device-plugin.config` 라벨이 없을 때 자동으로 이 키를 골라 적용한다.

| 조건 | 어떤 키가 적용되나 |
|---|---|
| 노드 라벨 `nvidia.com/device-plugin.config=<키>` 있음 | ConfigMap `data.<키>` |
| helm `config.default=<키>` 지정 | 라벨 없는 노드에 `data.<키>` |
| **라벨·default 둘 다 없음** | **`data.any`** (없으면 time-slicing 미적용 → 광고 1) |

키 이름을 `l4-config`처럼 바꿔도 된다. 다만 그때는 노드 라벨 `nvidia.com/device-plugin.config=l4-config`를 붙이거나, helm values에 `config.default: l4-config`를 지정해야 config-manager가 그 키를 찾는다. **이 실습은 라벨·default 없이 GPU 노드 1대만 쓰므로 `any`가 맞고, 다른 이름만 쓰면 광고가 1에 머문다.**

<br>

# `aiml-addons.tf` — device plugin + DCGM

## device plugin 핵심 설정

```yaml
# aiml-addons.tf nvidia_device_plugin_helm_config values 발췌
gfd:
  enabled: true                      # GPU Feature Discovery — 모델·메모리·replica 라벨
nfd:
  worker:
    tolerations:                     # GPU taint 노드에서 NFD worker가 뜨도록
      - key: nvidia.com/gpu
        operator: Exists
        effect: NoSchedule
deviceListStrategy: volume-mounts   # ← [추가] env 차단 환경에서 mount 채널 사용
config:
  name: time-slicing-config         # ← nvidia-ts.yaml 연결
```

NFD(Node Feature Discovery)는 노드에 GPU가 있는지 같은 **일반 하드웨어 특성**을 라벨로 붙이고, GFD(GPU Feature Discovery)는 그 위에서 **GPU 모델·메모리·time-slicing replica 수** 같은 세부 스펙을 추가로 라벨링한다. NFD가 "GPU 노드다"를 알리면 device plugin·DCGM DaemonSet이 그 노드에만 배치되고, GFD 라벨은 워크로드가 L4 노드만 골라 스케줄할 때 쓴다.

| 컴포넌트 | 라벨링 대상 | 예 |
|---|---|---|
| NFD | GPU 존재 여부, CPU 특성 | `nvidia.com/gpu.present=true` |
| GFD | GPU 세부 사양 | `nvidia.com/gpu.product=NVIDIA-L4`, time-slicing replica 수 |

## `deviceListStrategy: volume-mounts` — upstream 결함 보정

device plugin이 kubelet `Allocate()` 응답으로 "이 컨테이너에 이 GPU를 줘"라고 전달하는 건 세 전략 모두 같다. 다른 건 **그 정보를 어떤 형태로 넘기고, 누가 `/dev/nvidia*`와 드라이버 라이브러리 주입을 실행하느냐**다. OCI hook vs runtime-native(CDI) 패러다임 차이는 [컨테이너 장치 주입: OCI Runtime Hook과 CDI]({% post_url 2026-02-02-CS-Container-Device-Injection %})에서 다뤘다.

| 전략 | device plugin이 넘기는 것 | 누가 주입 실행 | 분류 |
|---|---|---|---|
| `envvar` | `NVIDIA_VISIBLE_DEVICES=<uuid>` 환경변수 | nvidia-container-runtime OCI hook → nvidia-container-cli | hook |
| **`volume-mounts`** | `/var/run/nvidia-container-devices/<uuid>` 마운트 엔트리 | 같은 OCI hook이 마운트 경로 basename을 읽어 주입 | hook |
| `cdi` | CDI device 이름(`nvidia.com/gpu=<uuid>`) / 어노테이션 | containerd(`enable_cdi=true`)가 `/etc/cdi/nvidia.json` 스펙을 OCI spec에 직접 병합 | runtime-native |

### envvar vs volume-mounts — 같은 hook, 입력 채널만 다름

둘 다 `nvidia-container-runtime`의 prestart/createContainer hook → `nvidia-container-cli`가 실제 주입을 한다(legacy 방식). 차이는 hook이 "어떤 GPU를 넣을지"를 **어디서 읽느냐**뿐이다.

- **envvar** → 컨테이너 환경변수에서 읽음
- **volume-mounts** → `/var/run/nvidia-container-devices/` 마운트 경로의 basename에서 읽음

### `/var/run/nvidia-container-devices/` vs `/dev/nvidia*`

혼동하기 쉬운 두 경로를 구분해야 한다.

| 경로 | 역할 |
|---|---|
| `/var/run/nvidia-container-devices/<uuid>` | device plugin Allocate가 컨테이너 spec에 넣는 **요청 신호용 빈 마운트**. 경로 basename의 uuid가 "이 GPU를 달라"는 신호 |
| `/dev/nvidia*` | libnvidia-container hook이 주입을 **완료한 뒤** 컨테이너 안에 실제로 나타나는 **장치 노드** |

volume-mounts 전략에서 plugin이 `/var/run/.../<uuid>` 마운트만 추가해 두면, OCI hook(`nvidia-container-cli`)이 그 uuid를 읽고 `/dev/nvidia0`, 드라이버 라이브러리 등을 주입한다. smoke test에서 `ls /dev/nvidia0`로 확인하는 게 **주입 성공**의 증거다. `/var/run/...` 자체는 장치 파일이 아니다.

이 메커니즘은 Bottlerocket 특유 기능이 아니라 **libnvidia-container의 범용 volume-mounts 채널**이다. `/dev`를 숨기는 게 아니라, env 대신 mount 채널로 GPU 요청을 받도록 강제하는 것이다. 이번 실습 노드(Bottlerocket)는 `config.toml`에서 env 채널만 비특권에 막아 두었기 때문에 mount 채널로 바꿔야 했을 뿐이다.

Bottlerocket 노드 `config.toml`은 입력 채널별로 신뢰도를 다르게 본다:

```toml
accept-nvidia-visible-devices-envvar-when-unprivileged = false   # env: 비특권이면 무시
accept-nvidia-visible-devices-as-volume-mounts        = true     # mount: 허용
```

env는 파드 스펙에 누구나 `NVIDIA_VISIBLE_DEVICES=all`을 적어 GPU를 가로챌 수 있는 **자가 주장(self-assertion) 채널**이라 비특권에서 차단한다. mount 채널은 (관례상) device plugin Allocate가 세팅하는 경로로 취급해 허용한다. 같은 hook인데 입력만 바꾸면 비특권 파드도 주입받는다.

### CDI — hook이 아니라 선언적 스펙

CDI는 nvidia-container-runtime wrapper/hook 없이도 동작하는 vendor-neutral 표준이다. `/etc/cdi/nvidia.json`에 "이 device는 이 `/dev/nvidia*` + 이 드라이버 라이브러리 마운트"를 선언하고, containerd 1.7+가 `enable_cdi=true`면 런타임이 스펙을 OCI spec에 직접 병합한다. "런타임이 매번 계산"(hook) → "스펙에 적힌 대로 적용"(declarative)로 패러다임이 바뀐다.

### 이번 실습에서 검증한 것과 선택 근거

| 전략 | 실습 검증 | 결과 |
|---|---|---|
| `envvar` | 비특권 cuda 파드 gpu:1 + SYS_ADMIN 없음 | **차단 확정** — `/dev/nvidia*` 없음, `cuda=False` |
| `cdi` | `deviceListStrategy=cdi` 직접 테스트 | **미검증** — 노드에 CDI 인프라(`enable_cdi=true`, `/etc/cdi/nvidia.json`, nvidia-cdi 런타임)가 있어 동작했을 가능성은 높지만, 이번 세션에서 확인하지 않음 |
| **`volume-mounts`** | 비특권 cuda 파드 gpu:1 smoke test | **실측 통과** — `nvidia-smi`, `/dev/nvidia0` 확인. 노드 `mode=legacy`와도 정합 |

정확히는 **env는 막혔고, CDI는 파지 않았고, 확실하게 검증된 volume-mounts로 갔다.** upstream 기본값 `envvar` 환경(Bottlerocket은 env 채널만 비특권 차단)에서는 device plugin·GFD·DCGM 같은 인프라 파드(`SYS_ADMIN` capability)만 GPU를 보고, llama 같은 비특권 워크로드는 `cuda.is_available()=False`가 된다.

> llama에 `SYS_ADMIN`을 주면 동작은 하지만, Bottlerocket이 일부러 막은 격리 우회 구멍을 다시 여는 **보안 안티패턴**이다. 올바른 해법은 plugin이 스케줄러가 할당한 GPU만 안전한 채널로 건네주게 하는 것 — 이번에는 `volume-mounts`. 진단·검증 전체는 [10.7 Step 5.5]({% post_url 2026-06-07-Kubernetes-GenAI-on-K8s-10-07-Ch10-Lab-Deploy-Time-Slicing-Verification %}) 참조.

## DCGM-Exporter

```yaml
# helm_release dcgm_exporter values 발췌
serviceMonitor:
  enabled: false                     # Ch12에서 Prometheus 연동 예정
affinity:
  nodeAffinity:
    requiredDuringSchedulingIgnoredDuringExecution:
      nodeSelectorTerms:
      - matchExpressions:
        - key: nvidia.com/gpu.present
          operator: Exists
tolerations:
- key: CriticalAddonsOnly
  operator: Exists
- key: nvidia.com/gpu
  operator: Exists
  effect: NoSchedule
```

DCGM-Exporter는 GPU 노드에서만 떠야 하므로 `gpu.present` affinity와 GPU taint toleration을 둔다. [10.2]({% post_url 2026-06-07-Kubernetes-GenAI-on-K8s-10-02-GPU-Utilization-and-DCGM %})에서 다룬 DCGM → Prometheus 파이프라인의 첫 hop이다.

<br>

# `llama32-deploy.yaml` — 분할 GPU 소비

```yaml
spec:
  replicas: 5
  template:
    spec:
      tolerations:
      - key: "nvidia.com/gpu"
        operator: "Exists"
        effect: "NoSchedule"
      serviceAccount: my-llama-sa
      containers:
      - image: k8s4genai/my-llama:32
        resources:
          limits:
            nvidia.com/gpu: 2          # time-slicing 슬롯 2개 (물리 GPU 2장 아님)
        env:
        - name: HUGGING_FACE_HUB_TOKEN
          valueFrom:
            secretKeyRef:
              name: hugging-face-secret
              key: token
        volumeMounts:
        - name: aws-sm-secrets
          mountPath: "/mnt/secrets-store"
          readOnly: true
```

## `replicas: 5 × gpu: 2 = 10`

`nvidia-ts.yaml`이 광고한 10 슬롯을 정확히 소진한다.

| 변형 | 결과 |
|---|---|
| `replicas: 5` (기본) | 10 슬롯 = 10 요청, 5 Pod Running |
| `replicas: 6` | 12 요청 > 10 슬롯 → 6번째 Pending |
| time-slicing OFF (광고 1) | `gpu:2`가 1-GPU 노드에 안 맞아 **전부 Pending** |

> **"time-slicing 없으면 노드를 더 만들면 된다"**는 오해와 달리, Pod GPU 요청은 **한 노드 안에서** 충족돼야 한다. 노드 10대를 만들어도 각 노드에 GPU 1장인데 Pod가 `gpu: 2`를 요청하면 여전히 Pending이다.

## 왜 1B, 왜 gpu:2, 왜 5개

| 사실 | 값 | 함의 |
|---|---|---|
| 인스턴스 | g6.2xlarge | 물리 L4 1장, 24GB VRAM |
| 모델 | Llama-3.2-1B | FP16 ~1.8GB VRAM |
| time-slicing | replicas 10 | allocatable 10 |
| Deployment | gpu:2 × 5 Pod | 총 10 슬롯 |
| VRAM 합산 | 1.8GB × 5 = 9GB | 24GB 안에 여유 |

**1B라서 작동한다.** 3B(~6GB)였다면 5×6=30GB > 24GB로 OOM이다. time-slicing은 메모리를 쪼개주지 않는다.

## secret·SA 의존

`meta-llama/Llama-3.2-1B`는 **gated model** — HF 토큰만으로는 부족하고, 모델별 접근 승인이 필요하다. 토큰은 Secrets Manager → SecretProviderClass → K8s Secret 경로로 주입되며, CSI mount는 **`serviceAccount: my-llama-sa`** + Pod Identity association이 있어야 동작한다.

<br>

# `main.py` — 추론 서버

```python
device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
tokenizer = AutoTokenizer.from_pretrained("meta-llama/Llama-3.2-1B")
model = AutoModelForCausalLM.from_pretrained(
    "meta-llama/Llama-3.2-1B", torch_dtype=torch.float16
)
model.to(device)
model.eval()

@app.post("/generate")
async def generate(request: Request):
    prompt = (await request.json()).get('prompt', '')
    inputs = tokenizer(prompt, return_tensors="pt").to(device)
    with torch.no_grad():
        outputs = model.generate(**inputs, max_length=256)
    return {"response": tokenizer.decode(outputs[0], skip_special_tokens=True)}
```

| 코드 | 의미 |
|---|---|
| `from_pretrained` | import 시점에 모델 로드 → gated 403이면 **CrashLoopBackOff** |
| `torch_dtype=float16` | ~2.5GB VRAM (실측 nvidia-smi ~2.5GB/프로세스) |
| `model.eval()` + `no_grad()` | 추론 전용 — gradient 추적 끔 |
| `@app.post("/generate")` | ClusterIP Service 뒤 5 Pod가 시분할 공유 |

> `async`지만 `model.generate()`는 블로킹 연산이라 한 프로세스 안 동시성은 없다. 이 실습은 **복제본 5개**로 동시성을 얻는다. Ch11 vLLM의 continuous batching과 대비해 보면 된다.

<br>

# `Dockerfile` — upstream 버그

```dockerfile
FROM nvidia/cuda:12.6.3-runtime-ubuntu24.04
RUN apt-get install -y python3-pip \
    && pip install torch transformers accelerate sentencepiece fastapi uvicorn
COPY main2.py /app/main.py          # ← 버그: 레포엔 main.py만 있음
ENV PYTHONUNBUFFERED=1
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "80"]
```

실습은 사전 빌드 이미지 `k8s4genai/my-llama:32`(7.7GB)를 쓰므로 당장은 무관하지만, 직접 빌드하려면 `COPY main.py`로 고쳐야 한다. 모델을 이미지에 baking하지 않아 **5 Pod가 각자 HF에서 중복 다운로드**한다 — pull ~1m52s, `xvdb` 100GB 덕분에 eviction 없이 받음.

<br>

# apply 전 가드레일

1. **HF gated 승인** — `meta-llama/Llama-3.2-1B` 접근 신청을 실습 시작 전에 완료
2. **비용** — g6.2xlarge On-Demand ~$1.20/h (서울). apply 전 비용 확인, 끝나면 즉시 teardown
3. **순서** — terraform apply → ConfigMap apply → 광고량 10 확인 → secret/SPC/SA → Deployment
4. **time-slicing OFF 시연** — terraform helm 변경(방법 B) 말고 **ConfigMap patch**(방법 A)만 사용 — 방법 B는 helm timeout으로 plugin 0·광고 0까지 깨짐

```bash
# 워크로드 올리기 전 필수 확인
kubectl describe node <gpu-node> | grep nvidia.com/gpu   # Allocatable: 10
```

<br>

# 정리

Ch10 코드는 **ConfigMap(replicas) → device plugin(광고) → Deployment(소비)** 3단으로 time-slicing을 시연한다. upstream 그대로면 Bottlerocket에서 GPU 주입이 깨지고, HF gated 미승인이면 모델 로드가 403으로 깨진다. 두 가지 모두 "스케줄링은 됐는데 추론이 안 되는" 헷갈리는 실패 패턴이다.

다음 [10.7]({% post_url 2026-06-07-Kubernetes-GenAI-on-K8s-10-07-Ch10-Lab-Deploy-Time-Slicing-Verification %})에서 terraform apply부터 teardown까지 실측 결과를 따라간다.

<br>

# 참고 링크

- [Kubernetes for Generative AI Solutions — GitHub ch10](https://github.com/PacktPublishing/Kubernetes-for-Generative-AI-Solutions/tree/main/chapter10)
- [NVIDIA k8s-device-plugin — time-slicing](https://github.com/NVIDIA/k8s-device-plugin#shared-access-to-gpus-with-cuda-time-slicing)
- [NVIDIA k8s-device-plugin — deviceListStrategy](https://github.com/NVIDIA/k8s-device-plugin#device-list-strategy)
- [컨테이너 장치 주입: OCI Runtime Hook과 CDI]({% post_url 2026-02-02-CS-Container-Device-Injection %})
- [time-slicing 적용·검증 — replicas 값 제한]({% post_url 2025-11-22-Kubernetes-GPU-Time-Slicing-3 %}#replicas-값-제한)

<br>
