---
title:  "[Kubernetes] Cluster: 내 손으로 클러스터 구성하기 - 8.1. Bootstrapping the Kubernetes Control Plane"
excerpt: "Kubernetes Control Plane 컴포넌트들의 systemd unit 파일과 설정 파일을 분석해 보자."
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

<br>

*[서종호(가시다)](https://www.linkedin.com/in/gasida99/)님의 On-Premise K8s Hands-on Study 1주차 학습 내용을 기반으로 합니다.*

<br>

# TL;DR


이번 글의 목표는 **Kubernetes Control Plane 컴포넌트 설정 파일 분석**이다. [Kubernetes the Hard Way 튜토리얼의 Bootstrapping the Kubernetes Control Plane 단계](https://github.com/kelseyhightower/kubernetes-the-hard-way/blob/master/docs/08-bootstrapping-kubernetes-controllers.md)를 수행한다.

Control Plane은 Kubernetes 클러스터의 두뇌 역할을 한다. API Server는 모든 요청의 진입점이고, Scheduler는 Pod 배치를 결정하며, Controller Manager는 클러스터 상태를 원하는 상태로 유지한다. 이번 단계에서는 각 컴포넌트가 어떤 옵션으로 구동되는지 이해한다.

- kube-apiserver 설정: systemd unit 파일 생성 및 주요 옵션 분석
- kube-scheduler 설정: 설정 파일(KubeSchedulerConfiguration) 및 unit 파일 분석
- kube-controller-manager 설정: unit 파일 생성 및 주요 옵션 분석


<br>

# 네트워크 대역 개요

Control Plane 설정에서 자주 등장하는 네트워크 대역이 있다. [4.3. Provisioning a CA and Generating TLS Certificates]({% post_url 2026-01-05-Kubernetes-Cluster-The-Hard-Way-04-3 %}) 글에서 정리한 것처럼, 실습 환경에서는 Pod CIDR로 `10.200.0.0/16`, Service CIDR로 `10.32.0.0/24`를 사용한다. 특히 `10.32.0.1`은 kubernetes Service의 ClusterIP로, API Server 인증서의 SAN에도 포함되어 있다.

<br>

# kube-apiserver

kube-apiserver는 Kubernetes 클러스터의 **중앙 API 서버**로, 모든 컴포넌트와 사용자 요청의 진입점이다. etcd와 직접 통신하는 유일한 컴포넌트이며, 인증(Authentication), 인가(Authorization), Admission Control을 담당한다.

## systemd unit 파일

kube-apiserver를 systemd 서비스로 관리하기 위한 unit 파일이다. [Kubernetes the Hard Way에서 제공하는 템플릿](https://github.com/kelseyhightower/kubernetes-the-hard-way/blob/master/units/kube-apiserver.service)을 그대로 사용하면 안 되고, `--service-cluster-ip-range` 옵션을 추가해야 한다.

> [Missing --service-cluster-ip-range flag in kube-apiserver.service causes certificate validation failures](https://github.com/kelseyhightower/kubernetes-the-hard-way/issues/905)에 관련 이슈가 등장한다.

```bash
cat << EOF > units/kube-apiserver.service
[Unit]
Description=Kubernetes API Server
Documentation=https://github.com/kubernetes/kubernetes

[Service]
ExecStart=/usr/local/bin/kube-apiserver \\
  --allow-privileged=true \\
  --apiserver-count=1 \\
  --audit-log-maxage=30 \\
  --audit-log-maxbackup=3 \\
  --audit-log-maxsize=100 \\
  --audit-log-path=/var/log/audit.log \\
  --authorization-mode=Node,RBAC \\
  --bind-address=0.0.0.0 \\
  --client-ca-file=/var/lib/kubernetes/ca.crt \\
  --enable-admission-plugins=NamespaceLifecycle,NodeRestriction,LimitRanger,ServiceAccount,DefaultStorageClass,ResourceQuota \\
  --etcd-servers=http://127.0.0.1:2379 \\
  --event-ttl=1h \\
  --encryption-provider-config=/var/lib/kubernetes/encryption-config.yaml \\
  --kubelet-certificate-authority=/var/lib/kubernetes/ca.crt \\
  --kubelet-client-certificate=/var/lib/kubernetes/kube-api-server.crt \\
  --kubelet-client-key=/var/lib/kubernetes/kube-api-server.key \\
  --runtime-config='api/all=true' \\
  --service-account-key-file=/var/lib/kubernetes/service-accounts.crt \\
  --service-account-signing-key-file=/var/lib/kubernetes/service-accounts.key \\
  --service-account-issuer=https://server.kubernetes.local:6443 \\
  --service-cluster-ip-range=10.32.0.0/24 \\
  --service-node-port-range=30000-32767 \\
  --tls-cert-file=/var/lib/kubernetes/kube-api-server.crt \\
  --tls-private-key-file=/var/lib/kubernetes/kube-api-server.key \\
  --v=2
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF
```

<br>

## 주요 옵션 분석

### 인증 관련

```bash
ExecStart=/usr/local/bin/kube-apiserver \\
  ...
  --client-ca-file=/var/lib/kubernetes/ca.crt \\
  ...
  --tls-cert-file=/var/lib/kubernetes/kube-api-server.crt \\
  --tls-private-key-file=/var/lib/kubernetes/kube-api-server.key \\
  ...
```

*거듭 등장하지만*, Kubernetes는 mTLS 통신을 수행한다. API Server도 클라이언트(kubectl, kubelet 등)가 연결할 때 서버 인증서를 제시해야 하고, 동시에 클라이언트 인증서를 검증한다. 이 때 필요한 설정이다.

- `--client-ca-file`: 클라이언트 인증서를 검증할 CA 인증서. 클라이언트가 제시한 인증서가 이 CA로 서명되었는지 확인
- `--tls-cert-file`: API Server가 클라이언트에게 제시할 서버 인증서
- `--tls-private-key-file`: 서버 인증서의 개인키

### 인가 관련

```bash
ExecStart=/usr/local/bin/kube-apiserver \\
  ...
  --authorization-mode=Node,RBAC \\
  ...
```

인증(Authentication)을 통과한 요청이 실제로 해당 작업을 수행할 권한이 있는지 검증하는 단계이다.

- `--authorization-mode=Node,RBAC`: 인가 방식 지정. 쉼표로 구분된 순서대로 평가

`Node,RBAC`로 값이 명시되어 있다. 이에 따라, 두 가지 인가 방식을 순차적으로 적용한다:

1. **[Node Authorizer]({% post_url 2026-01-05-Kubernetes-Cluster-The-Hard-Way-05-1 %}#node-authorizer)**: kubelet이 자신의 노드에 할당된 리소스(Pod, Secret, ConfigMap 등)에만 접근할 수 있도록 제한. `system:nodes` 그룹에 속한 사용자(`system:node:<nodeName>`)에게 적용
2. **RBAC(Role-Based Access Control)**: Role/ClusterRole과 RoleBinding/ClusterRoleBinding을 통해 권한 부여

요청이 들어오면 Node Authorizer가 먼저 평가하고, 결정을 내리지 못하면(해당 사항 없으면) RBAC이 평가한다.

### Admission Control

```bash
ExecStart=/usr/local/bin/kube-apiserver \\
  ...
  --enable-admission-plugins=NamespaceLifecycle,NodeRestriction,LimitRanger,ServiceAccount,DefaultStorageClass,ResourceQuota \\
  ...
```

Admission Controller는 API 요청이 etcd에 저장되기 전에 검증하거나 수정하는 플러그인이다([참고](https://kubernetes.io/docs/reference/access-authn-authz/admission-controllers/)).
- `--enable-admission-plugins`: 활성화할 Admission Controller 목록

값으로 지정되어 있는 플러그인들을 간단히 보면 다음과 같다.
- `NamespaceLifecycle`: 삭제 중인 Namespace에 새 리소스 생성 방지
- `NodeRestriction`: kubelet이 자신의 Node/Pod만 수정하도록 제한
- `LimitRanger`: Namespace의 LimitRange 정책 적용
- `ServiceAccount`: Pod에 ServiceAccount 자동 주입
- `DefaultStorageClass`: PVC에 기본 StorageClass 할당
- `ResourceQuota`: Namespace의 리소스 할당량 적용

### 네트워크 관련

```bash
ExecStart=/usr/local/bin/kube-apiserver \\
  ...
  --bind-address=0.0.0.0 \\
  ...
  --service-cluster-ip-range=10.32.0.0/24 \\
  --service-node-port-range=30000-32767 \\
  ...
```

API Server 네트워크 설정 관련 옵션이다. 

- `--service-cluster-ip-range=10.32.0.0/24`: API Server가 Service에 할당할 ClusterIP 대역
- `--service-node-port-range=30000-32767`: NodePort Service에 사용할 포트 범위
- `--bind-address=0.0.0.0`: API Server가 바인딩할 주소. 모든 인터페이스에서 수신

특히, `--service-cluster-ip-range` 옵션은 반드시 명시해야 한다. [앞서 언급했듯이](#systemd-unit-파일), Kubernetes the Hard Way 원본 템플릿에는 이 옵션이 없어 기본값 `10.0.0.0/24`가 적용된다. 하지만 [4.3. Provisioning a CA and Generating TLS Certificates]({% post_url 2026-01-05-Kubernetes-Cluster-The-Hard-Way-04-3 %}) 단계에서 API Server 인증서의 SAN에 `10.32.0.1`을 포함시켰다. 

따라서 이 값을 `10.32.0.0/24`로 명시적으로 설정하지 않으면 kubernetes Service의 ClusterIP가 `10.0.0.1`로 할당되어 **인증서 검증에 실패하고 클러스터가 정상 동작하지 않는다**. 

> 관련 이슈: [Missing --service-cluster-ip-range flag in kube-apiserver.service causes certificate validation failures](https://github.com/kelseyhightower/kubernetes-the-hard-way/issues/905)

### etcd 연결

```bash
ExecStart=/usr/local/bin/kube-apiserver \\
  ...
  --etcd-servers=http://127.0.0.1:2379 \\
  ...
```

API Server와 etcd 클러스터 간 통신 설정이다.

- `--etcd-servers=http://127.0.0.1:2379`: etcd 클러스터 주소. 로컬호스트의 2379 포트

실습 환경에서는 HTTP 평문 통신을 사용한다. 프로덕션에서는 etcd도 TLS로 보호해야 하며, `--etcd-cafile`, `--etcd-certfile`, `--etcd-keyfile` 옵션을 추가로 설정한다.

### ServiceAccount 관련

```bash
ExecStart=/usr/local/bin/kube-apiserver \\
  ...
  --service-account-key-file=/var/lib/kubernetes/service-accounts.crt \\
  --service-account-signing-key-file=/var/lib/kubernetes/service-accounts.key \\
  --service-account-issuer=https://server.kubernetes.local:6443 \\
  ...
```

Pod 내부의 애플리케이션이 API Server에 인증할 때 사용하는 ServiceAccount 토큰 설정이다.

- `--service-account-key-file`: ServiceAccount 토큰 검증에 사용할 공개키
- `--service-account-signing-key-file`: ServiceAccount 토큰 서명에 사용할 개인키
- `--service-account-issuer`: 토큰 발급자(iss claim) 식별자. OIDC 검증에 사용

ServiceAccount 토큰은 JWT(JSON Web Token) 형식이며, 다음과 같은 흐름으로 동작한다:

1. **토큰 발급**: Pod 생성 시 API Server가 개인키로 토큰에 서명하여 발급
2. **토큰 마운트**: Pod 내부 `/var/run/secrets/kubernetes.io/serviceaccount/token`에 자동 마운트
3. **인증 요청**: Pod 내 애플리케이션이 이 토큰을 HTTP Header에 포함하여 API 요청
4. **토큰 검증**: API Server가 공개키로 서명을 검증하여 토큰의 진위를 확인

비대칭 암호화를 사용함으로써 개인키를 가진 API Server만 토큰을 발급할 수 있고, 공개키를 가진 모든 컴포넌트(Controller Manager, Scheduler 등)가 토큰을 검증할 수 있다.

### kubelet 통신

```bash
ExecStart=/usr/local/bin/kube-apiserver \\
  ...
  --kubelet-certificate-authority=/var/lib/kubernetes/ca.crt \\
  --kubelet-client-certificate=/var/lib/kubernetes/kube-api-server.crt \\
  --kubelet-client-key=/var/lib/kubernetes/kube-api-server.key \\
  ...
```

API Server가 kubelet과 통신할 때 사용하는 인증서 설정이다.

- `--kubelet-certificate-authority`: kubelet 인증서를 검증할 CA 인증서
- `--kubelet-client-certificate`: API Server가 kubelet에 연결할 때 사용할 클라이언트 인증서
- `--kubelet-client-key`: 클라이언트 인증서의 개인키

API Server는 kubelet의 클라이언트이자 서버다:
- **서버 역할**: kubelet이 API Server에 노드 상태를 보고
- **클라이언트 역할**: API Server가 kubelet에 로그, 메트릭, exec 요청 전달

### 암호화 및 감사

```bash
ExecStart=/usr/local/bin/kube-apiserver \\
  ...
  --audit-log-maxage=30 \\
  --audit-log-maxbackup=3 \\
  --audit-log-maxsize=100 \\
  --audit-log-path=/var/log/audit.log \\
  ...
  --encryption-provider-config=/var/lib/kubernetes/encryption-config.yaml \\
  ...
```

etcd 저장 데이터 암호화와 API 요청 감사 로그 설정이다.

- `--encryption-provider-config`: etcd 저장 데이터 암호화 설정 파일 경로
- `--audit-log-path`: 감사 로그 파일 경로
- `--audit-log-maxage=30`: 감사 로그 보관 일수
- `--audit-log-maxbackup=3`: 보관할 백업 파일 수
- `--audit-log-maxsize=100`: 로그 파일 최대 크기(MB)

`encryption-provider-config`는 [6. Generating the Data Encryption Config and Key]({% post_url 2026-01-05-Kubernetes-Cluster-The-Hard-Way-06 %}) 단계에서 생성한 `encryption-config.yaml` 파일을 참조한다.

<br>

# kube-scheduler

kube-scheduler는 새로 생성된 Pod를 적절한 노드에 배치하는 역할을 한다. 노드의 리소스 가용량, Pod의 요구사항, affinity/anti-affinity, taint/toleration 등을 고려하여 최적의 노드를 선택한다.

## 설정 파일

kube-scheduler는 별도의 설정 파일(`KubeSchedulerConfiguration`)을 통해 구성된다.

```yaml
# configs/kube-scheduler.yaml
apiVersion: kubescheduler.config.k8s.io/v1
kind: KubeSchedulerConfiguration
clientConnection:
  kubeconfig: "/var/lib/kubernetes/kube-scheduler.kubeconfig"
leaderElection:
  leaderElect: true
```

주요 필드는 다음과 같다.

- `clientConnection.kubeconfig`: API Server에 연결할 때 사용할 kubeconfig 파일 경로
- `leaderElection.leaderElect: true`: 고가용성을 위한 리더 선출 활성화
    - 여러 kube-scheduler 인스턴스가 실행될 때 오직 하나만 실제 스케줄링 작업을 수행하도록 보장함
    - 리더가 실패하면 다른 인스턴스가 리더가 됨

<br>

## systemd unit 파일

```bash
cat units/kube-scheduler.service
[Unit]
Description=Kubernetes Scheduler
Documentation=https://github.com/kubernetes/kubernetes

[Service]
ExecStart=/usr/local/bin/kube-scheduler \
  --config=/etc/kubernetes/config/kube-scheduler.yaml \
  --v=2
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
```

kube-scheduler는 설정 파일에서 대부분의 옵션을 읽어오므로, unit 파일은 간단하다. 주요 옵션은 다음과 같다.

- `--config`: KubeSchedulerConfiguration 파일 경로
- `--v=2`: 로그 상세 수준

<br>

## kubeconfig 필요성

kube-scheduler는 API Server와 통신해야 하므로 kubeconfig가 필요하다:
- 스케줄링 대상 Pod 목록 조회
- 노드 정보 조회
- Pod를 노드에 바인딩(binding)

kubeconfig 파일에는 API Server 주소, 인증서, 인증 정보가 포함되어 있다. [5. Generating Kubernetes Configuration Files for Authentication]({% post_url 2026-01-05-Kubernetes-Cluster-The-Hard-Way-05-1 %}) 단계에서 생성했다.

<br>

# kube-controller-manager

kube-controller-manager는 클러스터 상태를 지속적으로 모니터링하고, 현재 상태를 원하는 상태(desired state)로 만들기 위해 동작하는 여러 컨트롤러들의 집합이다.

## systemd unit 파일

```bash
cat units/kube-controller-manager.service
[Unit]
Description=Kubernetes Controller Manager
Documentation=https://github.com/kubernetes/kubernetes

[Service]
ExecStart=/usr/local/bin/kube-controller-manager \
  --bind-address=0.0.0.0 \
  --cluster-cidr=10.200.0.0/16 \
  --cluster-name=kubernetes \
  --cluster-signing-cert-file=/var/lib/kubernetes/ca.crt \
  --cluster-signing-key-file=/var/lib/kubernetes/ca.key \
  --kubeconfig=/var/lib/kubernetes/kube-controller-manager.kubeconfig \
  --root-ca-file=/var/lib/kubernetes/ca.crt \
  --service-account-private-key-file=/var/lib/kubernetes/service-accounts.key \
  --service-cluster-ip-range=10.32.0.0/24 \
  --use-service-account-credentials=true \
  --v=2
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
```

<br>

## 주요 옵션 분석

### 네트워크 관련

Controller Manager의 네트워크 관련 설정이다.

- `--cluster-cidr=10.200.0.0/16`: Pod에 할당할 전체 CIDR 대역 
- `--service-cluster-ip-range=10.32.0.0/24`: Service에 할당할 ClusterIP 대역

`--cluster-cidr`와 `--service-cluster-ip-range`는 서로 다른 용도의 네트워크 대역이다.
- **`cluster-cidr`** (10.200.0.0/16): **Pod IP 대역**
  - Node Controller가 각 노드에 PodCIDR 할당 시 사용 (예: node-1 → 10.200.1.0/24)
  - CNI 플러그인이 이 범위에서 Pod에 IP 할당
- **`service-cluster-ip-range`** (10.32.0.0/24): **Service ClusterIP 대역**
  - API Server가 Service 생성 시 ClusterIP 할당에 사용 (예: 10.32.0.15)


<br>

### 인증서 서명

클러스터 내 CSR(Certificate Signing Request) 처리에 사용하는 CA 설정이다.

- `--cluster-signing-cert-file`: CSR 승인 시 인증서 서명에 사용할 CA 인증서
- `--cluster-signing-key-file`: CA 개인키

Kubernetes에서는 컴포넌트가 CSR(Certificate Signing Request)을 API Server에 제출할 수 있다. Controller Manager의 `csrsigning` 컨트롤러가 승인된 CSR에 대해 이 CA로 인증서를 발급한다.

<br>

### ServiceAccount 관련

ServiceAccount 토큰 발급 및 컨트롤러 인증 관련 설정이다.

- `--service-account-private-key-file`: ServiceAccount 토큰 서명에 사용할 개인키
- `--root-ca-file`: Pod에 주입할 CA 인증서
- `--use-service-account-credentials=true`: 각 컨트롤러가 개별 ServiceAccount 사용

Controller Manager는 여러 컨트롤러를 실행한다. `--use-service-account-credentials=true`로 설정하면 각 컨트롤러가 자신만의 ServiceAccount를 사용하여 API Server에 인증한다. 이는 최소 권한 원칙(Principle of Least Privilege)을 따른다.

<br>

### API Server 연결

Controller Manager가 API Server와 통신하기 위한 설정이다.

- `--kubeconfig`: API Server에 연결할 kubeconfig 파일 경로

kube-scheduler와 마찬가지로, Controller Manager도 API Server와 통신하기 위해 kubeconfig가 필요하다.

<br>

# 설정 파일 경로 정리

Control Plane 컴포넌트들이 참조하는 파일 경로를 정리한다.

## /var/lib/kubernetes

인증서, 키, kubeconfig 등 민감한 데이터가 저장되는 경로다.

| 파일 | 사용 컴포넌트 | 용도 |
| --- | --- | --- |
| `ca.crt` | apiserver, controller-manager | CA 인증서 |
| `ca.key` | controller-manager | CA 개인키 (CSR 서명용) |
| `kube-api-server.crt` | apiserver | API Server 인증서 |
| `kube-api-server.key` | apiserver | API Server 개인키 |
| `service-accounts.crt` | apiserver | SA 토큰 검증용 공개키 |
| `service-accounts.key` | apiserver, controller-manager | SA 토큰 서명용 개인키 |
| `encryption-config.yaml` | apiserver | etcd 암호화 설정 |
| `kube-controller-manager.kubeconfig` | controller-manager | API Server 연결 정보 |
| `kube-scheduler.kubeconfig` | scheduler | API Server 연결 정보 |

<br>

## /etc/kubernetes/config

설정 파일이 저장되는 경로다.

| 파일 | 사용 컴포넌트 | 용도 |
| --- | --- | --- |
| `kube-scheduler.yaml` | scheduler | 스케줄러 설정 |

<br>

## /etc/systemd/system

systemd unit 파일이 저장되는 경로다.

| 파일 | 용도 |
| --- | --- |
| `kube-apiserver.service` | API Server 서비스 정의 |
| `kube-controller-manager.service` | Controller Manager 서비스 정의 |
| `kube-scheduler.service` | Scheduler 서비스 정의 |

<br>

# 결과

이 단계를 완료하면 다음과 같은 설정 파일들이 준비된다:

1. **kube-apiserver.service**: 인증, 인가, Admission Control, etcd 연결, 암호화 설정이 포함된 systemd unit 파일
2. **kube-scheduler.yaml**: 리더 선출과 kubeconfig 경로가 설정된 스케줄러 설정 파일
3. **kube-scheduler.service**: 스케줄러 systemd unit 파일
4. **kube-controller-manager.service**: 클러스터 CIDR, 인증서 서명, ServiceAccount 설정이 포함된 systemd unit 파일

<br>

각 컴포넌트의 설정 옵션들이 서로 연관되어 있음을 확인했다:
- `--service-cluster-ip-range`는 API Server와 Controller Manager 모두에서 동일해야 함
- 인증서 파일들은 이전 단계에서 생성한 것을 참조
- kubeconfig 파일들은 각 컴포넌트가 API Server에 인증할 때 사용

<br> 

다음 단계에서는 이 설정 파일들을 server 노드에 배포하고, Control Plane 컴포넌트들을 실제로 시작한다.

