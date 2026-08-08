import pluginVue from 'eslint-plugin-vue'

export default [
  ...pluginVue.configs['flat/essential'],
  {
    rules: {
      'vue/no-reserved-keys': 'off',
    },
    languageOptions: {
      ecmaVersion: 'latest',
      sourceType: 'module',
      globals: {
        window: 'readonly',
        document: 'readonly',
        fetch: 'readonly',
        URL: 'readonly',
        Blob: 'readonly',
        FileReader: 'readonly',
        FormData: 'readonly',
        HTMLElement: 'readonly',
        setTimeout: 'readonly',
        clearInterval: 'readonly',
        setInterval: 'readonly',
      },
    },
  },
]
