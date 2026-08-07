<template>
  <div class="form-group">
    <label>单文件条数:</label>
    <input
      type="number"
      :value="modelValue"
      @input="handleInput"
      min="1"
      max="50000"
    />
  </div>
</template>

<script>
export default {
  name: 'CountInput',
  props: {
    modelValue: { type: Number, required: true },
  },
  emits: ['update:modelValue'],
  methods: {
    handleInput(e) {
      let n = parseInt(e.target.value) || 1
      n = Math.max(1, Math.min(50000, n))
      this.$emit('update:modelValue', n)
    },
  },
}
</script>
