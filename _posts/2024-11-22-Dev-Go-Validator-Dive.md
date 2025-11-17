---
title:  "[Go] gin 중첩 구조체 validation"
excerpt: gin의 binding tag로 dive를 사용하면 중첩 구조체에 대한 validation을 수행할 수 있다
categories:
  - Dev
toc: true
header:
  teaser: /assets/images/blog-Dev.jpg
tags:
  - go
  - gin
  - validator
---

<br>

gin 프레임워크를 이용해 API 서버를 개발하던 중, 중첩 구조체에 대한 binding validation을 수행하기 위한 방법을 기록해 두고자 한다.
- [gin](https://github.com/gin-gonic/gin)

<br>

# 배경

[gin을 이용해 친절한(?) 에러 메시지 보내기](https://sirzzang.github.io/dev/Dev-Go-Validator-Custom-Error-Message/){: .btn .btn--primary .btn--small}에서 알아 봤듯, gin 프레임워크를 이용하면 Request Body를 원하는 구조체로 쉽게 binding할 수 있다. 검증까지 포함해서!

<br>

 그런데, binding 대상이 되는 구조체의 속성이 다른 구조체를 요소로 갖는 slice나 array, 혹은 map인 경우, 어떻게 validation해야 할까. 

 예컨대, 아래와 같은 `AddServer` handler를 작성할 경우, 이 handler는 Request를 `AddServersRequest` 구조체에 binding하는 과정에서, `Servers` 슬라이스 안에 있는 각각의 요소들이 `Server`가 가지고 있는 binding tag를 모두 만족하는지 확인할 수 있을까?

```go
type Server struct {
	Name string `json:"name" binding:"required,min=1,max=255"`
	IP   string `json:"ip" binding:"required,ipv4"`
}

type AddServersRequest struct {
	Servers []*Server `json:"servers" binding:"dive"`
}

func (h *Handler) AddServer(c *gin.Context) {
	var req AddServersRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		c.AbortWithStatusJSON(http.StatusBadRequest, exception.InvalidRequestBodyException(err.Error()))
		return
	}
    
	if len(req.Servers) == 0 {
		c.JSON(http.StatusNoContent, nil)
		return
	}
    
    // 생략
}
```

 <br>

실제로 확인해 보면, 그렇지 않은 것을 확인할 수 있다. IPv4 태그를 만족하지 않는 요청을 보냈음에도, `400 Bad Request` 처리되지 않는다.

```bash
curl -X 'POST' \
  'http://localhost:9090/api/servers' \
  -H 'accept: application/json' \
  -H 'Content-Type: application/json' \
  -d '{
  "servers": [
    {
      "ip": "server1",
      "name": "server1_name"
    }
  ]
}'
```

<br>

그렇다면, 요청을 구조체로 binding하는 과정에서 array, slice 등에 속한 각각의 요소에 대해서도 validation을 진행하고 싶다면, 어떻게 해야 할까.



<br>

# 분석

먼저 gin의 모델 바인딩은 어떻게 동작하는지 살펴 보자. 위의 예시에서 작성한 `ShouldBindJSON`의 소스 코드를 보면, `binding.Binding` 인터페이스 타입 인스턴스의 `Bind` 메서드를 호출해 모델 바인딩을 진행하는 것을 확인할 수 있다.

```go
// ShouldBindJSON is a shortcut for c.ShouldBindWith(obj, binding.JSON).
func (c *Context) ShouldBindJSON(obj interface{}) error {
	return c.ShouldBindWith(obj, binding.JSON)
}

// ShouldBindQuery is a shortcut for c.ShouldBindWith(obj, binding.Query).
func (c *Context) ShouldBindQuery(obj interface{}) error {
	return c.ShouldBindWith(obj, binding.Query)
}

// ShouldBindWith binds the passed struct pointer using the specified binding engine.
// See the binding package.
func (c *Context) ShouldBindWith(obj interface{}, b binding.Binding) error {
	return b.Bind(c.Request, obj)
}
```

- [gin.Context.ShouldBindJSON](https://github.com/gin-gonic/gin/blob/b7e8a6b9b062473c7f3f4f5c16d0a28b6244de48/context.go#L499)
  - [gin.Context.ShouldBindWith](https://github.com/gin-gonic/gin/blob/b7e8a6b9b062473c7f3f4f5c16d0a28b6244de48/context.go#L510)를 호출함
  - 호출 시, 인자로 bind 대상이 되는 `obj`와 `binding.Binding` 인터페이스 타입의 `b`를 넘겨야 함

```go
type Binding interface {
	Name() string
	Bind(*http.Request, interface{}) error
}
```

- [binding.Binding](https://github.com/gin-gonic/gin/blob/b7e8a6b9b062473c7f3f4f5c16d0a28b6244de48/binding/binding.go#L26)

<br>

`binding.JSON`은 `binding.Binding` 인터페이스를 구현한 `jsonBinding` 타입 인스턴스이다. `Bind` 호출 시, `decodeJSON`을 이용해 binding을 진행한다. 우선 request 및 request body가 `nil`인지 확인하고, json decoding을 진행한 뒤, `validate` 함수를 호출한다.

```go
var (
	JSON          BindingBody = jsonBinding{}
	XML           BindingBody = xmlBinding{}
	Form          Binding     = formBinding{}
	Query         Binding     = queryBinding{}
	FormPost      Binding     = formPostBinding{}
	FormMultipart Binding     = formMultipartBinding{}
	ProtoBuf      BindingBody = protobufBinding{}
	MsgPack       BindingBody = msgpackBinding{}
	YAML          BindingBody = yamlBinding{}
	Uri           BindingUri  = uriBinding{}
	Header        Binding     = headerBinding{}
	TOML          BindingBody = tomlBinding{}
)
```

- [binding.JSON](https://github.com/gin-gonic/gin/blob/b7e8a6b9b062473c7f3f4f5c16d0a28b6244de48/binding/binding.go#L48)

```go
type jsonBinding struct{}

func (jsonBinding) Name() string {
	return "json"
}

func (jsonBinding) Bind(req *http.Request, obj any) error {
	if req == nil || req.Body == nil {
		return errors.New("invalid request")
	}
	return decodeJSON(req.Body, obj)
}

func (jsonBinding) BindBody(body []byte, obj any) error {
	return decodeJSON(bytes.NewReader(body), obj)
}

func decodeJSON(r io.Reader, obj any) error {
	decoder := json.NewDecoder(r)
	if EnableDecoderUseNumber {
		decoder.UseNumber()
	}
	if EnableDecoderDisallowUnknownFields {
		decoder.DisallowUnknownFields()
	}
	if err := decoder.Decode(obj); err != nil {
		return err
	}
	return validate(obj)
}
```

- [jsonBinding](https://github.com/gin-gonic/gin/blob/b7e8a6b9b062473c7f3f4f5c16d0a28b6244de48/binding/json.go)

> *참고*: validation 이전의 decoding
>
> json decoding 과정을 거치기 때문에, binding 과정에서 validation 단계에 가기 전, decoding에 실패하면 ~~당연히~~ 에러 처리 된다. 예컨대, 위의 예에서 `AddServer` 핸들러가 decoding할 수 없는 JSON을 보내 보면 아래와 같이 `400 Bad Request` 처리 된다.
>
>
> ```bash
> curl -X 'POST' \
> 'http://localhost:9090/api/servers' \
>     -H 'accept: application/json' \
>     -H 'Content-Type: application/json' \
>     -d '{
> "servers": [
> {
>   "ip": "string",
>    "name": "string"
>  }
> }' 
> {"message":"invalid request body","data":"invalid character '}' after array element"}
> ```
>

<br>

`validate` 함수는 `binding` 패키지에 정의되어 있는 `Validator` 변수가 참조하는 인스턴스의 `ValidateStruct` 메서드를 호출한다. 

```go
var Validator StructValidator = &defaultValidator{}

// 생략

func validate(obj interface{}) error {
	if Validator == nil {
		return nil
	}
	return Validator.ValidateStruct(obj)
}
```

- [binding.validate](https://github.com/gin-gonic/gin/blob/b7e8a6b9b062473c7f3f4f5c16d0a28b6244de48/binding/binding.go#L77)
- [binding.Validator](https://github.com/gin-gonic/gin/blob/b7e8a6b9b062473c7f3f4f5c16d0a28b6244de48/binding/binding.go#L45)

<br>

여기서 이용되는 `Validator`는 `StructValidator` 타입인데, 이 `StructValidator`는 `ValidateStruct`와 `RegisterValidations`라는 두 가지 메서드를 갖는 인터페이스 타입이다. 이 타입의 설명을 읽어 보면, `ValidateStruct` 호출 시, 인자로 받는 타입이 구조체나 구조체에 대한 포인터가 아닐 경우, validation을 진행하지 않는다고 나와 있다.

```go
var Validator StructValidator = &defaultValidator{}
```

- [binding.Validator](https://github.com/gin-gonic/gin/blob/b7e8a6b9b062473c7f3f4f5c16d0a28b6244de48/binding/binding.go#L45)

```go
type StructValidator interface {
	// ValidateStruct can receive any kind of type and it should never panic, even if the configuration is not right.
	// If the received type is not a struct, any validation should be skipped and nil must be returned.
	// If the received type is a struct or pointer to a struct, the validation should be performed.
	// If the struct is not valid or the validation itself fails, a descriptive error should be returned.
	// Otherwise nil must be returned.
	ValidateStruct(interface{}) error

	// RegisterValidation adds a validation Func to a Validate's map of validators denoted by the key
	// NOTE: if the key already exists, the previous validation function will be replaced.
	// NOTE: this method is not thread-safe it is intended that these all be registered prior to any validation
	RegisterValidation(string, validator.Func) error
}
```

- [binding.StructValidator](https://github.com/gin-gonic/gin/blob/b7e8a6b9b062473c7f3f4f5c16d0a28b6244de48/binding/binding.go#L31)



<br>

결론적으로, `ShouldBindWithJSON`을 이용해 Request Body에 대한 binding을 진행할 경우, `StructValidator` 타입의 `ValidateStruct` 메서드를 호출하게 됨을 알 수 있다. 그런데, 해당 메서드는 **구조체나 구조체에 대한 포인터를 받을 경우에만** validation을 진행하기 때문에, struct type이 아닌 다른 타입에 대해 validation을 진행하기 위해서는 다른 방법을 써야 함을 알 수 있다.





<br>

# 해결

- validator 라이브러리가 제공하는 `dive` 태그 이용
- ~~binding 대상이 되는 request body에 대한 unmarshalling 메서드 재정의~~ (굳이?)

<br>

## dive 태그 이용

gin이 이용하고 있는 validator 라이브러리는 내장 태그로 `dive`라는 것을 지원한다. 해당 태그를 사용하면 slice, array 혹은 map 타입 내부 각각의 요소에 대해서도 validation을 적용할 수 있다.

- [dive](https://pkg.go.dev/github.com/go-playground/validator#hdr-Dive)

<br>

 다차원 중첩에 대해서도 동작한다. struct 속성 내에 nested slice, array, map에 대해, 원하는 레벨까지 `dive` 태그를 붙여 주면 된다.

예컨대, `[][]string` 타입의 속성이 validation tag로 `gt=0,dive,len=1,dive,required`를 가지고 있다면, 다음과 같이 동작하게 된다.

- `gt=0`이 전체 slice에 대해 적용되고,
  - 즉, slice의 길이가 0보다 커야 함
- `dive` 태그에 의해 전체 slice 내부 요소인 `[]string` 타입 값에 대해 `len=1` 태그가 적용되고,
  - 즉, nested slice의 길이가 1이어야 함
- 두 번째 `dive` 태그에 의해 nested slice 내부 요소인 `string` 값에 대해 `required` 태그가 적용됨

```go
type MyStruct struct {
	Prop [][]string `json:"prop" binding:"gt=0,dive,len=1,dive,required"`
}

func handler(c *gin.Context) {
	var input MyStruct
	if err := c.ShouldBindJSON(&input); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}
	c.JSON(http.StatusOK, nil)
}

func TestDive(t *testing.T) {
	tests := []struct {
		body string
	}{
		{`{"prop": []}`},                  // []: gt=0에서 걸려야 함 -> Key: 'MyStruct.Prop' Error:Field validation for 'Prop' failed on the 'gt' tag"
		{`{"prop": [[], []]}`},            // []string: len=1에서 걸려야 함 -> "Key: 'MyStruct.Prop[0]' Error:Field validation for 'Prop[0]' failed on the 'len' tag\nKey: 'MyStruct.Prop[1]' Error:Field validation for 'Prop[1]' failed on the 'len' tag"
		{`{"prop": [[""], [""]]}`},        // string: required에서 걸려야 함 -> "Key: 'MyStruct.Prop[0][0]' Error:Field validation for 'Prop[0][0]' failed on the 'required' tag\nKey: 'MyStruct.Prop[1][0]' Error:Field validation for 'Prop[1][0]' failed on the 'required' tag"
		{`{"prop": [["a"], [""]]}`},       // string: required에서 걸려야 함 -> "Key: 'MyStruct.Prop[1][0]' Error:Field validation for 'Prop[1][0]' failed on the 'required' tag"
		{`{"prop": [["a"], ["b"]]}`},      // 정상
		{`{"prop": [["a"], ["b", "c"]]}`}, // []string: len=1에서 걸려야 함 -> "Key: 'MyStruct.Prop[1]' Error:Field validation for 'Prop[1]' failed on the 'len' tag"
	}

	for _, tt := range tests {
		req := httptest.NewRequest(http.MethodPost, "/", bytes.NewBufferString(tt.body))
		req.Header.Set("Content-Type", "application/json")

		w := httptest.NewRecorder()

		router := gin.Default()
		router.POST("/", handler)

		router.ServeHTTP(w, req)

		t.Logf("response: %v", w.Body.String())
		fmt.Println("=====================================================================")
	}
}
```

<br>

비슷하게, `[][]string` 타입의 속성이 validation tag로 `gt=0,dive,dive,required`를 가지고 있다면, 다음과 같이 동작하게 된다.

- `gt=0`이 전체 slice에 대해 적용되고,
  - 전체 slice의 길이가 0보다 커야 함
- slice 내부 요소인 `[]string` 타입의 값에 대해서는 적용되는 validation이 없고,
- `dive,dive` 태그에 의해 nested slice 내부 요소인 `string` 타입의 값에 대해 `require` 필드가 적용됨

```go
type MyStruct2 struct {
	Prop [][]string `json:"prop" binding:"gt=0,dive,dive,required"`
}

func handler2(c *gin.Context) {
	var input MyStruct2
	if err := c.ShouldBindJSON(&input); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}
	c.JSON(http.StatusOK, gin.H{"data": input})
}

func TestDive2(t *testing.T) {
	tests := []struct {
		body string
	}{
		{`{"prop": []}`},                  // []: gt=0에서 걸려야 함 -> "Key: 'MyStruct2.Prop' Error:Field validation for 'Prop' failed on the 'gt' tag"
		{`{"prop": [[], []]}`},            // 정상
		{`{"prop": [[""], [""]]}`},        // string: required에서 걸려야 함 -> "Key: 'MyStruct2.Prop[0][0]' Error:Field validation for 'Prop[0][0]' failed on the 'required' tag\nKey: 'MyStruct2.Prop[1][0]' Error:Field validation for 'Prop[1][0]' failed on the 'required' tag"
		{`{"prop": [["a"], [""]]}`},       // string: required에서 걸려야 함 -> "Key: 'MyStruct2.Prop[1][0]' Error:Field validation for 'Prop[1][0]' failed on the 'required' tag"
		{`{"prop": [["a"], ["b", "c"]]}`}, // 정상
	}

	for _, tt := range tests {
		req := httptest.NewRequest(http.MethodPost, "/", bytes.NewBufferString(tt.body))
		req.Header.Set("Content-Type", "application/json")

		w := httptest.NewRecorder()

		router := gin.Default()
		router.POST("/", handler2)

		router.ServeHTTP(w, req)

		t.Logf("response: %v", w.Body.String())
		fmt.Println("=====================================================================")
	}
}
```

<br>



`key`, `endkey`를 이용하면 map의 key에 대해서도 validation을 적용할 수 있다고 한다.

예컨대, `map[string]string` 타입의 속성이 validation tag로 `gt=0,dive,keys,eg=1|eq=2,endkeys,required` 를 가지고 있다면, 다음과 같이 동작하게 된다.

- `gt=0`이 map 자체에 대해 적용되고,
  - 전체 map의 길이가 0보다 커야 함
- `eq=1|eq=2`는 map key에 대해 적용되고,
  - map의 key가 `1` 혹은 `2`여야 함
- `required`는 map value에 대해 적용됨

```go
type MyStruct3 struct {
	Prop map[string]string `json:"prop" binding:"gt=0,dive,keys,eq=1|eq=2,endkeys,required"`
}

func handler3(c *gin.Context) {
	var input MyStruct3
	if err := c.ShouldBindJSON(&input); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}
	c.JSON(http.StatusOK, gin.H{"data": input})
}

func TestDive3(t *testing.T) {
	tests := []struct {
		body string
	}{
		{`{}`},                       // gt=0에서 걸려야 함 -> "Key: 'MyStruct3.Prop' Error:Field validation for 'Prop' failed on the 'gt' tag"
		{`{"prop": {}}`},             // gt=0에서 걸려야 함 -> "Key: 'MyStruct3.Prop' Error:Field validation for 'Prop' failed on the 'gt' tag"
		{`{"prop": {"1": "value"}}`}, // 정상
		{`{"prop": {"a": "value"}}`}, // eq=1|eq=2에서 걸려야 함
		{`{"prop": {"1": "value", "2": "value"}}`},               // 정상 -> "Key: 'MyStruct3.Prop[a]' Error:Field validation for 'Prop[a]' failed on the 'eq=1|eq=2' tag\nKey: 'MyStruct3.Prop[c]' Error:Field validation for 'Prop[c]' failed on the 'eq=1|eq=2' tag"
		{`{"prop": {"1": "value", "2": "value", "3": "value"}}`}, // eq=1|eq=2에서 걸려야 함 -> "Key: 'MyStruct3.Prop[3]' Error:Field validation for 'Prop[3]' failed on the 'eq=1|eq=2' tag"
		{`{"prop": {"1": ""}}`},                                  // required에서 걸려야 함 -> "Key: 'MyStruct3.Prop[1]' Error:Field validation for 'Prop[1]' failed on the 'required' tag"
		{`{"prop": {"1": "", "2": ""}}`},                         // required에서 걸려야 함 -> "Key: 'MyStruct3.Prop[1]' Error:Field validation for 'Prop[1]' failed on the 'required' tag\nKey: 'MyStruct3.Prop[2]' Error:Field validation for 'Prop[2]' failed on the 'required' tag"
	}

	for _, tt := range tests {
		fmt.Printf("req: %s\n", tt.body)
		req := httptest.NewRequest(http.MethodPost, "/", bytes.NewBufferString(tt.body))
		req.Header.Set("Content-Type", "application/json")

		w := httptest.NewRecorder()

		router := gin.Default()
		router.POST("/", handler3)

		router.ServeHTTP(w, req)

		t.Logf("response: %v", w.Body.String())
		fmt.Println("=====================================================================")
	}
}
```







<br>

# 결론

validator가 사용하는 validation tag에 `dive`만 추가해 주면 원하는 대로 동작하게 된다. gin 프레임워크에서 사용하는 validation tag는 `binding`이기 때문에, 아래와 같이 `binding` 태그에 `dive`만 추가해 주면  된다.

```go
type AddServersRequest struct {
	Servers []*Server `json:"servers" binding:"dive"`
} 
```

<br>

`400 Bad Request` 처리되지 않았던 요청이, `400 Bad Request` 처리 된다.

```bash
curl -X 'POST' \
  'http://localhost:9090/api/servers' \
  -H 'accept: application/json' \
  -H 'Content-Type: application/json' \
  -d '{
  "servers": [
    {
      "ip": "server2",
      "name": "server2_name"
    }
  ]
}'
```

```json
{
  "message": "invalid request body",
  "data": "IP must be a valid IPv4 address."
}
```

<br>













