---
title:  "[EKS] EKS: 데이터 플레인 컴퓨팅"
excerpt: "EKS 데이터 플레인을 구성하는 네 가지 방식을 비교하고, 관리형 노드 그룹의 동작 원리를 살펴보자."
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
  - Managed-Node-Group
  - Fargate
  - Auto-Scaling-Group
  - AWS-EKS-Workshop-Study
  - AWS-EKS-Workshop-Study-Week-1

---

*[서종호(가시다)](https://www.linkedin.com/in/gasida99/)님의 AWS EKS Workshop Study(AEWS) 1주차 학습 내용을 기반으로 합니다.*

<br>

# TL;DR

이번 글에서는 **EKS 데이터 플레인을 구성하는 네 가지 방식**을 다룬다.

- **관리형 노드 그룹**: EC2 인스턴스를 ASG로 묶어 EKS가 수명 주기를 관리. 온디맨드/스팟 용량 유형 지원
- **자체 관리형 노드**: 동일한 EC2 기반이나 ASG, Launch Template, 클러스터 조인, AMI 업데이트를 전부 직접 관리
- **Fargate**: 파드 단위 microVM 서버리스. 노드 관리 자체가 없음
- **EKS Auto Mode**: Karpenter 기반으로 컴퓨팅·네트워킹·스토리지를 EKS가 통합 자동 관리하는 최신 모드

<br>

# 들어가며

EKS에서 Control Plane은 AWS가 완전 관리한다. 사용자 입장에서 "컴퓨팅 리소스 관리"라 하면 결국 **Data Plane(워커 노드)을 어떻게 프로비저닝하고 관리하느냐**의 문제다.

이 글에서는 데이터 플레인을 구성하는 네 가지 방식의 개념과 동작 원리를 정리한다.

<br>

# 데이터 플레인 구성 개요

EKS 데이터 플레인을 구성하는 방식은 네 가지다.

| 방식 | 핵심 | 인프라 |
| --- | --- | --- |
| [**관리형 노드 그룹**](https://docs.aws.amazon.com/ko_kr/eks/latest/userguide/managed-node-groups.html) | EC2 인스턴스를 AWS가 ASG로 묶어서 수명 주기 관리 | EC2 인스턴스 |
| [**자체 관리형 노드**](https://docs.aws.amazon.com/ko_kr/eks/latest/userguide/worker.html) | EC2 인스턴스를 직접 ASG/Launch Template으로 만들고, 직접 EKS에 조인 | EC2 인스턴스 |
| [**Fargate**](https://docs.aws.amazon.com/ko_kr/eks/latest/userguide/fargate.html) | 파드 단위로 microVM이 뜨는 서버리스 방식. 노드 관리 불필요 | AWS 관리 microVM |
| [**EKS Auto Mode**](https://docs.aws.amazon.com/ko_kr/eks/latest/userguide/automode.html) | 컴퓨팅, 네트워킹, 스토리지를 EKS가 통합 자동 관리 | EKS 관리 |


관리형 노드 그룹과 자체 관리형 노드는 둘 다 EC2 인스턴스 기반이지만, **누가 관리하느냐**가 다르다. Fargate는 EC2 자체를 사용하지 않는 완전히 다른 모델이고, EKS Auto Mode는 내부적으로 Karpenter를 기반으로 노드 프로비저닝을 자동화하는 최신 모드다.

<br>

# 관리형 노드 그룹

관리형 노드 그룹(Managed Node Group)이 가장 일반적인 선택지다. [공식 문서](https://docs.aws.amazon.com/ko_kr/eks/latest/userguide/managed-node-groups.html)의 내용을 재구성하여 정의 → 동작 원리 → 용량 유형 → 배포/설정 → 비용/보안 순서로 이해해 본다.

<br>

## 정의와 핵심 가치

관리형 노드 그룹은 Amazon EC2 인스턴스를 **ASG(Auto Scaling Group)로 묶어** EKS가 수명 주기를 관리하는 방식이다. 핵심은 세 가지다.

1. **한 번의 조작으로 노드 관리**: Kubernetes 애플리케이션을 실행하기 위해 EC2 인스턴스를 별도로 프로비저닝하거나 등록할 필요가 없다. 한 번의 조작으로 클러스터에 대한 노드를 자동으로 생성, 업데이트, 종료할 수 있다.
2. **관리 단위는 "그룹"**: 개별 EC2를 하나씩 다루는 것이 아니라, **그룹을 선언하면 AWS가 그 안의 노드들을 알아서 관리**한다. 노드 업데이트 및 종료 시 자동으로 드레이닝하여 애플리케이션 가용성을 유지한다.
3. **추가 비용 없음**: 관리형 노드 그룹이라는 기능 자체에 대한 추가 비용은 없다. 프로비저닝한 AWS 리소스(EC2 인스턴스, EBS 볼륨, EKS 클러스터 시간 등)에 대해서만 비용을 지불한다. 최소 요금이나 선수금도 없다.

> **참고: EBS 볼륨 비용**
>
> **EBS(Elastic Block Store)**는 EC2 인스턴스에 네트워크로 연결되는 블록 스토리지(가상 디스크)다. EC2 인스턴스는 일반적으로 EBS 볼륨을 루트 볼륨으로 사용하며, 필요에 따라 추가 EBS 볼륨을 붙일 수도 있다. EBS 요금은 EC2 인스턴스 요금과 별도로 청구된다. EC2 비용(vCPU+메모리)만 생각하기 쉽지만, 각 노드에 붙은 루트 EBS 볼륨에 대해 프로비저닝된 용량(GB) 기준으로 추가 과금된다.

<br>

## 내부 동작 원리

### ASG 기반 프로비저닝

모든 관리형 노드는 **Amazon EC2 Auto Scaling 그룹의 일부로 프로비저닝**된다. 인스턴스 및 Auto Scaling 그룹을 포함한 모든 리소스는 AWS 계정 내에서 실행되며, 각 노드 그룹은 정의한 여러 가용 영역에서 실행된다.

- **서브넷 분산**: ASG는 노드 그룹 생성 시 지정하는 모든 서브넷에 걸쳐 있다. 예를 들어 `ap-northeast-2a`, `2b`, `2c` 서브넷을 지정하면 인스턴스가 3개 AZ에 걸쳐 분산 배치된다.
- **Launch Template**: 관리형 노드 그룹 배포 시 사용자 정의 시작 템플릿을 활용할 수 있다. Launch Template은 **"앞으로 새로 만들 인스턴스의 스펙 정의서"**다. 추가 `kubelet` 인수 지정, 사용자 지정 AMI 활용 등에 사용한다.

<br>

#### 참고: ASG와 노드 오토스케일링

관리형 노드 그룹과 오토스케일링의 관계를 이해하려면 ASG, Cluster Autoscaler, Karpenter 세 가지의 역할 분담을 알아야 한다.

**ASG(Auto Scaling Group)**는 EC2의 오토스케일링 단위다. 동일한 설정의 EC2 인스턴스를 하나의 그룹으로 묶고, min, max, desired 개수를 지정하여 자동으로 인스턴스를 늘리거나 줄인다. ASG는 지정된 desired 수만큼 인스턴스를 유지(self-healing)하지만, Kubernetes 파드의 스케줄링 상태를 인식하지 못한다. 즉, 파드가 Pending 상태여도 ASG가 스스로 desired를 올리지는 않는다. 외부에서 desired 값을 변경해 주지 않는 한, ASG는 현재 상태만 유지한다.

**Cluster Autoscaler**가 바로 이 역할을 담당하는 Kubernetes 애드온이다. Kubernetes 클러스터에서 Pending 파드를 감지하면 ASG의 desired 값을 증가시키고, ASG가 그에 맞춰 새 인스턴스를 시작한다. 새 노드가 클러스터에 조인하면 Pending이었던 파드가 스케줄된다. 반대로 노드 사용률이 낮아지면 desired를 줄여 스케일 다운한다. 단, Cluster Autoscaler의 조절 범위는 ASG에 설정된 min~max 범위 내로 제한된다. max를 초과하는 확장이 필요하면 사용자가 직접 max 값을 변경해야 한다.

| 주체 | 역할 |
| --- | --- |
| **ASG** | desired 수만큼 인스턴스 유지 (장애 시 자동 복구). desired 값 자체를 변경하지는 않음 |
| **Cluster Autoscaler** | Kubernetes 파드 상태를 감지하여 ASG의 desired를 min~max 범위 내에서 조절 |
| **사용자** | ASG의 min·max 범위 자체를 설정·변경 |

**Karpenter**는 Cluster Autoscaler와 같은 노드 자동 확장 역할을 하지만, 접근 방식이 근본적으로 다른 오픈소스 노드 프로비저너다.

| | **Cluster Autoscaler** | **Karpenter** |
| --- | --- | --- |
| **동작 방식** | ASG의 desired를 조절 | ASG를 거치지 않고 EC2 API로 인스턴스를 직접 시작 |
| **인스턴스 유형** | 노드 그룹에 미리 정의한 유형만 사용 | Pending 파드의 리소스 요구사항을 분석하여 최적 인스턴스 유형을 자동 선택 |
| **속도** | ASG를 거치므로 수 분 소요 | EC2 API 직접 호출로 수십 초 내 프로비저닝 |
| **설정** | 노드 그룹별 인스턴스 유형, min/max 설정 필요 | NodePool CRD에 CPU/메모리 범위, AZ 등 선언적 정의 |
| **스케일 다운** | 노드 사용률 기반으로 ASG desired를 줄임 | 유휴 또는 비효율 노드를 직접 종료 |

Cluster Autoscaler는 미리 정해둔 노드 그룹 단위로 확장 여부를 결정하는 반면, Karpenter는 Pending 파드의 요구사항에 맞는 인스턴스를 즉시 프로비저닝한다. Karpenter를 사용하면 노드 그룹을 여러 개 만들어 인스턴스 유형을 세밀하게 관리할 필요가 줄어든다. 특히 다양한 워크로드(CPU 집약, 메모리 집약, GPU 등)가 혼재하는 클러스터에서 유리하다.

후술할 **EKS Auto Mode**는 내부적으로 Karpenter를 기반으로 동작한다. 노드 그룹, ASG, Cluster Autoscaler 없이, EKS가 Karpenter 방식으로 노드를 자동 프로비저닝하는 모드다.

<br>

### 노드 수명 주기 관리

관리형 노드 그룹에서 EKS는 노드의 종료·업데이트 과정을 자동으로 관리한다. 다만, 모든 상황에서 동일하게 동작하지는 않으며, 사용자가 인지하고 대비해야 할 예외가 존재한다.

- **기본 동작 — 자동 드레이닝과 PDB 준수**: Amazon EKS는 종료 또는 업데이트 중에 Kubernetes API를 이용해 노드를 자동으로 비운다(drain). 관리형 노드 그룹 업데이트 시 파드에 설정된 **PodDisruptionBudget을 준수**한다. EKS가 노드를 종료·업데이트할 때 자동으로 `kubectl drain`을 수행하고, 이때 PDB를 존중한다.
- **예외 — AZRebalance 시 PDB 미준수**: `AZRebalance`는 ASG의 기능으로, AZ 간 인스턴스 수가 불균형하면 자동으로 한쪽을 종료하고 다른 AZ에 새로 띄워 균형을 맞춘다. 이때 EKS의 drain 로직이 아니라 ASG가 직접 종료하므로 **PodDisruptionBudget이 반영되지 않는다.** 노드에서 파드 제거를 시도하지만, 15분이 넘어가면 노드의 모든 파드가 종료되었는지 여부와 무관하게 노드가 종료된다. 이 기간을 연장하려면 Auto Scaling 그룹에 [수명 주기 후크를 추가](https://docs.aws.amazon.com/autoscaling/ec2/userguide/adding-lifecycle-hooks.html)해야 한다.
- **스팟 용량 리밸런싱**: 스팟 용량 유형의 관리형 노드 그룹에서는 EKS가 ASG의 `CapacityRebalance`를 자동으로 활성화한다. 이를 통해 스팟 중단 위험이 높아졌을 때 대체 노드를 선제적으로 시작하고, 기존 노드를 드레이닝하는 리밸런싱이 동작한다. 상세 흐름은 [용량 유형 - 스팟](#스팟) 섹션에서 다룬다.

<br>

### 노드 자동 복구

노드 자동 복구(Node Auto Repair)를 선택적으로 활용하여 노드 상태를 지속적으로 모니터링할 수 있다. 감지된 문제에 자동으로 대응하고 가능한 경우 노드를 교체한다.

- **활성화**: 노드 그룹 생성/수정 시 [`nodeRepairConfig`](https://docs.aws.amazon.com/ko_kr/eks/latest/userguide/node-health.html)를 설정하여 활성화/비활성화할 수 있다.
- **감지 대상**: [EC2 상태 체크](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/monitoring-system-instance-status-check.html) 실패(system status check, instance status check)와 Kubernetes 노드 조건(`NotReady` 등)을 감지한다. 기본적으로 노드가 일정 시간 이상 unhealthy 상태이면 감지한다.
- **복구 과정**: 문제 노드를 terminate한 후 새 노드로 교체한다. drain 후 종료하며, ASG가 자동으로 새 인스턴스를 띄운다.

> **참고: EC2 상태 체크**
>
> | 체크 유형 | 감지 대상 |
> | --- | --- |
> | **System status check** | 하드웨어/호스트 문제 (네트워크 연결 끊김, 전원, 하이퍼바이저 장애 등) — AWS 인프라 문제 |
> | **Instance status check** | 인스턴스 OS 레벨 문제 (커널 패닉, 네트워크 설정 오류, 메모리 부족, 파일시스템 손상 등) — 사용자 영역 문제 |
>
> 상태 확인 오류 발생 시, 문제 원인 파악에 도움이 되는 오류 메시지가 반환된다.

<br>

### 레이블과 태그 자동 부여

- **Kubernetes 레이블**: Amazon EKS는 관리형 노드 그룹 인스턴스에 Kubernetes 레이블을 추가한다. 이러한 EKS 제공 레이블에는 `eks.amazonaws.com` 접두사가 붙는다. 기존 K8s 기본 레이블(`kubernetes.io/*`, `node.kubernetes.io/*`)은 그대로 유지되고, EKS가 추가로 `eks.amazonaws.com/*` 접두사를 가진 레이블을 더 붙여주는 것이다. 노드 그룹을 사용해 Kubernetes 레이블을 노드에 적용하고 업데이트할 수도 있다.
- **ASG 태그**: Amazon EKS는 관리형 노드 그룹 리소스에 태그를 지정하여 Kubernetes Cluster Autoscaler를 사용하도록 구성한다. 관리형 노드 그룹을 만들면 EKS가 자동으로 `k8s.io/cluster-autoscaler/enabled`과 `k8s.io/cluster-autoscaler/<cluster-name>` 태그를 ASG에 붙인다. 이 태그가 있다고 Cluster Autoscaler가 자동 설치되는 것은 아니고, 사용자가 Cluster Autoscaler를 배포했을 때 이 태그로 ASG를 auto-discovery하는 데 사용된다.

<br>

## 용량 유형

관리형 노드 그룹 생성 시 **온디맨드** 또는 **스팟** 용량 유형을 설정할 수 있다. Amazon EKS는 온디맨드 또는 Amazon EC2 스팟 인스턴스만 포함하는 Amazon EC2 Auto Scaling 그룹과 함께 관리형 노드 그룹을 배포한다. 기본은 온디맨드다.

어떤 용량 유형을 선택하든, 관리형 노드 그룹을 만들면 ASG의 세부 설정(할당 전략, 인스턴스 유형 우선순위 등)을 EKS가 자동으로 구성한다. 다만 적용되는 할당 전략은 용량 유형에 따라 다르며, 스팟의 경우 AWS best practice에 따라 자동 구성된다는 점이 특징적이다.


하나의 클러스터 안에 **스팟 노드 그룹과 온디맨드 노드 그룹을 같이 쓸 수 있고**, fault-tolerant 앱은 스팟에, 그렇지 않은 앱은 온디맨드에 스케줄하면 된다.

<br>

## 온디맨드

장기 약정 없이 초 단위로 컴퓨팅 용량을 구입하는 방식이다. 용량 유형을 지정하지 않은 경우 기본적으로 온디맨드 인스턴스를 사용해 프로비저닝된다.

### 할당 전략

온디맨드 용량 프로비저닝을 위한 할당 전략은 `prioritized`로 설정된다. API에 전달된 인스턴스 유형의 순서를 사용해 온디맨드 용량을 채울 때 먼저 사용할 유형을 결정한다.

예를 들어 세 가지 인스턴스 유형을 `c5.large`, `c4.large`, `c3.large` 순서로 지정하면, 온디맨드 인스턴스가 시작될 때 `c5.large` → `c4.large` → `c3.large` 순으로 시작하여 온디맨드 용량을 채운다. `prioritized` 전략은 **가장 선호하는 인스턴스 유형을 첫 번째로** 넣으면 된다. 보통은 성능 대비 가격이 좋은 최신 세대(c5)를 먼저 넣고, fallback으로 이전 세대를 뒤에 넣는다.

### 레이블

Amazon EKS는 온디맨드 용량 유형의 관리형 노드 그룹 노드에 다음 레이블을 추가한다.

```
eks.amazonaws.com/capacityType: ON_DEMAND
```

Pod의 `nodeSelector`나 `nodeAffinity`에서 이 레이블을 지정하면, 해당 파드를 온디맨드 노드에만 스케줄하도록 만들 수 있다. 상태 저장(stateful) 또는 fault-tolerant하지 않은 애플리케이션을 온디맨드 노드에서 실행하는 데 활용한다.

<br>

## 스팟

스팟 인스턴스는 온디맨드 가격에서 큰 폭의 할인을 제공하는 여분의 Amazon EC2 용량이다. 스팟 인스턴스로 관리형 노드 그룹을 구성하여 컴퓨팅 노드의 비용을 최적화할 수 있다. 다만 AWS에 여유 EC2 용량이 줄어들면 **2분 전 알림 후 스팟 인스턴스를 회수(중단)**할 수 있으므로, fault-tolerant 워크로드에만 사용해야 한다.

관리형 노드 그룹 내에서 스팟 인스턴스를 사용하려면 용량 유형을 `spot`으로 설정하여 노드 그룹을 생성한다.

```hcl
resource "aws_eks_node_group" "spot" {
  # ...
  capacity_type  = "SPOT"
  instance_types = ["c5.large", "c5a.large", "m5.large", "m5a.large"]
}
```

### 할당 전략

스팟의 경우 EKS가 best practice에 따라 할당 전략을 자동 설정한다. 클러스터 버전에 따라 적용되는 전략이 다르다.

| 클러스터 버전 | 할당 전략 | 설명 |
| --- | --- | --- |
| **1.28 이상** | `price-capacity-optimized` (PCO) | 가격과 가용 용량을 함께 고려 |
| **1.27 이하** | `capacity-optimized` (CO) | 가용 용량만 고려 |

EKS 관리형 노드 그룹이 PCO 지원을 시작하기 전에 `capacity-optimized`로 이미 생성된 노드 그룹의 할당 전략은 변경되지 않는다. 기존에 CO로 생성된 노드 그룹은 클러스터를 1.28로 올려도 PCO로 자동 변경되지 않는다. 새 노드 그룹을 생성할 때만 적용되는 기본값이므로, 기존 것을 바꾸려면 노드 그룹을 삭제 후 재생성해야 한다.

### 레이블

Amazon EKS는 스팟 용량 유형의 관리형 노드 그룹 노드에 다음 레이블을 추가한다.

```
eks.amazonaws.com/capacityType: SPOT
```

이 레이블을 사용하여 스팟 노드에서 fault-tolerant 애플리케이션을 스케줄한다.

### 용량 리밸런싱

스팟 용량 유형의 관리형 노드 그룹을 생성하면, EKS가 ASG의 `CapacityRebalance`를 자동으로 활성화한다. 이를 통해 스팟 노드의 중단 위험이 높아졌을 때 노드를 정상적으로 비우고 리밸런싱하여 애플리케이션 중단을 최소화한다.

스팟 인스턴스가 rebalance recommendation(재조정 권장 사항)을 수신하면 "곧 회수될 가능성이 높다"는 경고다. 이때 Amazon EKS가 자동으로 새로운 대체 스팟 노드를 시작 시도한다.

구체적인 리밸런싱 흐름은 다음과 같다.

1. 교체 스팟 노드가 `Ready` 상태가 되면 Amazon EKS가 재조정 권장 사항을 받은 스팟 노드를 비우기 시작한다.
2. 스팟 노드를 cordon하면 서비스 컨트롤러가 이 스팟 노드로 새 요청을 보내지 않는다. 또한 정상 활성 스팟 노드 목록에서 제거한다.
3. 스팟 노드를 비우면 실행 중인 파드가 정상적으로 제거된다.

다만 Amazon EKS가 기존 노드를 드레이닝하기 전에 대체 노드가 클러스터에 조인할 때까지 기다린다는 보장이 없다. 종료된 노드에서 실행 중이던 파드가 유실될 수 있으므로, 스팟에는 **죽어도 다시 시작하면 되는 앱만 올리는 것**이 원칙이다. ReplicaSet/Deployment로 여러 replica를 두면 일부 파드가 종료되어도 서비스가 유지된다.

<br>

### 인스턴스 유형과 가용성 확보

스팟은 특정 인스턴스 유형의 용량이 부족하면 프로비저닝 자체가 실패한다. 여러 인스턴스 유형을 지정해야 AWS가 가용한 유형 중에서 선택하여 인스턴스를 시작할 수 있다.

- **동일 리소스 스펙 유지**: [Cluster Autoscaler](https://github.com/kubernetes/autoscaler/blob/master/cluster-autoscaler/cloudprovider/aws/README.md)를 사용하는 경우, vCPU와 메모리가 동일한 인스턴스 유형 집합을 사용해야 노드 확장이 예측 가능하다. 예를 들어 4 vCPU / 8 GiB가 필요하면 `c3.xlarge`, `c4.xlarge`, `c5.xlarge`, `c5d.xlarge`, `c5a.xlarge`, `c5n.xlarge` 등을 조합한다.

- **인스턴스 패밀리 분산**: 여러 스팟 노드 그룹을 배포하되, 각 그룹이 서로 다른 인스턴스 패밀리를 사용하면 스팟 용량 풀이 다양해져 중단 확률이 낮아진다. 예를 들어 한 노드 그룹은 compute 계열(`c3.xlarge`, `c4.xlarge`, `c5.xlarge`), 다른 노드 그룹은 general purpose 계열(`m3.xlarge`, `m4.xlarge`, `m5.xlarge`)을 사용한다.

- **사용자 지정 Launch Template 사용 시**: 스팟 노드 그룹에 사용자 정의 시작 템플릿을 사용하는 경우, API를 통해 여러 인스턴스 유형을 전달해야 한다. Launch Template에 단일 인스턴스 유형만 지정하면 가용성이 크게 떨어진다.

> **참고: EC2 인스턴스 유형 네이밍 컨벤션**
>
> EC2 인스턴스 유형은 `[패밀리][세대][속성].[사이즈]` 형식을 따른다. 예를 들어 `c5d.xlarge`는 다음과 같이 분해된다.
>
> | 구성 요소 | 값 | 의미 |
> | --- | --- | --- |
> | **패밀리** | `c` | Compute Optimized (CPU 집약 워크로드용) |
> | **세대** | `5` | 5세대 (숫자가 클수록 최신) |
> | **속성** | `d` | 로컬 NVMe SSD(Instance Store) 탑재 |
> | **사이즈** | `xlarge` | vCPU/메모리 규모 (4 vCPU / 8 GiB) |
>
> - 주요 패밀리: `c` = Compute Optimized, `m` = General Purpose, `r` = Memory Optimized, `p`/`g` = GPU. 
> - 주요 속성: `a` = AMD 프로세서, `g` = AWS Graviton(ARM), `n` = 네트워크 강화, `d` = Instance Store.
>
> 같은 패밀리의 같은 사이즈면 세대나 속성이 달라도 vCPU/메모리가 동일하다. `c3.xlarge`, `c5.xlarge`, `c5a.xlarge`, `c5n.xlarge`는 모두 4 vCPU / 8 GiB이며, CPU 아키텍처·네트워크 성능·로컬 스토리지 유무 등만 다르다. 따라서 스팟 가용성을 위해 여러 인스턴스 유형을 조합할 때, 같은 패밀리·같은 사이즈로 맞추면 리소스 스펙을 균일하게 유지할 수 있다.


<br>

## 워크로드 매칭 고려 사항

### 스팟에 적합한 워크로드: fault-tolerant

유연한 무상태(stateless) fault-tolerant 애플리케이션에 적합하다. 스팟 인스턴스는 시간이 지남에 따라 변경될 수 있는 예비 Amazon EC2 용량이므로, 중단에 대비한(= 중단되어도 괜찮도록 설계된) 워크로드에 쓰는 것이 좋다. 필요한 용량을 사용할 수 없는 기간을 허용할 수 있는 워크로드에 적합하다. 
- 배치 작업
- Machine Learning training workload
- Big data ETL (Apache Spark 등)
- Queue processing applications
- Stateless API endpoints

> **참고**: ML training이 스팟에 적합한 이유는 **체크포인트 기반 재시작**이 가능하기 때문이다. 순수한 stateless는 아니지만, 외부 스토리지(S3 등)에 주기적으로 체크포인트를 저장하고 중단 후 마지막 체크포인트부터 이어서 할 수 있으므로 fault-tolerant로 본다.

### 온디맨드에 적합한 워크로드: fault-intolerant

fault-tolerant하지 않은 애플리케이션은 온디맨드를 사용한다.
- 모니터링 및 운영 도구와 같은 클러스터 관리 도구
- `StatefulSets`가 필요한 배포
- 상태 유지 애플리케이션 (예: 데이터베이스)

<br>

## 배포와 설정

### 네트워크

관리형 노드 그룹은 퍼블릭 서브넷과 프라이빗 서브넷 모두에서 시작할 수 있다.

- **퍼블릭 서브넷**: 퍼블릭 서브넷에서 관리형 노드 그룹을 시작하는 경우, 인스턴스가 클러스터에 성공적으로 조인하려면 `MapPublicIpOnLaunch`를 `true`로 설정해야 한다. 퍼블릭 서브넷의 노드가 EKS API 서버와 통신하려면 퍼블릭 IP가 있어야 한다. 이 설정이 `false`이면 EC2에 퍼블릭 IP가 부여되지 않아 인터넷 통신이 불가능하고 EKS 클러스터 조인에 실패한다.

- **프라이빗 서브넷**: 프라이빗 서브넷에 관리형 노드 그룹을 배포할 때는 컨테이너 이미지를 가져오기 위해 Amazon ECR에 접근할 수 있는지 확인해야 한다. EKS 시스템 컴포넌트(VPC CNI, CoreDNS, kube-proxy 등)의 이미지는 ECR에서 pull하며, 사용자 애플리케이션 이미지도 ECR을 사용하는 것이 일반적이다. **프라이빗 서브넷에서는 인터넷에 직접 접근할 수 없으므로**, VPC 엔드포인트를 통해 AWS 서비스에 프라이빗하게 접근해야 한다.

> **참고: 프라이빗 서브넷에서의 VPC 엔드포인트**
>
> 이 내용은 관리형 노드 그룹 섹션에 기술되어 있지만, 프라이빗 서브넷에서의 VPC 엔드포인트 요건은 자체 관리형 노드와 Fargate에도 동일하게 적용된다.
>
> ECR에서 이미지를 pull하려면 세 가지 엔드포인트가 필요하다. ECR은 API(메타데이터 조회, 인증 토큰 발급)와 Docker 레지스트리(이미지 레이어 pull/push)가 별도 서비스로 분리되어 있고, 실제 이미지 레이어 데이터는 S3에 저장되므로 S3 엔드포인트도 함께 필요하다.
> 
> | VPC 엔드포인트 | 유형 | 역할 |
> | --- | --- | --- |
> | `com.amazonaws.<region>.ecr.api` | 인터페이스 | ECR API 호출 (이미지 메타데이터, 인증 토큰) |
> | `com.amazonaws.<region>.ecr.dkr` | 인터페이스 | Docker 레지스트리 API (이미지 레이어 pull/push) |
> | `com.amazonaws.<region>.s3` | 게이트웨이 | 이미지 레이어 실제 데이터 저장소 접근 |
>
> VPC 엔드포인트에는 **인터페이스**와 **게이트웨이** 두 가지 유형이 있다. 인터페이스 엔드포인트(PrivateLink)는 서브넷에 ENI를 생성하여 프라이빗 IP로 트래픽을 전달하며, 시간당 요금과 데이터 처리 비용이 발생한다. 게이트웨이 엔드포인트는 라우팅 테이블에 경로를 추가하는 방식으로, S3와 DynamoDB만 지원하지만 무료다. S3는 인터페이스 엔드포인트도 지원하나, 비용 면에서 게이트웨이가 권장된다.

<br>

### Launch Template

관리형 노드 그룹 배포 시 사용자 정의 시작 템플릿(Launch Template)을 활용할 수 있다. 추가 `kubelet` 인수 지정, 사용자 지정 AMI 활용 등 유연성과 사용자 지정 편의를 위해 사용한다.

관리형 노드 그룹 처음 생성 시 사용자 지정 템플릿을 활용하지 않으면, EKS가 자동 생성한 시작 템플릿이 적용된다. **자동 생성된 Launch Template을 AWS 콘솔에서 직접 수정하면** EKS 관리 로직과 충돌하여 **오류가 발생**한다.

[Launch Template](https://docs.aws.amazon.com/ko_kr/eks/latest/userguide/launch-templates.html)은 EC2 인스턴스 생성 시의 설정을 정의하는 템플릿이지, 이미 프로비저닝된 인스턴스에 변경을 가하는 것이 아니다. "템플릿을 수정한다"는 것은 "앞으로 새로 만들 인스턴스의 스펙을 변경한다"는 의미이며, 기존 인스턴스에는 영향을 주지 않는다. 변경 사항을 기존 노드에 적용하려면 rolling update가 필요하다.

변경이 필요할 때의 방법은 두 가지다.

1. **처음부터 사용자 지정 Launch Template을 만들어서** 노드 그룹에 연결
2. Launch Template의 **새 버전**을 만들고, 노드 그룹 업데이트로 새 버전을 적용 → EKS가 rolling update로 노드를 교체

<br>

### 여러 노드 그룹 운영

단일 클러스터에서 여러 관리형 노드 그룹을 생성할 수 있다. 예를 들어 일부 워크로드에는 표준 Amazon EKS 최적화 Amazon Linux AMI를 사용하는 노드 그룹을 생성하고, GPU 지원이 필요한 워크로드에는 GPU 변형을 사용하는 다른 노드 그룹을 생성한다.

<br>

## 비용과 보안

### 비용

관리형 노드 그룹이라는 기능 자체에 대한 추가 비용은 없다. 프로비저닝한 AWS 리소스에 대해서만 비용을 지불한다.

| 과금 대상 | 설명 |
| --- | --- |
| EC2 인스턴스 | 워커 노드 자체 |
| EBS 볼륨 | EC2 인스턴스의 루트 볼륨 |
| EKS 클러스터 시간 | 컨트롤 플레인 사용료 |

### 보안: CVE 및 보안 패치에 대한 공동 책임 모델

CVE(Common Vulnerabilities and Exposures)는 공개적으로 알려진 보안 취약점에 부여되는 고유 식별자(예: `CVE-2024-1234`)다. 관리형 노드 그룹에는 AWS와 사용자가 보안 책임을 나누는 공동 책임 모델이 적용된다.

| 책임 주체 | 하는 일 |
| --- | --- |
| **AWS** | 버그나 문제가 보고될 때 패치된 EKS 최적화 AMI를 빌드하여 게시 |
| **사용자** | 패치된 AMI 버전을 자신의 관리형 노드 그룹에 실제로 배포(적용) |

사용자 지정 AMI를 사용하는 경우에는 패치 자체도 사용자가 직접 해야 한다. 핵심은 "AWS가 고쳐서 새 AMI를 올려줄 테니, 사용자가 노드 그룹 업데이트를 통해 실제로 적용하라"는 것이다.

<br>

# 자체 관리형 노드

## 공식 문서 확인하기

[자체 관리형 노드 공식 문서](https://docs.aws.amazon.com/ko_kr/eks/latest/userguide/worker.html)를 읽으면, 대부분의 내용이 **자체 관리형에만 해당하는 것이 아니라 EKS 노드 전반의 공통 사항**이다. 공식 문서가 자체 관리형 노드 페이지에서 EKS 노드의 기본 개념을 함께 설명하고 있어 혼란스러울 수 있다.

| 문서의 설명 | 자체 관리형 전용 여부 | 실제 범위 |
| --- | --- | --- |
| 파드가 예약된 EC2 노드가 포함 | X | 모든 EC2 기반 노드 |
| API 서버 엔드포인트로 컨트롤 플레인에 연결 | X | 모든 노드 |
| EC2 가격 기준 요금 | X | 모든 EC2 노드 |
| 여러 노드 그룹, ASG 배포 | X | 관리형도 동일 |
| EKS 최적화 AMI 사용 | X | 관리형도 기본 사용 |
| 퍼블릭 엔드포인트 CIDR 제한 시 프라이빗 엔드포인트 권장 | X | 클러스터 전체 설정 |
| **수동으로 태그 추가** (`kubernetes.io/cluster/<name>: owned`) | **O** | 관리형은 EKS가 자동 부여 |
| **bootstrap 구성을 사용자가 직접 관리** (클러스터 이름, API 엔드포인트, CA 인증서 등) | **O** | 관리형은 EKS가 자동 주입 |

> **참고: 퍼블릭 엔드포인트 CIDR 제한과 프라이빗 엔드포인트**
>
> 위 테이블의 "퍼블릭 엔드포인트 CIDR 제한 시 프라이빗 엔드포인트 권장"이 의미하는 바는 다음과 같다.
>
> 워커 노드는 kubelet을 통해 API 서버와 지속적으로 통신한다. 프라이빗 엔드포인트가 비활성화된 상태에서 퍼블릭 엔드포인트에 CIDR 제한을 걸면, 워커 노드도 퍼블릭 엔드포인트를 통해서만 API 서버에 접근할 수 있다. 이때 워커 노드의 트래픽은 VPC 밖으로 나가면서 퍼블릭 IP로 변환되는데(퍼블릭 서브넷이면 인스턴스의 퍼블릭 IP, 프라이빗 서브넷이면 NAT Gateway의 퍼블릭 IP), 이 IP가 허용 CIDR에 포함되어 있지 않으면 워커 노드가 API 서버에 접근하지 못한다.
>
> 예를 들어 사무실 IP만 허용한 경우:
>
> ```
> # 사무실 IP만 허용 → kubectl은 되지만 워커 노드가 API 서버에 접근 불가
> publicAccessCidrs: ["203.0.113.0/24"]
>
> # 워커 노드의 송신 IP도 포함해야 동작
> publicAccessCidrs: ["203.0.113.0/24", "54.180.x.x/32"]
> #                    사무실              NAT GW 또는 인스턴스 퍼블릭 IP
> ```
>
> 프라이빗 엔드포인트를 활성화하면 워커 노드는 VPC 내부 경로(PrivateLink ENI)로 API 서버에 접근하므로 퍼블릭 CIDR 제한에 영향을 받지 않는다. 퍼블릭 엔드포인트는 관리자의 `kubectl` 접근용으로만 제한하고, 워커 노드 통신은 프라이빗으로 분리하는 것이 권장 구성이다.

결국 자체 관리형 노드 문서의 대부분은 **EKS 노드 공통 특징**이고, 자체 관리형의 핵심 차이는 그 공통 특징들을 **사용자가 직접 구성·관리해야 한다**는 데 있다. 태그 부여, bootstrap 설정, ASG 관리, AMI 업데이트 등 관리형에서 EKS가 자동으로 처리하는 영역이 모두 사용자 책임으로 넘어온다.

<br>

## 관리형 노드 그룹과의 실제 차이

자체 관리형 노드에서 사용자가 "직접" 해야 하는 것은 다음 네 가지다.

| 항목 | 관리형 노드 그룹 | 자체 관리형 노드 |
| --- | --- | --- |
| **ASG / Launch Template** | EKS가 생성 | 직접 생성 |
| **클러스터 조인** | 자동 | bootstrap 스크립트 직접 구성 |
| **태그** | EKS가 자동 부여 | `kubernetes.io/cluster/<cluster-name>: owned` 직접 추가 |
| **AMI 업데이트, drain, 교체** | EKS API로 관리 | 전부 수동 |

자체 관리형은 EKS 입장에서는 노드 그룹이라는 개념이 없다. ASG로 묶인 EC2들을 EKS에 조인시킨 것일 뿐이다. 편의상 "자체 관리형 노드 그룹"이라고 부르기도 하지만, 엄밀히 해당 노드 그룹이 EKS API에서 관리되는 리소스는 아니다.

자체 관리형 노드를 수동으로 시작하는 경우, 각 노드에 다음 태그를 추가해야 한다.

| **키** | **값** |
| --- | --- |
| `kubernetes.io/cluster/<cluster-name>` | `owned` |

EKS 최적화 AMI에는 `containerd`, `kubelet`, AWS IAM Authenticator 등이 포함되어 있고, 특별한 bootstrap 스크립트도 포함되어 있어 클러스터 컨트롤 플레인을 자동으로 찾고 연결할 수 있다. 관리형이든 자체 관리형이든 동일한 EKS 최적화 AMI를 사용할 수 있다.

<br>

# Fargate

## 개요

[Fargate](https://docs.aws.amazon.com/ko_kr/eks/latest/userguide/fargate.html)는 컨테이너에 대한 적정 규모의 온디맨드 컴퓨팅 용량을 제공하는 기술이다. 직접 가상 머신 그룹을 프로비저닝하거나, 구성하거나, 크기를 조정할 필요가 없다. 서버 유형을 선택하거나, 노드 그룹을 조정할 시점을 결정하거나, 클러스터 패킹을 최적화할 필요가 없다.

관리형 노드 그룹이나 자체 관리형 노드가 EC2 인스턴스 기반인 것과 달리, Fargate는 **파드 단위로 microVM**이 뜨는 서버리스 방식이다. 노드를 아예 관리하지 않는다.

<br>

## 파드 스케줄 메커니즘

일반적인 K8s에서는 kube-scheduler가 파드를 노드에 배치한다. Fargate는 노드가 없으므로 다른 방식이 필요하다. Amazon EKS는 Kubernetes에서 제공한 확장 가능한 업스트림 모델을 사용하여 AWS에서 빌드한 컨트롤러를 사용해 Kubernetes를 Fargate와 통합한다.

Fargate에서 시작하는 파드와 실행되는 방법은 [Fargate 프로필](https://docs.aws.amazon.com/ko_kr/eks/latest/userguide/fargate-profile.html)로 제어한다.

| 구성 요소 | 역할 |
| --- | --- |
| Fargate 프로필 | 사용자가 namespace + label 셀렉터를 지정하여 "이 조건의 파드는 Fargate에서 돌려라"고 선언 |
| Mutating/Validating Admission Webhook | 파드 생성 요청이 들어올 때 Fargate 프로필에 매칭되는지 확인하고, 파드 스펙을 수정(mutate) |
| Fargate 전용 스케줄러 | 기존 kube-scheduler 외에 추가로 동작. Fargate로 갈 파드를 이 스케줄러가 담당 |

이러한 컨트롤러는 Amazon EKS 관리형 컨트롤 플레인의 일부로 실행된다. 파드가 Fargate에서 실행되기까지의 흐름은 다음과 같다.

1. 사용자가 파드 생성 요청을 보낸다 (예: `kubectl apply -f pod.yaml`).
2. Admission Webhook이 파드의 namespace와 label을 Fargate 프로필 셀렉터와 대조한다.
3. 매칭되면 파드 스펙에 Fargate 관련 정보를 주입(mutate)한다.
4. Fargate 전용 스케줄러가 해당 파드를 담당하여 AWS Fargate API를 호출한다.
5. Fargate가 microVM을 생성하고 파드를 실행한다.

사용자가 직접 관여하는 것은 **Fargate Profile을 만들어 namespace/label 조건을 지정**하는 것뿐이다. 조건에 매칭되는 파드는 자동으로 Fargate에서 실행되며, admission webhook이나 전용 스케줄러는 EKS 컨트롤 플레인 내부에서 동작하는 구현이므로 사용자가 직접 관리할 필요가 없다.

<br>

## 고려 사항

Fargate는 편리하지만 EC2 기반 노드와 비교해 여러 제약이 있다.

### 격리 및 보안

- **자체 컴퓨팅 경계(커널, CPU, 메모리, ENI 공유 안 함)**: EC2 노드에서는 여러 파드가 하나의 OS 커널을 공유하지만, Fargate는 파드마다 별도 microVM이라 완전 격리된다. 컨테이너 이스케이프 공격을 당해도 다른 파드에 영향이 없다.
- **Privileged 컨테이너 불가**: `securityContext.privileged: true`를 사용할 수 없다. 호스트 커널에 직접 접근하는 것은 microVM 격리 모델과 모순되기 때문이다.
- **HostPort / HostNetwork 불가**: 파드 자체가 VM이므로 "호스트"라는 개념이 없다. 호스트 네트워크나 호스트 포트 공유가 불가능하다.
- **VM 격리 = 심층 방어**: Fargate의 보안 장점이다. 다만 공동 책임 모델은 그대로이므로, Fargate가 OS 패치는 해주지만 K8s RBAC, 네트워크 정책 등은 여전히 사용자 책임이다.
- **IMDS 사용 불가**: EC2에서는 IMDS(Instance Metadata Service, `http://169.254.169.254`)를 통해 인스턴스 메타데이터(IAM 역할 자격증명, 인스턴스 ID, AZ 등)를 조회할 수 있다. `169.254.169.254`는 링크-로컬 주소 대역으로, AWS·GCP·Azure 등 주요 클라우드가 메타데이터 서비스에 공통으로 사용하는 주소다. Fargate는 EC2가 아닌 microVM이므로 IMDS가 존재하지 않는다. IAM 자격증명이 필요하면 IRSA(서비스 계정용 IAM 역할)를 사용하고, 리전 등의 정보는 환경 변수로 직접 주입해야 한다.

<br>

### 네트워킹

- **NLB/ALB는 IP 대상만 가능**: EC2 노드에서는 NodePort를 통해 트래픽을 받을 수 있지만(instance 대상), Fargate에는 노드가 없으므로 파드 IP로 직접 라우팅(IP 대상)만 가능하다. 서비스 어노테이션에 `target-type: ip`가 필수다.
- **프라이빗 서브넷만 지원**: Fargate 파드에는 퍼블릭 IP가 부여되지 않는다. 인터넷 접근이 필요하면 NAT Gateway를 통해야 한다.
- **VPC DNS 확인/호스트 이름 활성화 필수**: Fargate가 내부적으로 DNS를 사용해서 EKS API 서버, ECR 등과 통신하므로, VPC 설정에서 `enableDnsSupport`와 `enableDnsHostnames`가 켜져 있어야 한다.
- **보조 CIDR 블록 지원**: Fargate에서는 파드 1개 = IP 1개인데, 서브넷 IP가 고갈될 수 있다. VPC에 보조 CIDR(예: `100.64.0.0/16`)을 추가하고 그 서브넷을 Fargate 프로필에 지정하면 IP 풀을 늘릴 수 있다.
- **대체 CNI 플러그인 사용 불가**: Fargate에는 AWS VPC CNI가 강제 설치된다. Calico, Cilium 같은 커스텀 CNI를 쓸 수 없다(EC2 노드에서만 가능).

<br>

### 스토리지

- **EBS 볼륨 마운트 불가**: Fargate 파드에 EBS를 붙일 수 없다. EBS는 특정 AZ의 EC2에 붙는 블록 스토리지인데, Fargate는 EC2가 아니기 때문이다.
- **EFS는 사용 가능(자동 마운트)**: EFS는 네트워크 파일시스템이라 Fargate에서도 동작한다. 드라이버 설치 없이 자동 마운트되지만, 동적 PV 프로비저닝은 불가하고 미리 만들어둔 EFS에 정적 PV로 연결해야 한다.
- **FSx for Lustre 불가**: 고성능 HPC 스토리지이지만 Fargate에서는 미지원이다.
- **Ephemeral 스토리지**: 기본 20GB 제공된다.

<br>

### 워크로드 제약

- **DaemonSet 불가**: DaemonSet은 모든 노드에 1개씩 배치하는 리소스인데, Fargate에는 노드 개념이 없으므로 사용할 수 없다. 사이드카 컨테이너로 대체한다(예: fluentbit를 각 파드에 사이드카로 주입).
- **GPU 불가**: GPU 인스턴스를 선택할 수 없으므로 ML 추론/학습에 사용할 수 없다.
- **Arm 프로세서 불가**: Graviton 기반 Fargate는 ECS에서만 지원되며, EKS Fargate는 x86만 가능하다.
- **Windows 불가**: Linux 컨테이너만 가능하다.
- **Inferentia / Bottlerocket / Outposts / Local Zones / Wavelength 전부 불가**: Fargate는 AWS가 관리하는 표준 리전 인프라에서만 동작한다.
- **Fargate 스팟 미지원**: ECS에서는 Fargate Spot이 있지만, EKS에서는 Fargate Spot을 쓸 수 없다.
- **nofile/nproc 제한**: 파일 디스크립터 소프트 1,024 / 하드 65,535. 고성능 네트워크 앱에서는 소프트 제한을 올려야 할 수 있다.

<br>

### 스케줄링과 프로필

- **파드 생성 시점에 Fargate 프로필 매칭 필요**: 이미 Pending인 파드는 나중에 Fargate 프로필을 만들어도 자동으로 재스케줄되지 않는다. 파드를 삭제 후 재생성해야 Fargate에서 실행된다.
- **VPA로 리소스 크기 설정 → HPA로 수량 조정**: Fargate는 요청한 것보다 더 많은 리소스를 사용할 수 없으므로, VPA로 적절한 CPU/메모리를 먼저 찾고 HPA로 파드 수를 조절하는 것이 권장 패턴이다. VPA 모드는 `Auto` 또는 `Recreate` 필수(파드를 재생성해야 새 리소스가 적용)다.

<br>

### 비용과 운영

- **파드별 vCPU/메모리 과금**: EC2처럼 인스턴스 단위가 아니라 파드 단위로 과금된다. 파드가 실행되는 시간 x (vCPU 단가 + 메모리 단가)로 계산한다.
- **Job 완료 후 파드 잔존 = 비용**: Kubernetes Job이 `Completed`/`Failed` 상태여도 파드가 남아 있으면 Fargate 요금이 계속 발생한다. `ttlSecondsAfterFinished`로 자동 정리를 설정해야 한다.
- **OS 패치 시 파드 재시작 가능**: AWS가 주기적으로 Fargate OS를 패치하는데, 이때 파드를 제거(evict)한다. PDB를 설정하여 동시 중단 수를 제어하고, EventBridge로 알림을 받을 수 있다.
- **EC2 관리/패치 불필요**: AMI 업데이트, OS 보안 패치 등이 전부 AWS 몫이다. 사용자는 컨테이너 이미지만 관리하면 된다.

<br>

# EKS Auto Mode

EKS Auto Mode는 컴퓨팅, 네트워킹, 스토리지 등을 EKS가 통합 자동 관리하는 최신 모드다. 내부적으로 **Karpenter를 기반**으로 동작하여, 노드 그룹/ASG/Cluster Autoscaler 없이 EKS가 알아서 Karpenter 방식으로 노드를 프로비저닝한다.

관리형 노드 그룹과 비교하면, 노드 그룹 설계(인스턴스 유형, ASG 설정, Cluster Autoscaler 설치 등)를 전부 EKS에 위임하는 것이다.

<br>

# 선택 기준

관리형 노드 그룹이 어떤 면모로 봐도 편하고 추가 비용도 없는데, 다른 것을 쓰는 이유는 무엇일까? 대부분의 경우 관리형 노드 그룹이 권장되지만, 특수한 상황에서 다른 선택지를 고려할 수 있다.

## 자체 관리형 노드를 쓰는 경우

- **완전한 AMI/bootstrap 제어가 필요할 때**: 관리형도 커스텀 AMI를 지원하지만, AMI 업데이트 시 EKS의 자동 롤링이 커스텀 부분과 충돌할 수 있다. 특수 커널 모듈, 보안 에이전트 프리로드, kubelet 외 추가 데몬의 선행 실행 등 Launch Template의 user-data를 완전히 제어해야 하는 경우에는 자체 관리형이 적합하다.
- **기존 인프라/자동화가 구축되어 있을 때**: 이미 Terraform/Ansible로 ASG + Launch Template 파이프라인이 구축되어 있어서 마이그레이션 비용이 큰 경우(레거시).
- **특정 AMI의 관리형 지원 이전**: 특정 AMI가 관리형 노드 그룹에서 완전 지원되기 전에는 자체 관리형으로 운영될 수 있다(예: Bottlerocket).

## Fargate를 쓰는 경우

- **노드 관리를 완전히 제거하고 싶을 때**: CI/CD 파이프라인, 이벤트 기반 단발성 잡 등 노드 운영 부담 없이 파드만 실행하고 싶은 경우.
- **보안 격리가 중요할 때**: 파드마다 별도 microVM이므로 커널 레벨 격리가 보장된다.

## EKS Auto Mode를 쓰는 경우

- **노드 그룹 설계 자체를 위임하고 싶을 때**: 인스턴스 유형 선정, ASG 설정, Cluster Autoscaler 설치 등을 전부 EKS에 맡긴다.

<br>

# 결론

EKS 데이터 플레인을 구성하는 네 가지 방식을 비교하면 다음과 같다.

| | **관리형 노드 그룹** | **자체 관리형 노드** | **Fargate** | **EKS Auto Mode** |
| --- | --- | --- | --- | --- |
| **노드 관리** | EKS가 EC2 프로비저닝·업데이트·교체 | 직접 ASG·AMI·업데이트 관리 | 노드 개념 없음 (서버리스) | EKS가 Karpenter 기반으로 자동 관리 |
| **인프라** | EC2 인스턴스 (ASG) | EC2 인스턴스 (ASG) | 파드별 microVM | EC2 인스턴스 (Karpenter) |
| **설정 자유도** | 중간 | 높음 (커스텀 AMI, 특수 bootstrap 등) | 낮음 (DaemonSet 불가 등 제약) | 낮음 (EKS에 위임) |
| **오토스케일링** | ASG + Cluster Autoscaler 또는 Karpenter | ASG + Cluster Autoscaler 또는 Karpenter | VPA + HPA | Karpenter 내장 |

대부분의 경우 **관리형 노드 그룹이 기본 선택지**다. EC2 수준의 제어권을 유지하면서도 노드 수명 주기 관리를 EKS에 위임할 수 있고, 온디맨드와 스팟 용량 유형으로 비용 최적화도 가능하다. 자체 관리형은 커스텀 AMI나 특수한 bootstrap 구성이 필요한 경우에 한정하여 사용하고, Fargate는 DaemonSet 불가 등 제약을 감수할 수 있는 이벤트 기반 워크로드에 적합하다. 노드 그룹 설계 자체를 EKS에 맡기고 싶다면 EKS Auto Mode를 검토한다.

<br>
