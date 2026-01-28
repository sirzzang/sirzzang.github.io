---
title:  "[Kubernetes] Cluster: 내 손으로 클러스터 구성하기 - 4.2. Provisioning a CA and Generating TLS Certificates"
excerpt: "Kubernetes 클러스터의 인증서 생성을 위한 OpenSSL 설정 파일(ca.conf)의 구조를 분석해보자."
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

이번 글의 목표는 **OpenSSL 설정 파일(ca.conf)의 구조 이해**다. [Kubernetes the Hard Way 튜토리얼의 Provisioning a CA and Generating TLS Certificates 단계](https://github.com/kelseyhightower/kubernetes-the-hard-way/blob/master/docs/04-certificate-authority.md)에서 사용하는 `ca.conf` 파일을 분석한다.

- ca.conf 파일의 전체 구조와 섹션별 역할 분석
- Root CA, Admin, Worker Node, API Server 등 각 인증서 설정 이해
- Subject 필드(CN, O)와 Kubernetes RBAC의 연동 방식
- SAN(Subject Alternative Name) 설정의 중요성

<br>

# 생성할 인증서 목록

이번 실습에서 생성할 인증서 구조는 다음과 같다. 이전 글에서 살펴본 것처럼 mTLS 기반 인증 구조에서 각 컴포넌트가 독립적인 신원을 가져야 하므로, 컴포넌트마다 별도의 인증서가 필요하다.

```
CA (Certificate Authority)
├── kube-apiserver 인증서
│   └── 용도: API 서버 식별
├── kubelet 인증서 (각 노드마다)
│   └── 용도: 워커 노드 식별  
├── kube-controller-manager 인증서
├── kube-scheduler 인증서
├── kube-proxy 인증서
├── service-accounts 인증서
└── admin 인증서
    └── 용도: kubectl로 클러스터 관리
```


| 용도 | 개인키 | CSR | 인증서 | Subject 정보 |
| --- | --- | --- | --- | --- |
| Root CA | ca.key | - | ca.crt | CN=CA |
| admin | admin.key | admin.csr | admin.crt | CN=admin, O=system:masters |
| node-0 | node-0.key | node-0.csr | node-0.crt | CN=system:node:node-0, O=system:nodes |
| node-1 | node-1.key | node-1.csr | node-1.crt | CN=system:node:node-1, O=system:nodes |
| kube-proxy | kube-proxy.key | kube-proxy.csr | kube-proxy.crt | CN=system:kube-proxy, O=system:node-proxier |
| kube-scheduler | kube-scheduler.key | kube-scheduler.csr | kube-scheduler.crt | CN=system:kube-scheduler, O=system:kube-scheduler |
| kube-controller-manager | kube-controller-manager.key | kube-controller-manager.csr | kube-controller-manager.crt | CN=system:kube-controller-manager, O=system:kube-controller-manager |
| kube-api-server | kube-api-server.key | kube-api-server.csr | kube-api-server.crt | CN=kubernetes, SAN 포함 |
| service-accounts | service-accounts.key | service-accounts.csr | service-accounts.crt | CN=service-accounts |

<br>

# ca.conf

실습에서는 위의 모든 인증서를 생성하기 위한 [설정 파일](https://github.com/kelseyhightower/kubernetes-the-hard-way/blob/master/ca.conf)을 제공해 주고 있다. 실습 환경의 편의를 위해 미리 정의된 파일을 사용하지만, 그 본질은 클러스터 내 모든 통신의 신원을 보장하는 정책을 한 데 모아 정의하는 데에 있다([출처: 박용연님 스터디 정리 글](https://yyeon2.medium.com/bootstrap-kubernetes-the-hard-way-48644e868550))

`ca.conf`는 쿠버네티스 클러스터 내 모든 컴포넌트의 TLS 인증서를 생성하기 위한 OpenSSL 설정 파일 형식을 따른다. 하나의 설정 파일에 여러 인증서 설정을 섹션별로 정의해 두고, OpenSSL 명령어 실행 시 `-section` 옵션으로 해당 섹션을 참조하여 각각의 인증서를 생성한다.

단, Root CA 생성 시에는 `-section` 옵션 없이 기본 `[req]` 섹션을 사용하고, 컴포넌트 인증서들은 각자의 섹션(admin, node-0 등)을 명시적으로 지정한다.

<br>

## 섹션별 항목 설명

*[박용연님의 1주차 스터디 정리 글](https://yyeon2.medium.com/bootstrap-kubernetes-the-hard-way-48644e868550)을 참고하였습니다.*

### 섹션 공통 구조
각 섹션 별로 아래와 같은 구조를 따른다.
- `distinguished_name`: 인증서의 주체(Subject) 정보를 어디서 가져올지 지정
- `XXX_req_extensions`: CSR을 만들 때, 추가할 확장(extension) 필드들이 어디에 있는지 지정

### req_extensions
- `basicConstraints`: CA 인증서인지 확인
- `extendedKeyUSage`: 인증서 사용 용도 지정
- `keyUsage`: 키의 사용 방식 지정
- `subjectAltName`: 해당 인증서로 접근할 수 있는 DNS 이름과 IP 주소 목록(SAN, Subject Alternative Name). 항목이 많을 경우 `@`를 사용해 별도 섹션으로 분리 가능


### distinguished_name
인증서의 Subject 정보를 정의하는 섹션이다. `CN`, `O` 등의 필드는 X.500 표준에서 유래한 Distinguished Name(DN) 구조를 따른다.
> DN 필드의 유래와 의미는 [이전 글(4.1)의 "Distinguished Name과 X.500 표준" 섹션](/kubernetes/Kubernetes-Cluster-The-Hard-Way-04-1/#distinguished-name-dn과-x500-표준)을 참고하자.

- **`CN`** (Common Name): 사용자 이름으로 매핑. `system:node:<nodeName>`, `system:kube-scheduler` 등
- **`O`** (Organization): 그룹 이름으로 매핑. `system:nodes`, `system:masters` 등

이 필드들은 RBAC 권한 부여 시 사용되므로, 올바른 값 설정이 중요하다.

<br>

## 파일 구성 확인

`ca.conf` 파일은 다음 8가지 부분으로 구성된다.

1. **Root CA**: CA 자체의 인증서 설정
2. **Admin**: kubectl 사용자 인증서
3. **Service Accounts**: ServiceAccount 토큰 서명용 인증서
4. **Worker Nodes**: kubelet 인증서 (node-0, node-1)
5. **Kube Proxy**: kube-proxy 인증서
6. **Controller Manager**: kube-controller-manager 인증서
7. **Scheduler**: kube-scheduler 인증서
8. **API Server**: kube-apiserver 인증서 (SAN 포함)
9. **공통 섹션**: 여러 인증서에서 공통으로 참조하는 설정

<br>

### Root CA

CA 자체의 인증서를 생성하기 위한 부분으로, `[req]`, `[ca_x509_extensions]`, `[req_distinguished_name]` 섹션으로 구성된다. 

```bash
[req]
distinguished_name = req_distinguished_name
prompt             = no                      # CSR 생성 시 대화형 입력 없음
x509_extensions    = ca_x509_extensions      # CA 인증서 생성 시 사용할 확장 필드: ca_x509_extensions

# x_509_extensions에 의해 바로 아래 해당 블록을 참조함
[ca_x509_extensions]                         # CA 인증서 설정 (Root of Trust)
basicConstraints = CA:TRUE                   # 이 인증서가 CA임을 명시
keyUsage         = cRLSign, keyCertSign      # CA의 핵심 권한
                                             # - keyCertSign: 다른 인증서에 서명
                                             # - cRLSign: 인증서 폐기 목록(CRL) 서명

[req_distinguished_name]
C   = US                                     # Country: 국가 코드
ST  = Washington                             # State: 주/도
L   = Seattle                                # Locality: 지역/도시
CN  = CA                                     # Common Name: 이름. 이 경우, CA로 클러스터 CA  
```

- `basicConstraints = CA:TRUE`가 설정이 핵심으로, 이 설정이 있어야 다른 인증서에 서명할 수 있는 CA 인증서가 된다
- `[req_distinguished_name]` 항목에 따라, 인증서가 생성될 때 Subject 필드에 `Subject: C=US, ST=Washington, L=Seattle, CN=CA` 값이 들어간다

> Root CA는 지리적 정보(C, ST, L)를 포함하지만, 다른 컴포넌트 인증서들은 주로 CN(사용자)과 O(그룹)만 중요하다. 

<br>

### Admin

Admin 사용자를 위한 설정이다. `[admin]`, `[admin_distinguished_name]` 섹션으로 구성된다. 

클러스터 관리자 권한을 가진 사용자(`CN=admin`)를 위한 인증서이다. 이 실습에서는 jumpbox에서 kubectl을 실행할 때 이 인증서를 사용하여 클러스터를 관리한다.
> 실제 kubectl 설정 방법은 [10. Configuring kubectl for Remote Access]({% post_url 2026-01-05-Kubernetes-Cluster-The-Hard-Way-10 %})에서 다룬다.


```bash
[admin]                                      # Admin 사용자 (kubectl)
distinguished_name = admin_distinguished_name
prompt             = no
req_extensions     = default_req_extensions

[admin_distinguished_name]
CN = admin                                   # 쿠버네티스 사용자 이름
O  = system:masters                          # 쿠버네티스 슈퍼유저 그룹, 모든 RBAC 인가 우회
```


- `O = system:masters`는 쿠버네티스의 built-in 슈퍼유저 그룹이다. 이 그룹에 속한 사용자는 모든 리소스에 대한 전체 권한을 가진다.
- kubectl은 여러 사용자 인증서를 전환하며 사용할 수 있지만, 이 실습에서는 단순화를 위해 admin 인증서만 사용한다.

<br>

### Service Accounts


`[service-accounts]`, `[service-accounts_distinguished_name]` 섹션으로 구성된다. 

ServiceAccount 토큰의 생성(서명)과 검증에 사용되는 키 쌍이다. Pod 내부에서 실행되는 애플리케이션이 API Server와 통신할 때 인증에 사용하는 토큰을 발급하고 검증하는 데 필요하다.

이후 실습 진행 과정의 kube-apiserver, kube-controller-manager 설정 과정에서 사용될 것이다.

- **kube-controller-manager**: `--service-account-private-key-file`에 개인키(`.key`)를 지정하여 ServiceAccount 토큰 생성 및 서명
- **kube-apiserver**: 
  - `--service-account-key-file`에 공개키(`.crt`)를 지정하여 Pod가 보낸 토큰 검증
  - `--service-account-signing-key-file`에 개인키(`.key`)를 지정하여 API Server도 토큰 발급 가능 (v1.20+)

> 실제 설정은 [8.1. Bootstrapping the Kubernetes Control Plane]({% post_url 2026-01-05-Kubernetes-Cluster-The-Hard-Way-08-1 %})에서 확인할 수 있다.

```bash
[service-accounts]                           # Service Account 서명자
distinguished_name = service-accounts_distinguished_name
prompt             = no
req_extensions     = default_req_extensions

[service-accounts_distinguished_name] 
CN = service-accounts                        # ServiceAccount 토큰 서명용 인증서
```
> ServiceAccount 인증서는 API Server와 통신하는 데에 사용되지 않고, 단지 Service Account 토큰을 서명하고 검증하는 데에만 사용된다. 따라서 RBAC 매핑이 필요 없어 O 필드가 필요하지 않다.

<br>

### Worker Nodes

`[node-0]`, `[node-1]` 및 각각의 하위 섹션들로 구성된다. 

kubelet이 API 서버와 통신하기 위한 인증서이다.
- kubelet 인증서는 [Node Authorizer](https://kubernetes.io/docs/reference/access-authn-authz/node/)의 요구사항을 충족해야 한다. CN은 반드시 `system:node:<nodeName>` 형식이어야 하고, O는 `system:nodes`여야 한다.
- `extendedKeyUsage`에 `clientAuth`와 `serverAuth`가 모두 포함된 이유는, kubelet이 API 서버의 클라이언트이면서 동시에 10250 포트로 HTTPS 서버를 운영하기 때문이다.

node-0과 node-1이 동일한 구조로 정의된다.

```bash
[node-0]                                       # Worker Node 인증서 (kubelet)
distinguished_name = node-0_distinguished_name # node-0_distinguished_name 참조 
prompt             = no
req_extensions     = node-0_req_extensions

[node-0_req_extensions]
basicConstraints     = CA:FALSE
extendedKeyUsage     = clientAuth, serverAuth  # 클라이언트 및 서버 인증 모두 사용
keyUsage             = critical, digitalSignature, keyEncipherment
nsCertType           = client
nsComment            = "Node-0 Certificate"
subjectAltName       = DNS:node-0, IP:127.0.0.1
subjectKeyIdentifier = hash

[node-0_distinguished_name]
CN = system:node:node-0                     # CN = system:node:<nodeName>
O  = system:nodes                           # O = system:nodes
C  = US
ST = Washington
L  = Seattle

# node-1 생략
```



<br>

### Kube Proxy

`[kube-proxy]` 및 하위 섹션들로 구성된다. 각 노드의 kube-proxy가 API 서버와 통신하기 위한 인증서이다.
- `O = system:node-proxier`는 kube-proxy에 필요한 권한을 부여하는 built-in ClusterRoleBinding과 연결된다.

```bash
[kube-proxy]                                # kube-proxy
distinguished_name = kube-proxy_distinguished_name
prompt             = no
req_extensions     = kube-proxy_req_extensions

[kube-proxy_req_extensions]
basicConstraints     = CA:FALSE
extendedKeyUsage     = clientAuth, serverAuth
keyUsage             = critical, digitalSignature, keyEncipherment
nsCertType           = client
nsComment            = "Kube Proxy Certificate"
subjectAltName       = DNS:kube-proxy, IP:127.0.0.1
subjectKeyIdentifier = hash

[kube-proxy_distinguished_name]
CN = system:kube-proxy
O  = system:node-proxier                    # 서비스 네트워크 제어 권한
C  = US
ST = Washington
L  = Seattle
```


<br>

### Controller Manager, Scheduler

Control plane 컴포넌트인 kube-controller-manager와 kube-scheduler의 인증서이다.

```bash
# Controller Manager
[kube-controller-manager]
distinguished_name = kube-controller-manager_distinguished_name
prompt             = no
req_extensions     = kube-controller-manager_req_extensions

[kube-controller-manager_req_extensions]
basicConstraints     = CA:FALSE
extendedKeyUsage     = clientAuth, serverAuth
keyUsage             = critical, digitalSignature, keyEncipherment
nsCertType           = client
nsComment            = "Kube Controller Manager Certificate"
subjectAltName       = DNS:kube-controller-manager, IP:127.0.0.1
subjectKeyIdentifier = hash

[kube-controller-manager_distinguished_name]
CN = system:kube-controller-manager
O  = system:kube-controller-manager         # 클러스터 상태 관리 권한
C  = US
ST = Washington
L  = Seattle


# Scheduler
[kube-scheduler]
distinguished_name = kube-scheduler_distinguished_name
prompt             = no
req_extensions     = kube-scheduler_req_extensions

[kube-scheduler_req_extensions]
basicConstraints     = CA:FALSE
extendedKeyUsage     = clientAuth, serverAuth
keyUsage             = critical, digitalSignature, keyEncipherment
nsCertType           = client
nsComment            = "Kube Scheduler Certificate"
subjectAltName       = DNS:kube-scheduler, IP:127.0.0.1
subjectKeyIdentifier = hash

[kube-scheduler_distinguished_name]
CN = system:kube-scheduler
O  = system:kube-scheduler                  # Pod 스케줄링 권한
C  = US
ST = Washington
L  = Seattle
```

<br>

### API Server

`[kube-api-server]` 및 하위 섹션들로 구성된다. 가장 복잡한 SAN(Subject Alternative Names) 설정을 가진다.

API 서버는 여러 경로로 접근 가능해야 하므로, 인증서에 모든 접근 주소를 SAN으로 포함해야 한다.

| 접근 경로 | 예시 |
| --- | --- |
| localhost | 127.0.0.1 |
| Service ClusterIP | 10.32.0.1 (ServiceCIDR의 첫 번째 IP) |
| 내부 DNS | kubernetes, kubernetes.default, kubernetes.default.svc 등 |
| 외부 접근용 | server.kubernetes.local, api-server.kubernetes.local |

- `10.32.0.1`은 ServiceCIDR(`10.32.0.0/24`)의 첫 번째 IP이다. 쿠버네티스는 이 IP를 `kubernetes` Service의 ClusterIP로 자동 할당한다. Pod 내부에서 API 서버에 접근할 때 이 IP를 사용한다.
- 로드밸런서나 외부 접근용 도메인을 추가해야 한다면, `[kube-api-server_alt_names]` 섹션에 해당 IP나 DNS를 추가해야 한다.


```bash
[kube-api-server]                           # API Server 인증서
distinguished_name = kube-api-server_distinguished_name
prompt             = no
req_extensions     = kube-api-server_req_extensions

[kube-api-server_req_extensions]
basicConstraints     = CA:FALSE
extendedKeyUsage     = clientAuth, serverAuth
keyUsage             = critical, digitalSignature, keyEncipherment
nsCertType           = client, server
nsComment            = "Kube API Server Certificate"
subjectAltName       = @kube-api-server_alt_names
subjectKeyIdentifier = hash

[kube-api-server_alt_names]                 # SAN: 모든 내부/외부 접근 주소
IP.0  = 127.0.0.1
IP.1  = 10.32.0.1                           # ServiceCIDR의 첫 번째 IP
DNS.0 = kubernetes
DNS.1 = kubernetes.default
DNS.2 = kubernetes.default.svc
DNS.3 = kubernetes.default.svc.cluster
DNS.4 = kubernetes.svc.cluster.local
DNS.5 = server.kubernetes.local
DNS.6 = api-server.kubernetes.local

[kube-api-server_distinguished_name]
CN = kubernetes
C  = US
ST = Washington
L  = Seattle
```


<br>

### 공통 섹션

`[default_req_extensions]`는 여러 클라이언트 인증서에서 공통으로 참조하는 설정이다.
- admin, service-accounts 인증서가 이 공통 섹션을 참조한다. 
- kubelet과 apiserver는 서버 역할도 해야 하므로 별도의 `req_extensions`를 정의한다.

```bash
[default_req_extensions]                    # 공통 CSR 확장
basicConstraints     = CA:FALSE
extendedKeyUsage     = clientAuth           # 클라이언트 인증 전용
keyUsage             = critical, digitalSignature, keyEncipherment
nsCertType           = client
nsComment            = "Admin Client Certificate"
subjectKeyIdentifier = hash
```



<br>

## 참조 동작 방식

`ca.conf` 파일은 섹션 간 참조를 통해 설정을 재사용한다.

### 단순 참조

`distinguished_name` 지시어로 Subject 정보가 담긴 섹션을 참조한다.

```
[섹션명]
distinguished_name = [다른섹션명]_distinguished_name
                     └─────────────┘
                            │
                            ▼
              [다른섹션명_distinguished_name]
              CN = ...
              O  = ...
```

### 체인 참조

`req_extensions`가 다시 `subjectAltName`을 통해 다른 섹션을 참조하는 구조이다. API Server 인증서에서 사용된다.

```
[섹션명]
req_extensions = [섹션명]_req_extensions
                          │
                          ▼
      [섹션명_req_extensions]
      subjectAltName = @[섹션명]_alt_names
                        └──────────┘
                              │
                              ▼
              [섹션명_alt_names]
              IP.0 = ...
              DNS.0 = ...
```

### 공통 참조

여러 섹션이 동일한 공통 섹션을 참조하는 구조이다.

```
[admin]                    [service-accounts]
req_extensions = default   req_extensions = default
                    │                │
                    └────────┬───────┘
                             ▼
                [default_req_extensions]
                (공통 클라이언트 설정)
```

<br>

## 실제 동작

![kubernetes-the-hard-way-ca-conf.png]({{site.url}}/assets/images/kubernetes-the-hard-way-ca-conf.png)

OpenSSL 명령어 실행 시 `-section` 옵션으로 섹션을 지정하면, 해당 섹션에서 시작하여 참조를 따라가며 설정을 읽는다.

```bash
# admin 인증서 CSR 생성 시
openssl req -new -key admin.key \
    -config ca.conf \
    -section admin \      # ← [admin] 섹션 참조
    -out admin.csr

# 내부적으로:
# 1. [admin] 섹션 읽기
# 2. distinguished_name = admin_distinguished_name 발견
# 3. [admin_distinguished_name] 섹션으로 이동 → CN, O 값 읽기
# 4. req_extensions = default_req_extensions 발견
# 5. [default_req_extensions] 섹션으로 이동 → 확장 정보 읽기
```

<br>

# 결과

이 단계를 완료하면 다음과 같은 결과를 얻을 수 있다:

1. **ca.conf 파일 구조 이해**: 하나의 파일에 여러 인증서 설정을 섹션별로 정의하고, `-section` 옵션으로 선택
2. **Subject 필드와 RBAC 연동**: CN은 사용자 이름, O는 그룹 이름으로 매핑되어 Kubernetes 인증/인가에 사용
3. **SAN(Subject Alternative Name) 설정**: API Server 인증서에 모든 접근 경로(IP, DNS)를 포함해야 함

<br>

이번 실습에서는 [Kubernetes the Hard Way 튜토리얼](https://github.com/kelseyhightower/kubernetes-the-hard-way/blob/master/configs/ca.conf)에서 제공하는 `ca.conf` 파일을 분석했다. 실무에서 인증서 갱신, 컴포넌트 추가, 커스텀 네트워크 환경 구성 시 이 글에서 분석한 각 섹션의 의미와 필드 설정 방법을 참고하면 된다.

<br> 

다음 단계에서는 이 설정 파일을 사용하여 실제로 인증서를 생성하고 확인한다.
