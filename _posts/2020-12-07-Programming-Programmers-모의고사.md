---
title: "[Programmers] 모의고사"
excerpt: 구현
header:
  teaser: /assets/images/blog-Programming.jpg
toc: true
categories:
  - Programming
tags:
  - Python
  - Programmers
---



# 문제

출처: [programmers.co.kr/learn/courses/30/lessons/42840](https://programmers.co.kr/learn/courses/30/lessons/42840)



<br>



# 풀이



## 구현 1

```python
def solution(answers):
    res = [0, 0, 0, 0]
    first = [1, 2, 3, 4, 5]
    second = [2, 1, 2, 3, 2, 4, 2, 5]
    third = [3, 3, 1, 1, 2, 2, 4, 4, 5, 5]        
    for i in range(len(answers)):
        if first[i%5] == answers[i]:
            res[1] += 1
        if second[i%8] == answers[i]:
            res[2] += 1
        if third[i%10] == answers[i]:
            res[3] += 1
    answer = []
    for i, v in enumerate(res):
        if v == max(res):
            answer.append(i)
    return answer
```



## 구현 2

 구현 1의 풀이를 기능별로 나눠 보았으나, 시간 효율성이 떨어졌다.

1. is_correct 함수
   - 수포자가 찍는 배열과 정답 배열을 인자로 받아, 맞춘 정답의 수를 반환한다.
   - 배열 길이와 나머지를 이용하여 정답 배열을 순환하며, 수포자가 찍은 것이 정답인지 체크했다. 
2. solution 함수
   - 각 수포자의 정답에 대해 점수를 계산하는 scores 배열을 만든다.
   - enumerate 함수를 활용해 scores 배열의 최댓값을 갖는 값들의 인덱스를 찾는다.

```python
def is_correct(pred, true):
    answer = 0
    for i in range(len(true)):
        answer += (pred[i % len(pred)] == true[i]) # boolean -> 숫자
    return answer    

def solution(answers):
    first = [1, 2, 3, 4, 5]
    second = [2, 1, 2, 3, 2, 4, 2, 5]
    third = [3, 3, 1, 1, 2, 2, 4, 4, 5, 5]
    scores = [is_correct(first, answers), is_correct(second, answers), is_correct(third, answers)]
    
    return [i+1 for i, v in enumerate(scores) if v == max(scores)] # 인덱스 0번부터 시작함.
```



<br>

# 다른 사람의 풀이

출처: [programmers.co.kr/learn/courses/30/lessons/42840/solution_groups?language=python3](https://programmers.co.kr/learn/courses/30/lessons/42840/solution_groups?language=python3)

```python
def solution(answers):
    pattern1 = [1,2,3,4,5]
    pattern2 = [2,1,2,3,2,4,2,5]
    pattern3 = [3,3,1,1,2,2,4,4,5,5]
    score = [0, 0, 0]
    result = []

    for idx, answer in enumerate(answers):
        if answer == pattern1[idx%len(pattern1)]:
            score[0] += 1
        if answer == pattern2[idx%len(pattern2)]:
            score[1] += 1
        if answer == pattern3[idx%len(pattern3)]:
            score[2] += 1

    for idx, s in enumerate(score):
        if s == max(score):
            result.append(idx+1)

    return result
```

