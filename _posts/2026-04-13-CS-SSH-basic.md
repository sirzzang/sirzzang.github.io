---
title: "[SSH] SSH 접속 원리"
excerpt: "매번 아무렇지 않게 접속하던 SSH의 동작 원리를 알아보자."
categories:
  - CS
toc: true
header:
  teaser: /assets/images/blog-Dev.jpg
tags:
  - SSH
  - OpenSSH
  - Cryptography
  - TOFU
  - Diffie-Hellman
  - Network-Security
---

<br>

매번 아무렇지 않게 `ssh user@host`를 치면서도, 접속할 때 내부에서 뭐가 일어나는지 제대로 정리한 적이 없어 SSH 접속 원리에 대해 알아 보았다.

<br>

# TL;DR

- SSH(Secure Shell)는 DH 키 교환으로 암호화 채널을 수립하고, 그 안에서 양방향 인증을 수행한다
- 신뢰 모델은 TOFU(Trust On First Use): 첫 접속 시 근거 없이 신뢰하고, 이후 known_hosts로 대조한다
- 핵심 흐름: 알고리즘 협상 → DH + 서버 인증(③④⑤⑥) → 암호화 터널(⑦) → 사용자 인증(⑧)
- host key(서버 신원)와 user key(사용자 인증)는 목적, 저장 위치, 신뢰 확립 방식이 모두 다르다

<br>

# 공개키 암호화와 신뢰 모델

SSH는 [공개키 암호화]({% post_url 2026-01-04-CS-Cryptography-04 %})를 기반으로 동작한다. 이 원리를 먼저 이해해야 뒤의 내용이 연결된다.

공개키 암호화에서는 키 쌍(key pair)을 생성한다: 개인키(private key)와 공개키(public key)다. SSH에서 키 쌍이 실제로 수행하는 핵심 기능은 **서명과 검증**이다. 개인키로 "이 데이터는 내가 만들었다"를 서명하고, 공개키로 "이 서명은 개인키 소유자가 만든 것이 맞다"를 검증한다.

공개키로 암호화하고 개인키로 복호화하는 것도 가능하지만, 이는 일부 알고리즘(RSA)에 한정된 기능이다. Ed25519, ECDSA 등 현대적 알고리즘은 서명 전용으로, 암호화/복호화 자체가 불가능하다. SSH에서 데이터 암호화는 키 쌍이 아닌 DH 키 교환으로 도출한 대칭키(AES 등)가 담당한다.

결과적으로 **서명과 검증**이 핵심 기능이고, 이 기능에서의 핵심 성질은 **공개키만으로 서명을 검증할 수 있지만, 서명을 만들기 위해서는 개인키가 필요하다**는 것이다. 그래서 개인키는 절대 외부에 나가면 안 되고, 공개키는 자유롭게 배포해도 된다.

## 신뢰 모델

공개키 암호화에는 근본적인 문제가 있다: 누군가 공개키를 보내 왔을 때, "이 공개키가 진짜 저 서버/사람의 것인가"를 어떻게 아는가? 공개키는 누구나 생성할 수 있는 수학적 값일 뿐이다. 공개키 안에 "나는 서버 A의 키다"라는 정보가 들어있지 않고, 공개키와 신원의 연결(binding)을 수학으로 증명할 방법도 없다. 공격자가 자기 키를 만들어서 "이것이 서버 A의 공개키다"라고 보내도, 공개키만 보고는 진위를 판별할 수 없다.

이 간극을 메우는 방법이 **신뢰 모델**(trust model)이다. "처음 보는 공개키가 진짜 그 상대의 것인지 어떻게 결정하는가?"에 대한 프레임워크다.

| 신뢰 모델 | 사용처 | 신원 확인 방법 |
|-----------|--------|---------------|
| **[PKI]({% post_url 2026-01-18-CS-PKI %})** | TLS | CA(인증기관)라는 제3자가 "이 공개키는 이 서버의 것이 맞다"를 보증 → 인증서 |
| **TOFU** | SSH | 제3자 없이, 처음 보는 공개키를 검증 근거 없이 신뢰 |
| **Web of Trust** | PGP | 내가 아는 사람이 보증하면 신뢰 |

각 프로토콜마다 채택하는 신뢰 모델이 다르다. 이후에 주로 살펴 보게 될 SSH와 TLS의 중요한 차이 역시 **신뢰 모델의 차이**에서 비롯된다.

<br>

# TOFU: SSH의 신뢰 모델

TOFU(Trust On First Use)는 **"최초의 신뢰를 어떻게 확립하는가?"**에 대한 답이다: "처음 만날 때 그냥 믿는다". 이후 저장된 host key와 대조하는 것은 TOFU 자체가 아니라, SSH가 확립된 신뢰를 유지/검증하는 별도 메커니즘이다.

앞서 본 것처럼 암호학적 검증은 "이 키와 이 서명이 수학적으로 맞다"까지만 증명하고, **"이 키가 내가 접속하려는 서버의 것이다"는 증명하지 못한다.** 이 남은 간극을 누구에게 맡기는가가 신뢰 모델이다. PKI는 CA에게, TOFU는 사용자(또는 자동 수락)에게 맡긴다.

## 첫 번째 접속

서버가 host key를 제시하는데, 이전에 저장한 host key가 없다. TOFU 원칙에 따라 이 키를 검증 근거 없이 신뢰하고 저장한다. 이 순간 신뢰가 확립된다.

