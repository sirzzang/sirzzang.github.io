---
title: "[EKS] EKS: 인증/인가 - 5. 사용자 → K8s API: 매핑과 인가(AuthZ)"
excerpt: "인증 완료 후 인가를 위해 IAM identity를 K8s username/group으로 변환하는 브릿지 단계에 대해 정리해 보자."
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
  - aws-auth
  - aws-iam-authenticator
  - AWS-EKS-Workshop-Study
  - AWS-EKS-Workshop-Study-Week-4
---

*[서종호(가시다)](https://www.linkedin.com/in/gasida99/)님의 AWS EKS Workshop Study(AEWS) 4주차 학습 내용을 기반으로 합니다.*

<br>

# TL;DR

- 인증이 완료되면 IAM ARN이 확인되지만, K8s RBAC은 IAM ARN을 모른다. IAM ARN을 K8s username/group으로 **변환하는 브릿지** 단계가 필요하다
- 이 매핑을 수행하는 방안이 두 가지다: **Access Entry**(EKS API, 권장)와 **aws-auth ConfigMap**(deprecated)
- 근본 차이: ConfigMap은 "K8s 안에서 IAM을 바라보는 것"이고, Access Entry는 "AWS에서 K8s 권한을 내려다보는 것"이다. ConfigMap이 deprecated되고 Access Entry가 도입되면서 매핑의 관리 주체가 K8s에서 AWS로 이동했다
- Access Entry는 **Access Policy**(AWS 관리형 ~6종)로 간편하게 권한을 부여하거나, **K8s Group만 매핑**하고 커스텀 RBAC을 직접 정의하는 하이브리드 패턴을 지원한다
- ConfigMap → Access Entry 마이그레이션은 `CONFIG_MAP` → `API_AND_CONFIG_MAP` → `API` 순서로 진행하며, 되돌릴 수 없다

<br>

# 개요

[이전 글]({% post_url 2026-04-02-Kubernetes-EKS-Auth-02-01-EKS-Auth-AuthN %})에서 EKS 인증 4단계를 실습으로 확인했다. 토큰 생성부터 STS 검증까지 거치면, API 서버는 "이 요청을 보낸 사람은 `arn:aws:iam::123456789012:user/admin`이다"라는 것을 알게 된다.

그런데 K8s RBAC은 IAM ARN을 모른다. RBAC이 이해하는 것은 K8s **username**과 **group**이다. 따라서 인증의 결과(검증된 IAM identity)를 인가의 입력(K8s username/group)으로 변환하는 단계가 필요하다. [전체 흐름 개요]({% post_url 2026-04-02-Kubernetes-EKS-Auth-02-00-EKS-Auth-Overview %})의 **[7] K8S User 확인** 단계에 해당한다.

이 글에서는 매핑 단계의 **개념과 설계 원칙**을 정리한다. 두 가지 매핑 방안(Access Entry, aws-auth ConfigMap)의 내부 구조와 차이를 다루고, 필요한 실습은 다음 글에서 진행한다.

<br>

# 왜 브릿지가 필요한가

[EKS 인증/인가 시리즈 개요]({% post_url 2026-04-02-Kubernetes-EKS-Auth-00-00-Overview %})에서 다뤘듯이, AWS IAM과 K8s RBAC은 서로의 신분증을 모르는 완전히 분리된 인증/인가 체계다. IAM은 `arn:aws:iam::...:user/admin`이라는 ARN으로 주체를 식별하지만, K8s RBAC은 `username`과 `group`으로 주체를 식별한다.

[이전 글]({% post_url 2026-04-02-Kubernetes-EKS-Auth-02-01-EKS-Auth-AuthN %})의 TokenReview 응답에서 이미 이 변환의 결과를 직접 확인했다.

```json
{
  "status": {
    "authenticated": true,
    "user": {
      "username": "arn:aws:iam::123456789012:user/admin",
      "groups": ["system:authenticated"]
    }
  }
}
```

`status.user`의 `username`과 `groups`가 바로 이 브릿지 단계의 **산출물**이다. aws-iam-authenticator가 STS 검증으로 IAM identity를 확인한 뒤, 매핑 정보를 조회하여 K8s username/group으로 변환한 결과를 API 서버에 돌려준다. API 서버는 이 username/group을 가지고 RBAC 인가를 수행한다.

여기서 핵심 질문은: "매핑 정보를 **어디서** 가져오는가?"이다. 이 질문에 대한 답이 두 가지 방안으로 갈린다.

- **Access Entry** — AWS EKS 관리형 Internal DB에서 가져온다. AWS API로 독립 관리되므로 클러스터 장애와 무관하게 복구 가능하다.
- **aws-auth ConfigMap** — K8s 내부 `kube-system` 네임스페이스의 ConfigMap(etcd)에서 가져온다. K8s API에 접근해야 관리할 수 있으므로, 잘못 수정하면 복구가 어렵다. 현재 deprecated 상태다.

<br>

# 두 방안의 설계 철학

[전체 흐름 개요]({% post_url 2026-04-02-Kubernetes-EKS-Auth-02-00-EKS-Auth-Overview %})에서 두 방안의 기본 비교를 다뤘다. 여기서는 그 비교를 확장하여 설계 철학의 차이를 살펴본다.

| 구분 | **Access Entry (EKS API)** | **aws-auth ConfigMap** |
| --- | --- | --- |
| **상태** | **권장** | **deprecated** |
| **데이터 저장소** | AWS EKS 관리형 Internal DB | K8s 내부의 ConfigMap (etcd) |
| **관리 인터페이스** | AWS API / 콘솔 (K8s API 접근 불필요) | `kubectl edit` 등 (K8s API 접근 필요) |
| **장애 복구** | 클러스터 응답 불능이어도 AWS API로 복구 가능 | ConfigMap 잘못 수정 시 복구 어려움 (K8s API 접근 필요) |
| **닭과 달걀 문제** | 없음 (AWS API로 독립 관리) | 있음 (K8s에 접근해야 K8s 접근 권한을 줄 수 있음) |
| **IaC 친화성** | AWS provider로 클러스터와 동시 선언 가능 | K8s provider 필요 + 클러스터 선행 필요 (순환 의존성) |
| **인가 엔진** | Node + RBAC + **Webhook** (3개 체인) | Node + RBAC (2개 체인) |
| **중복 시 우선순위** | **우선** | 무시됨 |

근본적인 차이를 다음과 같이 정리할 수 있다: 

- ConfigMap은 **"K8s 안에서 IAM을 바라보는 것"**이고, Access Entry는 **"AWS에서 K8s 권한을 내려다보는 것"**이다. 
- ConfigMap이 deprecated되고 Access Entry가 도입되면서, 매핑의 관리 주체(control plane)가 K8s에서 AWS로 이동한 것이 핵심이다.

```text
aws-auth ConfigMap                   Access Entry (EKS API)

  K8s etcd                             AWS 관리형 DB
    └─ ConfigMap                         └─ Access Entry
         └─ mapRoles                          └─ principal ARN
         └─ mapUsers                          └─ type / username
                                              └─ Access Policy
  관리: kubectl edit
  장애 시: K8s API 필요                관리: aws eks CLI / 콘솔
                                     장애 시: AWS API로 복구 가능
```

<br>

# K8s Group 개념

두 매핑 방안 모두 IAM principal을 K8s **Group**에 연결한다는 점에서 Group 개념을 먼저 정리할 필요가 있다.

K8s Group은 EKS 고유 개념이 아니라 **K8s 원래의 RBAC 개념**이다. 온프레미스 K8s에서도 X.509 클라이언트 인증서의 `O`(Organization) 필드가 K8s Group으로 매핑되고, OIDC 토큰의 `groups` claim도 마찬가지다. `system:masters`, `system:authenticated`, `system:unauthenticated` 같은 빌트인 그룹도 K8s 자체에 존재한다.

다만 ServiceAccount와 달리 **K8s 오브젝트로 존재하지 않는다**는 점이 직관적이지 않다. `kubectl get groups` 같은 명령은 없다. Group은 인증 시점에 토큰에 포함되는 **논리적 레이블**이며, RoleBinding/ClusterRoleBinding의 `subjects`에서 `kind: Group`으로 참조된다.

```yaml
subjects:
- kind: Group
  name: my-team-group
  apiGroup: rbac.authorization.k8s.io
roleRef:
  kind: ClusterRole
  name: edit
  apiGroup: rbac.authorization.k8s.io
```

결국 **IAM → Group → Role** 2단계 매핑 체인이며, 이 체인의 앞부분(IAM → Group)을 누가 담당하느냐가 두 방안의 차이다.

```text
IAM Role/User              K8s Group              K8s ClusterRole
─────────────── ──(매핑)── ───────────── ──(CRB)── ─────────────────────────
arn:...:role/Dev       →   dev-group          →   edit (또는 커스텀 Role)
```

- **aws-auth ConfigMap**: ConfigMap의 `groups` 필드에 그룹명을 지정한다. authenticator가 해당 IAM 주체의 TokenReview 응답에 그 그룹을 넣어주고, RBAC이 해당 그룹에 바인딩된 Role/ClusterRole의 권한으로 인가를 수행한다
- **Access Entry**: `STANDARD` type의 Access Entry에서 `kubernetesGroups` 필드에 그룹명을 지정한다. 동일하게 TokenReview 응답에 그룹이 포함되며 RBAC 인가가 수행된다. 또는 Access Policy를 연결하면 K8s Group/RBAC 없이도 EKS Webhook 인가로 권한이 부여된다

<br>

# aws-auth ConfigMap (deprecated)

EKS 초기부터 사용하던 방식으로, `kube-system` 네임스페이스의 `aws-auth` ConfigMap에 IAM → K8s 매핑을 직접 기록한다. deprecated 상태이지만, 리소스 자체가 삭제된 것은 아니다. `CONFIG_MAP` 또는 `API_AND_CONFIG_MAP` 모드에서는 여전히 활성 상태로 동작하며, `API` 모드로 전환하더라도 ConfigMap이 **무시**될 뿐 자동 삭제되지는 않는다. 여기서 deprecated는 "AWS가 이 방식을 더 이상 권장하지 않으며, Access Entry로 마이그레이션하라"는 방향성을 의미한다. 기존 클러스터에서 여전히 사용되고 있고, Access Entry로의 마이그레이션을 이해하기 위해서도 알아둘 필요가 있다.

> [1주차 클러스터 구성 확인]({% post_url 2026-03-12-Kubernetes-EKS-01-01-04-EKS-Cluster-Result %})에서 `kube-system` 리소스 목록에 `aws-auth` ConfigMap이 있는 것을 확인했지만, 내부 구조는 다루지 않았다. 여기서 그 내부를 살펴본다.

<br>

## ConfigMap 구조

aws-auth ConfigMap은 세 가지 매핑 섹션을 가진다.

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: aws-auth
  namespace: kube-system
data:
  # IAM Role → K8s username/group 매핑
  mapRoles: |
    # 워커 노드 조인용 — 노드의 EC2 인스턴스 Role을 system:nodes 그룹에 매핑
    - rolearn: arn:aws:iam::123456789012:role/myeks-ng-role
      username: system:node:{% raw %}{{EC2PrivateDNSName}}{% endraw %}
      groups:
      - system:bootstrappers
      - system:nodes
    # 개발팀 Role — assume role한 사용자를 dev-admin으로 매핑
    - rolearn: arn:aws:iam::123456789012:role/DevTeamRole
      username: dev-admin
      groups:
      - eks-console-dashboard-full-access-group
  # IAM User → K8s username/group 매핑
  mapUsers: |
    # 특정 IAM User에 직접 cluster-admin 권한 부여 (Role 사용 권장)
    - userarn: arn:aws:iam::123456789012:user/admin
      username: kubernetes-admin
      groups:
      - system:masters
  # AWS 계정 전체 자동 매핑 — 계정 내 모든 IAM 주체가 접근 가능
  mapAccounts: |
    - "234567890123"
    - "345678901234"
```

| 섹션 | 용도 | 매핑 대상 |
| --- | --- | --- |
| `mapRoles` | IAM Role → K8s username/group | EC2 노드 인스턴스 Role, Federated User Role, 개발팀 Role 등 |
| `mapUsers` | IAM User → K8s username/group | 특정 IAM User에 직접 권한 부여 (IAM 모범 사례상 Role 사용 권장) |
| `mapAccounts` | AWS 계정 전체 자동 매핑 | 계정 ID만 지정하면 해당 계정의 모든 IAM 주체가 자동으로 매핑 |

`mapRoles`의 `username` 필드에는 템플릿 변수를 사용할 수 있다: `{% raw %}{{AccountID}}{% endraw %}`, `{% raw %}{{SessionName}}{% endraw %}`, `{% raw %}{{EC2PrivateDNSName}}{% endraw %}` 등. 노드 조인 시 `{% raw %}{{EC2PrivateDNSName}}{% endraw %}`으로 각 노드의 고유 hostname을 username에 반영한다.

<br>

## 노드 조인 메커니즘

aws-auth ConfigMap에서 가장 중요한 매핑은 **노드 조인**이다. EKS 워커 노드도 IAM Role로 인증하며, 이 Role이 `system:bootstrappers`와 `system:nodes` 그룹에 매핑되어야 노드가 클러스터에 정상적으로 조인할 수 있다.

```yaml
mapRoles: |
  - rolearn: arn:aws:iam::123456789012:role/myeks-ng-role
    username: system:node:{% raw %}{{EC2PrivateDNSName}}{% endraw %}
    groups:
    - system:bootstrappers
    - system:nodes
```

[1주차 워커 노드 확인]({% post_url 2026-03-12-Kubernetes-EKS-01-01-05-EKS-Cluster-Worker-Node-Result %})에서 노드의 kubelet이 `aws eks get-token`으로 인증하는 것을 확인했다. 그 인증 결과를 K8s node identity(`system:node:<hostname>`)로 변환하는 것이 바로 이 매핑이다.

| 그룹 | 역할 |
| --- | --- |
| `system:bootstrappers` | 노드가 처음 클러스터에 참여할 때 필요한 CSR 생성 권한 |
| `system:nodes` | 조인 완료 후 kubelet이 API 서버와 통신하는 데 필요한 권한 |

<br>

## 운영 리스크와 한계

ConfigMap 방식은 구조 자체가 단순하지만, 운영 시 치명적인 리스크와 제약이 존재한다. 이 리스크들이 곧 Access Entry 도입의 직접적 배경이다.

### 노드 매핑 삭제 → 전체 NotReady

위 노드 조인 매핑에서 `system:nodes` 그룹을 실수로 삭제하면, 약 5분 후 모든 노드가 **NotReady** 상태에 빠진다. ConfigMap의 가장 큰 리스크가 여기에 있다.

실제로 ConfigMap만 사용하던 때에는 `system:nodes` 그룹 삭제로 인한 장애를 직접 재현(EKS 1.24, CONFIG_MAP 모드)할 수 있었다.

> 현재는 CONFIG_MAP 단독 모드가 지원되지 않아 직접 재현할 수 없다. 아래 내용은 스터디장(가시다)님의 자료를 참고하여 작성하였다.


```bash
# [터미널1] 노드 상태 모니터링
watch -d kubectl get node

# aws-auth ConfigMap에서 system:nodes 삭제
kubectl edit cm -n kube-system aws-auth
```

```yaml
# system:nodes를 삭제하면...
data:
  mapRoles: |
    - groups:
      - system:bootstrappers
      # - system:nodes        ← 이 한 줄 삭제만으로 장애 발생
```

약 5분 후 모든 노드가 NotReady로 전환된다.

```text
NAME                                               STATUS     ROLES    AGE    VERSION
ip-192-168-1-68.ap-northeast-2.compute.internal    NotReady   <none>   134m   v1.24.13-eks-0a21954
ip-192-168-2-53.ap-northeast-2.compute.internal    NotReady   <none>   134m   v1.24.13-eks-0a21954
ip-192-168-3-175.ap-northeast-2.compute.internal   NotReady   <none>   134m   v1.24.13-eks-0a21954
```

원복은 `kubectl edit cm -n kube-system aws-auth`로 `system:nodes`를 다시 추가하면 된다. 하지만 이 원복 자체도 K8s API 접근이 필요하므로, **ConfigMap을 잘못 건드린 사람이 K8s 접근 권한마저 잃었다면 복구가 불가능**하다.

> 현재 실습 환경은 `API_AND_CONFIG_MAP` 또는 `API` 모드이다. 이 모드에서는 EKS API(Access Entry)와 ConfigMap **두 경로**로 IAM → K8s 매핑을 관리한다. ConfigMap에서 `system:nodes` 매핑을 삭제하더라도, Access Entry 쪽에 동일한 노드 역할 매핑이 남아 있기 때문에 kubelet이 API 서버에 정상적으로 인증·인가를 받을 수 있고, 결과적으로 노드는 Ready 상태를 유지한다. 즉, ConfigMap이 SPOF였던 기존 구조에서 발생하던 장애가 구조적으로 차단되는 것이며, 이것이 **Access Entry 도입의 실질적 효과**다.

이런 위험 때문에 Access Entry 도입 이전에는 aws-auth ConfigMap에 [`immutable: true`]({% post_url 2026-04-05-Kubernetes-Application-Config-02-ConfigMap %})를 설정하여 `kubectl edit`에 의한 실수를 원천 차단하는 운영 방안이 권장되기도 했다.

### Creator의 암묵적 매핑

EKS 클러스터를 생성한 IAM principal은 aws-auth ConfigMap과 **상관없이** `kubernetes-admin` username으로 `system:masters` 그룹에 자동 매핑된다. 이 매핑은 EKS 컨트롤 플레인 내부에 하드코딩되어 있고, ConfigMap에 명시적으로 기록되지 않는다.

따라서 `kubectl describe configmap aws-auth -n kube-system`으로 확인해도 creator의 매핑은 보이지 않는다. 이것이 때때로 혼란을 주지만, "ConfigMap에 없는데 왜 `system:masters` 권한을 가지고 있지?"의 답이다.

> `system:masters`의 위험성에 대해서는 [RBAC 모범 사례]({% post_url 2026-04-02-Kubernetes-EKS-Auth-00-04-RBAC-Good-Practices %})에서 다뤘다. `system:masters`는 RBAC과 Authorization Webhook을 모두 우회하므로, 가능한 한 사용을 지양해야 한다.

### 닭과 달걀 문제 + Lockout 리스크

ConfigMap 방식의 근본적 문제는 **K8s에 접근해야 K8s 접근 권한을 줄 수 있다**는 것이다.

- 새 팀원에게 클러스터 접근 권한을 주려면 → `kubectl edit configmap aws-auth` → K8s API 접근이 필요
- K8s API에 접근하려면 → 이미 클러스터에 접근 권한이 있어야 함

Creator가 이미 `system:masters` 권한을 가지고 있으므로 최초 설정은 가능하지만, 만약 **ConfigMap을 잘못 수정**하면:

- 노드 Role 매핑 삭제 → 모든 노드 NotReady
- 모든 사용자 매핑 삭제 → 클러스터 접근 불가 (creator의 암묵적 매핑은 유지되므로 creator는 접근 가능)
- Creator 외에 관리자가 없고 creator의 IAM 자격증명이 분실된 경우 → **완전한 lockout**

이 lockout 문제를 해결하기 위해 Access Entry가 등장했다. 앞서 [노드 매핑 삭제](#노드-매핑-삭제--전체-notready)에서 다룬 장애 재현 시나리오와 `immutable` 운영 방안도 결국 이 lockout 리스크에서 비롯된 것이다.

### ARN Path 제약

ConfigMap의 `rolearn`에 IAM Role ARN을 지정할 때, **path가 포함된 ARN은 사용할 수 없다**.

```text
# 가능
arn:aws:iam::123456789012:role/my-role

# 불가능 (my-team/developers/ 가 path)
arn:aws:iam::123456789012:role/my-team/developers/my-role
```

IAM에서는 Role을 폴더처럼 분류할 수 있어서 `role/my-team/developers/my-role` 형태의 ARN이 유효하지만, aws-iam-authenticator가 ConfigMap의 `rolearn`과 토큰의 IAM ARN을 **문자열 비교**할 때 path를 제대로 파싱하지 못한다. path가 포함되면 매핑이 실패하여 권한 오류가 발생한다.

> Access Entry에서는 이 제약이 해소되어 `arn:aws:iam::123456789012:role/my-team/developers/my-role` 형태도 사용할 수 있다.

<br>

## 인가 체인

ConfigMap 방식에서의 인가는 순수 K8s RBAC이다. API 서버의 인가 체인은 **Node + RBAC** 2개다.

매핑된 K8s username/group에 대해 ClusterRole/RoleBinding을 직접 만들어야 한다. `system:masters` 같은 K8s 기본 그룹에 매핑하면 별도 RBAC 리소스 생성이 불필요하지만, 커스텀 그룹을 사용할 경우 ClusterRole/RoleBinding을 직접 생성하고 관리해야 한다.

<br>

## AWS 가이드 절차

AWS 공식 문서에서는 ConfigMap 방식을 다음 순서로 안내한다.

1. 기존 K8s Role/ClusterRole과 RoleBinding/ClusterRoleBinding 확인 → 매핑할 그룹에 적절한 권한이 부여되어 있는지 검증
2. `eksctl create iamidentitymapping` 또는 `kubectl edit configmap aws-auth -n kube-system`으로 `mapRoles`/`mapUsers` 항목 추가
3. 노드 조인 상태 확인 (`kubectl get nodes --watch`)

핵심은 **IAM ARN과 K8s Group을 연결**하는 것이다. deprecated 방식이므로 별도 실습은 진행하지 않고, 실습에서는 Access Entry 방식을 중심으로 다룬다.

<br>

# Access Entry (EKS API)

2023년 말에 도입된 방식으로, aws-auth ConfigMap의 lockout 문제를 해결하기 위해 등장했다. IAM → K8s 매핑 정보를 **EKS 관리형 DB**에 저장하고, **AWS API**로 관리한다. K8s API에 접근하지 않아도 되므로 닭과 달걀 문제가 없다.

> [1주차 실습 환경 구성]({% post_url 2026-03-12-Kubernetes-EKS-01-01-01-Installation %})에서 Terraform의 `enable_cluster_creator_admin_permissions = true` 설정으로 이미 Access Entry를 사용했다. [배포 결과 확인]({% post_url 2026-03-12-Kubernetes-EKS-01-01-02-Installation-Result %})에서 콘솔의 IAM 액세스 항목에 3개 entry(서비스 역할, 노드 역할, user/admin + `AmazonEKSClusterAdminPolicy`)가 등록된 것을 확인했는데, 이것이 Access Entry의 실체다.

<br>

## Authentication Mode

Access Entry를 사용하려면 클러스터의 Authentication Mode를 설정해야 한다. 세 가지 모드가 있다.

| 모드 | 매핑 소스 | 설명 |
| --- | --- | --- |
| `CONFIG_MAP` | aws-auth ConfigMap만 | EKS 초기 기본값. Access Entry 비활성 |
| `API_AND_CONFIG_MAP` | **Access Entry + aws-auth 모두** | 마이그레이션 과도기용. 중복 시 Access Entry 우선 |
| `API` | **Access Entry만** | ConfigMap 무시. 권장 최종 상태 |

<br>

![EKS 클러스터 Authentication Mode 설정]({{site.url}}/assets/images/eks-w4-cluster-access-setting.png){: .align-center}

<center><sup>EKS 콘솔에서 Authentication Mode 설정</sup></center>

스크린샷에서 **EKS API 및 ConfigMap**(`API_AND_CONFIG_MAP`)이 선택되어 있다. 3단계 전환 경로 중 과도기에 해당하며, `CONFIG_MAP` 옵션은 단방향 전환 특성상 이미 선택지에서 사라져 있다. 여기서 **EKS API**(`API`)로 한 단계 더 전환할 수 있지만, 되돌릴 수 없으므로 모든 매핑이 Access Entry로 재생성된 후 진행해야 한다. 모드 간 전환의 상세한 절차는 [마이그레이션 경로](#마이그레이션-경로)에서 다룬다.

<br>

## Access Entry 구성 요소

Access Entry는 다음 요소로 구성된다.

### Principal ARN

Access Entry에 연결할 IAM principal(User 또는 Role)의 ARN이다. 하나의 IAM principal은 하나의 Access Entry에만 포함될 수 있고, 생성 후 변경할 수 없다.

IAM 모범 사례상 **Role 사용을 권장**한다. Role은 `sts:AssumeRole`로 임시 자격증명(`ASIA...` 토큰)을 발급받으므로 IAM User의 영구 키(`AKIA...`)보다 안전하다.

ConfigMap과 달리, Access Entry에서는 **path가 포함된 ARN도 사용할 수 있다**. 예를 들어 `arn:aws:iam::123456789012:role/my-team/developers/my-role` 형태가 가능하다.

### Type

Access Entry의 유형으로, 연결된 리소스의 성격에 따라 결정된다.

| Type | 용도 |
| --- | --- |
| `STANDARD` | 기본값. 사용자(사람)의 kubectl 접근 등 |
| `EC2_LINUX` | Linux/Bottlerocket 셀프 매니지드 노드의 IAM Role |
| `EC2_WINDOWS` | Windows 셀프 매니지드 노드의 IAM Role |
| `FARGATE_LINUX` | Fargate 프로파일의 IAM Role |
| `HYBRID_LINUX` | 하이브리드 노드의 IAM Role |
| `EC2` | EKS Auto Mode 커스텀 노드 클래스 |

`STANDARD`를 제외한 나머지 type은 모두 **노드 조인**과 관련된다. ConfigMap에서는 `mapRoles`에 노드 Role을 수동으로 추가하고 `system:bootstrappers`/`system:nodes` 그룹을 직접 지정해야 했지만, Access Entry에서는 관리형 노드 그룹이나 Fargate 프로파일을 생성하면 **EKS가 적절한 type의 Access Entry를 자동으로 생성**한다. 수동 매핑이 필요 없으므로, ConfigMap에서 발생하던 노드 매핑 실수로 인한 장애 리스크가 원천적으로 사라진다.

> [1주차 콘솔]({% post_url 2026-03-12-Kubernetes-EKS-01-01-02-Installation-Result %})에서 확인한 3개 entry는: 서비스 역할(EKS 서비스 자체), 노드 역할(관리형 노드 그룹 → EKS가 자동 생성), user/admin(`STANDARD` + `AmazonEKSClusterAdminPolicy`)이었다.

생성 후 type은 변경할 수 없다.

### Username

K8s에서 사용할 username이다. 지정하지 않으면 EKS가 자동 생성한다.

| IAM Principal 유형 | Type | 자동 생성 Username |
| --- | --- | --- |
| IAM User | `STANDARD` | IAM User의 ARN (예: `arn:aws:iam::123456789012:user/my-user`) |
| IAM Role | `STANDARD` | STS assumed-role ARN + `{% raw %}{{SessionName}}{% endraw %}` (예: `arn:aws:sts::123456789012:assumed-role/my-role/{% raw %}{{SessionName}}{% endraw %}`) |
| IAM Role | `EC2_LINUX`/`EC2_WINDOWS` | `system:node:{% raw %}{{EC2PrivateDNSName}}{% endraw %}` |
| IAM Role | `FARGATE_LINUX`/`HYBRID_LINUX` | `system:node:{% raw %}{{SessionName}}{% endraw %}` |

직접 지정하는 경우, `system:`, `eks:`, `aws:`, `amazon:`, `iam:` 접두사로 시작할 수 없다. Role의 경우 `{% raw %}{{SessionName}}{% endraw %}` 템플릿을 사용하면 CloudTrail 로그에서 어떤 세션이 접근했는지 추적할 수 있으므로 권장된다.

### Kubernetes Groups

`STANDARD` type에서만 지정할 수 있다. 여기에 그룹명을 넣으면 ConfigMap의 `groups` 필드와 동일하게 동작한다. K8s RoleBinding/ClusterRoleBinding의 `subjects`에서 `kind: Group`으로 참조되는 값이다.

> EKS는 Access Entry에 지정한 그룹명이 실제로 K8s에 존재하는지 **검증하지 않는다**. 존재하지 않는 그룹명을 지정해도 오류 없이 생성된다.

<br>

## Access Policy

Access Entry에 연결할 수 있는 **AWS 관리형 K8s 권한 정책**이다. K8s의 Role/ClusterRole과 유사하게 `allow` 규칙만 포함하며, 사용자가 커스텀 정책을 직접 만들 수는 없다.

### 주요 정책과 K8s ClusterRole 대응

| Access Policy | K8s 대응 | Scope | 설명 |
| --- | --- | --- | --- |
| `AmazonEKSClusterAdminPolicy` | `cluster-admin` | 클러스터 전체 | 전체 클러스터 관리자 |
| `AmazonEKSAdminPolicy` | `admin` | 네임스페이스 | 네임스페이스 범위 관리자 (Node, PV 등 클러스터 리소스 제외) |
| `AmazonEKSEditPolicy` | `edit` | 네임스페이스 | 리소스 생성/수정 (개발자) |
| `AmazonEKSViewPolicy` | `view` | 네임스페이스 | 읽기 전용 |
| `AmazonEKSAdminViewPolicy` | - | 클러스터 전체 | Secret 포함 읽기 전용 |

> K8s의 user-facing ClusterRole에 대해서는 [Kubernetes 공식 문서](https://kubernetes.io/docs/reference/access-authn-authz/rbac/#user-facing-roles)를 참고한다.

Access Policy를 연결할 때 **scope**을 지정할 수 있다. `Cluster` scope은 클러스터 전체에 적용되고, `Namespace` scope은 특정 네임스페이스에만 적용된다.

사용 가능한 Access Policy 전체 목록은 `aws eks list-access-policies` 명령으로 확인할 수 있다.

### 왜 커스텀 정책을 허용하지 않는가

AWS가 Access Policy의 커스텀 생성을 허용하지 않는 이유는 **일관성 보장**과 **감사(Audit) 용이** 때문이다. AWS 관리형 정책은 내용이 고정되어 있으므로 CloudTrail에서 "이 주체는 `AmazonEKSViewPolicy`가 연결되어 있다"는 것만으로 권한 범위를 특정할 수 있다. 커스텀 정책을 허용하면 이 검증이 어려워진다.

대신 AWS는 **하이브리드 우회 경로**를 제공한다.

<br>

## 하이브리드 패턴: Access Entry + 커스텀 RBAC

AWS 관리형 Access Policy(~6종)로 부족할 때는, Access Entry에 **Access Policy를 붙이지 않고 K8s Group만 매핑**한 뒤, 해당 그룹에 대해 **K8s RBAC(Role/ClusterRole + RoleBinding)을 직접 정의**하는 방식을 사용한다.

```bash
# Access Entry에 Group만 매핑 (Access Policy 없이)
aws eks create-access-entry \
  --cluster-name myeks \
  --principal-arn arn:aws:iam::123456789012:role/CustomDevRole \
  --kubernetes-groups '["custom-dev-group"]'
```

```yaml
# K8s에서 해당 Group에 커스텀 권한 부여
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRoleBinding
metadata:
  name: custom-dev-binding
subjects:
- kind: Group
  name: custom-dev-group
  apiGroup: rbac.authorization.k8s.io
roleRef:
  kind: ClusterRole
  name: my-custom-clusterrole
  apiGroup: rbac.authorization.k8s.io
```

이 방식의 장점은 **인증 매핑은 AWS에서** 하면서(닭과 달걀 문제 없음, IaC 친화), **인가(권한 정의)는 K8s RBAC으로** 세밀하게 정의할 수 있다는 것이다.

<br>

## 인가 체인

Access Entry 방식에서의 인가는 **Node + RBAC + Webhook** 3개 체인이다. ConfigMap 방식의 2개(Node + RBAC)에 비해 **EKS Webhook 인가**가 추가된다. EKS kube-apiserver의 인가 설정은 `--authorization-mode=Node,RBAC,Webhook`이다.

```text
요청 → Node Authorizer → EKS Webhook Authorizer → RBAC Authorizer
        (노드 전용)        (Access Policy 평가)      (K8s RBAC 평가)
```

| 모드 | 역할 |
| --- | --- |
| **Node** | kubelet(노드)이 자기 Pod 정보만 읽을 수 있도록 제한하는 특수 인가. 노드 전용 |
| **RBAC** | K8s 기본 인가. Role/ClusterRole + RoleBinding/CRB로 권한 정의. 사용자가 직접 관리 |
| **Webhook** | 외부 서비스에 인가 판단을 위임. EKS에서는 **Access Policy 기반 인가**를 이 Webhook으로 처리 |

[K8s API Access Control]({% post_url 2026-04-02-Kubernetes-EKS-Auth-00-02-API-Access-Control %})에서 다뤘듯이 Authorization 모듈은 OR 체인이므로, 하나라도 `Allow`하면 인가가 통과한다. 모두 "No Opinion"이면 거부된다.
### 두 흐름이 EKS authorizer에서 만난다

Access Entry 방식의 인가를 이해하는 열쇠는, **관리자의 사전 설정 흐름**과 **사용자의 실시간 요청 흐름**이 EKS authorizer에서 만난다는 것이다.

![EKS Authorization Flow]({{site.url}}/assets/images/eks-w4-authorization-flow.png){: .align-center}

<center><sup>출처: <a href="https://youtu.be/yuXF-NXaelI?si=u6k2q6d764cOhfww&t=466">AWS re:Invent 2023 - A deep dive into simplified Amazon EKS access management controls</a></sup></center>

<br>

그림의 윗줄과 아랫줄이 각각 하나의 흐름이며, ④ EKS authorizer에서 합류한다.

```text
윗줄: 관리자 사전 설정
  ① IAM Role/User ─→ ② Cluster access management API ─→ Access Entry(Username/Groups)
                                                           + Access Policy
                                                                  ↓
                                                          ④ EKS authorizer ──→ Authorized EKS user
                                                                  ↑
아랫줄: 사용자 실시간 요청
  Kubernetes end-user ─→ ③ AWS STS + get-token ─→ kubeconfig ─→ kube-apiserver
```

| 그림 번호 | 하는 일 | 시점 |
| --- | --- | --- |
| **①** | IAM에서 Role/User 생성 | 사전 세팅 (관리자) |
| **②** | Cluster access management API로 **Access Entry + Access Policy 등록** | 사전 세팅 (관리자) |
| **③** | 사용자가 AWS STS + authenticator로 **K8s용 토큰 발급** | 요청 시 (사용자) |
| **④** | **EKS authorizer**가 두 흐름을 합쳐 인가 판단 | 요청 시 (시스템) |

**윗줄 — 관리자가 권한을 설정하는 흐름**

1. **① IAM**: Role/User를 생성한다
2. **② Cluster access management API**: `aws eks create-access-entry`로 Access Entry(IAM ARN → K8s Username/Groups 매핑)를 생성하고, Access Policy(권한 템플릿)를 연결한다
3. 이 설정이 EKS 관리형 DB에 저장되어 **④ EKS authorizer**에 반영된다

**아랫줄 — 사용자가 인증하는 흐름**

1. 사용자가 **③ AWS STS**로 임시 토큰을 받고, `aws eks get-token`으로 K8s용 Bearer 토큰을 생성한다
2. kubeconfig에 토큰을 담아 kube-apiserver에 요청을 보낸다
3. 인증이 완료되면 요청이 **④ EKS authorizer**에 도달한다

**④에서의 만남 — EKS authorizer 내부 판단**

두 흐름이 ④에서 합류하면, EKS authorizer는 다음 3단계로 인가를 판단한다.

1. **매핑 조회**: Access Entry DB를 조회하여 해당 IAM ARN에 매핑된 K8s Username과 Groups를 확인한다
2. **정책 평가**: 해당 Access Entry에 연결된 Access Policy의 권한 규칙을 현재 요청(verb + resource + namespace)과 대조한다
3. **판단 응답**: `allowed: true`(허용) 또는 "No Opinion"(판단 보류)을 API 서버에 응답한다

### Webhook 인가의 K8s API 수준 동작

위 3단계는 K8s API 서버 관점에서 보면 **SubjectAccessReview** 요청으로 구현된다. 사용자가 `kubectl delete pod`같은 명령을 실행하면, API 서버가 `SubjectAccessReview` 객체를 생성하여 EKS 인가 Webhook 서비스(AWS 관리 영역)로 보낸다. "사용자 A가 B 네임스페이스의 Pod을 삭제하려고 하는데, 허가할 것인가?"

Webhook의 응답에 따라 분기한다.

- `allowed: true` → **내부 RBAC에 해당 사용자의 RoleBinding이 없더라도** 명령이 즉시 실행된다
- "No Opinion" → API 서버가 다음 단계인 **RBAC Authorizer**로 넘어가서 K8s RoleBinding을 확인한다

이것이 Access Policy 방식과 수동 RBAC 방식의 실질적 차이다.

| 구분 | **수동 RBAC** | **Access Policy (EKS Managed)** |
| --- | --- | --- |
| **권한 정의** | `kind: ClusterRole` 직접 작성 | `AmazonEKS...Policy` 선택 |
| **연결 작업** | `kind: ClusterRoleBinding` 직접 작성/배포 | 없음 (EKS가 내부적으로 처리) |
| **수정/삭제** | `kubectl delete clusterrolebinding ...` | EKS API 호출 (콘솔 또는 CLI) |

> 커스텀 RBAC만 사용하고 싶다면 Access Policy를 붙이지 않으면 된다. Webhook이 항상 "No Opinion"을 반환하므로 API 서버가 다음 단계인 RBAC 엔진으로 넘어가서 사용자가 직접 작성한 RoleBinding을 확인한다. 결과적으로 RBAC만 동작한다.

<br>

## IaC 친화성

Access Entry가 AWS API 리소스이므로 Terraform `aws` provider로 직접 관리할 수 있다.

```hcl
resource "aws_eks_access_entry" "dev" {
  cluster_name  = aws_eks_cluster.main.name
  principal_arn = aws_iam_role.dev.arn
  type          = "STANDARD"
}

resource "aws_eks_access_policy_association" "dev" {
  cluster_name  = aws_eks_cluster.main.name
  principal_arn = aws_iam_role.dev.arn
  policy_arn    = "arn:aws:eks::aws:cluster-access-policy/AmazonEKSEditPolicy"

  access_scope {
    type       = "namespace"
    namespaces = ["dev"]
  }
}
```

ConfigMap 방식은 K8s 오브젝트이므로 Terraform `kubernetes` provider가 별도로 필요하고, 클러스터가 먼저 존재해야 한다(순환 의존성). Access Entry는 AWS provider 하나로 **클러스터 생성과 동시에** 권한까지 선언할 수 있다. [1주차]({% post_url 2026-03-12-Kubernetes-EKS-01-01-01-Installation %})의 `enable_cluster_creator_admin_permissions = true`가 바로 이것이다.

<br>

## AWS 가이드 절차

AWS 공식 문서에서는 Access Entry 방식을 다음 순서로 안내한다.

1. **IAM identity와 Access Policy 결정**: 사용할 IAM Role/User와 필요한 권한 수준(Cluster Admin, Admin, Edit, View 등)을 결정한다. [Access Policy 권한 상세](https://docs.aws.amazon.com/eks/latest/userguide/access-policy-permissions.html)에서 각 정책의 세부 K8s API 권한을 확인할 수 있다
2. **Authentication Mode 변경**: `aws eks update-cluster-config`로 `API_AND_CONFIG_MAP` 또는 `API` 모드로 전환한다. 이미 해당 모드면 생략
3. **Access Entry 생성**: `aws eks create-access-entry`로 IAM principal ARN + type(+ 선택적 username/groups)을 지정한다
4. **Access Policy 연결**: `aws eks associate-access-policy`로 Access Entry에 정책을 연결하고, scope(클러스터 전체 또는 특정 네임스페이스)을 지정한다
5. **인증 확인**: 해당 IAM identity로 `aws eks update-kubeconfig` + `kubectl` 명령으로 클러스터 접근을 확인한다

핵심은 (3)+(4)이며, 필요한 부분을 실습에서 진행한다.

<br>

# 마이그레이션 경로

기존 ConfigMap 기반 클러스터를 Access Entry로 전환하는 경로를 정리한다.

<br>

## 전환 순서

전환은 **단방향**이다. `CONFIG_MAP` → `API_AND_CONFIG_MAP` → `API`로만 진행할 수 있고, `API`에서 다시 `CONFIG_MAP`으로 되돌릴 수 없다.

```text
1. CONFIG_MAP (현재)
   │
   ├─ aws eks update-cluster-config --access-config authenticationMode=API_AND_CONFIG_MAP
   ▼
2. API_AND_CONFIG_MAP (과도기)
   │  - 기존 ConfigMap 매핑 유지
   │  - Access Entry 점진적 추가
   │  - 중복 시 Access Entry 우선
   │
   ├─ 모든 매핑을 Access Entry로 재생성 완료 확인
   ├─ aws eks update-cluster-config --access-config authenticationMode=API
   ▼
3. API (최종)
   - ConfigMap 있어도 무시됨
```

<br>

## 자동 vs 수동

- **클러스터 creator**: Access Entry 활성화 시 creator의 entry **하나만** 자동 생성된다 (내부적으로 `AmazonEKSClusterAdminPolicy` 연결)
- **나머지 ConfigMap 매핑**: `mapRoles`/`mapUsers`에 추가한 다른 Role/User 매핑은 **자동 마이그레이션되지 않는다**. `aws eks create-access-entry`로 수동 재생성 필요

자동 변환이 불가능한 이유는, ConfigMap의 매핑 형식(username/groups)이 Access Policy와 1:1 대응하지 않기 때문이다. 예를 들어 ConfigMap에서 `system:masters` 그룹에 매핑된 Role을 Access Entry로 옮길 때, `AmazonEKSClusterAdminPolicy`를 연결할지 다른 정책을 선택할지는 관리자가 판단해야 한다.

<br>

## 중복 시 주의사항

`API_AND_CONFIG_MAP` 모드에서 동일 IAM principal에 대해 ConfigMap과 Access Entry 양쪽 모두 매핑이 존재하면, **Access Entry가 우선**한다.

주의할 점은 **권한이 예상과 달라질 수 있다**는 것이다. 예를 들어:

| | ConfigMap 매핑 | Access Entry 매핑 | 실제 적용 |
| --- | --- | --- | --- |
| `arn:...:role/dev` | `system:masters` (전체 관리자) | `AmazonEKSViewPolicy` (읽기 전용) | **읽기 전용** (Access Entry 우선) |

마이그레이션 과도기에 의도치 않은 권한 축소/확대가 발생하지 않도록 주의해야 한다.

<br>

# 정리

인증(AuthN)이 완료된 후 인가(AuthZ)까지 이르는 과정에서, IAM identity를 K8s identity로 변환하는 **브릿지 단계**와 두 가지 매핑 방안을 정리했다.

| 구분 | **Access Entry (EKS API)** | **aws-auth ConfigMap** |
| --- | --- | --- |
| **설계 철학** | AWS에서 K8s 권한을 내려다봄 | K8s 안에서 IAM을 바라봄 |
| **데이터** | AWS 관리형 DB | K8s etcd (ConfigMap) |
| **관리** | AWS API/콘솔 | kubectl |
| **인가** | Node + RBAC + Webhook | Node + RBAC |
| **권한 부여** | Access Policy 또는 K8s Group + 커스텀 RBAC | K8s Group + CR/CRB 직접 관리 |
| **IaC** | AWS provider로 클러스터와 동시 선언 | K8s provider 별도 필요 |
| **장애 복구** | AWS API로 독립 복구 | K8s API 접근 필요 |
| **마이그레이션** | `CONFIG_MAP` → `API_AND_CONFIG_MAP` → `API` (단방향) | - |

다음 글에서는 이 개념들을 실습으로 확인한다. Access Entry 생성, ConfigMap 확인, 권한 테스트 등을 직접 수행할 예정이다.

<br>

# 참고 자료

- [aws-iam-authenticator GitHub](https://github.com/kubernetes-sigs/aws-iam-authenticator): Full Configuration Format (ConfigMap 전체 설정 포맷)
- [AWS EKS 공식 문서 - Grant IAM users and roles access to Kubernetes APIs](https://docs.aws.amazon.com/eks/latest/userguide/grant-k8s-access.html)
- [AWS EKS 공식 문서 - Access policy permissions](https://docs.aws.amazon.com/eks/latest/userguide/access-policy-permissions.html): Access Policy별 K8s API 권한 상세
- [AWS EKS 공식 문서 - Setting up access entries](https://docs.aws.amazon.com/eks/latest/userguide/setting-up-access-entries.html): Authentication Mode 변경 절차
- [AWS EKS 공식 문서 - Creating access entries](https://docs.aws.amazon.com/eks/latest/userguide/creating-access-entries.html): Access Entry CRUD
- [Kubernetes RBAC - User-facing roles](https://kubernetes.io/docs/reference/access-authn-authz/rbac/#user-facing-roles): Access Policy와 대응하는 K8s ClusterRole
- [AWS EKS Best Practices - Identity and Access Management](https://docs.aws.amazon.com/eks/latest/best-practices/identity-and-access-management.html)

<br>
