---
title:  "[Kubernetes] Cluster: Kubeadm을 이용해 클러스터 구성하기 - 1.5. 컨트롤 플레인 컴포넌트 확인"
excerpt: "노드 정보, 인증서, kubeconfig, Static Pod, 애드온 등 kubeadm init을 통해 구성된 컨트롤 플레인 컴포넌트를 상세히 확인해 보자."
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

이번 글의 목표는 **컨트롤 플레인 컴포넌트 상세 확인**이다.

- **노드 정보**: kubelet 상태, 노드 상세 정보, 커널 파라미터 확인
- **인증서**: PKI 구조, 인증서 내용, 만료 시간 확인
- **kubeconfig**: 각 컴포넌트별 kubeconfig 구조 확인
- **Static Pod**: etcd, API Server, Controller Manager, Scheduler 확인
- **애드온**: CoreDNS, kube-proxy 확인

<br>

# 들어가며

[이전 글]({% post_url 2026-01-18-Kubernetes-Kubeadm-01-4 %})에서 Flannel CNI를 설치하고 Linux 네트워크 스택(iptables, conntrack)을 확인했다. 이번 글에서는 CNI 설치가 완료되어 `Ready` 상태가 된 노드와 컨트롤 플레인 컴포넌트들을 상세히 확인한다.

<br>

# 노드 정보 확인

CNI 설치가 완료되어 노드가 `Ready` 상태가 되었다. 이 시점에서 노드의 상세 정보를 확인하면 kubeadm, kubelet, Flannel이 각각 어떤 설정을 추가했는지 파악할 수 있다.

## kubelet 상태 확인

```bash
systemctl is-active kubelet
# active

systemctl status kubelet --no-pager
# ● kubelet.service - kubelet: The Kubernetes Node Agent
#      Loaded: loaded (/usr/lib/systemd/system/kubelet.service; enabled; preset: disabled)
#     Drop-In: /usr/lib/systemd/system/kubelet.service.d
#              └─10-kubeadm.conf
#      Active: active (running) since Fri 2026-01-23 19:41:11 KST; 46min ago
#    Main PID: 16072 (kubelet)
#       Tasks: 12 (limit: 18742)
#      Memory: 39.6M (peak: 40.9M)
#         CPU: 52.578s
#      CGroup: /system.slice/kubelet.service
#              └─16072 /usr/bin/kubelet --bootstrap-kubeconfig=... --kubeconfig=...
```

`kubeadm init` 전에는 crashloop 상태였던 kubelet이 이제 정상 실행 중이다.

## 노드 상세 정보 확인

```bash
kc describe node k8s-ctr
```

주요 정보를 살펴보자:

### Labels & Annotations

```yaml
Labels:
  node-role.kubernetes.io/control-plane=       # kubeadm이 추가
  node.kubernetes.io/exclude-from-external-load-balancers=
Annotations:
  flannel.alpha.coreos.com/backend-type: vxlan  # Flannel이 추가
  flannel.alpha.coreos.com/public-ip: 192.168.10.100
  kubeadm.alpha.kubernetes.io/cri-socket: unix:///run/containerd/containerd.sock
Taints:
  node-role.kubernetes.io/control-plane:NoSchedule   # 일반 워크로드 스케줄 방지
```

### Conditions

| Condition | Status | Reason |
| --- | --- | --- |
| `NetworkUnavailable` | **False** | FlannelIsUp |
| `MemoryPressure` | False | KubeletHasSufficientMemory |
| `DiskPressure` | False | KubeletHasNoDiskPressure |
| `PIDPressure` | False | KubeletHasSufficientPID |
| `Ready` | **True** | KubeletReady |

CNI 설치 전에는 `NetworkUnavailable=True`였지만, Flannel 설치 후 `False`로 변경되었다.

### 리소스 사용량

```yaml
PodCIDR:     10.244.0.0/24
Capacity:    cpu: 4, memory: 2893976Ki, pods: 110
Allocatable: cpu: 4, memory: 2791576Ki, pods: 110

Non-terminated Pods: (8 in total)
  Namespace      Name                               CPU Requests  Memory Requests
  ---------      ----                               ------------  ---------------
  kube-flannel   kube-flannel-ds-hv2xd              100m (2%)     50Mi (1%)
  kube-system    coredns-668d6bf9bc-n8jxf           100m (2%)     70Mi (2%)
  kube-system    coredns-668d6bf9bc-z6h69           100m (2%)     70Mi (2%)
  kube-system    etcd-k8s-ctr                       100m (2%)     100Mi (3%)
  kube-system    kube-apiserver-k8s-ctr             250m (6%)     0 (0%)
  kube-system    kube-controller-manager-k8s-ctr    200m (5%)     0 (0%)
  kube-system    kube-proxy-5p6jx                   0 (0%)        0 (0%)
  kube-system    kube-scheduler-k8s-ctr             100m (2%)     0 (0%)

Allocated resources:
  cpu:    950m (23%)
  memory: 290Mi (10%)
```

