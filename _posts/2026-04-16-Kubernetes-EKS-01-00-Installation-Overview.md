---
title: "[EKS] GitOps 기반 SaaS: 실습 환경 개요"
excerpt: "EKS 기반 GitOps SaaS 워크숍의 실습 환경 구조(CloudFormation 부트스트랩과 Terraform 인프라 배포의 2단 구조)를 살펴보자."
categories:
  - Kubernetes
toc: true
header:
  teaser: /assets/images/blog-Dev.jpg
tags:
  - Kubernetes
  - AWS
  - EKS
  - GitOps
  - Terraform
  - CloudFormation
  - Flux
  - SaaS
  - AWS-EKS-Workshop-Study
  - AWS-EKS-Workshop-Study-Week-6
---

*[최영락](https://www.linkedin.com/in/ianychoi/)님의 AWS EKS Workshop Study(AEWS) 6주차 학습 내용을 기반으로 합니다.*

<br>

# TL;DR

- 이번 워크숍은 **EKS 기반 GitOps SaaS 아키텍처**를 다룬다
- 실습 환경은 **1단계 CloudFormation 부트스트랩 + 2단계 Terraform 인프라 배포**의 2단 구조이다
- 직접 환경을 구성할 경우, "스택 생성" 클릭 하나로 ~30분 후 모든 환경이 자동 구축된다
- 최종 환경: EKS + Flux v2 + Gitea + ECR + Argo Workflows/Events + Karpenter 등
- 참조 레포: [ianychoi/eks-saas-gitops](https://github.com/ianychoi/eks-saas-gitops) (re:Invent 2023 CON311 워크숍 기반 커스터마이징)

<br>

# 워크숍 배경

이번 워크숍은 AWS re:Invent 2023의 [CON311: Platform engineering with Amazon EKS](https://www.youtube.com/watch?v=eLxBnGoBltc) 워크숍([슬라이드](https://d1.awsstatic.com/events/Summits/reinvent2023/CON311_Platform-engineering-with-Amazon-EKS.pdf))을 기반으로 한다. 최영락님이 이를 커스터마이징한 [ianychoi/eks-saas-gitops](https://github.com/ianychoi/eks-saas-gitops) 레포를 사용한다.

개인 AWS 계정으로도 직접 구성할 수 있다. [구현 가이드](https://aws-solutions-library-samples.github.io/compute/building-saas-applications-on-amazon-eks-using-gitops.html#deploy-the-guidance)를 따르면 약 24분 만에 실습 환경을 프로비저닝할 수 있다.

<br>

# 실습 환경 2단 구조

이 워크숍의 실습 환경은 2단 구조로 프로비저닝된다.

1. **1단계**: CloudFormation으로 부트스트랩 EC2를 띄운다
2. **2단계**: 그 EC2 안에서 Terraform이 EKS, Flux, Gitea 등 본 실습 인프라를 배포한다

CloudFormation은 "Terraform을 돌릴 환경을 만들기 위한 가벼운 부팅 패드" 역할만 한다.

> [EKS 배포 개요]({% post_url 2026-03-12-Kubernetes-EKS-01-01-00-Installation-Overview %})에서 eksctl이 내부적으로 CloudFormation을 사용한다는 점을 다룬 바 있다. 이번에는 eksctl 없이 CloudFormation 템플릿을 직접 사용한다.

## 1단계: CloudFormation 부트스트랩

CloudFormation 템플릿([`vs-code-ec2.yaml`](https://github.com/ianychoi/eks-saas-gitops/blob/main/helpers/vs-code-ec2.yaml))으로 다음을 생성한다.

- **EC2 인스턴스** 생성 (VS Code 웹 서버 포함)
- **VPC, 서브넷, 보안 그룹** 등 네트워크 구성
- EC2에 **AdministratorAccess** IAM Role 부여
- **CLI 도구 자동 설치**: kubectl, helm, flux CLI, terraform, yq, git 등

상세 내용은 [CloudFormation 코드 분석]({% post_url 2026-04-16-Kubernetes-EKS-01-01-01-Installation-CloudFormation %})에서 다룬다.

## 2단계: install.sh (Terraform 인프라 배포)

CloudFormation에 의해 EC2가 부팅되면, SSM(AWS Systems Manager)이 자동으로 `install.sh`를 실행한다. 이 스크립트가 Terraform을 통해 다음을 배포한다.

- **EKS 클러스터** 생성 (+ 애드온)
- **Flux v2** 설치 및 부트스트랩
- **Tofu Controller** (tf-controller) 설치
- **Argo Workflows / Argo Events** 설치
- **Gitea** 서버 배포 + Git 저장소 초기화
- **ECR** 레포지토리 생성 + Producer/Consumer 컨테이너 이미지 빌드 & 푸시
- **Helm 차트** ECR에 업로드
- **pool-1 네임스페이스** 생성 + 기본 HelmRelease 배포
- **Karpenter, Kubecost, Metrics Server** 등 설치
- **ConfigMap**(`saas-infra-outputs`)에 Gitea URL/토큰 등 저장

상세 내용은 [install.sh 코드 분석]({% post_url 2026-04-16-Kubernetes-EKS-01-01-02-Installation-Install-Script %})에서 다룬다.

<br>

# 최종 실습 환경 아키텍처

1단계(CloudFormation) + 2단계(install.sh/Terraform)가 모두 끝나면, 참가자가 실습을 시작할 수 있는 최종 환경이 완성된다.

![최종 실습 환경 아키텍처]({{site.url}}/assets/images/eks-w6-saas-gitops-architecture.png){: .align-center}

## 구성 요소별 생성 단계

각 구성 요소가 어느 단계에서 만들어지는지 매핑하면 다음과 같다.

| 구성 요소 | 생성 단계 | 세부 |
| --- | --- | --- |
| **VS Code 서버 (EC2 + code-server)** | 1단계 (CFN; CloudFormation) | `vs-code-ec2.yaml`의 `EC2Instance`, code-server 설치, 8080 포트 SG(Security Group) |
| **VS Code용 VPC (10.0.0.0/16)** | 1단계 (CFN) | `AWS::EC2::VPC`, PublicSubnet + IGW |
| **EKS 클러스터 + Node Group** | 2단계 (install.sh) | `module.eks` |
| **EKS용 VPC + Subnet** | 2단계 (install.sh) | `module.vpc` (CFN VPC와는 별개, VPC Peering으로 연결) |
| **Flux v2** | 2단계 (install.sh) | `module.flux_v2`, `quick_fix_flux.sh` |
| **Tofu Controller (tf-controller)** | 2단계 (install.sh) | `module.gitops_saas_infra` |
| **Gitea 서버 (EC2)** | 2단계 (install.sh) | `module.gitea` (별도 EC2 인스턴스) |
| **Gitea 내 Git 저장소** | 2단계 (install.sh) | `gitea_repository.eks-saas-gitops` |
| **ECR 레포지토리** | 2단계 (install.sh) | `apply_remaining_resources`에서 생성 |
| **Producer / Consumer 이미지** | 2단계 (install.sh) | ECR에 빌드 & 푸시 |
| **Karpenter, Kubecost, Metrics Server** | 2단계 (install.sh) | `apply_remaining_resources` |
| **pool-1 네임스페이스 + HelmRelease** | 2단계 (install.sh) | Flux가 Gitea를 watch하며 배포 |
| **`saas-infra-outputs` ConfigMap** | 2단계 (install.sh) | `kubernetes_config_map.saas_infra_outputs` |

## 핵심 포인트

이 아키텍처에서 주목할 점은 크게 세 가지다.

### 1. VPC가 2개다

다이어그램에서는 하나처럼 보이지만, 실제로는 두 개의 VPC가 존재한다.

| VPC | CIDR | 용도 | 생성 단계 |
| --- | --- | --- | --- |
| CFN VPC | `10.0.0.0/16` | VS Code EC2 | 1단계 (CloudFormation) |
| Terraform VPC | `module.vpc` | EKS + Gitea | 2단계 (install.sh) |

두 VPC는 **VPC Peering**(`aws_vpc_peering_connection.vscode_to_gitea`)으로 연결되어, VS Code 터미널에서 `kubectl`이나 `git push`로 EKS와 Gitea에 접근할 수 있다.

### 2. 진입점은 VS Code 서버 하나다

다이어그램의 나머지 구성 요소(EKS, Flux, Gitea, ECR 등)는 전부 code-server 안 터미널에서 `kubectl`, `flux`, `git` 명령으로 조작한다. CFN으로 부트스트랩 EC2만 띄우면 그 안에서 전부 접근 가능한 구조다.

> 참고: code-server
>
> [code-server](https://github.com/coder/code-server)는 VS Code를 웹 서버로 실행하여 브라우저에서 접속할 수 있게 해주는 오픈소스 프로젝트다. VS Code 자체가 Electron(웹 기술 기반) 앱이므로, 서버에서 실행하고 브라우저로 UI를 렌더링하는 것이 가능하다.
>
> 워크숍에서 이 방식을 사용하는 이유는 **실습 참가자마다 로컬 환경이 다르기 때문**이다. Mac + zsh, Windows + PowerShell, 회사 보안 정책으로 로컬 설치가 불가능한 경우 등 다양한 환경 차이를 없애기 위해, 모든 도구(kubectl, helm, flux CLI, terraform, git 등)가 사전 설치된 **동일한 환경을 브라우저로 제공**한다.

### 3. CFN `CREATE_COMPLETE`은 2단계까지 완료됨을 의미한다

CloudFormation의 `WaitCondition`이 `install.sh`의 종료 신호를 기다리기 때문에, 스택 상태가 `CREATE_COMPLETE`로 바뀐 시점에는 다이어그램의 모든 컴포넌트가 이미 떠 있다. 참가자 입장에서 "스택 완료 → 바로 실습 시작"이 성립한다.

## GitOps 아키텍처 요약

최종 환경의 GitOps 흐름을 요약하면 다음과 같다.

![GitOps 아키텍처 흐름]({{site.url}}/assets/images/eks-w6-saas-gitops-architecture-diagram.png){: .align-center}

- **인프라 관리**: Terraform 소스 코드를 Gitea로 관리한다. Flux가 변경을 감지하면 Tofu Controller가 `tf-runner` Pod를 띄워 인프라를 프로비저닝한다.
- **애플리케이션 관리**: Producer/Consumer 마이크로서비스 코드를 Gitea로 관리한다. Gitea Actions가 컨테이너 이미지를 빌드하여 ECR에 업로드하고, Flux가 Gitea GitOps 레포의 HelmRelease 변경을 감지하면 ECR에서 Helm 차트와 이미지를 pull하여 EKS에 배포한다.

<br>

# 자동 세팅 vs 직접 하는 것

| 구분 | 내용 |
| --- | --- |
| **자동** | CloudFormation 템플릿 + install.sh + Terraform 모듈 + Git 저장소 코드 |
| **직접** | Terraform CRD(Custom Resource Definition) 파일을 Git에 push (테넌트 온보딩), 변수 변경 실험, Flux 반영 관찰 |

"스택 생성" 클릭 하나로 ~30분 후 모든 환경이 자동 구축된다. 복잡한 환경 세팅은 전부 자동화되어 있고, 참가자는 핵심 GitOps 흐름만 직접 체험하는 구조다.

<br>

# 참고: Flux, OpenTofu, Tofu Controller

## Flux

**Flux**(v2)는 CNCF 졸업(Graduated) 프로젝트로, Kubernetes 네이티브 GitOps 도구다. Git 저장소의 선언적 매니페스트를 단일 진실 공급원(Single Source of Truth)으로 삼아, 클러스터 상태를 자동으로 동기화한다.

이 워크숍에서 Flux는 두 가지 역할을 한다.

1. **애플리케이션 배포**: Gitea의 HelmRelease 변경을 감지하여 EKS에 배포
2. **인프라 GitOps 트리거**: Terraform CRD 변경을 감지하여 Tofu Controller를 트리거

### Flux vs ArgoCD

Flux와 ArgoCD는 모두 Kubernetes GitOps 도구이다.

| | Flux | ArgoCD |
| --- | --- | --- |
| **CNCF** | Graduated | Graduated |
| **아키텍처** | CRD 기반 컨트롤러 집합 (모듈형) | 단일 애플리케이션 (올인원) |
| **UI** | 없음 (CLI 중심, Weave GitOps 등 별도 UI) | 내장 웹 UI |
| **배포 방식** | `Kustomization`, `HelmRelease` CRD | `Application` CRD |
| **알림/이벤트** | Notification Controller 내장 | Notification 내장 |
| **IaC 연동** | Tofu Controller로 Terraform 직접 실행 | 별도 연동 필요 |

Tofu Controller가 Flux의 Source Controller에 의존하는 Flux 전용 컴포넌트이기 때문에, 이 워크숍에서는 Flux + Tofu Controller 조합으로 **애플리케이션 배포와 인프라 프로비저닝을 하나의 GitOps 파이프라인**에서 처리한다.

## OpenTofu

**OpenTofu**는 Terraform의 오픈소스 포크(Fork)다.

2023년 8월, HashiCorp가 Terraform의 라이선스를 오픈소스(MPL 2.0)에서 BSL(Business Source License)로 변경했다. 이에 커뮤니티가 기존 MPL 라이선스 기반 코드를 포크하여 만든 것이 OpenTofu이며, Linux Foundation 산하 프로젝트로 관리되고 있다.

| | Terraform | OpenTofu |
| --- | --- | --- |
| **라이선스** | BSL (2023년~) | MPL 2.0 (오픈소스) |
| **CLI** | `terraform` | `tofu` |
| **문법** | HCL | HCL (동일) |
| **상업적 사용** | 제약 있음 | 제약 없음 |

## Tofu Controller

**Tofu Controller**(구 Weave TF-Controller)는 Kubernetes에서 GitOps로 Terraform/OpenTofu를 자동 실행하는 컨트롤러다.

동작 흐름은 다음과 같다.

1. Git에 Terraform/OpenTofu 코드를 push
2. Flux가 변경을 감지
3. Tofu Controller가 `tf-runner` Pod를 띄워 인프라 프로비저닝 실행

Kubernetes CRD로 `Terraform` 리소스를 정의하면, Tofu Controller가 이를 감지하여 클러스터 안에서 자동으로 `terraform apply`(또는 `tofu apply`)를 실행한다. 자세한 내용은 [flux-iac/tofu-controller](https://github.com/flux-iac/tofu-controller)를 참고한다.

<br>

# 정리

이번 글에서는 EKS 기반 GitOps SaaS 워크숍의 실습 환경 전체 구조를 살펴봤다. 

이후 포스트에서는 각 단계를 상세히 분석한다.

1. [CloudFormation 코드 분석]({% post_url 2026-04-16-Kubernetes-EKS-01-01-01-Installation-CloudFormation %})
2. [install.sh 코드 분석]({% post_url 2026-04-16-Kubernetes-EKS-01-01-02-Installation-Install-Script %})
3. [설치]({% post_url 2026-04-16-Kubernetes-EKS-01-01-03-Installation %})
4. [설치 결과 확인]({% post_url 2026-04-16-Kubernetes-EKS-01-01-04-Installation-Result %})

<br>