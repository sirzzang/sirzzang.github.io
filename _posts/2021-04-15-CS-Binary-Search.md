---
title:  "[Algorithm] 이분탐색"
excerpt: 이분탐색 혹은 이진탐색
header:
  teaser: /assets/images/blog-Programming.jpg
categories:
  - CS
toc : true
tags:
  - Python
  - 알고리즘
  - 탐색
  - 이진탐색
  - 이분탐색
  - 분할정복
---



 선형 자료 구조(리스트, 어레이, 스택, 큐 등)에서의 대표적인 탐색 방법으로 선형 탐색(linear search), 이분 탐색(binary search), 해싱이 있다. 그 중에서도 이분 탐색은 선형 탐색에 비해 최악의 경우에도 시간복잡도가 더 좋아 자주 사용되는 탐색 방법이다. 

<br>

# 개념

 **이분 탐색**(*Binary Search*)은 이미 정렬되어 있는 배열에서 탐색 범위를 반씩 줄여 가며 찾고자 하는 값을 찾는 탐색 방법이다. 예컨대, 1부터 10까지 있는 배열에서 4를 찾고자 한다. 이 때, 1부터 5까지 절반을 먼저 탐색하고, 그 안에 4가 있기 때문에 6부터 10까지를 버린다. 다시 절반인 1부터 3까지를 탐색하여 그 안에 4가 없기 때문에 해당 범위를 버린다. 이렇게 분할하면서 필요 없는 부분을 버리고, 필요한 것을 찾아 간다. 

 절반씩 범위를 줄여 가며 찾기 때문에, 선형 자료 구조 내 내용이 미리 정렬되어 있어야 한다. 

