---
title:  "[NLP] Transformer_2.Positional Encoding"
excerpt: "<<Language Model>> Transformer 모델에 사용된 Positional Encoding을 알아 보자."
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

# *Transformer 이해하기_ Positional Encoding*

<br>

## 1. 개요





 트랜스포머 모델의 핵심 중 하나는 **RNN 네트워크를 제거**한 것이었다. RNN 네트워크는 모델 구조 자체가 시퀀스 데이터의 순서를 고려할 수 있게 설계된 것이지만, 이 네트워크를 *제거한 이상*  **입력 문장에서 단어의 순서를 고려할 수 있는 새로운 방법**이 필요하다. 그렇지 않다면 모델은 단어의 위치 정보를 알 수 없을 것이다.

 따라서 Transformer 모델은 입력 시퀀스의 단어를 임베딩한 뒤, **각 단어의 위치 정보**를 모델에 전달하기 위해 **Positional Encoding** 벡터를 사용한다. 쉽게 이해하자면, 임베딩 벡터에 위치 별로 특정한 패턴을 나타내는 Positional Encoding 벡터를 덧대는 것이다. Transformer 모델에서 인코더와 디코더의 입력은 **모두** Positional Encoding 단계를 거치게 된다.

> Since our model contains no recurrence and no convolution, in order for the model to make use of the order of the sequence, we must inject some information about the relative or absolute position of the tokens in the sequence. To this end, we add "positional encodings" to the input embeddings at the bottoms of the encoder and decoder stacks.

<br>



## 2. 방법



 Positional Encoding을 구현할 수 있는 방법은 여러 가지가 있다. **학습**을 통할 수도 있고(*learned*), 항상 **고정된 위치**의 값을 인코딩으로 사용할 수도 있다(*fixed*). 논문에서는 후자의 방법을 택한다. 학습을 통한다기 보다는, 조건을 만족하는 방식에 따라 각 단어의 위치에 일종의 번호를 부여한다는 의미이다.

 흥미로운 것은, 논문이 두 방법을 실제로 비교해 보고도 후자를 택했다는 점이다. 성능은 거의 같았는데, 고정된 값을 쓰면 **학습 때 본 것보다 긴 문장이 들어와도 인코딩 값을 계산해 낼 수 있기 때문**이다. 학습 방식은 학습 때 보지 못한 위치에 대한 벡터가 아예 존재하지 않는다.

> We also experimented with using learned positional embeddings instead, and found that the two versions produced nearly identical results. We chose the sinusoidal version because it may allow the model to extrapolate to sequence lengths longer than the ones encountered during training.

<br>

 Positional Encoding은 각 단어의 위치를 나타내기 때문에, 기본적으로 다음의 조건을 만족해야 한다.

* 각 문장에서 단어의 위치마다 **유일한 encoding 값**이 출력되어야 한다.
* 각 단어 위치 간 **거리가 일정**해야 한다.

<br>

 이제 인코딩 값을 어떻게 줄 수 있을지 생각해 보자. 먼저 스칼라를 사용할 수 있다.



![Scalar-Pos-Encoding]({{site.url}}/assets/images/pos_enc.png){: width="500"}{: .align-center} 





 *첫째*, 단순히 문장 내 단어 번호별로 숫자를 붙인다. `"I love you so much"`와 같은 문장의 경우, 각각의 단어의 위치를 나타내는 인코딩 숫자로서 `I`에 0, `love`에 1, `you`에 2와 같이 위치 인덱스를 사용하는 것이다.  그러나 문장이 길어질수록 **숫자가 커질 수 있고**, 인코딩 값의 **스케일이 맞지 않아** 훈련 시 사용했던 값보다 큰 값이 입력 값으로 들어오게 되면 문제가 발생한다. 

*둘째*, 문장 번호별로 숫자를 붙이고, 스케일 조정을 위해 단어의 개수로 나눠 준다. 위와 동일한 `"I love you so much"`  문장의 경우, `I`에 `0/5`, `love`에 `1/5`와 같은 방식으로 위치 인덱스를 사용하는 것이다. 각 단어를 나타내는 인코딩 간 거리가 동일하고, 스케일도 조정되어 있다. *그러나* 단어 임베딩 벡터의 차원 $$d_{model}$$ 이 *커질수록* 1차원의 벡터(이자 스칼라)로만 표현된 순서 정보는 의미 정보인 임베딩 벡터에 비해 **두각을 드러내지 못한다**.

