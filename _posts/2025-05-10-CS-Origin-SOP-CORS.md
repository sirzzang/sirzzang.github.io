---
title:  "[CS] Origin에 대한 고찰 - 정의, SOP, CORS"
excerpt: Origin에 대해 알아보자.
categories:
  - CS
toc: true
header:
  teaser: /assets/images/blog-Dev.jpg
tags:
  - Origin
  - SOP
  - Same Origin Policy
  - CORS
  - Cross Origin Resource Sharing
---

<br>

 웹 서비스 개발을 하다 보면 심심치 않게 CORS라는 녀석을 마주하곤 한다. 프런트엔드 개발의 세계에 처음 발을 내딛었을 때 서버에 API 연결을 하면서 처음 마주쳤었는데, 그 때는 백엔드 개발자가 `CORS 설정을 해 주면 된다`고만 해서 넘어갔던 기억이 있다. 백엔드 개발자의 길을 걷고 있는 지금은, 반대로 내가 CORS 설정을 해 주어야 하는 일이 잦아졌다. 

 그 때나 지금이나 CORS는 심심치 않게 마주할 수 있는 토픽인데, 정확히 개념을 정리한 적은 없는 것 같아, 공부한 내용을 정리해 보고자 한다.

<br>



# Origin

 웹 개발에서 Origin이란 웹 페이지의 리소스 출처를 의미한다. 웹 보안을 위해 도입된 개념으로, 웹 페이지의 출처를 의미한다.

<br>

![url-origin]({{site.url}}/assets/images/url-origin.png){: .align-center}

 Origin은 아래와 같은 세 가지의 요소로 구성된다.

- Scheme: 웹 페이지 출처와의 통신 프로토콜
  - http, https
- Host: 웹 페이지 출처의 호스트
  - Domain
  - IP
- Port: 웹 페이지 출처 서버의 통신 포트
  - 통신 프로토콜에 따라 생략되는 경우도 있음
    - http: `80`
    - https: `443`

<br>

그렇다면 브라우저는 Origin을 어떻게 해석할까. 브라우저는 URL 문자열을 scheme, host, port, path, query string, fragment 등의 각 구성 요소로 해석한다. 그리고 scheme, host, port만을 활용해, Origin을 판단한다. 이 셋 중 **하나라도 다르면, 브라우저는 다른 Origin이라고 판단**한다.

 즉, 브라우저 입장에서 `https://www.example.com`과 같은 Origin은 `https://www.example.com` 뿐이다. 다시 말해, 아래의 Origin은 모두 다른 Origin이다.

- `http://www.example.com`: scheme이 다름
- `http://www.example.net`: host가 다름
- `https://www.example.com:4443`: port가 다름
  - `https://example.com`의 경우, scheme이 https이므로, 기본 포트는 443

그렇다면, 도메인이 IP 주소로 변환되는 경우에는 어떻게 판단할까. 기본적으로 브라우저는 Origin을 판단하기 위해 URL을 해석하기만 할 뿐, 도메인을 IP 주소로 변환(resolve)하는 것까지는 하지 않는다. 따라서, `example.com`이 `93.184.216.34`로 resolve된다고 하더라도, `http://example.com`과 `http://93.184.216.34`는 다른 Origin이다.

<br>

 위와 같은 원리에 의해, 각각의 두 Origin이 서로 같은지 아닌지를 다음과 같이 판단할 수 있다.

| Origin 1                                 | Origin 2                                          | Same Origin?                         |
| ---------------------------------------- | ------------------------------------------------- | ------------------------------------ |
| `http://store.company.com/dir/page.html` | `http://store.company.com:80/dir/page.html`       | O<br />- http scheme default port 80 |
| `http://store.company.com/dir/page.html` | `http://store.company.com/dir/other.html`         | O<br />- path만 다름                 |
| `http://store.company.com/dir/page.html` | `http://store.company.com/dir/inner/another.html` | O<br />- path만 다름                 |
| `http://store.company.com/dir/page.html` | `https://store.company.com/page.html`             | X<br />- scheme이 다름               |
| `http://store.company.com/dir/page.html` | `http://store.company.com:81/dir/page.html`       | X<br />- port가 다름                 |
| `http://store.company.com/dir/page.html` | `http://news.company.com/dir/page.html`           | X<br />- host가 다름                 |

<br>

## Origin 판단 시 놓치기 쉬운 함정

 Origin 판단 원칙 자체는 단순하지만, 실무에서 의외로 놓치기 쉬운 함정들이 있다.

