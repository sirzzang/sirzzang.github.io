---
title:  "[Backend] 서블릿"
excerpt: 동적 컨텐츠를 생성하기 위한 자바 서버 측 프로그램
categories:
  - CS
toc: true
header:
  teaser: /assets/images/blog-Dev.jpg
tags:
  - 웹 어플리케이션 서버
  - Servlet
  - 요청 처리
  - JavaEE
  - Backend
---



 지난 번 WAS에 대해 공부하며 Java 진영에서의 WAS에 대해 조금 더 알아 보다가, 후속으로 **서블릿**(*Servlet*)에 대해 공부한 내용을 정리해 보고자 한다.

<br>

# Java Application Server 개요



 자바 진영에서의 WAS란, **Jakarta EE의 표준을 준수하여 구현된 웹 애플리케이션 서버**를 의미한다.

 Jakarta EE란, 자바를 이용해 서버를 개발할 수 있도록 정의한 자바 표준 명세이다. 자바의 기본적인 기능을 정의한 자바 SE에 더해, 웹 애플리케이션 서버의 동작을 위해 필요한 요청 처리, 장애 복구, 분산 멀티 티어 등을 표준화한 명세(혹은 규약)이다. 다만, 자바 기반이지만, Jakarta EE의 표준을 준수하지 않았음에도 웹 어플리케이션 서버의 일종으로 다루어지는 것들도 있다. Apache Tomcat이 대표적인 예. 

 자바 진영에서의 WAS가 지켜야 할 Jakarta EE의 주요 규약으로는 아래 그림에서와 같은 것들이 있다. 

![servlet-jakarta-ee-apis]({{site.url}}/assets/images/servlet-01.png){: .align-center width="500"}

<br>

 그 중에서도 WAS의 핵심 역할은 *동적 요청을 처리하는 것*이다. 따라서 Jakarta EE 기술 중에서도 동적 페이지에 대한 요청이 왔을 때, 요청에 맞는 페이지를 생성해 응답할 수 있도록 하는 자바 서버 측 프로그램 기술인 Servlet이 핵심이라 판단해, 이에 대해 정리해 보고자 한다. 서블릿이 요청을 처리하는 과정을 단계별로 톺아 보며, WAS의 핵심 역할인 **동적 요청 처리**가 어떻게 이루어지는지 확인해 보고자 한다.

<br>



# 서블릿



 자바 서블릿은 **자바를 사용하여 웹 페이지를 동적으로 생성하는 서버 측 프로그램 혹은 그 사양**을 의미한다. 즉, 서블릿 프로그램을 만들고 싶으면, Jakarta EE Servlet 명세에 맞게 구현체를 만들면 된다. 이름의 유래는, 서버 측에서 돌아가는 작은 어플리케이션이라는 의미로, server와 applet을 합친 것이라고 한다.

 편의상 아래 글에서는 서블릿 명세에 맞게 구현한 서블릿 프로그램을 서블릿이라 지칭하도록 하겠다. 서블릿은 추상 클래스 `javax.servlet.http.HttpServlet`을 상속해 구현한다.  

<br>

## 상속 구조



 서블릿 프로그램이 구현해야 할 클래스의 전체적인 상속 구조는 다음과 같다.

```markdown
javax.servlet.Servlet(인터페이스)
└── javax.servlet.GenericServlet(추상 클래스)
│   └── javax.servlet.http.HttpServlet(추상 클래스)
```

<br>

### javax.servlet.Servlet

 서블릿 최상위 인터페이스로, **서블릿 실행의 생명 주기**와 연관된 메소드, **서블릿 설정, 관련 정보**를 알기 위한 메소드를 정의한다. 생명 주기와 연관된 다음의 메소드들이 중요하다.

- `init`: 서블릿 객체를 생성한다. 서블릿 컨테이너에 의해 호출된다.
- `service`: 요청을 처리하고 응답을 반환한다.
  - 인자: `HttpServletRequest`, `HttpServletResponse`
  - 서블릿의 핵심인 요청 처리 시 호출되는 메소드
- `destroy`: 서블릿 객체를 제거한다. 서블릿 컨테이너에 의해 호출된다.

 Apache Tomcat의 구현체를 살펴 보면 다음과 같다.

![javax.servlet.Servlet]({{site.url}}/assets/images/servlet-06.png){: .align-center width="500"}





<br>

### javax.servlet.GenericServlet

 `javax.servlet.Servlet` 인터페이스를 구현한 추상 클래스로, `service`만 제외하고, 서블릿에 필요한 모든 메소드를 재정의한다.

 Apache Tomcat의 구현체를 살펴 보면 다음과 같다.

![javax.servlet.Servlet]({{site.url}}/assets/images/servlet-07.png){: .align-center}

 서블릿 객체 생성 및 파괴는 서블릿 컨테이너에서 이루어지기 때문에, `GenericServlet` 클래스의 생성자는 아무 일도 하지 않는다.