TOFU가 규정하는 것은 "처음 보는 키를 신뢰한다"는 원칙까지다. 그 신뢰를 **어떻게** 수락하는지는 구현체가 결정한다. OpenSSH는 yes/no 프롬프트로 사용자에게 묻지만, 자동 수락(`StrictHostKeyChecking=accept-new`), SSHFP DNS 레코드 조회, 사전 배포된 known_hosts 파일 대조 등 다른 방식도 가능하다. SSH 프로토콜(RFC 4251)도 "클라이언트는 host key를 검증해야 한다(SHOULD)"라고만 규정하고, 검증 방법은 구현체에 맡긴다.

## 두 번째 이후 접속 (이후 검증)

서버가 host key를 제시하면, 저장된 host key와 자동으로 대조한다. 일치하면 통과(사용자 눈에 안 보임)시키고, 불일치하면 차단(같은 서버가 아닐 수 있다)한다.

양방향 인증(서버 검증 + 사용자 검증)은 **매 접속마다** 일어난다. TOFU 질문은 첫 접속에서만 뜨지만, 저장된 host key 대조와 서명 검증은 매번 자동으로 진행된다. 매번 대조하니까 불일치를 감지할 수 있다.

## TOFU의 한계: 대규모 인프라

TOFU는 구조적으로 **첫 접속 순간이 취약 구간**이다. 처음 보는 키를 검증 근거 없이 믿기로 한 이상, 그 순간에 공격자가 끼어들어도 구별할 방법이 없다. 한 번 신뢰가 확립된 후에는 저장된 host key로 검증하니 괜찮지만, 신뢰가 확립되는 바로 그 순간만큼은 무방비다.

서버가 소수이고 오래 유지되는 환경이라면 이 취약 구간은 서버당 딱 한 번뿐이다. 하지만 현대 클라우드 인프라에서는 인스턴스가 수시로 생성되고 삭제된다. 새 인스턴스는 새 host key를 가지고, 새 host key는 곧 새로운 "첫 접속"이다. 즉 TOFU의 취약 구간이 일회성이 아니라 **반복적으로 발생**하는 구조가 된다.

- **규모**: 서버가 1000대면 첫 접속도 1000번이다. 그 중 하나가 공격자의 키여도 사람이 구별할 방법이 없다
- **빈도**: 오토스케일링, 컨테이너, 인스턴스 교체로 서버가 수시로 바뀌면, "첫 접속"이 운영 중 계속 발생한다
- **자동화**: 사람이 없는 환경(CI/CD, 스크립트)에서는 첫 접속의 신뢰 판단을 사람에게 위임할 수조차 없다

결국 TOFU가 안전하게 동작할 수 있는 조건 — 첫 접속이 드물고, 사람이 판단할 수 있는 환경 — 이 현대 인프라에서는 성립하지 않는 경우가 많다. 그래서 대규모 환경에서는 SSH도 TOFU를 벗어나 인증서 기반(OpenSSH Certificate) 등으로 전환하기도 한다.

<br>

# SSH 프로토콜 원리

SSH(Secure Shell, RFC 4251~4254)는 신뢰할 수 없는 네트워크 위에서 안전한 원격 접속을 제공하는 프로토콜이다. 핵심 원리는 두 가지다.

1. **암호화**: Diffie-Hellman 키 교환으로 세션 키를 만들어 모든 통신을 암호화
2. **양방향 인증**: 서버도 자기 신원을 증명하고, 클라이언트도 자기 신원을 증명

> 더 엄밀하게: 현대 OpenSSH(10.0+)의 기본 키 교환은 포스트 양자 하이브리드(`mlkem768x25519-sha256`)로, 내부에 X25519(ECDH)를 포함한다. 이전 버전에서도 `curve25519-sha256`(ECDH)이 기본이었다. 모두 DH의 변형이므로 "Diffie-Hellman 키 교환"이라는 표현은 틀리지 않지만, 고전적인 modular DH(`diffie-hellman-group14-sha256` 등)와는 다르다.

서버 인증은 DH 키 교환과 함께 이루어지고, 사용자 인증은 암호화 터널이 수립된 후 그 안에서 진행된다.

## 전체 흐름

![ssh-process-overview]({{site.url}}/assets/images/ssh-process-overview.png){: .align-center}

위 도식을 단계별로 정리하면 다음과 같다.

### 0단계: 연결 + 암호화 준비

① **TCP 연결 + 프로토콜 버전 교환**: 클라이언트와 서버가 TCP 연결을 맺고, 서로 SSH 프로토콜 버전을 교환한다

② **알고리즘 협상**: 양쪽이 `SSH_MSG_KEXINIT` 메시지로 자신이 지원하는 알고리즘 목록(키 교환, 암호화, MAC(Message Authentication Code), 압축)을 교환하고, 공통으로 지원하는 알고리즘을 협상한다

③ **DH 키 교환 — 클라이언트**: 클라이언트가 `SSH_MSG_KEXDH_INIT`으로 DH 공개값을 보낸다

④ **DH 키 교환 — 서버 응답**: 서버가 `SSH_MSG_KEXDH_REPLY`로 자신의 DH 공개값 + host key(공개키) + exchange hash H에 대한 서명을 보낸다. 양쪽이 독립적으로 **공유 비밀 K**와 **exchange hash H**를 계산한다

