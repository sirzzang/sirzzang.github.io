---
title: "[MLflow] 시스템 메트릭 로깅 - 3. 다른 도구와 런타임의 컨테이너 대응"
excerpt: "컨테이너 안에서 켠 관측 도구가 노드 값을 보여 주는 문제를, 다른 도구와 언어 런타임은 어떻게 다뤘는지 찾아보자."
categories:
  - Dev
toc: true
header:
  teaser: /assets/images/blog-Dev.jpg
tags:
  - MLflow
  - MLOps
  - Container
  - cgroup
  - psutil
  - System-Metrics
  - Observability
last_modified_at: 2026-09-28
---

<br>

# TL;DR

- 컨테이너 안에서 켠 관측 도구가 노드 값을 컨테이너 값처럼 보여 주는 문제는 MLflow만의 것이 아니다. 뿌리는 psutil에 있다
- psutil 이슈는 2022년 4월에 열려 2026년 9월 현재도 열려 있다. 닫히지 않는 이유는 "컨테이너 안에 있는지를 신뢰성 있게 감지할 표준이 없다"는 것이다
- 그래서 psutil 위에 얹힌 도구들이 각자 대응했다. W&B는 2026년 5월에 분모를 cgroup v2 한도로 바꿨고, Ray는 `cgroup_mem`과 `host_mem`을 다른 키로 내보내며, Lightning은 docstring에 "System-wide"라고 적어 이름으로 드러냈다
- 언어 런타임들은 이미 넘어갔다. JVM은 JDK 10, .NET은 GC 힙 상한, Go는 1.25의 `GOMAXPROCS`. 공통 패턴은 컨테이너 인식을 기본으로 켜고 끄는 스위치를 남기는 것이다
- 대응은 어느 층을 고치느냐로 세 갈래다. 도구를 고치거나(cgroup 수집기), 커널 뷰를 고치거나(lxcfs), 밖에서 잰다(cAdvisor → Prometheus)
- [2편]({% post_url 2026-09-23-Dev-MLflow-System-Metrics-Platform-SDK %})에서 플랫폼이 택한 것은 첫째 길이다

<br>

# 들어가며

[1편]({% post_url 2026-09-08-Dev-MLflow-System-Metrics-Container-Isolation %})에서 pod 안에서 켠 MLflow 시스템 메트릭이 무엇을 재는지 따라갔다. MLflow는 시스템 메트릭을 측정하지 않았다. MLflow의 `start_run`을 부른 프로세스 안의 스레드가 psutil로 `/proc` 파일을 읽고 pynvml로 NVML을 부른다. 그런데 `/proc/stat`과 `/proc/meminfo`는 어떤 namespace로도 격리되지 않아서, pod 안에서 열어도 노드 전체 값이 나온다. 실측한 run의 `system_memory_usage_megabytes`는 워커 한도 100 GiB를 넘어 14만 MB까지 올라갔고, 두 계열로 역산한 분모는 그 run이 뜬 노드의 용량과 0.002% 차이로 일치했다.

[2편]({% post_url 2026-09-23-Dev-MLflow-System-Metrics-Platform-SDK %})은 그 위에서 플랫폼 SDK가 한 일이다. 노드를 재는 계열에 `node_`·`rootfs_` 접두를 붙여 이름이 범위를 말하게 하고, cgroup 한도 대비 working set을 재는 `container_` 계열을 더했다. MLflow 원본은 한 줄도 고치지 않고 수집기 리스트라는 확장점에 얹었다.

그런데 이 문제가 MLflow만의 것일 리는 없다. psutil을 쓰는 도구는 전부 같은 자리에 있고, 컨테이너 안에서 자기 한도를 알아야 하는 것은 관측 도구만의 사정도 아니다. 같은 문제가 다른 도구에는 어떻게 있는지, 그리고 어떻게 대응했는지를 찾아봤다. 아래는 2026년 9월 초에 각 프로젝트의 문서·소스·이슈 트래커를 직접 확인한 내용이다. 도구들이 빠르게 바뀌는 영역이라 읽는 시점에는 달라져 있을 수 있으니, 링크에서 현재 상태를 확인하자.

<br>

# psutil의 미해결 이슈

이 문제의 뿌리는 psutil에 있고, psutil은 알고 있다. 2022년 4월에 열린 이슈가 2026년 9월 현재도 열려 있다.

