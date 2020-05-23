---
title : [백준] BOJ1966 프린터 큐
excerpt :
header:
	teaser : /assets/images/blog-Programming.jpg
categores :
	- Programming
tags:
	- Python
	- Programming
	- BOJ
	- 완전탐색
	- 자료구조
	- 큐
	- 시뮬레이션

---





## 문제

------

여러분도 알다시피 여러분의 프린터 기기는 여러분이 인쇄하고자 하는 문서를 인쇄 명령을 받은 ‘순서대로’, 즉 먼저 요청된 것을 먼저 인쇄한다. 여러 개의 문서가 쌓인다면 Queue 자료구조에 쌓여서 FIFO - First In First Out - 에 따라 인쇄가 되게 된다. 하지만 상근이는 새로운 프린터기 내부 소프트웨어를 개발하였는데, 이 프린터기는 다음과 같은 조건에 따라 인쇄를 하게 된다.

1. 현재 Queue의 가장 앞에 있는 문서의 ‘중요도’를 확인한다.
2. 나머지 문서들 중 현재 문서보다 중요도가 높은 문서가 하나라도 있다면, 이 문서를 인쇄하지 않고 Queue의 가장 뒤에 재배치 한다. 그렇지 않다면 바로 인쇄를 한다.

예를 들어 Queue에 4개의 문서(A B C D)가 있고, 중요도가 2 1 4 3 라면 C를 인쇄하고, 다음으로 D를 인쇄하고 A, B를 인쇄하게 된다.

여러분이 할 일은, 현재 Queue에 있는 문서의 수와 중요도가 주어졌을 때, 어떤 한 문서가 몇 번째로 인쇄되는지 알아내는 것이다. 예를 들어 위의 예에서 C문서는 1번째로, A문서는 3번째로 인쇄되게 된다.

### 입력

첫 줄에 test case의 수가 주어진다. 각 test case에 대해서 문서의 수 N(100이하)와 몇 번째로 인쇄되었는지 궁금한 문서가 현재 Queue의 어떤 위치에 있는지를 알려주는 M(0이상 N미만)이 주어진다. 다음줄에 N개 문서의 중요도가 주어지는데, 중요도는 1 이상 9 이하이다. 중요도가 같은 문서가 여러 개 있을 수도 있다. 위의 예는 N=4, M=0(A문서가 궁금하다면), 중요도는 2 1 4 3이 된다.

### 출력

각 test case에 대해 문서가 몇 번째로 인쇄되는지 출력한다.

## 풀이 방법

------

- 문제 자체보다 예제 입출력을 보고 이해하는 게 더 문제 이해에 도움이 된다. n, m 다음에 주어지는 입력에서 m번째 위치에 있는 종이가 몇 번째로 출력될지 구하는 문제이다.
- 가장 앞에 인쇄될 수 있는 종이가 있다면 인쇄하는 **FIFO 구조**이므로 큐를 사용해 구현한다.

| queue                   | front | back | pop_idx | flag_idx | cnt  |
| ----------------------- | ----- | ---- | ------- | -------- | ---- |
| **1** 2 3 4             | 0     | 3    | None    | 2        | 0    |
| 1 **2** 3 4 1           | 1     | 4    |         | 2        |      |
| 1 2 **3** 4 1 2         | 2     | 5    |         | 2        |      |
| 1 2 3 **4** 1 2 3       | 3     | 6    | 3       | 6        | 1    |
| (1 2 3 4) **1** 2 3     | 4     | 6    |         | 6        |      |
| (1 2 3 4) 1 **2** 3 1   | 5     | 7    |         | 6        |      |
| (1 2 3 4) 1 2 **3** 1 2 | 6     | 8    | 6       | 6        | 2    |

- 위의 표에서와 같이 다음과 같은 논리를 구현하면 된다.

  > 위의 표에서 m번째 위치에 있는 종이의 index가 바뀌는 과정은 4행에서 5행으로 갈 때에,
  >
  > 인쇄되는 과정은 5행에서 6행으로 갈 때에,
  >
  > 반복이 종료되는 조건은 8행에서 확인할 수 있다.

  - 인쇄 : queue의 top을 pop한다.
  - 인쇄되지 않는 종이 : queue의 back에 push한다.
  - 입력으로 주어진 m번째 종이가 queue의 top에 있고, pop할 수 있다면, 그 때의 인쇄 순서를 출력한다.

