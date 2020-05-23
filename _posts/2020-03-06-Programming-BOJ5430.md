---
title:  "[백준] BOJ5430 AC"
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
  - 덱
---

> [문제 출처](https://www.acmicpc.net/problem/1966)



## 문제

---

선영이는 주말에 할 일이 없어서 새로운 언어 AC를 만들었다. AC는 정수 배열에 연산을 하기 위해 만든 언어이다. 이 언어에는 두 가지 함수 R(뒤집기)과 D(버리기)가 있다.

함수 R은 배열에 있는 숫자의 순서를 뒤집는 함수이고, D는 첫 번째 숫자를 버리는 함수이다. 배열이 비어있는데 D를 사용한 경우에는 에러가 발생한다.

함수는 조합해서 한 번에 사용할 수 있다. 예를 들어, "AB"는 A를 수행한 다음에 바로 이어서 B를 수행하는 함수이다. 예를 들어, "RDD"는 배열을 뒤집은 다음 처음 두 숫자를 버리는 함수이다.

배열의 초기값과 수행할 함수가 주어졌을 때, 최종 결과를 구하는 프로그램을 작성하시오.



### 입력

첫째 줄에 테스트 케이스의 개수 T가 주어진다. T는 최대 100이다.

각 테스트 케이스의 첫째 줄에는 수행할 함수 p가 주어진다. p의 길이는 1보다 크거나 같고, 100,000보다 작거나 같다.

다음 줄에는 배열에 들어있는 수의 개수 n이 주어진다. (0 ≤ n ≤ 100,000)

다음 줄에는 [x1,...,xn]과 같은 형태로 배열에 들어있는 수가 주어진다. (1 ≤ xi ≤ 100)

전체 테스트 케이스에 주어지는 p의 길이의 합과 n의 합은 70만을 넘지 않는다.



### 출력

각 테스트 케이스에 대해서, 입력으로 주어진 정수 배열에 함수를 수행한 결과를 출력한다. 만약, 에러가 발생한 경우에는 error를 출력한다.





## 풀이 방법

---

문제를 풀 때 다음과 같은 사항을 고려해야 했다.

1. 입력 방법: [1,2,3,4] 처럼 str 형식으로 입력을 받기 때문에, 이를 list로 전환해야 한다.

2. error

   * 비어 있는 list에 D 연산을 적용할 때에만 error 처리해야 한다.

   * 따라서 []가 들어올 때, D 연산이 들어올 때에만 error 처리해야 한다.

3. 시간초과

   * 처음에 reverse, delete 함수를 구현하고, 문제에서 시키는 대로 R이 들어오면 reverse를, D가 들어오면 delete 함수를 실행했다. 그랬더니 시간 초과가 났다.
   * [질문 글]()에서 힌트를 얻었다. RR, RRRR과 같이 R이 짝수 번만큼 실행되면 reverse 함수를 전부 다 실행할 필요가 없다.

4. 출력 형식 : 역시 list가 아니고, 입력에서 주어진 것과 동일한 형식으로 출력해야 한다.



핵심은 reverse 연산이 수행된 누적 횟수에 따라 1) delete 연산을 어떻게 구현할 것인지와, 2) 마지막에 어떻게 출력할지 이다.

* reverse 연산이 수행된 누적 횟수가 짝수라면, 리스트는 원래 모양과 같아야 한다.
  * delete 연산을 수행할 때, 맨 앞의 원소를 pop한다.
  * 마지막에 출력할 때 그대로 출력한다.
* 반대로 홀수라면, 리스트는 뒤집어진 모양과 같다.
  * delete 연산을 수행할 때, 맨 뒤 원소를 pop한다.
  * 마지막에 출력할 때 반대로 출력한다.



## 풀이 코드

---

* 가장 먼저 입력으로 "[]"가 들어오는 경우를 생각한다. n = 0인 경우이므로, n=0일 때 "D" 명령이 들어온다면 바로 error가 난다.
* 그 외의 경우는, try, except, else 구문을 이용해 구현한다.
  * try : reverse, delete 연산을 수행한다.
  * except : 비어 있는 리스트에 delete 연산을 수행하면 `IndexError`가 난다. except절에서 "error"를 출력한다.
  * else : 에러가 나지 않을 때, reverse의 누적 횟수에 따라 리스트를 출력한다.
  * 

```python
import sys

t = int(sys.stdin.readline())

for _ in range(t):

    com = sys.stdin.readline().rstrip()
    n = int(sys.stdin.readline())
    arr = sys.stdin.readline()[1:-2].split(',')

    if n == 0: # 빈 배열이 들어올 때,
        if "D" in com: # 삭제할 수 없으므로 error.
            print("error")
        else:
            print("[]")
    
    else:

        arr = [int(i) for i in arr]
        
        rCount = 0

        try:
            for command in com:
                if command == "R":
                    rCount += 1
                else:
                    if rCount % 2 == 0: # 지금까지 명령 내 reverse 횟수가 짝수면,
                        arr.pop(0) # 앞을 pop.
                    elif rCount % 2 == 1: # 홀수면,
                        arr.pop() # 뒤를 pop.

        except IndexError:
            print("error")
        
        else:           
            if rCount % 2 == 1: # 명령 내 모든 reverse 횟수가 홀수번이면 반대로 출력
                print("[", end="")
                print(*arr[::-1], sep=",", end="") # 모든 원소 출력
                print("]")
            else:
                print("[", end="")
                print(*arr, sep=",", end="")
                print("]")
```



## 다른 풀이





## 배운 점, 더 생각해 볼 것

* 예전부터 공부해야겠다고 생각했던 try, except, else 구문을 드디어 활용해야 하는 때가 와서, [공부했다](https://wayhome25.github.io/python/2017/08/20/python-try-return-finally/). 아직 에러를 직접 발생시키는 경우에 대한 이해가 부족하다.


* 일단 문제를 풀긴 했으나, 시간이 굉장히 오래 걸린다. 시행착오를 굉장히 많이 겪었기 때문에, 일단 지금은 문제를 풀었음에 의의를 둔다. 이후 시간을 줄일 수 있는 방법을 찾아야 한다. 그 때까지 다른 사람의 풀이는 보지 않는 것이 좋을 것 같다.