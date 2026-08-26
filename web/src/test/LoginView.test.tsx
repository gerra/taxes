import { render, screen } from '@testing-library/react'
import LoginView from '../views/LoginView'

test('renders Google sign-in link', () => {
  render(<LoginView />)
  const link = screen.getByRole('link', { name: /sign in with google/i })
  expect(link).toHaveAttribute('href', '/oauth/google/start')
})