<br>

 이를 통해 위의 두 조건에 더해, 각 Positional Encoding은 단어의 의미 정보와 함께 모델에 전달되더라도 **위치 정보를 부각할 수 있도록** ~~*(조금 더 쉽게 말하자면, 위치 정보가 묻히지 않도록)*~~ 이루어져야 한다는 것을 알 수 있다. 이를 위해 **임베딩과 같은 차원의 벡터**로 단어의 순서 정보를 인코딩한다.  

<br>

 그래서 단어 임베딩과 같은 차원의 벡터로 Positional Encoding을 구현하기 위해, 아래 그림에서와 같이 위치 정보를 찾아낼 수 있는 벡터를 찾아 나간다.

![positional encoding 2]({{site.url}}/assets/images/pos_enc_ex.png){: width="400"}{: .align-center} 



 우선, 이웃한 위치끼리의 *거리가 일정해야*  한다. 이를 위해 원점으로부터 초기 벡터를 찾고, 원점과 초기 벡터 간 동일한 거리를 갖는 벡터를 찾는 방식을 택한다. 따라서 이웃한 Positional Encoding 벡터 간 **거리가 동일**해야 한다.

 동시에, 두 위치 벡터의 **내적이 절대 위치가 아니라 두 위치 사이의 간격에만 의존**해야 한다. 3번과 5번의 내적, 10번과 12번의 내적이 같아야 한다는 뜻이다. 그래야 모델이 "몇 번째 단어인가"가 아니라 "얼마나 떨어져 있는가"를 읽어 낼 수 있다. (내적이 *0*이어야 한다는 뜻은 아니다. 위치 벡터들이 서로 무관해야 하는 것이 아니라, 관계가 **간격에 대해서만** 정해져야 한다는 조건이다.)

 또한, 각 벡터가 원점으로부터 발산하지 않아야 한다. 내적이 동일한 벡터를 찾아 나가기 위해 동일한 일직선 상에서 벡터를 선택한다고 생각해 보자. 나중에는 계산량이 무한히 커질 것이다. 따라서 모든 벡터의 **노름이 동일**하도록, 이전 벡터에서 다음 벡터를 선택할 때 일정 크기의 각 $$\theta$$을 줘서 선택한다.

 어떠한 방식이든 위의 조건을 만족하도록 위치 정보 벡터를 찾아 나가면, 그 결과로 도출되는 각각의 벡터를 Positional Encoding 값으로 사용할 수 있다.



<br>

 정리하면 다음과 같다. 인코더 입력 문장이 $$d_{model}$$ 차원의 벡터로 임베딩된다고 하자. Positional Encoding은 **1)** 위와 같은 방법론을 따라 선택된, **2)** 임베딩된 벡터와 같은 $$d_{model}$$ 차원 공간에서의 벡터로서, **3)** 각 단어 임베딩과 합쳐져 문장 내 위치 정보를 표현하게 된다. **임베딩 결과에 Positional Encoding을 통해 위치 정보를 추가**하는 것이다.

> Similarly to other sequence transduction models, we use learned embeddings to convert the input tokens and output tokens to vectors of dimension $$d_{model}$$. (…) The positional encodings have the same dimension $$d_{model}$$ as the embeddings, so that the two can be summed.

<br>

> *참고* : 임베딩에 $$\sqrt{d_{model}}$$ 을 곱하는 이유
>
>  논문은 임베딩 레이어의 출력에 $$\sqrt{d_{model}}$$ 을 곱한 뒤 Positional Encoding을 더한다. 다만 논문 본문에 그 이유는 나와 있지 않다. 통상적으로는 두 값의 스케일을 맞추기 위한 것으로 해석한다. Positional Encoding 값은 $$sin$$, $$cos$$ 이라 항상 -1에서 1 사이인데, 임베딩 가중치는 분산이 $$1/d_{model}$$ 정도가 되도록 초기화하는 것이 보통이라 값의 크기가 훨씬 작다. 그대로 더하면 위치 정보가 의미 정보를 덮어 버릴 수 있으므로, $$\sqrt{d_{model}}$$ 을 곱해 임베딩 쪽 분산을 1 부근으로 끌어올린다는 설명이다.
>
> > In the embedding layers, we multiply those weights by $$\sqrt{d_{model}}$$.

<br>



## 3. 구현



 논문은 위와 같은 방법론에 따라 이상적인 조건을 만족하는 Positional Encoding 기술을 구현한다. 

