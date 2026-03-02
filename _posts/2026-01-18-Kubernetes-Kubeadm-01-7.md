---
title:  "[Kubernetes] Cluster: Kubeadm을 이용해 클러스터 구성하기 - 1.7. Static Pod 및 애드온 확인"
excerpt: "kubeadm init으로 배포된 Static Pod(etcd, API Server, Scheduler, Controller Manager)와 필수 애드온(CoreDNS, kube-proxy)을 상세히 확인해보자."
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

- **Static Pod**: etcd, kube-apiserver, kube-scheduler, kube-controller-manager가 `/etc/kubernetes/manifests`의 YAML 매니페스트로 실행됨
- **CoreDNS**: 클러스터 내부 DNS 서비스. Deployment로 2개 Pod 운영, `kube-dns` Service(`10.96.0.10`)로 접근
- **kube-proxy**: 각 노드에서 iptables 규칙으로 Service → Pod 라우팅 관리. DaemonSet으로 모든 노드에 배포

<br>

# 들어가며

[이전 글]({% post_url 2026-01-18-Kubernetes-Kubeadm-01-6 %})에서 노드 정보, 인증서, kubeconfig를 확인했다. 이번 글에서는 컨트롤 플레인의 핵심인 Static Pod와 필수 애드온을 상세히 확인한다.

<br>

# Static Pod 확인

## Static Pod 매니페스트 디렉토리

컨트롤 플레인 컴포넌트들은 **Static Pod**로 실행된다. kubelet이 특정 디렉토리를 감시하고, 그 안의 YAML 파일을 읽어 Pod를 직접 생성한다. API Server 없이도 컨트롤 플레인을 부트스트랩할 수 있는 핵심 메커니즘이다.

