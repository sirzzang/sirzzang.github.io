---
title: "[Problem Solving] 개미수열"
excerpt: 문자열, 스택, 구현 
header:
  teaser: /assets/images/blog-Programming.jpg
toc: true
categories:
  - Programming
tags:
  - Python
  - Programming
  - 문자열
  - 스택

---





> 문제 출처 : 신윤수 강사님(ys@betweak.com)

# 1. 문제



아래 수열은 ‘개미수열’이라고 불린다. 사용자로부터 n값을 입력받아서 n번째 위치에 있는 수열을 출력하시오.

```
1
11
12
1121
122111
112213
12221131
1123123111
```



---



# 2. 나의 풀이 



## 풀이 방법

 

 수열의 앞에서부터 뒤로 가면서 같은 숫자가 몇 개 있는지 세야 한다. stack을 사용해 구현했다.

* 직전 개미수열의 맨 앞에서부터 뒤로 가면서, 숫자를 pop한다.
* 숫자를 저장할 stack을 만들고, 해당 숫자가 **처음 나온 경우** stack에 저장한다. 뒤에 나올 숫자가 직전에 나왔는지 판단하기 위함이다.
* 다음의 두 가지 경우로 나누어 새로운 수열을 만든다.
  * pop한 숫자가 stack의 top과 **다른 경우**다. 직전에 *나오지 **않은*** 숫자라는 뜻이다. 새로운 수열을 저장할 배열에 해당 숫자와, 1을 저장한다. 여기서 1은 해당 숫자가 *등장한 횟수* 를 의미한다. 동시에 스택에 해당 숫자를 넣는다.
  * pop한 숫자가 stack의 top과 **같은 경우**다. pop한 숫자가 *직전에 나온 수와 **같다***는 뜻이다. 새로운 수열을 저장할 배열의 마지막 수에 1을 더해준다. 여기서 마지막 수는 *직전의 숫자가 지금까지 등장한 횟수*를 의미한다.
* 기존의 수열을 새로운 수열로 교체한다.





## 풀이 코드

* 사용한 변수

  * `flag` : pop한 숫자.
  * `stack` :`flag`를 저장할 배열.
  * `temp` : 새롭게 만들 수열.

* 예외 처리
  
  * n이 1일 때는 개미수열이 1이므로 바로 1을 출력한다.
  * `try ~ except ...`를 사용해 처음에 비교할 숫자를 stack에 넣었다.
  
  > 처음에는 `if len(stack) == 0`을 통해 구현하려 했다. 그러나 이 경우, 바로 밑에서 stack의 top과 비교하는 조건에 부합하며 첫 번째 숫자의 등장 횟수가 2가 되어 버린다. 따라서 애초에 stack의 top과 비교할 수 없어서 `IndexError`가 발생할 때 flag를 stack에 넣도록 했다.

```python
n = int(input())

ant = [1] # 초기 개미수열

if n == 1:
    print(1)
else:
    n -= 1
    while n:
        stack, temp = [], []
        while ant:
            flag = ant.pop(0)
            try:
                if flag == stack[-1]:
                    temp[-1] += 1
                else:
                    temp.extend([flag, 1])
                    stack.append(flag)
            except: # 수열의 맨 처음
                stack.append(flag)
                temp.extend([flag, 1])
        n -= 1
        ant = temp

    for a in ant:
        print(a, end="")
```





---

# 3. 다른 풀이



```python
n = int(input("정수를 입력하시오: "))

str1 = "1"

for i in range(0, n):
    prev = ""
    tmp = ""
    cnt = 0
    # notice: string도 for 가능.
    for s in str1:
        if prev != "" and prev != s:
            tmp += prev + str(cnt)
            cnt = 1
        else:
            cnt += 1
        prev = s
        
    tmp += prev + str(cnt)
    str1 = tmp
    print(str1)
```



 1등으로 제출하신 분의 풀이다. 1, 2등 분이 모두 문자열을 사용했다. 특히 이 분의 풀이가 가장 깔끔했다. 실력자시다...



---

# 4. 배운 점, 더 생각해 볼 점



*  꽤 빨리 풀었다고 생각했는데 3등이었다. 더 열심히 하자.
*  수열을 문자열로 보지 못했다. 사고의 전환이 필요하다. 비교하는 논리 자체는 비슷한데, 어떠한 자료형을 사용할 것인지에 따라 코드의 길이가 달라진다. 조건 분기도 더 깔끔하게 구현할 필요가 있다.

