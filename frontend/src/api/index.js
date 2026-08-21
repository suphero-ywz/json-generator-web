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

  /** 单次生成（opts.taskId 用于取消，opts.signal 用于中止请求） */
  generate(data, mode, opts = {}) {
    return request('/generate', {
      method: 'POST',
      body: JSON.stringify({ ...data, mode, task_id: opts.taskId }),
      signal: opts.signal,
    })
  },

  /** 批量生成（opts.taskId 用于取消，opts.signal 用于中止请求） */
  generateBatch(data, mode, opts = {}) {
    return request('/generate/batch', {
      method: 'POST',
      body: JSON.stringify({ ...data, mode, task_id: opts.taskId }),
      signal: opts.signal,
    })
  },

  /** 取消进行中的生成任务 */
  cancelGenerate(taskId) {
    return request('/generate/cancel', {
      method: 'POST',
      body: JSON.stringify({ task_id: taskId }),
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

  /** 重新生成（opts.taskId 用于取消，opts.signal 用于中止请求，opts.provider 指定后端） */
  regenerate(id, opts = {}) {
    const params = new URLSearchParams()
    if (opts.taskId) params.set('task_id', opts.taskId)
    if (opts.provider) params.set('provider', opts.provider)
    const q = params.toString() ? `?${params}` : ''
    return request(`/history/${encodeURIComponent(id)}/regenerate${q}`, {
      method: 'POST',
      signal: opts.signal,
    })
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
