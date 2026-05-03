---
title: "[EKS] EKS 업그레이드: 개요"
excerpt: "Kubernetes 업그레이드의 기본 원리를 짚고, 온프레미스 환경과 비교하며 EKS 클러스터 업그레이드 시리즈를 시작해 보자."
categories:
  - Kubernetes
toc: true
header:
  teaser: /assets/images/blog-Dev.jpg
tags:
  - Kubernetes
  - AWS
  - EKS
  - EKS-Upgrade
  - AWS-EKS-Workshop-Study
  - AWS-EKS-Workshop-Study-Week-7
hidden: true
---

*[서종호(가시다)](https://www.linkedin.com/in/gasida99/)님의 AWS EKS Workshop Study(AEWS) 7주차 학습 내용을 기반으로 합니다.*

<br>

# TL;DR

- Kubernetes는 약 4개월마다 마이너 버전을 출시하고, 최근 3개 마이너 버전만 패치를 지원한다
- 업그레이드 시 핵심은 **Version Skew Policy**: 컴포넌트 간 허용되는 버전 차이를 반드시 지켜야 한다
- 온프레미스 K8s 업그레이드는 Control Plane → Data Plane 순서로 직접 수행해야 하며, 컴포넌트 호환성 확인이 필수다
- EKS는 Control Plane 업그레이드를 AWS가 자동화(Blue/Green 방식)해 주므로, 온프레미스 대비 운영 부담이 크게 줄어든다
- 단, **Shared Responsibility Model**에 따라 Data Plane 업그레이드(노드, 애드온)와 워크로드 가용성 보장은 운영자의 책임이다
- EKS Platform Version은 AWS가 자동 업그레이드하므로, 운영자는 **K8s 마이너 버전**에 집중하면 된다
- 이 시리즈에서는 EKS 업그레이드 전략 선택부터 In-Place / Blue-Green 실습까지 다룬다

<br>

# 들어가며

Amazon EKS를 컨테이너 관리 플랫폼으로 선택했다면, 클러스터 업그레이드 계획은 피할 수 없는 과제다. Kubernetes 프로젝트는 새로운 기능, 설계 개선, 버그 수정을 꾸준히 반영하며, 평균 약 4개월마다 새 마이너 버전을 출시한다. 출시 후 약 12개월 동안만 지원되기 때문에, 정기적인 업그레이드 계획이 필수다.

EKS 업그레이드를 이해하려면, 먼저 Kubernetes 자체의 업그레이드 원리를 알아야 한다. 이 글에서는 Kubernetes의 버전 관리 체계와 Version Skew Policy를 정리하고, 온프레미스 환경의 업그레이드와 비교하며 EKS가 어떤 점에서 다른지 살펴본다.

<br>

# Kubernetes 버전 관리

## 버전 체계

Kubernetes는 **메이저.마이너.패치**(예: 1.32.3) 형태의 [Semantic Versioning](https://semver.org/)을 따른다.

| 구분 | 설명 | 예시 |
|------|------|------|
| 메이저 | 하위 호환이 깨지는 변경 | 1.x.x |
| 마이너 | 새 기능 추가, 하위 호환 유지 | x.32.x |
| 패치 | 버그 수정, 보안 패치 | x.x.3 |

## 릴리즈 주기와 지원 기간

Kubernetes는 1년에 약 3개의 마이너 버전을 출시하며, 공식적으로 **최근 3개 마이너 버전**에 대해서만 패치(릴리즈 브랜치)를 지원한다

![Kubernetes 릴리즈 관리 현황]({{site.url}}/assets/images/eks-upgrade-k8s-releases.png){: .align-center}

> 예를 들어 2026년 1월 기준, 공식적으로 1.35, 1.34, 1.33 버전이 릴리즈 관리 대상이다. 그 이전 버전은 보안 패치를 받을 수 없으므로, 주기적인 업그레이드가 중요하다.

<br>

# Version Skew Policy

[Version Skew Policy](https://kubernetes.io/releases/version-skew-policy/)는 Kubernetes 클러스터 내 각 컴포넌트 간 허용되는 버전 차이를 정의한다. 업그레이드 시 반드시 지켜야 하는 핵심 규칙이다.

## 컴포넌트별 허용 버전 범위

kube-apiserver 버전을 기준으로, 각 컴포넌트가 허용하는 버전 범위는 다음과 같다.

| 컴포넌트 | apiserver 대비 NEW | apiserver 대비 OLD | 비고 |
|----------|-------------------|--------------------|------|
| kube-apiserver (HA) | 현재 버전 | -1 마이너 | HA 구성 시 NEW/OLD 1단계 차이 허용 |
| kubelet | 불가 | -3 마이너 | apiserver보다 높을 수 없음 |
| kube-controller-manager | 불가 | -1 마이너 | apiserver보다 높을 수 없음 |
| kube-scheduler | 불가 | -1 마이너 | apiserver보다 높을 수 없음 |
| cloud-controller-manager | 불가 | -1 마이너 | apiserver보다 높을 수 없음 |
| kube-proxy | 불가 | -3 마이너 | kubelet 대비로는 +/-3 마이너 |
| kubectl | +1 마이너 | -1 마이너 | apiserver 기준 +/-1 |

## 예시: kube-apiserver 1.32 기준

| 컴포넌트 | 허용 버전 |
|----------|-----------|
| kubelet | 1.32, 1.31, 1.30, 1.29 |
| kcm / scheduler / ccm | 1.32, 1.31 |
| kube-proxy | 1.32, 1.31, 1.30, 1.29 |
| kubectl | 1.33, 1.32, 1.31 |

## HA 환경에서의 주의점

kube-apiserver가 HA 구성(예: 1.32, 1.31 혼재)인 경우, **가장 낮은 apiserver 버전**을 기준으로 다른 컴포넌트의 허용 범위를 계산해야 한다.

- kube-apiserver HA(1.32, 1.31) → kubelet은 1.31, 1.30, 1.29만 가능 (1.32는 아직 1.31 apiserver가 있으므로 불가)
- 따라서 HA 환경에서는 **apiserver를 모두 새 버전으로 올린 후** 다른 컴포넌트를 업그레이드해야 한다

<br>

# Kubernetes 업그레이드 개요

## 업그레이드 방식

Kubernetes 클러스터 업그레이드에는 크게 두 가지 방식이 있다.


| 방식 | 설명 | 장점 | 단점 |
|------|------|------|------|
| **In-Place** | Version Skew를 이용한 점진적 업그레이드. CP → DP 순서로 순차 업그레이드 | 기존 인프라 유지, 추가 비용 없음 | 롤백 어려움, 순차 진행 필요 |
| **Blue-Green** | 새 클러스터(Green)를 생성하고 워크로드를 마이그레이션 | 빠른 롤백, 여러 버전 건너뛰기 가능 | 이중 인프라 비용, 마이그레이션 복잡도 |

## 업그레이드 절차

어떤 방식이든, 기본적인 업그레이드 절차는 다음과 같다.

```text
사전 준비 → Control Plane 순차 업그레이드 → CP 동작 점검
         → Data Plane 순차 업그레이드 → 전체 동작 점검
```

## 업그레이드 시 고려사항

- **애드온 호환성**: 기존 Addon(CNI, CSI 등)과 애플리케이션 파드가 신규 K8s 버전의 컨트롤 컴포넌트와 호환되는지 확인
  - K8s API 리소스 버전의 변경 여부(Deprecation/Removal) 확인이 특히 중요하다
- **OS/CRI 호환성**: OS, 컨테이너 런타임(containerd 등)이 신규 K8s 버전과 호환되는지 확인
- **CI/CD 파이프라인**: 기존 배포 도구가 신규 K8s 버전에서 정상 동작하는지 검증
- **etcd 데이터**: 반드시 백업. 다만 etcd 데이터 형식은 하위 호환성을 유지한다
- **무중단 서비스**: kube-proxy, CNI 등 핵심 컴포넌트 업데이트 시 서비스 트래픽 중단 여부 확인

<br>

# 온프레미스 K8s vs. EKS 업그레이드

온프레미스 K8s 업그레이드와 비교했을 때, EKS는 다음과 같은 차이점이 있다.

| 항목 | 온프레미스 K8s | Amazon EKS |
|------|---------------|------------|
| Control Plane 업그레이드 | kubeadm 등으로 직접 수행 | AWS가 자동화(Blue/Green 방식) |
| 롤백 | 수동 복원 필요 | CP 업그레이드 실패 시 자동 롤백 |
| etcd 관리 | 직접 백업/복원 | AWS 관리형 |
| Version Skew 관리 | 직접 확인/준수 | Upgrade Insights로 자동 점검 |
| 노드 업그레이드 | 수동(drain/upgrade/uncordon) | Managed Node Group 자동 롤링 또는 Karpenter 활용 |
| 업그레이드 준비 도구 | 수동 점검 | EKS Upgrade Insights, API 호환성 자동 스캔 |
| OS/런타임 호환성 | 직접 확인(OS, containerd, CNI, CSI 등) | AMI 단위로 AWS가 검증 |

핵심적인 차이는, EKS에서는 **Control Plane 업그레이드가 완전 자동화**되어 있다는 점이다. AWS가 Blue/Green 방식으로 컨트롤 플레인 컴포넌트를 업그레이드하며, 문제 발생 시 자동으로 롤백한다. 또한 [EKS Upgrade Insights](https://docs.aws.amazon.com/eks/latest/userguide/cluster-insights.html)를 통해 업그레이드 전 호환성 문제를 사전에 파악할 수 있다.

온프레미스에서는 OS, 컨테이너 런타임, CNI, CSI 등 모든 구성요소의 호환성을 직접 확인하고, kubeadm 등으로 각 노드를 하나씩 업그레이드해야 한다. EKS는 이 부담을 크게 줄여 주지만, Data Plane(워커 노드) 업그레이드와 애드온 업그레이드는 여전히 운영자가 계획하고 실행해야 한다.

## Shared Responsibility Model

![EKS Shared Responsibility Model]({{site.url}}/assets/images/eks-upgrade-shared-responsibility-model.png){: .align-center}

Kubernetes 버전은 Control Plane과 Data Plane 모두에 걸쳐 있다. AWS가 Control Plane을 관리하고 업그레이드하지만, **클러스터 업그레이드를 시작하는 것은 운영자의 책임**이다. 업그레이드를 시작하면 AWS가 Control Plane 업그레이드를 처리하고, 그 이후의 Data Plane 업그레이드는 운영자가 직접 수행해야 한다.

Data Plane 업그레이드 대상:

- **Managed Node Group**: 운영자가 업그레이드를 시작하면, EKS가 롤링 업데이트로 자동 처리 → [In-Place 실습]({% post_url 2026-04-23-Kubernetes-EKS-Upgrade-02-01-03-In-Place-Managed-Node-Group-Upgrade %})
- **Self-managed Node Group**: 운영자가 직접 AMI 교체, drain/cordon 수행 → 이후 실습에서 다룰 예정
- **Karpenter**: [Drift](https://karpenter.sh/docs/concepts/disruption/#drift) 또는 `spec.expireAfter`를 활용한 자동 노드 재생성 가능 → 이후 실습에서 다룰 예정
- **Fargate**: 프로파일 재배포 시 새 버전 적용 → 이후 실습에서 다룰 예정

또한 업그레이드 중 워크로드 가용성을 보장하기 위해, [PodDisruptionBudget](https://kubernetes.io/docs/concepts/workloads/pods/disruptions/#pod-disruption-budgets)과 [TopologySpreadConstraints](https://kubernetes.io/docs/concepts/scheduling-eviction/topology-spread-constraints)를 적절히 설정해야 한다.

## EKS Platform Version

Kubernetes 마이너 버전 외에, Amazon EKS는 자체적으로 **플랫폼 버전**을 별도로 관리한다. 각 K8s 마이너 버전에는 하나 이상의 플랫폼 버전이 연결되며, 새 K8s 마이너 버전이 EKS에 출시되면 초기 플랫폼 버전은 `eks.1`에서 시작하여 릴리즈마다 `eks.n+1`로 증가한다.

![EKS Platform Version 예시]({{site.url}}/assets/images/eks-upgrade-platform-versions.png){: .align-center}

플랫폼 버전에는 Control Plane 설정 변경과 보안 패치가 포함된다. Amazon EKS는 기존 클러스터의 플랫폼 버전을 **자동으로 최신 버전으로 업그레이드**하므로, 운영자가 별도로 조치할 필요가 없다. 자세한 내용은 [Amazon EKS platform versions](https://docs.aws.amazon.com/eks/latest/userguide/platform-versions.html) 문서를 참고하자.

결론적으로, EKS 업그레이드에서 운영자가 신경 써야 할 것은 **K8s 마이너 버전**을 최신으로 유지하는 것이다. 최신 보안 패치와 버그 수정을 적용하고, 성능 및 확장성 개선을 활용하기 위해 정기적인 업그레이드 계획이 필수다.

<br>

# 시리즈 구성

이 시리즈에서는 EKS 클러스터 업그레이드를 이론과 실습 두 파트로 나누어 다뤄 보도록 한다.

|  | 주제 | 설명 |
|------|------|------|
| 01-00 | 개요 | Kubernetes 업그레이드 기본, 온프레미스 vs EKS 비교 (이 글) |
| 01-01 | 업그레이드 전략 | In-Place vs Blue-Green 전략 비교 및 선택 기준 |
| 01-02 | 업그레이드 준비 | EKS Upgrade Insights, 체크리스트, PDB 설정 등 |
| 02-00 | 실습 환경 | AWS Workshop 환경 확인 |
| 02-01 | In-Place 업그레이드 | Control Plane, 애드온, 노드 그룹 업그레이드 |
| 02-02 | Blue-Green 업그레이드 | Green 클러스터 생성, 워크로드 마이그레이션 |
| 02-03 | 정리 | 시리즈 마무리 |

<br>

# 참고 링크

- [Kubernetes Version Skew Policy](https://kubernetes.io/releases/version-skew-policy/)
- [Kubernetes Releases](https://kubernetes.io/releases/)
- [Amazon EKS Cluster Upgrades Best Practices](https://docs.aws.amazon.com/eks/latest/best-practices/cluster-upgrades.html)
- [EKS Upgrade Insights](https://docs.aws.amazon.com/eks/latest/userguide/cluster-insights.html)

<br>
