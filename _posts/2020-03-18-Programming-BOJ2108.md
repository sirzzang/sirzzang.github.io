---
title:  "[백준] BOJ11286 통계학"
excerpt:
header:
  teaser: /assets/images/blog-Programming.jpg

categories:
  - Programming
tags:
  - Python
  - Programming
  - BOJ
  - 알고리즘
  - 정렬
---

> [문제 출처](https://www.acmicpc.net/problem/2108)



## 문제

---

---

수를 처리하는 것은 통계학에서 상당히 중요한 일이다. 통계학에서 N개의 수를 대표하는 기본 통계값에는 다음과 같은 것들이 있다. 단, N은 홀수라고 가정하자.

1. 산술평균 : N개의 수들의 합을 N으로 나눈 값
2. 중앙값 : N개의 수들을 증가하는 순서로 나열했을 경우 그 중앙에 위치하는 값
3. 최빈값 : N개의 수들 중 가장 많이 나타나는 값
4. 범위 : N개의 수들 중 최댓값과 최솟값의 차이

N개의 수가 주어졌을 때, 네 가지 기본 통계값을 구하는 프로그램을 작성하시오.



### 입력

첫째 줄에 수의 개수 N(1 ≤ N ≤ 500,000)이 주어진다. 그 다음 N개의 줄에는 정수들이 주어진다. 입력되는 정수의 절댓값은 4,000을 넘지 않는다.

### 출력

첫째 줄에는 산술평균을 출력한다. 소수점 이하 첫째 자리에서 반올림한 값을 출력한다. 둘째 줄에는 중앙값을 출력한다. 셋째 줄에는 최빈값을 출력한다. 여러 개 있을 때에는 최빈값 중 두 번째로 작은 값을 출력한다. 넷째 줄에는 범위를 출력한다.						



## 풀이 방법

---

* 3시간 동안 너무나도 많은 시행착오를 거쳤다.
  * `QuickSort`를 사용해서 구현하면 시간 초과가 난다.
  * 1개의 값만 입력될 때를 주의하자. 
  * 최빈값이 여러 개일 때, 1개일 때 구현에 주의해야 한다.
* 산술 평균, 최빈값의 구현에 주의한다.
  * 산술 평균을 구할 때, round와 int 함수를 쓰면 안 된다.
  * 최빈값을 구현할 때 `collections` 모듈에서 `Counter`를 사용했다.
* 처음 -4000, 4000을 배열에 받는 방법을 구현하고 싶었으나, 어려움을 겪어 아쉬웠다.



## 풀이 코드



*56636KB, 608ms*

```python
import sys
from collections import Counter

n = int(sys.stdin.readline())

total = 0
arr = []
for _ in range(n):
    num = int(sys.stdin.readline())
    arr.append(num)
    total += num
arr = sorted(arr)


avg = total / n
print('%.0f' %(avg))


if n == 1:
    print(arr[0])
    print(arr[0])
    print(0)

else:
    print(arr[n//2])
    counts = Counter(arr).most_common()
    if counts[1][1] == counts[0][1]:
        print(counts[1][0])
    else:
        print(counts[0][0])

    print(arr[-1]-arr[0], end = "")
```





## 다른 풀이

---

> [코드 출처](https://www.acmicpc.net/source/16520219)

*29284KB, 280ms*

```python
import sys

read = sys.stdin.readline
N = int(read())
num = [0] * 8001    #num[0] = -4000
ans = [0] * 4
for i in range(N):
    num[int(read())+4000] += 1

l = sum(num)
s = 0
s_idx = 0
ans[1] = -4001
max_val = -4001
min_val = 4001
most = max(num)
most_vals = []
for n, i in enumerate(num):
    if i:
        val = n-4000
        s += val * i
        s_idx += i
        if ans[1] == -4001 and s_idx > l / 2:
            ans[1] = val
        if i == most:
            most_vals.append(val)
        max_val = max(max_val, val)
        min_val = min(min_val, val)
ans[0] = int("{:.0f}".format(s/l))
ans[2] = most_vals[0] if len(most_vals) == 1 else most_vals[1]
ans[3] = max_val - min_val

print("{}\n{}\n{}\n{}".format(ans[0], ans[1], ans[2], ans[3]))
```



> [코드 출처](https://www.acmicpc.net/source/14489213)

*29056KB, 292ms*

```python
import sys
s=sys.stdin.readline

def mean(n):
    total_val = 0
    for i in range(len(input_list)):
        total_val += (i - 4000) * input_list[i]
        
    return round(total_val / n)


def median(n):
    middle = (n // 2 + 1)
    count = 0
    
    for i in range(len(input_list)):
        if input_list[i] != 0:
            if middle == 1:
                return i - 4000


            if count < middle:
                count += input_list[i]
                if count >= middle:
                    return i - 4000

              
def max_count(n):
    max_count = 0
    idx_list = []
    
    for i in range(len(input_list)):
        if input_list[i] != 0:
            if max_count <= input_list[i]:
                max_count = input_list[i]
                idx_list.append(i)
                
    if len(idx_list) == 1:
        return idx_list[-1] - 4000
    
    else:
        sort_list = []
        pivot_idx = idx_list[-1]
        pivot_count = input_list[pivot_idx]
        for i in range(len(idx_list)-1, -1, -1):
            idx = idx_list[i]
            if input_list[idx] == pivot_count:
                sort_list.append(idx  - 4000)
                
            else:
                break
        
        if len(sort_list) == 1:
            return sort_list[0]
        
        else:
            return sort_list[-2]
                            
        
def value_range(n):
    len_list = len(input_list)
    min_val = 0
    max_val = 0
    count = 0
    for i in range(len_list):
        if input_list[i] != 0:
            min_val = i - 4000
            for j in range(len_list-1, -1, -1):
                if input_list[j] != 0:
                    max_val = j - 4000
                    return max_val - min_val

length = 8001
input_list = [0] * length

n = int(s())

for i in range(n):
    idx = int(s())
    input_list[idx+4000] += 1
    

print(mean(n))
print(median(n))
print(max_count(n))
print(value_range(n))
```







## 배운 점, 더 생각해 볼 것

---

* 파이썬의 `round` 함수는 사용에 [주의해야 한다](https://light-tree.tistory.com/107). `round(2.5)`는 2이지만, `round(3.5)`는 3이다. 소수점 형식을 지정해서 출력하는 방법을 사용하자.

  ```python
  print('%.2f' %avg) # 소수점 2자리까지 출력.
  print('%.0f' %avg) # 소수점 출력하지 않음. 
  ```

* Counting 정렬을 응용해 인덱스가 음수일 때와 양수일 때 배열에 다르게 저장하는 방법을 구현하고 싶었다. -4000일 때의 인덱스가 0이 되고, 0일 때의 인덱스가 4000, 4000일 때의 인덱스가 8000이 되는 방법을 찾았으나, 결국 구현하지 못했다. 다른 사람의 코드를 공부하며 [더 고민해 보자](https://home-body.tistory.com/438). 