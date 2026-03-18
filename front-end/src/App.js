import { BrowserRouter, Routes, Route, NavLink, Navigate } from 'react-router-dom';
import { Authenticator, useTheme, View, Text, Heading } from '@aws-amplify/ui-react';
import FeedbackForm from './components/FeedbackForm';
import RecommendationsPage from './pages/RecommendationsPage';

const components = {
  Header() {
    const { tokens } = useTheme();
    return (
      <View textAlign="center" padding={tokens.space.large}>
        <Heading level={4} style={{ color: '#1e293b', fontWeight: 600 }}>
          Feedback <span style={{ color: '#2563eb' }}>AI</span>
        </Heading>
        <Text style={{ color: '#64748b', fontSize: '0.85rem', marginTop: '0.25rem' }}>
          Turn manager feedback into a career action plan
        </Text>
      </View>
    );
  },
};

const formFields = {
  signIn: {
    username: { label: 'Email', placeholder: 'your@email.com' },
  },
  signUp: {
    username: { label: 'Email', placeholder: 'your@email.com', order: 1 },
    password: { label: 'Password', order: 2 },
    confirm_password: { label: 'Confirm password', order: 3 },
  },
};

export default function App() {
  return (
    <Authenticator components={components} formFields={formFields}>
      {({ signOut, user }) => (
        <BrowserRouter>
          <div className="app">
            {/* ── Top header ── */}
            <header className="header">
              <span className="logo">
                Feedback <span style={{ color: '#2563eb' }}>AI</span>
              </span>
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
                <span className="header-email">{user?.signInDetails?.loginId}</span>
                <button className="btn-ghost" onClick={signOut}>Sign out</button>
              </div>
            </header>

            {/* ── Navigation tabs ── */}
            <nav className="nav-tabs">
              <NavLink
                to="/submit"
                className={({ isActive }) => 'nav-tab' + (isActive ? ' nav-tab--active' : '')}
              >
                ✏ Submit Feedback
              </NavLink>
              <NavLink
                to="/recommendations"
                className={({ isActive }) => 'nav-tab' + (isActive ? ' nav-tab--active' : '')}
              >
                📋 My Recommendations
              </NavLink>
            </nav>

            {/* ── Page content ── */}
            <main className="main">
              <Routes>
                <Route path="/submit"          element={<FeedbackForm />} />
                <Route path="/recommendations" element={<RecommendationsPage />} />
                {/* Default redirect to submit page */}
                <Route path="*" element={<Navigate to="/submit" replace />} />
              </Routes>
            </main>
          </div>
        </BrowserRouter>
      )}
    </Authenticator>
  );
}
