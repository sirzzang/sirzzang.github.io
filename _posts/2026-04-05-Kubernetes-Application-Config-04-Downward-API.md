---
title:  "[Kubernetes] 어플리케이션 설정 - 4. Downward API"
excerpt: "Downward API를 이용해 파드 메타데이터와 컨테이너 리소스 정보를 어플리케이션에 전달하는 방법을 알아보자."
categories:
  - Kubernetes
toc: true
header:
  teaser: /assets/images/blog-Dev.jpg
tags:
  - Kubernetes
  - Kubernetes-in-Action-2nd
  - Downward-API
  - fieldRef
  - resourceFieldRef
  - metadata
hidden: true
---

*[Kubernetes in Action 2nd Edition](https://www.manning.com/books/kubernetes-in-action-second-edition) 8장의 학습 내용을 기반으로 합니다.*

<br>

# TL;DR

- Downward API는 파드의 메타데이터(`metadata`, `spec`, `status` 필드)를 환경 변수 또는 볼륨 파일로 컨테이너에 전달하는 메커니즘이다
- REST 엔드포인트가 아니라, Kubernetes API 서버의 Pod object 정보를 컨테이너 "아래로(down)" 내려주는 방식이다
- `fieldRef`로 파드의 일반 메타데이터(이름, IP, 노드 등)를, `resourceFieldRef`로 컨테이너의 리소스 제약(CPU/메모리)을 참조한다
- 어플리케이션이 Kubernetes API에 종속되지 않고도 파드 메타데이터를 활용할 수 있게 해준다

<br>

# Downward API 소개

지금까지 어플리케이션에 설정 데이터를 전달하는 방법을 알아봤지만, 그 데이터는 항상 정적이었다. 값은 파드를 배포하기 전에 이미 알려져 있었고, 동일한 파드를 여러 개 배포해도 모두 같은 값을 사용했다.

하지만 아래와 같은 경우는 문제가 된다.

- **파드가 생성되고 클러스터 노드에 스케줄링될 때까지 알 수 없는 데이터**(파드의 IP, 클러스터 노드의 이름, 파드 자체의 이름 등)는 어떻게 전달하는가?
- **파드 매니페스트의 다른 곳에 이미 지정된 데이터**(컨테이너에 할당된 CPU와 메모리 양 등)를 중복해서 정의하는 것이 바람직한가?

이런 경우를 Downward API를 이용해 해결할 수 있다.

## Downward API란

Downward API는 파드와 컨테이너의 메타데이터를 환경 변수 또는 파일을 통해 컨테이너에 주입할 수 있게 해주는 메커니즘이다. Kubernetes REST API를 직접 호출하지 않고도 Pod의 메타데이터에 접근할 수 있다. ([Kubernetes 공식 문서: Downward API](https://kubernetes.io/docs/concepts/workloads/pods/downward-api/)) 파드 매니페스트에 설정할 수 있는 다양한 구성 옵션이 있고, 동일한 정보를 어플리케이션에 전달해야 하는 경우도 있는데, 이때 환경 변수에 값을 반복하는 대신 Downward API를 사용하는 것이 더 좋은 방법이다.

## "Downward"의 의미

Downward API는 어플리케이션이 호출해야 하는 REST 엔드포인트가 아니다. 파드 매니페스트의 `metadata`, `spec`, `status` 필드의 값을 컨테이너 **아래로(down)** 내려주는 방식이다.

![Downward API가 Pod object의 메타데이터를 환경 변수와 볼륨 파일로 컨테이너에 전달하는 구조]({{site.url}}/assets/images/k8s-in-action-book-figure-downward-api.png){: .align-center}
*출처: Kubernetes in Action 2nd Edition*

Kubernetes 아키텍처 관점에서 **위(up)**는 Kubernetes API 서버(컨트롤 플레인)이고, **아래(down)**는 컨테이너(워크로드)다.

- **Upward**: 컨테이너 안의 어플리케이션이 Kubernetes API 서버에 위로 올라가서 정보를 직접 질의하는 방향이다. 예를 들어, 파드 안에서 `curl https://kubernetes.default.svc/api/v1/pods`로 API 서버를 호출하는 것이 이에 해당한다
- **Downward**: API 서버가 관리하는 Pod object의 메타데이터를 컨테이너 아래로 내려보내주는 방향이다. 환경 변수나 파일로 투영된다

파드 이름, IP 같은 기본 정보를 얻기 위해 매번 API 서버를 호출(upward)하는 건 과하고, 어플리케이션이 Kubernetes에 종속되게 만든다. Downward API는 이런 간단한 메타데이터를 환경 변수나 파일로 내려줘서 어플리케이션이 Kubernetes API를 전혀 모르고도 사용할 수 있게 해준다.

## 데이터 소스와 전달 방식

ConfigMap의 값을 가져올 때 `configMapKeyRef`, Secret의 값을 가져올 때 `secretKeyRef`를 사용했다. Downward API를 통해 값을 가져오려면, 주입하려는 정보에 따라 다음 두 가지를 사용한다.

- `fieldRef` → 파드의 일반 메타데이터 참조 (`metadata.name`, `spec.nodeName`, `status.podIP` 등)
- `resourceFieldRef` → 컨테이너의 컴퓨트 리소스 제약 참조 (`requests.cpu`, `limits.memory` 등)

전달 방식도 ConfigMap/Secret과 동일한 패턴이다.

- **env** → `valueFrom.fieldRef` 또는 `valueFrom.resourceFieldRef`로 환경 변수에 주입
- **volume** → `downwardAPI` 볼륨으로 파일 시스템에 파일로 투영

ConfigMap/Secret volume과 동일한 방식이지만, 데이터 소스가 외부 오브젝트가 아니라 Pod object 자체라는 점이 다르다.

<br>

# 분류 체계: 데이터 소스와 전달 방식

Downward API를 이해하려면 두 가지 축을 파악하면 된다.

1. **데이터 소스**: 어떤 정보를 가져오는가
  - `fieldRef` → 파드의 일반 메타데이터
  - `resourceFieldRef` → 컨테이너의 컴퓨트 리소스 제약
2. **전달 방식**: 어떻게 컨테이너에 전달하는가
  - env → 환경 변수에 주입
  - volume → 파일 시스템에 파일로 투영

그런데 완전한 2x2 조합은 아니다. `resourceFieldRef` 필드들은 env/volume 모든 전달 방식을 사용할 수 있지만, `fieldRef` 필드들은 필드마다 사용할 수 있는 전달 방식에 제한이 있다.

## fieldRef 필드별 지원 범위

| 필드 | 설명 | env | volume |
| --- | --- | --- | --- |
| `metadata.name` | 파드 이름 | O | O |
| `metadata.namespace` | 파드 네임스페이스 | O | O |
| `metadata.uid` | 파드 UID | O | O |
| `metadata.labels` | 파드의 모든 레이블 (한 줄에 하나씩, `key="value"` 형식) | X | O |
| `metadata.labels['key']` | 지정된 레이블의 값 | O | O |
| `metadata.annotations` | 파드의 모든 어노테이션 (한 줄에 하나씩, `key="value"` 형식) | X | O |
| `metadata.annotations['key']` | 지정된 어노테이션의 값 | O | O |
| `spec.nodeName` | 파드가 실행되는 워커 노드 이름 | O | X |
| `spec.serviceAccountName` | 파드의 서비스 어카운트 이름 | O | X |
| `status.podIP`, `status.podIPs` | 파드의 IP 주소 | O | X |
| `status.hostIP`, `status.hostIPs` | 워커 노드의 IP 주소 | O | X |

## resourceFieldRef 필드별 지원 범위

| 필드 | 설명 | env | volume |
| --- | --- | --- | --- |
| `requests.cpu` | 컨테이너의 CPU 요청 | O | O |
| `requests.memory` | 컨테이너의 메모리 요청 | O | O |
| `requests.ephemeral-storage` | 컨테이너의 임시 스토리지 요청 | O | O |
| `requests.hugepages-*` | 컨테이너의 hugepages 요청 | O | O |
| `limits.cpu` | 컨테이너의 CPU 제한 | O | O |
| `limits.memory` | 컨테이너의 메모리 제한 | O | O |
| `limits.ephemeral-storage` | 컨테이너의 임시 스토리지 제한 | O | O |
| `limits.hugepages-*` | 컨테이너의 hugepages 제한 | O | O |

## fieldRef 주입 방식 제한 이유

왜 `fieldRef`는 필드마다 지원하는 전달 방식이 다를까?

- **labels/annotations 전체**는 여러 줄의 키-값 쌍이라 단일 환경 변수에 담기 부적합하다. 그래서 volume만 허용된다
- `spec.nodeName`, `status.podIP` 등은 파드가 스케줄링된 후에야 결정되는 런타임 값이다. 환경 변수 방식이 더 적합하므로 env만 허용된다

<br>

# 환경 변수로 메타데이터 주입

## 파드 메타데이터 주입: fieldRef

Downward API를 사용하여 파드의 메타데이터를 환경 변수로 주입하는 예시를 보자. 다음은 파드와 노드의 이름, IP 주소를 환경 변수로 주입하는 파드 매니페스트다.

```yaml
apiVersion: v1
kind: Pod
metadata:
  name: kiada
spec:
  containers:
  - name: kiada
    image: luksa/kiada:0.4
    env:
    - name: POD_NAME
      valueFrom:
        fieldRef:
          fieldPath: metadata.name       # 파드 이름
    - name: POD_IP
      valueFrom:
        fieldRef:
          fieldPath: status.podIP        # 파드 IP
    - name: NODE_NAME
      valueFrom:
        fieldRef:
          fieldPath: spec.nodeName       # 노드 이름
    - name: NODE_IP
      valueFrom:
        fieldRef:
          fieldPath: status.hostIP       # 노드 IP
    ports:
    - name: http
      containerPort: 8080
```

파드를 생성한 후 어플리케이션에 요청을 보내면 다음과 같은 응답을 받을 수 있다.

```
Request processed by Kiada 0.4 running in pod "kiada" on node "kind-worker".
Pod hostname: kiada; Pod IP: 10.244.2.15; Node IP: 172.18.0.4. Client IP:
::ffff:127.0.0.1.
This is the default status message
```

`kubectl exec kiada -- env`로 컨테이너의 환경 변수 전체를 확인하거나, `kubectl get po kiada -o yaml`로 파드 매니페스트의 값과 비교할 수도 있다.

## 컨테이너 리소스 주입: resourceFieldRef

컨테이너에 할당된 컴퓨트 리소스 제약을 어플리케이션에 전달할 수도 있다. 일부 어플리케이션은 주어진 제약 내에서 최적으로 동작하기 위해 할당된 리소스를 알아야 한다.

```yaml
env:
- name: MAX_CPU_CORES
  valueFrom:
    resourceFieldRef:
      resource: limits.cpu          # CPU 리소스 제한
- name: MAX_MEMORY_KB
  valueFrom:
    resourceFieldRef:
      resource: limits.memory       # 메모리 리소스 제한
      divisor: 1k                   # 킬로바이트 단위로 변환
```

`valueFrom.resourceFieldRef`를 사용하여 컨테이너 리소스 필드를 주입하고, `resource` 필드로 주입할 리소스 값을 지정한다.

**`divisor`** 필드는 값을 어떤 단위로 저장할지 지정한다.

- 메모리: `1`(바이트), `1k`(킬로바이트), `1Ki`(키비바이트), `1M`(메가바이트), `1Mi`(메비바이트) 등
- CPU: 기본값 `1`(전체 코어), `1m`(밀리코어 = 1/1000 코어)으로 설정 가능
- divisor를 생략하면 기본값 `1`이 사용된다

> `containerName` 필드를 사용하면 다른 컨테이너의 리소스 제한도 참조할 수 있다. 기본적으로는 해당 환경 변수가 정의된 컨테이너의 리소스가 사용된다.

<br>

# 주요 유스케이스

Downward API가 실제로 어떤 상황에서 유용하게 쓰이는지 정리해 보자.

## 로깅/모니터링에서 파드 식별

로그에 파드 이름, 네임스페이스, 노드 이름을 포함시켜 어떤 파드에서 발생한 로그인지 추적할 수 있다. Prometheus, Datadog 등 메트릭 수집 시 라벨로 파드 메타데이터를 첨부하는 데에도 활용된다. `MY_POD_NAME`, `MY_NODE_NAME`을 환경 변수로 주입하여 로그 포맷에 포함하는 방식이다.

## 리소스 제한 인지

리소스 인지(resource-aware) 어플리케이션에서 유용하다. JVM의 `-Xmx` 설정을 컨테이너 `requests.memory` 기반으로 동적 계산하거나, 워커 스레드 수를 `requests.cpu` 기반으로 조정하는 식이다.

## 서비스 디스커버리/자기 참조

파드가 자신의 IP(`status.podIP`)를 알아야 다른 서비스에 자기 주소를 등록할 때 필요하다. Consul, etcd 클러스터 조인 같은 경우가 대표적이다. StatefulSet에서 자기 이름을 알아 리더/팔로워 역할을 분기하는 데에도 쓰인다.

## 멀티테넌트/RBAC 맥락 전달

`metadata.namespace`를 앱에 전달하여 네임스페이스별 분기 처리를 하는 경우에 활용된다.

<br>

# Downward API의 한계와 대안

Downward API가 노출할 수 있는 정보는 **자기 자신(Pod)의 메타데이터와 리소스 제약**으로 제한된다. 다음 정보는 Downward API로 얻을 수 없다.

- 다른 Pod나 Service의 정보
- Node의 상세 정보 (노드 이름, IP 외의 레이블, 어노테이션, 용량 등)
- 클러스터 전체의 상태 (네임스페이스 목록, RBAC 규칙 등)

이런 정보가 필요하면 **Kubernetes API를 직접 호출**해야 한다. 판단 기준은 단순하다.

| 필요한 정보 | 방법 |
| --- | --- |
| 자기 Pod의 이름, IP, 노드, 레이블, 리소스 제약 | Downward API |
| 다른 Pod, Service, Node 상세, 클러스터 상태 | Kubernetes API 직접 호출 |

Downward API는 어플리케이션을 Kubernetes에 종속시키지 않는다는 장점이 있으므로, 가능한 범위에서는 Downward API를 우선 사용하고 부족한 경우에만 API 호출을 고려하는 것이 좋다.

<br>

# 정리

Downward API의 핵심 가치는 어플리케이션이 Kubernetes API에 종속되지 않고도 런타임 메타데이터를 활용할 수 있다는 점이다. 파드 이름, IP, 노드 정보 같은 런타임 데이터를 얻기 위해 API 서버를 직접 호출할 필요가 없다.

ConfigMap/Secret과 동일한 `valueFrom` 패턴을 사용하지만, 데이터 소스가 Pod object 자체라는 점이 다르다. `fieldRef`로 파드의 일반 메타데이터를, `resourceFieldRef`로 컨테이너의 리소스 제약을 참조한다.

전달 방식은 env와 volume 두 가지를 지원하며, `fieldRef` 필드마다 지원 범위가 다르다는 점을 기억해 두자. labels/annotations 전체는 volume만, `spec.nodeName` 등 런타임 결정 값은 env만 지원된다.

<br>