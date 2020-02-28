---
title:  "Python, 두 번 검색하지 말자!"
excerpt: "Python 문법, 구문 등 표현에 관한 사항을 정리합니다."
toc: true
toc_sticky: true
header:
  teaser: /assets/images/blog-Programming.jpg

categories:
  - Programming
tags:
  - Python
last_modified_at: 2019-04-13T08:06:00-05:00
---







# _"2번 검색하지 말자"_

> 문제 풀이를 하면서 Python 언어의 문법, 자료 구조 등에 관해 [Stack Overflow](https://stackoverflow.com/), [Python Documentation](https://docs.python.org/3/library/index.html), 각종 블로그 등을 구글링하며, 다음에 다시 찾고 싶지 않은 내용들을 정리했습니다. 
>
> 처음 Python을 배우기 시작한 후로 정리한 내용이므로 기초적인 내용부터 심화된 내용까지 혼재되어 있습니다. 계속해서 내용이 추가될 수 있습니다.



*이 글이 마지막으로 수정된 시각은 {{ page.last_modified_at }} 입니다.*





## 입출력

---

* 빠른 입력 : sys.stdin.readline(), sys.stdin.readlines()를 사용한다.
  * 한 줄 입력 받을 때는 readline()를, 여러 줄 입력 받을 때는 readlines()를 사용한다. 이 때, 전자의 경우 문자열(str)을, 후자의 경우 list를 반환한다.
  * 입력 시 new line이 들어간다. 실제 테스트할 때에도 입력을 종료하기 위해서는 `Enter` + `Ctrl Z`가 필요하다. 문제 풀이에 사용할 때에는 .strip()을 통해 **개행문자를 제거**하는 것이 좋다.



* list(input()) : 입력 문자열을 한 글자씩 list로 반환할 때 사용한다.



* *(asterlisk) : 가변 길이 인자 받을 때 사용.

  ```python
  (사용 예)
  n, *x = map(int, input().split())
  
  1 2 3 4 5 6 7 8 9 # 입력
  1 # n
  [2, 3, 4, 5, 6, 7, 8, 9] # x
  ```





## 자료구조

---



### list



#### iterable에 대한 이해

> 아래의 항목은, 공통적으로 iterable에 대한 이해가 필요하다. iterable은 그 member를 하나씩 차례로 반환할 수 있는 객체를 의미한다. iterable에 대한 이해가 없어서 다음과 같은 어려움을 겪은 적이 있다.



* range로 [1, 2, 3, 4, 5]와 같은 list를 생성하고 싶다면, [range(0,5)]가 아니라, list(range(0,5))를 사용해야 한다.
  * list() 메서드는 iterable 객체를 받아 그 요소들을 list로 만들어 준다. 즉, list(x)의 의미는 iterable한 x의 요소들로 list를 생성한다는 의미이다. 즉, 예컨대, list('abc')는 ['a', 'b', 'c']를, list((1,2,3))은 [1, 2, 3]을 반환한다.
  * 반면, [x]는 한 요소가 x인 list를 생성한다. 다시 말해, [range(0, 5)]는 range(0, 5)라는 range 객체를 하나의 요소로 가지는 list이다. 
* range로 [1, 2, 3]을 [1, 2, 3, 4, 5, 6, 7]로 만들고 싶다면, list.append(range(4, 8))이 아니라, list.extend(range(4, 8))을 사용해야 한다.
  * list.append(x)는 list의 끝에 x라는 요소 하나를 넣는다. 즉, [1, 2, 3, range(4, 8)]이 반환된다.
  * list.extend(iterable)은 list의 끝에 iterable의 모든 항목을 넣는다. 즉, [1, 2, 3, 4, 5, 6, 7]이 반환된다.



#### list comprehension





## map

---

* 정의 `iterable` (반복 가능한) 객체를 받아서, 각 요소에 함수를 적용하는 함수.
* 사용 방법 : map(적용할 함수, 적용할 요소들)
  * 내장함수를 적용할 수도 있고, 함수를 정의해서 적용할 수도 있다.
  * 



## zip



## enumerate



