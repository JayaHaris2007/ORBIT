import { useEffect, useState } from 'react';
import { Link, useLocation } from 'react-router-dom';
import {
    Home,
    CheckSquare,
    ListTodo,
    Bell,
    BarChart2,
    Settings,
    GraduationCap,
    PanelLeftClose,
    PanelLeftOpen,
} from 'lucide-react';
import SpiderMark from './brand/SpiderMark';
import { useSpideyBrain } from '../context/SpideyBrainContext';

const NAVBAR_MINIMIZED_KEY = 'spidey_navbar_minimized';

const Navbar = () => {
    const location = useLocation();
    const brain = useSpideyBrain();
    const brainState = brain?.brainState || 'idle';

    const [minimized, setMinimized] = useState(() => {
        try {
            return localStorage.getItem(NAVBAR_MINIMIZED_KEY) === '1';
        } catch {
            return false;
        }
    });

    useEffect(() => {
        document.documentElement.classList.toggle('navbar-minimized', minimized);
        try {
            localStorage.setItem(NAVBAR_MINIMIZED_KEY, minimized ? '1' : '0');
        } catch { /* ignore */ }
    }, [minimized]);

    const navItems = [
        { code: '01', path: '/dashboard', icon: Home, label: 'Dashboard' },
        { code: '02', path: '/habits', icon: CheckSquare, label: 'Habits' },
        { code: '03', path: '/todos', icon: ListTodo, label: 'Tasks' },
        { code: '04', path: '/reminders', icon: Bell, label: 'Reminders & Memory' },
        { code: '05', path: '/learning', icon: GraduationCap, label: 'Learning' },
        { code: '06', path: '/analytics', icon: BarChart2, label: 'Analytics' },
        { code: '07', path: '/settings', icon: Settings, label: 'Settings' },
    ];

    return (
        <nav
            className={`app-sidebar fixed bottom-0 left-0 right-0 md:top-0 md:left-0 md:bottom-0 md:h-screen bg-[#111111] border-t md:border-t-0 md:border-r border-[#F2EFE9]/15 z-50 transition-all duration-200 ${
                minimized ? 'md:w-[72px]' : 'md:w-64'
            }`}
        >
            <div className="flex md:flex-col items-center justify-around md:items-stretch h-full p-2 md:p-0">
                {/* Brand Header with Choreographed Spider Mark & Minimize Button */}
                <div
                    className={`hidden md:flex items-center border-b border-[#F2EFE9]/15 ${
                        minimized ? 'flex-col gap-2.5 px-2 py-4' : 'justify-between gap-2 px-4 py-4'
                    }`}
                >
                    <div className={`flex items-center min-w-0 ${minimized ? 'justify-center' : 'gap-3'}`}>
                        <div className="flex h-11 w-11 shrink-0 items-center justify-center border border-[#F2EFE9]/20 bg-[#151515]">
                            <SpiderMark size={38} state={brainState} />
                        </div>
                        {!minimized && (
                            <div className="min-w-0">
                                <strong className="block truncate text-sm font-bold tracking-[0.26em] text-[#F2EFE9]">
                                    S.P.I.D.E.Y
                                </strong>
                                <span className="mt-0.5 block font-mono text-[10px] uppercase tracking-[0.18em] text-[#D95D24]">
                                    AI Workbench
                                </span>
                            </div>
                        )}
                    </div>
                    <button
                        type="button"
                        onClick={() => setMinimized((v) => !v)}
                        className="grid h-8 w-8 shrink-0 place-items-center border border-[#F2EFE9]/15 bg-[#151515] !p-0 text-[#9C968E] transition-colors hover:border-[#D95D24] hover:text-[#F2EFE9]"
                        title={minimized ? 'Expand navigation bar' : 'Minimize navigation bar'}
                        aria-label={minimized ? 'Expand navigation bar' : 'Minimize navigation bar'}
                        aria-expanded={!minimized}
                    >
                        {minimized ? <PanelLeftOpen size={14} /> : <PanelLeftClose size={14} />}
                    </button>
                </div>

                {!minimized && (
                    <div className="hidden md:flex items-center justify-between border-b border-[#F2EFE9]/10 px-5 py-2.5">
                        <span className="font-mono text-[10px] font-semibold uppercase tracking-[0.22em] text-[#9C968E]">
                            Index
                        </span>
                        <span className="font-mono text-[10px] uppercase tracking-[0.18em] text-[#9C968E]">
                            01–07
                        </span>
                    </div>
                )}

                <div className="flex md:flex-col w-full items-center justify-around md:items-stretch md:divide-y md:divide-[#F2EFE9]/10">
                    {navItems.map((item) => {
                        const Icon = item.icon;
                        const isActive = location.pathname === item.path;

                        return (
                            <Link
                                key={item.path}
                                to={item.path}
                                title={minimized ? `${item.code} · ${item.label}` : undefined}
                                className={`relative group flex items-center justify-center w-11 h-11 md:w-full md:h-auto transition-colors duration-150 ${
                                    minimized ? 'md:justify-center md:px-2 md:py-3.5' : 'md:justify-between md:px-5 md:py-3.5'
                                } ${
                                    isActive
                                        ? 'bg-[#D95D24] text-[#111111] font-bold'
                                        : 'text-[#9C968E] hover:text-[#F2EFE9] hover:bg-[#171614]'
                                }`}
                            >
                                <div className="flex items-center gap-3 min-w-0">
                                    <Icon size={17} strokeWidth={isActive ? 2.25 : 1.6} />
                                    {!minimized && (
                                        <span className="hidden md:block truncate text-xs uppercase tracking-[0.14em]">
                                            {item.label}
                                        </span>
                                    )}
                                </div>
                                {!minimized && (
                                    <span
                                        className={`hidden md:block font-mono text-[10px] tracking-widest ${
                                            isActive ? 'text-[#111111]/80 font-bold' : 'text-[#9C968E]/60'
                                        }`}
                                    >
                                        {item.code}
                                    </span>
                                )}

                                {/* Mobile Active Hairline Indicator */}
                                {isActive && (
                                    <span className="absolute -bottom-1 h-[2px] w-5 bg-[#D95D24] md:hidden" />
                                )}
                            </Link>
                        );
                    })}
                </div>

                {/* Footer Edition Stamp */}
                <div
                    className={`hidden md:flex mt-auto items-center border-t border-[#F2EFE9]/15 py-4 font-mono text-[10px] uppercase tracking-[0.18em] text-[#9C968E] ${
                        minimized ? 'justify-center px-2' : 'justify-between px-5'
                    }`}
                >
                    {minimized ? (
                        <span className="h-2.5 w-2.5 bg-[#D95D24]" title="Local Runtime v2.0" />
                    ) : (
                        <>
                            <span className="flex items-center gap-2">
                                <span className="h-2 w-2 bg-[#D95D24]" />
                                Local Runtime
                            </span>
                            <span className="text-[#F2EFE9]/60">v2.0</span>
                        </>
                    )}
                </div>
            </div>
        </nav>
    );
};

export default Navbar;
