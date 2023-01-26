---
title: "[BOJ] 그룹 단어 체커"
excerpt: 
header:
  teaser: /assets/images/blog-Programming.jpg
toc: true
categories:
  - Programming
tags:
  - Python
  - BOJ
  - 문자열
---



# 문제

출처: [www.acmicpc.net/problem/1316](https://www.acmicpc.net/problem/1316)



<br>



# 풀이



1. group_checker 함수
   - 각 단어에서 문자가 나타나는 첫 인덱스와 끝 인덱스를 구한다. 
   - 첫 인덱스와 끝 인덱스 사이에 문자가 2개 이상 존재하면 `False`를 반환하고, 그렇지 않으면 `True`를 반환한다.
2. 최종 출력
   - 입력으로 들어오는 각 문자열을 group_checker 함수로 검사한 뒤, True의 개수를 센다.

```python
def group_checker(text):
    for char in set(text):
        start, end = text.index(char), len(text)-text[::-1].index(char)-1 # 시작과 끝 위치
        check = text[start:end + 1]
        if len(set(check)) > 1:
            return False
    return True

n = int(input())
answer = 0
for _ in range(n):
    answer += group_checker(input()) # 입력으로 들어온 문자열 검사
print(answer)
```



<br>

# 다른 사람의 풀이



출처: [www.acmicpc.net/source/12127213](https://www.acmicpc.net/source/12127213)

- 문자열의 각 문자에 대해 먼저 나오는 순서대로 정렬한다.
- 정렬한 결과가 원래 문자열과 같으면 개수를 센다.

```python
result = 0
for i in range(int(input)):
	word = input()
    if list(word) == sorted(word, key=word.find):
    	result += 1
print(result)
```

