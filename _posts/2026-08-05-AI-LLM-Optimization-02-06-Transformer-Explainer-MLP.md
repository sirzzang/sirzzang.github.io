---
title: "[LLM] LLM 서빙과 최적화 - 2.6. Transformer: MLP와 트랜스포머 블록 마무리"
excerpt: "어텐션이 모아 온 정보를 토큰별로 비선형 가공하는 MLP 서브레이어에 대해 알아 보자."
categories:
  - AI
hidden: true
toc: true
header:
  teaser: /assets/images/blog-AI.jpg
tags:
  - Transformer
  - Transformer-Explainer
  - GPT-2
  - MLP
  - FFN
  - GELU
  - Up-Projection
  - Down-Projection
  - Hands-On-LLM-Serving-and-Optimization-Study
  - Hands-On-LLM-Serving-and-Optimization-Study-Week-1
last_modified_at: 2026-08-22
---

*[서종호(가시다)](https://www.linkedin.com/in/gasida99/)님의 Hands-On LLM Serving and Optimization Study (LLMSO) 1주차 학습 내용을 기반으로 합니다.*

<br>

# TL;DR

- 트랜스포머 블록의 두 번째 서브레이어인 MLP(=FFN)는 [1편]({% post_url 2026-08-05-AI-LLM-Optimization-01-AI-Overview %})에서 본 "선형층 + 활성화 함수" 구조 그대로다. GPT-2 small 기준 768 → 3072(GELU) → 768 — 셀프 어텐션이 모아 온 문맥 정보를 **토큰별로 비선형 가공**한다
- 어텐션이 이미 문맥을 섞었는데도 MLP가 또 필요한 이유는, 어텐션의 연산이 토큰별 관점에서는 (거의) 선형 결합이기 때문이다. 블록의 분업은 **어텐션 = 어디서 정보를 모을까(토큰 간 통신), MLP = 모은 정보로 무엇을 계산할까(토큰별 가공)**다
- GELU는 ReLU의 "0에서 딱 자르는 게이트"를 부드럽게 만든 활성화 함수다. 음수 구간에도 0이 아닌 기울기가 남아 뉴런이 죽지 않고, 전 구간 미분 가능해 최적화가 안정적이라는 이점이 경험적으로 보고되어 GPT 계열이 채택했다
- GPT-3 파라미터의 약 2/3는 MLP에 있다. 특별한 이유가 있어서가 아니라 은닉 차원을 4배로 잡은 설계에서 나오는 단순 계산 결과다 — 레이어당 어텐션 사영은 $4d^2$, MLP는 $2 \times d \times 4d = 8d^2$로 정확히 2배. 파라미터는 많지만 병렬화는 오히려 가장 잘 된다. MLP는 토큰 간 완전 독립인 거대 행렬곱이라 트랜스포머에서 가장 GPU 친화적인 구간이다
- 서빙 관점에서 MLP에는 KV cache가 없다. 대신 decode 단계에서 매 토큰 읽어야 하는 모델 가중치의 2/3가 MLP 몫이고, 텐서 병렬화의 표준 분할 축이며, MoE가 희소화하는 대상이다

<br>

# MLP 서브레이어: 어텐션이 하지 않은 일

[앞 글]({% post_url 2026-08-05-AI-LLM-Optimization-02-05-Transformer-Explainer-Self-Attention %})에서 셀프 어텐션의 계산을 끝까지 따라갔고, 출력 사영 $W^O$를 통과한 `(seq_len, 768)`이 블록의 두 번째 서브레이어인 MLP로 넘어간다는 데까지 왔다. Transformer Explainer의 소개는 이렇다.

> The attention output goes through an MLP to refine token representations. A Linear layer changes embedding values and size using learned weights and bias, then a non-linear decides how much each value passes.

**MLP는 새로운 구조가 아니다.** [1편]({% post_url 2026-08-05-AI-LLM-Optimization-01-AI-Overview %})에서 "완전연결층(선형변환)을 쌓고 사이에 활성화 함수를 끼운 것"으로 정리했던 바로 그 MLP이고, [1편 말미]({% post_url 2026-08-05-AI-LLM-Optimization-01-AI-Overview %}#mlp와-딥러닝)에 *"Transformer 안에서도 어텐션과 번갈아 끼는 FFN(feed-forward network) 블록이 정확히 이 '선형층 + 활성화' 구조"*라고 예고해 뒀던 지점이 여기다. FFN과 MLP는 같은 것을 가리키는 두 이름이다 — 원 논문은 position-wise feed-forward network라 부르고, GPT-2 구현과 Transformer Explainer는 MLP라 부른다. 이 글에서는 MLP로 통일한다.

> *참고*: feed-forward라는 이름
>
> feed-forward는 네트워크의 **연결 구조(위상)**를 가리키는 분류 용어다. 신호가 **입력에서 출력 한 방향으로만** 흐르고, 출력이 **자기 자신이나 앞 층으로 되돌아가는 순환 연결이 없다**는 뜻 — "앞으로만 보낸다"는 독법이 맞고, RNN(recurrent neural network)과 대비되는 자리에 놓인 이름이다. 반면 MLP는 그 feed-forward 네트워크 가운데 "완전연결층 + 활성화를 쌓은 구조"라는 **구체적 생김새**를 가리킨다 — CNN도 feed-forward지만 MLP는 아니다. 트랜스포머의 이 서브레이어는 선형층 두 개에 활성화 하나라 어느 이름으로 불러도 맞고, 원 논문은 상위 분류(FFN)로, 이후 구현들은 구체 구조(MLP)로 불렀을 뿐이다. 한 가지 주의 — 순전파(forward pass)와는 다른 말이다. forward pass는 RNN을 포함한 모든 신경망이 수행하는 계산 단계이고, feed-forward는 연결에 순환이 없다는 구조 분류다.

![Transformer Explainer에서 어텐션 출력이 MLP를 통과해 새 토큰 표현으로 바뀌는 애니메이션]({{site.url}}/assets/images/llmso-transformer-explainer-mlp.gif){: .align-center width="700"}

<center><sup>Transformer Explainer 화면 직접 캡처</sup></center>

## 입력과 출력

[2.4편]({% post_url 2026-08-05-AI-LLM-Optimization-02-04-Transformer-Explainer-Transformer-Block-and-Self-Attention-Layer %})에서 셀프 어텐션을 다룰 때와 같은 순서로, 입력과 출력의 경계를 먼저 확인한다.

- **입력**: 어텐션 서브레이어의 최종 출력 — concat과 $W^O$까지 거친 `(seq_len, 768)`이다. **Q·K·V가 아니다.** Q·K·V는 어텐션 안에서 만들어져 어텐션 안에서 소비되는 중간 계산 결과이고, MLP가 받는 것은 그 계산이 끝난 뒤의 문맥 혼합된 표현이다
- **출력**: 같은 모양 `(seq_len, 768)`의 새 표현이다. 토큰 개수도 차원도 유지된다

즉 이 서브레이어가 하는 일도 결국 지금까지의 프레임 그대로 — **토큰별 표현을 다른 표현으로 바꾸는 것** — 다. 달라지는 것은 바꾸는 방식이다.

## 재가공의 이유: 어텐션 연산의 선형성

여기서 자연스러운 의문이 생긴다. 어텐션이 이미 문맥 정보를 반영해 표현을 다시 써 줬는데, 왜 굳이 한 번 더 가공하는가.

답은 어텐션이 한 일의 **계산적 성격**에 있다. [2.4편]({% post_url 2026-08-05-AI-LLM-Optimization-02-04-Transformer-Explainer-Transformer-Block-and-Self-Attention-Layer %})에서 "문맥 반영의 실체는 토큰 간 정보 혼합"이라 정리했고, [앞 글]({% post_url 2026-08-05-AI-LLM-Optimization-02-05-Transformer-Explainer-Self-Attention %})에서 그 혼합이 "V 벡터들의 가중 평균"임을 수식으로 확인했다. 그런데 그 연산을 토큰 하나의 관점에서 다시 보면 — 다른 토큰들의 V를 비율대로 더하고(가중합), $W^O$를 곱한(선형 변환) 것이 전부다. **모아 온 내용물에 가해진 연산은 선형 결합뿐이다.** 어텐션에 들어 있는 유일한 비선형인 softmax는 "얼마씩 섞을까"라는 비율을 만드는 데 쓰였을 뿐, 섞인 내용물 자체를 휘게 만들지는 않았다.

그리고 [1편]({% post_url 2026-08-05-AI-LLM-Optimization-01-AI-Overview %})에서 확인했듯 **선형변환은 아무리 합성해도 하나의 선형변환으로 접힌다.** 문맥을 모아 온 표현에서 복잡한 특징을 뽑아내려면 어딘가에서 공간을 "접는" 비선형이 필요하고, 블록 안에서 그 접기를 담당하는 자리가 MLP다.

## 분업: 통신과 계산

이렇게 놓고 보면 트랜스포머 블록의 두 서브레이어는 역할이 깔끔하게 갈린다.

- **어텐션 — 어디서 정보를 모을까**: 각 토큰이 어떤 토큰과 더 관련 있는지를 계산해(어텐션 가중치), 관련도가 높은 토큰에서 더 많은 정보를 가져온다. 토큰 사이의 **통신**이다
- **MLP — 모은 정보로 무엇을 계산할까**: 그렇게 모인 표현을 토큰마다 독립적으로 비선형 가공해 특징을 뽑아낸다. 토큰 안의 **계산**이다

이 분업 프레임은 글 마지막의 [블록 갈무리](#두-서브레이어의-대비)에서 표로 다시 정리한다.

## position-wise: 토큰별 독립 변환

앞에서 "토큰마다 독립적으로" 비선형 가공해 특징을 뽑아낸다고 했는데, 이는 MLP는 **같은 가중치($W_1, W_2$)를 모든 토큰 벡터에 각각 적용**하고, **토큰 사이에는 아무 정보도 오가지 않는다**는 것을 의미한다. 원 논문이 이 성질을 가리켜 position-wise라 이름 붙였고, [2020년에 정리한 네트워크 구조 글]({% post_url 2020-08-13-AI-Transformer-05 %})에도 같은 문장이 있다 — *"문장 내 각 토큰 벡터에 똑같은 가중치를 독립적으로 적용하며, 위치 간에는 아무 정보도 주고받지 않는다. 위치 간 정보 교환은 전적으로 Attention이 담당한다."*

"모든 벡터에 대해 병렬 연산한다"는 말의 의미가 이것이다. 토큰 `i`의 MLP 출력은 토큰 `i`의 입력만으로 결정되므로, 계산 순서를 기다릴 이유가 없다. 실제 구현에서는 토큰별로 반복문을 도는 것이 아니라 `X (seq_len, 768) × W₁` 행렬곱 한 번으로 토큰 축 전체가 한꺼번에 처리된다 — 어텐션에서 "각 벡터 간 연산으로 문맥을 뽑아냈던 것"과 달리, 여기서는 각 토큰이 자기 자신의 특징만 다듬는다.

<br>

![3Blue1Brown 영상에서 어텐션과 Feedforward(MLP) 블록이 교대로 반복되며 토큰 벡터들이 통과하는 장면]({{site.url}}/assets/images/llmso-transformer-mlp-reference-2.png){: .align-center width="700"}

![3Blue1Brown 영상의 MLP 내부 — Linear, ReLU, Linear를 거쳐 잔차로 더해지는 구조]({{site.url}}/assets/images/llmso-transformer-transformer-mlp-reference-1.png){: .align-center width="700"}

![3Blue1Brown 영상에서 토큰 벡터들이 나란히 같은 MLP를 독립적으로 병렬 통과하는 장면]({{site.url}}/assets/images/llmso-transformer-mlp-reference-3.png){: .align-center width="700"}

<center><sup>출처: <a href="https://www.youtube.com/watch?v=9-Jl0dxWQs8">3Blue1Brown — How might LLMs store facts (딥러닝 챕터 7)</a> 영상 캡처. 영상은 단순화를 위해 활성화 함수를 ReLU로 그리는데, GPT-2가 실제로 쓰는 것은 뒤에서 볼 GELU다</sup></center>

이 독립성을 3Blue1Brown의 시각화가 가장 직관적으로 보여 준다. 영상은 어텐션을 지나온 토큰 벡터들을 나란히 세워 두고, **각 벡터가 같은 MLP의 복사본을 하나씩 따로 통과하는 모습**으로 그린다. 벡터마다 동일한 up-projection → 활성화 → down-projection이 동시에 적용되는데, 그동안 벡터와 벡터 사이를 잇는 선은 하나도 등장하지 않는다. 직전의 어텐션 챕터에서 벡터들 사이를 선이 가로지르며 정보가 오가던 그림과 정확히 대비되는 장면이고, 병렬 연산이 왜 되는지를 따로 설명할 필요가 없게 만드는 그림이기도 하다 — **서로를 기다릴 연결 자체가 없다.**

<br>

# 레이어 구조: 확장 → 활성화 → 압축

MLP 내부는 세 단계다. 선형층으로 차원을 넓히고, 활성화 함수를 통과시키고, 다시 선형층으로 원래 차원에 되돌린다.

![Transformer Explainer의 MLP 전체 구조 — 768차원 입력이 3072차원으로 확장됐다가 다시 768차원으로 줄어드는 모습]({{site.url}}/assets/images/llmso-transformer-explainer-mlp-overview.png){: .align-center width="700"}

<center><sup>Transformer Explainer 화면 직접 캡처</sup></center>

## up-projection과 down-projection

GPT-2 small 기준 숫자로 쓰면 **768 → 3072 → 768**이다.

```text
X (seq_len, 768)
→ × W₁ (768, 3072) + b₁ : (seq_len, 3072)   # up-projection — 4배 확장
→ GELU                  : (seq_len, 3072)   # 원소별(pointwise) 비선형
→ × W₂ (3072, 768) + b₂ : (seq_len, 768)    # down-projection — 원래 차원으로 압축
```

- 확장하는 첫 선형층을 **up-projection**, 되돌리는 둘째 선형층을 **down-projection**이라 부른다. 요즘 LLM 문헌과 구현에서 사실상 표준으로 굳은 명칭이다 — HuggingFace의 Llama 구현은 모듈 이름 자체가 `up_proj`·`down_proj`이고, GPT-2 구현에서는 `c_fc`·`c_proj`라는 이름으로 같은 것이 들어 있다. [2.4편]({% post_url 2026-08-05-AI-LLM-Optimization-02-04-Transformer-Explainer-Transformer-Block-and-Self-Attention-Layer %})에서 "사영(projection)은 다른 차원 공간으로 보내는 선형 변환의 관행적 명명"이라 했던 그 용법이 위아래 방향으로 확장된 것이다
- 중간 차원 3072는 768의 **4배**다. 이 4배는 이론적 필연이 아니라 원 논문(512 → 2048)부터 이어진 경험적 관행이고, GPT-2·GPT-3가 그대로 따랐다. [2020년 글]({% post_url 2020-08-13-AI-Transformer-05 %})에서 정리했던 원 논문의 FFN — 두 선형층 사이에 ReLU, 512에서 2048로 4배 — 에서 활성화 함수와 숫자만 바뀐 구조다

직관적으로는 "좁은 공간에서 곧바로 접는 대신, **넓은 작업 공간에 펼쳐 놓고 특징을 나눠 담은 뒤 다시 정리해 넣는다**"로 읽으면 된다. 다만 이 해석에는 [1편]({% post_url 2026-08-05-AI-LLM-Optimization-01-AI-Overview %})의 은닉층 논의에서 그어 둔 경계가 그대로 적용된다 — 확장·압축이라는 골격의 역할까지는 말할 수 있지만, 3072개 차원 각각이 어떤 특징을 담는지에 사람이 읽을 수 있는 의미는 없다. 은닉 차원을 4배로 두는 것도 판단 기준 4벌을 정해 넣는 일이 아니라 표현을 담을 그릇의 크기를 정하는 일이고, "왜 하필 4배가 잘 되는가"에는 경험적 답밖에 없다.

GPT-2 구조를 그대로 옮긴 nanoGPT의 MLP 모듈이 이 세 단계를 그대로 보여 준다.

```python
# nanoGPT MLP — n_embd=768 기준 768 → 3072 → 768 (원본의 bias 인자와 dropout은 생략한 발췌)
class MLP(nn.Module):
    def __init__(self, config):
        super().__init__()
        self.c_fc   = nn.Linear(config.n_embd, 4 * config.n_embd)  # up-projection (×4)
        self.gelu   = nn.GELU()                                    # 원소별 비선형
        self.c_proj = nn.Linear(4 * config.n_embd, config.n_embd)  # down-projection

    def forward(self, x):
        x = self.c_fc(x)     # (B, T, 768) → (B, T, 3072)
        x = self.gelu(x)     # shape 유지 — 원소별 적용
        x = self.c_proj(x)   # (B, T, 3072) → (B, T, 768)
        return x
```

$W_1, W_2$와 bias는 모두 사전학습으로 결정되는 학습 파라미터다. [2.4편]({% post_url 2026-08-05-AI-LLM-Optimization-02-04-Transformer-Explainer-Transformer-Block-and-Self-Attention-Layer %})의 "학습으로 결정 vs 입력마다 계산" 구분을 여기에 적용하면 — 가중치는 학습으로 결정되어 추론 시 고정이고, 중간의 3072차원 activation은 입력마다 새로 계산된다. 어텐션과 달리 **입력끼리 곱하는 연산이 없으므로**, MLP에는 "입력마다 새로 만들어지는 가중치" 같은 것이 없다.

## GELU: 부드러운 게이트

두 선형층 사이의 활성화 함수를 보자. Transformer Explainer의 설명이다.

> Many activation types exist; GPT-2 uses GELU, which lets small values pass partially and large values pass fully, helping capture both subtle and strong patterns.

![Transformer Explainer의 MLP 구간 — GELU 활성화와 Residual이 함께 표시된 화면]({{site.url}}/assets/images/llmso-transformer-explainer-mlp-activation.png){: .align-center width="700"}

<center><sup>Transformer Explainer 화면 직접 캡처</sup></center>

<br>

**GELU(Gaussian Error Linear Unit)**의 정의는 다음과 같다.

$$
\operatorname{GELU}(x) = x \cdot \Phi(x)
$$

$\Phi(x)$는 표준정규분포의 누적분포함수 — "표준정규분포에서 뽑은 값이 $x$보다 작을 확률" — 로, 0에서 1로 부드럽게 올라가는 S자 곡선이다. 그러니 GELU는 **입력값에 "통과 비율"을 곱하는 부드러운 게이트**다. $x$가 크면 $\Phi(x) \approx 1$이라 거의 그대로 통과하고, 큰 음수면 $\Phi(x) \approx 0$이라 사실상 차단되며, 0 근처의 작은 값들은 **부분적으로** 통과한다.

![GELU 함수 그래프 — ReLU와 달리 0 근처에서 부드럽게 꺾이고, 작은 음수 구간에서 0이 아닌 값을 갖는다]({{site.url}}/assets/images/llmso-activation-gelu.png){: .align-center width="600"}

<center><sup>출처: <a href="https://medium.com/@glomus_health/deep-learning-gelu-gaussian-error-linear-unit-activation-function-56168dd5997">Deep Learning: GELU (Gaussian Error Linear Unit) Activation Function (Medium)</a></sup></center>

[1편]({% post_url 2026-08-05-AI-LLM-Optimization-01-AI-Overview %})에서 본 ReLU와 비교하면 차이가 선명하다. ReLU는 0을 경계로 딱 자르는 hard 게이트 — 음수는 전부 0, 양수는 전부 통과 — 였다. GELU는 같은 일을 확률적 비율로 부드럽게 한다. "왜 음수를 다 꺼버리지 않는가"라는 질문에 대한 답이 여기 있고, 두 갈래로 정리된다.

- **뉴런이 죽지 않는다**: 역전파에서 활성화 함수를 지나는 gradient에는 chain rule에 따라 그 함수의 **미분값**이 곱해진다 — 출력값이 아니다. ReLU는 음수 구간의 미분이 정확히 0이라, 입력이 계속 음수 영역에 머무는 뉴런은 어떤 오차 신호가 와도 0이 곱해져 전달이 끊기고, 학습으로 회복할 수단이 사라진다(dead neuron). GELU는 음수 구간의 미분이 0이 아니라서 신호가 계속 흐른다. 이때 골짜기 왼쪽 구간에서는 미분값이 음수가 되어 gradient의 부호가 뒤집혀 전달되기도 하는데, 이는 문제가 아니다 — [1편]({% post_url 2026-08-05-AI-LLM-Optimization-01-AI-Overview %})에서 봤듯 gradient의 부호는 파라미터를 어느 방향으로 옮길지 알려주는 정보일 뿐이고, 학습을 막는 것은 부호가 아니라 **크기가 정확히 0이 되어 신호 자체가 끊기는 것**이다
- **손실 지형이 매끄럽다**: ReLU는 0에서 미분이 불연속이라 경계 근처에서 gradient 방향이 뚝뚝 끊긴다. GELU는 전 구간 미분 가능해서, 학습 중 가중치가 조금 움직일 때 출력과 gradient도 연속적으로 따라 움직인다. "부드러워서 최적화가 잘 된다"는 서술의 실체가 이것이다 — 오차를 줄이는 방향으로 조금씩 이동하는 gradient descent 입장에서, 지형에 꺾인 모서리가 없는 쪽이 안정적이다

다만 "GELU가 성능을 향상시킨다"는 문장은 이론적 보장이 아니라 **경험적 보고**로 받아들이는 것이 정확하다. GELU 논문과 이후 BERT·GPT 계열의 채택 과정에서 ReLU 대비 우위가 실험적으로 관측되었고, 그 결과 트랜스포머 계열의 기본값처럼 자리 잡았다.

> *참고*: GPT 계열의 활성화 함수와 이후의 이동
>
> GPT-1·2·3은 모두 GELU를 쓴다. 정확히는 계산이 무거운 $\Phi(x)$ 대신 tanh 근사식 $0.5x\left(1+\tanh\left[\sqrt{2/\pi}\,(x+0.044715x^3)\right]\right)$을 쓰는 구현이 표준이었다. 한편 이후 세대의 오픈 모델들(Llama, PaLM 계열 등)은 SwiGLU처럼 게이트 구조를 가진 활성화로 옮겨 갔다 — 지금 단계에서는 "GPT-2의 GELU가 유일한 선택지가 아니고, 활성화 함수도 계속 갱신되는 설계 선택"이라는 것까지만 알아 두면 충분하다.

<br>

# 파라미터 분포: GPT-3의 산수

MLP가 블록의 "나머지 절반"이라고 했지만, 파라미터 수로 보면 절반이 아니다.

## 레이어별 파라미터 표

GPT-3(175B)의 가중치를 레이어 종류별로 집계한 표를 확인해 보자.

| 레이어 | 차원 계산식 | 파라미터 수 |
| --- | --- | --- |
| Embedding | d_embed × n_vocab = 12,288 × 50,257 | 617,558,016 |
| Key | d_query × d_embed × n_heads × n_layers = 128 × 12,288 × 96 × 96 | 14,495,514,624 |
| Query | d_query × d_embed × n_heads × n_layers | 14,495,514,624 |
| Value | d_value × d_embed × n_heads × n_layers | 14,495,514,624 |
| Output | d_embed × d_value × n_heads × n_layers | 14,495,514,624 |
| **Up-projection** | n_neurons × d_embed × n_layers = 49,152 × 12,288 × 96 | **57,982,058,496** |
| **Down-projection** | d_embed × n_neurons × n_layers | **57,982,058,496** |
| Unembedding | n_vocab × d_embed | 617,558,016 |
| **합계** | | **175,181,291,520** |

<center><sup>출처: <a href="https://www.youtube.com/watch?v=9-Jl0dxWQs8">3Blue1Brown — How might LLMs store facts</a> 등 딥러닝 시리즈 챕터 5~7에 걸쳐 등장하는 파라미터 집계를 표로 재구성. bias·LayerNorm 파라미터는 집계에서 제외된 근사치다</sup></center>

표에 쓰인 아키텍처 상수는 다음과 같고, 괄호 안은 이 시리즈에서 계속 본 GPT-2 small의 대응 값이다.

- d_embed (임베딩 차원) = 12,288 (GPT-2 small: 768)
- n_vocab (어휘 사전 크기) = 50,257 (동일)
- d_query, d_value (헤드당 차원) = 128 (GPT-2 small: 64)
- n_heads (어텐션 헤드 수) = 96 (GPT-2 small: 12)
- n_layers (트랜스포머 블록 수) = 96 (GPT-2 small: 12)
- n_neurons (MLP 은닉 차원) = 49,152 = 4 × d_embed (GPT-2 small: 3072)

집계해 보면 어텐션(K+Q+V+Output) 합이 약 58.0B, MLP(Up+Down) 합이 약 116.0B으로, **전체 175B 중 약 2/3가 MLP에 있다.**

## MLP가 2/3인 이유

숫자가 커서 특별해 보이지만, 실체는 단순한 산수다. 블록 하나 기준으로 세어 보자. 모델 차원을 $d$라 하면,

- **어텐션**: $W^Q, W^K, W^V, W^O$ 네 장, 각 $d \times d$ (헤드로 쪼개도 총량은 같다 — [2.5편]({% post_url 2026-08-05-AI-LLM-Optimization-02-05-Transformer-Explainer-Self-Attention %})에서 본 "큰 행렬 슬라이스 = 헤드별 사영" 동치) → $4d^2$
- **MLP**: $W_1$이 $d \times 4d$, $W_2$가 $4d \times d$ → $8d^2$

**정확히 2배다.** "은닉 차원을 4배로 잡는다"는 설계 선택 하나가 그대로 파라미터 비율 2:1로 이어진 것이고, 임베딩·unembedding의 몫이 미미해지는 GPT-3 규모에서는 전체의 2/3라는 숫자로 나타난다. 표에서 재미있는 관찰 하나 — 어텐션 네 종류의 **합**(58.0B)이 up-projection **한 장**의 몫(58.0B)과 같다. $4d^2 = 4d \times d$이니 당연한 결과다.

"셀프 어텐션 쪽이 파라미터가 더 많을 것 같다"는 직관은 아마 어텐션 연산의 복잡성 — 토큰 쌍 전체를 훑는 $seq^2$ — 에서 왔을 텐데, 여기서 [2.5편]({% post_url 2026-08-05-AI-LLM-Optimization-02-05-Transformer-Explainer-Self-Attention %})의 구분이 그대로 힘을 발휘한다. **그 $QK^\top$는 파라미터 없는 연산이다.** 토큰끼리 곱하는 계산이 아무리 커져도 저장되는 숫자는 하나도 늘지 않는다. 파라미터 수와 연산 복잡도는 별개의 축이다.

## 파라미터 수와 계산 시간의 구분

그렇다면 파라미터가 2배인 MLP는 계산도 2배로 오래 걸리는가, 그리고 오래 걸린다면 순차 통과 때문인가 병렬화가 안 되어서이기 때문일까? 이 질문에 답하기 위해 두 축을 갈라서 확인해 보자.

- **일의 양(FLOPs)**: 행렬곱의 FLOPs는 가중치 크기에 비례하므로, MLP의 사영 연산량은 어텐션 사영의 2배가 맞다. 시퀀스가 짧을 때는 MLP가 블록 연산량의 지배 항이다. 다만 어텐션에는 파라미터 없는 $QK^\top$·$AV$ 항이 따로 있고 이쪽은 $seq$에 비례해 커지므로, 문맥이 길어질수록 어텐션 코어의 몫이 커진다
- **병렬성**: MLP는 **느린 쪽이 아니라 오히려 가장 병렬화가 잘 되는 쪽**이다. position-wise라 토큰 간 의존이 전혀 없고, 계산 전체가 `(seq_len, 768) × (768, 3072)` 같은 거대 GEMM(general matrix multiply, 행렬곱 커널) 두 방이다. [1편]({% post_url 2026-08-05-AI-LLM-Optimization-01-AI-Overview %})에서 본 "단순·균일·독립한 곱셈-누산의 대량 반복" — GPU의 SIMT 구조가 원하는 형태 그 자체다. 커널 관점에서 까다로워 FlashAttention 같은 융합 커널이 필요했던 쪽은 오히려 어텐션이다

정리하면 — MLP 구간이 시간이 걸린다면 그 이유는 **일의 양(FLOPs와 가중치 크기)이지, 순차 의존이나 병렬화 실패가 아니다.** 어텐션 서브레이어 → MLP 서브레이어의 순차는 있지만, 이는 블록 구조의 의존일 뿐 MLP 내부는 토큰 축이 통째로 병렬이다.

## MLP를 보는 연구 관점: 지식 저장소

파라미터의 2/3가 MLP에 있다는 사실은 "그럼 그 많은 숫자에 무엇이 담기는가"라는 질문으로 이어진다. 해석 연구(mechanistic interpretability) 쪽에서는 MLP를 **모델이 학습한 사실·연관 지식이 주로 저장되는 곳**으로 보는 관점이 있다 — MLP의 두 선형층을 key-value 메모리로 읽는 연구(Geva et al.)가 대표적이고, 위 표의 출처인 3Blue1Brown 챕터 제목("How might LLMs store facts")도 같은 관점을 다룬다. 어텐션이 정보를 옮기는 배선이라면 MLP는 저장과 변환이 일어나는 창고라는 그림이다. 다만 이것은 활발히 연구 중인 해석이지 확정된 사실이 아니다 — "MLP가 더 중요하다"는 서열보다는, [1편]({% post_url 2026-08-05-AI-LLM-Optimization-01-AI-Overview %})의 은닉층 이야기처럼 **역할이 다르다** 수준으로 받아들이는 것이 안전하다.

## 아키텍처 상수

남은 것은 위 표의 계산식에 등장한 값들 — d_embed, n_heads, n_layers, n_neurons — 을 어떻게 이해할 것인가다. 이들은 [1편]({% post_url 2026-08-05-AI-LLM-Optimization-01-AI-Overview %})에서 본 **하이퍼파라미터**다. 학습으로 찾아지는 값이 아니라 모델 설계 시점에 사람이 정하는 값이고, 한번 정해지면 학습 중에도 서빙 중에도 불변이라 "상수"라 부른다.

실무에서 이 상수들은 추상적 개념이 아니라 **모델 저장소의 `config.json`에 그대로 적혀 있는 값들**이다 — `hidden_size`(d_embed), `num_attention_heads`(n_heads), `num_hidden_layers`(n_layers), `intermediate_size`(n_neurons)라는 필드명으로 만나게 된다. 다만 필드명은 모델 계열마다 달라서, 이 시리즈의 주 예시인 GPT-2의 config.json은 같은 값들을 `n_embd`·`n_head`·`n_layer`라는 옛 이름으로 담고 있다. [2.1편]({% post_url 2026-08-05-AI-LLM-Optimization-02-01-LLM-Transformer-Overview %})에서 "서빙 튜닝 노브는 전부 아키텍처의 상수에서 유도된다"고 했던 그 상수들이 바로 이것이고, KV cache 크기 공식의 모든 항이 여기서 나온다.

<br>

# 서빙 관점: MLP가 결정하는 것

이 시리즈의 목적지가 서빙이니, MLP가 서빙 그림 어디에 관련되는지 살펴 보자. 셋 다 이후 서빙 편에서 자세히 다룰 ~~(것으로 예상되는)~~ 주제라, 지금은 연결 고리의 존재만 알아 두면 충분하다.

## KV cache의 부재와 decode 병목

**MLP에는 KV cache에 해당하는 것이 없다.** [2.5편]({% post_url 2026-08-05-AI-LLM-Optimization-02-05-Transformer-Explainer-Self-Attention %})에서 봤듯 KV cache는 "과거 토큰의 K·V를 미래의 모든 쿼리가 계속 참조한다"는 어텐션 고유의 재사용 패턴에서 나온 장치다. MLP는 토큰별 독립이라 과거 토큰의 중간 결과를 다시 참조할 일 자체가 없다 — 캐시할 것이 없다.

대신 MLP는 다른 방식으로 서빙 비용에 등장한다. 자기회귀 decode는 토큰 하나를 만들 때마다 **모델 가중치 전체를 VRAM에서 읽어야** 하는데, 방금 본 산수대로 그 가중치의 약 2/3가 MLP 몫이다. [2.1편]({% post_url 2026-08-05-AI-LLM-Optimization-02-01-LLM-Transformer-Overview %})에서 "decode는 memory-bandwidth-bound"라고 했던 비대칭의 가장 큰 지분이 바로 이 MLP 가중치 로드다. 파라미터 2/3라는 숫자가 저장 용량 문제로 끝나지 않고, 토큰 하나당 반복되는 메모리 트래픽으로 서빙 지연에 직결되는 것이다.

## 텐서 병렬화의 분할 축

모델이 GPU 한 장에 안 들어갈 때 가중치를 쪼개는 **텐서 병렬화(tensor parallelism, TP)**에서, MLP는 표준 분할 축이다. up-projection은 3072차원의 열 방향으로(column-parallel), down-projection은 행 방향으로(row-parallel) 나누면, GPU마다 은닉 차원의 자기 몫만 계산하다가 down-projection 뒤 한 번의 all-reduce로 합쳐진다(Megatron-LM 방식). 어텐션을 헤드 축으로 나누는 것과 함께 TP의 두 기둥이다.

vLLM 같은 서빙 엔진이 로드 시점에 여러 사영 가중치를 하나로 융합하는 것도 MLP에서 반복된다 — Llama 계열의 gate·up 두 사영을 붙여 GEMM 한 번으로 처리하는데, [2.5편]({% post_url 2026-08-05-AI-LLM-Optimization-02-05-Transformer-Explainer-Self-Attention %})에서 본 QKV 융합과 정확히 같은 논리(커널 실행 횟수와 메모리 읽기 절약)다.

## MoE: MLP의 희소화

파라미터의 2/3가 MLP라는 사실은 최적화의 표적이 어디인지도 알려 준다. **MoE(Mixture of Experts)**는 이 MLP를 여러 벌(expert)로 복제해 두고, 토큰마다 라우터가 고른 일부 expert만 계산에 참여시키는 구조다 — 파라미터 총량은 키우되 토큰당 실제 연산량은 일부만 쓰는, "가장 큰 덩어리를 희소하게 만드는" 접근이다. Mixtral, DeepSeek 계열 등 최근 모델들이 이 구조를 쓴다. 어텐션이 아니라 MLP가 희소화 대상이 된 이유가 방금 본 파라미터 분포다.

<br>

# 트랜스포머 블록 갈무리

이것으로 블록의 두 서브레이어를 모두 봤다. [2.4편]({% post_url 2026-08-05-AI-LLM-Optimization-02-04-Transformer-Explainer-Transformer-Block-and-Self-Attention-Layer %})에서 그렸던 골격을 완성판으로 다시 그리면 다음과 같다.

```text
Transformer Block × 12 (GPT-2 small)
├─ Multi-Head Self-Attention 서브레이어      # 2.4~2.5편
│  ├─ Q/K/V 융합 사영 (768 → 2304)
│  ├─ 12헤드 분할 → 헤드별 스코어·마스크·softmax → V 가중합
│  └─ concat → 출력 사영 W^O (→ 768)
├─ MLP 서브레이어                            # 이번 글
│  ├─ up-projection (768 → 3072)
│  ├─ GELU
│  └─ down-projection (3072 → 768)
└─ (서브레이어마다 잔차 연결 + LayerNorm)     # 아래에서 한 단계만 열어 본다
```

## 두 서브레이어의 대비

블록을 닫으면서, 시리즈 내내 쌓아 온 어텐션과 MLP의 대비를 한 표로 모은다.

| 구분 | MLP (FFN) | 어텐션 |
| --- | --- | --- |
| 학습 가중치 | $W_1, W_2$ (+bias) | $W^Q, W^K, W^V, W^O$ (+bias) |
| 비선형 | GELU — 내용물을 휘게 하는 원소별 활성화 | softmax — 혼합 비율을 만드는 행 단위 정규화 |
| 파라미터 없는 연산 | 없음 | $QK^\top$, $AV$ — 입력끼리의 곱 |
| 곱하는 대상 | 입력 × 학습된 가중치뿐 | 중간에 입력 × 입력이 낀다 |
| 토큰을 섞는 가중치 | 없음 — 고정 가중치를 토큰별 독립 적용 | 어텐션 가중치 — 입력마다 softmax로 새로 계산되는 동적 값 |
| 토큰 간 정보 교환 | 없음 (position-wise) | 있음 — 이 레이어의 존재 이유 |
| 역할 한 줄 | 모은 정보의 토큰별 가공 (계산) | 토큰 간 정보 수집 (통신) |

두 서브레이어의 선형층 자체는 완전히 같은 물건이다 — 학습되어 추론 시 고정되는 가중치 행렬. 결정적 차이는 선형층 **사이**에 있다. MLP는 처음부터 끝까지 "입력 × 학습된 가중치"만 하는 반면, 어텐션은 중간에 입력끼리 곱한다($QK^\top$). 그래서 어텐션 가중치는 학습된 값이 아니라 문장이 바뀔 때마다 새로 만들어지는 값이고, 이 동적인 토큰 혼합이 MLP가 흉내 낼 수 없는 어텐션의 정체성이다. [2.4편]({% post_url 2026-08-05-AI-LLM-Optimization-02-04-Transformer-Explainer-Transformer-Block-and-Self-Attention-Layer %})의 "학습으로 결정 vs 입력마다 계산" 표가 이 대비의 다른 표현이었던 셈이다.

## 서브레이어 순서

블록 안에서 어텐션이 먼저 오고 MLP가 뒤에 온다. 이 순서는 바꿀 수 없는 것인가.

결론부터 말하면 수학적 필연은 아니다. 실제로 어텐션과 MLP를 순차가 아니라 **같은 입력에 병렬로 적용해 더하는** 변형(parallel block — GPT-J, PaLM 계열 등)이 존재하고, 대규모 모델에서 실용적으로 동작한다고 보고되어 있다. 그럼에도 표준 순서의 직관은 분업 구조에서 나온다 — 먼저 토큰 간 정보를 모으고(통신), 모인 것을 가공하는(계산) 사이클이 자연스럽고, 이 블록이 12번(GPT-3는 96번) 반복되므로 통신과 계산이 교대로 누적된다. 반복 구조라는 점이 힌트이기도 하다. 블록이 수십 번 겹치면 "한 블록 안에서 무엇이 먼저냐"는 전체 흐름에서 생각보다 결정적이지 않다 — 어느 서브레이어든 곧 다음 블록에서 상대 서브레이어를 다시 만난다.

## 잔차 연결과 LayerNorm

[2.4편]({% post_url 2026-08-05-AI-LLM-Optimization-02-04-Transformer-Explainer-Transformer-Block-and-Self-Attention-Layer %})에서 "블록에 이런 장치가 함께 붙어 있다" 수준으로 접어 뒀던 **잔차 연결(residual connection)**과 **LayerNorm**을, 블록을 닫는 김에 한 단계만 열어 본다. nanoGPT의 블록 코드가 두 장치의 위치를 가장 정직하게 보여 준다.

```python
# nanoGPT Block.forward — 블록 하나의 전체 흐름
def forward(self, x):
    x = x + self.attn(self.ln_1(x))   # LayerNorm → 어텐션, 그리고 입력 x를 그대로 더한다(잔차)
    x = x + self.mlp(self.ln_2(x))    # LayerNorm → MLP, 마찬가지로 잔차
    return x
```

- **잔차 연결**: 각 서브레이어의 출력을 입력에 **더한다**($x + \text{sublayer}(x)$). 서브레이어가 표현을 통째로 다시 쓰는 것이 아니라 기존 표현에 수정분을 얹는 구조가 되고, 덧셈 경로를 따라 gradient가 곧장 흘러 깊은 블록 스택의 학습이 안정된다
- **LayerNorm**: 서브레이어에 들어가기 전 토큰 벡터의 스케일을 정규화해, 블록을 거듭 지나도 값의 크기가 폭주하거나 소멸하지 않게 잡아 준다

지금 단계에서는 "블록의 두 서브레이어가 모두 이 두 장치에 감싸여 있다"까지면 충분하다. 왜 이 구조가 깊은 스택을 가능하게 하는지의 상세(Pre-LN vs Post-LN 같은 갈래 포함)는 이 시리즈의 범위 밖에 둔다.

## GPU와의 궁합

블록 전체를 계산 관점에서 다시 보면, [1편]({% post_url 2026-08-05-AI-LLM-Optimization-01-AI-Overview %})과 [2.1편]({% post_url 2026-08-05-AI-LLM-Optimization-02-01-LLM-Transformer-Overview %})에서 예고했던 "트랜스포머와 GPU의 궁합"이 구체적으로 보인다.

- 블록을 이루는 계산은 전부 **거대 행렬곱의 사슬**이다 — QKV 융합 사영, $QK^\top$, $AV$, $W^O$, up/down-projection. 전부 1편에서 본 "단순·균일·독립한 곱셈-누산의 대량 반복"이다
- 토큰 축에 순차 의존이 없다. 어텐션은 토큰 쌍 전체를 행렬곱 한 방으로 처리하고, MLP는 아예 토큰별 독립이다. 순차로 남는 것은 블록 12개의 사슬과 블록 안 서브레이어 순서뿐 — [2.1편]({% post_url 2026-08-05-AI-LLM-Optimization-02-01-LLM-Transformer-Overview %})에서 RNN과 대비했던 "순차 스텝 수가 시퀀스 길이가 아니라 블록 수"라는 성질이 정확히 이 구조에서 나온다

토큰 간 통신(어텐션)조차 행렬곱으로 표현되고, 통신이 필요 없는 구간(MLP)은 완전 독립 — 이 구성이 SIMT 하드웨어에 그대로 얹히는 형태라서, 트랜스포머가 GPU 시대의 아키텍처가 될 수 있었다.

## 다음: 출력층

이것으로 [2.2편]({% post_url 2026-08-05-AI-LLM-Optimization-02-02-Transformer-Explainer-Overview %})에서 잡았던 세 부분 — 임베딩, 트랜스포머 블록, 출력층 — 중 두 번째까지 끝났다. 다음 글에서는 마지막 블록의 출력이 다음 토큰의 확률 분포가 되는 출력층(unembedding과 softmax, 그리고 temperature 같은 샘플링 장치)을 보고, Transformer Explainer 시리즈를 닫는다. 그 뒤는 실습이다.

<br>

# 정리

- MLP는 1편의 "선형층 + 활성화" 구조 그대로, 어텐션 출력 `(seq_len, 768)`을 받아 768 → 3072(GELU) → 768로 가공해 같은 모양을 내놓는다. 입력은 Q·K·V가 아니라 어텐션의 최종 출력이다
- 어텐션이 모은 정보에는 선형 결합만 가해졌으므로, 특징을 뽑는 비선형 가공이 필요하다. 블록의 분업은 어텐션 = 토큰 간 통신, MLP = 토큰별 계산이고, MLP는 position-wise — 같은 가중치를 토큰마다 독립 적용하며 토큰 간 정보 교환이 없다
- GELU는 통과 비율을 확률로 정하는 부드러운 게이트다. 음수 구간에도 기울기가 남아 뉴런이 죽지 않고 전 구간 미분 가능해 최적화가 안정적이라는 경험적 이점으로 GPT 계열의 기본값이 됐다
- 파라미터 분포는 산수다. 레이어당 어텐션 $4d^2$ vs MLP $8d^2$ — 4배 확장이라는 설계 선택이 곧 "전체 파라미터의 2/3가 MLP"로 이어진다. 파라미터 없는 연산($QK^\top$)과 파라미터 수를 가르면, MLP는 느린 구간이 아니라 가장 GPU 친화적인 구간이다
- 서빙에서 MLP는 KV cache가 없는 대신 decode 가중치 로드의 2/3를 차지하고, 텐서 병렬화의 표준 분할 축이며, MoE가 희소화하는 대상이다
- 트랜스포머 블록 = (잔차·LayerNorm에 감싸인) 멀티헤드 셀프 어텐션 + MLP. 결정적 차이는 입력끼리 곱하는 연산의 유무이고, 이 블록 12개의 사슬이 곧 GPT-2다

<br>

# 참고 링크

- [Transformer Explainer](https://poloclub.github.io/transformer-explainer/)
- [Attention Is All You Need (Vaswani et al., 2017)](https://arxiv.org/abs/1706.03762)
- [Gaussian Error Linear Units (GELUs) (Hendrycks & Gimpel, 2016)](https://arxiv.org/abs/1606.08415)
- [3Blue1Brown — How might LLMs store facts (딥러닝 챕터 7)](https://www.youtube.com/watch?v=9-Jl0dxWQs8)
- [Transformer Feed-Forward Layers Are Key-Value Memories (Geva et al., 2021)](https://arxiv.org/abs/2012.14913)
- [nanoGPT — Andrej Karpathy (MLP·Block 구현, MIT License)](https://github.com/karpathy/nanoGPT/blob/master/model.py)
- [Megatron-LM: Training Multi-Billion Parameter Language Models Using Model Parallelism](https://arxiv.org/abs/1909.08053)
- [LLM 서빙과 최적화 - 2.5. Transformer: 셀프 어텐션 계산 해부]({% post_url 2026-08-05-AI-LLM-Optimization-02-05-Transformer-Explainer-Self-Attention %})
- [LLM 서빙과 최적화 - 2.4. 트랜스포머 블록과 셀프 어텐션 레이어]({% post_url 2026-08-05-AI-LLM-Optimization-02-04-Transformer-Explainer-Transformer-Block-and-Self-Attention-Layer %})
- [LLM 서빙과 최적화 - 2.2. Transformer Explainer 개요]({% post_url 2026-08-05-AI-LLM-Optimization-02-02-Transformer-Explainer-Overview %})
- [LLM 서빙과 최적화 - 2.1. LLM과 트랜스포머 개요]({% post_url 2026-08-05-AI-LLM-Optimization-02-01-LLM-Transformer-Overview %})
- [LLM 서빙과 최적화 - 1. AI 개요]({% post_url 2026-08-05-AI-LLM-Optimization-01-AI-Overview %})
- [2020년 트랜스포머 시리즈 4편: 네트워크 구조 (원 논문 FFN)]({% post_url 2020-08-13-AI-Transformer-05 %})

<br>
