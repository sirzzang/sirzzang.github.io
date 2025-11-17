---
title:  "[Git] Permission Denied (public key) 에러 해결"
excerpt: git clone 과정에서 permission denied 에러 해결 방법
categories:
  - Dev
toc: false
header:
  teaser: /assets/images/blog-Dev.jpg
tags:
  - Git
  - permission denied
  - SSH
  - HTTP
  - clone
  - 암호화
---



 `git clone git@github.com:~~`과 같은 방식을 사용하여 원격 저장소의 코드를 클론해 오려다가 Permission Denied 에러가 났다.

![git-clone-ssh-error]({{site.url}}/assets/images/git-clone-ssh-error.png)



<br>

 그런데, `git clone https://github.com/~~.git`와 같은 방식을 사용해 git clone을 하니 되었다.

![git-clone-http-success]({{site.url}}/assets/images/git-clone-http-success.png)

<br>

 일단, 두 방식의 차이는 ssh 키의 사용 여부이다(*[참고한 StackOverflow 글](https://stackoverflow.com/questions/21532367/why-does-git-works-but-git-does-not)*). 처음 오류가 났던 방식에서 사용한 `git@` 방식은, SSH 프로토콜을 사용한 방식이다. 즉, `ssh:git@`의 git 주소를 사용해 클론하는 것이다. 따라서 올바른 SSH 키가 없으면 오류가 난다. 

 어차피 똑같은 clone 기능인데 뭐가 다른가에 대해서는 [이 글](https://develoduck.tistory.com/10)에서 힌트를 얻을 수 있었다. HTTPS 프로토콜을 통해 클론해 오는 방식(*기존에 내가 사용하던 방식*)에서는 사용자 username과 password를 물어본다. 그런데, 돌이켜 보니 이걸 애초에 초기에 설정했었고, 이후에는 한 번도 물어보지 않았다. 초기 설정 당시 git credential 저장소 혹은 window 자격증명 관리자의 기능을 통해 계정 정보가 저장된 것이기 때문에 매 번 로그인을 하지 않아도 되는 것이다.

 이와 비슷하게 SSH 프로토콜을 사용하여 접속하고자 할 경우, SSH key를 등록해 주기만 하면 된다. 그런데 나는 이전까지 한 번도 내 깃허브 계정의 SSH 키를 생성하지 않았고, 당연히 내 로컬 기기에 그 SSH 키가 담겨 있을 리도 없었다. 그러므로 오류가 난 것~~*(날 수 밖에 없었던 것)*~~이었다.

> *참고*: 그 외 Permission Denied 에러의 다른 이유들
>
>   [공식문서](https://docs.github.com/en/github/authenticating-to-github/error-permission-denied-publickey)를 참고하면, `sudo` 커맨드를 사용하거나, 올바른 서버를 사용하지 않는 경우(`githib.com`, `guthub.com` 등과 같이 오타를 내는 경우도 포함된다), `git` 유저가 아닌 자신의 유저 네임을 사용하는 경우도 Permission Denied 에러가 난다고 한다.
>
>  SSH 키를 생성한 후라면, 위의 경우도 조심해야 할 듯. ~~어쨌든 지금의 나에게는 해당되지 않는 이야기~~

<br>

 [공식문서](https://docs.github.com/en/github/authenticating-to-github/generating-a-new-ssh-key-and-adding-it-to-the-ssh-agent)를 참고해 SSH 키를 만들고 오류를 해결해 보자.

<br>

 `Ed25519` 방식으로 내 깃허브 계정에 SSH 키를 생성한다.

* 저장할 경로
* 암호

![gen-ssh-key]({{site.url}}/assets/images/gen-ssh-key.png)

<br>

 생성된 SSH 키를 ssh-agent에 등록한다.

![add-ssh-key-agent]({{site.url}}/assets/images/add-ssh-key-agent.png)

<br>

 github 계정 settings에 들어가서, SSH 키가 존재하는 파일을 열어 복사한 뒤, SSH 공개키를 붙여 넣고 저장한다. 

![ssh-key]({{site.url}}/assets/images/ssh-key.png)

<center><sup>`pub` 파일을 열기 위해 bash 터미널에서 `cat` 명령어를 사용하면 쉽다.</sup></center>

![ssh-register]({{site.url}}/assets/images/ssh-register.png)

<br>

 

 아래와 같이 접속되면 성공!

![ssh-success]({{site.url}}/assets/images/ssh-success.png)