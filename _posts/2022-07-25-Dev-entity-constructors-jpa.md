---
title:  "[JPA] 엔티티 생성자"
excerpt: JPA 엔티티 생성자에 디폴트 생성자 롬복 어노테이션이 필요한 이유
categories:
  - Dev
toc: true
header:
  teaser: /assets/images/blog-Dev.jpg
tags:
  - Java
  - JPA
  - Lombok
  - Entity
---

 JPA 엔티티를 보면, 대부분 엔티티 클래스에 아래와 같이 디폴트 생성자와 모든 필드 값을 파라미터로 갖는 생성자 혹은 필수 필드 값을 파라미터로 갖는 생성자가 같이 있는 것을 확인할 수 있다. 갑자기 그 이유가 궁금해 져서 찾아 본다. ~~*생각을 하면서 공부를 하자.*~~

```java
@Entity
@NoArgsConstructor
@AllArgsConstructor
public class User {
  
  private Long id;
  private String name;
  private String username;
  private String password;
  
}
```

<br>

## JPA 명세



 JPA 명세는 `@Entity` 어노테이션이 붙은 **모든 영속 클래스가 접근 제어 레벨이 public 혹은 protected인 기본 생성자를 갖도록 규정하고 있다**.

> The JPA specification requires that all persistent classes have a no-arg constructor. This constructor may be public or protected. Because the compiler automatically creates a default no-arg constructor when no other constructor is defined, only classes that define constructors must also include a no-arg constructor.



 이는 JPA가 리플렉션(reflection API)을 이용해 빈 클래스를 만들고, 이 때 **디폴트 생성자를 이용하기 때문**이다. 디폴트 생성자를 이용하는 이유는, 만약 개발자가 작성한 생성자가 여러 개일 경우, JPA는 어떤 생성자를 이용해 클래스를 인스턴스화해야 할지 알지 못하기 때문이다. 결과적으로 여러 개의 생성자 중 JPA는 디폴트 생성자를 이용한 리플렉션을 통해 클래스를 로드하게 되고, 이후 필드 세터를 이용해 값을 채운다

```java
User.class.newInstance(); // new User()와 동일
```



<br>

## 코드 작성



 자바 컴파일러는 클래스에 아무 생성자도 없는 경우, 자동으로 디폴트 생성자를 만들어 준다. 그러나 개발자가 생성자 코드를 작성한 경우, 컴파일러는 디폴트 생성자를 자동으로 만들어 주지 않는다.

 따라서 위와 같이 개발자가 엔티티 클래스에 모든 필드를 인자로 받는 생성자를 작성한 경우(`@AllArgsConstructor`), JPA 명세에 따라 디폴트 생성자(`@NoArgsConstructor`)도 같이 작성해 주어야 하는 것이다. 그렇지 않으면, 런타임에 `InstantiationException` 에러가 발생하게 된다.(컴파일 타임에는 에러가 발생하지는 않는다.)

```java
Whitelabel Error Page
 This application has no explicit mapping for /error, so you are seeing this as a fallback.
 Fri Oct 04 17:01:43 IST 2019
 There was an unexpected error (type=Internal Server Error, status=500).
 No default constructor for entity: : com.eraser.userservice.User; nested exception is org.hibernate.InstantiationException: No default constructor for entity:
...
```

<br>

 특히 엔티티에 `@Data` 어노테이션을 이용할 때도 주의해야 한다. 해당 어노테이션이 붙은 클래스에는 `@RequiredArgsConstructor` 어노테이션도 붙게 되는데, 이 경우 역시 JPA 명세에 따라 `@NoArgsConstructor` 어노테이션을 같이 붙여 주어야 한다.

다만, `@Data` 혹은 `@RequiredArgsConstructor` 어노테이션을 붙인 엔티티 클래스에 `final` 필드가 없는 경우는, `@NoArgsConstructor` 어노테이션이 없는 경우에도 디폴트 생성자가 만들어 진다.

- `final` 필드가 없는 `@RequiredArgsConstructor` 어노테이션이 붙은 엔티티 클래스

  ```java
  package com.eraser.auth.userservice.domain;
  
  import lombok.RequiredArgsConstructor;
  
  import javax.persistence.Entity;
  
  @Entity
  @RequiredArgsConstructor
  public class User {
  
      private Long id;
      private String name;
      private String username;
      private String password;
  
  }
  
  ```

  ```java
  //
  // Source code Recreated from a .class file by IntelliJ IDEA
  // (powered by FernFlower decompiler)
  //
  
  package com.eraser.auth.userservice.domain;
  
  import javax.persistence.Entity;
  
  @Entity
  public class User {
      private Long id;
      private String name;
      private String username;
      private String password;
  
    	// 디폴트 생성자가 만들어짐
      public User() {
      }
  }
  ```

