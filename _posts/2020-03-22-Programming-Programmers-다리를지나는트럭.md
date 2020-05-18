---
title:  "[Programmers] 다리를 지나는 트럭"
excerpt: "1일 1문제풀이 3일차"
header:
  teaser: /assets/images/blog-Programming.jpg
toc: true
categories:
  - Programming
tags:
  - Python
  - Programming
  - Programmers
  - 덱
---

> [문제 출처](https://programmers.co.kr/learn/courses/30/lessons/42583)



# 1. 문제



 트럭 여러 대가 강을 가로지르는 일 차선 다리를 정해진 순으로 건너려 합니다. 모든 트럭이 다리를 건너려면 최소 몇 초가 걸리는지 알아내야 합니다. 트럭은 1초에 1만큼 움직이며, 다리 길이는 bridge_length이고 다리는 무게 weight까지 견딥니다.

※ 트럭이 다리에 완전히 오르지 않은 경우, 이 트럭의 무게는 고려하지 않습니다.

 예를 들어, 길이가 2이고 10kg 무게를 견디는 다리가 있습니다. 무게가 [7, 4, 5, 6]kg인 트럭이 순서대로 최단 시간 안에 다리를 건너려면 다음과 같이 건너야 합니다.

| 경과 시간 | 다리를 지난 트럭 | 다리를 건너는 트럭 | 대기 트럭 |
| --------- | ---------------- | ------------------ | --------- |
| 0         | []               | []                 | [7,4,5,6] |
| 1~2       | []               | [7]                | [4,5,6]   |
| 3         | [7]              | [4]                | [5,6]     |
| 4         | [7]              | [4,5]              | [6]       |
| 5         | [7,4]            | [5]                | [6]       |
| 6~7       | [7,4,5]          | [6]                | []        |
| 8         | [7,4,5,6]        | []                 | []        |

 따라서, 모든 트럭이 다리를 지나려면 최소 8초가 걸립니다.

solution 함수의 매개변수로 다리 길이 bridge_length, 다리가 견딜 수 있는 무게 weight, 트럭별 무게 truck_weights가 주어집니다. 이때 모든 트럭이 다리를 건너려면 최소 몇 초가 걸리는지 return 하도록 solution 함수를 완성하세요.



**제한사항**

- bridge_length는 1 이상 10,000 이하입니다.
- weight는 1 이상 10,000 이하입니다.
- truck_weights의 길이는 1 이상 10,000 이하입니다.
- 모든 트럭의 무게는 1 이상 weight 이하입니다.



**입출력 예**

| bridge_length | weight | truck_weights                   | return |
| ------------- | ------ | ------------------------------- | ------ |
| 2             | 10     | [7,4,5,6]                       | 8      |
| 100           | 100    | [10]                            | 101    |
| 100           | 100    | [10,10,10,10,10,10,10,10,10,10] | 110    |



---



# 2. 나의 풀이 

## 풀이 방법

 

 모든 트럭이 1초에 1씩 움직인다. 트럭 1대가 다리를 지나가기 위해서는 다리 길이만큼의 시간이 필요하다.   



 트럭이 진입하여 다리를 건너는 것을 구현하기 위해 **덱**을 사용했다. 트럭이 한 쪽에서 진입하고, 1초가 지날 때마다 반대 방향으로 한 칸씩 이동해야 해야 하기 때문에, *양방향* 에서 자료를 삽입 또는 삭제할 수 있는 자료구조가 적합하다.

 트럭이 진입할 수 있는 조건은 현재 다리를 지나는 트럭 무게의 합이 다리가 견딜 수 있는 무게를 *넘기지 않을* 경우이다. 이 조건만 만족한다면 여러 대의 트럭들이 다리를 지나도 무방하다.  



 한편 트럭의 대기 순서는 문제에서 주어진다. 먼저 들어온 트럭이 먼저 나가야 하기 때문에, **큐**를 사용해 구현해야 하는데, 파이썬에서는 큐 역시 **덱**으로 구현한다. (주어진 배열을 뒤집어 스택으로 만들어도 될 것 같다.)

 처음에는 아무런 트럭도 다리 위에 없으므로, 다리 길이 만큼의 0을 갖는 초기 다리 덱(?)을 구현한다. 그리고 조건을 만족할 때마다 대기 트럭 큐를 pop하여 다리 덱에 append한다. 들어와서 나가는 방향만 정한다면, 가장 바깥에 있는 덱의 원소가 0이 아닐 때 다리 덱을 pop하여 트럭을 내보내면 된다.



> *시행 착오*
>
>   풀고 나니 별 거 아닌 것 같은데 처음에 별별 시도를 다 하느라 몇 시간은 걸린 듯하다.. ~~한 번에 올라올 수 있는 차 대수, 여러 대 함께 올릴 수 있는 차 무게 등등...~~

   



## 풀이 코드

* 다리에 들어오는 것을 덱의 오른쪽에서 진입하는 것으로, 나가는 것을 왼쪽에서 나가는 것으로 구현했다.
* 대기 트럭이 남아 있을 때까지 `while`문을 순회한다.
* 대기 트럭이 남지 않게 되면, 마지막 트럭이 다리에 진입했다는 의미이다. 따라서 마지막 트럭이 다리를 다 지나가고 난 후의 시각이 정답이 된다.

```python
from collections import deque

def solution(bridge_length, weight, truck_weights):
    trucks = deque(truck_weights)
    bridge = deque([0]*bridge_length) # 다리
    total = 0 # 다리 위 트럭 무게 총합
    time = 0 # 총 소요 시간
    
    while trucks:
        time += 1
        
        if bridge[0] != 0: # 다리의 맨 왼쪽까지 차가 오면
            total -= bridge.popleft() # 내보내고,
            bridge.appendleft(0) # 나간 자리를 만들어 준다.
        
        # 차가 이동하기 위해서는 왼쪽 칸을 비워야 한다.
        bridge.popleft()
        
        if total + trucks[0] <= weight: # 들어올 수 있다면
            total += trucks[0] # 무게 업데이트
            bridge.append(trucks.popleft()) # 대기 트럭 1대 들어온다.
        else:
            bridge.append(0) # 들어올 수 없다면 왼쪽으로 이동만 한다.
        
    answer = time + bridge_length # 마지막 차가 나가기까지 시간.
    return answer
        
```



> *참고*
>
>  처음 구현한 코드에서 시간 초과가 났다. 다리를 건너고 있는 차들의 무게를 `sum` 함수를 이용해 구했기 때문이다. sum을 사용하게 될 경우, 시간복잡도가 O(n)이므로 주의한다. 다리에서 나가고 들어오는 차들의 무게만 생각하여 총 무게를 구하자.





  

---



# 3. 다른 풀이

[풀이 출처](https://programmers.co.kr/learn/courses/30/lessons/42583/solution_groups?language=python3)

 

```python
import collections

DUMMY_TRUCK = 0


class Bridge(object):

    def __init__(self, length, weight):
        self._max_length = length
        self._max_weight = weight
        self._queue = collections.deque()
        self._current_weight = 0

    def push(self, truck):
        next_weight = self._current_weight + truck
        if next_weight <= self._max_weight and len(self._queue) < self._max_length:
            self._queue.append(truck)
            self._current_weight = next_weight
            return True
        else:
            return False

    def pop(self):
        item = self._queue.popleft()
        self._current_weight -= item
        return item

    def __len__(self):
        return len(self._queue)

    def __repr__(self):
        return 'Bridge({}/{} : [{}])'.format(self._current_weight, self._max_weight, list(self._queue))


def solution(bridge_length, weight, truck_weights):
    bridge = Bridge(bridge_length, weight)
    trucks = collections.deque(w for w in truck_weights)

    for _ in range(bridge_length):
        bridge.push(DUMMY_TRUCK)

    count = 0
    while trucks:
        bridge.pop()

        if bridge.push(trucks[0]):
            trucks.popleft()
        else:
            bridge.push(DUMMY_TRUCK)

        count += 1

    while bridge:
        bridge.pop()
        count += 1

    return count


def main():
    print(solution(2, 10, [7, 4, 5, 6]), 8)
    print(solution(100, 100, [10]), 101)
    print(solution(100, 100, [10, 10, 10, 10, 10, 10, 10, 10, 10, 10]), 110)


if __name__ == '__main__':
    main()
```

 클래스를 사용해 구현했는데도, 시간이 빠르다. 직관적으로 이해하기 쉽다. 코드를 뜯어보는 것은 여기서는 범위를 넘는다고 생각해 패스





---

  

# 4. 배운 점, 더 생각해볼 점

* 클래스로 구현한 풀이 보고 계속해서 공부하자.




