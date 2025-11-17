---
title:  "[JPA] 양방향 연관관계 엔티티 순환 참조 문제"
excerpt: JPA를 이용해 양방향 연관관계를 설정한 엔티티를 JSON 응답에 반환하는 경우 발생할 수 있는 문제
categories:
  - Dev
toc: true
header:
  teaser: /assets/images/blog-Dev.jpg
tags:
  - Java
  - Spring
  - JPA
  - 일대다
  - 양방향
  - infinite recursion
  - stack overflow
  - jackson
---



 JPA와 Spring을 이용해 프로젝트 개발을 진행하다, 양방향 참조 관계를 설정한 엔티티 간 순환 참조 문제가 나타나며 서버 오류가 발생했다. 



<br>

# 구현

 문제가 발생하기 전, 구현된 내용은 아래와 같다.



## 엔티티 설계

![jpa-bidirectional-objects]({{site.url}}/assets/images/jpa-bidirectional-objects.png){: .align-center}

 사용자(`User`)와 반려동물(`Pet`) 엔티티는 일대다 관계를 갖는다. 두 엔티티에는 각자 서로를 참조하는 필드가 존재한다. 서비스 요구사항 명세 상, 사용자 반려동물 목록 조회 및 반려동물의 사용자 조회가 필요했고, 이를 구현하고자 양방향 참조가 필요하다고 생각했기 때문이다.

 각 엔티티 코드는 다음과 같다.

- `User.java`

```java
@Entity
@NoArgsConstructor
@AllArgsConstructor
@Getter
@Builder
@Table(name = "users")
public class User {

    @Id @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long userId;
    private String name;
  
    ...

    // 회원별 펫
    @OneToMany(fetch = FetchType.LAZY, mappedBy = "user")
    private List<Pet> pets = new ArrayList<>();

    // 사용자 펫 등록 편의 메서드
    public void addPet(Pet pet) {
        pets.add(pet);
        pet.setUser(this);
    }
}
```

- `Pet.java`

```java
@Entity
@NoArgsConstructor
@AllArgsConstructor
@Getter
@Builder
public class Pet {

    @Id @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long petId;
 		private String name;

    // 사용자
    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "user_id")
    private User user;

		...    

    // 사용자에게 펫 설정
    public void setUser(User user) {
        this.user = user;
    }

}
```



## 서비스 코드

 사용자의 반려동물을 등록하는 서비스 관련 코드이다. 사용자의 반려동물을 등록한 후, 등록된 펫의 정보를 `CreatePetResponseDto`에 담아 컨트롤러로 돌려 보낸다.

- `CreatePetResponseDto.java`

```java
@Getter
@AllArgsConstructor
@Builder
public class CreatePetResponseDto {

    @NotNull
    private Long petId;

    // 유저 엔티티를 응답에 포함
    private User user;

    ...
}
```

- `PetService.java`

```java
@Service
@RequiredArgsConstructor
public class PetServiceImpl implements PetService {

    private final PetRepository petRepository;
    private final UserRepository userRepository;

    @Override
    public CreatePetResponseDto createPet(String username, CreatePetRequestDto createPetRequestDto) {
      
	      return CreatePetResponseDto.builder()
                // 생략
                .user(petEntity.getUser()) // 반려동물 엔티티에서 사용자 엔티티를 참조해 응답 DTO 객체를 생성함
                .build();
    }
  
  	..

}
```



<br>

# 문제



## 상황

 위와 같이 구현 시, 결과적으로 *~~그 유명한...~~* `StackOverflow` 에러가 발생한다. 

