<template>
  <div>
    <div class="weight-list">
      <div v-for="cat in categories" :key="cat" class="weight-item">
        <label>{{ cat }}:</label>
        <input
          type="number"
          :value="getWeight(cat)"
          @input="setWeight(cat, $event.target.value)"
          min="1"
          step="1"
        />
      </div>
    </div>
    <div class="weight-preview" v-if="totalWeight > 0">
      预览: {{ previewText }}
    </div>
    <button class="btn-sm" @click="equalize">平均分配</button>
  </div>
</template>

<script>
export default {
  name: 'WeightInput',
  props: {
    modelValue: { type: Object, required: true },
    categories: { type: Array, required: true },
  },
  emits: ['update:modelValue'],
  computed: {
    totalWeight() {
      return this.categories.reduce((sum, c) => sum + this.getWeight(c), 0)
    },
    previewText() {
      return this.categories
        .map((c) => {
          const pct = Math.round((this.getWeight(c) / this.totalWeight) * 100)
          return `${c} ${pct}%`
        })
        .join(' / ')
    },
  },
  methods: {
    getWeight(cat) {
      return this.modelValue[cat] || 1
    },
    setWeight(cat, val) {
      const n = Math.max(1, parseInt(val) || 1)
      this.$emit('update:modelValue', { ...this.modelValue, [cat]: n })
    },
    equalize() {
      const next = {}
      this.categories.forEach((c) => { next[c] = 1 })
      this.$emit('update:modelValue', next)
    },
  },
}
</script>
