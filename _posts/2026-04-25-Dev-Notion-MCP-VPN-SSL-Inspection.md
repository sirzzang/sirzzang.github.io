---
title: "[MCP] VPN SSL Inspection으로 인한 Notion MCP 연결 실패"
excerpt: "같은 VPN SSL Inspection인데 kubectl과는 해결이 정반대다. Node.js의 trust 모델과 NODE_EXTRA_CA_CERTS 해법을 정리해 보자."
permalink: /dev/Dev-Notion-MCP-VPN-SSL-Inspection/
categories:
  - cs-security
  - prog-tools
  - troubleshooting
toc: true
header:
  teaser: /assets/images/blog-Dev.jpg
tags:
  - Claude-Code
  - Notion
  - MCP
  - Node.js
  - TLS
  - certificate
  - VPN
  - SSL-Inspection
  - NODE_EXTRA_CA_CERTS
last_modified_at: 2026-10-21
---

<br>

# 배경

[이전 글]({% post_url 2026-04-23-Dev-Kubectl-VPN-SSL-Inspection %})에서 재택 VPN 환경의 SSL Inspection이 `kubectl` ↔ `kube-apiserver` TLS를 가로채 인증서 검증 실패를 일으키는 문제를 정리했다. 같은 시기에 **Claude Code의 Notion MCP**에서도 거의 동일한 원인으로 연결 실패가 발생했다.

사실 이 트러블슈팅은 [프롬프트 패턴 개선기]({% post_url 2026-04-10-Articles-AI-Prompt-Pattern-Improvement %})에서 "52턴짜리 비효율 세션"으로 회고했던 바로 그 사건이다. 당시에는 환경 맥락을 첫 프롬프트에 담지 않아서 턴이 과도하게 소모된 사례로 분석했는데, 지금은 관점을 조금 바꿔서 그때 궁금했던 것들 — 왜 브라우저는 되고 Node.js는 안 되는지, 왜 Jira MCP는 되는데 Notion MCP만 안 되는지 — 을 제대로 확인해 보고자 한다.

같은 "VPN SSL Inspection" 이라는 원인이지만, 도구의 trust 모델이 달라서 **증상도 다르고 해결 방향도 정반대**다. `kubectl`은 회사 CA를 trust에 넣으면 안 되는 반면, Node.js 기반 도구인 Notion MCP는 회사 CA를 **넣어야** 풀린다. 이 글에서는 왜 그런 차이가 생기는지를 중심으로 정리한다.

<br>

# TL;DR

1. 증상
   - 재택 VPN 환경에서만 Claude Code의 Notion MCP가 `Failed to connect`
   - 재연결 시 `SDK auth failed: self signed certificate in certificate chain`
   - 회사 WiFi에서는 정상 동작

2. 원인
   - 회사 VPN의 SSL Inspection이 `mcp.notion.com` TLS를 가로채 회사 CA로 재서명
   - Claude Code가 쓰는 Node.js 계열 런타임은 기본적으로 OS 키체인을 참조하지 않고 자체 내장 CA bundle(Mozilla 기반)만 사용하므로 회사 CA를 알 수 없음
   - `kubectl`과 달리 이번 대상은 **공인 인터넷 서비스**이므로, VPN 없이 직접 연결하면 정상 동작한다

3. 해결
   - macOS 시스템 인증서를 PEM으로 내보내 `NODE_EXTRA_CA_CERTS` 환경변수로 Node.js에 주입
   - 당시에는 `~/.zshrc`와 `settings.json` env 두 곳에 설정해 해결
   - Claude Code 2.1.101부터는 OS 인증서 저장소를 기본으로 신뢰하므로, 키체인에 회사 CA가 등록된 환경이라면 이 설정 없이도 동작한다

<br>

# 문제

집에서 회사 VPN을 연결한 상태에서 Claude Code의 Notion MCP가 동작하지 않는다.

```text
Failed to connect
```

`/mcp`로 재연결을 시도하면 다음 에러가 나온다.

```text
SDK auth failed: self signed certificate in certificate chain
```

환경별 차이는 `kubectl` 때와 비슷한 패턴이지만, 마지막 행이 다르다.

