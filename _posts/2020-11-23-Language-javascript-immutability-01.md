---
title:  "[JavaScript] 불변성"
excerpt: "자바스크립트에서의 데이터 불변성(immutability)에 대해 알아보자."
toc: true
toc_sticky: true
categories:
  - Language
header:
  teaser: /assets/images/blog-Dev.jpg
tags:
  - 자바스크립트
  - JavaScript
  - 불변성
  - immutability
use_math: true
---

<sup>참고: 생활코딩 [JavaScript Immutability](https://www.youtube.com/watch?v=iJcSFzR9s8Y&list=PLuHgQVnccGMBxNK38TqfBWk-QpEI7UkY8) 강의</sup>

<br>

# *JavaScript의 Immutability*

 *mutable*이란 단어 자체가 갖는 뜻(*변화 가능한*)처럼, **mutability**란 **변화 가능함**을 의미한다. **정보 원본이 변경될 수 있음**을 의미한다.  *immutable*은 *변화 가능하지 않은* 이란 뜻이다. 따라서 **immutability**란, **정보 원본이 변경될 수 없음**을 의미한다. 

<br>

## 0. 원본이란?

 어떠한 세계든, 정보의 세계에서 핵심을 이루는 것은 다음의 네 가지 작업이다.

* Create
* Read
* Update
* Delete

<br>

 이러한 네 가지 작업들 중 가장 중요한 것은 생성(**C**reate)과 읽기(**R**ead)이다. 따라서 모든 정보는 그것이 존재하고 있다면, 생성이라는 수단과 읽기라는 목적을 갖는다. 이것을 다른 말로 **원본**이라고 한다. 

 이런 점에서 어떠한 정보 시스템을 만나든 가장 먼저 확인해야 할 것은, `이 분야에서 생성과 읽기는 어떠한 것인가`이다. 이것을 이해해야 해당 분야 정보 시스템의 핵심을 알 수 있다. 생성과 읽기를 이해한 후, 수정과 삭제를 이해해야 한다. 수정과 삭제가 자유로울 때 발생하는 여러 문제점을 해결하기 위해 **불변함**(*Immutability*)에 대한 요구가 점차 높아지고 있다. 원본에 가해지는 무질서한 변화를 막을 수 있다면 사고를 막을 수 있다.

> *참고* : mutability는 안 좋은 것인가?
>
>  오해하지 말자. 가변성이 나쁘다는 의미가 아니다. 가변은 디지털의 특권이기도 하다. 다만, 어플리케이션에서 변할 필요가 없는 부분을 확실하게 잡아 놓는다면, 훨씬 더 안심할 수 있을 것이다.
>
>  mutability와 immutability를 유용하게 활용하여야 좋은 어플리케이션을 설계할 수 있다.

<br>

## 1. Immutability



 불변함을 적용할 수 있는 대상은 크게 두 가지이다. 첫째, 값의 **이름**, 둘째, 값 **자체**이다.

![immutable]({{site.url}}/assets/images/js-immutable-1.png){: .align-center}

<center><sup>그림 출처: 생활코딩 JavaScript Immutability 2강</sup></center>

<br>

### 이름

 `const`를 통해 변수를 선언하면, 변수의 값이 바뀌었을 때 아래와 같이 `TypeError`가 발생한다. 

![immutable-2]({{site.url}}/assets/images/js-immutable-2.png){: .align-center}

 변수는 변수의 이름이 가리키는 값이 계속해서 다른 값으로 바뀔 수 있다. 그러나 상수 변수(`const`)는 한 번 어떤 값을 가리키게 되면, 상수 변수가 가리키는 값을 변경하는 것이 금지된다. 따라서 이것을 시도할 때 위와 같은 에러가 발생하며 프로그램이 종료된다. 이를 통해, **부주의하게 값을 바꾸려는 시도**를 할 수 없고, 그 시도를 했을 때 **문제가 되는 행위를 했음**을 파악할 수 있다. 

<br>

### 값

 이제 값을 불변하게 유지하는 방법을 살펴 보자. 이를 위해  JavaScript가 어떤 값을 가리킬 때 어떻게 값을 가리키는지 먼저 이해해야 한다. 

<br>

**변수의 할당 방식**

 JavaScript에는 여러 데이터 타입이 존재한다. 이는 원시 데이터 타입(*Primitive Data Type*)과 객체(*Object*)이다.

<br>

1. 원시 데이터 타입

 더 이상 쪼갤 수 없는 최소한의 데이터 타입이라고 이해하자. 다음과 같은 것들이 있다.

* Number
* String
* Boolean
* Null
* Undefined
* Symbol (ES6~)

<br>

2. Object

 포괄적으로 **객체**라고 부르는 것들이다. 원자적인 데이터 타입과는 *달리*, 복합적인 특성을 갖는, 연관되어 있는 정보를 정리정돈할 때 사용한다는 특성을 갖는다고 이해하자. 

* Object
* Array: 객체에서 순서대로 정보를 정리한다는 기능이 추가된 자료형
* Function: JavaScript에서는 함수도 값으로 사용될 수 있는 객체

<br>

 따라서 JavaScript에서는 변수가 어떤 값을 가리킬 때, 그 값이 **원시 데이터 타입이냐, 객체냐**에 따라 동작 방식이 완전히 달라진다.

<br>

**초기 값의 비교**



 메모리에 어떻게 값이 저장되는지 과정을 살펴 보자.

```javascript
var p1 = 1;
```

 위와 같이 `p1`이라는 변수를 선언 후, 이에 `1`이라는 값을 할당하면, 컴퓨터 내부적으로 다음과 같이 할당이 이루어지게 된다.

![immutable-3]({{site.url}}/assets/images/js-immutable-3.png){: .align-center}

<br>

 이 상태에서 `p2`라는 변수에 `1`이라는 값을 할당하자. 

```javascript
var p2 = 1;
```

 이미 `1`이라는 값이 존재하므로, 아래와 같이 `p2`도 이미 있는 값을 가리키게 된다. *(또 다른 `1`이라는 값을 생성할 때보다 메모리를 ~~흥청망청~~ 쓰지 않게 된다고…)*

![immutable-4]({{site.url}}/assets/images/js-immutable-4.png){: .align-center}

<br>

 이 상태에서 `p1`과 `p2`는 같은 값을 가리킨다. 동등비교 연산자(같은 값일 때만 참)를 통해 확인해 보자. 

```javascript
console.log(p1 === p2); // true
```

 <br>

 여기서 메모리 상에 존재하는 `1`은 원시 데이터 타입에 속한다. 문자도 그렇고, 불리언 값 등 원시 데이터 타입에 속하는 값들이 모두 그렇다.

 그렇다면 조금 더 복합적인 데이터 타입인 객체의 경우 어떻게 달라질지 확인해 보자.

<br>

 `name`이라는 property의 값이 `kim`인 객체를 생성하자. 메모리 상 어딘가에 객체에 대한 정보가 저장된다. 그리고 `o1`이라는 변수가 이 객체를 가리키도록 하자.

```javascript
var o1 = {name:'kim'};
```

![immutable-5]({{site.url}}/assets/images/js-immutable-5.png){: .align-center}

<br>

 이제 똑같은 객체를 만들고, `o2`라는 변수에 할당하자. 

```javascript
var o2 = {name: 'kim'}
```

 이전에 원시 데이터 타입의 경우에는 값이 같으면 같은 곳을 가리킨다고 했으나, `Object`의 경우는 그렇지 않다. `o2`는 별도의 데이터를 새로 생성하고, 그 새로운 값을 가리킨다. 

![immutable-6]({{site.url}}/assets/images/js-immutable-6.png){: .align-center}

동등 비교 연산자를 통해 비교할 경우, `false`가 나온다. 각각이 각자의 데이터라는 의미이다.

```javascript
console.log(o1 === o2); // false
```

<br>

 이것이 의미하는 바가 무엇일까? 원시 데이터 타입의 경우, 더 이상 쪼갤 수가 없다. 언제나 같은 값을 의미한다. `1`을 `7`이라고 할 수는 없다. 그래서 이렇게 더 쪼갤 수 없는 데이터 타입의 경우, **불변**한 데이터 타입이라고 한다.  

 그러나 객체의 경우는 객체 안에 여러 property가 있고, 그 property가 가리킬 수 있는 값이 바뀔 수 있다. 따라서 각 객체를 별도로 생성해서 따로 보관하는 특성이 있다~~(*고 이고잉님도 추정한다*)~~. 어쨌든, *객체의 경우* 값이 바뀔 수 있는 **가변성을 갖고 있기 때문**에, 같은 값을 할당하더라도 각자 다른 메모리에 있는 값을 가리킨다고 이해하자.

> *참고*
>
>  위의 경우에서, `o1.name`과 `o2.name`이 같은지 비교하면 같다고 나온다. 아마도 `o1.name`의 값과 `o2.name`의 값이 같은 문자열이고, 문자열은 원시 데이터 타입이라 같은 주소에 있기 때문일 듯?
>
> ```javascript
> console.log(o1.name === o2.name); // true
> ```

<br>

**객체의 가변성**

 그렇다면 원시 데이터 타입과 객체의 경우, 값을 바꾸려 할 때 어떤 차이가 있는지 알아 보자.

<br>

 `p3`라는 변수를 `p1`에 할당하자. `p1`이 가리키는 값은 원시 데이터 타입이고, 이 값은 **바뀔 수 없다**. 따라서 컴퓨터의 메모리에서는 다음과 같이 `p3`가 기존에 존재하는 `1`을 가리키도록 한다. 

```javascript
var p3 = p1;
```

![immutable-7]({{site.url}}/assets/images/js-immutable-7.png){: .align-center}

<br>

 이제 `p3`의 값을 2로 바꿔 보자.

```javascript
var p3 = 2;
```

 이 상태에서는 메모리 상에 `2`라는 값이 존재하지 않는다. 따라서 메모리 상 다른 어딘가에 `2`라는 값을 만들고, `p3`는 이제 새로 만들어진 `2`를 가리키게 된다.

![immutable-8]({{site.url}}/assets/images/js-immutable-8.png){: .align-center}

 <br>

 **원시 데이터 타입**의 경우, 생성하는 시점에 값이 같을 때는 같은 값을 가리키다가, 값이 **달라졌을 때에야** 다른 값을 가리키게 된다.  반대로 **객체**는, 생성하는 시점에서 값이 같다고 하더라도 **별도의 값을 만들어서** 그 값들을 참조한다.

 그래서 원시 데이터 타입은 필요할 때까지는 새로 값을 만들지 않는다. 그러나 객체는 생성할 때마다 새로운 값을 만든다.

<br>

 여기서 객체는 원시 데이터 타입과 달리 **값 자체를 property를 통해 바꿀 수 있다**는 특성이 있다.

  `o3` 변수가 `o1` 값을 가리키도록 해 보자.

```javascript
var o3 = o1;
```

 `o3`과 `o1`은 같은 값을 가리킨다.

![immutable-9]({{site.url}}/assets/images/js-immutable-9.png){: .align-center}



<br> 이제 `o3`의 `name` 값을 `lee`로 바꿔 보자.

```javascript
o3.name = 'lee'; // o3의 name의 값을 바꾼다.
```

 그러면 `o3`가 가리키는 값이 그림에서처럼 바뀐다. 

![immutable-10]({{site.url}}/assets/images/js-immutable-10.png){: .align-center}

 그런데 이 때, `o1`이라는 변수가 가리키는 값도 바뀐다. `o3`가 바뀌니 `o1`이 가리키는 데이터도 바뀐다. 의도한 것이라면 편리하지만, **의도하지 않았다면** 문제가 생길 수 있다. 

<br>

**객체의 복사**

 따라서 원본 데이터를 건들지 않고, `o3`의 내용만 수정하고 싶다는 생각이 생긴다.`Object.assign`을 통해 객체를 `immutable`하게 다룰 수 있다.

<br>

 이전의 상태에서 다시 시작한다.

```javascript
var o1 = {name:'kim'};
var o2 = o1;
```

![immutable-11]({{site.url}}/assets/images/js-immutable-11.png){: .align-center}

<br>

  `o2`의 값을 수정할 때 `o1`이 가리키는 값이 바뀌는 문제를 방지하기 위해, `o1`이 갖는 값을 복사하고, 그 복사된 값을 수정하여 `o2`가 갖도록 한다. 

```javascript
var o1 = {name:'kim'};
var o2 = Object.assign({}, o1);
console.log(o1 === o2); // false
```

 먼저, `Object.assign`을 사용한다. 빈 객체와 뒤에 나오는 객체들을 병합해서 하나의 객체로 만들어서 반환한다. 메모리 상에 `o1`과 똑같은 객체가 만들어지고, `o2`가 가리키는 값은 새롭게 만들어진 *그* 객체이다. 

![immutable-12]({{site.url}}/assets/images/js-immutable-12.png){: .align-center}

 동등비교 연산자를 통해 `o1`과 `o2`가 같은지 확인해 보면, 새롭게 만들어진 객체이므로 다르다.

<br>

```javascript
o2.name = 'lee';
console.log(o1, o2, o1 === o2); // {name: 'kim'} {name: 'lee'} false
```

 이제 `o2`의 `name`을 바꿔 보자. `o2`가 가리키는 값만이 변경되고, 원본인 `o1`이 가리키는 값은 변경되지 않는다. 이를 통해 원본 데이터에 대해 **불변함**을 유지할 수 있고, 동시에 복제본의 변경을 통해 **가변성**을 달성할 수 있다.

![immutable-13]({{site.url}}/assets/images/js-immutable-13.png){: .align-center}

<br>

**중첩된 객체의 복사**

 중첩된(*nested*) 객체란, 객체를 구성하고 있는 property의 값 중 하나가 또 객체인 객체를 의미한다. 

<br>

 아래와 같이 중첩된 객체를 만들고 `o1`에 할당하자.

```javascript
var o1 = {name: 'kim', score: [1, 2]};
```

 이 때, `score`의 값인 `[1, 2]`라는 배열은 어떤 식으로 메모리에 저장될까?

![immutable-14]({{site.url}}/assets/images/js-immutable-14.png){: .align-center}

 원시 데이터 타입인 `String`은 그대로 저장되지만, `score`는 별도의 공간에 독립적으로 저장되고, `score`의 값은 그 배열의 **위치**를 저장한다. **reference**를 저장하고 있다고 한다.

<br>

 자 이제, 위와 같이 불변성을 위치하면서 복사하기 위해 `o2` 객체를 만들면서, `o1`에서 복제해서 사용하고 싶다. 위에서 했던 것과 같이 다음과 같이 코드를 작성한다.

```javascript
var o1 = {name: 'kim', score: [1, 2]};
var o2 = Object.assign({}, o1);
console.log(o1 === o2); // o1과 o2는 다른 값을 가리킨다.
console.log(o1.score === o2.score); // o1과 o2의 score는 같은 값을 가리킨다.
```

 이 때 컴퓨터 내부적으로 메모리에 어떻게 값이 할당되는지를 보자. 

![immutable-15]({{site.url}}/assets/images/js-immutable-15.png){: .align-center}

 `Object.assign`을 통해 복제하면, 그 객체의 property들만 복사한다. 그런데, 그 property 중 value가 `Object`형인 경우, 그 값이 아니라 그 **위치**(*reference*)만을 복제한다. 

<br>

 이 상태에서 배열의 내장함수 `push`를 이용해 `score`에 3이라는 값을 추가해 보자.

```javascript
o2.score.push(3);
```

![immutable-16]({{site.url}}/assets/images/js-immutable-16.png){: .align-center}

 `o2`의 입장에서는 `o2`의 `score`의 값을 잘 수정한다. 그런데, 그 `score`가 가리키는 게 `[1, 2]`라는 값이 아니라, 그 배열의 주소이기 때문에, 그 주소에 있는 값이 바뀌어 버린다. 즉, `o1`의 `score`가 가리키고 있는 배열도 바뀌어서, `o1`의 값도 바뀐다는 것이다.

<br> `o1`의 입장에서 값이 바뀌지 않도록 하려면, 어떻게 해야 할까? property의 값이 객체이고, 그 값을 수정할 때 원본에 영향이 가지 않도록 하려면, 그 객체까지도 복제해야 한다.

 위와 같이 배열인 경우에는, `push`가 아니라 `concat`이라는 배열 내장함수를 사용하면 된다. `concat`은 애초에 새로운 배열을 만들어 반환하기 때문에 더 이상 같은 값을 가리키지 않게 된다.

```javascript
o2.score = o2.score.concat(); // o2.score에 o2.score가 가리키는 값을 concat하여 할당한다.
console.log(o1.score === o2.score); // false: 이제 o1.score와 o2.score는 같은 값을 가리키지 않는다.
```

![immutable-17]({{site.url}}/assets/images/js-immutable-17.png){: .align-center}

<br>

> *참고* : 배열의 복제
>
>  배열의 내장함수 `push`와 `concat`은 둘 다 같은 기능을 하지만, `push`는 원본을 바꾸고, `concat`은 원본을 복제하고, 거기에 인자로 들어온 값을 추가한다. 인자로 값을 주지 않을 경우 복제만 한다. 배열을 복제한다.
>
>  특별히 배열의 경우는 `Object.assign`을 쓰지 않고 복제한다. 일단 지금은 해당 함수를 써서 배열을 복제했을 때 배열이 갖고 있는 특수한 기능이 사라진다고 이해해 두자. 배열을 복제할 때는 `concat`, `slice`, `array.from()` 등의 함수를 사용해야 한다.

<br>

 이제, 위와 같은 상태에서 `o2.score`에 `push`를 하면 `o1`이 가리키는 `score`의 배열은 바뀌지 않는다. 원본에 대한 불변성을 유지할 수 있게 된다.

```javascript
o2.score.push(3); // o2.score가 가리키는 값 원본을 변경한다. 
// 그러나 이제 o1의 score가 가리키는 값과 다른 배열이기 때문에 괜찮다.
```

![immutable-18]({{site.url}}/assets/images/js-immutable-18.png){: .align-center}