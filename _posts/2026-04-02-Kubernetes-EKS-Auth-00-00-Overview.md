---
title: "[EKS] EKS: 인증/인가 - 0. 개요"
excerpt: "EKS에서 두 인증 체계(K8s와 AWS IAM)가 만나면서 생기는 근본 문제와 세 가지 인증 흐름을 정리한다."
categories:
  - Kubernetes
toc: true
header:
  teaser: /assets/images/blog-Dev.jpg
tags:
  - Kubernetes
  - AWS
  - EKS
  - IAM
  - RBAC
  - AWS-EKS-Workshop-Study
  - AWS-EKS-Workshop-Study-Week-4
---

*[서종호(가시다)](https://www.linkedin.com/in/gasida99/)님의 AWS EKS Workshop Study(AEWS) 4주차 학습 내용을 기반으로 합니다.*

<br>

# TL;DR

- EKS 환경에는 **세 가지 인증 흐름**이 존재한다: 사용자 → K8S API, Pod → K8S API, Pod → AWS API
- 핵심 문제는 **독립적으로 설계된 두 인증 체계**(K8s ServiceAccount/RBAC vs AWS IAM)가 하나의 플랫폼에서 돌아간다는 것이다
- 두 세계를 넘는 흐름(1, 3)은 **신뢰 수립 → 신분 매핑 → 최소 권한**이라는 세 단계를 반드시 해결해야 한다
- 흐름 1(AWS → K8S)은 aws-iam-authenticator + Access Entry로, 흐름 3(K8S → AWS)은 OIDC Provider + IRSA/Pod Identity로 해결한다
- 흐름 2(Pod → K8S API)는 한 세계 안에서 완결되어 복잡도가 낮다

<br>

# EKS에서 발생하는 세 가지 인증 흐름

EKS 환경에서는 "누가 어디에 접근하는가"에 따라 세 가지 인증/인가(Authentication/Authorization) 흐름이 존재한다.

```text
1. 사람  ──IAM 토큰──▶ K8S API     (운영자가 kubectl 쓰는 것)
2. Pod  ──SA 토큰──▶  K8S API     (Pod가 K8S 내부 리소스 접근)
3. Pod  ──IAM 임시자격증명──▶ AWS API  (Pod가 S3 등 AWS 서비스 접근)
```

| # | 흐름 | 목적지 | 설명 | 인증/인가 방식 |
| --- | --- | --- | --- | --- |
| 1 | **사용자(운영자) → K8S API** | K8S API 서버 | 사람(IAM)이 K8s에 접근 | IAM → STS pre-signed URL → Access Entry/RBAC |
| 2 | **Pod → K8S API** | K8S API 서버 | Pod(SA)가 K8s 내부 리소스 접근 | SA → K8S RBAC (Role/RoleBinding) |
| 3 | **Pod → AWS 리소스** | AWS API (S3, DynamoDB 등) | Pod(SA + IAM Role)가 AWS 서비스 접근 | SA + IAM Role → IRSA / Pod Identity |

이 중 **흐름 1과 3은 서로 다른 두 세계(K8s ↔ AWS)를 넘나드는 인증**이다. 여기서 EKS 인증/인가의 핵심 문제가 발생한다.

<br>

# 근본 문제: 서로 모르는 두 인증 체계의 만남

EKS가 풀어야 하는 본질적인 문제는, 독립적으로 설계된 두 인증 체계(Authentication System)가 하나의 플랫폼 위에서 돌아간다는 것이다.

|  | K8S 세계 | AWS 세계 |
| --- | --- | --- |
| **인증 주체 (신분증)** | ServiceAccount + JWT | IAM User/Role + SigV4 |
| **권한 체계** | RBAC (Role/RoleBinding) | IAM Policy |
| **인증 방식** | X.509 인증서, SA 토큰 | Access Key + Secret Key 서명 (HMAC) |
| **설계 주체** | CNCF / 오픈소스 커뮤니티 | AWS |

기본적으로 서로의 인증 주체를 모른다.

- K8S API 서버는 IAM Access Key를 직접 검증하지 않는다 (webhook을 통해 STS에 위임)
- AWS STS는 K8S ServiceAccount 토큰이 뭔지 모른다

> 두 체계를 "PKI"로 묶는 것은 부정확하다. K8s는 PKI(X.509 인증서)를 쓰지만, AWS IAM은 PKI가 아니라 HMAC 기반 서명(SigV4)을 사용한다. 둘 다 포괄하는 용어로는 "인증 체계(Authentication System)" 또는 "신뢰 체계(Trust System)"가 적절하다.

## 왜 연결이 가능한가: K8s의 "User 없음" 설계

K8s는 의도적으로 User 오브젝트를 두지 않았다. "누구인지 확인하는 것(authentication)"은 지원하지만, "누가 있는지 관리하는 것(identity management)"은 범위 밖으로 둔 것이다. ServiceAccount만 내부 오브젝트인 이유는 Pod의 identity가 K8s의 핵심 도메인이기 때문이다.

이 설계의 이유는 다음과 같다.

- **사용자 관리는 이미 해결된 문제**: 기업 환경에는 LDAP, Active Directory, Okta 등 성숙한 IdP(Identity Provider)가 이미 있다. K8s가 자체 User 오브젝트를 만들면 기존 IdP와 동기화 문제(이중 관리), 비밀번호 정책/MFA/계정 잠금 등 IAM 기능의 자체 구현이 필요해져 "또 하나의 불완전한 IAM 시스템"이 된다
- **관심사 분리(Separation of Concerns)**: K8s의 핵심 도메인은 워크로드 오케스트레이션(Pod, Deployment, Service 등)이지, 사용자 관리가 아니다. ServiceAccount는 Pod/워크로드의 identity이므로 K8s 도메인에 속하고, Human User는 조직의 identity 관리이므로 외부에 위임한다
- **유연성과 이식성**: User 오브젝트를 두지 않음으로써 어떤 인증 방식이든 플러그인할 수 있다(X.509, OIDC, custom webhook 등). LDAP의 경우에도 Dex 같은 OIDC proxy를 앞에 두거나 custom webhook authenticator를 구현하면 연동할 수 있다. 클라우드 프로바이더마다 다른 IAM(AWS IAM, GCP IAM, Azure AD)과 자연스럽게 통합되고, 온프레미스 ↔ 클라우드 간 이식 시 인증 방식만 바꾸면 된다
- **etcd 부담 최소화**: User 오브젝트를 etcd에 저장하면 사용자 수만큼 오브젝트가 늘어나고, 인증 시마다 etcd 조회가 필요해진다. 현재 구조에서는 Human User 인증(X.509, OIDC, webhook)이 etcd 조회 없이 stateless하게 처리되어 API 서버 성능에 유리하다. 다만 ServiceAccount 토큰 검증은 완전히 stateless는 아닌데, bound SA token(projected token)의 경우 TokenReview API를 통해 토큰의 유효성(만료, 삭제 여부)을 확인하기 때문이다. 그래도 Human User 인증은 etcd 조회 없이 처리되므로, User 오브젝트가 없어서 etcd 부담이 줄어든다는 논지는 유효하다


### 이 설계가 EKS에 주는 의미

K8s에 User가 없는 것 자체는 문제가 아니다. 오히려 EKS가 IAM을 authenticator로 플러그인할 수 있게 해주는 설계적 장점이다. K8s의 authentication은 결국 `UserInfo{Username, Groups, UID}`를 반환하는 인터페이스이고, 그 뒤의 RBAC은 이 문자열만 본다. EKS는 webhook authenticator를 통해 IAM identity를 이 문자열로 변환할 뿐이다.

![EKS 인증/인가 개요]({{site.url}}/assets/images/aws-authn-authz-overview.png){: .align-center}

## 왜 IAM을 피할 수 없는가

AWS 위에서 EKS를 운영하는 한 IAM은 전제다. IAM을 쓰지 않는다는 것은 사실상 두 가지를 포기하겠다는 뜻이다.

- **기존 IAM 체계로 EKS를 관리할 수 없다** (흐름 1이 성립하지 않는다): EKS를 도입했다고 K8S용 별도 인증 체계(인증서 발급, 사용자 DB 등)를 별개로 또 만들어야 한다
- **Pod에서 AWS 서비스를 호출할 수 없다** (흐름 3이 성립하지 않는다): AWS 서비스(S3, DynamoDB 등)는 IAM 인증 없이는 접근할 수 없다

결국 "기존 IAM 사용자가 그대로 EKS도 쓸 수 있으면 좋겠다"는 요구와 "Pod가 AWS 서비스에 접근해야 한다"는 요구가 합쳐져서, 두 인증 체계를 연결할 수밖에 없게 된다.

## 풀어야 할 세 가지 문제

한쪽 세계의 주체가 다른 쪽 세계의 리소스에 접근하려면, 다음 세 단계를 반드시 해결해야 한다.

1. **신뢰 수립(Trust Establishment)**: "상대 세계의 인증 주체를 어떻게 믿을 수 있게 만들 것인가?"
2. **신분 매핑(Identity Mapping)**: "상대 세계의 인증 주체를 우리 세계의 누구로 대응시킬 것인가?"
3. **최소 권한(Least Privilege)**: "매핑된 주체에 적절한 권한만 부여할 것인가?"

> 최소 권한 문제 자체는 K8s RBAC 안에서도 존재한다(흐름 2). 다만 한 세계 안의 문제라 복잡도가 낮다. EKS에서 특별히 어려운 것은 "두 권한 체계를 동시에 설계해야 한다"는 점이다. 예를 들어 Node IAM Role 하나로 모든 Pod가 같은 AWS 권한을 갖는 문제는 K8s RBAC만으로는 해결할 수 없고, 이것이 IRSA/Pod Identity가 필요해진 이유이기도 하다.

## 운영상의 복잡성

진짜 복잡성은 "IAM 권한 체계와 K8s RBAC 권한 체계라는 두 개의 독립적인 인가 레이어를 동시에 관리해야 한다"는 운영상의 문제에서 온다.

### 이중 권한 관리

AWS IAM 측에서는 "이 IAM User/Role이 EKS 클러스터에 접근할 수 있는가?"(인증)를 보고, K8s RBAC 측에서는 "이 username이 pods를 get할 수 있는가?"(인가)를 본다. 두 레이어가 독립적이라서, IAM에서는 Admin인데 K8s에서는 아무 권한이 없는 상황이 발생할 수 있다. 반대로 IAM에서 제한된 Role인데 K8s에서 `system:masters` 그룹에 매핑되어 있으면 K8s에서는 슈퍼유저가 된다.

### 매핑 관리의 번거로움

`aws-auth` ConfigMap(deprecated)은 이 ConfigMap 하나가 잘못되면 클러스터 접근이 모두 막히는 문제가 있었다. EKS Access Entry(2023년 말 도입)는 AWS API로 매핑을 관리하므로 lockout 문제를 해결했지만, 여전히 "IAM identity ↔ K8s identity" 매핑 자체는 필요하다.

### IAM과 K8s 인가 체계의 본질적 미스매치

IAM Policy로 "pods를 get할 수 있다"를 표현할 수 없고, K8s 인가 체계로 "특정 IP에서만 접근"을 표현할 수 없다. 이 미스매치는 RBAC뿐 아니라 ABAC, Webhook 등 어떤 K8s authorization mode를 쓰더라도 동일하다. K8s 인가는 K8s 리소스/verb/namespace를, IAM은 AWS action/ARN/condition을 다루기 때문에 도메인 자체가 다르다.

|  | AWS IAM | K8s RBAC |
| --- | --- | --- |
| **권한 단위** | AWS 서비스 API action (`eks:DescribeCluster`) | K8s resource + verb (`pods/get`) |
| **범위** | AWS 리소스 ARN | namespace / cluster |
| **조건부 접근** | IAM Condition (IP, 시간 등) | 없음 (Admission Controller로 우회) |

<br>

# 세 가지 인증 흐름 상세

앞서 정리한 세 가지 흐름을 하나씩 살펴본다. 근본 문제(신뢰 수립 → 신분 매핑 → 최소 권한)가 실제로 발생하는 지점은 흐름 1과 흐름 3이고, 흐름 2는 그 문제가 없는 대조군이다.

## 흐름 1: 사용자(IAM) → K8S API (AWS → K8S 방향)

AWS IAM 주체(사람/관리자)가 EKS API 서버에 접근하기 위해 인증/인가를 받는 과정이다.

```text
사람(IAM User/Role) ──토큰──▶ EKS API 서버
                                    │
                        AWS STS로 "이 사람 누구?" 확인 (인증)
                        Access Entry/RBAC로 "뭘 할 수 있어?" 확인 (인가)
```

- **출발점**: AWS IAM (사람)
- **도착점**: Kubernetes API
- **핵심 질문**: "이 AWS IAM 사용자가 K8S에서 뭘 할 수 있는가?"

> kubectl이 `aws eks get-token`으로 생성하는 것은 STS GetCallerIdentity의 pre-signed URL을 base64 인코딩한 bearer token이다. STS가 토큰을 발급하는 것이 아니라, STS API 호출용 pre-signed URL 자체가 토큰 역할을 한다.

| 문제 | 흐름 1에서의 해결 |
| --- | --- |
| 신뢰 수립 | `aws-iam-authenticator` — STS의 pre-signed URL을 K8S가 webhook으로 검증 |
| 신분 매핑 | `Access Entry` / `aws-auth ConfigMap` — IAM User → K8S username/group |
| 최소 권한 | `Access Policy` / `K8S RBAC` — 매핑된 K8S 주체에 적절한 Role/RoleBinding |

## 흐름 3: Pod(SA) → AWS API (K8S → AWS 방향)

K8S 안의 Pod(애플리케이션)가 AWS 서비스(S3, DynamoDB, SQS 등)에 접근하기 위해 IAM 권한을 받는 과정이다.

```text
K8S Pod(ServiceAccount) ──IAM 임시자격증명──▶ AWS API (S3, DynamoDB 등)
                                                      │
                        "이 Pod이 어떤 IAM Role을 가지는가?" 확인
```

- **출발점**: Kubernetes Pod (애플리케이션)
- **도착점**: AWS API
- **핵심 질문**: "이 K8S Pod가 AWS에서 뭘 할 수 있는가?"

> IRSA에서 EKS가 발급하는 SA 토큰은 projected service account token(bound token)이며, 기존의 legacy SA token과 다르다. audience, expiry가 제한되어 있어 보안성이 높다.

| 문제 | 흐름 3에서의 해결 (IRSA) |
| --- | --- |
| 신뢰 수립 | `OIDC Provider` — EKS OIDC Provider를 AWS IAM에 등록하여 K8S 클러스터가 발급한 토큰을 신뢰 |
| 신분 매핑 | `IRSA 어노테이션` / `Pod Identity Association` — IAM Role의 Trust Policy에 SA 조건 명시 |
| 최소 권한 | `IAM Policy` (Role에 부여) — Pod별로 다른 SA → 다른 IAM Role → 다른 IAM Policy |

## 흐름 1 vs 흐름 3

|  | 흐름 1: 사용자 → K8S API | 흐름 3: Pod → AWS API |
| --- | --- | --- |
| **누가** | 사람 (IAM User/Role) | Pod (ServiceAccount) |
| **어디로** | K8S API 서버 | AWS 서비스 (S3 등) |
| **방향** | **AWS → K8S** | **K8S → AWS** |
| **핵심 질문** | IAM 주체가 K8S에서 뭘 할 수 있나? | Pod가 AWS에서 뭘 할 수 있나? |

같은 세 가지 문제(신뢰 수립 → 신분 매핑 → 최소 권한)를 풀지만, 신뢰 방향과 토큰 교환 흐름이 정반대다. 이 구분이 명확해야 전체 EKS 보안 아키텍처가 잡힌다.

## 비교 대상: 흐름 2

흐름 2는 위의 근본 문제가 발생하지 않는 경우다. 두 세계를 넘나들지 않기 때문이다.

```text
Pod  ──SA 토큰──▶  K8S API     (K8S 안에서 완결)
```

- SA에 Role/RoleBinding을 걸어서 K8s 내부 리소스(Pod, Service 등)에 접근
- IAM은 전혀 관여하지 않음 — 순수 K8s 세계 안의 인증/인가
- SA 토큰 발급 → K8S API가 직접 검증 → K8S RBAC으로 인가 → 끝

|  | SA만 사용 (흐름 2) | SA + **IAM Role** (흐름 3) |
| --- | --- | --- |
| **목적지** | K8S API | **AWS API** |
| **인가 방식** | K8S RBAC (Role/RoleBinding) | **IAM Policy** |
| **예시** | `kubectl get pods` | `aws s3 ls` |

이 흐름을 같이 놓는 이유는 "두 세계를 넘는 것이 왜 복잡한지"를 대비시키기 위해서다.

<br>

# 정리

## 전체 흐름 요약

| 흐름 | 신뢰 체계 | 복잡도 |
| --- | --- | --- |
| **1. 사람 → K8S API** | AWS IAM → K8S RBAC | **높음** — 두 세계를 넘어감 |
| **2. Pod → K8S API** | K8S SA → K8S RBAC | **낮음** — K8S 안에서만 |
| **3. Pod → AWS API** | K8S SA → AWS IAM | **높음** — 두 세계를 넘어감 |

**EKS 인증/인가의 핵심 = "독립적으로 설계된 두 인증 체계를, 보안을 유지하면서 양방향으로 연결하는 것"**

근본 문제(두 인증 체계의 불일치)에서 출발하면, 그 문제가 발생하는 지점이 곧 흐름 1과 3이고, 흐름 2는 그 문제가 없는 대조군이다.

## 기술 매핑

| 기술 | 어떤 문제를 푸는가 |
| --- | --- |
| `aws-iam-authenticator` | 흐름 1의 신뢰 수립 |
| `Access Entry` / `aws-auth` | 흐름 1의 신분 매핑 |
| `Access Policy` / `K8S RBAC` | 흐름 1의 최소 권한 |
| `OIDC Provider` | 흐름 3의 신뢰 수립 |
| `IRSA 어노테이션` / `Pod Identity Association` | 흐름 3의 신분 매핑 |
| `IAM Policy` (Role에 부여) | 흐름 3의 최소 권한 |

## 앞으로 볼 내용

| 흐름 | 비중 | 학습 방향 |
| --- | --- | --- |
| **1. 사람 → K8S API** | 높음 | STS pre-signed URL + aws-iam-authenticator라는 "다리"가 어떻게 AWS 신분증을 K8S가 인정하게 만드는지 확인 |
| **2. Pod → K8S API** | 낮음 | SA/RBAC 기초 실습으로 감을 잡는 수준 |
| **3. Pod → AWS API** | 높음 | OIDC + AssumeRoleWithWebIdentity라는 "다리"가 어떻게 K8S 신분증을 AWS가 인정하게 만드는지 확인 |

핵심 학습 목표는 1번과 3번 흐름을 이해하는 것이다. 두 흐름 모두 서로 다른 인증 체계 사이에 신뢰를 수립하는 메커니즘이 필요하고, 그 메커니즘이 정반대 방향으로 동작한다. 2번은 IAM이 관여하지 않아 단순하므로, 기초 실습으로 SA/RBAC 감을 잡은 뒤 본격적인 학습은 1번과 3번에 집중한다.

<br>

*다음 포스트: [EKS: 인증/인가 - 1. 실습 환경 배포]({% post_url 2026-04-02-Kubernetes-EKS-Auth-01-Installation %})*

<br>
