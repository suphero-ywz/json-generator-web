<template>
  <button
    class="btn-generate"
    :disabled="disabled"
    @click="$emit('generate')"
  >
    {{ loading ? '⏳ 生成中...' : '🚀 生成 JSON' }}
  </button>
</template>

<script>
export default {
  name: 'GenerateButton',
  props: {
    disabled: { type: Boolean, default: false },
    loading: { type: Boolean, default: false },
    mode: { type: String, default: 'element_pool' },
  },
  emits: ['generate'],
}
</script>
