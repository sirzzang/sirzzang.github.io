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



## Submodule을 Project에 추가



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

