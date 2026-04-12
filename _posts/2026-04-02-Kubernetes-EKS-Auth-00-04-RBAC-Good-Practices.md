---
title: "[[EKS] EKS: 인증/인가 - 1. K8S 인증/인가 기초 - 3. RBAC 모범 사례"
excerpt: "K8S RBAC에서 의도치 않은 권한 상승이 발생할 수 있는 경로를 정리하고, 안전한 설계 원칙을 살펴보자."
categories:
  - Kubernetes
toc: true
header:
  teaser: /assets/images/blog-Dev.jpg
tags:
  - Kubernetes
  - RBAC
  - Security
  - Privilege-Escalation
  - AWS-EKS-Workshop-Study
  - AWS-EKS-Workshop-Study-Week-4
---

*[서종호(가시다)](https://www.linkedin.com/in/gasida99/)님의 AWS EKS Workshop Study(AEWS) 4주차 학습 내용을 기반으로 합니다.*

<br>

# TL;DR

- K8S RBAC은 클러스터 사용자와 워크로드가 **역할 수행에 필요한 리소스에만 접근**하도록 보장하는 핵심 보안 통제다
- RBAC 권한 설계 시, 의도치 않게 **권한 상승(privilege escalation)**이 가능한 11가지 경로가 있다
- `escalate`, `bind`, `impersonate` verb는 위험하지만, **"RBAC을 관리하기 위한 RBAC"**에 필요하다. 없으면 `cluster-admin`을 남발해야 하는 모순이 생긴다
- RBAC으로 "무엇을 할 수 있는가"를 통제할 때 "**얼마나 많이** 할 수 있는가"도 함께 고려해야 한다

<br>

# RBAC 설계, 왜 신경 써야 하는가

[개요 포스트]({% post_url 2026-04-02-Kubernetes-EKS-Auth-00-00-Overview %})에서 EKS 인증/인가의 핵심 문제 중 하나가 **"두 권한 체계(IAM + RBAC)를 동시에 관리해야 한다"**는 것이라고 정리했다. IAM 측은 AWS가 잘 문서화해두었지만, RBAC 측은 "권한을 설계할 때 어디서 구멍이 생길 수 있는지"를 알아야 안전하다.

특히 EKS에서는 Access Entry로 IAM identity를 K8s username/group에 매핑한 후, **실제 "무엇을 할 수 있는가"는 RBAC이 결정**한다. RBAC 설계가 허술하면 IAM에서 아무리 잘 통제해도 K8s 안에서 권한 상승이 발생할 수 있다.

![Role, RoleBinding, Subject 관계]({{site.url}}/assets/images/kubernetes-role-rolebinding-subject.png){: .align-center}

<br>

# RBAC 설계 원칙

## 최소 권한 원칙

- **namespace 수준에서 권한 부여**: ClusterRoleBinding 대신 RoleBinding을 사용하여 특정 namespace 내에서만 권한을 부여한다
- **wildcard 권한 회피**: K8s는 확장 가능한 시스템이라 wildcard 접근을 주면 현재뿐 아니라 **미래에 만들어질 오브젝트 타입에 대해서도** 권한이 부여된다
- **`cluster-admin` 자제**: 꼭 필요한 경우가 아니면 쓰지 않는다. 낮은 권한 계정에 impersonation 권한을 부여하면, 평소에는 최소 권한으로 운영하다가 필요할 때만 높은 권한으로 전환할 수 있다. Linux의 `sudo`와 같은 패턴이다
- **`system:masters` 그룹 금지**: 이 그룹 멤버는 **모든 RBAC 검사를 우회**하며, RoleBinding/ClusterRoleBinding을 제거해도 접근을 취소할 수 없다. authorization webhook도 우회한다

> EKS에서 Access Entry로 IAM Role을 `system:masters` 그룹에 매핑하면 K8s에서 슈퍼유저가 된다. 편리하지만 위험하다. 필요한 최소 권한만 매핑하는 것이 원칙이다.

## Privileged Token 배포 최소화

Pod에 강력한 권한이 부여된 SA를 가급적 할당하지 않아야 한다. 강력한 권한이 필요한 워크로드가 있다면:

- 강력한 권한 Pod을 실행하는 **노드 수를 제한**한다
- 강력한 권한 Pod과 신뢰할 수 없는 Pod을 **같은 노드에서 실행하지 않는다**. Taint/Toleration, NodeAffinity, PodAntiAffinity를 활용한다

왜 스케줄링까지 신경 써야 하는가? 핵심은 **컨테이너 탈출(container escape)** 시나리오다. 강력한 권한을 가진 Pod에서 컨테이너 탈출이 발생하면 같은 노드의 다른 Pod에 접근할 수 있다. 스케줄링 분리는 Pod 간 API 통신을 막는 게 아니라 **노드 레벨의 blast radius(피해 범위)**를 제한하는 것이다.

## Hardening

K8s 기본 설정은 모든 클러스터에서 필요하지 않을 수 있는 접근을 제공한다. 다음을 확인하자.

- **`system:unauthenticated` 그룹 바인딩**: 가능하면 제거. 네트워크 수준에서 API 서버에 접촉할 수 있는 누구에게나 접근을 제공한다
- **SA 토큰 자동 마운트**: `automountServiceAccountToken: false`를 기본으로 설정하여, API 서버에 접근할 필요 없는 Pod에 불필요한 credential이 노출되는 것을 막는다

## 주기적 점검

RBAC 설정을 주기적으로 검토해야 한다. 특히 조심할 것: 공격자가 삭제된 사용자와 **같은 이름의 계정을 만들면**, 해당 사용자에게 할당된 모든 권한을 자동 상속받을 수 있다.

## 양적 통제: DoS 방지

RBAC은 "무엇을 할 수 있는가"를 통제하지만, **"얼마나 많이 할 수 있는가"**는 통제하지 못한다. 오브젝트 생성 권한이 있는 사용자가 크기나 수가 충분히 큰 오브젝트를 대량 생성하면, **etcd가 OOM**에 빠질 수 있다. 멀티테넌트 클러스터에서 한 사용자가 etcd 용량을 소진하면 전체 클러스터가 영향을 받는다.

완화 방법: [ResourceQuota](https://kubernetes.io/docs/concepts/policy/resource-quotas/#object-count-quota)로 namespace별 오브젝트 수를 제한한다.

> EKS에서도 멀티팀 환경이라면 namespace별 ResourceQuota 설정이 필수적이다. IAM으로 "누가 클러스터에 접근할 수 있는가"를 통제하고, RBAC으로 "무엇을 할 수 있는가"를 통제하고, ResourceQuota로 "얼마나 할 수 있는가"를 통제하는 삼중 구조다.

<br>

# 의도치 않은 권한 상승 11가지 경로

RBAC에는 부여 시 사용자나 SA의 권한을 상승시키거나 클러스터 외부 시스템에 영향을 줄 수 있는 권한들이 있다. 하나씩 살펴보자.

## 1. Listing Secrets

Secret에 대한 `get` 접근을 허용하면 내용을 읽을 수 있다. 중요한 건 `list`와 `watch`도 사실상 Secret 내용 노출이 가능하다는 점이다. `kubectl get secrets -A -o yaml`의 List 응답에는 **모든 Secret 내용이 포함**된다.

## 2. Workload Creation

namespace에서 워크로드를 생성할 수 있는 권한은, 해당 namespace의 다른 리소스에 대한 **간접 접근**을 부여한다. 이게 어떻게 가능한가?

- Pod spec의 `volumes`에서 **Secret, ConfigMap, PV를 마운트** → 내용 읽기 가능
- `spec.serviceAccountName`에 **아무 SA나 지정** → 해당 SA의 RBAC 권한 획득
- `env.valueFrom.secretKeyRef`로 Secret 값을 환경변수로 주입

즉 **Pod 생성 권한 = 그 namespace의 Secret/ConfigMap/SA에 대한 간접 읽기 권한**이다.

`privileged: true` securityContext가 설정된 Pod을 실행할 수 있으면 상황은 더 심각하다. 호스트 파일시스템 접근, 호스트 네트워크 접근, 커널 모듈 로드 등이 가능해진다. **Baseline** 또는 **Restricted** Pod Security Standard를 적용하는 것이 좋다.

> namespace 내부의 경계는 약하다고 인식해야 한다. namespace는 서로 다른 수준의 신뢰가 필요한 리소스를 분리하는 데 사용하고, 같은 namespace 안에서의 격리는 기대하지 않는 것이 안전하다.

## 3. PV Creation

임의의 PersistentVolume을 생성할 수 있으면 `hostPath` 볼륨을 만들 수 있고, 이는 해당 노드의 **호스트 파일시스템에 대한 접근**을 의미한다. [hostPath 위험성]({% post_url 2026-04-05-Kubernetes-Pod-Volume-03-Image-Volume-HostPath %})에서 살펴본 것처럼, 호스트 파일시스템에 접근할 수 있으면 권한 상승 방법이 다양하다.

- `/var/lib/kubelet/` → kubelet credential, SA 토큰
- `/etc/kubernetes/` → API 서버 인증서, encryption config
- `/var/run/docker.sock` → 다른 컨테이너 제어

**관심사 분리** 원칙에 따라, 클러스터 관리자나 CSI driver가 PV를 생성하고, 일반 사용자는 PVC로 스토리지를 요청만 하는 것이 안전하다.

## 4. Access to `nodes/proxy`

`nodes/proxy` 서브리소스 접근 권한이 있으면 kubelet API를 통해 해당 노드의 **모든 Pod에서 명령을 실행**할 수 있다. **audit logging과 admission control을 우회**한다는 점이 특히 위험하다.

> `nodes/proxy`는 `kubectl proxy`와 다른 개념이다. `kubectl proxy`는 로컬 → API 서버 프록시 터널이고, `nodes/proxy`는 API 서버를 통해 **kubelet API에 직접 접근**하는 K8s API 경로(`/api/v1/nodes/{node}/proxy/...`)다.

websocket HTTP `GET` 요청으로도 실행 가능하므로, `get` 권한이 읽기 전용 권한이 아니다.

## 5. Escalate Verb

K8s RBAC은 기본적으로 사용자가 **자신이 가진 것보다 더 많은 권한의 Role을 생성하지 못하도록** 방지한다. 내가 `pods/get`만 가지고 있으면 내가 만드는 Role에도 `pods/get`까지만 넣을 수 있다. `secrets/get`을 넣으려 하면 API 서버가 거부한다.

`escalate` verb는 이 보호를 우회한다.

```yaml
rules:
- apiGroups: ["rbac.authorization.k8s.io"]
  resources: ["clusterroles"]
  verbs: ["escalate"]
```

## 6. Bind Verb

`escalate`와 유사하게, 자신에게 없는 권한을 가진 Role에 대한 **RoleBinding을 생성**할 수 있게 한다.

## 7. Impersonate Verb

`users`, `groups`, `serviceaccounts` 리소스에 대한 `impersonate` verb를 가진 사용자는 **다른 사용자/그룹으로 위장**하여 API 요청을 보낼 수 있다.

## escalate, bind, impersonate는 왜 필요한가

5~7번(`escalate`, `bind`, `impersonate`)은 왜 위험한 걸 알면서 만들었을까? 핵심은 **"클러스터 관리 자동화"**를 가능하게 하기 위해서다.

### escalate: RBAC 자체를 관리하는 자동화

`escalate`가 없으면 GitOps로 RBAC을 관리하는 controller(ArgoCD 등)가 Role을 배포하려 할 때 배포할 **모든 Role의 모든 권한의 합집합**을 가져야 한다. 사실상 `cluster-admin`을 줘야 한다는 뜻이다.

`escalate`가 있으면 RBAC 관리 전용 SA에 `clusterroles`에 대한 `create`, `update`, `escalate`만 주면 된다. 이 SA는 RBAC 오브젝트를 만드는 권한만 있고, `pods/get`이나 `secrets/get` 같은 **실제 데이터 접근 권한은 없다**.

핵심 원칙: **"권한을 정의하는 능력" =/= "권한을 행사하는 능력"**

### bind: RoleBinding을 관리하는 자동화

온보딩 자동화 시스템이 신규 사용자에게 `developer` Role을 바인딩하려 할 때, `bind`가 없으면 시스템 자체가 `developer` Role의 모든 권한을 가져야 한다. `bind`가 있으면 특정 Role에 대한 바인딩 권한만 부여하면 된다.

```yaml
rules:
- apiGroups: ["rbac.authorization.k8s.io"]
  resources: ["rolebindings"]
  verbs: ["create"]
- apiGroups: ["rbac.authorization.k8s.io"]
  resources: ["clusterroles"]
  resourceNames: ["developer"]
  verbs: ["bind"]
```

이 SA는 developer Role을 바인딩할 수 있지만, developer Role의 실제 권한(`pods/get` 등)은 없다.

### impersonate: 감사 가능한 권한 전환

`impersonate`가 없으면 관리자가 항상 `cluster-admin`으로 작업해야 한다. `impersonate`가 있으면:

- **sudo 패턴**: 평소에는 낮은 권한, 필요할 때만 `kubectl --as=cluster-admin ...`
- **디버깅**: `kubectl --as=jane@example.com get pods`로 Jane의 시점에서 권한 테스트
- **멀티테넌트 자동화**: 하나의 controller가 `--as=team-a-sa`, `--as=team-b-sa`로 팀별 작업
- 모든 impersonation은 **audit log에 기록** → 추적 가능

### 공통 설계 원칙

|  | 없을 때 | 있을 때 |
| --- | --- | --- |
| **관리 방식** | 모든 관리자에게 `cluster-admin` 필수 | 세분화된 관리 권한 가능 |
| **자동화** | controller에 전체 권한 부여 필요 | 최소한의 메타 권한만 부여 |
| **위험도** | 역설적으로 더 위험 (과도한 권한 남발) | 위험하지만 **제어 가능** |

이 verb들이 없으면 **"RBAC을 관리하기 위해 RBAC을 우회해야 하는"** 모순이 생긴다. `cluster-admin`을 남발하는 것보다, `escalate`/`bind`/`impersonate`를 **극소수의 관리 주체에게만** 부여하는 것이 더 안전하다. Linux에서 root를 직접 쓰는 것보다 `sudo`를 쓰는 것이 더 안전한 것과 같은 논리다.

## 8. CSR / Certificate Issuing

CSR `create` + `certificatesigningrequests/approval` `update` 권한이 있으면 K8s 시스템 컴포넌트와 동일한 이름의 **임의 클라이언트 인증서**를 발급할 수 있다.

## 9. Token Request

`serviceaccounts/token`에 대한 `create` 권한이 있으면, 해당 namespace의 **아무 SA에 대해서나** TokenRequest를 호출할 수 있다. 해당 SA에 `cluster-admin` 수준의 RoleBinding이 있으면 권한 상승이다.

## 10. Admission Webhook Control

`validatingwebhookconfigurations`나 `mutatingwebhookconfigurations`를 제어할 수 있으면, 클러스터에 admit되는 **모든 오브젝트를 읽거나 수정**할 수 있다.

## 11. Namespace Modification

Namespace 오브젝트에 대한 `patch` 권한이 있으면 **라벨을 변경**하여 Pod Security Admission 정책을 우회하거나, NetworkPolicy를 우회하여 의도하지 않은 서비스에 접근할 수 있다.

<br>

# 정리

## Privilege Escalation 경로 요약

| # | 경로 | 위험 |
| --- | --- | --- |
| 1 | **Listing Secrets** | `get`/`list`/`watch`로 Secret 내용 노출 |
| 2 | **Workload creation** | Pod에서 Secret/ConfigMap/SA를 간접 참조 |
| 3 | **PV creation** | `hostPath`로 호스트 파일시스템 접근 |
| 4 | **nodes/proxy** | kubelet API로 모든 Pod에 명령 실행, audit 우회 |
| 5 | **escalate** | 자신보다 높은 권한의 Role 생성 |
| 6 | **bind** | 자신에게 없는 권한의 RoleBinding 생성 |
| 7 | **impersonate** | 다른 사용자로 위장 |
| 8 | **CSR/certificate** | 임의 클라이언트 인증서 발급 |
| 9 | **Token request** | 다른 SA의 토큰 발급 |
| 10 | **Admission webhook** | 모든 오브젝트 읽기/수정 |
| 11 | **Namespace modification** | 라벨 변경으로 PodSecurity/NetworkPolicy 우회 |

## 핵심 원칙

- **최소 권한**: namespace 수준, wildcard 회피, `cluster-admin` 자제
- **관심사 분리**: "권한을 정의하는 능력"과 "권한을 행사하는 능력"은 다르다. `escalate`/`bind`/`impersonate`는 이 원칙 덕분에 존재한다 — 없으면 `cluster-admin`을 남발해야 하는 모순이 생긴다
- **보수적 접근**: `escalate`/`bind`/`impersonate`는 극소수의 관리 주체에게만
- **양적 통제**: RBAC과 함께 ResourceQuota로 DoS 방지

EKS 맥락에서 정리하면: **IAM**으로 "누가 클러스터에 접근하는가"를 통제하고, **RBAC**으로 "K8s 안에서 무엇을 할 수 있는가"를 통제한다. 이 두 레이어 중 어느 쪽이라도 허술하면 보안 구멍이 생긴다. IAM 쪽은 AWS가 관리해주지만 RBAC 쪽은 클러스터 운영자의 몫이다.

<br>

# 참고 링크

- [RBAC Good Practices](https://kubernetes.io/docs/concepts/security/rbac-good-practices/)
- [Using RBAC Authorization](https://kubernetes.io/docs/reference/access-authn-authz/rbac/)
