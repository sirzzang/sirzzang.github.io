---
title: "[Performance] Roofline 모델: 연산 강도로 판별하는 성능 병목"
excerpt: "Roofline 모델에 대해 알아 보자."
categories:
  - CS
toc: true
header:
  teaser: /assets/images/blog-Dev.jpg
tags:
  - Roofline-Model
  - Operational-Intensity
  - GPU
  - Performance
  - HPC
  - LLM-Serving
  - Hands-On-LLM-Serving-and-Optimization-Study
  - Hands-On-LLM-Serving-and-Optimization-Study-Week-3
last_modified_at: 2026-08-22
---

*[서종호(가시다)](https://www.linkedin.com/in/gasida99/)님의 Hands-On LLM Serving and Optimization Study (LLMSO) 3주차 학습 내용을 기반으로 합니다.*

<br>

# TL;DR

- Roofline 모델은 워크로드의 성능 상한을 $P = \min(\pi, \beta I)$ 하나로 나타내는 시각적 성능 모델이다. Y축은 달성 성능 $P = W/T$(FLOP/s), 두 지붕은 하드웨어 상한인 수평선(연산 지붕 $\pi$)과 사선(대역폭 지붕 $\beta I$)이고, 그 아래에 실측점을 찍어 점의 위치로 병목을 판별한다
- X축인 연산 강도 $I = W/Q$는 DRAM에서 가져온 1바이트당 연산 횟수, 곧 데이터 재사용 횟수다. 시간이 들어가지 않는 값이고, 문제 크기와 무관하다
- 그래프 상에 표현된 점은 두 단계로 해석한다. 먼저 지붕(하드웨어 상한)에 붙었는지(남은 여유), 붙었다면 어느 지붕인지(병목의 정체)를 본다. 지붕에서 멀면 하드웨어가 아니라 돌리는 방식이 문제다
- 판별 결과에 따라 처방이 반대가 된다. 사선(메모리 바운드)에 붙었으면 $Q$를 줄여 점을 오른쪽으로 밀고(양자화·커널 퓨전·타일링·배칭), 수평(연산 바운드)에 붙었으면 $W$를 줄이거나 더 높은 지붕의 연산 유닛으로 옮겨야 한다

<br>

# 배경

MLOps 플랫폼 위에서 돌아가는 3D Object Detection 모델 학습을 관찰하던 중, `GPU_UTIL`은 96~100%인데 `PIPE_TENSOR_ACTIVE`는 약 1%, 전력은 명판 600W급 GPU에서 156W, `DRAM_ACTIVE`는 6%인 현상을 발견했다. MLOps에서는 보통 GPU utilization을 올리기 위해 노력하지만, 막상 GPU util이 100%에 가깝게 유지되는 것을 보니 정말 GPU를 잘 쓰고 있는 것인가 싶었다. 그렇게 파 보니 util은 "그 시간 동안 커널이 하나라도 돌고 있었는가"를 재는 **시간 지표**이고, FLOP/s는 **처리율 지표**라서, 시간이 꽉 차도 처리율은 낮을 수 있다는 답에 도달했다. util이 시간 기반 지표라는 정의 자체는 [Phantom GPU Utilization 사례 분석]({% post_url 2026-05-11-Dev-GPU-Phantom-Utilization %}#gpu-utilization의-정의-nvidia-smi와-nvml)에서 NVML 문서 기준으로 짚은 적이 있다. 

그렇다면 다음 질문이 남는다. **이 워크로드의 성능은 무엇이 가로막고 있나 — 연산기인가, 메모리 대역폭인가, 아니면 아직 어느 쪽도 아닌가.** 이걸 판별해 주는 도구가 Roofline 모델이다. LLM 서빙 최적화 스터디 3주차에서 산술 강도(arithmetic intensity)와 함께 이 키워드를 다시 만난 김에, 미루지 않고 정리해 보고자 한다.

<br>

# 개념

Roofline 모델은 **주어진 하드웨어에서 어떤 연산의 성능 상한이 연산 능력에 걸려 있는지 메모리 대역폭에 걸려 있는지를 보여 주는 시각적 성능 모델**이다. 연산 강도라는 하나의 축 위에서 병목을 판별하고, 남은 여유까지 함께 보여 준다. CPU, GPU, NPU 등 어느 연산기에서든 적용되는 컴퓨터 구조 쪽 도구이다.

실제 구글에 검색하면 아래와 같은 그림들이 나온다. 하드웨어가 가진 제약을 **사선과 수평선의 조합**으로 표현하고, 그 아래에 실제 측정한 성능을 **점**으로 표시한다.

![Roofline 모델 예시 - Wikipedia]({{site.url}}/assets/images/roofline-model-example.png){: .align-center}

<center><sup>출처: <a href="https://en.wikipedia.org/wiki/Roofline_model">Wikipedia — Roofline model</a>. x축 라벨의 FLOPS/byte 표기는 <a href="#표기-flops-vs-flops">표기 절</a>에서 다시 짚는다.</sup></center>

![Roofline 모델 예시 - Modal GPU Glossary]({{site.url}}/assets/images/roofline-model-example-2.png){: .align-center}

<center><sup>출처: <a href="https://modal.com/gpu-glossary/perf/roofline-model">Modal GPU Glossary — Roofline Model</a>. 수평 지붕을 arithmetic bandwidth라고 적어 두었는데, 표준 용어는 아니다. <a href="#정리">정리 절</a> 말미에서 다룬다.</sup></center>

위 그림에서 두 선을 왜 **지붕**이라 부르는지 보인다. 하드웨어 상한을 그린 이 선들 위로는 어떤 점도 올라갈 수 없다 — 성능을 위에서 덮어 누르는 한계다. 게다가 수평선과 사선이 꺾여 이어진 모양이 집 지붕을 그대로 닮았다. 그래서 모델 이름부터가 roofline(지붕선)이다. 이제부터 이 글에서는 이 상한선을 **지붕**으로 부른다 (수평 지붕 = 연산 한계, 사선 지붕 = 대역폭 한계).

자세한 내용은 차례로 알아 볼 예정이다. 지금은 그래프가 **점이 어디에 찍히는지를 보고 성능 상한을 올리기 위해 어떤 접근을 취해야 할지 판단하게 해 주는 시각화 도구**라는 감만 잡아 두면 된다.

분량이 꽤 길어서 읽는 경로를 먼저 적어 둔다. 순서대로 다 따라갈 필요는 없고, [구성 요소](#구성-요소)에서 기호와 연산 강도까지만 잡은 뒤 [해석](#해석)·[적용](#적용)으로 건너뛰어도 병목 판별이라는 실용 목적에는 충분하다. [유도](#유도)는 지붕이 왜 그 모양인지, [측정](#측정)은 점을 실제로 어떻게 찍는지가 궁금할 때 돌아와 읽으면 된다. 중간중간의 영어 인용문도 원문 자체보다 바로 아래 해석 위주로 보면 된다.

특히 이 글 내내 쓰는 판정 규칙 두 개를 미리 봐 두면 좋다.
1. 두 지붕이 꺾여 만나는 점을 **ridge point**라 하고, **점이 그 왼쪽이면 메모리 대역폭에, 오른쪽이면 연산 능력에 걸린다**(왜 그런지는 [유도](#변수-i)·[해석](#2단-판단)에서 따진다).
2. 이 그래프는 보통 **두 축이 로그 눈금**이라, 점과 지붕의 거리는 대각선이 아니라 **수직으로** 읽어야 한다([수평선과 사선](#수평선과-사선)).

<br>

# 구성 요소

## 기호와 정의

Roofline 모델을 이루는 값은 일곱 개다.

| 기호 | 이름 | 단위 | 의미 | 정체 |
| --- | --- | --- | --- | --- |
| $W$ | work | FLOP | 커널이 수행하는 총 부동소수점 연산 수 | 알고리즘 |
| $Q$ | memory traffic | byte | HBM(DRAM)↔칩 사이를 실제로 오간 총 바이트 | 알고리즘 + 캐시 |
| $T$ | time | s | 커널 실행 시간 | 측정값 |
| $\pi$ | peak performance | FLOP/s | 연산 처리율의 상한 | 하드웨어 |
| $\beta$ | peak bandwidth | byte/s | 메모리 대역폭 (A100 80GB $\approx 2\times10^{12}$) | 하드웨어 |
| $P$ | performance | FLOP/s | 달성 성능 $= W/T$, 그래프의 **Y축** | 측정값 |
| $I$ | intensity | FLOP/byte | $I = W/Q$, 바이트당 연산 밀도, 그래프의 **X축** | 알고리즘 + 캐시 |

단위 칸의 FLOP·FLOP/s·FLOP/byte는 부동소수점 연산 기준의 관습 표기다. 정수 연산이 주력인 하드웨어(엣지 NPU 등)라면 OP·OP/s·OP/byte로 그대로 바꿔 읽으면 되고, 모델 논리는 바뀌지 않는다 — 자세한 구분은 [작업량 단위 절](#작업량-단위-flop과-op)에서 다룬다.

- **Work $W$**: 주어진 커널 혹은 애플리케이션이 수행하는 연산의 수. 배열 원소 갱신 수, 정수 연산 수 등 어떤 종류의 연산이든 셀 수 있지만, 보통은 부동소수점 연산 수(FLOPs)를 센다
- **Memory traffic $Q$**: 커널 실행 중 발생한 메모리 전송 바이트 수
- **Time $T$**: 실행 시간
- **Performance $P$**: $P = W/T$. 총 FLOP을 초로 나눈 값, 즉 시간당 수행한 일의 양
- **Arithmetic intensity(operational intensity) $I$**: 산술 강도 혹은 연산 강도. $I = W/Q$, 메모리 트래픽 바이트 수 대비 연산 수

위키피디아는 $W$와 $Q$의 성질을 이렇게 적는다.

> Note that the *work* W is a property of the given kernel or application and thus depend just partially on the platform characteristics. … In contrast to W, Q is heavily dependent on the properties of the chosen platform, such as for instance the structure of the cache hierarchy.
>
> — [Wikipedia — Roofline model](https://en.wikipedia.org/wiki/Roofline_model)

요지는 이렇다. 여기서 *platform*은 MLOps 플랫폼 같은 소프트웨어가 아니라 **하드웨어**(칩·캐시 계층·메모리)를 가리킨다. $W$는 코드를 보고 세면 나오는 값이라 하드웨어와 거의 무관한 반면, $Q$는 "프로그램이 읽는 바이트"가 아니라 **DRAM과 칩 사이를 실제로 오간 바이트**라서 캐시 계층에 강하게 의존한다. 분자는 거의 하드웨어 무관, 분모는 하드웨어 의존 — 그 비율인 $I$가 "부분적으로만(partially)" 하드웨어에 의존한다는 뜻이다. 상세는 [이론 I vs 실측 I](#이론-i-vs-실측-i)에서 다시 살펴 본다.

<details markdown="1">
<summary><b>참고: $W$와 $Q$에 하드웨어가 개입하는 방식</b></summary>

$W$에 하드웨어가 개입하는 통로는 두 가지뿐이다 — FMA(곱셈-덧셈 융합)를 2 FLOP으로 셀 것인가 1로 셀 것인가, 그리고 컴파일러가 연산을 지우거나 늘리는가. 반면 $Q$는 같은 코드라도 캐시가 크면 한 번 가져온 데이터를 재사용해 줄고, 캐시가 작으면 같은 데이터를 여러 번 다시 가져와 늘어난다. 그래서 $Q$는 **알고리즘이 정하는 하한이 있고, 실제 값은 그 하한 이상에서 하드웨어가 결정**한다.

</details>

## 표기: FLOPs vs FLOP/s

앞의 [기호와 정의](#기호와-정의) 표에서 $P$(Y축)를 FLOP/s, $I$(X축)를 FLOP/byte로 적었다. 그런데 FLOP·FLOPs·FLOPS는 한 글자 차이로 뜻이 갈리는데도 실무에서 자주 섞여 쓰인다. 축이 왜 그 단위인지는 [유도](#유도)에서 따지고, 여기서는 **단위 표기 자체**만 정리한다.

대표적인 오표기가 위에 첨부한 위키피디아 그림에 있다. x축 라벨이 `Operational Intensity [FLOPS/byte]`인데 엄밀히는 **FLOP/byte가 맞다.** FLOPS/byte로 읽으면 "초당 연산을 바이트로 나눈 것"이 되어 의미가 없다 — **연산 강도에는 시간이 들어가지 않는다**는 x축의 핵심 성질이 지워지기 때문이다. 그림은 원본 그대로 인용하고, 본문에서는 FLOP/byte로 쓴다.

| 축 | 정확한 단위 | 의미 |
| --- | --- | --- |
| y축 | **FLOP/s** | 처리율 (시간 있음) |
| x축 | **FLOP/byte** | 작업량 ÷ 데이터량 (시간 없음) |

혼동을 피하기 위해서는 FLOPs와 FLOPS의 표기를 명확히 알아 둬야 한다.

$$
\text{FLOPS}(\text{초당 처리율}) = \frac{\text{FLOPs}(\text{작업량})}{\text{시간(초)}}
$$

|  | 확장 | 의미 | 단위 | Roofline에서 |
| --- | --- | --- | --- | --- |
| **FLOPs** | **FL**oating-point **OP**eration**s** | 부동소수점 연산의 **개수** — 작업량 | 개수 (무차원) | x축·y축의 분자 ($W$) |
| **FLOPS** | **FL**oating-point **O**perations **P**er **S**econd | 초당 연산 횟수 — **처리율** | 1/초 | y축 ($P$) |

<br>

<details markdown="1">
<summary><b>참고: 실무에서 '작업량'과 '처리율'을 구분하는 법 (대소문자·자릿수 신호, MFU)</b></summary>

*본문 이해엔 필수가 아니다. 찾아본 자료를 정리한 심화 내용이다.*

표기 관습상 대문자 S는 second, 소문자 s는 복수형인데, 실무에서는 거의 지켜지지 않는다. 소문자 s가 복수형인지 second인지 글자만 보고 구분이 안 되고, 논문·블로그·프로파일러가 제각각이라 같은 문서 안에서도 섞인다. 그래서 결과적으로 정착한 방식은 **대소문자에 의존하지 않고 슬래시로 명시**하는 것이다. 버클리랩 자료가 정확히 이런 식으로 쓴다.

```text
AI = Flops / Bytes presented to DRAM
Attainable Flop/s = min( peak Flop/s, AI * peak GB/s )
```

`Flops`는 작업량, `Flop/s`는 처리율이다. 문서를 읽을 때 둘을 구분하는 신호는 이렇다.

| 신호 | 판정 |
| --- | --- |
| `/s`, "초당", "per second"가 붙었다 | 처리율 |
| "총", "누적", "이 커널이 수행한" | 작업량 |
| 문맥이 하드웨어 스펙 (A100 312 TFLOPS) | 처리율 |
| 문맥이 모델·학습 비용 (GPT-3 학습 $\approx 3\times10^{23}$ FLOP) | 작업량 |
| 자릿수 $10^{12} \sim 10^{18}$ | 처리율일 가능성 |
| 자릿수 $10^{20} \sim 10^{25}$ | 작업량 (누적이라 훨씬 큼) |

두 의미가 한 수식에 동시에 나오는 예가 MFU(Model FLOPs Utilization)다.

$$
\text{MFU} = \frac{\text{토큰당 model FLOPs} \times \text{토큰 처리율}}{\text{peak FLOP/s}}
$$

분자의 앞항은 작업량(FLOPs), 전체 분자와 분모는 처리율(FLOP/s)이다. 여기서 단위를 헷갈리면 MFU가 몇 자리씩 틀어진다.

</details>

이 글의 표기는 아래로 고정한다.

| 쓸 것 | 뜻 | 안 쓸 것 |
| --- | --- | --- |
| **FLOP** | 연산 1회 (작업량의 단위) | — |
| **FLOP/s** | 처리율 | FLOPS, FLOPs/s |
| **FLOP/byte** | 연산 강도 | FLOPS/byte |
| **OP / OP/s / OP/byte** | 정수 포함 일반형 | — |

## 작업량 단위: FLOP과 OP

지금까지 단위를 FLOP으로 써 왔는데, 왜 대부분 부동소수점 연산량으로 세는가. FLOP은 특정 ISA나 벤더에 종속되지 않는 **하드웨어 중립적인 작업량 단위**라서 CPU·GPU·TPU·NPU·DSP·FPGA 어디서든 정의된다. 다만 정수 연산이 주력인 하드웨어에서는 일반형 OP를 쓴다.

| 표기 | 대상 | 주로 쓰는 하드웨어 |
| --- | --- | --- |
| **FLOP** | 부동소수점 (FP64/FP32/BF16/FP8 등) | CPU, GPU, TPU, HPC |
| **OP / TOP** | 정수 (INT8/INT4) 포함 일반 연산 | 모바일·엣지 NPU |

부동소수점 연산이 주력이 아닌 하드웨어(정수 전용 NPU 등)에서도 루프라인은 그대로 그려진다. **단위만 OP/s·OP/byte로 바꾸면 되고, 두 지붕과 ridge point 논리는 전혀 변하지 않는다.**

<br>

<details markdown="1">
<summary><b>참고: 정수 하드웨어의 TOPS 표기와 OP 일반형, 혼합 정밀도 주의</b></summary>

*본문 이해엔 필수가 아니다. 찾아본 자료를 정리한 심화 내용이다.*

엣지 NPU 스펙 시트가 "45 TOPS"처럼 정수 연산 처리율 위주로 표기하는 것은 INT8 파이프라인이 주력이고 FP 유닛이 없거나 약해서 FLOPS 표기가 부정확하기 때문이다. 엄밀히 말하면 연산기라면 OP/s가 적용되고, 그중 부동소수점을 다루는 연산기에 FLOP/s가 적용된다. 그래서 45 TOPS는 45 TOP/s, 즉 $4.5\times10^{13}$ OP/s를 뜻한다. 따라서 **y축이 FLOP/s인 것은 관습일 뿐 본질이 아니다.**

|  | 일반형 | 부동소수점 관습 | INT8 NPU에서 |
| --- | --- | --- | --- |
| y축 | 작업 처리율 OP/s | FLOP/s | INT8 OP/s |
| x축 (연산 강도) | OP/byte | FLOP/byte | OP/byte |

혼합 정밀도 커널을 분석할 때만 주의가 필요한데, FP16 GEMM과 FP32 누산이 섞이면 어느 지붕을 기준으로 그릴지가 애매해져서 보통 지배적인 유닛 기준으로 여러 층의 지붕을 겹쳐 그린다([정밀도·유닛](#정밀도유닛) 참고).

</details>

## 연산 강도

일곱 개의 구성 요소 중 연산 강도에 대해 더 자세히 알아 본다. 사실 위 구성 요소 중 $\pi$·$\beta$는 하드웨어가 준 상수, $W$·$T$·$P$는 세거나 나누면 바로 나오는 값이라 정의로 끝난다. $Q$도 단순하진 않다 — 실측 DRAM 트래픽이라 캐시에 따라 변한다. 다만 $W$가 거의 고정이라 $I = W/Q$의 미묘함은 사실상 전부 $Q$에서 오므로, $Q$는 따로 절을 두지 않고 [이론 I vs 실측 I](#이론-i-vs-실측-i)에서 $I$와 함께 다룬다. 

그래서 남는 하나, **$I$만 따로 파고들 이유**가 있다 — 그래프에서 유일하게 '고를 수 있는' 값이기 때문이다.

- 하드웨어를 고정하면 지붕($\pi$·$\beta$)은 정해지고, 점이 어디 서는지는 오직 $I$가 정한다 — **유일한 자유변수**다
- 사선(메모리)이냐 수평(연산)이냐, 즉 **병목 판정이 전적으로 $I$의 위치**(ridge point의 왼쪽이냐 오른쪽이냐)로 갈린다
- **최적화가 손대는 대상도 결국 $I$**다. 점을 오른쪽으로 미는 것이 곧 $Q$를 줄여 $I$를 키우는 일이다

그래서 $I$는 손으로 세는 법, 이론값과 실측값의 차이, 워크로드별 값까지 아래에서 따로 정리한다. (하드웨어 상수 $\pi$·$\beta$는 뒤 [유도](#유도)에서 지붕을 그릴 때 다시 다룬다.)

### 연산 강도 손계산

연산 강도는 **이 코드가 데이터 1바이트를 가져와서 몇 번 계산하는가**다.

$$
I = \frac{W}{Q}
$$

이걸 어떻게 계산하는가 하면, **정말 코드를 보고 손으로 $W$와 $Q$를 세서 나눠 주면 된다.** BLAS(Basic Linear Algebra Subprograms, 1979년부터 있는 선형대수 표준 라이브러리)의 함수를 예로 계산해 보자. BLAS 함수들은 첫 글자가 정밀도를 나타낸다. S는 Single(FP32), D는 Double(FP64), C/Z는 복소수다. 그리고 이 함수들은 BLAS Level이라는 연산 레벨로 분류되는데, 사실상 **이 연산 레벨이 연산 강도의 정체**다.

| BLAS Level | 대표 함수 | 데이터 크기 | 연산 횟수 | $I$ |
| --- | --- | --- | --- | --- |
| 1 (벡터-벡터) | **SAXPY** | $O(N)$ | $O(N)$ | $O(1)$ — 고정, 낮음 |
| 2 (행렬-벡터) | **GEMV** | $O(N^2)$ | $O(N^2)$ | $O(1)$ — 고정, 낮음 |
| 3 (행렬-행렬) | **GEMM** | $O(N^2)$ | $O(N^3)$ | $O(N)$ — 커질수록 증가 |

<br>

양 극단인 SAXPY(벡터 연산)와 GEMM(행렬 곱) 둘만 결과를 보면 이렇다.

- **SAXPY** (`y = a*x + y`): 원소당 곱 1 + 합 1이라 $W = 2N$, 오가는 byte는 x 읽기·y 읽기·y 쓰기로 원소당 접근 3회 × FP32 원소 하나 4 byte라 $Q = 12N$ → $I \approx 0.17$. $N$이 약분되니 **연산 강도는 문제 크기와 무관**하다([변수 I](#변수-i) 절에서 결정적으로 쓰인다). FP32를 FP16으로 바꾸면 $Q$가 절반이라 $I$는 2배가 되는데, 저정밀도가 대역폭 병목의 해법인 이유가 여기 있다
- **GEMM** (`C = A × B`): $W = 2N^3$, 각 행렬(A·B·C)을 DRAM에서 한 번씩만 옮기면 $Q = 3N^2 \times 4 = 12N^2$ → $I = N/6$ ($N=1024$면 약 170)

두 결과를 가르는 것은 **재사용**이다. GEMM은 서로 다른 데이터 $N^2$개를 $N^3$번 계산하니 같은 원소를 $N$번씩 다시 본다 — 이 $N$이 그대로 연산 강도의 $N$이다. 즉 **연산 강도 = 재사용 횟수의 다른 이름**이고, 강도를 가르는 건 "곱셈이냐 덧셈이냐"가 아니라 **같은 원소가 다시 등장하는가**다. SAXPY는 재사용이 0이라 강도가 낮게 고정된다.

<br>

<details markdown="1">
<summary><b>참고: $W$·$Q$를 손으로 세는 전 과정 (SAXPY·GEMM 단계별, dtype 영향)</b></summary>

*본문 이해엔 필수가 아니다. 찾아본 자료를 정리한 심화 내용이다.*

위의 BLAS 연산 중 연산 강도 스펙트럼의 양 극단에 있는 두 함수를 계산해 본다.

| 이름 | 풀어쓰면 | 하는 일 |
| --- | --- | --- |
| **SAXPY** | **S**ingle precision **A** times **X** **P**lus **Y** | `y = a*x + y` (a는 스칼라, x·y는 벡터) |
| **GEMM** | **GE**neral **M**atrix **M**ultiply | `C = A × B` (행렬 곱) |

**SAXPY** 코드는 이게 전부다.

```c
// 루프 한 바퀴에 곱 1회 + 합 1회 = 2 FLOP
for (int i = 0; i < N; i++)
    y[i] = a * x[i] + y[i];
```

$W$부터 센다. 루프 한 바퀴에 부동소수점 연산이 몇 개인지 본다. `a * x[i]`가 곱셈 1개, 거기에 `y[i]`를 더하는 덧셈 1개, 합 2개다. 루프가 $N$번 도니 $W = 2N$ FLOP. 이때 `i < N`(비교), `i++`(증가), 주소 계산은 세지 않는다. 이 연산들은 전부 정수 연산이라 FLOP이 아니기 때문이다. "부동소수점"이라는 단서가 붙어 있는 이유다.

다음은 $Q$다. 루프 한 바퀴에 메모리와 오가는 바이트를 센다. FP32는 32비트, 즉 4 byte다.

| 무엇 | 방향 | byte |
| --- | --- | --- |
| `x[i]` | 읽기 | 4 |
| `y[i]` (오른쪽, 더할 값) | 읽기 | 4 |
| `y[i]` (왼쪽, 결과 저장) | 쓰기 | 4 |
| 합 |  | **12** |

$N$번 반복이니 $Q = 12N$ byte. 헷갈리기 쉬운 지점이 둘 있다. 
- 첫째, **`a`는 세지 않는다.** 스칼라 하나라서 레지스터에 한 번 올려두면 $N$번 재사용되고, $N$에 비례하지 않으니 무시한다. 
- 둘째, **`y[i]`는 두 번 세는 게 맞다.** 같은 주소인데 왜 두 번인가 싶지만, 읽기와 쓰기는 별개의 트래픽이다. 값을 가져오려고 버스를 한 번 지나가고, 결과를 되돌려놓으려고 또 한 번 지나간다.

$$
I = \frac{2N}{12N} = \frac{1}{6} \approx 0.167
$$

$N$이 약분되는 것에서 **연산 강도는 문제 크기와 무관**하다는 것을 확인할 수 있다. 같은 연산인데 자료형이 바뀌면 어떻게 되는지도 보자.

| dtype | bit | byte |
| --- | --- | --- |
| FP64 (double) | 64 | 8 |
| FP32 (float, single) | 32 | 4 |
| FP16 / BF16 | 16 | 2 |
| FP8 / INT8 | 8 | 1 |

SAXPY의 S(single)가 4 byte였는데, DAXPY(FP64)로 바꾸면 원소 하나가 8 byte가 되니 $Q = 24N$이 되고, $I = \frac{2N}{24N} = \frac{1}{12} \approx 0.083$이 된다. **연산은 그대로인데 강도가 절반**이 된 것이다.

다음은 **GEMM**이다.

```c
// 가장 안쪽 한 줄에 곱 1회 + 합 1회 = 2 FLOP, 3중 루프로 N^3번 실행
for (i = 0; i < N; i++)
  for (j = 0; j < N; j++)
    for (k = 0; k < N; k++)
      C[i][j] += A[i][k] * B[k][j];
```

$W$는 가장 안쪽 한 줄에 곱 1 + 합 1 = 2 FLOP, 3중 루프 $N^3$번이니 $W = 2N^3$이다. 일반형으로는 `(m,k)·(k,n)` 행렬곱이 $2mkn$ FLOP이다 — 출력 원소 하나가 곱 $k$번 + 합 $k{-}1$번 ≈ $2k$ 연산이고 그런 원소가 $mn$개다. 정사각($m=k=n=N$)이면 $2N^3$으로 떨어진다. $Q$는 순진하게 세면 안쪽 루프마다 A, B를 읽으니 트래픽도 $N^3$에 비례할 것 같지만, A·B·C 각각 원소가 $N^2$개뿐이고 **같은 원소를 $N$번씩 다시 쓰는 것**이므로 새 데이터가 아니다. 캐시에 담아 두고 재사용하면 각 행렬을 DRAM에서 딱 한 번씩만 옮기는 것이 이상적 하한이다.

$$
Q_{\min} = \underbrace{3N^2}_{\text{A, B, C}} \times \underbrace{4}_{\text{FP32}} = 12N^2 \text{ byte}
$$

</details>

<details markdown="1">
<summary><b>참고: "재사용 = 연산 강도"를 코드 전개로 확인</b></summary>

*본문 이해엔 필수가 아니다. 찾아본 자료를 정리한 심화 내용이다.*

"같은 원소를 다시 쓴다"가 무슨 말인지는 두 코드를 펼쳐 보면 분명해진다. 먼저 $N=4$로 SAXPY 루프를 다 펼쳐 본다.

```c
// N=4로 펼친 SAXPY — 각 x[i], y[i]는 자기 줄에만 등장한다
i=0:  y[0] = a*x[0] + y[0]
i=1:  y[1] = a*x[1] + y[1]
i=2:  y[2] = a*x[2] + y[2]
i=3:  y[3] = a*x[3] + y[3]
```

`x[0]`은 딱 한 줄에만 나온다. i=0 줄에서 쓰이고 다시는 등장하지 않는다. `x[1]`도, `x[2]`도 마찬가지다. 그래서 `x[0]`을 캐시에 남겨 두는 것은 아무 의미가 없다. 다시 쓸 일이 없기 때문이다. **캐시가 100 TB여도 SAXPY는 빨라지지 않는다.** 그런데 `a`는 다르다. `a`는 4줄 전부에 나온다. 한 번 읽어 두면 4번 쓴다. 그래서 $Q$를 셀 때 `a`를 4번이 아니라 1번으로 센 것이다.

**GEMM은 SAXPY의 `a`처럼 행동하는 데이터가 전부인 코드다.** $N=2$로 똑같이 풀어 쓰면 안쪽 루프 실행이 $N^3 = 8$번이다.

| # | 실행되는 줄 |
| --- | --- |
| 1 | `C[0][0] += A[0][0] * B[0][0]` |
| 2 | `C[0][0] += A[0][1] * B[1][0]` |
| 3 | `C[0][1] +=` **`A[0][0]`** `* B[0][1]` |
| 4 | `C[0][1] +=` **`A[0][1]`** `* B[1][1]` |
| 5 | `C[1][0] += A[1][0] *` **`B[0][0]`** |
| 6 | `C[1][0] += A[1][1] *` **`B[1][0]`** |
| 7 | `C[1][1] += A[1][0] * B[0][1]` |
| 8 | `C[1][1] += A[1][1] * B[1][1]` |

`A[0][0]`을 찾아 보면 1번과 3번, 두 번 나온다. `B[0][0]`도 1번과 5번, 두 번이다. $N=2$니까 두 번이고, $N=1024$면 각 원소가 1024번 등장한다.

|  | $N=2$ | 일반 |
| --- | --- | --- |
| 안쪽 루프 실행 횟수 | 8 | $N^3$ |
| 서로 다른 데이터 원소 수 | 12 (A 4 + B 4 + C 4) | $3N^2$ |
| 원소 하나가 등장하는 횟수 | **2번** | $N$번 |

**$N^3$번 계산하는데 데이터는 $N^2$개뿐이다.** 그러니 $N^3/N^2 = N$번씩 같은 값을 다시 본다. 이 $N$이 재사용 횟수고, 이것이 그대로 연산 강도 $N/6$의 그 $N$이다. 정리하면 **재사용 횟수 = 총 연산 횟수 ÷ 서로 다른 데이터 원소 수**이고, **연산 강도는 재사용 횟수의 다른 이름**이다. 차이를 만드는 축은 "곱셈이냐 덧셈이냐"가 아니라 **같은 원소가 다시 등장하는가**다.

- 곱셈만 하는 코드 `z[i] = x[i]*y[i]`: $W=N$, $Q=12N$ → $I = 1/12$. 곱셈인데도 강도가 낮다
- 덧셈만 하는 코드 `for i: for j: s += x[i] + y[j]`: 원소 $2N$개($8N$ byte)로 $2N^2$번 연산 → $I = N/4$. 덧셈인데도 강도가 높다

$$
I = \frac{2N^3}{12N^2} = \frac{N}{6} \;\xrightarrow{N=1024}\; 170
$$

</details>


결국 공식이라고 부를 만한 것은 아래 두 개가 전부이고, 나머지는 코드를 보고 세는 일이다.

$$
W = (\text{반복 1회당 FLOP 수}) \times (\text{반복 횟수})
$$

$$
Q = (\text{꼭 한 번씩은 발생해야 하는 읽기·쓰기 전송 횟수}) \times (\text{원소 1개 byte})
$$

세는 규칙은 두 가지다. **같은 원소라도 읽기와 쓰기는 별개 트래픽으로 센다** — SAXPY의 y를 두 번 센 이유다. 반대로 **레지스터에 한 번 올려두고 재사용하는 스칼라는 세지 않는다** — SAXPY의 a를 0번 센 이유다.

### 이론 I vs 실측 I

연산 강도 $I = W/Q$에는 사실 **두 가지 값**이 있다. **손으로 셀 때**는 "캐시가 충분해서 데이터를 딱 한 번만 가져온다"고 가정하고 세므로 알고리즘만으로 정해지는 **이론값**이 나오고, **프로파일러로 잴 때**는 실제로 오간 DRAM 트래픽 기준이라 캐시 히트율에 따라 달라지는 **실측값**이 나온다. "연산 강도는 하드웨어와 무관하다"와 "캐시에 따라 변한다"는 상반된 설명이 둘 다 도는 건 이 서로 다른 두 $I$를 각각 가리키기 때문이고, 이 구분을 안 해 두면 뒤의 해석이 흔들린다. 이론값 쪽은 **compulsory**라 부른다 — 아무리 캐시가 좋아도 처음 한 번은 반드시 가져와야 하는 전송(cold miss)만 있다고 가정한 값이라는 뜻이다. 표로 대조하면 이렇다.

|  | $I_{\text{compulsory}}$ (이론상) | $I_{\text{실측}}$ |
| --- | --- | --- |
| $Q$를 어떻게 세나 | 서로 다른 원소 수 × 원소 byte (캐시가 충분하다고 가정) | 프로파일러로 실제 DRAM 트래픽 측정 |
| 하드웨어 의존 | **없음** | **있음** (캐시 크기, 타일링 성공 여부, 접근 패턴) |
| 뜻 | 알고리즘이 **허용하는 최대** 강도 | 실제로 **실현한** 강도 |
| 어디서 얻나 | 손계산 | `dram__bytes_read.sum`, `dram__bytes_write.sum` |
| GEMM $N=1024$ | 170 (앞 손계산의 값) | 타일링에 실패하면 SAXPY 수준(0.1대)까지 떨어진다 |

항상 $Q_{\text{실측}} \geq Q_{\text{compulsory}}$이므로 $I_{\text{실측}} \leq I_{\text{이론}}$이고, **그 격차가 곧 최적화 여유분**이다. 그래서 **최적화란 실측 $Q$를 이론 하한까지 끌어내려 실측 $I$를 이론값에 붙이는 일**이다 — 대표적인 게 **타일링**(캐시에 맞게 데이터를 잘라, 한 번 가져온 것을 최대한 재사용하도록 접근 순서를 바꾸는 것)이다. 실측값이 이론 상한보다 많이 낮으면 캐시 재사용에 실패했다는 신호다. 여기서 캐시의 역할을 정확히 말하면 이렇다. **캐시는 성능을 만들어내지 않는다. 알고리즘에 이미 있는 재사용을 실현시켜 줄 뿐이다.** 그래서 재사용이 있는 연산은 타일링으로 이론값에 다가갈 수 있지만, 재사용이 0인 연산은 캐시를 아무리 키워도 두 $I$가 같다 — 앞의 SAXPY(0.17)가 어느 하드웨어에서도 그대로인 이유다.

<details markdown="1">
<summary><b>참고: 메모리 재사용을 실현하는 건 프로그래머인가 하드웨어인가</b></summary>

*본문 이해엔 필수가 아니다. 찾아본 자료를 정리한 심화 내용이다.*

**캐시라는 장치와 자동 캐싱 동작 자체는 하드웨어가 준 것**이라, 프로그래머가 "이걸 L2에 넣어"라고 명령하지는 못한다. 대신 **그 자동 캐시가 얼마나 잘 먹히는지(히트율)는 접근 방식이 좌우한다** — 캐시를 직접 제어하는 게 아니라, 접근 패턴을 바꿔 자동 캐시가 재사용하도록 유도하는 것이다.

- **CPU**: L1/L2/L3는 투명하게 자동 관리된다. 프로그래머의 레버는 접근 순서(locality)·타일링·데이터 레이아웃·정밀도다. 루프를 재구성해 워킹셋이 캐시에 들어오게 만들면, 같은 하드웨어 캐시가 비로소 재사용을 준다
- **GPU**: 자동 캐시(L1/L2)에 더해 **shared memory**(온칩 스크래치패드)는 프로그래머가 "DRAM에서 이 타일을 올려라 → 재사용해라"를 직접 코드로 관리한다. 손으로 짠 GEMM 타일링 커널이 그 예이고, cuBLAS 같은 라이브러리가 이 일을 대신 해 준다

즉 **하드웨어가 고정하는 것**(캐시 크기·교체 정책·계층의 존재)과 **프로그래머가 정하는 것**(접근 순서·레이아웃·타일 크기·GPU shared memory 사용)이 나뉜다. 그래서 실측 $Q$가 compulsory 하한에 얼마나 가까운지는 결국 접근 패턴 = 프로그래머 몫이고, **타일링이 곧 점을 오른쪽으로 미는 일**이 된다.

</details>

<details markdown="1">
<summary><b>참고: 이론 상한의 경계 조건 및 operational intensity 용어</b></summary>

*본문 이해엔 필수가 아니다. 찾아본 자료를 정리한 심화 내용이다.*

한 가지 경계 조건도 적어 둔다. $Q_{\min} = 12N^2$은 각 행렬을 한 번씩만 옮긴다는 cold miss 하한인데, 이것이 달성 가능하려면 캐시가 재사용 워킹셋을 담을 수 있어야 한다. $N=1024$ FP32면 행렬 하나가 4 MB, 셋이 12 MB로 A100 L2(40 MB)에 들어가지만, $N=8192$면 셋이 768 MB라 들어가지 않는다. 이때는 완벽하게 타일링해도 트래픽 하한이 캐시 크기 $M$에 묶여 $\Theta(N^3/\sqrt{M})$로 커진다는 것이 알려져 있다(Hong–Kung, 1981). 즉 **큰 $N$에서 실측 $I$의 상한은 $N/6$이 아니라 $\sqrt{M}$ 스케일에서 포화**한다.

원논문이 arithmetic intensity가 아니라 operational intensity라는 새 용어를 만든 이유가 정확히 이 지점이다.

> We use operational intensity instead of the terms arithmetic intensity or machine balance for two reasons. First, arithmetic intensity and machine balance measure traffic between the **processor and cache**, whereas we want to measure traffic between the **caches and DRAM**. … allows us to include memory optimizations of a computer into our bound and bottleneck model.

즉 **원논문의 $I$는 실측 쪽**이다. 캐시↔DRAM 트래픽은 정의상 하드웨어에 의존하고, 논문은 그것을 일부러 택했다. 캐시 최적화의 효과를 모델 안으로 끌어들이기 위해서다. [기호와 정의](#기호와-정의)에서 본 *"depend just partially on the platform characteristics"*가 정확한 표현이 되는 이유이기도 하다. 같은 이유로, 어느 메모리 계층 기준으로 트래픽을 세느냐에 따라 $I$가 달라진다. L2 기준으로 다시 그리면 강도가 확 낮아진다. 이것이 HBM/L2/L1 지붕을 겹쳐 그리는 hierarchical roofline의 배경이다([메모리 계층](#메모리-계층) 참고).

</details>

### 워크로드별 연산 강도

자주 인용되는 워크로드별 연산 강도는 아래와 같다. 값 자체는 **널리 알려진 수치**라 표만 봐도 충분하다 — SAXPY·GEMM이 어떻게 나오는지는 앞 [손계산](#연산-강도-손계산)에서 봤고, 여기서는 LLM decode만 새로 짚는다.

| 워크로드 | $I$ (FLOP/byte) |
| --- | --- |
| SAXPY (FP32) | 0.17 |
| LLM decode, batch=1 | $\approx 1$ |
| LLM decode, batch=B | $\approx B$ |
| GEMM / prefill | 수백 |

- **LLM decode, batch=1**: 7B 모델, FP16, 배치 1에서 토큰 1개를 생성하려면 **가중치 전체를 한 번 읽어야** 한다. $Q = 7\times10^9 \times 2 \text{ byte} = 14$ GB. 가중치 원소 하나당 곱 1 + 합 1이니 $W = 7\times10^9 \times 2 = 1.4\times10^{10}$ FLOP. 따라서 $I \approx 1$ FLOP/byte — 가중치 읽는 시간이 거의 전부라 메모리 바운드다
- **LLM decode, batch=B**: 배치를 $B$로 늘리면 가중치를 **한 번 읽어 $B$개 토큰이 나눠 쓰므로** $Q$는 그대로인데 $W$만 $B$배가 된다 → $I \approx B$. 이것이 "**배칭이 곧 재사용**"의 뜻 — 한 번 가져온 가중치를 $B$개 토큰이 나눠 재사용하는 것이다. 그리고 **$I$가 이렇게 커지는 게 바로 노리는 바다**: batch=1은 $I \approx 1$로 사선(메모리 바운드)에 딱 붙어 연산기를 거의 못 쓰는데, $I$를 키우면 점이 오른쪽으로 이동해 사선을 벗어나 연산 지붕 쪽으로 올라간다. decode에서 $I$를 올릴 길은 배칭뿐이라(가중치 바이트도, 토큰당 연산량도 줄일 수 없으니) 배칭이 **유일한 탈출구**다 — "배칭하면 $I$가 세지는 것 아닌가?"가 맞고, 그게 정확히 원하는 결과다

단, 여기의 decode 계산은 가중치 트래픽만 센 것이다. KV 캐시 트래픽까지 넣은 보정은 [2편의 평가 지표]({% post_url 2026-08-21-Dev-Roofline-Model-LLM-Serving %}#평가-지표)에서 다룬다.

그리고 위의 BLAS Level 표가 곧 [prefill/decode]({% post_url 2026-08-14-Dev-LLM-Serving-Optimization-03-03-LLM-Serving-Prefill-Decode %})의 설명이다. 관건은 **연산 횟수가 데이터 크기와 같은 속도로 느는가, 더 빨리 느는가**다. Level 1·2는 둘이 같은 속도라($O(N)$:$O(N)$, $O(N^2)$:$O(N^2)$) 각 데이터를 사실상 한 번만 써서 $I$가 낮게 고정된다. 오직 Level 3(행렬×행렬)만 연산이 $O(N^3)$으로 데이터 $O(N^2)$보다 빨리 늘어나는데, 각 데이터를 $N$번 재사용하기 때문이고 그래서 $I$가 $N$에 비례해 커진다. **$I$가 커지면** 점이 ridge 오른쪽(수평 지붕)으로 올라 **연산 바운드**가 되고, **$I$가 낮게 고정되면** 점이 ridge 왼쪽(사선)에 머물러 **메모리 바운드**다 — 크기를 키워도 $I$가 그대로라 벗어나지 못한다. 그래서 GEMM(Level 3)만 연산 바운드가 될 수 있다.

|  | 한 번에 처리하는 토큰 수 | 연산 모양 | BLAS Level | $I$ | 판정 |
| --- | --- | --- | --- | --- | --- |
| **prefill** | $S$개 (프롬프트 전체) | 가중치 행렬 × (hidden × $S$) 행렬 | **3 (GEMM)** | $S$에 비례 | 연산 바운드 |
| **decode** | 1개 | 가중치 행렬 × 벡터 | **2 (GEMV)** | $\approx 1$ | 메모리 바운드 |

**같은 가중치, 같은 코드다.** 다른 것은 한 번에 몇 개의 토큰을 곱하는가 하나뿐이고, 그 하나가 BLAS Level 2와 3의 차이를 만든다. "prefill이 compute bound인 이유가 결국 GEMM이라서인가"에 대한 답은 그렇다이다. 가중치를 한 번 DRAM에서 읽어 $S$개 토큰에 재사용하므로 $I$가 $S$배로 커진다. decode는 $S=1$이라 재사용이 없다. 다만 **어텐션은 따로 봐야 한다.** prefill 어텐션은 $S^2$에 비례해 역시 연산 집약적이지만, decode 어텐션은 **KV 캐시**(요청마다 다르고 컨텍스트에 비례해 커지는 데이터) 전체를 읽어야 해 메모리 바운드다. 이쪽은 배칭으로도 잘 안 풀리는데, 그 이유와 처방(PagedAttention 등)은 [2편의 세 점 구분]({% post_url 2026-08-21-Dev-Roofline-Model-LLM-Serving %}#세-점으로-나누기)에서 다룬다.

<br>

# 유도

Roofline의 결론은 아래 한 줄이다.

$$
\text{Attainable FLOP/s} = \min(\pi,\ \beta \times I)
$$

원래 [roofline을 처음 제시한 논문](https://escholarship.org/content/qt78h8v7mr/qt78h8v7mr.pdf)도 이 결론 — *Attainable GFlops/sec = Min(Peak Floating Point Performance, Peak Memory Bandwidth × Operational Intensity)* — **만** 제시한다. 그런데 공식만 봐서는 이게 어떻게 나온 건지 이해하기 어려워, AI의 도움을 받아 이 식이 어떻게 유도됐을지 이해하기 편한 순서로 재구성한 것이 아래다.

논문은 자기 방법을 스스로 **bound and bottleneck analysis**라고 부르는데, 이는 "병목이 되는 자원이 전체 **시간**의 하한을 정한다"는 논증이다. 직계 조상인 Kung(1986)도 *"a PE is said to be balanced if the computation time equals the I/O time"*이라며 아예 시간으로 정의한다. 즉 이 계열 모델은 처음부터 '작업 시간의 하한'에서 출발한다 — 그래서 이 재구성도 성능을 새로 정의하지 않고 **[기호와 정의](#기호와-정의)에서 이미 준 $P = W/T$를 지렛대로** 쓴다. 성능이 시간의 함수이니, 시간의 하한을 구하면 성능의 상한이 딸려 나오기 때문이다.

흐름은 이렇다. ① 성능 정의 $P = W/T$에서 출발해(성능은 시간의 함수다), ② 그 시간 $T$의 하한을 구하고($T \geq \max(W/\pi,\ Q/\beta)$), ③ 둘을 합쳐 성능의 상한 $P \leq \min(\pi,\ \beta I)$을 얻는다. 그러면 ④ 이 식에서 왜 변수가 $I$ 하나(=X축)인지, ⑤ 이 식을 그리면 왜 수평선과 사선이 되는지가 차례로 따라 나온다.

## 시간 하한

커널이든 애플리케이션이든, 연산을 한다면 반드시 해야 하는 일이 두 가지다.

| 해야 할 일 | 양 | 처리 속도 | 최소 소요 시간 |
| --- | --- | --- | --- |
| 연산하기 | $W$ FLOP | $\pi$ FLOP/s | $W/\pi$ |
| 데이터 옮기기 | $Q$ byte | $\beta$ byte/s | $Q/\beta$ |

$W$ FLOP을 초당 $\pi$ FLOP으로 쉼 없이 연산하면 이론상 $W/\pi$ 초가 걸리고, 총 $Q$ byte를 초당 $\beta$ byte로 쉼 없이 옮기면 이론상 $Q/\beta$ 초가 걸린다.

두 일이 동시에 진행된다고 가정해 보자. 연산과 데이터 이동이 완벽하게 겹친다면 걸리는 시간은 **둘 중 더 오래 걸리는 쪽**이다. 그런데 이것은 두 자원이 100% 포화 상태로 쉼 없이 돌아야 가능한 값이다. 실제로는 latency 노출, 캐시 미스, 낮은 occupancy 때문에 항상 이보다 오래 걸린다. 그래서 등호가 아니라 부등호다.

$$
T \geq \max\left(\frac{W}{\pi},\ \frac{Q}{\beta}\right)
$$

## 성능 P = min(π, βI)

Roofline 모델이 나타내고 싶은 것은 시간이 아니라 **성능**이다. 성능은 $P = W/T$로 정의되었으니, 위 부등식을 그대로 넣는다.

$$
P = \frac{W}{T} \leq \frac{W}{\max\left(\dfrac{W}{\pi},\ \dfrac{Q}{\beta}\right)} = \min\left(\underbrace{\frac{W}{W/\pi}}_{\text{연산 쪽}},\ \underbrace{\frac{W}{Q/\beta}}_{\text{메모리 쪽}}\right)
$$

분모의 $T$에 $\max$가 들어가 있으니, 역수를 취하면서 $\min$으로 바뀐다. 

<br>

두 항을 각각 정리하면 연산 쪽은 $\frac{W}{W/\pi} = \pi$, 메모리 쪽은 다음과 같다.

$$
\frac{W}{Q/\beta} = \frac{W\beta}{Q} = \beta \cdot \underbrace{\frac{W}{Q}}_{= I} = \beta I
$$

$$
P = \min(\pi,\ \beta I)
$$

왜 갑자기 $\beta$가 $I$에 곱해지는가 당황할 수 있지만, $\beta$가 새로 붙은 게 아니다. $\dfrac{W}{Q/\beta}$ 안에 **이미 있던** $\beta$가 분자로 올라온 것이다. 그 과정에서 $W/Q$라는 덩어리가 남았고, 그 덩어리에 "연산 강도"라는 이름을 붙인 것이다. 

<br>

결과적으로 **$I$는 정의가 먼저 있었던 게 아니라, 이 나눗셈에서 살아남은 좌표다.** 원 논문이 굳이 $W/Q$라는 비율에 이름을 붙인 이유가 여기 있다 — 성능 식을 쓰면 반드시 이 형태로만 남기 때문이다.

단위를 붙여 다시 쓰면 좌우변이 맞는지 확인할 수 있다.

$$
\underbrace{P}_{\text{FLOP/s}} = \min\left(\underbrace{\pi}_{\text{FLOP/s}},\ \underbrace{\beta}_{\text{byte/s}} \times \underbrace{I}_{\text{FLOP/byte}}\right)
$$

$$
P = \min(\underbrace{\pi}_{\text{순수 하드웨어}},\ \underbrace{\beta}_{\text{하드웨어}} \times \underbrace{I}_{\text{워크로드 + 캐시}})
$$

위 식의 두 항을 뜯어 보면 성격이 다르다. **사선 항 $\beta I$는 하드웨어 상수와 소프트웨어 성질의 곱이다** — $\beta$(대역폭, byte/s)는 하드웨어가 정한 상수이고 $I$(연산 강도, FLOP/byte)는 워크로드·캐시가 정하는 값이라, 둘을 곱한 $\beta I$ 안에는 하드웨어와 소프트웨어가 함께 들어 있다. 반면 **수평 항 $\pi$는 순수하게 하드웨어**다 — 유도 과정에서 $W$가 약분돼 사라지면서($\pi = W/(W/\pi)$) 소프트웨어 성질이 하나도 안 남았다. 이 비대칭이 이 모델의 전부라고 해도 된다.

> **앞에서 $\max$(그리고 그걸 뒤집은 $\min$)가 등장한 것 자체가 사실 하나의 가정이었다.** 연산과 데이터 이동이 **완전히 겹친다**는 가정이다. 만약 전혀 겹치지 않는다면 두 시간을 더해야 한다.
>
> $$
> T = \frac{W}{\pi} + \frac{Q}{\beta} \quad\Longrightarrow\quad P = \left(\frac{1}{\pi} + \frac{1}{\beta I}\right)^{-1}
> $$
>
> 이 경우 그래프는 지붕처럼 꺾이지 않고 **완만하게 휘는 곡선**이 된다. 즉 루프라인이 "지붕" 모양인 이유가 곧 이 겹침 가정이고, 이것이 루프라인이 낙관적 상한인 이유다. 실제 하드웨어는 이 둘 사이 어딘가에 있다.

## 변수 I

이 모델의 변수는 연산 강도 $I$ 하나이다. 실제 위키피디아는 이 그래프를 두고 *"there are only two parameters, peak performance and peak bandwidth, and one variable, arithmetic intensity"*([Roofline model](https://en.wikipedia.org/wiki/Roofline_model))라고 말한다. 그런데, 왜 변수가 하나뿐인지는 말하지 않는다. 그 빈 자리를 채워야 그래프가 왜 이 모양인지 알 수 있다.

**첫째, 원래는 변수가 두 개였다.** 유도를 시작할 때 등장한 값은 다섯 개다: $W, Q, T, \pi, \beta$.

| 양 | 어떻게 되었나 |
| --- | --- |
| $\pi, \beta$ | 하드웨어가 고정 → **파라미터** (지붕의 모양을 결정) |
| $T$ | 고르는 값이 아니라 결과. $P = W/T$로 흡수되어 **Y축**이 됨 |
| $W, Q$ | **둘 다 남는다** |

그래서 원칙적으로 이 모델은 3차원이어야 한다: $(W, Q) \mapsto P$. 값이 셋이니 원래대로면 2차원 평면에는 그릴 수 없다 — 그런데도 그릴 수 있는 데는 이유가 있다.

**둘째, $(W, Q)$ 평면이 직선 하나로 줄어든다.** $W$와 $Q$에 똑같이 $\lambda$를 곱해 본다. 문제 크기를 $\lambda$배로 키운 것이다.

$$
\min\left(\pi,\ \beta\frac{\lambda W}{\lambda Q}\right) = \min\left(\pi,\ \beta\frac{W}{Q}\right)
$$

**상한이 변하지 않는다.** 이 상한 함수는 $W$와 $Q$를 각각 알 필요가 없고 **비율만** 알면 된다. 수학적으로는 한 줄이다 — $f(\lambda W, \lambda Q) = f(W, Q)$이면 $\lambda = 1/Q$를 넣어

$$
f(W, Q) = f(W/Q,\ 1)
$$

이므로 $f$는 $W/Q$ 하나만의 함수다. **2차원이 1차원으로 줄어든다. 이렇게 차원이 하나로 줄어드는 것이 루프라인을 평면 위에 그릴 수 있는 이유 전부다.** 그리고 그 살아남은 유일한 좌표에 붙은 이름이 연산 강도다.

**셋째, 남은 값들을 하나씩 축 후보로 넣어 보면 왜 $I$뿐인지 드러난다.** (논문이 여러 축을 시도해 봤다는 뜻이 아니라, 앞에 남은 유한한 값들로 축을 만들 수 있는지 하나씩 따져 보는 확인이다.)

| X축 후보 | 무슨 일이 생기나 | 판정 |
| --- | --- | --- |
| $W$ | $W$를 고정해도 상한이 안 정해진다($Q$에 따라 달라짐). 한 x값에 y값이 여러 개 | 함수가 아니다 |
| $Q$ | 마찬가지로 $W$에 따라 달라진다 | 함수가 아니다 |
| $T$ | 구하려는 답이고, 양변에 다 있다 | 순환 |
| 문제 크기 $N$ | 같은 커널인데 $N$마다 점이 옮겨다닌다 | 커널 비교 불가 |
| $W/Q$ | 상한이 **이것만의 함수**. 곡선이 존재한다 | **유일한 생존자** |

SAXPY를 $N=10^6$과 $N=10^9$로 돌려 보면 $W$와 $Q$는 1000배 차이인데 성능 상한은 똑같다. $W$축이나 $Q$축에서는 이 두 실행이 멀리 떨어진 두 점이 되고, $I$축에서는 같은 점이 된다. 그래프의 목적이 "워크로드의 성격을 한 점으로 요약하기"이므로, 문제 크기에 따라 움직이는 축은 애초에 축이 될 자격이 없다.

**넷째, 단위가 이미 답을 정해 놓았다 — 가장 짧은 답.** $\pi$는 FLOP/s, $\beta$는 byte/s다. 단위가 달라서 서로 비교할 수 없다. 비교하려면 byte를 FLOP으로 바꿔 주는 환산율이 필요하고, 그 환산율의 단위는 반드시 다음과 같다.

$$
\frac{\text{FLOP/s}}{\text{byte/s}} = \text{FLOP/byte}
$$

그래서 X축은 FLOP/byte인 축일 수밖에 없다. 그런데 여기서 중요한 것이 하나 더 나온다. **FLOP/byte 단위를 갖는 값이 하나 더 있다.**

| 값 | 정체 | 그래프에서 |
| --- | --- | --- |
| $I = W/Q$ | 소프트웨어가 **제공하는** FLOP/byte | 점의 x좌표 |
| $I^{*} = \pi/\beta$ | 하드웨어가 **요구하는** FLOP/byte | ridge point의 x좌표 |

$\min$을 풀어 쓰면 이렇게 된다.

$$
\min(\pi, \beta I) = \pi \iff \beta I \geq \pi \iff I \geq \frac{\pi}{\beta}
$$

**병목 판정은 결국 이 두 FLOP/byte 값의 크기 비교다.** 루프라인은 소프트웨어의 FLOP/byte와 하드웨어의 FLOP/byte를 같은 자 위에 올려놓고 어느 쪽이 큰지 보는 그림이다. X축이 FLOP/byte여야 하는 이유가 여기서 끝난다. 다른 축이면 이 비교를 할 수가 없다.

- A100 FP32 코어 기준: $\pi \approx 19.5$ TFLOP/s, $\beta \approx 2.0$ TB/s → $I^{*} \approx 9.8$. SAXPY는 $I = 0.17 \lll 9.8$이라 메모리 바운드, GEMM은 $I \approx 170 \ggg 9.8$이라 연산 바운드다
- 같은 A100인데 텐서코어(저정밀도 행렬곱 전용 유닛으로, 별도의 더 높은 수평 지붕을 만든다) 기준($\pi \approx 312$ TFLOP/s FP16)이면 $I^{*} \approx 156$. **지붕을 어느 유닛 기준으로 그리느냐에 따라 ridge가 16배 움직인다.** 같은 GEMM이 FP32 지붕에서는 여유롭게 연산 바운드인데 텐서코어 지붕에서는 겨우 붙는 수준이 된다. 정밀도·유닛별로 지붕을 겹쳐 그려야 하는 이유다([정밀도·유닛](#정밀도유닛) 참고)

## 수평선과 사선

앞에서 얻은 $P = \min(\pi,\ \beta I)$를 $I$축 위에 그려 보면, 두 항이 서로 다른 모양의 선이 되어 그래프가 결국 '수평선 + 사선'으로 나타난다. 두 모양을 가르는 것은 **"$I$가 식에 있느냐 없느냐" 하나**다.

| 항 | $I$가 있나 | 모양 |
| --- | --- | --- |
| 연산 항 $\pi$ | 없다 ($W$가 약분되어 사라졌다) | $I$를 바꿔도 값이 안 변함 → **수평선** |
| 메모리 항 $\beta I$ | 있다 ($W$가 $W/Q$로 살아남았다) | $I$의 1차식 → **원점을 지나는 직선** |

메모리에서 $Q$ 바이트를 옮겨야 한다면 시간의 하한이 $T \geq Q/\beta$로 정해지고, 이걸 대입하면 $P \leq W/(Q/\beta) = (W/Q) \times \beta = I\beta$다. 즉 사선은 "기울기가 대역폭인 직선"이라기보다, **애초에 $P = I\beta$라는 식 자체가 직선**이다. log-log로 그리면 $\log P = \log I + \log \beta$라서 **기울기 1(45°)의 직선**이 되고, **$I=1$ 지점의 y값이 곧 $\beta$ 수치**가 된다. 아래 그림에서 $I=1$일 때 사선이 2를 지나가는 것이 그 이유다. 로그 축이 아니면 원점을 지나는 직선이고 진짜 기울기가 $\beta$가 된다.

![naive Roofline 모델 - 편집본]({{site.url}}/assets/images/roofline-model-roofline-ai-edited-image.png){: .align-center}

<center><sup>출처: <a href="https://en.wikipedia.org/wiki/Roofline_model">Wikipedia — Roofline model</a>의 naive roofline 그림을 편집했다. x축 라벨을 FLOP/byte로 수정하고 ridge point 표시를 추가했다.</sup></center>

**왜 로그 눈금인가.** 반드시는 아니지만 거의 항상 그렇게 그린다. 이유는 두 가지다. 첫째, $I$가 DAXPY 0.083부터 GEMM 수백까지 네 자릿수를 오간다. 선형 축에서는 왼쪽 끝에 다 뭉친다. 둘째, 로그로 그리면 $\beta$가 무엇이든 사선의 기울기가 정확히 1이 되어 여러 기계를 겹쳐 놓고 눈으로 비교할 수 있다. 대가로 거리 감각이 왜곡되므로 점과 지붕의 간격은 항상 **수직으로** 읽어야 한다([해석](#해석)에서 다시 본다).

## ridge point

그래프에서 수평선과 사선이 만나는 지점을 **ridge point**라고 한다. ridge point의 x좌표는 $I^{*} = \pi/\beta$이고, **machine balance**라고도 불린다. 이 점이 **이 기계에서 peak에 도달하기가 얼마나 어려운가를 나타내는 숫자**이기 때문이다. ridge가 오른쪽에 있을수록, peak 성능을 보려면 더 높은 재사용을 가진 커널만 자격이 있다는 뜻이다.

원논문이 ridge point를 정의하는 대목을 그대로 옮기면 아래와 같은데, 그 요지 역시 **ridge point의 x좌표는 peak 성능에 도달하는 데 필요한 최소 연산 강도**라는 것이다.

> Note that the *ridge point*, where the diagonal and horizontal roofs meet, offers an insight into the overall performance of the computer. The x-coordinate of the ridge point is the **minimum operational intensity required to achieve maximum performance**. If the ridge point is far to the right, then only kernels with very high operational intensity can achieve the maximum performance…
>
> — Williams, Waterman, Patterson, ["Roofline: An Insightful Visual Performance Model for Multicore Architectures", CACM 2009](https://escholarship.org/content/qt78h8v7mr/qt78h8v7mr.pdf)

원논문의 실측에서도 이 해석이 그대로 확인된다. **ridge point가 clock rate나 peak performance보다 성능을 더 잘 예측했고**, 측정된 커널 대부분이 ridge 왼쪽(메모리 바운드)이었다. 실무에서 만나는 대부분의 커널이 왼쪽에 있다는 이 사실이 루프라인이 유용한 이유다.


<details markdown="1">
<summary><b>참고: 원논문의 기계별 실측 ridge point (2009)</b></summary>

| 기계 | ridge point (FLOP/byte) | 성격 |
| --- | --- | --- |
| Intel Xeon | **6.7** | DP peak은 가장 높지만 도달이 가장 어렵다 |
| Opteron X4 | 4.4 |  |
| IBM Cell | 0.65 |  |
| Sun T2+ | **0.33** | peak은 낮지만 도달이 가장 쉽다 |

논문은 *"Cell offered the highest performance on these kernels, but T2+ was the easiest computer on which to achieve its highest performance. One reason is because ridge point of the Roofline model for T2+ was the lowest."*라고 쓴다. 논문이 측정한 16개(커널×기계) 조합의 연산 강도는 0.25~1.64, 중간값 0.60이었다. ridge point가 0.33~6.7이므로 거의 전부가 사선 쪽(메모리 바운드)이다.

</details>

**ridge point는 하드웨어 세대가 바뀔 때마다 오른쪽으로 밀려 왔다.** 연산 성능($\pi$)이 메모리 대역폭($\beta$)보다 빨리 늘어 둘의 격차가 계속 벌어진다는 컴퓨터 구조의 오래된 관찰을 **memory wall**이라 부르는데, ridge point가 정확히 그 두 값의 비율($I^{*} = \pi/\beta$)이라서 그 추세가 루프라인 위에서는 "ridge point의 우측 이동"이라는 숫자 하나로 나타난다. 실제 값의 궤적이 그렇다.

|  | ridge point (FLOP/byte, 대략) |
| --- | --- |
| 일반 CPU | 5~10 |
| V100 (FP16 텐서코어) | $\approx 139$ |
| A100 (FP16 텐서코어, 80GB) | $\approx 156$ |
| H100 (BF16 텐서코어, SXM) | $\approx 295$ |
| TPU v5e | $\approx 240$ |

값은 각 SKU 명판 스펙으로 계산한 대략치다(A100은 $\beta \approx 2.0$ TB/s 기준). **peak이 올라갈수록 그 peak에 도달할 자격을 갖춘 커널은 줄어든다.** 원논문의 Opteron X2 → X4가 이미 그랬다(ridge 1.0 → 4.4). 뒤집어 보면 **ridge가 낮은 기계는 "균형 잡힌" 것일 수도 있고 "연산이 빈약한" 것일 수도 있다.** 낮은 peak의 높은 비율을 달성하는 것은 쉽다. 그래서 ridge point는 단독으로 좋고 나쁨을 말하지 않고, peak 높이와 함께 읽어야 한다.

## π와 β의 출처

여기까지의 유도에서 $\pi$와 $\beta$는 하드웨어가 주는 상수로 두고 기호로만 썼다. 실제 하드웨어의 루프라인을 그리려면 이제 이 두 값을 어디서 얻는지가 남는다. 

이 값의 출처에 대한 위키피디아의 서술을 그대로 옮기면 아래와 같다. 앞 반절(two parameters, one variable) — $\pi$·$\beta$는 그리기 전에 **고정**되어 **지붕의 모양을 결정**하는 파라미터고, $I$만 **변수**로 남아 점이 지붕 위 어디에 서는지를 정한다는 역할 구분 — 은 [변수 I](#변수-i)에서 이미 뜯었다. 이 절의 관심은 뒷반절이다 — **$\pi$는 벤치마킹으로, $\beta$는 아키텍처 매뉴얼로 얻는다는 출처의 비대칭.**

> The naive roofline is obtained by applying simple bound and bottleneck analysis. In this formulation of the roofline model, there are only **two parameters**, peak performance and peak bandwidth, and **one variable**, arithmetic intensity. The peak performance, in general expressed as GFLOPS, can be usually derived from benchmarking, while the peak bandwidth, that references to peak DRAM bandwidth to be specific, is instead obtained via architectural manuals
>
> — [Wikipedia — Roofline model](https://en.wikipedia.org/wiki/Roofline_model)

위키피디아가 두 파라미터의 출처를 다르게 적어 놓은 것($\pi$는 benchmarking, $\beta$는 architectural manuals)이 헷갈리는 지점인데, 모순이 아니라 둘의 성질이 다르다는 얘기다.

|  | 스펙 시트에 있나 | 왜 그런가 | 실무에서 |
| --- | --- | --- | --- |
| $\pi$ (peak FLOP/s) | 있지만 **여러 개** 있다 | FP64/FP32/FP16/FP8, FMA 유무, SIMD 폭, 텐서코어 사용 여부에 따라 값이 다 다르다. 어느 것이 이 커널의 실질 상한인지는 재 봐야 안다 | GEMM 스윕 등 마이크로벤치마크로 확인 |
| $\beta$ (peak bandwidth) | 산술적으로 명시된다 | (버스 폭 × 클럭 × 채널 수)로 계산되는 값이라 매뉴얼에 하나로 적힌다 | 실측은 보통 명판의 80~90% (STREAM, babelstream) |

실무 결론은 **둘 다 스펙에서 시작해서 실측으로 보정**이다. 원논문도 *"We measured the roofline and ceilings using microbenchmarks."*라고 적어 두었다. 명판 값으로 지붕을 그리면 점이 지붕을 뚫는 것처럼 보이거나, 반대로 도달 불가능한 목표를 잡게 된다.

**derived라는 표현을 쓰는 이유**도 짚어 둘 만하다. 위키피디아 원문은 두 지붕 모두에 derived를 붙인다 — *"a ceiling derived from the memory bandwidth and one derived from the processor's peak performance"*. 지붕은 하드웨어 스펙 그 자체가 아니라 **스펙으로부터 계산해 낸 선**이기 때문이다. 연산 지붕은 (코어 수 × 클럭 × 코어당 FLOP)으로 유도하고, 대역폭 지붕은 byte/s를 y축 단위인 FLOP/s로 환산($\beta I$)해서 유도한다. 특히 대역폭 쪽은 단위 변환이 필요하므로 "유도"의 의미가 더 강하다. 대역폭 자체는 그래프에 직접 그릴 수 없고, $I$를 곱해야 비로소 선이 된다.

<br>

# 해석

## 2단 판단

이제 그려진 그래프를 읽는 법이다. 위키피디아가 이 그래프를 정의하는 문장을 그대로 옮기면 아래와 같다. 그래프의 구성 요소 두 가지를 명확히 알려준다. 

> The most basic roofline model can be visualized by plotting floating-point performance as a function of machine peak performance, machine peak bandwidth, and arithmetic intensity. The relevant curve is effectively a **performance bound** under which **kernel or application performance** exists, and includes two **platform-specific performance ceilings**: a ceiling derived from the memory bandwidth and one derived from the processor's peak performance
>
> — [Wikipedia — Roofline model](https://en.wikipedia.org/wiki/Roofline_model)

**선은 하드웨어가 정하는 상한 두 개**(two platform-specific performance ceilings)이고, **그 아래에 찍히는 점이 워크로드의 실측 성능**(kernel or application performance)이다. 

![Roofline 모델 예시 - Wikipedia]({{site.url}}/assets/images/roofline-model-example.png){: .align-center}

<center><sup><a href="#개념">개념 절</a>에서 본 그림을 다시 가져왔다. 출처: <a href="https://en.wikipedia.org/wiki/Roofline_model">Wikipedia — Roofline model</a></sup></center>

**선은 하드웨어 스펙이 결정하는 상한**, 즉 지붕(platform-specific performance ceilings)이고 두 가지가 있다.

| 지붕 | 그래프에서 모양 | 무엇으로 유도하나 |
| --- | --- | --- |
| processor's peak performance에서 유도한 지붕 | 수평선 (기울기 0) | SM/코어 수 × 클럭 × 코어당 FLOP, FMA·텐서코어 유무 |
| memory bandwidth에서 유도한 지붕 | 기울기 1의 사선 | HBM/DDR 대역폭(byte/s)에 $I$를 곱해 환산 |

**점은 워크로드의 실측점**이다(*performance estimates of a given compute kernel or application*). **(FLOP, byte, time) 세 값이 하나로 정의되는 측정 단위**라면 무엇이든 점이 된다. 커널일 수도, 루프일 수도, 애플리케이션 전체일 수도 있다.

| 구분 | 영어 | 비고 |
| --- | --- | --- |
| 점의 **주체**(측정 단위) | workload (중립) / kernel, loop nest, function, application | kernel은 CUDA 어감이 강해 GPU 한정으로 읽히기 쉽다. CPU 쪽은 보통 loop nest |
| 점의 **y좌표** | attained performance | 원논문 용어. achieved performance도 통용 |
| 점의 **x좌표** | operational intensity | 원논문 용어 (arithmetic intensity는 관습적 별칭) |
| 점 **자체** | achieved value / dot | Nsight Compute는 "Achieved Value" 라벨, Intel Advisor는 "dot"이라 부르며 "each dot = a loop or function"이라고 설명한다 |

**지붕 위쪽에 점이 찍히는 경우는 없다.** 지붕은 하드웨어의 상한을 그려 놓은 곳이므로 물리적으로 불가능하다. 그렇게 나왔다면 측정이나 지붕이 틀렸다는 신호이고, 의심할 원인은 다음과 같다.

- FLOP을 세는 기준이 다름 (FMA를 2로 안 셌거나, model FLOPs와 hardware FLOPs 혼용)
- 정밀도 불일치 (FP16으로 돌린 것을 FP32 지붕에 그림)
- 대역폭 지붕을 HBM 기준으로 그렸는데 실제로는 캐시에서 재사용된 경우 (x축이 과소평가된 것)

**읽는 순서는 2단이다.** 순서를 바꾸면 오진한다.

1. **점이 지붕에 붙었나?** = 아직 남은 여유가 있나
2. **붙었다면 어느 쪽 지붕인가?** = 무엇이 지붕인가 → 무엇을 바꿔야 하나

![Roofline 읽는 순서 - 2단 판단 도해]({{site.url}}/assets/images/roofline-model-reading-order.png){: .align-center}

<center><sup>직접 제작한 그림</sup></center>

> **좌우 구분은 지붕에 붙은 다음에야 의미가 생긴다.** 지붕에서 떨어져 있을 때는 왼쪽이든 오른쪽이든 진단이 같다 — "아직 하드웨어 지붕이 원인이 아니다, 돌리는 방식이 문제다." 대역폭 지붕에도 연산 지붕에도 닿지 못했으니 어느 쪽을 탓할 근거가 없다. 도입에서 본 전력 156W 케이스가 정확히 여기에 해당한다.

| 점의 위치 | 진단 | 무엇을 해야 하나 |
| --- | --- | --- |
| 지붕에서 떨어져 있다 | 아직 하드웨어 지붕이 원인이 아니다. **이때는 좌우 위치가 의미 없다** | 돌리는 방식을 점검 — 메모리 접근 패턴, 병렬성 부족, 커널 실행·동기화 오버헤드, 데이터 공급 지연 |
| 사선 지붕에 붙었다 (ridge 왼쪽) | 데이터 이동이 지붕 | 오가는 데이터를 줄여 점을 **오른쪽으로** 밀기 — 연산 합치기, 재사용·타일링, 데이터를 작게 표현, 배치 늘리기 |
| 수평 지붕에 붙었다 (ridge 오른쪽) | 계산이 지붕 | 계산의 양 자체를 줄이거나 더 빠른 연산 유닛으로 — 알고리즘 교체, 전용 유닛 사용 |
| 지붕 위에 있다 | 일어날 수 없는 일 | 측정값이나 지붕 설정이 틀렸다는 신호 — 세는 기준, 정밀도, 어느 지붕을 그렸는지 확인 |

## 점의 이동 방향

점을 움직일 수 있는 방향은 두 가지뿐이다.

- **위로** = 성능 자체를 올리기. 지붕에서 떨어져 있을 때만 가능하다
- **오른쪽으로** = 연산 강도를 키우기. $W$를 늘리는 게 아니라 **$Q$를 줄이는 것**이 정석이다. 사선에 붙었을 때 유일한 탈출구다. 오른쪽으로 가면 사선이 높아지니 점도 따라 올라간다

거리는 **수직으로** 봐야 한다. 로그 축이라 눈대중으로 대각선 거리를 재면 틀린다. 어느 지붕에 붙었을 때 무엇을 손대는지(처방)는 [2단 판단](#2단-판단) 표에 이미 정리돼 있다. 한 가지만 덧붙이면 — 사선(메모리)에 붙었을 때 데이터를 작게 표현하는 것(저정밀도·양자화)은 같은 연산에 $Q$를 줄여 $I$를 키우는 일이라, **양자화가 "메모리 절약"이 아니라 "연산 강도를 올리는 수단"으로 보이는 것이 루프라인 관점**이다.

## 중첩 지붕

실제 자료에서 만나는 루프라인은 지붕이 여러 겹인 경우가 많다. 겹치는 대상은 세 종류이고, 각각 읽는 법이 다르다.

| 종류 | 무엇을 겹치나 | 대표 예 |
| --- | --- | --- |
| **서로 다른 하드웨어** | 기계 A의 지붕 vs 기계 B의 지붕 | 아래 그림 — TPU·K80·Haswell 비교 |
| **같은 칩의 메모리 계층** | L1 / L2 / HBM 사선 여러 개 | 아래 그림 — L1/L2/HBM 사선 |
| **같은 칩의 정밀도·유닛** | FP64/FP32/FP16/FP8 수평선, FMA 유무, CUDA core/Tensor core | 아래 그림 — FP32/FP16/FP8 지붕 |

### 하드웨어 비교

내 워크로드의 $I$ 위치에서 **수직선을 하나 긋는다.** 그 수직선이 각 지붕과 만나는 **높이의 비**가 곧 하드웨어를 바꿔서 얻을 수 있는 상한의 배수다. 여기서 두 가지가 바로 보인다.

- 내 $I$가 두 기계의 ridge point보다 **왼쪽**이면, 두 지붕의 높이 비 = **대역폭의 비**다. 연산 능력이 몇 배 좋아졌든 의미가 없다
- 내 $I$가 둘 다보다 **오른쪽**이면, 높이 비 = **peak 연산 능력의 비**다
- 덧붙여 [ridge point](#ridge-point)끼리 비교하면 "이 기계에서 peak에 도달하기가 얼마나 어려운가"가 나온다

![서로 다른 하드웨어의 roofline 비교]({{site.url}}/assets/images/roofline-model-different-hw.png){: .align-center}

<center><sup>출처: <a href="https://community.cadence.com/cadence_blogs_8/b/breakfast-bytes/posts/neural-nets-hit-the-roofline-memory-for-ai">Cadence Breakfast Bytes</a>. 원 그림은 TPU v1 논문(Jouppi et al., ISCA 2017)의 roofline이다. x축이 전체 트래픽이 아니라 가중치 바이트만 세는 Ops/weight byte 변형이라는 점에 주의.</sup></center>

### 메모리 계층

사선이 여러 개(L1/L2/HBM)다. 여기서 가장 중요한 주의점은, 계층을 바꾸면 트래픽의 기준이 바뀌므로 **지붕만이 아니라 점의 x좌표도 함께 움직인다**는 것이다. 지붕만 겹쳐 놓고 점을 그대로 두면 틀린 그림이 된다. 제대로 그렸다면 이렇게 읽는다.

- HBM 사선에는 붙었는데 L2 사선에는 여유가 있다 → DRAM 대역폭은 다 썼지만 캐시 재사용을 더 짜낼 수 있다. 타일링 여지가 있다
- L2 사선에 붙었다 → 캐시 대역폭이 병목. 데이터를 더 안쪽(레지스터·shared memory)에서 돌려야 한다

![메모리 계층별 roofline]({{site.url}}/assets/images/roofline-model-memory-hierarchical.png){: .align-center}

<center><sup>출처: <a href="https://www.scientific-computing.com/hpc2018-19/the-roofline-model">Scientific Computing World — The Roofline Model</a></sup></center>

### 정밀도·유닛

수평선이 여러 개다. 점이 낮은 수평선에 붙어 있고 그 위에 더 높은 수평선이 비어 있다면, **그 간격이 정밀도 변경이나 텐서코어 활용으로 얻을 수 있는 여유**다. FP32 코어 지붕에 붙어 있고 텐서코어 지붕이 훨씬 위에 있다면 답이 명확하다.

![정밀도·유닛을 겹쳐 그린 지붕]({{site.url}}/assets/images/roofline-model-precision-units.png){: .align-center}

<center><sup>직접 그린 도식. 실제 사례로는 [LLM Inference Unveiled](https://arxiv.org/abs/2402.16363)이 A6000의 유닛별 지붕을 겹쳐 그린 그림이 이 유형이다.</sup></center>

이 외에 에너지 roofline(J 기준), instruction roofline(FLOP 대신 인스트럭션) 같은 변종도 있는데, 전부 같은 뼈대다.

<br>

# 측정

필요한 값은 $W$, $Q$, $T$ 세 개뿐이고, 나머지는 다 이 셋의 조합이다. 이 셋만 있으면 커널이나 애플리케이션의 성능 점을 잡을 수 있다. 원리적으로는 손으로 세어 볼 수도 있지만 — 손계산은 "이 커널이 어디쯤 있어야 하는가"를 가늠하는 용도다 — 실무에서는 프로파일러로 내 커널·애플리케이션의 실제 값을 측정해 점을 찍는다.

$$
P = \frac{W}{T}, \qquad I = \frac{W}{Q}, \qquad \frac{W}{T} = \frac{W}{Q} \times \frac{Q}{T}
$$

마지막 식이 유용하다. **달성 성능 = 연산 강도 × 달성 대역폭.** 점의 y좌표는 x좌표에 실제 대역폭을 곱한 값이므로, 사선에서 얼마나 떨어졌는지가 곧 대역폭을 얼마나 못 쓰고 있는지다.

| 값 | 측정 방법 | Nsight Compute 카운터 |
| --- | --- | --- |
| $W$ (FLOP) | 해석적 계산(GEMM = $2MNK$) 또는 인스트럭션 카운터 | `sm__sass_thread_inst_executed_op_ffma_pred_on.sum` ×2에 `fadd`·`fmul` 합산, 텐서코어는 `sm__ops_path_tensor_*` 별도 |
| $Q$ (byte) | 실제 DRAM 트래픽 (텐서 크기 아님) | `dram__bytes_read.sum`, `dram__bytes_write.sum` |
| $T$ | 커널 실행 시간 | `gpu__time_duration.sum` |
| $\pi$ 지붕 | GEMM 스윕 등 마이크로벤치마크 | — |
| $\beta$ 지붕 | 스펙값 또는 실측(STREAM/babelstream). 보통 스펙의 80~90% | — |

실무 흐름은 **점 찍기**와 **지붕 그리기**가 따로다.

**점 찍기(커널별 좌표).** Nsight Compute가 자동으로 해 준다.

```bash
# 커널마다 roofline 점을 찍어 리포트 생성
# (계층별 차트는 --section SpeedOfLight_HierarchicalDoubleRooflineChart)
ncu --set roofline -o report ./my_app
```

숫자를 직접 뽑으려면 카운터를 지정해 손으로 조합한다.

```bash
ncu --metrics \
  sm__sass_thread_inst_executed_op_ffma_pred_on.sum,\
  sm__sass_thread_inst_executed_op_fadd_pred_on.sum,\
  sm__sass_thread_inst_executed_op_fmul_pred_on.sum,\
  dram__bytes_read.sum,dram__bytes_write.sum,\
  gpu__time_duration.sum ./my_app

# FP32: W = 2×FFMA + FADD + FMUL,  Q = read + write,  T = duration
# → I = W/Q (x좌표),  P = W/T (y좌표)
```

CPU는 Intel Advisor(`advisor --collect=roofline -- ./app`)가 루프마다 점을 찍는다. PyTorch는 `torch.utils.flop_counter.FlopCounterMode`로 $W$만 빠르게 얻고, `torch.cuda.max_memory_allocated`는 $Q$의 대용이 못 되므로 $Q$·$T$는 ncu를 병행한다.

**지붕 그리기(π·β).** 점과 별개로 마이크로벤치마크에서 뽑는다 — β는 STREAM/babelstream, π는 GEMM 스윕. 버클리랩 ERT(Empirical Roofline Tool)를 쓰면 π·β에 계층별 대역폭까지 한 번에 나온다. 스펙 시트 값을 그대로 써도 대략적인 그림은 되지만, **명판은 이론 최대치라 실제로는 그 80~90%만 나온다**(자세히는 [π와 β의 출처](#π와-β의-출처)).

> **$Q$가 함정이다.** "이론상 텐서 크기"가 아니라 **실측 DRAM 트래픽**이다. 그래서 실측 연산 강도는 알고리즘 고유 상수가 아니라 캐시 히트율에 따라 변하는 측정값이다([이론 I vs 실측 I](#이론-i-vs-실측-i)). 타일링을 잘 하면 같은 GEMM도 DRAM 트래픽이 줄어 점이 오른쪽으로 이동한다.

측정할 때 주의할 것이 둘 있다. 클럭이 흔들리면 지붕과 점이 같이 흔들린다(`nvidia-smi -lgc`로 고정). 그리고 명판 대역폭으로 지붕을 그리고 실측 트래픽으로 점을 찍으면 계통 오차가 한쪽으로만 쌓인다 — **지붕과 점은 같은 기준으로** 만들어야 한다.

도입의 사례를 이 틀로 다시 보면, `GPU_UTIL` 96~100%인데 `DRAM_ACTIVE` 6%, `PIPE_TENSOR_ACTIVE` 약 1%는 **두 지붕 어디에도 닿지 않은 상태**다. 점이 지붕에서 한참 아래에 있다. 하드웨어를 바꿀 문제가 아니라 돌리는 방식의 문제다.

<br>

# 적용

## 성립 조건

GPU 관련 계기로 알게 되었지만 GPU 전용으로 성립하는 모델이 아니다. Roofline 모델을 처음 제시한 원논문(Williams, Waterman, Patterson, CACM 2009)부터가 **멀티코어 CPU**를 대상으로 나왔다.

![원논문 Figure 1 - Opteron X2 roofline과 X2 vs X4 비교]({{site.url}}/assets/images/roofline-model-paper-figure-1.png){: .align-center}

<center><sup>출처: <a href="https://escholarship.org/content/qt78h8v7mr/qt78h8v7mr.pdf">원논문(Williams et al., 2009)</a> Figure 1 — AMD Opteron X2의 roofline(왼쪽)과 X2 vs X4 비교(오른쪽)</sup></center>

위키피디아의 roofline 정의는 이렇게 시작한다.

> ...performance estimates of a given *compute kernel or application* running on multi-core, many-core, or accelerator processor architectures...
>
> — [Wikipedia — Roofline model](https://en.wikipedia.org/wiki/Roofline_model)

여기서 *compute kernel*이라는 단어 때문에 가속기 한정으로 읽히기 쉬운데, 위키피디아의 별도 compute kernel 문서는 GPU·DSP·FPGA 문맥의 좁은 정의를 설명하지만, roofline 문서의 *"compute kernel or application"*은 그 좁은 뜻이 아니라 **측정 단위**라는 뜻이다. 근거는 세 가지다.

- 원논문의 대상 기계는 멀티코어 CPU 넷이고, 커널은 SpMV(희소 행렬-벡터 곱) 같은 CPU 루프다
- 논문은 *"Note that these limits are created once per multicore computer, not once per kernel."*이라고 쓴다. 커널을 가속기 코드로 한정하지 않는다
- Intel Advisor는 CPU 루프를 점으로 그리며 "each dot = a loop or function"이라고 설명한다

결국 필요한 조건은 하나뿐이다 — **$(W, Q, T)$ 세 값이 하나로 정의되는 실행 단위인가.** 그래서 모델의 성립 조건도 둘로 요약된다. **처리량 상한이 있는 자원 두 개**, 그리고 **둘 사이의 작업량 비율**. 이 틀을 다른 자원 쌍에 대입해 보면 아래처럼 된다. 분산학습처럼 실제로 쓰이는 확장도 있지만, DB·웹서비스 행은 모델이 정립되어 있다기보다 같은 뼈대를 이식해 본 유추에 가깝다.

| 도메인 | X축 (강도) | 사선 | 수평 |
| --- | --- | --- | --- |
| GPU/CPU | FLOP/byte | HBM 대역폭 | peak FLOP/s |
| 분산학습 | FLOP/전송 byte | NVLink/IB 대역폭 | 노드 연산력 |
| DB 쿼리 | 튜플당 CPU 작업 | 디스크 IOPS | 코어 처리량 |
| 웹서비스 | 요청당 CPU | NIC 대역폭 | CPU 코어 |
| FPGA/ASIC | 연산/DRAM byte | 외부 메모리 | MAC 수 |

이 틀을 LLM 서빙 워크로드에 실제로 적용하는 것은 [2편 — Roofline 모델로 보는 LLM 서빙]({% post_url 2026-08-21-Dev-Roofline-Model-LLM-Serving %})에서 다룬다. 워크로드를 최소 세 점(prefill·decode-FFN·decode-attention)으로 나눠 찍어야 하는 이유와 기법별 처방을 거기서 정리한다.

<br>

# 정리

한 문단으로 요약하면 이렇다. 어떤 연산이든 "계산하기"와 "데이터 옮기기"를 해야 하고, 각각에는 하드웨어가 정한 처리율 상한 $\pi$와 $\beta$가 있다. 둘이 완전히 겹친다고 가정하면 시간의 하한은 $\max(W/\pi, Q/\beta)$이고, 이것을 성능 $P = W/T$로 옮기면 $P \leq \min(\pi, \beta I)$가 된다. 이 식에서 $W$와 $Q$는 **비율 $I = W/Q$로만** 살아남기 때문에 2차원 그래프가 가능해지고, 그 비율이 X축이 된다. 그리고 $\pi/\beta$도 같은 FLOP/byte 단위이므로, **루프라인은 결국 소프트웨어의 FLOP/byte와 하드웨어의 FLOP/byte를 비교하는 그림**이다.

실제 판단은 두 단계다.

- 점이 지붕에 붙었나? → 안 붙었으면 $P$를 올려야 한다 (돌리는 방식의 문제)
- 붙었으면 어디에 붙었나? → 사선이면 $Q$를 줄이고, 수평이면 $W$를 줄이거나 더 높은 지붕으로 옮겨탄다

| 상태 | 진단 | 손댈 곳 |
| --- | --- | --- |
| 지붕에서 멀다 | 아직 하드웨어 한계가 아니다 | 접근 패턴, occupancy, 커널 오버헤드 |
| 사선 지붕에 붙었다 | 데이터 이동이 병목 | $Q$ 줄이기 — 양자화, 퓨전, 타일링, 배칭 |
| 수평 지붕에 붙었다 | 연산기가 병목 | $W$ 줄이기, 알고리즘 변경 |
| 더 높은 지붕이 비어 있다 | 유닛을 못 쓰고 있다 | 정밀도 변경, 텐서코어 |
| 다 했는데 부족하다 | 그때가 하드웨어 | 어느 스펙을 볼지는 어느 지붕에 붙었는지가 알려준다 |

이 모델의 의의를 위키피디아 정의로 다시 읽어 본다.

> intuitive visual performance model used to provide performance estimates of a given compute kernel or application running on multi-core, many-core, or accelerator processor architectures, by showing inherent hardware limitations, and potential benefit and priority of optimizations

> By **combining** locality, bandwidth, and different parallelization paradigms into a **single** performance figure, the model can be an effective alternative to assess the quality of attained performance instead of using simple percent-of-peak estimates, as it provides insights on both the implementation and inherent performance limitations

*single performance figure*는 따로따로 보고되던 세 가지가 한 장의 그림에 들어간다는 뜻이다.

| 원문 | 그래프의 어디에 들어갔나 |
| --- | --- |
| locality (캐시 재사용) | **x축** — 재사용이 곧 $I$ ([손계산](#연산-강도-손계산)) |
| bandwidth | **사선** |
| parallelization paradigms (코어·SIMD·FMA·텐서코어) | **수평선의 높이**, 그리고 여러 층의 지붕 |

percent-of-peak보다 나은 이유도 여기서 나온다. percent-of-peak은 "peak의 12%"라는 한 숫자만 주고 **왜 12%인지, 12%가 나쁜 것인지**를 말하지 못한다. 루프라인은 상한 자체가 워크로드의 $I$에 따라 달라지므로, "이 커널은 이 기계에서 원래 이 이상 갈 수 없다"와 "이 커널은 갈 수 있는데 못 가고 있다"를 구분해 준다. 도입의 `GPU_UTIL` 96% 의문이 정확히 이 구분을 필요로 했던 문제다.

용어를 최종 정리하면 아래와 같다.

| 용어 | 기호 | 단위 | 정체 | 그래프에서 |
| --- | --- | --- | --- | --- |
| peak performance | $\pi$ | FLOP/s | 하드웨어 | 수평선의 높이 |
| memory bandwidth | $\beta$ | byte/s | 하드웨어 | 사선 (로그축에서 $I=1$일 때의 y값) |
| attained performance | $P$ | FLOP/s | 측정값 | 점의 y좌표 |
| operational intensity | $I$ | FLOP/byte | 워크로드 + 캐시 | 점의 x좌표 |
| machine balance / ridge point | $I^{*} = \pi/\beta$ | FLOP/byte | 하드웨어 | 지붕이 꺾이는 x |

> arithmetic bandwidth라는 용어는 표준이 아니다. 문맥상 가리키려는 것은 대개 $\beta$(memory bandwidth)이거나 $\pi/\beta$(machine balance)이므로, 둘 중 하나로 명시해서 쓰는 편이 낫다. 또한 arithmetic intensity와 operational intensity는 흔히 동의어로 쓰이지만, 원논문은 후자를 '프로세서↔캐시'가 아니라 '캐시↔DRAM' 트래픽을 재는 뜻으로 구별해 만들었다 — 그래서 원논문 용어인 operational intensity를 쓰는 편이 안전하다.

<br>

# 참고 링크

- [Williams, Waterman, Patterson, "Roofline: An Insightful Visual Performance Model for Multicore Architectures", CACM 2009](https://escholarship.org/content/qt78h8v7mr/qt78h8v7mr.pdf)
- [Wikipedia — Roofline model](https://en.wikipedia.org/wiki/Roofline_model)
- [Modal GPU Glossary — Roofline Model](https://modal.com/gpu-glossary/perf/roofline-model)
- [Cadence Breakfast Bytes — Neural Nets Hit the Roofline](https://community.cadence.com/cadence_blogs_8/b/breakfast-bytes/posts/neural-nets-hit-the-roofline-memory-for-ai)
- [Scientific Computing World — The Roofline Model](https://www.scientific-computing.com/hpc2018-19/the-roofline-model)
- [NERSC — Roofline Performance Model](https://docs.nersc.gov/tools/performance/roofline/)
- [Berkeley Lab — Empirical Roofline Tool (ERT)](https://bitbucket.org/berkeleylab/cs-roofline-toolkit/)
- [LLM Inference Unveiled: Survey and Roofline Model Insights (arXiv:2402.16363)](https://arxiv.org/abs/2402.16363)
- [Hong, Kung, "I/O Complexity: The Red-Blue Pebble Game", STOC 1981](https://dl.acm.org/doi/10.1145/800076.802486)
- [Kung, "Memory Requirements for Balanced Computer Architectures", ISCA 1986](https://dl.acm.org/doi/10.1145/17356.17362)
- [LLM 서빙과 최적화 3.3편 — prefill과 decode]({% post_url 2026-08-14-Dev-LLM-Serving-Optimization-03-03-LLM-Serving-Prefill-Decode %})
- [2편 — Roofline 모델로 보는 LLM 서빙: 세 점으로 나눠 찍는 병목]({% post_url 2026-08-21-Dev-Roofline-Model-LLM-Serving %})

<br>
