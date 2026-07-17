import { createRouter, createWebHashHistory, createWebHistory } from 'vue-router'
import { ChatDotRound, Collection, Connection, MapLocation, Odometer, Setting, TrendCharts, User } from '@element-plus/icons-vue'
import AppLayout from '@/layouts/AppLayout.vue'
import { routerHistoryMode } from './history'

const routes = [
  {
    path: '/onboarding',
    name: 'Onboarding',
    component: () => import('@/views/Onboarding.vue'),
    meta: { title: '首次启动' },
  },
  {
    path: '/',
    component: AppLayout,
    redirect: '/dashboard',
    children: [
      {
        path: '/dashboard',
        name: 'Dashboard',
        component: () => import('@/views/Dashboard.vue'),
        meta: { title: '学习总览', icon: Odometer },
      },
      {
        path: '/profile',
        name: 'ProfileBuilder',
        component: () => import('@/views/ProfileBuilder.vue'),
        meta: { title: '学习画像', icon: User },
      },
      {
        path: '/agents',
        name: 'AgentWorkspace',
        component: () => import('@/views/AgentWorkspace.vue'),
        meta: { title: '智能体协作', icon: Connection },
      },
      {
        path: '/learning-path',
        name: 'LearningPath',
        component: () => import('@/views/LearningPath.vue'),
        meta: { title: '学习路径', icon: MapLocation },
      },
      {
        path: '/tutor',
        name: 'SmartTutor',
        component: () => import('@/views/SmartTutor.vue'),
        meta: { title: '学习助手', icon: ChatDotRound },
      },
      {
        path: '/assessment',
        name: 'Assessment',
        component: () => import('@/views/Assessment.vue'),
        meta: { title: '练习评估', icon: TrendCharts },
      },
      {
        path: '/knowledge',
        name: 'KnowledgeLibrary',
        component: () => import('@/views/KnowledgeLibrary.vue'),
        meta: { title: '知识库', icon: Collection },
      },
      {
        path: '/model-settings',
        name: 'ModelSettings',
        component: () => import('@/views/ModelSettings.vue'),
        meta: { title: '模型设置', icon: Setting },
      },
    ],
  },
]

export { routes }

const router = createRouter({
  history: routerHistoryMode(typeof window === 'undefined' ? undefined : window.location.protocol) === 'hash'
    ? createWebHashHistory()
    : createWebHistory(),
  routes,
})

export default router