<br>
$$
PE_{(pos, 2i)} = sin(pos/10000 ^ {2i/d_{model}}) \\
PE_{(pos, 2i+1)} = cos(pos/10000 ^ {2i/d_{model}})
$$



 $$pos$$ 는 각 단어가 문장 내에서 몇 번째 단어인지를 의미하며, $$i$$ 는 임베딩 벡터의 차원에서의 순서를 나타낸다. 예컨대,  `"I love you so much"`의 문장 내 각 단어를 128차원으로 임베딩했다면 $$pos$$ 는 0부터 4까지,  $$i$$ 는 0부터 127까지가 될 것이다.

 $$sin$$, $$cos$$ 함수를 이용하기 때문에, 각 값이 모두 -1에서 1 사이로 통일되어 벡터가 발산하지 않는다. 또한, 홀수 인덱스의 경우 $$cos$$ 함수의 주기를, 짝수 인덱스의 경우 $$sin$$ 함수의 주기를 이용하며, $$i$$ 가 커질수록 주기가 길어지기 때문에 각각의 값들이 모두 다르게 인코딩된다.

 상대적인 위치 정보를 전달할 수 있는 근거는 $$i$$ 가 증가하는 폭이 일정하다는 데 있는 것이 아니다. **$$PE_{pos+k}$$ 를 $$PE_{pos}$$ 의 선형 변환으로 쓸 수 있다**는 데 있다. 간격 $$k$$ 를 고정하면 그에 대응하는 회전 행렬이 하나 정해지고, 그 행렬은 $$pos$$ 가 무엇이든 동일하다. 그래서 모델이 절대 위치와 무관하게 "$$k$$ 만큼 떨어져 있다"를 일관된 방식으로 읽어 낼 수 있다. 논문도 이 성질을 sinusoid를 고른 이유로 든다.

