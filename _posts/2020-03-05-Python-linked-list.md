---
title:  "[자료구조] 연결 리스트(Linked List)"
excerpt:
header:
  teaser: /assets/images/blog-Programming.jpg

categories:
  - Python
tags:
  - Python
  - 자료구조
  - 연결 리스트
---









# 파이썬으로 구현하는 자료구조_Linked List



*출처*

\- [SW Expert Academy](https://swexpertacademy.com/main/learn/course/subjectDetail.do?courseId=AVuPDN86AAXw5UW6&subjectId=AWOVJ1r6qfkDFAWg)

\- [생활코딩](https://opentutorials.org/module/1335/8821)

\- [Visualgo.net](https://visualgo.net/en/list)

\- [GeeksforGeeks](https://www.geeksforgeeks.org/data-structures/linked-list/)

\- [tutorialspoint](https://www.tutorialspoint.com/python_data_structure/python_advanced_linked_list.htm)

\- [초보몽키의 개발공부로그](https://wayhome25.github.io/cs/2017/04/17/cs-19/)





# 개념



## 파이썬의 리스트



파이썬의 내장 자료구조형인 리스트는 다른 언어의 **배열**과 유사한 자료구조이다.

이러한 자료구조는 다음과 같은 특징을 가진다.

* 순서를 가진 데이터의 묶음으로, 
* 같은 데이터를 중복으로 저장할 수 있고,
* 시퀀스 자료형태로 인덱싱, 슬라이싱, 연산자, 메서드를 사용할 수 있다.



다른 언어의 배열과 달리, 크기와 데이터 타입에 제한이 없다. 

|               | 크기 변경 |     데이터 타입      |
| :-----------: | :-------: | :------------------: |
|     배열      |     X     | 선언된 하나의 타입만 |
| 파이썬 리스트 |     O     |   다양한 타입 모두   |





구체적으로 다른 언어의 자료구조 중 특히 **순차 리스트**가 파이썬의 내장 자료구조인 리스트라고 볼 수 있다. 따라서 연결 리스트에 대해 알기 위해서는, 순차 리스트에 대해 먼저 알아야 한다.



## 순차 리스트



> 파이썬의 내장 자료 구조인 리스트는 동적 배열로 작성된 리스트이다. 즉, 위에서도 보았듯 크기 변경이 가능하고, 다양한 데이터 타입을 모두 저장할 수 있는 리스트이다. 
>
> 이제부터는 이후에 구현할 연결 리스트와 구별하기 위해, 파이썬의 리스트를 "순차 리스트"라고 지칭한다. 



순차 리스트는 배열을 기반으로 구현한 리스트이다.



순차 리스트에서의 작업은 다음과 같다.

* 초기화 및 생성 : 변수에 값을 초기화함으로써 생성한다.

* 데이터 접근 : 인덱스를 이용해 원하는 위치의 데이터를 변경하고 참조할 수 있다. 우측에서부터 카운팅한 인덱스로 음수 인덱스를 사용할 수도 있다.
* 자료의 이동, 삽입 및 삭제 연산 : 원소의 접근 및 이동으로써 구현된다.



이러한 순차 리스트는 연산 특징으로 인해, **원소의 개수가 많고, 삽입/삭제 연산이 빈번한 작업에서는 소요되는 시간이 크게 증가**한다는 단점을 갖는다..



## 연결 리스트



연결 리스트는 메모리의 동적 할당을 기반으로 구현된 리스트이다. 순차 리스트와 달리, 개별적으로 위치한 원소의 주소를 연결하여 하나의 전체적인 자료구조를 형성한다. 따라서 자료의 논리적인 순서와 메모리 상 물리적 순서가 일치하지 않는다. 

![array vs. linked]({{site.url}}/assets/images/linkedlist1.jpg)

> 배열 리스트는 왼쪽 그림과 같이 원소들이 연속적으로 연결되어 있는 형태이다. 반면, 연결 리스트는 오른쪽 그림과 같이 각각의  원소들이 흩어져 있고, 연결되어 있는 형태이다.



연결 리스트는 순차 리스트의 단점을 보완한 자료구조로, 다음과 같은 장점을 갖는다.

* 링크를 통해 원소에 접근한다.
  * 삽입 및 삭제 연산 시 물리적인 순서를 맞추기 위한 작업이 필요하지 않다.
  * 따라서 순차 리스트에서처럼 자료의 이동이 필요하지 않다.
* 메모리의 효율적 사용 
  * 자료구조의 크기를 동적으로 조정할 수 있다.
  * 사용 후 기억 장소의 재사용이 가능하다.





### 구성 요소



![linked]({{site.url}}/assets/images/linkedlist2.jpg)



1. 노드/vertex : 연결 리스트에서 하나의 원소에 필요한 데이터를 갖고 있는 자료 단위.

   * 데이터 필드 : 원소의 값을 저장하는 자료구조.

   * 링크 필드 : 다음 노드의 주소를 저장하는 자료 구조.



2. 헤드 : 리스트의 처음 노드를 가리키는 레퍼런스.
   * 헤드 자체에는 데이터가 저장되지 않음.



### 연결리스트의 탐색 



연결리스트에서의 탐색은 링크를 따라 순차적으로 이루어지는, 순차 탐색의 형태를 갖는다.

![search]({{site.url}}/assets/images/linkedlist_search_visualgo.png)



탐색 작업을 의사 코드로 구현하면 다음과 같다.

```
if empty, return NOT_FOUND
index = 0, temp = head
while (temp.item != v)
	index++, temp = temp.next
	if temp == null
		return NOT_FOUND
return index
```



### 주요 기능

연결리스트에서 구현되어야 하는 주요 함수는 다음과 같다.

|     함수     | 기능                                                |
| :----------: | --------------------------------------------------- |
| addtoFirst() | 연결 리스트 앞쪽에 원소를 추가하는 연산             |
| addtoLast()  | 연결 리스트 뒤쪽에 원소를 추가하는 연산             |
|    add()     | 연결 리스트의 특정 위치에 원소를 추가하는 연산      |
|   delete()   | 연결 리스트의 특정 위치에 있는 원소를 삭제하는 연산 |
|    get()     | 연결 리스트의 특정 위치에 있는 원소를 리턴하는 연산 |





### 종류



연결 리스트에는 단순 연결 리스트(단방향 연결 리스트), 이중 연결 리스트(양방향 연결 리스트), 원형 연결 리스트가 있다. 일단 단순 연결 리스트와 이중 연결 리스트에 대해 알아본다.



**1. 단순 연결 리스트**

![sinlgy linked list]({{site.url}}/assets/images/simplelinkedlist.png)



노드가 하나의 링크 필드에 의해 다음 노드와 연결되는 구조로, 가장 단순한 형태의 연결 리스트이다. 

하나의 링크 필드와 하나의 데이터 필드로 구성된다. 헤드가 가장 앞 노드를 가리키고, 각 노드의 링크 필드가 연속적으로 다음 노드를 가리킨다. 최종적으로 `None`을 가리키는 노드가 리스트의 가장 마지막 노드가 된다.



#### 단순 연결 리스트 원소 삽입 연산



1. 메모리를 할당해 새로운 노드 new 생성한다.
2. 생성된 새로운 노드 new의 데이터 필드에 새로 삽입할 값을 저장한다.

3. 삽입될 위치의 바로 앞에 위치한 노드의 링크 필드를 new의 링크 필드에 복사한다.

4. 생성된 노드 new의 주소를 바로 앞 노드의 링크 필드에 저장한다.



삽입되는 위치에 따라 의사코드를 작성하면 다음과 같다.



* 첫 노드에 삽입(*O(1)*)

![add first]({{site.url}}/assets/images/linkedlist_addhead_visualgo.png)

```
Vertex vtx = new Vertex(v)
vtx.next = head
head = vtx
```



* 중간 노드에 삽입(*O(1)*)

![add mid]({{site.url}}/assets/images/linkedlist_addmid_visualgo.png)

```
Vertex pre = head
for (k=0; k<i-1; k++)
	pre = pre.next
Vertex aft = pre.next
Vertex vtx = new Vertex(v)
vtx.next = aft
pre.next = vtx
```



* 마지막에 삽입(*O(N)*)

![add tail]({{site.url}}/assets/images/linkedlist_addtail_visualgo.png)

```
Vertex vtx = new Vertex(v)
tail.next = vtx
tail = vtx
```



#### 단순 연결 리스트 원소 삭제 연산

1. 삭제할 노드의 앞 노드(선행 노드) 탐색한다.

2. 삭제할 노드의 링크 필드를 선행 노드에 복사한다.

   > 다음에 올 링크를 선행 노드에 저장하면, 선행 노드가 삭제할 노드의 이후 노드를 가리킨다. 결과적으로 삭제할 노드를 가리키는 노드가 없기 때문에, 삭제와 같은 기능을 한다.

   

삽입되는 위치에 따라 의사코드를 작성하면 다음과 같다.



* 첫 노드 삭제

![del head]({{site.url}}/assets/images/linkedlist_delhead_visualgo.png)

```
if empty, do nothing
temp = head
head = head.next
delete temp
```



* 중간 노드 삭제

![del mid]({{site.url}}/assets/images/linkedlist_delmid_visualgo.png)

```
if empty, do nothing
Vertex pre = head
for (k=0; k<i-1; k++)
	pre = pre.next
Vertex del = pre.next, aft = del.next
pre.next = aft // bypass del
delete del
```



* 마지막에 삽입

![del tail]({{site.url}}/assets/images/linkedlist_deltail_visualgo.png)

```
if empty, do nothing
Vertex pre = head
temp = head.next
while (temp.next != null)
	pre = pre.next
pre.next = null
```



단순 연결 리스트의 경우, 한 번 링크를 따라가기 시작하면 선행 노드로 따라가는 것이 불가능하다. 즉, 원하는 노드를 지나친 경우, 헤드부터 링크를 따라서 다시 찾아가야 한다.

이러한 단점을 보완해 구현한 자료 구조가 바로 **이중 연결 리스트**이다.



**2. 이중 연결 리스트**

![doubly linked list]({{site.url}}/assets/images/doublylinkedlist.png)



이중 연결 리스트는 단순 연결 리스트와 달리, 양쪽 방향으로 순회할 수 있도록 노드를 연결한 리스트이다.

하나의 노드는 두 개의 링크 필드와 한 개의 데이터 필드로 구성한다.

- prev : 이전 노드의 링크 주소 저장하는 링크 필드.
- data : 노드의 값을 저장하는 데이터 필드.
- next : 이후 노드의 링크 주소 저장하는 링크 필드.





#### 이중 연결 리스트 원소 삽입 연산

> 총 4개의 링크 연산이 필요하며, 순서를 잘 이해해야 구현할 수 있다.



1. 메모리를 할당하여 새로운 노드 new를 생성하고, 데이터 필드에 삽입할 값을 저장한다.
2. cur의 next를 new의 next에 저장하여, cur의 다음 노드를 삽입할 노드의 다음 노드로 연결한다. (*cur의 오른쪽 노드와 새 노드의 오른쪽이 연결된다.*)
3. new의 값을 cur의 next에 저장하여 삽입할 노드를 cur의 다음 노드로 연결한다.
4. cur의 값을 new의 prev 필드에 저장하여 cur을 new의 이전 노드로 연결한다.

5. new의 값을 new가 가리키는 다음 노드의 prev 필드에 저장하여 삽입하려는 노드의 다음 노드와 삽입하려는 노드를 연결한다.





삽입되는 위치에 따라 의사코드를 작성하면 다음과 같다.



* 첫 노드에 삽입(*O(1)*)

![dll add first]({{site.url}}/assets/images/dll_addhead_visualgo.png)

```
Vertex vtx = new Vertex(v)
vtx.next = head
if (head != null) head.prev = temp
head = vtx
```



* 중간 노드에 삽입(*O(N)*)

![dll add mid]({{site.url}}/assets/images/dll_addmid_visualgo.png)

```
Vertex pre = head
for (k=0; k<i-1; k++)
	pre = pre.next
Vertex aft = pre.next
Vertex vtx = new Vertex(v)
vtx.next = aft, aft.prev = vtx
pre.next = vtx, vtx.prev = pre
```



* 마지막에 삽입(*O(1)*)

![dll add tail]({{site.url}}/assets/images/dll_addtail_visualgo.png)

```
Vertex vtx = new Vertex(v)
tail.next = vtx, temp.prev = tail
tail = vtx
```



#### 이중 연결 리스트 원소 삭제 연산



1. 삭제할 노드의 다음 노드 주소를 삭제할 노드의 이전 노드의 next 필드에 저장하여 링크를 연결한다.(*cur의 오른쪽 노드가 이전 노드의 오른쪽 노드와 연결된다.*)
2. 삭제할 노드의 다음 노드에 있는 prev 필드에 삭제할 노드의 이전 노드 주소를 저장하여 링크를 연결한다.(*삭제할 노드의 왼쪽 노드와 오른쪽 노드를 연결한다.*)
3. cur이 가리키는 노드에 할당된 메모리를 반환한다.



삽입되는 위치에 따라 의사코드를 작성하면 다음과 같다.



* 첫 노드 삭제(*O(1)*)

![dll del first]({{site.url}}/assets/images/dll_delhead_visualgo.png)

```
if empty, do nothing
temp = head
head = head.next
delete temp
```



* 중간 노드 삭제(*O(N)*)

![dll del mid]({{site.url}}/assets/images/dll_delmid_visualgo.png)

```
if empty, do nothing
Vertex pre = head
for (k = 0; k < i-1; k++)
	pre = pre.next
Vertex del = pre.next, aft = del.next
pre.next = aft // bypass del
delete del
```



* 마지막 노드 삭제(*O(N)*)

![dll del tail]({{site.url}}/assets/images/dll_deltail_visualgo.png)

```
if empty, do nothing
Vertex pre = head
temp = head.next
while (temp.next != null)
	pre = pre.next
pre.next = null
delete temp, tail = pre
```



### 기타

위에서 소개하지는 않았지만, 연결 리스트의 또 다른 종류로 원형 연결 리스트가 있다.

![circular]({{site.url}}/assets/images/circularlinkedlist.png)

마지막 노드가 첫 노드와 연결되어 있는 구조로, 단순 연결 리스트의 마지막 노드가 `None`을 가리켰던 것과 달리, 원형 연결 리스트의 마지막 노드는 Head를 가리키게 된다.



한편, 맨 앞에 dummy를 두는 dummy linked list도 있다. 실제 데이터를 지닌 노드가 아니라, 구현의 편의를 위해 맨 앞에 두는 무의미한 노드이다. 맨 앞에 dummy를 두기 때문에, 구현하는 데 있어 if문의 양을 줄일 수 있다. 





# 구현

연결 리스트를 구현하는 데 있어서 가장 중요한 것은 **연결이 무엇인지 파악**하는 것이다.





## 단순 연결 리스트



Node 클래스를 선언한 후, SinglyLinkedList 클래스를 선언한다.



* Node 클래스 선언

```python
class Node(object):
    def __init__(self, data):
        self.data = data
        self.next = None
      
```

* Singly linked list 클래스 선언

```python
class SinglyLinkedList:
    # head 생성자
    def __init__(self):
        self.head = None
    
    # 맨 앞에 원소 삽입
    def push(self, new_data):
        new_node = Node(new_data) # 새로운 노드를 만들고 값을 저장
        new_node.next = self.head # 새로운 노드의 다음 노드를 head로 지정.
        self.head = new_node
        
    # 중간에 원소 삽입
    def add(self, prev_node, new_data):
        
        # 앞 노드가 존재하는지 확인
        if prev_node is None:
            print("head 노드가 없습니다.")
            return
      
        new_node = Node(new_data) # 새로운 노드 생성 후 삽입할 데이터 저장
        new_node.next = prev_node.next # 새로운 노드의 링크 필드를 이전 노드의 링크 필드로 지정
        prev_node.next = new_node # 이전 노드의 링크 필드를 새로운 노드로 지정
    
    def append(self, new_data):
        
        # 새로운 노드를 만들고, 삽입할 데이터를 저장한 뒤, 링크 필드를 None으로 지정.
        new_node = Node(new_data)
        
        # 리스트가 비어 있는지 확인
        if self.head is None:
            self.head = new_node # 비어 있으면 헤드 생성
            return
        
        # 리스트가 비어 있지 않다면, 마지막 노드까지 순회
        last = self.head
        while (last.next):
            last = last.next
        # 마지막 노드의 다음 노드를 새로운 노드로 지정.
        last.next = new_node
        
    def deleteNode(self, key):
        
        cur = self.head # head 노드 저장.
        
        # head가 있어야, 즉, 리스트가 비어 있지 않아야 지울 수 있음.
        if (cur is not None):
            if (cur.data == key):   # head 노드를 지울 경우
                self.head = cur.next
                cur = None # cur을 없앤다.
                return
            
            while (cur is not None):
                if cur.data == key: # 지울 데이터가 나오면 반복 중지
                    break
                prev = cur
                cur = cur.next # 지울 키를 찾을 때까지 순회
        
        # 지울 데이터를 찾지 못했다면
        if (cur == None):
            return
        
        # 이전 데이터의 다음을 cur의 다음으로 연결하고, cur을 없애서 삭제 구현.
        prev.next = cur.next
        temp = None
    
    # list 출력
    def printList(self):
        cur = self.head
        while(cur):
            print("%d" %(temp.data))
            temp = temp.next
```

``` python

```

## 이중 연결 리스트 구현 예

```python
class Node:
    def __init__(self, data):
        self.data = data
        self.next = None
        self.prev = None
       
class DoublyLinkedList:
  
    def __init__(self):
        self.head = None

    def push(self, new_data):
        new_node = Node(new_data)
        new_node.next = self.head
        if self.head is not None:
            self.head.prev = new_node
        self.head = new_node
        
	def add(self, prev_node, new_data):
        if prev_node is None:
            print("head 노드가 없습니다.")
            return
        new_node = Node(new_data)
        new_node.next = prev_node.next
        prev_node.next = new_node
        new_node.prev = prev_node
        if new_node.next is not None:
            new_node.next.prev = new_node
    
    def append(self, new_data):        
        new_node = Node(new_data)    
        new_node.next = None
        if self.head is None:
            new_node.prev = None
            self.head = new_node
            return      
        last = self.head
        while (last.next):
            last = last.next
        last.next = new_node
        new_node.prev = last
        return
        
    def deleteNode(self, key):
        
        if self.head is None or key is None:
            print("삭제할 수 없습니다.")
            return
        
        if self.head.next is None:
            if self.head.data == key:
                self.head = self.head.next
                self.head.prev = None
                return
        
        while self.head.next is not None:
            if self.head.data == key:
                break
            self.head = self.head.next
            
        if self.head.next is not None:
            self.head.prev.next = self.head.next
            self.head.next.prev = self.head.prev
        else:
            if self.head.data == key:
                self.head.next.next = None
            else:
                print("찾을 수 없습니다.")
                
        
    def printList(self):
        cur = self.head
        while(cur):
            print("%d" %(temp.data))
            temp = temp.next
```





## dummy linked list 구현 예

```python
class Node:
    def __init__(self, data):
        self.data = data
        self.next = None

class LinkedList:
    def __init__(self):
        dummy = Node("dummy")
        self.head = dummy
        self.tail = dummy
        self.cur = None
        self.before = None
        self.num_of_data = 0
    
    def append(self, new_data):
        new_node = Node(new_data)
        self.tail.next = new_node
        self.tail = new_node
        self.num_of_data += 1
    
    def pop(self):
        pop_data = self.current.data
        if self.cur is self.tail:
            self.tail = self.before
        self.before.next = self.cur.next
        self.cur = self.before # current가 before로 변경.
        self.num_of_data -= 1
        return pop_data
    
    def first_search(self):
        if self.num_of_data == 0:
            return None
        self.before = self.head
        self.current = self.head.next
        return self.current.data
    
    def next_search(self):
        if self.cur.next == None:
            return None
        self.before = self.current
        self.current = self.current.next
        return self.cur.data
    
    def size(self):
        return self.num_of_data
```








