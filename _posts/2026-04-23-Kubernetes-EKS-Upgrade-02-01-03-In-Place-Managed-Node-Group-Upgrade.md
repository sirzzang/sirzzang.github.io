---
title: "[EKS] EKS 업그레이드: In-Place 실습 - Managed Node Group 업그레이드"
excerpt: "Terraform으로 EKS Managed Node Group을 업그레이드하는 두 가지 시나리오(기본 AMI, 커스텀 AMI)를 실습해 보자."
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
  - Managed-Node-Group
  - Terraform
  - AWS-EKS-Workshop-Study
  - AWS-EKS-Workshop-Study-Week-7
hidden: true
---

*[서종호(가시다)](https://www.linkedin.com/in/gasida99/)님의 AWS EKS Workshop Study(AEWS) 7주차 학습 내용을 기반으로 합니다.*

<br>

# TL;DR

- Managed Node Group 업그레이드는 **완전 자동화된 롤링 업데이트**로 진행된다 (Setup → Scale Up → Upgrade → Scale Down)
- 업그레이드 시나리오는 두 가지: **기본 AMI**(EKS 관리형)와 **커스텀 AMI**(직접 지정)
- 기본 AMI: `mng_cluster_version` 변수만 변경하면 EKS가 최신 AMI를 자동 선택
- 커스텀 AMI: `ami_id` 변수를 대상 버전의 AMI로 직접 교체해야 함
- 실습에서는 `initial` 노드 그룹(기본 AMI)과 `custom` 노드 그룹(커스텀 AMI) 두 가지를 Terraform으로 동시 업그레이드
- 이 글은 In-Place 방식의 Data Plane 업그레이드 중 Managed Node Group을 다룬다. 이후 Self-managed 노드, Karpenter 노드, Fargate 프로파일 등 다른 노드 유형도 각각의 방식으로 업그레이드한다

<br>

# 워크숍의 노드 업그레이드 실습 구조

시작하기 전에, 이 워크숍이 노드 업그레이드를 어떻게 설계했는지 짚고 가자.

[실습 환경]({% post_url 2026-04-23-Kubernetes-EKS-Upgrade-02-00-Environment %})에서 확인한 것처럼, 이 클러스터에는 여러 노드 프로비저닝 방식이 혼재되어 있다.

| 노드 유형 | 노드 그룹 | 업그레이드 실습 |
|-----------|-----------|----------------|
| Managed Node Group | initial, blue-mng | 이 글 (In-Place) + 이후 글 (Blue-Green) |
| Karpenter | default NodePool | 이후 글 |
| Self-managed / Fargate | default-selfmng, fp-profile | 이후 글 (간략히) |

워크숍은 Managed Node Group에 대해 In-Place 업데이트와 새 노드 그룹으로의 마이그레이션(Blue-Green) **두 가지 전략을 모두** 실습하고, Karpenter의 Drift 기반 업그레이드까지 다룬다. Self-managed와 Fargate는 핵심 원리가 동일하므로 간략히 정리한다. 이 글에서는 그중 첫 번째인 **Managed Node Group In-Place 업데이트**를 다룬다.

<br>

# EKS Managed Node Group이란

Amazon EKS Managed Node Group은 노드(EC2 인스턴스)의 프로비저닝과 라이프사이클 관리를 자동화한다. 별도로 EC2 인스턴스를 프로비저닝하거나 등록할 필요 없이, 단일 작업으로 노드를 생성, 업데이트, 종료할 수 있다. 노드 업데이트와 종료 시 자동으로 drain이 수행되어 애플리케이션 가용성이 유지된다.

각 Managed Node Group은 Amazon EC2 Auto Scaling Group으로 구성되며, 정의한 여러 가용 영역에 걸쳐 실행된다.

<br>

# Managed Node Group 업그레이드 전략

Managed Node Group 업그레이드에는 두 가지 전략이 있다.

| 전략 | 설명 |
|------|------|
| **In-Place 업데이트** | 기존 노드 그룹을 그대로 두고, 롤링 업데이트로 노드를 순차 교체 |
| **새 노드 그룹으로 마이그레이션** | 새 버전의 노드 그룹을 생성하고, 워크로드를 마이그레이션한 뒤 기존 그룹 삭제 |

이 글에서는 **In-Place 업데이트**를 다루고, 새 노드 그룹으로의 마이그레이션은 이후 글에서 다룬다.

<br>

# In-Place 업데이트 동작 방식

Managed Node Group의 In-Place 업데이트는 4단계로 자동 진행된다.

## 1단계: Setup

- 노드 그룹에 연결된 Auto Scaling Group의 새 EC2 Launch Template 버전을 생성한다. 대상 AMI 또는 커스텀 Launch Template을 반영한다.
- Auto Scaling Group이 최신 Launch Template 버전을 사용하도록 업데이트한다.
- 노드 그룹의 `updateConfig`에 정의된 `max_unavailable` 값에 따라 병렬 업그레이드할 최대 노드 수를 결정한다 (최대 100, 기본값 1).

## 2단계: Scale Up

- Auto Scaling Group의 최대/원하는 크기를 증가시킨다 (가용 영역 수의 2배 또는 `max_unavailable` 중 큰 값).
- 최신 설정을 사용하는 새 노드가 Ready 상태가 될 때까지 대기한다.
- 기존 노드를 스케줄 불가(`Unschedulable`)로 표시하고, `node.kubernetes.io/exclude-from-external-load-balancers=true` 레이블을 추가하여 로드 밸런서에서 제거한다.

## 3단계: Upgrade

- 업그레이드가 필요한 노드를 `max_unavailable` 만큼 랜덤으로 선택한다.
- 선택된 노드에서 파드를 drain한다. 15분 내에 파드가 제거되지 않으면 **PodEvictionFailure** 에러가 발생한다 (force 플래그로 강제 제거 가능).
- 모든 파드가 축출된 후 노드를 cordon하고 60초 대기한다.
- Auto Scaling Group에 cordon된 노드의 종료 요청을 보낸다.
- 이전 Launch Template 버전의 노드가 남아 있지 않을 때까지 반복한다.

## 4단계: Scale Down

- Auto Scaling Group의 최대/원하는 크기를 업데이트 전 값으로 되돌린다.

<br>

# 업그레이드 방법

## 방법 1: eksctl

```bash
# 최신 AMI 버전으로 업그레이드
~$ eksctl upgrade nodegroup --name=managed-ng-1 --cluster=$EKS_CLUSTER_NAME

# 특정 K8s 버전으로 업그레이드
~$ eksctl upgrade nodegroup --name=managed-ng-1 --cluster=$EKS_CLUSTER_NAME \
    --kubernetes-version=1.31

# 특정 AMI 릴리스 버전으로 업그레이드
~$ eksctl upgrade nodegroup --name=managed-ng-1 --cluster=$EKS_CLUSTER_NAME \
    --release-version=<AMI-Release-Version>
```

## 방법 2: AWS 콘솔

1. [Amazon EKS 콘솔](https://console.aws.amazon.com/eks/home#/clusters)에서 클러스터 선택
2. **Compute** 탭에서 업데이트 가능한 노드 그룹의 **Update now** 선택
3. 업데이트 전략 선택
   - **Rolling update**: PDB를 존중하며 업데이트. PDB 위반 시 실패
   - **Force update**: PDB를 무시하고 강제 업데이트

## 방법 3: Terraform (이 실습에서 사용)

Terraform에서는 노드 그룹의 AMI 버전이나 Launch Template이 변경되면 자동으로 롤링 업데이트가 트리거된다.

<br>

# 실습 환경: Managed Node Group 구성

현재 클러스터에는 두 개의 Managed Node Group이 있다. Terraform `base.tf`의 EKS 모듈에서 확인할 수 있다.

```hcl
eks_managed_node_group_defaults = {
  cluster_version = var.mng_cluster_version
}

eks_managed_node_groups = {
  initial = {
    instance_types = ["m5.large", "m6a.large", "m6i.large"]
    min_size     = 2
    max_size     = 10
    desired_size = 2
    update_config = {
      max_unavailable_percentage = 35
    }
  }

  blue-mng = {
    instance_types  = ["m5.large", "m6a.large", "m6i.large"]
    cluster_version = "1.30"
    min_size     = 1
    max_size     = 2
    desired_size = 1
    update_config = {
      max_unavailable_percentage = 35
    }
    labels = {
      type = "OrdersMNG"
    }
    subnet_ids = [module.vpc.private_subnets[0]]
    taints = [
      {
        key    = "dedicated"
        value  = "OrdersApp"
        effect = "NO_SCHEDULE"
      }
    ]
  }
}
```

| 노드 그룹 | AMI 방식 | 버전 관리 | 용도 |
|-----------|----------|-----------|------|
| `initial` | EKS 관리형 (기본 AMI) | `mng_cluster_version` 변수 참조 | 범용 워크로드 |
| `blue-mng` | EKS 관리형 (기본 AMI) | `cluster_version = "1.30"` 고정 | Orders 전용 (taint/toleration) |

`initial`은 `eks_managed_node_group_defaults`의 `cluster_version`(= `var.mng_cluster_version`)을 따르고, `blue-mng`은 버전이 `"1.30"`으로 직접 고정되어 있다.

<br>

# 실습: 두 가지 AMI 시나리오

이 실습에서는 두 가지 시나리오를 동시에 검증한다.

| 시나리오 | 노드 그룹 | 업그레이드 방법 |
|----------|-----------|----------------|
| **기본 AMI** (EKS 관리형) | `initial` | `mng_cluster_version` 변수를 1.31로 변경 |
| **커스텀 AMI** (직접 지정) | `custom` (새로 생성) | `ami_id` 변수를 1.31용 AMI ID로 변경 |

커스텀 AMI 시나리오를 테스트하기 위해, 먼저 커스텀 AMI 기반 노드 그룹을 하나 추가한다.

## 1단계: 커스텀 AMI 노드 그룹 준비

### 1.30 버전 AMI ID 조회

```bash
~$ aws ssm get-parameter \
    --name /aws/service/eks/optimized-ami/1.30/amazon-linux-2023/x86_64/standard/recommended/image_id \
    --region $AWS_REGION --query "Parameter.Value" --output text

# 실행 결과 (시점에 따라 다름)
ami-0c42b1f4678fc81d1
```

> SSM Parameter Store에서 조회되는 AMI ID는 EKS Optimized AMI가 패치/업데이트될 때마다 달라진다. 반드시 본인 환경에서 조회된 값을 사용해야 한다.

### variables.tf에 ami_id 추가

```hcl
variable "ami_id" {
  description = "EKS AMI ID for node groups"
  type        = string
  default     = "ami-0c42b1f4678fc81d1"
}
```

![variables.tf에 ami_id 설정]({{site.url}}/assets/images/eks-upgrade-mng-variables-ami-id.png){: .align-center}

`ami_id`를 빈 문자열이 아닌 특정 값으로 지정하면, EKS가 AMI를 자동으로 관리하지 않게 된다. 이렇게 해야 이후 실습에서 AMI ID를 직접 교체하며 **수동 업그레이드 과정을 체험**할 수 있다.

### base.tf에 custom 노드 그룹 추가

```hcl
custom = {
  instance_types = ["t3.medium"]
  min_size     = 1
  max_size     = 2
  desired_size = 1
  update_config = {
    max_unavailable_percentage = 35
  }
  ami_id                     = try(var.ami_id)
  ami_type                   = "AL2023_x86_64_STANDARD"
  enable_bootstrap_user_data = true
}
```

![base.tf에 custom 노드 그룹 추가]({{site.url}}/assets/images/eks-upgrade-mng-base-tf-custom.png){: .align-center}

### Terraform Apply

```bash
~$ cd ~/environment/terraform
~$ terraform plan && terraform apply -auto-approve
```

<details markdown="1">
<summary><b>terraform apply 주요 출력</b></summary>

```text
module.eks.module.eks_managed_node_group["custom"].aws_eks_node_group.this[0]: Creating...
module.eks.module.eks_managed_node_group["initial"].aws_eks_node_group.this[0]: Modifying...
...
module.eks.module.eks_managed_node_group["custom"].aws_eks_node_group.this[0]: Creation complete after 1m47s
...
Apply complete! Resources: 10 added, 2 changed, 3 destroyed.
```

</details>

이 시점에서 클러스터에는 3개의 Managed Node Group이 존재한다.

| 노드 그룹 | AMI 방식 | K8s 버전 |
|-----------|----------|---------|
| `initial` | EKS 관리형 | 1.30 |
| `blue-mng` | EKS 관리형 (1.30 고정) | 1.30 |
| `custom` | 커스텀 AMI | 1.30 |

## 2단계: 기본 AMI vs 커스텀 AMI 업그레이드 차이 확인

`mng_cluster_version`만 1.31로 변경하고 `terraform plan`을 실행하면 어떻게 되는지 살펴보자.

```hcl
variable "mng_cluster_version" {
  description = "EKS cluster mng version."
  type        = string
  default     = "1.31"
}
```

이때 Terraform plan의 결과는:

- `initial` → **업그레이드 대상** (`mng_cluster_version` 변경을 따르므로)
- `custom` → **업그레이드 대상 아님** (특정 AMI ID가 지정되어 있어, `mng_cluster_version`과 무관)
- `blue-mng` → **업그레이드 대상 아님** (`cluster_version = "1.30"` 으로 직접 고정)

기본 AMI를 사용하는 노드 그룹은 버전 변수만 바꾸면 자동으로 업그레이드되지만, **커스텀 AMI를 사용하는 노드 그룹은 AMI ID를 직접 교체해야** 한다는 차이가 있다.

## 3단계: 두 노드 그룹 동시 업그레이드

`initial`과 `custom`을 모두 1.31로 올리려면, `mng_cluster_version`과 `ami_id`를 함께 변경해야 한다.

### 1.31 버전 AMI ID 조회

```bash
~$ aws ssm get-parameter \
    --name /aws/service/eks/optimized-ami/1.31/amazon-linux-2023/x86_64/standard/recommended/image_id \
    --region $AWS_REGION --query "Parameter.Value" --output text

# 실행 결과
ami-0c4dea04571b1b508
```

### variables.tf 변경

```hcl
variable "mng_cluster_version" {
  description = "EKS cluster mng version."
  type        = string
  default     = "1.31"
}

variable "ami_id" {
  description = "EKS AMI ID for node groups"
  type        = string
  default     = "ami-0c4dea04571b1b508"
}
```

![variables.tf 변경 - mng_cluster_version과 ami_id]({{site.url}}/assets/images/eks-upgrade-mng-variables-upgrade.png){: .align-center}

### Terraform Apply

```bash
~$ terraform plan && terraform apply -auto-approve
```

> 이 작업은 약 12~20분 소요된다. `initial` 노드 그룹의 롤링 업데이트가 진행되는 동안, `custom` 노드 그룹도 함께 업데이트된다.

## 4단계: 업그레이드 결과 확인

```bash
~$ kubectl get nodes -o wide
```

| 노드 | 버전 | AGE | 설명 |
|------|------|-----|------|
| ip-10-0-8-17 | **v1.31.14** | 16m | `initial` — 1.31로 업그레이드 완료 |
| ip-10-0-22-172 | **v1.31.14** | 17m | `custom` — 1.31로 업그레이드 완료 |
| ip-10-0-6-74 | v1.30.14 | 2d6h | `blue-mng` — 아직 1.30 |
| ip-10-0-22-47 | v1.30.14 | 2d6h | Self-managed — 아직 1.30 |
| ip-10-0-35-24 | v1.30.14 | 2d6h | Self-managed — 아직 1.30 |
| ip-10-0-19-61 | v1.30.14 | 2d6h | Karpenter — 아직 1.30 |
| fargate-ip-10-0-15-170 | v1.30.14 | 2d6h | Fargate — 아직 1.30 |

![콘솔에서 initial 업그레이드 완료 확인]({{site.url}}/assets/images/eks-upgrade-mng-initial-upgraded.png){: .align-center}

`initial`과 `custom` 두 노드 그룹만 1.31로 업그레이드되고, 나머지(`blue-mng`, Self-managed, Karpenter, Fargate)는 1.30을 유지하고 있다. 이들은 각각 다른 방식으로 업그레이드하게 된다.

## 5단계: Cleanup

커스텀 AMI 업그레이드 실습이 완료되었으므로, `custom` 노드 그룹을 삭제한다. `base.tf`에서 `custom` 블록을 제거하고 Terraform을 적용한다.

```bash
~$ terraform plan && terraform apply -auto-approve
```

<details markdown="1">
<summary><b>terraform apply 삭제 로그</b></summary>

```text
module.eks.module.eks_managed_node_group["custom"].aws_eks_node_group.this[0]: Destroying...
...
module.eks.module.eks_managed_node_group["custom"].aws_iam_role.this[0]: Destruction complete after 0s

Apply complete! Resources: 3 added, 1 changed, 10 destroyed.
```

</details>

Cleanup 후 남아 있는 Managed Node Group:

| 노드 그룹 | K8s 버전 | 상태 |
|-----------|---------|------|
| `initial` | 1.31 | 업그레이드 완료 |
| `blue-mng` | 1.30 | 아직 업그레이드 안 됨 (이후 실습에서 처리) |

<br>

# 정리

이 글에서는 Managed Node Group의 In-Place 업그레이드를 두 가지 시나리오로 실습했다.

| 시나리오 | 방법 | 핵심 |
|----------|------|------|
| 기본 AMI | `mng_cluster_version` 변경 | EKS가 최신 AMI 자동 선택 |
| 커스텀 AMI | `ami_id` 변경 | SSM에서 대상 버전 AMI 조회 후 직접 지정 |

In-Place 업그레이드의 전체 진행 상황:

| 단계 | 상태 |
|------|------|
| Control Plane 업그레이드 (1.30 → 1.31) | 완료 |
| EKS 애드온 업그레이드 | 완료 |
| **Managed Node Group In-Place 업그레이드** | **완료 (이 글)** |
| Managed Node Group Blue-Green 마이그레이션 (`blue-mng`) | 이후 |
| Karpenter 노드 업그레이드 | 이후 |
| Self-managed / Fargate 노드 업그레이드 | 이후 |

<br>

# 참고 링크

- [Amazon EKS Managed Node Groups](https://docs.aws.amazon.com/eks/latest/userguide/managed-node-groups.html)
- [Updating a Managed Node Group](https://docs.aws.amazon.com/eks/latest/userguide/update-managed-node-group.html)
- [EKS Optimized AMI Release Versions](https://docs.aws.amazon.com/eks/latest/userguide/eks-optimized-ami.html)
- [EKS Upgrade Workshop - Managed Node Group Upgrades](https://catalog.us-east-1.prod.workshops.aws/workshops/fb76a304-9e44-43b9-90b4-5542d4c1b15d)

<br>
