---
title:  "[Kubernetes] Pod 볼륨 - 2. emptyDir"
excerpt: "emptyDir 볼륨으로 컨테이너 재시작 간 데이터를 유지하고, init 컨테이너로 초기화하며, 컨테이너 간 파일을 공유하는 방법을 정리한다."
categories:
  - Kubernetes
toc: true
header:
  teaser: /assets/images/blog-Dev.jpg
tags:
  - Kubernetes
  - Kubernetes-in-Action-2nd
  - volume
  - emptyDir
  - init-container
  - sidecar
  - tmpfs
hidden: true
---

*[Kubernetes in Action 2nd Edition](https://www.manning.com/books/kubernetes-in-action-second-edition) 9장의 학습 내용을 기반으로 합니다.*

<br>

# TL;DR

- `emptyDir`은 Pod와 수명 주기를 같이 하는 임시 볼륨으로, 빈 디렉토리로 시작한다
- 컨테이너가 재생성(recreate)되어도 같은 Pod 내에서 emptyDir의 데이터는 유지된다. Pod가 삭제되면 데이터도 사라진다
- init 컨테이너를 사용해 emptyDir 볼륨에 초기 데이터를 채울 수 있다
- 동일한 emptyDir 볼륨을 여러 컨테이너에 마운트하여 파일을 공유할 수 있다
- `medium: Memory` 설정으로 tmpfs(메모리 기반) 볼륨을 생성할 수 있다

<br>

# emptyDir 볼륨 개요

가장 단순한 볼륨 타입인 `emptyDir`은 **Pod와 수명 주기를 같이 하는 임시 볼륨**이다.

- 이름에서 알 수 있듯이 **빈 디렉토리**로 시작한다
- `medium`을 `Memory`로 설정하면 데이터를 디스크 대신 메모리(tmpfs)에 저장할 수 있다
- 컨테이너에 마운트되면 볼륨에 작성된 파일은 **Pod가 존재하는 동안** 보존되나, 다른 Pod와는 공유할 수 없다

이 볼륨 타입은 다음 상황에서 사용된다.

- **단일 컨테이너 Pod**에서 컨테이너가 재시작되더라도 데이터를 보존해야 하는 경우
- 컨테이너의 파일시스템이 읽기 전용으로 설정되었지만 임시로 데이터를 쓸 공간이 필요한 경우
- **두 개 이상의 컨테이너**를 가진 Pod에서 컨테이너 간 데이터를 공유하는 경우

<br>

# 컨테이너 재시작 간 파일 유지

이전 글에서 만든 quiz Pod에 `emptyDir` 볼륨을 추가하여, MongoDB 컨테이너가 재시작될 때 데이터가 손실되지 않도록 만든다.

## Pod에 emptyDir 볼륨 추가하기

![quiz Pod에 emptyDir 볼륨이 추가된 모습]({{site.url}}/assets/images/k8s-vol-02-emptydir-added.png){: .align-center}

`quiz-data`라는 이름의 emptyDir 볼륨을 `spec.volumes`에 정의하고, mongo 컨테이너의 `/data/db`에 마운트한다.

```yaml
# pod.quiz.emptydir.yaml
apiVersion: v1
kind: Pod
metadata:
  name: quiz
spec:
  volumes:
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
```

## emptyDir 볼륨 설정

`emptyDir` 볼륨 타입은 두 가지 설정 필드를 지원한다.

| 필드 | 설명 |
| --- | --- |
| `medium` | 스토리지 매체 타입. 비워두면 호스트 노드의 기본 디스크를 사용한다. `Memory`로 설정하면 tmpfs(메모리 기반 파일시스템)를 사용한다 |
| `sizeLimit` | 볼륨의 최대 크기 제한. 예: `10Mi` |

두 필드 모두 선택 사항이다. `emptyDir: {}`는 "두 필드 모두 기본값을 사용하겠다"는 의미로, 저장 매체는 노드의 디스크, 크기 제한은 없음이다. YAML에서는 `emptyDir:`만 쓰고 `{}`를 생략해도 동일하게 동작한다.

## emptyDir 볼륨의 수명

문제를 추가한 후 MongoDB 컨테이너를 종료시키고 데이터가 유지되는지 확인한다.

```bash
kubectl apply -f pod.quiz.emptydir.yaml

# 문제 추가
./insert-question.sh

# 컨테이너 강제 종료
kubectl exec -it quiz -c mongo -- mongosh admin --eval "db.shutdownServer()"
# command terminated with exit code 137

# 데이터 확인 → 1건 유지!
kubectl exec -it quiz -c mongo -- mongosh kiada --quiet --eval "db.questions.countDocuments()"
# 1
```

컨테이너를 재시작해도 더 이상 파일이 사라지지 않는다. 파일이 컨테이너의 파일시스템이 아닌 **볼륨에 저장**되기 때문이다.

## emptyDir 볼륨의 파일 저장 위치

![emptyDir 볼륨 파일이 호스트 노드의 파일시스템에 저장되는 모습]({{site.url}}/assets/images/k8s-vol-02-emptydir-storage-location.png){: .align-center}

emptyDir 볼륨의 파일은 호스트 노드의 파일시스템에 있는 디렉토리에 저장된다. 일반적으로 다음 위치에 있다.

```
/var/lib/kubelet/pods/<pod_UID>/volumes/kubernetes.io~empty-dir/<volume_name>
```

```bash
# Pod UID 확인 후 호스트에서 emptyDir 확인
docker exec -it kind-control-plane ls -al \
  /var/lib/kubelet/pods/$(kubectl get pod quiz -o jsonpath='{.metadata.uid}')/volumes/kubernetes.io~empty-dir/quiz-data/
```

<details markdown="1">
<summary><b>출력 결과</b></summary>

```
total 360
drwxrwxrwx 5  999 root             4096 Mar 31 16:38 .
drwxr-xr-x 3 root root             4096 Mar 31 16:31 ..
drwx------ 3  999 root             4096 Mar 31 16:31 .mongodb
-rw------- 1  999 systemd-journal    50 Mar 31 16:31 WiredTiger
-rw------- 1  999 systemd-journal    21 Mar 31 16:31 WiredTiger.lock
-rw------- 1  999 systemd-journal  1468 Mar 31 16:38 WiredTiger.turtle
-rw------- 1  999 systemd-journal 77824 Mar 31 16:38 WiredTiger.wt
...
-rw------- 1  999 systemd-journal   114 Mar 31 16:31 storage.bson
```

</details>

MongoDB WiredTiger 스토리지 엔진 파일이 확인된다. 이 파일들이 emptyDir 볼륨을 통해 노드의 디스크에 실제로 저장된 것이다. **Pod가 삭제되면 이 디렉토리도 함께 지워진다.**

```bash
kubectl delete po quiz

# Pod 삭제 후 → 디렉토리도 사라짐
docker exec -it kind-control-plane ls -al \
  /var/lib/kubelet/pods/$(kubectl get pod quiz -o jsonpath='{.metadata.uid}')/volumes/kubernetes.io~empty-dir/quiz-data/
# Error from server (NotFound): pods "quiz" not found
```

데이터는 컨테이너 재시작 시에는 유지되지만, **Pod가 삭제되면 유지되지 않는다.** 데이터를 제대로 영속화하려면 퍼시스턴트 볼륨(persistent volume)을 사용해야 한다.

## 메모리에 emptyDir 볼륨 생성하기

볼륨의 I/O 성능을 최대한 빠르게 하거나 **민감한 데이터를 저장**할 때는, tmpfs 파일시스템을 사용하여 파일을 메모리에 저장할 수 있다. `medium` 필드를 `Memory`로 설정한다.

```yaml
volumes:
- name: content
  emptyDir:
    medium: Memory
```

데이터가 디스크에 기록되지 않으므로, 데이터가 유출되거나 원하는 것보다 오래 유지될 가능성이 줄어든다. Kubernetes는 Secret 오브젝트의 데이터를 컨테이너에 노출할 때도 동일한 인메모리 방식을 사용한다.

인메모리 볼륨의 크기는 `sizeLimit` 필드로 제한할 수 있으며, 특히 Pod의 전체 메모리 사용량이 리소스 제한(resource limits)에 의해 제한되는 경우에 중요하다.

<br>

# emptyDir 볼륨 초기화

emptyDir 볼륨은 항상 비어 있으므로, **init 컨테이너**를 사용해 Pod 시작 시 자동으로 데이터를 채울 수 있다.

## init 컨테이너로 emptyDir 볼륨 초기화하기

![init 컨테이너가 emptyDir 볼륨에 초기화 스크립트를 복사하는 구조]({{site.url}}/assets/images/k8s-vol-02-emptydir-init-container.png){: .align-center}

quiz 문제를 JSON 파일에 저장하고, init 컨테이너가 이 파일을 공유 볼륨에 복사하여 MongoDB가 시작할 때 읽을 수 있도록 한다. MongoDB의 `/docker-entrypoint-initdb.d/` 메커니즘을 활용한다. 이 디렉토리에 `.js` 파일을 넣으면 MongoDB가 첫 시작 시 자동으로 실행한다.

```yaml
# pod.quiz.emptydir.init.yaml
apiVersion: v1
kind: Pod
metadata:
  name: quiz
spec:
  volumes:
  - name: initdb
    emptyDir: {}
  - name: quiz-data
    emptyDir: {}
  initContainers:
  - name: installer
    image: luksa/quiz-initdb-script-installer:0.1
    imagePullPolicy: IfNotPresent
    volumeMounts:
    - name: initdb
      mountPath: /initdb.d
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

Pod가 시작되면 **먼저 볼륨이 생성된 후 init 컨테이너가 시작**된다. init 컨테이너가 `insert-questions.js` 파일을 `initdb` 볼륨에 복사한 후 종료되면, 메인 컨테이너들이 시작된다. `initdb` 볼륨이 mongo 컨테이너의 `/docker-entrypoint-initdb.d/`에 마운트되어 있으므로, MongoDB가 `.js` 파일을 실행하여 데이터베이스에 문제를 삽입한다.

```bash
kubectl apply -f pod.quiz.emptydir.init.yaml

kubectl exec -it quiz -c mongo -- mongosh kiada --quiet --eval "db.questions.countDocuments()"
# 6
```

## 인라인 방식으로 볼륨 초기화하기

짧은 파일로 emptyDir 볼륨을 초기화하고 싶을 때는 파일 내용을 Pod 매니페스트에 직접 정의할 수 있다.

```yaml
# pod.demo-emptydir-inline.yaml
apiVersion: v1
kind: Pod
metadata:
  name: demo-emptydir-inline
spec:
  volumes:
  - name: my-volume
    emptyDir: {}
  initContainers:
  - name: my-volume-initializer
    image: busybox
    command:
    - sh
    - -c
    - |
      cat <<EOF > /mnt/my-volume/my-file.txt
      line 1: This is a multi-line file
      line 2: Written from an init container
      line 3: Defined inline in the Pod manifest
      EOF
    volumeMounts:
    - name: my-volume
      mountPath: /mnt/my-volume
  containers:
  - name: main
    image: busybox
    command: ["sh", "-c", "cat /app/my-file.txt && sleep infinity"]
    volumeMounts:
    - name: my-volume
      mountPath: /app
```

ConfigMap이나 별도 리소스 없이도 어플리케이션에 짧은 설정 파일을 제공할 수 있는 간편한 방법이다.

<br>

# 컨테이너 간 파일 공유

emptyDir 볼륨을 여러 메인 컨테이너에 동시에 마운트하여 파일을 공유할 수 있다.

## quote Pod를 멀티 컨테이너 Pod로 변환

이전 장에서 `fortune` 커맨드를 실행하기 위해 post-start hook을 사용했던 `quote` Pod를 변경한다. Nginx는 웹 서버로 유지하되, post-start hook을 매분 새 quote를 생성하는 `quote-writer` 컨테이너로 대체한다.

![quote Pod의 멀티 컨테이너 구조: quote-writer와 nginx가 emptyDir를 공유]({{site.url}}/assets/images/k8s-vol-02-quote-pod-multi-container.png){: .align-center}

```yaml
# pod.quote.yaml
apiVersion: v1
kind: Pod
metadata:
  name: quote
spec:
  volumes:
  - name: shared
    emptyDir: {}
  containers:
  - name: quote-writer
    image: luksa/quote-writer:0.1
    imagePullPolicy: IfNotPresent
    volumeMounts:
    - name: shared
      mountPath: /var/local/output
  - name: nginx
    image: nginx:alpine
    volumeMounts:
    - name: shared
      mountPath: /usr/share/nginx/html
      readOnly: true
    ports:
    - name: http
      containerPort: 80
```

- `quote-writer` 컨테이너: `/var/local/output`에 quote 파일을 쓴다
- `nginx` 컨테이너: `/usr/share/nginx/html`에서 파일을 제공한다. 읽기 전용으로 마운트되어 있다

동일한 볼륨이 각 컨테이너에 **서로 다른 경로로 마운트**된다. 보안상 nginx가 볼륨에 쓰기를 하지 못하도록 `readOnly: true`로 설정하는 것이 좋다.

```bash
kubectl apply -f pod.quote.yaml

kubectl port-forward pod/quote 1080:80
curl localhost:1080/quote
```

> **Note:** 두 컨테이너는 동시에 시작되므로, nginx는 이미 실행 중인데 quote가 아직 생성되지 않은 짧은 기간이 발생할 수 있다. 이를 방지하려면 init 컨테이너(또는 네이티브 사이드카의 `restartPolicy: Always`)를 사용해 초기 quote를 미리 생성하면 된다.

<br>

# emptyDir 사용 사례

## 사이드카 간 파일 공유 (CKA 빈출)

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: logging-deployment
spec:
  replicas: 1
  selector:
    matchLabels:
      app: logger
  template:
    metadata:
      labels:
        app: logger
    spec:
      volumes:
      - name: log-volume
        emptyDir: {}
      initContainers:
      - name: log-agent
        image: busybox
        command: ["sh", "-c", "touch /var/log/app/app.log; tail -f /var/log/app/app.log"]
        volumeMounts:
        - name: log-volume
          mountPath: /var/log/app
        restartPolicy: Always
      containers:
      - name: app-container
        image: busybox
        command: ["sh", "-c", "while true; do echo 'Log entry' >> /var/log/app/app.log; sleep 5; done"]
        volumeMounts:
        - name: log-volume
          mountPath: /var/log/app
```

## ML 워크로드: /dev/shm 확장

PyTorch DataLoader의 `num_workers > 0` 설정 시 shared memory가 부족하면 에러가 발생한다. emptyDir 타입 볼륨으로 `/dev/shm`을 확장하여 해결한다.

```yaml
containers:
- name: model-trainer
  image: sirzzang/mlops:model-trainer-0.0.1
  volumeMounts:
  - mountPath: /dev/shm
    name: shm-empty-dir
volumes:
- emptyDir:
    medium: Memory
    sizeLimit: 2Gi
  name: shm-empty-dir
```

## ML 모델 서빙: init 컨테이너 + emptyDir

init 컨테이너가 MinIO에서 모델 파일을 다운로드하여 emptyDir에 저장하고, 메인 컨테이너가 이를 읽기 전용으로 마운트하여 서빙하는 패턴이다.

```yaml
initContainers:
- name: model-downloader
  image: minio/mc:latest
  command: ["/bin/sh", "-c"]
  args:
  - |
    mc alias set myminio $MINIO_ENDPOINT $MINIO_ACCESS_KEY $MINIO_SECRET_KEY
    mc cp myminio/${MINIO_BUCKET}/${MINIO_OBJECT_PATH} /models/model.pth
  volumeMounts:
  - name: model-storage
    mountPath: /models
containers:
- name: inference-server
  image: my-inference:latest
  env:
  - name: MODEL_PATH
    value: "/models/model.pth"
  volumeMounts:
  - name: model-storage
    mountPath: /models
    readOnly: true
  resources:
    limits:
      nvidia.com/gpu: 1
volumes:
- name: model-storage
  emptyDir: {}
```

<br>

# 정리

- `emptyDir`은 가장 단순한 볼륨 타입으로, 빈 디렉토리로 시작하여 Pod의 수명 동안 데이터를 저장한다
- 컨테이너 재생성(recreate) 시에도 emptyDir의 데이터는 유지되지만, **Pod가 삭제되면 함께 사라진다**
- `medium: Memory`로 tmpfs 볼륨을 생성하면 I/O 성능이 향상되고, 민감한 데이터 저장에도 적합하다
- init 컨테이너를 사용해 emptyDir 볼륨에 초기 데이터를 채울 수 있다. MongoDB의 `/docker-entrypoint-initdb.d/` 같은 메커니즘과 잘 어울린다
- 동일한 emptyDir 볼륨을 여러 컨테이너에 마운트하면 사이드카 패턴, 로그 공유, ML 워크로드 등 다양한 시나리오에서 활용할 수 있다

<br>
