---
title:  "[Kubernetes] Cluster: Kubespray를 이용해 클러스터 구성하기 - 3.3.1. cluster.yml - 태스크 구조"
excerpt: "cluster.yml의 15개 플레이와 태스크 구조를 --list-tasks로 분석해보자."
categories:
  - Kubernetes
toc: true
hidden: true
header:
  teaser: /assets/images/blog-Dev.jpg
tags:
  - Kubernetes
  - Kubespray
  - Ansible
  - On-Premise-K8s-Hands-On-Study
  - On-Premise-K8s-Hands-On-Study-Week-4

---

*[서종호(가시다)](https://www.linkedin.com/in/gasida99/)님의 On-Premise K8s Hands-on Study 4주차 학습 내용을 기반으로 합니다.*

<br>

# TL;DR

이번 글에서는 **cluster.yml의 태스크 구조**를 `--list-tasks` 옵션으로 분석한다.

- **15개 플레이**: 버전 체크부터 resolv.conf 설정까지 순차 실행
- **Warning 메시지**: bastion, k8s_cluster, calico_rr 등 무시 가능한 경고
- **주요 태스크 영역**: OS 준비, 컨테이너 런타임, etcd, 컨트롤 플레인, CNI, 애드온


<br>

# 태스크 목록 확인

## 명령어 실행

```bash
ansible-playbook -i inventory/mycluster/inventory.ini cluster.yml \
  -e kube_version="1.33.3" \
  --list-tasks > cluster-list-tasks.log
```

`--list-tasks` 옵션은 플레이북을 실제로 실행하지 않고 **실행될 태스크 목록만 출력**한다. 플레이북 구조를 파악하거나, 변경 사항이 어떤 태스크에 영향을 주는지 미리 확인할 때 유용하다.

명령어 실행 시 주의해야 할 사항은 아래와 같다:

- **반드시 `~/kubespray` 디렉토리**에서 실행해야 한다
- **root 권한**이 필요하다 (실습 환경에서는 이미 root)

root 권한이 필요한 이유는 Kubespray가 다음 작업들을 수행하기 때문이다:

| 작업 | 경로/대상 |
|------|-----------|
| SSL 인증서 작성 | `/etc/kubernetes/` |
| 패키지 설치 | apt, yum 등 |
| systemd 데몬 관리 | kubelet, containerd 등 |
| 네트워크 설정 변경 | iptables, ipvs 등 |
| 커널 파라미터 수정 | sysctl |

<br>

## Warning 메시지 분석

명령 실행 시 다음과 같은 경고가 발생한다:

```
[WARNING]: Could not match supplied host pattern, ignoring: bastion
[WARNING]: Could not match supplied host pattern, ignoring: k8s_cluster
[WARNING]: Could not match supplied host pattern, ignoring: calico_rr
[WARNING]: Could not match supplied host pattern, ignoring: _kubespray_needs_etcd
```

현재 `inventory.ini` 구성을 다시 확인하자:

```ini
k8s-ctr ansible_host=192.168.10.10 ip=192.168.10.10

[kube_control_plane]
k8s-ctr

[etcd:children]
kube_control_plane

[kube_node]
k8s-ctr
```

`inventory.ini` 구성에 의하면, 경고 메시지는 정상적이다.

| 경고 메시지 | 의미 | 영향 |
|------------|------|------|
| `bastion` | Jump host(Bastion 서버) 그룹 없음 | 직접 접속 환경이면 불필요 |
| `k8s_cluster` | `k8s_cluster` 그룹 미정의 | 내부적으로 자동 처리됨 |
| `calico_rr` | Calico Route Reflector 그룹 없음 | Flannel 사용 시 불필요 |
| `_kubespray_needs_etcd` | 내부 동적 그룹 | 자동 생성되므로 무시 가능 |

이 경고들은 단일 노드 테스트 환경에서 정상적으로 발생하며, 클러스터 설치에 영향을 주지 않는다.

<br>

# 플레이 구조 개요

`--list-tasks` 결과를 보면 총 **15개의 플레이**가 순차 실행된다:

| 플레이 | 대상 호스트 | 주요 역할 |
|--------|------------|----------|
| #1 | all | Ansible 버전 체크 |
| #2 | all | 인벤토리 검증 |
| #3 | bastion[0] | Bastion SSH 설정 |
| #4 | k8s_cluster:etcd:calico_rr | OS 부트스트랩 |
| #5 | k8s_cluster:etcd:calico_rr | 팩트 수집 |
| #6 | k8s_cluster:etcd | etcd 사전 준비, 컨테이너 런타임 설치 |
| #7 | kube_node | etcd 클라이언트 인증서 필요 여부 확인 |
| #8 | etcd:kube_control_plane:_kubespray_needs_etcd | etcd 설치 |
| #9 | k8s_cluster | kubelet 설치 |
| #10 | kube_control_plane | 컨트롤 플레인 설치 |
| #11 | k8s_cluster | kubeadm join, CNI 설치 |
| #12 | calico_rr | Calico Route Reflector 설치 |
| #13 | kube_control_plane[0] | Windows 노드 패치 |
| #14 | kube_control_plane | 애드온 설치 |
| #15 | k8s_cluster | resolv.conf 최종 설정 |

<br>

# 주요 태스크 영역

각 플레이에서 실행되는 핵심 태스크들을 영역별로 분류하면:

## 사전 검증 (Play #1-2)

```bash
Check {{ minimal_ansible_version }} <= Ansible version < {{ maximal_ansible_version }}
Check that python netaddr is installed
Stop if kube_control_plane group is empty
Stop if unsupported version of Kubernetes
```

## OS 준비 (Play #4)

```bash
bootstrap_os : Fetch /etc/os-release
bootstrap_os : Include vars
system_packages : Manage packages
bootstrap_os : Gather facts
```

## 컨테이너 런타임 (Play #6)

```bash
container-engine/containerd : Containerd | Download containerd
container-engine/containerd : Containerd | Copy containerd config file
container-engine/runc : Runc | Download runc binary
container-engine/crictl : Install crictl
```

## etcd (Play #8)

```bash
etcd : Check etcd certs
etcd : Generate etcd certs
etcd : Install etcd
etcd : Configure etcd
```

## Kubernetes 노드 (Play #9)

```bash
kubernetes/node : Install | Copy kubeadm binary from download dir
kubernetes/node : Install | Copy kubelet binary from download dir
kubernetes/node : Write kubelet config file
kubernetes/node : Enable kubelet
```

## 컨트롤 플레인 (Play #10)

```bash
kubernetes/control-plane : Install | Copy kubectl binary from download dir
kubernetes/control-plane : Kubeadm | Create kubeadm config
kubernetes/control-plane : Kubeadm | Initialize first control plane node
kubernetes/control-plane : Create kubeadm token for joining nodes
```

## CNI (Play #11)

```bash
network_plugin/cni : CNI | Copy cni plugins
network_plugin/flannel : Flannel | Create Flannel manifests
network_plugin/flannel : Flannel | Start Resources
```

## 애드온 (Play #14)

```bash
kubernetes-apps/ansible : Kubernetes Apps | CoreDNS
kubernetes-apps/helm : Helm | Download helm
kubernetes-apps/metrics_server : Metrics Server | Apply manifests
```

<br>

# 결과

이번 글에서 `--list-tasks`를 통해 cluster.yml의 전체 태스크 구조를 파악했다.

| 항목 | 내용 |
|------|------|
| 플레이 수 | 15개 |
| 주요 단계 | 검증 → OS → 런타임 → etcd → 노드 → 컨트롤 플레인 → CNI → 애드온 |
| Warning | 단일 노드 환경에서 정상 발생, 무시 가능 |

다음 글에서는 cluster.yml이 import하는 첫 번째 플레이북인 [boilerplate.yml]({% post_url 2026-01-25-Kubernetes-Kubespray-03-03-02 %})을 분석한다.

<br>

# 참고 자료

- [Ansible --list-tasks 옵션](https://docs.ansible.com/ansible/latest/cli/ansible-playbook.html#cmdoption-ansible-playbook-list-tasks)
- [이전 글: cluster.yml 흐름]({% post_url 2026-01-25-Kubernetes-Kubespray-03-03-00 %})

<br>
