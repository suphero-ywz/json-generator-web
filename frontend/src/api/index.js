const BASE = '/api'

async function request(url, options = {}) {
  const res = await fetch(BASE + url, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }))
    throw new Error(err.detail || `请求失败 (${res.status})`)
  }
  return res.json()
}

export const api = {
  /** 检查生成模式 */
  status() {
    return request('/status')
  },

  /** 单次生成 */
  generate(data, mode) {
    return request('/generate', {
      method: 'POST',
      body: JSON.stringify({ ...data, mode }),
    })
  },

  /** 批量生成 */
  generateBatch(data, mode) {
    return request('/generate/batch', {
      method: 'POST',
      body: JSON.stringify({ ...data, mode }),
    })
  },

  /** 历史记录 */
  history() {
    return request('/history')
  },

  /** 删除历史 */
  deleteHistory(id) {
    return request(`/history/${encodeURIComponent(id)}`, { method: 'DELETE' })
  },

  /** 重新生成 */
  regenerate(id) {
    return request(`/history/${encodeURIComponent(id)}/regenerate`, { method: 'POST' })
  },

  /** 导入 JSON */
  importFile(file) {
    const formData = new FormData()
    formData.append('file', file)
    return fetch(BASE + '/import', { method: 'POST', body: formData }).then((r) => r.json())
  },

  /** 去重池统计 */
  poolStats() {
    return request('/query-pool/stats')
  },
}
