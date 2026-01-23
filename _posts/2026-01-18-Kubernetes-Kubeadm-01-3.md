---
title:  "[Kubernetes] Cluster: Kubeadm을 이용해 클러스터 구성하기 - 1-3. kubeadm init 실행 및 편의 도구 설치"
excerpt: "kubeadm init을 실행하여 컨트롤 플레인을 구성하고, kubectl 편의 도구를 설치해 보자."
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

이번 글의 목표는 **kubeadm init 실행 및 컨트롤 플레인 구성**이다.

- **kubeadm init**: 설정 파일을 사용하여 컨트롤 플레인 초기화
- **kubeconfig 설정**: kubectl 사용을 위한 설정
- **편의 도구**: kubecolor, kubectx, kubens, kube-ps1, helm, k9s 설치

<br>

# 들어가며

[이전 글]({% post_url 2026-01-18-Kubernetes-Kubeadm-01-2 %})에서 사전 설정과 containerd, kubeadm 설치를 완료했다. 이제 `kubeadm init`을 실행하여 컨트롤 플레인을 구성한다. 

컨트롤 플레인 구성이 목적이므로, 이 글에서는 **컨트롤 플레인 노드(k8s-ctr)**에서만 작업을 진행한다.

<br>

# kubeadm init 실행

## kubeadm 설정 파일 작성

`kubeadm init`은 명령줄 옵션과 설정 파일 두 가지 방식을 지원한다.

### 명령줄 옵션 방식

명령줄 옵션 방식은 간단한 테스트에 적합하다.

```bash
kubeadm init \
  --apiserver-advertise-address=192.168.10.100 \
  --pod-network-cidr=10.244.0.0/16 \
  --service-cidr=10.96.0.0/16 \
  --kubernetes-version=1.32.11 \
  --token=123456.1234567890123456 \
  --token-ttl=0
```

### 설정 파일 방식

명령줄 옵션 대신 YAML 설정 파일을 사용하면 버전 관리와 재현성 측면에서 더 좋다. 이번 실습에서도 설정 파일 방식을 사용한다.

```bash
## kubeadm Configuration 파일 작성
cat << EOF > kubeadm-init.yaml
apiVersion: kubeadm.k8s.io/v1beta4
kind: InitConfiguration
bootstrapTokens:
- token: "123456.1234567890123456"    # 토큰 고정 (실습용)
  ttl: "0s"                           # 토큰 만료 시간 없음 (실습용)
  usages:
  - signing
  - authentication
nodeRegistration:
  kubeletExtraArgs:
    - name: node-ip
      value: "192.168.10.100"         # 미설정 시 10.0.2.15로 매핑될 수 있음 (실습 환경 특수성)
  criSocket: "unix:///run/containerd/containerd.sock"
localAPIEndpoint:
  advertiseAddress: "192.168.10.100"
---
apiVersion: kubeadm.k8s.io/v1beta4
kind: ClusterConfiguration
kubernetesVersion: "1.32.11"
networking:
  podSubnet: "10.244.0.0/16"          # Flannel 기본값
  serviceSubnet: "10.96.0.0/16"
EOF
cat kubeadm-init.yaml
```

### 설정 파일 주요 항목

| 항목 | 설명 |
| --- | --- |
| `bootstrapTokens` | 워커 노드 join 시 사용할 토큰 |
| `nodeRegistration.kubeletExtraArgs` | kubelet에 전달할 추가 인자. `node-ip`를 명시하여 올바른 IP 사용 |
| `localAPIEndpoint.advertiseAddress` | API Server가 광고할 IP 주소 |
| `networking.podSubnet` | Pod 네트워크 CIDR. Flannel 사용 시 `10.244.0.0/16` |
| `networking.serviceSubnet` | Service 네트워크 CIDR |

주요 설정 항목 값에서 주의해서 봐야 하는 것은 다음과 같다:
- **node-ip**: Vagrant처럼 여러 네트워크 인터페이스가 있는 환경에서는 반드시 명시해야 한다. 미설정 시 NAT 인터페이스 IP(10.0.2.15)가 사용되어 노드 간 통신에 문제가 발생할 수 있다.
- **advertiseAddress vs node-ip**: `advertiseAddress`는 API Server가 광고하는 주소, `node-ip`는 kubelet이 사용하는 주소다. 둘 다 클러스터 통신용 IP로 일치시키는 것이 좋다.
- **podSubnet**: CNI 플러그인마다 기본값이 다르다. Flannel은 `10.244.0.0/16`, Calico는 `192.168.0.0/16`이 기본값이다. 사용할 CNI에 맞춰 설정한다.
- **token**: 이번 실습에서는 토큰을 `123456.1234567890123456`으로 **고정**했다. 기본적으로 `kubeadm init`은 랜덤 토큰을 생성하지만, 실습 재현성과 워커 노드 join 편의를 위해 미리 정해진 토큰을 사용한다. `ttl: "0s"`는 토큰이 만료되지 않음을 의미한다. 프로덕션에서는 보안을 위해 적절한 TTL(예: `24h`)을 설정하거나, 노드 join 후 토큰을 삭제하는 것이 좋다.
- **criSocket**: containerd 외 CRI-O 등 다른 런타임 사용 시 해당 소켓 경로로 변경해야 한다.


<br>

## 컨테이너 이미지 사전 다운로드 (선택)

네트워크 환경에 따라 `kubeadm init` 시간을 단축하기 위해 이미지를 미리 다운로드할 수 있다.

