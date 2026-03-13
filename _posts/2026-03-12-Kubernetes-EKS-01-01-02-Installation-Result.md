---
title:  "[EKS] EKS: Public-Public EKS 클러스터 - 2. 배포"
excerpt: "Terraform init/plan/apply를 실행하고, Public-Public 구성의 EKS 클러스터 배포 결과를 확인하자."
categories:
  - Kubernetes
toc: true
header:
  teaser: /assets/images/blog-Dev.jpg
tags:
  - Kubernetes
  - AWS
  - EKS
  - Terraform
  - AWS-EKS-Workshop-Study
  - AWS-EKS-Workshop-Study-Week-1

---

*[서종호(가시다)](https://www.linkedin.com/in/gasida99/)님의 AWS EKS Workshop Study(AEWS) 1주차 학습 내용을 기반으로 합니다.*

<br>

# TL;DR

이번 글에서는 **Terraform으로 EKS 클러스터를 실제 배포하고 결과를 확인**한다.

- **변수 주입**: `TF_VAR_` 환경변수로 키 페어, SSH 접근 CIDR 주입
- **배포 흐름**: `terraform init` → `terraform plan` → `terraform apply` (약 12분 소요)
- **생성 리소스**: 총 52개 (VPC, 서브넷, IGW, 보안그룹, EKS 클러스터, 노드그룹, KMS, 애드온 등)
- **Public-Public 구성의 한계**: 보안적으로 권장되지 않으며, 다음 단계에서 Private 접근을 활성화

<br>

# 변수 주입

[이전 글]({% post_url 2026-03-12-Kubernetes-EKS-01-01-01-Installation %})에서 분석한 `var.tf`에서 `default`가 없는 두 변수(`KeyName`, `ssh_access_cidr`)에 값을 주입한다.

```bash
aws ec2 describe-key-pairs --query "KeyPairs[].KeyName" --output text
export TF_VAR_KeyName=$(aws ec2 describe-key-pairs --query "KeyPairs[].KeyName" --output text)
export TF_VAR_ssh_access_cidr=$(curl -s ipinfo.io/ip)/32
echo $TF_VAR_KeyName $TF_VAR_ssh_access_cidr
```

```
my-eks-keypair 118.xxx.xxx.xxx/32
```

> `curl -s ipinfo.io/ip`로 현재 공인 IP를 조회할 수 있다. 공유기(NAT) 뒤에 있더라도 외부에서 보이는 공인 IP를 반환한다. 이 IP를 `/32`로 CIDR 표기하여 내 IP에서만 워커 노드에 접근할 수 있도록 제한한다.



`TF_VAR_` 접두사가 붙은 환경변수는 Terraform이 자동으로 인식하여 변수에 매핑한다. `TF_VAR_KeyName` → `var.KeyName`, `TF_VAR_ssh_access_cidr` → `var.ssh_access_cidr`로 매핑된다. 

Terraform 변수 우선순위에서 실행 시 주입되는 변수가 가장 높다. [Ansible 변수 우선순위]({% post_url 2026-01-25-Kubernetes-Kubespray-03-02-01 %}#ansible-변수-우선순위)와 마찬가지로 실행 시 주입되는 것이 `default`보다 우선한다.



<br>

# 배포 실행

## terraform init

```bash
terraform init
```

```
Initializing the backend...
Initializing modules...
Downloading registry.terraform.io/terraform-aws-modules/eks/aws 21.15.1 for eks...
- eks in .terraform/modules/eks
- eks.eks_managed_node_group in .terraform/modules/eks/modules/eks-managed-node-group
- eks.eks_managed_node_group.user_data in .terraform/modules/eks/modules/_user_data
- eks.fargate_profile in .terraform/modules/eks/modules/fargate-profile
Downloading registry.terraform.io/terraform-aws-modules/kms/aws 4.0.0 for eks.kms...
- eks.kms in .terraform/modules/eks.kms
- eks.self_managed_node_group in .terraform/modules/eks/modules/self-managed-node-group
- eks.self_managed_node_group.user_data in .terraform/modules/eks/modules/_user_data
Downloading registry.terraform.io/terraform-aws-modules/vpc/aws 6.6.0 for vpc...
- vpc in .terraform/modules/vpc

Initializing provider plugins...
- Finding hashicorp/tls versions matching ">= 4.0.0"...
- Finding hashicorp/cloudinit versions matching ">= 2.0.0"...
- Finding hashicorp/null versions matching ">= 3.0.0"...
- Finding hashicorp/aws versions matching ">= 6.0.0, >= 6.28.0"...
- Finding hashicorp/time versions matching ">= 0.9.0"...
- Installing hashicorp/aws v6.36.0...
- Installed hashicorp/aws v6.36.0 (signed by HashiCorp)
- Installing hashicorp/time v0.13.1...
- Installed hashicorp/time v0.13.1 (signed by HashiCorp)
- Installing hashicorp/tls v4.2.1...
- Installed hashicorp/tls v4.2.1 (signed by HashiCorp)
- Installing hashicorp/cloudinit v2.3.7...
- Installed hashicorp/cloudinit v2.3.7 (signed by HashiCorp)
- Installing hashicorp/null v3.2.4...
- Installed hashicorp/null v3.2.4 (signed by HashiCorp)

Terraform has been successfully initialized!
```

<br>

### init 결과 분석

`terraform init`은 **모듈 먼저, Provider 나중** 순서로 처리한다. 모듈 내부에도 `required_providers`가 있을 수 있어서, 모듈을 다 받아야 전체 필요한 Provider 목록이 확정되기 때문이다.

init 실행 후 `.terraform` 디렉토리에 모듈과 Provider가 저장된다.

```bash
ls -al .terraform/
```

```
drwxr-xr-x@ 4 eraser  staff  128 .
drwxr-xr-x@ 7 eraser  staff  224 ..
drwxr-xr-x@ 6 eraser  staff  192 modules
drwxr-xr-x@ 3 eraser  staff   96 providers
```

| 경로 | 내용 |
| --- | --- |
| `.terraform/modules/eks` | EKS 모듈 (v21.15.1) |
| `.terraform/modules/eks.kms` | EKS 모듈이 내부적으로 의존하는 KMS 하위 모듈 |
| `.terraform/modules/vpc` | VPC 모듈 (v6.6.0) |
| `.terraform/providers/registry.terraform.io/hashicorp/aws` | AWS Provider (v6.36.0) |

모듈 경로의 점(`.`) 표기는 계층 구조를 나타낸다. `eks.kms`는 "eks 모듈 안에서 쓰는 kms 모듈"이라는 뜻이다.

<br>

실제 적용된 모듈 버전은 `modules.json`에서 확인할 수 있다. `eks`와 `vpc`만 필터링한 이유는, [코드 분석]({{ site.url }}/kubernetes/Kubernetes-EKS-01-01-01-Installation#모듈-ㅅ)에서 살펴본 것처럼 `module` 블록의 `source`로 선언된 것이 이 두 개뿐이기 때문이다.

```bash
cat .terraform/modules/modules.json | jq '.Modules[] | select(.Key == "eks" or .Key == "vpc") | {Key, Version}'
```

```json
{ "Key": "eks", "Version": "21.15.1" }
{ "Key": "vpc", "Version": "6.6.0" }
```

<br>

`.terraform.lock.hcl` 파일도 생성된다. Provider의 정확한 버전과 체크섬을 기록하여, 다른 환경에서 `terraform init`을 해도 동일한 버전이 설치되도록 보장한다. Node.js의 `package-lock.json`과 같은 역할이므로 VCS(git)에 커밋하는 것이 권장된다.

실제 파일을 발췌하면 다음과 같다.

```hcl
# This file is maintained automatically by "terraform init".
# Manual edits may be lost in future updates.

provider "registry.terraform.io/hashicorp/aws" {
  version     = "6.36.0"
  constraints = ">= 6.0.0, >= 6.28.0"
  hashes = [
    "h1:UYt6mrz0d3PfTJRbJAxe+fLcJt7voXJCLLdwfHrApGk=",
    "zh:0eb4481315564aaeec4905a804fd0df22c40f509ad2af63615eeaa90abacf81c",
    ...
  ]
}

provider "registry.terraform.io/hashicorp/cloudinit" {
  version     = "2.3.7"
  constraints = ">= 2.0.0"
  hashes = [ ... ]
}

provider "registry.terraform.io/hashicorp/null" {
  version     = "3.2.4"
  constraints = ">= 3.0.0"
  hashes = [ ... ]
}

provider "registry.terraform.io/hashicorp/time" {
  version     = "0.13.1"
  constraints = ">= 0.9.0"
  hashes = [ ... ]
}

provider "registry.terraform.io/hashicorp/tls" {
  version     = "4.2.1"
  constraints = ">= 4.0.0"
  hashes = [ ... ]
}
```

`eks.tf`에서 직접 선언한 Provider는 `hashicorp/aws` 하나뿐이지만, lock 파일에는 5개의 Provider가 기록되어 있다. 나머지 4개(`cloudinit`, `null`, `time`, `tls`)는 EKS 모듈과 VPC 모듈이 내부적으로 의존하는 Provider들로, `terraform init` 시 의존성 트리를 따라 자동으로 함께 다운로드된 것이다.

| Provider | 버전 | 사용처 |
| --- | --- | --- |
| `hashicorp/aws` | 6.36.0 | `eks.tf`에서 직접 선언. 모든 AWS 리소스 관리 |
| `hashicorp/cloudinit` | 2.3.7 | EKS 모듈이 워커 노드 userdata 생성 시 사용 |
| `hashicorp/null` | 3.2.4 | 모듈 내부에서 `null_resource` 등 보조 리소스에 사용 |
| `hashicorp/time` | 0.13.1 | 모듈 내부에서 타이밍 제어(예: 리소스 생성 대기)에 사용 |
| `hashicorp/tls` | 4.2.1 | EKS 모듈이 TLS 인증서 관련 처리에 사용 |

각 Provider 블록의 `constraints` 필드(예: `>= 6.0.0, >= 6.28.0`)는 모듈들이 요구하는 최소 버전 조건이고, `version` 필드(예: `6.36.0`)가 그 조건을 만족하는 실제 설치된 버전이다. `hashes`는 다운로드된 바이너리의 체크섬으로, 다른 환경에서도 동일한 바이너리가 설치되었는지 검증하는 데 사용된다.

<br>

## terraform plan

```bash
terraform plan
```

`plan`은 실제 변경 없이 "이렇게 만들 거야"를 미리 보여주는 dry-run이다. 주요 리소스의 plan 결과를 발췌한다.

### VPC 관련

```
# module.vpc.aws_vpc.this[0] will be created
+ resource "aws_vpc" "this" {
    + cidr_block           = "192.168.0.0/16"
    + enable_dns_hostnames = true
    + enable_dns_support   = true
    + tags                 = {
        + "Name" = "myeks-VPC"
      }
  }

# module.vpc.aws_subnet.public[0] will be created
+ resource "aws_subnet" "public" {
    + availability_zone       = "ap-northeast-2a"
    + cidr_block              = "192.168.1.0/24"
    + map_public_ip_on_launch = true
    + tags                    = {
        + "Name"                   = "myeks-PublicSubnet"
        + "kubernetes.io/role/elb" = "1"
      }
  }
```

`var.tf`에서 선언한 값들이 VPC 모듈을 통해 실제 리소스로 변환되는 것을 확인할 수 있다. 서브넷의 `kubernetes.io/role/elb` 태그도 의도대로 적용된다.

### EKS 노드그룹

```
# module.eks.module.eks_managed_node_group["default"].aws_eks_node_group.this[0]
+ resource "aws_eks_node_group" "this" {
    + ami_type        = "AL2023_x86_64_STANDARD"
    + capacity_type   = "ON_DEMAND"
    + instance_types  = ["t3.medium"]
    + node_group_name = "myeks-node-group"
    + version         = "1.34"

    + scaling_config {
        + desired_size = 2
        + max_size     = 4
        + min_size     = 1
      }
  }
```

### KMS 키 (자동 생성)

```
# module.eks.module.kms.aws_kms_key.this[0] will be created
+ resource "aws_kms_key" "this" {
    + description        = "myeks cluster encryption key"
    + enable_key_rotation = true
    + key_usage          = "ENCRYPT_DECRYPT"
  }
```

코드에 KMS 설정을 명시하지 않았는데도 EKS 모듈이 **KMS 키를 자동 생성**하여 클러스터의 **etcd Secret 암호화**에 사용한다(`eks.kms` 하위 모듈). 모듈이 내부적으로 뭘 해주는지 의식해야 하는 좋은 사례다.

### Plan 요약

```
Plan: 52 to add, 0 to change, 0 to destroy.
```

총 52개의 리소스가 새로 생성될 예정이다.

<br>

## terraform apply

`plan` 결과를 확인한 뒤, 백그라운드로 apply를 실행한다. 약 **12분** 소요된다.

```bash
nohup sh -c "terraform apply -auto-approve" > create.log 2>&1 &
tail -f create.log
```

| 명령어 구성 | 역할 |
| --- | --- |
| `nohup` | SIGHUP 무시. 터미널을 닫아도 프로세스가 죽지 않음 |
| `&` | 백그라운드 실행 |
| `-auto-approve` | 확인 프롬프트를 건너뛰고 바로 적용 |
| `> create.log 2>&1` | stdout과 stderr를 모두 `create.log`에 기록 |

> **주의**: `-auto-approve`는 `plan` 결과를 이미 확인한 실습 환경이나 CI/CD 파이프라인에서만 사용한다. 프로덕션에서는 `plan` 결과를 눈으로 확인하고 `yes`를 입력하는 것이 안전하다.

<br>

### 리소스 생성 순서

apply 로그를 보면 Terraform이 의존성 그래프에 따라 리소스를 순서대로 생성하는 것을 확인할 수 있다.

**1단계: VPC + IAM Role (병렬)**

```
module.vpc.aws_vpc.this[0]: Creating...
module.eks.aws_iam_role.this[0]: Creating...
module.vpc.aws_vpc.this[0]: Creation complete after 1s [id=vpc-0bbe44f3...]
module.eks.aws_iam_role.this[0]: Creation complete after 1s
```

VPC와 EKS 클러스터의 IAM Role은 서로 의존성이 없으므로 병렬로 생성된다.

**2단계: 서브넷 + 보안그룹 + KMS (VPC 의존)**

```
module.vpc.aws_subnet.public[0]: Creating...
module.vpc.aws_subnet.public[1]: Creating...
module.vpc.aws_subnet.public[2]: Creating...
aws_security_group.node_group_sg: Creating...
module.eks.module.kms.aws_kms_key.this[0]: Creating...
```

VPC가 생성된 후 서브넷과 보안그룹이 생성된다. KMS 키도 이 시점에 생성된다.

**3단계: EKS 클러스터 (가장 오래 걸림)**

```
module.eks.aws_eks_cluster.this[0]: Creating...
module.eks.aws_eks_cluster.this[0]: Still creating... [1m0s elapsed]
...
module.eks.aws_eks_cluster.this[0]: Creation complete after 6m42s [id=myeks]
```

EKS 클러스터 생성이 **약 6분 42초**로 가장 오래 걸린다. AWS가 컨트롤 플레인(API Server, etcd 등)을 프로비저닝하는 시간이다.

**4단계: VPC CNI (before_compute)**

```
module.eks.aws_eks_addon.before_compute["vpc-cni"]: Creating...
module.eks.aws_eks_addon.before_compute["vpc-cni"]: Creation complete after 24s [id=myeks:vpc-cni]
```

`before_compute = true` 설정 덕분에 VPC CNI가 노드그룹보다 먼저 설치된다.

**5단계: 노드그룹 (VPC CNI 이후)**

```
module.eks.module.eks_managed_node_group["default"].aws_eks_node_group.this[0]: Creating...
module.eks.module.eks_managed_node_group["default"].aws_eks_node_group.this[0]: Creation complete after 2m9s
```

노드그룹 생성에 약 2분 9초 소요된다.

**6단계: 나머지 애드온 (노드그룹 이후)**

```
module.eks.aws_eks_addon.this["coredns"]: Creating...
module.eks.aws_eks_addon.this["kube-proxy"]: Creating...
module.eks.aws_eks_addon.this["kube-proxy"]: Creation complete after 24s
module.eks.aws_eks_addon.this["coredns"]: Creation complete after 45s
```

CoreDNS와 kube-proxy는 노드그룹이 준비된 후 설치된다.

<br>

### 최종 결과

```
Apply complete! Resources: 52 added, 0 changed, 0 destroyed.
```

52개 리소스가 모두 생성되었다.

![eks-deploy-complete]({{site.url}}/assets/images/eks-deploy-complete.png){: .align-center width="600"}

<br>

# Public-Public 구성 분석

배포된 클러스터는 다음과 같은 **Public-Public 구성**이다.

```
kubectl (내 PC) ──── 인터넷 ──── EKS API Server (AWS 관리)
                                       │
                                       │ (인터넷 경유)
                                       │
               Worker Node (퍼블릭 서브넷, 퍼블릭 IP)

CI/CD, 모니터링 등 ──── 인터넷 ──── EKS API Server
```

**모든 통신이 퍼블릭 인터넷을 경유**한다.

- `kubectl` → 인터넷 → EKS API 서버
- 워커 노드 → 인터넷 → EKS API 서버 (VPC 내부가 아닌 퍼블릭 경로)
- CI/CD, 모니터링 등 → 인터넷 → EKS API 서버

<br>

## 이 구성의 한계

Public-Public 구성은 **보안적으로 권장되지 않는 구조**다.

| 문제 | 설명 |
| --- | --- |
| **API 서버 노출** | 전 세계 누구나 API 서버에 접근 시도 가능 |
| **비효율적 경로** | 워커 노드 ↔ 컨트롤 플레인이 퍼블릭 인터넷을 경유. 프라이빗 통신이 더 효율적 |
| **보안그룹 과다 개방** | `protocol = "-1"`로 모든 포트/프로토콜 허용. 프로덕션에서는 SSH(22), kubelet(10250) 등 필요한 포트만 열어야 함 |
| **API 접근 CIDR 제한 없음** | `endpoint_public_access_cidrs`가 주석 처리되어 있어 전 세계에서 접근 가능 |

비용 측면에서는 NAT Gateway를 사용하지 않으므로 절감 효과가 있다.

<br>

## 다음 단계: Public + Private 구성

다음에는 `endpoint_private_access = true`로 변경하여 **Public + Private 구성**으로 전환한다.

```hcl
endpoint_public_access = true
endpoint_private_access = true   # false → true
```

| | Public-Public (현재) | Public + Private (다음) |
| --- | --- | --- |
| **외부 → API 서버** | 인터넷 (퍼블릭) | 인터넷 (퍼블릭) |
| **워커 노드 → API 서버** | 인터넷 (퍼블릭) | **VPC 내부 (프라이빗)** |
| **워커 노드 위치** | 퍼블릭 서브넷 필수 | 프라이빗 서브넷 가능 |
| **NAT Gateway** | 불필요 | 필요 (프라이빗 서브넷 사용 시) |

<br>

# 배포 시 기억할 점

## KMS 암호화 자동 설정

`plan` 결과를 보면 코드에 명시하지 않았는데도 EKS 모듈이 KMS 키를 자동 생성한다. `eks.kms` 하위 모듈이 기본값으로 활성화되어 etcd Secret을 암호화한다. 모듈이 내부적으로 무엇을 해주는지 `plan` 단계에서 반드시 확인해야 한다.

## VPC CNI before_compute

`before_compute = true` 설정 하나가 빠지면 노드가 올라온 뒤에 CNI가 설치되어 **초기 Pod가 네트워킹 문제로 실패**할 수 있다. 사소해 보이지만 실무에서 트러블슈팅하기 까다로운 부분이다.

## -auto-approve 주의

실습에서는 편의상 `-auto-approve`를 사용했지만, 프로덕션에서는 `plan` 결과를 직접 눈으로 확인한 뒤 `yes`를 입력하는 워크플로우가 안전하다.

<br>

# 마무리

Terraform으로 EKS 클러스터를 배포했다. 전체 과정을 정리하면 다음과 같다.

| 단계 | 명령어 | 소요 시간 | 핵심 |
| --- | --- | --- | --- |
| **변수 주입** | `export TF_VAR_...` | - | `default` 없는 변수에 값 제공 |
| **초기화** | `terraform init` | ~19초 | 모듈 먼저 → Provider 나중 |
| **계획** | `terraform plan` | ~수초 | 52개 리소스 생성 예정 확인 |
| **적용** | `terraform apply` | ~12분 | EKS 클러스터 생성이 6분 42초로 가장 오래 걸림 |

현재 구성은 학습 목적의 Public-Public이다. 보안적으로 권장되지 않으므로, 다음 단계에서 Private 접근을 활성화하고 보안그룹을 강화한다.

<br>
