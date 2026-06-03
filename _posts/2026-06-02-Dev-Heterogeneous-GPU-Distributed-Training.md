---
title: "[Distributed Training] 이기종 GPU 분산학습: 다른 기종을 한 DDP 잡에 섞으면 벌어지는 일"
excerpt: 서로 다른 기종의 GPU를 한 DDP 잡에 섞으면 어떻게 되는지 직접 확인하고, 동기 데이터 병렬에서 이기종 GPU가 손해인 이유를 정리해 보자.
categories:
  - Dev
toc: true
header:
  teaser: /assets/images/blog-Dev.jpg
tags:
  - Distributed-Training
  - DDP
  - GPU
  - PyTorch
  - NCCL
  - MLOps
  - Scheduling
  - Blackwell
---

<br>

# TL;DR

- 쿠버네티스 스케줄러는 GPU 기종을 구분하지 않는다. RTX 5090(32GB)과 RTX 6000 Pro(96GB)가 한 풀에 섞여 있으면, 한 잡의 워커가 두 기종에 동시에 배치될 수 있고, **그 상태로도 학습은 돌아간다**
- 동기 데이터 병렬(synchronous data parallel — 대표 구현이 PyTorch DDP)에서는 두 가지 문제가 생긴다: **straggler**(매 step이 최저속 GPU에 묶여 전체가 느려짐, 항상 발생)와 **OOM**(배치를 큰 카드 기준으로 잡으면 작은 카드가 메모리 부족으로 종료, 조건부 발생)
- 수렴/정확도 자체는 깨지지 않는다. gradient가 동일하게 allreduce되므로 모델 품질은 동질 풀에서 돌릴 때와 같다. 문제는 성능과 효율이다
- 따라서 동기 데이터 병렬 잡에서는 **한 잡 = 한 GPU 기종**이 운영 원칙이 된다. 클러스터 전체를 통일하라는 뜻이 아니라, 각 잡이 동질 풀에 라우팅되도록 설계하라는 뜻이다
- 메모리 용량(VRAM)은 혼재 가능 여부를 가르는 **feasibility gate**다. 연산력 차이는 선형적 손해지만, 메모리 차이는 OOM이라는 이진적 벽이다

<br>

# 들어가며: 스케줄러는 GPU 기종을 구분하지 않는다

학습용으로 쓰는 GPU 노드 풀에 서로 다른 기종이 섞여 있는 상황을 가정해 보자. 일부 노드는 RTX 5090(VRAM 32GB), 일부 노드는 RTX 6000 Pro Blackwell(VRAM 96GB)을 달고 있다. 둘 다 같은 노드 풀(노드 라벨/role 하나)로 묶여 스케줄링 대상이 된다.

여기서 문득 궁금해졌다. **쿠버네티스 스케줄러 입장에서는 파드(Pod)가 요청한 `nvidia.com/gpu` 자원이 있는 노드에 올리기만 하면 되는 것 아닌가?** 그 GPU가 5090인지 6000 Pro인지까지 스케줄러가 신경 쓸 이유는 없어 보였다. 그렇다면 분산학습 잡 하나를 이 풀에 던지면, 워커(worker)들이 두 기종에 자유롭게 흩뿌려져 올라갈 것이라는 가설이 선다.

직관적으로는 "기종이 다르면 학습이 아예 안 돌아가거나, 돌더라도 많이 느릴 것"이라고 짐작해볼 수 있다. 그런데 "안 돌아간다"와 "느리다"는 사실 메커니즘이 전혀 다른 이야기다. 정말 그런지, 그리고 섞이면 구체적으로 무슨 일이 벌어지는지 직접 확인해 보기로 했다.

<br>

# 재현: 두 기종에 분산 배치되다

혼재 노드 풀에 동기 데이터 병렬 학습 잡(PyTorch DDP)을 제출하고, 각 워커가 어느 노드에 떨어졌는지를 Ray 모니터링 대시보드의 GRAM(GPU RAM 사용량) 컬럼으로 확인했다.