컨트롤 플레인 컴포넌트들이 CPU의 약 23%, 메모리의 약 10%를 사용 중이다.

### Events

```
Events:
  Normal  Starting                 46m    kubelet          Starting kubelet.
  Normal  RegisteredNode           46m    node-controller  Node k8s-ctr event: Registered Node k8s-ctr in Controller
  Normal  NodeReady                4m30s  kubelet          Node k8s-ctr status is now: NodeReady
```

CNI 설치 후 `NodeReady` 이벤트가 발생했다.

<br>

## 커널 파라미터 변경 사항

kubelet과 kube-proxy가 클러스터 안정성을 위해 일부 커널 파라미터를 자동으로 변경한다. `sysctl`을 이용해 변경된 값을 확인해 보자.

> 참고: sysctl
>
> `sysctl`은 Linux 커널 파라미터를 런타임에 조회/변경하는 인터페이스다. 내부적으로 `/proc/sys/` 디렉토리의 파일을 읽고 쓴다. 예를 들어 `sysctl net.ipv4.ip_forward`는 `/proc/sys/net/ipv4/ip_forward` 파일의 값을 조회한다. Kubernetes에서는 네트워크 포워딩, 메모리 관리, 연결 추적 등의 커널 설정이 중요하므로 kubelet과 kube-proxy가 시작 시 관련 파라미터를 자동으로 설정한다.

### kubelet이 변경하는 파라미터

kubelet은 `--protect-kernel-defaults=false`(기본값)일 때 아래 파라미터들을 자동으로 설정한다. `true`로 설정하면 kubelet이 직접 변경하지 않고, 기존 값이 kubelet의 기대값과 다르면 오류가 발생한다.

| 파라미터 | 변경 전 | 변경 후 | 이유 |
| --- | --- | --- | --- |
| `kernel.panic` | 0 | 10 | 커널 패닉 시 10초 후 자동 재부팅 (노드 복구) |
| `vm.overcommit_memory` | 0 | 1 | 메모리 오버커밋 허용 (컨테이너 메모리 할당 유연성) |

아래 파라미터들은 kubelet이 확인하지만, 기본값이 이미 kubelet의 기대값과 일치하므로 변경되지 않는다:

| 파라미터 | 기존값 | 설명 |
| --- | --- | --- |
| `kernel.panic_on_oops` | 1 | oops 발생 시 패닉 |
| `vm.panic_on_oom` | 0 | OOM 시 패닉하지 않음 (OOM Killer가 처리) |
| `kernel.keys.root_maxkeys` | 1000000 | root 사용자의 최대 키 개수 |
| `kernel.keys.root_maxbytes` | 25000000 | root 사용자의 최대 키 바이트 (root_maxkeys × 25) |

