---
title:  "[TLS] SNI와 SAN: 개념, 차이, 그리고 인증서 디버깅 팁"
excerpt: "TLS handshake에서 SNI와 SAN이 각각 어떤 역할을 하는지, 그리고 openssl s_client로 인증서를 디버깅할 때 servername을 신경써야 하는 이유에 대해 알아 보자."
categories:
  - CS
toc: true
header:
  teaser: /assets/images/blog-Dev.jpg
tags:
  - TLS
  - SNI
  - SAN
  - X.509
  - certificate
  - openssl
  - debugging
  - kube-apiserver
---

[VPN SSL Inspection 트러블슈팅]({% post_url 2026-04-23-Dev-Kubectl-VPN-SSL-Inspection %})에서 `openssl s_client`로 서버 인증서를 확인하던 중, `-servername`(SNI)을 지정하는 것이 좋다는 팁을 발견하고 공부한 내용을 정리한다.

<br>

# TL;DR

- **SNI**(Server Name Indication)는 클라이언트가 TLS handshake 시 서버에 보내는 힌트(ClientHello에 평문으로 포함)
- **SAN**(Subject Alternative Name)은 인증서에 박혀 있는 필드로, 해당 인증서가 유효한 이름/IP 목록
- SNI는 **서버가 어떤 인증서를 줄지** 결정하는 데 쓰이고, SAN은 **클라이언트가 받은 인증서를 검증**하는 데 쓰인다
- `openssl s_client`로 디버깅할 때는 `-servername`을 실제 접속 대상(kubeconfig의 `server` 주소 등)과 맞춰야 정확한 인증서를 확인할 수 있다
- 다만, kube-apiserver는 기본적으로 단일 서빙 인증서만 사용하므로 SNI에 민감하지 않다. 멀티 인증서 환경(NGINX Ingress, ALB, Envoy 등)에서 더 중요한 개념이다

<br>

# SNI vs SAN

한 줄로 요약하면, **SNI는 클라이언트가 보낼 때 쓰는 이름**이고 **SAN은 클라이언트가 받은 뒤 검증할 때 쓰는 이름**이다.

## SNI (Server Name Indication)

TLS handshake의 ClientHello 단계에서, 클라이언트가 서버에 "나 이 이름으로 연결하려고 하는데?"하는 힌트를 보내는 것이다.

- ClientHello 패킷에 **평문**으로 들어간다
- 방향: 클라이언트 → 서버
- 원래 목적: 한 IP에 여러 TLS 사이트(virtual host)가 있을 때, 서버가 올바른 인증서를 골라 응답하기 위함

SNI의 기본 개념은 [TLS/SSL 프로토콜 글]({% post_url 2026-01-05-CS-Security-TLS-SSL %})의 "SNI" 절에서 다룬 바 있다. 이 글에서는 디버깅 관점에서 더 깊이 들어간다.

## SAN (Subject Alternative Name)

인증서 내부에 박혀 있는 필드로, "이 인증서는 다음 이름들/IP들에 대해 유효하다"는 목록이다.

- 서버가 가진 인증서의 속성이지, 어딘가로 전송되는 값이 아니다
- DNS 이름(`DNS:example.com`)과 IP 주소(`IP:10.0.0.1`) 두 종류가 들어갈 수 있다
- 현재 표준에서는 CN(Common Name)보다 SAN을 우선 참조한다. 최신 브라우저와 Go는 CN을 아예 무시한다

SAN 필드의 구조에 대한 상세 설명은 [X.509 인증서 글]({% post_url 2026-01-04-CS-Security-X509-Certificate %})을 참고하자.

## 전체 흐름

SNI와 SAN이 TLS handshake에서 어떻게 맞물리는지 단계별로 보자.

1. 클라이언트 → 서버: ClientHello + SNI="api.example.com"
2. 서버: SNI를 보고 적절한 인증서 선택 (또는 default)
3. 서버 → 클라이언트: ServerHello + Certificate (선택된 인증서)
4. 클라이언트: 받은 인증서의 SAN에 "내가 접속하려던 이름/IP"가 있는지 검증

**1단계**에서 클라이언트가 SNI를 보내면, **2단계**에서 서버가 그걸 보고 인증서를 고른다. **3단계**에서 인증서가 내려오면, **4단계**에서 클라이언트가 SAN을 검증한다. 즉 SNI는 서버 측의 인증서 선택에 영향을 주고, SAN 검증은 클라이언트 측에서 독립적으로 수행된다.