<br>

### javax.servlet.http.HttpServlet



 `javax.servlet.GenericServlet` 클래스를 상속하여 `service` 메소드를 재정의한 추상 클래스이다. `HttpServlet`이기 때문에, HTTP 요청 방법에 따라 수행해야 할 작업이 `doGet`, `doPost` 등의 메소드로 정의되어 있고, `service` 메소드에서는 요청 방법에 따라 알맞은 메소드를 수행하도록 구현되어 있다.

 Apache Tomcat의 구현체를 살펴보면 다음과 같다.

![javax.servlet.http.HttpServlet]({{site.url}}/assets/images/servlet-08.png){: .align-center}

 개발자는 위의 `HttpServlet` 추상 클래스를 상속 받아 **요청에 따라 수행할 로직을 재정의**하면 된다. 재정의되지 않은 메소드가 호출되면, `method not allowed`와 같은 에러가 발생하게 된다.



<br>

# 서블릿 컨테이너



 서블릿 컨테이너는, JVM 상에서 **서블릿을 관리하고 동작시키는 환경**이다. 웹 서버에 동적 요청이 올 때, 적절한 서블릿 메소드를 실행하고 웹 서버에 그 결과를 전달하는데, 그 기능은 다음과 같다.

- 웹 서버와의 네트워크 통신
- 서블릿 프로그램 생명 주기 관리
- 스레드 기반의 요청 처리

<br>

 서블릿 컨테이너 상에서 요청이 처리되는 과정을 그림으로 나타내면 다음과 같다.

![servlet-request-response]({{site.url}}/assets/images/servlet-02.png){: .align-center}

<center><sup>아주 당연하게도, 서블릿 컨테이너는 웹 서버와 다른 프로세스인 WAS에서 실행된다.</sup></center>

1. 웹 서버: 클라이언트에게 동적 요청이 오면, 이를 서블릿 컨테이너에 위임한다.
2. 서블릿 컨테이너: 요청을 처리하기에 알맞은 서블릿을 찾고, 해당 서블릿 에서 요청을 처리하기 위한 메소드를 호출한다.
3. 서블릿: 요청을 처리한 후, 결과를 서블릿 컨테이너에 반환한다.
4. 서블릿 컨테이너: 웹 서버에 서블릿 프로그램이 반환한 결과를 전달한다.
5. 웹 서버: 서블릿 컨테이너가 전달한 결과를 클라이언트에게 응답으로 반환한다.

<br>

## Servlet Mapping

 서블릿 컨테이너 요청 처리 방법 `2`에서 살펴볼 수 있듯, 서블릿 컨테이너는 사용자의 요청이 오면 서블릿을 매핑(`.java` 확장자에서 서블릿을 찾아 실행한다고 이해하자)하여 실행한다. 이 매핑 정보는 다음과 같은 두 가지 방식으로 작성할 수 있다.

- 배포 서술자(`web.xml`) 파일의 `<servlet>` 태그 아래 서블릿 매핑 정보를 작성한다.
- `@WebServlet` 어노테이션을 사용한다.

<br>

 즉, 서블릿 컨테이너는 프로세스가 시작되어 로드될 때, 배포 서술자에서 `<servlet>`에 대한 내용이나 `@WebServlet` 어노테이션으로 지정된 클래스를 발견하면, 요청에 맞는 서블릿을 매핑할 수 있다.

![servlet-mapping]({{site.url}}/assets/images/servlet-05.png){: .align-center}

<center><sup>배포 서술자 파일을 통해 서블릿을 매핑(좌), annotation을 통해 서블릿을 매핑(우)</sup></center>

<br>

## Request, Response

 서블릿 컨테이너는 웹 서버에서 요청을 위임 받은 후, `HttpServletRequest`, `HttpServletResponse` 객체를 생성한다. 그리고 두 객체는 서블릿이 수행할 메소드의 인자로 전달된다.

 `HttpServletRequest`는 클라이언트의 요청 정보를, `HttpServletResponse`는 클라이언트에게 응답으로 반환할 정보를 가지고 있는 객체이다. Apache Tomcat의 구현체를 살펴 보면 다음과 같다.

![httpservletrequest]({{site.url}}/assets/images/servlet-04.png){: .align-center}

<br>

 위의 내용을 반영하여 `1` ~ `2` 사이에서 서블릿 컨테이너의 요청 처리 과정을 더 자세히 나타내 보면 다음과 같다.

![servlet-01-02]({{site.url}}/assets/images/servlet-03.png){: .align-center}

- 1.1. `HttpServletRequest` 객체 생성, `HttpServletResponse` 객체 생성
- 1.2. Servlet 매핑
- 1.3. 매핑된 서블릿의 `service` 메소드 호출 시 `HttpServletRequest`, `HttpServletResponse` 객체 전달

