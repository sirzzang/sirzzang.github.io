---
title: "[Nsight] Nsight 프로파일러: 2. 실행 환경별 적용"
excerpt: "로컬·컨테이너·쿠버네티스·런타임 exec 환경에서 프로파일러를 붙일 때 마주치는 다섯 가지 문제를 정리해 보자."
categories:
  - Dev
toc: true
use_math: false
header:
  teaser: /assets/images/blog-Dev.jpg
tags:
  - GPU
  - Nsight-Systems
  - Profiling
  - Kubernetes
  - Ray
  - Container
  - Hands-On-LLM-Serving-and-Optimization-Study
  - Hands-On-LLM-Serving-and-Optimization-Study-Week-5
last_modified_at: 2026-09-05
---

*[서종호(가시다)](https://www.linkedin.com/in/gasida99/)님의 Hands-On LLM Serving and Optimization Study (LLMSO) 5주차 학습 중 딥다이브한 내용입니다.*

<br>

# TL;DR

- 측정 원리는 환경이 바뀌어도 그대로다. 환경이 바꾸는 것은 **그 원리를 성립시키기 위해 매번 다시 풀어야 하는 다섯 가지**다. ① 측정기 배치, ② 감쌀 프로세스, ③ 결과 회수, ④ 권한, ⑤ 이웃과 격리
- 로컬에서는 다섯이 전부 자명하다. 컨테이너로 올라가면 ①③④가 새로 생기고, 쿠버네티스로 올라가면 ⑤가 심해진다
- **⑤가 생기는 조건은 쿠버네티스가 아니라 GPU를 남과 나눠 쓰는가다.** 랩 서버나 Slurm 노드에서도 그대로 생긴다. 쿠버네티스가 특별한 것은 어느 노드에 뜰지 고를 수 없어 ⑤를 **피할 수 없게** 만든다는 점이다
- **②가 깨지는 조건도 쿠버네티스가 아니다.** 런타임이 자기 손으로 새 프로세스를 exec할 때 깨지고, 베어 서버에서 `torchrun`만 써도 똑같다. 즉 ②와 ⑤는 3단계 위아래가 아니라 각자 다른 조건에 붙는다
- 그래서 도구 선택도 "①~⑤ 중 몇 개를 대신 풀어주는가"로 비교하면 정리된다. Ray의 `runtime_env`는 ②만 풀고, Nsight Operator는 ①②③을 풀되 클러스터 전역 webhook을 요구하고 `ncu`를 지원하지 않는다
- 권한을 하나도 얻지 못해도 CUDA 트레이스와 NVTX(코드 구간에 이름을 붙이는 주석 API) 트레이스는 그대로 수집된다. 다만 `--sample=none`만 주면 `--cpuctxsw`가 살아 있어 `perf_event_open()`을 계속 부르므로 둘 다 꺼야 한다

<br>

# 배경

[1편]({% post_url 2026-09-03-Dev-Nsight-Profiling-01-Concepts %}#동작-원리)에서 정리한 것은 **`nsys`와 `ncu`가 무엇을 어떻게 관측하는가**, 즉 CUPTI가 대상 프로세스에 붙어 사건을 기록하거나 하드웨어 카운터를 프로그래밍하는 구조였다. 이 구조는 로컬이든 컨테이너든 쿠버네티스든 달라지지 않는다. 그러면 환경이 바꾸는 것은 무엇인가가 이 편의 질문이다.

내가 직접 로컬이나 서버에서 실행할 수 있으면 문제가 간단하다. 하지만 실제로 프로파일링해야 하는 학습·서빙 프로세스는 컨테이너 안에서, 파드로, 스케줄러가 정한 어딘가에서 도는 경우가 많다. ssh로 서버에 들어가 명령을 치는 것과 구조가 다르다. 그래서 CLI 프로파일러를 붙이려면 매번 같은 문제들을 다시 풀게 된다.

> 번호 체계가 둘이라 헷갈리기 쉽다. 1편의 **제약 ①②③**은 측정 원리에서 파생되는 것이고, 이 편의 **적용 문제 ①~⑤**는 환경마다 다시 푸는 것이다. 서로 다른 축이라 이 글에서는 앞의 것을 항상 "제약 ①"처럼 접두어를 붙여 부른다.

<br>

# 적용 문제 다섯

환경에 따라 달라지는 것은 측정 원리가 아니라, 그 원리를 성립시키기 위해 매번 다시 풀어야 하는 **적용 문제** 다섯이다.

| | 로컬·단일 서버 | 컨테이너 | Kubernetes | 런타임이 exec |
| --- | --- | --- | --- | --- |
| **① 측정기 배치**<br>바이너리가 어느 파일시스템에 있어야 하나 | 노드의 PATH | **이미지 안** | 이미지 안 (노드에 넣어도 무의미) | 워커 이미지에도 있어야 |
| **② 감쌀 프로세스**<br>무엇을 감싸야 하나 | 내 명령이 곧 대상 | entrypoint가 대상 | entrypoint가 대상 (**안 깨짐**) | **entrypoint가 대상이 아님** |
| **③ 결과 회수**<br>결과 파일이 어떻게 나오나 | 로컬 디스크 | 컨테이너 FS는 휘발 → bind mount | 파드가 죽으면 소실 → 영속 볼륨 | 워커 N개 → 파일 N개, 이름 충돌 |
| **④ 권한** | 내가 sudo·sysctl | `--cap-add`, `--privileged` | securityContext + **노드 파라미터는 내 소유가 아님** | 워커 파드 spec까지 전파해야 |
| **⑤ 이웃·격리** | 혼자 쓰면 없음 | 혼자 쓰면 없음 | **멀티테넌시 + 배치 비결정성** | 동일 (워커가 여러 노드에 흩어짐) |

표에서 말하는 **노드는 컨테이너를 띄우는 기계**, 즉 [1편의 target]({% post_url 2026-09-03-Dev-Nsight-Profiling-01-Concepts %}#target과-host)이다. 결과를 보는 쪽인 host와는 다른 기계이므로 섞이지 않게 이 편에서는 노드로 부른다.

다섯 밖에도 환경이 얹는 조건이 몇 개 더 있다. GPU를 MPS·MIG·타임슬라이싱으로 나눠 쓰는 노드에서는 권한과 무관하게 카운터 경로 자체가 막히거나 제한되고, 파드가 죽을 때 `terminationGracePeriodSeconds`가 짧으면 `nsys`가 리포트를 마무리하지 못해 **다 맞게 했는데 결과 파일이 없는** 상황이 나온다. `/tmp`를 메모리 백업 emptyDir로 잡아 두면 큰 리포트가 파드를 OOM으로 밀어낼 수도 있다. 아래에서는 다섯 가지에 집중하되, 결과가 안 나올 때 이 셋을 함께 의심할 만하다.

핵심은 **②와 ⑤가 서로 다른 조건에서 생긴다**는 점이다. 쿠버네티스에서 두드러지는 것은 ⑤이고, 런타임 exec에서 생기는 것은 ②다.

다만 표를 계단으로 오해하면 안 된다. **⑤가 생기는 진짜 조건은 "쿠버네티스인가"가 아니라 "그 GPU를 남과 나눠 쓰는가"다.** 8장짜리 랩 서버에 여러 사람이 붙어 있거나, Slurm 노드를 공유하거나, `docker run --gpus all`을 두 번 띄우기만 해도 ⑤는 그대로 생긴다. 위 표의 로컬·컨테이너 칸이 "없음"인 것은 그 단계의 성질이라서가 아니라 혼자 쓰는 경우를 기준으로 적었기 때문이다. 쿠버네티스가 특별한 것은 ⑤를 **피할 수 없게** 만든다는 점이다 — 어느 노드에 뜰지 내가 고르지 않는다.

## 로컬·단일 서버

기준선이다. 다섯이 전부 자명하다.

- ① 노드에 직접 설치한다
- ② 내가 치는 명령이 곧 대상이라 `nsys profile <명령>`으로 끝난다
- ③ `-o`로 로컬 디스크에 떨어진다
- ④ 내가 sudo와 sysctl 권한을 가진다
- ⑤ 사실상 혼자라 경합 걱정이 거의 없다

[1편]({% post_url 2026-09-03-Dev-Nsight-Profiling-01-Concepts %}#열어-볼-리포트-만들기)에서 Colab T4로 리포트를 뜬 것이 이 경우다. Colab이 유독 수월했던 이유도 여기 있는데, root로 돌고(④) 이웃이 없다(⑤).

## 컨테이너

새로 생기는 것은 **①③④**다. ②는 아직 안 깨진다.

**① 측정기 배치.** 노드에 `nsys`가 깔려 있어도 컨테이너 안에서는 보이지 않는다. 이미지 안에 있어야 한다. 넣는 방법은 이미지 빌드 시 설치, NGC(NVIDIA GPU Cloud) 베이스 이미지 사용, 그리고 노드의 설치본을 읽기 전용으로 바인드 마운트하는 방식이 있다. 마지막 방식이 이미지를 다시 빌드하지 않아도 되어 문서가 컨테이너 절에서 기본형으로 쓴다.

```shell
# 노드의 Nsight 설치본을 읽기 전용으로 마운트해서 쓴다
~$ docker run --rm --gpus all --cap-add=SYS_ADMIN \
    -v /opt/nvidia/nsight-systems/2026.2.1:/opt/nvidia/nsight-systems/2026.2.1:ro \
    my-workload:latest \
    /opt/nvidia/nsight-systems/2026.2.1/bin/nsys profile -t cuda,nvtx -o /reports/run_%p python train.py
```

**② 감쌀 프로세스.** 대체로 entrypoint가 곧 대상이라 여전히 감싸면 된다.

**③ 결과 회수.** 컨테이너 파일시스템은 휘발성이라 bind mount로 빼야 한다.

**④ 권한.** 컨테이너는 검사를 하나 더 추가한다. 다만 노드가 내 것이라 sysctl은 직접 조정할 수 있다.

<details markdown="1">
<summary>컨테이너가 추가하는 검사 — seccomp</summary>

**seccomp는 프로세스가 호출할 수 있는 시스템 콜 목록을 커널 수준에서 제한하는 기능이고, Docker와 containerd는 기본 프로파일을 컨테이너에 적용한다.** 컨테이너에서 새로 생기는 것은 이 검사 하나뿐이다. **그리고 드라이버와 커널 검사는 컨테이너 안에서 사라지지 않는다.** 커널을 노드와 공유하므로 `perf_event_paranoid`는 노드 값이 그대로 적용되고, 드라이버는 컨테이너 프로세스의 capability 집합을 본다. 반대로 말하면 컨테이너 안에서 이 둘을 바꿀 방법은 없다.

Docker와 containerd가 적용하는 기본 seccomp 프로파일의 `defaultAction`은 `SCMP_ACT_ERRNO`이고, `perf_event_open`은 컨테이너의 bounding set에 `CAP_SYS_ADMIN` 또는 `CAP_PERFMON`이 있을 때만 허용 목록에 들어간다. `CAP_PERFMON` 단독으로도 허용하게 된 것은 moby 23.0부터이고, 그 이전에는 `CAP_SYS_ADMIN`만 인정했다. Docker가 기본으로 주는 capability 목록에는 둘 다 없다.

여는 방법은 셋인데, **권한을 적게 주는 순서로 보는 편이 낫다.**

```shell
# 방법 1: perf_event_open 만 허용한 커스텀 seccomp 프로파일. 권한 확대가 가장 적다
# default.json 의 syscalls 에 아래 항목을 추가해 저장한 뒤 지정한다
#   {"name": "perf_event_open", "action": "SCMP_ACT_ALLOW", "args": []}
~$ docker run --rm --gpus all --security-opt seccomp=default_with_perf.json my-workload:latest nsys profile ...

# 방법 2: capability 추가. 문서가 권하는 경로지만 SYS_ADMIN 은 범위가 넓다
~$ docker run --rm --gpus all --cap-add=SYS_ADMIN my-workload:latest nsys profile ...

# 방법 3: 전체 권한 부여. 되긴 하지만 마지막 수단이다
~$ docker run --rm --gpus all --privileged=true my-workload:latest nsys profile ...
```

방법 1은 시스템 콜 하나만 열고 capability는 그대로 두므로 드라이버의 카운터 제한은 여전히 닫혀 있다. GPU 카운터까지 필요하면 방법 2로 올라가야 한다.

`--cap-add=SYS_ADMIN` 하나가 서로 다른 세 검사를 동시에 통과시킨다. 컨테이너 seccomp의 허용 조건, 드라이버의 admin 검사, 그리고 배포판 커널의 `perf_event_paranoid` 검사다. 편리한 만큼 범위도 넓어서, 프로파일링 하나를 위해 붙이기에는 과하다는 것이 커널 문서 쪽 입장이다. 대안인 `CAP_PERFMON`은 앞의 둘만 통과시키고, 수정 이전 Ubuntu 커널의 검사는 넘지 못한다. 그 결과가 GPU 카운터는 되고 CPU 샘플링은 안 되는 상태다.

`ncu`는 이 검사와 무관하다. `perf_event_open()`을 쓰지 않으므로 seccomp도 `perf_event_paranoid`도 걸리지 않고, 드라이버 카운터 제한만 통과하면 된다. 컨테이너에서 `ncu`를 쓰는 공식 안내가 "카운터 접근은 컨테이너 밖 노드에서 설정하라"인 이유도 같다.

컨테이너 런타임에 따라 사정이 다르기도 하다. Enroot는 컨테이너를 비특권으로 띄우면서 Docker식 제한적 seccomp 프로파일을 노드 정책 위에 덧씌우지 않아, 추가 플래그 없이 `perf_event_open`이 되는 경우가 많다고 문서가 적는다.

</details>

## 쿠버네티스

새로 생기는 것은 **⑤**이고, ③과 ④가 함께 나빠진다. ②는 여전히 안 깨진다 — 단일 파드 학습 Job이면 entrypoint를 감싸는 것으로 끝난다.

**① 측정기 배치.** 컨테이너와 같다. 노드에 넣어도 무의미하다.

**③ 결과 회수.** 파드 파일시스템은 파드가 죽으면 사라진다. 파드가 마운트하는 것은 PV(PersistentVolume) 자체가 아니라 그것을 요청하는 **PVC(PersistentVolumeClaim)**이므로, 리포트 출력 경로를 PVC나 노드 공유 볼륨으로 빼야 한다.

**④ 권한.** 파드 securityContext로 capability와 privileged는 줄 수 있지만, **노드 드라이버 파라미터와 `kernel.perf_event_paranoid`는 파드 spec으로 바꿀 수 있는 값이 아니다.** 노드 수준 sysctl이라 노드 소유자와의 협의 영역으로 넘어간다. 게다가 파드 spec을 정책으로 검사하는 PSA(Pod Security Admission)에서 baseline 이상이 걸린 네임스페이스라면 `privileged`도 `SYS_ADMIN` 추가도 admission 단계에서 거부된다.

**⑤ 이웃과 격리.** 이 단계의 본질이다.

- 어느 노드에서 돌지 내가 고를 수 없다 (배치 비결정성)
- 그 노드에 이미 `dcgm-exporter` DaemonSet과 남의 파드가 돌고 있다 (멀티테넌시). DCGM(Data Center GPU Manager)은 NVIDIA의 GPU 모니터링 스택이고, `dcgm-exporter`는 그 지표를 Prometheus로 내보내는 컴포넌트다

즉 1편의 **[제약 ①(카운터 배타성)]({% post_url 2026-09-03-Dev-Nsight-Profiling-01-Concepts %}#-카운터-배타성)**이 실제로 터지는 자리가 여기다. GPU 클러스터라면 `dcgm-exporter`가 DaemonSet으로 모든 GPU 노드에서 `DCGM_FI_PROF_*`를 상시 수집하고 있는 경우가 대부분인데, 그러면 카운터를 항상 누가 잡고 있는 상태다. `ncu`나 `nsys --gpu-metrics-devices`를 띄우면 이렇게 끝난다.

```text
==ERROR== Profiling failed because a driver resource was unavailable.
```

조합별로 정리하면 이렇게 갈린다. 판정 기준은 1편에서 본 대로 **[하드웨어 카운터를 프로그래밍하는가]({% post_url 2026-09-03-Dev-Nsight-Profiling-01-Concepts %}#관측-방식-두-가지)** 하나다.

| 조합 | 충돌 | 이유 |
| --- | --- | --- |
| DCGM PROF ↔ `nsys -t cuda,nvtx,osrt` | 없음 | `nsys` 트레이스는 [CUPTI]({% post_url 2026-09-03-Dev-Nsight-Profiling-01-Concepts %}#cupti) Activity라 카운터를 안 쓴다 |
| DCGM PROF ↔ `nsys --gpu-metrics-devices` | 충돌 | 둘 다 카운터 |
| DCGM PROF ↔ `ncu` | 충돌 | 둘 다 카운터 |
| DCGM PROF ↔ `torch.profiler` | 없음 | CUPTI Activity |
| DCGM 비-PROF (이용률·전력·온도) ↔ 아무거나 | 없음 | NVML 경로라 카운터와 무관 |

조치는 DCGM 쪽 프로파일링 지표 수집을 잠시 멈추는 것인데, DaemonSet을 통째로 내리는 방식은 피하는 편이 낫다. 노드 전역으로 지표가 끊기고, GPU Operator가 reconcile로 되돌리며, 무엇보다 프로파일링이 끝난 뒤 되살리는 것을 잊기 쉽다. DCGM은 이 용도로 `dcgmProfPause()`·`dcgmProfResume()` API와 `dcgmi profile --pause`·`--resume`을 제공하므로, **필요한 구간만 일시 정지했다가 되돌리는 쪽**이 안전하다. 일시 정지 동안 프로파일링 지표는 BLANK로 발행된다.

이 표에는 세대 조건이 하나 붙는다. DCGM 문서는 프로파일링 도구와의 충돌을 **A100 및 그 이전** 아키텍처로 한정하고, Hopper 이후에는 모니터링과 프로파일링이 자원을 다투지 않는 경로를 쓴다고 적는다. H100·H200 클러스터라면 위 충돌이 안 날 수 있다는 뜻이다. 다만 데이터센터 라인이 아닌 워크스테이션 계열이 어느 쪽인지는 문서로 확인되지 않으므로, 노드에서 직접 재 보고 판단하는 편이 빠르다.

여기까지가 **이웃이 나를 막는 방향**이다. 반대 방향도 있다. [제약 ②(디바이스 전역 간섭)]({% post_url 2026-09-03-Dev-Nsight-Profiling-01-Concepts %}#-디바이스-전역-간섭)는 **내가 이웃을 망치는** 쪽인데, 이쪽이 운영에서는 더 위험하다. `ncu`는 프로파일링 동안 GPU 클럭을 잠그고 캐시를 비우고 커널을 직렬화하는데, 클럭 락은 GPU 전체에 걸리므로 같은 카드를 쓰는 남의 워크로드까지 함께 느려진다. 게다가 에러가 나지 않아 상대는 알아채지도 못한다. **공유 노드나 운영 노드에서 `ncu`를 돌리지 않는다**는 것이 ⑤에서 나오는 가장 실용적인 규칙이다.

## 런타임이 프로세스를 exec하는 경우

새로 생기는 것은 **②**다. 여기서만 exec 경계가 깨진다.

1편의 **[제약 ③]({% post_url 2026-09-03-Dev-Nsight-Profiling-01-Concepts %}#-exec-경계)**에서 본 대로, CUPTI는 대상 프로세스의 주소 공간에 로드된다. 그래서 `nsys`가 잡는 것은 자기가 exec한 프로세스와 그 자손뿐이다. 문제는 런타임이 자기 손으로 새 프로세스를 띄우는 구조다.

- **Ray** — 각 노드의 raylet(Ray 워커 프로세스를 띄우고 관리하는 데몬)이 워커 액터를 exec한다
- **`torchrun` / `torch.distributed.launch`** — rank별 자식 프로세스를 spawn한다
- **`multiprocessing` spawn** 기반 DataLoader와 DDP
- **gunicorn·uvicorn worker**, **vLLM의 TP worker**

RayJob으로 학습을 돌리는 경우가 알기 쉬운 예다. 일반적인 학습이었다면 `nsys profile`로 학습 프로세스를 감싸면 됐겠지만, RayJob의 `entrypoint`가 띄우는 것은 Ray 드라이버 프로세스다. 이 드라이버가 `ray.init()`으로 클러스터에 붙고 트레이너를 호출하면, Ray가 워커 파드의 raylet에게 액터 생성을 시키고 raylet이 **새 프로세스를 exec한다.** 실제 학습은 그 새 프로세스 안에서 돈다. 따라서 `entrypoint`를 `nsys`로 감싸면 **driver만 잡히고 학습은 안 잡힌다.**

③도 함께 나빠진다. 워커가 N개면 리포트도 N개이고, 출력 경로가 파드 안 임시 디렉터리이면 파드와 함께 사라진다.

중요한 것은 **이것이 쿠버네티스와 직교하는 축**이라는 점이다. 베어 서버에서 `torchrun`만 써도 ②는 똑같이 깨진다. 엄밀히는 3단계(로컬 → 컨테이너 → 쿠버네티스)와 프로세스 모델(단일 exec / 런타임이 exec)의 2차원 구조다. ②가 깨지는 조건은 "쿠버네티스를 쓴다"가 아니라 **런타임이 자기 손으로 새 프로세스를 exec하는가**다.

<br>

# 권한 없이 수집하기

적용 문제 ④를 협의로 푸는 데는 시간이 걸린다. 그동안 아무것도 못 하는 것은 아니다. **드라이버 카운터 제한이 막는 것은 카운터를 프로그래밍하는 기능뿐이고, CUDA 커널 타임라인과 [NVTX]({% post_url 2026-09-03-Dev-Nsight-Profiling-03-Nsys %}#nvtx와-pytorch-자동-주석) 구간은 CUPTI Activity API를 쓰므로 제한 상태에서도 정상 수집된다.** 커널이 언제 시작해 언제 끝났는지, 어디서 동기화로 멈췄는지를 보는 데는 이것으로 충분한 경우가 많다.

남는 것은 커널 쪽 `perf_event_paranoid`다. `nsys`가 대상을 직접 실행하면 `--sample`의 기본값이 `process-tree`라 `perf_event_open()`을 시도하고, 값이 높은 노드에서는 경고가 뜬다. 트레이스 자체는 끝까지 수집되지만 불필요한 시도는 없애는 편이 낫다.

여기에 한 번 걸리기 쉬운 지점이 있다. **`--sample=none`만 주면 안 된다.**

> If set to none, CPU context switch data will still be collected unless the --cpuctxsw switch is set to none.
>
> — Nsight Systems User Guide, `--sample`

`--sample`이 `none`이 아닐 때는 `--cpuctxsw`가 `--sample` 값을 따라가지만, `--sample=none`으로 두면 `--cpuctxsw`는 기본값 `process-tree`로 남는다. 컨텍스트 스위치 추적도 `perf_event_open()` 위에 있으므로 시스템 콜은 계속 호출된다. 둘 다 꺼야 비켜 간다.

```shell
# 권한 없이 CUDA·NVTX 트레이스만 수집. 두 옵션을 모두 꺼야 perf_event_open 을 호출하지 않는다
~$ nsys profile -t cuda,nvtx --sample=none --cpuctxsw=none -o report python train.py
```

이 선택으로 포기하는 것은 CPU 샘플 기반 뷰(Top-Down·Bottom-Up·Flat), 스레드 스케줄링 정보와 CPU 이용률 행, OSRT(OS 런타임) 추적의 blocked 상태 백트레이스, 그리고 CPU 샘플링을 전제로 하는 `--cudabacktrace`와 `--python-backtrace=cuda`다.

반대로 `ncu`에는 이런 우회 경로가 없다. **`ncu`의 커널 분석은 전부 하드웨어 카운터 기반이라, 드라이버 제한을 통과하지 못하면 리포트에 오류만 남는다.** 그래서 권한 협의가 필요한 대상은 `nsys` 트레이스가 아니라 `ncu`와 `nsys --gpu-metrics-devices` 쪽이고, 협의 전까지 할 수 있는 관측은 트레이스 범위로 한정된다.

<br>

# 대안 비교

환경별로 프로파일링을 붙이는 도구가 여럿 있는데, **①~⑤ 중 몇 개를 대신 풀어주는가**로 놓고 보면 비교가 정리된다.

| 해법 | ① 배치 | ② 프로세스 | ③ 회수 | 비고 |
| --- | --- | --- | --- | --- |
| 수동 (entrypoint 감싸기) | 직접 | **실패** (driver만 잡힘) | 직접 | 런타임 exec 환경에서는 부적합 |
| Ray `runtime_env` | 직접 | **해결** | 직접 | 클러스터 설치물 0개 |
| Nsight Operator | 해결 | 해결 | 해결 | 클러스터 전역 webhook 필요, `ncu` 미지원 |

## 수동으로 감싸기

가장 단순하다. entrypoint 앞에 `nsys profile`을 붙인다. 단일 파드 학습 Job이면 이것으로 끝난다. 런타임이 exec하는 환경에서만 ②에서 실패한다.

## Ray runtime_env

Ray는 `runtime_env`에 nsight 키를 공식 지원한다. **Ray 자신이 워커 프로세스를 띄우는 주체이므로, 워커 실행 명령 앞에 `nsys profile`을 붙여 줄 수 있다.** 즉 실제 exec 지점을 갈아끼워 ②를 푸는 방식이다.

```python
# 워커 액터를 nsys 아래에서 띄운다. 학습 코드는 고치지 않는다
runtime_env = {"_nsight": {"t": "cuda,cudnn,cublas,nvtx", "o": "/mnt/shared/nsys/%h_%p"}}
```

Ray 2.48.0 소스를 읽어 확인한 것들을 적어 둔다.

- 내부 플러그인 이름은 `nsight`가 아니라 **`_nsight`**다. `RuntimeEnv(**dict)` 생성자가 `nsight`를 `_nsight`로 매핑해 주므로 실제로는 두 표기 모두 동작하는데, 매핑을 거치지 않는 경로가 생길 여지를 없애려면 `_nsight`로 직접 쓰는 편이 확실하다
- 감싸는 방식은 `py_executable` 교체다. `ray/_private/runtime_env/nsight.py`가 `context.py_executable`을 바꿔 raylet이 워커를 `bash -c "exec nsys profile ... python .../default_worker.py"`로 띄우게 만든다. 액터 하나가 워커 프로세스 하나이므로 rank별로 자동 분리된다
- Ray Train v1의 워커 액터는 `runtime_env`를 따로 지정하지 않는다. 그래서 job 수준에서 준 값을 그대로 물려받는다(자식이 비어 있으면 부모 것을 반환한다)
- **측정기 부재만큼은 조용히 넘어가지 않는다.** `nsys`가 이미지에 없으면 플러그인이 실제로 `nsys profile`을 시험 실행해 보고, 실패하면 `RuntimeEnvSetupError`로 잡을 죽인다. 다만 이건 바이너리가 없는 경우에 한한 이야기다. 아래 알려진 문제처럼 **켜졌는데 리포트가 비는** 실패는 이 검사로 걸리지 않는다

**①과 ③은 여전히 직접 풀어야 한다.** 이미지에 `nsys`가 없으면 위 실패 모드로 잡이 죽고, `-o`를 파드 밖에서 접근 가능한 공유 볼륨 경로로 빼지 않으면 결과가 사라진다. 플러그인이 `-o`를 안 주면 Ray 세션 로그 디렉터리 아래(`/tmp/ray/session_*/logs/nsight/`)에 떨구는데, 차트에서 `/tmp/ray`를 emptyDir로 잡는 경우가 많아 파드와 함께 없어진다.

한 가지 더 있다. **②를 이렇게 풀면 ⑤가 따라온다.** 워커 액터마다 `nsys`가 하나씩 붙으므로 한 노드에 워커가 N개면 프로파일러도 N개가 뜬다. 트레이스만 수집한다면 문제가 없지만 `--gpu-metrics-devices`를 켜는 순간 내 워커들끼리 카운터를 놓고 다툰다. `dcgm-exporter`가 없어도 그렇다. ②와 ⑤가 각자 다른 조건에 붙는다고 했지만, 해법 하나가 다른 문제를 부르는 경로는 이렇게 존재한다.

알려진 문제도 둘 있다. 출력 파일 이름에 붙는 것이 PID(`%p`)뿐이라 어느 워커의 리포트인지 알아보기 어렵고([ray#50711](https://github.com/ray-project/ray/issues/50711)은 액터 이름을 파일명에 넣어 달라는 요청이다, open), 분산 학습 조합에서 리포트가 비거나 엉뚱한 프로세스를 잡는다는 보고가 열려 있다([ray#60904](https://github.com/ray-project/ray/issues/60904), open). 단일 GPU에서 단일 노드, 다시 다노드 순으로 올려 가며 확인하는 편이 안전하다.

## Nsight Operator

NVIDIA가 이 문제에 대해 내놓은 자체 답이다. 컨트롤러와 클러스터 전역 mutating webhook, 노드 sysctl DaemonSet, 오브젝트 스토리지 등 컴포넌트 아홉 종으로 구성되고, **차트를 고치지 않고 프로파일링을 켤 수 있게** 해 준다. mutating admission webhook이 파드에 initContainer(①), 볼륨(③), 프로세스 훅(②)을 주입하고, 정규식으로 프로세스를 매칭해 `nsys` 아래에서 실행시킨 뒤 결과를 업로드한다.

설치해서 검증한 것은 아니고 v26.3.1 문서를 읽어 정리한 내용인데, 판단에 필요한 사실은 이렇다.

- **`ncu`를 지원하지 않는다.** 문서가 `Nsight Operator integrates with Nsight Systems (nsys) only. Other Nsight tools (Nsight Compute...) are out of scope.`라고 명시하고, 기본 제외 패턴에 `ncu`가 들어가 있다
- **Ray·KubeRay 관련 서술이 없다.** 문서 전문에서 관련 키워드가 잡히지 않는다
- 커널 쪽은 DaemonSet으로 노드에 `kernel.perf_event_paranoid`를 써 넣어 푼다. 지원하는 sysctl은 이 하나뿐이다
- **드라이버 쪽은 풀어 주지 않는다.** GPU metrics를 쓰려면 대상 컨테이너에 `privileged` 또는 `SYS_ADMIN`이 필요하다고 문서가 적는다
- 문서가 카운터 경합을 직접 경고한다. `If the NVIDIA GPU Operator's nvidia-dcgm-exporter DaemonSet is active, it must be temporarily disabled during profiling.` 1편의 제약 ①을 오퍼레이터도 피해 가지 못한다는 뜻이다
- 실패 시 영향 범위가 파드 admission 경로 전체다. 기본 제외 네임스페이스는 셋뿐이다

정리하면 **차트가 내 소유가 아닐 때 이득이 큰 도구**다. 차트를 직접 고칠 수 있다면 얻는 것에 비해 들이는 것이 많다. 참고로 예전 Sidecar Injector는 2025년에 이 오퍼레이터로 통합되며 deprecated 됐다.

## Nsight Streamer

적용 문제 ③에 대한 다른 접근이다. 파일을 내 맥으로 내려받는 대신 **클러스터 안에서 뷰어 GUI를 띄우고 브라우저로 접속한다.**

> Nsight Streamer runs the Nsight Systems desktop application inside a container and streams its display to your browser over WebRTC.

1편의 [측정 환경 구성]({% post_url 2026-09-03-Dev-Nsight-Profiling-01-Concepts %}#뷰어를-서비스로-붙이기)에서 본 세 번째 방식이 제품으로 나와 있는 셈이다. 얻는 것은 대용량 리포트를 옮기지 않아도 된다는 점, 서버 자원으로 렌더링한다는 점, 데이터가 클러스터 밖으로 나가지 않는다는 점이다.

배포 경로가 둘인데, 오퍼레이터를 이미 쓰고 있지 않다면 **Docker 컨테이너 단독 경로**가 가볍다. Streamer 하나 때문에 클러스터 전역 webhook을 들일 이유는 없다. 걸리는 점도 몇 가지 있다. 오퍼레이터 경로의 Streamer는 리포트를 오브젝트 스토리지에서 읽어서 공유 볼륨에 떨군 리포트를 그대로 열지 못하고, 기본 자격증명이 그대로 두면 안 되는 값이며, GPU 가속 인코딩은 Ada Lovelace 이상을 요구한다(소프트웨어 렌더링은 항상 되지만 느리다).

리포트를 내려받는 데 불편이 없는 동안은 이득이 없다. **파일 크기가 병목이 될 때** 꺼내드는 카드로 두는 편이 적절하다. 이 절도 오퍼레이터와 마찬가지로 문서를 읽어 정리한 내용이고 직접 띄워 보지는 않았다.

<br>

# 정리

이번 편에서 정리한 것을 한 표로 모은다.

| 항목 | 내용 |
| --- | --- |
| 축 | 환경이 바꾸는 것은 측정 원리가 아니라 적용 문제 ①~⑤ |
| 컨테이너 | ①③④가 새로 생긴다. 추가되는 검사는 seccomp 하나 |
| Kubernetes | ⑤가 새로 생기고 ③④가 나빠진다. ②는 안 깨진다 |
| 런타임 exec | ②가 깨진다. 3단계와 직교하는 축 |
| 제약 ①과의 접점 | `dcgm-exporter`가 상시 도는 노드에서 카운터 경로만 막힌다 |
| 권한 없이 | CUDA·NVTX 트레이스는 수집된다. `--sample=none --cpuctxsw=none` |
| 도구 선택 | Ray `runtime_env`는 ②만, Nsight Operator는 ①②③ |

가장 자주 헷갈리는 지점을 한 번 더 적어 둔다. **쿠버네티스를 쓴다고 해서 감쌀 프로세스 문제가 생기는 것이 아니다.** 단일 파드 학습 Job이면 entrypoint를 감싸는 것으로 끝난다. ②가 깨지는 것은 런타임이 자기 손으로 새 프로세스를 exec할 때이고, 그건 베어 서버에서도 일어난다. 반대로 ⑤는 쿠버네티스에서만 생긴다. 증상을 보고 어느 쪽인지 먼저 가르면 손댈 곳이 정해진다.

다음 편에서는 `nsys`를 실제로 돌리면서 옵션과 리포트 읽는 법을 정리한다.

<br>

# 참고 링크

- [Nsight Systems User Guide](https://docs.nvidia.com/nsight-systems/UserGuide/index.html)
- [Nsight Operator Documentation](https://docs.nvidia.com/nsight-operator/)
- [Nsight Streamer Documentation](https://docs.nvidia.com/nsight-operator/NsightStreamer/index.html)
- [Ray — Profiling with Nsight Systems](https://docs.ray.io/en/latest/ray-observability/user-guides/profiling.html)
- [ray#50711 — Ray nsight 리포트 파일명에 액터 이름 요청](https://github.com/ray-project/ray/issues/50711)
- [ray#60904 — nsys profiling issues with distributed training](https://github.com/ray-project/ray/issues/60904)
- [moby/moby — default seccomp profile (v24.0.0)](https://github.com/moby/moby/blob/v24.0.0/profiles/seccomp/default.json)
- [DCGM Feature Overview — Concurrent Usage of NVIDIA Profiling Tools](https://docs.nvidia.com/datacenter/dcgm/latest/user-guide/feature-overview.html)
- [Nsight 프로파일러: 1. 개념과 동작 원리]({% post_url 2026-09-03-Dev-Nsight-Profiling-01-Concepts %})

<br>