```bash
# 필요한 이미지 목록 확인
kubeadm config images list
# registry.k8s.io/kube-apiserver:v1.32.11
# registry.k8s.io/kube-controller-manager:v1.32.11
# registry.k8s.io/kube-scheduler:v1.32.11
# registry.k8s.io/kube-proxy:v1.32.11
# registry.k8s.io/coredns/coredns:v1.11.3
# registry.k8s.io/pause:3.10
# registry.k8s.io/etcd:3.5.24-0

# 이미지 사전 다운로드
kubeadm config images pull
# [config/images] Pulled registry.k8s.io/kube-apiserver:v1.32.11
# [config/images] Pulled registry.k8s.io/kube-controller-manager:v1.32.11
# [config/images] Pulled registry.k8s.io/kube-scheduler:v1.32.11
# [config/images] Pulled registry.k8s.io/kube-proxy:v1.32.11
# [config/images] Pulled registry.k8s.io/coredns/coredns:v1.11.3
# [config/images] Pulled registry.k8s.io/pause:3.10
# [config/images] Pulled registry.k8s.io/etcd:3.5.24-0
```

kubeadm은 설치된 버전과 설정 파일을 기반으로 필요한 이미지 목록을 결정한다:

| 이미지 | 버전 결정 방식 |
| --- | --- |
| kube-apiserver, kube-controller-manager, kube-scheduler, kube-proxy | `kubernetesVersion`과 동일 |
| etcd, coredns, pause | kubeadm 소스 코드에 하드코딩된 호환 버전 |

설정 파일이나 특정 버전을 지정하면 해당 버전에 맞는 이미지 목록을 확인할 수 있다:

```bash
kubeadm config images list --config=kubeadm-init.yaml      # 설정 파일 기반
kubeadm config images list --kubernetes-version=1.33.0    # 특정 버전 지정
```

> **참고: 업그레이드 시 이미지 사전 다운로드**
> 
> 클러스터 **업그레이드** 시에는 이미지 사전 다운로드가 특히 유용하다. `kubeadm upgrade apply` 과정에서 새 버전 이미지를 pull하는 시간이 포함되면, 컨트롤 플레인 컴포넌트의 다운타임이 길어질 수 있다. 
> 
> 업그레이드 전에 `kubeadm config images pull --kubernetes-version=<target-version>`으로 미리 이미지를 받아두면 실제 업그레이드 시간을 크게 단축할 수 있다.

<br>

## 실행 단계

> **참고**: 이전 글에서 살펴본 `kubeadm init`의 14단계가 실제로 빠르게 진행된다. 사전에 이미지를 pull해두었고, 설정이 올바르다면 **전체 과정이 수 초 내에 완료**된다.

### (선택) dry-run으로 사전 확인

`--dry-run` 옵션을 사용하면 실제로 클러스터를 생성하지 않고 **어떤 작업이 수행될지 미리 확인**할 수 있다. 생성될 리소스들의 YAML 매니페스트도 출력된다.

```bash
kubeadm init --config="kubeadm-init.yaml" --dry-run
```

dry-run 출력은 `[dryrun] Would perform action <ACTION> on resource` 형식으로 **실제로 수행될 API 호출**을 보여준다:

```
[dryrun] Would perform action CREATE on resource "configmaps" in API group "core/v1"
[dryrun] Attached object:
apiVersion: v1
data:
  kubelet: |
    apiVersion: kubelet.config.k8s.io/v1beta1
    cgroupDriver: systemd
    clusterDNS:
    - 10.96.0.10
    staticPodPath: /etc/kubernetes/manifests
    rotateCertificates: true
    ...
kind: ConfigMap
metadata:
  name: kubelet-config
  namespace: kube-system
```

이처럼 각 리소스에 대해 **어떤 action(CREATE, GET, PATCH 등)이 수행될지**와 함께 **생성될 오브젝트의 YAML**이 출력된다.

dry-run 출력에서 주요하게 확인할 부분:

| 리소스 | 설명 |
| --- | --- |
| `kubelet-config` ConfigMap | 클러스터 내 모든 kubelet이 공유할 설정 (`cgroupDriver: systemd`, `clusterDNS`, `staticPodPath` 등) |
| `bootstrap-token-*` Secret | 워커 노드 join에 사용할 부트스트랩 토큰 |
| `cluster-info` ConfigMap | 워커 노드가 클러스터에 join할 때 사용하는 CA 인증서와 API Server 주소 |
| `coredns` Deployment/ConfigMap | 클러스터 DNS 서비스 |
| `kube-proxy` DaemonSet/ConfigMap | 각 노드의 네트워크 프록시 |

dry-run 후 `/etc/kubernetes` 디렉토리 구조를 확인하면, **실제 파일은 생성되지 않고 임시 디렉토리에만 생성**된 것을 알 수 있다:

```bash
tree /etc/kubernetes
# /etc/kubernetes
# ├── manifests                      <- 비어있음 (dry-run이므로)
# └── tmp
#     └── kubeadm-init-dryrun*       <- dry-run 결과가 여기에 저장
#         ├── admin.conf
#         ├── apiserver.crt
#         ├── ca.crt
#         ├── ca.key
#         ├── etcd/
#         │   ├── ca.crt, ca.key
#         │   ├── server.crt, server.key
#         │   └── ...
#         ├── etcd.yaml              <- etcd Static Pod 매니페스트
#         ├── kube-apiserver.yaml    <- API Server Static Pod 매니페스트
#         ├── kube-controller-manager.yaml
#         ├── kube-scheduler.yaml
#         └── ...
```

이 구조를 통해 실제 init 시 어떤 인증서와 매니페스트가 생성될지 미리 확인할 수 있다. 문제가 없으면 실제 init을 진행한다.

<br>

### init 실행

이제 init을 실행행한다.

```bash
kubeadm init --config="kubeadm-init.yaml"
```

클러스터 초기화 단계의 하이라이트인 만큼, 출력을 단계별로 살펴보자.

<br>

#### 1단계: [preflight] 사전 검사

```bash
[init] Using Kubernetes version: v1.32.11
[preflight] Running pre-flight checks
        [WARNING Firewalld]: firewalld is active, please ensure ports [6443 10250] are open or your cluster may not function correctly
[preflight] Pulling images required for setting up a Kubernetes cluster
[preflight] This might take a minute or two, depending on the speed of your internet connection
[preflight] You can also perform this action beforehand using 'kubeadm config images pull'
```

