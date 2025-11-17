---
title:  "[Algorithm] 후위표기법 연산"
excerpt: 
categories:
  - CS
toc: false
header:
  teaser: /assets/images/blog-Dev.jpg
tags:
  - 연산
  - 후위표기
  - 전위표기
  - 중위표기
---



# 개요

 계산을 위한 수식을 작성하는 방법에 다음의 세 가지가 있다.

* 전위표기(prefix): 피연산자 앞에 연산자를 사용하는 표기  *ex) a+b*
* 중위표기(infix): 피연산자 사이에 연산자를 사용해서 표기  *ex) +ab*
* 후위표기(postfix): 피연산자 뒤에 연산자를 사용해서 표기 *ex) ab+*



 사람은 사칙연산 우선순위를 알고 있고, 연산자를 피연산자 가운데에 표기하는 게 익숙하지만, 컴퓨터는 괄호와 연산자, 피연산자가 뒤섞인 식을 보고 어떤 것을 먼저 계산해야 할지 알기 어렵기 때문에 중위표기법보다는 전위표기 혹은 후위표기법을 더 많이 사용해 계산한다. [이 글](https://softwareengineering.stackexchange.com/questions/294898/why-use-postfix-prefix-expression-instead-of-infix)에 더 자세한 이유가 나와 있으니 참고.



 컴퓨터의 계산 방식을 구현하기 위해서는,

- 중위표기 식을 전위표기 혹은 후위표기식으로 변환하고,
- 표현된 전위표기 혹은 후위표기식을 계산 순서에 맞게 계산해야 한다.



 그 중에서도 중위표기 방식으로 작성된 식을 어떻게 후위표기 방식으로 바꾸고 계산할 수 있는지 정리해 보고자 한다.



<br>

# 후위표기법 변환



 괄호로 구분된 연산식이 연산자, 피연산자, 괄호로 분리되어 리스트에 들어 있을 때를 가정한다. 



 후위표기법 변환을 위해 연산자 우선 순위를 정의하고, 연산자 우선 순위에 맞게 괄호를 치는 것이 중요하다. 스택 자료 구조를 사용한다. 알고리즘은 다음과 같다.

- 피연산자: 그대로 후위표기식에 출력
- 괄호
  - 여는 괄호: stack에 push
  - 닫는 괄호: stack에 여는 괄호가 나올 때까지 stack에서 pop
- 연산자
  - stack이 빈 경우: stack에 push
  - stack이 비어있지 않은 경우
    - stack의 top보다 우선순위가 더 높으면 push
    - stack의 top보다 우선순위가 작거나 같으면 스택의 top을 pop한 뒤 현재 연산자를 push
    - 여는 괄호의 우선순위는 항상 어떠한 연산자보다 낮음
- 만약 수식을 모두 탐색했는데 스택에 연산자가 남아 있으면 모두 pop

<br>

 그림으로 표현하면 다음과 같다.

![postfix-image]({{site.url}}/assets/images/postfix-gif.gif){: .align-center}



 이를 구현하면 아래와 같다. 다른 방식으로 구현할 수도 있겠지만, 아래의 방식으로 구현하면 후위표기 방식으로 연산식을 작성했을 때의 각 항이 리스트에 구분되어 들어 간다.

```python
from typing import List

def infix_to_postfix(arr: List[str]) -> List[str]:
    stack = []
    postfix = []
    ranks = {'(': 0, '+': 1, '-': 1, '*': 2, '/':2}
    for elem in arr:
        if elem.isdigit():
            postfix.append(elem)
        elif elem == '(':
            stack.append(elem)
        elif elem == ')':
            while stack and stack[-1] != '(':
                postfix.append(stack.pop())
            stack.pop()
        else:
            while stack and ranks[elem] <= ranks[stack[-1]]:
                postfix.append(stack.pop())
                stack.append(elem)
            stack.append(elem)
    while stack:
        postfix.append(stack.pop())
    return postfix
```

<br>

# 후위표기 연산식 계산



 후위표기 방식으로 표현된 연산식의 각 연산자와 피연산자가 구분되어 리스트에 들어 있는 상황을 가정한다.

 이와 같이 표현된 후위표기 방식으로 표현된 식을 계산할 때에도 역시 스택을 활용한다. 알고리즘은 다음과 같다.

* 피연산자를 stack에 push
* 연산자가 나온 경우 stack의 마지막 두 원소를 pop한 뒤, 연산 방식에 맞게 계산한 결과를 stack에 pop

* stack에 마지막에 남는 값이 답

```python
from typing import List

def calculate_postfix(postfix_arr: List[str]) -> int:
    stack = []
    for elem in postfix_arr:
        if elem.isdigit():
            stack.append(int(elem))
        else:
            b = stack.pop()
            a = stack.pop()
            if elem == '+':
                stack.append(a+b)
            elif elem == '-':
                stack.append(a-b)
            elif elem == '*':
                stack.append(a*b)
            else:
                stack.append(a/b)
    return stack[-1]

```

<br>

# 기타

* 짝이 맞는지 차례로 판단하는 작업이 필요한 경우, 스택 자료구조를 사용하는 것이 좋아 보인다.
* 이건 굉장히 단순한 구현 방식이고, 실제 문제에는 여러 가지 방식으로 응용될 수 있으니, 이 구현 방식을 응용해서 잘 풀어보자.
  * string 형태로 이어진 문자열이 연산식으로 주어지는 경우(괄호가 없을 수도 있다)
  * 연산자 우선 순위가 일반적인 연산자 우선 순위와 다른 경우
  * 전위표기법으로 바꾸는 경우