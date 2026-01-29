---
title:  "[Kubernetes] Cluster: Kubespray를 이용해 클러스터 구성하기 - 4.1. 클러스터 배포 - 인벤토리 구성 및 변수 수정"
excerpt: "Kubespray 인벤토리를 구성하고 클러스터 배포를 위한 변수를 수정해보자."
categories:
  - Kubernetes
toc: true
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

이번 글에서는 **Kubespray 클러스터 배포를 위한 인벤토리**를 구성한다.

- **샘플 인벤토리 복사**: `cp -rfp`로 `sample` → `mycluster` 복사
- **inventory.ini 작성**: 단일 노드 클러스터 구성
- **Ansible 그룹 구조**: `kube_control_plane`, `etcd`, `kube_node` 그룹과 `[etcd:children]` 패턴 이해
- **변수 수정**: CNI, kube-proxy 모드, 인증서 자동 갱신 등 설정 변경

<br>

# 인벤토리 구성

## 샘플 인벤토리 복사

Kubespray는 `inventory/sample/` 디렉토리에 샘플 인벤토리를 제공한다. 이를 복사하여 커스텀 인벤토리를 생성한다.

```bash
cp -rfp /root/kubespray/inventory/sample /root/kubespray/inventory/mycluster
```

> **참고**: `-r`(recursive), `-f`(force), `-p`(preserve)로 디렉토리 전체를 원본 메타데이터(권한, 소유자, 시간)와 함께 복사한다.

<br>

## inventory.ini 수정

복사한 `inventory.ini`를 단일 노드 클러스터 구성에 맞게 수정한다:

```bash
cat << EOF > /root/kubespray/inventory/mycluster/inventory.ini
k8s-ctr ansible_host=192.168.10.10 ip=192.168.10.10

[kube_control_plane]
k8s-ctr

[etcd:children]
kube_control_plane

[kube_node]
k8s-ctr
EOF
```

```bash
cat /root/kubespray/inventory/mycluster/inventory.ini
# k8s-ctr ansible_host=192.168.10.10 ip=192.168.10.10
#
# [kube_control_plane]
# k8s-ctr
#
# [etcd:children]
# kube_control_plane
#
# [kube_node]
# k8s-ctr
```

## 인벤토리 구조 분석

### 호스트 정의

```ini
k8s-ctr ansible_host=192.168.10.10 ip=192.168.10.10
```

| 항목 | 값 | 설명 |
|------|----|----- |
| `k8s-ctr` | - | 호스트 별칭 (Ansible에서 사용할 이름) |
| `ansible_host` | `192.168.10.10` | SSH 연결 대상 IP 주소 |
| `ip` | `192.168.10.10` | Kubespray가 사용하는 노드 IP (클러스터 내부 통신) |

> **참고**: `ansible_host`는 Ansible이 SSH 연결 시 사용하는 주소이고, `ip`는 Kubespray가 클러스터 구성 시 사용하는 노드 주소다. 단일 NIC 환경에서는 동일하지만, 멀티 NIC 환경에서는 다를 수 있다.