![한 DDP 잡의 워커가 RTX 5090(32607MiB)과 RTX 6000 Pro(97887MiB) 노드에 동시에 떨어진 모습]({{site.url}}/assets/images/heterogeneous-gpu-ddp-mixed-gram.png){: .align-center width="320"}

<br>

GRAM 컬럼을 보면 같은 잡의 워커들이 두 종류의 메모리 총량을 보고하고 있다.

- `32607MiB` → 총량 약 32GB = **RTX 5090** 노드에 올라간 워커
- `97887MiB` → 총량 약 96GB = **RTX 6000 Pro** 노드에 올라간 워커

즉 가설대로다. 스케줄러는 기종을 구분하지 않으므로, **한 잡의 워커가 5090 노드와 6000 Pro 노드에 동시에 배치됐고, 그 상태로도 학습은 돌아갔다.** "이기종이면 아예 안 돈다"는 직관은 틀렸다. 일단 돌아가긴 한다.

문제는 여기서부터다. 돌아간다고 해서 괜찮다는 뜻은 아니다.

<br>

# 분석: 동기 데이터 병렬에서 벌어지는 일

## 분류 체계: 동기 데이터 병렬이란

본격적인 분석에 앞서, 이 글에서 계속 쓸 "동기 데이터 병렬"이 무엇인지 먼저 정의한다. "동기/비동기 × 병렬/비병렬"의 단일 4분류로 보면 깔끔히 맞지 않는다. 실제로는 여러 직교 축이 겹쳐 있고, 이 분류는 **분산학습 안에서** 일어난다.

```text
ML 학습 잡
├─ 단일 디바이스 (1 GPU)         ← 병렬화 축 자체가 없음. 동기/비동기 개념 무의미
└─ 분산학습 (2+ GPU)            ← 여기서부터 분류가 갈림
    │
    ├─ [축 A] 무엇을 쪼개나? (병렬화 전략)
    │   ├─ 데이터 병렬    : 모델을 복제, 데이터를 쪼갬           ← 가장 흔함
    │   ├─ 텐서 병렬      : 한 레이어 연산을 여러 GPU로 쪼갬     ← 모델이 GPU 하나에 안 들어갈 때
    │   ├─ 파이프라인 병렬 : 레이어들을 stage로 쪼개 GPU에 분배
    │   └─ 하이브리드(3D) : 위를 조합 (대형 LLM 학습)
    │
    └─ [축 B] 언제 동기화하나? (주로 데이터 병렬에서)
        ├─ 동기(synchronous) : 매 step allreduce barrier (= DDP)  ← 거의 기본값
        └─ 비동기(async)     : barrier 없이 각자 진행 (parameter server)
```

- **"동기 데이터 병렬" = [축 A: 데이터 병렬] + [축 B: 동기]**. PyTorch DDP가 대표 구현이고, 같은 방식을 구현한 것으로 Horovod, TensorFlow `MirroredStrategy`, PyTorch FSDP / DeepSpeed ZeRO(데이터 병렬 계열이되 파라미터를 sharding하는 변형) 등이 있다. 가장 흔한 기본 조합이다
- "비병렬"(단일 디바이스)에는 동기/비동기 축이 **존재하지 않는다**(혼자라 동기화할 상대가 없음). 그래서 "동기/비동기 × 병렬/비병렬 4칸"이 깔끔히 안 채워지는 것이다
- 병렬 쪽도 동기/비동기 2칸이 아니라, 그 위에 "무엇을 쪼개나(축 A)" 축이 하나 더 있어서 실제로는 더 다차원이다

> 데이터 병렬·텐서 병렬·파이프라인 병렬의 차이와 NCCL 통신 패턴은 분산학습의 기본기에 해당한다. 이 글에서는 가장 흔한 조합인 동기 데이터 병렬에 한정해서 본다.

이 글의 재현 사례와 이후 논의는 모두 **동기 데이터 병렬**, 그중에서도 대표 구현인 **PyTorch DDP** 잡을 전제로 한다.

