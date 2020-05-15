---
title:  "[NomadCoders] Making WebScrapper with Python_2.2_2"
excerpt: "Django 기초 - OOP"
header:
  teaser: /assets/images/nomad_scrapper.png
categories:
  - SELF
tags:
  - 함수
  - arguments
  - 노마드코더
last_modified_at: 2020-03-23
---





# Python으로 웹 스크래퍼 만들기



## 2. Get Ready for Django

 파이썬의 Django 프레임워크를 이용하면 쉽게 웹 애플리케이션을 개발할 수 있다. Django는 웹 앱을 개발하기 위한 ~~*아주 멋진*~~ class들의 모임이다. 따라서 Django를 이용하여 웹 앱을 개발하기 위해서는 다음의 기본적인 개념들을 알아야 한다.



### 2.2. OOP_2



**5) 재정의(override)**

 class가 갖는 메서드를 다른 방식으로 사용하고 싶다면, 재정의하면 된다.

 다음과 같이 `__str__` 메서드를 재정의하면, instance가 print()를 통해 호출되는 순간 새로 정의된 `__str__` 함수가 호출되며, 이전과 다른 결과가 나타난다.

```python
# __str__ 메서드 재정의
class Car():
    wheels = 4
    doors = 4
    windows = 4
    seats = 4
    
    def __str__(self): # override '__str__'
        return "__str__ 메서드가 실행되었습니다."

>>> porche = Car() # porche 인스턴스 생성
>>> print(porche) # __str__ 메서드 호출 : 재정의한 __str__ 메서드 작동.
# __str__ 메서드가 실행되었습니다.
```



**6) 생성자 메서드**

 class로부터 instance가 **만들어질 때** 그 객체가 갖게 될 여러 속성을 정해준다. 초기화 메서드라고도 하며, class로부터 instance가 생성되는 즉시 호출된다. `__init__` 함수로 사용한다.

 파이썬 생성자 규칙과 동일하게, 첫 인자는 무조건 instance 자신을 지칭하는 self가 되어야 한다. 그리고 정의할 속성들 앞에는 반드시 'self'가 붙어야 한다.

 여태까지 설계했던 자동차 class와 달리, 이제는 생성자를 통해 자동차 class로부터 만들어질 자동차 instance들이 생성자를 통해 생성되는 속성을 갖게 설계할 수 있다.

```python
# Car 클래스 설계 : 생성자 메서드 활용, 기본값 설정.
class Car():
    def __init__(self):
        self.wheels = 4
        self.doors = 4
        self.windows = 4
        self.seats = 4
    
    def start(self):
        return "Car started!"

# porche 인스턴스 생성 및 호출
>>> porche = Car()
>>> print(porche.windows) # 4
```

 위와 같은 자동차 class로 instance를 생성할 경우, 각 속성의 기본값이 4로 설정된 자동차 instance가 만들어진다. 



 만약, 서로 다른 속성 값을 갖는 instance를 생성하고 싶다면, 다음과 같이 설계하면 된다. 이 경우, **instance를 호출할 때 인자로 값을 넘겨야 함**을 잊지 말자.

```python
# Car 클래스 설계 : 생성자 메서드 활용.
class Car():
    def __init__(self, wheels, doors, windows, seats):
        self.wheels = wheels
        self.doors = doors
        self.windows = windows
        self.seats = seats
    
    def start(self):
        return "Car started!"

# porche 인스턴스 생성 및 호출
>>> porche = Car(4, 3, 2, 1)
>>> print(porche.windows) # 2
```



 생성자에 키워드 인자를 활용하여 가변 길이의 속성을 생성할 수도 있다. 키워드 인자는 dict 형태임을 활용해, `.get()` 함수를 통해 속성을 설정한다. 해당 속성이 입력되지 않을 경우 기본값을 지정할 수도 있다.

```python
# Car 클래스 설계 : 생성자 메서드, 키워드 인자 포함.
class Car():
    def __init__(self, **kwargs):
        # 미리 정의된 속성
        self.wheels = 4
        self.doors = 4
        self.windows = 4
        self.seats = 4
        # 키워드 인자를 통해 받는 속성
        self.color = kwargs.get('color', 'BLACK')
        self.price = kwargs.get('price', '$1000')
    
    def start(self):
        return "Car started!"

# porche 인스턴스 생성
>>> porche = Car(color='GREEN', price='$30')
>>> print(porche.color, porche.price) # GREEN $30

# bmw 인스턴스 생성
>>> bmw = Car()
>>> print(bmw.color, bmw.price) # BLACK $1000
```



**7) 상속(inherit)**

 이제 차에 지붕이 열리는 기능을 만들어 보자. 

```python
# Car class 설계 : 지붕 열리는 메서드 추가.
class Car():
    def __init__(self, **kwargs):
        self.wheels = 4
        self.doors = 4
        self.windows = 4
        self.seats = 4
        self.color = kwargs.get('color', 'BLACK')
        self.price = kwargs.get('price', '$1000')
    
    def __str__(self):
        return f"바퀴가 {self.wheels}개인 차입니다."
    
    def take_off(self): # 지붕을 여는 기능
        return "지붕을 엽니다."
```



 그런데 이 경우, Car class를 통해 만들어지는 모든 자동차 instance들은 전부 다 `take_off` 기능이 있는 오픈카가 되어 버린다. 