> We chose this function because we hypothesized it would allow the model to easily learn to attend by relative positions, since for any fixed offset $$k$$, $$PE_{pos+k}$$ can be represented as a linear function of $$PE_{pos}$$.

 (자세한 수학적인 증명이 ~~나중에~~ 알고 싶어 진다면, [여기](https://kazemnejad.com/blog/transformer_architecture_positional_encoding/)를 참고하자.)

<br>

 그렇다면 이것을 코드로 어떻게 구현할 수 있는지 알아 보자. 논문을 발표한 Google에서 공개한 Positional Encoding 코드는 다음과 같다.

```python
import numpy as np

def get_angles(pos, i, d_model):
    angle_rates = 1 / np.power(10000, (2 * (i // 2)) / np.float32(d_model))
    return pos * angle_rates

def positional_encoding(position, d_model):
    angle_rads = get_angles(np.arange(position)[:, np.newaxis],
                            np.arange(d_model)[np.newaxis, :],
                            d_model)

    # apply sin to even indices in the array; 2i
    sines = np.sin(angle_rads[:, 0::2])    
    # apply cos to odd indices in the array; 2i+1
    cosines = np.cos(angle_rads[:, 1::2])
    
    pos_encoding = np.concatenate([sines, cosines], axis=-1)

    return pos_encoding
```



 `get_angles` 함수를 통해 단어의 위치에 따라 $$sin$$, $$cos$$ 함수 안에 들어갈 중심각의 크기를 구한다. 임베딩 벡터와 같은 크기의 텐서를 만들어야 하는데, 이 텐서의 행은 문장의 길이, 열은 임베딩 벡터의 차원이 될 것이다. `positional encoding`에서 `pos`를 행으로, `i`를 열로 하는 행렬로 만들고 각 위치를 전달한다. `sines`와 `cosines`에서는 각각 `i`가 0부터 시작해 2씩 증가하는 짝수 위치의 인덱스, 1부터 시작해 2씩 증가하는 홀수 위치의 인덱스에 대해 $$sin$$ 값과 $$cos$$ 값을 구한다. 그리고 각각의 값을 concat한다.

> *참고* : 위 수식과 이 코드는 배치가 다르다
>
>  논문의 수식은 짝수 차원에 $$sin$$, 홀수 차원에 $$cos$$ 을 **번갈아** 배치한다. 그런데 이 코드는 `np.concatenate` 로 이어 붙이기 때문에 **앞 절반이 $$sin$$, 뒤 절반이 $$cos$$** 이 된다. 아래에서 확인할 출력값도 이 배치를 따른다.
>
>  차원의 *순서*만 다를 뿐 각 위치에 담기는 값의 집합은 같고, 뒤따르는 레이어의 가중치는 어차피 학습되는 것이라 결과에는 차이가 없다. 다만 수식과 코드가 다르다는 점은 알고 넘어가자.

<br>

 실제로 이렇게 만들어진 각 벡터가 무엇인지, 그 벡터 간 거리와 각 벡터의 크기는 일정한지 확인해 보자.

 먼저, 위에서 예로 든 `"I love you so much"`의 문장을 6차원의 벡터로 임베딩하고, 그에 대한 Positional Encoding 벡터를 구해 보자.

```python
PE = positional_encoding(5, 6)
print(PE.round(3))

# Positional Encoding 벡터
[[ 0.     0.     0.     1.     1.     1.   ]
 [ 0.841  0.046  0.002  0.54   0.999  1.   ]
 [ 0.909  0.093  0.004 -0.416  0.996  1.   ]
 [ 0.141  0.139  0.006 -0.99   0.99   1.   ]
 [-0.757  0.185  0.009 -0.654  0.983  1.   ]]
```

<br>

 그리고 각 벡터의 크기, 내적을 구해 보자.

```python
from sklearn.metrics.pairwise import euclidean_distances

for i in range(PE.shape[0] - 1):
    d = euclidean_distances(PE[i].reshape(1,-1), PE[i+1].reshape(1,-1))
    norm = np.linalg.norm(PE[i])
    dot = np.dot(PE[i], PE[i+1])
    print("%d - %d : distance = %.4f, norm = %.4f, dot = %.4f" % (i, i+1, d[0,0], norm, dot))
```



  **이웃한 위치끼리는** 모두 동일한 것을 알 수 있다.

```python
# 각 벡터 간 거리, 각 벡터의 노름, 내적
0 - 1 : distance = 0.9600, norm = 1.7321, dot = 2.5392
1 - 2 : distance = 0.9600, norm = 1.7321, dot = 2.5392
2 - 3 : distance = 0.9600, norm = 1.7321, dot = 2.5392
3 - 4 : distance = 0.9600, norm = 1.7321, dot = 2.5392
```

> *주의* : 위 결과가 보여 주는 것과 보여 주지 않는 것
>
>  위 코드는 `PE[i]` 와 `PE[i+1]`, 즉 **간격이 1인 쌍만** 계산한다. 간격을 2, 3으로 벌려 보면 거리와 내적 값이 달라진다. 그리고 달라야 정상이다. 모든 쌍이 등거리라면 위치 사이의 원근을 구분할 수 없기 때문이다.
>
>  정확한 성질은 이렇다. **간격 $$k$$ 를 고정하면, 문장의 어느 지점에서 재든 거리와 내적이 같다.** `PE[0]`-`PE[3]` 과 `PE[10]`-`PE[13]` 이 같은 값을 갖는다는 뜻이다. 위 출력은 그 중 $$k=1$$ 인 경우만 확인한 것이다. 노름은 위치·간격과 무관하게 항상 $$\sqrt{d_{model}/2}$$ 로 동일하다. (위 예시는 $$d_{model} = 6$$ 이므로 $$\sqrt{3} = 1.7321$$ 이다.)

<br>

 이제 정말 각 벡터가 동일한 간격을 보이는지, 원점에서 어느 같은 거리에 있는지 확인해 보자. 위와 같은 예에서는 6차원이므로 시각화하기 어렵기 때문에 2차원 그림을 그려 본다.

```python
import matplotlib.pyplot as plt

PE = positional_encoding(32, 2)
plt.figure(figsize=(8, 8))
plt.plot(PE[:, 0], PE[:, 1], marker='o')
plt.show()
```



![2d-positional-encoding]({{site.url}}/assets/images/pos_enc_1.png){: width="350"}{: .align-center} 

<center><sup> 실제로 뺑글 뺑글 원을 그리며 돈다!</sup></center>

<br> 

3차원으로도 나타내 보자.

```python
fig = plt.figure()
ax = fig.gca(projection='3d')

PE = positional_encoding(500, 3)
plt.figure(figsize=(12, 12))
ax.scatter(PE[:, 0], PE[:, 1], PE[:, 2], marker='o')
plt.show()
```



![3d-positional-encoding]({{site.url}}/assets/images/pos_enc_2.png){: width="400"}{: .align-center} 

<center><sup> 실제로 뺑글 뺑글하게 입체 도형을 만들며 돈다!</sup></center>

<br>



> *참고* 
>
>  Positional Encoding을 반드시 위의 공식으로만 구현할 수 있는 것은 아니다. 또 다른 Positional Encoding에 대해 다른 논문들도 많이 있다. 기본적으로 각 벡터 간 등간격 거리(**equidistant**)가 되도록 하는 게 조건이다. 

<br>