> *참고*: random access
>
>  구글링을 하다 보니, binary search의 경우 random access가 가능해야 성능을 보장할 수 있다고 한다. 즉, C언어와 같이 인덱스만 알면 특정 배열에서 그 인덱스에 해당하는 값을 $O(1)$의 시간복잡도로 참조할 수 있어야 한다고 한다. [이 글](https://wayhome25.github.io/python/2017/06/14/time-complexity/)을 참고하니 파이썬에서는 random access가 가능한 듯.
>
>  다만, random access가 불가능하더라도 이분 탐색이 가능하긴 하다. 단지 좋은 성능을 기대할 수 없을 뿐이라고. 그래서 sequential access만 가능한 연결 리스트와 같은 자료 구조에서는 탐색 시 이분 탐색을 잘 사용하지 않는다고 한다.

<br>

# 원리



 이분 탐색을 구현하기 위해서는 다음과 같은 과정이 필요하다.

* 배열을 정렬한다.
* 정렬된 배열에서 왼쪽 끝 인덱스 `left`와 오른쪽 끝 인덱스 `right`을 이용해 중간 인덱스 `mid` 값을 찾는다.
* `mid` 인덱스와 배열에서 찾고자 하는 값 `target`을 비교한다.
* `target`이 나올 때까지 탐색 과정을 반복한다.
  * `mid` 값보다 `target`이 크다면 `left`를 `mid+1`로 이동시켜, 오른쪽 구간에서 탐색한다.
  * `mid` 값보다 `target`이 작다면 `right`을 `mid-1`로 이동시켜, 왼쪽 구간에서 탐색한다.
* `target`이 없다면, `None`을 반환한다.



# 구현

 위의 과정을 반복과 재귀를 사용하여 모두 구현할 수 있다. 왼쪽 인덱스와 오른쪽 인덱스 값을 어떻게 이동시켜주느냐의 관점에서 차이가 있다.



## 반복



```python
def binary_search(array, target):
    array.sort() # 정렬
    
    left = 0
    right = len(array)-1
    
    while left <= right:
        mid = (left + right)//2 # 가운데 인덱스
        if array[mid] == target: # 찾는 값을 만나면 반환
            return mid 
        elif array[mid] > target: # 가운데 값이 더 크면 왼쪽 구간으로 이동
            right = mid-1 
        else: # 가운데 값이 더 작으면 오른쪽 구간으로 이동
            left = mid+1
    
    return None # 찾는 값이 없을 때
```



## 재귀



```python
def binary_search(array, target, left, right):
    
    if left > right: # 찾는 값이 없을 때
        return None
    
    mid = (left + right)//2
    if target == array[mid]:
        return
    elif target > array[mid]: # 왼쪽 구간에 대해 재귀 호출
        binary_search(array, target, left, mid-1)
    else: # 오른쪽 구간에 대해 재귀 호출
        binary_search(array, target, mid+1, right) 
```

# 파이썬 bisect 모듈



 파이썬에서는 이분 탐색 알고리즘을 사용해 배열을 검색하고, 배열에 항목을 삽입할 수 있는 표준 내장 라이브러리 [bisect](https://docs.python.org/3/library/bisect.html)가 지원된다. 

<br>

 정렬된 리스트에서의 위치를 찾고자 할 경우, `bisect` 모듈의 `bisect_left`, `bisect_right`, `bisect` 함수를 사용하면 된다. `bisect_left`은 찾고자 하는 값의 위치(만약 찾고자 하는 값이 없다면, 그 값이 들어가야 할 위치)를 반환한다. `bisect_right`, `bisect` 함수는 찾고자 하는 값이 있다면 그 값의 위치보다 한 칸 뒤의 위치를 반환하고, 찾고자 하는 값이 없다면 `bisect_left`와 같은 방식으로 동작한다.

```python
from bisect import *

my_list = [30, 94, 27, 92, 21, 37, 25, 47, 25, 53, 98, 19, 32, 32, 7]
my_list.sort()
bisect_left(my_list, 25) # 3
bisect_left(my_list, 26) # 5
bisect_right(my_list, 25) # 5
bisect(my_list, 25) # 5
bisect(my_list, 26) # 5
```

 삽입하고자 할 때는 `insort_left`, `insort_right`, `insort` 함수를 사용하면 된다. 리스트에 삽입이 된다는 것만 다를 뿐, 기본 동작 원리는 `bisect_`로 시작하는 함수와 동일하다.

<br>

# 시간복잡도

 이분 탐색을 반복할 수록, 탐색할 자료의 개수가 절반으로 줄어든다. 따라서 $$N$$개의 자료가 있을 때, 총 $$K$$번 자료를 검색한다면, 남은 자료의 개수는 $$N \cdot {\frac {1} {2}}^K$$이다. 최악의 경우, 탐색 종료 시점에 남는 자료의 개수가 1이 되어야 하므로, $$K=log_2^N$$이 된다. 따라서, 시간복잡도는 $O(logN)$이다.



> 참고
>
> * 프로그래머스 [징검다리 건너기](https://programmers.co.kr/learn/courses/30/lessons/64062) 문제 풀다가, 배열 내에 중복된 자료가 있을 때는 어떻게 이분 탐색을 해야 하는지 궁금해 졌다. [이 글](https://eine.tistory.com/entry/%EC%9D%B4%EC%A7%84-%ED%83%90%EC%83%89-%EC%9D%B4%EB%B6%84-%ED%83%90%EC%83%89binary-search-%EA%B5%AC%ED%98%84%EC%8B%9C-%EA%B3%A0%EB%A0%A4%ED%95%A0-%EA%B2%83%EB%93%A4)을 참고하니 `upper_bound`와 `lower_bound`를 구한 뒤, `lower_bound`부터 `upper_bound`까지 훑어서 해당 크기의 모든 원소를 탐색하면 된다고 한다.
> * 자료가 정렬이 되어 있어야 한다면, (내장 정렬 함수를 사용하지 않는다고 가정했을 때) 정렬 알고리즘에 따라서도 효율성이 달라질 수 있으..려나?
> * [이코테 이진탐색 강의](https://www.youtube.com/watch?v=94RC-DsGMLo)를 참고하니, 다음의 경우에는 반드시 이분 탐색을 떠올려야 한다고.
>   * 최적화 문제를 결정 문제(`예` 혹은 `아니오`)로 바꾸어 해결하는 **파라메트릭 서치**(*parametric search*)가 필요한 경우
>   * 탐색 범위가 큰 경우(예컨대, 0부터 10억 까지의 정수 중 하나)