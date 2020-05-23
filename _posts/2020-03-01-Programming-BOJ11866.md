---
title:  "[백준] BOJ11866 요세푸스 문제 0"
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
---



> [문제 출처](https://www.acmicpc.net/problem/11866)



## 문제

---

요세푸스 문제는 다음과 같다.

1번부터 N번까지 N명의 사람이 원을 이루면서 앉아있고, 양의 정수 K(≤ N)가 주어진다. 이제 순서대로 K번째 사람을 제거한다. 한 사람이 제거되면 남은 사람들로 이루어진 원을 따라 이 과정을 계속해 나간다. 이 과정은 N명의 사람이 모두 제거될 때까지 계속된다. 원에서 사람들이 제거되는 순서를 (N, K)-요세푸스 순열이라고 한다. 예를 들어 (7, 3)-요세푸스 순열은 <3, 6, 2, 7, 5, 1, 4>이다.

N과 K가 주어지면 (N, K)-요세푸스 순열을 구하는 프로그램을 작성하시오.



### 입력

첫째 줄에 N과 K가 빈 칸을 사이에 두고 순서대로 주어진다. (1 ≤ K ≤ N ≤ 1,000)



### 출력

예제와 같이 요세푸스 순열을 출력한다.





## 풀이 방법

---

* 처음에는 문제를 제대로 이해하지 못했다([b0b4edd](https://github.com/sirzzang/Baekjoon_problems/commit/53b2496ac902e9ea35993b4de349e1590b0276b7).
  * 제거하는 사람의 index를 저장하고, 그 앞에 사람들까지를 queue에 push해서 풀면 될 거라고 생각했다.
  * 그 동안 queue 문제를 풀 때 시간 제한 문제가 있었기 때문에, 이전과 같이 front_index, queue_length를 이용해 구현하고자 했다.
  * 마지막에 남은 사람들이 k보다 작을 때 index error가 난다는 것을 발견했고, 예제 입력, 출력만 보고 남은 사람들을 순서대로 작성했다.

* 그러나 [Josephus Problem](https://www.youtube.com/watch?v=uCsD3ZGzMgE) 동영상을 보고 문제를 완전히 잘못 이해했다는 것을 깨달았다. 남은 사람들끼리도  k에 따라 순서대로 제거해야 하는 것이었다. modula 연산을 적용하면 될 것 같다.

* 손으로 그림을 그려보며 규칙을 찾기로 했다.

  

  *(N=10, K=4인 경우)*

| 사람 LIST(현재)                | LEN(현재) | idx(현재) | idx(다음) |
| :----------------------------- | :-------: | :-------: | :-------: |
| **1** 2 3 4 5 6 7 8 9 10       |    10     |     3     |     7     |
| 1 2 3    **5** 6 7 8 9 10      |     9     |     7     |     1     |
| 1 2 3    5 6 7    **9** 10     |     8     |     1     |     4     |
| 1    **3**     5 6 7   9 10    |     7     |     4     |     1     |
| 1    3     5 6      **9** 10   |     6     |     1     |     4     |
| 1           **5** 6      9  10 |     5     |     4     |     3     |
| **1**           5 6      9     |     4     |     3     |     0     |
| **1**           5 6            |     3     |     0     |     1     |
| **5** 6                        |     2     |     1     |     0     |

- 사람들의 list, list의 길이, 제거해야 하는 사람의 순서(idx) 간에 다음과 같은 규칙이 있었다.
  $$
  idx(n+1) = (idx(n) + k-1)mod(len(n))
  $$

  - list에 있는 첫 사람의 입장에서, **제거해야 할 사람은 자신의 순서에 (k-1)을 더한 곳에 앉아 있는 사람**이다. 
    - n번째 사람을 제거한다.
    - n+1번째 사람의 입장에서 자신이 0번이 된다. 기존에 맨 앞에 있던 사람부터 (n-1)번째 사람까지를 자신의 뒤로 줄세운다. 이 때, n+1번째 사람의 입장에서 list의 길이를 len(n)이라 한다.
    - 제거해야 할 사람은, (k-1)만큼의 간격을 더한 자리에 앉아 있는 사람이다. **간격이 전체 사람의 길이보다 길 수 있으므로, modula 연산을 해준다.**
  - 해당 list에서 modula 연산은, idx > len일 때, 처음으로 돌아가서 앞에서부터 idx 세주는 역할을 한다. 
  - 전체적으로 봤을 때, k번째 사람이 순환하며 제거되는 구조가 구현된다.





## 풀이 코드

---



* 출력 형식에 주의하자 :  29440kb, 60ms.

```python
import sys

n, k = map(int, sys.stdin.readline().split())
people = list(range(1, n+1))

idx = k-1
gap = k-1 # pop한 후에 더할 간격

print("<", end="")
while people: # 인원 수 남아 있을 때
    if n > 1: # 출력 형식을 위한 n
        print(people.pop(idx), end= ", ")
        idx = (idx + gap) % len(people)
        n -= 1 # pop했으니까 인원수 감소
    else:
        print(people.pop(), end=">")
```





## 다른 풀이

> [코드 출처](https://claude-u.tistory.com/197)

```python
N, K = map(int, input().split())
stack = [i for i in range(1, N + 1)]
result = []
temp = K - 1

for i in range(N):
    if len(stack) > temp:
        result.append(stack.pop(temp))
        temp += K - 1
    elif len(stack) <= temp:
        temp = temp % len(stack)
        result.append(stack.pop(temp))
        temp += K - 1

print("<", end='')
for i in result:
    if i == result[-1]:
        print(i, end = '')
    else:
        print("%s, " %(i), end='')
print(">")
```



## 배운 점, 더 생각해 볼 것

* 문제가 왜 큐로 분류되어 있는지 궁금했는데, 순환 큐를 사용하는 문제인 것 같다.
  * [순환 큐](https://mailmail.tistory.com/41): **_'(index+1) % 배열의 사이즈'\_**를 이용하여 **OutOfBoundsException**이 일어나지 않고 인덱스 0으로 순환되는 구조를 가진다.
  * 처음 시행착오를 겪고, 문제를 이해한 뒤, 어떻게든 선형 큐를 이용해 index가 len을 넘어가는 문제를 해결하려 했는데, 순환 큐와 같은 방식을 이용하면 될 것 같다.
* 처음에 문제를 이해하지 못한 것도 있지만, 아직도 논리적 사고력이 많이 부족함을 느낀다. 전산학에서 요세퍼스 문제 굉장히 유명하다고 하니, [공부하자](https://en.wikipedia.org/wiki/Josephus_problem).

