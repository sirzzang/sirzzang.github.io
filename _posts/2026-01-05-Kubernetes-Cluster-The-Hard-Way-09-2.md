---
title:  "[Kubernetes] Cluster: 내 손으로 클러스터 구성하기 - 9.2. Bootstrapping the Kubernetes Worker Nodes"
excerpt: "Worker Node에 containerd, kubelet, kube-proxy를 설치하고 클러스터에 등록해 보자."
categories:
  - Kubernetes
toc: true
header:
  teaser: /assets/images/blog-Dev.jpg
tags:
  - Kubernetes
  - On-Premise-K8s-Hands-On-Study
  - On-Premise-K8s-Hands-On-Study-Week-1

---

*[서종호(가시다)](https://www.linkedin.com/in/gasida99/)님의 On-Premise K8s Hands-on Study 1주차 학습 내용을 기반으로 합니다.*

<br>

# TL;DR

이번 글의 목표는 **Worker Node 프로비저닝 및 클러스터 등록 검증**이다. [Kubernetes the Hard Way 튜토리얼의 Bootstrapping the Kubernetes Worker Nodes 단계](https://github.com/kelseyhightower/kubernetes-the-hard-way/blob/master/docs/09-bootstrapping-kubernetes-workers.md)를 수행한다.

이전 글에서 분석한 설정 파일들을 실제로 배치하고, Worker Node가 클러스터에 정상 등록되는지 확인한다.

- 바이너리 설치: containerd, kubelet, kube-proxy, CNI 플러그인 설치
- 커널 모듈 설정: br_netfilter 모듈 로드 및 sysctl 설정
- 서비스 시작: systemd로 containerd, kubelet, kube-proxy 시작
- 검증: 노드 등록 확인, 상태 점검



![kubernetes-the-hard-way-cluster-structure-9]({{site.url}}/assets/images/kubernetes-the-hard-way-cluster-structure-9.png)

<br>

# 사전 준비

Worker Node 프로비저닝 전에 필요한 준비 작업을 수행한다.

## OS 의존성 설치

각 Worker Node에 필요한 패키지를 설치한다.

```bash
apt-get -y install socat conntrack ipset kmod psmisc bridge-utils
```

- `socat`: `kubectl port-forward` 명령 지원
- `conntrack`: 연결 추적. kube-proxy가 iptables 규칙 관리에 사용
- `ipset`: IP 집합 관리. kube-proxy IPVS 모드에서 사용
- `kmod`: 커널 모듈 관리
- `psmisc`: 프로세스 관리 도구 (fuser, killall 등)
- `bridge-utils`: Linux bridge 관리 도구

<br>

## Swap 비활성화 확인

[1. Prerequisites]({% post_url 2026-01-05-Kubernetes-Cluster-The-Hard-Way-01 %}) 단계에서 swap을 비활성화했다. 다시 확인한다.

```bash
swapon --show
```

출력이 없으면 swap이 비활성화된 상태다. Kubernetes는 메모리 사용량을 정확히 모니터링해야 하는데, swap이 활성화되어 있으면 메모리 부족 상황을 제대로 감지하지 못할 수 있다.

<br>

## 디렉토리 생성

설정 파일과 바이너리를 저장할 디렉토리를 생성한다.

```bash
mkdir -p \
  /etc/cni/net.d \
  /opt/cni/bin \
  /var/lib/kubelet \
  /var/lib/kube-proxy \
  /var/lib/kubernetes \
  /var/run/kubernetes
```

- `/etc/cni/net.d`: CNI 설정 파일
- `/opt/cni/bin`: CNI 플러그인 바이너리
- `/var/lib/kubelet`: kubelet 설정 및 인증서
- `/var/lib/kube-proxy`: kube-proxy 설정
- `/var/lib/kubernetes`: 공통 인증서 (CA 등)
- `/var/run/kubernetes`: 런타임 데이터

<br>

# node-0 프로비저닝

node-0에 SSH 접속하여 작업을 진행한다.

```bash
ssh root@node-0
```

## 바이너리 설치

Worker Node 바이너리를 적절한 위치에 설치한다.

```bash
# 런타임 및 Kubernetes 바이너리
mv crictl kube-proxy kubelet runc /usr/local/bin/
mv containerd containerd-shim-runc-v2 containerd-stress /bin/

# CNI 플러그인
mv cni-plugins/* /opt/cni/bin/
```

| 바이너리 | 경로 | 용도 |
| --- | --- | --- |
| `containerd`, `containerd-shim-runc-v2` | `/bin/` | 컨테이너 런타임 |
| `runc` | `/usr/local/bin/` | 저수준 컨테이너 런타임 |
| `kubelet`, `kube-proxy` | `/usr/local/bin/` | Kubernetes 컴포넌트 |
| `crictl` | `/usr/local/bin/` | 컨테이너 런타임 디버깅 도구 |
| CNI 플러그인 | `/opt/cni/bin/` | 네트워크 설정 |

<br>

## CNI 네트워킹 설정

### 설정 파일 배치

CNI 설정 파일을 `/etc/cni/net.d/`에 배치한다.

```bash
mv 10-bridge.conf 99-loopback.conf /etc/cni/net.d/
```

배치된 설정을 확인한다.

```bash
cat /etc/cni/net.d/10-bridge.conf
```
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
      [{"subnet": "10.200.0.0/24"}]
    ],
    "routes": [{"dst": "0.0.0.0/0"}]
  }
}
```

node-0의 Pod CIDR이 `10.200.0.0/24`로 설정되어 있다.

<br>

### br_netfilter 커널 모듈 로드

Linux bridge를 통과하는 패킷이 iptables 규칙을 거치도록 `br_netfilter` 커널 모듈을 로드한다.

```bash
# 현재 상태 확인 (출력 없음 = 미로드)
lsmod | grep netfilter

