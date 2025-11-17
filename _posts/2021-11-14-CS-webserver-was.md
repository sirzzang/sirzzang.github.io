---
title:  "[Backend] 웹 서버, CGI, 웹 어플리케이션 서버"
excerpt: 웹 서비스에서 클라이언트의 요청을 처리하기 위한 기술의 변화
categories:
  - CS
toc: true
header:
  teaser: /assets/images/blog-Dev.jpg
tags:
  - 웹 서버
  - 웹 어플리케이션 서버
  - CGI
  - 요청 처리
  - Backend
---



 백엔드 개발을 하면서 가장 많이 접하면서도 이해하기 어려웠던 용어가 '서버'였다. 클라이언트에게 정보나 서비스를 제공(*serve*)하는 프로그램이라는 것에서 나아가, 회사에서 웹 개발을 경험하며 접했던 웹 서버, 웹 어플리케이션 서버 등의 개념을 어떻게 이해하면 좋을지 고민한 결과를 정리해 보고자 한다.

> 사실 서버는 소프트웨어로서의 프로그램과 하드웨어로서의 장치를 모두 의미하는데, 여기서는 전자의 개념에 한정한다.

<br>

# 웹 서비스 개요 

 클라이언트 서버 모델 구조를 따르는 웹 서비스에서, 클라이언트와 서버는 각각 다음의 역할을 담당한다.

- 클라이언트: 서버에 주소(url)를 가지고, 통신 규칙(HTTP)에 맞게 웹 페이지(html)를 요청(Request)
- 서버: 클라이언트의 요청에 맞는 웹 페이지(html)를 응답(Response)

<br>

 결과적으로 웹 서비스에서 서버는 **클라이언트의 요청을 처리**하는 역할을 담당하는데, 이 때 요청을 처리하는 것이란 **클라이언트의 요청을 받고, 분석해, 그에 맞는 웹 페이지를 응답으로 돌려주는 과정 혹은 작업**을 의미한다. 즉, 웹 서비스에서 서버는 클라이언트의 요청을 처리하는 작업을 하는 것이다. 따라서 웹 서비스의 백엔드에서 등장하는 다양한 개념 역시, 클라이언트의 요청을 처리하는 관점에서 서버 쪽 기술이 어떻게 발전해왔는지의 측면에서 살펴 볼 필요가 있다. 

<br>

 본격적으로 위의 기술들을 살펴 보기에 앞서, 사용자의 요청을 다음과 같이 구분하고자 한다.

* 정적 요청: 정적 페이지를 반환하는 요청
* 동적 요청: 동적 페이지를 반환하는 요청

 이유는 간단하다. 각 요청에 따라 처리 과정이 달라지기 때문이다. 클라이언트의 요청이 웹 서비스의 시작점이기 때문에, 모든 사용자가 동일한 페이지를 보게 되는 정적 페이지와, 사용자별로 다른 다른 페이지를 보게 되는 동적 페이지에 대해 서버가 수행해야 할 작업이 달라지게 될 것은 자명하다.

 따라서 앞으로 이루어질 논의에서는 사용자의 요청을 어떻게 처리하는지의 관점에서 웹 서버, 웹 어플리케이션 서버의 개념을 알아 보도록 한다.



<br>

# 정적 요청 처리: 웹 서버

![web-server]({{site.url}}/assets/images/web-server.jpg){: .align-center}

<center><sup>그림 출처: https://opentutorials.org/course/3084/18890</sup></center>

 사용자 모두에게 동일한 페이지를 반환하면 되는 정적 요청 처리 과정은 다음과 같다.

* 클라이언트에게 HTTP 요청을 받고,
* 요청을 분석해서,
* 서버는 요청에 맞는 페이지를 파일 시스템에서 **찾아서**,
* 클라이언트에게 HTTP 응답으로 반환한다.

<br>

 웹 서버란, 위와 같은 역할을 담당해 정적 요청을 처리하는 서버이다. 다시 말해, **웹 서버는 클라이언트의 HTTP 요청을 받아 들이고, 요청에 맞는 파일을 반환하는 서버**라는 것이다. 이 때 웹 서버가 반환하는 파일의 종류는 웹 페이지(HTML) 뿐만 아니라, 사진, 비디오 등이 될 수 있다. 주로 다음과 같은 기능을 한다.