- Kubernetes 버전 확인 (v1.32.11)
- 사전 검사 수행: 시스템 요구사항, 포트 충돌, 커널 파라미터 등
- **firewalld 경고**: 6443(API Server), 10250(kubelet) 포트가 열려있어야 함. 실습에서는 firewalld를 비활성화했으므로 무시해도 됨
- 이미지 pull 안내: 이미 `kubeadm config images pull`로 받아두었으므로 빠르게 진행

<br>

#### 2단계: [certs] 인증서 생성

```bash
[certs] Using certificateDir folder "/etc/kubernetes/pki"
[certs] Generating "ca" certificate and key
[certs] Generating "apiserver" certificate and key
[certs] apiserver serving cert is signed for DNS names [k8s-ctr kubernetes kubernetes.default kubernetes.default.svc kubernetes.default.svc.cluster.local] and IPs [10.96.0.1 192.168.10.100]
[certs] Generating "apiserver-kubelet-client" certificate and key
[certs] Generating "front-proxy-ca" certificate and key
[certs] Generating "front-proxy-client" certificate and key
[certs] Generating "etcd/ca" certificate and key
[certs] Generating "etcd/server" certificate and key
[certs] etcd/server serving cert is signed for DNS names [k8s-ctr localhost] and IPs [192.168.10.100 127.0.0.1 ::1]
[certs] Generating "etcd/peer" certificate and key
[certs] Generating "etcd/healthcheck-client" certificate and key
[certs] Generating "apiserver-etcd-client" certificate and key
[certs] Generating "sa" key and public key
```

[이전 글]({% post_url 2026-01-18-Kubernetes-Kubeadm-01-1 %})에서 살펴본, [Kubernetes The Hard Way]({% post_url 2026-01-05-Kubernetes-Cluster-The-Hard-Way-04-1 %})에서 OpenSSL로 일일이 생성했던 인증서들이 자동으로 생성된다:

| 인증서 | 용도 |
| --- | --- |
| `ca` | 클러스터 루트 CA (모든 인증서의 신뢰 기반) |
| `apiserver` | API Server의 TLS 서빙 인증서 |
| `apiserver-kubelet-client` | API Server가 kubelet에 접근할 때 사용 |
| `front-proxy-ca/client` | API Aggregation Layer용 |
| `etcd/ca`, `etcd/server`, `etcd/peer` | etcd 클러스터 내부 통신용 |
| `etcd/healthcheck-client` | etcd 헬스체크용 |
| `apiserver-etcd-client` | API Server가 etcd에 접근할 때 사용 |
| `sa` (Service Account) | ServiceAccount 토큰 서명용 키 쌍 |

<br>

`apiserver` 인증서의 SAN(Subject Alternative Name)에 다양한 DNS와 IP가 포함됨에 주목하자.
- DNS: `k8s-ctr`, `kubernetes`, `kubernetes.default`, `kubernetes.default.svc`, `kubernetes.default.svc.cluster.local`
- IP: `10.96.0.1` (Service CIDR의 첫 번째 IP), `192.168.10.100` (advertiseAddress)

다시 한 번 짚고 넘어 가지만, 클라이언트가 API Server에 접속할 때 **접속 주소가 인증서의 SAN에 포함되어 있어야** TLS 검증이 통과된다. 예를 들어,
- Pod 내부에서 `https://kubernetes.default.svc:443`으로 접속하거나
- 외부에서 `https://192.168.10.100:6443`으로 접속할 때
모두 이 인증서로 검증된다. 

만약 다음과 같은 경우에는 `--apiserver-cert-extra-sans` 옵션으로 SAN을 추가해야 한다:
- **HA 구성**: 여러 컨트롤 플레인 앞에 Load Balancer를 두는 경우, LB의 IP/DNS가 SAN에 포함되어야 함
- **커스텀 도메인**: `api.mycompany.com` 같은 도메인으로 접근하려는 경우
- **클라우드 환경**: 외부 IP(Public IP)가 내부 IP와 다른 경우

<br>

#### 3단계: [kubeconfig] kubeconfig 파일 생성

각 컴포넌트가 API Server에 인증할 때 사용하는 kubeconfig 파일이 생성된다.

```bash
[kubeconfig] Using kubeconfig folder "/etc/kubernetes"
[kubeconfig] Writing "admin.conf" kubeconfig file
[kubeconfig] Writing "super-admin.conf" kubeconfig file
[kubeconfig] Writing "kubelet.conf" kubeconfig file
[kubeconfig] Writing "controller-manager.conf" kubeconfig file
[kubeconfig] Writing "scheduler.conf" kubeconfig file
```

| 파일 | 용도 |
| --- | --- |
| `admin.conf` | 클러스터 관리자용 (`kubectl` 사용 시) |
| `super-admin.conf` | 최고 권한 관리자용 (1.29+에서 추가) |
| `kubelet.conf` | kubelet이 API Server에 연결할 때 사용 |
| `controller-manager.conf` | Controller Manager가 API Server에 연결할 때 사용 |
| `scheduler.conf` | Scheduler가 API Server에 연결할 때 사용 |

<br>

#### 4단계: [etcd], [control-plane] Static Pod 매니페스트 생성

etcd와 컨트롤 플레인 컴포넌트들의 Static Pod 매니페스트가 `/etc/kubernetes/manifests/`에 생성된다. kubelet은 이 디렉토리를 감시하다가 매니페스트가 생성되면 자동으로 Pod를 실행한다.

```bash
[etcd] Creating static Pod manifest for local etcd in "/etc/kubernetes/manifests"
[control-plane] Using manifest folder "/etc/kubernetes/manifests"
[control-plane] Creating static Pod manifest for "kube-apiserver"
[control-plane] Creating static Pod manifest for "kube-controller-manager"
[control-plane] Creating static Pod manifest for "kube-scheduler"
```

