<template>
  <div>
    <div v-if="loading" class="loading-state">加载历史记录...</div>
    <div v-else-if="records.length === 0" class="empty-state" style="padding:20px">
      暂无生成记录
    </div>
    <div v-else class="history-list">
      <div v-for="rec in records" :key="rec.id" class="history-item">
        <div>
          <div>{{ formatTime(rec.created_at) }}</div>
          <div class="history-meta">
            <span>{{ rec.total_records }} 条</span>
            <span>{{ rec.type === 'batch' ? `批量 ×${rec.file_count}` : '单次' }}</span>
            <span>{{ categorySummary(rec.categories_json) }}</span>
          </div>
        </div>
        <div class="history-actions">
          <button class="btn-sm" @click="regenerate(rec)">重新生成</button>
          <button class="btn-sm" @click="remove(rec.id)">删除</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script>
import { api } from '../api/index.js'

export default {
  name: 'HistoryPanel',
  emits: ['regenerate'],
  data() {
    return { records: [], loading: false }
  },
  created() {
    this.refresh()
  },
  methods: {
    async refresh() {
      this.loading = true
      try {
        const res = await api.history()
        this.records = res.data || []
      } catch (e) {
        // 忽略
      } finally {
        this.loading = false
      }
    },
    formatTime(iso) {
      try {
        const d = new Date(iso)
        const pad = (n) => String(n).padStart(2, '0')
        return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`
      } catch {
        return iso
      }
    },
    categorySummary(json) {
      try {
        const cats = JSON.parse(json)
        return cats.map((c) => c.name).join('、')
      } catch {
        return ''
      }
    },
    async remove(id) {
      try {
        await api.deleteHistory(id)
        this.records = this.records.filter((r) => r.id !== id)
      } catch (e) {
        // 忽略
      }
    },
    regenerate(rec) {
      this.$emit('regenerate', { id: rec.id, type: rec.type })
    },
  },
}
</script>
