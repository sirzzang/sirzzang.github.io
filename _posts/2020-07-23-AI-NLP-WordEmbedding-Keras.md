---
title:  "[NLP] Word Embedding"
excerpt: "<<Embedding>> 지도학습 기반의 단어 임베딩 기법을 알아 보자."
toc: true
toc_sticky: true
categories:
  - AI
header:
  teaser: /assets/images/blog-AI.jpg
tags:
  - NLP
  - Keras
  - Embedding
  - IMDB
use_math: true
last_modified_at: 2020-07-27
---



<sup> 출처가 명시되지 않은 모든 자료(이미지 등)는 [조성현 강사님](https://blog.naver.com/chunjein)의 강의 및 강의 자료를 기반으로 합니다.</sup> <sup>[Github Repo](https://github.com/sirzzang/LECTURE/tree/master/인공지능-자연어처리(NLP)-기반-기업-데이터-분석/조성현 강사님/04. NLP/NLP 실습/20200724)</sup>

<sup>Tensorflow : 2.2.0</sup>



# _단어 임베딩-Keras Embedding Layer_

<br>

 

 자연어에서 의미를 갖는 가장 작은 단위는 '단어'이다. 따라서 *단어를 어떻게 수치화할 것인가*는 NLP에서 중요한 문제이다. 이전에 살펴본 것과 같은 `BoW`, `Doc2Bow`, `TF-IDF`는 **통계** 기반의 수치화 방법으로, 빈도(수치)를 가지고 단어를 벡터로 수치화한다.

 그러나 이와 같은 기법으로는 단어의 의미를 수치화된 벡터에 투영하지 못한다는 한계가 있다. 따라서 단어에 의미를 부여해 수치화하기 위해 **임베딩** 기법이 제안되었다.

 지도학습 기반의 단어 임베딩 방법 중 가장 기본적인 Word Embedding 방법을 알아 보자. Keras의 Embedding 레이어를 활용한다.

<br>

## 1. 아키텍쳐

 

 기본적으로 단어 임베딩은 **1)** 자연어 데이터를 가지고 다른 문제를 풀기 위해, **2)** 자연어를 수치화하는 과정에서, **3)** 의미를 투영하기 위해 사용된다. 따라서 뒷단에 나오는 문제를 풀기 위한 모델에서, 앞단에 *임베딩을 위한 레이어로서* 삽입된다고 이해하면 된다. 

 `"I love you very much."`라는 문장을 긍정인지 부정인지 분류하는 이진 분류 문제를 푼다고 하자. 이 때 Keras Embedding 레이어가 어떻게 작동하는지에 초점을 맞추어 다음의 모델 아키텍쳐를 확인하자.

<br>

![embedding-architercure]({{site.url}}/assets/images/keras-embedding.png){: width="500"}{: .align-center}

<br>

 전체적으로 `입력 ~ Embedding 레이어 ~ 분류 작업을 수행하기 위한 신경망`의 구조를 갖는다.

 임베딩 이전 단계에 어휘 사전(Vocabulary)을 이미 구축했다고 가정한다. 구축한 어휘 집합의 크기가 500이라고 하자. 어휘 사전 내 각각의 어휘 인덱스에 맞추어 원핫 인코딩된 **원핫 벡터**가 Embedding 레이어에 입력된다. 따라서 Embedding 레이어의 입력 데이터 shape은 `(문장 길이, vocabulary size)`가 된다. 위의 예시에서는 `"I love you very much."`의 길이가 5이므로, `(5, 500)`가 된다. *일반적으로는* 문장이 **여러 개** 있기 때문에, `(문장 개수, 문장 길이, vocabulary size)`의 shape을 갖는 *3차원* 데이터가 입력된다.

