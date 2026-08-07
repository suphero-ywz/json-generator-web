<template>
  <div>
    <!-- 标签页（批量时显示） -->
    <div class="preview-header">
      <div class="tabs" v-if="files.length > 1">
        <button
          v-for="(f, i) in files"
          :key="f.record_id"
          :class="['tab', { active: activeIndex === i }]"
          @click="$emit('update:activeIndex', i)"
        >
          文件 {{ i + 1 }} ({{ f.data.length }}条)
        </button>
      </div>
      <div style="font-size:0.85rem;color:var(--text-secondary)" v-else>
        共 {{ currentFile.data.length }} 条记录
      </div>
    </div>

    <!-- 筛选 -->
    <div class="preview-filters">
      <select v-model="filterCategory">
        <option value="">全部类别</option>
        <option v-for="cat in categories" :key="cat" :value="cat">{{ cat }}</option>
      </select>
      <input
        v-model="searchQuery"
        type="text"
        placeholder="搜索 query / text..."
      />
    </div>

    <!-- 表格 -->
    <div class="table-wrapper">
      <table>
        <thead>
          <tr>
            <th>序号</th>
            <th>query</th>
            <th>query_description</th>
            <th>category</th>
            <th>is_head</th>
            <th>motion_description</th>
            <th>text</th>
            <th>voice_feedback</th>
            <th>aug_text</th>
          </tr>
        </thead>
        <tbody>
          <tr v-if="pagedData.length === 0">
            <td colspan="9" style="text-align:center;padding:24px;color:var(--text-secondary)">
              暂无数据
            </td>
          </tr>
          <tr v-for="(row, i) in pagedData" :key="i">
            <td>{{ (page - 1) * pageSize + i + 1 }}</td>
            <td>{{ row.query }}</td>
            <td class="text-col" :title="row.query_description">{{ row.query_description }}</td>
            <td>{{ row.category }}</td>
            <td>{{ row.is_head ? 'TRUE' : 'FALSE' }}</td>
            <td class="text-col" :title="row.motion_description">{{ row.motion_description }}</td>
            <td class="text-col" :title="row.text">{{ row.text }}</td>
            <td>{{ row.voice_feedback }}</td>
            <td class="text-col">{{ (row.aug_text || []).length }} 条变体</td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- 分页 -->
    <div class="pagination" v-if="totalPages > 1">
      <button class="btn-page" :disabled="page <= 1" @click="page--">上一页</button>
      <span>第 {{ page }}/{{ totalPages }} 页</span>
      <button class="btn-page" :disabled="page >= totalPages" @click="page++">下一页</button>
    </div>
  </div>
</template>

<script>
export default {
  name: 'PreviewTable',
  props: {
    files: { type: Array, required: true },
    activeIndex: { type: Number, default: 0 },
  },
  emits: ['update:activeIndex'],
  data() {
    return {
      filterCategory: '',
      searchQuery: '',
      page: 1,
      pageSize: 20,
    }
  },
  computed: {
    currentFile() {
      return this.files[this.activeIndex] || { data: [], stats: {} }
    },
    categories() {
      return Object.keys(this.currentFile.stats || {})
    },
    filteredData() {
      let data = this.currentFile.data
      if (this.filterCategory) {
        data = data.filter((r) => r.category === this.filterCategory)
      }
      if (this.searchQuery) {
        const q = this.searchQuery.toLowerCase()
        data = data.filter(
          (r) =>
            r.query.toLowerCase().includes(q) ||
            r.text.toLowerCase().includes(q) ||
            (r.query_description || '').toLowerCase().includes(q) ||
            (r.motion_description || '').toLowerCase().includes(q)
        )
      }
      return data
    },
    totalPages() {
      return Math.max(1, Math.ceil(this.filteredData.length / this.pageSize))
    },
    pagedData() {
      const start = (this.page - 1) * this.pageSize
      return this.filteredData.slice(start, start + this.pageSize)
    },
  },
  watch: {
    filterCategory() { this.page = 1 },
    searchQuery() { this.page = 1 },
    activeIndex() { this.page = 1 },
  },
}
</script>