## 혼재의 두 증상: straggler와 OOM

처음 짐작했던 "안 돌아가거나 느릴 것"이라는 직관을 정확히 쪼개면, 서로 다른 두 현상이 한 문장에 뭉쳐 있다.

### straggler: 매 step이 최저속 GPU에 묶인다

동기 데이터 병렬은 매 step마다 모든 워커의 gradient를 맞추는 동기화 지점을 거친다(그 메커니즘은 뒤의 allreduce barrier 절에서 다룬다). 이 동기화 때문에 **step 시간이 가장 느린 GPU에 묶인다.** 5090과 6000 Pro는 연산 throughput이 다르므로, 전체 처리량이 느린 카드 수준으로 수렴한다.

> 분산 시스템에서 "전체 잡을 끝까지 못 끝내게 발목을 잡는 느린 일꾼"을 **straggler(낙오자)**라고 부른다. 원래 MapReduce/Hadoop에서 나온 표준 용어이고, 분산학습 논문에서도 그대로 쓴다("straggler problem", "straggler mitigation"). 검색 키워드로도 이 단어를 그대로 쓰면 된다.

이 straggler 현상은 **혼재하기만 하면 항상 발생**한다. 배치를 어떻게 잡든, 빠른 카드는 매 step 느린 카드를 기다린다.

### OOM: 작은 메모리 카드가 배치를 못 올린다

이쪽이 "아예 안 돌아간다"의 진짜 실체일 수 있다. DDP는 모든 워커(rank)에게 **같은 per-GPU micro-batch**를 준다. 만약 누군가 배치 크기를 96GB 카드 기준으로 넉넉하게 잡아두면, 같은 잡에 끼어든 32GB 5090 워커는 그 배치를 메모리에 올리지 못하고 **OOM(Out Of Memory)으로 즉시 죽는다.**

그래서 배치는 **가장 작은 메모리 카드(5090의 32GB)에 맞춰야** 잡 전체가 살아남는다. 결국 작은 카드가 per-GPU 배치의 상한을 정하고, 그만큼 큰 메모리 카드(6000 Pro의 96GB)는 full로 쓰지 못하게 된다.

### 수렴·정확도는 안 깨진다

여기서부터는 직접 검증한 내용이 아니다. 앞의 실험에서는 워커가 두 기종에 올라가 학습이 시작되는 것까지만 확인하고, 몇 step 돌리다 잡을 종료했을 뿐 끝까지 학습시켜 정확도를 비교해 보지는 않았다. 그래서 "그러면 모델 품질은 괜찮은 건가?"가 궁금해 Claude에게 물어봤고, 그 답을 원리로 정리하면 다음과 같다.

혼재해도 **학습 결과물(수렴·정확도)은 정상**이라는 것이다. global batch가 같고 gradient가 동일하게 동기화되므로, 모델이 학습하는 방향 자체는 동질 풀에서 돌릴 때와 같다. 혼재의 문제는 "틀린 모델이 나온다"가 아니라 **"느려진다 + 비효율적이다 + (잘못 설정 시 잡이) 죽는다"**라는 것이다. 이 구분이 핵심이다.

> 즉 앞의 재현은 "정말 두 기종에 흩뿌려져 올라가는가"까지만 직접 본 것이고, 수렴/정확도가 깨지지 않는다는 부분은 DDP의 gradient 동기화 원리에 기댄 추론(+ AI에게 확인)이다.

## allreduce barrier

"매 step이 가장 느린 GPU에 묶인다"는 말의 정확한 메커니즘은 `step → allreduce → barrier` 세 조각으로 나눠 보면 분명해진다.

### 한 step의 구조 (DDP 기준)

```python
# DDP에서 1 step(1 iteration) 동안 각 rank가 하는 일
forward  : 입력 → 예측 → loss 계산
backward : loss를 미분 → 각 rank가 "자기 데이터로 만든 local gradient" 보유
# ─────────── 여기서 allreduce (gradient 동기화) ───────────
optimizer: 동기화된 gradient로 weight 갱신
```