| Origin 1 | Origin 2 | Same Origin? | 함정 |
| --- | --- | --- | --- |
| `http://example.com:8004` | `https://example.com` | X | 프로토콜 + 포트 **둘 다** 다름 |
| `http://example.com:8004` | `http://example.com` | X | 포트만 달라도 Cross-Origin |
| `http://example.com` | `http://example.com:80` | O | http 기본 포트는 80 |
| `https://example.com` | `https://example.com:443` | O | https 기본 포트는 443 |

 특히 첫 번째 케이스는 실무에서 자주 마주하는 상황이다. 프로토콜이 `http`에서 `https`로 바뀌면 그것만으로도 다른 Origin이 되는데, 여기에 포트까지 다르면 Origin 구성 요소 세 개 중 두 개가 다른 셈이 된다. 눈으로 보기에는 '같은 도메인 아닌가?' 싶지만, 브라우저는 엄격하게 다른 Origin으로 판단한다.

 두 번째 케이스도 주의해야 한다. 예를 들어, nginx로 프런트엔드를 `http://foo.example.com:8004`에서 서빙하면서, API 요청을 `http://foo.example.com`으로 보내는 경우를 생각해 보자. 같은 도메인이니까 Same-Origin이라고 생각하기 쉽지만, 포트가 다르기 때문에 브라우저는 이를 Cross-Origin으로 판단한다. `http`의 기본 포트는 80이므로, `http://foo.example.com`은 `http://foo.example.com:80`과 같다. 따라서 `:8004`와 `:80`은 서로 다른 포트이고, 결국 Cross-Origin이 되는 것이다.

> 실무에서 CORS 문제를 마주했을 때, 가장 먼저 확인해야 할 것은 현재 페이지의 Origin과 요청 대상의 Origin이 정말로 같은지다. 프로토콜, 호스트, 포트 세 가지를 하나하나 대조해 보자.



<br>



# Same Origin Policy

 그렇다면 Origin이라는 개념은 왜 중요한가. 그것은 바로 Origin이 웹 어플리케이션이 채택하고 있는 중요한 보안 메커니즘 중 하나인, **동일 출처 정책(Same Origin Policy, SOP)**의 근간이 되는 개념이기 때문이다.

 현대 웹 서비스 환경이 점차 복잡해지며, 웹 어플리케이션이 여러 소스로부터 컨텐츠를 로드해 오는 경우가 잦아졌다. 이 때 웹 브라우저는 악성 컨텐츠가 로드되는 것을 막기 위해, 하나의 Origin에서 로드된 문서 혹은 스크립트가 다른 Origin의 리소스와 상호작용하는 것을 제한한다. 다른 Origin에서 로드해 오는 리소스가 해로운 것일 수도 있기 때문이다. 

 이렇게 웹 브라우저 단에서 **동일한 출처의 리소스와만 상호작용하도록 제한하는 정책**을 Same Origin Policy라고 한다. 다시 말해, 서로 다른 출처로부터의 리소스 로드를 제한하는 것이다. 다른 Origin 리소스에 대해 보수적으로 접근해, 사용자를 악성 리소스로부터 보호하고자 하는 것이다. 

> 지금 리소스 Origin이랑 다른 Origin으로 요청하면, 그냥 브라우저가 막아 버린다.



<br>

## Cross Origin 접근 제한 정책

 해당 정책의 맥락에서, 다른 출처로부터의 리소스를 Cross Origin 리소스라고 한다. 또한, 다른 출처로의 리소스 요청을 Cross Origin 요청이라고 한다. 예컨대, `http://example.com`에서 `http://api.example.com`에 요청을 보내서 리소스를 얻어 와야 하는 경우, 이 요청은 Cross Origin 요청이 된다. 