| 접속 환경 | 결과 |
|---|---|
| 회사 사무실 (사내망 직접 연결) | 정상 동작 |
| 재택 + 회사 VPN | TLS 검증 실패 |
| VPN 끄고 집 공유기 | **정상 동작** | 

VPN을 끄면 정상 동작한다. `mcp.notion.com`은 공인 인터넷 서비스이므로 VPN 없이도 접근할 수 있고, 이때는 진짜 Notion 서버가 공인 CA로 서명한 인증서를 직접 보내 주기 때문이다. **VPN을 켜는 순간** 경로에 방화벽이 끼면서 인증서가 바뀐다는 뜻이다.

<br>

# 원인 분석

## Notion MCP는 Claude Code 프로세스 안에서 동작한다

본격적인 분석 전에 짚고 갈 것이 있다. 이번 사례에서 TLS 검증을 수행하는 주체는 Claude Code 본체이고, Claude Code는 **JavaScript 애플리케이션**이다. Notion MCP는 `--transport http`로 등록한 원격 MCP 서버라서 별도 로컬 프로세스를 띄우지 않는다. 즉 `mcp.notion.com`으로 향하는 HTTPS 요청은 Claude Code가 직접 보내고, 그 TLS 핸드셰이크 검증도 **Claude Code가 돌아가는 런타임의 TLS 스택과 내장 CA bundle**이 담당한다.

> 이 런타임은 설치 방식에 따라 다르다. 2.1.113 이전 버전을 npm 패키지로 설치했다면 Node.js 위에서 돌고, 네이티브 설치판은 Bun 런타임을 내장한 단일 바이너리다(2026년 10월 기준 확인). 두 런타임 모두 기본으로 Mozilla 기반 내장 CA bundle을 쓰고 `NODE_EXTRA_CA_CERTS`를 지원하므로, 이 글에서 다루는 trust 모델은 같다. 이하 편의상 Node.js trust 모델이라 부른다.

그래서 같은 SSL Inspection 환경이라도, `kubectl`(Go의 `crypto/tls`)과 Notion MCP(Claude Code 런타임의 TLS 스택)는 서로 **다른 trust 소스**를 들고 인증서를 검증하게 된다. 뒤이어 보겠지만, 에러 메시지가 다르고 해법이 정반대로 갈리는 근본 원인이 여기에 있다.

> 참고로 다음 절에서 비교할 Jira MCP는 `uvx`(Python)로 실행되는 **로컬** MCP 서버이고, 이 경우엔 Claude Code가 아니라 `uvx`로 띄운 Python 프로세스가 TLS 검증의 주체가 된다. 그래서 같은 "MCP 도구"라도 Node.js trust 모델이 적용되는지가 갈린다.

## SSL Inspection은 외부 트래픽이 본래 주 대상

SSL Inspection의 동작 메커니즘(방화벽 MITM, 인증서 즉석 생성, Trust/Untrust CA 분류 등)은 [이전 글]({% post_url 2026-04-23-Dev-Kubectl-VPN-SSL-Inspection %})에서 자세히 다루었으므로 여기서는 생략한다.

한 가지 짚어둘 차이는, `kubectl` 사례는 **사내 사설 IP의 내부 서비스**가 SSL Inspection에 걸린 것이고, 이번 사례는 **공인 인터넷 서비스(`mcp.notion.com`)**가 걸린 것이라는 점이다. "회사 내부 서버도 아닌데 왜 재서명하는가" 라는 의문이 들 수 있지만, 사실 SSL Inspection의 **본래 주 대상은 외부 인터넷 트래픽**이다.

- **DLP(Data Loss Prevention)**: 사내 데이터가 **외부로** 유출되는지 검사
- **악성 트래픽 탐지**: **외부에서** 들어오는 멀웨어, C2 통신 탐지
- **카테고리 차단**: 도박, 악성 등 **외부** 사이트 차단

전부 외부로 나가는/외부에서 들어오는 트래픽을 보기 위한 것이다. 회사 VPN에 연결하면 모든 트래픽이 회사 네트워크를 경유하고, 방화벽은 TLS 연결이면 대상이 사설 IP든 공인 도메인이든 가리지 않고 가로챈다. `mcp.notion.com`이 공인 서비스라는 사실은 SSL Inspection 대상에서 빠지는 이유가 되지 않는다. 오히려 **외부 서비스야말로 SSL Inspection의 본래 검사 대상**이다.

