<template>
  <div class="app">
    <!-- 后端未连接横幅 -->
    <div v-if="backendOffline" class="offline-banner">
      <span>后端服务未连接 — 请确认已运行 start.bat</span>
      <button class="btn-retry" :disabled="healthChecking" @click="checkHealth">
        {{ healthChecking ? '检测中...' : '重试连接' }}
      </button>
    </div>

    <!-- Header -->
    <header class="header">
      <h1>动作数据集 JSON 生成器</h1>
      <div class="header-right">
        <span :class="['mode-badge', backendOffline ? 'offline' : (resolvedMode === 'llm' ? 'llm' : 'pool')]">
          {{ backendOffline ? '🔴 未连接' : (resolvedMode === 'llm' ? '🟢 LLM 模式' : '🟡 要素池模式') }}
        </span>
        <label class="mode-toggle" v-if="!backendOffline">
          <span class="toggle-label">生成模式：</span>
          <select v-model="generationMode" class="mode-select">
            <option value="auto">自动（{{ detectedMode === 'llm' ? 'LLM' : '要素池' }}）</option>
            <option value="llm">LLM（DeepSeek）</option>
            <option value="element_pool">要素池（本地）</option>
          </select>
        </label>
      </div>
    </header>

    <!-- 配置区域 -->
    <div class="card">
      <div class="card-title">1. 选择类别</div>
      <CategorySelector
        v-model="selectedCategories"
        :all-categories="allCategories"
      />
    </div>

    <div class="card" v-if="selectedCategories.length > 0">
      <div class="card-title">2. 权重分配</div>
      <WeightInput
        v-model="weights"
        :categories="selectedCategories"
      />
    </div>

    <div class="card" v-if="selectedCategories.length > 0">
      <div class="card-title">3. 生成设置</div>
      <div class="form-row">
        <CountInput v-model="totalCount" />
        <BatchPanel
          v-model:enabled="batchMode"
          v-model:fileCount="fileCount"
        />
        <div class="form-group">
          <label>Actor ID</label>
          <input
            v-model="actorId"
            type="text"
            placeholder="Skeleton0"
            class="actor-id-input"
          />
        </div>
      </div>
      <GenerateButton
        :disabled="!canGenerate"
        :loading="generating"
        :mode="mode"
        @generate="handleGenerate"
      />
    </div>

    <!-- 错误提示 -->
    <div v-if="errorMsg" class="error-state">
      {{ errorMsg }}
      <button class="btn-link" @click="errorMsg = ''" style="margin-left:10px">关闭</button>
    </div>

    <!-- 预览区域 -->
    <div class="card" v-if="generatedFiles.length > 0">
      <PreviewTable
        :files="generatedFiles"
        :active-index="activeTab"
        @update:activeIndex="activeTab = $event"
      />
      <div class="download-row">
        <DownloadButton
          :data="currentFileData"
          :filename="downloadFilename"
        />
        <button
          v-if="generatedFiles.length > 1"
          class="btn-download"
          @click="downloadAllZip"
        >
          📦 批量下载 ZIP
        </button>
      </div>
    </div>

    <!-- 空状态 -->
    <div class="card" v-if="generatedFiles.length === 0 && !generating">
      <div class="empty-state">
        选择类别，配置权重和条数，点击「生成 JSON」开始
      </div>
    </div>

    <!-- 加载状态 -->
    <div class="card" v-if="generating">
      <div class="loading-state">正在生成数据，请稍候...</div>
    </div>

    <!-- 导入区域 -->
    <div class="card">
      <div class="card-title">📥 导入 JSON</div>
      <ImportButton @imported="handleImported" />
    </div>

    <!-- 历史记录 -->
    <div class="card">
      <div class="card-title">📋 历史记录</div>
      <HistoryPanel
        ref="historyPanel"
        @regenerate="handleRegenerate"
      />
    </div>
  </div>
</template>

<script>
import { api } from './api/index.js'
import CategorySelector from './components/CategorySelector.vue'
import WeightInput from './components/WeightInput.vue'
import CountInput from './components/CountInput.vue'
import BatchPanel from './components/BatchPanel.vue'
import GenerateButton from './components/GenerateButton.vue'
import PreviewTable from './components/PreviewTable.vue'
import DownloadButton from './components/DownloadButton.vue'
import ImportButton from './components/ImportButton.vue'
import HistoryPanel from './components/HistoryPanel.vue'

const ALL_CATEGORIES = [
  '站立', '行走', '跑步', '跳跃',
  '下蹲', '特技', '舞蹈', '爬行',
  '单膝跪地', '互动', '挪动物品', '后退',
  '侧移', '踏步', '上肢动作(比心)', '其他',
]

