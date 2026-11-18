import { lazy, Suspense } from 'react';
import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom';
import { AuthProvider, useTheme } from './context/AuthContext';
import { AppDataProvider } from './context/AppDataContext';
import { SpideyBrainProvider } from './context/SpideyBrainContext';
import Navbar from './components/Navbar';
import ErrorBoundary from './components/ErrorBoundary';
import AssistantSidebar from './components/AssistantSidebar';
import ParallaxStage from './components/ParallaxStage';
import ScrollProgressLine from './components/ScrollProgressLine';

const Dashboard = lazy(() => import('./pages/Dashboard'));
const Habits = lazy(() => import('./pages/Habits'));
const Todos = lazy(() => import('./pages/Todos'));
const Analytics = lazy(() => import('./pages/Analytics'));
const Settings = lazy(() => import('./pages/Settings'));
const RemindersMemory = lazy(() => import('./pages/RemindersMemory'));
const Learning = lazy(() => import('./pages/Learning'));
const SpideyCrawlerOverlay = lazy(() => import('./components/three/SpideyCrawlerOverlay'));

const AppLayout = ({ children }) => {
    const { theme } = useTheme();
    return <div className={`app-theme-${theme} min-h-screen bg-background text-text font-sans flex flex-col md:flex-row app-frame`}>
        <div aria-hidden="true" className="spidey-paper-grain" />
        <ScrollProgressLine />
        <Navbar />
        <div className="app-main-shell flex-1 md:ml-64 min-w-0 transition-all duration-200 flex flex-col">
            <ParallaxStage>
                <Suspense fallback={<div className="p-8 text-xs font-mono text-textMuted uppercase tracking-widest">Loading module...</div>}>
                    {children}
                </Suspense>
            </ParallaxStage>
        </div>
        {/* S.P.I.D.E.Y is docked on the right on every page */}
        <AssistantSidebar />
        <Suspense fallback={null}>
            <SpideyCrawlerOverlay />
        </Suspense>
    </div>;
};

function App() {
    return (
        <AuthProvider>
            <AppDataProvider>
                <SpideyBrainProvider>
                    <Router>
                        <Routes>
                            <Route path="/" element={<Navigate to="/dashboard" replace />} />
                            <Route path="/dashboard" element={<AppLayout><Dashboard /></AppLayout>} />
                            <Route path="/habits" element={<AppLayout><Habits /></AppLayout>} />
                            <Route path="/todos" element={<AppLayout><Todos /></AppLayout>} />
                            <Route path="/reminders" element={<AppLayout><RemindersMemory /></AppLayout>} />
                            <Route path="/learning" element={<AppLayout><ErrorBoundary><Learning /></ErrorBoundary></AppLayout>} />
                            <Route path="/analytics" element={<AppLayout><Analytics /></AppLayout>} />
                            <Route path="/settings" element={<AppLayout><Settings /></AppLayout>} />
                            <Route path="/tasks" element={<Navigate to="/todos" replace />} />
                            <Route path="/memories" element={<Navigate to="/reminders" replace />} />
                            <Route path="/notes" element={<Navigate to="/reminders" replace />} />
                            <Route path="*" element={<Navigate to="/dashboard" replace />} />
                        </Routes>
                    </Router>
                </SpideyBrainProvider>
            </AppDataProvider>
        </AuthProvider>
    );
}

export default App;
