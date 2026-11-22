import InteractivePlotterCanvas from './editorial/InteractivePlotterCanvas';

/**
 * Editorial print-poster workspace frame:
 * Fixed interactive pen-plotter S-curves, orbital rings & 1px hairline grid.
 */
const ParallaxStage = ({ children }) => {
    return (
        <div className="relative min-h-screen flex-1 flex flex-col">
            <InteractivePlotterCanvas />

            {/* Route Container (never uses opacity:0 AnimatePresence wait mode that can freeze on rapid agent navigation) */}
            <main className="relative z-10 flex-1 p-4 md:p-8 max-w-7xl mx-auto w-full mb-16 md:mb-0">
                <div className="mt-4 md:mt-0">
                    {children}
                </div>
            </main>
        </div>
    );
};

export default ParallaxStage;
