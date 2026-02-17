---
title:  "[Kubernetes] kubeconfig - 3. API Reference 톺아보기"
excerpt: "kubeconfig 파일의 전체 필드 스펙을 상세히 살펴보자."
categories:
  - Kubernetes
toc: true
header:
  teaser: /assets/images/blog-Dev.jpg
tags:
  - Kubernetes
  - kubeconfig
  - API Reference
  - AuthInfo
  - exec
---

<br>

# 들어가며

[kubeconfig 개요]({% post_url 2026-02-16-Kubernetes-Kubeconfig-01 %}) 글에서 kubeconfig의 핵심 구조와 주요 필드를 살펴보았다. 이 글에서는 [kubeconfig (v1) API Reference](https://kubernetes.io/docs/reference/config-api/kubeconfig.v1/)를 기반으로, kubeconfig 파일의 전체 필드 스펙을 상세히 톺아본다.

kubeconfig도 Kubernetes의 다른 리소스와 마찬가지로 정의된 API 스펙을 따른다. 최상위 객체인 `Config`를 중심으로, 이를 구성하는 `Cluster`, `AuthInfo`(users), `Context` 등의 타입을 하나씩 살펴보자.


<br>

# Config

**Config**는 kubeconfig 파일의 최상위 객체로, 원격 Kubernetes 클러스터에 연결하기 위해 필요한 정보를 담고 있다.

| 필드 | 타입 | 설명 |
| --- | --- | --- |
| `apiVersion` | string | `v1` 고정 |
| `kind` | string | `Config` 고정 |
| `clusters` **[Required]** | []NamedCluster | 참조 가능한 이름과 클러스터 설정의 맵. 클러스터 정보 목록 |
| `users` **[Required]** | []NamedAuthInfo | 참조 가능한 이름과 사용자 설정의 맵. 인증 정보 목록 |
| `contexts` **[Required]** | []NamedContext | 참조 가능한 이름과 컨텍스트 설정의 맵. 컨텍스트 목록 |
| `current-context` **[Required]** | string | 기본으로 사용할 컨텍스트의 이름 |
| `preferences` | Preferences | ~~일반 설정~~ (Kubernetes 1.34에서 deprecated) |
| `extensions` | []NamedExtension | 추가 정보를 담는 확장 필드 |

`clusters`, `users`, `contexts`는 각각 `NamedCluster`, `NamedAuthInfo`, `NamedContext`의 배열이다. 이 Named* 타입들은 단순히 `name` 필드와 실제 설정 객체를 묶는 wrapper이다. 예를 들어, `NamedCluster`는 `name`(string)과 `cluster`(Cluster 객체)를 가진다.


<br>

# Cluster

**Cluster**는 Kubernetes 클러스터와 통신하는 방법에 대한 정보를 담는다. `clusters[].cluster` 아래에 위치한다.

| 필드 | 타입 | 설명 |
| --- | --- | --- |
| `server` **[Required]** | string | Kubernetes 클러스터의 주소 (`https://hostname:port`) |
| `tls-server-name` | string | 서버 인증서를 검증할 때 사용할 서버 이름. 비어 있으면 서버에 접속할 때 사용한 hostname이 사용됨 |
| `insecure-skip-tls-verify` | bool | 서버 인증서의 유효성 검사를 건너뜀. **HTTPS 연결이 안전하지 않게 됨** |
| `certificate-authority` | string | CA 인증서 파일 경로 |
| `certificate-authority-data` | []byte | PEM 인코딩된 CA 인증서 데이터. `certificate-authority`보다 **우선** |
| `proxy-url` | string | 이 클라이언트의 모든 요청에 사용할 프록시 URL. `http`, `https`, `socks5` 스킴 지원 |
| `disable-compression` | bool | 서버로의 모든 요청에 대한 응답 압축을 비활성화. 클라이언트-서버 간 네트워크 대역폭이 충분할 때 압축/해제 시간을 절약하여 성능 향상 가능 |
| `extensions` | []NamedExtension | 추가 정보를 담는 확장 필드 |


## 주요 필드 상세

### server

클러스터 API 서버의 주소이다. `https://hostname:port` 형식이며, kubeconfig에서 가장 기본적인 필드이다.

### certificate-authority vs certificate-authority-data

두 필드 모두 API 서버의 TLS 인증서를 검증하기 위한 CA 인증서를 지정한다.

- `certificate-authority`: 파일 경로를 지정하는 방식
- `certificate-authority-data`: base64로 인코딩된 PEM 데이터를 kubeconfig 내에 인라인으로 포함하는 방식

**`-data` 필드가 있으면 파일 경로 필드를 무시**한다. 실무에서 kubeadm, EKS 등이 생성하는 kubeconfig는 대부분 `-data` 방식을 사용한다.

### insecure-skip-tls-verify

서버 인증서의 유효성 검사를 건너뛴다. 테스트 환경에서 자체 서명 인증서를 사용할 때 편의상 쓸 수 있지만, **운영 환경에서는 절대 사용하지 말아야** 한다. man-in-the-middle 공격에 취약해진다.

### proxy-url

클러스터 접근 시 프록시를 경유해야 하는 환경에서 사용한다. 설정하지 않으면 `http_proxy`, `https_proxy` 환경 변수를 참조한다.

> 참고: `socks5` 프록시는 현재 SPDY 스트리밍 엔드포인트(`exec`, `attach`, `port-forward`)를 지원하지 않는다.


<br>

# AuthInfo

**AuthInfo**는 사용자의 신원 정보를 담는다. `users[].user` 아래에 위치한다. API Reference에서의 타입 이름은 `AuthInfo`이지만, kubeconfig 파일에서는 `users` 섹션의 `user` 필드로 표현된다.

| 필드 | 타입 | 설명 |
| --- | --- | --- |
| `client-certificate` | string | TLS용 클라이언트 인증서 파일 경로 |
| `client-certificate-data` | []byte | PEM 인코딩된 클라이언트 인증서 데이터. `client-certificate`보다 **우선** |
| `client-key` | string | TLS용 클라이언트 개인 키 파일 경로 |
| `client-key-data` | []byte | PEM 인코딩된 클라이언트 개인 키 데이터. `client-key`보다 **우선** |
| `token` | string | Kubernetes 클러스터 인증을 위한 Bearer 토큰 |
| `tokenFile` | string | Bearer 토큰이 담긴 파일 경로 |
| `as` | string | Impersonate할 사용자 이름 |
| `as-uid` | string | Impersonate할 사용자 UID |
| `as-groups` | []string | Impersonate할 그룹 목록 |
| `as-user-extra` | map[string][]string | Impersonate할 사용자의 추가 정보 |
| `username` | string | ~~Basic 인증 사용자 이름~~ (deprecated) |
| `password` | string | ~~Basic 인증 비밀번호~~ (deprecated) |
| `auth-provider` | AuthProviderConfig | ~~커스텀 인증 플러그인~~ (deprecated) |
| `exec` | ExecConfig | exec 기반 인증 플러그인 설정 |

AuthInfo는 kubeconfig에서 가장 복잡한 타입이다. 인증 방식별로 상세히 살펴보자.


## mTLS (클라이언트 인증서) 방식

### 파일 경로 vs 인라인 데이터

| 파일 경로 필드 | 인라인 데이터 필드 | 우선순위 |
| --- | --- | --- |
| `client-certificate` | `client-certificate-data` | **data 우선** |
| `client-key` | `client-key-data` | **data 우선** |

설계 원칙은 다음과 같다:
- **파일 경로 방식** (`client-certificate`): 인증서를 별도 파일로 관리. 파일 시스템에 의존한다.
- **인라인 방식** (`client-certificate-data`): base64로 인코딩된 인증서 내용을 kubeconfig 안에 직접 포함. **파일 하나로 완결**되어 이동성이 좋다.

```yaml
# 파일 경로 방식
users:
- name: my-user
  user:
    client-certificate: /path/to/client.crt
    client-key: /path/to/client.key

# 인라인 방식
users:
- name: my-user
  user:
    client-certificate-data: LS0tLS1CRUdJTi...
    client-key-data: LS0tLS1CRUdJTi...
```

mTLS 방식은 [Kubernetes PKI]({% post_url 2026-01-18-Kubernetes-PKI %})에서 다루는 인증서 체계와 직접 연관된다. API 서버의 CA가 발급한 클라이언트 인증서를 사용하여 양방향 TLS 인증을 수행한다.


## Bearer Token 방식

### token vs tokenFile

| 필드 | 방식 | 특징 |
| --- | --- | --- |
| `token` | 토큰 문자열을 직접 기입 | 고정값. kubeconfig 수정 전까지 안 바뀜 |
| `tokenFile` | 토큰이 담긴 파일 경로를 지정 | **주기적으로 파일을 다시 읽음** → 토큰 갱신 시 자동 반영 |

둘 다 있으면 **`tokenFile`에서 마지막으로 성공적으로 읽은 값**이 `token`보다 우선한다.

mTLS 방식에서는 인라인(`-data`)이 우선이었는데, 토큰에서는 파일(`tokenFile`)이 우선이다. 우선순위 방향이 반대인 이유는, `tokenFile`이 주기적으로 다시 읽는 **동적 소스**이므로 더 최신값을 가지고 있을 가능성이 높기 때문이다.

### tokenFile의 대표적 사용 사례

- **Pod 내부에서 실행되는 컴포넌트**: Pod에 마운트된 ServiceAccount 토큰(`/var/run/secrets/kubernetes.io/serviceaccount/token`)은 kubelet이 주기적으로 갱신한다. `tokenFile`로 이 파일을 가리키면 갱신된 토큰을 자동으로 읽어 간다.
- **kubelet 자체**: kubelet이 bootstrap 후 토큰 로테이션을 받을 때

```yaml
# token (직접 기입) - CI/CD, 고정 토큰 사용 시
users:
- name: ci-bot
  user:
    token: eyJhbGciOiJSUzI1NiIs...

# tokenFile (파일 참조) - 토큰 자동 갱신 환경에서
users:
- name: in-cluster
  user:
    tokenFile: /var/run/secrets/kubernetes.io/serviceaccount/token
```


## exec 방식

### ExecConfig

kubectl이 **외부 명령어를 실행**하여 인증 정보를 동적으로 가져오는 방식이다.

| 필드 | 타입 | 설명 |
| --- | --- | --- |
| `command` **[Required]** | string | 실행할 명령어 |
| `args` | []string | 명령어에 전달할 인자 |
| `env` | []ExecEnvVar | 프로세스에 노출할 추가 환경 변수 |
| `apiVersion` **[Required]** | string | exec 정보의 선호 입력 버전 |
| `installHint` | string | 명령어가 없을 때 설치 방법을 안내하는 텍스트 |
| `provideClusterInfo` | bool | 클러스터 정보를 KUBERNETES_EXEC_INFO 환경 변수로 전달할지 여부 |
| `interactiveMode` | ExecInteractiveMode | 표준 입력(stdin)을 프로세스에 전달할지 결정 |

동작 흐름은 다음과 같다:

1. kubectl이 `command`를 `args`와 함께 실행
2. 명령어가 stdout으로 `ExecCredential` JSON을 출력
3. kubectl이 이 JSON에서 토큰(또는 인증서)을 꺼내 사용

```yaml
users:
- name: eks-user
  user:
    exec:
      apiVersion: client.authentication.k8s.io/v1beta1
      command: aws
      args:
        - eks
        - get-token
        - --cluster-name
        - my-cluster
      env:
        - name: AWS_PROFILE
          value: my-profile
```

### exec가 auth-provider를 대체한 이유

이전에는 kubectl에 내장된 인증 플러그인을 사용하는 `auth-provider` 방식이 있었다.

```yaml
# auth-provider (deprecated)
users:
- name: gke-user
  user:
    auth-provider:
      name: gcp
      config:
        access-token: ya29.xxx...
        expiry: "2024-01-01T00:00:00Z"
```

문제는 클라우드 벤더마다 플러그인을 kubectl 코어에 내장해야 했다는 점이다. **Kubernetes 1.26+에서 deprecated**되었고, `exec`로의 전환이 권장된다.

`exec` 방식의 장점:
- kubectl 코어에 벤더별 코드를 넣을 필요 없음 → **플러그인이 독립 바이너리**
- 어떤 인증 시스템이든 명령어만 만들면 연동 가능 → **확장성**
- 토큰 만료 시 자동으로 다시 exec해서 갱신 → **동적 인증**

### 클라우드별 exec 사용 예시

| 클라우드 | exec command | 설명 |
| --- | --- | --- |
| **AWS EKS** | `aws eks get-token` | AWS IAM → K8s 토큰 변환 |
| **GCP GKE** | `gke-gcloud-auth-plugin` | `auth-provider: gcp`에서 전환된 방식 |
| **Azure AKS** | `kubelogin` | Azure AD 인증 |


## Impersonation 필드

다른 사용자로 가장하여 API 요청을 보내는 기능이다. 주로 관리자가 특정 사용자의 권한을 테스트하거나 디버깅할 때 사용한다.

| 필드 | 설명 |
| --- | --- |
| `as` | 가장할 사용자 이름 |
| `as-uid` | 가장할 사용자 UID |
| `as-groups` | 가장할 그룹 목록 |
| `as-user-extra` | 가장할 사용자의 추가 정보 |

```yaml
users:
- name: admin-impersonating-dev
  user:
    client-certificate: /certs/admin.crt
    client-key: /certs/admin.key
    as: dev-user
    as-groups:
      - developers
```

이렇게 설정하면 관리자 인증서로 인증하되, API 서버에는 `dev-user`(developers 그룹)로 요청을 보낸다. 물론, 실제 admin 사용자에게 impersonation 권한(RBAC)이 부여되어 있어야 한다.


## username / password (deprecated)

kubeconfig API Reference에 `username`/`password` 필드가 존재하지만, 이는 이미 deprecated된 Basic Authentication 방식의 흔적이다.

- **Kubernetes 1.16**에서 `--basic-auth-file` 플래그가 deprecated
- **Kubernetes 1.19**에서 완전히 **삭제**됨
- 이유:
  - 비밀번호가 평문(또는 CSV 파일)으로 저장됨 → 보안 취약
  - 비밀번호 변경 시 API 서버를 재시작해야 함
  - mTLS나 토큰 기반 인증에 비해 보안성이 현저히 낮음

현재 버전의 Kubernetes API 서버는 이 인증 방식을 지원하지 않으므로, 사실상 사용 불가능하다.


## 인증 방식 충돌 규칙

하나의 user 항목에는 **한 가지 인증 방식만** 허용된다. kubectl 설정 해석 시, 충돌하는 두 가지 인증 기법이 있으면 실패한다.

예를 들어, `client-certificate`와 `token`을 동시에 넣으면 kubectl이 에러를 발생시킨다.

| 인증 방식 | 사용 필드 | 대표 사용처 |
| --- | --- | --- |
| **mTLS** | `client-certificate` + `client-key` | kubeadm, kubelet, 컴포넌트 |
| **Bearer Token** | `token` 또는 `tokenFile` | ServiceAccount, OIDC, CI/CD |
| **exec** | `exec` | 클라우드 환경 (EKS, GKE, AKS) |
| **auth-provider** (deprecated) | `auth-provider` | 과거 클라우드 환경 |


<br>

# Context

**Context**는 클러스터(어디에 접속하는지), 사용자(누구로 인증하는지), 네임스페이스(어떤 리소스 범위에서 작업하는지)의 조합이다. `contexts[].context` 아래에 위치한다.

| 필드 | 타입 | 설명 |
| --- | --- | --- |
| `cluster` **[Required]** | string | 이 컨텍스트에 사용할 클러스터의 이름 |
| `user` **[Required]** | string | 이 컨텍스트에 사용할 AuthInfo(인증 정보)의 이름 |
| `namespace` | string | 요청에 네임스페이스가 지정되지 않았을 때 사용할 기본 네임스페이스 |
| `extensions` | []NamedExtension | 추가 정보를 담는 확장 필드 |

API Reference에서 `user` 필드의 설명은 "AuthInfo is the name of the authInfo for this context"이다. kubeconfig 파일의 `users` 섹션에서 정의한 이름을 참조하는 것이다.

`namespace`를 지정하면 `kubectl get pods` 같은 명령어 실행 시 `-n` 플래그 없이도 해당 네임스페이스가 기본으로 사용된다. 생략 시 `default` 네임스페이스가 사용된다.


<br>

# NamedExtension

**NamedExtension**은 kubeconfig의 확장성을 위한 필드이다. `Config`, `Cluster`, `Context` 등 여러 객체에 `extensions` 필드로 존재한다.

| 필드 | 타입 | 설명 |
| --- | --- | --- |
| `name` **[Required]** | string | 확장의 이름 |
| `extension` **[Required]** | RawExtension | 확장 데이터 |

주로 서드파티 도구나 플러그인이 kubeconfig에 자체 정보를 저장할 때 사용한다. kubectl 자체는 이 필드를 읽거나 쓰지 않으며, 확장 도구가 unknown 필드를 덮어쓰지 않도록 보호하는 역할을 한다.


<br>

# 전체 필드 우선순위 정리

kubeconfig 필드 간 우선순위를 정리하면 다음과 같다.

| 구분 | 파일 경로 | 인라인 데이터/파일 | 우선순위 | 이유 |
| --- | --- | --- | --- | --- |
| **CA 인증서** | `certificate-authority` | `certificate-authority-data` | data 우선 | 정적 데이터. 인라인이 이동성 좋음 |
| **클라이언트 인증서** | `client-certificate` | `client-certificate-data` | data 우선 | 정적 데이터. 인라인이 이동성 좋음 |
| **클라이언트 키** | `client-key` | `client-key-data` | data 우선 | 정적 데이터. 인라인이 이동성 좋음 |
| **Bearer Token** | `tokenFile` | `token` (인라인) | **tokenFile 우선** | tokenFile이 동적 소스 (자동 갱신) |

인증서 계열은 **인라인(-data)이 우선**이고, 토큰은 **파일(tokenFile)이 우선**이다. 차이는 토큰이 동적으로 갱신될 수 있다는 점에서 비롯된다.


<br>

# 결론

- **Config**: `clusters` / `users` / `contexts` / `current-context` 필수. preferences는 1.34부터 deprecated.
- **Cluster·AuthInfo·Context**: server, 인증 수단(인증서·token·exec 등), cluster/user 조합을 정의. 인증서·키는 `-data` 인라인이 경로보다 우선, 토큰은 `tokenFile`이 `token`보다 우선.
- **exec**: 동적 인증용. auth-provider, username/password는 deprecated.

<br>

# 맺으며

평소에는 kubeadm이나 클라우드가 만들어 주는 kubeconfig를 그대로 쓰는 경우가 많지만, 디버깅이나 커스텀 인증 시 필드 의미를 아는 것이 중요하다. 개념·구조는 [kubeconfig 개요]({% post_url 2026-02-16-Kubernetes-Kubeconfig-01 %}), 실습은 [다중 클러스터 접근 구성 실습]({% post_url 2026-02-16-Kubernetes-Kubeconfig-02 %}), 공식 스펙은 [kubeconfig (v1) API Reference](https://kubernetes.io/docs/reference/config-api/kubeconfig.v1/)를 참고하자.
