---
title: "[EKS] GitOps 기반 SaaS: 실습 환경 구성 - 3. 설치"
excerpt: "CloudFormation 스택 생성부터 Terraform 인프라 배포 완료까지의 과정을 살펴 보자."
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
  - CloudFormation
  - Terraform
  - GitOps
  - AWS-EKS-Workshop-Study
  - AWS-EKS-Workshop-Study-Week-6
---

*[최영락](https://www.linkedin.com/in/ianychoi/)님의 AWS EKS Workshop Study(AEWS) 6주차 학습 내용을 기반으로 합니다.*

<br>

# TL;DR

- CloudFormation 콘솔에서 스택 생성 → ~30분 후 자동으로 전체 환경 구축
- 스택 배포 중 SSM Session Manager로 EC2에 접속하면 `terraform-install.log`로 진행 상황을 실시간 모니터링할 수 있다
- `CREATE_COMPLETE` = 1단계(CloudFormation) + 2단계(Terraform) **모두** 완료된 상태

<br>

# 사전 준비

- 개인 AWS 계정 + AdministratorAccess 권한을 가진 IAM 사용자
- 참조 레포: [ianychoi/eks-saas-gitops](https://github.com/ianychoi/eks-saas-gitops) 또는 [aws-samples/eks-saas-gitops](https://github.com/aws-samples/eks-saas-gitops)
- [구현 가이드](https://aws-solutions-library-samples.github.io/compute/building-saas-applications-on-amazon-eks-using-gitops.html#deploy-the-guidance) 참조

최영락님께서 AWS 워크숍 환경을 제공해 주셔서 1회차 실습을 진행했는데, 내부 구조를 더 자세히 이해하기 위해 2회차에는 개인 AWS 계정에서 직접 CloudFormation으로 배포해 보았다.

<br>

# CloudFormation 스택 생성

## 템플릿 업로드

1. AWS CloudFormation 콘솔로 이동한다

![CloudFormation 콘솔 검색]({{site.url}}/assets/images/eks-w6-cloudformation-installation-01.png){: .align-center width="700"}
<center><sup>AWS 콘솔에서 CloudFormation 검색</sup></center>

![CloudFormation 스택 목록]({{site.url}}/assets/images/eks-w6-cloudformation-installation-02.png){: .align-center width="700"}
<center><sup>CloudFormation 스택 목록 — 초기 상태</sup></center>

2. "스택 생성" → "새 리소스 사용(표준)"을 선택한다

![스택 생성 메뉴]({{site.url}}/assets/images/eks-w6-cloudformation-installation-03.png){: .align-center width="350"}
<center><sup>스택 생성 → 새 리소스 사용(표준) 선택</sup></center>

3. "템플릿 파일 업로드"를 선택하고, 이 리포지토리의 `helpers/vs-code-ec2.yaml` 파일을 업로드한다

![S3 URL 입력 화면]({{site.url}}/assets/images/eks-w6-cloudformation-installation-04.png){: .align-center width="700"}
<center><sup>1단계: 기존 템플릿 선택 — Amazon S3 URL 또는 템플릿 파일 업로드 선택</sup></center>

![템플릿 파일 업로드]({{site.url}}/assets/images/eks-w6-cloudformation-installation-05.png){: .align-center width="700"}
<center><sup>1단계: 템플릿 파일 업로드 — vs-code-ec2.yaml 선택</sup></center>

## 스택 세부 정보 지정

"다음"을 클릭하여 스택 세부 정보를 지정한다.

**스택 이름**: `eks-saas-gitops-vscode`

**파라미터 구성**:

| 파라미터 | 값 | 비고 |
|---|---|---|
| EnvironmentName | `eks-saas-gitops` | 기본값 |
| InstanceType | `t3.large` | 기본값 |
| **AllowedIP** | 본인 공인 IP/32 | 보안을 위해 `0.0.0.0/0` 대신 특정 IP 사용 권장 |
| LatestAmiId | 기본값 유지 | SSM에서 최신 AL2023 AMI 자동 조회 |

![파라미터 기본값]({{site.url}}/assets/images/eks-w6-cloudformation-installation-06.png){: .align-center width="700"}
<center><sup>2단계: 스택 세부 정보 지정 — 파라미터 기본값. AllowedIP가 0.0.0.0/0으로 설정되어 있다</sup></center>

![파라미터 실제 값]({{site.url}}/assets/images/eks-w6-cloudformation-installation-07.png){: .align-center width="700"}
<center><sup>2단계: AllowedIP에 본인 공인 IP/32를 입력한 모습</sup></center>

### AllowedIP 설정

AllowedIP는 VS Code 서버 EC2의 보안 그룹에 허용할 소스 CIDR이다. EC2 보안 그룹은 출발지를 공인 IP 기준으로 판단하므로, 사설 IP(예: `192.168.x.x`, `10.x.x.x`)를 넣으면 접속할 수 없다.

| 상황 | 권장 CIDR | 예시 |
|---|---|---|
| 집/개인 PC | 내 공인 IP/32 | `123.45.67.89/32` |
| 회사/VPN | 회사 egress IP 대역 | `203.0.113.0/24` |
| 테스트/단기 실습 (비권장) | `0.0.0.0/0` | 전체 오픈 |

현재 공인 IP는 터미널에서 확인할 수 있다.

```bash
curl ifconfig.me
```

`/32`는 "정확히 그 IP 하나만 허용"이라는 의미다.

## 스택 옵션 구성

기본값 그대로 유지하면 된다.

| 옵션 | 의미 | 실습에서 |
|---|---|---|
| 태그 | 리소스 라벨링 용도 | 불필요 (템플릿이 자동 태깅) |
| IAM 역할 | CFN이 위임받을 역할 | 비워두면 현재 사용자 권한으로 실행 |
| 스택 실패 옵션 | 실패 시 리소스 롤백 | 모든 리소스 롤백 (기본값 유지) |
| 롤백 중 삭제 | 삭제 정책 사용 | 기본값 유지 |

![스택 옵션 구성]({{site.url}}/assets/images/eks-w6-cloudformation-installation-08.png){: .align-center width="700"}
<center><sup>3단계: 스택 옵션 구성 — 태그, IAM 역할, 스택 실패 옵션 등 기본값 유지</sup></center>

## IAM 기능 승인 및 전송

맨 아래 "기능" 섹션의 체크박스를 반드시 체크해야 한다.

> **AWS CloudFormation에서 사용자 지정 이름으로 IAM 리소스를 생성할 수 있음을 승인합니다.**

이 템플릿은 `eks-saas-gitops-admin`이라는 **고정 이름의 IAM Role**(+ AdministratorAccess 권한)과 InstanceProfile을 만든다. 사용자 지정 이름의 IAM 리소스를 생성하기 때문에 `CAPABILITY_NAMED_IAM` 승인이 필요하다.

체크하지 않으면 다음 에러로 즉시 실패한다.

```text
Requires capabilities : [CAPABILITY_NAMED_IAM]
```

![IAM 기능 승인]({{site.url}}/assets/images/eks-w6-cloudformation-installation-09.png){: .align-center width="700"}
<center><sup>3단계 하단: 기능 섹션 — IAM 리소스 생성 승인 체크박스를 반드시 체크해야 한다</sup></center>

체크 후 "전송" 버튼을 클릭하면 스택 생성이 시작된다.

![검토 및 작성 상단]({{site.url}}/assets/images/eks-w6-cloudformation-installation-10.png){: .align-center width="700"}
<center><sup>4단계: 검토 및 작성 — 템플릿 지정단계, 스택 세부 정보 확인</sup></center>

![검토 및 작성 하단]({{site.url}}/assets/images/eks-w6-cloudformation-installation-11.png){: .align-center width="700"}
<center><sup>4단계: 검토 및 작성 하단 — 전송 버튼 클릭으로 스택 생성 시작</sup></center>

<br>

# 배포 진행 모니터링

## CloudFormation 콘솔에서 확인

스택 이벤트 탭에서 리소스 생성 타임라인을 확인할 수 있다.

![이벤트 테이블 뷰]({{site.url}}/assets/images/eks-w6-cloudformation-table-01.png){: .align-center width="700"}
<center><sup>이벤트 테이블 뷰 — 리소스별 생성 상태를 시간순으로 확인할 수 있다</sup></center>

![타임라인 초기]({{site.url}}/assets/images/eks-w6-cloudformation-timeline-01.png){: .align-center width="700"}
<center><sup>타임라인 뷰 — VPC, InternetGateway, EC2Role 등 기본 리소스 생성 시작</sup></center>

![타임라인 진행]({{site.url}}/assets/images/eks-w6-cloudformation-timeline-02.png){: .align-center width="700"}
<center><sup>타임라인 뷰 — PublicSubnet, EC2SecurityGroup 등 네트워크 리소스 생성 진행</sup></center>

![타임라인 WaitCondition 대기]({{site.url}}/assets/images/eks-w6-cloudformation-timeline-03.png){: .align-center width="700"}
<center><sup>타임라인 뷰 — EC2Instance 생성 완료 후 WaitCondition 대기 시작</sup></center>

![타임라인 완료]({{site.url}}/assets/images/eks-w6-cloudformation-timeline-04.png){: .align-center width="700"}
<center><sup>타임라인 뷰 — 스택 생성 완료. WaitCondition 막대가 전체의 대부분을 차지한다</sup></center>

콘솔 타임라인에서 주목할 점은 **WaitCondition 막대가 전체 길이의 80% 이상**을 차지한다는 것이다. 이 구간이 `install.sh` → Terraform 실행 시간에 해당한다. CFN 타임라인에는 EC2, VPC, SG 등 CloudFormation이 직접 만든 리소스만 보인다. EKS, Flux, Gitea, ECR 등은 **EC2 내부에서 Terraform이 생성한 것**이므로, CloudFormation은 그 존재를 알지 못하고 WaitCondition 신호만 기다리는 상태다.

> **참고: tracking-stack**
>
> CloudFormation 콘솔에 `tracking-stack-<랜덤>` 이름의 스택이 자동으로 나타날 수 있다. 이는 AWS가 내부 추적 용도로 자동 생성하는 스택으로, `EmptyResource` 하나만 포함되어 있다. 과금 없음, 실습 환경에 영향 없음 → 무시하면 된다.

![tracking-stack 타임라인]({{site.url}}/assets/images/eks-w6-cloudformation-timeline-05-tracking-stack.png){: .align-center width="700"}
<center><sup>tracking-stack 타임라인 — EmptyResource 하나만 포함된 AWS 내부 추적용 스택</sup></center>

## 터미널에서 실시간 모니터링

SSM Session Manager로 EC2에 접속하면, Terraform의 진행 상황을 실시간으로 확인할 수 있다.

```bash
# SSM 인스턴스 확인
aws ssm describe-instance-information \
  --query "InstanceInformationList[*].{InstanceId:InstanceId, Status:PingStatus, OS:PlatformName}" \
  --output text

# SSM으로 접속
export MYINSTANCE=i-0abc1234def56789
aws ssm start-session --target $MYINSTANCE

# 접속 후 root로 전환
sudo su -

# Terraform 설치 로그 실시간 확인
tail -f /home/ec2-user/environment/terraform-install.log

# install.sh 프로세스 확인
ps -ef | grep install.sh
```

> **주의**: SSM Status가 Online이라는 것은 SSM Agent가 정상 체크인 중이라는 뜻일 뿐, `install.sh`는 아직 진행 중일 수 있다.

### terraform-install.log 주요 단계

`tail -f` 로그를 보면 다음과 같은 단계를 거친다.

**1. VPC + EKS 클러스터 생성**: 가장 오래 걸리는 구간이다.

```text
module.vpc.aws_nat_gateway.this[0]: Still creating... [00m10s elapsed]
module.eks.aws_eks_cluster.this[0]: Still creating... [00m10s elapsed]
...
module.eks.aws_eks_cluster.this[0]: Still creating... [07m30s elapsed]
```

**2. Gitea 서버 생성**

```text
module.gitea.aws_instance.gitea: Creation complete after 13s [id=i-0abc1234def56789]
```

**3. IRSA(IAM Roles for Service Accounts) 역할 생성**: Karpenter, Argo Workflows, Argo Events, LB Controller, TF Controller 등의 IAM Role을 생성한다.

**4. setup-repos 스크립트 실행**: payments, consumer, producer 세 저장소를 Gitea에 생성하고 초기 코드를 푸시한다.

<details markdown="1">
<summary><b>setup-repos 로그 발췌</b></summary>

```text
null_resource.execute_setup_repos_script: Creating...
null_resource.execute_setup_repos_script (local-exec): Executing: ["/bin/sh" "-c" "bash ./setup-repos.sh"]
null_resource.execute_setup_repos_script (local-exec): Getting configuration from Terraform outputs...
null_resource.execute_setup_repos_script (local-exec): Getting Gitea token from SSM Parameter Store...
null_resource.execute_setup_repos_script (local-exec): Getting ECR repository URLs from Terraform outputs...

null_resource.execute_setup_repos_script (local-exec): Processing payments...
null_resource.execute_setup_repos_script (local-exec): Creating repository for payments...
null_resource.execute_setup_repos_script (local-exec): ECR URL for payments: 123456789012.dkr.ecr.ap-northeast-2.amazonaws.com/payments
null_resource.execute_setup_repos_script (local-exec): Preparing payments code...
null_resource.execute_setup_repos_script (local-exec): Pushing payments code to Gitea...
null_resource.execute_setup_repos_script (local-exec): payments setup complete

null_resource.execute_setup_repos_script (local-exec): Processing consumer...
null_resource.execute_setup_repos_script (local-exec): Creating repository for consumer...
null_resource.execute_setup_repos_script (local-exec): consumer setup complete

null_resource.execute_setup_repos_script (local-exec): Processing producer...
null_resource.execute_setup_repos_script (local-exec): Creating repository for producer...
null_resource.execute_setup_repos_script (local-exec): producer setup complete

null_resource.execute_setup_repos_script (local-exec): All repositories have been set up successfully
null_resource.execute_setup_repos_script: Creation complete after 24s
```

</details>

**5. Flux v2 설치**: Flux Operator Helm chart를 설치하고 FluxInstance CRD를 적용한다.

<details markdown="1">
<summary><b>Flux 설치 로그 발췌</b></summary>

```text
module.flux_v2.helm_release.flux2-operator: Creating...
module.flux_v2.kubernetes_secret.flux_system: Creating...
module.flux_v2.kubernetes_secret.flux_system: Creation complete after 1s
module.flux_v2.helm_release.flux2-operator: Creation complete after 24s [id=flux-operator]
module.flux_v2.local_file.flux_instance_manifest: Creation complete after 0s
module.flux_v2.null_resource.apply_flux_instance: Creating...
module.flux_v2.null_resource.apply_flux_instance (local-exec): Waiting for Flux CRDs to be available...
module.flux_v2.null_resource.apply_flux_instance (local-exec): customresourcedefinition.apiextensions.k8s.io/fluxinstances.fluxcd.controlplane.io condition met
module.flux_v2.null_resource.apply_flux_instance (local-exec): Applying FluxInstance manifest...
module.flux_v2.null_resource.apply_flux_instance (local-exec): fluxinstance.fluxcd.controlplane.io/flux created
module.flux_v2.null_resource.apply_flux_instance: Creation complete after 2s

Apply complete! Resources: 4 added, 0 changed, 0 destroyed.
```

</details>

**6. 최종 terraform apply**: 실패한 Helm release 정리 후, 나머지 리소스(EBS CSI IRSA, EKS addon 등)를 생성한다.

<details markdown="1">
<summary><b>최종 apply 로그 발췌</b></summary>

```text
Deleting failed Helm releases in the flux-system namespace...
► deleting helmrelease karpenter in flux-system namespace
✔ helmrelease deleted
► deleting helmrelease kubecost in flux-system namespace
✔ helmrelease deleted
► deleting helmrelease metrics-server in flux-system namespace
✔ helmrelease deleted

Reconciling source git 'flux-system' in the flux-system namespace...
✔ fetched revision refs/heads/main@sha1:b792d408...

Applying remaining Terraform resources...
Apply complete! Resources: 2 added, 1 changed, 0 destroyed.

All Terraform resources created successfully.
==============================
Flux Setup Complete!
==============================
You can now check the status of Flux with:
kubectl get pods -n flux-system
==============================
```

</details>

**7. 설치 완료 및 Gitea repo clone**: 모든 인프라가 생성된 후, `eks-saas-gitops` 저장소를 로컬에 clone한다.

```text
==============================
Infrastructure Installation Complete!
==============================
Gitea URL: http://xx.xx.xx.xx:3000
Gitea Admin Username: admin
Gitea Admin Password: ********

Your EKS cluster has been configured.
==============================
Cloning Gitea repositories...
Repository cloning completed successfully!
```

<br>

# 배포 완료 확인

## CREATE_COMPLETE의 의미

CloudFormation 콘솔에서 스택 상태가 `CREATE_COMPLETE`로 전환되었다면, 다음이 **모두** 완료된 것이다.

- VS Code EC2 부팅 완료
- code-server 실행 중 (8080 포트)
- `install.sh`의 Terraform이 전부 성공적으로 apply됨
- EKS 클러스터, Gitea, Flux, ECR 등 모두 배포됨
- `gitops-gitea-repo`까지 로컬에 clone 완료

이렇게 동작하는 이유는 [이전 포스트]({% post_url 2026-04-16-Kubernetes-EKS-GitOps-Saas-01-01-01-Installation-CloudFormation %})에서 분석한 **WaitCondition** 때문이다.

```yaml
WaitCondition.DependsOn: SSMBootstrapAssociation
WaitCondition.Timeout: 2000  # ~33분
```

CloudFormation은 EC2 내부의 `install.sh`가 Terraform으로 모든 리소스를 생성하고, `curl -X PUT '{"Status":"SUCCESS"...}'` 신호를 보내야만 WaitCondition 리소스를 "생성 완료"로 인정한다. 그래야 스택 전체가 `CREATE_COMPLETE`로 전이된다.

반대로, `install.sh`가 중간에 실패하면 `FAILURE` 신호가 전송되어 스택은 `CREATE_FAILED`가 되고, 아예 신호가 오지 않으면 33분 후 타임아웃으로 `CREATE_FAILED`가 된다. 따라서 `CREATE_COMPLETE` = "2단계까지 전부 성공"을 보장하는 지표다.

## Outputs 확인

![CloudFormation 출력 탭]({{site.url}}/assets/images/eks-w6-cloudformation-installation-result-01.png){: .align-center width="700"}
<center><sup>CloudFormation 출력 탭 — VsCodeIdeUrl과 VsCodePassword 확인</sup></center>

CloudFormation 콘솔의 "출력" 탭에서 다음을 확인할 수 있다.

| 키 | 값 |
|---|---|
| VsCodeIdeUrl | VS Code 웹 접속 URL |
| VsCodePassword | SSM Parameter Store 콘솔 링크 |

<br>

# 정리

- 전체 소요 시간: ~30분 (대부분 Terraform의 EKS 클러스터 생성에 소요)
- 모니터링 핵심: `tail -f /home/ec2-user/environment/terraform-install.log`
- `CREATE_COMPLETE` 확인 후 바로 VS Code(`http://<EC2 Public DNS>:8080`)에 접속하여 실습을 시작할 수 있다

<br>

