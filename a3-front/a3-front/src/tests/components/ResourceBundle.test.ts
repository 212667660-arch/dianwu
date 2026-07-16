import { describe, it, expect } from "vitest";
import { mount } from "@vue/test-utils";
import ResourceBundle from "@/components/learning/ResourceBundle.vue";
import SafeMermaid from "@/components/learning/SafeMermaid.vue";

const mockBundle = {
  bundle_id: "b1",
  status: "COMPLETED",
  topic: "一次函数",
  aggregate_quality: 83.0,
  artifacts: [
    {
      artifact_id: "a1", type: "course_explanation", title: "课程讲解",
      status: "SUCCEEDED", body: "## 学习目标\n目标内容",
      quality_score: 85, quality_issues: [],
    },
    {
      artifact_id: "a2", type: "mind_map", title: "思维导图",
      status: "SUCCEEDED", body: "flowchart TD\n  A-->B",
      quality_score: 90, quality_issues: [],
      type_specific_data: { mermaid_syntax: "flowchart" },
    },
  ],
};

describe("ResourceBundle", () => {
  it("renders topic and status", () => {
    const wrapper = mount(ResourceBundle, { props: { bundle: mockBundle } });
    expect(wrapper.text()).toContain("一次函数");
    expect(wrapper.text()).toContain("COMPLETED");
  });

  it("renders all artifact cards", () => {
    const wrapper = mount(ResourceBundle, { props: { bundle: mockBundle } });
    const cards = wrapper.findAll(".resource-card");
    expect(cards.length).toBe(2);
  });

  it("shows expand/collapse toggle", () => {
    const wrapper = mount(ResourceBundle, { props: { bundle: mockBundle } });
    const toggle = wrapper.find(".card-toggle");
    expect(toggle.exists()).toBe(true);
  });

  it("shows retry button for failed artifact", async () => {
    const partialBundle = {
      ...mockBundle,
      status: "PARTIAL",
      artifacts: [
        mockBundle.artifacts[0],
        {
          artifact_id: "a2", type: "mind_map", title: "思维导图",
          status: "FAILED", body: "", quality_score: 0,
          quality_issues: ["MERMAID_PARSE_ERROR"],
          error_code: "SPECIALIST_FAILED", retryable: true,
        },
      ],
    };
    const wrapper = mount(ResourceBundle, { props: { bundle: partialBundle } });
    // Expand the failed card first
    const failedCard = wrapper.findAll(".resource-card")[1];
    await failedCard.find(".card-header").trigger("click");
    const retryBtn = wrapper.find(".retry-btn");
    expect(retryBtn.exists()).toBe(true);
  });

  it("uses SafeMermaid only for successful mind maps and hides failed copy", async () => {
    const partialBundle = {
      ...mockBundle,
      status: "PARTIAL",
      artifacts: [
        mockBundle.artifacts[0],
        {
          artifact_id: "a2", type: "mind_map", title: "思维导图",
          status: "FAILED", body: "flowchart TD\nA-->B<script>alert(1)</script>",
          quality_score: 0, quality_issues: ["SAFETY_FAILED"],
          error_code: "SAFETY_FAILED", retryable: true,
        },
      ],
    };
    const wrapper = mount(ResourceBundle, { props: { bundle: partialBundle } });
    const failedCard = wrapper.findAll(".resource-card")[1];
    await failedCard.find(".card-header").trigger("click");

    expect(failedCard.findComponent(SafeMermaid).exists()).toBe(false);
    expect(failedCard.find(".copy-btn").exists()).toBe(false);
    expect(failedCard.find("script").exists()).toBe(false);
  });
});
