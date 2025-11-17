---
title:  "[Git] Git 활용하기"
excerpt: "<<VCS>> 기억해야 할 git 활용 방법"
toc: true
toc_sticky: true
categories:
  - Dev
header:
  teaser: /assets/images/blog-Dev.jpg
tags:
  - VCS
  - 협업
  - git
  - github
  
last_modified_at: 2020-02-01
---



<sup>[김탁희 강사님](https://github.com/edutak)의 강의 및 강의 자료를 기반으로 합니다.</sup>

<sup>[Github Repo](https://github.com/sirzzang/LECTURE/tree/master/서비스-산업-데이터를-활용한-머신러닝-분석/특강/GitHub)</sup>

# _Git, Github_

 분산형 버전관리 시스템 `Git`을 활용하여 `최종.txt`, `최종의 최종.txt`, ... 처럼 파일 이름 말고, `이력`을 관리해 보자.

![git-flow]({{site.url}}/assets/images/git.png){: .align-center}



<br>

## 1. 주요 명령어



* `git status` 

 파일의 상태를 확인할 때 사용하는 명령어다. CLI 기반 `git bash` 창에서는 상태를 바로 바로 확인할 수 없기 때문에, `git`의 `A to Z`라고 불러도 무방할 만큼 중요한 명령어이다.

* `git add` 

 이력을 확정하기 전, Staging Area로 커밋할 파일을 옮긴다. 아직 Staging Area에 올라가기 전인데 새로 생성된 파일이 있다면, Untracked 상태이다.

```bash
$ git status
On branch master

No commits yet

Untracked files: # git 이력에 담기지 않은 파일들: 새로 생성됨.
  (use "git add <file>..." to include in what will be committed)
  # git add 명령어를 통해서 커밋될 곳에 추가 해라.
        a.txt
        b.txt

nothing added to commit but untracked files present (use "git add" to track)
```



 이제 `add` 후 상태를 확인하면 다음과 같다.

```bash
$ git add .
$ git status
On branch master

No commits yet
# 커밋될 변경사항들
Changes to be committed:
  (use "git rm --cached <file>..." to unstage)
        new file:   a.txt
        new file:   b.txt
```



* `git commit`, `git commit -m "..."`

 파일의 변경 이력을 확정하고, hash 값을 부여한다. 부여된 hash 값을 통해 동일한 이력인지 확인한다. `-m`을 통해 커밋 메시지를 작성한다. 협업 시 커밋 메시지를 잘 작성하는 것이 매우 중요하다.



> *참고*
>
>  `git commit --amend` 명령을 활용하면 이력을 변경할 수 있다. 그러나 협업 시 웬만하면 사용하지 않는 것이 좋다. ~~*뭐 빠뜨렸더라도 그냥 새로 commit하자.*~~



* `git log` 

 commit 이력을 확인할 때 사용한다. 출력되는 이력 사항이 너무 길어서 한 줄씩만 보고 싶다면 `--one line`, 가장 최근 것을 보고 싶다면 `-1`을 함께 작성한다. 그래프를 그리려면 `--graph`를 작성한다.



* 원격 저장소 설정 관련 명령어
  * `git remote add origin (저장소url)`
  * `git remote -v`
  * `git remote rm origin`

 로컬 repository를 원격 repository에 등록할 때 `remote add` 명령어를 사용한다. 로컬 저장소에 등록된 원격 저장소를 확인하기 위해서는 `remote -v` 명령어를 사용한다. 혹시 잘못 연결했다면 `remote rm` 명령어를 통해 repository 연결을 삭제한다.



* `git push [저장소명] [branch명]`  

 실제로 업로드되는 것은 이력들 뿐이다. 버전만 업로드되는 것이 핵심이다. 항상 `commit` 후 `push`로 이력을 업로드한다. 원격 저장소에는 가장 최신 상태의 파일만 보여진다. `[저장소명]`에는 `origin`, `upstream` 등을 설정해서 원하는 저장소에 push한다.



* `git clone [repository] [destination]` 

 원격 저장소를 복제한다. 이후 해당 폴더로 이동해서 활용하면 된다. 이후 작업을 할 때, `add`, `commit`, `push`의 흐름으로 동일하게 작업하면 된다. `init` 명령어와 동일하게 생각하자. 새로운 원격 저장소를 받아오고 싶을 때니까, 새로 시작하는 것이다. `[repository]`에 저장소를, `[destination]`에 대상 폴더를 지정한다. 예컨대, 원격 저장소와 다른 이름의 디렉토리에 소스 코드를 받아오고 싶을 때, `[destination]` 옵션을 사용하면 된다. 



* `git pull` 

 원격 저장소의  변경 사항을 받아 온다.  협업 과정에서는 항상 이력을 확인하고, 원격 저장소의 변경 사항을 받아 와야 한다. 



> *참고* : 많이 하는 실수
>
>  원격 저장소에서 다음의 버튼을 눌러 `commit`을 하게 되면, 기존 local에서의 이력과 다르다고 판단한다. 원격 저장소와 local 저장소의 이력이 다르게 구성된다는 말이다.
>
> ![git no]({{site.url}}/assets/images/git-02.png)
>
>  `git pull`을 통해 이력을 합쳐줘야 한다. Github에서 직접 손대지 말고, 애초에 로컬에서 올리자.







<br>

## 2. 블로그 만들기



 정적 파일 생성기인 `Jekyll` 혹은 `Gatsby`를 이용해 `github.io` 블로그를 만들 수 있다. `.md` 파일을 HTML, CSS 등으로 바꿔 준다.

* `Jekyll` : 예전부터 많이 쓰임. `Ruby` 언어 기반.
* `Gatsby` : 최근에 많이 쓰이는 기술. `Js`, `React`, `graphql` 기반.



<br>

## 3. 브랜치 활용하기



 독립적인 작업 환경을 구성하여 협업할 때 사용한다. 메인 작업 흐름 외에 동시에 다양한 작업을 진행할 수 있게 해 준다. 일반적으로 브랜치의 이름은 해당 작업을 나타낸다.



### 3.1. 브랜치 기초 명령어

* `git branch` : 브랜치 목록 확인
* `git branch {브랜치 이름}` : 브랜치 생성
*  `git checkout {브랜치 이름}` : 브랜치 이동
* `git checkout -b {브랜치 이름}` : 브랜치 생성 및 이동
* `git branch -d {브랜치 이름}` : 브랜치 삭제



<br>



### 3.2. 브랜치 병합

 각 브랜치에서 작업을 진행한 후, 이력을 합치기 위해 `merge` 명령어를 활용한다. 만약 서로 다른 이력에서 동일한 파일을 수정한 경우, 이력에 충돌이 발생할 수 있다. 크게 다음의 세 가지 경우로 나누어볼 수 있으며, 수정 작업을 진행해 주어야 한다.



<br>

**1) Fast-Forward**



> 별 다른 충돌 없이 이력을 병합할 수 있는 경우이다.



 `feature/test` 브랜치를 생성한 후, 이동하자.

```bash
student@M16046 MINGW64 ~/Desktop/멀캠/web (master)
$ git checkout -b feature/test
Switched to a new branch 'feature/test'
```



 `master` 브랜치에서 `feature/test` 브랜치로 이동한 것에 주의한다. 해당 브랜치에서 작업을 마친 후, commit한다.

```bash
student@M16046 MINGW64 ~/Desktop/멀캠/web (feature/test)
$ touch test.txt


student@M16046 MINGW64 ~/Desktop/멀캠/web (feature/test)
$ git add .

student@M16046 MINGW64 ~/Desktop/멀캠/web (feature/test)
$ git commit -m '기능 개발 완료'
[feature/test 6b31a45] 기능 개발 완료
 1 file changed, 0 insertions(+), 0 deletions(-)
 create mode 100644 test.txt
```



 이력을 확인한다. 현재 `feature/test` 브랜치에 있으므로, 해당 브랜치에서의 이력을 확인할 수 있다. 실제로 `log` 명령어를 확인하면, `HEAD`가 `feature/test` 브랜치로 이동했다.

```bash
student@M16046 MINGW64 ~/Desktop/멀캠/web (feature/test)
$ git log --oneline
6b31a45 (HEAD -> feature/test) 기능 개발 완료
```

 

 다시 `master` 브랜치로 옮겨 간다.

```bash
$ git checkout master
Switched to branch 'master'
```



 `master` 브랜치에서 이력을 확인하면, `test/feature` 브랜치에서의 작업은 확인할 수 없다. `test.txt`를 commit한 이력이 없다.

```bash
$ git log --oneline
08fab78 (HEAD -> master, testbranch) testbranch에서 -test 작업을 함   # branch에서의 작업은 보이지 않는다(test.txt 없음).
```



 이제 `master` 브랜치에 이력을 병합해 주어야 한다.

```bash
student@M16046 MINGW64 ~/Desktop/멀캠/web (master)
$ git merge feature/test
Updating 08fab78..6b31a45
Fast-forward # fast-forward로 한 번에 병합된다.
 test.txt | 0
 1 file changed, 0 insertions(+), 0 deletions(-)
 create mode 100644 test.txt
```



 결과를 확인하면 단순히 `HEAD`만 이동한다.

```bash
student@M16046 MINGW64 ~/Desktop/멀캠/web (master)
$ git log --oneline
6b31a45 (HEAD -> master, feature/test) 기능 개발 완료
08fab78 (testbranch) testbranch에서 -test 작업을 함
55c96b7 (origin/master) Merge branch 'master' of https://github.com/sirzzang/multicampus-scenario
```



 병합이 완료되면 해당 브랜치를 삭제한다

```bash
student@M16046 MINGW64 ~/Desktop/멀캠/web (master)
$ git branch -d feature/test
Deleted branch feature/test (was 6b31a45).
```





<br>

**2) Merge Commit**



