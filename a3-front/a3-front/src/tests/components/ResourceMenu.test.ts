import { describe, it, expect } from "vitest";
import { mount } from "@vue/test-utils";
import ResourceMenu from "@/components/learning/ResourceMenu.vue";

describe("ResourceMenu", () => {
  it("renders bundle option as default", () => {
    const wrapper = mount(ResourceMenu);
    const options = wrapper.findAll("option");
    expect(options.length).toBeGreaterThan(0);
  });

  it("renders all five single types", () => {
    const wrapper = mount(ResourceMenu);
    const text = wrapper.text();
    expect(text).toContain("课程讲解");
    expect(text).toContain("思维导图");
    expect(text).toContain("题库");
    expect(text).toContain("延伸阅读");
    expect(text).toContain("自适应练习");
  });

  it("emits update:modelValue on bundle selection", async () => {
    const wrapper = mount(ResourceMenu);
    const select = wrapper.find("select");
    await select.setValue("bundle");
    const emitted = wrapper.emitted("update:modelValue");
    expect(emitted).toBeTruthy();
    if (emitted) {
      expect(emitted[0][0]).toEqual({ mode: "bundle" });
    }
  });

  it("emits update:modelValue with resourceType on single selection", async () => {
    const wrapper = mount(ResourceMenu);
    const select = wrapper.find("select");
    await select.setValue("single:course_explanation");
    const emitted = wrapper.emitted("update:modelValue");
    expect(emitted).toBeTruthy();
    if (emitted) {
      expect(emitted[0][0]).toEqual({
        mode: "single",
        resourceType: "course_explanation",
      });
    }
  });
});
