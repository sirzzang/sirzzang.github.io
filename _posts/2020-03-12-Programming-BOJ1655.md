---
title:  "[백준] BOJ1655 가운데를 말해요"
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

> [문제 출처](https://www.acmicpc.net/problem/1655)



## 문제

---

---

수빈이는 동생에게 "가운데를 말해요" 게임을 가르쳐주고 있다. 수빈이가 정수를 하나씩 외칠때마다 동생은 지금까지 수빈이가 말한 수 중에서 중간값을 말해야 한다. 만약, 그동안 수빈이가 외친 수의 개수가 짝수개라면 중간에 있는 두 수 중에서 작은 수를 말해야 한다.

예를 들어 수빈이가 동생에게 1, 5, 2, 10, -99, 7, 5를 순서대로 외쳤다고 하면, 동생은 1, 1, 2, 2, 2, 2, 5를 차례대로 말해야 한다. 수빈이가 외치는 수가 주어졌을 때, 동생이 말해야 하는 수를 구하는 프로그램을 작성하시오.



### 입력

첫째 줄에는 수빈이가 외치는 정수의 개수 N이 주어진다. N은 1보다 크거나 같고, 100,000보다 작거나 같은 자연수이다. 그 다음 N줄에 걸쳐서 수빈이가 외치는 정수가 차례대로 주어진다. 정수는 -10,000보다 크거나 같고, 10,000보다 작거나 같다.

### 출력

한 줄에 하나씩 N줄에 걸쳐 수빈이의 동생이 말해야하는 수를 순서대로 출력한다.



## 풀이 방법

---

* 처음 문제 접근하며 여러 차례의 시간 초과([cf412d6](https://github.com/sirzzang/Baekjoon_problems/blob/master/25_우선순위큐/우선순위큐_가운데를말해요_BOJ1655_시간초과.py))를 겪었다. 여기서 얻은 통찰은 heappop을 사용해 접근해서는 안 된다는 것이다.
* 절댓값 힙에서 0을 기준으로 큰 수가 들어오는지, 작은 수가 들어오는지를 기준으로 판단했던 것처럼, 케이스 예시를 통해 기준을 **이전 단계에서의 중간값**으로 잡고 그보다 큰 수가 들어 오는 경우, 작은 수가 들어 오는 경우로 나누어 판단해 보기로 했다.

*예제 케이스 : 1, 5, 2, 10, -99, 7, 5*

| 작은 값이 들어오는 경우 | 중간값 | 큰 값이 들어오는 경우 |
| ----------------------: | :----: | :-------------------- |
|                         |        | **1**                 |
|                   **1** |   1    | 5                     |
|                       1 |   2    | **2**, 5              |
|                1, **2** |   2    | 5, 10                 |
|                  -99, 1 |   2    | **2**, 5, 10          |
|           -99, 1, **2** |   2    | 5, 7, 10              |
|               -99, 1, 2 |   5    | **5**, 5, 7, 10       |

* 그 결과 다음과 같은 규칙을 발견했다.
  * 처음 들어오는 값은 무조건 중간값이다.
  * 전체 입력된 수의 개수가 짝수일 때는 작은 값이 들어올 때의 배열에서 최댓값을, 홀수일 때는 큰 값이 들어올 때의 배열에서 최솟값이 중간값이다.

* 이를 바탕으로 다음과 같이 구현했다.
  * 처음 들어오는 값은 무조건 중간값 기준 오른쪽 배열에 넣고, 이 값을 기준 중간값으로 설정한다.
  * 총 입력 개수가 홀수일 때, 직전 중간값은 왼쪽 배열의 최댓값이다.
    * 직전 중간값보다 크거나 같은 값이 들어오면, 입력된 값을 오른쪽 배열에 넣는다.
    * 직전 중간값보다 작은 값이 들어오면, 왼쪽 배열의 최댓값을 오른쪽 배열로 이동시키고, 입력된 값을 왼쪽 배열에 넣는다.
    * 새로운 중간값은 오른쪽 배열의 최솟값이다.
  * 총 입력 개수가 짝수일 때, 직전 중간값은 오른쪽 배열의 최솟값이다.
    * 직전 중간값보다 큰 값이 들어오면, 오른쪽 배열의 최솟값을 왼쪽 배열로 이동시키고, 입력된 값을 오른쪽 배열에 넣는다.
    * 직전 중간값보다 작거나 같은 값이 들어오면, 입력된 값을 왼쪽 배열에 넣는다.
    * 새로운 중간값은 왼쪽 배열의 최댓값이다.
  * 왼쪽 배열은 최대 힙으로, 오른쪽 배열은 최소 힙으로 구현하면 중간값을 빠르게 찾을 수 있다.



## 풀이 코드

---

* 변수
  * len_heap : 전체 입력 값 개수.
  * min_heap : 중간값보다 작은 값이 입력될 경우의 힙. 최소 힙으로 구현하되, 양수와 음수가 모두 들어올 수 있으므로 튜플을 입력한다.
  * max_heap : 중간 값보다 큰 값이 입력될 경우의 힙.
  * ctr : 직전 중간값.
* min_heap에 삽입하거나, max_heap에서 max_heap으로 이동할 때 항상 튜플을 사용해야 함에 주의한다.



*40312KB, 272ms*

```python
import sys
import heapq

len_heap = 1
min_heap = []
max_heap = []
ctr = None

N = int(sys.stdin.readline())

for _ in range(N):
    
    val = int(sys.stdin.readline())

    if len_heap == 1 :
        heapq.heappush(max_heap, val)
        len_heap += 1
        ctr = val
        print(ctr)

    else:
        if len_heap % 2 == 1:        
            if val >= ctr : # max에 push해야 함.
                heapq.heappush(max_heap, val)
                len_heap += 1
            else: # min pop 후 max로 옮기고, 입력값 min에 push.
                heapq.heappush(max_heap, heapq.heappop(min_heap)[1])
                heapq.heappush(min_heap, (-val, val))
                len_heap += 1
            ctr = max_heap[0]
            print(ctr)        
        elif len_heap % 2 == 0: # 위와 반대로 진행.
            if val > ctr :
                heapq.heappush(min_heap, (-ctr, heapq.heappop(max_heap)))            
                heapq.heappush(max_heap, val)
                len_heap += 1
            else:
                heapq.heappush(min_heap, (-val, val))
                len_heap += 1
            ctr = min_heap[0][1]
            print(ctr)
```



## 다른 풀이

> [코드 출처](https://www.acmicpc.net/source/14751370)

*41448KB, 200ms*

```python
#!/usr/bin/env python3

from heapq import heappush, heappushpop
import sys


def main():
    numbers = map(int, sys.stdin.read().split())
    next(numbers)
    median = next(numbers)
    print(median)
    lte, gte = [], []
    for number in numbers:
        if number < median:
            if len(lte) < len(gte):
                heappush(lte, -number)
            else:
                heappush(gte, median)
                median = -heappushpop(lte, -number)
        elif number == median:
            if len(lte) < len(gte):
                heappush(lte, -number)
            else:
                heappush(gte, number)
        else:
            if len(lte) < len(gte):
                heappush(lte, -median)
                median = heappushpop(gte, number)
            else:
                heappush(gte, number)
        print(median)


if __name__ == '__main__':
    sys.exit(main())
```

* 입력값을 모두 받아 놓고, `next` 함수를 사용해 다음 입력 숫자를 받아왔다. for문을 돌며 입력을 받는 것에 비해 입력 시 시간이 줄어들 수 있다.
* 튜플로 입력하지 않고, 양수일 때와 음수일 때를 나누어 바로 숫자를 입력했다.



> [코드 출처](https://www.acmicpc.net/source/16249084)

*34560KB, 224ms*

```python
from sys import stdin
from heapq import *


input()
P, Q = [], []
for x in map(int, stdin):
    if not P or x <= -P[0]:
        heappush(P, -x)
        if len(P) > len(Q) + 1:
            heappush(Q, -heappop(P))
    else:
        heappush(Q, x)
        if len(P) < len(Q):
            heappush(P, -heappop(Q))

    print(-P[0])
```

* 직전 중간값과 비교하는 것을 변수로 만들지 않고, 바로 heap에 index로 접근했다.
* 역시 튜플로 입력하지 않고, 양수일 때와 음수일 때를 나누어 바로 숫자를 입력했다.





## 배운 점, 더 생각해 볼 것

* 문제를 낑낑대며 풀고 나니, 중간값 구하는 알고리즘이 있었다. [그 중 하나](https://o-tantk.github.io/posts/finding-median/)가 힙을 이용해 구하는 것이라 하는데, 알고리즘의 기본 아이디어가 내가 생각한 것과 비슷해서 기분이 좋았다.
* 다른 풀이에서 `next` 함수를 처음 보았다. [공부하면](https://dojang.io/mod/page/view.php?id=2408) [좋을 것](https://python.bakyeono.net/chapter-7-4.html) [같다](https://docs.python.org/ko/3/library/functions.html).
