import { Authenticator, useTheme, View, Image, Text, Heading } from '@aws-amplify/ui-react';
import FeedbackForm from './components/FeedbackForm';

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
        <div className="app">
          <header className="header">
            <span className="logo">
              Feedback <span style={{ color: '#2563eb' }}>AI</span>
            </span>
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
              <span className="header-email">{user?.signInDetails?.loginId}</span>
              <button className="btn-ghost" onClick={signOut}>
                Sign out
              </button>
            </div>
          </header>
          <main className="main">
            <FeedbackForm />
          </main>
        </div>
      )}
    </Authenticator>
  );
}