## kubectl 사례와의 비교

두 사례를 나란히 놓고 비교해 보자.

| | kubectl (kube-apiserver) | Notion MCP (mcp.notion.com) |
|---|---|---|
| 대상 | 사설 IP의 사내 서비스 | 공인 인터넷 서비스 |
| 원본 서버 인증서 | 사설 CA(`rke2-server-ca`) 서명 | 공인 CA(DigiCert 등) 서명 |
| 방화벽 분류 | Untrust (사설 CA라 검증 불가) | Trust (공인 CA라 검증 가능) |
| 재서명 CA | `ExampleCorp_Untrust_ECDSA` | `ExampleCorp_Trust_ECDSA` |
| VPN 없으면? | 사설 IP라 라우팅 자체가 안 됨 | **정상 동작** (공인 CA 인증서 직접 받음) |
| 에러 메시지 | `x509: certificate signed by unknown authority` | `self signed certificate in certificate chain` |

에러 메시지는 표현이 다르지만 본질은 같다. Go(kubectl)는 "서명한 CA를 모르겠다"(`unknown authority`), Node.js는 "체인 안에 내가 모르는 자기서명 인증서가 있다"(`self signed certificate in certificate chain`)로 표현할 뿐, 둘 다 **"이 인증서를 서명한 CA가 내 trust store에 없다"**는 동일한 상태를 가리킨다. TLS 라이브러리(Go `crypto/tls` vs OpenSSL 계열 라이브러리. Node.js는 OpenSSL, Bun은 BoringSSL을 쓴다)에 따라 표현만 다른 것이다.

`openssl s_client`로 실제 확인해 보면 이 분류를 직접 볼 수 있다.

```bash
$ echo | openssl s_client -servername mcp.notion.com -connect mcp.notion.com:443 2>/dev/null \
    | openssl x509 -noout -issuer -subject

issuer=CN=ExampleCorp_Trust_ECDSA
subject=CN=notion.com
```

> kubectl 때는 `-connect 10.50.31.10:6443`처럼 IP 주소로 접속해서 SNI가 비었지만, 이번에는 호스트명으로 접속하므로 OpenSSL이 자동으로 SNI를 보낸다. `-servername`을 명시하지 않아도 결과는 같지만, [습관으로 붙여 두는 편]({% post_url 2026-04-25-CS-TLS-SNI-SAN %})이 좋다.

