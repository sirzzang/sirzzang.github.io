---
title:  "[ML] MNIST_1.Tensorflow 구현"
excerpt: "<<Classification>> Multinomial Classification을 Tensorflow로 구현해 보자."
toc: true
toc_sticky: true
categories:
  - AI
header:
  teaser: /assets/images/blog-AI.jpg
tags:
  - Python
  - Machine Learning
  - Tensorflow
  - MNIST
use_math: true
last_modified_at: 2020-03-01
---



<sup>[문성훈 강사님](https://moon9342.github.io/)의 강의 내용을 기반으로 합니다.</sup>

<sup>Tensorflow 1.X ver</sup>

# _MNIST - Tensorflow로 Machine Learning 구현_



 Tensorflow를 활용하여 MNIST multinomial classification 문제를 풀어 보자. Tensorflow의 사용법에 주의하며 흐름을 따라가 보자!



## 1. 기본 모델 만들기



 먼저 Kaggle 데이터셋 말고 Tensorflow 내장 데이터셋을 활용한다. `one hot encoding`이 쉽다.



```python
# module import
import tensorflow as tf
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from tensorflow.examples.tutorials.mnist import input_data

# load data
mnist = input_data.read_data_sets('./data/mnist', one_hot=True)
```

 `input_data`에서 `read_data_sets` 함수를 활용해 Tensorflow 내장 MNIST 데이터 셋을 불러온다. 경로에 지정한 폴더 아래 4개의 압축파일이 생성되며, `one_hot = True` 옵션을 주면 알아서 원핫 인코딩이 되어 나온다.



```python
# data to csv
X_train_df = pd.DataFrame(mnist.train.images)
X_train_df.to_csv('./mnist_x_data.csv', index=False)
y_train_df = pd.DataFrame(mnist.train.labels)
y_train_df.to_csv('./mnist_y_data.csv', index=False)
```

 위에서 받아 온 MNIST 데이터셋을 csv 파일로 만들어 보자. 데이터의 각 feature는 픽셀의 값을 나타낸다. 각 픽셀의 값은 0과 1 사이의 숫자로 되어 있다. scaling이 이미 되어 있다.

 다시 말하지만, 이미지는 RGB `+ a`로 표현되는 3차원이다. 각 픽셀 값은 0에 가까울 수록 흰색을 지칭하고, 1과 가까울수록 진해지므로 검은색을 지칭한다.





### 1.1. Placeholder

```python
X = tf.placeholder(shape=[None, 784], dtype=tf.float32)
Y = tf.placeholder(shape=[None, 10], dtype=tf.float32)
```

 Tensorflow에서는 입력 데이터를 받을 때 `tf.placeholder`를 사용한다. data shape에 맞게 `placeholder`를 설정해 주는 것이 중요하다. 몇 개의 데이터가 있는지 모르기 때문에, 행의 개수는 `None`으로 설정한다. *~~(약간 `NumPy` -1 개념인가)~~*



### 1.2. Weight, bias 설정

```python
W = tf.Variable(tf.random_normal([784, 10]), name='weight')
b = tf.Variable(tf.random_normal([10]), name='bias')
```

 Tensorflow에서 변수는 `tf.Variable`로 설정한다. 임의의 weight 행렬 및 가중치 값을 설정해 주기 위해 `tf.random_normal`을 사용한다.

 역시 data shape에 주의하자. 784차원의 데이터고, 라벨이 10개이므로 가중치 행렬은 784행 10열이 되어야 한다.



### 1.3.  Hypothesis, logit 설정

```python
logit = tf.matmul(X, W) + b
H = tf.nn.softmax(logit)
```

 multinomial classification에서의 logit 값을 정의한다. 행렬곱을 해주면 된다. Tensorflow에서는 `tf.matmul`로 구현한다.

 로짓 값에 소프트맥스 함수를 취해서 각 라벨에 속할 확률을 구한다. `tf.nn.softmax`로 구현한다.



### 1.4. Cost 설정

```python
cost = tf.reduce_mean(tf.nn.softmax_cross_entropy_with_logits_v2(logits=logit, labels=Y))
```

  multinomial classification 문제이다. 따라서 loss function으로 `tf.nn.softmax_cross_entropy_with_logits_v2`를 사용한다. 그리고 이 손실 함수의 제곱합을 최소화하기 위해 loss function에 `tf.reduce_mean`을 적용한 뒤, 이를 cost function으로 설정한다.



### 1.5. Train

```python
train = tf.train.GradientDescentOptimizer(learning_rate=0.5).minimize(cost)
```

 경사하강법을 사용해 학습한다. `tf.train.GradientDescentOptimizer`를 사용하면 된다. 해당 optimizer가 cost를 최소화하는 방향으로 학습하게 하면 되므로, `.minimize(cost)`를 붙여(? *~~적당한 말이 생각이 안 난다~~*) 준다. 학습률은 임의로 설정한다.



### 1.6. session 설정

```python
sess = tf.Session()
sess.run(tf.global_variables_initializer())
```

 Tensorflow에서는 `Session` 객체를 통해 그래프의 연산을 실행한다. 따라서 `Session` 객체를 생성해 준다. `tf.Session()`을 만들어 주면 된다.

 그래프 연산을 수행하기 전, 항상 변수를 초기화해야 한다. `tf.global_variables_initializer()`로 가능하다. 이 역시 `Session` 객체를 통해 수행되어야 한다.



### 1.7. 학습

```python
train_epoch = 30
for step in range(train_epoch):
    _, cost_val = sess.run([train, cost], feed_dict = {X:mnist.train.images, Y:mnist.train.labels})
    
    if step % 3 == 0:
        print("Cost 값은: {}".format(cost_val))
```



 위에서 설정한 `train`, `cost` 연산을 실행해야 한다. 순서를 따라가 보자. 

* `cost`는 `logit`, `Y`와 연결되어 있다. 
* `logit`은 `X`,  `W`와 연결되어 있다. `X`는 placeholder로서 입력 값을 받아야 한다.
* `Y` 역시 placeholder로서 입력 값을 받아야 한다.

 따라서 학습 과정에서는 placeholder로 설정해 준 빈 껍데기에 데이터를 밀어 넣어줘야 한다. `Session` 객체에 `feed_dict` 옵션을 통해 입력 이미지와 라벨을 넘겨 주자.

 cost 연산은 실행하면 cost 값이 나오지만, train 연산은 실행 후 의미 있게 받아야 할 값이 없다. 관행적으로 `_`를 사용해서 변수를 설정해 준다.

 train data를 한 번 학습하는 것이 1 epoch이므로, 여기서는 30번 학습하게 된다. 중간 중간 학습이 잘 진행되고 있는지 cost 값을 확인하기 위해, cost 값을 출력한다.

 출력한 cost값을 통해 학습 결과를 확인하면 다음과 같다.

```python
Cost 값은 : 19.766536712646484
Cost 값은 : 11.08687973022461
Cost 값은 : 8.81389331817627
Cost 값은 : 7.11265754699707
Cost 값은 : 5.837159633636475
Cost 값은 : 4.900848865509033
Cost 값은 : 4.216954708099365
Cost 값은 : 3.7111566066741943
Cost 값은 : 3.3278369903564453
Cost 값은 : 3.028888463973999
```

 cost 값이 잘 감소하는 것을 확인할 수 있다. 다만 학습 에폭 수가 늘어날 수록 cost 값의 수렴 정도는 더 작아진다.



### 1.8. 정확도 측정

```python
pred = tf.argmax(H, 1)
label = tf.argmax(Y, 1)
correct = tf.equal(pred, label)
accuracy = tf.reduce_mean(tf.cast(correct, dtype=tf.float32))
print("정확도는 : {}".format(sess.run(accuracy, feed_dict = {X : mnist.test.images, Y : mnist.test.labels})))
```

 가설 H로부터 도출된 값과 라벨 값을 `axis=1` 방향으로 `argmax`한다. NumPy의 `argmax`와 사용법이 동일하다. `argmax`한 결과, 예측 라벨과 실제 라벨이 나오게 된다. 

 `tf.equal`을 통해 예측 라벨과 실제 라벨이 같은지 확인하는 `correct` 연산을 만든다. `correct` 연산에 의해 두 라벨이 같으면 `True`, 같지 않으면 `False`의 boolean 값이 나오게 된다. 

 이제 `tf.cast` 함수를 사용하자. `tf.cast` 함수는 tensor를 새로운 형태로 바꾸는 데에 사용된다. 조건에 따라 1 또는 0 등을 반환하는데, 디폴트 상태인 경우 `True`면 1을, `False`면 0을 반환한다. `tf.reduce_mean` 함수를 이용해 나온 cast되어 나온 1, 0 값의 평균을 내자. 그러면 그게 바로 정확도가 된다.

 이렇게 만든 `accuracy` 연산을 정확도를 주는 데 사용하면 된다. 연산을 따라 올라가 보자.

* `pred`를 구하기 위해서는 궁극적으로 `X`에 입력 데이터가 필요하다.
* `label`을 구하기 위해서는 `Y`에 입력 데이터가 필요하다.



 정확도를 측정하는 게 목적이므로, 기존에 학습을 통해 생성한 가설 `H`에 테스트 이미지만 넣어 주면 된다. `feed_dict`에 `X`로`mnist.test.images`를, `Y`로 `mnist.test.labels`를 넣자.

 정확도를 확인하면 다음과 같다.

```python
정확도는 : 0.5236999988555908
```



*~~별로 안 좋다. 뭐지?~~*





## 2. batch를 통해 모델 다시 만들기



 MNIST 데이터셋 자체가 굉장히 크다. 너무 많은 데이터를 한 번에 불러들이고 입력하면 데이터를 잘못 계산해 학습의 결과가 좋지 않을 수 있다. 따라서 반복과 배치를 통해 데이터를 나누어 학습시켜 보자. 

 batch size를 설정하기 이전 부분까지는 동일하다.



### 2.1. 동일한 부분

```python
# placeholder
X = tf.placeholder(shape=[None, 784], dtype=tf.float32)
Y = tf.placeholder(shape=[None, 10], dtype=tf.float32)

# weight, bias
W = tf.Variable(tf.random_normal([784, 10]), name='weight')
b = tf.Variable(tf.random_normal([10]), name='bias')

# hypothesis
logit = tf.matmul(X, W) + b
H = tf.nn.softmax(logit)

# cost
cost = tf.reduce_mean(tf.nn.softmax_cross_entropy_with_logits_v2(logits=logit, labels=Y))

# train
train = tf.train.GradientDescentOptimizer(learning_rate=0.5).minimize(cost)

# session
sess = tf.Session()
sess.run(tf.global_variables_initializer())
```





### 2.2. batch size 설정



 55000개의 data를 100개씩 잘라서 학습시켜 보자. 큰 사이즈의 데이터를 배치로 나누어, 해당하는 배치만큼 학습을 진행하자.

 한 학습 에폭 안에서도 배치만큼 반복 횟수가 나누어지게 된다. *요컨대,* 1회기의 학습을 55000/100번으로 나누어 진행하는 셈이다.

```python
# 학습 횟수
train_epoch = 30

# 배치 사이즈
batch_size = 100

for step in range(train_epoch):
    num_of_iter = int(mnist.train.num_examples / batch_size)
    cost_val = 0
    
    # 배치에 대한 학습 진행
    for i in range(num_of_iter):
        batch_x, batch_y = mnist.train.next_batch(batch_size)
        _, cost_val = sess.run([train, cost], feed_dict = {X: batch_x, Y: batch_y})
        
    if step % 3 == 0:
        print("Cost 값은 : {}". format(cost_val))
    
# 정확도 측정
pred = tf.argmax(H, 1)
label = tf.argmax(Y, 1)
correct = tf.equal(pred, label)
accuracy = tf.reduce_mean(tf.cast(correct, dtype=tf.float32))
print("정확도는 : {}".format(sess.run(accuracy, feed_dict = {X : mnist.test.images, Y : mnist.test.labels})))
```



 위에서 말한, 1회기의 학습 내의 반복 횟수가 `num_of_iter`가 된다.  또한 배치 사이즈에 해당하는 크기의 데이터만큼 불러올 수 있도록,   Tensorflow는 `next_batch` 함수를 제공한다. *~~(아주 편리하다)~~* 

 한 학습 에폭 안에서 batch 사이즈만큼 데이터를 가져오고, `feed_dict`에 배치 사이즈만큼의 데이터를 넣어 주면 된다.



 결과를 확인하면 다음과 같다.

```python
Cost 값은 : 0.8596975207328796
Cost 값은 : 0.6384946703910828
Cost 값은 : 0.38845375180244446
Cost 값은 : 0.31539544463157654
Cost 값은 : 0.5171910524368286
Cost 값은 : 0.46512994170188904
Cost 값은 : 0.27266165614128113
Cost 값은 : 0.3753893971443176
Cost 값은 : 0.28353968262672424
Cost 값은 : 0.1510837972164154
정확도는 : 0.9192000031471252
```



 정확도가 올라간다! 아무래도 이전에 정확도가 낮았던 것은 너무 많은 데이터를 한 번에 학습시켰기 때문인 것 같다.



### 2.3. 임의의 데이터 예측하기

```python
import random

r = np.random.randint(0, mnist.test.num_examples)

print("Label : {}".format(sess.run(tf.argmax(mnist.test.labels[r:r+1], axis=1))))
print("predict : {}".format(sess.run(tf.argmax(H,1), feed_dict = { X : mnist.test.images[r:r+1] })))
```



 데이터를 2차원으로 만들어주기 위해 `test.labels[r]`이 아니라 `test.labels[r : r+1]`을 사용한다. 





## 3. Kaggle Dataset 사용



 Kaggle에서 제공하는 MNIST 데이터셋은 `one_hot encoding`과 `scaling`이 되어 있지 않다. 다른 부분은 동일하기 때문에 데이터셋을 로드하고 MNIST 데이터셋과 같은 형태로 맞춰주는 부분만 기록한다.

```python
import pandas as pd
from sklearn.preprocessing import MinMaxScaler
import tensorflow as tf

# load data
mnist_df = pd.read_csv("C:/python_DA/Ex/DA/train.csv")

# prepare data
X_df = pd.DataFrame(mnist_df.drop(columns=['label']))
X_df.to_csv("./X_df.csv", index=False)
y_df = pd.DataFrame(mnist_df['label'].values)
y_df.to_csv("./y_df.csv", index=False)

# 결측치 확인
X_df.isnull().sum(axis=1).sum(axis=0)
y_df.isnull().sum(axis=1).sum(axis=0)

# split train, test
split_num = int(X_df.shape[0] * 0.8) # 42000 = 33600 + 8400.

# scaling
scaler = MinMaxScaler()
X_data = scaler.fit_transform(X_df)
train_x_data, test_x_data = X_data[:split_num], X_data[split_num:]

# one-hot encoding
sess = tf.Session()
train_y_data = sess.run(tf.one_hot(y_df.loc[:split_num-1, 0], 10)) # 주의!
test_y_data = sess.run(tf.one.hot(y_df.loc[split_num:, 0], 10)) # 주의!
```



* `.loc[]`로 indexing할 때랑, 그냥 indexing할 때랑 숫자가 다르다! *(~~충격~~)*
* Tensorflow에서 `tf.one_hot` 함수 쓰면 onehot encoding 쉽게 할 수 있다.