<br>

 임베딩을 통해 각각의 단어를 64차원으로 나타내고 싶다고 하자. 그러면 Embedding 레이어의 출력 뉴런 수는 64가 되어야 한다. 따라서 Embedding 레이어에 `(500, 64)` 크기의 가중치 행렬이 만들어진다. 그렇다면, 단어를 임베딩한다는 것은 **학습을 통해** Embedding 레이어의 *가중치 행렬 값들을 **업데이트*** 한다는 의미가 된다. 

 위의 예시에서는 `"I love you very much."`의 각 단어들(`I`, `love`, `you`, `very`, `much`)을 나타내는 500차원의 벡터가 학습이 완료된 가중치 행렬과 *행렬곱이 수행*될 것이다. 그 결과 각 단어 1개는 64차원의 숫자 벡터가 된다. 그리고 문장 전체의 관점에서 보자면, `(5, 500)` 행렬과 `(500, 64)` 행렬이 곱해지고, 그 출력으로서 `(5, 64)` shape의 행렬이 나오게 된다. *일반적으로* 문장이 **여러 개** 있는 경우를 생각해 본다면, Embedding 레이어의 출력은 `(문장 개수, 문장 길이, Embedding Size)`의 shape을 갖는 *3차원* 데이터가 된다.

<br>

 그렇다면 가중치 행렬을 업데이트하기 위한 학습은 어떻게 이루어지는 것일까?  기본적으로 Keras의 Embedding 레이어는 문장 데이터 자체에서 의미를 뽑아 낸다기 보다, target 벡터를 가장 잘 맞출 수 있는 방향으로 학습한다. 결국 임베딩된 데이터를 감성분석, 기계번역 등 다른 작업을 수행하기 위한 신경망에 주입하고, target을 잘 맞출 수 있는 방향으로 **오류를 역전파해 나간다**는 의미다. 따라서 모델을 컴파일하고, `fit`을 통한 학습이 완료되어야 임베딩이 이루어지게 된다는 의미이다.



> *참고*
>
>  모델 구조 상, Embedding 레이어를 거치기 전후의 데이터가 3차원 형태이기 때문에, 뒷단의 작업을 수행하기 위한 네트워크로는 3차원 데이터를 다룰 수 있는 LSTM, CNN 등의 모델이 적합하다. 

<br>

 한편, 위에서는 설명하지 않았지만 문장이 여러 개 있는 경우를 고려한다면, **패딩** 작업이 필요하다. 각 문장별로 길이가 모두 다르기 때문에, 문장의 길이를 동일하게 맞추어 절삭(*truncate*)하거나 `0` 등 의미 없는 숫자로 채우는(*pad*) 것이다. 두 작업을 모두 통칭해 패딩이라고 하는데, Keras에서는 `pad_sequences` 함수로 쉽게 구현할 수 있다.



> *참고* : 시계열 데이터에서의 패딩
>
> 
>
>  이전에 LSTM, CNN 모델 공부하면서 패딩에 대해 공부하지 않았다. 사실, 원래 시계열 데이터를 다루며 `timestep`을 동일하게 맞춰준 작업이 NLP에서의 패딩이라고 생각하면 된다. 동일한 `timestep` 만큼의 데이터를 입력했기 때문에, 굳이 입력 데이터의 길이가 달라질 고민을 하지 않아도 되는 것이다.
>
> 
>
> ```python
> X_input_1 = Input(batch_size=(None, n_steps, n_features)) # 기존 방식 = 패딩됨.
> X_input_2 = Input(batch_size=(None, None, n_features)) # 패딩 안 함.
> ```
>
>  
>
>  기존에 우리가 다루었던 방식과 달리 `X_input_2`와 같이 모델을 구성해도 된다. 모델 내부에서 알아서 recurrent step을 적용한다. 그러나 이 경우 배치 사이즈가 일정하게 고정되지 않아 학습에 시간이 오래 걸린다. **특히** 단어 임베딩의 경우는 일정한 사이즈로 배치 데이터를 구성해주어야 하기 때문에, 패딩을 진행해주는 것이 적합하다.

<br>

## 2. 특징



 수행하고자 하는 작업에 맞게 단어의 의미를 반영하여 수치화할 수 있다. 그러나 한편으로는, 수행하고자 하는 작업에*만* 맞는, 특화된 수치 벡터가 나올 수도 있다. 또한 형태적으로는 같으나 의미가 다른 단어를 같은 벡터로 수치화하고, corpus가 수정될 때마다 계속해서 학습해야 한다는 단점이 있다. 또한, vocabulary에 없는 단어(OOV, *Out of Vocabulary*)들의 경우 학습하지 못한다.