방화벽이 `mcp.notion.com`에 대신 연결하면 Notion의 진짜 서버 인증서(공인 CA 서명)를 받는다. 공인 CA 체인이 정상 확인되므로 [이전 글에서 정리한]({% post_url 2026-04-23-Dev-Kubectl-VPN-SSL-Inspection %}#trust-ca와-untrust-ca) Trust CA로 재서명한다. `kubectl` 때 사설 CA라서 Untrust로 분류된 것과 다른 경로다.

그런데 **Node.js 입장에서는 Trust CA든 Untrust CA든 결과가 같다.** 둘 다 회사 CA이고, Node.js의 내장 CA bundle에는 어느 쪽도 없다.

## Node.js의 trust 모델

여기가 핵심이다. Node.js는 기본적으로 자체 내장한 **CA bundle(Mozilla NSS 기반)만** 사용한다. 이 bundle에는 DigiCert, Let's Encrypt 같은 공인 CA만 들어 있고, 회사 CA는 당연히 없다.

- **VPN 없이 직접 연결할 때**: `mcp.notion.com`의 진짜 인증서(공인 CA 서명)가 온다 → 내장 bundle에 해당 공인 CA가 있으므로 검증 성공
- **VPN 경유할 때**: 방화벽이 재서명한 인증서(회사 CA 서명)가 온다 → 내장 bundle에 회사 CA가 없으므로 검증 실패

에러 메시지도 이 구조를 반영한다. `self signed certificate in certificate chain`은 Node.js가 인증서 체인을 따라 올라가다 회사 루트 CA에 도달했는데, 이 루트 CA를 모르니까 "체인 안에 알 수 없는 자기서명 인증서가 있다"고 판단한 것이다.

<br>

# 그런데 이건 왜 되는가

Node.js의 내장 CA bundle에 회사 CA가 없어서 Notion MCP가 실패한다는 건 알겠다. 그런데 같은 VPN 환경에서 **되는 것들**이 있다. 대관절 이것들은 "왜 되는 건지" 궁금하지 않을 수 없다. 왜 되는지를 보면 Node.js의 문제가 더 선명해진다.

## 브라우저: google.com은 왜 정상인가

같은 VPN 환경에서 브라우저로 `google.com`, `naver.com` 같은 사이트에 접속하면 정상으로 열린다. 너무나도 당연하게 생각했지만, 두 차례의 트러블슈팅을 하다 보니, "이건 왜 되는지" 의문이 들지 않을 수 없다.

VPN을 켜면 모든 트래픽이 회사 방화벽을 경유하고, 방화벽은 TLS 연결이면 대상을 가리지 않고 가로챈다고 했다. 그렇다면 `google.com`도 SSL Inspection 대상이어야만 한다. 실제로 `openssl`로 확인해 보면 `google.com` 역시 회사 CA로 재서명되어 있다.

```bash
$ echo | openssl s_client -servername google.com -connect google.com:443 2>/dev/null \
    | openssl x509 -noout -issuer -subject

issuer=CN=ExampleCorp_Trust_ECDSA
subject=CN=*.google.com
```

브라우저에서 인증서 상세를 열어 봐도 발급 기관이 회사 CA로 찍혀 있지만, 자물쇠는 정상이고 차단도 되지 않는다.

![VPN 환경에서 google.com 인증서 — 회사 CA로 재서명되었지만 유효]({{site.url}}/assets/images/vpn-on-google-certificate.png){: .align-center width="500"}

이것이 가능한 이유는 **브라우저가 OS 시스템 trust store(macOS 키체인)를 참조**하기 때문이다. 회사 IT/MDM 정책으로 macOS 키체인에 회사 CA가 "항상 신뢰"로 설치되어 있다.

![macOS 키체인에 등록된 회사 CA 인증서]({{site.url}}/assets/images/macos-keychain.png){: .align-center width="700"}

브라우저는 인증서 체인을 따라 올라가다 회사 루트 CA에 도달하면 키체인을 확인하고, 거기에 "항상 신뢰"로 등록되어 있으니 검증을 통과시킨다. 그래서 회사 CA로 재서명된 인증서라도 정상으로 보이는 것이다.

> Windows도 원리는 같다. 시스템 trust store가 키체인 대신 **Windows 인증서 저장소**(certmgr.msc → "신뢰할 수 있는 루트 인증 기관")이고, 회사 IT가 **그룹 정책(GPO)**으로 회사 CA를 배포한다. Chrome·Edge 등은 양쪽 OS 모두 시스템 trust store를 참조하므로 동작 방식이 동일하다. 예외는 **Firefox**로, 기본적으로 자체 NSS 인증서 저장소를 사용해 OS trust store를 참조하지 않는다. `security.enterprise_roots.enabled` 설정을 켜야 OS store도 함께 참조한다. 회사 환경에서 Firefox만 HTTPS 경고가 뜨는데 대부분 이것이 원인이다. 다만 Firefox는 MITM으로 보이는 TLS 오류를 만나면 이 설정을 스스로 켜고 다시 접속을 시도하기도 해서, 경고 없이 넘어가는 경우도 있다.

**Node.js는 이 키체인을 참조하지 않는다.** 키체인에 회사 CA가 등록되어 있든 말든 Node.js에게는 아무 의미가 없다. 같은 머신, 같은 네트워크, 같은 SSL Inspection인데 브라우저는 되고 Node.js는 안 되는 이유가 바로 이것이다.

## Jira MCP: 같은 MCP인데 왜 되는가

같은 VPN 환경에서 Notion MCP는 안 되는데, Jira MCP는 정상 동작한다. 둘 다 Claude Code에서 실행하는 MCP 도구이고, 둘 다 외부 SaaS에 TLS로 연결하는 구조다. 방화벽이 재서명하는 건 마찬가지일 텐데, 왜 하나는 되고 하나는 안 되는 걸까?

차이는 **런타임**에 있다. Claude Code의 MCP 도구 설정을 보면 드러난다.

```bash
# Jira MCP — Python(uvx)으로 실행
claude mcp add-json jira '{
  "command": "uvx",
  "args": ["--system-certs", "mcp-atlassian"],
  "env": {
    "JIRA_URL": "...",
    "JIRA_USERNAME": "...",
    "JIRA_API_TOKEN": "..."
  }
}' --scope user

```

### 이 설정은 Atlassian 공식 MCP가 아니다

먼저 짚어 둘 것은, 이 설정은 **Atlassian 공식 원격 MCP가 아니라 커뮤니티 Python 패키지**(`mcp-atlassian`)를 로컬에 띄우는 구조라는 점이다. Notion이 벤더가 직접 호스팅하는 원격 MCP 서버(`https://mcp.notion.com/mcp`)에 HTTP transport로 곧장 붙는 것과 달리, 여기서는 `uvx`로 Python 어댑터를 로컬에 띄워 Jira REST API 호출 결과를 MCP 프로토콜로 노출시키는 방식이다.

| | Notion MCP (이 글) | Jira MCP (이 글) | Atlassian 공식 원격 MCP (가정) |
|---|---|---|---|
| 제공 주체 | Notion 공식 원격 서버 | 커뮤니티 `mcp-atlassian` | Atlassian 공식 원격 서버 |
| Transport | HTTP | stdio (로컬 프로세스) | HTTP |
| TLS 검증 주체 | Claude Code (Node.js) | `uvx`로 띄운 Python | Claude Code (Node.js) |
| 인증 | OAuth | Jira API token | OAuth |

만약 같은 VPN 환경에서 Atlassian 공식 원격 MCP를 등록했더라면, 구조가 Notion과 동일해져서(HTTP transport + Claude Code의 Node.js TLS 스택) **Jira MCP도 똑같이 깨졌을 것이다**. 즉 이 글에서 Jira가 정상 동작한 건 "Jira라서"가 아니라 "어쩌다 커뮤니티 Python 어댑터 경로를 골라 둔 덕분"이다. 결국 핵심은 TLS 검증이 어떤 런타임에서 일어나느냐로 모인다.

### 런타임 차이가 결과를 가른다

`uvx`는 Python 패키지 러너다. Node.js 진영의 `npx`와 같은 역할로, 패키지를 격리된 가상 환경에 설치하고 실행한다. Jira MCP는 `uvx`로 띄운 Python 프로세스로, Notion MCP는 Claude Code(Node.js 계열 런타임)로 동작한다.

사실 Python도 기본적으로는 Node.js와 마찬가지로 OS 키체인을 참조하지 않는다. 대표적인 HTTP 라이브러리인 `requests`는 자체 CA bundle(`certifi` 패키지)을 쓴다. 그런데 `mcp-atlassian`은 v0.19.0(2026년 2월)부터 시작할 때 `truststore` 라이브러리로 Python의 `ssl` 모듈이 **OS 신뢰 저장소**로 인증서를 검증하도록 바꿔 둔다. 이 동작은 기본으로 켜져 있고, `MCP_ATLASSIAN_USE_SYSTEM_TRUSTSTORE` 환경변수로 끌 수 있다. macOS에서는 키체인을 참조하게 되고, 키체인에 회사 CA가 "항상 신뢰"로 등록되어 있으므로 방화벽이 재서명한 인증서도 검증이 통과하는 것이다.

Jira MCP의 args에 들어간 `--system-certs`는 이것과 다른 층위의 플래그다. uv 0.11.0에서 `--native-tls`를 대신해 생긴 옵션으로, **uv 자신이** 패키지 인덱스(PyPI)에서 `mcp-atlassian`을 내려받을 때 OS 인증서 저장소로 검증하게 한다. VPN 환경에서는 이 다운로드도 SSL Inspection을 거치므로 캐시가 비어 있을 때는 필요하지만, uvx가 띄운 Python 프로세스의 인증서 검증에는 관여하지 않는다.

Node.js에도 OS 인증서 저장소를 쓰게 하는 옵션이 있다. `--use-system-ca` 플래그(v23.8.0, v22.15.0부터)와 `NODE_USE_SYSTEM_CA=1` 환경변수(v24.6.0, v22.19.0부터)다. 다만 이 글의 해결 시점에는 Claude Code 문서가 안내하던 방법인 `NODE_EXTRA_CA_CERTS` 환경변수로 추가 CA 인증서 파일을 직접 주입했다.

<br>

# 해결

macOS 키체인에서 시스템 인증서(회사 CA 포함)를 PEM 형식으로 내보내고, `NODE_EXTRA_CA_CERTS` 환경변수로 Node.js에 전달한다.

Jira MCP의 `truststore`가 검증 기준을 certifi bundle에서 OS 신뢰 저장소로 **통째로 바꾸는** 방식이었다면, `NODE_EXTRA_CA_CERTS`는 Node.js 내장 Mozilla bundle을 **그대로 유지**하면서 지정한 PEM 파일의 CA를 **추가로** 신뢰 목록에 넣는 확장 방식이다. 기존에 신뢰하던 공인 CA(DigiCert 등)는 그대로 살아 있고, 거기에 회사 CA가 더해지는 구조다.

## 1단계: 시스템 인증서를 PEM 파일로 내보내기

```bash
# System Keychain + SystemRootCertificates 모두 포함
security find-certificate -a -p /Library/Keychains/System.keychain > ~/.claude/system-certs.pem
security find-certificate -a -p /System/Library/Keychains/SystemRootCertificates.keychain >> ~/.claude/system-certs.pem
```

이렇게 하면 macOS에 등록된 모든 시스템 인증서(회사 CA 포함)가 하나의 PEM 파일에 담긴다.

## 2단계: NODE_EXTRA_CA_CERTS 환경변수 설정

이번에는 **두 곳에** 설정했다.

```bash
# ~/.zshrc에 추가
export NODE_EXTRA_CA_CERTS="$HOME/.claude/system-certs.pem"
```

```json
// Claude Code settings.json의 env에 추가
{
  "NODE_EXTRA_CA_CERTS": "/Users/<username>/.claude/system-certs.pem"
}
```

### 두 곳에 설정한 이유

| 설정 위치 | 적용 시점 |
|---|---|
| `~/.zshrc` 환경변수 | 셸에서 `claude`를 실행할 때 프로세스 환경으로 전달됨 |
| `settings.json` env | Claude Code가 시작한 뒤 설정을 읽어 자기 프로세스와 하위 프로세스(Bash 도구, stdio MCP 서버)에 적용 |

`NODE_EXTRA_CA_CERTS`는 원래 런타임이 프로세스를 시작할 때 한 번만 읽는 변수다. Node.js 문서도 실행 중에 `process.env`로 값을 바꾸면 현재 프로세스에는 효과가 없다고 명시한다. 그래서 Claude Code 본체 프로세스(OAuth 인증 플로우 포함)에 확실히 적용되도록 셸 환경에 넣었고, Claude Code가 띄우는 하위 프로세스에도 같은 값이 가도록 `settings.json`에도 넣었다.

> 2026년 10월 기준 Claude Code 문서는 `settings.json`의 `env`가 Claude Code 본체에도 적용된다고 안내한다. 따라서 현재 버전에서는 `settings.json` 한 곳만 설정해도 된다. 또 Notion MCP는 HTTP transport라 하위 프로세스를 띄우지 않으므로, 하위 프로세스 쪽 설정은 stdio로 띄우는 Node.js 기반 MCP 서버가 있을 때 의미가 있다.

## 3단계: Notion MCP 재설정

```bash
# 기존 설정 제거 후 재등록
claude mcp remove notion -s user
claude mcp add --transport http notion https://mcp.notion.com/mcp -s user
```

재설정하면 OAuth 인증부터 다시 진행되며, 이때 `NODE_EXTRA_CA_CERTS`로 주입된 회사 CA가 적용되어 TLS 검증이 통과한다.

## Claude Code 2.1.101 이후

이 트러블슈팅 직후에 나온 Claude Code 2.1.101(2026년 4월 10일)부터는 내장 CA bundle과 함께 **OS 인증서 저장소도 기본으로 신뢰**한다. 신뢰 소스는 `CLAUDE_CODE_CERT_STORE` 환경변수로 고르고, 기본값은 `bundled,system`이다. macOS에서는 키체인이 OS 인증서 저장소이므로, 키체인에 회사 CA가 "항상 신뢰"로 등록된 환경이라면 문서 기준으로는 `NODE_EXTRA_CA_CERTS` 없이도 Notion MCP가 동작한다. 이 경우 Claude Code의 trust 소스는 아래 정리 표의 브라우저 행과 같아진다.

`NODE_EXTRA_CA_CERTS`는 여전히 지원된다. OS 저장소에 넣기 어려운 CA를 따로 줘야 할 때나, OS 저장소를 끄고(`CLAUDE_CODE_CERT_STORE=bundled`) 쓸 때 의미가 있다. 2026년 10월 기준 Claude Code 문서와 changelog로 확인했다.

<br>

# 정리

두 차례의 트러블슈팅을 거치면서 결국 핵심은 **도구마다 trust 모델이 다르다**는 것이었다.

| 도구 | trust 소스 | OS 키체인 참조 | 회사 CA를 trust에 넣으면? |
|---|---|---|---|
| kubectl | kubeconfig `certificate-authority-data` | X | 하면 안 됨 (cluster 검증 포기) |
| Node.js (Notion MCP) | 내장 CA bundle (Mozilla) | X (기본값 기준) | **해야 풀림** (`NODE_EXTRA_CA_CERTS`) |
| 브라우저 (Safari/Chrome) | OS 시스템 trust store | O | 이미 되어 있어서 자물쇠 정상 |
| Python (`mcp-atlassian`의 `truststore`) | OS 시스템 trust store | O | 이미 되어 있어서 Jira MCP 정상 |

`kubectl`과 Node.js는 기본값 기준으로 **둘 다 OS 키체인을 무시**하지만, trust 소스의 성격이 달라서 해법이 정반대가 된다.

- **kubectl**: trust 소스가 **폐쇄 PKI**(cluster CA pinning)다. 회사 CA를 넣으면 "진짜 우리 cluster의 API 서버인가" 라는 검증 자체가 무의미해지므로 넣으면 안 된다. 해법은 SSL Inspection 경로를 회피하거나 bypass를 요청하는 것이다.
- **Node.js**: trust 소스가 **공개 PKI**(범용 CA bundle)다. 원래 DigiCert 같은 공인 CA를 신뢰하는 구조이므로, 회사 CA를 추가해 주면 "회사 방화벽이 재서명한 인증서도 공인 인증서와 같은 수준으로 신뢰한다"는 의미가 되고, 이것이 정확히 원하는 동작이다. `NODE_EXTRA_CA_CERTS`가 Node.js의 대표적인 해법이고, 최근 런타임에는 OS 저장소를 쓰게 하는 옵션(`--use-system-ca`)도 있다.

같은 "SSL Inspection으로 인증서가 바뀌었다"는 현상이지만, **클라이언트가 무엇을 신뢰하고 있느냐**에 따라 대응이 완전히 달라진다. VPN/프록시 환경에서 TLS 관련 에러를 만나면, 에러 메시지보다 먼저 **해당 도구가 어떤 trust 소스를 사용하는지**를 파악하는 것이 가장 빠른 진단 경로다.

이번 트러블슈팅에서 가장 헷갈렸던 건, macOS 키체인에 회사 CA가 "항상 신뢰"로 등록되어 있어서 브라우저에서는 모든 게 정상으로 보였다는 점이다. 같은 머신에서 브라우저는 되는데 CLI 도구만 안 되면, 도구 자체의 버그나 설정 실수를 먼저 의심하게 된다. 그게 아니라 **trust 소스가 다르다**는 걸 떠올리기까지가 돌아가는 길이었다.

잘 되던 도구가 네트워크 환경을 바꾼 직후 `self signed certificate in certificate chain`을 뱉기 시작했다면, VPN/프록시 경로 변화를 먼저 의심하자. 그리고 Node.js 기반 도구라면 `NODE_EXTRA_CA_CERTS`가 해법이다. 다만 회사 VPN 정책이 바뀌면 PEM 파일도 갱신해야 하므로, 어느 날 갑자기 다시 깨지면 인증서 파일 날짜부터 확인해 보자. 도구가 OS 저장소를 직접 읽을 수 있다면(`--use-system-ca`, Claude Code 2.1.101 이후의 기본 동작) 이런 갱신 부담은 없다.

<br>
