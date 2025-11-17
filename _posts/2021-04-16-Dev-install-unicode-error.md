---
title:  "[Python] pip 이용 의존 라이브러리 설치 시 unicode 에러 해결"
excerpt: unicode 에러가 날 때의 해결 방법을 알아 보자.
categories:
  - Dev
toc: false
header:
  teaser: /assets/images/blog-Dev.jpg
tags:
  - Python
  - UnicodeDecodeError
  - stdnum
---



 오픈소스 ERP 플랫폼 [Odoo](https://github.com/odoo/odoo)을 설치해서 사용해 보려다, `python-stdnum==1.8` 버전이 설치되지 않았다. 에러 메시지를 자세히 살펴 보니, stdnum 1.8의 `setup.py` 파일에서 문자 디코드 에러가 난다. 구글링해 보니, stdnum 라이브러리 1.8 버전의 오래 된 버그라고 한다. stdnum [이슈](https://github.com/arthurdejong/python-stdnum/issues/59)에도 등록되었던 것을 보니 나만 겪은 문제는 아닌 듯?

<br>

 `setup.py` 파일에 인코딩 부분을 추가해 주어야 하는데 어떻게 할지 몰라서, [이 글](https://stackoverflow.com/questions/65820347/unicodedecodeerror-charmap-codec-error-during-installation-of-pip-python-std)을 참고해 해결했다. 이 에러 해결법을 통해 얻고 싶었던 것은 **라이브러리 설치 시 setup 파일 자체에 문제가 있는 경우, 어떻게 해결해야 하는가**이다.

* 라이브러리 공식 문서에서 직접 해당 버전의 라이브러리 압축 파일을 다운받는다.
* 압축 파일을 직접 다운 받아 압축을 푼 뒤, 해당 폴더 내 `setup.py` 파일을 수정한다.
* 다시 압축한다.
* 라이브러리를 설치하고자 하는 폴더의 절대 경로에서 다시 압축한 파일을 설치하도록 커맨드라인에 명령어를 작성한다.

<br>

 코드는 위의 글을 참고했으므로, 각 단계별로 어떻게 폴더 내 코드 구조가 변화하는지의 결과 사진만 첨부한다.

![odoo-stdnum-opentarfile]({{site.url}}/assets/images/odoo-stdnum-opentarfile.png)

<center><sup>압축파일 다운받은 후 압축 해제하는 코드</sup></center>

![odoo-stdnum-editsetup]({{site.url}}/assets/images/odoo-stdnum-editsetup.png)

<center><sup>stdnum의 setup 파일에서 파일 읽는 부분 수정하는 코드</sup></center>

![odoo-stdnum-maketarfile]({{site.url}}/assets/images/odoo-stdnum-maketarfile.png)

<center><sup>setup 파일 수정 후 새로 압축하는 코드</sup></center>

![odoo-stdnum-absolutepathinstall]({{site.url}}/assets/images/odoo-stdnum-absolutepathinstall.png)

<center><sup>terminal에서 pip install</sup></center>

<br>

 이렇게 한 뒤, 다시 `requirements.txt`를 설치하니, 모든 의존 라이브러리가 옳게 설치되었다. *~~근데, 지금에서야 깨달았는데 왜 가상환경을 안 만들고 해서 다시 해야 할까^^.....~~*