> **중요**: `ip` 변수를 반드시 지정해야 한다. VirtualBox는 첫 번째 NIC로 NAT 인터페이스(`10.0.2.15`)를 사용하는데, `ip`를 생략하면 Kubespray가 이 주소를 사용하여 클러스터 구성에 실패한다. [맛보기 실습]({% post_url 2026-01-25-Kubernetes-Kubespray-02 %}#트러블-슈팅-virtualbox-nat-ip-문제)에서 직접 겪었던 문제다.

### 그룹 정의

이 인벤토리에는 다음 그룹들이 정의되어 있다:

| 그룹 | 유형 | 설명 |
|------|------|------|
| `all` | 암시적(예약) | Ansible 기본 그룹, 모든 호스트 자동 포함 |
| `kube_control_plane` | 명시적 | Kubernetes Control Plane 노드 |
| `etcd` | 중첩 그룹 | etcd 클러스터 노드 (children으로 정의) |
| `kube_node` | 명시적 | Kubernetes Worker 노드 |

<br>

## 그룹 상세 분석

### all 그룹

```ini
k8s-ctr ansible_host=192.168.10.10 ip=192.168.10.10
```

그룹 선언 없이 정의된 호스트는 암시적으로 `all` 그룹에 포함된다. `all`은 Ansible이 예약한 기본 그룹으로, **인벤토리의 모든 호스트가 자동으로 포함**된다.

### kube_control_plane 그룹

```ini
[kube_control_plane]
k8s-ctr
```

Kubernetes Control Plane 컴포넌트(kube-apiserver, kube-controller-manager, kube-scheduler)가 설치될 노드를 정의한다.

### etcd 그룹 (children)

```ini
[etcd:children]
kube_control_plane
```

`[etcd:children]`은 **중첩 그룹(Nested Group)**을 정의한다. 직접 호스트를 나열하지 않고, 다른 그룹을 자식으로 포함한다.

> **참고**: 중첩 그룹에 대한 자세한 설명은 [Ansible 인벤토리 - 중첩 그룹 (children)]({% post_url 2026-01-12-Kubernetes-Ansible-03 %}#중첩-그룹-children)을 참고하자.

이 설정의 의미는 다음과 같다:
- `etcd` 그룹은 `kube_control_plane` 그룹의 모든 호스트를 상속받는다
- `kube_control_plane`에 `k8s-ctr`이 있으므로, `etcd` 그룹에도 `k8s-ctr`이 포함된다

<br>

중첩 그룹 패턴을 사용하는 이유는 아래와 같다:

| 장점 | 설명 |
|------|------|
| **유연성** | etcd 클러스터 = Control Plane 노드로 자동 연동 |
| **유지보수** | Control Plane 노드 변경 시 etcd 멤버십 자동 변경 |
| **중복 제거** | 같은 호스트를 여러 그룹에 중복 정의할 필요 없음 |

프로덕션 환경에서는 etcd를 별도 노드에 구성하기도 한다. 그 경우 `[etcd:children]` 대신 직접 호스트를 나열하면 된다:

```ini
# 별도 etcd 클러스터 구성 예시
[etcd]
etcd-1 ansible_host=192.168.10.20
etcd-2 ansible_host=192.168.10.21
etcd-3 ansible_host=192.168.10.22
```

### kube_node 그룹

```ini
[kube_node]
k8s-ctr
```

Kubernetes Worker 노드(kubelet, kube-proxy)가 설치될 노드를 정의한다. 이번 실습에서는 단일 노드 클러스터이므로 Control Plane과 동일한 `k8s-ctr`을 지정한다.

<br>

## 그룹 구성 확인

ansible 명령어 그룹 구성을 확인한다.

```bash
ansible -i /root/kubespray/inventory/mycluster/inventory.ini etcd --list-hosts
#   hosts (1):
#     k8s-ctr

ansible -i /root/kubespray/inventory/mycluster/inventory.ini kube_control_plane --list-hosts
#   hosts (1):
#     k8s-ctr

ansible -i /root/kubespray/inventory/mycluster/inventory.ini kube_node --list-hosts
#   hosts (1):
#     k8s-ctr

ansible -i /root/kubespray/inventory/mycluster/inventory.ini all --list-hosts
#   hosts (1):
#     k8s-ctr
```

## 최종 그룹 멤버십

| 그룹 | 멤버 | 비고 |
|------|------|------|
| `all` | `k8s-ctr` | 모든 호스트 자동 포함 |
| `kube_control_plane` | `k8s-ctr` | 직접 정의 |
| `etcd` | `k8s-ctr` | `kube_control_plane`에서 상속 |
| `kube_node` | `k8s-ctr` | 직접 정의 |

단일 노드 클러스터이므로 모든 그룹이 `k8s-ctr` 하나로만 구성된다. 실제 프로덕션 환경에서는 각 그룹에 여러 노드를 분산 배치한다.

<br>

# 변수 수정

인벤토리 구성 후, 클러스터 설정을 변경하려면 `group_vars` 파일을 수정한다.

> **참고**: 변수 배치 전략과 각 변수의 상세 설명은 [변수 분석 시리즈]({% post_url 2026-01-25-Kubernetes-Kubespray-03-02-01 %})를 참고하자.

## 수정할 설정

| 변수 | 기본값 | 변경값 | 이유 |
|------|--------|--------|------|
| `kube_network_plugin` | `calico` | `flannel` | 더 간단한 CNI 테스트 |
| `kube_proxy_mode` | `ipvs` | `iptables` | 기본적인 모드로 변경 |
| `enable_nodelocaldns` | `true` | `false` | 단순화를 위해 비활성화 |
| `auto_renew_certificates` | `false` | `true` | 인증서 자동 갱신 활성화 |

## 변수 수정

```bash
# k8s-cluster.yml 수정
sed -i 's|kube_network_plugin: calico|kube_network_plugin: flannel|g' \
  inventory/mycluster/group_vars/k8s_cluster/k8s-cluster.yml

sed -i 's|kube_proxy_mode: ipvs|kube_proxy_mode: iptables|g' \
  inventory/mycluster/group_vars/k8s_cluster/k8s-cluster.yml

sed -i 's|enable_nodelocaldns: true|enable_nodelocaldns: false|g' \
  inventory/mycluster/group_vars/k8s_cluster/k8s-cluster.yml

sed -i 's|auto_renew_certificates: false|auto_renew_certificates: true|g' \
  inventory/mycluster/group_vars/k8s_cluster/k8s-cluster.yml

# 주석 해제 (인증서 자동 갱신 스케줄)
sed -i 's|# auto_renew_certificates_systemd_calendar|auto_renew_certificates_systemd_calendar|g' \
  inventory/mycluster/group_vars/k8s_cluster/k8s-cluster.yml
```

## 수정 확인

```bash
grep -iE 'kube_network_plugin:|kube_proxy_mode|enable_nodelocaldns:|^auto_renew_certificates' \
  inventory/mycluster/group_vars/k8s_cluster/k8s-cluster.yml
```

```yaml
kube_network_plugin: flannel
kube_proxy_mode: iptables
enable_nodelocaldns: false
auto_renew_certificates: true
auto_renew_certificates_systemd_calendar: "Mon *-*-1,2,3,4,5,6,7 03:00:00"
```

## Flannel 설정 추가

CNI를 Flannel으로 변경했으므로, Flannel 전용 설정 파일도 수정한다:

```bash
# 현재 설정 확인
cat inventory/mycluster/group_vars/k8s_cluster/k8s-net-flannel.yml

# Flannel이 사용할 네트워크 인터페이스 지정
echo "flannel_interface: enp0s8" >> inventory/mycluster/group_vars/k8s_cluster/k8s-net-flannel.yml

# 수정 확인
grep "^[^#]" inventory/mycluster/group_vars/k8s_cluster/k8s-net-flannel.yml
```

> **참고**: `flannel_interface`는 Flannel이 VXLAN 통신에 사용할 네트워크 인터페이스를 지정한다. VirtualBox 환경에서는 Host-Only 네트워크 인터페이스(예: `enp0s8`)를 지정해야 노드 간 통신이 정상 동작한다.

<br>

# 결과

인벤토리 구성과 변수 수정이 완료되었다. 다음 글에서는 `cluster.yml`을 실행하여 클러스터를 배포한다.

<br>

# 참고 자료

- [Kubespray - Building your own inventory](https://kubespray.io/#/docs/ansible/inventory)
- [Ansible 인벤토리 - 중첩 그룹 (children)]({% post_url 2026-01-12-Kubernetes-Ansible-03 %}#중첩-그룹-children)
- [이전 글: 실습 환경 구성]({% post_url 2026-01-25-Kubernetes-Kubespray-04-00 %})

<br>
