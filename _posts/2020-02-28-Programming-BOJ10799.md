---
title:  "[백준] BOJ10799 쇠막대기"
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
  - 스택
---







> [문제 출처](https://www.acmicpc.net/problem/10799)



## 문제

---



여러 개의 쇠막대기를 레이저로 절단하려고 한다. 효율적인 작업을 위해서 쇠막대기를 아래에서 위로 겹쳐 놓고, 레이저를 위에서 수직으로 발사하여 쇠막대기들을 자른다. 쇠막대기와 레이저의 배치는 다음 조건을 만족한다.

- 쇠막대기는 자신보다 긴 쇠막대기 위에만 놓일 수 있다. - 쇠막대기를 다른 쇠막대기 위에 놓는 경우 완전히 포함되도록 놓되, 끝점은 겹치지 않도록 놓는다.
- 각 쇠막대기를 자르는 레이저는 적어도 하나 존재한다.
- 레이저는 어떤 쇠막대기의 양 끝점과도 겹치지 않는다. 

쇠막대기와 레이저의 배치를 나타내는 괄호 표현이 주어졌을 때, 잘려진 쇠막대기 조각의 총 개수를 구하는 프로그램을 작성하시오.



### 입력

한 줄에 쇠막대기와 레이저의 배치를 나타내는 괄호 표현이 공백없이 주어진다. 괄호 문자의 개수는 최대 100,000이다. 



### 출력

잘려진 조각의 총 개수를 나타내는 정수를 한 줄에 출력한다.





## 풀이 방법

---

* 문제를 처음 풀 때, 엄청난 시행착오([760e2be](https://github.com/sirzzang/Baekjoon_problems/blob/master/%EC%8A%A4%ED%83%9D/%EC%8A%A4%ED%83%9D_%EC%87%A0%EB%A7%89%EB%8C%80%EA%B8%B0_BOJ10799_%EC%8B%9C%ED%96%89%EC%B0%A9%EC%98%A4.py))를 겪었다.

  * "()" 모양을 무조건 레이저라고 생각하여 L로 바꾼 것이 문제가 되었다. 판단해야 할 경우가 왼쪽 괄호, 오른쪽 괄호에 더해 하나 더 생겼기 때문이다.
  * **중첩된 쇠막대**를 판단하는 데 있어 핵심인 **오른쪽 괄호**를 놓치고, 이를 레이저의 개수로 판별하고자 했다.

  

  ![쇠막대기 문제 풀이]({{site.url}}/assets/images/blog-BOJ10799.jpg)

  *싹 다 갈아 엎은(유산슬?) 풀이*

  

  

* 다시 접근한 풀이 방법은 다음과 같다.
  * 첫째, 오른쪽 괄호가 레이저인지, 쇠막대의 끝인지 판단한다. 바로 앞에 나오는 괄호의 형태를 보면 알 수 있다.
    * () : 레이저
    * )) : 쇠막대
  * 둘째, 잘린 조각의 개수를 센다. 쇠막대를 n개의 레이저로 자르면, n+1개의 조각이 나온다.
    * 레이저를 기준으로 왼쪽 괄호의 개수를 세면, 레이저 개수만큼 잘려진 쇠막대 조각을 구할 수 있다. 오른쪽 조각 개수는 그 다음 레이저의 왼쪽에 있는 괄호 개수로 셀 수 있으므로, 왼쪽을 기준으로 본다.
    * 남은 하나의 조각은 쇠막대의 끝을 나타내는 오른쪽 괄호의 수와 같다.



## 풀이 코드

* 왼쪽 괄호를 stack에 push한다.
* 레이저의 끝을 나타내는 오른쪽 괄호이면, stack의 top을 pop하고, stack의 길이 만큼 조각의 개수를 누적한다. 쇠막대의 끝을 나타내는 오른쪽 괄호이면, stack의 top을 pop하고, 누적된 조각의 개수에 1을 더한다.

```python
import sys
sticks = sys.stdin.readline().strip('\n')

stack = []
pieces = 0

for i in range(len(sticks)):
    if sticks[i] == "(":
        stack.append(sticks[i])
    else:
        if sticks[i-1] == "(": # 레이저("()")인 경우
            stack.pop() # 레이저 짝 제거
            pieces += len(stack)
        else: # 쇠막대의 끝인 경우
            stack.pop() # 쇠막대 짝 제거
            pieces += 1

print(pieces)
```

* 이 외에, stack을 사용하지 않은 구현, class로 stack을 구현하여 풀어보았다.([760e2be](https://github.com/sirzzang/Baekjoon_problems/blob/master/%EC%8A%A4%ED%83%9D/%EC%8A%A4%ED%83%9D_%EC%87%A0%EB%A7%89%EB%8C%80%EA%B8%B0_BOJ10799.py))



## 다른 풀이

> [코드 출처](https://www.acmicpc.net/source/13964893)

```python
import sys

def solution(arrangement):
    arrangement = arrangement.replace('()', '0');
    temp = 0    # "("의 개수 = 현재 진행중인 막대기 개수
    answer = 0

    for i in arrangement:
        if i == "(": temp += 1
        elif i == "0": answer += temp
        else:
            temp -= 1
            answer += 1
    return answer

x = sys.stdin.readline().rstrip()
print(solution(x))
```

* 내가 처음 시행착오를 겪으며 구현하고 싶었던 방식이다.
* 시간과 메모리 면에서 효율성이 좋아 1위에 오른 풀이 방법이다.



## 배운 점, 더 생각해 볼 것

* 경우를 자꾸 나누는 풀이는 비효율적이다.