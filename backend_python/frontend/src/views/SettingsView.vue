<script setup lang="ts">
import { computed, nextTick, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import AppShell from '../components/AppShell.vue'
import UserAvatar from '../components/UserAvatar.vue'
import { ApiError } from '../api/client'
import * as accountApi from '../api/account'
import { useAuthStore } from '../stores/auth'
import { useToastStore } from '../stores/toast'

const router = useRouter()
const auth = useAuthStore()
const toast = useToastStore()
const busy = ref(false)

const me = computed(() => ({ id: auth.claims?.account_id ?? 0, username: auth.claims?.username ?? '' }))
const rename = reactive({ open: false, newUsername: '' })

async function openRename() { if (!auth.isLoggedIn) return; rename.open = true; rename.newUsername = me.value.username; await nextTick() }
async function submitRename() {
  if (!auth.isLoggedIn || busy.value) return
  const newUsername = rename.newUsername.trim()
  if (!newUsername) { toast.error('请输入新用户名'); return }
  busy.value = true
  try { const res = await accountApi.rename(newUsername); auth.setToken(res.token); rename.open = false; toast.success('改名成功（已刷新 token）') }
  catch (e) { toast.error(e instanceof ApiError ? e.message : String(e)) }
  finally { busy.value = false }
}

async function goLogin() { await router.push('/account') }
async function goChangePassword() { await router.push('/account/change-password') }
async function onLogout() {
  if (!auth.isLoggedIn || busy.value) return
  if (!window.confirm('确认退出登录？')) return
  busy.value = true
  try { await accountApi.logout() }
  catch (e) { toast.error(`登出失败：${e instanceof ApiError ? e.message : String(e)}`) }
  finally { auth.clearTokens(); rename.open = false; toast.info('已退出登录'); busy.value = false; await router.push('/') }
}
</script>

<template>
  <AppShell>
    <div v-if="!auth.isLoggedIn" class="login-wrap">
      <div class="card" style="width:min(420px,100%)">
        <h2>设置</h2>
        <p class="subtle" style="margin-top:8px">需要先登录后才能进行改名/退出等操作。</p>
        <button class="primary" style="margin-top:16px" @click="goLogin">去登录</button>
      </div>
    </div>

    <div v-else class="vstack">
      <div class="card">
        <div class="row" style="gap:14px;align-items:center">
          <UserAvatar :username="me.username" :id="me.id" :size="56" />
          <div><h2 style="margin:0">@{{ me.username }}</h2><p class="subtle mono">#{{ me.id }}</p></div>
        </div>

        <div class="card" style="margin-top:16px;background:var(--bg)">
          <div class="row" style="justify-content:space-between">
            <h3 style="margin:0">账号设置</h3>
            <button class="ghost" :disabled="busy" @click="openRename">改名</button>
          </div>
          <div v-if="rename.open" class="vstack" style="margin-top:12px">
            <input v-model.trim="rename.newUsername" placeholder="新用户名" @keydown.enter="submitRename" />
            <div class="row" style="justify-content:flex-end">
              <button :disabled="busy" @click="rename.open = false">取消</button>
              <button class="primary" :disabled="busy" @click="submitRename">提交</button>
            </div>
          </div>
        </div>

        <div class="card" style="margin-top:12px;background:var(--bg)">
          <h3 style="margin:0">账号安全</h3>
          <div class="row" style="margin-top:12px">
            <button class="ghost" :disabled="busy" @click="goChangePassword">修改密码</button>
            <button class="danger" :disabled="busy" @click="onLogout">退出登录</button>
          </div>
        </div>
      </div>

      <div class="card">
        <h3>说明</h3>
        <div class="vstack" style="margin-top:8px">
          <span class="pill ok">改名后会返回新 token，旧 token 立即失效</span>
          <span class="pill ok">退出登录会清空本地 token</span>
          <span class="pill">修改密码无需登录，但成功后会让旧 token 失效</span>
        </div>
      </div>
    </div>
  </AppShell>
</template>

<style scoped>
.login-wrap { display: grid; justify-items: center; padding: clamp(40px, 12vh, 120px) 16px; }
h2 { font-weight: 800; }
h3 { font-size: 15px; font-weight: 700; }
</style>