```java
java.lang.StackOverflowError: null
	at java.base/java.lang.ClassLoader.defineClass1(Native Method) ~[na:na]
	at java.base/java.lang.ClassLoader.defineClass(ClassLoader.java:1012) ~[na:na]
	at java.base/java.security.SecureClassLoader.defineClass(SecureClassLoader.java:150) ~[na:na]
	at java.base/jdk.internal.loader.BuiltinClassLoader.defineClass(BuiltinClassLoader.java:862) ~[na:na]
	at java.base/jdk.internal.loader.BuiltinClassLoader.findClassOnClassPathOrNull(BuiltinClassLoader.java:760) ~[na:na]
	at java.base/jdk.internal.loader.BuiltinClassLoader.loadClassOrNull(BuiltinClassLoader.java:681) ~[na:na]
	at java.base/jdk.internal.loader.BuiltinClassLoader.loadClass(BuiltinClassLoader.java:639) ~[na:na]
	at java.base/jdk.internal.loader.ClassLoaders$AppClassLoader.loadClass(ClassLoaders.java:188) ~[na:na]
	at java.base/java.lang.ClassLoader.loadClass(ClassLoader.java:520) ~[na:na]
	at com.fasterxml.jackson.databind.JsonMappingException.prependPath(JsonMappingException.java:445) ~[jackson-databind-2.13.3.jar:2.13.3]  // Json Mapping 과정에서 무언가 문제가 있다!
  ...
```



 조금 더 자세히 내려가 보면, 아래와 같은 오류 메시지를 발견할 수 있다. 뭘 모르는 상태에서 봐도 객체 간에 순환 참조 문제가 일어나고 있음을 직감할 수 있다.

![jpa-bidirectional-httpmessagenotwritable]({{site.url}}/assets/images/jpa-bidirectional-httpmessagenotwritable.png){: .align-center}







## 원인



응답 데이터 반환 시 `CreateResponseDto`를 HTTP 응답에 필요한 JSON 객체로 직렬화하지 못해 발생한 문제다. 조금 더 자세히 살펴 보자.

- 응답 반환 시 생성해야 하는 `CreateResponseDto` 객체의 필드에 `User` 엔티티가 있다
- Jackson 라이브러리의 HttpMessageConverter는 `CreateResponseDto` 객체 직렬화 과정에서 `User` 엔티티의 직렬화를 시도한다
- HttpMessageConverter는 `User` 엔티티의 `pets` 필드가 참조하는 `Pet` 엔티티의 직렬화를 시도한다
- HttpMessageConverter는 `Pet` 엔티티의 `user` 필드가 참조하는 `User` 엔티티의 직렬화를 시도한다
- HttpMessageConverter는 `User` 엔티티의 `pets` 필드가 참조하는 `Pet` 엔티티의 직렬화를 시도한다
- HttpMessageConverter는 `Pet` 엔티티의 `user` 필드가 참조하는 `User` 엔티티의 직렬화를 시도한다
- ... (무한 반복)

> 스프링 프레임워크는 HTTP 통신 과정에서의 요청 및 응답을 위한 객체의 직렬화 및 역직렬화를 위해 Jackson 라이브러리를 이용한다.



 결과적으로 양방향으로 **매핑된 도메인 객체를 응답 객체에 담아 반환하고자 하니, 엔티티 간에 서로가 서로의 필드를 계속해서 참조하며 JSON 직렬화가 되지 않아** 나타난 문제이다. 문제 해결을 위해, 원인을 계층적으로 나누어 파악해 보자.

- 도메인 엔티티가 양방향 매핑이 되어 있다. 굳이 양방향으로 매핑하지 않으면 순환 참조 문제가 나타날 일이 없다
- 도메인 엔티티를 응답 데이터에 그대로 담아 반환한다. 도메인 엔티티를 그대로 반환하지 않았다면, 응답 데이터 직렬화를 위해 도메인 엔티티를 순환해서 참조해야 하는 상황 자체가 일어나지 않았을 것이다
- 응답 반환 시 JSON 직렬화가 되지 않는다. 필드가 순환참조되는 경우에 JSON 직렬화를 할 수 있는 방법을 적용했다면, 직렬화 불가로 인한 문제가 나타나지 않았을 것이다

<br>



