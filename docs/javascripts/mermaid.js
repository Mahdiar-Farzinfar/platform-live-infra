(function () {
  function renderMermaid() {
    if (!window.mermaid) {
      console.error("Mermaid was not loaded.");
      return;
    }

    const nodes = document.querySelectorAll(".mermaid");

    if (!nodes.length) {
      return;
    }

    window.mermaid.initialize({
      startOnLoad: false,
      securityLevel: "strict",
      theme: "default",
    });

    window.mermaid
      .run({ nodes })
      .catch((error) => {
        console.error("Mermaid rendering failed:", error);
      });
  }

  if (window.document$) {
    document$.subscribe(() => {
      renderMermaid();
    });
  } else {
    window.addEventListener("DOMContentLoaded", renderMermaid);
  }
})();
