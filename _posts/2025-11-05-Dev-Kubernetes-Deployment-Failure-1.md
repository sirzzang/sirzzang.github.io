---
title:  "[Kubernetes] Kubernetes Deployment 재배포 실패 원인과 해결 - 1. Deployment 업데이트 전략"
excerpt: Kubernetes Deployment 업데이트 전략과 재배포 실패 문제 상황을 알아보자.
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

<br>

# TL;DR

- GPU가 1개뿐인 노드에 `nodeSelector`로 고정 배치한 Deployment를 업데이트했더니 새 파드가 Pending 상태에 빠졌다. 
- 원인은 `strategy`를 명시하지 않아 RollingUpdate 기본값(`maxSurge: 25%` → 1, `maxUnavailable: 25%` → 0)이 적용되면서, 새 파드를 먼저 띄우려 했지만 GPU가 이미 점유 중이라 스케줄링에 실패한 것이다.
- 이 글에서는 문제 상황과 Deployment 업데이트 전략(`Recreate`, `RollingUpdate`)의 동작 방식을 알아본다.

<br>

# 들어가며

~~도대체 거의 1년 가까이 된 내용을 왜 이제서야 작성하게 되었는지 반성하며~~ 회사에서 Deployment를 재배포하다가 쿠버네티스에서의 스케줄링과 Deployment 업데이트 전략에 대해 공부하게 된 내용을 작성한다.



<br>



# 문제

회사에서 객체 인식 모델로 추론한 객체 Bbox를 트래킹하기 위해 Boost 트래커를 사용하고 있다. 해당 컴포넌트는 GPU를 이용하기 때문에 GPU 노드에 배치되어 있고, Deployment로 배포되어 있다. 클러스터 내에 해당 목적으로 사용하기 위한 노드를 정해 두었다(이하 '`트래커노드`'라고 칭한다). 배포와 관련된 상세 사항은 다음과 같다.

- 해당 노드에서만 실행될 수 있도록, `nodeSelector`로 해당 노드명을 사용해서 배치하고 있다.
- 해당 노드에 GPU가 1개이기 때문에, `replicas` 값은 1로 설정되어 있다.



<br>



해당 트래커 서빙 코드를 수정할 일이 있어서, 수정한 뒤 Deployment를 업데이트했다. 근데 실패했다.

```bash
$ kubectl get pods -n <namespace> -l app=<namespace>-object-tracker
NAME                                          READY   STATUS        RESTARTS   AGE
<namespace>-object-tracker-7d59fb84b9-rj7mt   1/1     Running       0          17h
<namespace>-object-tracker-7fbf4cd6cf-d4bwb   0/1     Pending       0          5m31s
```



<br>

Pending 상태에 놓여 있는 파드의 이벤트를 확인해 보니, 해당 파드의 스케줄링에 실패했음을 알게 되었다.

```bash
Events:
  Type     Reason            Age                    From               Message
  ----     ------            ----                   ----               -------
  Warning  FailedScheduling  6m                     default-scheduler  0/10 nodes are available: 1 Insufficient nvidia.com/gpu, 9 node(s) didn't match Pod's node affinity/selector. preemption: 0/10 nodes are available: 1 No preemption victims found for incoming pod, 9 Preemption is not helpful for scheduling..
  Warning  FailedScheduling  4m18s (x2 over 4m30s)  default-scheduler  0/10 nodes are available: 1 Insufficient nvidia.com/gpu, 9 node(s) didn't match Pod's node affinity/selector. preemption: 0/10 nodes are available: 1 No preemption victims found for incoming pod, 9 Preemption is not helpful for scheduling..

```
<br>

처음에는 막연히 `nodeSelector`로 해당 노드명을 걸어 놓고, 재배포하려면 GPU가 1개밖에 없으니까 안 되는 게 아닐까 생각했다. 한편으로는 맞는 말이기도 하지만, 더 자세히 고찰해 볼 것이 너무나도 많은 사태였다. 



결과적으로, **문제는 Deployment 배포 시 업데이트 전략을 명확하게 설정하지 않았기 때문**에 발생한 것이었다. 그러나 이 문제의 원인을 더 정확하게 파악하기 위해서는 Deployment 배치 전략과 스케줄링 전략에 대해 자세히 알아야 한다. 

> *참고*: 스케줄링에 대한 자세한 내용은 별도로 정리한 [쿠버네티스 스케줄링 - 1. 개념]({% post_url 2025-11-05-Kubernetes-Scheduling-01 %})과 [쿠버네티스 스케줄링 - 2. 프로세스와 선점]({% post_url 2025-11-05-Kubernetes-Scheduling-02 %}) 글을 참고하자.

<br>

간단히 말해, 쿠버네티스 스케줄링이란 **스케줄러가 파드를 적합한 노드에 배치하는 프로세스**다. 스케줄러는 모든 노드를 대상으로 필터링(Filter)과 스코어링(Score)을 수행하여 최적의 노드를 선택하고, 모든 노드가 필터링에서 탈락하면 선점(Preemption)을 시도한다. 선점마저 실패하면 파드는 Unschedulable Queue로 이동하여, 클러스터 상태가 변경될 때까지 Pending 상태에 머문다.


