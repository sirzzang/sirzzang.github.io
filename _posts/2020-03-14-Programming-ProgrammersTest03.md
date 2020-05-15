---
title:  "[Programmers] 하노이의 탑"
excerpt:
header:
  teaser: /assets/images/blog-Programming.jpg

categories:
  - Programming
tags:
  - Python
  - Programming
  - Programmers

---

> [문제 출처](https://programmers.co.kr/learn/courses/30/lessons/12946)



## 문제



- 하노이 탑(Tower of Hanoi)은 퍼즐의 일종입니다. 세 개의 기둥과 이 기동에 꽂을 수 있는 크기가 다양한 원판들이 있고, 퍼즐을 시작하기 전에는 한 기둥에 원판들이 작은 것이 위에 있도록 순서대로 쌓여 있습니다. 게임의 목적은 다음 두 가지 조건을 만족시키면서, 한 기둥에 꽂힌 원판들을 그 순서 그대로 다른 기둥으로 옮겨서 다시 쌓는 것입니다.

  1. 한 번에 하나의 원판만 옮길 수 있습니다.
  2. 큰 원판이 작은 원판 위에 있어서는 안됩니다.

  하노이 탑의 세 개의 기둥을 왼쪽 부터 1번, 2번, 3번이라고 하겠습니다. 1번에는 n개의 원판이 있고 이 n개의 원판을 3번 원판으로 최소 횟수로 옮기려고 합니다.

  1번 기둥에 있는 원판의 개수 n이 매개변수로 주어질 때, n개의 원판을 3번 원판으로 최소로 옮기는 방법을 return하는 solution를 완성해주세요.

  ##### 제한사항

  - n은 15이하의 자연수 입니다.



## 풀이 방법

* 이전에 공부한 하노이의 탑 풀이 방법과 크게 다르지 않다.
* 다만, 시작 기둥에서 목적지 기둥으로 향하는 이동 경로를 리스트로 만들어 정답으로 출력할 리스트에 저장하면 된다.



## 풀이 코드

```python
answer = []

def Hanoi(n, start, end, mid):
    global answer
    if n == 1:
        answer.append([start, end])
        return
    else:
        Hanoi(n-1, start, mid, end)
        answer.append([start, end])
        Hanoi(n-1, mid, end, start)
    
def solution(n):
    Hanoi(n, 1, 3, 2) # Hanoi 함수를 호출한다.
    return answer
```



## 다른 풀이

[풀이 출처](https://programmers.co.kr/learn/courses/30/lessons/12946/solution_groups?language=python3)



 함수 안에 중첩 함수를 사용하여 호출했다. 또한, 이를 위해 `yield`를 사용하여 내부 함수를 제너레이터로 만들었다.

```python
def hanoi(n):

    def _hanoi(m, s, b, d):
        if m == 1:
            yield [s, d]
        else:
            yield from _hanoi(m-1, s, d, b)
            yield [s, d]
            yield from _hanoi(m-1, b, s, d)

    ans = list(_hanoi(n, 1, 2, 3))
    return ans  # 2차원 배열을 반환해 주어야 합니다.


# 아래는 테스트로 출력해 보기 위한 코드입니다.
print(hanoi(2))
```



* _hanoi 함수는 제너레이터가 되어, s부터 d까지의 이동 경로를 반환한다.
* 보조 기둥을 사용해야 할 때는, `yield from` 키워드를 사용하여 뒤의 함수에서 생성되는 객체를 전달했다.
* 전달된 이동 경로들을 ans라는 list에 받았다.





## 배운 점

[참고](https://dojang.io/mod/page/view.php?id=2412)

[참고 2](https://itholic.github.io/python-yield-from/)



* `yield` : 함수 안에서 사용할 때, 함수를 제너레이터로 만든다. 즉, 함수를 통해 반복 가능한 객체를 호출할 수 있도록 한다.
* `yield from` : 다른 제너레이터에게 작업을 `yield` 작업을 위임한다.



