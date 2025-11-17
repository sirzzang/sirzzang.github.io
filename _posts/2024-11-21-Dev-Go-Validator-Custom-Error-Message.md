---
title:  "[Go] gin validator 에러 메시지 변경"
excerpt: gin의 json struct validator를 사용할 때, 사용자 친화적인 에러 메시지를 반환해 보자
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

gin 프레임워크를 이용해 API 서버를 개발하던 중, Request Body에 대한 validation이 실패할 경우 사용자에게 어떤 메시지를 전달해야 할 지에 대해 고민한 과정과 결과에 대해 기록하고자 한다.
- [gin](https://github.com/gin-gonic/gin)

<br>

# 배경

 gin 프레임워크를 이용하면 Request Body를 원하는 구조체로 쉽게 binding할 수 있다. 아래와 같이 Request Body에 매핑되는 구조체를 작성하고, `binding` 태그를 작성해 주면 된다. 

```go
type AddTrainMetricRequest struct {
	MAP float64 `json:"mean_average_precision" binding:"required"`
}
```
- [gin의 model binding and validation](https://gin-gonic.com/docs/examples/binding-and-validation/)
- [validator의 baked in validations](https://github.com/go-playground/validator?tab=readme-ov-file#baked-in-validations)
- [validator의 custom validation](https://github.com/go-playground/validator/blob/master/_examples/custom-validation/main.go)

<br>

나의 경우 HTTP handler에서 `ShouldBindJSON`을 이용해 Request Body를 원하는 타입의 구조체로 바인딩하고, 이 과정에서 에러 발생 시 해당 에러를 그대로 사용자에게 전달했다. 

```go
func (h *Handler) AddTrainMetric(c *gin.Context) {
    var req AddTrainMetricRequest
	if err := c.ShouldBindJSON(&req); err != nil {
        c.AbortWithStatusJSON(http.StatusBadRequest, exception.InvalidRequestBodyException(err.Error()))
	return
    }
    
    // 생략
}
```

<br>


그런데 이렇게 validator가 반환하는 에러 메시지를 그대로 사용자에게 전달하다 보니, 사용자가 에러를 직관적으로 이해하지 못한다는 문제점이 있었다.

```json
{"message":"invalid request body","data":"Key: 'AddTrainMetricRequest.MAP' Error:Field validation for 'MAP' failed on the 'required' tag"}
```



이에 어떻게 하면 사용자가 더 이해하기 쉬운 에러를 전달할 수 있을까 고민하게 되었다.



<br>

# 해결



validator 라이브러리는 validation에 실패할 경우, `ValidationErrors` 타입의 에러를 반환한다. 해당 에러는 `[]FieldError` 타입으로, 어떤 필드가 어떤 태그 검증에 실패했는지에 대한 정보를 담고 있다.

```go
// ValidationErrors is an array of FieldError's
// for use in custom error messages post validation.
type ValidationErrors []FieldError

// Error is intended for use in development + debugging and not intended to be a production error message.
// It allows ValidationErrors to subscribe to the Error interface.
// All information to create an error message specific to your application is contained within
// the FieldError found within the ValidationErrors array
func (ve ValidationErrors) Error() string {

	buff := bytes.NewBufferString("")

	var fe *fieldError

	for i := 0; i < len(ve); i++ {

		fe = ve[i].(*fieldError)
		buff.WriteString(fe.Error())
		buff.WriteString("\n")
	}

	return strings.TrimSpace(buff.String())
}
```
- [ValidationErrors](https://pkg.go.dev/github.com/go-playground/validator#ValidationErrors)
  - `Error()` 메서드에 대한 주석을 보니, 해당 에러가 반환하는 에러 메시지는 개발 및 디버깅 용일 뿐, production 용으로는 적절하지 못하다고 아주 *친절하게* 설명되어 있다. ~~그런데도 그걸 사용자에게 그대로 반환했던 나 자신:)~~

```go
type FieldError interface {

	// returns the validation tag that failed. if the
	// validation was an alias, this will return the
	// alias name and not the underlying tag that failed.
	//
	// eg. alias "iscolor": "hexcolor|rgb|rgba|hsl|hsla"
	// will return "iscolor"
	Tag() string

	// returns the validation tag that failed, even if an
	// alias the actual tag within the alias will be returned.
	// If an 'or' validation fails the entire or will be returned.
	//
	// eg. alias "iscolor": "hexcolor|rgb|rgba|hsl|hsla"
	// will return "hexcolor|rgb|rgba|hsl|hsla"
	ActualTag() string

	// returns the namespace for the field error, with the tag
	// name taking precedence over the fields actual name.
	//
	// eg. JSON name "User.fname"
	//
	// See StructNamespace() for a version that returns actual names.
	//
	// NOTE: this field can be blank when validating a single primitive field
	// using validate.Field(...) as there is no way to extract it's name
	Namespace() string

	// returns the namespace for the field error, with the fields
	// actual name.
	//
	// eq. "User.FirstName" see Namespace for comparison
	//
	// NOTE: this field can be blank when validating a single primitive field
	// using validate.Field(...) as there is no way to extract it's name
	StructNamespace() string

	// returns the fields name with the tag name taking precedence over the
	// fields actual name.
	//
	// eq. JSON name "fname"
	// see StructField for comparison
	Field() string

	// returns the fields actual name from the struct, when able to determine.
	//
	// eq.  "FirstName"
	// see Field for comparison
	StructField() string

	// returns the actual fields value in case needed for creating the error
	// message
	Value() interface{}

	// returns the param value, in string form for comparison; this will also
	// help with generating an error message
	Param() string

	// Kind returns the Field's reflect Kind
	//
	// eg. time.Time's kind is a struct
	Kind() reflect.Kind

	// Type returns the Field's reflect Type
	//
	// // eg. time.Time's type is time.Time
	Type() reflect.Type

	// returns the FieldError's translated error
	// from the provided 'ut.Translator' and registered 'TranslationFunc'
	//
	// NOTE: if no registered translator can be found it returns the same as
	// calling fe.Error()
	Translate(ut ut.Translator) string
}
```
- [FieldError](https://pkg.go.dev/github.com/go-playground/validator#FieldError)



<br>

따라서 `ShouldBindJSON`에서 반환된 에러가 `ValidationErrors` 타입인지 확인하고, 이 경우 사용자가 이해할 수 있는 메시지로 변환하면 된다. 다음과 같은 두 가지 방법을 이용할 수 있다.
- Custom Helper Function
- Translator 이용

<br>


## Custom Helper Function

조금 무식하지만, 필드 에러를 일일이 확인해 에러 메시지로 만들어 주는 방법이다. 어떤 Helper Function을 만들지는 구현자의 자유이지만, 나는 임의로 아래와 같은 방식을 사용해 봤다.
```go
const (
	FieldErrorRequired   = "required"
	FieldErrorMin        = "min"
	FieldErrorMax        = "max"
	FieldErrorStartsWith = "startswith"
	FieldErrorIPv4       = "ipv4"
)

func FieldErrorMessage(tag string) string {
	switch tag {
	case FieldErrorRequired:
		return "This field is required."
	case FieldErrorMin:
		return "This field violates the minimum length constraint."
	case FieldErrorMax:
		return "This field violates the maximum length constraint."
	case FieldErrorStartsWith:
		return "This field violates the prefix constraint."
	case FieldErrorIPv4:
		return "This field violates the IPv4 constraint."
	default:
		return fmt.Sprintf("This field violates the %s constraint", tag)
	}
}
```



이후 HTTP Handler에서 아래와 같은 방식으로 validation error를 처리한다.
```go
import (
	"github.com/gin-gonic/gin"
	"github.com/go-playground/validator/v10"
)

type AddProjectRequest struct {
	Name    string `json:"name" binding:"required,min=1,max=3"`
	Sources []int  `json:"source_ids" binding:"required,min=1"`
	Classes []int  `json:"class_ids" binding:"required,min=1"`
}

func (h *Handler) AddProject(c *gin.Context) {
	var req dto.AddProjectRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		var ve validator.ValidationErrors
		switch {
		case errors.As(err, &ve):
			fieldErrors := make(map[string]string)
			for _, fe := range ve {
				fieldErrors[fe.Field()] = exception.FieldErrorMessage(fe.Tag())
			}
			c.AbortWithStatusJSON(http.StatusBadRequest, exception.InvalidRequestBodyFieldsException(fieldErrors))
			return
		default:
			c.AbortWithStatusJSON(http.StatusBadRequest, exception.InvalidRequestBodyException(err.Error()))
			return
		}
	}
	
	// 생략
}	
```



아래와 같이 요청을 보냈을 때, Request Body에서 어떤 필드 검증에 실패했는지를 확인할 수 있다.
```bash
curl -X 'POST' \
  'http://localhost:9090/api/projects' \
  -H 'accept: application/json' \
  -H 'Content-Type: application/json' \
  -d '{
    "name": "3333333333",
    "source_ids": [],
    "class_ids": []
}'
```

```json
{
    "message": "invalid fields in request body",
    "data": {
        "Classes": "This field violates the minimum length constraint.",
        "Name": "This field violates the maximum length constraint.",
        "Sources": "This field violates the minimum length constraint."
    }
}
```






<br>


## Translator 이용

validator의 translation 기능을 이용하면 조금 더 읽기 편한 메시지를 확인할 수 있다. `FieldError` 인터페이스에 `Translate`가 있는데, 이 메서드를 이용하면 된다. 

아래와 같이 validator를 생성한 후, translator를 등록해 주면 된다. 그리고 해당 translator를 이용해 `FieldError` 타입의 값에 대해 `Translate` 메서드를 호출한다. custom 에러 메시지를 등록하는 것 또한 가능하다. 
```go
package main

import (
	"fmt"

	"github.com/go-playground/locales/en"
	ut "github.com/go-playground/universal-translator"
	"github.com/go-playground/validator/v10"
	en_translations "github.com/go-playground/validator/v10/translations/en"
)

func main() {

	// NOTE: omitting allot of error checking for brevity

	en := en.New()
	uni = ut.New(en, en)

	// this is usually know or extracted from http 'Accept-Language' header
	// also see uni.FindTranslator(...)
	trans, _ := uni.GetTranslator("en")

	validate = validator.New()
	en_translations.RegisterDefaultTranslations(validate, trans)

	translateAll(trans)
	translateIndividual(trans)
	translateOverride(trans) // yep you can specify your own in whatever locale you want!
}
```
- [validator translation](https://github.com/go-playground/validator/blob/master/_examples/translations/main.go)

<br>

gin에 접목하기 위해서는 gin의 binding validator에 translator를 등록해 주면 된다. 위의 코드에서의 과정을 gin의 binding validator를 대상으로 해 주면 된다.
```go
en := en.New()
uni := ut.New(en, en)

trans, _ := uni.GetTranslator("en")

v, ok := binding.Validator.Engine().(*validator.Validate)
if ok {
	en_translations.RegisterDefaultTranslations(v, trans)
} else {
	v = validator.New()
}

// custom translation
v.RegisterTranslation("startswith", trans, func(ut ut.Translator) error {
	return ut.Add("startswith", "{0} must start with '{1}'", true)
}, func(ut ut.Translator, fe validator.FieldError) string {
	t, _ := ut.T("startswith", fe.Field(), fe.Param())
	return t
})

en_translations.RegisterDefaultTranslations(v, trans)
```
- [gin examples about validator.v9 Translations & Custom Errors](https://github.com/gin-gonic/gin/issues/2167)
- 위에서 등록한 custom translation은 `startswith` 태그에 대한 것이다. 해당 태그에 대한 기본 에러 메시지 translation이 없어 직접 작성했다.
  - [strings validator tag](https://github.com/go-playground/validator?tab=readme-ov-file#strings)에 보면 `startswith`에 대한 내용을 확인할 수 있다.


<br>

이후 HTTP Handler에서는 `ValidationErrors` 타입의 값에 담긴 `FieldError` 타입의 값들에 대해 `Translate` 메서드를 호출해 주면 된다. 위에서 생성한 translator를 이용한다.
```go
import (
	"github.com/gin-gonic/gin"
	"github.com/go-playground/validator/v10"
)

type AddProjectRequest struct {
	Name    string `json:"name" binding:"required,min=1,max=3"`
	Sources []int  `json:"source_ids" binding:"required,min=1"`
	Classes []int  `json:"class_ids" binding:"required,min=1"`
}

func (h *Handler) AddProject(c *gin.Context) {
	var req AddProjectRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		var ve validator.ValidationErrors
		switch {
		case errors.As(err, &ve):
			fieldErrors := make(map[string]string)
			for _, fe := range ve {
				fieldErrors[fe.Field()] = e.Translate(getValidatorTranslator()) // translator
			}
			c.AbortWithStatusJSON(http.StatusBadRequest, exception.InvalidRequestBodyFieldsException(fieldErrors))
			return
		default:
			c.AbortWithStatusJSON(http.StatusBadRequest, exception.InvalidRequestBodyException(err.Error()))
			return
		}
	}
	
	// 생략
}	
```
- 위에서 만든 translator를 가져 오는 `getValidatorTranslator` 함수를 구현했다.



잘못된 요청을 보냈을 때, 어떤 필드 검증이 실패했는지 확인할 수 있다.
```json
{
    "message": "invalid fields in request body",
    "data": {
        "Name": "Name is a required field.",
        "Classes": "Classes must contain at least 1 item.",
        "Sources": "Sources must contain at least 1 item."
    }
}
```

<br>

~~이제 코드를 정리하자~~



<br>

# 결론

사용자에게 친절한 정보를 전달하는 것은 매우 중요하다. 이 코드를 직접 구현한 개발자 입장에서야 읽기 편한 에러 메시지라고 해도, 받아 보는 사람 입장에서는 `이게 뭐야` 할 수 있다. 친절한 개발자가 되도록 노력하자.













