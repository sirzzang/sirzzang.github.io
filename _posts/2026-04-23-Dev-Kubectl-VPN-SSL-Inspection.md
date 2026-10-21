---
title:  "[Kubernetes] VPN SSL Inspection으로 인한 클러스터 API 접근 실패"
excerpt: "VPN 환경에서 회사 방화벽이 kube-apiserver TLS를 가로채 재서명하며 발생한 인증서 검증 실패에 대해 알아 보자."
permalink: /dev/Dev-Kubectl-VPN-SSL-Inspection/
categories:
  - k8s-auth
  - cs-security
  - troubleshooting
toc: true
header:
  teaser: /assets/images/blog-Dev.jpg
tags:
  - kubectl
  - kubernetes
  - TLS
  - PKI
  - certificate
  - VPN
  - SSL-Inspection
  - MITM
  - RKE2
last_modified_at: 2026-10-21
---

<br>

# 배경

회사에서는 멀쩡하게 잘 쓰던 `kubectl`이, 재택 근무 중 회사 VPN을 연결한 상태에서는 자꾸 깨졌다. 사내 RKE2 클러스터의 `kube-apiserver`로 어떤 명령을 보내도 모두 TLS 인증서 검증 단계에서 막혀 버렸다. kubeconfig를 새로 받아도, 같은 명령을 사무실에서 그대로 실행하면 되는데, VPN으로 접속하면 또 깨진다.

참고로 사용 중인 kubeconfig는 RKE2 bootstrap 노드의 admin 인증서(`/etc/rancher/rke2/rke2.yaml`)를 로컬로 그대로 복사한 것이다.

```bash
$ scp bootstrap:/etc/rancher/rke2/rke2.yaml ~/.kube/config
```

