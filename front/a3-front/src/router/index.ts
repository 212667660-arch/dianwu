import { createRouter, createWebHashHistory, createWebHistory } from 'vue-router'
import { ChatDotRound, Collection, Connection, MapLocation, Odometer, Setting, TrendCharts, User } from '@element-plus/icons-vue'
import AppLayout from '@/layouts/AppLayout.vue'
import { routerHistoryMode } from './history'

const routes = [
  {
    path: '/onboarding',
    name: 'Onboarding',
    component: () => import('@/views/Onboarding.vue'),
    meta: { titleKey: 'navigation.onboarding' },
  },
  {
    path: '/',
    component: AppLayout,
    redirect: '/dashboard',
    meta: { titleKey: 'navigation.dashboard' },
    children: [
      {
        path: '/dashboard',
        name: 'Dashboard',
        component: () => import('@/views/Dashboard.vue'),
        meta: { titleKey: 'navigation.dashboard', icon: Odometer },
      },
      {
        path: '/profile',
        name: 'ProfileBuilder',
        component: () => import('@/views/ProfileBuilder.vue'),
        meta: { titleKey: 'navigation.profile', icon: User },
      },
      {
        path: '/agents',
        name: 'AgentWorkspace',
        component: () => import('@/views/AgentWorkspace.vue'),
        meta: { titleKey: 'navigation.agents', icon: Connection },
      },
      {
        path: '/learning-path',
        name: 'LearningPath',
        component: () => import('@/views/LearningPath.vue'),
        meta: { titleKey: 'navigation.learningPath', icon: MapLocation },
      },
      {
        path: '/tutor',
        name: 'SmartTutor',
        component: () => import('@/views/SmartTutor.vue'),
        meta: { titleKey: 'navigation.tutor', icon: ChatDotRound },
      },
      {
        path: '/assessment',
        name: 'Assessment',
        component: () => import('@/views/Assessment.vue'),
        meta: { titleKey: 'navigation.assessment', icon: TrendCharts },
      },
      {
        path: '/knowledge',
        name: 'KnowledgeLibrary',
        component: () => import('@/views/KnowledgeLibrary.vue'),
        meta: { titleKey: 'navigation.knowledge', icon: Collection },
      },
      {
        path: '/model-settings',
        name: 'ModelSettings',
        component: () => import('@/views/ModelSettings.vue'),
        meta: { titleKey: 'navigation.modelSettings', icon: Setting },
      },
      {
        path: '/desktop-settings',
        name: 'DesktopSettings',
        component: () => import('@/views/DesktopSettings.vue'),
        meta: { titleKey: 'navigation.desktopSettings', icon: Setting },
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
