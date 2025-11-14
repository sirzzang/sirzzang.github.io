---
title:  "[Kubernetes] Kubernetes Deployment 재배포 실패 원인과 해결 - 1. 스케쥴링"
excerpt: Kubernetes에서의 파드 스케쥴링 전략에 대해 알아 보자
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



~~도대체 거의 1년 가까이 된 내용을 왜 이제서야 작성하게 되었는지 반성하며~~ 회사에서 Deployment를 재배포하다가 쿠버네티스에서의 스케쥴링과 Deployment 업데이트 전략에 대해 공부하게 된 내용을 작성한다.



<br>



# 문제

회사에서 객체 인식 모델로 추론한 객체 Bbox를 트래킹하기 위해 Boost 트래커를 사용하고 있다. 해당 컴포넌트는 GPU를 이용하기 때문에 GPU 노드에 배치되어 있고, Deployment로 배포되어 있다. 클러스터 내에 해당 목적으로 사용하기 위한 노드를 정해 두었다(이하 '`트래커노드`'라고 칭한다). 배포와 관련된 상세 사항은 다음과 같다.

- 해당 노드에서만 실행될 수 있도록, `nodeSelector`로 해당 노드명을 사용해서 배치하고 있다.
- 해당 노드에 GPU가 1개이기 때문에, `replicas` 값은 1로 설정되어 있다.



<br>



해당 트래커 서빙 코드를 수정할 일이 있어서, 수정한 뒤 Deployment를 재배포했다. 근데 실패했다.

```bash
$ kubectl get pods -n <namespace> -l app=<namespace>-object-tracker
NAME                                          READY   STATUS        RESTARTS   AGE
<namespace>-object-tracker-7d59fb84b9-rj7mt   1/1     Running       0          17h
<namespace>-object-tracker-7fbf4cd6cf-d4bwb   0/1     Pending       0          5m31s
```



<br>

Pending 상태에 놓여 있는 파드의 이벤트를 확인해 보니, 해당 파드의 스케쥴링에 실패했음을 알게 되었다.

```bash
Events:
  Type     Reason            Age                    From               Message
  ----     ------            ----                   ----               -------
  Warning  FailedScheduling  6m                     default-scheduler  0/10 nodes are available: 1 Insufficient nvidia.com/gpu, 9 node(s) didn't match Pod's node affinity/selector. preemption: 0/10 nodes are available: 1 No preemption victims found for incoming pod, 9 Preemption is not helpful for scheduling..
  Warning  FailedScheduling  4m18s (x2 over 4m30s)  default-scheduler  0/10 nodes are available: 1 Insufficient nvidia.com/gpu, 9 node(s) didn't match Pod's node affinity/selector. preemption: 0/10 nodes are available: 1 No preemption victims found for incoming pod, 9 Preemption is not helpful for scheduling..

```

<br>

처음에는 막연히 `nodeSelector`로 해당 노드명을 걸어 놓고, 재배포하려면 GPU가 1개밖에 없으니까 안 되는 게 아닐까 생각했다. 한편으로는 맞는 말이기도 하지만, 더 자세히 고찰해 볼 것이 너무나도 많은 사태였다. 



결과적으로, **문제는 Deployment 배포 시 업데이트 전략을 명확하게 설정하지 않았기 때문**에 발생한 것이었다. 그러나 이 문제의 원인을 더 정확하게 파악하기 위해서는 Deployment 배치 전략과 스케쥴링 전략에 대해 자세히 알아야 한다. 

<br>





# 스케쥴링



## 개념



Kubernetes 스케쥴링이란, **Kubernetes 스케쥴러가 파드를 적합한 노드에 배치하는 프로세스**를 의미한다. 조금 더 정확하게는, 생성된 파드를 클러스터 내 어느 노드에서 실행할지 결정하고 할당하는 과정이다. 더 상세한 개념을 말해 보라면,

- `kube-scheduler`가 Pending 상태의 파드를 감지하여,
- (후술할) 필터링과 스코어링(과 필요하다면 선점)을 통해 최적의 노드를 선택하고,
- 해당 노드에 파드를 바인딩하는 일련의 프로세스

라고 할 수 있지 않을까 싶다.

<br>



