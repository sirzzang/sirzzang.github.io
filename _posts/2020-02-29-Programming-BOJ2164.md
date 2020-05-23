---
title:  "[백준] BOJ2164 카드2"
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
  - 큐
  - 시뮬레이션
---







> [문제 출처](https://www.acmicpc.net/problem/2164)



## 문제

---



N장의 카드가 있다. 각각의 카드는 차례로 1부터 N까지의 번호가 붙어 있으며, 1번 카드가 제일 위에, N번 카드가 제일 아래인 상태로 순서대로 카드가 놓여 있다.

이제 다음과 같은 동작을 카드가 한 장 남을 때까지 반복하게 된다. 우선, 제일 위에 있는 카드를 바닥에 버린다. 그 다음, 제일 위에 있는 카드를 제일 아래에 있는 카드 밑으로 옮긴다.

예를 들어 N=4인 경우를 생각해 보자. 카드는 제일 위에서부터 1234 의 순서로 놓여있다. 1을 버리면 234가 남는다. 여기서 2를 제일 아래로 옮기면 342가 된다. 3을 버리면 42가 되고, 4를 밑으로 옮기면 24가 된다. 마지막으로 2를 버리고 나면, 남는 카드는 4가 된다.

N이 주어졌을 때, 제일 마지막에 남게 되는 카드를 구하는 프로그램을 작성하시오.



### 입력

첫째 줄에 정수 N(1≤N≤500,000)이 주어진다.



### 출력

첫째 줄에 남게 되는 카드의 번호를 출력한다.



## 풀이 방법

---

* 먼저 들어온 원소가 top이 되고, 카드를 버리는 동작과 카드의 위치를 바꾸는 동작 모두 top을 기준으로 하는 *First In First Out 구조*이므로 **큐**를 사용해 구현한다.
* 다음과 같은 단계에 따라 문제를 풀이한다.
* 카드를 queue에 push한다.
  * queue의 길이가 1이 될 때까지, "카드 버리기"와 "카드 위치 바꾸기"를 반복한다.
* pop(특정 위치) 방법을 사용하니 시간초과 문제([b0b4edd](https://github.com/sirzzang/Baekjoon_problems/blob/master/큐%2C%20덱/큐_카드2_BOJ2164.py))가 있었다. 따라서, index를 사용해 위의 논리를 구현한다.
* front_index : queue의 top 위치를 나타냄. queue_len : queue의 길이.
  * 카드 버리기 : front_index 한 칸씩 밀고, queue의 길이를 1만큼 줄인다.
  * 카드 위치 바꾸기 : top을 기존 queue의 맨 뒤에 push, front_index를 한 칸씩 뒤로 민다.
  * queue의 길이가 1이 되었을 때, 마지막에 있는 원소를 출력한다. 



## 풀이 코드

* class 사용하지 않은 구현 : 52368kb, 256ms

```python
import sys
n = int(sys.stdin.readline())

queue = [i for i in range(1, n+1)] # 입력된 숫자까지 push

front_index = 0 # queue의 top
queue_len = len(queue)

while queue_len != 1: # queue의 길이가 1이 될 때까지 아래의 연산 반복
    front_index += 1 # 버리기
    queue_len -= 1

    queue.append(queue[front_index]) # 바꾸기
    front_index += 1

print(queue.pop())
```

* class를 사용한 구현 : 52368kb 664ms.

```python
# class로 구현

class Queue:
    def __init__(self):
        self.itemList = []
        self.itemList_len = 0
        self.front_index = 0

    def push(self, item):
        self.itemList.append(item)
        self.itemList_len += 1

    def size(self):
        return self.itemList_len
    
    def pop(self):
        self.front_index += 1
        self.itemList_len -= 1
    
    def change(self): # 카드 순서 바꾸기
        self.itemList.append(self.itemList[self.front_index])
        self.front_index += 1
    
    def back(self):
        return self.itemList[-1]

import sys

n = int(sys.stdin.readline())

cards = Queue()

# 입력받은 숫자만큼 push
for i in range(1, n+1):
    cards.push(i)

# pop, change 연산 순서대로 반복
while cards.size() != 1:
    cards.pop()
    cards.change()

print(cards.back())

```



## 다른 풀이

> [코드 출처](https://www.acmicpc.net/source/13435078) : 큐를 사용하지 않고, 수학 논리/규칙으로 해결.

```python
n,s=int(input()),1
while s<n:
    s*=2
print(s if s==n else 2*n-s)
```

* 답만 적어서 규칙을 발견하면 됨.
  * n이 2의 제곱수일 때: 그대로 출력.
  * 아닐 때: n보다 큰 2의 제곱수 중 가장 작은 것을 s라고 하고, 2*n에서 s를 뺀다.



## 배운 점, 더 생각해 볼 것

* 자료구조 사용하지 않고, 규칙을 발견하는 방법!