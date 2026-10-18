---
title: "All Posts"
layout: posts
permalink: /categories/
author_profile: true
---

<script>
  // 개편 전 카테고리 링크(/categories/#kubernetes 등)로 들어오면 새 주제 페이지로 보낸다
  (function () {
    var oldAnchors = { kubernetes: "/categories/Kubernetes/", cs: "/categories/CS/", ai: "/categories/AI/",
      language: "/categories/Programming/", articles: "/categories/articles/", etc: "/categories/etc/", dev: "/" };
    var to = oldAnchors[decodeURIComponent(location.hash.slice(1)).toLowerCase()];
    if (to) location.replace(to);
  })();
</script>
