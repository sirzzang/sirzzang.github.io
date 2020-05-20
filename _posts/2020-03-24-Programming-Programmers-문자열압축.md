---
title:  "[Programmers] 문자열 압축"
excerpt: "1일 1문제풀이 5일차"
header:
  teaser: /assets/images/blog-Programming.jpg
toc: true
categories:
  - Programming
tags:
  - Python
  - Programming
  - Programmers
  - 완전탐색
---



> [문제 출처](https://programmers.co.kr/learn/courses/30/lessons/60057)



# 1. 문제



 데이터 처리 전문가가 되고 싶은 **어피치**는 문자열을 압축하는 방법에 대해 공부를 하고 있습니다. 최근에 대량의 데이터 처리를 위한 간단한 비손실 압축 방법에 대해 공부를 하고 있는데, 문자열에서 같은 값이 연속해서 나타나는 것을 그 문자의 개수와 반복되는 값으로 표현하여 더 짧은 문자열로 줄여서 표현하는 알고리즘을 공부하고 있습니다.

 간단한 예로 aabbaccc의 경우 2a2ba3c(문자가 반복되지 않아 한번만 나타난 경우 1은 생략함)와 같이 표현할 수 있는데, 이러한 방식은 반복되는 문자가 적은 경우 압축률이 낮다는 단점이 있습니다. 예를 들면, abcabcdede와 같은 문자열은 전혀 압축되지 않습니다. 어피치는 이러한 단점을 해결하기 위해 문자열을 1개 이상의 단위로 잘라서 압축하여 더 짧은 문자열로 표현할 수 있는지 방법을 찾아보려고 합니다.

예를 들어, ababcdcdababcdcd의 경우 문자를 1개 단위로 자르면 전혀 압축되지 않지만, 2개 단위로 잘라서 압축한다면 2ab2cd2ab2cd로 표현할 수 있습니다. 다른 방법으로 8개 단위로 잘라서 압축한다면 2ababcdcd로 표현할 수 있으며, 이때가 가장 짧게 압축하여 표현할 수 있는 방법입니다.

다른 예로, abcabcdede와 같은 경우, 문자를 2개 단위로 잘라서 압축하면 abcabc2de가 되지만, 3개 단위로 자른다면 2abcdede가 되어 3개 단위가 가장 짧은 압축 방법이 됩니다. 이때 3개 단위로 자르고 마지막에 남는 문자열은 그대로 붙여주면 됩니다.

압축할 문자열 s가 매개변수로 주어질 때, 위에 설명한 방법으로 1개 이상 단위로 문자열을 잘라 압축하여 표현한 문자열 중 가장 짧은 것의 길이를 return 하도록 solution 함수를 완성해주세요.



**제한사항**

- s의 길이는 1 이상 1,000 이하입니다.
- s는 알파벳 소문자로만 이루어져 있습니다.



**입출력 예**

| s                            | result |
| :--------------------------- | :----- |
| `"aabbaccc"`                 | 7      |
| `"ababcdcdababcdcd"`         | 9      |
| `"abcabcdede"`               | 8      |
| `"abcabcabcabcdededededede"` | 14     |
| `"xababcdcdababcdcd"`        | 17     |

### 입출력 예에 대한 설명



**입출력 예 #1**

문자열을 1개 단위로 잘라 압축했을 때 가장 짧습니다.



**입출력 예 #2**

문자열을 8개 단위로 잘라 압축했을 때 가장 짧습니다.



**입출력 예 #3**

문자열을 3개 단위로 잘라 압축했을 때 가장 짧습니다.



**입출력 예 #4**

문자열을 2개 단위로 자르면 abcabcabcabc6de 가 됩니다.
문자열을 3개 단위로 자르면 4abcdededededede 가 됩니다.
문자열을 4개 단위로 자르면 abcabcabcabc3dede 가 됩니다.
문자열을 6개 단위로 자를 경우 2abcabc2dedede가 되며, 이때의 길이가 14로 가장 짧습니다.



**입출력 예 #5**

문자열은 제일 앞부터 정해진 길이만큼 잘라야 합니다.
따라서 주어진 문자열을 x / ababcdcd  /  ababcdcd 로 자르는 것은 불가능 합니다.
이 경우 어떻게 문자열을 잘라도 압축되지 않으므로 가장 짧은 길이는 17이 됩니다. 



---







# 2. 나의 풀이 

## 풀이 방법



 문자열을 앞에서부터 1개, 2개, 3개, ... 씩 잘라 나간다. 이 때 잘라야 할 문자열의 개수가 주어진 문자열의 개수보다 절반을 넘어가면 자르는 게 의미가 없다. 잘라봐야 반복될 수가 없기 때문이다. 따라서 주어진 문자열의 길이의 절반까지 문자열을 자른다.

 1개, 2개, 3개, ...씩 자른 문자열을 chunk라고 하자. 이 chunk를 리스트로 만들고, chunk 안에 연속되어 나오는 문자열이 몇 개씩 있는지 센다. 연속되는 문자열 없이 1개만 있다면 그 문자열의 개수를 더하고, 연속되는 문자열이 있다면 그 문자열의 개수의 자릿수와 그 문자열의 자릿수를 더한다.

> *시행 착오*
>
>    제발 문제 좀 잘 읽자. 처음에 문제 잘 안 읽어서 앞에서부터 잘라야 한다는 걸 모르고 뻘짓하고 있었다.

   



## 풀이 코드

* 리스트 안에서 반복되는 문자열의 개수를 구하기 위해 itertools의 `groupby` 함수를 사용했다.
* 다른 사람의 풀이를 보고 나서 보니 좋지 못한 풀이임을 깨닫는다(...).

```python
from itertools import groupby

def solution(s):
    answer == len(s) # 초기 답안 설정
    if len(set(s)) == 1: # 문자열이 1개의 문자로만 구성되어 있을 경우
        if len(s) == 1: # 문자열의 길이가 1이라면 답은 1.
            answer = 1
           else: # 1개의 문자가 여러 개라면
            answer += 1+len(str(answer))
    else:
        for n in range(1, len(s)//2+1):
            chunks = [s[i:i+n] for i in range(0, len(s), n)] # n개씩 자른 chunk 생성
            cnt_chunks = [(k, sum(1 for _ in g)) for k, g in groupby(chunks)] 
            # chunk안에 문자열 몇 개씩 있는지 개수 센 리스트
            cnt = 0 # 최종 문자열 글자 수
            if all(c[1] == 1 for c in cnt_chunks):
                continue # 다 1개씩 있다면 검사할 필요 없음.
            else:
                for c in cnt_chunks:
                    if c[1] == 1: # 중복 아니면
                        cnt += len(c[0]) # 문자열 개수 더하기.
                    else:
                        cnt += (len(c[0]) + len(str(c[1])))
             if cnt< answer: # 작다면 답 교체
                answer = cnt
    return answer
```









---





# 3. 다른 풀이



**완전 탐색**을 구현해야 한다.



[풀이 출처](https://velog.io/@devjuun_s/문자열-압축-프로그래머스python2020-Kakao-공채)

```python
def solution(s):
    length = []
    result = ""
    
    if len(s) == 1:
        return 1
    
    for cut in range(1, len(s) // 2 + 1):
        count = 1
        tempStr = s[:cut] 
        for i in range(cut, len(s), cut):
            if s[i:i+cut] == tempStr:
                count += 1
            else:
                if count == 1:
                    count = ""
                result += str(count) + tempStr
                tempStr = s[i:i+cut]
                count = 1

        if count == 1:
            count = ""
        result += str(count) + tempStr
        length.append(len(result))
        result = ""
    
    return min(length)
```

* result : 압축될 문자열. length : 압축될 문자열(result)들의 길이를 기록할 리스트.
* cut : 자를 문자열 개수. tempStr : 검사할 윈도우 문자열. count : 문자열이 등장한 횟수.
* 내부 `for문` 안 로직
  * 다음 문자열들 안에서 윈도우 문자열과 같은 게 나오면 횟수를 더해준다.
  * 그 다음 문자열이 윈도우 문자열과 같지 않다면, 그 때까지 나온 횟수와 윈도우 문자열을 압축 문자열에 적어 준다. 이 때, 윈도우 문자열이 1번만 나왔다면, 1은 기록하지 않도록 조건을 추가한다.
  * 이후 윈도우 문자열을 다음 비교 문자열로 바꿔 준다. count도 초기화한다.
* 내부 `for문 밖` 예외 처리 : `len(s)//2 + 1` 범위까지만 검사했으므로, 마지막 부분의 문자열은 검사하지 않았다. 따라서 똑같은 로직을 내부 `for문 밖`에서 실행해 주어야 마지막 부분의 문자열까지 검사할 수 있게 된다.



[풀이 출처](https://programmers.co.kr/learn/courses/30/lessons/60057/solution_groups?language=python3)

```python
def compress(text, tok_len):
    words = [text[i:i+tok_len] for i in range(0, len(text), tok_len)]
    res = []
    cur_word = words[0]
    cur_cnt = 1
    for a, b in zip(words, words[1:] + ['']):
        if a == b:
            cur_cnt += 1
        else:
            res.append([cur_word, cur_cnt])
            cur_word = b
            cur_cnt = 1
    return sum(len(word) + (len(str(cnt)) if cnt > 1 else 0) for word, cnt in res)

def solution(text):
    return min(compress(text, tok_len) for tok_len in list(range(1, int(len(text)/2) + 1)) + [len(text)])
```

 가장 많은 호평을 받은 풀이이다. 깔끔하다.

* compress 함수와 solution 함수를 따로 구현했다.
* 위의 풀이와 윈도우 문자열 비교하는 논리 자체는 비슷하나, `zip` 함수를 사용해 구현했다. 윈도우 문자열을 변경하는 과정이 간편해 졌다.
* 단어와 등장 개수를 기록하는 것은 내 풀이와 비슷하다(기본 아이디어만...). 이후 compress 함수에서 `for문`과 `if문`을 조합하여 한 줄로 답을 뽑아 냈다.
* solution 함수에서 문자열의 절반 길이까지만 윈도우 문자열을 구하도록 했다.







---

  

# 4. 배운 점, 더 생각해볼 점

* `groupby`를 써서 쉽게 풀라고 낸 문제가 아니다. 나는 처음에 chunk로 문자열을 자를 생각만 해서 중복되는 문자열이 몇 개인지 구하는 데에만 급급했다. 그러나, 앞에서부터 1개, 2개, ...씩 윈도우를 설정하여 뒤로 보내면서 윈도우가 중복될 때마다 개수를 업데이트해주면 되는 문제였다. 왜 바보같이 접근했는지 모르겠다. 반성할 것.


