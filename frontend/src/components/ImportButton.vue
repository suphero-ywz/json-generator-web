<template>
  <div>
    <div class="import-row">
      <button class="btn-sm" @click="$refs.fileInput.click()">
        选择 JSON 文件
      </button>
      <span class="file-input-wrapper">
        <input
          ref="fileInput"
          type="file"
          accept=".json"
          @change="handleFile"
        />
      </span>
      <span v-if="loading" style="font-size:0.85rem;color:var(--text-secondary)">
        导入中...
      </span>
      <span style="font-size:0.85rem;color:var(--text-secondary)">
        导入的 query 自动进入去重池
      </span>
    </div>
    <div v-if="result" class="import-result" :style="{ color: result.success ? 'var(--success)' : 'var(--danger)' }">
      <template v-if="result.success">
        ✓ 导入完成：新增 {{ result.imported_count }} 条，跳过 {{ result.skipped_count }} 条重复
      </template>
      <template v-else>
        ✗ {{ result.error || '导入失败' }}
      </template>
    </div>
  </div>
</template>

<script>
import { api } from '../api/index.js'

export default {
  name: 'ImportButton',
  emits: ['imported'],
  data() {
    return { loading: false, result: null }
  },
  methods: {
    async handleFile(e) {
      const file = e.target.files[0]
      if (!file) return
      this.loading = true
      this.result = null
      try {
        this.result = await api.importFile(file)
        this.$emit('imported', this.result)
      } catch (err) {
        this.result = { success: false, error: err.message }
      } finally {
        this.loading = false
        e.target.value = ''
      }
    },
  },
}
</script>
