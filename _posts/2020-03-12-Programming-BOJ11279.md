---
title:  "[백준] BOJ11279 최대 힙"
excerpt:
header:
  teaser: /assets/images/blog-Programming.jpg

categories:
  - Programming
tags:
  - Python
  - Programming
  - BOJ
  - 자료구조
  - 힙
  - 우선순위 큐
---

> [문제 출처](https://www.acmicpc.net/problem/11279)



## 문제

---

널리 잘 알려진 자료구조 중 최대 힙이라는 것이 있다. 최대 힙을 이용하여 다음과 같은 연산을 지원하는 프로그램을 작성하시오.

1. 배열에 자연수 x를 넣는다.
2. 배열에서 가장 큰 값을 출력하고, 그 값을 배열에서 제거한다. 

프로그램은 처음에 비어있는 배열에서 시작하게 된다.



### 입력

첫째 줄에 연산의 개수 N(1≤N≤100,000)이 주어진다. 다음 N개의 줄에는 연산에 대한 정보를 나타내는 정수 x가 주어진다. 만약 x가 자연수라면 배열에 x라는 값을 넣는(추가하는) 연산이고, x가 0이라면 배열에서 가장 큰 값을 출력하고 그 값을 배열에서 제거하는 경우이다. 입력되는 자연수는 2^31보다 작다.

### 출력

입력에서 0이 주어진 회수만큼 답을 출력한다. 만약 배열이 비어 있는 경우인데 가장 큰 값을 출력하라고 한 경우에는 0을 출력하면 된다.



## 풀이 방법

---

---

* 처음에는 모듈을 사용하지 않고 풀려고 고집을 부리다가(...) 여러 차례의 시간 초과([cf412d6](https://github.com/sirzzang/Baekjoon_problems/blob/master/25_우선순위큐/우선순위큐_최대힙_BOJ11279_시간초과.py))를 겪었다. 이 때 구현하고 싶었던 방식은 *stack을 활용해* **큰 값일수록 뒤에 위치**하도록 하는 것이다. 
  * stack의 pop 방식을 이용하면 시간 복잡도가 줄어들 것이라 생각했다.
  * 힙을 알고 난 후, 이 방법을 다시 보니 **우선순위를 부여하기 위해** 순차적으로 원소를 탐색해야 하므로(최악의 경우 끝까지 탐색해 가야 한다) 애초에 stack에 push하는 과정에서 시간 초과가 날 수밖에 없는 방식이다.
* `heapq` 모듈이 최소 힙만을 지원한다는 사실에 유의하고, 모듈을 응용하면 쉽게 풀린다.





## 풀이 코드

---

---

* 우선순위로 입력값에 `-`를 취한 값을 지정한다. 출력할 때는 튜플의 두 번째 원소만을 읽어 온다.

*45468KB, 192ms*

```python
import sys
import heapq

max_heap = []
N = int(sys.stdin.readline())

for _ in range(N):
    com = int(sys.stdin.readline())

    if com == 0:
        if len(max_heap) == 0:
            print(0)
        else:
            print(heapq.heappop(max_heap)[1])
    
    else:
        heapq.heappush(max_heap, (-com, com))
```



* 문제 조건에 자연수만 입력으로 주어지기 때문에, 튜플을 push하지 않고 바로 음수로 만들어 준 입력값을 push해도 된다. 위의 방식보다 시간이 줄어든다. 그러나 이는 음수와 양수가 모두 입력으로 주어지는 문제의 경우 적합하지 않은 풀이 방식이다. 

```python
import sys
import heapq

max_heap = []
N = int(sys.stdin.readline())

for _ in range(N):
    com = int(sys.stdin.readline())

    if com == 0:
        if len(max_heap) == 0:
            print(0)
        else:
            print(-heapq.heappop(max_heap))
    
    else:
        heapq.heappush(max_heap, -com)
```





## 다른 풀이

---

> [코드 출처](https://www.acmicpc.net/source/8587880)



*34204KB, 128ms*

```python
import sys, heapq

heap = []

input()

for value in map(int, sys.stdin):
	heapq.heappush(heap, -value) if value else print(heap and -heapq.heappop(heap) or 0)
```

* print 방식을 잘 보자.
* 입력값이 0이 아닌 value값으로 들어오는 경우 push하고, heap이 있는 경우 pop한 값을, 아니면 0을 출력한다.



## 배운 점, 더 생각해 볼 것

* 힙과 힙큐 모듈에 대해 배웠다.
