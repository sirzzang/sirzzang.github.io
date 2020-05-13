---
title:  "[Programmers] 2016년"
excerpt:
header:
  teaser: /assets/images/blog-Programming.jpg

categories:
  - Programming
tags:
  - Python
  - Programming
  - Programmers

---

> [문제 출처](https://programmers.co.kr/learn/courses/30/lessons/12901)



## 문제



2016년 1월 1일은 금요일입니다. 2016년 a월 b일은 무슨 요일일까요? 두 수 a ,b를 입력받아 2016년 a월 b일이 무슨 요일인지 리턴하는 함수, solution을 완성하세요. 요일의 이름은 일요일부터 토요일까지 각각 `SUN,MON,TUE,WED,THU,FRI,SAT`

입니다. 예를 들어 a=5, b=24라면 5월 24일은 화요일이므로 문자열 TUE를 반환하세요.



##### 제한 조건

- 2016년은 윤년입니다.
- 2016년 a월 b일은 실제로 있는 날입니다. (13월 26일이나 2월 45일같은 날짜는 주어지지 않습니다)





## 풀이 방법

* 주어진 날짜가 2016년 1월 1일로부터 며칠 후인지 계산한다. 윤년이므로, 2월이 29일임에 주의한다.
* 계산한 숫자를 7로 나누고, 그 나머지에 따라 요일을 계산한다. 금요일로부터 며칠 지났는지 따져 본다.



## 풀이 코드

```python
def solution(a, b):
    days = [31, 29, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
    yoil = ['FRI', 'SAT', 'SUN', 'MON', 'TUE', 'WED', 'THU']
    
    # 며칠 지났는지 구하기
    d = 0
    for i in range(a-1):
        d += days[i]
    d += b
    
    # 몇 번째 요일인지 구하기
    idx = d % 7 -1
    answer = yoil[idx]
    return answer
```



## 다른 풀이

[출처](https://programmers.co.kr/learn/courses/30/lessons/12901/solution_groups?language=python3)



### 풀이 1

 내 풀이와 비슷하다. 다만, 출력하는 부분에서 수식을 활용해 쉽고 알아보기 편하게 사용했다. 예전부터 항상 출력(*혹은* 결과 return) 부분에서 모든 코드를 간결하게 하는 방법을 연습하고자 하나, 잘 되지 않는다.

```python
def getDayName(a,b):
    months = [31, 29, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
    days = ['FRI', 'SAT', 'SUN', 'MON', 'TUE', 'WED', 'THU']
    return days[(sum(months[:a-1])+b-1)%7]

#아래 코드는 테스트를 위한 출력 코드입니다.
print(getDayName(5,24))
```



### 풀이 2

 사람들의 좋아요를 가장 많이 받은 재밌는 풀이이다. 말 그대로 경우를 나누었는데, 코드가 예술적이라는 폭발적인 댓글을 받았다 ㅎㅎ 코드를 길게 짜야 한다면, 예쁘고 보기 좋게 짜는 것이 좋겠다(..? ㅇㅅㅇ).

```python
def getDayName(a,b):
    answer = ""
    if a>=2:
        b+=31
        if a>=3:
            b+=29#2월
            if a>=4:
                b+=31#3월
                if a>=5:
                    b+=30#4월
                    if a>=6:
                        b+=31#5월
                        if a>=7:
                            b+=30#6월
                            if a>=8:
                                b+=31#7월
                                if a>=9:
                                    b+=31#8월
                                    if a>=10:
                                        b+=30#9월
                                        if a>=11:
                                            b+=31#10월
                                            if a==12:
                                                b+=30#11월
    b=b%7

    if b==1:answer="FRI"
    elif b==2:answer="SAT" 
    elif b==3:answer="SUN"
    elif b==4:answer="MON"
    elif b==5:answer="TUE"
    elif b==6:answer="WED"
    else:answer="THU"
    return answer


print(getDayName(5,24))
```

