---
title:  "[Dev] Pod CPU Limit과 FFmpeg Thread 최적 조정 - 5. 결론: CPU Limit을 설정하지 않기로 한 이유"
excerpt: "튜닝 실험 결과를 종합하고, CPU limit 설정에 대한 고민과 최종 결정을 정리해 보자."
categories:
  - Dev
toc: true
header:
  teaser: /assets/images/blog-Dev.jpg
tags:
  - Kubernetes
  - FFmpeg
  - CPU
  - cgroup
  - throttling
  - 리소스관리
---

<br>

지금까지의 여정을 되돌아보면, 출발점은 단순했다. "K8s Pod에서 ffmpeg이 37배 느리다." 원인을 파악하고, 튜닝하고, 최적값을 찾으면 되겠지 싶었다. 하지만 실험을 거듭할수록 다른 질문이 떠올랐다.

**애초에 CPU limit을 설정하는 게 맞는 걸까?**

<br>

# 실험이 보여준 것

## CPU limit이 CPU-bound 워크로드에 미치는 영향

| 시리즈 글 | 확인한 것 |
|----------|----------|
| [4.0]({% post_url 2026-02-06-Dev-FFmpeg-CPU-04-00 %}) | CPU limit 1 core에서 37배 느림. limit 해제 시 즉시 회복 |
| [4.1]({% post_url 2026-02-06-Dev-FFmpeg-CPU-04-01 %}) | 85% period에서 throttling 발생, 대기 시간이 작업 시간의 2배 |
| [4.3]({% post_url 2026-02-06-Dev-FFmpeg-CPU-04-03 %}) | CPU limit 증가는 비선형적. 5~7 core Dead Zone 존재 |
| [4.4]({% post_url 2026-02-06-Dev-FFmpeg-CPU-04-04 %}) | limit = threads 명시 시 선형 확장. 병렬 처리 한계 ~10 core |

실험 결과를 종합하면, CPU limit은 이 워크로드에 대해 **"시간을 나눠 쓰게 하되, 나눠 쓰는 방식이 비효율적"**인 제약이었다.

<br>

## 튜닝은 가능하지만, 유지는 어렵다

[4.4]({% post_url 2026-02-06-Dev-FFmpeg-CPU-04-04 %})의 실험에서 limit = threads로 명시 지정하면 Dead Zone을 회피하고 선형 확장이 가능하다는 것을 확인했다. 이론적으로는 이렇게 하면 된다:

1. CPU limit을 적정값으로 설정
2. ffmpeg `-threads`를 limit에 맞춰 명시 지정
3. Dead Zone(5~7 core) 회피

하지만 실무에서 이것을 유지하는 것은 다른 문제다.

- **Kubernetes manifest와 애플리케이션 코드 두 곳을 동기화해야 한다.** CPU limit을 바꾸면 `-threads` 값도 함께 바꿔야 한다.
- **서버 환경이 바뀌면 최적값도 바뀐다.** 이번 실험은 20 core 서버에서 진행했는데, 다른 사양의 노드로 이동하면 Dead Zone 구간이나 병렬 처리 한계가 달라질 수 있다.
- **그때마다 이런 실험을 반복할 수는 없다.** 이번 실험만 해도 수십 번의 측정과 분석이 필요했다.

물론 이를 자동화하는 방법이 없는 것은 아니다. cgroup에서 CPU limit을 읽어 threads를 동적으로 결정하는 wrapper를 만들거나, Downward API로 limit 값을 주입하는 방식이 가능하다. 하지만 이것은 **CPU limit이 만든 문제를 우회하기 위해 복잡성을 추가하는 것**이다.

<br>

## 그래도 설정한다면: 코어 수만 보면 된다

만약 조직 정책이나 멀티테넌트 환경 등의 이유로 CPU limit을 설정해야 하는 상황이라면, 고려해야 할 변수가 많아 보이지만 실제로는 **코어 수**가 지배적이다.

영상 처리에 영향을 줄 수 있는 변수를 나열하면:

| 변수 | 영향도 | 비고 |
|------|--------|------|
| **CPU 코어 수** | **높음** | 병렬 처리 능력을 직접 결정 |
| CPU 아키텍처/클럭 | 낮음 | 같은 코어 수에서 차이 ±5% 수준. ffmpeg이 SIMD 등 아키텍처별 최적화 내장 |
| 영상 코덱/해상도 | - | ffmpeg 내부에서 자동 조정. `-threads` 수만 적절하면 됨 |

