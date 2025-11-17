---
title:  "[Pyhton] 손실함수, 규제함수 만들기"
excerpt: "Keras 기능을 이용해 Loss Function, Regularizer Function 커스텀하기"
toc: true
toc_sticky: true
categories:
  - AI
tags:
  - ML
  - DL
  - Tensorflow
  - Keras
use_math: true
last_modified_at: 2020-06-27
---



<sup>출처가 명시되지 않은 모든 자료(이미지 등)는 [조성현 강사님](https://blog.naver.com/chunjein)의 강의 및 강의 자료를 기반으로 합니다.</sup> <sup>[Github Repo](https://github.com/sirzzang/LECTURE/tree/master/인공지능-자연어처리(NLP)-기반-기업-데이터-분석/조성현 강사님/DL/DL 실습/20200629)</sup>

<sup>Tensorflow : 2.2.0</sup>

# _Keras로 Custom Loss/Regularizer 만들기_



 Keras는 `loss function`, `regularization function`을 커스터마이징할 수 있는 기능을 제공한다.



 다음의 [documentation](https://www.tensorflow.org/guide/keras/train_and_evaluate#custom_losses)을 보자.

> There are two ways to provide custom losses with Keras. The first example creates a function that accepts inputs `y_true` and `y_pred`. The following example shows a loss function that computes the mean squared error between the real data and the predictions.



 `loss` 함수를 커스텀하는 방법은 간단하다. `y_true`, `y_pred` 값을 인자로 받는 함수를 만든다. 컴파일된 모델에 대해 훈련(`.fit`)하면, 모델이 자동으로 예측값을 계산하고, 내부적으로 커스텀 함수의 `y_pred`로 계산된 값을 넘긴다.



 커스텀 `loss`, `regularizer` 함수를 만들어 XOR 문제를 풀어 보자.



## 1. Custom Loss



### Basic



 모듈을 불러오고, 그래프를 생성하는 부분까지는 모두 동일하다. 

 함수를 커스텀하기 위해 `tensorflow.keras.backend` 기능을 사용한다. 일반적인 Tensorflow의 함수를 사용해도 문제는 없다. 다만 `backend` 기능을 사용할 때에는 Tensorflow의 함수와 이름이 조금씩 달라진다.



```python
# module import
from tensorflow.keras.layers import Input, Dense, Dropout
from tensorflow.keras.models import Model
from tensorflow.keras.optimizers import Adam
import tensorflow.keras.backend as K
import numpy as np

# data
X = np.array([[0, 0], [0, 1], [1, 0], [1, 1]], dtype=np.float32)
y = np.array([[0], [1], [1], [0]], dtype=np.float32)

# custom Loss Function - 1
def myLoss(y_true, y_pred):
    loss = -K.mean(
        y_true * K.log(y_pred + 1e-6) +
        (1-y_true) * K.log(1 - y_pred + 1e-6)
        )
    return loss

# layers
X_input = Input(batch_shape=(None, 2))
X_hidden = Dense(4, activation='sigmoid')(X_input) 
X_hidden = Dropout(rate=0.1)(X_hidden)
y_output = Dense(1, activation='sigmoid')(X_hidden)

# model
model = Model(X_input, y_output)
model.compile(loss=myLoss, optimizer=Adam(lr=0.05))
print(model.summary())

# train
model.fit(X, y, epochs=500, batch_size=4)

# predict
y_hat = model.predict(X)
y_hat_pred = np.where(y_hat > 0.5, 1, 0)
print(y_hat)
print(y_hat_pred)
```





 `tensorflow.keras.backend`를 사용하려면, `reduce_mean` 대신 `mean`을, `math.log` 대신 `log`를 사용해야 한다. 그렇지 않으면 다음의 오류가 난다.

![backend error]({{site.url}}/assets/images/backend-error.png)



  기존에는 `log(0)`을 방지하기 위해 `tf.clip_by_value` 함수를 이용했다. 이 기능을 구현하기 위해 아주 작은 수(`1e-6`)을 `y_pred` 값에 더해 준다. *아주 작은 값* 이기 때문에, 더해 주어도 별 영향이 없다. 

 

 custom loss function만 정의하고, 아무 데서도 `y_pred` 값을 정의하지 않았다는 점에 유의하자. `.fit`이 호출되어 모델에서 훈련이 이루어지는 순간 Keras가 내부적으로 예측 값을 custom function으로 넘긴다.





### Inner Function: additional arguments



 여러 개의 loss function을 조합해 사용하고 싶을 수도 있다. 이 때 custom loss function의 인자로서 조합 비율을 넘겨 준다고 생각해 보자.



 *아주 `naive`하게*  다음과 같이 함수를 설계하면 된다고 생각할 수 있다.

```python
# Invlaid Loss Function
def myLoss(y_true, y_pred, r):    
    BCE = -K.mean(
        y_true * K.log(y_pred + 1e-6) +
        (1-y_true) * K.log(1 - y_pred + 1e-6)
        )
    MSE = K.mean(K.square(y_true - y_pred))

    loss = r * BCE + (1-r) * MSE
    return loss
```



 정의한 후, 다음과 같이 모델을 컴파일하고 훈련시켜 보자.

```python
# layers
X_input = Input(batch_shape=(None, 2))
X_hidden = Dense(4, activation='sigmoid')(X_input)
X_hidden = Dropout(rate=0.1)(X_hidden)
y_output = Dense(1, activation='sigmoid')(X_hidden)

# model
model = Model(X_input, y_output)
model.compile(loss=myLoss(0.8), optimizer=Adam(lr=0.05))
```



  에러가 난다. 

![backend error 2]({{site.url}}/assets/images/backend-error2.png)



  Keras의 custom loss function은 기본적으로 2개의 인자(`y_true`, `y_pred`)만을 받는다. 이것까지 건드릴 수 없다. 따라서 다음과 같이 `Inner Function`을 사용해야 한다.(*참고 : [Passing additional arguments to objective function](https://github.com/keras-team/keras/issues/2121)*)



```python
# custom Loss Function - 2: Inner Function
def myLoss(r):
    def loss(y_true, y_pred):    
        BCE = -K.mean(
            y_true * K.log(y_pred + 1e-6) +
            (1-y_true) * K.log(1 - y_pred + 1e-6)
            )
        MSE = K.mean(K.square(y_true - y_pred))
        return r * BCE + (1-r) * MSE
    return loss # loss 함수를 return 한다.

# layers
X_input = Input(batch_shape=(None, 2))
X_hidden = Dense(4, activation='sigmoid')(X_input)
X_hidden = Dropout(rate=0.1)(X_hidden)
y_output = Dense(1, activation='sigmoid')(X_hidden)

# model
model = Model(X_input, y_output)
model.compile(loss=myLoss(0.8), optimizer=Adam(lr=0.05))
print(model.summary())
```





## 2. Custom Regularizer



### Basic



 `Regularizer`를 커스텀하는 방법도 동일하다. 아래와 같이 Inner Function을 사용해 `L2` 규제 함수와 `BCE`, `MSE`를 결합한 `Loss Function`을 동시에 사용해 보자.



```python
# module import
from tensorflow.keras.layers import Input, Dense, Dropout
import tensorflow.keras.backend as K
from tensorflow.keras.models import Model
from tensorflow.keras import optimizers
from tensorflow.keras import regularizers
import numpy as np

# data
X = np.array([[0, 0], [0, 1], [1, 0], [1, 1]], dtype=np.float32)
y = np.array([[0], [1], [1], [0]], dtype=np.float32)

# custom loss function: inner function
def myLoss(r):
    def loss(y_true, y_pred):    
        BCE = -K.mean(
            y_true * K.log(y_pred + 1e-6) +
            (1-y_true) * K.log(1 - y_pred + 1e-6)
            )
        MSE = K.mean(K.square(y_true - y_pred))
        return r * BCE + (1-r) * MSE
    return loss # 함수를 return 한다.

# custom regularizer function
def myRegularizer(r):
    def regularizer(weights):
        reg_term = K.sum(r * K.square(weights))
        return reg_term
    return regularizer

# layers
X_input = Input(batch_shape=(None, 2))
X_hidden = Dense(4, activation='sigmoid', kernel_regularizer=myRegularizer(0.0001))(X_input)
X_hidden = Dropout(rate=0.1)(X_hidden) # fit에만 적용, predict에서는 알아서 적용 안 됨.
y_output = Dense(1, activation='sigmoid')(X_hidden)

# model
model = Model(X_input, y_output)
model.compile(loss=myLoss(0.8), optimizer=Adam(lr=0.05))
print(model.summary())

# train
model.fit(X, y, epochs=500, batch_size=4)

# predict
y_hat = model.predict(X)
y_hat_pred = np.where(y_hat > 0.5, 1, 0)
print(y_hat)
print(y_hat_pred)
```



> *참고*
>
>  위와 같이 커스텀한 뒤, `epoch`을 100으로 주고 `r=0.0002`를 줬는데, XOR 문제를 푸는 데에 성공하지 못했다! `[[1], [1], [1], [1]]`로 예측했다.







### To be Continued...



 가중치와 규제항 파라미터 `Lambda`를 변수를 통해 전달할 수도 있다. 지금은 어려우니까, 나중에 보도록 하자.