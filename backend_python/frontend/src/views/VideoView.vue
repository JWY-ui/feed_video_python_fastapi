<script setup lang="ts">
import { onUnmounted, reactive, ref, watch } from 'vue'
import { RouterLink, useRouter } from 'vue-router'
import AppShell from '../components/AppShell.vue'
import { ApiError } from '../api/client'
import * as videoApi from '../api/video'
import type { Video } from '../api/types'
import { useAuthStore } from '../stores/auth'
import { useToastStore } from '../stores/toast'
import SparkMD5 from 'spark-md5'

const router = useRouter()
const auth = useAuthStore()
const toast = useToastStore()

const busy = ref(false)
const stage = ref('')
const published = ref<Video | null>(null)
const videoInput = ref<HTMLInputElement | null>(null)
const coverInput = ref<HTMLInputElement | null>(null)
const publishForm = reactive({ title: '', description: '', video: null as File | null, cover: null as File | null })
const preview = reactive({ videoUrl: '', coverUrl: '' })
const uploadProgress = reactive({ uploadedBytes: 0, totalBytes: 0, percent: 0 })

function setPreviewVideo(file: File | null) { if (preview.videoUrl) URL.revokeObjectURL(preview.videoUrl); preview.videoUrl = file ? URL.createObjectURL(file) : '' }
function setPreviewCover(file: File | null) { if (preview.coverUrl) URL.revokeObjectURL(preview.coverUrl); preview.coverUrl = file ? URL.createObjectURL(file) : '' }
watch(() => publishForm.video, (f) => setPreviewVideo(f))
watch(() => publishForm.cover, (f) => setPreviewCover(f))
onUnmounted(() => { setPreviewVideo(null); setPreviewCover(null) })

function pickVideo(e: Event) { publishForm.video = (e.target as HTMLInputElement).files?.[0] ?? null }
function pickCover(e: Event) { publishForm.cover = (e.target as HTMLInputElement).files?.[0] ?? null }
function openVideoPicker() { videoInput.value?.click() }
function openCoverPicker() { coverInput.value?.click() }
function clearVideo() { publishForm.video = null; if (videoInput.value) videoInput.value.value = '' }
function clearCover() { publishForm.cover = null; if (coverInput.value) coverInput.value.value = '' }
function resetProgress() { uploadProgress.uploadedBytes = 0; uploadProgress.totalBytes = 0; uploadProgress.percent = 0 }

async function computeFileMD5(file: File): Promise<string> {
  const chunkSize = 2 << 20; const spark = new SparkMD5.ArrayBuffer()
  for (let offset = 0; offset < file.size; offset += chunkSize) { const buf = await file.slice(offset, Math.min(offset + chunkSize, file.size)).arrayBuffer(); spark.append(buf) }
  return spark.end()
}
async function computeChunkMD5(blob: Blob): Promise<string> { const buf = await blob.arrayBuffer(); const spark = new SparkMD5.ArrayBuffer(); spark.append(buf); return spark.end() }

const CHUNK_SIZE = 5 << 20; const MAX_CONCURRENT = 3; const MAX_RETRIES = 3

