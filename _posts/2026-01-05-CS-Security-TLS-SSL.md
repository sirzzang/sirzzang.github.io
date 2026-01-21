---
title:  "[Security] TLS/SSL 프로토콜"
excerpt: "TLS와 mTLS에 대해 알아 보자."
categories:
  - CS
toc: true
header:
  teaser: /assets/images/blog-Dev.jpg
tags:
  - Security
  - 보안
  - TLS
  - SSL
  - HTTPS
  - mTLS
---


<br>

# 개념

TLS(Transport Layer Security)는 네트워크 통신을 **암호화**하는 프로토콜이다. 기밀성, 무결성, 인증을 제공하며, HTTPS, 이메일, VPN 등 대부분의 보안 통신에서 사용된다.

## TLS와 SSL

TLS와 SSL은 같은 목적의 프로토콜이지만, SSL은 TLS의 전신이다.

- **SSL(Secure Sockets Layer)**: 초기 버전으로 Netscape가 개발 (SSL 2.0, 3.0)
- **TLS(Transport Layer Security)**: SSL의 후속 버전으로 IETF가 표준화 (현재 표준)

> SSL은 취약점이 발견되어 더 이상 사용하지 않으며, 현재는 **TLS 1.2 / TLS 1.3**이 표준이다. 관습적으로 "SSL 인증서"라고 부르기도 하지만, 실제로는 TLS를 사용한다.


### 버전 히스토리

TLS/SSL의 버전별 역사를 살펴보면 다음과 같다:
- SSL 2.0: 1995년에 출시되었으나 심각한 취약점으로 인해 폐기
- SSL 3.0: 1996년에 출시되었으나 POODLE 공격에 취약하여 2015년 공식 폐기
- TLS 1.0: 1999년에 출시되었으나 여러 취약점이 발견되어 더 이상 권장되지 않으며, 2020년부터 주요 브라우저에서 지원 중단
- TLS 1.1: 2006년에 출시되었으나 마찬가지로 권장되지 않으며 2020년부터 지원 중단
- TLS 1.2: 2008년에 출시되어 현재 가장 널리 사용되는 표준이며 안전한 것으로 평가됨
- TLS 1.3: 2018년에 출시된 최신 표준으로, 더 빠르고 안전하며 핸드셰이크가 단순화됨

### 권장 사항

보안과 호환성을 고려한 TLS 버전 선택 기준은 다음과 같다:

- 최소 TLS 1.2 이상 사용
- 가능하면 TLS 1.3 사용
- SSL 및 TLS 1.0/1.1은 비활성화

## 보안 목표

TLS는 세 가지 핵심 보안 목표를 달성한다:

1. **기밀성(Confidentiality)**: 대칭키 암호화로 보장하며, AES-GCM, ChaCha20-Poly1305 등의 알고리즘을 사용함
2. **무결성(Integrity)**: MAC(Message Authentication Code) 또는 HMAC을 통해 데이터 변조 방지
3. **인증(Authentication)**: [X.509 인증서](/cs/CS-X509-Certificate/)와 디지털 서명을 통해 통신 상대방의 신원 확인

## Cipher Suite

Cipher Suite는 TLS/SSL 통신에서 사용할 암호화 알고리즘들의 조합을 정의한 집합이다. 데이터를 안전하게 주고받기 위해서는 키 교환, 인증, 암호화, 무결성 검증 등 여러 단계가 필요하고, 각 단계마다 서로 다른 암호화 알고리즘이 사용된다. Cipher Suite는 이 모든 알고리즘을 하나의 패키지로 묶어 명명한 것이다.

핸드셰이크 과정에서 클라이언트는 자신이 지원하는 Cipher Suite 목록을 서버에 제시하고, 서버는 그 중 자신도 지원하면서 가장 안전한 것을 선택한다. 이렇게 협상된 Cipher Suite가 이후 통신 전체에 적용된다.

Cipher Suite는 다음 네 가지 요소로 구성된다:

