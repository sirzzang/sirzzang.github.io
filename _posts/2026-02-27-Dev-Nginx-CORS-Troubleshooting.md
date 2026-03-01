---
title:  "[nginx] CORS 상황 해결: 같은 도메인의 다른 nginx가 응답하고 있었다"
excerpt: "프론트엔드 로그인 시 405 에러의 원인을 추적하고, 같은 도메인에 nginx가 여러 개 떠 있을 때의 함정을 정리해 보자."
categories:
  - Dev
toc: true
header:
  teaser: /assets/images/blog-Dev.jpg
tags:
  - nginx
  - CORS
  - Vite
  - Docker
  - 트러블슈팅
  - Reverse Proxy
---

<br>

클라우드(AWS EC2)에서 운영하던 서비스를 사내 외부 접근이 가능한 온프레미스 서버로 마이그레이션하게 되었다. 프론트엔드를 옮긴 뒤 로그인을 시도하니 CORS 에러가 발생했다. nginx CORS 설정 문제인 줄 알고 한참을 들여다봤는데, 알고 보니 전혀 다른 곳이었다. 같은 도메인에 nginx 컨테이너가 2개 떠 있었고, 요청이 의도하지 않은 nginx로 가고 있었다.

SOP와 Origin의 기본 개념은 [Origin에 대한 고찰 - 정의, SOP, CORS]({% post_url 2025-05-10-CS-Origin-SOP-CORS %})에 정리한 적이 있다. 이번 트러블슈팅은 그 개념이 실제 nginx 프록시 아키텍처에서 어떻게 작동하는지를 경험한 사례다.

<br>

# TL;DR

- **현상**: 프론트엔드 로그인 시 OPTIONS preflight → 405 Method Not Allowed
- **근본 원인**: `.env.production`에 `VITE_API_URL=https://foo.example.com/`(절대 경로)으로 설정되어 있어, 브라우저가 API 요청을 같은 도메인의 다른 nginx(포트 443의 `proxy-server`)로 보냄
- **혼란 포인트**: 응답 헤더 `Server: nginx`가 찍혀서, 프론트 nginx가 차단한 것처럼 보였음
- **해결**: `VITE_API_URL=/` 상대 경로로 변경 → 재빌드 → 컨테이너 재시작
- **교훈**: CORS 에러 시 응답 주체가 누구인지 먼저 확인

<br>

# 배경

## 마이그레이션 맥락

클라우드(AWS EC2)에서 운영하던 MLOps 서비스를 사내 서버(외부 접근 가능)로 마이그레이션하기로 결정했다. 프론트엔드도 이 과정에서 함께 옮기게 되었는데, 마이그레이션 후 새 환경에서 로그인을 시도하니 CORS 에러가 발생했다.

## 인프라 구성

마이그레이션 대상 서버에는 이미 Docker 컨테이너 여러 개가 운영되고 있었다.

```
[외부] → proxy-server (443, TLS 종단) → 각 서비스 컨테이너
                                          ├─ ws-bar (40000)
                                          └─ api-service (40005)

[외부] → frontend-app (8004) ← 직접 노출 (과도기적 상태)
```

- **proxy-server**: L7 진입점 리버스 프록시. 포트 443에서 TLS를 종단하고, 요청 path에 따라 내부 서비스로 라우팅한다.
- **frontend-app**: 이번에 추가된 프론트엔드 앱 nginx. 포트 8004(내부 포트 80)에서 정적 파일을 서빙하고, `/api` 요청은 `proxy_pass`로 백엔드에 전달한다.

둘 다 nginx이지만, 역할이 완전히 다르다. 클라우드로 치면 proxy-server는 ALB/Ingress Controller에 해당하고, frontend-app은 Pod 안의 nginx sidecar에 해당한다. 포워드 프록시와 리버스 프록시의 개념 차이는 [Proxy / Reverse Proxy]({% post_url 2026-02-27-CS-Proxy-Reverse-Proxy %})에 정리했다. 이번 케이스에서 등장하는 두 nginx가 각각 어떤 역할인지 이해하려면 이 글을 먼저 읽는 게 도움이 된다.

문제는, frontend-app이 proxy-server에 등록되지 않은 채로 8004 포트에 직접 노출되어 있었다는 점이다. 이 과도기적 상태가 이번 트러블슈팅의 출발점이 되었다.

<br>

# 배경 지식

## VITE_API_URL: 빌드 타임 vs 런타임

이번 문제를 이해하려면 Vite의 환경변수 주입 방식을 알아야 한다. Vite는 프론트엔드 빌드 도구로, `VITE_` 접두사가 붙은 환경변수를 빌드 시점에 번들 JS에 **문자열로** 주입한다. Vite는 빌드 모드에 따라 환경변수 파일을 자동으로 로드하는데, 프로덕션 빌드(`vite build`)에서는 `.env.production`을 읽는다.

핵심은 **빌드 타임**과 **런타임**의 구분이다.

1. **빌드 타임** (`yarn build` → 내부적으로 `vite build`): Vite가 프로덕션 환경변수 파일(`.env.production`)의 `VITE_API_URL` 값을 번들에 문자열로 치환한다. 상대 경로인지 절대 경로인지 의미를 해석하지 않는다. 문자열을 그대로 주입할 뿐이다.

    ```jsx
    // 빌드 결과물 (dist/assets/index-xxxx.js)
    const API_BASE_URL = "/";  // ← 그냥 문자열 "/"
    ```

2. **런타임** (브라우저): 유저가 `http://foo.example.com:8004`에 접속하면 JS가 실행되고, 브라우저가 URL을 해석한다.

    ```jsx
    axios.post("/" + "api/user/login")
    // → axios.post("/api/user/login")
    ```

실제 런타임에 경로를 해석하는 주체는 Vite가 아니라 **브라우저**다. Vite는 문자열 치환만 하면 역할이 끝난다. 이후는 nginx + 인프라의 영역이다.

### 상대 경로 vs 절대 경로

| 설정 | 요청이 가는 곳 | 이유 |
| --- | --- | --- |
| `VITE_API_URL=/` | `http://foo.example.com:8004/api/...` | 브라우저가 현재 origin 기준으로 해석 → **Same-Origin** |
| `VITE_API_URL=https://foo.example.com/` | `https://foo.example.com/api/...` | 절대 경로 그대로 → 포트 443의 proxy-server → **Cross-Origin** |

같은 코드, 같은 빌드 결과물인데도, `.env.production`에 뭘 넣어줬느냐에 따라 요청이 완전히 다른 서버로 갈 수 있다. **누가 설정했느냐보다, 설정값이 최종 배포 환경의 origin과 일치하는가**가 핵심이다. 상대 경로(`/`)로 하면 이걸 자동으로 보장해 주니까 안전하다.