export default {
  name: 'App',
  components: {
    CategorySelector, WeightInput, CountInput, BatchPanel,
    GenerateButton, PreviewTable, DownloadButton, ImportButton, HistoryPanel,
  },
  data() {
    return {
      mode: 'element_pool',
      generationMode: 'auto',
      allCategories: ALL_CATEGORIES,
      selectedCategories: [],
      weights: {},
      totalCount: 400,
      batchMode: false,
      fileCount: 5,
      actorId: 'Skeleton0',
      generating: false,
      errorMsg: '',
      generatedFiles: [],
      activeTab: 0,
      backendOffline: false,
      healthChecking: false,
      _healthTimer: null,
    }
  },
  computed: {
    detectedMode() {
      return this.mode
    },
    resolvedMode() {
      if (this.generationMode === 'auto') return this.mode
      return this.generationMode
    },
    canGenerate() {
      if (this.selectedCategories.length === 0) return false
      const totalWeight = this.selectedCategories.reduce(
        (sum, c) => sum + (this.weights[c] || 1), 0
      )
      return totalWeight > 0 && this.totalCount > 0
    },
    currentFileData() {
      const f = this.generatedFiles[this.activeTab]
      return f ? f.data : []
    },
    downloadFilename() {
      if (this.generatedFiles.length === 1) {
        return `actions_${this.generatedFiles[0].record_id.slice(0, 8)}.json`
      }
      const f = this.generatedFiles[this.activeTab]
      return f ? `actions_${f.record_id.slice(0, 8)}.json` : 'actions.json'
    },
  },
  async created() {
    await this.checkHealth()
    this._healthTimer = setInterval(() => this.checkHealth(), 10000)
  },
  beforeUnmount() {
    clearInterval(this._healthTimer)
  },
  methods: {
    async checkHealth() {
      this.healthChecking = true
      try {
        const s = await api.status()
        this.mode = s.mode
        this.backendOffline = false
      } catch (e) {
        this.backendOffline = true
      } finally {
        this.healthChecking = false
      }
    },

    async handleGenerate() {
      this.generating = true
      this.errorMsg = ''
      this.generatedFiles = []

      const categories = this.selectedCategories.map((name) => ({
        name,
        weight: this.weights[name] || 1,
      }))

      try {
        if (this.batchMode) {
          const res = await api.generateBatch({
            total_count: this.totalCount,
            file_count: this.fileCount,
            categories,
            actor_id: this.actorId,
          }, this.generationMode)
          if (res.success) {
            this.generatedFiles = res.files.map((f) => ({
              record_id: f.record_id,
              data: f.data,
              stats: f.stats,
            }))
            this.activeTab = 0
          } else {
            this.errorMsg = res.error || '生成失败'
          }
        } else {
          const res = await api.generate({
            total_count: this.totalCount,
            categories,
            actor_id: this.actorId,
          }, this.generationMode)
          if (res.success) {
            this.generatedFiles = [{
              record_id: res.record_id,
              data: res.data,
              stats: res.stats,
            }]
            this.activeTab = 0
          } else {
            this.errorMsg = res.error || '生成失败'
          }
        }
      } catch (e) {
        this.errorMsg = e.message || '网络请求失败，请确认后端已启动'
      } finally {
        this.generating = false
      }
    },

    handleImported(result) {
      if (result.success) {
        this.errorMsg = ''
      }
    },

    async handleRegenerate({ id, type }) {
      this.generating = true
      this.errorMsg = ''
      this.generatedFiles = []
      try {
        const res = await api.regenerate(id)
        if (res.success) {
          if (type === 'single') {
            this.generatedFiles = [{
              record_id: res.record_id,
              data: res.data,
              stats: res.stats,
            }]
          } else if (res.files) {
            this.generatedFiles = res.files.map((f) => ({
              record_id: f.record_id,
              data: f.data,
              stats: f.stats,
            }))
          }
          this.activeTab = 0
        } else {
          this.errorMsg = res.error || '重新生成失败'
        }
      } catch (e) {
        this.errorMsg = e.message || '请求失败'
      } finally {
        this.generating = false
        this.$refs.historyPanel?.refresh()
      }
    },

    async downloadAllZip() {
      try {
        const JSZip = (await import('jszip')).default
        const zip = new JSZip()
        for (const file of this.generatedFiles) {
          zip.file(
            `actions_${file.record_id.slice(0, 8)}.json`,
            JSON.stringify(file.data, null, 2)
          )
        }
        const blob = await zip.generateAsync({ type: 'blob' })
        const url = URL.createObjectURL(blob)
        const a = document.createElement('a')
        a.href = url
        a.download = `actions_batch_${this.generatedFiles.length}files.zip`
        a.click()
        URL.revokeObjectURL(url)
      } catch (e) {
        this.errorMsg = 'ZIP 打包失败：' + e.message
      }
    },
  },
}
</script>
