---
title:  "[백준] BOJ18258 큐 2"
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
  - 큐
  - 시간복잡도
---







> [문제 출처](https://www.acmicpc.net/problem/18258)



## 문제

---



정수를 저장하는 큐를 구현한 다음, 입력으로 주어지는 명령을 처리하는 프로그램을 작성하시오.

명령은 총 여섯 가지이다.

- push X: 정수 X를 큐에 넣는 연산이다.
- pop: 큐에서 가장 앞에 있는 정수를 빼고, 그 수를 출력한다. 만약 큐에 들어있는 정수가 없는 경우에는 -1을 출력한다.
- size: 큐에 들어있는 정수의 개수를 출력한다.
- empty: 큐가 비어있으면 1, 아니면 0을 출력한다.
- front: 큐의 가장 앞에 있는 정수를 출력한다. 만약 큐에 들어있는 정수가 없는 경우에는 -1을 출력한다.
- back: 큐의 가장 뒤에 있는 정수를 출력한다. 만약 큐에 들어있는 정수가 없는 경우에는 -1을 출력한다.



### 입력

첫째 줄에 주어지는 명령의 수 N (1 ≤ N ≤ 2,000,000)이 주어진다. 둘째 줄부터 N개의 줄에는 명령이 하나씩 주어진다. 주어지는 정수는 1보다 크거나 같고, 100,000보다 작거나 같다. 문제에 나와있지 않은 명령이 주어지는 경우는 없다.



### 출력

출력해야하는 명령이 주어질 때마다, 한 줄에 하나씩 출력한다.





## 풀이 방법

---

* 문제를 처음 풀 때, 시간초과 문제가 있었다.

  * [큐 2 FAQ](https://www.acmicpc.net/board/view/45080)를 참고하니, list에서 특정 위치에 있는 원소를 제거하면 안 된다는 말이 있었다. 큐의 pop에서 내가 구현한 `pop(0)`이 문제가 된다는 말인 것 같다.
  * 입력이 최대 2,000,000까지 들어오므로, 연산을 비효율적으로 구현하면 시간 초과가 난다. **O(1)의 시간복잡도**를 가지도록 풀이를 구현해야 한다.
  * 시간복잡도가 무엇인지 정확하게 알지 못하지만, 일단 구글링을 통해 [Python 자료형별 시간복잡도](https://deepwelloper.tistory.com/72)를 알 수 있었다.  **시간복잡도가 O(1)인 `pop()`과 달리, `pop(특정 위치)`는 시간복잡도가 O(n)이다.** 뒤에 있는 원소들을 일일이 왼쪽으로 미느라 시간이 낭비되기 때문이라고 한다.

  

* 따라서, pop()을 사용하지 않고, index만을 이용해 pop 연산을 구현해야 한다.
  * front_index와 queue_length를 정의한다.
    * front_index : pop해 올 원소의 위치. 즉, 해당 queue에서 맨 앞 index.
    * queue_length : queue의 길이.
  * front_index와 queue_length가 영향을 미치는 연산을 생각한다. 
    * _pop_ : 스택 문제([BOJ 10828](https://www.acmicpc.net/problem/10828))와 달리, 실제로 원소를 빼지는 않는다. 연산이 수행될 때, **front_index를 한 칸씩 뒤로 밀고, queue_length를 1씩 감소**시킨다.
    * _size_ : queue_length를 그대로 출력한다.
    * _empty_ : queue_length가 0이면 1을, 아니면 0을 출력한다.
    * _front_ : front_index를 이용하여 queue 원소를 indexing한다.
    * _back_ : **front_index + queue_length - 1이 가장 마지막에 있는 원소 위치가 된다**. list의 index가 0부터 시작하므로, 1을 빼주어야 한다.

  

* 문제 풀이 과정에서 다음과 같은 시행착오([217188ab](https://github.com/sirzzang/Baekjoon_problems/blob/master/큐%2C%20덱/큐_큐2_BOJ18258.py))를 겪었다.



## 풀이 코드

* class 사용하지 않은 구현 : 89196kb 2228ms.

```python
import sys

n = int(sys.stdin.readline())
queue = []
queue_length = 0 # push할 때마다 length 증가.
front_index = 0 # pop 연산 이루어질 때마다 처음 index를 나타낼 것.

for _ in range(n):
    input_method = sys.stdin.readline().split()

    if input_method[0] == "push":
        queue.append(int(input_method[1]))
        queue_length += 1
    
    elif input_method[0] == "pop":
        if queue_length == 0:
            print(-1)

        else:
            print(queue[front_index])
            front_index += 1
            queue_length -= 1

    elif input_method[0] == "size":
        print(queue_length)
    
    elif input_method[0] == "empty":
        if queue_length == 0:
            print(1)
        else:
            print(0)
    
    elif input_method[0] == "front":
        if queue_length == 0:
            print(-1)
        else:
            print(queue[front_index])

    else:
        if queue_length == 0:
            print(-1)
        else:
            print(queue[queue_length + front_index - 1]) # front index + queue_length를 하면, index 1 초과.
```

* class를 사용한 구현 : 89196kb 2452ms.

```python
import sys

class Queue:
    
    def __init__(self):
        self.itemList = []
        self.itemList_len = 0
        self.front_index = 0

    def push(self, item):
        self.itemList.append(item)
        self.itemList_len += 1
    
    def pop(self):
        if self.itemList_len == 0:
            return -1
        else:
            self.front_index += 1
            self.itemList_len -= 1
            return self.itemList[self.front_index-1] # front_index가 return 뒤로 가면 안 된다.          
    
    def size(self):
        return self.itemList_len
    
    def empty(self):
        if self.itemList_len == 0:
            return 1
        else:
            return 0
    
    def front(self):
        if self.itemList_len == 0:
            return -1
        else:
            return self.itemList[self.front_index]
    
    def back(self):
        if self.itemList_len == 0:
            return -1
        else:
            return self.itemList[self.front_index + self.itemList_len -1]

myQueue = Queue()

n = int(sys.stdin.readline())

for _ in range(n):
    input_method = sys.stdin.readline()

    if "push" in input_method:
        myQueue.push(int(input_method.split()[1]))
    
    elif "pop" in input_method:
        print(myQueue.pop())
    
    elif "size" in input_method:
        print(myQueue.size())
    
    elif "empty" in input_method:
        print(myQueue.empty())
    
    elif "front" in input_method:
        print(myQueue.front())
    
    else:
        print(myQueue.back())
```





## 다른 풀이

> [코드 출처](https://www.acmicpc.net/source/13964893)

```python
# python3

import sys
from collections import deque

deq = deque([])
num = int(sys.stdin.readline())
clist = sys.stdin.read().split("\n")
for i in clist:
	if i == "pop":
		if len(deq) == 0:
			print(-1)
		else:
			print(deq.popleft())
	elif i == "size":
		print(len(deq))
	elif i == "empty":
		if len(deq) == 0:
			print(1)
		else:
			print(0)
	elif i == "front":
		if len(deq) == 0:
			print(-1)
		else:
			print(deq[0])
	elif i == "back":
		if len(deq) == 0:
			print(-1)
		else:
			print(deq[-1])
	elif i.split(" ")[0] == "push":
		i = i.split(" ")
		deq.append(i[1])
```

* collections 모듈을 import해 deque를 사용했다. 실제 코딩테스트에서 모듈을 import할 수 있을지 몰라서, 내장함수와 자료구조만으로 구현하는 방식을 사용했는데, deque를 사용해도 되는지 알아봐야 겠다.



## 배운 점, 더 생각해 볼 것

* [시간복잡도](https://www.ics.uci.edu/~pattis/ICS-33/lectures/complexitypython.txt), [Big-O표기법](https://brenden.tistory.com/2) 공부하자.
* [deque](https://dongdongfather.tistory.com/72) 공부하자.