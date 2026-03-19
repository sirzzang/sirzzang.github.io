---
title:  "[EKS] EKS: EKS 배포 개요"
excerpt: "EKS 클러스터를 배포하기 위한 방법을 비교하고, 이번 실습에서 사용할 Terraform의 핵심 개념을 살펴보자."
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
  - eksctl
  - CloudFormation
  - AWS-EKS-Workshop-Study
  - AWS-EKS-Workshop-Study-Week-1

---

*[서종호(가시다)](https://www.linkedin.com/in/gasida99/)님의 AWS EKS Workshop Study(AEWS) 1주차 학습 내용을 기반으로 합니다.*

<br>

# TL;DR

이번 글에서는 **EKS 클러스터 배포 방법과 Terraform의 핵심 개념**을 다룬다.

- **EKS 배포 방식**: 웹 콘솔, eksctl, IaC(Terraform, CloudFormation 등) 세 가지
- **eksctl**: 내부적으로 CloudFormation 스택을 생성하여 리소스를 프로비저닝하는 CLI 도구
- **Terraform**: HCL로 인프라를 정의하고 `init` → `plan` → `apply`로 배포하는 IaC 도구
- **이번 실습에서는 Terraform을 주 배포 도구로 사용**

<br>

# EKS 배포 방식

EKS 클러스터를 배포하는 방법은 크게 세 가지다.

| 방식 | 도구 | 특징 |
| --- | --- | --- |
| **웹 관리 콘솔** | AWS Console | GUI로 직접 생성. 학습용으로 적합 |
| **CLI** | **eksctl** | EKS 전용 CLI 도구. 내부적으로 CloudFormation 사용 |
| **IaC** | **Terraform**, CloudFormation, CDK 등 | 인프라를 코드로 정의하고 관리 |

이번 실습에서는 **Terraform**을 사용한다.

<br>

# eksctl

## 개요

[eksctl](https://eksctl.io/)은 EKS 클러스터 구축 및 관리를 위한 오픈소스 명령줄 도구다. Weaveworks와 AWS가 [공동으로 유지 관리](https://aws.amazon.com/ko/blogs/opensource/weaveworks-and-aws-joining-forces-to-maintain-open-source-eksctl/)하고 있다.

eksctl의 핵심 특징은 **내부적으로 AWS CloudFormation을 사용**한다는 점이다. eksctl이 직접 EC2나 EKS API를 호출해서 리소스를 하나하나 만드는 것이 아니라, CloudFormation 템플릿을 만들어서 스택 생성을 위임하는 구조다.

> **CloudFormation**: AWS의 IaC 서비스. JSON이나 YAML로 작성한 템플릿 파일을 제출하면, AWS가 템플릿에 정의된 리소스(VPC, EC2, IAM Role 등)를 자동으로 생성·관리한다. CloudFormation을 통해 생성된 리소스 묶음을 "스택"이라고 한다. 자세한 내용은 [공식 문서](https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/Welcome.html)를 참고한다.

<br>

## 동작 방식

eksctl의 배포 흐름은 다음과 같다.

1. 사용자: `eksctl create cluster ...` 실행
2. eksctl: CloudFormation 템플릿 생성 (VPC, 서브넷, IAM Role, EKS, 노드그룹 등 정의)
3. eksctl → AWS CloudFormation API 호출: 해당 템플릿으로 스택 생성 요청
4. CloudFormation: 실제 AWS 리소스 프로비저닝


eksctl로 클러스터를 만들면 AWS 콘솔 CloudFormation 페이지에서 `eksctl-<클러스터이름>-cluster` 같은 스택이 생성된 것을 확인할 수 있다.

<br>

## 코드로 확인하기

실제 [eksctl 소스 코드](https://github.com/weaveworks/eksctl/blob/8064a501bd4c9c0fa2199ba358fcbd1db63e3356/pkg/cfn/manager/api.go#L93)를 보면, CloudFormation API 클라이언트를 초기화하고 스택 생성을 요청하는 구조를 확인할 수 있다.

`NewStackCollection`에서 `provider.CloudFormation()`으로 CloudFormation API 클라이언트를 초기화한다.

```go
func NewStackCollection(provider api.ClusterProvider, spec *api.ClusterConfig) StackManager {
	tags := []types.Tag{
		newTag(api.ClusterNameTag, spec.Metadata.Name),
		newTag(api.OldClusterNameTag, spec.Metadata.Name),
		newTag(api.EksctlVersionTag, version.GetVersion()),
	}
	for key, value := range spec.Metadata.Tags {
		tags = append(tags, newTag(key, value))
	}
	return &StackCollection{
		spec:              spec,
		sharedTags:        tags,
		cloudformationAPI: provider.CloudFormation(),
		ec2API:            provider.EC2(),
		eksAPI:            provider.EKS(),
		iamAPI:            provider.IAM(),
		cloudTrailAPI:     provider.CloudTrail(),
		asgAPI:            provider.ASG(),
		disableRollback:   provider.CloudFormationDisableRollback(),
		roleARN:           provider.CloudFormationRoleARN(),
		region:            provider.Region(),
		waitTimeout:       provider.WaitTimeout(),
	}
}
```

`DoCreateStackRequest`가 실제로 CloudFormation에 스택 생성을 요청하는 핵심 로직이다. `CreateStackInput`을 구성하고, `c.cloudformationAPI.CreateStack(ctx, input)` 한 줄로 CloudFormation에 스택 생성을 요청한다.

```go
func (c *StackCollection) DoCreateStackRequest(ctx context.Context, i *Stack, templateData TemplateData, tags, parameters map[string]string, withIAM bool, withNamedIAM bool) error {
	input := &cloudformation.CreateStackInput{
		StackName:       i.StackName,
		DisableRollback: aws.Bool(c.disableRollback),
	}
	input.Tags = append(input.Tags, c.sharedTags...)
	for k, v := range tags {
		input.Tags = append(input.Tags, newTag(k, v))
	}

	switch data := templateData.(type) {
	case TemplateBody:
		input.TemplateBody = aws.String(string(data))
	case TemplateURL:
		input.TemplateURL = aws.String(string(data))
	default:
		return fmt.Errorf("unknown template data type: %T", templateData)
	}

	if withIAM {
		input.Capabilities = stackCapabilitiesIAM
	}

	if withNamedIAM {
		input.Capabilities = stackCapabilitiesNamedIAM
	}

	if cfnRole := c.roleARN; cfnRole != "" {
		input.RoleARN = aws.String(cfnRole)
	}

	for k, v := range parameters {
		input.Parameters = append(input.Parameters, types.Parameter{
			ParameterKey:   aws.String(k),
			ParameterValue: aws.String(v),
		})
	}

	logger.Debug("CreateStackInput = %#v", input)
	s, err := c.cloudformationAPI.CreateStack(ctx, input)
	if err != nil {
		return errors.Wrapf(err, "creating CloudFormation stack %q", *i.StackName)
	}
	i.StackId = s.StackId
	return nil
}
```

<br>

# Terraform

## 개요

[Terraform](https://www.terraform.io/)은 HashiCorp의 오픈소스 IaC 도구다. **HCL(HashiCorp Configuration Language)**로 인프라를 코드로 정의하고, `plan` → `apply`로 배포한다. AWS뿐 아니라 다양한 클라우드 프로바이더를 지원한다는 점에서 AWS 전용인 CloudFormation과 차이가 있다.

**이번 실습에서는 Terraform을 주 배포 도구로 사용한다.**

<br>

## HCL 블록

Terraform의 HCL 코드는 다음과 같은 블록으로 구성된다.

| 블록 | 역할 | 예시 |
| --- | --- | --- |
| `provider` | 클라우드 API 연결 설정 | `provider "aws" { ... }` |
| `resource` | **실제 리소스 1개를 직접 생성** | `resource "aws_security_group" "node_group_sg" { ... }` |
| `module` | 여러 resource를 묶은 패키지를 가져다 씀 | `module "vpc" { source = "..." }` |
| `variable` | 변수 선언 | `variable "KeyName" { ... }` |
| `data` | 이미 존재하는 리소스 조회 (읽기 전용) | `data "aws_ami" "latest" { ... }` |

<br>

## Provider

Provider는 특정 클라우드/서비스의 **API와 통신하는 플러그인**이다. Terraform Core가 리소스를 생성·수정·삭제할 때, 실제로 해당 서비스의 API를 호출하는 역할을 담당한다.

Terraform 자체는 코어 엔진이고, 각 클라우드/서비스별 구현은 Provider 플러그인이 담당한다.

| Provider | 대상 |
| --- | --- |
| `hashicorp/aws` | AWS 리소스 (EC2, VPC, EKS 등) |
| `hashicorp/google` | GCP 리소스 |
| `hashicorp/azurerm` | Azure 리소스 |
| `hashicorp/kubernetes` | K8s 리소스 직접 관리 |

`terraform init`을 실행하면 `.tf` 파일에 선언된 Provider를 보고 해당 플러그인을 자동으로 다운로드한다. 실행 후 `.terraform/providers/` 디렉토리에 Provider 플러그인이, `.terraform/modules/` 디렉토리에 모듈 소스가 저장된다.

<br>

## Module

Module은 **재사용 가능한 Terraform 코드 묶음**이다. 여러 `resource`를 묶어 놓은 패키지로, `module` 블록으로 선언한다.

예를 들어 VPC를 만들려면 서브넷, 라우팅 테이블, IGW 등 수십 개 리소스를 일일이 `resource` 블록으로 정의해야 하는데, 커뮤니티가 이를 **모듈로 패키징**해 놓았다. 파라미터만 넘기면 된다.

```hcl
module "vpc" {
  source  = "terraform-aws-modules/vpc/aws"   # 가져올 모듈 위치
  version = "~>6.5"                            # 모듈 버전
  ...
}
```

> **참고**: Ansible Galaxy에서 Role을 가져다 쓰는 것처럼, Terraform Registry에서 모듈을 가져다 쓴다. Kubespray에서 Ansible Role을 활용했던 것과 유사한 구조다.

<br>

## Resource

Resource는 Terraform의 핵심 블록으로, **실제 인프라 리소스 1개를 만들겠다는 선언**이다. 리소스 타입과 로컬 이름으로 구성된다.

```hcl
resource "aws_security_group" "node_group_sg" {
  ...
}
```

- **`aws_security_group`**: 리소스 타입. "AWS의 Security Group을 만들겠다"는 뜻. Provider가 정의한 리소스 종류
- **`node_group_sg`**: 로컬 이름. 이 Terraform 코드 안에서 이 리소스를 참조할 때 쓰는 이름

다른 곳에서 `리소스타입.로컬이름.속성` 형태로 참조할 수 있다. Terraform은 이 참조를 기반으로 **의존성 그래프(DAG)**를 만들어 리소스 간 의존성을 추적하고, 생성 순서를 결정하며, 런타임에 실제 값을 주입한다. `plan` 단계에서 `(known after apply)`라고 나오는 값들이 이에 해당한다.

<br>

## Module vs. Provider

Provider가 있어야 Module이 동작한다.

| | Provider | Module |
| --- | --- | --- |
| **역할** | 클라우드 **API와 통신하는 플러그인** | 여러 리소스를 묶어놓은 **재사용 코드 패키지** |
| **비유** | "AWS랑 대화할 수 있는 드라이버" | "VPC 만드는 레시피북" |
| **없으면?** | AWS 리소스를 아예 만들 수 없음 | 만들 수는 있지만 resource 블록을 일일이 다 써야 함 |
| **선언** | `provider "aws" { ... }` | `module "vpc" { source = "..." }` |

**Provider = 통신 계층, Module = 그 위에서 동작하는 편의 패키지**다. 예를 들어, `module "vpc"`가 내부적으로 `aws_subnet`, `aws_internet_gateway` 같은 리소스를 만드는데, 이 `aws_*` 리소스들은 전부 `hashicorp/aws` Provider를 통해 AWS API를 호출한다.

<br>

## 기본 워크플로우

Terraform의 기본 워크플로우는 네 단계로 이루어진다.

| 단계 | 명령어 | 하는 일 |
| --- | --- | --- |
| **초기화** | `terraform init` | Provider 플러그인 다운로드 + 모듈 다운로드 → `.terraform/` 디렉토리 생성 |
| **계획** | `terraform plan` | "이렇게 만들 거야"를 미리 보여줌 (dry-run). 실제 변경 없음 |
| **적용** | `terraform apply` | plan 내용을 실제로 AWS에 반영. 리소스 생성/수정 |
| **삭제** | `terraform destroy` | apply로 만든 리소스를 전부 삭제 |

- `init`: 처음 한 번, 혹은 모듈/프로바이더가 바뀔 때 실행
- `plan`: `kubectl diff` 혹은 `kubectl apply --dry-run=server`와 비슷한 역할
- `apply`: `kubectl apply`와 비슷한 역할

<br>

## 참고: State와 Backend

Terraform은 `apply`로 생성한 리소스의 현재 상태를 **state 파일**(`terraform.tfstate`)에 기록한다. 이후 `plan`이나 `apply`를 실행할 때 이 state 파일과 실제 인프라를 비교하여 변경 사항을 결정한다.

기본적으로 state 파일은 **로컬**에 저장된다. 혼자 실습할 때는 괜찮지만, 팀 환경에서는 문제가 된다.

| 문제 | 설명 |
| --- | --- |
| **공유 불가** | 로컬 파일이므로 다른 팀원이 state를 볼 수 없음 |
| **동시 수정** | 여러 사람이 동시에 `apply`하면 state가 충돌 |
| **유실 위험** | 로컬 디스크 장애 시 state 파일 유실 → 인프라 추적 불가 |

이를 해결하기 위해 **remote backend**를 설정한다. AWS에서는 S3(state 저장) + DynamoDB(state locking)를 조합하는 것이 일반적이다.

```hcl
terraform {
  backend "s3" {
    bucket         = "my-terraform-state"
    key            = "eks/terraform.tfstate"
    region         = "ap-northeast-2"
    dynamodb_table = "terraform-lock"
    encrypt        = true
  }
}
```

이번 실습에서는 개인 학습 환경이므로 backend 설정 없이 로컬 state로 진행하지만, 실무에서 Terraform을 사용할 때는 항상 remote backend 설정을 의식해야 한다.

<br>

## 참고: Kubespray와의 비교

[On-Premise K8s 스터디](https://sirzzang.github.io/tags/#on-premise-k8s-hands-on-study)에서 사용한 Kubespray가 떠오를 수 있다. 둘 다 인프라를 자동화하는 도구이지만, 추상화하는 대상이 다르다.

- **Kubespray**: Ansible 기반. OS별(Ubuntu, CentOS 등), 환경별(클라우드, 베어메탈 등) **K8s 클러스터 설치 과정**을 추상화한다. 대상은 "이미 존재하는 서버 위에 K8s를 올리는 것"
- **Terraform**: 클라우드 프로바이더별로 **인프라 자체(서버, 네트워크, 스토리지 등)**를 생성하는 것을 추상화한다. 대상은 "인프라 리소스 자체를 만드는 것"

구조적으로도 유사한 점이 있다.

| | Kubespray | Terraform |
| --- | --- | --- |
| **엔진** | Ansible | Terraform Core |
| **환경별 구현** | Kubespray 프로젝트가 직접 작성한 Ansible Playbook/Role | 각 클라우드 벤더(또는 커뮤니티)가 만든 Provider 플러그인 |
| **구현 주체** | Kubespray 팀 | AWS Provider → HashiCorp/AWS, GCP Provider → HashiCorp/Google 등 |

비유하자면 다음과 같다.

- **Ansible = Terraform Core** → 실행 엔진. "이 코드를 해석하고 실행해 줄게"
- **Kubespray의 OS별 Playbook = Terraform의 Provider** → "이 환경에서는 이렇게 해야 해"라는 구체적 구현

다만 차이점도 있다. Kubespray는 하나의 프로젝트 안에서 OS별 로직을 전부 관리하지만, Terraform은 Provider를 플러그인으로 분리해서 각 벤더가 독립적으로 개발하고 배포한다.

<br>

# 결론

EKS 클러스터를 배포하는 세 가지 방법을 살펴봤다.

| 방식 | 내부 구조 | 적합한 환경 |
| --- | --- | --- |
| **웹 콘솔** | AWS Console에서 직접 클릭 | 학습, 일회성 테스트 |
| **eksctl** | CLI → CloudFormation 스택 생성 | 빠른 프로토타이핑, EKS 전용 |
| **Terraform** | HCL → Provider → AWS API 호출 | 프로덕션, 멀티 클라우드, IaC 관리 |

eksctl은 편리하지만 내부적으로 CloudFormation에 위임하는 구조이고, Terraform은 Provider 플러그인을 통해 직접 AWS API를 호출하는 구조다. 이번 스터디에서는 Terraform을 사용해 EKS 클러스터와 관련 인프라를 코드로 관리한다.

다음 글에서는 Terraform 코드를 작성하고, 실제로 EKS 클러스터를 배포한다.

<br>
