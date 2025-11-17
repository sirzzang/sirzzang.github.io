---
title:  "[Go] Nil Slice"
excerpt: nil slice와 empty slice의 차이
categories:
  - Language
header:
  teaser: /assets/images/blog-Dev.jpg
tags:
  - Go
  - slice
  - nil
toc: true
---



<br>

Go를 공부하다 nil slice와 empty slice의 차이가 궁금해져 알아 보았다. slice가 `nil`인 것과 비어 있는 것은 엄밀히 다른 개념이지만, 관찰되는 것만 보면 비슷하기 때문에 혼동하기 쉽다.

- nil slice: 초기화하지 않은 slice
- empty slice: 초기화되었으나 길이가 0인 slice

<br>

# slice 내부 구조



 Go 언어에서 slice 내부 구현은 감춰져 있다. 그러나 reflect 패키지의 `SliceHeader` 구조체를 통해 그 내부 구현을 짐작해 볼 수 있다.

```go
type SliceHeader struct {
    Data uintptr
    Len int
    Cap int
}
```

slice는 필드가 3개인 구조체로, 24 byte의 크기를 가진다.

* `Data`: 실제 배열을 가리키는 포인터
* `Len`: 배열 요소 개수
* `Cap`: 배열 용량

즉, Go에서 slice는 아래 그림과 같이, 실제 배열을 가리키는 포인터와, 그 포인터가 참조하는 배열에 채워져 있는 요소의 개수(길이) 및 그 배열이 총 가질 수 있는 요소의 최대 개수(용량)으로 이루어진 구조체이다.

![slice-structure]({{site.url}}/assets/images/slice-structure.png){: .align-center width="400"}

## nil slice

 slice가 `nil`이라는 것은 slice 구조체가 가리키는 배열이 없음을 의미한다. 아래 그림에서와 같이 slice 타입 변수가 가리키는 slice 구조체의 `Data` 필드가 가리키는 배열이 없는 것이다.

![slice-structure-nil]({{site.url}}/assets/images/slice-structure-nil.png){: .align-center width="300"}

슬라이스 구조체가 가리키는 배열이 없다. 

- 따라서 슬라이스 구조체의 각 필드는 해당 필드 타입의 zero value로 초기화된다.
- `Data`, `Len`, `Cap` 필드 값 모두 0이 된다.

## empty slice

 slice가 empty라는 것은 slice 구조체가 가리키는 배열이 있으나, 그 배열의 길이가 0이라는 것을 의미한다. 아래 그림에서와 같이 slice 타입 변수가 가리키는 slice 구조체의 `Data` 필드가 가리키는 배열이 있으나, 그 배열이 비어 있는 것이다.

![slice-structure-empty]({{site.url}}/assets/images/slice-structure-empty.png){: .align-center width="400"}

<center><sup>길이가 0인 것을 표현할 방법이 마땅치가 않지만, 어쨌든 길이가 0!</sup></center>

<br>

# 코드로 살펴 보기

실제 코드로 nil slice와 empty slice의 차이를 확인할 수 있다.

## nil slice

선언 후 초기화하지 않은 nil slice이다.

* `nil`과 비교하면 `true`이다.
* 슬라이스 구조체가 가리키는 배열 포인터 주소 값이 0이다.

```go
package main

import (
	"fmt"
	"reflect"
	"unsafe"
)

func main() {
	var slice []int
	slicePtr := unsafe.Pointer(&slice)
	sliceHeader := (*reflect.SliceHeader)(slicePtr)
	fmt.Println(slicePtr, sliceHeader.Data) // 0x1400011e018 0
	fmt.Println(slice == nil, slice, len(slice), cap(slice)) // true [] 0 0
}
```



## empty slice



### 1. 리터럴을 이용해 초기화한 empty slice

* `nil`과 비교하면 `false`이다.
* 슬라이스 구조체가 가리키는 배열 포인터 주소 값이 0이 아니다.

```go
package main

import (
	"fmt"
	"reflect"
	"unsafe"
)

func main() {
	slice = []int{}
	fmt.Println(slicePtr, sliceHeader.Data) // 0x1400011e018 4312952808
	fmt.Println(slice == nil, slice, len(slice), cap(slice)) // false [] 0 0
}
```

