---
title:  "[Python] heapq 모듈"
excerpt:
header:
  teaser: /assets/images/blog-Dev.jpg
categories:
  - Language
toc : true
tags:
  - Python
  - 자료구조
  - 우선순위 큐
  - 힙
---



 파이썬에서 우선순위 큐 알고리즘을 구현할 수 있도록 제공하는 내장 모듈([공식 문서](https://python.flowdas.com/library/heapq.html))이다. 다만, 이 모듈은 **최소 힙**만을 지원한다. 따라서 최댓값을 찾아야 하는 경우는, 이 모듈을 응용하여 다른 방식으로 활용해야 한다.



<br>

# 개요



 파이썬이 설치되어 있다면, 다음과 같이 간단하게 임포트하여 힙 관련 함수를 사용할 수 있다.

```python
import heapq
```

 이 모듈은 일반 리스트를 최소 힙처럼 사용 다룰 수 있도록 한다. 따라서 아래와 같이 빈 리스트를 생성한 후, 모듈의 함수를 호출할 때 이 리스트를 인자로 넘기면 된다. 

```python
h = []
```

 즉, 빈 리스트를 생성하고, `heapq` 모듈의 함수를 통해 원소를 추가하거나 삭제하면, 그 결과로 반환되는 리스트가 바로 힙이 되는 것이다.



<br>

# 주요 함수

 사용할 수 있는 주요 함수는 다음과 같다.


## heappush

힙에 원소를 추가한다. 원소를 추가할 대상 리스트와 추가할 요소를 인자로 넣는다.

```python
h = []
heapq.heappush(h, 5)
heapq.heappush(h, 7)
heapq.heappush(h, 1)
heapq.heappush(h, 3)
print(h)

(실행 결과)
[1, 3, 5, 7]
```

 아래와 같이 튜플을 요소로 넣으면 튜플의 첫 번째 원소에 따라 정렬의 우선순위가 설정된다.

```python
h2 = []
heapq.heappush(h2, (5, 'write code'))
heapq.heappush(h2, (7, 'release product'))
heapq.heappush(h2, (1, 'write spec'))
heapq.heappush(h2, (3, 'create tests'))
print(h2)

(실행 결과)
[(1, 'write spec'), (3, 'create tests'), (5, 'write code'), (7, 'release product')]
```



## heappop

힙에서 가장 작은 원소를 삭제하고, 그 값을 리턴한다. 원소를 삭제할 대상 리스트만을 인자로 넣는다.

```python
print(heapq.heappop(h))
print(h)

(실행 결과)
1
[3, 7, 5]
```

```python
print(heapq.heappop(h2))
print(h2)

(실행 결과)
(1, 'write spec')
[(3, 'create tests'), (7, 'release product'), (5, 'write code')]
```



**[참고] 최솟값 삭제하지 않고 얻기**

 힙에서 최솟값을 삭제하지 않고 단순히 얻기만 하려면, 인덱스를 통해 접근하면 된다.

```python
print(h[0])

(실행 결과)
3
```

 주의할 점은, 힙 트리를 리스트로 표현한 것이기 때문에, 인덱스 0에 가장 작은 원소가 있다고 해서, 인덱스 1에 두 번째로 작은 원소, 인덱스 2에 세 번쨰로 작은 원소가 있다는 보장이 없다는 것이다. 따라서 두 번째로 작은 원소를 얻으려면 `heappop()`을 진행하고 난 후 인덱스 0에 접근해야 한다.



## heapify

이미 원소가 들어 있는 리스트를 힙으로 만든다. 리스트 내부의 원소들이 힙 트리 구조에 맞게 재배치되며 최솟값이 인덱스 0에 위치하게 된다.

```python
heap = [-1, 8, 15, 29, 3, -7, 3, -8, 5]
heapq.heapify(heap)
print(heap)

(실행 결과)
[-8, -1, -7, 5, 3, 15, 3, 29, 8]
```

인자로 넘기는 리스트 내 원소를 힙 구조에 맞게 정렬해야 하기 때문에 O(N)의 시간 복잡도를 갖는다.(문제 풀이 시 함부로 heapify를 하면 안 된다. [참고](https://www.acmicpc.net/board/view/40809))



## nlargest, nsmallest

리스트에서 n번째 큰 값을 반환하거나(nlargest), 작은 값(nsmallest)을 반환한다. 리스트 요소를 힙 트리 구조로 만든 후 반환하기 때문에, n이 1이라면 `min()`이나 `max()`를 사용하는 것이, n이 리스트의 길이와 비슷하거나 같다면 `sorted`를 사용한 후 slicing을 사용하는 것이 낫다.

```python
print(heapq.nlargest(3, heap))
print(heapq.nsmallest(3, heap))

(실행 결과)
[29, 15, 8]
[-8, -7, -1]
```



## 최대 힙의 구현



 위에서도 말했듯, `heapq` 모듈을 활용하여 최대 힙을 구현하려면 응용이 필요하다. 인터넷을 [찾아 보면](https://stackoverflow.com/questions/2501457/what-do-i-use-for-a-max-heap-implementation-in-python), `heapq._heapify_max`나 `heapq._heappop_max`를 사용할 수 있는 것 같다. 그렇지만 push할 수 없고, 이미 최소힙으로 정렬된 상태에서 최댓값을 찾는 것이기 때문에 온전히 최대 힙을 구현한 것이라는 생각이 들지는 않는다.



  튜플을 원소로 추가하여 힙을 만들 수 있다는 원리를 이용하면, 최대 힙을 구현할 수 있다([참고](https://stackoverflow.com/questions/48255849/how-to-get-the-max-heap-in-python)). 튜플 내 우선순위를 값에 `-`를 취한 값으로 설정하면 된다. 양수 범위에서 큰 값은 음수 범위에서는 작아지기 때문에, 가장 큰 값이 최솟값이 되는 것이다. 이후 최댓값을 불러오고 싶다면, `heappop`을 한 뒤, 튜플의 두 번째 요소만을 읽어 오면 된다.



```python
nums = [24, 11, -7, -3, 18, 55]
myheap = []
for num in nums:
  heapq.heappush(myheap, (-num, num))  # (우선 순위, 값)
print(myheap)
print(heapq.heappop(myheap)[1])

(실행 결과)
[(-55, 55), (-18, 18), (-24, 24), (3, -3), (-11, 11), (7, -7)]
55
```