---
title: "[EKS] EKS: 인증/인가 - 3. 사용자 → K8s API: 인증(AuthN) 실습"
excerpt: "사용자(IAM) → K8s API 인증 과정을 단계별로 실습하며, 토큰 생성부터 STS 검증까지의 전 과정을 직접 확인해 보자."
categories:
  - Kubernetes
toc: true
header:
  teaser: /assets/images/blog-Dev.jpg
tags:
  - Kubernetes
  - AWS
  - EKS
  - STS
  - IAM
  - TokenReview
  - CloudTrail
  - CloudWatch
  - aws-iam-authenticator
  - AWS-EKS-Workshop-Study
  - AWS-EKS-Workshop-Study-Week-4
---

*[서종호(가시다)](https://www.linkedin.com/in/gasida99/)님의 AWS EKS Workshop Study(AEWS) 4주차 학습 내용을 기반으로 합니다.*

<br>

# TL;DR

- EKS 인증은 4단계로 진행된다: (1) 토큰 생성 → (2) Bearer Token 전송 → (3) TokenReview → (4) STS 검증
- 토큰 생성(`aws eks get-token`)은 **네트워크 통신 0회**로 완료되는 순수 로컬 연산이다
- EKS 토큰은 JWT가 아니라 `k8s-aws-v1.<base64>` **2파트 구조**다. 서명은 토큰 바깥이 아닌 pre-signed URL 내부에 있다
- TokenReview 응답으로 IAM identity가 K8s username/group으로 변환되는 것을 직접 확인할 수 있다
- CloudTrail과 CloudWatch에서 인증의 **양면**(STS 호출 기록 + authenticator 로그)을 교차 확인할 수 있다

<br>

# 개요

[이전 글]({% post_url 2026-03-12-Kubernetes-EKS-01-01-03-Kubeconfig-Authentication %})에서 EKS 인증의 근본 구조(왜 STS `GetCallerIdentity`인가, pre-signed URL, Bearer Token, kubeconfig exec)를 다뤘다. 이번 글에서는 그 메커니즘이 실제로 어떻게 동작하는지 **실습을 통해 확인**한다. [전체 흐름 개요]({% post_url 2026-04-02-Kubernetes-EKS-Auth-02-00-EKS-Auth-Overview %}) 중 인증(AuthN) 부분에 해당한다.

인증 4단계를 하나씩 따라가며, 각 단계에서 무엇이 일어나는지 직접 확인해 볼 것이다.

```text
[1] 토큰 생성   →  [2] Bearer Token 전송  →  [3] TokenReview  →  [4] STS 검증
(클라이언트)        (kubectl → EKS API)      (API → webhook)     (authenticator → STS)
```

> 이 글의 4단계는 [전체 흐름 개요]({% post_url 2026-04-02-Kubernetes-EKS-Auth-02-00-EKS-Auth-Overview %})의 9단계 중 인증([1]~[6])에 해당한다.
>
> | 이 글 | 전체 흐름 개요 |
> | --- | --- |
> | 1. 토큰 생성 | [1] K8S Action + [2] Token 발급 |
> | 2. Bearer Token 전송 | [3] Action + Token |
> | 3. TokenReview | [4] Id Token 확인 |
> | 4. STS 검증 | [5] sts:GetCallerIdentity + [6] 성공 |

<br>

# 1. 토큰 생성 -- 클라이언트 측

## aws eks get-token

현재 IAM 자격증명을 확인한 뒤, 토큰을 발급해 보자.

```bash
aws sts get-caller-identity --query Arn
```

```
"arn:aws:iam::123456789012:user/admin"
```

```bash
export CLUSTER_NAME=myeks
aws eks get-token --cluster-name $CLUSTER_NAME | jq
```

```json
{
  "kind": "ExecCredential",
  "apiVersion": "client.authentication.k8s.io/v1beta1",
  "spec": {},
  "status": {
    "expirationTimestamp": "2026-04-09T12:35:59Z",
    "token": "k8s-aws-v1.aHR0cHM6Ly9zdHMu..."
  }
}
```

응답은 [`ExecCredential`](https://kubernetes.io/docs/reference/config-api/client-authentication.v1beta1/) 형식이다. kubeconfig의 `exec` 블록으로 실행된 외부 명령이 kubectl에 인증 정보를 반환할 때 사용하는 **K8s 표준 형식**으로, kubectl(client-go)은 `status.token`을 Bearer Token으로 사용하고, `status.expirationTimestamp`를 보고 만료 전까지 캐시된 토큰을 재사용한다. 만료되면 exec 명령을 다시 실행하여 새 토큰을 발급받는다. 사용자는 이 과정을 인지하지 못한 채 계속 작업할 수 있다.

`expirationTimestamp`는 토큰 생성 시각 기준 약 **15분** 후다.

<br>

## SigV4 서명 과정: 토큰 생성의 핵심

`aws eks get-token`이 내부적으로 수행하는 것은 **SigV4(Signature Version 4)** 서명이다. AWS API 요청의 무결성과 신원 증명을 위한 서명 프로토콜로, Secret Access Key를 직접 통신에 노출하지 않으면서 해당 키의 소유를 증명하는 "일회성 증명서"를 만드는 과정이다.

왜 Secret Key를 직접 사용하지 않는가? 만약 Secret Key로 직접 서명했다가 그 서명이 탈취되면, 공격자가 해당 키를 영구적으로 악용할 수 있다. SigV4는 Secret Key를 재료로 삼아 **날짜, 리전, 서비스에 종속된 하위 키**를 단계적으로 유도하므로 훨씬 안전하다.

### 서명 키(Signing Key) 유도 4단계

모든 단계에는 **HMAC-SHA256** 알고리즘이 사용된다.

**1단계: 정규 요청(Canonical Request) 생성**

서명할 HTTP 요청을 정해진 포맷으로 정규화(normalize)한다. 공백, 헤더 순서 등이 달라도 같은 서명이 나오게 하기 위함이다.

- HTTP 메서드: `GET`
- 엔드포인트: `sts.ap-northeast-2.amazonaws.com`
- 쿼리 파라미터: `Action=GetCallerIdentity`, `Version=2011-06-15` 등
- 헤더: `host`, `x-k8s-aws-id` (클러스터 이름)

이 정보들을 정규화한 후 SHA256 해시하여 **Hashed Canonical Request**를 만든다.

**2단계: 서명할 문자열(String to Sign) 생성**

정규 요청에 "언제, 어디서" 보낸 요청인지를 덧붙인다.

- 알고리즘: `AWS4-HMAC-SHA256`
- 요청 시각: ISO8601 타임스탬프 (예: `20260409T120000Z`)
- Credential Scope: `날짜/리전/서비스/aws4_request` (예: `20260409/ap-northeast-2/sts/aws4_request`)
- 1단계의 해시값

**3단계: 서명 키(Signing Key) 유도**

Secret Access Key를 직접 사용하지 않고, 단계별로 암호화된 키를 새로 만든다.

```text
DateKey    = HMAC-SHA256("AWS4" + SecretKey, 날짜)
RegionKey  = HMAC-SHA256(DateKey,    리전)        ← ap-northeast-2
ServiceKey = HMAC-SHA256(RegionKey,  서비스)       ← sts
SigningKey = HMAC-SHA256(ServiceKey, "aws4_request")
```

각 단계마다 범위가 좁아진다. `DateKey`는 해당 날짜에만, `RegionKey`는 해당 날짜+리전에서만, `ServiceKey`는 해당 날짜+리전+서비스에서만 유효하다. `ap-northeast-2`로 만든 서명은 `us-east-1`에서 검증하면 불일치한다.

Secret Key는 **1단계 `DateKey`를 만들 때 딱 한 번** 입력값으로 쓰인다. 이후 단계부터는 이전 단계에서 생성된 해시값이 키 역할을 수행한다. 결국 Secret Key는 "내가 나임을 증명하는 수학적 연쇄 반응의 첫 번째 도미노" 역할이다.

**4단계: Pre-signed URL 생성 및 토큰 변환**

최종 `SigningKey`와 2단계의 `String to Sign`으로 **Signature**를 생성한 뒤, 모든 파라미터를 URL의 쿼리 스트링으로 조립하여 Pre-signed URL을 만든다. 이 URL을 Base64url 인코딩하고 `k8s-aws-v1.` 접두사를 붙이면 최종 토큰이 된다.

### AWS 서버의 검증

AWS STS는 동일한 과정을 재현(재계산)하여 서명을 검증한다. SigV4의 HMAC 구조상, 서버 측에서도 원본 Secret Key(또는 동등한 값)를 보유해야 검증이 가능하다. 일반적인 비밀번호는 단방향 해시로 저장하지만, AWS Secret Key는 `HMAC(secret, data)` 연산에 secret 자체가 필요하므로 해시만 저장할 수 없다. AWS는 이를 HSM(Hardware Security Module) 기반으로 암호화하여 안전하게 보관한다.

```text
클라이언트: Secret Key → HMAC → Signature 생성 → Pre-signed URL에 포함
AWS 서버:  (저장된 Secret Key) → 동일한 HMAC 계산 → Signature 비교
           → 일치: "Secret Key를 가진 사람만이 이 서명을 만들 수 있으니 인증 성공"
           → 불일치: "키가 틀렸거나 내용이 변조된 것이니 거부"
```

이 과정에서 네트워크에 Secret Key가 단 한 번도 노출되지 않는다.

<br>

## --debug 로그 분석

`--debug` 플래그를 붙이면 토큰 생성 과정의 내부 동작을 볼 수 있다.

```bash
aws eks get-token --cluster-name $CLUSTER_NAME --debug 2>&1
```

핵심 로그를 단계별로 정리하면 다음과 같다.

### 자격증명 탐색 (Credential Provider Chain)

```
Looking for credentials via: env
Looking for credentials via: assume-role
Looking for credentials via: assume-role-with-web-identity
Looking for credentials via: sso
Looking for credentials via: shared-credentials-file
Found credentials in shared credentials file: ~/.aws/credentials
```

botocore가 `env → assume-role → web-identity → sso → shared-credentials-file` 순서로 크리덴셜을 찾는다. 여기서는 `~/.aws/credentials` 파일에서 찾았다. Access Key ID가 `AKIA...`(영구 키)로 시작하는 것을 확인할 수 있다. EC2 인스턴스였다면 IMDS에서 임시 자격증명(`ASIA...`)을 가져왔을 것이다.

### STS 엔드포인트 Resolve

```
Calling endpoint provider with parameters:
  {'Region': 'ap-northeast-2', 'UseDualStack': False, 'UseFIPS': False, 'UseGlobalEndpoint': False}
Endpoint provider result: https://sts.ap-northeast-2.amazonaws.com
```

**리전별 STS 엔드포인트**(`sts.ap-northeast-2.amazonaws.com`)가 선택되었다. 이건 **실제 HTTP 호출이 아니라**, Pre-signed URL을 만들 대상 주소를 결정한 것뿐이다. CloudWatch Logs Insight 쿼리로 `stsendpoint`를 확인할 때 이 부분과 매칭된다.

### SigV4 서명 -- Canonical Request

```
Calculating signature using v4 auth.
```

```text
GET
/
Action=GetCallerIdentity&Version=2011-06-15
&X-Amz-Algorithm=AWS4-HMAC-SHA256
&X-Amz-Credential=AKIA...%2F20260409%2Fap-northeast-2%2Fsts%2Faws4_request
&X-Amz-Date=20260409T122237Z&X-Amz-Expires=60
&X-Amz-SignedHeaders=host%3Bx-k8s-aws-id
host:sts.ap-northeast-2.amazonaws.com
x-k8s-aws-id:myeks                    ← 클러스터 이름이 서명에 포함
host;x-k8s-aws-id
e3b0c44298fc1c14...                    ← 빈 body의 SHA256 해시
```

| 관찰 포인트 | 의미 |
| --- | --- |
| `x-k8s-aws-id:myeks` | 이 토큰은 `myeks` 클러스터에서**만** 유효하다 |
| `X-Amz-Expires=60` | Pre-signed URL의 유효 시간은 **60초**다 (kubectl의 15분 만료와 별개) |
| `X-Amz-SignedHeaders=host;x-k8s-aws-id` | 서명에 포함된 헤더가 정확히 2개다 |
| Body 해시 `e3b0c44...` | 빈 문자열의 SHA256 해시. GET 요청이라 body가 없다 |

### SigV4 서명 -- String to Sign

```text
AWS4-HMAC-SHA256
20260409T122237Z
20260409/ap-northeast-2/sts/aws4_request
9a3409dff4ae289a...    ← Canonical Request의 SHA256
```

Credential Scope 구조(`날짜/리전/서비스/aws4_request`)가 그대로 나타난다.

### SigV4 서명 -- 최종 서명 및 출력

```
Signature: fe16a7228e1f1f393e309130ebd97b2430835d831faa5bb0a1b10385d4692b35
```

최종 ExecCredential 토큰이 출력된다. `expirationTimestamp`는 생성 시각 기준 약 14~15분 후다.

### 놓치기 쉬운 포인트

| 관찰 포인트 | 의미 |
| --- | --- |
| `No configured endpoint found` | `~/.aws/config`에 `sts_regional_endpoints` 설정이 없지만, SDK 기본값으로 리전별 엔드포인트 사용 |
| `Setting sts timeout as (60, 60)` | connect/read timeout 60s. 실제 HTTP 호출이 아니므로 사용되지 않음 |
| `STSClientFactory._inject_k8s_aws_id_header` | `x-k8s-aws-id` 헤더를 주입하는 EKS 커스텀 핸들러 |
| `STSClientFactory._retrieve_k8s_aws_id` | `--cluster-name myeks`에서 클러스터 이름을 가져와 서명에 바인딩 |

### 실제 네트워크 통신은 0회

`--debug` 로그 전체에 `Sending http request`, `Response received` 같은 실제 HTTP 통신 로그는 없다. 모든 것이 로컬에서 수학적 연산만으로 완료된다.

<br>

## 토큰 디코딩

토큰을 디코딩하면 pre-signed URL이 나오는지 직접 확인해 보자.

```bash
TOKEN_DATA=$(aws eks get-token --cluster-name myeks | jq -r '.status.token')
echo "$TOKEN_DATA"
```

```
k8s-aws-v1.aHR0cHM6Ly9zdHMuYXAtbm9ydGhlYXN0LTIu...
```

### 토큰 분리 (IFS split)

```bash
IFS='.' read header payload signature <<< "$TOKEN_DATA"
echo "header: $header"
echo "payload: ${payload:0:30}..."
echo "signature: '$signature'"
```

`IFS`(Internal Field Separator)를 `.`으로 설정하면 `read` 명령이 토큰을 `.` 기준으로 분리한다.

```
header: k8s-aws-v1
payload: aHR0cHM6Ly9zdHMuYXAtbm9ydGhl...
signature: ''
```

signature가 **비어 있다**. EKS 토큰은 JWT가 아니기 때문에 정상이다 (이유는 아래에서 설명).

### Payload 디코딩

```bash
echo "$payload" | tr '_-' '/+' | base64 -d
```

| 명령어 | 설명 |
| --- | --- |
| `tr '_-' '/+'` | base64url → 표준 base64 문자 치환 (`_`→`/`, `-`→`+`) |
| `base64 -d` | 표준 base64 디코딩 |

디코딩 결과는 Pre-signed URL이다.

### Pre-signed URL 파라미터 분해

디코딩된 URL을 파라미터별로 분해하면 다음과 같다.

```
https://sts.ap-northeast-2.amazonaws.com/
  ?Action=GetCallerIdentity
  &Version=2011-06-15
  &X-Amz-Algorithm=AWS4-HMAC-SHA256
  &X-Amz-Credential=AKIA...%2F20260409%2Fap-northeast-2%2Fsts%2Faws4_request
  &X-Amz-Date=20260409T122351Z
  &X-Amz-Expires=60
  &X-Amz-SignedHeaders=host%3Bx-k8s-aws-id
  &X-Amz-Signature=4c4a5aaa...
```

| 파라미터 | 의미 |
| --- | --- |
| `Action=GetCallerIdentity` | STS `GetCallerIdentity` API를 호출하겠다는 의미 |
| `X-Amz-Algorithm` | 서명에 사용된 알고리즘 (AWS4-HMAC-SHA256) |
| `X-Amz-Credential` | Access Key ID + Credential Scope. `AKIA...`는 IAM User 영구키, `aws4_request`는 SigV4 서명임을 표시 |
| `X-Amz-Date` | 서명 생성 시각 |
| `X-Amz-Expires=60` | 이 URL은 생성 후 **60초**만 유효 |
| `X-Amz-SignedHeaders` | 서명에 포함된 헤더. `host`와 `x-k8s-aws-id` |
| `X-Amz-Signature` | **최종 서명값**. 이것이 곧 인증의 핵심이다 |

이것이 바로 Pre-signed URL이다. "인증이 완료된 요청서" 자체로, 이 URL을 가진 누구든 STS에 제출하면 해당 IAM 주체의 identity를 확인할 수 있다. 단, 60초 후에는 만료된다.

> 이 URL을 받아서 어떻게 검증하는가? 4단계에서 aws-iam-authenticator가 이 URL로 STS에 실제 HTTP GET 요청을 보내서 검증한다.

<br>

## EKS 토큰 vs JWT

토큰을 `.`으로 분리하면 EKS 토큰이 JWT와 다른 구조임을 알 수 있다.

| | **JWT** | **EKS 토큰** |
| --- | --- | --- |
| **구조** | `header.payload.signature` (3파트) | `k8s-aws-v1.payload` (2파트) |
| **서명 위치** | 토큰의 세 번째 파트 | Pre-signed URL **내부** (`X-Amz-Signature` 파라미터) |
| **검증 방식** | 수신자가 서명을 **로컬에서** 검증 | aws-iam-authenticator가 Pre-signed URL로 STS에 **원격 검증** 요청 |

```text
JWT:        header.payload.signature     ← 3파트, 로컬 검증
EKS 토큰:   k8s-aws-v1.payload           ← 2파트, 서명은 URL 안에 내장 → 원격 검증(STS)
```

EKS 토큰의 서명은 토큰 바깥이 아닌 Pre-signed URL 안에 내장되어 있다. payload를 디코딩하면 `X-Amz-Signature=4c4a5aaa...`가 URL 안에 들어 있는 것을 확인할 수 있다. 따라서 `IFS='.' read`로 split했을 때 signature 변수가 비어 있는 것이 **정상**이다.

<br>

# 2. Bearer Token 전송 -- kubectl → EKS API

kubectl이 EKS API 서버에 보내는 실제 요청을 확인해 보자.

## kubectl -v=10 로그

```bash
kubectl get node -v=10
```

<details markdown="1">
<summary><b>전체 출력</b></summary>

```
I0409 21:30:52.139662 loader.go:405] Config loaded from file:  /Users/eraser/.kube/config
...
I0409 21:30:52.151600 helper.go:113] "Request Body" body=""
I0409 21:30:52.152851 round_trippers.go:527] "Request" curlCommand=<
        curl -v -XGET  -H "Accept: application/json;as=Table;v=v1;g=meta.k8s.io,..." -H "User-Agent: kubectl/v1.35.2 (darwin/arm64) kubernetes/fdc9d74" 'https://C0D990...gr7.ap-northeast-2.eks.amazonaws.com/api/v1/nodes?limit=500'
 >
I0409 21:30:52.902063 round_trippers.go:547] "HTTP Trace: DNS Lookup resolved" host="C0D990...gr7.ap-northeast-2.eks.amazonaws.com" address=[{"IP":"3.35.115.125"},{"IP":"54.116.134.20"}]
I0409 21:30:52.909575 round_trippers.go:562] "HTTP Trace: Dial succeed" network="tcp" address="3.35.115.125:443"
I0409 21:30:52.954101 round_trippers.go:632] "Response" verb="GET" url="https://C0D990...gr7.ap-northeast-2.eks.amazonaws.com/api/v1/nodes?limit=500" status="200 OK"
 > milliseconds=801 dnsLookupMilliseconds=11 dialMilliseconds=7 tlsHandshakeMilliseconds=13 serverProcessingMilliseconds=29
...
NAME                                                STATUS   ROLES    AGE   VERSION
ip-192-168-15-163.ap-northeast-2.compute.internal   Ready    <none>   27m   v1.35.2-eks-f69f56f
ip-192-168-17-28.ap-northeast-2.compute.internal    Ready    <none>   27m   v1.35.2-eks-f69f56f
```

</details>

핵심 로그만 발췌하면 다음과 같다.

```
I0409 21:30:52.152851 round_trippers.go:527] "Request" curlCommand=<
    curl -v -XGET
      -H "Accept: application/json;as=Table;v=v1;g=meta.k8s.io,..."
      -H "User-Agent: kubectl/v1.35.2 (darwin/arm64) kubernetes/fdc9d74"
      'https://C0D990...gr7.ap-northeast-2.eks.amazonaws.com/api/v1/nodes?limit=500'
 >
I0409 21:30:52.954101 round_trippers.go:632] "Response" verb="GET"
    status="200 OK" milliseconds=801
```

kubectl이 출력하는 curl 명령어에는 `Authorization` 헤더가 **의도적으로 제외**되어 있다. 보안 민감 정보를 일반 로그 레벨에서 마스킹하는 것이다. 실제로는 `Authorization: Bearer k8s-aws-v1.<base64>` 헤더가 포함된다.

<br>

## curl로 직접 요청

kubectl을 거치지 않고, 토큰을 직접 사용하여 API를 호출해 보자. `-v` 옵션으로 헤더를 확인한다.

```bash
TOKEN_DATA=$(aws eks get-token --cluster-name myeks | jq -r '.status.token')

curl -k -v -XGET \
  -H "Authorization: Bearer $TOKEN_DATA" \
  -H "Accept: application/json" \
  'https://<EKS-ENDPOINT>/api/v1/nodes?limit=500'
```

<details markdown="1">
<summary><b>전체 출력</b></summary>

```
* Host C0D990...gr7.ap-northeast-2.eks.amazonaws.com:443 was resolved.
* IPv4: 54.116.134.20, 3.35.115.125
*   Trying 54.116.134.20:443...
* Connected to C0D990...gr7.ap-northeast-2.eks.amazonaws.com port 443
* SSL connection using TLSv1.3 / AEAD-CHACHA20-POLY1305-SHA256
* Server certificate:
*  subject: CN=kube-apiserver
*  issuer: CN=kubernetes
* [HTTP/2] [1] [authorization: Bearer k8s-aws-v1.aHR0cHM6Ly9zdHMu...]
> GET /api/v1/nodes?limit=500 HTTP/2
> Host: C0D990...gr7.ap-northeast-2.eks.amazonaws.com
> User-Agent: curl/8.7.1
> Authorization: Bearer k8s-aws-v1.aHR0cHM6Ly9zdHMu...
> Accept: application/json
>
< HTTP/2 200
...
```

</details>

핵심은 curl의 verbose 출력에서 `Authorization: Bearer k8s-aws-v1.<base64>` 헤더가 그대로 노출되는 것을 확인할 수 있다는 점이다. kubectl과 달리 마스킹하지 않는다.

```bash
curl -k -s -XGET \
  -H "Authorization: Bearer $TOKEN_DATA" \
  -H "Accept: application/json" \
  'https://<EKS-ENDPOINT>/api/v1/nodes?limit=500' | jq '.items[].metadata.name'
```

```json
"ip-192-168-15-163.ap-northeast-2.compute.internal"
"ip-192-168-17-28.ap-northeast-2.compute.internal"
```

> 토큰의 유효 기간은 약 15분이다. 15분 이후에는 토큰을 재발급해야 한다.

<br>

# 3. TokenReview -- EKS API → aws-iam-authenticator

## TokenReview 오브젝트

TokenReview는 K8s `authentication.k8s.io/v1` API 그룹에 속하는 리소스다. Bearer Token을 제출하면, 해당 토큰이 유효한지, 어떤 사용자의 것인지 인증해 주는 요청 객체다.

```bash
kubectl api-resources | grep authentication
```

```
selfsubjectreviews    authentication.k8s.io/v1   false   SelfSubjectReview
tokenreviews          authentication.k8s.io/v1   false   TokenReview
```

```bash
kubectl explain tokenreviews
```

```
DESCRIPTION:
  TokenReview attempts to authenticate a token to a known user. Note:
  TokenReview requests may be cached by the webhook token authenticator
  plugin in the kube-apiserver.
```

TokenReview는 **K8s의 범용 토큰 검증 인터페이스**다.

- **요청(`spec`)**: `spec.token`에 검증할 토큰을 담는다
- **응답(`status`)**: `status.authenticated`(true/false), `status.user`(username, uid, groups, extra)를 돌려준다

K8s에서 TokenReview가 사용되는 주요 장면은 다음과 같다.

| 사용처 | 설명 |
| --- | --- |
| **Webhook Token Authentication** | API 서버가 외부 webhook(예: aws-iam-authenticator)에 토큰 검증을 위임. **EKS가 이 방식 사용** |
| **API Server TokenReview API** | 클러스터 내부 컴포넌트가 `POST /apis/authentication.k8s.io/v1/tokenreviews`를 호출하여 SA 토큰이나 OIDC 토큰 검증 |
| **Service Account Token Verification** | kubelet이 Pod에 마운트된 SA 토큰 유효성 확인 |

K8s API 서버 자체는 `k8s-aws-v1.` 토큰을 이해하지 못한다. "이 토큰 검증해줘"라고 webhook에 넘기기만 할 뿐, AWS 서명을 직접 검증하지 않는다.

> **참고: K8s 인증 방법들**
>
> K8s는 다양한 인증 방법을 지원한다.
> - **X.509 Client Certificates**: 인증서 기반. 일반적인 kubeadm 클러스터에서 kubectl 인증에 사용
> - **Bootstrap Tokens**: 노드가 클러스터에 처음 join할 때 사용하는 임시 토큰
> - **Service Account Tokens**: Pod 내부에서 K8s API를 호출할 때 사용
> - **Static Token File**: API 서버 시작 시 파일로 토큰 목록을 제공. 변경 시 재시작 필요하여 프로덕션에서 비권장
> - **Webhook Token Authentication**: 외부 서비스에 토큰 검증을 위임. **EKS가 사용하는 방식**

<br>

## TokenReview 직접 요청

토큰을 발급받아 TokenReview 요청을 직접 만들어 보자.

```bash
TOKEN_DATA=$(aws eks get-token --cluster-name myeks | jq -r '.status.token')

cat > token-review.yaml << EOF
apiVersion: authentication.k8s.io/v1
kind: TokenReview
metadata:
  name: mytoken
spec:
  token: ${TOKEN_DATA}
EOF
```

```bash
kubectl create -f token-review.yaml
```

```
tokenreview.authentication.k8s.io/mytoken created
```

<br>

## TokenReview 응답 분석

`-v=9` 옵션으로 응답 본문을 직접 확인해 보자.

```bash
kubectl create -f token-review.yaml -v=9 2>&1 | grep "Response Body"
```

<details markdown="1">
<summary><b>전체 Response Body</b></summary>

```json
{
  "kind": "TokenReview",
  "apiVersion": "authentication.k8s.io/v1",
  "metadata": {
    "name": "mytoken",
    "managedFields": [...]
  },
  "spec": {
    "token": "k8s-aws-v1.aHR0cHM6Ly9zdHMu..."
  },
  "status": {
    "authenticated": true,
    "user": {
      "username": "arn:aws:iam::123456789012:user/admin",
      "uid": "aws-iam-authenticator:123456789012:AIDA...",
      "groups": [
        "system:authenticated"
      ],
      "extra": {
        "accessKeyId": ["AKIA..."],
        "arn": ["arn:aws:iam::123456789012:user/admin"],
        "canonicalArn": ["arn:aws:iam::123456789012:user/admin"],
        "principalId": ["AIDA..."],
        "sessionName": [""],
        "sigs.k8s.io/aws-iam-authenticator/principalId": ["AIDA..."]
      }
    },
    "audiences": [
      "https://kubernetes.default.svc"
    ]
  }
}
```

</details>

핵심 필드를 정리하면 다음과 같다.

| 필드 | 값 | 의미 |
| --- | --- | --- |
| `authenticated` | `true` | 토큰이 유효하고 인증에 성공 |
| `username` | `arn:aws:iam::123456789012:user/admin` | IAM ARN이 그대로 K8s username으로 사용 |
| `uid` | `aws-iam-authenticator:123456789012:AIDA...` | authenticator가 부여한 고유 ID |
| `groups` | `["system:authenticated"]` | K8s 기본 인증 그룹 |
| `extra.accessKeyId` | `AKIA...` | 토큰 서명에 사용된 Access Key ID |
| `extra.principalId` | `AIDA...` | IAM User의 고유 ID |
| `audiences` | `["https://kubernetes.default.svc"]` | 토큰의 대상 audience |

`groups`에 `system:authenticated`만 표시되고 `system:masters`는 보이지 않는다. 이는 EKS를 생성한 IAM principal에게 자동 부여되는 `system:masters` 권한이 **표시되는 설정에 나타나지 않기** 때문이다. [AWS 공식 문서](https://docs.aws.amazon.com/eks/latest/userguide/cluster-auth.html)에 따르면, 클러스터를 생성한 IAM principal은 RBAC 구성에서 `system:masters` 권한이 자동으로 부여되지만, 이는 내부적으로 처리되어 TokenReview 응답의 groups에는 포함되지 않는다.

<br>

# 4. STS 검증 -- aws-iam-authenticator → STS

3단계에서 API 서버가 aws-iam-authenticator webhook에 TokenReview를 전달하면, authenticator는 토큰에서 Pre-signed URL을 복원하여 STS `GetCallerIdentity`를 호출한다. 이 단계는 EKS 컨트롤 플레인 내부에서 일어나므로 직접 관찰할 수 없지만, **CloudTrail**과 **CloudWatch**에서 간접적으로 확인할 수 있다.

<br>

## CloudTrail: STS 호출 기록

### CloudTrail이란

AWS CloudTrail은 AWS 계정에서 일어나는 **모든 API 호출을 기록하는 감사(Audit) 로그 서비스**다. 누가, 언제, 어디서, 어떤 AWS API를 호출했는지 전부 기록한다.

### 무엇을 보는 것인가

`sts.amazonaws.com` + `GetCallerIdentity`로 필터링하면 보이는 것은, **사용자(kubectl)가 STS를 직접 호출한 기록이 아니다**. `aws eks get-token`은 STS에 실제 HTTP 호출을 하지 않는다(디버그 로그에서 확인한 것처럼 네트워크 통신 0회). 실제로 보이는 것은 **aws-iam-authenticator → STS** 호출이다.

```text
사용자 (kubectl)
  → EKS API 서버 (Bearer Token 전달)
    → aws-iam-authenticator (TokenReview)
      → STS GetCallerIdentity 호출  ← 이게 CloudTrail에 기록된다
```

![CloudTrail에서 GetCallerIdentity 이벤트 확인]({{site.url}}/assets/images/eks-cloudtrail-getcalleridentity.png){: .align-center}

<center><sup>CloudTrail에서 GetCallerIdentity 이벤트 확인</sup></center>

### CloudTrail 이벤트 분석

```json
{
    "userIdentity": {
        "type": "IAMUser",
        "principalId": "AIDA...",
        "arn": "arn:aws:iam::123456789012:user/admin",
        "accountId": "123456789012",
        "accessKeyId": "AKIA...",
        "userName": "admin"
    },
    "eventTime": "2026-04-09T12:36:44Z",
    "eventSource": "sts.amazonaws.com",
    "eventName": "GetCallerIdentity",
    "awsRegion": "ap-northeast-2",
    "sourceIPAddress": "3.39.18.244",
    "userAgent": "Go-http-client/1.1",
    "additionalEventData": {
        "RequestDetails": {
            "endpointType": "regional",
            "awsServingRegion": "ap-northeast-2"
        }
    },
    "tlsDetails": {
        "tlsVersion": "TLSv1.3",
        "clientProvidedHostHeader": "sts.ap-northeast-2.amazonaws.com"
    }
}
```

| 필드 | 의미 |
| --- | --- |
| `userAgent: "Go-http-client/1.1"` | aws-iam-authenticator(Go로 작성됨)가 호출한 것 |
| `sourceIPAddress: "3.39.18.244"` | **EKS 컨트롤 플레인의 IP**이다. 사용자의 IP가 아니다 |
| `userIdentity.arn` | 토큰의 주인, 즉 인증 대상 IAM 주체 |
| `endpointType: "regional"` | 리전별 STS 엔드포인트가 사용되었다 |
| `clientProvidedHostHeader` | `sts.ap-northeast-2.amazonaws.com` -- debug 로그에서 resolve한 엔드포인트와 일치 |

`sourceIPAddress`가 사용자의 IP가 아닌 EKS 컨트롤 플레인의 IP라는 점이 핵심이다. STS `GetCallerIdentity`를 호출하는 것은 사용자(kubectl)가 아니라 **aws-iam-authenticator**이기 때문이다.

### 왜 CloudTrail을 보는가

1. **인증 감사**: 누가 언제 EKS 클러스터에 접근했는지 확인
2. **트러블슈팅**: 인증 실패 시 STS 호출이 실제로 일어났는지, 어떤 IAM 주체로 시도했는지 확인
3. **STS 엔드포인트 확인**: 글로벌 vs 리전별 어느 쪽으로 호출되는지 확인

<br>

## CloudWatch: authenticator 로그

### CloudWatch란

CloudWatch는 로그 수집 + 메트릭 모니터링 서비스다.

- **CloudWatch Logs**: 애플리케이션/서비스가 출력하는 텍스트 로그를 수집, 저장, 검색
- **CloudWatch Metrics**: CPU, 메모리, 네트워크 등 수치 데이터를 시계열로 저장
- **CloudWatch Alarms**: 메트릭이 임계값을 넘으면 알림

### EKS 컨트롤 플레인 로그

EKS 컨트롤 플레인 로깅을 활성화했다면, `/aws/eks/<클러스터명>/cluster` 로그 그룹에서 다음 로그 스트림을 볼 수 있다.

| 로그 스트림 | 내용 |
| --- | --- |
| **`authenticator`** | aws-iam-authenticator의 동작 로그 (인증 성공/실패) |
| `kube-apiserver` | K8s API 서버 로그 (인가 모드, webhook 설정 등) |
| `kube-controller-manager` | 컨트롤러 매니저 로그 |
| `kube-scheduler` | 스케줄러 로그 |
| `cloud-controller-manager` | AWS 클라우드 컨트롤러 로그 |

![CloudWatch authenticator 로그]({{site.url}}/assets/images/eks-cloudwatch-authenticator-log.png){: .align-center}

<center><sup>CloudWatch에서 authenticator 로그 스트림 확인</sup></center>

`authenticator` 스트림에서 주로 봐야 할 것은 다음과 같다.

| 필드 | 의미 |
| --- | --- |
| `msg="access granted"` | 인증 성공. 이 사용자의 토큰이 STS 검증을 통과했다 |
| `username` | 인증된 K8s username (IAM ARN) |
| `uid` | aws-iam-authenticator가 부여한 고유 ID |
| `stsendpoint` | 토큰 검증에 사용된 STS 엔드포인트 |

<br>

## Logs Insight: STS 엔드포인트 확인

CloudWatch Logs Insight를 사용하면 authenticator가 어떤 STS 엔드포인트를 사용했는지 확인할 수 있다. 글로벌 엔드포인트(`sts.amazonaws.com`)를 사용하면 레이턴시 이슈가 생길 수 있으므로, 리전별 엔드포인트를 사용하는지 확인하는 것이 [베스트 프랙티스](https://docs.aws.amazon.com/eks/latest/best-practices/identity-and-access-management.html)다.

```
fields @timestamp, @message, @logStream, @log, stsendpoint
| filter @logStream like /authenticator/
| filter @message like /stsendpoint/
| sort @timestamp desc
| limit 10000
```

![Logs Insight 쿼리 결과]({{site.url}}/assets/images/eks-cloudwatch-logs-insight-stsendpoint.png){: .align-center}

<center><sup>Logs Insight에서 STS 엔드포인트 확인</sup></center>

<br>

## CloudTrail vs CloudWatch

같은 인증 이벤트를 두 곳에서 교차 확인할 수 있다. **같은 사건의 양면**이다.

```text
kubectl → EKS API → aws-iam-authenticator → STS GetCallerIdentity
                     │                        │
                     ▼                        ▼
              CloudWatch Logs           CloudTrail
              (authenticator 스트림)     (STS 이벤트)
              "access granted,          "GetCallerIdentity,
               username=...,             userAgent=Go-http-client,
               stsendpoint=..."          sourceIP=3.39.18.244"
```

| | **CloudTrail** | **CloudWatch** |
| --- | --- | --- |
| **비유** | CCTV (누가 뭘 했는지 기록) | 대시보드 + 알람 (지금 상태가 어떤지 모니터링) |
| **기록 대상** | AWS API 호출 (누가, 언제, 어떤 API) | 로그, 메트릭, 알람 (애플리케이션/서비스 출력) |
| **EKS 인증에서 보는 것** | STS에 실제 호출이 왔는지, 어떤 IAM 주체인지, sourceIP | EKS 인증 결과(성공/실패), STS 엔드포인트, K8s username |
| **대표 질문** | "누가 S3 버킷을 삭제했지?" | "지금 CPU 사용률이 몇 %야?" |

트러블슈팅 시 둘을 교차 확인하면 인증 실패의 원인을 빠르게 파악할 수 있다.

<br>

# (참고) AWS ID 접두사

실습 과정에서 등장하는 AWS ID의 접두사는 리소스 유형을 식별하는 데 유용하다.

| 접두사 | 대상 | 설명 |
| --- | --- | --- |
| **AKIA** | IAM Access Key | **Permanent.** IAM User의 고정 액세스 키. 직접 삭제하기 전까지 유지 |
| **ASIA** | Temporary Access Key | **Session.** `AssumeRole`이나 STS를 통해 발급된 임시 키. 만료 시간 존재 |
| **AIDA** | IAM User ID | IAM User 자체를 식별하는 고유 ID |
| **AROA** | IAM Role ID | IAM Role을 식별하는 내부 ID |
| **ANPA** | IAM Managed Policy | AWS 관리형 또는 고객 관리형 정책의 고유 ID |
| **ANVA** | IAM Group ID | IAM 사용자 그룹을 식별하는 ID |

TokenReview 응답의 `accessKeyId`가 `AKIA...`로 시작하면 IAM User의 영구 키로 서명한 토큰이고, `ASIA...`로 시작하면 임시 자격증명(예: AssumeRole 결과)으로 서명한 토큰이다.

<br>

# 정리

EKS 인증 4단계를 실습으로 하나씩 확인했다.

| 단계 | 내용 | 확인 방법 |
| --- | --- | --- |
| **[1] 토큰 생성** | SigV4 서명 4단계 → Pre-signed URL → `k8s-aws-v1.<base64>` | `aws eks get-token --debug`, 토큰 디코딩, Pre-signed URL 파라미터 분해 |
| **[2] Bearer Token 전송** | kubectl이 Authorization 헤더에 토큰을 실어 전송 | `kubectl -v=10`, `curl -v`로 직접 호출 |
| **[3] TokenReview** | API 서버가 webhook에 토큰 검증 위임 | `kubectl create -f token-review.yaml -v=9` |
| **[4] STS 검증** | authenticator가 STS `GetCallerIdentity` 호출 | CloudTrail + CloudWatch authenticator 로그 |

인증이 완료되면 "이 요청을 보낸 사람은 `arn:aws:iam::123456789012:user/admin`이다"라는 것이 확인된다. 이 IAM identity를 K8s username/group으로 매핑하고, 해당 주체가 요청한 동작을 할 수 있는지 확인하는 것이 인가(AuthZ) 단계다. 인가에 대해서는 다음 글에서 다룬다.

<br>

# 참고 자료

- [aws-iam-authenticator GitHub](https://github.com/kubernetes-sigs/aws-iam-authenticator): "uses the AWS STS `GetCallerIdentity` API as the identity verification mechanism" 명시
- [AWS 공식 문서 - EKS Best Practices (Identity and Access Management)](https://docs.aws.amazon.com/eks/latest/best-practices/identity-and-access-management.html): STS 엔드포인트 확인용 Logs Insight 쿼리 포함
- [AWS STS GetCallerIdentity API 공식 문서](https://docs.aws.amazon.com/STS/latest/APIReference/API_GetCallerIdentity.html): 권한 불필요 특성 설명
- [Kubernetes 공식 문서 - Webhook Token Authentication](https://kubernetes.io/docs/reference/access-authn-authz/authentication/#webhook-token-authentication): TokenReview 스펙
- [Kubernetes 공식 문서 - ExecCredential](https://kubernetes.io/docs/reference/config-api/client-authentication.v1beta1/): kubeconfig exec 응답 형식
- [AWS Signature Version 4 서명 프로세스](https://docs.aws.amazon.com/general/latest/gr/signature-version-4.html): SigV4 서명 4단계 공식 문서

<br>