### 2. make 함수를 이용해 초기화한 empty slice

* `nil`과 비교하면 `false`이다.
* 슬라이스 구조체가 가리키는 배열 포인터 주소 값이 0이 아니다.

```go
package main

import (
	"fmt"
	"reflect"
	"unsafe"
)

func main() {
	slice1 := make([]int, 0)
	slice1Ptr := unsafe.Pointer(&slice1)
	slice1Header := (*reflect.SliceHeader)(slice1Ptr)
	fmt.Println(slice1Ptr, slice1Header.Data) // 0x1400011e018 4375097320
	fmt.Println(slice1 == nil, slice1, len(slice1), cap(slice1)) // false [] 0 0
}
```



<br>



# 동작



`nil` slice와 empty slice는 가리키는 배열이 있는지 여부에서 차이가 나지만, 길이와 용량이 모두 0이기 때문에 비슷하게 동작하는 경우도 있다.

- `len()`, `cap()` 함수를 사용할 수 있다.
- `range`를 사용할 수 있다. 다만, iteration이 일어나지는 않는다.
- 길이가 0이기 때문에, 접근할 수 있는 요소가 없다. 접근하려고 할 경우, 런타임 에러가 발생한다.

```
panic: runtime error: index out of range [1] with length 0
```

* 길이가 0이기 때문에, 그 내용을 바꿀 수는 없다. 만약, append 함수를 사용한다면, 두 경우 모두 길이가 0이기 때문에 새로운 배열을 할당하고, 기존 슬라이스 값을 바꾼다.
* 슬라이싱할 수 있다. 다만, nil slice는 슬라이싱 후에도 nil slice이나, empty slice는 슬라이싱 후에도 여전히 nil slice가 아니라 empty slice이다.

## nil slice

```go
package main

import (
	"fmt"
	"reflect"
	"unsafe"
)

func main() {

	// nil slice
	var slice []int
	slicePtr := unsafe.Pointer(&slice)
	sliceHeader := (*reflect.SliceHeader)(slicePtr)
	fmt.Println(slicePtr, sliceHeader.Data) // 0x1400000c030 0
	fmt.Println(slice == nil, slice, len(slice), cap(slice)) // true [] 0 0
	// fmt.Println(slice[1]) // panic
	// slice[1] = 10 // panic
	for i, v := range slice {
		fmt.Println(i, v) // 아무 것도 출력되지 않음
	}
	fmt.Println(slice[:], slice[:] == nil) // [] true
	slice = append(slice, 1)
	fmt.Println(slice) // [1]
	fmt.Println(slicePtr, sliceHeader.Data) // 0x1400000c030 1374389616840, 슬라이스가 가리키는 배열이 바뀜

}
```

## empty slice

```go
package main

import (
	"fmt"
	"reflect"
	"unsafe"
)

func main() {

	// nil slice
	var slice []int = make([]int, 0)
	slicePtr := unsafe.Pointer(&slice)
	sliceHeader := (*reflect.SliceHeader)(slicePtr)
	fmt.Println(slicePtr, sliceHeader.Data) // 0x1400011e018 4371329000
	fmt.Println(slice == nil, slice, len(slice), cap(slice)) // false [] 0 0
	// fmt.Println(slice[1]) // panic
	// slice[1] = 10 // panic
	for i, v := range slice {
		fmt.Println(i, v) // 아무 것도 출력되지 않음
	}
	fmt.Println(slice[:], slice[:] == nil) // [] false
	slice = append(slice, 1)
	fmt.Println(slice) // [1]
	fmt.Println(slicePtr, sliceHeader.Data) // 0x1400011e018 1374390763552, 슬라이스가 가리키는 배열이 바뀜
  
}
```

<br>

## 결론

선언 후 초기화하지 않은 slice만 `nil` slice이다.

```go
var s1 []int         // nil slice
s2 := []int{}        // non-nil, empty slice
s3 := make([]int, 0) // non-nil, empty slice
```
