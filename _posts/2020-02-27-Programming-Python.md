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
last_modified_at: 2020-03-03
---







# _"2번 검색하지 말자"_

> 문제 풀이를 하면서 Python 언어의 문법, 자료 구조 등에 관해 [Stack Overflow](https://stackoverflow.com/), [Python Documentation](https://docs.python.org/3/library/index.html), 각종 블로그 등을 구글링하며, 다음에 다시 찾고 싶지 않은 내용들을 정리했습니다. 



*이 글이 마지막으로 수정된 시각은 {{ page.last_modified_at }} 입니다.*





## 1. 입출력

---

* 빠른 입력 : sys.stdin.readline(), sys.stdin.readlines()를 사용한다.
  * 한 줄 입력 받을 때는 readline()를, 여러 줄 입력 받을 때는 readlines()를 사용한다. 이 때, 전자의 경우 문자열(str)을, 후자의 경우 list를 반환한다.
  * 입력 시 new line이 들어간다. 실제 테스트할 때에도 입력을 종료하기 위해서는 `Enter` + `Ctrl Z`가 필요하다. 문제 풀이에 사용할 때에는 .strip()을 통해 **개행문자를 제거**하는 것이 좋다.



* list(input()) : 입력 문자열을 한 글자씩 list로 반환할 때 사용한다.



* *(asterlisk) : 가변 길이 인자 받을 때 사용.

  ```python
  (사용 예)
  n, *x = map(int, input().split())
  
  >> 1 2 3 4 5 6 7 8 9
  1 # n
  [2, 3, 4, 5, 6, 7, 8, 9] # x
  ```



* print('%.10f' % num) : 출력 시 소수점 자리 수를 10자리로 제한하고 싶을 때 사용.
* `.rjust(n)` : n자리 칸에서 오른쪽 정렬하여 출력, `.ljust(n)` : n자리 칸에서 왼쪽 정렬하여 출력.



## 2. 자료구조

---

### [list](https://docs.python.org/3/tutorial/datastructures.html)



#### 특정 메서드(iterable) vs. 특정 메서드(x)

> iterable은 그 member를 **하나씩 차례로 반환할 수 있는 객체**를 의미한다.
>
> iterable한 type으로는 list, dict, set, str, bytes, tuple, range가 있다.



* list() 메서드는 iterable 객체를 받아 그 요소들을 list로 만들어 준다. 반면, [x]는 요소가 x인 list를 생성한다.

  ```python
  >>> list('abc')
  ['a', 'b', 'c']
  >>> list(range(0,5))
  [0, 1, 2, 3, 4]
  >>> [range(0,5)] # range object를 element로 갖는 list.
  [range(0, 5)]
  ```

* list.append(x) vs. list.extend(iterable)
  
  * list.append(x)는 list의 끝에 x라는 요소 하나를 넣는다.
  
  * list.extend(iterable)은 list의 끝에 iterable의 모든 항목을 덧붙여서 넣는다.
  
  ```python
  >>> myList = ['a', 'b', 'c']
  >>> myList.append(range(2))
  ['a', 'b', 'c', range(0, 2)] # range object 자체를 더한다.
  >>> myList.extend(range(2))
  ['a', 'b', 'c', 0, 1] # list에 iterable
  ```
  
* sorted(list)는 vs. reversed(list)

  * sorted(list) : 오름차순으로 정렬된 list를 반환.
  * reversed(list) : list를 뒤집은 iterable 객체를 반환. 확인하려면 list 메서드로 변형해야 함.

  ```python
  >>> myList = [3, 16, 5, 8, 7, 6]
  >>> sorted(myList)
  [3, 5, 6, 7, 8, 16]
  >>> reversed(myList)
  <list_reverseiterator object at 0x0351A160>
  >>> list(reversed(myList))
  [3, 16, 5, 8, 7, 6]
  ```

  







#### list comprehension

* 









## 3. 함수

### map



* 정의 `iterable` (반복 가능한) 객체를 받아서, 각 요소에 함수를 적용하는 함수.
* 사용 방법 : map(적용할 함수, 적용할 요소들)
  * 내장함수를 적용할 수도 있고, 함수를 정의해서 적용할 수도 있다.
  * 



### zip



### enumerate

* 반복문 사용 시 
* https://suwoni-codelab.com/python%20%EA%B8%B0%EB%B3%B8/2018/03/03/Python-Basic-for-in/



### key를 사용한 정렬

> list, dictionary 등을 정렬할 때, key 파라미터를 지정함으로써 특정 기준에 따라 정렬할 수 있다.



* key 파라미터 : 정렬에 사용할 비교 함수.

  * 익명 함수(lambda)도 활용할 수 있고, 별도로 정의할 수도 있다.
  * 비교할 아이템이 여러 개의 요소로 구성되어 있을 경우, 튜플로 그 순서를 지정할 수 있다. 이 때, `-`를 붙이면, 현재의 정렬 차순과 반대로 정렬한다.

* [list에서의 사용 예](https://docs.python.org/ko/3/howto/sorting.html)

  * **문자열**에서의 사용

  ```python
  # 대문자, 소문자 동일하게 취급해서 정렬 
  >>> sorted("This is a test string from Andrew".split(), key=str.lower)
  ['a', 'Andrew', 'from', 'is', 'string', 'test', 'This']
  
  # 글자수로 정렬
  m = "This is a test string from Anderew".split()
  
  >>> m.sort(key=len)
  ['a', 'is', 'This', 'test', 'from', 'string', 'Anderew']
  
  ```

  * **다중 조건** 사용

  ```python
  myList = [(1,4), (3, 5), (0, 6), (5, 7), (3, 8), (5, 9), (6, 10), (8, 11), (8, 12), (2, 13), (12, 14)]
  
  >>> sorted(myList, key = lambda x : x[0])
  [(0, 6), (1, 4), (2, 13), (3, 5), (3, 8), (5, 7), (5, 9), (6, 10), (8, 11), (8, 12), (12, 14)]
  >>> sorted(myList, key = lambda x : x[1])
  [(1, 4), (3, 5), (0, 6), (5, 7), (3, 8), (5, 9), (6, 10), (8, 11), (8, 12), (2, 13), (12, 14)]
  # (3, 5)와 (3, 8) 비교, (8, 11)과 (8, 12)비교.
  >>> sorted(myList, key = lambda x : (x[0], x[1]))
  [(0, 6), (1, 4), (2, 13), (3, 5), (3, 8), (5, 7), (5, 9), (6, 10), (8, 11), (8, 12), (12, 14)]
  >>> sorted(myList, key = lambda x : (x[0], -x[1]))
  [(0, 6), (1, 4), (2, 13), (3, 8), (3, 5), (5, 9), (5, 7), (6, 10), (8, 12), (8, 11), (12, 14)]
  ```

* [dictionary에서의 사용 예](https://rfriend.tistory.com/473)

  * **key를 기준**으로  정렬 : 
    * dict.keys() : key만 정렬된 값 반환.
    * dict.items() : key를 기준으로 정렬하되, key와 value를 tuple로 묶어서 정렬된 값 반환.

  ```python
  pgm_lang = {
      "java": 20, 
      "javascript": 8, 
      "c": 7,  
      "r": 4, 
      "python": 28 } 
  
  >>> sorted(pgm_lang.keys())
  ['c', 'java', 'javascript', 'python', 'r']
  >>> sorted(pgm_lang.items())
  [('c', 7), ('java', 20), ('javascript', 8), ('python', 28), ('r', 4)]
  
  # lambda 함수를 이용하여 key의 길이를 기준으로 오름차순 정렬
  >>> pgm_lang_len = sorted(pgm_lang.items(), key = lambda item: len(item[0])) 
  [('c', 7), ('r', 4), ('java', 20), ('python', 28), ('javascript', 8)]
  ```

  * **value를 기준**으로 정렬 : lambda 함수 사용하여 item[1]로 지정.

  ```python
  >> sorted(pgm_lang.items(), key = lambda item: item[1]) # value: [1]
  [('r', 4), ('c', 7), ('javascript', 8), ('java', 20), ('python', 28)]
  ```

* 객체에서의 사용

  * lambda 함수로 객체의 attribute를 지정할 수 있음.

  ```python
  >>> class Student:
  ...     def __init__(self, name, grade, age):
  ...         self.name = name
  ...         self.grade = grade
  ...         self.age = age
  ...     def __repr__(self):
  ...         return repr((self.name, self.grade, self.age))
  
  >>> student_objects = [
  ...     Student('john', 'A', 15),
  ...     Student('jane', 'B', 12),
  ...     Student('dave', 'B', 10),
  ... ]
  >>> sorted(student_objects, key=lambda student: student.age) # age attribute로 정렬.
  [('dave', 'B', 10), ('jane', 'B', 12), ('john', 'A', 15)]
  
  
  ```

  

## 4. 기타



### any, all을 사용한 조건문

* if any(*조건* for element in iterable) : iterable 안의 element 중 하나라도 조건을 만족한다면,
* if all(*조건* for element in iterable) : iterable의 모든 element가 조건을 만족한다면,

 







