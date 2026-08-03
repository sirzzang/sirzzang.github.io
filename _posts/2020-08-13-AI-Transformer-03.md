---
title:  "[NLP] Transformer_3.Multi-head Attention_1"
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

## 1. Scaled Dot-Product Attention

<br>

### Attention



 Transformer 논문에서는 Attention 과정을 설명하기 위해 Query, Key, Value라는 개념을 사용한다. 이를 이해하기 위해 이전에  [Seq2Seq 모델](https://sirzzang.github.io/lecture/Lecture-Seq2Seq/){: .btn .btn--danger .btn--small} 에 Attention 메커니즘으로서 Dot-Product를 적용해 챗봇을 만들었던 내용을 돌이켜 보자.

 <br>

![seq2seq chatbot attention]({{site.url}}/assets/images/attention-seq2seq.png){: width="700"}{: .align-center}

<br>

 위의 그림에서 Attention Score를 계산하기 위해 입력으로 받은 현재 벡터를 **Query**라고 한다. 다른 단어와의 점수를 매기기 위해 기준으로 삼을 벡터이다. 주어진 Query와의 Attention Score를 계산할 때 대상이 되는 단어 벡터들을 **Key**라고 한다. 다른 위치의 단어 벡터이다. **Value**는 원래 문장의 각 단어가 벡터로 수치화된 값을 의미한다.

 Attention에 Query, Key, Value 개념만 입혀 다시 이해해 보자. 

|                       Attention Weight                       |                       Attention                        |
| :----------------------------------------------------------: | :----------------------------------------------------: |
| ![attention weight]({{site.url}}/assets/images/attention-weight.png) | ![attention]({{site.url}}/assets/images/attention.png) |

<br>

 왼쪽의 그림에서처럼 Query와 Key 간 Dot-Product 연산을 수행하고, Softmax를 취해 합이 1인 확률 값으로 변환해 주면, 각 Key에 대한 *Attention Weight*이 나온다. 기존의 설명에 Query, Key 개념만 입혀 다시 이해하자면, *Attention Weight*은 **Query가 각각의 Key에 어느 정도 Attention을 둬야 하는지를 나타내는 비중**이다. 그리고 오른쪽의 그림처럼 Value에 *Attention Weight*을 곱하면, Query와 유사한 Value일수록 더 높은 값을 가지는 *Attention Value*가 나온다.

 결과적으로, Transformer 논문에서의 Attention 개념은 Query, Key, Value 개념만 추가되었을 뿐, 기존의 Attention 개념과 크게 다르지 않다. 이 개념을 활용해 논문의 Attention 함수를 다시 이해해 보자면, **Query 벡터와 유사한 Key 벡터를 탐색해 그에 상응하는 Value를 반환하는 dictionary 자료형**과 같은 개념이다. 다만 일반적인 dictionary와 달리 키 하나만 골라 내지는 않는다. **모든 Key와의 유사도를 가중치로 삼아 Value 전체를 가중 평균**한다. 그래서 *soft*한 dictionary에 가깝다.



![attention-dict]({{site.url}}/assets/images/attention-dict.png){: width="300"}{: .align-center}



<br>



### Scale

<br>

 논문에서는 위의 Attention 과정에서 Dot-Product 결과를 차원에 루트를 씌운 값($$\sqrt{d_k}$$)으로 나눠 주어 Scaling한 뒤, Softmax 함수를 취해 주었다. **계산량과는 무관한 조치이다.**

 $$d_k$$ 가 커지면 내적 값의 분산이 $$d_k$$ 에 비례해 커진다. 그 상태로 Softmax를 통과시키면 가장 큰 값 하나에 확률이 거의 전부 몰리는 **포화 영역**으로 밀려 들어가는데, 이 영역에서는 gradient가 0에 가까워져 학습이 진행되지 않는다. $$\sqrt{d_k}$$ 로 나누는 것은 그 분산을 다시 1 수준으로 되돌려 놓는 조치이다.

> *참고* : Scaling이 필요한 이유
>
> We suspect that for large values of $$d_k$$, the dot products grow large in magnitude, pushing the softmax function into regions where it has extremely small gradients. (…) To illustrate why the dot products get large, assume that the components of q and k are independent random variables with mean 0 and variance 1. Then their dot product, $$q · k = \Sigma_{i=1}^{d_k} qiki$$, has mean 0 and variance $$d_k$$.

<br>

 결과적으로, 논문에 구현된 Scaled Dot-Product Attention의 공식은 다음과 같다.



$$Attention(Q, K, V) = softmax(\frac {QK^T} {\sqrt {d_k}})V$$



<br>



## 2. Multi-head Attention



 Attention을 수행하기 위해 입력 문장으로부터 `A)`에서와 같이 **Query, Key, Value를 만든다**.

 여기서 순서를 주의하자. 입력 하나를 셋으로 *쪼개는* 것이 아니다. **같은 입력을 서로 다른 세 개의 linear projection 네트워크**($$W^Q$$, $$W^K$$, $$W^V$$)에 각각 통과시켜, Query, Key, Value **세 벌을 만들어 내는** 것이다. Self-Attention에서 Q, K, V가 모두 같은 문장에서 나오면서도 서로 다른 값을 갖는 이유가 여기에 있다.

> *참고* : 디코더의 Q, K, V
>
>  이후에 더 자세히 살펴보겠지만, 트랜스포머 모델에서는 Multi-head Attention 레이어의 종류가 2가지이다. Self-Attention을 하는 레이어와 Encoder-Decoder Attention을 수행하는 레이어이다. 인코더는 전자만 사용하지만, 디코더는 전자와 후자 모두를 사용한다. 이 때, **디코더에서는** 레이어별로 Q, K, V 가 다음과 같이 달라진다.
>
> * **Encoder-Decoder Attention**: Q는 디코더의 이전 레이어 output, K와 V는 인코더의 output.
> * **Self-Attention**: Q, K, V 모두 **디코더**의 이전 레이어 output.
>
>  디코더의 Self-Attention은 말 그대로 디코더 자기 자신에 대한 Attention이므로, 인코더가 관여하지 않는다. 인코더의 출력이 디코더로 들어오는 통로는 Encoder-Decoder Attention 하나뿐이다.

<br>

이제 Transformer 모델의 또 다른 핵심인 **Multi-head Attention** 개념이 등장한다. 위의 *Scaled Dot-Product Attention*을 여러 개의 **head**로 나누어 진행하는 것이다.

 목적은 속도가 아니다. Attention을 한 번만 수행하면 문장 안에 있는 여러 종류의 관계가 **하나의 가중 평균으로 뭉개진다**. head를 나누면 각 head가 **서로 다른 표현 공간(representation subspace)**에서 서로 다른 종류의 관계를 따로 볼 수 있다. 문법적 관계에 주목하는 head와 지시 대상에 주목하는 head가 따로 생길 수 있다는 뜻이다.

> Multi-head attention allows the model to jointly attend to information from different representation subspaces at different positions. With a single attention head, averaging inhibits this.

 head들이 서로 독립이라 실제로 동시에 계산할 수 있는 것은 맞다. 그러나 그것은 이 구조가 갖게 된 *성질*이지, 도입한 *목적*이 아니다.

 교재의 예시에서와 같이 `"I love you so much"`라는 문장을 6차원으로 임베딩한 후, 3개의 head로 나누어 Attention을 진행한다고 하자. 

<br>

![multihead-attention-in-detail]({{site.url}}/assets/images/multihead-attention-3d.png){: width="600"}{: .align-center}

<br>

 임베딩 차원 $$d_{model}$$ 이 6이고 *head* 의 개수가 3일 때, head 하나가 담당하는 차원의 수를 $$d_k$$ 라고 하자. 여기서는 $$d_k = 6 / 3 = 2$$ 이다. 그러면 각각의 *head*는 Query에서 $$(seq\_len, d_{k})$$ 만큼의 행렬을 처리하게 된다. `"I love you so much"` 는 5개 토큰이므로 $$(5, 2)$$ 가 된다.

 행이 어휘 집합 크기가 아니라 **문장 안의 토큰 개수**라는 점에 주의하자. Attention은 어휘 전체를 훑는 연산이 아니라, **한 문장 안의 위치들 사이에서** 일어나는 연산이다.

> 쉽게 이해하자면, 쪼개진 각각의 부분을 `1)`, `2)`, `3)`이라 했을 때 각각의 head는 Query에서 `1)`, `2)`, `3)`의 부분을 맡아 처리하는 것이라고 볼 수 있다.



  그림에서는 Query 벡터 밖에 나타내지 않았지만, Key, Value 벡터에 대해서도 동일한 과정을 진행한다. Key, Value 벡터 모두 Query 벡터와 동일한 크기를 가지고 있을 것이므로, **각각의 head는  $$(seq\_len, d_{k})$$ shape의 Query, Key, Value에 대해 Scaled Dot-Product Attention**을 진행하게 된다.

<br>

  그 이후, 각각의 *head*가 Scaled Dot-Product Attention을 진행한 결과를 모두 concat한다. 그러면 Multi-head Attention을 거쳐 나오는 결과는 기존에 입력으로 들어온 벡터의 shape과 같아진다.  

 이렇게 Multi-head로 나누어 Scaled Dot-Product Attention을 진행한 결과를 다시 linear projection 네트워크에 통과시킨다.



> *참고* : Multi-head Attention에서의 $$d_k$$
>
>  논문에서는 $$d_k$$ 를 원래의 임베딩 차원인 $$d_{model}$$ 보다 작게, 정확히는 $$d_{model}/h$$ 로 설정했다. 여기서 주의할 것은, 이것이 계산량을 **낮추기** 위한 선택은 아니라는 점이다.
>
> > In this work we employ h = 8 parallel attention layers, or heads. For each of these we use dk = dv = dmodel/h = 64. Due to the reduced dimension of each head, the total computational cost is similar to that of single-head attention with full dimensionality.
>
>  인용문이 말하는 것은 비용이 "similar" 하다는 것이다. head를 8개로 늘렸으니 차원을 그대로 두면 계산량이 8배가 될 텐데, head마다 차원을 $$1/8$$ 로 줄였기 때문에 **전체 비용이 single-head로 full dimension을 쓸 때와 비슷한 수준에 머무른다**. 즉 $$d_k = d_{model}/h$$ 는 head를 늘리면서도 비용을 그대로 유지하기 위한 배분이지, $$d_k$$ 가 반드시 그 값이어야 할 구조적인 이유는 없다.



<br>