>  다른 브랜치에서 작업하고 있는 동안, `master` 브랜치에서 이력이 추가적으로 발생한 경우이다.



 로그아웃(signout)이라는 기능을 만든다고 가정해 보자. `feature/signout` 브랜치를 생성하고 이동한다.

```bash
student@M16046 MINGW64 ~/Desktop/멀캠/web (master)
$ git checkout -b feature/signout
Switched to a new branch 'feature/signout'
```



 작업 후 commit한다.

```bash
student@M16046 MINGW64 ~/Desktop/멀캠/web (feature/signout)
$ touch signout.txt

student@M16046 MINGW64 ~/Desktop/멀캠/web (feature/signout)
$ git add .

student@M16046 MINGW64 ~/Desktop/멀캠/web (feature/signout)
$ git commit -m 'signout 기능 개발 완료'
[feature/signout 3b64214] signout 기능 개발 완료
 1 file changed, 0 insertions(+), 0 deletions(-)
 create mode 100644 signout.txt
```



 로그를 확인하자. `feature/signout` 브랜치에서의 이력이다.

```bash
student@M16046 MINGW64 ~/Desktop/멀캠/web (feature/signout) # signout branch에서 작업 중.
$ git log --oneline
3b64214 (HEAD -> feature/signout) signout 기능 개발 완료 # signout 기능 뜬 것
```



 이제 이 상태에서 `master` 브랜치에 추가 작업을 진행해 보자. 아직 `feature/signout` 브랜치에서 commit이 이루어지지 않았음을 기억하자. 먼저 `master` 브랜치로 이동하고, 새로운 파일(`mastersometask.txt`)을 생성한 후 commit하자.

