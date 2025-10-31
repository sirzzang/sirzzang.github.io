---
title:  "파일 저장 기능을 개발하며 고민했던 점들"
excerpt: "go의 write 관련 함수를 살펴보게 된 건에 대하여"
toc: true
categories:
  - Articles
tags:
  - go
  - file
  - write
  - systemcall
use_math: true
---



<br>

 회사에서 실시간으로 영상을 수신해 저장하는 레코딩 서버를 구현하며, 파일 쓰기 시 에러 처리를 어떻게 하는 것이 좋을지 고민한 과정을 기록하고자 한다.

![recorder-file-write]({{site.url}}/assets/images/recorder-file-write.png)

<br>

# 개요



 고민이 시작된 것은, 레코딩 서버가 그 특성상 수신한 영상의 프레임이 손실되지 않도록 저장함을 보장해야 하기 때문이었다.

- 영상 데이터는 실시간으로 계속 들어온다
- 이렇게 수신한 영상 프레임 데이터가 일부라도 쓰여지지 않는다면 나중에 영상을 재생할 수 없다(*혹은 재생은 가능하겠지만 해당 프레임은 재생 시 버려지게 될 것이다. 누락된 프레임이 고객 입장에서 매우 중요한 장면이라면...*).

 따라서 파일 쓰기 과정에서 만약 프레임 데이터 전부가 정상적으로 쓰여지지 않았다면, 이를 인지해 다음 프레임을 저장하기 전에 에러 처리를 해야 한다. 이 과정에서,

- 언어 차원에서 파일 쓰기 함수를 호출하면, 에러가 발생하지 않는 한 진짜 데이터가 다 저장되는 게 맞는지,
- 파일 쓰기 시 어떤 에러가 발생할 수 있는지,

가 궁금해졌고, 이 궁금증을 해결한 후에 파일 쓰기 에러를 처리할 수 있도록 기능을 고도화하고 싶었다.

이를 위해, 개발 시 사용하고 있는 go 언어에서 파일 쓰기를 어떻게 다루고 있는지, write 시스템 콜 함수에서 어떤 에러가 발생할 수 있는지 알아 보았다. 파일 쓰기 작업은, 궁극적으로는 file descriptor에 대한 시스템 콜이기 때문이다. 그리고 레코딩 서버에서 각 에러 상황을 어떻게 처리하는 것이 좋을지 고민한 내용을 간략하게나마 정리해보고자 한다.



<br>



# 구현



 현재 레코딩 서버에서 프레임 데이터를 파일에 쓰는 함수이다. 

```go
func (w *Writer) WriteFrame(fp io.WriterAt, timestamp int64, data *[]byte) (int, error)
```

 파일 쓰기는 `File` 타입 객체가 사용할 수 있는 `WriterAt` 메서드를 사용하도록 구현되어 있다.

```go
n, err := fp.WriteAt(frameHeaderArr, w.offset)
if err != nil {
	log.Error("%v", err)
	return bytesWritten, err
}
```

 반환 값은 바이트 수와 에러이다. 구현 내용에서 볼 수 있듯, 현재는 `WriteAt` 메서드에서 에러가 발생한 경우, 아무런 처리 없이 그대로 쓰여진 바이트 수와 에러를 반환한다.

 테스트 시 이 부분에서 에러가 발생했던 적은 없다. 그러나 이 상태라면, 만약 실제 상황에서 에러가 발생하게 된다면, 해당 부분의 프레임 데이터는 다 쓰여지지 않은 채로 다음 프레임이 기록될 것이다. 물론 추후 파일 복구 로직을 구현할 예정이지만, 복구는 다른 차원의 문제이고, 파일을 쓸 때 최대한 에러 없이 프레임 데이터를 기록할 수 있도록 해야할 것이다.



<br>

# go에서의 Write 과정 분석





## File

 Go의 `File` 타입은 open file descriptor를 가지고 있는 구조체이다.

> `File` 타입은 `WriteAt` 메서드를 구현했기 때문에, `io.WriterAt` 인터페이스 타입으로 사용될 수 있다.

```go
// File represents an open file descriptor.
type File struct {
	*file // os specific
}
```

