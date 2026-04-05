---
title:  "[Kubernetes] kubeconfig - 2. 다중 클러스터 접근 구성"
excerpt: "여러 Kubernetes 클러스터를 하나의 kubeconfig로 관리해보자."
categories:
  - Kubernetes
toc: true
header:
  teaser: /assets/images/blog-Dev.jpg
tags:
  - Kubernetes
  - kubeconfig
  - kubectl
  - Context
  - Multipass
  - kind
  - k3s
  - kubeadm
---

<br>

# 들어가며

[이전 글]({% post_url 2026-02-16-Kubernetes-Kubeconfig-01 %})에서 kubeconfig의 개념과 구조를 살펴보았다. 이번 글에서는 실제로 여러 Kubernetes 클러스터를 구성하고, 하나의 작업 환경에서 `KUBECONFIG` 환경 변수 병합과 `kubectl config use-context`를 이용하여 컨텍스트를 전환하는 실습을 진행한다.

공식 문서의 [다중 클러스터 접근 구성하기](https://kubernetes.io/docs/tasks/access-application-cluster/configure-access-multiple-clusters/) 가이드를 참고하되, 실제 클러스터 환경에서 진행한다.


<br>

# 실습 환경

## 구성도

[Multipass](https://multipass.run/)로 4개의 VM을 생성한다. jumpbox에서 kubectl로 나머지 3개 클러스터에 접근하는 구조이다.

```
┌──────────────────────────────────────────────────┐
│  Host (macOS - Apple Silicon)                    │
│  Multipass                                       │
│                                                  │
│  ┌───────────┐  ┌───────────┐  ┌──────────────┐  │
│  │  jumpbox  │  │ kind-node │  │ kubeadm-node │  │
│  │ (kubectl) │  │  (kind)   │  │  (kubeadm)   │  │
│  └───────────┘  └───────────┘  └──────────────┘  │
│                  ┌───────────┐                   │
│                  │ k3s-node  │                   │
│                  │   (k3s)   │                   │
│                  └───────────┘                   │
│  (모든 VM은 Multipass 브리지 네트워크로 연결)           │
└──────────────────────────────────────────────────┘
```

| VM | 역할 | 리소스 |
| --- | --- | --- |
| jumpbox | kubectl만 설치된 관리 노드 | 1GB RAM, 1 CPU, 10GB Disk |
| kind-node | Docker + kind 클러스터 | 4GB RAM, 2 CPU, 20GB Disk |
| k3s-node | k3s 클러스터 | 2GB RAM, 2 CPU, 15GB Disk |
| kubeadm-node | kubeadm 클러스터 | 4GB RAM, 2 CPU, 20GB Disk |

> Multipass는 VM에 IP를 동적으로 할당한다(DHCP). Vagrant처럼 IP를 미리 지정할 수는 없지만, 같은 브리지 네트워크 위에 있으므로 **VM 간 통신에는 문제가 없다**. VM 생성 후 `multipass list`로 할당된 IP를 확인하고, 이후 과정에서 해당 IP를 사용하면 된다.


## 핵심 주의 사항

| 주의 사항 | 적용 위치 |
| --- | --- |
| **VM IP 확인 후 진행** | `multipass list`로 각 VM의 IP를 먼저 확인 |
| **API server bind address를 VM IP로** | kind의 `apiServerAddress`, k3s의 `--bind-address`, kubeadm의 `--apiserver-advertise-address` |
| **TLS SAN에 VM IP 추가** | k3s의 `--tls-san`, kubeadm은 advertise-address가 자동으로 SAN에 포함 |
| **kubeconfig의 server 주소를 VM IP로 변경** | 특히 k3s는 기본이 `127.0.0.1`이므로 치환 필수 |
| **jumpbox의 KUBECONFIG 환경 변수** | `.bashrc`에 미리 export 설정 |


## 클러스터 배포 도구별 차이

| 도구 | 특징 |
| --- | --- |
| **kind** | Docker 위에서 동작. Docker만 있으면 됨. containerd/kubelet은 kind가 컨테이너 안에 알아서 설치 |
| **k3s** | `curl -sfL get.k3s.io \| sh -` 한 줄로 containerd + kubelet + kubectl 전부 포함 설치 |
| **kubeadm** | 가장 저수준 도구. 아무것도 대신 설치해 주지 않으므로 사전 준비(containerd, kubelet 등)를 전부 직접 해야 함 |

이 실습의 목적은 **다중 클러스터 kubeconfig 병합 및 context 전환 확인**이므로, 클러스터별 Kubernetes 버전이 달라도 상관없다. 버전은 의도적으로 다르게 잡은 것이 아니라, kind·k3s는 각 도구의 기본(또는 stable) 버전으로 설치되고, kubeadm만 APT 저장소로 v1.31을 지정한 것이다.

<br>

# VM 생성

## Multipass 설치

```bash
brew install multipass
```

## VM 생성

4개의 VM을 생성한다. Multipass는 기본 이미지로 Ubuntu를 사용한다.

```bash
multipass launch --name jumpbox     --memory 1G  --cpus 1 --disk 10G
multipass launch --name kind-node   --memory 4G  --cpus 2 --disk 20G
multipass launch --name k3s-node    --memory 2G  --cpus 2 --disk 15G
multipass launch --name kubeadm-node --memory 4G --cpus 2 --disk 20G
```

## IP 확인

VM 생성이 완료되면, 각 VM에 할당된 IP를 확인한다. 이후 과정에서 이 IP를 사용한다.

```bash
multipass list
```

```bash
Name                    State             IPv4             Image
jumpbox                 Running           192.168.2.2      Ubuntu 24.04 LTS
k3s-node                Running           192.168.2.4      Ubuntu 24.04 LTS
kind-node               Running           192.168.2.3      Ubuntu 24.04 LTS
kubeadm-node            Running           192.168.2.5      Ubuntu 24.04 LTS
```

이후 명령어에서 사용할 수 있도록, 호스트 셸에서 각 VM의 IP를 변수로 저장해 두면 편리하다.

```bash
# 각 VM의 IP를 변수로 저장 (위 출력 결과에 따라 수정)
KIND_IP=$(multipass info kind-node --format csv | tail -1 | cut -d',' -f3)
K3S_IP=$(multipass info k3s-node --format csv | tail -1 | cut -d',' -f3)
KUBEADM_IP=$(multipass info kubeadm-node --format csv | tail -1 | cut -d',' -f3)

echo "kind-node:    $KIND_IP"
echo "k3s-node:     $K3S_IP"
echo "kubeadm-node: $KUBEADM_IP"
```


<br>

# 클러스터 프로비저닝

각 VM에 접속하여 클러스터를 구성한다. `multipass exec`로 명령어를 실행하거나, `multipass shell`로 직접 접속할 수 있다.

> 이하 스크립트에서 아키텍처 감지(`$(dpkg --print-architecture)`, `$(uname -m)` 등)를 사용하므로, Apple Silicon 호스트에서 생성된 ARM64 VM에서도 정상 동작한다.


## kind 클러스터

kind는 Docker 위에서 동작하므로 Docker를 먼저 설치한 뒤, `apiServerAddress`를 VM IP로 지정하여 클러스터를 생성한다.

### Docker, kind, kubectl 설치

```bash
multipass exec kind-node -- bash -c "
set -e

# Docker 설치
sudo apt-get update && sudo apt-get install -y docker.io
sudo systemctl enable --now docker
sudo usermod -aG docker ubuntu

# kind 설치
ARCH=\$(dpkg --print-architecture)  # amd64 또는 arm64
sudo curl -Lo /usr/local/bin/kind https://kind.sigs.k8s.io/dl/v0.27.0/kind-linux-\${ARCH}
sudo chmod +x /usr/local/bin/kind

# kubectl 설치
sudo curl -LO \"https://dl.k8s.io/release/\$(curl -Ls https://dl.k8s.io/release/stable.txt)/bin/linux/\${ARCH}/kubectl\"
sudo install kubectl /usr/local/bin/
"
```

설치 여부를 확인한다.

```bash
multipass exec kind-node -- docker --version
multipass exec kind-node -- kind --version
multipass exec kind-node -- kubectl version --client
```

```
Docker version 28.2.2, build 28.2.2-0ubuntu1~24.04.1
kind version 0.27.0
Client Version: v1.35.1
Kustomize Version: v5.7.1
```

### kind 클러스터 생성

Docker 그룹 변경을 반영하기 위해, `sg docker -c`로 명령을 실행한다.

> `sg docker -c '...'`는 현재 셸 세션에서 docker 그룹 권한을 임시로 적용하여 명령을 실행하는 방법이다. `newgrp docker`와 유사하지만 비대화형 스크립트에서 사용하기 적합하다.

```bash
multipass exec kind-node -- bash -c "
# VM 자신의 IP 확인
VM_IP=\$(hostname -I | awk '{print \$1}')
echo \"VM IP: \${VM_IP}\"

# kind 설정 파일 생성 — apiServerAddress를 VM IP로 지정
cat <<EOF > /tmp/kind-config.yaml
kind: Cluster
apiVersion: kind.x-k8s.io/v1alpha4
networking:
  apiServerAddress: \"\${VM_IP}\"
  apiServerPort: 6443
EOF

sg docker -c 'kind create cluster --name kind-lab --config /tmp/kind-config.yaml'
"
```

```
VM IP: 192.168.2.3
Creating cluster "kind-lab" ...
 ✓ Ensuring node image (kindest/node:v1.32.2) 🖼
 ✓ Preparing nodes 📦
 ✓ Writing configuration 📜
 ✓ Starting control-plane 🕹️
 ✓ Installing CNI 🔌
 ✓ Installing StorageClass 💾
Set kubectl context to "kind-kind-lab"
You can now use your cluster with:

kubectl cluster-info --context kind-kind-lab
```

클러스터가 생성되었는지 확인한다.

```bash
multipass exec kind-node -- sg docker -c 'kind get clusters'
```

```
kind-lab
```

### kubeconfig 저장 및 server 주소 확인

```bash
multipass exec kind-node -- bash -c "
mkdir -p ~/.kube
sg docker -c 'kind get kubeconfig --name kind-lab' > ~/.kube/config
"
```

kind는 `apiServerAddress`를 VM IP로 지정하여 클러스터를 생성했으므로, kubeconfig의 server 주소가 VM IP로 되어 있는지 확인한다.

```bash
multipass exec kind-node -- grep server /home/ubuntu/.kube/config
```

```
    server: https://192.168.2.3:6443
```

kubeconfig가 정상적으로 저장되었다면, `kubectl`이 클러스터에 접근할 수 있어야 한다. 노드가 `Ready` 상태인지 확인한다.

```bash
multipass exec kind-node -- kubectl get nodes
```

```
NAME                     STATUS   ROLES           AGE    VERSION
kind-lab-control-plane   Ready    control-plane   114s   v1.32.2
```


## k3s 클러스터

k3s는 기본적으로 `127.0.0.1`에 바인딩되므로, `--tls-san`과 `--bind-address`로 VM IP를 지정해야 한다.

### k3s 설치

```bash
multipass exec k3s-node -- bash -c "
set -e

# VM 자신의 IP 확인
VM_IP=\$(hostname -I | awk '{print \$1}')
echo \"VM IP: \${VM_IP}\"

# k3s 설치 — bind-address와 tls-san을 VM IP로 지정
curl -sfL https://get.k3s.io | INSTALL_K3S_EXEC=\"\
  --tls-san \${VM_IP} \
  --bind-address \${VM_IP} \
  --advertise-address \${VM_IP}\" sh -
"
```

`k3s kubectl`은 k3s 바이너리에 내장된 kubectl로, `/etc/rancher/k3s/k3s.yaml`을 자동으로 참조한다. 따라서 별도의 kubeconfig 설정 없이도 바로 노드 확인이 가능하다.

```bash
multipass exec k3s-node -- sudo k3s kubectl get nodes
```

```
NAME       STATUS   ROLES           AGE   VERSION
k3s-node   Ready    control-plane   13s   v1.34.4+k3s1
```

### kubeconfig 저장 및 server 주소 치환

위에서 `k3s kubectl`로 확인한 것은 k3s 내장 경로를 사용한 것이다. 이후 jumpbox에서 접근하려면, server 주소가 `127.0.0.1`이 아닌 VM IP여야 한다. 기본 kubeconfig(`/etc/rancher/k3s/k3s.yaml`)를 복사하면서 주소를 치환한다.

```bash
multipass exec k3s-node -- bash -c "
VM_IP=\$(hostname -I | awk '{print \$1}')

sudo mkdir -p /home/ubuntu/.kube
sudo sed \"s|127.0.0.1|\${VM_IP}|g\" /etc/rancher/k3s/k3s.yaml > /tmp/k3s-config
sudo mv /tmp/k3s-config /home/ubuntu/.kube/config
sudo chown -R ubuntu:ubuntu /home/ubuntu/.kube
sudo chmod 600 /home/ubuntu/.kube/config
"
```

server 주소가 VM IP로 변경되었는지 확인한다. `multipass exec`에서 `~`는 호스트의 홈 디렉토리로 해석되므로, VM 내부의 절대 경로를 사용해야 한다.

```bash
multipass exec k3s-node -- grep server /home/ubuntu/.kube/config
```

```
    server: https://192.168.2.4:6443
```


## kubeadm 클러스터

kubeadm은 가장 저수준 도구로, containerd, kubelet, kubeadm, kubectl을 모두 직접 설치해야 한다. 이 글에서는 최소 절차만 다루며, swap/커널 모듈/sysctl 각 항목의 의미, containerd·kubeadm 설치 상세, init 옵션 등은 [Kubernetes kubeadm 시리즈]({% post_url 2026-01-18-Kubernetes-Kubeadm-00 %})를 참고한다.

### 사전 준비 (swap 비활성화, 커널 모듈, 네트워크 파라미터)

```bash
multipass exec kubeadm-node -- sudo bash -c "
set -e

# swap 비활성화 (kubelet 요구 사항)
swapoff -a
sed -i '/swap/d' /etc/fstab

# 컨테이너 런타임에 필요한 커널 모듈 로드
cat <<EOF | tee /etc/modules-load.d/k8s.conf
overlay
br_netfilter
EOF
modprobe overlay
modprobe br_netfilter

# 브리지 네트워크 트래픽이 iptables를 거치도록 설정, IP 포워딩 활성화
cat <<EOF | tee /etc/sysctl.d/k8s.conf
net.bridge.bridge-nf-call-iptables  = 1
net.bridge.bridge-nf-call-ip6tables = 1
net.ipv4.ip_forward                 = 1
EOF
sysctl --system

# kubeadm preflight 요구: conntrack (없으면 init 단계에서 [ERROR FileExisting-conntrack]로 실패)
apt-get update && apt-get install -y conntrack
"
```

실행 시 `tee`로 찍히는 모듈·sysctl 값과 `sysctl --system` 적용 로그가 나온다. 출력에 `* Applying /etc/sysctl.d/k8s.conf ...`가 있고, 마지막에 `net.bridge.bridge-nf-call-iptables`, `net.bridge.bridge-nf-call-ip6tables`, `net.ipv4.ip_forward = 1`이 적용되어 있으면 된다.

```
overlay
br_netfilter
net.bridge.bridge-nf-call-iptables  = 1
net.bridge.bridge-nf-call-ip6tables = 1
net.ipv4.ip_forward                 = 1
* Applying /usr/lib/sysctl.d/10-apparmor.conf ...
...
* Applying /etc/sysctl.d/k8s.conf ...
...
net.bridge.bridge-nf-call-iptables = 1
net.bridge.bridge-nf-call-ip6tables = 1
net.ipv4.ip_forward = 1
```

결과를 확인한다.

```bash
multipass exec kubeadm-node -- swapon --show        # 출력 없으면 swap 비활성화 성공
multipass exec kubeadm-node -- lsmod | grep br_netfilter
```

```
br_netfilter           32768  0
bridge                405504  1 br_netfilter
```

### containerd 설치

```bash
multipass exec kubeadm-node -- sudo bash -c "
set -e

apt-get update
apt-get install -y ca-certificates curl gnupg

install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | \
  gpg --dearmor -o /etc/apt/keyrings/docker.gpg
chmod a+r /etc/apt/keyrings/docker.gpg

echo \"deb [arch=\$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
  https://download.docker.com/linux/ubuntu \$(lsb_release -cs) stable\" | \
  tee /etc/apt/sources.list.d/docker.list > /dev/null

apt-get update
apt-get install -y containerd.io

containerd config default | tee /etc/containerd/config.toml
sed -i 's/SystemdCgroup = false/SystemdCgroup = true/' /etc/containerd/config.toml
systemctl restart containerd
systemctl enable containerd
"
```

실행 시 Docker 저장소 추가 후 `containerd.io`가 설치되고, `containerd config default`로 기본 설정이 길게 출력된 뒤 `SystemdCgroup = true`로 치환·재시작된다. `systemctl status containerd`에서 `Active: active (running)`인지 확인한다.

```bash
multipass exec kubeadm-node -- sudo systemctl status containerd --no-pager
```

```
● containerd.service - containerd container runtime
     Loaded: loaded (/usr/lib/systemd/system/containerd.service; enabled; preset: enabled)
     Active: active (running) since Mon 2026-02-16 16:00:30 KST; 2s ago
       Docs: https://containerd.io
   Main PID: 2612 (containerd)
      Tasks: 7
     Memory: 14.0M (peak: 17.5M)
        CPU: 45ms
     CGroup: /system.slice/containerd.service
             └─2612 /usr/bin/containerd
```

### kubeadm, kubelet, kubectl 설치

```bash
multipass exec kubeadm-node -- sudo bash -c "
set -e

curl -fsSL https://pkgs.k8s.io/core:/stable:/v1.31/deb/Release.key | \
  gpg --dearmor -o /etc/apt/keyrings/kubernetes-apt-keyring.gpg

echo \"deb [signed-by=/etc/apt/keyrings/kubernetes-apt-keyring.gpg] \
  https://pkgs.k8s.io/core:/stable:/v1.31/deb/ /\" | \
  tee /etc/apt/sources.list.d/kubernetes.list

apt-get update
apt-get install -y kubelet kubeadm kubectl
apt-mark hold kubelet kubeadm kubectl
"
```

실행 시 Kubernetes APT 저장소가 추가되고 `kubelet`, `kubeadm`, `kubectl`과 의존 패키지(cri-tools, kubernetes-cni)가 설치된 뒤 `apt-mark hold`로 고정된다.


```bash
multipass exec kubeadm-node -- kubeadm version
multipass exec kubeadm-node -- kubelet --version
multipass exec kubeadm-node -- kubectl version --client
```

```
kubeadm version: &version.Info{Major:"1", Minor:"31", GitVersion:"v1.31.14", ...}
Kubernetes v1.31.14
Client Version: v1.31.14
Kustomize Version: v5.4.2
```

### kubeadm init

> **버전 안내**: 아래 실습에서는 Kubernetes APT 저장소를 `v1.31`로 두었기 때문에 kubeadm/kubelet/kubectl이 1.31.x로 설치된다. `kubeadm init` 시 `remote version is much newer: v1.35.1; falling back to: stable-1.31` 메시지는 공식 최신(1.35)보다 낮은 1.31을 쓰겠다는 안내일 뿐이며, 1.31로 진행해도 된다. kind(1.32), k3s(1.34)와 버전을 맞추고 싶다면 [kubeadm·kubelet·kubectl 설치](#kubeadm-kubelet-kubectl-설치) 단계의 저장소 URL에서 `v1.31`을 `v1.32` 등으로 바꾼 뒤 재설치하면 된다.

```bash
multipass exec kubeadm-node -- bash -c "
VM_IP=\$(hostname -I | awk '{print \$1}')
echo \"VM IP: \${VM_IP}\"
sudo kubeadm init \
  --apiserver-advertise-address=\${VM_IP} \
  --pod-network-cidr=10.244.0.0/16
"
```

init이 성공하면 마지막에 `Your Kubernetes control-plane has initialized successfully!`가 나온다. **사전 준비**에서 `conntrack`을 설치하지 않았다면 `[ERROR FileExisting-conntrack]: conntrack not found`로 실패하므로, 해당 VM에서 `sudo apt-get install -y conntrack` 후 다시 실행한다.

출력되는 단계(certs, kubeconfig 작성, control-plane static Pod, addons 등)는 [Kubernetes kubeadm 시리즈의 kubeadm init 글]({% post_url 2026-01-18-Kubernetes-Kubeadm-01-1 %})에서 다룬 내용과 동일하다.

```
VM IP: 192.168.2.5
[init] Using Kubernetes version: v1.31.14
[preflight] Running pre-flight checks
[preflight] Pulling images required for setting up a Kubernetes cluster
...
[certs] Generating "ca" certificate and key
[certs] Generating "apiserver" certificate and key
[certs] apiserver serving cert is signed for DNS names [kubeadm-node kubernetes ...] and IPs [10.96.0.1 192.168.2.5]
...
[kubeconfig] Writing "admin.conf" kubeconfig file
[kubeconfig] Writing "kubelet.conf" kubeconfig file
...
[control-plane] Creating static Pod manifest for "kube-apiserver"
...
[addons] Applied essential addon: CoreDNS
[addons] Applied essential addon: kube-proxy

Your Kubernetes control-plane has initialized successfully!

To start using your cluster, you need to run the following as a regular user:
  mkdir -p $HOME/.kube
  sudo cp -i /etc/kubernetes/admin.conf $HOME/.kube/config
  sudo chown $(id -u):$(id -g) $HOME/.kube/config
...
You should now deploy a pod network to the cluster.
Run "kubectl apply -f [podnetwork].yaml" with one of the options listed at:
  https://kubernetes.io/docs/concepts/cluster-administration/addons/

Then you can join any number of worker nodes by running the following on each as root:

kubeadm join 192.168.2.5:6443 --token 8antl4.h0xpx27mb53ut65e \
        --discovery-token-ca-cert-hash sha256:ac2c3374c8a9e26b3ea5a176dca2642abe1eaf089a3eb91c19dd0bb0aef8384e 
```

### CNI (flannel) 설치 및 kubeconfig 설정

```bash
multipass exec kubeadm-node -- sudo bash -c "
# CNI 설치
export KUBECONFIG=/etc/kubernetes/admin.conf
kubectl apply -f https://github.com/flannel-io/flannel/releases/latest/download/kube-flannel.yml

# ubuntu 사용자 kubeconfig
mkdir -p /home/ubuntu/.kube
cp /etc/kubernetes/admin.conf /home/ubuntu/.kube/config
chown -R ubuntu:ubuntu /home/ubuntu/.kube
"
```

```
namespace/kube-flannel created
serviceaccount/flannel created
clusterrole.rbac.authorization.k8s.io/flannel created
clusterrolebinding.rbac.authorization.k8s.io/flannel created
configmap/kube-flannel-cfg created
daemonset.apps/kube-flannel-ds created
```

클러스터에 등록된 노드와 상태(Ready 여부)를 확인한다.

```bash
multipass exec kubeadm-node -- kubectl get nodes
```

CNI(flannel)가 올라와야 노드가 `Ready`가 된다. Pod 네트워크를 제공하는 CNI가 없으면 kubelet이 노드를 Ready로 보고하지 않으므로, flannel 적용 직후에는 `NotReady`였다가 DaemonSet Pod가 기동되면 `Ready`로 바뀐다.

```
NAME           STATUS     ROLES           AGE    VERSION
kubeadm-node   NotReady   control-plane   113s   v1.31.14
```

잠시 후 다시 확인하면:

```
NAME           STATUS   ROLES           AGE   VERSION
kubeadm-node   Ready    control-plane   2m    v1.31.14
```



<br>

# jumpbox 설정

## kubectl 및 도구 설치

```bash
multipass exec jumpbox -- bash -c "
set -e

# kubectl 설치
ARCH=\$(dpkg --print-architecture)
sudo curl -LO \"https://dl.k8s.io/release/\$(curl -Ls https://dl.k8s.io/release/stable.txt)/bin/linux/\${ARCH}/kubectl\"
sudo install kubectl /usr/local/bin/

# kubectx/kubens (선택)
sudo apt-get update && sudo apt-get install -y fzf git
sudo git clone https://github.com/ahmetb/kubectx /opt/kubectx
sudo ln -s /opt/kubectx/kubectx /usr/local/bin/kubectx
sudo ln -s /opt/kubectx/kubens /usr/local/bin/kubens

mkdir -p ~/.kube
"
```


## kubeconfig 파일 모으기

각 VM의 kubeconfig를 호스트로 가져온 뒤, jumpbox로 전달한다.

```bash
# 호스트에서 실행: 각 VM에서 kubeconfig를 호스트로 가져오기
multipass transfer kind-node:/home/ubuntu/.kube/config /tmp/config-kind
multipass transfer k3s-node:/home/ubuntu/.kube/config /tmp/config-k3s
multipass transfer kubeadm-node:/home/ubuntu/.kube/config /tmp/config-kubeadm

# 전달된 파일에 server 주소가 각 VM IP로 들어가 있는지 확인 (kind 192.168.2.3, k3s 192.168.2.4, kubeadm 192.168.2.5)
grep server /tmp/config-kind /tmp/config-k3s /tmp/config-kubeadm

# 호스트에서 jumpbox로 전달
multipass transfer /tmp/config-kind jumpbox:/home/ubuntu/.kube/config-kind
multipass transfer /tmp/config-k3s jumpbox:/home/ubuntu/.kube/config-k3s
multipass transfer /tmp/config-kubeadm jumpbox:/home/ubuntu/.kube/config-kubeadm
```

```
/tmp/config-kind:    server: https://192.168.2.3:6443
/tmp/config-k3s:    server: https://192.168.2.4:6443
/tmp/config-kubeadm:    server: https://192.168.2.5:6443
```

> `multipass transfer`는 VM과 호스트 간 파일 복사 명령이다. VM 간 직접 전송은 지원하지 않으므로, 호스트를 경유한다.


## KUBECONFIG 환경 변수 설정

```bash
multipass exec jumpbox -- bash -c "
cat <<'EOF' >> ~/.bashrc
export KUBECONFIG=~/.kube/config-kind:~/.kube/config-k3s:~/.kube/config-kubeadm
EOF
"
```


<br>

# KUBECONFIG 병합 및 컨텍스트 전환

이제 jumpbox에 접속하여 실습을 진행한다.

```bash
multipass shell jumpbox
```

## 환경 변수 확인

```bash
# 셸을 새로 열었으므로 .bashrc가 적용됨
echo $KUBECONFIG
```

```
/home/ubuntu/.kube/config-kind:/home/ubuntu/.kube/config-k3s:/home/ubuntu/.kube/config-kubeadm
```

## 컨텍스트 목록 확인

컨텍스트 목록을 `kubectl config get-contexts`로 확인한다. 

```bash
kubectl config get-contexts
```

```
CURRENT   NAME                          CLUSTER         AUTHINFO           NAMESPACE
          default                       default         default            
*         kind-kind-lab                 kind-kind-lab   kind-kind-lab      
          kubernetes-admin@kubernetes   kubernetes      kubernetes-admin 
```

> k3s의 기본 컨텍스트 이름이 `default`이므로, 다른 클러스터와 헷갈릴 수 있다. `kubectl config rename-context default k3s-lab`으로 이름을 변경하면 관리하기 편하다.

```bash
kubectl config rename-context default k3s-lab
kubectl config get-contexts
```

```
Context "default" renamed to "k3s-lab".

CURRENT   NAME                          CLUSTER         AUTHINFO           NAMESPACE
          k3s-lab                       default         default            
*         kind-kind-lab                 kind-kind-lab   kind-kind-lab      
          kubernetes-admin@kubernetes   kubernetes      kubernetes-admin 
```

## 컨텍스트 전환 및 노드 확인

### use-context 전후 파일 변경 확인

`kubectl config use-context`는 kubeconfig의 `current-context`를 바꾼다고 했다([kubectl config use-context]({% post_url 2026-02-16-Kubernetes-Kubeconfig-01 %}#kubectl-config-use-context)). 지금처럼 **KUBECONFIG에 여러 파일이 있으면 쓰기는 목록의 첫 번째 파일**에만 일어난다. 

현재 jumpbox의 `KUBECONFIG=~/.kube/config-kind:~/.kube/config-k3s:~/.kube/config-kubeadm`이므로, use-context를 실행하면 첫 번째 파일인 `config-kind`에만 `current-context`가 기록된다. config-k3s, config-kubeadm은 수정되지 않으며, 각 파일이 원래 갖고 있던 current-context 값은 그대로다.

실제로 아래와 같이 use-context의 동작을 확인해 볼 수 있다.

```bash
cd ~/.kube
grep current-context ~/.kube/config-kind ~/.kube/config-k3s ~/.kube/config-kubeadm
kubectl config use-context kind-kind-lab
grep current-context ~/.kube/config-kind ~/.kube/config-k3s ~/.kube/config-kubeadm
kubectl config use-context k3s-lab
grep current-context ~/.kube/config-kind ~/.kube/config-k3s ~/.kube/config-kubeadm
```

**다른** 컨텍스트(예: k3s-lab)로 바꾸면 config-kind의 current-context만 그 값으로 바뀌지만, 이미 config-kind가 kind-kind-lab이면 use-context kind-kind-lab 후에는 내용이 달라지지 않음을 확인할 수 있다.

```bash
# 최초 상태
config-k3s:current-context: default
config-kind:current-context: kind-kind-lab
config-kubeadm:current-context: kubernetes-admin@kubernetes

# kubectl config use-context kind-kind-lab으로 kind-kind-lab으로 변경한 후
/home/ubuntu/.kube/config-k3s:current-context: default
/home/ubuntu/.kube/config-kind:current-context: kind-kind-lab # 변경 없음
/home/ubuntu/.kube/config-kubeadm:current-context: kubernetes-admin@kubernetes

# kubectl config use-context k3s-lab으로 k3s-lab으로 변경한 후
Switched to context "k3s-lab".

# config-kind의 current-context가 변경되어 있음
config-k3s:current-context: default
config-kind:current-context: k3s-lab # 변경됨
config-kubeadm:current-context: kubernetes-admin@kubernetes
```

### kind 클러스터

```bash
kubectl config use-context kind-kind-lab
kubectl get nodes
```

```
NAME                     STATUS   ROLES           AGE   VERSION
kind-lab-control-plane   Ready    control-plane   35m   v1.32.2
```


### k3s 클러스터

```bash
kubectl config use-context k3s-lab   # rename-context로 이름 바꿨다면 k3s-lab
kubectl get nodes
```

```
Switched to context "k3s-lab".

NAME       STATUS   ROLES           AGE   VERSION
k3s-node   Ready    control-plane   37m   v1.34.4+k3s1
```


### kubeadm 클러스터

```bash
kubectl config use-context kubernetes-admin@kubernetes
kubectl get nodes
```

```
Switched to context "kubernetes-admin@kubernetes".

NAME           STATUS   ROLES           AGE   VERSION
kubeadm-node   Ready    control-plane   20m   v1.31.14
```


## 현재 컨텍스트만 확인

```bash
# 현재 활성 컨텍스트 이름 확인
kubectl config current-context

# 현재 컨텍스트의 설정만 확인 (--minify)
kubectl config view --minify
```

현재 컨텍스트가 `kubernetes-admin@kubernetes`인 상태에서 실행한 결과를 확인해 보자.

```
$ kubectl config current-context
kubernetes-admin@kubernetes

$ kubectl config view --minify
apiVersion: v1
clusters:
- cluster:
    certificate-authority-data: DATA+OMITTED
    server: https://192.168.2.5:6443
  name: kubernetes
contexts:
- context:
    cluster: kubernetes
    user: kubernetes-admin
  name: kubernetes-admin@kubernetes
current-context: kubernetes-admin@kubernetes
kind: Config
users:
- name: kubernetes-admin
  user:
    client-certificate-data: DATA+OMITTED
    client-key-data: DATA+OMITTED
```

## 병합된 전체 설정 확인

```bash
# 병합된 전체 kubeconfig 확인
kubectl config view

# 하나의 파일로 합치기 (선택)
kubectl config view --flatten > ~/.kube/config-merged
```

```
$ kubectl config view
apiVersion: v1
clusters:
- cluster:
    certificate-authority-data: DATA+OMITTED
    server: https://192.168.2.4:6443
  name: default
- cluster:
    certificate-authority-data: DATA+OMITTED
    server: https://192.168.2.3:6443
  name: kind-kind-lab
- cluster:
    certificate-authority-data: DATA+OMITTED
    server: https://192.168.2.5:6443
  name: kubernetes
contexts:
- context:
    cluster: default
    user: default
  name: k3s-lab
- context:
    cluster: kind-kind-lab
    user: kind-kind-lab
  name: kind-kind-lab
- context:
    cluster: kubernetes
    user: kubernetes-admin
  name: kubernetes-admin@kubernetes
current-context: kubernetes-admin@kubernetes
kind: Config
users:
- name: default
  user:
    client-certificate-data: DATA+OMITTED
    client-key-data: DATA+OMITTED
- name: kind-kind-lab
  user:
    client-certificate-data: DATA+OMITTED
    client-key-data: DATA+OMITTED
- name: kubernetes-admin
  user:
    client-certificate-data: DATA+OMITTED
    client-key-data: DATA+OMITTED

$ kubectl config view --flatten > ~/.kube/config-merged
$ ls ~/.kube
cache  config-k3s  config-kind  config-kubeadm  config-merged
```

## --kubeconfig 플래그로 특정 파일만 사용

```bash
# 특정 kubeconfig 파일만 사용 (경로에 ~ 사용 시 kubectl이 확장하지 않을 수 있으므로 $HOME 권장)
kubectl --kubeconfig=$HOME/.kube/config-kind get nodes
```

`--kubeconfig=~/.kube/config-kind`처럼 `~`를 쓰면 kubectl이 경로를 확장하지 않아 `stat ~/.kube/config-kind: no such file or directory`가 날 수 있다. `$HOME/.kube/config-kind` 또는 절대 경로를 사용한다.

```
$ kubectl --kubeconfig=$HOME/.kube/config-kind get nodes
NAME                     STATUS   ROLES           AGE   VERSION
kind-lab-control-plane   Ready    control-plane   35m   v1.32.2
```

> **주의:** kubeconfig 파일의 current-context가 해당 파일에 존재하지 않는 context인 경우
>
> `--kubeconfig`로 한 파일만 줄 때, 그 파일에 적힌 `current-context`가 **다른 파일에만 있는 컨텍스트**(예: 마지막에 `use-context kubernetes-admin@kubernetes`를 해서 config-kind에 `current-context: kubernetes-admin@kubernetes`만 들어간 경우)면 `context was not found for specified context: kubernetes-admin@kubernetes` 에러가 난다. 대처 방법은 두 가지다.
> 1. **`--context` 지정**: 해당 파일에 있는 컨텍스트를 명시한다.
> 2. **먼저 `kubectl config use-context`로 전환**: `kubectl config use-context kind-kind-lab`을 실행하면 config-kind에 `current-context: kind-kind-lab`이 기록되므로, 이후에는 `--kubeconfig=$HOME/.kube/config-kind`만 써도 된다.
> 
> ```bash
> # 방법 1: --context로 해당 파일의 컨텍스트 지정
> kubectl --kubeconfig=$HOME/.kube/config-kind --context=kind-kind-lab get nodes
> 
> # 방법 2: use-context로 먼저 전환한 뒤 --kubeconfig만 사용
> kubectl config use-context kind-kind-lab
> kubectl --kubeconfig=$HOME/.kube/config-kind get nodes
> ```

## 클러스터별 kubeconfig 구조 비교

```bash
# 각 클러스터의 kubeconfig 구조를 비교 (경로는 $HOME 사용 권장)
kubectl config view --kubeconfig=$HOME/.kube/config-kind
kubectl config view --kubeconfig=$HOME/.kube/config-k3s
kubectl config view --kubeconfig=$HOME/.kube/config-kubeadm
```

<details markdown="1">
<summary>kind</summary>

```
apiVersion: v1
clusters:
- cluster:
    certificate-authority-data: DATA+OMITTED
    server: https://192.168.2.3:6443
  name: kind-kind-lab
contexts:
- context:
    cluster: kind-kind-lab
    user: kind-kind-lab
  name: kind-kind-lab
current-context: kind-kind-lab
kind: Config
users:
- name: kind-kind-lab
  user:
    client-certificate-data: DATA+OMITTED
    client-key-data: DATA+OMITTED
```
</details>

<details markdown="1">
<summary>k3s (rename-context로 context 이름만 k3s-lab으로 바꾼 상태)</summary>

```
clusters: name "default", server https://192.168.2.4:6443
contexts: name "k3s-lab", cluster default, user default
current-context: default
users: name "default", client cert/key
```
</details>

<details markdown="1">
<summary>kubeadm</summary>

```
clusters: name "kubernetes", server https://192.168.2.5:6443
contexts: name "kubernetes-admin@kubernetes", cluster kubernetes, user kubernetes-admin
current-context: kubernetes-admin@kubernetes
users: name "kubernetes-admin", client cert/key
```
</details>


- 세 파일 모두 `clusters` / `contexts` / `users` / `current-context` 구조는 동일하다.
- 배포 도구별로 cluster·context·user 이름과 server 주소(VM IP)만 다르다.
  - kind: cluster/context/user가 모두 `kind-kind-lab`으로 통일.
  - k3s: cluster 이름 `default`, context는 rename으로 `k3s-lab`.
  - kubeadm: `kubernetes` / `kubernetes-admin@kubernetes` 식의 이름.
- `--kubeconfig=~/.kube/...`처럼 `~`를 쓰면 kubectl이 확장하지 않아 `clusters: null`, `contexts: null`이 나오므로 `$HOME`을 사용한다.


<br>

# 실습 정리

이 실습을 통해 익힌 것들을 정리하면 다음과 같다.

| 항목 | 내용 |
| --- | --- |
| `KUBECONFIG` 환경 변수 병합 | 여러 파일을 콜론으로 구분하여 자동 병합 |
| `kubectl config get-contexts` | 병합된 모든 컨텍스트 목록 조회 |
| `kubectl config use-context` | 컨텍스트 전환 (파일 직접 수정) |
| `kubectl config current-context` | 현재 활성 컨텍스트 확인 |
| `kubectl config view --minify` | 현재 컨텍스트의 설정만 확인 |
| `kubectl config rename-context` | 컨텍스트 이름 변경 |
| `--kubeconfig` 플래그 | 특정 파일만 지정하여 사용 |
| 클러스터별 kubeconfig 구조 차이 | kind vs k3s vs kubeadm 배포 방식에 따른 차이 비교 |


<br>

# 실습 환경 정리

실습이 끝나면 VM을 정리한다.

```bash
# VM 중지
multipass stop jumpbox kind-node k3s-node kubeadm-node

# VM 삭제
multipass delete jumpbox kind-node k3s-node kubeadm-node
multipass purge
```


<br>

# 맺으며

이번 실습으로 `KUBECONFIG` 환경 변수 병합, 컨텍스트 전환, 클러스터별 kubeconfig 구조 차이를 직접 다뤄 봤다. 이걸 실무에서 어떻게 쓰면 좋을까?

**개발/스테이징/프로덕션**처럼 환경별로 클러스터가 나뉘어 있으면, 한 터미널에서 `kubectl config use-context`만 바꿔 가며 같은 kubectl로 각 클러스터에 접근할 수 있다. **CI/CD 파이프라인**에서는 배포 대상 클러스터에 맞는 kubeconfig만 주입하거나, `KUBECONFIG`에 여러 파일을 넣어 두고 `--context`로 컨텍스트를 고정해 사용하는 식으로 활용할 수 있다. **점프박스나 베스천**에서 여러 클러스터를 관리할 때도, 지금처럼 kubeconfig를 병합해 두고 컨텍스트만 전환하면 한 머신에서 여러 클러스터를 안전하게 다룰 수 있다. 실습에서 썼던 “jumpbox에서 여러 클러스터 접근” 구조가 그대로 실무 패턴과 맞닿아 있다.

kubeconfig의 개념과 구조가 궁금하다면 [이전 글]({% post_url 2026-02-16-Kubernetes-Kubeconfig-01 %})을, API Reference를 더 보고 싶다면 [kubeconfig API Reference 톺아보기]({% post_url 2026-02-16-Kubernetes-Kubeconfig-03 %})를 참고하면 된다.
