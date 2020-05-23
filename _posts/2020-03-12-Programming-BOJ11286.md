---
title:  "[백준] BOJ11286 절댓값 힙"
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

> [문제 출처](https://www.acmicpc.net/problem/11286)



## 문제

---

---

절댓값 힙은 다음과 같은 연산을 지원하는 자료구조이다.

1. 배열에 정수 x (x ≠ 0)를 넣는다.
2. 배열에서 절댓값이 가장 작은 값을 출력하고, 그 값을 배열에서 제거한다. 절댓값이 가장 작은 값이 여러개일 때는, 가장 작은 수를 출력하고, 그 값을 배열에서 제거한다.

프로그램은 처음에 비어있는 배열에서 시작하게 된다.



### 입력

첫째 줄에 연산의 개수 N(1≤N≤100,000)이 주어진다. 다음 N개의 줄에는 연산에 대한 정보를 나타내는 정수 x가 주어진다. 만약 x가 0이 아니라면 배열에 x라는 값을 넣는(추가하는) 연산이고, x가 0이라면 배열에서 절댓값이 가장 작은 값을 출력하고 그 값을 배열에서 제거하는 경우이다. 입력되는 정수는 -2^31보다 크고, 2^31보다 작다.

### 출력

입력에서 0이 주어진 회수만큼 답을 출력한다. 만약 배열이 비어 있는 경우인데 절댓값이 가장 작은 값을 출력하라고 한 경우에는 0을 출력하면 된다.



## 풀이 방법

---

* 음수가 들어올 때와 양수가 들어올 때의 힙을 나누어 구현한다.
  * 양수의 경우 실제 값과 절댓값의 크기 순서가 일치하기 때문에, 최소 힙으로 구현한다.
  * 음수의 경우 실제 값이 클수록 절댓값이 크기 때문에, 최대 힙으로 구현한다.
* 절댓값이 작으면 음수부터 출력해야 하기 때문에, 음수 힙에 들어 있는 *모든* 수의 절댓값이 양수 힙에서 가장 작은 수의 절댓값보다 크지 않은 한 음수 힙에서 우선적으로 출력한다. 즉, 음수 힙 -> 양수 힙 -> 음수 힙 -> 양수 힙 ... 의 순서로 순회하며 절댓값이 작은 순서대로 뽑아 나간다.



## 풀이 코드

---

* 음수 힙이나 양수 힙 둘 중 하나라도 비면 `IndexError`가 나는 점을 이용하기 위해, try, except 절을 사용했다. 특히, except절에서 음수 힙이나 양수 힙이 모두 비는 경우 0을 출력한다.
* 음수 힙의 출력에 주의한다!



*32832KB, 156ms : 0312 기준 5등이다!!!!!*

```python
import sys
import heapq

N = int(sys.stdin.readline())
neg_heap = []
pos_heap = []

for _ in range(N):
    num = int(sys.stdin.readline())

    if num > 0:
        heapq.heappush(pos_heap, num)    
    elif num < 0 :
        heapq.heappush(neg_heap, -num)
    
    else: # 0이 들어올 때
        try:
            if pos_heap[0] < neg_heap[0]: # 양수 힙 최솟값이 음수 힙 최소 절댓값보다 작으면,
                print(heapq.heappop(pos_heap))
            elif pos_heap[0] >= neg_heap[0]: # 그렇지 않으면 음수 힙에서 우선 출력.
                print(-heapq.heappop(neg_heap))
        except IndexError: # heap이 하나라도 비어서 IndexError가 나는 경우.
            if len(neg_heap) == 0: # neg_heap이 비었을 때
                if len(pos_heap) == 0: # pos_heap도 비었으면 0 출력.
                    print(0)
                else:
                    print(heapq.heappop(pos_heap)) # 아니면 pos_heap에서 pop.
            elif len(pos_heap) == 0: # 같은 방식
                if len(neg_heap) == 0:
                    print(0)
                else:
                    print(-heapq.heappop(neg_heap))
```





## 다른 풀이

---

> [코드 출처](https://www.acmicpc.net/source/16238466)

*32912KB, 148ms*

```python
from heapq import *
input=__import__('sys').stdin.readline

Pq,Mq=[],[]
for i in range(int(input())):
    n=int(input())
    if n==0:
        if len(Pq)!=0 and (len(Mq)==0 or Pq[0]<Mq[0]):
            print(heappop(Pq))
        elif len(Mq)!=0 and (len(Pq)==0 or Mq[0]<=Pq[0]):
            print(-heappop(Mq))
        else:print(0)
    if n>0:heappush(Pq,n)
    elif n<0:heappush(Mq,-n)
```

* 내가 except 절에 구현한 방식을 `if n==0` 안의 if, elif절로 한 번에 구현했다.



> [코드 출처](https://www.acmicpc.net/source/17216507)

*38664KB, 148ms*

```python
import sys
from heapq import *
input = sys.stdin.readline
def BOJ_11286():
    input()
    heap = []
    for x in map(int,sys.stdin):
        if x != 0:
            heappush(heap, (abs(x), x))
        else:
            print(heappop(heap)[1] if heap else 0)
BOJ_11286()
```

* 최댓값 힙을 구현할 때 방식을 응용해, 우선순위를 절댓값으로 주는 방법도 있다! 간단한데도 불구하고, 생각하지 못했던 방식이다.





## 배운 점, 더 생각해 볼 것

---

* 튜플에 절댓값을 그냥 넣어주면 되는데?!