위에서 `File` 타입은 private한 `file` 타입에 대한 포인터를 갖는다. `file` 타입은 아래와 같은 구조체이다.

- `file_unix.go` 파일에서 찾아볼 수 있다.
- 파일 이름, directory 정보 등과 함께, file descriptor인 `poll.FD` 타입의 `pfd` 속성을 가지고 있다.

```go
// file is the real representation of *File.
// The extra level of indirection ensures that no clients of os
// can overwrite this data, which could cause the finalizer
// to close the wrong file descriptor.
type file struct {
	pfd         poll.FD
	name        string
	dirinfo     *dirInfo // nil unless directory being read
	nonblock    bool     // whether we set nonblocking mode
	stdoutOrErr bool     // whether this is stdout or stderr
	appendMode  bool     // whether file is opened for appending
}
```

즉, `file` 타입에 file descriptor가 있고, `File` 타입은 `file` 타입 구조체를 갖고 있기 때문에, 사용자는 `File` 객체를 통해 file descriptor에 접근할 수 있게 된다. 주석을 통해, file descriptor에 대한 의도하지 않은 동작을 막기 위해 file descriptor를 가진 `file` 타입은 공개되지 않고, 사용자가 `File` 타입만 이용할 수 있도록 구현해 두었음을 짐작할 수 있다.

`poll` 패키지의 `FD` 타입은 file descriptor를 나타내는 다음과 같은 구조체이다. ~~각각의 필드는 리눅스 공부하며 알아서 찾아보는 것으로~~

```go
// FD is a file descriptor. The net and os packages use this type as a
// field of a larger type representing a network connection or OS file.
type FD struct {
	// Lock sysfd and serialize access to Read and Write methods.
	fdmu fdMutex

	// System file descriptor. Immutable until Close.
	Sysfd int

	// I/O poller.
	pd pollDesc

	// Writev cache.
	iovecs *[]syscall.Iovec

	// Semaphore signaled when file is closed.
	csema uint32

	// Non-zero if this file has been set to blocking mode.
	isBlocking uint32

	// Whether this is a streaming descriptor, as opposed to a
	// packet-based descriptor like a UDP socket. Immutable.
	IsStream bool

	// Whether a zero byte read indicates EOF. This is false for a
	// message based socket connection.
	ZeroReadIsEOF bool

	// Whether this is a file rather than a network socket.
	isFile bool
}
```



<br>

## (*File).WriteAt



 `File` 타입의 메서드 `WriteAt`은 인자로 주어진 `[]byte` 타입(*이하 버퍼. 써야 할 데이터이다*) 바이트 슬라이스를 파일의 `off` 위치부터 쓴다. 즉, 파일에  `off`에서부터 `len(b)` 바이트를 쓰는 함수이다.

```go
// WriteAt writes len(b) bytes to the File starting at byte offset off.
// It returns the number of bytes written and an error, if any.
// WriteAt returns a non-nil error when n != len(b).
//
// If file was opened with the O_APPEND flag, WriteAt returns an error.
func (f *File) WriteAt(b []byte, off int64) (n int, err error) {
    // 1
	if err := f.checkValid("write"); err != nil {
		return 0, err
	}
	if f.appendMode {
		return 0, errWriteAtInAppendMode
	}

	if off < 0 {
		return 0, &PathError{Op: "writeat", Path: f.name, Err: errors.New("negative offset")}
	}

    // 2
	for len(b) > 0 {
		m, e := f.pwrite(b, off)
		if e != nil {
			err = f.wrapErr("write", e)
			break
		}
		n += m
		b = b[m:]
		off += int64(m)
	}
	return
}
```

 자세한 내용은 나중에 다시 살펴 본다. 대략적으로 구현 내용을 살펴 보면 다음과 같은 점을 알 수 있다.

- 1: 주어진 파일이 쓸 수 있는 상태인지, offset이 음수는 아닌지 등 유효성 검사를 한다. 
- 2: 더 이상 써야 할 버퍼가 남아 있지 않을 때까지 반복문을 통해 파일을 쓴다.

 2의 과정에서, 실제 파일을 쓰는 것이 `File` 객체 자신의 `pwrite` 메서드를 호출함으로써 이루어지는 것을 확인할 수 있다.



