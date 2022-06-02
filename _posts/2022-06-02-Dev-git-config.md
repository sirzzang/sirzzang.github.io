---
title:  "[Git] Git configuration 변경 방법"
excerpt: git 사용 환경 설정 파일을 확인하고 변경해 보자
categories:
  - Dev
toc: false
header:
  teaser: /assets/images/blog-Dev.jpg
tags:
  - Git
  - config
  - ignorecase
---



# Git 환경 설정 변경하기



 정리하던 Git repository 중 하나의 원격 저장소에서 다음과 같이 동일한 폴더가 두 개 존재하는 것을 발견했다. 



![git-repo-uppercase]({{site.url}}/assets/images/git-config-uppercase.png){: .align-center}

 예전에 폴더 명을 소문자(`network`)에서 대문자(`Network`)로 변경한 적이 있는데, 그 이후로 로컬 저장소에서 `network` 폴더는 보이지 않지만, 원격 저장소에는 계속해서 남아 있었다. 당시 폴더명 변경이 원격 저장소에 반영되지 않아 급하게 구글링한 후 `git config core.ignorecase false` 명령어를 사용한 뒤, 확인하지 않고 그대로 두다가 이제서야 해결했다.

<br>

## Git 설정 파일

 Git의 사용 환경은 config 파일로 관리된다. 이 때 Git 환경 설정을 위해 사용되는 config 파일은 아래와 같이 3가지가 있다.

- `/etc/config`: 시스템 모든 사용자 및 모든 저장소에 적용되는 설정 파일. `git config --system` 옵션으로 설정 가능
- `~/.gitconfig`, `~/.config/git/config`: 특정 사용자(*`~` 현재 사용자*)에게 적용되는 설정 파일. `git config --global` 옵션으로 설정 가능
- `[git directory]/.git/config`: Git 디렉토리 특정 저장소에만 적용되는 설정 파일. `git config --local` 옵션으로 설정 가능
  - Git 디렉토리 이동 후 실행 시 `--local`이 기본 옵션
  - 즉, Git 디렉토리에서 config 설정 시, 해당 저장소에만 해당 항목 설정이 적용됨





 Window 운영체제에서 Git 설정 파일은 다음의 위치에서 찾을 수 있다.

- `/etc/config`: `/etc/config`

  ```bash
  sir95@DESKTOP-CA22JII MINGW64 /etc
  $ ls -al | grep git
  -rw-r--r-- 1 sir95 197121   515  7월 28  2020 gitattributes
  -rw-r--r-- 1 sir95 197121   347 12월  7  2020 gitconfig # git 시스템 설정 파일
  ```

  ![git-config-window-system]({{site.url}}/assets/images/git-config-window-system.png){: width="400"}{: .align-center}

- `~/.gitconfig`: Window `$HOME` 디렉토리(`C:/Users/$USER`)의 `~/.gitconfig` 파일

  ```bash
  sir95@DESKTOP-CA22JII MINGW64 ~
  $ ls -al | grep git
  -rw-r--r-- 1 sir95 197121       81  5월  2 13:24 .gitconfig
  -rw-r--r-- 1 sir95 197121      176  6월  2 10:30 .git-credentials
  ```

  ![git-config-window-user]({{site.url}}/assets/images/git-config-window-user.png){: width="400"}{: .align-center}

- `[git directory]/.git/config`: Git 디렉토리 내의 `.git` 폴더 내의 `.config` 파일

  ```bash
  sir95@DESKTOP-CA22JII MINGW64 ~/Documents/TIL/.git (GIT_DIR!)
  $ ls -al | grep config
  -rw-r--r-- 1 sir95 197121   376  6월  2 10:23 config
  ```

  ![git-config-window-directory]({{site.url}}/assets/images/git-config-window-directory.png){: width="400"}{: .align-center}



 각 설정파일의 우선 순위는 **시스템 < 사용자 < 디렉토리**이다. 즉, git 디렉토리 내의 `.git/config` 파일이 `/etc/config` 파일보다 우선하여 적용된다. 

<br>

