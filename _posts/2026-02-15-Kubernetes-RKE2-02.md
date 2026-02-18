---
title:  "[Kubernetes] Cluster: RKE2를 이용해 클러스터 구성하기 - 2. 에이전트 노드 조인"
excerpt: "RKE2 에이전트 노드를 설치하고 서버 노드에 조인한 뒤, 샘플 파드 배포로 클러스터를 확인한다."
categories:
  - Kubernetes
toc: true
header:
  teaser: /assets/images/blog-Dev.jpg
tags:
  - Kubernetes
  - RKE2
  - On-Premise-K8s-Hands-On-Study
  - On-Premise-K8s-Hands-On-Study-Week-7

---

*[서종호(가시다)](https://www.linkedin.com/in/gasida99/)님의 On-Premise K8s Hands-on Study 7주차 학습 내용을 기반으로 합니다.*

<br>

# TL;DR

이번 글의 목표는 **RKE2 에이전트 노드를 클러스터에 조인하고 멀티 노드 클러스터를 완성**하는 것이다.

- **에이전트 설치**: 동일한 설치 스크립트를 `INSTALL_RKE2_TYPE=agent`로 실행
- **설정**: 서버 URL(포트 9345), 토큰, NIC 지정 (`config.yaml`)
- **조인 과정**: 에이전트 프로세스 라이프사이클 확인
- **결과 확인**: 에이전트 노드 디렉터리 구조, `server/`가 없는 이유
- **클러스터 검증**: 샘플 파드 배포로 멀티 노드 클러스터 동작 확인

<br>

# 들어가며

[이전 글]({% post_url 2026-02-15-Kubernetes-RKE2-01-02 %})에서 RKE2 서버 노드에서 생성된 디렉터리와 설정 파일을 상세히 확인했다. `server/token`에 에이전트 조인용 토큰이 있고, 에이전트 노드는 이 토큰과 서버 URL을 `config.yaml`에 설정해서 클러스터에 합류한다는 내용을 짚었다.

이번 글에서는 그 조인 과정을 직접 진행한다. 에이전트 설치와 서비스 기동은 서버보다 훨씬 단순하다. 설치 방법 외에도 에이전트 라이프사이클이 서버와 어떻게 다른지, 조인 후 만들어지는 디렉터리 구조가 서버 노드와 어떻게 다른지를 함께 확인한다.

<br>

# RKE2 에이전트 노드 설치

## 토큰 확인

에이전트 노드가 클러스터에 조인하려면 서버 노드의 토큰이 필요하다. 서버 노드(node1)에서 토큰을 확인한다.

```bash
# node1에서 실행
cat /var/lib/rancher/rke2/server/node-token
# K1037f1b1f84d631265adcff239308d8b19ae073480250e9fcded6330c97452ad8d::server:158adc28471c9fd7122146cb86bfb5a5
```

토큰 형식은 `K1<sha256>::<type>:<secret>` 구조다. `server`가 타입이고 뒤의 hex 문자열이 실제 secret이다.

서버 토큰은 서비스 시작 시 자동으로 생성되고 만료되지 않는다. kubeadm의 bootstrap token은 24시간 후 만료되어 재발급이 필요했다. RKE2의 서버 토큰은 영구적이라 관리 부담이 없다.

서버 노드에서 9345 포트가 열려 있는지도 확인한다. 에이전트가 조인할 때 사용하는 RKE2 supervisor 등록 포트다.

```bash
# node1에서 실행
ss -tnlp | grep 9345
# LISTEN 0  4096  192.168.10.11:9345  0.0.0.0:*  users:(("rke2",pid=133127,fd=6))
# LISTEN 0  4096      127.0.0.1:9345  0.0.0.0:*  users:(("rke2",pid=133127,fd=7))
# LISTEN 0  4096          [::1]:9345     [::]:*  users:(("rke2",pid=133127,fd=8))
```

<br>

## 에이전트 설치

에이전트 노드(node2)에 접속해서 설치한다. 설치 스크립트는 서버와 동일하지만 `INSTALL_RKE2_TYPE="agent"`를 지정하는 것이 차이점이다.

```bash
# node2에서 실행
curl -sfL https://get.rke2.io | INSTALL_RKE2_TYPE="agent" INSTALL_RKE2_CHANNEL=v1.33 sh -
```

```
[INFO]  using stable RPM repositories
[INFO]  using 1.33 series from channel stable
...
Installing:
 rke2-agent              aarch64  1.33.8~rke2r1-0.el9  rancher-rke2-1.33-stable  8.3 k
Installing dependencies:
 rke2-common             aarch64  1.33.8~rke2r1-0.el9  rancher-rke2-1.33-stable   25 M
 rke2-selinux            noarch   0.22-1.el9            rancher-rke2-common-stable 22 k
...
Installed:
  rke2-agent-1.33.8~rke2r1-0.el9.aarch64  rke2-common-1.33.8~rke2r1-0.el9.aarch64  rke2-selinux-0.22-1.el9.noarch
```

서버 설치와 비교하면 `rke2-server` 대신 `rke2-agent`가 설치된다. `rke2-common`과 `rke2-selinux`는 서버와 공통이다. `rke2-agent` 패키지에는 `rke2-agent.service` systemd 유닛 파일이 포함된다.

<br>

## config.yaml 작성

에이전트 노드에서도 설정 파일 경로는 `/etc/rancher/rke2/config.yaml`로 동일하다. 서버와 달리 컨트롤 플레인 관련 설정은 없고, 어느 서버에 조인할지와 인증 정보만 필요하다.

```bash
# node2에서 실행
TOKEN=K1037f1b1f84d631265adcff239308d8b19ae073480250e9fcded6330c97452ad8d::server:158adc28471c9fd7122146cb86bfb5a5

mkdir -p /etc/rancher/rke2/
cat << EOF > /etc/rancher/rke2/config.yaml
server: https://192.168.10.11:9345
token: $TOKEN
node-ip: 192.168.10.12
EOF

cat /etc/rancher/rke2/config.yaml
# server: https://192.168.10.11:9345
# token: K1037f1b1f84d631265adcff239308d8b19ae073480250e9fcded6330c97452ad8d::server:158adc28471c9fd7122146cb86bfb5a5
# node-ip: 192.168.10.12
```

`server` 항목의 포트가 `9345`인 점이 눈에 띈다. API 서버 포트(6443)와 다르다.

| 포트 | 용도 | 접근 주체 |
| --- | --- | --- |
| **6443** | Kubernetes API 서버 | kubectl, 파드, 외부 클라이언트 |
| **9345** | RKE2 supervisor 등록 엔드포인트 | 에이전트 노드 조인 시 |

에이전트가 조인할 때 Kubernetes API 서버(6443)가 아니라 RKE2 supervisor가 노출하는 등록 엔드포인트(9345)에 먼저 접속한다. 클러스터 메타데이터(CA 인증서, API 서버 엔드포인트, 초기 설정 등)를 받아온 뒤 kubelet 등록을 진행하는 방식이다. kubeadm의 `kubeadm join`은 처음부터 6443에 접속했다. RKE2는 supervisor 레이어가 존재하기 때문에 별도 등록 포트가 있다.

`node-ip`를 `192.168.10.12`로 지정하는 이유는 서버 노드에서와 같다. VirtualBox VM에 NAT NIC(`enp0s3`, `10.0.2.15`)와 호스트 전용 NIC(`enp0s9`, `192.168.10.12`)가 함께 있기 때문에, 클러스터 내부 통신에 사용할 NIC를 명시적으로 지정해야 한다. 이 설정이 없으면 노드가 조인되더라도 `INTERNAL-IP`가 NAT IP로 등록된다.

<br>

## 서비스 시작

```bash
# node2에서 실행

# 서비스 시작 후 로그 확인
systemctl enable --now rke2-agent.service
journalctl -u rke2-agent -f
```

node1에서 `kube-system` 네임스페이스를 관찰하면 node2 조인과 함께 관련 파드가 생성되는 과정을 볼 수 있다. 노드 상태가 `NotReady`에서 `Ready`로 변화하는 모습도 확인할 수 있다.

![rke2-agent-join]({{site.url}}/assets/images/rke2-agent-join.gif)

에이전트가 뜨는 과정을 프로세스 트리로 보면 서버와 유사하지만 훨씬 단순하다.

```bash
# 1단계: rke2 supervisor만 보임
rke2

# 2단계: containerd spawn
rke2
└── containerd

# 3단계: kubelet spawn
rke2
├── containerd
└── kubelet

# 4단계: containerd-shim들이 나타남 (kube-proxy static pod, canal DaemonSet Pod 기동)
rke2
├── containerd
├── kubelet
containerd-shim-runc-v2  ← kube-proxy
containerd-shim-runc-v2  ← canal
```

서버와 비교하면 etcd, kube-apiserver, kube-controller-manager, kube-scheduler가 없다. 에이전트 노드는 컨트롤 플레인 컴포넌트 없이 kubelet과 kube-proxy, 그리고 DaemonSet으로 배포되는 CNI만 실행한다.

<br>

서비스 상태와 프로세스 트리를 확인한다.

```bash
systemctl status rke2-agent.service --no-pager
● rke2-agent.service - Rancher Kubernetes Engine v2 (agent)
     Loaded: loaded (/usr/lib/systemd/system/rke2-agent.service; enabled; preset: disabled)
     Active: active (running) since Thu 2026-02-19 01:04:01 KST; 2min 56s ago
   Main PID: 6453 (rke2)
      Tasks: 61
     Memory: 2.2G
     CGroup: /system.slice/rke2-agent.service
             ├─6453 "/usr/bin/rke2 agent"
             ├─6477 containerd -c /var/lib/rancher/rke2/agent/etc/containerd/config.toml
             ├─6531 kubelet --volume-plugin-dir=/var/lib/kubelet/volumeplugins ...
             ├─6597 /var/lib/rancher/rke2/data/v1.33.8-rke2r1-1b2872361ec5/bin/containerd-shim-runc-v2 ...
             └─6598 /var/lib/rancher/rke2/data/v1.33.8-rke2r1-1b2872361ec5/bin/containerd-shim-runc-v2 ...
```

서버와 구조가 같다. `rke2 agent` 프로세스가 Main PID이고, containerd와 kubelet이 자식으로 있다.

```bash
pstree -al | grep -A5 'rke2$'
  |-rke2
  |   |-containerd -c /var/lib/rancher/rke2/agent/etc/containerd/config.toml
  |   |   └─11*[{containerd}]
  |   |-kubelet --volume-plugin-dir=/var/lib/kubelet/volumeplugins ...
  |   |   └─11*[{kubelet}]
  |   └─10*[{rke2}]
```

서버 노드의 pstree 결과와 구조가 같다. containerd-shim들은 rke2 트리 밖에 PID 1의 자식으로 나타난다. canal과 kube-proxy 컨테이너에 각각 shim이 붙어 있다.

```bash
pstree -al | grep -A5 'containerd-shim' | head -20
  |-containerd-shim -namespace k8s.io -id 835eea162bfc93d7... -address /run/k3s/containerd/containerd.sock
  |   |-flanneld --ip-masq --kube-subnet-mgr ...
  |   |-pause
  |   |-runsvdir -P /etc/service/enabled
  |   |   ├─runsv felix
  |   |   |   └─calico-node -felix
  ...
  |-containerd-shim -namespace k8s.io -id ca5e31812e3807fe... -address /run/k3s/containerd/containerd.sock
  |   |-kube-proxy --cluster-cidr=10.42.0.0/16 ...
  |   |-pause
```

shim이 2개다. 서버 노드(8~10개)보다 훨씬 적다. 실행 중인 컨테이너가 kube-proxy와 canal 2개뿐이기 때문이다.

<br>

# 에이전트 노드 디렉터리 구조

조인 후 에이전트 노드에서 생성된 디렉터리를 확인한다. 서버 노드와의 차이가 핵심이다.

```bash
# node2에서 실행
tree /var/lib/rancher/rke2 -L 1
/var/lib/rancher/rke2
├── agent
├── bin -> /var/lib/rancher/rke2/data/v1.33.8-rke2r1-1b2872361ec5/bin
└── data
```

서버 노드(`agent/`, `bin/`, `data/`, `server/`)와 달리 **`server/` 디렉터리가 없다**. `server/`에는 etcd 데이터, PKI, 인증서, 조인 토큰 등 컨트롤 플레인 운영에 필요한 모든 상태가 들어 있다. 에이전트 노드는 컨트롤 플레인을 실행하지 않으므로 이 디렉터리 자체가 생성되지 않는다.

```bash
tree /var/lib/rancher/rke2/agent/ -L 2
/var/lib/rancher/rke2/agent/
├── client-ca.crt
├── client-kubelet.crt, .key
├── client-kube-proxy.crt, .key
├── client-rke2-controller.crt, .key
├── containerd/
├── etc/
│   ├── containerd/
│   │   └── config.toml
│   ├── crictl.yaml
│   ├── kubelet.conf.d/
│   │   └── 00-rke2-defaults.conf
│   ├── rke2-agent-load-balancer.json        ← 에이전트 노드에만 있는 파일
│   └── rke2-api-server-agent-load-balancer.json  ← 에이전트 노드에만 있는 파일
├── images/
│   ├── kube-proxy-image.txt
│   └── runtime-image.txt
├── kubelet.kubeconfig
├── kubeproxy.kubeconfig
├── logs/
├── pod-manifests/
│   └── kube-proxy.yaml                      ← kube-proxy 하나만 있음
├── server-ca.crt
├── serving-kubelet.crt, .key
└── rke2controller.kubeconfig
```

서버 노드의 `agent/` 구조와 거의 동일하지만 두 가지 차이가 있다.

## pod-manifests

첫 번째는 `pod-manifests/` 내용이다.

```bash
# 서버 노드 (node1)
tree /var/lib/rancher/rke2/agent/pod-manifests
├── etcd.yaml
├── kube-apiserver.yaml
├── kube-controller-manager.yaml
├── kube-proxy.yaml
└── kube-scheduler.yaml

# 에이전트 노드 (node2)
tree /var/lib/rancher/rke2/agent/pod-manifests
└── kube-proxy.yaml
```

에이전트 노드의 `pod-manifests/`에는 `kube-proxy.yaml` 하나만 있다. etcd, kube-apiserver, kube-controller-manager, kube-scheduler는 서버 노드에서만 실행되는 static pod다.

## load balancer JSON

두 번째는 load balancer JSON 파일이다. 서버 노드에는 없고 에이전트 노드에만 생성된다.

```bash
cat /var/lib/rancher/rke2/agent/etc/rke2-agent-load-balancer.json
{
  "ServerURL": "https://192.168.10.11:9345",
  "ServerAddresses": [
    "192.168.10.11:9345"
  ]
}

cat /var/lib/rancher/rke2/agent/etc/rke2-api-server-agent-load-balancer.json
{
  "ServerURL": "https://192.168.10.11:6443",
  "ServerAddresses": [
    "192.168.10.11:6443"
  ]
}
```

`rke2-agent-load-balancer.json`은 에이전트가 supervisor에 접속하는 9345 엔드포인트를, `rke2-api-server-agent-load-balancer.json`은 kubelet이 API 서버에 접속하는 6443 엔드포인트를 추적한다. 서버가 여러 대인 HA 구성에서 에이전트가 어떤 서버에 접속할지를 관리하는 데 사용된다.

서버 노드에는 이 파일들이 없다. 서버 노드 자체가 supervisor를 실행하기 때문에 외부 supervisor에 접속할 필요가 없기 때문이다.

## kubelet 설정

에이전트 노드의 kubelet 설정도 서버와 차이가 있다.

```bash
cat /var/lib/rancher/rke2/agent/etc/kubelet.conf.d/00-rke2-defaults.conf
address: 0.0.0.0                    ← 서버 노드는 192.168.10.11로 고정됨
allowedUnsafeSysctls:               ← 서버 노드에는 없는 설정
- net.ipv4.ip_forward
- net.ipv6.conf.all.forwarding
...
```

`address: 0.0.0.0` — 서버 노드는 `192.168.10.11`로 특정 인터페이스에 바인딩됐지만, 에이전트 노드는 모든 인터페이스에서 kubelet API를 수신한다.

`allowedUnsafeSysctls` — 파드 내에서 `net.ipv4.ip_forward`, `net.ipv6.conf.all.forwarding` sysctl을 사용할 수 있도록 허용한다. 에이전트 노드는 실제 파드가 실행되는 워커 역할을 하므로, 파드 수준에서 네트워크 포워딩이 필요한 워크로드(ex. 네트워크 관련 시스템 파드)를 수용하기 위한 설정이다.

<br>

# 클러스터 상태 확인

서버 노드(node1)에서 클러스터 상태를 확인한다.

```bash
# node1에서 실행
kubectl get node -o wide
# NAME               STATUS   ROLES                       AGE    VERSION          INTERNAL-IP     OS-IMAGE                      CONTAINER-RUNTIME
# week07-k8s-node1   Ready    control-plane,etcd,master   4h3m   v1.33.8+rke2r1   192.168.10.11   Rocky Linux 9.6 (Blue Onyx)   containerd://2.1.5-k3s1
# week07-k8s-node2   Ready    <none>                      119s   v1.33.8+rke2r1   192.168.10.12   Rocky Linux 9.6 (Blue Onyx)   containerd://2.1.5-k3s1
```

두 노드 모두 `Ready` 상태다. `INTERNAL-IP`가 각각 `192.168.10.11`, `192.168.10.12`로 호스트 전용 NIC IP가 등록됐다. `config.yaml`에 `node-ip`를 명시적으로 지정한 결과다.

`ROLES` 컬럼에서 node2는 `<none>`이다. kubeadm에서는 워커 노드 조인 시 `worker` Role이 자동으로 붙었다. RKE2는 에이전트 노드에 Role을 자동으로 부여하지 않는다.

```bash
# worker Role 라벨 추가
kubectl label node week07-k8s-node2 node-role.kubernetes.io/worker=worker

kubectl get node
# NAME               STATUS   ROLES                       AGE
# week07-k8s-node1   Ready    control-plane,etcd,master   4h4m
# week07-k8s-node2   Ready    worker                      2m
```

파드 상태도 확인한다.

```bash
kubectl get pod -n kube-system -o wide | grep k8s-node2
# kube-proxy-week07-k8s-node2  1/1  Running  0  2m  192.168.10.12  week07-k8s-node2
# rke2-canal-j6h6t             2/2  Running  0  2m  192.168.10.12  week07-k8s-node2
```


node2가 조인되자 DaemonSet 기반 컴포넌트들이 node2에도 배포됐다.

- `kube-proxy-week07-k8s-node2`: 에이전트 노드의 `pod-manifests/kube-proxy.yaml`에서 kubelet이 기동하는 static pod다.
- `rke2-canal-j6h6t`: Canal은 DaemonSet이다. 새 노드가 추가되면 Helm Controller가 배포한 Canal DaemonSet이 자동으로 해당 노드에 Pod를 스케줄한다.

node2에서 crictl로 직접 확인한다.

```bash
# node2에서 실행
ln -s /var/lib/rancher/rke2/bin/crictl /usr/local/bin/crictl
ln -s /var/lib/rancher/rke2/agent/etc/crictl.yaml /etc/crictl.yaml

crictl ps
# CONTAINER  IMAGE  CREATED      STATE    NAME           POD ID  POD
# b39af908   fc623  3 min ago   Running  kube-flannel   835eea  rke2-canal-j6h6t     kube-system
# ecbd11e0   3b961  4 min ago   Running  calico-node    835eea  rke2-canal-j6h6t     kube-system
# 692eaa7f   603f9  4 min ago   Running  kube-proxy     ca5e31  kube-proxy-week07-k8s-node2  kube-system

crictl images
# IMAGE                                   TAG                            SIZE
# docker.io/rancher/hardened-calico       v3.31.3-build20260206          217MB
# docker.io/rancher/hardened-flannel      v0.28.1-build20260206          19.8MB
# docker.io/rancher/hardened-kubernetes   v1.33.8-rke2r1-build20260210   187MB
# docker.io/rancher/mirrored-pause        3.6                            253kB
# docker.io/rancher/rke2-runtime          v1.33.8-rke2r1                 91.3MB
```

서버 노드의 `crictl images`와 비교하면 이미지 수가 적다. 서버 노드에는 coredns, metrics-server, klipper-helm, etcd 등이 더 있다. 에이전트 노드에는 실제로 실행 중인 컨테이너에 필요한 이미지만 존재한다.

<br>


# 에이전트 노드 삭제와 재조인

에이전트 노드를 클러스터에서 제거하고 다시 추가하는 과정을 확인한다.

## 노드 삭제 (서버 노드에서)

```bash
# node1에서 실행

# 노드 drain: 파드를 안전하게 이동시킨 뒤 새 스케줄 차단
kubectl drain week07-k8s-node2 --ignore-daemonsets --delete-emptydir-data
# node/week07-k8s-node2 cordoned
# Warning: ignoring DaemonSet-managed Pods: kube-system/rke2-canal-j6h6t
# node/week07-k8s-node2 drained

kubectl get nodes
# NAME               STATUS                     ROLES                       AGE
# week07-k8s-node1   Ready                      control-plane,etcd,master   4h10m
# week07-k8s-node2   Ready,SchedulingDisabled   <none>                      8m16s

# 클러스터에서 노드 오브젝트 삭제
kubectl delete node week07-k8s-node2
# node "week07-k8s-node2" deleted
```

`kubectl delete node`는 Kubernetes API에서 노드 오브젝트를 제거하는 것이다. 에이전트 프로세스(`rke2-agent`)는 node2에서 계속 실행 중이다.

## RKE2 제거 (에이전트 노드에서)

RKE2 패키지를 설치하면 `rke2-uninstall.sh`와 `rke2-killall.sh`가 함께 제공된다.

```bash
# node2에서 실행

# 서비스 중지
systemctl stop rke2-agent

# 언인스톨 스크립트 실행
# 컨테이너 종료, 네트워크 인터페이스 정리, RPM 제거, 디렉터리 삭제까지 처리
rke2-uninstall.sh
```

스크립트가 완료되면 `/etc/rancher`, `/var/lib/rancher` 디렉터리가 모두 삭제된다.

```bash
tree /etc/rancher
# /etc/rancher [error opening dir]
tree /var/lib/rancher
# /var/lib/rancher [error opening dir]
```

## 재조인

재조인은 최초 조인과 동일한 절차다. 토큰은 서버 노드에서 바뀌지 않았으므로 그대로 사용할 수 있다.

```bash
# node2에서 실행
curl -sfL https://get.rke2.io | INSTALL_RKE2_TYPE="agent" INSTALL_RKE2_CHANNEL=v1.33 sh -

TOKEN=K1037f1b1f84d631265adcff239308d8b19ae073480250e9fcded6330c97452ad8d::server:158adc28471c9fd7122146cb86bfb5a5

mkdir -p /etc/rancher/rke2/
cat << EOF > /etc/rancher/rke2/config.yaml
server: https://192.168.10.11:9345
token: $TOKEN
node-ip: 192.168.10.12
EOF

systemctl enable --now rke2-agent.service
```

RKE2 토큰이 만료되지 않기 때문에 기존 토큰으로 재조인이 가능하다. kubeadm에서는 토큰이 만료된 경우 `kubeadm token create`로 새 토큰을 생성하고 `kubeadm token list`로 확인해야 했다. RKE2는 이 과정이 불필요하다.

<br>

# 서버 노드 vs 에이전트 노드 비교

클러스터를 완성하고 나서 두 노드의 차이를 정리한다.

| 항목 | 서버 노드 (node1) | 에이전트 노드 (node2) |
| --- | --- | --- |
| **systemd 서비스** | `rke2-server.service` | `rke2-agent.service` |
| **실행 명령** | `rke2 server` | `rke2 agent` |
| **컨트롤 플레인** | etcd, kube-apiserver, kcm, scheduler | 없음 |
| **static pod 수** | 5개 (etcd, apiserver, kcm, scheduler, kube-proxy) | 1개 (kube-proxy) |
| **`server/` 디렉터리** | 있음 (PKI, etcd, token, manifests) | 없음 |
| **`rke2.yaml` (kubeconfig)** | `/etc/rancher/rke2/rke2.yaml` | 없음 |
| **조인 설정** | 없음 (최초 서버) | `server:`, `token:` 필요 |
| **load balancer JSON** | 없음 | `rke2-agent-load-balancer.json` 생성 |
| **`allowedUnsafeSysctls`** | 없음 | `net.ipv4.ip_forward` 등 허용 |
| **Node ROLES** | `control-plane,etcd,master` | `<none>` (수동 지정 필요) |

<br>

kubeadm의 `kubeadm join`과 비교하면:

| 항목 | kubeadm join | RKE2 agent |
| --- | --- | --- |
| **조인 방식** | `kubeadm join <host>:6443 --token ... --discovery-token-ca-cert-hash ...` | `config.yaml`에 `server:`, `token:` 설정 후 systemctl start |
| **토큰 만료** | 24시간 | 만료 없음 |
| **서버 접속 포트** | 6443 (API 서버 직접) | 9345 (supervisor 등록 엔드포인트) |
| **kube-proxy** | DaemonSet | static pod |
| **CNI 배포** | 별도 `kubectl apply` 필요 | Helm Controller가 자동 처리 |

<br>


# 샘플 파드 배포

배포 전에 서버 노드의 Taint를 확인한다.

```bash
# node1에서 실행
kubectl describe node week07-k8s-node1 | grep -A5 Taints
# Taints:             <none>
```

kubeadm은 컨트롤 플레인 노드에 `node-role.kubernetes.io/control-plane:NoSchedule` Taint를 기본으로 설정해 워크로드 파드가 컨트롤 플레인에 스케줄되지 않도록 한다. RKE2의 컨트롤 플레인에는 Taint가 없다. K3s의 설계를 계승한 것으로, 노드 1대만으로도 완전한 클러스터가 동작해야 한다는 철학 때문이다. 서버 노드에도 일반 파드가 스케줄될 수 있다.

명시적으로 Taint를 걸고 싶다면 `config.yaml`에 `node-taint`를 추가하거나 `kubectl taint`로 직접 설정하면 된다.

배포 매니페스트는 `podAntiAffinity`를 사용해 두 파드가 서로 다른 노드에 배포되도록 한다.

```bash
# node1에서 실행
cat << EOF | kubectl apply -f -
apiVersion: apps/v1
kind: Deployment
metadata:
  name: webpod
spec:
  replicas: 2
  selector:
    matchLabels:
      app: webpod
  template:
    metadata:
      labels:
        app: webpod
    spec:
      affinity:
        podAntiAffinity:
          requiredDuringSchedulingIgnoredDuringExecution:
          - labelSelector:
              matchExpressions:
              - key: app
                operator: In
                values:
                - sample-app
            topologyKey: "kubernetes.io/hostname"
      containers:
      - name: webpod
        image: traefik/whoami
        ports:
        - containerPort: 80
---
apiVersion: v1
kind: Service
metadata:
  name: webpod
  labels:
    app: webpod
spec:
  selector:
    app: webpod
  ports:
  - protocol: TCP
    port: 80
    targetPort: 80
    nodePort: 30000
  type: NodePort
EOF
# deployment.apps/webpod created
# service/webpod created
```

```bash
kubectl get deploy,pod,svc,ep -o wide
# NAME                     READY   UP-TO-DATE   AVAILABLE   AGE   CONTAINERS   IMAGES           SELECTOR
# deployment.apps/webpod   2/2     2            2           10s   webpod       traefik/whoami   app=webpod
#
# NAME                          READY   STATUS    RESTARTS   AGE   IP          NODE               NOMINATED NODE   READINESS GATES
# pod/webpod-697b545f57-brtbk   1/1     Running   0          10s   10.42.2.2   week07-k8s-node2   <none>           <none>
# pod/webpod-697b545f57-tqkrt   1/1     Running   0          10s   10.42.0.6   week07-k8s-node1   <none>           <none>
#
# NAME                 TYPE        CLUSTER-IP      EXTERNAL-IP   PORT(S)        AGE     SELECTOR
# service/kubernetes   ClusterIP   10.43.0.1       <none>        443/TCP        4h18m   <none>
# service/webpod       NodePort    10.43.194.214   <none>        80:30000/TCP   10s     app=webpod
#
# NAME                   ENDPOINTS                   AGE
# endpoints/kubernetes   192.168.10.11:6443          4h18m
# endpoints/webpod       10.42.0.6:80,10.42.2.2:80   10s
```

파드 2개가 각각 node1(`10.42.0.6`)과 node2(`10.42.2.2`)에 분산 배포됐다. `podAntiAffinity`가 정상 동작한 결과다.

`endpoints/webpod`에 두 파드의 IP가 모두 등록됐다. NodePort 30000으로 접근 테스트를 한다.

```bash
# node1에서 실행
curl -s http://192.168.10.11:30000 | grep Hostname
# Hostname: webpod-697b545f57-tqkrt

curl -s http://192.168.10.12:30000 | grep Hostname
# Hostname: webpod-697b545f57-brtbk
```

두 노드 모두에서 NodePort로 접근이 되고, 각 노드에 배포된 파드가 응답한다. kube-proxy가 iptables 규칙을 통해 NodePort 트래픽을 파드로 전달하는 구조가 node2에서도 정상 동작함을 확인했다.

<br>

# 결과

RKE2 에이전트 노드 조인을 완료하고, 샘플 파드 배포로 멀티 노드 클러스터 동작을 확인했다.

- 에이전트 설치는 서버와 동일한 스크립트에 `INSTALL_RKE2_TYPE="agent"`만 추가하면 된다.
- `config.yaml`에 서버 URL(포트 9345)과 토큰만 지정하면 조인이 완료된다.
- 에이전트 노드에는 `server/` 디렉터리가 생성되지 않는다. 컨트롤 플레인이 없기 때문이다.
- Canal DaemonSet은 새 노드 조인 시 자동으로 파드를 배포한다.
- nginx Deployment를 통해 두 노드에 파드가 분산 배포되고 ClusterIP를 통한 통신이 정상 동작하는 것을 확인했다.
- RKE2 토큰은 만료되지 않아 언인스톨 후 재조인 시에도 동일한 토큰을 사용할 수 있다.

<br>

# 참고

- [RKE2 Agent Install](https://docs.rke2.io/install/linux_agent_install)
- [RKE2 Configuration Reference](https://docs.rke2.io/reference/server_config)
- [RKE2 Token Security](https://docs.rke2.io/security/token)
- [RKE2 Architecture](https://docs.rke2.io/architecture)