> 사실 위에서 복사한 파일은 `system:masters` 그룹(= cluster-admin 권한)에 매핑되는 강한 자격증명이다. 이로 인해 야기될 수 있는 문제점은 [뒤쪽 우회 방법](#insecure-skip-tls-verify-임시-한정)에서 다시 짚는다.

[이전에도 kubeconfig 인증서 문제로 kubectl이 깨진 경험]({% post_url 2026-01-10-Dev-Kubernetes-Certificate-Trouble-Shooting %})이 있다. 그때는 **클라이언트 인증서 만료**(mTLS에서 서버가 클라이언트를 검증하는 단계 실패)였다면, 이번에는 **서버 인증서 trust chain 불일치**(클라이언트가 서버를 검증하는 단계 실패)다. 같은 mTLS handshake의 다른 실패 지점이지만, 원인의 성격은 꽤 다르다. 인증서 자체의 시간 경과가 아니라, 네트워크 경로 위의 외부 개입이 문제였다.

처음에는 "VPN이 뭔가 이상한가" 정도로 단순하게 생각했지만, 실제로 받은 서버 인증서를 까 보니 **원래 cluster CA가 아니라 회사 방화벽 CA가 서명한 인증서**가 돌아오고 있었다. 회사 VPN 경로에 있는 방화벽이 SSL Inspection으로 `kube-apiserver` TLS 트래픽까지 가로채서 자체 CA로 재서명하고 있었던 것이다.

이 글에서는 같은 상황을 만났을 때 도움이 될 수 있도록, 문제 분석 과정과 SSL Inspection 동작 원리, 그리고 우회 방법을 정리해 본다.

<br>

# TL;DR

1. 증상
   - 재택 VPN 환경에서만 `kubectl` 명령이 `tls: failed to verify certificate: x509: certificate signed by unknown authority` 에러로 실패
   - 회사 내부 네트워크에서는 정상 동작

2. 원인
   - 회사 VPN 경로의 방화벽이 SSL Inspection을 수행 → `kube-apiserver`로 가는 TLS 트래픽을 MITM(Man-in-the-Middle) 가로채기
   - 방화벽이 자체 CA(`ExampleCorp_Untrust_ECDSA`)로 새 서버 인증서를 즉석 발급해 `kubectl`에 전달
   - kubeconfig에 박힌 CA(`rke2-server-ca`)와 issuer가 달라서 검증 실패

3. 해결
   - 임시: bootstrap 노드에 SSH로 접속해서 작업 (인증서 문제 자체를 회피)
   - 임시: `kubectl --insecure-skip-tls-verify get nodes`처럼 일회성 플래그로 검증 생략 (보안 위험 인지 후 잠깐만. `kubectl config set-cluster`로 켜면 kubeconfig의 CA가 지워진다)
   - 근본: 인프라/네트워크팀에 해당 IP:포트의 SSL Inspection bypass(권장) 또는 VPN 라우팅 분기 적용을 요청

<br>

# 문제

VPN 접속 후 `kubectl get nodes`를 실행하면, 동일한 에러가 반복된다.

```bash
$ kubectl get nodes
E0422 10:43:34.193393   86062 memcache.go:265] "Unhandled Error" err="couldn't get current server API group list: Get \"https://10.50.31.10:6443/api?timeout=32s\": tls: failed to verify certificate: x509: certificate signed by unknown authority"
Unable to connect to the server: tls: failed to verify certificate: x509: certificate signed by unknown authority
```

<details markdown="1">
<summary><b>전체 에러 로그</b></summary>

```bash
$ kubectl get nodes
E0422 10:43:34.193393   86062 memcache.go:265] "Unhandled Error" err="couldn't get current server API group list: Get \"https://10.50.31.10:6443/api?timeout=32s\": tls: failed to verify certificate: x509: certificate signed by unknown authority"
E0422 10:43:34.270515   86062 memcache.go:265] "Unhandled Error" err="couldn't get current server API group list: Get \"https://10.50.31.10:6443/api?timeout=32s\": tls: failed to verify certificate: x509: certificate signed by unknown authority"
E0422 10:43:34.338637   86062 memcache.go:265] "Unhandled Error" err="couldn't get current server API group list: Get \"https://10.50.31.10:6443/api?timeout=32s\": tls: failed to verify certificate: x509: certificate signed by unknown authority"
E0422 10:43:34.401360   86062 memcache.go:265] "Unhandled Error" err="couldn't get current server API group list: Get \"https://10.50.31.10:6443/api?timeout=32s\": tls: failed to verify certificate: x509: certificate signed by unknown authority"
E0422 10:43:34.473238   86062 memcache.go:265] "Unhandled Error" err="couldn't get current server API group list: Get \"https://10.50.31.10:6443/api?timeout=32s\": tls: failed to verify certificate: x509: certificate signed by unknown authority"
Unable to connect to the server: tls: failed to verify certificate: x509: certificate signed by unknown authority
```

</details>

흥미로운 점은 **환경에 따라 결과가 달라진다**는 것이다.

| 접속 환경 | 결과 |
|---|---|
| 회사 사무실 (사내망 직접 연결) | 정상 동작 |
| 재택 + 회사 VPN | TLS 검증 실패 |
| VPN 끄고 외부망 (공유기) | 애초에 사설 IP로 라우팅 안 됨 |

사용하는 `kubectl` 바이너리도 같고, kubeconfig 파일도 같다. 바뀐 건 **네트워크 경로**뿐이다. 그렇다면 경로 위에 있는 무언가가 인증서를 바꿔치기하고 있다는 의미가 된다.

## kubeconfig는 무엇을 검증하는가

이 동작을 이해하려면 kubeconfig가 TLS 검증에서 어떤 역할을 하는지 떠올려 둘 필요가 있다. kubeconfig의 `clusters[].cluster.certificate-authority-data` 필드는 "이 cluster의 API 서버 인증서를 서명한 CA"를 base64로 담고 있다. `kubectl`은 API 서버에 연결할 때 받은 서버 인증서가 이 CA가 서명한 것인지를 확인한다.

```yaml
apiVersion: v1
clusters:
- cluster:
    certificate-authority-data: DATA+OMITTED   # 이 CA가 서명한 서버 인증서만 신뢰
    server: https://10.50.31.10:6443
  name: default
contexts:
- context:
    cluster: default
    namespace: default
    user: default
  name: example-mlops
current-context: example-mlops
kind: Config
users:
- name: default
  user:
    client-certificate-data: DATA+OMITTED      # kubectl 신원 증명용 (mTLS의 client 측)
    client-key-data: DATA+OMITTED
```

kubeconfig의 전체 구조와 각 필드의 의미는 [kubeconfig 개요 글]({% post_url 2026-02-16-Kubernetes-Kubeconfig-01 %})에서 자세히 다룬 적이 있어 여기서는 생략한다. 핵심은 **`certificate-authority-data`가 cluster 전용 trust anchor**라는 점이다. 이 필드에 등록된 CA가 서명한 인증서만 진짜 API 서버로 인정한다.

그렇다면 받은 서버 인증서가 실제로 어느 CA가 서명한 것인지 확인해 보면 된다.

<br>

# 원인 분석

## 받은 서버 인증서 직접 확인

`openssl s_client`는 OpenSSL이 제공하는 진단용 TLS 클라이언트다. 지정한 `호스트:포트`로 직접 TLS handshake를 수행하고, 그 과정에서 서버가 보내 준 인증서 체인을 그대로 출력해 준다. 즉, **`kubectl`이 보고 있는 것과 동일한 서버 인증서**를 사람이 읽을 수 있는 형태로 꺼내 볼 수 있다.

```bash
# kube-apiserver가 보내 주는 서버 인증서의 issuer/subject 확인
$ echo | openssl s_client -connect 10.50.31.10:6443 2>/dev/null \
    | openssl x509 -noout -issuer -subject

issuer=CN=ExampleCorp_Untrust_ECDSA
subject=CN=kube-apiserver
```

> `openssl s_client`에서 `-servername`(SNI)을 지정하지 않으면, 서버가 default 인증서를 내려줄 수 있다. kube-apiserver는 단일 서빙 인증서 구조라서 이번 경우에는 영향이 없었지만, NGINX Ingress나 ALB처럼 멀티 인증서 환경에서는 SNI 하나 차이로 전혀 다른 인증서가 나올 수 있다. 정확한 진단을 위해 `-servername`을 kubeconfig의 `server` 주소와 맞추는 습관이 좋다. SNI와 SAN의 차이, 디버깅 시 `-servername` 활용법에 대해서는 [SNI와 SAN 글]({% post_url 2026-04-25-CS-TLS-SNI-SAN %})에서 자세히 다룬다.

여기서 `subject`는 인증서가 누구에게 발급된 것인지(누구의 신원을 증명하는지), `issuer`는 그 인증서를 누가 서명했는지를 나타낸다. mTLS handshake 단계와 인증서의 역할에 대한 자세한 설명은 [Kubernetes PKI 글]({% post_url 2026-01-18-Kubernetes-PKI %})을 참고하자.

서버 인증서의 subject가 `CN=kube-apiserver`인 것은 정상이다. 그런데 issuer가 `CN=ExampleCorp_Untrust_ECDSA` → 처음 보는 이름이다. RKE2가 만든 cluster CA가 아니다.

## kubeconfig에 박힌 CA와 비교

비교를 위해 kubeconfig가 신뢰하도록 박혀 있는 CA의 subject를 확인해 본다.

```bash
# kubeconfig에 등록된 CA의 subject 확인
$ kubectl config view --raw -o json \
    | jq -r '.clusters[].cluster."certificate-authority-data"' \
    | base64 -d \
    | openssl x509 -noout -subject

subject=CN=rke2-server-ca@1770348093
```

## Issuer 불일치 확인

정리하면 다음과 같은 불일치가 발생한 상태다.

| 항목 | 값 |
|---|---|
| 받은 서버 인증서의 issuer | `CN=ExampleCorp_Untrust_ECDSA` (회사 방화벽 CA) |
| kubeconfig가 신뢰하는 CA의 subject | `CN=rke2-server-ca@1770348093` (RKE2 cluster CA) |

`kubectl` 입장에서는 받은 서버 인증서가 **신뢰 목록에 없는 CA가 서명한 것**이므로 검증을 실패시키는 것이 정상 동작이다. 에러 메시지 `x509: certificate signed by unknown authority`는 정확히 이 상태를 가리킨다.

문제는 "왜 회사 내부망에서는 멀쩡한 cluster CA가 서명한 인증서가 오다가, VPN 경로에서는 회사 방화벽 CA가 서명한 인증서가 오는가" 이다. 답은 그 경로 위에 있는 방화벽이 TLS를 가로채서 새 인증서로 바꿔치기하고 있기 때문이다. 이 동작을 SSL Inspection이라고 부른다.

<br>

# 동작 원리: VPN SSL Inspection

SSL Inspection과 SSL Interception은 실무에서 혼용되지만, 엄밀히는 초점이 다르다.

- **SSL/TLS Interception**(가로채기): 방화벽이 TLS 세션을 중간에서 끊고 양쪽에 별도 세션을 맺는 MITM 동작 자체에 초점을 둔 표현이다. 보안 커뮤니티, RFC, 기술 논문에서 주로 쓴다.
- **SSL/TLS Inspection**(검사): 그렇게 복호화한 트래픽을 보안 정책에 따라 검사하는 목적에 초점을 둔 표현이다. 방화벽/보안 벤더(Fortinet, Zscaler 등)가 제품 기능명으로 주로 쓴다. Palo Alto Networks처럼 같은 기능을 Decryption(SSL Forward Proxy)이라 부르는 벤더도 있다. "가로채는 게 아니라 검사하는 것이다"라는 뉘앙스가 담겨 있다.

즉 interception은 수단이고 inspection은 목적이다. inspection을 하려면 interception이 반드시 선행되어야 한다. 이 글에서 문제가 되는 동작은 "방화벽이 TLS를 가로채서 재서명한다"는 interception 쪽이지만, 회사가 이것을 하는 이유는 트래픽 검사(inspection)이므로, 벤더/인프라팀이 쓰는 표현을 따라 SSL Inspection으로 표기한다.

## 정상 vs SSL Inspection 개입

먼저 일반화된 client / 서버 / 방화벽의 흐름을 보자.

![정상 TLS 연결 (회사 내부망)]({{site.url}}/assets/images/kubectl-apiserver-without-firewall.png){: .align-center width="600"}

회사 사무실에서는 `kubectl`이 `kube-apiserver`와 직접 TLS handshake를 한다. 받은 서버 인증서의 issuer가 cluster CA이므로 kubeconfig CA로 검증되고, 정상 동작한다.

다음으로 VPN을 거치는 경우를 보자.

![SSL Inspection 개입 (VPN 경로)]({{site.url}}/assets/images/kubectl-apiserver-with-firewall.png){: .align-center width="700"}

핵심은 클라이언트와 서버 사이에 **완전히 독립된 두 TLS 세션**이 만들어진다는 점이다. 클라이언트의 패킷이 서버에 그대로 전달(릴레이)되는 것이 아니다. 방화벽이 중간에서 양쪽과 **각각 별도의 TCP 연결 + TLS handshake**를 수행하고, 각 세션은 서로 다른 인증서·세션 키·cipher suite를 갖는다. 


### Handshake 단계

두 세션이 만들어지는 과정은 다음과 같다. 아래 1~7은 모두 TCP handshake가 끝난 뒤의 **TLS handshake** 과정이다. TCP 연결도 양쪽으로 따로 맺어지는데(클라이언트 ↔ 방화벽 TCP 연결, 방화벽 ↔ 서버 TCP 연결), TLS handshake는 그 위에서 각각 독립적으로 진행된다.

![SSL Inspection 상세 과정]({{site.url}}/assets/images/vpn-ssl-inspection-detailed-process.png){: .align-center}

- **①** 클라이언트가 ClientHello를 보낸다
- **②** 방화벽이 이것을 가로채고, **자기가 직접 새로운 ClientHello를 만들어서** 진짜 서버(`kube-apiserver`)에 보낸다. 클라이언트의 ClientHello를 릴레이하는 것이 아니라, 방화벽이 독자적인 TLS 클라이언트로서 서버에 접속하는 것이다
- **③** 진짜 서버가 방화벽에게 ServerHello + 서버 인증서를 돌려준다
- **④** 방화벽 ↔ 서버 간 TLS handshake가 완료된다 **(세션 A)**
- **⑤** 방화벽은 받은 진짜 인증서에서 Subject·SAN 등의 정보를 베껴 **위조 인증서를 즉석 발급**하고, 자기 CA 개인키로 서명한다
- **⑥** 위조 인증서를 클라이언트에게 ServerHello로 보낸다
- **⑦** 클라이언트 ↔ 방화벽 간 TLS handshake가 완료된다 **(세션 B)**


핵심은 **②번**이다. 방화벽은 클라이언트의 ClientHello를 서버에 그대로 전달하지 않는다. 자기가 독자적인 TLS 클라이언트로서 **새로운 ClientHello를 만들어** 서버에 접속한다. 따라서 세션 A와 세션 B는 세션 키·cipher suite·인증서가 전부 다른, 완전히 별개의 TLS 세션이다.

### 데이터 전송 단계

TLS handshake 이후 실제 요청·응답이 오가는 과정도 릴레이가 아니라 복호화 → 검사 → 재암호화다.

- 클라이언트 → 서버 방향: 클라이언트가 보낸 암호문을 **세션 B의 키로 복호화** → 평문을 검사(DLP, IDS 등) → **세션 A의 키로 재암호화** → 서버에 전달
- 서버 → 클라이언트 방향: 서버가 보낸 암호문을 **세션 A의 키로 복호화** → 평문 검사 → **세션 B의 키로 재암호화** → 클라이언트에 전달

결국 클라이언트 입장에서는 방화벽이 서버인 줄 알고, 서버 입장에서는 방화벽이 클라이언트인 줄 안다. 이것이 "MITM(Man-in-the-Middle)"이라 부르는 이유다 — 양쪽 어디에서도 중간자의 존재를 TLS 계층만으로는 알 수 없고, 오직 **인증서의 issuer를 확인해야만** 개입 여부를 판단할 수 있다.

## 방화벽은 응답 인증서를 보고 가로채는가

처음 이 동작을 보면 "방화벽이 어떻게 이게 `kube-apiserver` 인증서인지 알고 가로채는가" 같은 의문이 들 수 있다. 결론부터 말하면 **inspection 여부는 서버 응답을 보기 전, 클라이언트 요청 시점에 이미 결정된다.** 방화벽은 응답으로 돌아오는 인증서의 내용을 인지해서 가로채는 것이 아니라, TLS handshake의 첫 패킷(ClientHello)만 보고 이 연결을 inspection할지 결정한다. 일단 inspection 경로로 들어온 연결은 **서버가 어떤 인증서를 돌려주든 — `kube-apiserver`든, nginx든, 무엇이든 — 전부 가로채서 재서명**한다.

구체적으로 방화벽이 보는 것은 다음과 같다.

- 방화벽은 TCP 연결 위로 ClientHello 패킷이 보이는 순간 이 연결을 SSL Inspection 대상으로 가져간다
- inspection 정책에 포트(서비스) 조건을 따로 걸지 않았다면, 포트가 6443이든 443이든 8443이든 무관하다. TLS 트래픽이면 동일하게 처리한다
- 따라서 "이게 `kube-apiserver` 인증서인지 인지해서" 가 아니라, "TLS 연결이니까 일단 가로챈다" 가 정확한 표현이다

조금 더 정확히 보면, 많은 방화벽은 ClientHello 안의 **SNI(Server Name Indication)** 값을 보고 inspection 여부를 분기한다. 이것 역시 클라이언트가 보내는 정보다. SNI와 SAN의 역할 차이, 그리고 서버가 SNI를 어떻게 처리하는지에 대한 자세한 내용은 [SNI와 SAN 글]({% post_url 2026-04-25-CS-TLS-SNI-SAN %})에서 별도로 정리했다.

- SNI는 2003년 RFC 3546에서 TLS 확장으로 처음 정의된 ClientHello 확장 필드로(현재 정의는 RFC 6066 §3), 클라이언트가 "지금 접속하려는 서버 호스트명"을 **암호화 이전 평문**으로 실어 보낸다. 원래 목적은 한 IP에 여러 TLS 사이트(virtual host)가 올라가 있을 때 서버가 올바른 인증서를 골라 응답하도록 하기 위해서다.
- 평문이라는 특성 때문에 방화벽도 별도 복호화 없이 SNI를 읽을 수 있다. 그래서 inspecting firewall은 **SNI 기준으로 정책을 분기**한다 — 예를 들어 SNI로 사이트의 URL 카테고리를 판정해, 금융·의료처럼 민감한 카테고리의 사이트는 inspection 대상에서 제외하는 식이다.
- 그런데 `kubectl`이 **IP 주소로 직접 연결**하는 경우(이번 사례의 `https://10.50.31.10:6443`처럼) Go의 `crypto/tls`는 **SNI를 비워 보낸다**. RFC 6066이 SNI의 HostName에 IP literal을 넣는 것을 허용하지 않기 때문이다("Literal IPv4 and IPv6 addresses are not permitted in HostName").
- 결과적으로 SNI 기반 bypass 룰이 정책에 있더라도 매칭되지 않는다. 목적지 IP 기준으로 따로 제외해 두지 않았다면, 이 연결은 **기본 inspection 정책을 그대로 따르게** 되기 쉽다.

정리하면 이렇다. 방화벽이 이 연결을 inspection할지는 **주로 ClientHello 시점의 정보**(목적지 IP·포트, SNI)로 정한다. SNI 같은 메타정보로 bypass 분기가 가능하지만, 이번 사례처럼 SNI가 비어 있으면 매칭될 단서가 없어 기본 inspection 경로로 떨어진다. 그리고 일단 inspection 대상이 된 연결은 **서버 응답에 무엇이 담겨 있든 — 인증서가 공인 CA든 사설 CA든 — 가로채서 재서명**한다. 서버 인증서에 따라 달라지는 것은 재서명 여부가 아니라 어느 CA로 재서명하느냐인데, 이는 [아래 절](#trust-ca와-untrust-ca)에서 다룬다. SNI에 대한 자세한 사양은 [RFC 6066 §3](https://datatracker.ietf.org/doc/html/rfc6066#section-3)을 참고하자.

## CA만 바꾸는가, 인증서를 새로 만드는가

또 흔한 오해 중 하나는 "원본 인증서에서 issuer 필드만 바꿔치기하는 것 아니냐" 이다. 그렇지 않다. **인증서 자체를 새로 만든다.** X.509 인증서는 issuer가 자기 개인키로 직접 서명한 데이터 구조이므로, 다른 CA가 단순히 한 필드만 갈아 끼우는 것이 불가능하다. 실제로 일어나는 일은 다음과 같다.

1. 방화벽이 진짜 `kube-apiserver`에 TLS 연결을 맺고 원본 서버 인증서를 받는다
2. 원본 인증서에서 Subject(`CN=kube-apiserver`)와 SAN 같은 기본 필드를 가져온다
3. 그 정보를 바탕으로 **완전히 새로운 인증서를 즉석 발급**하고, 자기 CA(`ExampleCorp_Untrust_ECDSA`)의 개인키로 서명한다
4. 새로 만든 인증서를 클라이언트에게 서버 인증서로 전달한다

따라서 클라이언트가 받는 인증서는 Subject는 같지만 **Issuer와 서명, 일부 확장 필드가 모두 달라진** 다른 인증서다. 위에서 `openssl s_client`로 확인한 결과(subject 동일, issuer 다름)가 정확히 이 상황이다.

## Trust CA와 Untrust CA

방화벽 CA 이름에 `Untrust`가 들어 있는 점도 짚어둘 만하다. SSL Inspection을 하는 방화벽은 보통 재서명용 CA를 두 개 두고, **방화벽이 원래 서버에 대신 연결해 받은 인증서를 자기 신뢰 CA 목록으로 검증할 수 있느냐**에 따라 둘 중 하나로 재서명한다. 대표적으로 Palo Alto Networks 문서는 이 둘을 Forward Trust 인증서와 Forward Untrust 인증서라고 부른다.

- `*_Trust_*`: 원래 서버 인증서가 방화벽의 신뢰 CA 목록으로 검증되는 경우에 사용한다. 이 목록은 방화벽에 기본으로 들어 있는 공인 CA(DigiCert, Let's Encrypt 등)에 관리자가 추가한 CA를 더한 것이다. 예를 들어 `google.com`에 연결하면 공인 CA 체인이 확인되므로 Trust CA로 재서명한다.
- `*_Untrust_*`: 원래 서버 인증서가 그 목록으로 검증되지 않는 경우에 사용한다. 자체 서명(self-signed) 인증서이거나, 관리자가 신뢰 목록에 넣지 않은 사설 PKI의 CA가 서명한 인증서가 여기에 해당한다.

[앞 절](#방화벽은-응답-인증서를-보고-가로채는가)에서 본 URL 카테고리와 헷갈리기 쉬운데, 둘은 쓰이는 단계가 다르다. 카테고리는 **이 연결을 복호화할지 말지**를 정하는 정책 조건이고, ClientHello 시점에 판단한다. Trust와 Untrust는 **복호화하기로 한 연결을 어느 CA로 재서명할지**의 문제이고, 방화벽이 서버에서 원래 인증서를 받은 뒤(위 handshake의 ③ 이후)에 정해진다. 기준은 카테고리가 아니라 원래 서버 인증서의 검증 결과다.

`kube-apiserver` 트래픽이 `Untrust`로 재서명된 이유가 바로 이것이다. 방화벽이 `kube-apiserver`에 대신 연결해서 받은 서버 인증서의 issuer가 `rke2-server-ca` → RKE2 클러스터가 자체적으로 만든 사설 CA다. 관리자가 이 CA를 방화벽 신뢰 목록에 따로 넣어 두지 않았으니 "신뢰할 수 없는 인증서"로 판단하고 Untrust CA로 재서명한 것이다. 사용자나 관리자 입장에서 보면 "내부 인프라 트래픽인데 왜 untrust냐" 싶지만, 방화벽은 이 맥락을 알지 못하고 오직 인증서의 CA 체인만 보고 판단한다.

같은 회사 도메인 아래의 사내 서비스 두 개에 각각 접속해 보면 이 기준이 그대로 드러난다.

| 사내 서비스 | 원래 서버 인증서 발급자 | 재서명 CA |
|---|---|---|
| 서비스 A | 공인 CA | Trust CA |
| 서비스 B | 사내 사설 CA | Untrust CA |

둘 다 같은 회사 도메인의 사내 서비스인데, 결과를 가른 것은 원래 인증서의 발급자뿐이었다.

그렇다면 왜 굳이 CA를 둘로 나눌까. 방화벽이 모든 연결을 회사 CA 하나로 재서명한다고 생각해 보자. 원래라면 브라우저 경고가 떠야 할 사이트(자체 서명 인증서나, 알 수 없는 CA가 서명한 인증서를 쓰는 사이트)도, 회사 CA를 신뢰하는 PC에서는 멀쩡한 사이트처럼 보이게 된다. 방화벽이 끼어드는 바람에 사용자가 받아야 할 경고가 사라지는 것이다.

Untrust CA는 이 경고를 살려 두기 위한 장치다. Palo Alto Networks 문서는 Forward Trust 인증서는 클라이언트의 trust store에 배포하되, Forward Untrust 인증서는 클라이언트에 설치하지 말라고 안내한다. 그러면 원래 인증서를 믿을 수 있는 사이트는 회사 CA 덕분에 정상으로 보이고, 원래부터 믿을 수 없던 사이트는 Untrust CA로 재서명되어 클라이언트에서 그대로 인증서 경고가 뜬다.

> 이 환경도 그렇게 구성되어 있다. macOS 시스템 키체인에는 회사 루트 CA와 Trust CA 두 개(RSA용, ECDSA용)만 있고, Untrust 쪽은 중간 CA도 루트 CA도 없다. Trust CA가 두 개인 것은 재서명 인증서의 키 알고리즘이 원래 서버 인증서를 따라가기 때문이다. RSA 인증서를 쓰는 사이트는 RSA용 Trust CA로, ECDSA 인증서를 쓰는 `google.com`은 `ExampleCorp_Trust_ECDSA`로 재서명되어 있었다. `kube-apiserver`가 `ExampleCorp_Untrust_ECDSA`로 재서명된 것도 같은 이치로, 받은 인증서의 공개키가 RKE2가 만든 원래 인증서처럼 ECDSA(P-256)였다.

**다만 이번 글의 `kubectl` 상황**에서는, Trust든 Untrust든 결국 **방화벽이 만든 MITM 인증서**이고, kubeconfig에 박힌 CA는 `rke2-server-ca`뿐이므로 — **검증 실패라는 점에서 구분할 실익이 없다.** 둘 다 cluster CA로는 검증할 수 없다. Trust/Untrust는 **이 연결의 상대(원 서버) 인증서를 방화벽이 신뢰하는 체인으로 검증할 수 있느냐**에 따른 방화벽 내부 구분이지만, `kubectl`의 cluster CA pinning과는 별도 축이다.

## SSL Inspection의 목적

참고로 SSL Inspection을 돌리는 일반적인 이유는 다음과 같다. 깊게 다룰 필요는 없지만, 왜 회사가 이런 검사를 하는지 맥락 정도는 알아두면 좋다.

- **악성 트래픽 탐지**: 암호화된 채널 안에 숨어 들어오는 멀웨어, C2(Command and Control) 통신을 IDS/IPS 시그니처로 탐지
- **DLP(Data Loss Prevention)**: 사내 민감 데이터(소스코드, 개인정보 등)가 외부로 유출되는지 트래픽 페이로드를 검사
- **카테고리 기반 정책 적용**: URL 카테고리(예: 도박, 악성, 미분류 등)에 따라 차단/허용 정책을 적용

이런 목적상 회사 입장에서 SSL Inspection 자체를 끄기는 어렵다. 부득이한 상황에 "특정 트래픽만 검사 대상에서 빼 달라" 정도를 요청할 수 있을 뿐이다.

<br>

# 그냥 회사 CA를 등록하면 안 되는 건가

SSL Inspection이 원인이라면, 방화벽이 재서명에 사용하는 회사 CA를 kubeconfig에 등록해 놓으면 되는 것 아닌가? 기술적으로는 가능하다. 하지만 **하면 안 된다.** 그 이유를 정리해 보자.

> 브라우저로 웹 사이트를 열 때는 SSL Inspection이 끼어 있어도 대부분 자물쇠 표시가 정상으로 뜬다. [다음 글]({% post_url 2026-04-25-Dev-Notion-MCP-VPN-SSL-Inspection %})의 "그런데 이건 왜 되는가" 절에서 다루겠지만, 이것은 **내 로컬 macOS 키체인에 회사 CA(정확히는 Trust CA)가 이미 신뢰됨으로 등록되어 있기 때문**이다. 그러니 같은 방식으로 kubeconfig에도 회사 CA를 등록하면 안 되는가 하는 의문이 자연스레 떠오른 것이다.

## kubeconfig CA는 cluster 전용 trust anchor

`kubectl`은 kubeconfig에 `certificate-authority-data`(또는 `certificate-authority`) 필드가 지정되어 있으면 **OS 시스템 trust store(macOS 키체인 등)를 보지 않고** 오직 해당 필드의 CA만을 신뢰 기준으로 사용한다. 즉 키체인에 회사 CA가 등록되어 있는지 여부는 이 상황의 `kubectl`에게는 무관한 정보다.

> 참고로, kubeconfig에 CA가 아예 지정되어 있지 않고 `insecure-skip-tls-verify`도 꺼져 있는 경우에는 client-go가 시스템 루트 CA로 폴백한다. 다만 RKE2·EKS 등 일반적인 클러스터 배포는 `certificate-authority-data`를 항상 채워 주므로, 실제로는 "kubeconfig CA만 신뢰" 상태로 동작한다. 설령 시스템 루트 CA로 폴백하더라도 이 환경에서는 소용이 없다. 키체인에 있는 회사 CA는 Trust CA뿐이고, `kube-apiserver` 인증서를 재서명한 Untrust CA는 없기 때문이다.

이는 의도된 설계다. cluster CA는 그 cluster를 관리하는 주체(여기서는 RKE2)가 직접 만들고 관리하는 폐쇄 PKI이기 때문에, 그 CA가 서명한 인증서만 진짜 API 서버임을 보장할 수 있다. 시스템 trust store에 등록된 공개 CA들은 이 cluster와 무관하므로, 처음부터 검증 후보에 들이지 않는다.

## 회사 CA를 추가하면 발생하는 일

만약 kubeconfig의 `certificate-authority-data`를 회사 CA를 포함하도록 수정한다고 가정해 보자. 표면적으로는 TLS 검증이 통과되고 `kubectl`이 동작하는 것처럼 보일 것이다. 하지만 이 방식은 보안, 운영, 그리고 대안과의 실질적 동등성 세 가지 층위에서 문제가 있다.

1. 보안: **진짜 cluster 검증을 포기하는 셈이 된다**
   - 회사 방화벽이 만들어 주는 어떤 서버 인증서든 `CN=kube-apiserver`로만 서명해서 보내면 통과한다
   - 즉 "이 연결의 끝이 진짜 우리 cluster의 API 서버인가" 라는 근본 검증이 사라진다
   - 이론상 회사 방화벽 자체가 침해되거나 정책이 변경되면, 가짜 API 서버로 트래픽이 돌아가도 알아챌 수 없다
   - 게다가 이번에 `kube-apiserver` 인증서를 재서명한 것은 Untrust CA다. kubeconfig에 넣게 될 CA가 바로, [앞에서 본 것처럼](#trust-ca와-untrust-ca) 클라이언트에 설치하지 않도록 되어 있는 그 인증서다. 원래 서버를 믿을 수 없을 때 경고를 띄우려고 둔 CA를 신뢰하는 셈이다

2. 운영: **사무실/VPN 환경에서 kubeconfig가 분기된다**
   - 사무실에서 직접 연결할 때는 방화벽을 안 거치므로 진짜 cluster CA(rke2-server-ca)가 서명한 인증서가 그대로 온다
   - 그런데 kubeconfig에 회사 CA만 등록되어 있다면 rke2-server-ca가 신뢰 목록에 없으니 이번엔 사무실에서 검증 실패다
   - 결국 "사무실용 kubeconfig"와 "VPN용 kubeconfig"를 분기 관리해야 한다. 이 방법은 VPN 경로에만 국한된 패치이고, 이걸 "해결"이라고 부르려면 환경 감지 로직까지 딸려 붙어야 한다

3. **`insecure-skip-tls-verify=true`와 보안 수준이 비슷해진다**
   - 회사 CA를 신뢰한다는 것은, 방화벽이 `CN=kube-apiserver`로 서명해 주기만 하면 `kubectl`이 무조건 통과시킨다는 뜻이다. 엔드포인트 뒤에 누가 있는지를 더 이상 판별하지 못한다.
   - 회사 inspecting firewall을 거치는 어떤 TLS 세션이든, 그 세션에 대해 회사 CA가 즉석에서 발급한 서버 인증서를 받게 된다. 즉 "회사 CA 서명"이라는 사실 자체로는 상대 엔드포인트가 진짜 `kube-apiserver`임을 더 이상 증명하지 못한다
   - 이 점에서, 검증을 명시적으로 끈 `insecure-skip-tls-verify=true`와 보안 수준은 사실상 같다.
   - 차이가 있다면 의도가 드러나느냐뿐이다. 회사 CA를 넣는 쪽은 "검증이 켜져 있는 것처럼" 보이게 만들어 오히려 나중에 문제를 찾기 어렵다
   - 임시로 검증을 풀어야 한다면, 차라리 아래 [우회 방법](#우회-방법) 절에서 다룰 `insecure-skip-tls-verify=true`를 명시적으로 설정하는 편이 낫다

정리하면, kubeconfig의 certificate-authority-data는 시스템 trust store와 분리된 PKI이며, 그 신뢰 범위는 "이 cluster의 API 서버가 진짜인가"를 판별하는 데만 쓰도록 좁게 유지하는 게 설계 의도에 맞다. 키체인의 "항상 신뢰" 설정과 kubeconfig의 `certificate-authority-data`는 같은 의미가 아니다. 키체인의 "항상 신뢰"를 추가하는 것처럼 회사 CA를 kubeconfig에 넣으면, TLS 검증은 통과하지만 의미 있는 검증은 사라진다.

<br>

# 우회 방법

근본 원인이 회사 인프라 정책이므로, 내가 직접, 즉시 할 수 있는 임시 우회와 인프라/네트워크팀에 요청해야 하는 근본 해결을 분리해서 정리해 보자.

| 방법 | 방식 | 처리 주체 | 비고 |
|---|---|---|---|
| bootstrap 노드 SSH | VPN 경로 자체를 우회. 노드 안에서 직접 작업 | 본인 | 즉시 적용. bootstrap 노드 본래 목적과도 부합 |
| `--insecure-skip-tls-verify` (일회성 플래그) | 서버 인증서 검증을 명시적으로 건너뜀 | 본인 | 임시용. MITM 위험 인지 필요. kubeconfig에 저장하는 방식은 CA가 지워지므로 피함 |
| SSL Inspection bypass | 방화벽 정책에서 해당 IP:포트를 SSL 검사 제외 | 방화벽 관리자 | 방화벽은 통과하지만 복호화·재서명을 안 함. 일반적으로 가장 깔끔 |
| VPN 라우팅 분기 | 클러스터 대역만 inspecting firewall을 거치지 않는 경로로 라우팅 | VPN 관리자 | 토폴로지가 받쳐 줄 때만 가능. 흔히 "split tunnel"로도 불리지만 의미가 다름 |

## bootstrap 노드 SSH (채택)

가장 깔끔한 즉시 해결책은 **클러스터의 bootstrap 노드에 SSH로 접속해서 그 안에서 `kubectl`을 실행**하는 것이다. 이 경로는 VPN을 통해 bootstrap 노드까지만 들어가고, 그 노드에서 `kube-apiserver`로의 통신은 사내 네트워크 안에서 이뤄지므로 SSL Inspection이 개입하지 않는다.

추가로 bootstrap 노드는 보통 클러스터 초기화·설치·유지보수 작업 수행을 위한 관리 노드 역할을 부여하는 경우가 많다. 즉 이렇게 쓰는 건 임시 우회라기보다 **노드 본래 용도에 부합하는 사용**이기도 하다.

## insecure-skip-tls-verify (임시 한정)

로컬 `kubectl`을 꼭 써야 하는 경우, 검증을 명시적으로 끄는 옵션이 있다. 명령마다 붙이는 **일회성 플래그**로 쓰는 것이 좋다.

```bash
# TLS 검증 끄기 (이 명령 한 번에만 적용, kubeconfig는 바뀌지 않음)
$ kubectl --insecure-skip-tls-verify get nodes
```

같은 설정을 `kubectl config set-cluster`로 kubeconfig에 저장할 수도 있지만, 권하지 않는다. `set-cluster`는 insecure 모드를 켤 때 그 cluster의 `certificate-authority`·`certificate-authority-data`를 **함께 지운다**. 나중에 `--insecure-skip-tls-verify=false`로 되돌려도 지워진 CA는 돌아오지 않는다.

```bash
# 권하지 않음: cluster CA가 kubeconfig에서 지워진다
$ kubectl config set-cluster <cluster-name> --insecure-skip-tls-verify=true

# 되돌려도 CA는 복구되지 않는다
$ kubectl config set-cluster <cluster-name> --insecure-skip-tls-verify=false
```

되돌린 뒤의 kubeconfig에는 CA도 insecure 설정도 없으므로, [앞에서 본 것처럼](#kubeconfig-ca는-cluster-전용-trust-anchor) client-go는 시스템 루트 CA로 검증한다. 시스템 루트 CA에는 `rke2-server-ca`도 회사 Untrust CA도 없으니, 사무실에서도 VPN에서도 검증에 실패한다. 이미 이렇게 됐다면 cluster CA 파일로 다시 채우거나(`kubectl config set-cluster <cluster-name> --certificate-authority=<ca.crt> --embed-certs=true`), bootstrap 노드의 `rke2.yaml`을 다시 복사해 오면 된다.

> `kubectl config set clusters.<cluster-name>.insecure-skip-tls-verify true`처럼 범용 `config set`으로 필드만 바꾸면 CA는 지워지지 않는다. 대신 CA와 insecure 설정이 함께 남아 `specifying a root certificates file with the insecure flag is not allowed` 에러로 아예 연결이 안 된다. client-go가 둘을 동시에 설정하는 것을 허용하지 않기 때문이다. 일회성 플래그로 insecure를 켜면 kubeconfig의 CA를 그 명령에서만 비우도록 처리되어 있어 이 충돌이 없다.

기능 자체는 잘 동작하지만, 사용 시 다음을 인지하고 있어야 한다.

- **MITM에 무방비**: 서버 인증서를 전혀 검증하지 않으므로 가짜 API 서버에 연결돼도 모른다. 다만 회사 VPN 안에서 사설 IP로만 도달 가능한 대상이라 실제 공격 가능성은 낮은 편이다
- **권한 측면 위험**: RKE2의 `/etc/rancher/rke2/rke2.yaml`을 그대로 가져온 kubeconfig는 일반적으로 `system:masters` 그룹(= cluster-admin 권한)에 매핑된다. 이런 강한 권한의 자격증명을 검증 없이 사용하면 보안 감사에서 지적받기 쉽다

따라서 굳이 쓰려면, **SSL Inspection bypass 등 인프라 쪽에서 진짜 cluster CA가 서명한 인증서를 다시 받을 수 있게 될 때까지** 잠깐 쓰는 임시 옵션으로만 두자.

## SSL Inspection bypass와 VPN 라우팅 분기

근본 해결책은 인프라 쪽에서 **클라이언트가 진짜 cluster CA가 서명한 서버 인증서를 다시 받을 수 있도록** 경로를 조정하는 것이다. 크게 두 가지 접근이 있고, 적용 위치와 주체가 다르다.

- **SSL Inspection bypass** (권장): 방화벽 정책에서 특정 목적지 IP:포트(여기서는 `10.50.31.10:6443`)를 SSL 검사 대상에서 제외한다. 트래픽은 여전히 방화벽을 통과하지만 복호화·재서명을 하지 않는다. **방화벽 관리자**가 처리한다. 내부 cluster API라면 inspection 대상에서 빼도 보안 손실이 거의 없으므로 일반적으로 가장 깔끔한 정공법이다.
- **VPN 라우팅 분기**: 일부 환경에서는 VPN concentrator와 inspecting firewall이 별도 경로로 구성되어 있어, VPN 클라이언트나 VPN 게이트웨이의 라우팅 정책에서 특정 대역(예: 사내 클러스터 대역)을 inspection 경로 외로 분기할 수 있다. **VPN 관리자**가 처리한다.

> 흔히 "VPN split tunnel"이라고도 부르지만, 일반적인 split tunnel(= "사내 트래픽만 VPN으로, 인터넷 트래픽은 VPN 밖으로 빼기")의 정의와는 다르다. 사내 사설 IP인 `10.50.31.10`은 VPN 터널 밖으로 빼면 애초에 라우팅 자체가 안 되기 때문이다. 여기서 의미하는 것은 "VPN 안에서, inspecting firewall만 우회하는 별도 경로"이며, 사내 네트워크 토폴로지가 그런 분기를 허용할 때만 가능하다.

둘 중 어느 쪽이든 결과적으로 클라이언트는 진짜 cluster CA가 서명한 서버 인증서를 받게 되어 검증이 통과한다. 토폴로지 제약이 적고 적용 범위를 정확히 좁힐 수 있는 SSL Inspection bypass 쪽이 보통 더 현실적이다.

> 이론상 직접 외부 IP로 6443 포트를 열어 공인 인터넷에서 바로 접속하게 만드는 방법도 가능하겠지만, 사내 cluster API를 외부 노출하는 것이므로 보안상의 이유에서 사실상 선택지로 고려조차 할 수 없다.

<br>

# 정리

이번 문제는 표면적으로는 평범한 TLS 검증 실패 에러 한 줄이지만, 그 뒤에는 **VPN 경로의 방화벽이 SSL Inspection으로 모든 TLS 트래픽을 가로채 재서명한다**는 회사 인프라 정책이 깔려 있었다. 이 동작 자체는 IDS/IPS, DLP 같은 보안 목적상 일반적인 회사 환경에서 흔히 쓰이는 방식이지만, **cluster 전용 폐쇄 PKI**를 사용하는 `kubectl`과는 구조적으로 충돌한다.

`kubectl`이 OS 시스템 trust store를 보지 않고 kubeconfig CA만 신뢰하는 것은 보안적으로 옳은 설계다. cluster CA가 서명한 인증서만이 "진짜 우리 cluster의 API 서버"임을 보장하므로, 방화벽이 만든 인증서를 신뢰 목록에 추가하는 것은 그 보장을 포기하는 셈이 된다. 즉 "키체인에 회사 CA가 신뢰됨" 과 "kubectl이 회사 CA를 신뢰함" 은 의미가 다르다.

해결 방향도 그래서 두 갈래로 나뉜다. 본인 측에서는 bootstrap 노드 SSH로 SSL Inspection 경로 자체를 회피하거나(권장), 임시로 검증을 끄는 정도까지가 가능하다. 본질적인 해결은 방화벽/네트워크 정책 변경이 필요하므로, 인프라 팀에 SSL Inspection bypass(권장) 또는 VPN 라우팅 분기 적용을 요청해야 한다.

마지막으로, 같은 "VPN SSL Inspection" 이슈여도 클라이언트 도구의 trust 모델에 따라 증상과 해결 방향이 달라질 수 있다. 예를 들어 Node.js 기반 도구는 OS trust store도 kubeconfig 같은 도구별 trust store도 보지 않고 자체 내장 CA bundle만 사용하므로, kubectl과는 또 다른 양상의 문제가 생긴다. 이 부분은 [VPN SSL Inspection으로 인한 Notion MCP 연결 실패]({% post_url 2026-04-25-Dev-Notion-MCP-VPN-SSL-Inspection %})에서 정리한다.

<br>