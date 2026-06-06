<script setup lang="ts">
import { reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import AppShell from '../components/AppShell.vue'
import { ApiError } from '../api/client'
import * as accountApi from '../api/account'
import { useToastStore } from '../stores/toast'

const router = useRouter()
const toast = useToastStore()
const busy = ref(false)
const form = reactive({ username: '', oldPassword: '', newPassword: '' })

async function submit() {
  if (busy.value) return
  const username = form.username.trim(); const oldPassword = form.oldPassword.trim(); const newPassword = form.newPassword.trim()
  if (!username || !oldPassword || !newPassword) { toast.error('请把信息填完整'); return }
  busy.value = true
  try { await accountApi.changePassword(username, oldPassword, newPassword); toast.success('密码已修改，请重新登录'); await router.push('/account') }
  catch (e) { toast.error(e instanceof ApiError ? e.message : String(e)) }
  finally { busy.value = false }
}
</script>

<template>
  <AppShell>
    <div class="wrap">
      <div class="form-card">
        <h2>修改密码</h2>
        <p class="subtle" style="margin-top:4px">不需要登录（对应后端 /account/changePassword）</p>
        <div class="vstack" style="margin-top:16px">
          <div><label>用户名</label><input v-model.trim="form.username" autocomplete="username" /></div>
          <div><label>旧密码</label><input v-model.trim="form.oldPassword" type="password" autocomplete="current-password" /></div>
          <div><label>新密码</label><input v-model.trim="form.newPassword" type="password" autocomplete="new-password" /></div>
          <button class="primary" :disabled="busy" @click="submit" style="width:100%;padding:14px;font-size:15px">提交</button>
        </div>
      </div>
    </div>
  </AppShell>
</template>

<style scoped>
.wrap { display: grid; justify-items: center; align-content: start; padding: clamp(40px, 12vh, 120px) 16px 40px; }
.form-card { width: min(420px, 100%); background: var(--surface); border: 1px solid var(--border); border-radius: var(--r-lg); padding: 28px 24px; box-shadow: var(--shadow); }
.form-card h2 { margin: 0; font-size: 22px; font-weight: 800; }
</style>