## 풀이 코드

------

- 입력으로 주어진 m번째 종이를 flag라 하고, flag가 뒤로 이동할 때 그 위치를 기억해야 한다.
- 변수
  - front : queue의 top 위치.
  - back : queue의 마지막 원소 위치.
  - pop_idx : 인쇄되는 종이의 위치. m(=flag_idx)이 0으로 주어질 경우를 대비해 `None`으로 초기값 설정.
  - flag_idx : flag의 위치.
  - cnt : 현재까지 인쇄 횟수.
- pop_idx와 flag_idx가 같아지는 순간 출력한다.
- 29284kb, 72ms : 시간 측면에서 크게 효율적이지는 않다.

```python
import sys

t = int(sys.stdin.readline())

for _ in range(t):

    n, m = map(int, sys.stdin.readline().split())
    papers = [int(i) for i in sys.stdin.readline().split()]

    front = 0
    back = n-1
    pop_idx = None
    flag_idx = m
    cnt = 0

    if n == 1:
        print(1)
    else:
        while pop_idx != flag_idx:
            if any(paper > papers[front] for paper in papers[front+1:]): 
                papers.append(papers[front]) # 하나라도 큰 게 있다면, 뒤로 밀림.
                front += 1
                back += 1
                if front - 1 == flag_idx: # 찾아야 할 flag가 top에 있었고, 뒤로 밀렸다면,
                    flag_idx = back # flag의 index도 변함.
            else: # 인쇄한다면,
                pop_idx = front # top을 pop
                front += 1 # front의 위치만 +1
                cnt += 1
        print(cnt)
```

## 다른 풀이

> [코드 출처](https://www.acmicpc.net/source/14651728)

```python
import sys

T = int(sys.stdin.readline())
for t in range(T):
    M,N = list(map(int,sys.stdin.readline().split()))
    info = list(map(int,sys.stdin.readline().split()))

    if info.count(info[N]) == 1:
        print(sorted(info, reverse = True).index(info[N])+1)
    else:
        temp = sorted(info, reverse = True)
        
        target = info[N]
        info[N] = 0

        prior = temp.index(target)

        answer = prior
        for i in range(prior):
            index = info.index(temp[i])
            info.pop(index)
            info = info[index:] + info[:index]
        for j in range(M-prior):
            if (info.count(target) != 0) and (info.index(target) < info.index(0)):
                answer += 1
                info.remove(target)
            else:
                break
        answer += 1
        print(answer)
```

- pop(index), remove(특정 원소)를 하면 시간복잡도가 늘어나서 시간이 더 걸릴 줄 알았는데 오히려 56ms로 가장 빠른 시간이다.

## 배운 점, 더 생각해 볼 것

- 다른 풀이 생각해보고 싶은 것

  - 처음 문제를 보자 마자 생각했던 풀이는 enumerate와 dict를 사용해 정렬하는 것이었다. 문제를 다 푼 후 구현해 봤는데([6e7cae4](https://github.com/sirzzang/Baekjoon_problems/commit/15bb70f4a8f3f21af08fa4dcfcbe55257ecaf4fe)), "1 1 9 1 1 1"과 같이 똑같은 중요성을 가지는 종이가 들어올 때를 분류하지 못했다.
  - 정렬 알고리즘을 활용해서 풀 수는 없을까?
  - 덱을 사용해서 구현한다면?

- 큐의 또 다른 종류로, "우선순위 큐"라는 것이 있음을 알게 되었다.

   

  우선순위 큐

  에 대해 공부한 후, 다시 문제를 풀어보자.

  - [우선순위 큐에 대한 간단한 설명](http://www.daleseo.com/python-priority-queue/)
  - [우선순위 큐 class로 구현하기](https://sang-gamja.tistory.com/34)
  - [우선순위 큐의 단점을 보완한 순환 큐](https://elrion018.tistory.com/34)