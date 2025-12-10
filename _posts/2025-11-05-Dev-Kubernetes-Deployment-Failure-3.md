---
title:  "[Kubernetes] Kubernetes Deployment 재배포 실패 원인과 해결 - 3. 분석 및 해결"
excerpt: Kubernetes에서의 Deployment 재배포는 왜 실패했을까
categories:
  - Dev
toc: true
header:
  teaser: /assets/images/blog-Dev.jpg
tags:
  - k8s
  - k3s
  - kubernetes
  - deployment
  - scheduler
---



~~도대체 거의 1년 가까이 된 내용을 왜 이제서야 작성하게 되었는지 반성하며~~ 회사에서 Deployment를 재배포하다가 쿠버네티스의 스케줄링과 Deployment 업데이트 전략에 대해 공부하게 된 내용을 작성한다.



<br>

# 분석

돌고 돌아, 다시 처음으로 가 보자. 내 소중한(?) 트래커 파드는 왜 Pending 상태에 갇혀 있었으며, 왜 내 Deployment 배포는 실패했는가.

<br>

Deployment 매니페스트를 보자.

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: <namespace>-object-tracker
  namespace: <namespace>
  labels:
    app: <namespace>-object-tracker
spec:
  replicas: 1
  selector:
    matchLabels:
      app: <namespace>-object-tracker
  template:
    metadata:
      labels:
        app: <namespace>-object-tracker
    spec:
      containers:
      - name: <namespace>-object-tracker
        image: <namespace>/boost-track-app:1.0
        imagePullPolicy: Always
        env:
        - name: MAX_AGE
          value: "30" # int
        - name: MIN_HITS
          value: "3" # int
        - name: IOU_THRH
          value: "0.3" # 0 ~ 1 float
        - name: USE_ECC # cache
          value: "true" # true / false
        - name: USE_EMBEDDING # reID
          value: "true" # true / false
        ports:
        - containerPort: 8004
        command: ["/bin/bash" , "-c"]
        args:
        - |
          uvicorn app.main:app --host 0.0.0.0 --port 8004
        resources:
          limits:
            nvidia.com/gpu: 1 # gpu 필요
      nodeSelector:
        kubernetes.io/hostname: <`트래커노드`>
---
apiVersion: v1
kind: Service
metadata:
  name: <namespace>-object-tracker
  namespace: <namespace>
spec:
  type: NodePort
  selector:
    app: <namespace>-object-tracker
  ports:
  - port: 8004
    targetPort: 8004
    nodePort: 30006
```



<br>

이제 보인다.
- strategy가 명시되지 않았으므로, `RollingUpdate` 전략을 사용함
- `RollingUpdate` 전략 설정값이 `maxSurge`, `maxUnavailable` 값이 명시되지 않았으므로, 각각 기본값인 25%가 설정됨

<br>

실제로, 해당 Deployment를 확인해 보니, 그렇더라.

```bash
$ kubectl describe deployment -n <namespace> <namespace>-object-tracker
Name:                   <namespace>-object-tracker
Namespace:              <namespace>
CreationTimestamp:      Fri, 26 Sep 2024 15:04:38 +0900
Labels:                 app=<namespace>-object-tracker
Annotations:            deployment.kubernetes.io/revision: 4
                        field.cattle.io/publicEndpoints: [{"port":30006,"protocol":"TCP","serviceName":"<namespace>:<namespace>-object-tracker","allNodes":true}]
