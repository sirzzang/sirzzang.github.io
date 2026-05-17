---
title: "[EKS] EKS GPU 트러블슈팅: 5. 결론"
excerpt: "EKS GPU 트러블슈팅 시리즈를 마무리하며, 실습에서 도출한 운영 체크리스트와 회고를 정리한다."
categories:
  - Kubernetes
toc: true
hidden: true
header:
  teaser: /assets/images/blog-Dev.jpg
tags:
  - Kubernetes
  - AWS
  - EKS
  - GPU
  - NVIDIA
  - Troubleshooting
  - Checklist
  - AWS-EKS-Workshop-Study
  - AWS-EKS-Workshop-Study-Week-5
---

*정영준님의 AWS EKS Workshop Study(AEWS) [5주차 학습 내용](https://devfloor9.github.io/engineering-playbook/slides/eks-debugging/)을 기반으로 합니다.*

<br>

# TL;DR

- EKS GPU 클러스터를 구성하고, 인프라/앱/네트워크 층의 장애를 재현하고, 재현할 수 없는 주제는 사례 탐구로 다뤘다
- 각 시나리오에서 발견한 "한 번이라도 놓으면 재발할 구멍"을 5-레이어(인프라/드라이버/네트워크/워크로드/관측) 운영 체크리스트로 정리한다
- 관리형 환경에서 재현할 수 없다는 것 자체가 AWS가 인프라/HW 문제를 커버해준다는 뜻이기도 하다

<br>

# 시리즈 돌아보기

| 편 | 주제 | 핵심 발견 |
|---|---|---|
| [0. 개요]({% post_url 2026-04-09-Kubernetes-EKS-GPU-TroubleShooting-00-Overview %}) | 배경, 환경 옵션, 비용 | g5.xlarge × 2 Option B 선택 |
| [1. 사전 준비]({% post_url 2026-04-09-Kubernetes-EKS-GPU-TroubleShooting-01-PreRequisites %}) | EC2 Service Quota | 서울 리전 G/VT 쿼터 기본값이 0인 계정 있음 |
| [2-1. Terraform 코드]({% post_url 2026-04-09-Kubernetes-EKS-GPU-TroubleShooting-02-01-Installation %}) | IaC 구성 | `block_device_mappings` 함정, conditional resource 관리 |
| [2-2. 배포 결과]({% post_url 2026-04-09-Kubernetes-EKS-GPU-TroubleShooting-02-02-Installation-Result %}) | 배포 실행 | vpc-cni ordering, SG(Security Group) baseline |
| [2-3. GPU 노드 프로비저닝]({% post_url 2026-04-09-Kubernetes-EKS-GPU-TroubleShooting-02-03-GPU-Node-Provisioning %}) | GPU Operator 설치 | Helm vs Operator 리소스 경계 |
| [3-1. Device Plugin 비활성화]({% post_url 2026-04-09-Kubernetes-EKS-GPU-TroubleShooting-03-01-GPU-Pod-Pending %}) | GPU Pod Pending 재현 | `status.state`가 `ready` 유지하는 함정, Allocatable `== 0` alert |
| [3-2. vLLM 기동 실패]({% post_url 2026-04-09-Kubernetes-EKS-GPU-TroubleShooting-03-02-vLLM-TroubleShooting %}) | 앱 층 장애 재현 | `enableServiceLinks`, KV cache 예산, max-model-len 2중 벽 |
| [3-3-1. 분산학습 배경]({% post_url 2026-04-09-Kubernetes-EKS-GPU-TroubleShooting-03-03-01-Distributed-Learning-Background %}) | NCCL 통신 배경 | DP/TP/PP, NCCL transport 우선순위, 실험 설계 |
| [3-3-2. SG 차단 장애 재현]({% post_url 2026-04-09-Kubernetes-EKS-GPU-TroubleShooting-03-03-02-Distributed-Learning-Network-Failure %}) | 네트워크 장애 재현 | 실패 지점이 NCCL이 아닌 c10d TCPStore |
| [4. 사례 탐구]({% post_url 2026-04-09-Kubernetes-EKS-GPU-TroubleShooting-04-Error-Cases %}) | XID, Auto Mode, EFA | "다르게 배워야 한다", 소유권 분리 원칙 |

전체 시리즈는 크게 두 가지 접근으로 나뉘었다.

- **재현 시나리오** (3-1 ~ 3-3-2): 실제 클러스터에서 장애를 유발하고 디버깅. "이 증상이 보이면 어디를 봐야 하는가"
- **사례 탐구** (4편): 재현 불가한 주제를 문서 탐구 + 실무 경험 매핑으로 접근. "이 문제가 생기면 어떤 파이프라인을 갖춰야 하는가"

<br>

# 운영 체크리스트 핵심 요약

각 시나리오에서 발굴된 재발 방지 항목을 5-레이어로 분류해서 핵심만 추린다.

## 인프라 레이어

- **Terraform `block_device_mappings` 명시**: `terraform-aws-modules/eks` v21은 `use_custom_launch_template=true` 경로에서 `disk_size`를 조용히 무시한다. 반드시 `block_device_mappings.xvda.ebs.volume_size`로 지정
- **SG(Security Group) 수정 IAM deny**: 런타임 SG 직접 수정을 차단하고 Terraform 경로만 허용. EKS node SG에 태그 기반 Deny 정책 적용
- **LT(Launch Template) 변경 3-step**: GPU vCPU 쿼터가 desired와 정확히 일치할 때 rolling replace 불가. scale-down → TF apply → scale-up 순서 준수

## GPU 드라이버/플러그인 레이어

- **Allocatable `== 0` alert**: Device Plugin off 시 키가 사라지지 않고 값만 0이 됨. `absent()` 대신 `== 0`으로 감지하고, `nvidia.com/gpu.present=true` 조인으로 시스템 노드 false alarm 차단
- **ClusterPolicy drift 감지**: ArgoCD/Flux로 sync + RBAC로 `clusterpolicies.nvidia.com` UPDATE 권한 제거. `status.state`만 보면 disable 상태에서도 `ready` 유지하는 함정에 빠짐

## 네트워크 레이어

- **NCCL smoke CronJob**: GPU 클러스터에 활성 분산학습 job이 없더라도 NCCL 경로가 살아있음을 주기 검증 (30분 주기)
- **NCCL env 기본값 Kyverno 주입**: [Kyverno](https://kyverno.io/)는 Kubernetes-native 정책 엔진으로, Pod 생성 시 admission webhook을 통해 spec을 자동 변경(mutate)하거나 검증(validate)할 수 있다. Kyverno ClusterPolicy로 trainer Pod에 `NCCL_IB_DISABLE=1`, `NCCL_DEBUG=WARN`, `NCCL_SOCKET_IFNAME=eth0`를 자동 주입하면, 개발자가 YAML에서 env를 빠뜨려도 NCCL 기본값이 항상 보장된다

## 워크로드 레이어

- **`enableServiceLinks: false` 고정**: Kubernetes가 auto-inject하는 `VLLM_PORT=tcp://IP:PORT`가 vLLM 자체 env와 충돌
- **vLLM max-model-len 2중 벽**: (a) 모델 config `max_position_embeddings` → pydantic fail-fast, (b) KV cache VRAM 예산. 순서대로 확인

## 관측 레이어

- **XID 감지 → 자동 격리 파이프라인**: dcgm-exporter → Prometheus alert → NPD taint → Karpenter 교체. HW 계열 XID(48/74/79)는 즉시 cordon 트리거
- **증적 자동 수집**: 장애 노드 retire 전에 `dmesg`, `dcgmi diag` 결과를 S3로 push

<details markdown="1">
<summary><b>"1분 인지" 자가 감사</b></summary>

위 체크리스트를 갖췄을 때, 각 시나리오의 장애가 재발하면 **운영자가 몇 분 안에 인지할 수 있는가?** 판정 기준은 "위 체크리스트의 모니터링/알림 체계가 구축되어 있다"는 전제 하에, alert 발화 또는 CronJob 실패까지 걸리는 시간이다.

| 시나리오 | 인지 속도 | 감지 경로 | 예상 소요 |
|---|---|---|---|
| ephemeral-storage 부족 | 느림 | Pod Pending 이벤트 → kube-event alert | 수 분 (이벤트 수집 주기 의존) |
| Device Plugin 비활성화 | 보통 | Allocatable `== 0` alert + DaemonSet 수 불일치 alert | 2~3분 (scrape interval + alert pending) |
| SG(Security Group) self-ref 제거 | 빠름 | NCCL smoke CronJob 실패 → alert | ~1분 (CronJob 주기 의존) |
| NCCL env 누락 | 느림 | 학습 로그에서 성능 이상 감지 (NCCL_DEBUG 미출력 등) | 5분+ (로그 수집 window 의존) |
| XID 에러 | 빠름 | DCGM metric scrape → Prometheus alert | ~15초 (scrape interval) |
| vLLM OOM/CrashLoop | 보통 | CrashLoopBackOff alert + KV cache OOM 로그 | 1~2분 (restart backoff + scrape) |
| EFA 누락 / silent fallback | 감지 불가 | 에러 없이 성능만 열화. iteration time 기반 SLO 위반 alert 필요 | SLO 미구축 시 인지 못함 |

</details>

<br>

# 실습 회고

EKS에서 GPU 클러스터를 직접 운영해 본 적은 없지만, 재현 시나리오를 짜고 실행해 본 것은 좋은 경험이었다 (비용이 얼마 나올지 좀 두렵긴 하다).

온프레미스에서는 서버 OS 업데이트 후 GPU 드라이버 장애, 컨테이너 런타임과 GPU 드라이버 호환성 문제, GPU 하드웨어 인식 문제 같은 것들이 생각보다 많았다. EKS에서 이런 문제를 재현해 볼 수 없어 아쉬웠지만, 재현할 수 없다는 것 자체가 오히려 **운영 상에 발생하는 하드웨어/인프라 단의 문제를 AWS가 커버해 준다**는 뜻이다. 운영 측면에서는 더 편할 것 같다는 생각도 든다.

다만 "AWS가 커버해 준다"는 건 문제가 사라진다는 게 아니라, **문제의 형태가 바뀐다**는 것이다. GPU를 손으로 뽑던 행위가 DCGM → NPD → Karpenter 파이프라인으로 번역되고, 인프라팀이 깔아준 드라이버와의 충돌이 Auto Mode `enabled: false` 선언으로 번역된다. 양쪽을 다 경험하면 추상화의 비용과 이득이 선명해진다.

<br>

# 참고 링크

- [정영준님 AEWS 5주차 슬라이드](https://devfloor9.github.io/engineering-playbook/slides/eks-debugging/)
- [Kubernetes 환경에서 NVIDIA GPU 사용하기]({% post_url 2024-07-19-Dev-Kubernetes-GPU-Setting %})
- [NVIDIA Container Runtime]({% post_url 2024-07-21-Dev-Nvidia-Container-Runtime %})
- [NVIDIA Device Plugin 동작 원리]({% post_url 2024-07-23-Dev-Kubernetes-NVIDIA-GPU-Mechanism %})
- [GPU Sharing: Time Slicing - 1. 개념]({% post_url 2025-11-22-Kubernetes-GPU-Time-Slicing-1 %})

<br>