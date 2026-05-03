---
title: "[EKS] GitOps 기반 SaaS: 실습 환경 구성 - 2. install.sh 코드 분석"
excerpt: "EKS SaaS GitOps 워크숍의 2단계 인프라 배포 스크립트(install.sh)를 분석해 보자."
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
  - Flux
  - Gitea
  - VPC-Peering
  - Shell-Script
  - AWS-EKS-Workshop-Study
  - AWS-EKS-Workshop-Study-Week-6
---

*[최영락](https://www.linkedin.com/in/ianychoi/)님의 AWS EKS Workshop Study(AEWS) 6주차 학습 내용을 기반으로 합니다.*

<br>

# TL;DR

- `install.sh`는 [CloudFormation이 EC2 부팅 후 SSM을 통해 자동 실행]({% post_url 2026-04-16-Kubernetes-EKS-GitOps-Saas-01-01-01-Installation-CloudFormation %})하는 2단계 스크립트다
- `main()` 함수가 Terraform을 **7단계**로 나눠서 실행한다
  1. `check_prerequisites` → 도구 확인
  2. `deploy_terraform_infra` → VPC, EKS, Gitea 등 기반 인프라
  3. `create_gitea_repositories` → Gitea 저장소 생성
  4. `apply_flux` → GitOps 인프라 + Flux 설치
  5. `apply_remaining_resources` → 나머지 전체 apply
  6. `print_setup_info` → 접속 정보 출력
  7. `clone_gitea_repos` → Gitea에서 repo clone
- `-target` 옵션으로 Terraform을 단계적으로 apply하는 이유: 리소스 간 의존성 순서를 보장하기 위해서다
- VPC가 2개 생기고 (CFN VPC + Terraform VPC) → VPC Peering(피어링)으로 연결

<br>

# 전체 코드

`install.sh` 전체 코드는 아래 접은 글에서 확인할 수 있다. 

<details markdown="1">
<summary><b>install.sh 전체 코드</b></summary>

```bash
#!/bin/bash
set -e

AWS_REGION=${1:-$(aws configure get region)}
export AWS_REGION

ALLOWED_IP=${2:-""}
export ALLOWED_IP

TERRAFORM_DIR="workshop"

echo "Starting infrastructure-only installation in region: ${AWS_REGION}..."
echo "Using allowed IP for Gitea access: ${ALLOWED_IP}"

check_prerequisites() {
    echo "Checking prerequisites..."

    if ! command -v terraform &> /dev/null
    then
        echo "Terraform is not installed. Please install Terraform first."
        exit 1
    fi

    if ! command -v aws &> /dev/null
    then
        echo "AWS CLI is not installed. Please install AWS CLI first."
        exit 1
    fi

    if [ ! -d "$TERRAFORM_DIR" ]
    then
        echo "Terraform directory '$TERRAFORM_DIR' not found!"
        exit 1
    fi

    REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
    export REPO_ROOT
    echo "Repository root: ${REPO_ROOT}"
}

deploy_terraform_infra() {
    cd "$TERRAFORM_DIR"
    echo "Initializing Terraform..."
    terraform init

    echo "Planning Terraform deployment (infrastructure only) in region: ${AWS_REGION}..."
    export TF_VAR_aws_region="${AWS_REGION}"
    export TF_VAR_allowed_ip="${ALLOWED_IP}"

    terraform plan -target=module.vpc \
                  -target=module.ebs_csi_irsa_role \
                  -target=module.image_automation_irsa_role \
                  -target=module.eks \
                  -target=random_password.gitea_admin \
                  -target=aws_ssm_parameter.gitea_password \
                  -target=module.gitea \
                  -target=aws_vpc_peering_connection.vscode_to_gitea \
                  -target=aws_route.vscode_to_gitea \
                  -target=aws_route.gitea_to_vscode

    echo "Applying Terraform configuration (infrastructure only)..."
    terraform apply -target=module.vpc \
                   -target=module.ebs_csi_irsa_role \
                   -target=module.image_automation_irsa_role \
                   -target=module.eks \
                   -target=random_password.gitea_admin \
                   -target=aws_ssm_parameter.gitea_password \
                   -target=module.gitea \
                   -target=aws_vpc_peering_connection.vscode_to_gitea \
                   -target=aws_route.vscode_to_gitea \
                   -target=aws_route.gitea_to_vscode \
                   -target=kubernetes_namespace.flux_system \
                   --auto-approve

    GITEA_PASSWORD=$(aws ssm get-parameter \
        --name '/eks-saas-gitops/gitea-admin-password' \
        --with-decryption \
        --query 'Parameter.Value' \
        --region "${AWS_REGION}" \
        --output text)

    GITEA_PUBLIC_IP=$(aws ec2 describe-instances \
        --filters "Name=tag:Name,Values=*gitea*" "Name=instance-state-name,Values=running" \
        --query 'Reservations[0].Instances[0].PublicIpAddress' \
        --region "${AWS_REGION}" \
        --output text)

    GITEA_PRIVATE_IP=$(aws ec2 describe-instances \
        --filters "Name=tag:Name,Values=*gitea*" "Name=instance-state-name,Values=running" \
        --query 'Reservations[0].Instances[0].PrivateIpAddress' \
        --region "${AWS_REGION}" \
        --output text)

    echo "Gitea server public IP: ${GITEA_PUBLIC_IP}"
    echo "Gitea server private IP: ${GITEA_PRIVATE_IP}"

    if [ -z "$GITEA_PRIVATE_IP" ] || [ "$GITEA_PRIVATE_IP" == "None" ] || [ "$GITEA_PRIVATE_IP" == "null" ]; then
        echo "ERROR: Could not determine Gitea private IP address. Please check if the Gitea instance is running."
        exit 1
    fi

    echo "Configuring kubectl for region: $AWS_REGION"
    aws eks update-kubeconfig --name eks-saas-gitops --region "$AWS_REGION"
}

create_gitea_repositories() {
    echo "Creating Gitea repositories..."

    terraform apply -target=data.aws_ssm_parameter.gitea_token --auto-approve
    terraform apply -target=gitea_repository.eks-saas-gitops --auto-approve

    echo "Gitea repositories created successfully!"
}

apply_flux() {
    echo "Applying GitOps infrastructure and Flux..."
    terraform apply -target=module.gitops_saas_infra -target=kubernetes_config_map.saas_infra_outputs --auto-approve
    terraform apply -target=null_resource.execute_templating_script --auto-approve
    terraform apply -target=null_resource.execute_setup_repos_script --auto-approve
    terraform apply -target=module.flux_v2 --auto-approve

    sleep 120
    bash quick_fix_flux.sh

    echo "Flux and GitOps infrastructure applied successfully."
}

apply_remaining_resources() {
    echo "Applying remaining Terraform resources..."
    terraform apply --auto-approve

    echo "All Terraform resources created successfully."
}

print_setup_info() {
    echo "=============================="
    echo "Infrastructure Installation Complete!"
    echo "=============================="
    echo "Gitea URL: http://${GITEA_PUBLIC_IP}:3000"
    echo "Gitea Admin Username: admin"
    echo "Gitea Admin Password: ${GITEA_PASSWORD}"
    echo ""
    echo "Your EKS cluster has been configured."
    echo "=============================="
}

clone_gitea_repos() {
    echo "Cloning Gitea repositories..."

    GITEA_TOKEN=$(aws ssm get-parameter \
        --name "/eks-saas-gitops/gitea-flux-token" \
        --with-decryption \
        --query 'Parameter.Value' \
        --region "${AWS_REGION}" \
        --output text)

    TEMP_DIR=$(mktemp -d)
    cd "${TEMP_DIR}"

    echo "Cloning eks-saas-gitops repository..."
    git clone "http://admin:${GITEA_TOKEN}@${GITEA_PRIVATE_IP}:3000/admin/eks-saas-gitops.git"

    cd "${REPO_ROOT}"
    cp -r "${TEMP_DIR}/eks-saas-gitops" ../gitops-gitea-repo

    rm -rf "${TEMP_DIR}"

    echo "Repository cloning completed successfully!"

    echo "Moving eks-saas-gitops up one level"
    cd "${REPO_ROOT}/.."
    mv eks-saas-gitops ../

    echo "Move values.yaml from /home/ec2-user/eks-saas-gitops/helm-charts/helm-tenant-chart/values.yaml to /home/ec2-user/environment/gitops-gitea-repo/helm-charts/helm-tenant-chart"
    cp /home/ec2-user/eks-saas-gitops/helm-charts/helm-tenant-chart/values.yaml /home/ec2-user/environment/gitops-gitea-repo/helm-charts/helm-tenant-chart/
}

main() {
    check_prerequisites
    deploy_terraform_infra
    create_gitea_repositories
    echo "Proceeding with Flux setup..."
    apply_flux
    apply_remaining_resources
    echo "=============================="
    echo "Flux Setup Complete!"
    echo "=============================="
    echo "You can now check the status of Flux with:"
    echo "kubectl get pods -n flux-system"
    echo "=============================="
    print_setup_info
    clone_gitea_repos
}

main
```

</details>

<br>

# main() 흐름

스크립트의 진입점인 `main()` 함수는 7개의 함수를 순차적으로 호출한다.

```
main()
  ├─ check_prerequisites          ← 1
  ├─ deploy_terraform_infra       ← 2
  ├─ create_gitea_repositories    ← 3
  ├─ apply_flux                   ← 4
  ├─ apply_remaining_resources    ← 5
  ├─ print_setup_info             ← 6
  └─ clone_gitea_repos            ← 7
```

각 단계에서 만드는 리소스를 정리하면 아래와 같다.

| 단계 | 함수 | 주요 Terraform target |
|------|------|-----------------------|
| 1 | `check_prerequisites` | (Terraform 실행 아님) terraform/aws CLI, workshop 디렉터리 확인 |
| 2 | `deploy_terraform_infra` | `module.vpc`, `module.eks`, `module.gitea`, VPC Peering, IRSA 역할, `kubernetes_namespace.flux_system` |
| 3 | `create_gitea_repositories` | `data.aws_ssm_parameter.gitea_token`, `gitea_repository.eks-saas-gitops` |
| 4 | `apply_flux` | `module.gitops_saas_infra`, `kubernetes_config_map.saas_infra_outputs`, templating/setup 스크립트, `module.flux_v2` |
| 5 | `apply_remaining_resources` | 남은 **모든** 리소스 — ECR, Karpenter, Kubecost, Metrics Server, Producer/Consumer 이미지 등 |
| 6 | `print_setup_info` | (Terraform 실행 아님) Gitea 접속 정보 출력 |
| 7 | `clone_gitea_repos` | (Terraform 실행 아님) Gitea에서 repo clone → 로컬에 복사 |

<br>

# 함수별 분석

## check_prerequisites

```bash
#!/bin/bash
set -e  # 에러 발생 시 즉시 중단

# 첫 번째 인수로 AWS 리전, 없으면 aws configure에서 가져옴
AWS_REGION=${1:-$(aws configure get region)}
export AWS_REGION

# 두 번째 인수로 Gitea 접근 허용 IP
ALLOWED_IP=${2:-""}
export ALLOWED_IP

TERRAFORM_DIR="workshop"
```

스크립트 시작부에서 `set -e`로 에러 즉시 중단을 설정하고, `AWS_REGION`과 `ALLOWED_IP`를 인수로 받아 환경 변수로 export한다. CloudFormation의 SSM 문서에서 이 스크립트를 호출할 때 리전과 허용 IP를 전달하는 부분이 여기에 연결된다.

```bash
check_prerequisites() {
    # terraform CLI 존재 확인
    if ! command -v terraform &> /dev/null; then
        echo "Terraform is not installed. Please install Terraform first."
        exit 1
    fi

    # aws CLI 존재 확인
    if ! command -v aws &> /dev/null; then
        echo "AWS CLI is not installed. Please install AWS CLI first."
        exit 1
    fi

    # workshop 디렉터리 존재 확인
    if [ ! -d "$TERRAFORM_DIR" ]; then
        echo "Terraform directory '$TERRAFORM_DIR' not found!"
        exit 1
    fi

    # 레포지토리 루트 경로 설정
    REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
    export REPO_ROOT
}
```

`terraform`, `aws` CLI 바이너리가 설치되어 있는지, Terraform 코드가 있는 `workshop` 디렉터리가 존재하는지 확인한다. 이 도구들은 [이전 포스트]({% post_url 2026-04-16-Kubernetes-EKS-GitOps-Saas-01-01-01-Installation-CloudFormation %})에서 본 SSM 부트스트랩 스크립트가 `yum install`과 `curl`로 미리 설치해 둔 것이다.

마지막으로 `REPO_ROOT`를 설정한다. `${BASH_SOURCE[0]}`은 현재 실행 중인 스크립트 파일의 경로로, `install.sh`가 위치한 `terraform/` 디렉터리의 상위, 즉 `/home/ec2-user/environment/eks-saas-gitops`가 된다.

## deploy_terraform_infra

가장 핵심적인 함수다. `-target` 옵션으로 기반 인프라만 먼저 골라서 apply한다.

```bash
deploy_terraform_infra() {
    cd "$TERRAFORM_DIR"
    terraform init

    export TF_VAR_aws_region="${AWS_REGION}"
    export TF_VAR_allowed_ip="${ALLOWED_IP}"

    # plan: 기반 인프라만 대상으로 실행 계획 확인
    terraform plan -target=module.vpc \
                  -target=module.ebs_csi_irsa_role \
                  -target=module.image_automation_irsa_role \
                  -target=module.eks \
                  -target=random_password.gitea_admin \
                  -target=aws_ssm_parameter.gitea_password \
                  -target=module.gitea \
                  -target=aws_vpc_peering_connection.vscode_to_gitea \
                  -target=aws_route.vscode_to_gitea \
                  -target=aws_route.gitea_to_vscode

    # apply: plan과 같은 대상 + kubernetes_namespace.flux_system 추가
    terraform apply -target=module.vpc \
                   -target=module.ebs_csi_irsa_role \
                   -target=module.image_automation_irsa_role \
                   -target=module.eks \
                   -target=random_password.gitea_admin \
                   -target=aws_ssm_parameter.gitea_password \
                   -target=module.gitea \
                   -target=aws_vpc_peering_connection.vscode_to_gitea \
                   -target=aws_route.vscode_to_gitea \
                   -target=aws_route.gitea_to_vscode \
                   -target=kubernetes_namespace.flux_system \ 
                   --auto-approve
    # ...
}
```

눈여겨볼 포인트가 몇 가지 있다.

1. **`plan`과 `apply`의 target이 다르다.**: `kubernetes_namespace.flux_system`은 `apply`에만 포함되어 있다. EKS 클러스터가 먼저 생성되어야 Kubernetes 네임스페이스를 만들 수 있기 때문에, plan 단계에서는 아직 클러스터가 없으므로 빼놓고 apply에서만 추가한 것이다.

2. **`-target` 옵션은 Terraform이 지정된 리소스만 골라서 apply하게 만든다.**: 전체 `terraform apply`를 하면 모든 리소스를 한 번에 만드려고 시도하는데, 리소스 간 의존성이 복잡한 경우 타이밍 이슈가 발생할 수 있다. 여기서는 VPC → EKS → Gitea 순으로 의존성이 있기 때문에 단계를 나눈 것이다.

<br>

apply 후에는 Gitea 서버 정보를 조회하고 kubeconfig를 설정한다. 여기서 SSM Parameter Store에서 비밀번호를 읽어오는데, 이 값은 **방금 위 `terraform apply`에서 생성된 것**이다. `-target` 목록에 포함된 `random_password.gitea_admin`이 랜덤 비밀번호를 생성하고, `aws_ssm_parameter.gitea_password`가 그 값을 SSM에 저장한다. 셸 스크립트는 Terraform이 저장한 값을 다시 읽어와서 이후 `print_setup_info()`에서 출력할 수 있도록 셸 변수에 담는 것이다.

```bash
    # Gitea 관리자 비밀번호를 SSM Parameter Store에서 조회 (위 terraform apply에서 생성·저장된 값)
    GITEA_PASSWORD=$(aws ssm get-parameter \
        --name '/eks-saas-gitops/gitea-admin-password' \
        --with-decryption \
        --query 'Parameter.Value' \
        --region "${AWS_REGION}" \
        --output text)

    # Gitea EC2 인스턴스의 Public/Private IP 조회
    GITEA_PUBLIC_IP=$(aws ec2 describe-instances \
        --filters "Name=tag:Name,Values=*gitea*" "Name=instance-state-name,Values=running" \
        --query 'Reservations[0].Instances[0].PublicIpAddress' \
        --region "${AWS_REGION}" \
        --output text)

    GITEA_PRIVATE_IP=$(aws ec2 describe-instances \
        --filters "Name=tag:Name,Values=*gitea*" "Name=instance-state-name,Values=running" \
        --query 'Reservations[0].Instances[0].PrivateIpAddress' \
        --region "${AWS_REGION}" \
        --output text)

    # kubectl이 새로 만든 EKS 클러스터에 연결되도록 설정
    aws eks update-kubeconfig --name eks-saas-gitops --region "$AWS_REGION"
```

### VPC 2개 구조

이 함수에서 만드는 VPC(`module.vpc`)는 [이전 포스트]({% post_url 2026-04-16-Kubernetes-EKS-GitOps-Saas-01-01-01-Installation-CloudFormation %})에서 CloudFormation이 만든 VPC와는 **별개의 VPC**다. 이 워크숍은 VPC가 2개인 구조로 동작한다.

![VPC 2개 구조]({{site.url}}/assets/images/eks-w6-saas-gitops-vpc-architecture.png){: .align-center}

| 구분 | CFN VPC | Terraform VPC |
|------|---------|---------------|
| CIDR | `10.0.0.0/16` | `module.vpc` 생성 (예: `10.35.0.0/16`) |
| 서브넷 | Public Subnet (VS Code EC2) | Private Subnet (EKS, NAT GW) + Public Subnet (Gitea EC2) |
| 주요 리소스 | VS Code EC2 (code-server :8080), IGW | EKS 클러스터 (노드 + 컨트롤 플레인 ENI), Gitea EC2 (:3000), NAT GW |
| 생성 주체 | CloudFormation (`vs-code-ec2.yaml`) | `install.sh` → `deploy_terraform_infra()` |

VPC Peering(`aws_vpc_peering_connection.vscode_to_gitea`)과 양방향 라우팅(`aws_route.vscode_to_gitea`, `aws_route.gitea_to_vscode`)으로 두 VPC를 연결한다. VS Code EC2의 터미널에서 `kubectl`은 EKS API 엔드포인트로, `git push`는 Gitea의 Private IP(:3000)로 도달한다. EKS 클러스터 안의 Flux source-controller 역시 Gitea의 Private IP로 저장소를 watch한다.

## create_gitea_repositories

```bash
create_gitea_repositories() {
    # Gitea 토큰을 SSM Parameter Store에서 조회
    terraform apply -target=data.aws_ssm_parameter.gitea_token --auto-approve
    # Gitea에 eks-saas-gitops 저장소 생성
    terraform apply -target=gitea_repository.eks-saas-gitops --auto-approve
}
```

Gitea 서버가 떠 있어야 저장소를 만들 수 있으므로, 앞서 `deploy_terraform_infra()`에서 `module.gitea`가 완료된 후에 실행된다. Terraform의 [go-gitea provider](https://registry.terraform.io/providers/go-gitea/gitea/latest/docs)를 사용해 Gitea API로 저장소를 생성한다.

## apply_flux

GitOps 인프라와 Flux를 설치한다. 4개의 `terraform apply`를 순차 실행한다.

```bash
apply_flux() {
    # 1. GitOps SaaS 인프라 모듈 + ConfigMap 생성
    terraform apply -target=module.gitops_saas_infra \
                    -target=kubernetes_config_map.saas_infra_outputs --auto-approve

    # 2. 템플릿 스크립트 실행 (null_resource)
    terraform apply -target=null_resource.execute_templating_script --auto-approve

    # 3. 저장소 셋업 스크립트 실행 (null_resource)
    terraform apply -target=null_resource.execute_setup_repos_script --auto-approve

    # 4. Flux v2 설치
    terraform apply -target=module.flux_v2 --auto-approve

    # Flux 컨트롤러 안정화 대기
    sleep 120
    bash quick_fix_flux.sh
}
```

마지막에 `sleep 120`과 `quick_fix_flux.sh`가 붙어 있다. `module.flux_v2`가 Flux CRD와 컨트롤러 Pod(source-controller, kustomize-controller, helm-controller 등)를 클러스터에 설치하면, Terraform 입장에서는 Kubernetes 리소스가 **생성(created)된 시점에 완료**로 간주한다. 하지만 실제로는 컨트롤러 Pod가 이미지 pull → 컨테이너 시작 → readiness probe 통과 → CRD watch 시작까지 시간이 더 걸린다.

다음 단계인 `apply_remaining_resources()`는 Flux가 **실제로 동작하는 상태를 전제**로 리소스를 만든다. GitRepository, Kustomization, HelmRelease 같은 Flux CR(Custom Resource)을 생성하는데, 이걸 처리할 컨트롤러가 아직 준비 안 되어 있으면 reconcile이 실패하거나 무시될 수 있다. `sleep 120`은 이 간극을 시간으로 메우는 것이고, `quick_fix_flux.sh`는 그래도 타이밍이 안 맞아서 실패 상태에 빠진 HelmRelease를 후처리한다. 

### quick_fix_flux

[실제 스크립트](https://github.com/ianychoi/eks-saas-gitops/blob/README-korean/terraform/workshop/quick_fix_flux.sh)의 동작은 다음과 같다.

```bash
# 1. flux-system 네임스페이스에서 False(실패) 상태의 HelmRelease를 찾는다
kubectl get helmrelease -n flux-system | grep -i 'False'

# 2. 실패한 HelmRelease를 삭제한다
flux delete helmrelease <release-name> -n flux-system --silent

# 3. Git 소스를 재동기화(reconcile)하여 Flux가 다시 시도하게 만든다
flux reconcile source git flux-system -n flux-system
```

부트스트랩 직후 컨트롤러가 미처 준비되지 않은 상태에서 생성된 HelmRelease가 `False`로 빠지면, 이를 삭제하고 reconcile을 트리거해서 Flux가 깨끗한 상태에서 재시도하도록 만드는 것이다.

실습 중 Flux 관련 이상이 보이면 부트스트랩 타이밍 문제일 가능성이 있다. 예를 들어:

- `kubectl get pods -n flux-system`에서 Pod가 `CrashLoopBackOff`이거나 `0/1 Ready`인 경우
- GitRepository 리소스가 `Not Ready` 상태로 source-controller가 Gitea에 연결 못 한 경우
- HelmRelease/Kustomization이 `waiting for source` 상태로 멈춘 경우
- Flux가 배포해야 할 리소스(예: pool-1 네임스페이스)가 클러스터에 없는 경우

이런 증상이 나타나면 바로 설정을 의심하기보다, **`quick_fix_flux.sh` 재실행이나 충분한 시간 대기를 먼저 시도**해 보는 것이 좋다.

## apply_remaining_resources


이전 단계에서 이미 만들어진 리소스는 no-op(변경 없음)으로 넘어가고, 아직 생성되지 않은 나머지 리소스만 만든다. ECR 레포지토리, Karpenter(카펜터), Kubecost(큐브코스트), Metrics Server(메트릭스 서버), Producer/Consumer 컨테이너 이미지 빌드 및 푸시 등이 여기에 해당한다.

```bash
apply_remaining_resources() {
    # -target 없이 전체 대상으로 apply
    terraform apply --auto-approve
}
```

## print_setup_info

설치 완료 후 Gitea 접속 정보(URL, 관리자 계정, 비밀번호)를 출력한다.


```bash
print_setup_info() {
    echo "=============================="
    echo "Infrastructure Installation Complete!"
    echo "=============================="
    echo "Gitea URL: http://${GITEA_PUBLIC_IP}:3000"
    echo "Gitea Admin Username: admin"
    echo "Gitea Admin Password: ${GITEA_PASSWORD}"
    echo ""
    echo "Your EKS cluster has been configured."
    echo "=============================="
}
```

## clone_gitea_repos

마지막 단계다. Terraform이 만든 Gitea 서버에서 `eks-saas-gitops` 저장소를 clone하고, 실습에서 사용할 로컬 작업 디렉터리(`gitops-gitea-repo`)를 구성한다.

```bash
clone_gitea_repos() {
    # SSM에서 Gitea Flux 토큰 조회
    GITEA_TOKEN=$(aws ssm get-parameter \
        --name "/eks-saas-gitops/gitea-flux-token" \
        --with-decryption \
        --query 'Parameter.Value' \
        --region "${AWS_REGION}" \
        --output text)

    TEMP_DIR=$(mktemp -d)
    cd "${TEMP_DIR}"

    # Gitea에서 eks-saas-gitops 저장소를 clone
    git clone "http://admin:${GITEA_TOKEN}@${GITEA_PRIVATE_IP}:3000/admin/eks-saas-gitops.git"

    cd "${REPO_ROOT}"
    cp -r "${TEMP_DIR}/eks-saas-gitops" ../gitops-gitea-repo

    rm -rf "${TEMP_DIR}"

    # Helm 차트용 values.yaml도 복사
    cp /home/ec2-user/eks-saas-gitops/helm-charts/helm-tenant-chart/values.yaml \
       /home/ec2-user/environment/gitops-gitea-repo/helm-charts/helm-tenant-chart/
}
```

여기서 주의할 점은 **clone하는 저장소가 두 종류**라는 것이다.

| 구분 | GitHub clone | Gitea clone |
|------|-------------|-------------|
| 시점 | SSM 부트스트랩 단계 (CloudFormation) | `install.sh` 마지막 단계 |
| 출처 | `github.com/aws-samples/eks-saas-gitops` | Gitea 서버 (`${GITEA_PRIVATE_IP}:3000`) |
| 경로 | `/home/ec2-user/environment/eks-saas-gitops` | `/home/ec2-user/environment/gitops-gitea-repo` |
| 역할 | 원본 소스 코드 (읽기 전용 참조) | **실습용 GitOps 루프의 source** |

참가자가 실습 중 편집하고 `git push`하는 대상은 `/home/ec2-user/environment/gitops-gitea-repo`다. 이 저장소에 push하면 Flux가 변경을 감지하고 EKS에 반영하는 GitOps 루프가 동작한다.

<br>

# Terraform을 나눠서 실행하는 이유

`install.sh`가 `terraform apply`를 `-target`으로 여러 번 나눠서 실행하는 이유가 있다.

- **리소스 간 의존성 순서 보장**: VPC가 있어야 EKS를 만들 수 있고, EKS가 있어야 Kubernetes 리소스를 만들 수 있다
- **Gitea 서버가 먼저 떠야 저장소를 만들 수 있다**: `module.gitea` 완료 → `gitea_repository.eks-saas-gitops` 생성 순서가 필요하다
- **Flux 컨트롤러가 안정화된 후 나머지 리소스를 배포해야 정상 동작한다**: `module.flux_v2` 완료 → `sleep 120` → `quick_fix_flux.sh` → 나머지 apply
- **단일 `terraform apply`로는 타이밍 이슈가 발생할 수 있다**: Terraform이 의존성 그래프를 자체적으로 관리하지만, 외부 시스템(Gitea API, Flux 컨트롤러)의 준비 상태까지는 추적하지 못한다

결국 `install.sh`는 Terraform을 감싸는 오케스트레이션(orchestration) 스크립트 역할을 하면서, Terraform만으로는 해결하기 어려운 **외부 시스템 의존성과 타이밍 제어**를 셸 스크립트 레벨에서 처리하고 있다.

<br>

# 정리

- `install.sh`는 CloudFormation이 트리거하는 **Terraform 오케스트레이션 스크립트**다
- `main()` 함수가 7단계로 나눠서 Terraform을 실행하며, `-target` 옵션으로 의존성 순서를 강제한다
- VPC Peering으로 CFN VPC(VS Code EC2)와 Terraform VPC(EKS + Gitea)를 연결한다
- Flux 부트스트랩 후 타이밍 이슈를 `sleep 120` + `quick_fix_flux.sh`로 처리한다
- 최종 결과: 참가자가 바로 실습을 시작할 수 있는 완전한 GitOps 환경이 구축된다

<br>

