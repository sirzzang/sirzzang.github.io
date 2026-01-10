---
title:  "[Kubernetes] Cluster: 내 손으로 클러스터 구성하기 - 4.1. Provisioning a CA and Generating TLS Certificates"
excerpt: "Kubernetes 클러스터 구성에 필요한 TLS, mTLS, X.509, PKI 개념을 이해해 보자."
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

이번 글의 목표는 **CA 구성 및 TLS 인증서 생성 실습에 필요한 배경지식 이해**다. [Kubernetes the Hard Way 튜토리얼의 Provisioning a CA and Generating TLS Certificates 단계](https://github.com/kelseyhightower/kubernetes-the-hard-way/blob/master/docs/04-certificate-authority.md)를 수행하기 전에, TLS/mTLS/X.509/PKI 개념을 먼저 정리한다.

- TLS: 네트워크 통신 암호화 및 서버 인증 프로토콜
- mTLS: 클라이언트와 서버가 서로의 인증서를 검증하는 상호 인증 방식
- X.509: 공개키 인증서의 국제 표준 형식
- PKI: 공개키를 안전하게 배포하고 관리하기 위한 체계


<br>

# TLS

## 개요

TLS(Transport Layer Security)는 네트워크 통신을 암호화하고, 통신 상대방의 신원을 검증하는 프로토콜이다. 웹 브라우저에서 HTTPS로 접속할 때 사용되는 것이 TLS이다.

TLS의 핵심 기능은 다음과 같다.
- **암호화**: 통신 내용을 제3자가 볼 수 없도록 암호화
- **인증**: 통신 상대방이 실제로 그 서버가 맞는지 검증
- **무결성**: 전송 중 데이터가 변조되지 않았음을 보장

<br>

## TLS Handshake

클라이언트와 서버가 TLS 통신을 시작할 때, 먼저 **Handshake** 과정을 거친다. 이 과정에서 서버 인증과 세션 키 교환이 이루어진다.

```
Client                                 Server
   │                                      │
   │─────── 1. ClientHello ──────────────>│
   │        (supported cipher suites,     │
   │         TLS version, random)         │
   │                                      │
   │<────── 2. ServerHello ───────────────│
   │        (selected cipher suite,       │
   │         TLS version, random)         │
   │                                      │
   │<────── 3. Certificate ───────────────│
   │        (server's X.509 certificate)  │
   │                                      │
   │<────── 4. ServerHelloDone ───────────│
   │                                      │
   │  5. Verify server certificate        │
   │     using CA's public key            │
   │                                      │
   │─────── 6. ClientKeyExchange ────────>│
   │        (encrypted pre-master secret) │
   │                                      │
   │─────── 7. ChangeCipherSpec ─────────>│
   │                                      │
   │─────── 8. Finished ─────────────────>│
   │                                      │
   │<────── 9. ChangeCipherSpec ──────────│
   │                                      │
   │<────── 10. Finished ─────────────────│
   │                                      │
   │<═══════ Encrypted Communication ════>│
   │        (using session key)           │
```

주요 단계를 정리하면 다음과 같다.

1. **ClientHello**: 클라이언트가 지원하는 TLS 버전, 암호화 방식 목록을 서버에 전송
2. **ServerHello**: 서버가 사용할 TLS 버전, 암호화 방식을 선택하여 응답
3. **Certificate**: 서버가 자신의 인증서(공개키 포함)를 클라이언트에 전송
4. **인증서 검증**: 클라이언트가 CA의 공개키로 서버 인증서의 디지털 서명을 검증
5. **키 교환**: 클라이언트가 세션 키(대칭키)를 생성하고, 서버의 공개키로 암호화하여 전송
6. **암호화 통신 시작**: 이후 모든 통신은 세션 키로 암호화

<br>

## 인증서 검증 과정

TLS에서 클라이언트가 서버 인증서를 검증하는 과정은 다음과 같다.

1. **서버가 인증서 전송**: 인증서에는 서버의 공개키, 서버 정보, CA의 디지털 서명이 포함되어 있다
2. **클라이언트의 서명 검증**:
   - 인증서 본문을 해싱하여 해시값 생성
   - CA의 공개키로 디지털 서명을 복호화하여 해시값 추출
   - 두 해시값이 일치하면 인증서가 변조되지 않았음을 확인
3. **인증서 내용 확인**: 유효기간, 도메인 주소 등이 실제 접속하려는 서버와 일치하는지 확인

일반적인 웹 환경에서 CA의 공개키는 OS나 브라우저에 미리 내장되어 있다. DigiCert, Let's Encrypt 등 신뢰할 수 있는 CA의 루트 인증서가 Trust Store에 저장되어 있어, 별도의 설정 없이 인증서 검증이 가능하다.

<br>

## CA와 인증서 발급

### CA(Certificate Authority)

CA(Certificate Authority)는 **인증서에 서명하여 공개키의 소유자를 보증하는 기관**이다. CA가 서명한 인증서는 `이 공개키는 이 주체의 것이 맞다`는 것을 보증한다.

CA의 핵심 역할:
- 인증서 요청자의 신원 확인
- 인증서에 디지털 서명 (CA의 개인키로 서명)
- 인증서 폐기 목록(CRL) 관리

<br>

### 인증서 발급 과정 (CSR)

일반적인 인증서 발급은 **CSR(Certificate Signing Request)** 방식을 따른다. 추후 실습에서 Root CA가 아닌 컴포넌트들의 인증서를 생성할 때 따르는 과정이다.


```
┌─────────────┐        ┌─────────────┐
│   Subject   │        │     CA      │
│  (요청자)    │        │  (인증기관)  │
└──────┬──────┘        └──────┬──────┘
       │                      │
       │  1. Generate         │
       │     Key Pair         │
       │  (subject.key)       │
       │                      │
       │  2. Create CSR ─────>│
       │     (subject.csr)    │
       │     - Public Key     │
       │     - Subject Info   │
       │                      │
       │                      │  3. Verify &
       │                      │     Sign with
       │                      │     CA's private key
       │                      │
       │<──── 4. Certificate ─│
       │      (subject.crt)   │
       │                      │
```

1. **개인키 생성**: 요청자가 자신의 개인키/공개키 쌍 생성
2. **CSR 생성**: 공개키와 Subject 정보(CN, O 등)를 포함한 CSR 생성
3. **CA 서명**: CA가 CSR을 검토하고, CA의 개인키로 서명
4. **인증서 발급**: 서명된 인증서(.crt)를 요청자에게 전달

<br>

### Self-Signed 인증서

CA 없이 자기 자신이 서명한 인증서이다. 추후 실습에서 `ca.crt`(Root CA 인증서)를 생성할 때 Self-Signed 방식을 사용한다. 이후 이 CA로 다른 컴포넌트의 인증서에 서명한다. 

```
일반 인증서: 개인키 생성 → CSR 생성 → CA에 서명 요청 → 인증서 발급
Self-Signed: 개인키 생성 → 자기 자신이 서명 → 인증서 생성
```

다음과 같은 특징을 갖는다:
- Issuer(발급자)와 Subject(소유자)가 동일
- 외부 CA의 검증 없이 생성 가능
- 신뢰 체인이 없어 브라우저에서 경고 발생

<br>

# mTLS

## 개요

mTLS(mutual TLS)는 TLS의 확장으로, **클라이언트와 서버가 서로의 인증서를 검증**하는 방식이다.

- **TLS**: 클라이언트가 서버의 인증서만 검증 (서버 인증)
- **mTLS**: 서버도 클라이언트의 인증서를 검증 (상호 인증)

<br>

## mTLS Handshake

mTLS는 TLS Handshake에 클라이언트 인증서 전송 및 검증 단계가 추가된다.

```
Client                                 Server
   │                                      │
   │─────── 1. ClientHello ──────────────>│
   │                                      │
   │<────── 2. ServerHello ───────────────│
   │                                      │
   │<────── 3. Server Certificate ────────│
   │                                      │
   │<────── 4. CertificateRequest ────────│  ← mTLS: server requests
   │        (request client certificate)  │         client certificate
   │                                      │
   │<────── 5. ServerHelloDone ───────────│
   │                                      │
6. Verify server certificate              │
   │                                      │
   │─────── 7. Client Certificate ───────>│  ← mTLS: client sends
   │        (client's X.509 certificate)  │         its certificate
   │                                      │
   │─────── 8. ClientKeyExchange ────────>│
   │                                      │
   │─────── 9. CertificateVerify ────────>│  ← mTLS: client proves
   │        (signature with client key)   │         it owns the cert
   │                                      │
   │─────── 10. ChangeCipherSpec ────────>│
   │                                      │
   │─────── 11. Finished ────────────────>│
   │                                      │
   │                 12. Verify client certificate
   │                                      │
   │<────── 13. ChangeCipherSpec ─────────│
   │                                      │
   │<────── 14. Finished ─────────────────│
   │                                      │
   │<═══════ Encrypted Communication ════>│
```

TLS와의 차이점은 다음과 같다.
- **CertificateRequest** (4단계): 서버가 클라이언트에게 인증서를 요청
- **Client Certificate** (7단계): 클라이언트가 자신의 인증서를 서버에 전송
- **CertificateVerify** (9단계): 클라이언트가 인증서의 개인키 소유를 증명

<br>

## 쿠버네티스에서 mTLS가 필요한 이유

쿠버네티스는 분산 시스템으로, 수많은 컴포넌트가 네트워크를 통해 통신한다. mTLS를 사용하는 이유는 다음과 같다.
- **인증(Authentication)**: 요청을 보낸 컴포넌트가 누구인지 식별해야 한다. 인증서의 Subject 필드(CN, O 등)를 통해 `system:kube-scheduler`, `system:node:node-0` 등의 신원을 확인할 수 있다.

- **권한 부여(Authorization)와의 연동**: 인증서로 신원이 확인되면, RBAC(Role-Based Access Control)을 적용하여 해당 컴포넌트가 수행할 수 있는 작업을 제한한다.

- **내부망 침입 방어**: 공격자가 클러스터 내부 노드 하나를 장악하더라도, 유효한 인증서 없이는 다른 컴포넌트와 통신할 수 없다.

<br>

예를 들어, kubelet이 kube-apiserver와 통신할 때:
1. kube-apiserver가 자신의 인증서를 kubelet에 전송
2. kubelet이 kube-apiserver 인증서를 CA 공개키로 검증
3. kubelet이 자신의 인증서를 kube-apiserver에 전송
4. kube-apiserver가 kubelet 인증서를 CA 공개키로 검증
5. 상호 신뢰가 성립된 후 암호화 통신 시작

이 과정이 없다면, 공격자가 kubelet이나 API 서버를 위장하여 클러스터를 조작할 수 있다.

<br>

# X.509

## 개요

X.509는 ITU-T에서 정의한 **공개키 인증서의 국제 표준 형식**이다. TLS에서 사용되는 인증서는 사실상 모두 X.509 형식을 따른다.

> TLS 1.3 명세([RFC 8446](https://datatracker.ietf.org/doc/html/rfc8446#section-4.4.2))에서도 인증서 타입은 기본적으로 X.509를 사용한다고 명시되어 있다.

TLS 프로토콜 자체는 확장성을 고려하여 다른 인증서 타입도 허용하도록 설계되었다. 그러나 실제로는 다음과 같은 이유로 X.509가 사실상의 표준(de facto standard)이다.
- 전 세계 CA(DigiCert, Let's Encrypt 등)가 X.509 형식으로 인증서를 발급
- 브라우저와 OS의 Trust Store가 X.509 형식의 루트 인증서를 저장
- OpenSSL, GnuTLS 등 주요 TLS 구현체가 X.509를 기본으로 처리

<br>

쿠버네티스도 인증서 처리 로직이 Go의 `crypto/x509` 패키지에 의존한다. 그러니 이 형식을 중심으로 학습하면 된다. 

<br>

## 인증서 구조

X.509 인증서는 **본문(TBSCertificate) + 서명 알고리즘 + 디지털 서명**으로 구성된다. 본문 안에 인증서 소유자의 공개키가 포함되어 있다.
> 실습에서 `openssl`로 인증서를 생성하고 `openssl x509 -text`로 내용을 확인할 때, 위 구조를 직접 볼 수 있다.

```
+--------------------------------------------------+
|        TBSCertificate (To Be Signed)             |
+--------------------------------------------------+
| 1. Version: v3                                   |
| 2. Serial Number: 01:23:45:67:89                 |
| 3. Signature Algorithm: SHA-256 with RSA         |
| 4. Issuer: CN=MyLocalCA                          |  ← *실습: ca.conf의 CA 섹션*
| 5. Validity:                                     |
|    - Not Before: 2026-01-01                      |
|    - Not After: 2027-01-01                       |
| 6. Subject: CN=my-kubernetes-node-1              |  ← *실습: 각 컴포넌트별 설정*
| 7. Subject Public Key Info:                      |
|    - Algorithm: RSA (2048 bit)                   |
|    - Public Key: 0xAF31...                       |
| 8. Extensions:                                   |
|    - SAN: DNS:node1.example.com, IP:192.168.1.10 |  ← *실습: kube-api-server 등*
|    - Key Usage: Digital Signature                |
+--------------------------------------------------+

+--------------------------------------------------+
| Signature Algorithm: SHA-256 with RSA            |
+--------------------------------------------------+

+--------------------------------------------------+
| Signature Value: 0x82...FA                       |
| (TBSCertificate hashed and signed with CA's key) |
+--------------------------------------------------+
```


주요 구성 요소는 다음과 같다.
- **본문(TBSCertificate)**: 서명 대상이 되는 인증서 정보. 소유자의 공개키가 포함됨
- **서명 알고리즘**: 본문을 해싱하고 서명할 때 사용한 알고리즘 (예: SHA-256 with RSA)
- **서명 값(Signature)**: CA가 본문을 해싱한 후 자신의 개인키로 암호화한 값

클라이언트가 인증서를 검증하는 과정은 다음과 같다.
1. 서명 값을 CA의 공개키로 복호화하여 해시값 추출
2. 본문을 동일한 알고리즘으로 해싱하여 해시값 생성
3. 두 해시값이 일치하면 인증서가 유효하다고 판단하고, 본문 내의 공개키를 신뢰

<br>

<br>

## Distinguished Name (DN)과 X.500 표준

X.509 인증서의 Subject와 Issuer 필드에서 사용하는 `CN`, `O`, `OU`, `C` 같은 필드들은 **X.500 디렉토리 서비스 표준**에서 유래했다.

X.500은 국제 전기통신 연합(ITU-T)이 정의한 디렉토리 서비스 표준으로, 계층적 구조로 개체를 식별하기 위한 **Distinguished Name (DN)** 체계를 제공한다. X.509는 X.500의 인증서 표준으로 만들어졌기 때문에, 동일한 DN 구조를 사용한다.

### 주요 DN 필드

| 필드 | 의미 | 예시 |
|------|------|------|
| **CN** (Common Name) | 주체의 이름 | `CN=admin`, `CN=kubernetes` |
| **O** (Organization) | 조직명 | `O=system:masters` |
| **OU** (Organizational Unit) | 조직 단위 | `OU=Engineering` |
| **L** (Locality) | 지역/도시 | `L=Seattle` |
| **ST** (State) | 주/도 | `ST=Washington` |
| **C** (Country) | 국가 코드 | `C=US` |

### LDAP와의 관계

LDAP(Lightweight Directory Access Protocol)는 X.500의 경량화 버전으로, 동일한 DN 구조를 사용한다. 그래서 [LDAP 디렉토리 서비스를 사용했던 경험](https://sirzzang.github.io//articles/Articles-Opensource-Contribution/#%EC%84%B1%EA%B3%B5%EA%B8%B0)이 있다면, 인증서에서도 동일한 필드들을 보게 된다.

LDAP의 DN은 아래와 같이 구성된다.
```bash
# LDAP DN 예시
dn: CN=John Doe,OU=Engineering,O=Acme Corp,C=US
```

X.509 인증서의 Subject도 동일한 구조를 따른다.
```bash
# X.509 인증서 Subject 예시
Subject: CN=admin, O=system:masters, C=US
```

이러한 표준화된 필드 덕분에 인증서, 디렉토리 서비스, Kerberos 등 다양한 인증/인가 시스템이 일관된 방식으로 주체를 식별할 수 있다.

<br>

## 쿠버네티스에서 중요한 필드

쿠버네티스 인증서에서 특히 중요한 필드가 있다. 이후 [](링크)에서 `ca.conf` 파일을 작성할 때 이 필드들을 직접 만나보게 될 것이다.

### Subject

인증서 소유자를 식별하는 필드이다. CN(Common Name)과 O(Organization)가 쿠버네티스의 사용자 이름과 그룹 이름으로 매핑된다.
> 실습에서 admin, kube-scheduler, kube-controller-manager 등의 인증서를 생성할 때 각각 다른 Subject를 지정한다.

```
Subject: CN=admin, O=system:masters
         │         └─ 그룹: system:masters
         └─ 사용자: admin
```

### SAN(Subject Alternative Name)

하나의 인증서로 여러 호스트명이나 IP에서 유효하도록 한다. kube-apiserver 인증서의 경우 클러스터 내부 IP, 로드밸런서 IP, kubernetes.default 등 여러 값을 포함해야 한다.

> 실습에서 kube-api-server 인증서 생성 시 `subjectAltName` 확장 필드를 설정한다.

### Key Usage / Extended Key Usage
인증서의 용도를 명시한다.
- 서버 인증용(`serverAuth`)
- 클라이언트 인증용(`clientAuth`)

<br>

# PKI

## 개요

PKI(Public Key Infrastructure)는 **공개키를 안전하게 배포하고 관리하기 위한 체계**이다. CA, 인증서, 신뢰 저장소 등이 PKI의 구성 요소이다.

PKI가 해결하는 핵심 문제는 **중간자 공격(Man-In-The-Middle)**이다. 공개키를 배포할 때, 해당 공개키가 정말 의도한 상대방의 것인지 검증할 수 없다면, 공격자가 자신의 공개키를 대신 전달하여 통신을 가로챌 수 있다. PKI는 신뢰할 수 있는 CA가 `이 공개키는 이 주체의 것이 맞다`고 보증하는 인증서를 발급함으로써 이 문제를 해결한다.

<br>

## 구성 요소

PKI의 주요 구성 요소는 다음과 같다.

- **CA(Certificate Authority)**: 인증서에 서명하여 공개키의 소유자를 보증하는 기관
- **인증서(Certificate)**: 공개키와 소유자 정보, CA의 서명을 포함한 문서. X.509 형식
- **신뢰 저장소(Trust Store)**: 신뢰할 수 있는 CA의 루트 인증서 목록
- **CRL/OCSP**: 폐기된 인증서 목록 또는 인증서 상태 확인 프로토콜

<br>

## 쿠버네티스에서의 PKI

일반적인 웹 환경에서는 DigiCert, Let's Encrypt 같은 외부 CA를 사용하지만, 쿠버네티스에서는 **클러스터 관리자가 직접 CA를 운영**한다.

쿠버네티스 PKI의 특징:
- 클러스터 관리자가 Root CA를 생성하고, 모든 컴포넌트에 인증서를 발급 ← *실습에서 `openssl`로 직접 수행*
- CA의 개인키(`ca.key`)는 마스터 노드의 `/etc/kubernetes/pki/` 디렉토리에 보관
- CA의 공개키(루트 인증서, `ca.crt`)는 클러스터 내 모든 노드에 배포 ← *실습에서 `scp`로 배포*
- 각 컴포넌트는 `--client-ca-file` 옵션으로 CA 인증서 경로를 지정받아, 상대방 인증서를 검증

쿠버네티스 설치 시 많은 `.crt`, `.key` 파일을 생성하고 복사하는 이유가 바로 이 PKI 구성 때문이다. kubeadm 같은 도구는 이 과정을 자동화해주는 것이고, 지금 실습에서는 이를 직접 수행하는 것이다.

<br>

# 결과

이 단계를 완료하면 다음과 같은 개념을 이해할 수 있다:

| 개념 | 설명 |
|------|------|
| **TLS** | 통신 암호화 및 서버 인증 프로토콜 |
| **mTLS** | 클라이언트와 서버가 서로의 인증서를 검증하는 상호 인증 방식 |
| **X.509** | 공개키 인증서의 국제 표준 형식 |
| **PKI** | 공개키를 안전하게 배포하고 관리하기 위한 체계 |
| **CA** | 인증서에 서명하여 공개키 소유자를 보증하는 기관 |

<br>

쿠버네티스는 클러스터 내 모든 통신에 mTLS를 적용하여 보안을 강화한다. <br> 

다음 단계에서는 인증서 생성에 사용할 OpenSSL 설정 파일(ca.conf)의 구조를 분석한다.

