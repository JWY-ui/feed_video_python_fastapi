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
const form = reactive({ username: '', password: '' })

async function submit() {
  if (busy.value) return
  const username = form.username.trim(); const password = form.password.trim()
  if (!username || !password) { toast.error('请输入 username 和 password'); return }
  busy.value = true
  try { await accountApi.register(username, password); toast.success('注册成功，请登录'); await router.push('/account') }
  catch (e) { toast.error(e instanceof ApiError ? e.message : String(e)) }
  finally { busy.value = false }
}
</script>

<template>
  <AppShell>
    <div class="wrap">
      <div class="form-card">
        <h2>注册</h2>
        <p class="subtle" style="margin-top:4px">创建新账号（对应后端 /account/register）</p>
        <div class="vstack" style="margin-top:16px">
          <div><label>用户名</label><input v-model.trim="form.username" autocomplete="username" /></div>
          <div><label>密码</label><input v-model.trim="form.password" type="password" autocomplete="new-password" /></div>
          <button class="primary" :disabled="busy" @click="submit" style="width:100%;padding:14px;font-size:15px">注册</button>
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