> nginx 프록시 뒤에 배포하는 경우, `/`(상대 경로)를 쓰는 게 베스트 프랙티스다. 다만 개발 초기에는 `VITE_API_URL=http://10.0.1.100:30001`처럼 백엔드를 직접 호출하는 절대 경로로 시작하는 경우가 많다. 프록시 구성이 완료되면 `/`로 바꿔야 한다.

<br>

## nginx 리버스 프록시 관련 설정

이번 케이스의 프론트 nginx 설정을 읽으려면 몇 가지 nginx 지시어를 알아야 한다. 아래에서 상황 섹션의 conf를 볼 때 참고한다.

### location 매칭 규칙

nginx는 요청 URI에 따라 어떤 `location` 블록이 처리할지를 결정한다. 매칭 우선순위는 다음과 같다.

| 문법 | 유형 | 우선순위 | 설명 |
| --- | --- | --- | --- |
| `location = /path` | 정확 매칭 | 1 (최우선) | `/path`만 매칭 |
| `location ^~ /path` | 접두사 매칭 (정규식 스킵) | 2 | `/path`로 시작하면 매칭, 이후 정규식 검사를 건너뜀 |
| `location ~ regex` | 정규식 매칭 (대소문자 구분) | 3 | 정규식에 매칭되는 URI |
| `location ~* regex` | 정규식 매칭 (대소문자 무시) | 3 | 위와 동일, 대소문자 무시 |
| `location /path` | 일반 접두사 매칭 | 4 | `/path`로 시작하면 매칭 (정규식에 밀릴 수 있음) |

특히 `^~`가 중요하다. 정적 파일 캐싱용 정규식(`location ~* \.(js|css|png|...)$`)이 있을 때, `/api/user/login.json` 같은 요청이 이 정규식에 걸리는 걸 방어한다. `location ^~ /api`로 선언하면 `/api`로 시작하는 요청은 정규식 검사를 아예 건너뛴다.

### try_files: SPA 라우팅 지원

`try_files $uri $uri/ /index.html`은 SPA 폴백 설정이다. 요청된 파일이나 디렉토리가 없으면 `index.html`을 반환해서, 클라이언트 사이드 라우터(React Router 등)가 URL을 처리할 수 있게 한다.

### proxy_set_header: 원본 정보 전달