<br>

#### 5단계: [kubelet-start] kubelet 시작

kubelet을 시작한다. kubelet이 시작되면 `/etc/kubernetes/manifests/`의 Static Pod들을 실행한다.

```bash
[kubelet-start] Writing kubelet environment file with flags to file "/var/lib/kubelet/kubeadm-flags.env"
[kubelet-start] Writing kubelet configuration to file "/var/lib/kubelet/config.yaml"
[kubelet-start] Starting the kubelet
```

- `/var/lib/kubelet/kubeadm-flags.env`: kubelet 시작 시 전달할 플래그 (node-ip 등)
- `/var/lib/kubelet/config.yaml`: kubelet 설정 파일 (이 파일이 없어서 이전에 crashloop이었음)

<br>

#### 6단계: [wait-control-plane] 컨트롤 플레인 대기

이 단계에서 이미지 사전 다운로드의 효과가 나타난다. 최대 4분까지 기다릴 수 있다고 하지만, 실제로는 수 초 만에 완료된다.

```bash
[wait-control-plane] Waiting for the kubelet to boot up the control plane as static Pods from directory "/etc/kubernetes/manifests"
[kubelet-check] Waiting for a healthy kubelet at http://127.0.0.1:10248/healthz. This can take up to 4m0s
[kubelet-check] The kubelet is healthy after 1.002214971s
[api-check] Waiting for a healthy API server. This can take up to 4m0s
[api-check] The API server is healthy after 3.003031359s
```

- kubelet 헬스체크 (`:10248/healthz`): 약 **1초** 만에 healthy
- API Server 헬스체크: 약 **3초** 만에 healthy

<br>

#### 7단계: [upload-config] 설정 업로드

이제 API Server가 동작하므로, 클러스터 자체에 설정을 저장할 수 있다. 이렇게 하면 나중에 업그레이드하거나 노드를 추가할 때 일관된 설정을 사용할 수 있다.

```
[upload-config] Storing the configuration used in ConfigMap "kubeadm-config" in the "kube-system" Namespace
[kubelet] Creating a ConfigMap "kubelet-config" in namespace kube-system with the configuration for the kubelets in the cluster
```

- `kubeadm-config`: kubeadm init에 사용된 설정을 ConfigMap으로 저장 (`kubeadm upgrade` 시 참조)
- `kubelet-config`: 클러스터 내 모든 kubelet이 공유할 설정 (워커 노드 join 시 참조)

<br>

#### 8단계: [mark-control-plane] 컨트롤 플레인 마킹

컨트롤 플레인 노드는 etcd, API Server 등 핵심 컴포넌트가 실행되므로, 일반 워크로드와 분리하여 안정성을 확보해야 한다. Label과 Taint로 이를 구현한다.

```bash
[mark-control-plane] Marking the node k8s-ctr as control-plane by adding the labels: [node-role.kubernetes.io/control-plane node.kubernetes.io/exclude-from-external-load-balancers]
[mark-control-plane] Marking the node k8s-ctr as control-plane by adding the taints [node-role.kubernetes.io/control-plane:NoSchedule]
```

- **Label 추가**: `node-role.kubernetes.io/control-plane` → `kubectl get nodes`에서 역할 표시
- **Taint 추가**: `node-role.kubernetes.io/control-plane:NoSchedule` → 일반 Pod가 스케줄링되지 않음

<br>

#### 9단계: [bootstrap-token] 부트스트랩 토큰 설정

부트스트랩 토큰은 워커 노드가 클러스터에 join할 때 사용하는 임시 인증 수단이다. 이 토큰으로 인증한 후 kubelet은 자신의 인증서를 발급받아 장기 자격 증명으로 전환한다.

```bash
[bootstrap-token] Using token: 123456.1234567890123456
[bootstrap-token] Configuring bootstrap tokens, cluster-info ConfigMap, RBAC Roles
[bootstrap-token] Configured RBAC rules to allow Node Bootstrap tokens to get nodes
[bootstrap-token] Configured RBAC rules to allow Node Bootstrap tokens to post CSRs in order for nodes to get long term certificate credentials
[bootstrap-token] Configured RBAC rules to allow the csrapprover controller automatically approve CSRs from a Node Bootstrap Token
[bootstrap-token] Configured RBAC rules to allow certificate rotation for all node client certificates in the cluster
[bootstrap-token] Creating the "cluster-info" ConfigMap in the "kube-public" namespace
```

- 설정 파일에서 지정한 **고정 토큰**(`123456.1234567890123456`)이 사용됨
- RBAC 규칙 설정: 워커 노드가 토큰으로 join하고 인증서를 발급받을 수 있도록
- `cluster-info` ConfigMap: `kube-public` 네임스페이스에 생성되어 워커 노드가 클러스터 정보를 가져갈 수 있음

<br>

#### 10단계: [addons] 애드온 설치

클러스터가 정상 작동하려면 DNS와 네트워크 프록시가 필수다. kubeadm은 이 두 가지 핵심 애드온을 자동으로 설치한다.

```bash
[addons] Applied essential addon: CoreDNS
[addons] Applied essential addon: kube-proxy
```

- **CoreDNS**: 클러스터 내부 DNS 서비스 (Deployment로 배포, CNI 설치 전까지 Pending 상태)
- **kube-proxy**: 각 노드의 네트워크 프록시 (DaemonSet으로 배포)

#### 완료 메시지

드디어 완료 메시지를 볼 수 있다.