# 해결


 파악한 문제 원인에 따라 다음과 같이 문제를 해결할 수 있다.



## 양방향 참조 제거

 애초에 엔티티 간 참조 관계 매핑을 다시 설정해 주면 된다. 양방향 매핑이 필요하지 않은 경우라면, 다음과 같이 엔티티를 설계하여 구현하면 된다.

![jpa-bidirectional-objects-2]({{site.url}}/assets/images/jpa-bidirectional-objects-2.png){: .align-center}

 가장 근본적인 해결책이지만, 요구사항 분석을 통해 도출된 서비스 명세가 있고, 이를 바꾸기 어려운 경우라면 적용하기 어려울 수 있다.



## 응답 데이터에서 엔티티 제외



 응답 데이터에 굳이 참조되는 엔티티가 필요한 경우가 아니라면, 제외해 주면 된다. 다만, ~~과거의 나 자신이 아무런 생각 없이 개발을 진행하지 않았다면~~ 애초에 응답 시 사용자 정보가 필요할 것이라 생각한 맥락이 있을 것이기 때문에, 함부로 제외하기에는 어려움이 있을 수 있다.



### 응답 DTO 변경

 응답 데이터에 사용자 엔티티를 넣지 않으면 된다. 

- `CreatePetResponseDto.java`

```java
@Getter
@AllArgsConstructor
@Builder
public class CreatePetResponseDto {

    @NotNull
    private Long petId;

    // 유저 엔티티를 응답에서 제외
    // private User user;

    ...
}
```



### @JsonIgnore 어노테이션 이용

 응답 객체 생성 시 참조되는 엔티티(`User`)의 필드에서 참조하는 또 다른 엔티티(`Pet`)가 JSON 직렬화 시 무시되도록 `@JsonIgnore` 어노테이션을 적용한다.

