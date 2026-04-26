---
title: "[EKS] EKS GPU 트러블슈팅: 2. 실습 환경 구성 - 1. Terraform 코드"
excerpt: "GPU 트러블슈팅 실습을 위한 EKS 환경을 Terraform으로 구성해 보자."
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
  - Terraform
  - GPU-Operator
  - AWS-EKS-Workshop-Study
  - AWS-EKS-Workshop-Study-Week-5
---

*정영준님의 AWS EKS Workshop Study(AEWS) [5주차 학습 내용](https://devfloor9.github.io/engineering-playbook/slides/eks-debugging/)을 기반으로 합니다.*

<br>

# TL;DR

[이전 실습 환경]({% post_url 2026-04-02-Kubernetes-EKS-Auth-01-Installation %}) 대비 주요 변경점은 다음과 같다.

- **GPU 노드 그룹 추가**: g5.xlarge(A10G 24GB) × 2대, AL2023 NVIDIA AMI, 단일 AZ 고정, taint/label로 GPU 전용 워크로드 격리
- **GPU Operator Helm 배포**: AMI에 포함된 드라이버/toolkit은 비활성, Device Plugin·NFD·DCGM 등 나머지 레이어를 Operator가 관리
- **보안그룹 실험 토글**: NCCL 통신 차단 시나리오 재현을 위해 보안그룹 규칙을 변수로 on/off
- **비용 가드**: GPU 노드 `desired_size=0` 기본, ASG `max_size=2`(쿼터 8 vCPU 한도 대응)

<br>

# 환경 개요

GPU 트러블슈팅 실습 환경의 핵심 구성을 정리한다.

| 항목 | 구성 | 이유 |
| --- | --- | --- |
| K8s 버전 | **1.35** | 최신 버전 |
| 시스템 노드 | t3.medium × **2** | 기존과 동일 |
| GPU 노드 | g5.xlarge × **2** (기본 0) | Option B — A10G 24GB, NCCL 멀티노드 재현 가능 |
| GPU AMI | **AL2023_x86_64_NVIDIA** | NVIDIA 드라이버/toolkit 포함 |
| GPU 배치 | **단일 AZ 고정** | NCCL 실험 시 크로스-AZ 지연 변수 제거 |
| GPU taint | `nvidia.com/gpu=true:NoSchedule` | 시스템 파드가 GPU 노드에 뜨지 않도록 차단 |
| GPU Operator | Helm (기본 비활성) | driver/toolkit off, Device Plugin/NFD/DCGM on |
| 보안그룹 | **실험 토글** 포함 | NCCL 차단 시나리오 재현용 |
| ASG max_size | **2** | G/VT 쿼터 8 vCPU 한도 초과 방지 |
| CP 로깅 | api, scheduler | 필요 최소 |
| addon | **7종** + cert-manager | 기존 실습 구성 유지 |
| 노드 접근 | SSM (SSH 없음) | 기존과 동일 |

[시리즈 개요]({% post_url 2026-04-09-Kubernetes-EKS-GPU-TroubleShooting-00-Overview %})에서 선택한 **Option B**(g5.xlarge × 2, On-Demand) 기반이다. [사전 준비]({% post_url 2026-04-09-Kubernetes-EKS-GPU-TroubleShooting-01-PreRequisites %})에서 확보한 G/VT 쿼터(8 vCPU)에 맞춰 ASG를 설계했다.

이 환경의 핵심 설계 원칙은 세 가지다.

1. **비용 가드**: GPU 노드의 `desired_size`를 기본 0으로 두어 최초 배포 시 GPU 인스턴스가 기동되지 않도록 한다. 실습 세션에서만 AWS CLI로 `desiredSize`를 2로 올리고, 끝나면 다시 0으로 내려 비용을 차단한다. Terraform variable은 노드 그룹 생성 시 초기값을 결정하며, 이후 스케일링은 [아래 별도 섹션](#비용-가드의-실제-스케일링-경로)에서 다룬다
2. **단일 AZ 고정**: GPU 노드를 같은 가용 영역에 배치하여, NCCL 통신 실험 시 크로스-AZ 네트워크 지연 변수를 제거한다
3. **보안그룹 실험 토글**: Terraform 변수 하나로 보안그룹 규칙을 on/off하여, NCCL 통신 차단 시나리오를 재현하고 원복할 수 있다

이제 Terraform 코드를 파일별로 살펴보자. 기존 실습 환경([1주차]({% post_url 2026-03-12-Kubernetes-EKS-01-01-01-Installation %}), [2주차]({% post_url 2026-03-19-Kubernetes-EKS-02-02-00-Installation %}), [4주차]({% post_url 2026-04-02-Kubernetes-EKS-Auth-01-Installation %}))과 달라진 부분을 중심으로 발췌하고, 전체 코드는 각 섹션의 접은 글에 포함한다.

<br>

# 디렉토리 구조

전체 코드는 [GitHub 저장소](https://github.com/sirzzang/aews-study/tree/main/5w)에서 확인할 수 있다.

```
.
├── aws_lb_controller_policy.json
├── cas_autoscaling_policy.json      # 새로 추가
├── eks.tf
├── externaldns_controller_policy.json
├── gpu_operator.tf                   # 새로 추가
├── outputs.tf
├── var.tf
├── versions.tf                       # 새로 추가
└── vpc.tf
```

기존 대비 세 파일이 추가되었다.

| 파일 | 역할 |
| --- | --- |
| `versions.tf` | Terraform/Provider 버전 고정 |
| `gpu_operator.tf` | NVIDIA GPU Operator Helm 배포 |
| `cas_autoscaling_policy.json` | Cluster Autoscaler용 IAM 정책 |

<br>

# versions.tf

기존 실습에서는 Provider 버전을 별도 파일로 분리하지 않았다. 이번에는 `versions.tf`를 두어 Terraform 버전과 Provider 버전을 명시적으로 관리한다.

```hcl
terraform {
  required_version = ">= 1.5.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = ">= 6.0"
    }
    helm = {
      source  = "hashicorp/helm"
      version = "~> 2.17"
    }
  }
}
```

주목할 점은 **Helm Provider를 v2 계열로 고정**한 것이다. Helm Provider v2.x와 v3.x는 `kubernetes` 블록 문법이 다르다. v2.x는 nested block(`kubernetes { ... }`)을, v3.x는 속성 문법(`kubernetes = { ... }`)을 사용한다. `gpu_operator.tf`에서 Helm Provider를 사용하므로 문법 호환을 위해 v2로 고정했다.

> **v2.17.0은 v2 계열의 마지막 릴리스**(2024-12-20)다. v3.0.0(2025-06-18)부터 `terraform-plugin-framework`로 마이그레이션되었고, 이후 v2에 대한 신규 패치 릴리스는 없다. 실습 환경에서는 v2.17로 충분하지만, 프로덕션에서는 보안 패치 및 Helm SDK 업데이트를 받을 수 있는 v3 계열로의 마이그레이션을 권장한다.

그 외 `cloudinit`, `null`, `tls`, `time` 등은 EKS/VPC 모듈이 전이적(transitive)으로 요구하는 Provider다. `terraform init` 시 자동 설치되지만, 협업과 재현성을 위해 명시적으로 기록해 두었다.

<details markdown="1">
<summary><b>versions.tf 전체 코드</b></summary>

```hcl
terraform {
  required_version = ">= 1.5.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = ">= 6.0"
    }
    # Helm v2 계열 고정 — v3.x 와 kubernetes 블록 문법이 다르므로
    # gpu_operator.tf 와 문법을 맞추기 위해 v2 고정
    helm = {
      source  = "hashicorp/helm"
      version = "~> 2.17"
    }
    # EKS/VPC 모듈이 전이적으로 요구하는 Provider
    # 재현성을 위해 명시적으로 기록
    cloudinit = {
      source  = "hashicorp/cloudinit"
      version = ">= 2.0.0"
    }
    null = {
      source  = "hashicorp/null"
      version = ">= 3.0.0"
    }
    tls = {
      source  = "hashicorp/tls"
      version = ">= 4.0.0"
    }
    time = {
      source  = "hashicorp/time"
      version = ">= 0.9.0"
    }
  }
}
```

</details>

<br>

# var.tf

기존 변수(클러스터 이름, 리전, 서브넷 등)는 [이전 실습]({% post_url 2026-04-02-Kubernetes-EKS-Auth-01-Installation %}#vartf)과 거의 동일하다. 새로 추가된 GPU 관련 변수 블록을 중심으로 살펴본다.

## GPU 노드 그룹 변수

```hcl
# 비용 가드: NG 최초 생성 시 초기값을 결정한다.
# 이미 존재하는 NG의 스케일링은 lifecycle.ignore_changes로 인해
# TF 경로로 반영되지 않으므로 AWS CLI로 수행한다.
#   aws eks update-nodegroup-config --scaling-config desiredSize=2
#   aws eks update-nodegroup-config --scaling-config desiredSize=0
variable "gpu_desired_size" {
  description = "GPU 노드 그룹 desired_size. 비용 가드를 위해 기본 0."
  type        = number
  default     = 0
}

variable "gpu_max_size" {
  description = "GPU 노드 그룹 max_size."
  type        = number
  default     = 2
}

variable "gpu_instance_type" {
  description = "GPU 워커 인스턴스 타입."
  type        = string
  default     = "g5.xlarge"
}

variable "gpu_node_disk_size" {
  description = "GPU 노드 EBS 볼륨 크기(GiB). GPU Operator/CUDA 이미지 고려 100GB 권장."
  type        = number
  default     = 100
}

variable "gpu_az_index" {
  description = "GPU 노드를 배치할 AZ 인덱스 (availability_zones 기준). 단일 AZ 고정 목적."
  type        = number
  default     = 0
}
```

핵심 포인트를 짚어 보자.

- **`gpu_desired_size` (기본 0)**: 비용 가드의 출발점이다. 노드 그룹 **최초 생성 시** `scaling_config.desired_size`의 초기값을 결정한다. 다만, 이미 존재하는 노드 그룹에 대해 이 변수를 바꿔 `terraform apply`해도 실제 AWS에는 반영되지 않는다. EKS 모듈의 `lifecycle.ignore_changes` 설계 때문이다. 이후 스케일 up/down은 AWS CLI(`aws eks update-nodegroup-config`)로 수행한다. 상세한 배경은 [아래](#비용-가드의-실제-스케일링-경로)에서 다룬다
- **`gpu_max_size` (기본 2)**: [사전 준비]({% post_url 2026-04-09-Kubernetes-EKS-GPU-TroubleShooting-01-PreRequisites %}#부분-승인8-vcpu-영향-분석)에서 G/VT 쿼터가 8 vCPU로 부분 승인되었다. g5.xlarge는 4 vCPU/대이므로 동시 실행 한도가 2대다. max_size를 4로 두면 ASG 롤링(새 노드 선행 기동 → 기존 노드 drain) 시 일시적으로 3~4대가 필요해져 쿼터 초과로 실패한다. **ASG 레벨에서 2로 잠가 쿼터 초과 경로를 차단**한다. 다만 이 제한은 LaunchTemplate 변경(예: [디스크 크기 수정](#disk_size)) 시 EKS가 자동으로 시도하는 rolling update도 차단한다 — surge 노드를 띄울 여유가 없어 `VcpuLimitExceeded`로 실패하므로, LT 변경 시에는 scale-down(0) → apply → scale-up(2)으로 우회해야 한다
- **`gpu_node_disk_size` (100GB)**: GPU Operator 컴포넌트와 CUDA 컨테이너 이미지가 크므로 시스템 노드(30GB)보다 넉넉하게 잡았다. 이 변수는 `block_device_mappings.xvda.ebs.volume_size`로 전달된다. `disk_size` 속성으로 넘기면 custom LT 경로에서 무시되므로 주의한다([아래 참고](#disk_size))
- **`gpu_az_index` (0)**: `availability_zones` 리스트에서 하나의 AZ만 선택한다. NCCL 실험에서 크로스-AZ 지연을 제거하기 위함이다

### 비용 가드의 실제 스케일링 경로

`gpu_desired_size` 변수에 대해 한 가지 중요한 제약이 있다. 이 변수는 **노드 그룹 최초 생성 시점의 초기값**으로만 동작하며, 이미 존재하는 노드 그룹의 `desiredSize`를 변경하는 데는 사용할 수 없다.

원인은 `terraform-aws-modules/eks` v21의 managed node group submodule에 있다. 이 모듈은 `aws_eks_node_group` 리소스에 다음과 같은 lifecycle 블록을 포함한다.

```hcl
lifecycle {
  create_before_destroy = true
  ignore_changes = [
    scaling_config[0].desired_size,
  ]
}
```

**설계 의도**: Cluster Autoscaler나 Karpenter 같은 오토스케일러가 런타임에 `desiredSize`를 동적으로 조정한다. 만약 Terraform이 매 `apply`마다 이 값을 코드에 선언된 값으로 되돌리면, 오토스케일러와 충돌이 발생한다. 이를 방지하기 위해 모듈이 명시적으로 `desired_size` 변경을 무시하도록 설계된 것이다.

**주의**: Terraform variable은 선언만 하면 언제든 값을 바꿔 apply할 수 있을 것 같지만, `desired_size`는 그렇지 않다. 위 `ignore_changes` 때문에 이 변수는 노드 그룹 생성 시점의 초기값으로만 유효하다. `-var gpu_desired_size=0`을 재실행한다고 GPU 노드가 종료되지 않는다.

<details markdown="1">
<summary><b>참고: <code>-var gpu_desired_size=2</code>를 실제로 적용해 본 결과</b></summary>

이미 `desired_size=0`으로 생성된 GPU 노드 그룹에 `-var gpu_desired_size=2`를 주고 `terraform plan`을 실행하면, plan diff에 scaling 변경이 **잡히지 않는다**. TF state에만 기록될 뿐 실제 AWS EKS `scalingConfig`는 변하지 않는다. `aws eks describe-nodegroup`으로 확인해도 `desiredSize`는 여전히 0이다.

</details>

따라서 이미 존재하는 노드 그룹의 스케일 up/down은 **AWS CLI**로 수행한다.

```bash
# GPU 노드 스케일 업 (실습 세션 진입 시)
aws eks update-nodegroup-config \
  --cluster-name myeks5w \
  --nodegroup-name myeks5w-ng-gpu \
  --scaling-config minSize=0,maxSize=2,desiredSize=2

# GPU 노드 스케일 다운 (실습 종료 시)
aws eks update-nodegroup-config \
  --cluster-name myeks5w \
  --nodegroup-name myeks5w-ng-gpu \
  --scaling-config minSize=0,maxSize=2,desiredSize=0
```

> 모듈 내부의 `lifecycle` 블록은 외부에서 override할 수 없다. 이 동작을 바꾸려면 모듈을 포크하거나 로컬에서 수정해야 하는데, 유지보수 부담이 크다. CLI 스케일링은 모듈의 설계 의도와 정렬되며, Terraform state를 건드리지 않는 깔끔한 경로다.

시점별 동작을 정리하면 다음과 같다.

| 시점 | 경로 | 동작 |
| --- | --- | --- |
| NG 최초 생성 | `terraform apply` + `-var gpu_desired_size=N` | `scaling_config.desired_size = N`으로 NG 생성. **동작함** |
| NG 이미 존재 | `terraform apply` + `-var gpu_desired_size=N` | `ignore_changes`로 무시. state만 갱신, **AWS 미반영** |
| NG 이미 존재 | `aws eks update-nodegroup-config --scaling-config desiredSize=N` | AWS API 직접 호출. **즉시 반영** |

## GPU Operator 변수

```hcl
variable "enable_gpu_operator" {
  description = "NVIDIA GPU Operator helm_release 생성 여부. 기본 true(운영 상태). 최초 클러스터 부트스트랩 시에만 -var enable_gpu_operator=false 로 명시적 override."
  type        = bool
  default     = true
}

variable "gpu_operator_namespace" {
  description = "GPU Operator 설치 네임스페이스."
  type        = string
  default     = "gpu-operator"
}

variable "gpu_operator_chart_version" {
  description = "NVIDIA GPU Operator Helm 차트 버전. AL2023 NVIDIA AMI + driver/toolkit disabled 운영 전제에 맞춰 K8s 1.35 호환 최신 stable 로 고정."
  type        = string
  default     = "v26.3.1"
}
```

**`default = true`로 둔 이유에 주의한다.** 이 프로젝트의 "일상 상태"는 GPU Operator가 설치되어 있는 운영 중 구성이다. 만약 `default = false`로 두면, GPU Operator 설치 후 매번 `-var enable_gpu_operator=true`를 빠뜨리지 않아야 한다. 빠뜨리는 순간 `count = var.enable_gpu_operator ? 1 : 0`이 `count = 0`으로 평가되어 **`helm_release.gpu_operator`가 destroy 대상**으로 잡힌다. 디스크 변경 같은 무관한 작업을 하다가 GPU Operator를 날릴 수 있다.

`default = true`로 두면 평상시 `terraform apply`만으로 안전하다. 최초 클러스터 부트스트랩 시(아직 GPU 노드가 없어 Operator를 설치하면 안 되는 단계)에만 `-var enable_gpu_operator=false`로 명시적 override한다.

차트 버전은 **반드시 핀(pin)해야 한다.** `null`(최신)로 두면 Helm이 repo 기준 latest를 받아오기 때문에, 실습 도중 예고 없이 major 버전이 바뀔 수 있다. 수개월 후에도 실습을 통해 동일한 환경을 재현할 수 있으려면 버전 고정이 필수다.

`v26.3.1`을 선택한 근거는 [NVIDIA GPU Operator compatibility matrix](https://docs.nvidia.com/datacenter/cloud-native/gpu-operator/latest/platform-support.html)다.

| 기준 | 확인 결과 |
| --- | --- |
| K8s 지원 범위 | v26.3.x는 **K8s 1.32~1.35** 지원. 이 실습의 1.35에 부합 |
| 이전 stable (v25.10.x) | K8s 1.29~1.34까지만 지원. **1.35 미포함** |
| 기본 NVIDIA 드라이버 | v26.3.x 기본값은 580.126.20 — AL2023 NVIDIA AMI의 드라이버 580과 **같은 major stream** |
| AL2023 공식 지원 여부 | NVIDIA matrix에 AL2023은 **미등재**. 단, driver/toolkit disabled 운영은 AWS 공식 권장 경로 |
| values 스키마 호환 | `helm show values --version v26.3.1` 결과, driver/toolkit/devicePlugin/nfd/dcgmExporter/validator/operator 키 구조가 `gpu_operator.tf` 오버라이드와 호환 |

> **참고**: NVIDIA 공식 matrix에 Amazon Linux 2023은 지원 OS 목록에 등재되어 있지 않다. 하지만 `driver.enabled=false` + `toolkit.enabled=false`로 운영하면 호스트(AMI)의 드라이버를 그대로 사용하므로, OS 레벨 드라이버 빌드 호환성 문제를 우회할 수 있다. 이것이 [AWS 공식 가이드](https://docs.aws.amazon.com/eks/latest/userguide/ml-eks-optimized-ami.html)의 권장 경로다.

> 버전 갱신이 필요한 경우, `helm search repo nvidia/gpu-operator --versions | head`로 최신 stable을 확인한 뒤 이 default 값만 변경하여 apply하면 된다.

## 보안그룹 실험 토글

```hcl
variable "enable_aux_sg_vpc_allow" {
  description = "보조 SG에 VPC 대역 all-traffic ingress 규칙을 둘지 여부."
  type        = bool
  default     = true
}

variable "node_sg_enable_recommended_rules" {
  description = "EKS 모듈의 node_security_group_enable_recommended_rules."
  type        = bool
  default     = true
}
```

두 변수 모두 기본 `true`(정상 동작)다. NCCL 보안그룹 차단 실험 시 둘 다 `false`로 apply하면 노드 간 NCCL 통신 경로가 차단된다. 원복은 다시 `true`로 돌려 apply 1회면 된다.

```bash
# NCCL 차단 실험
terraform apply \
  -var enable_aux_sg_vpc_allow=false \
  -var node_sg_enable_recommended_rules=false

# 원복
terraform apply \
  -var enable_aux_sg_vpc_allow=true \
  -var node_sg_enable_recommended_rules=true
```

> **주의**: `node_sg_enable_recommended_rules=false`는 EKS 모듈의 recommended rules 전체를 내리므로, cluster→node webhook 포트(4443/6443/8443/9443/10251)도 함께 꺼진다. 컨트롤러 webhook이 깨질 수 있으므로 실험은 짧게, 원복은 즉시 수행한다. apply 전 `terraform plan` diff로 영향 범위를 반드시 확인한다.

<details markdown="1">
<summary><b>var.tf 전체 코드</b></summary>

```hcl
########################
# Cluster basics
########################

variable "ClusterBaseName" {
  description = "Base name of the cluster."
  type        = string
  default     = "myeks"
}

variable "KubernetesVersion" {
  description = "Kubernetes version for the EKS cluster."
  type        = string
  default     = "1.35"
}

variable "TargetRegion" {
  description = "AWS region where the resources will be created."
  type        = string
  default     = "ap-northeast-2"
}

variable "availability_zones" {
  description = "List of availability zones."
  type        = list(string)
  default     = ["ap-northeast-2a", "ap-northeast-2b", "ap-northeast-2c"]
}

########################
# VPC / subnets
########################

variable "VpcBlock" {
  description = "CIDR block for the VPC."
  type        = string
  default     = "192.168.0.0/16"
}

variable "public_subnet_blocks" {
  description = "List of CIDR blocks for the public subnets."
  type        = list(string)
  default     = ["192.168.0.0/22", "192.168.4.0/22", "192.168.8.0/22"]
}

variable "private_subnet_blocks" {
  description = "List of CIDR blocks for the private subnets."
  type        = list(string)
  default     = ["192.168.12.0/22", "192.168.16.0/22", "192.168.20.0/22"]
}

########################
# System node group
########################

variable "WorkerNodeInstanceType" {
  description = "EC2 instance type for the system worker nodes."
  type        = string
  default     = "t3.medium"
}

variable "WorkerNodeCount" {
  description = "Number of system worker nodes."
  type        = number
  default     = 2
}

variable "WorkerNodeVolumesize" {
  description = "Volume size for system worker nodes (in GiB)."
  type        = number
  default     = 30
}

########################
# GPU node group
########################

variable "gpu_desired_size" {
  description = "GPU 노드 그룹 desired_size. 비용 가드를 위해 기본 0."
  type        = number
  default     = 0
}

variable "gpu_max_size" {
  description = "GPU 노드 그룹 max_size."
  type        = number
  default     = 2
}

variable "gpu_instance_type" {
  description = "GPU 워커 인스턴스 타입."
  type        = string
  default     = "g5.xlarge"
}

variable "gpu_node_disk_size" {
  description = "GPU 노드 EBS 볼륨 크기(GiB). GPU Operator/CUDA 이미지 고려 100GB 권장."
  type        = number
  default     = 100
}

variable "gpu_az_index" {
  description = "GPU 노드를 배치할 AZ 인덱스 (availability_zones 기준). 단일 AZ 고정 목적."
  type        = number
  default     = 0
}

########################
# GPU Operator (helm) — 기본 활성
########################

# default=true 인 이유: 이 프로젝트의 "일상 상태" 는 GPU Operator 가 설치되어 있는 운영 중 구성.
# 매 plan/apply 마다 CLI 로 -var 를 빠뜨리면 state 의 helm_release 가 destroy 대상으로 잡히는 구조를 방지.
#
# 최초 배포 시(아직 operator 설치 전)에는 반드시 다음과 같이 명시:
#   terraform plan  -var enable_gpu_operator=false -out=...
#   terraform apply ...
# GPU Operator 설치 단계부터는 -var 플래그 없이 default(true) 사용.
variable "enable_gpu_operator" {
  description = "NVIDIA GPU Operator helm_release 생성 여부. 기본 true(운영 상태). 최초 클러스터 부트스트랩 시에만 -var enable_gpu_operator=false 로 명시적 override."
  type        = bool
  default     = true
}

variable "gpu_operator_namespace" {
  description = "GPU Operator 설치 네임스페이스."
  type        = string
  default     = "gpu-operator"
}

# 핀 근거:
#   - K8s 1.35 는 GPU Operator v26.3.x 계열부터 공식 지원 (v25.10.x 이하 미지원)
#   - v26.3.1 이 조회 시점 최신 stable. v26.3.0 대비 SLES/ARM 수정이 주이며
#     AL2023 x86_64 + driver/toolkit disabled 환경에 실질 영향 없음
#   - AL2023 NVIDIA AMI 에 NVIDIA driver 580 / container toolkit 이 포함
#     → Operator 는 driver.enabled=false, toolkit.enabled=false 로 두고
#       devicePlugin/NFD/DCGM/validator 레이어만 사용.
#     이 운영은 AWS 공식 가이드(docs.aws.amazon.com ml-eks-optimized-ami) 권장 경로
#   - null(=latest) 유지 시 차후 v27.x 릴리스로 자동 major bump 위험 → 고정 필수
variable "gpu_operator_chart_version" {
  description = "NVIDIA GPU Operator Helm 차트 버전. AL2023 NVIDIA AMI + driver/toolkit disabled 운영 전제에 맞춰 K8s 1.35 호환 최신 stable 로 고정."
  type        = string
  default     = "v26.3.1"
}

########################
# 보안그룹 실험 토글
########################

variable "enable_aux_sg_vpc_allow" {
  description = "보조 SG에 VPC 대역 all-traffic ingress 규칙을 둘지 여부."
  type        = bool
  default     = true
}

variable "node_sg_enable_recommended_rules" {
  description = "EKS 모듈의 node_security_group_enable_recommended_rules."
  type        = bool
  default     = true
}
```

</details>

<br>

# vpc.tf

VPC 구성은 [4주차 실습 환경]({% post_url 2026-04-02-Kubernetes-EKS-Auth-01-Installation %}#vpctf)과 동일하다. 퍼블릭 서브넷 3개 + 프라이빗 서브넷 3개, NAT Gateway 1개 구성이다. 워커 노드는 프라이빗 서브넷에 배치된다.

<details markdown="1">
<summary><b>vpc.tf 전체 코드</b></summary>

```hcl
########################
# VPC
########################

module "vpc" {
  source  = "terraform-aws-modules/vpc/aws"
  version = "~>6.5"

  name = "${var.ClusterBaseName}-VPC"
  cidr = var.VpcBlock
  azs  = var.availability_zones

  enable_dns_support   = true
  enable_dns_hostnames = true

  public_subnets  = var.public_subnet_blocks
  private_subnets = var.private_subnet_blocks

  enable_nat_gateway     = true
  single_nat_gateway     = true
  one_nat_gateway_per_az = false

  manage_default_network_acl = false

  map_public_ip_on_launch = true

  igw_tags = {
    "Name" = "${var.ClusterBaseName}-IGW"
  }

  nat_gateway_tags = {
    "Name" = "${var.ClusterBaseName}-NAT"
  }

  public_subnet_tags = {
    "Name"                   = "${var.ClusterBaseName}-PublicSubnet"
    "kubernetes.io/role/elb" = "1"
  }

  private_subnet_tags = {
    "Name"                            = "${var.ClusterBaseName}-PrivateSubnet"
    "kubernetes.io/role/internal-elb" = "1"
  }

  tags = {
    "Environment" = "cloudneta-lab"
  }
}
```

</details>

<br>

# eks.tf

가장 변경이 많은 파일이다. GPU 관련 추가 사항을 중심으로 살펴본다.

## EKS 최적화 AMI

```hcl
# 시스템 노드 — AL2023 x86_64 standard
data "aws_ssm_parameter" "eks_ami_al2023_std" {
  name = "/aws/service/eks/optimized-ami/${var.KubernetesVersion}/amazon-linux-2023/x86_64/standard/recommended/image_id"
}

# GPU 노드 — AL2023 x86_64 NVIDIA 최적화 AMI
data "aws_ssm_parameter" "eks_ami_al2023_nvidia" {
  name = "/aws/service/eks/optimized-ami/${var.KubernetesVersion}/amazon-linux-2023/x86_64/nvidia/recommended/image_id"
}
```

AWS는 EKS 최적화 AMI ID를 SSM Parameter Store로 제공한다. `standard`는 일반 노드용, `nvidia`는 **NVIDIA 드라이버와 Container Toolkit이 사전 설치된** GPU 노드용 AMI다.

실제 노드 그룹에서는 `ami_type` 속성으로 AMI를 선택하므로, 이 data source는 AMI 버전 확인·검증 용도로 사용한다.

## 보안그룹

기존에는 보조 보안그룹에 VPC 대역 all-traffic ingress를 무조건 열어뒀다. 이번에는 **변수 토글로 on/off 가능**하게 변경했다.

```hcl
resource "aws_security_group" "node_group_sg" {
  name        = "${var.ClusterBaseName}-node-group-sg"
  description = "Auxiliary security group for EKS Node Group (shared by system & GPU NG)"
  vpc_id      = module.vpc.vpc_id

  tags = {
    Name = "${var.ClusterBaseName}-node-group-sg"
  }
}

# VPC 대역 all-traffic ingress — 토글로 제어
resource "aws_security_group_rule" "allow_vpc_all" {
  count = var.enable_aux_sg_vpc_allow ? 1 : 0

  type              = "ingress"
  from_port         = 0
  to_port           = 0
  protocol          = "-1"
  cidr_blocks       = [var.VpcBlock]
  security_group_id = aws_security_group.node_group_sg.id
}
```

`count = var.enable_aux_sg_vpc_allow ? 1 : 0`으로 규칙 자체의 생성/삭제를 제어한다. `false`로 apply하면 이 규칙이 사라져 VPC 대역 내 트래픽도 차단된다.

추가로 **egress 안전망**을 별도로 둔다.

```hcl
resource "aws_security_group_rule" "aux_egress_all" {
  type              = "egress"
  from_port         = 0
  to_port           = 0
  protocol          = "-1"
  cidr_blocks       = ["0.0.0.0/0"]
  security_group_id = aws_security_group.node_group_sg.id
  description       = "Node egress to anywhere"
}
```

이 egress 규칙은 항상 유지한다. `node_sg_enable_recommended_rules=false`로 EKS 모듈의 node SG egress_all이 함께 빠지는 부작용에 대한 안전망이다. 보안그룹은 여러 개 중 하나라도 egress를 허용하면 통과하므로, 노드가 외부(EKS API, ECR, NGC 등)로 나가는 경로를 보장한다.

## IAM 정책: Cluster Autoscaler

기존 LB Controller, ExternalDNS 정책에 더해 **Cluster Autoscaler(CAS) 정책**이 새로 추가되었다.

```hcl
resource "aws_iam_policy" "aws_cas_autoscaler_policy" {
  name        = "${var.ClusterBaseName}CasAutoScalerPolicy"
  description = "Policy for allowing CAS to management AWS AutoScaling"
  policy      = file("cas_autoscaling_policy.json")
}
```

CAS는 파드가 리소스 부족으로 Pending 상태에 빠지면 ASG를 스케일 아웃하고, 여유 노드가 있으면 스케일 인하는 Kubernetes 오토스케일러다. CAS가 런타임에 `desiredSize`를 동적으로 변경하기 때문에, EKS 모듈은 `lifecycle.ignore_changes`로 `desired_size`를 Terraform 관리 대상에서 제외한다([비용 가드의 실제 스케일링 경로](#비용-가드의-실제-스케일링-경로) 참고). CAS가 ASG를 제어하려면 `autoscaling:SetDesiredCapacity`, `autoscaling:TerminateInstanceInAutoScalingGroup` 등의 권한이 필요하다.

## 입력 검증

```hcl
resource "terraform_data" "validate_inputs" {
  lifecycle {
    precondition {
      condition     = var.gpu_max_size >= var.gpu_desired_size
      error_message = "gpu_max_size (${var.gpu_max_size}) must be >= gpu_desired_size (${var.gpu_desired_size})."
    }
    precondition {
      condition     = var.gpu_az_index >= 0 && var.gpu_az_index < length(var.availability_zones)
      error_message = "gpu_az_index (${var.gpu_az_index}) is out of range for availability_zones list (length ${length(var.availability_zones)})."
    }
  }
}
```

`terraform plan` 단계에서 잘못된 입력을 선차단한다. `gpu_max_size < gpu_desired_size`로 apply하면 EKS Managed Node Group 생성이 15~20분 뒤에 실패하는데, 그 시간을 낭비하지 않기 위한 가드다.

## GPU 단일 AZ 서브넷

```hcl
locals {
  gpu_subnet_ids = [module.vpc.private_subnets[var.gpu_az_index]]
  gpu_subnet_az  = var.availability_zones[var.gpu_az_index]
}
```

VPC 모듈은 `azs` 순서대로 `private_subnets`를 반환하므로, `gpu_az_index`로 하나만 선택한다. GPU 노드를 같은 AZ에 고정하여 NCCL 실험의 네트워크 변수를 최소화한다.

## EKS 모듈

### 노드 보안그룹 설정

```hcl
module "eks" {
  source  = "terraform-aws-modules/eks/aws"
  version = "~> 21.0"

  # ...

  create_node_security_group                   = true
  node_security_group_enable_recommended_rules = var.node_sg_enable_recommended_rules

  # ...
}
```

EKS 모듈 v21의 recommended rules에는 ephemeral 포트(1025-65535/tcp) self-reference 규칙이 포함되어 있다. 이 규칙이 **NCCL 통신의 실질 경로**다. `var.node_sg_enable_recommended_rules=false`로 내리면 해당 self-reference가 빠져 NCCL 차단을 재현할 수 있다.

### 시스템 노드 그룹

기존과 대부분 동일하되, **NodeConfig로 maxPods를 50으로 설정**하고 **CAS 정책을 추가**한 점이 다르다. CAS 정책은 시스템 노드 그룹에도 부여해야 한다. Cluster Autoscaler 컨트롤러 파드는 시스템 노드에서 실행되면서 **모든** 노드 그룹(시스템 + GPU)의 ASG를 조회·조정하는데, 이 때 파드가 실행되는 노드의 Instance Profile 권한을 사용하기 때문이다.

```hcl
primary = {
  # ... (기존과 동일한 설정)

  iam_role_additional_policies = {
    "${var.ClusterBaseName}AWSLoadBalancerControllerPolicy" = aws_iam_policy.aws_lb_controller_policy.arn
    "${var.ClusterBaseName}ExternalDNSPolicy"               = aws_iam_policy.external_dns_policy.arn
    "${var.ClusterBaseName}CasAutoScalerPolicy"             = aws_iam_policy.aws_cas_autoscaler_policy.arn
    AmazonSSMManagedInstanceCore                            = "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
  }

  cloudinit_pre_nodeadm = [
    {
      content_type = "application/node.eks.aws"
      content      = <<-EOT
        ---
        apiVersion: node.eks.aws/v1alpha1
        kind: NodeConfig
        spec:
          kubelet:
            config:
              maxPods: 50
      EOT
    },
    {
      content_type = "text/x-shellscript"
      content      = <<-EOT
        #!/bin/bash
        dnf update -y
        dnf install -y tree bind-utils tcpdump nvme-cli links sysstat ipset htop
      EOT
    }
  ]
}
```

`content_type = "application/node.eks.aws"`는 AL2023의 nodeadm 설정이다. `maxPods: 50`은 VPC CNI의 ENI 제한보다 높은 값을 직접 지정하여 파드 스케줄링 여유를 확보한다.

### GPU 노드 그룹

이번 실습의 핵심이다.

```hcl
gpu = {
  name            = "${var.ClusterBaseName}-ng-gpu"
  use_name_prefix = false
  ami_type        = "AL2023_x86_64_NVIDIA"
  capacity_type   = "ON_DEMAND"
  instance_types  = [var.gpu_instance_type]
  desired_size    = var.gpu_desired_size
  max_size        = var.gpu_max_size
  min_size        = 0

  block_device_mappings = {
    xvda = {
      device_name = "/dev/xvda"
      ebs = {
        volume_size           = var.gpu_node_disk_size
        volume_type           = "gp3"
        delete_on_termination = true
      }
    }
  }

  subnet_ids      = local.gpu_subnet_ids
  vpc_security_group_ids = [aws_security_group.node_group_sg.id]

  iam_role_name            = "${var.ClusterBaseName}-ng-gpu"
  iam_role_use_name_prefix = false
  iam_role_additional_policies = {
    AmazonSSMManagedInstanceCore = "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
  }

  metadata_options = {
    http_endpoint               = "enabled"
    http_tokens                 = "required"
    http_put_response_hop_limit = 2
  }

  labels = {
    tier             = "gpu"
    "nvidia.com/gpu" = "true"
  }

  taints = {
    gpu = {
      key    = "nvidia.com/gpu"
      value  = "true"
      effect = "NO_SCHEDULE"
    }
  }

  cloudinit_pre_nodeadm = [
    {
      content_type = "text/x-shellscript"
      content      = <<-EOT
        #!/bin/bash
        dnf install -y tree bind-utils tcpdump nvme-cli links sysstat ipset htop pciutils
      EOT
    }
  ]

  tags = {
    "k8s.io/cluster-autoscaler/node-template/label/nvidia.com/gpu" = "true"
    "k8s.io/cluster-autoscaler/node-template/taint/nvidia.com/gpu" = "true:NoSchedule"
  }
}
```

주요 설정을 하나씩 살펴보자.

| 설정 | 값 | 설명 |
| --- | --- | --- |
| `ami_type` | `AL2023_x86_64_NVIDIA` | NVIDIA 드라이버/toolkit 포함 AMI |
| `capacity_type` | `ON_DEMAND` | SPOT 중단 위험 제거 |
| `desired_size` | `0` (기본) | 비용 가드 — NG 생성 시 초기값. 이후 스케일링은 [CLI 경로](#비용-가드의-실제-스케일링-경로) |
| `max_size` | `2` | G/VT 쿼터 8 vCPU 한도 대응 |
| `min_size` | `0` | 완전 종료 가능 |
| `subnet_ids` | `local.gpu_subnet_ids` | 단일 AZ 고정 (아래 참고) |
| `block_device_mappings` | `xvda`, 100GB gp3 | LT에 직접 주입. `disk_size`는 custom LT 경로에서 무시됨 ([아래 참고](#disk_size)) |

#### subnet_ids

**`subnet_ids` 속성명에 주의해야 한다.** `terraform-aws-modules/eks/aws` v21의 managed node group submodule은 서브넷을 받는 변수명이 `subnet_ids`다. `subnets`처럼 다른 키를 넘기면 Terraform 모듈은 정의되지 않은 키를 **조용히 무시**하고, 내부의 `coalesce(each.value.subnet_ids, var.subnet_ids)` 로직에서 상위 모듈의 `subnet_ids`(= 3개 private subnet, multi-AZ)로 fallback한다. 단일 AZ를 의도했지만 실제 노드 그룹은 3개 서브넷(multi-AZ)으로 구성되는 것이다. `desired_size=0`이라 즉시 체감 영향은 없지만, desired를 올리는 순간 GPU 노드가 서로 다른 AZ에 분산될 수 있다.

이후 NCCL SG 차단 실험은 "같은 AZ, 같은 서브넷 내에서 SG가 pod-pod 통신을 막는다"가 전제다. AZ가 달라지면 cross-AZ 라우팅과 레이턴시라는 의도하지 않은 변인이 추가되어 실험 해석이 흐려진다. 속성명을 `subnet_ids`로 정확히 지정하여 단일 AZ 고정 의도가 코드에 반영되도록 한다.

#### disk_size

**`disk_size`가 아니라 `block_device_mappings`를 사용해야 한다.** `terraform-aws-modules/eks/aws` v21의 managed node group submodule은 `ami_type`을 지정하면서 동시에 `cloudinit_pre_nodeadm` 등 custom Launch Template 경로를 타게 되는데, 이 경로에서 `disk_size` 속성은 **조용히 무시**된다. 모듈 내부의 Launch Template 리소스가 `block_device_mappings`를 직접 구성하지 않으면 AWS는 `BlockDeviceMappings=null`로 렌더하고, AMI 기본값으로 fallback한다. AL2023 NVIDIA AMI의 기본 루트 볼륨은 **20GB**이므로, `disk_size=100`을 넘겼더라도 실제 노드의 EBS는 20GB로 잡힌다.

이 문제는 `subnet_ids` 속성명 문제와 같은 패턴이다. 모듈이 정의하지 않은 키를 넘기면 에러 없이 무시되고, 의도와 다른 기본값으로 동작한다. `desired_size=0`이라 즉시 체감하지 못하지만, 실제 GPU 노드를 올리는 순간 `ephemeral-storage`가 ~17GiB밖에 잡히지 않는다. vLLM 같은 대형 모델 서빙(Llama-3-8B FP16 ≈ 15GB 체크포인트)에서는 모델 로딩 시 ephemeral storage 부족으로 Pod이 Evict될 수 있다.

`block_device_mappings`로 Launch Template에 직접 주입하면, 모듈이 LT의 `block_device_mappings` 블록을 렌더링하고 AWS에 100GB gp3가 정확히 전달된다.

#### taint, label, CAS tag

taint/label/tag 세 가지가 맞물려 "GPU 노드에는 GPU 워크로드만, GPU 워크로드는 GPU 노드에만" 스케줄링되도록 제어한다.

- **taint** `nvidia.com/gpu=true:NoSchedule`: 이 taint을 toleration하지 않는 파드(시스템 파드, 일반 워크로드)는 GPU 노드에 스케줄링되지 않는다. GPU 리소스를 GPU 워크로드 전용으로 보호한다
- **label** `nvidia.com/gpu=true`: GPU Operator의 DaemonSet과 사용자 워크로드가 `nodeSelector`로 GPU 노드를 타겟팅할 때 사용한다
- **CAS tag**: `k8s.io/cluster-autoscaler/node-template/...` 태그는 Cluster Autoscaler가 이 노드 그룹의 label/taint을 인식하여 GPU 워크로드 Pending 시 올바른 노드 그룹을 스케일 아웃하도록 한다

#### 초기화 스크립트

시스템 노드 대비 **`pciutils`가 추가**되었다. `lspci` 명령으로 GPU 디바이스(A10G)를 확인할 수 있다. GPU AMI에는 이미 NVIDIA 드라이버가 포함되어 있으므로 별도 드라이버 설치는 불필요하다.

### Addon

```hcl
addons = {
  coredns                = { most_recent = true }
  kube-proxy             = { most_recent = true }
  vpc-cni                = { most_recent = true, before_compute = true }
  metrics-server         = { most_recent = true }
  external-dns           = { most_recent = true }
  eks-pod-identity-agent = { most_recent = true }
  cert-manager           = { most_recent = true }
}
```

기존 실습과 거의 동일하다. 7종 addon + cert-manager 구성이다.

### Control Plane 로깅

```hcl
enabled_log_types = [
  "api",
  "scheduler"
]
```

4주차에서는 인증/인가 디버깅을 위해 5종 전부를 켰지만, 이번에는 `api`와 `scheduler`만 활성화했다. GPU 트러블슈팅에서는 인증 로그보다 API 요청/스케줄링 로그가 더 유용하고, 불필요한 로그 비용을 절감한다.

<details markdown="1">
<summary><b>eks.tf 전체 코드</b></summary>

```hcl
########################
# Provider Definitions #
########################

provider "aws" {
  region = var.TargetRegion
}

########################
# EKS-optimized AMI (system / NVIDIA)
########################

data "aws_ssm_parameter" "eks_ami_al2023_std" {
  name = "/aws/service/eks/optimized-ami/${var.KubernetesVersion}/amazon-linux-2023/x86_64/standard/recommended/image_id"
}

data "aws_ssm_parameter" "eks_ami_al2023_nvidia" {
  name = "/aws/service/eks/optimized-ami/${var.KubernetesVersion}/amazon-linux-2023/x86_64/nvidia/recommended/image_id"
}

########################
# Security Group Setup
########################

resource "aws_security_group" "node_group_sg" {
  name        = "${var.ClusterBaseName}-node-group-sg"
  description = "Auxiliary security group for EKS Node Group (shared by system & GPU NG)"
  vpc_id      = module.vpc.vpc_id

  tags = {
    Name = "${var.ClusterBaseName}-node-group-sg"
  }
}

resource "aws_security_group_rule" "allow_vpc_all" {
  count = var.enable_aux_sg_vpc_allow ? 1 : 0

  type              = "ingress"
  from_port         = 0
  to_port           = 0
  protocol          = "-1"
  cidr_blocks       = [var.VpcBlock]
  security_group_id = aws_security_group.node_group_sg.id
}

resource "aws_security_group_rule" "aux_egress_all" {
  type              = "egress"
  from_port         = 0
  to_port           = 0
  protocol          = "-1"
  cidr_blocks       = ["0.0.0.0/0"]
  security_group_id = aws_security_group.node_group_sg.id
  description       = "Node egress to anywhere (safety net for C-3 experiment)"
}

################
# IAM Policies
################

resource "aws_iam_policy" "aws_lb_controller_policy" {
  name        = "${var.ClusterBaseName}AWSLoadBalancerControllerPolicy"
  description = "Policy for allowing AWS LoadBalancerController to modify AWS ELB"
  policy      = file("aws_lb_controller_policy.json")
}

resource "aws_iam_policy" "external_dns_policy" {
  name        = "${var.ClusterBaseName}ExternalDNSPolicy"
  description = "Policy for allowing ExternalDNS to modify Route 53 records"
  policy      = file("externaldns_controller_policy.json")
}

resource "aws_iam_policy" "aws_cas_autoscaler_policy" {
  name        = "${var.ClusterBaseName}CasAutoScalerPolicy"
  description = "Policy for allowing CAS to management AWS AutoScaling"
  policy      = file("cas_autoscaling_policy.json")
}

########################
# 입력 검증 (apply 전 plan 단계에서 gate)
########################

resource "terraform_data" "validate_inputs" {
  lifecycle {
    precondition {
      condition     = var.gpu_max_size >= var.gpu_desired_size
      error_message = "gpu_max_size (${var.gpu_max_size}) must be >= gpu_desired_size (${var.gpu_desired_size})."
    }
    precondition {
      condition     = var.gpu_az_index >= 0 && var.gpu_az_index < length(var.availability_zones)
      error_message = "gpu_az_index (${var.gpu_az_index}) is out of range for availability_zones list (length ${length(var.availability_zones)})."
    }
  }
}

########################
# Locals — GPU 단일 AZ 서브넷 추출
########################

locals {
  gpu_subnet_ids = [module.vpc.private_subnets[var.gpu_az_index]]
  gpu_subnet_az  = var.availability_zones[var.gpu_az_index]
}

########################
# EKS
########################

module "eks" {
  source  = "terraform-aws-modules/eks/aws"
  version = "~> 21.0"

  name               = var.ClusterBaseName
  kubernetes_version = var.KubernetesVersion

  vpc_id     = module.vpc.vpc_id
  subnet_ids = module.vpc.private_subnets

  enable_irsa = true

  endpoint_public_access  = true
  endpoint_private_access = true

  enabled_log_types = [
    "api",
    "scheduler"
  ]

  enable_cluster_creator_admin_permissions = true

  create_node_security_group                   = true
  node_security_group_enable_recommended_rules = var.node_sg_enable_recommended_rules

  eks_managed_node_groups = {
    # 시스템 노드 그룹
    primary = {
      name                   = "${var.ClusterBaseName}-ng-1"
      use_name_prefix        = false
      ami_type               = "AL2023_x86_64_STANDARD"
      instance_types         = [var.WorkerNodeInstanceType]
      desired_size           = var.WorkerNodeCount
      max_size               = var.WorkerNodeCount + 2
      min_size               = var.WorkerNodeCount - 1
      disk_size              = var.WorkerNodeVolumesize
      # terraform-aws-modules/eks v21 managed NG submodule 변수명은 subnet_ids.
      # subnets 등 다른 키는 조용히 무시되고 상위 모듈 subnet_ids 로 fallback 된다.
      subnet_ids             = module.vpc.private_subnets
      vpc_security_group_ids = [aws_security_group.node_group_sg.id]

      iam_role_name            = "${var.ClusterBaseName}-ng-1"
      iam_role_use_name_prefix = false
      iam_role_additional_policies = {
        "${var.ClusterBaseName}AWSLoadBalancerControllerPolicy" = aws_iam_policy.aws_lb_controller_policy.arn
        "${var.ClusterBaseName}ExternalDNSPolicy"               = aws_iam_policy.external_dns_policy.arn
        "${var.ClusterBaseName}CasAutoScalerPolicy"             = aws_iam_policy.aws_cas_autoscaler_policy.arn
        AmazonSSMManagedInstanceCore                            = "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
      }

      metadata_options = {
        http_endpoint               = "enabled"
        http_tokens                 = "required"
        http_put_response_hop_limit = 2
      }

      labels = {
        tier = "primary"
      }

      cloudinit_pre_nodeadm = [
        {
          content_type = "application/node.eks.aws"
          content      = <<-EOT
            ---
            apiVersion: node.eks.aws/v1alpha1
            kind: NodeConfig
            spec:
              kubelet:
                config:
                  maxPods: 50
          EOT
        },
        {
          content_type = "text/x-shellscript"
          content      = <<-EOT
            #!/bin/bash
            echo "Starting custom initialization..."
            dnf update -y
            dnf install -y tree bind-utils tcpdump nvme-cli links sysstat ipset htop
            echo "Custom initialization completed."
          EOT
        }
      ]
    }

    # GPU 노드 그룹
    gpu = {
      name                   = "${var.ClusterBaseName}-ng-gpu"
      use_name_prefix        = false
      ami_type               = "AL2023_x86_64_NVIDIA"
      capacity_type          = "ON_DEMAND"
      instance_types         = [var.gpu_instance_type]
      desired_size           = var.gpu_desired_size
      max_size               = var.gpu_max_size
      min_size               = 0

      # disk_size 는 v21 custom LT 경로에서 무시된다.
      # block_device_mappings 로 LT 에 직접 주입.
      block_device_mappings = {
        xvda = {
          device_name = "/dev/xvda"
          ebs = {
            volume_size           = var.gpu_node_disk_size
            volume_type           = "gp3"
            delete_on_termination = true
          }
        }
      }

      # 단일 AZ 고정. submodule 변수명이 subnet_ids 이므로 이 이름이어야 실제 적용된다.
      subnet_ids             = local.gpu_subnet_ids
      vpc_security_group_ids = [aws_security_group.node_group_sg.id]

      iam_role_name            = "${var.ClusterBaseName}-ng-gpu"
      iam_role_use_name_prefix = false
      iam_role_additional_policies = {
        AmazonSSMManagedInstanceCore = "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
      }

      metadata_options = {
        http_endpoint               = "enabled"
        http_tokens                 = "required"
        http_put_response_hop_limit = 2
      }

      labels = {
        tier             = "gpu"
        "nvidia.com/gpu" = "true"
      }

      taints = {
        gpu = {
          key    = "nvidia.com/gpu"
          value  = "true"
          effect = "NO_SCHEDULE"
        }
      }

      cloudinit_pre_nodeadm = [
        {
          content_type = "text/x-shellscript"
          content      = <<-EOT
            #!/bin/bash
            echo "Starting GPU node custom initialization..."
            dnf install -y tree bind-utils tcpdump nvme-cli links sysstat ipset htop pciutils
            echo "GPU node custom initialization completed."
          EOT
        }
      ]

      tags = {
        "k8s.io/cluster-autoscaler/node-template/label/nvidia.com/gpu" = "true"
        "k8s.io/cluster-autoscaler/node-template/taint/nvidia.com/gpu" = "true:NoSchedule"
      }
    }
  }

  addons = {
    coredns = {
      most_recent = true
    }
    kube-proxy = {
      most_recent = true
    }
    vpc-cni = {
      most_recent    = true
      before_compute = true
    }
    metrics-server = {
      most_recent = true
    }
    external-dns = {
      most_recent = true
    }
    eks-pod-identity-agent = {
      most_recent = true
    }
    cert-manager = {
      most_recent = true
    }
  }

  tags = {
    Environment = "cloudneta-lab"
    Terraform   = "true"
    Week        = "aews-5w"
  }
}
```

</details>

<br>

# gpu_operator.tf

NVIDIA GPU Operator를 Helm으로 배포하는 파일이다. `var.enable_gpu_operator`가 `true`일 때만 리소스가 생성된다.

## Helm Provider 설정

```hcl
provider "helm" {
  kubernetes {
    host                   = module.eks.cluster_endpoint
    cluster_ca_certificate = base64decode(module.eks.cluster_certificate_authority_data)
    exec {
      api_version = "client.authentication.k8s.io/v1beta1"
      command     = "aws"
      args = [
        "eks", "get-token",
        "--cluster-name", module.eks.cluster_name,
        "--region", var.TargetRegion
      ]
    }
  }
}
```

Helm Provider가 EKS 클러스터에 인증하는 방식이다. `exec` 블록으로 `aws eks get-token` 명령을 실행하여 임시 토큰을 발급받는다. 정적 토큰을 하드코딩하는 대신 매번 새 토큰을 발급받으므로 만료 문제가 없다.

## GPU Operator Helm Release

```hcl
resource "helm_release" "gpu_operator" {
  count = var.enable_gpu_operator ? 1 : 0

  name             = "gpu-operator"
  namespace        = var.gpu_operator_namespace
  create_namespace = true
  repository       = "https://helm.ngc.nvidia.com/nvidia"
  chart            = "gpu-operator"
  version          = var.gpu_operator_chart_version
  timeout          = 900
  atomic           = false
  wait             = true

  values = [yamlencode({
    driver = {
      enabled = false
    }
    toolkit = {
      enabled = false
    }
    devicePlugin = {
      enabled = true
    }
    nfd = {
      enabled = true
    }
    dcgmExporter = {
      enabled = true
    }
    validator = {
      plugin = {
        env = [
          {
            name  = "WITH_WORKLOAD"
            value = "true"
          }
        ]
      }
    }
    operator = {
      tolerations = [
        {
          key      = "nvidia.com/gpu"
          operator = "Exists"
          effect   = "NoSchedule"
        }
      ]
    }
  })]

  depends_on = [module.eks]
}
```

주요 설정을 살펴보자.

**컴포넌트 on/off:**

| 컴포넌트 | 설정 | 이유 |
| --- | --- | --- |
| `driver` | `false` | AL2023 NVIDIA AMI에 이미 포함 |
| `toolkit` | `false` | AL2023 NVIDIA AMI에 이미 포함 |
| `devicePlugin` | `true` | AMI에 포함되지 않음 — kubelet에 GPU 리소스를 등록하는 역할 |
| `nfd` | `true` | Node Feature Discovery — GPU 노드의 하드웨어 특성을 label로 노출 |
| `dcgmExporter` | `true` | NVIDIA DCGM(Data Center GPU Manager) 메트릭을 Prometheus 형식으로 노출 |

AL2023_x86_64_NVIDIA AMI는 NVIDIA 드라이버(580)와 Container Toolkit을 이미 탑재하고 있다. 따라서 GPU Operator에서 이 두 컴포넌트는 비활성하고, **Device Plugin, NFD, DCGM Exporter, Validator** 등 나머지 레이어만 Operator가 관리한다. 이것이 [AWS 공식 가이드](https://docs.aws.amazon.com/eks/latest/userguide/ml-eks-optimized-ami.html)의 권장 운영 방식이다.

**버전 핀:**

차트 버전은 `var.gpu_operator_chart_version`으로 `v26.3.1`에 고정했다. 버전 선택 근거와 `null`(latest)을 피해야 하는 이유는 [var.tf의 GPU Operator 변수](#gpu-operator-변수) 섹션에서 다뤘다.

**tolerations:**

```yaml
operator:
  tolerations:
    - key: nvidia.com/gpu
      operator: Exists
      effect: NoSchedule
```

GPU 노드에 `nvidia.com/gpu=true:NoSchedule` taint을 걸어뒀으므로, GPU Operator의 구성요소(DaemonSet 등)도 이 taint을 toleration해야 GPU 노드에 스케줄링된다.

**기타 설정:**

- `atomic = false`: 실습 중 설치 실패 원인을 관찰하기 위해 자동 rollback을 비활성화했다
- `timeout = 900`: GPU Operator 설치에는 시간이 걸릴 수 있으므로 15분으로 설정

<details markdown="1">
<summary><b>gpu_operator.tf 전체 코드</b></summary>

```hcl
########################
# NVIDIA GPU Operator (Helm) — 기본 비활성
########################

data "aws_eks_cluster_auth" "this" {
  name = module.eks.cluster_name
}

provider "helm" {
  kubernetes {
    host                   = module.eks.cluster_endpoint
    cluster_ca_certificate = base64decode(module.eks.cluster_certificate_authority_data)
    exec {
      api_version = "client.authentication.k8s.io/v1beta1"
      command     = "aws"
      args = [
        "eks", "get-token",
        "--cluster-name", module.eks.cluster_name,
        "--region", var.TargetRegion
      ]
    }
  }
}

resource "helm_release" "gpu_operator" {
  count = var.enable_gpu_operator ? 1 : 0

  name             = "gpu-operator"
  namespace        = var.gpu_operator_namespace
  create_namespace = true
  repository       = "https://helm.ngc.nvidia.com/nvidia"
  chart            = "gpu-operator"
  version          = var.gpu_operator_chart_version
  timeout          = 900
  atomic           = false
  wait             = true

  values = [yamlencode({
    driver = {
      enabled = false
    }
    toolkit = {
      enabled = false
    }
    devicePlugin = {
      enabled = true
    }
    nfd = {
      enabled = true
    }
    dcgmExporter = {
      enabled = true
    }
    validator = {
      plugin = {
        env = [
          {
            name  = "WITH_WORKLOAD"
            value = "true"
          }
        ]
      }
    }
    operator = {
      tolerations = [
        {
          key      = "nvidia.com/gpu"
          operator = "Exists"
          effect   = "NoSchedule"
        }
      ]
    }
  })]

  depends_on = [module.eks]
}
```

</details>

<details markdown="1">
<summary><b>GPU Operator v26.3.1 기본 values.yaml 전체</b></summary>

`helm show values nvidia/gpu-operator --version v26.3.1` 결과에 학습용 주석을 추가한 버전이다. Terraform에서 오버라이드하지 않은 나머지 값은 아래 기본값이 적용된다. 각 컴포넌트의 역할, AL2023 NVIDIA AMI 환경에서의 영향, 프로덕션 고려사항 등을 주석으로 달아 두었다. 추후 재현 시 스키마 변경 여부를 확인하는 참고 자료로 기록해 둔다.

```yaml
# Default values for gpu-operator.
# This is a YAML-formatted file.
# Declare variables to be passed into your templates.

platform:
  openshift: false    # OpenShift 전용 SCC/권한 설정 활성화 여부. EKS 에서는 false.

# ──────────────────────────────────────────────
# NFD (Node Feature Discovery)
#   노드의 하드웨어 특성(PCI 디바이스, CPU 플래그 등)을 탐지하여 라벨로 부착.
#   GPU Operator 는 이 라벨(nvidia.com/gpu.present 등)을 보고
#   어떤 노드에 GPU 컴포넌트를 배포할지 결정한다.
#   gpu_operator.tf 에서 nfd.enabled=true 로 유지하는 이유.
# ──────────────────────────────────────────────
nfd:
  enabled: true
  nodefeaturerules: false  # NodeFeatureRule CRD 기반 커스텀 룰. 기본 탐지로 충분하면 false.

# PSA (Pod Security Admission)
#   K8s 1.25+ 의 Pod Security Standards 연동.
#   restricted 프로필에서는 GPU 파드가 hostPath/privileged 등으로 차단될 수 있으므로,
#   네임스페이스에 privileged 라벨을 붙이거나 이 값을 true 로 설정하여 자동 처리한다.
psa:
  enabled: false

# CDI (Container Device Interface)
#   디바이스를 컨테이너에 노출하는 표준 인터페이스.
#   기존 nvidia-docker/nvidia-container-runtime 방식의 후속.
#   K8s 1.31+ 에서 DevicePluginCDIDevices 가 GA → CDI 활성이 기본 경로.
cdi:
  enabled: true
  nriPluginEnabled: false  # NRI(Node Resource Interface) 플러그인. CDI 와 별개 확장점.

# ──────────────────────────────────────────────
# sandboxWorkloads: KubeVirt/Kata 등 VM 기반 샌드박스에서 GPU 를 사용할 때.
#   일반 컨테이너 워크로드에서는 전부 비활성 상태로 무시해도 된다.
# ──────────────────────────────────────────────
sandboxWorkloads:
  enabled: false
  defaultWorkload: "container"
  mode: "kubevirt"     # "kubevirt" 또는 "kata". Kata 선택 시 kataSandboxDevicePlugin 이 배포됨.

hostPaths:
  rootFS: "/"
  # driver.enabled=true 일 때 컨테이너화된 드라이버가 설치되는 호스트 경로.
  # AL2023 NVIDIA AMI 처럼 driver.enabled=false 이면 이 경로는 사용되지 않는다.
  driverInstallDir: "/run/nvidia/driver"

# ──────────────────────────────────────────────
# daemonsets: GPU Operator 가 배포하는 *모든* DaemonSet 의 공통 설정.
#   개별 컴포넌트(driver, toolkit, devicePlugin 등)에도 별도 설정이 있지만,
#   여기서 지정한 값이 전역 기본값으로 적용된다.
# ──────────────────────────────────────────────
daemonsets:
  labels: {}
  annotations: {}
  # system-node-critical: GPU 컴포넌트가 리소스 부족 시에도 축출되지 않도록 보장.
  priorityClassName: system-node-critical
  tolerations:
  - key: nvidia.com/gpu
    operator: Exists
    effect: NoSchedule
    # ↑ GPU 노드의 nvidia.com/gpu taint 를 tolerate.
    #   이 설정이 없으면 Operator DaemonSet 파드가 GPU 노드에 스케줄링되지 않는다.
    #   gpu_operator.tf 에서 별도로 daemonsets.tolerations 을 오버라이드하지 않는 이유:
    #   기본값이 이미 올바르기 때문.
  # RollingUpdate vs OnDelete:
  #   대부분의 DaemonSet 은 RollingUpdate. 단, driver DaemonSet 만은 항상 OnDelete 로
  #   강제된다(Operator 내부 로직). 드라이버 업데이트는 GPU 를 사용 중인 파드를 먼저
  #   정리해야 안전하기 때문.
  updateStrategy: "RollingUpdate"
  rollingUpdate:
    maxUnavailable: "1"

# ──────────────────────────────────────────────
# validator: GPU 스택이 정상 설치되었는지 검증하는 파드.
#   드라이버 → toolkit → devicePlugin → CUDA 워크로드 순서로 health check 수행.
#   gpu_operator.tf 에서 validator.plugin.env 에 WITH_WORKLOAD=true 를 주입하여
#   실제 CUDA Job 으로 E2E 검증까지 수행하도록 설정했다.
# ──────────────────────────────────────────────
validator:
  repository: nvcr.io/nvidia
  image: gpu-operator
  #version: ""           # 비워두면 chart.AppVersion 사용
  imagePullPolicy: IfNotPresent
  imagePullSecrets: []
  env: []
  args: []
  resources: {}
  hostNetwork: false
  plugin:
    env: []              # ← gpu_operator.tf 에서 [{name="WITH_WORKLOAD", value="true"}] 로 오버라이드

# ──────────────────────────────────────────────
# operator: GPU Operator 컨트롤러 자체(Deployment).
#   ClusterPolicy CRD 를 watch 하고, 각 컴포넌트 DaemonSet 을 reconcile 한다.
# ──────────────────────────────────────────────
operator:
  repository: nvcr.io/nvidia
  image: gpu-operator
  #version: ""
  imagePullPolicy: IfNotPresent
  imagePullSecrets: []
  priorityClassName: system-node-critical
  # nvidia RuntimeClass 를 자동 생성. 파드 spec.runtimeClassName: nvidia 로 지정하면
  # nvidia-container-runtime 을 사용하게 된다.
  runtimeClass: nvidia
  use_ocp_driver_toolkit: false  # OpenShift 전용
  cleanupCRD: false     # helm uninstall 시 CRD 삭제 여부. false 면 CRD 보존 → 재설치 용이.
  upgradeCRD: true      # helm upgrade 시 CRD 자동 업그레이드. --disable-openapi-validation 필요.
  # 컨트롤 플레인 taint toleration + affinity.
  # EKS managed 노드에서는 컨트롤 플레인에 파드를 띄울 수 없으므로 사실상 무효.
  # 자체 관리 클러스터에서는 Operator 가 마스터 노드에서 실행되도록 유도하는 설정.
  tolerations:
  - key: "node-role.kubernetes.io/control-plane"
    operator: "Equal"
    value: ""
    effect: "NoSchedule"
  annotations:
    openshift.io/scc: restricted-readonly
  affinity:
    nodeAffinity:
      preferredDuringSchedulingIgnoredDuringExecution:
        - weight: 1
          preference:
            matchExpressions:
              - key: "node-role.kubernetes.io/control-plane"
                operator: In
                values: [""]
  logging:
    timeEncoding: epoch
    level: info          # 트러블슈팅 시 debug 로 올리면 Operator 상세 로그 확인 가능
    develMode: false
  resources:
    limits:
      cpu: 500m
      memory: 350Mi
    requests:
      cpu: 200m
      memory: 100Mi

# ──────────────────────────────────────────────
# MIG (Multi-Instance GPU)
#   A100/H100 같은 MIG 지원 GPU 를 여러 인스턴스로 분할하는 전략.
#   "single": 모든 GPU 에 동일한 MIG 프로필. "mixed": GPU 별로 다른 프로필 허용.
#   G4dn(T4) 등 MIG 미지원 GPU 에서는 이 설정이 무시된다.
# ──────────────────────────────────────────────
mig:
  strategy: single

# ──────────────────────────────────────────────
# driver: NVIDIA 커널 드라이버를 컨테이너로 설치·관리하는 컴포넌트.
#   ★ AL2023 NVIDIA AMI 사용 시 driver.enabled=false 로 반드시 비활성 ★
#   AMI 에 이미 호스트 레벨 드라이버(580)가 설치되어 있기 때문에,
#   Operator 가 중복 설치하면 충돌이 발생한다.
# ──────────────────────────────────────────────
driver:
  enabled: true          # ← gpu_operator.tf 에서 false 로 오버라이드
  nvidiaDriverCRD:
    enabled: false       # NVIDIADriver CRD 기반 드라이버 관리. 고급 시나리오용.
    deployDefaultCR: true
    driverType: gpu
    nodeSelector: {}
  # "auto": 하드웨어에 따라 open/proprietary 커널 모듈 자동 선택.
  # Turing(T4) 이상에서 open 모듈 지원. Volta 이하는 proprietary 전용.
  kernelModuleType: "auto"
  usePrecompiled: false  # Ubuntu 22.04 한정 프리컴파일 패키지. AL2023 에선 해당 없음.
  repository: nvcr.io/nvidia
  image: driver
  # 이 버전은 Operator 가 컨테이너화된 드라이버를 설치할 때의 버전.
  # AL2023 NVIDIA AMI 의 호스트 드라이버(580)와 같은 major stream.
  # driver.enabled=false 면 이 값은 실제 사용되지 않는다.
  version: "580.126.20"
  imagePullPolicy: IfNotPresent
  imagePullSecrets: []
  # 드라이버 로딩은 커널 모듈 컴파일/로드를 포함하므로 매우 느릴 수 있다.
  # failureThreshold × periodSeconds = 120 × 10 = 최대 20분 대기.
  startupProbe:
    initialDelaySeconds: 60
    periodSeconds: 10
    timeoutSeconds: 60
    failureThreshold: 120
  rdma:
    enabled: false       # RDMA(InfiniBand/RoCE) 네트워킹. 멀티노드 GPU 학습에서
    useHostMofed: false   # EFA + NCCL 환경이면 별도 EFA 플러그인을 쓰므로 여기서는 false.
  # ──── 프로덕션 주의 ────
  # upgradePolicy: Operator 가 드라이버를 라이브 업그레이드하는 정책.
  # autoUpgrade=true 면 새 driver 이미지 감지 시 자동으로 노드별 순차 업그레이드.
  # GPU 워크로드가 돌고 있을 때 드라이버를 교체하면 CUDA 컨텍스트가 깨지므로,
  # gpuPodDeletion/drain 설정으로 사전 정리 전략을 제어한다.
  upgradePolicy:
    autoUpgrade: true
    maxParallelUpgrades: 1
    maxUnavailable: 25%
    waitForCompletion:
      timeoutSeconds: 0
      podSelector: ""
    gpuPodDeletion:
      force: false
      timeoutSeconds: 300
      deleteEmptyDir: false
    drain:
      enable: false      # true 로 바꾸면 kubectl drain 수행 후 드라이버 교체
      force: false
      podSelector: ""
      timeoutSeconds: 300
      deleteEmptyDir: false
  # k8s-driver-manager: 노드에서 드라이버 파드 라이프사이클을 관리하는 init container.
  manager:
    repository: nvcr.io/nvidia/cloud-native
    image: k8s-driver-manager
    version: v0.10.0
    imagePullPolicy: IfNotPresent
    env: []
  env: []
  resources: {}
  repoConfig:
    configMapName: ""    # 프라이빗 패키지 리포지토리 설정 (에어갭 환경용)
  certConfig:
    name: ""             # 커스텀 SSL 인증서 (프라이빗 리포지토리 HTTPS 용)
  licensingConfig:
    secretName: ""
    nlsEnabled: true     # vGPU 라이선싱. 물리 GPU(T4/A100 등) 사용 시 무관.
  virtualTopology:
    config: ""           # vGPU 토폴로지. 물리 GPU 사용 시 무관.
  kernelModuleConfig:
    name: ""
  secretEnv: ""
  hostNetwork: false

# ──────────────────────────────────────────────
# toolkit: NVIDIA Container Toolkit (nvidia-ctk).
#   컨테이너 런타임(containerd)에 NVIDIA 디바이스를 주입하는 레이어.
#   ★ AL2023 NVIDIA AMI 에 이미 포함 → gpu_operator.tf 에서 false 로 비활성 ★
# ──────────────────────────────────────────────
toolkit:
  enabled: true          # ← gpu_operator.tf 에서 false 로 오버라이드
  repository: nvcr.io/nvidia/k8s
  image: container-toolkit
  version: v1.19.0
  imagePullPolicy: IfNotPresent
  imagePullSecrets: []
  env: []
  resources: {}
  installDir: "/usr/local/nvidia"  # toolkit 바이너리 설치 경로 (호스트)
  hostNetwork: false

# ──────────────────────────────────────────────
# devicePlugin: kubelet 에 nvidia.com/gpu 리소스를 등록하는 핵심 컴포넌트.
#   Pod spec 에서 resources.limits["nvidia.com/gpu"] = 1 처럼 요청하면,
#   이 플러그인이 GPU 디바이스를 할당한다.
#   driver.enabled=false 여도 devicePlugin 은 호스트 드라이버를 통해 동작한다.
# ──────────────────────────────────────────────
devicePlugin:
  enabled: true
  repository: nvcr.io/nvidia
  image: k8s-device-plugin
  version: v0.19.0
  imagePullPolicy: IfNotPresent
  imagePullSecrets: []
  args: []
  env: []
  resources: {}
  # config: GPU 공유 전략(Time-Slicing, MPS) 을 ConfigMap 으로 정의할 때 사용.
  #   예) time-slicing 으로 T4 1장을 논리 4장으로 분할:
  #     data:
  #       time-slicing: |-
  #         version: v1
  #         sharing:
  #           timeSlicing:
  #             resources:
  #               - name: nvidia.com/gpu
  #                 replicas: 4
  config:
    create: false
    name: ""
    default: ""
    data: {}
  mps:
    root: "/run/nvidia/mps"  # MPS(Multi-Process Service) 소켓 경로.
                              # MPS 는 여러 프로세스가 하나의 GPU 를 공유할 때
                              # context switching 없이 동시 실행하게 해주는 CUDA 기능.
  hostNetwork: false

# ──────────────────────────────────────────────
# dcgm: 독립 DCGM(Data Center GPU Manager) hostengine.
#   기본 disabled — dcgmExporter 내장 hostengine 이 대신 사용된다.
#   대규모 클러스터에서 중앙 집중식 DCGM 관리가 필요하면 활성화.
# ──────────────────────────────────────────────
dcgm:
  enabled: false
  repository: nvcr.io/nvidia/cloud-native
  image: dcgm
  version: 4.5.2-1-ubuntu22.04
  imagePullPolicy: IfNotPresent
  args: []
  env: []
  resources: {}
  hostNetwork: false

# ──────────────────────────────────────────────
# dcgmExporter: GPU 메트릭(온도, 사용률, 메모리, ECC 에러 등)을
#   Prometheus 형식으로 노출하는 DaemonSet.
#   내장 hostengine 을 사용하므로 위의 dcgm.enabled=false 여도 독립 동작한다.
# ──────────────────────────────────────────────
dcgmExporter:
  enabled: true
  repository: nvcr.io/nvidia/k8s
  image: dcgm-exporter
  version: 4.5.1-4.8.0-distroless
  imagePullPolicy: IfNotPresent
  env: []
  resources: {}
  hostPID: false
  hostNetwork: false
  service:
    internalTrafficPolicy: Cluster
  serviceMonitor:
    enabled: false       # Prometheus Operator(ServiceMonitor CRD) 사용 시 true 로 변경.
    interval: 15s        # 스크래핑 간격
    honorLabels: false
    additionalLabels: {}
    relabelings: []

# ──────────────────────────────────────────────
# GFD (GPU Feature Discovery)
#   NFD 의 GPU 전용 확장. 노드에 GPU 모델명, 메모리 크기, 드라이버 버전,
#   CUDA 버전 등을 라벨(nvidia.com/gpu.product 등)로 부착한다.
#   스케줄링 시 nodeSelector/nodeAffinity 로 특정 GPU 모델을 선택할 때 유용.
#   device-plugin 과 같은 이미지를 사용한다.
# ──────────────────────────────────────────────
gfd:
  enabled: true
  repository: nvcr.io/nvidia
  image: k8s-device-plugin
  version: v0.19.0
  imagePullPolicy: IfNotPresent
  imagePullSecrets: []
  env: []
  resources: {}
  hostNetwork: false

# ──────────────────────────────────────────────
# migManager: MIG 파티셔닝을 자동 관리.
#   config.default="all-disabled" → MIG 미사용이 기본값.
#   A100/H100 에서 MIG 를 사용하려면 ConfigMap 으로 파티션 프로필을 정의한다.
#   G4dn(T4) 같은 MIG 미지원 GPU 에서는 파드가 뜨지만 실질 동작 없음.
# ──────────────────────────────────────────────
migManager:
  enabled: true
  repository: nvcr.io/nvidia/cloud-native
  image: k8s-mig-manager
  version: v0.14.0
  imagePullPolicy: IfNotPresent
  imagePullSecrets: []
  env: []
  resources: {}
  config:
    default: "all-disabled"
    create: false
    name: ""
    data: {}
  gpuClientsConfig:
    name: ""
  hostNetwork: false

# nodeStatusExporter: 노드 수준 GPU 상태를 CRD 로 내보내는 컴포넌트. 기본 비활성.
nodeStatusExporter:
  enabled: false
  repository: nvcr.io/nvidia
  image: gpu-operator
  #version: ""
  imagePullPolicy: IfNotPresent
  imagePullSecrets: []
  resources: {}
  hostNetwork: false

# ──────────────────────────────────────────────
# GDS (GPUDirect Storage): GPU 메모리 ↔ NVMe/NFS 간 직접 DMA 전송.
#   대규모 데이터 파이프라인(학습 데이터 로딩)에서 CPU 바이패스로 처리량 향상.
#   특수한 스토리지 구성이 필요하므로 기본 비활성.
# ──────────────────────────────────────────────
gds:
  enabled: false
  repository: nvcr.io/nvidia/cloud-native
  image: nvidia-fs
  version: "2.27.3"
  imagePullPolicy: IfNotPresent
  imagePullSecrets: []
  env: []
  args: []

# GDRCopy: GPU 메모리에 대한 저지연 복사. HPC/RDMA 워크로드 전용.
gdrcopy:
  enabled: false
  repository: nvcr.io/nvidia/cloud-native
  image: gdrdrv
  version: "v2.5.2"
  imagePullPolicy: IfNotPresent
  imagePullSecrets: []
  env: []
  args: []

# ──────────────────────────────────────────────
# vGPU 관련 (vgpuManager, vgpuDeviceManager)
#   NVIDIA vGPU 는 하나의 물리 GPU 를 여러 VM 에 가상으로 분할하는 엔터프라이즈 기능.
#   별도 vGPU 라이선스가 필요하며, EKS 의 베어메탈/물리 GPU 사용 시에는 해당 없음.
# ──────────────────────────────────────────────
vgpuManager:
  enabled: false
  repository: ""
  image: vgpu-manager
  version: ""
  imagePullPolicy: IfNotPresent
  imagePullSecrets: []
  env: []
  resources: {}
  driverManager:
    repository: nvcr.io/nvidia/cloud-native
    image: k8s-driver-manager
    version: v0.10.0
    imagePullPolicy: IfNotPresent
    env: []
  kernelModuleConfig:
    name: ""
  hostNetwork: false

vgpuDeviceManager:
  enabled: true          # vgpuManager.enabled=false 면 실질 동작 없음
  repository: nvcr.io/nvidia/cloud-native
  image: vgpu-device-manager
  version: v0.4.2
  imagePullPolicy: IfNotPresent
  imagePullSecrets: []
  env: []
  config:
    name: ""
    default: "default"
  hostNetwork: false

# ──────────────────────────────────────────────
# vfioManager: VFIO(Virtual Function I/O) 를 통한 GPU PCIe 패스스루.
#   KubeVirt 같은 VM 오케스트레이터에서 GPU 를 VM 에 직접 할당할 때 사용.
#   일반 컨테이너 워크로드에서는 해당 없음.
# ──────────────────────────────────────────────
vfioManager:
  enabled: true          # sandboxWorkloads.enabled=false 면 실질 동작 없음
  repository: nvcr.io/nvidia/cloud-native
  image: k8s-driver-manager
  version: v0.10.0
  imagePullPolicy: IfNotPresent
  imagePullSecrets: []
  env: []
  resources: {}
  driverManager:
    repository: nvcr.io/nvidia/cloud-native
    image: k8s-driver-manager
    version: v0.10.0
    imagePullPolicy: IfNotPresent
    env: []
  hostNetwork: false

# Kata Containers: 경량 VM 기반 컨테이너 런타임. GPU 패스스루 시나리오.
kataManager:
  enabled: false
  config: {}
  imagePullPolicy: IfNotPresent
  imagePullSecrets: []
  env: []
  resources: {}
  hostNetwork: false

# KubeVirt GPU device plugin: VM 에 GPU 를 할당하는 디바이스 플러그인.
sandboxDevicePlugin:
  enabled: true          # sandboxWorkloads.enabled=false 면 실질 동작 없음
  repository: nvcr.io/nvidia
  image: kubevirt-gpu-device-plugin
  version: v1.5.0
  imagePullPolicy: IfNotPresent
  imagePullSecrets: []
  args: []
  env: []
  resources: {}
  hostNetwork: false

# Kata sandbox device plugin: Kata 모드 전용.
kataSandboxDevicePlugin:
  enabled: true          # sandboxWorkloads.mode="kata" 일 때만 의미 있음
  repository: nvcr.io/nvidia/cloud-native
  image: nvidia-sandbox-device-plugin
  version: "v0.0.3"
  imagePullPolicy: IfNotPresent
  imagePullSecrets: []
  args: []
  env: []
  resources: {}
  hostNetwork: false

# ──────────────────────────────────────────────
# ccManager (Confidential Computing Manager)
#   H100 CC(Confidential Computing) 모드에서 GPU 메모리 암호화를 관리.
#   CC 미지원 GPU(T4, A10G 등) 에서는 파드가 뜨지만 실질 동작 없음.
#   defaultMode: "on" → CC 지원 하드웨어에서 자동 활성화.
# ──────────────────────────────────────────────
ccManager:
  enabled: true
  defaultMode: "on"
  repository: nvcr.io/nvidia/cloud-native
  image: k8s-cc-manager
  version: v0.4.0
  imagePullPolicy: IfNotPresent
  imagePullSecrets: []
  resources: {}
  hostNetwork: false

# 추가 K8s 매니페스트를 Helm 릴리스에 포함할 때 사용. 디버깅용 ConfigMap 등.
extraObjects: []

# ──────────────────────────────────────────────
# NFD subchart 설정.
#   GPU Operator 가 NFD 를 subchart 로 번들하여 배포한다.
#   이미 클러스터에 NFD 가 있다면 nfd.enabled=false + 이 섹션 무시.
# ──────────────────────────────────────────────
node-feature-discovery:
  priorityClassName: system-node-critical
  gc:
    enable: true         # 사라진 노드의 stale NodeFeature 오브젝트 정리
    replicaCount: 1
    serviceAccount:
      name: node-feature-discovery
      create: false
  worker:
    serviceAccount:
      name: node-feature-discovery
      create: false
    tolerations:
    - key: "node-role.kubernetes.io/control-plane"
      operator: "Equal"
      value: ""
      effect: "NoSchedule"
    - key: nvidia.com/gpu
      operator: Exists
      effect: NoSchedule
    config:
      sources:
        pci:
          # PCI 디바이스 클래스 코드로 탐지 대상을 필터링:
          #   02   = Network controller
          #   0200 = Ethernet controller
          #   0207 = InfiniBand controller (NCCL/RDMA 관련 탐지)
          #   0300 = VGA compatible controller
          #   0302 = 3D controller ← 이것이 NVIDIA GPU (T4, A10G, A100, H100 등)
          deviceClassWhitelist:
          - "02"
          - "0200"
          - "0207"
          - "0300"
          - "0302"
          deviceLabelFields:
          - vendor
  master:
    serviceAccount:
      name: node-feature-discovery
      create: true
    config:
      # nvidia.com 네임스페이스의 라벨을 NFD 가 설정할 수 있도록 허용.
      # 이 설정이 없으면 NFD 가 nvidia.com/gpu.present 등의 라벨을 거부한다.
      extraLabelNs: ["nvidia.com"]
```

</details>

<br>

# outputs.tf

기존 output(`configure_kubectl`, `cluster_name`, `cluster_endpoint`)에 GPU 관련 output이 추가되었다.

```hcl
output "node_security_group_id" {
  description = "EKS 모듈이 생성한 노드 SG. NCCL 차단 실험 시 확인 대상."
  value       = module.eks.node_security_group_id
}

output "gpu_subnet_az" {
  description = "GPU 노드가 배치된 단일 AZ"
  value       = local.gpu_subnet_az
}

output "ami_al2023_nvidia" {
  description = "GPU 노드 AMI (AL2023 nvidia) — 참고용"
  value       = nonsensitive(data.aws_ssm_parameter.eks_ami_al2023_nvidia.value)
}
```

| output | 용도 |
| --- | --- |
| `node_security_group_id` | NCCL 보안그룹 차단 실험에서 규칙을 확인할 대상 SG |
| `gpu_subnet_az` | GPU 노드가 어떤 AZ에 배치되었는지 확인 |
| `ami_al2023_nvidia` | GPU 노드에 사용된 AMI ID — 버전 확인용 |

<details markdown="1">
<summary><b>outputs.tf 전체 코드</b></summary>

```hcl
output "configure_kubectl" {
  description = "kubeconfig 업데이트 명령어"
  value       = "aws eks --region ${var.TargetRegion} update-kubeconfig --name ${var.ClusterBaseName}"
}

output "cluster_name" {
  description = "EKS 클러스터 이름"
  value       = module.eks.cluster_name
}

output "cluster_endpoint" {
  description = "EKS API endpoint"
  value       = module.eks.cluster_endpoint
}

output "cluster_security_group_id" {
  description = "EKS 모듈이 생성한 클러스터 SG."
  value       = module.eks.cluster_security_group_id
}

output "node_security_group_id" {
  description = "EKS 모듈이 생성한 노드 SG. NCCL 차단 실험 시 확인 대상."
  value       = module.eks.node_security_group_id
}

output "auxiliary_node_sg_id" {
  description = "보조 node_group_sg (VPC 대역 all traffic 허용)"
  value       = aws_security_group.node_group_sg.id
}

output "gpu_subnet_az" {
  description = "GPU 노드가 배치된 단일 AZ"
  value       = local.gpu_subnet_az
}

output "gpu_subnet_id" {
  description = "GPU 노드 그룹이 사용하는 private subnet id (단일 AZ)"
  value       = local.gpu_subnet_ids[0]
}

output "ami_al2023_standard" {
  description = "시스템 노드 AMI (AL2023 standard)"
  value       = nonsensitive(data.aws_ssm_parameter.eks_ami_al2023_std.value)
}

output "ami_al2023_nvidia" {
  description = "GPU 노드 AMI (AL2023 nvidia) — 참고용"
  value       = nonsensitive(data.aws_ssm_parameter.eks_ami_al2023_nvidia.value)
}
```

</details>

<br>

# 정리

이번 실습 환경의 핵심은 **기존 EKS 환경에 GPU 레이어를 얹되, 비용과 쿼터 제약을 Terraform 변수로 제어**하는 구조다.

## 주차별 비교

| 항목 | 1주차 | 2주차 | 3주차 | 4주차 | 이번 실습 |
| --- | --- | --- | --- | --- | --- |
| 노드 서브넷 | 퍼블릭 | 퍼블릭+프라이빗 | **프라이빗** | **프라이빗** | **프라이빗** |
| GPU 노드 | - | - | - | - | **g5.xlarge × 2** |
| GPU AMI | - | - | - | - | **AL2023_x86_64_NVIDIA** |
| GPU Operator | - | - | - | - | **Helm (토글)** |
| SG 실험 토글 | - | - | - | - | **NCCL 차단용** |
| CP 로깅 | 비활성 | 비활성 | api, scheduler (2종) | 전면 활성화 (5종) | api, scheduler (2종) |
| Addon | 3종 | 3종 | 5종 | 7종 | **7종 + cert-manager** |
| 노드 접근 | SSH | SSH | SSM | SSM | **SSM** |
| IRSA | 미설정 | 활성화 | 활성화 | 활성화 | 활성화 |
| CAS 정책 | - | - | **추가** | - | **추가** |

## 배포 순서

실제 배포는 다음 순서로 진행한다.

1. **기반 인프라 먼저**: GPU 노드 수 0, GPU Operator 비활성 상태로 `terraform apply -var enable_gpu_operator=false`
2. **GPU 세션 진입 시**: `aws eks update-nodegroup-config --scaling-config desiredSize=2`로 GPU 노드 기동
3. **GPU Operator 설치**: `terraform apply` (`default = true`이므로 별도 플래그 불필요)
4. **실습 종료 시**: `aws eks update-nodegroup-config --scaling-config desiredSize=0`으로 GPU 노드 종료

> Step 1에서 `-var enable_gpu_operator=false`로 CLI override하는 이유는 [GPU Operator 변수](#gpu-operator-변수) 섹션을 참고한다. `default = true`이므로 최초 배포 시에만 명시적으로 꺼야 한다.

> Step 2, 4가 Terraform이 아닌 AWS CLI인 이유는 [비용 가드의 실제 스케일링 경로](#비용-가드의-실제-스케일링-경로)를 참고한다.

<br>
