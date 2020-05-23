---
title:  "[백준] BOJ1021 회전하는 큐"
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

> [문제 출처](https://www.acmicpc.net/problem/1966)



## 문제

---

지민이는 N개의 원소를 포함하고 있는 양방향 순환 큐를 가지고 있다. 지민이는 이 큐에서 몇 개의 원소를 뽑아내려고 한다.

지민이는 이 큐에서 다음과 같은 3가지 연산을 수행할 수 있다.

1. 첫 번째 원소를 뽑아낸다. 이 연산을 수행하면, 원래 큐의 원소가 a1, ..., ak이었던 것이 a2, ..., ak와 같이 된다.
2. 왼쪽으로 한 칸 이동시킨다. 이 연산을 수행하면, a1, ..., ak가 a2, ..., ak, a1이 된다.
3. 오른쪽으로 한 칸 이동시킨다. 이 연산을 수행하면, a1, ..., ak가 ak, a1, ..., ak-1이 된다.

큐에 처음에 포함되어 있던 수 N이 주어진다. 그리고 지민이가 뽑아내려고 하는 원소의 위치가 주어진다. (이 위치는 가장 처음 큐에서의 위치이다.) 이때, 그 원소를 주어진 순서대로 뽑아내는데 드는 2번, 3번 연산의 최솟값을 출력하는 프로그램을 작성하시오.



### 입력

첫째 줄에 큐의 크기 N과 뽑아내려고 하는 수의 개수 M이 주어진다. N은 50보다 작거나 같은 자연수이고, M은 N보다 작거나 같은 자연수이다. 둘째 줄에는 지민이가 뽑아내려고 하는 수의 위치가 순서대로 주어진다. 위치는 1보다 크거나 같고, N보다 작거나 같은 자연수이다.



### 출력

첫째 줄에 문제의 정답을 출력한다.





## 풀이 방법

---

* 숫자가 queue의 top에 있을 때 pop하는 **FIFO 구조**이므로 큐를 사용해 구현한다.
* 뽑을 숫자가 앞쪽에 가까우면 왼쪽 이동, 뒤쪽에 가까우면 오른쪽 이동을 진행한다. 숫자가 top에 오면 pop한다.





## 풀이 코드

---

* 함수 정의 : rshift(오른쪽 이동), lshift(왼쪽 이동).
* 변수
  * extract : 뽑아 내야 할 숫자 list.
  * flag : 뽑아내야 할 숫자.
  * queue : 초기에 입력 받는 숫자 모음.
  * cnt : lshift와 rshift를 수행한 횟수.
* 왼쪽 이동의 경우, idx가 0이 되는 순간 pop하면 되지만, 오른쪽 이동의 경우, 순환하는 경우를 대비해 idx를 다른 방식으로 초기화한다.
* 29284kb, 60ms : 제일 짧은 시간이 52ms인 것을 고려하면 크게 효율적이지는 않다.

```python
def rshift(lst):
    for idx, value in enumerate(lst[:]):
        lst[(idx+1) % len(lst)] = value
    return lst

def lshift(lst):
    for idx, value in enumerate(lst[:]):
        lst[(idx-1) % len(lst)] = value
    return lst

def pop(lst):
    lst.pop(0)
    return lst

import sys

n, m = map(int, sys.stdin.readline().split())
extract = list(map(int, sys.stdin.readline().split()))
queue = list(range(1, n+1))
cnt = 0

for flag in extract:

    idx = queue.index(flag)
    
    if idx == 0:
        pop(queue)
    
    else:
        if idx <= len(queue) - idx:
            while idx != 0:
                lshift(queue)
                cnt += 1
                idx -= 1
            pop(queue)
        else:
            while idx != 0:
                rshift(queue)
                cnt += 1
                idx = (idx+1) % len(queue)
            pop(queue)

print(cnt)
```



## 다른 풀이

> [코드 출처](https://home-body.tistory.com/422)

```python
import sys

def lshift():
    q.append(q.pop(0))
    
def rshift():
    q.insert(0, q.pop())

def pop():
    global N
    q.pop(0)
    N -= 1
    
N, M = map(int, input().split())
q = list(range(1, N+1))
pop_list = list(map(int, input().split()))
cnt = 0

for n in pop_list:
    i = q.index(n)
    l = i
    r = N-i
    
    if i == 0:
        pop()
    elif l >= r:
        for _ in range(r):
            rshift()
        pop()
        cnt += r
    elif l < r:
        for _ in range(l):
            lshift()
        pop()
        cnt += l
        
print(cnt)
```



* pop(0)의 연산을 사용해도 되는지 처음 풀 때 고민했다. 그런데 내 방법으로 풀고 이 코드를 보고 다시 생각해보니, 어차피 index 위치를 한 칸씩 미는 것이나, pop(0)을 하나, 시간복잡도는 차이가 없을 것이라 보인다.
* 왼쪽에 가까울 때는 어차피 0으로 갈 때까지, 오른쪽에 가까울 때는 마지막 위치를 지나 맨 앞에 갈 때까지 이동을 진행해야 하므로, **굳이 내 방법처럼 배열을 바꾸지 말고** cnt에 l과 r을 더하는 게 더 좋아 보인다.



> [코드 출처](https://www.acmicpc.net/source/18232022)

```python
n, m = map(int, input().split())
dq = [i for i in range(1, n+1)]

ans = 0

for find in map(int, input().split()):
    ix = dq.index(find)
    ans += min(len(dq[ix:]), len(dq[:ix])) # 주목1
    dq = dq[ix+1:] + dq[:ix] # 주목2

print(ans)
```



* python으로 푼 문제 중 가장 시간이 빠른 풀이다.
* 왼쪽에 가까운지, 오른쪽에 가까운지를 파악하고, 그 위치만 더해주는 것은 위의 방법과 비슷하다. 그런데 그것을 최솟값을 찾는 한 줄의 코드로 구현한 것이 매우 효율적이라고 판단된다.
* pop한 후 순환한 것을 구현한 것 역시 생각하지 못했던 방법이었다.





## 배운 점, 더 생각해 볼 것

* 며칠 전 우선순위 큐의 단점을 보완하기 위해 순환 큐를 사용한다는 글을 보았다. 

  > 순환 큐는 `(rear + 1) % arraysize == front`라면 배열이 포화상태인 걸로 파악하고 데이터 삽입이 이루어지지 않는다.  *_[출처](https://lktprogrammer.tistory.com/59)*

  * `(rear + 1) % arraysize == front`에서 힌트를 얻어 오른쪽 이동, 왼쪽 이동을 구현할 때, 각 원소의 index를 각각 +1, -1 해주고 list의 길이로 modula연산한 값으로 바꾸면 된다는 것을 깨달았다.
  * 그런데 이를 실제로 구현하려고 해도, list의 원소가 이동하지 않고 모두 첫 번째 원소로 바뀌어 버린다든가, 마지막 원소로 바뀌어 버리는 문제를 발견했다. [이 글](https://stackoverflow.com/questions/29498418/python-shifting-elements-in-a-list-to-the-right-and-shifting-the-element-at-the/29498853)에서 힌트를 얻어 `enumerate(list)`가 아니라, `enumerate(list[:])`를 해야 각 원소에 대해 index가 이동한다는 것을 알게 되었다.



