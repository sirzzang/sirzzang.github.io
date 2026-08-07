---
title:  "[NLP] Transformer_3.Multi-head Attention_2"
excerpt: "<<Language Model>> Transformer 모델에 사용된 Multi-head Attention을 알아 보자."
toc: true
toc_sticky: true
categories:
  - AI
header:
  teaser: /assets/images/blog-AI.jpg
tags:
  - DL
  - NLP
  - Transformer
  - 언어 모델
use_math: true
last_modified_at: 2026-08-02
---



<sup>출처가 명시되지 않은 모든 자료(이미지 등)는 [조성현 강사님](https://blog.naver.com/chunjein)의 강의 및 강의 자료를 기반으로 합니다. [논문 출처](https://arxiv.org/abs/1706.03762) </sup> 

<br>

# *Transformer 이해하기_Multi-head Attention*

<br>



 트랜스포머 모델의 또 다른 핵심 중 하나는 **Multi-head Attention**을 네트워크를 사용한 것이었다. 전체적인 *Multi-head Attention 네트워크* 구조는 다음과 같다.

![multihead attention]({{site.url}}/assets/images/multihead-attention.png){: width="400"}{: .align-center}

 **1)** Attention 메커니즘으로서 **2)** Scaled Dot-Product를 수행하는데, **3)** 이를 여러 개의 head로 나누어 수행한다. 특이한 것은 **4)** 입력 문장 자신에 대해 Scaled Dot-Product를 수행하는 *Self-Attention* 레이어가 있다는 것과, **5)** 레이어에 따라 Masking을 진행할 수 있다는 것이다.

<br>

## 3. Self-Attention

<br>

 *Self* 라는 단어에서도 알 수 있듯, 문장 자기 자신과 attention을 진행하는 것이다.

![Selfhead-Attention]({{site.url}}/assets/images/self-attention.png){: width="500"}{: .align-center}

 예컨대, `Jungkook is very handsome. He is a perfect singer.`이라는 문장이 있을 때, 자기 자신의 문장과 attention을 수행함으로써 `He`가 무엇인지 알아내고자 하는 아이디어이다.

<br>

 *Multi-head Attention*을 수행할 때, **Query, Key, Value**가 모두 동일하다. 자기 자신인 것이다. **입력 문장의 단어들끼리 Attention 메커니즘을 통해 유사도를 구하면서, 문장 내의 각 단어가 어떤 단어와 가장 연관되어 있는지** 구한다. 이제 구체적으로 그 과정을 살펴 보자.

<br>



 먼저 입력 문장으로부터 Query, Key, Value를 얻어야 한다.

![Selfhead-Attention-QKV]({{site.url}}/assets/images/self-attention-qkv.png)

<center><sup>편의상 3번 head를 기준으로 그림을 그렸다. 3번 head이기 때문에 가중치 행렬의 인덱스는 2가 된다.</sup></center>

<br>

* 각 head에 대해 서로 다른 가중치 행렬이 설정된다. 그 shape은 $$(d_{model}, d_k)$$ 이다. 단어 임베딩 행렬이 이 가중치를 통과하면, head 하나가 담당할 $$d_k$$ 차원의 Query, Key, Value가 나온다.

  > *참고* : head는 임베딩의 일부가 아니라 전체를 본다
  >
  >  각 head가 임베딩의 자기 조각만 담당하는 것이 아니다. 자르지 않은 **$$d_{model}$$ 차원 전체**가 head별로 서로 다른 $$(d_{model}, d_k)$$ 가중치를 통과해 $$d_k$$ 차원으로 사영된다. 임베딩 전체를 자기만의 관점으로 압축해서 보기 때문에, head마다 "다른 종류의 관계"를 잡아낼 수 있다.
  >
  > > MultiHead(Q, K, V) = Concat(head_1, ..., head_h)W^O, where head_i = Attention(QW_i^Q, KW_i^K, VW_i^V). Where the projections are parameter matrices W_i^Q ∈ R^(d_model × d_k), W_i^K ∈ R^(d_model × d_k), W_i^V ∈ R^(d_model × d_v) and W^O ∈ R^(h·d_v × d_model).
  >
  >  head 구분은 입력 $$X$$가 아니라 가중치에 있다 — 그림 왼쪽 아래 인셋이 이 지점이다. 실제 구현에서는 $$(d_{model}, d_{model})$$ 가중치 하나로 한 번에 사영한 뒤 결과를 head 개수만큼 나누는데, 이는 head별 $$(d_{model}, d_k)$$ 가중치를 옆으로 이어 붙인 것과 같으므로 논문 정의와 동일한 연산이다.




* 임베딩과 가중치 행렬을 곱한다. 그림 상으로는 한 부분(*정확히는, `love` 단어에 대해 3번 head의 가중치를 적용하는 부분*)에 대해 Query, Key, Value를 얻는 과정만 표현했다. 문장의 모든 토큰, 그리고 모든 head에 대해 이 과정을 수행하면 된다.

 사실은 위의 과정이 모든 head에 대해 다 수행되므로, head별로 Query, Key, Value가 나온다. **Query, Key, Value가 head 개수만큼 있다**는 말이다. *~~(이를 어떻게든 나타내고 싶어 그림에서는 입체(?)적으로 표현하고자 했다.)~~* 또한, 각 Query, Key, Value가 문장 **자기 자신으로부터 나왔다**는 것이 *매우* 중요하다. (그래서 Self-Attention이다.)

