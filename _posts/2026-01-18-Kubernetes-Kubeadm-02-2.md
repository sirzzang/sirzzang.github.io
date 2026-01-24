---
title:  "[Kubernetes] Cluster: Kubeadm을 이용해 클러스터 구성하기 - 2.2. kubeadm join 실행"
excerpt: "kubeadm join을 실행하여 워커 노드를 클러스터에 추가해 보자."
categories:
  - Kubernetes
toc: true
header:
  teaser: /assets/images/blog-Dev.jpg
tags:
  - Kubernetes
  - On-Premise-K8s-Hands-On-Study
  - On-Premise-K8s-Hands-On-Study-Week-3

---

*[서종호(가시다)](https://www.linkedin.com/in/gasida99/)님의 On-Premise K8s Hands-on Study 3주차 학습 내용을 기반으로 합니다.*

<br>

# TL;DR

이번 글의 목표는 **kubeadm join으로 워커 노드를 클러스터에 추가**하는 것이다.

- **워커 노드 사전 설정**: 컨트롤 플레인과 동일한 사전 설정 적용
- **kubeadm join**: JoinConfiguration을 사용하여 클러스터에 합류
- **결과 확인**: 노드 상태, Pod CIDR, 라우팅 테이블 확인

<br>

# 들어가며

[이전 글]({% post_url 2026-01-18-Kubernetes-Kubeadm-02-1 %})에서 `kubeadm join`의 동작 원리를 살펴보았다. 이번 글에서는 실제로 워커 노드(k8s-w1, k8s-w2)를 클러스터에 추가한다.

워커 노드 설정은 컨트롤 플레인과 대부분 동일하지만, `kubeadm init` 대신 `kubeadm join`을 실행한다는 점이 다르다.

<br>

# 워커 노드 사전 설정

워커 노드(k8s-w1, k8s-w2) 모두에서 [1-2. 사전 설정 및 구성 요소 설치]({% post_url 2026-01-18-Kubernetes-Kubeadm-01-2 %})와 동일한 설정을 수행한다.

<details markdown="1">
<summary>사전 설정 및 구성 요소 설치 명령어</summary>

```bash
# root 권한 전환
echo "sudo su -" >> /home/vagrant/.bashrc
sudo su -

# Time, NTP 설정
timedatectl set-local-rtc 0
timedatectl set-timezone Asia/Seoul
timedatectl set-ntp true

# SELinux 설정 (Permissive)
setenforce 0
sed -i 's/^SELINUX=enforcing/SELINUX=permissive/' /etc/selinux/config

# 방화벽 비활성화
systemctl disable --now firewalld

# Swap 비활성화
swapoff -a
sed -i '/swap/d' /etc/fstab

# 커널 모듈 로드
modprobe overlay
modprobe br_netfilter
cat <<EOF | tee /etc/modules-load.d/k8s.conf
overlay
br_netfilter
EOF

# 커널 파라미터 설정
cat <<EOF | tee /etc/sysctl.d/k8s.conf
net.bridge.bridge-nf-call-iptables  = 1
net.bridge.bridge-nf-call-ip6tables = 1
net.ipv4.ip_forward                 = 1
EOF
sysctl --system >/dev/null 2>&1

# hosts 설정
sed -i '/^127\.0\.\(1\|2\)\.1/d' /etc/hosts
cat << EOF >> /etc/hosts
192.168.10.100 k8s-ctr
192.168.10.101 k8s-w1
192.168.10.102 k8s-w2
EOF

# containerd 설치
dnf config-manager --add-repo https://download.docker.com/linux/centos/docker-ce.repo
dnf install -y containerd.io-2.1.5-1.el10
containerd config default | tee /etc/containerd/config.toml
sed -i 's/SystemdCgroup = false/SystemdCgroup = true/g' /etc/containerd/config.toml
systemctl daemon-reload
systemctl enable --now containerd

# kubeadm, kubelet, kubectl 설치
cat <<EOF | tee /etc/yum.repos.d/kubernetes.repo
[kubernetes]
name=Kubernetes
baseurl=https://pkgs.k8s.io/core:/stable:/v1.32/rpm/
enabled=1
gpgcheck=1
gpgkey=https://pkgs.k8s.io/core:/stable:/v1.32/rpm/repodata/repomd.xml.key
exclude=kubelet kubeadm kubectl cri-tools kubernetes-cni
EOF
dnf install -y kubelet kubeadm kubectl --disableexcludes=kubernetes
systemctl enable --now kubelet

# crictl 설정
cat << EOF > /etc/crictl.yaml
runtime-endpoint: unix:///run/containerd/containerd.sock
image-endpoint: unix:///run/containerd/containerd.sock
EOF
```

</details>

<br>

# kubeadm join 실행

## 기본 환경 정보 저장

join 전후 비교를 위해 현재 상태를 저장한다.

```bash
# 기본 환경 정보 출력 저장
crictl images | tee -a crictl_images-1.txt
crictl ps -a | tee -a crictl_ps-1.txt
cat /etc/sysconfig/kubelet | tee -a kubelet_config-1.txt
tree /etc/kubernetes  | tee -a etc_kubernetes-1.txt
tree /var/lib/kubelet | tee -a var_lib_kubelet-1.txt
tree /run/containerd/ -L 3 | tee -a run_containerd-1.txt
pstree -alnp | tee -a pstree-1.txt
systemd-cgls --no-pager | tee -a systemd-cgls-1.txt
lsns | tee -a lsns-1.txt
ip addr | tee -a ip_addr-1.txt 
ss -tnlp | tee -a ss-1.txt
df -hT | tee -a df-1.txt
findmnt | tee -a findmnt-1.txt
sysctl -a | tee -a sysctl-1.txt
```

<br>

## kubeadm join 설정 방식

`kubeadm join`도 `kubeadm init`과 마찬가지로 명령줄 옵션과 설정 파일 두 가지 방식을 지원한다.

### 명령줄 옵션 방식

`kubeadm init` 완료 시 출력되는 명령어를 그대로 사용하는 방식이다:

```bash
kubeadm join 192.168.10.100:6443 --token 123456.1234567890123456 \
  --discovery-token-ca-cert-hash sha256:xxx...
```

토큰과 CA 해시는 컨트롤 플레인에서 조회할 수 있다:

```bash
# 토큰 확인
kubeadm token list

# CA 해시 확인
openssl x509 -pubkey -in /etc/kubernetes/pki/ca.crt | \
  openssl rsa -pubin -outform der 2>/dev/null | \
  openssl dgst -sha256 -hex | sed 's/^.* //'
```

### 설정 파일 방식

명령줄 옵션 대신 YAML 설정 파일(`JoinConfiguration`)을 사용하면 버전 관리와 재현성 측면에서 더 좋다. 이번 실습에서도 설정 파일 방식을 사용한다.

```bash
# 현재 노드의 IP 주소 확인
NODEIP=$(ip -4 addr show enp0s9 | grep -oP '(?<=inet\s)\d+(\.\d+){3}')
echo $NODEIP

# kubeadm JoinConfiguration 파일 작성
cat << EOF > kubeadm-join.yaml
apiVersion: kubeadm.k8s.io/v1beta4
kind: JoinConfiguration
discovery:
  bootstrapToken:
    token: "123456.1234567890123456"       # kubeadm init에서 설정한 토큰
    apiServerEndpoint: "192.168.10.100:6443"  # 컨트롤 플레인 API Server 주소
    unsafeSkipCAVerification: true         # CA 해시 검증 건너뛰기 (실습용)
nodeRegistration:
  criSocket: "unix:///run/containerd/containerd.sock"
  kubeletExtraArgs:
    - name: node-ip
      value: "$NODEIP"                     # 미설정 시 10.0.2.15로 매핑될 수 있음 (실습 환경 특수성)
EOF
cat kubeadm-join.yaml
```

| 항목 | 설명 |
| --- | --- |
| `discovery.bootstrapToken.token` | `kubeadm init`에서 생성된 Bootstrap Token |
| `discovery.bootstrapToken.apiServerEndpoint` | 컨트롤 플레인 API Server 주소 |
| `unsafeSkipCAVerification` | CA 해시 검증 건너뛰기 (실습용, 프로덕션에서는 `caCertHashes` 사용) |
| `nodeRegistration.criSocket` | CRI 소켓 경로 (CRI-O 등 다른 런타임 사용 시 변경) |
| `nodeRegistration.kubeletExtraArgs.node-ip` | kubelet에 전달할 노드 IP (Vagrant 환경에서 중요) |

주요 설정 항목 값에서 주의해서 봐야 하는 것은 다음과 같다:
- **token**: [kubeadm init 시 설정한 토큰]({% post_url 2026-01-18-Kubernetes-Kubeadm-01-3 %}#설정-파일-방식)과 동일해야 한다. 이번 실습에서는 `123456.1234567890123456`으로 고정했다.
- **apiServerEndpoint**: 컨트롤 플레인의 API Server 주소다. HA 구성에서는 로드밸런서 주소를 지정한다.
- **unsafeSkipCAVerification**: `true`로 설정하면 CA 인증서 해시 검증을 건너뛴다. 실습 편의를 위해 사용하지만, **프로덕션에서는 `caCertHashes`를 명시**하여 중간자 공격을 방지해야 한다.
- **node-ip**: [init에서 설명한 것처럼]({% post_url 2026-01-18-Kubernetes-Kubeadm-01-3 %}#설정-파일-방식), Vagrant처럼 여러 네트워크 인터페이스가 있는 환경에서는 반드시 명시해야 한다. 미설정 시 NAT 인터페이스 IP(10.0.2.15)가 사용되어 노드 간 통신에 문제가 발생할 수 있다.
- **criSocket**: containerd 외 CRI-O 등 다른 런타임 사용 시 해당 소켓 경로로 변경해야 한다.

<br>

## 컨테이너 이미지 사전 다운로드 (선택)

워커 노드에서 **실제로 사용하는** 이미지는 컨트롤 플레인보다 적다. 주로 `kube-proxy`와 `pause` 이미지만 필요하다.

```bash
# 필요한 이미지만 다운로드
crictl pull registry.k8s.io/kube-proxy:v1.32.11
crictl pull registry.k8s.io/pause:3.10
```

또는 `kubeadm config images pull`을 사용할 수도 있다:

```bash
# kubeadm으로 전체 이미지 다운로드 (워커 노드에서도 실행 가능)
kubeadm config images pull
```

> **참고**: `kubeadm config images pull`은 노드 역할을 구분하지 않고 **모든 이미지**(apiserver, controller-manager, scheduler, etcd 포함)를 pull한다. 워커 노드에서는 `kube-proxy`와 `pause`만 실제로 사용되므로, 디스크 공간이 제한적이라면 필요한 이미지만 선택적으로 pull하는 것이 좋다.

이번 실습에서는 **이미지 사전 다운로드 없이 진행**한다. 컨트롤 플레인 init과 달리 워커 노드는 필요한 이미지가 적고(`kube-proxy`, `pause` 2개), 용량도 작아서 join 과정에서 이미지를 pull해도 시간이 크게 늘어나지 않는다.

<br>

## 실행 단계

### (선택) dry-run으로 사전 확인

`--dry-run` 옵션을 사용하면 실제로 join하지 않고 **어떤 작업이 수행될지 미리 확인**할 수 있다.

```bash
kubeadm join --config="kubeadm-join.yaml" --dry-run
```

dry-run 출력은 `[dryrun] Would perform action <ACTION> on resource` 형식으로 **실제로 수행될 API 호출**과 **생성될 파일**을 보여준다:

```
W0125 02:14:16.405445 constants.go:614] Using dry-run directory /etc/kubernetes/tmp/kubeadm-join-dryrun*
[preflight] Running pre-flight checks
[dryrun] Would perform action GET on resource "configmaps" in API group "core/v1"
[dryrun] Resource name "cluster-info", namespace "kube-public"
[dryrun] Attached object:
apiVersion: v1
data:
  kubeconfig: |
    apiVersion: v1
    clusters:
    - cluster:
        certificate-authority-data: LS0tLS1CRUdJTi...  # CA 인증서 (base64)
        server: https://192.168.10.100:6443
...

[preflight] Reading configuration from the "kubeadm-config" ConfigMap in namespace "kube-system"...
[dryrun] Would perform action GET on resource "configmaps" in API group "core/v1"
[dryrun] Resource name "kubeadm-config", namespace "kube-system"
[dryrun] Resource name "kube-proxy", namespace "kube-system"
[dryrun] Resource name "kubelet-config", namespace "kube-system"
...

[kubelet-start] Would stop the kubelet
[kubelet-start] Writing kubelet configuration to file "/etc/kubernetes/tmp/kubeadm-join-dryrun*/config.yaml"
[kubelet-start] Writing kubelet environment file with flags to file "/etc/kubernetes/tmp/kubeadm-join-dryrun*/kubeadm-flags.env"
[kubelet-start] Would start the kubelet
[dryrun] Wrote certificates and kubeconfig files to the "/etc/kubernetes/tmp/kubeadm-join-dryrun*" directory
[dryrun] Would write file "/var/lib/kubelet/config.yaml" with content:
apiVersion: kubelet.config.k8s.io/v1beta1
cgroupDriver: systemd
clusterDNS:
- 10.96.0.10
rotateCertificates: true
...

This node has joined the cluster:
* Certificate signing request was sent to apiserver and a response was received.
* The Kubelet was informed of the new secure connection details.

Run 'kubectl get nodes' on the control-plane to see this node join the cluster.
```

dry-run 출력에서 주요하게 확인할 부분:

| ConfigMap | 설명 |
| --- | --- |
| `cluster-info` | 클러스터 CA 인증서와 API Server 주소 (discovery에 사용) |
| `kubeadm-config` | 클러스터 설정 (`podSubnet`, `serviceSubnet` 등) |
| `kube-proxy` | kube-proxy 설정 |
| `kubelet-config` | kubelet 설정 (`cgroupDriver`, `clusterDNS`, `rotateCertificates` 등) |

<details markdown="1">
<summary>dry-run 전체 출력</summary>

```
W0125 02:14:16.405445 constants.go:614] Using dry-run directory /etc/kubernetes/tmp/kubeadm-join-dryrun803182261
[preflight] Running pre-flight checks
[dryrun] Would perform action GET on resource "configmaps" in API group "core/v1"
[dryrun] Resource name "cluster-info", namespace "kube-public"
[dryrun] Attached object:
apiVersion: v1
data:
  jws-kubeconfig-abcdef: eyJhbGciOiJIUzI1NiIsImtpZCI6ImFiY2RlZiJ9...
  kubeconfig: |
    apiVersion: v1
    clusters:
    - cluster:
        certificate-authority-data: LS0tLS1CRUdJTi...
        server: https://192.168.10.100:6443
      name: ""
    kind: Config
kind: ConfigMap
metadata:
  name: cluster-info
  namespace: kube-public

[preflight] Reading configuration from the "kubeadm-config" ConfigMap in namespace "kube-system"...
[dryrun] Would perform action GET on resource "configmaps" in API group "core/v1"
[dryrun] Resource name "kubeadm-config", namespace "kube-system"
[dryrun] Attached object:
apiVersion: v1
data:
  ClusterConfiguration: |
    apiVersion: kubeadm.k8s.io/v1beta4
    certificatesDir: /etc/kubernetes/pki
    clusterName: kubernetes
    controlPlaneEndpoint: 192.168.10.100:6443
    etcd:
      local:
        dataDir: /var/lib/etcd
    imageRepository: registry.k8s.io
    kubernetesVersion: 1.32.11
    networking:
      dnsDomain: cluster.local
      podSubnet: 10.244.0.0/16
      serviceSubnet: 10.96.0.0/16
kind: ConfigMap
metadata:
  name: kubeadm-config
  namespace: kube-system

[dryrun] Resource name "kube-proxy", namespace "kube-system"
[dryrun] Attached object:
apiVersion: v1
data:
  config.conf: |
    apiVersion: kubeproxy.config.k8s.io/v1alpha1
    bindAddress: 0.0.0.0
    clientConnection:
      kubeconfig: /var/lib/kube-proxy/kubeconfig.conf
    clusterCIDR: 10.244.0.0/16
    kind: KubeProxyConfiguration
kind: ConfigMap
metadata:
  name: kube-proxy
  namespace: kube-system

[dryrun] Resource name "kubelet-config", namespace "kube-system"
[dryrun] Attached object:
apiVersion: v1
data:
  kubelet: |
    apiVersion: kubelet.config.k8s.io/v1beta1
    authentication:
      anonymous:
        enabled: false
      webhook:
        enabled: true
      x509:
        clientCAFile: /etc/kubernetes/pki/ca.crt
    authorization:
      mode: Webhook
    cgroupDriver: systemd
    clusterDNS:
    - 10.96.0.10
    clusterDomain: cluster.local
    rotateCertificates: true
    staticPodPath: /etc/kubernetes/manifests
kind: ConfigMap
metadata:
  name: kubelet-config
  namespace: kube-system

[dryrun] Would perform action GET on resource "nodes" in API group "core/v1"
[dryrun] Resource name "k8s-w1", namespace ""
[kubelet-start] Would stop the kubelet
[kubelet-start] Writing kubelet configuration to file "/etc/kubernetes/tmp/kubeadm-join-dryrun803182261/config.yaml"
[kubelet-start] Writing kubelet environment file with flags to file "/etc/kubernetes/tmp/kubeadm-join-dryrun803182261/kubeadm-flags.env"
[kubelet-start] Would start the kubelet
[dryrun] Wrote certificates and kubeconfig files to the "/etc/kubernetes/tmp/kubeadm-join-dryrun803182261" directory
[dryrun] Would write file "/var/lib/kubelet/config.yaml" with content:
apiVersion: kubelet.config.k8s.io/v1beta1
authentication:
  anonymous:
    enabled: false
  webhook:
    enabled: true
  x509:
    clientCAFile: /etc/kubernetes/pki/ca.crt
authorization:
  mode: Webhook
cgroupDriver: systemd
clusterDNS:
- 10.96.0.10
clusterDomain: cluster.local
rotateCertificates: true
staticPodPath: /etc/kubernetes/manifests
...

[dryrun] Would write file "/var/lib/kubelet/kubeadm-flags.env" with content:
KUBELET_KUBEADM_ARGS="--container-runtime-endpoint=unix:///run/containerd/containerd.sock --node-ip=192.168.10.101 --pod-infra-container-image=registry.k8s.io/pause:3.10"

This node has joined the cluster:
* Certificate signing request was sent to apiserver and a response was received.
* The Kubelet was informed of the new secure connection details.

Run 'kubectl get nodes' on the control-plane to see this node join the cluster.
```

</details>

<br>

dry-run 후 `/etc/kubernetes` 디렉토리를 확인하면, **실제 파일은 생성되지 않고 임시 디렉토리에만 생성**된 것을 알 수 있다:

```bash
tree /etc/kubernetes
# /etc/kubernetes
# ├── manifests                           <- 비어있음 (dry-run이므로)
# └── tmp
#     └── kubeadm-join-dryrun*
#         ├── ca.crt                       <- 클러스터 CA 인증서
#         ├── config.yaml                  <- kubelet 설정
#         └── kubeadm-flags.env            <- kubelet 환경 변수
```

문제가 없으면 실제 join을 진행한다.

<br>

### join 실행

이제 join을 실행한다.

```bash
kubeadm join --config="kubeadm-join.yaml"
```

클러스터 join 단계를 살펴보자.

<br>

#### 1단계: [preflight] 사전 검사

```
[preflight] Running pre-flight checks
[preflight] Reading configuration from the "kubeadm-config" ConfigMap in namespace "kube-system"...
[preflight] Use 'kubeadm init phase upload-config --config your-config.yaml' to re-upload it.
```

#### 2단계: [kubelet-start] kubelet 시작

```
[kubelet-start] Writing kubelet configuration to file "/var/lib/kubelet/config.yaml"
[kubelet-start] Writing kubelet environment file with flags to file "/var/lib/kubelet/kubeadm-flags.env"
[kubelet-start] Starting the kubelet
[kubelet-check] Waiting for a healthy kubelet at http://127.0.0.1:10248/healthz. This can take up to 4m0s
[kubelet-check] The kubelet is healthy after 501.164948ms
[kubelet-start] Waiting for the kubelet to perform the TLS Bootstrap
```

> **참고**: `[kubelet-start]`와 `[kubelet-check]`가 출력에서 섞여 있지만, 모두 **kubelet 초기화의 연속적인 단계**(설정 작성 → 시작 → 헬스체크 → TLS Bootstrap)이므로 하나로 묶었다.

#### 3단계: 완료 메시지

```
This node has joined the cluster:
* Certificate signing request was sent to apiserver and a response was received.
* The Kubelet was informed of the new secure connection details.

Run 'kubectl get nodes' on the control-plane to see this node join the cluster.
```

join이 완료되면 다음 작업이 수행된 것이다:
- kubelet이 API Server에 **CSR(Certificate Signing Request)**을 제출
- kube-controller-manager가 CSR을 **자동 승인** 및 서명
- kubelet이 발급받은 인증서로 API Server와 **mTLS 연결** 설정

<br>

## 워커 노드에서 확인

```bash
# 다운로드된 이미지 확인
crictl images
# IMAGE                                   TAG                 IMAGE ID            SIZE
# ghcr.io/flannel-io/flannel-cni-plugin   v1.7.1-flannel1     127562bd9047f       5.14MB
# ghcr.io/flannel-io/flannel              v0.27.3             d84558c0144bc       33.1MB
# registry.k8s.io/kube-proxy              v1.32.11            dcdb790dc2bfe       27.6MB
# registry.k8s.io/pause                   3.10                afb61768ce381       268kB

# 실행 중인 컨테이너 확인
crictl ps
# CONTAINER       IMAGE           CREATED              STATE     NAME           POD ID          POD                     NAMESPACE
# c5a1bb2f09cf0   d84558c0144bc   About a minute ago   Running   kube-flannel   788680ac14fe0   kube-flannel-ds-8vmb6   kube-flannel
# a96c89da4f25b   dcdb790dc2bfe   2 minutes ago        Running   kube-proxy     b2e21d4d0da3f   kube-proxy-dkczx        kube-system
```

워커 노드가 클러스터에 join되면, DaemonSet으로 배포된 **kube-proxy**와 **kube-flannel**이 자동으로 해당 노드에 스케줄링된다. kube-proxy는 Service 네트워크 규칙(iptables)을 관리하고, kube-flannel은 Pod 네트워크(VXLAN 오버레이)를 구성한다. 이 두 컴포넌트가 정상 실행되어야 노드가 `Ready` 상태가 된다.

### kubelet 상태 확인

```bash
systemctl status kubelet --no-pager
# ● kubelet.service - kubelet: The Kubernetes Node Agent
#      Loaded: loaded (/usr/lib/systemd/system/kubelet.service; enabled; preset: disabled)
#     Drop-In: /usr/lib/systemd/system/kubelet.service.d
#              └─10-kubeadm.conf
#      Active: active (running) since Sun 2026-01-25 02:27:58 KST; 13min ago
#    Main PID: 10552 (kubelet)
#      CGroup: /system.slice/kubelet.service
#              └─10552 /usr/bin/kubelet --bootstrap-kubeconfig=/etc/kubernetes/bootstrap-kubelet.conf --kubeconfig=/etc/kubernetes/kubelet.conf ...
```

kubelet이 [systemd 서비스]({% post_url 2026-01-18-Kubernetes-Kubeadm-01-2 %}#kubelet-서비스-파일-확인)로 실행 중이며, `10-kubeadm.conf` drop-in 파일을 통해 추가 설정이 적용된다.

### 디렉토리 구조 확인

워커 노드의 `/etc/kubernetes` 디렉토리는 컨트롤 플레인보다 훨씬 단순하다:

```bash
tree /etc/kubernetes
# /etc/kubernetes
# ├── kubelet.conf          <- kubelet의 kubeconfig (API Server 연결용)
# ├── manifests             <- 비어있음 (워커 노드는 Static Pod 없음)
# └── pki
#     └── ca.crt            <- 클러스터 CA 인증서 (API Server 검증용)
```

컨트롤 플레인과 달리:
- `admin.conf`, `controller-manager.conf`, `scheduler.conf` 등이 **없음**
- `/etc/kubernetes/pki/`에 `ca.crt`**만** 존재 (다른 인증서/키 없음)
- `manifests/` 디렉토리가 **비어 있음** (Static Pod 없음)

### kubelet.conf 확인

워커 노드의 `kubelet.conf`도 컨트롤 플레인과 마찬가지로 **외부 PEM 파일을 참조**한다:

```yaml
# cat /etc/kubernetes/kubelet.conf
apiVersion: v1
clusters:
- cluster:
    certificate-authority-data: LS0tLS1CRUdJTi...  # 클러스터 CA (base64)
    server: https://192.168.10.100:6443
  name: default-cluster
contexts:
- context:
    cluster: default-cluster
    namespace: default
    user: default-auth
  name: default-context
current-context: default-context
kind: Config
users:
- name: default-auth
  user:
    client-certificate: /var/lib/kubelet/pki/kubelet-client-current.pem
    client-key: /var/lib/kubelet/pki/kubelet-client-current.pem
```

`client-certificate`와 `client-key`가 `/var/lib/kubelet/pki/kubelet-client-current.pem`을 참조하는 것은 [컨트롤 플레인의 kubelet.conf]({% post_url 2026-01-18-Kubernetes-Kubeadm-01-5 %}#kubeletconf)와 동일하다. 이는 `rotateCertificates: true` 설정에 의한 **인증서 자동 갱신**을 지원하기 위함이다.

### cluster-info ConfigMap 접근 확인

워커 노드에서 **인증 없이** API Server의 `cluster-info` ConfigMap에 접근할 수 있다:

```bash
curl -s -k https://192.168.10.100:6443/api/v1/namespaces/kube-public/configmaps/cluster-info | jq '.data | keys'
# [
#   "jws-kubeconfig-123456",
#   "kubeconfig"
# ]
```

이 ConfigMap은 `kube-public` 네임스페이스에 있어 **인증 없이 접근 가능**하며, 새 노드가 클러스터에 join할 때 필요한 정보(CA 인증서, API Server 주소)를 제공한다.

| 필드 | 설명 |
| --- | --- |
| `kubeconfig` | 클러스터 CA 인증서와 API Server 주소가 포함된 kubeconfig |
| `jws-kubeconfig-123456` | Bootstrap Token(`123456`)으로 서명된 JWS (무결성 검증용) |

<br>

# 컨트롤 플레인에서 확인

컨트롤 플레인(k8s-ctr)에서 워커 노드가 정상적으로 join되었는지 확인한다.

## 노드 상태 확인

```bash
# join된 워커 노드 확인
kubectl get nodes
# NAME      STATUS   ROLES           AGE     VERSION
# k8s-ctr   Ready    control-plane   30h     v1.32.11
# k8s-w1    Ready    <none>          7m29s   v1.32.11
# k8s-w2    Ready    <none>          119s    v1.32.11
```

워커 노드 `k8s-w1`, `k8s-w2`가 모두 `Ready` 상태로 join되었다. Flannel이 DaemonSet으로 자동 배포되어 네트워크가 구성되었기 때문에 바로 Ready 상태가 된다.

### 노드 상세 정보

```bash
kubectl describe node k8s-w1
```

<details markdown="1">
<summary>출력 결과</summary>

```
Name:               k8s-w1
Roles:              <none>
Labels:             beta.kubernetes.io/arch=arm64
                    beta.kubernetes.io/os=linux
                    kubernetes.io/arch=arm64
                    kubernetes.io/hostname=k8s-w1
                    kubernetes.io/os=linux
Annotations:        flannel.alpha.coreos.com/backend-data: {"VNI":1,"VtepMAC":"72:14:b4:42:7f:95"}
                    flannel.alpha.coreos.com/backend-type: vxlan
                    flannel.alpha.coreos.com/kube-subnet-manager: true
                    flannel.alpha.coreos.com/public-ip: 192.168.10.101
                    kubeadm.alpha.kubernetes.io/cri-socket: unix:///run/containerd/containerd.sock
Taints:             <none>
Lease:
  HolderIdentity:  k8s-w1
  RenewTime:       Sun, 25 Jan 2026 02:31:12 +0900
Conditions:
  Type                 Status  Reason                       Message
  ----                 ------  ------                       -------
  NetworkUnavailable   False   FlannelIsUp                  Flannel is running on this node
  MemoryPressure       False   KubeletHasSufficientMemory   kubelet has sufficient memory available
  DiskPressure         False   KubeletHasNoDiskPressure     kubelet has no disk pressure
  PIDPressure          False   KubeletHasSufficientPID      kubelet has sufficient PID available
  Ready                True    KubeletReady                 kubelet is posting ready status
Addresses:
  InternalIP:  192.168.10.101
  Hostname:    k8s-w1
System Info:
  OS Image:                   Rocky Linux 10.0 (Red Quartz)
  Container Runtime Version:  containerd://2.1.5
  Kubelet Version:            v1.32.11
  Kube-Proxy Version:         v1.32.11
PodCIDR:                      10.244.1.0/24
Non-terminated Pods:          (2 in total)
  Namespace      Name                     CPU Requests  Memory Requests
  ---------      ----                     ------------  ---------------
  kube-flannel   kube-flannel-ds-8vmb6    100m (5%)     50Mi (2%)
  kube-system    kube-proxy-dkczx         0 (0%)        0 (0%)
Events:
  Type    Reason                   Age    From             Message
  ----    ------                   ----   ----             -------
  Normal  Starting                 3m5s   kube-proxy       
  Normal  RegisteredNode           3m14s  node-controller  Node k8s-w1 event: Registered Node k8s-w1 in Controller
  Normal  NodeReady                2m56s  kubelet          Node k8s-w1 status is now: NodeReady
```

</details>

<br>

`kubectl describe node`는 노드의 상세 상태를 확인할 때 사용한다. 워커 노드가 정상적으로 join되었는지 확인하려면 다음 항목들을 점검한다:

| 항목 | 값 | 설명 |
| --- | --- | --- |
| `Annotations` | `flannel.alpha.coreos.com/*` | Flannel이 VXLAN 설정 정보를 노드에 기록 |
| `Conditions.NetworkUnavailable` | `False` | Flannel이 정상 동작 중 |
| `Conditions.Ready` | `True` | 노드가 워크로드를 받을 준비 완료 |
| `PodCIDR` | `10.244.1.0/24` | 이 노드에 할당된 Pod 네트워크 대역 |
| `Non-terminated Pods` | 2개 | kube-proxy, kube-flannel 자동 배포됨 |

특히 `NetworkUnavailable: False`와 `Ready: True`는 CNI(Flannel)와 kubelet이 정상 동작 중임을 나타내므로 반드시 확인해야 한다.

<br>

## 노드별 Pod CIDR 확인

```bash
# 노드별 Pod CIDR 확인
kubectl get nodes -o jsonpath='{range .items[*]}{.metadata.name}{"\t"}{.spec.podCIDR}{"\n"}{end}'
# k8s-ctr 10.244.0.0/24
# k8s-w1  10.244.1.0/24
# k8s-w2  10.244.2.0/24
```

각 노드에 서로 다른 Pod CIDR이 할당되었다. kube-controller-manager가 `--allocate-node-cidrs=true` 옵션에 따라 `10.244.0.0/16` 대역에서 `/24` 단위로 자동 할당한다.

<br>

## 라우팅 테이블 확인

워커 노드가 join되면 Flannel이 다른 노드의 Pod CIDR에 대한 라우팅을 커널 라우팅 테이블에 자동으로 추가한다:

```bash
# 다른 노드의 Pod CIDR에 대한 라우팅 확인 (컨트롤 플레인에서)
ip -c route | grep flannel
# 10.244.1.0/24 via 10.244.1.0 dev flannel.1 onlink
# 10.244.2.0/24 via 10.244.2.0 dev flannel.1 onlink
```

`flannel.1` 인터페이스를 통해 VXLAN 오버레이 네트워크로 라우팅된다. 이를 통해 컨트롤 플레인에서 워커 노드의 Pod CIDR로 통신이 가능하다:

```bash
# 다른 노드 Pod CIDR로 통신 가능 확인 (VXLAN 오버레이 사용)
ping -c 1 10.244.1.0
# PING 10.244.1.0 (10.244.1.0) 56(84) bytes of data.
# 64 bytes from 10.244.1.0: icmp_seq=1 ttl=64 time=0.765 ms
```

<br>

## 워커 노드에 배포된 Pod 확인

워커 노드에는 Taint가 없으므로 일반 워크로드 Pod가 스케줄링될 수 있다:

```bash
# 워커 노드의 Taints 정보 확인 (없음)
kubectl describe node k8s-w1 | grep Taints
# Taints:             <none>
```

DaemonSet으로 배포되는 `kube-flannel`과 `kube-proxy`가 각 워커 노드에 자동으로 배포되어 있다:

```bash
# 워커 노드에 배포된 Pod 확인
kubectl get pod -A -owide | grep k8s-w1
# kube-flannel   kube-flannel-ds-8vmb6   1/1   Running   0   10m   192.168.10.101   k8s-w1
# kube-system    kube-proxy-dkczx        1/1   Running   0   10m   192.168.10.101   k8s-w1

kubectl get pod -A -owide | grep k8s-w2
# kube-flannel   kube-flannel-ds-wtdsc   1/1   Running   0   4m39s   192.168.10.102   k8s-w2
# kube-system    kube-proxy-frb9n        1/1   Running   0   4m39s   192.168.10.102   k8s-w2
```

컨트롤 플레인 노드와 달리 워커 노드에는 `node-role.kubernetes.io/control-plane:NoSchedule` Taint가 없어서 일반 Pod가 스케줄링된다.

<br>


# 결과

이 단계를 완료하면 다음과 같은 결과를 얻을 수 있다:

| 항목 | 결과 |
| --- | --- |
| 워커 노드 | k8s-w1, k8s-w2 클러스터에 join 완료 |
| 노드 상태 | 모든 노드 Ready |
| Pod CIDR | k8s-ctr: 10.244.0.0/24, k8s-w1: 10.244.1.0/24, k8s-w2: 10.244.2.0/24 |
| DaemonSet | kube-proxy, kube-flannel 자동 배포 |
| 라우팅 | Flannel VXLAN을 통한 노드 간 Pod 통신 가능 |

<br>

클러스터 구성이 완료되었다. 다음 글에서는 모니터링 도구(kube-prometheus-stack, x509 certificate exporter)를 설치하여 클러스터와 인증서 상태를 모니터링한다.

<br>

# 부록

## 트러블슈팅: kubeadm join이 멈출 때

`kubeadm join`이 `[preflight] Running pre-flight checks`에서 멈추는 경우, 대부분 **네트워크 연결 문제**다.

### 증상

```bash
kubeadm join --config="kubeadm-join.yaml"
# [preflight] Running pre-flight checks
# (여기서 멈춤)
```

### 확인 순서

**1단계: API Server 연결 테스트** (워커 노드에서)

```bash
curl -k https://192.168.10.100:6443/healthz
# 정상: "ok"
# 실패: "Could not connect to server"
```

**2단계: 네트워크 연결 확인** (워커 노드에서)

```bash
# IP 주소 확인
ip addr show enp0s9
# 192.168.10.101이 있어야 함

# ping 테스트
ping -c 3 192.168.10.100
# 정상: 응답 받음

# 라우팅 테이블 확인
ip route
# 192.168.10.0/24 dev enp0s9 경로가 있어야 함
```

**3단계: API Server 바인딩 확인** (컨트롤 플레인에서)

```bash
ss -tlnp | grep 6443
# LISTEN *:6443 이어야 함 (모든 인터페이스)
# 127.0.0.1:6443이면 외부 접근 불가
```

**4단계: 방화벽 확인** (컨트롤 플레인에서)

```bash
# Rocky/CentOS
systemctl is-active firewalld
# active면 방화벽이 차단 중일 수 있음

# Ubuntu
ufw status
```

### 원인

이번 실습에서는 ping은 성공하지만 6443 포트 연결이 실패했다:

```bash
# 워커에서
ping -c 3 192.168.10.100
# 64 bytes from 192.168.10.100: icmp_seq=1 ttl=64 time=0.882 ms  <- 성공

curl -k https://192.168.10.100:6443/healthz
# curl: (7) Failed to connect to 192.168.10.100 port 6443  <- 실패
```

**컨트롤 플레인의 firewalld가 활성화**되어 6443 포트를 차단하고 있었기 때문이다.

```bash
# 컨트롤 플레인에서
systemctl is-active firewalld
# active
```

> **참고**: [1-2 글]({% post_url 2026-01-18-Kubernetes-Kubeadm-01-2 %}#방화벽-비활성화)에서 firewalld를 비활성화했지만, VM을 새로 provision하거나 snapshot에서 복원하면 다시 활성화될 수 있다.

### 해결

```bash
# 컨트롤 플레인에서 firewalld 비활성화
systemctl disable --now firewalld

# 또는 필요한 포트만 열기
firewall-cmd --permanent --add-port=6443/tcp
firewall-cmd --permanent --add-port=10250/tcp
firewall-cmd --reload
```

방화벽 비활성화 후 워커 노드에서 다시 join하면 정상 동작한다.

<br>

## 설정 전후 비교

kubeadm join 전후의 시스템 상태를 비교하면 어떤 변경이 발생했는지 파악할 수 있다. 학습이나 트러블슈팅 시 유용하다.

```bash
# join 후 환경 정보 저장 (워커 노드에서)
crictl images | tee -a crictl_images-2.txt
crictl ps | tee -a crictl_ps-2.txt
cat /etc/sysconfig/kubelet  # KUBELET_EXTRA_ARGS= (비어있음)
tree /etc/kubernetes  | tee -a etc_kubernetes-2.txt
tree /var/lib/kubelet | tee -a var_lib_kubelet-2.txt
tree /run/containerd/ -L 3 | tee -a run_containerd-2.txt
pstree -alnp | tee -a pstree-2.txt
systemd-cgls --no-pager | tee -a systemd-cgls-2.txt
lsns | tee -a lsns-2.txt
ip addr | tee -a ip_addr-2.txt 
ss -tnlp | tee -a ss-2.txt
df -hT | tee -a df-2.txt
findmnt | tee -a findmnt-2.txt
sysctl -a | tee -a sysctl-2.txt

# join 전후 비교 (vi -d 로 diff 확인)
vi -d crictl_images-1.txt crictl_images-2.txt
vi -d crictl_ps-1.txt crictl_ps-2.txt
vi -d etc_kubernetes-1.txt etc_kubernetes-2.txt
vi -d var_lib_kubelet-1.txt var_lib_kubelet-2.txt
vi -d run_containerd-1.txt run_containerd-2.txt
vi -d pstree-1.txt pstree-2.txt
vi -d systemd-cgls-1.txt systemd-cgls-2.txt
vi -d lsns-1.txt lsns-2.txt
vi -d ip_addr-1.txt ip_addr-2.txt
vi -d ss-1.txt ss-2.txt
vi -d df-1.txt df-2.txt
vi -d findmnt-1.txt findmnt-2.txt
vi -d sysctl-1.txt sysctl-2.txt
```

> **팁**: kubeadm join 전에 동일한 명령으로 `*-1.txt` 파일들을 생성해 두면, `vi -d`로 변경 사항을 시각적으로 비교할 수 있다.

워커 노드 join 후 주요 변경 사항:
- `/etc/kubernetes/`: `kubelet.conf`, `pki/ca.crt` 생성 (컨트롤 플레인보다 훨씬 적음)
- `/var/lib/kubelet/`: `config.yaml`, `kubeadm-flags.env` 등 kubelet 설정 생성
- `sysctl`: `kernel.panic`, `vm.overcommit_memory` 등 커널 파라미터 변경
- 프로세스: kubelet, containerd 하위에 kube-proxy, kube-flannel 컨테이너 실행

<br>