이 워크로드에서는 single-thread 성능보다 **병렬 처리 능력**(코어 수)이 처리 시간을 결정한다. 실험에서도 코어 수에 따라 처리 시간이 거의 선형으로 변했고, CPU 세대 차이(i7-12700F vs i9-7900X)는 추이 자체를 바꾸지 못했다.

또한 이 서비스의 출력은 고정(1280x720 JPEG 프레임)이다. 입력 영상의 코덱이나 해상도가 다양하더라도, ffmpeg이 내부적으로 디코딩/스케일링 전략을 조정하므로 threads 수까지 직접 관여할 필요는 없다. 코어 수에 맞춰 threads를 설정하면 나머지는 ffmpeg에 맡겨도 충분하다.

정리하면, limit을 설정해야 한다면:
1. **노드의 코어 수를 기준으로 limit 결정** (실험에서 확인한 Phase별 특성 참고)
2. **`-threads`는 limit과 동일하게 명시 지정** (auto에 맡기지 않기)
3. **Dead Zone(5~7 core) 회피**

<br>

# CPU limit을 설정하지 않기로 한 이유

## 워크로드 특성

이 워크로드(ffmpeg 프레임 추출)는 전형적인 **CPU-bound burst 워크로드**다.

- 요청이 들어오면 짧은 시간 동안 CPU를 집중적으로 사용한다
- 처리가 끝나면 CPU를 거의 쓰지 않는다 (idle)
- 처리 시간이 곧 사용자 경험이다 (빠를수록 좋다)

이런 특성의 워크로드에 CPU limit을 거는 것은, [배경지식]({% post_url 2026-02-06-Dev-FFmpeg-CPU-02 %})에서 다룬 것처럼 **유휴 CPU가 있는데도 강제로 대기시키는** 결과를 낳는다. request만 적절히 설정하면 CFS가 경합 상황에서 공정하게 배분하므로, limit 없이도 다른 Pod에 대한 "시끄러운 이웃" 문제는 관리할 수 있다.

<br>

## 시작은 일반적 예제였다

[첫 번째 글]({% post_url 2026-02-06-Dev-FFmpeg-CPU-00 %})에서 언급했듯, 처음 CPU limit을 `1000m`으로 설정한 것은 웹 서비스/API 서버의 일반적 예제를 참고한 것이었다. 당시에는 ffmpeg이 얼마나 CPU를 쓰는지, 멀티스레드로 동작하는지조차 몰랐다.

지금 돌아보면, 워크로드 특성을 파악하지 않고 "일반적 예제"를 그대로 가져다 쓴 것이 문제의 출발점이었다. 영상 처리 워크로드는 웹 서비스와 근본적으로 다르다.

<br>

## 최적값을 찾는 것이 불가능하다

CPU는 [배경지식]({% post_url 2026-02-06-Dev-FFmpeg-CPU-01 %})에서 다룬 것처럼 **시간을 나눠 쓰는 자원**이다. 같은 4 core limit이라도, 노드의 다른 워크로드 상태에 따라 실제 사용 가능한 CPU 시간이 달라진다. "이 서버에서 이 영상으로 측정한 최적값"이 다른 환경에서도 최적이라는 보장이 없다.

결국, 이 워크로드에 대해서는 **CPU limit을 설정하지 않고, request만 설정하여 Burstable로 운영**하기로 했다.

> 처음에는 limit을 설정하지 않는 것에 부담이 있었다. "제한 없이 Pod가 노드 CPU를 전부 잡아먹으면 어떡하지?"라는 걱정이었다. 하지만 시리즈를 진행하면서 CFS의 shares 기반 공정 배분, request의 역할, limit의 한계를 이해하고 나니, limit 없이 운영하는 것이 이 워크로드에서는 더 합리적인 선택이라는 확신이 생겼다.

<br>

# 대신 해야 할 것

CPU limit을 제거한다고 끝이 아니다. limit이 없으면 throttling이라는 "안전장치"가 사라지는 것이므로, **모니터링과 관찰이 더 중요해진다.**

<br>

## CPU 사용량 추이 관찰