<br>

# 서버 측: SNI 매칭과 default 인증서

## SNI 매칭 성공

서버가 여러 인증서를 가지고 있을 때, 클라이언트가 보낸 SNI 값에 매칭되는 인증서를 골라 반환한다. 가장 단순하고 정상적인 경우다.

## SNI 매칭 실패 시

SNI가 비어 있거나, 서버가 가진 어떤 인증서와도 매칭되지 않으면, 서버 구현에 따라 두 갈래로 갈린다.

### default 인증서를 내려주는 경우

대부분의 서버 구현이 이 방식이다. 매칭 실패 시 미리 지정된 기본 인증서(default cert)를 내려준다.

| 구현체 | default 인증서 결정 방식 |
|---|---|
| NGINX / NGINX Ingress | `--default-ssl-certificate` 또는 `default_server` 블록의 cert |
| HAProxy | `bind ... ssl crt-list ...`의 첫 번째 cert |
| Envoy | `filter_chain_match` 없는 fallback filter chain의 cert |
| Apache httpd | 첫 번째 VirtualHost의 cert |
| AWS ALB | 리스너 생성 시 지정하는 default certificate |
| Go `crypto/tls` | `Config.Certificates[0]` 또는 `GetCertificate(nil)` 반환값 |

### TLS 에러로 끊는 경우

default cert가 설정되어 있지 않거나, 명시적으로 거부하도록 설정한 경우다.

- Envoy, 최신 NGINX(`ssl_reject_handshake on;`): `unrecognized_name`(TLS alert 112) 또는 `handshake_failure` alert를 보내고 세션을 종료한다
- 일부 구현: SNI 매칭 실패 시 TCP RST로 끊어 버린다

> `unrecognized_name` alert는 SNI로 도달은 했지만 매칭에 실패했을 때 서버가 보낼 수 있는 표준 alert다. warning 레벨이면 연결은 계속 진행(default cert)되고, fatal 레벨이면 끊긴다.

클라이언트 쪽에서는 `OpenSSL SSL_connect: SSL_ERROR_SYSCALL` 또는 `tlsv1 alert unrecognized name` 같은 에러가 뜬다

<br>

# 클라이언트 측: SAN 검증

## 검증 타이밍

서버 측의 SNI 처리와 달리, SAN 검증은 **인증서를 받은 뒤 클라이언트가 로컬에서** 수행한다. 전체 흐름 안에서의 위치를 보면 다음과 같다. 1번은 TCP handshake(전송 계층)이고, 2~5번이 그 위에서 이루어지는 TLS handshake(보안 계층)다.

1. TCP 3-way handshake: SYN → SYN-ACK → ACK → TCP 연결 수립 (전송 계층)
2. ClientHello (SNI 포함) 전송 ← 여기서부터 TLS handshake
3. ServerHello + Certificate (서버가 cert를 내려줌)
4. 클라이언트가 받은 cert를 검증:
   - Chain 검증: CA 신뢰 체인이 유효한가? → 실패 시 "unknown authority"
   - 이름 검증 (hostname verification): 접속 대상이 cert의 SAN에 있는가? → 실패 시 "cannot validate certificate"
   - 기타: 유효기간, revocation 등
5. 전부 통과 → Finished 메시지 교환 → 애플리케이션 데이터 전송 시작

검증 실패 시 TLS handshake 자체는 끝까지 간다. 클라이언트가 인증서를 받고 나서 "검증 실패"로 세션을 끊는 구조다. "접속 안 하는" 게 아니라 "handshake는 갔다가 클라이언트가 끊는" 것이다.

CA 체인 검증과 신뢰 구조에 대한 상세 내용은 [PKI 글]({% post_url 2026-01-18-CS-PKI %})을 참고하자.

## 이름 검증의 기준: SNI 값이 아니다

흔한 오해 중 하나가 "SNI에 넣은 값으로 SAN 검증을 한다"는 것이다. 체감상 그렇게 보이지만, **엄밀히는 별개**다.

이름 검증에서 "내가 접속하려던 호스트/IP"란, 애플리케이션이 TLS 라이브러리에 지정한 `ServerName` 값이다. 보통 URL의 호스트 부분이 된다.

- `curl https://api.example.com/` → 검증 기준은 `api.example.com`
- `kubectl`의 kubeconfig `server: https://10.50.31.212:6443` → 검증 기준은 `10.50.31.212` (IP)

