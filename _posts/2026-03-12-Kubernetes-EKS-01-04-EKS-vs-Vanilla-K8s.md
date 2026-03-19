---
title:  "[EKS] EKS: EKS vs. Vanilla Kubernetes"
excerpt: "EKS에서 달라지는 것과 달라지지 않는 것을 정리해보자."
categories:
  - Kubernetes
toc: true
header:
  teaser: /assets/images/blog-Dev.jpg
tags:
  - Kubernetes
  - AWS
  - EKS
  - VPC-CNI
  - IAM
  - AWS-EKS-Workshop-Study
  - AWS-EKS-Workshop-Study-Week-1

---

*[서종호(가시다)](https://www.linkedin.com/in/gasida99/)님의 AWS EKS Workshop Study(AEWS) 1주차 학습 내용을 기반으로 합니다.*

<br>

# TL;DR

[구성 요소 확인]({% post_url 2026-03-12-Kubernetes-EKS-01-01-04-EKS-Cluster-Result %})과 [워커 노드 내부 확인]({% post_url 2026-03-12-Kubernetes-EKS-01-01-05-EKS-Cluster-Worker-Node-Result %})에서 EKS 클러스터를 바깥과 안에서 살펴보았다. 이번 글에서는 이 결과를 바탕으로 **온프레미스 Kubernetes와의 구조적 차이**를 정리한다.

- **클러스터 구성**: 컨트롤 플레인 소유권, 워커 노드 프로비저닝, 인증, etcd, 애드온 — "누가 관리하느냐"가 달라진다
- **AWS 네트워크**: VPC CNI(오버레이 → 네이티브), Security Group, 엔드포인트 — 패러다임 자체가 전환된다
- **추상화의 대가**: 편해지는 것이 있지만, 보이지 않는 것도 늘어나고, Kubernetes와 별개의 AWS 도메인 지식(IAM, VPC, STS, KMS)이 필요해진다

<br>

# 들어가며

[이전 글]({% post_url 2026-03-12-Kubernetes-EKS-01-01-04-EKS-Cluster-Result %})에서는 `aws eks describe-cluster`와 `kubectl`로 EKS 클러스터를 **바깥에서**, [워커 노드 내부 확인]({% post_url 2026-03-12-Kubernetes-EKS-01-01-05-EKS-Cluster-Worker-Node-Result %})에서는 SSH로 **안에서** 살펴보았다. 그 결과, containerd가 있고 kubelet이 있고 CNI 설정 파일이 있다 — **구조 자체는 온프레미스와 크게 다르지 않지만, 누가 관리하느냐가 완전히 다르다**는 것을 확인했다.

이번 글에서는 이 차이를 조금 더 멀리서 조망해 보고자 한다.

<br>

# EKS vs. 온프레미스

"온프레미스에서 내가 하던 것을 EKS가 어떻게 바꾸나?"를 축으로 비교한다. 크게 **클러스터 구성** 측면과 **AWS 네트워크** 측면으로 나눈다.

## 클러스터 구성

### 컨트롤 플레인: 소유권과 가시성

| 포인트 | 온프레미스 | EKS |
| --- | --- | --- |
| **관리 주체** | 사용자가 etcd, API Server, Scheduler, CM을 직접 운영 | AWS가 Multi-AZ로 운영, 사용자에게 **불투명(opaque)** |
| **확인 방법** | `kubectl get pod -n kube-system`으로 Static Pod 직접 확인 | `aws eks describe-cluster`로 간접 확인 |
| **etcd 접근** | `etcdctl`로 직접 조회·백업 | 접근 불가. AWS 관리 영역 |
| **컴포넌트 튜닝** | API Server 플래그, Scheduler 프로파일 등 직접 수정 | 불가. AWS가 정해진 설정으로 운영 |
| **로깅** | `journalctl`, Pod 로그 직접 확인 | CloudWatch Logs로 전송 (활성화 시) |

[구성 요소 확인 - 시스템 파드]({% post_url 2026-03-12-Kubernetes-EKS-01-01-04-EKS-Cluster-Result %}#시스템-파드-확인)에서 `kubectl get pod -n kube-system`을 실행했을 때, **kube-apiserver, etcd, scheduler, controller-manager가 하나도 보이지 않았다**. 파드는 `aws-node` 2개, `coredns` 2개, `kube-proxy` 2개 — 총 6개뿐이었다.

온프레미스에서는 컨트롤 플레인을 systemd 서비스든 Static Pod든 어떤 형태로든 **직접 확인할 수 있었다**. EKS에서는 이 축 자체가 사라진다.

### 워커 노드: 프로비저닝 주체의 전환

| 포인트 | 온프레미스 | EKS |
| --- | --- | --- |
| **노드 프로비저닝** | VM 직접 생성 → OS 설정 → CRI·kubelet 설치 | Managed Node Group → ASG → EC2 자동 생성 + AL2023 AMI에 모두 포함 |
| **노드 등록** | `kubeadm join` (Bootstrap Token), RKE2 (server token) | IAM Node Role + nodeadm 자동 등록 |
| **kubelet 설정** | `/var/lib/kubelet/config.yaml` (직접 작성) | `/etc/kubernetes/kubelet/config.json` + nodeadm drop-in (AMI 사전 설정) |
| **ROLES 칼럼** | control-plane / `<none>` (또는 수동 label) | 모든 노드가 `<none>` (컨트롤 플레인이 노드 목록에 없음) |
| **스케일링** | VM 추가 + join | ASG desired_size 변경, Cluster Autoscaler/Karpenter |

[워커 노드 내부]({% post_url 2026-03-12-Kubernetes-EKS-01-01-05-EKS-Cluster-Worker-Node-Result %})에서 확인한 바, containerd, kubelet, CNI 플러그인이 모두 AMI에 포함되어 있었다. 온프레미스에서 `apt install`, `systemctl enable` 등으로 수동 설치하던 것이 AMI 한 장으로 대체된다. 설정 역시 nodeadm이 Launch Template의 userdata(NodeConfig)를 읽어 자동으로 적용한다.

### 인증/인가: X.509에서 IAM으로

| 포인트 | 온프레미스 | EKS |
| --- | --- | --- |
| **사용자 인증** | X.509 클라이언트 인증서 (kubeconfig에 cert-data 내장) | IAM identity → STS pre-signed URL → Bearer Token |
| **노드 인증** | kubelet 클라이언트 인증서 (X.509) | IAM Node Role → EC2 Instance Profile |
| **CA 관리** | `ca.crt` + `ca.key` 모두 마스터에 존재 | `ca.crt`만 존재. **`ca.key`는 AWS만 보유** |
| **kubelet 서버 인증서** | kubeadm 발급, 1년 유효, 수동 갱신 | CSR 자동 발급, ~45일 유효, 자동 갱신 |
| **RBAC 매핑** | ClusterRoleBinding + X.509 CN/O | EKS Access Entry + IAM 매핑 |

[인증서 확인]({% post_url 2026-03-12-Kubernetes-EKS-01-01-05-EKS-Cluster-Worker-Node-Result %}#인증서)에서 CA 인증서를 직접 열어보았다. `ca.crt`만 존재하고 `ca.key`는 없었다. [kubeconfig]({% post_url 2026-03-12-Kubernetes-EKS-01-01-05-EKS-Cluster-Worker-Node-Result %}#kubelet)에서도 X.509 인증서 대신 `aws eks get-token` 명령이 들어 있었다.

온프레미스에서는 "노드가 CA 인증서 없이 어떻게 클러스터에 합류하느냐"라는 신뢰 부트스트래핑 문제를 Bootstrap Token이나 SCP로 해결했다. EKS에서는 이 문제 자체가 IAM + STS로 완전히 대체된다.

### etcd와 데이터 보호

| 포인트 | 온프레미스 | EKS |
| --- | --- | --- |
| **etcd 운영** | 사용자 관리 (백업, 복구, compaction) | AWS 관리 (사용자 접근 불가) |
| **Encryption at Rest** | 수동 설정 필요 (kubeadm), 기본 활성 (RKE2) | **KMS 자동 통합** |
| **백업/복구** | `etcdctl snapshot save` | 직접 불가. Velero 등 K8s-level 백업 필요 |

### 애드온 관리

| 포인트 | 온프레미스 | EKS |
| --- | --- | --- |
| **CNI** | 별도 설치 또는 자동화 도구가 설치 | **EKS Add-on** (VPC CNI를 AWS가 버전 관리) |
| **CoreDNS, kube-proxy** | `kubeadm init` 기본 포함, 업그레이드는 수동 | EKS Add-on으로 관리, `-eksbuild.x` 버전 |
| **이미지 레지스트리** | `registry.k8s.io` (인터넷) | **AWS ECR** (같은 리전 내) |
| **업그레이드** | `kubeadm upgrade` 등 도구별 명령 | EKS API 호출 (Terraform apply) → 자동 |

[EKS Add-on 확인]({% post_url 2026-03-12-Kubernetes-EKS-01-01-04-EKS-Cluster-Result %}#eks-add-on)에서 세 애드온(VPC CNI, CoreDNS, kube-proxy)이 모두 `ACTIVE` 상태이고, 각각 `-eksbuild.x` 접미사가 붙은 AWS 커스텀 빌드임을 확인했다. 이미지도 전부 `602401143452.dkr.ecr.ap-northeast-2.amazonaws.com`에서 제공되어, `registry.k8s.io`로의 외부 네트워크 의존이 없었다.

<br>

## AWS 네트워크

클러스터 구성 측면의 차이가 "**누가 관리하느냐**"의 문제라면, 네트워크 측면의 차이는 **패러다임 자체의 전환**이다.

### CNI: 오버레이에서 VPC 네이티브로

| 포인트 | 온프레미스 | EKS |
| --- | --- | --- |
| **파드 IP 할당** | 오버레이 네트워크 (Flannel VXLAN, Calico IPIP 등) | ENI secondary IP → **VPC 서브넷의 실제 IP** |
| **파드 IP 대역** | 별도 CIDR (예: `10.244.0.0/16`) | 노드와 같은 VPC 서브넷 (`192.168.x.x`) |
| **kube-proxy `clusterCIDR`** | Pod CIDR 명시 (예: `10.244.0.0/16`) | **비어 있음** (VPC 라우팅이 직접 처리) |
| **파드 수 제한** | 이론상 무제한 (CIDR 범위 내) | 인스턴스 유형별 ENI × IP 수 상한 (예: `t3.medium` → 17개) |
| **통신 경로** | 캡슐화 (VXLAN 터널) 또는 BGP | VPC 라우팅 테이블에서 **직접 라우팅** |

[워커 노드 네트워크 확인]({% post_url 2026-03-12-Kubernetes-EKS-01-01-05-EKS-Cluster-Worker-Node-Result %}#네트워크)에서 `ip addr`로 ENI 2개(`ens5`, `ens6`)와 veth 인터페이스를, `ip route`로 파드 IP가 VPC 서브넷에서 직접 라우팅되는 것을 확인했다. `iptables -t nat -S`에서도 오버레이 캡슐화 규칙 대신 VPC CNI의 `AWS-SNAT-CHAIN-0`이 있었다.

온프레미스 Kubernetes에서는 Flannel VXLAN이든 Calico IPIP든, **오버레이 네트워크가 기본 전제**였다. EKS VPC CNI는 이 전제 자체를 바꾼다.

### 보안 경계: iptables에서 Security Group으로

| 포인트 | 온프레미스 | EKS |
| --- | --- | --- |
| **네트워크 보안** | iptables, firewalld, SELinux | **Security Group** (VPC-level 방화벽) + NACL |
| **컨트롤 플레인 ↔ 워커** | 같은 네트워크 or LB | EKS managed SG (9443, 443 등 자동 허용) |
| **외부 접근 제어** | 방화벽 규칙 | endpoint access (public/private), `publicAccessCidrs`, SG |

EKS에서는 Security Group이 컨트롤 플레인과 워커 노드 간 통신을 제어한다. 온프레미스에서 노드 간 방화벽 규칙을 수동으로 열어주던 것을 AWS가 자동 생성·관리하는 Security Group으로 대체한 것이다.

### API 서버 접근: localhost에서 NLB 엔드포인트로

| 포인트 | 온프레미스 | EKS |
| --- | --- | --- |
| **API 서버 주소** | `https://192.168.x.x:6443` (마스터 IP) | `https://xxxxx.gr7.ap-northeast-2.eks.amazonaws.com` |
| **HA 구성** | HAProxy, nginx static pod, 또는 LB 직접 구성 | AWS NLB **기본 제공** (Multi-AZ) |
| **접근 제어** | 방화벽 규칙 | `endpointPublicAccess`, `endpointPrivateAccess`, `publicAccessCidrs` |
| **Service CIDR** | `--service-cluster-ip-range`로 직접 지정 | AWS가 자동 할당 (예: `10.100.0.0/16`) |

<br>

# 부록: 온프레미스 스터디 시리즈와의 연결

이전 스터디([On-Premise K8s Hands-on Study](https://gasidaseo.notion.site/26-K8S-Deploy-Hands-on-Study-31150aec5edf800c9b3ccfd9ed41e271))에서 Hard Way → kubeadm → Kubespray → RKE2로 클러스터를 구성해 왔다. 그 연장선에서 EKS를 포함한 5가지 방법을 9개 축으로 통합 비교한다.

## 통합 비교표

| 비교 축 | Hard Way | kubeadm | Kubespray | RKE2 | **EKS** |
| --- | --- | --- | --- | --- | --- |
| **인프라 프로비저닝** | [수동 VM]({% post_url 2026-01-05-Kubernetes-Cluster-The-Hard-Way-03 %}) | 수동 VM | [Ansible]({% post_url 2026-01-25-Kubernetes-Kubespray-00 %}) | 수동 VM | **IaC (Terraform) + AWS API** |
| **컨트롤 플레인 배포** | [systemd]({% post_url 2026-01-05-Kubernetes-Cluster-The-Hard-Way-08-1 %}) | [Static Pod]({% post_url 2026-01-18-Kubernetes-Kubeadm-00 %}#kubeadm이-배포하는-것) | Static Pod | [supervisor + Static Pod]({% post_url 2026-02-15-Kubernetes-RKE2-00 %}#핵심-구조-단일-바이너리--supervisor-패턴) | **AWS 관리형 (사용자에게 비공개)** |
| **인증서/PKI** | [OpenSSL 수동]({% post_url 2026-01-05-Kubernetes-Cluster-The-Hard-Way-04-3 %}) | 자동 생성 | kubeadm 위임 | supervisor 내장 | **AWS CA + IAM + STS** |
| **노드 Join** | [SCP 수동]({% post_url 2026-01-05-Kubernetes-Cluster-The-Hard-Way-09-2 %}) | [Bootstrap Token]({% post_url 2026-01-18-Kubernetes-Kubeadm-00 %}#init과-join의-신뢰-모델) | Ansible 자동화 | server token | **IAM Node Role** |
| **CNI** | [bridge 수동]({% post_url 2026-01-05-Kubernetes-Cluster-The-Hard-Way-09-1 %}) | 별도 설치 | Ansible Role | [Canal 내장]({% post_url 2026-02-15-Kubernetes-RKE2-00 %}#참고-canal) | **VPC CNI (오버레이 없음)** |
| **HA** | 해당 없음 | 수동 | [Client-Side/External LB]({% post_url 2026-01-25-Kubernetes-Kubespray-00 %}) | built-in | **Multi-AZ 기본 제공** |
| **보안 기본값** | 최소 (HTTP etcd) | 중간 (HTTPS etcd) | kubeadm 기본 | [CIS Benchmark 통과]({% post_url 2026-02-15-Kubernetes-RKE2-00 %}#보안-하드닝) | **AWS 관리 + KMS + IAM** |
| **업그레이드** | 수동 재설치 | [`kubeadm upgrade`]({% post_url 2026-01-18-Kubernetes-Kubeadm-00 %}#클러스터-업그레이드) | `upgrade-cluster.yml` | SUC/수동 | **API 호출 (Terraform apply)** |
| **추상화 수준** | 모든 것이 보임 | 부트스트래핑 자동화 | 전체 자동화 | 단일 바이너리 | **컨트롤 플레인이 보이지 않음** |

## 핵심 전환점

비교표에서 EKS 열만 유독 다르다. Hard Way부터 RKE2까지, 추상화 수준이 달라도 **같은 Kubernetes 도메인 안에서** 움직였다. Bootstrap Token, Static Pod manifest, `kubeadm upgrade` 같은 개념이 반복되었다. EKS에서는 이것들이 IAM Node Role, Terraform `addons` 블록, AWS managed Security Group으로 대체되면서, **Kubernetes 도메인과 별개의 AWS 도메인**이 끼어든다.

<br>

# 추상화의 대가

EKS는 관리형 서비스다. 자동화 수준이 올라가면 편해지지만, 블랙박스도 함께 커진다.

## 편해지는 것

- **etcd**: 백업, 복구, compaction, encryption — 전부 AWS가 처리
- **HA**: Multi-AZ 기본. HAProxy, nginx static pod 같은 LB 구성이 필요 없음
- **인증서 갱신**: CA 키를 AWS가 보유하고, kubelet 서버 인증서는 ~45일마다 자동 갱신
- **업그레이드**: Terraform apply로 컨트롤 플레인 자동 업그레이드, 노드 그룹 rolling update
- **노드 프로비저닝**: VM 생성, OS 설정, CRI·kubelet 설치가 AMI 한 장으로 대체

## 보이지 않는 것

- **컨트롤 플레인 컴포넌트**: API Server, Scheduler, Controller Manager의 **플래그를 바꿀 수 없다**
- **etcd**: `etcdctl`로 직접 조회하거나 스냅샷을 뜰 수 없다
- **CA 프라이빗 키**: `ca.key`에 접근할 수 없으므로, 직접 인증서를 발급하는 것도 불가
- **네트워크 내부**: 컨트롤 플레인이 어떤 VPC에, 어떤 AZ에, 몇 개의 API Server 인스턴스로 동작하는지 알 수 없다

## 새로 알아야 하는 것

| Kubernetes 도메인 | AWS 도메인 (새로 필요) |
| --- | --- |
| kubelet, containerd, etcd | VPC, 서브넷, 라우팅 테이블, IGW, NAT GW |
| X.509 인증서, CSR, CA | IAM, STS, OIDC, IRSA |
| NetworkPolicy, iptables | Security Group, NACL, NLB |
| ConfigMap, Secret | KMS, CloudWatch Logs |
| PV, StorageClass | EBS CSI Driver, EFS CSI Driver |

EKS를 운영하려면 **Kubernetes 지식 + AWS 지식** 두 축이 모두 필요하다. 한쪽만으로는 문제 해결이 어렵다. API 서버 접근이 안 되는 문제가 endpoint access 설정인지 Security Group인지 `publicAccessCidrs`인지, Kubernetes 쪽이 아니라 AWS 쪽을 봐야 할 수도 있다.

<br>

# 결론

EKS에서 달라지는 것은 **"누가 관리하느냐"**와 **"어떤 도메인 위에서 동작하느냐"**다. 컨트롤 플레인은 AWS가 관리하고, 인증은 IAM + STS로, 네트워크는 VPC CNI로, 보안 경계는 Security Group으로 바뀐다. Kubernetes 안에서만 움직이면 되던 것이, AWS 인프라(VPC, IAM, KMS, Security Group)라는 새로운 축 위에서 동작하게 된다.

그러나 달라지지 않는 것도 있다. [워커 노드 내부]({% post_url 2026-03-12-Kubernetes-EKS-01-01-05-EKS-Cluster-Worker-Node-Result %})에 들어가 보면, containerd가 있고 kubelet이 있고 CNI 설정 파일이 있다. `systemctl status containerd`, `cat /etc/kubernetes/kubelet/config.json`, `iptables -t nat -S`를 실행하면 온프레미스에서 보던 것과 **구조적으로 같은 것**이 보인다. 달라진 것은 설치 방법(AMI), 설정 방법(nodeadm + NodeConfig), 인증 방법(IAM + STS)이지, **Kubernetes 자체의 동작 원리가 바뀐 것은 아니다**.

AWS가 관리해 주는 영역이 넓어졌을 뿐, 그 아래에서 동작하는 Kubernetes 원리를 아는 것이 문제 해결의 출발점이라는 점은 변하지 않는다. 다만 솔직히, Kubernetes 원리를 안다고 끝이 아니라 **그 위에 AWS 도메인 지식까지 얹어야 한다**는 점이 EKS의 진입 장벽이기도 하다.

결국 잘 쓴다는 건, **평소에는 AWS가 관리하는 영역을 신뢰하되, 문제가 생겼을 때는 추상화 아래 계층을 직접 볼 줄 아는 것**이 아닐까 싶다. etcd 백업을 안 해도 되고 HA 구성을 안 해도 되는 건 EKS의 혜택이지만, 워커 노드에 SSH로 들어가 `journalctl -u kubelet`, `crictl ps`, `iptables -t nat -S`를 실행하며 문제를 추적할 줄 알아야 할 것이다.

<br>
