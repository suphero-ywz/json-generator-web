<template>
  <div>
    <label class="batch-toggle">
      <input type="checkbox" :checked="enabled" @change="toggleBatch" />
      启用批量生成
    </label>
    <div v-if="enabled" class="form-group" style="margin-top:8px">
      <label>文件个数:</label>
      <input
        type="number"
        :value="fileCount"
        @input="handleFileCount"
        min="1"
        max="50"
      />
    </div>
  </div>
</template>

<script>
export default {
  name: 'BatchPanel',
  props: {
    enabled: { type: Boolean, default: false },
    fileCount: { type: Number, default: 5 },
  },
  emits: ['update:enabled', 'update:fileCount'],
  methods: {
    toggleBatch(e) {
      this.$emit('update:enabled', e.target.checked)
    },
    handleFileCount(e) {
      let n = parseInt(e.target.value) || 1
      n = Math.max(1, Math.min(50, n))
      this.$emit('update:fileCount', n)
    },
  },
}
</script>