**DH 키 교환 자체는 상대가 누구인지 모르는 상태에서 일어난다.** DH는 "도청자가 엿볼 수 없는 공유 비밀 생성"만 보장하고, 상대의 신원은 보장하지 않는다. 그래서 DH 단독으로는 MITM(Man-in-the-Middle)에 취약하다 — 공격자가 중간에서 양쪽과 각각 DH를 수행할 수 있다. 이걸 방어하는 게 ④에서 시작되는 host key 기반 검증 과정(④⑤⑥)이다. 서버가 DH 교환 데이터에 host key(개인키)로 서명하고(④), 클라이언트가 그 서명을 검증한 뒤(⑤), known_hosts와 대조하여 신원을 확인한다(⑥). 공격자는 진짜 서버의 개인키가 없으니 서명을 위조할 수 없고, known_hosts에 저장된 키와도 일치하지 않는다.

### 1단계: 서버 신원 확인 (키 교환 완료 후)

⑤ 클라이언트가 서버의 host key로 exchange hash H의 서명을 검증한다. 이 검증은 두 가지를 동시에 확인한다: 서버가 해당 host key의 private key를 소유하고 있는지, DH 교환 데이터가 변조되지 않았는지. 단, "이 host key가 내가 접속하려는 서버의 것인지"는 ⑤만으로 알 수 없고, ⑥의 known_hosts 대조를 거쳐야 확인된다.

⑥ 클라이언트가 이 host key를 이전에 저장한 적 있는지 확인한다. 첫 접속(⑥-a)이면 저장된 host key가 없으므로 TOFU 질문이 뜬다. YES면 host key를 저장하고 NO면 접속을 중단한다. 이후 접속에서 일치(⑥-b)하면 통과하고, 불일치(⑥-c)하면 MITM 가능성으로 접속을 차단한다.

⑦ 공유 비밀 K로 대칭키(AES 등) + MAC 키를 도출한다. 여기서부터 모든 통신이 암호화된다.

### 2단계: 사용자 인증 (암호화 터널 안에서)

⑧ 클라이언트가 `SSH_MSG_USERAUTH_REQUEST`로 자신의 공개키 + session ID를 포함한 데이터에 대한 서명을 보낸다. 서버는 authorized_keys에서 공개키를 찾아 서명을 검증한다. **authorized_keys에는 TOFU가 없다** — 미등록 키는 즉시 거부된다.

⑨ 인증 성공 시 세션이 시작된다.

## DH에서 대칭키까지

"SSH는 공개키 암호화를 쓴다"는 말이 자칫 "공개키로 데이터를 암호화한다"로 오해될 수 있는데, 실제로는 다르다. 공개키 암호화는 **인증에만** 사용되고, 실제 데이터 암호화는 **DH로 도출한 대칭키**가 담당한다.

```text
DH 키 교환
    │
    ├─→ 공유 비밀 K (양쪽이 독립 계산, 네트워크에 노출되지 않음)
    │
    └─→ K + exchange hash H + session ID 등을 입력으로
        키 유도 함수(KDF) 적용
            │
            ├─→ 암호화 키 (AES 등)     ← 데이터 암호화에 사용
            ├─→ MAC 키                  ← 메시지 무결성 검증에 사용
            └─→ IV (초기화 벡터)        ← 암호화 알고리즘의 초기 상태
```

> 참고: 첫 키 교환에서는 session ID가 exchange hash H와 같은 값이다(RFC 4253 §7.2). 세션 중 재키잉(re-keying)이 발생하면 새 H가 계산되지만, session ID는 첫 키 교환의 H로 고정된다. 이 글에서는 재키잉을 다루지 않으므로 session ID = H로 이해하면 된다.

이 구조는 SSH만의 특징이 아니다. [TLS]({% post_url 2026-01-05-CS-Security-TLS-SSL %})도 동일한 구조를 따른다: 비대칭키는 핸드셰이크에서 인증과 키 교환에만 쓰이고, 실제 데이터 암호화는 대칭키가 담당한다. 비대칭키 연산이 대칭키 연산보다 수백~수천 배 느리기 때문이다.

## 흐름 상세: 서버 신원 확인 (④⑤⑥)

![ssh-process-deepdive]({{site.url}}/assets/images/ssh-process-deepdive.png){: .align-center}

위 도식의 분기를 정리하면 다음과 같다.

### 첫 접속과 이후 접속의 구분

⑥에서 갈린다. 이전에 저장한 host key가 있는가 없는가.

### 첫 접속일 때 (⑥-a)

MITM이 통신에 끼어들었다면, 공격자는 host key만 슬쩍 바꾸는 게 아니라 **자기 DH + 자기 host key + 자기 서명을 통째로** 만들어 보낸다. 이 경우 ⑤(서명 검증)도 정상 통과한다. 공격자의 공개키와 공격자의 서명이 수학적으로 맞으니까. 그리고 첫 접속이라 비교 대상이 없으므로 TOFU 질문으로 넘어가고, 사용자가 YES를 누르면 공격자의 키를 진짜로 믿어버린다. **이게 TOFU의 취약점이다.**

MITM이 없다면, ⑤에서 진짜 서버의 서명이 통과하고, TOFU 질문에 YES를 누르면 host key가 저장되어 정상 진행된다.

⑤(서명 검증)와 TOFU의 YES/NO는 **별개 단계**라는 점을 주의해야 한다. ⑤는 자동/암호학적이고, TOFU는 서명 검증을 통과한 후에만 사람에게 물어보는 것이다.

### 이후 접속일 때