<br>

## (*File).pwrite

 `(*File).pwrite` 메서드는 `File` 객체에 버퍼를 쓴다. 일단 이 메서드가 호출되었다면 `File` 객체가 파일을 쓸 수 있는 적합한 상태임을 의미한다.

```go
// pwrite writes len(b) bytes to the File starting at byte offset off.
// It returns the number of bytes written and an error, if any.
func (f *File) pwrite(b []byte, off int64) (n int, err error) {
	n, err = f.pfd.Pwrite(b, off) // 1
	runtime.KeepAlive(f) // 2
	return n, err
}
```

 구현 내용을 간략히 살펴 보면,

- 1: file descriptor에 대해 `Pwrite` 메서드를 호출한다.
- 2: `Pwrite`가 반환하기 전에 `File` 객체에 대한 finalizer가 작동하지 않도록, 해당 객체를 reachable 상태로 마킹한다.



<br>

## (*FD).Pwrite

 `(*FD).Pwrite` 메서드는 실제 pwrite system call 함수를 래핑해 놓은 함수이다. 시스템 콜까지 온 것을 보니, 실제로 write가 되는 과정이라고 보아도 될 듯하다.

```go
// Pwrite wraps the pwrite system call.
func (fd *FD) Pwrite(p []byte, off int64) (int, error) {
	// Call incref, not writeLock, because since pwrite specifies the
	// offset it is independent from other writes.
	// Similarly, using the poller doesn't make sense for pwrite.
    
    // 1
	if err := fd.incref(); err != nil {
		return 0, err
	}
	defer fd.decref()


    // 2
	var nn int
	for {
		max := len(p)
		if fd.IsStream && max-nn > maxRW {
			max = nn + maxRW
		}
		n, err := syscall.Pwrite(fd.Sysfd, p[nn:max], off+int64(nn))

		if err == syscall.EINTR { // 3
			continue
		}
		if n > 0 {
			nn += n
		}
        
		if nn == len(p) { // 4
			return nn, err
		}
        
		if err != nil { // 5
			return nn, err
		}
        
		if n == 0 { // 6
			return nn, io.ErrUnexpectedEOF
		}
	}
}
```

 구현 내용을 살펴 보자.

- 1: file descriptor에 대한 reference를 마킹한다.
- 2: Pwrite 시스템 콜 함수를 호출하며, 시스템 콜을 통해 쓴 바이트 수를 누적해 더해 나간다. 무한히 반복한다.

 시스템 콜을 통해 쓴 바이트 수와 에러를 얻어 온다. 시스템 콜을 확인해야 알겠지만, 일단 지금은 

- go 언어에서 쓰기 관련 시스템 콜을 할 때 `syscall.Pwrite`를 사용한다
- 시스템 콜에서 쓴 바이트 수와 에러를 반환한다

정도만 알아 두어도 될 듯하다.

이후 로직을 조금만 더 자세히 살펴 보자.

- 3: 시스템 콜에서 `EINTR` 에러가 발생한 경우, 에러 처리를 하지 않고 다음 루프로 넘어 간다. 
  - 다음 루프로 넘어간다는 것은 곧, 다시 Pwrite 시스템 콜 함수를 호출한다는 의미이다.
- 4: 쓴 바이트 수가 버퍼 바이트 수와 같다면, 루프를 종료하고 결과를 반환한다.
- 5: 시스템 콜에서 에러가 발생한다면, 루프를 종료하고 결과를 반환한다.
- 6: 시스템 콜에서 에러가 발생하지 않았지만, 쓴 바이트 수가 0이라면, 루프를 종료하고 결과를 반환한다.

4, 5, 6을 통해 다음과 같은 점을 확인할 수 있다.

- 시스템 콜 에러가 발생하지 않았거나 에러가 발생했더라도 `EINTR` 에러가 발생한 경우라면, 주어진 버퍼를 다 쓰는 것이 보장된다.
- 시스템 콜에서 에러가 발생했다면, 주어진 버퍼를 다 쓰지 않았더라도 go 차원에서 에러 처리된다.
- 시스템 콜에서 에러가 발생하지 않았더라도, 쓴 바이트 수가 0이면 go 차원에서 에러 처리된다.

