---
title:  "[Kubernetes] Kubernetes PKI"
excerpt: "Kubernetes 클러스터의 인증서 인프라에 대해 알아 보자."
categories:
  - Kubernetes
toc: true
header:
  teaser: /assets/images/blog-Dev.jpg
tags:
  - Kubernetes
  - PKI
  - TLS
  - mTLS
  - Certificate
---

<br>

# 들어가며

Kubernetes 클러스터를 구축하다 보면 수많은 인증서 파일들을 마주하게 된다. `/etc/kubernetes/pki/` 디렉토리에 ca.crt, apiserver.crt, etcd/server.crt 등 다양한 인증서들이 존재하는데, 왜 이렇게 많은 인증서가 필요한 것일까?

[Kubernetes 공식 문서](https://kubernetes.io/ko/docs/setup/best-practices/certificates/)에 따르면, 아래와 같은 문구를 확인할 수 있다.

> 쿠버네티스는 TLS를 통한 인증을 위해서 PKI 인증서가 필요하다. 만약 kubeadm으로 쿠버네티스를 설치한다면, 클러스터에 필요한 인증서는 자동으로 생성된다. 또한 더 안전하게 자신이 소유한 인증서를 생성할 수 있다.

즉, Kubernetes는 컴포넌트 간 통신을 암호화하고 상호 인증하기 위해 PKI 인증서를 사용한다. kubeadm을 사용하면 인증서가 자동 생성되어 편리하지만, 보안 요구사항에 따라 직접 인증서를 생성하여 개인키를 API Server에 저장하지 않고 별도로 관리할 수도 있다.

<br>

# 개념


Kubernetes는 클러스터 내부의 모든 컴포넌트 간 통신을 보호하기 위해 자체 Certificate Authority(CA)를 운영하고, 이를 기반으로 각 컴포넌트에 필요한 인증서를 발급/관리한다. 

Kubernetes PKI의 핵심 특징은 다음과 같다.

- 자체 Root CA를 생성한다.
- 모든 컴포넌트 인증서를 직접 발급/관리한다.
- 외부 CA에 의존하지 않는다.

> 참고: [PKI](/cs/CS-PKI)
>
> [PKI 글](/cs/CS-PKI)에서 사설 PKI는 조직 내부에서 운영하는 독립적인 PKI 시스템이라고 설명했는데, Kubernetes의 클러스터 인증서 인프라가 바로 사설 PKI의 전형적인 구현 사례다.



<br>

## 자체 PKI 구축 이유

Kubernetes가 DigiCert나 Let's Encrypt 같은 공개 CA 대신 자체 PKI를 구축하는 이유가 있다.

- **폐쇄망 운영 가능**: 인터넷 연결 없이도 인증서를 발급할 수 있다. 보안이 중요한 환경에서 외부 네트워크에 의존하지 않고 독립적으로 운영할 수 있다.
- **완전한 통제 가능**: 인증서의 만료 정책, 갱신 주기, 발급 규칙을 모두 자체적으로 결정할 수 있다. 공개 CA의 정책에 종속되지 않는다.
- **비용 절감**: 클러스터 규모에 따라 수십~수백 개의 인증서가 필요한데, 이를 모두 상업 CA에서 구매하면 비용이 막대하다. 자체 PKI는 무료다.
- **보안 강화**: 외부 CA의 개인키가 유출되어도 우리 클러스터에는 영향이 없다. 신뢰 체인이 완전히 독립적이다.



<br>

# Kubernetes PKI 구조

Kubernetes PKI는 세 개의 독립적인 CA를 운영한다. Kubernetes CA, etcd CA, front-proxy CA다.

```
kubernetes-ca (클러스터 CA)
├── kube-apiserver
├── kube-apiserver-kubelet-client
├── kube-controller-manager
├── kube-scheduler
└── kubelet (각 노드별)

etcd-ca (etcd 전용 CA)
├── etcd-server
├── etcd-peer
└── etcd-healthcheck-client

front-proxy-ca (API 확장용 CA)
└── front-proxy-client
```

etcd는 클러스터의 모든 상태를 저장하는 핵심 데이터 저장소이므로, 별도의 CA로 분리하여 더 강력한 격리를 제공한다. 

front-proxy-ca는 API Aggregation Layer에서 사용된다. 예를 들어 `kubectl top pods` 명령을 실행하면, 요청이 kube-apiserver를 거쳐 metrics-server로 프록시된다. 이때 kube-apiserver는 front-proxy-client 인증서로 metrics-server에 "나는 정당한 API Server다"라고 자신을 인증한다. metrics-server나 custom API server 같은 확장 API 서버에 요청을 프록시할 때 사용하는 별도의 신뢰 체계다.



<br>

# 인증서의 역할

Kubernetes PKI에서 인증서는 세 가지 역할로 구분된다.

## CA 인증서

클러스터의 최상위 신뢰 기관이다.

- 클러스터 생성 시 자체 서명된(self-signed) CA 인증서 생성
- 모든 컴포넌트 및 사용자 인증서에 서명
- CA의 개인키(private key)로 서명함으로써 해당 인증서의 신뢰성 보장

## 서버 인증서

서버가 자신이 정당한 서버임을 클라이언트에게 증명한다.

- API Server가 자신이 정당한 서버임을 클라이언트에게 증명
- CA에 의해 서명됨
- 클라이언트는 CA 인증서로 서버 인증서를 검증

## 클라이언트 인증서

사용자 또는 클러스터 컴포넌트의 신원을 증명한다.

- kubectl과 같은 클라이언트가 자신의 신원을 API Server에 증명
- CA에 의해 서명됨
- API Server는 CA 인증서로 클라이언트 인증서를 검증



<br>

# 인증서 생성 방법

## CA 인증서 생성

클러스터당 최초 1회 생성한다.

```bash
# 1. CA 개인키 생성
openssl genrsa -out ca.key 2048

# 2. CA 자체 서명 인증서 생성 (CSR 없이 바로 생성)
openssl req -x509 -new -nodes -key ca.key \
  -subj "/CN=kubernetes-ca" \
  -days 3650 -out ca.crt
```

## 컴포넌트 인증서 생성

각 컴포넌트마다 자신을 인증하기 위한 인증서를 생성한다.

```bash
# 1. 컴포넌트 개인키 생성
openssl genrsa -out apiserver.key 2048

# 2. CSR 생성 (공개키는 이 과정에서 자동 포함됨)
openssl req -new -key apiserver.key \
  -subj "/CN=kube-apiserver" \
  -out apiserver.csr

# 3. CA로 인증서 서명/발급
openssl x509 -req -in apiserver.csr \
  -CA ca.crt -CAkey ca.key -CAcreateserial \
  -out apiserver.crt -days 365
```



<br>

# 핵심 메커니즘: mTLS

Kubernetes 컴포넌트 간 통신은 mTLS(Mutual TLS)를 사용한다. 일반적인 TLS는 서버만 인증서를 제시하지만, mTLS는 클라이언트도 인증서를 제시하여 양방향으로 신원을 검증한다.

## mTLS 인증 과정

1. **Client → Server**: ClientHello (지원하는 암호화 알고리즘 목록 전송)
2. **Server → Client**: ServerHello + 서버 인증서 전송
3. **Client**: 서버 인증서 검증
   - CA 인증서로 서버 인증서의 서명 검증
   - 서버 인증서의 유효 기간 확인
   - 서버 인증서의 CN(Common Name) 또는 SAN(Subject Alternative Name)이 접속 중인 서버와 일치하는지 확인
4. **Client → Server**: 클라이언트 인증서 전송
5. **Server**: 클라이언트 인증서 검증
   - CA 인증서로 클라이언트 인증서의 서명 검증
   - 클라이언트 인증서의 유효 기간 확인
   - 인증서의 Organization(O) 필드로 사용자의 그룹 확인
   - 인증서의 Common Name(CN) 필드로 사용자 이름 확인
6. **양측**: 세션 키 교환 및 암호화 통신 시작

## 왜 mTLS가 필요한가

일반적인 웹 서비스에서는 서버만 인증하면 충분하다. 하지만 Kubernetes 클러스터 내부에서는 모든 통신 당사자가 신뢰할 수 있는 컴포넌트인지 확인해야 한다. 악의적인 Pod가 API Server인 척 할 수도 있고, 공격자가 kubelet인 척 할 수도 있기 때문이다. mTLS는 통신하는 양쪽 모두가 정당한 컴포넌트임을 보장한다.



<br>

# 왜 인증서가 이렇게 많은가

Kubernetes를 처음 접하면 인증서 종류가 너무 많아서 당황하게 된다. [공식 문서](https://kubernetes.io/ko/docs/setup/best-practices/certificates/)에 따르면 Kubernetes는 다음 작업에서 PKI를 필요로 한다.

- kubelet에서 API Server 인증서를 인증 시 사용하는 클라이언트 인증서
- API Server가 kubelet과 통신하기 위한 kubelet 서버 인증서
- API Server 엔드포인트를 위한 서버 인증서
- API Server에 클러스터 관리자 인증을 위한 클라이언트 인증서
- API Server에서 kubelet과 통신을 위한 클라이언트 인증서
- API Server에서 etcd 간의 통신을 위한 클라이언트 인증서
- Controller Manager와 API Server 간의 통신을 위한 클라이언트 인증서/kubeconfig
- Scheduler와 API Server 간 통신을 위한 클라이언트 인증서/kubeconfig

하지만 이해하고 보면 당연한 구조다.

> 사실 쿠버네티스만 특별히 인증서가 많은 것은 아니고, 복잡한 분산 시스템에서 높은 수준의 보안을 유지하기 위해서는 이렇게 많은 인증서가 필요하다. 같은 수준의 복잡도와 보안을 요구하는 일반 시스템도 비슷한 개수의 인증서가 필요하다.

## 통신 관계가 복잡하다

```
[API Server] ←→ [etcd]
     ↕              ↕
[kubelet]      [Controller Manager]
     ↕              ↕
[Scheduler]    [Proxy]
```

각 화살표마다 양방향 인증이 필요하다. API Server와 etcd가 통신할 때, API Server는 클라이언트로서 `apiserver-etcd-client.crt`가 필요하고, etcd는 서버로서 `etcd-server.crt`가 필요하다. etcd는 "당신이 진짜 API Server인가?"를 클라이언트 인증서로 검증하고, API Server는 "당신이 진짜 etcd인가?"를 서버 인증서로 검증한다.

## 역할이 전환된다

API Server와 kubelet의 관계를 보자. API Server가 kubelet에 로그 조회나 exec 명령을 보낼 때는 API Server가 클라이언트이고 kubelet이 서버다. 반대로 kubelet이 노드 상태를 보고할 때는 kubelet이 클라이언트이고 API Server가 서버다. 같은 두 컴포넌트 사이에서도 역할에 따라 다른 인증서가 필요하다.

## 최소 권한 원칙

만약 하나의 인증서로 모든 일을 한다면 어떻게 될까? 하나가 유출되면 전체 시스템이 위험해진다. 어떤 컴포넌트가 어떤 권한을 가지는지 불분명해지고, 감사(audit)도 어려워진다.

역할별로 인증서를 분리하면 유출 시 피해를 최소화할 수 있다. `apiserver-kubelet-client.crt`가 유출되어도 kubelet 접근만 위험하고, etcd나 다른 컴포넌트는 안전하다. 다른 인증서를 즉시 폐기할 필요도 없다.



<br>

# 필수 인증서 목록

Kubernetes 클러스터에 필요한 인증서 목록이다. kubeadm으로 설치하면 대부분 `/etc/kubernetes/pki`에 저장된다. 상세한 내용은 [공식 문서](https://kubernetes.io/ko/docs/setup/best-practices/certificates/)를 참고하자.

## CA 인증서

| 경로 | 기본 CN | 설명 |
|------|---------|------|
| ca.crt, ca.key | kubernetes-ca | Kubernetes 일반 CA |
| etcd/ca.crt, etcd/ca.key | etcd-ca | etcd 전용 CA |
| front-proxy-ca.crt, front-proxy-ca.key | kubernetes-front-proxy-ca | API 확장용 CA |

## 서버/클라이언트 인증서

| 기본 CN | 부모 CA | 종류 | 용도 |
|---------|---------|------|------|
| kube-apiserver | kubernetes-ca | server | API Server TLS |
| kube-apiserver-kubelet-client | kubernetes-ca | client | API Server → kubelet 호출 |
| front-proxy-client | kubernetes-front-proxy-ca | client | API 확장 요청 |
| kube-etcd | etcd-ca | server, client | etcd 서버 |
| kube-etcd-peer | etcd-ca | server, client | etcd 노드 간 통신 |
| kube-etcd-healthcheck-client | etcd-ca | client | etcd 헬스체크 |
| kube-apiserver-etcd-client | etcd-ca | client | API Server → etcd 접근 |

## ServiceAccount 키

| 파일 | 용도 |
|------|------|
| sa.key | ServiceAccount 토큰 서명용 개인키 |
| sa.pub | ServiceAccount 토큰 검증용 공개키 |

## 인증서와 명령어 파라미터

각 인증서는 컴포넌트 실행 시 명령어 파라미터로 지정된다. 예를 들어 kube-apiserver는 `--tls-cert-file`, `--etcd-certfile`, `--kubelet-client-certificate` 등의 파라미터로 어떤 인증서를 사용할지 지정받는다. 컴포넌트가 시작할 때 통신 상대방을 인증하고 자신을 증명하기 위해 어떤 인증서를 사용할지 알아야 하기 때문이다.

각 인증서가 어떤 명령어의 어떤 파라미터로 사용되는지에 대한 상세 매핑은 [공식 문서의 인증서 파일 경로](https://kubernetes.io/ko/docs/setup/best-practices/certificates/#인증서-파일-경로)를 참고하자.

<br>

# 실제 PKI 디렉토리 구조

kubeadm으로 설치한 클러스터의 실제 PKI 디렉토리 구조다.

```
/etc/kubernetes/pki/
├── ca.crt, ca.key                        # 클러스터 CA
├── apiserver.crt, apiserver.key          # API Server
├── apiserver-kubelet-client.crt, .key    # API Server → kubelet 클라이언트
├── apiserver-etcd-client.crt, .key       # API Server → etcd 클라이언트
├── front-proxy-ca.crt, .key              # Aggregation Layer CA
├── front-proxy-client.crt, .key          # Aggregation Layer 클라이언트
├── etcd/
│   ├── ca.crt, ca.key                    # etcd CA (별도)
│   ├── server.crt, server.key            # etcd 서버
│   ├── peer.crt, peer.key                # etcd 피어 통신
│   └── healthcheck-client.crt, .key      # etcd 헬스체크
└── sa.key, sa.pub                        # ServiceAccount 토큰 서명용
```

kubeconfig 파일은 `/etc/kubernetes/`에 저장된다. 각 kubeconfig에 포함된 인증서는 다음과 같은 CN(Common Name)과 O(Organization) 필드를 갖는다.

| 파일명 | 기본 CN | O (그룹) | 용도 |
|--------|---------|----------|------|
| admin.conf | kubernetes-admin | system:masters | 클러스터 관리자 |
| kubelet.conf | system:node:\<nodeName\> | system:nodes | 각 노드의 kubelet |
| controller-manager.conf | system:kube-controller-manager | - | controller-manager |
| scheduler.conf | system:kube-scheduler | - | scheduler |

```
/etc/kubernetes/
├── admin.conf              # 클러스터 관리자용
├── kubelet.conf            # kubelet용
├── controller-manager.conf # controller-manager용
└── scheduler.conf          # scheduler용
```

kubelet.conf의 `<nodeName>`은 API Server에 등록된 노드 이름과 정확히 일치해야 한다.



<br>

# 구축 방법

## kubeadm (권장)

kubeadm으로 클러스터를 설치하면 필요한 모든 인증서가 자동으로 생성된다. 가장 간편하고 권장되는 방법이다.

```bash
kubeadm init
```

kubeadm이 생성하는 인증서는 기본적으로 1년 후 만료된다. CA 인증서는 10년이다. 만료 전에 `kubeadm certs renew` 명령으로 갱신해야 하며, 갱신하지 않으면 클러스터 컴포넌트 간 통신이 실패한다.

## 수동 생성

학습 목적이거나 특별한 요구사항이 있는 경우 모든 인증서를 직접 생성할 수 있다. 

실제 [Kubernetes 공식 문서](https://kubernetes.io/ko/docs/setup/best-practices/certificates/#인증서-수동-설정)도 아래와 같이 말한다.
>  필요한 인증서를 kubeadm으로 생성하기 싫다면, 단일 루트 CA를 이용하거나 모든 인증서를 제공하여 생성할 수 있다.

[Kubernetes the Hard Way](https://github.com/kelseyhightower/kubernetes-the-hard-way) 문서가 이 방법을 상세히 설명한다. 실제 운영 환경에서는 권장되지 않지만, PKI 구조를 깊이 이해하는 데 도움이 된다.

> 해당 튜토리얼의 인증서 설정 파일 구조와 실제 생성 과정은 [4.2. ca.conf 파일 분석]({% post_url 2026-01-05-Kubernetes-Cluster-The-Hard-Way-04-2 %})과 [4.3. 인증서 생성 및 배포]({% post_url 2026-01-05-Kubernetes-Cluster-The-Hard-Way-04-3 %}) 글에서 확인할 수 있다. 



<br>

# 맺으며

Kubernetes PKI는 복잡해 보이지만, 결국 "누가 누구인지 확인하고, 통신을 암호화한다"는 PKI의 기본 원칙을 충실히 따른다. 인증서가 많은 이유는 컴포넌트가 많고, 각 컴포넌트가 서로 양방향 인증을 하며, 최소 권한 원칙을 따르기 때문이다.

자체 PKI를 구축함으로써 Kubernetes는 폐쇄망에서도 운영 가능하고, 완전한 통제가 가능하며, 비용을 절감하고, 외부 CA에 의존하지 않는 독립적인 보안 체계를 갖추게 된다. 처음에는 인증서 파일들이 복잡하게 느껴지겠지만, 각 인증서의 역할과 통신 흐름을 이해하면 클러스터 보안의 전체 그림이 보이기 시작한다.
