---
title: "[EKS] EKS: 인증/인가 - 6. 사용자 → K8s API: 매핑과 인가(AuthZ) 실습"
excerpt: "Access Entry 확인, SubjectAccessReview, 새 IAM Role 생성과 권한 테스트를 통해 매핑과 인가 과정을 직접 확인해 보자."
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
  - Access-Entry
  - Access-Policy
  - SubjectAccessReview
  - aws-iam-authenticator
  - AWS-EKS-Workshop-Study
  - AWS-EKS-Workshop-Study-Week-4
---

*[서종호(가시다)](https://www.linkedin.com/in/gasida99/)님의 AWS EKS Workshop Study(AEWS) 4주차 학습 내용을 기반으로 합니다.*

<br>

# TL;DR

- Access Entry 목록과 연결된 Access Policy를 확인하여 현재 클러스터의 매핑 구성을 파악할 수 있다
- `kubectl rbac-tool whoami`로 현재 인증된 K8s identity(username, groups)를 확인할 수 있다. creator의 `system:masters`는 표시되지 않는다
- `SubjectAccessReview`로 특정 주체가 특정 동작을 할 수 있는지 인가 여부를 직접 질의할 수 있다
- 새 IAM Role을 만들고 Access Entry + Access Policy를 연결하면, 해당 Role로 클러스터에 접근할 수 있다
- Access Policy를 변경하면 권한 범위가 즉시 달라지는 것을 확인할 수 있다

<br>

# 개요

[이전 글]({% post_url 2026-04-02-Kubernetes-EKS-Auth-02-02-EKS-Auth-AuthZ %})에서 IAM → K8s 매핑(브릿지)과 인가의 개념, 두 방안(Access Entry vs aws-auth ConfigMap)의 설계 원칙을 정리했다. 이번 글에서는 이 개념들을 **실습으로 확인**한다.

[전체 흐름 개요]({% post_url 2026-04-02-Kubernetes-EKS-Auth-02-00-EKS-Auth-Overview %})의 **[7] K8S User 확인**, **[8] K8S Role 확인**, **[9] 허용/차단** 단계에 해당한다.

```text
[1]~[6] 인증(AuthN)        [7] 매핑(브릿지)         [8]~[9] 인가(AuthZ)
─────────────────── → ─────────────────── → ───────────────────
   이전 글에서 실습          이번 글에서 실습
```

> [7]~[9]는 API 서버 내부에서 순차적으로 일어나는 메커니즘이다. [1]~[6]처럼 단계마다 분리해서 관찰하기는 어렵고, 대신 매핑 구성/결과와 인가 질의/응답을 확인하는 방식으로 진행한다.

아래 표는 각 실습 섹션이 [개념 글]({% post_url 2026-04-02-Kubernetes-EKS-Auth-02-02-EKS-Auth-AuthZ %})의 어느 부분을 검증하는지 정리한 것이다.

| 실습 섹션 | 하는 일 | 개념 글 대응 | Overview 단계 |
| --- | --- | --- | --- |
| [1. 현재 매핑 구성 확인](#1-현재-매핑-구성-확인) | Access Entry 목록, 연결된 Access Policy 조회 | Access Entry 구성 요소, Access Policy | [7] |
| [2. 현재 K8s Identity 확인](#2-현재-k8s-identity-확인) | `rbac-tool whoami`, SubjectAccessReview 직접 요청 | 왜 브릿지가 필요한가, 인가 체인 (SubjectAccessReview) | [7]+[8]+[9] |
| [3. 새 IAM Role로 Access Entry 테스트](#3-새-iam-role로-access-entry-테스트) | IAM Role 생성 → ViewPolicy → EditPolicy 변경 | Access Entry 구성 요소, Access Policy, AWS 가이드 절차 | [7]+[8]+[9] |
| [4. 하이브리드 패턴](#4-하이브리드-패턴-group-매핑--커스텀-rbac) | Group만 매핑 + 커스텀 ClusterRole/RoleBinding | 하이브리드 패턴: Access Entry + 커스텀 RBAC | [7]+[8]+[9] |
| [5. 실습 리소스 정리](#5-실습-리소스-정리) | 환경 원복 | - | - |

<br>

# 1. 현재 매핑 구성 확인

## Access Entry 목록

현재 클러스터에 등록된 Access Entry를 확인한다.

```bash
aws eks list-access-entries --cluster-name myeks | jq
```

```json
{
  "accessEntries": [
    "arn:aws:iam::123456789012:role/aws-service-role/eks.amazonaws.com/AWSServiceRoleForAmazonEKS",
    "arn:aws:iam::123456789012:role/myeks-ng-1",
    "arn:aws:iam::123456789012:user/admin"
  ]
}
```

총 3개의 Access Entry가 등록되어 있다. [1주차 배포 결과]({% post_url 2026-03-12-Kubernetes-EKS-01-01-02-Installation-Result %})에서 콘솔로 확인했던 항목이 CLI로도 동일하게 확인된다.

| Entry | 설명 |
| --- | --- |
| `arn:aws:iam::<ACCOUNT_ID>:role/aws-service-role/eks.amazonaws.com/AWSServiceRoleForAmazonEKS` | EKS 서비스 자체의 서비스 연결 역할 |
| `arn:aws:iam::<ACCOUNT_ID>:role/myeks-ng-1` | 관리형 노드 그룹의 IAM Role (EKS가 자동 생성) |
| `arn:aws:iam::<ACCOUNT_ID>:user/admin` | 클러스터 creator (Terraform의 `enable_cluster_creator_admin_permissions`) |

<br>

## 연결된 Access Policy 확인

admin 사용자에게 어떤 Access Policy가 연결되어 있는지 확인한다.

```bash
export ACCOUNT_ID=$(aws sts get-caller-identity --query 'Account' --output text)
aws eks list-associated-access-policies \
  --cluster-name myeks \
  --principal-arn arn:aws:iam::${ACCOUNT_ID}:user/admin | jq
```

```json
{
  "associatedAccessPolicies": [
    {
      "policyArn": "arn:aws:eks::aws:cluster-access-policy/AmazonEKSClusterAdminPolicy",
      "accessScope": {
        "type": "cluster",
        "namespaces": []
      },
      "associatedAt": "2026-04-09T21:01:40.786000+09:00",
      "modifiedAt": "2026-04-09T21:01:40.786000+09:00"
    }
  ],
  "clusterName": "myeks",
  "principalArn": "arn:aws:iam::123456789012:user/admin"
}
```

`AmazonEKSClusterAdminPolicy`가 `cluster` scope으로 연결되어 있다. 주요 필드를 살펴보면 다음과 같다.

- `policyArn`: 연결된 Access Policy. `AmazonEKSClusterAdminPolicy`는 K8s의 `cluster-admin` ClusterRole에 대응하는 전체 클러스터 관리자 권한이다.
- `accessScope.type`: `cluster`로 설정되어 있어 클러스터 전체에 대한 권한이 부여된다. `namespace` scope인 경우 `namespaces` 배열에 대상 네임스페이스가 지정된다.
- `principalArn`: 이 정책이 연결된 IAM principal. Terraform에서 `enable_cluster_creator_admin_permissions`로 자동 등록된 클러스터 생성자(`admin` 사용자)다.

[이전 글]({% post_url 2026-04-02-Kubernetes-EKS-Auth-02-02-EKS-Auth-AuthZ %})에서 정리한 Access Policy 개념이 실제 클러스터에 어떻게 적용되어 있는지 확인할 수 있다.

<br>

## 사용 가능한 Access Policy 목록

EKS에서 제공하는 관리형 Access Policy 전체 목록을 확인한다.

```bash
aws eks list-access-policies --output table
```

총 32개의 관리형 Access Policy가 확인된다. [이전 글]({% post_url 2026-04-02-Kubernetes-EKS-Auth-02-02-EKS-Auth-AuthZ %})에서 정리한 주요 5종을 포함해, 다양한 서비스 전용 정책이 제공되고 있다.

| Policy | 대응 K8s Role | 설명 |
| --- | --- | --- |
| `AmazonEKSClusterAdminPolicy` | `cluster-admin` | 전체 클러스터 관리자 |
| `AmazonEKSAdminPolicy` | `admin` | 네임스페이스 수준 관리자 |
| `AmazonEKSEditPolicy` | `edit` | 리소스 읽기/쓰기 |
| `AmazonEKSViewPolicy` | `view` | 리소스 읽기 전용 |
| `AmazonEKSAdminViewPolicy` | - | Secret 포함 클러스터 전체 읽기 |

이 외에도 Networking, Storage, SageMaker, ArgoCD, EMR 등 AWS 서비스와의 통합을 위한 전용 정책이 다수 포함되어 있다.

<details markdown="1">
<summary>전체 Access Policy 목록 (펼치기)</summary>

```
-------------------------------------------------------------------------------------------------------------------------------------------
|                                                           ListAccessPolicies                                                            |
+-----------------------------------------------------------------------------------------------------------------------------------------+
||                                                            accessPolicies                                                             ||
|+--------------------------------------------------------------------------------------+------------------------------------------------+|
||                                          arn                                         |                     name                       ||
|+--------------------------------------------------------------------------------------+------------------------------------------------+|
||  arn:aws:eks::aws:cluster-access-policy/AIDevOpsAgentAccessPolicy                    |  AIDevOpsAgentAccessPolicy                     ||
||  arn:aws:eks::aws:cluster-access-policy/AmazonAIOpsAssistantPolicy                   |  AmazonAIOpsAssistantPolicy                    ||
||  arn:aws:eks::aws:cluster-access-policy/AmazonARCRegionSwitchScalingPolicy           |  AmazonARCRegionSwitchScalingPolicy            ||
||  arn:aws:eks::aws:cluster-access-policy/AmazonEKSACKPolicy                           |  AmazonEKSACKPolicy                            ||
||  arn:aws:eks::aws:cluster-access-policy/AmazonEKSAdminPolicy                         |  AmazonEKSAdminPolicy                          ||
||  arn:aws:eks::aws:cluster-access-policy/AmazonEKSAdminViewPolicy                     |  AmazonEKSAdminViewPolicy                      ||
||  arn:aws:eks::aws:cluster-access-policy/AmazonEKSArgoCDClusterPolicy                 |  AmazonEKSArgoCDClusterPolicy                  ||
||  arn:aws:eks::aws:cluster-access-policy/AmazonEKSArgoCDPolicy                        |  AmazonEKSArgoCDPolicy                         ||
||  arn:aws:eks::aws:cluster-access-policy/AmazonEKSAutoNodePolicy                      |  AmazonEKSAutoNodePolicy                       ||
||  arn:aws:eks::aws:cluster-access-policy/AmazonEKSBlockStorageClusterPolicy           |  AmazonEKSBlockStorageClusterPolicy            ||
||  arn:aws:eks::aws:cluster-access-policy/AmazonEKSBlockStoragePolicy                  |  AmazonEKSBlockStoragePolicy                   ||
||  arn:aws:eks::aws:cluster-access-policy/AmazonEKSClusterAdminPolicy                  |  AmazonEKSClusterAdminPolicy                   ||
||  arn:aws:eks::aws:cluster-access-policy/AmazonEKSComputeClusterPolicy                |  AmazonEKSComputeClusterPolicy                 ||
||  arn:aws:eks::aws:cluster-access-policy/AmazonEKSComputePolicy                       |  AmazonEKSComputePolicy                        ||
||  arn:aws:eks::aws:cluster-access-policy/AmazonEKSEditPolicy                          |  AmazonEKSEditPolicy                           ||
||  arn:aws:eks::aws:cluster-access-policy/AmazonEKSEventPolicy                         |  AmazonEKSEventPolicy                          ||
||  arn:aws:eks::aws:cluster-access-policy/AmazonEKSHybridPolicy                        |  AmazonEKSHybridPolicy                         ||
||  arn:aws:eks::aws:cluster-access-policy/AmazonEKSKROPolicy                           |  AmazonEKSKROPolicy                            ||
||  arn:aws:eks::aws:cluster-access-policy/AmazonEKSLoadBalancingClusterPolicy          |  AmazonEKSLoadBalancingClusterPolicy           ||
||  arn:aws:eks::aws:cluster-access-policy/AmazonEKSLoadBalancingPolicy                 |  AmazonEKSLoadBalancingPolicy                  ||
||  arn:aws:eks::aws:cluster-access-policy/AmazonEKSNetworkingClusterPolicy             |  AmazonEKSNetworkingClusterPolicy              ||
||  arn:aws:eks::aws:cluster-access-policy/AmazonEKSNetworkingPolicy                    |  AmazonEKSNetworkingPolicy                     ||
||  arn:aws:eks::aws:cluster-access-policy/AmazonEKSPodIdentityPolicy                   |  AmazonEKSPodIdentityPolicy                    ||
||  arn:aws:eks::aws:cluster-access-policy/AmazonEKSSecretAdminPolicy                   |  AmazonEKSSecretAdminPolicy                    ||
||  arn:aws:eks::aws:cluster-access-policy/AmazonEKSSecretReaderPolicy                  |  AmazonEKSSecretReaderPolicy                   ||
||  arn:aws:eks::aws:cluster-access-policy/AmazonEKSViewPolicy                          |  AmazonEKSViewPolicy                           ||
||  arn:aws:eks::aws:cluster-access-policy/AmazonEMRJobPolicy                           |  AmazonEMRJobPolicy                            ||
||  arn:aws:eks::aws:cluster-access-policy/AmazonSagemakerHyperpodClusterPolicy         |  AmazonSagemakerHyperpodClusterPolicy          ||
||  arn:aws:eks::aws:cluster-access-policy/AmazonSagemakerHyperpodControllerPolicy      |  AmazonSagemakerHyperpodControllerPolicy       ||
||  arn:aws:eks::aws:cluster-access-policy/AmazonSagemakerHyperpodSpacePolicy           |  AmazonSagemakerHyperpodSpacePolicy            ||
||  arn:aws:eks::aws:cluster-access-policy/AmazonSagemakerHyperpodSpaceTemplatePolicy   |  AmazonSagemakerHyperpodSpaceTemplatePolicy    ||
||  arn:aws:eks::aws:cluster-access-policy/AmazonSagemakerHyperpodSystemNamespacePolicy |  AmazonSagemakerHyperpodSystemNamespacePolicy  ||
||  arn:aws:eks::aws:cluster-access-policy/AmazonSagemakerHyperpodUserClusterPolicy     |  AmazonSagemakerHyperpodUserClusterPolicy      ||
|+--------------------------------------------------------------------------------------+------------------------------------------------+|
```

</details>

<br>

# 2. 현재 K8s Identity 확인

앞서 Access Entry / Access Policy 조회는 AWS CLI로 수행했다. 이는 EKS(AWS) 측에서 매핑 구성이 어떻게 되어 있는지를 본 것이다. 이번에는 시점을 바꿔서, **K8s 측에서** 현재 인증된 주체가 누구이고 어떤 권한을 갖는지를 확인해 본다.

이를 위해 [krew](https://krew.sigs.k8s.io/)를 활용한다. krew는 `kubectl`의 플러그인 매니저로, RBAC 조회·요약·시각화 등 다양한 커뮤니티 플러그인을 `kubectl` 하위 명령으로 설치·실행할 수 있게 해 준다.

## krew 플러그인 설치

RBAC 확인에 유용한 플러그인을 설치한다.

```bash
kubectl krew install access-matrix rbac-tool rolesum whoami
```

| 플러그인 | 설명 |
| --- | --- |
| `access-matrix` | 서버 리소스에 대한 RBAC 접근 권한 매트릭스 표시 |
| `rbac-tool` | RBAC 주체 조회, 정책 규칙 목록, ClusterRole 생성 등 다목적 도구 |
| `rolesum` | 주체(ServiceAccount, User, Group)별 RBAC 역할 요약 |
| `whoami` | 현재 인증된 주체 확인 (`kubectl rbac-tool whoami`의 간편 버전) |

> krew 플러그인은 `kubectl` 하위 명령으로 실행된다. 예를 들어 `kubectl rbac-tool whoami`는 `rbac-tool` 플러그인의 `whoami` 서브커맨드다.

<br>

## kubectl rbac-tool whoami

현재 인증된 사용자의 K8s identity를 확인한다.

```bash
kubectl rbac-tool whoami
```

```
{Username: "arn:aws:iam::123456789012:user/admin",
 UID:      "aws-iam-authenticator:123456789012:AIDACKEXAMPLEUSERID12",
 Groups:   ["system:authenticated"],
 Extra:    {accessKeyId:                                   ["AKIAIOSFODNN7EXAMPLE"],
            arn:                                           ["arn:aws:iam::123456789012:user/admin"],
            canonicalArn:                                  ["arn:aws:iam::123456789012:user/admin"],
            principalId:                                   ["AIDACKEXAMPLEUSERID12"],
            sessionName:                                   [""],
            sigs.k8s.io/aws-iam-authenticator/principalId: ["AIDACKEXAMPLEUSERID12"]}}
```

| 필드 | 값 | 의미 |
| --- | --- | --- |
| `Username` | `arn:aws:iam::123456789012:user/admin` | IAM ARN이 그대로 K8s username으로 매핑됨 |
| `UID` | `aws-iam-authenticator:123456789012:AIDA6...` | aws-iam-authenticator가 부여한 고유 식별자 |
| `Groups` | `["system:authenticated"]` | `system:masters`가 **표시되지 않는다** |
| `Extra.arn` | IAM ARN | TokenReview 응답에 포함된 IAM principal 정보 |
| `Extra.accessKeyId` | `AKIA6...` | 토큰 서명에 사용된 Access Key ID |


<br>

`system:masters`가 groups에 보이지 않는다. EKS 콘솔의 IAM 액세스 항목에서도 마찬가지다.

![EKS 콘솔 IAM 액세스 항목 - system:masters 미노출]({{site.url}}/assets/images/eks-w4-system-masters-not-exposed.png){: .align-center}

<center><sup>EKS 콘솔의 IAM 액세스 항목. admin 사용자의 그룹 이름에 <code>system:masters</code>가 노출되지 않는다</sup></center>

<br>

creator의 `system:masters` 매핑은 aws-iam-authenticator가 TokenReview 응답에 넣는 것이 아니라, EKS 컨트롤 플레인 내부에 하드코딩되어 **인가 단계에서 별도로 주입**된다. authenticator의 TokenReview 응답 경로와는 분리된 메커니즘이므로, TokenReview·Access Entry API·콘솔 어디에서도 드러나지 않는다. 그렇다면 왜 이렇게 설계한 것일까?

> **내부 주입 메커니즘의 현재 위상**: Access Entry 도입 이전에는 creator만이 `system:masters`로 매핑되었고, 이것이 클러스터 관리자가 사용할 수 있는 **유일한 통로**였다. Access Entry 도입 후에는 creator 외에도 임의의 IAM principal에 `AmazonEKSClusterAdminPolicy` 같은 Access Policy를 연결하여 관리자 권한을 부여할 수 있게 되었다. 따라서 현재 이 내부 `system:masters` 주입 메커니즘은 레거시 호환용 안전장치로, creator가 클러스터에서 완전히 잠기는 상황(예: Access Entry 삭제, Access Policy 미스컨피그)을 방지하는 최후의 fallback으로 남아 있을 뿐이다.

### Creator의 system:masters가 노출되지 않는 이유

클러스터 creator는 내부적으로 `system:masters` 그룹에 매핑되어 전체 관리자 권한을 갖지만, 이 매핑은 **TokenReview 응답, Access Entry API, 콘솔 어디에서도 노출되지 않는다**. 이것은 사용자의 선택이 아니라 **EKS 컨트롤 플레인의 의도적인 설계 결정**이며, 핵심 이유는 **`system:masters`가 TokenReview groups에 포함되면 EKS의 Access Policy 기반 인가 관리 체계가 무력화되기 때문**이다.

이를 이해하려기 위해 먼저 각 컴포넌트의 역할을 분리해서 보자.

```text
요청 → aws-iam-authenticator → kube-apiserver → 인가 체인
       ├─ 인증만 담당               ├─ TokenReview 응답 수신
       ├─ STS 검증, IAM ARN 확인   ├─ groups 기반 인가 체인 진행
       └─ TokenReview 응답 반환    └─ Node → Webhook → RBAC
          "이 IAM ARN은 유효하고,
           groups는 이거다"
```

- **aws-iam-authenticator**: 인증만 담당한다. "이 IAM ARN은 유효하고, groups는 이거다"를 TokenReview 응답으로 돌려줄 뿐, 인가에는 관여하지 않는다.
- **kube-apiserver**: TokenReview 응답을 받아서 인가 체인(Node → Webhook → RBAC)을 돌린다. 이때 groups에 `system:masters`가 있으면, API 서버 코드가 인가 체인을 거치지 않고 즉시 Allow를 내린다.

인증은 정상적으로 수행된다(STS 검증, IAM ARN 확인 등). 무력화되는 것은 **인가** 쪽, 정확히 말하면 **EKS의 Access Policy 기반 인가 관리 체계**다.

#### 만약 system:masters가 TokenReview groups에 포함된다면

`system:masters`는 K8s API 서버 소스 코드에 하드코딩된 특수 그룹으로, RBAC과 Webhook Authorizer를 **모두 우회**한다. [`pkg/registry/rbac/escalation_check.go`](https://github.com/kubernetes/kubernetes/blob/master/pkg/registry/rbac/escalation_check.go)의 `EscalationAllowed()` 함수가 `system:masters`(`SystemPrivilegedGroup` [상수](https://github.com/kubernetes/apiserver/blob/master/pkg/authentication/user/user.go))를 보면 즉시 `true`를 반환한다([RBAC 모범 사례]({% post_url 2026-04-02-Kubernetes-EKS-Auth-00-04-RBAC-Good-Practices %}) 참고).

TokenReview 자체는 매 요청(또는 캐시 TTL) 단위로 호출되는 일회성 질의다. 하지만 TokenReview 응답을 만드는 것은 aws-iam-authenticator이고, authenticator의 매핑 로직이 "creator IAM ARN이면 groups에 `system:masters`를 넣어라"로 되어 있다면, creator가 요청할 때**마다** 매번 `system:masters`가 응답에 포함된다. kube-apiserver는 `system:masters`를 보는 즉시 인가 체인을 건너뛰고 Allow를 내리므로, 매 요청이 항상 인가 우회로 처리된다.

```text
요청 1 → TokenReview → groups: ["system:masters"] → 인가 우회 → Allow
요청 2 → TokenReview → groups: ["system:masters"] → 인가 우회 → Allow
요청 3 → TokenReview → groups: ["system:masters"] → 인가 우회 → Allow
  ...영원히
```

authenticator의 매핑 로직은 변하지 않으므로 모든 요청에서 동일한 결과가 나온다. **매번 반복되는 일회성**이고, 실질적으로 영구 superuser와 다름없다. Webhook(Access Policy 평가)에 도달하기 전에 즉시 Allow가 내려지므로, Access Policy를 `ViewPolicy`로 바꾸든 아예 삭제하든 아무 효과가 없는, 제어 불가능한 영구 superuser가 되는 것이다.

#### EKS의 설계: TokenReview에 넣지 않는다

EKS는 이 문제를 알고 **의도적으로** `system:masters`를 TokenReview 응답에 포함시키지 않는다. 앞서 확인한 것처럼, creator의 `system:masters` 매핑은 컨트롤 플레인 내부에서 인가 단계에 별도로 주입되는 메커니즘이다.

TokenReview에 넣지 않으면, 매 요청마다 인가가 정상적으로 EKS Webhook Authorizer까지 도달하여 **Access Policy 기반으로 권한을 평가**하므로, 정책을 변경하면 다음 요청부터 즉시 반영된다.

```text
[system:masters가 TokenReview에 포함되는 경우 — 가상 시나리오]
  요청 → authenticator → TokenReview groups: ["system:masters", ...]
       → kube-apiserver 인가 체인 진입
       → system:masters 감지 → 즉시 Allow (Webhook 스킵)
       → Access Policy 변경해도 효과 없음

[현재 EKS 설계 — system:masters를 TokenReview에 넣지 않음]
  요청 → authenticator → TokenReview groups: ["system:authenticated"]
       → kube-apiserver 인가 체인 진입
       → Node Authorizer → EKS Webhook Authorizer → RBAC
                           ↑
                           Access Policy 평가 (정상 도달)
       → 정책 변경 시 다음 요청부터 즉시 반영
```

[ViewPolicy → EditPolicy 변경](#access-policy-변경----editpolicy로-업그레이드) 실습에서 확인하는 것이 바로 이 동작이다.

<br>

## krew 플러그인 활용

krew 플러그인으로 주체별 RBAC 바인딩, 정책 규칙, 리소스 접근 매트릭스 등을 다양한 관점에서 확인할 수 있다. 핵심 흐름을 따라가려면 [SubjectAccessReview API 확인](#subjectaccessreview-api-확인)으로 건너뛰어도 된다.

<details markdown="1">
<summary>rbac-tool, access-matrix, rolesum 사용 예제 (펼치기)</summary>

### rbac-tool lookup

주체(User, Group, ServiceAccount) 이름으로 바인딩된 RBAC 역할을 조회한다. EKS 클러스터에서 주요 그룹 3개를 확인해 보자.

```bash
kubectl rbac-tool lookup system:masters
kubectl rbac-tool lookup system:nodes
kubectl rbac-tool lookup system:bootstrappers
```

```
  SUBJECT        | SUBJECT TYPE | SCOPE       | NAMESPACE | ROLE          | BINDING
-----------------+--------------+-------------+-----------+---------------+----------------
  system:masters | Group        | ClusterRole |           | cluster-admin | cluster-admin

  SUBJECT      | SUBJECT TYPE | SCOPE       | NAMESPACE | ROLE                  | BINDING
---------------+--------------+-------------+-----------+-----------------------+------------------------
  system:nodes | Group        | ClusterRole |           | eks:node-bootstrapper | eks:node-bootstrapper

  SUBJECT              | SUBJECT TYPE | SCOPE       | NAMESPACE | ROLE                  | BINDING
-----------------------+--------------+-------------+-----------+-----------------------+------------------------
  system:bootstrappers | Group        | ClusterRole |           | eks:node-bootstrapper | eks:node-bootstrapper
```

| 그룹 | 바인딩된 ClusterRole | 의미 |
| --- | --- | --- |
| `system:masters` | `cluster-admin` | 전체 클러스터 관리자. 모든 리소스에 대한 모든 동작 허용 |
| `system:nodes` | `eks:node-bootstrapper` | 노드 부트스트랩 권한. 노드가 클러스터에 조인할 때 필요한 최소 권한 |
| `system:bootstrappers` | `eks:node-bootstrapper` | 위와 동일. EKS에서는 노드 그룹과 부트스트랩 그룹 모두에 같은 역할을 바인딩 |

<br>

### rbac-tool policy-rules

특정 주체에 적용되는 정책 규칙 목록을 확인한다. `system:authenticated` 그룹에는 인증된 사용자라면 누구나 갖는 기본 정책이 바인딩되어 있다.

```bash
kubectl rbac-tool policy-rules -e '^system:authenticated'
```

```
  TYPE  | SUBJECT              | VERBS  | NAMESPACE | API GROUP             | KIND                     | NAMES | NONRESOURCEURI                                                                           | ORIGINATED FROM
--------+----------------------+--------+-----------+-----------------------+--------------------------+-------+------------------------------------------------------------------------------------------+------------------------------------------
  Group | system:authenticated | create | *         | authentication.k8s.io | selfsubjectreviews       |       |                                                                                          | ClusterRoles>>system:basic-user
  Group | system:authenticated | create | *         | authorization.k8s.io  | selfsubjectaccessreviews |       |                                                                                          | ClusterRoles>>system:basic-user
  Group | system:authenticated | create | *         | authorization.k8s.io  | selfsubjectrulesreviews  |       |                                                                                          | ClusterRoles>>system:basic-user
  Group | system:authenticated | get    | *         |                       |                          |       | /api,/api/*,/apis,/apis/*,/healthz,/livez,/openapi,/openapi/*,/readyz,/version,/version/ | ClusterRoles>>system:discovery
  Group | system:authenticated | get    | *         |                       |                          |       | /healthz,/livez,/readyz,/version,/version/                                               | ClusterRoles>>system:public-info-viewer
```

총 3개의 ClusterRole에서 정책이 파생된다.

| ClusterRole | 허용 동작 | 설명 |
| --- | --- | --- |
| `system:basic-user` | `create` selfsubject* 리소스 | 자기 자신의 접근 권한 조회 (SelfSubjectAccessReview 등) |
| `system:discovery` | `get` API 디스커버리 경로 | `/api`, `/apis`, `/openapi`, `/healthz` 등 API 엔드포인트 탐색 |
| `system:public-info-viewer` | `get` 공개 정보 경로 | `/healthz`, `/livez`, `/readyz`, `/version` 등 상태 확인 |

이들은 K8s가 기본으로 제공하는 ClusterRole로, 모든 인증된 사용자가 클러스터의 API 구조를 탐색하고 자기 자신의 권한을 조회할 수 있도록 보장한다.

<br>

### access-matrix

현재 인증된 사용자의 리소스별 접근 권한을 매트릭스 형태로 보여준다.

```bash
kubectl access-matrix                        # 클러스터 스코프 리소스
kubectl access-matrix --namespace default     # 네임스페이스 스코프 리소스
```

클러스터 스코프 결과를 일부 발췌하면 다음과 같다.

```
NAME                                                            LIST  CREATE  UPDATE  DELETE
apiservices.apiregistration.k8s.io                              ✔     ✔       ✔       ✔
clusterrolebindings.rbac.authorization.k8s.io                   ✔     ✔       ✔       ✔
clusterroles.rbac.authorization.k8s.io                          ✔     ✔       ✔       ✔
namespaces                                                      ✔     ✔       ✔       ✔
nodes                                                           ✔     ✔       ✔       ✔
persistentvolumes                                               ✔     ✔       ✔       ✔
selfsubjectaccessreviews.authorization.k8s.io                         ✔
subjectaccessreviews.authorization.k8s.io                             ✔
tokenreviews.authentication.k8s.io                                    ✔
```

admin 사용자에게 `AmazonEKSClusterAdminPolicy`가 연결되어 있으므로 대부분의 리소스에 대해 LIST/CREATE/UPDATE/DELETE 모두 허용(✔)된다. `selfsubjectaccessreviews`, `subjectaccessreviews`, `tokenreviews`처럼 **CREATE만 허용**되는 리소스는 조회 대상이 아닌 질의(요청) 전용 API 리소스이기 때문이다.

<details>
<summary>클러스터 스코프 전체 결과 (펼치기)</summary>

```
NAME                                                            LIST  CREATE  UPDATE  DELETE
apiservices.apiregistration.k8s.io                              ✔     ✔       ✔       ✔
applicationnetworkpolicies.networking.k8s.aws                   ✔     ✔       ✔       ✔
bindings                                                              ✔
certificaterequests.cert-manager.io                             ✔     ✔       ✔       ✔
certificates.cert-manager.io                                    ✔     ✔       ✔       ✔
certificatesigningrequests.certificates.k8s.io                  ✔     ✔       ✔       ✔
challenges.acme.cert-manager.io                                 ✔     ✔       ✔       ✔
clusterissuers.cert-manager.io                                  ✔     ✔       ✔       ✔
clusternetworkpolicies.networking.k8s.aws                       ✔     ✔       ✔       ✔
clusterpolicyendpoints.networking.k8s.aws                       ✔     ✔       ✔       ✔
clusterrolebindings.rbac.authorization.k8s.io                   ✔     ✔       ✔       ✔
clusterroles.rbac.authorization.k8s.io                          ✔     ✔       ✔       ✔
cninodes.vpcresources.k8s.aws                                   ✔     ✔       ✔       ✔
componentstatuses                                               ✔
configmaps                                                      ✔     ✔       ✔       ✔
controllerrevisions.apps                                        ✔     ✔       ✔       ✔
cronjobs.batch                                                  ✔     ✔       ✔       ✔
csidrivers.storage.k8s.io                                       ✔     ✔       ✔       ✔
csinodes.storage.k8s.io                                         ✔     ✔       ✔       ✔
csistoragecapacities.storage.k8s.io                             ✔     ✔       ✔       ✔
customresourcedefinitions.apiextensions.k8s.io                  ✔     ✔       ✔       ✔
daemonsets.apps                                                 ✔     ✔       ✔       ✔
deployments.apps                                                ✔     ✔       ✔       ✔
deviceclasses.resource.k8s.io                                   ✔     ✔       ✔       ✔
dnsendpoints.externaldns.k8s.io                                 ✔     ✔       ✔       ✔
endpoints                                                       ✔     ✔       ✔       ✔
endpointslices.discovery.k8s.io                                 ✔     ✔       ✔       ✔
eniconfigs.crd.k8s.amazonaws.com                                ✔     ✔       ✔       ✔
events                                                          ✔     ✔       ✔       ✔
events.events.k8s.io                                            ✔     ✔       ✔       ✔
flowschemas.flowcontrol.apiserver.k8s.io                        ✔     ✔       ✔       ✔
horizontalpodautoscalers.autoscaling                            ✔     ✔       ✔       ✔
ingressclasses.networking.k8s.io                                ✔     ✔       ✔       ✔
ingresses.networking.k8s.io                                     ✔     ✔       ✔       ✔
ipaddresses.networking.k8s.io                                   ✔     ✔       ✔       ✔
issuers.cert-manager.io                                         ✔     ✔       ✔       ✔
jobs.batch                                                      ✔     ✔       ✔       ✔
leases.coordination.k8s.io                                      ✔     ✔       ✔       ✔
limitranges                                                     ✔     ✔       ✔       ✔
localsubjectaccessreviews.authorization.k8s.io                        ✔
mutatingwebhookconfigurations.admissionregistration.k8s.io      ✔     ✔       ✔       ✔
namespaces                                                      ✔     ✔       ✔       ✔
networkpolicies.networking.k8s.io                               ✔     ✔       ✔       ✔
nodes                                                           ✔     ✔       ✔       ✔
nodes.metrics.k8s.io                                            ✔
orders.acme.cert-manager.io                                     ✔     ✔       ✔       ✔
persistentvolumeclaims                                          ✔     ✔       ✔       ✔
persistentvolumes                                               ✔     ✔       ✔       ✔
poddisruptionbudgets.policy                                     ✔     ✔       ✔       ✔
pods                                                            ✔     ✔       ✔       ✔
pods.metrics.k8s.io                                             ✔
podtemplates                                                    ✔     ✔       ✔       ✔
policyendpoints.networking.k8s.aws                              ✔     ✔       ✔       ✔
priorityclasses.scheduling.k8s.io                               ✔     ✔       ✔       ✔
prioritylevelconfigurations.flowcontrol.apiserver.k8s.io        ✔     ✔       ✔       ✔
replicasets.apps                                                ✔     ✔       ✔       ✔
replicationcontrollers                                          ✔     ✔       ✔       ✔
resourceclaims.resource.k8s.io                                  ✔     ✔       ✔       ✔
resourceclaimtemplates.resource.k8s.io                          ✔     ✔       ✔       ✔
resourcequotas                                                  ✔     ✔       ✔       ✔
resourceslices.resource.k8s.io                                  ✔     ✔       ✔       ✔
rolebindings.rbac.authorization.k8s.io                          ✔     ✔       ✔       ✔
roles.rbac.authorization.k8s.io                                 ✔     ✔       ✔       ✔
runtimeclasses.node.k8s.io                                      ✔     ✔       ✔       ✔
secrets                                                         ✔     ✔       ✔       ✔
securitygrouppolicies.vpcresources.k8s.aws                      ✔     ✔       ✔       ✔
selfsubjectaccessreviews.authorization.k8s.io                         ✔
selfsubjectreviews.authentication.k8s.io                              ✔
selfsubjectrulesreviews.authorization.k8s.io                          ✔
serviceaccounts                                                 ✔     ✔       ✔       ✔
servicecidrs.networking.k8s.io                                  ✔     ✔       ✔       ✔
services                                                        ✔     ✔       ✔       ✔
statefulsets.apps                                               ✔     ✔       ✔       ✔
storageclasses.storage.k8s.io                                   ✔     ✔       ✔       ✔
subjectaccessreviews.authorization.k8s.io                             ✔
tokenreviews.authentication.k8s.io                                    ✔
validatingadmissionpolicies.admissionregistration.k8s.io        ✔     ✔       ✔       ✔
validatingadmissionpolicybindings.admissionregistration.k8s.io  ✔     ✔       ✔       ✔
validatingwebhookconfigurations.admissionregistration.k8s.io    ✔     ✔       ✔       ✔
volumeattachments.storage.k8s.io                                ✔     ✔       ✔       ✔
volumeattributesclasses.storage.k8s.io                          ✔     ✔       ✔       ✔
```

</details>

<details>
<summary>네임스페이스 스코프(default) 전체 결과 (펼치기)</summary>

```
NAME                                            LIST  CREATE  UPDATE  DELETE
applicationnetworkpolicies.networking.k8s.aws   ✔     ✔       ✔       ✔
bindings                                              ✔
certificaterequests.cert-manager.io             ✔     ✔       ✔       ✔
certificates.cert-manager.io                    ✔     ✔       ✔       ✔
challenges.acme.cert-manager.io                 ✔     ✔       ✔       ✔
configmaps                                      ✔     ✔       ✔       ✔
controllerrevisions.apps                        ✔     ✔       ✔       ✔
cronjobs.batch                                  ✔     ✔       ✔       ✔
csistoragecapacities.storage.k8s.io             ✔     ✔       ✔       ✔
daemonsets.apps                                 ✔     ✔       ✔       ✔
deployments.apps                                ✔     ✔       ✔       ✔
dnsendpoints.externaldns.k8s.io                 ✔     ✔       ✔       ✔
endpoints                                       ✔     ✔       ✔       ✔
endpointslices.discovery.k8s.io                 ✔     ✔       ✔       ✔
events                                          ✔     ✔       ✔       ✔
events.events.k8s.io                            ✔     ✔       ✔       ✔
horizontalpodautoscalers.autoscaling            ✔     ✔       ✔       ✔
ingresses.networking.k8s.io                     ✔     ✔       ✔       ✔
issuers.cert-manager.io                         ✔     ✔       ✔       ✔
jobs.batch                                      ✔     ✔       ✔       ✔
leases.coordination.k8s.io                      ✔     ✔       ✔       ✔
limitranges                                     ✔     ✔       ✔       ✔
localsubjectaccessreviews.authorization.k8s.io        ✔
networkpolicies.networking.k8s.io               ✔     ✔       ✔       ✔
orders.acme.cert-manager.io                     ✔     ✔       ✔       ✔
persistentvolumeclaims                          ✔     ✔       ✔       ✔
poddisruptionbudgets.policy                     ✔     ✔       ✔       ✔
pods                                            ✔     ✔       ✔       ✔
pods.metrics.k8s.io                             ✔
podtemplates                                    ✔     ✔       ✔       ✔
policyendpoints.networking.k8s.aws              ✔     ✔       ✔       ✔
replicasets.apps                                ✔     ✔       ✔       ✔
replicationcontrollers                          ✔     ✔       ✔       ✔
resourceclaims.resource.k8s.io                  ✔     ✔       ✔       ✔
resourceclaimtemplates.resource.k8s.io          ✔     ✔       ✔       ✔
resourcequotas                                  ✔     ✔       ✔       ✔
rolebindings.rbac.authorization.k8s.io          ✔     ✔       ✔       ✔
roles.rbac.authorization.k8s.io                 ✔     ✔       ✔       ✔
secrets                                         ✔     ✔       ✔       ✔
securitygrouppolicies.vpcresources.k8s.aws      ✔     ✔       ✔       ✔
serviceaccounts                                 ✔     ✔       ✔       ✔
services                                        ✔     ✔       ✔       ✔
statefulsets.apps                               ✔     ✔       ✔       ✔
```

</details>

<br>

### rolesum

주체별 RBAC 역할을 바인딩 경로와 verb 매트릭스로 요약해 준다. 출력의 verb 약어는 다음과 같다.

| 약어 | Verb | 설명 |
| --- | --- | --- |
| **G** | `get` | 리소스 조회 |
| **L** | `list` | 리소스 목록 조회 |
| **W** | `watch` | 리소스 변경 감시 |
| **C** | `create` | 리소스 생성 |
| **U** | `update` | 리소스 수정 |
| **P** | `patch` | 리소스 일부 수정 |
| **D** | `delete` | 리소스 삭제 |
| **DC** | `deletecollection` | 리소스 일괄 삭제 |

> K8s API에서 리소스에 대해 수행할 수 있는 동작(verb)은 HTTP 메서드에 매핑된다. `get` → GET(단일), `list` → GET(컬렉션), `create` → POST, `update` → PUT, `patch` → PATCH, `delete` → DELETE 순이다. 자세한 내용은 [Kubernetes API 공식 문서](https://kubernetes.io/docs/reference/access-authn-authz/authorization/#determine-the-request-verb)를 참고한다.

**system:masters 그룹**

```bash
kubectl rolesum -k Group system:masters
```

```
Group: system:masters

Policies:
• [CRB] */cluster-admin ⟶  [CR] */cluster-admin
  Resource  Name  Exclude  Verbs  G L W C U P D DC
  *.*       [*]     [-]     [-]   ✔ ✔ ✔ ✔ ✔ ✔ ✔ ✔
```

`cluster-admin` ClusterRole이 바인딩되어 있고, `*.*`(모든 API 그룹의 모든 리소스)에 대해 전체 verb가 허용된다.

**system:authenticated 그룹**

```bash
kubectl rolesum -k Group system:authenticated
```

```
Group: system:authenticated

Policies:
• [CRB] */system:basic-user ⟶  [CR] */system:basic-user
  Resource                                       Name  Exclude  Verbs  G L W C U P D DC
  selfsubjectaccessreviews.authorization.k8s.io  [*]     [-]     [-]   ✖ ✖ ✖ ✔ ✖ ✖ ✖ ✖
  selfsubjectreviews.authentication.k8s.io       [*]     [-]     [-]   ✖ ✖ ✖ ✔ ✖ ✖ ✖ ✖
  selfsubjectrulesreviews.authorization.k8s.io   [*]     [-]     [-]   ✖ ✖ ✖ ✔ ✖ ✖ ✖ ✖
• [CRB] */system:discovery ⟶  [CR] */system:discovery
• [CRB] */system:public-info-viewer ⟶  [CR] */system:public-info-viewer
```

앞서 `rbac-tool policy-rules`로 확인한 3개 ClusterRole이 동일하게 보인다. `system:basic-user`를 통해 `selfsubject*` 리소스에 대한 `create`(C)만 허용되어, 자기 자신의 권한 조회만 가능하다.

**aws-node ServiceAccount (kube-system)**

```bash
kubectl rolesum aws-node -n kube-system
```

```
ServiceAccount: kube-system/aws-node

Policies:
• [CRB] */aws-node ⟶  [CR] */aws-node
  Resource                                          Name  Exclude  Verbs  G L W C U P D DC
  clusterpolicyendpoints.networking.k8s.aws         [*]     [-]     [-]   ✔ ✔ ✔ ✖ ✖ ✖ ✖ ✖
  clusterpolicyendpoints.networking.k8s.aws/status  [*]     [-]     [-]   ✔ ✖ ✖ ✖ ✖ ✖ ✖ ✖
  cninodes.vpcresources.k8s.aws                     [*]     [-]     [-]   ✔ ✔ ✔ ✖ ✖ ✔ ✖ ✖
  eniconfigs.crd.k8s.amazonaws.com                  [*]     [-]     [-]   ✔ ✔ ✔ ✖ ✖ ✖ ✖ ✖
  events.[,events.k8s.io]                           [*]     [-]     [-]   ✖ ✔ ✖ ✔ ✖ ✔ ✖ ✖
  namespaces                                        [*]     [-]     [-]   ✔ ✔ ✔ ✖ ✖ ✖ ✖ ✖
  nodes                                             [*]     [-]     [-]   ✔ ✔ ✔ ✖ ✖ ✖ ✖ ✖
  pods                                              [*]     [-]     [-]   ✔ ✔ ✔ ✖ ✖ ✖ ✖ ✖
  policyendpoints.networking.k8s.aws                [*]     [-]     [-]   ✔ ✔ ✔ ✖ ✖ ✖ ✖ ✖
  policyendpoints.networking.k8s.aws/status         [*]     [-]     [-]   ✔ ✖ ✖ ✖ ✖ ✖ ✖ ✖
```

VPC CNI 플러그인이 사용하는 ServiceAccount로, CNI 관련 CRD(`cninodes`, `eniconfigs`, `policyendpoints`)와 `nodes`, `pods` 등 네트워킹에 필요한 리소스에 대해 읽기(G/L/W) 위주의 최소 권한이 부여되어 있다. 생성/삭제 권한은 없고, `events`에 대한 `create`/`patch`만 예외적으로 허용되어 이벤트 기록 용도로 사용된다.

</details>

<br>

## SubjectAccessReview API 확인

[개념 글]({% post_url 2026-04-02-Kubernetes-EKS-Auth-02-02-EKS-Auth-AuthZ %})에서 다뤘듯이, SubjectAccessReview는 "이 주체가 이 동작을 할 수 있는가?"를 묻는 인가 요청 객체로, kube-apiserver가 인가 판단 시 EKS Webhook Authorizer에 보내는 것이 바로 이것이다. 관리자가 직접 이 요청을 생성하여 인가 체인의 동작을 확인할 수도 있다. 아래에서 이를 실습해 본다.

```bash
kubectl api-resources | grep subject
```

```
selfsubjectreviews                               authentication.k8s.io/v1          false        SelfSubjectReview
localsubjectaccessreviews                        authorization.k8s.io/v1           true         LocalSubjectAccessReview
selfsubjectaccessreviews                         authorization.k8s.io/v1           false        SelfSubjectAccessReview
selfsubjectrulesreviews                          authorization.k8s.io/v1           false        SelfSubjectRulesReview
subjectaccessreviews                             authorization.k8s.io/v1           false        SubjectAccessReview
```

`subject` 관련 API 리소스가 5종 확인된다.

| 리소스 | API 그룹 | Namespaced | 용도 |
| --- | --- | --- | --- |
| `SelfSubjectReview` | `authentication.k8s.io` | No | 현재 인증된 자기 자신의 identity 확인 |
| `SelfSubjectAccessReview` | `authorization.k8s.io` | No | 자기 자신이 특정 동작을 할 수 있는지 확인 |
| `SelfSubjectRulesReview` | `authorization.k8s.io` | No | 자기 자신에게 허용된 규칙 목록 조회 |
| `LocalSubjectAccessReview` | `authorization.k8s.io` | **Yes** | 특정 네임스페이스 내에서 주체의 인가 확인 |
| `SubjectAccessReview` | `authorization.k8s.io` | No | **임의 주체**의 인가 여부 질의 (클러스터 전체) |

`Self*` 리소스는 현재 인증된 사용자가 자기 자신에 대해 질의하는 것이고, `SubjectAccessReview`와 `LocalSubjectAccessReview`는 **다른 주체**에 대해서도 질의할 수 있어 관리자가 권한을 점검할 때 사용한다.

```bash
kubectl explain subjectaccessreviews
```

```
GROUP:      authorization.k8s.io
KIND:       SubjectAccessReview
VERSION:    v1

FIELDS:
     spec       <SubjectAccessReviewSpec> -required-
     Spec holds information about the request being evaluated

     status     <SubjectAccessReviewStatus>
     Status is filled in by the server and indicates whether the request is
     allowed or not
```

구조를 보면 `spec`에 질의 내용(누가, 어떤 리소스에, 어떤 동작을)을 담아 요청하면, 서버가 `status`에 허용 여부를 채워서 응답한다. [인증 실습]({% post_url 2026-04-02-Kubernetes-EKS-Auth-02-01-EKS-Auth-AuthN %})에서 다뤘던 TokenReview가 "이 토큰이 유효한가?"를 묻는 **인증** 요청이었다면, SubjectAccessReview는 "이 주체가 이 동작을 할 수 있는가?"를 묻는 **인가** 요청이다.

<br>

## SubjectAccessReview 직접 요청

admin 사용자가 `kube-system` 네임스페이스에서 `pods`를 `get`할 수 있는지 확인해 보자.

```bash
ACCOUNT_ID=$(aws sts get-caller-identity --query "Account" --output text)
cat << EOF | kubectl create -v=8 -f -
apiVersion: authorization.k8s.io/v1
kind: SubjectAccessReview
spec:
  user: "arn:aws:iam::${ACCOUNT_ID}:user/admin"
  groups:
    - system:masters
  resourceAttributes:
    namespace: "kube-system"
    verb: "get"
    resource: "pods"
EOF
```

`-v=8` 옵션으로 실행하면 kubectl의 HTTP 요청/응답 로그를 확인할 수 있다. 핵심 부분만 발췌한다.

**Request Body** — kubectl이 API 서버로 보낸 SubjectAccessReview 요청:

```json
{
  "apiVersion": "authorization.k8s.io/v1",
  "kind": "SubjectAccessReview",
  "spec": {
    "user": "arn:aws:iam::123456789012:user/admin",
    "groups": ["system:masters"],
    "resourceAttributes": {
      "namespace": "kube-system",
      "verb": "get",
      "resource": "pods"
    }
  }
}
```

**Request/Response** — API 서버로의 POST 요청과 응답:

```
"Request"  verb="POST" url="https://...eks.amazonaws.com/apis/authorization.k8s.io/v1/subjectaccessreviews?fieldManager=kubectl-create&fieldValidation=Strict"
"Response" status="201 Created" ... milliseconds=444
```

**Response Body** — API 서버가 `status`를 채워서 응답:

```json
{
  "kind": "SubjectAccessReview",
  "apiVersion": "authorization.k8s.io/v1",
  "spec": {
    "resourceAttributes": {
      "namespace": "kube-system",
      "verb": "get",
      "resource": "pods"
    },
    "user": "arn:aws:iam::123456789012:user/admin",
    "groups": ["system:masters"]
  },
  "status": {
    "allowed": true
  }
}
```

**최종 출력**:

```
subjectaccessreview.authorization.k8s.io/<unknown> created
```

핵심 필드를 정리하면 다음과 같다.

| 필드 | 값 | 의미 |
| --- | --- | --- |
| `spec.user` | `arn:aws:iam::123456789012:user/admin` | 인가를 확인할 대상 주체 |
| `spec.groups` | `["system:masters"]` | 해당 주체의 K8s 그룹 |
| `spec.resourceAttributes` | `kube-system` / `get` / `pods` | 확인할 동작 |
| `status.allowed` | `true` | **인가 통과** |

`system:masters` 그룹은 `cluster-admin` ClusterRole에 바인딩되어 모든 동작이 허용되므로 `allowed: true`가 반환된다.

> 최종 출력에서 리소스 이름이 `<unknown>`으로 표시되는 것은 정상이다. SubjectAccessReview는 etcd에 저장되지 않는 **비영속적(non-persisted) API 리소스**로, `.metadata.name`이 존재하지 않는다. API 서버가 요청을 받아 인가 판단을 수행하고 `status`를 채워 즉시 응답할 뿐, 오브젝트로 저장하지 않기 때문이다. TokenReview도 동일한 패턴이다.

<br>

# 3. 새 IAM Role로 Access Entry 테스트

현재까지는 클러스터 creator(admin)의 매핑을 확인했다. admin은 `AmazonEKSClusterAdminPolicy`로 전체 관리자 권한을 갖고 있어, 권한 제한에 따른 동작 차이를 관찰할 수 없다. 이제 **권한을 제한한 별도 IAM Role을 만들고 assume하여, 다른 권한 수준으로 클러스터에 접근**해 보자. 실제 운영 환경에서도 팀별·역할별로 IAM Role을 분리하고 필요할 때 assume하는 것이 일반적인 패턴이다.

> 참고: **AssumeRole**이란?
>
> AWS에서 **assume**은 "역할을 맡다"라는 의미다. IAM User(또는 다른 Role)가 STS(Security Token Service)에 `sts:AssumeRole` 요청을 보내면, STS가 trust policy를 검증한 뒤 해당 Role의 권한이 담긴 **임시 자격 증명**(Access Key + Secret Key + Session Token)을 발급한다. 요청자는 이 임시 자격 증명으로 해당 Role의 권한으로 활동하고, 세션이 만료되면 원래 권한으로 돌아간다. 원래 자기 자신의 자격 증명은 그대로 유지한 채, **일시적으로 다른 Role의 권한으로 전환**하는 것이 핵심이다.

<br>

## IAM Role 생성

먼저 trust policy를 작성한다. trust policy는 "**누가** 이 Role을 assume할 수 있는가"를 정의하는 IAM 정책이다.

```bash
export ACCOUNT_ID=$(aws sts get-caller-identity --query 'Account' --output text)

# Trust Policy: "누가 이 Role을 assume할 수 있는가"를 정의하는 IAM 정책
# - Principal: assume을 허용할 대상. :root는 해당 계정의 모든 IAM entity(User, Role 등)를 의미
# - Action: sts:AssumeRole → STS를 통해 임시 자격 증명을 발급받아 이 Role로 전환 가능
cat > trust-policy.json << EOF
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "AWS": "arn:aws:iam::${ACCOUNT_ID}:root"
      },
      "Action": "sts:AssumeRole"
    }
  ]
}
EOF
```

이제 이 trust policy로 Role을 생성한다.

```bash
aws iam create-role \
  --role-name eks-viewer-test-role \
  --assume-role-policy-document file://trust-policy.json
```

```json
{
    "Role": {
        "Path": "/",
        "RoleName": "eks-viewer-test-role",
        "RoleId": "AROACKEXAMPLEROLEID12",
        "Arn": "arn:aws:iam::123456789012:role/eks-viewer-test-role",
        "CreateDate": "2026-04-12T09:41:30+00:00",
        "AssumeRolePolicyDocument": {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Effect": "Allow",
                    "Principal": {
                        "AWS": "arn:aws:iam::123456789012:root"
                    },
                    "Action": "sts:AssumeRole"
                }
            ]
        }
    }
}
```

이 시점에서 Role 자체에는 어떤 AWS 권한도 부여되어 있지 않다. K8s 접근 권한은 다음 단계에서 EKS Access Entry + Access Policy로 부여한다.

<br>

## Access Entry 생성 + ViewPolicy 연결

새 Role에 대한 Access Entry를 생성하고, `AmazonEKSViewPolicy`(읽기 전용)를 연결한다. Access Entry 생성과 Access Policy 연결은 별도 API 호출이다.

```bash
# Access Entry 생성
# - --principal-arn: 이 IAM Role을 K8s 클러스터에 접근 가능한 주체로 등록
# - --type STANDARD: 일반 IAM User/Role 용. EC2 노드 Role은 EC2_LINUX 타입을 사용
aws eks create-access-entry \
  --cluster-name myeks \
  --principal-arn arn:aws:iam::${ACCOUNT_ID}:role/eks-viewer-test-role \
  --type STANDARD
```

```json
{
    "accessEntry": {
        "clusterName": "myeks",
        "principalArn": "arn:aws:iam::123456789012:role/eks-viewer-test-role",
        "kubernetesGroups": [],
        "accessEntryArn": "arn:aws:eks:ap-northeast-2:123456789012:access-entry/myeks/role/123456789012/eks-viewer-test-role/14cec08a-6ad3-db0d-163e-5abedd344426",
        "createdAt": "2026-04-12T18:45:19.564000+09:00",
        "modifiedAt": "2026-04-12T18:45:19.564000+09:00",
        "tags": {},
        "username": "arn:aws:sts::123456789012:assumed-role/eks-viewer-test-role/{{SessionName}}",
        "type": "STANDARD"
    }
}
```

`username` 필드를 보면, 이 Role을 assume한 주체가 K8s에서 `arn:aws:sts::...:assumed-role/eks-viewer-test-role/{{SessionName}}`이라는 이름으로 인식된다는 것을 알 수 있다. `{{SessionName}}`은 `sts:AssumeRole` 호출 시 지정한 세션 이름으로 치환된다.

```bash
# Access Policy 연결
# - --policy-arn: 연결할 EKS 관리형 정책. ViewPolicy는 K8s view ClusterRole에 대응 (읽기 전용)
# - --access-scope type=cluster: 클러스터 전체에 적용. namespace로 제한 시 type=namespace,namespaces=ns1,ns2
aws eks associate-access-policy \
  --cluster-name myeks \
  --principal-arn arn:aws:iam::${ACCOUNT_ID}:role/eks-viewer-test-role \
  --policy-arn arn:aws:eks::aws:cluster-access-policy/AmazonEKSViewPolicy \
  --access-scope type=cluster
```

```json
{
    "clusterName": "myeks",
    "principalArn": "arn:aws:iam::123456789012:role/eks-viewer-test-role",
    "associatedAccessPolicy": {
        "policyArn": "arn:aws:eks::aws:cluster-access-policy/AmazonEKSViewPolicy",
        "accessScope": {
            "type": "cluster",
            "namespaces": []
        },
        "associatedAt": "2026-04-12T18:45:33.620000+09:00",
        "modifiedAt": "2026-04-12T18:45:33.620000+09:00"
    }
}
```

`AmazonEKSViewPolicy`가 `cluster` scope으로 연결되었다. 이제 이 Role을 assume하면 클러스터 전체에서 리소스를 **읽기만** 할 수 있고, 생성·수정·삭제는 거부된다.

Access Entry 목록에 새 Role이 추가되었는지 확인한다.

```bash
aws eks list-access-entries --cluster-name myeks | jq
```

```json
{
  "accessEntries": [
    "arn:aws:iam::123456789012:role/aws-service-role/eks.amazonaws.com/AWSServiceRoleForAmazonEKS",
    "arn:aws:iam::123456789012:role/eks-viewer-test-role",
    "arn:aws:iam::123456789012:role/myeks-ng-1",
    "arn:aws:iam::123456789012:user/admin"
  ]
}
```

기존 3개에서 `eks-viewer-test-role`이 추가되어 4개가 되었다.

<br>

## 새 Role로 kubectl 테스트 -- 읽기 전용

새 Role을 assume하여 kubectl을 실행한다. ViewPolicy이므로 읽기는 되지만 쓰기는 거부되어야 한다.

```bash
# STS를 통해 Role assume → 임시 자격 증명(AccessKeyId, SecretAccessKey, SessionToken) 획득
# --role-session-name: 세션 식별자. K8s username의 {{SessionName}} 자리에 들어감
CREDS=$(aws sts assume-role \
  --role-arn arn:aws:iam::${ACCOUNT_ID}:role/eks-viewer-test-role \
  --role-session-name viewer-test)

# 발급된 임시 자격 증명을 환경 변수로 설정 → 이후 모든 AWS CLI/kubectl 호출에 이 자격 증명 사용
export AWS_ACCESS_KEY_ID=$(echo $CREDS | jq -r '.Credentials.AccessKeyId')
export AWS_SECRET_ACCESS_KEY=$(echo $CREDS | jq -r '.Credentials.SecretAccessKey')
export AWS_SESSION_TOKEN=$(echo $CREDS | jq -r '.Credentials.SessionToken')

# 현재 identity 확인
aws sts get-caller-identity
```

```json
{
    "UserId": "AROACKEXAMPLEROLEID12:viewer-test",
    "Account": "123456789012",
    "Arn": "arn:aws:sts::123456789012:assumed-role/eks-viewer-test-role/viewer-test"
}
```

`Arn`이 `arn:aws:iam::...:user/admin`이 아닌 `arn:aws:sts::...:assumed-role/eks-viewer-test-role/viewer-test`로 바뀌었다. 이제 이 터미널에서 실행하는 모든 AWS API 호출은 `eks-viewer-test-role` 권한으로 수행된다. Access Entry 생성 시 확인했던 `username` 필드의 `{{SessionName}}`이 여기서 지정한 `viewer-test`로 치환되어, K8s에서는 이 값이 인증된 사용자 이름으로 인식된다.

```bash
# kubeconfig 갱신
aws eks update-kubeconfig --name myeks --region ap-northeast-2
```

```
An error occurred (AccessDeniedException) when calling the DescribeCluster operation:
User: arn:aws:sts::123456789012:assumed-role/eks-viewer-test-role/viewer-test
is not authorized to perform: eks:DescribeCluster on resource:
arn:aws:eks:ap-northeast-2:123456789012:cluster/myeks
because no identity-based policy allows the eks:DescribeCluster action
```

`AccessDeniedException`이 발생한다. `update-kubeconfig`는 내부적으로 `eks:DescribeCluster` AWS API를 호출하여 클러스터 엔드포인트 정보를 가져오는데, `eks-viewer-test-role`에는 **IAM 정책이 하나도 없기 때문**이다.

여기서 중요한 구분이 드러난다.

| 레벨 | 관리 대상 | 설정 위치 |
| --- | --- | --- |
| **AWS IAM 레벨** | AWS API 호출 권한 (`eks:DescribeCluster` 등) | IAM Policy (identity-based) |
| **K8s 레벨** | K8s API 호출 권한 (`get pods` 등) | EKS Access Entry + Access Policy |

앞서 설정한 Access Entry / Access Policy는 K8s 레벨 권한이다. AWS API를 호출하려면 별도로 IAM 정책이 필요하다.

`eks:DescribeCluster` 최소 권한을 inline policy로 추가한다. viewer role에는 IAM 정책 수정 권한이 없으므로, 먼저 admin 자격 증명으로 복귀해야 한다.

```bash
# admin 자격 증명으로 복귀 (환경 변수 해제 → 원래 ~/.aws/credentials의 admin 사용)
unset AWS_ACCESS_KEY_ID AWS_SECRET_ACCESS_KEY AWS_SESSION_TOKEN

# 복귀 확인
aws sts get-caller-identity
```

```json
{
    "UserId": "AIDACKEXAMPLEUSERID12",
    "Account": "123456789012",
    "Arn": "arn:aws:iam::123456789012:user/admin"
}
```

admin으로 돌아왔다. `eks:DescribeCluster` 최소 권한을 inline policy로 추가한다.

```bash
# eks:DescribeCluster 최소 권한 추가 (대상 클러스터를 Resource로 한정)
aws iam put-role-policy \
  --role-name eks-viewer-test-role \
  --policy-name eks-describe-cluster \
  --policy-document '{
    "Version": "2012-10-17",
    "Statement": [
      {
        "Effect": "Allow",
        "Action": "eks:DescribeCluster",
        "Resource": "arn:aws:eks:ap-northeast-2:'${ACCOUNT_ID}':cluster/myeks"
      }
    ]
  }'
```

다시 viewer role로 assume한다.

```bash
CREDS=$(aws sts assume-role \
  --role-arn arn:aws:iam::${ACCOUNT_ID}:role/eks-viewer-test-role \
  --role-session-name viewer-test)
export AWS_ACCESS_KEY_ID=$(echo $CREDS | jq -r '.Credentials.AccessKeyId')
export AWS_SECRET_ACCESS_KEY=$(echo $CREDS | jq -r '.Credentials.SecretAccessKey')
export AWS_SESSION_TOKEN=$(echo $CREDS | jq -r '.Credentials.SessionToken')
```

이제 다시 kubeconfig를 갱신한다.

```bash
aws eks update-kubeconfig --name myeks --region ap-northeast-2
```

```
Updated context arn:aws:eks:ap-northeast-2:123456789012:cluster/myeks in /home/user/.kube/config
```

이번에는 `eks:DescribeCluster` 권한이 있으므로 정상적으로 갱신된다. 다만 `update-kubeconfig`는 context 이름을 ARN 전체(`arn:aws:eks:...`)로 설정하기 때문에, 기존 admin용 context를 덮어쓴다. 구분하기 쉽도록 `--alias`로 별칭을 지정하자.

```bash
# viewer 전용 context로 재설정
aws eks update-kubeconfig --name myeks --region ap-northeast-2 --alias myeks-viewer
kubectl config use-context myeks-viewer
```

```
Updated context myeks-viewer in /home/user/.kube/config
Switched to context "myeks-viewer".
```

프롬프트가 `(myeks-viewer:N/A)`로 바뀌어, 현재 viewer context임을 확인할 수 있다.

<details>
<summary>현재 kubeconfig 상태 (펼치기)</summary>

```yaml
apiVersion: v1
clusters:
- cluster:
    certificate-authority-data: LS0tLS1CRUdJ...  # (축약)
    server: https://C0D9900980BE2445FBFA9B92520D06B5.gr7.ap-northeast-2.eks.amazonaws.com
  name: arn:aws:eks:ap-northeast-2:123456789012:cluster/myeks

contexts:
# 기존 admin 실습에서 생성된 context
- context:
    cluster: arn:aws:eks:ap-northeast-2:123456789012:cluster/myeks
    user: arn:aws:eks:ap-northeast-2:123456789012:cluster/myeks
  name: myeks

# 이번 실습에서 --alias로 생성한 viewer context
- context:
    cluster: arn:aws:eks:ap-northeast-2:123456789012:cluster/myeks
    user: arn:aws:eks:ap-northeast-2:123456789012:cluster/myeks
  name: myeks-viewer

current-context: myeks-viewer    # ← 현재 활성 context

users:
- name: arn:aws:eks:ap-northeast-2:123456789012:cluster/myeks
  user:
    exec:
      apiVersion: client.authentication.k8s.io/v1beta1
      args: [--region, ap-northeast-2, eks, get-token, --cluster-name, myeks, --output, json]
      command: aws    # ← 실행 시 환경 변수의 AWS 자격 증명을 사용
```

`myeks`와 `myeks-viewer` 두 context 모두 같은 cluster와 user를 참조하지만, **어떤 AWS 자격 증명이 환경 변수에 설정되어 있느냐**에 따라 실제 K8s identity가 달라진다. `exec`의 `aws eks get-token` 명령이 현재 셸의 `AWS_ACCESS_KEY_ID` 등을 사용하기 때문이다.

</details>

이제 kubectl을 테스트한다. ViewPolicy(읽기 전용)이므로 읽기는 성공하고 쓰기는 거부되어야 한다.

```bash
# 읽기 테스트 (성공해야 함)
kubectl get pods -A
```

```
NAMESPACE      NAME                                       READY   STATUS    RESTARTS   AGE
cert-manager   cert-manager-b5c55cbd4-9gqnm               1/1     Running   0          2d21h
cert-manager   cert-manager-b5c55cbd4-9xj2q               1/1     Running   0          2d21h
cert-manager   cert-manager-cainjector-6fc9d9ddc7-9sn5z   1/1     Running   0          2d21h
cert-manager   cert-manager-cainjector-6fc9d9ddc7-vlslw   1/1     Running   0          2d21h
cert-manager   cert-manager-webhook-cf55c69cf-ckkls       1/1     Running   0          2d21h
cert-manager   cert-manager-webhook-cf55c69cf-g5lhs       1/1     Running   0          2d21h
external-dns   external-dns-699bd5cfdd-kj4ch              1/1     Running   0          2d21h
kube-system    aws-node-nx58q                             2/2     Running   0          2d21h
kube-system    aws-node-zlgch                             2/2     Running   0          97m
kube-system    coredns-7b7dc46964-7x57q                   1/1     Running   0          2d21h
kube-system    coredns-7b7dc46964-w9g5j                   1/1     Running   0          2d21h
kube-system    eks-pod-identity-agent-t28qb               1/1     Running   0          2d21h
kube-system    eks-pod-identity-agent-zhhbt               1/1     Running   0          2d21h
kube-system    kube-proxy-fwj5z                           1/1     Running   0          2d21h
kube-system    kube-proxy-njk7f                           1/1     Running   0          2d21h
kube-system    metrics-server-69cfcf7444-fpd5n            1/1     Running   0          2d21h
kube-system    metrics-server-69cfcf7444-tx86q            1/1     Running   0          2d21h
```

모든 네임스페이스의 Pod 목록이 정상 출력된다. ViewPolicy의 읽기 권한이 동작하는 것을 확인했다.

```bash
# 쓰기 테스트 (거부되어야 함)
kubectl run nginx-test --image=nginx -n default
```

```
Error from server (Forbidden): pods is forbidden: User "arn:aws:sts::123456789012:assumed-role/eks-viewer-test-role/viewer-test" cannot create resource "pods" in API group "" in the namespace "default"
```

```bash
# 삭제 테스트 (거부되어야 함)
kubectl delete pod cert-manager-b5c55cbd4-9gqnm -n cert-manager
```

```
Error from server (Forbidden): pods "cert-manager-b5c55cbd4-9gqnm" is forbidden: User "arn:aws:sts::123456789012:assumed-role/eks-viewer-test-role/viewer-test" cannot delete resource "pods" in API group "" in the namespace "cert-manager"
```

> **주의**: 삭제 테스트에서 `kube-system` 네임스페이스의 파드를 대상으로 했다. 지금은 ViewPolicy라 `Forbidden`으로 거부되지만, 만약 권한이 있는 상태에서 실행했다면 **클러스터 핵심 컴포넌트(CoreDNS, kube-proxy 등)가 삭제**되어 클러스터 장애가 발생할 수 있다. 실습이라도 `kube-system`의 파드를 삭제 대상으로 삼는 것은 피해야 한다.

```bash
# 현재 identity 확인
kubectl rbac-tool whoami
```

```
{Username: "arn:aws:sts::123456789012:assumed-role/eks-viewer-test-role/viewer-test",
 UID:      "",
 Groups:   [],
 Extra:    {}}
```

ViewPolicy(읽기 전용)이므로 `get`, `list`, `watch`는 허용되지만 `create`, `delete`, `update`는 거부된다. `whoami` 결과를 보면 admin과 달리 `Groups`가 비어 있고, `Username`이 assumed-role ARN 형태(`assumed-role/eks-viewer-test-role/viewer-test`)로 표시된다. Access Entry 생성 시 확인했던 `username` 필드와 정확히 일치한다.

<br>

## Access Policy 변경 -- EditPolicy로 업그레이드

동일한 Role에 연결된 정책을 ViewPolicy에서 EditPolicy로 변경하면 권한이 달라지는지 확인한다.

```bash
# 기존 admin identity로 복귀
unset AWS_ACCESS_KEY_ID AWS_SECRET_ACCESS_KEY AWS_SESSION_TOKEN

# ViewPolicy 해제
aws eks disassociate-access-policy \
  --cluster-name myeks \
  --principal-arn arn:aws:iam::${ACCOUNT_ID}:role/eks-viewer-test-role \
  --policy-arn arn:aws:eks::aws:cluster-access-policy/AmazonEKSViewPolicy

# EditPolicy 연결
aws eks associate-access-policy \
  --cluster-name myeks \
  --principal-arn arn:aws:iam::${ACCOUNT_ID}:role/eks-viewer-test-role \
  --policy-arn arn:aws:eks::aws:cluster-access-policy/AmazonEKSEditPolicy \
  --access-scope type=cluster
```

```json
{
    "clusterName": "myeks",
    "principalArn": "arn:aws:iam::123456789012:role/eks-viewer-test-role",
    "associatedAccessPolicy": {
        "policyArn": "arn:aws:eks::aws:cluster-access-policy/AmazonEKSEditPolicy",
        "accessScope": {
            "type": "cluster",
            "namespaces": []
        },
        "associatedAt": "2026-04-12T18:57:21.496000+09:00",
        "modifiedAt": "2026-04-12T18:57:21.496000+09:00"
    }
}
```

변경된 정책을 확인한다.

```bash
aws eks list-associated-access-policies \
  --cluster-name myeks \
  --principal-arn arn:aws:iam::${ACCOUNT_ID}:role/eks-viewer-test-role | jq
```

```json
{
  "associatedAccessPolicies": [
    {
      "policyArn": "arn:aws:eks::aws:cluster-access-policy/AmazonEKSEditPolicy",
      "accessScope": {
        "type": "cluster",
        "namespaces": []
      },
      "associatedAt": "2026-04-12T18:57:21.496000+09:00",
      "modifiedAt": "2026-04-12T18:57:21.496000+09:00"
    }
  ],
  "clusterName": "myeks",
  "principalArn": "arn:aws:iam::123456789012:role/eks-viewer-test-role"
}
```

`AmazonEKSViewPolicy`에서 `AmazonEKSEditPolicy`로 교체된 것을 확인했다. Access Policy 변경은 EKS 컨트롤 플레인 서버 측에서 즉시 반영되므로, kubeconfig 재설정 없이 다시 viewer role을 assume하기만 하면 된다.

다시 해당 Role로 assume하여 쓰기 테스트를 한다. 이번에는 `--role-session-name`을 `editor-test`로 변경했다.

```bash
CREDS=$(aws sts assume-role \
  --role-arn arn:aws:iam::${ACCOUNT_ID}:role/eks-viewer-test-role \
  --role-session-name editor-test)
export AWS_ACCESS_KEY_ID=$(echo $CREDS | jq -r '.Credentials.AccessKeyId')
export AWS_SECRET_ACCESS_KEY=$(echo $CREDS | jq -r '.Credentials.SecretAccessKey')
export AWS_SESSION_TOKEN=$(echo $CREDS | jq -r '.Credentials.SessionToken')
```

```bash
# 쓰기 테스트 (이번에는 성공해야 함)
kubectl run nginx --image=nginx -n default
```

```
pod/nginx created
```

ViewPolicy에서는 `Forbidden`이었던 Pod 생성이, EditPolicy로 변경한 뒤에는 성공한다. **Access Entry를 다시 만들거나 kubeconfig를 갱신할 필요 없이, Access Policy만 교체하면 즉시 권한이 바뀐다**는 것을 확인할 수 있다.

```bash
kubectl get pod nginx -n default
```

```
NAME    READY   STATUS    RESTARTS   AGE
nginx   1/1     Running   0          31s
```

Pod가 정상적으로 생성되어 Running 상태다. 테스트를 마쳤으니 정리한다.

```bash
kubectl delete pod nginx -n default
```

```
pod "nginx" deleted from default namespace
```

삭제도 성공한다. ViewPolicy에서는 `create`와 `delete` 모두 `Forbidden`이었지만, EditPolicy에서는 둘 다 허용된다. Access Policy를 ViewPolicy → EditPolicy로 교체한 것만으로 동일한 IAM Role의 K8s 권한이 달라지는 것을 확인할 수 있다.

<br>

# 4. 하이브리드 패턴: Group 매핑 + 커스텀 RBAC

앞서는 EKS 관리형 Access Policy(`ViewPolicy`, `EditPolicy`)를 사용했다. 이 방식은 간편하지만, "default 네임스페이스의 pods만 읽기 허용"처럼 **세밀한 권한 제어가 필요한 경우에는 관리형 정책만으로는 부족**하다. 이때 Access Entry에 **K8s Group만 매핑**하고, 해당 그룹에 대해 **커스텀 RBAC(ClusterRole + RoleBinding)**을 직접 정의하는 하이브리드 패턴을 사용할 수 있다.

```bash
# admin identity로 복귀
unset AWS_ACCESS_KEY_ID AWS_SECRET_ACCESS_KEY AWS_SESSION_TOKEN
```

<br>

## 기존 Access Entry 수정

기존 Access Entry에서 Access Policy를 제거하고, K8s Group만 지정한다.

```bash
# 기존 EditPolicy 해제
aws eks disassociate-access-policy \
  --cluster-name myeks \
  --principal-arn arn:aws:iam::${ACCOUNT_ID}:role/eks-viewer-test-role \
  --policy-arn arn:aws:eks::aws:cluster-access-policy/AmazonEKSEditPolicy
```

```bash
# K8s Group 매핑 추가
# - --kubernetes-groups: 이 IAM Role로 인증 시 K8s에서 추가로 부여할 그룹
# - Access Policy 없이 Group만 지정하면, K8s RBAC으로만 권한이 결정됨
aws eks update-access-entry \
  --cluster-name myeks \
  --principal-arn arn:aws:iam::${ACCOUNT_ID}:role/eks-viewer-test-role \
  --kubernetes-groups '["custom-test-group"]'
```

```json
{
    "accessEntry": {
        "clusterName": "myeks",
        "principalArn": "arn:aws:iam::123456789012:role/eks-viewer-test-role",
        "kubernetesGroups": [
            "custom-test-group"
        ],
        "accessEntryArn": "arn:aws:eks:ap-northeast-2:123456789012:access-entry/myeks/role/123456789012/eks-viewer-test-role/14cec08a-6ad3-db0d-163e-5abedd344426",
        "createdAt": "2026-04-12T18:45:19.564000+09:00",
        "modifiedAt": "2026-04-12T19:00:32.323000+09:00",
        "tags": {},
        "username": "arn:aws:sts::123456789012:assumed-role/eks-viewer-test-role/{{SessionName}}",
        "type": "STANDARD"
    }
}
```

`kubernetesGroups`에 `custom-test-group`이 추가되었다. 이제 이 Role을 assume한 주체는 K8s에서 `custom-test-group` 그룹에 속하게 되고, 해당 그룹에 바인딩된 RBAC 규칙이 적용된다.

<br>

## 커스텀 ClusterRole + RoleBinding 생성

`custom-test-group`에 대해 **default 네임스페이스의 pods만 읽을 수 있는** 커스텀 권한을 정의한다. 관리형 Access Policy에는 없는, 세밀한 범위 지정이 가능하다.

```bash
cat > custom-rbac.yaml << 'EOF'
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRole
metadata:
  name: custom-pod-reader
rules:
  # core API 그룹("")의 pods 리소스에 대해 읽기만 허용
- apiGroups: [""]
  resources: ["pods"]
  verbs: ["get", "list", "watch"]
---
apiVersion: rbac.authorization.k8s.io/v1
kind: RoleBinding                      # ClusterRoleBinding이 아닌 RoleBinding
metadata:
  name: custom-test-group-pod-reader
  namespace: default                   # default 네임스페이스에만 적용
subjects:
- kind: Group
  name: custom-test-group              # Access Entry에서 매핑한 K8s Group
  apiGroup: rbac.authorization.k8s.io
roleRef:
  kind: ClusterRole
  name: custom-pod-reader
  apiGroup: rbac.authorization.k8s.io
EOF

kubectl apply -f custom-rbac.yaml
```

```
clusterrole.rbac.authorization.k8s.io/custom-pod-reader created
rolebinding.rbac.authorization.k8s.io/custom-test-group-pod-reader created
```

ClusterRole로 "pods 읽기" 규칙을 정의하되, **RoleBinding**으로 `default` 네임스페이스에만 바인딩했다. 따라서 `default`에서는 pods를 조회할 수 있지만, `kube-system` 등 다른 네임스페이스에서는 거부될 것이다.

RoleBinding을 `default` 네임스페이스에만 생성했으므로, `default` 네임스페이스의 pods는 읽을 수 있지만 `kube-system` 네임스페이스의 pods는 읽을 수 없어야 한다.

<br>

## 테스트

```bash
CREDS=$(aws sts assume-role \
  --role-arn arn:aws:iam::${ACCOUNT_ID}:role/eks-viewer-test-role \
  --role-session-name hybrid-test)
export AWS_ACCESS_KEY_ID=$(echo $CREDS | jq -r '.Credentials.AccessKeyId')
export AWS_SECRET_ACCESS_KEY=$(echo $CREDS | jq -r '.Credentials.SecretAccessKey')
export AWS_SESSION_TOKEN=$(echo $CREDS | jq -r '.Credentials.SessionToken')
```

커스텀 RBAC에서 정의한 범위를 하나씩 확인한다.

```bash
# (1) default 네임스페이스 pods 읽기 → 성공해야 함
kubectl get pods -n default
```

```
NAME         READY   STATUS    RESTARTS   AGE
nginx-test   1/1     Running   0          5m26s
```

RoleBinding이 `default` 네임스페이스에 적용되어 있으므로, pods 조회가 성공한다.

```bash
# (2) kube-system 네임스페이스 pods 읽기 → 거부되어야 함
kubectl get pods -n kube-system
```

```
Error from server (Forbidden): pods is forbidden: User "arn:aws:sts::123456789012:assumed-role/eks-viewer-test-role/hybrid-test" cannot list resource "pods" in API group "" in the namespace "kube-system"
```

RoleBinding이 `default`에만 적용되어 있으므로, `kube-system`에서는 같은 pods 읽기도 거부된다. **네임스페이스 수준의 격리**가 동작하는 것을 확인할 수 있다.

```bash
# (3) default 네임스페이스에서 deployments 읽기 → 거부되어야 함
kubectl get deployments -n default
```

```
Error from server (Forbidden): deployments.apps is forbidden: User "arn:aws:sts::123456789012:assumed-role/eks-viewer-test-role/hybrid-test" cannot list resource "deployments" in API group "apps" in the namespace "default"
```

같은 `default` 네임스페이스라도, ClusterRole에서 허용한 리소스가 `pods`뿐이므로 `deployments`는 거부된다. **리소스 수준의 격리**도 동작한다.

```bash
# (4) 현재 identity 확인
kubectl rbac-tool whoami
```

```
{Username: "arn:aws:sts::123456789012:assumed-role/eks-viewer-test-role/hybrid-test",
 UID:      "",
 Groups:   [],
 Extra:    {}}
```

`Groups`가 비어 있는 것은 `whoami`가 TokenReview 응답을 보여주기 때문이다. Access Entry의 `kubernetesGroups`는 EKS 컨트롤 플레인이 인가 단계에서 내부적으로 주입하는 것이므로, TokenReview 응답에는 나타나지 않는다. 하지만 실제 RBAC 평가에서는 `custom-test-group` 그룹이 적용되어 위 테스트 결과처럼 동작한다.

정리하면 다음과 같다.

| 테스트 | 결과 | 이유 |
| --- | --- | --- |
| `get pods -n default` | **성공** | RoleBinding이 `default` 네임스페이스에 적용, pods 읽기 허용 |
| `get pods -n kube-system` | **거부** | RoleBinding 범위 밖 (네임스페이스 격리) |
| `get deployments -n default` | **거부** | ClusterRole에서 `pods`만 허용 (리소스 격리) |

Access Policy 없이 K8s Group만 매핑한 경우, EKS Webhook Authorizer는 해당 요청에 대해 "No Opinion"을 반환하고 K8s RBAC Authorizer로 넘어간다. 따라서 **커스텀 RBAC에서 정의한 것만큼만** 정확히 권한이 부여된다.

<br>

# 5. 실습 리소스 정리

```bash
# admin identity로 복귀
unset AWS_ACCESS_KEY_ID AWS_SECRET_ACCESS_KEY AWS_SESSION_TOKEN

# K8s 리소스 정리
kubectl delete clusterrole custom-pod-reader --ignore-not-found
kubectl delete rolebinding custom-test-group-pod-reader -n default --ignore-not-found
kubectl delete pod nginx-test -n default --ignore-not-found

# EKS Access Entry 삭제
aws eks delete-access-entry \
  --cluster-name myeks \
  --principal-arn arn:aws:iam::${ACCOUNT_ID}:role/eks-viewer-test-role

# IAM Role 삭제 (연결된 inline policy를 먼저 제거해야 함)
aws iam delete-role-policy --role-name eks-viewer-test-role --policy-name eks-describe-cluster
aws iam delete-role --role-name eks-viewer-test-role

# 실습 중 생성된 임시 파일 정리
rm -f trust-policy.json custom-rbac.yaml

# kubeconfig에서 viewer context 제거
kubectl config delete-context myeks-viewer 2>/dev/null
```

<br>

# 정리

매핑([7])과 인가([8]~[9]) 과정을 실습으로 확인했다.

| 실습 | 확인한 것 | Overview 단계 |
| --- | --- | --- |
| Access Entry / Policy 목록 확인 | 매핑 구성과 연결된 정책 | [7] |
| `rbac-tool whoami` | 매핑 결과(K8s username, groups). creator의 `system:masters` 생략 | [7] |
| `SubjectAccessReview` | 특정 주체+그룹의 인가 여부 직접 질의 | [8]+[9] |
| 새 IAM Role + ViewPolicy | 읽기 전용 권한으로 클러스터 접근 | [7]+[8]+[9] |
| ViewPolicy → EditPolicy | Access Policy 변경만으로 권한 변화 확인 | [8] |
| Group 매핑 + 커스텀 RBAC | 하이브리드 패턴: 네임스페이스/리소스 수준 세밀 제어 | [7]+[8]+[9] |

인증(AuthN)부터 매핑(브릿지)과 인가(AuthZ)까지, EKS에서 사용자가 K8s API에 접근하는 전체 과정을 실습으로 확인했다. 다음 글부터는 흐름 3(Pod → AWS API), 즉 Pod Identity/IRSA를 통한 Pod의 AWS 리소스 접근을 다룰 예정이다.

<br>

# 참고 자료

- [AWS EKS 공식 문서 - Grant IAM users and roles access to Kubernetes APIs](https://docs.aws.amazon.com/eks/latest/userguide/grant-k8s-access.html)
- [AWS EKS 공식 문서 - Creating access entries](https://docs.aws.amazon.com/eks/latest/userguide/creating-access-entries.html)
- [AWS EKS 공식 문서 - Access policy permissions](https://docs.aws.amazon.com/eks/latest/userguide/access-policy-permissions.html)
- [Kubernetes 공식 문서 - Authorization Overview](https://kubernetes.io/docs/reference/access-authn-authz/authorization/): SubjectAccessReview 스펙
- [rbac-tool GitHub](https://github.com/alcideio/rbac-tool): `whoami`, `lookup` 등 RBAC 디버깅 도구

<br>
