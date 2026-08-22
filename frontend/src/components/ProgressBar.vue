<template>
  <div v-if="total > 0" class="progress-wrap">
    <div class="progress-track">
      <div class="progress-fill" :style="{ width: pct + '%' }"></div>
    </div>
    <div class="progress-text">
      <span>{{ displayCompleted }} / {{ total }} 条（{{ pct }}%）</span>
      <span v-if="filesTotal > 0">文件 {{ displayFilesDone }} / {{ filesTotal }}</span>
    </div>
  </div>
</template>

<script>
export default {
  name: 'ProgressBar',
  props: {
    completed: { type: Number, default: 0 },
    total: { type: Number, default: 0 },
    filesDone: { type: Number, default: 0 },
    filesTotal: { type: Number, default: 0 },
  },
  computed: {
    // 放宽补全轮可能超量（如 402/400），封顶避免 UI 溢出
    pct() {
      return this.total > 0 ? Math.min(100, Math.round((this.completed / this.total) * 100)) : 0
    },
    displayCompleted() {
      return Math.min(this.completed, this.total)
    },
    displayFilesDone() {
      return Math.min(this.filesDone, this.filesTotal)
    },
  },
}
</script>