```bash
student@M16046 MINGW64 ~/Desktop/멀캠/web (feature/signout)
$ git checkout master
Switched to branch 'master'

student@M16046 MINGW64 ~/Desktop/멀캠/web (master)
$ touch mastersometask.txt

student@M16046 MINGW64 ~/Desktop/멀캠/web (master)
$ git add .

student@M16046 MINGW64 ~/Desktop/멀캠/web (master)
$ git commit -m 'master 브랜치 작업 완료'
[master e780fef] master 브랜치 작업 완료
 1 file changed, 0 insertions(+), 0 deletions(-)
 create mode 100644 mastersometask.txt
```



 이 상태에서 브랜치 병합을 시도하면 `vim` 편집기 화면이 나타난다. 해당 화면에서 commit 메시지를 남긴다.

```bash
student@M16046 MINGW64 ~/Desktop/멀캠/web (master)
$ git merge feature/signout
Merge made by the 'recursive' strategy.
 signout.txt | 0
 1 file changed, 0 insertions(+), 0 deletions(-)
 create mode 100644 signout.txt
```



 이후, 자동으로 Merge Commit이 이루어진다. 로그를 확인해 보자.

```bash
student@M16046 MINGW64 ~/Desktop/멀캠/web (master)
$ git log --oneline
a2f90d1 (HEAD -> master) Merge branch 'feature/signout'
e780fef master 브랜치 작업 완료
3b64214 (feature/signout) signout 기능 개발 완료
```



 모든 병합 작업이 완료되면 해당 브랜치를 삭제한다.

```bash
$ git branch -d feature/signout
```





<br>

**3) Merge Commit 시의 충돌** 



>  특정 기능 개발 중간에 `master` 브랜치 뿐만 아니라, 다른 브랜치에서도 동시에 같은 기능을 수정하는 경우, 충돌이 발생한다.



  긴급하게 수정해야 할 작업 흐름이 있다고 하자. `hotfix/test branch`를 생성하여 작업을 진행한다. 이전에 만들어 놓은 `test.txt` 파일을 수정하는 상황을 가정하자.

