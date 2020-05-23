---
title:  "[NomadCoders] Making WebScrapper with Python_2.2_1"
excerpt: "Django 기초 - OOP"
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



### 2.2. OOP_1

> [*객체지향 참고1*]([http://www.incodom.kr/%ED%8C%8C%EC%9D%B4%EC%8D%AC/%EA%B0%9D%EC%B2%B4%EC%A7%80%ED%96%A5%ED%8A%B9%EC%A7%95]) 
>
> [*객체지향 참고2*]([http://schoolofweb.net/blog/posts/%ED%8C%8C%EC%9D%B4%EC%8D%AC-oop-part-1-%EA%B0%9D%EC%B2%B4-%EC%A7%80%ED%96%A5-%ED%94%84%EB%A1%9C%EA%B7%B8%EB%9E%98%EB%B0%8Doop%EC%9D%80-%EB%AC%B4%EC%97%87%EC%9D%B8%EA%B0%80-%EC%99%9C-%EC%82%AC%EC%9A%A9%ED%95%98%EB%8A%94%EA%B0%80/])



**1) Intro**

 파이썬에서 객체지향 프로그래밍을 하기 위해서는, **class**와 **instance**에 대해 이해해야 한다.

* class : 만들 제품의 설계도. 제품이 어떤 특징을 갖는지, 어떻게 작동하는지 안내하는 *blueprint*.
* instance(s) : 설계도(class)를 기반으로 만든 제품(들). 설계도에 안내되어 있는 속성과 작동 방식을 가짐.

 즉, class를 설계하면, 그 class를 기반으로 무한히 많은 instance들을 만들 수 있다. class에서 instance를 생성하는 것을 **instantiation**이라고 한다.



 예컨대, 다음과 같이 자동차 class를 생성할 수 있다.(class 명명 시 규칙은 [파이썬 코딩 스타일](http://pythonstudy.xyz/python/article/511-%ED%8C%8C%EC%9D%B4%EC%8D%AC-%EC%BD%94%EB%94%A9-%EC%8A%A4%ED%83%80%EC%9D%BC)을 따른다.)

```python
# Car 클래스 설계
class Car():
    pass

>>> print(Car) # __main__.Car
```

 Car class를 출력해 보면, 해당 스크립트 환경에서 Car이라는 객체로 존재하고 있음을 알 수 있다.



 이제 자동차 class로부터 자동차 instance를 생성할 수 있다. class 뒤에 괄호(`()`)를 붙여 instance를 호출하면 된다. 

```python
# 포르쉐 instance 생성
>>> porche = Car()
>>> print(porche) # <__main__.Car at 0x24eb4b5e3c8>
```

 실제 메모리 주소를 할당 받아 instance가 생성되었음을 확인할 수 있다.



**2) 속성**

 위에서 class라는 설계도는 만들어질 instance의 특징, 작동 방식 등을 정의할 수 있다고 했다. 앞에서 설계한 자동차 class는 아무런 특징도, 작동 방식도 나타내지 않는 빈 깡통 같은 설계도이다.

 이제 설계도로부터 만들어질 각각의 자동차 instance들이 4개의 바퀴, 4개의 문, 4개의 창문, 4개의 의자 등의 특징을 갖도록 설계해 보자. 이러한 특징을 **'속성'**이라 하며, 다음과 같이 class 내에 바로 설계하면 된다.

```python
# Car 클래스 설계 : 속성 추가
class Car():
    wheels = 4
    doors = 4
    windows = 4
    seats = 4
```



 위의 설계도에 따라 만들어진 자동차 instance가 갖는 속성을 확인하려면, `.`을 통해 속성에 접근하면 된다. 

```python
# porche 인스턴스 생성
>>> porche = Car()

# 속성 접근
>>> print(porche.wheels) # 4 
```



class 내에 정의되지 않은 속성도 할당할 수 있다.

```python
>>> porche.color = "RED"
>>> print(porche.color) # RED
```



**3) 메서드**

 메서드는 class로부터 만들어지는 instance들이 수행할 수 있는 **기능**이라고 이해하면 된다. 앞에서 언급한, 설계도가 안내하는 제품의 작동 방식이다.

 class 안의 function(`def`)으로 정의된다. 파이썬에서는 class 안의 메서드를 호출할 때, 메서드를 호출하는 instance 자기 자신을 첫 번째 인자로 사용한다. 따라서 메서드의 첫 번째 인자는 **자기 자신**이 되어야 한다. 여러 단어를 사용할 수 있으나, 관용적으로 *self* 를 사용한다. (potato 등 다른 인자를 사용해도 작동한다.)

 메서드 호출 시 속성과 동일하게 `.`을 이용한다. 다만, 함수이므로 **괄호 안에 인자를 넘겨야** 한다. self 외에 다른 인자가 없을 경우, `.()`를 사용하여 호출하면 된다.

 자동차 class에 시동을 거는 start 메서드를 다음과 같이 작성해 보자. 메서드를 호출할 때 어떤 instance가 호출하는지 알기 위해, `self` 를 출력하도록 했다.

```python
# Car 클래스 설계 : 메서드 추가
class Car():
    wheels = 4
    doors = 4
    windows = 4
    seats = 4
    
    def start(self):
        print(f"메서드를 호출한 것은: {self}")
        print("Car started!")
```



 자동차 instance를 생성하고 시동을 거는 기능을 사용해 보자. 

```python
# porche 인스턴스 생성
>>> porche = Car()
>>> porche.start() # start 메서드 호출
# 메서드를 호출한 것은: <__main__.Car object at 0x0000024EB4B5E080>
# Car started!
```

 "Car started!"가 잘 출력되는 것으로 보아, 메서드가 제대로 호출되었음을 알 수 있다. 또한, 메서드를 호출한 instance도 확인할 수 있다. 



*참고*

- 메서드에 자기 자신을 호출하는 인자가 없을 경우, 다음과 같이 `TypeError`가 발생한다.

![self error]({{site.url}}/assets/images/selferror.png){: width="60%" height="60%"}{: .aligncenter}

* 인자로 *potato* 를 주더라도 메서드는 작동한다(..!)

![potato]({{site.url}}/assets/images/potato.png){: width="60%" height="60%"}{: .aligncenter}



**4) class 살펴보기**

 class 역시 하나의 객체이다. 따라서 내장 함수 `dir()`을 활용해 해당 객체가 어떤 변수와 메서드를 갖는지 리스트로 확인할 수 있다.

```python
>>> print(dir(Car))
# ['__class__', '__delattr__', '__dict__', '__dir__', '__doc__', '__eq__', '__format__', '__ge__', '__getattribute__', '__gt__', '__hash__', '__init__', '__init_subclass__', '__le__', '__lt__', '__module__', '__ne__', '__new__', '__reduce__', '__reduce_ex__', '__repr__', '__setattr__', '__sizeof__', '__str__', '__subclasshook__', '__weakref__', 'doors', 'seats', 'start', 'wheels', 'windows']
```



 double underscore(`__`)를 달고 있는 변수 및 메서드들은 공개되지 않은 것들이다. 해당 강의의 범위를 벗어나므로 그 자체에 대한 설명은 생략한다.

 위의 메서드들 중 예시로 `__str__` 메서드를 알아 보자. 이 메서드는 instance가 `str(instance)` 혹은 `print(instance)`의 형태로 호출될 때 자동적으로 호출된다. 호출되면, instance를 문자열(str)로 바꾸어 표현한다.

```python
# __str__ 메서드 알아보기
>>> porche = Car() # porche instance 생성
>>> print(porche) # __str__ 메서드 호출 : 인스턴스를 문자열로 바꾸어 표현.
```



 그 외에 doors, seats, start 등 class를 설계하며 정의한 속성과 메서드가 있음을 확인할 수 있다. 이들은 외부에서 접근할 수 있기 때문에, double underscore를 달고 있지 않다.