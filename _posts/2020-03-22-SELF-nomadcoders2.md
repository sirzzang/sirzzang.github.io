---
title:  "[NomadCoders] Making WebScrapper with Python_2.1"
excerpt: "Django 기초 - 함수 인자 이해"
header:
  teaser: /assets/images/nomad_scrapper.png
categories:
  - SELF
tags:
  - 함수
  - arguments
  - 노마드코더
last_modified_at: 2020-03-21
---





# Python으로 웹 스크래퍼 만들기



## 2. Get Ready for Django

 파이썬의 Django 프레임워크를 이용하면 쉽게 웹 애플리케이션을 개발할 수 있다. Django는 웹 앱을 개발하기 위한 ~~*아주 멋진*~~ class들의 모임이다. 따라서 Django를 이용하여 웹 앱을 개발하기 위해서는 다음의 기본적인 개념들을 알아야 한다.



### 2.1. 함수 인자



**1) 인자 전달 방식**

 파이썬에서 함수를 정의할 때는 인자를 주어야 한다. 함수 인자를 보내는 방식에는 다음의 두 가지가 있다.

* positional argument : 위치 인자. 인자를 **위치**로 전달.
* keyword argument : 키워드 인자. 인자를 **키워드**로 전달.

  위치 인자를 전달할 때는, 함수를 정의할 때 나열되어 있는 매개변수 순서대로 값을 전달해야 하며, 매개변수를 key로 하여 값을 전달하면 된다.

```python
def plus(a, b):
    return a+b

# 위치 인자 전달
>>> print(plus(1, 1)) # 2
# 키워드 인자 전달
>>> print(plus(b=3, a=2)) # 5
```

 어떤 방식으로 인자를 보내도 상관 없지만, **위치 인자**는 항상 키워드 인자보다 **먼저** 작성해야 한다.



**2) 가변 길이의 인자를 받고 싶을 때**

 함수 정의 시 사용한 매개변수의 개수와 다른 인자를 전달하면, 아래와 같은 `TypeError`가 발생한다.

![positional argument error]({{site.url}}/assets/images/argserror.png){: width="60%" height="60%"}{: .center}

 또한, 정의되지 않은 키워드 인자를 전달할 때도, 아래와 같은 `TypeError`가 발생한다.

![keyword argument error]({{site.url}}/assets/images/kwargserror.png){: width="60%" height="60%"}{: .center}



 그러나 함수에서 들어오는 인자의 길이를 모른다거나, 입력되는 인자를 모두 받아서 처리하고 싶을 때가 있다. 이 때는 asterisk(`*`)를 사용하면 된다.

* *args : 가변 길이의 위치 인자를 tuple 형식으로 받는다.
* **kwargs : 가변 길이의 키워드 인자를 dict 형식으로 받는다.



 다음과 같이 사용하면 된다.

```python
def plus_(a, b, *args, **kwargs): # 위치 인자, 키워드 인자를 무제한으로 받을 수 있다.
    print(f"args: {args}")
    print(f"kwargs: {kwargs}")
    return a+b

>>> print(plus_(1, 2, 1, 3, 1, 4, hello=True, bye=False, fdf=1))
# args: (1, 3, 1, 4)
# kwargs: {'hello': True, 'bye': False, 'fdf': 1}
# 3
```



 무제한으로 위치 인자를 받아 합을 구하는 함수를 다음과 같이 작성할 수 있다.

```python
def plus__(*args):
    result = 0
    for number in args:
        result += number
    return result

>>> print(plus__(1, 2, 3, 5, 5, 1, 2, 3, 1, 5, 6, 7, 8, 2, 3, 5, 4)) # 63
```

