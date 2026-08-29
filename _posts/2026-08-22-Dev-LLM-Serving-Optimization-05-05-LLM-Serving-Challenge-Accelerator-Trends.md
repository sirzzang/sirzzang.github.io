---
title: "[LLM] LLM 서빙과 최적화: LLM 서빙의 도전 과제 - 5.5. AI 가속기 지형과 메모리 벽"
excerpt: "NVIDIA 밖 AI 가속기 지형과 메모리 벽 완화 트렌드를 살펴보고 5장을 정리해 보자."
categories:
  - Dev
toc: true
header:
  teaser: /assets/images/blog-Dev.jpg
tags:
  - AI-Accelerator
  - TPU
  - NPU
  - Memory-Wall
  - SRAM
  - NVL72
  - Hands-On-LLM-Serving-and-Optimization-Study
  - Hands-On-LLM-Serving-and-Optimization-Study-Week-3
last_modified_at: 2026-08-29
---

*[서종호(가시다)](https://www.linkedin.com/in/gasida99/)님의 Hands-On LLM Serving and Optimization Study (LLMSO) 3주차 학습 내용을 기반으로 합니다.*

<br>

# TL;DR

- 시리즈 내내 NVIDIA GPU만 봤지만, 모델이 로드되고 실행되는 핵심 원리(용량 → 대역폭 → 인터커넥트, 산술 강도 판정)는 TPU·NPU 등 다른 칩에서도 동일하다
- 지난 20년간 연산 성능(FLOPS)은 폭발적으로 늘었지만 메모리·인터커넥트 대역폭은 훨씬 느리게 개선됐다. 이 격차가 "메모리 벽(memory wall)"이고, decode가 항상 memory-bound인 상황을 세대가 갈수록 심화시킨다
- 메모리 벽을 완화하는 두 트렌드: 대량의 온칩 SRAM으로 데이터를 연산 옆에 두는 접근(Groq·Cerebras 계열)과, NVLink 도메인을 랙 전체로 키우는 긴밀 결합 멀티 GPU 시스템(GB200 NVL72)
- 5장의 결론: 하드웨어 스펙을 읽는 법, 모델이 그 위에서 동작하는 방식, 병목을 판별하는 직관은 칩과 아키텍처가 바뀌어도 유효한 자산으로 남는다

<br>

# AI 가속기 지형

[5.2편]({% post_url 2026-08-22-Dev-LLM-Serving-Optimization-05-02-LLM-Serving-Challenge-GPU-Compute-Memory %})부터 NVIDIA GPU만 다뤘지만, 모델이 로드되고 실행되는 핵심 원리는 다른 칩에서도 동일하다. LLM 추론 시장에서 경쟁하는 칩들을 책은 이렇게 분류한다.

| 분류 | 대표 | 성격 |
| --- | --- | --- |
| 범용 대안 | AMD MI300X, Intel Gaudi 2 | NVIDIA H100/A100의 직접 대안 |
| 클라우드 전용 | Google TPU, Amazon Inferentia | 각 클라우드에서만 주로 사용 가능 |
| 지역 제약 시장 대안 | Huawei Ascend NPU | NVIDIA가 규제받는 시장에서 주목 |
| 스타트업 | Groq, Cerebras, Untether AI, SambaNova, d-Matrix 등 | 특화 아키텍처로 차별화 |

그럼에도 2026년 초 기준 NVIDIA가 시장을 지배하는 이유를 책은 네 가지로 정리한다.

- **범용성 vs 특화**: 일부 경쟁 칩은 추론·행렬곱·트랜스포머 워크로드에 특화되어 구조가 단순하고 비용·에너지 효율이 좋지만, 모델 아키텍처가 빠르게 진화하는 상황에 대응하기 어렵다
- **소프트웨어 생태계**: CUDA 생태계는 학습·추론 모두에서 성숙해 있다. 커스텀 칩은 각자 독자 스택(AMD ROCm, TPU의 JAX, Inferentia의 Neuron)이 필요해 전환 비용이 크고 커뮤니티 지원이 부족하다
- **온칩 SRAM 칩의 비용 구조**: SRAM 중심 칩은 지연 시간 성능이 뛰어나지만 SRAM 자체가 비싸고, 모델 하나를 서빙하는 데 필요한 칩 수가 많아 비용 효율이 떨어지는 경우가 많다
- **유연성**: FP8·FP4 등 다양한 정밀도, 높은 메모리 대역폭, 고급 인터커넥트까지 다양한 추론 구성에 대응하는 폭에서 여전히 우위다

<br>

# 메모리 벽

가속기 제조사들이 공통으로 마주한 문제가 있다. 지난 20년간 연산 성능(FLOPS)은 폭발적으로 향상된 반면, 메모리 대역폭과 GPU 간 인터커넥트 대역폭 같은 데이터 이동 속도는 훨씬 느리게 개선되어 왔다는 것이다.

![하드웨어 피크 FLOPS, 메모리 대역폭, 인터커넥트 대역폭의 스케일링 추세 격차]({{site.url}}/assets/images/llmso-flops-memory-interconnect-scaling.png){: .align-center width="720"}

<center><sup>출처: Hands-On LLM Serving and Optimization (O'Reilly), Figure 5-17</sup></center>

결과적으로 데이터 이동의 한계가 빠른 연산 발전을 제대로 활용하지 못하게 막는 걸림돌이 됐고, 이를 **메모리 벽(memory wall)** 이라 부른다. [5.4편]({% post_url 2026-08-22-Dev-LLM-Serving-Optimization-05-04-LLM-Serving-Challenge-Loading-Execution-Bottleneck %})에서 본 "decode는 항상 memory bandwidth-bound"라는 결론과 붙여 읽으면 문제의 심각성이 보인다. 연산과 대역폭의 격차가 벌어질수록 [Roofline 모델]({% post_url 2026-08-21-CS-Roofline-Model %}#ridge-point)의 ridge point가 오른쪽으로 밀리고, 산술 강도가 1 근처에 고정된 decode는 세대가 갈수록 상대적으로 더 왼쪽에 갇힌다.

<br>

# 완화 트렌드

메모리 벽에 대응하는 최신 트렌드를 책은 두 갈래로 정리한다.

## 온칩 SRAM 접근

첫 번째는 연산을 데이터에 더 가깝게 끌어오는 방향이다. 대량의 온칩 SRAM을 활용해 모델 파라미터와 중간 데이터를 연산 유닛 바로 옆에 유지하면 메모리 접근 지연이 크게 줄어든다. 비용은 비싸지만 극도로 낮고 예측 가능한 지연 시간을 달성할 수 있어, 지연에 민감한 추론 워크로드에 매력적이다. Groq·Cerebras 같은 스타트업이 이 계열이고, 책은 일부 추론 워크로드에서는 극한의 저지연이 피크 처리량보다 더 가치 있을 수 있다는 인식이 업계에 퍼지고 있다고 정리한다 — 실리콘 비용이 더 들고 모델을 여러 칩에 신중히 분할해야 하더라도 그렇다.

## 랙 스케일 확장

두 번째는 긴밀하게 결합된 멀티 GPU 시스템 전체로 성능을 확장하는 방향이다. 대표 사례가 NVIDIA의 랙 스케일 아키텍처 GB200 NVL72로, 이름의 세 부분이 각각 다른 층을 가리킨다.

- **B200**: Blackwell 세대 GPU
- **GB200**: Grace CPU와 Blackwell GPU를 NVLink-C2C로 연결한 빌딩 블록. CPU-GPU 간 데이터 전송 오버헤드를 줄인다 — 메모리 벽 대응이 CPU 계층까지 확장된 셈이다
- **NVL72**: NVLink Switch System으로 Blackwell GPU 72개를 하나의 거대한 NVLink 도메인으로 묶은 랙 스케일 시스템

결과적으로 랙 하나에 Grace CPU 36개와 Blackwell GPU 72개가 연결된다. [5.3편]({% post_url 2026-08-22-Dev-LLM-Serving-Optimization-05-03-LLM-Serving-Challenge-GPU-Interconnect-Selection %})에서 본 "NVLink 도메인 = 노드 내 8장"의 경계가 랙 전체로 올라간 것으로, 텐서 병렬을 걸 수 있는 범위가 8장에서 72장이 된다. 이 경계 이동을 가능하게 한 물리(액랭, 랙 내부 구리 배선)는 [GPU 패키징과 노드 경계]({% post_url 2026-08-21-CS-GPU-Package-Node-Boundary %})에서 정리한다.

이 랙 스케일 아키텍처는 대형 MoE 모델의 분리형 서빙(disaggregated serving)과 결합될 때 특히 강력하다고 평가되는데([7.1편]({% post_url 2026-08-29-Dev-LLM-Serving-Optimization-07-01-LLM-Serving-Advanced-Techniques-Overview %})에서 시작하는 책 7장의 주제다), 이런 소프트웨어-하드웨어 공동설계가 필요한 구성은 아직 업계 대부분이 도입 중인 단계고 일부 하이퍼스케일러만 최전선에서 채택하고 있다.

<br>

# 5장 정리

시리즈 다섯 편으로 나눠 본 책 5장은 크게 세 부분이었다.

1. **왜 LLM 서빙 최적화인가** ([5.1편]({% post_url 2026-08-22-Dev-LLM-Serving-Optimization-05-01-LLM-Serving-Challenge-Importance %})) — 효율적인 서빙은 고객 경험, 비용, 나아가 비즈니스의 확장 가능성까지 좌우한다
2. **AI 가속기 이해** ([5.2편]({% post_url 2026-08-22-Dev-LLM-Serving-Optimization-05-02-LLM-Serving-Challenge-GPU-Compute-Memory %})·[5.3편]({% post_url 2026-08-22-Dev-LLM-Serving-Optimization-05-03-LLM-Serving-Challenge-GPU-Interconnect-Selection %})) — 핵심 스펙 세 가지(메모리 용량, 연산 FLOPS, 메모리 대역폭)와, 단일 GPU로 부족할 때의 인터커넥트, 그리고 메모리 벽을 넘으려는 다른 가속기들
3. **하드웨어 위에서의 LLM 동작** ([5.4편]({% post_url 2026-08-22-Dev-LLM-Serving-Optimization-05-04-LLM-Serving-Challenge-Loading-Execution-Bottleneck %})) — 로딩(용량)과 실행(산술 강도)의 병목. LLM 서빙은 compute-bound 구간과 memory bandwidth-bound 구간을 모두 가지며, 특히 배치 1의 decode는 GPU 연산력을 포화시키지 못한다

이 장을 바탕으로 아래 세 가지 질문에 답해 보자.
1. TFLOPS가 높은 GPU가 곧 좋은 LLM 서빙 GPU인가: 아니다. 용량·대역폭·인터커넥트를 함께 봐야 한다 — [5.2편]({% post_url 2026-08-22-Dev-LLM-Serving-Optimization-05-02-LLM-Serving-Challenge-GPU-Compute-Memory %})·[5.3편]({% post_url 2026-08-22-Dev-LLM-Serving-Optimization-05-03-LLM-Serving-Challenge-GPU-Interconnect-Selection %})을 참고하자.
2. 우리 워크로드는 연산력을 다 쓰고 있는가, 대역폭이 병목인가: 산술 강도와 루프라인으로 판별한다. prefill은 조건부 compute-bound, decode는 항상 memory-bound이다. [5.4편]({% post_url 2026-08-22-Dev-LLM-Serving-Optimization-05-04-LLM-Serving-Challenge-Loading-Execution-Bottleneck %})을 참고하자.
3. 같은 하드웨어로 지연·처리량을 유지하며 비용·품질을 더 유리하게 바꿀 수 있는가. 그렇다. 그리고 그 자체가 서빙 최적화의 정의다. 교환비 조율을 넘어 곡선 자체를 밀어낸다 — [5.1편]({% post_url 2026-08-22-Dev-LLM-Serving-Optimization-05-01-LLM-Serving-Challenge-Importance %}), 구체 기법은 책 6장 이후에 다룬다.

이 분야는 전례 없는 속도로 새 기법이 쏟아진다. 하지만 이 장에서 쌓은 직관 — 스펙을 읽는 법, 모델이 하드웨어 위에서 동작하는 방식, 병목을 판별하는 틀 — 은 언어 모델이 새 아키텍처로 넘어가거나 비전 모델 작업으로 옮겨 가더라도 유효한 자산으로 남는다.

<br>

# 참고 링크

- [Hands-On LLM Serving and Optimization (O'Reilly)](https://www.oreilly.com/library/view/hands-on-llm-serving/9798341621480/)
- [NVIDIA GB200 NVL72](https://www.nvidia.com/en-us/data-center/gb200-nvl72/)
- [Fire-Flyer AI-HPC: A Cost-Effective Software-Hardware Co-Design for Deep Learning (arXiv 2408.14158)](https://arxiv.org/abs/2408.14158)
- [SemiAnalysis — InferenceX: NVIDIA Blackwell 분석](https://newsletter.semianalysis.com/p/inferencex-v2-nvidia-blackwell-vs)
- [Roofline 모델: 연산 강도로 판별하는 성능 병목]({% post_url 2026-08-21-CS-Roofline-Model %})
- [Roofline 모델로 보는 LLM 서빙: 세 점으로 나눠 찍는 병목]({% post_url 2026-08-21-Dev-Roofline-Model-LLM-Serving %})

<br>
