---
title:  "[EKS] EKS: Public-Public EKS 클러스터 - 4. 클러스터 구성 요소 확인"
excerpt: "EKS 클러스터의 구성 요소를 확인하고, 온프레미스 Kubernetes와의 구조적 차이를 분석해보자."
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
  - VPC-CNI
  - CoreDNS
  - kube-proxy
  - AWS-EKS-Workshop-Study
  - AWS-EKS-Workshop-Study-Week-1

---

*[서종호(가시다)](https://www.linkedin.com/in/gasida99/)님의 AWS EKS Workshop Study(AEWS) 1주차 학습 내용을 기반으로 합니다.*

<br>

# TL;DR

이번 글에서는 Terraform으로 배포한 EKS 클러스터의 **구성 요소**를 확인하고, 온프레미스 Kubernetes와의 구조적 차이를 확인해 본다.

- **클러스터 설정**: `aws eks describe-cluster`로 IAM Role, OIDC, KMS 암호화, Service CIDR 등 주요 설정 확인
- **노드**: 관리형 노드 그룹의 스케일링·AMI·롤링 업데이트 설정, EKS 고유 라벨 확인
- **시스템 파드**: 온프레미스와 달리 컨트롤 플레인 컴포넌트(API Server, etcd 등)가 보이지 않고, `aws-node`(VPC CNI)가 추가됨
- **이미지 레지스트리**: 모든 시스템 이미지가 `registry.k8s.io`가 아닌 AWS ECR에서 제공됨
- **EKS Add-on**: CoreDNS, kube-proxy, VPC CNI를 AWS가 버전 관리

<br>


# 들어가며

[이전 글]({% post_url 2026-03-12-Kubernetes-EKS-01-01-03-Kubeconfig-Authentication %})에서 kubeconfig를 설정하고 EKS API 서버의 IAM 기반 인증 구조를 확인했다. `kubectl get nodes`로 워커 노드 2대가 `Ready` 상태인 것을 확인했으니, 이번 글에서는 클러스터의 **구성 요소**를 확인한다.

온프레미스에서는 배포 후 컨트롤 플레인 컴포넌트(Static Pod, systemd 서비스), 인증서, kubeconfig, CNI 설정 등을 직접 확인했다. EKS에서는 컨트롤 플레인이 AWS 관리 영역에 있으므로, **사용자에게 보이는 것과 보이지 않는 것**이 명확히 나뉜다. 이 차이를 의식하면서 확인해 보자.

<br>

# 클러스터 정보 확인

## kubectl cluster-info

```bash
kubectl cluster-info
```

```
Kubernetes control plane is running at https://461A1FA....gr7.ap-northeast-2.eks.amazonaws.com
CoreDNS is running at https://461A1FA....gr7.ap-northeast-2.eks.amazonaws.com/api/v1/namespaces/kube-system/services/kube-dns:dns/proxy

To further debug and diagnose cluster problems, use 'kubectl cluster-info dump'.
```

온프레미스에서 `kubectl cluster-info`를 실행하면 API 서버 주소가 `https://192.168.10.100:6443`처럼 컨트롤 플레인 노드의 IP와 포트로 나왔다. EKS에서는 `461A1FA....gr7.ap-northeast-2.eks.amazonaws.com`이라는 도메인이 나온다.

| 부분 | 의미 |
| --- | --- |
| `461A1FA...` | 클러스터별로 생성되는 **고유 해시 식별자**. <br>EKS가 멀티테넌트로 운영되므로 각 클러스터 API 엔드포인트를 구분하기 위해 사용. <br>클러스터 이름을 직접 노출하지 않는 보안 효과도 있음 |
| `gr7` | EKS 내부 리전 식별자 |
| `ap-northeast-2` | AWS 리전 (서울) |
| `eks.amazonaws.com` | EKS 서비스 도메인 |

<br>

## aws eks describe-cluster

AWS CLI로 클러스터의 전체 설정을 조회한다.

```bash
CLUSTER_NAME=myeks
aws eks describe-cluster --name $CLUSTER_NAME | jq
```

<details markdown="1">
<summary>전체 출력</summary>

```json
{
  "cluster": {
    "name": "myeks",
    "arn": "arn:aws:eks:ap-northeast-2:988608581192:cluster/myeks",
    "createdAt": "2026-03-13T22:57:12.819000+09:00",
    "version": "1.34",
    "endpoint": "https://461A1FA....gr7.ap-northeast-2.eks.amazonaws.com",
    "roleArn": "arn:aws:iam::988608581192:role/myeks-cluster-20260313135647575900000001",
    "resourcesVpcConfig": {
      "subnetIds": [
        "subnet-09ff80d6277d22372",
        "subnet-0e89ca3e59aabe395",
        "subnet-04b03277d6d97e07c"
      ],
      "securityGroupIds": [
        "sg-07ca47ee2acbb5ccd"
      ],
      "clusterSecurityGroupId": "sg-0776f9de59b07e26a",
      "vpcId": "vpc-0bbe44f398f6fc948",
      "endpointPublicAccess": true,
      "endpointPrivateAccess": false,
      "publicAccessCidrs": [
        "0.0.0.0/0"
      ]
    },
    "kubernetesNetworkConfig": {
      "serviceIpv4Cidr": "10.100.0.0/16",
      "ipFamily": "ipv4"
    },
    "logging": {
      "clusterLogging": [
        {
          "types": ["api", "audit", "authenticator", "controllerManager", "scheduler"],
          "enabled": false
        }
      ]
    },
    "identity": {
      "oidc": {
        "issuer": "https://oidc.eks.ap-northeast-2.amazonaws.com/id/461A1FA..."
      }
    },
    "status": "ACTIVE",
    "certificateAuthority": {
      "data": "LS0tLS1CRUdJTi..."
    },
    "platformVersion": "eks.17",
    "tags": {
      "Terraform": "true",
      "Environment": "cloudneta-lab"
    },
    "encryptionConfig": [
      {
        "resources": ["secrets"],
        "provider": {
          "keyArn": "arn:aws:kms:ap-northeast-2:988608581192:key/7d150232-a52d-4bb3-a6cd-734f55cf67ed"
        }
      }
    ]
  }
}
```

</details>

[이전 글(코드 분석)]({% post_url 2026-03-12-Kubernetes-EKS-01-01-01-Installation %})과 [배포 결과]({% post_url 2026-03-12-Kubernetes-EKS-01-01-02-Installation-Result %})에서 콘솔로 확인한 내용이 대부분이므로, 아직 다루지 않은 필드를 중심으로 살펴 본다.

<br>

### roleArn

```json
"roleArn": "arn:aws:iam::988608581192:role/myeks-cluster-20260313135647575900000001"
```

Terraform 코드에서 IAM Role을 직접 선언하지 않았지만, EKS 모듈이 **자동으로 생성**한 클러스터 IAM Role이다. EKS 클러스터가 AWS 리소스(ENI 생성, 로그 전송, NLB 관리 등)를 조작하려면 IAM Role이 필요한데, EKS 모듈이 `AmazonEKSClusterPolicy` 등을 붙인 Role을 생성하고 연결한 것이다.

[KMS 키 자동 생성]({% post_url 2026-03-12-Kubernetes-EKS-01-01-02-Installation-Result %}#kms-키-자동-생성)과 마찬가지로 모듈이 내부적으로 생성하는 리소스다.

<br>

### kubernetesNetworkConfig

```json
"kubernetesNetworkConfig": {
  "serviceIpv4Cidr": "10.100.0.0/16",
  "ipFamily": "ipv4"
}
```

`serviceIpv4Cidr`는 `ClusterIP` 타입 서비스에 할당되는 **가상 IP 대역**이다. 온프레미스에서 `kube-apiserver --service-cluster-ip-range`로 직접 지정하던 것과 같은 개념인데, EKS에서는 클러스터 생성 시 AWS가 자동으로 할당한다. 실제로 이 클러스터의 CoreDNS ClusterIP가 `10.100.0.10`인 것도 이 대역 안에 있다.

<br>

### identity (OIDC)

```json
"identity": {
  "oidc": {
    "issuer": "https://oidc.eks.ap-northeast-2.amazonaws.com/id/461A1FA..."
  }
}
```

EKS는 **IAM Roles for Service Accounts(IRSA)**를 지원하기 위해 OIDC Provider를 자동 생성한다. Kubernetes ServiceAccount 토큰을 AWS IAM이 신뢰할 수 있도록 OIDC Provider를 연결하는 구조로, 이를 통해 파드별로 세분화된 AWS 권한(S3 접근, DynamoDB 접근 등)을 부여할 수 있다. 온프레미스 Kubernetes에는 이 개념이 없다.

> **참고: OIDC Provider와 IRSA**
>
> OIDC(OpenID Connect)는 OAuth 2.0 위에 구축된 신원 확인 프로토콜이다. OIDC Provider는 "이 토큰을 가진 주체가 누구인지"를 제3자가 신뢰할 수 있도록 증명하는 인증 서버 역할을 한다.
>
> EKS에서의 동작 흐름은 다음과 같다.
>
> 1. Pod가 ServiceAccount 토큰(JWT)을 들고 AWS 리소스에 접근을 요청한다
> 2. AWS IAM이 EKS OIDC Provider에 토큰 서명 검증을 요청한다 (`.well-known/openid-configuration` 엔드포인트에서 공개 키 조회)
> 3. 검증에 성공하면, 해당 ServiceAccount에 매핑된 IAM Role의 임시 자격증명(STS)을 발급한다
>
> OIDC Provider URL이 클러스터별로 고유하므로, 다른 클러스터의 SA 토큰이 이 클러스터의 IAM Role에 접근하는 것은 불가능하다. IRSA가 없으면 EC2 Instance Profile을 노드 전체가 공유하게 되어 최소 권한 원칙을 지키기 어렵다. IRSA를 통해 **파드 단위의 세분화된 AWS 권한 부여**가 가능해진다.

<br>

### certificateAuthority

```json
"certificateAuthority": {
  "data": "LS0tLS1CRUdJTi..."
}
```

Base64로 인코딩된 **CA 공개 인증서**다. [이전 글]({% post_url 2026-03-12-Kubernetes-EKS-01-01-03-Kubeconfig-Authentication %})에서 kubeconfig의 `certificate-authority-data`에 들어가는 값이 바로 이것이다. kubectl이 API 서버의 TLS 인증서를 검증할 때 사용하고, 워커 노드의 `/etc/kubernetes/pki/ca.crt`에도 이 값이 저장된다.

핵심은 CA의 **프라이빗 키는 AWS만 보유**한다는 점이다. 온프레미스에서는 CA 프라이빗 키가 컨트롤 플레인 노드의 `/etc/kubernetes/pki/ca.key`에 저장되어 관리자가 직접 관리했지만, EKS에서는 사용자에게 공개 인증서만 제공되고 프라이빗 키에는 접근할 수 없다.

<br>

### encryptionConfig

```json
"encryptionConfig": [
  {
    "resources": ["secrets"],
    "provider": {
      "keyArn": "arn:aws:kms:ap-northeast-2:988608581192:key/7d150232-..."
    }
  }
]
```

[배포 단계]({% post_url 2026-03-12-Kubernetes-EKS-01-01-02-Installation-Result %}#kms-키-자동-생성)에서 plan으로 확인한 KMS 키가 실제 적용된 결과다. etcd에 저장되는 Secret 리소스가 이 KMS 키로 암호화된다. [Hard Way 6단계]({% post_url 2026-01-05-Kubernetes-Cluster-The-Hard-Way-06 %})에서 `/dev/urandom`으로 키를 생성하고 `EncryptionConfiguration`을 직접 작성했던 것을 EKS 모듈이 KMS로 자동 처리해 준 것이다.

<br>

# 노드 확인

## 노드 그룹

Terraform에서 `eks_managed_node_group`으로 선언한 노드 그룹이 **관리형 노드 그룹(Managed Node Group)**으로 생성되었는지 확인한다. `aws eks describe-nodegroup` 명령 자체가 관리형 노드 그룹 전용 API이므로, 정상 응답이 오면 관리형으로 생성된 것이다.

```bash
aws eks describe-nodegroup --cluster-name $CLUSTER_NAME --nodegroup-name $CLUSTER_NAME-node-group | jq
```

<details markdown="1">
<summary>describe-nodegroup JSON 전문</summary>

```json
{
  "nodegroup": {
    "nodegroupName": "myeks-node-group",
    "nodegroupArn": "arn:aws:eks:ap-northeast-2:988608581192:nodegroup/myeks/myeks-node-group/7ece73c1-...",
    "clusterName": "myeks",
    "version": "1.34",
    "releaseVersion": "1.34.4-20260311",
    "status": "ACTIVE",
    "capacityType": "ON_DEMAND",
    "scalingConfig": {
      "minSize": 1,
      "maxSize": 4,
      "desiredSize": 2
    },
    "instanceTypes": ["t3.medium"],
    "subnets": [
      "subnet-09ff80d6277d22372",
      "subnet-0e89ca3e59aabe395",
      "subnet-04b03277d6d97e07c"
    ],
    "amiType": "AL2023_x86_64_STANDARD",
    "nodeRole": "arn:aws:iam::988608581192:role/myeks-node-group-eks-node-group-20260313135702848600000005",
    "resources": {
      "autoScalingGroups": [
        { "name": "eks-myeks-node-group-7ece73c1-a768-056e-3510-652d1175ebea" }
      ]
    },
    "health": { "issues": [] },
    "updateConfig": {
      "maxUnavailablePercentage": 33
    },
    "launchTemplate": {
      "name": "default-20260313140422498100000008",
      "version": "1",
      "id": "lt-05b80e624cb67171d"
    },
    "tags": {
      "Terraform": "true",
      "Environment": "cloudneta-lab",
      "Name": "myeks-node-group"
    }
  }
}
```

</details>

[배포 단계에서 콘솔로 확인한]({% post_url 2026-03-12-Kubernetes-EKS-01-01-02-Installation-Result %}#관리형-노드-그룹-auto-scaling-그룹) 내용에 더해, CLI에서 확인할 수 있는 주요 필드를 짚는다.

### amiType과 releaseVersion

```json
"amiType": "AL2023_x86_64_STANDARD",
"releaseVersion": "1.34.4-20260311"
```

`amiType`은 노드에 사용되는 **EKS 최적화 AMI의 OS·아키텍처 조합**이다. `AL2023_x86_64_STANDARD`는 Amazon Linux 2023 기반 x86_64 표준 AMI를 뜻한다. Terraform 코드에서 `ami_type`을 명시하지 않았지만, EKS 모듈이 기본값으로 선택한 것이다. GPU 워크로드라면 `AL2023_x86_64_NVIDIA`, Arm 기반이라면 `AL2023_ARM_64_STANDARD` 등 다른 타입을 지정한다.

`releaseVersion`은 해당 AMI 타입 내에서의 **구체적인 릴리즈 버전**이다. `1.34.4`는 kubelet 패치 버전, `20260311`은 AMI 빌드 날짜다. EKS가 보안 패치나 런타임 업데이트를 적용할 때 이 릴리즈 버전이 올라간다.

### updateConfig

```json
"updateConfig": {
  "maxUnavailablePercentage": 33
}
```

노드 그룹을 **롤링 업데이트**할 때, 동시에 unavailable 상태가 될 수 있는 노드의 최대 비율이다. Terraform 코드에서 `update_config`를 명시하지 않았지만, EKS 모듈이 기본값으로 33%를 설정한 것이다(AWS API 자체의 기본값은 `maxUnavailable = 1`이므로 모듈이 덮어쓴 값이다).

비율은 **내림(floor) 처리하되 최소 1**이다. 예를 들어 노드 4대면 4 × 0.33 = 1.32 → 내림 → **1대**, 노드 7대면 7 × 0.33 = 2.31 → 내림 → **2대**가 동시에 업데이트된다. 서비스 가용성과 업데이트 속도 사이의 균형을 조절하는 설정이다.

온프레미스에서 [kubespray의 `serial`]({% post_url 2026-01-25-Kubernetes-Kubespray-04-02 %})이나 [RKE2의 SUC `concurrency`]({% post_url 2026-02-15-Kubernetes-RKE2-04-02 %})로 업그레이드 병렬도를 조절했던 것과 같은 역할이다.

### launchTemplate

```json
"launchTemplate": {
  "name": "default-20260313140422498100000008",
  "version": "1",
  "id": "lt-05b80e624cb67171d"
}
```

EC2 **시작 템플릿(Launch Template)**으로, 노드(EC2 인스턴스)를 생성할 때 사용할 AMI, 인스턴스 타입, 보안 그룹, userdata 스크립트 등을 정의한 템플릿이다. 관리형 노드 그룹은 이 시작 템플릿을 기반으로 Auto Scaling Group을 통해 EC2 인스턴스를 프로비저닝한다. [배포 단계]({% post_url 2026-03-12-Kubernetes-EKS-01-01-02-Installation-Result %}#시작-템플릿-launch-template)에서 콘솔을 통해 노드 그룹 → ASG → 시작 템플릿까지 따라가며 userdata와 템플릿 버전 관리 구조를 확인한 바 있다.

<br>

## 노드 목록

```bash
kubectl get node --label-columns=node.kubernetes.io/instance-type,eks.amazonaws.com/capacityType,topology.kubernetes.io/zone
```

```
NAME                                              STATUS   ROLES    AGE   VERSION               INSTANCE-TYPE   CAPACITYTYPE   ZONE
ip-192-168-2-21.ap-northeast-2.compute.internal   Ready    <none>   27h   v1.34.4-eks-f69f56f   t3.medium       ON_DEMAND      ap-northeast-2b
ip-192-168-3-96.ap-northeast-2.compute.internal   Ready    <none>   27h   v1.34.4-eks-f69f56f   t3.medium       ON_DEMAND      ap-northeast-2c
```

몇 가지 눈에 띄는 점이 있다.

- **ROLES가 `<none>`이다**: 온프레미스에서 kubeadm은 컨트롤 플레인 노드에 `control-plane` role을 붙이고, 워커 노드는 `<none>`(또는 수동 label)이었다. EKS에서는 컨트롤 플레인이 노드 목록에 **아예 나타나지 않으므로**, 모든 노드가 `<none>`이다.

- **노드 이름이 EC2 프라이빗 DNS다**: `ip-192-168-2-21.ap-northeast-2.compute.internal`은 AWS가 EC2 인스턴스에 자동 부여하는 프라이빗 DNS 이름이다. 온프레미스에서 `k8s-m`, `k8s-w1`처럼 호스트 이름을 직접 지정했던 것과 다르다.

- **EKS 고유 라벨이 붙어 있다**: 전체 라벨을 확인해 보면 양이 상당하다. `eks.amazonaws.com/capacityType=ON_DEMAND`, `topology.kubernetes.io/zone` 등 AWS 인프라 정보가 라벨로 자동 부여된다. 이 라벨을 활용해 특정 AZ나 인스턴스 유형에만 워크로드를 스케줄링할 수 있다.

### 노드 라벨

```bash
kubectl get nodes -o wide --show-labels
```

<details markdown="1">
<summary>전체 출력</summary>

```
NAME                                              STATUS   ROLES    AGE     VERSION               INTERNAL-IP    EXTERNAL-IP     OS-IMAGE                        KERNEL-VERSION                   CONTAINER-RUNTIME    LABELS
ip-192-168-2-21.ap-northeast-2.compute.internal   Ready    <none>   2d19h   v1.34.4-eks-f69f56f   192.168.2.21   xx.xxx.xxx.xxx   Amazon Linux 2023.10.20260302   6.12.73-95.123.amzn2023.x86_64   containerd://2.1.5   beta.kubernetes.io/arch=amd64,beta.kubernetes.io/instance-type=t3.medium,beta.kubernetes.io/os=linux,eks.amazonaws.com/capacityType=ON_DEMAND,eks.amazonaws.com/nodegroup-image=ami-0c19bc6c6295a611b,eks.amazonaws.com/nodegroup=myeks-node-group,eks.amazonaws.com/sourceLaunchTemplateId=lt-05b80e624cb67171d,eks.amazonaws.com/sourceLaunchTemplateVersion=1,failure-domain.beta.kubernetes.io/region=ap-northeast-2,failure-domain.beta.kubernetes.io/zone=ap-northeast-2b,k8s.io/cloud-provider-aws=5553ae84a0d29114870f67bbabd07d44,kubernetes.io/arch=amd64,kubernetes.io/hostname=ip-192-168-2-21.ap-northeast-2.compute.internal,kubernetes.io/os=linux,node.kubernetes.io/instance-type=t3.medium,topology.k8s.aws/zone-id=apne2-az2,topology.kubernetes.io/region=ap-northeast-2,topology.kubernetes.io/zone=ap-northeast-2b
ip-192-168-3-96.ap-northeast-2.compute.internal   Ready    <none>   2d19h   v1.34.4-eks-f69f56f   192.168.3.96   xx.xxx.xxx.xxx   Amazon Linux 2023.10.20260302   6.12.73-95.123.amzn2023.x86_64   containerd://2.1.5   beta.kubernetes.io/arch=amd64,beta.kubernetes.io/instance-type=t3.medium,beta.kubernetes.io/os=linux,eks.amazonaws.com/capacityType=ON_DEMAND,eks.amazonaws.com/nodegroup-image=ami-0c19bc6c6295a611b,eks.amazonaws.com/nodegroup=myeks-node-group,eks.amazonaws.com/sourceLaunchTemplateId=lt-05b80e624cb67171d,eks.amazonaws.com/sourceLaunchTemplateVersion=1,failure-domain.beta.kubernetes.io/region=ap-northeast-2,failure-domain.beta.kubernetes.io/zone=ap-northeast-2c,k8s.io/cloud-provider-aws=5553ae84a0d29114870f67bbabd07d44,kubernetes.io/arch=amd64,kubernetes.io/hostname=ip-192-168-3-96.ap-northeast-2.compute.internal,kubernetes.io/os=linux,node.kubernetes.io/instance-type=t3.medium,topology.k8s.aws/zone-id=apne2-az3,topology.kubernetes.io/region=ap-northeast-2,topology.kubernetes.io/zone=ap-northeast-2c
```

</details>

라벨이 많으므로 Kubernetes 표준 라벨과 EKS 추가 라벨로 나누어 정리한다.

**Kubernetes 표준 라벨**

| 라벨 | 값 (예시) | 용도 |
| --- | --- | --- |
| `kubernetes.io/arch` | `amd64` | CPU 아키텍처. 멀티 아키텍처 클러스터에서 nodeSelector로 활용 |
| `kubernetes.io/os` | `linux` | OS. Windows 노드와 혼합 운영 시 구분 |
| `kubernetes.io/hostname` | `ip-192-168-2-21...` | 노드 이름 (= EC2 프라이빗 DNS) |
| `node.kubernetes.io/instance-type` | `t3.medium` | 인스턴스 타입. 리소스 요구량에 따른 스케줄링에 활용 |
| `topology.kubernetes.io/region` | `ap-northeast-2` | AWS 리전 |
| `topology.kubernetes.io/zone` | `ap-northeast-2b` | AZ. Pod Topology Spread Constraints로 AZ 분산 배치 시 핵심 |

> `beta.kubernetes.io/arch`, `failure-domain.beta.kubernetes.io/zone` 등은 위 라벨의 **레거시 버전**으로, 하위 호환을 위해 함께 부여된다.

**EKS 추가 라벨**

| 라벨 | 값 (예시) | 용도 |
| --- | --- | --- |
| `eks.amazonaws.com/capacityType` | `ON_DEMAND` | 용량 유형. 스팟이면 `SPOT`. nodeSelector로 온디맨드/스팟 워크로드를 분리할 수 있음 |
| `eks.amazonaws.com/nodegroup` | `myeks-node-group` | 소속 노드 그룹 이름. 특정 노드 그룹에만 워크로드를 배치할 때 활용 |
| `eks.amazonaws.com/nodegroup-image` | `ami-0c19bc6c...` | 노드 AMI ID. 어떤 AMI로 프로비저닝되었는지 추적 |
| `eks.amazonaws.com/sourceLaunchTemplateId` | `lt-05b80e62...` | Launch Template ID |
| `eks.amazonaws.com/sourceLaunchTemplateVersion` | `1` | Launch Template 버전 |
| `topology.k8s.aws/zone-id` | `apne2-az2` | AWS 내부 AZ ID. 계정마다 `ap-northeast-2b`가 매핑되는 물리 AZ가 다를 수 있어, 크로스 계정 일관성이 필요할 때 이 ID를 사용 |
| `k8s.io/cloud-provider-aws` | `5553ae84a0d...` | AWS Cloud Provider 식별 해시 |

온프레미스에서는 이런 라벨을 수동으로 붙이거나 아예 없었지만, EKS에서는 **kubelet 등록 시 자동으로 부여**된다. 특히 `capacityType`, `nodegroup`, `topology.kubernetes.io/zone`은 nodeSelector나 Pod Topology Spread Constraints에서 자주 쓰이므로 기억해 두면 좋다.

<br>

# 시스템 리소스 확인

## kube-system 파드

```bash
kubectl get pod -n kube-system -o wide
```

```
NAME                      READY   STATUS    RESTARTS   AGE   IP              NODE                                              NOMINATED NODE   READINESS GATES
aws-node-m8zzp            2/2     Running   0          27h   192.168.2.21    ip-192-168-2-21.ap-northeast-2.compute.internal   <none>           <none>
aws-node-q2hph            2/2     Running   0          27h   192.168.3.96    ip-192-168-3-96.ap-northeast-2.compute.internal   <none>           <none>
coredns-5759dc8cd-jp5md   1/1     Running   0          27h   192.168.2.132   ip-192-168-2-21.ap-northeast-2.compute.internal   <none>           <none>
coredns-5759dc8cd-sscgz   1/1     Running   0          27h   192.168.3.89    ip-192-168-3-96.ap-northeast-2.compute.internal   <none>           <none>
kube-proxy-9hbkd          1/1     Running   0          27h   192.168.2.21    ip-192-168-2-21.ap-northeast-2.compute.internal   <none>           <none>
kube-proxy-fpq85          1/1     Running   0          27h   192.168.3.96    ip-192-168-3-96.ap-northeast-2.compute.internal   <none>           <none>
```

온프레미스와 비교하면 **두 가지 핵심 차이**가 보인다.

### 컨트롤 플레인 컴포넌트가 없다

온프레미스(kubeadm)에서는 `kube-system` 네임스페이스에 `kube-apiserver`, `kube-controller-manager`, `kube-scheduler`, `etcd`가 Static Pod로 보였다. EKS에서는 컨트롤 플레인이 AWS 관리 VPC에서 동작하므로 **사용자 클러스터의 파드 목록에 나타나지 않는다**. 이것이 [EKS Overview]({% post_url 2026-03-12-Kubernetes-EKS-00-00-EKS-Overview %}#아키텍처)에서 말한 컨트롤 플레인 불가시성의 실체다.

EKS 콘솔의 리소스 탭에서도 동일하게 확인할 수 있다. All Namespaces로 봐도 파드는 `aws-node` 2개, `coredns` 2개, `kube-proxy` 2개 — 총 6개뿐이다.

![eks-dashboard-workload-pods]({{site.url}}/assets/images/eks-dashboard-workload-pods.png){: .align-center width="600"}

<center><sup>EKS 콘솔 리소스 탭 — 워크로드 파드 6개만 존재. 컨트롤 플레인 컴포넌트는 보이지 않는다</sup></center>

### 파드 IP가 VPC 서브넷의 실제 IP다

```
aws-node-m8zzp    192.168.2.21   ← 노드 IP와 동일 (hostNetwork)
coredns-...       192.168.2.132  ← 같은 서브넷의 다른 IP
coredns-...       192.168.3.89   ← 다른 서브넷의 IP
```

온프레미스에서는 파드 IP가 별도의 오버레이 대역(예: Flannel의 `10.244.x.x`, Calico의 `10.233.x.x`)이었다. EKS VPC CNI는 **ENI의 보조 IP를 파드에 직접 할당**하므로 파드 IP가 VPC 서브넷(`192.168.x.x`)의 실제 IP다. 이 차이는 [aws-node 상세](#aws-node-vpc-cni)에서 더 자세히 다룬다.

<br>

## kube-system 전체 리소스

```bash
kubectl get deploy,ds,pod,cm,secret,svc,ep,endpointslice,pdb,sa,role,rolebinding -n kube-system
```

<details markdown="1">
<summary>전체 출력</summary>

```
Warning: v1 Endpoints is deprecated in v1.33+; use discovery.k8s.io/v1 EndpointSlice
NAME                      READY   UP-TO-DATE   AVAILABLE   AGE
deployment.apps/coredns   2/2     2            2           27h

NAME                        DESIRED   CURRENT   READY   UP-TO-DATE   AVAILABLE   NODE SELECTOR   AGE
daemonset.apps/aws-node     2         2         2       2            2           <none>          27h
daemonset.apps/kube-proxy   2         2         2       2            2           <none>          27h

NAME                          READY   STATUS    RESTARTS   AGE
pod/aws-node-m8zzp            2/2     Running   0          27h
pod/aws-node-q2hph            2/2     Running   0          27h
pod/coredns-5759dc8cd-jp5md   1/1     Running   0          27h
pod/coredns-5759dc8cd-sscgz   1/1     Running   0          27h
pod/kube-proxy-9hbkd          1/1     Running   0          27h
pod/kube-proxy-fpq85          1/1     Running   0          27h

NAME                                                             DATA   AGE
configmap/amazon-vpc-cni                                         7      27h
configmap/aws-auth                                               1      27h
configmap/coredns                                                1      27h
configmap/extension-apiserver-authentication                     6      27h
configmap/kube-apiserver-legacy-service-account-token-tracking   1      27h
configmap/kube-proxy                                             1      27h
configmap/kube-proxy-config                                      1      27h
configmap/kube-root-ca.crt                                       1      27h

NAME                                TYPE        CLUSTER-IP      EXTERNAL-IP   PORT(S)                  AGE
service/eks-extension-metrics-api   ClusterIP   10.100.213.67   <none>        443/TCP                  27h
service/kube-dns                    ClusterIP   10.100.0.10     <none>        53/UDP,53/TCP,9153/TCP   27h

NAME                                                             ADDRESSTYPE   PORTS        ENDPOINTS                    AGE
endpointslice.discovery.k8s.io/eks-extension-metrics-api-wx9kx   IPv4          10443        172.0.32.0                   27h
endpointslice.discovery.k8s.io/kube-dns-7tfb4                    IPv4          9153,53,53   192.168.2.132,192.168.3.89   27h

NAME                                 MIN AVAILABLE   MAX UNAVAILABLE   ALLOWED DISRUPTIONS   AGE
poddisruptionbudget.policy/coredns   N/A             1                 1                     27h


NAME                                                         SECRETS   AGE
serviceaccount/attachdetach-controller                       0         27h
serviceaccount/aws-cloud-provider                            0         27h
serviceaccount/aws-node                                      0         27h
serviceaccount/certificate-controller                        0         27h
serviceaccount/clusterrole-aggregation-controller            0         27h
serviceaccount/coredns                                       0         27h
serviceaccount/cronjob-controller                            0         27h
serviceaccount/daemon-set-controller                         0         27h
serviceaccount/default                                       0         27h
serviceaccount/deployment-controller                         0         27h
serviceaccount/disruption-controller                         0         27h
serviceaccount/endpoint-controller                           0         27h
serviceaccount/endpointslice-controller                      0         27h
serviceaccount/endpointslicemirroring-controller             0         27h
serviceaccount/ephemeral-volume-controller                   0         27h
serviceaccount/expand-controller                             0         27h
serviceaccount/generic-garbage-collector                     0         27h
serviceaccount/horizontal-pod-autoscaler                     0         27h
serviceaccount/job-controller                                0         27h
serviceaccount/kube-proxy                                    0         27h
serviceaccount/legacy-service-account-token-cleaner          0         27h
serviceaccount/namespace-controller                          0         27h
serviceaccount/node-controller                               0         27h
serviceaccount/persistent-volume-binder                      0         27h
serviceaccount/pod-garbage-collector                         0         27h
serviceaccount/pv-protection-controller                      0         27h
serviceaccount/pvc-protection-controller                     0         27h
serviceaccount/replicaset-controller                         0         27h
serviceaccount/replication-controller                        0         27h
serviceaccount/resource-claim-controller                     0         27h
serviceaccount/resourcequota-controller                      0         27h
serviceaccount/root-ca-cert-publisher                        0         27h
serviceaccount/service-account-controller                    0         27h
serviceaccount/service-cidrs-controller                      0         27h
serviceaccount/service-controller                            0         27h
serviceaccount/statefulset-controller                        0         27h
serviceaccount/tagging-controller                            0         27h
serviceaccount/ttl-after-finished-controller                 0         27h
serviceaccount/ttl-controller                                0         27h
serviceaccount/validatingadmissionpolicy-status-controller   0         27h
serviceaccount/volumeattributesclass-protection-controller   0         27h

NAME                                                                            CREATED AT
role.rbac.authorization.k8s.io/eks-vpc-resource-controller-role                 2026-03-13T14:02:50Z
role.rbac.authorization.k8s.io/eks:addon-manager                                2026-03-13T14:02:49Z
role.rbac.authorization.k8s.io/eks:authenticator                                2026-03-13T14:02:47Z
role.rbac.authorization.k8s.io/eks:az-poller                                    2026-03-13T14:02:47Z
role.rbac.authorization.k8s.io/eks:coredns-autoscaler                           2026-03-13T14:02:47Z
role.rbac.authorization.k8s.io/eks:fargate-manager                              2026-03-13T14:02:49Z
role.rbac.authorization.k8s.io/eks:network-policy-controller                    2026-03-13T14:02:50Z
role.rbac.authorization.k8s.io/eks:node-manager                                 2026-03-13T14:02:48Z
role.rbac.authorization.k8s.io/eks:service-operations-configmaps                2026-03-13T14:02:47Z
role.rbac.authorization.k8s.io/extension-apiserver-authentication-reader        2026-03-13T14:02:45Z
role.rbac.authorization.k8s.io/system::leader-locking-kube-controller-manager   2026-03-13T14:02:45Z
role.rbac.authorization.k8s.io/system::leader-locking-kube-scheduler            2026-03-13T14:02:45Z
role.rbac.authorization.k8s.io/system:controller:bootstrap-signer               2026-03-13T14:02:45Z
role.rbac.authorization.k8s.io/system:controller:cloud-provider                 2026-03-13T14:02:45Z
role.rbac.authorization.k8s.io/system:controller:token-cleaner                  2026-03-13T14:02:45Z

NAME                                                                                      ROLE                                                  AGE
rolebinding.rbac.authorization.k8s.io/eks-vpc-resource-controller-rolebinding             Role/eks-vpc-resource-controller-role                 27h
rolebinding.rbac.authorization.k8s.io/eks:addon-manager                                   Role/eks:addon-manager                                27h
rolebinding.rbac.authorization.k8s.io/eks:authenticator                                   Role/eks:authenticator                                27h
rolebinding.rbac.authorization.k8s.io/eks:az-poller                                       Role/eks:az-poller                                    27h
rolebinding.rbac.authorization.k8s.io/eks:coredns-autoscaler                              Role/eks:coredns-autoscaler                           27h
rolebinding.rbac.authorization.k8s.io/eks:fargate-manager                                 Role/eks:fargate-manager                              27h
rolebinding.rbac.authorization.k8s.io/eks:network-policy-controller                       Role/eks:network-policy-controller                    27h
rolebinding.rbac.authorization.k8s.io/eks:node-manager                                    Role/eks:node-manager                                 27h
rolebinding.rbac.authorization.k8s.io/eks:service-operations                              Role/eks:service-operations-configmaps                27h
rolebinding.rbac.authorization.k8s.io/system::extension-apiserver-authentication-reader   Role/extension-apiserver-authentication-reader        27h
rolebinding.rbac.authorization.k8s.io/system::leader-locking-kube-controller-manager      Role/system::leader-locking-kube-controller-manager   27h
rolebinding.rbac.authorization.k8s.io/system::leader-locking-kube-scheduler               Role/system::leader-locking-kube-scheduler            27h
rolebinding.rbac.authorization.k8s.io/system:controller:bootstrap-signer                  Role/system:controller:bootstrap-signer               27h
rolebinding.rbac.authorization.k8s.io/system:controller:cloud-provider                    Role/system:controller:cloud-provider                 27h
rolebinding.rbac.authorization.k8s.io/system:controller:token-cleaner                     Role/system:controller:token-cleaner                  27h
```

</details>

<br>

전체 리소스를 온프레미스와 대비하여 정리해 보자.

### 워크로드

| 리소스 유형 | 이름 | 온프레미스(kubeadm) 대응 | 비고 |
| --- | --- | --- | --- |
| Deployment | `coredns` | coredns (Deployment) | 동일 |
| DaemonSet | `kube-proxy` | kube-proxy (DaemonSet) | 동일 |
| DaemonSet | **`aws-node`** | **해당 없음** | EKS 고유. VPC CNI 플러그인 |

`aws-node`는 EKS에서 VPC CNI 플러그인을 실행하는 DaemonSet이다. 온프레미스에서 Flannel이나 Calico를 별도로 설치했던 것에 대응하지만, [EKS Add-on]({% post_url 2026-03-12-Kubernetes-EKS-01-01-01-Installation %}#eks-애드온)으로 관리된다는 점이 다르다.

### ConfigMap

| ConfigMap | 설명 | 온프레미스 대응 |
| --- | --- | --- |
| `amazon-vpc-cni` | **VPC CNI 플러그인 설정** | **해당 없음 (EKS 고유)** |
| `aws-auth` | **IAM ↔ K8s RBAC 매핑** | **해당 없음 (EKS 고유)** |
| `coredns` | CoreDNS Corefile | coredns (동일) |
| `extension-apiserver-authentication` | 확장 API 서버 인증용 프론트 프록시 인증서 | 동일 (K8s 자동 생성) |
| `kube-apiserver-legacy-service-account-token-tracking` | 레거시 SA 토큰 사용 추적 (K8s 1.26+) | 동일 (K8s 자동 생성) |
| `kube-proxy` | kube-proxy kubeconfig | kube-proxy (동일) |
| `kube-proxy-config` | kube-proxy 설정 | kube-proxy-config (동일) |
| `kube-root-ca.crt` | CA 인증서 | kube-root-ca.crt (동일) |

### Service

| Service | ClusterIP | 설명 | 온프레미스 대응 |
| --- | --- | --- | --- |
| `kube-dns` | `10.100.0.10` | CoreDNS. `serviceIpv4Cidr: 10.100.0.0/16` 대역 안 | kube-dns (동일) |
| **`eks-extension-metrics-api`** | `10.100.213.67` | EKS 내부 확장 API | **해당 없음 (EKS 고유)** |

`eks-extension-metrics-api`는 `kubectl top`이 사용하는 Metrics Server와는 **다른 것**이다. EKS 컨트롤 플레인이 노드/파드 상태를 모니터링하기 위해 사용하는 내부 확장 API다. EndpointSlice의 주소가 `172.0.32.0`으로, 사용자 VPC 대역(`192.168.x.x`)이 아닌 **별도의 대역**인 것에서 알 수 있듯 AWS 관리 영역의 컴포넌트다.

> **참고**: `kubectl top`은 **Metrics Server**가 필요한데, 현재 클러스터에는 설치되어 있지 않다. kubeadm으로 설치한 클러스터에서도 Metrics Server는 기본 포함이 아니라 별도 설치가 필요하다. EKS에서도 마찬가지로 Add-on으로 별도 설치해야 한다.

### ServiceAccount

대부분의 ServiceAccount는 온프레미스 Kubernetes에도 있는 컨트롤러용 SA다. EKS 고유의 SA는 다음과 같다.

| ServiceAccount | 설명 |
| --- | --- |
| `aws-cloud-provider` | AWS Cloud Controller Manager가 사용. EC2, ELB 등 AWS 리소스와 Kubernetes 오브젝트를 연동 |
| `aws-node` | VPC CNI 플러그인(`aws-node` DaemonSet)이 ENI 할당·IP 관리에 사용 |
| `tagging-controller` | EKS가 관리하는 AWS 리소스(서브넷, 보안그룹 등)에 Kubernetes 태그를 자동 부여 |

### Role / RoleBinding

eks 접두사(`eks-`, `eks:`)가 붙은 Role들이 EKS 고유한 것이다.

| Role | 역할 |
| --- | --- |
| `eks-vpc-resource-controller-role` | VPC 리소스 컨트롤러. Security Groups for Pods 등 ENI 관련 리소스 관리 |
| `eks:addon-manager` | EKS Add-on 라이프사이클 관리 |
| `eks:authenticator` | IAM ↔ K8s 인증 연동 |
| `eks:az-poller` | 가용 영역(AZ) 정보 폴링 |
| `eks:coredns-autoscaler` | CoreDNS 레플리카 수 자동 조절 |
| `eks:fargate-manager` | Fargate 프로파일 관리 |
| `eks:network-policy-controller` | Network Policy 관리 |
| `eks:node-manager` | 노드 등록/관리 |
| `eks:service-operations-configmaps` | EKS 서비스 운영용 ConfigMap 접근 |

이 Role들은 EKS 컨트롤 플레인이 사용자 클러스터의 리소스를 관리하기 위해 자동 생성한 것이다.

<br>

# 시스템 파드 상세

kube-system 네임스페이스에 aws-node 2개, coredns 2개, kube-proxy 2개의 파드가 존재했다. 각각에 대해 살펴 보자.

## kube-proxy

```bash
kubectl describe pod -n kube-system -l k8s-app=kube-proxy
```

```
Priority Class Name:  system-node-critical
Controlled By:  DaemonSet/kube-proxy
Containers:
  kube-proxy:
    Image:   602401143452.dkr.ecr.ap-northeast-2.amazonaws.com/eks/kube-proxy:v1.34.3-eksbuild.5
    Command:
      kube-proxy
      --v=2
      --config=/var/lib/kube-proxy-config/config
      --hostname-override=$(NODE_NAME)
    Requests:
      cpu:  100m
```

### 설정 (kube-proxy-config)

kube-proxy의 실제 설정은 `kube-proxy-config` ConfigMap에 저장되어 있다.

```bash
kubectl get cm -n kube-system kube-proxy-config -o yaml
```

```yaml
data:
  config: |-
    apiVersion: kubeproxy.config.k8s.io/v1alpha1
    bindAddress: 0.0.0.0
    clientConnection:
      kubeconfig: /var/lib/kube-proxy/kubeconfig
      qps: 5
    clusterCIDR: ""
    conntrack:
      maxPerCore: 32768
      min: 131072
      tcpCloseWaitTimeout: 1h0m0s
      tcpEstablishedTimeout: 24h0m0s
    iptables:
      masqueradeAll: false
      masqueradeBit: 14
      minSyncPeriod: 0s
      syncPeriod: 30s
    mode: "iptables"
    metricsBindAddress: 0.0.0.0:10249
```

온프레미스(kubeadm)의 kube-proxy 설정과 큰 차이는 없다. 

- **`mode: "iptables"`**: EKS 기본은 iptables 모드다.
- **`clusterCIDR: ""`**: 비어 있다. 온프레미스에서는 오버레이 네트워크의 Pod CIDR을 명시해야 했다 — [Hard Way]({% post_url 2026-01-05-Kubernetes-Cluster-The-Hard-Way-09-1 %}#kube-proxy-설정-파일)에서는 `10.200.0.0/16`, [kubeadm]({% post_url 2026-01-18-Kubernetes-Kubeadm-01-7 %}#configmap-주요-설정)에서는 `10.244.0.0/16`, [RKE2]({% post_url 2026-02-15-Kubernetes-RKE2-01-02 %}#kube-proxy)에서는 `10.42.0.0/16`. EKS VPC CNI에서는 Pod IP가 VPC 서브넷의 실제 IP이므로 별도의 clusterCIDR이 불필요하다.
- **`conntrack.maxPerCore: 32768`**: CPU 코어당 최대 conntrack 엔트리 수. 비교해 보면, [kubeadm]({% post_url 2026-01-18-Kubernetes-Kubeadm-01-7 %}#configmap-주요-설정)에서는 `null`(커널 기본값 사용)이고, [RKE2]({% post_url 2026-02-15-Kubernetes-RKE2-01-02 %}#kube-proxy)에서는 `--conntrack-max-per-core=0`(제한 없음)이었다. EKS는 `32768`로 명시적 상한을 설정한다.

### kubeconfig (인증 방식)

kube-proxy가 사용하는 kubeconfig도 확인해 보자.

```bash
kubectl get cm -n kube-system kube-proxy -o yaml
```

```yaml
data:
  kubeconfig: |-
    kind: Config
    apiVersion: v1
    clusters:
    - cluster:
        certificate-authority: /var/run/secrets/kubernetes.io/serviceaccount/ca.crt
        server: https://461a1fa334847e0e1b597af07ff0cce0.gr7.ap-northeast-2.eks.amazonaws.com
      name: default
    users:
    - name: default
      user:
        tokenFile: /var/run/secrets/kubernetes.io/serviceaccount/token
```

온프레미스에서는 kube-proxy가 X.509 클라이언트 인증서로 API 서버에 인증했지만, EKS에서는 **ServiceAccount 토큰**(`/var/run/secrets/kubernetes.io/serviceaccount/token`)으로 인증한다. API 서버 주소도 EKS 엔드포인트 도메인이다.

<br>

## CoreDNS

```bash
kubectl describe pod -n kube-system -l k8s-app=kube-dns
```

```
Priority Class Name:  system-cluster-critical
Controlled By:  ReplicaSet/coredns-5759dc8cd
Containers:
  coredns:
    Image:   602401143452.dkr.ecr.ap-northeast-2.amazonaws.com/eks/coredns:v1.13.2-eksbuild.1
    Ports:   53/UDP (dns), 53/TCP (dns-tcp), 9153/TCP (metrics)
    Limits:
      memory:  170Mi
    Requests:
      cpu:     100m
      memory:  70Mi
    Liveness:   http-get http://:8080/health delay=60s
    Readiness:  http-get http://:8181/ready delay=0s
Tolerations:  CriticalAddonsOnly op=Exists
              node-role.kubernetes.io/control-plane:NoSchedule
Topology Spread Constraints:
  topology.kubernetes.io/zone:ScheduleAnyway when max skew 1 is exceeded for selector k8s-app=kube-dns
```

온프레미스(kubeadm)의 CoreDNS와 거의 동일하지만, 몇 가지 차이점이 있다.

### Topology Spread 

**Topology Spread Constraints가 설정되어 있다.** `topology.kubernetes.io/zone`을 기준으로 `maxSkew: 1`, `whenUnsatisfiable: ScheduleAnyway`로 AZ 간 균등 분산을 유도한다. 온프레미스에서는 AZ 개념이 없었으므로 이 설정이 없었다. 실제로 CoreDNS 2개 파드가 `ap-northeast-2b`와 `ap-northeast-2c`에 하나씩 분산되어 있다.


```yaml
topologySpreadConstraints:
- labelSelector:
    matchLabels:
      k8s-app: kube-dns
  maxSkew: 1
  topologyKey: topology.kubernetes.io/zone
  whenUnsatisfiable: ScheduleAnyway
```

### PDB

**PodDisruptionBudget이 설정되어 있다.** CoreDNS 2개 중 최대 1개까지만 동시에 중단될 수 있다. 온프레미스(kubeadm)에서는 CoreDNS에 PDB가 기본 포함되지 않았는데, EKS에서 추가한 이유는 **관리형 노드 그룹의 롤링 업데이트가 자동**이기 때문이다. 자동화된 drain 프로세스가 CoreDNS 파드가 올라간 노드를 동시에 교체할 수 있으므로, DNS 중단을 방지하기 위한 **자동화된 안전장치**가 필요하다.

```bash
kubectl get pdb -n kube-system coredns -o jsonpath='{.spec}' | jq
```

```json
{
  "maxUnavailable": 1,
  "selector": {
    "matchLabels": {
      "eks.amazonaws.com/component": "coredns",
      "k8s-app": "kube-dns"
    }
  }
}
```

### Corefile

Corefile 설정은 다음과 같다.

```bash
kubectl get cm -n kube-system coredns -o yaml
```

```yaml
data:
  Corefile: |
    .:53 {
        errors
        health {
            lameduck 5s
          }
        ready
        kubernetes cluster.local in-addr.arpa ip6.arpa {
          pods insecure
          fallthrough in-addr.arpa ip6.arpa
        }
        prometheus :9153
        forward . /etc/resolv.conf
        cache 30
        loop
        reload
        loadbalance
    }
```

온프레미스(kubeadm)의 Corefile과 동일한 구조다. `forward . /etc/resolv.conf`로 클러스터 외부 DNS 쿼리를 VPC의 DNS 서버(AmazonProvidedDNS, 일반적으로 VPC CIDR + 2)로 전달한다.

<br>

## aws-node (VPC CNI)

EKS에서 가장 핵심적인 네트워킹 컴포넌트다. 온프레미스의 Flannel이나 Calico에 대응하지만, 동작 방식이 근본적으로 다르다.

```bash
kubectl describe pod -n kube-system -l k8s-app=aws-node
```

<details markdown="1">
<summary>describe 전문 (노드 1대분)</summary>

```
Name:                 aws-node-57wfc
Namespace:            kube-system
Priority:             2000001000
Priority Class Name:  system-node-critical
Service Account:      aws-node
Node:                 ip-192-168-2-21.ap-northeast-2.compute.internal/192.168.2.21
Start Time:           Tue, 17 Mar 2026 21:28:44 +0900
Labels:               app.kubernetes.io/instance=aws-vpc-cni
                      app.kubernetes.io/name=aws-node
                      controller-revision-hash=5d6b59759d
                      k8s-app=aws-node
                      pod-template-generation=2
Status:               Running
IP:                   192.168.2.21
Controlled By:  DaemonSet/aws-node
Init Containers:
  aws-vpc-cni-init:
    Image:          602401143452.dkr.ecr.ap-northeast-2.amazonaws.com/amazon-k8s-cni-init:v1.21.1-eksbuild.5
    State:          Terminated
      Reason:       Completed
      Exit Code:    0
    Requests:
      cpu:  25m
    Environment:
      DISABLE_TCP_EARLY_DEMUX:  false
      ENABLE_IPv6:              false
    Mounts:
      /host/opt/cni/bin from cni-bin-dir (rw)
Containers:
  aws-node:
    Image:          602401143452.dkr.ecr.ap-northeast-2.amazonaws.com/amazon-k8s-cni:v1.21.1-eksbuild.5
    Port:           61678/TCP (metrics)
    Host Port:      61678/TCP (metrics)
    Requests:
      cpu:      25m
    Liveness:   exec [/app/grpc-health-probe -addr=:50051 -connect-timeout=5s -rpc-timeout=5s] delay=60s
    Readiness:  exec [/app/grpc-health-probe -addr=:50051 -connect-timeout=5s -rpc-timeout=5s] delay=1s
    Environment:
      ADDITIONAL_ENI_TAGS:                    {}
      ANNOTATE_POD_IP:                        false
      AWS_VPC_CNI_NODE_PORT_SUPPORT:          true
      AWS_VPC_ENI_MTU:                        9001
      AWS_VPC_K8S_CNI_CUSTOM_NETWORK_CFG:     false
      AWS_VPC_K8S_CNI_EXTERNALSNAT:           false
      AWS_VPC_K8S_CNI_LOGLEVEL:               DEBUG
      AWS_VPC_K8S_CNI_LOG_FILE:               /host/var/log/aws-routed-eni/ipamd.log
      AWS_VPC_K8S_CNI_RANDOMIZESNAT:          prng
      AWS_VPC_K8S_CNI_VETHPREFIX:             eni
      AWS_VPC_K8S_PLUGIN_LOG_FILE:            /var/log/aws-routed-eni/plugin.log
      AWS_VPC_K8S_PLUGIN_LOG_LEVEL:           DEBUG
      CLUSTER_ENDPOINT:                       https://461A1FA...gr7.ap-northeast-2.eks.amazonaws.com
      CLUSTER_NAME:                           myeks
      DISABLE_INTROSPECTION:                  false
      DISABLE_METRICS:                        false
      DISABLE_NETWORK_RESOURCE_PROVISIONING:  false
      ENABLE_IMDS_ONLY_MODE:                  false
      ENABLE_IPv4:                            true
      ENABLE_IPv6:                            false
      ENABLE_MULTI_NIC:                       false
      ENABLE_POD_ENI:                         false
      ENABLE_PREFIX_DELEGATION:               false
      ENABLE_SUBNET_DISCOVERY:                true
      NETWORK_POLICY_ENFORCING_MODE:          standard
      VPC_CNI_VERSION:                        v1.21.1
      VPC_ID:                                 vpc-0bbe44f398f6fc948
      WARM_ENI_TARGET:                        1
      WARM_PREFIX_TARGET:                     1
      MY_NODE_NAME:                            (v1:spec.nodeName)
      MY_POD_NAME:                            aws-node-57wfc (v1:metadata.name)
    Mounts:
      /host/etc/cni/net.d from cni-net-dir (rw)
      /host/opt/cni/bin from cni-bin-dir (rw)
      /host/var/log/aws-routed-eni from log-dir (rw)
      /run/xtables.lock from xtables-lock (rw)
      /var/run/aws-node from run-dir (rw)
  aws-eks-nodeagent:
    Image:         602401143452.dkr.ecr.ap-northeast-2.amazonaws.com/amazon/aws-network-policy-agent:v1.3.1-eksbuild.1
    Port:          8162/TCP (agentmetrics)
    Host Port:     8162/TCP (agentmetrics)
    Args:
      --enable-ipv6=false
      --enable-network-policy=false
      --enable-cloudwatch-logs=false
      --enable-policy-event-logs=false
      --log-file=/var/log/aws-routed-eni/network-policy-agent.log
      --metrics-bind-addr=:8162
      --health-probe-bind-addr=:8163
      --conntrack-cache-cleanup-period=300
      --log-level=debug
    Requests:
      cpu:  25m
    Mounts:
      /host/opt/cni/bin from cni-bin-dir (rw)
      /sys/fs/bpf from bpf-pin-path (rw)
      /var/log/aws-routed-eni from log-dir (rw)
      /var/run/aws-node from run-dir (rw)
Volumes:
  bpf-pin-path:       HostPath /sys/fs/bpf
  cni-bin-dir:        HostPath /opt/cni/bin
  cni-net-dir:        HostPath /etc/cni/net.d
  log-dir:            HostPath /var/log/aws-routed-eni (DirectoryOrCreate)
  run-dir:            HostPath /var/run/aws-node (DirectoryOrCreate)
  xtables-lock:       HostPath /run/xtables.lock (FileOrCreate)
QoS Class:            Burstable
Tolerations:          op=Exists
                      node.kubernetes.io/disk-pressure:NoSchedule op=Exists
                      node.kubernetes.io/memory-pressure:NoSchedule op=Exists
                      node.kubernetes.io/network-unavailable:NoSchedule op=Exists
                      node.kubernetes.io/not-ready:NoExecute op=Exists
                      node.kubernetes.io/pid-pressure:NoSchedule op=Exists
                      node.kubernetes.io/unreachable:NoExecute op=Exists
                      node.kubernetes.io/unschedulable:NoSchedule op=Exists
```

</details>

### 컨테이너 구성

aws-node 파드는 init 컨테이너 1개 + 일반 컨테이너 2개로 구성된다.

| 컨테이너 | 이미지 | 역할 |
| --- | --- | --- |
| `aws-vpc-cni-init` (init) | `amazon-k8s-cni-init` | CNI 바이너리를 호스트의 `/opt/cni/bin`에 설치 |
| `aws-node` | `amazon-k8s-cni` | **VPC CNI 플러그인** — 파드에 VPC IP 할당 |
| `aws-eks-nodeagent` | `aws-network-policy-agent` | **Network Policy 에이전트** — K8s NetworkPolicy 적용 |

### VPC CNI 개요

온프레미스에서는 Calico, Flannel 같은 CNI가 **오버레이 네트워크**(VXLAN, IP-in-IP 등)를 만들어 파드 IP를 할당한다. EKS VPC CNI는 완전히 다른 접근으로, ENI(Elastic Network Interface)의 보조 IP를 파드에 직접 할당하여 **VPC 서브넷의 실제 IP**를 파드가 사용한다. 오버레이 터널이 없으므로 캡슐화 오버헤드가 없지만, 인스턴스 유형별 ENI × IP 수로 **파드 수 상한**이 생기는 트레이드오프가 있다.

| | **온프레미스 (Calico/Flannel)** | **EKS (VPC CNI)** |
| --- | --- | --- |
| 파드 IP | 별도의 오버레이 대역 (예: `10.244.x.x`) | **VPC 서브넷의 실제 IP** (`192.168.x.x`) |
| 네트워크 | VXLAN/IP-in-IP 터널 | **네이티브 VPC 라우팅** (터널 없음) |
| 성능 | 캡슐화 오버헤드 있음 | 오버헤드 없음 |
| 파드 수 제한 | 거의 없음 | **ENI × IP 수**로 제한 (인스턴스 유형별 상한) |

ENI warm pool, prefix delegation, SNAT 모드 등 VPC CNI의 세부 설정과 동작 원리는 이후 더 자세히 다룬다.

<details markdown="1">
<summary>aws-node 환경 변수 및 호스트 마운트 상세</summary>

**주요 환경 변수**

```
ENABLE_PREFIX_DELEGATION:    false
WARM_ENI_TARGET:             1
WARM_PREFIX_TARGET:          1
AWS_VPC_ENI_MTU:             9001
AWS_VPC_K8S_CNI_VETHPREFIX:  eni
AWS_VPC_K8S_CNI_EXTERNALSNAT: false
VPC_ID:                      vpc-0bbe44f398f6fc948
CLUSTER_ENDPOINT:            https://461A1FA...eks.amazonaws.com
```

| 환경 변수 | 값 | 의미 |
| --- | --- | --- |
| `WARM_ENI_TARGET` | `1` | 파드 할당에 대비해 미리 1개의 ENI를 warm pool에 확보 |
| `WARM_PREFIX_TARGET` | `1` | `/28` prefix 1개를 미리 확보 (prefix delegation 사용 시) |
| `ENABLE_PREFIX_DELEGATION` | `false` | 비활성화. 활성화하면 ENI당 더 많은 IP를 할당 가능 |
| `AWS_VPC_ENI_MTU` | `9001` | Jumbo Frame 지원. VPC 내 통신에서 오버헤드 감소 |
| `AWS_VPC_K8S_CNI_VETHPREFIX` | `eni` | veth pair 이름 접두사. 온프레미스의 `cali` (Calico), `veth` (Flannel)에 대응 |
| `AWS_VPC_K8S_CNI_EXTERNALSNAT` | `false` | VPC CNI가 직접 SNAT 처리. `true`면 외부 SNAT(iptables) 사용 |

**호스트 경로 마운트**

CNI 플러그인은 호스트 네트워크 스택을 직접 조작해야 하므로, 온프레미스의 Calico/Flannel과 마찬가지로 호스트 경로를 마운트한다.

| 마운트 경로 | 용도 |
| --- | --- |
| `/opt/cni/bin` | CNI 바이너리 배포. init 컨테이너가 여기에 CNI 바이너리를 설치 |
| `/etc/cni/net.d` | CNI 설정 파일(`10-aws.conflist`) 배포. kubelet이 이 경로에서 CNI 설정을 읽음 |
| `/run/xtables.lock` | iptables 규칙 동시 수정 방지를 위한 락 파일 |
| `/sys/fs/bpf` | eBPF 맵 고정(pinning). Network Policy 에이전트가 사용 |

</details>

<br>

# 컨테이너 이미지: ECR

시스템 파드들의 컨테이너 이미지가 어디서 오는지 확인한다. 온프레미스에서는 `registry.k8s.io`에서 가져왔는데, EKS에서는 어떨까.

```bash
kubectl get pods --all-namespaces -o jsonpath="{.items[*].spec.containers[*].image}" | tr -s '[[:space:]]' '\n' | sort | uniq -c
```

```
  2 602401143452.dkr.ecr.ap-northeast-2.amazonaws.com/amazon-k8s-cni:v1.21.1-eksbuild.3
  2 602401143452.dkr.ecr.ap-northeast-2.amazonaws.com/amazon/aws-network-policy-agent:v1.3.1-eksbuild.1
  2 602401143452.dkr.ecr.ap-northeast-2.amazonaws.com/eks/coredns:v1.13.2-eksbuild.1
  2 602401143452.dkr.ecr.ap-northeast-2.amazonaws.com/eks/kube-proxy:v1.34.3-eksbuild.5
```

모든 이미지가 `602401143452.dkr.ecr.ap-northeast-2.amazonaws.com`에서 가져온 것이다.

| 부분 | 의미 |
| --- | --- |
| `602401143452` | AWS가 EKS용으로 운영하는 공용 ECR 계정 ID |
| `dkr.ecr.ap-northeast-2` | 서울 리전의 ECR |

온프레미스 Kubernetes에서는 `registry.k8s.io`(구 `k8s.gcr.io`)에서 이미지를 가져오지만, EKS는 이를 전부 ECR로 대체한다.

| | **온프레미스 (registry.k8s.io)** | **EKS (ECR)** |
| --- | --- | --- |
| 위치 | 인터넷 (해외 CDN) | **같은 AWS 리전 내** |
| 속도 | 상대적으로 느림 | 빠름 (리전 내부 통신) |
| 가용성 | AWS 통제 불가 | **AWS가 직접 관리** |
| 인증 | 없음 (공개) | IAM 기반 인증 |

EKS 시스템 컴포넌트(CoreDNS, kube-proxy, VPC CNI)는 클러스터 부팅에 **필수**이므로, 외부 레지스트리에 의존하지 않고 AWS가 자체 ECR에 이미지를 미러링해서 제공한다.

<br>

# EKS Add-on 확인

```bash
aws eks list-addons --cluster-name myeks | jq
```

```json
{
  "addons": [
    "coredns",
    "kube-proxy",
    "vpc-cni"
  ]
}
```

[Terraform 코드]({% post_url 2026-03-12-Kubernetes-EKS-01-01-01-Installation %}#eks-애드온)에서 `addons` 블록으로 선언한 3개가 그대로 설치되어 있다.

```bash
aws eks list-addons --cluster-name myeks \
| jq -r '.addons[]' \
| xargs -I{} aws eks describe-addon \
     --cluster-name myeks \
     --addon-name {} \
| jq '.addon | {addonName, addonVersion, status}'
```

```json
{ "addonName": "coredns", "addonVersion": "v1.13.2-eksbuild.1", "status": "ACTIVE" }
{ "addonName": "kube-proxy", "addonVersion": "v1.34.3-eksbuild.5", "status": "ACTIVE" }
{ "addonName": "vpc-cni", "addonVersion": "v1.21.1-eksbuild.3", "status": "ACTIVE" }
```

세 애드온 모두 `ACTIVE` 상태다. 각 애드온에 EKS 빌드 버전(`-eksbuild.x`)이 붙어 있는데, 이는 AWS가 업스트림 버전에 EKS 환경 최적화 패치를 적용한 빌드임을 나타낸다.

온프레미스에서는 이 컴포넌트들의 버전 관리를 사용자가 직접 해야 했다.

| | **온프레미스** | **EKS Add-on** |
| --- | --- | --- |
| **설치** | `kubectl apply`, Helm, 또는 도구별 자동 설치 | Terraform `addons` 블록 또는 AWS 콘솔 |
| **버전 관리** | 직접 호환성 확인 후 수동 업그레이드 | `most_recent = true`로 클러스터 버전 호환 최신 자동 적용 |
| **롤백** | 직접 이전 버전 매니페스트 적용 | AWS API로 이전 버전 지정 |
| **상태 관리** | 직접 모니터링 | `health.issues`로 상태 확인 가능 |

추가 애드온이 필요하면 Terraform 코드의 `addons` 블록에 선언하면 된다. Metrics Server, AWS Load Balancer Controller 등이 대표적이다.

<br>

# 결론

EKS 클러스터의 구성 요소를 확인해 보았다. 이를 바탕으로 온프레미스 Kubernetes와의 구조적 차이를 정리해 본다.

| 항목 | 온프레미스 | EKS |
| --- | --- | --- |
| **컨트롤 플레인 가시성** | Static Pod / systemd로 직접 확인 가능 | 불가시. AWS 관리 VPC에 숨어 있음 |
| **시스템 파드** | API Server, etcd, Scheduler, CM + CoreDNS, kube-proxy | CoreDNS, kube-proxy, **aws-node**(VPC CNI) |
| **파드 IP** | 오버레이 대역 (`10.244.x.x` 등) | VPC 서브넷 실제 IP (`192.168.x.x`) |
| **이미지 레지스트리** | `registry.k8s.io` | AWS ECR (`602401143452.dkr.ecr...`) |
| **컴포넌트 인증** | X.509 클라이언트 인증서 | ServiceAccount 토큰 |
| **애드온 관리** | 직접 설치·업그레이드 | EKS Add-on (AWS가 버전 관리) |

가장 큰 차이는 **보이는 것의 범위**다. 온프레미스에서는 `kubectl get pod -n kube-system`만으로 클러스터의 거의 모든 구성 요소를 볼 수 있었지만, EKS에서는 컨트롤 플레인 전체가 보이지 않는다. 대신 `aws eks describe-cluster`라는 AWS API를 통해 간접적으로 확인해야 한다. [EKS Overview]({% post_url 2026-03-12-Kubernetes-EKS-00-00-EKS-Overview %}#결론)에서 이야기한 **관리형 서비스의 추상화 수준이 한 단계 더 높다**는 것이 CLI 확인 과정에서도 체감된다.

이 글에서 확인한 구성 요소(시스템 파드, VPC CNI, ECR, Add-on 등)는 엔드포인트 모드와 무관하게 모든 EKS 클러스터에 공통이다. [다음 글]({% post_url 2026-03-12-Kubernetes-EKS-01-01-05-EKS-Cluster-Worker-Node-Result %})에서는 SSH로 워커 노드에 접속하여 **노드 내부 구성**(kubelet, containerd, 인증서 등)을 확인한다.

<br>