<br>

 Same Origin Policy 하에서, Cross Origin에 대한 요청은 아래와 같이 제한된다([참고: Cross Origin Network Access](https://developer.mozilla.org/en-US/docs/Web/Security/Same-origin_policy#cross-origin_network_access))

- Cross Origin Write: 일반적으로 허용됨
  - link
  - redirect
  - form submission
- Cross Origin Embedding: 일반적으로 허용됨
  - `<script src="..."></script>` 태그를 이용한 자바스크립트 소스
  - `<link rel="stylesheet" href="...">`  태그를 이용한 CSS
    * 다만, cross-origin CSS는 올바른 `Content-Type` 헤더를 가져야 하고, 올바른 CSS 문법을 따라야 함
  - `<img>` 태그로 보여지는 이미지
  - `<video>`, `<audio>` 등의 태그로 보여지는 미디어
  - `<object>`, `<embed>` 등의 태그로 임베드되는 외부 리소스
  - `@font-face`로 적용되는 폰트
    * 몇몇 브라우저에서는 cross-origin 폰트를 허용하지만, 그렇지 않은 브라우저도 있음
  - `<iframe>` 태그로 임베드되는 것
    * cross-origin 프레이밍을 막기 위해서는 `X-Frame-Options` 헤더를 사용할 수 있음
- Cross Origin Read: 허용되지 않음

<br>

위에서 더 나아가, 조금 더 엄격한 Cross Origin 접근 제한 정책을 적용할 수도 있다고 한다.

- Cross Origin Write를 막기 위해, CSRF 토큰과 같은 것을 체크할 수도 있음
- Cross Origin Read를 더 엄격히 막기 위해서는, Cross Origin Embed가 되지 않도록 해야 함
  - Cross Origin 리소스가 Embedabble Format으로 해석되지 않도록 주의해야 함



<br>

# Cross Origin Resource Sharing

그러나 점차 복잡해지는 현대 웹 서비스 환경에서 동일한 출처에서만 리소스를 로드해 오는 것은 상당한 제약이 아닐 수 없다. 프런트엔드와 백엔드가 분리되며, API 서버를 따로 두는 요즘 같은 추세에서는 더욱 그러하다.

<br>

 그렇기 때문에, Cross Origin 리소스를 허용해 주기 위한 정책이 존재한다. 이를 **교차 출처 리소스 공유(Cross Origin Resource Sharing, CORS)**라고 한다. Cross Origin Resource Sharing은 브라우저가 Cross Origin으로부터의 리소스를 로드할 수 있도록 하는 메커니즘이다.

> Use [CORS](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/CORS) to allow cross-origin access. CORS is a part of [HTTP](https://developer.mozilla.org/en-US/docs/Glossary/HTTP) that lets servers specify any other hosts from which a browser should permit loading of content.

> 보통 개발하다가 Origin이 달라서 자원을 로드하지 못하는 상황에 마주쳤을 때, `CORS 문제`라고 이야기하는 경우가 있는데, 엄밀히 말하면 이건 잘못된 표현이다. SOP로 인해 발생한 문제로, CORS를 설정 혹은 허용해 주어야 한다고 표현해야 한다.

![cors-example]({{site.url}}/assets/images/cors-document-example.png){: .align-center}

<center><sup>domain-a.com 도메인을 가진 서버에서 서빙되는 웹 페이지에, domain-b.com 도메인을 가진 서버에서 로드되는 리소스가 있다면, CORS를 통해 SOP에 걸리지 않도록 해 주어야 한다.(그림 출처: https://developer.mozilla.org/ko/docs/Web/HTTP/Guides/CORS) </sup></center>







<br>

## 개념

브라우저가 Cross Origin으로부터 자원을 로딩할 수 있도록 서버에서 허가해 주는 HTTP 헤더 기반의 메커니즘이다. 즉, 브라우저가 Cross Origin으로부터 자원을 로딩하기 위해서는 어떻게 통신하면 되는가에 대한 방식을 표준화한 것이다.

 보통 브라우저가 Cross Origin 서버에 CORS 관련 헤더를 포함한 사전 요청(Preflight Request)을 보내고, Cross Origin 서버는 이 요청에 대한 응답으로 CORS 관련 헤더를 포함한 응답을 보낸다. 이 응답을 확인한 브라우저는 해당 Cross Origin 서버에 요청을 보낸다. 

<br>

## 시나리오

 브라우저는 `XMLHttpRequest`나 `fetch()` API를 이용해야 하는 경우, 요청의 대상이 Cross Origin인지 아닌지 URL을 통해 판단한다. 그리고 Cross Origin에 대한 요청인 경우, CORS 메커니즘을 따른다. 위에서 사전 요청을 보낸다고 했으나, 엄밀히는 사전 요청이 필요한 경우와 그렇지 않은 경우의 두 가지 시나리오로 나뉘며, 사전 요청이 필요한지 여부는 브라우저에서 자바스크립트 코드를 통해 알아서 판단할 수 있다.

 브라우저가 알아서 판단할 수 있긴 하지만, 단순 요청의 경우, 아래의 조건을 **모두** 충족해야 한다. 이 조건을 알아 두는 것이 실무적으로 중요한데, **대부분의 API 요청은 이 조건을 만족하지 못해 사전 요청이 발생하기 때문**이다.

- 메서드: `GET`, `HEAD`, `POST` 중 하나
- 헤더: 사용자 에이전트에서 자동으로 설정되는 헤더 외에, Fetch 명세에서 [CORS-safelisted request header](https://fetch.spec.whatwg.org/#cors-safelisted-request-header)로 지정한 헤더
  - `Accept`
  - `Accept-Language`
  - `Content-Language`
  - `Content-Type`: 이 헤더가 있는 경우, 추가 요구 사항이 있음
  - `Range`: 단순 범위 헤더 값
- `Content-Type`: 허용된 타입 및 서브타입 조합만 가능
  - `application/x-www-form-urlencoded`
  - `multipart/form-data`
  - `text/plain`
- 기타 요구 조건들도 있으나, 그건 궁금하면 더 알아 보도록 하자([참고: CORS Simple Request](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/CORS#simple_requests))



<br>

### 단순 요청

사전 요청 없이, 요청 자체에 CORS 헤더를 담아 보내고, 응답에 CORS 헤더를 보내는 경우이다.

![cors-simple-request-flow]({{site.url}}/assets/images/cors-simple-request-flow.png){: .align-center}

<center><sup>그림 출처: https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/CORS</sup></center>

- 브라우저 HTTP 요청 메시지

  ```http
  GET /resources/public-data/ HTTP/1.1
  Host: bar.other
  User-Agent: Mozilla/5.0 (Macintosh; Intel Mac OS X 10.14; rv:71.0) Gecko/20100101 Firefox/71.0
  Accept: text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8
  Accept-Language: en-us,en;q=0.5
  Accept-Encoding: gzip,deflate
  Connection: keep-alive
  Origin: https://foo.example
  ```

  - `Origin` 헤더를 통해, 자신의 Origin을 알려 줌

- 서버 HTTP 응답 메시지

  ```http
  HTTP/1.1 200 OK
  Date: Mon, 01 Dec 2008 00:23:53 GMT
  Server: Apache/2
  Access-Control-Allow-Origin: *
  Keep-Alive: timeout=2, max=100
  Connection: Keep-Alive
  Transfer-Encoding: chunked
  Content-Type: application/xml
  
  […XML Data…]
  ```

  - `Access-Control-Allow-Origin` 헤더를 통해 요청을 보낼 수 있는 Origin을 알려 줌
    - `*` 와일드카드를 통해 모든 Origin에서 요청을 보낼 수 있음을 알림
    - 따라서 이 응답을 받은 브라우저에서는 Cross Origin 서버가 요청을 보내도 안전한 Origin임을 알고, 응답으로 받은 데이터를 로드함
    - 만약, Origin에 특정 Origin이 명시되어 있고, 그것이 자신의 Origin과 다르다면, 응답으로 받은 데이터를 로드하지 않을 것
      - `Origin: http://bar.example`으로 명시되어 있는 경우의 예

> **실무에서의 빈도**: 단순 요청 조건을 만족하는 API 호출은 생각보다 드물다. 대부분의 API 요청은 `Content-Type: application/json`을 사용하거나, `Authorization`과 같은 커스텀 헤더를 포함하기 때문에, 단순 요청 조건을 충족하지 못한다. 즉, 실무에서 마주하는 거의 모든 API 통신은 아래의 사전 요청 시나리오에 해당한다.

<br>



### 사전 요청

 단순 요청의 조건을 충족하지 않는 모든 시나리오에 해당한다. 실제 요청을 전송하는 것이 안전한지 판단하기 위한 사전 요청(Preflight Request)가 추가되고, 사전 요청 결과를 바탕으로 안전한 Origin이라는 것이 판단되면, 그 이후 요청을 진행한다.

 사전 요청은 `OPTIONS` 메서드를 이용해 진행된다. 해당 메서드를 이용한 요청은 서버의 리소스를 바꾸지 않는 안전한 요청임이 보장된다.

![cors-preflight-request-flow]({{site.url}}/assets/images/cors-preflight-request-flow.png){: .align-center}

<center><sup>그림 출처: https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/CORS</sup></center>

- 브라우저 Preflight HTTP 요청 메시지

  ```http
  OPTIONS /doc HTTP/1.1
  Host: bar.other
  User-Agent: Mozilla/5.0 (Macintosh; Intel Mac OS X 10.14; rv:71.0) Gecko/20100101 Firefox/71.0
  Accept: text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8
  Accept-Language: en-us,en;q=0.5
  Accept-Encoding: gzip,deflate
  Connection: keep-alive
  Origin: https://foo.example
  Access-Control-Request-Method: POST
  Access-Control-Request-Headers: content-type,x-pingother
  ```

  - `Origin` 헤더를 통해, 자신의 Origin을 알려 줌
  - `Access-Control-Request-*` 헤더를 통해 요청에 관련한 정보를 줌
    - `Access-Control-Request-Method`: 요청에 사용할 메서드
    - `Access-Control-Request-Headers`: 요청에 사용할 헤더

- 서버 Preflight HTTP 응답 메시지

  ```http
  HTTP/1.1 204 No Content
  Date: Mon, 01 Dec 2008 01:15:39 GMT
  Server: Apache/2
  Access-Control-Allow-Origin: https://foo.example
  Access-Control-Allow-Methods: POST, GET, OPTIONS
  Access-Control-Allow-Headers: X-PINGOTHER, Content-Type
  Access-Control-Max-Age: 86400
  Vary: Accept-Encoding, Origin
  Keep-Alive: timeout=2, max=100
  Connection: Keep-Alive
  ```

  - `Access-Control-Allow-*` 헤더를 통해 허용된 요청에 대한 정보를 줌
    - `Access-Control-Allow-Origin`: 요청이 허용된 Origin
    - `Access-Control-Allow-Methods`: 요청에 허용된 메서드
    - `Access-Control-Allow-Headers`: 요청에 허용된 헤더
  - `Access-Control-Max-Age`: 브라우저에서 응답을 캐시해 두고 사용할 수 있는 시간(초)
    - 브라우저에서 이후에 또 다른 사전 요청을 보내지 않아도 되도록 하기 위함
    - 최대 캐시 시간은 86400초(24시간)
      - 해당 최대값을 초과하는 값을 설정해서 보낼 경우, 각 브라우저는 내부적으로 설정된 최대값에 해당하는 시간 동안만 캐시해 둠

- 메인 HTTP 요청 메시지

  ```http
  POST /doc HTTP/1.1
  Host: bar.other
  User-Agent: Mozilla/5.0 (Macintosh; Intel Mac OS X 10.14; rv:71.0) Gecko/20100101 Firefox/71.0
  Accept: text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8
  Accept-Language: en-us,en;q=0.5
  Accept-Encoding: gzip,deflate
  Connection: keep-alive
  X-PINGOTHER: pingpong
  Content-Type: text/xml; charset=UTF-8
  Referer: https://foo.example/examples/preflightInvocation.html
  Content-Length: 55
  Origin: https://foo.example
  Pragma: no-cache
  Cache-Control: no-cache
  
  <person><name>Arun</name></person>
  ```

  - `Origin` 헤더

- 메인 HTTP 응답 메시지

  ```http
  HTTP/1.1 200 OK
  Date: Mon, 01 Dec 2008 01:15:40 GMT
  Server: Apache/2
  Access-Control-Allow-Origin: https://foo.example
  Vary: Accept-Encoding, Origin
  Content-Encoding: gzip
  Content-Length: 235
  Keep-Alive: timeout=2, max=99
  Connection: Keep-Alive
  Content-Type: text/plain
  
  [Some XML payload]
  ```

<br>

 **실무에서 대부분의 API 요청은 사전 요청 시나리오에 해당한다.** 아래와 같은 전형적인 로그인 API 호출을 생각해 보자.

```javascript
axios.post('/api/user/login', {
    username: id,
    password: pw,
})
```

 이 요청은 `Content-Type: application/json`으로 전송된다. 단순 요청이 허용하는 Content-Type은 `application/x-www-form-urlencoded`, `multipart/form-data`, `text/plain` 세 가지뿐이므로, 이 요청은 단순 요청 조건을 충족하지 못한다. 따라서 브라우저는 자동으로 사전 요청(OPTIONS)을 먼저 보내게 된다. JSON을 주고받는 API 통신이 표준인 현대 웹 개발에서, **Preflight는 사실상 기본값**이라고 봐도 무방하다.

 그렇다면 Preflight를 아예 피할 수는 없을까?

```javascript
// 방법 1: Form 데이터로 전송 (비현실적)
const formData = new URLSearchParams();
formData.append('username', id);
formData.append('password', pw);

axios.post('/api/user/login', formData, {
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' }
})
// → Preflight 없음! 하지만 JSON이 표준인 현대 API에서는 거의 쓰이지 않음
```

 `application/x-www-form-urlencoded`를 사용하면 단순 요청이 되어 Preflight를 피할 수 있다. 하지만, JSON이 사실상 API 통신의 표준인 현실에서 이 방법은 비현실적이다. 결론적으로, **서버에서 OPTIONS 요청을 올바르게 처리하는 것이 정답**이다.

<br>

### 기타 시나리오

- 사전 요청 후의 리다이렉션은 허용되지 않음

- 자격 증명(credentials)이 포함된 요청 및 응답의 경우, 브라우저에서 요청 시 credential 관련 설정을 해 주어야 하며, 서버에서는 응답에 와일드카드를 사용할 수 없음

  - 브라우저 요청 자바스크립트 예

    ```javascript
    const url = "https://bar.other/resources/credentialed-content/";
    
    const request = new Request(url, { credentials: "include" });
    
    const fetchPromise = fetch(request);
    fetchPromise.then((response) => console.log(response));
    ```

  - HTTP 요청 메시지

    ```http
    GET /resources/credentialed-content/ HTTP/1.1
    Host: bar.other
    User-Agent: Mozilla/5.0 (Macintosh; Intel Mac OS X 10.14; rv:71.0) Gecko/20100101 Firefox/71.0
    Accept: text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8
    Accept-Language: en-us,en;q=0.5
    Accept-Encoding: gzip,deflate
    Connection: keep-alive
    Referer: https://foo.example/examples/credential.html
    Origin: https://foo.example
    Cookie: pageAccess=2
    ```

  - HTTP 응답 메시지

    ```http
    HTTP/1.1 200 OK
    Date: Mon, 01 Dec 2008 01:34:52 GMT
    Server: Apache/2
    Access-Control-Allow-Origin: https://foo.example
    Access-Control-Allow-Credentials: true
    Cache-Control: no-cache
    Pragma: no-cache
    Set-Cookie: pageAccess=3; expires=Wed, 31-Dec-2008 01:34:53 GMT
    Vary: Accept-Encoding, Origin
    Content-Encoding: gzip
    Content-Length: 106
    Keep-Alive: timeout=2, max=100
    Connection: Keep-Alive
    Content-Type: text/plain
    
    [text/plain payload]
    ```

    - `Access-Control-Allow-Origins` 헤더에 `true` 값을 설정해야 함
      - 그렇지 않으면 응답을 받은 브라우저에서는 요청할 수 없는 것으로 판단함
    - `Access-Control-Allow-*` 헤더에 `*` 와일드카드를 사용해서는 안 됨
      - 그렇지 않은 경우, 대부분의 브라우저에서는 응답에 대한 접근을 차단하고 개발자 도구 콘솔에 CORS 에러를 보고함





<br>

## CORS 헤더

위의 시나리오를 통해 어떤 헤더들이 있는지 언급하긴 했으나, CORS를 위해 사용되는 더 자세한 헤더에 대해 알고 싶다면, 아래 문서를 참고하면 된다. 

- [CORS 요청 헤더](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/CORS#the_http_request_headers)
- [CORS 응답 헤더](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/CORS#the_http_response_headers)



<br>

# 실무에서의 CORS 대응

 결론적으로 Origin은 Same Origin Policy로 인해 발생하는 문제 상황 및 이를 해결하기 위한 Cross Origin Resource Sharing 메커니즘을 이해하기 위한 핵심 개념이다.

- 브라우저에서 리소스를 로드할 때, 웹 보안을 위해 Same Origin Policy가 동작함
  - 브라우저에서 로드하는 리소스는 원칙적으로 동일 Origin으로부터의 것이어야 함
  - 로드해야 할 리소스의 Origin이 현재 리소스의 Origin과 다르다면 브라우저 단에서 요청 자체를 막아 버림
- Same Origin Policy에도 불구하고 Cross Origin으로부터 리소스를 로드해야 한다면, Cross Origin Resource Sharing을 허용해야 함

<br>

 그렇다면, 개발자로서 실무 상황에서 SOP에 위배되는 상황에 어떻게 대처할 수 있을까.

## 서버 CORS 설정

- 클라이언트 개발자는 요청을 보내면 된다.
  - 브라우저가 CORS 관련 판단을 다 알아서 해 준다.
  - credentials가 필요한 경우에는, 관련 설정이 필요하다.
- 서버 개발자는 CORS 허용을 위한 관련 설정을 해 주면 된다.
  - 어떤 origin, method, header를 허용할지에 대한 코드 설정이 필요하다.
  - 사실 대부분의 웹 프레임워크나 미들웨어에서는 관련 설정을 쉽게 할 수 있도록 지원하고 있다.

<br>

## 프록시로 Same-Origin 만들기

 서버에서 무언가 할 수 없는 상황이라면, 클라이언트 요청 처리를 위한 프록시 서버를 두는 방법이 있다. SOP는 브라우저의 웹 보안 정책이고, 서버 간 통신에서는 적용되지 않기 때문이다.

 이 패턴의 대표적인 예가 **nginx 리버스 프록시**다. nginx가 프런트엔드 정적 파일 서빙과 API `proxy_pass`를 함께 처리하면, 브라우저 입장에서는 모든 요청이 Same-Origin이 된다.

```nginx
server {
    listen 8004;
    server_name foo.example.com;

    # 프런트엔드 정적 파일 서빙
    location / {
        root /usr/share/nginx/html;
        index index.html;
    }

    # API 요청을 백엔드로 프록시
    location /api/ {
        proxy_pass http://backend-server:8080;
    }
}
```

 이렇게 구성하면, 브라우저에서 `http://foo.example.com:8004`로 페이지를 로드한 후 `http://foo.example.com:8004/api/...`로 API 요청을 보내게 된다. 프로토콜(`http`), 호스트(`foo.example.com`), 포트(`8004`)가 모두 같으므로, 브라우저 입장에서 Same-Origin 요청이 된다. Same-Origin 요청에는 CORS 메커니즘이 적용되지 않으므로, Cross-Origin 문제 자체가 발생하지 않는다.

<br>

### Same-Origin 구성이 깨지면 즉시 Cross-Origin

 프록시로 Same-Origin을 만들 때 주의할 점은, **Origin 구성 요소가 하나라도 틀어지면 즉시 Cross-Origin이 된다**는 것이다. 그리고 Cross-Origin 상황에서 `Content-Type: application/json`을 사용하는 순간, 단순 요청 조건을 만족하지 못하므로 Preflight가 반드시 발생한다.

 예를 들어, 아래와 같은 상황을 생각해 보자.

```
현재 페이지: http://foo.example.com:8004
요청 URL:   http://foo.example.com/api/user/login

브라우저의 판단:
  1. Origin 비교: http://foo.example.com:8004 vs http://foo.example.com(:80)
  2. 포트 불일치! → Cross-Origin!
  3. Content-Type: application/json → 단순 요청 아님!
  4. → OPTIONS Preflight 발생
  5. → CORS 헤더 엄격히 체크
```

 같은 도메인이라 Same-Origin이라고 생각하기 쉽지만, 포트가 다르기 때문에 Cross-Origin으로 처리된다. 이런 상황에서는 서버에서 CORS 헤더를 정확히 설정해 주어야 한다.

<br>

 Cross-Origin에서의 CORS 검증은 엄격하다. 모든 CORS 헤더가 정확히 매칭되어야 한다.

```http
HTTP/1.1 204 No Content
Access-Control-Allow-Origin: http://foo.example.com:8004  ← 정확히 매칭!
Access-Control-Allow-Methods: GET, POST, OPTIONS           ← 필수!
Access-Control-Allow-Headers: Content-Type, Authorization  ← 필수!
Access-Control-Allow-Credentials: true                     ← Cookie 있으면 필수!
Access-Control-Max-Age: 86400                              ← 선택
```

 하나라도 빠지거나 값이 틀리면, 브라우저는 응답을 차단한다.

<br>

### nginx에서 OPTIONS를 처리하는 이유

 Cross-Origin 상황에서 Preflight(OPTIONS) 요청이 발생하면, 서버가 이를 올바르게 처리해야 한다. nginx에서 OPTIONS를 직접 처리하는 방식은 다음과 같다.

```nginx
location /api/ {
    # Preflight 요청 처리
    if ($request_method = 'OPTIONS') {
        add_header 'Access-Control-Allow-Origin' '$http_origin' always;
        add_header 'Access-Control-Allow-Methods' 'GET, POST, PUT, DELETE, OPTIONS' always;
        add_header 'Access-Control-Allow-Headers' 'Content-Type, Authorization' always;
        add_header 'Access-Control-Max-Age' 86400;
        return 204;
    }

    # 실제 요청에 대한 CORS 헤더
    add_header 'Access-Control-Allow-Origin' '$http_origin' always;

    proxy_pass http://backend-server:8080;
}
```

 여기서 주목할 포인트가 몇 가지 있다.

- **`add_header ... always`의 중요성**: `always` 키워드가 없으면, nginx는 2xx, 3xx 응답에만 해당 헤더를 추가한다. 즉, 백엔드에서 4xx나 5xx 에러가 발생했을 때 CORS 헤더가 붙지 않게 되고, 브라우저가 에러 응답조차 읽지 못하는 상황이 생긴다. `always`를 붙이면 모든 응답 코드에 헤더가 추가된다.
- **OPTIONS를 nginx에서 직접 204로 반환**: 백엔드까지 OPTIONS 요청을 전달하지 않으므로, 백엔드 부담을 줄이고 CORS 정책을 nginx 한 곳에서 중앙 집중적으로 관리할 수 있다.

<br>

### 백엔드에도 CORS 설정을 유지하는 이유

 nginx에서 CORS를 처리한다면, 백엔드에서는 CORS 설정이 불필요한 것 아닌가 싶을 수 있다. 하지만, 다음과 같은 이유로 백엔드에도 CORS 설정을 유지하는 것이 좋다.

- **로컬 개발 환경**: 개발 시에는 nginx 없이 프런트엔드 개발 서버(`localhost:3000`)와 백엔드(`localhost:8080`)를 직접 연결하는 경우가 많다. 이 때 백엔드에 CORS 설정이 없으면, 포트가 다르므로 Cross-Origin이 되어 개발 자체가 어려워진다.
- **아키텍처 변경 대응**: nginx 앞단 구성이 바뀌거나, 다른 서비스에서 직접 API를 호출하게 될 수도 있다. 백엔드 자체에 CORS 설정이 있으면 이런 변경에 유연하게 대응할 수 있다.
- **이중 방어**: nginx CORS 설정에 문제가 생기더라도 백엔드가 자체적으로 CORS를 처리할 수 있다.

<br>

## 에러 유형별 감별법

 CORS 관련 문제를 디버깅할 때, 브라우저 개발자 도구에서 보이는 에러 메시지만으로는 원인을 파악하기 어려운 경우가 많다. 사실 CORS 에러처럼 보이지만, 실제로는 네트워크 단계에서 이미 실패한 경우도 있다. 아래는 에러 유형별로 원인을 감별하는 가이드다.

| 에러 | 단계 | 원인 | 대응 |
| --- | --- | --- | --- |
| `net::ERR_NAME_NOT_RESOLVED` | DNS | 도메인을 IP로 변환하지 못함 | DNS 설정 확인, 도메인 오타 확인 |
| `net::ERR_CONNECTION_REFUSED` | TCP | 서버에 연결할 수 없음 | 서버 구동 여부, 포트, 방화벽 확인 |
| `405 Method Not Allowed` | 서버 | 서버가 OPTIONS 메서드를 지원하지 않음 | 서버 또는 nginx에서 OPTIONS 처리 추가 |
| `CORS error` + 200 OK | CORS | 응답은 왔지만 CORS 헤더가 없거나 잘못됨 | `Access-Control-Allow-*` 헤더 확인 |

<br>

 감별의 핵심은, **에러가 어느 단계에서 발생했는지를 먼저 파악하는 것**이다.

```
[브라우저 요청]
    │
    ├── DNS 실패 → net::ERR_NAME_NOT_RESOLVED
    │   └── CORS 이전 단계. 네트워크 설정 문제.
    │
    ├── TCP 실패 → net::ERR_CONNECTION_REFUSED
    │   └── CORS 이전 단계. 서버가 안 떠 있거나 포트/방화벽 문제.
    │
    ├── OPTIONS 요청 → 405 Method Not Allowed
    │   └── 서버가 OPTIONS를 처리하지 못함.
    │       nginx 또는 백엔드에서 OPTIONS 처리 필요.
    │
    ├── OPTIONS 요청 → 200/204 but CORS 헤더 없음
    │   └── Preflight는 성공했지만, CORS 헤더가 빠져 있음.
    │       add_header 설정 확인 (always 키워드 포함).
    │
    └── 실제 요청 → 200 OK but 브라우저에서 차단
        └── 응답은 성공했지만, CORS 헤더가 없어
            브라우저가 JavaScript에 응답을 전달하지 않음.
            Access-Control-Allow-Origin 헤더 확인.
```

 특히, `405 Method Not Allowed` 에러는 CORS 문제처럼 보이지만, 실제로는 서버가 OPTIONS 메서드를 처리하지 못해서 발생하는 것이다. Preflight에서 OPTIONS 요청이 발생했는데, 서버가 이 메서드를 지원하지 않으면 405를 반환한다. 이 경우, nginx에서 OPTIONS를 직접 처리하거나, 백엔드에서 OPTIONS 메서드를 허용하도록 설정하면 해결된다.

 또한, 브라우저 개발자 도구의 Network 탭에서 요청과 응답의 헤더를 직접 확인하는 것이 가장 확실한 디버깅 방법이다. 응답에 `Access-Control-Allow-Origin` 헤더가 있는지, 그 값이 현재 Origin과 정확히 일치하는지 확인하자.



<br>

## CORS에 대한 고찰

아래는 CORS 관련 상황을 겪을 때마다, 항상 내가 궁금했던 부분이다. 개념을 제대로 알고 공부하고 보니, 내가 어떤 부분을 헷갈렸는지 궁금증을 조금은 정리할 수 있어, 기록 차원에서 남겨 둔다. 

- 도대체 브라우저에서 막는 걸 왜 서버에서 **허가**해주는 거지?

  - 브라우저도 결국 프로그램일 뿐이라, 어떤 서버가 안전하고 안전하지 않은지 알 방법이 없음
  - 그러니 cross origin 리소스 서버가 리소스를 가져 가도 된다고 알려 주면, 브라우저는 그 서버를 신뢰하는 것
  - 서버에서 허가하는 메커니즘이라는 표현이 헷갈릴 수 있지만, 허가라기보다는 안전한 서버라는 신호를 주는 것이라고 봐도 됨

  > The browser won't allow cross-origin request **unless** the server **explicitly says it's okay.** The server isn't enabling the request—the server is signaling trust to the browser, and the browser decides whether to allow it.

- 그러면 애초에 이런 메커니즘을 클라이언트 코드 단에서 해 버리면 안 되나? 자바스크립트 코드에서?

  - 그러면 애초에 Same Origin Policy를 도입한 이유가 없음

- 어떤 악의적인 사이트에서 CORS 요청을 다 허가해 줘 버리면, 그럼 그냥 그 사이트에서의 리소스는 다 뜨는 거 아닌가?

  - 그건 CORS가 하는 일이 아님
    - CORS는 브라우저랑 서버 간에 안전하다는 것을 확인하기 위한 메커니즘이지, 그 서버가 안전한지 아닌지를 판별하는 메커니즘이 아님
  - CORS가 해결해야 할 일도 아님
    - 무슨 말이냐 하면, 브라우저에서 로드해야 하는 자원에 악의적인 사이트가 포함되어 있다면, 그건 웹 어플리케이션 코드를 점검해야 할 일 
    - 애초에 개발자 입장에서 신뢰할 수 있는 사이트에서 리소스를 가져 오도록 해야 할 일
    - 어쩌다 실수로(*혹은 고의로*) 악의적인 사이트로부터 리소스를 가져오도록 되어 있다고 하고, 그 악의적인 사이트가 CORS 허용 설정을 해 두었더라도, 그건 CORS로 인해 발생한 문제가 아니라는 것
  - 만약에 이런 걸 더 자세히 알아 보고 싶다면, CSP(Content Security Policy), Sanitization 관련 개념을 더 살펴 보는 것이 좋다고 함





<br>

<br>

- *참고*
  - [https://developer.mozilla.org/en-US/docs/Web/Security/Same-origin_policy](https://developer.mozilla.org/en-US/docs/Web/Security/Same-origin_policy)
  - [https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/CORS](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/CORS)
  - [https://medium.com/@lifthus531/cors%EC%97%90-%EB%8C%80%ED%95%9C-%EA%B9%8A%EC%9D%80-%EC%9D%B4%ED%95%B4-8c84c2137c83](https://medium.com/@lifthus531/cors%EC%97%90-%EB%8C%80%ED%95%9C-%EA%B9%8A%EC%9D%80-%EC%9D%B4%ED%95%B4-8c84c2137c83)
  - [https://velog.io/@kansun12/%ED%94%84%EB%A1%A0%ED%8A%B8%EC%97%94%EB%93%9C-CORS](https://velog.io/@kansun12/%ED%94%84%EB%A1%A0%ED%8A%B8%EC%97%94%EB%93%9C-CORS)