[4.2]({% post_url 2026-02-06-Dev-FFmpeg-CPU-04-02 %})에서 구성한 Grafana 대시보드를 활용하여:

- 요청 처리 시 CPU 사용량이 노드 전체에 비해 얼마나 차지하는지
- 영상 길이/해상도에 따라 CPU 사용 패턴이 어떻게 달라지는지
- 피크 시간대에 동시 요청이 몰릴 때의 양상

을 지속적으로 관찰해야 한다.

<br>

## 다른 워크로드에 대한 영향 확인

현재 백엔드 레플리카가 3으로 설정되어 있다. 영상 처리 요청이 동시에 들어오면 3개 Pod이 동시에 CPU를 burst할 수 있고, 같은 노드의 다른 서비스에 영향을 줄 수 있다.

- 같은 노드에 배치된 다른 Pod들의 성능 변화 관찰
- 필요하다면 nodeAffinity나 taint/toleration으로 영상 처리 Pod을 전용 노드에 격리
- request를 적절히 설정하여 스케줄러가 노드 용량을 정확히 판단하도록 유도

<br>

## request 적정값 설정

limit은 제거하지만 **request는 반드시 설정**해야 한다. request가 없으면 [BestEffort QoS](https://kubernetes.io/docs/concepts/workloads/pods/pod-qos/#besteffort)가 되어 노드 리소스 압박 시 가장 먼저 축출(eviction)된다.

request 적정값은 운영 환경에서 limit을 제거한 뒤, 실제 CPU 사용량 추이를 관찰하여 결정해야 한다. Grafana 대시보드의 `container_cpu_usage_seconds_total` 메트릭으로 p50~p90 사용량을 확인하고, 이를 기준으로 설정한다. VPA(Vertical Pod Autoscaler)를 recommendation 모드로 배포하면 적정값을 추천받을 수도 있다.

<br>

# 더 생각해 볼 것

이번 시리즈에서 CPU limit 문제는 해결했지만, 그 과정에서 더 근본적인 질문들이 떠올랐다.

<br>

## 영상 처리 SLA와 리소스 투자의 균형

CPU limit을 제거하면 처리 속도는 빨라지지만, "어느 정도면 충분한가"에 대한 기준은 아직 없다. 모든 영상을 길이의 1/10 안에 처리한다든지, 절대적으로 N초 안에 처리한다든지, 서비스 신뢰도를 위한 SLA가 필요하다. 사용자에게 영상 처리 진행을 보여줄 때, "얼마나 기다리게 할 것인가"는 서비스 경험에 직결되기 때문이다.

이번 실험 데이터가 이 판단의 근거가 될 수 있다. [4.4]({% post_url 2026-02-06-Dev-FFmpeg-CPU-04-04 %})의 limit = threads 실험 결과를 SLA 관점에서 다시 보면:

| SLA 목표 | 필요한 코어 수 | 리소스 비용 |
|----------|-------------|-----------|
| 3~4초 이내 | 12+ core | 높음 |
| 10초 이내 | 10 core | 중간 |
| 15초 이내 | 9 core | 중간 |
| 20초 이내 | 8 core | 낮음 |
| 25초 이내 | 4 core | 최소 |

만약 서비스 관점에서 "10초면 충분하다"는 판단이 나온다면, 12코어를 줄 필요 없이 10코어로 괜찮다. 4초와 10초 사이에 코어 2개 차이가 있고, 그 2개의 코어는 다른 Pod에 줄 수 있다. SLA를 정의하면 **리소스 투자의 상한선**이 생기는 셈이다.

그런데 SLA를 아무리 넉넉하게 잡아도 충족하지 못하는 순간이 올 수 있다. 실험에서 확인했듯 이 워크로드는 CPU-bound이므로, **코어 수를 늘리면 성능은 올라간다**. 하지만 서버를 무한정 키울 수는 없다. 그 지점에서 선택지는 두 가지다.

1. **서버 확장**: 코어 수를 늘리거나, 전용 노드를 배치하거나, 더 빠른 CPU 사양의 서버를 도입한다. 비용이 직접적으로 증가한다.
2. **코드/파이프라인 최적화**: ffmpeg 옵션 최적화(`-preset`, 해상도 조정), GPU 디코딩(`-hwaccel`), 영상 분할 병렬 처리 등 애플리케이션 레벨에서 효율을 높인다.

지금까지의 시리즈는 1의 영역(서버 리소스 관점)에서 문제를 해결했다. 하지만 이것만으로 SLA를 영원히 충족할 수는 없고, 결국 2의 영역도 함께 고민해야 하는 시점이 올 것이다. 어디까지가 서버로 해결할 영역이고, 어디부터가 코드로 해결할 영역인지 — 그 균형점을 찾는 것이 다음 과제다.

<br>

## 아키텍처 분리를 고려해야 하는 시점

이 고민의 근본적인 원인을 생각해 보면, **백엔드 API 서버에 영상 처리 로직이 들어 있다는 것** 자체가 문제의 출발점이다.

원래 백엔드가 영상 처리를 담당한 데에는 이유가 있었다. 영상에서 추출한 프레임을 뒷단의 여러 컴포넌트가 참조하는데, 각자 추출하면 동일한 결과를 보장할 수 없다. 사용자와 맞닿아 있는 백엔드에서 프레임을 추출하여 single source of truth를 만드는 것이 합리적인 설계였다.

하지만 이번 경험을 통해 느낀 것은, 영상 처리 로직이 포함되어 있다는 이유만으로 **백엔드 전체의 워크로드 특성이 달라져 버린다**는 점이다.

- 백엔드 API 자체는 일반적인 웹 서비스 워크로드다 (I/O-bound, 낮은 CPU 사용)
- 영상 처리는 CPU-bound burst 워크로드다
- 두 가지가 하나의 Pod에 있으면, **영상 처리 기준으로 리소스를 설정해야** 한다
- 그러면 영상 처리가 없는 대부분의 시간에 리소스가 낭비되고, 백엔드 스케일링도 제약된다

워크로드 성격이 다른 로직을 분리하는 것 — 예를 들어 영상 처리를 별도 Job이나 Worker로 떼어내는 것 — 이 근본적인 해결이 될 수 있다. 분리하면 백엔드는 경량으로 유지하면서 많이 복제할 수 있고, 영상 처리는 필요할 때만 리소스를 할당받을 수 있다.

물론 아키텍처 분리에는 비용이 따른다. 비동기 처리 흐름 설계, 메시지 큐 도입, 프레임 저장소 관리 등 새로운 복잡성이 생긴다. 하지만 현재처럼 하나의 Pod에서 모든 것을 처리하는 구조가 **스케일링의 병목**이 되고 있다면, 검토해 볼 가치는 충분하다.

<br>

# 돌아보며

## 이번 경험을 통해 배운 것

기술적으로는 cgroup, CFS bandwidth control, throttling 메커니즘을 깊이 이해하게 되었다. 하지만 더 큰 배움은 다른 데에 있었다.

- **"일반적 예제"를 그대로 가져다 쓰는 것의 위험.** 웹 서비스에 맞는 리소스 설정이 영상 처리 워크로드에서는 37배의 성능 저하를 만들었다. 워크로드 특성을 이해하지 않고 설정한 값은, 얼마든지 이런 결과를 만들 수 있다.

- **"감"이 아니라 "측정"으로 판단하는 것.** "아마 CPU 때문일 것이다"에서 출발했지만, `cpu.stat`의 delta를 계산하고, Grafana 대시보드로 시계열을 관찰하고, 변수를 하나씩 바꿔가며 실험한 끝에야 확신을 가질 수 있었다.

- **설정하지 않는 것도 결정이다.** CPU limit을 제거하기로 한 것은 "아무것도 안 하는 것"이 아니라, 실험 데이터에 근거한 결정이다. 그리고 그 결정에는 모니터링이라는 책임이 따른다.

## 마치며

항상 느끼지만, 언제 어느 상황에서나 결국 문제 해결의 핵심은 "원인을 정확히 이해하는 것"이었다. 이번에도 마찬가지다. CPU limit이라는 한 줄의 설정이 커널 수준에서 어떤 결과를 만드는지 이해하고 나서야, "설정하지 않는다"는 결정을 자신 있게 내릴 수 있었다.

<br>

# 참고: ffmpeg `-threads auto`와 컨테이너 환경

## 컨테이너에서 코어 수 감지 문제

ffmpeg의 `-threads` 미지정(auto) 시 동작은 [공식 문서](https://github.com/FFmpeg/FFmpeg/blob/master/doc/multithreading.txt)에 따르면 호스트의 논리 프로세서 수를 기반으로 스레드 수를 결정한다. 공식 문서에서는 ffmpeg이 지원하는 두 가지 멀티스레딩 방식을 다음과 같이 설명한다.

> FFmpeg provides two methods for multithreading codecs.
>
> Slice threading decodes multiple parts of a frame at the same time, using AVCodecContext execute() and execute2().
>
> Frame threading decodes multiple frames at the same time. It accepts N future frames and delays decoded pictures by N-1 frames. The later frames are decoded in separate threads while the user is displaying the current one.

문제는 이것이 **cgroup의 CPU limit을 인식하지 못한다**는 것이다.

컨테이너 내부에서 ffmpeg이 보는 코어 수는 호스트의 코어 수(이 경우 20)이지, cgroup으로 제한된 코어 수(예: 4)가 아니다. 이는 ffmpeg만의 문제가 아니라, 많은 애플리케이션이 컨테이너 환경에서 겪는 [일반적인 이슈](https://superuser.com/questions/1721064/ffmpeg-limiting-to-single-cpu-core-when-encoding-h264)다. 해당 논의에서도 `-threads 1`이 기대대로 동작하지 않는 문제가 보고된다.

> "Somehow `-threads 1` has no effect at all… All the cores are still maxed out. How can I limit this to just one core?"
>
> — 질문자, "output threads only limits encoding threads. There's decoding and filtering as well as the main program thread." — Gyan(답변자)

인용에서 볼 수 있듯, `-threads`만으로는 디코딩·필터링·메인 스레드까지 제어할 수 없다. `-threads`를 명시적으로 지정하거나, `taskset`으로 CPU affinity를 제한하는 것이 권장된다.

이번 실험에서 `-threads auto`가 Dead Zone을 만든 것도 이 맥락이다. 5~7 core limit 환경에서 ffmpeg은 호스트의 20 core를 보고 스레드를 생성하여, 실제 사용 가능한 quota에 비해 과도한 스레드가 경쟁하는 상황을 만들었다.

<br>

## JPEG 인코딩과 Dead Zone의 관계

이번 서비스에서 프레임 추출 시 출력 포맷이 JPEG(MJPEG)인 것도 Dead Zone을 두드러지게 만든 요인일 수 있다. 아이러니한 것은, 원래 PNG로 인코딩하던 것을 압축 효율이 더 좋은 JPEG으로 바꾼 것이 이 서비스의 역사라는 점이다. "더 가벼운 포맷이면 더 빠르지 않을까"라는 판단이었는데, 컨테이너 CPU limit 환경에서는 오히려 독이 되었을 수 있다.

ffmpeg의 [MJPEG 인코더](https://ffmpeg.org/doxygen/trunk/mjpegenc_8c_source.html)는 **slice threading**을 지원한다. 앞서 인용한 공식 문서의 표현대로 "multiple parts of a frame at the same time"을 처리하는 방식이다. JPEG은 이미지를 독립적인 블록으로 나누어 압축하기 때문에, 각 블록을 여러 스레드가 동시에 인코딩할 수 있다. 이 특성 때문에 auto가 코어 수 기반으로 적극적으로 스레드를 생성한다.

반면, 이전에 사용하던 PNG는 병렬화가 제한적인 포맷이다. PNG였다면 auto가 보수적으로 스레드를 선택했을 것이고, Dead Zone이 덜 두드러졌을 가능성이 있다. 압축 효율을 위한 포맷 변경이, CPU limit 환경에서는 스레드 과생성이라는 예상치 못한 부작용을 낳은 셈이다.

| 포맷 | 병렬화 방식 | auto의 스레드 선택 | Dead Zone 가능성 |
|------|-----------|-----------------|----------------|
| JPEG | slice threading (독립 블록 압축) | 적극적 (코어 수 기반) | 높음 |
| PNG | 제한적 (sequential 압축) | 보수적 (1~2개) | 낮음 |

검증하지 못한 추정이지만, 만약 다른 프로젝트에서 비슷한 Dead Zone을 경험한다면 출력 포맷의 병렬화 특성을 함께 확인해 볼 가치는 있다.