첫 접속에서 저장한 host key가 있으므로 비교가 가능하다. 서버가 제시한 공개키가 저장된 것과 다르면(⑥-c) 접속이 차단된다. MITM이 자기 키를 보내도 여기서 잡힌다. 일치하면(⑥-b) ⑦으로 진행하여 사용자 인증(⑧) → 세션 시작(⑨)으로 이어진다.

> **참고: SSH와 TLS/mTLS의 비교**
>
> 양방향 인증이라는 점에서 mTLS(mutual TLS)와 구조적으로 비슷하지만, **신뢰 모델**과 **암호화-인증 순서**가 다르다.
>
> | 구분 | SSH | TLS 1.2 (mTLS) | TLS 1.3 (mTLS) |
> |------|-----|----------------|-----------------|
> | 신뢰 모델 | TOFU | PKI (CA 기반) | PKI (CA 기반) |
> | 암호화 vs 인증 순서 | 서버 인증은 DH와 동시, **사용자 인증은 암호화 안에서** | 인증서 교환(평문) → 암호화 | DH → **인증서 교환도 암호화 안에서** |
> | 중앙 신뢰 기관 | 없음 (각 클라이언트가 개별 관리) | CA | CA |
>
> SSH의 고유한 점: 인증이 **서버 인증(DH와 동시)** + **사용자 인증(암호화 터널 안)** 두 단계로 분리되어 있다. [TLS]({% post_url 2026-01-05-CS-Security-TLS-SSL %})는 보통 핸드셰이크에서 양쪽 인증을 한꺼번에 처리한다.
>
> 참고로 TLS 1.3에서는 post-handshake client authentication(RFC 8446 §4.6.2)이 가능하여, 핸드셰이크 완료 후 서버가 클라이언트 인증을 요청할 수도 있다. SSH에도 인증서 기반 인증(OpenSSH Certificate)이 존재하지만, 기본 모드가 아니고 대규모 인프라에서만 쓰인다.

<br>

# OpenSSH

SSH는 프로토콜이고, 이를 구현한 프로그램은 여러 가지가 있다. 프로토콜은 "host key를 검증해라", "사용자를 인증해라"라고만 규정하고, 그 데이터를 **어디에 어떻게 저장할지는 구현체가 결정**한다.

| 구현체 | 특징 | 저장 방식 |
|--------|------|-----------|
| **OpenSSH** | 가장 널리 사용. Linux/macOS 기본 탑재 | 파일 시스템 (`~/.ssh/`) |
| **PuTTY** | Windows 전용 GUI 클라이언트 | Windows Registry |
| **Dropbear** | 임베디드/경량 환경용. IoT, 라우터 등 | 파일 시스템 (경량 포맷) |
| **libssh / paramiko** | 라이브러리 형태. 프로그래밍적 SSH 구현 | 호출 코드가 결정 |

이 글에서는 가장 보편적인 **OpenSSH** 기준으로 설명한다.

## 구성 요소

### 클라이언트 측

| 파일/프로그램 | 역할 |
|---------------|------|
| `ssh` | 클라이언트 프로그램 |
| `~/.ssh/config` | 접속 설정 (alias, 기본 옵션 등) |
| `~/.ssh/known_hosts` | 접속했던 서버들의 host key 저장. 다음 접속 시 "같은 서버인가?" 대조 |
| `~/.ssh/id_ed25519` (`.pub`) | 사용자의 개인키/공개키 |

### 서버 측

| 파일/프로그램 | 역할 |
|---------------|------|
| `sshd` | 서버 데몬 |
| `/etc/ssh/sshd_config` | 데몬 설정 |
| `/etc/ssh/ssh_host_*_key` | 서버 자신의 host key 파일들 (알고리즘별: rsa, ecdsa, ed25519 등. sshd 설치 시 자동 생성) |
| `~/.ssh/authorized_keys` | 접속 허용된 사용자 공개키 |

### 키 쌍 2종류

| 키 | 용도 | 프로토콜 단계 |
|----|------|---------------|
| host key | 서버 신원 확인 | ④에서 사용 (서버가 보유) |
| user key | 사용자 인증 | ⑧에서 사용 (클라이언트가 보유) |

### 인증 방식

| 방식 | 특징 |
|------|------|
| 공개키 인증 | passwordless, 자동화에 적합 |
| 비밀번호 인증 | interactive 필요, 자동화에 부적합 |

> 참고: "passwordless"는 SSH 커뮤니티에서 "서버 계정 비밀번호 없이 인증 가능"이라는 의미로 관례적으로 사용되는 용어다. 개인키에 passphrase를 설정한 경우 ssh-agent/keychain 없이는 여전히 프롬프트가 뜨므로, 엄밀히는 "비밀번호 기반 인증이 아님(not password-based authentication)"이 더 정확하다.

프로토콜 도식에서 "저장된 host key"라고 표현한 것이 OpenSSH에서는 `~/.ssh/known_hosts` 파일이다.

## 접속 흐름

위 프로토콜 원리(①~⑨)를 OpenSSH가 실제로 처리하는 흐름은 크게 두 단계다.

| 단계 | 질문 | 기반 |
|------|------|------|
| ④⑤⑥ 서버 신원 확인 | "이 서버가 진짜인가?" | known_hosts |
| ⑧ 사용자 인증 | "이 사용자가 접속 권한이 있는가?" | authorized_keys 또는 비밀번호 |

### 서버 신원 확인

서버가 host key(공개키) + DH 서명을 보내면(④), 클라이언트가 서명을 검증하고(⑤), `~/.ssh/known_hosts`와 대조한다(⑥). known_hosts에 기록이 없으면 TOFU에 따라 신뢰 여부를 결정하고, 기록이 있으면 일치/불일치를 판정한다.