<br>

## 3. 구현



 IMDB 데이터셋의 감성분석을 수행하는 CNN 모델을 구성하자. *~~사실 설명은 길었지만, Embedding 레이어 함수 하나 추가하면 된다. 그리고 역시나, shape을 잘 맞춰야 한다.~~*

```python
# 모듈 불러오기
from tensorflow.keras.datasets import imdb
from tensorflow.keras.models import Model
from tensorflow.keras.layers import Input, Dense, Embedding, Dropout
from tensorflow.keras.layers import Conv1D, GlobalMaxPooling1D
from tensorflow.keras.optimizers import Adam
from tensorflow.keras.callbacks import EarlyStopping
from tensorflow.keras.preprocessing.sequence import pad_sequences
import matplotlib.pyplot as plt
from sklearn.metrics import accuracy_score
from sklearn.metrics.pairwise import euclidean_distances
import numpy as np

# 파라미터 설정
max_features = int(input('단어 빈도 threshold 설정: ')) # 최대 단어 출현 빈도 수
max_length = int(input('문장 최대 길이 설정: ')) # 패딩 길이

# 데이터 로드
(X_train, y_train), (X_test, y_test) = imdb.load_data(num_words=max_features)

# 패딩
X_train = pad_sequences(X_train, maxlen=max_length)
X_test = pad_sequences(X_tst, maxlen=max_length)

# 모델 파라미터
n_embed = int(input('임베딩 차원 설정: '))
n_kernels = int(input('컨볼루션 필터 수 설정: '))
s_kernels = int(input('컨볼루션 필터 사이즈 설정: '))
n_hidden = int(input('은닉 노드 수 설정: '))
EPOCHS = int(input('학습 에폭 수 설정: '))
BATCH = int(input('배치 사이즈 설정: '))

# 1) 모델 네트워크
X_input = Input(batch_shape=(None, max_length))
X_embed = Embedding(input_dim=max_features, input_length=max_length, output_dim=n_embed)(X_input) # 임베딩 레이어
X_embed = Dropout(0.5)(X_embed)
X_conv = Conv1D(filters=n_kernels, kernel_size=s_kernels, strides=1, padding='valid', activation='relu')(X_embed)
X_pool = GlobalMaxPooling1D()(X_conv)
X_dense = Dense(n_hidden, activation='relu')(X_pool)
X_dense = Dropout(0.5)(X_dense)
y_output = Dense(1, activation='sigmoid')(X_dense)

# 2) 모델 구성
model = Model(X_input, y_output)
embed_model = Model(X_input, X_embed)
model.compile(loss='binary_crossentropy', optimizer=Adam(learning_rate=0.002))
print("============ 모델 전체 구조 ============")
print(model.summary())

# 3) 학습
es = EarlyStopping(monitor='val_loss', patience=4, verbose=1)
hist = model.fit(X_train, y_train,
                 batch_size=BATCH,
                 epochs=EPOCHS, 
                 validation_data=(X_test, y_test),
                 callbacks=[es])

# loss 시각화
plt.plot(hist.history['loss'], label='Train Loss')
plt.plot(hist.history['val_loss'], label='Test Loss')
plt.legend()
plt.xlabel('epochs')
plt.ylabel('loss')
plt.title('Loss Trajectory', size=15)
plt.show()

# 4) 예측 후 성능 확인
y_pred = model.predict(X_test)
y_pred = np.where(y_pred > 0.5, 1, 0) 
print(f"Test Accuracy: {accuracy_score(y_test, y_pred)}")

# 5) 임베딩 결과 확인
W_embed = np.array(model.layers[1].get_weights())
W_embed = W_embed.reshape(max_features, n_embed)
print(W_embed)
```

<br>

