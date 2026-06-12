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
      // Unit tests live under src/ only — without this Vitest's default
      // glob also picks up e2e/*.spec.ts (Playwright files) and fails.
      include: ['src/**/*.{test,spec}.{ts,tsx}'],
    },
  }),
)
