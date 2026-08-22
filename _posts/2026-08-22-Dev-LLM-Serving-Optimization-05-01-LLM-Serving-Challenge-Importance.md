---
title: "[LLM] LLM 서빙과 최적화: LLM 서빙의 도전 과제 - 5.1. 서빙 최적화의 중요성: 고객 경험·비용·확장성"
excerpt: "LLM 서빙 최적화가 고객 경험·비용·확장성을 어떻게 좌우하는지 알아 보자."
categories:
  - Dev
toc: true
header:
  teaser: /assets/images/blog-Dev.jpg
tags:
  - LLM-Serving
  - Inference
  - Latency
  - Throughput
  - Cost-Optimization
  - Hands-On-LLM-Serving-and-Optimization-Study
  - Hands-On-LLM-Serving-and-Optimization-Study-Week-3
last_modified_at: 2026-08-22
---

*[서종호(가시다)](https://www.linkedin.com/in/gasida99/)님의 Hands-On LLM Serving and Optimization Study (LLMSO) 3주차 학습 내용을 기반으로 합니다.*

<br>

# TL;DR

- 서빙 최적화는 지연 시간·처리량·모델 품질(크기)이 하드웨어 예산 하나를 나눠 쓰는 구조에서 교환비를 조율하는 작업이고, 나아가 그 교환비 자체를 유리하게 바꾸는 작업이다
- 지연 시간과 고객 만족도의 관계는 비선형이다. 만족 임계선을 넘긴 뒤의 지연 시간 여유는 처리량(비용)이나 모델 크기(품질)로 환산하는 편이 낫다
- AI 비용의 중심은 훈련이 아니라 추론이다. 훈련은 대체로 일회성 선투자지만, 추론 비용은 쿼리마다 발생하고 사용량과 함께 누적된다
- 피크 트래픽 대응력과 하드웨어 유연성(리전별 GPU 가용성 제약)까지 서빙 최적화가 좌우한다. 성능 문제를 넘어 사업 실현 가능성의 문제다

<br>

# 5장의 구성

[1편]({% post_url 2026-08-14-Dev-LLM-Serving-Optimization-01-LLM-Serving-Overview %})부터 [3.3편]({% post_url 2026-08-14-Dev-LLM-Serving-Optimization-03-03-LLM-Serving-Prefill-Decode %})까지는 책 앞부분을 따라 일반적인 모델 서빙 개념과 단일 모델 서빙 시스템 실습을 다뤘다. 책 5장부터는 주제가 바뀐다. LLM 서빙 최적화라는, 지금 가장 빠르게 움직이는 분야다.

ChatGPT 등장 이후 LLM이 실무에 널리 쓰이게 됐지만, 모델 크기·연산량·서빙 방식이 기존 모델과 달라 새로운 문제가 쏟아졌다. 기술 블로그의 vLLM, 논문의 FlashAttention, 뉴스의 MLA 같은 이름들이 그 산물이다. 책은 이런 개별 기법으로 들어가기 전에 5장에서 기초를 다진다. 원리를 모르면 최적화가 시행착오의 반복이 되고, 왜 그런지 모른 채 지역 최적해에 갇히기 쉽다는 것이 책의 진단이다.

5장이 답하는 질문은 세 가지다.

1. **왜 중요한가** — LLM을 효율적으로 서빙하는 것이 애플리케이션과 비즈니스 성패에 왜 처음부터 중요한가 (이 글)
2. **무엇 위에서 도는가** — GPU 같은 AI 가속기의 연산·메모리·인터커넥트 특성을 어떻게 읽는가 ([5.2편]({% post_url 2026-08-22-Dev-LLM-Serving-Optimization-05-02-LLM-Serving-Challenge-GPU-Compute-Memory %}), [5.3편]({% post_url 2026-08-22-Dev-LLM-Serving-Optimization-05-03-LLM-Serving-Challenge-GPU-Interconnect-Selection %}))
3. **어디서 막히는가** — 모델 로딩과 실행(prefill·decode) 단계별 병목이 어디서 생기는가 ([5.4편]({% post_url 2026-08-22-Dev-LLM-Serving-Optimization-05-04-LLM-Serving-Challenge-Loading-Execution-Bottleneck %}), [5.5편]({% post_url 2026-08-22-Dev-LLM-Serving-Optimization-05-05-LLM-Serving-Challenge-Accelerator-Trends %}))

미리 결론 하나를 당겨 두면, LLM 서빙이 느린 원인은 GPU 계산 성능(TFLOPS) 부족만이 아니다. 모델을 올릴 때는 메모리 용량이, decode 단계에서는 메모리 대역폭이, 여러 장을 묶을 때는 인터커넥트가 각각 병목이 된다. 그래서 GPU를 고를 때도 TFLOPS 하나가 아니라 여러 축을 함께 봐야 한다.

![LLM 서빙 GPU 선택 시 함께 봐야 하는 축들을 정리한 도식]({{site.url}}/assets/images/llmso-llm-serving-gpu-decisions.png){: .align-center width="720"}

<center><sup>직접 정리한 도식. 연산 성능 외에 VRAM 용량, 메모리 대역폭, 인터커넥트, 그리고 모델 크기·정밀도·KV 캐시·prefill/decode 비율까지 GPU 선택에 관여한다</sup></center>

각 축이 왜 병목이 되는지는 [5.2편]({% post_url 2026-08-22-Dev-LLM-Serving-Optimization-05-02-LLM-Serving-Challenge-GPU-Compute-Memory %})부터 하나씩 확인한다. 이 글은 그 전에, 이 최적화가 왜 필요한지를 세 측면 — 고객 경험, 비용 효율, 확장성·실현 가능성 — 으로 정리한다.

<br>

# 고객 경험: 지연·처리량·품질

결론부터 말하면, 고객 경험을 결정하는 지연 시간·처리량·모델 품질(크기) 세 축은 하드웨어 예산이라는 하나의 제약을 나눠 쓴다. 셋 중 둘을 고르면 나머지는 대체로 결정된다. 서빙 최적화는 이 교환비를 상황에 맞게 조율하는 일에서 시작한다.

## 지연 시간과 만족도의 비선형 관계

지연 시간(latency)과 고객 만족도는 반비례하지만, 그 영향은 비선형이다. ChatGPT에 질문하고 첫 토큰까지 20초를 기다려야 한다면 쓸 수 없는 제품이다. 같은 하드웨어와 처리량을 유지하면서 지연 시간을 20초에서 1초로 줄이면 제품 성패가 갈린다. 반면 첫 토큰 시간(TTFT)을 0.1초에서 0.01초로 줄이는 것은 사람이 인지하지 못한다.

![지연 시간과 고객 만족도의 반비례 곡선. 지연이 줄어들수록 만족도 개선 폭이 감소한다]({{site.url}}/assets/images/llmso-latency-customer-satisfaction.png){: .align-center width="640"}

<center><sup>출처: Hands-On LLM Serving and Optimization (O'Reilly), Figure 5-1</sup></center>

경제학의 한계효용 체감과 같은 모양이다. 20초 → 1초 구간에서는 만족도가 폭증하지만, 0.1초 → 0.01초 구간에서는 투자 대비 효과가 0에 가깝다. 그래서 지연 시간은 "낮을수록 좋은 최적화 목표"라기보다, **만족 임계선을 넘기면 그 이상은 가치가 거의 없는 제약 조건**에 가깝다. 임계선을 넘긴 뒤에 남는 여유는 다른 축으로 환산하는 편이 합리적이다.

## 환산의 두 방향: 처리량과 모델 품질

임계선 이후의 지연 시간 여유를 바꿀 수 있는 대상은 두 가지다.

| 환산 방향 | 얻는 것 | 책의 근거 |
| --- | --- | --- |
| 지연 시간 → 처리량(throughput) | 비용 효율. 동일 GPU로 더 많은 동시 사용자 처리 | TTFT 0.01초를 0.1초로 양보하면 비용 효율을 크게 개선할 수 있다 |
| 지연 시간 → 모델 크기 | 응답 품질. 같은 계열에서 더 큰 모델 사용 | Figure 5-2, Llama-3-8B vs 70B 벤치마크 비교 |

모델 품질 쪽을 보면, 같은 계열(예: Llama-3)에서는 파라미터 수가 클수록 벤치마크 성능이 좋다.

![Llama-3-70B와 Llama-3-8B의 벤치마크 점수 비교 막대 차트. 전 항목에서 70B가 우세하다]({{site.url}}/assets/images/llmso-llama-3-70B-vs-llama-3-8B.png){: .align-center width="720"}

<center><sup>출처: Hands-On LLM Serving and Optimization (O'Reilly), Figure 5-2. Open LLM Leaderboard 모델 비교 도구 기반</sup></center>

다만 큰 모델은 그만큼 느리고 비싸다. [3.3편]({% post_url 2026-08-14-Dev-LLM-Serving-Optimization-03-03-LLM-Serving-Prefill-Decode %})에서 본 대로 decode 단계는 토큰 하나를 만들 때마다 모델 가중치 전체를 GPU 메모리에서 읽는다. 8B(FP16 기준 약 16GB)에서 70B(약 140GB)로 가면 토큰마다 읽어야 할 바이트가 약 9배가 되고, 토큰당 생성 시간(TPOT)도 대략 그만큼 늘어난다. 게다가 70B는 단일 GPU에 들어가지 않아 여러 장으로 나눠야 하고, 그 순간 GPU 간 통신 오버헤드가 붙는다. 왜 그런지는 [5.4편]({% post_url 2026-08-22-Dev-LLM-Serving-Optimization-05-04-LLM-Serving-Challenge-Loading-Execution-Bottleneck %})에서 산술 강도로 계산해 확인한다.

## 최적화의 위치: 교환비 조율과 곡선 이동

이 구조를 실무 순서로 쓰면 다음과 같다.

1. 제품이 요구하는 지연 시간 SLO(TTFT·TPOT)를 먼저 고정한다 — 최소화 대상이 아니라 만족시킬 제약 조건이다
2. 그 제약 안에서 품질(모델 크기)을 최대화하거나 비용(처리량 대비 하드웨어)을 최소화한다 — 교환비 위에서의 선택이다
3. 둘 다 부족하면, 교환비 자체를 바꾸는 최적화를 찾는다

3번이 이 시리즈의 주제다. 교환비 위에서 움직이는 것이 곡선 위의 이동(하나를 내주고 하나를 얻는 제로섬)이라면, 서빙 최적화는 곡선 자체를 바깥으로 밀어내는 일이다. 책은 서빙 시스템을 전면적으로 최적화한 뒤 같은 하드웨어·지연 시간·처리량 조건에서 8B 대신 32B나 70B 모델을 운영할 수 있었다는 경험을 소개한다. 이후 장에서 다룰 양자화(FP8), continuous batching, PagedAttention, GQA/MLA, prefix caching 같은 기법이 전부 이 "포기하지 않고 더 큰 모델을 쓰게 만드는" 수단에 해당한다. 서빙 최적화가 성능 튜닝을 넘어 제품 품질 레버가 되는 이유다.

<br>

# 비용 효율: 추론 비용의 지배

두 번째 측면은 비용이다. 요지는 하나다. AI 비용 구조에서 가장 큰 비중을 차지하는 것은 훈련이 아니라 추론(inference)이다.

## 훈련 비용과 추론 비용

직관과 어긋날 수 있다. GPT-4 훈련 비용이 5천만 달러를 넘는다는 보도처럼, 눈에 띄는 것은 훈련 비용이기 때문이다. 하지만 책이 인용하는 Signal Integrity Journal의 2024~2034년 AI 칩 매출 전망에 따르면, 추론용 하드웨어 소비는 이미 훈련용을 넘어섰고 격차는 계속 벌어질 것으로 예상된다.

![2024년부터 2034년까지 AI 칩 매출 성장과 훈련/추론 구성 변화 전망 차트]({{site.url}}/assets/images/llmso-ai-chi-revenue-training-inference-composition.png){: .align-center width="720"}

<center><sup>출처: Hands-On LLM Serving and Optimization (O'Reilly), Figure 5-3. "The Age of Artificial Intelligence: AI Chips to 2034" 일부 수정</sup></center>

구조적인 이유가 있다.

- **훈련**은 대부분 일회성 선투자다. 재훈련·파인튜닝 비용이 간간이 발생하지만 상한이 있다
- **추론**은 모델이 배포된 뒤 모든 쿼리·상호작용마다 비용이 발생하고, 채택이 늘수록 누적된다
- 대다수 기업은 파운데이션 모델을 처음부터 훈련하지 않는다. 기존 모델을 파인튜닝하거나 RAG로 보강하는 쪽을 택해 훈련 비용을 크게 줄인다. 반면 추론 수요는 모두에게 발생한다
- AI 에이전트와 복잡한 워크플로우는 하나의 작업 안에서 LLM·임베딩 모델 호출을 여러 번 수행해 추론 비용을 더 가중시킨다

## 서빙 최적화의 비용 효과

그래서 추론 비용을 낮추는 서빙 최적화가 재무적 생존의 문제가 된다. 효과는 두 방향이다.

- 동일한 하드웨어와 비슷한 지연 시간을 유지하면서 처리량을 높이면, 같은 GPU로 더 많은 고객을 동시에 서빙한다 → 수평 확장 시 필요한 하드웨어 수가 줄어든다
- 최적화된 모델은 더 저렴한(성능 등급이 낮은) 칩에서도 비슷한 지연 시간·처리량을 낼 수 있다 → 칩 단가 자체를 낮춘다

<br>

# 확장성과 실현 가능성

세 번째 측면은 시스템이 커질 수 있는가, 그리고 애초에 돌아갈 수 있는가다.

## 피크 트래픽 대응

프로덕션에 배포된 모델의 GPU 수요는 고객 성장에 따라 늘어난다. 문제는 평균이 아니라 피크다. 책은 LLM 기반 영업 에이전트가 연중 안정적으로 돌다가 블랙 프라이데이에 수요가 400% 이상 급증하는 예를 든다. 최적화가 부족한 시스템은 이런 급증을 감당하지 못해 병목, 지연 시간 악화, 요청 실패로 이어진다. 저자들은 이 문제를 직접 겪었고, 해당 시간대 서비스 가용성을 확보하기 위해 많은 튜닝과 성능 테스트가 필요했다고 적는다.

피크 부하를 다루려면 모델 복제본 수, GPU 메모리, 큐잉, 오토스케일링, 콜드 스타트 시간을 함께 고려해야 한다. 모델이 커서 단일 GPU에 올라가지 않으면 텐서 병렬화나 멀티 노드 서빙이 필요해지고, 이때는 인터커넥트가 성능을 좌우한다 — [5.3편]({% post_url 2026-08-22-Dev-LLM-Serving-Optimization-05-03-LLM-Serving-Challenge-GPU-Interconnect-Selection %})의 주제다. GPU 공급이 제한된 시기라면 "GPU를 더 붙인다"는 선택지 자체가 막힐 수 있어, 최적화된 추론 솔루션의 유무가 확장 가능 여부를 가른다.

## 하드웨어 유연성

최적화된 모델은 저사양 칩에서도 구동할 수 있어 배포 유연성이 커진다. AWS·GCP·Azure 같은 주요 클라우드를 쓰더라도 모든 리전에서 고사양 GPU를 항상 구할 수 있는 것은 아니다. 특정 고급 GPU에 종속되지 않고 더 넓은 범위의 하드웨어에서 모델을 효율적으로 돌릴 수 있는 능력은, 새로운 시장·리전으로 확장할 때 핵심 요인이 된다. 저자들도 전 세계에 애플리케이션을 배포하면서 이 문제를 자주 겪었다고 언급한다.

<br>

# 정리

| 측면 | 요지 | 서빙 최적화의 역할 |
| --- | --- | --- |
| 고객 경험 | 지연·처리량·품질이 하드웨어 예산을 나눠 씀. 지연의 한계효용은 체감 | SLO를 제약으로 고정하고 교환비를 조율, 나아가 곡선 자체를 밀어냄 |
| 비용 효율 | AI 비용의 중심은 누적되는 추론 비용 | 같은 하드웨어로 더 높은 처리량, 또는 더 싼 칩으로 동등 성능 |
| 확장성·실현 가능성 | 문제는 평균이 아니라 피크. 리전별 GPU 가용성도 제약 | 피크 대응력과 하드웨어 선택 폭을 넓힘 |

다음 글부터는 이 최적화가 다루는 대상인 하드웨어로 들어간다. [5.2편]({% post_url 2026-08-22-Dev-LLM-Serving-Optimization-05-02-LLM-Serving-Challenge-GPU-Compute-Memory %})에서 GPU 스펙의 연산·메모리 속성을 읽는 법부터 본다.

<br>

# 참고 링크

- [Hands-On LLM Serving and Optimization (O'Reilly)](https://www.oreilly.com/library/view/hands-on-llm-serving/9798341621480/)
- [Open LLM Leaderboard](https://huggingface.co/spaces/open-llm-leaderboard/open_llm_leaderboard)
- [LLM 서빙과 최적화 - 1. 개요: 트랜스포머에서 서빙 시스템으로]({% post_url 2026-08-14-Dev-LLM-Serving-Optimization-01-LLM-Serving-Overview %})
- [단일 모델 서빙 시스템 - 3.3. prefill과 decode: 생성 추론의 두 단계]({% post_url 2026-08-14-Dev-LLM-Serving-Optimization-03-03-LLM-Serving-Prefill-Decode %})

<br>