**1), 2) 모델 네트워크 및 모델 구성**

 역시나 shape이 중요하다. Embedding 레이어의 파라미터로 주어지는 `input_length`는 각 문장 시퀀스의 길이, `input_dim`은 어휘 집합의 수, 즉, 기존 단어 벡터의 차원 수가 된다. `output_dim`은 Embedding 레이어를 통과한 후 각 단어를 몇 차원의 벡터로 나타낼 것인지를 의미한다. CNN 네트워크 및 은닉층의 파라미터는 임의로 구성했다. 다만, IMDB 감정분석 문제가 이진 분류 문제이므로, 출력층의 활성화 함수로 `sigmoid` 함수를 사용한다.

 모델은 2개 구성한다. `model`은 실제 컴파일될 모델로서 임베딩 후 IMDB 감성분석을 수행할 모델이다. `embed_model`은 학습 컴파일한 모델의 학습을 완료한 후, 결과를 확인하기 위해 구성했다. 학습할 모델의 전체 구조는 다음과 같다.

 Embedding 레이어에는 bias 파라미터가 없다. 따라서 `Parma #`을 계산할 때 주의하자.



```python
============ 모델 전체 구조 ============
Model: "model_5"
_________________________________________________________________
Layer (type)                 Output Shape              Param #   
=================================================================
input_5 (InputLayer)         [(None, 400)]             0         
_________________________________________________________________
embedding_4 (Embedding)      (None, 400, 60)           360000    
_________________________________________________________________
dropout_8 (Dropout)          (None, 400, 60)           0         
_________________________________________________________________
conv1d_4 (Conv1D)            (None, 398, 260)          47060     
_________________________________________________________________
global_max_pooling1d_4 (Glob (None, 260)               0         
_________________________________________________________________
dense_8 (Dense)              (None, 300)               78300     
_________________________________________________________________
dropout_9 (Dropout)          (None, 300)               0         
_________________________________________________________________
dense_9 (Dense)              (None, 1)                 301       
=================================================================
Total params: 485,661
Trainable params: 485,661
Non-trainable params: 0
_________________________________________________________________
None
```



<br>

**3), 4) 학습 및 성능 확인**

 patience를 4로 해서 조기 종료 조건을 줬다. ~~*(의미가 있는지는 모르겠지만)*~~ 학습률을 바꿔 보다가 0.002로 했을 때, 가장 높은 예측 정확도를 얻었다. 전부 다 88% 초반대였는데, 0.002로 했을 때 0.8863의 정확도를 기록했다. 이 때 loss 변화 추이는 다음과 같다.



![IMDB]({{site.url}}/assets/images/imdb-loss.png){: width="400"}{: .align-center}

<br>

**5) 임베딩 가중치 행렬 확인**

 입력 데이터 shape이 3차원이기 때문에, Embedding 레이어를 통과한 가중치 행렬도 역시 3차원이 된다. 확인하기 편한 형태로 바꿔 주기 위해 2차원으로 reshape한다. 60차원으로 각 단어를 임베딩했을 때 임베딩 가중치 행렬을 확인하면 다음과 같다.



```python
[[ 0.00901345  0.0538222   0.04109327 ...  0.03056829 -0.02638648
  -0.04607034]
 [-0.0940984   0.01635588 -0.05697206 ... -0.05675483 -0.22963212
  -0.10466143]
 [-0.01744831 -0.03595665 -0.07113352 ...  0.05882598  0.0396422
   0.08856237]
 ...
 [-0.1342757  -0.04574351 -0.10624611 ...  0.08260629  0.07482476
   0.12663783]
 [ 0.34726202  0.01347591 -0.2104143  ...  0.03326342 -0.33965907
   0.13740674]
 [ 0.14605394  0.04584099 -0.09383202 ... -0.1666545  -0.1469388
  -0.04617616]]
```

<br>

<br>

 임베딩 가중치 행렬만을 확인하는 것으로는 의미가 없다. 실제로 각 문장이 어떻게 바뀌는지를 확인해 보자. IMDB 데이터 셋에서 어휘 사전(vocabulary)을 가져 오고, data를 원래 데이터로 변환해 주는 작업이 필요하다.