- `final` 필드가 없는 `@Data` 어노테이션이 붙은 엔티티 클래스

  ```java
  package com.eraser.auth.userservice.domain;
  
  import lombok.Data;
  
  import javax.persistence.Entity;
  
  @Entity
  @Data
  public class User {
  
      private Long id;
      private String name;
      private String username;
      private String password;
  
  }
  ```

  ```java
  //
  // Source code Recreated from a .class file by IntelliJ IDEA
  // (powered by FernFlower decompiler)
  //
  
  package com.eraser.auth.userservice.domain;
  
  import javax.persistence.Entity;
  
  @Entity
  public class User {
      private Long id;
      private String name;
      private String username;
      private String password;
  
      // 디폴트 생성자가 만들어짐
      public User() {
      }
  
      public Long getId() {
          return this.id;
      }
  
      public String getName() {
          return this.name;
      }
  
      public String getUsername() {
          return this.username;
      }
  
      public String getPassword() {
          return this.password;
      }
  
      public void setId(final Long id) {
          this.id = id;
      }
  
      public void setName(final String name) {
          this.name = name;
      }
  
      public void setUsername(final String username) {
          this.username = username;
      }
  
      public void setPassword(final String password) {
          this.password = password;
      }
  
      public boolean equals(final Object o) {
          if (o == this) {
              return true;
          } else if (!(o instanceof User)) {
              return false;
          } else {
              User other = (User)o;
              if (!other.canEqual(this)) {
                  return false;
              } else {
                  label59: {
                      Object this$id = this.getId();
                      Object other$id = other.getId();
                      if (this$id == null) {
                          if (other$id == null) {
                              break label59;
                          }
                      } else if (this$id.equals(other$id)) {
                          break label59;
                      }
  
                      return false;
                  }
  
                  Object this$name = this.getName();
                  Object other$name = other.getName();
                  if (this$name == null) {
                      if (other$name != null) {
                          return false;
                      }
                  } else if (!this$name.equals(other$name)) {
                      return false;
                  }
  
                  Object this$username = this.getUsername();
                  Object other$username = other.getUsername();
                  if (this$username == null) {
                      if (other$username != null) {
                          return false;
                      }
                  } else if (!this$username.equals(other$username)) {
                      return false;
                  }
  
                  Object this$password = this.getPassword();
                  Object other$password = other.getPassword();
                  if (this$password == null) {
                      if (other$password != null) {
                          return false;
                      }
                  } else if (!this$password.equals(other$password)) {
                      return false;
                  }
  
                  return true;
              }
          }
      }
  
      protected boolean canEqual(final Object other) {
          return other instanceof User;
      }
  
      public int hashCode() {
          int PRIME = true;
          int result = 1;
          Object $id = this.getId();
          int result = result * 59 + ($id == null ? 43 : $id.hashCode());
          Object $name = this.getName();
          result = result * 59 + ($name == null ? 43 : $name.hashCode());
          Object $username = this.getUsername();
          result = result * 59 + ($username == null ? 43 : $username.hashCode());
          Object $password = this.getPassword();
          result = result * 59 + ($password == null ? 43 : $password.hashCode());
          return result;
      }
  
      public String toString() {
          Long var10000 = this.getId();
          return "User(id=" + var10000 + ", name=" + this.getName() + ", username=" + this.getUsername() + ", password=" + this.getPassword() + ")";
      }
  }
  
  ```

<br>

## 결론

 결론적으로, JPA 엔티티 클래스를 작성할 때, **엔티티 클래스에 생성자 코드를 작성하고 싶다면 디폴트 생성자도 같이 작성해야 함**을 기억하는 것이 좋겠다.

 `final` 필드가 없는 클래스의 경우에는 `@RequiredArgsConstructor` 어노테이션만 작성해도 될 테지만, 개인적으로 좋은 방법인지는 모르겠다. `final` 필드가 없는 클래스에 굳이 `@RequiredArgsConstructor`를 붙일 이유가 잘 떠오르지 않기 때문이다.

 `@Data` 어노테이션의 경우는, 엔티티에 사용했을 때 성능상 이슈가 있을 수 있다고는 한다. 지금 범위에서 논할 문제는 아니기 때문에, 어쨌든 `@Data` 어노테이션을 사용할 때에도 디폴트 생성자를 같이 작성해 주는 것이 좋다. 다만 이 경우에도 역시 `final` 필드가 없을 때에는 디폴트 생성자를 작성하지 않더라도, 컴파일러에 의해 디폴트 생성자가 만들어지게 된다.



<br>

*참고*

- https://stackoverflow.com/questions/68314072/why-to-use-allargsconstructor-and-noargsconstructor-together-over-an-entity
- https://stackoverflow.com/questions/2935826/why-does-hibernate-require-no-argument-constructor/29433238#29433238
- https://jcp.org/en/jsr/detail?id=338



