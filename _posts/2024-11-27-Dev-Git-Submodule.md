---
title:  "[Git] Git Submodule 사용 방법"
excerpt: Git의 submodule 기능을 이용해 Git 저장소 하위에 또 다른 Git 저장소를 관리하기
categories:
  - Dev
toc: true
header:
  teaser: /assets/images/blog-Dev.jpg
tags:
  - git
  - submodule
---

<br>

회사에서 진행하던 프로젝트에 Git Submodule을 적용해 볼 수 있지 않을까 생각이 들어 공부한 내용을 기록하고자 한다.

- [Git Submodule](https://git-scm.com/book/en/v2/Git-Tools-Submodules)

<br>

# 배경



<br>





# 개요

![submodule-concept]({{site.url}}/assets/images/submodule-concept.png){: .align-center }

<center><sup>이미지 출처: https://medium.com/day34/git-submodule-9f0ab0b79826</sup></center>

Git Submodule이란, Git 저장소 안(하위)에 디렉토리로 분리해 넣은 또 다른 Git 저장소이다. 

- 상위 저장소: main repository
- 디렉토리로 분리되어 들어간 하위 저장소: submodule

<br>

프로젝트 수행 시 다른 프로젝트를 함께 사용해야 하는 경우를 위해 Git에서 제공하는 기능이다. 외부에서 개발한 라이브러리나, 내부 여러 프로젝트에서 공통으로 사용할 라이브러리 코드를 관리하고 동기화할 필요가 있을 때 주로 사용한다.

이 때, main repository와 submodule은 각각 독립적인 프로젝트로 관리된다. 따라서 **두 저장소의 커밋은 동기화되지 않고, 별도로 관리**된다. 이것이 의미하는 바는 다음과 같다.

- main repository에서 submodule의 내용을 직접 변경할 수 없음
  - submodule 내용을 변경하고 싶다면, submodule repository에서 변경해야 함
- submodule의 내용이 변경되더라도 main repository에서 이 내용이 자동으로 업데이트되지 않음
  - main repository에서 submodule의 상태를 확인하고, 업데이트해야 함

즉, main repository에서는 submodule의 커밋 로그를 바탕으로, submodule 데이터를 가져와 사용할 뿐이다. 결과적으로, 서로 다른 두 프로젝트를 별개로 관리하면서도, 그 중 하나를 다른 프로젝트에서 사용할 수 있게 된다.



<br>

## .gitmodules

main repository에서 submodule을 사용하고자 할 때, submodule 각각의 프로젝트 정보를 담고 있는 설정 파일이다. 

- [.gitmodules](https://git-scm.com/docs/gitmodules)

<br>

아래와 같은 항목으로 구성된다.

```
[submodule "DbConnector"]
    path = DbConnector
    url = https://github.com/chaconinc/DbConnector
```

여러 가지 설정 항목이 있지만, 그 중에서도 주로 사용하게 되는 설정 항목은 다음과 같다.

- [path](https://git-scm.com/docs/gitmodules#Documentation/gitmodules.txt-submoduleltnamegtpath): main repository 내 submodule 경로
- [url](https://git-scm.com/docs/gitmodules#Documentation/gitmodules.txt-submoduleltnamegturl): submodule 원격 저장소 clone 경로
- [branch](https://git-scm.com/docs/gitmodules#Documentation/gitmodules.txt-submoduleltnamegtbranch): submodule 추적 대상 브랜치

<br>

main repository에서 사용할 submodule의 개수만큼 위 설정 항목이 추가되며, `.gitignore` 파일처럼 버전 관리의 대상이 된다. 따라서 main repository 프로젝트를 clone하는 사람은 이 파일을 통해 해당 프로젝트에서 사용하는 submodule이 어떤 것이 있는지 확인할 수 있다.

<br>

# 사용



main repository, submodule을 사용하는 예시 상황을 가정하기 위해, 아래와 같이 2개의 Git Repository를 생성한다.

- `main-repo`: main repository

  ```bash
  $ mkdir main-repo
  $ cd main-repo
  $ echo "#main-repo" >> README.md
  $ git init
  $ git add .
  $ git remote add origin https://github.com/sirzzang/main-repo.git
  $ git push origin master
  ```

- `submodule-repo`: submodule repository

  ```bash
  $ mkdir submodule-repo
  $ cd submodule-repo
  $ echo "#submodule-repo" >> README.md
  $ git init
  $ git add .
  $ git remote add origin https://github.com/sirzzang/submodule-repo.git
  $ git push origin master
  ```





## Submodule을 Project에 추가

main repository에 submodule을 추가하기 위해서는 `git submodule add` 커맨드를 이용한다.

```bash
git submodule add <repo-url> [path]
```

```bash
eraser@ubuntu-2204:~/temp/submodule-test/main-repo$ git submodule add git@github.com:sirzzang/submodule-repo.git
Cloning into '/home/eraser/temp/submodule-test/main-repo/submodule-repo'...
remote: Enumerating objects: 3, done.
remote: Counting objects: 100% (3/3), done.
remote: Total 3 (delta 0), reused 3 (delta 0), pack-reused 0 (from 0)
Receiving objects: 100% (3/3), done.
```

<br>

추가 후, main repository의 상태를 확인해 보면, 아래와 같이 `.gitmodules`와 submodule에 해당하는 디렉토리 `submodule-repo/`가 추가된 것을 확인할 수 있다.

```bash
eraser@ubuntu-2204:~/temp/submodule-test/main-repo$ git status
On branch master
Your branch is up to date with 'origin/master'.

Changes to be committed:
  (use "git restore --staged <file>..." to unstage)
        new file:   .gitmodules
        new file:   submodule-repo
```

- `git diff` 커맨드를 통해 달라진 내용을 확인한 결과

  ```bash
  eraser@ubuntu-2204:~/temp/submodule-test/main-repo$ git diff --cached submodule-repo
  diff --git a/submodule-repo b/submodule-repo
  new file mode 160000
  index 0000000..ea76cfc
  --- /dev/null
  +++ b/submodule-repo
  @@ -0,0 +1 @@
  +Subproject commit ea76cfc7e1e8e8d8899ec0fc53401499a9505802
  ```

- `--submodule` 옵션을 주면, 더 자세히 확인 가능

  ```bash
  eraser@ubuntu-2204:~/temp/submodule-test/main-repo$ git diff --cached --submodule
  diff --git a/.gitmodules b/.gitmodules
  new file mode 100644
  index 0000000..5c36d60
  --- /dev/null
  +++ b/.gitmodules
  @@ -0,0 +1,3 @@
  +[submodule "submodule-repo"]
  +       path = submodule-repo
  +       url = git@github.com:sirzzang/submodule-repo.git
  Submodule submodule-repo 0000000...ea76cfc (new submodule)
  ```

  

<br>

main repository에 submodule을 추가하게 될 경우, submodule에 해당하는 디렉토리 하나 전체가 하나의 특별한 커밋으로 취급된다. 해당 디렉토리에 대한 git mode는 `160000`이다.

이렇게 main repository에 submodule을 추가하면, main repository는 submodule의 특정 커밋을 가리키게 된다. 이제 submodule을 포함한 커밋을 생성하면, main repository에서의 submodule 추가가 완료된다.

```bash
eraser@ubuntu-2204:~/temp/submodule-test/main-repo$ git add .
eraser@ubuntu-2204:~/temp/submodule-test/main-repo$ git commit -m 'add submodule-repo as a submodule'
[master 9faed64] add submodule-repo as a submodule
 2 files changed, 4 insertions(+)
 create mode 100644 .gitmodules
 create mode 160000 submodule-repo
```

- [commit 참고](https://github.com/sirzzang/main-repo/commit/9faed6434829fbd89d471280c502a3c3566e2b5e)

<br>

main repository 원격 저장소에 push하면, 아래와 같이 submodule이 생성된 것을 확인할 수 있다. submodule 뒤에 커밋 해시 값이 붙어 있는 것도 확인할 수 있다. 

![add-submodule-push]({{site.url}}/assets/images/add-submodule-push.png){: .align-center}

만약 submodule 저장소에 대한 접근 권한이 없는 사용자가 있다면, main repository에서 submodule 링크를 클릭해도 이동할 수 없다.

<br>



## Submodule을 포함한 Project Clone



### init



### update



### clone with `--recurse-submodules`





## Submodule을 포함한 Project Update





### fetch



### merge





### update with `--remote`





## 기타





<br>

# 활용

