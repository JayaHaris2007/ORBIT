import { BrowserRouter as Router, Routes, Route } from 'react-router-dom';
import { AuthProvider } from './context/AuthContext';
import { AppDataProvider } from './context/AppDataContext';
import { SpideyBrainProvider } from './context/SpideyBrainContext';
import ErrorBoundary from './components/ErrorBoundary';
import SpideyWorkspace from './pages/SpideyWorkspace';

function App() {
    return (
        <AuthProvider>
            <AppDataProvider>
                <SpideyBrainProvider>
                    <Router>
                        <ErrorBoundary>
                            <Routes>
                                <Route path="/*" element={<SpideyWorkspace />} />
                            </Routes>
                        </ErrorBoundary>
                    </Router>
                </SpideyBrainProvider>
            </AppDataProvider>
        </AuthProvider>
    );
}

export default App;
