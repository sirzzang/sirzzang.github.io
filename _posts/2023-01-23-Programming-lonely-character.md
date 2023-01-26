---
title: "[Programmers] 외톨이 문자"
excerpt: "문자열, groupby, counter"
header:
  teaser: /assets/images/blog-Programming.jpg
toc: true
categories:
  - Programming
tags:
  - Python
  - Programmers
  - 문자열
---



# 문제

출처: https://school.programmers.co.kr/learn/courses/15008/lessons/121683



<br>



# 풀이

```python
def solution(input_string):
        
    char_dict = {}
    prev = ''
    for i, v in enumerate(input_string):
        
        # 뭉쳐서 등장한 경우는 체크하지 않음
        if v == prev:
            continue
            
        # 문자별 첫 등장 위치 기록
        if v not in char_dict:
            char_dict[v] = []
        char_dict[v].append(i)        
        prev = v

    answer = "".join(sorted([k for k in char_dict if len(char_dict[k]) >= 2]))
    
    return answer if answer else "N"
```



<br>

# 다른 사람의 풀이



출처: https://school.programmers.co.kr/learn/courses/15008/lessons/121683/solution_groups?language=python3

```python
def solution(input_string):
    answer = set()
    alphabets = set([input_string[0]])
    prev = input_string[0]
    for s in input_string[1:]:
        if s != prev and s in alphabets:
            answer.add(s)
        alphabets.add(s)
        prev = s

    if answer:
        answer = ''.join(sorted(list(answer)))
    else:
        answer = 'N'
    return answer
```