## Git 환경 설정 항목 



 Git 환경 설정에 사용되는 항목들은 [git-config documentation](https://git-scm.com/docs/git-config)에서 확인할 수 있다.

 예컨대, Git 커밋 시 사용되는 사용자 이름과 이메일 주소는 [user.name](https://git-scm.com/docs/git-config#Documentation/git-config.txt-username)과 [user.email](https://git-scm.com/docs/git-config#Documentation/git-config.txt-useremail) 항목으로 설정할 수 있다. 다음과 같이 현재 사용자를 대상으로 user.name과 user.email을 설정하면 된다.

```bash
sir95@DESKTOP-CA22JII MINGW64 ~
$ git config --global user.name "sirzzang"

sir95@DESKTOP-CA22JII MINGW64 ~
$ git config --global user.email "sirzzang@naver.com"
```

<br>

 모든 환경 설정 항목을 다 보고 싶다면, `git config --list`를 사용하면 된다.

```bash
# 시스템 수준의 설정 항목 리스트
$ git config --system --list
diff.astextplain.textconv=astextplain
filter.lfs.clean=git-lfs clean -- %f
filter.lfs.smudge=git-lfs smudge -- %f
filter.lfs.process=git-lfs filter-process
filter.lfs.required=true
http.sslbackend=openssl
http.sslcainfo=C:/Program Files/Git/mingw64/ssl/certs/ca-bundle.crt
core.autocrlf=true
core.fscache=true
core.symlinks=false
pull.rebase=false
```

```bash
# 사용자 수준의 설정 항목 리스트
user.name=sirzzang
user.email=sirzzang@naver.com
credential.helper=store
```

```bash
# git 디렉토리 설정 항목 리스트
$ git config --list
diff.astextplain.textconv=astextplain
filter.lfs.clean=git-lfs clean -- %f
filter.lfs.smudge=git-lfs smudge -- %f
filter.lfs.process=git-lfs filter-process
diff.astextplain.textconv=astextplain
filter.lfs.clean=git-lfs clean -- %f
filter.lfs.smudge=git-lfs smudge -- %f
filter.lfs.process=git-lfs filter-process
filter.lfs.required=true
http.sslbackend=openssl
http.sslcainfo=C:/Program Files/Git/mingw64/ssl/certs/ca-bundle.crt
core.autocrlf=true
core.fscache=true
core.symlinks=false
pull.rebase=false
user.name=sirzzang
user.email=sirzzang@naver.com
credential.helper=store
core.repositoryformatversion=0
core.filemode=false
core.bare=false
core.logallrefupdates=true
core.symlinks=false
core.protectntfs=false
core.ignorecase=false
remote.origin.url=https://github.com/sirzzang/TIL.git
remote.origin.fetch=+refs/heads/*:refs/remotes/origin/*
```

 `git config <key>` 명령어를 통해 특정 키만 가지고 설정 항목을 확인할 수도 있다.

```bash
$ git config user.name
sirzzang
```

<br>

## 문제 해결



 기존에 문제가 되었던 상황의 git 설정은 `core.ignorecase` 옵션과 관련이 있다.

```bash
$ git config core.ignorecase
false
```

<br>

 `core.ignorecase` 설정 옵션은 다음과 같다.

> Internal variable which enables various workarounds to enable Git to work better on filesystems that are not case sensitive, like APFS, HFS+, FAT, NTFS, etc. For example, if a directory listing finds "makefile" when Git expects "Makefile", Git will assume it is really the same file, and continue to remember it as "Makefile".
>
> The default is false, except [git-clone[1\]](https://git-scm.com/docs/git-clone) or [git-init[1\]](https://git-scm.com/docs/git-init) will probe and set core.ignoreCase true if appropriate when the repository is created.
>
> Git relies on the proper configuration of this variable for your operating and file system. Modifying this value may result in unexpected behavior.

`git-init`이나 `git-clone`을 통해 Git 레포지토리를 생성한 경우에는 `core.ignorecase`가 `true`로 설정된다. 그래서 파일 시스템에서 파일의 대소문자를 변경하더라도, 이는 커밋 변경 사항으로 인식되지 않는 것이다.

<br>

 예전에 나는 대소문자 변경을 인식해 주기 위해 해당 옵션을 `false`로 변경했고, 이 때문에 Git은 대소문자가 다른 파일명을 갖는 파일을 서로 다른 파일로 인식해 변경 사항을 추적한다. 그러나 로컬 파일시스템은 case sensitve하지 않아, 대소문자가 변경되었을 때의 파일을 동일한 파일로 인식한다. 이 때문에 Git은 `Network`와 `network`를 서로 다른 폴더로 인식하고, 이 변경사항을 추적한 것이 Github 원격 레포지토리에 반영되었으나, 로컬 파일시스템에서는 이 두 폴더가 이미 같은 폴더이기 때문에 혼란이 야기되었던 것이다.

 ~~공식 문서를 읽어 보니, 애초에 이 설정을 변경하는 것이 권장되지 않는 행위라고 나와 있었음에도 불구하고 섣부르게 구글링하여 변경했던 과거의 나 자신~~. 비슷한 문제를 [여기 글](https://dlee0129.tistory.com/25)에서도 찾을 수 있다.

<br>

 어쨌든,  Git 설정을 바꾸고, 원격 저장소에 있는 파일을 삭제한 뒤에 다시 원격 저장소에 푸쉬해주면 이 문제는 깔끔하게 해결된다!

```bash
$ git config core.ignorecase true
$ git rm -r --cached .
$ git add .
$ git commit -m 'fix: fix uppercase'
$ git push origin main
```

![git-config-uppercase-fix]({{site.url}}/assets/images/git-config-uppercase-fix.png){: width="500"}{: .align-center}

<center><sup>Network, network... 편안..</sup></center>



<br>

*참고*

- [git config](https://git-scm.com/docs/git-config#Documentation/git-config.txt-useremail)
- [git 최초 설정](https://git-scm.com/book/ko/v2/%EC%8B%9C%EC%9E%91%ED%95%98%EA%B8%B0-Git-%EC%B5%9C%EC%B4%88-%EC%84%A4%EC%A0%95)

