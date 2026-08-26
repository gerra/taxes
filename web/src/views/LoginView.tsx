export default function LoginView() {
  const denied = new URLSearchParams(window.location.search).get('denied')
  return (
    <div className="center-page">
      <div className="login-card">
        <h1>taxes.gerra.sh</h1>
        <p>UK Self Assessment investment figures, explained.</p>
        {denied && (
          <p className="error-text">
            {denied} isn’t on the allowed list — this is a private instance.
          </p>
        )}
        <a className="btn primary" href="/oauth/google/start">
          Sign in with Google
        </a>
      </div>
    </div>
  )
}
