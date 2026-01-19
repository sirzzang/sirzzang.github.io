---
title:  "[Security] X.509 인증서"
excerpt: "X.509 인증서의 구조와 필드에 대해 알아 보자."
categories:
  - CS
toc: true
header:
  teaser: /assets/images/blog-Dev.jpg
tags:
  - Security
  - 보안
  - X.509
  - 인증서
  - CA
---

<br>

# 개요

X.509는 공개키 인증서의 **국제 표준 형식**이다. HTTPS, 쿠버네티스, VPN 등 다양한 시스템에서 사용된다. 이 글에서는 X.509 인증서의 구조와 필드에 대해 알아본다.

> 인증서의 기본 개념(필요성, 체인, 종류)은 [디지털 인증서](/cs/CS-Certificate/)를, PKI 전반에 대해서는 [PKI](/cs/CS-PKI/)를 참고하자.

<br>

# X.509 인증서

## 정의

X.509는 ITU-T에서 정의한 **공인 인증서 표준**이다. 1988년에 처음 정의되었으며, 현재는 버전 3(V3)가 표준으로 사용된다. **{사용자 ID, 유효기간, 사용자의 공개키, CA의 디지털 서명}**으로 구성된다.

TLS에서 사용되는 인증서는 사실상 모두 X.509 형식을 따른다. TLS 1.3 명세([RFC 8446](https://datatracker.ietf.org/doc/html/rfc8446#section-4.4.2))에서도 인증서 타입은 기본적으로 X.509를 사용한다고 명시되어 있다. TLS 프로토콜 자체는 확장성을 고려하여 다른 인증서 타입도 허용하도록 설계되었으나, 실제로는 다음과 같은 이유로 X.509가 사실상의 표준(de facto standard)이다:
- 전 세계 CA(DigiCert, Let's Encrypt 등)가 X.509 형식으로 인증서를 발급
- 브라우저와 OS의 Trust Store가 X.509 형식의 루트 인증서를 저장
- OpenSSL, GnuTLS 등 주요 TLS 구현체가 X.509를 기본으로 처리

<br>

## 구조

X.509 인증서는 **본문(TBSCertificate) + 서명 알고리즘 + 디지털 서명**으로 구성된다. 본문 안에 인증서 소유자의 공개키가 포함되어 있다.
- 본문(TBSCertificate): 서명 대상이 되는 인증서 정보. 소유자의 공개키 포함
- 서명 알고리즘: 본문을 해싱하고 서명할 때 사용한 알고리즘 (예: SHA-256 with RSA)
- 서명 값(Signature): CA가 본문을 해싱한 후 자신의 개인키로 암호화한 값

```
+--------------------------------------------------+
|        TBSCertificate (To Be Signed)             |
+--------------------------------------------------+
| 1. Version: v3                                   |
| 2. Serial Number: 01:23:45:67:89                 |
| 3. Signature Algorithm: SHA-256 with RSA         |
| 4. Issuer: CN=MyLocalCA                          |
| 5. Validity:                                     |
|    - Not Before: 2026-01-01                      |
|    - Not After: 2027-01-01                       |
| 6. Subject: CN=my-server                         |
| 7. Subject Public Key Info:                      |
|    - Algorithm: RSA (2048 bit)                   |
|    - Public Key: 0xAF31...                       |
| 8. Extensions:                                   |
|    - SAN: DNS:example.com, IP:192.168.1.10       |
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

주요 구성 요소는 다음과 같다:
- **본문(TBSCertificate)**: 서명 대상이 되는 인증서 정보. 소유자의 공개키가 포함됨 (공개되어도 안전)
- **서명 알고리즘**: 본문을 해싱하고 서명할 때 사용한 알고리즘 (예: SHA-256 with RSA)
- **서명 값(Signature)**: CA가 본문을 해싱한 후 자신의 개인키로 암호화한 값



## 필드 상세

인증서 구조 다이어그램에서 본 각 필드가 실제로 어떤 정보를 담는지 살펴보자.

### 주요 필드

X.509 V3 인증서의 주요 필드는 다음과 같다:
- Version: 인증서 버전을 나타내며 현재는 V3가 표준
- Serial Number: CA가 발급한 고유 일련번호로 인증서를 유일하게 식별함
- Signature Algorithm: 서명에 사용된 알고리즘을 명시하며, 예를 들어 SHA256withRSA는 SHA-256 해시와 RSA 서명을 의미함
- Issuer: 인증서 발급자(CA)의 DN(Distinguished Name)을 나타냄
- Validity: 인증서의 유효 기간으로 Not Before와 Not After 날짜를 포함함
- Subject: 인증서 소유자의 DN(Distinguished Name)으로, 조직명, 국가, 도메인 등의 정보를 담고 있음
- Subject Public Key Info: 소유자의 공개키 정보로, 알고리즘과 키 값을 포함함
- Extensions: V3에서 추가된 확장 필드로, 키 용도와 제약 사항 등을 정의함
- Signature: CA의 디지털 서명으로, 인증서 전체 내용을 해시한 후 CA의 개인키로 서명한 값


### 확장 필드(Extensions)

V3에서 추가된 확장 필드는 인증서의 용도와 제약 사항을 세밀하게 정의한다.

- Key Usage: 키 용도 지정
  - digitalSignature(디지털 서명)
  - keyEncipherment(키 암호화)
  - dataEncipherment(데이터 암호화)
- Extended Key Usage: 확장키 용도
  - serverAuth(서버 인증)
  - clientAuth(클라이언트 인증)
  - codeSigning(코드 서명)
- Subject Alternative Name(SAN): 대체 이름으로, 하나의 인증서로 여러 도메인을 지원할 때 사용함
  - 예를 들어 example.com, www.example.com, api.example.com을 모두 포함할 수 있음
  - 현재는 CN(Common Name) 대신 SAN을 우선시함
- Basic Constraints: CA 인증서 여부를 나타내며, 인증서 체인에서 경로 길이 제한을 설정



## Distinguished Name (DN)과 X.500 표준

X.509 인증서의 Subject와 Issuer 필드에서 사용하는 `CN`, `O`, `OU`, `C` 같은 필드들은 **X.500 디렉토리 서비스 표준**에서 유래했다.

X.500은 국제 전기통신 연합(ITU-T)이 정의한 디렉토리 서비스 표준으로, 계층적 구조로 개체를 식별하기 위한 **Distinguished Name (DN)** 체계를 제공한다. X.509는 X.500의 인증서 표준으로 만들어졌기 때문에, 동일한 DN 구조를 사용한다.

### 주요 DN 필드

| 필드 | 의미 | 예시 |
|------|------|------|
| **CN** (Common Name) | 주체의 이름 | `CN=admin`, `CN=kubernetes` |
| **O** (Organization) | 조직명 | `O=system:masters` |
| **OU** (Organizational Unit) | 조직 단위 | `OU=Engineering` |
| **L** (Locality) | 지역/도시 | `L=Seoul` |
| **ST** (State) | 주/도 | `ST=Gyeonggi` |
| **C** (Country) | 국가 코드 | `C=KR` |

### LDAP와의 관계

LDAP(Lightweight Directory Access Protocol)는 X.500의 경량화 버전으로, 동일한 DN 구조를 사용한다. 그래서 LDAP 디렉토리 서비스를 사용해 본 경험이 있다면, 인증서에서도 동일한 필드들을 보게 된다.

```bash
# LDAP DN 예시
dn: CN=John Doe,OU=Engineering,O=Acme Corp,C=US
```

X.509 인증서의 Subject도 동일한 구조를 따른다:

```bash
# X.509 인증서 Subject 예시
Subject: CN=admin, O=system:masters, C=KR
```

이러한 표준화된 필드 덕분에 인증서, 디렉토리 서비스, Kerberos 등 다양한 인증/인가 시스템이 일관된 방식으로 주체를 식별할 수 있다.


<br>

# 인증서 검증

클라이언트가 인증서를 검증하는 과정은 다음과 같다:

```
                  +--------------------+
                  |    Certificate     |
                  +--------------------+
                  | TBSCertificate     |
                  +----------+---------+
                  | Signature Value    |
                  +----------+---------+
                             |
         +-------------------+-------------------+
         |                                       |
         v                                       v
+-----------------+                   +---------------------+
| Signature Value |                   |   TBSCertificate    |
+-----------------+                   +---------------------+
         |                                       |
         | Decrypt with CA Public Key            | Hash
         v                                       v
+-----------------+                   +---------------------+
|    Hash A       |                   |       Hash B        |
+--------+--------+                   +----------+----------+
         |                                       |
         +-------------------+-------------------+
                             |
                             v
                      +--------------+
                      |  A == B ?    |
                      +--------------+
                      | Yes: Valid   |
                      | No : Forged  |
                      +--------------+
```

1. 인증서에서 TBSCertificate(본문)와 Signature Value(서명 값)를 분리한다.
2. Signature Value를 CA의 공개키로 복호화하여 Hash A를 얻는다.
3. TBSCertificate를 동일한 알고리즘으로 해싱하여 Hash B를 얻는다.
4. Hash A와 Hash B를 비교하여, 일치하면 유효한 인증서, 불일치하면 위조된 인증서로 판단한다.

<br>

# 인증서 예시

브라우저에서 구글 인증서를 확인하면 X.509 구조가 어떻게 표시되는지 볼 수 있다.

![x509-google-example]({{site.url}}/assets/images/x509-google-example.png){: .align-center width="500"}

> 이 화면이 정상적으로 보인다는 것 자체가 "CA 공개키로 서명을 검증했더니 본문 해시값이 일치했다"는 의미다. 가짜 인증서였다면 브라우저가 빨간색 경고창을 띄웠을 것이다.

## 인증서 본문 (TBSCertificate)

이미지 상단의 내용들이 서명 대상이 되는 본문에 해당한다:
- **발급 대상 (Subject)**: `*.google.com` - 인증서의 주인 (CN: Common Name)
- **발급 기관 (Issuer)**: `Google Trust Services` - 도장을 찍어준 CA
- **유효성 기간 (Validity)**: 2025년 12월 4일 ~ 2026년 2월 26일

## 공개키와 지문

- **공개 키 지문**: 실제 공개키는 매우 길기 때문에, SHA-256으로 해싱한 지문(Fingerprint)만 표시됨. 실제 공개키는 [세부 정보] 탭의 "Subject Public Key Info"에서 확인 가능
- **인증서 지문**: 인증서 전체를 SHA-256으로 해싱한 값. 이 값이 다르면 인증서가 변조된 것

## 서명

일반 탭에는 서명 값이 표시되지 않지만, [세부 정보] 탭에서 "서명 알고리즘"과 "서명" 항목을 확인할 수 있다. CA가 개인키로 암호화한 16진수 값이 들어있다.

<br>

# 인코딩 형식

인증서 파일을 다루다 보면 `.pem`, `.crt`, `.der` 등 다양한 확장자를 만나게 된다. X.509 인증서는 ASN.1(Abstract Syntax Notation One) 구조로 정의되며, 두 가지 인코딩 형식으로 저장된다.

## DER(Distinguished Encoding Rules)

원본 바이너리 형식으로, 기계가 직접 처리하기에 효율적이다.

- 바이너리 형식
- 파일 확장자: `.der`, `.cer`, `.crt`
- 사람이 읽을 수 없음

## PEM(Privacy Enhanced Mail)

DER을 Base64로 인코딩하여 텍스트로 표현한 형식으로, 복사/붙여넣기가 가능해 가장 널리 사용된다.

```bash
-----BEGIN CERTIFICATE-----
MIIDXTCCAkWgAwIBAgIJAKL0UG+mRHKpMA0GCSqGSIb3DQEBCwUAMEUxCzAJBgNV
...
-----END CERTIFICATE-----
```

- 텍스트 형식 (DER의 Base64 인코딩)
- BEGIN/END 태그로 둘러싸임
- 파일 확장자: `.pem`, `.crt`, `.cer`


<br>

# 정리

X.509는 공개키 인증서의 국제 표준 형식으로, ITU-T에서 정의했다. TBSCertificate(본문) + 서명 알고리즘 + 디지털 서명으로 구성되며, Subject와 Issuer를 DN(Distinguished Name) 형식으로 표현한다. DER(바이너리)과 PEM(텍스트) 두 가지 인코딩 형식으로 저장된다.

인증서의 기본 개념(필요성, 루트 인증서, 체인, 종류, 관리)은 [디지털 인증서](/cs/CS-Certificate/)를, PKI 전반에 대해서는 [PKI](/cs/CS-PKI/)를, 쿠버네티스에서의 활용은 [Kubernetes PKI](/kubernetes/Kubernetes-PKI/)를 참고하자.

<br>