---
title: "[LLM] LLM 서빙과 최적화: 고급 최적화 기법 - 7.1. 개요: 단일 GPU 너머의 네 기법"
excerpt: "LLM 서빙 고급 최적화 기법(speculative decoding, 멀티 GPU 분산, PD 분리, 고급 KV 캐싱)에 대해 알아 보자."
categories:
  - Dev
toc: true
header:
  teaser: /assets/images/blog-Dev.jpg
tags:
  - LLM-Serving
  - Speculative-Decoding
  - Parallelism
  - PD-Disaggregation
  - KV-Cache
  - Hands-On-LLM-Serving-and-Optimization-Study
  - Hands-On-LLM-Serving-and-Optimization-Study-Week-4
last_modified_at: 2026-08-29
---

*[서종호(가시다)](https://www.linkedin.com/in/gasida99/)님의 Hands-On LLM Serving and Optimization Study (LLMSO) 4주차 학습 내용을 기반으로 합니다.*

<br>

# TL;DR

- 6장까지의 논의는 **모델이 GPU 한 장에 올라가는 상황**을 상정했다. 기법 자체는 분산 서빙에서도 그대로 쓰이지만, 100B급 모델은 용량(bf16 기준 파라미터만 200GB)과 지연 모든 측면에서 6장까지 논의한 기법들만으로는 해결되지 않는 문제를 새로 만든다
- 이에 대한 7장의 답은 넷이다: **speculative decoding**(ITL 개선), **멀티 GPU·멀티 노드 분산**(용량·처리량 확장), **PD disaggregation**(TTFT·ITL 독립 튜닝), **고급 KV 캐싱**(TTFT 단축·적중률 향상)
- 네 기법의 적용 조건은 전부 compute-bound / memory-bound 축 위의 위치로 결정된다. speculative decoding은 decode의 노는 연산 유닛에 검증을 맡기는 구조라 이득이 memory-bound·저배치에서 가장 크고, 배치가 차면 줄어들거나 손해로 바뀐다
- 속도를 얻는 지점마다 새 비용이 생긴다: 거부된 draft 토큰, all-reduce 통신, KV cache 전송, 캐시 콜드 스타트. 기법마다 이런 핸드오프 비용이 따르므로 스택 전체를 함께 튜닝해야 한다

<br>

# 전제: 단일 GPU 서빙의 한계

[6.1편]({% post_url 2026-08-22-Dev-LLM-Serving-Optimization-06-01-LLM-Serving-Optimization-Techniques-Overview %}#6장의-지도-하나의-분수-세-방향의-공략)에서 6장의 기법들을 산술 강도라는 분수 하나에 대한 세 방향의 공략 — 분자를 키우는 배칭·스케줄링, 분모를 줄이는 어텐션 최적화·모델 압축, 계산 자체를 피하는 프리픽스 캐싱 — 으로 정리했다. 이 논의 전체가 상정한 범위가 하나 있다. **모델이 GPU 한 장에 올라간다**는 것이다 — [6.1편의 실행 모델]({% post_url 2026-08-22-Dev-LLM-Serving-Optimization-06-01-LLM-Serving-Optimization-Techniques-Overview %}#실행-단위-iteration)부터가 한 엔진이 도는 단일 루프였다. 분명히 해 둘 것은, 이 상정이 기법의 적용 한계는 아니라는 점이다. 배칭도 어텐션 최적화도 캐싱도 여러 GPU에 분산된 모델 위에서 그대로 동작한다. 모델이 한 장을 넘을 때 생기는 일은 6장 기법이 무효가 되는 것이 아니라, **그 기법들이 다루지 않는 문제가 추가되는 것**이다.

추가되는 문제는 두 갈래다.

- **용량**: [5.4편의 모델 크기 추정]({% post_url 2026-08-22-Dev-LLM-Serving-Optimization-05-04-LLM-Serving-Challenge-Loading-Execution-Bottleneck %}#모델-크기-추정)대로 bf16은 파라미터당 2바이트라, 100B 모델이면 가중치만 200GB다. H100 80GB는 물론 B200(180~192GB)으로도 한 장에 안 들어가고, [KV cache]({% post_url 2026-08-22-Dev-LLM-Serving-Optimization-05-04-LLM-Serving-Challenge-Loading-Execution-Bottleneck %}#kv-캐시-크기-추정)와 activation 몫까지 얹으면 경계는 더 이르게 온다
- **지연**: 모델이 한 장에 올라가는 크기여도 문제가 끝나지 않는다. decode 한 스텝은 가중치 전체를 HBM에서 읽으므로, 모델이 클수록 스텝당 읽을 바이트가 늘어 ITL(Inter-Token Latency, 토큰 간 지연 — [3.3편의 서빙 지표]({% post_url 2026-08-14-Dev-LLM-Serving-Optimization-03-03-LLM-Serving-Prefill-Decode %}#서빙-지표-ttft와-tpot) 참고)이 커진다. 단일 카드의 메모리 대역폭으로는 SLO(Service Level Objective)를 못 맞추는 지점이 온다

사실 5장이 이미 이 방향을 예고했다. [5.3편]({% post_url 2026-08-22-Dev-LLM-Serving-Optimization-05-03-LLM-Serving-Challenge-GPU-Interconnect-Selection %})은 모델이 한 장을 넘을 때를 대비해 인터커넥트 대역폭 계층을 정리했고, [5.5편]({% post_url 2026-08-22-Dev-LLM-Serving-Optimization-05-05-LLM-Serving-Challenge-Accelerator-Trends %})은 NVL72 같은 랙 스케일 아키텍처가 "대형 MoE 모델의 분리형 서빙(disaggregated serving)과 결합될 때 특히 강력하다"고 언급하며 7장을 가리켰다. 5장이 이 방향의 하드웨어 기반(인터커넥트 계층, 랙 스케일 아키텍처)을 정리했다면, 7장은 같은 문제를 소프트웨어 기법으로 다룬다.

<br>

# 7장의 지도: 네 가지 기법

책이 7장에서 다루는 기법은 네 가지다. 표의 TTFT(Time To First Token, 첫 토큰까지의 시간)를 비롯한 지연 지표의 정의는 [3.3편의 서빙 지표]({% post_url 2026-08-14-Dev-LLM-Serving-Optimization-03-03-LLM-Serving-Prefill-Decode %}#서빙-지표-ttft와-tpot)를 따른다.

| # | 기법 | 해결하려는 문제 | 주로 개선하는 지표 |
|---|------|----------------|--------------|
| 1 | **Speculative Decoding** | decode가 스텝당 토큰 1개씩만 생성 | ITL |
| 2 | **멀티 GPU·멀티 노드 분산** (DP·TP·PP·EP) | 모델이 한 장에 안 들어가거나 처리량 부족 | 메모리 용량, 처리량 |
| 3 | **PD Disaggregation** | prefill과 decode가 서로 다른 자원 특성 요구 | TTFT·ITL 독립 튜닝 |
| 4 | **고급 KV 캐싱** | 긴 컨텍스트의 prefill 반복과 GPU 메모리 부족 | TTFT, 캐시 적중률 |

<br>

넷은 독립된 기능이 아니라 하나의 서빙 스택으로 조립된다. 책의 소개 순서(번호)와 각 기법이 배치되는 스택 계층(위아래)이 다르다는 점을 그림으로 먼저 확인해 두자.

[![7장 네 기법의 서빙 스택 내 위치]({{site.url}}/assets/images/llmso-ch07-advanced-techniques-stack.svg){: .align-center width="820"}]({{site.url}}/assets/images/llmso-ch07-advanced-techniques-stack.svg){: target="_blank" }

<center><sup>AI를 이용해 직접 그린 도식. 요청 라우팅부터 하드웨어까지의 서빙 스택 위에 7장 네 기법이 각자 다른 층으로 들어간다</sup></center>

- **speculative decoding**(추측 디코딩, 1)은 엔진 안의 디코딩 로직을 바꾼다. 한 스텝에 토큰 하나라는 decode의 규칙을 깨고, 후보 여러 개를 한 번의 forward로 검증한다
- **분산 실행**(2)은 엔진 아래에서 모델을 쪼갠다. 복제(DP), 레이어 내 분할(TP), 레이어 간 분할(PP), expert 분할(EP)로 여러 GPU·노드에 나눠 싣는다
- **PD disaggregation**(3)은 엔진 위에서 인스턴스를 쪼갠다. prefill 전용 풀과 decode 전용 풀을 물리적으로 분리하고 그 사이에서 KV cache를 넘긴다
- **고급 KV 캐싱**(4)은 KV cache를 GPU HBM에 가두지 않고 CPU RAM → SSD → 원격 스토리지로 이어지는 계층 저장소로 확장하며, 맨 위 라우팅 층은 이 캐시가 어디에 있는지를 신호로 삼는다(cache-aware routing)

<br>

스택이 정적인 배치도라면, 같은 네 기법을 요청 하나의 경로 위에 놓으면 각 기법의 개입 지점이 지표와 연결된다. [3.3편]({% post_url 2026-08-14-Dev-LLM-Serving-Optimization-03-03-LLM-Serving-Prefill-Decode %})의 시간축 — prefill → 첫 토큰 → decode 반복 — 위에서 보면 다음과 같다.

[![요청 경로 위의 개입 지점]({{site.url}}/assets/images/llmso-ch07-request-path-interventions.svg){: .align-center width="860"}]({{site.url}}/assets/images/llmso-ch07-request-path-interventions.svg){: target="_blank" }

<center><sup>스터디 노트의 도식을 바탕으로 AI를 이용해 재구성했다. prefill 구간의 개입(③·④)은 TTFT를, decode 구간의 개입(①)은 토큰당 지연을 움직인다. ②(분산 실행)는 특정 구간이 아니라 경로 전체의 전제라 시간축 위에 점으로 찍히지 않는다</sup></center>

<br>

# 네 기법을 관통하는 두 기준

기법을 하나씩 살펴 보기 전에, 넷을 관통하는 판단 기준 두 개를 먼저 정리한다. **언제 이득인가**와 **무엇을 대가로 치르는가**다. 이 장이 답하려는 질문을 먼저 살펴 보자.

- compute-bound / memory-bound 축이 왜 이 장 전체를 관통하는 단일 기준이 되는가
- 네 기법이 공통적으로 핸드오프 비용을 대가로 치른다는 패턴은 무엇을 의미하는가
- 모든 최적화가 특정 조건에서만 이득이라면, 그 조건을 실시간으로 감지해 자동 전환하는 메커니즘은 왜 다뤄지지 않는가

앞의 두 질문은 아래 두 절이 하나씩 맡는다 — 다만 각 절을 따로 읽어서는 답이 안 나오고 겹쳐 읽어야 답이 나온다. 마지막 질문은 [정리](#정리)에서 답한다.

## 병목 축: compute-bound와 memory-bound

첫 번째 기준은 [5.4편]({% post_url 2026-08-22-Dev-LLM-Serving-Optimization-05-04-LLM-Serving-Challenge-Loading-Execution-Bottleneck %}#병목-판정과-최적화-방향)과 [roofline 실측 글]({% post_url 2026-08-21-Dev-Roofline-Model-LLM-Serving %})에서 쌓은 병목 판정 축이다. 이하의 memory-bound는 [6.1편]({% post_url 2026-08-22-Dev-LLM-Serving-Optimization-06-01-LLM-Serving-Optimization-Techniques-Overview %})과 마찬가지로 메모리 용량이 아니라 대역폭의 병목을 가리킨다 — 용량 문제는 앞 절에서 따로 다뤘다. 결론부터 말하면, **네 기법의 적용 조건은 전부 워크로드가 이 축의 어디에 있느냐로 결정된다.**

| 기법 | 축 위의 위치와 적용 조건 |
|------|--------------------------|
| speculative decoding | decode의 memory-bound(저배치) 구간에서 이득 — 배치가 차서 compute-bound로 넘어가면 손해 |
| PD disaggregation | prefill(compute-bound)과 decode(memory-bound)가 축의 양 끝 — 분리해서 독립 튜닝 |
| 분산 실행과 MoE | 배치 크기가 축 위의 위치를 옮긴다 — MoE는 expert를 채울 큰 배치가 조건 |
| 고급 KV 캐싱 | prefill이 compute-bound로 비싼 워크로드(긴 컨텍스트, 반복 프롬프트)일수록 이득 |

각 판정의 근거는 다음과 같다.

- **speculative decoding**: decode는 memory-bound라 가중치를 읽는 동안 연산 유닛이 논다. 이 기법은 그 노는 연산에 후보 토큰 검증을 맡기는 구조다 — [6.1편의 배칭]({% post_url 2026-08-22-Dev-LLM-Serving-Optimization-06-01-LLM-Serving-Optimization-Techniques-Overview %}#처리량-이득의-원리)과 같은 상각 구조를 다른 축에서 쓰는 셈이다. 뒤집으면, 배치가 차서 GPU가 이미 compute-bound로 넘어간 상황에서는 맡길 노는 연산이 없고, 검증에 쓴 잉여 연산이 그대로 처리량 손실이 된다 — 배칭과 같은 자원(노는 연산)을 두고 경쟁하기 때문이다. 이 경쟁 구조는 [7.2.1편]({% post_url 2026-08-29-Dev-LLM-Serving-Optimization-07-02-01-Speculative-Decoding-Concept %}#이득의-원리-가중치-읽기-1회당-생성-토큰-수)에서 전개하고, 부호 반전은 [7.2.2편]({% post_url 2026-08-29-Dev-LLM-Serving-Optimization-07-02-02-Speculative-Decoding-Hands-On %})에서 실측으로 확인한다
- **PD disaggregation**: [3.3편]({% post_url 2026-08-14-Dev-LLM-Serving-Optimization-03-03-LLM-Serving-Prefill-Decode %}#같은-flops-다른-병목)에서 정리했듯 prefill은 compute-bound, decode는 memory-bound로 축의 반대편에 있다. 성격이 다른 두 단계가 같은 GPU에서 섞이면 서로 간섭한다 — [6.1편 말미]({% post_url 2026-08-22-Dev-LLM-Serving-Optimization-06-01-LLM-Serving-Optimization-Techniques-Overview %}#남는-질문-6장의-나머지)에서 본, 긴 prefill이 스텝 길이를 지배해 진행 중인 decode의 ITL을 흔드는 문제가 그것이다. 6장의 chunked prefill이 한 GPU 안에서 시간을 쪼개는 완화였다면, PD 분리는 아예 공간을 쪼개서 각 풀을 자기 병목에 맞는 하드웨어와 배치 설정으로 독립 튜닝하는 접근이다
- **분산 실행과 MoE**: 배치 크기는 축 위의 위치를 움직이는 조절 변수다. MoE(Mixture-of-Experts)의 희소성이 효율로 이어지려면 expert들이 고르게 채워질 만큼 큰 배치가 필요하다는 것도, 결국 배치가 병목 경계를 어느 쪽으로 옮기느냐의 문제다
- **고급 KV 캐싱**: prefill의 계산을 다시 하지 않으려는 기법이니, prefill이 compute-bound로 비싼 워크로드(긴 컨텍스트, 반복 프롬프트)일수록 이득이 크다

## 공통 비용: 핸드오프

두 번째 기준은 비용이다. 네 기법 모두 속도를 얻는 지점에서 **무언가를 옮기거나 버리는 비용**을 새로 만든다.

| 기법 | 새로 생기는 비용 |
|------|------------------|
| speculative decoding | 거부된 draft 토큰에 쓴 연산 (폐기) |
| TP 등 분산 실행 | 레이어마다 all-reduce 같은 집합 통신 (비용의 크기는 [5.3편]({% post_url 2026-08-22-Dev-LLM-Serving-Optimization-05-03-LLM-Serving-Challenge-GPU-Interconnect-Selection %}#병렬화-배치와-인터커넥트-계층)의 인터커넥트 계층이 결정한다) |
| PD disaggregation | prefill 풀 → decode 풀로의 KV cache 전송 대역폭 |
| 고급 KV 캐싱 | 계층 간 캐시 이동, 콜드 스타트 구간의 오히려 느려지는 지점 |

우연이 아니다. 6장까지가 한 장의 GPU 안에서 일을 재배치하는 이야기였다면, 7장은 일을 **여러 실행 주체에 나누는** 이야기라 나눈 경계마다 반드시 이동·폐기 비용이 생긴다. 그래서 이 장의 결론이 "기법을 켜라"가 아니라 **"계층을 함께 튜닝하라"**가 된다 — 어떤 기법의 이득도 그 기법이 만든 핸드오프 비용이 워크로드에서 실제로 얼마인지와 함께 계산해야 순이득이 보인다.

<br>

# 정리

- 6장까지의 논의는 모델이 GPU 한 장에 올라가는 상황을 상정했고, 100B급 모델은 용량과 지연 양쪽에서 그 기법들만으로 해결되지 않는 문제를 추가한다
- 7장의 네 기법은 스택의 서로 다른 층으로 들어간다: 라우팅(고급 KV 캐싱과 연동) → PD 분리 → 엔진 내 디코딩(speculative decoding) → 분산 실행 → KV cache 계층
- 적용 조건은 compute-bound / memory-bound 축 위의 위치가 정하고, 대가는 기법마다 새로 생기는 핸드오프 비용이 정한다

한 가지 알아 둘 점이 있다. 네 기법 모두 "특정 조건에서만" 이득인데, 책의 실습은 전부 사람이 값을 고정해 두는 정적 튜닝이다 — speculative decoding의 K값이 대표적이다. 조건을 실시간으로 감지해 전환하는 동적 자동화는 Dynamo·llm-d의 라우팅 신호나 vLLM 문서의 dynamic speculative decoding 같은 형태로 언급만 되고, 엔진 내부 동작을 파는 이후 장에서 본격적으로 다루게 된다. 정적 튜닝으로 개념을 익히되, 실무의 끝 그림은 동적이라는 것을 염두에 두고 읽으면 좋다.

이번 주는 첫 번째 기법인 speculative decoding을 두 편으로 다룬다. [7.2.1편]({% post_url 2026-08-29-Dev-LLM-Serving-Optimization-07-02-01-Speculative-Decoding-Concept %})에서 동작 원리와 draft 선택지를, [7.2.2편]({% post_url 2026-08-29-Dev-LLM-Serving-Optimization-07-02-02-Speculative-Decoding-Hands-On %})에서 vLLM 네 가지 변형의 실측을 정리한다. 나머지 세 기법은 이후 글에서 이어간다.

<br>

# 참고 링크

- [Hands-On LLM Serving and Optimization (O'Reilly)](https://www.oreilly.com/library/view/hands-on-llm-serving/9798341621480/)
- [NVIDIA Dynamo (GitHub)](https://github.com/ai-dynamo/dynamo)
- [llm-d (GitHub)](https://github.com/llm-d/llm-d)
- [6.1편: 서빙 최적화 기법 개요]({% post_url 2026-08-22-Dev-LLM-Serving-Optimization-06-01-LLM-Serving-Optimization-Techniques-Overview %})
- [5.5편: AI 가속기 지형과 메모리 벽]({% post_url 2026-08-22-Dev-LLM-Serving-Optimization-05-05-LLM-Serving-Challenge-Accelerator-Trends %})

<br>
