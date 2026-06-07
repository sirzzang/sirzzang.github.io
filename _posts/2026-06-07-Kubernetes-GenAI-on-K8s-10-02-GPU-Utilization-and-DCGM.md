---
title: "[GenAI] GenAI on K8s: 10.2 - GPU Utilization 이해와 DCGM"
excerpt: "DCGM과 dcgm-exporter의 역할을 구분하고, GPU utilization이 왜 문제가 되는지, 그리고 파티셔닝 기법의 필요성까지 살펴보자."
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
  - DCGM
  - Prometheus
  - Monitoring
use_math: false
---

*[Kubernetes for Generative AI Solutions(Packt 2025, ISBN 978-1-83620-993-5, 저자 Ashok Srirama / Sukirti Gupta)](https://github.com/PacktPublishing/Kubernetes-for-Generative-AI-Solutions) 10장의 학습 내용을 바탕으로 합니다*

<br>

# TL;DR

- DCGM은 GPU 지표를 수집하는 라이브러리/에이전트이고, dcgm-exporter는 이를 Prometheus 포맷으로 노출하는 얇은 래퍼다 — 측정과 노출의 역할이 다르다
- 메트릭은 GPU → DCGM → dcgm-exporter(:9400/metrics) → Prometheus pull 모델로 흐른다
- K8s의 기본 GPU 할당은 배타적(exclusive) — Pod가 실제로 안 쓰는 순간에도 GPU를 독점해 underutilization을 부른다
- 해결 수단은 GPU 파티셔닝·공유 기법(MIG / MPS / time-slicing)이고, 핵심 구분은 allocation(소유) vs isolation(격리)이다

<br>

[이전 글]({% post_url 2026-06-07-Kubernetes-GenAI-on-K8s-10-01-GPU-Resources-and-K8s-Allocation %})에서 GPU 자원의 종류와 K8s에서의 할당 메커니즘을 다뤘다. 이번 글에서는 GPU utilization 모니터링(DCGM)과 활용률 문제, 그리고 GPU 파티셔닝·공유 기법의 필요성을 정리한다.

<br>

# GPU Utilization 이해

GPU는 GenAI 워크로드 실행 비용의 대부분을 차지하므로, 효율적으로 활용하는 것이 최적 성능·비용 효율의 핵심이다. 적절한 모니터링이 없으면 문제가 생긴다:

- **underutilized GPU**: 컴퓨팅 비효율 + 운영비 증가
- **overutilized GPU**: request throttling + application 실패 위험

<br>

## NVIDIA DCGM

DCGM(Data Center GPU Manager)은 NVIDIA GPU를 클러스터·데이터센터 규모로 모니터링·관리하기 위한 경량 라이브러리이자 에이전트다. GPU의 상태·성능 지표를 수집하고, 문제를 조기에 감지하는 역할을 한다.

<br>

### DCGM ≠ dcgm-exporter

흔히 혼동하지만, DCGM과 dcgm-exporter는 역할이 명확히 다르다.

| 컴포넌트 | 정체 | 역할 |
|---|---|---|
| **DCGM** (nv-hostengine) | NVML로 GPU와 직접 대화하는 라이브러리/에이전트 | GPU 지표 수집. Prometheus를 전혀 모름 |
| **dcgm-exporter** | Go로 짠 얇은 래퍼 | DCGM에 질의 → Prometheus exposition format으로 렌더링 → `:9400/metrics`로 노출 |

exporter는 **변환·게시** 담당이지 측정 장치가 아니다. 어떤 GPU 필드를 낼지는 CSV/ConfigMap으로 설정한다.

<br>

### 메트릭이 Prometheus까지 가는 경로 — pull 모델

![DCGM-Prometheus 메트릭 파이프라인]({{site.url}}/assets/images/genai-on-k8s-ch10-dcgm-pipeline.jpg){: .align-center}

dcgm-exporter는 kubelet의 **PodResources API**를 읽어 "이 GPU를 지금 어느 Pod/namespace가 쓰는지"를 메트릭 라벨로 붙인다. Grafana에서 Pod 단위 GPU 사용률이 나오는 건 이 연동 덕분이다. K8s에서 dcgm-exporter를 쓰는 핵심 이유 중 하나다.

> 화살표 읽는 방향 — 데이터는 →, 호출은 그 반대(pull)이다.
>
> | 구간 | 데이터 방향 | 누가 먼저 부르나 |
> |---|---|---|
> | exporter ↔ Prometheus | exporter → Prometheus | Prometheus가 exporter의 /metrics를 긁음 |
> | kubelet ↔ exporter | kubelet → exporter | exporter가 kubelet 소켓을 읽음 |

PodResources API는 노드 로컬 소켓(`/var/lib/kubelet/pod-resources/kubelet.sock`)을 통해 제공된다. exporter는 이 소켓을 읽어서 GPU UUID와 Pod/namespace 라벨을 조인한다. 이를 통해 단순 GPU 지표가 아니라 **"어떤 Pod가 어떤 GPU를 얼마나 쓰는지"** 라는 K8s 수준의 관측 가능성이 확보된다.

핵심은 "exporter는 push하지 않는다. **Pull 모델**이다."라는 것이다.

전체 파이프라인을 정리하면 다음과 같다:

| 단계 | 누가 | 무엇을 |
|---|---|---|
| 수집 | DCGM | NVML 통해 GPU 원시 지표 읽음 |
| 변환·노출 | dcgm-exporter | Prometheus 텍스트로 렌더 → `:9400/metrics` |
| 발견 | ServiceMonitor | Prometheus에 엔드포인트 등록 |
| 수집(pull) | Prometheus | 주기적으로 /metrics scrape → TSDB 저장 |
| 시각화 | Grafana | Prometheus 쿼리 |

<br>

### 배포

Helm으로 간단히 배포할 수 있다:

```hcl
resource "helm_release" "dcgm_exporter" {
  name       = "dcgm-exporter"
  repository = "https://nvidia.github.io/dcgm-exporter/"
  chart      = "dcgm-exporter"
  namespace  = "dcgm-exporter"
}
```

DaemonSet으로 배포되므로 GPU 노드마다 1 Pod가 뜬다.

배포 확인:

```bash
kubectl get pods -n dcgm-exporter
```

메트릭 확인:

```bash
kubectl port-forward -n dcgm-exporter svc/dcgm-exporter 9400:9400
curl localhost:9400/metrics
```

<br>

## GPU utilization challenges

K8s는 기본적으로 GPU를 Pod에 **배타적(exclusive)**으로 할당한다. Pod가 실제로 안 쓰는 순간에도 수명 내내 점유하며, 여러 Pod 간 GPU 공유나 부분 GPU 할당을 기본 지원하지 않는다.

| 요인 | 내용 |
|---|---|
| **모델 크기 편차** | SOTA LLM은 전체 GPU 필요, 작은/distilled 모델은 일부만 → over-provisioning |
| **동적 워크로드 패턴** | 연산 집약 구간에 100% 치솟다가 epoch 사이에 급락. fractional 할당 미지원 |
| **스케줄링 복잡도·파편화** | 기본 스케줄러엔 고급 GPU 공유 패턴 없음. underutilized GPU를 다른 Pod에 동적 재배정 불가 → 클러스터 GPU 파편화 |

> **참고: AWS 블로그의 fractional GPU 사례 (비디오 인코딩)**
>
> [AWS 블로그](https://aws.amazon.com/blogs/containers/delivering-video-content-with-fractional-gpus-in-containers-on-amazon-eks/)는 GenAI/LLM이 아니라 **EKS 위 비디오 인코딩·트랜스코딩** 워크로드를 다룬다. ffmpeg + NVENC(CUDA)로 1080p25 스트림을 GPU에서 인코딩하는데, **작업 하나가 GPU의 약 10%만 쓴다** — 나머지 90%는 놀고 있다. 그래서 time-slicing으로 물리 GPU 1장을 10슬롯으로 광고하고, g4dn.2xlarge(T4) 한 대에 최대 **28개 동시 인코딩 세션**을 bin-pack한다.
>
> 결론의 "최대 95% price-performance 개선"은 time-slicing 단독 수치가 아니다. **fractional GPU + EKS + Bottlerocket(이미지 캐싱) + Karpenter(이종 인스턴스) + spot** 등을 묶은 **비디오 파이프라인 전체** 최적화 결과다. LLM 추론에 그대로 95%를 기대하면 안 된다.
>
> 그래도 이 글에서 GenAI와 공유하는 교훈은 분명하다. **K8s 기본 GPU 할당(whole GPU, exclusive)은 워크로드가 GPU를 다 쓰지 않으면 underutilization을 만든다**는 구조적 문제는 도메인을 가리지 않는다. 비디오는 "인코더 10% × 28세션", GenAI는 "1B 모델 3GB × L4 24GB"처럼 표현만 다를 뿐, **작은 워크로드가 통째 GPU를 받는 over-provisioning**이라는 패턴은 같다. 해결 수단(time-slicing / MIG / MPS)도 동일한 계열이다.

<br>

# GPU 파티셔닝·공유 기법 개요

GPU 파티셔닝·공유 기법은 대체로 벤더별(vendor-specific)이다. NVIDIA의 경우 MIG, MPS, time-slicing 세 가지가 대표적이다. 세 기법 모두 "GPU를 나눠 쓴다"고 말하지만, **얼마나 강하게 갈라 주느냐**는 전혀 다르다. NVIDIA 문서와 원서는 *"each process retains its memory allocations"*처럼 **allocation(소유)** 표현을 자주 쓰는데, 이걸 **isolation(격리)**으로 읽으면 MPS·time-slicing도 MIG만큼 안전하다고 오해하기 쉽다. 아래 용어를 먼저 구분해 두면 이후 MIG/MPS/time-slicing 비교가 훨씬 명확해진다.

> 참고: **allocation vs isolation** 용어 구분
>
> | 용어 | 의미 |
> |---|---|
> | **allocation** (할당) | "이 메모리는 이 프로세스가 잡은(가진) 것" — 소유·점유 |
> | **isolation** (격리) | "남이 못 건드리게 + 용량·대역폭·장애까지 갈라서 보장" |
>
> 도서관 비유: allocation은 "이 책상은 내가 쓰고 있다"이고, isolation은 "칸막이가 있어서 옆 사람 소음·시야까지 차단된다"이다. MPS·time-slicing의 메모리 표현은 대부분 allocation(소유) 얘기지, MIG 같은 하드 격리가 아니다.

세 가지 기법을 한 줄로 요약하면 다음과 같다:

| 기법 | 핵심 | 적합한 시나리오 |
|---|---|---|
| **MIG** | 최소 오버헤드로 강한 격리 + 예측 가능한 성능 | 멀티테넌트·추론 |
| **MPS** | 여러 프로세스가 한 GPU를 동시(concurrent) 공유 | 자원 활용 최적화 |
| **time-slicing** | compute 자원을 round-robin으로 배분 | 여러 워크로드가 번갈아 실행 |

다음 글에서 MIG를, 그 다음 글에서 MPS와 time-slicing을 상세히 다룬다.

<br>

# 정리

| 영역 | 핵심 포인트 |
|---|---|
| **DCGM vs dcgm-exporter** | 측정(NVML) vs 노출(Prometheus /metrics) |
| **메트릭 흐름** | GPU → DCGM → exporter → Prometheus (pull) |
| **PodResources API** | exporter가 읽어 Pod/namespace 라벨 부착 |
| **기본 할당 문제** | 배타적 → underutilization (모델 편차, 동적 패턴, 파편화) |
| **파티셔닝 키워드** | allocation(소유) ≠ isolation(격리) |

<br>

# 참고 링크

- [Kubernetes for Generative AI Solutions — GitHub](https://github.com/PacktPublishing/Kubernetes-for-Generative-AI-Solutions)
- [NVIDIA DCGM Documentation](https://docs.nvidia.com/datacenter/dcgm/latest/)
- [dcgm-exporter GitHub](https://github.com/NVIDIA/dcgm-exporter)
- [Delivering video content with fractional GPUs — AWS Blog](https://aws.amazon.com/blogs/containers/delivering-video-content-with-fractional-gpus-in-containers-on-amazon-eks/)

<br>