| ⑥ 분기 | 상황 | 동작 |
|--------|------|------|
| ⑥-a | known_hosts에 기록 없음 | interactive: "신뢰하겠습니까?" (TOFU) / BatchMode: 즉시 실패 |
| ⑥-b | known_hosts에 기록 있고 일치 | ⑦ 암호화 터널 수립 → ⑧로 진행 |
| ⑥-c | known_hosts에 기록 있는데 불일치 | **경고 + 접속 차단** (MITM 공격 가능성) |

### 사용자 인증

⑦에서 암호화된 터널이 수립된 후, 그 안에서 "이 사용자가 접속 권한이 있는가?"를 확인한다.

| 방식 | 메커니즘 | 비고 |
|------|----------|------|
| 공개키 인증 | 클라이언트의 공개키가 서버 `~/.ssh/authorized_keys`에 등록 | passwordless, 권장 |
| 비밀번호 인증 | 서버 OS 계정 비밀번호 입력 | interactive 필요, 자동화에 부적합 |

비밀번호를 평문으로 보내는 게 아니라, DH로 만든 암호화 터널 안에서 사용자 인증이 진행된다.

## Host Key Verification 상세

### host key vs fingerprint(지문)

host key는 서버의 공개키 그 자체로, 길이가 긴 Base64 문자열이다. 기계가 저장하고 비교한다. fingerprint(지문)는 host key의 해시값으로, 짧은 요약 문자열이다. 사람이 눈으로 비교할 때 사용한다.

```text
host key (공개키 원본)
AAAAB3NzaC1yc2EAAAADAQABAAABAQ...  ← 긴 Base64 문자열

    └─ hash ─→ fingerprint (지문)
               SHA256:W6Y3MRx9K2p...  ← 짧은 요약값
```

known_hosts에 저장되는 것은 **공개키 원본**이다. "지문 일치/불일치"라고 표현하지만, 실제로는 공개키 전체를 비교한다. "host key 미등록"이라는 것은 클라이언트의 known_hosts에 해당 서버의 공개키가 없다는 뜻이고, 곧 **이 서버가 진짜인지 판단할 근거가 없다**는 것이다.

### 문제가 발생하는 상황

Host Key Verification은 ⑥-a(미등록)와 ⑥-c(불일치) 두 가지 이유로 실패한다. 실무에서 이 두 분기를 만나는 대표적인 상황은 다음과 같다.

| 상황 | ⑥ 분기 | 발생하는 문제 |
|------|--------|-------------|
| 서버에 **처음 접속** | ⑥-a | known_hosts에 기록 없음 → 프롬프트 또는 실패 |
| 서버 **재설치/재구성** | ⑥-c | host key가 새로 생성됨 → 불일치 |
| 클라우드 인스턴스 **삭제 후 재생성** | ⑥-c | 같은 IP에 새 인스턴스 → 불일치 |
| **같은 IP가 다른 서버에 재할당** | ⑥-c | 다른 서버의 host key → 불일치 |
| **known_hosts 초기화/삭제** | ⑥-a | 모든 서버가 미등록 상태로 돌아감 |

정상적인 상황(재설치 등)에서 ⑥-c가 뜨면 known_hosts에서 해당 줄을 삭제하고 다시 등록하면 된다. 원리는 간단하다: known_hosts에서 해당 서버를 지우면 ⑥-c(불일치) 상태에서 ⑥-a(미등록) 상태로 돌아가고, TOFU에 의한 신뢰 확립이 처음부터 다시 시작된다. 인터넷에서 흔히 보이는 "known_hosts에서 삭제하세요" 해결법이 동작하는 이유가 이것이다.

```bash
ssh-keygen -R 192.168.1.100   # known_hosts에서 해당 호스트의 기존 host key 삭제
ssh-keyscan 192.168.1.100 >> ~/.ssh/known_hosts  # 새 host key 등록
```

> **ssh-keyscan의 한계**: `ssh-keyscan`은 네트워크를 통해 키를 수집할 뿐, 그 키가 진짜 해당 서버의 것인지 검증하지 않는다. 사설 네트워크 내부에서는 실용적으로 충분하지만, 신뢰할 수 없는 네트워크 경로에서는 MITM이 끼어있을 경우 공격자의 키를 등록할 수 있다. 엄격한 환경에서는 콘솔 접속, 클라우드 메타데이터 API, SSHFP(DNS) 레코드, 또는 OpenSSH Certificate 등 별도 신뢰 경로로 host key를 검증한 후 등록해야 한다.

### MITM 공격과 ⑥의 관계

⑤(서명 검증)는 "이 키와 이 서명이 수학적으로 맞는가"만 확인한다. 공격자가 자기 DH 공개값 + 자기 host key + 자기 서명을 통째로 보내면, 수학적으로는 맞기 때문에 ⑤를 통과한다. MITM을 실제로 걸러내는 것은 ⑥의 known_hosts 대조다.

```text
정상 접속:
클라이언트 ─────────────────→ 진짜 서버
             host key: ABC      (known_hosts에 ABC 저장됨)

MITM 공격 시:
클라이언트 ────→ [공격자] ────→ 진짜 서버
            host key: XYZ    host key: ABC
            (공격자 자신의 키)

⑤ 서명 검증: 통과 (공격자의 키와 서명이 수학적으로 맞으니까)
⑥-a(첫 접속): 비교 대상 없음 → TOFU로 수락하면 공격자 키를 신뢰 (취약점)
⑥-c(이후 접속): known_hosts의 ABC ≠ XYZ → 차단 (방어 성공)
```