async function uploadVideoChunked(file: File): Promise<videoApi.UploadResponse> {
  const totalChunks = Math.ceil(file.size / CHUNK_SIZE); const fileHash = await computeFileMD5(file)
  stage.value = '初始化上传'
  const initRes = await videoApi.initChunkUpload({ filename: file.name, file_size: file.size, chunk_size: CHUNK_SIZE, total_chunks: totalChunks, file_hash: fileHash })
  const uploadId = initRes.upload_id; const uploadedSet = new Set(initRes.uploaded_chunks)
  uploadProgress.totalBytes = file.size; uploadProgress.uploadedBytes = uploadedSet.size * CHUNK_SIZE
  if (uploadedSet.has(totalChunks - 1)) { uploadProgress.uploadedBytes -= CHUNK_SIZE; uploadProgress.uploadedBytes += file.size - (totalChunks - 1) * CHUNK_SIZE }
  uploadProgress.percent = uploadProgress.totalBytes > 0 ? Math.round((uploadProgress.uploadedBytes / uploadProgress.totalBytes) * 100) : 0

  const pending: number[] = []
  for (let i = 0; i < totalChunks; i++) { if (!uploadedSet.has(i)) pending.push(i) }
  if (pending.length === 0) { stage.value = '合并文件'; return videoApi.completeChunkUpload(uploadId) }

  stage.value = '上传视频'
  let idx = 0
  const advanceProgress = (ci: number) => { const cb = ci === totalChunks - 1 ? file.size - ci * CHUNK_SIZE : CHUNK_SIZE; uploadProgress.uploadedBytes += cb; uploadProgress.percent = Math.round((uploadProgress.uploadedBytes / uploadProgress.totalBytes) * 100) }
  const uploadOne = async (ci: number) => {
    const start = ci * CHUNK_SIZE; const end = Math.min(start + CHUNK_SIZE, file.size); const blob = file.slice(start, end); const hash = await computeChunkMD5(blob)
    let lastErr: unknown
    for (let attempt = 0; attempt < MAX_RETRIES; attempt++) { try { await videoApi.uploadChunk(uploadId, ci, hash, blob); advanceProgress(ci); return } catch (e) { lastErr = e } }
    throw lastErr
  }
  await new Promise<void>((resolve, reject) => { let active = 0; let done = false; const next = () => { if (done) return; if (idx >= pending.length && active === 0) { resolve(); return }; while (active < MAX_CONCURRENT && idx < pending.length) { const ci = pending[idx++]!; active++; uploadOne(ci).then(() => { active--; next() }).catch((e) => { done = true; reject(e) }) } }; next() })
  stage.value = '合并文件'; return videoApi.completeChunkUpload(uploadId)
}

async function onPublish() {
  if (busy.value || !auth.isLoggedIn) { toast.error('请先登录'); await router.push('/account'); return }
  const title = publishForm.title.trim(); const description = publishForm.description.trim()
  if (!title) { toast.error('请输入 title'); return }
  if (!publishForm.video) { toast.error('请选择视频文件（.mp4）'); return }
  if (!publishForm.cover) { toast.error('请选择封面图片（jpg/png/webp）'); return }

  busy.value = true; stage.value = ''; published.value = null; resetProgress()
  try {
    const videoRes = await uploadVideoChunked(publishForm.video!)
    stage.value = '上传封面'; const coverRes = await videoApi.uploadCover(publishForm.cover!)
    const coverUrl = coverRes.url || coverRes.cover_url || ''; const playUrl = videoRes.url || videoRes.play_url || ''
    if (!coverUrl || !playUrl) { toast.error('上传成功但缺少 url'); return }
    stage.value = '发布视频'; const res = await videoApi.publishVideo({ title, description, play_url: playUrl, cover_url: coverUrl })
    published.value = res; toast.success('已发布')
    publishForm.title = ''; publishForm.description = ''; clearVideo(); clearCover()
  } catch (e) { toast.error(e instanceof ApiError ? e.message : String(e)) }
  finally { busy.value = false; stage.value = ''; resetProgress() }
}
</script>

