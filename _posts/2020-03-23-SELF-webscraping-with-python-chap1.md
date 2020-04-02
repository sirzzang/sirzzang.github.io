---
title:  "[Scraping] 파이썬으로 웹 크롤러 만들기_1"
excerpt: "단순히 데이터를 추출하는, 웹 스크레이핑의 기본."
header:
  teaser: /assets/images/webscraingwithpython.jpg
categories:
  - SELF
tags:
  - scraping
  - crawling
  - 크롤러
last_modified_at: 2020-03-21
---










# 파이썬으로 웹 크롤러 만들기

[1장](https://github.com/sirzzang/Scraping/blob/master/1부_스크레이퍼 제작.ipynb)

---



 웹 서버에 특정 페이지 콘텐츠를 요청하는 `GET` 요청을 보내고, 그 페이지의 HTML 결과를 얻어, 원하는 데이터를 뽑아낸다.

* `urllib.request`의 `urlopen` : `GET` 요청을 보내 URL을 연다.
* `bs4`의 `BeautifulSoup` : `GET` 요청을 보내 받아 온 HTML을 파싱하여 원하는 데이터를 추출한다.





## BeautifulSoup



 HTML을 파싱해 데이터를 뽑아내기 위해서는, 먼저 `BeautifulSoup` 객체를 **생성**해야 한다.  인자로는 GET 요청을 통해 받아 온 HTML 텍스트(혹은 `HTML.read()`)와 HTML 구문 분석기의 이름 문자열을 넘겨 준다.

 BeautifulSoup이 파싱한 HTML 텍스트에서 태그 객체는 원래 HTML 문서의 태그에 상응한다. `find` 메서드를 통해 태그를 찾으면, 해당하는 태그 중 첫 번째 태그만을 반환한다.



### 구문 분석기 비교

|    분석기     |  속도  | 문제 | 기타                              |
| :-----------: | :----: | :--: | :-------------------------------- |
| `html.parser` | 괜찮음 |      | 파이썬 3에 내장                   |
|    `lxml`     |  빠름  | 수정 | 따로 설치, C 언어 라이브러리 필요 |
|  `html5lib`   |  느림  | 수정 | 설치, lxml보다 더 많은 수정       |



### 페이지 구조 확인

* `bs.prettify()` 메서드 사용
* `tag.name` 메서드 사용







## 신뢰할 수 없는 연결과 예외 처리



 각 상황에서 발생할 수 있는 에러를 예상하고, 이를 처리하는 코드를 넣어야 한다. 어떠한 예외가 발생했는지 알 수 없다면 오류를 고치는 데 애를 먹게 된다. 예외 처리를 철저하게 만들어 둘수록, 빠르고 신뢰할 수 있는 스크레이퍼가 된다.



### 예외 종류

* `URLError` : 서버를 찾을 수 없는 경우
* `HTTPError` : 페이지를 찾을 수 없거나, URL 해석에서 에러가 생긴 경우
* `AttributeError` : 실제로 존재하지 않는 태그(`None` 객체 반환)에 함수를 호출하는 경우. 어떤 태그를 찾을 때 태그가 실제 있는지 확인하는 용도로 체크한다.



**예외 처리 코드 예시**

1. `URLError` : 명시하지는 않았으나, 서버가 존재하지 않을 때 접근하면 `None` 객체가 반환되므로, `AttributeError`를 일으키도록 설계.
2. `HTMLError` : 명시적으로 언급함.
3. `AttributeError` : 명시적으로 언급함. `URLError` 외에 태그가 존재하지 않는다면 해당 에러 발생.

```python
from bs4 import BeautifulSoup
from urllib.request import urlopen
from urllib.request import HTTPError

def getTitle(url):
    try: # 접속
        html = urlopen(url)
    except HTTPError as e:
        print("Error! {}".format(e))
    try: # HTML 컨텐츠 접근
        bs = BeautifulSoup(html, 'html.parser')
        title = bs.h1 # URL에 접속할 수 없으면 애초에 AttributeError 발생.
    except AttributeError as e:
        return None
    
    return title # 제대로 된 경우

title = getTitle("https://www.naver.com")
if title == None:
    print("Title을 찾을 수 없습니다.")
else:
    print(title)
```





---

# 배운 점



 HTML 소스의 전반적 패턴을 생각한다. 패턴을 통해 일어날 수 있는 예외를 최대한 많이 생각하고, 예외 처리를 쉽게 할 수 있도록 방법을 생각한다.