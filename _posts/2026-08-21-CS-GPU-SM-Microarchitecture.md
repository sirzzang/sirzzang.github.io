---
title: "[GPU] SM 마이크로아키텍처: CUDA 코어·텐서 코어와 TFLOPS의 출처"
excerpt: "스펙표의 TFLOPS가 어디서 나오는지 SM 구조로 분해해 보자."
categories:
  - CS
toc: true
header:
  teaser: /assets/images/blog-Dev.jpg
tags:
  - GPU
  - CUDA
  - SM
  - Tensor-Core
  - Microarchitecture
  - NVIDIA
  - Hands-On-LLM-Serving-and-Optimization-Study
  - Hands-On-LLM-Serving-and-Optimization-Study-Week-3
last_modified_at: 2026-08-22
---

*[서종호(가시다)](https://www.linkedin.com/in/gasida99/)님의 Hands-On LLM Serving and Optimization Study (LLMSO) 3주차 학습 중 딥다이브한 내용입니다.*

<br>

# TL;DR

- SM(Streaming Multiprocessor)은 처리 블록(processing block) 4개와 이들이 공유하는 자원으로 구성된다. 워프를 발행·실행하는 스케줄 경계는 블록이고, shared memory로 협력하는 데이터 공유 경계는 SM이다
- 스펙시트의 "CUDA Cores"는 FP32 레인만 센 숫자다(H100 SXM: 128 × 132 SM = 16,896). LLM의 행렬 곱은 전부 텐서 코어에서 돌기 때문에, 이 숫자는 서빙 성능 지표로 거의 쓸모가 없다
- 표의 두 자릿수 TFLOPS(FP32 67, FP64 34)는 CUDA 코어 레인에서, 네 자릿수(1979, 3958)는 전부 텐서 코어에서 나온다. FP8은 새 유닛이 아니라 같은 텐서 코어의 저정밀 모드다
- 서빙 실무와 닿는 지점: wave quantization, MIG/MPS의 분할 단위, 그리고 decode 구간에서 nvidia-smi utilization 100%를 믿으면 안 되는 이유가 전부 SM 개념 위에 있다

<br>

# 배경

3주차 학습 내용 [5.2편]({% post_url 2026-08-22-Dev-LLM-Serving-Optimization-05-02-LLM-Serving-Challenge-GPU-Compute-Memory %})은 GPU 연산 속성을 정밀도별 TFLOPS로 읽으면 충분하다고 정리한다. 실무 판단 — 어떤 GPU를 살까, FP8을 쓸까 — 은 실제로 거기서 끝난다. 층위를 나누면 이렇다.

| 층위 | 무엇을 보는가 | 누가 쓰는가 |
| --- | --- | --- |
| 제품/스펙 층 | 정밀도별 TFLOPS, 텐서 코어 세대, FP8·FP4 지원 여부 | 서빙 엔지니어 — GPU 선택, 배치 판단 |
| 마이크로아키텍처 층 | SM 수, SM당 CUDA/텐서 코어, L1·shared 크기, 유닛 배치 | 커널 작성자 — FlashAttention, CUTLASS, 컴파일러 |

그런데 스펙 층의 숫자에 대해 한 발 더 들어간 질문을 던지는 순간 — 1979 TFLOPS의 1979는 어디서 나왔는가, 왜 실제로는 그 절반도 안 나오는가, FlashAttention이 말하는 "온칩"이 무엇인가 — 답은 전부 SM 안에 있다. 이 글은 그 세 질문을 따라 SM을 분해한다. GPU 선택만 하면 되는 상황이라면 이 글 없이 3주차 학습 내용 [5.2편]({% post_url 2026-08-22-Dev-LLM-Serving-Optimization-05-02-LLM-Serving-Challenge-GPU-Compute-Memory %})의 세 가지 결론만으로도 충분하다.

<br>

# SM의 구조

NVIDIA H100의 연산 die인 GH100은 SM이라는 단위의 반복으로 구성된다(H100 SXM은 활성 SM 132개, 풀 다이는 144개). SM 하나의 내부를 보자.

![GH100 SM 블록 다이어그램]({{site.url}}/assets/images/llmso-gh100-sm-diagram.png){: .align-center width="560"}

<center><sup>출처: NVIDIA H100 (Hopper) Architecture Whitepaper — GH100 Streaming Multiprocessor</sup></center>

![GH100 SM 주석판. 처리 블록 4개와 SM 공유 자원을 색으로 구분했다]({{site.url}}/assets/images/llmso-gh100-sm-annotated.png){: .align-center}

<center><sup>위 백서 그림에 직접 주석을 덧붙였다. 큰 사각형 하나 = 처리 블록 1개, 사각형 밖 = 4개 블록이 공유하는 SM 단위 자원</sup></center>

## 처리 블록: 스케줄 경계

흔히 "CUDA 코어"를 CPU 코어 같은 독립 처리 유닛으로 생각하기 쉽지만, 실제로는 연산 파이프라인의 레인(lane) 하나에 가깝다. 실제 제어 단위는 그 위의 **처리 블록(processing block, SM sub-partition)** 이다. 블록 하나에는 다음이 들어 있다.

| 층 | 내용 | 수량 (블록당) |
| --- | --- | --- |
| 명령 | L0 Instruction Cache | 1 |
| 스케줄 | Warp Scheduler (32 thread/clk) | 1 |
| 발행 | Dispatch Unit (32 thread/clk) | 1 |
| 상태 | Register File 16,384 × 32-bit (= 64KB) | 1 |
| 연산 | INT32 레인 16 · FP32 레인 32 · FP64 레인 16 · 4세대 텐서 코어 1 | — |
| 메모리 접근 | LD/ST 8 · SFU 1 | — |

**SM 하나 = 이 블록 4개**다. 곱해 보면 SM당 FP32 CUDA 코어 128개(32×4), 텐서 코어 4개, 레지스터 256KB, 워프 스케줄러 4개가 나온다. H100 SXM은 SM이 132개니까 FP32 레인이 총 16,896개다. 워프 스케줄러·디스패치 유닛·레지스터 파일이 블록마다 하나씩이므로, **워프를 발행·실행하는 실제 제어 단위는 SM이 아니라 이 블록**이다. 워프 하나는 한 블록에 배정되면 다른 블록으로 옮겨 가지 않는다.

## SM 공유 자원: 데이터 공유 경계

주석판에서 사각형 바깥에 있는 것들 — L1 Instruction Cache, Tensor Memory Accelerator(TMA), 256KB L1 Data Cache / Shared Memory, 텍스처 유닛 — 은 4개 블록이 공유하는 SM 단위 자원이다. 사각형 밖에 있다는 사실이 중요한데, 이 때문에 경계가 둘로 나뉜다.

- **스케줄 경계 = 처리 블록**: 워프의 발행·실행은 블록 안에서 끝난다
- **데이터 공유 경계 = SM**: shared memory(온칩 SRAM)는 SM 단위라서, 같은 CUDA 블록의 스레드들이 shared memory로 협력하는 범위는 SM 전체다

FlashAttention이 "타일을 온칩에 올려 HBM 왕복을 줄인다"고 할 때의 온칩이 바로 이 SM당 256KB L1/shared다(L2는 다이 전체가 공유하는 50MB). 서빙 중 가중치가 이동하는 HBM → L2 → L1/shared → 레지스터 경로(3주차 학습 내용 [5.4편]({% post_url 2026-08-22-Dev-LLM-Serving-Optimization-05-04-LLM-Serving-Challenge-Loading-Execution-Bottleneck %}) 참고)에서, L1/shared 칸이 SM마다 하나씩 붙어 있는 셈이다.

<br>

# CUDA 코어와 텐서 코어

## 스칼라 레인과 행렬 곱셈기

두 유닛은 하는 일의 단위가 다르다.

- **CUDA 코어**: 스칼라 하나짜리 계산기. 1클럭에 `a × b + c`(FMA) 하나를 처리한다. 32개 레인이 각자 자기 원소를 맡아 동시에 도는 SIMT 구조다
- **텐서 코어**: 작은 행렬 곱셈기 통째. 명령 하나(`mma.sync`)로 행렬 타일 하나를 곱해 누적한다. 내부에 곱셈기가 격자처럼 하드와이어드로 깔려 있어, 한 명령에 수백 번의 곱셈-누적이 동시에 일어난다

숫자로 보면 H100 기준 FP32 CUDA 코어 경로가 약 67 TFLOPS, FP16 텐서 코어가 1979 TFLOPS — 같은 칩 안에서 약 30배 차이다. "레인 32개짜리 밴드"와 "블록당 1개짜리 행렬 엔진"의 차이가 이만큼이다.

## 스펙시트 CUDA Cores의 산정 범위

주의할 점은 스펙시트의 `CUDA Cores` 숫자가 연산 유닛 전체가 아니라 **FP32 레인만 센 값**이라는 것이다.

| 유닛 (블록당) | SM당 | 스펙시트 "CUDA Cores"에 포함? |
| --- | --- | --- |
| FP32 32 | 128 | 포함 — 이 숫자만 센다 |
| INT32 16 | 64 | 미포함 |
| FP64 16 | 64 | 미포함 (FP64 코어로 따로 표기) |
| Tensor Core 1 | 4 | 미포함 (Tensor Cores로 따로 표기) |
| LD/ST 8 · SFU 1 | 32 · 4 | 미포함 |

그래서 H100 SXM의 CUDA 코어 16,896개 = 128 × 132 SM = FP32 레인 수다.

## TFLOPS 분해식

이 구조를 알면 스펙표의 숫자를 검산할 수 있다. 공개 스펙 기준 어림이라 클럭 가정에 따라 오차는 있다.

```
# H100 SXM 검산 (부스트 클럭 약 1.98 GHz 가정, FMA 1회 = 2 FLOP)
FP32 (CUDA 코어):  16,896 레인 × 2 FLOP × ~1.98 GHz  ≈   67 TFLOPS   ← 표의 FP32 67
FP64:               8,448 레인 × 2 FLOP × ~1.98 GHz  ≈   34 TFLOPS   ← 표의 FP64 34
FP16 (텐서 코어):     528 TC × ~1024 MAC/clk × 2 × 클럭 ≈ 1979 TFLOPS  ← 표의 FP16 TC 1979
```

표의 두 자릿수(67, 34)는 처리 블록의 작은 레인들에서, 네 자릿수(1979, 3958)는 전부 텐서 코어에서 나온다. 같은 아키텍처인 H100 NVL의 값이 SXM보다 조금 낮은 것도 같은 식으로 설명된다 — 활성 SM 수와 클럭(전력 한도)이 깎였기 때문이다.

<br>

# 정밀도와 실행 유닛

정밀도마다 도는 유닛이 다르다. H100 SXM 기준으로 정리하면:

| 정밀도 | 도는 유닛 | 값 |
| --- | --- | --- |
| FP64 / FP32 | CUDA 코어 (FP64·FP32 레인) | 34 / 67 TFLOPS |
| TF32 · BF16 · FP16 | 텐서 코어 | 989 / 1979 / 1979 TFLOPS |
| FP8 | 텐서 코어 전용 (Hopper 4세대에서 신설) | 3958 TFLOPS |
| INT8 | 텐서 코어 (CUDA 코어에서는 DP4A 명령으로 우회 가능) | 3958 TOPS |

FP8은 CUDA 코어에 대응 레인이 없다. **텐서 코어 내부 데이터 경로가 8비트를 지원하느냐의 문제**라서, 이전 세대(A100·A10)는 FP8 지원이 아예 없다. 처리량이 FP16의 정확히 2배(1979 → 3958)인 것도 같은 유닛에서 비트 폭을 절반으로 줄여 한 클럭에 2배를 밀어넣기 때문이다. FP8은 새 유닛이 아니라 같은 유닛의 저정밀 모드다.

INT8도 마찬가지로 양자화 모델의 행렬 연산은 대부분 텐서 코어에서 처리된다. INT8을 쓴다고 유닛이 노는 것이 아니라, 가장 강력한 유닛으로 일을 몰아 주는 셈이다. 반대로 FP64 레인은 AI 추론에서 거의 100% 논다. H100 같은 데이터센터 칩에 FP64가 실린 것은 HPC(기상·시뮬레이션) 시장 때문이고, 게이밍 GPU(RTX)에서는 FP64 유닛을 1/64 비율로 깎아 버린다. 유닛 구성 자체가 그래픽/HPC/AI 워크로드 믹스에 맞춘 다이 면적 배분의 결과다.

<br>

# 명령 발행과 유닛 동시성

INT32·FP32·FP64가 "서로 다른 코어"가 아니라 같은 블록 안의 서로 다른 파이프라인이라는 점은 발행 방식에서 드러난다. 워프 스케줄러는 1클럭에 명령어 하나를 골라 해당 타입의 유닛 묶음으로 보낸다. 32스레드 워프를 16개짜리 INT32 레인에 태우면 2클럭이 걸리는데, 발행한 다음 클럭에 스케줄러는 자유로워져서 다른 파이프라인(FP32, FP64)으로 별개 명령을 발행할 수 있다. "INT32를 쓰는 동안 FP64가 완전히 막힌다"가 아니라 **클럭 단위로 번갈아 발행된다**가 정확한 표현이다.

그렇다고 모든 유닛이 동시에 도는 것은 아니다. 전력 한계 때문에 100% 동시 가동은 불가능하고, 설계도 그것을 전제하지 않는다. 정확히 말하면 **모든 유닛이 동시에 돌지는 못하지만, 겹칠 수 있는 조합은 정해져 있다.** 대표 조합이 FP32 + INT32다.

- Pascal 세대까지는 FP32와 INT32가 같은 유닛을 공유했다. `a[i] * b[i]` 한 줄에서도 인덱스 `i`를 구하는 INT 연산과 곱셈인 FP32 연산이 같은 자리를 놓고 경쟁했고, 주소 계산이 FP32 처리량을 잠식했다
- Turing 세대부터 FP32와 INT32를 별도 파이프라인으로 분리했다. 워프 스케줄러가 같은 사이클 창에서 FP32 명령과 INT 명령을 각각 다른 파이프라인으로 동시에 발행할 수 있게 되어, 루프 카운터·인덱싱이 실수 연산 성능을 깎지 않는다. NVIDIA는 Turing 백서에서 실제 셰이더 워크로드 기준 FP32 명령 100개당 INT 명령이 평균 약 36개 섞여 나온다고 밝혔다 — 분리만으로 이만큼을 겹칠 수 있게 된 것이다

서빙 관점에서 이 겹침이 이득을 주는 구간은 softmax·LayerNorm·RoPE·샘플링 같은 비(非)행렬곱 연산이다. 행렬 곱은 텐서 코어에서 돌기 때문에 이 이야기의 바깥에 있다.

<br>

# 서빙 관점의 함의

이 구조 지식이 실무 판단과 닿는 지점을 모아 둔다.

- **CUDA 코어 수는 서빙 지표가 아니다.** 어텐션·MLP의 행렬 곱은 전부 텐서 코어에서 돈다. CUDA 코어(FP32/INT32 레인)가 맡는 것은 softmax, LayerNorm/RMSNorm, RoPE, element-wise, 샘플링 같은 연산인데, 이들은 로드하는 데이터 대비 연산량이 적어 산술 강도가 낮고 전체 비중도 작다. GPU를 고를 때는 정밀도별 텐서 코어 TFLOPS를 본다 (3주차 학습 내용 [5.2편]({% post_url 2026-08-22-Dev-LLM-Serving-Optimization-05-02-LLM-Serving-Challenge-GPU-Compute-Memory %}))
- **wave quantization**: GEMM은 출력 행렬을 타일(tile)로 쪼개 SM들에 뿌리고, 한 번에 SM 수만큼 깔리는 라운드를 wave라 부른다. 타일 수가 SM 수의 배수가 아니면 마지막 wave에서 SM 대부분이 논다. 132 SM에 타일이 133개면 두 번째 wave가 거의 비어 실효 성능이 절반으로 떨어진다. 배치 크기·TP 분할이 어중간할 때 나타나는 계단 현상의 정체다
- **MIG/MPS의 분할 단위**: MIG는 SM과 L2를 물리적으로 쪼개 나눠 주는 기능이라, 파티션 경계가 곧 SM 경계다
- **nvidia-smi utilization의 함정**: `nvidia-smi`의 GPU utilization은 "SM에서 커널이 하나라도 돌고 있던 시간의 비율"이다. decode처럼 memory bandwidth-bound인 구간에서는 커널이 SM 전체에 깔려 있어도 각 SM이 시간 대부분을 HBM 대기(stall)로 보내는데, 이때도 utilization은 100%로 찍힌다. 일부 SM만 일하는 것이 아니라, 떠 있는 SM들이 기다리고 있는 상태다. 이 지표의 함정은 [GPU 팬텀 사용률]({% post_url 2026-05-11-Dev-GPU-Phantom-Utilization %})에서 따로 다뤘고, 진짜 판별은 [Roofline 모델]({% post_url 2026-08-21-CS-Roofline-Model %})의 실측 절처럼 달성 대역폭을 봐야 한다

<br>

# 정리

스펙표를 다시 읽는 법으로 정리한다.

- CUDA Cores 16,896 → FP32 레인 수(128 × 132 SM). 서빙 판단에는 쓰지 않는다
- FP16 Tensor Core 1979 TFLOPS → 528개 텐서 코어의 행렬 엔진 처리량. LLM 서빙의 연산 상한은 이 행이다
- FP8 3958 → 같은 텐서 코어의 저정밀 모드. 세대가 지원하는지(Hopper 이후)만 확인하면 된다
- 실효 성능이 이론값에 못 미치는 이유의 상당 부분 — wave quantization, memory-bound 구간의 SM stall — 도 SM 구조 위에서 설명된다

<br>

# 참고 링크

- [NVIDIA H100 (Hopper) Architecture Whitepaper](https://resources.nvidia.com/en-us-tensor-core/gtc22-whitepaper-hopper)
- [NVIDIA Turing Architecture Whitepaper](https://images.nvidia.com/aem-dam/en-zz/Solutions/design-visualization/technologies/turing-architecture/NVIDIA-Turing-Architecture-Whitepaper.pdf)
- [NVIDIA Ampere Architecture In-Depth (Developer Blog)](https://developer.nvidia.com/blog/nvidia-ampere-architecture-in-depth/)
- [LLM 서빙의 도전 과제 - 5.2. GPU 스펙 읽기: 연산과 메모리]({% post_url 2026-08-22-Dev-LLM-Serving-Optimization-05-02-LLM-Serving-Challenge-GPU-Compute-Memory %})
- [Roofline 모델: 연산 강도로 판별하는 성능 병목]({% post_url 2026-08-21-CS-Roofline-Model %})
- [GPU 팬텀 사용률]({% post_url 2026-05-11-Dev-GPU-Phantom-Utilization %})

<br>
