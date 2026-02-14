---
title:  "[Go] go run command와 working directory"
excerpt: 패키지 실행 시 working directory에 주의하지 않으면 발생할 수 있는 문제
categories:
  - Language
header:
  teaser: /assets/images/blog-Dev.jpg
tags:
  - Go
  - run
toc: true
---



<br>

 Go 어플리케이션을 개발하며 `go run` 커맨드를 이용해 어플리케이션을 실행하다, working directory를 잘못 설정해 실행하는 바람에 잘못된 결과를 얻었다.

<br>

# 구현

 구현하고 있던 Go 어플리케이션은 웹 어플리케이션으로, `/` 경로에 대한 GET 요청이 왔을 때, `Home` 핸들러 함수를 이용해 Go HTML 템플릿 `home.page.gohtml`, `base.page.gohtml`을 렌더링한다.

- `handlers.go`

  ```go
  package main
  
  import (
  	"html/template"
  	"net/http"
  	"path"
  )
  
  // go html 템플릿들이 보관된 경로
  var pathToTemplates = "./templates/" 
  
  // go html 템플릿에 넘길 데이터 구조체
  type TemplateData struct {
    // 생략
  }
  
  // `/` 요청을 처리하는 Home handler
  func (app *application) Home(w http.ResponseWriter, r *http.Request) {
  	
  	var td = make(map[string]any)
    // 생략
  	_ = app.render(w, r, "home.page.gohtml", &TemplateData{Data: td})
  }
  
  // go html 템플릿 렌더링을 위한 유틸 함수
  func (app *application) render(w http.ResponseWriter, r *http.Request, t string, td *TemplateData) error {
  
  	parsedTemplate, err := template.ParseFiles(path.Join(pathToTemplates, t), path.Join(pathToTemplates, "base.layout.gohtml"))
  
  	if err != nil {
  		http.Error(w, "Bad Request", http.StatusBadRequest)
  		return err
  	}
  	// 생략
  	err = parsedTemplate.Execute(w, td)
  	if err != nil {
  		return err
  	}
  
  	return nil
  }
  ```



 전체 디렉토리 구조는 다음과 같다. 어플리케이션 main 패키지의 진입점은 루트 디렉토리 아래의 `cmd` 폴더 아래의 `web` 폴더 아래에 존재한다.

![go-webapp-directory-structure]({{site.url}}/assets/images/go-webapp-directory-structure.png){: .align-center width="400"}



 Go html 템플릿 파일(`.gohtml`)들은 모두 프로젝트 루트 디렉토리 아래의 `templates` 폴더에 저장되어 있다.

 그리고 `handlers.go`에서는 템플릿들이 보관되어 있는 경로를 `pathToTemplates`라는 변수의 값으로 지정해 두었으며, 해당 경로는 루트 디렉토리로부터의 상대 경로를 나타내도록 설정되어 있다.



<br>



# 문제



## 상황

 아무 생각 없이 `go run` 커맨드로 코드를 실행하다가, 갑자기 `/` 경로로 접속해 봤는데 404 Bad Request가 발생한다.

![go-webapp-404-error]({{site.url}}/assets/images/go-webapp-404-error.png){: .align-center width="500"}

 `handlers.go` 소스 코드의 `render` 함수에서 템플릿 파일을 파싱하지 못하면 404 Bad Request 에러가 나도록 했기 때문에, 템플릿을 찾지 못하는 것이 아닌가 의심해 볼 수 있다.



## 원인

 결과적으로 이 문제는 `/cmd/web` 폴더에서 `go run .` 커맨드를 이용해 어플리케이션을 실행했기 때문에 발생한 문제다.

 `go run` 커맨드를 사용할 때는 패키지가 위치한 경로를 주어 패키지를 빌드하고 실행할 수 있다. 내가 구성한 패키지 디렉토리 구조에 의하면, main 패키지는 루트 디렉토리 하의 `/cmd/web` 폴더에 존재하기 때문에, main 패키지를 다음의 2가지 방법으로 실행할 수 있다.

- 프로젝트 루트 디렉토리에서 `go run ./cmd/web` 커맨드 실행
- 프로젝트 루트 디렉토리 아래 `/cmd/web` 디렉토리에서 `go run .` 커맨드 실행



 그런데 후자의 경우로 어플리케이션을 실행하면, 어플리케이션 실행 중인 경로가 `./cmd/web`으로 잡히게 된다. 그런데, 해당 경로 아래에는 `templates`라는 폴더가 없다. 따라서, `handlers.go`의 `pathToTemplates`의 값에 지정된 경로가 없고, 템플릿을 파싱할 수 없게 되는 것이다. 

 어플리케이션 실행 시, 현재 경로가 어떻게 잡히는지 아래와 같이 `os` 패키지를 이용해 간단히 확인해 볼 수 있다.

- `main.go`

  ```go
  package main
  
  import (
  	"log"
  	"os"
  )
  
  func main() {
  
  	dir, err := os.Getwd()
  	if err != nil {
  		log.Fatal(err)
  	}
  	log.Printf("Working directory: %s", dir)
    
    // 생략
  }
  ```
  
- 실행 결과

  | 루트 디렉토리에서 실행 시                                    | `/cmd/web` 디렉토리에서 실행 시                              |
  | ------------------------------------------------------------ | ------------------------------------------------------------ |
  | ![go-webapp-cmdweb]({{site.url}}/assets/images/go-webapp-cmdweb.png) | ![go-webapp-root]({{site.url}}/assets/images/go-webapp-root.png) |

  

<br>



# 해결

 ~~그 전까지 잘 실행되던 게 안 되어서 갑자기 당황했지만~~ 아주 간단하게 해결된다.

- 루트 디렉토리에서 `go run ./cmd/web` 커맨드를 이용해 실행
- `handlers.go`에서 `pathToTemplates` 변수의 값을 절대 경로를 이용해 지정

```go
var pathToTemplates = "/Users/eraser/tutorial/go-webapp/templates/"
```

 다만, 두 번째 해결 방법의 경우 소스 코드에 절대 경로가 그대로 들어가기 때문에 좋은 방식인지는 모르겠다.



<br>

# 결론

 오랜만에 마주한 아주 바보 같은 실수다. 간혹 정신 놓고 개발하다 또 이런 문제 겪을까봐 스스로 박제하는 차원에서 기록한다.

- 실행 경로를 항상 주의 깊게 살피자
- 코드 내에서 런타임에 결정되는 실행 경로와 상관 없이 특정 경로 값을 이용하고 싶은 경우, 어떻게 하는 것이 좋을지 고민해 보자
  - 어플리케이션 실행 시 command를 이용할 수 있지 않을까
  - 지금은 개발 단계지만, 개발 완료 후 어플리케이션 설정 관련 config에서 설정해볼 수 있지 않을까

