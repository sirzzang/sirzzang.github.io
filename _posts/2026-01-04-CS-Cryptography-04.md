---
title:  "[Cryptography] 양방향 암호화 - 비대칭키"
excerpt: "비대칭키 암호화의 개념, RSA 알고리즘, 그리고 암호화와 서명의 차이"
categories:
  - CS
toc: true
hidden: true
header:
  teaser: /assets/images/blog-Dev.jpg
tags:
  - Cryptography
  - 암호화
  - 보안
  - 비대칭키
  - RSA
  - 공개키
  - 개인키
  - 디지털서명
---

<br>

*[서종호(가시다)](https://www.linkedin.com/in/gasida99/)님의 On-Premise K8s Hands-on Study 자료를 기반으로 합니다.*


> 암호화 기초
> - (1) [암호학 기초 - 개념과 분류](/cs/CS-Cryptography-01/)
> - (2) [단방향 암호화 - 해시 함수](/cs/CS-Cryptography-02/)
> - (3) [양방향 암호화 - 대칭키](/cs/CS-Cryptography-03/)
> - **(4) 양방향 암호화 - 비대칭키**

<br>

# 개요

비대칭키 암호화(Asymmetric Key Encryption)는 암호화와 복호화에 **서로 다른 키**를 사용하는 방식이다. **공개키(Public Key)**와 **개인키(Private Key)** 한 쌍으로 구성되며, 대칭키의 키 분배 문제를 해결할 수 있다.

<br>

# 비대칭키 암호화란?

비대칭키 암호화는 **수학적으로 연결된 두 개의 키**를 사용한다.

```
Public Key                    Private Key
    │                            │
    │  Mathematically linked      │
    │  (Cannot derive one from    │
    │   the other)               │
    │                            │
    ▼                            ▼
  Publicly available         Must be kept secret
  Encryption/Verification    Decryption/Signing
```

- **공개키(Public Key)**: 누구에게나 공개해도 됨
- **개인키(Private Key)**: 반드시 비밀로 유지해야 함

```python
# 공개키로 암호화 → 개인키로 복호화
enc(x, 공개키) = y
dec(y, 개인키) = x

# 개인키로 암호화(서명) → 공개키로 복호화(검증)
enc(x, 개인키) = y
dec(y, 공개키) = x
```

<br>

# 비대칭키 암호화의 특징

## 장점: 키 분배가 쉬움

- 공개키는 누구에게나 공개해도 안전
- 개인키만 비밀로 유지하면 됨
- 인터넷을 통한 안전한 키 교환 가능

<br>

## 단점: 느린 처리 속도

- 큰 수(2048비트 이상)의 **지수승 연산, 모듈러 연산** 필요
- 수학적으로 복잡하고 계산량이 많음
- 처리 속도: **수백 KB/s ~ 수십 MB/s** (대칭키 대비 100~1000배 느림)

<br>

이 문제를 해결하기 위해 실제 데이터 암호화에는 **대칭키**를 사용하고, **키 교환**에만 비대칭키를 사용하는 것이 일반적이다.

<br>

# 비대칭키의 두 가지 용도

비대칭키는 **어떤 키로 암호화하느냐**에 따라 용도가 달라진다.

<br>

- 암호화/복호화: 공개키로 암호화 → 개인키로 복호화
  - 목적: 기밀성(Confidentiality) 보장
  - 효과: 수신자만 읽을 수 있음
  - 예시: 세션키 전달
- 서명/검증
  - 개인키로 서명 → 공개키로 검증
  - 목적: 인증과 무결성 보장
  - 효과: 송신자 확인 및 변조 방지
  - 예시: 인증서 서명, Git 커밋 서명

<br>

## 암호화/복호화: 기밀성

수신자만 읽을 수 있게 하는 것을 목적으로 한다.

```
Sender (A)                    Receiver (B)
    │                              │
    │  1. Get B's public key       │
    │                              │
    │  2. Encrypt plaintext with   │
    │     B's public key           │
    │     Ciphertext = Encrypt(    │
    │       Plaintext, B_PublicKey)│
    │                              │
    │  3. Send [Ciphertext]        │
    │─────────────────────────────>│
    │                              │
    │                              │  4. Decrypt with B's
    │                              │     private key
    │                              │     Plaintext = Decrypt(
    │                              │       Ciphertext,
    │                              │       B_PrivateKey)
```
- B의 공개키는 누구나 알 수 있음
- **B의 개인키를 가진 B만** 복호화 가능
- 중간자가 가로채도 개인키 없이는 읽을 수 없음

<br>

## 서명/검증: 인증과 무결성

송신자 신원 증명 및 변조 방지를 목적으로 한다.

```
Sender (A)                    Receiver (B)
    │                              │
    │  1. Generate message hash    │
    │     hash = SHA256(message)   │
    │                              │
    │  2. Sign hash with A's       │
    │     private key              │
    │     signature = Sign(        │
    │       hash, A_PrivateKey)    │
    │                              │
    │  3. Send[Message + Signature]│
    │─────────────────────────────>│
    │                              │
    │                              │  4. Calculate hash of
    │                              │     received message
    │                              │     hash' = SHA256(message)
    │                              │
    │                              │  5. Verify signature with
    │                              │     A's public key
    │                              │     Verify(signature,
    │                              │            A_PublicKey)
    │                              │     → Extract original hash
    │                              │
    │                              │  6. Compare: hash == hash'?
    │                              │     Match: Verification success
    │                              │     Mismatch: Tampered or fake
```

위의 동작 과정에서 볼 수 있듯, 디지털 서명은 메시지 전체를 개인키로 암호화하는 것이 아니라, 메시지의 해시값만을 개인키로 암호화한다. 이는 성능상의 이유로, 큰 메시지를 직접 암호화하면 너무 느리기 때문이다.

<br>

### 서명의 효과

- **인증**: A만 개인키를 가지고 있으므로, A가 보낸 것이 확실함
- **무결성**: 메시지가 변조되면 해시값이 달라져 검증 실패
- **부인 방지(Non-repudiation)**: A는 나중에 "내가 안 보냈다"고 부인할 수 없음

<br>

# RSA 알고리즘

RSA는 가장 널리 사용되는 비대칭키 암호화 알고리즘이다. 1977년 Ron Rivest, Adi Shamir, Leonard Adleman에 의해 개발되었으며, 큰 소수의 곱셈은 쉽지만 그 곱을 다시 소인수분해하는 것은 어렵다는 수학적 특성에 기반한다.

<br>

## 키 구조

```
공개키: KU = {e, n}
개인키: KR = {d, n}
```

- `e`, `d`, `n`은 정수론에 의해 결정되는 특수한 값
- 공개키와 개인키는 수학적으로 연결되어 있음
- `n`은 두 큰 소수 `p`와 `q`의 곱 (n = p * q)
- `e`와 `d`는 모듈러 역원 관계

<br>

## RSA 동작 원리

### 예시

```
공개키: KU = {e, n} = {5, 119}
개인키: KR = {d, n} = {77, 119}
```
<br>

**암호화 (송신)**
```
평문 M = 19
암호문 C = M^e mod n = 19^5 mod 119 = 2476099 mod 119 = 66
```

<br>

**복호화 (수신)**
```
암호문 C = 66
평문 M = C^d mod n = 66^77 mod 119 = 19
```

개인키 {d, n}를 모르는 제3자는 공개키 {e, n}만으로 원본 데이터를 복호화할 수 없다.

<br>

## RSA 키 길이 선택

RSA의 안전성은 키 길이에 크게 의존한다:

- **1024비트**: 취약, 더 이상 사용하면 안 됨
- **2048비트**: 현재 권장되는 최소 길이, 대부분의 용도에 충분
- **3072비트**: 장기간 보안이 필요한 경우 권장
- **4096비트**: 최고 수준의 보안, 성능 오버헤드 큼

**NIST 권장사항:**
- 2030년까지: 2048비트 이상
- 2030년 이후: 3072비트 이상

<br>

## 실제 RSA 키 생성

RSA 키는 **PEM 형식**(Base64 인코딩)으로 저장된다.

```bash
# OpenSSL을 사용한 RSA 키 생성 예시
openssl genrsa -out private_key.pem 2048
openssl rsa -in private_key.pem -pubout -out public_key.pem
```

### 공개키 (공개해도 됨)

```
-----BEGIN PUBLIC KEY-----
MIGfMA0GCSqGSIb3DQEBAQUAA4GNADCBiQKBgQCOLDdaQ0P69ulKckj58ys7imLJ
9jCk862WlvgZgAUat+J8PBTpyH/iywJDOuLmNfA8Km+iZmatSY/YxNC7RFJuTafa
XcqhKDk2H0LUL30N//rfYxh+XeqfN++pHNJRggazyj5am4PKHwQRDZUgDO/k4BkQ
6Ii6eZ3mlkcVy74Z/QIDAQAB
-----END PUBLIC KEY-----
```

### 개인키 (절대 공개하면 안 됨)

```
-----BEGIN PRIVATE KEY-----
MIICdgIBADANBgkqhkiG9w0BAQEFAASCAmAwggJcAgEAAoGBAI4sN1pDQ/r26Upy
SPnzKzuKYsn2MKTzrZaW+BmABRq34nw8FOnIf+LLAkM64uY18Dwqb6JmZq1Jj9jE
...
-----END PRIVATE KEY-----
```

<br>

## RSA 암호화/복호화 실습

### 암호화 (공개키 사용)
```
입력: eraser
출력: 55ae20f2bea1c467031bf789f3f63064845d3d8f57e51a12c708b24cf2a3c8431f0ea8161954cf4c66af2f43ae093c34e794bd4009c81cb01a9e717c9fbb5b1e0fa639c4d3da3a4766e85265f3e7200991cf85428bf902ad1fc5d694b654df180b9e3622d8572a776375408c1879015e9e2612d4162f0923b70b21eca47e06a6
```

### 복호화 (개인키 사용)
```
입력: 55ae20f2bea1c467...
출력: eraser
```

<br>

# 키 분배 문제 해결

대칭키 방식에서는 **비밀 키를 어떻게 안전하게 공유할 것인가**가 문제였다.

> 대칭키 암호화와 키 분배 문제에 대한 자세한 내용은 [양방향 암호화 - 대칭키](/cs/CS-Cryptography-03/)를 참고하자.

<br>

## RSA를 이용한 대칭키 분배

비대칭키로 **대칭키 자체를 암호화**하여 전송한다.

```
1. B: (공개키, 개인키) 쌍 생성
2. B → A: 공개키 전송
3. A: 대칭키 생성 → B의 공개키로 암호화 → 전송
4. B: 개인키로 복호화 → 대칭키 획득
5. 이후 대칭키로 데이터 암호화 통신
```

<br>

## 중간자 공격 (Man-in-the-Middle Attack)

하지만 이 방식에도 취약점이 있다. 중간자에게 탈취될 수 있다는 것이다.

```
Normal Communication:
A ─────[A's Public Key]─────> B

Man-in-the-Middle Attack:
A >───[A's Public Key]───> Z ────[Z's Public Key]───> B
      (intercepted)              (impersonates)
      
A <───[A's Public Key]───< Z <───[Z's Public Key]───< B
      (intercepted)              (impersonates)

Result: Z can intercept and manipulate all communication
```

1. A가 공개키를 B에게 전송
2. **Z가 A의 공개키를 탈취** + 자신의 (공개키, 개인키) 생성
3. Z가 **자신의 공개키를 B에게 전송** (A인 척)
4. B는 A의 공개키라고 생각하지만, 실제로는 Z의 공개키로 대칭키 암호화
5. Z가 중간에서 **자신의 개인키로 대칭키 획득**
6. Z가 원래 A의 공개키로 다시 암호화해서 A에게 전송
7. A와 B는 서로 직접 통신했다고 생각하지만, **Z가 모든 내용을 탈취**

<br>

## 해결책: 인증서와 인증 기관

중간자 공격을 방지하려면 **공개키가 진짜 상대방의 것인지 확인**해야 한다. 이를 위해 인증 개념이 필요하다.

<br>

### 인증 기관(CA: Certificate Authority)

신뢰할 수 있는 제3자가 `이 공개키는 A의 것이 맞다`고 **보증**한다.

<br>

### 인증서(Certificate)

CA가 서명한 문서로, 공개키의 소유자를 증명한다.

```python
인증서 = {
    공개키: KU_A,
    소유자: "A",
    발급자: "CA",
    유효기간: ...,
    CA의 디지털 서명
}
```

<br>

### 동작 원리

1. A가 CA에게 인증서 발급 요청 (CSR: Certificate Signing Request)
2. CA가 A의 신원 확인 (도메인 소유권, 회사 등록증 등)
3. CA가 A의 공개키가 A의 것임을 **CA의 개인키로 서명**하여 인증서 발급
4. B는 **CA의 공개키**로 인증서의 서명 검증
5. 검증 성공 → A의 공개키를 신뢰

<br>

### 중간자 공격 방어

중간자 공격 시나리오는 아래와 같이 방어된다:

<br>

**시나리오 1: 인증서 재사용 + 다른 공개키**
- Z가 A의 인증서를 그대로 보내면서 자신의 공개키를 보냄
- 인증서 내 공개키 ≠ 받은 공개키
- 결과: **탐지**

<br>

**시나리오 2: 위조 인증서**
- Z가 위조 인증서를 만듦
- CA의 개인키 없이는 유효한 서명 생성 불가
- 결과: **탐지**

<br>

**시나리오 3: 인증서 없이 공개키만 전송**
- Z가 인증서 없이 공개키만 보냄
- 인증서 없음
- 결과: **거부**

<br>

# 인증 기관 체계

## Root CA

최상위 인증 기관으로, 브라우저와 운영체제에 **미리 내장**되어 있다.

**주요 Root CA:**
- DigiCert, Let's Encrypt, GlobalSign, Comodo, VeriSign 등
- 약 50~100개의 Root CA가 존재
- 이들의 **공개키가 브라우저와 OS에 사전 설치**되어 있음

**보안:**
- 개인키는 극도로 엄격하게 보호됨
- 오프라인 환경에서 물리적으로 격리된 하드웨어 보안 모듈(HSM)에 저장

<br>

## 인증서 체인 (Certificate Chain)

```
Root CA (최상위)
    ↓ 서명
Intermediate CA (중간)
    ↓ 서명
google.com (최종 엔티티)
```

Root CA가 직접 모든 인증서를 발급하지 않고, 중간 CA를 통해 발급한다.

**이유:**
- **보안**: Root CA의 개인키 사용을 최소화하여 위험 감소
- **확장성**: 중간 CA가 실제 발급 업무 담당
- **유연성**: 중간 CA가 손상되어도 Root CA는 안전하게 유지

<br>

## 인증서 검증 과정

브라우저가 웹사이트의 인증서를 검증하는 과정:

1. 서버가 인증서 체인 전송 (서버 인증서 + 중간 CA 인증서)
2. 브라우저가 서버 인증서의 서명을 중간 CA 공개키로 검증
3. 중간 CA 인증서의 서명을 Root CA 공개키로 검증
4. Root CA는 브라우저에 사전 설치되어 있으므로 신뢰
5. 체인 전체가 유효하면 서버 인증서 신뢰

<br>

# 알고리즘 비교

비대칭키 암호화 알고리즘은 용도와 특징에 따라 구분된다:

**RSA**
- 용도: 암호화와 서명 모두 가능
- 특징: 가장 널리 사용됨
- 권장 키 길이: 2048비트 이상

**ECC (Elliptic Curve Cryptography)**
- 용도: 암호화와 서명 모두 가능
- 특징: RSA보다 짧은 키로 동등한 보안성 제공
- 예시: 256비트 ECC = 3072비트 RSA 보안 수준
- 적합한 환경: 모바일 기기, IoT

**DSA (Digital Signature Algorithm)**
- 용도: 서명 전용
- 특징: 미국 표준이었으나 현재는 ECDSA가 더 선호됨

**Ed25519**
- 용도: 서명 전용
- 특징: 매우 빠르고 안전
- 권장 용도: SSH 키 생성

<br>

# 정리

비대칭키 암호화의 핵심 개념을 정리하면 다음과 같다. 
1. 비대칭키는 암복호화에 다른 키를 사용하는 방식으로 공개키와 개인키 한 쌍으로 구성된다
2. 공개키는 누구에게나 공개 가능하며 암호화와 검증에 사용된다
3. 개인키는 비밀 유지가 필수이며 복호화와 서명에 사용된다
4. 암호화 용도에서는 공개키로 암호화하고 개인키로 복호화하여 기밀성을 보장한다
5. 서명 용도에서는 개인키로 서명하고 공개키로 검증하여 인증과 무결성을 보장한다
6. RSA는 큰 소수의 인수분해 어려움에 기반한 가장 널리 사용되는 비대칭키 알고리즘이다
7. 중간자 공격은 공개키를 바꿔치기하는 공격으로 인증서로 방어할 수 있다
8. 인증서는 CA가 디지털 서명하여 공개키 소유자를 보증하는 문서이다
9. CA(Certificate Authority)는 인증서를 발급하는 신뢰할 수 있는 기관이며, 그들의 공개키는 브라우저와 OS에 사전 설치되어 있다

<br>