<br>





# Deployment 업데이트

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: rolling-update-deploy
spec:
  replicas: 2
  strategy: # 파드 배포 전략
    type: RollingUpdate
    rollingUpdate:
      maxUnavailable: 1
      maxSurge: 1
```

Kubernetes는 Deployment 리소스 타입에 대해 파드 배포 전략(`strategy`)으로 아래의 2가지를 지원한다. 어떤 전략을 선택하든, 배포가 끝나면, `replicas`에 명시된 수만큼의 파드가 떠 있을 것이다.

- `Recreate`: 현재 실행 중인 모든 파드를 종료하고, 새로운 파드를 생성
  - 서비스 중단 발생
- `RollingUpdate`: 파드를 점진적으로 교체
  - 배포 과정에서 새로운 버전의 파드가 생성되고, 기존 파드가 종료됨으로써 무중단 업데이트 가능
    - 새로운 버전의 파드 생성 및 기존 파드의 종료를 설정값으로 조정
  - 기본값



<br>

## RollingUpdate

RollingUpdate 전략은 점진적인 파드 업데이트를 위해 아래와 같은 두 가지 값을 설정할 수 있게 한다.

- `maxSurge`: 업데이트 시 동시에 새로 생성(*surge라는 단어를 참 센스 있게 사용한 느낌이다*)할 수 있는 파드 수

  ```yaml
  maxSurge: 3          # 정확히 3개
  maxSurge: 30%        # 30%(소수점일 경우 올림)
  maxSurge: "30%"      # 문자열로도 가능
  ```

  - 숫자나 퍼센티지 사용 가능
  - 퍼센티지일 경우, `replicas` 값에 곱하고, 곱한 결과가 소수점일 경우 올림
  - 퍼센티지 계산 한 최종값이 `replicas` 값을 초과하는 경우, `replicas` 값 적용
  - 기본값 25%

- `maxUnavailable`: 업데이트 시, 동시에 종료할 수 있는 파드 수

  ```yaml
  maxUnavailable: 3          # 정확히 3개
  maxUnavailable: 30%        # 30% (소수점일 경우)
  maxUnavailable: "30%"      # 문자열로도 가능
  ```

  - 숫자나 퍼센티지 사용 가능
  - 퍼센티지일 경우, `replicas` 값에 곱하고, 곱한 결과가 소수점일 경우 내림
  - 퍼센티지 계산 한 최종값이 `replicas` 값을 초과하는 경우, `replicas` 값 적용
  - 기본값 25%

<br>

그렇다면, 해당 값들의 설정에 따라 Deployment의 배포는 어떻게 동작할까.

|                        | maxSurge = 0                                            | maxSurge > 0                                                |
| ---------------------- | ------------------------------------------------------- | ----------------------------------------------------------- |
| **maxUnavailable = 0** | 1. 불가                                                 | 2. 새 파드 먼저 생성하고, 기존 파드는 새 파드 Ready 후 종료 |
| **maxUnavailable > 0** | 3. 기존 파드 먼저 종료하고, 리소스 확보 후 새 파드 생성 | 4. 2, 3의 경우가 모두 가능하고, 상황에 따라 선택됨          |

1. 애초에 불가능한 경우다. 이럴 거면 배포를 안 하는 거랑 다름이 없으니 굳이 케이스를 열어 둘 필요가 없다.
2. 항상 새 파드를 먼저 생성하고, 종료할 수 있는 파드가 없기 때문에, 파드 수는 `replicas` 값 이하로 내려가지 않는다.
3. 항상 기존 파드를 먼저 종료하기 때문에, 파드 수는 `replicas` 값 이상으로 올라가지 않는다.
4. 배포 과정에서 이론 상  `[replicas - maxUnavailable, replicas + maxSurge]` 범위 내의 파드 수가 존재할 수 있다.
   - 최대 파드 수 = `replicas + maxSurge` → 기존 파드 수 유지하면서 최대로 생성할 수 있는 파드 수를 더함
   - 최소 파드 수 = `replicas - maxUnavailable` → 기존 파드 수에서 최대로 종료할 수 있는 파드 수를 뺌
   - 이론 상, 최소 파드 수가 0이 되는 순간이 가능하므로, 이 경우 서비스 다운타임이 올 수 있음

> *참고*: 이론 상 최소 파드 수가 0이 된다면?
>
> - 이 경우에는 애초에 다운타임이 있기 때문에  `Recreate`를 선택하는 게 낫지 않나 싶을 수 있으나, 그런 것만은 아니다. 그건 **이론상 가능한 경우**로 항상 발생하는 것은 아니기 때문이다.
> - 다만, 다운타임이 있어도 되는 서비스라면, 이런 경우가 올 수 있더라도 크게 걱정하지 않아도 될 것이다. 사실 이 경우는 그런데, 차라리 `Recreate`를 선택하는 게 오히려 관리 상 더 편할 수 있다.
> - 애초에 `replicas` 값을 설정하고 Deployment로 배포한다는 것 자체가 무중단 운영을 전제로 한 건데, 이 상태에서 이론적으로 최소 파드 수가 0이 될 수 있게 Rolling Update Strategy를 설계하면, 그게 이상한 거 아닐까 싶기도 하다.



> *참고*: 설정 기본값에 대한 생각
>
> 두 항목 모두 기본값이 25%인데, 이는 확장성을 고려했기 때문이라고 한다. 당장 생각해 봐도 알 수 있다. `replicas` 값이 적으면 상관 없겠지만, 만약 100일 때 `maxSurge`가 1이라면, 항상 1개씩만 새로 생성될 테니, 한 세월이 걸릴 것이다.
>
> 올림과 내림을 적용하는 전략이 다른 것은, 아무래도 보수적으로 접근하기 위함이 아닐까. `maxSurge`를 내리고 `maxUnavailable`을 올리면, 디폴트 상황에 0과 1이 적용되어 다운타임이 발생할 수밖에 없으니까.



<br>

다양한 조합에 따른 배포 상황을 알아 보자.

```yaml
# 최대: 13개, 최소: 10개
replicas: 10
maxSurge: 25%        # 2.5 -> 3(올림) 생성 가능
maxUnavailable: 0    # 중단 불가
```

```yaml
# 최대: 13개, 최소: 8개
replicas: 10
maxSurge: 25%        # 2.5 -> 3(올림) 생성 가능
maxUnavailable: 25%  # 2.5 -> 2(내림) 중단
```

```yaml
# 최대 1개, 최소 0개 (순차 교체)
replicas: 1
maxSurge: 0          # 생성 불가
maxUnavailable: 1    # 중단 가능
```

```yaml
# 최대 2개, 최소 1개
replicas: 1
maxSurge: 1          # 생성 가능
maxUnavailable: 0    # 중단 불가
```


<br>


## 배포 전략

언제나 그러하듯, 상황에 따라 적합한 배포 전략을 선택해야 한다.

* `Recreate`는 무조건 다시 만드는 것이기 때문에, 다운타임이 존재할 수밖에 없음
  * 다운타임이 중요하다면, 선택하면 안 됨
  * 반대로, 다운타임이 크게 중요하지 않다면, 적용해 볼 수 있음
    * 개발 환경, 테스트 환경
    * 다운타임이 허용 가능한 내부 도구
  * 또한, 이런 환경에는 적용하는 것을 고려해야 함
    * 애초에 노드에 리소스 제약이 있어서, 해당 노드에서 여러 개의 파드를 띄울 수 없는 경우
    * 상태를 엄밀하게 저장해야 해서, 여러 개의 파드가 떠서 다른 상태를 저장해 버리면 안 되는 경우

* `RollingUpdate`는 잘 설계한다면 다운타임이 없음
  * 다음과 같은 상황에 적합함
    * 프로덕션 환경에서의 무중단 서비스로, 점진적 배포가 필요한 상황
    * 로드 밸런서로 트래픽을 분산해야 하는 상황
  * 그 외에, 이런 상황에서도 고려해볼 수 있음
    * 리소스에 여유가 있는 상황
    * 상태 저장이 필요 없는 파드

> 어떤 것이 권장된다는 것은 없으나, 기본값이 `RollingUpdate`인 것도 그렇고, Kubernetes를 도입해야 하는 상황 자체가, 다운타임이 생기면 안되는 경우일 가능성이 높기 때문에, `RollingUpdate`를 선택하는 것이 좋지 않을까

<br>

## 기타

Deployment 배포 전략 외에, 추가적으로 Deployment 배포 시 고려해 볼 수 있는 항목들이 있다. 있다는 걸 알아만 두자.

- `minReadySeconds`: 파드 Ready 상태가 된 후 최소 대기 시간
  - 새 파드가 Ready 상태가 된 후, 정말 안정적인지 확인하기 위함
  - 파드가 CrashLoopBackOff 상태에 빠지는 것을 방지하기 위함
- `progressDeadlineSeconds`: 배포 타임아웃
  - 해당 시간 안에 배포하지 못하면 실패 처리
  - 기본 600초
- ...



<br>

# 결론

Deployment 업데이트 시 `strategy`를 명시하지 않으면 기본값인 `RollingUpdate`가 적용되며, `maxSurge`와 `maxUnavailable` 역시 기본값 25%가 설정된다. `replicas: 1`인 경우 이 기본값은 올림/내림에 의해 `maxSurge: 1`, `maxUnavailable: 0`이 되어, **새 파드를 먼저 생성한 뒤 기존 파드를 종료**하는 방식으로 동작한다. 리소스가 제한된 환경에서는 이 기본 동작이 문제가 될 수 있으므로, 배포 전략을 반드시 명시적으로 설정해야 한다.

<br>

---

다음 글에서는 이 Deployment 업데이트 전략과 스케줄링 개념을 바탕으로, **실제 문제를 분석하고 해결**해 본다. [다음 글 보기]({% post_url 2025-11-05-Dev-Kubernetes-Deployment-Failure-2 %})

<br>