1. **키 교환 알고리즘**: RSA, ECDHE (Elliptic Curve Diffie-Hellman Ephemeral) 등
2. **인증 알고리즘**: RSA, ECDSA 등
3. **대칭키 암호화 알고리즘**: AES-128-GCM, AES-256-GCM, ChaCha20-Poly1305 등
4. **해시 함수**: SHA-256, SHA-384 등

예시는 다음과 같다.

```plaintext
TLS_ECDHE_RSA_WITH_AES_128_GCM_SHA256
│   │     │   │    └─────┬─────┘ │
│   │     │   │          │       └─── 4. 해시/PRF: SHA-256
│   │     │   │          └─────────── 3. 대칭키 암호화: AES-128-GCM
│   │     │   │                          (알고리즘_키길이_운용모드)
│   │     │   └────────────────────── 구분자
│   │     └────────────────────────── 2. 인증 알고리즘: RSA
│   └──────────────────────────────── 1. 키 교환 알고리즘: ECDHE (PFS 지원)
└──────────────────────────────────── 프로토콜: TLS
```

### 권장 Cipher Suite

보안성과 성능을 고려한 권장 조합이다. TLS 1.3에서는 키 교환과 인증 알고리즘이 별도로 협상되므로 Cipher Suite 이름이 간소화되었다.

- TLS 1.3: TLS_AES_256_GCM_SHA384, TLS_CHACHA20_POLY1305_SHA256
- TLS 1.2: TLS_ECDHE_RSA_WITH_AES_256_GCM_SHA384 (ECDHE로 PFS 보장)

<br>

# TLS 연결 단계

TLS 연결은 크게 두 단계로 나뉜다.

1. **핸드셰이크 단계**: 연결 수립. Cipher Suite 협상, 서버 인증, 세션 키 교환이 이루어진다.
2. **데이터 전송 단계**: 암호화 통신. 핸드셰이크에서 생성한 세션 키로 데이터를 암호화하여 주고받는다.

<br>

# TLS 핸드셰이크

핸드셰이크는 TLS 연결의 첫 단계로, 암호화 통신에 필요한 모든 준비를 마친다. TLS 1.2와 1.3의 핸드셰이크는 구조가 다르다.

## TLS 1.2

> 참고: 다이어그램 범례
>
> 이하 섹션에서 사용되는 다이어그램 표기법은 다음과 같다:
>
> ```plaintext
> ───>  : 단방향 메시지 전송
> <──   : 단방향 메시지 수신
> <══>  : 양방향 암호화 통신
> [  ]  : 내부 처리 과정 (메시지 전송 없음)
> ```

### 기본 흐름 (서버 인증만)

가장 일반적인 TLS 핸드셰이크다. 클라이언트가 서버의 신원을 확인하고, 암호화 통신에 사용할 세션키를 교환한다. 웹 브라우저로 HTTPS 사이트에 접속할 때 이 방식이 사용된다.

서버만 인증서를 제시하고, 클라이언트 인증은 필요 시 애플리케이션 레벨(ID/비밀번호, OAuth 등)에서 처리한다.

TLS 1.2 핸드셰이크는 **2-RTT(Round Trip Time)**가 필요하다. 클라이언트와 서버 간에 2번의 왕복 통신을 거쳐야 암호화된 데이터를 주고받을 수 있다.

- **1st RTT**: ClientHello → ServerHello + Certificate
- **2nd RTT**: ClientKeyExchange + ChangeCipherSpec + Finished → ChangeCipherSpec + Finished

```plaintext
        ┌─────────────┐                              ┌─────────────┐
        │   Client    │                              │   Server    │
        └──────┬──────┘                              └──────┬──────┘
               │                                            │
               │  1. ClientHello                            │
  1st RTT ─┬── │───────────────────────────────────────────>│
           │   │                                            │
           │   │  2. ServerHello + Certificate              │
           └── │<───────────────────────────────────────────│
               │                                            │
            3. [Verify Server Certificate]                  │
               │                                            │
               │  4. ClientKeyExchange (Session Key)        │
  2nd RTT ─┬── │───────────────────────────────────────────>│
           │   │                                            │
           │   │  5. Encrypted Communication                │
           └── │<══════════════════════════════════════════>│
               │                                            │
```