```bash
(실행 결과)
student@M16046 MINGW64 ~/Desktop/멀캠/web (master)
$ git checkout -b hotfix/test
Switched to a new branch 'hotfix/test'

student@M16046 MINGW64 ~/Desktop/멀캠/web (hotfix/test)
$ ls
index.html  mastersometask.txt  signout.txt  test.txt
main.html   new.html            test.html

student@M16046 MINGW64 ~/Desktop/멀캠/web (hotfix/test)
$ git status
On branch hotfix/test
Changes not staged for commit:
  (use "git add <file>..." to update what will be committed)
  (use "git restore <file>..." to discard changes in working directory)
        modified:   test.txt
```



 작업 완료 후, 해당 브랜치에서 commit한다.

```bash
student@M16046 MINGW64 ~/Desktop/멀캠/web (hotfix/test)
$ git add .

student@M16046 MINGW64 ~/Desktop/멀캠/web (hotfix/test)
$ git commit -m 'hotfix test'
[hotfix/test 28cdf59] hotfix test
 1 file changed, 3 insertions(+)
```



 로그를 확인한다.

```bash
$ git log --oneline
28cdf59 (HEAD -> hotfix/test) hotfix test
a2f90d1 (master) Merge branch 'feature/signout'
e780fef master 브랜치 작업 완료
```



 `master` 브랜치로 이동한다. 이동 후, 동일한 파일(`test.txt`)에 추가 수정 혹은 생성 작업을 하고, commit하자.

```bash
$ git checkout master

student@M16046 MINGW64 ~/Desktop/멀캠/web (master)
$ git add .

student@M16046 MINGW64 ~/Desktop/멀캠/web (master)
$ git commit -m 'master test'
On branch master
nothing to commit, working tree clean

student@M16046 MINGW64 ~/Desktop/멀캠/web (master)
$ git status
On branch master
Changes not staged for commit:
  (use "git add <file>..." to update what will be committed)
  (use "git restore <file>..." to discard changes in working directory)
        modified:   test.txt
```



 이제 `hotfix/test` 브랜치를 `master` 브랜치에 병합하려고 하면, Merge Conflict가 발생한다. 동일한 파일에 대해 이력이 다르기 때문에 당연히 발생할 수밖에 없는 상황이다.

```bash
$ git merge hotfix/test
Auto-merging test.txt
CONFLICT (content): Merge conflict in test.txt
Automatic merge failed; fix conflicts and then commit the result.
student@M16046 MINGW64 ~/Desktop/멀캠/web (master)

$ git merge hotfix/test
Auto-merging test.txt
CONFLICT (content): Merge conflict in test.txt # 충돌!
Automatic merge failed; fix conflicts and then commit the result.
```



 충돌을 해결하기 위해서는 실제로 파일을 확인하고, 선택해야 한다. 실제로 눈으로 바뀐 부분을 확인하고, 어떤 코드가 돌아가게 하려는지 판단한 후, **첫째,** `master` 브랜치의 내용을 반영하든가, **둘째,** `hotfix/test` 브랜치의 내용을 반영하든가, **셋째,** `둘 모두를` 놔두든가 해야 한다. 

* `hotfix/test` 내용 남긴다면, `Accept Incoming Change`.
* `master` 내용 남긴다면, `Accept Current`.

```bash
(실행 결과)
student@M16046 MINGW64 ~/Desktop/멀캠/web (master|MERGING)
$ git status
On branch master
You have unmerged paths.
  (fix conflicts and run "git commit")
  (use "git merge --abort" to abort the merge)

Unmerged paths:
  (use "git add <file>..." to mark resolution)
        both modified:   test.txt

no changes added to commit (use "git add" and/or "git commit -a")
```



 이후 Merge Commit을 진행한다. `3.2.2)`에서처럼 `vim` 편집기 화면이 나타난다. commit 메시지를 작성한다.

```bash
student@M16046 MINGW64 ~/Desktop/멀캠/web (master|MERGING)
$ git add .

student@M16046 MINGW64 ~/Desktop/멀캠/web (master|MERGING)
$ git commit
[master 944a330] Merge branch 'hotfix/test'
```



 작업이 완료되면 브랜치를 삭제한다.

```bash
$ git branch -d hotfix/test
```



<br>

 위의 세 가지 상황을 정리하면 다음과 같다.

* Fast-Forward: 좋다고 생각할 수 있지만, 브랜치에서 작업했던 commit 이력이 사라진다.
* Merge Commit: 어떠한 브랜치를 병합했는지 이력이 남는다.
* Merge Conflict: 충돌을 직접 해결하고, merge commit을 진행한다.





## 4. 기타



* rebase

 이력을 합치는 과정 중 하나이다. 이력을 깔끔하게 만들기 위해 rebase라는 이름이 붙었으나, hash 값(commit history hash)이 변한다. 따라서 잘못하면 이력의 순서가 바뀐다. *~~혹시나 현업에 가게 된다면, 선임이 허락하거나 흐름을 알리지 않는 한 절대로 쓰지 말아야..~~*

