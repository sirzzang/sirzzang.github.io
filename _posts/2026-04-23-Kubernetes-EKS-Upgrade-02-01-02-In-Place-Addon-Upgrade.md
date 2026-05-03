---
title: "[EKS] EKS 업그레이드: In-Place 실습 - EKS 애드온 업그레이드"
excerpt: "Control Plane 업그레이드 후, Terraform을 이용해 CoreDNS, kube-proxy, VPC CNI 등 EKS 애드온을 업그레이드해 보자."
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
  - CoreDNS
  - kube-proxy
  - VPC-CNI
  - AWS-EKS-Workshop-Study
  - AWS-EKS-Workshop-Study-Week-7
hidden: true
---

*[서종호(가시다)](https://www.linkedin.com/in/gasida99/)님의 AWS EKS Workshop Study(AEWS) 7주차 학습 내용을 기반으로 합니다.*

<br>

# TL;DR

- Control Plane 업그레이드 후, 클러스터에 설치된 **EKS 애드온**도 함께 업그레이드해야 한다
- 이 실습에서 업그레이드하는 애드온: **CoreDNS**, **kube-proxy**, **VPC CNI**
- `aws eks describe-addon-versions` 명령으로 대상 K8s 버전에 호환되는 애드온 버전을 확인할 수 있다
- Terraform의 `addons.tf`에서 버전을 변경하고 `terraform apply`로 업그레이드를 적용한다
- 업그레이드 후 다른 애드온(EBS CSI Driver, EFS CSI Driver, AWS Load Balancer Controller 등)도 호환성을 확인해야 한다

<br>

# EKS 애드온이란

EKS 애드온(Add-on)은 Kubernetes 애플리케이션에 운영 지원 기능을 제공하는 소프트웨어다. 옵저버빌리티 에이전트, 네트워킹/컴퓨팅/스토리지를 위한 Kubernetes 드라이버 등이 포함된다. 일반적으로 Kubernetes 커뮤니티, AWS 같은 클라우드 프로바이더, 또는 서드파티 벤더가 개발하고 유지보수한다.

Amazon EKS 애드온을 사용하면 클러스터의 보안과 안정성을 일관되게 유지할 수 있으며, 설치/설정/업데이트에 드는 작업량을 줄일 수 있다.

> 전체 EKS 애드온 목록은 [Amazon EKS add-ons](https://docs.aws.amazon.com/eks/latest/userguide/eks-add-ons.html#workloads-add-ons-available-eks) 문서를 참고하자.

<br>

# 현재 설치된 애드온 확인

업그레이드 전에 먼저 현재 클러스터에 설치된 애드온과 버전을 확인한다.

```bash
# 설치된 EKS 애드온 목록 확인
~$ eksctl get addon --cluster $CLUSTER_NAME
```

| 애드온 | 현재 버전 | 상태 | 업데이트 가능 버전 |
|--------|-----------|------|-------------------|
| aws-ebs-csi-driver | v1.59.0-eksbuild.1 | ACTIVE | - |
| coredns | v1.11.4-eksbuild.32 | ACTIVE | - |
| kube-proxy | v1.30.14-eksbuild.28 | ACTIVE | v1.31.x 다수 |
| vpc-cni | v1.21.1-eksbuild.7 | ACTIVE | - |

Control Plane을 1.31로 업그레이드한 후, kube-proxy에 업데이트 가능한 버전이 표시되는 것을 확인할 수 있다. 이 실습에서는 **CoreDNS**, **kube-proxy**, **VPC CNI** 세 가지를 업그레이드한다.

<br>

# 호환 버전 확인

EKS는 대상 K8s 버전에 호환되는 애드온 버전 목록을 API로 제공한다. 각 애드온별로 확인해 보자.

## CoreDNS

```bash
~$ aws eks describe-addon-versions \
    --addon-name coredns \
    --kubernetes-version 1.31 \
    --output table \
    --query "addons[].addonVersions[:10].{Version:addonVersion,DefaultVersion:compatibilities[0].defaultVersion}"
```

```text
-------------------------------------------
|          DescribeAddonVersions          |
+-----------------+-----------------------+
| DefaultVersion  |        Version        |
+-----------------+-----------------------+
|  True           |  v1.11.4-eksbuild.33  |
|  False          |  v1.11.4-eksbuild.32  |
|  ...            |  ...                  |
+-----------------+-----------------------+
```

`DefaultVersion`이 `True`인 버전이 해당 K8s 버전의 기본 권장 버전이다.

## kube-proxy

```bash
~$ aws eks describe-addon-versions \
    --addon-name kube-proxy \
    --kubernetes-version 1.31 \
    --output table \
    --query "addons[].addonVersions[:10].{Version:addonVersion,DefaultVersion:compatibilities[0].defaultVersion}"
```

```text
-------------------------------------------
|          DescribeAddonVersions          |
+-----------------+------------------------+
| DefaultVersion  |        Version         |
+-----------------+------------------------+
|  False          |  v1.31.14-eksbuild.9   |
|  ...            |  ...                   |
|  True           |  v1.31.10-eksbuild.12  |
|  ...            |  ...                   |
+-----------------+------------------------+
```

kube-proxy는 K8s 마이너 버전에 맞춰 `v1.31.x` 계열로 업그레이드해야 한다.

## VPC CNI

```bash
~$ aws eks describe-addon-versions \
    --addon-name vpc-cni \
    --kubernetes-version 1.31 \
    --output table \
    --query "addons[].addonVersions[:10].{Version:addonVersion,DefaultVersion:compatibilities[0].defaultVersion}"
```

> VPC CNI는 한 번에 1 마이너 버전만 업그레이드할 수 있으므로, 현재 버전과 대상 버전 사이의 간격을 확인해야 한다.

호환 버전 확인은 다음 문서에서도 가능하다.

| 애드온 | 호환성 문서 |
|--------|------------|
| CoreDNS | [CoreDNS 관리](https://docs.aws.amazon.com/eks/latest/userguide/managing-coredns.html) |
| kube-proxy | [kube-proxy 관리](https://docs.aws.amazon.com/eks/latest/userguide/managing-kube-proxy.html) |
| VPC CNI | [VPC CNI 관리](https://docs.aws.amazon.com/eks/latest/userguide/managing-vpc-cni.html) |

<br>

# 트러블슈팅: Terraform 변수 미동기화

## 증상

애드온 업그레이드를 위해 `terraform apply`를 실행했는데, 애드온이 아닌 **클러스터 버전 다운그레이드** 에러가 발생하는 경우가 있다.

```bash
~$ terraform apply -auto-approve

# 실행 결과
module.eks.aws_eks_cluster.this[0]: Modifying... [id=eksworkshop-eksctl]
╷
│ Error: updating EKS Cluster (eksworkshop-eksctl) version:
│ operation error EKS: UpdateClusterVersion,
│ https response error StatusCode: 400,
│ RequestID: e8e17103-xxxx-xxxx-xxxx-xxxxxxxxxxxx,
│ InvalidParameterException:
│ Unsupported Kubernetes minor version update from 1.31 to 1.30
│
│   with module.eks.aws_eks_cluster.this[0],
│   on .terraform/modules/eks/main.tf line 35, in resource "aws_eks_cluster" "this":
│   35: resource "aws_eks_cluster" "this" {
│
╵
```

## 원인

[Control Plane 업그레이드 글]({% post_url 2026-04-23-Kubernetes-EKS-Upgrade-02-01-01-In-Place-Control-Plane-Upgrade %})에서도 다뤘지만, Control Plane을 CLI나 콘솔로 먼저 1.31로 업그레이드한 뒤, `variables.tf`의 `cluster_version`을 `"1.30"`으로 남겨두면 발생한다. Terraform이 현재 상태(1.31)와 desired 상태(1.30)의 차이를 감지하고 다운그레이드를 시도하지만, EKS는 다운그레이드를 지원하지 않으므로 에러가 발생한다.

워크숍 진행 흐름에서 이 문제가 발생하는 시나리오는 다음과 같다.

1. 클러스터가 **v1.30**으로 프로비저닝됨
2. In-Place 업그레이드 실습에서 Control Plane을 **CLI로** 1.31로 업그레이드
3. 이후 애드온 업그레이드를 위해 `addons.tf`만 수정하고 `terraform apply` 실행
4. Terraform이 `variables.tf`의 `cluster_version = "1.30"`을 보고 다운그레이드를 시도 → 에러

## 해결

`terraform/variables.tf`에서 `cluster_version`을 현재 클러스터 버전 이상으로 맞춘다.

```hcl
variable "cluster_version" {
  description = "EKS cluster version."
  type        = string
  default     = "1.31"
}
```

> Control Plane 업그레이드와 Terraform 변수 변경은 항상 **함께** 수행해야 한다. 콘솔/CLI로 먼저 업그레이드한 뒤 Terraform 변수를 업데이트하지 않으면, 이후 어떤 `terraform apply`에서든 이 drift 에러가 발생한다.

<br>

# 실습: Terraform으로 애드온 업그레이드

## 1단계: addons.tf 수정

호환 버전을 확인한 후, `terraform/addons.tf` 파일에서 각 애드온의 버전을 업데이트한다.

![addons.tf 수정 화면]({{site.url}}/assets/images/eks-upgrade-terraform-addons-tf.png){: .align-center}

확인한 최신 호환 버전으로 CoreDNS, kube-proxy, VPC CNI의 버전을 수정한다.

## 2단계: Terraform Plan 및 Apply

```bash
~$ cd ~/environment/terraform
~$ terraform plan
~$ terraform apply -auto-approve
```

`terraform plan`에서 애드온 버전 변경에 따른 업데이트 계획이 표시된다. 확인 후 `terraform apply`를 실행하면 애드온 업그레이드가 진행된다.

## 3단계: 업그레이드 확인

```bash
# 업그레이드 후 애드온 상태 확인
~$ eksctl get addon --cluster $CLUSTER_NAME
```

각 애드온의 버전이 의도한 대로 업데이트되었는지, 상태가 ACTIVE인지 확인한다.

<details markdown="1">
<summary><b>실습 CLI 전체 출력</b></summary>

```bash
# 업그레이드 전 상태
~$ eksctl get addon --cluster $CLUSTER_NAME
2026-05-01 14:11:36 [i]  Kubernetes version "1.31" in use by cluster "eksworkshop-eksctl"
2026-05-01 14:11:36 [i]  getting all addons
NAME                    VERSION                 STATUS     ISSUES
aws-ebs-csi-driver      v1.59.0-eksbuild.1      ACTIVE     0
coredns                 v1.11.4-eksbuild.32     ACTIVE     0
kube-proxy              v1.30.14-eksbuild.28    ACTIVE     0
vpc-cni                 v1.21.1-eksbuild.7      ACTIVE     0

# coredns 호환 버전 확인
~$ aws eks describe-addon-versions \
    --addon-name coredns \
    --kubernetes-version 1.31 \
    --output table \
    --query "addons[].addonVersions[:10].{Version:addonVersion,DefaultVersion:compatibilities[0].defaultVersion}"
-------------------------------------------
|          DescribeAddonVersions          |
+-----------------+-----------------------+
| DefaultVersion  |        Version        |
+-----------------+-----------------------+
|  True           |  v1.11.4-eksbuild.33  |
|  False          |  v1.11.4-eksbuild.32  |
|  False          |  v1.11.4-eksbuild.28  |
|  False          |  v1.11.4-eksbuild.24  |
|  False          |  v1.11.4-eksbuild.22  |
|  False          |  v1.11.4-eksbuild.20  |
|  False          |  v1.11.4-eksbuild.14  |
|  False          |  v1.11.4-eksbuild.10  |
|  False          |  v1.11.4-eksbuild.2   |
|  False          |  v1.11.4-eksbuild.1   |
+-----------------+-----------------------+

# kube-proxy 호환 버전 확인
~$ aws eks describe-addon-versions \
    --addon-name kube-proxy \
    --kubernetes-version 1.31 \
    --output table \
    --query "addons[].addonVersions[:10].{Version:addonVersion,DefaultVersion:compatibilities[0].defaultVersion}"
-------------------------------------------
|          DescribeAddonVersions          |
+-----------------+------------------------+
| DefaultVersion  |        Version         |
+-----------------+------------------------+
|  False          |  v1.31.14-eksbuild.9   |
|  False          |  v1.31.14-eksbuild.6   |
|  False          |  v1.31.14-eksbuild.5   |
|  False          |  v1.31.14-eksbuild.2   |
|  False          |  v1.31.13-eksbuild.2   |
|  True           |  v1.31.10-eksbuild.12  |
|  False          |  v1.31.10-eksbuild.8   |
|  False          |  v1.31.10-eksbuild.6   |
|  False          |  v1.31.10-eksbuild.2   |
|  False          |  v1.31.9-eksbuild.2    |
+-----------------+------------------------+
```

</details>

<br>

# 추가 애드온 확인

이 실습에서는 CoreDNS, kube-proxy, VPC CNI 세 가지만 업그레이드했지만, 실제 운영 환경에서는 다른 애드온도 반드시 확인해야 한다.

| 애드온 | 확인 사항 |
|--------|-----------|
| AWS EBS CSI Driver | K8s 버전 호환성 확인 |
| AWS EFS CSI Driver | K8s 버전 호환성 확인 |
| AWS Load Balancer Controller | [지원 K8s 버전 목록](https://kubernetes-sigs.github.io/aws-load-balancer-controller/latest/deploy/installation/#supported-kubernetes-versions) 확인 |
| Karpenter | [Karpenter 문서](https://karpenter.sh/docs/getting-started/getting-started-with-karpenter/)에서 호환 버전 확인 |
| Metrics Server | [GitHub](https://github.com/kubernetes-sigs/metrics-server)에서 호환 버전 확인 |

> 업그레이드 후에는 애드온의 로그와 메트릭을 모니터링하여 정상 동작하는지 확인해야 한다.

<br>

# 정리

Control Plane 업그레이드에 이어 EKS 애드온 업그레이드를 완료했다. In-Place 업그레이드의 전체 진행 상황은 다음과 같다.

| 단계 | 상태 |
|------|------|
| Control Plane 업그레이드 (1.30 → 1.31) | 완료 |
| **EKS 애드온 업그레이드** | **완료 (이 글)** |
| EKS Managed Node Group 업그레이드 | 다음 글 |
| Karpenter Managed 노드 업그레이드 | 다음 글 |

다음 글에서는 Data Plane의 **EKS Managed Node Group 업그레이드**를 진행한다.

<br>

# 참고 링크

- [Amazon EKS add-ons](https://docs.aws.amazon.com/eks/latest/userguide/eks-add-ons.html)
- [Managing CoreDNS](https://docs.aws.amazon.com/eks/latest/userguide/managing-coredns.html)
- [Managing kube-proxy](https://docs.aws.amazon.com/eks/latest/userguide/managing-kube-proxy.html)
- [Managing VPC CNI](https://docs.aws.amazon.com/eks/latest/userguide/managing-vpc-cni.html)

<br>