* HTTP 요청 및 응답 핸들링
* 통신
* (정적) 컨텐츠 제공

 초창기 웹 서비스에서 html, css, js 파일 등을 가지고 있고, 사용자의 요청이 들어 오면 요청에 맞는 페이지를 그대로 반환해 주던 서버이다. 서버에 저장되어 있는 파일을 가공하지 않는다는 사실이 중요하다.

 사실 단순히 위에서 언급한 기능 외에도 로드 밸런싱, 프록시, 리버스 프록시 등의 기능을 하는데, 이들에 대해서는 나중에 더 자세히 알아보도록 한다. 주요 제품으로는 Apache HTTTPd, nginx, Tmax WebtoB 등이 있다.

<br>

# 동적 요청 처리: CGI, WAS

 동적 요청의 경우, 정적 페이지와 달리 클라이언트별로 다른 페이지를 반환해 주어야 한다. 즉, 동적 요청을 처리하는 과정은 다음과 같다.

* 클라이언트에게 HTTP 요청을 받고,
* 요청을 분석해서,
* 클라이언트 별로 요청에 맞는 페이지를 **만들어서**,
* 클라이언트에게 HTTP 응답으로 반환한다.

<br>

![web-server-2]({{site.url}}/assets/images/web-server-2.jpg)

 이 때, 클라이언트 별로 요청에 맞는 페이지를 만들기 위한 과정은 웹 서버나 HTML로는 할 수 없다. 클라이언트 별로 다른 페이지를 반환하기 위해서는 클라이언트에 대한 데이터를 조회하고, 그에 맞게 데이터를 가공하는(*더 나아가 그 데이터를 이용해 페이지를 만드는*) 과정이 필요하다.

 그러나 웹 서버는 이미 만들어져 있는 페이지를 반환하는 역할만 할 뿐이고, HTML은 프로그래밍 언어가 아니기 때문에, 위와 같은 역할을 할 수 없다.

<br>

## CGI

![cgi-concept]({{site.url}}/assets/images/cgi-1.jpg)

 위와 같이 동적 요청을 처리하기 위해, 웹 서버가 또 다른 프로그램을 실행할 수 있다. 웹 서버만으로 동적 요청을 처리할 수 없으니, 웹 서버가 DB 접속, 데이터 가공, 로직 처리 등을 수행하는 프로그램을 실행하는 것이다.

 이 때 해당 프로그램의 입출력은 다음과 같다.

* 입력: 사용자 별로 다른 페이지를 반환하기 위해 필요한 정보
* 출력: 사용자 별로 반환해 줄 페이지