```python
# 6) vocabulary 생성
word2idx = imdb.get_word_index() # 기존 imdb vocabulary
idx2word = dict((v, k) for k, v in word2idx.items())
idx2word = dict((idx+3, word) for idx, word in idx2word.items())
idx2word[0] = '<PAD>' # 패딩
idx2word[1] = '<START>' # 문장 시작
idx2word[2] = '<OOV>' # OOV
idx2word[3] = '<INV>' # invalid 문자
word2idx = dict((k, v) for v, k in idx2word.items())

# 7) 원래 문장으로 변환하는 함수
def decode_sent(sent):
    x = [idx2word[s] for s in sent]
    return ' '.join(x)

# 8) 첫 번째 문장의 임베딩 결과 확인
print("============ 원래 문장 확인 ============")
print(decode_sent(X_train[0]))
print('')
embed_sent = embed_model.predict(X_train[0].reshape(1, max_length)) 
print("============ 임베딩된 문장 확인 ============")
print(embed_sent.shape)
print(embed_sent)

# 9) 예시 단어 간 거리 측정
father = W_embed[word2idx['father']]
mother = W_embed[word2idx['mother']]
daughter = W_embed[word2idx['daughter']]
son = W_embed[word2idx['son']]
print("============ 단어 간 유클리드 거리 측정 ============")
print(euclidean_distances([father, mother, daughter, son]))
```

<br>

**6) vocabulary**

 Keras의 IMDB 데이터셋은 *빈도* 순으로 나열된 어휘 사전을 사용한다. `get_word_index`를 통해 어휘 사전을 가져 오면, `word : index` 구조로 어휘 집합이 배열되어 있음을 알 수 있다. 그런데 이 어휘 집합 안에는 패딩, 문장 시작, OOV, 유효하지 않은 문자를 표시하는 인덱스가 없다. 따라서 어휘 사전 구조를 `index : word` 형태로 바꾸고, `index`를 3씩 더해준 뒤, `0`, `1`, `2`, `3`에 특수 단어를 매핑해 추가한다. 그리고 다시 원래의 `word : index` 구조로 문장을 바꾼다.



**7) 문장 해석 함수**

 원래 IMDB 데이터셋에서 가져 온 데이터가 수치로 인코딩된 것이었기 때문에, 위에서 만든 vocabulary 사전 구조에 맞게 문장을 해독하는 함수를 만든다.



**8) 문장 임베딩 결과 확인**

 샘플 문장을 하나 가져 온다. 모델 입력 형태에 맞게 형태를 바꿔준 뒤, 원래 문장과 임베딩된 문장 벡터를 확인한다. 원래 문장을 해독한 결과, 패딩이 이루어져 앞에 `<PAD>`가 붙어 있음을 볼 수 있다. `decode_sent` 함수가 잘 작동한다! 인코딩된 문장 벡터는, 그냥 그 수치대로 이해해야 할 듯하다.



