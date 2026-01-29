---
title:  "[Kubernetes] Cluster: Kubespray를 이용해 클러스터 구성하기 - 1. Kubespray 개요"
excerpt: "Kubespray의 핵심 기능과 동작 원리를 살펴보고, Kubernetes The Hard Way 및 kubeadm과 비교해보자."
categories:
  - Kubernetes
toc: true
header:
  teaser: /assets/images/blog-Dev.jpg
tags:
  - Kubernetes
  - On-Premise-K8s-Hands-On-Study
  - On-Premise-K8s-Hands-On-Study-Week-4

---

*[서종호(가시다)](https://www.linkedin.com/in/gasida99/)님의 On-Premise K8s Hands-on Study 4주차 학습 내용을 기반으로 합니다.*

<br>

# TL;DR

이번 글의 목표는 **Kubespray의 핵심 기능과 동작 원리 이해**다.

- **Ansible 기반**: Role, Playbook, 변수 파일로 구성된 구조
- **핵심 기능**: 다양한 환경(퍼블릭/폐쇄망) 지원, HA 구성, Best Practice 설정 제공
- **클러스터 운영 전반 지원**: 생성, 업그레이드, 노드 추가/제거, 백업/복구
- **비교**: Kubernetes The Hard Way → kubeadm → **Kubespray** (자동화 수준 증가)

<br>

# 들어가며

[이전 글]({% post_url 2026-01-25-Kubernetes-Kubespray-00 %})에서 Kubespray가 무엇을 제공하고자 하는지 살펴보았다. Kubespray는 Ansible 기반으로 동작하며, kubeadm을 내부적으로 사용하면서 OS 설정부터 클러스터 구성까지 전체 과정을 자동화한다.

이번 글에서는 Kubespray가 **어떻게 동작하는지**, **어떤 기능을 제공하는지** 구체적으로 살펴본다.

<br>

# Ansible 기반 동작 원리

Kubespray는 Ansible Playbook의 집합이다. Kubespray를 이해하려면 [Ansible의 기본 개념]({% post_url 2026-01-12-Kubernetes-Ansible-01 %})을 알아야 한다.

## Kubespray에서의 Ansible 구성 요소

| Ansible 개념 | Kubespray에서의 활용 |
| --- | --- |
| **[Control Node]({% post_url 2026-01-12-Kubernetes-Ansible-01 %}#control-node와-managed-node)** | Kubespray를 실행하는 노드 (클러스터 외부) |
| **Managed Node** | 컨트롤 플레인, 워커 노드 (클러스터 구성 노드) |
| **[Inventory]({% post_url 2026-01-12-Kubernetes-Ansible-01 %}#inventory)** | `inventory/mycluster/inventory.ini` (노드 목록 및 그룹 정의) |
| **[Playbook]({% post_url 2026-01-12-Kubernetes-Ansible-01 %}#playbook-play-task)** | `cluster.yml`, `scale.yml`, `reset.yml` 등 |
| **[Role]({% post_url 2026-01-12-Kubernetes-Ansible-01 %}#role)** | `roles/kubernetes/`, `roles/etcd/`, `roles/network_plugin/` 등 |

## Kubespray 디렉토리 구조

Kubespray의 구조를 보면 Ansible의 [Role]({% post_url 2026-01-12-Kubernetes-Ansible-01 %}#role) 패턴을 따르고 있음을 알 수 있다.

```bash
kubespray/
├── cluster.yml              # 메인 Playbook
├── scale.yml                # 노드 추가 Playbook
├── reset.yml                # 클러스터 초기화 Playbook
├── inventory/
│   └── sample/              # 샘플 인벤토리
│       ├── inventory.ini    # 노드 목록
│       └── group_vars/      # 그룹별 변수
│           ├── all.yml
│           └── k8s_cluster/
│               ├── k8s-cluster.yml
│               └── addons.yml
└── roles/                   # Ansible Role들
    ├── bootstrap-os/        # OS 기본 설정
    ├── container-engine/    # containerd 설치
    │   └── containerd/
    ├── etcd/                # etcd 클러스터 구성
    ├── kubernetes/          # Kubernetes 컴포넌트
    │   ├── control-plane/
    │   └── node/
    └── network_plugin/      # CNI 플러그인
        ├── calico/
        └── flannel/
```

## 멱등성 활용

[Ansible의 멱등성]({% post_url 2026-01-12-Kubernetes-Ansible-01 %}#멱등성-보장이-아니라-지향)은 Kubespray에서 큰 장점이 된다.

- **안전한 재실행**: 배포 중 실패하더라도 동일한 플레이북을 다시 실행하면 중단된 지점부터 이어서 진행
- **설정 변경 적용**: 변수를 수정하고 다시 실행하면 변경된 부분만 적용
- **Drift 방지**: 정기적으로 플레이북을 실행하여 클러스터가 원하는 상태를 유지하도록 보장

```bash
# 배포 중 실패 시 동일한 명령으로 재실행
ansible-playbook -i inventory/mycluster/inventory.ini cluster.yml -b

# 이미 완료된 작업은 ok, 변경이 필요한 작업만 changed
```

## Ansible 설계 철학의 반영

[Ansible의 설계 철학]({% post_url 2026-01-12-Kubernetes-Ansible-00 %}#설계-철학)이 Kubespray에도 그대로 반영되어 있다.

| Ansible 철학 | Kubespray 적용 |
| --- | --- |
| **Agentless** | 대상 노드에 SSH와 Python만 있으면 됨 |
| **Push 방식** | `ansible-playbook` 명령으로 즉시 배포 |
| **YAML 기반** | 인벤토리와 변수 파일로 선언적 설정 |
| **Desired State** | 원하는 클러스터 상태를 정의하면 Kubespray가 맞춰줌 |

> [Ansible 탄생 배경]({% post_url 2026-01-12-Kubernetes-Ansible-00 %}#탄생-배경)에서 살펴보았듯이, Ansible은 복잡한 인프라 설정을 단순하게 만들기 위해 탄생했다. Kubespray는 이 철학을 계승하여, 복잡한 Kubernetes 클러스터 구성을 단순한 변수 설정과 명령어 하나로 해결한다.

<br>

# 클러스터 운영 전반 지원

Kubespray는 클러스터 생성뿐만 아니라 운영 전반을 지원한다.

| 기능 | 설명 |
| --- | --- |
| **클러스터 생성** | 신규 쿠버네티스 클러스터 배포 |
| **클러스터 업그레이드** | 컨트롤 플레인 및 워커 노드 버전 업그레이드 |
| **노드 추가/제거** | 워커 노드, 컨트롤 플레인, etcd 노드 스케일링 |
| **클러스터 재설정** | 클러스터 초기화 및 재구성 |
| **설정 관리** | 클러스터 설정 변경 및 적용 |
| **etcd 관리** | 백업, 복구, 업그레이드 시 etcd 스냅샷 수행 |

<br>

# 핵심 기능

## 다양한 환경 지원

Kubespray의 가장 큰 장점 중 하나는 **어떤 환경에서든 동일한 방식으로 클러스터를 배포**할 수 있다는 것이다.

### 퍼블릭 클라우드 환경

AWS, GCP, Azure 등 퍼블릭 클라우드에서 VM을 프로비저닝한 후, Kubespray로 쿠버네티스를 배포할 수 있다. Terraform으로 인프라를 구성하고, Kubespray로 클러스터를 배포하는 패턴이 일반적이다.

```bash
# 예시: Terraform으로 인프라 구성 후 Kubespray 실행
terraform apply                    # VM 프로비저닝
ansible-playbook cluster.yml       # Kubernetes 배포
```

공식 GitHub에서 [Terraform 샘플](https://github.com/kubernetes-sigs/kubespray/tree/master/contrib/terraform)도 제공한다.

### 폐쇄망(Air-gap) 환경

인터넷이 차단된 폐쇄망 환경에서도 쿠버네티스를 배포할 수 있다. 폐쇄망 환경에서는 컨테이너 이미지, 바이너리 파일 등을 미리 다운로드하여 내부에 배포해야 하는데, Kubespray는 이를 위한 [오프라인 배포 가이드](https://github.com/kubernetes-sigs/kubespray/blob/master/docs/operations/offline-environment.md)를 제공한다.

### 핵심 요구사항

어떤 환경이든 **SSH 접근이 가능하고 Python이 설치**되어 있으면 Kubespray를 사용할 수 있다. Ansible이 SSH 기반으로 동작하기 때문이다. 이 덕분에 퍼블릭 클라우드, 프라이빗 클라우드, 온프레미스 환경 모두 동일한 설정으로 배포할 수 있다.

<br>

## HA(고가용성) 구성 지원

Kubespray는 컨트롤 플레인과 etcd의 HA 구성을 기본으로 지원한다.

kubeadm으로 HA 클러스터를 구성하려면 로드밸런서(HAProxy, keepalived 등)를 직접 설정해야 한다. Kubespray는 **워커 노드에 nginx 또는 haproxy를 자동으로 배포**하여 client-side 로드밸런싱을 제공한다.

| 구분 | kubeadm | Kubespray |
| --- | --- | --- |
| **외부 LB** (kubectl 등 외부 접근용) | 직접 구성 | 직접 구성 (kube-vip 사용 가능) |
| **Client-side LB** (kubelet 등 내부 통신용) | 직접 구성 | **자동 배포** |
| **etcd 구성** | Stacked/External 선택 | Stacked/External 선택 (기본: Stacked) |

![kubespray-ha-configuration]({{site.url}}/assets/images/kubespray-ha-configuration.png){: .align-center}

### 왜 Kubespray는 Client-side LB만 자동화하는가?

외부 LB는 환경마다 구성 방식이 완전히 다르다.

| 환경 | 외부 LB 구성 방법 |
| --- | --- |
| AWS | ELB/NLB (AWS API 호출 필요) |
| GCP | GCP Load Balancer (GCP API 호출 필요) |
| 온프레미스 | HAProxy + keepalived + VIP 설정 |
| 베어메탈 | MetalLB, kube-vip 등 |

Kubespray는 "OS 위 소프트웨어"를 자동화하는 도구이지, VIP/방화벽/DNS 같은 인프라 레이어를 자동화하는 도구가 아니다. 반면 Client-side LB는 각 노드에 nginx/haproxy만 설치하면 되므로 어떤 환경에서든 동일하게 동작한다.

외부 LB는 Terraform 같은 인프라 도구로 구성하거나 직접 설정하고, Kubespray는 그 위에서 클러스터를 배포하는 방식이 일반적이다. 단, **kube-vip**을 사용하면 별도 인프라 없이 VIP를 구성할 수 있어서 Kubespray에서 이 옵션을 지원한다.

<br>

## Best Practice 설정 제공

Kubespray는 운영 환경에서 검증된 Best Practice 설정을 기본으로 제공한다. [kubeadm 사전 설정 글]({% post_url 2026-01-18-Kubernetes-Kubeadm-01-2 %})에서 수동으로 진행했던 작업들이 자동화되어 있다.

| 설정 항목 | 설명 |
| --- | --- |
| **시간 동기화 (NTP)** | chrony/ntp 자동 설정 |
| **커널 파라미터** | `net.bridge.bridge-nf-call-iptables`, `net.ipv4.ip_forward` 등 |
| **커널 모듈** | `overlay`, `br_netfilter` 자동 로드 |
| **Swap 비활성화** | 자동 비활성화 |
| **보안 설정** | API Server audit, RBAC 등 |

이러한 설정들은 kubeadm을 사용할 때 직접 해야 했던 작업들이다. Kubespray는 이를 자동화하여 운영 환경에 바로 사용할 수 있는 클러스터를 구성한다.

<br>

## 다양한 환경 지원

Kubespray는 다양한 클라우드, OS, 컨테이너 런타임, 네트워크/스토리지 플러그인을 지원한다.


| Cloud | Supported Linux | CRI | CNI | CSI | Others |
| --- | --- | --- | --- | --- | --- |
| AWS | Flatcar Container Linux | Containerd | Calico | cephfs-provisioner | CoreDNS |
| Google Cloud | Ubuntu 20.04, 22.04 | Docker* | Cilium | rbd-provisioner | MetalLB |
| Equinix | CentOS/RHEL/Oracle 7, 8, 9 | CRI-O | cni-plugins (MacVlan...) | aws-ebs-csi-plugin | Ingress-nginx |
| Huawei Cloud | Alma/Rocky Linux 8, 9 | Crun | Multus | azure-csi-plugin | Kube-vip |
| Upcloud | Fedora 37, 38; CoreOS | Gvisor | Flannel | cinder-csi-plugin | Cert-manager |
| VMware vSphere | Debian 10, 11, 12 | Kata | Cannel | gcp-pd-csi-plugin | ArgoCD |
| OpenStack | OpenSUSE Leap 15.x/Tumbleweed | Youki | Weave | local-path-provisioner | Registry |
| Hetzner | Amazon Linux 2 | | Kube-OVN | local-volume-provisioner | Helm |
| Nif cloud | Kylin V10; UOS Linux; openEuler | | Customize | | Node-Feature-Discovery |

<small>* Docker는 cri-dockerd를 통해 지원</small>

> **주의**: 위 표는 **Kubespray에서 지원하는 각 카테고리별 옵션 목록**이지, **모든 조합이 테스트되고 보장된다는 의미는 아니다**. 특정 조합을 사용하기 전에 [Kubespray CI 테스트 결과](https://github.com/kubernetes-sigs/kubespray/actions)나 [공식 문서](https://kubespray.io/)를 확인하는 것이 좋다.

<br>

# 버전 관리

## 릴리즈 사이클

Kubespray 한 버전은 Kubernetes 3개 minor 버전을 지원한다.

| Kubespray | Kubernetes 지원 버전 |
| --- | --- |
| 2.29.x (master) | 1.31 ~ 1.33 |
| 2.28.x | 1.30 ~ 1.32 |
| 2.27.x | 1.29 ~ 1.31 |

Kubespray는 Kubernetes 최신 버전이 나오면 1~2 버전 늦춰서 안정화된 후 포함한다.

## 운영 환경 버전 추천

| 환경 | 추천 버전 |
| --- | --- |
| **개발(Dev)** | Kubespray 최신 + Kubernetes N-1 |
| **운영(Prod)** | Kubespray 최신-1 + Kubernetes N-2 |

예를 들어, 현재 Kubernetes 최신 버전이 1.34라면:
- 개발 환경: Kubespray 2.29.x + Kubernetes 1.33
- 운영 환경: Kubespray 2.28.x + Kubernetes 1.32

<br>

# 다른 도구와의 비교

## vs. Kops

| 구분 | Kubespray | Kops |
| --- | --- | --- |
| **기반 기술** | Ansible | 자체 오케스트레이션 |
| **지원 환경** | 베어메탈, 모든 클라우드 | AWS, GCP 등 특정 클라우드 |
| **유연성** | 높음 (다중 플랫폼) | 낮음 (클라우드 특화) |
| **추천 대상** | Ansible에 익숙한 팀, 멀티 플랫폼 필요 시 | 단일 클라우드 장기 사용 시 |

Kops는 특정 클라우드의 고유 기능과 더 밀접하게 통합되어 있어, 단일 플랫폼만 사용할 예정이라면 더 나은 선택일 수 있다. 반면 Kubespray는 여러 플랫폼에서 동일한 방식으로 클러스터를 관리하고 싶을 때 적합하다.

## vs. kubeadm

| 구분 | kubeadm | Kubespray |
| --- | --- | --- |
| **역할** | 클러스터 부트스트래핑 | OS 설정 + 클러스터 부트스트래핑 + 애드온 |
| **자동화 범위** | 인증서, etcd, 컨트롤 플레인 | 위 + OS 설정, CRI, CNI, HA 구성 |
| **실행 방식** | 각 노드에서 직접 실행 | 컨트롤 노드에서 원격 실행 (Ansible) |
| **설정 관리** | 수동 또는 별도 도구 필요 | Ansible 변수로 선언적 관리 |

Kubespray는 **v2.3 버전부터 내부적으로 kubeadm을 사용**한다. kubeadm이 클러스터 라이프사이클 관리를 담당하고, Kubespray가 OS 설정 및 전체적인 자동화를 담당하는 구조다. 공식 문서에서는 이를 다음과 같이 설명한다:

> Kubespray has started using kubeadm internally for cluster creation since v2.3 in order to consume life cycle management domain knowledge from it and offload generic OS configuration things from it, which hopefully benefits both sides.

<br>

# Kubernetes The Hard Way vs. Kubespray

Kubespray는 Kubernetes The Hard Way에서 수동으로 수행하는 단계들과 kubeadm이 자동화하는 단계들을 모두 포함하여 더 높은 수준의 자동화를 제공한다.

| Kubespray 작업 | Kubernetes The Hard Way | kubeadm |
| --- | --- | --- |
| **머신 프로비저닝** | [1. Prerequisites]({% post_url 2026-01-05-Kubernetes-Cluster-The-Hard-Way-01 %})<br>[3. Provisioning Compute Resources]({% post_url 2026-01-05-Kubernetes-Cluster-The-Hard-Way-03 %}) | (수동) |
| **OS 사전 설정** | | [1.2. 사전 설정]({% post_url 2026-01-18-Kubernetes-Kubeadm-01-2 %}#사전-설정) |
| └ 시간 동기화 | | 수동 설정 |
| └ 커널 모듈/파라미터 | | 수동 설정 |
| └ Swap 비활성화 | | 수동 설정 |
| **CRI 설치 (containerd)** | [9.1. CNI 및 Worker Node 설정]({% post_url 2026-01-05-Kubernetes-Cluster-The-Hard-Way-09-1 %}) | [1.2. containerd 설치]({% post_url 2026-01-18-Kubernetes-Kubeadm-01-2 %}#cri-설치-containerd) |
| **kubeadm/kubelet/kubectl 설치** | | [1.2. kubeadm 설치]({% post_url 2026-01-18-Kubernetes-Kubeadm-01-2 %}#kubeadm-kubelet-kubectl-설치) |
| **인증서 생성** | [4.1. TLS/mTLS/PKI 개념]({% post_url 2026-01-05-Kubernetes-Cluster-The-Hard-Way-04-1 %})<br>[4.3. CA 및 TLS 인증서 생성]({% post_url 2026-01-05-Kubernetes-Cluster-The-Hard-Way-04-3 %}) | `kubeadm init` (자동) |
| **kubeconfig 생성** | [5.1. kubeconfig 개념]({% post_url 2026-01-05-Kubernetes-Cluster-The-Hard-Way-05-1 %})<br>[5.2. kubeconfig 파일 생성]({% post_url 2026-01-05-Kubernetes-Cluster-The-Hard-Way-05-2 %}) | `kubeadm init` (자동) |
| **etcd 구성** | [7. Bootstrapping etcd]({% post_url 2026-01-05-Kubernetes-Cluster-The-Hard-Way-07 %}) | `kubeadm init` (자동) |
| **컨트롤 플레인 구성** | [8.1. Control Plane 설정 분석]({% post_url 2026-01-05-Kubernetes-Cluster-The-Hard-Way-08-1 %})<br>[8.2. Control Plane 배포]({% post_url 2026-01-05-Kubernetes-Cluster-The-Hard-Way-08-2 %}) | `kubeadm init` (자동) |
| **워커 노드 조인** | [9.2. Worker Node 프로비저닝]({% post_url 2026-01-05-Kubernetes-Cluster-The-Hard-Way-09-2 %}) | `kubeadm join` |
| **CNI 플러그인 설치** | [11. Pod Network Routes]({% post_url 2026-01-05-Kubernetes-Cluster-The-Hard-Way-11 %}) | (수동 설치) |
| **HA 로드밸런서 구성** | (미포함) | (수동) |
| **애드온 설치** | | (수동) |

<br>

## 주요 차이점

| 구분 | Kubernetes The Hard Way | kubeadm | Kubespray |
| --- | --- | --- | --- |
| **자동화 수준** | 없음 (완전 수동) | 부트스트래핑 자동화 | 전체 자동화 |
| **실행 방식** | 각 노드에서 수동 | 각 노드에서 명령 실행 | 컨트롤 노드에서 원격 |
| **OS 사전 설정** | 수동 | 수동 | 자동 |
| **CRI 설치** | 수동 | 수동 | 자동 |
| **CNI 설치** | 수동 | 수동 | 자동 |
| **HA 구성** | 미지원 | 가능 (수동 설정 필요) | 자동 (client-side LB) |
| **설정 관리** | 수동 | 설정 파일 | Ansible 변수 |
| **멱등성** | 없음 | 부분적 | 있음 (Ansible) |

<br>

# 클러스터 구성 절차 개요

본격적인 실습에 앞서, Kubespray를 사용한 클러스터 구성 절차를 간단히 살펴보자. [공식 문서](https://github.com/kubernetes-sigs/kubespray/blob/master/docs/getting_started/getting-started.md)에서 안내하는 단계는 다음과 같다.

## 1. 사전 요구사항

| 항목 | 요구사항 |
| --- | --- |
| Kubernetes | 1.22+ |
| Ansible | 2.14+, Jinja 2.11+ |
| Python | netaddr 라이브러리 |
| 대상 노드 | IPv4 포워딩 활성화, SSH 접근 가능, Python 설치 |
| 네트워크 | 인터넷 접속 가능 (또는 오프라인 설정 필요) |
| 권한 | root 또는 sudo (`ansible_become` 플래그 사용) |

> **참고**: 방화벽은 Kubespray가 관리하지 않는다. 배포 중 문제를 예방하려면 방화벽을 비활성화하거나 필요한 포트를 미리 열어두어야 한다.

## 2. 인벤토리 파일 구성

서버 프로비저닝 후, **내가 구성하고자 하는 클러스터에 맞게** Ansible 인벤토리 파일을 작성한다.

인벤토리 파일에는 다음을 정의한다:
- 각 노드의 호스트명과 IP 주소
- 어떤 노드가 컨트롤 플레인(`kube_control_plane`)인지
- 어떤 노드가 워커(`kube_node`)인지
- etcd를 어디에 배치할지(`etcd`)

```bash
# 샘플 인벤토리 복사
cp -rfp inventory/sample inventory/mycluster

# 인벤토리 파일 수정 (노드 구성에 맞게)
vi inventory/mycluster/inventory.ini

# 그룹 변수 설정
vi inventory/mycluster/group_vars/all.yml           # 모든 노드 (etcd 포함)
vi inventory/mycluster/group_vars/k8s_cluster.yml   # 클러스터 노드
```

## 3. 클러스터 배포 계획

자동화된 도구인 만큼, **구성을 미리 계획하고 설정하는 것이 중요하다**. 한 번 배포하면 CNI나 CIDR처럼 변경하기 어려운 설정들이 있기 때문이다. 배포 전에 어떤 구성으로 클러스터를 배포할지 결정하고, Kubespray [변수 파일](https://github.com/kubernetes-sigs/kubespray/tree/master/inventory/sample/group_vars)에 설정한다.

### 결정해야 할 사항

예를 들어, 아래와 같은 것을 결정해야 한다.

| 결정 항목 | 선택지 예시 | 변수 파일 |
| --- | --- | --- |
| **CNI 플러그인** | Calico, Flannel, Cilium, Weave 등 | `k8s-cluster.yml` |
| **컨테이너 런타임** | containerd, CRI-O | `k8s-cluster.yml` |
| **Kubernetes 버전** | v1.30.x, v1.31.x 등 | `k8s-cluster.yml` |
| **Pod/Service CIDR** | 10.233.64.0/18, 10.233.0.0/18 등 | `k8s-cluster.yml` |
| **클러스터 이름** | cluster.local (기본) | `k8s-cluster.yml` |
| **애드온** | MetalLB, Ingress-nginx, Helm, ArgoCD 등 | `addons.yml` |
| **NTP 설정** | 시간 동기화 서버 | `all.yml` |
| **프록시 설정** | HTTP/HTTPS 프록시 (폐쇄망 환경) | `all.yml` |

주요 설정은 [`k8s-cluster.yml`](https://github.com/kubernetes-sigs/kubespray/blob/master/inventory/sample/group_vars/k8s_cluster/k8s-cluster.yml)에서 확인할 수 있다.

### 예시: CNI 선택

```yaml
# inventory/mycluster/group_vars/k8s_cluster/k8s-cluster.yml
kube_network_plugin: calico  # calico, flannel, cilium, weave 등
```

### 예시: 컨테이너 런타임 선택

```yaml
# inventory/mycluster/group_vars/k8s_cluster/k8s-cluster.yml
container_manager: containerd  # containerd, crio
```

> **팁**: 처음 사용하는 경우, 기본 설정값으로 클러스터를 배포하고 쿠버네티스를 탐색하는 것이 좋다. 나중에 설정을 변경하고 다시 배포할 수 있다.

## 4. 클러스터 배포

```bash
ansible-playbook -i inventory/mycluster/inventory.ini cluster.yml -b -v \
  --private-key=~/.ssh/private_key
```

## 5. 배포 검증

Kubespray는 [Netchecker](https://github.com/kubernetes-sigs/kubespray/blob/master/docs/netcheck.md)를 사용하여 Pod 간 연결성과 DNS 해석을 검증할 수 있다.

<br>

# 결과

Kubespray는 kubeadm 위에 더 높은 수준의 자동화를 제공하는 도구다. Ansible 기반으로 동작하므로 [Ansible 기초]({% post_url 2026-01-12-Kubernetes-Ansible-00 %})를 이해하면 Kubespray의 동작 원리를 더 잘 이해할 수 있다.

1주차에 Kubernetes The Hard Way로 클러스터를 수동 구성하고, 3주차에 kubeadm으로 부트스트래핑을 자동화했다. 이번 4주차에는 Kubespray로 전체 과정을 자동화해 본다. 각 단계를 거치면서 자동화 도구들이 **어떤 작업을 대신해주는지** 체감할 수 있다.

다음 글에서는 실제로 Kubespray를 사용하여 클러스터를 구성해 본다.

<br>