<br>

 다음으로 Attention을 계산한다. 앞에서 살펴 보았던 *Self Dot-Product* 공식에 따라 진행하면 된다.

![Selfhead-Attention-QKV-calculation]({{site.url}}/assets/images/self-attention-qkv-att.png)

* Query와 Key 간에 dot product 연산을 한다.
* $$\sqrt{d_k}$$로 scale한다.
* softmax를 취한다. 그림에서 각 행끼리 더하면 1의 값이 나온다.
* Value와 dot product 연산을 한다.

 결과적으로 나오는 행렬은 **Attention Value**로, 각각의 Query가 각 Value에 얼마나 집중해야 할지 그 가중치를 나타내게 된다. *의미적으로 해석하자면*, 문장의 각 부분 부분을 Query로 볼 때, 그 **각 단어가 문장 내 다른 단어들에 얼마나 주목해야 할지, 그 주목도를 수치로 표현한 값**이다.

<br>

 다시 한 번 잊지 말아야 한다. 위와 같은 연산을 각각의 head에서 모두 수행한다. 따라서 Attention Value가 헤드의 개수만큼 있다. 이를 linear 네트워크를 거쳐서 최종적인 **Multi-head Attention Value**를 얻어 내자.

![Selfhead-Attention-concat]({{site.url}}/assets/images/self-attention-concat.png){: width="600"}{: .align-center}

<center><sup>그림에서는 나타내지 않았지만, linear 네트워크의 weight가 있고, 이것을Multi-head Attention Value 행렬과 dot product하면 된다.</sup></center>

<br>

 이렇게 각 문장이 *임베딩 + Positional Encoding + Self-Attention*을 과정을 거치고 난 후에는, 결과로 나오는 *Multi-head Attention Value*에 각 단어별로 어느 단어와 관련이 높은지가 수치로 표현된다. 논문에서는 예시 문장을 가지고 *Multi-head Attention Value*를 구한 뒤, 각 문장의 단어가 어떤 부분과 가장 연관성이 높은지를 다음과 같이 시각화했다. `its`라는 지칭어가 `Law`와 `application`라는 단어에 주목하고 있음을 알 수 있다.

![Selfhead-Attention-visualization]({{site.url}}/assets/images/self-attention-paper.png){: width="400"}{: .align-center}

<center><sup>출처: Attention is All You Need 논문</sup></center>

<br>

## 4. Masking

<br>

 이전까지의 과정을 요약해 Seq2Seq 모델과 트랜스포머 모델의 차이점을 생각해 보자. 트랜스포머 모델은 순환신경망 네트워크를 제거하고, Self-Attention 과정을 거쳐 문장의 정보를 효과적으로 추출해 낸다. 그런데 이 과정에서 문장 전체를 한번에 행렬 형태로 입력했다. 이 때문에 **학습 과정에 문제가 발생한다**.

 예측 시에는 아직 만들어지지 않은 단어를 볼 방법이 애초에 없다. 그런데 학습 시에는 정답 문장 전체를 한 번에 넣기 때문에, 가만히 두면 **자기 자신보다 뒤에 있는 단어까지 참고**해 버린다. 정답을 미리 보고 정답을 맞히는 셈이라, 학습할 때와 예측할 때의 조건이 어긋나게 된다.

 따라서 *순차적으로* 결과를 만들어내야 하는 디코더의 경우에는 **Masking** 기법을 사용해 학습한다. 특정 포지션 $$i$$에 단어가 들어 온다면, 그 뒤에 있는 위치의 단어들에 Attention을 주지 못하게 하는 것이다. 이렇게 하면 학습 시에도 예측 시와 똑같이 **이미 알고 있는 결과만 가지고** 다음 단어를 예측하게 된다.

> *참고* 
>
>  논문에서는 디코더에서는 Self-Attention 기법을 변형하여 적용한다고 표현되어 있다.
>
> > We also modify the self-attention
> > sub-layer in the decoder stack to prevent positions from attending to subsequent positions. This
> > masking, combined with fact that the output embeddings are offset by one position, ensures that the
> > predictions for position i can depend only on the known outputs at positions less than i.

<br>

아래 그림에서와 같이 상삼각행렬 부분에 마스킹을 씌우면 된다.

![Masking]({{site.url}}/assets/images/transformer-masking.png){: width="400"}{: .align-center}

<br>

 실제로 "가린다"는 것이 값을 지운다는 뜻은 아니다. Softmax를 취하기 **직전**의 Attention Score 행렬에서, 가려야 할 상삼각 위치에 $$-\infty$$ (구현상으로는 -1e9 같은 아주 작은 값)를 더한다. 그러면 Softmax를 통과한 뒤 그 자리의 가중치가 0이 되어, Value를 가중합할 때 아무 기여도 하지 못한다.

> We implement this inside of scaled dot-product attention by masking out (setting to $$-\infty$$) all values in the input of the softmax which correspond to illegal connections.

<br>