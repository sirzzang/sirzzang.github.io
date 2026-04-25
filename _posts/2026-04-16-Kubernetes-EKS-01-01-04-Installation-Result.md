---
title: "[EKS] GitOps 기반 SaaS: 실습 환경 구성 - 4. 설치 결과 확인"
excerpt: "EKS SaaS GitOps 실습 환경 배포가 완료된 후, SSM 접속과 VS Code 웹 환경으로 설치 결과를 확인해 보자."
categories:
  - Kubernetes
toc: true
header:
  teaser: /assets/images/blog-Dev.jpg
tags:
  - Kubernetes
  - AWS
  - EKS
  - SSM
  - Terraform
  - code-server
  - AWS-EKS-Workshop-Study
  - AWS-EKS-Workshop-Study-Week-6
---

*[최영락](https://www.linkedin.com/in/ianychoi/)님의 AWS EKS Workshop Study(AEWS) 6주차 학습 내용을 기반으로 합니다.*

<br>

# TL;DR

- SSM Session Manager로 EC2에 접속하여 배포 결과를 확인한다
- 주요 확인 항목: IAM 자격 증명, 디렉터리 구조, code-server, Terraform 상태, kubectl
- VS Code for the Web(code-server)으로 브라우저 기반 실습 환경을 확인한다
- `terraform output`으로 배포된 전체 리소스 정보를 한눈에 파악한다
- 실습 완료 후 삭제 시 잔여 리소스 수동 제거가 필요하다

<br>

# SSM 접속 및 기본 확인

[이전 포스트]({% post_url 2026-04-16-Kubernetes-EKS-01-01-03-Installation %})에서 CloudFormation 스택 배포를 완료했다. 이제 SSM(Systems Manager) Session Manager를 통해 EC2에 접속하여 설치 결과를 확인한다.

## SSM 인스턴스 확인

먼저 SSM 관리 대상 인스턴스 목록을 조회한다.

```bash
# SSM 관리 대상 인스턴스 목록 조회
aws ssm describe-instance-information \
  --query "InstanceInformationList[*].{InstanceId:InstanceId, Status:PingStatus, OS:PlatformName}" \
  --output text
```

```text
i-0abc1234def56789   Amazon Linux   Online
```

`PingStatus`가 `Online`이면 SSM으로 접속할 수 있는 상태다.

## SSM Session Manager로 접속

조회한 인스턴스 ID를 지정하여 SSM 세션을 시작한다.

```bash
export MYINSTANCE=i-0abc1234def56789
aws ssm start-session --target $MYINSTANCE
```

접속 후 관리자로 전환한다.

```bash
sudo su -
```

## 자격 증명 확인

EC2에 할당된 IAM Role 자격 증명을 확인한다.

```bash
aws configure list
```

```text
NAME       : VALUE                    : TYPE             : LOCATION
profile    : <not set>                : None             : None
access_key : ****************XXXX     : iam-role         :
secret_key : ****************XXXX     : iam-role         :
region     : ap-northeast-2           : imds             :
```

- `TYPE`이 `iam-role`이다. CloudFormation이 부여한 `eks-saas-gitops-admin` IAM Role이 자동으로 적용되어 있다
- `region`은 `imds`(EC2 Instance Metadata Service)에서 자동으로 설정된다

```bash
aws sts get-caller-identity
```

```json
{
    "UserId": "AROA6XXXXXXXXX:i-0abc1234def56789",
    "Account": "123456789012",
    "Arn": "arn:aws:sts::123456789012:assumed-role/eks-saas-gitops-admin/i-0abc1234def56789"
}
```

`assumed-role/eks-saas-gitops-admin`으로 자격 증명이 잡혀 있는 것을 확인할 수 있다.

<br>

# 디렉터리 구조 확인

작업 디렉터리(`/home/ec2-user/`)의 구조를 확인한다.

```bash
cd /home/ec2-user/
tree -a -L 3
```

<details markdown="1">
<summary><b>tree 전체 출력</b></summary>

```text
.
├── .bash_logout
├── .bash_profile
├── .bashrc
├── .cache
│   ├── code-server
│   │   └── code-server-4.117.0-amd64.rpm
│   └── helm
│       └── repository
├── .config
│   ├── code-server
│   │   └── config.yaml
│   └── helm
│       └── registry
├── .kube
│   ├── cache
│   │   ├── discovery
│   │   └── http
│   └── config
├── .local
│   └── share
│       └── code-server
├── .ssh
│   └── authorized_keys
├── .terraform.d
│   ├── checkpoint_cache
│   └── checkpoint_signature
├── eks-saas-gitops
│   ├── .git
│   ├── .gitignore
│   ├── CODE_OF_CONDUCT.md
│   ├── CONTRIBUTING.md
│   ├── LICENSE
│   ├── README.md
│   ├── gitops
│   │   ├── application-plane
│   │   ├── clusters
│   │   ├── control-plane
│   │   └── infrastructure
│   ├── helm-charts
│   │   ├── application-chart
│   │   ├── application-chart-0.0.1.tgz
│   │   ├── helm-tenant-chart
│   │   └── helm-tenant-chart-0.0.1.tgz
│   ├── helpers
│   │   └── vs-code-ec2.yaml
│   ├── scripts
│   │   ├── cleanup.sh
│   │   ├── monitor-tenants.sh
│   │   ├── resize-cloud9-ebs-vol.sh
│   │   └── tenant-control.sh
│   ├── static
│   │   ├── guidance-architecture.png
│   │   └── reference_architecture_part1.jpg
│   ├── tenant-microservices
│   │   ├── consumer
│   │   ├── payments
│   │   └── producer
│   ├── terraform
│   │   ├── destroy.sh
│   │   ├── gitea-ci-test
│   │   ├── install.sh
│   │   ├── modules
│   │   └── workshop
│   └── workflow-scripts
│       ├── 00-validate-tenant.sh
│       ├── 01-tenant-clone-repo.sh
│       ├── 02-tenant-onboarding.sh
│       ├── 03-tenant-deployment.sh
│       ├── 04-tenant-offboarding.sh
│       ├── Dockerfile
│       └── README.md
└── environment
    ├── gitops-gitea-repo
    │   ├── .git
    │   ├── .gitignore
    │   ├── application-plane
    │   ├── clusters
    │   ├── control-plane
    │   ├── helm-charts
    │   ├── infrastructure
    │   └── terraform
    └── terraform-install.log

53 directories, 39 files
```

</details>

## `/home/ec2-user/eks-saas-gitops/`

GitHub에서 clone한 원본 소스 코드이다.

| 하위 디렉터리 | 역할 |
|---|---|
| `helpers/vs-code-ec2.yaml` | CloudFormation 부트스트랩 템플릿 |
| `terraform/install.sh` | 설치 스크립트 |
| `terraform/workshop/` | Terraform 작업 디렉터리 |
| `gitops/` | GitOps 매니페스트 (control-plane, application-plane, infrastructure, clusters) |
| `helm-charts/` | Helm 차트 (application-chart, helm-tenant-chart) |
| `tenant-microservices/` | 마이크로서비스 (producer, consumer, payments) |
| `workflow-scripts/` | Argo Workflow 스크립트 (tenant onboarding/offboarding 등) |

## `/home/ec2-user/environment/gitops-gitea-repo/`

Gitea에서 clone한 실습용 repo이다. 이 repo가 **실제 GitOps 루프의 source**다. 여기에 push하면 Flux가 변경을 감지하여 클러스터에 반영한다.

| 하위 디렉터리 | 역할 |
|---|---|
| `application-plane/` | 애플리케이션 플레인 GitOps 매니페스트 |
| `clusters/` | 클러스터 구성 |
| `control-plane/` | 컨트롤 플레인 GitOps 매니페스트 |
| `infrastructure/` | 인프라 구성 |
| `terraform/` | Terraform 리소스 정의 |

<br>

# code-server 확인

## 설정 파일

code-server의 설정 파일을 확인한다.

```bash
cat .config/code-server/config.yaml
```

```yaml
bind-addr: 0.0.0.0:8080
auth: password
password: xxxxxxxxxxxxxxxx
```

- `bind-addr`: 모든 IP에서 접속을 허용한다 (`0.0.0.0:8080`)
- `auth`: 패스워드 인증을 사용한다
- `password`: SSM Parameter Store의 `code-password` 값과 동일하다

## 프로세스 확인

code-server 프로세스가 정상적으로 실행 중인지 확인한다.

```bash
ps -ef | grep code-server
```

```text
root       27989       1  0 14:20 ?        00:00:00 sudo -u ec2-user nohup /usr/bin/code-server --port 8080 --host 0.0.0.0
ec2-user   28002   27989  0 14:20 ?        00:00:00 /usr/lib/code-server/lib/node /usr/lib/code-server --port 8080 --host 0.0.0.0
ec2-user   28023   28002  0 14:20 ?        00:00:00 /usr/lib/code-server/lib/node /usr/lib/code-server/out/node/entry
```

```bash
ss -tnlp | grep 8080
```

```text
LISTEN 0   511   0.0.0.0:8080   0.0.0.0:*   users:(("node",pid=28023,fd=22))
```

8080 포트에서 정상적으로 리스닝하고 있다.


<br>

# Terraform 상태 확인

## Terraform 버전

```bash
terraform version
```

```text
Terraform v1.14.9
on linux_amd64
```

## Terraform 모듈 구조

Terraform 작업 디렉터리(`/home/ec2-user/eks-saas-gitops/terraform/workshop`)에서 모듈 구조를 확인한다.

```bash
cd /home/ec2-user/eks-saas-gitops/terraform/workshop
tree .terraform -L 3
```

주요 모듈은 다음과 같다.

| 모듈 | 역할 |
|---|---|
| `vpc` | EKS용 VPC 생성 |
| `eks`, `eks.kms` | EKS 클러스터 및 KMS 암호화 |
| `ebs_csi_irsa_role` | EBS CSI 드라이버 IRSA(IAM Roles for Service Accounts) |
| `image_automation_irsa_role` | 이미지 자동화 IRSA |
| `gitops_saas_infra.argo_events_eks_role` | Argo Events IRSA |
| `gitops_saas_infra.argo_workflows_eks_role` | Argo Workflows IRSA |
| `gitops_saas_infra.karpenter_irsa_role` | Karpenter IRSA |
| `gitops_saas_infra.lb_controller_irsa` | AWS Load Balancer Controller IRSA |
| `gitops_saas_infra.tf_controller_irsa_role` | Tofu Controller IRSA |

Provider는 `hashicorp`(aws, kubernetes, helm, null, random 등)와 `go-gitea`(Gitea 리소스 관리)를 사용한다.

<details markdown="1">
<summary><b>tree .terraform 전체 출력</b></summary>

```text
.terraform
├── modules
│   ├── ebs_csi_irsa_role
│   │   ├── CHANGELOG.md
│   │   ├── LICENSE
│   │   ├── README.md
│   │   ├── examples
│   │   ├── modules
│   │   └── wrappers
│   ├── eks
│   │   ├── CHANGELOG.md
│   │   ├── LICENSE
│   │   ├── README.md
│   │   ├── docs
│   │   ├── examples
│   │   ├── main.tf
│   │   ├── modules
│   │   ├── node_groups.tf
│   │   ├── outputs.tf
│   │   ├── templates
│   │   ├── variables.tf
│   │   └── versions.tf
│   ├── eks.kms
│   │   ├── CHANGELOG.md
│   │   ├── LICENSE
│   │   ├── README.md
│   │   ├── examples
│   │   ├── main.tf
│   │   ├── outputs.tf
│   │   ├── variables.tf
│   │   └── versions.tf
│   ├── gitops_saas_infra.argo_events_eks_role
│   │   ├── CHANGELOG.md
│   │   ├── LICENSE
│   │   ├── README.md
│   │   ├── examples
│   │   ├── modules
│   │   └── wrappers
│   ├── gitops_saas_infra.argo_workflows_eks_role
│   │   ├── CHANGELOG.md
│   │   ├── LICENSE
│   │   ├── README.md
│   │   ├── examples
│   │   ├── modules
│   │   └── wrappers
│   ├── gitops_saas_infra.karpenter_irsa_role
│   │   ├── CHANGELOG.md
│   │   ├── LICENSE
│   │   ├── README.md
│   │   ├── examples
│   │   ├── modules
│   │   └── wrappers
│   ├── gitops_saas_infra.lb_controller_irsa
│   │   ├── CHANGELOG.md
│   │   ├── LICENSE
│   │   ├── README.md
│   │   ├── examples
│   │   ├── modules
│   │   └── wrappers
│   ├── gitops_saas_infra.tf_controller_irsa_role
│   │   ├── CHANGELOG.md
│   │   ├── LICENSE
│   │   ├── README.md
│   │   ├── examples
│   │   ├── modules
│   │   └── wrappers
│   ├── image_automation_irsa_role
│   │   ├── CHANGELOG.md
│   │   ├── LICENSE
│   │   ├── README.md
│   │   ├── examples
│   │   ├── modules
│   │   └── wrappers
│   ├── modules.json
│   └── vpc
│       ├── CHANGELOG.md
│       ├── LICENSE
│       ├── README.md
│       ├── UPGRADE-3.0.md
│       ├── UPGRADE-4.0.md
│       ├── examples
│       ├── main.tf
│       ├── modules
│       ├── outputs.tf
│       ├── variables.tf
│       ├── versions.tf
│       └── vpc-flow-logs.tf
└── providers
    └── registry.terraform.io
        ├── go-gitea
        └── hashicorp

43 directories, 47 files
```

</details>

## terraform output

`terraform output` 명령으로 배포된 전체 리소스 정보를 확인한다.

```bash
terraform output
```

핵심 output 항목은 다음과 같다.

| 항목 | 설명 |
|---|---|
| `cluster_name`, `cluster_endpoint` | EKS 클러스터 이름 및 API 서버 엔드포인트 |
| `configure_kubectl` | kubeconfig 설정 명령어 |
| `gitea_url`, `gitea_public_ip`, `gitea_private_ip` | Gitea 서버 접속 정보 |
| `ecr_repositories` | ECR 레포지토리 (consumer, producer, payments, onboarding_service) |
| `*_irsa` | 각 컴포넌트의 IRSA Role ARN (Karpenter, Argo, LB Controller, TF Controller) |
| `argoworkflows_*_queue_url` | SQS 큐 URL (onboarding, deployment, offboarding) |

<details markdown="1">
<summary><b>terraform output 전체 결과 (익명화)</b></summary>

```text
account_id = "123456789012"
argo_events_irsa = "arn:aws:iam::123456789012:role/argo-events-irsa"
argo_workflows_bucket_name = "saasgitops-argo-xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
argo_workflows_irsa = "arn:aws:iam::123456789012:role/argo-workflows-irsa-eks-saas-gitops"
argoworkflows_deployment_queue_url = "https://sqs.ap-northeast-2.amazonaws.com/123456789012/argoworkflows-deployment-queue"
argoworkflows_offboarding_queue_url = "https://sqs.ap-northeast-2.amazonaws.com/123456789012/argoworkflows-offboarding-queue"
argoworkflows_onboarding_queue_url = "https://sqs.ap-northeast-2.amazonaws.com/123456789012/argoworkflows-onboarding-queue"
aws_region = "ap-northeast-2"
cluster_endpoint = "https://XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX.gr7.ap-northeast-2.eks.amazonaws.com"
cluster_name = "eks-saas-gitops"
configure_kubectl = "aws eks --region ap-northeast-2 update-kubeconfig --name eks-saas-gitops"
ecr_argoworkflow_container = "123456789012.dkr.ecr.ap-northeast-2.amazonaws.com/argoworkflow-container"
ecr_helm_chart_url = "123456789012.dkr.ecr.ap-northeast-2.amazonaws.com/gitops-saas/helm-tenant-chart"
ecr_helm_chart_url_application = "123456789012.dkr.ecr.ap-northeast-2.amazonaws.com/gitops-saas/application-chart"
ecr_helm_chart_url_base = "123456789012.dkr.ecr.ap-northeast-2.amazonaws.com/gitops-saas"
ecr_repositories = {
  "consumer" = "123456789012.dkr.ecr.ap-northeast-2.amazonaws.com/consumer"
  "onboarding_service" = "123456789012.dkr.ecr.ap-northeast-2.amazonaws.com/onboarding_service"
  "payments" = "123456789012.dkr.ecr.ap-northeast-2.amazonaws.com/payments"
  "producer" = "123456789012.dkr.ecr.ap-northeast-2.amazonaws.com/producer"
}
flux_namespace = "flux-system"
gitea_password_command = "aws ssm get-parameter --name '/eks-saas-gitops/gitea-admin-password' --with-decryption --query 'Parameter.Value' --output text"
gitea_private_ip = "10.0.1.100"
gitea_public_ip = "203.0.113.50"
gitea_url = "http://203.0.113.50:3000"
karpenter_irsa = "arn:aws:iam::123456789012:role/karpenter_controller"
karpenter_node_role_arn = "arn:aws:iam::123456789012:role/KarpenterNodeRole-eks-saas-gitops"
lb_controller_irsa = "arn:aws:iam::123456789012:role/lb-controller-irsa-eks-saas-gitops"
tf_controller_irsa = "arn:aws:iam::123456789012:role/tf-controller-eks-saas-gitops"
```

</details>

<br>

# VS Code for the Web 접속

CloudFormation 출력(Outputs) 탭에서 VS Code 웹 환경에 접속한다.

## 1. CFN 콘솔 출력 탭 확인

`VsCodeIdeUrl`(접속 URL)과 `VsCodePassword`(SSM Parameter Store 콘솔 링크)를 확인한다.

![CFN 출력 탭]({{site.url}}/assets/images/eks-w6-cloudformation-installation-result-01.png){: .align-center width="700"}
<center><sup>CloudFormation 출력 탭 — VsCodeIdeUrl과 VsCodePassword 확인</sup></center>

## 2. 패스워드 확인

SSM Parameter Store 콘솔에서 `coder-password` 값을 확인한다.

![SSM Parameter Store 패스워드]({{site.url}}/assets/images/eks-w6-cloudformation-installation-result-02.png){: .align-center width="650"}
<center><sup>SSM Parameter Store — coder-password 파라미터 상세 정보</sup></center>

## 3. VsCode 접속

VsCodeIdeUrl 클릭 → 패스워드 입력 → VS Code 웹 환경 확인. code-server 로그인 후 파일 탐색기와 터미널을 사용할 수 있다.

![VS Code 웹 환경]({{site.url}}/assets/images/eks-w6-cloudformation-installation-result-03.png){: .align-center width="700"}
<center><sup>VS Code for the Web 초기 화면 — 폴더 신뢰 확인 다이얼로그</sup></center>

## 4. 터미널에서 기본 확인

`whoami`, `kubectl cluster-info`, `kubectl config view` 등으로 환경이 정상인지 확인한다

![터미널 kubectl 확인]({{site.url}}/assets/images/eks-w6-cloudformation-installation-result-04.png){: .align-center width="700"}
<center><sup>VS Code 터미널에서 kubectl cluster-info, kubectl config view 실행 결과</sup></center>

VS Code 인스턴스에는 모든 필수 도구(AWS CLI, Terraform, Git, kubectl, Helm, Flux CLI)가 사전 설치되어 있다. 이후 실습에서 사용할 Terraform 인프라는 VS Code 서버 인스턴스 설정의 일부로 자동 배포된 상태이므로, 별도의 추가 설치 없이 바로 실습을 진행할 수 있다.

<br>

# 실습 완료 후 삭제

개인 AWS 계정으로 직접 배포한 경우, 실습이 끝나면 리소스를 삭제해야 한다. 삭제 스크립트는 [eks-saas-gitops 삭제 가이드](https://github.com/ianychoi/eks-saas-gitops?tab=readme-ov-file#삭제-스크립트-실행)를 참고한다.

Terraform이 만든 리소스 중 일부는 CloudFormation 스택 삭제만으로 깨끗이 지워지지 않을 수 있다. 다음 리소스들은 수동으로 확인하여 제거해야 한다.

- ELB 대상 그룹
- SQS 큐
- DynamoDB Table
- SSM Parameter Store
- VPC
- S3 버킷
- IAM Role

<br>

# 정리

- SSM으로 EC2 내부 상태를 직접 확인하면 배포가 정상적으로 완료되었는지 검증할 수 있다
- code-server 덕분에 브라우저만으로 완전한 개발 환경을 사용할 수 있다
- `terraform output`으로 배포된 전체 인프라의 접속 정보를 한 번에 확인할 수 있다
- 삭제 시 잔여 리소스 수동 정리를 잊지 말 것

이제 실습 환경 구성이 마무리되었다.

1. [개요]({% post_url 2026-04-16-Kubernetes-EKS-01-00-Installation-Overview %})
2. [CloudFormation 템플릿 분석]({% post_url 2026-04-16-Kubernetes-EKS-01-01-01-Installation-CloudFormation %})
3. [install.sh 분석]({% post_url 2026-04-16-Kubernetes-EKS-01-01-02-Installation-Install-Script %})
4. [설치]({% post_url 2026-04-16-Kubernetes-EKS-01-01-03-Installation %})
5. **설치 결과 확인** (현재 글)

이제는 이렇게 구성된 환경 위에서 본격적인 GitOps 실습을 진행한다. Gitea에 Terraform CRD를 push하여 테넌트를 온보딩하고, Flux가 변경을 감지하여 클러스터에 반영하는 과정, 그리고 Argo Workflows를 통한 배포 워크플로우를 다뤄 본다.

<br>
