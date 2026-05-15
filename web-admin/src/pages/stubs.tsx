/**
 * All web-admin page stubs have shipped — this file is intentionally empty.
 *
 * Historically this module re-exported `<ComingSoon>` placeholders for
 * any page whose backend wasn't yet built. As of admin-chat-sessions-
 * endpoints-and-pages, every admin route resolves to a real page, so
 * there is nothing left to stub.
 *
 * Keeping the file (rather than deleting it) preserves the import path
 * for any future regression that wants to ship a temporary placeholder
 * — just re-add `import { ComingSoon } from '@/components/ComingSoon'`
 * and export a `make(...)` view.
 */

export {}