이 값이 SNI로도 같이 나가기 때문에 체감상 SNI에 넣은 값으로 검증하는 것처럼 보이지만, 프로토콜 상으로는 SNI 전송과 SAN 검증은 독립된 단계다.

## 검증 규칙

검증 규칙은 접속 대상의 형태에 따라 다르고, 관련 RFC도 다르다.

- **도메인명으로 접속** (`https://api.example.com`): cert SAN의 `DNS:` 항목과 비교한다. 와일드카드 매칭(`*.example.com`)도 지원된다. CN은 최신 브라우저/Go에서 **무시**한다. [RFC 6125](https://datatracker.ietf.org/doc/html/rfc6125)가 이 규칙을 체계화하면서 CN 사용을 공식적으로 폐기(deprecate)했다
- **IP literal로 접속** (`https://10.50.31.212`): cert SAN의 `IP:` 항목과**만** 비교한다. `DNS:` 항목은 보지 않는다. RFC 6125는 IP 주소를 명시적으로 범위 밖으로 두고 있어, 이 경우에는 [RFC 2818](https://datatracker.ietf.org/doc/html/rfc2818)(HTTP Over TLS)의 규칙이 여전히 적용된다

> RFC 2818은 HTTPS 인증서 검증의 원조 규격으로 도메인명과 IP 매칭을 둘 다 다루지만, 도메인명 검증 부분은 RFC 6125가 사실상 대체했다. IP literal 검증은 RFC 6125이 다루지 않으므로 RFC 2818이 현역이다.

## 실패 시 에러 메시지

SAN 검증 실패 시 환경별로 보이는 에러 메시지는 다음과 같다.

| 환경 | 에러 메시지 |
|---|---|
| Go (kubectl 등) | `x509: cannot validate certificate for 10.50.31.212 because it doesn't contain any IP SANs` |
| curl | `SSL: no alternative certificate subject name matches target host name 'api.example.com'` |
| 브라우저 | `NET::ERR_CERT_COMMON_NAME_INVALID` / "이 사이트의 보안 연결에 문제가 있습니다" |
| Java | `java.security.cert.CertificateException: No subject alternative names matching IP address 10.50.31.212 found` |

## 요약

- **SNI 매칭은 서버 쪽 일**: 실패 시 default cert를 주거나 alert로 끊는다
- **SAN 검증은 클라이언트 쪽 일**: 실패 시 handshake 후 로컬에서 에러를 내고 연결을 종료한다. TCP 레벨 RST나 TLS alert로 종료되며, 애플리케이션은 "certificate invalid" 에러를 받는다

<br>

# kube-apiserver에서의 SNI

## 단일 서빙 인증서 구조

kube-apiserver는 기본적으로 **단일 서빙 인증서 하나**만 들고 있다. 그 인증서의 SAN에 다음과 같은 이름/IP가 한꺼번에 박혀 있는 구조다.

- `kubernetes`, `kubernetes.default`, `kubernetes.default.svc`, `kubernetes.default.svc.cluster.local`
- 컨트롤플레인 노드의 호스트명
- default `kubernetes` 서비스 ClusterIP (예: `10.43.0.1`), 각 노드 IP
- RKE2의 경우 설치 시 `tls-san`으로 추가한 값들

kube-apiserver의 인증서 구조에 대해서는 [Kubernetes PKI 글]({% post_url 2026-01-18-Kubernetes-PKI %})에서 자세히 다룬 바 있다.

## SNI가 영향을 미치지 않는 이유

인증서가 여러 개인 구조가 아니므로, SNI가 비어 있든(`""`), `10.50.31.212`든, `kubernetes`든, 엉뚱한 `foo.bar`든 **응답으로 내려오는 인증서는 동일**하다.

`--tls-sni-cert-key` 플래그로 SNI별 다중 바인딩을 **명시적으로** 구성하지 않는 한, kube-apiserver는 항상 같은 인증서를 내려준다. RKE2나 kubeadm 기본 설치는 `--tls-sni-cert-key`를 쓰지 않고 `--tls-cert-file` 하나로만 세팅하므로, 사내에서 누군가 일부러 멀티 cert 구성을 하지 않았다면 SNI 걱정은 실질적으로 불필요하다.

[VPN SSL Inspection 트러블슈팅]({% post_url 2026-04-23-Dev-Kubectl-VPN-SSL-Inspection %})에서 `-servername` 없이 진단할 수 있었던 것도 이 때문이다. SSL Inspection 환경에서의 구체적인 영향은 [아래 디버깅 영향](#ssl-inspection-환경에서의-sni)에서 다시 짚는다.

## 만약 다중 바인딩이 설정되어 있다면

드문 경우지만, 누군가 `--tls-sni-cert-key`를 설정해 놓았다면 SNI에 따라 다른 인증서가 내려올 수 있다.

```yaml
# kube-apiserver 플래그 예시
--tls-cert-file=apiserver.crt                          # default
--tls-sni-cert-key=kubernetes.crt,kubernetes.key:kubernetes,kubernetes.default
```

이 구성에서는 SNI=`kubernetes`로 붙으면 `kubernetes.crt`를 주고, SNI 없이 IP로 붙으면 `apiserver.crt`(default)가 내려온다. 두 인증서의 CA는 같아도 SAN 구성이 다를 수 있으므로, `kubectl`이 kubeconfig의 `server: https://10.50.31.212:6443` 기준으로 IP SAN 검증을 하는데 default cert의 SAN에 그 IP가 없으면 `x509: cannot validate certificate for 10.50.31.212` 에러가 발생한다.

<br>

# openssl s_client의 SNI 동작

앞서 kube-apiserver는 단일 인증서 구조라 SNI에 민감하지 않다고 했다. 그렇다면 `openssl s_client`는 SNI를 어떻게 처리하길래, [트러블슈팅]({% post_url 2026-04-23-Dev-Kubectl-VPN-SSL-Inspection %})에서 `-servername` 없이도 문제가 없었을까?

`openssl s_client`는 `-servername`을 명시하지 않더라도 `-connect`의 호스트 부분을 기본 SNI로 **자동 세팅**한다. 단, IP로 접속하면 RFC 6066 권고에 따라 SNI가 빈 상태가 된다.

```bash
# IP로 접속 → SNI가 비어서 나감
openssl s_client -connect 10.50.31.212:6443

# 호스트명으로 접속 → SNI에 "kubernetes" 자동 세팅
openssl s_client -connect kubernetes:6443
```

kube-apiserver는 단일 인증서 구조이므로 어느 쪽이든 같은 인증서를 준다. 그러나 반복적으로 강조하듯 멀티 인증서 환경에서는 이 차이가 전혀 다른 인증서를 가져오는 결과로 이어질 수 있다.

원칙은 **kubeconfig `server:` 에 들어 있는 값과 동일하게 맞추는 것**이다.

```bash
# 1. kubeconfig가 IP 기반인 경우 (server: https://10.50.31.212:6443)
#     → SNI를 비워서 kubectl과 동일한 조건으로 확인
openssl s_client -connect 10.50.31.212:6443 -servername "" 2>/dev/null \
  | openssl x509 -noout -issuer -subject

# 2. kubeconfig가 호스트명 기반이거나, 정식 인증서를 확인하고 싶은 경우
#     → -servername에 해당 호스트명 지정
openssl s_client -connect 10.50.31.212:6443 -servername kubernetes 2>/dev/null \
  | openssl x509 -noout -issuer -subject
```

<br>

# 실무 디버깅 팁

## SNI/default 인증서를 의심해야 하는 증상

아래 증상이 나타나면 SNI 미지정 또는 default 인증서가 문제일 가능성이 있다.

1. `openssl s_client -connect IP:PORT`로는 Subject가 이상한데, `-servername 호스트명`을 붙이면 정상 Subject가 나오는 경우
2. kubectl이 `certificate signed by unknown authority`가 아니라 `cannot validate certificate for X because it doesn't contain any IP SANs / DNS names`를 뱉는 경우
3. kubeconfig의 `clusters[].cluster.server`를 IP에서 호스트명으로 바꿨더니 에러가 달라지는 경우

## 디버깅 패턴: SNI 비교

핵심은 **"실제로 접속하려던 이름을 `-servername`에 넣기"**와 **"그걸 뺐을 때 뭐가 나오는지 비교하기"** 두 가지다. 이 둘의 차이가 default cert 문제인지 아닌지를 가른다.

### NGINX Ingress 예시

NGINX Ingress Controller에 `api.example.com`, `app.example.com` 두 Ingress가 붙어 있고, `--default-ssl-certificate`로 self-signed default가 설정된 환경을 가정하자.

```bash
INGRESS_IP=10.0.0.50

# 1. SNI 없이 → default cert 확인
openssl s_client -connect $INGRESS_IP:443 -servername "" 2>/dev/null \
  | openssl x509 -noout -subject -issuer
# subject=CN=ingress-default   ← default SSL cert (self-signed)

# 2. 문제 도메인 SNI로 → 정상이면 Let's Encrypt cert가 나와야 함
openssl s_client -connect $INGRESS_IP:443 -servername api.example.com 2>/dev/null \
  | openssl x509 -noout -subject -issuer -ext subjectAltName
# subject=CN=api.example.com
# issuer=C=US, O=Let's Encrypt, CN=R3
# X509v3 Subject Alternative Name: DNS:api.example.com

# 3. 다른 도메인 SNI로 → 해당 Ingress의 cert 확인
openssl s_client -connect $INGRESS_IP:443 -servername app.example.com 2>/dev/null \
  | openssl x509 -noout -subject
```

이 비교를 통해 진단할 수 있는 것들:

- `-servername api.example.com`을 줬는데 default cert가 내려온다 → **해당 Ingress의 TLS secret이 안 붙어 있거나, secret 이름 오타이거나, cert-manager 발급 실패**
- 받은 cert의 SAN에 `api.example.com`이 없다 → **cert-manager가 잘못된 도메인으로 발급**했거나 **와일드카드 범위 밖**
- 정상 cert가 나오는데 브라우저만 안 된다 → **클라이언트 쪽 신뢰 문제** (루트 CA 미설치, 체인 누락)

### 다른 환경에서도 동일한 패턴

- **AWS ALB**: `-servername your-domain.com` vs `-servername ""` → SNI 없으면 ALB가 default action certificate를 내려준다
- **Envoy**: 리스너에 여러 `filter_chain_match.server_names`가 있을 때, 해당 SNI로 비교한다
- **CloudFront**: SNI를 잘못 주면 완전히 다른 distribution cert가 내려올 수 있다

## SSL Inspection 환경에서의 SNI

[VPN SSL Inspection 글]({% post_url 2026-04-23-Dev-Kubectl-VPN-SSL-Inspection %})에서 다뤘던 상황을 이 관점에서 다시 보자.

방화벽이 SSL Inspection을 수행하는 환경에서, default 인증서를 주는 주체가 방화벽/프록시(SSL Inspection 장비)인 경우를 생각해 보면:

- 방화벽이 SNI/도착지에 따라 재서명 인증서의 Subject를 만들어 주는데, SNI가 비어 있거나 매칭되지 않으면 플레이스홀더성 Subject로 재서명할 수 있다
- kubectl 입장에서는 Issuer 불일치(`x509: certificate signed by unknown authority`)와 Hostname/IP SAN 불일치(`x509: cannot validate certificate for 10.50.31.212 because it doesn't contain any IP SANs`)가 겹칠 수 있다
- 에러 메시지가 평소와 다르게 나올 때, SNI 미지정으로 인한 default cert 문제인지 아닌지를 구분하려면 `-servername`을 붙여서 비교해 보는 것이 유효하다

해당 트러블슈팅에서는 방화벽 재서명이 원인이었고, SNI 없이 뽑아낸 Issuer 값만으로도 원인 판정이 충분히 성립했다. 다만, default 인증서를 받게 되면 Issuer 불일치 외에 호스트/IP SAN 불일치까지 겹쳐서 에러 메시지가 달라질 수 있으므로, 그때 진단을 헷갈리지 않으려면 `-servername`을 붙이는 것이 안전한 습관이다.

<br>

# 정리

SNI와 SAN은 이름이 비슷하고 TLS handshake라는 같은 맥락에서 등장하지만, 역할과 담당 주체가 다르다.

| 항목 | SNI | SAN |
|---|---|---|
| 정체 | ClientHello의 확장 필드 | 인증서 내부 필드 |
| 방향 | 클라이언트 → 서버 | 인증서 속성 (전송되는 값 아님) |
| 역할 | 서버가 인증서를 **선택**하는 힌트 | 클라이언트가 인증서를 **검증**하는 기준 |
| 실패 시 | 서버가 default cert를 주거나 끊음 | 클라이언트가 handshake 후 연결을 끊음 |

`openssl s_client`로 인증서를 디버깅할 때는, **접속 대상과 동일한 SNI를 `-servername`으로 넣는 것**을 습관으로 들이자. kube-apiserver처럼 단일 인증서 환경에서는 실질적 차이가 없지만, NGINX Ingress나 ALB 같은 멀티 인증서 환경에서는 SNI 하나 차이로 전혀 다른 인증서가 내려올 수 있다.

<br>
