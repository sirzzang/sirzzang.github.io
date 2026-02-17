---
title:  "[Kubernetes] kubeconfig - 1. 개요"
excerpt: "Kubernetes 클러스터 접근 설정 파일인 kubeconfig의 개념, 구조, 사용법에 대해 알아보자."
categories:
  - Kubernetes
toc: true
header:
  teaser: /assets/images/blog-Dev.jpg
tags:
  - Kubernetes
  - kubeconfig
  - kubectl
  - Context
---

<br>

# 들어가며

Kubernetes 클러스터를 사용하다 보면, `kubectl get pods` 같은 명령어가 어떻게 올바른 클러스터의 올바른 API 서버로 연결되는지 궁금해질 때가 있다. 이 연결 정보를 관리하는 것이 바로 **kubeconfig** 파일이다.

[Kubernetes 공식 문서](https://kubernetes.io/ko/docs/concepts/configuration/organize-cluster-access-kubeconfig/)에 따르면, kubeconfig 파일을 사용하여 클러스터, 사용자, 네임스페이스 및 인증 메커니즘에 대한 정보를 관리할 수 있다. `kubectl` 커맨드라인 도구는 kubeconfig 파일을 사용하여 클러스터를 선택하고 클러스터의 API 서버와 통신하는 데 필요한 정보를 찾는다.

이 글에서는 kubeconfig의 개념, 파일 구조, 사용법, 그리고 Best Practice에 대해 정리한다. 각 필드의 상세한 API Reference는 [별도 글]({% post_url 2026-02-16-Kubernetes-Kubeconfig-03 %})에서 다루고, 다중 클러스터 접근 구성 실습은 [다음 글]({% post_url 2026-02-16-Kubernetes-Kubeconfig-02 %})에서 진행한다.


<br>

# 개념

## 정의

kubeconfig란, **Kubernetes 클러스터에 접근하기 위한 설정 정보를 담은 YAML 파일**이다. 더 정확히 말하면, 어떤 클러스터의 API 서버에 어떤 인증 정보로 통신할지를 정의하는 파일이다.

참고로 "kubeconfig"는 **파일 이름이 아니라 개념적 용어**이다. 클러스터 접근 설정을 담고 있는 파일을 통칭하여 kubeconfig라고 부르는 것이며, 실제 파일 이름은 `config`, `admin.conf`, `kubelet.conf` 등 다양할 수 있다.

여기서 **"Kubernetes 클러스터에 접근한다"는 것은 곧 "API 서버에 접근한다"**는 것과 사실상 동일하다. Kubernetes에서 모든 작업은 API 서버를 통해 이루어지기 때문이다. `kubectl`이든, `kubelet`이든, `kube-scheduler`든, 클러스터에 뭔가를 하려면 **반드시 API 서버와 통신**해야 한다. API 서버가 클러스터의 **유일한 진입점(single entry point)**이기 때문이다.


## 사용 주체

Kubernetes API 서버에 접근하는 주체는 크게 두 부류로 나눌 수 있다.

| 구분 | 예시 | 설명 |
| --- | --- | --- |
| **구성 요소**(컴포넌트) | kubelet, kube-scheduler, kube-controller-manager | 클러스터 내부에서 자동으로 동작하는 시스템 컴포넌트 |
| **사용자**(사람) | 개발자, 운영자, 관리자 | kubectl 등을 통해 수동으로 접근하는 사람 |


### 컴포넌트용 kubeconfig

컴포넌트는 각자 전용 kubeconfig를 사용하여 API 서버에 인증한다.

| 파일 | 사용 주체 | 용도 |
| --- | --- | --- |
| `admin.conf` | 관리자 (kubectl) | 클러스터 전체 관리 권한 |
| `kubelet.conf` | kubelet | 노드에서 API 서버와 통신 |
| `controller-manager.conf` | kube-controller-manager | 컨트롤러 매니저가 API 서버와 통신 |
| `scheduler.conf` | kube-scheduler | 스케줄러가 API 서버와 통신 |

이 파일들은 전부 동일한 kubeconfig 포맷을 따른다. 예를 들어, kubeadm으로 설치한 클러스터에서 kubelet의 kubeconfig를 보면 다음과 같다.

```yaml
apiVersion: v1
kind: Config
clusters:
- cluster:
    certificate-authority-data: LS0tLS1CRUdJTi...  # base64 인코딩된 CA 인증서
    server: https://192.168.56.13:6443
  name: default-cluster
contexts:
- context:
    cluster: default-cluster
    namespace: default
    user: default-auth
  name: default-context
current-context: default-context
users:
- name: default-auth
  user:
    client-certificate: /var/lib/kubelet/pki/kubelet-client-current.pem
    client-key: /var/lib/kubelet/pki/kubelet-client-current.pem
```

컴포넌트용 kubeconfig는 클러스터 프로비저닝 도구에 의해 자동 생성되거나(kubeadm 등), 직접 수동으로 생성한다. Kubernetes PKI 인증서를 기반으로 생성되며, 자세한 내용은 [Kubernetes PKI]({% post_url 2026-01-18-Kubernetes-PKI %}) 글을 참고하자. 한 번 만들어지면 사용자가 직접 건드릴 일은 거의 없다.


### 사용자용 kubeconfig

쿠버네티스 클러스터를 이용하는 사람이 매일 사용하는 것은 **사용자용 kubeconfig**이다. 컴포넌트와 마찬가지로, 사용자도 kubeconfig를 통해 API 서버에 인증한다.

- `admin.conf`: 클러스터 관리자가 처음에 받는 전체 권한 kubeconfig
- 관리자가 개별 사용자별로 제한된 권한의 kubeconfig를 별도로 생성해서 배포
  - 예: dev 팀에게는 dev namespace만 접근 가능한 kubeconfig
  - 예: readonly 권한만 있는 kubeconfig
- 사용자는 이런 kubeconfig를 받아서 클러스터에 접근하면 됨
- 사용자용 kubeconfig가 여러 개라면, `~/.kube/config`에 모아서 context를 전환하며 사용하면 됨


### 핵심: 포맷은 동일하다

사용자든 컴포넌트든 **같은 kubeconfig 포맷**을 사용한다. 위에서 본 kubelet의 kubeconfig와, 사용자가 `~/.kube/config`에 두고 쓰는 kubeconfig를 비교해 보면 구조가 동일하다는 것을 알 수 있다. `apiVersion`, `kind`, `clusters`, `users`, `contexts`, `current-context` — 모두 같은 필드를 사용한다.

차이는 **누가 읽느냐**와 **어떤 인증 정보가 들어 있느냐**뿐이다.

| 구분 | 읽는 주체 | 인증 정보 예시 | 생성/관리 |
| --- | --- | --- | --- |
| **컴포넌트용** | kubelet, scheduler 등 | 클라이언트 인증서(mTLS) | 프로비저닝 도구가 자동 생성. 이후 거의 수정하지 않음 |
| **사용자용** | kubectl 등 | 인증서, 토큰, exec 등 다양 | 관리자가 배포하거나, 클라우드 CLI가 생성 |

즉, kubeconfig라는 하나의 포맷이 Kubernetes 클러스터 접근 설정의 **공용어** 역할을 하는 것이다. 이 구조를 이해하면 컴포넌트의 kubeconfig를 읽을 때도, 사용자용 kubeconfig를 직접 작성할 때도 동일한 관점에서 접근할 수 있다.


<br>

# 필요성

왜 kubeconfig라는 별도의 설정 파일이 필요할까? [공식 문서](https://kubernetes.io/ko/docs/concepts/configuration/organize-cluster-access-kubeconfig/#%EB%8B%A4%EC%A4%91-%ED%81%B4%EB%9F%AC%EC%8A%A4%ED%84%B0-%EC%82%AC%EC%9A%A9%EC%9E%90%EC%99%80-%EC%9D%B8%EC%A6%9D-%EB%A9%94%EC%BB%A4%EB%8B%88%EC%A6%98-%EC%A7%80%EC%9B%90)에서 이야기하는 상황을 보자.

> 여러 클러스터가 있고, 사용자와 구성 요소가 다양한 방식으로 인증한다고 가정하자. 예를 들면 다음과 같다.
>
> - 실행 중인 kubelet은 인증서를 이용하여 인증할 수 있다.
> - 사용자는 토큰으로 인증할 수 있다.
> - 관리자는 개별 사용자에게 제공하는 인증서 집합을 가지고 있다.

즉, 현실의 Kubernetes 환경에서는 **클러스터도 여러 개**이고, **접근 주체도 여러 종류**이며, **인증 방식도 제각각**이다. kubeconfig는 이 복잡성을 두 가지 측면에서 해결한다.


## 인증 방식의 표준화

API 서버에 접근하려면 인증이 필요한데, 공식 문서가 보여 주듯 인증 방식이 다양하다. kubeconfig는 이 다양한 방식을 **하나의 포맷** 안에서 표현할 수 있게 해 준다. `users` 섹션에 어떤 필드를 작성하느냐에 따라 인증 방식이 달라질 뿐, 파일 구조 자체는 동일하다.

공식 문서의 세 가지 시나리오가 kubeconfig에서 어떻게 표현되는지 보자.

<br>

**1. kubelet은 인증서를 이용하여 인증할 수 있다.**

kubelet은 각 노드에서 Pod을 관리하는 에이전트로, API 서버와 통신 시 **클라이언트 인증서(mTLS)**를 사용한다.

```yaml
users:
- name: kubelet-node01
  user:
    client-certificate: /var/lib/kubelet/pki/kubelet-client.crt
    client-key: /var/lib/kubelet/pki/kubelet-client.key
```

<br>

**2. 사용자는 토큰으로 인증할 수 있다.**

일반 개발자가 kubectl로 접근할 때 **Bearer Token**을 사용하는 경우이다. ServiceAccount 토큰, OIDC 토큰 등이 이에 해당한다.

```yaml
users:
- name: developer
  user:
    token: eyJhbGciOiJSUzI1NiIs...
```

<br>

**3. 관리자는 개별 사용자에게 제공하는 인증서 집합을 가지고 있다.**

클러스터 관리자가 각 사용자별로 별도의 클라이언트 인증서를 발급하여, 사용자마다 다른 인증서로 다른 권한(RBAC)을 갖게 하는 경우이다.

```yaml
users:
- name: admin
  user:
    client-certificate: /certs/admin.crt
    client-key: /certs/admin.key
- name: dev-user
  user:
    client-certificate: /certs/dev.crt
    client-key: /certs/dev.key
```

<br>

이처럼 mTLS든 토큰이든, kubeconfig의 `users` 섹션에 해당 필드만 채우면 된다. 인증 방식이 달라져도 파일을 읽는 쪽(kubectl, kubelet 등)은 같은 구조를 파싱하면 되므로, **접근 설정의 표준화**가 이루어진다.


## 다중 클러스터 × 다중 사용자 조합 관리

인증 방식이 표준화되었다면, 그 다음 문제는 **조합**이다. 클러스터가 여러 개이고 사용자도 여러 명이면 "어떤 클러스터에 어떤 인증 정보로 접근할지"를 관리해야 한다.

kubeconfig는 이를 `clusters`(어디에), `users`(누구로), `contexts`(둘의 조합)라는 세 배열로 해결한다. N개의 클러스터와 M명의 사용자를 각각 정의해 두고, 필요한 조합만 context로 만들면 된다. 그리고 `kubectl config use-context`로 빠르게 전환할 수 있다.

공식 문서도 이 설계 의도를 다음과 같이 말하고 있다.

> kubeconfig 파일을 사용하면 클러스터와 사용자와 네임스페이스를 구성할 수 있다. 또한 컨텍스트를 정의하여 빠르고 쉽게 클러스터와 네임스페이스 간에 전환할 수 있다.

정리하면, kubeconfig의 필요성은 **다양한 인증 방식을 하나의 포맷으로 표준화**하고, **다중 클러스터 × 다중 사용자 조합을 체계적으로 관리**할 수 있다는 데 있다. 이 필요성이 kubeconfig의 구조 설계에 그대로 반영되어 있다.


<br>

# 구조

## 전체 구조

kubeconfig 파일은 다음과 같은 YAML 구조를 가진다.

```yaml
apiVersion: v1
kind: Config
current-context: my-context

clusters:
- name: my-cluster
  cluster:
    server: https://k8s.example.com:6443
    certificate-authority: /path/to/ca.crt

users:
- name: my-user
  user:
    client-certificate: /path/to/client.crt
    client-key: /path/to/client.key

contexts:
- name: my-context
  context:
    cluster: my-cluster
    user: my-user
    namespace: default
```

각 필드의 의미는 다음과 같다.

| 필드 | 설명 |
| --- | --- |
| `apiVersion` | `v1` 고정. kubeconfig 파일의 API 버전 |
| `kind` | `Config` 고정. kubeconfig 파일임을 나타냄 |
| `current-context` | 현재 활성 컨텍스트. kubectl 기본 동작에 사용됨 |
| `clusters` | 접속할 클러스터 정보 목록 (API 서버 주소, CA 인증서 등) |
| `users` | 인증 정보 목록 (클라이언트 인증서, 토큰 등) |
| `contexts` | cluster + user + namespace를 하나로 묶은 **바로가기** 목록 |

핵심은 `clusters`, `users`, `contexts` 세 섹션이다. 하나씩 살펴보자.

> 각 필드의 세부 API Reference는 [kubeconfig API Reference 톺아보기]({% post_url 2026-02-16-Kubernetes-Kubeconfig-03 %}) 글에서 상세히 다룬다.


## clusters

클러스터 정보를 정의한다. API 서버의 주소와 CA 인증서 등을 포함한다.

```yaml
clusters:
- name: my-cluster
  cluster:
    server: https://k8s.example.com:6443
    certificate-authority: /path/to/ca.crt
```

- `server`: Kubernetes API 서버의 주소 (`https://hostname:port`)
- `certificate-authority`: API 서버의 인증서를 검증하기 위한 CA 인증서 경로
- `certificate-authority-data`: CA 인증서를 base64로 인코딩하여 파일 안에 직접 내장하는 방식. `certificate-authority`보다 우선한다


## users

API 서버에 대한 인증 정보를 정의한다. `users`라는 이름이지만, 사람만을 의미하는 것이 아니라 **API 서버에 접근하는 모든 주체**의 인증 정보라고 보면 된다.

주요 인증 방식은 다음과 같다.


### mTLS (클라이언트 인증서) 방식

클라이언트가 자신의 인증서와 개인 키를 제시하고, API 서버가 CA로 검증하는 **양방향 TLS(mTLS)** 방식이다. kubeadm이 생성하는 `admin.conf`가 대표적인 예이다.

```yaml
users:
- name: my-user
  user:
    client-certificate: /path/to/client.crt
    client-key: /path/to/client.key
```

파일 경로 방식(`client-certificate`) 외에 인라인 방식(`client-certificate-data`)도 있다. 인라인 방식은 base64로 인코딩된 인증서 내용을 kubeconfig 파일 안에 직접 포함하는 것으로, `-data` 필드가 있으면 파일 경로 필드를 무시한다.

| 파일 경로 필드 | 인라인 데이터 필드 | 우선순위 |
| --- | --- | --- |
| `client-certificate` | `client-certificate-data` | **data 우선** |
| `client-key` | `client-key-data` | **data 우선** |
| `certificate-authority` | `certificate-authority-data` | **data 우선** |

실무에서 kubeadm이나 EKS 등이 생성하는 kubeconfig는 거의 다 `-data` 필드를 사용한다. 파일 하나로 완결되어 이동성이 좋고, 경로 해석 문제가 없기 때문이다.


### Bearer Token 방식

HTTP 헤더에 `Authorization: Bearer <token>`을 실어 보내는 방식이다. ServiceAccount 토큰, OIDC 토큰, 정적 토큰 등이 여기에 해당한다.

```yaml
users:
- name: my-user
  user:
    token: eyJhbGciOiJSUzI1NiIs...
```

`tokenFile`을 사용하면 파일에서 주기적으로 토큰을 읽어 자동 갱신도 가능하다.

| 필드 | 방식 | 특징 |
| --- | --- | --- |
| `token` | 토큰 문자열을 직접 기입 | 고정값. kubeconfig 수정 전까지 안 바뀜 |
| `tokenFile` | 토큰이 담긴 파일 경로를 지정 | 주기적으로 파일을 다시 읽음 → 토큰 갱신 시 자동 반영 |

둘 다 있으면 `tokenFile`에서 마지막으로 성공적으로 읽은 값이 `token`보다 우선한다. mTLS 방식에서 인라인(`-data`)이 우선이었던 것과 **우선순위 방향이 반대**인데, 이는 `tokenFile`이 주기적으로 다시 읽는 동적 소스이므로 더 최신값을 가지고 있을 가능성이 높기 때문이다.

> `tokenFile`의 대표적 사용처는 Pod 내부에서 마운트되는 ServiceAccount 토큰(`/var/run/secrets/kubernetes.io/serviceaccount/token`)이다. Kubernetes 1.21+부터 ServiceAccount 토큰은 기본적으로 시간 제한 있는 bound token이므로, `tokenFile`로 파일을 가리키면 kubelet이 갱신한 새 토큰을 자동으로 읽어 끊김 없이 통신할 수 있다.


### exec 방식

kubectl이 **외부 명령어를 실행**하여 인증 정보(토큰 등)를 동적으로 받아오는 방식이다. kubeconfig에 토큰이나 인증서를 직접 넣는 것이 아니라, 매번 외부 명령어가 동적으로 토큰을 발급하는 것이 핵심이다. 클라우드 환경에서 가장 흔히 볼 수 있다.

AWS EKS를 예로 들면, `aws eks update-kubeconfig`를 실행하면 다음과 같은 kubeconfig가 생성된다.

```yaml
apiVersion: v1
kind: Config
clusters:
- name: my-eks-cluster
  cluster:
    server: https://ABCDEF1234567890.gr7.ap-northeast-2.eks.amazonaws.com
    certificate-authority-data: LS0tLS1CRUdJTi...
contexts:
- name: arn:aws:eks:ap-northeast-2:123456789012:cluster/my-eks-cluster
  context:
    cluster: my-eks-cluster
    user: arn:aws:eks:ap-northeast-2:123456789012:cluster/my-eks-cluster
current-context: arn:aws:eks:ap-northeast-2:123456789012:cluster/my-eks-cluster
users:
- name: arn:aws:eks:ap-northeast-2:123456789012:cluster/my-eks-cluster
  user:
    exec:
      apiVersion: client.authentication.k8s.io/v1beta1
      command: aws
      args:
        - eks
        - get-token
        - --cluster-name
        - my-eks-cluster
        - --region
        - ap-northeast-2
      env:
        - name: AWS_PROFILE
          value: my-profile
      interactiveMode: Never
      provideClusterInfo: false
```

`users` 섹션에 `client-certificate`나 `token` 같은 정적 인증 정보가 없고, `exec` 블록만 있다는 점에 주목하자. 동작 흐름은 다음과 같다.

1. `kubectl get pods` 등 명령어 실행
2. kubectl이 `exec` 블록을 읽고 `aws eks get-token --cluster-name my-eks-cluster --region ap-northeast-2`를 실행
3. `aws` CLI가 AWS IAM 자격 증명으로 임시 토큰을 생성하여 stdout에 JSON(`ExecCredential`)으로 출력
4. kubectl이 그 JSON에서 토큰을 꺼내 `Authorization: Bearer <token>` 헤더에 실어 API 서버로 요청
5. 토큰이 만료되면 다음 요청 시 자동으로 다시 exec하여 새 토큰을 받아옴

GKE나 AKS도 `command`와 `args`만 다를 뿐 같은 구조이다.

| 클라우드 | exec command | 설명 |
| --- | --- | --- |
| **AWS EKS** | `aws eks get-token` | AWS IAM → K8s 토큰 변환 |
| **GCP GKE** | `gke-gcloud-auth-plugin` | `auth-provider: gcp`에서 전환된 방식 |
| **Azure AKS** | `kubelogin` | Azure AD 인증 |

참고로, 이전에는 kubectl에 내장된 인증 플러그인을 사용하는 `auth-provider` 방식이 있었으나, 클라우드 벤더마다 플러그인을 kubectl 코어에 내장해야 하는 유지보수 부담 때문에 **Kubernetes 1.26+에서 deprecated**되었다. `exec`는 kubectl 코어에 벤더별 코드를 넣을 필요 없이, 어떤 인증 시스템이든 명령어만 만들면 연동할 수 있어 확장성이 좋다.


### 인증 방식 요약

하나의 user 항목에는 **한 가지 인증 방식만** 사용해야 한다. 예를 들어, `client-certificate`와 `token`을 동시에 넣으면 kubectl이 에러를 발생시킨다.

| 인증 방식 | kubeconfig 필드 | 대표 사용처 |
| --- | --- | --- |
| **mTLS** (클라이언트 인증서) | `client-certificate`, `client-key` | kubeadm admin, kubelet, 컴포넌트 |
| **Bearer Token** | `token` 또는 `tokenFile` | ServiceAccount, OIDC, CI/CD |
| **exec** (외부 명령어) | `exec` | 클라우드 환경 (EKS, GKE, AKS) |


## contexts

`clusters`에 정의된 클러스터와 `users`에 정의된 사용자를 **조합**하여, 하나의 접근 단위로 묶는 것이 context이다. 선택적으로 기본 namespace도 지정할 수 있다.

```yaml
contexts:
- name: dev-admin
  context:
    cluster: cluster-dev       # clusters에서 정의한 이름
    user: admin-user           # users에서 정의한 이름
    namespace: default

- name: prod-readonly
  context:
    cluster: cluster-prod
    user: readonly-user
    namespace: monitoring
```

- `cluster`: `clusters` 섹션에 정의된 클러스터의 이름(name)을 참조
- `user`: `users` 섹션에 정의된 사용자의 이름(name)을 참조
- `namespace`: 해당 컨텍스트에서 기본으로 사용할 네임스페이스 (생략 시 `default`)


### context 조합의 핵심

`clusters`, `users`, `contexts`는 모두 **배열**(리스트)이므로, 각각 여러 개 정의할 수 있다. N개의 클러스터와 M명의 사용자 중 필요한 조합만 context로 만들면 된다.

다만, context 조합이 올바른지는 **사용자 책임**이다. kubectl은 kubeconfig에 적힌 대로 연결을 시도할 뿐, 조합의 유효성까지 검증해 주지 않는다. 잘못 작성하면 다음과 같은 에러가 발생한다.

| 잘못된 경우 | 결과 |
| --- | --- |
| context에서 참조하는 cluster나 user **이름이 실제로 정의되어 있지 않을 때** | kubectl이 해당 정보를 찾지 못해 에러 |
| cluster A의 API 서버에 user B의 인증 정보가 **등록되어 있지 않을 때** | 인증 실패 (Unauthorized) |
| 존재하지 않는 namespace를 기본값으로 지정했을 때 | 해당 namespace의 리소스 조회 시 에러 |

kubectl은 kubeconfig를 파싱하여 연결 정보를 조립하는 클라이언트일 뿐이고, "이 user가 이 cluster에 접근 권한이 있는지" 같은 인증/인가(RBAC) 검증은 **API 서버 측**에서 이루어진다.


## current-context

`current-context`는 현재 활성화된 컨텍스트의 이름이다. kubeconfig를 읽는 주체(kubectl, kubelet 등)는 이 필드를 보고 어떤 context를 사용할지 결정한다.

위에서 본 kubelet의 kubeconfig 예시에서도 `current-context: default-context`가 있었다. 컴포넌트용 kubeconfig는 클러스터/사용자/컨텍스트가 각각 하나뿐이므로 "전환"의 의미보다는 포맷 일관성을 위해 존재한다. 반면, 사용자용 kubeconfig에서는 여러 컨텍스트 중 **기본으로 사용할 것**을 지정하는 역할을 한다.

### kubectl에서의 동작

`current-context`가 kubectl 사용에 미치는 영향은 직접적이다. kubectl은 명령어를 실행할 때, 별도 지정이 없으면 `current-context`에 명시된 컨텍스트를 사용한다. 이 컨텍스트가 가리키는 cluster의 `server` 필드가 곧 kubectl이 연결할 API 서버 주소가 된다.

좀 더 정확히는, kubectl이 API 서버를 결정하는 우선순위는 다음과 같다:

1. `--server` 플래그 → 있으면 그것을 사용
2. kubeconfig의 `current-context` → context가 가리키는 cluster의 `server` 필드
3. 둘 다 없으면 → `http://localhost:8080`으로 fallback

`--server` 플래그를 명시적으로 지정하는 경우는 드물기 때문에, 사실상 `current-context`가 kubectl의 기본 연결 대상을 결정한다.


`current-context`가 비어 있거나 없는 경우, kubectl은 클러스터/사용자 정보를 결정할 수 없어 기본값인 `localhost:8080`으로 연결을 시도하고, `The connection to the server localhost:8080 was refused` 같은 에러가 발생한다.


### 참고: localhost:8080 fallback

`localhost:8080` fallback은 Kubernetes 초기 설계의 흔적이다. 과거에는 kube-apiserver가 두 개의 포트를 열 수 있었다.

| 포트 | 프로토콜 | 용도 | 인증 |
| --- | --- | --- | --- |
| **6443** (secure port) | HTTPS | 정상적인 API 접근 | TLS + 인증/인가 적용 |
| **8080** (insecure port) | HTTP | 로컬 디버깅/개발용 | **인증 완전 우회** |

insecure port는 `--insecure-port=8080` 플래그로 열 수 있었고, 주로 마스터 노드에서 로컬로 빠르게 테스트할 때 쓰였다. **Kubernetes 1.20+에서 이 플래그가 삭제**되어 현재는 이 포트가 열리지 않는다.

그런데 `current-context`가 없어도 `localhost:8080`에 연결이 성공하는 경우가 있을 수 있다.

| 상황 | 결과 |
| --- | --- |
| **Kubernetes 1.20+** (현재) | insecure port가 삭제됨. 8080 포트가 아예 열리지 않으므로 연결 거부 |
| **아주 오래된 클러스터** (1.19 이하) | insecure port가 열려 있을 수 있고, **인증 없이 전체 권한으로 접근** 가능 → 심각한 보안 문제 |
| **`kubectl proxy` 실행 중** | `kubectl proxy`가 기본적으로 `localhost:8080`에서 리슨함. proxy 자체가 이미 유효한 kubeconfig로 인증된 상태이므로 연결 성공 |

어느 경우든 `current-context` 없이 `localhost:8080`으로 연결되는 것은 의도된 사용법이 아니다. insecure port는 보안 위험이고, `kubectl proxy`는 우연히 동작하는 것처럼 보이는 것일 뿐이다. `current-context`는 항상 명시하는 것이 맞다.


## 경로 해석

kubeconfig에는 인증서 파일 등의 경로가 들어갈 수 있다. 이 경로의 **저장(쓰기)**과 **해석(읽기)** 규칙이 다르므로 주의가 필요하다.

### 저장: 준 경로 그대로

kubeconfig 파일에 경로를 넣는 방법은 두 가지이다. YAML 파일을 직접 작성하거나, `kubectl config set-cluster` 같은 명령어를 사용하거나. 어느 쪽이든, 절대 경로든 상대 경로든 **적은 그대로** kubeconfig 파일에 기록된다. 별도의 변환이나 정규화가 일어나지 않는다.

```yaml
# 직접 작성 — 적은 그대로 저장됨
clusters:
- cluster:
    certificate-authority: ./certs/ca.crt  # 이 상대 경로가 그대로 들어감
```

```bash
# 명령어로 설정 — 마찬가지로 준 그대로 저장됨
kubectl config set-cluster my-cluster --certificate-authority=./certs/ca.crt
```

### 해석: kubeconfig 파일 위치 기준

kubectl이 kubeconfig를 **읽을 때**, 경로는 다음과 같이 해석된다.
- **절대 경로**: 그대로 해석
- **상대 경로**: **kubeconfig 파일이 위치한 디렉토리**를 기준으로 해석

```yaml
# 이 파일이 /etc/kubernetes/admin.conf에 있다면
clusters:
- cluster:
    certificate-authority: ../pki/ca.crt  # → /etc/pki/ca.crt로 해석됨
```

### 주의: 쓰기와 읽기의 기준이 다르다

문제는 여기서 발생한다. 명령어를 실행할 때의 **현재 디렉토리(pwd)**와, 나중에 kubectl이 kubeconfig를 읽을 때의 **기준 디렉토리(kubeconfig 파일 위치)**가 다를 수 있다.

예를 들어, `/home/user/`에서 `./certs/ca.crt`를 저장했는데 kubeconfig 파일은 `~/.kube/config`에 있다면, kubectl은 `~/.kube/certs/ca.crt`를 찾게 되어 의도와 달라진다. [공식 문서](https://kubernetes.io/ko/docs/concepts/configuration/organize-cluster-access-kubeconfig/#%ED%8C%8C%EC%9D%BC-%EC%B0%B8%EC%A1%B0)에서도 이 점을 언급하고 있다.

> kubeconfig 파일에서 파일과 경로 참조는 kubeconfig 파일의 위치와 관련 있다. 커맨드라인 상에 파일 참조는 현재 디렉터리를 기준으로 한다.

따라서 kubeconfig에 경로를 넣을 때는 거의 항상 **절대 경로**를 사용하거나, `certificate-authority-data`처럼 **base64 인라인**으로 넣는 것이 안전하다.


<br>

# 사용

## 기본 경로

기본적으로 `kubectl`은 `$HOME/.kube` 디렉토리에서 `config`라는 이름의 kubeconfig 파일을 찾는다. 다만, `KUBECONFIG` 환경 변수를 설정하거나 `--kubeconfig` 플래그를 지정하여 다른 kubeconfig 파일을 사용할 수 있다.


## kubectl이 파일을 선택하는 우선순위

kubectl이 어떤 kubeconfig 파일을 읽을지는 다음 우선순위를 따른다.

| 우선순위 | 방법 | 설명 |
| --- | --- | --- |
| **1 (최우선)** | `--kubeconfig` 플래그 | 지정하면 **이 파일만** 사용. 환경 변수와 기본 경로 모두 무시됨 |
| **2** | `KUBECONFIG` 환경 변수 | 플래그가 없을 때 사용. 여러 파일 병합 가능 |
| **3 (기본)** | `$HOME/.kube/config` | 플래그도 환경 변수도 없을 때 사용 |

일반적인 CLI 도구의 설정 우선순위 패턴(플래그 > 환경 변수 > 기본 설정 파일)과 동일하다.


## KUBECONFIG 환경 변수

`KUBECONFIG` 환경 변수에 여러 파일을 구분자로 나열하면, kubectl이 자동으로 병합하여 마치 하나의 파일처럼 동작한다.

```bash
# Linux/macOS: 콜론(:)으로 구분
export KUBECONFIG=~/.kube/config-dev:~/.kube/config-staging:~/.kube/config-prod

# Windows: 세미콜론(;)으로 구분
set KUBECONFIG=%USERPROFILE%\.kube\config-dev;%USERPROFILE%\.kube\config-staging
```

병합 규칙은 다음과 같다:
1. 빈 파일명은 무시
2. 역직렬화할 수 없는 파일 내용에 대해서는 오류 발생
3. 특정 값이나 맵 키를 설정한 **첫 번째 파일의 값이 우선**
4. 이미 설정된 값이나 맵 키는 변경하지 않음
  - 예: `current-context`를 설정한 첫 번째 파일의 컨텍스트가 유지됨
  - 예: 두 파일이 모두 `red-user`를 정의했다면, 첫 번째 파일의 `red-user`만 사용되고 두 번째 파일의 것은 무시됨


<br>

# 주요 명령어: kubectl config

kubeconfig를 조회하거나 수정할 때는 `kubectl config` 하위 명령어를 사용한다.

| 명령어 | 설명 |
| --- | --- |
| `kubectl config view` | 현재 kubeconfig 내용 확인 (병합 결과 포함) |
| `kubectl config get-contexts` | 컨텍스트 목록 조회 |
| `kubectl config current-context` | 현재 활성 컨텍스트 확인 |
| `kubectl config use-context <name>` | 컨텍스트 전환 |
| `kubectl config set-context` | 컨텍스트 생성/수정 |
| `kubectl config set-cluster` | 클러스터 정보 설정 |
| `kubectl config set-credentials` | 사용자 인증 정보 설정 |
| `kubectl config delete-context` | 컨텍스트 삭제 |

자주 사용하는 명령어 몇 가지만 짚어 보자.


## kubectl config view

현재 적용 중인 kubeconfig 내용을 출력한다. 출력되는 내용은 위에서 살펴본 [kubectl 파일 선택 우선순위](#kubectl이-파일을-선택하는-우선순위)에 따라 결정된다. `--kubeconfig` 플래그가 있으면 그 파일만, 없으면 `KUBECONFIG` 환경 변수에 지정된 파일들의 병합 결과가, 둘 다 없으면 `~/.kube/config`의 내용이 출력된다.

```bash
# 전체 설정 확인
kubectl config view

# 현재 컨텍스트의 설정만 확인
kubectl config view --minify
```


## kubectl config use-context

컨텍스트를 전환한다. 이 명령어는 kubeconfig 파일의 `current-context` 필드를 **직접 덮어쓴다**.

```bash
kubectl config use-context my-context
```

```yaml
# 실행 전
current-context: old-context

# kubectl config use-context new-context 실행 후
current-context: new-context  # ← 파일이 직접 수정됨
```

파일이 실제로 수정되므로, 터미널을 닫아도, 재부팅해도, 다른 터미널에서도 바뀐 컨텍스트가 적용된다. 다시 `use-context`로 바꾸지 않는 한 원래대로 돌아오지 않는다.

**파일을 수정하지 않고** 임시로 다른 컨텍스트를 사용하고 싶다면, `--context` 플래그를 쓰는 것이 좋다.

```bash
# 이번 명령만 다른 컨텍스트로 실행 (파일 수정 없음)
kubectl --context=prod-admin get pods
```

> `kubectl config` 하위 명령어의 전체 목록과 상세 사용법은 [kubectl config 공식 레퍼런스](https://kubernetes.io/docs/reference/kubectl/generated/kubectl_config/)를 참고하자.



<br>

# Best Practice

## 환경별 파일 분리 후 KUBECONFIG로 병합

하나의 kubeconfig 파일에 모든 클러스터/사용자 정보를 넣는 것은 이론적으로 가능하지만, 실무에서는 권장되지 않는다.

```bash
# 클러스터별로 파일을 따로 관리
~/.kube/config-dev
~/.kube/config-staging
~/.kube/config-prod

# KUBECONFIG 환경변수로 병합
export KUBECONFIG=~/.kube/config-dev:~/.kube/config-staging:~/.kube/config-prod
```

이렇게 하면:
- 특정 클러스터 설정만 추가/삭제하기 쉽고,
- 실수로 민감한 환경의 인증 정보를 날리는 사고를 줄일 수 있고,
- 팀원 간 특정 환경 config만 공유하기 편하다.


## 경로는 절대 경로 또는 인라인으로

kubeconfig 안에 인증서 경로를 쓸 때는, 거의 항상 **절대 경로**를 사용하거나 `certificate-authority-data`처럼 **base64 인라인**으로 넣는 것이 좋다.

[공식 문서](https://kubernetes.io/ko/docs/concepts/configuration/organize-cluster-access-kubeconfig/#%ED%8C%8C%EC%9D%BC-%EC%B0%B8%EC%A1%B0)에서도 다음과 같이 말한다.

> kubeconfig 파일에서 파일과 경로 참조는 kubeconfig 파일의 위치와 관련 있다. 커맨드라인 상에 파일 참조는 현재 디렉터리를 기준으로 한다. `$HOME/.kube/config`에서 상대 경로는 상대적으로, 절대 경로는 절대적으로 저장한다.


## 보안

- kubeconfig 파일 권한은 `chmod 600`으로 본인만 읽을 수 있게 설정
- 절대 Git 등 버전 관리에 커밋하지 않기 (인증서, 토큰 등 민감 정보 포함)
- 신뢰할 수 없는 출처의 kubeconfig 파일은 먼저 내용을 검사할 것
  - [공식 문서](https://kubernetes.io/ko/docs/concepts/configuration/organize-cluster-access-kubeconfig/)에서도 경고하고 있듯, 특수 제작된 kubeconfig 파일을 통해 악성 코드가 실행되거나 파일이 노출될 수 있다


## 정기적 정리 및 도구 활용

- 더 이상 사용하지 않는 컨텍스트, 클러스터, 사용자 항목은 주기적으로 삭제
- [kubectx / kubens](https://github.com/ahmetb/kubectx) 같은 도구를 사용하면 컨텍스트/네임스페이스 전환이 훨씬 편리하다


<br>

# 결론

kubeconfig는 "어떤 클러스터에, 어떤 인증 정보로, 어떤 네임스페이스에서 작업할지"를 정의하는 접근 설정 파일이다. `clusters`, `users`, `contexts`라는 세 배열로 구성되어 다양한 클러스터와 사용자 조합을 유연하게 관리할 수 있으며, `current-context`로 기본 작업 대상을 지정한다.

포맷 자체는 컴포넌트든 사용자든 동일하지만, 실제로 사용자가 일상적으로 관리하는 것은 사용자용 kubeconfig이다. 환경별로 파일을 분리하고 `KUBECONFIG` 환경 변수로 병합하여 사용하는 것이 Best Practice이다.

- kubeconfig API Reference 상세: [kubeconfig API Reference 톺아보기]({% post_url 2026-02-16-Kubernetes-Kubeconfig-03 %})
- 다중 클러스터 접근 구성 실습: [다중 클러스터 접근 구성 실습]({% post_url 2026-02-16-Kubernetes-Kubeconfig-02 %})