Selector:               app=<namespace>-object-tracker
Replicas:               1 desired | 1 updated | 2 total | 1 available | 1 unavailable
StrategyType:           RollingUpdate # strategy
MinReadySeconds:        0
RollingUpdateStrategy:  25% max unavailable, 25% max surge # rolling update 항목
...
```

<br>

그럼 어떻게 업데이트가 시도될까. 당연히 아무 것도 설정하지 않아 기본값이 설정되니, 계산해 보면 아래와 같다.
- `maxSurge`: 1 * 0.25 = 0.25이므로, 올림하여 1로 설정됨
- `maxUnavailable`: 1 * 0.25 =0.25이므로, 내림하여 0으로 설정됨

그러니, 내 상황에서는 **일단 새로운 파드를 생성하고 난 뒤에**, 기존 파드가 종료될 것이다. 

<br>
그리고 새로운 파드를 생성하려고 할 때는 스케줄링 프로세스를 따를 것이다. 스케줄러에 빙의해 보자. 
- 필터링: 모든 노드를 살펴 본다
  - `트래커노드`: 탈락
    - `nodeSelector`, cpu, memory 등 다른 조건은 만족했을 수 있음
    - gpu 1개 필요하나, 이미 기존 파드가 점유 중이므로 **탈락**
  - 그 외 노드: 애초에 `nodeSelector` 단계부터 **탈락**
- 선점: 모든 노드에 대해 필터링이 실패했으니 선점 전략을 써보려 한다
  - `트래커노드`: 불가
    - Deployment 내 파드들은 우선순위가 동일하기 때문에, 기존 파드를 종료할 수 없음
  - 그 외 노드: 선점 전략을 시도해 보려 해도, 애초에 `nodeSelector`가 안 맞으니, 선점을 시도해 봐야 의미가 없음

<br>

## 에러 메시지 분석

여기까지 왔으면, 에러 메시지가 읽힌다. ~~다시 읽어보니 어찌나 잘 쓴 메시지인지~~

> 0/10 nodes are available: 1 Insufficient nvidia.com/gpu, 9 node(s) didn't match Pod's node affinity/selector. preemption: 0/10 nodes are available: 1 No preemption victims found for incoming pod, 9 Preemption is not helpful for scheduling..

* `0/10 nodes are available: 1 Insufficient nvidia.com/gpu, 9 node(s) didn't match Pod's node affinity/selector.`: 10개 노드 중 어디에도 파드를 배치할 수 없음
  * 일반 스케줄링 실패 이유에 대한 분류
    * 1 Insufficient nvidia.com/gpu: 1개 노드에서 GPU가 부족함 → `트래커노드`. nodeSelctor는 만족하지만, GPU 리소스가 부족
    * 9 node(s) didn’t match Pod’s node affinity: 9개 노드에서는 `nodeSelector` 불일치 
  * 즉, `nodeSelector`를 해당 노드로 걸어 놨으니까, 다른 노드들은 당연히 `ndoeSelector` 불일치이고, 일치하는 노드에 파드 배치하려고 봤더니 GPU가 부족하다
* `preemption: 0/10 nodes are available: 1 No preemption victims found for incoming pod, 9 Preemption is not helpful for scheduling..`: preemption을 시도해 봤으나, 그렇게 해서도 파드를 배치할 수 없음
  * 선점 실패 이유에 대한 분류
    * 1 No preemption victims found for incoming pod: 배치하려는 새 파드(incoming pod)를 위해 희생시킬 파드가 없음
      - 기존 파드와 새 파드가 우선순위가 같기 때문
    * 9 Preemption is not helpful for scheduling: 다른 노드는 선점을 해 봤자, 도움이 안 된다(not helpful) → 다른 노드에서 preemption에 의해 아무리 파드를 종료해서 리소스를 확보해도, `nodeSelector` 조건 때문에 거기에 배치할 수가 없다
  * 즉, 선점으로 해보려고 해도 불가능하다
* 즉, 일반적인 방식으로 스케줄링하고, 필요하면 preemption해야 하는데, 불가능하다!



<br>

# 해결



## 대안

그럼 이 상황을 어떻게 해결할 수 있을까. 원리를 아니까, 이제는 간단하다.

- 노드 필터링 조건 변경
  - `nodeSelector` 변경
  - node affinity 추가
  - ...
- 해당 노드의 가용 GPU 자원 늘려 주기
  - 물리적으로 GPU를 더 달기
  - Time Slicing을 적용하기
  - (가능하다면) MIG를 적용하기
- 업데이트 전략 변경
  - `Recreate`
  - `RollingUpdate`를 쓰되, `maxSurge`를 0으로, `maxUnavailable`을 1로 명시적으로 설정하기

<br>

## 채택

사실 트래커의 경우, 다운타임이 생겨도 문제가 없는 상황이다. 또한, 어차피 GPU를 1개 점유하는데, 다른 노드들의 GPU는 이 노드보다 더 사양이 좋아 더 무거운 작업에 사용해야 하기 때문에 굳이 다른 노드에서 띄울 이유도 없다. 그러니, 기존 파드를 종료하고 새 파드가 뜨게 하는 방안을 택했다.

`Recreate`를 선택해도 되지만, 나중에 GPU를 논리적으로 분할(time slicing)하여 사용하려고 했었기 때문에, 확장성 측면에서 `RollingUpdate`를 선택하기로 했다. 대신, 배포 매니페스트에 주석을 잘 달았다.

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: <namespace>-object-tracker
  namespace: <namespace>
  labels:
    app: <namespace>-object-tracker
spec:
  # NOTE: 현재 해당 노드에 가용 GPU 1개 뿐이므로, replicas를 1로 설정함
  replicas: 1
  strategy:
    type: RollingUpdate
    # NOTE: 현재 해당 노드에 가용 GPU 1개 뿐이므로, maxSurge를 0으로 설정해야 함.
    # 추후 가용 GPU 늘 경우, 아래 값 조정 필요
    rollingUpdate:
      maxSurge: 0        # 추가 파드 생성 안함
      maxUnavailable: 1   # 기존 파드 먼저 종료 허용
```





<br>

# 결과

배포 후 재시작해주었더니 잘 동작한다. 혹시나 이전에 스케줄링에 실패 중이던 파드가 Pending 상태로 남아 있을 수 있기 때문에, `kubectl rollout restart`로 재시작해주는 게 좋다.

```bash
$ kubectl apply -f tracker-deployment.yaml
$ kubectl rollout restart deployment -n <namespace> <namespace>-object-tracker
```



<br>

## 더 생각해 볼 점

- 애초에 이렇게 GPU가 제한되어 있는데 `nodeSelector`를 쓴 게 잘못 아닐까?
  - 내 상황에서는, 노드셀렉터를 쓴 거 자체가 잘못이라기 보다는, Deployment 배포 전략을 잘못 채택한 게 잘못이었다고 봐야 함
  - 배포 전략을 명확히 설정하지 않아 잡혔던 기본값이, 해당 노드의 제한된 리소스와 맞지 않았던 것
- `nodeSelector`를 사용하여 배포하는건 오히려 스케줄러의 선택의 폭을 줄여서 안 좋은 게 아닐까?
  - 상황에 따라 다름
  - 그리고 오히려, 다음의 경우는 `nodeSelector`를 명시적으로 사용하는 게 도움이 됨
    - GPU 모델 지정
    - 특정 노드 라이센스 제약
    - 대용량 데이터셋이 있는 노드
    - 워크로드 격리가 필요한 경우
  - 내 상황의 경우, 애초에 팀 내에서 해당 노드에 트래커를 띄우기로 했으니 그러려니 하지만, 만약 트래커가 다른 노드의 GPU에서 구동되어도 무방한 상황에 이렇게 `nodeSelector`를 설정했다면, 그 경우엔 다시 생각해 볼 필요가 있음



