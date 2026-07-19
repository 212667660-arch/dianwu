import { describe, it, expect } from "vitest";
import { mount } from "@vue/test-utils";
import ResourceBundle from "@/components/learning/ResourceBundle.vue";
import SafeMermaid from "@/components/learning/SafeMermaid.vue";
import type { ResourceBundle as ResourceBundleType } from "@/api/types";

const mockBundle: ResourceBundleType = {
  bundle_id: "b1",
  protocol_version: "learning-resource-bundle/v2",
  status: "COMPLETED",
  topic: "一次函数",
  profile_version: 1,
  learning_state_version: "1",
  mode: "bundle",
  requested_types: ["course_explanation", "mind_map"],
  aggregate_quality: 83.0,
  created_at: "2026-07-17T00:00:00Z",
  knowledge_sources: [],
  public_sources: [],
  artifacts: [
    {
      artifact_id: "a1", type: "course_explanation", title: "课程讲解",
      status: "SUCCEEDED", body: "## 学习目标\n目标内容",
      quality_score: 85, quality_issues: [], type_specific_data: {}, error_code: null, retryable: false,
    },
    {
      artifact_id: "a2", type: "mind_map", title: "思维导图",
      status: "SUCCEEDED", body: "flowchart TD\n  A-->B",
      quality_score: 90, quality_issues: [],
      type_specific_data: { mermaid_syntax: "flowchart" },
      error_code: null, retryable: false,
    },
  ],
};

describe("ResourceBundle", () => {
  it("renders topic and status", () => {
    const wrapper = mount(ResourceBundle, { props: { bundle: mockBundle } });
    expect(wrapper.text()).toContain("一次函数");
    expect(wrapper.text()).toContain("已完成");
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
    const partialBundle: ResourceBundleType = {
      ...mockBundle,
      status: "PARTIAL",
      artifacts: [
        mockBundle.artifacts[0],
        {
          artifact_id: "a2", type: "mind_map", title: "思维导图",
          status: "FAILED", body: "", quality_score: 0,
          type_specific_data: {},
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
    const partialBundle: ResourceBundleType = {
      ...mockBundle,
      status: "PARTIAL",
      artifacts: [
        mockBundle.artifacts[0],
        {
          artifact_id: "a2", type: "mind_map", title: "思维导图",
          status: "FAILED", body: "flowchart TD\nA-->B<script>alert(1)</script>",
          type_specific_data: {}, quality_score: 0, quality_issues: ["SAFETY_FAILED"],
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

  it("shows a safe message for content safety blocks without exposing reason details", async () => {
    const partialBundle: ResourceBundleType = {
      ...mockBundle,
      status: "PARTIAL",
      artifacts: [
        {
          ...mockBundle.artifacts[0],
          status: "FAILED",
          body: "",
          quality_score: 0,
          quality_issues: ["ACTIVE_CONTENT_BLOCKED"],
          error_code: "CONTENT_ARTIFACT_BLOCKED",
          retryable: true,
          safety: {
            stage: "ARTIFACT",
            decision: "BLOCK",
            risk_level: "HIGH",
            categories: ["ACTIVE_CONTENT_OR_UNSAFE_RENDERING"],
            reason_codes: ["ACTIVE_CONTENT_BLOCKED"],
            policy_version: "content-safety/v1",
            reviewer_profile_id: "reviewer",
            checked_at: "2026-07-17T00:00:00Z",
          },
        },
        mockBundle.artifacts[1],
      ],
    };
    const wrapper = mount(ResourceBundle, { props: { bundle: partialBundle } });
    const blockedCard = wrapper.findAll(".resource-card")[0];
    await blockedCard.find(".card-header").trigger("click");

    expect(blockedCard.text()).toContain("内容未通过安全检查");
    expect(blockedCard.text()).not.toContain("ACTIVE_CONTENT_BLOCKED");
  });

  it("shows the independent answer reviewer verdict", async () => {
    const reviewed: ResourceBundleType = {
      ...mockBundle,
      artifacts: [{
        ...mockBundle.artifacts[0],
        type_specific_data: {
          answer_review: {
            agent: 'answer-reviewer/v1', status: 'REPAIRED', issues: [],
            repair_attempted: true, formula_checked: true, substitution_checked: true,
          },
        },
      }, mockBundle.artifacts[1]],
    }
    const wrapper = mount(ResourceBundle, { props: { bundle: reviewed } })
    const card = wrapper.findAll('.resource-card')[0]

    expect(card.text()).toContain('答案复核：已修正')
    expect(card.text()).toContain('公式与代入已检查')
  })
});
