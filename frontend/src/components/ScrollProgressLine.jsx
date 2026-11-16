import { useEffect, useState } from 'react';
import { useLocation } from 'react-router-dom';

/**
 * Top scroll progress indicator line in S.P.I.D.E.Y orange theme.
 * Smoothly tracks viewport scroll progress with glowing orange gradient and leading photon head.
 */
const ScrollProgressLine = () => {
    const location = useLocation();
    const [progress, setProgress] = useState(0);
    const [isScrollable, setIsScrollable] = useState(false);

    useEffect(() => {
        let rafId = 0;

        const updateProgress = () => {
            const scrollTop = window.scrollY || document.documentElement.scrollTop || 0;
            const scrollHeight = document.documentElement.scrollHeight || 0;
            const clientHeight = window.innerHeight || document.documentElement.clientHeight || 1;
            const maxScroll = scrollHeight - clientHeight;

            if (maxScroll > 10) {
                setIsScrollable(true);
                const current = Math.min(1, Math.max(0, scrollTop / maxScroll));
                setProgress(current);
            } else {
                setIsScrollable(false);
                setProgress(0);
            }
        };

        const handleScrollOrResize = () => {
            cancelAnimationFrame(rafId);
            rafId = requestAnimationFrame(updateProgress);
        };

        handleScrollOrResize();
        window.addEventListener('scroll', handleScrollOrResize, { passive: true });
        window.addEventListener('resize', handleScrollOrResize, { passive: true });

        const timer = setTimeout(handleScrollOrResize, 200);

        return () => {
            window.removeEventListener('scroll', handleScrollOrResize);
            window.removeEventListener('resize', handleScrollOrResize);
            cancelAnimationFrame(rafId);
            clearTimeout(timer);
        };
    }, [location.pathname]);

    return (
        <div
            className={`fixed top-0 left-0 right-0 h-[2px] z-[99] pointer-events-none transition-opacity duration-200 ${
                isScrollable ? 'opacity-100' : 'opacity-0'
            }`}
            aria-hidden="true"
        >
            <div className="absolute inset-0 bg-[#F2EFE9]/10" />
            <div
                className="h-full bg-[#D95D24] origin-left will-change-transform"
                style={{
                    transform: `scaleX(${progress})`,
                    transition: 'transform 80ms cubic-bezier(0.22, 1, 0.36, 1)',
                }}
            />
        </div>
    );
};

export default ScrollProgressLine;