<br>

### 상세 흐름 (서버 인증만)

TLS 1.2 핸드셰이크 과정을 상세히 살펴보면 다음과 같다:

```plaintext
┌─────────────┐                              ┌─────────────┐
│   Client    │                              │   Server    │
└──────┬──────┘                              └──────┬──────┘
       │                                            │
       │  1. ClientHello                            │
       │  - TLS version (1.2)                       │
       │  - Supported cipher suites                 │
       │  - clientRandom (32 bytes)                 │
       │  - SNI (Server Name Indication)            │
       │───────────────────────────────────────────>│
       │                                            │
       │  2. ServerHello                            │
       │  - Selected TLS version                    │
       │  - Selected cipher suite                   │
       │  - serverRandom (32 bytes)                 │
       │<───────────────────────────────────────────│
       │                                            │
       │  3. Certificate (Server's X.509 Cert)      │
       │<───────────────────────────────────────────│
       │                                            │
       │  4. ServerHelloDone                        │
       │<───────────────────────────────────────────│
       │                                            │
   [Client: Verify Server Cert]                     │
     - Check CA signature                           │
     - Verify domain match (SNI)                    │
     - Check validity period                        │
     - Check revocation (OCSP/CRL)                  │
       │                                            │
       │  5. ClientKeyExchange                      │
       │  - PMS encrypted with server public key    │
       │───────────────────────────────────────────>│
       │                                            │
       │   [Both: Generate Session Keys]            │
       │    - Master Secret from PMS + randoms      │
       │    - Derive encryption/MAC keys            │
       │                                            │
       │  6. ChangeCipherSpec                       │
       │───────────────────────────────────────────>│
       │                                            │
       │  7. Finished (encrypted)                   │
       │  - HMAC of all handshake msgs              │
       │───────────────────────────────────────────>│
       │                                            │
       │  8. ChangeCipherSpec                       │
       │<───────────────────────────────────────────│
       │                                            │
       │  9. Finished (encrypted)                   │
       │  - HMAC of all handshake msgs              │
       │<───────────────────────────────────────────│
       │                                            │
       │  ═══════ Encrypted Communication ════════  │
       │<══════════════════════════════════════════>│
       │                                            │
```

<br>

**1. ClientHello**

클라이언트가 서버에게 연결 요청을 보낸다.

- 지원하는 TLS 버전 (예: TLS 1.2)
- 지원하는 암호화 알고리즘 목록 (Cipher Suite)
- **clientRandom**: 32바이트 랜덤 값 (나중에 키 생성에 사용)
- **SNI (Server Name Indication)**: 접속하려는 도메인 이름 (하나의 IP에 여러 도메인이 있을 때 필요)

<br>

**2. ServerHello**

서버가 응답한다.

- 선택된 TLS 버전
- 선택된 Cipher Suite
- **serverRandom**: 32바이트 랜덤 값

<br>

**3-4. Certificate + ServerHelloDone**

서버가 인증서를 전송하고 협상 완료를 알린다.

- **서버 인증서**: 서버의 공개키, 서버 정보(도메인 등), CA의 디지털 서명이 포함됨
- **ServerHelloDone**: 서버 측 협상 메시지 완료 신호

<br>

**인증서 검증 (클라이언트 내부 동작)**

클라이언트가 수신한 서버 인증서를 검증한다.

