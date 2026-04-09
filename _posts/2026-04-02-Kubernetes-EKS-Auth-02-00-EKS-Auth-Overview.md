---
title: "[EKS] EKS: 인증/인가 - 2. EKS 인증/인가 전체 흐름"
excerpt: "EKS에서 사용자의 kubectl 요청이 인증되고 인가되기까지의 전 과정을 단계별로 따라가 보자."
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
  - RBAC
  - TokenReview
  - Access-Entry
  - aws-iam-authenticator
  - AWS-EKS-Workshop-Study
  - AWS-EKS-Workshop-Study-Week-4
---

*[서종호(가시다)](https://www.linkedin.com/in/gasida99/)님의 AWS EKS Workshop Study(AEWS) 4주차 학습 내용을 기반으로 합니다.*

<br>

# TL;DR

- `kubectl` 요청이 EKS 클러스터에 도달하면 **인증(AuthN)**과 **인가(AuthZ)** 두 단계를 거친다
- **인증**: 클라이언트가 STS pre-signed URL 기반 Bearer Token을 보내면, aws-iam-authenticator가 STS에 검증을 위임하여 IAM identity를 확인한다
- **인가**: 인증된 IAM identity를 K8s username/group으로 매핑한 뒤, 해당 주체가 요청한 동작을 수행할 권한이 있는지 확인한다
- IAM → K8s 매핑에는 **Access Entry**(권장)와 **aws-auth ConfigMap**(deprecated) 두 가지 방안이 있다
- 인증은 방식이 하나(STS 기반)로 고정이고, 인가 단계에서 두 방안이 갈린다

<br>

# 전체 흐름 한눈에 보기

![EKS 인증/인가 전체 흐름]({{site.url}}/assets/images/eks-w4-user-to-eks-authn-authz.png){: .align-center}

<center><sup>EKS 인증/인가 전체 흐름 (출처: <a href="https://www.youtube.com/watch?v=wgH9xL_48vM">AEWS 스터디</a>)</sup></center>

<br>

사용자가 `kubectl`로 EKS 클러스터에 요청을 보내면, 크게 두 단계를 거친다.

| 단계 | 질문 | 답을 주는 것 |
| --- | --- | --- |
| **인증(AuthN)** | "이 요청을 보낸 사람이 누구인가?" | STS `GetCallerIdentity` + aws-iam-authenticator |
| **인가(AuthZ)** | "이 사람이 이 동작을 할 수 있는가?" | Access Entry/aws-auth ConfigMap + K8s RBAC |

인증은 방식이 하나다. 어떤 IAM User든 Role이든 STS pre-signed URL 기반 Bearer Token으로 인증한다. 인가 단계에서 Access Entry(EKS API) 방안과 aws-auth ConfigMap 방안으로 갈린다.

<br>

# 인증(AuthN)

EKS 인증의 근본 구조(왜 STS `GetCallerIdentity`인가, pre-signed URL, Bearer Token, kubeconfig exec)는 [이전 글]({% post_url 2026-03-12-Kubernetes-EKS-01-01-03-Kubeconfig-Authentication %})에서 다뤘다. 이 글에서는 전체 흐름 속에서 인증이 어떤 위치에 있는지 요약하고, 상세 실습은 [다음 글]({% post_url 2026-04-02-Kubernetes-EKS-Auth-02-01-EKS-Auth-AuthN %})로 넘긴다.

그림의 1~7단계가 인증에 해당한다.

<br>

## [1] K8S Action

사용자가 `kubectl` 명령을 실행한다. kubectl은 kubeconfig를 읽어 대상 클러스터를 확인하고, `exec` 블록에 정의된 토큰 생성 명령을 호출한다.

<br>

## [2] Token 발급

kubeconfig의 `exec` 블록에 의해 AWS-IAM-Authenticator 클라이언트(`aws eks get-token`)가 실행된다.

1. 현재 IAM 자격증명의 Secret Access Key로 **Signature V4 서명**을 만든다
2. 서명을 포함한 STS `GetCallerIdentity` **pre-signed URL**을 생성한다
3. pre-signed URL을 base64url 인코딩하여 `k8s-aws-v1.<base64>` 형태의 토큰으로 포장한다

이 과정에서 네트워크 통신은 **0회**다. 서명 생성은 순수 로컬 연산이고, STS에 실제 요청을 보내는 것은 [5]단계에서 서버 측 authenticator가 한다.

<br>

## [3] Action + Token 전송

kubectl이 EKS API 서버에 HTTP 요청을 보낸다. `Authorization: Bearer k8s-aws-v1.<base64>` 헤더에 토큰을 실어 보낸다.

<br>

## [4] Id Token 확인

EKS API 서버는 Bearer Token을 받으면, **Webhook Token Authentication** 설정에 따라 AWS-IAM-Authenticator 서버에 **TokenReview** 요청을 전달한다.

TokenReview는 `authentication.k8s.io/v1` API 그룹에 속하는 K8s 리소스로, "이 토큰이 유효한가? 유효하다면 누구의 것인가?"를 묻는 인증 요청 객체다.

- **요청(`spec`)**: `spec.token`에 검증할 토큰을 담는다
- **응답(`status`)**: `status.authenticated`(true/false), `status.user`(username, uid, groups, extra)를 돌려준다

K8s API 서버 자체는 `k8s-aws-v1.` 토큰을 이해하지 못한다. "이 토큰 검증해줘"라고 webhook에 넘기기만 할 뿐, AWS 서명을 직접 검증하지 않는다.

<br>

## [5] sts:GetCallerIdentity

AWS-IAM-Authenticator 서버가 TokenReview를 받으면 다음을 수행한다.

1. `k8s-aws-v1.` 접두사를 제거하고 base64url 디코딩하여 **pre-signed URL을 복원**한다
2. 복원된 URL로 STS에 **HTTP GET 요청**을 보낸다 (`GetCallerIdentity`)

<br>

## [6] 성공

STS가 서명을 검증하고 **IAM identity(Account, ARN, UserID)**를 응답한다. AWS-IAM-Authenticator 서버가 이 identity 정보를 K8s API 서버에 TokenReview 응답으로 반환한다.

이 시점에서 API 서버는 "이 요청을 보낸 사람은 `arn:aws:iam::123456789012:user/admin`이다"라는 것을 알게 된다.

<br>

## [7] K8S User 확인

IAM ARN이 확인되었지만, K8s RBAC은 IAM ARN을 모른다. RBAC이 이해하는 것은 K8s username과 group이다. 따라서 "이 IAM ARN은 K8s에서 어떤 username/group에 해당하는가?"를 매핑해야 한다.

이 매핑을 수행하는 방법이 두 가지다.

| 구분 | **방안 1: Access Entry (EKS API)** | **방안 2: aws-auth ConfigMap** |
| --- | --- | --- |
| **상태** | **권장** | **deprecated** |
| **데이터 저장소** | AWS EKS 관리형 Internal DB | K8s 내부의 ConfigMap (etcd) |
| **관리 방법** | AWS API / 콘솔 | `kubectl edit` 등으로 YAML 직접 편집 |
| **리스크** | AWS가 관리하므로 상대적으로 안전 | 휴먼 에러 (잘못 수정 시 노드 NotReady 등) |
| **우선순위** | 정책 중복 시 **EKS API 우선** | 정책 중복 시 **무시됨** |

<br>

### 방안 1: Access Entry (EKS API)

2023년 말에 도입된 방식으로, AWS API를 통해 IAM → K8s 매핑을 관리한다. aws-auth ConfigMap의 lockout 문제(ConfigMap 잘못 수정 → 클러스터 접근 불가)를 해결하기 위해 등장했다.

Access Entry에서는 매핑 정보가 EKS 관리형 DB에 저장되고, AWS API(`aws eks create-access-entry`)나 콘솔로 관리한다. K8s 오브젝트를 직접 수정하지 않으므로 휴먼 에러의 위험이 낮다.

<br>

### 방안 2: aws-auth ConfigMap (deprecated)

EKS 초기부터 사용하던 방식으로, `kube-system` 네임스페이스의 `aws-auth` ConfigMap에 IAM → K8s 매핑을 직접 기록한다.

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: aws-auth
  namespace: kube-system
data:
  mapRoles: |
    - rolearn: arn:aws:iam::123456789012:role/myeks-ng-1
      groups:
      - system:bootstrappers
      - system:nodes
      username: system:node:{% raw %}{{EC2PrivateDNSName}}{% endraw %}
  mapUsers: |
    - groups:
      - system:masters
      userarn: arn:aws:iam::123456789012:user/admin
      username: kubernetes-admin
```

`mapRoles`에 IAM Role, `mapUsers`에 IAM User의 매핑을 기록한다. 문제는 이 ConfigMap을 잘못 수정하면 클러스터 접근이 막히거나 노드가 NotReady 상태에 빠질 수 있다는 것이다. 예를 들어 `system:nodes` 그룹 매핑을 실수로 삭제하면, 약 5분 후 모든 노드가 NotReady 상태로 빠진다.

> EKS를 생성한 IAM principal은 aws-auth와 상관없이 `kubernetes-admin` username으로 `system:masters` 그룹에 자동 매핑된다. 이 매핑은 표시되는 설정에 나타나지 않는다.

<br>

# 인가(AuthZ)

IAM → K8s 매핑까지 완료되면 "이 사람이 이 동작을 할 수 있는가?"를 판단하는 인가 단계로 넘어간다.

<br>

## [8] K8S Role 확인

매핑된 K8s username/group으로 인가를 수행한다. 매핑 방안에 따라 인가 엔진이 다르다.

| 구분 | **방안 1: Access Entry** | **방안 2: aws-auth ConfigMap** |
| --- | --- | --- |
| **인가 엔진** | **Node + RBAC + Webhook** (3개 체인) | **Node + RBAC** (2개) |
| **권한 부여 방법** | Access Policy 연결만으로 가능 (+ 커스텀 RBAC 병행 가능) | CR/CRB를 **직접 생성/관리** 필요 |

<br>

### 방안 1의 인가: Access Policy + Webhook

Access Entry 방안에서는 EKS가 자체 **Webhook 인가**를 추가로 제공한다. Access Policy(EKS 관리형 정책)를 Access Entry에 연결하면, Webhook 인가가 이 정책을 확인하여 허용/거부를 판단한다.

Webhook이 "No Opinion"을 반환하면 K8s RBAC으로 넘어간다. 커스텀 RBAC을 쓰고 싶을 때는 Access Policy를 붙이지 않으면 된다.

<br>

### 방안 2의 인가: K8s RBAC

aws-auth ConfigMap 방안에서는 순수 K8s RBAC만 사용한다. 매핑된 username/group에 대해 ClusterRole/RoleBinding을 직접 만들어야 한다.

K8s에 미리 생성된 group(예: `system:masters`)에 매핑하면 별도 RBAC 리소스 생성이 불필요하지만, 커스텀 그룹을 사용할 경우 CR/CRB를 직접 생성하고 관리해야 한다.

<br>

## [9] 허용/차단

인가를 통과하면 API 서버가 요청을 실행하고 결과를 kubectl에 반환한다. 인가에 실패하면 403 Forbidden으로 거부된다.

<br>

# 전체 시퀀스 정리

인증과 인가를 하나의 흐름으로 정리하면 다음과 같다.

| 단계 | 수행 주체 | 내용 | 구분 |
| --- | --- | --- | --- |
| **[1] K8S Action** | 사용자 | kubectl 명령 실행, kubeconfig에서 exec 블록 호출 | AuthN |
| **[2] Token 발급** | AWS-IAM-Authenticator 클라이언트 | SigV4 서명 → pre-signed URL → `k8s-aws-v1.<base64>` 토큰 생성 (네트워크 0회) | AuthN |
| **[3] Action + Token** | kubectl | Bearer Token을 EKS API 서버에 HTTPS로 전송 | AuthN |
| **[4] Id Token 확인** | EKS API 서버 | AWS-IAM-Authenticator 서버에 TokenReview 위임 | AuthN |
| **[5] sts:GetCallerIdentity** | AWS-IAM-Authenticator 서버 | pre-signed URL을 복원하여 STS에 검증 요청 | AuthN |
| **[6] 성공** | AWS STS | 서명 검증 후 IAM identity(Account, ARN, UserID) 응답 | AuthN |
| **[7] K8S User 확인** | Access Entry 또는 aws-auth | IAM ARN → K8s username/group 매핑 | AuthN |
| **[8] K8S Role 확인** | Webhook + RBAC 또는 RBAC만 | 매핑된 주체의 요청 동작에 대한 권한 확인 | AuthZ |
| **[9] 허용/차단** | K8s API 서버 | 인가 통과 시 요청 실행, 실패 시 403 Forbidden | - |

1~7단계(인증)는 방식이 하나다. 어떤 IAM 주체든 동일한 STS 기반 메커니즘을 거친다. 7단계의 매핑 방안(Access Entry vs aws-auth ConfigMap)에 따라 8단계의 인가 엔진이 달라진다.

<br>

# 정리

이번 글에서는 EKS 인증/인가의 전체 흐름을 조감도 수준에서 정리했다.

| 구분 | 핵심 |
| --- | --- |
| **인증** | STS pre-signed URL 기반 Bearer Token → aws-iam-authenticator → STS 검증. 방식은 하나 |
| **매핑** | IAM ARN → K8s username/group. Access Entry(권장) 또는 aws-auth ConfigMap(deprecated) |
| **인가** | Access Entry는 Webhook + RBAC, aws-auth는 RBAC만. 결국 K8s RBAC이 최종 인가를 담당 |

다음 글에서는 인증 흐름([1]~[6])을 실습으로 하나씩 따라가며, 토큰 생성부터 CloudTrail/CloudWatch 검증까지 직접 확인해 본다.

<br>