- rank = 하나의 GPU 프로세스. `world_size=32`면 rank 0~31이 존재한다
- 데이터 병렬이라 각 rank는 **서로 다른 데이터 조각**으로 forward/backward를 돈다
- 그래서 backward가 끝난 직후에는 rank마다 gradient가 **제각각**이다

### allreduce: gradient를 합쳐 모두에게 되돌리는 집합 통신

allreduce는 모든 rank의 gradient를 **합산(또는 평균)**해서, 그 결과를 다시 모든 rank에 뿌리는 집합 통신(collective)이다. 끝나면 32개 GPU 전부가 동일한 평균 gradient를 갖는다. 이래야 모든 모델 복제본(replica)의 weight가 같은 방향으로 갱신되어 계속 동일하게 유지된다.


### barrier: 왜 자동으로 동기화 지점이 되나

allreduce는 모든 rank의 local gradient가 준비되어야 합산을 시작할 수 있다는 데이터 의존성을 갖는다. 그래서 backward를 먼저 끝낸 빠른 GPU도 allreduce 호출 지점에서 **가장 느린 rank의 backward가 완료될 때까지 블로킹(blocking)된다.** DDP 학습 루프에는 별도의 `barrier()` 호출이 없다. allreduce가 모든 rank의 local gradient를 필요로 하는 데이터 의존성 자체가 암묵적 동기화 지점(implicit synchronization point)으로 작동한다.

![DDP 한 step에서 빠른 rank0(RTX 6000 Pro)이 allreduce 지점에서 느린 rank1(RTX 5090)의 backward 완료를 기다리는 모습. step 시간은 가장 느린 rank의 backward에 통신을 더한 값이 된다]({{site.url}}/assets/images/gpu-different-types.svg){: .align-center width="480"}

결국 `step 시간 = max(모든 GPU의 backward 시간) + 통신`이 되고, 느린 카드 하나가 매 step 전체를 게이팅한다. 이게 straggler가 발생하는 정확한 지점이다.

## 혼재 결과: 배치 기준의 트레이드오프

DDP가 모든 rank에 같은 per-GPU micro-batch를 준다는 제약 때문에, 배치를 어느 메모리 용량에 맞추느냐로 결과가 갈린다. 어느 쪽도 두 카드를 모두 효율적으로 쓰지는 못한다.

| 배치 기준 | 기준 카드 | 결과 |
|-----------|-----------|------|
| 최소 메모리 기준 | 5090 (32GB) | 6000 Pro 메모리 약 2/3 미사용 + 매 step throughput이 5090에 묶임 (저효율) |
| 최대 메모리 기준 | 6000 Pro (96GB) | 5090 rank가 OOM으로 종료 (잡 abort) |

즉 최소 메모리 기준으로 맞추면 96GB 카드를 32GB 카드만큼만 활용하게 되고, 최대 메모리 기준으로 맞추면 작은 카드가 OOM으로 종료된다. 앞에서 본 straggler(저throughput)와 OOM이 이 두 설정에 각각 대응한다.

### 제3안은 표준 도구에 없다

여기서 자연스럽게 드는 생각이 있다. **"6000 Pro엔 큰 배치, 5090엔 작은 배치를 주면 둘 다 살리고 둘 다 full로 쓸 수 있지 않나?"**

원리적으로는 맞지만, vanilla PyTorch DDP는 이걸 지원하지 않는다. rank마다 배치가 다르면 gradient 기여도가 달라져서 평균이 왜곡된다(큰 배치로 만든 gradient가 통계적으로 더 신뢰도 높은데, 똑같은 가중치로 평균됨). 이를 보정하려면 gradient에 배치 크기 비례 가중치를 매겨야 하는데, 단순 스칼라 곱이 아니라 학습률·수렴 역학과 맞물려 튜닝이 까다롭고, vanilla DDP의 allreduce 경로를 직접 수정해야 해서 표준 프레임워크가 제공하는 범위 밖이다. 이 문제를 다루는 게 heterogeneity-aware training인데, 아직 연구 레벨이고 뒤에서 범위를 나눠 다시 정리한다. 그래서 **현실의 표준 DDP에서는 최소 메모리 기준(저효율) 아니면 최대 메모리 기준(OOM), 둘 중 하나로 귀결**된다.