1. **디지털 서명 검증**: 인증서 본문을 해싱하여 해시값 생성 후, CA의 공개키로 서명을 복호화하여 두 해시값 비교
2. **도메인 일치 확인**: SNI와 인증서의 CN 또는 SAN 비교
3. **유효기간 확인**: 현재 시간이 인증서 유효 기간 내인지 확인
4. **폐기 확인**: OCSP 또는 CRL을 통해 인증서가 폐기되지 않았는지 확인. TLS 핸드셰이크에서는 [OCSP Stapling](/cs/CS-PKI/#ocsp-stapling)을 통해 이 과정을 최적화할 수 있다.

일반적인 웹 환경에서 CA의 공개키는 OS나 브라우저에 미리 내장되어 있다. DigiCert, Let's Encrypt 등 신뢰할 수 있는 CA의 루트 인증서가 Trust Store에 저장되어 있어, 별도의 설정 없이 인증서 검증이 가능하다.

<br>

**5. ClientKeyExchange**

대칭키(세션키)를 생성하기 위한 PMS(Pre-Master Secret)를 교환한다.

- 클라이언트가 48바이트 PMS 생성
- 서버의 공개키(RSA)로 암호화하여 전송
- 서버는 자신의 개인키로 복호화

<br>

**세션 키 생성 (양쪽 내부 동작)**

클라이언트와 서버가 동일한 방식으로 세션 키를 생성한다. 생성 방식은 다음과 같다:

1. Master Secret 생성
  ```bash
  Master Secret = PRF(PMS, "master secret", clientRandom + serverRandom)
  ```
2. 세션 키 생성
  ```bash
  Key Block = PRF(Master Secret, "key expansion", serverRandom + clientRandom)
  ```
3. Key Block에서 다음 키들을 추출
  - Client Write MAC Key (메시지 인증)
  - Server Write MAC Key
  - Client Write Encryption Key (데이터 암호화)
  - Server Write Encryption Key
  - Client Write IV (초기화 벡터)
  - Server Write IV

PRF(Pseudo-Random Function)는 TLS에서 정의한 키 유도 함수로, HMAC-SHA256 등을 기반으로 한다.

<br>

**6-9. ChangeCipherSpec + Finished**

양쪽이 세션키를 생성했으므로 암호화 통신으로 전환한다.

- **ChangeCipherSpec**: "이제부터 암호화 통신 시작"
- **Finished**: 지금까지의 모든 핸드셰이크 메시지를 HMAC으로 검증하여 변조 여부 확인

<br>

## TLS 1.3

TLS 1.3은 1.2에 비해 크게 개선되었다.

### 핸드셰이크 단순화

TLS 1.3은 TLS 1.2에 비해 핸드셰이크 라운드트립을 단축했다.
- 1.2: 2-RTT
- 1.3: 1-RTT, 0-RTT 재개(이전 연결 정보 재사용) 지원

```plaintext
┌─────────────────────────────────────────────────────────────────────────────┐
│ TLS 1.2: 2-RTT                                                              │
├─────────────────────────────────────────────────────────────────────────────┤
│  Client                                              Server                 │
│    │                                                    │                   │
│    │  1. ClientHello                                    │                   │
│    │───────────────────────────────────────────────────>│  ─┬─ 1st RTT      │
│    │                                                    │   │               │
│    │  2. ServerHello + Certificate + ServerHelloDone    │   │               │
│    │<───────────────────────────────────────────────────│  ─┘               │
│    │                                                    │                   │
│    │  3. ClientKeyExchange + ChangeCipherSpec + Finished│                   │
│    │───────────────────────────────────────────────────>│  ─┬─ 2nd RTT      │
│    │                                                    │   │               │
│    │  4. ChangeCipherSpec + Finished                    │   │               │
│    │<───────────────────────────────────────────────────│  ─┘               │
│    │                                                    │                   │
│    │  [Application Data]                                │                   │
│    │<══════════════════════════════════════════════════>│                   │
└─────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────┐
│ TLS 1.3: 1-RTT                                                              │
├─────────────────────────────────────────────────────────────────────────────┤
│  Client                                              Server                 │
│    │                                                    │                   │
│    │  1. ClientHello + KeyShare                         │                   │
│    │───────────────────────────────────────────────────>│  ─┬─ 1-RTT        │
│    │                                                    │   │               │
│    │  2. ServerHello + KeyShare + Encrypted Extensions  │   │               │
│    │     + Certificate + CertificateVerify + Finished   │   │               │
│    │<───────────────────────────────────────────────────│  ─┘               │
│    │                                                    │                   │
│    │  3. Finished + [Application Data]                  │                   │
│    │<══════════════════════════════════════════════════>│                   │
└─────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────┐
│ TLS 1.3 (0-RTT 재개)                                                         │
├─────────────────────────────────────────────────────────────────────────────┤
│  Client                                              Server                 │
│    │                                                    │                   │
│    │  1. ClientHello + KeyShare + Early Data (0-RTT)    │                   │
│    │───────────────────────────────────────────────────>│  ─┬─ 0-RTT        │
│    │                           [Server processes early] │   │               │
│    │  2. ServerHello + ... + Finished                   │   │               │
│    │<───────────────────────────────────────────────────│  ─┘               │
│    │                                                    │                   │
│    │  [Application Data continues]                      │                   │
│    │<══════════════════════════════════════════════════>│                   │
└─────────────────────────────────────────────────────────────────────────────┘
```

#### 0-RTT

0-RTT는 이전 연결에서 저장한 세션 정보를 재사용하여 첫 번째 메시지에서 바로 암호화된 데이터를 전송하는 방식이다. 작동 과정은 다음과 같다.

1. **첫 번째 연결**: 정상적인 1-RTT 핸드셰이크 수행
2. **세션 티켓 발급**: 핸드셰이크 완료 후, 서버가 클라이언트에게 세션 티켓(Session Ticket) 또는 PSK(Pre-Shared Key)를 발급
3. **클라이언트 저장**: 클라이언트(브라우저 등)가 티켓/PSK를 로컬에 캐시
4. **재연결 시**: 같은 서버에 다시 연결할 때, 저장된 티켓/PSK를 사용해 첫 번째 메시지에 암호화된 데이터를 포함

예를 들어 웹사이트를 방문했다가 탭을 닫고 다시 방문하거나, 모바일 앱이 백그라운드에서 포그라운드로 전환될 때 0-RTT를 활용할 수 있다.

다만, 보안상 취약하다는 한계도 있다. 

> 참고: **0-RTT의 한계**
> 
> 0-RTT는 성능 향상을 제공하지만 Replay Attack에 취약하다는 보안상 한계가 있다. 공격자가 0-RTT 데이터를 캡처하여 재전송할 수 있기 때문이다. 
> 따라서 멱등성(idempotent)이 보장되는 요청(GET 요청, 읽기 전용 API 등)에만 사용하는 것이 권장되며, 상태를 변경하는 POST, PUT, DELETE 요청에는 사용하지 않는 것이 안전하다. 또한, 서버 측에서는 Replay 방지를 위해 타임스탬프나 토큰 등 추가 메커니즘을 구현해야 한다.

### 보안 강화

TLS 1.3에서는 취약한 알고리즘을 제거하고 안전한 옵션만 남겼다. RSA 키 교환이 제거되어 Perfect Forward Secrecy가 필수가 되었고, RC4, 3DES, MD5, SHA-1 등 약한 알고리즘도 모두 제거되었다. 또한 0-RTT를 제외한 모든 핸드셰이크 메시지가 암호화되어 중간자가 협상 과정을 엿볼 수 없게 되었다.

### Cipher Suite 간소화

TLS 1.3에서는 키 교환과 인증 알고리즘이 Cipher Suite와 별도로 협상되므로, Cipher Suite 이름에서 생략된다. 또한 AEAD가 필수가 되면서 대칭키 암호화와 해시 함수만 남게 되었다.

```plaintext
# TLS 1.2 Cipher Suite (4가지 요소 모두 포함)
TLS_ECDHE_RSA_WITH_AES_128_GCM_SHA256
    │     │        │         │
    │     │        │         └─── 해시 함수
    │     │        └───────────── 대칭키 암호화 (AEAD)
    │     └────────────────────── 인증 알고리즘
    └──────────────────────────── 키 교환 알고리즘

# TLS 1.3 Cipher Suite (대칭키 암호화 + 해시 함수만)
TLS_AES_256_GCM_SHA384
        │         │
        │         └─── 해시 함수
        └───────────── 대칭키 암호화 (AEAD)
```

키 교환(ECDHE 등)과 인증(RSA, ECDSA 등)은 핸드셰이크의 다른 단계에서 협상된다.

> AEAD(Authenticated Encryption with Associated Data)는 암호화와 인증을 동시에 수행하는 방식으로, TLS 1.3에서 필수가 되었다. 자세한 내용은 [데이터 전송의 암호화 방식](#암호화-방식)을 참고하자.

<br>

## mTLS (Mutual TLS)

일반 TLS는 **서버만 인증**하지만, mTLS는 **서버와 클라이언트 모두 인증**한다. 핸드셰이크 과정만 다르고, 이후 데이터 전송은 TLS와 동일하다. 쿠버네티스, 마이크로서비스 등 내부 시스템 간 통신에서 주로 사용된다.

- **TLS**: 클라이언트가 서버의 인증서만 검증 (서버 인증)
- **mTLS**: 서버도 클라이언트의 인증서를 검증 (상호 인증)

### mTLS Handshake

mTLS는 TLS Handshake에 클라이언트 인증서 전송 및 검증 단계가 추가된다.

```plaintext
┌─────────────┐                              ┌─────────────┐
│   Client    │                              │   Server    │
└──────┬──────┘                              └──────┬──────┘
       │                                            │
       │  1. ClientHello                            │
       │───────────────────────────────────────────>│
       │                                            │
       │  2. ServerHello                            │
       │<───────────────────────────────────────────│
       │                                            │
       │  3. Server Certificate                     │
       │<───────────────────────────────────────────│
       │                                            │
       │  4. CertificateRequest                     │  ← mTLS: 서버가
       │     (request client certificate)           │    클라이언트 인증서 요청
       │<───────────────────────────────────────────│
       │                                            │
       │  5. ServerHelloDone                        │
       │<───────────────────────────────────────────│
       │                                            │
       │  6. [Verify Server Certificate]            │
       │                                            │
       │  7. Client Certificate                     │  ← mTLS: 클라이언트가
       │     (client's X.509 certificate)           │    인증서 전송
       │───────────────────────────────────────────>│
       │                                            │
       │  8. ClientKeyExchange                      │
       │───────────────────────────────────────────>│
       │                                            │
       │  9. CertificateVerify                      │  ← mTLS: 클라이언트가
       │     (signature with client key)            │    개인키 소유 증명
       │───────────────────────────────────────────>│
       │                                            │
       │  10. ChangeCipherSpec                      │
       │───────────────────────────────────────────>│
       │                                            │
       │  11. Finished                              │
       │───────────────────────────────────────────>│
       │                                            │
       │                    12. [Verify Client Certificate]
       │                                            │
       │  13. ChangeCipherSpec                      │
       │<───────────────────────────────────────────│
       │                                            │
       │  14. Finished                              │
       │<───────────────────────────────────────────│
       │                                            │
       │  ═══════ Encrypted Communication ════════  │
       │<══════════════════════════════════════════>│
       │                                            │
```

TLS와의 차이점은 다음과 같다.
- **CertificateRequest** (4단계): 서버가 클라이언트에게 인증서를 요청
- **Client Certificate** (7단계): 클라이언트가 자신의 인증서를 서버에 전송
- **CertificateVerify** (9단계): 클라이언트가 인증서의 개인키 소유를 증명

아래와 같은 경우에 사용된다.
- **쿠버네티스**: 컴포넌트 간 통신 (API Server ↔ kubelet, etcd 등)
  > 쿠버네티스 PKI의 상세 구조는 [Kubernetes PKI](/kubernetes/Kubernetes-PKI/)를 참고하자.
- **서비스 메시**: Istio, Linkerd 등에서 마이크로서비스 간 자동 암호화
- **금융/의료 시스템**: 높은 보안 수준이 요구되는 내부 API 통신

<br>

# TLS 데이터 전송

핸드셰이크가 완료되면 세션키로 암호화된 데이터를 주고받는다. 이 단계에서는 무결성 보장과 성능 최적화가 중요하다.

## 암호화 방식

세션키가 생성된 후, 실제 데이터 전송에는 **AEAD(Authenticated Encryption with Associated Data)** 또는 **HMAC**이 사용된다.

### TLS 1.2: Encrypt-then-MAC

```plaintext
┌─────────────────────────────────────────────────────────────────────────────┐
│ TLS 1.2: Encrypt-then-MAC                                                   │
├─────────────────────────────────────────────────────────────────────────────┤
│  Client                                                      Server         │
│    │                                                            │           │
│    │  1. Encrypt(data, session_key)                             │           │
│    │  2. HMAC(encrypted_data, MAC_key)                          │           │
│    │                                                            │           │
│    │  [Encrypted Data + HMAC] ─────────────────────────────────>│           │
│    │                                                            │           │
│    │                                        1. Verify HMAC      │           │
│    │                                        2. Decrypt data     │           │
│    │                                        3. Process data     │           │
└─────────────────────────────────────────────────────────────────────────────┘
```

### TLS 1.3: AEAD 필수

TLS 1.3에서는 AEAD(예: AES-GCM, ChaCha20-Poly1305)가 필수다. 암호화와 인증을 한 번에 수행하여 더 빠르고 안전하다.

```plaintext
┌─────────────────────────────────────────────────────────────────────────────┐
│ TLS 1.3: AEAD (암호화 + 인증 동시 수행)                                          │
├─────────────────────────────────────────────────────────────────────────────┤
│  Client                                                      Server         │
│    │                                                            │           │
│    │  AEAD_Encrypt(data, key, nonce)                            │           │
│    │                                                            │           │
│    │  [Ciphertext + Auth Tag] ─────────────────────────────────>│           │
│    │                                                            │           │
│    │                              AEAD_Decrypt(ciphertext, key) │           │
│    │                              → 인증 실패 시 연결 거부           │           │
└─────────────────────────────────────────────────────────────────────────────┘
```

- Encrypt-then-MAC의 타이밍 공격 취약점 방지
- 구현이 더 간단하고 안전

> TLS 핸드셰이크는 비용이 크므로, 이전 연결을 재사용하는 **세션 재개(Session Resumption)** 메커니즘이 있다. TLS 1.2의 Session ID/Session Ticket, TLS 1.3의 0-RTT 등이 이에 해당하며, 자세한 내용은 [TLS 1.3 핸드셰이크의 0-RTT](#0-rtt) 섹션을 참고하자.

<br>

# 단계별 무결성 검증

TLS는 **핸드셰이크**와 **데이터 전송**에서 다른 무결성 검증 방식을 사용한다.

| 구분 | 핸드셰이크 | 데이터 전송 |
|------|-----------|------------|
| 방식 | 디지털 서명 | MAC / AEAD |
| 목적 | 신원 증명 (제3자 검증) | 무결성 확인 (세션 내) |
| 암호화 | 공개키 (느림) | 대칭키 (빠름) |

핸드셰이크에서는 CA의 디지털 서명으로 서버 신원을 확인하고, 데이터 전송에서는 세션키로 빠르게 무결성만 검증한다. 이미 세션키를 공유한 양쪽만 검증하면 되므로 제3자 증명이 필요 없다.

<br>

# TLS 확장 기능

## SNI (Server Name Indication)

SNI는 TLS 확장 기능으로, 하나의 IP 주소에서 여러 도메인의 인증서를 제공할 수 있게 한다. ClientHello에 접속하려는 도메인 이름을 명시하면, 서버가 적절한 인증서를 선택하여 반환한다.

```plaintext
IP: 203.0.113.1           Client → Server: ClientHello + SNI: "example.com"
├── example.com           Server → Client: ServerHello + Certificate for example.com
├── test.com
└── demo.com
```

> SNI는 평문으로 전송되므로 어떤 도메인에 접속하는지 중간자가 알 수 있다. TLS 1.3의 Encrypted SNI (ESNI)로 이를 개선하려는 노력이 있다.

<br>

## Perfect Forward Secrecy (PFS)

PFS는 서버의 개인키가 나중에 유출되어도 **과거의 통신 내용을 복호화할 수 없도록** 보장하는 특성이다. 개인키 유출 자체를 막는 것이 아니라, 유출되어도 피해 범위를 현재 세션 이후로 제한한다.

### RSA 키 교환의 문제점

RSA 키 교환에서는 클라이언트가 PMS(Pre-Master Secret)를 **서버의 공개키로 암호화**해서 전송한다. 서버는 자신의 개인키로 이를 복호화하여 세션키를 생성한다. 문제는 서버의 개인키가 **모든 세션의 PMS를 복호화하는 데 사용**된다는 점이다.

```plaintext
[공격 시나리오]
1. 공격자가 과거 TLS 통신을 모두 녹화
2. 몇 년 후 서버 개인키 유출
3. 녹화된 통신에서 암호화된 PMS 추출
4. 서버 개인키로 PMS 복호화
5. PMS로부터 세션키 재생성
6. 모든 과거 통신 복호화 성공
```

### ECDHE를 통한 PFS

ECDHE(Elliptic Curve Diffie-Hellman Ephemeral)는 **매 세션마다 새로운 임시 키 쌍**을 생성한다.

- **서버 개인키의 역할 분리**: 서버의 장기 개인키는 **인증(서명)**에만 사용되고, 세션키 생성에는 사용되지 않는다.
- **임시 키로 세션키 생성**: 클라이언트와 서버가 각각 임시 키 쌍을 생성하고, Diffie-Hellman 알고리즘으로 세션키를 합의한다.
- **세션 종료 후 폐기**: 임시 키는 세션이 끝나면 폐기되므로, 나중에 서버 개인키가 유출되어도 과거 세션키를 복구할 수 없다.

**TLS 1.3에서는 PFS가 필수**이며, RSA 키 교환은 완전히 제거되었다.

<br>

# 응용 프로토콜

TLS 위에서 동작하는 다양한 응용 프로토콜이 있다.

- **HTTPS**: HTTP over TLS로, 포트 443을 사용하며 웹 보안 통신의 표준
- **FTPS**: FTP over TLS로, 파일 전송을 암호화
- **SMTPS**: SMTP over TLS로 이메일 전송을 암호화(포트 465 또는 587)
- **WSS**: WebSocket over TLS로 실시간 양방향 통신을 암호화한
- **gRPC**: HTTP/2 over TLS를 사용하며 mTLS를 지원함

<br>

# 정리

TLS/SSL 프로토콜의 핵심 개념을 정리하면 다음과 같다.

**기본 개념:**
- TLS는 네트워크 통신을 암호화하는 프로토콜이다
- SSL은 TLS의 이전 버전으로 현재 폐기되었다
- 현재 표준은 TLS 1.2와 TLS 1.3이다

**TLS가 제공하는 보안:**
- 기밀성: 대칭키 암호화 (AES-GCM, ChaCha20-Poly1305)
- 무결성: MAC/HMAC 또는 AEAD
- 인증: X.509 인증서와 디지털 서명

**핸드셰이크:**
- TLS 연결 수립 과정으로 인증서 교환과 세션키 생성을 수행한다
- TLS 1.2는 2-RTT, TLS 1.3은 1-RTT로 개선되었다
- Cipher Suite를 협상하여 암호화 알고리즘 조합을 결정한다

**세션키:**
- 데이터 암호화에 사용되는 대칭키이다
- PMS, clientRandom, serverRandom으로부터 PRF를 통해 생성된다
- 매 세션마다 다른 키를 생성하여 재사용 공격을 방지한다

**Perfect Forward Secrecy (PFS):**
- 서버 개인키 유출 시에도 과거 통신 보호를 보장한다
- ECDHE 같은 임시 키 교환 방식을 사용한다
- TLS 1.3에서는 필수 기능이다

**mTLS:**
- 서버와 클라이언트 모두 인증서로 인증하는 방식이다
- 쿠버네티스와 서비스 메시에서 널리 사용된다
- 마이크로서비스 간 Zero Trust 보안 구현에 필수적이다

**데이터 무결성:**
- 핸드셰이크는 디지털 서명으로 신원을 증명한다
- 데이터 전송은 HMAC 또는 AEAD로 무결성을 검증한다
- TLS 1.3에서는 AEAD가 필수이다

**최적화:**
- Session Resumption으로 핸드셰이크를 생략할 수 있다
- TLS 1.3의 0-RTT로 즉시 데이터 전송이 가능하다
- SNI로 하나의 IP에서 여러 도메인을 서비스할 수 있다

<br>