> 참고
> - [kubelet sysctl 관련 코드](https://github.com/kubernetes/kubernetes/blob/master/staging/src/k8s.io/component-helpers/node/util/sysctl/sysctl.go)
> - [kubelet이 원하는 커널 파라미터](https://www.kimsehwan96.com/kubelet-expected-kernel-parameters/)

> 참고: kubespray에서의 처리
>
> `--protect-kernel-defaults=true`로 운영할 경우, kubelet이 커널 파라미터를 직접 변경하지 않으므로 사전에 설정해야 한다. kubespray는 아래와 같이 Ansible로 처리한다:
>
> ```yaml
> - name: Ensure kube-bench parameters are set
>   ansible.posix.sysctl:
>     name: "{{ item.name }}"
>     value: "{{ item.value }}"
>     state: present
>     reload: yes
>   with_items:
>     - { name: kernel.keys.root_maxbytes, value: 25000000 }
>     - { name: kernel.keys.root_maxkeys, value: 1000000 }
>     - { name: kernel.panic, value: 10 }
>     - { name: kernel.panic_on_oops, value: 1 }
>     - { name: vm.overcommit_memory, value: 1 }
>     - { name: vm.panic_on_oom, value: 0 }
>   when: kubelet_protect_kernel_defaults | bool
> ```

### kube-proxy가 변경하는 파라미터

kube-proxy는 iptables/IPVS를 통해 Service 트래픽을 라우팅하므로, conntrack(연결 추적) 테이블 관련 파라미터를 자동으로 설정한다.

| 파라미터 | 변경 전 | 변경 후 | 이유 |
| --- | --- | --- | --- |
| `net.nf_conntrack_max` | 65536 | 131072 | conntrack 테이블 크기 증가 (더 많은 연결 추적) |
| `net.netfilter.nf_conntrack_tcp_timeout_close_wait` | 60 | 3600 | CLOSE_WAIT 타임아웃 증가 (연결 정리 지연) |
| `net.netfilter.nf_conntrack_tcp_timeout_established` | 432000 | 86400 | ESTABLISHED 타임아웃 감소 (5일 → 1일, 오래된 연결 정리) |

> 참고: [kube-proxy conntrack sysctl 관련 코드](https://github.com/kubernetes/kubernetes/blob/master/pkg/proxy/conntrack/sysctls.go)

### 트러블슈팅 팁

커널 파라미터 튜닝 중 **설정 값이 자꾸 원복되거나 변경**된다면 kubelet 또는 kube-proxy를 의심해볼 수 있다. 이들 컴포넌트는 시작 시 위 파라미터들을 자동으로 설정하므로, 수동 튜닝 값과 충돌할 수 있다.


<br>

# 인증서 확인

## 인증서 만료 시간 확인

Kubernetes 클러스터의 인증서는 기본적으로 **1년** 후 만료된다. 운영 환경에서는 인증서 만료 전에 갱신해야 클러스터 장애를 방지할 수 있다. `kubeadm certs renew` 명령으로 갱신하거나, `kubeadm upgrade`를 수행하면 자동으로 갱신된다.

### kubeadm-config에서 유효 기간 확인

```bash
kc describe cm -n kube-system kubeadm-config
# Data
# ====
# ClusterConfiguration:
# ----
# apiVersion: kubeadm.k8s.io/v1beta4
# caCertificateValidityPeriod: 87600h0m0s   # CA 인증서: 10년 (87600시간)
# certificateValidityPeriod: 8760h0m0s      # 일반 인증서: 1년 (8760시간)
# certificatesDir: /etc/kubernetes/pki
# kubernetesVersion: v1.32.11
# networking:
#   dnsDomain: cluster.local
#   podSubnet: 10.244.0.0/16
#   serviceSubnet: 10.96.0.0/16
```

`kubeadm-config` ConfigMap은 클러스터 업그레이드 시 참조되므로, 설정 변경이 필요하면 이 ConfigMap을 업데이트해야 한다.

### 인증서 만료 시간 확인

```bash
kubeadm certs check-expiration
# CERTIFICATE                EXPIRES                  RESIDUAL TIME   CERTIFICATE AUTHORITY   EXTERNALLY MANAGED
# admin.conf                 Jan 23, 2027 10:41 UTC   364d            ca                      no
# apiserver                  Jan 23, 2027 10:41 UTC   364d            ca                      no
# apiserver-etcd-client      Jan 23, 2027 10:41 UTC   364d            etcd-ca                 no
# apiserver-kubelet-client   Jan 23, 2027 10:41 UTC   364d            ca                      no
# controller-manager.conf    Jan 23, 2027 10:41 UTC   364d            ca                      no
# etcd-healthcheck-client    Jan 23, 2027 10:41 UTC   364d            etcd-ca                 no
# etcd-peer                  Jan 23, 2027 10:41 UTC   364d            etcd-ca                 no
# etcd-server                Jan 23, 2027 10:41 UTC   364d            etcd-ca                 no
# front-proxy-client         Jan 23, 2027 10:41 UTC   364d            front-proxy-ca          no
# scheduler.conf             Jan 23, 2027 10:41 UTC   364d            ca                      no
# super-admin.conf           Jan 23, 2027 10:41 UTC   364d            ca                      no
#
# CERTIFICATE AUTHORITY   EXPIRES                  RESIDUAL TIME   EXTERNALLY MANAGED
# ca                      Jan 21, 2036 10:41 UTC   9y              no
# etcd-ca                 Jan 21, 2036 10:41 UTC   9y              no
# front-proxy-ca          Jan 21, 2036 10:41 UTC   9y              no
```

| 인증서 유형 | 유효 기간 | 만료일 |
| --- | --- | --- |
| 일반 인증서 (apiserver, admin.conf 등) | **1년** | 2027-01-23 |
| CA 인증서 (ca, etcd-ca, front-proxy-ca) | **10년** | 2036-01-21 |

> **운영 팁**: 인증서 만료 30일 전에 알림을 받도록 모니터링을 설정하고, 정기적인 클러스터 업그레이드를 통해 인증서를 갱신하는 것이 좋다.

<br>

## 인증서 파일 구조

[이전 글]({% post_url 2026-01-18-Kubernetes-Kubeadm-01-1 %})에서 설명한 PKI 구조가 실제로 생성되었는지 확인한다.

```bash
tree /etc/kubernetes/pki
# /etc/kubernetes/pki
# ├── apiserver.crt                    # API Server 서버 인증서
# ├── apiserver.key
# ├── apiserver-etcd-client.crt        # API Server → etcd 클라이언트 인증서
# ├── apiserver-etcd-client.key
# ├── apiserver-kubelet-client.crt     # API Server → kubelet 클라이언트 인증서
# ├── apiserver-kubelet-client.key
# ├── ca.crt                           # 클러스터 CA (루트)
# ├── ca.key
# ├── front-proxy-ca.crt               # API Aggregation용 CA
# ├── front-proxy-ca.key
# ├── front-proxy-client.crt           # API Aggregation 클라이언트 인증서
# ├── front-proxy-client.key
# ├── sa.key                           # ServiceAccount 토큰 서명용 키
# ├── sa.pub
# └── etcd/                            # etcd 전용 PKI
#     ├── ca.crt                       # etcd CA
#     ├── ca.key
#     ├── healthcheck-client.crt       # etcd 헬스체크용
#     ├── healthcheck-client.key
#     ├── peer.crt                     # etcd 노드 간 통신용
#     ├── peer.key
#     ├── server.crt                   # etcd 서버 인증서
#     └── server.key
#
# 2 directories, 22 files
```

총 **22개 파일** (3개 CA + 8개 인증서/키 쌍 + SA 키 쌍)이 생성되었다. [Kubernetes The Hard Way]({% post_url 2026-01-05-Kubernetes-Cluster-The-Hard-Way-04-1 %})에서 OpenSSL로 수동 생성했던 인증서들이 kubeadm에 의해 자동으로 생성되었다.

<br>

## 주요 인증서 내용 확인

인증서 내용을 직접 확인하면 각 인증서가 **누구에게 발급되었는지(Subject)**, **어떤 용도인지(Key Usage)**, **어디서 유효한지(SAN)** 를 이해할 수 있다. 특히 API Server 인증서의 SAN은 클라이언트가 접속할 수 있는 모든 주소를 포함해야 한다.

~~익숙해질 때까지는 계속 확인하도록 하자.~~

### CA 인증서

```bash
cat /etc/kubernetes/pki/ca.crt | openssl x509 -text -noout
# Certificate:
#     Data:
#         Version: 3 (0x2)
#         Serial Number: 9110514726841664365 (0x7e6f0cdfde5cc36d)
#         Signature Algorithm: sha256WithRSAEncryption
#         Issuer: CN=kubernetes
#         Validity
#             Not Before: Jan 23 10:36:04 2026 GMT
#             Not After : Jan 21 10:41:04 2036 GMT        ← 10년 유효
#         Subject: CN=kubernetes
#         Subject Public Key Info:
#             Public Key Algorithm: rsaEncryption
#                 Public-Key: (2048 bit)
#         X509v3 extensions:
#             X509v3 Key Usage: critical
#                 Digital Signature, Key Encipherment, Certificate Sign
#             X509v3 Basic Constraints: critical
#                 CA:TRUE                                 ← 루트 CA 인증서
#             X509v3 Subject Alternative Name:
#                 DNS:kubernetes
```

- **Issuer = Subject = `CN=kubernetes`**: 자체 서명된 루트 CA
- **CA:TRUE**: 다른 인증서를 서명할 수 있는 CA 인증서
- **유효기간 10년**: CA 인증서는 장기간 유효

### API Server 인증서

```bash
cat /etc/kubernetes/pki/apiserver.crt | openssl x509 -text -noout
# Certificate:
#     Data:
#         Signature Algorithm: sha256WithRSAEncryption
#         Issuer: CN=kubernetes                          ← CA가 서명
#         Validity
#             Not Before: Jan 23 10:36:04 2026 GMT
#             Not After : Jan 23 10:41:04 2027 GMT       ← 1년 유효
#         Subject: CN=kube-apiserver
#         X509v3 extensions:
#             X509v3 Key Usage: critical
#                 Digital Signature, Key Encipherment
#             X509v3 Extended Key Usage:
#                 TLS Web Server Authentication          ← 서버 인증서
#             X509v3 Basic Constraints: critical
#                 CA:FALSE
#             X509v3 Subject Alternative Name:
#                 DNS:k8s-ctr, DNS:kubernetes, DNS:kubernetes.default,
#                 DNS:kubernetes.default.svc, DNS:kubernetes.default.svc.cluster.local,
#                 IP Address:10.96.0.1, IP Address:192.168.10.100
```

- **Subject: `CN=kube-apiserver`**: API Server의 서버 인증서
- **Extended Key Usage: `TLS Web Server Authentication`**: 서버 인증 전용
- **SAN (Subject Alternative Name)**: 클라이언트가 이 주소들로 접속 시 인증서 검증 통과
  - `kubernetes.default.svc.cluster.local`: Pod 내부에서 접근 시
  - `10.96.0.1`: Service ClusterIP (kubernetes 서비스)
  - `192.168.10.100`: 외부에서 접근 시

### API Server → Kubelet 클라이언트 인증서

```bash
cat /etc/kubernetes/pki/apiserver-kubelet-client.crt | openssl x509 -text -noout
# Certificate:
#     Data:
#         Signature Algorithm: sha256WithRSAEncryption
#         Issuer: CN=kubernetes
#         Validity
#             Not Before: Jan 23 10:36:04 2026 GMT
#             Not After : Jan 23 10:41:04 2027 GMT
#         Subject: O=kubeadm:cluster-admins, CN=kube-apiserver-kubelet-client
#         X509v3 extensions:
#             X509v3 Key Usage: critical
#                 Digital Signature, Key Encipherment
#             X509v3 Extended Key Usage:
#                 TLS Web Client Authentication          ← 클라이언트 인증서
#             X509v3 Basic Constraints: critical
#                 CA:FALSE
```

- **Subject: `O=kubeadm:cluster-admins, CN=kube-apiserver-kubelet-client`**: 조직(O)과 이름(CN) 포함
- **Extended Key Usage: `TLS Web Client Authentication`**: 클라이언트 인증 전용
- API Server가 kubelet에 접속할 때 이 인증서로 자신을 증명

<br>

# kubeconfig 확인

kubeconfig 파일은 각 컴포넌트가 API Server에 접속할 때 사용하는 **인증 정보**를 담고 있다. 각 파일의 `user` 섹션에서 **누구로 인증하는지**를 확인할 수 있으며, 이 정보가 RBAC 권한과 연결된다.

대부분의 kubeconfig는 인증서가 base64로 **내장**(`client-certificate-data`)되어 있지만, **kubelet.conf만 외부 파일 경로**(`client-certificate`)를 참조한다. 이는 kubeadm이 kubelet 인증서 자동 갱신(Certificate Rotation)을 지원하기 때문이다.

> 참고: **Hard Way와의 차이 (클라이언트 인증서)**
>
> [Hard Way에서는 kubelet kubeconfig도 **클라이언트 인증서**가 base64로 내장]({% post_url 2026-01-05-Kubernetes-Cluster-The-Hard-Way-05-2 %}#kubelet-kubeconfig-생성)되어 있었다:
> - 수동으로 인증서를 생성하고 배포했기 때문에 **인증서 자동 갱신 기능이 없었다**
> - kubeconfig 파일 안에 인증서가 포함되어 있어 갱신 시 파일 전체를 교체해야 한다
>
> kubeadm은 kubelet 클라이언트 인증서를 **클러스터 CA로 서명**하여 생성하고, `rotateCertificates: true` 설정으로 만료 전 자동 갱신을 지원한다. 이를 위해 kubeconfig가 외부 파일을 참조하는 구조를 사용한다. 자동 갱신 메커니즘 상세는 [kubelet 클라이언트 인증서](#kubelet-클라이언트-인증서)에서, 서버 인증서는 [kubelet 서버 인증서](#kubelet-서버-인증서)에서 설명한다.

| 파일 | 사용자 | 용도 |
| --- | --- | --- |
| `admin.conf` | `kubernetes-admin` (O=`kubeadm:cluster-admins`) | kubectl 관리 작업용 |
| `super-admin.conf` | `kubernetes-super-admin` (O=`system:masters`) | 비상 복구용 (RBAC 우회) |
| `controller-manager.conf` | `system:kube-controller-manager` | Controller Manager 전용 |
| `scheduler.conf` | `system:kube-scheduler` | Scheduler 전용 |
| `kubelet.conf` | `system:node:<노드명>` | kubelet 전용 (외부 인증서 참조) |

## admin.conf

`O=kubeadm:cluster-admins` 그룹에 속한 `kubernetes-admin` 사용자로 인증한다. 일반적인 클러스터 관리 작업에 사용한다.

```bash
# 관리자용 kubeconfig
cat /etc/kubernetes/admin.conf
# apiVersion: v1
# clusters:
# - cluster:
#     certificate-authority-data: LS0t...   ← CA 인증서 (base64)
#     server: https://192.168.10.100:6443
#   name: kubernetes
# contexts:
# - context:
#     cluster: kubernetes
#     user: kubernetes-admin
#   name: kubernetes-admin@kubernetes
# current-context: kubernetes-admin@kubernetes
# users:
# - name: kubernetes-admin
#   user:
#     client-certificate-data: LS0t...      ← 클라이언트 인증서 (base64)
#     client-key-data: LS0t...              ← 클라이언트 키 (base64)
```



## super-admin.conf

`O=system:masters` 그룹에 속한 `kubernetes-super-admin` 사용자로 인증한다. `system:masters`는 kube-apiserver에 하드코딩된 특수 그룹으로, **RBAC 평가를 거치지 않고 모든 권한이 허용**된다. 클러스터 복구 시에만 사용해야 한다.

> 참고
> - [Using RBAC Authorization - Default roles and role bindings](https://kubernetes.io/docs/reference/access-authn-authz/rbac/#default-roles-and-role-bindings)
> - [PKI certificates and requirements](https://kubernetes.io/docs/setup/best-practices/certificates/)


```bash
# 슈퍼 관리자용 kubeconfig (비상 복구용)
cat /etc/kubernetes/super-admin.conf
# apiVersion: v1
# clusters:
# - cluster:
#     certificate-authority-data: LS0t...
#     server: https://192.168.10.100:6443
#   name: kubernetes
# contexts:
# - context:
#     cluster: kubernetes
#     user: kubernetes-super-admin
#   name: kubernetes-super-admin@kubernetes
# current-context: kubernetes-super-admin@kubernetes
# users:
# - name: kubernetes-super-admin
#   user:
#     client-certificate-data: LS0t...
#     client-key-data: LS0t...
```

## controller-manager.conf, scheduler.conf

각 컴포넌트는 자신만의 kubeconfig로 API Server에 인증한다. `system:kube-controller-manager`와 `system:kube-scheduler`는 [Kubernetes가 부트스트랩 시 생성하는 기본 ClusterRoleBinding]({% post_url 2026-01-05-Kubernetes-Cluster-The-Hard-Way-08-2 %}#rbac-기본-역할)으로 필요한 권한을 부여받는다.

```bash
# 컴포넌트용 kubeconfig
cat /etc/kubernetes/controller-manager.conf
# users:
# - name: system:kube-controller-manager
#   user:
#     client-certificate-data: LS0t...
#     client-key-data: LS0t...

cat /etc/kubernetes/scheduler.conf
# users:
# - name: system:kube-scheduler
#   user:
#     client-certificate-data: LS0t...
#     client-key-data: LS0t...
```

## kubelet.conf

앞서 언급한 대로, kubelet.conf만 인증서를 외부 파일 경로로 참조한다. `kubelet-client-current.pem`은 현재 유효한 인증서에 대한 심볼릭 링크로, 인증서 갱신 시 이 링크가 새 인증서를 가리키도록 업데이트된다.

> 참고: **PEM 파일과 kubeconfig의 인증서 형식**
>
> [PEM 파일]({% post_url 2026-01-04-CS-Security-X509-Certificate %}#pemprivacy-enhanced-mail)은 DER의 Base64 인코딩에 헤더/푸터(`-----BEGIN CERTIFICATE-----`)를 추가한 형식이다. 다른 kubeconfig의 `client-certificate-data`는 이 헤더/푸터를 제거한 순수 base64가 들어간 것이다.
>
> kubelet은 인증서 갱신 시 kubeconfig 파일 수정 없이 새 PEM 파일 생성 후 심볼릭 링크만 업데이트하면 된다. 반면 다른 kubeconfig(admin.conf, controller-manager.conf 등)는 인증서 갱신 시 파일 내의 base64 값을 직접 교체해야 한다.

```bash
# kubelet kubeconfig
cat /etc/kubernetes/kubelet.conf
# contexts:
# - context:
#     cluster: kubernetes
#     user: system:node:k8s-ctr             ← 노드명 포함
#   name: system:node:k8s-ctr@kubernetes
# users:
# - name: system:node:k8s-ctr
#   user:
#     client-certificate: /var/lib/kubelet/pki/kubelet-client-current.pem
#     client-key: /var/lib/kubelet/pki/kubelet-client-current.pem
```

### kubelet 인증서 확인

kubelet.conf에서 참조하는 인증서 파일들을 확인한다.

```bash
ls -l /var/lib/kubelet/pki
# total 12
# -rw-------. 1 root root 2826 Jan 23 19:41 kubelet-client-2026-01-23-19-41-07.pem
# lrwxrwxrwx. 1 root root   59 Jan 23 19:41 kubelet-client-current.pem -> /var/lib/kubelet/pki/kubelet-client-2026-01-23-19-41-07.pem
# -rw-r--r--. 1 root root 2262 Jan 23 19:41 kubelet.crt
# -rw-------. 1 root root 1679 Jan 23 19:41 kubelet.key
```

| 파일 | 용도 |
| --- | --- |
| `kubelet-client-current.pem` | kubelet → API Server 클라이언트 인증서 (심볼릭 링크) |
| `kubelet-client-2026-01-23-...pem` | 실제 클라이언트 인증서 (자동 갱신 시 새 파일 생성) |
| `kubelet.crt` / `kubelet.key` | kubelet 서버 인증서 (API Server → kubelet 접속 시) |

kubelet은 **클라이언트 인증서**와 **서버 인증서** 두 가지를 모두 사용한다:
- **클라이언트 인증서** (`kubelet-client-*.pem`): kubelet → API Server 접속 시
- **서버 인증서** (`kubelet.crt/key`): API Server → kubelet 접속 시

두 인증서의 **발급자(Issuer)가 다른데**, 아래에서 각각 확인해 보자.



#### kubelet 서버 인증서

API Server가 kubelet의 `/logs`, `/exec`, `/attach` 등 API에 접속할 때 이 인증서로 kubelet을 검증한다.

```bash
cat /var/lib/kubelet/pki/kubelet.crt | openssl x509 -text -noout
# Certificate:
#     Data:
#         Signature Algorithm: sha256WithRSAEncryption
#         Issuer: CN=k8s-ctr-ca@1769164867              ← kubelet 자체 생성 CA
#         Validity
#             Not Before: Jan 23 09:41:06 2026 GMT
#             Not After : Jan 23 09:41:06 2027 GMT
#         Subject: CN=k8s-ctr@1769164867
#         X509v3 extensions:
#             X509v3 Extended Key Usage:
#                 TLS Web Server Authentication          ← 서버 인증서
#             X509v3 Subject Alternative Name:
#                 DNS:k8s-ctr                            ← 노드 호스트명
```

- **Issuer: `CN=k8s-ctr-ca@...`**: 클러스터 CA가 아닌 **kubelet이 자체 생성한 CA**로 서명됨
- **SAN: `DNS:k8s-ctr`**: 노드 호스트명만 포함

> 참고: **왜 자체 CA로 서명되었나?**
>
> kubelet 서버 인증서의 서명자를 결정하는 핵심 설정은 `serverTLSBootstrap`이다([KubeletConfiguration](https://kubernetes.io/docs/reference/config-api/kubelet-config.v1beta1/#kubelet-config-k8s-io-v1beta1-KubeletConfiguration))
> - `serverTLSBootstrap: true` → 클러스터 CA가 서명 (CSR 승인 필요)
> - `serverTLSBootstrap: false` (기본값) → kubelet이 자체 CA 생성하여 서명
>
> [이전 글]({% post_url 2026-01-18-Kubernetes-Kubeadm-01-3 %}#선택-dry-run으로-사전-확인)에서 `kubelet-config` ConfigMap이 클러스터 내 모든 kubelet이 공유할 설정을 담고 있다고 설명했다. 실제 ConfigMap 내용을 확인해보면:
>
> ```bash
> kubectl get configmap kubelet-config -n kube-system -o yaml
> # apiVersion: v1
> # data:
> #   kubelet: |
> #     apiVersion: kubelet.config.k8s.io/v1beta1
> #     ...
> #     rotateCertificates: true
> #     ...
> #     (serverTLSBootstrap 설정 없음)
> ```
>
> `serverTLSBootstrap` 설정이 **명시되지 않았으므로 기본값 `false`가 적용**된다. 이 때문에:
> - kubelet이 **자체 CA를 생성**하여 서버 인증서에 서명
> - 클러스터 CA와 **독립적으로** 서버 인증서 관리
>
> 만약 `serverTLSBootstrap: true`로 설정하면 kubelet이 **CSR(Certificate Signing Request)**을 API Server에 요청한다. 그러나 kube-controller-manager의 기본 서명자는 **자동 승인하지 않으므로**, 관리자가 `kubectl certificate approve`로 수동 승인하거나 [kubelet-csr-approver](https://github.com/postfinance/kubelet-csr-approver) 같은 써드파티 컨트롤러가 필요하다. 
>
> 현재 실습에서는 이러한 복잡성을 피하기 위해 kubeadm의 기본 설정(비활성화)을 그대로 사용했다.
>
> 다만, 프로덕션 환경에서는 통일된 인증서 관리를 위해 `serverTLSBootstrap: true`를 고려할 수 있다. 이 경우, CSR 승인 자동화 메커니즘을 함께 구성해야 하므로 운영 복잡도가 증가할 수 있다. 아래 글을 참고해 보자.
> - [서명된 kubelet 인증서 활성화하기](https://kubernetes.io/ko/docs/tasks/administer-cluster/kubeadm/kubeadm-certs/#kubelet-serving-certs)
- [Kubelet의 인증서 갱신 구성](https://kubernetes.io/ko/docs/tasks/tls/certificate-rotation/)

#### kubelet 클라이언트 인증서

kubelet이 API Server에 접속하여 Pod 정보 조회, 상태 보고 등을 수행할 때 이 인증서로 자신을 인증한다.

```bash
cat /var/lib/kubelet/pki/kubelet-client-current.pem | openssl x509 -text -noout
# Certificate:
#     Data:
#         Signature Algorithm: sha256WithRSAEncryption
#         Issuer: CN=kubernetes                         ← 클러스터 CA가 서명
#         Validity
#             Not Before: Jan 23 10:36:04 2026 GMT
#             Not After : Jan 23 10:41:04 2027 GMT
#         Subject: O=system:nodes, CN=system:node:k8s-ctr
#         X509v3 extensions:
#             X509v3 Extended Key Usage:
#                 TLS Web Client Authentication         ← 클라이언트 인증서
```

- **Issuer: `CN=kubernetes`**: **클러스터 CA**가 서명 → API Server가 신뢰함
- **Subject: `O=system:nodes, CN=system:node:k8s-ctr`**: RBAC에서 `system:nodes` 그룹과 `system:node:k8s-ctr` 사용자로 인식됨

> **참고: 클라이언트 인증서 자동 갱신 (`rotateCertificates`)**
>
> [이전 글]({% post_url 2026-01-18-Kubernetes-Kubeadm-01-3 %}#선택-dry-run으로-사전-확인)의 `kubelet-config` ConfigMap에서 `rotateCertificates: true`가 설정되어 있다. 이 설정으로 인해:
> 1. 인증서 만료가 임박하면 kubelet이 **CSR(Certificate Signing Request)**을 API Server에 제출
> 2. kube-controller-manager가 **자동 승인** 후 `--cluster-signing-cert-file`로 지정된 **클러스터 CA로 서명**
> 3. 새 인증서가 `kubelet-client-current.pem`에 갱신됨
>
> [위](#kubeconfig-확인)에서 설명한 대로 kubeadm은 kubelet.conf가 외부 파일을 참조하도록 구성하여 이 자동 갱신을 지원한다.

#### 두 인증서의 차이 요약

| 구분 | `kubelet.crt` (서버) | `kubelet-client-current.pem` (클라이언트) |
| --- | --- | --- |
| **용도** | API Server → kubelet 접속 시 | kubelet → API Server 접속 시 |
| **발급자** | kubelet 자체 CA | 클러스터 CA (`kubernetes`) |
| **Extended Key Usage** | Server Authentication | Client Authentication |
| **자동 갱신** | kubelet이 자체 관리 | kubelet이 CSR 요청, 컨트롤러가 승인 |

<br>

# Static Pod 확인

## Static Pod 매니페스트 디렉토리

컨트롤 플레인 컴포넌트들은 **Static Pod**로 실행된다. kubelet이 특정 디렉토리를 감시하고, 그 안의 YAML 파일을 읽어 Pod를 직접 생성한다. API Server 없이도 컨트롤 플레인을 부트스트랩할 수 있는 핵심 메커니즘이다.

> **참고: Hard Way와의 비교**
>
> [Kubernetes The Hard Way 실습]({% post_url 2026-01-05-Kubernetes-Cluster-The-Hard-Way-08-1 %})에서는 컨트롤 플레인 컴포넌트들을 **systemd 서비스**로 직접 구성했다:
> - `kube-apiserver.service`, `kube-controller-manager.service`, `kube-scheduler.service` 파일을 **수동으로 작성**
> - 각 서비스의 실행 옵션(인증서 경로, etcd 연결, CIDR 등)을 **직접 지정**
> - Control Plane 노드에 **kubelet이 필요 없었다** (systemd가 직접 관리)
>
> kubeadm은 이 모든 작업을 **Static Pod 매니페스트 자동 생성**으로 대체한다. 대신 Control Plane에도 kubelet이 필수다.

```bash
# Static Pod 매니페스트 위치
tree /etc/kubernetes/manifests/
# /etc/kubernetes/manifests/
# ├── etcd.yaml
# ├── kube-apiserver.yaml
# ├── kube-controller-manager.yaml
# └── kube-scheduler.yaml
#
# 1 directory, 4 files

# kubelet 설정에서 Static Pod 경로 확인
cat /var/lib/kubelet/config.yaml | grep staticPodPath
# staticPodPath: /etc/kubernetes/manifests

# kubelet 플래그 확인
cat /var/lib/kubelet/kubeadm-flags.env
# KUBELET_KUBEADM_ARGS="--container-runtime-endpoint=unix:///run/containerd/containerd.sock --node-ip=192.168.10.100 --pod-infra-container-image=registry.k8s.io/pause:3.10"
```

| 플래그 | 값 | 설명 |
| --- | --- | --- |
| `--container-runtime-endpoint` | `unix:///run/containerd/containerd.sock` | containerd CRI 소켓 경로 |
| `--node-ip` | `192.168.10.100` | 노드 IP (kubeadm 설정에서 지정한 값) |
| `--pod-infra-container-image` | `registry.k8s.io/pause:3.10` | Pod의 [인프라 컨테이너(pause)]({% post_url 2026-01-05-Kubernetes-Cluster-The-Hard-Way-12 %}#pause-컨테이너) 이미지 |

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

### Leader Election 상세 확인

[이전 글]({% post_url 2026-01-18-Kubernetes-Kubeadm-01-3 %}#lease)에서 Lease 리소스가 Leader Election과 Node Heartbeat에 사용된다고 설명했다. Lease의 상세 정보를 확인하면 Leader Election 동작 방식을 이해할 수 있다.

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
#     - --bind-address=127.0.0.1
#     - --cluster-cidr=10.244.0.0/16
#     - --cluster-signing-cert-file=/etc/kubernetes/pki/ca.crt
#     - --cluster-signing-key-file=/etc/kubernetes/pki/ca.key
#     - --controllers=*,bootstrapsigner,tokencleaner
#     - --leader-elect=true
#     - --service-cluster-ip-range=10.96.0.0/16
#     - --use-service-account-credentials=true
```

| 옵션 | 설명 |
| --- | --- |
| `--allocate-node-cidrs=true` | 각 노드에 Pod CIDR(`/24`) 자동 할당 |
| `--bind-address=127.0.0.1` | 로컬에서만 접근 가능 (보안) |
| `--cluster-cidr=10.244.0.0/16` | Pod 네트워크 대역 (kubeadm 설정의 `podSubnet`) |
| `--cluster-signing-cert-file`, `--cluster-signing-key-file` | CSR 서명용 CA. kubelet 클라이언트 인증서 갱신(`rotateCertificates`) 시 자동 적용 |
| `--controllers=*,bootstrapsigner,tokencleaner` | 모든 기본 컨트롤러 + 부트스트랩 관련 컨트롤러 활성화 |
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
