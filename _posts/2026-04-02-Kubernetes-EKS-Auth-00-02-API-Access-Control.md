---
title: "[EKS] EKS: 인증/인가 - 1. K8S 인증/인가 기초 - 1. API 접근 통제"
excerpt: "K8S API 서버로 들어오는 모든 요청이 거치는 파이프라인을 TLS, 인증, 인가, Admission Control까지 정리해 보자."
categories:
  - Kubernetes
toc: true
hidden: true
header:
  teaser: /assets/images/blog-Dev.jpg
tags:
  - Kubernetes
  - Authentication
  - Authorization
  - Admission-Control
  - AWS-EKS-Workshop-Study
  - AWS-EKS-Workshop-Study-Week-4
---

*[서종호(가시다)](https://www.linkedin.com/in/gasida99/)님의 AWS EKS Workshop Study(AEWS) 4주차 학습 내용을 기반으로 합니다.*

<br>

# TL;DR

- K8S API 서버로 들어오는 모든 요청은 **TLS → Authentication → Authorization → Admission Control → etcd** 파이프라인을 거친다
- Authentication(인증): 여러 모듈 중 **하나만 성공하면 통과**(OR). 실패 시 401
- Authorization(인가): 여러 모듈 중 **하나만 승인하면 통과**(OR). 거부 시 403
- Admission Control: **하나라도 거부하면 즉시 거부**(AND). 오브젝트 내용까지 검사하는 마지막 관문
- K8s에는 `User` 오브젝트가 없다 — 인증은 지원하지만 사용자 관리는 외부에 위임한다
- 프로덕션 멀티유저 클러스터에서는 **OIDC 등 외부 인증 소스**를 사용하는 것이 권장된다

<br>

# 들어가며

[이전 포스트]({% post_url 2026-04-02-Kubernetes-EKS-Auth-00-00-Overview %})에서 EKS에는 세 가지 인증 흐름이 있고, 그 중 흐름 2(Pod → K8S API)는 "K8s 안에서 완결"된다고 정리했다. 이 완결이 무엇인지, 즉 **K8S API 서버가 요청을 어떻게 처리하는지**를 이해해야 흐름 1(사용자 → K8S API)과 흐름 3(Pod → AWS API)에서 "무엇이 추가되는지"가 보인다.

Human User든 ServiceAccount든, K8S API 서버에 도달하는 **모든 요청은 동일한 파이프라인**을 거친다. 차이는 Authentication 단계에서 어떤 authenticator 모듈이 처리하느냐뿐이다.

```text
모든 요청 (사람이든 Pod이든)
  → TLS → Authentication → Authorization → Admission Control → etcd
```

![K8S API 접근 통제 개요]({{site.url}}/assets/images/kubernetes-access-control-overview.svg){: .align-center}

- Human User → X.509 인증서, OIDC, webhook 등으로 인증
- ServiceAccount → K8S가 발급한 JWT 토큰으로 인증

EKS에서 `aws-iam-authenticator`가 하는 일도 결국 이 Authentication 단계에 **webhook authenticator 모듈을 하나 끼워넣는 것**이다. 파이프라인 자체는 바뀌지 않는다.

<br>

# Transport Security

파이프라인의 첫 번째 전제 조건은 TLS다. 인증·인가 이전에 통신 자체가 암호화되어야 한다. 토큰이 평문으로 날아다니면 인증이고 뭐고 의미가 없기 때문이다.

- K8S API 서버는 기본적으로 **포트 6443**에서 TLS로 보호된 상태로 리슨한다. 프로덕션에서는 보통 443번 포트를 사용한다
- API 서버가 인증서를 제시하고, Private CA 또는 공인 CA가 서명한 인증서를 사용할 수 있다
- Private CA를 사용하는 경우, 클라이언트의 `~/.kube/config`에 해당 CA 인증서를 등록해야 한다
- 클라이언트도 이 단계에서 TLS 클라이언트 인증서를 제시할 수 있다(X.509 인증)

> EKS에서는 이 부분을 AWS가 관리한다. EKS API 서버 엔드포인트는 AWS가 발급한 TLS 인증서로 보호되고, kubeconfig에 cluster CA certificate가 자동으로 설정된다.

<br>

# Authentication

TLS가 수립되면 HTTP 요청은 Authentication(인증) 단계로 넘어간다.

## Authenticator 모듈 동작 방식

클러스터 관리자가 API 서버 기동 시 플래그로 활성화한 **Authenticator 모듈들이 순서대로 인증을 시도**한다.

| API 서버 플래그 | Authenticator 모듈 |
| --- | --- |
| `--client-ca-file` | X.509 Client Certificate |
| `--oidc-issuer-url` | OIDC |
| `--token-auth-file` | Static Token |
| `--service-account-key-file` | Service Account Token |

기술적으로 authenticator는 전체 HTTP request 객체를 입력으로 받지만, 실제로 확인하는 부분은 주로 `Authorization` 헤더(Bearer token 등)와 TLS handshake 시 제시된 **클라이언트 인증서** 둘이다.

핵심 동작: 여러 모듈이 설정되어 있으면 **순서대로 시도**하고, **하나라도 성공하면 인증 통과**한다. 나머지 모듈은 더 이상 시도하지 않는다. 모든 모듈이 실패해야 **401 Unauthorized**가 반환된다.

> EKS에서는 여기에 `--authentication-token-webhook-config-file`로 **aws-iam-authenticator**가 추가된다. 이 모듈이 STS pre-signed URL 형태의 bearer token을 받아서 IAM identity를 확인하는 것이다. K8s 입장에서는 그냥 webhook authenticator 모듈 중 하나일 뿐이다.

## 인증 결과: username과 group

인증 성공 시 authenticator는 반드시 **username**을 반환한다. group은 authenticator에 따라 포함될 수도 있고 아닐 수도 있다.

| Authenticator | username 추출 방식 | group 추출 방식 |
| --- | --- | --- |
| X.509 Client Certificate | 인증서 Subject의 `CN` | Subject의 `O`(Organization) |
| Service Account Token | 토큰 payload에서 추출 (`system:serviceaccount:<ns>:<name>`) | 자동 소속 (`system:serviceaccounts`, `system:serviceaccounts:<ns>`) |
| OIDC | ID Token의 `sub` 또는 설정된 claim | `groups` claim이 있으면 매핑 |
| Static Token | 파일에 직접 정의 | 파일에 정의된 group |

이전 포스트에서 K8s authentication은 결국 `UserInfo{Username, Groups, UID}`를 반환하는 인터페이스라고 정리했다. 여기서 보는 것이 정확히 그 과정이다. authenticator가 어떤 방식으로든 이 정보를 채워서 반환하면, 이후 Authorization은 이 문자열만 보고 판단한다.

## K8s에 User 오브젝트가 없다는 것의 의미

이전 포스트에서도 짚었지만 다시 한 번 확인하자. K8s는 인증에 username을 사용하지만, `User`라는 API 오브젝트는 **존재하지 않는다**.

> *"Kubernetes does not have objects which represent normal user accounts"*

authenticator가 반환하는 username/group은 **문자열**일 뿐, etcd에 저장되는 사용자 레코드 같은 건 없다. 사용자 관리(생성, 삭제, 비밀번호 변경 등)는 K8s 범위 **밖**에서 이루어진다.

반면 **ServiceAccount**는 K8s API 오브젝트(`v1/ServiceAccount`)로 존재하며, K8s가 직접 생성·관리한다. 이 비대칭이 EKS 같은 관리형 서비스에서 **외부 인증 체계를 자연스럽게 플러그인할 수 있게** 해주는 설계적 기반이다. User 오브젝트가 있었다면 IAM User/Role과 K8s User 사이의 동기화 문제가 생겼을 것이다.

## 인증 메커니즘별 특성: 프로덕션에서 뭘 써야 하는가

프로덕션 멀티유저 클러스터에서는 **OIDC 등 외부 인증 소스를 사용하는 것이 권장**된다. 가능한 한 **적은 수의 인증 메커니즘만 활성화**하여 사용자 관리를 단순화하는 것이 좋다. 각 메커니즘의 특성을 살펴보자.

### X.509 클라이언트 인증서

kubelet 등 **시스템 컴포넌트 인증**에 주로 사용된다. 사용자 인증에도 쓸 수 있지만 프로덕션에서는 제약이 많다.

- 개별 인증서를 **폐기(revoke)할 수 없다** — CA 자체를 re-key해야 하므로 가용성 위험
- Private key에 **패스워드 보호 불가**
- group 정보가 인증서 `O` 필드에 고정되어 **수명 동안 그룹 변경 불가**
- API 서버와의 **직접 연결 필요** (중간 TLS termination 불가)

### Static Token 파일

컨트롤 플레인 디스크에 credential을 평문 저장하는 방식이다. credential 변경 시 **API 서버 재시작** 필요, rotation 메커니즘 없음, lockout 메커니즘 없음. 프로덕션에서 **쓸 이유가 없다**.

### Bootstrap Token

**노드를 클러스터에 조인**시키기 위해 사용된다. hard-coded 그룹 멤버십으로 범용 사용에 부적합하고, 수동 생성 시 약한 토큰이 만들어질 위험이 있다. 사용자 인증 용도가 아니다.

### SA Secret Token (레거시)

K8s < 1.23의 기본이었으나, 만료 없는 영구 토큰이라 **현재는 비권장**. 다음 포스트에서 자세히 다룬다.

### TokenRequest API Token

서비스 인증용 **short-lived credential**을 생성하는 도구다. 사용자 인증에는 revocation 메커니즘이 없어 부적합하지만, SA 토큰 발급에는 핵심 역할을 한다. 역시 다음 포스트에서 상세히 본다.

### OIDC Token — 권장

K8s와 외부 IdP(Okta, Google, Azure AD 등)를 연동하는 **권장 방식**이다.

- OIDC 지원 소프트웨어는 높은 권한으로 실행되므로 **일반 워크로드와 격리** 필요
- 토큰 수명을 **짧게** 설정해야 한다
- 일부 관리형 서비스는 사용 가능한 OIDC provider가 제한될 수 있다

> EKS에서 사람 사용자 인증(흐름 1)에는 OIDC가 아니라 IAM + aws-iam-authenticator를 쓴다. 그런데 흐름 3(Pod → AWS API)에서는 EKS 자체가 **OIDC Provider** 역할을 한다. 같은 OIDC 기술이 방향에 따라 다른 위치에서 쓰인다는 점이 흥미롭다.

### Webhook Token

외부 인증 서비스에 webhook으로 인증 판단을 위임하는 방식이다. 컨트롤 플레인 서버 파일시스템 접근이 필요하므로 **관리형 K8s에서는 사용이 제한**될 수 있다. EKS의 aws-iam-authenticator가 바로 이 방식이다.

### Authenticating Proxy

프록시가 특정 헤더 값을 설정하여 username과 group을 전달하는 방식이다. 프록시와 API 서버 간 **TLS 필수**, 헤더 변조 시 **무단 접근** 가능하므로 보안에 주의해야 한다.

<br>

# Authorization

인증이 완료되면 요청은 Authorization(인가) 단계로 넘어간다.

## REST Attributes 기반 판단

중요한 건, 사용자가 인가 요청을 직접 구성하는 게 아니라는 점이다. API 서버가 HTTP 요청에서 **자동으로** authorization attributes를 추출한다.

`kubectl get pods -n projectCaribou`를 실행하면 kubectl이 이를 REST 요청으로 변환한다.

```text
GET /api/v1/namespaces/projectCaribou/pods
```

API 서버는 이 URL 경로와 HTTP method에서 다음을 추출한다.

| Attribute | 추출 방식 | 예시 |
| --- | --- | --- |
| **username** | Authentication 단계에서 확보 | `bob` |
| **verb** | HTTP method 매핑 | `GET` → `get`, `POST` → `create` |
| **resource** | URL 경로 | `pods` |
| **namespace** | URL 경로 | `projectCaribou` |
| **API group** | URL 경로 | `/apis/apps/v1/...` → `apps` |

**REST URL 구조 자체가 "누가 무엇을 어디에 하려는지"를 인코딩**하고 있고, API 서버가 이를 파싱하여 authorization 모듈에 전달한다. K8s가 REST attributes를 기반으로 설계한 이유는 기존 조직의 접근 제어 시스템(LDAP, 기업 IAM 등)과 통합하기 쉽게 하기 위해서다.

## Authorization 모듈

K8s는 여러 authorization 모듈을 지원한다.

| 모듈 | 설명 |
| --- | --- |
| **RBAC** | Role/ClusterRole에 verb+resource 권한을 정의하고, RoleBinding/ClusterRoleBinding으로 연결. **사실상 표준** |
| **ABAC** | JSON 정책 파일에 조합을 정의. 변경 시 API 서버 재시작 필요. 현재는 거의 사용 안 함 |
| **Node** | kubelet이 자기 노드에 스케줄된 Pod 관련 리소스만 접근할 수 있도록 제한하는 특수 모듈 |
| **Webhook** | 외부 HTTP 서비스에 authorization 판단을 위임. 기업 IAM 연동에 활용 |

Authentication과 동일한 OR 로직이다. 여러 모듈이 설정되어 있으면 **하나만 승인하면 통과**하고, 모든 모듈이 거부해야 **403 Forbidden**이 반환된다. 다만 Authorization에는 "의견 없음(no opinion)"이라는 옵션이 하나 더 있다.

> ABAC 예제를 보면 개념이 바로 잡힌다. Bob이 `projectCaribou` 네임스페이스의 Pod를 읽기만 할 수 있는 정책:
>
> ```json
> {
>     "apiVersion": "abac.authorization.kubernetes.io/v1beta1",
>     "kind": "Policy",
>     "spec": {
>         "user": "bob",
>         "namespace": "projectCaribou",
>         "resource": "pods",
>         "readonly": true
>     }
> }
> ```
>
> Bob이 `projectCaribou`에서 Pod `get` → 승인. Pod `create` → 거부. `projectFish`에서 Pod `get` → 거부. 문서가 ABAC 예제를 먼저 보여주는 이유는 개념을 단순하게 설명하기 위해서이고, 실제 프로덕션에서는 거의 항상 **RBAC**을 쓴다.

<br>

# Admission Control

인증·인가를 통과한 요청은 Admission Control 단계로 넘어간다. 요청을 **수정(modify)하거나 거부(reject)할 수 있는 소프트웨어 모듈**이다.

"인증 → 인가는 통과했지만, 실제로 이 오브젝트를 만들거나 수정해도 되는가?"를 세밀하게 검사하거나, 요청 내용을 보정하는 단계다.

Admission Controller는 각각 특정 검증·보정 로직을 담당하는 플러그인이다. Kubernetes에 여러 종류가 내장되어 있고, Webhook으로 사용자 정의 로직을 추가할 수도 있다. 대표적인 것들을 보면 역할이 감이 온다.

| Controller | 동작 |
| --- | --- |
| **NamespaceLifecycle** | 삭제 중인 namespace에 새 오브젝트 생성 → 거부 |
| **LimitRanger** | resource limits/requests 없으면 namespace 기본값 자동 주입 |
| **ResourceQuota** | namespace 리소스 할당량 초과 → 거부 |
| **PodSecurity** | securityContext가 정책에 맞지 않으면 거부 |
| **MutatingAdmissionWebhook** | 사용자 정의 webhook으로 요청 수정 (Istio sidecar 자동 주입이 이 방식) |
| **ValidatingAdmissionWebhook** | 사용자 정의 webhook으로 요청 검증만 |

## 깔때기(Funnel) 구조

Admission Control이 이전 단계와 결정적으로 다른 점은, 생성·수정되는 **오브젝트의 실제 내용(spec)**까지 접근할 수 있다는 것이다.

| 단계 | 접근 가능한 정보 |
| --- | --- |
| **Authentication** | HTTP 헤더, 클라이언트 인증서 |
| **Authorization** | username, group, verb, resource, namespace 등 **요청 메타데이터** |
| **Admission Control** | 위 메타데이터 + **요청 body (오브젝트 spec 전체)** |

의도적인 설계다. 앞 단계에서 "누구인가" → "권한이 있는가"를 먼저 걸러내고, 마지막에 실제 오브젝트 내용까지 검사한다.

## Authentication/Authorization과의 결정적 차이

|  | Authentication / Authorization | Admission Control |
| --- | --- | --- |
| 다중 모듈 시 | 하나만 성공/승인하면 통과 (**OR**) | **하나라도 거부하면 즉시 거부 (AND)** |
| 설계 의도 | "할 수 있는가?" | "해도 **안전한가**?" |
| 대상 작업 | 모든 요청 | **변경 요청만** (create, modify, delete, proxy) |

클러스터 상태를 변경하는 작업이므로 모든 검증 게이트를 통과해야만 허용된다. 보안/안정성에 대해서는 보수적(fail-closed)으로 동작한다. **조회(GET/LIST/WATCH)는 Admission Control을 거치지 않는다** — 상태를 바꾸지 않으니 Authorization에서 읽기 권한만 확인하면 충분하다.

모든 Admission Controller를 통과하면, 해당 API 오브젝트의 validation 루틴을 거친 후 최종적으로 etcd에 기록된다.

<br>

# Auditing: 전체 과정의 기록

Auditing은 파이프라인의 특정 단계가 아니라, **전 과정에서 로그를 기록하는 횡단(cross-cutting) 관심사**다. 누가 인증을 시도했는지, 인가가 승인/거부되었는지, Admission에서 수정/거부되었는지, 최종 저장되었는지 — 모든 이벤트를 시간순으로 기록한다.

별도의 "관문"이 아니라 전체를 아우르는 기록 메커니즘이기 때문에 문서에서도 개별 단계 설명이 끝난 후 마지막에 언급된다.

<br>

# 정리

K8S API 서버의 요청 처리 파이프라인을 다시 한 번 정리하면 다음과 같다.

```text
클라이언트 → TLS → Authentication → Authorization → Admission Control → etcd
                    (신원 확인)       (권한 확인)      (요청 검증/보정)
                    (너 누구야?)      (할 수 있어?)    (해도 안전해?)
```

| 단계 | 실패 시 | 다중 모듈 동작 | 접근 정보 |
| --- | --- | --- | --- |
| **Authentication** | 401 | OR (하나만 성공하면 됨) | HTTP 헤더, 인증서 |
| **Authorization** | 403 | OR (하나만 승인하면 됨) | 요청 메타데이터 |
| **Admission Control** | 즉시 거부 | AND (모두 통과해야 함) | 메타데이터 + 오브젝트 spec |
| **Auditing** | - | 횡단 | 전 과정 기록 |

이 파이프라인은 EKS에서도 동일하다. EKS가 추가하는 것은 Authentication 단계의 **webhook authenticator 모듈**(aws-iam-authenticator)과 Authorization의 **Access Entry 기반 RBAC 매핑**이다. 파이프라인 자체가 바뀌는 건 아니다.

프로덕션에서 인증 메커니즘을 선택할 때 기억할 것:

- **OIDC 등 외부 인증 소스**가 권장된다. 내부 메커니즘(X.509, Static Token, SA Secret)은 사용자 인증에 부적합하다
- 활성화하는 인증 메커니즘 수는 **최소화**한다
- K8s에 User 오브젝트가 없다는 설계가 EKS 같은 관리형 서비스에서 **외부 인증 체계를 자연스럽게 끼워넣을 수 있는 기반**이 된다

<br>

# 참고 링크

- [Controlling Access to the Kubernetes API](https://kubernetes.io/docs/concepts/security/controlling-access/)
- [Hardening Guide - Authentication Mechanisms](https://kubernetes.io/docs/concepts/security/hardening-guide/authentication-mechanisms/)
- [Authenticating](https://kubernetes.io/docs/reference/access-authn-authz/authentication/)
- [Authorization](https://kubernetes.io/docs/reference/access-authn-authz/authorization/)
- [Admission Controllers](https://kubernetes.io/docs/reference/access-authn-authz/admission-controllers/)
