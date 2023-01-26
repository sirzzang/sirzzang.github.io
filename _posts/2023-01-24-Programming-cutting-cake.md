---
title: "[Programmers] 롤케이크 자르기"
excerpt: "문자열, groupby, counter"
header:
  teaser: /assets/images/blog-Programming.jpg
toc: true
categories:
  - Programming
tags:
  - Go
  - Programmers
  - 탐색
  - 해시
  - DP
---



# 문제

출처: https://school.programmers.co.kr/learn/courses/30/lessons/132265



<br>



# 풀이

 롤케이크의 길이가 최대 100만이므로, 완전 탐색을 이용해 앞에서부터 잘라 가며 각자가 가진 토핑이 몇 개인지 체크하고자 할 경우 시간 초과가 발생한다. O(n^2)의 시간 복잡도를 갖는다.

 O(n)으로 반복할 수 있도록 하며 경우의 수를 탐색한다.

- 한 사람이 토핑을 전부 가질 때 전체 토핑이 몇 개인지, 토핑 별로 몇 개를 가지는지 체크
- 롤케이크(`topping`)를 앞에서 부터 잘라 가며, 한 사람이 모든 토핑을 가지고 있을 때의 경우에서 나눠 주도록 함
- 나눠 주는 과정에서 두 사람이 가진 토핑 개수의 합이 같아지면, 체크

```go
package main

func solution(topping []int) int {
    
    answer := 0
    
    // 한 사람이 모든 토핑을 가질 때 토핑 별 개수
    allToppings := make(map[int]int)    
    for _, v := range(topping) {
        allToppings[v] += 1
    }
    
    // 한 사람이 가진 모든 토핑의 수
    cnt := len(allToppings)   
    
    // 앞에서부터 잘라 가며 나눠 가질 수 있는 토핑 경우의 수 체크
    splitToppings := make(map[int]int)
    for _, v := range(topping) {
        allToppings[v] -= 1
        if (allToppings[v] == 0) {
            cnt -= 1
        }
        splitToppings[v] += 1
        
        // 두 사람이 가진 토핑의 수가 동일한지 확인
        if cnt == len(splitToppings) {
            answer += 1
        }
    }

    return answer
}
```



<br>

# 다른 사람의 풀이



출처: https://school.programmers.co.kr/learn/courses/30/lessons/132265?language=python3

- 존시나 님 풀이

```go
package main

func solution(plate []int) int {
    var result int

    mine := make(map[int]int)
    bros := make(map[int]int)

    for i := range plate {
        bros[plate[i]]++
    }

    for i := range plate {
        mine[plate[i]]++
        bros[plate[i]]--
        if bros[plate[i]] <= 0 {
            delete(bros, plate[i])
        }
        if len(mine) == len(bros) {
            result++
        }
    }

    return result
}
```

- 김성수 님 풀이

```python
func solution(topping []int) int {
    answer := 0
    dp := [2][1000001]int{}
    mL := map[int]bool{}
    mR := map[int]bool{}

    for i:=0; i < len(topping); i++ {
        // L
        mL[topping[i]] = true
        dp[0][i] = len(mL)

        // R
        mR[topping[len(topping)-i-1]] = true
        dp[1][len(topping)-i-1] = len(mR)
    }

    for i:=0; i < len(topping) - 1; i++ {
        if dp[0][i] == dp[1][i + 1] {
            answer++
        }
    }

    return answer
}
```

