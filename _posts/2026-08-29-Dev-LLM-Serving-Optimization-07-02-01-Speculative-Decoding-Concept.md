---
title: "[LLM] LLM 서빙과 최적화: 고급 최적화 기법 - 7.2.1. speculative decoding 원리: 추측, 병렬 검증, 분포 보존"
excerpt: "추측과 병렬 검증으로 decode를 가속하는 speculative decoding의 원리에 대해 알아 보자."
categories:
  - Dev
toc: true
header:
  teaser: /assets/images/blog-Dev.jpg
tags:
  - LLM-Serving
  - Speculative-Decoding
  - Rejection-Sampling
  - EAGLE
  - Medusa
  - N-gram
  - Hands-On-LLM-Serving-and-Optimization-Study
  - Hands-On-LLM-Serving-and-Optimization-Study-Week-4
last_modified_at: 2026-08-29
---

*[서종호(가시다)](https://www.linkedin.com/in/gasida99/)님의 Hands-On LLM Serving and Optimization Study (LLMSO) 4주차 학습 내용을 기반으로 합니다.*

<br>

# TL;DR

- decode는 자기회귀 제약 때문에 target forward 1회당 토큰 1개만 생성하고, 그 forward의 시간은 대부분 가중치 읽기다. speculative decoding은 **작은 draft 모델이 후보 K개를 추측하고, target이 한 번의 forward로 병렬 검증**해 가중치 읽기 1회에 최대 K+1개 토큰을 확정한다
- 검증은 rejection sampling(기각 샘플링)이다: target 확률이 draft 확률 이상이면 수락, 낮으면 비율만큼 확률적으로 수락하고, 거부되면 잔여 분포에서 다시 샘플링한다. 이 규칙 덕에 **출력 분포가 target 혼자 생성했을 때와 수학적으로 동일**하다 — draft가 나빠도 품질이 아니라 속도만 나빠진다
- draft 선택지는 넷이다: 같은 계열 소형 모델, 증류, 셀프 드래프팅(Medusa·EAGLE), n-gram. 오버헤드가 거의 없는 n-gram이 첫 시도로 권장되고, 성능은 EAGLE 계열이 앞선다
- K(draft 토큰 개수)는 2~4에서 시작해 보통 4~8, 구조화된 출력이면 16~32까지 늘릴 수 있다. 위치별 수락률을 보고 이득 없는 뒷부분을 잘라내는 것이 실전 튜닝법이다
- 이득의 전제는 decode가 memory-bound라 연산 유닛이 놀고 있다는 것이다. prefill이나 큰 배치처럼 이미 compute-bound인 구간에서는 효과가 없거나 처리량을 해친다

<br>

# 문제: 한 스텝에 토큰 하나

[6.1편]({% post_url 2026-08-22-Dev-LLM-Serving-Optimization-06-01-LLM-Serving-Optimization-Techniques-Overview %}#실행-단위-iteration)에서 서빙 엔진의 실행 단위를 iteration — 모델 forward 1회 — 으로 잡았다. decode iteration 하나는 토큰 1개를 만들기 위해 가중치 전체를 HBM에서 읽고, [5.4편]({% post_url 2026-08-22-Dev-LLM-Serving-Optimization-05-04-LLM-Serving-Challenge-Loading-Execution-Bottleneck %}#prefill과-decode의-산술-강도)에서 본 대로 그 시간의 대부분이 계산이 아니라 읽기다. 연산 유닛은 놀고 있다.

6장은 이 비효율을 [세 방향]({% post_url 2026-08-22-Dev-LLM-Serving-Optimization-06-01-LLM-Serving-Optimization-Techniques-Overview %}#6장의-지도-하나의-분수-세-방향의-공략)에서 공략했다. 그중 노는 연산을 다른 요청의 일로 채우는 정면 대응이 [배칭]({% post_url 2026-08-22-Dev-LLM-Serving-Optimization-06-01-LLM-Serving-Optimization-Techniques-Overview %}#배칭-한-번-읽은-가중치로-여러-요청)인데, 배칭이 올리는 것은 시스템의 처리량이지 요청 하나의 속도가 아니다 — 내 요청의 토큰 간 지연(ITL, Inter-Token Latency — [3.3편의 서빙 지표]({% post_url 2026-08-14-Dev-LLM-Serving-Optimization-03-03-LLM-Serving-Prefill-Decode %}#서빙-지표-ttft와-tpot) 참고)은 여전히 스텝 시간 그대로이고, 전체 생성 시간은 "스텝 시간 × 내 토큰 수"다. 스텝 시간의 하한은 가중치 읽기 시간이라 모델이 클수록 올라간다. 요청이 몰리지 않는 저부하 상황이라면 배칭으로 채울 다른 요청도 없다. 나머지 두 방향은 단일 요청에도 유효하지만 각도가 다르다. 어텐션 최적화·모델 압축은 스텝이 옮길 바이트를 줄여 스텝 시간 자체를 낮추되 아키텍처 변경이나 정밀도와의 거래가 따르고, 줄인 뒤에도 "읽기 1회당 토큰 1개"라는 구조는 그대로다. 프리픽스 캐싱은 prefill의 재계산을 피하는 기법이라 decode의 반복에는 손을 대지 않는다.

이제 관점을 바꿔 보자. **요청 하나의 decode 자체를 빠르게 할 수는 없을까?** 스텝당 토큰이 1개인 이유는 자기회귀 제약, 즉 다음 토큰이 이전 토큰에 의존하기 때문이다. 토큰 N+1을 계산하려면 토큰 N이 확정되어 있어야 하니, 원리적으로 건너뛸 수 없어 보인다. 하지만 우회할 길은 있다 — **확정을 기다리는 대신 일단 추측하고, 추측이 맞았는지를 검증으로 확인하는 것**이다. 검증을 병렬로 할 수만 있다면, 자기회귀 제약을 깨지 않고도 한 번에 여러 토큰을 확정할 수 있다.

이 아이디어는 익숙한 구도이기도 하다. 대규모 검색·추천 시스템은 수백만 후보를 작고 부정확한 모델로 먼저 걸러 수천 개로 줄인 뒤, 크고 정확한 모델을 남은 후보에만 적용한다. 같은 일을 토큰 단위에서 한다고 보면 이해가 쉽다 — 작은 모델이 후보를 만들고, 큰 모델은 채점만 한다.

<br>

# 핵심 구조: draft의 추측과 target의 검증

**speculative decoding(추측 디코딩)은 앞의 아이디어를 그대로 구현한 디코딩 기법이다 — 작은 보조 모델이 다음에 올 토큰 후보 여러 개를 먼저 생성하고, 원래 서빙하려던 모델이 그 후보들을 한 번의 forward로 병렬 검증해 수락·거부한다.** 그래서 두 모델이 등장한다. 앞 절까지 "모델"이라고만 불러 온 서빙 대상이 여기서는 target이라는 이름을 얻고, 그 옆에 추측을 전담하는 보조 모델이 하나 붙는다.

- **target 모델**: 사용자에게 응답을 내야 하는 서빙 대상 모델이다. speculative decoding을 붙이기 전부터 서빙하던 크고 정확한 모델로, 최종 출력이 따라야 할 확률 분포의 기준이고 모든 토큰의 확정 권한이 target에 있다
- **draft 모델**(초안 모델): 후보 토큰을 빠르게 만들어 내는 작은 보조 모델이다. 보통 target의 수십분의 일 크기이고, target과 같은 토크나이저를 써야 한다 — 같은 토큰 공간에서 제안해야 target이 검증할 수 있다. 역할은 제안뿐이라 draft의 출력이 검증 없이 사용자에게 나가는 일은 없다

운영상 주의할 점이 하나 있다. 이 구조에서는 **두 모델을 같은 GPU에 함께 올리고, 매 iteration 둘 다 실행**해야 한다. draft를 별도 서버로 배포하는 것이 아니라 서빙 엔진 안에 target과 나란히 로드하는 구성이고(vLLM에서는 [서버 기동 옵션으로 draft를 지정]({% post_url 2026-08-29-Dev-LLM-Serving-Optimization-07-02-02-Speculative-Decoding-Hands-On %}#변형별-서버-기동)한다), 그만큼 draft 가중치가 GPU 메모리를 차지해 KV cache의 몫을 줄이고, 운영도 복잡해진다. 이 비용이 [뒤에서 볼](#셀프-드래프팅-medusa와-eagle) 셀프 드래프팅과 n-gram의 등장 동기가 된다.

적재 구조를 그림으로 보면 다음과 같다.

[![두 모델의 적재 구조]({{site.url}}/assets/images/llmso-ch07-specdecode-deployment.svg){: .align-center width="820"}]({{site.url}}/assets/images/llmso-ch07-specdecode-deployment.svg){: target="_blank" }

<center><sup>AI를 이용해 직접 그린 도식. draft는 별도 서버가 아니라 target과 같은 엔진 프로세스·같은 GPU에 로드된다. 예시 수치는 7.2.2편 실습 구성이다</sup></center>

## 한 iteration의 네 단계

speculative decoding의 한 iteration은 네 단계로 돈다.

[![speculative decoding 한 iteration]({{site.url}}/assets/images/llmso-ch07-specdecode-iteration.svg){: .align-center width="820"}]({{site.url}}/assets/images/llmso-ch07-specdecode-iteration.svg){: target="_blank" }

<center><sup>출처: Hands-On LLM Serving and Optimization (O'Reilly) 그림 7-1. AI를 이용해 재구성했다</sup></center>

1. **draft 모델이 K개 토큰을 자기회귀로 추측한다**(token speculation). K는 draft가 한 번에 추측하는 토큰 개수로, 뒤에서 볼 핵심 튜닝 파라미터다. draft도 자기회귀라 forward를 K번 돌지만, 모델이 작아 한 번 한 번이 가볍다
2. **target 모델이 한 번의 forward로 K개를 병렬 검증한다**(parallel verification). 혼동하면 안 되는 것이 있는데, **자기회귀를 K번 도는 것이 아니다.** 프롬프트 뒤에 draft 토큰들을 이어 붙여 시퀀스로 넣으면, target은 forward 1회로 각 위치에서 "내가 여기서 다음 토큰에 부여하는 확률 분포"를 전부 계산한다. [prefill이 프롬프트 전체를 한 forward로 처리하는 것]({% post_url 2026-08-14-Dev-LLM-Serving-Optimization-03-03-LLM-Serving-Prefill-Decode %}#프롬프트-병렬-처리-prefill의-기원)과 같은 원리다. 일반 decode가 forward를 토큰마다 도는 이유는 계산이 순차적이어야 해서가 아니라 **다음 위치의 입력 토큰이 아직 존재하지 않기 때문**인데, 지금은 draft가 그 토큰들을 미리 공급해 뒀다. 그래서 자기회귀로 K번 돌았을 때 각 스텝에서 나왔을 분포와 정확히 같은 것들이 forward 1회에서 한꺼번에 나온다 — 가중치 읽기 K번이 1번이 되는 지점이고, 이 절약의 크기는 [이득의 원리](#이득의-원리-가중치-읽기-1회당-생성-토큰-수)에서 계산한다
3. **위치별로 수락/거부를 판정한다.** target의 확률이 draft의 확률 이상이면 그대로 수락하고, 낮으면 두 확률의 비율만큼 확률적으로 수락한다 (규칙의 정확한 형태는 [다음 절](#검증-알고리즘-rejection-sampling과-분포-보존)에서). 한 토큰이 거부되는 순간 **그 이후의 draft 토큰은 전부 폐기한다** — 생성이 자기회귀적이라 앞 토큰이 바뀌면 그 뒤의 추측은 전제부터 무효이기 때문이다
4. **거부 지점에서 target이 직접 토큰 1개를 생성한다.** 2단계의 forward가 그 위치의 분포를 이미 계산해 뒀으므로 추가 forward 없이, 거부된 토큰을 반영해 조정한 분포에서 새 토큰을 샘플링한다. 여기서부터 다음 iteration이 다시 시작된다

> 참고: [6.1편]({% post_url 2026-08-22-Dev-LLM-Serving-Optimization-06-01-LLM-Serving-Optimization-Techniques-Overview %}#실행-단위-iteration)에서 iteration을 "모델 forward 1회"로 정의했는데, speculative decoding에서는 이 등식이 확장된다. 스케줄러가 개입하는 스텝 경계라는 의미는 그대로지만, 한 스텝 안에서 도는 forward가 1회가 아니라 draft K회 + target 1회다 (별도 draft 모델 기준 — n-gram이면 draft 쪽 forward가 아예 없고, 셀프 드래프팅이면 draft 몫이 target에 붙은 경량 헤드·모듈의 forward로 줄어든다). 이 글에서 "한 iteration"은 위 네 단계 전체를 가리킨다.

[문제 절](#문제-한-스텝에-토큰-하나) 말미에 "큰 모델은 채점만 한다"고 했는데, 그 채점의 실체가 2단계인 것이다. 검증은 별도의 절차가 아니라 **target의 forward 1회** 그 자체이고, target이 각 위치에서 자기가 그 토큰을 뱉을 확률을 계산해 draft의 확률과 비교하는 일이다. draft 생성 K회와 target 검증 1회가 직렬로 이어지지만, 비교 대상이 "target forward K+1회"라는 점이 중요하다 — draft가 target의 수십분의 일 크기라면 draft K회는 target 1회보다도 싸다.

이 2단계의 내부를 [셀프 어텐션 정리 글]({% post_url 2026-08-05-AI-LLM-Optimization-02-05-Transformer-Explainer-Self-Attention %})에서 본 causal mask 행렬로 펼치면 다음과 같다. 각 계산 위치(행)는 자기 이전 위치(열)만 참조하고, 네 행이 한 번의 forward에서 동시에 계산된다.

[![검증 forward 1회의 내부 — causal mask 위의 병렬 계산]({{site.url}}/assets/images/llmso-ch07-specdecode-parallel-verification-matrix.svg){: .align-center width="860"}]({{site.url}}/assets/images/llmso-ch07-specdecode-parallel-verification-matrix.svg){: target="_blank" }

<center><sup>AI를 이용해 직접 그린 도식. 각 행의 출력 분포는 자기회귀로 그 지점까지 갔을 때의 분포와 동일하다 — draft가 입력 토큰을 미리 공급했기 때문에 순차 없이 계산할 수 있다</sup></center>

한 iteration이 끝나면 확정된 시퀀스 위에서 같은 네 단계가 다시 돈다. 몇 번의 iteration을 시계열로 늘어놓으면 다음과 같다 — 거부가 나도 iteration당 최소 1개는 확정되고, 전부 수락되면 보너스 토큰까지 K+1개가 확정된다 (보너스의 정확한 규칙은 [후술](#수락률과-수락-길이)).

[![iteration의 반복 — 거부 후 재시작]({{site.url}}/assets/images/llmso-ch07-specdecode-iteration-timeline.svg){: .align-center width="860"}]({{site.url}}/assets/images/llmso-ch07-specdecode-iteration-timeline.svg){: target="_blank" }

<center><sup>AI를 이용해 직접 그린 도식. 거부된 draft는 폐기되고 target이 만든 토큰이 그 자리를 채우며, 다음 iteration은 확정된 시퀀스 위에서 재시작한다</sup></center>

## 이득의 원리: 가중치 읽기 1회당 생성 토큰 수

그런데 앞 절의 네 단계를 횟수로만 세면 일이 오히려 늘어 있다. 일반 decode가 토큰 하나에 target forward 1회를 쓰는 동안, 이 구조는 draft forward K회에 target forward 1회까지 쓴다. 그런데도 총 시간이 줄어든다 — 직관적이지는 않지만, 이것이 speculative decoding을 통해 얻고자 하는 이득이다. 왜 그런지를 계산해 보면, 시간을 지배하는 것이 forward의 횟수가 아니라 **target 가중치를 HBM에서 읽는 횟수**라는 데 답이 있다. decode가 memory-bound라는 사실이 계산에 두 번 쓰인다.

첫째, **target 가중치 읽기 횟수가 줄어든다.** 일반 decode에서 토큰 3개는 forward 3회, 즉 가중치 전체 읽기 3회다. speculative decoding에서 한 iteration에 토큰 3개가 확정되면 target 읽기는 1회다.

[![토큰 3개를 만드는 두 경로의 HBM 이동량]({{site.url}}/assets/images/llmso-ch07-specdecode-memory-traffic.svg){: .align-center width="820"}]({{site.url}}/assets/images/llmso-ch07-specdecode-memory-traffic.svg){: target="_blank" }

<center><sup>출처: The Engineering Behind LLM Inference: Speculative Decoding and Long Context (YouTube). 예제 수치를 바탕으로 AI를 이용해 재구성했다</sup></center>

70B(bf16, 140GB) target에 1.4GB짜리 draft를 붙인 위 예제에서, 토큰 3개의 HBM 이동량은 420GB에서 147GB로 줄어든다. decode 스텝 시간이 곧 메모리 이동 시간이므로 이 비율이 거의 그대로 속도가 된다.

둘째, **검증 forward는 토큰 1개짜리 forward와 비용이 거의 같다.** 검증 입력은 S축이 1에서 K+1로 늘어난 텐서인데, memory-bound 구간에서는 스텝 시간을 가중치 읽기가 지배하므로 계산할 위치가 몇 개 늘어도 스텝 시간이 거의 변하지 않는다. [6.1편의 배칭]({% post_url 2026-08-22-Dev-LLM-Serving-Optimization-06-01-LLM-Serving-Optimization-Techniques-Overview %}#처리량-이득의-원리)이 B축에서 쓴 상각을 그대로 S축에서 쓰는 것이다.

이 대칭은 그대로 이 기법의 위치를 정한다. 배칭은 가중치 읽기 1회를 **다른 요청들의 토큰**으로 나눠 쓰고, speculative decoding은 **같은 요청의 미래 토큰 후보**로 나눠 쓴다. 나눠 쓰는 자원 — 가중치를 읽는 동안 노는 연산 — 이 같으므로 둘은 경쟁 관계다. 요청이 몰려 배치가 그 자원을 이미 채우고 있으면 speculative decoding이 가져갈 몫이 없고, 오히려 거부된 후보에 쓴 연산이 손실로 남는다.

[![가중치 읽기 1회의 연산 슬롯 — 저부하와 고부하]({{site.url}}/assets/images/llmso-ch07-specdecode-slot-competition.svg){: .align-center width="860"}]({{site.url}}/assets/images/llmso-ch07-specdecode-slot-competition.svg){: target="_blank" }

<center><sup>출처: The Engineering Behind LLM Inference: Speculative Decoding and Long Context (YouTube). 예제 수치를 바탕으로 AI를 이용해 재구성했다</sup></center>

[7.1편의 병목 축]({% post_url 2026-08-29-Dev-LLM-Serving-Optimization-07-01-LLM-Serving-Advanced-Techniques-Overview %}#병목-축-compute-bound와-memory-bound)에서 정리한 이 조건은 [적용 한계](#효과가-사라지는-조건)에서 다시 정리하고, [7.2.2편]({% post_url 2026-08-29-Dev-LLM-Serving-Optimization-07-02-02-Speculative-Decoding-Hands-On %})에서 실측으로 확인한다.

<br>

# 검증 알고리즘: rejection sampling과 분포 보존

속도만 보면 "작은 모델이 대신 생성"하는 것과 다를 게 없어 보인다. 이 기법이 성립하는 진짜 이유는 검증 규칙이 **출력 분포를 target 혼자 생성했을 때와 수학적으로 동일하게 보존**한다는 데 있다. 규칙을 뜯어 보자.

## 수락 규칙

어떤 위치에서 draft가 토큰 x를 제안했다고 하자. draft가 x에 부여한 확률을 q(x), target이 같은 위치에서 x에 부여한 확률을 p(x)라고 하면, 수락 확률은 다음과 같다.

$$
P(\text{수락}) = \min\!\left(1,\ \frac{p(x)}{q(x)}\right)
$$

- **p(x) ≥ q(x)**: 무조건 수락한다. target이 보기에 draft가 그 토큰을 오히려 덜 제안했으니, 제안된 김에 전부 받아도 target 기준으로 과잉이 아니다
- **p(x) < q(x)**: 비율만큼만 수락한다. 책의 예를 빌리면, "The soccer team of the United" 다음에 draft가 "States"를 확률 0.6으로 제안했는데 target은 0.4를 매겼다면, 0.4/0.6 = 2/3의 확률로 수락한다. draft가 target보다 1.5배 과하게 제안하는 토큰이니 3번 중 1번은 걸러서 빈도를 target 수준으로 맞추는 것이다

확률적 수락의 구현은 단순하다 — 판정 순간에 균일 난수 u를 하나 뽑아 u < p/q면 수락한다. 과거에 몇 번 수락했는지를 기억하거나 집계하는 장치는 없고, 매 판정이 독립이다. "2/3의 확률"은 이 독립 시행의 장기 빈도이고, 아래에서 볼 분포 보존도 개별 판정이 아니라 이 기대값 수준에서 성립한다.

## 거부 시 잔여 분포 샘플링

거부가 일어나면 target이 그 위치의 토큰을 직접 뽑는데, 원래 분포 p가 아니라 **잔여 분포**(residual distribution)에서 뽑는다. target 분포에서 draft 분포를 빼고, 음수를 0으로 클리핑한 뒤, 남은 값의 합으로 재정규화한 분포다.

$$
p'(x) = \frac{\max\!\left(0,\ p(x) - q(x)\right)}{\sum_{x'} \max\!\left(0,\ p(x') - q(x')\right)}
$$

여기에 추가 forward는 없다. 일반 decode에서도 forward가 하는 일은 분포를 계산하는 것까지이고, 그 분포에서 토큰을 뽑는 것은 모델 밖 샘플러의 몫이다. 지금 p는 [검증 forward](#한-iteration의-네-단계)가 이미 내놓은 값이고 q는 draft가 준 값이므로, 잔여 분포는 두 벡터의 뺄셈·클리핑·정규화라는 가벼운 후처리다 — 샘플러가 참조하는 분포만 p에서 p′로 바뀐다. p′는 미리 만들어 두거나 학습하는 별도의 분포가 아니라, 거부가 난 위치에서 그때그때 계산해 한 번 쓰고 버리는 임시 분포다.

이 분포여야 하는 이유는, 수락 경로만으로는 target 분포를 다 채울 수 없기 때문이다. 수락 경로에서 토큰 x가 최종 출력될 확률은 q(x)·min(1, p(x)/q(x)) = min(p(x), q(x))다. draft가 과잉 제안한 토큰(q > p)은 수락 필터가 정확히 p(x)까지 깎아 주지만, 과소 제안한 토큰(q < p)은 전부 수락해도 q(x)만큼밖에 못 나온다 — p(x) 대비 **모자란 몫**이 max(0, p−q)다. 그런데 거부가 일어날 총 확률이 정확히 이 모자란 몫들의 합과 같다. 그러니 거부가 났을 때 모자란 몫에 비례해 뽑아 주면, 수락 경로와 거부 경로의 합이 모든 토큰에서 p(x)로 복원된다. 잔여 분포는 곧 수락 경로가 채우지 못한 부족분의 목록이다.

구체적인 수치로 확인하면 다음과 같다.

[![rejection sampling — 거부가 일어나도 target 분포가 보존된다]({{site.url}}/assets/images/llmso-ch07-specdecode-rejection-sampling.svg){: .align-center width="860"}]({{site.url}}/assets/images/llmso-ch07-specdecode-rejection-sampling.svg){: target="_blank" }

<center><sup>출처: The Engineering Behind LLM Inference: Speculative Decoding and Long Context (YouTube). 예제 수치를 바탕으로 AI를 이용해 재구성했다</sup></center>

그림의 검산 패널이 이 복원을 다섯 토큰 전부에서 확인한다.

speculative decoding을 소개할 때 흔히 따라붙는 말이 "**품질 손실이 없다(lossless)**"인데, 그 정확한 의미가 이것이다. 출력 문장이 target 단독 생성과 토큰 단위로 같다는 뜻이 아니라(둘 다 확률적 샘플링이다), **출력이 따르는 확률 분포가 같다**는 뜻이다. 따라서 draft 모델이 아무리 형편없어도 출력 품질은 target과 동일하다 — 나쁜 draft가 해치는 것은 품질이 아니라 수락률, 즉 속도뿐이다. draft를 공격적으로 양자화해도 되는 근거이고, [후술할 Kakao 발표 사례](#실전-사례-kakao의-speculative-decoding)에서 볼, draft가 생각보다 훨씬 작아도 된다는 관찰의 근거이기도 하다. 참고로 temperature 0의 greedy decoding이라면 p가 argmax 토큰에 몰린 one-hot이 되어, 이 규칙은 "draft 토큰이 target의 argmax와 일치하면 수락"으로 단순해진다.

## 수락률과 수락 길이

이 기법의 성능을 말하는 지표 두 개를 정의해 두자. [7.2.2편]({% post_url 2026-08-29-Dev-LLM-Serving-Optimization-07-02-02-Speculative-Decoding-Hands-On %})의 실측 분석에서 그대로 쓴다.

- **수락률(acceptance rate)** — draft가 생성한 토큰 중 수락된 비율
- **수락 길이(acceptance length)** — iteration 하나가 확정하는 토큰 수. 수락된 draft 토큰 s개에 target이 직접 만든 1개를 더한 s+1이다. 거부가 났으면 그 1개는 잔여 분포에서 뽑은 대체 토큰이고, K개가 전부 수락됐으면 검증 forward가 이미 계산해 둔 K+1번째 위치의 분포에서 보너스로 1개를 더 뽑는다. 그래서 수락 길이의 범위는 1 이상 K+1 이하다 — **전부 거부돼도 1개는 나온다**. 일반 decode와 같은 속도가 하한이 아니라, draft를 돌린 비용만큼만 손해가 하한이다

간단한 예로 K=3짜리 두 iteration을 따라가 보자. 첫 iteration에서 draft 3개 중 2개가 수락되고 3번째에서 거부됐다면, 수락 길이는 2+1=3(수락 2개 + 잔여 분포 토큰 1개)이다. 두 번째 iteration에서 3개 전부 수락됐다면 수락 길이는 3+1=4(수락 3개 + 보너스 1개)다. 두 iteration을 합치면 draft 토큰 6개 중 5개가 수락됐으니 수락률은 5/6 ≈ 0.83이고, target forward 2회로 토큰 7개를 확정했다.

speculative decoding의 성능은 결국 이 수락 길이가 얼마나 크고 **일관되게** 나오느냐에 달려 있다. 수락률이 낮으면 draft 생성과 검증에 쓴 자원 대부분이 폐기로 끝난다.

<br>

# draft를 고르는 네 가지 방법

수락률을 좌우하는 첫 번째 선택이 draft다. 결론부터 말하면 실무의 시도 순서는 이렇다 — **학습 여력이 없다면 오버헤드가 거의 없는 n-gram부터 시도하고**, 학습이 가능하다면 target에 정렬된 draft(증류한 소형 모델이나 셀프 드래프팅 모듈)로 올라간다. 성능만 보면 2025년 말 기준 EAGLE 계열이 셀프 드래프팅 중 가장 앞서 있다.

| 방법 | 방식 | 장점 | 단점 |
|------|------|------|------|
| 기존 소형 모델 | 같은 계열의 작은 모델을 그대로 사용 | 구현이 간단 | 정렬이 안 맞으면 수락률 낮음 |
| 증류(distillation) | target으로부터 소형 draft를 직접 학습 | 수락률 향상, target 스타일 특화 | 별도 학습 필요 |
| 셀프 드래프팅 (Medusa, EAGLE) | target 자체에 예측 헤드·보조 모듈 추가 | 별도 모델 불필요, 메모리 절약, 정렬 우수 | 추가 학습·튜닝 필요 |
| n-gram | 시퀀스 내 반복 패턴을 테이블화해 매칭 | 오버헤드 거의 0, 가장 간단 | 반복성 낮은 자유 생성에 약함 |

## 기존 소형 모델과 증류

가장 단순한 선택은 같은 계열(family)의 작은 모델이다. 같은 토크나이저와 사전학습을 공유하므로 확률 분포가 비슷하게 나와 수락률에 실질적으로 유리하다. draft는 공격적으로 양자화해도 좋다 — 앞 절에서 본 대로 target이 항상 폴백이라 품질 부담이 없다.

학습이 가능하다면 기존 모델을 고르기보다 **target으로부터 draft를 증류**하는 쪽이 보통 낫다. 여기서 증류는 knowledge distillation 그대로다 — target(교사 모델)이 내놓는 확률 분포를 정답 삼아, 작은 모델(학생)이 같은 입력에서 그 분포를 재현하도록 학습시키는 기법이다. 증류로 만든 정렬(alignment)은 draft의 예측과 target의 검증 사이 불일치를 줄여 수락률을 올린다. 수락 규칙의 수식을 다시 보면 당연한 귀결이다 — 수락 확률은 p와 q가 가까울수록 1에 붙는다.

## 셀프 드래프팅: Medusa와 EAGLE

별도 draft 모델은 그 자체로 비용이다. 작다고 해도 가중치가 GPU 메모리를 차지하고, 두 모델을 한 GPU에서 효율적으로 함께 돌리는 운영 부담도 있다. 셀프 드래프팅(self-drafting)은 draft 모델을 없애고 **target 모델 스스로 미래 토큰을 추측하게** 만든다 — target에 경량 예측 헤드나 보조 모듈을 붙여, 같은 forward 안에서 여러 단계 앞을 내다보게 하는 방식이다.

**Medusa**는 target 위에 예측 헤드(prediction head)를 여러 개 얹는다. 이름처럼 머리가 여럿인데, 멀티헤드 어텐션의 head와는 무관한 별개 개념이다. 원래 forward가 첫 번째 다음 토큰의 후보만 내놓는 자리에서, 각 Medusa 헤드가 같은 forward 안에서 두 번째·세 번째·네 번째 토큰 후보를 병렬로 추가 생성한다. 위치별 후보들을 조합해 후보 시퀀스 여러 개를 만들고 그중 가장 길게 수락되는 것을 고른다.

![Medusa의 셀프 드래프팅]({{site.url}}/assets/images/llmso-speculative-decoding-figure-7-2.png){: .align-center width="720"}

<center><sup>출처: Hands-On LLM Serving and Optimization (O'Reilly) 그림 7-2</sup></center>

**EAGLE**(Extrapolation Algorithm for Greater Language-model Efficiency)은 접근이 다르다. 토큰을 직접 추측하는 대신 **target의 미래 내부 hidden state를 예측**하도록 학습된 작은 보조 모듈을 쓰고, target이 그 예측된 hidden state로부터 토큰을 만들어 낸다. 토큰 공간보다 연속적인 hidden state 공간이 예측하기 안정적이라는 관찰에 기반한다. EAGLE-2는 텍스트가 얼마나 예측 가능한지에 따라 추측 길이를 조절하는 동적 draft 트리를 더했고, EAGLE-3는 여러 레이어의 feature를 융합해 입력으로 쓰되 예측 대상은 hidden state에서 직접 토큰으로 바꿔, 정확도를 한 단계 더 올렸다. 좋은 성능에는 그만큼 추가 학습과 튜닝이 필요하다.

![EAGLE-3의 feature 융합]({{site.url}}/assets/images/llmso-speculative-decoding-figure-7-3.png){: .align-center width="720"}

<center><sup>출처: Hands-On LLM Serving and Optimization (O'Reilly) 그림 7-3</sup></center>

## n-gram: 모델 없는 추측

세 번째 갈래는 모델이 아예 아니다. **n-gram 방식은 시퀀스 앞부분에서 인접 n개 토큰의 나열을 테이블에 저장해 두고, 방금 생성된 마지막 n-1개 토큰과 매칭되는 항목이 있으면 그 뒤에 왔던 토큰을 그대로 제안**한다. CPU에서의 배열 탐색이라 비용이 사실상 0이고 GPU 메모리도 쓰지 않는다.

| 트라이그램 테이블 (n=3) | 다음 토큰 | 카운트 |
|------------------------|-----------|--------|
| a quick brown | fox | 1 |
| quick brown fox | ran | 1 |

`An hour ago, a quick brown fox ran away and now, that quick brown` 뒤의 토큰을 예측해야 한다면, 테이블 첫 행을 근거로 `fox`를 제안하고 target은 검증만 하면 된다.

이 방식이 강력해지는 상황은 두 가지다. 하나는 JSON·SQL처럼 **구조화된 출력**을 만들 때 — 생성이 결정론적이고 반복 패턴을 따른다. 다른 하나는 **입력 프롬프트의 내용이 출력에 대량 재사용될 때**다. 문서를 다듬거나 정해진 템플릿을 채우는 요청이라면, 프롬프트 안의 템플릿 구조(`Subject:`, `Hi <이름>,` 같은 라인들)가 출력에 거의 그대로 등장하므로 n-gram 매칭이 잘 맞고, 그만큼 K를 높게 잡아 지연을 더 줄일 수 있다. 오버헤드가 워낙 작아 수락률이 낮아도 손해가 거의 없으니, **다른 draft를 검토하기 전에 가장 먼저 시도해 볼 방법**으로 권장된다.

<br>

# K 튜닝과 적용 한계

## draft 토큰 개수 K

draft를 정했다면 남는 조절 변수는 K, 즉 한 iteration에서 draft가 추측하는 토큰 개수다.

- **K가 크면** 속도 향상의 상한이 높아진다. 대신 수락률이 받쳐 주지 않으면 버려지는 토큰이 많아지고, 거부 시 폐기 비용도 커진다
- **K가 작으면** 검증하고 거부할 토큰이 적어 예측 가능하고 안정적이지만, 이득의 상한도 낮다

실무 권장은 2~4에서 시작해 늘려 가는 것이고, 많은 경우 최적은 4~8 사이다. 구조화된 출력이나 AI 에이전트의 함수 호출처럼 생성이 매우 예측 가능한 경우에는 16~32까지도 늘릴 수 있다. 튜닝의 근거는 **위치별 수락률**이다. 많은 서빙 프레임워크가 이를 노출하는데, 예컨대 K=6에서 위치별 수락률이 [0.8, 0.7, 0.6, 0.5, 0.10, 0.02]라면 다섯 번째부터는 추측이 거의 안 맞고 있다는 뜻이므로 K를 4로 줄이는 편이 낫다.

## 효과가 사라지는 조건

이 기법의 한계는 전부 [이득의 원리](#이득의-원리-가중치-읽기-1회당-생성-토큰-수)의 전제 — 노는 연산이 있다 — 가 깨지는 지점에서 나온다.

- **decode 단계에만 유효하다.** 긴 입력 컨텍스트의 prefill처럼 이미 compute-bound인 구간에는 맡길 노는 연산이 없다
- **큰 배치가 병목을 옮긴다.** 6장에서 본 대로 배칭은 병목을 memory-bound에서 compute-bound로 전환시킨다. 그 구간에서 speculative decoding은 지연에는 여전히 도움이 되지만, 거부된 후보의 잉여 연산이 전체 처리량을 갉아먹는다
- **운영이 어렵다.** 성능 향상이 보장되지 않는 데다, 공유 GPU 한 장에서 두 모델을 높은 활용률로 함께 돌리는 것 자체가 만만치 않다. 최근 연구가 별도 draft 모델보다 셀프 드래프팅과 n-gram으로 기우는 이유다
- **정적 K는 수요 변화를 못 따라간다.** 워크로드가 출렁이면 고정 K가 최적일 수 없어, 적응형(adaptive) K 연구가 활발하다 — [7.1편 정리]({% post_url 2026-08-29-Dev-LLM-Serving-Optimization-07-01-LLM-Serving-Advanced-Techniques-Overview %}#정리)에서 언급한 "정적 튜닝 대 동적 자동화" 문제의 한 사례다

요약하면 최적 시나리오는 **지연에 민감하고, ITL 개선을 위해 처리량이나 TTFT(Time To First Token, 첫 토큰까지의 시간)를 어느 정도 내줄 수 있으며, prefill 대 decode 토큰 비율이 낮고 실제 배치가 작아 memory-bound인 워크로드**다.

<br>

# 실전 사례: Kakao의 speculative decoding

이론이 실무에서 어떻게 쓰이는지는 if(kakaoAI) 2024의 발표 [빠르고 비용 효율적으로 LLM 서빙하기](https://youtu.be/mdninhUqp5o)가 좋은 참고가 된다. 발표 기준으로 Kakao는 LLM 서빙용 NVIDIA GPU를 온프레미스로 운영하며, 당시 집중하던 최적화 기술 두 가지로 양자화와 speculative decoding을 꼽는다 (양자화 쪽 내용은 6장 모델 압축 계열이라 이 글에서는 다루지 않는다).

발표에서 눈에 띄는 것은 draft 크기에 대한 실험이다. OPT 계열로 target 6.7B에 draft 125M과 350M을 붙여 비교했는데, 장표의 평가 표 기준으로 두 draft의 벤치마크 점수는 대부분 항목에서 target에 한참 못 미친다(HellaSwag 31.5·36.7 대 68.7) — 그런데도 발표의 결론은 "모델이 충분히 작아도 되더라, evaluation 성능이 높지 않아도 된다"이다.

![Kakao의 OPT draft 크기 실험]({{site.url}}/assets/images/llmso-ifkakao-speculative-decoding-result-1.png){: .align-center width="720"}

<center><sup>출처: if(kakaoAI) 2024 '빠르고 비용 효율적으로 LLM 서빙하기' 발표 영상</sup></center>

측정 결과는 앞에서 정리한 원리로 그대로 읽힌다. greedy decoding·ShareGPT 데이터셋 기준으로 **수락률(발표 표기는 채택률)은 350M이 근소하게 높지만(K에 따라 0.81~0.88, 125M은 0.77~0.87) 속도는 오히려 더 작은 125M 쪽이 높았다.** 속도를 정하는 변수는 수락률 하나가 아니라 둘이다 — **수락이 만들어 내는 토큰 수와, draft를 돌리는 데 드는 비용**. 125M은 350M보다 수락률이 근소하게 낮지만 draft 비용은 절반 이하라, 비용 감소 폭이 수락률 하락의 손실보다 크다. 결과적으로 오히려 더 작은 모델의 속도가 높게 나타난다. 품질은 검증이 보장해 주기 때문에, draft에게 필요한 능력은 벤치마크 점수가 아니라 "다음에 올 쉬운 토큰"을 맞히는 것뿐이다.

![Kakao의 OPT draft 실험 측정 결과]({{site.url}}/assets/images/llmso-ifkakao-speculative-decoding-result-2.png){: .align-center width="720"}

<center><sup>출처: if(kakaoAI) 2024 '빠르고 비용 효율적으로 LLM 서빙하기' 발표 영상</sup></center>

이 장표에는 앞서 본 명제 두 개가 더 들어 있다. 표에서 수락률은 K가 3에서 6으로 커질수록 떨어지고(125M 기준 0.867 → 0.773 — [위치별 수락률](#draft-토큰-개수-k)이 뒤로 갈수록 낮아지는 그 현상이다), 그래프에서 speedup은 동시 클라이언트 수가 1에서 32로 늘수록 2.3배대에서 1배 근처로 줄어든다 — [배치가 차면 이득이 사라진다](#효과가-사라지는-조건)의 프로덕션 실측판이다.

자사 Kanana 모델 적용 실험에서는 target의 약 1/10 크기 draft — 그것도 pretraining 중간 체크포인트에 instruct 튜닝 전 상태 — 로 수락률 0.6~0.8(greedy decoding·ShareGPT 기준)을 얻었고, 한국어 챗 데이터셋에서는 수락률이 0.84~0.91로 더 올라가며 속도 개선 폭도 커졌다고 소개한다.

![Kanana 모델 적용 결과]({{site.url}}/assets/images/llmso-ifkakao-speculative-decoding-result-4-kanana-greedy-decoding.png){: .align-center width="720"}

<center><sup>출처: if(kakaoAI) 2024 '빠르고 비용 효율적으로 LLM 서빙하기' 발표 영상</sup></center>

![Kanana 한국어 챗 데이터셋 적용 결과]({{site.url}}/assets/images/llmso-ifkakao-speculative-decoding-result-5-greedy-decoding-korean-dataset.png){: .align-center width="720"}

<center><sup>출처: if(kakaoAI) 2024 '빠르고 비용 효율적으로 LLM 서빙하기' 발표 영상. 한국어 챗 데이터셋에서 K별 수락률 0.843~0.907</sup></center>

남은 과제로 꼽는 것도 같은 원리의 연장선에 있다: draft를 target의 1/50 수준까지 줄이는 것(pruning·distillation), instruction tuning으로 수락률을 올리는 것. **실무의 중심 과제는 알고리즘이 아니라 좋은 draft의 확보**라는 것이 사례가 주는 요점이다.

<br>

# 정리

- decode의 "한 스텝에 토큰 하나"는 자기회귀 제약의 결과이고, speculative decoding은 추측(draft K개)과 병렬 검증(target forward 1회)으로 이를 우회해 가중치 읽기 1회당 최대 K+1개 토큰을 확정한다
- rejection sampling 검증 — p ≥ q면 수락, 아니면 p/q 확률 수락, 거부 시 잔여 분포 재샘플링 — 이 출력 분포를 target과 동일하게 보존한다. draft의 품질은 속도(수락률)에만 영향을 준다
- draft 선택지는 소형 모델, 증류, 셀프 드래프팅(Medusa·EAGLE), n-gram 넷이고, n-gram이 첫 시도, EAGLE 계열이 성능 상한이다
- K는 2~4에서 시작해 위치별 수락률을 보며 조정한다. 이득의 전제는 memory-bound·저배치이고, 이 전제가 깨지면 처리량 손해로 부호가 바뀐다

다음 [7.2.2편]({% post_url 2026-08-29-Dev-LLM-Serving-Optimization-07-02-02-Speculative-Decoding-Hands-On %})에서는 vLLM에서 vanilla, n-gram 두 종, EAGLE-3 네 가지 변형을 실제로 돌려, 동시성 1과 16에서 이 글의 명제들 — 특히 배치가 차면 이득의 부호가 바뀐다는 것, 그리고 수락은 최댓값이 아니라 일관성이 결정한다는 것 — 을 실측으로 확인한다.

<br>

# 참고 링크

- [Hands-On LLM Serving and Optimization (O'Reilly)](https://www.oreilly.com/library/view/hands-on-llm-serving/9798341621480/)
- [Fast Inference from Transformers via Speculative Decoding (arXiv 2211.17192)](https://arxiv.org/abs/2211.17192)
- [Accelerating Large Language Model Decoding with Speculative Sampling (arXiv 2302.01318)](https://arxiv.org/abs/2302.01318)
- [Medusa: Simple LLM Inference Acceleration Framework (arXiv 2401.10774)](https://arxiv.org/abs/2401.10774)
- [EAGLE: Speculative Sampling Requires Rethinking Feature Uncertainty (arXiv 2401.15077)](https://arxiv.org/abs/2401.15077)
- [EAGLE-3: Scaling up Inference Acceleration of Large Language Models via Training-Time Test (arXiv 2503.01840)](https://arxiv.org/abs/2503.01840)
- [vLLM Speculative Decoding 문서](https://docs.vllm.ai/en/latest/features/spec_decode.html)
- [The Engineering Behind LLM Inference: Speculative Decoding and Long Context (YouTube)](https://www.youtube.com/watch?v=jLDyJqAOrmQ)
- [if(kakaoAI) 2024 — 빠르고 비용 효율적으로 LLM 서빙하기](https://youtu.be/mdninhUqp5o)
- [7.1편: 고급 최적화 기법 개요]({% post_url 2026-08-29-Dev-LLM-Serving-Optimization-07-01-LLM-Serving-Advanced-Techniques-Overview %})

<br>