결국 known_hosts는 ⑥-c에서 MITM을 감지하는 방어선이다. 단, ⑥-a(첫 접속)에서는 비교 대상 자체가 없으므로 방어할 수 없다.

## host key vs user key

SSH에는 키 쌍이 두 종류 등장한다. 서버 신원 확인에 쓰이는 host key와 사용자 인증에 쓰이는 user key다. 목적, 저장 위치, 흐름 방향이 모두 다르다.

| 구분 | host key | user key |
|------|----------|----------|
| 도식 위치 | ④ (서버가 제시) | ⑧ (클라이언트가 제시) |
| 목적 | 서버 신원 확인 | 사용자 인증 |
| 저장 위치 (클라이언트) | `~/.ssh/known_hosts` | `~/.ssh/id_ed25519` (개인키) |
| 저장 위치 (서버) | `/etc/ssh/ssh_host_*_key` | `~/.ssh/authorized_keys` |
| 방향 | 서버 → 클라이언트 | 클라이언트 → 서버 |

### known_hosts ↔ authorized_keys: 대칭 구조와 신뢰 모델의 차이

위 표에서 클라이언트의 known_hosts와 서버의 authorized_keys는 구조적으로 대응 관계에 있다. 둘 다 "상대방의 공개키를 저장해두고 대조한다"는 동일한 원리다. 하지만 **신뢰 확립 방식**이 근본적으로 다르다.

| 구분 | known_hosts (클라이언트) | authorized_keys (서버) |
|------|--------------------------|------------------------|
| 저장하는 것 | 서버의 공개키 (host key) | 사용자의 공개키 (user key) |
| 용도 | "이 서버가 진짜인가?" (⑥) | "이 사용자가 접속 권한이 있는가?" (⑧) |
| 신뢰 확립 방식 | TOFU — 처음 보는 키를 그냥 믿음 | **사전 등록** — 관리자가 미리 넣어둠 |
| "처음 보는 키" 대응 | 프롬프트로 물어봄 (yes/no) | **즉시 거부** (프롬프트 없음) |

서버 측이 더 엄격한 이유: 서버는 "이 사용자를 처음 보는데 일단 신뢰하겠습니까?" 같은 메커니즘이 없다. authorized_keys에 공개키가 없으면 접속이 거부된다. 클라이언트의 known_hosts는 TOFU로 "일단 믿고 저장"이 가능하지만, 서버의 authorized_keys는 반드시 사전에 공개키를 등록해야 한다.

## StrictHostKeyChecking

