- **Amazon EKS 관련 서비스**
    
    `Cloud Controller Manager` 를 통해 K8S NodePort 정보를 사용하는 CLB/NLB 프로비저닝
    
    ![ [https://youtu.be/E49Q3y9wsUo?si=reLXmCvO1me52lf4&t=375](https://youtu.be/E49Q3y9wsUo?si=reLXmCvO1me52lf4&t=3751)](attachment:659b24ed-08c5-4e07-a8d8-ce826076ef74:CleanShot_2025-02-08_at_07.24.12.png)
    
     [https://youtu.be/E49Q3y9wsUo?si=reLXmCvO1me52lf4&t=375](https://youtu.be/E49Q3y9wsUo?si=reLXmCvO1me52lf4&t=3751)
    
    ![CleanShot 2025-02-08 at 07.25.11@2x.png](attachment:576bfcc0-6bf7-4736-bae8-dda668c2803a:CleanShot_2025-02-08_at_07.25.112x.png)
    
    `Service (LoadBalancer Controller`) : **AWS Load Balancer Controller** + **NLB** **(파드) IP 모드** 동작 with **AWS VPC CNI**
    
    ![](https://s3-us-west-2.amazonaws.com/secure.notion-static.com/c36dfaa0-ab24-4cb7-bb43-c9e8bd114586/Untitled.png)
    
    ![https://docs.aws.amazon.com/eks/latest/best-practices/load-balancing.html](attachment:cb944f94-b0b5-49a4-99cf-ff76a16ca141:image.png)
    
    https://docs.aws.amazon.com/eks/latest/best-practices/load-balancing.html