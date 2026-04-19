---
title: "[EKS] EKS GPU 트러블슈팅: 0. 개요"
excerpt: "EKS GPU 트러블슈팅 실습을 진행해보자."
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
  - NVIDIA
  - Troubleshooting
  - AWS-EKS-Workshop-Study
  - AWS-EKS-Workshop-Study-Week-5
---

*정영준님의 AWS EKS Workshop Study(AEWS) [5주차 학습 내용](https://devfloor9.github.io/engineering-playbook/slides/eks-debugging/)을 기반으로 합니다.*

<br>

# 배경

MLOps 관련 실무를 수행하면서 일부 GPU 이슈를 경험한 적은 있지만, 아쉽게도 아직까지 EKS 환경에서 직접 GPU 노드를 운영한 경험은 없다. 이에 AEWS 5주차 스터디 내용 중 GPU 트러블슈팅을 기회 삼아 **"클라우드 관리형(EKS)에서 나타날 수 있는 GPU 문제 및 해결 방법"**에 대해 확인해 보고자 한다.

- **진행 방향**: EKS GPU 클러스터를 구성하고 트러블슈팅 시나리오를 재현
- **구성 원칙**: 재현 가능한 시나리오는 **실습**, 재현 어려우면 **사례 탐구**, 일부는 혼합
- **환경 구성**: [서종호(가시다)](https://www.linkedin.com/in/gasida99/)님의 [기존 실습 환경 구성 코드](https://github.com/gasida/aews)를 참고하여 Terraform으로 구성

<br>

# 환경 구성 주의사항

실습 환경을 구성하기 전에 알아둬야 할 사항이 있다.

- **G/P 인스턴스 vCPU 쿼터**: 서울 리전에서 G/P 인스턴스의 vCPU 쿼터 기본값이 **0**인 계정이 있다. `Running On-Demand G and VT instances` 쿼터를 사전에 확인해야 한다. 증설 신청은 보통 수시간에서 수일 소요된다
- **SPOT 중단 위험**: SPOT 인스턴스를 선택하면 실습 중간에 노드가 회수될 수 있다. GPU 인스턴스는 수요 대비 공급 풀이 작아 범용 인스턴스보다 회수 빈도가 높고, 회수 후 동일 타입 재확보도 보장되지 않는다. 모델 가중치 로딩, NCCL 통신 초기화, 의도적으로 만든 에러 상태 등 GPU 워크로드 특성상 복구 비용이 크기 때문에, 트러블슈팅 맥락이 유실되고 시나리오를 처음부터 다시 시작해야 할 수 있다
- **단일 노드 멀티 GPU 제약**: g5.12xlarge 같은 단일 노드 4-GPU 구성에서는 "노드 간" NCCL(NVIDIA Collective Communications Library, GPU 간 집합 통신 라이브러리) 이슈를 재현할 수 없다. 노드 간 NCCL을 보려면 g5.xlarge × 4 구성이 필요하다

<br>

# 환경 구성 옵션

비용 예상치를 기반으로 실습 환경 옵션을 비교한다.

## 비용 베이스라인

GPU 노드를 제외한 기반 인프라 비용이다. 서울 리전(ap-northeast-2), On-Demand, 24시간 기준이며 대략값이다. 실제 요금은 AWS 공식 페이지 기준으로 apply 전에 재확인이 필요하다.

| 항목 | 단가 | 1일 비용 |
|---|---|---|
| EKS 컨트롤 플레인 | $0.10/h | $2.40 |
| NAT Gateway (1개, 데이터 전송 제외) | $0.059/h | $1.42 |
| 시스템 노드 t3.medium × 2 | $0.052/h × 2 | $2.50 |
| EBS gp3 30GB × 2 | - | $0.20 |
| **기반 소계** | | **≈ $6.5/일** |

## GPU 노드 구성에 따른 3가지 옵션 비교

여기에 GPU 노드 비용이 추가된다.

| 항목 | **Option A — 최소 비용** | **Option B — 표준 (권장)** | **Option C — 분산학습** |
|---|---|---|---|
| GPU 인스턴스 | g4dn.xlarge (T4 16GB) × 1, SPOT 우선 | g5.xlarge (A10G 24GB) × 2, On-Demand | g5.12xlarge (A10G × 4) × 1 또는 g5.xlarge × 4 |
| 시간당 GPU 비용 (대략) | OD $0.526 / SPOT ~$0.20 | $1.006 × 2 = $2.012 | $5.672 (12xlarge) 또는 $1.006 × 4 = $4.024 |
| **1일 총비용 (기반 포함)** | SPOT 기준 **~$12**, OD 기준 **~$20** | **~$55** | **~$100~145** |
| 재현 가능 시나리오 | 단일 GPU: Device Plugin, GPU Operator 기본, vLLM 소형(1~3B), XID 사례 탐구 | + 멀티 노드 NCCL, SG 차단 시나리오, vLLM 7B 모델, tensor-parallel 2 | + 4-GPU NCCL 재현, tensor-parallel 4, 분산학습 smoke |
| 재현 불가 | 멀티 노드 통신 전반, EFA | EFA, p4d/p5 특수 시나리오 | EFA(여전히), p4d/p5 하드웨어 시나리오 |

> **용어 참고**: EFA(Elastic Fabric Adapter)는 AWS의 고성능 네트워크 인터페이스, XID는 NVIDIA GPU 드라이버가 보고하는 에러 코드 체계, SG는 Security Group(보안 그룹)을 의미한다.

## 선택: Option B

비용은 예측값이므로, 실제로 얼마가 청구될지는 실습 진행 후 다시 확인해 봐야 한다(~~요금 폭탄이 아니길 바라며~~). 정말 트러블슈팅 실습이 필요한 동안에만 인스턴스를 사용할 수 있도록 주의가 필요하다.

<br>