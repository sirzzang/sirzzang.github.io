---
title:  "[재귀] 하노이의 탑"
excerpt:
header:
  teaser: /assets/images/blog-Programming.jpg
categories:
  - Python
tags:
  - Python
  - 재귀
  - 하노이의 탑
---

---





# 하노이의 탑



## 문제



 다음의 규칙을 만족하면서 한 기둥에 꽂힌 원판들을 순서대로 다른 기둥으로 옮긴다.

* 한 번에 하나의 원판만 옮긴다.
* 큰 원판이 작은 원판 위에 있을 수 없다.



## 원리



[참고](https://www.youtube.com/watch?v=buWXDMbY3Ww)



![tower of hanoi]({{site.url}}/assets/images/hanoi.png)



1. 맨 아래(가장 큰) 원반을 제외한 다른 원반을 **보조 기둥**으로 옮긴다.
2. 맨 아래 원반을 **목적지 기둥**으로 옮긴다.
3. 보조 기둥에 옮겨 놓았던 원반을 옮긴 **맨 아래 원반 위**로 옮긴다.



## 구현



* **Parameters** : 원반 개수, 시작 기둥(start), 목적지 기둥(end), 보조 기둥(spare).

* **Base Case** : 원반이 1개일 때(원반이 1개일 때는, 시작 기둥에서 목적지 기둥으로 바로 옮긴다.)
* **이해** 
  * 각 단계에서 함수는, *시작 기둥에서 목적지 기둥으로* 지정된 개수의 원반을 옮김을 의미한다.
  * 옮겨야 할 원반이 1개가 될 때까지 함수를 재귀적으로 호출한다.
  * 1개의 원반을 시작 기둥에서 목적지 기둥으로 옮기는 과정의 반복이다. 즉, 이동 경로는 *항상* 시작 기둥에서 목적지 기둥이 된다. 그 과정에 목적지 기둥과 보조 기둥이 *왔다 갔다* 하며 변화하게 된다. 



### 1. 이동 경로

```python
def Hanoi(n, start, end, spare):
    if n == 1: # Base Case : 시작 기둥에서 목적지 기둥으로 바로 옮긴다.
        print(start, "->", end) # 이동 경로
        return
    Hanoi(n-1, start, spare, end) # n-1개의 원판을 보조 기둥으로 옮긴다.
    print(start, "->", end) # 이동 경로
    Hanoi(n-1, spare, end, start) # 보조 기둥의 n-1개의 원판을 목적지 기둥으로 옮긴다.

>>> Hanoi(4, "A", "C", "B")
# A -> B
# A -> C
# B -> C
# A -> B
# C -> A
# C -> B
# A -> B
# A -> C
# B -> C
# B -> A
# C -> A
# B -> C
# A -> B
# A -> C
# B -> C
```





### 2. 횟수



***방법 1***

 시작 기둥에 몇 개의 원판이 있는지만 주어진다. 

```python
def Hanoi(n, start, end, spare):
    if n == 1: # Base Case : 시작 기둥에서 목적지 기둥으로 1회 만에 옮긴다.
        return 1
    cnt = 0
    cnt += Hanoi(n-1, start, spare, end) # n-1개의 원판을 보조 기둥으로 옮긴다.
    cnt += 1 # 맨 아래 원판을 목적지 기둥으로 옮긴다.
    cnt += Hanoi(n-1, spare, end, start) # 보조 기둥의 n-1개의 원판을 목적지 기둥으로 옮긴다.
    return cnt

>>> Hanoi(4, 'A', 'C', 'B') # 31
```



 다음과 같이 구현해도 된다.

```python
def Hanoi(n, start, end, spare):
    global cnt
    if n == 1:
        cnt += 1
        return
    else:
        Hanoi(n-1, start, spare, end)
        Hanoi(1, start, end, spare)
        Hanoi(n-1, spare, end, start)

def main(n):
    Hanoi(n, "a", "c", "b")
    return cnt

>>> cnt = 0
>>> main(4) # 31
```



***방법 2***

 각 기둥의 원판이 숫자, 문자 등의 리스트로 주어진다. 보조 기둥, 목적지 기둥은 비어 있는 리스트로 주어진다. 한 원판을 옮길 때마다 시작 기둥에서 `pop` 메서드를 사용해 목적지 기둥에 옮긴다. 시작 기둥에 옮겨야 할 원판이 남아 있는 경우에 재귀 호출이 이루어진다. ([참고](https://scipython.com/book/chapter-2-the-core-python-language-i/examples/the-tower-of-hanoi/))

```python
def Hanoi(n, start, end, spare):
    if n == 0: # 옮길 원반이 없는 경우
        return
    global cnt
    cnt += 1
    Hanoi(n-1, start, spare, end)
    if start: # 옮길 원반이 남아 있는 경우
        end.append(start.pop())
    Hanoi(n-1, spare, start, end)

>>> n = 4
>>> A = list(range(n)) # [1, 2, 3, 4]
>>> B, C = [], []
>>> cnt = 0
>>> Hanoi(n, A, C, B)
>>> print(cnt) # 31
```



 다음과 같이 구현해도 된다. 다만, 위와 달리 24개까지 원반을 옮기는 데 걸리는 횟수를 모두 구하는 코드이다.

```python
def Hanoi(n, start, end, spare):    
    global cnt
    if n > 0 :
        Hanoi(n-1, start, spare, end)
        end.append(start.pop())
        cnt += 1
        Hanoi(n-1, spare, end, start)

>>> num_cnts = []
>>> for n in range(1, 25):
    A = list(range(n))
    B, C = [], []
    cnt = 0
    Hanoi(n, A, C, B)
    num_cnts.append(cnt)
>>> print(num_cnts) # [1, 3, 7, 15, 31, 63, 127, 255, 511, 1023, 2047, 4095, 8191, 16383, 32767, 65535, 131071, 262143, 524287, 1048575, 2097151, 4194303, 8388607, 16777215]
```