> *참고*: [@JsonIgnore 어노테이션](https://fasterxml.github.io/jackson-annotations/javadoc/2.9/com/fasterxml/jackson/annotation/JsonIgnore.html)
>
> - 어노테이션이 적용된 속성이 JSON 직렬화 혹은 역직렬화 시 무시되도록 한다
> - getter, setter, 클래스 멤버 변수 등에 적용될 수 있다

- `User.java`

```java
@Entity
@NoArgsConstructor
@AllArgsConstructor
@Getter
@Builder
@Table(name = "users")
public class User {

    @Id @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long userId;
  private String name;
  ...

    // 회원별 펫
    @OneToMany(fetch = FetchType.LAZY, mappedBy = "user")
    @JsonIgnore // JSON 변환 시 순환참조 방지
    private List<Pet> pets = new ArrayList<>();

    // 사용자 펫 등록 편의 메서드
    public void addPet(Pet pet) {
        pets.add(pet);
        pet.setUser(this);
    }
}
```



## 응답 데이터에서의 엔티티 전달 방식 변경

 응답 데이터에 엔티티 자체를 전달하지 않고, 엔티티에서 필요한 데이터만 옮겨 전달하면 된다. 예컨대, 아래와 같이 반려동물의 주인이 누구인지를 알 수 있도록 사용자의 Id(`UserId`)를 응답 객체 DTO에 포함할 수 있다.

- `CreatePetResponseDto.java`

```java
@Getter
@AllArgsConstructor
public class CreatePetResponseDto {

    @NotNull
    private Long petId;

    // 사용자 엔티티 대신 사용자 ID 반환
//    private User user;
    private Long userId;

    ..
}
```



 필요한 필드만 모아서, 새로 클래스를 만들어도 된다. 서비스 구현체 변경할 부분도 많지 않고, 사용자에게 응답으로 엔티티 자체를 반환하지 않는다는 점에서도 나은 해결책이 될 수 있다.





## 응답 JSON 직렬화 단계에서의 순환 참조 방지



 `@JsonManagedReference`와 `@JsonBackReference` 어노테이션을 적용해 Jackson 라이브러리가 두 필드 모두를 직렬화하지 않도록 설정한다.

> *참고*: [@JsonManagedReference 어노테이션](https://fasterxml.github.io/jackson-annotations/javadoc/2.6/com/fasterxml/jackson/annotation/JsonManagedReference.html)과 [@JsonBackReference 어노테이션](https://fasterxml.github.io/jackson-annotations/javadoc/2.6/com/fasterxml/jackson/annotation/JsonBackReference.html)
>
> - `@JsonManagedReference`: 양방향 참조 필드의 일부임을 알리는 어노테이션. 부모 쪽에 설정하며, 직렬화는 수행되지만 역직렬화는 수행되지 않는다
> - `@JsonBackReference`: 양방향 참조 필드의 일부임을 알리는 어노테이션. 자식 쪽에 설정하며, 직렬화는 수행되지 않지만 역직렬화 수행 시 `@JsonManagedReference`가 적용된 인스턴스 값으로 설정된다

 `@OneToMany` 어노테이션이 적용된 부모 엔티티에 `@JsonManagedReference` 어노테이션을, `@ManyToOne` 어노테이션이 적용된 자식 엔티티에 `@JsonBackReference` 어노테이션을 적용한다.

- `User.java`

```java
@Entity
@NoArgsConstructor
@AllArgsConstructor
@Getter
@Builder
@Table(name = "users")
public class User {

    @Id @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long userId;
  
  ...
    
    // 회원별 펫
    @OneToMany(fetch = FetchType.LAZY, mappedBy = "user")
    @JsonManagedReference // 적용한 어노테이션
    private List<Pet> pets = new ArrayList<>();

    ...
}
```

- `Pet.java`

```java
@Entity
@NoArgsConstructor
@AllArgsConstructor
@Getter
@Builder
public class Pet {

    @Id @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long petId;
  private String name;

    // 사용자
    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "user_id")
  @JsonBackReference // 적용한 어노테이션
    private User user;

  ...

}
```



 위 어노테이션 적용 시, Jackson 라이브러리에서 양방향 참조 필드를 인식해 직렬화 시 무한 참조를 하지 않게 된다. 다만, 이 경우 엔티티가 그대로 응답에 담겨 오기 때문에, 엔티티 자체를 응답으로 반환하는 것이 맞는지, 엔티티 내 모든 필드가 응답으로 반환될 필요가 있는지 고민해 볼 필요가 있어 보인다.

 어노테이션을 사용하면서 엔티티 내 모든 필드를 응답으로 반환하지 않고자 한다면, `User` 엔티티에서 JSON 직렬화 시 무시할 속성을 찾아 보아도 될 듯하다.

<br>

# 결론

 결국 엔티티를 어떻게 설계할 것인가, 응답을 어떻게 줄 것인가를 애초부터 올바르게 설계하는 것이 가장 중요하다는 것을 다시 한 번 깨닫는다. 기존 구현과 서비스 명세를 해치지 않는 선에서 세 번째 방법을 선택해 문제를 해결하긴 했지만, 애초에 응답 데이터 설계 단계에서 왜 엔티티를 그대로 반환하고자 했는지 돌아볼 필요가 있다. 나아가 양방향 매핑 없이 로직을 짤 수 있지 않았을지도 고민해 보아야 한다.

 한편, 지금 당장은 응답 데이터 형식과 관련해 문제가 발생했지만, 비즈니스 로직을 작성하는 부분에서도 충분히 순환 참조로 인한 문제가 발생할 수 있을 것이라 보인다. 때문에 양방향 연관관계를 남발하지 말고, 설계 단계에서부터 양방향 참조의 필요성을 검토할 필요가 있다. 검토 후에도 양방향 참조가 필요해 사용하기로 결정했다면, 양방향 연관관계 편의 메서드를 작성하고, 해당 메서드 내에서 도메인 엔티티 간 순환 참조가 일어나지는 않는지 체크해야 할 것이다.