<template>
  <AppShell>
    <div class="wrap">
      <div class="card publish-card">
        <div class="row" style="justify-content:space-between">
          <h2 style="margin:0">发布视频</h2>
          <span v-if="busy" class="pill">{{ stage || '…' }}</span>
        </div>
        <p class="subtle" style="margin-top:8px">选择视频文件与封面图片，上传到本机后自动生成 URL，再写入 /video/publish。</p>

        <div class="vstack" style="margin-top:16px;gap:16px">
          <div><label>标题</label><input v-model.trim="publishForm.title" :disabled="busy" /></div>
          <div><label>描述</label><textarea v-model.trim="publishForm.description" :disabled="busy" /></div>

          <div class="grid two">
            <div>
              <label>视频 (.mp4)</label>
              <input ref="videoInput" class="file-native" type="file" accept="video/mp4" :disabled="busy" @change="pickVideo" />
              <div class="file-box">
                <button :disabled="busy" @click="openVideoPicker">选择视频</button>
                <span class="file-name" :class="publishForm.video ? '' : 'muted'">{{ publishForm.video ? publishForm.video.name : '未选择文件' }}</span>
                <button v-if="publishForm.video" :disabled="busy" @click="clearVideo">清除</button>
              </div>
              <div v-if="publishForm.video" class="subtle" style="margin-top:4px">{{ publishForm.video.name }}（{{ Math.ceil(publishForm.video.size / 1024 / 1024) }} MB）</div>
            </div>
            <div>
              <label>封面 (jpg/png/webp)</label>
              <input ref="coverInput" class="file-native" type="file" accept="image/jpeg,image/png,image/webp" :disabled="busy" @change="pickCover" />
              <div class="file-box">
                <button :disabled="busy" @click="openCoverPicker">选择封面</button>
                <span class="file-name" :class="publishForm.cover ? '' : 'muted'">{{ publishForm.cover ? publishForm.cover.name : '未选择文件' }}</span>
                <button v-if="publishForm.cover" :disabled="busy" @click="clearCover">清除</button>
              </div>
            </div>
          </div>

          <!-- Progress -->
          <div v-if="busy && uploadProgress.totalBytes > 0" class="progress-wrap">
            <div class="progress-bar"><div class="progress-fill" :style="{ width: uploadProgress.percent + '%' }" /></div>
            <div class="subtle">{{ (uploadProgress.uploadedBytes / 1024 / 1024).toFixed(1) }} / {{ (uploadProgress.totalBytes / 1024 / 1024).toFixed(1) }} MB ({{ uploadProgress.percent }}%)</div>
          </div>

          <!-- Preview -->
          <div v-if="preview.coverUrl || preview.videoUrl" class="grid two">
            <div v-if="preview.videoUrl" class="preview-card"><div class="subtle">视频预览</div><video :src="preview.videoUrl" controls playsinline preload="metadata" /></div>
            <div v-if="preview.coverUrl" class="preview-card"><div class="subtle">封面预览</div><img :src="preview.coverUrl" alt="cover preview" class="cover-preview" /></div>
          </div>

          <div style="text-align:right"><button class="primary" :disabled="busy" @click="onPublish" style="padding:14px 28px;font-size:16px">发布</button></div>
        </div>

        <div v-if="published" class="card" style="margin-top:16px;background:var(--bg)">
          <h3 style="margin:0">已发布</h3>
          <div class="row" style="justify-content:space-between;margin-top:8px">
            <div><strong>{{ published.title }}</strong><p class="subtle mono">#{{ published.id }}</p></div>
            <div class="row">
              <RouterLink class="pill" :to="`/video/${published.id}`">去播放</RouterLink>
              <a class="pill mono" :href="published.play_url" target="_blank" rel="noreferrer">play_url</a>
            </div>
          </div>
        </div>
      </div>
    </div>
  </AppShell>
</template>

<style scoped>
.wrap { display: grid; justify-items: center; }
.publish-card { width: min(980px, 100%); padding: 24px; }

.file-native { position: absolute; width: 1px; height: 1px; overflow: hidden; clip: rect(0,0,0,0); }
.file-box { display: flex; align-items: center; gap: 8px; padding: 10px 14px; border: 1.5px dashed var(--border); border-radius: var(--r-md); min-height: 46px; background: var(--bg); }
.file-box button { padding: 8px 14px; }
.file-name { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-size: 13px; }

.progress-wrap { display: grid; gap: 6px; }
.progress-bar { height: 8px; background: var(--border); border-radius: var(--r-full); overflow: hidden; }
.progress-fill { height: 100%; background: var(--pink-gradient); border-radius: var(--r-full); transition: width 200ms var(--ease-out); }

.preview-card { border: 1px solid var(--border); background: var(--bg); border-radius: var(--r-md); padding: 12px; display: grid; gap: 8px; }
.preview-card video { width: 100%; border-radius: var(--r-sm); }
.cover-preview { width: 100%; aspect-ratio: 9/12; object-fit: cover; border-radius: var(--r-sm); }
</style>