<br>

# best practice: 잡 단위 동질성

"무조건 같은 GPU여야 하나, 스펙이 비슷하면 괜찮은가?" — 이 질문을 정확히 쪼개면 두 축이다. **메모리**와 **연산 throughput**. 둘 다 봐야 한다.

| 축 | 차이가 나면 | "비슷하면 괜찮나?" |
|----|-------------|---------------------|
| 메모리(VRAM) | 배치가 최소 메모리에 캡 → 큰 카드 용량 낭비, 잘못 설정 시 OOM | No. 동일해야 함. 32 vs 96은 "비슷"이 아님. 메모리는 hard cap |
| 연산 throughput | 가장 느린 카드에 step이 묶임 | 선형 손해. 5~10% 차이는 감내 가능, 세대·티어가 다르면 손해 큼 |

그래서 정확한 답은 이렇다.

- **동기 데이터 병렬 한 잡 안에서는 "동일 GPU 기종"이 정답**이다. 이건 "안 그러면 틀린다"는 정합성(correctness) 요구가 아니라, **성능 + 메모리 활용** 요구다
- **연산이 비슷해도 메모리가 다르면 "비슷한 GPU"가 아니다.** 5090(32GB)과 6000 Pro(96GB)는 둘 다 Blackwell GB202 다이를 쓰는 사촌이라 연산은 비슷할 수 있어도, 메모리 3배 차이 때문에 위 표의 hard cap에 걸린다. 딱 "스펙 비슷해 보여도 섞으면 안 되는" 반례다
- 결론: **한 잡 = 한 GPU 기종.** 단 클러스터 전체를 한 기종으로 통일할 필요는 없다. 여러 풀이 공존하되, 각 잡이 단일 동질 풀 위에 떨어지게 하면 된다

## VRAM은 feasibility gate

메모리가 혼재 가능 여부를 좌우하는 hard cap이라면, 결국 "메모리가 가장 중요한 스펙"이라는 뜻일까? 맥락을 갈라야 한다. **혼재 가능 여부를 가르는 게이트**로서는 메모리가 1순위가 맞지만, **절대적으로 가장 중요한 스펙**은 아니다.

| 스펙 | 역할 | 성격 |
|------|------|------|
| 메모리 용량 (VRAM capacity) | 배치가 들어가냐 / OOM 나냐 | feasibility gate — 넘으면 즉시 죽음(이진적). "비슷"이 안 통함 |
| 연산력 (FLOPS), 메모리 대역폭 | 들어간 다음 얼마나 빠르냐 | performance — 선형적. 차이만큼 비례 손해 |
| interconnect (NVLink/PCIe/네트워크) | 통신(allreduce)이 얼마나 빠르냐 | performance — 통신 병목 좌우 |

- 이기종 혼재가 되냐 안 되냐를 따질 때는 메모리 용량이 가장 먼저 걸리는 **hard cap**이라 1순위로 보인다. OOM은 타협이 없기 때문이다.
- 하지만 **학습이 얼마나 빠르냐(throughput)**는 메모리 용량이 아니라 **연산력 + 메모리 대역폭**이 좌우한다. 32GB든 96GB든, 배치가 들어가기만 하면 그다음 속도는 코어·클럭·대역폭 싸움이다

그래서 정확히 말하면 **"메모리 용량은 가장 중요한 스펙이 아니라, 이기종 혼재 가능성을 가르는 가장 먼저 걸리는 제약(feasibility gate)"**이다. 5090과 6000 Pro가 "비슷"의 범주에 못 드는 이유도 연산이 달라서가 아니라 용량 3배 차이가 게이트를 통과 못 해서다.

