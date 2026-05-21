/// <reference types="vitest/config" />
import { mergeConfig } from 'vitest/config'
import { defineConfig } from 'vite'
import viteConfig from './vite.config'

export default mergeConfig(
  viteConfig,
  defineConfig({
    test: {
      environment: 'jsdom',
      globals: true,
      setupFiles: ['./src/test/setup.ts'],
      css: true,
      exclude: ['node_modules/**', 'dist/**', 'e2e/**'],
    },
  }),
)
