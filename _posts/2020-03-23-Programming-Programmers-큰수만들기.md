---
title:  "[Programmers] 큰 수 만들기"
excerpt: "1일 1문제풀이 4일차"
header:
  teaser: /assets/images/blog-Programming.jpg
toc: true
categories:

  - Programming
    tags:
  - Python
  - Programming
  - Programmers
  - 그리디
  - 스택
---



> [문제 출처](https://programmers.co.kr/learn/courses/30/lessons/42583)



# 1. 문제



어떤 숫자에서 k개의 수를 제거했을 때 얻을 수 있는 가장 큰 숫자를 구하려 합니다.

예를 들어, 숫자 1924에서 수 두 개를 제거하면 [19, 12, 14, 92, 94, 24] 를 만들 수 있습니다. 이 중 가장 큰 숫자는 94 입니다.

문자열 형식으로 숫자 number와 제거할 수의 개수 k가 solution 함수의 매개변수로 주어집니다. number에서 k 개의 수를 제거했을 때 만들 수 있는 수 중 가장 큰 숫자를 문자열 형태로 return 하도록 solution 함수를 완성하세요.



**제한사항**

- number는 1자리 이상, 1,000,000자리 이하인 숫자입니다.
- k는 1 이상 `number의 자릿수` 미만인 자연수입니다.



**입출력 예**

| number     | k    | return |
| ---------- | ---- | ------ |
| 1924       | 2    | 94     |
| 1231234    | 3    | 3234   |
| 4177252841 | 4    | 775841 |



---



# 2. 나의 풀이 

## 풀이 방법



 일단 숫자를 선택한다. 선택한 뒤, 그 다음의 숫자가 기존에 선택되어 있던 숫자보다 크다면, 기존의 숫자를 삭제한다. 먼저 선택한 숫자일수록 더 자릿수가 높은 숫자라고 간주한다. 따라서, 새로운 숫자를 기존의 숫자와 비교할 때는 **더 자릿수가 낮은 숫자부터** 비교해 나간다. (이 풀이 과정 때문에 '그리디' 알고리즘으로 분류되는 듯하다.)

 이 과정을 구현하기 위해 후입선출 자료구조인 **스택**을 활용했다. 숫자를 선택하는 과정은 다음과 같다.

* top에 가까울수록, 자릿수가 낮은 수이다.

* 스택의 top이 다음에 들어올 수보다 *작다면* **pop**한다. 
  * pop한다는 것은 기존의 숫자를 삭제한다는 의미이다. 따라서 삭제할 수 있는 최대 숫자(k)를 1씩 감소시켜야 한다.
  * pop한 후 top이 다음에 들어올 수보다 크거나 같거나, 스택이 비게 된다면, append한다.  
* pop 조건에 부합하는 것이 *아니라면* 스택에 **append**한다.



 숫자를 선택하는 과정이 문제 없이 구현되었다면, 문제 조건은 만족한 것이라고 본다. 그러나, 똑같은 숫자가 연달아 들어오는 등 예외 케이스가 있을 수 있다. 이 경우 위의 과정만 구현한다면, 삭제되는 숫자가 없게 된다.

 따라서 위의 선택 과정을 구현한 상태에서, 선택할 수 있는 *최대 개수의 숫자* 를 선택했다면 **선택 과정을 종료**하는 조건을 추가한다.



> *참고*
>
>  입출력 예를 통해 문제를 이해할 때 착오가 있었다. 문제 설명에 '주어진 숫자 순서는 그대로 보장되어야 한다'는 설명이 추가되면 더 이해하기 쉬울 것 같다.

> *시행 착오*
>
>    파이썬을 배운 지 얼마 지나지 않았을 때, logic을 이용해서 풀려고 했다가 포기했던 문제이다. 그 때 거의 7시간을 고민했던 것 같은데(...) 테스트 케이스에서 2개만 맞아서 너무 허무했던 기억이 난다. 어쨌든 이번에 다시 풀었으니, 성장한 걸로..?! 

   



## 풀이 코드

```python
def solution(number, k):
    
    stack = [number[0]] # 스택 초기값 : 첫 번째 수 선택한 것으로 간주.
    
    for n in number[1:]:        
        while stack and int(n)>int(stack[-1]) and k>0: # pop 조건
            stack.pop()
            k -= 1            
        stack.append(n) # pop하지 않으면 append.
    
        if len(stack) == len(number) - k: # 선택 과정 종료 조건
            break
    
    answer = ''.join(stack)
    
    return answer
```



  

---



# 3. 다른 풀이

[풀이 출처](https://programmers.co.kr/learn/courses/30/lessons/42883/solution_groups?language=python3)

 

```python
def solution(number, k):
    stack = [number[0]]
    for num in number[1:]:
        while len(stack) > 0 and stack[-1] < num and k > 0:
            k -= 1
            stack.pop()
        stack.append(num)
    if k != 0:
        stack = stack[:-k]
    return ''.join(stack)
```

 내 풀이와 비슷하다. 제거 횟수를 사용하지 않았을 때 남은 횟수만큼 스택 뒷부분을 잘라준다는 점이 다르다.





---

  

# 4. 배운 점, 더 생각해볼 점

* 다양한 테스트 케이스를 생각해낼 수 있는 것도 능력인 것 같다.




