---
title:  "[Kubernetes] Pod 볼륨 - 1. 볼륨 소개"
excerpt: "Kubernetes Pod에서 볼륨이 필요한 이유, 마운트 기초, 볼륨 타입 개요를 정리한다."
categories:
  - Kubernetes
toc: true
header:
  teaser: /assets/images/blog-Dev.jpg
tags:
  - Kubernetes
  - Kubernetes-in-Action-2nd
  - volume
  - volumeMount
  - subPath
  - emptyDir
  - hostPath
  - ephemeral-volume
hidden: true
---

*[Kubernetes in Action 2nd Edition](https://www.manning.com/books/kubernetes-in-action-second-edition) 9장의 학습 내용을 기반으로 합니다.*

<br>

# TL;DR

- 컨테이너의 파일시스템은 일회용(ephemeral)이므로, 컨테이너가 재생성(recreate)되면 데이터가 사라진다. 이를 해결하기 위해 **볼륨**을 사용한다
- 볼륨은 `spec.volumes`에서 정의하고, `spec.containers[].volumeMounts`에서 컨테이너에 마운트한다. 볼륨 타입에 따라 `volumes` 하위 설정이 달라지지만, `volumeMounts` 구조는 모든 볼륨 타입에서 동일하다
- 볼륨은 Pod 내부의 구성 요소로 Pod와 수명 주기를 공유하며, 컨테이너의 수명 주기와는 독립적이다
- Kubernetes 볼륨은 Pod의 수명에 종속되는 **임시(ephemeral) 볼륨**과 독립적인 **영구(persistent) 볼륨**으로 나뉜다

<br>

# 시리즈 안내

Kubernetes Pod에서 볼륨을 사용하는 방법을 다루는 시리즈다. 9장의 임시 볼륨(ephemeral volume)을 중심으로 정리한다.

1. 볼륨 소개 (이 글)
2. [emptyDir]({% post_url 2026-04-05-Kubernetes-Pod-Volume-02-emptyDir %})
3. [image 볼륨과 hostPath]({% post_url 2026-04-05-Kubernetes-Pod-Volume-03-Image-Volume-HostPath %})
4. [configMap, secret, downwardAPI, projected 볼륨]({% post_url 2026-04-05-Kubernetes-Pod-Volume-04-ConfigMap-Secret-DownwardAPI-Projected %})

[어플리케이션 설정]({% post_url 2026-04-05-Kubernetes-Application-Config-01-Command-Args-Env %}) 시리즈에서 ConfigMap, Secret, Downward API의 데이터를 환경 변수로 주입하는 방법을 다뤘다면, 이 시리즈에서는 **볼륨 마운트**를 통해 파일로 전달하는 방식을 다룬다.

<br>

# 볼륨과 마운트 기초

Pod의 컨테이너는 보통 스토리지 **볼륨**을 동반하며, 볼륨은 Pod의 수명 동안(또는 그 이상) 데이터를 저장하거나 Pod 내 다른 컨테이너와 파일을 공유할 수 있게 해준다.

## YAML 구조: volumes와 volumeMounts

컨테이너에서 볼륨을 사용하려면 두 곳을 설정해야 한다.

1. `spec.volumes`에서 볼륨을 **정의**한다
2. `spec.containers[].volumeMounts`에서 컨테이너에 **마운트**한다

```yaml
apiVersion: v1
kind: Pod
metadata:
  name: my-pod
spec:
  # 1. Pod 레벨: 볼륨 정의
  volumes:
  - name: <볼륨이름>              # volumeMounts에서 참조할 이름
    <볼륨타입>: <설정>             # emptyDir, hostPath, configMap, secret, pvc 등

  containers:
  - name: <컨테이너이름>
    image: <이미지>
    # 2. 컨테이너 레벨: 볼륨 마운트
    volumeMounts:
    - name: <볼륨이름>            # volumes[].name과 매칭
      mountPath: <컨테이너 내 경로> # 컨테이너 안에서 마운트될 위치
      subPath: <볼륨 내 항목>      # (선택) 볼륨에서 특정 파일/디렉토리만 선택
      readOnly: true|false        # (선택, 기본값: false)
```

`volumes`는 "어떤 스토리지를 사용할 것인가"를 정의하고, `volumeMounts`는 "그 스토리지를 컨테이너의 어디에 연결할 것인가"를 정의한다. 볼륨 타입(`emptyDir`, `hostPath`, `configMap` 등)에 따라 `volumes` 하위 설정이 달라지지만, `volumeMounts` 구조는 **모든 볼륨 타입에서 동일**하다.

## 디렉토리 마운트 vs subPath

볼륨 마운트는 Linux의 `mount` 시스템콜을 기반으로 하며, 볼륨 타입과 무관하게 공통으로 적용되는 동작이다.

|  | 디렉토리 마운트 (기본) | 단일 파일 마운트 (`subPath`) |
| --- | --- | --- |
| **마운트 대상** | 볼륨 전체 | 볼륨 내 특정 파일 |
| **기존 파일** | 해당 디렉토리의 기존 파일이 **모두 가려짐** | 기존 파일 **유지**, 지정한 파일만 추가/덮어쓰기 |
| **자동 갱신** | 원본 업데이트 시 **자동 반영** (심볼릭 링크 기반) | 원본 업데이트 시 **반영되지 않음** (bind mount) |

**디렉토리 마운트**(기본 동작)는 볼륨을 디렉토리에 마운트하면 해당 디렉토리의 기존 파일이 모두 가려지고, 볼륨이 제공하는 파일만 보이게 된다.

```yaml
volumeMounts:
- name: my-volume
  mountPath: /etc/envoy      # 디렉토리 마운트
  readOnly: true
```

**단일 파일 마운트**(`subPath` 사용)는 기존 디렉토리의 파일을 유지하면서 볼륨의 특정 파일 하나만 추가한다.

```yaml
volumeMounts:
- name: my-volume
  subPath: my-app.conf       # 볼륨 내에서 마운트할 특정 파일
  mountPath: /etc/my-app.conf # 파일 경로를 명시
```

규칙을 정리하면 다음과 같다.

- `subPath` 없음 → `mountPath`는 **디렉토리**가 되고, 볼륨 전체가 마운트된다
- `subPath` 있음 → `mountPath`는 **파일 하나**가 되고, 볼륨에서 선택한 항목만 마운트된다

## 마운트 시 업데이트 동작

디렉토리 마운트와 단일 파일 마운트는 원본(ConfigMap/Secret 등) 업데이트 시 갱신 동작이 다르다.

- **디렉토리 마운트**: kubelet이 `..data` → 타임스탬프 디렉토리 심볼릭 링크를 사용한다. ConfigMap/Secret 업데이트 시 새 타임스탬프 디렉토리를 만들고 `..data` 심볼릭 링크를 원자적(atomic)으로 교체한다. 컨테이너가 파일을 열 때마다 심볼릭 링크를 따라가므로 **항상 최신 데이터를 읽는다**
- **subPath 마운트**: kubelet이 특정 파일을 bind mount로 컨테이너에 연결한다. bind mount는 마운트 시점의 inode에 고정되므로, 원본이 업데이트되어도 **반영되지 않는다**

디렉토리 마운트를 쓰되, 기존 파일을 가리지 않는 별도 경로에 마운트한 뒤 활용하면 두 가지 장점을 모두 살릴 수 있다.

```yaml
volumeMounts:
- name: my-config
  mountPath: /etc/config    # 별도 디렉토리에 마운트 (자동 갱신됨)
  readOnly: true
```

<br>

# 볼륨이 필요한 이유

일반적인 컴퓨터에서는 프로세스들이 동일한 파일시스템을 사용하지만, 컨테이너는 다르다. 각 컨테이너는 컨테이너 이미지에서 제공하는 **자체 격리된 파일시스템**을 가진다.

- 컨테이너가 시작되면 파일시스템에는 빌드 시점에 이미지에 추가된 파일들만 존재한다
- 실행 중인 프로세스가 파일을 수정하거나 새 파일을 생성할 수 있다
- 하지만 컨테이너가 종료되고 재시작되면 모든 변경 사항이 사라진다

![볼륨이 컨테이너에 마운트되는 기본 그림]({{site.url}}/assets/images/k8s-vol-01-volume-mount-basic.png){: .align-center}

## Quiz 서비스 소개

Kiada 웹 어플리케이션, Quote 서비스에 이어 Quiz 서비스를 만든다. Quiz 서비스는 Kiada 웹 어플리케이션에서 표시할 객관식 문제를 제공하고, 답변도 저장한다.

![kiada web app 구성: quote service, quiz service]({{site.url}}/assets/images/k8s-vol-01-kiada-architecture.png){: .align-center}

![Quiz 서비스 구조: RESTful API + MongoDB]({{site.url}}/assets/images/k8s-vol-01-quiz-service-architecture.png){: .align-center}

Quiz 서비스는 RESTful API 프론트엔드와 MongoDB 데이터베이스 백엔드로 구성된다. 처음에는 이 두 컴포넌트를 동일한 Pod의 별도 컨테이너에서 실행한다.

## 볼륨 없이 실행

볼륨 없이 Quiz 서비스를 실행해 보자.

```yaml
# pod.quiz.novolume.yaml
apiVersion: v1
kind: Pod
metadata:
  name: quiz
spec:
  containers:
  - name: quiz-api
    image: luksa/quiz-api:0.1
    imagePullPolicy: IfNotPresent
    ports:
    - name: http
      containerPort: 8080
  - name: mongo
    image: mongo:7
```

```bash
kubectl apply -f pod.quiz.novolume.yaml
kubectl get pods
# NAME   READY   STATUS    RESTARTS   AGE
# quiz   2/2     Running   0          113s
```

MongoDB에 문제를 추가한 후, Quiz API를 통해 조회할 수 있다.

```bash
# MongoDB에 문제 추가
kubectl exec -it quiz -c mongo -- mongosh kiada --eval '
db.questions.insertOne({
  id: 1,
  text: "What does k8s mean?",
  answers: ["Kates", "Kubernetes", "Kooba Dooba Doo!"],
  correctAnswerIndex: 1
})'

# Quiz API로 조회
kubectl port-forward pod/quiz 8080:8080
curl localhost:8080/questions/random
# {"id":1,"text":"What does k8s mean?","correctAnswerIndex":1,...}
```

## 컨테이너 재생성과 데이터 손실

MongoDB 컨테이너가 재시작(실제로는 **재생성**)되면 파일시스템이 초기화되어 모든 데이터가 사라진다.

```bash
# MongoDB 서버 강제 종료
kubectl exec -it quiz -c mongo -- mongosh admin --eval "db.shutdownServer()"
# command terminated with exit code 137

# 데이터 확인 → 0건
kubectl exec -it quiz -c mongo -- mongosh kiada --quiet --eval "db.questions.countDocuments()"
# 0
```

`quiz` Pod는 여전히 동일한 Pod이다. `quiz-api` 컨테이너는 정상적으로 실행 중이었고, `mongo` 컨테이너만 재생성되었다. 더 정확히 말하면, 재시작(restart)이 아니라 **재생성(recreate)**된 것이다.

| | Restart (재시작) | Recreate (재생성) |
| --- | --- | --- |
| 의미 | 같은 컨테이너를 다시 시작 | 기존 컨테이너를 버리고 새로 만듦 |
| 파일시스템 | 기존 데이터 유지 | **완전히 초기화** |
| Container ID | 동일 | **새로운 ID** |

Kubernetes의 kubelet은 컨테이너 프로세스가 종료되면 **항상 기존 컨테이너를 삭제하고 새 컨테이너를 만든다.** "같은 컨테이너를 다시 켜는" 메커니즘 자체가 없다. `kubectl get pods`에 표시되는 `RESTARTS`는 실제로는 "몇 번 recreate했는가"에 가깝다.

Kubernetes의 설계 철학은 컨테이너를 **일회용(disposable), 불변(immutable)** 단위로 취급하는 것이다. 컨테이너에 문제가 생기면 고치는 게 아니라 버리고 새로 만든다. 따라서 컨테이너 내부에 상태를 저장하면 **반드시 잃어버리게 되므로**, 영속적인 데이터는 **반드시 볼륨을 사용해야 한다.**

<br>

# 볼륨이 Pod에 들어가는 방식

컨테이너와 마찬가지로, 볼륨은 Pod나 노드처럼 최상위 리소스가 아니라 **Pod 내부의 구성 요소**이며, 따라서 **Pod와 수명 주기를 공유**한다.

![볼륨이 Pod 내부의 구성 요소로 존재하는 모습]({{site.url}}/assets/images/k8s-vol-01-volume-in-pod.png){: .align-center}

- `volumes:`는 항상 Pod spec 안에 정의된다. `kubectl get volume` 같은 건 없다
- Ephemeral volume (emptyDir 등): Pod 삭제 시 **데이터 자체가 사라진다**
- Persistent volume (PVC/PV): Pod 삭제 시 **마운트 연결만 끊기고**, 데이터는 PV에 그대로 남는다

## 컨테이너 재시작 시 파일 유지

Pod의 모든 볼륨은 Pod가 설정될 때 생성되며, **컨테이너가 시작되기 전에 만들어진다.** Pod가 종료되면 볼륨도 함께 제거된다. 컨테이너가 (재)시작될 때마다, 컨테이너가 사용하도록 구성된 볼륨이 컨테이너의 파일시스템에 마운트된다.

![컨테이너 재시작 시에도 볼륨 데이터가 유지되는 모습]({{site.url}}/assets/images/k8s-vol-01-volume-container-restart.png){: .align-center}

| **상황** | **볼륨** | **데이터** |
| --- | --- | --- |
| **컨테이너 재시작** (Pod은 유지) | **유지됨** | 유지됨 (emptyDir 포함) |
| **Pod 삭제/재생성** | 새로 생성됨 | emptyDir는 사라짐, PV는 유지됨 |

> **Note:** 컨테이너 재시작 시 파일을 보존하기 위해 볼륨을 마운트하기 전에, 이것이 컨테이너의 **자가 치유(self-healing) 능력**에 어떤 영향을 미치는지 고려해야 한다. 손상된 파일을 그대로 사용하여 컨테이너를 재시작하면 **무한 크래시 루프(CrashLoopBackOff)**에 빠질 수 있다. 어플리케이션의 **상태(state)** 데이터는 보존해야 하지만, 로컬 캐시처럼 재생성 가능한 데이터는 오히려 볼륨에 넣지 않는 것이 컨테이너의 self-healing 능력을 유지하는 데 더 나을 수 있다.

## 여러 볼륨과 컨테이너

Pod는 여러 볼륨을 가질 수 있으며, 각 컨테이너는 이 볼륨들 중 0개, 1개 또는 여러 개를 **서로 다른 위치에 마운트할 수 있다.**

![하나의 Pod에 여러 볼륨이 서로 다른 컨테이너에 마운트되는 모습]({{site.url}}/assets/images/k8s-vol-01-volume-multiple-mounts.png){: .align-center}

하나의 볼륨을 둘 이상의 컨테이너에 마운트하여 파일을 공유할 수도 있다. 예를 들어, 사이드카 컨테이너가 웹 서버 로그를 처리하거나, 콘텐츠 생성 에이전트가 만든 파일을 웹 서버가 제공하는 경우다.

![사이드카 패턴에서 볼륨을 통한 파일 공유]({{site.url}}/assets/images/k8s-vol-01-volume-sidecar-sharing.png){: .align-center}

동일한 볼륨을 각 컨테이너의 필요에 따라 **서로 다른 경로에 마운트**할 수 있으며, 각 컨테이너의 볼륨 마운트를 **읽기/쓰기** 또는 **읽기 전용**으로 구성할 수 있다.

## Pod 인스턴스 간 데이터 유지

볼륨은 Pod의 수명 주기에 연결되어 있으나, 볼륨 타입에 따라 Pod와 볼륨이 사라진 후에도 볼륨 내 파일이 온전하게 남아 있을 수 있다.

![Pod 외부의 영구 스토리지에 매핑된 볼륨]({{site.url}}/assets/images/k8s-vol-01-volume-persistent-storage.png){: .align-center}

Pod 볼륨이 NAS(Network Attached Storage) 같은 외부 영구 스토리지에 매핑되면, Pod가 다른 워커 노드에서 실행되는 새 Pod로 교체된 후에도 이전 인스턴스가 저장한 데이터에 접근할 수 있다.

## Pod 간 데이터 공유

외부 스토리지 볼륨을 제공하는 기술에 따라, 동일한 외부 볼륨을 여러 Pod에 동시에 연결하여 데이터를 공유할 수 있다.

![세 개의 Pod가 동일한 외부 영구 스토리지 볼륨에 매핑]({{site.url}}/assets/images/k8s-vol-01-volume-shared-pods.png){: .align-center}

- NFS 같은 기술은 여러 머신에서 읽기/쓰기 모드로 볼륨을 마운트하는 것을 지원한다
- GCE Persistent Disk 같은 클라우드 기술은 단일 노드에서만 읽기/쓰기가 가능하고, 여러 노드에서는 읽기 전용만 지원한다

<br>

# 볼륨 타입 소개

Pod에 볼륨을 추가할 때는 **볼륨 타입**을 지정해야 한다. 다양한 볼륨 타입이 제공된다.

| 볼륨 타입 | 설명 |
| --- | --- |
| `emptyDir` | Pod의 수명 동안 데이터를 저장하는 빈 디렉토리. Pod 시작 직전에 생성됨 |
| `hostPath` | 워커 노드의 파일시스템에 있는 파일을 Pod에 마운트 |
| `configMap`, `secret`, `downwardAPI`, `projected` | ConfigMap, Secret 데이터, Pod 메타데이터를 노출하는 특수 볼륨 타입 |
| `image` | 다른 컨테이너 이미지의 파일시스템을 볼륨으로 마운트 |
| `ephemeral` | CSI 드라이버가 제공하는 임시 볼륨. Pod의 수명 동안에만 존재 |
| `persistentVolumeClaim` | PersistentVolumeClaim을 통해 외부 스토리지를 Pod에 통합하는 이식성 있는 방법 |

이전에는 `nfs`, `gcePersistentDisk`, `awsElasticBlockStore` 등 기술별 볼륨 타입이 있었으나, 현재는 **deprecated**되었다. CSI 드라이버를 통해 접근하며, `persistentVolumeClaim` 볼륨을 사용하는 것이 권장된다.

Kubernetes 볼륨은 크게 두 분류로 나뉜다.

- **임시(ephemeral) 볼륨**: 컨테이너와 독립적이나 **Pod와 종속**. Pod 삭제 시 데이터 소멸. 9장(이 시리즈)에서 다룬다
  - `emptyDir`, `configMap`, `secret`, `downwardAPI`, `hostPath`, `image`, CSI `ephemeral`
- **영구(persistent) 볼륨**: 컨테이너와도 독립, **Pod와도 독립**. Pod 삭제/재스케줄되어도 데이터 유지. 10장에서 다룬다
  - `PersistentVolume`, `PersistentVolumeClaim`, CSI 기반 영구 스토리지

<br>

# 정리

- 컨테이너의 파일시스템은 일회용이므로, 데이터를 유지하려면 **볼륨**이 필요하다
- 볼륨은 `spec.volumes`에서 정의하고, `spec.containers[].volumeMounts`에서 마운트한다
- 디렉토리 마운트는 기존 파일을 가리고 자동 갱신된다. `subPath` 마운트는 기존 파일을 유지하지만 자동 갱신되지 않는다
- Kubernetes에서 컨테이너 "재시작"은 실제로는 **재생성(recreate)**이다. 같은 컨테이너를 다시 켜는 메커니즘 자체가 없다
- 볼륨은 Pod와 수명 주기를 공유하며, 컨테이너 수명 주기와는 독립적이다
- 임시 볼륨(emptyDir, configMap, secret 등)은 Pod 삭제 시 사라지고, 영구 볼륨(PV/PVC)은 Pod와 독립적으로 존재한다

<br>