> 참고로 메모리 안에서도 용량(capacity)과 대역폭(bandwidth)은 다른 스펙이다. 용량이 배치를 게이트하고, 대역폭이 throughput에 기여한다. GPU 메모리 자체의 무결성 관점은 [GPU ECC]({% post_url 2026-06-01-Dev-GPU-ECC-Memory-Integrity %}) 글에서 따로 다뤘다.

## 이기종이 가능한 경우

"이기종"이라는 단어를 어느 범위에 거느냐에 따라 답이 달라진다.

| 내용 | 범위 |
|------|------|
| 한 학습 잡 내부에 이기종 GPU 섞기 | 연구 레벨. 특수 프레임워크 필요. 일반 프로덕션은 안 함 |
| 클러스터에 이기종 풀 여러 개 공존 | 프로덕션 일상. 5090 풀 + 6000 Pro 풀을 두고 각 잡을 동질 풀에 라우팅. 정상 설계 |
| 이기종 추론 서빙 | 프로덕션 일상. replica가 독립이라 자유롭게 섞고 capacity로 라우팅 |

지금까지 이 글에서 다룬 straggler·OOM 문제는 첫 번째 행, 즉 **한 동기 데이터 병렬 잡 안에 이기종을 섞는 경우**에 해당한다. DDP가 이기종에 가장 취약한 조합이기 때문이다.

그렇다면 이기종을 한 잡 안에서 의도적으로 쓰는 방법은 아예 없는 걸까? 있긴 하다. 다만 vanilla DDP로는 안 되고, 이기종을 흡수하도록 설계된 다른 병렬화/스케줄링을 같이 들고 와야 한다.

- **Heterogeneity-aware data parallel**: 빠르고 큰 카드에 더 큰 micro-batch를 주고, gradient 기여도를 가중 평균한다. 배치를 카드 능력에 비례 분배해 straggler를 상쇄. 표준 프레임워크에는 없다
- **Pipeline parallelism + capacity-aware stage 배치**: 모델을 stage로 쪼개 큰 stage를 큰 GPU에 할당. barrier가 step 전체가 아니라 stage 경계라 이기종 흡수 여지가 있다
- **Asynchronous SGD / parameter server**: barrier 자체를 없앤다. 대신 gradient staleness — 이미 지나간 과거 weight 기준으로 계산된 gradient로 현재 weight를 갱신하는 문제 — 로 수렴이 나빠져서 요즘 대규모 학습에선 거의 안 쓴다

정리하면, 피해야 하는 건 "한 동기 학습 잡의 워커가 서로 다른 기종의 GPU에 흩어지는 것"이다. 클러스터에 여러 기종이 공존하는 것 자체는 문제가 아니다. 앞의 재현이 전자에 해당했고, 해법은 풀을 기종별로 나눈 뒤 각 잡을 동질 풀에 라우팅하는 것이다.

<br>

# MLOps 플랫폼 레퍼런스: 동질 GPU 설계

그렇다면 실제로 MLOps 플랫폼은 이 문제를 어떻게 다루고 있을까? 확인해 본 범위에서는 동질 GPU를 전제로 한 설계가 일반적이었고, 이것이 앞서 본 straggler·OOM 문제에 대한 구조적 해법이기도 하다. 근거는 업계 관행과 구현 패턴 두 갈래로 나뉜다.

## 관리형 서비스

AWS SageMaker, GCP Vertex AI 등 대부분의 관리형 학습은 **하나의 training job = 단일 instance type**으로 강제한다. 워커 그룹에 인스턴스 타입을 섞는 걸 애초에 허용하지 않는다. 업계가 "한 잡 = 동질 fleet"을 **API 레벨에서 못박은 것** 자체가 이 best practice의 방증이다.

## 온프레미스 구현 패턴

관리형이 막아주는 걸, 직접 운영하는 클러스터에서는 다음 패턴으로 구현한다.