# 모듈 로드
modprobe br-netfilter

# 부팅 시 자동 로드 설정
echo "br-netfilter" >> /etc/modules-load.d/modules.conf

# 로드 확인
lsmod | grep netfilter
br_netfilter           32768  0
bridge                262144  1 br_netfilter
```

<br>

### br_netfilter 모듈의 역할

`br_netfilter` 모듈은 Linux bridge를 통과하는 패킷이 iptables 규칙을 거치도록 한다.

기본적으로 Linux bridge는 Layer 2(데이터 링크 계층)에서 동작한다. bridge를 통과하는 패킷은 MAC 주소 기반으로 전달되며, Layer 3(네트워크 계층)의 iptables 규칙을 거치지 않는다.

하지만 Kubernetes의 kube-proxy는 iptables를 사용하여 Service 트래픽을 Pod로 전달한다. Pod 간 통신이 bridge를 통과할 때 iptables 규칙이 적용되지 않으면 Service 라우팅이 동작하지 않는다.

즉, `br_netfilter` 모듈이 로드되면, 아래와 같이 동작하는 것이다.
- bridge를 통과하는 IPv4/IPv6 패킷이 iptables/ip6tables 규칙을 거침
- kube-proxy의 Service 규칙이 Pod 간 통신에도 적용됨

<br>

### sysctl 설정

bridge 트래픽이 iptables를 거치도록 커널 파라미터를 설정한다.

```bash
echo "net.bridge.bridge-nf-call-iptables = 1"  >> /etc/sysctl.d/kubernetes.conf
echo "net.bridge.bridge-nf-call-ip6tables = 1" >> /etc/sysctl.d/kubernetes.conf
sysctl -p /etc/sysctl.d/kubernetes.conf
# 출력
net.bridge.bridge-nf-call-iptables = 1
net.bridge.bridge-nf-call-ip6tables = 1
```

- `bridge-nf-call-iptables`: bridge를 통과하는 IPv4 패킷에 iptables 적용
- `bridge-nf-call-ip6tables`: bridge를 통과하는 IPv6 패킷에 ip6tables 적용

이 설정이 없으면 Pod 간 통신 시 Service ClusterIP로의 접근이 실패할 수 있다.

<br>

## containerd 설정

containerd 설정 파일을 배치하고 서비스를 등록한다.

```bash
mkdir -p /etc/containerd/
mv containerd-config.toml /etc/containerd/config.toml
mv containerd.service /etc/systemd/system/
cat /etc/containerd/config.toml
# 출력
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

