---
title: "[EKS] EKS 업그레이드: In-Place 실습 - Control Plane 업그레이드"
excerpt: "Terraform을 이용해 EKS Control Plane을 1.30에서 1.31로 업그레이드하는 실습을 진행해 보자."
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
  - Terraform
  - AWS-EKS-Workshop-Study
  - AWS-EKS-Workshop-Study-Week-7
hidden: true
---

*[서종호(가시다)](https://www.linkedin.com/in/gasida99/)님의 AWS EKS Workshop Study(AEWS) 7주차 학습 내용을 기반으로 합니다.*

<br>

# TL;DR

- In-Place 업그레이드는 **Control Plane → 애드온 → 노드** 순서로 진행한다
- EKS Control Plane 업그레이드는 AWS가 **Blue/Green 방식**으로 자동 수행하며, 실패 시 자동 롤백된다
- 업그레이드 방법은 eksctl, AWS 콘솔, AWS CLI, **Terraform** 4가지가 있다
- 이 실습에서는 Terraform으로 `variables.tf`의 `cluster_version`을 1.30 → 1.31로 변경하여 업그레이드를 진행한다
- 약 10~15분 소요되며, `kubectl version`과 `aws eks describe-cluster`로 완료를 확인할 수 있다
- 주의: CLI/콘솔로 업그레이드한 후 Terraform 변수를 업데이트하지 않으면 **다운그레이드 시도 에러**가 발생한다

<br>

# In-Place 업그레이드 개요

In-Place 업그레이드는 가장 단순한 형태로 다음 세 단계로 구성된다.

1. **클러스터 Control Plane** 업그레이드
2. Kubernetes **애드온 및 커스텀 컨트롤러** 업데이트
3. 클러스터 **노드** 업그레이드

업그레이드 전에 Deprecated API 제거, Kubernetes 매니페스트 업데이트 등의 사전 조치를 완료해야 한다. 사전 요구사항에 대한 자세한 내용은 [업그레이드 준비]({% post_url 2026-04-23-Kubernetes-EKS-Upgrade-01-02-Preparation %}) 포스트를 참고하자.

> 운영 환경 업그레이드 전에 테스트 환경에서 전체 과정을 먼저 완료하여, 클러스터 설정이나 애플리케이션 매니페스트의 문제를 사전에 발견하는 것이 좋다.

이 글에서는 첫 번째 단계인 **Control Plane 업그레이드**를 실습한다.

<br>

# Control Plane 업그레이드 절차

EKS Control Plane 업그레이드는 **한 번에 1 마이너 버전**만 올릴 수 있는 순차적 업그레이드다. 여러 버전 뒤처져 있다면, 각 버전을 순서대로 거쳐야 한다.

## AWS가 수행하는 업그레이드 과정

업그레이드를 시작하면, AWS가 다음 과정을 자동으로 수행한다.

**정상 업그레이드 시:**

1. **사전 점검**: EKS Upgrade Insights를 통해 업그레이드에 영향을 줄 수 있는 문제를 확인
2. **Control Plane 컴포넌트 업그레이드**: Blue/Green 방식으로 새 버전의 컨트롤 플레인을 프로비저닝하고, API 서버 엔드포인트를 갱신
3. **이전 Control Plane 종료**: 업그레이드가 완료되면 이전 버전의 컨트롤 플레인 컴포넌트를 종료

**업그레이드 실패 시:**

1. **장애 감지**: AWS가 업그레이드 과정을 지속적으로 모니터링하다 문제가 발생하면 즉시 중단
2. **새 컨트롤 플레인 종료**: 업그레이드 중 프로비저닝된 새 컨트롤 플레인 컴포넌트를 종료
3. **사후 분석**: AWS가 실패 원인을 분석하고, 해결 방법을 안내

Blue/Green 방식으로 진행되기 때문에, 업그레이드 실패 시에도 기존 애플리케이션은 계속 가용 상태를 유지한다.

<br>

# 업그레이드 방법

Control Plane 업그레이드를 시작하는 방법은 4가지가 있다.

## 방법 1: eksctl

```bash
~$ eksctl upgrade cluster --name $EKS_CLUSTER_NAME --approve
```

`--version` 플래그로 대상 버전을 지정할 수 있으며, 현재 버전 또는 1단계 높은 버전만 허용된다.

## 방법 2: AWS 콘솔

1. [Amazon EKS 콘솔](https://console.aws.amazon.com/eks/home#/clusters) 접속
2. 대상 클러스터 선택
3. **Upgrade now** 선택
4. 대상 Kubernetes 버전 선택 후 **Update**

![AWS 콘솔에서 Control Plane 업그레이드]({{site.url}}/assets/images/eks-upgrade-console-cp-upgrade.png){: .align-center}

## 방법 3: AWS CLI

```bash
~$ aws eks update-cluster-version \
    --region ${AWS_REGION} \
    --name $EKS_CLUSTER_NAME \
    --kubernetes-version 1.31
```

업그레이드 상태는 반환된 update ID로 확인할 수 있다.

```bash
# 업그레이드 상태 확인
~$ aws eks describe-update \
    --region ${AWS_REGION} \
    --name $EKS_CLUSTER_NAME \
    --update-id <update-id>
```

## 방법 4: Terraform (이 실습에서 사용)

이 워크숍에서는 Terraform을 사용하여 업그레이드를 진행한다. EKS 클러스터가 이미 Terraform으로 프로비저닝되어 있으므로, `variables.tf`의 버전 변수를 변경하고 `terraform apply`를 실행하면 된다.

<br>

# 실습: Terraform으로 Control Plane 업그레이드

## 1단계: Terraform 상태 초기화

먼저 Terraform 상태를 최신으로 동기화한다.

```bash
~$ cd ~/environment/terraform
~$ terraform init
~$ terraform plan
~$ terraform apply -auto-approve
```

## 2단계: cluster_version 변경

`variables.tf`에서 `cluster_version`을 `"1.30"`에서 `"1.31"`로 변경한다.

```hcl
variable "cluster_version" {
  description = "EKS cluster version."
  type        = string
  default     = "1.31"
}
```

![variables.tf에서 cluster_version 변경]({{site.url}}/assets/images/eks-upgrade-terraform-variables-tf.png){: .align-center}

## 3단계: Terraform Plan 및 Apply

```bash
~$ terraform plan && terraform apply -auto-approve
```

`terraform plan`을 실행하면, EKS 클러스터 Control Plane과 관련 리소스(Managed Node Group, 애드온 등)의 변경 계획이 표시된다. 특정 버전이나 AMI가 명시적으로 지정되지 않은 Managed Node Group은 자동으로 In-Place 업그레이드 또는 교체된다.

> `terraform apply`는 약 10~15분 소요된다.

## 4단계: 업그레이드 완료 확인

업그레이드가 완료되면 다음 명령으로 확인할 수 있다.

```bash
# AWS CLI로 확인
~$ aws eks describe-cluster --name $EKS_CLUSTER_NAME \
    --query "cluster.version" --output text

# 실행 결과
1.31
```

```bash
# kubectl로 확인
~$ kubectl version

# 실행 결과
Client Version: v1.31.0
Kustomize Version: v5.4.2
Server Version: v1.31.14-eks-40737a8
```

Server Version이 `v1.31.x`로 변경된 것을 확인할 수 있다.

> `kubectl get nodes`에서는 Control Plane이 보이지 않는다. EKS에서는 Control Plane을 AWS가 관리하므로, 노드 목록에 나타나지 않는다. Control Plane 버전은 `kubectl version`의 Server Version이나 `aws eks describe-cluster`로 확인한다.

<details markdown="1">
<summary><b>실습 CLI 전체 출력 (AWS CLI로 업그레이드)</b></summary>

워크숍에서 AWS CLI를 이용해 업그레이드한 과정의 전체 출력이다.

```bash
~$ aws eks update-cluster-version \
    --region ${AWS_REGION} \
    --name $EKS_CLUSTER_NAME \
    --kubernetes-version 1.31
{
    "update": {
        "id": "a856955d-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
        "status": "InProgress",
        "type": "VersionUpdate",
        "params": [
            {
                "type": "Version",
                "value": "1.31"
            },
            {
                "type": "PlatformVersion",
                "value": "eks.58"
            }
        ],
        "createdAt": "2026-05-01T14:03:19.378000+00:00",
        "errors": []
    }
}

# 업그레이드 상태 확인 (InProgress → Successful)
~$ aws eks describe-update \
    --region ${AWS_REGION} \
    --name $EKS_CLUSTER_NAME \
    --update-id a856955d-xxxx-xxxx-xxxx-xxxxxxxxxxxx
{
    "update": {
        "id": "a856955d-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
        "status": "Successful",
        "type": "VersionUpdate",
        "params": [
            {
                "type": "Version",
                "value": "1.31"
            },
            {
                "type": "PlatformVersion",
                "value": "eks.58"
            }
        ],
        "createdAt": "2026-05-01T14:03:19.378000+00:00",
        "errors": []
    }
}
```

</details>

<br>

# 트러블슈팅: Terraform 변수 미동기화

## 문제

Control Plane을 CLI나 콘솔로 먼저 업그레이드한 후, `variables.tf`의 `cluster_version`을 업데이트하지 않은 채 `terraform apply`를 실행하면 다음 에러가 발생한다.

```bash
│ Error: updating EKS Cluster (eksworkshop-eksctl) version:
│ operation error EKS: UpdateClusterVersion,
│ InvalidParameterException:
│ Unsupported Kubernetes minor version update from 1.31 to 1.30
```

## 원인

EKS는 **다운그레이드를 지원하지 않는다**. 클러스터의 Control Plane이 이미 1.31로 업그레이드된 상태인데, Terraform의 `cluster_version` 변수가 "1.30"으로 남아 있으면, Terraform이 현재 상태(1.31)와 desired 상태(1.30)의 차이를 감지하고 다운그레이드를 시도하게 된다.

## 해결

`terraform/variables.tf`에서 `cluster_version`을 현재 클러스터 버전 이상으로 맞춰야 한다.

```hcl
variable "cluster_version" {
  description = "EKS cluster version."
  type        = string
  default     = "1.31"
}
```

> Control Plane 업그레이드와 Terraform 변수 변경은 항상 **함께** 수행해야 한다. 콘솔/CLI로 먼저 업그레이드한 뒤 Terraform 변수를 업데이트하지 않으면, 다음 `terraform apply` 시 drift 에러가 발생한다.

<br>

# 정리

이 글에서는 EKS Control Plane을 1.30에서 1.31로 업그레이드하는 실습을 진행했다.

| 항목 | 내용 |
|------|------|
| 업그레이드 대상 | Control Plane (1.30 → 1.31) |
| 업그레이드 방식 | AWS Blue/Green 자동화 |
| 실습 도구 | Terraform (`variables.tf` 수정) |
| 소요 시간 | 약 10~15분 |
| 확인 방법 | `kubectl version`, `aws eks describe-cluster` |

Control Plane 업그레이드가 완료되었으니, 다음 글에서는 **EKS 애드온 업그레이드**를 진행한다.

<br>

# 참고 링크

- [Amazon EKS Cluster Upgrades - Control Plane](https://docs.aws.amazon.com/eks/latest/userguide/update-cluster.html)
- [EKS Terraform Blueprints](https://github.com/aws-ia/terraform-aws-eks-blueprints)
- [EKS Upgrade Workshop - In-Place Upgrades](https://catalog.us-east-1.prod.workshops.aws/workshops/fb76a304-9e44-43b9-90b4-5542d4c1b15d/en-US/module-3)

<br>
