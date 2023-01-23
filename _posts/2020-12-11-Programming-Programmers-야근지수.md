---
title: "[Programmers] 멀리 뛰기"
excerpt: DP
header:
  teaser: /assets/images/blog-Programming.jpg
toc: true
categories:
  - Programming
tags:
  - Python
  - Programmers
  - DP
---



# 문제

출처: [programmers.co.kr/learn/courses/30/lessons/12914](https://programmers.co.kr/learn/courses/30/lessons/12914)

<br>



# 풀이

1. DP
   - 한 번에 뛸 수 있는 칸이 1칸 혹은 2칸이다.
   - n번째 칸에 갈 수 있는 방법은 (n-1)번째 칸에서 1칸을 뛰거나, (n-2)번째 칸에서 2칸을 뛰면 된다.
2. mod 연산의 성질
   - (a+b)%m = {(a%m)+(b%m)}%m이므로 처음 값을 할당할 때부터 나머지를 할당했다.

```python
def solution(n):
    if n == 1:
        return 1
    elif n == 2:
        return 2
    else:
        a, b, answer = 1, 2, 0
        for i in range(3, n+1):
            answer = (a%1234567 +b%1234567)%1234567 # mod 연산
            a = b
            b = answer
    return answer
```





<br>

# 다른 사람의 풀이

출처: [programmers.co.kr/learn/courses/30/lessons/12914/solution_groups?language=python3](https://programmers.co.kr/learn/courses/30/lessons/12914/solution_groups?language=python3)

[
](https://programmers.co.kr/learn/courses/30/lessons/12914/solution_groups?language=python3)

```python
def jumpCase(num):
    a, b = 1, 2
    for i in range(2,num):
        a, b = b, a+b
    return b

#아래는 테스트로 출력해 보기 위한 코드입니다.
print(jumpCase(4))
```

