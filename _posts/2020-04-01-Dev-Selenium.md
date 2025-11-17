---
title:  "[Crawling] Selenium"
excerpt : "웹 크롤링을 위해 알아 본 파이썬에서의 Selenium 사용법"
toc: true
toc_sticky: true
header:
  teaser: /assets/images/blog-Dev.jpg
categories:
  - Dev
tags:
  - Python
  - Crawling
  - Scraping
  - Selenium
last_modified_at: 2020-03-11
---







# _"Selenium"_



> *"Selenium is an umbrella project for a range of tools and libraries that enable and support the automation of web browsers."*																			
>
> ​																											*_출처 : selenium.dev/documentation/en/*



 Selenium은 **웹 브라우저를 컨트롤하여 웹 UI를 자동화하는 도구** 중 하나이다. 자동화라 함은, 브라우저가 웹사이트를 불러오고, 필요한 데이터를 가져 오고, 로그인을 하거나 스크린샷을 찍는 등 *특정 행동*이 웹사이트에서 일어난다고 가정하고 *이 과정을 자동화*한다는 것이다. 

 Selenium은 프레임워크일 뿐, 웹사이트에 접근하기 위해서는 웹 브라우저를 대신할 웹 드라이버가 필요하다. 즉, Selenium은 웹 드라이버를 이용해 웹 어플리케이션에 접근하여 여러 동작을 수행하는 것이다.

 Selenium은 원래 웹사이트를 테스트하는 목적으로 개발되었다. 그러나 그 강력함 때문에, 웹 스크레이핑 도구로서 자주 사용된다.

 특히 `requests.text`를 이용하게 되면 불러올 수 없는 데이터가 있다. 예컨대 뉴스 기사나 커뮤니티의 댓글이라든지, SNS 게시물 등 실시간 혹은 사용자의 입력 및 게시에 따라 동적으로 변화하는 것들이 그것이다. 이 경우 requests 모듈을 사용하게 되면 페이지의 **껍데기** 소스만 불러오게 되며, HTML 문서를 파싱한 뒤에도 정작 필요로 하는 데이터들은 *눈을 아무리 크게 뜨더라도* 찾아볼 수 없게 된다.

<br>



## 1. Basics



### Webdriver 설정

 Selenium에서 사용할 수 있는 `Webdriver`는 `Chrome`, `Firefox`, `Internet Explorer`, `Opera`, `Safari`가 있다. 나는 Chrome Webdriver를 사용한다. 크롬 브라우저 버전에 맞게 설치하면 된다.

 설치가 완료되고, 웹 드라이버를 사용하기 위해서는 웹 드라이버 객체를 생성하면 된다. 이 때, 필수적으로 웹 드라이버가 **설치된 경로**를 명시해야 한다.

```python
from selenium import webdriver

driver = webdriver.Chrome('설치 경로')
```



### 2Webdriver Options

  

 웹 드라이버를 사용하면서 필요한 셋팅 옵션을 설정할 수 있다. Options 모듈을 추가한 뒤, 원하는 옵션을 지정하면 된다. 다음과 같이 사용한다. 크롬 드라이버이기 때문에, `chrome_options`라는 인자에 옵션을 넘겨 준다.

```python
from selenium import webdriver
from selenium.webdriver.chrome.options import Options

options = Options()

# 추가하고 싶은 옵션
options.add_argument('옵션')

# 드라이버 설정
driver = webdriver(chrome_options = options, executable_path='설치 경로')
```

  주로 사용할 수 있는 옵션은 다음과 같다.

* `user-agent` : 사용자 에이전트 값을 지정할 수 있다.
  * 웹사이트에서 대규모로 데이터를 긁어오는 시스템을 방지할 수 있다. 이 경우 가장 먼저 시도하는 방법이 `user-agent` 옵션을 주는 것이다. (*최대한 사람인 척 하기 위해...*)
  * 좋은 방법인지는 모르겠으나, `fake-useragent`를 사용할 수도 있다고 한다. 이 방법은 나중에.

* `headless` : 브라우저를 렌더링하지 않고, 메모리 상에서만 작업이 이루어지도록 한다. 즉, GUI 없이 웹드라이버를 사용한다.

* `window-size` : 크롬 창의 크기를 바꾼다. 주로 사용하는 모니터의 크기가 1920x1080이기 때문에, 특별한 경우가 아니라면, `window-size = 1920x1080` 옵션을 주면 모니터에 보이는 크기대로 드라이버가 작동한다.
* `--disable-gpu` : GPU를 통한 그래픽 가속을 사용하지 않는다. 크롬 브라우저에서 GPU 사용으로 인해 나타나는 버그 문제를 해결할 때 주로 사용한다.
* `--disable-dev-shm-usage`
* `--no-sandbox`








## 2. Locating Elements

 드라이버가 직접 웹 소스에서 element들을 찾아 반환한다.



### 각 element에 따라 다른 메서드 사용



 일치하는 요소들 중 첫 번째 element만을 반환하는 메서드는 다음과 같다.

* `find_element_by_id` : 'id' 속성으로 찾는다.
* `find_element_by_name` : 'name' 속성으로 찾는다.
* `find_element_by_class_name` : 'class' 속성으로 찾는다.
* `find_element_by_xpath` : xpath(XML 노드의 위치를 찾는 언어)로 접근해서 찾는다.
* `find_element_by_link_text` : 링크 텍스트로 찾는다. 주로 `href` 속성이 있는 anchor(`a`) 태그에서 태그가 가진 텍스트로 찾는다.
* `find_element_by_partial_link_text` : 링크 텍스트가 부분적으로 일치하는 태그를 찾는다.

```html
<html>
    <head>
        <title> find by Links </title>
    </head>
    <body>
        <a href="https://sirzzang.github.io"> come </a>
        <br>
        <a href="https://projectlog-eraser.tistory.com"> click </a>
    </body>
</html>
```

```python
from selenium import webdriver

driver = webdriver.Chrome('설치 경로')
driver.find_element_by_link_text("click") # 두 번째 태그를 찾는다.
driver.find_element_by_partial_link_text("com") # 첫 번째 태그를 찾는다.
```

* `find_element_by_tag_name` : 태그의 이름으로 찾는다.
* `find_element_by_css_selector` : CSS 선택자 문법으로 찾는다.



 **복수의 elements**를 모두 반환하기 위해서는, 위의 메서드에서 `element`만 `elements`로 바꾸면 된다.



### By 사용

 **By** 모듈을 추가하면, 각 요소마다 다른 메서드를 쓰지 않고도 `find_element(By.속성, '속성 값')`으로 간편하게 찾을 수 있다. 이 때, 속성은 *대문자*로 지정한다.

```python
from selenium.webdriver.common.by import By

driver.find_element(By.'속성', '속성 값')
```



 사용할 수 있는 속성은 다음과 같다.

* ID
* XPATH
* LINK_TEXT
* PARTIAL_LINK_TEXT
* NAME
* TAG_NAME
* CLASS_NAME
* CSS_SELECTOR





## 3. Wait

 브라우저 드라이버가 웹에서 데이터를 받아올 수 있도록 *충분히* 기다려야 한다. 로딩이 끝날 때까지 기다리지 않는다면, 껍데기만 전송되어 온(`requests.text`가 받은 것과 별반 다를 것 없는) HTML 소스를 보게 된다.

 만약, 동적으로 HTML 구조가 변하는 경우 충분히 기다리지 않고 element를 찾으려 한다면, `NoSuchElementException` 에러를 보게 될 것이다.

 다음의 두 가지 종류의 대기 메서드가 있다.



### Implicitly Wait

 인자로 넘겨준 시간만큼 브라우저 요소들을 기다린다.  '암묵적으로', '관용 있게' 기다리는 만큼, 지정한 시간만큼은 끝까지 기다린다.

```python
from selenium import webdriver

driver = webdriver.Chrome('설치 경로')

# 암묵적으로 기다릴 값(초 단위)을 인자로 넣는다.
driver.implicitly_wait(3)
```

 몇 초 동안 기다리는 것이 적정 값인지 알 수 없다는 문제가 있다. 



> *참고* : 내용 추가
>
>  실제로 [웹 크롤링 미니 프로젝트](https://github.com/sirzzang/LECTURE/blob/master/인공지능-자연어처리(NLP)-기반-기업-데이터-분석/프로젝트/01. 크롤링/[미니 프로젝트] 크롤링 프로젝트 리뷰.md){: .btn .btn--danger .btn--small}를 진행했을 때, 옆 반에서 `implicitly_wait`으로 1000을 설정한 분이 계셨다. 진짜로 기다린다고 한다(…).



### Explicitly Wait

 특정 상태가 될 때까지 기다리고, 상태가 되면 바로 실행한다.  이 방법을 쓰기 위해서는 **예상 조건**(expected condition)에 대한 이해가 필요하다. *어떠한 동작을 한 후, 혹은 웹 요소가 로딩되었을 때의 상태*를 예상 조건이라고 한다. 다음과 같은 상황을 예로 들 수 있다.

> * 알림 박스가 나타난다.
>
> * 텍스트 박스가 선택 상태로 바뀐다.
>
> * 페이지 타이틀이 바뀐다.
>
> * ''다음' 버튼이 나타난다/ 더 이상 존재하지 않는다.
>
>   ...

 이 경우에 기대되는 상태에서 수행할 수 있는 행동, 찾을 수 있는 요소 등을 expected condition으로 정의하고, `expected_conditions`를 import하여 사용할 수 있다. 이 때, `expected_conditions`의 alias로는 `EC`를 주로 사용한다. EC 상태는 [documentation](https://www.selenium.dev/selenium/docs/api/py/webdriver_support/selenium.webdriver.support.expected_conditions.html?highlight=expected_conditions#selenium.webdriver.support.expected_conditions)을 참고하면 알 수 있다.

 이후 명시적으로 대기하도록 `WebDriver Wait`을 사용할 수 있다. 사용 예시는 다음과 같다.

```python
from selenium import webdriver
from selenium.webdriver.support.ui import WebDriverWait # 명시적 대기
from selenium.webdriver.suppor import expected_conditions as EC

driver = webdriver.Chrome('설치 경로')

wait = WebDriverWait(driver, 10) # 10초 동안 기다린다
# 특정 class 이름을 가진 요소가 로드되어 클릭할 수 있을 때까지 지정된 시간을 기다린다.
element = wait.until(EC.element_to_be_clickable((By.CLASS_NAME, 'class_name'))) 
# CSS 선택자로 특정 요소를 찾을 수 있을 때까지 지정된 시간을 기다린다.
element2 = wait.until(EC.presence_of_element_located((BY.CSS_SELECTOR, 'CSS')))
```



**time.sleep과의 [차이](https://www.a-ha.io/questions/4d1c8589dcb22246af4a4d4960834bcf)**

 대기하는 것으로 `time.sleep`을 사용할 수도 있다. 이 메서드도 일정 시간 동안 대기하는 것은 마찬가지이지만, 이것은 **코드의 수행 자체를** 일정 시간 동안 멈추는 메서드이다. `implicitly_wait`이나 `WebdriverWait`은  Selenium의 웹 드라이버에만 특화된 메서드라고 보면 된다.



## 4. 웹 사이트 자동 조작



### 동작

* `element.click()` : element를 클릭한다.
* `element.double_click()` : element를 더블 클릭한다.

 클릭 메서드를 사용한 예시 코드는 다음과 같다. 네이버 뉴스 댓글 창에서 `더보기` 버튼이 나오지 않을 때까지 계속해서 클릭한다. 이 코드에서는 로드될 때까지 기다리기 위해 `time.sleep` 메서드를 사용했다.

```python
from selenium import webdriver
import time

driver = webdriver.Chrome('설치 경로')

while True:
        try:
            more_comments = driver.find_element_by_css_selector('a.u_cbox_btn_more')
            more_comments.click()
            time.sleep(0.3)
        except:
            break
```

* `element.send_keys()` : 특정 element에 키보드를 입력하고 전송할 때 사용한다. 

* `element.move_to_element()` : 특정 element로 마우스를 이동한다.



### 동작을 묶어서 실행

* `ActionChains()` : 행동  여러 개를 체인으로 묶어서 실행한다.
* `perform()` : 전체 행동을 실행한다.

```python
from selenium import webdriver
from selenium.webdriver.common.keys import Keys
from selenium.webdriver import ActionChains

driver = webdriver.Chrome('설치 경로')
driver.get("http://some.url.address")

first_element = driver.find_element_by_name("some_name")
second_element = driver.find_element_by_id("some_id")
submitButton = driver.find_element_by_id("submit")

actions = ActionChains(driver).click(first_element).send_keys("some string").click(second_element).send_keys("some string").send_keys(Keys.RETURN)
actions.perform()
```





## 5. 기타



### Keys 모듈

 element를 찾아서 특정 동작을 할 때 오류가 날 수 있다. 이 때 키보드의 여러 키들을 객체로서 사용할 수 있도록 한다. 다 적지는 못하고, [documentation](https://www.selenium.dev/selenium/docs/api/py/webdriver/selenium.webdriver.common.keys.html)을 참고하자.



**엔터 키로 클릭**

 다음은 특정 요소를 찾아 엔터 키를 눌러서 클릭을 대체하는 예시 코드이다.

```python
from selenium import webdriver
from selenium.webdriver.common.keys import Keys

driver = webdriver.Chrome('설치 경로')
element = driver.find_element_by_id('some id')
element.send_keys(Keys.ENTER)
```



**마지막 페이지까지 스크롤 다운**

 `return document.body.scrollHeight`로 전체 페이지의 스크롤 height를 반환한다([참고](https://www.w3schools.com/jsref/prop_element_scrollheight.asp)). 키보드의 END 키를 이용하여 스크롤 다운한다. ([참고](https://stackoverflow.com/questions/51690101/why-execute-scriptreturn-document-body-scrollheight-with-python-selenium-ret/51702698) : 유튜브와 같은 사이트에서는 작동하지 않을 수도 있으므로 `scrollHeight` 객체 선택 시 다른 방법 사용.)

```python
(...)
    while True:
        height = driver.execute_script("return document.body.scrollHeight")
        time.sleep(wait_time)
        driver.find_element_by_tag_name('body').send_keys(Keys.END)
```



```python
# 유튜브 사이트 크롤링 시 사용한 코드
def get_page(wd, url, wait_time=1):
    wd.get(url)
    while True:
        height = driver.execute_script("return document.body.scrollHeight")
        time.sleep(wait_time)
        driver.find_element_by_tag_name('body').send_keys(Keys.END)
        try:
            bottom = driver.find_element_by_class_name('style-scope ytd-message-renderer')
        except:
            continue
        if bottom is not None:
            break

    html = wd.page_source
    wd.quit()
    return html
```





### Colab에서 Selenium 사용하기

* 크롬 브라우저 최신 확인.
* 우분투 업데이트 필수.

```python
# 크롬 드라이버 설치
!apt-get update # 우분투 환경 업데이트
!wget https://chromedriver.storage.googleapis.com/83.0.4103.39/chromedriver_linux64.zip  && unzip chromedriver_linux64
!apt install chromium-chromedriver
!pip install selenium

# driver 설정
chrome_options = Options()
chrome_options.add_argument('--headless')
chrome_options.add_argument('--no-sandbox')
chrome_options.add_argument('--disable-dev-shm-usage')
driver = webdriver.Chrome("/usr/bin/chromedriver", options=chrome_options)
```



### 팁

* 항상 `driver.close()`나 `driver.quit()`을 해주자. 코드에서 빼먹으면, 계속해서 브라우저가 나타나는 불상사를(...) 겪게 된다. 시도해보지는 않았지만, `headless` 옵션을 줘도 될 것 같기는 하다.
* 필요로 하는 요소를 다 찾은 후라면, 혹은 데이터가 다 전송되었다는 것을 확인한 후라면, `BeautifulSoup`을 이용해 `driver.page_source`를 파싱하여 사용하자. 웹 드라이버로 모든 요소를 다 찾으려고 하면, 속도가 상당히 느리다.