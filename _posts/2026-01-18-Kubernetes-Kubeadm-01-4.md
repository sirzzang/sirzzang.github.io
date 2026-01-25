---
title:  "[Kubernetes] Cluster: Kubeadm을 이용해 클러스터 구성하기 - 1.4. Flannel CNI 설치 및 네트워크 확인"
excerpt: "Flannel CNI를 설치하고, iptables와 conntrack을 통해 Kubernetes 네트워킹이 Linux에서 어떻게 구현되는지 확인해 보자."
categories:
  - Kubernetes
toc: true
header:
  teaser: /assets/images/blog-Dev.jpg
tags:
  - Kubernetes
  - On-Premise-K8s-Hands-On-Study
  - On-Premise-K8s-Hands-On-Study-Week-3
hidden: true

---

*[서종호(가시다)](https://www.linkedin.com/in/gasida99/)님의 On-Premise K8s Hands-on Study 3주차 학습 내용을 기반으로 합니다.*

<br>

# TL;DR

이번 글의 목표는 **Flannel CNI 설치 및 Linux 네트워크 스택 확인**이다.

- **Flannel CNI 설치**: Pod 네트워크를 위한 CNI 플러그인 설치
- **네트워크 리소스**: 라우팅, 인터페이스, 브릿지 확인
- **Linux 네트워크 스택**: iptables 규칙, conntrack 연결 추적 확인

<br>

# 들어가며

[이전 글]({% post_url 2026-01-18-Kubernetes-Kubeadm-01-3 %})에서 `kubeadm init`을 실행하고 편의 도구를 설치했다. 하지만 노드 상태가 **NotReady**이고 CoreDNS Pod도 **Pending** 상태였다. 이번 글에서는 CNI 플러그인을 설치하여 Pod 네트워크를 구성하고, Linux 네트워크 스택을 통해 Kubernetes 네트워킹이 어떻게 동작하는지 확인한다.

<br>

# Flannel CNI 설치

## CNI 플러그인의 필요성

지금까지 노드가 **NotReady** 상태였고, CoreDNS Pod도 **Pending** 상태였다. 이는 CNI 플러그인이 없어서 Pod 네트워크를 구성할 수 없었기 때문이다.

[이전 글]({% post_url 2026-01-18-Kubernetes-Kubeadm-01-2 %}#cni-바이너리-및-설정-디렉토리-확인)에서 `kubernetes-cni` 패키지로 표준 CNI 플러그인(`bridge`, `host-local` 등)이 이미 설치되어 있다. 하지만 표준 플러그인만으로는 노드 간 Pod 통신이 불가능하고 수동 설정이 필요하기 때문에, 별도의 CNI 솔루션을 설치해야 한다:

| 표준 CNI 플러그인만 | + Flannel 같은 CNI 솔루션 |
| --- | --- |
| 단일 노드 내 네트워크 설정 (브릿지, IP 할당) | 클러스터 전체 서브넷 자동 할당 |
| 수동으로 각 노드마다 설정 필요 | CNI 설정 파일 자동 생성 |
| 노드 간 통신 불가 | 오버레이 네트워크로 노드 간 통신 |

> 참고: **Hard Way와의 비교**
>
> [Kubernetes The Hard Way 실습]({% post_url 2026-01-05-Kubernetes-Cluster-The-Hard-Way-09-2 %}#cni-설정-파일-배치)에서는 표준 CNI 플러그인만 사용했기 때문에:
> - 각 노드에 `10-bridge.conf` 설정 파일을 **수동으로 배치**해야 했다
> - 노드 간 Pod 통신을 위해 [라우팅 테이블을 수동으로 설정]({% post_url 2026-01-05-Kubernetes-Cluster-The-Hard-Way-11 %})해야 했다 (`ip route add 10.200.1.0/24 via 192.168.10.102` 형태)
> - 이 설정은 **휘발성**이라 재부팅 시 사라졌다
>
> Flannel 같은 CNI 솔루션은 이 모든 작업을 **자동화**한다.

CNI 솔루션은 여러 종류가 있다 (Calico, Cilium, Weave 등). 이 실습에서는 설정이 간단한 **Flannel**을 사용한다.

## Flannel이란

Flannel은 실제 네트워크 설정(veth 생성, IP 할당)을 `bridge`, `host-local` 같은 표준 플러그인에 **위임**하여 수행하게 하고, 자신은 이 플러그인들이 사용할 **설정 파일을 자동 생성**하고 **노드 간 오버레이 네트워크를 구성**하는 역할을 담당한다.

위 역할을 담당하는 핵심 컴포넌트가 **flanneld** 데몬이며, 각 노드에서 실행되어 Pod 네트워크를 구성한다. flanneld는 호스트의 네트워크 인터페이스와 라우팅 테이블을 직접 조작해야 하므로 `hostNetwork: true`로 실행된다.

### Pod 네트워크 구조

Pod 네트워크 구성의 계층별 역할은 다음과 같다:

| 계층 | 역할 |
| --- | --- |
| **Flannel (flanneld)** | CNI 설정 파일 배포 + VXLAN 오버레이 네트워크 구성 |
| **표준 CNI 플러그인 (bridge, host-local)** | Pod 생성 시 veth 쌍 생성, `cni0` 브릿지 연결, IP 할당 |
| **Linux 커널** | [veth]({% post_url 2026-01-05-Kubernetes-Cluster-The-Hard-Way-12 %}#veth-인터페이스와-pod-네트워킹)(Virtual Ethernet) 기능 제공 |

<br>

![kubeadm-flannel]({{site.url}}/assets/images/kubeadm-flannel.png){: .align-center}

flanneld는 Kubernetes API와 통신하여 노드별 서브넷 할당 정보를 동기화하고, 이를 기반으로 라우팅 테이블과 VXLAN 터널을 설정한다.

> 참고: **VXLAN(Virtual Extensible LAN)**
>
> L2 이더넷 프레임을 UDP 패킷으로 캡슐화하는 터널링 프로토콜이다. 서로 다른 물리 네트워크(L3)에 있는 노드들도 마치 같은 L2 네트워크에 있는 것처럼 통신할 수 있다. Flannel은 `flannel.1` 인터페이스를 VXLAN 터널의 끝점(VTEP: VXLAN Tunnel Endpoint)으로 사용하여 다른 노드로 가는 Pod 트래픽을 캡슐화/역캡슐화한다.

각 Pod는 veth 쌍을 통해 노드의 `cni0` 브릿지에 연결된다. veth의 한쪽은 Pod 내부(eth0), 다른 쪽은 호스트의 cni0에 연결된다. `cni0`는 Linux 브릿지로, 같은 노드 내 모든 Pod를 하나의 L2 네트워크로 묶어준다.

- **같은 노드 내 통신**: `cni0` 브릿지가 MAC 주소를 학습하여 직접 전달한다. (Pod1 → veth → cni0 → veth → Pod2)
- **다른 노드 간 통신**: flannel.1(VXLAN 터널 엔드포인트)이 L2 프레임을 UDP로 캡슐화하여 물리 네트워크를 넘어 전달한다. (Pod1 → veth → cni0 → flannel.1 → eth0 → 네트워크 → eth0 → flannel.1 → cni0 → veth → Pod3)

<br>

## 현재 Pod CIDR 확인

Flannel 설치 전에 `kubeadm init` 시 설정한 Pod CIDR이 제대로 적용되었는지 확인한다.

**kube-controller-manager**가 노드별 Pod CIDR 할당을 담당한다. `kubeadm init` 시 설정한 `podSubnet`이 controller-manager의 `--cluster-cidr` 옵션으로 전달되고, `--allocate-node-cidrs=true`가 활성화되어 있으면 새 노드가 join할 때마다 `/24` 서브넷을 자동 할당한다.

```bash
kc describe pod -n kube-system kube-controller-manager-k8s-ctr | grep -E 'cluster-cidr|allocate-node-cidrs'
#   --allocate-node-cidrs=true      # 노드별 CIDR 자동 할당 활성화
#   --cluster-cidr=10.244.0.0/16    # 전체 Pod 네트워크 대역
```

위 설정이 실제로 노드에 반영되었는지 확인한다.

```bash
# 노드별 할당된 CIDR 확인 (각 노드의 spec.podCIDR 필드 조회)
kubectl get nodes -o jsonpath='{range .items[*]}{.metadata.name}{"\t"}{.spec.podCIDR}{"\n"}{end}'
# k8s-ctr	10.244.0.0/24    # 첫 번째 노드에 /24 할당됨
```

Flannel은 이 설정을 그대로 사용한다. Flannel이 CIDR을 새로 만드는 게 아니라, Kubernetes가 이미 할당한 `spec.podCIDR`을 읽어서 해당 노드의 Pod 네트워크를 구성한다.

<br>

## Helm으로 Flannel 설치

이번 실습에서는 Helm을 이용해 Flannel을 설치한다. 
- [Helm으로 설치](https://github.com/flannel-io/flannel?tab=readme-ov-file#deploying-flannel-with-helm) (이번 실습)
- [`kubectl apply -f`로 설치](https://github.com/flannel-io/flannel?tab=readme-ov-file#deploying-flannel-manually)

`kubectl apply -f`를 이용해 직접 설치할 수도 있지만, Helm을 사용하면 다음과 같은 이점이 있다.
- 버전 관리가 용이함
- 설정 변경 시 `helm upgrade`로 간편하게 적용
- `helm uninstall`로 깔끔하게 제거 가능

```bash
# Flannel Helm 저장소 추가
helm repo add flannel https://flannel-io.github.io/flannel
# "flannel" has been added to your repositories

helm repo update
# ...Successfully got an update from the "flannel" chart repository
# Update Complete. ⎈Happy Helming!⎈

# Flannel 네임스페이스 생성
kubectl create namespace kube-flannel
# namespace/kube-flannel created
```

Flannel Helm 설치 시 사용할 설정 파일을 작성한다.

```yaml
# flannel.yaml
podCidr: "10.244.0.0/16"
flannel:
  cniBinDir: "/opt/cni/bin"
  cniConfDir: "/etc/cni/net.d"
  args:
  - "--ip-masq"
  - "--kube-subnet-mgr"
  - "--iface=enp0s9"              # 클러스터 통신용 인터페이스
  backend: "vxlan"
```

| 설정 | 설명 |
| --- | --- |
| `podCidr` | `kubeadm init` 시 설정한 Pod 네트워크 대역 |
| `--ip-masq` | Pod에서 외부로 나가는 트래픽에 SNAT 적용 |
| `--kube-subnet-mgr` | Kubernetes API에서 서브넷 정보 조회 |
| `--iface` | Flannel이 사용할 네트워크 인터페이스 |
| `backend` | 오버레이 네트워크 방식 (vxlan, host-gw 등) |

> 참고: **--iface 옵션**
> 
> 여러 네트워크 인터페이스가 있는 환경에서 Flannel이 사용할 인터페이스를 명시한다.
> Vagrant 환경에서는 `kubelet --node-ip`와 동일하게 Host-Only 네트워크 인터페이스(`enp0s9`)를 지정해야 노드 간 Pod 통신이 정상 작동한다.

```bash
# Flannel 설치
helm install flannel flannel/flannel --namespace kube-flannel --version 0.27.3 -f flannel.yaml
# NAME: flannel
# LAST DEPLOYED: Fri Jan 23 20:23:12 2026
# NAMESPACE: kube-flannel
# STATUS: deployed
# REVISION: 1
```

<br>

## 설치 확인

### Helm 릴리스 확인

Helm으로 배포된 Flannel 릴리스를 확인한다.

`helm list -A`는 모든 네임스페이스의 Helm 릴리스를 조회한다. Flannel이 `kube-flannel` 네임스페이스에 `deployed` 상태로 설치되어 있음을 확인할 수 있다.

```bash
helm list -A
# NAME    NAMESPACE     REVISION  UPDATED                                STATUS    CHART            APP VERSION
# flannel kube-flannel  1         2026-01-23 20:23:12.809390297 +0900 KST deployed  flannel-v0.27.3  v0.27.3
```

`helm get values`는 릴리스에 적용된 사용자 정의 값(User-Supplied Values)을 출력한다. 앞서 설치 시 `-f flannel.yaml`로 지정한 설정이 정상적으로 반영되었는지 확인할 수 있다. 

```bash
helm get values -n kube-flannel flannel
# USER-SUPPLIED VALUES:
# flannel:
#   args:
#   - --ip-masq
#   - --kube-subnet-mgr
#   - --iface=enp0s9
#   backend: vxlan
#   cniBinDir: /opt/cni/bin
#   cniConfDir: /etc/cni/net.d
# podCidr: 10.244.0.0/16
```

### Flannel 리소스 확인

`kube-flannel` 네임스페이스의 리소스를 확인한다.

```bash
kubectl get ds,pod,cm -n kube-flannel -o wide
# NAME                             DESIRED   CURRENT   READY   UP-TO-DATE   AVAILABLE   AGE
# daemonset.apps/kube-flannel-ds   1         1         1       1            1           66s
#
# NAME                        READY   STATUS    RESTARTS   AGE   IP               NODE
# pod/kube-flannel-ds-hv2xd   1/1     Running   0          66s   192.168.10.100   k8s-ctr
#
# NAME                         DATA   AGE
# configmap/kube-flannel-cfg   2      66s
```

Flannel은 **DaemonSet**으로 배포되어 모든 노드에서 실행된다. Pod IP가 `192.168.10.100`(노드 IP)인 것은 `hostNetwork: true` 설정으로 호스트의 네트워크 네임스페이스를 공유하기 때문이다.

### DaemonSet 구성 확인

DaemonSet의 구성을 확인하면 Flannel이 어떻게 CNI 바이너리와 설정 파일을 배포하는지 알 수 있다.

```bash
kubectl describe ds -n kube-flannel kube-flannel-ds
# ...
# Pod Template:
#   Init Containers:
#    install-cni-plugin:
#     Image:      ghcr.io/flannel-io/flannel-cni-plugin:v1.7.1-flannel1
#    install-cni:
#     Image:      ghcr.io/flannel-io/flannel:v0.27.3
#   Containers:
#    kube-flannel:
#     Image:      ghcr.io/flannel-io/flannel:v0.27.3
# ...
```

| 컨테이너 | 역할 |
| --- | --- |
| `install-cni-plugin` (init) | `/opt/cni/bin/flannel` 바이너리 복사 |
| `install-cni` (init) | `/etc/cni/net.d/10-flannel.conflist` 설정 파일 복사 |
| `kube-flannel` (main) | VXLAN 오버레이 네트워크 운영 |

<details markdown="1">
<summary>DaemonSet 전체 상세 정보</summary>

```bash
kubectl describe ds -n kube-flannel kube-flannel-ds
# Name:           kube-flannel-ds
# Selector:       app=flannel
# Node-Selector:  <none>
# Labels:         app=flannel
#                 app.kubernetes.io/managed-by=Helm
#                 tier=node
# Annotations:    deprecated.daemonset.template.generation: 1
#                 meta.helm.sh/release-name: flannel
#                 meta.helm.sh/release-namespace: kube-flannel
# Desired Number of Nodes Scheduled: 1
# Current Number of Nodes Scheduled: 1
# Number of Nodes Scheduled with Up-to-date Pods: 1
# Number of Nodes Scheduled with Available Pods: 1
# Number of Nodes Misscheduled: 0
# Pods Status:  1 Running / 0 Waiting / 0 Succeeded / 0 Failed
# Pod Template:
#   Labels:           app=flannel
#                     tier=node
#   Service Account:  flannel
#   Init Containers:
#    install-cni-plugin:
#     Image:      ghcr.io/flannel-io/flannel-cni-plugin:v1.7.1-flannel1
#     Command:    cp
#     Args:       -f /flannel /opt/cni/bin/flannel
#     Mounts:     /opt/cni/bin from cni-plugin (rw)
#    install-cni:
#     Image:      ghcr.io/flannel-io/flannel:v0.27.3
#     Command:    cp
#     Args:       -f /etc/kube-flannel/cni-conf.json /etc/cni/net.d/10-flannel.conflist
#     Mounts:
#       /etc/cni/net.d from cni (rw)
#       /etc/kube-flannel/ from flannel-cfg (rw)
#   Containers:
#    kube-flannel:
#     Image:      ghcr.io/flannel-io/flannel:v0.27.3
#     Command:    /opt/bin/flanneld --ip-masq --kube-subnet-mgr --iface=enp0s9
#     Requests:   cpu: 100m, memory: 50Mi
#     Environment:
#       POD_NAME:                    (v1:metadata.name)
#       POD_NAMESPACE:               (v1:metadata.namespace)
#       EVENT_QUEUE_DEPTH:          5000
#       CONT_WHEN_CACHE_NOT_READY:  false
#     Mounts:
#       /etc/kube-flannel/ from flannel-cfg (rw)
#       /run/flannel from run (rw)
#       /run/xtables.lock from xtables-lock (rw)
#   Volumes:
#    run:          HostPath /run/flannel
#    cni-plugin:   HostPath /opt/cni/bin
#    cni:          HostPath /etc/cni/net.d
#    flannel-cfg:  ConfigMap kube-flannel-cfg
#    xtables-lock: HostPath /run/xtables.lock (FileOrCreate)
#   Priority Class Name:  system-node-critical
#   Tolerations:          :NoExecute op=Exists
#                         :NoSchedule op=Exists
```

- **Init Containers**: CNI 바이너리와 설정 파일을 호스트에 복사
- **HostPath Volumes**: 호스트의 `/opt/cni/bin`, `/etc/cni/net.d`, `/run/flannel` 등에 직접 접근
- **Priority Class**: `system-node-critical`로 설정되어 클러스터 핵심 컴포넌트로 취급
- **Tolerations**: 모든 taint를 허용하여 Control Plane 노드에서도 실행 가능

</details>

<br>

flanneld 실행 커맨드에 `--iface=enp0s9` 옵션이 적용되었음을 확인할 수 있다.

```bash
kubectl describe ds -n kube-flannel kube-flannel-ds | grep -A5 "Command:"
#     Command:
#       /opt/bin/flanneld
#       --ip-masq
#       --kube-subnet-mgr
#       --iface=enp0s9
```

### CNI 바이너리 및 설정 확인

Init Container가 설치한 파일들을 확인한다:

```bash
# CNI 바이너리 목록
ls -l /opt/cni/bin/
# -rwxr-xr-x. 1 root root 3239200 Dec 12  2024 bandwidth
# -rwxr-xr-x. 1 root root 3731632 Dec 12  2024 bridge
# -rwxr-xr-x. 1 root root 9123544 Dec 12  2024 dhcp
# ...
# -rwxr-xr-x. 1 root root 2903098 Jan 23 20:23 flannel    # ← init container가 복사
# -rwxr-xr-x. 1 root root 2812400 Dec 12  2024 host-local
# -rwxr-xr-x. 1 root root 2953200 Dec 12  2024 loopback
# -rwxr-xr-x. 1 root root 3312488 Dec 12  2024 portmap
# ...
```

`flannel`만 init container가 복사한 것이고(*날짜가 다름*), 나머지는 [kubelet 설치 시]({% post_url 2026-01-18-Kubernetes-Kubeadm-01-2 %}#cni-바이너리-및-설정-디렉토리-확인) `kubernetes-cni` 패키지로 설치된 표준 CNI 플러그인이다. [앞서 설명한 대로](#cni-플러그인의-필요성), Flannel이 내부적으로 이 표준 플러그인들(`bridge`, `host-local`)에 위임하여 실제 네트워크 설정을 수행한다.

```bash
# CNI 설정 파일 (init container가 복사)
tree /etc/cni/net.d/
# /etc/cni/net.d/
# └── 10-flannel.conflist

cat /etc/cni/net.d/10-flannel.conflist | jq
# {
#   "name": "cbr0",
#   "cniVersion": "0.3.1",
#   "plugins": [
#     {
#       "type": "flannel",
#       "delegate": {
#         "hairpinMode": true,
#         "isDefaultGateway": true
#       }
#     },
#     {
#       "type": "portmap",
#       "capabilities": { "portMappings": true }
#     }
#   ]
# }
```

이제 kubelet이 Pod 생성 시 이 설정 파일을 읽고 `flannel` CNI 플러그인을 호출할 수 있다.

<br>

## CNI 설치 후 클러스터 상태 변화

### NetworkReady 상태

[이전 글]({% post_url 2026-01-18-Kubernetes-Kubeadm-01-2 %}#crictl-info-확인)에서 `NetworkReady: false`였던 상태가 CNI 설치 후 `true`로 변경되었다.

```bash
crictl info | jq '.status.conditions'
# [
#   { "status": true, "type": "RuntimeReady" },
#   { "status": true, "type": "NetworkReady" },      # false → true로 변경됨!
#   { "status": true, "type": "ContainerdHasNoDeprecationWarnings" }
# ]
```

### CoreDNS 및 노드 상태

CNI가 정상 동작하면서 Pending 상태였던 CoreDNS Pod가 IP를 할당받고 Running 상태가 된다.

```bash
kubectl get pod -n kube-system -o wide
# NAME                              READY   STATUS    AGE   IP               NODE
# coredns-668d6bf9bc-n8jxf          1/1     Running   44m   10.244.0.3       k8s-ctr
# coredns-668d6bf9bc-z6h69          1/1     Running   44m   10.244.0.2       k8s-ctr
# etcd-k8s-ctr                      1/1     Running   44m   192.168.10.100   k8s-ctr
# kube-apiserver-k8s-ctr            1/1     Running   44m   192.168.10.100   k8s-ctr
# kube-controller-manager-k8s-ctr   1/1     Running   44m   192.168.10.100   k8s-ctr
# kube-proxy-5p6jx                  1/1     Running   44m   192.168.10.100   k8s-ctr
# kube-scheduler-k8s-ctr            1/1     Running   44m   192.168.10.100   k8s-ctr
```

CoreDNS가 정상 기동되면 클러스터 DNS 서비스가 준비되므로, 노드 상태도 `NotReady`에서 `Ready`로 변경된다.

```bash
kubectl get node -o wide
# NAME      STATUS   ROLES           AGE   VERSION    INTERNAL-IP      CONTAINER-RUNTIME
# k8s-ctr   Ready    control-plane   44m   v1.32.11   192.168.10.100   containerd://2.1.5
```

<br>

CNI 플러그인 설치 후 변화를 요약하면 아래와 같다.

| 변화 | Before | After |
| --- | --- | --- |
| `NetworkReady` | false | **true** |
| 노드 상태 | NotReady | **Ready** |
| CoreDNS 상태 | Pending | **Running** |
| CoreDNS IP | `<none>` | **10.244.0.2, 10.244.0.3** |

CoreDNS Pod에 `10.244.0.0/24` 대역의 IP가 할당되었다. 이는 컨트롤 플레인 노드에 할당된 Pod CIDR이다.

<br>

## 네트워크 리소스 확인

CNI 설치 후 노드에 생성된 네트워크 리소스를 확인한다.

### 라우팅 테이블

`kubeadm init` 시 설정한 Pod CIDR(`10.244.0.0/16`)에 대한 라우트가 Flannel에 의해 추가되었는지 확인한다.

```bash
ip -c route | grep 10.244
# 10.244.0.0/24 dev cni0 proto kernel scope link src 10.244.0.1
```

Pod 네트워크(`10.244.0.0/24`)로 향하는 패킷은 `cni0` 브릿지를 통해 전달된다.

### 네트워크 인터페이스

Flannel이 생성한 오버레이 네트워크 인터페이스와 Pod 연결 상태를 확인한다.

```bash
ip addr | grep -E "flannel|cni0|veth"
# 4: flannel.1: ... inet 10.244.0.0/32 scope global flannel.1
# 5: cni0: ...      inet 10.244.0.1/24 brd 10.244.0.255 scope global cni0
# 6: vethd46304de@if2: ... master cni0
# 7: vethc5ce784f@if2: ... master cni0
```

| 인터페이스 | IP | 역할 |
| --- | --- | --- |
| `flannel.1` | 10.244.0.0/32 | VXLAN 터널 엔드포인트 (노드 간 오버레이 통신 - 다른 노드 간 통신) |
| `cni0` | 10.244.0.1/24 | Linux 브릿지 (같은 노드 내 Pod 연결, Pod 게이트웨이) |
| `veth*` | - | Pod-브릿지(cni0) 연결 (2개 = CoreDNS Pod 2개 ) |

### 브릿지 연결

Pod의 veth 인터페이스가 `cni0` 브릿지에 제대로 연결되어 있는지 확인한다.

```bash
bridge link
# 6: vethd46304de@enp0s8: master cni0 state forwarding priority 32 cost 2
# 7: vethc5ce784f@enp0s8: master cni0 state forwarding priority 32 cost 2
```

- **`master cni0`**: 해당 veth가 `cni0` 브릿지에 연결됨
- **`state forwarding`**: 트래픽을 정상적으로 전달하는 상태

2개의 veth가 `cni0`에 연결되어 있으며, 이는 CoreDNS Pod 2개에 해당한다.

### 네트워크 네임스페이스

CNI가 생성한 Pod별 네트워크 네임스페이스를 확인한다.

```bash
lsns -t net | grep cni
# 4026532303 net  2 18164 65535  0 /run/netns/cni-b55a74ef-... /pause
# 4026532378 net  2 18157 65535  1 /run/netns/cni-55b1d32b-... /pause
```

각 Pod는 고유한 네트워크 네임스페이스를 가진다. Hard Way에서 Pod를 직접 배포할 때 보았던 [pause 컨테이너]({% post_url 2026-01-05-Kubernetes-Cluster-The-Hard-Way-12 %}#pause-컨테이너)가 여기서도 동일하게 동작하여 이 네임스페이스를 소유하고 유지한다. CNI는 이 pause 컨테이너의 네트워크 네임스페이스에 veth 쌍을 연결하고 IP를 할당한다. Pod 내 다른 컨테이너들은 pause의 네트워크 네임스페이스를 공유하여 같은 IP와 포트 공간을 사용한다.

<br>

# Linux 네트워크 스택 확인

[이전 글]({% post_url 2026-01-18-Kubernetes-Kubeadm-01-3 %})에서 kube-proxy가 배포되었고, 이번 글에서 Flannel을 설치했다. 이 두 컴포넌트가 모두 배포된 시점에 Linux 네트워크 스택을 살펴보면 Kubernetes 네트워킹이 어떻게 동작하는지 파악할 수 있다. 

## Kubernetes 네트워킹 개요

Kubernetes 네트워킹은 Linux 네트워크 스택 위에서 동작한다. 네트워킹에서의 핵심은 **Linux 네트워크 스택(특히 iptables)을 동적으로 조작**하는 것이다. Pod가 생성되거나 Service가 추가될 때마다 iptables 규칙이 자동으로 업데이트되어 트래픽이 올바른 목적지로 라우팅된다.
- [클러스터 네트워킹](https://kubernetes.io/ko/docs/concepts/cluster-administration/networking/)
- [Service](https://kubernetes.io/ko/docs/concepts/services-networking/service/)


<br>

지금까지 설치한 컴포넌트들이 어떻게 Linux 네트워크를 활용하는지 정리해 보자.

| 컴포넌트 | 설치 시점 | Linux 네트워크 활용 |
| --- | --- | --- |
| **kube-proxy** | [kubeadm init]({% post_url 2026-01-18-Kubernetes-Kubeadm-01-3 %}#static-pod-매니페스트) 시 DaemonSet 배포 | iptables로 Service → Pod 라우팅 |
| **Flannel** | 이번 글에서 Helm으로 설치 | veth, bridge, VXLAN, iptables로 Pod 네트워크 구성 |

> **참고: kube-proxy 모드**
> 
> kube-proxy는 Service 라우팅 구현 방식에 따라 여러 모드를 지원한다:
> - **iptables** (기본값): iptables 규칙으로 DNAT 수행. 대부분의 환경에서 사용
> - **IPVS**: Linux IPVS(IP Virtual Server)를 사용한 L4 로드밸런싱. 대규모 클러스터에서 더 나은 성능
> - **nftables**: iptables의 후속 기술. Kubernetes 1.29+에서 지원
> 
> IPVS나 nftables를 사용하려면 [kubeadm 설정 파일]({% post_url 2026-01-18-Kubernetes-Kubeadm-01-3 %}#kubeadm-설정-파일)에서 `KubeProxyConfiguration`의 `mode` 필드를 명시해야 한다. 이전 글에서 별도 설정 없이 기본값을 사용했으므로 iptables 모드다.
> 
> ```bash
> # kube-proxy ConfigMap에서 현재 모드 확인
> kubectl get cm kube-proxy -n kube-system -o yaml | grep mode
> #     mode: ""   # 빈 문자열 = iptables (기본값)
> ```

두 컴포넌트 모두 **iptables**를 사용하지만 목적이 다르다:
- **kube-proxy**: Service 추상화 (ClusterIP → Pod IP 변환)
- **Flannel**: Pod 네트워크 통신 (SNAT, 포워딩 허용)

## iptables 규칙

iptables 규칙을 확인하여 Kubernetes 네트워킹이 Linux 수준에서 어떻게 구현되는지 이해해 보자.

### iptables 개요

iptables는 Linux 커널의 패킷 필터링 프레임워크다. 패킷이 들어오면 **테이블**(nat, filter 등) 내의 **체인**(PREROUTING, FORWARD 등)을 순서대로 거치며, 각 체인의 규칙에 따라 패킷이 처리된다.

Kubernetes에서 iptables 규칙은 **Flannel**과 **kube-proxy**가 각각 다른 시점에 추가한다:

| 컴포넌트 | 규칙 추가 시점 | 체인 | 역할 |
| --- | --- | --- | --- |
| **Flannel** | flanneld 시작 시 | `FLANNEL-POSTRTG` (nat) | Pod → 외부 통신 시 SNAT |
| **Flannel** | flanneld 시작 시 | `FLANNEL-FWD` (filter) | Pod 네트워크 트래픽 포워딩 허용 |
| **kube-proxy** | Service 생성 시 | `KUBE-SERVICES` (nat) | Service ClusterIP 매칭 진입점 |
| **kube-proxy** | Service 생성 시 | `KUBE-SVC-*` (nat) | 서비스별 로드밸런싱 |
| **kube-proxy** | Service 생성 시 | `KUBE-SEP-*` (nat) | 실제 Pod IP로 DNAT |
| **kube-proxy** | Service 생성 시 | `KUBE-FORWARD` (filter) | 마킹된 패킷 포워딩 허용 |

### nat 테이블

nat 테이블은 주소 변환(NAT)을 담당한다. Service ClusterIP → Pod IP 변환(DNAT)과 Pod → 외부 통신 시 IP 변환(SNAT)이 여기서 처리된다.

<br>

**Flannel이 추가한 규칙** (flanneld 시작 시):

```bash
# Pod → 외부 통신 시 SNAT (--ip-masq 옵션)
iptables -t nat -S | grep FLANNEL
# -A POSTROUTING -m comment --comment "flanneld masq" -j FLANNEL-POSTRTG
# -A FLANNEL-POSTRTG -s 10.244.0.0/16 ! -d 224.0.0.0/4 ... -j MASQUERADE
```

Pod(`10.244.0.0/16`)에서 외부로 나가는 트래픽의 출발지 IP를 노드 IP로 변환(SNAT)한다. 이렇게 해야 외부 네트워크에서 응답을 노드로 돌려보낼 수 있고, 노드가 다시 Pod로 전달한다. `--ip-masq` 옵션이 이 규칙을 활성화한다.

<br>

**kube-proxy가 추가한 규칙** (Service 생성 시):

현재 시점에 이미 존재하는 Service들이 있어서 kube-proxy가 해당 규칙을 생성해 둔 상태다:

| Service | ClusterIP | 생성 시점 |
| --- | --- | --- |
| `default/kubernetes` | 10.96.0.1:443 | [kubeadm init]({% post_url 2026-01-18-Kubernetes-Kubeadm-01-3 %}#kubeadm-init-실행) 시 자동 생성 (API Server) |
| `kube-system/kube-dns` | 10.96.0.10:53 | [CoreDNS addon]({% post_url 2026-01-18-Kubernetes-Kubeadm-01-3 %}#coredns-kube-proxy) 배포 시 생성 |

```bash
# kube-dns Service (10.96.0.10:53) → CoreDNS Pod로 DNAT
iptables -t nat -S | grep "kube-dns:dns ->"
# -A KUBE-SVC-TCOU7JCQXEZGVUNU ... --probability 0.50000000000 -j KUBE-SEP-YIL6JZP7A3QYXJU2
# -A KUBE-SVC-TCOU7JCQXEZGVUNU ... -j KUBE-SEP-6E7XQMQ4RAYOWTTM
# (2개의 CoreDNS Pod에 50% 확률로 로드밸런싱)
```

<details markdown="1">
<summary>nat 테이블 전체 규칙</summary>

```bash
iptables -t nat -S
# -P PREROUTING ACCEPT
# -P INPUT ACCEPT
# -P OUTPUT ACCEPT
# -P POSTROUTING ACCEPT
# -N FLANNEL-POSTRTG
# -N KUBE-MARK-MASQ
# -N KUBE-NODEPORTS
# -N KUBE-POSTROUTING
# -N KUBE-SEP-6E7XQMQ4RAYOWTTM
# -N KUBE-SEP-ETI7FUQQE3BS2IXE
# ... (생략)
# -N KUBE-SERVICES
# -N KUBE-SVC-ERIFXISQEP7F7OF4
# -N KUBE-SVC-NPX46M4PTMTKRN6Y
# -N KUBE-SVC-TCOU7JCQXEZGVUNU
# [kube-proxy] 모든 들어오는/나가는 패킷을 KUBE-SERVICES 체인으로 전달
# [kube-proxy] 들어오는/나가는 패킷을 KUBE-SERVICES 체인으로 전달
# -A PREROUTING -m comment --comment "kubernetes service portals" -j KUBE-SERVICES
# -A OUTPUT -m comment --comment "kubernetes service portals" -j KUBE-SERVICES
# -A POSTROUTING -m comment --comment "kubernetes postrouting rules" -j KUBE-POSTROUTING
#
# [Flannel] Pod → 외부 통신 시 SNAT 처리를 위해 FLANNEL-POSTRTG로 전달
# -A POSTROUTING -m comment --comment "flanneld masq" -j FLANNEL-POSTRTG
#
# [Flannel] Pod CIDR에서 출발하는 트래픽을 노드 IP로 MASQUERADE (SNAT)
# -A FLANNEL-POSTRTG -s 10.244.0.0/16 ! -d 224.0.0.0/4 ... -j MASQUERADE --random-fully
#
# [kube-proxy] kube-dns Service (10.96.0.10:53) → CoreDNS Pod로 DNAT
# -A KUBE-SERVICES -d 10.96.0.10/32 -p udp --dport 53 -j KUBE-SVC-TCOU7JCQXEZGVUNU
# -A KUBE-SVC-TCOU7JCQXEZGVUNU ... --probability 0.50 -j KUBE-SEP-YIL6JZP7A3QYXJU2
# -A KUBE-SVC-TCOU7JCQXEZGVUNU ... -j KUBE-SEP-6E7XQMQ4RAYOWTTM
# -A KUBE-SEP-YIL6JZP7A3QYXJU2 -p udp -j DNAT --to-destination 10.244.0.2:53
# -A KUBE-SEP-6E7XQMQ4RAYOWTTM -p udp -j DNAT --to-destination 10.244.0.3:53
#
# [kube-proxy] kubernetes Service (10.96.0.1:443) → API Server로 DNAT
# -A KUBE-SERVICES -d 10.96.0.1/32 -p tcp --dport 443 -j KUBE-SVC-NPX46M4PTMTKRN6Y
# -A KUBE-SVC-NPX46M4PTMTKRN6Y ... -j KUBE-SEP-ETI7FUQQE3BS2IXE
# -A KUBE-SEP-ETI7FUQQE3BS2IXE -p tcp -j DNAT --to-destination 192.168.10.100:6443
```

</details>

<br>

### filter 테이블

filter 테이블은 패킷 필터링(허용/차단)을 담당한다. Pod 네트워크 트래픽의 포워딩 허용이 여기서 처리된다.

**Flannel이 추가한 규칙** (flanneld 시작 시):

```bash
# Pod 네트워크 트래픽 포워딩 허용
iptables -t filter -S | grep FLANNEL
# -A FORWARD -m comment --comment "flanneld forward" -j FLANNEL-FWD
# -A FLANNEL-FWD -s 10.244.0.0/16 ... -j ACCEPT
# -A FLANNEL-FWD -d 10.244.0.0/16 ... -j ACCEPT
```

Pod CIDR(`10.244.0.0/16`)에서 출발하거나 도착하는 트래픽의 포워딩을 허용한다.

<br>

**kube-proxy가 추가한 규칙** (Service 생성 시):

```bash
# 마킹된 패킷 포워딩 허용
iptables -t filter -S | grep KUBE-FORWARD
# -A KUBE-FORWARD -m conntrack --ctstate INVALID -j DROP
# -A KUBE-FORWARD -m mark --mark 0x4000/0x4000 -j ACCEPT
# -A KUBE-FORWARD -m conntrack --ctstate RELATED,ESTABLISHED -j ACCEPT
```

kube-proxy가 마킹한 패킷(`0x4000`)과 기존 연결의 응답 패킷(`RELATED,ESTABLISHED`)을 포워딩 허용한다. 잘못된 패킷(`INVALID`)은 드롭한다.

<details markdown="1">
<summary>filter 테이블 전체 규칙</summary>

```bash
iptables -t filter -S
# -P INPUT ACCEPT
# -P FORWARD ACCEPT
# -P OUTPUT ACCEPT
# -N FLANNEL-FWD
# -N KUBE-EXTERNAL-SERVICES
# -N KUBE-FIREWALL
# -N KUBE-FORWARD
# -N KUBE-NODEPORTS
# -N KUBE-SERVICES
#
# [Flannel] Pod 네트워크 트래픽 포워딩 허용
# -A FORWARD -m comment --comment "flanneld forward" -j FLANNEL-FWD
# -A FLANNEL-FWD -s 10.244.0.0/16 -m comment --comment "flanneld forward" -j ACCEPT
# -A FLANNEL-FWD -d 10.244.0.0/16 -m comment --comment "flanneld forward" -j ACCEPT
#
# [kube-proxy] 마킹된 패킷 및 기존 연결 포워딩 허용
# -A KUBE-FORWARD -m conntrack --ctstate INVALID -j DROP
# -A KUBE-FORWARD -m mark --mark 0x4000/0x4000 -j ACCEPT
# -A KUBE-FORWARD -m conntrack --ctstate RELATED,ESTABLISHED -j ACCEPT
```

</details>

<br>

## conntrack

conntrack 테이블을 확인하여 iptables NAT 규칙이 적용된 연결이 어떻게 추적되는지 이해해 보자.

### conntrack 개요

**conntrack(Connection Tracking)**은 Linux 커널의 네트워크 연결 상태 추적 시스템이다. kube-proxy가 Service의 ClusterIP를 Pod IP로 변환(DNAT)할 때 conntrack 테이블을 사용하여 응답 패킷을 올바른 출발지로 되돌린다.

| 역할 | 설명 |
| --- | --- |
| **NAT 상태 추적** | DNAT 규칙이 적용된 연결의 원본 주소를 기억하여 응답 패킷을 올바르게 라우팅 |
| **연결 상태 관리** | TCP 연결의 상태(ESTABLISHED, TIME_WAIT 등)를 추적하여 stateful 방화벽 기능 제공 |
| **Service 로드밸런싱** | 동일 클라이언트의 후속 패킷이 같은 Pod로 전달되도록 연결 유지 |
| **성능 최적화** | 이미 추적된 연결은 iptables 규칙을 다시 평가하지 않고 빠르게 처리 |

```bash
# conntrack 도구 설치
dnf install -y conntrack-tools
```

### 전체 conntrack 엔트리 조회

```bash
# 전체 conntrack 엔트리 조회
conntrack -L
# conntrack v1.4.8 (conntrack-tools): 286 flow entries have been shown.
```

<details markdown="1">
<summary>전체 출력 보기 (286 entries)</summary>

```
tcp      6 65 TIME_WAIT src=127.0.0.1 dst=127.0.0.1 sport=56844 dport=2381 src=127.0.0.1 dst=127.0.0.1 sport=2381 dport=56844 [ASSURED] mark=0
tcp      6 15 TIME_WAIT src=10.244.0.1 dst=10.244.0.2 sport=46574 dport=8080 src=10.244.0.2 dst=10.244.0.1 sport=8080 dport=46574 [ASSURED] mark=0
tcp      6 86399 ESTABLISHED src=127.0.0.1 dst=127.0.0.1 sport=46870 dport=2379 src=127.0.0.1 dst=127.0.0.1 sport=2379 dport=46870 [ASSURED] mark=0
tcp      6 86383 ESTABLISHED src=10.244.0.3 dst=10.96.0.1 sport=48242 dport=443 src=192.168.10.100 dst=10.244.0.3 sport=6443 dport=48242 [ASSURED] mark=0
tcp      6 86399 ESTABLISHED src=192.168.10.100 dst=192.168.10.100 sport=54874 dport=6443 src=192.168.10.100 dst=192.168.10.100 sport=6443 dport=54874 [ASSURED] mark=0
udp      17 27 src=10.0.2.15 dst=175.195.167.194 sport=56947 dport=123 src=175.195.167.194 dst=10.0.2.15 sport=123 dport=56947 mark=0
udp      17 26 src=10.0.2.15 dst=168.126.63.1 sport=46942 dport=53 src=168.126.63.1 dst=10.0.2.15 sport=53 dport=46942 mark=0
tcp      6 86400 ESTABLISHED src=10.0.2.2 dst=10.0.2.15 sport=61614 dport=22 src=10.0.2.15 dst=10.0.2.2 sport=22 dport=61614 [ASSURED] mark=0
... (이하 생략)
```

</details>

<br>

**conntrack 엔트리 형식:**

```
tcp 6 86399 ESTABLISHED src=10.244.0.3 dst=10.96.0.1 sport=48242 dport=443 src=192.168.10.100 dst=10.244.0.3 sport=6443 dport=48242 [ASSURED]
```

| 필드 | 예시 값 | 설명 |
| --- | --- | --- |
| 프로토콜 | `tcp` | 프로토콜 이름 |
| 프로토콜 번호 | `6` | 6=TCP, 17=UDP |
| TTL | `86399` | 연결 만료까지 남은 시간 (초) |
| 연결 상태 | `ESTABLISHED` | TCP 상태 (ESTABLISHED, TIME_WAIT, CLOSE 등) |
| **원본 패킷 (요청)** | `src=10.244.0.3 dst=10.96.0.1 sport=48242 dport=443` | CoreDNS Pod → kubernetes Service ClusterIP |
| **응답 패킷 (DNAT 역변환)** | `src=192.168.10.100 dst=10.244.0.3 sport=6443 dport=48242` | API Server → CoreDNS Pod |
| 플래그 | `[ASSURED]` | 양방향 트래픽이 확인된 연결 |

### TCP 연결만 조회

```bash
# TCP 연결만 보기
conntrack -L -p tcp
# conntrack v1.4.8 (conntrack-tools): 279 flow entries have been shown.
```

### ESTABLISHED 상태만 조회

```bash
# ESTABLISHED 상태만 보기 (활성 연결)
conntrack -L -p tcp --state ESTABLISHED
# tcp  6 86376 ESTABLISHED src=127.0.0.1 dst=127.0.0.1 sport=47672 dport=2379 ... [ASSURED]        # etcd 연결
# tcp  6 86388 ESTABLISHED src=192.168.10.100 dst=192.168.10.100 sport=38154 dport=6443 ... [ASSURED]  # API Server 연결
# tcp  6 86375 ESTABLISHED src=10.244.0.3 dst=10.96.0.1 sport=48242 dport=443 src=192.168.10.100 dst=10.244.0.3 sport=6443 dport=48242 [ASSURED]  # Service DNAT
# tcp  6 86399 ESTABLISHED src=10.0.2.2 dst=10.0.2.15 sport=61614 dport=22 ... [ASSURED]           # SSH 연결
# ... (68 flow entries)
```

**주요 ESTABLISHED 연결 분석:**

| 연결 유형 | 예시 | 설명 |
| --- | --- | --- |
| etcd 연결 | `127.0.0.1:* → 127.0.0.1:2379` | API Server, Controller Manager 등이 etcd에 연결 (다수) |
| API Server 연결 | `192.168.10.100:* → 192.168.10.100:6443` | 컴포넌트들이 API Server에 연결 |
| **Service DNAT** | `10.244.0.3:48242 → 10.96.0.1:443` ↔ `192.168.10.100:6443 → 10.244.0.3` | CoreDNS가 `kubernetes` Service를 통해 API Server에 연결 |
| SSH 연결 | `10.0.2.2:61614 → 10.0.2.15:22` | Vagrant SSH 연결 |

> **Service DNAT 추적 예시**: `10.244.0.3`(CoreDNS Pod)이 `10.96.0.1:443`(kubernetes Service ClusterIP)에 접속하면, conntrack은 이 연결을 추적하고 응답 패킷이 `192.168.10.100:6443`(실제 API Server)에서 올 때 원래 목적지인 `10.244.0.3`으로 정확히 전달한다.

### 특정 포트 관련 연결

```bash
# Service(443) 관련 연결 확인
conntrack -L | grep dport=443
# tcp  6 86376 ESTABLISHED src=10.244.0.3 dst=10.96.0.1 sport=48242 dport=443 src=192.168.10.100 dst=10.244.0.3 sport=6443 dport=48242 [ASSURED]
# tcp  6 86389 ESTABLISHED src=10.0.2.15 dst=10.96.0.1 sport=39156 dport=443 src=192.168.10.100 dst=10.0.2.15 sport=6443 dport=6826 [ASSURED]
# tcp  6 86383 ESTABLISHED src=10.244.0.2 dst=10.96.0.1 sport=40304 dport=443 src=192.168.10.100 dst=10.244.0.2 sport=6443 dport=40304 [ASSURED]
```

위 결과에서 `dst=10.96.0.1`(kubernetes Service ClusterIP)로 향하는 연결이 실제로는 `192.168.10.100:6443`(API Server)으로 DNAT되어 처리됨을 확인할 수 있다.

### 실시간 이벤트 추적

```bash
# 실시간 conntrack 이벤트 추적 (Ctrl+C로 종료)
conntrack -E
#     [NEW] tcp      6 120 SYN_SENT src=192.168.10.100 dst=192.168.10.100 sport=34518 dport=6443 [UNREPLIED]
#  [UPDATE] tcp      6 60 SYN_RECV src=192.168.10.100 dst=192.168.10.100 sport=34518 dport=6443
#  [UPDATE] tcp      6 86400 ESTABLISHED src=192.168.10.100 dst=192.168.10.100 sport=34518 dport=6443 [ASSURED]
#  [UPDATE] tcp      6 120 FIN_WAIT src=192.168.10.100 dst=192.168.10.100 sport=34518 dport=6443 [ASSURED]
#  [UPDATE] tcp      6 300 CLOSE_WAIT src=192.168.10.100 dst=192.168.10.100 sport=34518 dport=6443 [ASSURED]
#  [UPDATE] tcp      6 10 CLOSE src=192.168.10.100 dst=192.168.10.100 sport=34518 dport=6443 [ASSURED]
```

TCP 연결의 전체 생명주기를 실시간으로 관찰할 수 있다: `SYN_SENT` → `SYN_RECV` → `ESTABLISHED` → `FIN_WAIT` → `CLOSE_WAIT` → `CLOSE`.

### conntrack 커널 파라미터

```bash
# conntrack 관련 커널 파라미터 확인
sysctl -a | grep conntrack
# net.netfilter.nf_conntrack_buckets = 65536
# net.netfilter.nf_conntrack_count = 420              # 현재 추적 중인 연결 수
# net.netfilter.nf_conntrack_max = 131072             # 최대 추적 가능 연결 수
# net.netfilter.nf_conntrack_tcp_timeout_close = 10
# net.netfilter.nf_conntrack_tcp_timeout_close_wait = 3600
# net.netfilter.nf_conntrack_tcp_timeout_established = 86400
# net.netfilter.nf_conntrack_tcp_timeout_fin_wait = 120
# net.netfilter.nf_conntrack_tcp_timeout_syn_recv = 60
# net.netfilter.nf_conntrack_tcp_timeout_syn_sent = 120
# net.netfilter.nf_conntrack_tcp_timeout_time_wait = 120
# net.netfilter.nf_conntrack_udp_timeout = 30
# net.netfilter.nf_conntrack_udp_timeout_stream = 120
# ... (이하 생략)
```

| 파라미터 | 값 | 설명 |
| --- | --- | --- |
| `nf_conntrack_max` | 131072 | conntrack 테이블 최대 크기(최대 엔트리 수) |
| `nf_conntrack_count` | 420 | 현재 추적 중인 연결 수(현재 사용 중) |
| `nf_conntrack_buckets` | 65536 | 해시 테이블 버킷 수 |
| `nf_conntrack_tcp_timeout_established` | 86400초 (24시간) | ESTABLISHED 연결 유지 시간 |
| `nf_conntrack_tcp_timeout_close_wait` | 3600초 (1시간) | CLOSE_WAIT 상태 유지 시간 |
| `nf_conntrack_tcp_timeout_time_wait` | 120초 | TIME_WAIT 상태 유지 시간 |
| `nf_conntrack_udp_timeout` | 30초 | UDP 연결 타임아웃 |

> **트러블슈팅 팁**: 대규모 클러스터에서 `nf_conntrack: table full, dropping packet` 에러가 발생하면 `nf_conntrack_max` 값을 증가시켜야 한다. 현재 사용률은 `count/max = 420/131072 ≈ 0.3%`로 여유롭다. `conntrack -S`로 통계를 확인하여 drop된 패킷 수를 모니터링할 수 있다.

<br>

# 결과

이 단계를 완료하면 다음과 같은 결과를 얻을 수 있다:

| 항목 | 결과 |
| --- | --- |
| CNI | Flannel v0.27.3 설치, 노드 상태 Ready |
| 네트워크 인터페이스 | `cni0` 브릿지, `flannel.1` VXLAN 인터페이스 생성 |
| iptables | `KUBE-*`, `FLANNEL-*` 체인 구성 완료 |
| conntrack | Service DNAT 연결 추적 정상 동작 |

<br>

CNI 설치로 Pod 네트워크가 구성되었다. [다음 글]({% post_url 2026-01-18-Kubernetes-Kubeadm-01-5 %})에서는 노드 정보, 인증서, kubeconfig, Static Pod, 애드온 등 컨트롤 플레인 컴포넌트를 상세히 확인한다.

