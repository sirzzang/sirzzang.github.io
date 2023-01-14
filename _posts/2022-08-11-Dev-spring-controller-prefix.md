---
title:  "[Spring] url prefix 설정"
excerpt: Spring에서 API 버전 관리를 위한 url prefix를 설정하는 방법
categories:
  - Dev
toc: true
header:
  teaser: /assets/images/blog-Dev.jpg
tags:
  - Java
  - Spring
  - url
  - prefix
  - controller
---

 

스프링을 이용해 API 서버 개발을 하다, API 버전 관리를 위한 url prefix를 분리하여 설정하기 위한 방법을 알아 보았다. 분리의 필요성은 다음과 같다.

- 모든 API 엔드포인트에 동일한 url prefix가 적용되고 있으나, 모든 컨트롤러의 `RequestMapping` 엔드포인트마다 일일이 작성하고 있음
- url prefix 변경 시, 모든 컨트롤러의 `RequestMapping` 엔드포인트 설정 값을 변경해 주어야 함

<br>

# 어플리케이션 설정





## 서블릿 설정 항목 이용

`server.servlet.context-path` 속성을 이용하면 된다.

- `application.yml`

  ```yaml
  server:
  	servlet:
  		context-path: /api/v1
  ```

- `application.properties`

  ```properties
  server.servlet.context-path: /api/v1
  ```



## Spring Data REST 설정 이용

 [Spring Data Rest](spring.io/projects/spring-data-rest)를 이용해서 설정할 수도 있다.

- 의존성 설정

  - Gradle

    ```groovy
    dependencies {
      implementation 'org.springframework.boot:spring-boot-starter-data-rest'
    }
    ```

  - Maven

    ```xml
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-data-rest</artifactId>
    </dependency>
    ```

- 어플리케이션 프로퍼티 설정

  ```properties
  spring.data.rest.basePath=/api/v1
  ```





## 커스텀 설정 값 이용

 아래와 같이 어플리케이션 프로퍼티 설정 시 `api prefix` 관련 속성을 설정하고, 요청 매핑 시 해당 설정 값을 읽어 오도록 컨트롤러 코드를 작성한다.

- `application.yml`

  ```yaml
  server:
    port: 8080
  
  # api prefix 설정
  api:
    prefix: "/api/v1"
  ```

- 컨트롤러 코드 작성

  ```java
  @Controller
  public class ExampleController {
  
      @RequestMapping("${api.prefix}/hello")
      public @ResponseBody String hello() {
          return "Hello, world!";
      }
    
    	@RequestMapping("${api.prefix}/bye")
    	public @ResponseBody String bye() {
        	return "Bye, world!"
      }
  }
  
  ```

 이와 같이 url prefix 설정 시, 다음과 같은 특징이 있다.

- url prefix를 한 곳에서 관리할 수 있다. 쉽게 변경할 수 있다
- 컨트롤러에서 요청 매핑 시 url prefix 설정 값을 읽어 와야 하기는 하다



<br>

# 자바 코드 이용



## 어노테이션 이용

 특정 url prefix로 요청을 매핑하도록 Controller 어노테이션을 작성한 뒤, url prefix를 적용하고 싶은 컨트롤러에 해당 어노테이션을 붙여 준다.

- `@BaseController`

  ```java
  @Target(ElementType.TYPE)
  @Retention(RetentionPolicy.RUNTIME)
  @RestController
  @RequestMapping("/api/v1/*")
  public @interface BaseController {
  }
  ```

- 컨트롤러 코드 작성

  ```java
  @BaseController
  public class ExampleController {
  
      @RequestMapping("/hello")
      public @ResponseBody String hello() {
          return "Hello, world!";
      }
    
    	@RequestMapping("/bye")
    	public @ResponseBody String bye() {
        	return "Bye, world!"
      }
  }
  
  ```

 이와 같이 url prefix를 설정하는 방식에는 다음과 같은 특징이 있다.

- url prefix를 설정하고 싶은 엔드 포인트에만 적용할 수 있다. 해당 엔드 포인트를 관리하는 컨트롤러만 골라서 어노테이션을 붙이면 된다
- 컨트롤러 요청 매핑 시 url prefix를 신경쓰지 않아도 된다
- url prefix 변경 시 어노테이션의 요청 매핑 값만 변경하면 된다



<br>

## 공통 컨트롤러 상속

 어노테이션을 사용하는 방법과 유사하다. 다만, url prefix를 붙이고 싶은 엔드포인트를 관리하는 공통 컨트롤러를 만들고, 다른 컨트롤러가 이를 상속 받아 사용하도록 한다.

- `BaseController`

  ```java
  @RequestMapping("/api/v1/*")
  public class BaseController {
  }
  ```

- 컨트롤러 코드 작성

  ```java
  @Controller
  public class ExampleController extends BaseController {
  
      @RequestMapping("/hello")
      public @ResponseBody String hello() {
          return "Hello, world!";
      }
    
    	@RequestMapping("/bye")
    	public @ResponseBody String bye() {
        	return "Bye, world!"
      }
  }
  ```

 어노테이션을 설정하는 것과 동일한 특징을 지닌다. 어떤 방법을 선택할지는 취향 차이일 듯하다.



<br>

# 결론



 위와 같은 방법을 이용하여 api 버전에 대한 url prefix를 일일이 작성하지 않고도 요청 매핑 엔드 포인트를들을 관리할 수 있다. API 버전 별 인가가 달라질 때에도 유용할 것으로 보인다. 개인적으로는 어노테이션 혹은 공통 컨트롤러를 사용해 보고 싶긴 하나, 어떤 방식이든 url prefix를 관리할 수 있다는 것에 초점을 두어 개발 시 수고로움을 덜어 보자.