주요 설정 항목은 다음과 같다:

- `snapshotter = "overlayfs"`: 컨테이너 이미지 레이어 관리에 [overlayfs](https://sirzzang.github.io/dev/Dev-Container-Duplicate-Container-Images-2/#overlayfs) 사용
- `default_runtime_name = "runc"`: 기본 저수준 런타임으로 runc 사용
- `runtime_type = "io.containerd.runc.v2"`: runc v2 shim 사용
- `SystemdCgroup = true`: systemd를 cgroup 드라이버로 사용 (kubelet과 일치 필요)
- `bin_dir`, `conf_dir`: CNI 플러그인 바이너리와 설정 파일 경로

<br>

## kubelet 설정

kubelet 설정 파일과 서비스를 배치한다.

```bash
mv kubelet-config.yaml /var/lib/kubelet/
mv kubelet.service /etc/systemd/system/
```

<br>

## kube-proxy 설정

kube-proxy 설정 파일과 서비스를 배치한다.

```bash
mv kube-proxy-config.yaml /var/lib/kube-proxy/
mv kube-proxy.service /etc/systemd/system/
```

<br>

## 서비스 시작

systemd 설정을 리로드하고 서비스를 시작한다.

```bash
systemctl daemon-reload
systemctl enable containerd kubelet kube-proxy
systemctl start containerd kubelet kube-proxy
```

<br>

## 서비스 상태 확인

각 서비스가 정상 실행 중인지 확인한다.

```bash
systemctl status containerd --no-pager
```
● containerd.service - containerd container runtime
     Loaded: loaded (/etc/systemd/system/containerd.service; enabled)
     Active: active (running) since Sat 2026-01-10 00:30:17 KST
       Docs: https://containerd.io
    Process: 3432 ExecStartPre=/sbin/modprobe overlay (code=exited, status=0/SUCCESS)
   Main PID: 3440 (containerd)
      Tasks: 8 (limit: 2096)
     Memory: 20.0M
     CGroup: /system.slice/containerd.service
             └─3440 /bin/containerd
```

```bash
systemctl status kubelet --no-pager
● kubelet.service - Kubernetes Kubelet
     Loaded: loaded (/etc/systemd/system/kubelet.service; enabled)
     Active: active (running) since Sat 2026-01-10 00:30:17 KST
       Docs: https://github.com/kubernetes/kubernetes
   Main PID: 3441 (kubelet)
      Tasks: 10 (limit: 2096)
     Memory: 45.2M
     CGroup: /system.slice/kubelet.service
             └─3441 /usr/local/bin/kubelet --config=/var/lib/kubelet/kubelet-config.yaml ...
```

```bash
systemctl status kube-proxy --no-pager
● kube-proxy.service - Kubernetes Kube Proxy
     Loaded: loaded (/etc/systemd/system/kube-proxy.service; enabled)
     Active: active (running) since Sat 2026-01-10 00:30:17 KST
       Docs: https://github.com/kubernetes/kubernetes
   Main PID: 3433 (kube-proxy)
      Tasks: 5 (limit: 2096)
     Memory: 16.2M
     CGroup: /system.slice/kube-proxy.service
             └─3433 /usr/local/bin/kube-proxy --config=/var/lib/kube-proxy/kube-proxy-config.yaml
```

모든 서비스가 `active (running)` 상태면 정상이다.

<br>

# node-1 프로비저닝

node-1도 동일한 절차로 프로비저닝한다. 주요 명령만 나열한다.

```bash
# SSH 접속
ssh root@node-1

# OS 의존성 설치
apt-get -y install socat conntrack ipset kmod psmisc bridge-utils

# Swap 확인
swapon --show

# 디렉토리 생성
mkdir -p \
  /etc/cni/net.d \
  /opt/cni/bin \
  /var/lib/kubelet \
  /var/lib/kube-proxy \
  /var/lib/kubernetes \
  /var/run/kubernetes

# 바이너리 설치
mv crictl kube-proxy kubelet runc /usr/local/bin/
mv containerd containerd-shim-runc-v2 containerd-stress /bin/
mv cni-plugins/* /opt/cni/bin/

# CNI 설정
mv 10-bridge.conf 99-loopback.conf /etc/cni/net.d/

# br_netfilter 모듈 로드
modprobe br-netfilter
echo "br-netfilter" >> /etc/modules-load.d/modules.conf

# sysctl 설정
echo "net.bridge.bridge-nf-call-iptables = 1"  >> /etc/sysctl.d/kubernetes.conf
echo "net.bridge.bridge-nf-call-ip6tables = 1" >> /etc/sysctl.d/kubernetes.conf
sysctl -p /etc/sysctl.d/kubernetes.conf

# containerd 설정
mkdir -p /etc/containerd/
mv containerd-config.toml /etc/containerd/config.toml
mv containerd.service /etc/systemd/system/

# kubelet 설정
mv kubelet-config.yaml /var/lib/kubelet/
mv kubelet.service /etc/systemd/system/

# kube-proxy 설정
mv kube-proxy-config.yaml /var/lib/kube-proxy/
mv kube-proxy.service /etc/systemd/system/

# 서비스 시작
systemctl daemon-reload
systemctl enable containerd kubelet kube-proxy
systemctl start containerd kubelet kube-proxy
```

CNI 설정에서 node-1의 Pod CIDR은 `10.200.1.0/24`다.

```bash
cat /etc/cni/net.d/10-bridge.conf
```

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
      [{"subnet": "10.200.1.0/24"}]
    ],
    "routes": [{"dst": "0.0.0.0/0"}]
  }
}
```

서비스 상태를 확인한다.

```bash
systemctl status kubelet containerd kube-proxy --no-pager
```

```
● kubelet.service - Kubernetes Kubelet
     Loaded: loaded (/etc/systemd/system/kubelet.service; enabled)
     Active: active (running) since Sat 2026-01-10 00:33:24 KST
...
● containerd.service - containerd container runtime
     Loaded: loaded (/etc/systemd/system/containerd.service; enabled)
     Active: active (running) since Sat 2026-01-10 00:33:24 KST
...
● kube-proxy.service - Kubernetes Kube Proxy
     Loaded: loaded (/etc/systemd/system/kube-proxy.service; enabled)
     Active: active (running) since Sat 2026-01-10 00:33:24 KST
...
```

<br>

# 클러스터 등록 확인

Worker Node 프로비저닝이 완료되면 kubelet이 API Server에 자신을 등록한다. jumpbox에서 server에 접속하여 노드 등록 상태를 확인한다.

## 노드 목록 확인

```bash
ssh server "kubectl get nodes -owide --kubeconfig admin.kubeconfig"
```

```
NAME     STATUS   ROLES    AGE     VERSION   INTERNAL-IP      EXTERNAL-IP   OS-IMAGE                         KERNEL-VERSION   CONTAINER-RUNTIME
node-0   Ready    <none>   7m11s   v1.32.3   192.168.10.101   <none>        Debian GNU/Linux 12 (bookworm)   6.1.0-40-arm64   containerd://2.1.0-beta.0
node-1   Ready    <none>   4m4s    v1.32.3   192.168.10.102   <none>        Debian GNU/Linux 12 (bookworm)   6.1.0-40-arm64   containerd://2.1.0-beta.0
```

두 노드 모두 `Ready` 상태로 클러스터에 등록되었다. 출력 필드의 의미는 다음과 같다.

- `STATUS: Ready`: kubelet이 정상 동작하고 Pod를 실행할 준비가 됨
- `ROLES: <none>`: 기본적으로 역할이 할당되지 않음. 필요시 `kubectl label`로 추가
- `VERSION`: kubelet 버전
- `INTERNAL-IP`: 노드의 내부 IP (192.168.10.x)
- `CONTAINER-RUNTIME`: 사용 중인 컨테이너 런타임

<br>

## 노드 상세 정보 확인

node-0의 상세 정보를 확인한다.

```bash
ssh server "kubectl get nodes node-0 -o yaml --kubeconfig admin.kubeconfig" | yq
```

```yaml
apiVersion: v1
kind: Node
metadata:
  name: node-0
  labels:
    kubernetes.io/arch: arm64
    kubernetes.io/hostname: node-0
    kubernetes.io/os: linux
spec: {}
status:
  addresses:
    - address: 192.168.10.101
      type: InternalIP
    - address: node-0
      type: Hostname
  allocatable:
    cpu: "2"
    memory: 1791292Ki
    pods: "16"
  capacity:
    cpu: "2"
    ephemeral-storage: 63739556Ki
    memory: 1893692Ki
    pods: "16"
  conditions:
    - type: Ready
      status: "True"
      reason: KubeletReady
      message: kubelet is posting ready status
    - type: MemoryPressure
      status: "False"
    - type: DiskPressure
      status: "False"
    - type: PIDPressure
      status: "False"
  nodeInfo:
    architecture: arm64
    containerRuntimeVersion: containerd://2.1.0-beta.0
    kernelVersion: 6.1.0-40-arm64
    kubeletVersion: v1.32.3
    operatingSystem: linux
    osImage: Debian GNU/Linux 12 (bookworm)
```

주요 정보:
- **allocatable.pods: "16"**: kubelet-config.yaml의 `maxPods: 16` 설정이 반영됨
- **conditions**: 모든 condition이 정상 (Ready=True, 나머지=False)
- **nodeInfo**: 운영체제, 커널, 런타임 버전 정보

<br>

## Pod 확인

아직 Pod를 배포하지 않았으므로 Pod가 없어야 정상이다.

```bash
ssh server "kubectl get pod -A --kubeconfig admin.kubeconfig"
No resources found
```

<br>

# 결과

이 단계를 완료하면 다음과 같은 결과를 얻을 수 있다:

1. **Worker Node 바이너리 설치**: containerd, runc, kubelet, kube-proxy, CNI 플러그인 설치 완료
2. **CNI 네트워킹 구성**: bridge, loopback 플러그인 설정, br_netfilter 모듈 활성화
3. **systemd 서비스 시작**: containerd, kubelet, kube-proxy 서비스 정상 실행
4. **클러스터 등록**: node-0, node-1이 `Ready` 상태로 등록
5. **노드 리소스**: 각 노드당 최대 16개 Pod 실행 가능

<br>

Worker Node 프로비저닝이 완료되었다. **드디어** Kubernetes 클러스터의 핵심 구성 요소가 모두 갖춰졌다:

| 컴포넌트 | 노드 | 역할 |
| --- | --- | --- |
| etcd | server | 클러스터 상태 저장소 |
| kube-apiserver | server | API 엔드포인트 |
| kube-scheduler | server | Pod 스케줄링 |
| kube-controller-manager | server | 컨트롤러 실행 |
| containerd | node-0, node-1 | 컨테이너 런타임 |
| kubelet | node-0, node-1 | 노드 에이전트 |
| kube-proxy | node-0, node-1 | 네트워크 프록시 |


<br> 

다음 단계에서는 jumpbox에서 원격으로 클러스터를 관리할 수 있도록 kubectl을 설정한다.
