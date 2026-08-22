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
        <span :class="['mode-badge', backendOffline ? 'offline' : (generationMode === 'llm' ? 'llm' : 'pool')]">
          {{ backendOffline ? '🔴 未连接' : (generationMode === 'llm' ? `🟢 LLM · ${currentProviderModel}` : '🟡 要素池模式') }}
        </span>
        <label class="mode-toggle" v-if="!backendOffline">
          <span class="toggle-label">生成模式：</span>
          <select v-model="generationMode" class="mode-select">
            <option value="llm">LLM 模式</option>
            <option value="element_pool">要素池模式</option>
          </select>
        </label>
        <label class="mode-toggle" v-if="!backendOffline && generationMode === 'llm' && availableProviders.length > 0">
          <span class="toggle-label">大模型：</span>
          <select v-model="provider" class="mode-select">
            <option
              v-for="p in availableProviders"
              :key="p.id"
              :value="p.id"
            >
              {{ p.label }} · {{ p.model }}{{ p.online ? '' : '（离线）' }}
            </option>
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
          v-model:filenamePrefix="filenamePrefix"
          :date-placeholder="dateString"
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
        :disabled="!canGenerate || generating"
        :loading="generating"
        :mode="mode"
        @generate="handleGenerate"
      />
      <button
        v-if="generating"
        class="btn-stop"
        @click="stopGenerate"
      >
        🛑 停止生成
      </button>
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
      <div class="loading-state">
        正在生成数据，请稍候...（已等待 {{ elapsedStr }}）
        <ProgressBar
          :completed="progress.completed"
          :total="progress.total"
          :files-done="progress.filesDone"
          :files-total="progress.filesTotal"
        />
        <div class="loading-hint">LLM 模式下每条约 20-30 秒，条数较多时请耐心等待或点击「停止生成」</div>
      </div>
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
import ProgressBar from './components/ProgressBar.vue'

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
    ProgressBar,
  },
  data() {
    return {
      mode: 'element_pool',
      generationMode: 'element_pool',
      allCategories: ALL_CATEGORIES,
      selectedCategories: [],
      weights: {},
      totalCount: 400,
      batchMode: false,
      fileCount: 5,
      filenamePrefix: '',
      actorId: 'Skeleton0',
      generating: false,
      errorMsg: '',
      generatedFiles: [],
      activeTab: 0,
      backendOffline: false,
      modelName: '',
      provider: 'auto',
      providers: [],
      healthChecking: false,
      elapsedSeconds: 0,
      progress: { completed: 0, total: 0, filesDone: 0, filesTotal: 0 },
      _healthTimer: null,
      _abortController: null,
      _currentTaskId: null,
      _modeInitialized: false,
      _elapsedTimer: null,
      _progressTimer: null,
    }
  },
  computed: {
    availableProviders() {
      // 仅显示已配置的 LLM 后端
      return this.providers.filter((p) => p.available)
    },
    currentProvider() {
      return this.providers.find((p) => p.id === this.provider) || null
    },
    currentProviderModel() {
      if (this.currentProvider) {
        return this.currentProvider.model
      }
      return this.modelName || 'LLM'
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
    dateString() {
      const d = new Date()
      const y = d.getFullYear()
      const m = String(d.getMonth() + 1).padStart(2, '0')
      const day = String(d.getDate()).padStart(2, '0')
      return `${y}${m}${day}`
    },
    baseFilename() {
      return this.filenamePrefix || this.dateString
    },
    elapsedStr() {
      const m = Math.floor(this.elapsedSeconds / 60)
      const s = this.elapsedSeconds % 60
      return m > 0 ? `${m} 分 ${s} 秒` : `${s} 秒`
    },
    downloadFilename() {
      if (this.generatedFiles.length === 1) {
        return `${this.baseFilename}.json`
      }
      const f = this.generatedFiles[this.activeTab]
      if (!f) return `${this.baseFilename}.json`
      const idx = this.activeTab + 1
      return `${this.baseFilename}_${String(idx).padStart(2, '0')}.json`
    },
  },
  async created() {
    await this.checkHealth()
    this._healthTimer = setInterval(() => this.checkHealth(), 10000)
    // 页面刷新/关闭时通知后端取消生成（卸载阶段 fetch 不可靠，用 sendBeacon）
    window.addEventListener('pagehide', this._handlePageUnload)
  },
  beforeUnmount() {
    clearInterval(this._healthTimer)
    this._stopProgressPoll()
    window.removeEventListener('pagehide', this._handlePageUnload)
  },
  methods: {
    _newTaskId() {
      // crypto.randomUUID 仅在安全上下文可用，非 localhost 部署时回退
      if (window.crypto && crypto.randomUUID) {
        return crypto.randomUUID()
      }
      return `task-${Date.now()}-${Math.random().toString(36).slice(2)}`
    },

    /** 页面卸载（刷新/关闭/回收）时用 sendBeacon 取消后端生成任务 */
    _handlePageUnload() {
      if (!this.generating || !this._currentTaskId) return
      const body = new Blob(
        [JSON.stringify({ task_id: this._currentTaskId })],
        { type: 'application/json' },
      )
      navigator.sendBeacon('/api/generate/cancel', body)
    },

    /** 开始一次生成：创建取消控制器并记录 task_id */
    _beginTask() {
      const controller = new AbortController()
      const taskId = this._newTaskId()
      this._abortController = controller
      this._currentTaskId = taskId
      return { signal: controller.signal, taskId }
    },

    /** 清理取消控制器 */
    _endTask() {
      this._abortController = null
      this._currentTaskId = null
    },

    _startElapsed() {
      this.elapsedSeconds = 0
      this._elapsedTimer = setInterval(() => {
        this.elapsedSeconds += 1
      }, 1000)
    },

    _stopElapsed() {
      if (this._elapsedTimer) {
        clearInterval(this._elapsedTimer)
        this._elapsedTimer = null
      }
    },

    /** 开始进度轮询（每 1.5s 查询一次后端进度） */
    _startProgressPoll() {
      this._stopProgressPoll()
      this.progress = { completed: 0, total: 0, filesDone: 0, filesTotal: 0 }
      this._progressTimer = setInterval(() => this._pollProgress(), 1500)
    },

    /** 查询一次进度；后端返回 success:false 表示任务已结束，停止轮询 */
    _pollProgress() {
      if (!this._currentTaskId) return
      api.progress(this._currentTaskId)
        .then((res) => {
          if (res.success) {
            this.progress = {
              completed: res.completed || 0,
              total: res.total || 0,
              filesDone: res.files_done || 0,
              filesTotal: res.files_total || 0,
            }
          } else {
            this._stopProgressPoll()
          }
        })
        .catch(() => { /* 后端暂时不可达，忽略本轮，下轮再试 */ })
    },

    _stopProgressPoll() {
      if (this._progressTimer) {
        clearInterval(this._progressTimer)
        this._progressTimer = null
      }
    },

    stopGenerate() {
      if (!this.generating) return
      // 通知后端停止任务（后端会中断后续 LLM 调用）
      if (this._currentTaskId) {
        api.cancelGenerate(this._currentTaskId).catch(() => {})
      }
      // 中止前端请求，立即恢复界面
      if (this._abortController) {
        this._abortController.abort()
      }
      this.generating = false
      this.errorMsg = '已停止生成'
      this._stopElapsed()
      this._stopProgressPoll()
      this._endTask()
    },

    async checkHealth() {
      this.healthChecking = true
      try {
        const s = await api.status()
        this.mode = s.mode
        this.modelName = s.model || ''
        this.providers = s.providers || []
        this.backendOffline = false
        // 首次连接成功后：按后端状态初始化模式与大模型（之后尊重用户手动选择）
        if (!this._modeInitialized) {
          this._modeInitialized = true
          this.generationMode = s.mode === 'llm' ? 'llm' : 'element_pool'
          const first = this.availableProviders[0]
          if (first) this.provider = first.id
        }
      } catch (e) {
        this.backendOffline = true
        this.modelName = ''
        this.providers = []
      } finally {
        this.healthChecking = false
      }
    },

    async handleGenerate() {
      if (this.generating) return
      this.generating = true
      this.errorMsg = ''
      this.generatedFiles = []
      this._startElapsed()

      const opts = this._beginTask()
      this._startProgressPoll()
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
            provider: this.provider,
          }, this.generationMode, opts)
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
            provider: this.provider,
          }, this.generationMode, opts)
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
        if (e.name === 'AbortError') {
          this.errorMsg = '已停止生成'
        } else {
          this.errorMsg = e.message || '网络请求失败，请确认后端已启动'
        }
      } finally {
        this.generating = false
        this._stopElapsed()
        this._stopProgressPoll()
        this._endTask()
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
      this._startElapsed()
      const opts = this._beginTask()
      this._startProgressPoll()
      try {
        const res = await api.regenerate(id, { ...opts, provider: this.provider })
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
        if (e.name === 'AbortError') {
          this.errorMsg = '已停止生成'
        } else {
          this.errorMsg = e.message || '请求失败'
        }
      } finally {
        this.generating = false
        this._stopElapsed()
        this._stopProgressPoll()
        this._endTask()
        this.$refs.historyPanel?.refresh()
      }
    },

    async downloadAllZip() {
      try {
        const JSZip = (await import('jszip')).default
        const zip = new JSZip()
        this.generatedFiles.forEach((file, i) => {
          zip.file(
            `${this.baseFilename}_${String(i + 1).padStart(2, '0')}.json`,
            JSON.stringify(file.data, null, 2)
          )
        })
        const blob = await zip.generateAsync({ type: 'blob' })
        const url = URL.createObjectURL(blob)
        const a = document.createElement('a')
        a.href = url
        a.download = `${this.baseFilename}.zip`
        a.click()
        URL.revokeObjectURL(url)
      } catch (e) {
        this.errorMsg = 'ZIP 打包失败：' + e.message
      }
    },
  },
}
</script>