```bash
Your Kubernetes control-plane has initialized successfully!

To start using your cluster, you need to run the following as a regular user:

  mkdir -p $HOME/.kube
  sudo cp -i /etc/kubernetes/admin.conf $HOME/.kube/config
  sudo chown $(id -u):$(id -g) $HOME/.kube/config

Alternatively, if you are the root user, you can run:

  export KUBECONFIG=/etc/kubernetes/admin.conf

You should now deploy a pod network to the cluster.
Run "kubectl apply -f [podnetwork].yaml" with one of the options listed at:
  https://kubernetes.io/docs/concepts/cluster-administration/addons/

Then you can join any number of worker nodes by running the following on each as root:

kubeadm join 192.168.10.100:6443 --token 123456.1234567890123456 \
        --discovery-token-ca-cert-hash sha256:bd763182471f1ed47780644230f234a89061a29041a922a74c849a48342c797d
```

완료 메시지에서 중요한 정보를 살펴 보자.
1. **kubeconfig 설정 방법**: kubectl 사용을 위한 설정
2. **CNI 플러그인 설치 필요**: 아직 Pod 네트워크가 없음
3. **워커 노드 join 명령어**: 토큰과 CA cert hash가 포함된 명령어 → **워커 노드에서 그대로 복사하여 실행하면 됨**

> **참고**: 토큰을 고정해두었기 때문에 join 명령어의 토큰 부분이 항상 동일하다. CA cert hash만 기억해두면 워커 노드 join 시 바로 사용할 수 있다.

완료 메시지에서 보이는 아래 커맨드를 [워커 노드 join]({% post_url 2026-01-18-Kubernetes-Kubeadm-01-5 %}) 시 바로 사용할 수 있다.

```bash
Then you can join any number of worker nodes by running the following on each as root:

kubeadm join 192.168.10.100:6443 --token 123456.1234567890123456 \
        --discovery-token-ca-cert-hash sha256:bd763182471f1ed47780644230f234a89061a29041a922a74c849a48342c797d
```

<br>

### crictl로 컨트롤 플레인 컴포넌트 확인

`kubeadm init`이 완료된 직후 crictl로 실행 중인 컨테이너를 확인해 보자.

```bash
crictl images
# IMAGE                                     TAG                 IMAGE ID            SIZE
# registry.k8s.io/coredns/coredns           v1.11.3             2f6c962e7b831       16.9MB
# registry.k8s.io/etcd                      3.5.24-0            1211402d28f58       21.9MB
# registry.k8s.io/kube-apiserver            v1.32.11            58951ea1a0b5d       26.4MB
# registry.k8s.io/kube-controller-manager   v1.32.11            82766e5f2d560       24.2MB
# registry.k8s.io/kube-proxy                v1.32.11            dcdb790dc2bfe       27.6MB
# registry.k8s.io/kube-scheduler            v1.32.11            cfa17ff3d6634       19.2MB
# registry.k8s.io/pause                     3.10                afb61768ce381       268kB

crictl ps
# CONTAINER      IMAGE          CREATED          STATE     NAME                      POD
# dc8f81e24dff7  dcdb790dc2bfe  18 minutes ago   Running   kube-proxy                kube-proxy-5p6jx
# 28856e606823f  58951ea1a0b5d  18 minutes ago   Running   kube-apiserver            kube-apiserver-k8s-ctr
# e7593756117ad  1211402d28f58  18 minutes ago   Running   etcd                      etcd-k8s-ctr
# 61a09c44673c6  cfa17ff3d6634  18 minutes ago   Running   kube-scheduler            kube-scheduler-k8s-ctr
# 65d20308c4200  82766e5f2d560  18 minutes ago   Running   kube-controller-manager   kube-controller-manager-k8s-ctr
```

사전에 다운로드한 7개의 이미지가 모두 사용되고 있다. 실행 중인 컨테이너를 보면:
- **Static Pod**: `kube-apiserver`, `etcd`, `kube-scheduler`, `kube-controller-manager` (이름에 `-k8s-ctr` 노드명 포함)
- **DaemonSet Pod**: `kube-proxy` (이름이 랜덤 suffix)
- **coredns**는 CNI 플러그인 설치 전이라 아직 Pending 상태 (컨테이너로 보이지 않음)

<br>

## kubeconfig 설정

kubectl을 사용하기 위해 kubeconfig를 설정한다.

### `/root/.kube/config`

kubectl은 기본적으로 `$HOME/.kube/config` 파일에서 클러스터 접속 정보를 읽는다. 현재 root 사용자이므로 `/root/.kube/config`에 설정한다. 일반 사용자라면 `/home/<username>/.kube/config`가 된다.

### `admin.conf`