- **GPU 모델별 노드 라벨**: `nvidia.com/gpu.product` 같은 자동 라벨이나 커스텀 라벨로 기종을 구분한다. NVIDIA GPU Operator의 GFD(GPU Feature Discovery)가 이런 라벨을 자동으로 붙여 준다
- **`nodeSelector` / `affinity`로 단일 동질 풀 타겟팅**: 잡 제출 시 특정 기종 노드만 고르게 한다

```yaml
# 예시: 학습 잡 워커를 RTX 5090 노드에만 떨어지게 고정
spec:
  nodeSelector:
    # GFD가 자동으로 붙이거나, 운영자가 커스텀으로 붙인 라벨
    nvidia.com/gpu.product: "NVIDIA-GeForce-RTX-5090"
```

- **Gang scheduling**(Volcano, Kueue 등): all-or-nothing 배치로, 잡의 워커가 쪼개져 이기종에 흩어지는 것 자체를 방지한다
- **Topology-aware scheduling**: 같은 풀 안에서도 interconnect가 좋은 노드끼리 묶어 통신 병목을 줄인다

핵심은 균형이다. 이기종을 클러스터에서 물리적으로 영구 격리하라는 게 아니다. **같은 클러스터에 5090 풀과 6000 Pro 풀이 공존하되, 라벨 + 스케줄링 제약으로 각 잡을 동질 풀에 라우팅**하는 게 정석이다. 그래야 6000 Pro 풀을 더 큰 모델·더 큰 배치 잡에 따로 활용할 수 있다.

> 위 패턴들의 공통점은 잡이 실행되기 전에 GPU 조건을 플랫폼 레벨에서 거른다는 것이다. 이 발상은 [NCCL GPU 호환성 게이트]({% post_url 2026-04-30-Dev-NCCL-GPU-Compat-CI-Runtime-Gate %})에서 다룬 빌드/런타임 게이트와 같은 결이다. 거기서는 GPU 아키텍처 호환성을, 여기서는 GPU 기종 동질성을 보장한다는 차이만 있다.

<br>

# GPU만의 문제가 아니다

지금까지는 GPU 자체(메모리·연산)만 놓고 봤다. 그런데 현실적으로는 GPU만 다른 게 아니다. 데이터 병렬은 모든 워커가 **대칭(symmetric)**이라고 암묵적으로 가정하는데, 이기종 GPU 노드는 보통 GPU 외의 사양도 함께 다르다.

온프렘 클러스터를 떠올려 보면, RTX 6000 Pro가 꽂힌 서버와 RTX 5090이 꽂힌 서버는 CPU 코어 수, 시스템 메모리(RAM), NUMA 토폴로지, 스토리지·네트워크 대역폭까지 다른 경우가 많다. 같은 학습 잡을 던져도 이 비대칭이 다음 경로에서 문제를 만들 수 있다.

- **host-side 데이터 경로**: 데이터 로딩, 디코딩, augmentation 같은 전처리는 GPU가 아니라 CPU·RAM이 한다. CPU 코어가 적은 노드의 dataloader가 배치를 제때 못 만들어 내면, GPU 연산이 빨라도 그 노드가 또 다른 straggler가 된다. 즉 GPU를 동질로 맞춰도 host가 비대칭이면 step이 다시 최저속 노드에 묶일 수 있다
- **시스템 메모리·NUMA 토폴로지**: 시스템 RAM이 적으면 GPU 전송용 pinned memory나 prefetch 버퍼를 충분히 잡을 수 없다. 또한 멀티소켓 서버에서는 GPU가 물리적으로 특정 CPU 소켓(NUMA 노드)의 PCIe 슬롯에 연결되어 있는데, 학습 프로세스가 GPU와 다른 소켓의 메모리를 사용하면 소켓 간 링크를 타야 해서 host↔device 전송(H2D)이 느려진다. 서버마다 소켓 수나 GPU-소켓 배치가 다르면 이 지연도 노드마다 달라진다

