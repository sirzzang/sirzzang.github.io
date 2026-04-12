---
title: "[EKS] EKS: 인증/인가 - 1. K8S 인증/인가 기초 - 2. Service Account"
excerpt: "K8s가 직접 관리하는 non-human identity인 Service Account의 개념과 토큰 생명주기를 정리해 보자."
categories:
  - Kubernetes
toc: true
header:
  teaser: /assets/images/blog-Dev.jpg
tags:
  - Kubernetes
  - ServiceAccount
  - TokenRequest
  - TokenReview
  - JWT
  - AWS-EKS-Workshop-Study
  - AWS-EKS-Workshop-Study-Week-4
---

*[서종호(가시다)](https://www.linkedin.com/in/gasida99/)님의 AWS EKS Workshop Study(AEWS) 4주차 학습 내용을 기반으로 합니다.*

<br>

# TL;DR

- ServiceAccount(SA)는 K8s가 직접 관리하는 **non-human identity**다. Human User와 달리 K8s API 오브젝트로 존재한다
- SA 토큰의 생명주기: **TokenRequest(발급)** → **Projected Volume(전달)** → **TokenReview(검증)**
- 1.22+ 이후 projected volume 기반 **short-lived 토큰**이 기본이다. 레거시 Secret 기반 영구 토큰은 비권장
- 모든 Pod은 반드시 하나의 SA identity를 가져야 하지만, **토큰 마운트는 비활성화**할 수 있다

<br>

# 들어가며

이전 포스트에서 K8s에는 `User` 오브젝트가 없고, 사용자 관리는 외부에 위임한다고 정리했다. 그렇다면 K8s가 **직접 관리하는 identity**는 뭘까? 바로 ServiceAccount다.

[개요 포스트]({% post_url 2026-04-02-Kubernetes-EKS-Auth-00-00-Overview %})에서 정리한 세 가지 인증 흐름을 다시 보자.

```text
1. 사람  ──IAM 토큰──▶ K8S API     (외부 인증 — OIDC, webhook, X.509)
2. Pod  ──SA 토큰──▶  K8S API     (내부 인증 — SA JWT)
3. Pod  ──IAM 임시자격증명──▶ AWS API  (내부 → 외부 — SA + IAM Role)
```

흐름 2와 3에서 SA가 등장한다. 특히 흐름 3(IRSA/Pod Identity)은 **SA 토큰을 AWS IAM이 신뢰할 수 있게 만드는 것**이 핵심인데, 그러려면 SA 토큰이 어떻게 발급·검증되는지를 알아야 한다.

<br>

# SA 개념

ServiceAccount는 K8s 클러스터에서 **고유한 identity를 제공하는 non-human account**다. Pod, 시스템 컴포넌트, 클러스터 내외부의 엔티티가 특정 SA의 credential을 사용하여 해당 SA로 식별될 수 있다.

## SA vs Human User

| 구분 | ServiceAccount | Human User |
| --- | --- | --- |
| **위치** | K8s API 오브젝트 (`v1/ServiceAccount`) | 외부 시스템 |
| **K8s가 관리하나?** | O (etcd에 저장, `kubectl get sa`로 조회) | X (외부에 위임) |
| **K8s가 토큰 발급하나?** | O (TokenRequest API) | X |
| **인증 방식** | SA JWT (K8s가 서명) | X.509, OIDC, webhook 등 (외부 발급) |
| **용도** | 워크로드, 자동화 | 사람 |

K8s가 User 오브젝트를 두지 않았기 때문에, **K8s가 직접 발급·관리하는 토큰은 오직 SA용**이다.

- **SA**: K8s가 SA 생성 → K8s가 JWT 발급(TokenRequest) → K8s가 JWT 검증. **K8s가 전체 생명주기를 관리**한다.
- **User**: 외부 IdP가 사용자 관리 → 외부가 credential 발급 → K8s는 검증만. **K8s는 "이 사람 누구?"만 판단**한다.

SA의 특징은 다음 세 가지로 요약된다.

- **Namespaced**: 특정 namespace에 종속된다. 같은 이름의 SA라도 namespace가 다르면 별개의 identity이며, 권한 범위도 namespace 단위로 격리된다.
- **Lightweight**: API 호출 한 번으로 즉시 생성할 수 있다. 외부 IdP 연동이나 인증서 발급 같은 무거운 절차가 필요 없다.
- **Portable**: Pod spec의 `serviceAccountName` 필드 하나로 워크로드에 바인딩할 수 있다. Helm chart나 매니페스트에 포함시켜 환경 간 이동이 쉽다.

<br>

# SA 토큰의 구조

SA 토큰은 **JWT(JSON Web Token)** 형식이다. JWT가 뭔지 간단히 짚고 가자.

## JWT 기초

JWT는 `.`(dot)으로 구분된 세 파트로 이루어진다: **헤더(Header)** . **페이로드(Payload)** . **서명(Signature)**.

```text
eyJhbGciOiJSUzI1NiJ9.eyJpc3MiOiJrdWJlcm5ldGVzLmRlZmF1bHQuc3ZjIi....SIGNATURE
─── Header ──────────  ─── Payload ──────────────────────────────  ── Sig ──
```

| 부분 | 내용 | 인코딩 |
| --- | --- | --- |
| **Header** | 서명 알고리즘(`alg`), 토큰 타입(`typ`) | Base64URL |
| **Payload** | claim 데이터 (누구인지, 만료 시간 등) | Base64URL |
| **Signature** | Header + Payload를 private key로 서명한 값 | 바이너리 → Base64URL |

Header와 Payload는 **암호화가 아니라 인코딩**이다. 누구나 디코딩해서 내용을 읽을 수 있다. JWT의 보안은 **서명(Signature)**에 있다. API 서버가 private key로 서명하고, 검증자는 public key로 서명이 변조되지 않았음을 확인한다.

> JWT 자체는 "이 토큰의 내용이 발급자에 의해 서명되었다"는 것만 보장한다. 만료(`exp`), audience(`aud`) 등의 제한은 claim에 넣을 수 있지만 **선택적**이다. 레거시 SA 토큰에 `exp`가 없어서 영구 유효했던 것도 이 때문이다.

## SA JWT의 Payload

K8s가 SA에 발급하는 JWT의 payload에는 SA identity 정보가 담겨 있다.

```json
{
  "iss": "https://kubernetes.default.svc",
  "sub": "system:serviceaccount:default:my-sa",
  "aud": ["api"],
  "exp": 1712617200,
  "kubernetes.io": {
    "namespace": "default",
    "serviceaccount": { "name": "my-sa", "uid": "..." },
    "pod": { "name": "my-pod", "uid": "..." }
  }
}
```

| Claim | 의미 |
| --- | --- |
| `iss` | 발급자(issuer). K8s API 서버 |
| `sub` | SA identity. `system:serviceaccount:<namespace>:<name>` 형식 |
| `aud` | 이 토큰의 의도된 수신자(audience). JWT 자체가 수신을 차단하는 것이 아니라, **검증자가 자신의 identity와 `aud`를 대조하여 불일치하면 거부**하는 방식이다 |
| `exp` | 만료 시간 (TokenRequest 기반이면 있고, 레거시면 없음) |
| `kubernetes.io` | K8s 전용 claim. bound token이면 바인딩된 Pod 정보도 포함 |

![SA 토큰 JWT 디버그 결과]({{site.url}}/assets/images/kubernetes-service-account-token-jwt-debug-result.png){: .align-center}

> 흐름 3(IRSA)에서는 이 JWT를 AWS STS가 검증한다. EKS가 OIDC Provider 역할을 하면서 `/.well-known/openid-configuration` 엔드포인트와 public key를 노출하고, AWS IAM이 이 public key로 SA JWT의 서명을 직접 검증하는 구조다. JWT의 `aud`를 `sts.amazonaws.com`으로 설정하면, AWS STS가 자신에게 발급된 토큰인지 확인하여 일치할 때만 수락한다.

<br>

# 토큰 생명주기

SA 토큰은 **발급 → 전달 → 검증**의 생명주기를 갖는다.

```text
1. 발급 (TokenRequest)    "이 SA의 JWT를 만들어줘"
         ↓
2. 전달 (Projected Volume) "발급받은 JWT를 Pod에 전달"
         ↓
3. 검증 (TokenReview)      "이 JWT 진짜야? 누구거야?"
```

## TokenRequest: 토큰 발급

TokenRequest API(`authentication.k8s.io/v1`)는 특정 SA의 **short-lived JWT를 동적으로 발급**하는 역할을 한다. kubelet이 자동으로 호출하지만, 사용자가 `kubectl create token`으로 직접 호출하거나 애플리케이션 코드에서 호출할 수도 있다.

```text
kubelet (또는 사용자)
    │
    │  POST /api/v1/namespaces/default/serviceaccounts/my-sa/token
    │  body: { audience: ["api"], expirationSeconds: 3600 }
    ▼
API Server (controller-manager의 signing key로 JWT 생성)
    │
    │  Response: { token: "eyJhbG..." }  ← exp, audience 포함된 JWT
    ▼
kubelet이 projected volume에 쓰기
    → /var/run/secrets/kubernetes.io/serviceaccount/token (tmpfs)
```

발급 시점에 `exp`(만료), `audience`, `boundObjectRef`(Pod에 바인딩) 등을 지정한다. K8s를 인식하지 못하는 레거시 앱의 경우, sidecar 컨테이너가 TokenRequest API를 대신 호출하여 토큰을 가져다 주는 패턴도 가능하다.

## Projected Volume: 토큰 전달

kubelet이 TokenRequest API로 발급받은 JWT를 Pod의 볼륨 마운트 경로(`/var/run/secrets/kubernetes.io/serviceaccount/token`)에 **tmpfs(메모리 기반 파일시스템)**로 마운트한다. [Projected Volume]({% post_url 2026-04-05-Kubernetes-Pod-Volume-04-ConfigMap-Secret-DownwardAPI-Projected %}) 메커니즘을 활용하는 것이다.

kubelet은 토큰 수명의 **80% 시점** 또는 만료 24시간 전(둘 중 빠른 시점)에 자동으로 새 토큰을 요청하여 교체한다. tmpfs에 저장되므로 **Pod 종료 시 사라지고**, 클러스터 전체에서 조회할 수 없으며, etcd에도 남지 않아 etcd 탈취와도 무관하다.

> 레거시 Secret 방식과의 결정적 차이가 바로 여기다. Secret은 etcd에 오브젝트로 저장되어 `kubectl get secret`으로 조회 가능하고 etcd 백업에도 포함된다. projected volume 토큰은 해당 노드의 메모리에만 존재한다.

자동 마운트되는 projected volume은 audience가 `api`이고 기본 경로에 마운트되지만, Pod spec에서 직접 설정하면 **audience, 만료 시간, 마운트 경로를 커스텀**할 수 있다.

```yaml
volumes:
- name: custom-token
  projected:
    sources:
    - serviceAccountToken:
        audience: "vault.example.com"  # API server가 아닌 다른 audience
        expirationSeconds: 3600
        path: token
```

> IRSA에서 Pod에 주입되는 SA 토큰이 바로 이 방식이다. audience가 `sts.amazonaws.com`으로 설정되고, AWS STS가 자신에게 발급된 토큰인지 `aud`를 확인하여 일치할 때만 수락한다.

## TokenReview: 토큰 검증

TokenReview API(`POST /apis/authentication.k8s.io/v1/tokenreviews`)는 주어진 JWT가 **유효한지 검증**하고, 누구의 토큰인지 반환하는 역할을 한다. API server가 내부적으로 호출하지만, webhook authenticator나 외부 시스템에서도 호출할 수 있다.

API 서버가 SA 토큰을 검증할 때 거치는 **5단계**:

1. **서명 검증**: public key로 JWT 서명을 확인
2. **시간 만료 체크**: JWT의 `exp` claim 기준 만료 여부
3. **참조 오브젝트 존재 확인**: 토큰에 참조된 SA, Pod, Secret 등이 클러스터에 실제로 존재하는지 확인. 서명이 유효해도 참조 오브젝트가 삭제되었으면 인증 거부
4. **런타임 유효성 체크**: 토큰이 폐기(revoke)되지 않았는지 확인. 2번(시간 기반)과 달리 **상태 기반** 유효성 검증이다. `exp`가 안 지났어도 Pod이 삭제되면 bound token은 즉시 무효화된다
5. **audience 일치 여부**: 토큰의 audience가 요청 대상과 일치하는지 확인

실제 인증 흐름에서 SA 클라이언트는 API 서버에 `Authorization: Bearer <token>` 헤더로 요청을 보내고, API 서버가 위 5단계를 거쳐 토큰을 검증한다.

SA credential을 검증해야 하는 서비스는 두 가지 방식을 선택할 수 있다.

- **TokenReview API (권장)**: SA, Pod, Node 등 바인딩된 오브젝트가 삭제되면 **즉시** 토큰을 무효화한다
- **OIDC Discovery**: 외부 시스템이 public key로 직접 JWT 서명을 검증한다. 다만 토큰 만료 timestamp까지는 유효한 것으로 취급된다

> TokenReview vs OIDC Discovery의 차이가 보안 관점에서 중요하다. TokenReview는 실시간으로 유효성을 확인하지만 API server 호출이 필요하다. OIDC Discovery는 API server 없이 검증 가능하지만 만료까지 기다려야 한다. IRSA가 OIDC Discovery를 쓰는 이유는 AWS STS가 K8s API server를 직접 호출하지 않아도 되게 하기 위해서다.

애플리케이션은 항상 수락할 audience를 정의하고, 토큰의 audience가 기대하는 값과 일치하는지 확인해야 한다. 토큰의 scope를 최소화하여 다른 곳에서 사용되는 것을 방지하기 위해서다.

## 현행 vs 레거시

지금까지 다룬 발급 → 전달 → 검증 흐름을 현행 방식과 레거시 방식으로 정리하면 다음과 같다.

| 단계 | 현행 (1.22+) | 레거시 |
| --- | --- | --- |
| **발급** | TokenRequest API: short-lived JWT, audience/expiration 지정, Pod 바인딩 | Secret 자동생성: 영구 JWT(exp 없음), etcd 저장 |
| **전달** | Projected Volume: tmpfs 마운트, 자동 rotation(만료 80% 시점) | Secret Volume: rotation 없음 |
| **검증** | TokenReview API: 서명+만료+참조 오브젝트+상태+audience | 동일 |

검증에는 **외부 경로**도 있다. K8s API server가 OIDC provider 역할을 하면서 `/.well-known/openid-configuration` 엔드포인트와 public key를 노출하는데, 외부 시스템(AWS IAM, Vault 등)이 이 public key로 SA JWT 서명을 직접 검증할 수 있다. TokenReview API를 호출할 필요 없이 외부에서 독립적으로 검증이 완결되는 구조다. EKS에서는 이것이 IRSA의 핵심 메커니즘이 된다.

레거시 토큰도 JWT이지만 `exp` claim이 없다. JWT 스펙(RFC 7519)에서 `exp`는 선택적이기 때문이다. Secret을 삭제하지 않는 한 **영원히 유효**하며, 대규모 클러스터에서는 SA마다 Secret이 etcd 부담을 늘리고 유출 표면적을 확대한다. 영구 토큰 자동 생성은 다음과 같이 폐지되었다.

- v1.24 이전: SA 생성 시 자동으로 영구 토큰 Secret 생성
- v1.24~v1.26: `LegacyServiceAccountTokenNoAutoGeneration` feature gate로 자동 생성 중단
- v1.27+: feature gate가 GA 승격. **자동 생성 완전 폐지**

수동으로 만들 수는 있지만, 위의 이유로 권장되지 않는다.

<br>

# Default SA와 Pod 할당

K8s는 모든 namespace마다 `default`라는 SA를 자동으로 만든다. 삭제해도 control plane이 **자동 재생성**한다. "모든 Pod은 반드시 어떤 SA identity를 가져야 한다"는 설계를 보장하기 위해서다.

## default SA의 권한

`default` SA는 RBAC에서 **API Discovery 권한** 외에는 별도 권한이 없다. API Discovery 권한은 `default` SA 고유가 아니라 **모든 authenticated principal**(인증된 주체 전체, Human User + SA 모두 포함)에게 자동 부여되는 것이다.

- `/api`, `/apis` 등의 엔드포인트를 GET하여 "이 클러스터에 어떤 리소스가 있는지" 조회하는 수준
- 실제 리소스(pods, deployments 등)를 읽거나 쓰는 권한은 **전혀 없다**
- `system:discovery`, `system:public-info-viewer` ClusterRoleBinding이 `system:authenticated` 그룹에 자동 부여된다

`default` SA에 RoleBinding으로 추가 권한을 줄 수는 있지만, **보안상 좋지 않다**. 해당 namespace에서 SA를 지정하지 않은 모든 Pod이 그 권한을 갖게 되기 때문이다. 용도별로 별도 SA를 만드는 것이 원칙이다.

## Pod당 SA 하나

**Pod에는 하나의 SA만 할당할 수 있다.** 여러 SA를 동시에 마운트하는 것은 불가능하다. custom SA를 지정하면 `default` SA는 완전히 대체된다(합산이 아님). API Discovery 권한은 모든 authenticated principal에게 부여되므로, 어떤 SA를 쓰든 항상 있다.

여러 권한이 필요한 경우, SA 여러 개를 합치는 게 아니라 **하나의 SA에 여러 RoleBinding을 연결**하면 된다.

## automountServiceAccountToken

Pod에 SA identity는 할당되지만 **토큰 마운트를 비활성화**할 수 있다.

```yaml
apiVersion: v1
kind: Pod
spec:
  serviceAccountName: my-sa
  automountServiceAccountToken: false
```

이렇게 하면 Pod에 credential이 없는 상태가 된다. API 서버에 접근할 필요 없는 Pod이라면 이렇게 설정하는 것이 보안상 좋다.

SA 자체를 없애지 않고 credential만 제거하는 이유가 궁금할 수 있다. K8s 설계상 모든 Pod은 반드시 SA identity를 가져야 한다. **Auditing**(누가 이 요청을 했는가), **Admission Control**(이 Pod의 SA에 대한 정책), **RBAC 평가** 등에서 주체 식별이 필요하기 때문이다.

<br>

# Use Cases

SA는 다양한 맥락에서 워크로드의 identity로 활용된다.

- **Pod → K8S API 서버**: Secret 읽기 전용 접근, cross-namespace 리소스 접근 등 (흐름 2)
- **Pod → 외부 서비스**: trust relationship이 설정된 시스템(AWS IRSA, Vault, GCP Workload Identity 등)에서 SA JWT를 인증 수단으로 활용 (흐름 3)
- **Private image registry 인증**: SA의 `imagePullSecrets` 필드에 registry 인증 정보를 연결하면, 해당 SA를 사용하는 모든 Pod이 자동 인증
- **외부 서비스 → K8S API 서버**: CI/CD 파이프라인에서 클러스터에 인증. long-lived SA 토큰을 쓸 수도 있지만, 탈취 시 만료 없이 무기한 사용 가능하고 audience binding이 없어 **권장되지 않는다**. 대안으로 X.509 클라이언트 인증서, custom authentication webhook, 또는 TokenRequest API로 short-lived 토큰을 발급받는 방법이 있다

<br>

# 정리

이 포스트에서 정리한 SA 토큰의 구조와 생명주기는 EKS의 세 가지 인증 흐름 중 **흐름 2(Pod → K8S API)**와 **흐름 3(Pod → AWS API)**의 기초가 된다.

- **흐름 2**: SA JWT → K8S API server가 TokenReview로 검증 → RBAC으로 인가
- **흐름 3**: SA JWT → audience를 `sts.amazonaws.com`으로 설정 → AWS STS가 OIDC Discovery로 검증 → IAM Role 발급

결국 흐름 3은 "K8S가 발급한 SA JWT를 AWS가 신뢰할 수 있게 만드는 것"이고, 이를 가능하게 하는 것이 EKS OIDC Provider와 TokenRequest의 audience binding이다.

<br>

# 참고 링크

- [Service Accounts](https://kubernetes.io/docs/concepts/security/service-accounts/)
- [Configure Service Accounts for Pods](https://kubernetes.io/docs/tasks/configure-pod-container/configure-service-account/)
- [Managing Service Accounts](https://kubernetes.io/docs/reference/access-authn-authz/service-accounts-admin/)
- [Projected Volumes](https://kubernetes.io/docs/concepts/storage/projected-volumes/)
