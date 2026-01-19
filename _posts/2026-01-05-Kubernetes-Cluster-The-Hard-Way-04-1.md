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

이번 글의 목표는 **CA 구성 및 TLS 인증서 생성 실습에 필요한 배경지식 이해**다. [Kubernetes the Hard Way 튜토리얼의 Provisioning a CA and Generating TLS Certificates 단계](https://github.com/kelseyhightower/kubernetes-the-hard-way/blob/master/docs/04-certificate-authority.md)를 수행하기 전에, TLS/mTLS/X.509/PKI 개념이 쿠버네티스에서 왜 중요한지 먼저 정리한다.

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

X.509는 ITU-T에서 정의한 **공개키 인증서의 국제 표준 형식**이다. TLS에서 사용되는 인증서는 사실상 모두 X.509 형식을 따르며, 쿠버네티스도 인증서 처리 로직이 Go의 `crypto/x509` 패키지에 의존한다.

- 인증서 구조와 검증 과정에 대한 자세한 내용은 [X.509 인증서 글의 인증서 구조](/cs/CS-X509-Certificate/#인증서-구조)를 참고하자.
- DN 체계(CN, O 등)에 대한 자세한 내용은 [X.509 인증서 글의 Distinguished Name](/cs/CS-X509-Certificate/#distinguished-name-dn과-x500-표준)을 참고하자.

> 실습에서 `openssl`로 인증서를 생성하고 `openssl x509 -text`로 내용을 확인할 때 다음 필드를 직접 볼 수 있다:
> - **Issuer**: `ca.conf`의 `[ca]` 섹션에서 설정한 CA 정보
> - **Subject**: 각 컴포넌트별 `[req_distinguished_name]` 섹션에서 설정한 CN, O 값
> - **SAN**: `kube-apiserver` 등 `[alt_names]` 섹션에서 설정한 DNS, IP 값

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

PKI(Public Key Infrastructure)는 공개키를 안전하게 배포하고 관리하기 위한 체계다. PKI의 핵심은 중간자 공격을 방지하는 것으로, 신뢰할 수 있는 CA(Certificate Authority)가 "이 공개키는 이 주체의 것이 맞다"고 보증하는 인증서를 발급함으로써 이 문제를 해결한다.

인증서 발급은 CSR(Certificate Signing Request) 방식을 따르며, Root CA는 Self-Signed 인증서로 생성된다.

- PKI의 개념, 구성 요소, 실제 사용 사례에 대한 자세한 내용은 [PKI 글]({% post_url 2026-01-18-CS-PKI %})을 참고하자.
- CA와 CSR 발급 과정에 대한 자세한 내용은 [PKI 글의 인증서 발급 프로세스](/cs/CS-PKI/#인증서-발급-프로세스)를 참고하자.
- Self-Signed 인증서에 대한 자세한 내용은 [인증서 글의 루트 인증서](/cs/CS-Security-Certificate/#루트-인증서)를 참고하자.

> 추후 실습에서 Root CA가 아닌 컴포넌트들의 인증서를 생성할 때 CSR 방식을 따른다. `ca.crt`(Root CA 인증서)는 Self-Signed 방식으로 생성하고, 이 CA로 다른 컴포넌트의 인증서에 서명한다.

<br>

## 쿠버네티스에서의 PKI

일반적인 웹 환경에서는 DigiCert, Let's Encrypt 같은 외부 CA를 사용하지만, 쿠버네티스에서는 **클러스터 관리자가 직접 CA를 운영**한다. 자체 PKI를 구축하는 이유와 전체 인증서 구조에 대한 자세한 내용은 [Kubernetes PKI 글]({% post_url 2026-01-18-Kubernetes-PKI %})을 참고하자.

쿠버네티스 설치 시 수많은 `.crt`, `.key` 파일을 생성해야 하는데, kubeadm 같은 도구는 이 과정을 자동화해주는 것이고, 지금 실습에서는 이를 직접 수행하는 것이다.

- 클러스터 관리자가 Root CA를 생성하고, 모든 컴포넌트에 인증서를 발급 ← *실습에서 `openssl`로 직접 수행*
- CA의 개인키(`ca.key`)는 마스터 노드의 `/etc/kubernetes/pki/` 디렉토리에 보관
- CA의 공개키(루트 인증서, `ca.crt`)는 클러스터 내 모든 노드에 배포 ← *실습에서 `scp`로 배포*
- 각 컴포넌트는 `--client-ca-file` 옵션으로 CA 인증서 경로를 지정받아, 상대방 인증서를 검증


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

