---
title: "[Programmers] 멀리 뛰기"
excerpt: 우선순위 큐, 완전 탐색
header:
  teaser: /assets/images/blog-Programming.jpg
toc: true
categories:
  - Programming
tags:
  - Python
  - Programmers
  - heapq
---



# 문제

출처: [programmers.co.kr/learn/courses/30/lessons/12927](https://programmers.co.kr/learn/courses/30/lessons/12927)

<br>



# 풀이



## 구현 1

 야근 지수를 최소화하기 위해서는 **각 작업량 간 차이가 가장 적어져야** 한다. 

- 이를 위해 남은 시간 n만큼 works 배열을 순회하며 그 때 그 때 작업량의 최댓값을 1씩 낮춰줘야 한다. 
- 이 과정에서 정렬, 인덱싱 등을 사용하면 효율성 테스트를 통과하기가 매우 어렵다.

 우선순위 큐 자료구조를 사용하기 위해 파이썬 내장 모듈인 heapq 모듈에서 힙 자료구조를 사용하여 구현했다. 

- 다만, 최대 힙을 구현해야 하기 때문에 주어진 works 배열의 작업량을 음수로 만든다.
- 작업량을 줄일 때는 1씩 빼는 것이 아니라 1씩 더한다.

answer를 구할 때는 남은 작업량을 제곱해서 구하기 때문에, 음수를 제곱해서 더하나 양수를 제곱해서 더하나 상관이 없다. 

```python
import heapq

def solution(n, works):
    if n >= sum(works): # 야근을 하지 않아도 되는 경우
        return 0
    
    # 작업량을 최대힙으로 구현
    works_heap = [] 
    for work in works:
        heapq.heappush(works_heap, -work)
    
    # 작업량 최댓값 낮춰 주기
    while n:
        max_work = heapq.heappop(works_heap)
        max_work += 1
        n -= 1
        heapq.heappush(works_heap, max_work)
        
    # 최종 야근지수
    answer = 0
    for work in works_heap:
        answer += (work**2)
        
    return answer
```





## 구현 2

 통과가 되긴 하나, 예외 처리를 해야 하고 가독성도 좋지 않다.

```python
def solution(n, works):
    answer = 0
    if n >= sum(works):
        return answer
    else:
        works.sort(reverse = True) # 한 번만 정렬하자 처음에.
        i = 0 # 인덱스
        try:
            while n > 0:
                if works[i] == works[i+1]:
                    i += 1
                elif (works[i] - works[i+1]) * (i+1) <= n:
                    n -= (works[i] - works[i+1]) * (i+1)
                    for j in range(i+1):
                        works[j] -= (works[i] - works[i+1])
                    i += 1
                else:
                    for j in range(i+1):
                        works[j] -= 1
                        n -= 1
                        if n == 0:
                            break
        except IndexError:
            q, r = n // len(works), n % len(works)
            if q > 0 :
                for i in range(len(works)):
                    works[i] -= q
                n -= q * len(works)

            while n > 0:
                for i in range(len(works)):
                    works[i] -= 1
                    n -= 1
                    if n == 0:
                        break

        for work in works:
            answer += work * work

        return answer
```







<br>

# 다른 사람의 풀이

 프로그래머스 사이트에 올라온 다른 풀이의 접근법들도 비슷하게 최대 작업량을 1씩 감소시켜 주었다. 다만, 문제가 개편되어 효율성 테스트를 통과하지 못하는 경우가 있다고 한다.

 