그리고 실제 서버를 구성할 때를 생각해 보면, 한 서버에 서로 다른 기종의 GPU를 섞어 꽂는 경우는 드물다. 비싼 GPU를 달 서버는 CPU·RAM·네트워크도 함께 좋은 사양으로 맞추는 게 보통이고, 저사양 GPU를 꽂는 서버는 호스트 스펙도 그에 맞게 낮다. 결국 "이기종 GPU 풀"은 실제로는 "이기종 서버 풀"인 경우가 대부분이다. GPU 차이 뒤에 host 사양 차이가 자연스럽게 따라온다.

> 정밀 벤치마크로 정량화한 것은 아니지만, 실제 클러스터 구성을 떠올려 보면 이 문제를 무시하기 어렵다. GPU 차원의 straggler·OOM이 1차 요인이고, host 사양 비대칭은 그 위에 얹히는 2차 요인이다. 결론은 같은 방향으로 강화된다 — **이기종 GPU가 섞인 노드 풀에 학습 잡을 사양 고려 없이 던지면 안 된다.**

<br>

# 정리

| 질문 | 답 |
|------|-----|
| 이기종 학습 시 무슨 일? | (동기 DDP 기준) 학습은 돌아가나 ① 최저속 카드에 묶여 느려지고(straggler) ② 배치 잘못 잡으면 작은 카드 OOM. 수렴/정확도는 정상 |
| 무조건 같은 GPU가 best practice? | 동기 DDP 한 잡 안에선 사실상 Yes. 단 클러스터 전체 통일이 아니라 "잡 단위 동질" |
| 스펙 비슷하면 OK? | 메모리가 같을 때만. 메모리 차이는 "비슷"으로 못 넘김(배치 hard cap). 연산은 5~10% 정도면 감내 가능 |
| GPU만 보면 되나? | 아님. 이기종 GPU 풀은 보통 이기종 서버 풀(CPU·RAM·NUMA 차이)이라 host-side straggler가 2차 요인으로 얹힘 |
| 이기종 학습 자체가 불가능? | 아님. heterogeneity-aware DP / pipeline parallel / async가 흡수. 단 vanilla DDP론 안 됨 |
| 플랫폼은 동질만 고려? 옳은가? | Yes & 옳음. 관리형은 API로 강제. 직접 운영 시 GPU 라벨 + nodeSelector + gang scheduling으로 구현 |

쿠버네티스 스케줄러는 "GPU가 있는 노드"까지만 본다는 단순한 사실에서 출발했지만, 그 위에서 동기 데이터 병렬이 매 step을 최저속 워커에 묶는다는 구조 때문에 "한 잡 = 한 기종"이라는 운영 원칙이 따라 나온다. 이기종 자체가 죄는 아니고, **이기종을 한 동기 잡에 흩뿌리는 것**이 문제다.

## 심화 학습 키워드

이 주제는 분산학습 표면만 짚고 넘어가지만, 독립적으로 더 정리해 볼 만한 키워드들이다.

- **synchronous SGD straggler problem**: straggler 완화 기법(backup workers, gradient coding 등)
- **heterogeneity-aware training**: 배치 비례 분배, gradient weighting (예: Whale 등 연구)
- **gradient staleness in async SGD**: 비동기가 수렴을 어떻게 해치는가
- **gang scheduling**: Volcano / Kueue의 all-or-nothing 배치 원리
- **NCCL collective topology**: 이기종/PCIe-NVLink 혼재에서 ring-allreduce 토폴로지가 어떻게 바뀌는가

<br>

# 참고 자료

- [PyTorch Distributed Data Parallel (DDP) 공식 문서](https://docs.pytorch.org/docs/stable/notes/ddp.html)
- [NVIDIA NCCL: AllReduce](https://docs.nvidia.com/deeplearning/nccl/user-guide/docs/usage/collectives.html)
- [NVIDIA GPU Feature Discovery (GFD)](https://github.com/NVIDIA/gpu-feature-discovery)
- [Kueue Documentation](https://kueue.sigs.k8s.io/docs/)
- [Volcano: Gang Scheduling](https://volcano.sh/en/docs/gang_scheduling/)

<br>
