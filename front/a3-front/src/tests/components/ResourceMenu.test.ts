import { describe, it, expect } from "vitest";
import { mount } from "@vue/test-utils";
import { activateLocale, installLocaleMessages } from "@/i18n";
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
    expect(text).toContain("知识导图");
    expect(text).toContain("题库");
    expect(text).toContain("拓展阅读");
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

  it("renders injected English learning labels", () => {
    installLocaleMessages("en-US", { components: { resourceMenu: { resourceType: "Resource type", resource: "📦 Complete bundle" } } });
    activateLocale("en-US");
    const wrapper = mount(ResourceMenu);

    expect(wrapper.text()).toContain("Resource type");
    expect(wrapper.text()).toContain("Complete bundle");
  });
});
