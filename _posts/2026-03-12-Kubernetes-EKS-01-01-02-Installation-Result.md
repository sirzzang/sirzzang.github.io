---
title:  "[EKS] EKS: Public-Public EKS 클러스터 - 2. 배포"
excerpt: "Terraform init/plan/apply를 실행하고, Public-Public 구성의 EKS 클러스터 배포 결과를 확인하자."
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

plan 결과를 보면, 직접 선언하지 않은 리소스가 하나 눈에 띈다.

```
# module.eks.module.kms.aws_kms_key.this[0] will be created
+ resource "aws_kms_key" "this" {
    + description        = "myeks cluster encryption key"
    + enable_key_rotation = true
    + key_usage          = "ENCRYPT_DECRYPT"
  }
```

코드에 KMS 설정을 명시하지 않았는데도 EKS 모듈이 `eks.kms` 하위 모듈을 통해 **KMS 키를 자동 생성**한 것으로, 모듈이 내부적으로 뭘 해주는지 의식해야 하는 좋은 사례다.

**KMS**(Key Management Service)는 AWS에서 제공하는 암호화 키 관리 서비스로, 키 생성·보관·교체를 맡는다. 이 KMS 키가 하는 일이 바로 **Encryption at Rest**(저장 시 암호화)다. EKS 클러스터는 etcd에 Secret(비밀번호, 토큰 등)을 저장하는데, 이를 평문이 아닌 암호화된 상태로 디스크에 보관하는 것이다. 누군가 etcd의 데이터 파일에 직접 접근하더라도 암호화 키 없이는 내용을 읽을 수 없다.

> **참고**: Encryption at Rest는 "저장된 데이터"를 암호화하는 것이고, Encryption in Transit는 "전송 중인 데이터"를 암호화하는 것이다(TLS/SSL 등). 여기서 KMS가 담당하는 것은 etcd에 저장된 Secret의 encryption at rest다.

사용된 각 속성의 의미는 다음과 같다.

- `key_usage = "ENCRYPT_DECRYPT"`: 데이터 암호화/복호화 용도
- `enable_key_rotation = true`: 보안을 위해 키를 주기적으로 자동 교체
- `description = "myeks cluster encryption key"`: EKS 클러스터 암호화 전용 키

[Kubernetes Hard Way - Data Encryption Config and Key]({% post_url 2026-01-05-Kubernetes-Cluster-The-Hard-Way-06 %})에서 이 encryption at rest를 직접 구성한 적이 있다. 그때는 `/dev/urandom`으로 암호화 키를 생성하고, `EncryptionConfiguration`을 작성해 kube-apiserver의 `--encryption-provider-config` 플래그로 전달했다. EKS에서는 이 과정을 EKS 모듈이 KMS를 통해 자동으로 처리해 준다.


<br>

### KMS 키 정책

KMS 키와 함께 생성되는 **키 정책(Key Policy)**의 plan 결과도 눈여겨볼 만하다.

```
# module.eks.module.kms.data.aws_iam_policy_document.this[0] will be read during apply
<= data "aws_iam_policy_document" "this" {
    + statement {
        + actions   = ["kms:*"]
        + resources = ["*"]
        + sid       = "Default"
        + principals {
            + identifiers = ["arn:aws:iam::988608581192:root"]
            + type        = "AWS"
          }
      }
    + statement {
        + actions   = ["kms:CancelKeyDeletion", "kms:Create*", "kms:Delete*", ...]
        + resources = ["*"]
        + sid       = "KeyAdministration"
        + principals {
            + identifiers = ["arn:aws:iam::988608581192:user/admin"]
            + type        = "AWS"
          }
      }
    + statement {
        + actions   = ["kms:Decrypt", "kms:DescribeKey", "kms:Encrypt", ...]
        + resources = ["*"]
        + sid       = "KeyUsage"
        + principals {
            + identifiers = [(known after apply)]
            + type        = "AWS"
          }
      }
  }
```

