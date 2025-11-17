---
title:  "[AI] KoNLPy 사용자 사전 추가"
excerpt: "Google Colabaratory에서 사용자 사전을 추가해 보자."
toc: true
toc_sticky: true
categories:
  - AI
tags:
  - 자연어처리
  - Python
  - Colab
  - NLP
  - KoNLPy
  - 사용자사전
last_modified_at: 2020-08-07_
---





# _Okt 사용자 사전 추가_





## 1. 사전 작업



 KoNLPy와 Java 등을 설치해 놓았다는 것을 전제로 한다. 예전에 프로젝트를 할 때에는 임시 설치의 개념이어서 런타임을 새로 시작할 때마다 다시 깔았어야 했는데, 구글링을 통해 [이 글](https://colab.research.google.com/drive/1tL2WjfE0v_es4YJCLGoEJM5NXs_O_ytW#scrollTo=9gqwqppQaVqg)을 발견하고 영구적(?)으로 설치할 수 있었다. *(예전에는 automake를 안 깔아서 영구적으로 설치된 것이 아니었던 듯 하다. ~~확실하지는 않다.~~)*



```python
import os

# KoNLPy 라이브러리 설치
!pip install konlpy

# jdk, JPype1-py3 설치
!apt-get install openjdk-8-jdk-headless -qq > /dev/null
!pip3 install JPype1-py3

# automake 설치
os.chdir('/tmp')
!curl -LO http://ftpmirror.gnu.org/automake/automake-1.11.tar.gz
!tar -zxvf automake-1.11.tar.gz
os.chdir('/tmp/automake-1.11')
!./configure
!make
!make install

# automake 설치 오류 시
os.chdir('/tmp/') 
!wget -O m4-1.4.9.tar.gz http://ftp.gnu.org/gnu/m4/m4-1.4.9.tar.gz
!tar -zvxf m4-1.4.9.tar.gz
os.chdir('/tmp/m4-1.4.9')
!./configure
!make
!make install
os.chdir('/tmp')
!curl -OL http://ftpmirror.gnu.org/autoconf/autoconf-2.69.tar.gz
!tar xzf autoconf-2.69.tar.gz
os.chdir('/tmp/autoconf-2.69')
!./configure --prefix=/usr/local
!make
!make install
!export PATH=/usr/local/bin
```

<br>

 강의에서는 `Okt` 형태소 분석기를 기준으로 해서 `mecab`을 깔지는 않았지만, 위 문서에서는 다음과 같은 방식으로 `mecab`을 설치할 수 있다고 설명한다.

```python
import os

# mecab-ko 설치
os.chdir('/tmp/')
!curl -LO https://bitbucket.org/eunjeon/mecab-ko/downloads/mecab-0.996-ko-0.9.1.tar.gz
!tar zxfv mecab-0.996-ko-0.9.1.tar.gz
os.chdir('/tmp/mecab-0.996-ko-0.9.1')
!./configure
!make
!make check
!make install

# mecab-ko-dic 설치
os.chdir('/tmp')
!curl -LO https://bitbucket.org/eunjeon/mecab-ko-dic/downloads/mecab-ko-dic-2.0.1-20150920.tar.gz
!tar -zxvf mecab-ko-dic-2.0.1-20150920.tar.gz
os.chdir('/tmp/mecab-ko-dic-2.0.1-20150920')
!./autogen.sh
!./configure
!make
# !sh -c 'echo "dicdir=/usr/local/lib/mecab/dic/mecab-ko-dic" > /usr/local/etc/mecabrc'
!make install

# mecab-python 설치: python3 기준
os.chdir('/content')
!git clone https://bitbucket.org/eunjeon/mecab-python-0.996.git
os.chdir('/content/mecab-python-0.996')
!python3 setup.py build
!python3 setup.py install
```

<br>

## 2. KoNLPy 설치 위치로 이동



 구글 드라이브에서 `내 드라이브`의 상위 경로로 이동하는 게 핵심이었다. ~~*(예전에는 이걸 몰랐다)*~~ 그 상위 경로로만 이동하면, 로컬 환경에서 진행하는 것과 똑같다! (다만, Google Colabaratory가 리눅스 환경 기반이어서 조금씩 폴더 명이 다르긴 하다.)

 아래의 사진에서처럼 `konlpy` 폴더를 찾아 가자. `/usr/local/lib/python3.6/dist-packages/konlpy`를 따라 가면 된다.



|               내 드라이브 상위 경로로 이동                |                  KoNLPy 폴더로 이동                  |
| :-------------------------------------------------------: | :--------------------------------------------------: |
| ![change-path]({{site.url}}/assets/images/user-dic-1.png) | ![konlpy]({{site.url}}/assets/images/user-dic-2.png) |



> *참고* 
>
>  로컬 환경(아나콘다 기준)에서 사용자 사전을 추가하려면, `C/user/anaconda3/Lib/site-packages/konlpy/java` 경로를 찾아 가면 된다.

<br>

## 3. 사용자 사전 추가



> *참고* 
>
>  아래의 작업을 로컬 환경에서 진행하려면 윈도우에서 cmd 창을 관리자 권한으로 열어 실행하면 된다. 명령어는 전부 동일하다. 사용자 사전을 추가하고자 하는 경우는 메모장, notepad 등의 텍스트 편집기를 열어서 추가하면 된다.



 `konlpy` 폴더에서 `java` 폴더에 들어 가면 아래와 같이 `open-korean-text-2.1.0.jar` 파일이 있는 것을 확인할 수 있다. 이 묶음 파일 안에 `Okt`의 사전이 들어 있다. 



![okt-jar]({{site.url}}/assets/images/user-dic-3.png){: width="400"}{: .align-center}

<br>

 `java` 폴더로 이동해 아래에 임시 폴더를 만든다. 나는 'aaa'라는 이름으로 만들었다. `os.makedirs`를 이용하긴 했으나, 사실 colabaratory 상에서는 옆의 GUI 환경 상에서 폴더를 만드는 게 훨씬 편하다. `os` 모듈을 이용한다면, 항상 현재 경로를 확인하자.

```python
import os

os.chdir('/usr/local/lib/python3.6/dist-packages/konlpy/java')
os.getcwd() 
os.makedirs('./aaa')
```

<br>

 임시 폴더에 `Okt` 사전 파일의 압축을 풀어 준다.

```python
!jar xvf ../open-korean-text-2.1.0.jar
```

 콘솔 창에 아래와 같은 출력이 나타나면 된다.

```python
created: META-INF/
 inflated: META-INF/MANIFEST.MF
  created: org/
  created: org/openkoreantext/
  created: org/openkoreantext/processor/
  created: org/openkoreantext/processor/normalizer/
  ...
```

<br>

 이후 원하는 품사의 파일을 열어 사용자 사전에 추가한다. 나는 `Nouns`에서 `names.txt`에 추가했다. 

```python
# 사용자 사전 열기
with open(f"/usr/local/lib/python3.6/dist-packages/konlpy/java/aaa/org/openkoreantext/processor/util/noun/names.txt") as f:
    data = f.read()
```



 사용자 사전을 열어 보면, 개행 문자로 각 단어가 구분되어 있다. 

```python
# names.txt 예시
가몽\n가온\n갓세븐\n강새이\n게임닉가\n관우\n귀여미...
```



  따라서 `\n`으로 구분하여 새로운 단어를 추가하고, 해당 파일을 `쓰기 모드`로 열어 새롭게 쓴다.

```python
# 새로운 단어 추가
data += '김재경자경\n송이레만세\n'

# 파일 새롭게 저장
with open("/usr/local/lib/python3.6/dist-packages/konlpy/java/aaa/org/openkoreantext/processor/util/noun/names.txt", 'w') as f:
    f.write(data)
```

<br>

 이제 `java` 폴더의 `open-korean-text-2.1.0.jar`로 다시 압축해 준다.

```python
!jar cvf ../open-korean-text-2.1.0.jar * 
```



 콘솔 창에 아래와 같은 출력이 나타나면 된다.

```python
added manifest
adding: mecab-python-0.996/(in = 0) (out= 0)(stored 0%)
adding: mecab-python-0.996/build/(in = 0) (out= 0)(stored 0%)
adding: mecab-python-0.996/build/lib.linux-x86_64-3.6/(in = 0) (out= 0)(stored 0%)
adding: mecab-python-0.996/build/lib.linux-x86_64-3.6/MeCab.py(in = 15733) (out= 2743)(deflated 82%)
    ...
```



<br>

> *참고* : `startJVM()` 오류 발생 시
>
>  형태소 분석기를 사용하기 위해 로드하면, JVM 오류가 발생하는 경우도 있다. 구글링을 통해 [이 글](https://i-am-eden.tistory.com/9)을 찾아 냈다. Colabaratory에서는 콘솔 창에서 `jvm.py` 파일을 그대로 열어서 `convertStrings=True` 옵션을 없애 주면 된다.
>
> ![JVM-error]({{site.url}}/assets/images/user-dic-4.png){: width="600"}{: .align-center}

<br>



 런타임을 초기화하자. 그리고 추가한 사용자 사전이 제대로 작동되는지 확인한다. 성공했다!



```python
from konlpy.tag import Okt
okt = Okt()
print(okt.nouns('송이레만세')) # ['송이레만세']
print(okt.morphs('김재경자경')) # ['김재경자경']
```

