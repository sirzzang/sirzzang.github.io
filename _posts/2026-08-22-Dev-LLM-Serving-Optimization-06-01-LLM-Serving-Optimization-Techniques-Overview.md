---
title: "[LLM] LLM 서빙과 최적화: 서빙 최적화 기법 - 6.1. 개요: iteration에서 continuous batching까지"
excerpt: "서빙 최적화 기법의 출발점인 배칭의 큰 흐름을 실행 단위, 동기, 구조, 재구성 시점 순으로 잡아 보자."
categories:
  - Dev
toc: true
header:
  teaser: /assets/images/blog-Dev.jpg
tags:
  - LLM-Serving
  - Batching
  - Continuous-Batching
  - Prefill-Decode
  - Iteration-Level-Scheduling
  - vLLM
  - Hands-On-LLM-Serving-and-Optimization-Study
  - Hands-On-LLM-Serving-and-Optimization-Study-Week-3
last_modified_at: 2026-08-27
---

*[서종호(가시다)](https://www.linkedin.com/in/gasida99/)님의 Hands-On LLM Serving and Optimization Study (LLMSO) 3주차 학습 내용을 기반으로 합니다.*

<br>

# TL;DR

- 6장의 기법들은 산술 강도(FLOPs/byte)라는 분수 하나를 서로 다른 항에서 공략한다: 분자를 키우는 배칭·스케줄링, 분모를 줄이는 어텐션 최적화·모델 압축, 계산 자체를 피하는 프리픽스 캐싱
- 서빙 엔진의 실행 단위는 요청이 아니라 모델 forward 1회, 즉 iteration이다. forward는 원자적이라 스케줄러(CPU)가 개입할 수 있는 지점은 iteration 경계뿐이다
- 배칭의 이득은 **한 번 읽은 가중치를 여러 요청이 나눠 쓰는 데서** 온다. memory-bound인 decode에서는 스텝 시간이 거의 그대로인 채 처리량이 배치 크기만큼 늘어난다. 단, 배칭이 상각하는 것은 공유되는 가중치 읽기뿐이고, 요청마다 따로 쌓이는 KV cache 읽기는 줄지 않는다
- prefill은 `[B, 1000, H]`처럼 넓은 텐서, decode는 `[B, 1, H]`의 좁은 텐서다. prefill 배치는 길이 차이(패딩), decode 배치는 종료 시점 분산이라는 문제를 남긴다
- static·dynamic·continuous 배칭 모두 텐서 쌓기는 같다. 차이는 배치 멤버십을 다시 정하는 시점 하나다: 배치 전체가 끝난 뒤 vs 매 iteration
- continuous batching에서는 prefill과 decode가 같은 스텝에서 만나면서 새로운 문제가 생긴다. 섞지 않으면 진행 중인 decode가 멎고, 섞어도 긴 prefill이 스텝 길이를 지배한다. chunked prefill·selective batching·KV cache 관리가 여기서 출발한다

<br>

# 전제: 지금까지 만든 서빙 시스템

6장은 continuous batching을 비롯한 서빙 최적화 기법들을 다룬다. 기법 하나하나로 들어가기 전에, 이 글에서 전체를 관통하는 흐름을 먼저 잡는다.

개인적으로 이해하는 데 도움이 되었던 **단위 → 동기 → 구조 → 시점**의 순서를 이용해 보고자 한다. 실행의 단위가 무엇인지, 그 단위에 여러 요청을 넣는 게 왜 이득인지, 넣으면 어떤 모양이 되는지, 그 구성을 언제 다시 정하는지 순서로 따라가다 보면, 각 항목이 남기는 질문이 다음 항목의 출발점이 된다는 것을 알 수 있다.

그 출발점을 놓기 위해 지금까지 내용부터 복기해 보자.

## 요청 단위 실행 모델

[2편]({% post_url 2026-08-14-Dev-LLM-Serving-Optimization-02-LLM-Serving-From-Scratch-Structure %})에서 해부한 단일 모델 서빙 시스템은 API server가 요청을 받아 큐에 넣고, WorkloadManager가 배치 상한만큼 묶어 내주면, 별도 프로세스의 워커가 `generate()`를 호출해 완성된 텍스트를 돌려주는 구조였다. [3.1편]({% post_url 2026-08-14-Dev-LLM-Serving-Optimization-03-01-LLM-Serving-From-Scratch-Basic-Request %})에서 한 번에 한 요청씩 처리할 때의 낮은 처리량을 재현했고, [3.2편]({% post_url 2026-08-14-Dev-LLM-Serving-Optimization-03-02-LLM-Serving-From-Scratch-Batch-Request %})에서 정적 배칭으로 처리량이 약 2배가 되는 것과 그 한계를 측정했다.

이 시스템에서 실행의 단위는 **요청**(정확히는 요청 묶음)이었다. `generate()` 호출이 한 번 시작되면 끝날 때까지 블랙박스다. 큐잉·프로세스 분리·IPC 같은 시스템 바깥 구조는 그대로 두고, 6장의 시선은 그 블랙박스 안쪽 — GPU가 실제로 도는 루프 — 으로 내려간다. 실서비스 엔진은 요청이 끊임없이 유입되는 **온라인** 상황에서 돌고, 일반적으로 생성 중간중간 토큰을 곧바로 내보내는 **스트리밍** 형태의 응답을 내놓는다. 이후의 배칭 논의는 이 온라인·토큰 단위 관점을 전제한다.

## 병목의 언어: 산술 강도와 roofline

병목을 판정하는 도구는 [5.4편]({% post_url 2026-08-22-Dev-LLM-Serving-Optimization-05-04-LLM-Serving-Challenge-Loading-Execution-Bottleneck %})과 [roofline 실측 글]({% post_url 2026-08-21-Dev-Roofline-Model-LLM-Serving %})에서 정리했다. 산술 강도(연산 강도, FLOPs/byte)가 ridge point보다 낮으면 memory-bound, 높으면 compute-bound이고, LLM 추론에서 prefill은 compute-bound 쪽에, decode는 memory-bound 쪽에 찍힌다 (이 글의 memory-bound는 전부 메모리 용량이 아니라 대역폭의 병목, 즉 [5.4편]({% post_url 2026-08-22-Dev-LLM-Serving-Optimization-05-04-LLM-Serving-Challenge-Loading-Execution-Bottleneck %})의 memory bandwidth-bound를 가리킨다).

5장 전체를 관통하는 요점은 결국 한 문장으로 모인다. decode는 토큰 하나를 만들려고 가중치 전체를 HBM에서 훑는다. 만들 토큰이 하나뿐이니 FLOPs는 작은데 그 계산을 위해 메모리에서 옮기는 바이트는 최대치라, 산술 강도의 분수는 바닥이고 GPU 연산 유닛은 논다. **하드웨어가 부족한 게 아니라, 하드웨어에 일을 못 먹이고 있는 것이다.**

## 6장의 지도: 하나의 분수, 세 방향의 공략

6장의 모든 기법은 결국 "바이트 하나를 옮길 때 최대한 많은 토큰을 뽑아내라"는 하나의 명령을 서로 다른 층위에서 실행한 것이다. 그 명령을 분수로 쓰면 5장에서 정리한 산술 강도 그대로다.

$$
\text{산술 강도} = \frac{\text{FLOPs (수행한 계산)}}{\text{bytes (이동한 데이터)}}
$$

이 분수를 기준으로 놓고 보면, 산술 강도를 증가시키기 위한 공략 방향은 원리적으로 셋이다.

| 방향 | 무엇을 하는가 | 6장의 기법 |
|------|--------------|-----------|
| ① 분자(FLOPs)를 키운다 | 같은 한 번의 읽기로 더 많은 일을 시킨다 | 배칭·스케줄링 (static → dynamic → continuous → chunked prefill) |
| ② 분모(bytes)를 줄인다 | 옮겨야 할 바이트 자체를 줄인다 | 어텐션 최적화 (GQA/MLA, FlashAttention), 모델 압축 (양자화) |
| ③ 아예 안 한다 | 이미 한 계산을 다시 하지 않는다 | 프리픽스 캐싱 (RadixAttention, cache-aware routing) |

하나의 분수를 각자 다른 항에서 공략하는 체계다. 한 가지, 6장의 대표 기법인 PagedAttention은 이 분수의 어느 항도 직접 건드리지 않는다 — KV cache 메모리의 단편화 낭비를 회수해 같은 용량으로 더 큰 배치(①)를 가능하게 하는 기반 기법이라, 지도에서는 별도 자리로 둔다. 이 글은 그중 첫 번째 축 — 배칭 — 을 따라 continuous batching까지의 큰 흐름만 잡고, 거기서 드러나는 새 문제들을 확인하는 데서 멈춘다. 나머지 축의 기법들은 이후 글에서 하나씩 다룬다.

<br>

# 실행 단위: iteration

첫 번째 질문은 단위다. 지금까지의 서빙 시스템은 요청을 실행 단위로 삼았다 — 이 단위가 어떤 문제를 만드는지, 무엇으로 바꿔야 하는지부터 보자.

## 요청 단위의 문제

자기회귀 생성의 구조는 [3.3편]({% post_url 2026-08-14-Dev-LLM-Serving-Optimization-03-03-LLM-Serving-Prefill-Decode %})에서 정리했다. 요청 하나는 프롬프트 전체를 한 번에 처리하는 prefill 1회와, 토큰을 하나씩 이어 붙이는 decode의 반복으로 이루어진다. 토큰 N개를 생성하면 모델 forward가 N회 돈다.

전통적인 ML 서빙에서는 이 구분이 필요 없었다. 요청 1개 = forward 1회 = 응답 1회라서 "요청"과 "실행 스텝"이 같은 말이었고, 그 안을 더 쪼개서 부를 단어 자체가 필요 없었다. 그런데 LLM 서빙에서는 하나의 요청이 토큰 N개를 생성하면서 이 등식이 요청 1개 = forward N회로 바뀐다. 여기에 와서야 처음으로 두 개념이 분리됐고, 비로소 그 스텝을 가리킬 이름이 필요해진 것이다. 그렇게 자리 잡은 용어가 **iteration**(또는 step)이다 — 모델 전체를 처음부터 끝까지 한 번 통과시키는 forward pass 1회를 가리킨다.

요청 단위로 스케줄링하면 이 forward N회짜리 반복이 통째로 하나의 작업 덩어리가 된다. 반복이 도는 동안 스케줄러가 끼어들어 내릴 수 있는 결정이 없다 — 새 요청을 넣을지, 먼저 끝난 요청을 뺄지는 실행 중인 묶음이 전부 끝난 뒤에야 정할 수 있다. 그래서 긴 생성 하나가 GPU를 붙잡고 있는 동안 짧은 요청은 큐에서 기다린다. [3.2편]({% post_url 2026-08-14-Dev-LLM-Serving-Optimization-03-02-LLM-Serving-From-Scratch-Batch-Request %})에서 관찰한 대기 지연 — 실행 중인 배치가 통째로 끝나야 대기 중인 요청이 실행되던 현상 — 이 정확히 이 구조에서 온 문제였다.

## 토큰 1개 생성 스텝이라는 통칭

방금 iteration을 forward pass 1회로 정의했지만, 실무에서는 흔히 "iteration = 토큰 1개 생성 스텝"이라고도 말한다. 토큰을 하나씩 만드는 단계는 decode니, 언뜻 decode에 대한 말로 들린다. 그러나 이 등식은 decode만의 것이 아니다 — [3.3편에서 정리했듯]({% post_url 2026-08-14-Dev-LLM-Serving-Optimization-03-03-LLM-Serving-Prefill-Decode %}#경계-첫-토큰) prefill의 forward도 마지막 위치에서 새 토큰 1개를 내놓고, 그 토큰이 곧 TTFT(Time To First Token, [3.3편의 서빙 지표]({% post_url 2026-08-14-Dev-LLM-Serving-Optimization-03-03-LLM-Serving-Prefill-Decode %}#서빙-지표-ttft와-tpot) 참고)의 첫 토큰이다. 둘이 갈리는 지점은 나온 토큰 수가 아니라, 그 1개를 만들기 위해 **한 번의 forward 안에서 계산한 위치의 수**다.

| 구분 | 계산한 위치 수 | 나온 새 토큰 |
|------|--------------|-------------|
| prefill (프롬프트 1000토큰) | 1000 | 1 |
| decode | 1 | 1 |

그럼에도 이 등식은 대개 decode의 표현으로 통용된다. 이유는 방금 본 스텝 하나의 크기가 아니라 **스텝의 횟수**에 있다. 요청 하나의 생애에서 prefill iteration은 1회뿐이고 decode iteration은 나머지 토큰 수만큼(N−1회) 반복되니, 엔진이 도는 iteration의 대부분은 토큰 1개를 만드는 decode 스텝이다. 물론 "forward 1회 = 새 토큰 1개"가 항상 지켜지는 등식도 아니다. prefill을 여러 스텝에 나눠 실으면 새 토큰 없이 끝나는 iteration도 생기는데, 이 예외는 [후술](#남는-질문-6장의-나머지)하는 기법에서 등장한다.

## 엔진 루프의 한 스텝

그럼 이 iteration이 엔진 안에서 실제로 어떻게 도는지 보자. LLM 서빙 엔진이 GPU에 일을 시키는 방법은 하나뿐이다 — 입력 텐서를 만들어서 모델 전체를 한 번 통과시키고 출력을 받는 것, 즉 iteration 한 번이다. 엔진의 실체는 이 스텝을 도는 무한 루프고, vLLM 코드에서는 실제로 `engine.step()`이다 (버전에 따라 클래스 이름이나 경로는 바뀔 수 있다).

```python
# 엔진 바깥의 루프
while engine.has_unfinished_requests():
    request_outputs = engine.step()

# step() 내부 (개념적으로)
def step(self):
    scheduler_output = self.scheduler.schedule()   # CPU. 이번 forward에 태울 요청 결정
    model_output = self.model_executor.execute_model(scheduler_output)  # GPU
    return self.scheduler.update_from_output(model_output)  # CPU. EOS 판정, 슬롯 회수
```

이 루프는 특정 요청의 것이 아니라 엔진의 것이다. 요청 하나의 눈으로 보면 이 루프에서 자기 몫은 prefill iteration 1회와 decode iteration N−1회지만, 루프 자체는 요청들이 들어오고 나가는 동안 멈추지 않고 돈다. 각 스텝에 어느 요청의 어떤 작업을 실을지는 아직 정하지 않았다.

## 스케줄러의 위치: CPU와 GPU의 분업

그렇다면 이번 forward에서 처리할 요청을 정하는 일 — 위 코드의 `schedule()` — 은 누가 하는가.

GPU는 아니다. 판단할 지능이 없어서가 아니라 구조가 그렇다. GPU는 CPU가 큐에 넣어 준 커널을 실행하는 코프로세서(co-processor)라 스스로 다음 작업을 고르는 제어 주체가 아니고, 무엇보다 "다음에 누구를 넣을지"를 정하는 데 필요한 정보 — 요청 큐, 대기 중인 요청, 메모리 현황 — 가 전부 호스트(CPU) 쪽에 있다. 커널은 launch될 때 받은 텐서와 인자만 보고 돈다.

그래서 정책 판단은 전부 CPU 몫이고, 그 판단을 내리는 CPU 쪽 코드가 곧 서빙 엔진의 스케줄러다. [2편]({% post_url 2026-08-14-Dev-LLM-Serving-Optimization-02-LLM-Serving-From-Scratch-Structure %})에서 본 시스템의 구도 — 요청 큐와 배처는 CPU, 모델 실행만 GPU — 의 직계 연장이다.

이름이 겹쳐서 헷갈리기 쉬운데, GPU 주변에는 층위가 완전히 다른 스케줄러 셋이 있다. 6장에서 말하는 스케줄러는 첫 번째이다.

| 스케줄러 | 무엇을 정하나 | 어디서 | 시간 스케일 |
|---------|--------------|--------|------------|
| ① 서빙 스케줄러 | 이번 forward에 어느 요청을 넣을까 | CPU (엔진 코드) | ms |
| ② GPU 드라이버/스트림 | 큐에 쌓인 커널을 어느 순서로 | CPU 드라이버 + GPU 커맨드 프로세서 | µs |
| ③ warp 스케줄러 | SM 안에서 어느 warp를 이번 사이클에 | GPU 하드웨어 | ns |

## 원자성과 스케줄링 단위

그런데 이 CPU 스케줄러가 아무 때나 끼어들 수 있는 것은 아니다. forward는 **원자적(atomic)**이다. 한 번 GPU에 던지면 중간에 끼어들 수도, 일부만 빼낼 수도 없고, forward가 끝나야 CPU가 다시 개입할 수 있다.

> 참고: 이 원자성을 DB 트랜잭션에 비유하면 all-or-nothing과 중간 상태 관찰 불가라는 점에서는 같지만 롤백이 없다는 점에서 다른, 일종의 "롤백 없는 원자적 커밋"이라고 이해할 수 있다. 클라이언트가 연결을 끊어도 이미 launch된 스텝은 끝까지 돌고, 그 요청은 다음 스케줄에서 빠질 뿐이다. 실행 중인 요청을 미루는 preemption류의 동작도 iteration 도중 중단이 아니라 다음 iteration에서 제외하는 방식으로 일어난다.

그래서 **스케줄링 단위**라는 말이 나온다. 스케줄러가 개입할 수 있는 지점은 오직 **iteration 경계뿐이고**, 그 경계에서 다음 forward에 무엇을 넣어서 처리할지 정하는 것이다.

```python
CPU: schedule() → 텐서 조립 → 커널들을 GPU 큐에 enqueue (비동기, 바로 리턴)
GPU:                          ... 실제 실행 ...
CPU: 결과 동기화 → EOS 판정 → 슬롯 회수 → 다시 schedule()
     # 여기가 iteration 경계. 개입할 수 있는 유일한 틈
```

단위를 iteration으로 잘게 쪼개면 얻는 것은 **결정 지점의 수**다. 요청 단위에서는 스케줄링 결정의 기회가 요청 묶음당 1회지만, iteration 단위에서는 forward마다 돌아온다. 이 결정 기회를 실제로 언제 쓰는지는 [배칭 방식](#배칭-방식-배치를-다시-짜는-시점)에서 갈린다 — 여기서는 단위만 바꿔 두었다.

<br>

# 배칭: 한 번 읽은 가중치로 여러 요청

실행 단위는 iteration으로 잡았다. 다음 질문은 하나다 — 그 한 스텝에 무엇을 넣나.

## 처리량 이득의 원리

hidden size 4096, 가중치 14GB인 모델에서 요청 하나를 decode하는 상황을 보자. 아래 shape은 행렬 곱에 들어가는 2차원 모양(행 × hidden)으로 **단순화해** 적은 것이다 — 입력 텐서의 정확한 축 구조는 [배치의 구조](#세-축으로-읽는-입력-텐서)에서 후술한다.

```bash
입력  [1, 4096]   # 요청 1개, 토큰 1개
가중치 W: 14GB 전체를 HBM에서 읽어 옴
출력  [1, 4096]   # 토큰 1개
```

decode 한 스텝의 forward는 모든 레이어의 attention projection과 FFN 가중치, 그리고 lm_head까지 전부 읽는다 — 입력 embedding만 lookup이라 해당 토큰의 행만 읽는다. 그 총합이 14GB다. 연산량은 이에 비해 매우 작고, 시간 대부분을 메모리에서 가중치를 퍼 오는 데 쓴다 — memory-bound다.

여기서 요청 3개를 배칭해 보자.

```bash
입력  [3, 4096]   # 요청 3개, 각각 토큰 1개
가중치 W: 14GB ... 똑같이 한 번만 읽음
출력  [3, 4096]   # 토큰 3개
```

행렬 곱셈은 `[3, 4096] × [4096, 4096]`으로 왼쪽 행렬의 행이 3개가 된 것뿐이고, 가중치 읽기는 그대로다. 3개 요청 모두 같은 가중치를 곱하기 때문에 가중치를 3번 읽을 필요가 없다.

| 구분 | 요청 1개씩 3번 | 3개 배칭해서 1번 |
|------|---------------|-----------------|
| 가중치 읽기 | 14GB × 3 = 42GB | 14GB |
| 생성 토큰 | 3 | 3 |
| FLOPs | 3배 | 3배 (같음) |
| 산술 강도 (FLOPs/byte) | 기준 | 3배 |

같은 계산량에 바이트 이동이 1/3이니 산술 강도가 3배다. "배칭이 산술 강도를 인위적으로 올린다"는 말의 문자 그대로의 의미가 이것이고, roofline 위에서는 memory-bound 사선 구간의 점이 오른쪽으로 이동하는 것으로 나타난다. [roofline 실측 글]({% post_url 2026-08-21-Dev-Roofline-Model-LLM-Serving %})에서 배치를 실어 찍은 점들이 실제로 오른쪽으로 움직이는 것을 확인했다 (다만 실측 대상이 MoE 모델이라 이동 폭은 B에 비례하는 이상치에 못 미쳤다). 

이 이득을 처리량의 식으로 옮기면 다음과 같다.

```python
throughput = (스텝당 산출 토큰) / (스텝 시간)
#              ↑ B배로 늘어남     ↑ memory-bound 구간에선 거의 그대로
# → 거의 B배
```

돌아보면 이 구조 — 한 번 치른 읽기 비용을 여러 토큰이 나눠 부담하는 상각(amortization) — 는 prefill이 이미 쓰고 있던 수법이다. [3.3편]({% post_url 2026-08-14-Dev-LLM-Serving-Optimization-03-03-LLM-Serving-Prefill-Decode %}#같은-flops-다른-병목)의 표현으로 prefill은 **가중치를 한 번 읽어 프롬프트 토큰 전체에 쓰는 단계**였다 — 한 요청 안에서 토큰 축으로 상각한 것이다. decode는 자기회귀 때문에 그 축을 늘릴 수 없다. 그러니 배칭은 같은 상각 구조를 남은 축인 요청(B)에서 재현하는 것이다. 토큰이 어느 축에서 오든, 가중치 읽기 한 번을 나눠 쓰는 토큰 수가 늘어나는 만큼 산술 강도가 오른다.

> 참고: 정확히 하면 decode 한 스텝의 HBM 읽기는 가중치 항 하나가 아니라 가중치 항 + [KV cache]({% post_url 2026-08-14-Dev-LLM-Serving-Optimization-03-03-LLM-Serving-Prefill-Decode %}#kv-cache-두-단계의-연결) 항의 합이다. 배칭이 상각하는 것은 모든 요청이 **공유**하는 가중치 항뿐이고, 요청마다 따로 쌓이는 KV cache 항은 배칭으로 줄지 않는다 — 오히려 배치를 키우는 만큼 늘어난다. 위 계산은 가중치 항이 지배하는 구간의 이야기이고, 미뤄 둔 이 항은 [남는 질문](#남는-질문-6장의-나머지)에서 다시 만난다.

## 선택으로서의 배칭과 지연의 거래

그런데 이렇게 배치로 같이 처리해야 한다는 법이 있는 건 아니다. [3.3편]({% post_url 2026-08-14-Dev-LLM-Serving-Optimization-03-03-LLM-Serving-Prefill-Decode %})에서 prefill의 병렬 처리를 두고 강제가 아니라 "가능해서 하는" 선택이라고 정리한 것과 같은 구도다. 요청 3개를 따로따로 3번 forward 돌려도 결과는 같다 — 가중치를 3번 읽을 뿐이다. 배칭은 법이 아니라 **선택**이고, 그 선택의 동기는 "가중치를 한 번만 읽는다"다.

선택의 대가는 지연시간이다. 큐잉 이론(queueing theory)의 기본 분해를 빌리면, 어느 시스템에서든 요청 하나가 겪는 지연(latency)은 두 항의 합이다.

$$
\text{latency} = \text{queueing time (대기 시간)} + \text{service time (서비스 시간)}
$$

"여러 요청을 같은 텐서에 쌓아서 한 forward에 넣는다"는 배칭의 정의만으로 이 두 항이 모두 영향을 받는다.

- **대기 시간**: 혼자면 도착 즉시 출발할 수 있었는데, 같은 텐서에 쌓으려면 누구와 쌓을지가 먼저 확정돼야 한다. 같이 탈 요청이 정해질 때까지 기다리는 시간이 이 항에 더해진다
- **서비스 시간**: 텐서의 행이 B개가 되니 한 스텝이 짊어지는 일의 양이 B배가 된다. 일이 B배면 스텝 시간도 늘어날 수 있다 — 실제로 얼마나 늘어나는지는 워크로드의 병목에 달렸다

여기까지는 LLM이 아니어도, 어떤 시스템의 배칭이든 성립하는 일반론이다. 

LLM decode에 오면 두 번째 항의 사정이 특별해진다.

- **배치가 작을 때 — memory-bound 구간**: decode는 스텝 시간의 대부분이 계산이 아니라 가중치 읽기인데, 가중치 읽기는 행이 1개든 B개든 한 번이다. 일의 양이 B배가 되어도 스텝 시간은 거의 변하지 않는다 — 서비스 시간 증가가 거의 0인, 배칭의 이득이 사실상 추가 비용 없이 나오는 구간이다
- **배치를 계속 키우면 — compute-bound 전환**: [처리량 이득의 원리](#처리량-이득의-원리)에서 본 대로 배치를 키우는 것은 곧 산술 강도를 올리는 것이라, 읽기는 그대로인데 계산만 B배로 쌓이다 어느 순간 ridge point를 넘는다. 그때부터는 병목이 읽기에서 계산으로 바뀌어 스텝 시간이 배치 크기에 비례해 늘고, KV cache 메모리 압박도 커진다

그래서 배치 크기와 처리량의 곡선에는 무릎(knee)이 있고, 서빙 엔진들이 배치 상한 파라미터(vLLM의 `max_num_seqs` 등)를 두는 이유가 이것이다. 참고로 이 값을 1로 두면 배치 차원을 1로 강제해 배칭이 무력화된다.

정리하면, 배칭은 요청 하나의 지표(지연)를 내주고 시스템의 지표(처리량)를 사는 거래다 — 내 완료 시각이 남의 요청 상태에 종속되는 대신, 같은 시간에 시스템이 처리하는 토큰이 늘어난다. 이 거래의 대가가 대기 항과 서비스 항 중 어디에 얼마나 실리는지는 배칭 방식마다 다른데, [배칭 방식](#배칭-방식-배치를-다시-짜는-시점)에서 다시 본다.

<br>

# 배치의 구조: prefill과 decode

배칭의 동기까지 확인했다. 그런데 iteration에 넣을 작업들이 전부 같은 모양은 아니다 — 이번에는 그 작업들이 텐서로 어떻게 쌓이는지, 그 모양이 어떤 문제를 남기는지 본다.

## 세 축으로 읽는 입력 텐서

prefill과 decode의 개념과 기원은 [3.3편]({% post_url 2026-08-14-Dev-LLM-Serving-Optimization-03-03-LLM-Serving-Prefill-Decode %})에서 정리했다. 여기서는 배칭에 필요한 관점 하나만 얹는다 — 두 단계는 forward에 들어가는 **텐서의 모양**이 다르다. 입력 텐서 `[B, S, H]`에서 원소 하나는 "b번째 요청의, s번째 토큰의, h번째 특징값"이다 — [5.4편]({% post_url 2026-08-22-Dev-LLM-Serving-Optimization-05-04-LLM-Serving-Challenge-Loading-Execution-Bottleneck %})에서 산술 강도를 계산할 때 쓴 그 shape다.

| 축 | 이름 | 뜻 | 예시 값 |
|----|------|-----|--------|
| B | batch | 이번 forward의 요청 개수 | 3 |
| S | sequence | 요청당 이번 forward에서 계산할 토큰 수 | prefill 1000 / decode 1 |
| H | hidden | 토큰 1개를 표현하는 벡터 길이 (모델 상수) | 4096 |

앞서 [배칭](#처리량-이득의-원리)에서 쓴 `[1, 4096]`·`[3, 4096]`은 이 표기로 각각 `[1, 1, 4096]`·`[3, 1, 4096]`이다 — decode는 S=1이라 그 축을 접고, 행렬 곱에 들어가는 2차원 모양으로 적은 것이었다. 두 단계의 차이는 S 축에 몇 개가 들어가는가다.

```bash
Prefill (프롬프트 1000토큰):
  입력 [1, 1000, 4096]  # 1000개 토큰을 한 forward에 전부

Decode (그 다음부터):
  입력 [1, 1, 4096]     # 매 forward마다 딱 1개
  입력 [1, 1, 4096]
  ...
```

여기에 배치까지 얹어(B=3) 그림으로 보면, 두 단계의 텐서는 S 축의 폭만 다른 같은 구조다.

![B=3일 때 prefill과 decode의 입력 텐서 shape 비교]({{site.url}}/assets/images/llmso-ch06-input-tensor-shapes.svg){: .align-center}

<center><sup>AI를 이용해 직접 그린 도식. prefill은 요청마다 프롬프트 전체(S=1000)가, decode는 직전 생성 토큰 1개(S=1)가 실린다 — B와 H는 같고 S만 다르다</sup></center>

prefill이 1000개를 한 번에 넣을 수 있는 이유는 프롬프트 토큰을 이미 다 알고 있고, causal mask 덕분에 동시에 넣어도 각 토큰이 자기 앞만 보기 때문이다. decode가 1개씩인 이유는 다음 토큰을 모르기 때문이다 — 501번째 토큰을 계산하려면 500번째 결과가 있어야 하는 자기회귀 구조라 원리적으로 병렬화가 안 된다.

> 참고: 서빙 엔진의 튜닝 파라미터가 정확히 이 두 축을 제한한다. vLLM 기준으로 `--max-num-seqs`는 B(이번 forward의 요청 개수), `--max-num-batched-tokens`는 이번 forward에 넣는 토큰 총수(요청별 S의 합)의 상한이다.

## prefill 배치: 길이가 다른 시퀀스와 패딩

여러 요청이 "다 같이 prefill한다"는 말의 정확한 의미는 물리적으로 **같은 forward pass 안에 들어간다**는 것이다. 시각이 같다는 뜻이 아니라 스케줄러가 그것들을 하나의 실행 단위로 묶었다는 뜻이고, forward 1회를 이루는 수백 개의 커널 호출(레이어마다 QKV projection, attention, FFN 등) 각각이 요청들을 하나의 텐서로 함께 받는다는 뜻이다. 요청들은 같은 텐서의 서로 다른 행이 되고, 결과는 iteration이 끝날 때 함께 나온다.

문제는 길이가 다르면 그냥 쌓을 수 없다는 것이다. 텐서는 직사각형이어야 한다. 이 문제를 해결하기 위한 가장 전통적 해법이 패딩(padding)이다.

![패딩으로 직사각형 텐서 만들기]({{site.url}}/assets/images/llmso-ch06-prefill-batch-padding.svg){: .align-center}

<center><sup>AI를 이용해 직접 그린 도식. 가장 긴 요청(1000토큰)에 맞춰 직사각형을 만들면 짧은 요청의 남는 칸이 전부 pad가 된다</sup></center>

pad 토큰은 mask로 결과에서 무효화되지만 메모리 자리와 연산은 그대로 소모한다. 길이 편차가 클수록 직사각형의 빈 구석, 즉 낭비가 커진다. 그래서 요즘 엔진(vLLM, FlashAttention의 varlen 커널)은 패딩 대신 토큰을 일렬로 이어 붙이고 경계만 따로 알려 주는 방식을 쓴다.

![varlen 이어붙이기]({{site.url}}/assets/images/llmso-ch06-prefill-batch-varlen.svg){: .align-center}

<center><sup>AI를 이용해 직접 그린 도식. 세 요청의 토큰을 일렬로 이어 붙이고 cu_seqlens로 경계만 표시한다 — pad가 사라진다</sup></center>

길이 차이 때문에 패딩으로 생기던 낭비는 없어지되 "같은 forward pass 안에서 처리한다"는 성질은 동일하다. 개념적으로 달라진 것은 없다.

## decode 배치: lockstep과 종료 시점

decode를 배칭하면 배치 안 요청들 사이에 시점 차이가 물리적으로 존재할 수 없다. 같은 커널 호출의 출력 텐서에서 서로 다른 행일 뿐이기 때문이다.

```bash
iteration 5:  입력 [3, 1, 4096] → GEMM(행렬 곱) → 출력 [3, 1, 4096]
# A의 5번째 토큰, B의 5번째 토큰, C의 5번째 토큰이
# 같은 행렬 곱셈의 3개 행으로 한꺼번에 나옴
```

A가 먼저 나오고 B가 0.1ms 뒤에 나오는 일은 없다. iteration 자체가 원자적이라 그 안에서는 순서라는 개념이 없다 — 발맞춰 행진하는 lockstep이다.

진짜 차이가 나는 것은 **언제 끝나는가**뿐이다.

![decode 배치의 흩어지는 종료 시점]({{site.url}}/assets/images/llmso-ch06-decode-eos-timing.svg){: .align-center}

<center><sup>AI를 이용해 직접 그린 도식. lockstep으로 함께 돌던 요청들도 EOS를 뱉는 iteration은 제각각이다</sup></center>

출력 길이는 미리 알 수 없으므로 각 요청이 EOS를 뱉는 시점은 제각각이다.

<br>

# 배칭 방식: 배치를 다시 짜는 시점

[배치의 구조](#배치의-구조-prefill과-decode) 마지막에서 본 것은 종료 시점의 분산이었다. lockstep으로 돌던 배치에서 어떤 요청이 먼저 끝나면, 그 요청이 차지하던 배치 텐서의 행은 더 계산할 것이 없어진다. 이 자리를 어떻게 할 것인가 — 배치가 통째로 끝날 때까지 빈 채로 둘 수도 있고, 곧바로 새 요청으로 채울 수도 있다.

결국 배치 구성을 다시 정하는 시점의 문제고, 이 시점에 대한 서로 다른 답이 세 가지 배칭 방식이다.

## 세 가지 방식

결론부터 말하면, 세 방식 모두 지금까지 본 텐서 쌓기를 똑같이 한다. 다른 것은 이번 forward의 텐서에 어떤 요청들이 행으로 실려 있는가 — 이 요청 집합을 **배치 멤버십**(batch membership)이라고 부르자 — 를 **언제 다시 정하느냐** 하나뿐이다.

| 방식 | 배치 확정 시점 | 멤버십이 바뀌는 시점 | 짧은 요청이 끝나면 |
|------|---------------|---------------------|-------------------|
| static | 요청 N개가 다 모이면 | 배치 전체가 끝난 뒤 | 슬롯이 빈 채로 끝까지 유지 |
| dynamic | N개 차거나 max delay 지나면 | 배치 전체가 끝난 뒤 (static과 동일) | 동일 |
| continuous | 매 스텝 | 매 iteration | 그 자리에 대기 중인 새 요청이 들어옴 |

### static batching

배치 구성을 실행 시작 전에 한 번 정하고 끝까지 유지한다. [3.2편]({% post_url 2026-08-14-Dev-LLM-Serving-Optimization-03-02-LLM-Serving-From-Scratch-Batch-Request %})에서 실습한 방식이 여기에 해당한다 — 다만 그 구현은 정원이 찰 때까지 기다리지 않고 큐에 있는 만큼(최대 4개)으로 즉시 출발하는 변형이었다. 그런데도 static으로 묶이는 이유는 출발 조건이 아니라, 한 번 출발한 배치가 통째로 끝나야 해산한다는 멤버십 고정에 있다. 그렇게 상한 4로 잘라 실행한 결과가 `ceil(N/B)` 계단으로 처리 시간에 그대로 드러났다.

![static batching: 정원이 차야 출발, 전원이 끝나야 해산]({{site.url}}/assets/images/llmso-ch06-static-batching.svg){: .align-center}

<center><sup>AI를 이용해 직접 그린 도식. 요청 셋이 모두 모여야 출발하고, 먼저 끝난 슬롯은 C가 끝나는 300번째 iteration까지 빈 채로 낭비된다</sup></center>

### dynamic batching

static과의 차이는 출발 조건뿐이다. 합승에 비유하면 정원이 다 차야 출발하는 쪽(static)과, 정원이 안 찼어도 시간이 되면 출발하는 쪽(dynamic)이다. 출발한 뒤의 동작은 완전히 동일하다 — 배치가 통째로 끝나야 해산한다.

문제는 출발한 뒤다. [위의 종료 시점 그림](#decode-배치-lockstep과-종료-시점)에서 A는 iteration 4에 끝났는데도 C가 300번째 iteration을 돌 때까지 슬롯이 빈 채로 유지된다.

![dynamic batching: 시간이 되면 미달인 채로 출발]({{site.url}}/assets/images/llmso-ch06-dynamic-batching.svg){: .align-center}

<center><sup>AI를 이용해 직접 그린 도식. max delay가 지나면 정원이 안 찼어도 출발하지만, 출발한 뒤의 낭비 구조는 static과 같다</sup></center>

배치에 묶인 요청들이 함께 끝나야 하는 구조 — 가장 오래 걸리는 요청까지 모두가 기다리는 구조다. 배치 경계를 요청 단위로 정했기 때문에 생기는 일이다.

### continuous batching

이것을 개선한 것이 continuous batching이다. 매 iteration 경계(forward 한 번이 끝날 때마다)에서 다음 forward에 넣을 텐서를 새로 조립한다. 끝난 요청은 그 스텝에서 즉시 빠지고, 큐에서 기다리던 요청은 다음 스텝에 바로 들어온다.

![continuous batching: 매 iteration 경계에서 재구성]({{site.url}}/assets/images/llmso-ch06-continuous-batching.svg){: .align-center}

<center><sup>AI를 이용해 직접 그린 도식. 먼저 끝난 슬롯이 다음 iteration에서 큐의 새 요청(prefill부터)으로 즉시 채워져 빈 슬롯이 없다</sup></center>

알고리즘적으로 대단한 것을 새로 만든 게 아니다. 스케줄러가 개입하는 단위를 요청에서 iteration으로 내린 것이고, [3.3편]({% post_url 2026-08-14-Dev-LLM-Serving-Optimization-03-03-LLM-Serving-Prefill-Decode %}#직접-만든-서빙-시스템-속의-두-단계)에서 예고한 그대로다. 위의 `engine.step()` 코드로 보면 `schedule()`이 매 루프마다 호출되는 것이 continuous batching이고, static/dynamic에서는 배치가 끝날 때까지 `schedule()`이 다시 불리지 않는 것이다. [2편]({% post_url 2026-08-14-Dev-LLM-Serving-Optimization-02-LLM-Serving-From-Scratch-Structure %})의 시스템과 비교하면 새 컴포넌트가 생긴 게 아니라 **기존 배처의 호출 주기가 요청당 1회에서 스텝당 1회로 바뀐 것**이다.

이 방식을 iteration-level scheduling이라는 이름으로 처음 정식화한 것이 [Orca(OSDI '22)](https://www.usenix.org/conference/osdi22/presentation/yu) 논문이다. 굳이 *iteration-level*이라고 부른 것은 기존 방식이 암묵적으로 *request-level*이었기 때문이고, 이후 vLLM을 비롯한 현대 서빙 엔진의 표준이 됐다.

성립 전제도 짚어 둘 만하다. iteration-level scheduling이 가능하려면 두 가지가 필요하고, 둘 다 prefill/decode 구분에서 나온다.

- 요청이 여러 iteration에 걸쳐 살아 있어야 한다 → 스텝 사이에 넘겨줄 상태(KV cache)가 있어야 하고, 그 상태를 만드는 단계(prefill)와 이어가는 단계(decode)가 갈린다. 전통 ML 서빙은 요청 = forward 1회라 넘길 상태가 없고, iteration-level scheduling이라는 말 자체가 무의미하다
- 스케줄러가 "이 요청은 이번 스텝에 몇 토큰을 기여하나"를 계산할 수 있어야 한다 → decode면 1, prefill이면 남은 프롬프트 길이다. 이 값을 모르면 스텝의 토큰 예산을 짤 수 없다

## continuous batching이 남기는 문제

[앞](#선택으로서의-배칭과-지연의-거래)에서 배칭의 지연 비용을 대기와 서비스 두 항으로 분해했는데, 방식에 따라 주범이 달라진다. continuous batching에서는 새 항이 하나 생긴다 — **남의 요청과의 간섭**이다.

| 지연 요인 | static/dynamic | continuous |
|----------|----------------|------------|
| 대기 (배치가 찰 때까지) | 주범 (static은 정원이 찰 때까지, dynamic은 최대 max delay) | 거의 없음 (다음 iteration 경계까지만) |
| 스텝 자체가 무거워짐 | 있음 | 있음 |
| 남의 요청과의 간섭 | 없음 (배치 고정) | 주범 |

이 간섭은 어디서 오는가. static/dynamic에서는 배치 안 요청들의 단계가 항상 같다 — 다 같이 출발했으니 다 같이 prefill을 하고, 그 다음부터 다 같이 decode를 한다. 단계가 섞일 일 자체가 구조적으로 없다.

![static/dynamic의 단계 정렬: 전원 같이 prefill한 뒤 전원 같이 decode한다]({{site.url}}/assets/images/llmso-non-continuous-batching-happy-path.svg){: .align-center}

<center><sup>AI를 이용해 직접 그린 도식. 요청 셋이 iteration 1에서 한 배치로 prefill을 하고, 이후 전원이 lockstep으로 decode를 반복한다 — 단계가 섞일 일이 구조적으로 없다. 그림은 생성 길이까지 같아 빈 슬롯조차 없는 이상적 경우(happy path)다</sup></center>

반면 continuous batching에서 새로 합류하는 요청은 prefill부터 시작해야 하는데, 배치에는 이미 decode 중인 요청들이 있다. [위 continuous batching 그림](#continuous-batching)에서 초록 decode 셀들 사이에 파란 prefill 셀이 끼어들던 장면이 바로 이것이다. [배치의 구조](#배치의-구조-prefill과-decode)의 용어로, S=1인 요청들 옆에 — 예컨대 긴 문서가 프롬프트로 들어와 — S=8000짜리 요청이 오는 것이다. 공교롭게도 prefill/decode 구분은 continuous batching의 성립 전제이면서 동시에 이 문제의 원천이다 — 배치를 자유롭게 재구성할 수 있는 근거가 "decode는 전부 S=1이라 아무나 같은 모양으로 쌓인다"였는데, 새로 합류하는 요청은 S=8000의 prefill이기 때문이다.


![continuous의 단계가 섞이는 세계: 스텝 길이는 prefill이 정한다]({{site.url}}/assets/images/llmso-ch06-mixed-step-length.svg){: .align-center}

<center><sup>AI를 이용해 직접 그린 도식. decode 박자로 돌던 배치(it k−1)에 새 요청 D가 끼어들면, 그 스텝(iteration k)의 길이는 S=8000 prefill이 정한다 — decode의 몫은 토큰 1개지만 prefill이 끝날 때까지 같은 스텝에 묶인다. prefill이 빠진 다음 스텝(it k+1)은 다시 decode 박자로 돌아온다</sup></center>

문제 해결에 활용할 수 있는 선택지는 둘인데, 결론부터 말하면 어느 쪽도 만족스럽지 않다. 섞지 않으면 진행 중인 decode가 멎고, 섞어도 긴 prefill이 스텝 길이를 지배한다.

### 방안 1: prefill과 decode를 함께 배칭하지 않음

prefill과 decode를 섞은 하이브리드 배치는 더 복잡한 GPU 커널이 필요하다. 그러니 우선 섞지 않는 쪽부터 보자.

![prefill을 우선하고 decode와 함께 배칭하지 않는 continuous batching]({{site.url}}/assets/images/llmso-ch06-cb-prefill-priority.svg){: .align-center}

<center><sup>출처: Hands-On LLM Serving and Optimization (O'Reilly) 그림 6-7. AI를 이용해 재구성했다</sup></center>

요청 1이 prefill(iteration 1)을 거쳐 decode(iteration 2)를 진행하던 중 요청 2·3이 도착했다. 이때 보통 prefill을 우선한다. prefill이 첫 토큰까지의 시간, 즉 TTFT를 결정하고, 챗봇 같은 대화형 서비스에서 TTFT가 중요한 지연 지표이기 때문이다.

대가는 그림의 iteration 3에 그대로 보인다. 요청 2·3의 prefill이 도는 동안 **요청 1은 완전히 유휴 상태로 멎는다.** 새 요청의 프롬프트가 길수록 이 공백이 길어지고, 요청 1의 종단 지연(end-to-end latency)과 토큰 간 지연(inter-token latency, [3.3편]의 TPOT에 해당)이 그만큼 타격을 입는다. 스트리밍으로 토큰을 받아 보던 사용자 입장에서는 잘 나오던 글자가 갑자기 멈추는 것이다.

### 방안 2: prefill과 decode를 함께 배칭

그럼 섞어 보자. 요청 1의 decode 스텝을 요청 2·3의 prefill과 같은 iteration에 넣어 함께 실행한다.

![decode와 prefill을 함께 배칭하는 continuous batching]({{site.url}}/assets/images/llmso-ch06-cb-prefill-decode-mixed.svg){: .align-center}

<center><sup>출처: Hands-On LLM Serving and Optimization (O'Reilly) 그림 6-8. AI를 이용해 재구성했다</sup></center>

그런데 "S=1과 S=8000을 한 텐서에 같이 담는다"는 게 그냥 되는 일인가? 층위를 나눠서 보자.

| 층위 | S=1과 S=8000 같이 담기 | 왜 |
|------|----------------------|-----|
| GEMM / FFN | 된다 | 토큰끼리 독립이라 8001개 행으로 이어 붙이면 된다 |
| attention | 순수 batched 커널로는 안 된다 | 요청마다 Q 길이도 참조할 KV 길이도 달라 직사각형이 안 된다 |
| 실무 관점 | 담아도 손해다 | 그 스텝의 소요 시간이 8000토큰 prefill에 지배된다 |

진짜 문제는 마지막 줄이다. 토큰 하나를 디코딩하는 것은 prefill을 끝내는 것보다 훨씬 빠르기 때문에, 한 스텝의 길이는 그 스텝에서 가장 무거운 작업 — prefill — 이 결정한다. 담을 수는 있어도, 담는 순간 decode 중이던 요청의 그 스텝이 prefill 시간만큼 늘어나 토큰 간 지연이 튄다. 그림에서 요청 2·3의 prefill이 이어지는 동안 요청 1의 decode 토큰들이 그 긴 스텝의 박자에 묶이는 것이 보인다. 입력 프롬프트가 길수록 지연은 여전히 두드러진다.

<br>

# 남는 질문: 6장의 나머지

continuous batching은 빈 슬롯 문제를 풀었지만, prefill과 decode가 한 스텝에서 만나는 새 문제를 남겼다. 두 방안 모두 만족스럽지 않다는 결론이 다음 질문들을 만든다. 이것이 6장 나머지의 지도다. 여기서는 방향만 확인하고 상세는 이후 글에서 다룬다.

## prefill 쪼개기: selective batching과 chunked prefill

방안 1과 2가 모두 만족스럽지 않았던 원인은 긴 prefill이 한 스텝에 통째로 실린다는 데 있었다. 그렇다면 prefill을 쪼갤 수는 없나 — **쪼갤 수 있다.** 쪼개는 축이 두 개 있다.

| 구분 | selective batching | chunked prefill |
|------|-------------------|-----------------|
| 무엇을 쪼개나 | 연산 종류 (GEMM은 묶고 attention은 요청별로) | 작업을 시간축으로 (prefill을 여러 iteration에 분산) |
| 층위 | 커널 / 텐서 조립 | 스케줄링 |
| 출처 | Orca (OSDI '22) | Sarathi (2023) → vLLM |
| 노리는 것 | 혼재 배치가 성립하게 만들기 | 토큰 간 지연 안정화 (대가는 TTFT) |

selective batching의 아이디어는 위 표의 첫 두 줄 대비가 전부다 — **GEMM은 행(토큰)마다 계산이 독립이라** 어느 요청의 토큰인지가 결과에 영향을 주지 않으니 전부 이어 붙여 한 번에 돌리고, **attention은 같은 요청의 KV를 참조해야 해서 요청 경계가 계산 자체에 들어가니** 요청별로 따로 돈다. chunked prefill은 긴 prefill을 한 스텝에 다 하지 않고 청크로 나눠 여러 스텝에 싣는 방식이다. 어떻게 쪼개도 결과가 같다는 성질([3.3편]({% post_url 2026-08-14-Dev-LLM-Serving-Optimization-03-03-LLM-Serving-Prefill-Decode %}#프롬프트-병렬-처리-prefill의-기원)에서 정리한 분할의 자유)이 정확성을 보장하고, 앞 청크의 KV cache가 남아 있어 다음 청크가 이어서 계산할 수 있다 — decode를 이어갈 수 있는 것과 같은 원리다. 이때 [앞](#토큰-1개-생성-스텝이라는-통칭)에서 말한 "새 토큰 없이 끝나는 iteration"(마지막이 아닌 중간 청크)이 실제로 생긴다.

## 스케줄링의 CPU 비용

**매 스텝 배치를 다시 짜는 CPU 비용도 공짜가 아니다.** 스케줄링은 CPU 몫이므로, 모델이 작아 GPU 스텝이 짧으면 CPU 스케줄링 시간이 상대적으로 커져 GPU가 CPU를 기다리는 상황이 생긴다. vLLM의 엔진 재작성(V1)이나 CUDA graph 같은 작업들이 이 CPU 구간을 줄이거나 GPU 실행 뒤로 숨기려는 시도다.

## KV cache 항

**KV cache를 절약할 수는 없을까.** decode 한 스텝의 HBM 읽기는 가중치 항과 KV cache 항의 합인데([처리량 이득의 원리](#처리량-이득의-원리)에서 미뤄 둔 항이다), 배칭이 절약하는 것은 앞 항뿐이다.

```python
decode 1스텝의 HBM 읽기 = 가중치 14GB        # 모든 요청이 공유. 배칭해도 1번
                        + KV cache (요청별)   # 요청마다 각자. 배칭하면 B배
```

배치를 키우다 보면 어느 순간 KV 읽기가 지배하기 시작하고, 그때부터는 배칭이 아니라 [6장 지도](#6장의-지도-하나의-분수-세-방향의-공략)의 두 번째 축 — 옮길 바이트를 줄이는 GQA·KV cache 양자화 — 이 답이 된다. 요청이 매 스텝 들고나는 배치에서 요청별로 자라나는 KV cache 메모리를 어떻게 관리하느냐의 문제도 여기서 함께 만나는데, PagedAttention이 다루는 단편화 낭비가 바로 그것이다.

<br>

# 정리

이 글의 흐름을 질문 사슬로 압축하면 다음과 같다.

| 순서 | 질문 | 답 | 다음 질문 |
|------|------|-----|----------|
| 단위 | 실행 단위는 무엇인가 | 요청이 아니라 forward 1회, iteration. 원자적이라 개입 지점은 경계뿐 | 그 스텝에 무엇을 넣나 |
| 동기 | 여러 개 넣는 게 왜 이득인가 | 한 번 읽은 가중치의 상각 — 산술 강도 상승 | 넣을 작업의 모양이 같은가 |
| 구조 | 어떤 모양으로 쌓이나 | prefill은 S가 크고 decode는 S=1 — 패딩 낭비와 종료 시점 분산 | 빈 슬롯을 누가 언제 다시 채우나 |
| 시점 | 배치를 언제 다시 짜나 | static·dynamic·continuous — 매 iteration 재구성이 continuous | prefill과 decode가 한 스텝에서 만나면 |

이후 기법들을 읽을 때 길을 잃지 않기 위한 핵심 개념을 다시 정리하면:

- **iteration** = 모델을 처음부터 끝까지 한 번 통과시키는 것. decode에서는 토큰 1개 생성. 원자적이며, 스케줄러의 개입 지점은 iteration 경계뿐이다
- **배칭** = 여러 요청의 입력을 같은 텐서에 쌓아 한 forward에 넣는 것. 목적은 오직 가중치를 한 번만 읽기다
- **다 같이 prefill/decode** = 시간적 동시가 아니라 같은 forward pass 안이라는 뜻. 길이가 다르면 패딩 또는 varlen 이어붙이기로 맞춘다
- **decode 배치에 시점 차이는 없다** — 같은 GEMM의 다른 행, lockstep이다. 차이가 나는 것은 오로지 끝나는 시점이다
- **세 방식의 차이** = 텐서 쌓기는 동일하고, 배치 멤버십을 언제 다시 정하느냐뿐이다
- **continuous batching의 대가** = prefill과 decode의 혼합. selective batching과 chunked prefill이 필요해진 이유다

continuous batching은 종착점이 아니라 새 문제의 시작점이다. 6장의 나머지 기법들은 전부 [이 지도](#남는-질문-6장의-나머지) 위의 좌표로 읽을 수 있다.

<br>

# 참고 링크

- [Hands-On LLM Serving and Optimization (O'Reilly)](https://www.oreilly.com/library/view/hands-on-llm-serving/9798341621480/)
- [Orca: A Distributed Serving System for Transformer-Based Generative Models (OSDI '22)](https://www.usenix.org/conference/osdi22/presentation/yu)
- [SARATHI: Efficient LLM Inference by Piggybacking Decodes with Chunked Prefills](https://arxiv.org/abs/2308.16369)
- [Anyscale — How continuous batching enables 23x throughput in LLM inference](https://www.anyscale.com/blog/continuous-batching-llm-inference)
- [The Engineering Behind LLM Inference: Serving in Production (YouTube)](https://www.youtube.com/watch?v=9gmHwe5-j0E&t=611s)
- [LLM 서빙과 최적화 - 3.2. 배치 요청: 정적 배칭의 효과와 한계]({% post_url 2026-08-14-Dev-LLM-Serving-Optimization-03-02-LLM-Serving-From-Scratch-Batch-Request %})
- [LLM 서빙과 최적화 - 3.3. prefill과 decode: 생성 추론의 두 단계]({% post_url 2026-08-14-Dev-LLM-Serving-Optimization-03-03-LLM-Serving-Prefill-Decode %})
- [Roofline 모델로 보는 LLM 서빙]({% post_url 2026-08-21-Dev-Roofline-Model-LLM-Serving %})

<br>