```python
============ 원래 문장 확인 ============
<PAD> <PAD> <PAD> <PAD> <PAD> <PAD> <PAD> <PAD> <PAD> <PAD> <PAD> <PAD> <PAD> <PAD> <PAD> <PAD> <PAD> <PAD> <PAD> <PAD> <PAD> <PAD> <PAD> <PAD> <PAD> <PAD> <PAD> <PAD> <PAD> <PAD> <PAD> <PAD> <PAD> <PAD> <PAD> <PAD> <PAD> <PAD> <PAD> <PAD> <PAD> <PAD> <PAD> <PAD> <PAD> <PAD> <PAD> <PAD> <PAD> <PAD> <PAD> <PAD> <PAD> <PAD> <PAD> <PAD> <PAD> <PAD> <PAD> <PAD> <PAD> <PAD> <PAD> <PAD> <PAD> <PAD> <PAD> <PAD> <PAD> <PAD> <PAD> <PAD> <PAD> <PAD> <PAD> <PAD> <PAD> <PAD> <PAD> <PAD> <PAD> <PAD> <PAD> <PAD> <PAD> <PAD> <PAD> <PAD> <PAD> <PAD> <PAD> <PAD> <PAD> <PAD> <PAD> <PAD> <PAD> <PAD> <PAD> <PAD> <PAD> <PAD> <PAD> <PAD> <PAD> <PAD> <PAD> <PAD> <PAD> <PAD> <PAD> <PAD> <PAD> <PAD> <PAD> <PAD> <PAD> <PAD> <PAD> <PAD> <PAD> <PAD> <PAD> <PAD> <PAD> <PAD> <PAD> <PAD> <PAD> <PAD> <PAD> <PAD> <PAD> <PAD> <PAD> <PAD> <PAD> <PAD> <PAD> <PAD> <PAD> <PAD> <PAD> <PAD> <PAD> <PAD> <PAD> <PAD> <PAD> <PAD> <PAD> <PAD> <PAD> <PAD> <PAD> <PAD> <PAD> <PAD> <PAD> <PAD> <PAD> <PAD> <PAD> <PAD> <PAD> <PAD> <PAD> <PAD> <PAD> <PAD> <PAD> <PAD> <PAD> <PAD> <PAD> <PAD> <PAD> <PAD> <PAD> <PAD> <PAD> <PAD> <START> this film was just brilliant casting location scenery story direction everyone's really suited the part they played and you could just imagine being there robert <OOV> is an amazing actor and now the same being director <OOV> father came from the same scottish island as myself so i loved the fact there was a real connection with this film the witty remarks throughout the film were great it was just brilliant so much that i bought the film as soon as it was released for <OOV> and would recommend it to everyone to watch and the fly fishing was amazing really cried at the end it was so sad and you know what they say if you cry at a film it must have been good and this definitely was also <OOV> to the two little boy's that played the <OOV> of norman and paul they were just brilliant children are often left out of the <OOV> list i think because the stars that play them all grown up are such a big <OOV> for the whole film but these children are amazing and should be praised for what they have done don't you think the whole story was so lovely because it was true and was someone's life after all that was shared with us all

============ 임베딩된 문장 확인 ============
(1, 400, 60)
[[[ 0.0088832  -0.0436639   0.07654434 ...  0.04261591 -0.00109518
    0.04554922]
  [ 0.0088832  -0.0436639   0.07654434 ...  0.04261591 -0.00109518
    0.04554922]
  [ 0.0088832  -0.0436639   0.07654434 ...  0.04261591 -0.00109518
    0.04554922]
  ...
  [ 0.05499315  0.07495009 -0.06593661 ...  0.02310263 -0.03915591
    0.03818268]
  [ 0.17379531 -0.04260442 -0.03142205 ...  0.01213738 -0.00449449
   -0.17220676]
  [-0.06178711  0.07810801  0.01260059 ...  0.11740308 -0.0989247
    0.01683315]]]
```

<br>

**9) 예시 단어 간 거리 측정**

 어휘 사전에서 `father`, `mother`, `daughter`, `son`의 인덱스를 찾는다. 그 인덱스가 가중치 행렬에 그대로 들어 있다. 따라서 그 인덱스를 임베딩 가중치 행렬에서 찾으면, 해당하는 단어가 어떻게 임베딩되었는지를 볼 수 있다.



> *더 생각해볼 점*
>
>  수업 들을 때는 몰랐는데, 3을 더해서 밀고 `word2idx`를 생성했으니까 여기서 결과 확인할 때는 3을 빼줘야 하는 게 아닌가 싶은 생각이 든다. ~~지금은 일단 좀 졸리니까~~ 다시 고민해 볼 것!



 IMDB 데이터셋 감성 분석 문제를 풀기 위해 생성된 단어 임베딩 가중치 행렬에서, 각 단어 간 유클리디안 거리를 계산해 본다. 결과는 다음과 같다. 각 가족 구성원 중 누가 더 가까워 보이는지 재밌게 결과를 해석해 보자! 나중에 `Word2Vec`에서 코사인 거리 등을 통해 각 단어 간 거리를 측정할 일이 있을 텐데, 그 때 더 자세히 보도록 하자.



```python
============ 단어 간 유클리드 거리 측정 ============
[[0.         1.2515203  1.1916165  0.93515205]
 [1.2515203  0.         1.5647719  1.627764  ]
 [1.1916165  1.5647719  0.         1.5134325 ]
 [0.93515205 1.627764   1.5134325  0.        ]]
```

<br>