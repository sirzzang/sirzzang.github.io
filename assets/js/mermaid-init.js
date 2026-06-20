// mermaid 클라이언트 사이드 렌더링
// Kramdown+Rouge 가 만든 ```mermaid 코드블록(<div class="language-mermaid">)에서
// 원본 텍스트만 뽑아 <pre class="mermaid"> 로 바꾼 뒤, dirt 스킨 팔레트로 렌더한다.
// 이 파일은 mermaid 블록이 있는 글에서만 조건부로 로드된다(_includes/scripts.html).
import mermaid from "https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.esm.min.mjs";

// dirt 스킨 팔레트
const DIRT = {
  charcoal: "#343434",
  beige: "#e9dcbe",
  lightgray: "#f3f3f3",
};

// Rouge 가 만든 코드블록 → mermaid 가 읽는 <pre class="mermaid"> 로 교체.
// textContent 로 읽으면 Rouge 의 <span> 분할과 HTML 엔티티(--&gt;&gt; 등)가
// 자동으로 디코드된 원본 다이어그램 텍스트를 얻는다.
const blocks = document.querySelectorAll(".language-mermaid");
blocks.forEach((block) => {
  const code = block.textContent.trim();
  const pre = document.createElement("pre");
  pre.className = "mermaid";
  pre.textContent = code;
  block.replaceWith(pre);
});

if (document.querySelector("pre.mermaid")) {
  mermaid.initialize({
    startOnLoad: false,
    theme: "base",
    themeVariables: {
      fontFamily: "inherit",
      background: DIRT.lightgray,
      primaryColor: DIRT.beige,
      primaryBorderColor: DIRT.charcoal,
      primaryTextColor: DIRT.charcoal,
      secondaryColor: DIRT.lightgray,
      tertiaryColor: DIRT.lightgray,
      lineColor: DIRT.charcoal,
      textColor: DIRT.charcoal,
      // flowchart 노드
      nodeBorder: DIRT.charcoal,
      clusterBkg: DIRT.lightgray,
      clusterBorder: DIRT.charcoal,
      // sequenceDiagram
      actorBkg: DIRT.beige,
      actorBorder: DIRT.charcoal,
      actorTextColor: DIRT.charcoal,
      signalColor: DIRT.charcoal,
      signalTextColor: DIRT.charcoal,
      labelBoxBkgColor: DIRT.beige,
      labelBoxBorderColor: DIRT.charcoal,
      labelTextColor: DIRT.charcoal,
      noteBkgColor: DIRT.beige,
      noteBorderColor: DIRT.charcoal,
      noteTextColor: DIRT.charcoal,
    },
  });
  await mermaid.run({ querySelector: "pre.mermaid" });
}
