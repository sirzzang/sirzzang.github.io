---
title:  "[EKS] EKS: Public-Public EKS 클러스터 - 1. Terraform 코드 분석"
excerpt: "Public-Public 엔드포인트 구성을 가진 EKS 클러스터를 배포하기 위한 Terraform 코드를 분석해보자."
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
  - VPC
  - AWS-EKS-Workshop-Study
  - AWS-EKS-Workshop-Study-Week-1

---

*[서종호(가시다)](https://www.linkedin.com/in/gasida99/)님의 AWS EKS Workshop Study(AEWS) 1주차 학습 내용을 기반으로 합니다.*

<br>

# TL;DR

이번 글에서는 Public-Public 엔드포인트 구성의 EKS 클러스터를 배포하기 위한 **Terraform 코드를 분석**한다.

- **코드 구조**: `var.tf`(변수 선언), `vpc.tf`(네트워크), `eks.tf`(클러스터 + 노드그룹)로 역할별 분리
- **VPC**: 퍼블릭 서브넷 3개(AZ별) + IGW 구성. DNS 설정은 EKS 필수 요건
- **EKS**: Public Endpoint + [관리형 노드 그룹(Managed Node Group)]({% post_url 2026-03-12-Kubernetes-EKS-00-01-EKS-Computing-Group %}#관리형-노드-그룹) + VPC CNI 구성
- **핵심**: Public-Public 구성으로 API 서버와 워커 노드 모두 퍼블릭 인터넷 경유

<br>

# 실습 코드 다운로드

실습 코드를 다운로드하고 1주차 디렉토리로 이동한다.

```bash
git clone https://github.com/gasida/aews.git
cd aews/1w
```

<br>

## 디렉토리 구조

```
aews/1w
├── eks.tf
├── var.tf
└── vpc.tf
```

Terraform에서는 역할별로 `.tf` 파일을 분리하는 것이 일반적인 관행이다. 같은 디렉토리 안의 `.tf` 파일들은 Terraform이 전부 합쳐서 하나로 읽으므로, 파일 분리는 사람이 읽기 편하게 하기 위한 것이다.

| 파일 | 역할 |
| --- | --- |
| `var.tf` (또는 `variables.tf`) | 변수 선언 |
| `vpc.tf` | 네트워크 리소스 정의 |
| `eks.tf` | Provider 설정 + 보안그룹 + EKS 클러스터 + 노드그룹 정의 |

> **참고**: 일반적으로 `provider.tf`, `outputs.tf`, `terraform.tfvars` 등을 추가로 분리하기도 한다. 이 실습에서는 Provider 설정이 `eks.tf` 안에 포함되어 있다.

이제 `var.tf` → `vpc.tf` → `eks.tf` 순서로 각 파일을 분석한다. 변수 정의를 먼저 파악하고, 네트워크를 이해한 뒤, 클러스터 설정을 보는 흐름이다.

<br>

# var.tf: 변수 선언

`var.tf`는 전체 인프라에서 사용할 변수를 선언하는 파일이다. 여기서 하는 일은 **"이런 변수가 있다"를 선언하고 모아 놓는 것**이다. 실제 값을 넣는 것이 아니라, 어떤 값들이 파라미터로 들어오는지 전체 그림을 파악할 수 있게 해준다.

```hcl
variable "KeyName" {
  description = "Name of an existing EC2 KeyPair to enable SSH access to the instances."
  type        = string
}

variable "ssh_access_cidr" {
  description = "Allowed CIDR for SSH access"
  type        = string
}

variable "ClusterBaseName" {
  description = "Base name of the cluster."
  type        = string
  default     = "myeks"
}

variable "KubernetesVersion" {
  description = "Kubernetes version for the EKS cluster."
  type        = string
  default     = "1.34"
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
  default     = ["192.168.1.0/24", "192.168.2.0/24", "192.168.3.0/24"]
}
```

<br>

## 변수 정리

변수들을 역할별로 정리하면 다음과 같다.

| 변수 | 기본값 | 설명 |
| --- | --- | --- |
| `KeyName` | *(없음)* | EC2 키 페어 이름. 배포 시 주입 |
| `ssh_access_cidr` | *(없음)* | SSH 접근 허용 CIDR. 배포 시 주입 |
| `ClusterBaseName` | `myeks` | 클러스터 및 리소스 이름 접두사 |
| `KubernetesVersion` | `1.34` | EKS 클러스터 K8s 버전 |
| `WorkerNodeInstanceType` | `t3.medium` | 워커 노드 인스턴스 타입 |
| `WorkerNodeCount` | `2` | 워커 노드 수 |
| `WorkerNodeVolumesize` | `30` | 워커 노드 디스크 크기 (GiB) |
| `TargetRegion` | `ap-northeast-2` | AWS 리전 |
| `availability_zones` | `[a, b, c]` | 가용 영역 목록 |
| `VpcBlock` | `192.168.0.0/16` | VPC CIDR 블록 |
| `public_subnet_blocks` | `[1.0/24, 2.0/24, 3.0/24]` | 퍼블릭 서브넷 CIDR 목록 |

여기서 중요한 점은, `var.tf`에서는 **실제 값을 넣지 않는다**는 것이다. 변수를 선언하기만 할 뿐, 실제 값을 넣는 건 배포 시 하게 된다. `default`가 선언된 변수들은 별도로 값을 넣지 않아도 기본값이 사용되고, `default`가 없는 `KeyName`과 `ssh_access_cidr`은 뒤의 배포 단계에서 값을 주입해줘야 한다.

> **참고**: 네이밍 컨벤션이 혼재되어 있다(`KeyName`은 PascalCase, `ssh_access_cidr`은 snake_case). 공식적으로 정해진 것은 없으나 Terraform 권장은 snake_case이다. 다만 AWS CloudFormation 파라미터 스타일인 PascalCase도 자주 쓰인다.

<br>

## 주요 변수 해설

### VPC 대역

VPC CIDR 블록은 RFC 1918 사설 IP 대역 내에서 자유롭게 선택할 수 있다.

| 대역 | 범위 |
| --- | --- |
| `10.0.0.0/8` | 10.0.0.0 ~ 10.255.255.255 |
| `172.16.0.0/12` | 172.16.0.0 ~ 172.31.255.255 |
| `192.168.0.0/16` | 192.168.0.0 ~ 192.168.255.255 |

이 실습에서는 `192.168.0.0/16`을 사용한다. 실무에서는 다른 VPC나 온프레미스 네트워크 대역과 겹치지 않도록 설계하는 것이 중요하다.

### 퍼블릭 서브넷

VPC 전체 대역 중 일부를 AZ별로 퍼블릭 서브넷으로 지정한다.

| 서브넷 | AZ | CIDR | IP 수 |
| --- | --- | --- | --- |
| Public Subnet 1 | ap-northeast-2a | `192.168.1.0/24` | 254개 |
| Public Subnet 2 | ap-northeast-2b | `192.168.2.0/24` | 254개 |
| Public Subnet 3 | ap-northeast-2c | `192.168.3.0/24` | 254개 |

"퍼블릭"의 의미는 서브넷의 라우팅 테이블에 **인터넷 게이트웨이(IGW)로의 경로**가 있다는 뜻이다. IGW 설정은 `vpc.tf`의 VPC 모듈이 자동으로 처리한다.

### 가용 영역(AZ)

AWS는 리전별로 사용 가능한 AZ 목록을 공개하고 있고(`ap-northeast-2`에는 a, b, c, d), 그 중에서 원하는 것을 골라 쓸 수 있다. 참고로 **AZ 이름과 물리적 데이터센터의 매핑은 계정마다 다르다.** A 계정의 `ap-northeast-2a`와 B 계정의 `ap-northeast-2a`가 실제로는 다른 물리 DC일 수 있다. 보안 및 사용자 쏠림 방지를 위한 AWS의 설계다.

<br>

# vpc.tf: 네트워크 구성

`vpc.tf`는 EKS가 올라갈 네트워크 기반을 정의한다. VPC CIDR, 퍼블릭 서브넷 3개(AZ별), IGW, DNS 설정 등이 포함된다.

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

  enable_nat_gateway = false
  
  manage_default_network_acl = false

  map_public_ip_on_launch = true

  igw_tags = {
    "Name" = "${var.ClusterBaseName}-IGW"
  }

  public_subnet_tags = {
    "Name"                     = "${var.ClusterBaseName}-PublicSubnet"
    "kubernetes.io/role/elb"   = "1"
  }

  tags = {
    "Environment" = "cloudneta-lab"
  }
}
```

<br>

## 모듈 설정

- **source**: [terraform-aws-modules/vpc/aws](https://registry.terraform.io/modules/terraform-aws-modules/vpc/aws/6.5.0) 모듈을 사용한다. 만약 모듈 없이 직접 만든다면 `resource "aws_internet_gateway"` 같은 블록을 하나하나 작성해야 한다.
- **version**: `~>6.5`는 6.5 이상 7.0 미만(`>=6.5.0, <7.0.0`)을 의미한다. 메이저 업데이트로 인한 breaking change를 방지하면서 패치/마이너 업데이트는 받겠다는 뜻이다.
- **name**: `${var.ClusterBaseName}-VPC`로 `var.tf`에서 선언한 `ClusterBaseName` 변수를 이용해서 VPC 이름을 생성한다(기본값 `myeks-VPC`).
- **azs**: `var.tf`에서 선언한 `availability_zones` 변수를 그대로 넘긴다.


> **참고: Semantic Versioning과 `~>` 연산자**
>
> 버전은 `MAJOR.MINOR.PATCH` 형식을 따른다(예: `6.5.0`).
>
> | 구분 | 의미 |
> | --- | --- |
> | MAJOR | 호환이 깨지는 변경 |
> | MINOR | 호환을 유지하며 기능 추가 |
> | PATCH | 버그 수정 |
>
> `~>` 연산자는 Terraform에서 **Pessimistic Constraint Operator**라고 부른다. 지정한 버전 이상, 다음 메이저 미만의 범위를 의미하며, breaking change는 막으면서 패치/마이너 업데이트는 자동으로 받을 수 있다.

<br>

`terraform init`을 실행하면 Terraform이 이 `source`와 `version` 선언을 보고 [Terraform Registry](https://registry.terraform.io/)에서 해당 모듈을 `.terraform/modules/` 디렉토리에 다운로드한다. 이 코드에서 `module` 블록의 `source`로 선언된 것은 VPC 모듈(`terraform-aws-modules/vpc/aws`)과 EKS 모듈(`terraform-aws-modules/eks/aws`, `eks.tf`에서 선언) 두 개이므로, 이 두 모듈(및 각 모듈이 내부적으로 의존하는 하위 모듈)이 다운로드된다. 실제 다운로드된 모듈 버전은 배포 결과 확인 시 `modules.json`에서 확인할 수 있다.


<br>

## DNS 설정

| 설정 | 값 | 역할 |
| --- | --- | --- |
| `enable_dns_support` | `true` | VPC 내부에서 AWS 제공 DNS 서버(`169.254.169.253`)를 사용 가능하게 함 |
| `enable_dns_hostnames` | `true` | 퍼블릭 IP를 가진 인스턴스에 DNS 호스트네임 자동 부여 |

- **`enable_dns_support = true`**: VPC 내부에서 AWS가 제공하는 DNS 서버를 활성화하는 설정이다. 이 설정이 꺼져 있으면 VPC 안의 인스턴스가 도메인 이름을 IP로 변환할 수 없다.

- **`enable_dns_hostnames = true`**: 퍼블릭 IP를 가진 인스턴스에 `ec2-<IP>.ap-northeast-2.compute.amazonaws.com` 같은 퍼블릭 DNS 호스트네임을 자동으로 부여하는 설정이다.

EKS에서는 이 두 설정이 **필수**다. 없으면 API 서버 엔드포인트 DNS 해석 등이 안 되어 클러스터가 정상 동작하지 않는다.

> **참고: VPC DNS vs CoreDNS**
>
> `enable_dns_support`는 **VPC 레벨의 AWS 내부 DNS 서버**(Amazon Route 53 Resolver)를 켜는 것이고, CoreDNS는 **K8s 클러스터 내부의 서비스 디스커버리용 DNS**다. 둘은 독립적으로 동작하는 다른 레이어이지만, CoreDNS가 외부 도메인을 해석할 때 결국 VPC DNS 서버에 포워딩하므로, VPC DNS가 꺼져 있으면 CoreDNS도 외부 해석이 불가능하다.

<br>

## 네트워크 설정

| 설정 | 값 | 역할 |
| --- | --- | --- |
| `enable_nat_gateway` | `false` | 프라이빗 서브넷이 없으므로 NAT Gateway 불필요 |
| `manage_default_network_acl` | `false` | AWS가 만든 기본 NACL을 그대로 둠 (모든 트래픽 허용) |
| `map_public_ip_on_launch` | `true` | 서브넷에 생성되는 모든 인스턴스에 퍼블릭 IP 자동 할당 |

- **`enable_nat_gateway = false`**: NAT Gateway는 프라이빗 서브넷의 인스턴스가 인터넷에 나갈 때 필요한 것인데, 이 실습에서는 모든 노드가 퍼블릭 서브넷에 있어서 직접 IGW를 통해 인터넷 통신이 가능하므로 필요 없다. NAT Gateway는 시간당 과금 + 데이터 처리 비용이 있어서, 굳이 필요하지 않다면 비활성화하여 비용을 절감한다.

- **`manage_default_network_acl = false`**: Terraform이 VPC의 기본 NACL을 관리하지 않겠다는 뜻이다. AWS가 만든 기본 NACL은 **모든 인바운드/아웃바운드 트래픽을 허용**하므로, 별도 설정 없이도 통신에 문제가 없다.

- **`map_public_ip_on_launch = true`**: 이 설정이 가장 중요하다. 이 서브넷에 생성되는 **모든 인스턴스에 퍼블릭 IP가 자동으로 할당**된다. 이 설정이 없으면 워커 노드가 퍼블릭 서브넷에 있어도 퍼블릭 IP가 없어서 인터넷 통신이 불가능하다. **Public-Public 구성에서 워커 노드가 EKS API 서버와 통신하려면 필수**다. 이 요건에 대한 자세한 내용은 [관리형 노드 그룹 - 네트워크]({% post_url 2026-03-12-Kubernetes-EKS-00-01-EKS-Computing-Group %}#네트워크)를 참고한다.

> **참고: NACL vs. Security Group**
>
> | | NACL | Security Group |
> | --- | --- | --- |
> | **적용 단위** | 서브넷 | 인스턴스(ENI) |
> | **상태** | Stateless (요청/응답 별도 규칙) | Stateful (요청 허용 시 응답 자동 허용) |
> | **규칙** | 허용/거부 모두 가능 | 허용 규칙만 가능 |
>
> 이 실습에서는 Security Group(`eks.tf`의 `node_group_sg`)으로 충분히 제어하므로 NACL을 별도로 관리할 필요가 없다.

<br>

## 태그 설정

### IGW 태그

```hcl
igw_tags = {
  "Name" = "${var.ClusterBaseName}-IGW"
}
```

Internet Gateway에 붙일 태그다. `{ }` 블록인 이유는 Terraform에서 태그가 **key-value map** 형태이기 때문이다. 태그를 여러 개 달 수 있어서 이런 구조를 사용한다. 여기서는 Name 태그 하나만 달고 있다(`myeks-IGW`).

### 퍼블릭 서브넷 태그

```hcl
public_subnet_tags = {
  "Name"                     = "${var.ClusterBaseName}-PublicSubnet"
  "kubernetes.io/role/elb"   = "1"
}
```

`Name` 태그는 `ClusterBaseName` 변수를 이용해서 뒤에 `-PublicSubnet`을 붙인다.

`kubernetes.io/role/elb` 태그가 핵심이다. **AWS Load Balancer Controller**가 이 태그를 보고 "이 서브넷에 인터넷 향 로드밸런서(ELB)를 배치해도 된다"고 판단하는 마커다. K8s에서 `type: LoadBalancer` Service를 만들면, 컨트롤러가 이 태그가 있는 퍼블릭 서브넷을 찾아서 ALB/NLB를 생성한다. 웹 서비스를 외부에 노출할 때(예: 프론트엔드 앱, API 서버 등을 인터넷에서 접근 가능하게 만들 때) 사용된다.

ELB가 배치되면 외부 트래픽이 ELB를 거쳐 워커 노드의 Pod로 라우팅된다. ELB 없이는 외부에서 클러스터 내 서비스에 접근할 방법이 없다(NodePort 제외).

```
클라이언트 → 인터넷 → ALB/NLB (퍼블릭 서브넷에 배치) → 워커 노드의 Pod (kube-proxy 또는 VPC CNI가 라우팅)
```

> 참고로 프라이빗 서브넷에는 `kubernetes.io/role/internal-elb`=`"1"` 태그를 붙인다.

### 공통 태그

```hcl
tags = {
  "Environment" = "cloudneta-lab"
}
```

VPC 모듈이 만드는 **모든 리소스**에 공통으로 붙는 태그다. `Environment = "cloudneta-lab"`으로 스터디 실습 환경임을 표시한다.

<br>

## VPC 모듈이 자동으로 해주는 것

`public_subnets`를 지정하면 VPC 모듈이 내부적으로 다음을 자동 처리한다.

1. **IGW 생성**: `aws_internet_gateway` 리소스 생성
2. **라우팅 테이블 생성**: 퍼블릭 서브넷용 라우팅 테이블에 `0.0.0.0/0 → IGW` 경로 추가
3. **퍼블릭 IP 자동 부여**: `map_public_ip_on_launch = true`이면 해당 서브넷의 인스턴스에 퍼블릭 IP 할당

> **참고**: 라우팅 테이블은 **Longest Prefix Match**로 경로를 매칭한다. VPC 내부 통신(`192.168.0.0/16`)은 로컬 경로로 먼저 매칭되고, 그 외 나머지 모든 트래픽(`0.0.0.0/0`)이 IGW로 빠지는 구조다.

<br>

모듈 없이 직접 만들었다면 최소 다음 리소스 블록을 작성해야 했을 것이다.

1. `aws_vpc` — VPC 생성
2. `aws_subnet` × 3 — AZ별 퍼블릭 서브넷
3. `aws_internet_gateway` — IGW 생성
4. `aws_route_table` — 퍼블릭 라우팅 테이블
5. `aws_route` — `0.0.0.0/0 → IGW` 경로 추가
6. `aws_route_table_association` × 3 — 서브넷에 라우팅 테이블 연결
7. 각 리소스마다 태그, 의존성 설정...

모듈 한 블록으로 끝날 것이 **최소 7~10개 resource 블록**이 된다. 거기에 CIDR 계산, AZ 매핑, 태그 일관성 등 실수 가능성이 크게 늘어난다.


<br>

# eks.tf: EKS 클러스터 구성

`eks.tf`는 핵심 파일이다. Provider 선언, 보안그룹, EKS 모듈이 모두 포함되어 있으며, `vpc.tf`에서 만든 VPC/서브넷을 참조한다.

## Provider

```hcl
provider "aws" {
  region = var.TargetRegion
}
```

AWS Provider 사용을 선언하는 블록이다. Provider 플러그인(실제 바이너리)을 어떻게 설정할지 적는 곳으로, 여기서는 리전만 지정하고 있다. `terraform init` 시 이 선언을 보고 `hashicorp/aws` Provider 플러그인을 다운로드한다.

코드 어디에도 `access_key`나 `secret_key`가 없는데, Terraform의 AWS Provider는 인증 정보가 명시적으로 없으면 아래 순서대로 자격증명을 자동 탐색한다.

1. **Provider 블록 내 직접 지정** (코드에 하드코딩 — 비권장)
   ```hcl
   provider "aws" {
     access_key = "AKIA..."
     secret_key = "wJalr..."
   }
   ```
2. **환경변수** (`AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`)
3. **AWS CLI 프로파일** (`~/.aws/credentials` + `~/.aws/config`)
4. **EC2 Instance Profile / ECS Task Role** (IAM Role이 인스턴스에 붙어 있는 경우)
5. **Web Identity Token** (OIDC 등)

[사전 준비]({% post_url 2026-03-12-Kubernetes-EKS-00-Prerequisites %}#aws-cli-자격증명-설정)에서 `aws configure`로 설정한 인증 정보가 `~/.aws/credentials`에 저장되어 있으므로, 3번 경로로 자동 사용된다. Ansible에서 SSH 키를 `~/.ssh/`에 두면 별도로 명시하지 않아도 자동으로 쓰이는 것과 비슷한 원리다.

이 자격증명의 IAM 사용자가 이후 모든 AWS API 호출의 주체(**caller identity**)가 되며, [클러스터 생성자 권한](#클러스터-생성자-권한) 설정에서 EKS 관리자로 등록되는 대상이기도 하다.

<br>

## 보안그룹

```hcl
resource "aws_security_group" "node_group_sg" {
  name        = "${var.ClusterBaseName}-node-group-sg"
  description = "Security group for EKS Node Group"
  vpc_id      = module.vpc.vpc_id

  tags = {
    Name = "${var.ClusterBaseName}-node-group-sg"
  }
}

resource "aws_security_group_rule" "allow_ssh" {
  type        = "ingress"
  from_port         = 0
  to_port           = 0
  protocol          = "-1"
  cidr_blocks = [
    var.ssh_access_cidr,
    "192.168.1.100/32"
  ]
  security_group_id = aws_security_group.node_group_sg.id
}
```

### 보안그룹 리소스

`aws_security_group.node_group_sg`는 EKS 워커 노드용 보안그룹이다. `vpc_id = module.vpc.vpc_id`에서 VPC 모듈의 output을 참조한다. `terraform-aws-modules/vpc/aws` 모듈이 내부적으로 `aws_vpc` 리소스를 생성하고, 그 결과값을 output으로 노출한다. 모듈의 `outputs.tf`에 `output "vpc_id" { value = aws_vpc.this[0].id }` 같은 선언이 있어서, `module.vpc.vpc_id`로 참조할 수 있다. `.tf` 파일에 직접 보이진 않지만 모듈 내부에 정의되어 있는 것이다.

이 리소스는 **인바운드/아웃바운드 규칙이 없는 빈 보안그룹 껍데기**만 만든다. AWS API 수준에서 `CreateSecurityGroup`을 호출하여 보안그룹을 생성하고, `sg-0a6afe6fd37744d7f` 같은 ID를 발급받는 단계다. 실제 트래픽 허용 규칙은 아래의 `aws_security_group_rule`에서 별도로 부착한다.

> **참고**: Terraform에서는 `aws_security_group` 블록 안에 `ingress { }` 블록을 직접 넣는 인라인 방식도 있지만, 이 코드처럼 `aws_security_group_rule`로 분리하면 규칙을 독립적으로 추가/삭제할 수 있어 관리가 편하다.

### 보안그룹 규칙

`aws_security_group_rule.allow_ssh`는 앞에서 만든 빈 보안그룹에 **인바운드 규칙을 부착**하는 리소스다. AWS API 수준에서는 `AuthorizeSecurityGroupIngress`를 호출하는 것에 해당한다. 각 필드를 살펴보면:

- `type = "ingress"`: 인바운드(들어오는) 트래픽 규칙
- `from_port = 0`, `to_port = 0`: 허용할 포트 범위를 지정하는 것인데, `protocol = "-1"`과 함께 쓰이면 의미가 달라짐
- `protocol = "-1"`: **모든 프로토콜**(TCP, UDP, ICMP 등 전부)을 의미. 이 경우 포트 범위는 무시되어 `0`/`0`으로 설정

즉, 지정된 CIDR에서 오는 **모든 프로토콜의 모든 포트 트래픽을 허용**하는 규칙이다. 접속 대상만 CIDR로 제한하되, 포트나 프로토콜은 제한하지 않는 구조다.

> 참고로, SSH(22번 포트)만 허용하려면 다음과 같이 설정한다.
>
> ```hcl
> from_port = 22
> to_port   = 22
> protocol  = "tcp"
> ```

`cidr_blocks`에는 두 값이 들어간다.

| CIDR | 설명 |
| --- | --- |
| `var.ssh_access_cidr` | 배포 시 주입하는 내 실습 환경 IP |
| `192.168.1.100/32` | AZ-a 퍼블릭 서브넷(`192.168.1.0/24`) 내 특정 인스턴스 IP |

`192.168.1.100/32`에 대해 조금 더 살펴보면, `192.168.1.0/24`는 AZ-a의 퍼블릭 서브넷 대역이고 `192.168.1.100`은 그 서브넷 안의 특정 인스턴스 하나를 가리킨다. 현재 구성에서는 `map_public_ip_on_launch = true`이고 별도의 bastion 인스턴스 리소스가 정의되어 있지 않으므로, 실제로 `192.168.1.100`을 쓰는 리소스가 이 코드 안에는 없다. 다만 향후 이 서브넷에 **bastion host(점프 서버)**나 관리용 인스턴스를 `192.168.1.100`으로 배치할 때, 그 인스턴스에서 워커 노드로 접근할 수 있도록 미리 허용해 둔다. 

### Terraform 리소스 참조 추적

`security_group_id = aws_security_group.node_group_sg.id`에서 앞에서 생성한 보안그룹의 ID를 참조한다. 이 참조가 바로 **"빈 껍데기를 먼저 만들고, 거기에 규칙을 붙인다"**는 두 단계 구조를 Terraform이 자동으로 보장하는 메커니즘이다.

| 순서 | 리소스 | AWS API | 하는 일 |
| --- | --- | --- | --- |
| 1 | `aws_security_group.node_group_sg` | `CreateSecurityGroup` | 빈 보안그룹 생성 (ID 발급) |
| 2 | `aws_security_group_rule.allow_ssh` | `AuthorizeSecurityGroupIngress` | 1에서 만든 보안그룹에 인바운드 규칙 부착 |

Terraform의 리소스 간 참조 추적 기능이 동작하는 방식은 다음과 같다.

1. `aws_security_group.node_group_sg`를 먼저 생성
2. AWS가 해당 리소스의 `id`를 반환 (예: `sg-0a6afe6fd37744d7f`)
3. Terraform이 그 값을 **state에 저장**하고, `aws_security_group.node_group_sg.id`로 참조하는 다른 리소스에 주입

이 참조를 통해 Terraform은 보안그룹 생성 → 규칙 생성 순서를 자동으로 보장한다.

<br>

## EKS 모듈

```hcl
module "eks" {
  
  source  = "terraform-aws-modules/eks/aws"
  version = "~> 21.0"

  name               = var.ClusterBaseName
  kubernetes_version = var.KubernetesVersion

  vpc_id = module.vpc.vpc_id
  subnet_ids = module.vpc.public_subnets

  endpoint_public_access = true
  endpoint_private_access = false

  enabled_log_types = []

  enable_cluster_creator_admin_permissions = true

  eks_managed_node_groups = {
    default = {
      name             = "${var.ClusterBaseName}-node-group"
      use_name_prefix  = false
      instance_types   = ["${var.WorkerNodeInstanceType}"]
      desired_size     = var.WorkerNodeCount
      max_size         = var.WorkerNodeCount + 2
      min_size         = var.WorkerNodeCount - 1
      disk_size        = var.WorkerNodeVolumesize
      subnets          = module.vpc.public_subnets
      key_name         = "${var.KeyName}"
      vpc_security_group_ids = [aws_security_group.node_group_sg.id]

      cloudinit_pre_nodeadm = [
        {
          content_type = "text/x-shellscript"
          content      = <<-EOT
            #!/bin/bash
            echo "Starting custom initialization..."
            dnf update -y
            dnf install -y tree bind-utils
            echo "Custom initialization completed."
          EOT
        }
      ]
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
      most_recent = true
      before_compute = true
    }
  }

  tags = {
    Environment = "cloudneta-lab"
    Terraform   = "true"
  }

}
```

<br>

### 클러스터 기본 설정

| 설정 | 값 | 설명 |
| --- | --- | --- |
| `source` | `terraform-aws-modules/eks/aws` | [EKS 모듈](https://registry.terraform.io/modules/terraform-aws-modules/eks/aws/latest) 사용 |
| `version` | `~> 21.0` | 21.0 이상 22.0 미만 |
| `name` | `myeks` | 클러스터 이름 |
| `kubernetes_version` | `1.34` | K8s 버전 |

<br>

### VPC 연결

```hcl
vpc_id = module.vpc.vpc_id
subnet_ids = module.vpc.public_subnets
```

`vpc.tf`에서 만든 VPC와 서브넷을 참조한다. 여기서 `module.vpc.public_subnets`가 반환하는 값에 대해 짚고 넘어가자.

`subnet_ids`에는 서브넷 ID가 들어간다. VPC 모듈의 `outputs.tf`를 보면 이름이 비슷한 항목들이 있다.

```hcl
# .terraform/modules/vpc/outputs.tf
...

output "public_subnet_objects" {
  description = "A list of all public subnets, containing the full objects."
  value       = aws_subnet.public
}

output "public_subnets" {
  description = "List of IDs of public subnets"
  value       = aws_subnet.public[*].id
}

output "public_subnet_arns" {
  description = "List of ARNs of public subnets"
  value       = aws_subnet.public[*].arn
}

...
```

- `public_subnet_objects`는 서브넷 **오브젝트 전체**를 반환(모든 속성 포함)
- `public_subnets`는 서브넷 **ID 리스트만** 반환(`aws_subnet.public[*].id`)
- `public_subnet_arns`는 서브넷 **ARN 리스트**를 반환

여기서 `module.vpc.public_subnets`는 두 번째 output을 참조해서 `["subnet-0abc123...", "subnet-0def456...", "subnet-0ghi789..."]` 같은 **ID 리스트**를 받아오는 것이다.

코드를 처음 읽을 때 `vpc.tf`의 `public_subnets = var.public_subnet_blocks`(모듈 **input**)와 `module.vpc.public_subnets`(모듈 **output**)가 헷갈릴 수 있다. 이름은 같지만 역할이 완전히 다르다.

실제로 IDE에서 `public_subnets`를 검색하면 두 군데에서 나온다.

![vpc-module-input]({{site.url}}/assets/images/eks-terraform-vpc-module-input.png){: .align-center width="500"}

<center><sup>VPC 모듈 input으로 <code>public_subnets</code>가 정의되어 있음</sup></center>

![vpc-module-output]({{site.url}}/assets/images/eks-terraform-vpc-module-output.png){: .align-center width="500"}

<center><sup>VPC 모듈 <code>outputs.tf</code>에 <code>public_subnets</code>라는 output이 정의되어 있음</sup></center>

처음에는 둘이 같은 건 줄 알았다. "`module.vpc.public_subnets`가 결국 `var.public_subnet_blocks`를 가리키는 거 아닌가?" 싶었는데, 전혀 다른 것이었다.

| | input (모듈에 넣는 값) | output (모듈이 내보내는 값) |
| --- | --- | --- |
| **위치** | `module "vpc" { }` 블록 안 | 모듈 내부 `outputs.tf` |
| **타입** | CIDR 문자열 리스트 | 서브넷 ID 리스트 |
| **예시** | `["192.168.1.0/24", ...]` | `["subnet-0abc123...", ...]` |
| **참조 방식** | `var.public_subnet_blocks`를 넘김 | `module.vpc.public_subnets`로 꺼내 씀 |

흐름으로 보면 다음과 같다.

1. `var.public_subnet_blocks` (CIDR 리스트) → 모듈 input `public_subnets`로 전달
2. 모듈 내부에서 `aws_subnet.public` 리소스 생성
3. 생성된 서브넷의 ID를 모듈 output `public_subnets`로 내보냄
4. `eks.tf`에서 `module.vpc.public_subnets`로 ID 리스트를 가져다 씀

**input은 모듈 블록 안에서 `=`로 할당하는 것**이고, **output은 `module.모듈이름.output이름`으로 꺼내 쓰는 것**이다.

<br>

### API 서버 엔드포인트 접근

```hcl
endpoint_public_access = true
endpoint_private_access = false
```

이 조합은 **Public-Public 구성**이다.

| 설정 | 의미 |
| --- | --- |
| `endpoint_public_access = true` | EKS API 서버 엔드포인트를 인터넷에서 접근 가능. `kubectl` 명령이 인터넷을 통해 API 서버에 도달 |
| `endpoint_private_access = false` | VPC 내부(프라이빗)에서의 API 서버 접근 비활성화 |

이 구성에서는 워커 노드도 API 서버에 접근할 때 **퍼블릭 인터넷을 경유**한다. VPC 내부에서 프라이빗 DNS로 API 서버에 접근하는 경로가 없다.

<br>

### Control Plane 로그

```hcl
enabled_log_types = []
```

Control Plane 로그를 CloudWatch로 보내지 않는 설정이다. 

EKS Control Plane 로그 타입은 아래와 같이 5가지가 있다. 

| 로그 타입 | 내용 |
| --- | --- |
| `api` | kube-apiserver 요청/응답 로그 |
| `audit` | K8s 감사 로그 (누가 뭘 했는지) |
| `authenticator` | IAM 인증 관련 로그 |
| `controllerManager` | 컨트롤러 매니저 로그 |
| `scheduler` | 스케줄러 로그 |


프로덕션에서는 최소 `["api", "audit"]` 정도는 켜두고, 비용이 괜찮다면 아래와 같이 전부 켜두는 것이 좋다. 

```hcl
enabled_log_types = ["api", "audit", "authenticator", "controllerManager", "scheduler"]
```

꼭 필요하지 않은 지금과 같은 실습 환경에서는 비용 절감을 위해 비활성화하는 것이 좋다. 로그는 CloudWatch Logs의 `/aws/eks/<클러스터이름>/cluster` 로그 그룹에 저장된다.


<br>

### 클러스터 생성자 권한

```hcl
enable_cluster_creator_admin_permissions = true
```

`terraform apply`를 실행하는 IAM 사용자를 **EKS 클러스터 관리자로 자동 등록**하는 설정이다. [Provider 섹션](#provider)에서 살펴본 것처럼, `~/.aws/credentials`에서 읽어 온 IAM 사용자가 `terraform apply`의 caller identity가 되고, 이 설정에 의해 해당 IAM 사용자가 EKS Access Entry에 `AmazonEKSClusterAdminPolicy` 권한으로 등록된다.

이 설정이 없으면 클러스터를 만들고도 `kubectl`로 접근 권한이 없는 상황이 발생할 수 있다. EKS는 기본적으로 아무에게도 K8s RBAC 권한을 주지 않으므로, 클러스터를 만든 IAM 사용자라도 Access Entry에 등록되지 않으면 `kubectl get pods`에 `Unauthorized`가 반환된다.

<br>

### Managed Node Group

```hcl
eks_managed_node_groups = {
  default = {
    ...
  }
}
```

**[관리형 노드 그룹]({% post_url 2026-03-12-Kubernetes-EKS-00-01-EKS-Computing-Group %}#관리형-노드-그룹)(Managed Node Group)**을 사용한다. AWS가 노드의 프로비저닝과 라이프사이클(업데이트, 패치, 교체)을 관리해주는 방식이다. 자체 관리형(self-managed)과 비교했을 때 다음과 같은 장점이 있다.

- 노드 AMI(Amazon Machine Image — OS, 런타임 등이 패키징된 머신 이미지) 업데이트를 AWS 콘솔/API로 간편하게 수행
- 노드 헬스 체크와 자동 교체
- EKS 콘솔에서 노드 그룹 상태 확인 가능

> **참고**: 다른 노드 그룹 유형을 사용하고 싶다면, EKS 모듈 안에 해당 키만 추가하면 된다.
>
> ```hcl
> module "eks" {
>   ...
>   eks_managed_node_groups = { ... }   # 관리형 (이 실습)
>   self_managed_node_groups = { ... }  # 자체 관리형
>   fargate_profiles = { ... }          # Fargate (서버리스)
> }
> ```
>
> 실제로 `terraform init`에서 다른 하위 모듈이 다운로드된 것을 확인할 수 있다.
>
> ```
> - eks.eks_managed_node_group   ← 관리형 노드 그룹
> - eks.self_managed_node_group  ← 자체 관리형 노드 그룹
> - eks.fargate_profile          ← Fargate
> ```

주요 설정을 하나씩 살펴보자.

| 설정 | 값 | 설명 |
| --- | --- | --- |
| `name` | `myeks-node-group` | 노드 그룹 이름 |
| `use_name_prefix` | `false` | 이름에 랜덤 접미사를 붙이지 않음. `true`면 `myeks-node-group-abc123` 같이 되고, `false`면 정확히 `myeks-node-group` |
| `instance_types` | `["t3.medium"]` | 인스턴스 타입 |
| `desired_size` | `2` | 실제 노드 수 |
| `max_size` | `4` (`WorkerNodeCount + 2`) | 오토스케일링 최대 수 |
| `min_size` | `1` (`WorkerNodeCount - 1`) | 오토스케일링 최소 수 |
| `disk_size` | `30` | 노드 디스크 크기 (GiB) |
| `key_name` | *(배포 시 주입)* | SSH 접속용 EC2 키 페어 |
| `vpc_security_group_ids` | `[...node_group_sg.id]` | 앞서 생성한 보안그룹 연결 |

`instance_types`는 현재 `t3.medium` 한 가지 타입이지만, 여러 인스턴스 타입을 지정하면 AWS가 **가용성과 비용을 고려해서 자동으로 선택**한다. 특히 [스팟 인스턴스]({% post_url 2026-03-12-Kubernetes-EKS-00-01-EKS-Computing-Group %}#스팟) 사용 시 유용한데, 하나의 타입이 부족하면 다른 타입으로 대체 배치할 수 있다.

오토스케일링 설정(`desired_size`, `min_size`, `max_size`)에 대해서는, `desired_size`가 실제 노드 수이고 min/max 범위 안에서 **Cluster Autoscaler**나 **Karpenter** 같은 별도 오토스케일러를 설치해야 실제로 자동 조절된다. 기본적으로는 `desired_size`로 고정된다.

`vpc_security_group_ids = [aws_security_group.node_group_sg.id]`는 보안그룹에서 본 것과 동일한 의존성 참조 원리다. `aws_security_group.node_group_sg.id`를 참조하면 Terraform이 보안그룹 생성 → 노드 그룹 생성 순서를 보장한다.

#### 커스텀 초기화 스크립트

```hcl
cloudinit_pre_nodeadm = [
  {
    content_type = "text/x-shellscript"
    content      = <<-EOT
      #!/bin/bash
      echo "Starting custom initialization..."
      dnf update -y
      dnf install -y tree bind-utils
      echo "Custom initialization completed."
    EOT
  }
]
```

AL2023(Amazon Linux 2023, AWS가 만든 리눅스 배포판으로 EKS 노드의 기본 OS) 전용 userdata 주입이다. userdata는 EC2 인스턴스가 **최초 부팅 시 실행하는 스크립트**다.

`content_type = "text/x-shellscript"`는 **cloud-init**에서 정의한 MIME 타입이다. cloud-init은 EC2 인스턴스 초기화의 표준으로, 이 타입을 보고 해당 콘텐츠를 쉘 스크립트로 실행해야 한다는 것을 인식한다.

`content` 블록에서는 `dnf update -y`로 패키지를 업데이트하고, `tree`(디렉토리 구조 확인 도구)와 `bind-utils`(DNS 디버깅 도구, `dig`, `nslookup` 등 포함)를 설치한다. 디버깅 및 실습 편의를 위한 설정이다.

<br>

### EKS 애드온

```hcl
addons = {
  coredns = {
    most_recent = true
  }
  kube-proxy = {
    most_recent = true
  }
  vpc-cni = {
    most_recent = true
    before_compute = true
  }
}
```

| 애드온 | 역할 | 비고 |
| --- | --- | --- |
| **CoreDNS** | 클러스터 내부 DNS | |
| **kube-proxy** | 서비스 네트워크 규칙 관리 | |
| **VPC CNI** | Pod에 VPC 서브넷의 실제 IP 할당 | `before_compute = true`로 노드보다 먼저 설치 |

VPC CNI에 주목할 필요가 있다. **Amazon VPC CNI Plugin**은 Pod에 **VPC 서브넷의 실제 IP 주소를 직접 할당**하는 네트워크 플러그인이다.

일반적인 K8s의 [오버레이 네트워크]({% post_url 2026-03-19-Kubernetes-Networking-03-CNI-Flow %})(Calico, Flannel 등)는 호스트 네트워크 위에 **가상 네트워크 계층을 한 겹 더 씌워서** Pod 간 통신을 한다. 반면 VPC CNI는 오버레이를 쓰지 않고 Pod에 **VPC 서브넷의 실제 IP를 직접 할당**한다. Pod IP가 VPC 라우팅 테이블에 바로 보이고, 다른 EC2 인스턴스나 RDS 같은 AWS 서비스에서 Pod IP로 직접 통신할 수 있다. 추가 터널링 없이 네이티브 VPC 네트워킹을 사용하니 성능도 좋고 구조도 단순하다.

| | 오버레이 네트워크 (Calico, Flannel 등) | VPC CNI |
| --- | --- | --- |
| **구조** | 호스트 네트워크 위에 가상 네트워크 계층 추가 | VPC 네이티브 (오버레이 없음) |
| **Pod IP** | 가상 네트워크 대역 | VPC 서브넷의 실제 IP |
| **VPC 라우팅 테이블** | Pod IP가 보이지 않음 | Pod IP가 직접 보임 |
| **AWS 서비스 통신** | NAT/프록시 필요 | 직접 통신 가능 |
| **성능** | 터널링 오버헤드 | 네이티브 VPC 네트워킹 |

`before_compute = true`는 VPC CNI 애드온을 **워커 노드(compute)보다 먼저 설치**하겠다는 뜻이다. 노드가 뜨기 전에 CNI가 준비되어 있어야 Pod 네트워킹이 정상 동작하기 때문이다.

<br>

# 결론

실습 코드의 Terraform 파일 세 개를 분석했다.

| 파일 | 핵심 역할 | 주요 설정 |
| --- | --- | --- |
| `var.tf` | 변수 선언 | 클러스터 이름, 리전, 인스턴스 타입, CIDR 등 |
| `vpc.tf` | 네트워크 구성 | VPC, 퍼블릭 서브넷 3개, IGW, DNS, ELB 태그 |
| `eks.tf` | 클러스터 구성 | Provider, 보안그룹, EKS 모듈, 관리형 노드그룹, 애드온 |

코드의 의존성 흐름은 다음과 같다.

```
var.tf (변수 정의)
  ↓
vpc.tf (VPC, 서브넷 생성)
  ↓ module.vpc.vpc_id, module.vpc.public_subnets
eks.tf (보안그룹 → EKS 클러스터 → 노드그룹)
```

`var.tf`의 변수가 `vpc.tf`와 `eks.tf`에서 참조되고, `vpc.tf`의 output(VPC ID, 서브넷 ID)이 `eks.tf`에서 참조되는 구조다. Terraform은 이 참조를 기반으로 의존성 그래프를 만들어 생성 순서를 자동으로 결정한다.

<br>
