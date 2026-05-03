---
title: "[EKS] EKS 업그레이드: 실습 환경"
excerpt: "AWS EKS 업그레이드 워크숍 실습 환경의 클러스터 구성, 노드, 애드온, 샘플 애플리케이션을 확인해 보자."
categories:
  - Kubernetes
toc: true
header:
  teaser: /assets/images/blog-Dev.jpg
tags:
  - Kubernetes
  - AWS
  - EKS
  - EKS-Upgrade
  - Terraform
  - ArgoCD
  - Karpenter
  - AWS-EKS-Workshop-Study
  - AWS-EKS-Workshop-Study-Week-7
hidden: true
---

*[서종호(가시다)](https://www.linkedin.com/in/gasida99/)님의 AWS EKS Workshop Study(AEWS) 7주차 학습 내용을 기반으로 합니다.*

<br>

# TL;DR

- 실습은 [AWS EKS Cluster Upgrades Workshop](https://catalog.us-east-1.prod.workshops.aws/workshops/fb76a304-9e44-43b9-90b4-5542d4c1b15d)에서 제공하는 사전 구성된 환경에서 진행했다
- 클러스터 버전은 **EKS 1.30**, 업그레이드 목표 버전은 **1.31**이다
- 노드 구성: **Managed Node Group 2개** + **Self-managed Node Group 1개(2노드)** + **Karpenter 노드 1개** + **Fargate 노드 1개** = 총 7노드
- 주요 애드온: ArgoCD, Karpenter, AWS Load Balancer Controller, EFS/EBS CSI Driver, Metrics Server
- 인프라는 **Terraform**으로 관리되며, 애플리케이션은 **ArgoCD(GitOps)**로 배포된다
- EKS Upgrade Insights 5개 항목 **모두 PASSING** — 1.31 업그레이드에 문제 없는 상태

<br>

# 실습 환경 개요

이 실습은 AWS Workshop Studio에서 제공하는 사전 구성된 환경에서 진행했다. 환경에는 AWS 계정, EKS 클러스터, VSCode IDE가 포함되어 있으며, 별도의 인프라 구축 없이 바로 실습을 시작할 수 있다.

> 이 글에서는 실습 환경 구축 과정은 다루지 않는다. 대신, 업그레이드를 진행하기 전에 알아두어야 할 **현재 클러스터의 구성 상태**를 확인하는 데 집중한다.

<br>

# 클러스터 기본 정보

## 클러스터 버전

```bash
# 클러스터 버전 확인
~$ kubectl version
Client Version: v1.31.0
Kustomize Version: v5.4.2
Server Version: v1.30.14-eks-bbe087e
```

| 항목 | 값 |
|------|-----|
| 클러스터 이름 | eksworkshop-eksctl |
| K8s 버전 | 1.30 |
| 리전 | us-west-2 |
| 엔드포인트 접근 | Public + Private |
| 인증 모드 | API_AND_CONFIG_MAP |
| Secrets 암호화 | KMS 활성화 |
| 지원 정책 | EXTENDED |

<details markdown="1">
<summary><b>aws eks describe-cluster 전체 출력</b></summary>

```json
{
    "cluster": {
        "name": "eksworkshop-eksctl",
        "arn": "arn:aws:eks:us-west-2:123456789012:cluster/eksworkshop-eksctl",
        "createdAt": "2026-04-29T08:21:31.122000+00:00",
        "version": "1.30",
        "endpoint": "https://EXAMPLE1234567890.yl4.us-west-2.eks.amazonaws.com",
        "roleArn": "arn:aws:iam::123456789012:role/eksworkshop-eksctl-cluster-20260429082059967600000002",
        "resourcesVpcConfig": {
            "subnetIds": [
                "subnet-0example1",
                "subnet-0example2",
                "subnet-0example3"
            ],
            "clusterSecurityGroupId": "sg-0example",
            "vpcId": "vpc-0example",
            "endpointPublicAccess": true,
            "endpointPrivateAccess": true
        },
        "kubernetesNetworkConfig": {
            "serviceIpv4Cidr": "172.20.0.0/16",
            "ipFamily": "ipv4"
        },
        "status": "ACTIVE",
        "platformVersion": "eks.65",
        "tags": {
            "karpenter.sh/discovery": "eksworkshop-eksctl",
            "terraform-aws-modules": "eks",
            "Blueprint": "eksworkshop-eksctl"
        },
        "encryptionConfig": [
            {
                "resources": ["secrets"],
                "provider": {
                    "keyArn": "arn:aws:kms:us-west-2:123456789012:key/example-key-id"
                }
            }
        ],
        "accessConfig": {
            "authenticationMode": "API_AND_CONFIG_MAP"
        },
        "upgradePolicy": {
            "supportType": "EXTENDED"
        }
    }
}
```

</details>

<br>

# 노드 구성

클러스터에는 총 7개의 노드가 다양한 방식으로 프로비저닝되어 있다.

```bash
# 노드 목록 및 노드 그룹/풀 확인
~$ kubectl get node -L eks.amazonaws.com/nodegroup,karpenter.sh/nodepool
```

| 노드 | 버전 | 유형 | 노드 그룹/풀 | 용도 |
|------|------|------|-------------|------|
| fargate-ip-10-0-15-170 | v1.30.14-eks-d6694b8 | Fargate | - | ArgoCD 등 |
| ip-10-0-15-169 | v1.30.14-eks-40737a8 | Managed Node Group | initial-* | 범용 워크로드 |
| ip-10-0-32-13 | v1.30.14-eks-40737a8 | Managed Node Group | initial-* | 범용 워크로드 |
| ip-10-0-6-74 | v1.30.14-eks-40737a8 | Managed Node Group | blue-mng-* | Orders 전용 (taint/toleration) |
| ip-10-0-22-47 | v1.30.14-eks-f69f56f | Self-managed | - | Carts 전용 (label: team=carts) |
| ip-10-0-35-24 | v1.30.14-eks-f69f56f | Self-managed | - | Carts 전용 (label: team=carts) |
| ip-10-0-19-61 | v1.30.14-eks-f69f56f | Karpenter | default | Checkout 전용 (label: team=checkout) |

이처럼 **5가지 서로 다른 노드 프로비저닝 방식**(Managed Node Group 2종, Self-managed, Karpenter, Fargate)이 혼재하는 구성이다. 업그레이드 시 각 유형별로 다른 방법을 적용해야 하므로, 이 구성을 사전에 파악하는 것이 중요하다.

<br>

# 설치된 애드온 및 Helm 차트

```bash
~$ helm list -A
```

| 이름 | 네임스페이스 | Chart 버전 | 앱 버전 |
|------|-------------|-----------|---------|
| argo-cd | argocd | argo-cd-5.55.0 | v2.10.0 |
| aws-efs-csi-driver | kube-system | aws-efs-csi-driver-2.5.6 | 1.7.6 |
| aws-load-balancer-controller | kube-system | aws-load-balancer-controller-1.7.1 | v2.7.1 |
| karpenter | karpenter | karpenter-1.0.0 | 1.0.0 |
| metrics-server | kube-system | metrics-server-3.12.0 | 0.7.0 |

EKS 관리형 애드온도 별도로 설치되어 있다.

| 애드온 | 버전 | 상태 |
|--------|------|------|
| aws-ebs-csi-driver | v1.59.0-eksbuild.1 | ACTIVE |
| coredns | v1.11.4-eksbuild.32 | ACTIVE |
| kube-proxy | v1.30.14-eksbuild.28 | ACTIVE |
| vpc-cni | v1.21.1-eksbuild.7 | ACTIVE |

<br>

# 샘플 애플리케이션

워크숍에서는 **Retail Store** 샘플 애플리케이션을 사용한다. 고객이 카탈로그를 탐색하고, 장바구니에 담고, 체크아웃하는 간단한 웹 스토어 구조다.

![샘플 애플리케이션 구성도]({{site.url}}/assets/images/eks-upgrade-sample-app-architecture.png){: .align-center}

| 컴포넌트 | 설명 | 네임스페이스 |
|----------|------|-------------|
| UI | 프론트엔드 UI, 다른 서비스에 대한 API 호출 집약 | ui |
| Catalog | 상품 목록 및 상세 API | catalog |
| Cart | 장바구니 API | carts |
| Checkout | 체크아웃 프로세스 오케스트레이션 API | checkout |
| Orders | 주문 접수 및 처리 API | orders |
| Static Assets | 상품 카탈로그 이미지 등 정적 리소스 제공 | assets |

모든 컴포넌트는 **ArgoCD**를 통해 AWS CodeCommit Git 저장소에서 배포된다.

![ArgoCD 콘솔 접속 시 인증서 경고]({{site.url}}/assets/images/eks-upgrade-argocd-cert-warning.png){: .align-center}
<center><sup>ArgoCD 콘솔에 처음 접속하면 Self-signed 인증서로 인해 브라우저 경고가 뜬다. 고급 옵션을 눌러 이동하면 된다.</sup></center>

ArgoCD 콘솔에 접속하려면 먼저 서버 URL과 초기 관리자 비밀번호를 확인한다.

```bash
# ArgoCD 서버 URL 확인
~$ export ARGOCD_SERVER=$(kubectl get svc argo-cd-argocd-server -n argocd \
    -o json | jq --raw-output '.status.loadBalancer.ingress[0].hostname')
~$ echo "ArgoCD URL: http://${ARGOCD_SERVER}"

# 초기 관리자 비밀번호 확인
~$ export ARGOCD_PWD=$(kubectl -n argocd get secret argocd-initial-admin-secret \
    -o jsonpath="{.data.password}" | base64 -d)
~$ echo "Username: admin"
~$ echo "Password: ${ARGOCD_PWD}"
```

CLI 로그인도 가능하다.

```bash
~$ argocd login ${ARGOCD_SERVER} \
    --username admin --password ${ARGOCD_PWD} \
    --insecure --skip-test-tls --grpc-web

# 실행 결과
'admin:login' logged in successfully
```

![ArgoCD 콘솔 - 애플리케이션 목록]({{site.url}}/assets/images/eks-upgrade-argocd-console.png){: .align-center}

<br>

# 인프라 구성 (Terraform)

실습 환경의 인프라는 Terraform으로 관리된다. `terraform/` 디렉토리에 주요 설정 파일이 위치한다.

| 파일 | 역할 |
|------|------|
| `base.tf` | EKS 클러스터 및 노드 그룹 정의 |
| `addons.tf` | EKS 애드온 및 Helm 차트 설정 |
| `variables.tf` | 클러스터 버전 등 변수 정의 |
| `vpc.tf` | VPC 네트워크 설정 |
| `gitops-setup.tf` | ArgoCD 및 CodeCommit 설정 |

업그레이드 실습에서는 주로 `variables.tf`의 `cluster_version` 변수와 `addons.tf`의 애드온 버전을 수정하게 된다.

<br>

# Upgrade Insights 확인

업그레이드를 시작하기 전에, [EKS Upgrade Insights]({% post_url 2026-04-23-Kubernetes-EKS-Upgrade-01-02-Preparation %}#eks-upgrade-insights)를 통해 클러스터의 업그레이드 준비 상태를 점검한다. Upgrade Insights가 무엇이고 어떤 항목을 검사하는지는 [업그레이드 준비]({% post_url 2026-04-23-Kubernetes-EKS-Upgrade-01-02-Preparation %}) 포스트에서 다뤘다.

대상 버전(1.31)에 대한 Insights를 조회해 보자.

```bash
~$ aws eks list-insights \
    --filter kubernetesVersions=1.31 \
    --cluster-name $CLUSTER_NAME | jq .
```

<details markdown="1">
<summary><b>Upgrade Insights 전체 출력</b></summary>

```json
{
  "insights": [
    {
      "id": "37c3aa7e-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
      "name": "EKS add-on version compatibility",
      "category": "UPGRADE_READINESS",
      "kubernetesVersion": "1.31",
      "lastRefreshTime": "2026-05-01T00:47:46+00:00",
      "lastTransitionTime": "2026-04-29T08:37:45+00:00",
      "description": "Checks version of installed EKS add-ons to ensure they are compatible with the next version of Kubernetes.",
      "insightStatus": {
        "status": "PASSING",
        "reason": "All installed EKS add-on versions are compatible with next Kubernetes version."
      }
    },
    {
      "id": "2b599880-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
      "name": "Cluster health issues",
      "category": "UPGRADE_READINESS",
      "kubernetesVersion": "1.31",
      "lastRefreshTime": "2026-05-01T00:47:46+00:00",
      "lastTransitionTime": "2026-04-29T08:37:45+00:00",
      "description": "Checks for any cluster health issues that prevent successful upgrade to the next Kubernetes version on EKS.",
      "insightStatus": {
        "status": "PASSING",
        "reason": "No cluster health issues detected."
      }
    },
    {
      "id": "4072fb48-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
      "name": "kube-proxy version skew",
      "category": "UPGRADE_READINESS",
      "kubernetesVersion": "1.31",
      "lastRefreshTime": "2026-05-01T00:47:46+00:00",
      "lastTransitionTime": "2026-04-29T08:37:45+00:00",
      "description": "Checks version of kube-proxy in cluster to see if upgrade would cause non compliance with supported Kubernetes kube-proxy version skew policy.",
      "insightStatus": {
        "status": "PASSING",
        "reason": "kube-proxy versions match the cluster control plane version."
      }
    },
    {
      "id": "b3cb48bf-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
      "name": "Kubelet version skew",
      "category": "UPGRADE_READINESS",
      "kubernetesVersion": "1.31",
      "lastRefreshTime": "2026-05-01T00:47:46+00:00",
      "lastTransitionTime": "2026-04-29T08:37:45+00:00",
      "description": "Checks for kubelet versions of worker nodes in the cluster to see if upgrade would cause non compliance with supported Kubernetes kubelet version skew policy.",
      "insightStatus": {
        "status": "PASSING",
        "reason": "Node kubelet versions match the cluster control plane version."
      }
    },
    {
      "id": "e925e73f-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
      "name": "Amazon Linux 2 compatibility",
      "category": "UPGRADE_READINESS",
      "kubernetesVersion": "1.31",
      "lastRefreshTime": "2026-05-01T00:47:46+00:00",
      "lastTransitionTime": "2026-04-29T08:37:45+00:00",
      "description": "Checks if any nodes in the cluster are running Amazon Linux 2.",
      "insightStatus": {
        "status": "PASSING",
        "reason": "No Amazon Linux 2 nodes detected."
      }
    }
  ]
}
```

</details>

5개 항목 모두 **PASSING** 상태다. 각 항목별 결과를 정리하면 다음과 같다.

| Insight | 상태 | 설명 |
|---------|------|------|
| EKS add-on version compatibility | PASSING | 설치된 EKS 애드온 버전이 1.31과 호환 |
| Cluster health issues | PASSING | 업그레이드를 방해하는 클러스터 상태 이상 없음 |
| kube-proxy version skew | PASSING | kube-proxy 버전이 Control Plane 버전과 일치 |
| Kubelet version skew | PASSING | 워커 노드 kubelet 버전이 Control Plane 버전과 일치 |
| Amazon Linux 2 compatibility | PASSING | AL2 노드 없음 (AL2 지원 종료 대비) |

모든 Insight가 PASSING이므로, 1.31로의 업그레이드를 진행해도 문제가 없는 상태다. 만약 여기서 ERROR나 WARNING이 있었다면, [업그레이드 준비]({% post_url 2026-04-23-Kubernetes-EKS-Upgrade-01-02-Preparation %}) 포스트에서 설명한 대로 Deprecated API 마이그레이션(`kubectl-convert`), 애드온 버전 업데이트 등의 사전 조치가 필요했을 것이다.

<br>

# 정리

업그레이드를 시작하기 전에 파악해야 할 현재 클러스터 상태를 요약하면 다음과 같다.

| 항목 | 현재 상태 |
|------|-----------|
| EKS 버전 | 1.30 (목표: 1.31) |
| 노드 수 | 7개 (5가지 프로비저닝 방식 혼재) |
| 핵심 애드온 | coredns, kube-proxy, vpc-cni, ebs-csi-driver |
| 운영 도구 | ArgoCD, Karpenter, ALB Controller, Metrics Server |
| 인프라 관리 | Terraform |
| 배포 관리 | ArgoCD (GitOps) |
| Upgrade Insights | 5개 항목 모두 PASSING |

다음 글부터 본격적으로 In-Place 업그레이드를 실습한다. 먼저 Control Plane 업그레이드부터 시작한다.

<br>

# 참고 링크

- [AWS EKS Cluster Upgrades Workshop](https://catalog.us-east-1.prod.workshops.aws/workshops/fb76a304-9e44-43b9-90b4-5542d4c1b15d)
- [Retail Store Sample App (GitHub)](https://github.com/aws-containers/retail-store-sample-app)
- [EKS Terraform Blueprints](https://github.com/aws-ia/terraform-aws-eks-blueprints)

<br>