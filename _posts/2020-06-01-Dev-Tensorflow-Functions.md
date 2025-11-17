---
title:  "[Tensorflow] 기억해야 할 Tensorflow 사용법"
excerpt: 파이썬 Tensorflow 2.x 버전 사용법 이해하기
categories:
  - Dev
toc : true
tags:
  - Python
  - Tensorflow
last_modified_at: 2020-06-01
---





# _Tensorflow  2.x  매뉴얼_

<br>

 



## 1. tf.Data



 `lambda` 함수는 `익명 함수`로, 이름 없는 함수이다. 다음과 같이 사용한다.

```python
(lambda <인자> : <코드>) (전달 인자)
```



 `lambda` 함수는 일반적인 함수와 달리 `return`을 사용하지 않는다. 다만 반환값을 만드는 표현식만 있을 뿐이다. 

 예를 들어 어떤 수의 제곱을 계산하는 함수를 만든다고 하자.

```python
def f(x):
    return x**2

>>> f(3) # 9
```



 위의 함수를 람다 표현식을 사용해 표현하면 다음과 같다.

```python
>>> (lambda x: x**2)(3) # 9
```



 그러나 `lambda`는 파이썬의 예약어로서, 뒤에 나오는 표현식이 익명 함수임을 나타내는 것일 뿐이다. 아래의 코드를 실행해 보면, 스크립트 환경에 저장되어 있는 `lambda` 함수임을 알 수 있다. 마치 위에서 `f`만을 지칭하여 실행한 것과 같다.

```python
>>> lambda x: x**2  # <function __main__.<lambda>>
>>> f  # <function __main__.f>
```



 익명 함수에 이름을 붙여 준다면, 일반적인 함수처럼 사용할 수 있다. 다만 익명 함수에 이름을 붙인 것일 뿐이므로, 그 본질은 여전히 익명 함수이다.

```python
g = lambda x: x**2
>>> g(3)  # 9
>>> g  # <function __main__.<lambda>>
>>> print(g)  # <function <lambda> at 0x7f47bfb49d08>
```



 여러 개의 인자를 전달할 수도 있다. 인자를 아예 전달하지 않아도 된다. 

```python
lambda : "Hello"
lambda x : x**2
lambda x, y : x**2 + y**2
lambda x, y, z : x**2 + y**2 + z**2

(중략)

lambda x1, x2, x3, ..., xn : <some expression>
```



 주의할 것은 `lambda` 표현식에서는 변수를 사용할 수 없다는 점이다. 익명 함수를 사용하여 함수를 표현하고 싶을 경우, 변수 없이 한 줄로 식을 표현할 수 있어야 한다.

 다음과 같이 변수를 만들고자 할 경우, 에러가 난다.

```python
>>> (lambda x: y= 10; x**2 + y**2)(3)
# SyntaxError: invalid syntax
```



 다만, 밖에 있는 변수는 사용할 수 있다.

```python
y=10
(lambda x: x**2 + y**2)(3)
```



 다음의 예와 같이 두 개의 인자를 입력 받아 Full Name을 반환하는 함수를 만들 수 있다.

```python
full_name = lambda first, last: first.strip() + " " + last.strip()
>>> full_name("S", "Eraser")  # 'S Eraser'
```



## 2. 활용 예



### 2.1. 정렬

 파이썬의 정렬 기능은 사용할 때, `key` argument로서 정렬할 때 사용할 함수를 입력 받는다. 이 때 `lambda` 표현식을 사용해 정렬할 기준을 지정할 수 있다.

```python
members = [sys.stdin.readline().split() for _ in range(N)]
members = sorted(members, key=lambda x : int(x[0]))
```





### 2.2. lambda  함수를 반환 값으로 전달

 다음과 같이 익명 함수를 반환 값으로 활용할 수 있다. *~~그러나 보기에 편하지는 않다.~~*



```python
def build_quadratic_function(a, b, c):
    return lambda x: a*x**2 + b*x + c

>>> f = build_quadratic_function(2, 3, -5) 
>>> f(0)  # -5
>>> f(1)  # 0
>>> f(2)  # 9

>>> build_quadratic_function(3, 0, 1)(2) # 13
```



### 2.3. Pandas 데이터프레임

 Pandas 라이브러리에서도 `apply` 함수와 함께 자주 사용된다.

```python
>>> df[df['CC Exp Date'].apply(lambda x: x[-2:] =='25')].count() # 신용카드 만료일이 2025년 이후인 고객 수 확인
```



```python
def cancel_fn(x):
    if x > 0:
        return "단골"
    elif x == 0:
        return "평범"
    else:
        return "취소"
df['CANCEL'] = df['CANCEL'].apply(lambda x: cancel_fn(x))
```





### 2.4. Tensorflow

 Tensorflow 2.x 버전에서 옵티마이저에 loss function을 넘겨 줄 때 사용한다.

```python
# loss function 정의
def loss_CE(X, y, c):
    y_pred = predict(X)
    y_clip = tf.clip_by_value(y_pred, 0.000001, 0.999999)
    cost = -tf.reduce_mean(y * tf.math.log(y_clip) + (1-y) * tf.math.log(1-y_clip)) +\
                           c * tf.reduce_mean(tf.square(Wh)) +\
                           c * tf.reduce_mean(tf.square(Bh)) +\
                           c * tf.reduce_mean(tf.square(Wo)) +\
                           c * tf.reduce_mean(tf.square(Bo))
    return cost

# 옵티마이저 설정
adam = Adam(learning_rate=0.01)

# 학습
for epoch in range(epochs):

    # mini-batch
    for batch_X, batch_y in train_batch:
        adam.minimize(lambda: loss_CE(batch_X, batch_y, c), var_list=[Wh, Bh, Wo, Bo]) # loss function 전달
        
    ...
```





 