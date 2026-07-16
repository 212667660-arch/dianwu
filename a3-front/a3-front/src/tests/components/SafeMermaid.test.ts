import { describe, it, expect } from "vitest";
import { flushPromises, mount } from "@vue/test-utils";
import SafeMermaid from "@/components/learning/SafeMermaid.vue";
import { beforeEach, vi } from "vitest";

const mermaidRender = vi.hoisted(() => vi.fn());
const mermaidInitialize = vi.hoisted(() => vi.fn());
vi.mock("mermaid", () => ({
  default: { initialize: mermaidInitialize, render: mermaidRender },
}));

beforeEach(() => {
  mermaidInitialize.mockReset();
  mermaidRender.mockReset();
  mermaidRender.mockResolvedValue({ svg: '<svg><text>safe</text></svg>' });
});

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

  it("falls back after mermaid.render rejects", async () => {
    mermaidRender.mockRejectedValue(new Error("parse"));
    const wrapper = mount(SafeMermaid, {
      props: { content: "flowchart TD\nA-->B", outline: "- A\n  - B" },
    });

    await flushPromises();

    expect(wrapper.find(".outline-fallback").exists()).toBe(true);
  });

  it("rejects oversized and directive-bearing diagrams", () => {
    const directive = mount(SafeMermaid, {
      props: { content: "%%{init: {'securityLevel':'loose'}}%%\nflowchart TD\nA-->B", outline: "- A" },
    });
    const oversized = mount(SafeMermaid, {
      props: { content: `flowchart TD\n${'A-->B\n'.repeat(251)}`, outline: "- A" },
    });

    expect(directive.find(".outline-fallback").exists()).toBe(true);
    expect(oversized.find(".outline-fallback").exists()).toBe(true);
  });

  it("sanitizes unsafe nodes and attributes from rendered SVG", async () => {
    mermaidRender.mockResolvedValue({
      svg: '<svg onload="alert(1)"><foreignObject><div>bad</div></foreignObject><g id="safe"><text>ok</text></g></svg>',
    });
    const wrapper = mount(SafeMermaid, {
      props: { content: "flowchart TD\nA-->B", outline: "- A\n- B" },
    });

    await flushPromises();

    expect(wrapper.html()).not.toContain("onload");
    expect(wrapper.html()).not.toContain("foreignObject");
    expect(wrapper.text()).toContain("ok");
  });

  it("falls back when node or edge budgets are exceeded", () => {
    const edges = Array.from({ length: 301 }, (_, index) => `N${index}-->N${index + 1}`).join(";");
    const wrapper = mount(SafeMermaid, {
      props: { content: `flowchart TD\n${edges}`, outline: "- fallback" },
    });

    expect(wrapper.find(".outline-fallback").exists()).toBe(true);
  });
});