> **참고**: Control Plane을 systemd vs Static Pod로 구성하는 방식의 차이와, 그 때문에 Control Plane에도 kubelet이 필요한 이유는 [Overview의 Control Plane 구성: systemd vs Static Pod]({% post_url 2026-01-18-Kubernetes-Kubeadm-00 %}#control-plane-구성-systemd-vs-static-pod)를 참고하자.

```bash
tree /etc/kubernetes/manifests/
# /etc/kubernetes/manifests/
# ├── etcd.yaml
# ├── kube-apiserver.yaml
# ├── kube-controller-manager.yaml
# └── kube-scheduler.yaml
#
# 1 directory, 4 files
```

[이전 글에서 확인한]({% post_url 2026-01-18-Kubernetes-Kubeadm-01-6 %}#kubelet-상태-및-설정-확인) `staticPodPath: /etc/kubernetes/manifests` 설정에 의해 kubelet이 이 디렉토리를 감시하고, 각 YAML 파일을 Static Pod로 실행한다.

<br>

## etcd

etcd는 Kubernetes **모든 클러스터 상태**를 저장하는 분산 키-값 저장소다.

```bash
# 주요 설정 확인
cat /etc/kubernetes/manifests/etcd.yaml | grep -E 'listen-|advertise-|data-dir'
# - --advertise-client-urls=https://192.168.10.100:2379
# - --data-dir=/var/lib/etcd
# - --initial-advertise-peer-urls=https://192.168.10.100:2380
# - --listen-client-urls=https://127.0.0.1:2379,https://192.168.10.100:2379
# - --listen-metrics-urls=http://127.0.0.1:2381
# - --listen-peer-urls=https://192.168.10.100:2380
```

| 항목 | 값 | 설명 |
| --- | --- | --- |
| **포트** | `2379` | 클라이언트 요청 (API Server → etcd) |
| | `2380` | 피어 통신 (etcd 노드 간, HA 구성 시) |
| | `2381` | 메트릭/헬스체크 (HTTP, TLS 없음) |
| **hostNetwork** | `true` | Pod 네트워크가 아닌 호스트 네트워크 사용 |
| **priorityClassName** | `system-node-critical` | 리소스 부족 시에도 최우선 스케줄링 |
| **client-cert-auth** | `true` | 클라이언트 인증서 필수 (API Server만 접근 가능) |

```bash
# 주요 설정 확인
cat /etc/kubernetes/manifests/etcd.yaml | grep -E 'listen-|advertise-|data-dir'
# - --advertise-client-urls=https://192.168.10.100:2379
# - --data-dir=/var/lib/etcd
# - --initial-advertise-peer-urls=https://192.168.10.100:2380
# - --listen-client-urls=https://127.0.0.1:2379,https://192.168.10.100:2379
# - --listen-metrics-urls=http://127.0.0.1:2381
# - --listen-peer-urls=https://192.168.10.100:2380
```

- **`listen-client-urls`**: `127.0.0.1:2379`와 `192.168.10.100:2379` 모두에서 수신. 로컬과 네트워크 모두 접근 허용
- **`listen-peer-urls`**: `192.168.10.100:2380`에서만 수신. HA 구성 시 다른 etcd 노드가 이 주소로 연결
- **`listen-metrics-urls`**: `127.0.0.1:2381` (HTTP). 메트릭은 로컬에서만, TLS 없이 수집

<br>

<details markdown="1">
<summary>etcd.yaml 전체 보기</summary>

```yaml
apiVersion: v1
kind: Pod
metadata:
  annotations:
    kubeadm.kubernetes.io/etcd.advertise-client-urls: https://192.168.10.100:2379
  labels:
    component: etcd
    tier: control-plane
  name: etcd
  namespace: kube-system
spec:
  containers:
  - command:
    - etcd
    - --advertise-client-urls=https://192.168.10.100:2379
    - --cert-file=/etc/kubernetes/pki/etcd/server.crt
    - --client-cert-auth=true
    - --data-dir=/var/lib/etcd
    - --experimental-initial-corrupt-check=true
    - --experimental-watch-progress-notify-interval=5s
    - --initial-advertise-peer-urls=https://192.168.10.100:2380
    - --initial-cluster=k8s-ctr=https://192.168.10.100:2380
    - --key-file=/etc/kubernetes/pki/etcd/server.key
    - --listen-client-urls=https://127.0.0.1:2379,https://192.168.10.100:2379 # client는 https://192.168.10.100:2379 호출
    - --listen-metrics-urls=http://127.0.0.1:2381
    - --listen-peer-urls=https://192.168.10.100:2380
    - --name=k8s-ctr
    - --peer-cert-file=/etc/kubernetes/pki/etcd/peer.crt
    - --peer-client-cert-auth=true
    - --peer-key-file=/etc/kubernetes/pki/etcd/peer.key
    - --peer-trusted-ca-file=/etc/kubernetes/pki/etcd/ca.crt
    - --snapshot-count=10000
    - --trusted-ca-file=/etc/kubernetes/pki/etcd/ca.crt
    image: registry.k8s.io/etcd:3.5.24-0
    livenessProbe:
      httpGet:
        host: 127.0.0.1
        path: /livez
        port: 2381
        scheme: HTTP
    volumeMounts:
    - mountPath: /var/lib/etcd
      name: etcd-data
    - mountPath: /etc/kubernetes/pki/etcd
      name: etcd-certs
  hostNetwork: true
  priorityClassName: system-node-critical
  volumes:
  - hostPath:
      path: /etc/kubernetes/pki/etcd
    name: etcd-certs
  - hostPath:
      path: /var/lib/etcd
    name: etcd-data
```

</details>

<br>

### etcd 데이터 디렉토리

etcd에는 Pod, Service, ConfigMap, Secret 등 모든 리소스 정보가 저장된다. etcd 데이터가 손실되면 클러스터 전체를 잃게 되므로, **백업이 필수**다.

```bash
tree /var/lib/etcd/
# /var/lib/etcd/
# └── member
#     ├── snap
#     │   └── db              ← 실제 데이터베이스 (BoltDB)
#     └── wal
#         ├── 0000000000000000-0000000000000000.wal   ← Write-Ahead Log
#         └── 0.tmp
```

| 디렉토리/파일 | 설명 |
| --- | --- |
| `member/snap/` | 주기적으로 생성되는 스냅샷. 장애 복구 시 이 시점부터 WAL 재생 |
| `member/snap/db` | **실제 데이터베이스 파일** (BoltDB 형식). 모든 Kubernetes 리소스가 여기에 저장됨 |
| `member/wal/` | **Write-Ahead Log**. 변경사항이 먼저 WAL에 기록된 후 db에 반영됨. 장애 복구에 사용 |

> **백업 팁**: etcd 백업 시 `etcdctl snapshot save` 명령을 사용하거나, `/var/lib/etcd` 디렉토리 전체를 복사한다. 프로덕션에서는 정기적인 스냅샷 백업이 필수다.

<br>

## kube-apiserver

API Server는 Kubernetes 클러스터의 중앙 허브로, 모든 컴포넌트와 사용자 요청이 이곳을 통해 처리된다.

```bash
# API Server 포트 확인
ss -tnlp | grep apiserver
# LISTEN 0      4096                *:6443             *:*    users:(("kube-apiserver",pid=15952,fd=3))

# kubernetes Service 확인 (클러스터 내부에서 API Server 접근용)
kubectl get svc,ep
# NAME                 TYPE        CLUSTER-IP   EXTERNAL-IP   PORT(S)   AGE
# service/kubernetes   ClusterIP   10.96.0.1    <none>        443/TCP   138m
#
# NAME                   ENDPOINTS             AGE
# endpoints/kubernetes   192.168.10.100:6443   138m
```

| 항목 | 값 | 설명 |
| --- | --- | --- |
| **리스닝 포트** | `6443` | 모든 인터페이스(`*`)에서 수신 |
| **Service ClusterIP** | `10.96.0.1` | Pod 내부에서 `https://kubernetes.default.svc:443`으로 접근 시 사용 |
| **Endpoints** | `192.168.10.100:6443` | 실제 API Server 주소 |

Pod 내부에서 API Server에 접근할 때는 `kubernetes.default.svc` DNS를 사용하고, 이는 `10.96.0.1:443`으로 해석된 후 `192.168.10.100:6443`으로 라우팅된다.

<br>

<details markdown="1">
<summary>kube-apiserver.yaml 전체 보기</summary>

```yaml
apiVersion: v1
kind: Pod
metadata:
  annotations:
    kubeadm.kubernetes.io/kube-apiserver.advertise-address.endpoint: 192.168.10.100:6443
  creationTimestamp: null
  labels:
    component: kube-apiserver
    tier: control-plane
  name: kube-apiserver
  namespace: kube-system
spec:
  containers:
  - command:
    - kube-apiserver
    - --advertise-address=192.168.10.100
    - --allow-privileged=true
    - --authorization-mode=Node,RBAC
    - --client-ca-file=/etc/kubernetes/pki/ca.crt
    - --enable-admission-plugins=NodeRestriction
    - --enable-bootstrap-token-auth=true
    - --etcd-cafile=/etc/kubernetes/pki/etcd/ca.crt
    - --etcd-certfile=/etc/kubernetes/pki/apiserver-etcd-client.crt
    - --etcd-keyfile=/etc/kubernetes/pki/apiserver-etcd-client.key
    - --etcd-servers=https://127.0.0.1:2379
    - --kubelet-client-certificate=/etc/kubernetes/pki/apiserver-kubelet-client.crt
    - --kubelet-client-key=/etc/kubernetes/pki/apiserver-kubelet-client.key
    - --kubelet-preferred-address-types=InternalIP,ExternalIP,Hostname
    - --proxy-client-cert-file=/etc/kubernetes/pki/front-proxy-client.crt
    - --proxy-client-key-file=/etc/kubernetes/pki/front-proxy-client.key
    - --requestheader-allowed-names=front-proxy-client
    - --requestheader-client-ca-file=/etc/kubernetes/pki/front-proxy-ca.crt
    - --requestheader-extra-headers-prefix=X-Remote-Extra-
    - --requestheader-group-headers=X-Remote-Group
    - --requestheader-username-headers=X-Remote-User
    - --secure-port=6443
    - --service-account-issuer=https://kubernetes.default.svc.cluster.local
    - --service-account-key-file=/etc/kubernetes/pki/sa.pub
    - --service-account-signing-key-file=/etc/kubernetes/pki/sa.key
    - --service-cluster-ip-range=10.96.0.0/16
    - --tls-cert-file=/etc/kubernetes/pki/apiserver.crt
    - --tls-private-key-file=/etc/kubernetes/pki/apiserver.key
    image: registry.k8s.io/kube-apiserver:v1.32.11
    imagePullPolicy: IfNotPresent
    livenessProbe:
      failureThreshold: 8
      httpGet:
        host: 192.168.10.100
        path: /livez
        port: 6443
        scheme: HTTPS
      initialDelaySeconds: 10
      periodSeconds: 10
      timeoutSeconds: 15
    name: kube-apiserver
    readinessProbe:
      failureThreshold: 3
      httpGet:
        host: 192.168.10.100
        path: /readyz
        port: 6443
        scheme: HTTPS
      periodSeconds: 1
      timeoutSeconds: 15
    resources:
      requests:
        cpu: 250m
    startupProbe:
      failureThreshold: 24
      httpGet:
        host: 192.168.10.100
        path: /livez
        port: 6443
        scheme: HTTPS
      initialDelaySeconds: 10
      periodSeconds: 10
      timeoutSeconds: 15
    volumeMounts:
    - mountPath: /etc/ssl/certs
      name: ca-certs
      readOnly: true
    - mountPath: /etc/pki/ca-trust
      name: etc-pki-ca-trust
      readOnly: true
    - mountPath: /etc/pki/tls/certs
      name: etc-pki-tls-certs
      readOnly: true
    - mountPath: /etc/kubernetes/pki
      name: k8s-certs
      readOnly: true
  hostNetwork: true
  priority: 2000001000
  priorityClassName: system-node-critical
  securityContext:
    seccompProfile:
      type: RuntimeDefault
  volumes:
  - hostPath:
      path: /etc/ssl/certs
      type: DirectoryOrCreate
    name: ca-certs
  - hostPath:
      path: /etc/pki/ca-trust
      type: DirectoryOrCreate
    name: etc-pki-ca-trust
  - hostPath:
      path: /etc/pki/tls/certs
      type: DirectoryOrCreate
    name: etc-pki-tls-certs
  - hostPath:
      path: /etc/kubernetes/pki
      type: DirectoryOrCreate
    name: k8s-certs
status: {}
```

</details>

<br>

## kube-scheduler

스케줄러는 새로 생성된 Pod를 어떤 노드에 배치할지 결정하는 컴포넌트다. HA 구성에서는 여러 스케줄러 인스턴스가 실행되지만, **한 번에 하나만 활성화**(Leader)되어 스케줄링 충돌을 방지한다.

```bash
# scheduler 포트 확인
ss -nltp | grep scheduler
# LISTEN 0      4096        127.0.0.1:10259      0.0.0.0:*    users:(("kube-scheduler",pid=15945,fd=3))

# Leader Election 확인 (Lease 리소스)
kubectl get leases.coordination.k8s.io -n kube-system kube-scheduler
# NAME             HOLDER                                         AGE
# kube-scheduler   k8s-ctr_1c1836c2-c546-4dcf-8759-3368587749a8   139m
```

| 항목 | 값 | 설명 |
| --- | --- | --- |
| **리스닝 주소** | `127.0.0.1:10259` | 로컬에서만 접근 가능 (보안) |
| **Leader** | `k8s-ctr_...` | 현재 이 노드의 스케줄러가 Leader |

<details markdown="1">
<summary>kube-scheduler.yaml 전체 보기</summary>

```yaml
apiVersion: v1
kind: Pod
metadata:
  creationTimestamp: null
  labels:
    component: kube-scheduler
    tier: control-plane
  name: kube-scheduler
  namespace: kube-system
spec:
  containers:
  - command:
    - kube-scheduler
    - --authentication-kubeconfig=/etc/kubernetes/scheduler.conf
    - --authorization-kubeconfig=/etc/kubernetes/scheduler.conf
    - --bind-address=127.0.0.1
    - --kubeconfig=/etc/kubernetes/scheduler.conf
    - --leader-elect=true
    image: registry.k8s.io/kube-scheduler:v1.32.11
    imagePullPolicy: IfNotPresent
    livenessProbe:
      failureThreshold: 8
      httpGet:
        host: 127.0.0.1
        path: /livez
        port: 10259
        scheme: HTTPS
      initialDelaySeconds: 10
      periodSeconds: 10
      timeoutSeconds: 15
    name: kube-scheduler
    readinessProbe:
      failureThreshold: 3
      httpGet:
        host: 127.0.0.1
        path: /readyz
        port: 10259
        scheme: HTTPS
      periodSeconds: 1
      timeoutSeconds: 15
    resources:
      requests:
        cpu: 100m
    startupProbe:
      failureThreshold: 24
      httpGet:
        host: 127.0.0.1
        path: /livez
        port: 10259
        scheme: HTTPS
      initialDelaySeconds: 10
      periodSeconds: 10
      timeoutSeconds: 15
    volumeMounts:
    - mountPath: /etc/kubernetes/scheduler.conf
      name: kubeconfig
      readOnly: true
  hostNetwork: true
  priority: 2000001000
  priorityClassName: system-node-critical
  securityContext:
    seccompProfile:
      type: RuntimeDefault
  volumes:
  - hostPath:
      path: /etc/kubernetes/scheduler.conf
      type: FileOrCreate
    name: kubeconfig
status: {}
```
</details>


### Leader Election 상세 확인

[이전 글]({% post_url 2026-01-18-Kubernetes-Kubeadm-01-4 %}#lease)에서 Lease 리소스가 Leader Election과 Node Heartbeat에 사용된다고 설명했다. Lease의 상세 정보를 확인하면 Leader Election 동작 방식을 이해할 수 있다.

> 현재 단일 컨트롤 플레인 구성이지만, `--leader-elect=true` 옵션이 기본 활성화되어 있어 HA 확장 시 별도 설정 없이 Leader Election이 작동할 수 있다.

```bash
kubectl get lease -n kube-system kube-scheduler -o yaml
# spec:
#   acquireTime: "2026-01-23T10:41:13.349875Z"                     # Leader 획득 시간
#   holderIdentity: k8s-ctr_1c1836c2-c546-4dcf-8759-3368587749a8  # 현재 Leader
#   leaseDurationSeconds: 15                                       # 15초 내 갱신 없으면 만료
#   leaseTransitions: 0                                            # Leader 변경 횟수
#   renewTime: "2026-01-24T15:23:19.653612Z"                       # 마지막 갱신 시간
```

| 필드 | 설명 |
| --- | --- |
| `holderIdentity` | 현재 Leader (노드명_UUID 형식) |
| `leaseDurationSeconds` | 이 시간 내 갱신 없으면 Leader 상실 |
| `renewTime` | Leader가 주기적으로 갱신하는 시간 |
| `leaseTransitions` | Leader가 변경된 횟수 (HA 환경에서 failover 발생 시 증가) |

> **참고**: HA 구성에서 여러 인스턴스가 실행되면, 각 인스턴스가 `holderIdentity`를 자신으로 설정하려고 경쟁한다. 먼저 설정에 성공한 인스턴스가 Leader가 되어 실제 작업을 수행하고, 나머지는 대기한다. Leader가 `leaseDurationSeconds` 내에 갱신하지 못하면 다른 인스턴스가 Leader를 획득한다.

<br>

## kube-controller-manager

Controller Manager는 클러스터 상태를 원하는 상태로 유지하는 **여러 컨트롤러의 집합체**다. Deployment, ReplicaSet, Node, Service 등 각 리소스 유형별로 전담 컨트롤러가 있다.


```bash
cat /etc/kubernetes/manifests/kube-controller-manager.yaml | grep -E '^\s+- --'
#     - --allocate-node-cidrs=true
#     - --authentication-kubeconfig=/etc/kubernetes/controller-manager.conf
#     - --authorization-kubeconfig=/etc/kubernetes/controller-manager.conf
#     - --bind-address=127.0.0.1
#     - --cluster-cidr=10.244.0.0/16
#     - --cluster-signing-cert-file=/etc/kubernetes/pki/ca.crt
#     - --cluster-signing-key-file=/etc/kubernetes/pki/ca.key
#     - --controllers=*,bootstrapsigner,tokencleaner
#     - --kubeconfig=/etc/kubernetes/controller-manager.conf
#     - --leader-elect=true
#     - --service-cluster-ip-range=10.96.0.0/16
#     - --use-service-account-credentials=true
```

| 옵션 | 설명 |
| --- | --- |
| `--allocate-node-cidrs=true` | 각 노드에 Pod CIDR(`/24`) 자동 할당 |
| `--authentication-kubeconfig`, `--authorization-kubeconfig` | API Server에 인증/인가 요청 시 사용하는 [kubeconfig]({% post_url 2026-01-18-Kubernetes-Kubeadm-01-6 %}#controller-managerconf) |
| `--bind-address=127.0.0.1` | 로컬에서만 접근 가능 (보안) |
| `--cluster-cidr=10.244.0.0/16` | Pod 네트워크 대역 (kubeadm 설정의 `podSubnet`) |
| `--cluster-signing-cert-file`, `--cluster-signing-key-file` | CSR 서명용 CA. kubelet 클라이언트 인증서 갱신(`rotateCertificates`) 시 자동 적용 |
| `--controllers=*,bootstrapsigner,tokencleaner` | 모든 기본 컨트롤러 + 부트스트랩 관련 컨트롤러 활성화 |
| `--kubeconfig` | API Server 접속에 사용하는 kubeconfig (`controller-manager.conf`) |
| `--leader-elect=true` | HA 환경에서 Leader Election 활성화 |
| `--service-cluster-ip-range=10.96.0.0/16` | Service CIDR (kubeadm 설정의 `serviceSubnet`) |
| `--use-service-account-credentials=true` | 각 컨트롤러가 **개별 ServiceAccount**로 API Server에 인증 (보안 강화) |

```bash
# controller-manager 포트 확인
ss -tnlp | grep controller
# LISTEN 0      4096        127.0.0.1:10257      0.0.0.0:*    users:(("kube-controller",pid=15758,fd=3))

# Leader Election 확인 (scheduler와 동일하게 Lease 사용)
kubectl get lease -n kube-system kube-controller-manager
# NAME                      HOLDER                                         AGE
# kube-controller-manager   k8s-ctr_5de52747-b49e-4b78-8424-ba461a604868   146m
```

| 항목 | 값 | 설명 |
| --- | --- | --- |
| **리스닝 주소** | `127.0.0.1:10257` | 로컬에서만 접근 가능 (보안) |
| **Leader** | `k8s-ctr_...` | 현재 이 노드의 컨트롤러 매니저가 Leader |

<br>

<details markdown="1">
<summary>kube-controller-manager.yaml 전체 보기</summary>
```yaml
apiVersion: v1
kind: Pod
metadata:
  creationTimestamp: null
  labels:
    component: kube-controller-manager
    tier: control-plane
  name: kube-controller-manager
  namespace: kube-system
spec:
  containers:
  - command:
    - kube-controller-manager
    - --allocate-node-cidrs=true
    - --authentication-kubeconfig=/etc/kubernetes/controller-manager.conf
    - --authorization-kubeconfig=/etc/kubernetes/controller-manager.conf
    - --bind-address=127.0.0.1
    - --client-ca-file=/etc/kubernetes/pki/ca.crt
    - --cluster-cidr=10.244.0.0/16
    - --cluster-name=kubernetes
    - --cluster-signing-cert-file=/etc/kubernetes/pki/ca.crt
    - --cluster-signing-key-file=/etc/kubernetes/pki/ca.key
    - --controllers=*,bootstrapsigner,tokencleaner
    - --kubeconfig=/etc/kubernetes/controller-manager.conf
    - --leader-elect=true
    - --requestheader-client-ca-file=/etc/kubernetes/pki/front-proxy-ca.crt
    - --root-ca-file=/etc/kubernetes/pki/ca.crt
    - --service-account-private-key-file=/etc/kubernetes/pki/sa.key
    - --service-cluster-ip-range=10.96.0.0/16
    - --use-service-account-credentials=true
    image: registry.k8s.io/kube-controller-manager:v1.32.11
    imagePullPolicy: IfNotPresent
    livenessProbe:
      failureThreshold: 8
      httpGet:
        host: 127.0.0.1
        path: /healthz
        port: 10257
        scheme: HTTPS
      initialDelaySeconds: 10
      periodSeconds: 10
      timeoutSeconds: 15
    name: kube-controller-manager
    resources:
      requests:
        cpu: 200m
    startupProbe:
      failureThreshold: 24
      httpGet:
        host: 127.0.0.1
        path: /healthz
        port: 10257
        scheme: HTTPS
      initialDelaySeconds: 10
      periodSeconds: 10
      timeoutSeconds: 15
    volumeMounts:
    - mountPath: /etc/ssl/certs
      name: ca-certs
      readOnly: true
    - mountPath: /etc/pki/ca-trust
      name: etc-pki-ca-trust
      readOnly: true
    - mountPath: /etc/pki/tls/certs
      name: etc-pki-tls-certs
      readOnly: true
    - mountPath: /usr/libexec/kubernetes/kubelet-plugins/volume/exec
      name: flexvolume-dir
    - mountPath: /etc/kubernetes/pki
      name: k8s-certs
      readOnly: true
    - mountPath: /etc/kubernetes/controller-manager.conf
      name: kubeconfig
      readOnly: true
  hostNetwork: true
  priority: 2000001000
  priorityClassName: system-node-critical
  securityContext:
    seccompProfile:
      type: RuntimeDefault
  volumes:
  - hostPath:
      path: /etc/ssl/certs
      type: DirectoryOrCreate
    name: ca-certs
  - hostPath:
      path: /etc/pki/ca-trust
      type: DirectoryOrCreate
    name: etc-pki-ca-trust
  - hostPath:
      path: /etc/pki/tls/certs
      type: DirectoryOrCreate
    name: etc-pki-tls-certs
  - hostPath:
      path: /usr/libexec/kubernetes/kubelet-plugins/volume/exec
      type: DirectoryOrCreate
    name: flexvolume-dir
  - hostPath:
      path: /etc/kubernetes/pki
      type: DirectoryOrCreate
    name: k8s-certs
  - hostPath:
      path: /etc/kubernetes/controller-manager.conf
      type: FileOrCreate
    name: kubeconfig
status: {}
```
</details>


### 컨트롤러별 ServiceAccount

**ServiceAccount**는 Pod(또는 클러스터 내 프로세스)가 API Server에 접근할 때 사용하는 인증 수단이다. kube-controller-manager도 Pod로 실행되므로 ServiceAccount를 사용하여 API Server에 인증한다.

kubeadm은 kube-controller-manager Static Pod 생성 시 `--use-service-account-credentials=true` 옵션을 **기본 적용**한다. 이 옵션이 활성화되면 각 내부 컨트롤러(deployment-controller, replicaset-controller 등)가 **개별 ServiceAccount**를 사용하여, 하나의 컨트롤러가 침해되더라도 다른 리소스에 대한 접근이 제한된다.

```bash
# 옵션 확인
kubectl describe pod -n kube-system kube-controller-manager-k8s-ctr | grep credentials
#      --use-service-account-credentials=true
```

> **참고: Hard Way와의 비교**
>
> [Hard Way]({% post_url 2026-01-05-Kubernetes-Cluster-The-Hard-Way-08-2 %}#kube-controller-manager-설정)에서는 kube-controller-manager가 systemd 서비스로 실행되었기 때문에:
> - ServiceAccount가 아닌 단일 **kubeconfig (X.509 인증서)**로 API Server에 인증했다
> - 모든 내부 컨트롤러가 **같은 권한**을 공유했다
>
> kubeadm은 `--use-service-account-credentials=true`로 각 컨트롤러에 **최소 권한 원칙**을 적용한다.

```bash
# 컨트롤러별 ServiceAccount 확인
kubectl get sa -n kube-system | grep controller
# attachdetach-controller                       0         146m
# certificate-controller                        0         146m
# cronjob-controller                            0         146m
# daemon-set-controller                         0         146m
# deployment-controller                         0         146m
# endpoint-controller                           0         146m
# job-controller                                0         146m
# namespace-controller                          0         146m
# node-controller                               0         146m
# replicaset-controller                         0         146m
# replication-controller                        0         146m
# service-account-controller                    0         146m
# statefulset-controller                        0         146m
# ... (총 25개)
```

<br>

# 필수 애드온 확인

## CoreDNS

CoreDNS는 클러스터 내부 DNS 서비스를 제공한다. Pod가 Service 이름으로 통신할 때 CoreDNS가 해당 이름을 ClusterIP로 해석한다.

```bash
# CoreDNS Deployment 확인
kubectl get deploy -n kube-system coredns -owide
# NAME      READY   UP-TO-DATE   AVAILABLE   AGE    CONTAINERS   IMAGES                                    SELECTOR
# coredns   2/2     2            2           147m   coredns      registry.k8s.io/coredns/coredns:v1.11.3   k8s-app=kube-dns

# CoreDNS Pod 확인
kubectl get pod -n kube-system -l k8s-app=kube-dns -owide
# NAME                       READY   STATUS    RESTARTS   AGE    IP           NODE      NOMINATED NODE   READINESS GATES
# coredns-668d6bf9bc-n8jxf   1/1     Running   0          147m   10.244.0.3   k8s-ctr   <none>           <none>
# coredns-668d6bf9bc-z6h69   1/1     Running   0          147m   10.244.0.2   k8s-ctr   <none>           <none>

# CoreDNS Service (이름은 kube-dns로 레거시 호환)
kubectl get svc,ep -n kube-system
# NAME               TYPE        CLUSTER-IP   EXTERNAL-IP   PORT(S)                  AGE
# service/kube-dns   ClusterIP   10.96.0.10   <none>        53/UDP,53/TCP,9153/TCP   148m
#
# NAME                 ENDPOINTS                                               AGE
# endpoints/kube-dns   10.244.0.2:53,10.244.0.3:53,10.244.0.2:53 + 3 more...   148m
```

| 항목 | 설명 |
| --- | --- |
| **Deployment** | 2개의 Pod로 고가용성 제공 |
| **Service 이름** | `kube-dns` (kube-dns에서 CoreDNS로 전환됐지만 호환성 유지) |
| **ClusterIP** | `10.96.0.10` (Pod의 `/etc/resolv.conf`에 이 IP가 nameserver로 설정됨) |
| **포트** | `53/UDP,TCP` (DNS), `9153/TCP` (Prometheus 메트릭) |

> 참고: **`k8s-app` 라벨**
>
> `-l k8s-app=kube-dns`에서 `k8s-app`은 Kubernetes **시스템 컴포넌트**를 식별하는 관례적 라벨이다. 일반 애플리케이션에서 사용하는 `app` 라벨과 구분하기 위해 `k8s-app`을 사용한다.
>
> | 라벨 | 용도 | 예시 |
> | --- | --- | --- |
> | `app` | 일반 사용자 애플리케이션 | `app=nginx`, `app=my-api` |
> | `k8s-app` | Kubernetes 시스템 컴포넌트 | `k8s-app=kube-dns`, `k8s-app=kube-proxy` |
>
> `kubeadm`이 설치하는 CoreDNS, kube-proxy 등은 모두 `k8s-app` 라벨을 사용한다.

### 메트릭 엔드포인트 확인

```bash
# CoreDNS 메트릭 확인
curl -s http://10.96.0.10:9153/metrics | head
# # HELP coredns_build_info A metric with a constant '1' value labeled by version, revision, and goversion from which CoreDNS was built.
# # TYPE coredns_build_info gauge
# coredns_build_info{goversion="go1.21.11",revision="a6338e9",version="1.11.3"} 1
# # HELP coredns_cache_entries The number of elements in the cache.
# # TYPE coredns_cache_entries gauge
# coredns_cache_entries{server="dns://:53",type="denial",view="",zones="."} 1
# ...
```

### Corefile 설정 확인

Corefile은 CoreDNS 설정 파일이다. Corefile 설정을 확인해 보자.


```bash
# CoreDNS ConfigMap 확인
kc describe cm -n kube-system coredns
# Data
# ====
# Corefile:
# ----
# .:53 {
#     errors                                    # 에러 로깅
#     health { lameduck 5s }                    # 헬스체크 (/health)
#     ready                                     # 준비 상태 체크 (/ready)
#     kubernetes cluster.local in-addr.arpa ip6.arpa {
#        pods insecure                          # Pod A 레코드 생성
#        fallthrough in-addr.arpa ip6.arpa      # 역방향 DNS는 다음 플러그인으로
#        ttl 30
#     }
#     prometheus :9153                          # 메트릭 노출
#     forward . /etc/resolv.conf {              # 외부 DNS는 호스트의 resolv.conf로 포워딩
#        max_concurrent 1000
#     }
#     cache 30 {                                # 30초 캐싱 (cluster.local 제외)
#        disable success cluster.local
#        disable denial cluster.local
#     }
#     loop                                      # 무한 루프 방지
#     reload                                    # ConfigMap 변경 시 자동 리로드
#     loadbalance                               # 응답 라운드로빈
# }
```

| 플러그인 | 설명 |
| --- | --- |
| `kubernetes` | `cluster.local` 도메인에 대한 DNS 레코드 생성 (Service, Pod) |
| `forward` | 클러스터 외부 도메인은 호스트의 DNS 서버로 포워딩 |
| `cache` | DNS 응답 캐싱 (클러스터 내부 도메인은 캐싱 비활성화) |
| `prometheus` | 9153 포트로 메트릭 노출 |

`forward . /etc/resolv.conf` 설정에 의해 클러스터 외부 도메인(예: `google.com`)은 호스트의 DNS 서버로 포워딩된다. 호스트의 DNS 설정을 확인해 보자.

```bash
# 호스트의 DNS 서버 확인
cat /etc/resolv.conf
# Generated by NetworkManager
# nameserver 168.126.63.1    ← KT 기본 DNS
# nameserver 168.126.63.2    ← KT 보조 DNS
```

즉, Pod에서 `google.com`을 조회하면: Pod → CoreDNS(`10.96.0.10`) → 호스트 DNS(`168.126.63.1`) → 외부 DNS 응답 순서로 처리된다.

> **참고: Corefile 이름의 유래**
>
> CoreDNS는 **Caddy** 웹 서버를 기반으로 만들어졌다. Caddy의 설정 파일이 `Caddyfile`이었기 때문에, 같은 네이밍 컨벤션을 따라 CoreDNS의 설정 파일은 `Corefile`이 되었다. `Dockerfile`, `Makefile`, `Jenkinsfile`처럼 `[제품명]file` 패턴이다.

<br>

## kube-proxy

kube-proxy는 각 노드에서 실행되는 **네트워크 프록시**로, Service의 ClusterIP를 실제 Pod IP로 라우팅하는 iptables/IPVS 규칙을 관리한다.

```bash
# kube-proxy DaemonSet 확인
kubectl get ds -n kube-system -owide
# NAME         DESIRED   CURRENT   READY   UP-TO-DATE   AVAILABLE   NODE SELECTOR            AGE    CONTAINERS   IMAGES                                SELECTOR
# kube-proxy   1         1         1       1            1           kubernetes.io/os=linux   151m   kube-proxy   registry.k8s.io/kube-proxy:v1.32.11   k8s-app=kube-proxy

# kube-proxy Pod 확인
kubectl get pod -n kube-system -l k8s-app=kube-proxy -owide
# NAME               READY   STATUS    RESTARTS   AGE    IP               NODE      NOMINATED NODE   READINESS GATES
# kube-proxy-5p6jx   1/1     Running   0          152m   192.168.10.100   k8s-ctr   <none>           <none>
```

| 항목 | 설명 |
| --- | --- |
| **DaemonSet** | 모든 노드에 하나씩 배포 (`NODE SELECTOR: kubernetes.io/os=linux`) |
| **Pod IP** | `192.168.10.100` (hostNetwork 모드로 노드 IP 사용) |
| **Tolerations** | 모든 Taint를 허용하여 컨트롤 플레인/문제 노드에도 배포됨 |

### Pod 볼륨 마운트

```bash
# kube-proxy Pod 상세 정보에서 Mounts 확인
kc describe pod -n kube-system -l k8s-app=kube-proxy | grep -A5 Mounts
#     Mounts:
#       /lib/modules from lib-modules (ro)              # 커널 모듈 접근 (iptables 등)
#       /run/xtables.lock from xtables-lock (rw)        # iptables 동시 접근 잠금
#       /var/lib/kube-proxy from kube-proxy (rw)        # ConfigMap (설정 파일)
#       /var/run/secrets/kubernetes.io/serviceaccount   # API Server 인증 토큰
```

### ConfigMap 주요 설정

```bash
# kube-proxy ConfigMap 확인
kc describe cm -n kube-system kube-proxy
# config.conf:
# ----
# apiVersion: kubeproxy.config.k8s.io/v1alpha1
# kind: KubeProxyConfiguration
# bindAddress: 0.0.0.0
# clusterCIDR: 10.244.0.0/16
# mode: ""                  # 기본값: iptables (빈 문자열 = iptables)
# conntrack:
#   maxPerCore: null        # 커널 기본값 사용
#   min: null
# nodePortAddresses: null   # 모든 노드 인터페이스에 바인딩
# portRange: ""             # 포트 범위 제한 없음
# iptables:
#   masqueradeAll: false    # 외부 트래픽만 SNAT
#   syncPeriod: 0s          # 기본 동기화 주기 사용
# ipvs:
#   scheduler: ""           # IPVS 모드 시 스케줄러 (rr, lc, dh 등)
```

| 설정 | 값 | 설명 |
| --- | --- | --- |
| `mode` | `""` (빈 문자열) | 기본값은 `iptables`. `ipvs`로 변경하면 IPVS 모드 사용 |
| `clusterCIDR` | `10.244.0.0/16` | Pod 네트워크 대역 |
| `nodePortAddresses` | `null` | NodePort가 모든 노드 IP에 바인딩됨 |
| `conntrack.maxPerCore` | `null` | 커널 기본 conntrack 테이블 크기 사용 |

### 포트 및 헬스체크

```bash
# kube-proxy 포트 확인
ss -nltp | grep kube-proxy
# LISTEN 0      4096        127.0.0.1:10249      0.0.0.0:*    users:(("kube-proxy",pid=16175,fd=11))
# LISTEN 0      4096                *:10256            *:*    users:(("kube-proxy",pid=16175,fd=10))

# 헬스체크 확인
curl 127.0.0.1:10249/healthz ; echo
# ok
```

| 포트 | 바인딩 | 용도 |
| --- | --- | --- |
| `10249` | `127.0.0.1` (로컬만) | 헬스체크 (`/healthz`) |
| `10256` | `*` (모든 인터페이스) | 메트릭 노출 (Prometheus 스크래핑용) |

<br>

# 결과

이 단계를 완료하면 다음과 같은 결과를 얻을 수 있다:

| 항목 | 결과 |
| --- | --- |
| 노드 | `Ready` 상태, Flannel 어노테이션 추가됨 |
| 인증서 | /etc/kubernetes/pki에 22개 파일 생성 (CA 3개 + 인증서/키 쌍) |
| kubeconfig | admin.conf, controller-manager.conf, scheduler.conf, kubelet.conf 생성 |
| Static Pod | etcd, kube-apiserver, kube-controller-manager, kube-scheduler 실행 중 |
| 애드온 | CoreDNS (Running), kube-proxy (Running) |

<br>

컨트롤 플레인 구성이 완료되었다. 다음 글에서는 워커 노드를 `kubeadm join`으로 클러스터에 추가한다.

<br>

# 부록: 설정 전후 비교

kubeadm init 전후의 시스템 상태를 비교하면 어떤 변경이 발생했는지 파악할 수 있다. 학습이나 트러블슈팅 시 유용하다.

```bash
# kubeadm init 후 환경 정보 저장
cat /etc/sysconfig/kubelet
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

# init 전후 비교 (vi -d 로 diff 확인)
vi -d etc_kubernetes-1.txt etc_kubernetes-2.txt
vi -d var_lib_kubelet-1.txt var_lib_kubelet-2.txt
vi -d pstree-1.txt pstree-2.txt
vi -d ss-1.txt ss-2.txt
vi -d sysctl-1.txt sysctl-2.txt
```

> **팁**: kubeadm init 전에 동일한 명령으로 `*-1.txt` 파일들을 생성해 두면, `vi -d`로 변경 사항을 시각적으로 비교할 수 있다.

<br>
