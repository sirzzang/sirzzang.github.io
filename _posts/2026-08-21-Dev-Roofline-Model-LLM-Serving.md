---
title: "[Performance] Roofline 모델로 보는 LLM 서빙: 세 점으로 나눠 찍는 병목"
excerpt: "Roofline 모델을 LLM 서빙 워크로드에 적용해 보자."
categories:
  - Dev
toc: true
header:
  teaser: /assets/images/blog-Dev.jpg
tags:
  - Roofline-Model
  - LLM-Serving
  - GPU
  - Performance
  - KV-Cache
  - Continuous-Batching
  - Hands-On-LLM-Serving-and-Optimization-Study
  - Hands-On-LLM-Serving-and-Optimization-Study-Week-3
last_modified_at: 2026-08-22
---

*[서종호(가시다)](https://www.linkedin.com/in/gasida99/)님의 Hands-On LLM Serving and Optimization Study (LLMSO) 3주차 학습 내용을 기반으로 합니다.*

<br>

# TL;DR

- LLM 서빙 워크로드는 루프라인에 최소 세 점으로 나눠 찍어야 한다. prefill은 연산 바운드, decode-FFN은 $I \approx B$라 배칭으로 사선을 벗어날 수 있지만, decode-attention은 KV 캐시가 요청마다 달라 배칭으로도 움직이지 않는다
- decode-FFN의 연산 강도는 배치 크기와 같다($I \approx B$). H100의 ridge point가 $\approx 295$ FLOP/byte이므로 배치가 수백 규모가 되어야 연산 바운드로 넘어가고, batch=1이면 7B FP16 기준 이론 상한이 $\approx 240$ tok/s로 대역폭이 직접 결정한다
- prefill과 decode는 다른 지표로 평가해야 한다. prefill의 성적표는 MFU·텐서코어 활용률, decode의 성적표는 달성 대역폭이다
- 최적화 기법은 "점을 어느 방향으로 옮기는가 / 지붕을 어떻게 바꾸는가"로 정리된다. INT4 같은 $Q$ 절감은 저배치(메모리 바운드)에서만 듣고, 고배치에서는 오히려 느려질 수 있다

<br>

# 배경

[Roofline 모델 편]({% post_url 2026-08-21-CS-Roofline-Model %})에서 모델 자체를 정리했다 — 성능 상한 $P = \min(\pi, \beta I)$, 연산 강도 $I = W/Q$, 그리고 점이 [ridge point]({% post_url 2026-08-21-CS-Roofline-Model %}#ridge-point) 왼쪽이면 메모리 바운드, 오른쪽이면 연산 바운드라는 판정 규칙까지. 이 글은 그 틀을 LLM 서빙 워크로드에 실제로 적용한다. prefill/decode의 실행 구조 자체는 [LLM 서빙과 최적화 3.3편]({% post_url 2026-08-14-Dev-LLM-Serving-Optimization-03-03-LLM-Serving-Prefill-Decode %})에서 다뤘다.

<br>

# LLM 서빙의 세 점

루프라인이 LLM 서빙에서 유독 많이 언급되는 데는 이유가 있다.
- 첫째, **decode가 있을 수 있는 가장 심한 정도로 메모리 바운드**($I \approx 1$, ridge에서 한참 왼쪽)라 성능이 왜 낮은지 util·FLOP/s만 봐서는 진단되지 않는다.
- 둘째, **prefill과 decode의 자원 성격이 정반대**(연산 바운드 vs 메모리 바운드)라 무엇을 손봐야 할지가 갈리는데, 그 판별을 해 주는 것이 정확히 루프라인이다.
- 셋째, 세대마다 연산이 대역폭보다 빨리 늘어 **ridge가 오른쪽으로 밀리므로** decode는 점점 더 왼쪽에 갇히고, 그것을 모르면 최적화 방향을 정반대로 잡기 쉽다. 그리고 그 진단을 제대로 하려면 배칭이 듣는 부분과 안 듣는 부분을 나눠야 한다.

## 세 점으로 나누기

LLM 서빙에서 루프라인을 활용하기 위해서는 **워크로드를 한 덩어리로 보면 안 되고, 최소 세 점으로 나눠 찍어야 한다.**

| 점 | $I$ | 배치 $B$를 키우면 | 이유 |
| --- | --- | --- | --- |
| **prefill** (FFN·projection) | $S$에 비례, 수백 | 이미 연산 바운드 | 가중치를 $S$개 토큰이 공유 |
| **decode-FFN·projection** | $\approx B$ | **오른쪽으로 이동** | 가중치를 $B$개 요청이 공유 |
| **decode-attention** | $\approx 1$에서 사실상 고정 | **움직이지 않는다** | KV 캐시는 요청마다 별개 → $W$와 $Q$가 같이 $B$배 |

- **decode-FFN의 강도가 배치 크기와 같아지는 이유**: FP16 가중치 원소 하나(2 byte)에 곱 1 + 합 1 = 2 FLOP이므로 배치 1에서 $I = 2/2 = 1$ FLOP/byte다. 배치가 $B$면 그 원소를 $B$번 재사용하니 $I \approx B$로 올라간다. 즉 배치 크기가 그대로 연산 강도가 된다
- 그런데 ridge는 A100 $\approx 156$, H100 $\approx 295$다. **배치가 300 근처가 되어야 겨우 연산 바운드로 넘어간다.** 배치 1이면 H100 지붕의 $1/295 \approx 0.3\%$밖에 못 쓴다. "H100인데 왜 이렇게 느린가"의 답이 이 한 줄에 전부 있다
- **decode-attention은 배칭으로 나아지지 않는다.** 요청이 $B$개면 KV도 $B$세트를 읽어야 하므로 $W$와 $Q$가 나란히 $B$배가 되고, 비율은 그대로다. GQA/MQA(KV 헤드 수를 줄여 KV 트래픽을 낮추는 어텐션 변형), KV 양자화, paged KV가 배칭과 **별개로** 필요한 이유가 여기에 있다
- 그래서 프로파일할 때도 커널을 한 점으로 뭉치지 말고 세 점으로 나눠 찍어야 한다. 한 덩어리로 보면 FFN의 개선이 attention의 정체를 가리거나 그 반대가 된다

## H100 숫자로 확인

이 구도를 H100 숫자로 직접 확인해 보면($\pi \approx 990$ TFLOP/s BF16, $\beta \approx 3.35$ TB/s → $I^{*} \approx 295$ FLOP/byte) 이렇게 된다.

**decode, batch=1**: $I \approx 1$. ridge($\approx 295$)에서 한참 왼쪽이므로 완전한 메모리 바운드다. 상한을 대역폭으로 직접 계산할 수 있다.

$$
\text{tok/s} \lesssim \frac{\beta}{\text{모델 바이트}} = \frac{3.35\times10^{12}}{1.4\times10^{10}} \approx 240
$$

7B FP16이면 단일 GPU에서 초당 대략 240토큰이 이론 상한이다(KV 캐시·오버헤드 무시). 커널을 아무리 잘 짜도 이 값을 넘을 수 없다. 넘었다면 가중치가 캐시에 남아 있거나 계산이 틀렸다.

**decode, batch=B**: $I \approx B$. ridge가 $\approx 295$이므로 **배치가 수백 규모가 되어야 비로소 사선을 벗어난다.** 이것이 [continuous batching]({% post_url 2026-08-14-Dev-LLM-Serving-Optimization-03-02-LLM-Serving-From-Scratch-Batch-Request %})이 LLM 서빙의 핵심 기법인 이유다 — 처리량을 늘리는 트릭이 아니라, 점을 사선에서 떼어내는 사실상 유일한 수단이다. 다만 배칭은 공짜가 아니다. 루프라인은 처리량 모델이라 지연을 말하지 않는데, 배치를 키우면 토큰당 지연(TPOT)은 나빠진다. 사선 탈출은 처리량 관점의 처방이고, 지연 SLO가 있는 서빙에서는 그 트레이드오프 위에서 배치 크기를 고른다.

**prefill**: $I$가 프롬프트 길이 $S$에 비례해 수백까지 올라가므로 ridge 오른쪽, 연산 바운드다.

## 평가 지표

그래서 **prefill과 decode는 애초에 다른 지표로 평가해야 한다.**

|  | 병목 | 어느 지붕 | 무엇을 봐야 하나 | 처방 |
| --- | --- | --- | --- | --- |
| **prefill** | 연산기 | 수평 | 텐서코어 활용률, MFU | 저정밀도, 텐서코어, 커널 튜닝 |
| **decode** | 대역폭 | 사선 | 달성 대역폭 (`DRAM_ACTIVE`) | 배칭, 양자화, KV 캐시 관리 |

같은 MFU(Model FLOPs Utilization — 하드웨어 연산 peak의 몇 %를 실제 모델 연산에 쓰고 있나) 숫자로 둘을 나란히 평가하면 decode는 항상 낮게 나오는데, 그것은 커널이 나쁜 게 아니라 **애초에 도달 가능한 지붕이 낮기 때문**이다. decode의 성적표는 MFU가 아니라 "대역폭을 몇 % 썼는가"다. 한 가지 보정도 필요하다. decode의 $Q$는 가중치만이 아니라 **가중치 + KV 캐시**다. 컨텍스트가 길어지면 KV 쪽이 트래픽을 지배하기 시작하고, KV는 요청마다 다르므로 배칭으로 공유되지 않는다. 즉 컨텍스트가 길어질수록 배칭의 효과가 줄어든다. 위의 $\approx 240$ tok/s 계산도 KV를 무시한 낙관적 상한이다.

<br>

# 최적화 기법

Roofline Model을 기준으로 **점을 어느 방향으로 옮기는가 / 지붕을 어떻게 바꾸는가**로 정리하면, 어떤 상황에서 어떤 최적화 해법을 골라야 하는지가 보인다.

| 기법 | roofline 상 동작 | 언제 듣나 |
| --- | --- | --- |
| Continuous batching | 점을 오른쪽으로 ($I \approx B$) | decode-FFN이 사선에 붙어 있는 동안 |
| Weight-only INT4 | $Q$를 $1/4$로 → $I$ 4배 | **저배치에서만** |
| FlashAttention | $S^2$ 중간 행렬을 HBM에 안 적어 $Q$ 감소 → 점 오른쪽 | prefill attention |
| GQA/MQA, KV 양자화, paged KV | KV 트래픽 감소 → attention 점 오른쪽 | decode-attention |
| Speculative decoding | 가중치 1회 읽고 $k$토큰 검증 → $I$를 최대 $k$배 | 저배치·저지연 |
| Chunked prefill | 연산 바운드 작업과 메모리 바운드 작업을 섞어 두 지붕을 동시에 사용 | prefill·decode 혼재 |
| AMP / FP8 | **지붕 자체를 위로** (동시에 ridge도 오른쪽으로) + $Q$ 감소로 점도 오른쪽 | 전 구간 |

> **자주 나는 오판: INT4가 처리량을 올려 줄 것이라고 기대하는 것.** 고배치에서는 이미 점이 수평 지붕 쪽으로 넘어가 있으므로 $Q$를 줄여도 상한이 오르지 않고, dequant 오버헤드($W$ 증가)만 붙어서 오히려 느려질 수 있다. **저지연(저배치) 최적화와 고처리량(고배치) 최적화는 서로 다른 지붕을 상대하는 작업이다.** [1편의 2단 판단]({% post_url 2026-08-21-CS-Roofline-Model %}#2단-판단)의 순서를 그대로 쓰면 된다 — 지금 점이 어떤 지붕에 붙었는지를 밝힌 다음에야 기법을 고를 수 있다.

<br>

# 정리

LLM 서빙 워크로드는 한 덩어리가 아니다. prefill(연산 바운드), decode-FFN($I \approx B$, 배칭으로 이동 가능), decode-attention(KV 캐시 탓에 배칭으로도 고정) — 이 세 점을 나눠 찍어야 배칭이 듣는 부분과 안 듣는 부분이 구분되고, 그다음에야 기법을 고를 수 있다. 판단 순서는 루프라인의 일반 규칙 그대로다: 점이 지붕에 붙었는지 먼저, 붙었다면 어느 지붕인지 — 그 답이 처방을 결정한다.

<br>

# 참고 링크

- [Roofline 모델: 연산 강도로 판별하는 성능 병목]({% post_url 2026-08-21-CS-Roofline-Model %})
- [Williams, Waterman, Patterson, "Roofline: An Insightful Visual Performance Model for Multicore Architectures", CACM 2009](https://escholarship.org/content/qt78h8v7mr/qt78h8v7mr.pdf)
- [LLM Inference Unveiled: Survey and Roofline Model Insights (arXiv:2402.16363)](https://arxiv.org/abs/2402.16363)
- [LLM 서빙과 최적화 3.3편 — prefill과 decode]({% post_url 2026-08-14-Dev-LLM-Serving-Optimization-03-03-LLM-Serving-Prefill-Decode %})
- [LLM 서빙과 최적화 3.2편 — 배치 요청]({% post_url 2026-08-14-Dev-LLM-Serving-Optimization-03-02-LLM-Serving-From-Scratch-Batch-Request %})

<br>