<br>

 사실 이렇게 사용자 별로 다른 페이지를 만들어 주기 위한 프로그램의 경우, 말 그대로 *프로그램*이기 때문에, 어떤 언어로든, 어떤 방식으로든 작성되어도 상관이 없다. 다만, 이런 상황에서 늘 그렇듯, 규약이 생겨나게 된다. 서버 프로그램에서 다른 프로그램을 불러 내고, 그 처리 결과를 클라이언트에게 보내주기 위한 방법이 고안된 것이다. 

 이렇게 등장하게 된 개념이 **CGI**(*Common Gateway Interface*)이다. CGI란, **웹 서버와 동적 요청을 처리하기 위한 프로그램 간 규약**(*참고: [CGI 1.1](https://datatracker.ietf.org/doc/html/rfc3875)*)으로, 다음과 같은 사항을 규정하고 있다.

* 환경변수
* 표준 입력
* 표준 출력
* 커맨드라인 인자

<br>

 즉, 위와 같은 CGI 규약을 지켜 작성된 프로그램이 CGI 프로그램이고, 웹 서버는 동적 요청이 왔을 때 CGI 프로그램을 호출하게 된다. 

 이 때, 동적인 요청이 처리되는 과정을 자세히 살펴 보면 다음과 같다.

![cgi-2]({{site.url}}/assets/images/cgi-2.png)

* 웹 서버로 동적 처리가 필요한 요청이 오면,
* 웹 서버는 CGI 스크립트가 저장되어 있는 곳에서 알맞은 **CGI 스크립트를 찾아 실행하는데**,
* 해당 CGI 프로그램은 요청에 맞는 HTML을 생성한 다음 웹 서버로 돌려 보내고,
* 웹 서버는 CGI 프로그램이 반환한 결과를 클라이언트에게 응답으로 반환하게 되는 것이다.

 하나의 물리적인 서버에서 정적인 파일을 전달하는 웹 서버와 (CGI 규약을 지켜 작성된) 호출되어 컨텐츠를 가공할 수 있는 애플리케이션이 **함께 실행*되었다는 것이 중요하다.

<br>

 이와 같은 방식으로 동적 요청을 처리하게 되면, 어떤 언어든 CGI 규약만 지킨 프로그램을 작성하면 되기 때문에, **언어 독립적**이다. 

 그러나, **많은 요청을 처리하기에 적절하지 않다**. 요청이 들어올 때마다 요청에 맞는 스크립트를 찾아 소스 코드를 컴파일하고 실행해야 하고, 요청을 처리하기 위해 프로그램을 실행하는 것 자체가 모두 각각의 프로세스이기 때문에 서버에 부하가 걸릴 수 있다. 

<br>

 이러한 단점으로 인해, CGI 방식에 대한 대안으로 다음과 같은 방식이 등장했다.

* 스크립트를 미리 C, C++로 컴파일하거나, 컴파일해 놓은 코드의 캐시를 이용
* 웹 서버에 인터프리터 엔진을 내장(Apache Httpd 웹 서버의 `mod_`로 시작하는 모듈들). 웹 서버와 애플리케이션을 따로 돌리는 것이 아니라, 웹 서버 자체가 동적 요청을 처리하기 위한 모듈을 내장하고 있는 것
* CGI 프로세스를 미리 데몬 프로세스로 띄워 놓고 요청 처리(이 경우, 웹 서버가 환경변수로 정보를 전달할 수 없어 표준 입력으로 정보를 전달한다고 한다)



<br>

## WAS

 이후 동적 요청을 처리하기 위한 웹 어플리케이션 서버(**WAS**: *Web Application Server*, 영어권에서는 주로 어플리케이션 서버)가 등장하게 되었다. 위키피디아에서는 **웹 어플리케이션과 서버 환경을 만들어 동작시키는 기능을 하는 소프트웨어 프레임워크**라고 정의한다.

<br>

 동적 요청을 처리하는 어플리케이션이 물리적으로 다른 서버(*노드*라고 이해하는 것이 더 편할 수도 있겠다)로 분리되어, **웹 서버와 다른 프로세스에서 실행**되는 것이다.

 CGI 프로그램 방식의 대안 중 CGI 프로세스를 데몬으로 띄우는 방식이 동적 요청을 처리하기 위한 애플리케이션 전용 데몬 프로세스를 띄우는 방식으로 발전한 것이라고도 한다. 이 관점에서라면, CGI 프로그램은 요청을 처리할 때마다 프로세스가 실행되는 반면, 어플리케이션 서버의 경우 어플리케이션 프로세스가 항상 실행되고 있다는 점에서 차이가 있다. 즉, **항상 실행되고 있는 프로세스**가 웹 서버로부터 요청을 받아 요청을 처리한 뒤 결과를 반환하는 것이다.

<br>

![web-application-server]({{site.url}}/assets/images/web-application-server.jpg)

 이 때 WAS에서 동적 요청이 처리되는 과정은 다음과 같다.

* 웹 서버로 동적 처리가 필요한 요청이 오면,
* 웹 서버는 웹 어플리케이션 서버에 요청 처리를 위임하고,
* 웹 어플리케이션 서버가 위임 받은 동적 요청을 처리해 웹 서버에 결과를 반환하면,
* 웹 서버는 웹 어플리케이션 서버가 반환한 결과를 사용자에게 응답으로 전달한다.

<br>

 결과적으로, 웹 어플리케이션 서버는 **웹 서버에 오는 동적 요청을 처리하고, 그 결과를 웹 서버로 반환하는 서버**라고 할 수 있다. 웹 서버 뒷단에, 동적 요청을 처리하는 서버를 하나 더 두는 것이다. 주로 다음과 같은 기능을 한다.

- DB 접속
- 트랜잭션 관리
- 데이터 가공 등 비즈니스 로직 수행



 웹 어플리케이션의 주요 제품으로는 Tmax JEUS, IBM Websphere, Redhat JBoss 등의 Java 어플리케이션 서버, .Net Framework, Zend Server(PHP 기반) 등이 있다.



<br>

 



# 결론

 그렇다면, 지금까지 등장했던 웹 서버, CGI, 웹 어플리케이션 서버 등을 어떻게 이해해야 할까. 

 일단, 모두 다 클라이언트의 요청을 처리하기 위해 등장한 기술이지만,

* 초창기 정적 페이지만으로 이루어지는 웹 서비스의 경우 웹 서버가 정적인 페이지를 반환하기만 하면 되었고, 
* 점차 웹 서비스가 발전하며 동적인 페이지를 반환할 필요성이 생겼고, 이를 위해 CGI 규약(및 그 대안들), WAS가 등장했다
  * 초창기 웹 서버는 CGI로 동적 요청을 처리했다.
  * 이후 CGI의 단점으로 인해 FastCGI, WAS 등이 등장했다.

고 이해할 수 있을 것이다.

<br>

 다만, 현대 웹 서비스의 경우 정적 요청 혹은 동적 요청 중 하나만 처리하는 경우는 거의 없다. 어떻게 보면, 이 시점에서 웹 서버와 웹 어플리케이션 서버에 대한 확실한(누가 봐도 명확하게 선을 그을 수 있다고 할 만한) 정의는 **없다**고 보는 게 맞지 않을까. 

> *참고*: [Web Server vs. Application Server ㅡ IBM](https://www.ibm.com/cloud/learn/web-server-vs-application-server)
>
> By strict definition, a web server is a common subset of an application server. A web server delivers static web content—e.g., HTML pages, files, images, video—primarily in response to hypertext transfer protocol (HTTP) requests from a web browser.
>
> An application server typically can deliver web content too, but its primary job is to enable interaction between end-user clients and server-side application code—the code representing what is often called *business logic*—to generate and deliver dynamic content, such as transaction results, decision support, or real-time analytics. The client for an application server can be the application’s own end-user UI, a web browser, or a mobile app, and the client-server interaction can occur via any number of communication protocols.
>
> **In practice, however, the line between web servers and application servers has become fuzzier, particularly as the web browser has emerged as the application client of choice and as user expectations of web applications and web application performance have grown.**
>
> (…)
>
> The bottom line is that today’s most popular web servers and application servers are hybrids of both. Most of the increasingly rich applications you use today feature a combination of static web content and dynamic application content, delivered via a combination of web server and application server technologies.

<br>

> *참고*: 어플리케이션 서버와 웹 어플리케이션 서버
>
>   위에서는 전혀 언급하지 않았지만, 웹 애플리케이션 서버를 공부하다 보면, 애플리케이션 서버라는 말도 많이 등장한다. '웹'이 앞에 붙어서 헷갈리기는 한데, 웹 어플리케이션 서버는 어플리케이션 서버라고 보는 게 맞는 듯하다. 위키피디아의 [웹 어플리케이션 서버 문서](https://ko.wikipedia.org/wiki/%EC%9B%B9_%EC%95%A0%ED%94%8C%EB%A6%AC%EC%BC%80%EC%9D%B4%EC%85%98_%EC%84%9C%EB%B2%84)를 보면, 한국에서 일반적으로 통용되는 명칭이 WAS일 뿐, 영어권에서는 어플리케이션 서버라고 부르는 것이 일반적이라고 한다. 



이 때문에, 여태까지 등장했던 개념들 중 웹 서버와 웹 어플리케이션 서버의 개념은, 어느 하나에 끼워 맞춰서 이해하기보다는 다음과 같이 **클라이언트의 요청을 처리하기 위한 3계층 구조** 중 어디에 해당하는지에 맞춰 이해하는 것이 더 맞다는 생각이 든다.

![web-3-tier]({{site.url}}/assets/images/web-3-tier.jpg)

* 웹 서버: 정적 요청 처리, 동적 요청 위임 및 결과 전달
* 웹 어플리케이션 서버: 동적 요청 처리



<br>

 사실 이러한 계층 구조로 이해할 때, 굳이 웹 서버와 웹 어플리케이션 서버가 분리되어야 하는지에 대해서 의문이 있을 수도 있다. **실제 웹 어플리케이션 서버가 웹 서버의 기능까지 할 수 있기 때문에**, 굳이 둘을 분리하지 않아도 되고 그렇게 웹 서비스를 제공해도 된다고 한다. 그러나 이러한 경우, 굳이 개념적인 문제를 떠나 모든 부하가 하나의 서버에 집중될 수 있고, 보안 상의 문제도 있기 때문에 웹 서버와 웹 어플리케이션 서버를 분리하는 것이 좋다고 한다.

<br>

 한편, 웹 어플리케이션 서버가 등장했다고 해서 CGI 방식이 쓰이지 않는 것은 아니다. Python으로 백엔드를 구축할 때는 웹 서버가 Python 어플리케이션을 쉽게 호출할 수 있도록 하는 WSGI 인터페이스를 사용한다. Python에서 사용할 수 있도록 CGI의 단점을 개선한 인터페이스라고 보면 될 듯하다. 실제 Python 웹 프레임워크(Django, Flask)는 WSGI 서버(WSGI 구현체)인 uwsgi를 내장하고 있다. 

<br>

 결론적으로, 웹 서버와 웹 어플리케이션 서버를 이해할 때는 **정적 요청과 동적 요청의 처리**, **동적 요청을 처리하기 위한 백엔드 기술의 변화**(웹 서버의 한계 → CGI의 한계 → WAS의 등장)를 기억해야 한다.