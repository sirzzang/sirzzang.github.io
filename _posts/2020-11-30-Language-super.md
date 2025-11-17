---
title:  "[Python] super() vs. super(Class)"
excerpt: 문득 궁금해진 파이썬 super 키워드
categories:
  - Language
toc: false
header:
  teaser: /assets/images/blog-Dev.jpg
tags:
  - Python
  - super
  - 상속
---





 PyTorch의 class형 모델 코드를 살펴 보다가, `super([모델명], self).__init__()`이라는 코드를 보고 의문이 생겼다. `super`가 그 전에는 부모 클래스를 상속받는 것이라고 생각했었는데, 왜 그 인자로 자기 자신의 모델명을 넣는 것인가. ~~객체 무식자…~~



<br>

 이 [stackoverflow 글](https://stackoverflow.com/questions/14743787/python-superclass-self-method-vs-superparent-self-method)을 통해 이해한 바로는 다음과 같다.

* `super`는 하위 클래스의 이름과 하위 클래스의 object를 파라미터로 받는다.
* 인자로 하위 클래스의 이름을 명시하면, 그 부모로부터 탐색한다.

<br>

 다음과 같이 코드를 실행해서 `super`가 반환하는 것이 무엇인지 정확히 알아 보자.

```python
class A(object):
    def do_work(self):
        print('A의 do_work')
        
class B(A): # A를 상속받는 클래스
    print(super(B, self))
    print(super(A, self))

b = B()
# <super: <class 'B'>, <B object>>
# <super: <class 'A'>, <B object>>
```

 인자로 클래스를 받고, object를 리턴하는 것은 알겠는데, 정확히 감이 오지 않는다.

<br>

```python
class A(object):
    def do_work(self):
        print('A의 do_work')
        
class B(A): # A를 상속받는 클래스
    def do_work(self):
        print(1)
        super(B, self).do_work()
        print(2)
        super(A, self).do_work()

# B 인스턴스 생성
b = B()
b.do_work()
```

 위의 코드를 실행해 보면, 다음과 같이 2까지는 실행되고, AttributeError가 난다.

```
1
A의 do_work
2
AttributeError: 'super' object has no attribute 'do_work'
```

<br>

 즉, super는 인자로 받은 클래스의 부모 클래스의 object들을 가져 온다. 리턴된 자기 자신 클래스의 object에서는 인자로 넘긴 클래스의 부모가 갖는 메소드들을 사용할 수 있는 것이다. 

 리턴하는 것은 `B` 클래스의 인스턴스이지만, 그 인스턴스가 가져 오는 object들은 인자로 받은 클래스의 부모 클래스가 갖는 것들이다. 위의 코드에서 마지막에 에러가 난 원인은, A의 부모 클래스가 없기 때문이다. 

<br>

 조금 더 명확히 해 보자.

```python
class A(object):
    def do_work(self):
        print('A의 do_work')

class B(A):
    def do_work(self):
        print('B의 do_work')
        super(B, self).do_work()

class C(B):
    def do_work(self):
        print(1)
        super(C, self).do_work()
        print(2)
        super(B, self).do_work()
        print(3)
        super(A, self).do_work

# C 인스턴스 생성
c = C()
c.do_work()
```

 실행해 보면 결과는 다음과 같다.

```
1
B의 do_work
A의 do_work
2
A의 do_work
3
AttributeError: 'super' object has no attribute 'do_work'
```

 `1`  출력 이후에는 `C`의 부모 클래스인 `B`의 `do_work` 메소드에서의 `print`가 실행되고, 다음 줄 코드로 넘어가 `B`의 부모 클래스인 `A`의 `do_work` 메소드에서의 `print`가 실행된다.

 `2` 출력 이후에는 `B`의 부모 클래스인 `A`의 `do_work` 메소드에서의 `print`가 실행된다.

 `3` 출력 이후에는 (현재 코드 상에서) 최상위 클래스인 `A`가 상속받는 클래스가 없으므로(*=A의 부모 클래스가 없으므로*)  오류가 난다.

<br>

 그렇다면 `super`에 인자를 넘기지 않는다면 어떻게 될까. 

```python
class A(object):
    def do_work(self):
        print('A의 do_work')

class B(A):
    def do_work(self):
        print('B의 do_work')
        super().do_work()

class C(B):
    def do_work(self):
        print(1)
        super().do_work()
        print(2)
        super().do_work()
        print(3)
        super().do_work

# C 인스턴스 생성
c = C()
c.do_work()
```

 실행해 보면, 다음과 같이 아무런 오류 없이 잘 실행된다!

```python
1
B의 do_work
A의 do_work
2
B의 do_work
A의 do_work
3
B의 do_work
A의 do_work
```



<br> 결론적으로 인자를 넘기지 않으면 `super`의 할머니까지 탐색해서 object를 가져 오고, 인자를 넘기면 인자로 명시된 클래스의 부모에서 object를 탐색해서 가져 온다.

<br>

 **어쨌든**, 아래 코드([출처](https://github.com/Seanny123/da-rnn/blob/master/modules.py))에서 원래 궁금했던 것은 `Encoder` 클래스의 부모 클래스인 `nn.Module` 클래스의 생성자를 상속받는 것이었다!

![pytorch-code-example]({{site.url}}/assets/images/pytorch-example.png){: .align-center}