<br>

## 서블릿 생명 주기



 서블릿 컨테이너에서 서블릿 객체는 **단 1개**만 생성된다. 즉, 하나의 요청에 대해 하나의 서블릿만 매핑되어 요청 처리에 이용되는 것이다. 그리고 이 서블릿 객체의 생명 주기는 서블릿 컨테이너에 의해 관리된다. 따라서, 서블릿 프로그램에는 진입점인 `main` 매소드가 없다.

<br>

 서블릿 객체의 생명 주기는 다음과 같다.

![servlet-lifecycle]({{site.url}}/assets/images/servlet-09.png){: .align-center width="400"}

1. `init()`: 서블릿 인스턴스 생성
   - 서블릿 인스턴스가 메모리에 있는지 확인
   - 서블릿 인스턴스가 없으면, 서블릿 클래스 파일을 메모리에 로드
2. `service()`: `service` 메소드를 실행해 요청 처리
3. `destroy()`: 서블릿 인스턴스를 메모리에서 삭제

> *참고*: 서블릿 init 메소드의 호출 시점?
>
>  서블릿 생명주기의 시작이 언제부터인지 궁금했다. [stackoverflow 글](https://stackoverflow.com/questions/3106452/how-do-servlets-work-instantiation-sessions-shared-variables-and-multithreadi/3106909#3106909)을 참고한 결과, 매핑 단계에서 서블릿에 `load-on-startup` 값이 설정되어 있지 않은 경우, HTTP 요청이 온 첫 시점에 인스턴스화되는 듯하다.
>
> "When a `Servlet` has a `<servlet><load-on-startup>` or `@WebServlet(loadOnStartup)` value greater than `0`, then its `init()` method is also invoked during startup with a new `ServletConfig`. (…) In the event the `load-on-startup` value is absent, the `init()` method will be invoked whenever the HTTP request hits the servlet for the first time."

<br>

 위의 과정을 참고해 서블릿 컨테이너에서 요청이 처리되는 과정 중 `2`와 `3`을 구체화해 보면 다음과 같다.

![servlet-lifecycle-request-response]({{site.url}}/assets/images/servlet-10.png){: .align-center}

- 2.1. 요청과 매핑된 서블릿 인스턴스가 없으면 생성

- 2.2. 요청과 매핑된 서블릿 인스턴스가 있으면 해당 서블릿 객체의 `service()` 메소드 호출
- 2.3. 서블릿이 반환한 결과를 받아 웹 서버에 전달

<br>

## Thread Pool

 서블릿 컨테이너는 하나의 요청 처리 과정을 하나의 **스레드**로 관리한다. 즉, 요청 하나 당 스레드 하나가 할당되며, 각 스레드는 요청을 처리하기 위해 서블릿의 `service` 메소드를 호출하고 그 결과를 반환하며, 결과가 반환되면 작업이 종료된다. 

 각각의 스레드가 메모리에 올라가 있는 서블릿 인스턴스에 모두 접근하기 때문에, 서블릿 설계 시에는 thread-safe한 설계가 중요하다. 예컨대, 서블릿에 클래스 변수가 있으면 안 된다. (*HTTP 통신 방식이 stateless해야 함을 이런 방식의 설계를 통해 구현한 것이라는 피드백도 있었다*)

![servlet-thread]({{site.url}}/assets/images/servlet-11.png){: .align-center}

<br>

 이를 위해 서블릿 컨테이너는 **스레드 풀** 방식을 사용한다. 미리 스레드 풀에 스레드를 일정 개수 생성해 놓고, 요청이 올 때 마다 스레드 풀에 있는 스레드가 하나씩 맡아서 처리한 뒤, 요청 처리가 종료되면 스레드 풀에 스레드를 반납하도록 하는 것이다.

 처음에는 요청이 올 때마다 스레드를 생성하도록 했는데, 이 방식이 비효율적이기 때문에 점차 스레드 풀을 이용하는 방식으로 변화했다고 한다. 이 때문에, 서블릿 컨테이너에서는 최소 및 최대 스레드 수를 결정하는 게 주요 튜닝 포인트이기도 하다.

 각각의 요청에 따라 스레드 풀에서 스레드가 할당되어 요청을 처리하는 과정을 도식화하면 다음과 같다.

![servlet-thread-pool]({{site.url}}/assets/images/servlet-12.png)

<br>

# 결론



  결과적으로, 자바 진영의 WAS에서 서블릿은 서블릿 컨테이너에 의해, 프로세스에서 단 하나만 생성되어 그 생명 주기가 관리되며, 서블릿 컨테이너 내 스레드 풀에 있는 각 스레드가 서블릿을 이용해 동적 요청을 처리하게 된다.

 이후 동적 처리 과정과 연관해 더 알아보고 싶은 부분은 다음과 같다.

- JSP
- Spring Framework에서 서블릿의 동작