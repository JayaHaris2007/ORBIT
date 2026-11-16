import { Link, useLocation } from 'react-router-dom';
import { Home, CheckSquare, ListTodo, Bell, BarChart2, Settings, GraduationCap } from 'lucide-react';
import SpiderMark from './brand/SpiderMark';
import { useSpideyBrain } from '../context/SpideyBrainContext';

const Navbar = () => {
    const location = useLocation();
    const brain = useSpideyBrain();
    const brainState = brain?.brainState || 'idle';

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
        <nav className="app-sidebar fixed bottom-0 left-0 right-0 md:top-0 md:left-0 md:bottom-0 md:w-64 md:h-screen bg-[#111111] border-t md:border-t-0 md:border-r border-[#F2EFE9]/15 z-50 transition-colors duration-200">
            <div className="flex md:flex-col items-center justify-around md:items-stretch h-full p-2 md:p-0">
                {/* Brand Header with Choreographed Spider Mark */}
                <div className="hidden md:flex items-center gap-3 border-b border-[#F2EFE9]/15 px-5 py-5">
                    <div className="flex h-12 w-12 shrink-0 items-center justify-center border border-[#F2EFE9]/20 bg-[#151515]">
                        <SpiderMark size={42} state={brainState} />
                    </div>
                    <div className="min-w-0">
                        <strong className="block text-sm font-bold tracking-[0.26em] text-[#F2EFE9]">
                            S.P.I.D.E.Y
                        </strong>
                        <span className="mt-0.5 block font-mono text-[10px] uppercase tracking-[0.18em] text-[#D95D24]">
                            AI Workbench
                        </span>
                    </div>
                </div>

                <div className="hidden md:flex items-center justify-between border-b border-[#F2EFE9]/10 px-5 py-2.5">
                    <span className="font-mono text-[10px] font-semibold uppercase tracking-[0.22em] text-[#9C968E]">
                        Index
                    </span>
                    <span className="font-mono text-[10px] uppercase tracking-[0.18em] text-[#9C968E]">
                        01–07
                    </span>
                </div>

                <div className="flex md:flex-col w-full items-center justify-around md:items-stretch md:divide-y md:divide-[#F2EFE9]/10">
                    {navItems.map((item) => {
                        const Icon = item.icon;
                        const isActive = location.pathname === item.path;

                        return (
                            <Link
                                key={item.path}
                                to={item.path}
                                className={`relative group flex items-center justify-center md:justify-between w-11 h-11 md:w-full md:h-auto md:px-5 md:py-3.5 transition-colors duration-150 ${
                                    isActive
                                        ? 'bg-[#D95D24] text-[#111111] font-bold'
                                        : 'text-[#9C968E] hover:text-[#F2EFE9] hover:bg-[#171614]'
                                }`}
                            >
                                <div className="flex items-center gap-3 min-w-0">
                                    <Icon size={17} strokeWidth={isActive ? 2.25 : 1.6} />
                                    <span className="hidden md:block truncate text-xs uppercase tracking-[0.14em]">
                                        {item.label}
                                    </span>
                                </div>
                                <span
                                    className={`hidden md:block font-mono text-[10px] tracking-widest ${
                                        isActive ? 'text-[#111111]/80 font-bold' : 'text-[#9C968E]/60'
                                    }`}
                                >
                                    {item.code}
                                </span>

                                {/* Mobile Active Hairline Indicator */}
                                {isActive && (
                                    <span className="absolute -bottom-1 h-[2px] w-5 bg-[#D95D24] md:hidden" />
                                )}
                            </Link>
                        );
                    })}
                </div>

                {/* Footer Edition Stamp */}
                <div className="hidden md:flex mt-auto items-center justify-between border-t border-[#F2EFE9]/15 px-5 py-4 font-mono text-[10px] uppercase tracking-[0.18em] text-[#9C968E]">
                    <span className="flex items-center gap-2">
                        <span className="h-2 w-2 bg-[#D95D24]" />
                        Local Runtime
                    </span>
                    <span className="text-[#F2EFE9]/60">v2.0</span>
                </div>
            </div>
        </nav>
    );
};

export default Navbar;
