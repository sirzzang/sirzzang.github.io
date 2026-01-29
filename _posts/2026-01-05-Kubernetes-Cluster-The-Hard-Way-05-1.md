---
title:  "[Kubernetes] Cluster: 내 손으로 클러스터 구성하기 - 5.1. Generating Kubernetes Configuration Files"
excerpt: "kubeconfig의 개념과 구성 요소, Node Authorizer의 동작 원리를 이해해보자."
categories:
  - Kubernetes
toc: true
header:
  teaser: /assets/images/blog-Dev.jpg
tags:
  - Kubernetes
  - On-Premise-K8s-Hands-On-Study
  - On-Premise-K8s-Hands-On-Study-Week-1
hidden: true

---

<br>

*[서종호(가시다)](https://www.linkedin.com/in/gasida99/)님의 On-Premise K8s Hands-on Study 1주차 학습 내용을 기반으로 합니다.*

<br>

# TL;DR

이번 글의 목표는 **kubeconfig와 Node Authorizer 개념 이해**다. [Kubernetes the Hard Way 튜토리얼의 Generating Kubernetes Configuration Files for Authentication 단계](https://github.com/kelseyhightower/kubernetes-the-hard-way/blob/master/docs/05-kubernetes-configuration-files.md)를 수행하기 전에, kubeconfig의 구성 요소와 Node Authorizer의 동작 원리를 먼저 정리한다.

- kubeconfig: 클러스터 접근 설정 파일. clusters, users, contexts로 구성
- Node Authorizer: kubelet의 API 요청에 대해 특별한 권한 부여를 수행하는 인가 모드
- kubelet 인증서 명명 규칙: `CN=system:node:<nodeName>`, `O=system:nodes` 형식을 따라야 Node Authorizer가 자동 인식

직전 단계에서 TLS 인증서를 생성했다면, 이번 단계에서는 해당 인증서를 사용해 각 컴포넌트가 API Server와 통신할 수 있도록 설정 파일(kubeconfig)을 구성한다. 
<br>

# kubeconfig

## 개념

[kubeconfig](https://kubernetes.io/docs/concepts/configuration/organize-cluster-access-kubeconfig/)는 클러스터 접근 설정 정보를 담은 파일이다. 클러스터, 사용자, 네임스페이스, 인증 메커니즘 정보를 정의하며, kubectl 등 Kubernetes 클라이언트는 이 파일을 통해 어떤 클러스터의 API Server와 통신할지 결정한다.

여기서 말하는 클라이언트란 API Server와 통신하는 모든 주체를 의미한다. kubectl을 사용하는 사용자뿐 아니라, kubelet, kube-proxy, kube-scheduler, kube-controller-manager 같은 클러스터 컴포넌트도 API Server의 클라이언트다. 이번 실습에서 각 컴포넌트별 kubeconfig를 생성하는 이유가 바로 이것이다.


> *참고*: kubeconfig 파일이란
> "kubeconfig"라는 이름의 파일이 존재하는 것이 아니라, 클러스터 접근 설정 파일을 총칭하는 용어다. 실제로는 `config`, `admin.kubeconfig` 등 다양한 이름으로 존재할 수 있다.


## 구성 요소

kubeconfig 파일은 크게 세 가지 핵심 요소로 구성된다.

1. `clusters`: 접속할 클러스터 정보. API Server 주소와 CA 인증서 포함
2. `users`: 인증 정보. 클라이언트 인증서, 키, 토큰 등 포함
3. `contexts`: cluster와 user를 조합한 접근 설정. namespace 지정도 가능

```yaml
apiVersion: v1
kind: Config
clusters: # 1
- name: kubernetes-the-hard-way
  cluster:
    certificate-authority-data: <CA_CERT_BASE64>
    server: https://server:6443

users: # 2
- name: admin
  user:
    client-certificate-data: <CLIENT_CERT_BASE64>
    client-key-data: <CLIENT_KEY_BASE64>

contexts: # 3
- name: default
  context:
    cluster: kubernetes-the-hard-way
    user: admin

current-context: default 
```

### context

context는 "어떤 클러스터에 어떤 사용자로 접속할 것인가"를 정의하는 조합이다. 여러 클러스터를 다루는 환경에서는 context를 전환하여 손쉽게 접속 대상을 변경할 수 있다.

`current-context`는 현재 사용 중인 context를 지정한다. kubectl은 기본적으로 current-context에 지정된 설정을 사용해 클러스터와 통신한다.


## 설정 파일 위치 및 우선순위

kubectl이 kubeconfig를 찾는 우선순위는 다음과 같다.

1. `--kubeconfig` 플래그로 명시적 지정
2. `KUBECONFIG` 환경 변수에 지정된 파일
3. 기본 경로: `$HOME/.kube/config`

`--kubeconfig` 플래그가 가장 높은 우선순위를 가지며, 지정 시 해당 파일만 사용한다. 환경 변수에 여러 파일이 지정된 경우 kubectl은 이를 병합하여 사용한다.

<br>

# Node Authorizer

## 인증과 인가

직전 단계에서 생성한 TLS 인증서는 **인증(Authentication)**을 위한 것이다. "이 요청이 정말 kubelet에서 온 것인가?"를 검증한다. 반면 **인가(Authorization)**는 "인증된 주체가 요청한 작업을 수행할 권한이 있는가?"를 결정한다.

Kubernetes에서 API Server로 들어오는 모든 요청은 인증 → 인가 → Admission Control 순서로 처리된다.


## 개념

[Node Authorizer](https://kubernetes.io/docs/reference/access-authn-authz/node/)는 kubelet의 API 요청에 대해 특별한 권한 부여를 수행하는 인가 모드다. 

kubelet은 자신이 실행 중인 노드의 Pod를 관리하기 위해 API Server와 통신해야 한다. 그러나 보안 관점에서, 특정 노드의 kubelet이 다른 노드의 리소스에 접근하는 것은 바람직하지 않다. Node Authorizer는 이러한 제한을 적용한다.

Node Authorizer가 kubelet에게 허용하는 주요 작업은 다음과 같다.

- **읽기**: 자신의 노드에 바인딩된 Pod, 해당 Pod가 참조하는 Secret/ConfigMap/PV/PVC
- **쓰기**: 자신의 노드 및 노드 상태, 자신의 노드에 바인딩된 Pod 상태, 이벤트
- **인증 관련**: 인증서 서명 요청(CSR) 생성 등

핵심은 kubelet이 **자신의 노드에 바인딩된 리소스에만** 접근할 수 있다는 점이다.


## Kubelet 인증서와 Node Authorizer

Node Authorizer가 kubelet을 식별하려면, kubelet이 제시하는 인증서가 **Node Authorizer가 인식하는 명명 규칙**을 따라야 한다.
- **그룹(Organization)**: `system:nodes`
- **사용자 이름(Common Name)**: `system:node:<nodeName>`

명명 규칙이 시사하는 것은, `system:node:<nodeName>`이 **Kubernetes에 미리 정의된 사용자가 아니라는 것**이다. 이것은 Node Authorizer가 **인식하는 명명 규칙(naming convention)**을 따른 것일 뿐이다.

## 동작 원리

Node Authorizer가 kubelet을 인가하는 방식은 다음과 같다.

1. kubelet이 인증서를 제시하면서 API Server에 요청
2. API Server가 인증서 검증 (CA로 서명 확인)
3. 인증서의 CN과 O 확인:
   - CN이 `system:node:node-0` 형식이고
   - O가 `system:nodes`이면
4. Node Authorizer가 "이것은 node-0의 kubelet이다"라고 **자동으로 인식**
5. 해당 kubelet에게 **규칙 기반으로 권한 부여**
   - node-0에 바인딩된 Pod만 접근 가능
   - 다른 노드의 리소스는 접근 불가

## 사용 이유

RBAC처럼 별도로 권한을 설정할 필요 없이, 명명 규칙만 따르면 Node Authorizer가 자동으로 적절한 권한을 부여한다.

```yaml
CN = system:node:node-0  # ← Node Authorizer가 이 패턴을 감지
O = system:nodes         # ← 이 그룹을 확인
```

결과적으로, Node Authorizer를 사용하는 이유는 **운영 편의성과 보안**이다. 명명 규칙만 따르면 별도 설정 없이 노드별로 적절한 권한이 자동으로 부여된다. 


### 만약 Node Authorizer가 없다면?

보통 kube-apiserver를 실행할 때, `--authorization-mode=Node,RBAC,...` 등의 옵션으로, Node Authorizer를 활성화한다.

Node Authorizer 없이 kube-apiserver를 실행하는 경우는 어떨까?

```bash
# 일반적인 설정
--authorization-mode=Node,RBAC

# Node Authorizer 없이 실행
--authorization-mode=RBAC
```

kubelet 인증은 성공하지만, 인가 단계에서 문제가 발생할 수 있다.
1. **인증 단계**: kubelet은 TLS 인증서가 유효하므로 인증에 성공함
2. **인가 단계**: Node Authorizer가 없으므로 자동 권한 부여가 되지 않아 기본적으로 거부됨

따라서 이런 경우에는 RBAC으로 각 kubelet에 대해 수동으로 RBAC 리소스를 생성해야 한다. 그런데, 명명 규칙만 지켜 주면 됐던 Node Authorizer 방식에 비해, 많이 번거롭다. 모든 노드 kubelet마다 전부 리소스를 생성해 줘야 할테니.

| 구분 | Node Authorizer 사용 | RBAC만 사용 |
|------|---------------------|------------|
| 설정 | 명명 규칙만 따르면 자동 권한 부여 | 각 kubelet마다 RBAC 리소스 수동 생성 필요 |
| 보안 | 자동으로 "자기 노드만" 접근 제한 | 수동 설정 필요 (실수 가능) |
| 관리 | 노드 추가 시 자동 인식 | 노드 추가 시 RBAC 설정 추가 필요 |
| 스케일링 | 노드 수에 관계없이 동일한 관리 비용 | 노드 수에 비례해 관리 비용 증가 |

<br>

<br>


## 인증서와 kubeconfig의 연관성

[직전 단계]({% post_url 2026-01-05-Kubernetes-Cluster-The-Hard-Way-04-3 %})에서 kubelet 인증서를 생성할 때 이 명명 규칙을 따랐다.

```bash
# node-0 인증서 생성 시
CN = system:node:node-0  # 인증서의 Common Name
O = system:nodes         # 인증서의 Organization
```

이후 실습에서 생성하는 kubeconfig도 이 인증서를 사용한다. `set-credentials` 단계에서 `system:node:node-0`이라는 이름으로 사용자를 설정할 것이다. 따라서,
- 새로운 사용자를 만들지 않고
- 인증서에 담긴 CN/O 정보를 사용자 정보로 kubeconfig에 기록하는 것이기 때문에
- kubelet이 API Server에 요청할 때 이 인증서를 제시하면 Node Authorizer가 자동으로 권한을 부여한다.

<br>

# 결과

이 단계를 완료하면 다음과 같은 개념을 이해할 수 있다:

| 개념 | 설명 |
|------|------|
| **kubeconfig** | 클러스터 접근 설정 파일. clusters, users, contexts로 구성 |
| **clusters** | 접속할 클러스터 정보. API Server 주소와 CA 인증서 포함 |
| **users** | 인증 정보. 클라이언트 인증서, 키, 토큰 등 포함 |
| **contexts** | cluster와 user를 조합한 접근 설정 |
| **Node Authorizer** | kubelet의 API 요청에 대해 특별한 권한 부여를 수행하는 인가 모드 |
| **명명 규칙** | `CN=system:node:<nodeName>`, `O=system:nodes` 형식을 따라야 Node Authorizer가 자동 인식 |

<br>

Kubernetes는 kubeconfig를 통해 각 컴포넌트가 API Server와 통신할 수 있도록 설정한다. Node Authorizer는 kubelet 인증서의 명명 규칙을 기반으로 자동으로 적절한 권한을 부여하여, 별도의 RBAC 설정 없이도 노드별 리소스 접근을 제한할 수 있다. 


<br> 

다음 단계에서는 지난 단계에서 생성한 인증서를 이용해 kubeconfig 파일을 생성하고 배포한다.

