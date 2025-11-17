---
title:  "[tbAdmin] .fileTableLock Permission Denied 에러 해결"
excerpt: 권한을 가지지 않은 사용자가 프로그램을 실행할 때 마주치는 오류
categories:
  - Dev
toc: false
header:
  teaser: /assets/images/blog-Dev.jpg
tags:
  - tbAdmin
  - permission denied
  - fileTableLock
  - 허가권
  - 사용자
  - 그룹
  - 리눅스
---



 회사 업무 중 tbAdmin 프로그램을 사용해야 하는데, 설치 후 실행할 때마다 아래와 같은 오류를 마주했다.

![tbadmin-run-error]({{site.url}}/assets/images/tbadmin-run-error.png){: .align-center}

<br>

 오류 메시지를 읽어 보면, 런타임 환경에서 file locking이 불가능하기 때문인 것으로 보인다. 친절하게 해결책도 안내해 주고 있길래, 이를 참고하여 `-Dosgi.locking=none` 설정을 `tbAdmin.ini` 설정에 추가해 주었다. 그래도 여전히 같은 오류가 발생한다. ~~한 번에 될 리가~~

![tbadmin-dosgi-locking-none]({{site.url}}/assets/images/tbadmin-dosgi-locking-none.png){: .align-center}

<br>

 구글링을 통해 [이 글](https://www.ibm.com/support/pages/error-locking-not-possible-directory-when-running-group-mode){: .btn .btn--primary .btn--small}을 발견했는데, 내가 겪었던 문제와 동일했다. 이러한 에러는 **`.fileTableLock` 파일에 접근할 수 있는 권한을 가지지 않은 사용자가 해당 파일을 실행할 때** 발생한다고 한다. 프로그램 실행 런타임 시 OSGi cache가 `.fileTableLock` 파일에 접근할 수 있어야 하는데, **프로그램을 실행하는 사용자가 `.fileTableLock` 파일에 대한 접근 권한을 가지고 있지 않다면**, 런타임 시 내부 로직에 문제가 발생하며 프로그램이 종료되는 것이다.

> *참고*: 궁금한 것
>
> 사실, OSGi가 뭔지, `.fileTableLock`이 어떤 역할을 수행하는지 정확히 알지 못한다. 대강 리눅스 파일 시스템 상의 허가권한 때문에 문제가 발생했구나 하는 정도로만 이해하고 넘어가기로 했다. Java runtime과 관련된 듯한데, 나중에 기회가 되면 더 깊이 공부해 보도록 하자. ~~Java 무식자...~~
>

<br>

 tbAdmin을 실행할 때(tbAdmin 프로그램을 클릭하여 실행하거나, `sudo` 명령어 없이 터미널에서 바로 실행할 때), 사용자는 `root`가 아닌, `Eraser`(내가 설정한 계정 사용자)이다. 위의 글에서 본 설명대로라면, tbAdmin 프로그램을 실행하기 위해 OSGi cache가 접근해야 하는 configuration 폴더 내 `.fileTableLock` 파일은 `Eraser` 계정에서 접근할 수 없어야 한다.

 configuration 폴더 내 `.fileTableLock`은 다음과 같은 3개의 폴더 내의 `.manager` 폴더에 존재한다.

```
tbAdmin
  (...)
  ㄴconfiguration
    (...)
    ㄴorg.eclipse.core.runtime
    ㄴorg.eclipse.equinox.app
    ㄴorg.eclipse.osgi
```

 configuration 내 접근 권한을 살펴 보자.

![tbadmin-configuration-lsal]({{site.url}}/assets/images/tbadmin-configuration-lsal.png){: .align-center}

<center><sup> `.fileTableLock` 파일이 존재하는 3개의 디렉토리 모두 소유권과 소유그룹이 `root`이다(!!)</sup></center>

 해당 폴더 내 `.manager` 내 `.fileTableLock` 파일 허가권을 살펴 보니,  접근이 허용되어 있지 않다.

![tbadmin-filetablelock-lsal]({{site.url}}/assets/images/tbadmin-filetablelock-lsal.png){: .align-center}

> 소유자에 대해서도 접근이 허용되어 있지 않은데, 그 이전에 `sudo` 명령어로 실행했을 때는 왜 되었던 것일까?

<br>

 이에 위의 글에서 보았던 방법을 따라 오류를 해결하였다. `.fileTableLock`에 대한 허가권을 변경한 뒤, 소유 그룹을 tbAdmin을 실행할 사용자 그룹으로 만들어 주는 것이 핵심인 듯.

* configuration 내 존재하는 모든 `.fileTableLock` 파일에 대해 허가권을 `777`로 변경한다. 소유자, 그룹, 기타 사용자에 대해 모두 파일 읽기, 쓰기, 접근 권한을 허용한다.
* configuration 폴더 하위 디렉토리 및 파일 모두 읽기, 쓰기, 접근 권한을 소유 그룹에 대해 부여한다.
* configuration 폴더의 소유 그룹을 기존 사용자 계정 그룹으로 변경해 준다.

<br>

 각 단계별 명령어를 실행하는 과정은 다음 사진에서와 같다.

![tbadmin-filetablelock-chmod]({{site.url}}/assets/images/tbadmin-filetablelock-chmod.png){: .align-center}



![tbadmin-chmod-configuration]({{site.url}}/assets/images/tbadmin-chmod-configuration.png){: .align-center}



![tbadmin-chgrp-configuration]({{site.url}}/assets/images/tbadmin-chgrp-configuration.png){: .align-center}

<br>

 이제 tbAdmin configuration 폴더에 대해 허가권을 다시 살펴 보면, 다음과 같이 변경된 것을 볼 수 있다. 그리고 실행 시, 문제 없이 실행된다!

![tbadmin-configuration-done]({{site.url}}/assets/images/tbadmin-configuration-done.png){: .align-center}

 

<br> 문제를 해결하긴 했으나, 중간 중간에 적어 놓은 의문점과 같이 아직도 궁금한 것이 많다. 나중에 여유가 생길 때, 리눅스 파일 시스템 허가권, 소유권 및 Java 기반 프로그램 런타임 환경에 대해 조금 더 알아보아야 할 듯하다. 일단, 리눅스 기반 운영체제에서 프로그램을 실행했을 때 *Permission Denied 에러가 발생한다면*, **소유자와 소유그룹, 허가권을 살펴 보는 것**이 에러 해결을 위한 하나의 방법이 될 수 있다는 것을 알고 넘어가도록 하자.





