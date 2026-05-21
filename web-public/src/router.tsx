import { createBrowserRouter } from 'react-router'
import { App } from '@/App'
import { OfficeScene } from '@/pages/OfficeScene'
import { About } from '@/pages/About'
import { NotFoundPage } from '@/pages/NotFoundPage'

// Exactly two routes under <App />: index → OfficeScene, /about → About.
// Unknown paths resolve to the 404 boundary via errorElement (not a third
// catch-all route).
export const router = createBrowserRouter([
  {
    path: '/',
    element: <App />,
    errorElement: <NotFoundPage />,
    children: [
      { index: true, element: <OfficeScene /> },
      { path: 'about', element: <About /> },
    ],
  },
])
