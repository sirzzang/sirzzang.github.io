---
title:  "[EKS] EKS: Public-Public EKS 클러스터 - 3. kubeconfig와 EKS API 서버 인증"
excerpt: "kubeconfig를 설정하고, EKS API 서버가 IAM 자격증명을 인증하는 구조를 확인해보자."
categories:
  - Kubernetes
toc: true
hidden: true
header:
  teaser: /assets/images/blog-Dev.jpg
tags:
  - Kubernetes
  - AWS
  - EKS
  - STS
  - IAM
  - kubeconfig
  - aws-iam-authenticator
  - AWS-EKS-Workshop-Study
  - AWS-EKS-Workshop-Study-Week-1

---

*[서종호(가시다)](https://www.linkedin.com/in/gasida99/)님의 AWS EKS Workshop Study(AEWS) 1주차 학습 내용을 기반으로 합니다.*

<br>

# TL;DR

이번 글에서는 **kubeconfig 설정 과정과 그 이면의 EKS API 서버 인증 구조**를 다룬다.

- **kubeconfig 설정**: `aws eks update-kubeconfig` 한 줄로 완료. 클러스터 엔드포인트, CA 인증서, 토큰 발급 명령어가 자동으로 등록됨
- **EKS API 서버 인증**: K8s API 서버(AWS 외부 시스템)가 IAM identity를 확인해야 하는 문제를 STS `GetCallerIdentity` pre-signed URL로 해결
- **토큰 구조**: `aws eks get-token`이 STS pre-signed URL을 base64 인코딩하여 `k8s-aws-v1.<base64>` 형태의 Bearer Token으로 변환
- **kubeconfig exec**: 15분마다 만료되는 토큰을 만료 시 자동으로 갱신하는 메커니즘

<br>

# kubeconfig 설정

[이전 글]({% post_url 2026-03-12-Kubernetes-EKS-01-01-02-Installation-Result %})에서 Terraform으로 EKS 클러스터를 배포했다. 이제 `kubectl`로 클러스터에 접근하기 위한 자격증명을 설정한다.

```bash
aws eks update-kubeconfig --region ap-northeast-2 --name myeks
```

```
Added new context arn:aws:eks:ap-northeast-2:988608581192:cluster/myeks to /Users/eraser/.kube/config
```

context 이름이 ARN 전체로 들어가므로, 편의를 위해 이름을 변경한다.

```bash
kubectl config rename-context $(kubectl config current-context) myeks
```

```
Context "arn:aws:eks:ap-northeast-2:988608581192:cluster/myeks" renamed to "myeks".
```

설정 후 EKS 클러스터에 정상적으로 접근되는 것을 확인할 수 있다.

```bash
kubectl get nodes
```

```
NAME                                              STATUS   ROLES    AGE   VERSION
ip-192-168-2-21.ap-northeast-2.compute.internal   Ready    <none>   13h   v1.34.4-eks-f69f56f
ip-192-168-3-96.ap-northeast-2.compute.internal   Ready    <none>   13h   v1.34.4-eks-f69f56f
```

설정 자체는 간단하다. 하지만 이 한 줄 뒤에 숨어 있는 인증 구조는 상당히 복잡하다.

<br>

## kubeconfig 변경 내용

`aws eks update-kubeconfig`가 `~/.kube/config`에 무엇을 추가했는지 확인해 보자.

```bash
kubectl config view
```

```yaml
apiVersion: v1
clusters:
- cluster:
    certificate-authority-data: DATA+OMITTED
    server: https://461A1FA334847E0E1B597AF07FF0CCE0.gr7.ap-northeast-2.eks.amazonaws.com
  name: arn:aws:eks:ap-northeast-2:988608581192:cluster/myeks
contexts:
- context:
    cluster: arn:aws:eks:ap-northeast-2:988608581192:cluster/myeks
    user: arn:aws:eks:ap-northeast-2:988608581192:cluster/myeks
  name: arn:aws:eks:ap-northeast-2:988608581192:cluster/myeks
current-context: arn:aws:eks:ap-northeast-2:988608581192:cluster/myeks
kind: Config
users:
- name: arn:aws:eks:ap-northeast-2:988608581192:cluster/myeks
  user:
    exec:
      apiVersion: client.authentication.k8s.io/v1beta1
      args:
      - --region
      - ap-northeast-2
      - eks
      - get-token
      - --cluster-name
      - myeks
      - --output
      - json
      command: aws
      env: null
      interactiveMode: IfAvailable
      provideClusterInfo: false
```

kubeconfig는 [cluster, user, context]({% post_url 2026-02-16-Kubernetes-Kubeconfig-01 %}#정의) 세 가지로 구성된다. 각 섹션에 추가된 내용을 정리하면 다음과 같다.

| 섹션 | 추가된 내용 | 설명 |
| --- | --- | --- |
| **clusters** | `server`, `certificate-authority-data` | EKS API 서버 엔드포인트 URL과 CA 인증서 |
| **users** | `exec` 블록 | `aws eks get-token` 명령어로 인증 토큰을 자동 발급하는 설정 |
| **contexts** | cluster + user 연결 | 위의 cluster와 user를 묶어서 하나의 context로 등록 |

여기서 `users` 섹션이 핵심이다. 일반적인 kubeconfig에서는 `client-certificate-data`나 `token` 같은 **정적 인증 정보**가 들어가는데, EKS kubeconfig에서는 `exec` 블록이 들어가 있다. 이것은 **kubectl이 매 요청마다 외부 명령어를 실행해서 인증 토큰을 동적으로 받아오겠다**는 뜻이다.

`exec` 블록의 `command`와 `args`를 이어 붙이면 다음과 같다. `command`에 실행할 바이너리를, `args`에 인자 목록을 넣어 `command args[0] args[1] ...`을 실행하는 구조로, [Kubernetes Pod spec의 `command`/`args`]({% post_url 2026-03-06-CS-Container-CMD-Entrypoint %}#command와-args)와 형태가 유사하지만 의미는 다르다. Pod spec의 `command`/`args`는 OCI 이미지의 ENTRYPOINT/CMD를 오버라이드하는 배열이고, 이미지 스펙과의 상호작용(생략 시 기본값 사용 등)이 있다. kubeconfig exec에는 그런 개념 없이 단순히 외부 명령어를 실행한다.

```bash
aws --region ap-northeast-2 eks get-token --cluster-name myeks --output json
```

kubectl이 EKS API 서버에 요청을 보낼 때마다 이 명령어를 실행해서 토큰을 받아오는 것이다. 이 토큰이 무엇이고 왜 이런 구조가 필요한지 이해하려면, EKS API 서버의 인증 방식을 파고들어야 한다.

<br>

# EKS API 서버 인증

![eks-api-auth-overview]({{site.url}}/assets/images/eks-api-auth-overview.png){: .align-center}

<center><sup>EKS API 서버 인증 구조 개요</sup></center>

<br>

## 전제: EKS의 "사용자" 개념

EKS 클러스터에 접근하려면 "내가 누구인지"를 클러스터에 알려야 한다. AWS 세계에서 "사용자"에 해당하는 것은 두 가지다.

| AWS 주체 | 설명 |
| --- | --- |
| **IAM User** | 장기 자격증명(Access Key ID + Secret Access Key)을 가진 사용자. 사람이 직접 사용 |
| **IAM Role** | 임시 자격증명을 발급받아 사용하는 역할. EC2 인스턴스, Lambda, 다른 계정 사용자 등이 "이 역할을 맡아서(assume)" 사용 |

EKS에서의 사용자 인증은 **IAM User 또는 IAM Role을 기준으로** 이루어진다. K8s 자체의 ServiceAccount와는 별개로, EKS API 서버에 접근하는 주체는 반드시 IAM identity(User 또는 Role)여야 한다. [이전 글]({% post_url 2026-03-12-Kubernetes-EKS-01-01-02-Installation-Result %}#iam-액세스-항목)의 IAM 액세스 항목에서 확인한 것처럼, EKS Access Entry에 등록된 IAM 주체만 클러스터에 접근할 수 있다.

<br>

## 문제 정의

### AWS API 인증의 기본 구조

AWS의 모든 API 호출(S3에 파일 업로드, EC2 인스턴스 생성 등)에는 **"이 요청을 보낸 사람이 누구인가"를 증명하는 과정**이 필요하다. 이것을 처리하는 것이 IAM이고, 증명 방식이 **Signature V4 서명**이다.

동작 방식은 이렇다.

1. 클라이언트가 API 요청을 보낼 때, 자신의 **Secret Access Key**로 요청 내용에 대한 서명을 만들어서 함께 보냄
2. AWS 서비스가 요청을 받으면, IAM의 **내부 서명 검증 시스템**에 서명을 넘겨서 검증 요청
3. IAM이 해당 Access Key ID에 대응하는 Secret Access Key를 내부 키 저장소에서 찾아 서명을 재계산하고, 일치하면 "이 요청은 IAM User `admin`이 보낸 것이 맞다"고 응답

핵심은, **AWS 내부 서비스(S3, EC2 등)는 IAM의 서명 검증 시스템에 직접 접근할 수 있다**는 점이다. 같은 AWS 인프라 안에 있기 때문에 가능한 것이다.

### EKS의 문제

EKS가 풀어야 하는 문제는 이렇다.

> **Kubernetes API 서버(= AWS 서비스가 아닌 것)가, 클라이언트의 IAM identity를 알아내야 한다.**

Kubernetes API 서버는 **K8s 오픈소스 소프트웨어**이지, S3나 EC2 같은 AWS 내부 서비스가 아니다. IAM의 서명 검증 시스템은 비공개이고 AWS 내부 서비스만 접근할 수 있다. 외부에 "이 서명 검증해줘"라는 공개 API는 없다.

즉, 일반 AWS 서비스가 하는 것처럼 "서명을 받아서 IAM에 검증을 요청"하는 방법을 EKS API 서버는 쓸 수 없다. **외부 시스템이 IAM identity를 확인할 수 있는 다른 방법**을 찾아야 했다.

<br>

## STS GetCallerIdentity

EKS가 선택한 방법은 **STS(Security Token Service)의 `GetCallerIdentity` API**를 이용하는 것이다.

### STS란

STS는 AWS의 **임시 보안 자격증명 발급 서비스**다. IAM User의 장기 Access Key 대신 짧은 유효기간의 임시 토큰을 발급해 주는 서비스로, `GetCallerIdentity`, `AssumeRole`, `GetSessionToken` 같은 API를 제공한다.

| 서비스 | 하는 일 |
| --- | --- |
| **IAM** | 사용자/역할/정책 관리, API 요청 시 Signature V4 서명 검증 |
| **STS** | 임시 자격증명 발급, `GetCallerIdentity`, `AssumeRole` 등 |
| **Cognito** | 웹/모바일 사용자 인증, federation |
| **SSO (IAM Identity Center)** | 중앙 집중식 SSO 관리 |

<br>

### 왜 STS인가

AWS의 인증 관련 서비스 중에서, 외부 시스템이 "이 자격증명이 누구의 것인지" 물어볼 수 있는 서비스는 **STS가 유일**하다.

| 서비스 | 외부에서 identity 확인 가능? | 이유 |
| --- | --- | --- |
| **Cognito** | X | 웹/모바일 사용자 인증용. IAM identity 확인 API 없음 |
| **SSO (IAM Identity Center)** | X | 중앙 집중식 로그인 관리. IAM 자격증명 확인 API 없음 |
| **IAM** | X | 서명 검증 시스템이 **비공개**. 외부에서 접근 가능한 공개 API 없음 |
| **STS** | O | `GetCallerIdentity`가 서명된 요청을 받으면 "누구인지" 반환 |

<br>

### 왜 GetCallerIdentity인가

STS의 여러 API 중에서도 `GetCallerIdentity`가 선택된 이유가 있다. "지금 이 요청을 보내는 사람이 누구인가?"를 반환하는 API로, 현재 자격증명의 Account, ARN, UserID를 반환한다.

| STS API | EKS 인증에 적합한가? | 이유 |
| --- | --- | --- |
| **GetCallerIdentity** | O (유일하게 적합) | 권한 불필요, 부작용 없음, identity만 반환 |
| `AssumeRole` | X | IAM 권한 필요. Trust relationship 필요. 새 임시 자격증명 발급(부작용) |
| `GetSessionToken` | X | IAM 권한 필요. 새 임시 자격증명 발급(부작용). Role 기반 호출 불가 |
| `AssumeRoleWithSAML` | X | SAML assertion 필요. IAM identity 확인 목적이 아님 |
| `AssumeRoleWithWebIdentity` | X | OIDC 토큰 필요. IAM identity 확인 목적이 아님 |
| `DecodeAuthorizationMessage` | X | 에러 메시지 디코딩용. identity 확인 아님 |

`GetCallerIdentity`의 핵심 특성은 다음과 같다.

1. **공개 API**: 누구나 호출 가능 (IAM 내부 검증 시스템과 달리)
2. **IAM 권한 불필요**: 어떤 IAM User/Role이든 호출 가능. [공식 문서](https://docs.aws.amazon.com/STS/latest/APIReference/API_GetCallerIdentity.html)에 따르면, 관리자가 명시적 deny 정책을 붙여도 차단되지 않는다. `GetCallerIdentity`는 IAM 정책 평가 이전 단계에서 동작하기 때문으로, 접근이 거부될 때도 동일한 정보가 반환된다.
    > "No permissions are required to perform this operation. If an administrator attaches a policy to your identity that explicitly denies access to the `sts:GetCallerIdentity` action, you can still perform this operation. Permissions are not required because the same information is returned when access is denied."
    > — [AWS STS API Reference - GetCallerIdentity](https://docs.aws.amazon.com/STS/latest/APIReference/API_GetCallerIdentity.html)
3. **부작용 없음**: 읽기 전용. 새 자격증명을 발급하지 않고, 아무것도 변경하지 않음
4. **정확한 identity 반환**: Account, ARN, UserID를 반환하므로 "이 사람이 누구인지" 정확히 알 수 있음

정리하면 이렇다. **EKS API 서버(= K8s 오픈소스)는 AWS 외부 시스템이고, 외부 시스템이 IAM 자격증명의 주인을 확인할 수 있는 공개 API가 STS `GetCallerIdentity`뿐이었기 때문에 이것을 선택한 것이다.**

<br>

## Pre-signed URL

여기까지는 "EKS API 서버가 STS에 인증을 위임한다"는 결론이다. 그런데 한 가지 문제가 더 있다.

EKS API 서버가 클라이언트를 대신해서 STS `GetCallerIdentity`를 호출하려면, 클라이언트의 **Secret Access Key**가 필요하다. AWS API 호출에는 Signature V4 서명이 필수인데, 서명을 만들려면 Secret Access Key가 있어야 하기 때문이다.

하지만 **API 서버는 클라이언트의 Secret Access Key를 모른다.** 당연히 모르는 게 맞다. Secret Access Key를 API 서버에 넘기는 것은 보안적으로 불가능하다.

해결책은 **클라이언트가 직접 서명해서 보내주는 것**이다. 클라이언트가 자신의 Secret Access Key로 STS `GetCallerIdentity` 요청에 대한 서명을 미리 만들어두고, 그 서명이 포함된 URL을 API 서버에 전달한다. API 서버는 그 URL을 그대로 STS에 보내기만 하면 된다.

이것이 바로 **pre-signed URL** 방식이다.

<br>

### Pre-signed URL의 구조

Pre-signed URL은 **요청을 실제로 보내지 않고, 나중에 이 URL로 요청하면 유효하다는 서명을 쿼리 파라미터에 담아 놓은 URL**이다. 형태를 보면, 서명값과 서명을 만들기 위한 메타데이터가 모두 쿼리 파라미터로 들어간다.

```
https://sts.ap-northeast-2.amazonaws.com/
  ?Action=GetCallerIdentity              # 호출할 API
  &Version=2011-06-15                    # API 버전

  # ── 서명 메타데이터 (STS가 같은 조건으로 재계산하기 위해 필요) ──
  &X-Amz-Algorithm=AWS4-HMAC-SHA256      # 서명 알고리즘
  &X-Amz-Credential=AKIA6MLNJZZE...      # "누가" 서명했는지
       /20260314                          #   서명 날짜
       /ap-northeast-2                    #   리전
       /sts                               #   서비스
       /aws4_request                      #   고정 접미사
  &X-Amz-Date=20260314T033424Z           # 서명 시각
  &X-Amz-Expires=60                      # 유효 기간 (초)
  &X-Amz-SignedHeaders=host;x-k8s-aws-id # 서명에 포함된 헤더 목록

  # ── 최종 서명값 ──
  &X-Amz-Signature=03a54ed27f2e...        # Signature V4로 계산한 서명
```

이 URL은 아직 STS에 요청이 보내지지 않은 상태다. 누군가가 이 URL로 GET 요청을 보내기만 하면, STS가 서명을 검증하고 응답한다.

STS의 검증 과정은 다음과 같다.

1. `X-Amz-Credential`에서 Access Key ID를 꺼냄
2. 내부 키 저장소에서 해당 Secret Access Key를 찾음
3. 나머지 파라미터(Date, SignedHeaders 등)로 **같은 알고리즘을 다시 돌려서** 서명을 재계산
4. 자기가 계산한 서명과 `X-Amz-Signature` 값을 비교
5. 일치하면 "이 서명을 만든 사람은 이 IAM identity다"라고 응답

핵심은, **Secret Access Key는 클라이언트와 STS만 알고 있다**는 점이다. 클라이언트가 서명을 만들고, STS가 같은 키로 서명을 재계산해서 비교한다. API 서버는 중간에서 URL을 전달할 뿐, Secret Access Key를 알 필요가 없다.

> **참고: Signature V4 서명 생성 알고리즘**
>
> 1. **Canonical Request** 생성: HTTP 메서드, URL 경로, 쿼리 파라미터, 헤더를 정규화
> 2. **String to Sign** 생성: 날짜, 리전, 서비스명 + Canonical Request의 해시
> 3. **Signing Key 유도**: Secret Access Key → HMAC(날짜) → HMAC(리전) → HMAC(서비스) → HMAC("aws4_request") — 체인 형태로 키를 유도
> 4. **최종 서명**: Signing Key로 String to Sign을 HMAC-SHA256
>
> 공개된 스펙이므로, 이 알고리즘을 구현하면 누구나 서명을 만들 수 있다.

<br>

## Bearer Token

Pre-signed URL을 EKS API 서버에 전달하는 방식은 **Bearer Token**이다.

K8s API 서버에는 **Webhook Token Authentication**이라는 확장 포인트가 있다. "토큰이 들어오면 이 webhook에 물어봐라"라는 설정으로, EKS는 이 webhook으로 **[aws-iam-authenticator](https://github.com/kubernetes-sigs/aws-iam-authenticator)**를 붙여 놓았다. aws-iam-authenticator는 토큰에서 pre-signed URL을 복원한 뒤 STS에 보내서 IAM identity를 확인하고, 그 결과를 API 서버에 반환하는 역할을 한다.

aws-iam-authenticator가 정의한 토큰 포맷은 `k8s-aws-v1.<base64>` 형태다. pre-signed URL을 base64url 인코딩한 뒤 이 접두사를 붙인 것이다.

토큰 생성 과정을 정리하면 다음과 같다.

1. IAM 자격증명의 Secret Access Key로 Signature V4 서명을 만듦
2. 서명 및 메타데이터를 조합하여 STS `GetCallerIdentity` pre-signed URL을 생성
3. pre-signed URL을 base64url 인코딩
4. `k8s-aws-v1.` 접두사를 붙여 Bearer Token 완성

결과적으로, **외부 사용자가 IAM identity로 EKS API 서버에 인증할 수 있는 유일한 방법은 STS pre-signed URL 기반 Bearer Token**이다. 형태는 `Bearer k8s-aws-v1.<base64>` 이고, 다른 어떤 형태(IAM User 이름, IAM ARN, Access Key ID/Secret Access Key 등)를 Bearer Token으로 보내면 인증에 실패한다. (Pod 내부에서 사용하는 ServiceAccount 토큰(OIDC 기반 projected service account token)은 별개의 인증 경로다.)

<br>

## 처리 흐름

전체 인증 흐름을 정리하면 다음과 같다.

**클라이언트 측:**

1. IAM 자격증명으로 STS `GetCallerIdentity` pre-signed URL 생성
2. pre-signed URL을 base64url 인코딩
3. `k8s-aws-v1.<base64>` 형태의 Bearer Token으로 API 서버에 전달

**API 서버 측 (K8s API 서버 + aws-iam-authenticator webhook):**

1. K8s API 서버가 Bearer Token을 받아 aws-iam-authenticator webhook에 전달
2. aws-iam-authenticator가 `k8s-aws-v1.` 접두사를 제거하고 base64url 디코딩하여 pre-signed URL 복원
3. aws-iam-authenticator가 복원된 URL로 STS에 HTTP GET 요청 (GetCallerIdentity)
4. STS가 서명을 검증하고 IAM identity를 응답
5. aws-iam-authenticator가 identity를 K8s API 서버에 반환하고, API 서버가 RBAC 인가 수행

우아한 구조다. K8s API 서버 자체는 AWS 서명을 이해하지도 검증하지도 않고, webhook으로 인증을 위임할 뿐이다. 실제로 STS와 통신하는 것은 aws-iam-authenticator이고, **URL을 받아서 STS에 전달하는 중개자(proxy) 역할**을 한다. 복잡한 암호학적 검증은 전부 STS가 처리하므로, authenticator 입장에서도 AWS SDK나 Signature V4 로직은 불필요하고 **HTTP GET 하나면 끝**이다.

역할과 책임도 계층적으로 잘 분리되어 있다.

| 계층 | 누가 정한 것인가 |
| --- | --- |
| Bearer Token을 webhook으로 검증 | **K8s** (Webhook Token Authentication 스펙) |
| `k8s-aws-v1.<base64>` 토큰 포맷 | **aws-iam-authenticator** (AWS가 만든 오픈소스) |
| pre-signed URL + Signature V4 | **AWS** (STS/IAM 스펙) |

복잡해 보이지만, 오픈소스 K8s 서버를 AWS IAM 생태계에 통합시키기 위해 구현한 방법에서 배울 게 많다.

<br>

# 토큰 생성

## 도구

기술적으로는 Signature V4 스펙을 따라 직접 서명을 만들고 aws-iam-authenticator가 정의한 포맷대로 토큰을 조립할 수도 있다. 하지만 이 과정을 대신 해주는 도구들이 있다.

| 도구 | 방식 |
| --- | --- |
| `aws eks get-token` (AWS CLI) | 가장 일반적인 공식 도구 |
| **aws-iam-authenticator** | EKS 초기에 사용하던 별도 바이너리. 내부적으로 동일한 일을 함 |
| **AWS SDK (boto3, Go SDK 등)** | 직접 코드로 STS pre-signed URL을 만들어서 토큰 생성 가능 |

모든 도구가 결국 동일하게 **STS `GetCallerIdentity`에 대한 pre-signed URL**을 만든다.

<br>

## aws eks get-token

`aws eks get-token`은 현재 IAM 자격증명을 EKS API 서버가 이해할 수 있는 토큰 형태로 변환하는 명령어다.

1. 현재 AWS CLI에 설정된 IAM 자격증명(User든 Role이든)을 읽어서
2. STS `GetCallerIdentity`에 대한 pre-signed URL을 만들고
3. `k8s-aws-v1.<base64>` 형태의 Kubernetes Bearer Token으로 포장해서 반환

`aws eks` 하위 명령어로만 존재하는 EKS 전용 유틸리티로, IAM 인증 정보를 K8s(EKS) API 서버가 이해할 수 있는 토큰으로 변환해 주는 브릿지 역할이다.

```bash
aws --region ap-northeast-2 eks get-token --cluster-name myeks --output json
```

```json
{
    "kind": "ExecCredential",
    "apiVersion": "client.authentication.k8s.io/v1beta1",
    "spec": {},
    "status": {
        "expirationTimestamp": "2026-03-14T03:15:25Z",
        "token": "k8s-aws-v1.aHR0c..."
    }
}
```

응답 형식은 [`ExecCredential`](https://kubernetes.io/docs/reference/config-api/client-authentication.v1beta1/)이다. kubeconfig의 `exec` 블록으로 실행된 외부 명령이 kubectl에 인증 정보를 돌려줄 때 사용하는 K8s 표준 형식으로, kubectl은 이 응답의 `status`에서 토큰과 만료 정보를 읽는다.

`status.token`에 `k8s-aws-v1.aHR0c...` 형태의 토큰이 나온다. `status.expirationTimestamp`는 이 토큰의 만료 시각으로, kubectl은 이 값을 보고 만료 전까지는 exec 명령을 다시 실행하지 않고 캐시된 토큰을 재사용한다. `--role-arn`을 명시하지 않았으므로, 현재 AWS CLI에 설정된 기본 IAM 자격증명(IAM User의 Access Key)이 그대로 사용된다.

다른 자격증명을 사용할 수도 있다.

```bash
# 다른 IAM User의 프로필로 토큰 발급
AWS_PROFILE=other-user aws eks get-token --cluster-name myeks

# IAM Role로 토큰 발급 (내부적으로 AssumeRole 후 임시 자격증명으로 서명)
aws eks get-token --cluster-name myeks --role-arn arn:aws:iam::123456789012:role/MyEKSRole
```

`--role-arn`을 지정하면 내부적으로 `AssumeRole`을 먼저 수행한 뒤, 그 임시 자격증명으로 STS `GetCallerIdentity` pre-signed URL을 만든다. 결과적으로 토큰에 찍히는 identity는 원래 IAM User가 아니라 해당 Role의 ARN이 된다.

<br>

## 토큰 디코딩

토큰을 디코딩하면 pre-signed URL이 나오는지 직접 확인해 볼 수 있다.

```bash
echo "k8s-aws-v1.aHR0c..." | cut -d. -f2 | tr '_-' '/+' | base64 -d
```

| 명령어 | 설명 |
| --- | --- |
| `cut -d. -f2` | `.`을 구분자로 두 번째 필드(base64 부분)만 추출 |
| `tr '_-' '/+'` | base64url → 표준 base64 문자로 치환 (`_`→`/`, `-`→`+`) |
| `base64 -d` | 표준 base64 디코딩 |

`tr` 치환이 필요한 이유는, 토큰이 **base64url 인코딩**이기 때문이다. 일반 base64는 `+`와 `/`를 쓰는데, URL에서는 이 문자들이 특수 의미를 가지므로 URL-safe 버전에서는 `-`와 `_`로 대체한다. 디코딩하려면 다시 표준 base64 문자로 되돌려야 한다.

디코딩 결과를 살펴 보면, 정확하게 STS `GetCallerIdentity`에 대한 pre-signed URL이 나온다. URL 자체에 AWS Signature V4 서명이 쿼리 파라미터로 포함되어 있다.


```
https://sts.ap-northeast-2.amazonaws.com/
  ?Action=GetCallerIdentity
  &Version=2011-06-15
  &X-Amz-Algorithm=AWS4-HMAC-SHA256
  &X-Amz-Credential=AKIA.../sts/aws4_request
  &X-Amz-Date=...
  &X-Amz-Expires=60
  &X-Amz-SignedHeaders=host;x-k8s-aws-id
  &X-Amz-Signature=d681acb4266cc7ec06d2a1020cf90e08...
```

<br>

## 토큰 유효 기간

Pre-signed URL의 `X-Amz-Expires=60`은 STS가 이 URL에 대한 요청을 수락하는 기간이다. 생성 후 60초가 지나면 STS는 해당 URL의 요청을 거부한다. 그렇다면 토큰도 60초 후에 무효화될까?

아니다. EKS 토큰의 실질적 유효 기간은 **15분**이다. 60초와 15분 사이의 차이는 **캐싱**으로 설명된다.

토큰이 최초로 사용되면, aws-iam-authenticator가 pre-signed URL을 복원해서 STS에 보낸다. 이 STS 호출은 URL이 아직 유효한 60초 이내에 일어난다. STS가 IAM identity를 응답하면, authenticator는 그 **검증 결과를 캐시**한다. 이후 같은 토큰이 다시 들어오면 STS를 재호출하지 않고 캐시된 identity를 사용한다. 따라서 60초가 지나 pre-signed URL 자체가 만료되더라도, 이미 캐시된 토큰은 계속 유효하다. 15분이 지나면 authenticator가 `X-Amz-Date`(서명 시각) 기준으로 토큰 자체를 거부한다.

시간축으로 정리하면 다음과 같다.

| 시간 | 상태 |
| --- | --- |
| **0~60초** | pre-signed URL 유효. 최초 사용 시 authenticator가 STS를 호출하고 결과를 캐시 |
| **60초~15분** | pre-signed URL 만료. authenticator가 캐시된 검증 결과를 사용하므로 토큰은 유효 |
| **15분 이후** | authenticator가 `X-Amz-Date` 기준으로 토큰 거부. 캐시도 무효화 |

kubectl 쪽에서도 캐싱이 있다. `aws eks get-token`이 반환하는 `ExecCredential` 응답에는 `expirationTimestamp`가 포함되어 있고, kubectl은 이 값을 보고 만료 전까지는 exec 명령을 다시 실행하지 않는다. 즉 두 레벨의 캐싱(kubectl의 ExecCredential 캐싱 + authenticator의 검증 결과 캐싱)이 조합되어 동작한다.

결과적으로 EKS 토큰의 **실질적 유효 기간은 15분**이다. 후술하겠지만, 이것이 kubeconfig에서 정적 토큰 방식을 사용하는 것이 비실용적이고, kubeconfig의 `exec` 방식을 채택한 이유이다.

<br>

# kubectl에서 EKS API 서버까지

지금까지 알게 된 것을 정리하면 세 가지다.

1. EKS API 서버는 STS에 인증을 위임한다
2. 이를 위해 사용자는 STS `GetCallerIdentity` pre-signed URL을 Bearer Token 형태로 보내줘야 한다
3. `aws eks get-token` 같은 도구로 토큰을 만들 수 있다

이를 바탕으로 `kubectl`에서 EKS API 서버까지의 전체 요청 흐름을 살펴보자.

![kubectl-to-eks-api-flow]({{site.url}}/assets/images/kubectl-to-eks-api-flow.png){: .align-center}

<center><sup>kubectl에서 EKS API 서버까지의 전체 요청 흐름</sup></center>

<br>

## kubeconfig exec 방식

Kubernetes 클러스터는 kubeconfig라는 통일된 형식으로 클러스터 접근 설정 파일을 관리한다. API 서버에 접근하는 모든 주체의 인증 정보가 `users` 섹션에 들어가고, kubectl은 요청 시 이 섹션을 읽어서 API 서버에 "이 사용자가 누구다"라는 정보를 전달한다.

EKS도 Kubernetes 클러스터이니 예외는 아니다. `users` 섹션에 인증 정보를 담아야 한다. 문제는 그 인증 정보가 **15분마다 만료되는 토큰**이라는 것이다.

kubeconfig에 담을 수 있는 user 인증 방식은 여러 가지(client certificate, token, exec, authProvider 등)인데, 정적 `token` 필드에 토큰을 박아 넣는 것은 이론적으로 가능하지만 비실용적이다.

```yaml
# 이론상 가능하지만...
users:
- name: myeks
  user:
    token: k8s-aws-v1.aHR0cHM6Ly9zdHMu...  # 미리 발급한 토큰
```

15분이 지나면 무효한 토큰이 되어 `401 Unauthorized` 에러가 반환된다. 만료될 때마다 수동으로 토큰을 교체해야 하는데, 이건 쓸 수 없는 구조다.

EKS가 채택한 방식은 `exec`이다. kubectl이 **외부 명령어를 실행**하여 인증 정보를 동적으로 받아오는 방식으로, 토큰이 만료되면 자동으로 새 토큰을 발급받는다.

```yaml
users:
- name: arn:aws:eks:ap-northeast-2:988608581192:cluster/myeks
  user:
    exec:
      apiVersion: client.authentication.k8s.io/v1beta1
      args:
      - --region
      - ap-northeast-2
      - eks
      - get-token
      - --cluster-name
      - myeks
      - --output
      - json
      command: aws
```

| | 정적 token 방식 | exec 방식 |
| --- | --- | --- |
| **동작** | 토큰 발급 → kubeconfig에 복붙 → 15분 후 만료 → 다시 복붙 | kubectl이 토큰 만료 시 자동으로 새 토큰 발급 |
| **사용자 경험** | 15분마다 수동 갱신 | 토큰 만료에 대해 신경 쓸 필요 없음 |
| **토큰 발급 방식** | 사용자가 직접 도구를 실행 | kubectl이 내부적으로 도구를 실행 |

exec으로 자동화되어 있으니, 사용자는 토큰 만료에 대해서도, 토큰 발급 방식에 대해서도 신경쓰지 않고 투명하게 `kubectl`을 사용할 수 있다.

<br>

## kubeconfig exec 블록 설정

kubeconfig에는 "user 정보 자체"가 아니라 **"user 정보를 알아내는 방법(exec 블록)"**이 들어간다. exec 블록을 설정하는 방법은 두 가지다.

### aws eks update-kubeconfig 명령

가장 간단한 방법이다. 기본 IAM User를 그대로 쓰는 경우:

```bash
aws eks update-kubeconfig --region ap-northeast-2 --name myeks
```

다른 IAM User의 프로필을 사용하는 경우:

```bash
aws eks update-kubeconfig --region ap-northeast-2 --name myeks \
  --profile other-user
```

IAM Role을 사용하는 경우:

```bash
aws eks update-kubeconfig --region ap-northeast-2 --name myeks \
  --role-arn arn:aws:iam::123456789012:role/MyEKSRole
```

<br>

### kubeconfig 직접 편집

IAM User를 사용하는 경우, `env`에 `AWS_PROFILE`을 설정한다.

```yaml
exec:
  command: aws
  args:
    - --region
    - ap-northeast-2
    - eks
    - get-token
    - --cluster-name
    - myeks
  env:
    - name: AWS_PROFILE
      value: other-user
```

`env`를 생략하거나 `null`로 두면 기본 프로필의 IAM User 자격증명이 사용된다. 기본 IAM User를 그대로 쓸 거라면 exec 블록을 별도로 수정할 필요 없다.

IAM Role을 사용하는 경우, `args`에 `--role-arn`을 추가한다.

```yaml
exec:
  command: aws
  args:
    - --region
    - ap-northeast-2
    - eks
    - get-token
    - --cluster-name
    - myeks
    - --role-arn
    - arn:aws:iam::123456789012:role/MyEKSRole
```

<br>

### 전제 조건

kubeconfig exec 기반 동작이 동작하려면 다음이 갖춰져 있어야 한다.

| 요구사항 | 역할 |
| --- | --- |
| **AWS CLI 설치** | `exec.command`가 `aws`이므로, 이 바이너리가 PATH에 있어야 함 |
| **IAM 자격증명 설정** | `aws eks get-token`이 STS pre-signed URL을 만들려면 유효한 IAM credential이 필요 |
| **EKS 클러스터 존재** | `--cluster-name`으로 지정한 클러스터가 실제로 존재하고, 해당 IAM identity가 접근 권한을 가지고 있어야 함 |

<br>


# 결론

kubeconfig 설정은 `aws eks update-kubeconfig` 한 줄이면 끝이지만, 그 이면에는 K8s 오픈소스를 AWS IAM 생태계에 통합하기 위한 정교한 인증 구조가 있다.

| 단계 | 내용 |
| --- | --- |
| **문제** | K8s API 서버(AWS 외부 시스템)가 IAM identity를 확인해야 함 |
| **해결** | STS `GetCallerIdentity` — 외부에서 IAM identity를 확인할 수 있는 유일한 공개 API |
| **전달 방식** | Pre-signed URL → base64url 인코딩 → `k8s-aws-v1.<base64>` Bearer Token |
| **검증 주체** | aws-iam-authenticator webhook → STS에 HTTP GET으로 identity 확인 위임 |
| **자동화** | kubeconfig `exec`로 토큰 만료 시 자동 갱신 |

K8s API 서버 자체는 AWS 서명을 이해하지도 검증하지도 않고, webhook(aws-iam-authenticator)으로 인증을 위임할 뿐이다. aws-iam-authenticator가 STS에 URL을 전달하는 중개자 역할을 하고, 복잡한 암호학적 검증은 전부 STS가 처리한다. K8s의 Webhook Token Authentication, aws-iam-authenticator의 토큰 포맷, AWS의 pre-signed URL + Signature V4가 각자의 책임 영역 안에서 깔끔하게 조합된 구조다.

<br>


# 참고 자료

EKS가 STS `GetCallerIdentity` pre-signed URL을 사용한다는 것을 확인할 수 있는 공식/준공식 소스들이다. 나중에 알아보기 위해 기록해 둔다.

- **[aws-iam-authenticator GitHub](https://github.com/kubernetes-sigs/aws-iam-authenticator)**: `README.md`에 "uses the AWS STS `GetCallerIdentity` API as the identity verification mechanism"이라고 명시되어 있다. 토큰 검증 로직에서 `GetCallerIdentity` action만 허용하는 코드도 확인할 수 있다.
- **[AWS 공식 문서 - EKS Best Practices (Identity and Access Management)](https://docs.aws.amazon.com/eks/latest/best-practices/identity-and-access-management.html)**: IAM 인증이 STS 기반임을 설명한다.
- **[AWS STS GetCallerIdentity API 공식 문서](https://docs.aws.amazon.com/STS/latest/APIReference/API_GetCallerIdentity.html)**: "No permissions are required to perform this operation"이라는 점이 명시되어 있다.
- **[Using AWS IAM with STS as an Identity Provider](https://medium.com/datamindedbe/using-aws-iam-with-sts-as-an-identity-provider-f5177ca0850c)**: EKS뿐 아니라 HashiCorp Vault도 동일한 패턴을 사용한다는 점을 설명한다.

<br>
