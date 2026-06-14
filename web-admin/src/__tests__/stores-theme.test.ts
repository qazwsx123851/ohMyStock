import { beforeEach, describe, expect, it } from 'vitest'
import { useUiStore } from '@/stores'

const THEME_KEY = 'ohmystock.admin.theme'

describe('useUiStore theme', () => {
  beforeEach(() => {
    localStorage.clear()
    document.documentElement.classList.remove('dark')
    // reset to a known state (default dark)
    useUiStore.setState({ theme: 'dark' })
  })

  it('toggleTheme flips dark -> light: state, localStorage, and <html> class', () => {
    useUiStore.getState().toggleTheme()

    expect(useUiStore.getState().theme).toBe('light')
    expect(localStorage.getItem(THEME_KEY)).toBe('light')
    expect(document.documentElement.classList.contains('dark')).toBe(false)
  })

  it('toggleTheme flips light -> dark: state, localStorage, and <html> class', () => {
    useUiStore.setState({ theme: 'light' })

    useUiStore.getState().toggleTheme()

    expect(useUiStore.getState().theme).toBe('dark')
    expect(localStorage.getItem(THEME_KEY)).toBe('dark')
    expect(document.documentElement.classList.contains('dark')).toBe(true)
  })
})