[이전 글]({% post_url 2026-01-18-Kubernetes-Kubeadm-01-1 %}#3-kubeconfig)에서 살펴본 것처럼, `/etc/kubernetes/admin.conf`는 **클러스터 관리자 권한**이 포함된 kubeconfig 파일이다:
- **인증서**: `kubernetes-admin` 사용자의 클라이언트 인증서 (Base64 인코딩)
- **API Server 주소**: `https://192.168.10.100:6443`
- **클러스터 CA**: API Server 인증서 검증용

이 파일을 복사하면 kubectl이 API Server에 인증하고 모든 리소스에 접근할 수 있다.

```bash
mkdir -p /root/.kube
cp -i /etc/kubernetes/admin.conf /root/.kube/config
chown $(id -u):$(id -g) /root/.kube/config

kubectl cluster-info
# Kubernetes control plane is running at https://192.168.10.100:6443
# CoreDNS is running at https://192.168.10.100:6443/api/v1/namespaces/kube-system/services/kube-dns:dns/proxy
```

컨트롤 플레인이 `192.168.10.100:6443`에서 실행 중임을 확인할 수 있다.

<br>

## 초기 상태 확인

이제 클러스터 컨트롤 플레인 구성이 완료되었으니 초기 상태를 확인해 보자.

### 노드 상태

클러스터에 등록된 노드 정보를 확인한다. 현재 컨트롤 플레인만 초기화했기 때문에, 컨트롤 플레인 노드만 확인할 수 있다.

```bash
kubectl get node -o wide
# NAME      STATUS     ROLES           AGE   VERSION    INTERNAL-IP      EXTERNAL-IP   OS-IMAGE                        KERNEL-VERSION                  CONTAINER-RUNTIME
# k8s-ctr   NotReady   control-plane   20m   v1.32.11   192.168.10.100   <none>        Rocky Linux 10.0 (Red Quartz)   6.12.0-55.39.1.el10_0.aarch64   containerd://2.1.5
```

| 필드 | 값 | 설명 |
| --- | --- | --- |
| `STATUS` | **NotReady** | CNI 플러그인 미설치로 네트워크 준비 안됨 |
| `ROLES` | control-plane | 8단계에서 추가한 Label |
| `INTERNAL-IP` | 192.168.10.100 | `node-ip`로 지정한 클러스터 통신용 IP |
| `CONTAINER-RUNTIME` | containerd://2.1.5 | 설치한 containerd 버전 |

### 노드 리소스 정보

kubelet이 노드의 리소스를 API Server에 보고한다. 스케줄러는 이 정보를 바탕으로 Pod 배치를 결정한다.

```bash
kubectl get nodes -o json | jq ".items[] | {name:.metadata.name} + .status.capacity"
# {
#   "name": "k8s-ctr",
#   "cpu": "4",
#   "ephemeral-storage": "60970Mi",
#   "memory": "2893976Ki",
#   "pods": "110"
# }
```

### kube-system 네임스페이스 리소스 확인

[`kube-system`]({% post_url 2026-01-18-Kubernetes-Kubeadm-01-1 %}#4-etcd-control-plane-static-pod-매니페스트-생성)은 Kubernetes 시스템 컴포넌트가 배포되는 예약된 네임스페이스다.

#### Pod

컨트롤 플레인 컴포넌트(Static Pod)와 kube-proxy(DaemonSet)는 `hostNetwork: true`로 호스트 네트워크를 사용하므로 `Running` 상태지만, CoreDNS(Deployment)는 Pod 네트워크가 필요하여 CNI 플러그인 없이는 IP를 할당받지 못해 `Pending` 상태다.

> CNI를 설치하면 노드가 Ready가 되고, CoreDNS도 Pod IP를 할당받아 Running 상태가 된다.

```bash
kubectl get pod -n kube-system -o wide
# NAME                              READY   STATUS    RESTARTS   AGE   IP               NODE      NOMINATED NODE   READINESS GATES
# coredns-668d6bf9bc-n8jxf          0/1     Pending   0          21m   <none>           <none>    <none>           <none>
# coredns-668d6bf9bc-z6h69          0/1     Pending   0          21m   <none>           <none>    <none>           <none>
# etcd-k8s-ctr                      1/1     Running   0          21m   192.168.10.100   k8s-ctr   <none>           <none>
# kube-apiserver-k8s-ctr            1/1     Running   0          21m   192.168.10.100   k8s-ctr   <none>           <none>
# kube-controller-manager-k8s-ctr   1/1     Running   0          21m   192.168.10.100   k8s-ctr   <none>           <none>
# kube-proxy-5p6jx                  1/1     Running   0          21m   192.168.10.100   k8s-ctr   <none>           <none>
# kube-scheduler-k8s-ctr            1/1     Running   0          21m   192.168.10.100   k8s-ctr   <none>           <none>
```

| Pod | 유형 | 상태 | 설명 |
| --- | --- | --- | --- |
| `etcd-k8s-ctr` | Static Pod | Running | 클러스터 데이터 저장소 |
| `kube-apiserver-k8s-ctr` | Static Pod | Running | API Server |
| `kube-controller-manager-k8s-ctr` | Static Pod | Running | 컨트롤러 매니저 |
| `kube-scheduler-k8s-ctr` | Static Pod | Running | 스케줄러 |
| `kube-proxy-5p6jx` | DaemonSet | Running | 네트워크 프록시 |
| `coredns-*` | Deployment | **Pending** | CNI 없어서 스케줄링 불가 |


#### Service

kubeadm 초기화 직후에는 `kube-dns` 서비스만 존재한다. CoreDNS **Pod**이지만 서비스명은 **`kube-dns`**인데, 이는 기존 kube-dns와의 호환성을 위한 것이다. Pod 내부에서 DNS 조회 시 `/etc/resolv.conf`에 `nameserver 10.96.0.10`이 설정된다.

```bash
kubectl get svc -n kube-system
# NAME       TYPE        CLUSTER-IP   EXTERNAL-IP   PORT(S)                  AGE
# kube-dns   ClusterIP   10.96.0.10   <none>        53/UDP,53/TCP,9153/TCP   22m
```

<br>

## TLS Bootstrap을 위한 객체들

`kubeadm init`은 워커 노드가 클러스터에 join할 수 있도록 **부트스트랩 인프라**를 자동으로 구성한다. 해당 인프라는 아직 클러스터 인증서가 없는 노드(worker) 가 (kubeadm join 전) API Server에 처음 접속해서 최소 정보(엔드포인트 + CA)를 얻기 위해 필요하다. 

각 객체들은 아래와 같다.

| 객체 | 이름 | 용도 |
| --- | --- | --- |
| **Namespace** | `kube-public` | 공개 리소스 저장용 네임스페이스 |
| **ConfigMap** | `cluster-info` | API Server 엔드포인트 + CA 인증서 |
| **Role** | `kubeadm:bootstrap-signer-clusterinfo` | `cluster-info` 읽기 권한 정의 |
| **RoleBinding** | `kubeadm:bootstrap-signer-clusterinfo` | `system:unauthenticated` 그룹에 Role 부여 |

### cluster-info ConfigMap

`cluster-info` ConfigMap은 워커 노드가 클러스터에 join할 때 필요한 **부트스트랩 데이터**(API Server 주소 + CA 인증서)를 담고 있다. Role/RoleBinding은 **인증되지 않은 사용자**(`system:unauthenticated`)도 이 ConfigMap을 읽을 수 있도록 권한을 부여한다.


```
워커 노드 (인증서 없음)
    │
    ▼ curl -k https://API_SERVER/api/v1/namespaces/kube-public/configmaps/cluster-info
    │
    ▼ cluster-info에서 CA 인증서 + API Server 주소 획득
    │
    ▼ 부트스트랩 토큰으로 인증 → CSR 제출 → 인증서 발급
    │
    ▼ 정식 kubelet 인증서로 클러스터 참여
```

> 자세한 TLS Bootstrap 과정은 [워커 노드 join]({% post_url 2026-01-18-Kubernetes-Kubeadm-01-5 %}) 글에서 다룬다.

### Role/RoleBinding 확인

`cluster-info`가 인증 없이 접근 가능한 이유는 RBAC 설정 때문이다.

```bash
kubectl -n kube-public get role,rolebinding
# NAME                                               CREATED AT
# role.rbac.../kubeadm:bootstrap-signer-clusterinfo  2026-01-23T10:41:10Z
# role.rbac.../system:controller:bootstrap-signer    2026-01-23T10:41:10Z
# NAME                                                      ROLE                                        AGE
# rolebinding.../kubeadm:bootstrap-signer-clusterinfo       Role/kubeadm:bootstrap-signer-clusterinfo   25m
# rolebinding.../system:controller:bootstrap-signer         Role/system:controller:bootstrap-signer     25m
```

`kubeadm:bootstrap-signer-clusterinfo` RoleBinding이 `system:unauthenticated` 그룹(= 인증서 없는 누구나)에게 `cluster-info` ConfigMap 읽기 권한을 부여한다.

> **보안 참고**: `cluster-info`에는 CA 인증서만 포함되어 있고, 개인키나 인증 토큰은 없다. CA 인증서는 공개되어도 안전하며, 오히려 클라이언트가 API Server를 검증하는 데 필요하다.

### 인증 없이 접근 가능 확인

RoleBinding 덕분에 `cluster-info`는 Kubernetes API 리소스 중 **유일하게 인증 없이 접근 가능**하다.

```bash
curl -s -k https://192.168.10.100:6443/api/v1/namespaces/kube-public/configmaps/cluster-info | jq '.data | keys'
# [
#   "jws-kubeconfig-123456",
#   "kubeconfig"
# ]
```

반면 다른 리소스는 인증 없이 접근하면 `403 Forbidden` 에러가 발생한다.

```bash
curl -s -k https://192.168.10.100:6443/api/v1/namespaces/default/pods | jq '.message'
# "pods is forbidden: User \"system:anonymous\" cannot list resource \"pods\" in API group \"\" in the namespace \"default\""
```

### ConfigMap 내용 확인

```bash
kubectl -n kube-public get configmap cluster-info
# NAME           DATA   AGE
# cluster-info   2      24m
```

ConfigMap에는 2개의 데이터가 있다:

- **kubeconfig**: API Server 주소와 CA 인증서 (워커 노드가 필요한 정보)
- **jws-kubeconfig-123456**: 부트스트랩 토큰으로 서명한 값 (중간자가 ConfigMap을 조작하지 않았음을 검증)

<details>
<summary>cluster-info ConfigMap 전체 내용</summary>

```yaml
apiVersion: v1
data:
  jws-kubeconfig-123456: eyJhbGciOiJIUzI1NiIsImtpZCI6IjEyMzQ1NiJ9..xAk3Y-C21V53bEt0Yh96uKkWfuycbM-piDu6Kqr4RKs
  kubeconfig: |
    apiVersion: v1
    clusters:
    - cluster:
        certificate-authority-data: LS0tLS1CRUdJTi...  # CA 인증서 (Base64)
        server: https://192.168.10.100:6443
      name: ""
    contexts: null
    current-context: ""
    kind: Config
    preferences: {}
    users: null
kind: ConfigMap
metadata:
  name: cluster-info
  namespace: kube-public
```

</details>

### CA 인증서 확인

```bash
kubectl -n kube-public get configmap cluster-info -o jsonpath='{.data.kubeconfig}' | \
  grep certificate-authority-data | cut -d ':' -f2 | tr -d ' ' | base64 -d | openssl x509 -text -noout
# Certificate:
#     Data:
#         Issuer: CN=kubernetes
#         Validity
#             Not Before: Jan 23 10:36:04 2026 GMT
#             Not After : Jan 21 10:41:04 2036 GMT      # 10년 유효
#         Subject: CN=kubernetes
#         X509v3 Basic Constraints: critical
#             CA:TRUE                                   # CA 인증서임
#         X509v3 Subject Alternative Name:
#             DNS:kubernetes
```

이 CA 인증서는 `/etc/kubernetes/pki/ca.crt`와 동일하며, 워커 노드가 API Server의 인증서를 검증할 때 사용한다.

<br>

# 편의성 설정

클러스터 관리를 위한 도구들을 설치한다.

## kubectl 자동 완성

```bash
# 현재 세션에 즉시 적용
source <(kubectl completion bash)   # kubectl 자동 완성
source <(kubeadm completion bash)   # kubeadm 자동 완성

# 영구 설정 (다음 로그인부터 자동 적용)
echo 'source <(kubectl completion bash)' >> /etc/profile   # kubectl
echo 'source <(kubeadm completion bash)' >> /etc/profile   # kubeadm

# kubectl을 k로 alias
alias k=kubectl
complete -o default -F __start_kubectl k   # k에도 자동 완성 적용
echo 'alias k=kubectl' >> /etc/profile
echo 'complete -o default -F __start_kubectl k' >> /etc/profile

# 테스트
k get node
# NAME      STATUS     ROLES           AGE   VERSION
# k8s-ctr   NotReady   control-plane   27m   v1.32.11
```

이제 `k`만 입력해도 `kubectl`처럼 동작하고, Tab 자동 완성도 사용할 수 있다.

<br>

## kubecolor 설치

kubectl 출력을 컬러로 표시해주는 도구다.

```bash
# kubecolor 설치
dnf install -y 'dnf-command(config-manager)'   # config-manager 플러그인 설치
dnf config-manager --add-repo https://kubecolor.github.io/packages/rpm/kubecolor.repo   # 저장소 추가
dnf install -y kubecolor

# 테스트 (출력이 컬러로 표시됨)
kubecolor get node
kubecolor describe node

# alias 설정 (kc로 짧게 사용)
alias kc=kubecolor
echo 'alias kc=kubecolor' >> /etc/profile
```

![kubecolor-result]({{site.url}}/assets/images/kubecolor-result.png){: .align-center}


<br>

## kubectx, kubens 설치

context와 namespace를 쉽게 전환할 수 있는 도구다.
- **kubectx**: 여러 클러스터(context) 간 전환
- **kubens**: 네임스페이스 간 전환

```bash
# 설치
dnf install -y git
git clone https://github.com/ahmetb/kubectx /opt/kubectx
ln -s /opt/kubectx/kubectx /usr/local/bin/kubectx   # context 전환 도구
ln -s /opt/kubectx/kubens /usr/local/bin/kubens     # namespace 전환 도구

# 테스트
kubens                  # 네임스페이스 목록 (현재 선택된 것 하이라이트)
kubens kube-system      # kube-system으로 전환
kubectl get pod         # -n 옵션 없이도 kube-system의 Pod 조회
kubens default          # 다시 default로 복귀

kubectx                 # context 목록 (현재는 1개뿐)
```

<br>

## kube-ps1 설치

bash 프롬프트에 현재 context와 namespace를 표시한다.

```bash
# kube-ps1 설치
git clone https://github.com/jonmosco/kube-ps1.git /root/kube-ps1

# bash_profile 설정
cat << "EOT" >> /root/.bash_profile
source /root/kube-ps1/kube-ps1.sh
KUBE_PS1_SYMBOL_ENABLE=true
function get_cluster_short() {
  echo "$1" | cut -d . -f1
}
KUBE_PS1_CLUSTER_FUNCTION=get_cluster_short
KUBE_PS1_SUFFIX=') '
PS1='$(kube_ps1)'$PS1
EOT

# 자동 root 전환 설정 (Vagrant용)
echo "sudo su -" >> /home/vagrant/.bashrc
```
![kubeps1-result]({{site.url}}/assets/images/kubeps1-result.png){: .align-center}

<br>

## Helm 설치

Kubernetes 패키지 관리 도구다.

```bash
# Helm 3 설치 (버전 지정)
curl -fsSL https://raw.githubusercontent.com/helm/helm/main/scripts/get-helm-3 | DESIRED_VERSION=v3.18.6 bash
# Downloading https://get.helm.sh/helm-v3.18.6-linux-arm64.tar.gz
# Verifying checksum... Done.
# Preparing to install helm into /usr/local/bin
# helm installed into /usr/local/bin/helm

# 버전 확인
helm version
# version.BuildInfo{Version:"v3.18.6", GitCommit:"b76a950f6835474e0906b96c9ec68a2eff3a6430", GitTreeState:"clean", GoVersion:"go1.24.6"}
```

<br>

## k9s 설치

터미널 기반 Kubernetes 대시보드다.

```bash
# k9s 설치
CLI_ARCH=amd64
if [ "$(uname -m)" = "aarch64" ]; then CLI_ARCH=arm64; fi
wget https://github.com/derailed/k9s/releases/latest/download/k9s_linux_${CLI_ARCH}.tar.gz
tar -xzf k9s_linux_*.tar.gz
chown root:root k9s
mv k9s /usr/local/bin/
chmod +x /usr/local/bin/k9s

# 실행 테스트
k9s
# 종료: Ctrl+C 또는 :q
```

![k9s-result]({{site.url}}/assets/images/k9s-result.png){: .align-center}


<br>

## 설정 적용

```bash
# 셸 재시작하여 /etc/profile 설정 적용
exit   # root -> vagrant
exit   # vagrant -> host

# 다시 접속 (vagrant 로그인 시 자동으로 root 전환됨)
vagrant ssh k8s-ctr

# context 이름 변경 (선택, 기본 이름이 너무 길어서)
kubectl config rename-context "kubernetes-admin@kubernetes" "HomeLab"
# Context "kubernetes-admin@kubernetes" renamed to "HomeLab".

kubens default   # 기본 네임스페이스 확인
```
![k-result.png]({{site.url}}/assets/images/k-result.png){: .align-center}

<br>

# 결과

이 단계를 완료하면 다음과 같은 결과를 얻을 수 있다:

| 항목 | 결과 |
| --- | --- |
| 컨트롤 플레인 | kube-apiserver, kube-controller-manager, kube-scheduler, etcd 실행 중 |
| 인증서 | /etc/kubernetes/pki에 모든 인증서 생성됨 |
| kubeconfig | admin.conf, controller-manager.conf, scheduler.conf, kubelet.conf 생성됨 |
| 노드 상태 | **NotReady** (CNI 플러그인 미설치) |
| CoreDNS 상태 | **Pending** (CNI 플러그인 미설치) |
| 편의 도구 | kubecolor, kubectx, kubens, kube-ps1, helm, k9s 설치됨 |

> **다음 단계**: 노드가 NotReady이고 CoreDNS가 Pending인 상태다. 이는 CNI 플러그인이 없어서 Pod 네트워크를 구성할 수 없기 때문이다. [다음 글]({% post_url 2026-01-18-Kubernetes-Kubeadm-01-4 %})에서 Flannel CNI를 설치하고, 생성된 컴포넌트들을 상세히 확인한다.