`KeyAdministration`의 principal이 `arn:aws:iam::988608581192:user/admin`으로 되어 있다. 이것이 바로 `~/.aws/credentials`에서 읽어 온 IAM 사용자이며, [코드 분석의 Provider 섹션]({% post_url 2026-03-12-Kubernetes-EKS-01-01-01-Installation %}#provider)에서 설명한 자격증명 자동 탐색의 결과다. `KeyUsage`의 principal이 `(known after apply)`인 이유는 EKS 클러스터의 IAM Role ARN이 아직 생성 전이라 plan 시점에는 알 수 없기 때문이다.

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

52개 리소스가 모두 생성되었다. 콘솔에서 생성 결과를 확인할 수 있다.

콘솔에서 Terraform 설정이 어떻게 반영되었는지 확인해 보자.

### VPC

![myeks-vpc-console-result]({{site.url}}/assets/images/myeks-vpc-console-result.png){: .align-center width="600"}

<center><sup>VPC 콘솔에서 <code>myeks-VPC</code>가 <code>192.168.0.0/16</code> CIDR로 생성된 것을 확인할 수 있다</sup></center>

`vpc.tf`에서 `name = "${var.ClusterBaseName}-VPC"`, `cidr = var.VpcBlock`으로 설정한 값이 그대로 반영되었다.

<br>

### VPC 리소스 맵

![myeks-vpc-console-result-2]({{site.url}}/assets/images/myeks-vpc-console-result-2.png){: .align-center width="600"}

<center><sup><code>myeks-VPC</code>의 리소스 맵</sup></center>

VPC 모듈이 자동으로 만들어준 리소스들의 전체 구조를 한눈에 볼 수 있다. AZ별 퍼블릭 서브넷 3개(`ap-northeast-2a`, `2b`, `2c`), 라우팅 테이블 2개(`myeks-VPC-public`, `myeks-VPC-default`), 네트워크 연결 1개(`myeks-IGW`)가 생성되었다. [코드 분석]({% post_url 2026-03-12-Kubernetes-EKS-01-01-01-Installation %}#vpc-모듈이-자동으로-해주는-것)에서 "모듈 한 블록으로 최소 7~10개 resource 블록을 대체한다"고 했는데, 그 결과물이다.

<br>

### 퍼블릭 서브넷

![myeks-public-subnet-console-result]({{site.url}}/assets/images/myeks-public-subnet-console-result.png){: .align-center width="600"}

<center><sup>퍼블릭 서브넷 3개가 AZ별로 생성됨</sup></center>

`var.tf`에서 선언한 `public_subnet_blocks`(`192.168.1.0/24`, `192.168.2.0/24`, `192.168.3.0/24`)가 그대로 반영되었다. 세 서브넷 모두 동일한 VPC(`vpc-0bbe44f398f6f...`)에 속해 있고, 이름도 `myeks-PublicSubnet`으로 통일되어 있다.

<br>

### 라우팅 테이블

![myeks-vpc-routingtable-console-result]({{site.url}}/assets/images/myeks-vpc-routingtable-console-result.png){: .align-center width="600"}

<center><sup><code>myeks-VPC-public</code> 라우팅 테이블의 라우팅 규칙</sup></center>

`myeks-VPC-public` 라우팅 테이블에 3개 서브넷이 연결되어 있고, 라우팅 규칙은 두 개다.

| 대상 | 대상(Target) | 의미 |
| --- | --- | --- |
| `0.0.0.0/0` | `igw-03d522d4af99...` (myeks-IGW) | 모든 외부 트래픽은 IGW로 |
| `192.168.0.0/16` | `local` | VPC 내부 통신은 로컬 라우팅 |

[코드 분석]({% post_url 2026-03-12-Kubernetes-EKS-01-01-01-Installation %}#vpc-모듈이-자동으로-해주는-것)에서 설명한 대로, VPC 모듈이 `public_subnets`를 지정하면 자동으로 IGW 생성과 `0.0.0.0/0 → IGW` 경로 추가를 처리해 준 것이다. Longest Prefix Match에 의해 VPC 내부 통신(`192.168.0.0/16`)은 로컬 경로로 먼저 매칭되고, 그 외 나머지 모든 트래픽(`0.0.0.0/0`)이 IGW로 빠지는 구조다.

<br>

### EKS 클러스터

![myeks-endpoint-access-public-console-result]({{site.url}}/assets/images/myeks-endpoint-access-public-console-result.png){: .align-center width="600"}

<center><sup>EKS 콘솔에서 <code>myeks</code> 클러스터의 네트워킹 정보</sup></center>

EKS 콘솔의 네트워킹 탭에서 Terraform 설정이 반영된 결과를 확인할 수 있다.

| 항목 | 콘솔 표시값 | Terraform 설정 |
| --- | --- | --- |
| **Kubernetes 버전** | 1.34 | `kubernetes_version = var.KubernetesVersion` |
| **VPC** | `vpc-0bbe44f398f6fc948` | `vpc_id = module.vpc.vpc_id` |
| **서브넷** | 3개 (`subnet-09ff...`, `subnet-0e89...`, `subnet-04b0...`) | `subnet_ids = module.vpc.public_subnets` |
| **API 서버 엔드포인트 액세스** | 퍼블릭 | `endpoint_public_access = true`, `endpoint_private_access = false` |
| **퍼블릭 액세스 소스 허용 목록** | `0.0.0.0/0` (모든 트래픽에 개방) | `endpoint_public_access_cidrs` 미설정 (기본값) |
| **서비스 IPv4 범위** | `10.100.0.0/16` | EKS가 자동 할당한 Service CIDR |

API 서버 엔드포인트 액세스가 **퍼블릭**이고, 퍼블릭 액세스 소스 허용 목록이 `0.0.0.0/0`으로 모든 트래픽에 개방되어 있다. [Public-Public 구성의 한계](#이-구성의-한계)에서 지적한 보안 이슈가 여기서 확인된다.

<br>

### 컨트롤 플레인 로그

![myeks-cluster-observability-console-result]({{site.url}}/assets/images/myeks-cluster-observability-console-result.png){: .align-center width="600"}

<center><sup>EKS 콘솔 관찰성 탭에서 컨트롤 플레인 로그 설정 확인</sup></center>

관찰성 탭의 컨트롤 플레인 로그 섹션에서 5가지 로그 타입(API 서버, 감사, Authenticator, 컨트롤러 관리자, 스케줄러)이 모두 **off**인 것을 확인할 수 있다. [코드 분석]({% post_url 2026-03-12-Kubernetes-EKS-01-01-01-Installation %}#control-plane-로그)에서 살펴본 `enabled_log_types = []` 설정이 그대로 반영된 결과다. 실습 환경에서의 비용 절감을 위해 비활성화한 것이고, 프로덕션에서는 최소 `api`, `audit` 정도는 켜두는 것이 좋다.

<br>

### IAM 액세스 항목

![mycluster-admin-access-console-result]({{site.url}}/assets/images/mycluster-admin-access-console-result.png){: .align-center width="600"}

<center><sup>EKS 콘솔 액세스 탭에서 IAM 액세스 항목 확인</sup></center>

액세스 탭에서 클러스터에 등록된 IAM 액세스 항목 3개를 확인할 수 있다.

| IAM 보안 주체 ARN | 유형 | 사용자 이름 | 액세스 정책 |
| --- | --- | --- | --- |
| `arn:aws:iam::...:role/AWSServiceRoleForAmazonEKS` | 표준 | `eks:managed` | AmazonEKSClusterInsightsPolicy, AmazonEKSEventPolicy |
| `arn:aws:iam::...:role/myeks-node-group-eks-node-group-...` | EC2 Linux | `system:node:{% raw %}{{EC2PrivateDNSName}}{% endraw %}` | system:nodes 그룹 |
| **`arn:aws:iam::...:user/admin`** | 표준 | `arn:aws:iam::988608581192:user/admin` | **AmazonEKSClusterAdminPolicy** |

세 번째 항목이 핵심이다. [코드 분석]({% post_url 2026-03-12-Kubernetes-EKS-01-01-01-Installation %}#클러스터-생성자-권한)에서 살펴본 `enable_cluster_creator_admin_permissions = true` 설정에 의해, `terraform apply`를 실행한 IAM User `admin`이 **AmazonEKSClusterAdminPolicy** 권한으로 EKS Access Entry에 자동 등록된 것이다. 이 설정이 없었다면 클러스터를 만들고도 `kubectl`로 접근할 수 없는 상황이 발생했을 것이다.

<br>

### 관리형 노드 그룹 (Auto Scaling 그룹)

![myeks-node-autoscaling-group-console-result]({{site.url}}/assets/images/myeks-node-autoscaling-group-console-result.png){: .align-center width="600"}

<center><sup>EC2 콘솔의 Auto Scaling 그룹에서 관리형 노드 그룹 확인</sup></center>

EKS 관리형 노드 그룹은 내부적으로 **[EC2 Auto Scaling 그룹]({% post_url 2026-03-12-Kubernetes-EKS-00-01-EKS-Computing-Group %}#asg-기반-프로비저닝)**으로 관리된다. EC2 콘솔의 Auto Scaling 그룹 페이지에서 확인할 수 있다.

| 항목 | 콘솔 표시값 | Terraform 설정 |
| --- | --- | --- |
| **원하는 용량** | 2 | `desired_size = var.WorkerNodeCount` (기본값 2) |
| **크기 조정 한도** | 1 - 4 | `min_size = var.WorkerNodeCount - 1`, `max_size = var.WorkerNodeCount + 2` |
| **원하는 용량 유형** | 단위(인스턴스 개수) | ON_DEMAND (plan에서 확인) |
| **인스턴스** | 2 | `desired_size`와 일치 |
| **소유자** | `AWSServiceRoleForAmazonEKSNodegroup/EKS` | AWS가 관리형 노드 그룹을 위해 생성한 서비스 연결 역할 |

[코드 분석]({% post_url 2026-03-12-Kubernetes-EKS-01-01-01-Installation %}#managed-node-group)에서 확인한 대로, `desired_size`, `min_size`, `max_size` 설정이 Auto Scaling 그룹의 용량 설정으로 그대로 반영되었다. 다만 실제 자동 조절이 동작하려면 [Cluster Autoscaler나 Karpenter]({% post_url 2026-03-12-Kubernetes-EKS-00-01-EKS-Computing-Group %}#참고-asg와-노드-오토스케일링) 같은 별도 오토스케일러를 설치해야 하고, 기본적으로는 `desired_size`인 2대로 고정된다.

실제로 EC2 인스턴스 목록에서도 2대가 실행 중인 것을 확인할 수 있다.

![myeks-ec2-instance-running-console-result]({{site.url}}/assets/images/myeks-ec2-instance-running-console-result.png){: .align-center width="600"}

<center><sup>EC2 콘솔에서 워커 노드 인스턴스 2대가 실행 중</sup></center>

| 항목 | 인스턴스 1 | 인스턴스 2 |
| --- | --- | --- |
| **Name** | myeks-node-g... | myeks-node-g... |
| **인스턴스 유형** | t3.medium | t3.medium |
| **가용 영역** | ap-northeast-2b | ap-northeast-2c |
| **퍼블릭 IPv4 DNS** | ec2-16-184-33-1... | ec2-13-209-87-1... |

두 인스턴스가 서로 다른 AZ(`2b`, `2c`)에 분산 배치되어 있고, 인스턴스 유형은 `var.WorkerNodeInstanceType`의 기본값인 `t3.medium`이다. `map_public_ip_on_launch = true` 설정 덕분에 퍼블릭 IP(DNS)가 자동으로 할당된 것도 확인할 수 있다.

<br>

### 시작 템플릿 (Launch Template)

EKS 콘솔의 노드 그룹 상세 페이지에서 **Auto Scaling 그룹 이름** 링크를 통해 ASG → 시작 템플릿까지 따라갈 수 있다.

![myeks-nodegroup-asg-link-console]({{site.url}}/assets/images/myeks-nodegroup-asg-link-console.png){: .align-center width="600"}

<center><sup>노드 그룹 상세 — Auto Scaling 그룹 이름 링크</sup></center>

ASG 상세 페이지 하단의 **시작 템플릿** 섹션에서 템플릿 ID, AMI ID, 보안 그룹 ID 등을 확인할 수 있다.

![myeks-asg-launch-template-console]({{site.url}}/assets/images/myeks-asg-launch-template-console.png){: .align-center width="600"}

<center><sup>Auto Scaling 그룹 상세 — 시작 템플릿 정보</sup></center>

시작 템플릿의 **고급 세부 정보 → 사용자 데이터**에서는 노드 부팅 시 실행되는 userdata를 확인할 수 있다. [코드 분석]({% post_url 2026-03-12-Kubernetes-EKS-01-01-01-Installation %}#userdata)에서 살펴본 `NodeConfig`(API 서버 엔드포인트, CA 인증서, kubelet 설정)와 커스텀 초기화 스크립트(`dnf update`, `bind-utils` 설치)가 들어있다.

![myeks-launch-template-userdata-console]({{site.url}}/assets/images/myeks-launch-template-userdata-console.png){: .align-center width="600"}

<center><sup>시작 템플릿 사용자 데이터 — NodeConfig와 커스텀 초기화 스크립트</sup></center>

시작 템플릿을 수정하려면 **"템플릿 수정(새 버전 생성)"**을 해야 한다. 기존 버전을 직접 수정하는 것이 아니라 새 버전을 만드는 구조다.

![myeks-launch-template-version-console]({{site.url}}/assets/images/myeks-launch-template-version-console.png){: .align-center width="600"}

<center><sup>시작 템플릿 수정 시 새 버전 생성이 필요</sup></center>

이는 [Launch Template의 동작 원리]({% post_url 2026-03-12-Kubernetes-EKS-00-01-EKS-Computing-Group %}#launch-template)에서 다룬 것처럼, 템플릿은 "앞으로 새로 만들 인스턴스의 스펙 정의서"이기 때문이다. 새 버전을 만든 후 노드 그룹 업데이트를 하면 EKS가 rolling update로 노드를 교체한다. 또한 EKS가 자동 생성한 시작 템플릿을 콘솔에서 직접 수정하면 EKS 관리 로직과 충돌할 수 있으므로 주의해야 한다.

<br>

### 보안그룹

인스턴스 하나를 선택해서 보안 탭을 보면, 보안그룹이 두 개 연결되어 있다.

![myeks-ec2-security-group-console-result-1]({{site.url}}/assets/images/myeks-ec2-security-group-console-result-1.png){: .align-center width="600"}

<center><sup>워커 노드 인스턴스의 보안 탭 — 두 개의 보안그룹이 연결됨</sup></center>

| 보안그룹 | 설명 |
| --- | --- |
| `myeks-node-...` (EKS 모듈이 자동 생성) | EKS 관리형 노드 그룹의 기본 보안그룹. 컨트롤 플레인과의 통신(9443, 6443 등)을 허용 |
| **`myeks-node-group-sg`** (Terraform에서 직접 정의) | `eks.tf`의 `aws_security_group.node_group_sg`. `vpc_security_group_ids`로 연결한 것 |

`myeks-node-group-sg`의 인바운드 규칙을 확인해 보자.

![myeks-ec2-security-group-console-result-2]({{site.url}}/assets/images/myeks-ec2-security-group-console-result-2.png){: .align-center width="600"}

<center><sup><code>myeks-node-group-sg</code> 보안그룹의 인바운드 규칙</sup></center>

인바운드 규칙 2개가 [코드 분석]({% post_url 2026-03-12-Kubernetes-EKS-01-01-01-Installation %}#보안그룹-규칙)에서 살펴본 `aws_security_group_rule.allow_ssh`의 `cidr_blocks`와 정확히 일치한다.

| 유형 | 프로토콜 | 포트 범위 | 소스 | Terraform 설정 |
| --- | --- | --- | --- | --- |
| 모든 트래픽 | 전체 | 전체 | `192.168.1.100/32` | bastion host용 예비 허용 |
| 모든 트래픽 | 전체 | 전체 | `118.xxx.xxx.xxx/32` | `var.ssh_access_cidr` (내 공인 IP) |

`protocol = "-1"`(모든 프로토콜)로 설정했기 때문에 유형이 "모든 트래픽", 프로토콜과 포트 범위가 "전체"로 표시된다. 지정된 CIDR에서 오는 모든 트래픽을 허용하되, 접속 대상만 IP로 제한하는 구조다.

<br>

### EKS 애드온

![aws-myeks-cluster-addon-console-result]({{site.url}}/assets/images/aws-myeks-cluster-addon-console-result.png){: .align-center width="600"}

<center><sup>EKS 콘솔 추가 기능 탭에서 설치된 애드온 확인</sup></center>

[코드 분석]({% post_url 2026-03-12-Kubernetes-EKS-01-01-01-Installation %}#eks-애드온)에서 `addons` 블록에 선언한 3개 애드온이 모두 활성 상태로 설치되어 있다.

| 애드온 | 버전 | 카테고리 | Terraform 설정 |
| --- | --- | --- | --- |
| **Amazon VPC CNI** | v1.21.1-eksbuild.3 | networking | `most_recent = true`, `before_compute = true` |
| **CoreDNS** | v1.13.2-eksbuild.1 | networking | `most_recent = true` |
| **kube-proxy** | v1.34.3-eksbuild.5 | networking | `most_recent = true` |

세 애드온 모두 `most_recent = true` 설정에 의해 EKS 클러스터 버전(1.34)과 호환되는 최신 버전이 설치되었다. VPC CNI의 `before_compute = true` 설정 덕분에 [apply 로그](#리소스-생성-순서)에서 확인한 것처럼 노드그룹보다 먼저 설치되어 Pod 네트워킹이 정상 동작한다.

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

관련 주요 설정은 아래와 같았다.

```hcl
endpoint_public_access = true
endpoint_private_access = false
enable_nat_gateway = false
```

- `endpoint_public_access = true` → 인터넷에서 `kubectl` 접근 가능
- `enable_nat_gateway = false` → 프라이빗 서브넷을 안 쓰니 NAT Gateway 불필요. 비용 절감
- `ssh_access_cidr`로 IP 제한 → 워커 노드에 SSH 접속 가능


결과적으로, **모든 통신이 퍼블릭 인터넷을 경유**한다. API 서버 엔드포인트가 인터넷에서 접근 가능하고, 워커 노드도 퍼블릭 서브넷에 배치되어 인터넷을 통해 API 서버와 통신한다.

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

# 트러블슈팅: 실습 환경 공인 IP 변경

## 증상

실습 진행 환경(카페, 자취방 등)이 바뀌어 공인 IP가 달라진 경우, 워커 노드에 접근할 수 없다.

- 노드 공인 IP로 `ping` → **100% packet loss**
- `ssh ec2-user@$NODE1` → **접속 안 됨**
- `kubectl` 명령은 정상 동작 (API 서버는 `publicAccessCidrs: 0.0.0.0/0`이라 무관)

```bash
ping -c 1 $NODE1
PING xx.xxx.xxx.xxx (xx.xxx.xxx.xxx): 56 data bytes
--- xx.xxx.xxx.xxx ping statistics ---
1 packets transmitted, 0 packets received, 100.0% packet loss
```

## 원인

[위에서 확인한](#보안그룹) `myeks-node-group-sg` 보안그룹의 인바운드 규칙은 `protocol = "-1"`(모든 프로토콜)을 허용하지만, **소스 CIDR**이 `terraform apply` 시점의 공인 IP(`var.ssh_access_cidr`)와 `192.168.1.100/32`로 제한되어 있다.

실습 환경이 바뀌어 현재 PC의 공인 IP가 이 CIDR에 매칭되지 않으면, 보안 그룹에서 **모든 인바운드 트래픽이 차단**된다. ping(ICMP)도 SSH(TCP 22)도 마찬가지다.

`kubectl`은 영향을 받지 않는다. `kubectl`은 워커 노드가 아닌 **EKS API 서버**에 접속하고, API 서버의 `publicAccessCidrs`가 `0.0.0.0/0`이기 때문이다.

## 해결

환경변수를 갱신하고 `terraform apply`를 다시 실행한다.

```bash
export TF_VAR_ssh_access_cidr=$(curl -s ipinfo.io/ip)/32
terraform plan
terraform apply
```

`plan` 결과를 보면 보안그룹 규칙의 `cidr_blocks`만 변경된다. `cidr_blocks` 변경은 in-place 업데이트가 되지 않아 `forces replacement`(기존 규칙 삭제 → 새 규칙 생성)로 처리되지만, EKS 클러스터나 노드에는 영향이 없다.

```
-/+ resource "aws_security_group_rule" "allow_ssh" {
      ~ cidr_blocks = [             # forces replacement
          ~ "121.xxx.xxx.xxx/32" -> "새_IP/32",
            "192.168.1.100/32",
        ]
    }
```

> `terraform apply` 시 addon 버전 업데이트(`vpc-cni`, `coredns` 등)가 함께 잡힐 수 있다. `eks.tf`에서 `most_recent = true`로 설정했기 때문에, AWS 쪽에서 새 빌드 버전이 나오면 자동 감지된다. 이 역시 `update in-place`이므로 안전하게 적용할 수 있다.

AWS 콘솔에서 보안 그룹 인바운드 규칙을 직접 수정하는 방법도 있지만, Terraform 상태와 실제 상태가 불일치(drift)하게 되므로 `terraform apply`로 진행하는 것이 깔끔하다.

<br>

# 배포 시 기억할 점

## KMS 암호화 자동 설정

코드에 명시하지 않았는데도 EKS 모듈이 [KMS 키를 자동 생성](#kms-키-자동-생성)하여 etcd Secret의 encryption at rest를 적용한다. 모듈이 내부적으로 무엇을 해주는지 `plan` 단계에서 반드시 확인해야 한다.

## VPC CNI before_compute

`before_compute = true` 설정 하나가 빠지면 노드가 올라온 뒤에 CNI가 설치되어 **초기 Pod가 네트워킹 문제로 실패**할 수 있다. 사소해 보이지만 실무에서 트러블슈팅하기 까다로운 부분이다.

## AWS 자격증명 흐름

[코드 분석]({% post_url 2026-03-12-Kubernetes-EKS-01-01-01-Installation %}#provider)에서 살펴본 것처럼 코드에는 `access_key`나 `secret_key`가 없고, `~/.aws/credentials`의 IAM 사용자가 자동으로 사용된다. 이 IAM 사용자가 배포 전체 과정에서 어떻게 쓰이는지 정리하면 다음과 같다.

| 단계 | IAM 자격증명이 쓰이는 곳 |
| --- | --- |
| `terraform init` | Provider 플러그인 다운로드 (AWS API 불필요) |
| `terraform plan` | `data` 소스 읽기 위해 AWS API 호출 (caller identity 확인 등) |
| `terraform apply` | 모든 리소스 생성 시 AWS API 호출 (VPC, EKS, IAM Role 등) |
| `aws eks update-kubeconfig` | kubeconfig에 해당 IAM 사용자 기반 인증 설정 |
| `kubectl` | kubeconfig → `aws eks get-token` → IAM 사용자로 EKS API 인증 |

결국 `~/.aws/credentials`에 있는 IAM 사용자가 이 전체 과정의 신원(identity)이며, [클러스터 생성자 권한]({% post_url 2026-03-12-Kubernetes-EKS-01-01-01-Installation %}#클러스터-생성자-권한) 설정에 의해 EKS 관리자로 등록되는 주체이기도 하다. 위의 [KMS 키 정책 plan 결과](#kms-키-자동-생성)에서 `KeyAdministration` principal로 `user/admin`이 찍힌 것이 바로 이 IAM 사용자다.

코드에 자격증명이 안 보여서 마법처럼 느껴질 수 있지만, Ansible에서 SSH 키를 `~/.ssh/`에 두면 인벤토리나 플레이북에 명시하지 않아도 자동으로 쓰이는 것과 같은 원리다. 도구가 정해진 경로에서 자격증명을 자동 탐색하는 것이고, 그 자격증명의 주체가 전체 작업의 실행자가 된다.

## -auto-approve 주의

실습에서는 편의상 `-auto-approve`를 사용했지만, 프로덕션에서는 `plan` 결과를 직접 눈으로 확인한 뒤 `yes`를 입력하는 워크플로우가 안전하다.

<br>

# 결론

Terraform으로 EKS 클러스터를 배포했다. 전체 과정을 정리하면 다음과 같다.

| 단계 | 명령어 | 소요 시간 | 핵심 |
| --- | --- | --- | --- |
| **변수 주입** | `export TF_VAR_...` | - | `default` 없는 변수에 값 제공 |
| **초기화** | `terraform init` | ~19초 | 모듈 먼저 → Provider 나중 |
| **계획** | `terraform plan` | ~수초 | 52개 리소스 생성 예정 확인 |
| **적용** | `terraform apply` | ~12분 | EKS 클러스터 생성이 6분 42초로 가장 오래 걸림 |

현재 구성은 학습 목적의 Public-Public이다. 보안적으로 권장되지 않으므로, 다음 단계에서 Private 접근을 활성화하고 보안그룹을 강화한다.

<br>
