---
title:  "[Scraping] NomadCoders_Making Job Scrapper with Python"
excerpt:
toc: true
toc_sticky: true
header:
  teaser: /assets/images/nomad_scrapper.png
categories:
  - SELF
tags:
  - scraping
  - crawling
  - 노마드코더
last_modified_at: 2020-03-21
---





# Python으로 웹 스크래퍼 만들기

> 파일
>
> https://github.com/sirzzang/Scraping/blob/master/%5BNomadCoder%5Dmaking%20web%20scraper%20with%20Python_Indeed.ipynb
>
> https://github.com/sirzzang/Scraping/blob/master/%5BNomadCoder%5Dmaking%20web%20scraper%20with%20Python_StackOverflow.ipynb

---



### 총평

 `StackOverflow`와 `Indeed`에서 python 관련 구인 공고를 찾는 간단한 웹 스크레이퍼를 만드는 강의이다. 각 사이트에서 필요한 정보를 추출하고, 이를 `csv` 파일로 만들 수 있다. 짧은 강의임에도 





### 배운 점

 웹 페이지에 요청을 보내고, `BeautifulSoup` 라이브러리를 이용해 데이터를 추출하는 것은 이전에도 여러 번 경험했기 때문에 다시 정리하지 않는다.

 강의를 통해 가장 크게 느낀 것은 스크레이핑하는 과정을 **"함수화"**해야 한다는 것이다. 이전에 강의에서 내가 시도했던 스크레이핑은 단순히 하나의 페이지에서 정보를 추출하는 초보적인 작업일 뿐이었다.

 *구체적으로는* 다음과 같은 점을 느꼈다.

 	1. 작업의 과정을 생각하고, 그에 맞게 함수를 세분화한다.
     * URL에 요청을 보낸다. 어디까지? 검색 결과 창의 마지막 페이지까지.
       * 마지막 페이지까지 얻는 함수가 필요하다.
       * 각 페이지별로 URL에 요청을 보내는 함수가 필요하다.
     * 요청을 보낸 페이지에서 `BeautifulSoup` 객체를 만들고, 정보를 추출하는 함수가 필요하다.

2. **구조**를 파악하는 것이 먼저다.
   * URL의 경우라면, 필요 없는 부분은 무엇인지, 페이지가 바뀔 때 어떤 부분이 변화하는지 파악하자. 변하는 부분은 함수에서 **변수**로 받아 처리하자.
   * html 페이지에서는 어떻게 태그를 찾을 수 있는지 꼼꼼히 살펴야 한다. 또한, 태그가 시간에 따라 변화하지 않았는지 확인한다.
3. 함수를 만들 때는 밑에서부터, 단계별로, **항상 확인 *또* 확인**한다.
   * 밑단에 `main.py`에서 실행할 `main()` 함수를 만든다.
   * `main()` 함수 안에 단계별로 호출되어야 할 함수를 만들고 `pass` 나 `return []` 등의 방법을 통해 단계별로 함수가 잘 동작하는지 확인하는 과정을 거친다.
   * 각각의 작은 함수를 설계할 때에도 `print()`를 통해 제대로 동작하는지 확인한다.
   * 확인 후 마지막에 코드를 정리한다.
4. 여러 페이지에서 비슷한 구조의 태그를 사용하는 경우, 하나의 함수로 스크레이핑하는 방법을 고민한다.
5. `main.py`에서는 함수를 import하고, 스크레이핑하는 역할만 한다. 나는 `Jupyter Notebook`을 사용해서 import까지는 하지 않고, 다른 셀에 진행했다.
6. `csv` 파일로 저장하는 것도 함수로 만들어야 한다.
   * `csv` 파일 열기 옵션
     * `r` : 읽기 모드. 디폴트. 파일 없으면 에러.
     * `r+` : 읽기 또는 쓰기 모드. 파일 없으면 에러. 기존 데이터를 그대로 두고 이후부터 쓰기 작업 수행.
     * `w` : 쓰기 모드. 파일 없으면 생성.
     * `w+` : 읽기 또는 쓰기 모드. 파일 없으면 생성. 기존의 데이터를 완전히 지워버리고 새로 쓰기 때문에 주의.
     * `a` : 파일 추가(FP가 파일의 끝으로 이동)로 쓰기 모드. 파일 없으면 생성.
     * `a+` : 읽기 또는 파일 추가 모드. 파일 없으면 생성.
     * `t` : 텍스트 모드로 파일 열기, `b` : 바이너리 모드로 파일 열기.
   * `csv` 모듈에서는 파일이 바뀌더라도 에러를 내지 않으므로 주의해야 한다. `Indeed` 파일에 `StackOverflow`가 덧씌워진 줄도 모르고 한참 동안 심각하게 오류를 찾았다(...)







### 체크할 사항

1. `StackOverflow` 태그 구조가 강의에서와 달리 바뀌었다.

2. 강의에서는 `if ~ is None`을 사용해 태그가 없는 부분을 확인한다. 내 코드에서는 한 군데를 변형해 `try, except` 문을 사용했다.

   * 태그가 없다면 다음 단계에서 `.text` 등의 메서드를 사용할 때 `AttributeError`가 발생한다.
   * 이를 이용해 `except` 절에서 `AttributeError`를 처리하도록 했다.

   

```python

```

### 꼭 기억하고 싶은 코드 리뷰



* `main.py` : 모든 함수를 한 번에 실행한다.
  * `indeed.py`에서 get_jobs 함수를,
  * `so.py`에서 get_jobs 함수를 가져 온다.

```python
from indeed import get_jobs as get_indeed_jobs
from so import get_jobs as get_so_jobs
from save import save_to_file

indeed_jobs = get_indeed_jobs()
so_jobs = get_so_jobs()

jobs = indeed_jobs + so_jobs
save_to_file(jobs)

```

* `get_jobs()` 함수는 `get_last_page()` 함수와 `extract_jobs()`를 호출한다.

```python
def get_jobs():
    last_page = get_last_page()
    jobs = extract_jobs(last_page)
    return jobs
```



* `extract_jobs()` 함수는 마지막 페이지까지 요청을 보내고, 각 페이지별로 `BeautifulSoup` 객체를 만들어 `extract_job()` 함수를 호출한다.

```python
def extract_jobs(last_page):
    jobs = []
    for page in range(last_page):
        print(f"Scrapping page {page+1}") # 확인용.
        req = requests.get(f"{URL}&pg={page+1}")
        soup = BeautifulSoup(req.text, 'lxml')
        results = soup.find_all("div", {"class":"-job"})
        for result in results:
            job = extract_job(result) # 위의 함수로 result 넘김!
            jobs.append(job)   
    return jobs

```

