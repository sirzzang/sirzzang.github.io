---
title: "[Programmers] 마법의 엘리베이터"
excerpt: 그리디, 완전 탐색, DFS, 백트래킹
header:
  teaser: /assets/images/blog-Programming.jpg
toc: true
categories:
  - Programming
tags:
  - Go
  - Programmers
  - 그리디
---



# 문제

출처: https://school.programmers.co.kr/learn/courses/30/lessons/148653



<br>



# 풀이



```go
func solution(storey int) int {
    
    answer := 0
    
    // 그리디하게 탐색
    for {
        if storey == 0 {
            break
        }
        
        r := storey % 10
        storey /= 10
        
        if r > 5 { 
            // 6층 이상일 때 올라가야 함
            answer += (10 - r)
            storey += 1
        } else if r == 5 && (storey % 10 >= 5) {
            // 5층이면서 올라갔을 때 5층 이상에 가는 경우 올라가야 함
            answer += (10 - r)
            storey += 1
        } else {
            answer += r
        }
    }
    return answer
}
```



<br>

# 다른 사람의 풀이



출처: https://school.programmers.co.kr/learn/courses/30/lessons/148653/solution_groups?language=python3 Magenta195

```python
def solution(storey):
    if storey < 10 :
        return min(storey, 11 - storey)
    left = storey % 10
    return min(left + solution(storey // 10), 10 - left + solution(storey // 10 + 1))
```

