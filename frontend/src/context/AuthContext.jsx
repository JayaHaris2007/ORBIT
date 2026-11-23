import { createContext, useContext, useMemo, useState } from 'react';

const AuthContext = createContext(null);
const ThemeContext = createContext(null);

// eslint-disable-next-line react-refresh/only-export-components
export function useAuth() {
    return useContext(AuthContext);
}

// eslint-disable-next-line react-refresh/only-export-components
export function useTheme() {
    return useContext(ThemeContext);
}

export function AuthProvider({ children }) {
    const [theme, setTheme] = useState(
        () => localStorage.getItem('spidey_theme') || localStorage.getItem('kage_theme') || 'dark'
    );
    const [displayName, setDisplayName] = useState(
        () => localStorage.getItem('spidey_display_name') || 'Shadow Hunter'
    );

    const value = useMemo(() => ({
        currentUser: { uid: 'local-user', displayName },
        loading: false,
        updateDisplayName: (nextName) => {
            const clean = String(nextName || '').trim() || 'Shadow Hunter';
            try {
                localStorage.setItem('spidey_display_name', clean);
            } catch { /* ignore */ }
            setDisplayName(clean);
        },
        logout: () => {},
    }), [displayName]);

    const themeValue = useMemo(() => ({
        theme,
        setTheme: (nextTheme) => {
            localStorage.setItem('spidey_theme', nextTheme);
            setTheme(nextTheme);
        },
    }), [theme]);

    return (
        <AuthContext.Provider value={value}>
            <ThemeContext.Provider value={themeValue}>{children}</ThemeContext.Provider>
        </AuthContext.Provider>
    );
}
