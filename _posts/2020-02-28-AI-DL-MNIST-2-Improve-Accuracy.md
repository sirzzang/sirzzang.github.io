---
title:  "[DL] MNIST_3.Deep Learning 정확도 향상"
excerpt: "<<Neural Network>> 딥러닝에서 더 정확도를 높여 MNIST 문제를 풀어보자."
toc: true
toc_sticky: true
categories:
  - AI
header:
  teaser: /assets/images/blog-AI.jpg
tags:
  - Python
  - Deep Learning
  - Tensorflow
  - MNIST
use_math: true
last_modified_at: 2020-03-01
---



<sup>[문성훈 강사님](https://moon9342.github.io/)의 강의 내용을 기반으로 합니다.</sup>

<sup>Tensorflow 1.X ver</sup>

# _MNIST - DEEP LEARNING 정확도 높이기_



 딥러닝을 통해 MNIST 데이터셋 예측 문제를 풀어 보았다. 이제 활성화 함수 변경, 가중치 초기화 방식 변경, `Dropout` 적용 등을 통해 정확도를 높이자. 



## 0. 모듈 불러오기 및 데이터셋 준비

```python
import tensorflow as tf
from tensorflow.examples.tutorials.mnist import input_data
import warnings

# warning 출력 제한
warnings.filterwarnings(action='ignore')

# load data
mnist = input_data.read_data_sets('./data/mnist', one_hot=True)
```

* 데이터를 읽어 들이게 되면, data 폴더 안에 4개의 압축 파일이 생성된다.
* warning 설정을 통해 경고 문구가 표시되지 않도록 하자.





## 1. 활성화 함수: ReLU



 대부분의 딥러닝 기법에서는 활성화 함수로 `ReLU` 함수를 사용한다. 해당 함수는 Hinton 교수가 고안한 것이다. 

 기존 딥러닝 기법에서 sigmoid / softmax 함수를 활성화 함수를 사용하다 보니, 여러 layer가 중첩되면서 층이 깊어질수록 학습 및 예측이 어려워지는 현상이 나타났다. 이를  **Vanishing Gradient** 문제라고 한다.

 `ReLU` 함수는 입력값이 0보다 작을 때에는 활성화 함수에 0을 할당하고, 0보다 클 때에는 그 값을 그대로 반환한다.



### 코드 구현



  activation function과 logit 부분을 `tf.nn.softmax`에서 `tf.nn.relu`로 바꿔 주자.



```python
tf.reset_default_graph # 그래프 초기화

# placeholder
X = tf.placeholder(shape=[None, 784], dtype=tf.float32)
Y = tf.placeholder(shape=[None, 10], dtype=tf.float32)

# 3 layers
W1 = tf.Variable(tf.random_normal([784, 256], name='weight1'))
b1 = tf.Variable(tf.random_normal([256]), name='bias1')
layer1 = tf.nn.relu(tf.matmul(X, W1)+b1)

W2 = tf.Variable(tf.random_normal([256, 256]), name='weight2')
b2 = tf.Variable(tf.random_normal([256]), name='bias2')
layer2 = tf.nn.relu(tf.matmul(layer1, W2)+b2)

W3 = tf.Variable(tf.random_normal([256, 10]), name='weight3')
b3 = tf.Variable(tf.random_normal([10]), name='bias3')

# Hypothesis, logit
logit = tf.matmul(layer2, W3) + b3
H = tf.nn.relu(logit) # 로짓 활성화 함수도 relu!

# cost
cost = tf.reduce_mean(tf.nn.softmax_cross_entropy_with_logits_v2(logits=logit, labels=Y))

# train
train = tf.train.GradientDescentOptimizer(learning_rate=0.1).minimize(cost)

# session
sess = tf.Session()
sess.run(tf.global_variables_initializer()) # 변수 초기화

# 학습
num_of_epoch = 30
batch_size = 100
for step in range(num_of_epoch):
    num_of_iter = int(mnist.train.num_examples/batch_size)
    cost_val = 0
    for i in range(num_of_iter):
        batch_x, batch_y = mnist.train.next_batch(batch_size)
        _, cost_val = sess.run([train, cost], feed_dict={X: batch_x, Y: batch_y})
    if step % 3 == 0:
        print("cost: {}".format(cost_val))
print("학습 끝")

# 정확도 측정
pred = tf.argmax(H, 1)
label = tf.argmax(Y, 1)
correct = tf.equal(pred, label)
accuracy = tf.reduce_mean(tf.cost(correct, dtype=tf.float32))
result = sess.run(accuracy, feed_dict={X: mnist.test.images, Y: mnist.test.labels})
print("accuracy: {}".format(accuracy))
```





### 결과

 cost값이 `nan`이 나온다. 모델이 발산한다는 의미다.



## 2. 초기값 설정: Xavier



 위에서 활성화 함수로 `ReLU`를 사용했으나, 모델이 발산했다. 이는 초기 weight 값이 어떻게 주어지는지에 따라 모델의 결과가 다르게 나타날 수 있음을 의미한다.

 여태까지는 편의상 weight을 `random_normal`을 통해 설정했지만, 좋은 방법이 아니다. 

 초기값을 무작위로 할당하는 방식은 학습과 예측에 좋지 않다. 따라서 딥러닝 모델 학습 시 초기값을 설정하는 방법에 대해 많은 연구가 이루어지고 있다. `RBM`, `Xavier`, `He's` 등의 방식이 있다. 우리는 `Xavier` 방식을 이용한다.



### 코드 구현

* 가중치 설정: `tf.get_variable`
* 가중치 `initializer` 옵션 : `tf.contrib.layers.xavier_initializer()`



```python
tf.reset_default_graph()

# 모델 설정: ReLU + Xavier
X = tf.placeholder(shape=[None, 784], dtype=tf.float32)
Y = tf.placeholder(shape=[None, 10], dtype=tf.float32)

# 3 layers
W1 = tf.get_variable('weight1', shape=[784, 256], initializer=tf.contrib.layers.xavier_initializer())
b1 = tf.Variable(tf.random_normal([256]), name='bias1')
layer1 = tf.nn.relu(tf.matmul(X, W1)+b1)

W2 = tf.get_variable('weight2', shape=[256, 256], initializer=tf.contrib.layers.xavier_initializer())
b2 = tf.Variable(tf.random_normal([256]), name='bias2')
layer2 = tf.nn.relu(tf.matmul(layer1, W2)+b2)

W3 = tf.get_variable('weight3', shape=[256, 10], initializer=tf.contrib.layers.xavier_initializer())
b3 = tf.Variable(tf.random_normal([256]), name='bias3')

logit = tf.matmul(layer2, W3)+b3
H = tf.nn.relu(logit)

cost = tf.reduce_mean(tf.nn.softmax_cross_entropy_with_logits_v2(logits=logit, labels=Y))

train = tf.train.GradientDescentOptimizer(learning_rate=0.1).minimize(cost)

sess = tf.Session()
sess.run(tf.global_variables_inizializer())

...
```



### 결과

 아까와 달리 모델이 발산하지 않으며, 정확도가 높아진다.

```python
cost 값은 : 0.265817791223526
cost 값은 : 0.045113854110240936
cost 값은 : 0.025331275537610054
cost 값은 : 0.11332390457391739
cost 값은 : 0.023575926199555397
cost 값은 : 0.024161063134670258
cost 값은 : 0.00599552970379591
cost 값은 : 0.0028295035008341074
cost 값은 : 0.000999674666672945
cost 값은 : 0.003491774434223771
학습 끝
정확도는 98.01999926567078%입니다.
```





## 3. 옵티마이저: AdamOptimizer



 기존의 `GradientDescentOptimizer`보다 더 정확하다고 알려진 옵티마이저다. 그러나 항상 더 높은 정확도를 보장하지는 않는다.



### 코드 구현

 train 부분에서 optimizer를 `AdamOptimizer`로 변경한다.

```python
...
train = tf.train.AdamOptimizer(learning_rate = 0.01).minimize(cost)

sess = tf.Session()
sess.run(tf.global_variables_initializer())
...
```



### 결과

 항상 더 좋은 결과를 보장하지 않는다고 말씀하셨듯, 실제로 정확도는 더 낮아진다. `cost` 수렴 역시 느리다.

```python

cost 값은 : 0.1014658734202385
cost 값은 : 0.01694793999195099
cost 값은 : 0.16454263031482697
cost 값은 : 0.037584271281957626
cost 값은 : 0.08709853887557983
cost 값은 : 0.05138076841831207
cost 값은 : 0.0625457689166069
cost 값은 : 0.05042741447687149
cost 값은 : 0.043750762939453125
cost 값은 : 0.028329525142908096
학습 끝
정확도는 96.81000113487244%입니다.
```



## 4. DropOut



 모델의 과적합을 피하기 위해서 사용하는 방법 중 하나다. 모든 데이터를 전부 다 이용하지 말고, 일정 비율의 node 기능을 상실시킨다. 모든 node가 전부 다 학습 및 예측에 참여하기 때문에 과적합이 발생한다는 아이디어에서 출발한다.

 test 단계에서 정확도를 측정하고, 모델을 사용해 예측할 때에는 dropout rate를 설정하지 않음에 유의한다.



### 코드 구현

 `dropout rate`를 placeholder로 구현한다. 다만, tensorflow 버전에 따라서 무엇을 인자로 설정해야 하는지가 바뀐다.

* `1.5.0` : `keep_prob` (기능을 **남길** 노드)
* `1.15.0` : `rate` (기능을 **상실시킬** 노드)

 layer를 설정할 때, `tf.nn.dropout`을 통해 dropout layer를 설정한다.



```python
# ver 1.15.0
tf.reset_default_graph()

X = tf.placeholder(shape=[None, 784], dtype=tf.float32)
Y = tf.placeholder(shape=[None, 10], dtype=tf.float32)
dout_rate = tf.placeholder(dtype=tf.float32) # 기능 상실

W1 = tf.get_variable('weight1', shape=[784, 256], initializer=tf.contrib.layers.xavier_initializer())
b1 = tf.Variable(tf.random_normal([256]), name='bias1')
_layer1 = tf.nn.relu(tf.matmul(X, W1)+b1)
layer1 = tf.nn.dropout(_layer1, rate=dout_rate) # dropout

W2 = tf.get_variable('weight2', shape=[256, 256], initializer=tf.contrib.layers.xavier_initializer())
b2 = tf.Variable(tf.random_normal([256]), name='bias2')
_layer2 = tf.nn.relu(tf.matmul(layer1, W2)+b2)
layer2 = tf.nn.dropout(_layer2, rate=dout_rate)

W3 = tf.get_variable('weight3', shape=[256, 10], initializer=tf.contrib.layers.xavier_initializer())
b3 = tf.Variable(tf.random_normal([10]), name='bias3')

logit = tf.matmul(layer2, W3)+b3
H = tf.nn.relu(logit)

cost = tf.reduce_mean(tf.nn.softmax_cross_entropy_with_logits_v2(logits=logit, labels=Y))
train = tf.train.GradientDescentOptimizer(learning_rate=0.1).minimize(cost)

sess = tf.Session()
sess.run(tf.global_variables_initializer())

# 학습
num_of_epoch = 30
batch_size = 100
for step in range(num_of_epoch):
    num_of_iter = int(mnist.train.num_examples / batch_size)
    cost_val = 0
    for i in range(num_of_iter):
        batch_x, batch_y = mnist.train.next_batch(batch_size)
        _, cost_val = sess.run([train, cost], feed_dict={X:batch_x, Y: batch_y, dout_rate:0.3})
    if step % 3 == 0:
        print(f"cost 값은 : {cost_val}")
print("학습 끝")

# 정확도 측정: dropout 설정하면 안 됨.
pred = tf.argmax(H, 1)
label = tf.argmax(Y, 1)
correct = tf.equal(pred, label)
accuracy = tf.reduce_mean(tf.cast(correct, dtype=tf.float32))
result = sess.run(accuracy, feed_dict={X:mnist.test.images, Y:mnist.test.labels, dout_rate:0}) # 주의
print(f"정확도는 {result * 100}%입니다.")
```



### 결과



 지금까지 진행한 것 중 가장 높은 정확도가 나왔다. 그러나 항상 더 높은 정확도가 보장되지는 않는다.



```python
cost 값은 : 0.3003239333629608
cost 값은 : 0.18545137345790863
cost 값은 : 0.07099945098161697
cost 값은 : 0.17450176179409027
cost 값은 : 0.11239916831254959
cost 값은 : 0.10157787054777145
cost 값은 : 0.09994788467884064
cost 값은 : 0.19651824235916138
cost 값은 : 0.03572039678692818
cost 값은 : 0.04375575855374336
학습 끝
정확도는 98.18999767303467%입니다.
```