결과적으로, 이 단계에서 에러가 발생하면, 그것은 주어진 버퍼를 다 쓰지 못했다는 의미이기 때문에, `(*File).WriteAt`을 호출한 사용자가 에러를 처리해야 함을 알 수 있다.



<br>

##  syscall.Pwrite

 내장 함수 pwrite를 호출하고, 그 결과를 반환한다. 추측해 보건대, 내장 함수 `pwrite`가 시스템 콜을 하는 함수일 것 같다.

> 반환 시 naked return을 사용했다.

```go
func Pwrite(fd int, p []byte, offset int64) (n int, err error) {
	if race.Enabled {
		race.ReleaseMerge(unsafe.Pointer(&ioSync))
	}
	n, err = pwrite(fd, p, offset)
	if race.Enabled && n > 0 {
		race.ReadRange(unsafe.Pointer(&p[0]), n)
	}
	if msanenabled && n > 0 {
		msanRead(unsafe.Pointer(&p[0]), n)
	}
	if asanenabled && n > 0 {
		asanRead(unsafe.Pointer(&p[0]), n)
	}
	return
}
```



<br>

## pwrite

 PWRITE64  시스템 콜을 한 뒤, 그 결과를 반환한다. 

```go
// THIS FILE IS GENERATED BY THE COMMAND AT THE TOP; DO NOT EDIT

func pwrite(fd int, p []byte, offset int64) (n int, err error) {
	var _p0 unsafe.Pointer
	if len(p) > 0 {
		_p0 = unsafe.Pointer(&p[0])
	} else {
		_p0 = unsafe.Pointer(&_zero)
	}
	r0, _, e1 := Syscall6(SYS_PWRITE64, uintptr(fd), uintptr(_p0), uintptr(len(p)), uintptr(offset), 0, 0)
	n = int(r0)
	if e1 != 0 {
		err = errnoErr(e1)
	}
	return
}
```



 PWRITE64 시스템 콜에 대해 더 알아 보아야 하겠지만, 구현 내용만 봤을 때 다음의 것들을 알 수 있다.

- 시스템 콜에서 쓴 바이트 수를 반환한다.
- 시스템 콜에서 반환한 `Errno`가 0이 아니라면, 에러가 있다.

 결과적으로, 시스템 콜에서 `Errno`가 세팅되어 넘어 온 경우, 이것이 `(*File).WriteAt`까지 상위로 가며 에러로서 전파되는 것이다.



<br>

# 결론

결과적으로, `(*File).WriteAt`은 `SYS_PWRITE64`라는 go의 시스템 콜 함수를 통해 커널의 PWRITE64 시스템 콜 함수를 호출한다. 

1. 내가 구현한 Writer는 파일에 쓰기 위해 `File` 객체의 `WriteAt` 메서드를 사용한다.
2. `File` 타입의 `WriterAt` 메서드는 `File` 타입의 `pwrite` 메서드를 호출한다.
3. `(*File).pwrite` 메서드는 `File` 객체에 데이터를 쓴다.
   - `File` 객체는 내부에 file descriptor인 `FD` 타입 객체를 `pfd` 속성으로서 가지고 있다. 이`pfd`의  `Pwrite` 메서드를 호출한다.
   - `pfd.Pwrite` 메서드가 반환할 때까지 `File` 객체에 대한 garbage collection이 이루어지지 않도록 `runtime.Keepalive` 메서드를 호출한다.
4. `(*FD).Pwrite` 메서드는 pwrite 시스템 콜을 wrapping하고 있는 메서드로, `syscall.Pwrite` 함수를 호출한다.
5. `syscall.Pwrite` 함수는 내장함수 `pwrite`를 호출한다.
6. `pwrite` 함수에서 실제 `SYS_PWRITE64` 시스템 콜 함수를 호출하고, 실제 쓰기 작업이 이루어진다.

 그러므로 더 정교한 에러 처리를 위해서는 PWRITE64 시스템 콜 함수에서 어떤 에러가 발생하는지, 에러 발생 시 어떻게 처리하는 것이 권장되는지 알아볼 필요가 있다.

<br>
