---
title: "[LLM] LLM 서빙과 최적화: LLM 서빙의 도전 과제 - 5.2. GPU 스펙 읽기: 연산과 메모리"
excerpt: "GPU 스펙의 연산·메모리 속성을 읽고 H100 SXM과 NVL을 비교해 보자."
categories:
  - Dev
toc: true
header:
  teaser: /assets/images/blog-Dev.jpg
tags:
  - GPU
  - TFLOPS
  - Tensor-Core
  - HBM
  - Memory-Bandwidth
  - VRAM
  - H100
  - Hands-On-LLM-Serving-and-Optimization-Study
  - Hands-On-LLM-Serving-and-Optimization-Study-Week-3
last_modified_at: 2026-08-22
---

*[서종호(가시다)](https://www.linkedin.com/in/gasida99/)님의 Hands-On LLM Serving and Optimization Study (LLMSO) 3주차 학습 내용을 기반으로 합니다.*

<br>

# TL;DR

- LLM 서빙에 영향을 주는 GPU 스펙은 연산·메모리(용량·대역폭)·인터커넥트·전력 네 요소로 나뉜다. 앞의 둘은 GPU 한 장 안에서 끝나는 숫자고, 인터커넥트는 여러 장을 한 덩어리로 쓸 수 있는가의 문제다
- 연산 속성은 정밀도별 TFLOPS로 읽는다. 네 자릿수 TFLOPS는 전부 텐서 코어에서 나오고, 스펙시트의 CUDA Cores 수는 LLM 서빙 성능 지표로 거의 쓸모가 없다
- 메모리는 용량(모델이 올라가는가)과 대역폭(decode가 얼마나 빠른가)이 서로 다른 질문에 답한다. 한쪽이 크다고 다른 쪽을 이기지 않는다
- H100 SXM vs NVL 비교의 결론: 모델이 안 들어가면 NVL(94GB·3.9TB/s), 들어가면 SXM(연산·NVLink 우위)

<br>

# GPU 스펙의 네 요소

[5.1편]({% post_url 2026-08-22-Dev-LLM-Serving-Optimization-05-01-LLM-Serving-Challenge-Importance %})에서 서빙 최적화가 왜 중요한지 봤다. 다음 단계는 LLM을 구동하는 하드웨어를 이해하는 것이다. 가속기 구성 선택은 LLM 서빙에서 가장 중요한 결정 중 하나인데, 하드웨어 제약이 메모리 용량·연산 성능·효율의 상한을 정하기 때문이다. 책은 NVIDIA GPU에 초점을 맞춘다. 2026년 초 현재 NVIDIA의 범용 GPU 컴퓨팅(GPGPU) 솔루션이 시장을 지배하고 있어서다 (다른 가속기 동향은 [5.5편]({% post_url 2026-08-22-Dev-LLM-Serving-Optimization-05-05-LLM-Serving-Challenge-Accelerator-Trends %})에서 다룬다).

GPU 스펙 항목은 많지만, 책은 LLM과 가장 관련 있는 네 그룹으로 압축한다.

| 요소 | 스펙 항목 | 결정하는 것 |
| --- | --- | --- |
| 연산(compute) | 정밀도별 TFLOPS, 텐서 코어, 지원 정밀도 | 행렬 곱셈·어텐션·MLP 연산 처리량 |
| 메모리 용량 | VRAM (GB) | 모델 가중치 + KV 캐시 적재 가능 여부 |
| 메모리 대역폭 | GB/s ~ TB/s | 가중치·활성값을 연산 유닛으로 나르는 속도 |
| 인터커넥트 | PCIe, NVLink, NVSwitch, InfiniBand | 여러 GPU를 한 덩어리로 묶을 수 있는 범위 |

여기에 전력 소비(power consumption)가 더해진다. 성질이 다른 점 하나를 먼저 짚어 두면, 연산과 메모리는 **GPU 한 장 안에서 끝나는 숫자**고, 인터커넥트는 **여러 장을 한 덩어리로 쓸 수 있는가**를 정하는 값이다. 이 글은 한 장 안의 속성(연산·메모리·전력)을 다루고, 인터커넥트는 [5.3편]({% post_url 2026-08-22-Dev-LLM-Serving-Optimization-05-03-LLM-Serving-Challenge-GPU-Interconnect-Selection %})에서 따로 본다.

## 최소 어휘

책이 정의 없이 쓰는 단어들을 한 화면으로 모아 둔다. 이 장의 스펙 표(책 표 5-1·5-2·5-4)를 읽는 데 필요한 수준이다.

| 단어 | 한 줄 정의 | 쓰이는 곳 |
| --- | --- | --- |
| 소켓 | 메인보드에 CPU 패키지 1개를 꽂는 자리. GPU 서버는 거의 전부 2소켓 | PCIe 레인 예산, NUMA |
| 노드(node) | 보통 섀시(서버 박스) 1대 = OS 1개 = NVLink 도메인 1개 | intra-node / inter-node |
| die vs. package | die는 회로가 새겨진 실리콘 조각, package는 그것을 담아 부품으로 파는 단위 | 인터커넥트의 경계 |
| 폼팩터 | GPU를 서버에 장착하는 물리 방식(SXM / PCIe). NVLink 지원 여부를 결정하는 전제 | 책 표 5-2 |
| SM | Streaming Multiprocessor. 연산 유닛·스케줄러·온칩 SRAM을 묶은 GPU 내부 단위. H100 SXM은 132개 | TFLOPS의 출처 |
| 정밀도 | 파라미터 1개를 몇 비트로 저장하는가. FP32 / FP16·BF16 / FP8·INT8 = 4 / 2 / 1바이트 | 모델 크기 계산 |
| TFLOPS | 1초에 가능한 부동소수점 연산 횟수(10^12). 정밀도마다 값이 다르다 | 연산 속성 |

지금은 이 정도로 충분하다. SM 내부가 궁금하면 [SM 마이크로아키텍처]({% post_url 2026-08-21-CS-GPU-SM-Microarchitecture %}), die·package·노드 경계가 궁금하면 [GPU 패키징과 노드 경계]({% post_url 2026-08-21-CS-GPU-Package-Node-Boundary %})에서 따로 정리한다.

<br>

# 연산 속성

## 정밀도별 TFLOPS

**FLOPS**(Floating-point Operations Per Second)는 1초에 수행 가능한 부동소수점 연산(곱셈·덧셈 등) 횟수, 즉 이론적인 연산 성능 지표다. tera-는 1조(10^12)를 뜻하므로, H100 SXM의 FP16 1979 teraFLOPS는 초당 1979 × 10^12번의 연산이 가능하다는 의미다.

핵심은 **TFLOPS가 하나의 숫자가 아니라는 것**이다. 뒤에 나올 책 표 5-1의 연산 항목은 FP64 / FP64 텐서 코어 / FP32 / TF32 텐서 코어 / BF16 텐서 코어 / FP16 텐서 코어 / FP8 텐서 코어 / INT8 텐서 코어처럼 정밀도별로 행이 나뉘고, 행마다 값이 다르다. 스펙을 읽을 때는 내가 돌릴 정밀도의 행만 보면 된다. FP16(16비트)과 FP8(8비트)은 딥러닝에서 쓰이는 저정밀도 포맷인데, FP8은 FP16의 절반 크기라 연산 처리량이 거의 2배다 (정밀도와 품질의 트레이드오프는 책 6장, 시리즈 후속 글에서 다룬다).

## CUDA 코어와 텐서 코어

정밀도별 TFLOPS를 읽을 때 알아 두면 판단이 빨라지는 사실 세 가지가 있다.

- **네 자릿수 TFLOPS는 전부 텐서 코어에서 나온다.** H100 기준 FP32 CUDA 코어 경로는 약 67 TFLOPS인데, FP16 텐서 코어는 1979 TFLOPS다. 같은 칩 안에서 약 30배 차이다. CUDA 코어가 값 하나를 곱하고 더하는 스칼라 레인이라면, 텐서 코어는 행렬 타일 하나를 명령 한 번에 통째로 곱하는 유닛이다
- **스펙시트의 "CUDA Cores" 수는 LLM 서빙 지표로 거의 쓸모가 없다.** LLM의 계산 대부분(어텐션·MLP의 행렬 곱)은 텐서 코어에서 돌기 때문이다. CUDA 코어가 실제로 맡는 것은 softmax, LayerNorm, RoPE, 샘플링 같은 비(非)행렬곱 연산이다. 예를 들어 L40S 스펙에서 봐야 할 것은 CUDA Cores 18,176이 아니라 FP16 텐서 코어 362.05 TFLOPS다
- **FP8은 새 유닛이 아니라 같은 텐서 코어의 저정밀 모드다.** H100에서 FP8이 FP16의 정확히 2배(1979 → 3958)인 이유는 같은 유닛에서 비트 폭을 절반으로 줄여 한 클럭에 2배를 밀어넣기 때문이다. 텐서 코어 내부 데이터 경로가 8비트를 지원해야 하는 문제라, 이전 세대(A100·A10)는 FP8을 지원하지 않는다

1979라는 숫자가 정확히 어디서 유도되는지(SM 수 × 텐서 코어 수 × 클럭), 그리고 왜 실제로는 그 절반도 안 나오는지는 [SM 마이크로아키텍처]({% post_url 2026-08-21-CS-GPU-SM-Microarchitecture %})에서 분해한다. 지금은 위 세 가지로 GPU 선택 판단에는 충분하다.

<br>

# 메모리 속성

메모리 속성은 단위가 다른 두 숫자가 서로 다른 질문에 답한다.

## 용량: 모델 적재

**VRAM 용량(GB)은 "모델이 올라가는가"에 답한다.** 모델 가중치와 KV 캐시가 여기 들어가야 한다. 들어가지 않으면 속도 이야기가 시작되지 않고, 모델을 여러 GPU로 쪼개야 한다. 주어진 모델·워크로드에서 얼마나 필요한지 추정하는 방법은 [5.4편]({% post_url 2026-08-22-Dev-LLM-Serving-Optimization-05-04-LLM-Serving-Challenge-Loading-Execution-Bottleneck %})에서 계산한다.

## 대역폭: decode 속도 상한

**메모리 대역폭(TB/s)은 "decode가 얼마나 빠른가"에 답한다.** [3.3편]({% post_url 2026-08-14-Dev-LLM-Serving-Optimization-03-03-LLM-Serving-Prefill-Decode %})에서 본 대로 decode는 토큰 하나를 만들 때마다 모델 가중치 전체를 다시 읽는다. 그래서 토큰당 생성 시간(TPOT)의 이론 상한이 이 숫자에서 나온다 — 계산은 [Roofline 모델로 보는 LLM 서빙]({% post_url 2026-08-21-Dev-Roofline-Model-LLM-Serving %}#h100-숫자로-확인)에 있다.

참고로 GPU 메모리는 HBM(High-Bandwidth Memory)이다. CPU 메모리에 쓰이는 일반 DRAM과 별개 물건이 아니라 DRAM의 특수한 형태로, 용량·범용성 대신 대규모 병렬 데이터 이동에 최적화되어 있다.

두 숫자는 별개 축이라 한쪽이 크다고 모든 것을 이기지 않는다. H100 NVL은 용량 94GB·대역폭 3.9TB/s로 H100 SXM(80GB·3.35TB/s)을 이기지만, TFLOPS는 SXM이 높다. 이 대비는 아래 스펙 읽기에서 그대로 판단 기준이 된다.

<br>

# 전력 속성

마지막으로 전력이다. 눈에 잘 띄지 않지만 근본적인 지표다. 단위는 와트(W)이고 보통 TDP(Thermal Design Power), 즉 지속 부하에서 설계상 소비하는 최대 지속 전력으로 표기된다. 최신 데이터센터 GPU는 수백 W에서 700W 이상까지 간다. 전력 예산이 클수록 연산 밀도와 메모리 대역폭이 높아지지만, 냉각·전력 공급·시스템 통합 요구도 함께 올라간다.

배포 환경에 따라 중요도가 다르다.

- **일반 클라우드 사용자**: 전력은 대부분 추상화되어 있다. 인스턴스 타입을 고르고 시간당 요금을 낼 뿐, 전력은 가격·가용성에 암묵적으로 반영된다
- **클라우드 제공업체·프라이빗 데이터센터**: 전력은 1급 설계 제약이다. 랙당 배치 가능한 GPU 수를 전력·냉각 용량이 제한하므로, 와트당 성능이 고정 인프라 예산에서 처리량을 극대화하는 핵심 지표가 된다
- **엣지·온디바이스**: 전력이 시스템 전체를 규정한다. 배터리·발열·폼팩터 한계 때문에 모델 아키텍처와 정밀도 선택이 전력 효율 중심으로 결정된다

정리하면 전력은 "얼마나 빠른가"가 아니라 **그 성능을 어디서, 어떻게 실현할 수 있는가**를 정하는 요소다. 노드당 GPU가 8장에서 멈추는 이유에도 전력이 크게 관여하는데, 이는 [GPU 패키징과 노드 경계]({% post_url 2026-08-21-CS-GPU-Package-Node-Boundary %})에서 정리한다.

<br>

# 스펙 읽기: H100 SXM vs H100 NVL

이제 실제 스펙 표를 읽어 보자. 책 표 5-1은 H100의 두 변형인 SXM과 NVL을 비교한다.

| 구분 | 항목 | H100 SXM | H100 NVL |
| --- | --- | --- | --- |
| 연산 | FP64 | 34 teraFLOPS | 30 teraFLOPS |
| 연산 | FP64 Tensor Core | 67 teraFLOPS | 60 teraFLOPS |
| 연산 | FP32 | 67 teraFLOPS | 60 teraFLOPS |
| 연산 | TF32 Tensor Core | 989 teraFLOPS | 835 teraFLOPS |
| 연산 | BFLOAT16 Tensor Core | 1979 teraFLOPS | 1671 teraFLOPS |
| 연산 | FP16 Tensor Core | 1979 teraFLOPS | 1671 teraFLOPS |
| 연산 | FP8 Tensor Core | 3958 teraFLOPS | 3341 teraFLOPS |
| 연산 | INT8 Tensor Core | 3958 TOPS | 3341 TOPS |
| 메모리 용량 | GPU Memory | 80 GB | 94 GB |
| 메모리 대역폭 | GPU Memory Bandwidth | 3.35 TB/s | 3.9 TB/s |
| 폼팩터 | Form Factor | SXM | PCIe dual-slot (공랭) |
| 인터커넥트 | Interconnect | NVLink 900GB/s, PCIe Gen5 128GB/s | NVLink 600GB/s, PCIe Gen5 128GB/s |

<center><sup>출처: Hands-On LLM Serving and Optimization (O'Reilly), Table 5-1. NVIDIA H100 제품 페이지 기준</sup></center>

읽는 순서는 앞에서 정리한 그대로다.

1. **연산 행**: 내 정밀도의 행만 본다. 세로로 보면 정밀도가 절반이 될 때마다 값이 약 2배가 되고(FP16 1979 → FP8 3958), 가로로 보면 SXM이 NVL보다 조금 높다. 아키텍처가 같은데 값이 다른 것은 활성 SM 수와 클럭이 다르기 때문이다
2. **메모리 행**: 용량과 대역폭 모두 NVL이 우세하다(94GB > 80GB, 3.9TB/s > 3.35TB/s)
3. **인터커넥트 행**: SXM은 NVLink/NVSwitch로 최대 8장을 900GB/s로 묶을 수 있고, NVL은 NVLink Bridge로 인접 2장을 600GB/s로 잇는다 — 이 차이는 [5.3편]({% post_url 2026-08-22-Dev-LLM-Serving-Optimization-05-03-LLM-Serving-Challenge-GPU-Interconnect-Selection %})에서 본다

그래서 어느 쪽을 골라야 하나. 책은 피자 가게에 비유한다. 연산력은 오븐의 화력, 메모리 대역폭은 반죽을 오븐에 공급하는 속도, 메모리 용량은 반죽을 보관하는 냉장고 크기다. 냉장고가 작으면 장사 자체가 안 되고(모델 로드 불가, OOM), 오븐만 강하고 공급이 느리면 오븐이 놀고(연산력 낭비), 공급만 빠르고 오븐이 약하면 손님이 기다린다(연산 병목). 세 요소의 균형을 워크로드에 맞추는 것이 GPU 선택이다.

판단 기준을 한 줄로 줄이면 이렇다. **서빙하려는 모델(+KV 캐시)이 80GB에 안 들어가면 NVL, 들어가면 연산·NVLink 도메인이 넓은 SXM.** 실제 사용 사례별 GPU 선택(표 5-4의 5종 비교)은 인터커넥트를 이해한 뒤 [5.3편]({% post_url 2026-08-22-Dev-LLM-Serving-Optimization-05-03-LLM-Serving-Challenge-GPU-Interconnect-Selection %}) 말미에서 다룬다.

<br>

# 정리

| 속성 | 스펙에서 읽을 것 | 답하는 질문 |
| --- | --- | --- |
| 연산 | 내 정밀도의 텐서 코어 TFLOPS (CUDA Cores 수 아님) | 행렬 곱을 얼마나 빨리 처리하는가 |
| 메모리 용량 | VRAM GB | 모델 + KV 캐시가 올라가는가 |
| 메모리 대역폭 | TB/s | decode 토큰 생성이 얼마나 빠른가 |
| 전력 | TDP | 그 성능을 어디서 실현할 수 있는가 |

다음 글은 남은 한 요소, GPU 여러 장을 묶는 인터커넥트다. 대역폭 계층(900/600/128/50 GB/s)과 그 위에 올릴 수 있는 병렬화, 그리고 모델 크기별 GPU 선택까지 [5.3편]({% post_url 2026-08-22-Dev-LLM-Serving-Optimization-05-03-LLM-Serving-Challenge-GPU-Interconnect-Selection %})에서 이어진다.

<br>

# 참고 링크

- [Hands-On LLM Serving and Optimization (O'Reilly)](https://www.oreilly.com/library/view/hands-on-llm-serving/9798341621480/)
- [NVIDIA H100 Tensor Core GPU](https://www.nvidia.com/en-us/data-center/h100/)
- [NVIDIA L40S](https://www.nvidia.com/en-us/data-center/l40s/)
- [SM 마이크로아키텍처: CUDA 코어·텐서 코어와 TFLOPS의 출처]({% post_url 2026-08-21-CS-GPU-SM-Microarchitecture %})
- [Roofline 모델: 연산 강도로 판별하는 성능 병목]({% post_url 2026-08-21-CS-Roofline-Model %})
- [Roofline 모델로 보는 LLM 서빙: 세 점으로 나눠 찍는 병목]({% post_url 2026-08-21-Dev-Roofline-Model-LLM-Serving %})
- [단일 모델 서빙 시스템 - 3.3. prefill과 decode: 생성 추론의 두 단계]({% post_url 2026-08-14-Dev-LLM-Serving-Optimization-03-03-LLM-Serving-Prefill-Decode %})

<br>
