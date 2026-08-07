<template>
  <button class="btn-download" @click="download" :disabled="!data || data.length === 0">
    ⬇ 下载 JSON
  </button>
</template>

<script>
export default {
  name: 'DownloadButton',
  props: {
    data: { type: Array, default: () => [] },
    filename: { type: String, default: 'actions.json' },
  },
  methods: {
    download() {
      if (!this.data || this.data.length === 0) return
      const blob = new Blob([JSON.stringify(this.data, null, 2)], {
        type: 'application/json',
      })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = this.filename
      a.click()
      URL.revokeObjectURL(url)
    },
  },
}
</script>
