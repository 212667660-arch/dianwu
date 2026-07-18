import { describe, it, expect } from "vitest";
import { mount } from "@vue/test-utils";
import SafeMermaid from "@/components/learning/SafeMermaid.vue";

describe("SafeMermaid", () => {
  it("renders mermaid container for valid flowchart", () => {
    const wrapper = mount(SafeMermaid, {
      props: {
        content: "## Mermaid\nflowchart TD\n  A-->B\n## 大纲\n- A\n  - B",
        outline: "- A\n  - B",
      },
    });
    expect(wrapper.find(".mermaid-container").exists()).toBe(true);
  });

  it("falls back to outline when mermaid is invalid", () => {
    const wrapper = mount(SafeMermaid, {
      props: {
        content: "sequenceDiagram\n  A->>B: hello",
        outline: "- A\n  - B",
      },
    });
    expect(wrapper.find(".outline-fallback").exists()).toBe(true);
  });

  it("falls back when script tag present", () => {
    const wrapper = mount(SafeMermaid, {
      props: {
        content: 'flowchart TD\n  A-->B\n<script>alert(1)</script>',
        outline: "- A\n  - B",
      },
    });
    expect(wrapper.find(".outline-fallback").exists()).toBe(true);
  });

  it("renders outline text from content when no outline prop", () => {
    const wrapper = mount(SafeMermaid, {
      props: {
        content: "graph LR\n  A-->B\n## 大纲\n- 主题\n  - 概念",
      },
    });
    expect(wrapper.text()).toContain("主题");
    expect(wrapper.text()).toContain("概念");
  });
});
