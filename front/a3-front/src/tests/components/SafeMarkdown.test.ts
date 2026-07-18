import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import SafeMarkdown from '@/components/learning/SafeMarkdown.vue'

describe('SafeMarkdown', () => {
  it('renders model HTML as inert text', () => {
    const wrapper = mount(SafeMarkdown, {
      props: { content: '<img src=x onerror=alert(1)>\n## 标题' },
    })

    expect(wrapper.find('img').exists()).toBe(false)
    expect(wrapper.text()).toContain('<img src=x onerror=alert(1)>')
    expect(wrapper.find('h2').text()).toBe('标题')
  })

  it('renders fenced code and lists without executable markup', () => {
    const wrapper = mount(SafeMarkdown, {
      props: { content: '- 第一项\n- 第二项\n```html\n<script>alert(1)</script>\n```' },
    })

    expect(wrapper.findAll('li')).toHaveLength(2)
    expect(wrapper.find('script').exists()).toBe(false)
    expect(wrapper.find('code').text()).toContain('<script>alert(1)</script>')
  })
})
