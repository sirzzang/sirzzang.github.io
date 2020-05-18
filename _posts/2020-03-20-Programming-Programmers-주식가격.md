---
title:  "[Programmers] 주식가격"
excerpt: "1일 1문제풀이 1일차"
header:
  teaser: /assets/images/blog-Programming.jpg
toc: true
categories:
  - Programming
tags:
  - Python
  - Programming
  - Programmers
  - 스택, 큐
  - 그리디
---

> [문제 출처](https://programmers.co.kr/learn/courses/30/lessons/42584?language=python3)



# 1. 문제

초 단위로 기록된 주식가격이 담긴 배열 prices가 매개변수로 주어질 때, 가격이 떨어지지 않은 기간은 몇 초인지를 return 하도록 solution 함수를 완성하세요.



**제한사항**

- prices의 각 가격은 1 이상 10,000 이하인 자연수입니다.
- prices의 길이는 2 이상 100,000 이하입니다.



**입출력 예**

| prices          | return          |
| --------------- | --------------- |
| [1, 2, 3, 2, 3] | [4, 3, 1, 1, 0] |



**입출력 예 설명**

- 1초 시점의 ₩1은 끝까지 가격이 떨어지지 않았습니다.

- 2초 시점의 ₩2은 끝까지 가격이 떨어지지 않았습니다.

- 3초 시점의 ₩3은 1초뒤에 가격이 떨어집니다. 따라서 1초간 가격이 떨어지지 않은 것으로 봅니다.

- 4초 시점의 ₩2은 1초간 가격이 떨어지지 않았습니다.

- 5초 시점의 ₩3은 0초간 가격이 떨어지지 않았습니다.

  

---



# 2. 나의 풀이 

## 풀이 방법

 문제 분류는 **스택, 큐**였는데, 내가 푼 방법은 *그리디* 에 가깝다. 자료 구조가 아니라, logic을 사용해서 풀었다.

 논리는 간단하다. 각 시점마다의 가격이 주어지므로, **자신보다 뒤에 등장하는 가격 중 낮은 가격이 하나라도 있다면 그 때까지의 시간을 계산**해 주었다.

* 초기값이 0이고, 길이가 주어진 주식가격의 배열과 같은 시간 배열을 만든다.
  * 낮은 가격이 등장하는 시간을 기록하는 배열이다.
  * 기록할 시간의 초기값은 모두 0이다. 주가가 기록되기 전에는 자기 자신보다 낮은 가격이 등장할 수가 없기 때문이다.
* 낮은 가격이 등장할 때의 인덱스를 시간 배열에 기록한다.
  * 시간 배열의 해당 위치 값이 0이라면, 자기 자신보다 낮은 가격이 등장하지 않았다는 말이다. 따라서 종료 시간까지의 초를 계산하면 된다.
  * 낮은 가격이 등장한 경우에는, 그 때까지의 초를 계산하면 된다.

  



## 풀이 코드

* `for문` 안에 `for문`을 사용하여 자신보다 뒤에 나오는 가격들을 검사하도록 했다. 특히, 하나라도 낮은 가격이 나오면 내부 `for문`을 빠져나오도록 한다. 그래야 처음으로 등장한 낮은 가격의 인덱스를 기록한다.
* 시간을 계산하기 위해 `enumerate` 함수를 사용했다. 

```python
def solution(prices):
    prices = prices
    answer = [0]*len(prices) # 초기 시간 배열
    
    for i in range(len(prices)):
        price = prices[i]
        for j in range(i+1, len(prices)): # 자신보다 뒤에 나오는 가격 검사
            if prices[j] < price:
                answer[i] = j
                break
    
    for idx, ans in enumerate(answer):
        if ans == 0:
            answer[idx] = len(answer)-1-idx # 종료까지 남은 시간
        else:
            answer[idx] = ans-idx # 낮은 가격이 등장할 때까지의 시간
        
    return answer
```

 

*참고*

 `for문`을 여러 번 순회하고, 심지어 `enumerate()`를 사용하여 효율성 면에서 시간이 오바될 줄 알았는데, 통과되었다(읭?!).

  

---



# 3. 다른 풀이

[풀이 출처](https://programmers.co.kr/learn/courses/30/lessons/42584/solution_groups?language=python3)

  



**첫째**

```python
def solution(prices):
    answer = [0] * len(prices)
    for i in range(len(prices)):
        for j in range(i+1, len(prices)):
            if prices[i] <= prices[j]:
                answer[i] += 1
            else:
                answer[i] += 1
                break
    return answer
```

 가장 많은 좋아요를 받은 풀이이며, 유사한 풀이도 가장 많다. 내 풀이와 다른 점은 **떨어지지 않은 시간을 계산한다**는 점이다.

 애초에 이중 `for문`을 활용해 뒤에 나오는 가격이 떨어졌는지, 떨어지지 않았는지 계산한다. 떨어지지 않았다면(즉, 낮은 가격이 나오지 않았다면) 시간을 1초씩 더해주고, 낮은 가격이 나왔다면 내부 `for문` 순회를 종료한다.

  



**둘째**

 스택, 큐 등 자료구조를 활용한 풀이들이다.



```python
from collections import deque
def solution(prices):
    answer = []
    prices = deque(prices)
    while prices:
        c = prices.popleft()

        count = 0
        for i in prices:
            if c > i:
                count += 1
                break
            count += 1

        answer.append(count)

    return answer
```

 이중 `for문`에서 바깥 `for문`을 deque의 `popleft` 메서드를 활용해 구현했다. 또한, 떨어지지 않은 시간을 계산한 뒤, 그것을 list에 append했다.

  

---



# 4. 배운 점, 더 생각해볼 점

* `enumerate`는 반복 자료형 내 원소를 하나씩 다 보아야 하기 때문에, 시간 복잡도가 O(n)이다. 웬만하면 다른 방법을 사용하자.

* 뭔가 다른 사람의 풀이를 보고 나면, 내 풀이는 항상 마지막에서 몇 단계 꼬아 가는 느낌이 든다. 떨어지지 않은 시간을 계산하면 될 것을, 굳이 전체 시간에서 빼고 어쩌고... 로직보다는 내 사고의 문제 같다. 갈 길이 멀구나.