<template>
  <div>
    <div class="category-grid">
      <label
        v-for="cat in allCategories"
        :key="cat"
        :class="['category-item', { checked: isSelected(cat) }]"
      >
        <input
          type="checkbox"
          :value="cat"
          :checked="isSelected(cat)"
          @change="toggle(cat)"
        />
        {{ cat }}
      </label>
    </div>
    <div class="select-actions">
      <button class="btn-link" @click="selectAll">全选</button>
      <button class="btn-link" @click="deselectAll">取消全选</button>
    </div>
  </div>
</template>

<script>
export default {
  name: 'CategorySelector',
  props: {
    modelValue: { type: Array, required: true },
    allCategories: { type: Array, required: true },
  },
  emits: ['update:modelValue'],
  methods: {
    isSelected(cat) {
      return this.modelValue.includes(cat)
    },
    toggle(cat) {
      const next = this.isSelected(cat)
        ? this.modelValue.filter((c) => c !== cat)
        : [...this.modelValue, cat]
      this.$emit('update:modelValue', next)
    },
    selectAll() {
      this.$emit('update:modelValue', [...this.allCategories])
    },
    deselectAll() {
      this.$emit('update:modelValue', [])
    },
  },
}
</script>
