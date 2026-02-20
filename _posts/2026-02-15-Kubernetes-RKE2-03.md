---
title:  "[Kubernetes] Cluster: RKE2를 이용해 클러스터 구성하기 - 3. 인증서 관리"
excerpt: "RKE2 클러스터의 인증서 구조와 갱신 메커니즘을 확인해보자."
categories:
  - Kubernetes
toc: true
header:
  teaser: /assets/images/blog-Dev.jpg
tags:
  - Kubernetes
  - RKE2
  - Certificate
  - PKI
  - On-Premise-K8s-Hands-On-Study
  - On-Premise-K8s-Hands-On-Study-Week-7

---

*[서종호(가시다)](https://www.linkedin.com/in/gasida99/)님의 On-Premise K8s Hands-on Study 7주차 학습 내용을 기반으로 합니다.*

<br>

# TL;DR

이번 글의 목표는 **RKE2 클러스터의 인증서 관리 구조를 이해하고 실습으로 확인**하는 것이다.

- **클라이언트/서버 인증서**: 365일 유효, 만료 120일 전 자동 갱신, 수동 로테이션 가능
- **CA 인증서**: 10년 유효, 자동 갱신 없음, `rke2 certificate rotate-ca`로 수동 관리
- **CA 저장 구조**: 원본은 etcd에 암호화 저장, 디스크 파일은 부팅 시 추출되는 사본
- **Self-signed CA 교체**: cross-signing + intermediate CA로 무중단 교체 가능
- **Custom CA**: 기존 PKI 체계를 RKE2에 통합할 수 있음
- **Service Account Issuer Key**: CA와 독립적으로 로테이션 가능

<br>

# 들어가며

[이전 글]({% post_url 2026-02-15-Kubernetes-RKE2-01-02 %})에서 RKE2 서버 노드의 `server/tls/` 디렉터리에 전체 PKI가 모여 있는 것을 확인했다. CA 인증서 유효기간이 10년이고, 리프 인증서는 1년이며, 만료 120일 전에 자동 갱신된다는 것도 간단히 짚었다.

이번 글에서는 그 인증서들이 실제로 어떤 구조로 저장되고, 어떤 조건에서 갱신되며, 수동으로 로테이션해야 하는 경우 어떻게 해야 하는지를 상세히 다룬다. [Kubernetes PKI]({% post_url 2026-01-18-Kubernetes-PKI %}) 글에서 다뤘던 인증서 인프라의 기본 개념을 전제한다.

<br>

# 클라이언트/서버 인증서

## 개요

RKE2의 클라이언트/서버 인증서는 CA가 서명한 리프 인증서들이다. API 서버 서빙 인증서, kubelet 클라이언트 인증서, scheduler 클라이언트 인증서 등이 여기에 해당한다.

- **유효기간**: 발급일로부터 **365일**
- **자동 갱신**: 만료되었거나 만료 예정일로부터 **120일 이내**인 인증서는 RKE2가 시작될 때 자동으로 갱신
- **갱신 방식**: 기존 키를 재사용하고, 유효기간만 연장
- **경고 이벤트**: 인증서 만료일이 120일 이내로 남으면 Kubernetes Warning 이벤트가 `CertificateExpirationWarning` 사유로 생성

> 2025년 5월 이전 릴리즈에서는 갱신 및 경고 기준이 120일이 아닌 90일이었다.

## 자동 갱신 메커니즘

자동 갱신은 **오직 RKE2 프로세스가 시작될 때에만** 트리거된다. 장시간 재시작 없이 운영하면 인증서가 만료될 수 있다. 만료되더라도 RKE2를 재시작하면 만료된 인증서를 자동으로 갱신해 준다.

갱신 시 기존 키(private key)를 재사용한다. CSR을 새로 만들되 키 쌍은 기존 것을 쓴다는 의미다. 키를 재사용하는 이유는 다음과 같다.

1. **암호학적 안전성**: 개인키가 노출되지 않았다면, 같은 키로 새 인증서를 발급해도 보안 강도는 동일하다. ECDSA P-256(RKE2/K3s 기본) 기준으로 키 수명과 무관하게, 키가 유출되지 않은 이상 강도는 동일하다.
2. **운영 안정성**: 키를 바꾸면 해당 키를 참조하는 모든 곳을 동시에 갱신해야 한다. 예를 들어 kubelet 키가 바뀌면 `kubelet.kubeconfig`, `serving-kubelet.crt` 등이 모두 새 키와 매칭되어야 한다. 자동 갱신에서 키까지 바꾸면 rolling restart 중 불일치 위험이 생긴다. 유효기간만 연장하는 것이 **무중단 갱신의 가장 안전한 방법**이다.

키 자체를 새로 생성하고 싶으면, 아래에서 다루는 `rke2 certificate rotate` 명령으로 수동 로테이션해야 한다.

## 인증서 만료일 확인

`rke2 certificate check --output table` 명령으로 전체 인증서의 만료일을 확인할 수 있다.

```bash
rke2 certificate check --output table
INFO[0000] Server detected, checking agent and server certificates

FILENAME                           SUBJECT                             USAGES                  EXPIRES                  RESIDUAL TIME   STATUS
--------                           -------                             ------                  -------                  -------------   ------
client-scheduler.crt               system:kube-scheduler               ClientAuth              Feb 18, 2027 12:00 UTC   1 year          OK
client-scheduler.crt               rke2-client-ca@1771416044           CertSign                Feb 16, 2036 12:00 UTC   10 years        OK
kube-scheduler.crt                 kube-scheduler                      ServerAuth              Feb 18, 2027 12:00 UTC   1 year          OK
kube-scheduler.crt                 rke2-server-ca@1771416044           CertSign                Feb 16, 2036 12:00 UTC   10 years        OK
client-kubelet.crt                 system:node:week07-k8s-node1        ClientAuth              Feb 18, 2027 14:29 UTC   1 year          OK
client-kubelet.crt                 rke2-client-ca@1771416044           CertSign                Feb 16, 2036 12:00 UTC   10 years        OK
serving-kubelet.crt                week07-k8s-node1                    ServerAuth              Feb 18, 2027 14:29 UTC   1 year          OK
serving-kubelet.crt                rke2-server-ca@1771416044           CertSign                Feb 16, 2036 12:00 UTC   10 years        OK
...
```

각 파일(FILENAME)에 인증서가 2줄씩 나오는 것이 보인다. 첫 번째 줄이 리프 인증서(ClientAuth 또는 ServerAuth), 두 번째 줄이 CA 인증서(CertSign)다. 리프 인증서는 유효기간 1년, CA 인증서는 10년이다.

### 참고: 인증서 번들 구조

위 출력에서 하나의 `.crt` 파일 이름이 2줄씩 나타나는 이유는, PEM 형식의 인증서 파일에 여러 인증서가 연결(concatenate)되어 있기 때문이다.

```
-----BEGIN CERTIFICATE-----
(리프 인증서 = client-admin 본인)
-----END CERTIFICATE-----
-----BEGIN CERTIFICATE-----
(CA 인증서 = client-ca)
-----END CERTIFICATE-----
```

인증서 번들로 묶는 이유는 TLS 핸드셰이크 시 신뢰 체인을 한 번에 전달하기 위해서다. 상대방이 인증서를 검증할 때:

1. 리프 인증서를 받음 → Issuer 확인
2. Issuer인 CA 인증서가 필요 → 같은 파일에 들어 있으니 바로 확인 가능
3. CA 인증서가 신뢰할 수 있는 루트인지 검증 → 완료

리프 인증서만 단독으로 보내면, 상대방이 중간 CA를 어디서 구해야 하는지 모를 수 있다. 번들로 묶어서 보내면 검증에 필요한 체인 전체를 한 번에 제공한다.

RKE2의 실제 구조는 중간 CA 없이 **루트 CA가 직접 리프를 서명하는 2-depth 구조**이므로, 파일에는 보통 2개(리프 + 루트 CA)가 들어 있다.

```
client-admin.crt 파일 내용:
├── 인증서 1: 리프 (CN=system:admin, 유효기간 365일)
└── 인증서 2: CA  (CN=rke2-client-ca, 유효기간 10년)
```

## 수동 로테이션

키 자체를 새로 생성해야 하는 경우가 있다.

| 상황 | 대응 |
| --- | --- |
| **키 유출 의심** (노드 침해, 백업 유출 등) | `rke2 certificate rotate` — 새 키 생성 + 인증서 재발급 |
| **보안 정책상 키 로테이션 주기 준수 필요** | 수동 rotate 명령 사용 |
| **암호 알고리즘 업그레이드** (예: P-256 → P-384) | 수동 rotate 필요 |

수동 로테이션 절차는 다음과 같다.

```bash
# 1. RKE2 중지
systemctl stop rke2-server

# 2. 인증서 로테이션
rke2 certificate rotate

# 3. RKE2 시작
systemctl start rke2-server
```

개별 인증서만 로테이션할 수도 있다.

```bash
rke2 certificate rotate --service <SERVICE>,<SERVICE>
```

`<SERVICE>`에 사용할 수 있는 로테이션 가능한 서비스 목록은 다음과 같다: `admin`, `api-server`, `controller-manager`, `scheduler`, `rke2-controller`, `rke2-server`, `cloud-controller`, `etcd`, `auth-proxy`, `kubelet`, `kube-proxy`.

<br>

# CA 인증서

## 개요

RKE2는 첫 번째 서버 노드 시작 시 self-signed CA 인증서를 생성한다. 유효기간은 **10년**이며, **자동 갱신되지 않는다**.

기본 CA 구조는 intermediate CA 없이 다음과 같다.

```
Server CA (self-signed)  -->  Kubernetes servers
Client CA (self-signed)  -->  Kubernetes clients
API Aggregation CA       -->  apiserver proxy client
etcd Peer CA             -->  etcd replication
etcd Server CA           -->  Kubernetes <-> etcd
```

## 저장 및 배포 구조

CA의 원본은 etcd에 암호화 저장되고, 디스크 파일은 부팅 시 추출되는 사본이다.

```
┌─────────────────────────────────────────────┐
  etcd (datastore)                           
  └── bootstrap key                          
      └── CA cert + key (암호화 원본)         
          암호화: server token → PBKDF2 →    
                  AES256-GCM + HMAC-SHA1     
└──────────────┬──────────────────────────────┘
               │ 서버 시작 시 추출 (복호화)
               ▼
┌─────────────────────────────────────────────┐
  /var/lib/rancher/rke2/server/tls/          
  ├── server-ca.crt / .key   ← 사본(copy)    
  ├── client-ca.crt / .key   ← 사본(copy)    
  └── ...                                    
└──────────────┬──────────────────────────────┘
               │ CA key로 서명
               ▼
            리프 인증서 발급
            ├── 노드 join 시 → RKE2 서버가 직접 발급
            └── 런타임 시 → K8s CSR API (kcm signer)
```

이 구조에서 핵심적인 포인트가 몇 가지 있다.

- **CA 원본은 datastore에 저장된다.** `/var/lib/rancher/rke2/server/tls/`에 있는 파일은 사본(copy)이고, 진짜 원본은 etcd 안의 bootstrap key에 저장된다. 이 원본은 서버 토큰을 패스프레이즈로 사용해서 암호화되어 있다. PBKDF2로 서버 토큰을 암호화 키로 변환하고, AES256-GCM으로 실제 암호화하며, HMAC-SHA1로 무결성을 검증한다. 서버 토큰을 모르면 CA 키를 복호화할 수 없으므로, **토큰이 곧 클러스터 보안의 root**다.

- **디스크에 있는 파일은 사본이다.** RKE2 서버가 시작될 때마다 etcd의 bootstrap key에서 CA cert/key를 추출해서 디스크에 쓴다. 10년짜리 CA 원본이 etcd에 안전하게 보관되어 있고, 서버가 재시작될 때마다 이 원본에서 사본을 꺼내 리프 인증서를 갱신 및 발급하는 구조다.

- **어떤 서버든 리프 인증서를 발급할 수 있다.** HA 구성에서 서버가 3대면, 어느 서버든 새 노드가 join할 때 리프 인증서를 발급할 수 있다. 모든 서버가 같은 etcd에서 같은 CA cert/key 사본을 추출하기 때문에 동일한 CA로 서명 가능하다.

- **런타임에도 추가 인증서 발급이 가능하다.** 노드가 join한 뒤에도 런타임에 추가 인증서가 필요할 수 있다(예: kubelet serving cert 갱신). 이때는 RKE2 자체가 아니라 kube-controller-manager의 CSR signer가 처리한다.

## CA 인증서 갱신

`rke2 certificate rotate-ca` 명령으로 CA 인증서를 갱신한다. 이 명령은:

- 업데이트된 인증서와 키가 사용 가능한지 **무결성 검사**를 수행한다.
- 검증에 문제가 없으면, datastore의 암호화된 bootstrap key를 업데이트한다. 새 인증서와 키는 다음 RKE2 시작 시 사용된다.
- 검증 중 문제가 발견되면, 시스템 로그에 에러를 보고하고 변경 없이 작업을 취소한다.

<br>

# Self-signed CA 교체

## 문제

기존 CA로 발급된 인증서들이 클러스터 전체에 퍼져 있는 상태에서 CA를 바꾸면, 기존 인증서를 검증할 수 없게 된다. 신뢰 체인이 끊기는 것이다.

## 해결: cross-signing + intermediate CA

![rke2-self-signed-ca-rotation.png]({{site.url}}/assets/images/rke2-self-signed-ca-rotation.png)

각 CA 계열마다 아래 구조를 만든다.

```
Old CA
  |-- self-signed (기존 체인 유지용)
  |-- cross-signed (새 CA가 Old CA를 서명 → 신뢰 브릿지)
       |
       Intermediate CA (새로 발급되는 인증서들이 여기서 발급)
            |
            실제 리프 인증서들
```

cross-signed CA의 역할은, 새 Root CA가 Old CA에 서명해줌으로써 구 CA를 신뢰하는 클라이언트도 새 CA 체인을 검증할 수 있고, 새 CA를 신뢰하는 클라이언트도 구 CA 체인을 검증할 수 있는 상태를 만드는 것이다. 전환 기간 동안 양쪽이 모두 유효한 상태가 유지된다.

전체 흐름은 다음과 같다.

1. 새 Root CA 생성
2. 새 CA로 Old CA를 cross-sign
3. 각 계열에 Intermediate CA 생성
4. 새 인증서들을 Intermediate CA에서 발급
5. 클러스터 전체 롤아웃 후 Old CA 제거

이를 통해 **무중단 CA 교체**가 가능하다.

## 교체 실행

K3s/RKE2 프로젝트에서 예시 스크립트를 제공한다.

```bash
# cross-signed CA 인증서와 키 생성
curl -sL https://github.com/k3s-io/k3s/raw/master/contrib/util/rotate-default-ca-certs.sh | PRODUCT=rke2 bash -

# datastore에 업데이트된 인증서 로드 (스크립트 출력에 업데이트된 토큰 값이 포함됨)
rke2 certificate rotate-ca --path=/var/lib/rancher/rke2/server/rotate-ca
```

<br>

# Custom CA 인증서

## Custom CA Topology

조직의 기존 PKI 체계를 RKE2에 통합할 수 있다. Custom CA를 사용하면 Root CA 아래에 Intermediate CA를 두고, 그 아래에 RKE2가 사용하는 5개의 Leaf CA를 배치하는 구조가 된다.

![rke2-custom-ca-topology.png]({{site.url}}/assets/images/rke2-custom-ca-topology.png)

| CA | 용도 |
| --- | --- |
| **Server CA** | kube-apiserver, kubelet 등 서버 리스너용 TLS 인증서 발급 |
| **Client CA** | kube-apiserver, kubelet 클라이언트 인증서 발급 |
| **API Aggregation CA** | API Aggregation Layer용 — apiserver가 extension apiserver에 프록시할 때 사용 |
| **etcd Peer CA** | etcd 노드 간 replication 통신 (peer-to-peer TLS) |
| **etcd Server CA** | Kubernetes(apiserver) ↔ etcd 간 클라이언트/서버 인증서 |

Kubernetes PKI의 인증서 트리 구조에 대한 자세한 내용은 [Kubernetes PKI]({% post_url 2026-01-18-Kubernetes-PKI %}) 글을 참고한다.

## CA 재사용 주의

Root CA나 Intermediate CA를 여러 개의 클러스터에서 공유하거나, 이미 구축된 private CA를 클러스터 CA로 사용하는 것은 **권장되지 않는다**. 이유는 다음과 같다.

- 여러 클러스터가 하나의 신뢰 루트를 공유하면, 하나의 클러스터에서 발급된 리프 인증서가 다른 모든 클러스터에서도 신뢰된다. 거슬러 올라가면 같은 trust anchor이기 때문이다.
- 특정 클러스터에 대해 유효한 client certificate 혹은 kubeconfig를 가진 유저가 다른 클러스터에도 인증할 수 있다. 특정 클러스터의 RBAC이 다른 클러스터에도 적용될 수 있다.
- 하나의 클러스터에서 발급된 서버 인증서도 다른 모든 클러스터에서, 그리고 root CA를 신뢰하는 다른 인프라나 클라이언트에 의해 신뢰될 수 있다.
- Kubernetes는 **Certificate Revocation List(CRL)의 사용을 지원하지 않는다**. 특정 이유로 인증서를 revoke해야 한다면(예: compromised admin kubeconfig), 클러스터 CA 전체를 교체해야 해당 인증서의 신뢰를 무효화할 수 있다.

## Custom CA 적용

그럼에도 불구하고 custom CA를 사용하고 싶다면, 첫 번째 서버 시작 전에 CA 인증서와 키 파일을 `/var/lib/rancher/rke2/server/tls/`에 배치해야 한다.

필요한 파일 목록은 다음과 같다.

- `server-ca.crt` / `server-ca.key`
- `client-ca.crt` / `client-ca.key`
- `request-header-ca.crt` / `request-header-ca.key`
- `etcd/peer-ca.crt` / `etcd/peer-ca.key`
- `etcd/server-ca.crt` / `etcd/server-ca.key`
- `service.key` — 서비스 어카운트 토큰 서명에 사용하는 private key. 대응하는 인증서 파일은 없다.

첫 번째 서버 시작 시 CA certificate와 key가 올바른 위치에 있으면, RKE2는 CA 인증서를 자동 생성하지 않고 기존 파일을 사용한다.

K3s/RKE2 프로젝트에서 제공하는 예시 스크립트로 custom CA 인증서를 생성할 수 있다. 이 스크립트는 **RKE2 첫 시작 전에 실행해야 한다**. 이미 시작된 클러스터에는 사용할 수 없다.

```bash
mkdir -p /var/lib/rancher/rke2/server/tls

# 기존 CA 파일 복사 (있는 경우)
cp /etc/ssl/certs/root-ca.pem \
   /etc/ssl/certs/intermediate-ca.pem \
   /etc/ssl/private/intermediate-ca.key \
   /var/lib/rancher/rke2/server/tls

# 스크립트 실행
curl -sL https://github.com/k3s-io/k3s/raw/master/contrib/util/generate-custom-ca-certs.sh \
  | PRODUCT=rke2 bash -
```

기존 CA 파일 배치에 따른 동작은 다음과 같다.

| 배치 파일 | 동작 |
| --- | --- |
| **Root + Intermediate 둘 다 제공** | 둘 다 기존 것 사용 |
| **Root CA만 제공** | 스크립트가 Intermediate CA를 새로 생성 |
| **아무것도 안 넣으면** | Root CA, Intermediate CA 모두 스크립트가 새로 생성 |

스크립트가 성공적으로 완료되면 RKE2를 설치하고 시작할 수 있다. 스크립트가 root/intermediate CA 파일을 생성한 경우, 나중에 CA 인증서 로테이션이 필요할 때 재사용해야 하므로 **반드시 백업해야 한다**.

## Custom CA 인증서 갱신

custom CA 인증서를 갱신하려면 `rke2 certificate rotate-ca` 명령을 사용한다. 업데이트된 파일은 임시 디렉터리에 준비하고, datastore에 로드한 뒤, 모든 노드에서 RKE2를 재시작해야 한다.

**현재 사용 중인 데이터를 덮어쓰면 안 된다.** `/var/lib/rancher/rke2/server/tls/`의 파일을 직접 수정하지 말고, 별도 디렉터리에 준비해야 한다.

**같은 root CA를 사용하면 무중단 갱신이 가능하다.** 새 root CA가 필요하면 `--force` 옵션을 사용해야 하며, 이 경우 모든 노드(서버 및 에이전트)가 새 토큰 값으로 재설정되어야 하고, Pod도 새 root CA를 신뢰하도록 재시작되어야 하므로 중단이 발생한다.

갱신 절차는 다음과 같다.

```bash
# 임시 디렉터리 생성
mkdir -p /opt/rke2/server/tls

# root CA + intermediate CA 복사 (무중단 갱신을 위해 기존과 같은 root CA 사용)
cp /var/lib/rancher/rke2/server/tls/root-ca.* \
   /var/lib/rancher/rke2/server/tls/intermediate-ca.* \
   /opt/rke2/server/tls

# 기존 service-account signing key 복사 (기존 SA 토큰 무효화 방지)
cp /var/lib/rancher/rke2/server/tls/service.key /opt/rke2/server/tls

# 업데이트된 custom CA 인증서와 키 생성
curl -sL https://github.com/k3s-io/k3s/raw/master/contrib/util/generate-custom-ca-certs.sh \
  | DATA_DIR=/opt/rke2 PRODUCT=rke2 bash -

# datastore에 업데이트된 CA 인증서와 키 로드
rke2 certificate rotate-ca --path=/opt/rke2/server
```

성공하면 클러스터 내 모든 노드에서 RKE2를 재시작한다. **서버 먼저, 그 다음 에이전트** 순서를 지켜야 한다. 에러가 발생하면 서비스 로그를 확인한다.

<br>

# Service Account Issuer Key 로테이션

service-account issuer key는 서비스 어카운트 토큰 서명에 사용하는 RSA private key다. CA 인증서와 독립적으로 로테이션할 수 있다.

로테이션 시 **기존 키를 반드시 파일에 남겨야 한다**. 새 키만 넣으면 기존 서비스 어카운트 토큰이 무효화된다.

```bash
# 임시 디렉터리 생성
mkdir -p /opt/rke2/server/tls

# OpenSSL 버전 확인
openssl version | grep -qF 'OpenSSL 3' && OPENSSL_GENRSA_FLAGS=-traditional

# 새 키 생성
openssl genrsa ${OPENSSL_GENRSA_FLAGS:-} -out /opt/rke2/server/tls/service.key 2048

# 기존 키를 뒤에 추가 (기존 토큰 무효화 방지)
cat /var/lib/rancher/rke2/server/tls/service.key >> /opt/rke2/server/tls/service.key

# datastore에 업데이트된 키 로드
rke2 certificate rotate-ca --path=/opt/rke2/server
```

새 키가 파일 앞에, 기존 키가 뒤에 위치한다. 새로 발급되는 토큰은 새 키로 서명되고, 기존 토큰은 뒤에 남아 있는 기존 키로 여전히 검증할 수 있다.

<br>

# 실습

## 인증서 만료일 확인

서버 노드(node1)에서 인증서를 확인한다.

```bash
[root@week07-k8s-node1 ~]# rke2 certificate check --output table
INFO[0000] Server detected, checking agent and server certificates

FILENAME                           SUBJECT                             USAGES                  EXPIRES                  RESIDUAL TIME   STATUS
--------                           -------                             ------                  -------                  -------------   ------
client-scheduler.crt               system:kube-scheduler               ClientAuth              Feb 18, 2027 12:00 UTC   1 year          OK
client-scheduler.crt               rke2-client-ca@1771416044           CertSign                Feb 16, 2036 12:00 UTC   10 years        OK
kube-scheduler.crt                 kube-scheduler                      ServerAuth              Feb 18, 2027 12:00 UTC   1 year          OK
kube-scheduler.crt                 rke2-server-ca@1771416044           CertSign                Feb 16, 2036 12:00 UTC   10 years        OK
client-kubelet.crt                 system:node:week07-k8s-node1        ClientAuth              Feb 18, 2027 14:29 UTC   1 year          OK
client-kubelet.crt                 rke2-client-ca@1771416044           CertSign                Feb 16, 2036 12:00 UTC   10 years        OK
serving-kubelet.crt                week07-k8s-node1                    ServerAuth              Feb 18, 2027 14:29 UTC   1 year          OK
serving-kubelet.crt                rke2-server-ca@1771416044           CertSign                Feb 16, 2036 12:00 UTC   10 years        OK
client-rke2-controller.crt         system:rke2-controller              ClientAuth              Feb 18, 2027 14:29 UTC   1 year          OK
client-rke2-controller.crt         rke2-client-ca@1771416044           CertSign                Feb 16, 2036 12:00 UTC   10 years        OK
client-kube-apiserver.crt          system:apiserver                    ClientAuth              Feb 18, 2027 12:00 UTC   1 year          OK
client-kube-apiserver.crt          rke2-client-ca@1771416044           CertSign                Feb 16, 2036 12:00 UTC   10 years        OK
serving-kube-apiserver.crt         kube-apiserver                      ServerAuth              Feb 18, 2027 12:00 UTC   1 year          OK
serving-kube-apiserver.crt         rke2-server-ca@1771416044           CertSign                Feb 16, 2036 12:00 UTC   10 years        OK
client-admin.crt                   system:admin                        ClientAuth              Feb 18, 2027 12:00 UTC   1 year          OK
client-admin.crt                   rke2-client-ca@1771416044           CertSign                Feb 16, 2036 12:00 UTC   10 years        OK
client-auth-proxy.crt              system:auth-proxy                   ClientAuth              Feb 18, 2027 12:00 UTC   1 year          OK
client-auth-proxy.crt              rke2-request-header-ca@1771416044   CertSign                Feb 16, 2036 12:00 UTC   10 years        OK
client-rke2-cloud-controller.crt   rke2-cloud-controller-manager       ClientAuth              Feb 18, 2027 12:00 UTC   1 year          OK
client-rke2-cloud-controller.crt   rke2-client-ca@1771416044           CertSign                Feb 16, 2036 12:00 UTC   10 years        OK
client-controller.crt              system:kube-controller-manager      ClientAuth              Feb 18, 2027 12:00 UTC   1 year          OK
client-controller.crt              rke2-client-ca@1771416044           CertSign                Feb 16, 2036 12:00 UTC   10 years        OK
kube-controller-manager.crt        kube-controller-manager             ServerAuth              Feb 18, 2027 12:00 UTC   1 year          OK
kube-controller-manager.crt        rke2-server-ca@1771416044           CertSign                Feb 16, 2036 12:00 UTC   10 years        OK
client.crt                         etcd-client                         ClientAuth              Feb 18, 2027 12:00 UTC   1 year          OK
client.crt                         etcd-server-ca@1771416044           CertSign                Feb 16, 2036 12:00 UTC   10 years        OK
server-client.crt                  etcd-server                         ServerAuth,ClientAuth   Feb 18, 2027 12:00 UTC   1 year          OK
server-client.crt                  etcd-server-ca@1771416044           CertSign                Feb 16, 2036 12:00 UTC   10 years        OK
peer-server-client.crt             etcd-peer                           ServerAuth,ClientAuth   Feb 18, 2027 12:00 UTC   1 year          OK
peer-server-client.crt             etcd-peer-ca@1771416044             CertSign                Feb 16, 2036 12:00 UTC   10 years        OK
client-supervisor.crt              system:rke2-supervisor              ClientAuth              Feb 18, 2027 12:00 UTC   1 year          OK
client-supervisor.crt              rke2-client-ca@1771416044           CertSign                Feb 16, 2036 12:00 UTC   10 years        OK
client-kube-proxy.crt              system:kube-proxy                   ClientAuth              Feb 18, 2027 14:29 UTC   1 year          OK
client-kube-proxy.crt              rke2-client-ca@1771416044           CertSign                Feb 16, 2036 12:00 UTC   10 years        OK
```

에이전트 노드(node2)에서도 확인한다.

```bash
[root@week07-k8s-node2 ~]# rke2 certificate check --output table
INFO[0000] Server detected, checking agent and server certificates

FILENAME                     SUBJECT                        USAGES       EXPIRES                  RESIDUAL TIME   STATUS
--------                     -------                        ------       -------                  -------------   ------
client-kube-proxy.crt        system:kube-proxy              ClientAuth   Feb 18, 2027 16:16 UTC   1 year          OK
client-kube-proxy.crt        rke2-client-ca@1771416044      CertSign     Feb 16, 2036 12:00 UTC   10 years        OK
client-kubelet.crt           system:node:week07-k8s-node2   ClientAuth   Feb 18, 2027 16:16 UTC   1 year          OK
client-kubelet.crt           rke2-client-ca@1771416044      CertSign     Feb 16, 2036 12:00 UTC   10 years        OK
serving-kubelet.crt          week07-k8s-node2               ServerAuth   Feb 18, 2027 16:16 UTC   1 year          OK
serving-kubelet.crt          rke2-server-ca@1771416044      CertSign     Feb 16, 2036 12:00 UTC   10 years        OK
client-rke2-controller.crt   system:rke2-controller         ClientAuth   Feb 18, 2027 16:16 UTC   1 year          OK
client-rke2-controller.crt   rke2-client-ca@1771416044      CertSign     Feb 16, 2036 12:00 UTC   10 years        OK
```

서버 노드는 API 서버, scheduler, controller-manager, etcd 등 전체 컴포넌트의 인증서가 나타나지만, 에이전트 노드는 kubelet, kube-proxy, rke2-controller 인증서만 있다. 에이전트 노드에는 컨트롤 플레인 컴포넌트가 없기 때문이다.

## 인증서 수동 로테이션

서버 노드에서 인증서를 수동으로 로테이션한다.

```bash
# 1. RKE2 중지
[root@week07-k8s-node1 ~]# systemctl stop rke2-server

# 2. 인증서 로테이션
[root@week07-k8s-node1 ~]# rke2 certificate rotate
INFO[0000] Server detected, rotating agent and server certificates
INFO[0000] Rotating dynamic listener certificate
INFO[0000] Rotating certificates for api-server
INFO[0000] Rotating certificates for auth-proxy
INFO[0000] Rotating certificates for cloud-controller
INFO[0000] Rotating certificates for etcd
INFO[0000] Rotating certificates for kube-proxy
INFO[0000] Rotating certificates for kubelet
INFO[0000] Rotating certificates for admin
INFO[0000] Rotating certificates for controller-manager
INFO[0000] Rotating certificates for scheduler
INFO[0000] Rotating certificates for supervisor
INFO[0000] Rotating certificates for rke2-controller
INFO[0000] Successfully backed up certificates to /var/lib/rancher/rke2/server/tls-1771510362, please restart rke2 server or agent to rotate certificates
```

기존 인증서가 `/var/lib/rancher/rke2/server/tls-1771510362`에 백업된다. 로테이션 직후, RKE2가 중지된 상태에서 인증서를 확인하면 아무것도 나오지 않는다.

```bash
[root@week07-k8s-node1 ~]# rke2 certificate check --output table
INFO[0000] Server detected, checking agent and server certificates

FILENAME   SUBJECT   USAGES   EXPIRES   RESIDUAL TIME   STATUS
--------   -------   ------   -------   -------------   ------
```

RKE2를 시작해야 새 인증서가 발급된다.

```bash
# 3. RKE2 시작
[root@week07-k8s-node1 ~]# systemctl start rke2-server

# 4. 새 인증서 확인
[root@week07-k8s-node1 ~]# rke2 certificate check --output table
INFO[0000] Server detected, checking agent and server certificates

FILENAME                           SUBJECT                             USAGES                  EXPIRES                  RESIDUAL TIME   STATUS
--------                           -------                             ------                  -------                  -------------   ------
client-scheduler.crt               system:kube-scheduler               ClientAuth              Feb 19, 2027 14:14 UTC   1 year          OK
...
```

만료일이 `Feb 18, 2027`에서 `Feb 19, 2027`로 변경된 것을 확인할 수 있다. 로테이션 시점 기준으로 새로 365일이 부여된 것이다.

## kubeconfig 갱신

인증서 로테이션 후에는 kubeconfig의 client-certificate-data도 변경된다. 기존 kubeconfig를 그대로 사용하면 인증에 실패할 수 있으므로, 새 kubeconfig로 교체해야 한다.

```bash
# diff로 변경 확인
[root@week07-k8s-node1 ~]# diff /etc/rancher/rke2/rke2.yaml ~/.kube/config
18,19c18,19
<     client-certificate-data: LS0tLS1CRUdJTi...
<     client-key-data: LS0tLS1CRUdJTi...
---
>     client-certificate-data: LS0tLS1CRUdJTi...
>     client-key-data: LS0tLS1CRUdJTi...

# 새 kubeconfig로 교체
[root@week07-k8s-node1 ~]# yes | cp /etc/rancher/rke2/rke2.yaml ~/.kube/config

# 클러스터 접근 확인
[root@week07-k8s-node1 ~]# kubectl cluster-info
Kubernetes control plane is running at https://192.168.10.11:6443
CoreDNS is running at https://192.168.10.11:6443/api/v1/namespaces/kube-system/services/rke2-coredns-rke2-coredns:udp-53/proxy
```

## 에이전트 노드의 인증서 갱신

서버 노드에서 인증서를 로테이션한 후, 에이전트 노드(rke2-agent)는 기존 연결이 끊기면 서버에 다시 붙으면서 새 CA 기준으로 인증서를 재발급받는다. kubeadm 환경에서 인증서 갱신 시 워커 노드가 자동으로 처리되는 것과 동일한 동작이다. 워커 노드에서 인증서 갱신 작업을 수동으로 할 필요는 없다.

<br>

# 결과

RKE2 클러스터의 인증서 관리 전체 구조를 살펴봤다. 핵심 내용을 아래와 같다.

| 항목 | 내용 |
| --- | --- |
| **클라이언트/서버 인증서 유효기간** | 365일, 만료 120일 전 자동 갱신 (RKE2 시작 시) |
| **CA 인증서 유효기간** | 10년, 자동 갱신 없음 |
| **CA 원본 저장 위치** | etcd bootstrap key (AES256-GCM 암호화) |
| **디스크 CA 파일** | etcd에서 추출한 사본 |
| **자동 갱신 시 키 처리** | 기존 키 재사용, 유효기간만 연장 |
| **수동 로테이션** | `rke2 certificate rotate` — 새 키 생성 + 인증서 재발급 |
| **CA 갱신** | `rke2 certificate rotate-ca` — 무결성 검사 후 datastore 업데이트 |
| **Self-signed CA 교체** | cross-signing + intermediate CA로 무중단 교체 |
| **Custom CA** | 첫 번째 서버 시작 전 파일 배치, 기존 PKI 통합 가능 |
| **SA Issuer Key** | CA와 독립적 로테이션, 기존 키 보존 필수 |

<br>

# 참고

- [RKE2 Certificate Management](https://docs.rke2.io/security/certificates)
- [K3s Certificate Management](https://docs.k3s.io/cli/certificate)
- [Kubernetes PKI Certificates and Requirements](https://kubernetes.io/docs/setup/best-practices/certificates/)
- [K3s generate-custom-ca-certs.sh](https://github.com/k3s-io/k3s/blob/main/contrib/util/generate-custom-ca-certs.sh)
- [K3s rotate-default-ca-certs.sh](https://github.com/k3s-io/k3s/blob/main/contrib/util/rotate-default-ca-certs.sh)
