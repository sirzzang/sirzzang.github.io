---
title:  "[JavaScript] 불변성-2"
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

## 2. 활용



### 함수



 `person`을 인자로 받고 그 `person`의 `name`을 lee로 변경하는 함수 `fn`을 만들어 보자. 

 ```javascript
function fn(person){
    person.name = 'lee'; // 인자로 받은 데이터의 값을 직접 바꾼다.
}

var o1 = {name: 'kim'};
fn(o1);
 ```

 `o1`에 `{name: 'kim'}` 객체를 할당하고, 이를 `fn`에 인자로 넘긴다. 그러면 해당 함수는 내부적으로 다음과 같이 작동한다.

```javascript
var person = o1;
person.name = 'lee';
```

<br>

 `o1`의 값을 콘솔에 출력해 보자. 함수가 원본의 값을 변경한다.

```javascript
console.log(o1); // { name: 'lee' }
```

  의도한 효과라면 상관없지만, 의도하지 않았을 때는 문제가 된다.

<br>

 이제 함수 `fn`에 전달되는 데이터를 immutable하도록 수정해 보자. 값을 직접 다루지 않고, 원본을 복제한 뒤 `return`을 통해 반환하는 방식을 사용한다.

```javascript
function fn(person){
    person = Object.assign({}, person);
    person.name = 'lee';
    return person;
}
var o1 = {name: 'kim'};
var o2 = fn(o1);
console.log(o1, o2); // { name: 'kim' } { name: 'lee' }
```

 `fn` 함수에 파라미터로 전달된 원본 데이터 `o1`이 바뀌지 않았고, `fn`이 `o1`을 받아 복제본을 바꾼 뒤 반환한 객체가 `o2`에 할당되었음을 알 수 있다.

 애초에 함수에서 반환하지 않고, 복제한 객체를 인자로 넘겨도 결과는 같다.

 ```javascript
function fn(person){
    person.name = 'lee';
}
var o1 = {name: 'kim'};
var o2 = Object.assign({}, o1);
fn(o2);
console.log(o1, o2); // { name: 'kim' } { name: 'lee' }
 ```

<br>

### 배열



 자바스크립트에서 배열의 immutability를 유지하며 데이터를 삽입하고 싶을 때는 `concat` 메소드를 사용한다.

* 배열의 `push` 메소드는 원본 배열 데이터 자체를 바꾼다.

```javascript
var score = [1, 2, 3];
score.push(4);
console.log(score); // [1, 2, 3, 4]
```

* 반면 `concat`은 원본 데이터를 복제한 뒤 push한 결과를 반환한다.

```javascript
var score = [1, 2, 3];
var score2 = score.concat(4);
console.log(score, score2); // [1, 2, 3] [1, 2, 3,4]
```

<br>

> *참고* : 어떤 것이 더 좋을까?
>
>  답은 없다. 다음과 같이 1억 개의 변수들이 `score`를 참조하고 있는 상황을 가정해 보자.
>
> ```javascript
> var score = [1, 2, 3];
> var a = score;
> var b = score;
> // ...
> ```
>
>  이 상태에서 `push`를 통해 4를 삽입하면, 참조하고 있는 모든 변수들이 동시에 업데이트된다. 의도했다면, 폭발적인 효과이다. 데이터를 최소한으로 유지하면서도 동시에 바꿀 수 있다. 복제를 사용하지 않아도 되기 때문에 훨씬 빠르다(=성능이 좋다). 그러나 의도한 것이 아니라면, 1억 개 변수의 이름을 사용하고 있는 쪽에서는 재난이다. 이 때는 `concat`을 사용해서 4를 삽입해야 한다.

<br>

## 3. 불변 객체 만들기



 `Object.freeze`를 통해 불변 객체를 만들 수 있다. 객체의 property를 얼리는 방법으로, 없던 property를 추가하거나  property의 값을 바꾸는 것이 허용되지 않는다. 한 번 얼린 객체를 해동하는 방법은 없다. `freeze`를 풀고 싶다면 복제해야 한다. 

```javascript
var o1 = {name: 'kim', score=[1, 2]};
/*
o1.name = 'lee'; // 원본 데이터를 변경한다.
console.log(o1); // {name: 'lee', score=[1, 2]}
*/
Object.freeze(o1); // 원본 데이터 o1을 immutable하게 얼린다.
o1.name = 'lee'; // 원본 데이터는 변경되지 않는다.
console.log(o1); // {name: 'kim', score=[1, 2]};
```

<br>

 다만, 다음과 같이 객체가 중첩되어 있다면 문제가 된다. 

```javascript
var o1 = {name: 'kim', score:[1, 2]};
Object.freeze(o1);
o1.name = 'lee'; // X
o1.city = 'seoul'; // X
o1.score.push(3); // O
console.log(o1); // { name: 'kim', score=[1, 2, 3] }
```

 `o1` 안에 있는 `score`가 참조하는 객체는 **다른 곳에 저장되어 있고**, `o1`의 `score` property에는 그 reference만 저장되어 있다. 따라서, `o1` 객체를 얼렸음에도 불구하고, `o1.score.push`로 인해 `o1.score`가 변하게 된다.

 위와 같은 경우에 `score`가 변하지 않게 하려면, 중첩된 객체까지 모두 얼려야 한다. 그러면 아래와 같이 에러가 발생한다. 

```javascript
var o1 = {name: 'kim', score:[1, 2]};
Object.freeze(o1);
Object.freeze(o1.score);
o1.name = 'lee'; // X
o1.city = 'seoul'; // X
o1.score.push(3); // TypeError: Cannot add property 2, object is not extensible
console.log(o1); 
```

<br>

## 4. const vs. Object.freeze

<br>

![immutability]({{site.url}}/assets/images/js-immutable-19.png){: .align-center}

* `const`: 변수 이름이 가리키는 것을 다른 것으로 바꾸지 못하게 한다.

  > *참고* : `const`를 바꾸려고 할 때 생기는 오류
  >
  >  TypeError: Assignment to constant variable.

* `freeze`: 객체 property를 바꿀 수 없게 한다.