```python
# 해당 클래스로 생성하는 모든 인스턴스들이 지붕이 열리는 차가 된다.
>>> porche = Car(color='GREEN', price='$30')
>>> sonata = Car()
>>> print(porche, porche.take_off())
# 바퀴가 4개인 차입니다. 지붕을 엽니다.
>>> print(sonata, sonata.take_off()) # 문제 : sonata는 오픈카가 아니라면?
# 바퀴가 4개인 차입니다. 지붕을 엽니다.
```

 이 문제를 해결하려면, 자동차이면서, 지붕을 여는 기능만 추가된 새로운 자동차 class를 설계하면 된다.



 이 때 **'상속(inherit)'**을 활용하면 된다. 상속이란, 기존의 class에 기능을 추가하거나 재정의하여 새로운 class를 정의하는 것이다.

 파이썬에서는 새로운 class의 인자로 기존 class를 넘겨 기존 class를 상속한다. 상속을 통해 새롭게 만든 class에서는 부모 class의 속성, 메서드를 그대로 사용할 수 있다.

 이제 기존 자동차에서 지붕을 여는 기능만 추가된 오픈카 class를 만들어 보자.

```python
# Car 클래스 : 기본 자동차.
class Car():
    def __init__(self, **kwargs):
        self.wheels = 4
        self.doors = 4
        self.windows = 4
        self.seats = 4
        self.color = kwargs.get('color', 'BLACK')
        self.price = kwargs.get('price', '$1000')
    
    def __str__(self):
        return f"바퀴가 {self.wheels}개인 차입니다."

# Convertible 클래스 : 지붕이 열리는 오픈카.
class Convertible(Car):
    def take_off(self):
        return "지붕을 엽니다."
```

  이제 각각의 class로부터 오픈카가 아닌 일반 자동차 instance와 오픈카 instance를 생성해 보자. 당연히, take_off 메서드는 Convertible 클래스로부터 생성된 인스턴스에만 적용된다.

```python
# 오픈카와 오픈카가 아닌 차를 구별하여 인스턴스 생성
>>> porche = Convertible(color='GREEN', price='$30')
>>> sonata = Car()
>>> print(porche, porche.take_off())
# 바퀴가 4개인 차입니다. 지붕을 엽니다.
>>> print(sonata)
# 바퀴가 4개인 차입니다.
>>> print(sonata.take_off())
# AttributeError: 'Car' object has no attribute 'take_off'
```



 상속을 통해 새롭게 생성한 class에서 필요한 경우, 기존 class의 메서드를 재정의할 수 있다.

```python
# Convertible 클래스 : 부모 클래스 메서드 재정의.
class Convertible(Car):
    def take_off(self):
        return "지붕을 엽니다."
    
    def __str__(self):
        return f"바퀴가 {self.wheels}개인 차입니다. 오픈카입니다."

# 오픈카가 아닌 sonata 인스턴스 생성
>>> sonata = Car()
>>> print(sonata)
# 바퀴가 4개인 차입니다.
>>> print(sonata.color)
# BLACK

# 오픈카인 porche 인스턴스 생성
>>> porche = Convertible(color='GREEN', price='$30')
>>> print(porche) # 재정의된 __str__ 메서드 호출
# 바퀴가 4개인 차입니다. 오픈카입니다.
>>> print(porche.color)
# GREEN
>>> print(porche.take_off())
# 지붕을 엽니다.
```

 

 class를 상속할 때 기존의 메서드를 재정의하지 않고, 확장할 수도 있다. 이 경우 `super()` 함수를 이용한다. `super()` 함수는 부모 class를 호출하는 함수로, 기존 class에 정의된 속성, 메서드 등에 모두 접근할 수 있다.



 예컨대, 오픈카 instance가 생성될 때, 기존의 자동차 instance가 갖는 속성들에 더해 지붕이 열리는 시간을 속성으로 추가하고 싶다면, 다음과 같이 Convertible class를 설계하면 된다.

```python
# Convertible 클래스 설계 : 부모 클래스 생성자 메서드 확장.
class Convertible(Car):
    def __init__(self, **kwargs):
        super().__init__(**kwargs) # 부모 클래스인 Car의 init 메서드 호출.
        self.time = kwargs.get('time', 10)
        
    def take_off(self):
        return "지붕을 엽니다."
    
    def __str__(self):
        return f"바퀴가 {self.wheels}개인 차입니다. 오픈카입니다."

>>> porche = Convertible()
>>> print(porche.color) # BLACK
>>> print(porche.time) # 10
```



*참고*

* 새롭게 속성을 추가하고 싶어서 다음과 같이 `__init__` 메서드를 재정의하면, 부모 class에서 생성되는 속성이 사라진다.

![convertible attribute error]({{site.url}}/assets/images/convertibleerror.ong){: width="60%" height="60%"}{: .center}

