---
title:  "[Kubernetes] Cluster: 내 손으로 클러스터 구성하기 - 9.1. Bootstrapping the Kubernetes Worker Nodes"
excerpt: "CNI의 동작 원리와 Worker Node 설정 파일들을 분석해 보자."
categories:
  - Kubernetes
toc: true
header:
  teaser: /assets/images/blog-Dev.jpg
tags:
  - Kubernetes
  - On-Premise-K8s-Hands-On-Study
  - On-Premise-K8s-Hands-On-Study-Week-1
hidden: true

---

*[서종호(가시다)](https://www.linkedin.com/in/gasida99/)님의 On-Premise K8s Hands-on Study 1주차 학습 내용을 기반으로 합니다.*

<br>

# TL;DR

이번 글의 목표는 **CNI의 동작 원리 이해와 Worker Node 설정 파일 분석**이다. [Kubernetes the Hard Way 튜토리얼의 Bootstrapping the Kubernetes Worker Nodes 단계](https://github.com/kelseyhightower/kubernetes-the-hard-way/blob/master/docs/09-bootstrapping-kubernetes-workers.md)를 수행한다.


Worker Node는 실제로 Pod를 실행하는 노드다. containerd(컨테이너 런타임), kubelet(노드 에이전트), kube-proxy(네트워크 프록시), CNI 플러그인(Pod 네트워크)이 필요하다. 이번 글에서는 각 컴포넌트의 설정 파일을 분석한다.

- CNI 개념: Container Network Interface의 역할과 동작 방식
- 설정 파일 분석: CNI, kubelet, containerd, kube-proxy 설정
- 파일 배포: jumpbox에서 Worker Node로 바이너리, 설정 파일 전송


<br>

# CNI (Container Network Interface)

CNI는 컨테이너에 네트워크 설정을 자동화하기 위한 표준 인터페이스다. Kubernetes에서 Pod가 생성될 때 자동으로 네트워크 인터페이스를 구성하고 IP를 할당하는 역할을 한다.

## 용어 정의

정확한 용어 구분이 중요하다.

- **CNI (Container Network Interface)**: 사양/표준/인터페이스 (문서)
  - 표준 인터페이스: stdin으로 JSON을 받고, stdout으로 JSON을 반환하는 단순한 규약
- **CNI 플러그인**: 그 사양을 구현한 바이너리 실행 파일
  - containerd가 필요할 때마다 fork/exec으로 실행
  - 구현체 예시: Calico, Flannel, Weave Net, Cilium
    

> 실무에서는 "CNI 설치했어?", "어떤 CNI 써?"처럼 혼용되기도 한다. 마치 USB는 표준 규격이지만 일상에서 "USB 샀어"라고 말하는 것과 같다. 하지만 정확히 뭘 말하는지 구분할 수 있어야 한다.

<br>

## 동작 방식

[이전에 Container Runtime에 대해 간략히 알아 본 글](https://sirzzang.github.io/dev/Dev-Nvidia-Container-Runtime/#container-runtime)에서 설명했듯, 컨테이너 런타임에는 고수준(containerd, CRI-O)과 저수준(runc)이 있다. 고수준 컨테이너 런타임이 담당하는 역할에 네트워크 설정도 있는데, 정확히는 다음과 같다:

- 고수준 컨테이너 런타임이 
- CNI 플러그인을 호출하여
- 네트워크 설정을 위임한다

<br>

컨테이너 생성 시 동작 원리는 다음과 같다:

1. [고수준 컨테이너 런타임] **네트워크 네임스페이스 생성**: 컨테이너의 격리된 네트워크 환경을 위한 network namespace 생성
2. [고수준 컨테이너 런타임] **CNI 설정 파일 읽기**: `/etc/cni/net.d/`에서 네트워크 구성 정보 로드
3. [고수준 컨테이너 런타임] **CNI 플러그인 실행**: `/opt/cni/bin/` 아래의 플러그인 바이너리를 fork/exec로 실행
4. [CNI 플러그인] **네트워크 설정 적용**: CNI 플러그인이 veth pair 생성, IP 할당, 라우팅 테이블 구성, iptables 규칙 추가
5. [CNI 플러그인] **결과 반환**: 할당된 IP 정보를 stdout으로 JSON 형식으로 반환
6. [고수준 컨테이너 런타임] **컨테이너 실행 시작**: containerd가 IP 정보를 저장하고, runc(저수준 런타임)를 호출하여 실제 컨테이너 프로세스 시작

편의상, 이하 고수준 컨테이너 런타임은 containerd에 빗대어 설명한다.

<br>

### 1-3단계: containerd (고수준 런타임)

containerd가 CNI 플러그인 실행을 위해 CNI 플러그인 설정 파일을 읽는다. `/etc/cni/net.d/` 하위에 CNI 플러그인 별 설정이 저장된다.

```bash
/etc/cni/net.d/
├── 10-bridge.conf          # bridge 플러그인 설정
├── 10-calico.conflist      # Calico 설정
├── 10-flannel.conflist     # Flannel 설정
└── 99-loopback.conf        # loopback 설정
```

- 숫자 prefix (10-, 20-, 99-): 실행 순서 (낮은 번호가 먼저)
- containerd는 사전순으로 첫 번째 설정 파일을 사용

<br>

CNI 실행 파일은 `/opt/cni/bin` 하위에 위치한다. containerd가 CNI 플러그인을 실행할 때는 환경 변수와 stdin을 통해 정보를 전달한다. 

```bash
# containerd가 내부적으로 실행하는 명령
CNI_COMMAND=ADD \
CNI_CONTAINERID=abc123 \
CNI_NETNS=/var/run/netns/abc123 \
CNI_IFNAME=eth0 \
CNI_PATH=/opt/cni/bin \
/opt/cni/bin/bridge < /etc/cni/net.d/10-bridge.conf
```

주요 환경 변수는 다음과 같다.

- `CNI_COMMAND`: 수행할 작업 (ADD: 네트워크 연결, DEL: 네트워크 해제)
- `CNI_CONTAINERID`: 컨테이너의 고유 식별자
- `CNI_NETNS`: 컨테이너의 network namespace 경로
- `CNI_IFNAME`: 컨테이너 내부에 생성할 네트워크 인터페이스 이름
- `CNI_PATH`: CNI 플러그인 바이너리 검색 경로

<br>

### 4-5단계: CNI 플러그인 (독립 바이너리)

바이너리에 stdin으로 설정이 전달되고, 바이너리가 네트워크 설정을 수행한 후 stdout으로 결과를 반환한다.

네트워크 설정 과정에서 하는 일은 여러 가지가 있지만, 핵심은 veth pair 생성, IP 주소 할당, 네트워크 인터페이스 활성화, 라우팅 테이블 구성 등이다. 예를 들어 다음과 같은 작업들을 수행한다:

```bash
# 컨테이너 network namespace 내에서 IP 할당
ip netns exec cni-abc123 ip addr add 10.244.1.5/24 dev eth0
# 네트워크 인터페이스 활성화
ip netns exec cni-abc123 ip link set eth0 up
# 기본 라우팅 설정
ip netns exec cni-abc123 ip route add default via 10.244.1.1
```

<br>

## Kubernetes에서의 CNI

앞서 설명한 containerd와 CNI 플러그인의 관계를 Kubernetes 환경에서 다시 정리하면 다음과 같다:

```
[kube-apiserver] 
    ↓ Pod 생성 요청
[kubelet] 
    ↓ CRI(Container Runtime Interface) 호출
[containerd] 
    ↓ CNI 플러그인 실행
[CNI 플러그인] 네트워크 설정 수행
```

<br>

### Pod 생성 플로우에서의 CNI

kubelet이 직접 CNI를 호출하는 것이 아니다. kubelet이 Pod 생성 요청을 받고 containerd에게 컨테이너 생성을 요청하면, containerd가 CNI를 호출한다는 점이 중요하다.

1. **kube-apiserver**: scheduler가 Pod를 특정 worker node에 할당
2. **kubelet**: 해당 노드의 kubelet이 Pod 생성 요청을 받음
3. **kubelet -> containerd**: CRI를 통해 컨테이너 생성 요청
4. **containerd -> CNI 플러그인**: `/etc/cni/net.d/` 설정을 읽고 `/opt/cni/bin/` 바이너리 실행
5. **CNI 플러그인**: Pod에 IP 할당, veth pair 생성, 라우팅 설정
6. **containerd -> runc**: 네트워크가 구성된 상태에서 실제 컨테이너 프로세스 시작

<br>

## 이번 실습에서의 CNI

Kubernetes the Hard Way 튜토리얼에서는 CNI 플러그인 중 가장 기본적인 **bridge 플러그인**을 사용한다:

1. **CNI 플러그인 바이너리 설치**: `/opt/cni/bin/`에 bridge, loopback 등 기본 플러그인 설치
2. **CNI 설정 파일 배치**: `/etc/cni/net.d/`에 Pod 네트워크 대역(10.200.x.0/24) 설정
3. **kubelet 설정**: kubelet이 containerd를 통해 CNI를 사용하도록 구성
4. **테스트**: Pod 생성 후 IP 할당 및 네트워크 연결 확인

> 실무에서는 Calico, Flannel, Cilium 등 더 강력한 CNI 플러그인을 사용하지만, 학습 목적으로는 가장 단순한 bridge 플러그인으로 CNI의 동작 원리를 이해하는 것이 좋다.

CNI 플러그인 바이너리는 [2. Setup the Jumpbox]({% post_url 2026-01-05-Kubernetes-Cluster-The-Hard-Way-02 %}) 단계에서 이미 다운로드해 두었다.

<br>

# CNI 설정 파일

## 10-bridge.conf

[Kubernetes the Hard Way에서 제공하는 bridge 플러그인 설정 파일](https://github.com/kelseyhightower/kubernetes-the-hard-way/blob/master/configs/10-bridge.conf)이다.

```json
{
  "cniVersion": "1.0.0",
  "name": "bridge",
  "type": "bridge",
  "bridge": "cni0",
  "isGateway": true,
  "ipMasq": true,
  "ipam": {
    "type": "host-local",
    "ranges": [
      [{"subnet": "SUBNET"}]
    ],
    "routes": [{"dst": "0.0.0.0/0"}]
  }
}
```

`SUBNET`은 각 노드별로 다른 값으로 치환된다. node-0은 `10.200.0.0/24`, node-1은 `10.200.1.0/24`를 사용한다.

<br>

### 주요 옵션 분석

- `cniVersion`: 사용하는 CNI 스펙 버전
- `name`: 네트워크 이름 (로깅, 디버깅용)
- `type`: 사용할 CNI 플러그인 바이너리 이름. `/opt/cni/bin/bridge` 실행
- `bridge`: 호스트에 생성할 Linux bridge 이름
- `isGateway`: bridge 인터페이스에 IP 할당 여부. `true`면 subnet의 첫 번째 IP(예: 10.200.0.1)가 gateway로 할당됨
- `ipMasq`: IP 마스커레이딩(SNAT) 활성화. Pod가 외부 통신 시 노드 IP로 변환

<br>

### IPAM 옵션 분석

IPAM(IP Address Management)은 컨테이너에 IP 주소를 할당하는 방식을 정의한다.

- `type: host-local`: 각 노드가 로컬에서 IP 관리. 별도 IPAM 서버 없이 노드별로 독립적으로 IP 할당
- `ranges`: IP 할당 범위. 2차원 배열로 여러 대역 지정 가능
- `subnet`: Pod에 할당할 IP 대역
- `routes`: 컨테이너에 추가할 라우팅 규칙. `0.0.0.0/0`은 모든 트래픽을 gateway로 전달

<br>

## 99-loopback.conf

[loopback 설정 파일](https://github.com/kelseyhightower/kubernetes-the-hard-way/blob/master/configs/99-loopback.conf)이다.

```json
{
  "cniVersion": "1.1.0",
  "name": "lo",
  "type": "loopback"
}
```

컨테이너 내부의 loopback 인터페이스(`lo`)를 활성화한다. 모든 컨테이너는 `127.0.0.1`로 자기 자신과 통신할 수 있어야 하므로 필수 설정이다.

파일명의 `99-` prefix로 인해 bridge 설정(10-) 이후에 적용된다.

<br>

# containerd 설정 파일

containerd의 설정 파일 `containerd-config.toml`을 분석한다.

```bash
version = 2

[plugins."io.containerd.grpc.v1.cri"]
  [plugins."io.containerd.grpc.v1.cri".containerd]
    snapshotter = "overlayfs"
    default_runtime_name = "runc"
  [plugins."io.containerd.grpc.v1.cri".containerd.runtimes.runc]
    runtime_type = "io.containerd.runc.v2"
  [plugins."io.containerd.grpc.v1.cri".containerd.runtimes.runc.options]
    SystemdCgroup = true
[plugins."io.containerd.grpc.v1.cri".cni]
  bin_dir = "/opt/cni/bin"
  conf_dir = "/etc/cni/net.d"
```

<br>

## 주요 옵션 분석

### CRI 플러그인 설정

containerd는 플러그인 아키텍처로 동작한다. `io.containerd.grpc.v1.cri`는 Kubernetes의 CRI(Container Runtime Interface)를 구현하는 플러그인이다. kubelet은 이 플러그인을 통해 containerd와 통신한다.

- `snapshotter = "overlayfs"`: 컨테이너 이미지 레이어를 관리하는 방식. overlayfs는 Linux의 copy-on-write 파일시스템으로 효율적인 레이어 관리 제공
- `default_runtime_name = "runc"`: 기본으로 사용할 저수준 런타임
- `runtime_type = "io.containerd.runc.v2"`: runc v2 shim 사용. containerd와 runc 사이의 인터페이스

<br>

### Cgroup 설정

cgroup(control group)은 Linux 커널의 리소스 관리 기능으로, 프로세스 그룹의 CPU, 메모리, I/O 등을 제한하고 격리한다. containerd는 컨테이너별로 cgroup을 생성하여 리소스를 관리하는데, 이 때 cgroup을 어떤 방식으로 관리할지 결정하는 것이 cgroup 드라이버다.

- `SystemdCgroup = true`: systemd를 cgroup 드라이버로 사용. kubelet의 `cgroupDriver: systemd` 설정과 일치해야 함

> **중요**: containerd와 kubelet의 cgroup 드라이버가 일치하지 않으면 Pod가 정상적으로 생성되지 않는다. 둘 다 `systemd` 또는 둘 다 `cgroupfs`를 사용해야 한다.

<br>

### CNI 경로 설정

containerd가 컨테이너의 네트워크를 설정할 때 아래 경로들을 참조한다.

- `bin_dir = "/opt/cni/bin"`: CNI 플러그인 바이너리 경로
- `conf_dir = "/etc/cni/net.d"`: CNI 설정 파일 경로

<br>

# kubelet 설정 파일

kubelet의 설정 파일 `kubelet-config.yaml`을 분석한다.

```yaml
kind: KubeletConfiguration 
apiVersion: kubelet.config.k8s.io/v1beta1
address: "0.0.0.0"
authentication:
  anonymous:
    enabled: false
  webhook:
    enabled: true
  x509:
    clientCAFile: "/var/lib/kubelet/ca.crt"
authorization:
  mode: Webhook
cgroupDriver: systemd
containerRuntimeEndpoint: "unix:///var/run/containerd/containerd.sock"
enableServer: true
failSwapOn: false
maxPods: 16
memorySwap:
  swapBehavior: NoSwap
port: 10250
resolvConf: "/etc/resolv.conf"
registerNode: true
runtimeRequestTimeout: "15m"
tlsCertFile: "/var/lib/kubelet/kubelet.crt"
tlsPrivateKeyFile: "/var/lib/kubelet/kubelet.key"
```

<br>

## 주요 옵션 분석

### 네트워크 바인딩

kubelet의 네트워크 바인딩 설정이다.

- `address: "0.0.0.0"`: kubelet HTTPS 서버 바인딩 주소. 모든 인터페이스에서 수신
- `port: 10250`: kubelet API 포트. 로그, exec, stats, metrics 접근에 사용
- `enableServer: true`: kubelet API 서버 활성화. `false`면 kube-apiserver가 kubelet에 접근 불가

<br>

### 인증 설정

kubelet에 접근하는 요청의 인증 방식을 설정한다.

- `anonymous.enabled: false`: 익명 인증 비활성화. 모든 요청에 인증 필요
- `webhook.enabled: true`: 인증 요청을 kube-apiserver에 위임. ServiceAccount 토큰, bootstrap 토큰 처리 가능
- `x509.clientCAFile`: kubelet에 접근하는 클라이언트 인증서 검증용 CA. kube-apiserver, metrics-server 등이 kubelet에 연결할 때 사용

<br>

### 인가 설정

인증된 요청의 권한을 검증하는 방식을 설정한다.

- `authorization.mode: Webhook`: 인가 요청을 kube-apiserver에 위임

`Webhook` 모드에서 kubelet은 요청자의 권한을 kube-apiserver에 질의한다. kube-apiserver는 자신의 인가 모드(Node, RBAC)를 적용하여 결정을 내린다.

**동작 순서:**

1. kube-apiserver가 kubelet에 요청 (예: `kubectl logs`)
2. kubelet이 kube-apiserver에 SubjectAccessReview 요청
3. kube-apiserver가 Node Authorizer 평가 -> 해당 없으면 RBAC 평가
4. kubelet이 결과에 따라 요청 처리/거부

[이전 글의 RBAC 설정]({% post_url 2026-01-05-Kubernetes-Cluster-The-Hard-Way-08-2 %}#rbac-설정)에서 `system:kube-apiserver-to-kubelet` ClusterRole을 생성한 이유가 바로 이것이다. kubelet의 Webhook 인가 모드에서 kube-apiserver의 요청이 허용되려면 해당 RBAC 권한이 필요하다.

<br>

### TLS 설정

kubelet HTTPS 서버의 인증서 설정이다.

- `tlsCertFile`: kubelet HTTPS 서버의 서버 인증서
- `tlsPrivateKeyFile`: 서버 인증서의 개인키

kubelet은 자체 HTTPS 서버를 운영한다. kube-apiserver가 kubelet에 연결할 때 이 인증서로 kubelet의 신원을 확인한다.

<br>

### 컨테이너 런타임 설정

kubelet과 containerd 간의 통신 설정이다.

- `containerRuntimeEndpoint`: containerd의 Unix 소켓 경로. CRI를 통해 통신
- `cgroupDriver: systemd`: cgroup 드라이버. containerd 설정과 일치해야 함
- `runtimeRequestTimeout: "15m"`: CRI 요청 최대 대기 시간. 이미지 pull, container start 등에 적용

<br>

### 노드 등록 및 리소스

노드 등록과 리소스 제한 관련 설정이다.

- `registerNode: true`: kubelet이 API Server에 Node 객체 자동 등록
- `maxPods: 16`: 노드당 최대 Pod 수
- `resolvConf`: Pod에 전달할 DNS 설정 파일 경로

<br>

### Swap 설정

kubelet의 swap 관련 설정이다.

| 설정 | 값 | 설명 |
|-----|---|------|
| `failSwapOn` | `false` | swap이 활성화된 호스트에서도 kubelet 시작 허용 |
| `memorySwap.swapBehavior` | `NoSwap` | 컨테이너가 swap을 사용하지 않도록 설정 |

`swapBehavior` 옵션으로 설정할 수 있는 값은 아래와 같다.
- **`NoSwap`** (기본값): 컨테이너가 swap 사용 불가. cgroup에서 `memory.swap.max=0` 설정
- **`LimitedSwap`**: 컨테이너가 제한된 swap 사용 가능. cgroup v2 필요

이 조합은 "호스트에 swap이 있어도 kubelet은 시작하되, 컨테이너는 swap을 쓰지 않는다"는 의미다. Kubernetes가 swap을 권장하지 않는 이유와 swap의 동작 원리는 [메모리, 페이지, 스왑]({% post_url 2026-01-23-CS-Memory-Page-Swap %}) 글을 참고한다.

<br>

# kube-proxy 설정 파일

kube-proxy의 설정 파일 `kube-proxy-config.yaml`을 분석한다.

```yaml
kind: KubeProxyConfiguration
apiVersion: kubeproxy.config.k8s.io/v1alpha1
clientConnection:
  kubeconfig: "/var/lib/kube-proxy/kubeconfig"
mode: "iptables"
clusterCIDR: "10.200.0.0/16"
```

<br>

## 주요 옵션 분석

kube-proxy의 주요 설정 항목이다.

- `clientConnection.kubeconfig`: API Server 연결을 위한 kubeconfig 경로
- `mode: "iptables"`: 프록시 모드. Service로의 트래픽을 Pod로 전달하는 방식
- `clusterCIDR: "10.200.0.0/16"`: Pod 네트워크 대역. kube-proxy가 이 대역의 트래픽을 처리

<br>

### 프록시 모드

kube-proxy는 여러 모드를 지원한다.

- `iptables`: Linux iptables를 사용한 패킷 포워딩. 가장 일반적으로 사용
- `ipvs`: Linux IPVS를 사용. 대규모 클러스터에서 더 나은 성능
- `kernelspace`: Windows 환경용

이번 실습에서는 `iptables` 모드를 사용한다.

<br>

### clusterCIDR 설정

`clusterCIDR`은 kube-controller-manager의 `--cluster-cidr` 옵션과 동일한 값(`10.200.0.0/16`)이어야 한다. kube-proxy는 이 대역의 트래픽이 Pod 간 통신임을 인식하고 적절히 라우팅한다.

<br>

# systemd unit 파일

각 컴포넌트를 systemd 서비스로 관리하기 위한 unit 파일들을 분석한다.

## containerd.service

```ini
[Unit]
Description=containerd container runtime
Documentation=https://containerd.io
After=network.target

[Service]
ExecStartPre=/sbin/modprobe overlay
ExecStart=/bin/containerd
Restart=always
RestartSec=5
Delegate=yes
KillMode=process
OOMScoreAdjust=-999
LimitNOFILE=1048576
LimitNPROC=infinity
LimitCORE=infinity

[Install]
WantedBy=multi-user.target
```

<br>

### 주요 옵션 분석

containerd 서비스의 주요 설정 항목이다.

- `After=network.target`: 네트워크 서비스 시작 후 실행
- `ExecStartPre=/sbin/modprobe overlay`: 시작 전 overlay 커널 모듈 로드. overlayfs 사용을 위해 필요
- `Delegate=yes`: cgroup 제어 위임. containerd가 하위 cgroup을 자유롭게 관리 가능
- `KillMode=process`: 메인 프로세스만 종료. 컨테이너들은 유지
- `OOMScoreAdjust=-999`: OOM Killer 우선순위 최하위. 메모리 부족 시 containerd가 종료되지 않도록 보호
- `LimitNOFILE`: 최대 오픈 파일 수. 많은 컨테이너 실행 시 필요

<br>

## kubelet.service

```ini
[Unit]
Description=Kubernetes Kubelet
Documentation=https://github.com/kubernetes/kubernetes
After=containerd.service
Requires=containerd.service

[Service]
ExecStart=/usr/local/bin/kubelet \
  --config=/var/lib/kubelet/kubelet-config.yaml \
  --kubeconfig=/var/lib/kubelet/kubeconfig \
  --v=2
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
```

<br>

### 주요 옵션 분석

kubelet 서비스의 주요 설정 항목이다.

- `After=containerd.service`: containerd 시작 후 실행
- `Requires=containerd.service`: containerd가 실행 중이어야 함. containerd 종료 시 kubelet도 종료
- `--config`: kubelet 설정 파일 경로
- `--kubeconfig`: API Server 연결을 위한 kubeconfig 경로
- `--v=2`: 로그 상세 수준

<br>

## kube-proxy.service

```ini
[Unit]
Description=Kubernetes Kube Proxy
Documentation=https://github.com/kubernetes/kubernetes

[Service]
ExecStart=/usr/local/bin/kube-proxy \
  --config=/var/lib/kube-proxy/kube-proxy-config.yaml
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
```

kube-proxy는 containerd에 의존하지 않는다. API Server에서 Service 정보를 가져와 iptables 규칙을 관리하는 독립적인 컴포넌트다.

<br>

# 파일 배포

jumpbox에서 Worker Node로 설정 파일과 바이너리를 전송한다.

## CNI, kubelet 설정 파일 배포

CNI 설정의 `SUBNET` 값을 각 노드에 맞게 치환하여 배포한다.

```bash
for HOST in node-0 node-1; do
  SUBNET=$(grep ${HOST} machines.txt | cut -d " " -f 4)
  sed "s|SUBNET|$SUBNET|g" \
    configs/10-bridge.conf > 10-bridge.conf

  sed "s|SUBNET|$SUBNET|g" \
    configs/kubelet-config.yaml > kubelet-config.yaml

  scp 10-bridge.conf kubelet-config.yaml \
  root@${HOST}:~/
done
```

`machines.txt` 파일에서 각 노드의 Pod CIDR을 읽어와 `SUBNET`을 치환한다:
- node-0: `10.200.0.0/24`
- node-1: `10.200.1.0/24`

<br>

## 기타 설정 파일 및 바이너리 배포

containerd, kube-proxy 설정과 바이너리를 배포한다.

```bash
for HOST in node-0 node-1; do
  scp \
    downloads/worker/* \
    downloads/client/kubectl \
    configs/99-loopback.conf \
    configs/containerd-config.toml \
    configs/kube-proxy-config.yaml \
    units/containerd.service \
    units/kubelet.service \
    units/kube-proxy.service \
    root@${HOST}:~/
done
```

```
# 출력 (축약)
containerd                100%   54MB  69.4MB/s   00:00    
crictl                    100%   38MB  97.8MB/s   00:00    
kubelet                   100%   75MB  99.8MB/s   00:00    
kube-proxy                100%   65MB  63.8MB/s   00:00    
runc                      100%   11MB  99.8MB/s   00:00    
...
```

<br>

## CNI 플러그인 배포

CNI 플러그인 바이너리를 배포한다.

```bash
for HOST in node-0 node-1; do
  scp \
    downloads/cni-plugins/* \
    root@${HOST}:~/cni-plugins/
done

# 출력 (축약)
bandwidth     100% 4492KB  61.1MB/s   00:00    
bridge        100% 5065KB  63.8MB/s   00:00    
host-local    100% 3886KB  86.2MB/s   00:00    
loopback      100% 4030KB 101.7MB/s   00:00    
...
```

<br>

## 배포 확인

node-0에 배포된 파일을 확인한다.

```bash
ssh node-0 ls -l /root

# 출력 
-rw-r--r-- 1 root root      280 Jan  9 23:46 10-bridge.conf
-rw-r--r-- 1 root root       65 Jan  9 23:50 99-loopback.conf
drwxr-xr-x 2 root root     4096 Jan  9 23:51 cni-plugins
-rwxr-xr-x 1 root root 56836190 Jan  9 23:50 containerd
-rw-r--r-- 1 root root      470 Jan  9 23:50 containerd-config.toml
-rw-r--r-- 1 root root      352 Jan  9 23:50 containerd.service
-rwxr-xr-x 1 root root 75235588 Jan  9 23:50 kubelet
-rw-r--r-- 1 root root      580 Jan  9 23:46 kubelet-config.yaml
-rw-r--r-- 1 root root      365 Jan  9 23:50 kubelet.service
-rwxr-xr-x 1 root root 65274008 Jan  9 23:50 kube-proxy
-rw-r--r-- 1 root root      184 Jan  9 23:50 kube-proxy-config.yaml
-rw-r--r-- 1 root root      268 Jan  9 23:50 kube-proxy.service
-rwxr-xr-x 1 root root 11305168 Jan  9 23:50 runc
```

CNI 플러그인 디렉토리도 확인한다.

```bash
ssh node-0 ls /root/cni-plugins
bandwidth  bridge  dhcp  dummy  firewall  host-device  host-local  ipvlan  loopback  macvlan  portmap  ptp  sbr  static  tap  tuning  vlan  vrf
```

bridge, host-local, loopback 등 이번 실습에서 사용할 플러그인이 포함되어 있다.

<br>

# 설정 파일 경로 정리

Worker Node 컴포넌트들이 참조하는 파일 경로를 정리한다.

## /etc/cni/net.d

CNI 설정 파일이 저장되는 경로다. containerd가 컨테이너 네트워크를 구성할 때 이 디렉토리에서 설정 파일을 읽는다.

- `10-bridge.conf`: bridge 플러그인 설정 (Pod 네트워크)
- `99-loopback.conf`: loopback 플러그인 설정

<br>

## /opt/cni/bin

CNI 플러그인 바이너리가 저장되는 경로다. containerd가 네트워크 설정 시 이 디렉토리의 바이너리를 실행한다.

- `bridge`: Linux bridge 기반 네트워크
- `host-local`: 로컬 IP 주소 관리
- `loopback`: loopback 인터페이스
- 기타: bandwidth, portmap 등 추가 기능

<br>

## /etc/containerd

containerd 설정 파일이 저장되는 경로다. containerd 데몬이 시작할 때 이 디렉토리의 설정을 로드한다.

- `config.toml`: containerd 메인 설정

<br>

## /var/lib/kubelet

kubelet 관련 파일이 저장되는 경로다. kubelet의 설정, 인증서, kubeconfig 등 런타임에 필요한 파일들이 위치한다.

- `kubelet-config.yaml`: kubelet 설정
- `kubeconfig`: API Server 연결 정보
- `ca.crt`: 클라이언트 인증서 검증용 CA
- `kubelet.crt`, `kubelet.key`: kubelet 서버 인증서

<br>

## /var/lib/kube-proxy

kube-proxy 관련 파일이 저장되는 경로다. Service 트래픽 라우팅을 위한 설정과 API Server 연결 정보가 위치한다.

- `kube-proxy-config.yaml`: kube-proxy 설정
- `kubeconfig`: API Server 연결 정보

<br>

# 결과

이 단계를 완료하면 다음과 같은 설정 파일들이 준비된다:

1. **CNI 설정**: bridge, loopback 플러그인 설정
2. **containerd 설정**: CRI 플러그인, cgroup, CNI 경로 설정
3. **kubelet 설정**: 인증/인가, TLS, 컨테이너 런타임 연결 설정
4. **kube-proxy 설정**: iptables 모드, Pod CIDR 설정
5. **systemd unit 파일**: 각 컴포넌트의 서비스 정의

<br>

각 설정 옵션들이 서로 연관되어 있음을 확인했다:
- containerd의 `SystemdCgroup`과 kubelet의 `cgroupDriver`가 일치해야 함
- containerd의 CNI 경로와 실제 CNI 설정/바이너리 위치가 일치해야 함
- kubelet의 `authorization.mode: Webhook`과 [이전 글에서 설정한 RBAC]({% post_url 2026-01-05-Kubernetes-Cluster-The-Hard-Way-08-2 %}#rbac-설정)이 연계됨

<br> 

다음 단계에서는 이 파일들을 Worker Node에 설치하고 서비스를 시작하여 클러스터에 노드를 등록한다.
