---
title:  "[Go] Go 언어 메모리 패딩"
excerpt: Memory Padding을 생각하지 않고 구조체를 설계할 때 마주칠 수 있는 문제
categories:
  - Dev
toc: true
header:
  teaser: /assets/images/blog-Dev.jpg
tags:
  - go
  - memory
  - memory padding
  - structure alignment
---



회사에서 Recording 서비스를 개발하던 중, 파일 구조를 변경하다 메모리 패딩을 고려하지 못해 겪었던 상황을 기록하고자 한다.

<br>

# 문제

Recording 서비스가 저장하는 파일 중 일부 헤더 속성 크기를 1 바이트에서 4 바이트로 변경했다. 파일 구조 상 해당 헤더는 64 바이트의 크기를 갖는 것으로 설계되었고, 속성 크기를 변경할 때는 Reserve되어 있던 속성의 크기를 변경했다.

- 기존 구조체

   ```go
   type MHeader struct {
   	A         uint8
   	Reserved1 [3]uint8 // 제외될 속성
   	B         [36]uint8
   	C         uint8
   	D         uint8
   	E         uint8
   	F         uint8
   	G         int32
   	H         int32
   	I         int32
   	Reserved2 [8]uint8
   }
   
   const MHeaderSize = unsafe.Sizeof(MHeader{}) // 64
   ```

- 변경할 구조체

  ```go
  type MHeader struct {
  	A         uint8
  	B         [36]uint8
  	C         uint8
  	D         uint8
  	E         uint32 // 변경 속성: uint8 -> uint32
  	F         uint8
  	G         int32
  	H         int32
  	I         int32
  	Reserved2 [8]uint8
  }
  
  const MHeaderSize = unsafe.Sizeof(MHeader{}) // 68
  ```

<br>



구조체 크기의 속성을 손으로 계산해 보면,

- 1(`uint8`) + 36(`[3]uint8`) + 1(`[36]uint8`) + 1(`uint8`) + 4(`uint32`) + 1(`uint8`) + 4(`int32`) + 4(`int32`) + 4(`int32`) + 8(`[8]uint8`) = 64 바이트가 되어야 할 것 같은데, 
- 실제 크기는 68바이트이다. 

해당 헤더의 크기가 64 바이트가 되어야 한다고 설계해 두었기 때문에 구조체 사이즈가 달라지면, 실제 쓰이는 파일이 설계와 달라질 수 있기 때문에 문제가 되는 상황이었다.



<br>



# 원인

이러한 문제는 컴파일러에서 메모리 패딩을 집어 넣기 때문에 발생한다. C 언어에서와 같은 이유로, Go 컴파일러 역시 구조체의 메모리 정렬 제한을 만족시키기 위해 패딩을 집어 넣는 것이다.

 정렬 제한 원칙은 다음과 같다.

- 1바이트 정렬 객체는 어떤 메모리 주소에도 올 수 있다.
- 2바이트 정렬 객체는 짝수인 주소에만 올 수 있다. 즉, 16진수 주소 끝이 0, 2, 4, 8, A, C, E여야 한다.
- 4바이트 정렬 객체는 4의 배수가 되는 주소에만 올 수 있다. 즉, 16진수 주소 끝이 0, 4, 8, C여야 한다.
- 16바이트 정렬 객체는 16의 배수가 되는 주소에만 올 수 있다. 즉, 16진수 주소 끝이 0이어야 한다.

이 원칙에 따라, 변경한 구조체의 크기는 다음과 같은 원리로 계산되는 것이다.

```go
type MHeader struct {
	A         uint8 // 1 -> 1
	B         [36]uint8 // 36 -> 37, 1바이트 정렬 객체의 배열이기 때문에 그대로 정렬됨
	C         uint8 // 1 -> 38
	D         uint8 // 1 -> 39
	// padding // 1 -> 40
	E         uint32 // 4 -> 44, 4의 배수로 끝나는 주소에 정렬되도록 해야 함
	F         uint8 // 1 -> 45,
	// padding // 3 -> 48 
	G         int32 // 4 -> 52, 4의 배수로 끝나는 주소에 정렬되도록 해야 함 
	H         int32 // 4 -> 56
	I         int32 // 4 -> 60
	Reserved2 [8]uint8 // 8 -> 68
}

const MHeaderSize = unsafe.Sizeof(MHeader{}) // 68
```



<br>

# 해결



간단하다. 패딩이 들어감을 고려해, 정렬 제한 원칙을 만족할 수 있도록 구조체 속성의 순서를 바꿔 주면 된다.

```go
type MHeader struct {
	A         uint8 // 1 -> 1
	C         uint8 // 1 -> 2
	D         uint8 // 1 -> 3
	F         uint8 // 1 -> 4
	B         [36]uint8 // 36 -> 40
	E         uint32 // 4 -> 44
	G         int32 // 4 -> 48
	H         int32 // 4 -> 52
	I         int32 // 4 -> 56
	Reserved2 [8]uint8 // 8 -> 64
}

const MHeaderSize = unsafe.Sizeof(MHeader{}) // 64
```



<br>

# 결론

해결은 간단했지만, 아래와 같은 점을 배울 수 있었다.

- 컴퓨팅 자원 빵빵하다고, 1바이트 차이 아무 것도 아니라고 구조체 대충 설계하지 말고, 패딩 데이터 신경 써서 설계하는 습관을 들이자.
- 파일 설계할 때 Reserved 바이트를 남겨두는 것은 매우 중요하다. 1바이트 아낀다고 꽉꽉 눌러 담아서 설계하다간 이런 상황에 유연하게 대처하지 못한다.





