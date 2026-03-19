---
title:  "[EKS] EKS: Overview"
excerpt: "AWS의 관리형 Kubernetes 서비스인 EKS가 무엇인지 간단히 살펴보자."
categories:
  - Kubernetes
toc: true
header:
  teaser: /assets/images/blog-Dev.jpg
tags:
  - Kubernetes
  - AWS
  - EKS
  - AWS-EKS-Workshop-Study
  - AWS-EKS-Workshop-Study-Week-1

---

*[서종호(가시다)](https://www.linkedin.com/in/gasida99/)님의 AWS EKS Workshop Study(AEWS) 1주차 학습 내용을 기반으로 합니다.*

<br>

# TL;DR

이번 글에서는 **EKS의 핵심 개념과 아키텍처**, 그리고 시작하는 방법을 간략히 다룬다.

- **정의**: AWS가 컨트롤 플레인을 완전 관리하는 Kubernetes 서비스
- **아키텍처**: 컨트롤 플레인(AWS 관리) + 데이터 플레인(사용자 관리) 분리 구조
- **접근 모드**: EKS 표준(컨트롤 플레인만 관리) vs. EKS Auto Mode(데이터 플레인까지 관리)
- **시작하기**: 클러스터 프로비저닝 → 컴퓨팅 자원 배포 → 클러스터 연결 → 애플리케이션 배포
- **온프레미스와의 차이**: 컨트롤 플레인 관리 부담이 사라지고, 관리 책임 경계가 달라짐

<br>

# 들어가며

[On-Premise K8s Hands-on Study]({% post_url 2026-01-05-Kubernetes-Cluster-The-Hard-Way-00 %})에서는 Kubernetes 클러스터를 직접 구성하고 운영했다. [The Hard Way]({% post_url 2026-01-05-Kubernetes-Cluster-The-Hard-Way-00 %})로 모든 구성 요소를 손으로 설치했고, [kubeadm]({% post_url 2026-01-18-Kubernetes-Kubeadm-00 %})으로 부트스트래핑을 자동화했고, [Kubespray]({% post_url 2026-01-25-Kubernetes-Kubespray-00 %})로 OS 설정부터 클러스터 구성까지 전체를 자동화했고, [RKE2]({% post_url 2026-02-15-Kubernetes-RKE2-00 %})로 단일 바이너리 배포판을 경험했다.

이번에는 **EKS(Elastic Kubernetes Service)**다. 지금까지의 도구들은 자동화 수준이 달랐을 뿐, 결국 **컨트롤 플레인을 사용자가 직접 관리**했다. etcd를 직접 구성하고, API 서버 인증서를 직접 갱신하고, 컨트롤 플레인 노드의 장애 복구를 직접 해야 했다. EKS는 이 컨트롤 플레인 관리를 **AWS가 완전히 맡는** 관리형 서비스다. 사용자는 데이터 플레인(워커 노드)과 워크로드에 집중한다.

온프레미스 환경에서 직접 구성하던 것들이 EKS에서는 어떻게 달라지는지, 그리고 새롭게 알아야 할 것은 무엇인지 살펴보자.

<br>

# 정의

EKS(Elastic Kubernetes Service)는 **AWS의 관리형 Kubernetes 서비스**로, AWS에서 Kubernetes 컨트롤 플레인 영역(혹은 컨트롤 플레인과 데이터 플레인 영역)을 완전 관리해주는 Kubernetes 서비스이다.

"Elastic"은 AWS 서비스 네이밍에서 반복되는 키워드로(EC2, ELB, EBS 등), 수요에 따라 리소스를 탄력적으로 확장·축소할 수 있음을 나타낸다. EKS에서는 노드 수·인스턴스 용량 조절(Cluster Autoscaler, Karpenter 등)뿐 아니라 HPA·VPA를 통한 파드 스케일링, Fargate를 통한 파드 단위 서버리스 컴퓨트까지 **인프라·애플리케이션 계층 전반의 탄력적 확장·축소**가 이에 해당한다. Kubernetes 호환 인증([CNCF Certified Kubernetes](https://www.cncf.io/training/certification/software-conformance/))을 받았으므로, 리팩터링 없이 Kubernetes 호환 애플리케이션을 배포하고 커뮤니티 도구 및 플러그인을 사용할 수 있다.

[AWS 공식 문서](https://docs.aws.amazon.com/ko_kr/eks/latest/userguide/what-is-eks.html)를 보면, EKS를 다음과 같이 소개한다.

> Amazon Elastic Kubernetes Service(Amazon EKS)는 Amazon Web Services(AWS) 클라우드와 자체 데이터 센터 모두에서 Kubernetes 클러스터를 실행하는 데 있어 최적의 플랫폼입니다. 
> 
> Amazon EKS는 Kubernetes 클러스터의 구축, 보안 및 유지 관리를 간소화합니다.

핵심은 **"Kubernetes 클러스터의 구축, 보안 및 유지 관리를 간소화"**하는 것이다.

<br>

# 주요 기능

EKS는 Kubernetes 클러스터 위에서 컨트롤러 및 기타 구성 요소를 완전 관리하며, 자동화된 패치 적용·조정·모니터링을 제공한다. [주요 특징은 아래와 같다](https://www.ongja.space/13c4c62d-36c3-8136-ab0e-d0fd60d0645b#1444c62d-36c3-803e-ad5c-f1e034798953).

- **AWS 관리형 서비스**: 쿠버네티스 컨트롤 플레인(*또는 컨트롤 플레인과 데이터 플레인 영역*)을 AWS 관리 VPC에 구성하고 관리
- **고가용성 구성**: 다수의 AWS 가용 영역에 배치되어 고가용성 보장
- **다양한 AWS 서비스와 통합**: IAM, VPC, ELB, EBS, CloudWatch 등 AWS 서비스와 연동하여 포괄적인 플랫폼 제공
- **쿠버네티스 최신 버전 적용**: 쿠버네티스 최신 버전을 적용하며, [표준 지원](https://docs.aws.amazon.com/ko_kr/eks/latest/userguide/kubernetes-versions-standard.html)과 [확장 지원](https://docs.aws.amazon.com/ko_kr/eks/latest/userguide/kubernetes-versions-extended.html) 제공
- **다양한 관리 인터페이스**: AWS Console, EKS API/SDK, CDK, AWS CLI, eksctl, CloudFormation, Terraform 등 다양한 프로비저닝·관리 방법 제공

<br>

# 아키텍처

EKS 아키텍처는 크게 **컨트롤 플레인**과 **데이터 플레인** 두 축으로 구성된다.

## 컨트롤 플레인

쿠버네티스를 제어하기 위한 컨트롤 플레인 컴포넌트(API 서버, 컨트롤러, 스케줄러, etcd 등)가 **AWS Managed VPC**에서 관리형으로 동작한다.

![EKS 컨트롤 플레인 아키텍처](/assets/images/eks-control-plane-architecture.png)
<center><sup>출처: <a href="https://www.ongja.space/13c4c62d-36c3-8136-ab0e-d0fd60d0645b#1444c62d-36c3-803e-ad5c-f1e034798953">Amazon EKS 소개 - Ongja.Space</a></sup></center>

AWS 리전 내 3개 가용 영역에 걸쳐 최소 2개의 API 서버와 3개의 etcd 인스턴스가 분산 배치되며, 인스턴스 장애 시 자동으로 대체된다. 온프레미스에서 etcd 클러스터를 직접 구성하고 API 서버를 로드밸런서 뒤에 배치했던 것을 AWS가 자동으로 처리해 준다.

## 데이터 플레인

쿠버네티스 노드를 구성하기 위한 데이터 플레인 컴포넌트(컨테이너 런타임, kubelet, kube-proxy 등)가 **사용자의 Custom VPC**에서 동작한다. **EKS Owned ENI**를 통해 컨트롤 플레인 영역과 연결된다.

![EKS 데이터 플레인 아키텍처](/assets/images/eks-data-plane-architecture.png)
<center><sup>출처: <a href="https://www.ongja.space/13c4c62d-36c3-8136-ab0e-d0fd60d0645b#1444c62d-36c3-803e-ad5c-f1e034798953">Amazon EKS 소개 - Ongja.Space</a></sup></center>

데이터 플레인을 구성하는 방식은 [관리형 노드 그룹](https://docs.aws.amazon.com/ko_kr/eks/latest/userguide/managed-node-groups.html), [자체 관리형 노드](https://docs.aws.amazon.com/ko_kr/eks/latest/userguide/worker.html), [Fargate](https://docs.aws.amazon.com/ko_kr/eks/latest/userguide/fargate.html), [EKS Auto Mode](https://docs.aws.amazon.com/ko_kr/eks/latest/userguide/automode.html) 네 가지다. 각 방식의 상세한 비교는 [데이터 플레인 컴퓨팅]({% post_url 2026-03-12-Kubernetes-EKS-00-01-EKS-Computing-Group %}) 글에서 다룬다.

<br>

# 접근 모드

EKS 사용과 관련된 두 가지 주요 접근 방식은 다음과 같다.

| 방식 | AWS가 관리하는 범위 |
| --- | --- |
| **EKS 표준** | **컨트롤 플레인만** 관리. <br> 노드 관리, 워크로드 스케줄링, AWS 통합은 사용자가 처리 |
| **EKS Auto Mode** | 컨트롤 플레인 + **데이터 플레인(노드)까지** 관리. <br> 인프라 프로비저닝, 컴퓨팅 인스턴스 선택, 동적 스케일링, OS 패치를 자동 처리 |

![EKS 클러스터 아키텍처 — Standard vs Auto Mode](/assets/images/amazon-eks-cluster-whatis.png)
<center><sup><a href="https://docs.aws.amazon.com/ko_kr/eks/latest/userguide/what-is-eks.html#_amazon_eks_simplified_kubernetes_management">Amazon EKS: 간소화된 Kubernetes 관리</a></sup></center>

위 그림은 EKS Standard와 EKS Auto Mode의 관리 경계를 보여준다. EKS Standard에서는 AWS가 컨트롤 플레인만 관리하고, EKS Add-Ons(CNI, EBS CSI Driver, Load Balancer Controller 등)와 EC2 인스턴스는 고객 계정에서 관리한다. EKS Auto Mode에서는 이러한 기능들이 **Managed Capabilities**로 EKS 관리 범위에 포함되어, 고객은 EC2 인스턴스와 Supporting AWS Services만 관리하면 된다.

<br>

# EKS 시작하기

## 작업 단계

EKS에서 Kubernetes 클러스터를 운영하기까지의 단계는 다음과 같다.
**1. Amazon EKS 클러스터 프로비저닝**: 쿠버네티스 컨트롤 플레인을 AWS 관리형으로 배포
**2. 컴퓨팅 자원 배포**: 쿠버네티스 데이터 플레인을 위한 워커 노드를 사용자 영역에 배포
**3. 클러스터 연결**: kubectl 등 쿠버네티스 관리 도구를 통해 Amazon EKS 클러스터에 연결
**4. 애플리케이션 배포**: 쿠버네티스 네이티브 리소스를 사용해 Amazon EKS 클러스터에 애플리케이션 배포

## 배포 방법

EKS 클러스터를 배포하는 주요 방법은 세 가지다. 자세한 내용은 [EKS 설치 개요]({% post_url 2026-03-12-Kubernetes-EKS-01-01-00-Installation-Overview %})에서 다룬다.

**관리 콘솔**

![eks-console-provisioning]({{site.url}}/assets/images/eks-console-provisioning.png){: .align-center width="600"}

AWS 관리 콘솔에서 Amazon EKS 클러스터를 직접 배포한다.

**eksctl**

Amazon EKS 클러스터를 생성하고 관리하는 명령어 기반의 CLI 도구이다.

```bash
eksctl create cluster --name myeks --region=ap-northeast-2
=========================================
OUTPUT:

...
2023-05-23 01:32:22 [▶] setting current-context to admin@myeks.ap-northeast-2.eksctl.io
2023-05-23 01:32:22 [✔] saved kubeconfig as "/root/.kube/config"
...

:END
```

**IaC 도구**

코드 기반으로 Amazon EKS 클러스터를 정의하고 배포한다. AWS CDK, AWS CloudFormation, Terraform 등이 있다.

```hcl
# Terraform 예시
module "eks" {
  source  = "terraform-aws-modules/eks/aws"

  cluster_name    = myeks
  cluster_version = 1.30
  ...
}
```

<br>

# 요금

온프레미스에서는 Kubernetes 자체가 오픈소스이므로 소프트웨어 비용이 없었다. EKS에서는 AWS가 컨트롤 플레인을 관리해 주는 대가로 **클러스터당 시간 요금**(관리 수수료)이 새로운 비용 항목으로 추가되고, 컴퓨팅·스토리지·네트워크 등 인프라도 AWS 리소스 사용량 기반으로 과금된다.

주요 EKS 요금 구조는 다음과 같다.

| 과금 항목 | 설명 |
| --- | --- |
| **EKS 클러스터** | Kubernetes 클러스터 버전 지원에 따라 클러스터당 시간 요금 |
| **EC2 인스턴스** | 워커 노드로 사용하는 인스턴스 비용 |
| **EBS 볼륨** | 워커 노드의 루트 볼륨 및 PV용 볼륨 |
| **네트워크** | 퍼블릭 IPv4 주소, NAT Gateway, 데이터 전송 등 |
| **EKS Auto Mode** | Auto Mode 사용 시 별도 요금 |

관리형 노드 그룹이나 Fargate 등 [데이터 플레인 방식]({% post_url 2026-03-12-Kubernetes-EKS-00-01-EKS-Computing-Group %})에 따라 비용 구조가 달라진다. EKS 요금 정책은 변경될 수 있으므로 [AWS 공식 요금 페이지](https://aws.amazon.com/ko/eks/pricing/)를 참고한다.

<br>

# 결론

## 온프레미스와의 비교

온프레미스 스터디에서 직접 관리했던 것들이 EKS에서는 어떻게 달라지는지 비교하면, EKS가 제공하는 가치가 분명해진다.

| 항목 | 온프레미스 (직접 관리) | EKS |
| --- | --- | --- |
| **컨트롤 플레인** | etcd, API Server, Controller Manager, Scheduler 직접 설치·운영 | AWS가 완전 관리 (HA 기본, 자동 복원) |
| **인증서** | 직접 생성·갱신 (The Hard Way), kubeadm 자동화 | AWS가 관리 |
| **etcd** | 직접 구성·백업·복구 | AWS가 관리 (3개 AZ에 분산) |
| **노드 프로비저닝** | VM 직접 생성, OS 설정, kubelet 설치 | 관리형 노드 그룹 등 여러 방식 제공 |
| **네트워킹** | CNI 직접 선택·설치 (Flannel, Calico 등) | VPC CNI 기본 제공 (Pod에 VPC IP 직접 할당) |
| **업그레이드** | 컨트롤 플레인 + 노드 전부 수동 | 컨트롤 플레인은 API 한 번, 노드는 롤링 업데이트 |
| **보안** | 모든 보안 설정 직접 관리 | AWS와 사용자 간 공동 책임 모델 |

컨트롤 플레인 관리 부담이 사라지는 것이 가장 큰 변화다. 온프레미스에서 etcd 백업·복구, 인증서 갱신, API 서버 HA 구성 등에 들이던 노력을 워크로드 운영에 집중할 수 있다. CNI, CoreDNS, metrics-server 등도 [EKS 애드온]({% post_url 2026-03-12-Kubernetes-EKS-01-01-01-Installation %}#eks-애드온)으로 관리되어, 직접 설치하고 업데이트하던 부담이 줄어든다.

## 앞으로

하지만 편해지는 만큼 새로 알아야 할 것도 있다. EKS에서는 쿠버네티스 자체에 대한 이해 위에, **AWS 고유의 개념**을 함께 파악해야 한다. AWS IAM과 Kubernetes RBAC이 어떻게 통합되는지, VPC 네트워킹과 Pod 네트워킹이 어떤 관계인지, 공동 책임 모델에서 보안 경계가 어디인지 — 이것들은 쿠버네티스만 알아서는 답이 나오지 않는, 관리형 서비스 고유의 영역이다.

[Kubespray Overview]({% post_url 2026-01-25-Kubernetes-Kubespray-00 %}#블랙박스의-위험)에서 자동화 도구의 블랙박스 위험을 이야기했는데, 관리형 서비스는 그 추상화 수준이 한 단계 더 높다. 컨트롤 플레인이 보이지 않는 데다, AWS라는 플랫폼의 고유 개념까지 겹치면서 문제가 생겼을 때 쿠버네티스 문제인지 AWS 문제인지 구분하는 것부터가 과제가 된다. 앞으로는 클러스터 배포·운영 과정에서 AWS가 무엇을 대신하고, 사용자에게 무엇이 남는지를 하나씩 짚어 나가 보고자 한다.

<br>
