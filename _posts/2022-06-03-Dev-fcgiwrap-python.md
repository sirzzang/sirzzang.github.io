---
title:  "[CGI] fcgiwrap으로 Python 스크립트를 실행하며 겪었던 문제 해결하기"
excerpt: FastCGI 방식으로 Python 스크립트를 실행할 때 마주했던 문제들
categories:
  - Dev
toc: true
header:
  teaser: /assets/images/blog-Dev.jpg
tags:
  - FastCGI
  - fcgiwrap
  - Python
  - Nginx
  - CGI
  - "502"
  - shebang
---



# fgciwrap + Python 삽질기

 회사에서 Nginx와 fastcgi 모듈을 이용해 서버를 개발하던 중, 502 Bad Gateway 에러를 종종 마주했다. [tcpdump](https://sirzzang.github.io/dev/Dev-tcpdump/){: .btn .btn--primary} 를 이용해 확인한 결과 fcgiwrap 프로세스에서 Python 스크립트를 실행할 수 없거나, 실행하였는데 요청이 올바르게 처리되지 않는 경우, fcgiwrap process socket 쪽에서 먼저 연결을 종료하는 것을 확인할 수 있었다.

 위와 같은 상황이 크게 어떤 경우에 발생할 수 있는지, 해당 경우에 fcgiwrap 프로그램이 어떤 에러 메시지를 출력하는지 정리해 보고자 한다.

<br>



## Python 스크립트 실행 불가

 fcgiwrap 프로세스가 Python 스크립트를 실행하기 위해서는 Python 스크립트 최상단에 Shebang 문자열을 작성해 주어야 한다. 그런데 Shebang 문자열에 명시된 Python 인터프리터의 경로가 잘못되었거나, Shebang 문자열을 작성했음에도 Python 스크립트에 실행 권한(`x`)이 없는 경우 다음과 같은 에러 메시지와 함께 Nginx에서 502 Bad Gateway 에러가 발생한다.

```bash
FastCGI sent in stderr: “Cannot execute script (/home/eraser/nginx/script/upload_test.py)” while reading resonse header from upstream, client: ...
```



### Shebang 

 Shebang이란, Unix 계열 운영 체제에서 **스크립트 코드 최상단에 해당 파일을 해석할 인터프리터의 경로를 명시하는 문자 시퀀스**를 의미한다. 해시 기호(`#`, sharp)와 느낌표(`!`, bang)의 합성어이다.

셔뱅으로 선언한 인터프리터로 스크립트를 동작시키겠다는 것을 의미하며, 다음과 같이 사용한다.

```python
#!/usr/bin/python3

print("Content-Type: text/html")
print()
print("<h1>Hello, World!</h1>")
```

 shebang이 있는 스크립트는 프로그램으로서 실행된다. 프로그램 로더가 스크립트 첫 줄의 셔뱅에 지정된 인터프리터 지시자를 이용해 구문을 분석하고, 스크립트를 실행한다. 즉, 특정 프로그램이 지정된 인터프리터 프로그램을 대신 실행할 수 있도록, 그 인터프리터 경로를 넘겨주는 것이다.

  fcgiwrap 프로세스가 shell에서 Python 인터프리터가 설치된 경로인 `usr/bin/python3`을 실행해 Python 터미널을 띄우고, 해당 Python 프로그램이 그 다음 줄부터 스크립트를 해석하며 프로그램을 동작시키는 것이다.

> *참고*: `#`를 사용하는 이유
>
> 대부분의 인터프리터 언어에서 `#` 문자가 주석으로 사용되기 때문에, 실제 스크립트 실행 시에는 주석처럼 무시되어서 해시 기호를 사용한다고 한다.

 Shebang이 있는 스크립트 파일은 다른 프로세스에 의해 실행 가능해야 하므로, 해당 프로세스의 user에게 실행 가능 권한(`x`)이 부여되어 있어야 한다.

<br>

 로컬 개발 환경에서 개발할 때는 문제가 되지 않았는데, Docker container 환경에서 개발할 때 스크립트를 실행할 수 없다는 것과 관련된 문제가 발생했고, 이를 다음과 같이 해결했다.

- 인터프리터 경로를 환경변수에 지정된 경로로 설정: `#!/usr/bin/env python`
  - 실행되는 환경마다 인터프리터 경로가 다를 수 있다. 나의 경우는 `python:3.9-slim-bullseye`를 베이스 이미지로 사용했는데, 해당 이미지를 실행한 컨테이너 내에서 `which python3` 명령어를 통해 Python3가 설치된 경로를 알아내고자 했고, `/usr/local/bin/python3`라는 경로를 Shebang에 지정했다
  - 다만, 컨테이너 상에서 경로가 제대로 잡히지 않을 수 있기 때문에(*TODO*), 환경변수 상에 지정되어 있는 python 경로를 Shebang 문자열에 명시하는 것이 좋다. 컨테이너 환경이 아니더라도, 실제 Shebang 문자열을 작성할 때는 인터프리터 실행 환경이 모두 다를 수 있기 때문에, 인터프리터 절대 경로를 그대로 명시하는 것보다는 **환경변수에 명시된 경로**를 사용하는 것이 더 권장된다고 한다
- Python 스크립트 실행 권한 부여: `chmod 755 upload_test.py `
  - Python 스크립트에 실행 권한을 부여한다. 특히 컨테이너 환경에서 스크립트 소유자와 fcgiwrap 소유자가 다를 수 있기 때문에, 그룹과 다른 사용자에 대해 읽기 및 실행 권한을 부여하는 것이 안전하다
  - 나의 경우는 Dockerfile 이미지 작성 시, 스크립트가 저장되어 있는 폴더를 마운트한 후, 이미지에 `RUN chmod 755 -R scripts/` 레이어를 추가함으로써 해결했다



<br>



## 권한 관련 문제



 fcgiwrap 프로세스가 실행한 Python 스크립트에서 **접근 권한이 없는 일을 수행하고자 할 경우**, 다음과 같은 에러 메시지와 함께 Nginx 502 Bad Gateway 에러가 발생한다. ~~*이 놈의 권한...*~~

```bash
upstream prematurely cloased FastCGI stdout while reading response header from upstream: fastcgi://unix:/var/run/fcgiwrap.sock
```

<br>

 Python 스크립트에서 파일 시스템의 파일을 읽어야 하는 경우에 위와 같은 에러가 발생했다. Python CGI 스크립트에서 발생한 에러를 추적할 수 있도록 cgitb 라이브러리를 이용해 해당 경우의 에러 메시지를 출력해 보았는데, 아래와 같이 `upload/0/4/3/...` 파일에 접근하려고 했으나 `Permission Denied` 에러가 발생했음을 확인할 수 있다.

![python-cgi-error]({{site.url}}/assets/images/python-cgi-permissiondenied.png)


 fcgiwrap을 실행하는 user는 `www-data`이기 때문에, fcgiwrap 프로세스에서 Python 스크립트를 실행하는 user 역시 `www-data`이다. 그런데 Python 스크립트에서 접근하려고 하는 파일의 소유자는 `nginx`이며, 소유 권한은 `-rw-------`이다. 따라서 Python 스크립트를 실행하는 user를 `nginx`로 바꿔 주거나, 스크립트에서 접근하고자 하는 파일의 소유 권한을 변경해 주면 된다.

- fcgiwrap user 변경: `spawn-fcgi -u 102 -g 102 -U 102 -G 102`
  - 해당 개발 환경에서 파일 소유 권한을 가진 user, group의 id가 무엇인지 확인한 후, `spawn-fcgi` 명령어 옵션을 통해 fcgiwrap 프로세스를 spawn하는 user, group을 변경한다 
- 파일 시스템 내 해당 파일 권한 변경: `chmod +rw /upload/0/4/3...`



<br>

## 줄바꿈 방식

 조금은 황당하지만, **Python 스크립트 줄바꿈 방식이 달라졌을 때**, 다음과 같은 에러 메시지와 함께 Nginx 502 Bad Gateway 에러가 발생한다. 줄 바꿈 방식이 바뀌면 스크립트를 읽을 수 없어 실행할 수 없음 관련 에러 메시지가 출력되어야 할 것 같은데, 처음 보는 에러 메시지가 나와 한 동안 고생했다. ~~*도무지 알다가도 모르겠는 컴퓨터...*~~

```bash
An error occurred while reading CGI reply (no response received)
```

<br>

 윈도우 환경에서 VSCode 편집기를 이용해 회사 Ubuntu 환경에 원격접속한 뒤, Python 스크립트를 수정하고 저장한 뒤 서버를 실행하니 발생한 문제다. 윈도우에서의 줄바꿈은 `CRLF`여서 VSCode에서 저장하니, 줄바꿈 문자가 Ubuntu 환경에서의 `LF`로부터 자동으로 바뀐 것이다. 편집기를 이용해 줄바꿈  문자를 다시 원래대로 바꿔 주면 해결된다.

 문제가 발생한 상황도, 해결 방안도 다소 당황스럽지만, 아무튼 이런 상황에서도 502 에러가 발생하므로 주의하는 것이 좋을 듯하다.