OpenSSH의 yes/no 프롬프트를 자동화하는 옵션이 [`StrictHostKeyChecking`](https://man.openbsd.org/ssh_config#StrictHostKeyChecking)이다. 값에 따라 보안 수준이 크게 다르다.

| 값 | ⑥-a (첫 접속, 키 없음) | ⑥-c (키 불일치) | 용도 |
|---|---|---|---|
| `ask` (기본값) | 사용자에게 yes/no 프롬프트 | 접속 거부 | interactive 환경의 기본 동작 |
| `yes` | 접속 거부 | 접속 거부 | known_hosts를 사전에 관리하는 환경 |
| `accept-new` (OpenSSH 7.6+) | 자동 수락 + 저장 | **접속 거부** | 자동화에서 TOFU는 허용, 변경 감지는 유지 |
| `no` | 자동 수락 + 저장 | **경고만 하고 접속 허용** | ⑥-c 방어까지 무력화 — 권장하지 않음 |

`accept-new`는 ⑥-a(첫 접속)만 자동화하고 ⑥-c(변경된 키 감지)는 유지하므로, 자동화 환경에서 `no` 대신 사용해야 하는 옵션이다. `no`는 ⑥-c까지 우회하여 **이미 확립된 신뢰마저 무시**하므로 MITM 방어가 사실상 무력화된다. 어느 값이든 "처음 보는 키를 그냥 믿는다"는 TOFU 원칙 자체는 동일하다.

## BatchMode

interactive 프롬프트를 일절 띄우지 않는 SSH 옵션이다.

```bash
ssh -o BatchMode=yes user@host "hostname"  # interactive 프롬프트 없이 접속 시도
```

| 상황 | BatchMode=yes일 때 동작 |
|------|------------------------|
| 비밀번호 묻기 | 안 묻고 즉시 실패 |
| host key 확인 (yes/no) | 안 묻고 즉시 실패 |
| passphrase 입력 | 안 묻고 즉시 실패 |

스크립트/cron/CI/CD처럼 사람이 없는 환경에서 "접속 가능한지 깔끔하게 테스트"할 때 주로 사용한다. 성공하면 인증이 완벽히 설정된 것이고, 실패하면 뭔가 빠진 것이다.


## ssh-keyscan

서버에 로그인하지 않고 host key(공개키)만 가져오는 OpenSSH 도구다.

```bash
ssh-keyscan -T 5 192.168.1.100          # -T: 타임아웃(초). 기본값 5
ssh-keyscan 192.168.1.100 >> ~/.ssh/known_hosts  # known_hosts에 추가 → ⑥-a 해결
```

ssh-keyscan은 서버가 지원하는 **모든 키 알고리즘**에 대해 각각 한 줄씩 출력한다.

> 그래서 출력 결과가 길다.

출력 형태는 `호스트 알고리즘 공개키` 형태로, known_hosts의 저장 형식과 동일하다. 그래서 `>>` 리다이렉션으로 바로 추가 가능하다.

```bash
# ssh-keyscan 192.168.1.100 실행 결과 (예시)
192.168.1.100 ssh-rsa AAAAB3NzaC1yc2EAAAA...     # RSA 키
192.168.1.100 ecdsa-sha2-nistp256 AAAAE2VjZH...   # ECDSA 키
192.168.1.100 ssh-ed25519 AAAAC3NzaC1lZDI1...     # Ed25519 키

# 이 형태가 known_hosts의 저장 형식과 동일:
# [호스트] [알고리즘] [공개키(Base64)]
```

서버 하나당 보통 2~3줄이 출력된다(지원하는 알고리즘 수만큼). 출력 형태가 known_hosts와 **동일한 포맷**이라 `>>` 리다이렉션으로 바로 추가할 수 있다. known_hosts 추가는 자동이 아닌 수동이다 — 필요할 때 직접 `>>` 로 append한다.

## SSH Config

`~/.ssh/config`로 접속 정보를 alias화할 수 있다.

```bash
Host gpu1                    # alias — ssh gpu1 으로 접속
    HostName 192.168.1.100   # 실제 IP 또는 hostname
    User my-user             # 접속 계정
```

설정 후 `ssh gpu1`만으로 `ssh my-user@192.168.1.100`와 동일 효과.

<br>

# 실무에서 겪는 접속 문제

## 사례 1: 자동화 스크립트에서 SSH 설정 순서

여러 노드에 SSH 접속을 설정하는 자동화 스크립트를 만드는 중이었다. 각 노드의 인증 상태를 프로그래밍적으로 확인하기 위해 BatchMode를 진단 도구로 사용했다.

```bash
# 1단계: BatchMode로 현재 상태 진단
ssh -o BatchMode=yes user@192.168.1.100 "hostname"
# → Host key verification failed (⑥-a: known_hosts에 host key 없음)

# 2단계: host key 등록
ssh-keyscan 192.168.1.100 >> ~/.ssh/known_hosts

# 3단계: 다시 시도
ssh -o BatchMode=yes user@192.168.1.100 "hostname"
# → Permission denied (publickey,password) (⑧: 공개키 미등록 + BatchMode라 비밀번호 입력 불가)

# 4단계: expect로 비밀번호 접속하여 공개키 등록
# (비밀번호를 자동 입력하여 접속한 뒤, authorized_keys에 공개키 추가)

# 5단계: 최종 검증
ssh -o BatchMode=yes user@192.168.1.100 "hostname"
# → 성공 (⑥ host key + ⑧ user key 모두 완료)
```

이 순서는 SSH 접속의 2단계(서버 확인 → 사용자 인증)를 그대로 반영한다. BatchMode를 처음과 끝에 사용하여 설정 전후 상태를 검증한 것.

<details markdown="1">
<summary><b>expect/sshpass: 비밀번호 인증 자동화 도구</b></summary>

위 4단계에서 비밀번호 인증을 자동화하기 위해 사용한 도구가 **expect**다. SSH 프로토콜이나 OpenSSH의 구성 요소가 아니라, interactive 입력을 자동화하기 위한 **외부 도구**다.

**expect**: 터미널 출력을 감시하다가 특정 문자열이 나오면 미리 정한 입력을 보내는 범용 자동화 도구.

```bash
expect -c '
spawn ssh user@192.168.1.100 "hostname"   # ssh 프로세스를 expect 제어 하에 실행
expect "password:"                          # ssh가 출력하는 텍스트를 감시
send "my-password\r"                        # ssh의 stdin에 텍스트 주입 (\r = Enter)
expect eof                                  # 프로세스 종료 대기
'
```

`spawn`은 expect 언어의 내장 명령어(쉘 커맨드가 아님)로, 가상 터미널(PTY)을 생성하여 대상 프로세스의 입출력을 가로챈다. SSH뿐 아니라 ftp, mysql 등 모든 interactive 프로그램 자동화에 사용할 수 있으며, macOS에 기본 내장되어 있다(`/usr/bin/expect`).

**sshpass**: SSH 전용 비밀번호 자동 입력 도구. expect보다 단순하지만 macOS에 기본 설치되어 있지 않다.

```bash
sshpass -p 'my-password' ssh user@192.168.1.100 "hostname"  # 비밀번호를 인자로 전달하여 자동 입력
```

| 도구 | 범용성 | 복잡도 | macOS 기본 |
|------|--------|--------|-----------|
| expect | 모든 interactive 프로그램 | 높음 (자체 스크립팅 언어) | O |
| sshpass | SSH 전용 | 낮음 (한 줄) | X (`brew install` 필요) |

공개키 인증이 완전히 설정되면 이 도구들은 더 이상 필요 없다.

</details>

## 사례 2: 클라우드 인스턴스 교체 후 접속 불가

**증상**: 같은 IP에 인스턴스를 재생성했더니 접속이 차단된다.

```text
@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@
@    WARNING: REMOTE HOST IDENTIFICATION HAS CHANGED!     @
@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@
```

**원인**: ⑥-c 분기. 같은 IP에 새 host key를 가진 서버가 응답하고 있다. 이전 인스턴스의 host key가 known_hosts에 남아 있어서 불일치가 발생한다.

**해결**:

```bash
ssh-keygen -R 192.168.1.100                              # 기존 host key 삭제 (⑥-c → ⑥-a로 전환)
ssh-keyscan 192.168.1.100 >> ~/.ssh/known_hosts           # 새 host key 등록
ssh user@192.168.1.100                                     # 재접속
```

## 사례 3: Permission denied (publickey)

**증상**: 공개키 인증이 안 되고, 비밀번호 프롬프트도 뜨지 않는다.

```text
user@192.168.1.100: Permission denied (publickey).
```

**원인**: 대부분 서버 측 파일 퍼미션 문제다. SSH는 보안상 느슨한 퍼미션의 키 파일을 거부한다.

**해결**: 서버에서 퍼미션을 확인한다.

```bash
chmod 700 ~/.ssh                     # .ssh 디렉토리: 소유자만 접근
chmod 600 ~/.ssh/authorized_keys     # authorized_keys: 소유자만 읽기/쓰기
```

퍼미션이 정상인데도 안 된다면 sshd 로그를 확인한다.

```bash
# Debian/Ubuntu
sudo tail -f /var/log/auth.log

# RHEL/CentOS/Rocky
sudo journalctl -u sshd -f
```

로그에서 `Authentication refused: bad ownership or modes` 같은 메시지가 보이면 퍼미션 문제가 맞다. 그 외에 SELinux 컨텍스트가 꼬인 경우도 있다(`restorecon -Rv ~/.ssh`로 복구).

<br>

# 정리

SSH 접속은 크게 세 단계로 진행된다: **알고리즘 협상과 DH 키 교환**으로 암호화 채널을 수립하고, **host key로 서버 신원을 확인**한 뒤, **암호화된 터널 안에서 사용자를 인증**한다. 신뢰 모델은 TOFU로, 첫 접속 시 검증 없이 신뢰하고 이후 known_hosts에 저장된 키로 대조한다.

이 글에서 다루지 않은 내용 중, 시간이 되면 나중에 다른 글에서 다뤄 볼 만한 주제들이 있다. 각각이 무엇인지만 짧게 짚어 두자.

**ssh-agent**는 개인키를 메모리에 캐시해서 passphrase 반복 입력 없이 인증을 처리하는 데몬이다. 한 번 잠금 해제하면 세션 동안 자동으로 서명을 수행한다. **keychain**은 ssh-agent의 수명을 로그인 세션 전체로 확장해주는 래퍼(wrapper)로, 터미널을 닫았다 열어도 agent가 유지된다.

**key forwarding(agent forwarding)**은 로컬 ssh-agent를 원격 서버에서도 사용할 수 있게 해주는 기능이다. A → B → C로 접속할 때 A의 키로 C에 인증할 수 있다. **SSH key 종류(ed25519 vs rsa vs ecdsa)**는 알고리즘별 키 길이, 성능, 보안 강도가 다르며, 현재는 ed25519가 권장된다.

<br>

# 부록: 에러 메시지와 프로토콜 단계 매핑

SSH 접속 시 만나는 에러 메시지가 프로토콜의 어느 단계에서 실패한 것인지 빠르게 확인할 수 있는 레퍼런스다.

## ⑥-a: 첫 접속 (known_hosts에 기록 없음)

**interactive 모드** (`StrictHostKeyChecking=ask`):

```text
The authenticity of host '192.168.1.100 (192.168.1.100)' can't be established.
ED25519 key fingerprint is SHA256:W6Y3MRx9K2p...
Are you sure you want to continue connecting (yes/no/[fingerprint])?
```

**StrictHostKeyChecking=yes**:

```text
No ED25519 host key is known for 192.168.1.100 and you have requested strict checking.
Host key verification failed.
```

**BatchMode=yes**:

```text
Host key verification failed.
```

## ⑥-c: 이후 접속, host key 불일치

```text
@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@
@    WARNING: REMOTE HOST IDENTIFICATION HAS CHANGED!     @
@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@
IT IS POSSIBLE THAT SOMEONE IS DOING SOMETHING NASTY!
Someone could be eavesdropping on you right now (man-in-the-middle attack)!
...
Offending ED25519 key in /Users/user/.ssh/known_hosts:42
Host key verification failed.
```

## ⑧: 사용자 인증 실패

**공개키 미등록 (authorized_keys에 없음)**:

```text
user@192.168.1.100: Permission denied (publickey).
```

**비밀번호 인증 실패**:

```text
user@192.168.1.100's password:
Permission denied, please try again.
```

**클라이언트 개인키 퍼미션 문제**:

```text
@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@
@         WARNING: UNPROTECTED PRIVATE KEY FILE!          @
@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@
Permissions 0644 for '/Users/user/.ssh/id_ed25519' are too open.
This private key will be ignored.
```

<br>

# 참고 링크

- [RFC 4251 - The Secure Shell (SSH) Protocol Architecture](https://datatracker.ietf.org/doc/html/rfc4251)
- [RFC 4253 - The Secure Shell (SSH) Transport Layer Protocol](https://datatracker.ietf.org/doc/html/rfc4253)
- [RFC 4252 - The Secure Shell (SSH) Authentication Protocol](https://datatracker.ietf.org/doc/html/rfc4252)
- [공개키 암호화 - 비대칭키]({% post_url 2026-01-04-CS-Cryptography-04 %})
- [PKI]({% post_url 2026-01-18-CS-PKI %})
- [TLS/SSL 프로토콜]({% post_url 2026-01-05-CS-Security-TLS-SSL %})

<br>