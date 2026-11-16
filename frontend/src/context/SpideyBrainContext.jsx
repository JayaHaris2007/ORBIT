import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from 'react';

const SpideyBrainContext = createContext(null);

// eslint-disable-next-line react-refresh/only-export-components
export const useSpideyBrain = () => useContext(SpideyBrainContext);

/**
 * Helper to broadcast AI brain state or audio level from anywhere (including hooks/non-React helpers).
 */
// eslint-disable-next-line react-refresh/only-export-components
export function emitBrainState(state, extra = {}) {
    if (typeof window === 'undefined') return;
    window.dispatchEvent(
        new CustomEvent('spidey:brain_state', {
            detail: { state, ...extra },
        })
    );
}

// eslint-disable-next-line react-refresh/only-export-components
export function emitBrainAudioLevel(level) {
    if (typeof window === 'undefined') return;
    window.dispatchEvent(
        new CustomEvent('spidey:brain_audio', {
            detail: { level: Math.max(0, Math.min(1, Number(level) || 0)) },
        })
    );
}

// eslint-disable-next-line react-refresh/only-export-components
export function emitBrainPulse(intensity = 1) {
    if (typeof window === 'undefined') return;
    window.dispatchEvent(
        new CustomEvent('spidey:brain_pulse', {
            detail: { intensity: Math.max(0.2, Math.min(2, Number(intensity) || 1)) },
        })
    );
}

export function SpideyBrainProvider({ children }) {
    const [brainState, setBrainStateRaw] = useState('idle');
    const brainStateRef = useRef('idle');
    const audioLevelRef = useRef(0);
    const pulseRef = useRef({ time: 0, intensity: 0 });

    const setBrainState = useCallback((nextState) => {
        const normalized = nextState || 'idle';
        brainStateRef.current = normalized;
        setBrainStateRaw((prev) => (prev === normalized ? prev : normalized));
    }, []);

    const setAudioLevel = useCallback((level) => {
        audioLevelRef.current = Math.max(0, Math.min(1, Number(level) || 0));
    }, []);

    const triggerPulse = useCallback((intensity = 1) => {
        pulseRef.current = {
            time: typeof performance !== 'undefined' ? performance.now() : Date.now(),
            intensity: Math.max(0.2, Math.min(2, Number(intensity) || 1)),
        };
    }, []);

    useEffect(() => {
        const onState = (e) => {
            const detail = e?.detail;
            if (!detail) return;
            if (detail.state) setBrainState(detail.state);
            if (typeof detail.audioLevel === 'number') setAudioLevel(detail.audioLevel);
            if (detail.pulse) triggerPulse(detail.pulse);
        };
        const onAudio = (e) => {
            if (typeof e?.detail?.level === 'number') {
                setAudioLevel(e.detail.level);
            }
        };
        const onPulse = (e) => {
            triggerPulse(e?.detail?.intensity ?? 1);
        };

        window.addEventListener('spidey:brain_state', onState);
        window.addEventListener('spidey:brain_audio', onAudio);
        window.addEventListener('spidey:brain_pulse', onPulse);
        return () => {
            window.removeEventListener('spidey:brain_state', onState);
            window.removeEventListener('spidey:brain_audio', onAudio);
            window.removeEventListener('spidey:brain_pulse', onPulse);
        };
    }, [setBrainState, setAudioLevel, triggerPulse]);

    const value = useMemo(
        () => ({
            brainState,
            brainStateRef,
            audioLevelRef,
            pulseRef,
            setBrainState,
            setAudioLevel,
            triggerPulse,
        }),
        [brainState, setBrainState, setAudioLevel, triggerPulse]
    );

    return (
        <SpideyBrainContext.Provider value={value}>
            {children}
        </SpideyBrainContext.Provider>
    );
}
