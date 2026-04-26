---
title: "[EKS] EKS: 인증/인가 - 2. 실습 환경 배포"
excerpt: "4주차 인증/인가 실습을 위한 EKS 환경을 배포해 보자."
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
  - Terraform
  - IAM
  - Pod-Identity
  - IRSA
  - AWS-EKS-Workshop-Study
  - AWS-EKS-Workshop-Study-Week-4
---

*[서종호(가시다)](https://www.linkedin.com/in/gasida99/)님의 AWS EKS Workshop Study(AEWS) 4주차 학습 내용을 기반으로 합니다.*

<br>

# TL;DR

4주차 실습 환경을 배포하고 그 결과를 확인한다.

- **네트워크**: 노드를 **프라이빗 서브넷**에 배포하고, NAT Gateway를 통해 인터넷에 접근한다. 노드 접근은 SSM으로 한다
- **컨트롤 플레인 로깅 전면 활성화**: 인증/인가 흐름 분석을 위해 api, audit, authenticator, controllerManager, scheduler 로그를 모두 켰다
- **addon 7종 구성**: coredns, kube-proxy, vpc-cni 외에 metrics-server, external-dns, eks-pod-identity-agent, cert-manager를 포함한다
- **Kubernetes 1.35**, 워커 노드 **2대**

<br>

# 환경 개요

인증/인가 실습에 맞춰 구성된 4주차 환경의 주요 특징을 정리하면 다음과 같다.

| 항목 | 구성 | 이유 |
| --- | --- | --- |
| K8s 버전 | **1.35** | 최신 버전 |
| 워커 노드 수 | **2** | 인증/인가 실습에 충분 |
| 노드 서브넷 | **프라이빗** | 외부에서 노드 직접 접근 차단 |
| NAT Gateway | **Single** | 프라이빗 노드의 인터넷 접근용 |
| 노드 접근 | **SSM** (SSH 없음) | 키 관리 불필요, 접근 로그 자동 기록 |
| CP 로깅 | **전체 활성화** (5종) | authenticator/audit 로그로 인증 흐름 디버깅 |
| addon | **7종** (coredns<br>- kube-proxy<br>- vpc-cni<br>- metrics-server<br>- external-dns<br>- eks-pod-identity-agent<br>- cert-manager) | 인증/인가 실습 준비 |
| 노드 IAM 정책 | **ExternalDNS + SSM** 추가 | addon 동작 + SSM 접근 |
| IMDS hop limit | **2** (IMDSv2 강제) | 파드에서 IMDS 접근 허용 (학습용) |

이제 각 항목을 코드 수준에서 살펴보자.

<br>

# var.tf

## SSH 없음, SSM으로 노드 접근

SSH 키 페어 관련 변수(`KeyName`, `ssh_access_cidr`)는 정의되어 있지 않다. 노드에 대한 접근은 **AWS Systems Manager(SSM) Session Manager**로 한다. SSM은 포트를 열지 않고도 EC2 인스턴스에 접근할 수 있는 서비스로, 키 페어 관리가 필요 없고 접근 로그가 자동으로 남는다. 이를 위해 노드 IAM 역할에 `AmazonSSMManagedInstanceCore` 정책을 추가하는데, 이것은 뒤의 eks.tf에서 확인한다.

## Kubernetes 버전과 노드 수

```hcl
variable "KubernetesVersion" {
  type    = string
  default = "1.35"
}

variable "WorkerNodeCount" {
  type    = number
  default = 2
}
```

Kubernetes 1.35를 사용하고, 워커 노드는 2대로 구성한다. 인증/인가 실습에서는 많은 파드를 생성하지 않으므로 2대면 충분하다.

<br>

# vpc.tf

## 프라이빗 서브넷과 NAT Gateway

퍼블릭 서브넷 3개와 **프라이빗 서브넷 3개**를 함께 구성하고, NAT Gateway를 활성화했다.

```hcl
module "vpc" {
  source  = "terraform-aws-modules/vpc/aws"
  version = "~>6.5"

  # ...

  public_subnets  = var.public_subnet_blocks   # 퍼블릭 서브넷 3개
  private_subnets = var.private_subnet_blocks   # 프라이빗 서브넷 3개

  enable_nat_gateway     = true
  single_nat_gateway     = true   # NAT Gateway 1개로 비용 절감
  one_nat_gateway_per_az = false

  # ...

  private_subnet_tags = {
    "Name"                            = "${var.ClusterBaseName}-PrivateSubnet"
    "kubernetes.io/role/internal-elb" = "1"
  }
}
```

워커 노드는 프라이빗 서브넷에 배치한다. 인터넷에서 노드로 직접 접근할 수 없고, 노드가 인터넷에 나가야 할 때(컨테이너 이미지 풀, AWS API 호출 등)는 NAT Gateway를 경유한다.

`single_nat_gateway = true`는 NAT Gateway를 **AZ당 하나가 아닌 전체 1개만** 생성한다는 뜻이다. 프로덕션에서는 AZ별로 NAT Gateway를 두는 것이 고가용성 측면에서 권장되지만, 실습 환경에서는 비용 절감을 위해 1개로 충분하다.

프라이빗 서브넷 태그의 `kubernetes.io/role/internal-elb = "1"`은 AWS Load Balancer Controller가 **내부 로드밸런서**를 배치할 서브넷을 식별하는 마커다. 퍼블릭 서브넷의 `kubernetes.io/role/elb`(외부용)와 대응된다.

<br>

# eks.tf

가장 내용이 많은 파일이다. 핵심 설정 위주로 본다.

## 보안 그룹

```hcl
resource "aws_security_group_rule" "allow_ssh" {
  type      = "ingress"
  from_port = 0
  to_port   = 0
  protocol  = "-1"
  cidr_blocks = [
    var.VpcBlock
  ]
  security_group_id = aws_security_group.node_group_sg.id
}
```

`VpcBlock`(VPC CIDR)만 허용한다. VPC 내부 통신만 가능하고, 외부에서의 직접 접근은 차단된다.

## EKS 클러스터 모듈

```hcl
module "eks" {
  source  = "terraform-aws-modules/eks/aws"
  version = "~> 21.0"

  # ...

  vpc_id     = module.vpc.vpc_id
  subnet_ids = module.vpc.private_subnets

  endpoint_public_access  = true
  endpoint_private_access = true

  enabled_log_types = [
    "api",
    "scheduler",
    "authenticator",
    "controllerManager",
    "audit"
  ]

  enable_cluster_creator_admin_permissions = true

  # ...
}
```

### 프라이빗 서브넷에 노드 배포

`subnet_ids`에 `module.vpc.private_subnets`을 지정하여 노드 그룹이 프라이빗 서브넷에 배포된다.

API 서버 엔드포인트는 `endpoint_public_access = true`와 `endpoint_private_access = true`를 모두 설정한다. 외부에서 kubectl 접근도 가능하고, 프라이빗 서브넷의 노드가 VPC 내부 경로로 API 서버에 접근하는 것도 가능하다.

### 컨트롤 플레인 로깅 전면 활성화

**5개 로그 타입을 전부 활성화**했다.

| 로그 타입 | 용도 |
| --- | --- |
| `api` | API 서버 요청/응답 로그 |
| `audit` | 누가, 언제, 무엇을 요청했는지 기록 |
| `authenticator` | IAM 인증 관련 로그 |
| `controllerManager` | 컨트롤러 매니저 동작 로그 |
| `scheduler` | 스케줄러 결정 로그 |

인증/인가 흐름을 디버깅하려면 `authenticator`와 `audit` 로그가 필수다. 예를 들어, 특정 IAM 사용자가 kubectl로 접근했을 때 어떤 Access Entry에 매핑되는지, RBAC에서 허용/거부되는지를 추적할 수 있다. 나머지 로그도 함께 켜 두면 전체 흐름을 종합적으로 파악할 수 있다.

> 컨트롤 플레인 로그는 CloudWatch Logs의 `/aws/eks/<클러스터명>/cluster` 로그 그룹에 저장된다. 로그 보관 기간은 기본 90일이며, Terraform 모듈이 자동으로 로그 그룹을 생성한다.
> ![eks-w4-cloudwatch-log-location]({{site.url}}/assets/images/eks-w4-cloudwatch-log-location.png)

## 노드 그룹

```hcl
eks_managed_node_groups = {
  primary = {
    name            = "${var.ClusterBaseName}-ng-1"
    use_name_prefix = false
    ami_type        = "AL2023_x86_64_STANDARD"
    instance_types  = ["${var.WorkerNodeInstanceType}"]
    desired_size    = var.WorkerNodeCount
    max_size        = var.WorkerNodeCount + 2
    min_size        = var.WorkerNodeCount - 1
    disk_size       = var.WorkerNodeVolumesize
    subnets         = module.vpc.private_subnets
    vpc_security_group_ids = [aws_security_group.node_group_sg.id]

    iam_role_name            = "${var.ClusterBaseName}-ng-1"
    iam_role_use_name_prefix = false
    iam_role_additional_policies = {
      "${var.ClusterBaseName}ExternalDNSPolicy" = aws_iam_policy.external_dns_policy.arn
      AmazonSSMManagedInstanceCore = "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
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
        content_type = "text/x-shellscript"
        content      = <<-EOT
          #!/bin/bash
          dnf update -y
          dnf install -y tree bind-utils tcpdump nvme-cli links sysstat ipset htop
        EOT
      }
    ]
  }
}
```

### IAM 추가 정책

`iam_role_additional_policies`로 두 가지 정책을 연결한다.

| 정책 | 용도 |
| --- | --- |
| `ExternalDNSPolicy` | ExternalDNS addon이 Route 53 레코드를 관리할 수 있도록 허용 |
| `AmazonSSMManagedInstanceCore` | SSM Session Manager로 노드에 접근할 수 있도록 허용 |

`AmazonSSMManagedInstanceCore` 정책이 있어야 SSM Agent가 AWS Systems Manager와 통신할 수 있다. SSH 키 페어 없이도 노드에 접근할 수 있는 기반이 된다.

### IMDS hop limit

```hcl
metadata_options = {
  http_endpoint               = "enabled"
  http_tokens                 = "required"   # IMDSv2 강제
  http_put_response_hop_limit = 2            # 기본값 1 → 2로 증가
}
```

EC2 Instance Metadata Service(IMDS)의 hop limit을 2로 설정했다. 기본값은 1인데, 이 경우 **컨테이너(파드) 내부에서 IMDS에 접근할 수 없다**. 파드에서 IMDS까지의 네트워크 경로가 노드의 네트워크 네임스페이스를 거치면서 hop이 하나 더 추가되기 때문이다. hop limit을 2로 올리면 파드에서도 EC2 Instance Profile의 임시 자격증명을 조회할 수 있다.

> IRSA나 Pod Identity를 사용하면 파드가 IMDS 대신 전용 메커니즘으로 AWS 자격증명을 받으므로 hop limit과 무관하다. 하지만 학습 목적으로 IMDS 기반 접근도 테스트할 수 있도록 열어 둔 것이다.

## Addon

addon 구성을 살펴보자.

```hcl
addons = {
  coredns    = { most_recent = true }
  kube-proxy = { most_recent = true }
  vpc-cni    = {
    most_recent    = true
    before_compute = true  # 노드 그룹보다 먼저 배포
  }
  metrics-server = { most_recent = true }
  external-dns = {
    most_recent = true
    configuration_values = jsonencode({
      txtOwnerId = var.ClusterBaseName
      policy     = "sync"
    })
  }
  eks-pod-identity-agent = { most_recent = true }
  cert-manager           = { most_recent = true }
}
```

총 7종의 addon을 구성한다. 기본 3종(coredns, kube-proxy, vpc-cni)과 함께 인증/인가 실습에 필요한 4종을 추가했다. VPC CNI는 `WARM_ENI_TARGET` 등 별도 설정 없이 기본값을 사용한다. 이번 주차는 네트워킹이 아닌 인증/인가가 주제이므로 기본값으로 충분하다.

각 addon의 역할은 다음과 같다.

| addon | 역할 | 비고 |
| --- | --- | --- |
| **metrics-server** | 노드/파드의 CPU, 메모리 사용량을 수집하여 `kubectl top` 등에 제공 | HPA(Horizontal Pod Autoscaler) 동작에도 필요 |
| **external-dns** | K8s Service/Ingress의 호스트명을 Route 53 DNS 레코드로 자동 동기화 | `policy = "sync"`는 K8s에서 삭제된 리소스의 DNS 레코드도 삭제한다는 의미 |
| **eks-pod-identity-agent** | EKS Pod Identity 기능을 위한 에이전트 (DaemonSet) | 파드가 AWS IAM 권한을 받는 **IRSA의 차세대 방식** |
| **cert-manager** | K8s 클러스터 내 TLS 인증서를 자동 발급/갱신 | Let's Encrypt 등과 연동 가능 |

특히 **eks-pod-identity-agent**는 이번 주차 인증/인가 실습의 핵심이다. IRSA가 OIDC Provider + IAM Trust Policy 조합으로 파드에 AWS 권한을 부여했다면, Pod Identity는 EKS가 직접 관리하는 더 간단한 방식이다. 이 에이전트가 DaemonSet으로 각 노드에서 실행되면서 파드의 AWS 자격증명 요청을 처리한다.

## outputs.tf

```hcl
output "configure_kubectl" {
  description = "Configure kubectl: run this command to update your kubeconfig"
  value       = "aws eks --region ${var.TargetRegion} update-kubeconfig --name ${var.ClusterBaseName}"
}
```

`configure_kubectl` 출력으로 kubeconfig 설정 명령어를 제공한다.

<br>

# 배포

## Terraform 실행

```bash
git clone https://github.com/gasida/aews.git
cd aews/4w

terraform init
terraform plan
nohup sh -c "terraform apply -auto-approve" > create.log 2>&1 &
tail -f create.log
```

SSH 관련 변수가 없으므로 별도의 환경 변수 설정 없이 바로 `terraform apply`를 실행하면 된다.

<details markdown="1">
<summary><b>Terraform 전체 코드 (var.tf, vpc.tf, eks.tf, outputs.tf)</b></summary>

**var.tf**

```hcl
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

variable "WorkerNodeInstanceType" {
  description = "EC2 instance type for the worker nodes."
  type        = string
  default     = "t3.medium"
}

variable "WorkerNodeCount" {
  description = "Number of worker nodes."
  type        = number
  default     = 2
}

variable "WorkerNodeVolumesize" {
  description = "Volume size for worker nodes (in GiB)."
  type        = number
  default     = 30
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
```

**vpc.tf**

```hcl
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
  map_public_ip_on_launch    = true

  igw_tags         = { "Name" = "${var.ClusterBaseName}-IGW" }
  nat_gateway_tags = { "Name" = "${var.ClusterBaseName}-NAT" }

  public_subnet_tags = {
    "Name"                   = "${var.ClusterBaseName}-PublicSubnet"
    "kubernetes.io/role/elb" = "1"
  }

  private_subnet_tags = {
    "Name"                            = "${var.ClusterBaseName}-PrivateSubnet"
    "kubernetes.io/role/internal-elb" = "1"
  }

  tags = { "Environment" = "cloudneta-lab" }
}
```

**eks.tf**

```hcl
provider "aws" {
  region = var.TargetRegion
}

resource "aws_security_group" "node_group_sg" {
  name        = "${var.ClusterBaseName}-node-group-sg"
  description = "Security group for EKS Node Group"
  vpc_id      = module.vpc.vpc_id
  tags = { Name = "${var.ClusterBaseName}-node-group-sg" }
}

resource "aws_security_group_rule" "allow_ssh" {
  type              = "ingress"
  from_port         = 0
  to_port           = 0
  protocol          = "-1"
  cidr_blocks       = [var.VpcBlock]
  security_group_id = aws_security_group.node_group_sg.id
}

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

module "eks" {
  source  = "terraform-aws-modules/eks/aws"
  version = "~> 21.0"

  name              = var.ClusterBaseName
  kubernetes_version = var.KubernetesVersion

  vpc_id     = module.vpc.vpc_id
  subnet_ids = module.vpc.private_subnets

  enable_irsa = true

  endpoint_public_access  = true
  endpoint_private_access = true

  enabled_log_types = [
    "api", "scheduler", "authenticator", "controllerManager", "audit"
  ]

  enable_cluster_creator_admin_permissions = true

  eks_managed_node_groups = {
    primary = {
      name            = "${var.ClusterBaseName}-ng-1"
      use_name_prefix = false
      ami_type        = "AL2023_x86_64_STANDARD"
      instance_types  = ["${var.WorkerNodeInstanceType}"]
      desired_size    = var.WorkerNodeCount
      max_size        = var.WorkerNodeCount + 2
      min_size        = var.WorkerNodeCount - 1
      disk_size       = var.WorkerNodeVolumesize
      subnets         = module.vpc.private_subnets
      vpc_security_group_ids = [aws_security_group.node_group_sg.id]

      iam_role_name            = "${var.ClusterBaseName}-ng-1"
      iam_role_use_name_prefix = false
      iam_role_additional_policies = {
        "${var.ClusterBaseName}ExternalDNSPolicy" = aws_iam_policy.external_dns_policy.arn
        AmazonSSMManagedInstanceCore = "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
      }

      metadata_options = {
        http_endpoint               = "enabled"
        http_tokens                 = "required"
        http_put_response_hop_limit = 2
      }

      labels = { tier = "primary" }

      cloudinit_pre_nodeadm = [
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
  }

  addons = {
    coredns    = { most_recent = true }
    kube-proxy = { most_recent = true }
    vpc-cni    = { most_recent = true, before_compute = true }
    metrics-server         = { most_recent = true }
    external-dns = {
      most_recent = true
      configuration_values = jsonencode({
        txtOwnerId = var.ClusterBaseName
        policy     = "sync"
      })
    }
    eks-pod-identity-agent = { most_recent = true }
    cert-manager           = { most_recent = true }
  }

  tags = {
    Environment = "cloudneta-lab"
    Terraform   = "true"
  }
}
```

**outputs.tf**

```hcl
output "configure_kubectl" {
  description = "Configure kubectl: run this command to update your kubeconfig"
  value       = "aws eks --region ${var.TargetRegion} update-kubeconfig --name ${var.ClusterBaseName}"
}
```

</details>

## kubeconfig 설정

배포가 완료되면 kubeconfig를 설정한다.

```bash
aws eks --region ap-northeast-2 update-kubeconfig --name myeks
```

context 이름이 ARN 형식이라 길고 불편하므로 짧게 변경한다.

```bash
kubectl config rename-context \
  $(kubectl config current-context) \
  myeks
```

```bash
kubens default
```

<br>

# 기본 정보 확인

## 노드 확인

```bash
kubectl get node --label-columns=node.kubernetes.io/instance-type,eks.amazonaws.com/capacityType,topology.kubernetes.io/zone
```

2개 노드가 서로 다른 가용 영역에 배포되어 있다. 노드 호스트명이 프라이빗 서브넷 대역(`192.168.12.0/22`, `192.168.16.0/22` 등)의 IP를 갖고 있는 것을 확인할 수 있다.

## 파드 확인

```bash
kubectl get pod -A
```

aws-node, coredns, kube-proxy와 함께 cert-manager, external-dns, eks-pod-identity-agent, metrics-server 파드가 실행된다. 특히 **eks-pod-identity-agent**가 DaemonSet으로 각 노드에 배포되어 있는 것을 확인할 수 있다.

## Addon 확인

```bash
eksctl get addon --cluster myeks
```

7개 addon이 모두 ACTIVE 상태인지 확인한다. external-dns의 `CONFIGURATION VALUES`에 `txtOwnerId`와 `policy` 설정이 반영되어 있어야 한다.

<br>

# 정리

4주차 실습 환경은 **보안 강화**(프라이빗 서브넷, SSH 제거, SSM 대체)와 **인증/인가 실습 준비**(CP 로깅, Pod Identity Agent, cert-manager)에 초점을 맞추고 있다.

| 구성 | 목적 |
| --- | --- |
| 프라이빗 서브넷 + NAT GW | 노드를 외부에서 직접 접근 불가능하게 격리 |
| SSM으로 노드 접근 (SSH 없음) | 키 관리 없는 안전한 노드 접근 |
| CP 로그 전면 활성화 | authenticator/audit 로그로 인증 흐름 추적 |
| eks-pod-identity-agent | Pod Identity 실습 기반 마련 |
| cert-manager | TLS 인증서 자동 관리 |
| IMDS hop limit 2 | 파드에서 EC2 메타데이터 접근 허용 (학습용) |

<br>

