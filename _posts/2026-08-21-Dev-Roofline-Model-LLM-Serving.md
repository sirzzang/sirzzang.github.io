---
title: "[Performance] Roofline 모델로 보는 LLM 서빙: 세 점으로 나눠 찍는 병목"
excerpt: "Roofline 모델을 LLM 서빙 워크로드에 세 점으로 나눠 찍고, 실제 서빙에 적용해 그래프를 그려 보자."
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
  - vLLM
  - MoE
  - Hands-On-LLM-Serving-and-Optimization-Study
  - Hands-On-LLM-Serving-and-Optimization-Study-Week-3
last_modified_at: 2026-08-24
---

*[서종호(가시다)](https://www.linkedin.com/in/gasida99/)님의 Hands-On LLM Serving and Optimization Study (LLMSO) 3주차 학습 중 딥다이브한 내용입니다.*

<br>

# TL;DR

- LLM 서빙 워크로드는 루프라인에 최소 세 점으로 나눠 찍어야 한다. prefill은 연산 바운드, decode-FFN은 $I \approx B$라 배칭으로 사선을 벗어날 수 있지만, decode-attention은 KV 캐시가 요청마다 달라 배칭으로도 움직이지 않는다
- decode-FFN의 연산 강도는 배치 크기와 같다($I \approx B$). H100의 ridge point가 $\approx 295$ FLOP/byte이므로 배치가 수백 규모가 되어야 연산 바운드로 넘어가고, batch=1이면 7B FP16 기준 이론 상한이 $\approx 240$ tok/s로 대역폭이 직접 결정한다
- prefill과 decode는 다른 지표로 평가해야 한다. prefill의 성적표는 MFU·텐서코어 활용률, decode의 성적표는 달성 대역폭이다
- 최적화 기법은 "점을 어느 방향으로 옮기는가 / 지붕을 어떻게 바꾸는가"로 정리된다. INT4 같은 $Q$ 절감은 저배치(메모리 바운드)에서만 듣고, 고배치에서는 오히려 느려질 수 있다
- 실제 서빙 워크로드에 적용해 보면 두 점은 정말 반대편에 찍힌다. decode는 배치를 키울수록 대역폭 지붕에 붙어 지붕의 39% → 88%로 올라가고, prefill은 ridge 오른쪽에 놓인다
- 다만 교과서 값이 그대로 나오지는 않는다. MoE 모델에서는 $I \approx B$가 성립하지 않고(배치 16배에 강도 3.4배), ridge 오른쪽이라고 빠른 것도 아니다 — 실측 prefill은 연산 지붕의 12%만 쓴다

<br>

# 배경

[Roofline 모델]({% post_url 2026-08-21-CS-Roofline-Model %})에서 모델 자체를 정리했다 — 성능 상한 $P = \min(\pi, \beta I)$, 연산 강도 $I = W/Q$, 그리고 점이 [ridge point]({% post_url 2026-08-21-CS-Roofline-Model %}#ridge-point) 왼쪽이면 메모리 바운드, 오른쪽이면 연산 바운드라는 판정 규칙까지. 이 글은 그 틀을 LLM 서빙 워크로드에 실제로 적용한다. prefill/decode의 실행 구조 자체는 [LLM 서빙과 최적화 3.3편]({% post_url 2026-08-14-Dev-LLM-Serving-Optimization-03-03-LLM-Serving-Prefill-Decode %})에서 다뤘다.

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

- **decode-FFN의 강도가 배치 크기와 같아지는 이유**: FP16 가중치 원소 하나(2 byte)에 곱 1 + 합 1 = 2 FLOP이므로 배치 1에서 $I = 2/2 = 1$ FLOP/byte다. 배치가 $B$면 그 원소를 $B$번 재사용하니 $I \approx B$로 올라간다. 즉 배치 크기가 그대로 연산 강도가 된다. 다만 이 값은 **가중치 한 벌을 배치 전체가 나눠 쓴다**는 전제 위에 있다 — MoE에서 그 전제가 어떻게 깨지는지는 [실측](#배치와-강도)에서 확인한다
- 그런데 ridge는 A100 $\approx 153$, H100 $\approx 295$다(둘 다 SXM·sparsity 미적용 기준). **배치가 300 근처가 되어야 겨우 연산 바운드로 넘어간다.** 배치 1이면 H100 지붕의 $1/295 \approx 0.3\%$밖에 못 쓴다. "H100인데 왜 이렇게 느린가"의 답이 이 한 줄에 전부 있다
- **decode-attention은 배칭으로 나아지지 않는다.** 요청이 $B$개면 KV도 $B$세트를 읽어야 하므로 $W$와 $Q$가 나란히 $B$배가 되고, 비율은 그대로다. GQA/MQA(KV 헤드 수를 줄여 KV 트래픽을 낮추는 어텐션 변형), KV 양자화, paged KV가 배칭과 **별개로** 필요한 이유가 여기에 있다
- 그래서 프로파일할 때도 커널을 한 점으로 뭉치지 말고 세 점으로 나눠 찍어야 한다. 한 덩어리로 보면 FFN의 개선이 attention의 정체를 가리거나 그 반대가 된다

## H100 숫자로 확인

이 구도를 H100 숫자로 직접 확인해 보면($\pi \approx 990$ TFLOP/s BF16(SXM, sparsity 미적용), $\beta \approx 3.35$ TB/s → $I^{*} \approx 295$ FLOP/byte) 이렇게 된다.

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
| **decode** | 대역폭 | 사선 | 달성 대역폭 (`dram__bytes_*`, 프록시로 `DRAM_ACTIVE`) | 배칭, 양자화, KV 캐시 관리 |

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

> **자주 나는 오판: INT4가 처리량을 올려 줄 것이라고 기대하는 것.** 고배치에서는 이미 점이 수평 지붕 쪽으로 넘어가 있으므로 $Q$를 줄여도 상한이 오르지 않고, dequant 오버헤드($W$ 증가)만 붙어서 오히려 느려질 수 있다. **저지연(저배치) 최적화와 고처리량(고배치) 최적화는 서로 다른 지붕을 상대하는 작업이다.** [Roofline 모델의 2단 판단]({% post_url 2026-08-21-CS-Roofline-Model %}#2단-판단)의 순서를 그대로 쓰면 된다 — 지금 점이 어떤 지붕에 붙었는지를 밝힌 다음에야 기법을 고를 수 있다.

<br>

# 실측

여기까지가 틀이고, 이제 실제 워크로드에 적용해 본 결과다. 대상은 본문 예시와 다른 조합이다 — H100·7B dense FP16이 아니라 **RTX 5090 1장 위의 MoE(Mixture of Experts — 토큰마다 전체 가중치 중 일부 전문가만 골라 쓰는 구조) 모델**(Qwen3.6-35B-A3B의 NVFP4 양자화본, vLLM 서빙)이다. 선형 어텐션과 full attention을 섞은 구조라 요청마다 별개인 항에 KV 캐시 말고 recurrent state도 있다. 조합이 다른 쪽이 오히려 세 점 틀이 그대로 쓰이는지를 보기에 낫다.

## 측정 방법

프로파일러로 잰 값이 아니다. Nsight Compute는 가동 중인 서빙 프로세스에 붙이기 어렵고, DCGM의 프로파일링 지표(`DCGM_FI_PROF_*`)는 GeForce 계열이 대상 밖이라 [Roofline 모델]({% post_url 2026-08-21-CS-Roofline-Model %}#측정)에서 정리한 `dram__bytes_*` · `DRAM_ACTIVE` 경로를 쓸 수 없었다.

그래서 **실측한 것은 넷뿐**이다 — 엔진 카운터에서 읽은 step 수와 토큰 수, 창의 벽시계 시간, 그리고 마이크로벤치마크로 잰 지붕. 강도와 달성 성능은 모델 config로 계산한 FLOP·바이트에 그 step 수를 곱해 냈다. 따라오는 한계가 셋 있다.

- **$I$는 이론 $I$다.** [Roofline 모델의 두 $I$ 구분]({% post_url 2026-08-21-CS-Roofline-Model %}#이론-i-vs-실측-i)에서 손으로 세는 쪽, 즉 캐시 재사용을 가정한 compulsory 값에 가깝다. 실측 DRAM 트래픽이 아니다
- **달성 대역폭은 계산한 바이트를 실측 step 시간으로 나눈 값이다.** 바이트 계산이 틀리면 좌표도 같이 틀린다
- **decode를 FFN과 attention으로 쪼개지 않고 한 점으로 찍었다.** [세 점](#세-점으로-나누기) 중 둘을 합친 셈이다

즉 이 좌표는 정밀 측정이 아니라 **자릿수를 가리는 스케치**로 두는 편이 적절하다. 아래 판정은 그 해상도에서 성립하는 것들이다.

부하 자체는 기존 부하 테스트 하네스(locust)로 걸었다. 출력 길이(`ignore_eos`로 고정)·입력 길이·동시성을 고정하고, decode 창과 prefill 창이 섞이지 않도록 두 런으로 나눴다 — decode는 짧은 프롬프트에 출력 4,096 토큰, prefill은 긴 프롬프트에 출력 1 토큰이다.

<details markdown="1">
<summary><b>참고: 실측·작도 코드</b></summary>

*본문 이해엔 필수가 아니다. 위 좌표를 어떻게 냈는지의 실제 코드다.*

**① 지붕 측정.** 사선(대역폭)은 STREAM scale을 1버퍼 in-place로 변형한 것, 수평(연산)은 정사각 GEMM으로 잰다. 여기서 제일 중요한 것은 **버퍼 크기**다 — L2보다 작으면 DRAM이 아니라 캐시 대역폭이 찍혀 지붕이 몇 배로 부푼다. [STREAM 런 규칙](https://www.cs.virginia.edu/stream/ref.html)이 배열을 마지막 레벨 캐시 합의 **4배 이상**으로 잡으라고 하는 이유가 이것이고, 그 문턱을 넉넉히 넘기려고 2 GiB로 잡았다.

```python
import time
import torch

WORKSET_MIB = 2048   # 버퍼 1개. 문턱은 LLC 의 4배 — RTX 5090 L2(96 MiB) 기준 21배로 넉넉하다
GEMM_N = 4096        # 4096^3 GEMM 의 FLOP 은 2*N^3 으로 확정적이다


def timed(fn, warmup=3, iters=20):
    # 커널 하나가 아니라 반복 구간 전체를 동기화 후 벽시계로 잰다
    for _ in range(warmup):
        fn()
    torch.cuda.synchronize()
    t0 = time.perf_counter()
    for _ in range(iters):
        fn()
    torch.cuda.synchronize()
    return (time.perf_counter() - t0) / iters


def bandwidth_gbs():
    # STREAM scale 변형(1버퍼 in-place) — 하나를 읽어 같은 자리에 쓴다. 이동 바이트는 2 x size 인데
    # VRAM 은 size 만 쓴다. mul_(1.0) 은 항등이라 구현이 건너뛸 여지가 있어 add_ 를 쓴다
    a = torch.zeros(WORKSET_MIB * 1024**2 // 2, dtype=torch.bfloat16, device="cuda")
    dt = timed(lambda: a.add_(1.0))
    return 2 * a.numel() * a.element_size() / dt / 1e9


def gemm_tflops(dtype):
    # BF16 전용. torch.matmul 은 fp8 을 못 받아서 FP8 은 torch._scaled_mm 로 따로 쟀다
    # (그 호출의 use_fast_accum 이 FP32 누산이냐 FP16 누산이냐를 가른다)
    a = torch.randn(GEMM_N, GEMM_N, device="cuda", dtype=torch.bfloat16).to(dtype)
    b = torch.randn(GEMM_N, GEMM_N, device="cuda", dtype=torch.bfloat16).to(dtype)
    dt = timed(lambda: torch.matmul(a, b))
    return 2 * GEMM_N**3 / dt / 1e12
```

가동 중인 GPU에서는 이 측정이 안 된다. 서빙 엔진이 KV 캐시를 미리 잡아 여유 VRAM이 수십 MiB뿐이라 2 GiB 버퍼를 못 잡고, 억지로 줄이면 그 버퍼가 L2 안에 들어앉는다. 대상 GPU를 잠깐 내리고 쟀다.

**② 좌표 계산.** 엔진 카운터를 창 단위로 잘라 step 수와 배치를 얻고, 거기에 config로 계산한 바이트·FLOP을 곱한다.

```python
# ── 창 단위 델타 → step 수 · 배치 · prefill 비율 ────────────────────────
# iteration_tokens_total_count 의 증분이 engine step 수 원본이라,
# 배치를 "tok/s 를 무언가로 나눠" 추정할 필요가 없다
d_iter = b["iter_count"] - a["iter_count"]            # 창 안의 step 수
d_gen = b["gen_tokens"] - a["gen_tokens"]             # 생성(decode) 토큰
d_prompt = b["prompt_tokens"] - a["prompt_tokens"]    # 프롬프트(prefill) 토큰

batch = d_gen / d_iter                                # step 당 배치 — 실측값이다
steps_s = d_iter / dt
prefill_frac = d_prompt / (d_prompt + d_gen)          # 0.05 미만이면 decode 창으로 채택


# ── step 당 이동 바이트 — 항별로 낸다 ──────────────────────────────────
def expert_touch_fraction(n_tok):
    """step 당 실제로 읽히는 routed expert 비율.

    토큰마다 독립적으로 top-k 를 고른다고 보고 충돌을 센다. dense 모델이면
    이 항 자체가 없고(항상 전량 읽는다), 그래서 I ~= B 가 성립한다.
    """
    return 1.0 - (1.0 - TOPK / N_EXPERT) ** n_tok


def bytes_per_step(n_tok, n_req, ctx_len):
    # 총합만 맞추면 반대 방향 오차 둘이 상쇄돼도 모른다. 그래서 항을 쪼개 둔다
    return {
        "routed_experts": EXPERT_BYTES * expert_touch_fraction(n_tok),  # 배치 의존
        "kv_read": n_req * ctx_len * KV_BYTES_PER_TOKEN,                # 요청 수 의존
        "lm_head": VOCAB * D_MODEL * BYTES_PER_PARAM,                   # 매 step 전량
        # attention/projection 등 상주 가중치 항이 이어진다
    }


# ── 좌표 ───────────────────────────────────────────────────────────────
intensity = flops_step / bytes_step        # x축. 둘 다 계산값이라 이것이 "이론 I" 다
achieved_tflops = flops_step * steps_s / 1e12   # y축
achieved_gbs = bytes_step * steps_s / 1e9       # 달성 대역폭
```

**③ 자체 점검.** 계산이 깨졌으면 좌표를 보기 전에 멈춰야 한다. 앵커는 전부 독립 출처와 대조되는 값으로 골랐다.

```python
# 토큰당 FLOP 이 2 x 활성 파라미터(A3B 이므로 약 6 GFLOP)와 맞아야 한다
assert 5.0 < per_token_gflop < 7.0
# 상주 가중치 합이 실측 VRAM 점유(23.25 GiB) 아래여야 한다
assert 20.0 < weight_gib < 23.25
# recurrent state 크기가 KV 예산에서 역산한 값과 같은 자릿수여야 한다
assert 50 < state_mb_per_req < 100
# 강도가 배치에 대해 증가하되, f(B) 포화 때문에 선형이면 안 된다
assert i_b8 < i_b16 and i_b16 / i_b8 < 2.0
# 두 단계가 반대편에 찍히는지 — 이게 무너지면 부하 설정이 잘못된 것이다
assert i_prefill > 10 * i_b16
```

**④ 작도.** 사선과 수평을 `min()`으로 잇는 한 줄이 곧 $P = \min(\pi, \beta I)$다.

```python
# 사선(대역폭 x 강도)과 수평(연산 peak) 중 낮은 쪽이 그대로 지붕이 된다
ax.plot(xs, [min(BW_ROOF / 1000 * x, TOP_ROOF) for x in xs], "k-", lw=1.5)
for name, v in ROOFS:                      # 정밀도별 수평 지붕을 점선으로 겹쳐 그린다
    ax.axhline(v, ls="--", lw=1, alpha=0.6)

# 마커 크기에 배치를 실어 "배치를 키우면 점이 어디로 가나"를 한 장에 담는다
ax.scatter(intensities, tflops, s=[8 + 4 * b for b in batches], alpha=0.7)

ax.set_xscale("log")   # 양축 로그라야 사선이 직선으로 보이고 자릿수 비교가 된다
ax.set_yscale("log")
```

</details>

## 지붕과 좌표

두 점이 반대편에 찍혔다.

지붕부터 실측하면 이렇다. [명판은 이론 최대치라 실제로는 80~90%만 나온다]({% post_url 2026-08-21-CS-Roofline-Model %}#π와-β의-출처)고 했던 그 범위 안이다.

| 지붕 | 스펙 | 실측 | 스펙 대비 | ridge point |
| --- | --- | --- | --- | --- |
| HBM 대역폭 | 1,792 GB/s | **1,525 GB/s** | 85% | — |
| BF16 텐서 (FP32 누산) | 209.5 TFLOP/s | **210.4 TFLOP/s** | 100% | 138 FLOP/byte |
| FP8 텐서 | 419 (FP32 누산) / 838 (FP16 누산) | **498.0 TFLOP/s** | 59% (FP16 누산 기준) | 327 FLOP/byte |
| FP4 텐서 | 1,676 TFLOP/s | 996 (FP8 실측 × 2 **유도값**) | 59% | 653 FLOP/byte |

스펙은 [NVIDIA RTX Blackwell GPU Architecture 백서](https://images.nvidia.com/aem-dam/Solutions/geforce/blackwell/nvidia-rtx-blackwell-gpu-architecture.pdf) Appendix A의 GB202(RTX 5090) 열이고, 전부 sparsity를 쓰지 않은 dense 값이다. ridge point는 스펙이 아니라 실측 지붕끼리 나눈 값이다.

**BF16 실측이 스펙과 오차 범위 안에서 겹쳤다** — 타이밍이나 FLOP 계산이 크게 틀렸으면 여기서 어긋난다. 다만 명판의 100%가 나왔다는 것은 클럭이 명판 부스트 위에서 돌았다는 뜻이기도 해서, 계산이 대충 맞다는 확인이지 지붕 값이 정확하다는 보증은 아니다.

FP8은 읽는 법이 하나 더 있다. 백서가 FP8 텐서 성능을 **누산 정밀도에 따라 둘로 나눠** 적는데(FP32 누산 419, FP16 누산 838), 실측 498이 그 사이에 떨어졌다. FP32 누산 열을 상한으로 보면 나올 수 없는 값이므로, `torch._scaled_mm`이 FP16 누산 경로로 붙었다고 보는 편이 앞뒤가 맞는다 — 그러면 498은 838의 59%다. 두 경로를 가르는 것은 그 호출의 `use_fast_accum` 플래그인데, 이번 측정에서는 확인하지 않았다.

**FP4 지붕 996은 그 위에 얹힌 유도값이다.** FP16 누산 FP8(838)에서 FP4(1,676)로 가는 백서 배율이 2배라 실측을 2배 했고, 결과가 스펙 1,676의 59%로 FP8 쪽과 같은 비율이 나온다. 가정이 어긋나지 않았다는 방증이지 검증은 아니다. 그래서 뒤에서 "연산 지붕의 몇 %"를 읽을 때는 이 값을 분모로 쓰지 않고 실측이 확인된 BF16 지붕을 쓴다.

![RTX 5090 위 vLLM MoE 모델의 roofline 실측 차트]({{site.url}}/assets/images/roofline-measured-vllm-rtx5090.png){: .align-center}

<center><sup>직접 측정. 원자료는 <a href="{{site.url}}/assets/data/roofline-points.csv">roofline-points.csv</a> — 목표 배치에서 벗어난 창은 작도·집계에서 뺐다</sup></center>

그림에서 읽는 것은 넷이다.

- **decode(파란 원)는 사선을 따라 오른쪽 위로 간다.** 마커가 커질수록(배치가 커질수록) 강도와 성능이 같이 오르는데, 그 이동이 사선 위에서 일어난다. 사선까지의 세로 거리가 못 쓴 대역폭이다 — B=1은 눈에 띄게 아래고(지붕의 39%), B=16은 거의 붙는다(88%)
- **prefill(주황 세모)은 ridge 오른쪽인데 수평 지붕에서 한참 아래다.** 사선에도 수평선에도 닿지 않은 점이라, 두 축 어느 쪽도 병목이 아니라는 뜻이다
- **꺾임(ridge 653)이 두 무리 사이에 놓인다.** 같은 모델·같은 가중치·같은 코드인데 x축으로 두 자릿수 넘게 벌어져 있다. prefill과 decode를 한 점으로 뭉치면 안 되는 이유가 그림 하나로 보인다
- **y축만 보면 prefill이 더 높다** (25 vs 10 TFLOP/s 수준). 그런데 지붕 대비로는 decode가 88%, prefill이 12%다. 상대하는 지붕이 다르기 때문이고, [평가 지표](#평가-지표)에서 두 단계를 같은 숫자로 나란히 놓지 말라고 한 것이 이 모양이다

숫자로는 이렇다. GPU 1장, 문맥 약 2,200 토큰 기준이고, $B$는 반올림 라벨이라 실측 평균 배치와 소수점에서 조금 다르다(B=2 행이 2.05라 `tok/s = B / step ms`로 재현하면 이 행만 어긋난다).

| $B$ | 출력 tok/s | step ms | 강도 | 달성 대역폭 | 지붕 대비 |
| --- | --- | --- | --- | --- | --- |
| 1 | 221 | 4.52 | 2.2 | 588 GB/s | 39% |
| 2 | 366 | 5.61 | 3.4 | 628 GB/s | 41% |
| 4 | 649 | 6.16 | 4.7 | 816 GB/s | 53% |
| 8 | 1,093 | 7.31 | 5.9 | 1,078 GB/s | 71% |
| 12 | 1,299 | 9.23 | 6.7 | 1,137 GB/s | 75% |
| 16 | 1,696 | 9.44 | 7.4 | 1,338 GB/s | 88% |

prefill은 프롬프트 9,649 토큰 기준으로 강도 **1,677**, 달성 연산 25 TFLOP/s, 달성 대역폭 15 GB/s다.

## 배치와 강도

강도가 배치만큼 오르지 않았다. 배치는 16배인데 강도는 2.2 → 7.4로 **3.4배**뿐이다.

[세 점 표](#세-점으로-나누기)의 $I \approx B$는 가중치 한 벌을 배치 전체가 나눠 쓴다는 전제 위의 값인데, MoE에서는 그 전제가 성립하지 않는다. 토큰마다 고르는 전문가가 다르므로 **배치가 커지면 읽어야 할 전문가 수도 같이 는다.** 전문가 256개에서 토큰마다 8개를 고른다고 보면 step 당 읽히는 전문가 비율은 $1 - (1 - 8/256)^B$이고, $B=1$에 3.1%, $B=16$에 39.8%다. $Q$가 상수로 남지 않고 함께 커지니 비율의 상승이 꺾인다.

이 식은 토큰마다 라우팅이 독립이고 전문가가 고르게 뽑힌다는 가정 위에 있고, 그 가정에서 접촉 비율의 **상한**이다. 실제 라우팅이 한쪽으로 몰리면 읽히는 전문가는 이보다 적어지므로 실제 강도는 더 높고, 앞의 "지붕의 88%"는 그만큼 낙관값이다. $B=1$에서는 식이 정확하고 배치가 커질수록 벌어진다.

그러니 $I \approx B$는 dense 모델 이야기로 읽어야 한다. **처방의 방향은 그대로다** — 배칭이 점을 오른쪽으로 민다는 것도, ridge를 넘으려면 배치가 수백은 되어야 한다는 것도 여전하다. 다만 MoE에서는 같은 배치로 얻는 이동 폭이 작고, 그만큼 배칭만으로 사선을 벗어나기가 dense보다 어렵다.

## ridge 오른쪽과 실제 성능

prefill은 ridge 오른쪽인데 연산 지붕의 12%만 쓴다. 강도 1,677은 ridge 653의 2.6배 오른쪽이라 분류상 연산 바운드 영역인데, 달성은 25 TFLOP/s로 BF16 실측 지붕(210.4)의 12%다. 유도 FP4 지붕이 분모면 2.5%지만 그쪽은 앞서 적은 불확실성이 있으므로 실측 지붕 기준으로 읽는 편이 안전하다. 대역폭 쪽도 15 GB/s로 지붕의 1%다.

다만 "2.6배 오른쪽"의 ridge 653과 "12%"의 분모 210.4는 서로 다른 지붕에서 나온 값이다. BF16 지붕으로 통일하면 ridge는 138이고 prefill은 12배 오른쪽이 되는데, 어느 쪽으로 그리든 ridge 오른쪽이라는 판정도 지붕에 못 닿았다는 판정도 바뀌지 않는다.

**어느 지붕에도 닿지 않았다.** roofline이 말해 주는 것은 *어느 지붕을 상대하는가*이지 *그 지붕에 닿았는가*가 아니다. [Roofline 모델의 2단 판단]({% post_url 2026-08-21-CS-Roofline-Model %}#2단-판단)에서 1단(점이 지붕에 붙었나)에 걸리는 사례이고, 이때 roofline이 해 주는 일은 처방이 아니라 **배제**다 — 양자화도 배칭도 답이 아니라는 것까지가 이 그림이 말할 수 있는 전부다. 왜 12%인지는 이 측정으로 알 수 없고, 커널 단위 프로파일이 따로 필요하다.

<br>

# 정리

LLM 서빙 워크로드는 한 덩어리가 아니다. prefill(연산 바운드), decode-FFN($I \approx B$, 배칭으로 이동 가능), decode-attention(KV 캐시 탓에 배칭으로도 고정) — 이 세 점을 나눠 찍어야 배칭이 듣는 부분과 안 듣는 부분이 구분되고, 그다음에야 기법을 고를 수 있다. 판단 순서는 루프라인의 일반 규칙 그대로다: 점이 지붕에 붙었는지 먼저, 붙었다면 어느 지붕인지 — 그 답이 처방을 결정한다.

실제로 찍어 보면 두 점은 정말 반대편에 놓인다. 다만 교과서 값이 그대로 나오지는 않는다 — MoE에서는 $I \approx B$가 무너지고, ridge 오른쪽에 있으면서도 지붕에 닿지 못하는 점이 생긴다. 판정 규칙 자체는 그대로 쓰이되, 그 규칙이 답해 주는 범위는 어느 지붕을 상대하는가까지다.

<br>

# 참고 링크

- [Roofline 모델: 연산 강도로 판별하는 성능 병목]({% post_url 2026-08-21-CS-Roofline-Model %})
- [Williams, Waterman, Patterson, "Roofline: An Insightful Visual Performance Model for Multicore Architectures", CACM 2009](https://escholarship.org/content/qt78h8v7mr/qt78h8v7mr.pdf)
- [LLM Inference Unveiled: Survey and Roofline Model Insights (arXiv:2402.16363)](https://arxiv.org/abs/2402.16363)
- [LLM 서빙과 최적화 3.3편 — prefill과 decode]({% post_url 2026-08-14-Dev-LLM-Serving-Optimization-03-03-LLM-Serving-Prefill-Decode %})
- [LLM 서빙과 최적화 3.2편 — 배치 요청]({% post_url 2026-08-14-Dev-LLM-Serving-Optimization-03-02-LLM-Serving-From-Scratch-Batch-Request %})

<br>