> To my understanding from this ticket (#2100) and #2076, reading `/proc` from within the container returns info about the host and not the container. And that is a problem. I would say it's the container that is at fault here, but anyway.
> — [giampaolo/psutil#2100](https://github.com/giampaolo/psutil/issues/2100), 메인테이너 코멘트 (2024-11)

닫히지 않는 이유도 이슈에 있다. `/sys/fs/cgroup`을 읽자는 제안에 대해 "그 경로는 Docker 전용이고 다른 컨테이너 런타임이 있다", "컨테이너 안에 있는지, 어떤 컨테이너인지를 신뢰성 있게 감지할 표준이 없다"는 반론이 붙어 있다. 2017년에 같은 내용으로 열린 이슈는 2026년 8월에 이 이슈의 중복으로 닫혔다.

psutil이 그대로이니 psutil 위에 얹힌 파이썬 도구들도 그대로다. MLflow에는 2024년 6월에 "컨테이너 안에서 psutil이 노출하는 시스템 메트릭은 학습의 실제 자원 소비를 반영하지 않는다"는 기능 요청([mlflow#12365](https://github.com/mlflow/mlflow/issues/12365))이 열렸고, 메인테이너가 긍정적으로 답했지만 구현은 없다. ClearML의 리소스 모니터와 Aim의 수집기도 `psutil.virtual_memory()`를 그대로 쓴다.

이름이 정직한 예도 있다. Lightning의 `DeviceStatsMonitor`는 docstring에서 `cpu_percent`를 "System-wide CPU utilization (%)", `cpu_vm_percent`를 "System-wide virtual memory (RAM) utilization (%)"으로 적는다. 값은 노드 값이지만 이름이 그렇다고 말한다. HuggingFace Trainer의 메모리 추적은 `psutil.Process().memory_info().rss`, 즉 프로세스 RSS를 본다. 노드도 컨테이너도 아닌 제3의 관점이다.

<br>

# 도구와 런타임의 대응

## 도구별 비교

| 도구 | CPU·메모리 퍼센트의 분모 | 방식 | 확인 기준 |
| --- | --- | --- | --- |
| MLflow | 노드 | psutil 그대로. 키 이름이 `system_`이라 이름은 범위를 말한다 | 3.15 소스 |
| W&B | **cgroup v2 한도** (컨테이너일 때) | 리눅스 컨테이너에서 cgroup v2 한도를 분모로. 옵트아웃 `x_stats_no_cgroup` | v0.27.0, 2026-05 |
| Ray | cgroup 한도 (노드 메모리) / 호스트 (호스트 메모리) | 두 관점을 **다른 함수, 다른 키**로 노출 | master 소스 |
| Lightning | 노드 | psutil 그대로. docstring이 "System-wide"라고 명시 | master 소스 |

## W&B의 cgroup v2 전환

W&B의 변화가 가장 최근이다. 2026년 4월 30일에 머지된 PR이 5월 14일 0.27.0에 들어갔다.

> Changed CPU and memory system metric percentages in Linux containers to use cgroup v2 resource limits instead of host node totals. Set the private `x_stats_no_cgroup` setting to `True` to opt out
> — [wandb CHANGELOG 0.27.0](https://github.com/wandb/wandb/blob/main/CHANGELOG.md)

구현 파일의 머리 주석이 문제를 이 글과 같은 말로 적고 있다.

> This file detects cgroup v2 limits to use as denominators for the system memory and CPU percentages. Without these, a containerized run reports usage as a fraction of the host node, which produces misleading numbers when the cgroup limit is much smaller than the host.
> — [wandb `core/internal/monitor/cgroup.go`](https://github.com/wandb/wandb/blob/main/core/internal/monitor/cgroup.go)

설계 판단 몇 가지가 참고할 만하다. cgroup v1은 의도적으로 지원하지 않는다("v2 has been the default in every major distro for years"). 부모 cgroup이 아니라 프로세스가 실제로 속한 leaf cgroup만 읽는다. 부모의 `memory.current`에는 형제 워크로드가 섞이기 때문이다. CPU는 `cpu.max` 쿼터와 `Cpus_allowed_list`의 크기 중 작은 쪽을 쓴다. 그리고 이 판단의 근거로 Go 런타임을 직접 인용한다("The Go runtime's cgroup-aware GOMAXPROCS makes the same call").

한 가지 눈에 띄는 것은, 코드는 바뀌었는데 문서는 아직이라는 점이다. W&B 시스템 메트릭 레퍼런스는 2026년 9월 기준으로 Memory Percent를 "the total system memory usage as a percentage of the total available memory"로 설명하고 있고, cgroup이나 container라는 단어가 없다. 코드가 고쳐져도 이름과 문서가 따라오지 않으면 사용자는 여전히 오해한다. [2편]({% post_url 2026-09-23-Dev-MLflow-System-Metrics-Platform-SDK %}#범위-접두)에서 지표 이름에 집착한 이유가 여기 있다.

## Ray의 두 관점 분리

Ray는 훨씬 전부터 cgroup을 읽었다. `get_system_memory()`가 `/sys/fs/cgroup/memory/memory.limit_in_bytes`(v1)와 `/sys/fs/cgroup/memory.max`(v2)를 확인하고, 주석에 "Try to accurately figure out the memory limit if we are in a docker container"라고 적어 두었다. Ray의 OOM 방지 메모리 모니터도 이 값을 쓴다. 흥미로운 것은 대시보드 리포터다. `_get_mem_usage()`는 cgroup 기준 총량을, `_get_host_mem_usage()`는 `psutil.virtual_memory()`를 쓰고, 둘을 `cgroup_mem`과 `host_mem`이라는 다른 키로 내보낸다. 두 관점을 이름으로 분리한다는 [2편]({% post_url 2026-09-23-Dev-MLflow-System-Metrics-Platform-SDK %}#범위-접두)의 결론을 Ray는 이미 하고 있었다.

## 언어 런타임의 선례

관측 도구보다 먼저 이 길을 걸은 것은 언어 런타임들이다.

- **JVM**: JDK 10에서 컨테이너 감지와 자원 설정이 들어갔고(JDK-8146115, 8u191에도 백포트) `-XX:+UseContainerSupport`가 기본 on이다. 그 전의 JVM은 힙 크기를 "기계의 물리 메모리"에서 계산했다
- **.NET**: GC 문서가 "If the process runs inside an environment with a set memory limit (for example, a container), that limit is treated as the total physical memory"라고 적는다. 힙 상한 기본값은 그 한도의 75%다
- **Go**: 1.25부터 cgroup CPU 쿼터를 `GOMAXPROCS` 기본값에 반영한다. 공식 블로그는 "Before Go 1.25, Go was unaware of CPU limits set by orchestration platforms. Instead, it would set `GOMAXPROCS` to the number of cores on the machine it was deployed to"라고 적는다. 그 전에는 uber-go/automaxprocs가 사실상 표준이었다
- **Python**: 3.13에서 `os.process_cpu_count()`와 `PYTHON_CPU_COUNT`가 추가됐다. 다만 이것은 CPU affinity(cpuset) 기준이라 `cpu.max` 쿼터는 반영하지 않는다. 메모리 쪽은 psutil 이슈가 열려 있는 채로다

공통 패턴이 하나 보인다. 컨테이너 인식을 기본으로 켜되, 끄는 스위치를 남긴다. JVM의 `-XX:-UseContainerSupport`, W&B의 `x_stats_no_cgroup`, Go의 `GODEBUG=containermaxprocs=0`이 그것이다.

<br>

# 대응의 세 갈래

## 고치는 층에 따른 분기

정리하면 이 문제, 즉 **컨테이너 안에서 켠 관측 도구가 노드 값을 컨테이너 값처럼 보여 주는 것**에 대한 대응은 세 갈래다. 어느 층을 고치느냐로 나뉜다.

| 길 | 무엇을 고치나 | 예 | 맞는 경우 |
| --- | --- | --- | --- |
| **도구를 고친다** | 값을 재는 쪽이 `/proc` 대신 cgroup을 읽게 한다 | W&B의 자체 수집기(cgroup.go), Ray의 `get_system_memory()`, [2편의 cgroup 수집기]({% post_url 2026-09-23-Dev-MLflow-System-Metrics-Platform-SDK %}#cgroup-수집기) | 도구가 내 것이거나 감쌀 수 있을 때 |
| **커널 뷰를 고친다** | 도구는 그대로 두고, 도구가 읽는 `/proc` 파일 쪽을 컨테이너 값으로 바꿔치기한다 | [1편의 원인 절]({% post_url 2026-09-08-Dev-MLflow-System-Metrics-Container-Isolation %}#격리되는-파일-격리되지-않는-파일)에서 언급한 lxcfs. FUSE로 `/proc/meminfo`·`/proc/stat`을 덮어써 cgroup 값을 보여 준다 | 도구를 못 고치고 노드에 손댈 수 있을 때. kubelet이 보는 값과 어긋날 수 있다 |
| **밖에서 잰다** | 프로세스 안에서 재기를 포기하고, 노드의 에이전트가 cgroup을 읽어 다른 저장소에 보낸다 | cAdvisor → Prometheus → Grafana. GPU는 DCGM exporter | 시계열 관측 백엔드가 필요할 때. [1편에서 검토한 Grafana 안]({% post_url 2026-09-08-Dev-MLflow-System-Metrics-Container-Isolation %}#레퍼런스와-검토한-대안)이 이것이다. 실험 화면과는 분리된다 |

첫째 길에서 "도구"는 psutil일 수도 있고 그 위의 관측 도구일 수도 있다. psutil이 cgroup을 읽게 고치는 것이 가장 근본적이지만 [psutil 절](#psutil의-미해결-이슈)에서 본 대로 그 이슈는 4년째 열려 있고, 그래서 그 위의 도구들이 각자 cgroup을 읽는 수집기를 따로 붙였다. 셋째 길은 MLflow의 시스템 메트릭을 쓰지 않는 길이다. MLflow 모니터가 밖의 값을 가져오는 것이 아니라, 관측 자체를 MLflow 밖에 두는 것이다.

## 밖에서 잴 때의 선택

셋째 길을 택할 때 무엇으로 재느냐도 갈린다. `kubectl top`의 데이터 소스인 metrics-server는 README에서 "Metrics Server is meant only for autoscaling purposes. For example, don't use it to forward metrics to monitoring solutions"라고 못 박는다. 순간값을 확인하는 용도이지 시계열 저장소가 아니라는 뜻이다. pod 관점의 시계열은 cAdvisor에서 Prometheus로 가는 라인이 맞다. GPU는 NVML이 장치 파일 격리를 따르므로 컨테이너 안에서 잰 값 자체는 맞지만, 노드에서 밖으로 잴 때는 "이 GPU가 어느 pod 것인가"를 NVML이 모른다. DCGM exporter는 kubelet의 pod-resources API로 그 매핑을 얻어 `pod`·`namespace`·`container` 라벨을 붙인다.

## 실천 원칙

위 조사를 통해 배울 수 있는 실천 원칙은 다섯이다.

1. **컨테이너가 자기 한도를 알아야 하면 `/proc`이 아니라 cgroup에서 읽는다.** 2014년의 글, psutil 메인테이너의 코멘트, Docker `stats`의 구현, kubelet 문서가 전부 같은 말을 한다. [1편의 실측 pod]({% post_url 2026-09-08-Dev-MLflow-System-Metrics-Container-Isolation %}#격리되는-파일-격리되지-않는-파일)에서도 psutil은 540 GB를, cgroup은 64 GiB를 답했다
2. **도구가 container-aware가 아니면, 이름으로 범위를 드러내거나 수집기를 더한다.** Lightning은 docstring에 "System-wide"라고 적어 이름으로 드러냈고, Ray는 `cgroup_mem`과 `host_mem`으로 키를 갈랐으며, W&B는 수집 자체를 cgroup 기준으로 바꿨다. 둘 다 없으면 해석이 사용자 몫으로 남는다
3. **pod 관점의 기준값은 kubelet과 cAdvisor가 쓰는 working set이고, 자체 수집기는 그 값과 맞아야 한다.** kubelet의 eviction 판정이 이 값으로 이뤄진다. 실험 화면과 관측 화면의 숫자가 다르면 사용자가 어느 쪽을 믿을지 판단해야 한다
4. **GPU는 장치 파일 격리를 그대로 쓰되, pod 매핑은 DCGM exporter에 맡긴다.** NVML이 `CUDA_VISIBLE_DEVICES`를 무시하고 장치 파일만 본다는 것은 [1편의 호스트 실측]({% post_url 2026-09-08-Dev-MLflow-System-Metrics-Container-Isolation %}#gpu)이고, 1차 문서로 확인한 것은 아니다
5. **컨테이너 인식은 기본으로 켜고, 끄는 스위치는 남긴다.** JVM의 `-XX:-UseContainerSupport`, Go의 `GODEBUG=containermaxprocs=0`, W&B의 `x_stats_no_cgroup`이 같은 모양이다

<br>

# 정리

조사 결과를 정리하면 셋이다.

1. **이 문제는 도구 하나의 버그가 아니다.** psutil이 그대로이니 그 위의 파이썬 도구들도 그대로다. MLflow의 기능 요청은 2024년부터 열려 있고, ClearML과 Aim도 같은 자리에 있다
2. **관측 도구는 런타임이 걸어간 길을 뒤늦게 걷고 있다.** JVM은 JDK 10에서, Go는 1.25에서 컨테이너 인식으로 넘어갔고, W&B는 2026년에 그 선을 넘었다. 컨테이너 인식을 기본으로 켜고 끄는 스위치를 남긴다는 모양까지 같다
3. **코드를 고쳐도 이름과 문서가 따라오지 않으면 오해는 남는다.** W&B는 수집을 cgroup 기준으로 바꿨지만 레퍼런스 문서에는 아직 cgroup이라는 단어가 없다. 값이 맞아도 이름이 범위를 말하지 않으면 해석은 사용자 몫이다

플랫폼이 택한 것은 첫째 길이다. MLflow 원본을 고치지 않고 감싸서 cgroup 수집기를 더하고, 노드를 재는 계열의 이름에 범위를 드러냈다. 그 설계와 구현은 [2편]({% post_url 2026-09-23-Dev-MLflow-System-Metrics-Platform-SDK %})에 있고, 그 앞의 문제 추적은 [1편]({% post_url 2026-09-08-Dev-MLflow-System-Metrics-Container-Isolation %})에 있다.

<br>

# 참고 자료

- [giampaolo/psutil#2100](https://github.com/giampaolo/psutil/issues/2100) — 컨테이너 안에서 호스트 메모리 보고 (2022-04, open)
- [Fabio Kung, Memory inside Linux containers (2014)](https://fabiokung.com/2014/03/13/memory-inside-linux-containers/)
- [mlflow/mlflow#12365](https://github.com/mlflow/mlflow/issues/12365) — cgroup 메트릭 기능 요청 (2024-06, open)
- [W&B System Metrics](https://docs.wandb.ai/models/ref/python/experiments/system-metrics) — 수집 주기와 지표 정의
- [wandb/wandb#11796](https://github.com/wandb/wandb/pull/11796) — cgroup v2 한도를 분모로 쓰는 변경 (2026-04)
- [wandb CHANGELOG 0.27.0](https://github.com/wandb/wandb/blob/main/CHANGELOG.md)
- [wandb `core/internal/monitor/cgroup.go`](https://github.com/wandb/wandb/blob/main/core/internal/monitor/cgroup.go)
- [Ray `_common/utils.py`](https://github.com/ray-project/ray/blob/master/python/ray/_common/utils.py) — `get_system_memory()`
- [Ray Out-Of-Memory Prevention](https://docs.ray.io/en/latest/ray-core/scheduling/ray-oom-prevention.html)
- [Lightning DeviceStatsMonitor](https://github.com/Lightning-AI/pytorch-lightning/blob/master/src/lightning/pytorch/callbacks/device_stats_monitor.py)
- [lxc/lxcfs](https://github.com/lxc/lxcfs) — `/proc` 파일을 cgroup 값으로 덮어쓰는 FUSE 파일시스템
- [Alibaba Cloud, Using LXCFS to Improve Container Resource Visibility](https://www.alibabacloud.com/blog/kubernetes-demystified-using-lxcfs-to-improve-container-resource-visibility_594109)
- [kubernetes-sigs/metrics-server](https://github.com/kubernetes-sigs/metrics-server) — autoscaling 전용이라는 경고
- [NVIDIA/dcgm-exporter](https://github.com/NVIDIA/dcgm-exporter) — kubelet pod-resources API로 GPU→pod 매핑
- [Kubernetes, Node-pressure Eviction](https://kubernetes.io/docs/concepts/scheduling-eviction/node-pressure-eviction/) — working set 정의
- [Linux cgroup v2 admin guide](https://docs.kernel.org/admin-guide/cgroup-v2.html) — `memory.current`, `memory.max`, `memory.stat`, `cpu.max`, `cpu.stat`
- [Go blog, Container-aware GOMAXPROCS](https://go.dev/blog/container-aware-gomaxprocs), [Go 1.25 release notes](https://go.dev/doc/go1.25)
- [uber-go/automaxprocs](https://github.com/uber-go/automaxprocs)
- [JDK-8146115](https://bugs.openjdk.org/browse/JDK-8146115) — Improve docker container detection and resource configuration usage
- [.NET Runtime configuration options for garbage collection](https://learn.microsoft.com/en-us/dotnet/core/runtime-config/garbage-collector)
- [What's New In Python 3.13](https://docs.python.org/3/whatsnew/3.13.html) — `os.process_cpu_count()`
- [1편: [MLflow] 시스템 메트릭 로깅 - 1. 컨테이너 안에서 잰 값은 누구의 것인가: psutil, 네임스페이스, cgroup]({% post_url 2026-09-08-Dev-MLflow-System-Metrics-Container-Isolation %})
- [2편: [MLflow] 시스템 메트릭 로깅 - 2. 플랫폼 SDK에 얹기: 이름, cgroup 수집기, 원본 무수정 확장]({% post_url 2026-09-23-Dev-MLflow-System-Metrics-Platform-SDK %})

<br>
