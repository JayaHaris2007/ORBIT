import { useLocation } from 'react-router-dom';
import { motion, AnimatePresence } from 'framer-motion';
import InteractivePlotterCanvas from './editorial/InteractivePlotterCanvas';

const PAGE_VARIANTS = {
    initial: {
        opacity: 0,
        y: 10,
    },
    animate: {
        opacity: 1,
        y: 0,
        transition: {
            duration: 0.24,
            ease: [0.22, 1, 0.36, 1],
        },
    },
    exit: {
        opacity: 0,
        y: -6,
        transition: {
            duration: 0.14,
            ease: [0.4, 0, 1, 1],
        },
    },
};

/**
 * Editorial print-poster workspace frame:
 * 1) Fixed interactive pen-plotter S-curves, orbital rings & 1px hairline grid
 * 2) Restrained, mechanical ease-out route transitions
 */
const ParallaxStage = ({ children }) => {
    const location = useLocation();

    return (
        <div className="relative min-h-screen flex-1 flex flex-col">
            <InteractivePlotterCanvas />

            {/* Animated Route Container */}
            <main className="relative z-10 flex-1 p-4 md:p-8 max-w-7xl mx-auto w-full mb-16 md:mb-0">
                <AnimatePresence mode="wait" initial={true}>
                    <motion.div
                        key={location.pathname}
                        variants={PAGE_VARIANTS}
                        initial="initial"
                        animate="animate"
                        exit="exit"
                        className="mt-4 md:mt-0"
                    >
                        {children}
                    </motion.div>
                </AnimatePresence>
            </main>
        </div>
    );
};

export default ParallaxStage;