리버스 프록시가 요청을 중계할 때 원본 클라이언트 정보(호스트, IP)가 유실될 수 있다. `proxy_set_header Host $host`와 `proxy_set_header X-Real-IP $remote_addr`로 원본 정보를 백엔드에 전달한다. 자세한 내용은 [Proxy / Reverse Proxy - 원본 정보 전달]({% post_url 2026-02-27-CS-Proxy-Reverse-Proxy %}#원본-정보-전달)을 참고한다.

<br>

# 상황

## 프론트엔드 코드와 설정

프론트엔드 코드에서는 `VITE_API_URL` 환경변수를 기반으로 API base URL을 설정하고 있었다.

```jsx
const API_BASE_URL = import.meta.env.VITE_API_URL || '';

export const publicAxios = axios.create({
    baseURL: API_BASE_URL,
});

// 로그인 호출
const res = await publicAxios.post('/api/user/login', {
    username: id,
    password: pw,
});
```

`.env.production` 파일에는 다음과 같이 설정되어 있었다.

```bash
# .env.production
VITE_API_URL=https://foo.example.com
```

## nginx 설정

프론트 nginx(`frontend-app`)의 설정을 확인해 보자.

```nginx
server {
    listen 80;

    set $allow_origin "";
    if ($http_origin ~* "^https?://(10\.0\.1\.\d+|localhost|127\.0\.0\.1)(:\d+)?$") {
        set $allow_origin $http_origin;
    }

    location / {
        root /var/www/html;
        index index.html;
        try_files $uri $uri/ /index.html;

        add_header 'Access-Control-Allow-Origin' $allow_origin always;
        add_header 'Access-Control-Allow-Methods' 'GET, POST, PUT, DELETE, OPTIONS' always;
        add_header 'Access-Control-Allow-Headers' 'Origin, Content-Type, Accept, Authorization' always;
        add_header 'Access-Control-Allow-Credentials' 'true' always;

        if ($request_method = 'OPTIONS') {
            return 204;
        }
    }

    location ^~ /api {
        proxy_pass http://10.0.1.100:30001;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;

        add_header 'Access-Control-Allow-Origin' $allow_origin always;
        add_header 'Access-Control-Allow-Methods' 'GET, POST, PUT, DELETE, OPTIONS' always;
        add_header 'Access-Control-Allow-Headers' 'Origin, Content-Type, Accept, Authorization' always;
        add_header 'Access-Control-Allow-Credentials' 'true' always;

        if ($request_method = 'OPTIONS') {
            return 204;
        }
    }
}
```

설정을 하나씩 짚어 보면 (각 지시어의 배경은 [배경 지식 > nginx 리버스 프록시 관련 설정](#nginx-리버스-프록시-관련-설정) 참고):

- **`location /`**: 프론트엔드 정적 파일을 서빙한다. [`try_files $uri $uri/ /index.html`](#try_files-spa-라우팅-지원)은 SPA 라우팅 지원 설정으로, 파일이 없으면 `index.html`을 반환한다.
- **`location ^~ /api`**: `/api`로 시작하는 요청을 백엔드로 프록시한다. [`^~`](#location-매칭-규칙)는 접두사 매칭 시 정규식 검사를 건너뛰는 수식어로, 정적 파일 캐싱용 정규식이 `/api` 요청을 가로채는 것을 방어한다.
- **`proxy_pass`, [`proxy_set_header`](#proxy_set_header-원본-정보-전달)**: nginx가 서버 사이드에서 백엔드로 요청을 중계한다. 브라우저는 이 과정을 모르므로 Same-Origin이 유지된다. `Host`와 `X-Real-IP` 헤더 전달은 리버스 프록시에서의 [원본 정보 전달]({% post_url 2026-02-27-CS-Proxy-Reverse-Proxy %}#원본-정보-전달) 목적이다.
- **CORS 헤더 + OPTIONS 처리**: `add_header ... always`로 모든 응답(에러 응답 포함)에 CORS 헤더를 추가하고, OPTIONS preflight는 백엔드까지 보내지 않고 204로 즉시 반환한다. 백엔드(Go gin)에도 CORS 미들웨어가 있지만, nginx에서 방어적으로 이중 처리한 구성이다. Same-Origin 상태에서는 실질적으로 불필요하지만, 아키텍처 변경 대비용이다. CORS 처리에 대한 자세한 내용은 [Origin에 대한 고찰]({% post_url 2025-05-10-CS-Origin-SOP-CORS %}#nginx에서-options를-처리하는-이유)을 참고한다.

정리하면, **CORS 설정은 잘 되어 있고, OPTIONS도 204로 처리하고 있었다.** 이 nginx를 요청이 거쳤다면 문제가 없어야 했다.


## Docker Compose 설정

Docker Compose로 8004:80 포트 매핑으로 운영 중이었다.

```yaml
services:
  frontend-app:
    build:
      context: .
      dockerfile: infra/docker/Dockerfile
    container_name: frontend-app
    ports:
      - "8004:80"
    volumes:
      - ./infra/nginx/default.conf.template:/etc/nginx/templates/default.conf.template:ro
    environment:
      - NGINX_ENVSUBST_OUTPUT_DIR=/etc/nginx/conf.d
    env_file:
      - .env.production
```

nginx 공식 Docker 이미지의 `NGINX_ENVSUBST_OUTPUT_DIR` 기능을 사용하고 있었다. 컨테이너 시작 시 `/etc/nginx/templates/*.template` 파일에서 `${ENV_VAR}`를 실제 환경변수 값으로 치환해서 실제 nginx conf를 생성하는 방식이다.

<br>

# 문제 분석

## 증상

프론트엔드에서 로그인 시, 브라우저 네트워크 탭에 OPTIONS 요청만 찍히고 실제 POST 요청은 보이지 않았다. 에러는 **405 Method Not Allowed**. 응답 헤더에 `Server: nginx`가 찍혀 있었다.

정상이라면 OPTIONS preflight는 프론트 nginx(8004)를 거치거나, 거친 뒤 백엔드로 전달되어야 한다. 그런데 **백엔드 로그에 OPTIONS 조차 찍히지 않았다.** 요청이 우리가 CORS를 설정해 둔 그 nginx로 간 게 아니라는 뜻이다. 이걸 보고 "혹시 포트 443의 다른 서버가 받고 있는 건 아닐까?" 하는 의심이 생겼다.

## 요청 흐름 분석: 왜 Cross-Origin이 되었나

`.env.production`에 `VITE_API_URL=https://foo.example.com/`이 설정되어 있었으므로, 빌드된 JS에서 API 요청 URL이 절대 경로로 생성되었다.
- 브라우저 origin: http://foo.example.com:8004 (프론트 nginx, HTTP)
- 요청 URL: https://foo.example.com/api/user/login (절대 경로)

<br>
브라우저의 Same-Origin 판단:
- 프로토콜 다름: `http` vs `https`
- 포트 다름: `8004` vs `443` (https 기본 포트)
- → **Cross-Origin**

Cross-Origin 요청에 `Content-Type: application/json`을 사용하므로 Simple Request 조건을 만족하지 못한다. 
> Preflight 요청의 조건과 흐름에 대해서는 [사전 요청 섹션]({% post_url 2025-05-10-CS-Origin-SOP-CORS %}#사전-요청preflight-request)을 참고한다.

<br>

**정상이어야 할 흐름**은 다음과 같다. 상대 경로(`/`)였다면 요청이 같은 origin(8004)으로 가고, 프론트 nginx가 OPTIONS에 204를 반환하거나 proxy_pass로 백엔드까지 전달했을 것이다.

```
브라우저 → OPTIONS /api/user/login (origin 8004)
         → 프론트 nginx (8004) 수신
         → 204 또는 백엔드 전달
         → Preflight 성공
         → POST 요청 발생
```

**실제로는** 절대 경로 때문에 브라우저가 OPTIONS를 `https://foo.example.com`(포트 443)으로 보냈다. 443에서 받는 쪽은 프론트 nginx가 아니다(프론트는 8004·HTTP). 그쪽에서 405를 돌려주면서 preflight가 실패했고, POST는 아예 나가지 않았다.

```
브라우저 → OPTIONS https://foo.example.com/api/user/login (→ 포트 443)
         → 405 Method Not Allowed (443에서 응답한 서버)
         → Preflight 실패
         → POST 요청 자체를 보내지 않음
```

결정적인 단서는 **백엔드 로그에 OPTIONS조차 없다**는 점이다. OPTIONS가 프론트 nginx를 거쳤다면 proxy_pass로 백엔드까지 전달되어 로그에 남았을 것이다. 로그에 없다는 건 요청이 프론트 nginx로 가지 않았다는 뜻이고, 따라서 "포트 443의 어떤 서버가 받은 것"이라는 추론으로 이어진다.

<br>

## 백엔드 CORS 설정 확인

CORS 에러로 보였기 때문에 트러블슈팅 시 **백엔드 설정을 먼저** 살펴봤다. 백엔드(Go gin)에는 CORS 미들웨어(예: `gin-contrib/cors`)가 붙어 있었고, `AllowOrigins`, `AllowMethods`, `AllowHeaders`가 설정되어 있었으며 OPTIONS 요청은 미들웨어에서 204로 처리하도록 되어 있었다. 즉 백엔드만 보면 CORS 설정은 정상이었고, 요청이 백엔드까지 도달했다면 거기서 preflight가 처리됐을 것이다. 

물론 백엔드 설정이 완벽하지 않았을 가능성도 있다. 그런데 백엔드 로그에 OPTIONS가 전혀 찍히지 않았다. 결과적으로 문제는 요청이 백엔드에 도달하기 **전** 단계—어딘가에서 405를 반환하고 있다—로 좁혀졌다. 

<br>

# 원인 추적

## 프론트 nginx는 정상이었다

응답 주체를 좁혀 나갔다. 프론트 nginx(`frontend-app`)에는 CORS 설정이 분명히 잘 되어 있었다. 컨테이너 안에 직접 들어가서 확인해 봐도 환경변수가 정상 치환되어 있었고, OPTIONS 요청에 대한 204 반환 설정도 있었다.

```bash
# 프론트엔드 nginx 컨테이너 내부에서 확인
$ cat /etc/nginx/conf.d/default.conf
# → CORS 헤더 설정 정상
# → OPTIONS → 204 설정 정상
# → proxy_pass 대상 IP/포트 정상
```

만약 이 nginx를 거쳤다면 문제가 없어야 했다. **그런데 백엔드 로그에 OPTIONS·POST 둘 다 안 찍힌다.** 게다가 프론트 nginx는 **HTTP**(포트 80, 외부 8004)로 서빙하는데, 브라우저가 보낸 요청은 **HTTPS**(포트 443)로 가고 있었다. 응답 주체가 프론트 nginx가 아닌 건 명확했다.

## curl -v로 재현

의심을 확인하기 위해 같은 OPTIONS 요청을 `curl -v`로 보내봤다.

```bash
curl -X OPTIONS https://foo.example.com/api/user/login \
  -H "Origin: http://foo.example.com:8004" \
  -H "Access-Control-Request-Method: POST" \
  -H "Access-Control-Request-Headers: content-type" \
  -v
```

결과를 보니, TLS handshake가 맺어지고 있었다. 포트 443으로 연결되어 HTTPS 통신이 이루어졌다.

```
*   Trying <ip>:443...
* Connected to foo.example.com (<ip>) port 443 (#0)
* TLSv1.3 (OUT), TLS handshake, Client hello (1):
...
* SSL connection using TLSv1.3 / TLS_AES_256_GCM_SHA384
* Server certificate:
*  subject: CN=foo.example.com
...
> OPTIONS /api/user/login HTTP/1.1
> Host: foo.example.com
> Origin: http://foo.example.com:8004
> Access-Control-Request-Method: POST
> Access-Control-Request-Headers: content-type
>
< HTTP/1.1 405 Not Allowed
< Server: nginx/1.29.1
< Content-Type: text/html
< Content-Length: 157
<
<html>
<head><title>405 Not Allowed</title></head>
<body>
<center><h1>405 Not Allowed</h1></center>
<hr><center>nginx/1.29.1</center>
</body>
</html>
```

응답의 `Server: nginx/1.29.1`을 보는 순간 의문이 들었다. 우리 프론트 nginx 이미지의 버전은 **1.19.6**이었다. 버전이 다르다. **이건 우리 프론트 nginx가 아니다.**

## 진짜 원인: 같은 도메인의 다른 nginx

해당 서버의 컨테이너 목록을 확인해 봤다.

```bash
$ docker ps
CONTAINER ID   IMAGE              PORTS                                        NAMES
73d02c0acba5   frontend-app       0.0.0.0:8004->80/tcp                         frontend-app
9d7f3d89b9d1   nginx:latest       0.0.0.0:80->80/tcp, 0.0.0.0:443->443/tcp    proxy-server
482162960f95   api-service        0.0.0.0:40005->40005/tcp                     api-service
ee6db37e989c   golang:alpine      0.0.0.0:40000->40000/tcp                     ws-bar
```

**`proxy-server`라는 이름의 nginx 컨테이너가 포트 443에서 돌고 있었다.**(..!) 이 컨테이너의 nginx 설정을 확인해 봤다.

```nginx
# proxy-server의 /etc/nginx/conf.d/default.conf
server {
    server_name  foo.example.com;

    # Security Headers
    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;
    add_header X-Frame-Options "DENY" always;
    # ...

    location / {
        root   /usr/share/nginx/html;
        index  index.html index.htm;
    }

    location /bar/ {
        proxy_pass http://ws-bar:40000/;
        # WebSocket 관련 헤더...
    }

    location /secondary/ {
        proxy_pass http://api-service:40005;
        # ...
    }

    listen 443 ssl;
    ssl_certificate /etc/letsencrypt/live/foo.example.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/foo.example.com/privkey.pem;
}

server {
    listen       80;
    server_name  foo.example.com;
    return 301 https://$server_name$request_uri;
}
```

**`/api` 라우팅이 없다. CORS 설정도 없다. OPTIONS 처리도 없다.**

퍼즐이 맞춰졌다.

## 상황 도식 정리

이번 문제는 **요청이 CORS 설정이 있는 백엔드 서버에도, 프론트 nginx에 도달하지 못하고, 같은 도메인의 다른 nginx로 갔던 것**이 근본 원인이었다. 
- 문제의 **핵심 3단계**: 절대 경로(`VITE_API_URL=https://...`) → 443의 proxy-server가 수신 → `/api` 라우팅·CORS 설정 없음 → 405

![nginx-fe-troubleshooting-1.png]({{site.url}}/assets/images/nginx-fe-troubleshooting-1.png)

상세 흐름은 다음과 같다.

1. `VITE_API_URL=https://foo.example.com/`
2. `axios.post('https://foo.example.com/api/user/login')`
3. 브라우저 Same-Origin 판단: Cross-Origin
4. 브라우저 Preflight 요청 판단: Preflight 필요
5. `OPTIONS https://foo.example.com/api/user/login`
6. 포트 443의 proxy-server(nginx/1.29.1)가 받음
7. `/api` 라우팅 없음
8. CORS 설정 없음
9. 405 Method Not Allowed
10. Preflight 실패
11. POST 안 보냄

<br>

# 해결

결과적으로 요청은 **프론트 nginx**(CORS·OPTIONS 처리 설정이 되어 있던 곳)에도, **백엔드**(CORS 미들웨어가 붙어 있던 곳)에도 도달하지 않았다. 대신 CORS 설정이 전혀 없는 443의 다른 nginx가 OPTIONS를 받아 405를 돌려준, 참 웃픈 상황이었다. 아래에서는 이걸 어떻게 해결할 수 있는지, 채택한 방법과 대안을 정리한다.

## 방법 1: VITE_API_URL 상대 경로 설정 (채택)

`.env.production`을 수정하고 **재빌드** 후 컨테이너를 재시작했다.

```bash
# .env.production
VITE_API_URL=/
```

> **주의**: `VITE_` 접두사 환경변수는 빌드 시점에 번들 JS에 문자열로 주입된다. `.env.production`을 수정한 후 반드시 `yarn build`(또는 `vite build`)로 **재빌드**해야 변경이 반영된다. 컨테이너 재시작(`docker restart`)만으로는 이전 빌드의 값이 그대로 유지된다.

**방법 1 적용 시 흐름**은 다음과 같다.

![nginx-fe-troubleshooting-2.png]({{site.url}}/assets/images/nginx-fe-troubleshooting-2.png)

1. `VITE_API_URL=/`
2. `axios.post('/api/user/login')` (상대 경로)
3. 브라우저가 현재 origin(`http://foo.example.com:8004`) 기준으로 경로 해석
4. 요청 URL: `http://foo.example.com:8004/api/user/login`
5. 브라우저 Same-Origin 판단: Same-Origin
6. CORS 검사 없음
7. 프론트 nginx(8004)가 수신
8. `location ^~ /api` → proxy_pass로 백엔드 전달
9. 로그인 요청 정상 도달

다만 이렇게 할 경우, 8004 포트가 외부에 직접 노출된다. 문제는 해결하더라도, 아직 과도기적 상태가 유지된다. `VITE_API_URL=/`로 바꿔서 당장의 문제는 해결할 수 있겠지만, 마이그레이션 완료 후에는 proxy-server를 통한 통합 라우팅으로 전환해야 한다. 사용자에게 `:8004` 포트를 직접 입력하게 할 수는 없는 노릇이다.

## 방법 2: proxy-server에 라우팅 추가 (더 나은 아키텍처)

인프라 아키텍처 측면에서는 proxy-server에 프론트엔드와 API 라우팅을 모두 등록하는 것이 더 바람직하다.

```nginx
# proxy-server (443) 설정에 추가
server {
    listen 443 ssl;
    server_name foo.example.com;

    # 프론트엔드
    location / {
        proxy_pass http://frontend-app:80;
    }

    # API
    location /api {
        proxy_pass http://10.0.1.100:30001;
    }

    # 기존 서비스들...
}
```

이렇게 하면:
- 외부에는 443 하나만 노출
- `VITE_API_URL=/`(상대 경로)로 설정하면 모든 게 Same-Origin
- 8004 포트를 외부에 노출할 필요 없음

<br>

# 교훈

nginx CORS 쪽에 심오한 문제가 있는 줄 알았는데, 알고 보니 같은 도메인에 **다른 nginx 컨테이너**가 또 있어서 꽤 당황했다. "이런 구성이 있다"는 걸 미리 알았더라면 디버깅에 쏟은 삽질을 많이 줄였을 텐데 하는 아쉬움이 남았다.

## 이 구조가 흔한가

**리버스 프록시 + 앱별 nginx** 구조 자체는 온프레미스에서 굉장히 흔한 환경 구성이다.

```
[외부] → proxy-server (443, TLS 종단) → 각 서비스 컨테이너
                                          ├─ ws-bar (40000)
                                          ├─ api-service (40005)
                                          └─ frontend-app (8004) ← 여기가 빠져 있었음
```

nginx를 **2단**으로 쓰는 것이다.

1. **1단 (L7 진입점)** — `proxy-server`: 포트 443에서 TLS 종단하고, 요청 path에 따라 내부 서비스로 라우팅
2. **2단 (앱 레벨)** — `frontend-app`: 포트 8004(내부 80)에서 정적 파일 서빙 + `/api` proxy_pass

둘 다 nginx이지만 역할이 완전히 다르다. 클라우드로 치면 1단은 ALB/Ingress Controller, 2단은 Pod 안의 nginx sidecar에 해당한다. 클라우드에서는 1단 역할을 ALB/Ingress가 대신하니까 이런 이슈가 잘 안 보이지만, **온프레미스에서는 이 2단 구조가 꽤나 흔하다**.

## 이번 상황의 문제

같은 도메인에 nginx가 2개 떠 있는데 **역할이 다르고**, **한쪽(proxy-server)에만 라우팅이 설정되어 있지 않아서** 혼란이 났다. 과도기적 상태에서 생긴 일이다.

**추가된 순서를 역추적**해보자.

1. 태초에 `proxy-server`만 있었음 (443, HTTPS, bar·api-service 등)
2. 새 프론트엔드(frontend-app)를 추가하면서 Docker로 띄우고, 8004 포트로 **임시** 오픈
3. "나중에 proxy-server에 라우팅 추가해야지" → 그리고 잊음
4. `.env.production`에 `VITE_API_URL=https://foo.example.com/` 설정 → proxy-server를 거치도록 의도했지만, proxy-server에 `/api` 라우팅이 없었으므로 405

임시로 열어 둔 구성을 나중에 proxy-server에 반영했어야 하는데 잊어버리는 식으로 진행되면서 이렇게 됐다. **온프레미스에서 서비스를 붙여 나갈 때 정말 자주 나오는 실수**이고, 서비스 성장의 부산물이라고 보면 된다.

다만 이런 상황은 **디버깅이 어렵다.** 뚜껑을 열어 보면 간단한 상황임에도, 잘 모르니 생각보다 많은 시간을 낭비하게 된다.

- 에러 응답의 `Server: nginx`만 보면, 우리 프론트 nginx인지 다른 nginx인지 구분이 안 된다.
- 도메인이 같아서 "같은 서버인데 왜?"라는 착각이 생긴다.
- **nginx 버전**(`1.19.6` vs `1.29.1`)이 다르다는 걸 확인하고 나서야, 비로소 "이건 다른 nginx구나"를 알 수 있었다.

<br>

# 다음에는

## 예방

**1순위는 기존 인프라 구조를 먼저 확인하는 것이다.** 그다음에 신규 서비스를 어디에 붙일지 결정하는 게 안전하다.

임시로 포트를 열어서 노출할 때도, **proxy-server에 먼저 라우팅을 추가하는 쪽이 낫다.** nginx conf에 블록 하나 넣는 건 금방이고, "나중에 하겠지"하고 미루는 순간 잊기 쉽다. 정말 임시로 포트를 직접 열어야 한다면, **`VITE_API_URL`은 반드시 상대 경로(`/`)로** 잡아 두는 게 안전하다. 절대 경로를 쓰는 순간 "이 도메인의 어떤 포트로 갈지" 문제가 생겨 버린다.

### 체크 리스트

**신규 서비스 추가 시**, 아래와 같은 점을 체크하자:

1. `docker ps`로 같은 도메인에서 이미 돌고 있는 컨테이너 확인
2. 443/80 포트를 잡고 있는 프록시가 있는지 확인
3. 있으면 → **거기에 라우팅 추가가 우선**
4. 프론트 `VITE_API_URL`은 상대 경로(`/`) 기본

### 개발 영역과 인프라 영역의 합의

`VITE_API_URL` 같은 환경변수는 "프론트 영역이냐, 인프라 영역이냐"로 나누면 안 된다. **둘 다의 영역**이다.

| | 프론트엔드 개발자 | 인프라 팀 |
| --- | --- | --- |
| **책임** | `VITE_API_URL`을 **어떻게 쓸지** 설계 | 배포 환경에서 **실제 값을** 결정 |
| **구체적으로** | 코드에서 `import.meta.env.VITE_API_URL`을 base URL로 쓰는 구조 설계, `.env.development` 기본값 세팅 | `.env.production` 값 세팅, nginx 라우팅 구조와 일치시키기 |
| **알아야 하는 것** | 상대 경로(`/`) vs 절대 경로의 차이, 빌드 시점에 주입된다는 것 | 프론트가 이 값을 어떻게 쓰는지, 어떤 origin으로 요청이 나가는지 |

이번 케이스에서 생긴 갭을 복기해 보자. 프론트에서 `VITE_API_URL`을 쓰는 구조를 만들어 두었고, 인프라 설정 시 `.env.production`에 `https://foo.example.com/`을 넣었다. 인프라 입장에서는 `HTTPS 도메인으로 통일하면 된다`라는 의도였을 수 있지만, **이 값이 빌드 타임에 번들에 주입되어 브라우저가 그대로 요청 URL로 쓴다**는 걸 모르면, proxy-server에 `/api` 라우팅이 없다는 사실과 맞물려 깨진다. 한쪽이 다른 쪽의 맥락 없이 값을 바꾸면 깨지기 쉽다.

`VITE_API_URL`의 **"기본값 설계"는 프론트 개발자**, **"운영 환경에서 쓸 값 결정"은 인프라와 프론트가 함께 합의**해야 하는 영역이다. 체크리스트나 문서화가 중요한 부분이다.

따라서 인프라에서 이 환경변수를 바꿀 때에는 아래처럼 접근해야 한다.

1. 해당 환경변수가 빌드 결과물에 **어떻게 반영되는지** 확인
2. `VITE_` 접두사 환경변수는 **클라이언트 번들에 주입되고**, 런타임에 브라우저가 해석한다는 점 인지
3. nginx 라우팅 구조(`proxy_pass`)와 이 값이 **일치하는지** 검증

## 감지 (디버깅 팁)

CORS 에러가 났을 때, **응답을 준 서버가 내가 생각하는 그 서버가 맞는지를 먼저 의심하라.**

1. **요청이 실제로 어디까지 갔는지** — 백엔드 로그에 해당 요청이 찍혔는지 확인. 안 찍혔으면 백엔드까지 안 간 것이다.
2. **프로토콜/포트 교차 확인** — 브라우저 origin이 `http://...:8004`인데 요청이 `https://...`(443)으로 가고 있다면, 아예 다른 서버로 가고 있는 것이다.
3. **`curl -v`로 직접 재현** — TLS handshake 여부, 응답 서버 버전이 바로 보인다.
4. **`Server` 헤더의 nginx 버전** — 이번 케이스의 결정적 단서. `nginx/1.19.6` vs `nginx/1.29.1`. 버전이 다르면 다른 nginx다.
5. **응답 body의 에러 페이지 스타일** — nginx 기본 에러 페이지 하단에 버전이 찍힌다 (`<center>nginx/1.29.1</center>`).
6. **`X-Served-By` 커스텀 헤더 (예방적)** — 각 nginx에 구분용 헤더(`add_header X-Served-By "proxy-server" always`)를 넣어두면, 응답 헤더만 봐도 어떤 nginx가 응답했는지 즉시 알 수 있다. 비용은 거의 없으면서 효과가 크다. 온프레미스에서 nginx를 여러 개 운영할 경우, 습관적으로 넣어 두자.
7. **TLS 여부** — `http`로 서빙하는 nginx로 갔으면 TLS handshake가 없고, `https`(443) nginx로 갔으면 있다. `curl -v`에서 바로 보인다.

<br>

# 결론

CORS 설정이 아무리 잘 되어 있어도, **요청이 그 설정이 있는 서버로 가야** 의미가 있다. 이번 케이스에서는 같은 도메인에 nginx 컨테이너가 2개 떠 있었고, `VITE_API_URL` 절대 경로 설정 때문에 요청이 의도하지 않은 nginx로 갔다. 단순히 "CORS 에러 → CORS 설정 확인"이 아니라, **"응답을 준 주체가 누구인지"**를 먼저 확인하는 습관이 중요하다.

이번 경험이 좋은 안테나가 될 수 있을 것 같다. 같은 상황을 다시 마주했을 때 예방·감지 둘 다 더 빨리 할 수 있을 것이다.

<br>

<!-- ## 참고: nginx CORS 설정 딥다이브

아래는 위 트러블슈팅 과정에서 파고든 배경지식(nginx CORS 설정 상세, Preflight 패턴, 백엔드 이중 방어, 에러 감별법)을 참고용으로 정리한 것이다.

### TL;DR

- nginx에서 CORS를 처리하는 이유: 중앙 집중 관리, 백엔드 부담 경감, 일관성
- OPTIONS preflight 처리 패턴: `if` 블록 vs `error_page 418` 트릭
- 백엔드에도 CORS를 유지해야 하는 이유: 로컬 개발, 아키텍처 변경 대응, 이중 방어
- 에러 감별법: DNS → TCP → 서버 응답 → CORS 단계별 구분

<br>

### nginx에서의 CORS 설정

#### 왜 nginx에서 처리하는가

백엔드에서도 CORS 설정을 할 수 있지만, nginx(리버스 프록시)에서 처리하는 게 실무에서 더 일반적이다.

- **중앙 집중 관리**: 백엔드가 여러 개여도 nginx 한 곳에서 CORS 정책을 통일할 수 있다.
- **백엔드 부담 경감**: OPTIONS preflight 요청을 nginx에서 204로 바로 끊어주면, 백엔드까지 도달하지 않는다.
- **일관성**: 백엔드 프레임워크마다 CORS 미들웨어 설정 방식이 다른데, nginx에서 통일하면 실수가 줄어든다.

<br>

#### 핵심 CORS 헤더 4개

| 헤더 | 역할 | 예시 |
| --- | --- | --- |
| `Access-Control-Allow-Origin` | 이 origin에서 온 요청을 허용 | `$allow_origin` 또는 `*` |
| `Access-Control-Allow-Methods` | 허용하는 HTTP 메서드 | `GET, POST, PUT, DELETE, OPTIONS` |
| `Access-Control-Allow-Headers` | 허용하는 요청 헤더 | `Content-Type, Authorization` |
| `Access-Control-Allow-Credentials` | 쿠키/인증 정보 포함 허용 여부 | `true` |

이 중 하나라도 빠지거나 값이 맞지 않으면 브라우저가 응답을 차단한다. 참고로 `Allow-Origin`이 `*`이면서 `Allow-Credentials`가 `true`이면, 브라우저가 거부한다(보안 정책).

<br>

#### OPTIONS preflight 처리 패턴

브라우저가 Cross-Origin 요청 전에 보내는 "사전 확인" 요청을 nginx에서 처리하는 대표적인 패턴 두 가지가 있다.

**패턴 1: if 블록**

```nginx
location ^~ /api {
    proxy_pass http://backend;
    add_header 'Access-Control-Allow-Origin' $allow_origin always;
    add_header 'Access-Control-Allow-Methods' 'GET, POST, PUT, DELETE, OPTIONS' always;
    add_header 'Access-Control-Allow-Headers' 'Origin, Content-Type, Accept, Authorization' always;
    add_header 'Access-Control-Allow-Credentials' 'true' always;

    if ($request_method = 'OPTIONS') {
        return 204;
    }
}
```

- **장점**: 간결하다.
- **단점**: nginx의 "if is evil" 문제 — `if` 안에서 `proxy_pass`나 다른 지시어와 예기치 않은 상호작용이 있을 수 있다.

**패턴 2: error_page 418 트릭**

```nginx
location /api {
    error_page 418 = @cors_preflight;
    if ($request_method = OPTIONS) {
        return 418;
    }

    proxy_pass http://backend;
    add_header 'Access-Control-Allow-Origin' $cors_origin always;
    add_header 'Access-Control-Allow-Methods' 'GET, POST, PUT, DELETE, PATCH, OPTIONS' always;
    add_header 'Access-Control-Allow-Headers' 'Authorization, Content-Type, Accept' always;
}

location @cors_preflight {
    add_header 'Access-Control-Allow-Origin' $cors_origin;
    add_header 'Access-Control-Allow-Methods' 'GET, POST, PUT, DELETE, PATCH, OPTIONS';
    add_header 'Access-Control-Allow-Headers' 'Authorization, Content-Type, Accept';
    add_header 'Access-Control-Max-Age' 86400;  # 24시간 캐싱
    add_header 'Content-Type' 'text/plain; charset=utf-8';
    add_header 'Content-Length' 0;
    return 204;
}
```

- **장점**: `if` 블록과 `proxy_pass`를 분리해서 "if is evil" 문제를 회피한다.
- **추가 이점**: `Access-Control-Max-Age`로 preflight 결과를 캐싱할 수 있어, 반복적인 OPTIONS 요청을 줄인다.

418은 "I'm a teapot"이라는 장난 같은 HTTP 상태 코드인데, 실무에서는 이렇게 내부 라우팅 용도로 활용되기도 한다. OPTIONS 요청이 들어오면 일부러 418을 반환하게 하고, `error_page` 지시어로 `@cors_preflight` named location으로 리다이렉트하는 트릭이다.

<br>

#### $allow_origin 동적 패턴

`Access-Control-Allow-Origin`에 `*`를 쓰면 간편하지만, `Access-Control-Allow-Credentials: true`와 함께 쓸 수 없다(브라우저가 거부). 그래서 요청의 `Origin` 헤더를 정규식으로 검증한 뒤, 매칭되면 그 값을 그대로 응답에 돌려주는 패턴을 쓴다.

```nginx
set $allow_origin "";
if ($http_origin ~* "^https?://(10\.0\.1\.\d+|localhost|127\.0\.0\.1)(:\d+)?$") {
    set $allow_origin $http_origin;
}
```

이렇게 하면 **허용된 origin만 동적으로 반영**하면서 credentials도 사용 가능하다.

<br>

#### add_header always의 중요성

```nginx
add_header 'Access-Control-Allow-Origin' $allow_origin always;
```

`always`가 없으면 2xx, 3xx 응답에만 헤더가 추가된다. `always`가 있으면 4xx, 5xx 에러 응답에도 헤더가 붙는다.

CORS에서 이게 중요한 이유는, 에러 응답에 CORS 헤더가 없으면 **브라우저가 에러 내용조차 JS에 전달하지 않기 때문**이다. 예를 들어, 백엔드가 500 에러를 반환했는데 nginx의 `always` 설정이 없으면, 브라우저는 에러 응답에 CORS 헤더가 없으므로 응답 자체를 차단한다. 프론트엔드 개발자는 에러 메시지를 볼 수조차 없게 된다.

> 앞서 정리한 트러블슈팅 케이스에서는 `always` 자체가 의미가 없었다. 405 에러를 준 건 프론트 nginx가 아니라 `proxy-server`였고, `proxy-server`에는 CORS 설정 자체가 없었다. `always`든 아니든 CORS 헤더가 애초에 안 붙었다. 하지만 일반적인 상황에서는 `always`를 빠뜨리면 에러 디버깅이 매우 어려워진다.

<br>

#### Same-Origin인데 CORS 헤더를 붙이는 이유

nginx가 프론트 서빙 + API `proxy_pass`를 동시에 하면, 브라우저 입장에서 Same-Origin이다. Same-Origin이면 브라우저가 CORS 헤더를 체크하지 않으므로, 헤더가 있든 없든 상관없다.

그런데도 붙여두는 이유는 **방어적 설정**이다.

- 나중에 아키텍처가 바뀌어서 Cross-Origin이 될 수 있다.
- 로컬 개발 환경에서는 프론트(`localhost:3000`)와 nginx(다른 포트)가 Cross-Origin일 수 있다.
- 있어서 해가 되지 않고, 없으면 나중에 빠뜨릴 수 있다.

<br>

### Preflight는 언제 발생하는가

CORS와 Preflight의 기본 개념은 [Origin에 대한 고찰 - 정의, SOP, CORS]({% post_url 2025-05-10-CS-Origin-SOP-CORS %}#사전-요청preflight-request)에 정리해 두었다. 여기서는 실무에서 혼동하기 쉬운 부분을 짚는다.

#### Cross-Origin에서만 발생한다

Preflight(OPTIONS)는 **Cross-Origin 요청에서만** 발생한다. Same-Origin이면 CORS 메커니즘 자체가 적용되지 않으므로, `Content-Type: application/json`을 쓰든 커스텀 헤더를 넣든 Preflight가 발생하지 않는다.

| 상황 | Preflight 발생? |
| --- | --- |
| Same-Origin + `Content-Type: application/json` | 아니오 |
| Same-Origin + `Authorization` 헤더 | 아니오 |
| Cross-Origin + Simple Request 조건 충족 | 아니오 |
| Cross-Origin + `Content-Type: application/json` | **발생** |
| Cross-Origin + 커스텀 헤더 사용 | **발생** |

#### nginx에서 OPTIONS를 처리해 두는 이유

Same-Origin 구성이라면 OPTIONS 처리 설정은 당장 필요 없다. 하지만 다음과 같은 이유로 미리 설정해 두는 게 좋다.

- 아키텍처 변경으로 Cross-Origin이 될 수 있다.
- 로컬 개발 환경에서는 Cross-Origin이다.
- OPTIONS 요청이 들어왔을 때 백엔드까지 가지 않게 막아주는 것은, 불필요한 부하를 줄이는 효과도 있다.

```
# OPTIONS 처리가 없으면
브라우저 OPTIONS → Nginx → Backend (OPTIONS 처리 필요)
                          ↑ 불필요한 왕복

# OPTIONS 처리가 있으면
브라우저 OPTIONS → Nginx (204 즉시 반환)
                  ↑ 여기서 끝
```

<br>

### 백엔드 CORS 이중 방어

#### nginx만으로 충분한가

이론적으로는 nginx가 모든 CORS를 완벽하게 처리한다면 백엔드에서 CORS 설정을 할 필요가 없다. nginx가 OPTIONS를 직접 처리하고, 실제 요청 응답에도 `add_header ... always`로 CORS 헤더를 추가하면, 백엔드는 CORS를 전혀 신경 쓸 필요가 없다.

```
POST /api/user/login
  ↓
Backend: {"accessToken": "..."}  (CORS 헤더 없음)
  ↓
Nginx: add_header로 CORS 헤더 추가
  ↓
Browser: {"accessToken": "..."} + CORS 헤더
```

하지만 실무에서는 백엔드에도 CORS 설정을 유지한다.

#### 백엔드에도 CORS를 유지하는 이유

**로컬 개발 환경**

```bash
# 개발자 로컬 환경
npm run dev    # 프론트엔드 (localhost:3000)
go run main.go # 백엔드 (localhost:8080)

# Nginx 없음! 백엔드 CORS 설정 필요
```

개발 시에는 nginx 없이 프론트엔드 개발 서버와 백엔드를 직접 연결하는 경우가 많다. 포트가 다르므로 Cross-Origin이 되고, 백엔드에 CORS 설정이 없으면 개발 자체가 어려워진다.

**nginx 설정 실수 방어**

```nginx
# 실수로 always를 빼먹으면?
add_header 'Access-Control-Allow-Origin' $allow_origin;  # always 없음!
# → 2xx 응답에만 헤더 추가, 4xx/5xx는 헤더 없음 → CORS 에러!
```

**아키텍처 변경 대응**

```
현재: Browser → Nginx → Backend
미래: Browser → API Gateway → Backend
      Browser → Backend (직접 호출)
```

nginx 앞단 구성이 바뀌거나, 다른 서비스에서 직접 API를 호출하게 될 수도 있다.

**Defense in Depth**

```
Nginx CORS  ← 1차 방어
Backend CORS ← 2차 방어 (중복이지만 더 안전)
```

#### CORS 미들웨어

대부분의 웹 프레임워크에서는 CORS 미들웨어를 제공한다. 미들웨어 없이는 각 엔드포인트마다 OPTIONS 핸들러를 수동으로 추가해야 한다.

```go
// 미들웨어 없이 수동 처리
router.OPTIONS("/api/user/login", corsHandler)
router.POST("/api/user/login", handler.Login)
router.OPTIONS("/api/user/register", corsHandler)
router.POST("/api/user/register", handler.Register)
// ... 100개 엔드포인트마다 반복
```

미들웨어를 사용하면 한 번 설정으로 모든 엔드포인트에 자동 적용된다.

```go
// 미들웨어 사용
import "github.com/gin-contrib/cors"

router.Use(cors.New(cors.Config{
    AllowOrigins: []string{"http://foo.example.com:8004"},
    AllowMethods: []string{"GET", "POST", "PUT", "DELETE", "OPTIONS"},
    AllowHeaders: []string{"Content-Type", "Authorization"},
}))

router.POST("/api/user/login", handler.Login)
router.POST("/api/user/register", handler.Register)
// OPTIONS 핸들러 자동 추가
```

내부적으로는 이런 식으로 동작한다.

```
모든 요청 → CORS 미들웨어
               ↓
            OPTIONS? → 204 응답 (끝)
               ↓ No
            실제 핸들러로 전달
```

**실무 권장**: nginx에서 CORS를 주로 처리하되, 백엔드에도 CORS 미들웨어를 유지한다. 약간의 중복이지만, 유연성과 안전성 면에서 이점이 크다.

<br>

### 에러 유형별 감별법

CORS 에러처럼 보이지만, 실제로는 네트워크 단계에서 이미 실패한 경우가 있다. 에러가 **어느 단계에서 발생했는지**를 먼저 파악하는 것이 감별의 핵심이다.

| 상황 | 에러 | 시간 | Preflight | 특징 |
| --- | --- | --- | --- | --- |
| DNS 실패 (도메인 오타) | `ERR_NAME_NOT_RESOLVED` | ~2ms | 안 감 | 가장 빠르게 실패 |
| TCP 연결 거부 (서버 없음) | `ERR_CONNECTION_REFUSED` | ~100ms | 안 감 | DNS는 되지만 연결 안 됨 |
| 타임아웃 (방화벽 차단 등) | `ERR_TIMED_OUT` | ~30s | 안 감 | 가장 느리게 실패 |
| CORS 에러 (헤더 불일치) | 200 OK but blocked | ~100ms | 감 | 응답은 받았지만 브라우저가 차단 |
| 405 에러 (OPTIONS 미지원) | `405 Not Allowed` | ~100ms | 감 | 서버가 OPTIONS를 모름 |

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
    │       앞서 정리한 케이스가 바로 이것.
    │
    ├── OPTIONS 요청 → 204 but CORS 헤더 없음/불일치
    │   └── Preflight는 성공했지만, CORS 헤더가 빠져 있거나 값이 틀림.
    │
    └── 실제 요청 → 200 but CORS 에러
        └── 응답은 정상이지만, CORS 헤더가 없어서 브라우저가 차단.
            네트워크 탭에서는 보이지만, 코드에서는 접근 불가.
```

**DNS 실패**

```
❌ POST https://foo.example.co/api/user/login   ← 도메인 오타
net::ERR_NAME_NOT_RESOLVED
```

매우 빠르게 실패한다(수 ms). 서버 응답 없음. Preflight도 안 간다. CORS 에러가 아니다.

**연결 거부**

```
❌ POST http://foo.example.com:9999/api/user/login   ← 열려있지 않은 포트
net::ERR_CONNECTION_REFUSED
```

DNS 해석은 되지만 TCP 연결이 실패한다. 역시 CORS 에러가 아니다.

**Preflight 실패 → 405**

앞서 정리한 케이스가 바로 이것이다. OPTIONS 요청을 보냈는데 서버가 405를 반환했다. Preflight가 실패하면 브라우저는 본 요청(POST)을 아예 보내지 않는다. 네트워크 탭에 OPTIONS만 찍히고 POST는 흔적도 없다.

**CORS 헤더 불일치**

Preflight는 성공했지만, 실제 응답의 CORS 헤더가 없거나 값이 틀리면 브라우저가 응답을 차단한다. 네트워크 탭에서 응답은 보이지만, JS 코드에서는 접근할 수 없다.

<br>

### 참고 섹션 정리

- nginx에서 CORS를 처리하면 **중앙 집중 관리**의 이점이 크다. 하지만 위에서 경험했듯이, 요청이 그 nginx에 도달해야 의미가 있다.
- OPTIONS preflight 처리에는 `if` 블록과 `error_page 418` 트릭 두 가지 패턴이 있다. "if is evil" 문제를 회피하려면 후자가 낫다.
- 백엔드에도 CORS 설정을 유지하는 것이 실무 권장이다. 로컬 개발, nginx 설정 실수, 아키텍처 변경에 대비하는 이중 방어가 된다.
- CORS 에러를 디버깅할 때는 **에러가 어느 단계에서 발생했는지**를 먼저 파악해야 한다. DNS 실패, TCP 거부, Preflight 실패, CORS 헤더 불일치는 모두 증상이 다르다. -->