[공식 문서](https://kubernetes.io/docs/concepts/scheduling-eviction/kube-scheduler/)는 아래와 같이 정의한다.

> In Kubernetes, scheduling refers to making sure that Pods are matched to nodes so that Kubelet can run them.

Kubelet이 실행할 수 있도록, 파드가 노드에 매치되게 하는 작업이란다. 정의에서도 확인할 수 있지만, 스케쥴링은 순전히 **배치** 작업일 뿐이다. 아래와 같은 작업은, 스케쥴링이 아니다.

- 파드 생성 그 자체: Deployment의 경우, Deployment Controller가 담당
- 파드 실행: Kubelet 담당. Scheduler는 어디서 실행할지만 결정
- 리소스 할당: Linux cgroups/namespaces가 담당

그리고 이와 같은 스케쥴링에 포함될 수 있는 작업의 범위는 다음과 같다:

- 노드 선택
- (선택했다면) 파드와 노드 연결
- (필요시) 선점을 통해 기존 파드 종료

또한, 당연히 스케쥴링은 **파드**에 적용되는 개념이다. Deployment, Statefulset 등과 같은 리소스 컨트롤러에 적용되는 개념이 아니라는 의미다.

<br>



## 대상

Pending 상태의 파드를 감지했을 때 스케쥴링이 진행된다는 것을 전제로, 궁금한 것이 하나 생긴다. *모든 Pending 상태의 Pod가 스케쥴링 대상이 되는가?* 으레 짐작할 수 있겠지만, **그렇지 않다**. 

 <br>

Pending 상태라는 것은 광범위하게 지칭한 것으로, 엄밀히 말하면 `status.phase`이다. 그런데 쿠버네티스에서 모든 파드는 조건을 가지고 있다. 파드 매니페스트에서 `status.conditions`로 확인해 볼 수 있다. 

```yaml
apiVersion: v1
kind: Pod
metadata:
  name: my-pod
spec:
  nodeName: "" # 비어 있음 
status:
  phase: Pending # 파드 상태 Pending
  conditions: # 파드 Condition
  - type: PodScheduled 
    status: "False"  
    reason: Unschedulable
    message: "0/10 nodes available: 1 Insufficient gpu"
```

<br>

이 조건 중에는 `PodScheduled`라는 타입의 조건이 있는데, 이것이 해당 파드가 스케쥴링되었는지 아닌지를 나타내는 것이다. 스케쥴러는 `PodScheduled` 조건의 값이 `False`인 값을 대상으로 스케쥴링을 시도한다. 만약, 현재 클러스터에서 확인해 보고 싶다면, 아래와 같이 확인해 보면 된다.

```bash
$ kubectl get pods --all-namespaces \
  -o jsonpath='{range .items[?(@.status.conditions[?(@.type=="PodScheduled")].status=="False")]}{.metadata.name}{"\n"}{end}'
```

> 참고: 실제로 더 권장되는 방법
>
> 사실 이론적으로는 PodScheduled 조건 값을 통해 찾으면 될 것 같으나, 실무적으는 특수 케이스가 존재하기 때문에 `nodeName`이 비어있는 것을 찾는 게 더 좋다고 한다. 파드가 스케쥴링되지 않았을 때에만 `nodeName`이 비어 있어야 할 것 같은데, 아주 아주 예외적으로 해당 조건 값이 `True`이지만ㅡ `nodeName`이 비어 있는 경우도 있다고 한다.  ~~물론, 이건 파보고 파보다 찾게 된 Claude 피셜이기 때문에, 내 눈으로 확인한 적은 없다. 어쨌든~~ 더 엄밀하게 확인해 보고 싶다면 아래와 같이 확인할 것!
>
> ```bash
> # 또는 nodeName이 비어있는 파드
> $ kubectl get pods --all-namespaces \
>   -o jsonpath='{range .items[?(@.spec.nodeName=="")]}{.metadata.name}{"\n"}{end}'
> ```

<br>

결과적으로, Kubernetes에서 파드가 Pending 상태(Phase)가 될 수 있는 경우는 다양하다.

- 새로 생성되어 스케쥴링 대기 중일 때
- 스케쥴링된 후 컨테이너 시작 대기 중일 때
- 스케쥴링 실패 후 재시도 중일 때
- 노드에 장애가 났을 때
- ...

더 자세히 보자면 파드 상태에 대한 고찰이 필요하겠으나, 일단 지금은 스케쥴링 관점에서만 집중하기 위해, **Pending 상태인 파드 중 스케쥴링이 되지 않은 파드**가 스케쥴링 프로세스의 대상이 된다고 알아 두자.



<br>



## 메커니즘

스케쥴러는 스케쥴링 대상인 파드를 감지하기 위해, 타이머와 이벤트를 이용한다. 특정 시간 간격으로 스케쥴링을 시도하고(~~스케쥴러의 스케쥴링?~~), 또 클러스터 내 특정 이벤트가 발생하면 바로 스케쥴링을 시도하는 것이다. 어쨌든 클러스터 내에서는 이렇게 스케쥴러가 스케쥴링을 시도하고, 실패한 파드들에 대해 특정 시간 간격을 두고 재시도하는 루프가 무한 반복되는 것이다.

<br>

이를 위해 Kubernetes 스케쥴러는 아래와 같이 3개의 큐를 관리한다.

- Active Queue: 활성 큐. 즉시 스케쥴링 시도할 파드들
  - 새로 생성된 파드
  - Backoff Queue에서 타이머 만료된 파드
  - Unschedulable Queue에서 조건 충족된 파드
- Backoff Queue: 백오프 큐. 일시적으로 스케쥴링에 실패한 파드들
  - 지수 백오프(exponential backoff) 타이머 대기 중
  - **일시적 실패**: 스케줄링 시도는 가능했으나 실패한 경우
    - 리소스가 약간 부족 (CPU 90% 사용 중)
    - 노드가 일시적으로 NotReady 상태
    - 다른 파드가 먼저 리소스를 선점함
  - 초기 1초부터 시작하여 점진적으로 증가 (2초, 4초, 8초... 최대 약 10초)
  - **지수 백오프를 사용하는 이유**:
    - 스케줄러 부하 감소: 즉시 재시도하면 CPU 낭비
    - 클러스터 상태 변경 대기: 리소스 확보 등을 위한 시간 확보
    - 시스템 안정성: 초기에는 빠르게 재시도하되, 계속 실패하면 간격을 늘림
- Unschedulable Queue: 스케쥴 불가 큐. 현재 클러스터 구조상 스케쥴링이 불가능한 파드들
  - **구조적 실패**: 클러스터 상태 변경이 필요한 경우
    - 배치 가능한 노드가 없음
      - 모든 노드가 `nodeSelector` 불일치
      - taint/toleration 불일치로 배치 가능한 노드가 없음
    - 요청한 PV가 아예 존재하지 않음
    - 요청한 GPU 타입이 클러스터에 없음
  - **빠져나오는 조건**: 클러스터 이벤트 발생 시 Active Queue로 이동
    - 노드 추가/변경 (라벨, taint 등)
    - PV/PVC 생성
    - 다른 파드 삭제 (affinity 조건 변경)
    - 리소스 증가 이벤트

<br>

결국, 백오프 타이머에 의해 정기적으로 아래와 같은 스케쥴링 루프가 동작하게 된다.

```
Pending 파드 발견
    ↓
스케줄링 시도
    ↓
실패 → Scheduling Queue에 다시 추가
    ↓
특정 조건/시간 후 재시도
    ↓
(무한 반복)
```

<br>

그리고, 무한 반복 루프 외에 스케쥴링을 트리거하는 아래와 같은 이벤트가 발생하면, 즉시 재시도가 트리거링된다:

- 노드 추가, 변경: 새 노드 추가, 노드 리소스 증가, 노드 레이블 변경
- 파드 종료: 기존 파드 삭제, 기존 파드 종료, 리소스 확보
- PV, PVC 변경: 새 볼륨 생성, 볼륨 바인딩 완료
- Service/Configmap 변경: 관련 리소스 업데이트



<br>

## 프로세스

그렇게 스케쥴링이 시작되면, 아래와 같이 작동한다.

![kubernetes-scheduling]({{site.url}}/assets/images/kubernetes-scheduling.png){: width="500"}{:. align-center}

- 일반 스케쥴링: 클러스터 내에서 대상 파드를 배치할 수 있는 노드 탐색
  - 필터링: 각 노드 별로 모든 노드 조건에 대해 만족하는지 확인. 하나라도 실패 시 탈락
    - 리소스
    - `nodeSelector` 일치 여부
    - node affinity/anti-affinity 여부
    - taint/toleration 적합 여부
    - 볼륨 마운트 가능 여부
    - 포트 충돌 유무
    - ...
  - 스코어링: 필터링을 통과한 노드들에 대하여 점수 부여 후, 가장 높은 점수의 노드를 선택함
    - 리소스 밸런싱
    - pod anti-affinity
    - 이미지가 해당 노드에 이미 존재하는지 여부
    - ...
  - 바인딩: 선택된 노드에 파드 배치
- 선점: 일반 스케쥴링 실패 시, 우선순위 기반으로 기존 파드를 강제로 종료 후 대상 파드 배치

<br>

> 참고: 스코어링 단계에서 동점인 노드가 여러 개 있는 경우
>
> 스코어링 단계에서 당연히 동점 노드가 발생할 수 있는데, 이 경우 랜덤 선택, 라운드 로빈, 노드 이름 순서 등의 방법을 통해 선택한다고 한다. 동점이 발생하는 게 좋은지 나쁜지는, 생각을 해 봐야겠지만. 만약 노드들이 대부분 비슷한 조건을 가졌다면, 해당 클러스터에서는 동점이 많이 나오는 게 당연할 수 있고, 오히려 그 경우 스케쥴러에게 적절히 맡기는 게 나을 것이라는 생각이 든다. 그런데 만약 그렇지 않은 클러스터에서 동점이 많이 나온다면, 그건 문제가 있지 않을까.
>
> 물론, 동점이 나온 걸 어떻게 파악하는가에 대해서는 조금 더 공부해 봐야 한다. 일단 지금은 여기까지만!

<br>

즉, 일반 스케쥴링 단계에서 모든 노드에 대한 필터링과 스코어링을 거쳐 파드를 배치할 노드를 찾아 내고, 그것에 실패할 경우, 선점을 진행하는 것이다. 크게 아래와 같이 진행된다고 봐도 무방하다.

1. 필터링: 모든 노드 동시 체크
2. 스코어링: 필터링 통과한 노드에 대해 점수 부여
3. 바인딩: 선택된 노드에 파드 배치
4. 선점: 모든 노드에 대해 필터링이 실패했을 경우 시도

<br>

### 선점

[공식 문서](https://kubernetes.io/docs/concepts/scheduling-eviction/pod-priority-preemption/)에서는 이렇게 설명한다.

> Pods can have priority. Priority indicates the importance of a Pod relative to other Pods. If a Pod cannot be scheduled, the scheduler tries to preempt (evict) lower priority Pods to make scheduling of the pending Pod possible.

다시 말해, 우선 순위가 더 높은 파드를 위해 더 낮은 우선 순위 파드를 종료하는 것이다. 선점이라고 하니 뭔가 해당 파드가 뺏어 가는 것 같지만, 공식 문서 맥락을 보면, 더 낮은 우선 순위의 파드를 종료하는 것 뿐이다. 그렇게 되면, 우선순위가 더 높은 파드가 스케쥴링될 수 있을 테니.

<br>

우선 순위에 따라 결정한다는 것이 중요하다. 즉, 선점이 이루어지기 위해서는 우선 순위가 있어야 한다.

- priorityClass 리소스를 정의해야 함

  ```yaml
  ---
  apiVersion: scheduling.k8s.io/v1
  kind: PriorityClass
  metadata:
    name: high-priority
  value: 1000000
  globalDefault: false  # true로 설정하면 priorityClassName 미지정 파드의 기본값으로 사용됨 (클러스터당 1개만 가능)
  preemptionPolicy: PreemptLowerPriority  # PreemptLowerPriority: 낮은 우선순위 파드 선점 가능 / Never: 선점하지 않음
  description: "High priority pods"
  ---
  apiVersion: scheduling.k8s.io/v1
  kind: PriorityClass
  metadata:
    name: low-priority
  value: 1000
  globalDefault: false
  description: "Low priority pods"
  ```

- 기존 파드와 우선 순위 대상 파드에 해당 priorityClass가 적용되어 있어야 함

  ```yaml
  apiVersion: v1
  kind: Pod
  metadata:
    name: nginx
    labels:
      env: test
  spec:
    containers:
    - name: nginx
      image: nginx
      imagePullPolicy: IfNotPresent 
    priorityClassName: high-priority
  ```



<br>

 대부분, 파드를 그 자체로 띄우진 않으니, Deployment와 같은 리소스 컨트롤러에 우선 순위를 적용한다. 그런데, 중요한 것은, 같은 리소스 컨트롤러에서 생성된 파드는 같은 우선 순위를 갖는다는 것이다. 그래서 실제로 우선 순위에 의한 파드 선점이 동작하는 경우는 거의 드물다고 한다. 생각해 보면 그럴 수밖에 없다. priorityClass를 명시적으로 정의하고, 리소스 컨트롤러마다 정의해 줘야 하며, 그런 상황에서 클러스터 리소스가 빡빡하게(?) 운영되는 상황이어야 발생할 수 있을 테니까. ~~솔직히 일단 priorityClass를 정의하고 관리해줘야 한다는 것 자체가 부담일 수도 있을 것 같다~~



<br>
