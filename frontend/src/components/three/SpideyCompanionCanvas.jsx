import { useEffect, useRef, useState } from 'react';
import * as THREE from 'three';
import { useSpideyBrain } from '../../context/SpideyBrainContext';
import { loadSpideyAICompanion } from './spideyLoader';

function clipForBrainState(brainState) {
    switch (brainState) {
        case 'listening':
            return 'Front_Wave';
        case 'thinking':
        case 'transcribing':
            return 'Tetrapod_Walk';
        case 'streaming':
        case 'speaking':
            return 'Happy_Bounce';
        case 'idle':
        default:
            return 'Idle_Breath';
    }
}

export default function SpideyCompanionCanvas({
    size = 'hero',
    manualClip = null,
    interactive = true,
    className = '',
    onClick,
}) {
    const containerRef = useRef(null);
    const companionRef = useRef(null);
    const manualClipRef = useRef(manualClip);
    const brain = useSpideyBrain();
    const [loaded, setLoaded] = useState(false);
    const [loadError, setLoadError] = useState(false);

    useEffect(() => {
        manualClipRef.current = manualClip;
        if (manualClip && companionRef.current) {
            companionRef.current.playClip(manualClip, 0.3);
        }
    }, [manualClip]);

    // Sync AI brain state -> animation clip when no manual clip override is active
    useEffect(() => {
        if (!companionRef.current || manualClipRef.current) return;
        const targetClip = clipForBrainState(brain?.brainState || 'idle');
        companionRef.current.playClip(targetClip, 0.35);
    }, [brain?.brainState]);

    useEffect(() => {
        const container = containerRef.current;
        if (!container) return undefined;

        let renderer;
        try {
            renderer = new THREE.WebGLRenderer({
                antialias: true,
                alpha: true,
                powerPreference: 'high-performance',
            });
        } catch {
            return undefined;
        }

        const pixelRatio = Math.min(window.devicePixelRatio || 1, 1.5);
        renderer.setPixelRatio(pixelRatio);
        renderer.setClearColor(0x000000, 0);
        renderer.outputColorSpace = THREE.SRGBColorSpace;
        renderer.toneMapping = THREE.ACESFilmicToneMapping;
        renderer.toneMappingExposure = 1.2;

        const initialWidth = Math.max(container.clientWidth, 100);
        const initialHeight = Math.max(container.clientHeight, 100);
        renderer.setSize(initialWidth, initialHeight, false);
        renderer.domElement.style.width = '100%';
        renderer.domElement.style.height = '100%';
        renderer.domElement.style.display = 'block';
        container.appendChild(renderer.domElement);

        const scene = new THREE.Scene();
        const camera = new THREE.PerspectiveCamera(
            size === 'compact' ? 36 : 34,
            initialWidth / initialHeight,
            0.1,
            25
        );
        camera.position.set(0, 0.42, size === 'compact' ? 3.25 : 3.45);
        camera.lookAt(0, 0.02, 0);

        // Editorial studio lighting: cream key, warm burnt-orange rim, soft ambient fill
        const hemiLight = new THREE.HemisphereLight('#F2EFE9', '#1c1816', 1.15);
        scene.add(hemiLight);

        const keyLight = new THREE.DirectionalLight('#F2EFE9', 2.1);
        keyLight.position.set(2.4, 3.2, 3.0);
        scene.add(keyLight);

        const rimLight = new THREE.DirectionalLight('#D95D24', 1.85);
        rimLight.position.set(-2.6, 1.4, -2.2);
        scene.add(rimLight);

        const fillLight = new THREE.DirectionalLight('#ffffff', 0.7);
        fillLight.position.set(0, -1.5, 2.2);
        scene.add(fillLight);

        const rootGroup = new THREE.Group();
        scene.add(rootGroup);

        let disposed = false;
        let introTimer = null;
        let clickRevertTimer = null;

        loadSpideyAICompanion(rootGroup, '/spidey-ai-companion-animated.glb')
            .then((companion) => {
                if (disposed) {
                    companion.dispose();
                    return;
                }
                companionRef.current = companion;
                setLoaded(true);

                // Play friendly wave briefly on entrance, then follow brain state
                if (!manualClipRef.current && (brain?.brainStateRef?.current || 'idle') === 'idle') {
                    companion.playClip('Front_Wave', 0.25);
                    introTimer = setTimeout(() => {
                        if (!disposed && !manualClipRef.current && companionRef.current) {
                            companionRef.current.playClip(
                                clipForBrainState(brain?.brainStateRef?.current || 'idle'),
                                0.45
                            );
                        }
                    }, 2200);
                } else {
                    companion.playClip(
                        manualClipRef.current || clipForBrainState(brain?.brainStateRef?.current || 'idle'),
                        0.25
                    );
                }
            })
            .catch((err) => {
                console.error('Failed to load Spidey 3D GLB:', err);
                if (!disposed) setLoadError(true);
            });

        // Pointer interactivity
        let targetRotY = 0;
        let targetRotX = 0;

        const onPointerMove = (e) => {
            if (!interactive) return;
            const rect = container.getBoundingClientRect();
            const nx = ((e.clientX - rect.left) / Math.max(rect.width, 1) - 0.5) * 2;
            const ny = ((e.clientY - rect.top) / Math.max(rect.height, 1) - 0.5) * 2;
            targetRotY = nx * 0.45;
            targetRotX = ny * 0.18;
        };

        const onPointerLeave = () => {
            targetRotY = 0;
            targetRotX = 0;
        };

        const onPointerDown = () => {
            if (!interactive || !companionRef.current) return;
            brain?.triggerPulse?.(1.25);
            if (!manualClipRef.current) {
                companionRef.current.playClip('Happy_Bounce', 0.2);
                clearTimeout(clickRevertTimer);
                clickRevertTimer = setTimeout(() => {
                    if (!disposed && !manualClipRef.current && companionRef.current) {
                        companionRef.current.playClip(
                            clipForBrainState(brain?.brainStateRef?.current || 'idle'),
                            0.4
                        );
                    }
                }, 1900);
            }
        };

        container.addEventListener('pointermove', onPointerMove, { passive: true });
        container.addEventListener('pointerleave', onPointerLeave, { passive: true });
        container.addEventListener('pointerdown', onPointerDown, { passive: true });

        const resizeObserver = new ResizeObserver((entries) => {
            for (const entry of entries) {
                const { width, height } = entry.contentRect;
                if (width > 10 && height > 10) {
                    renderer.setSize(width, height, false);
                    camera.aspect = width / height;
                    camera.updateProjectionMatrix();
                }
            }
        });
        resizeObserver.observe(container);

        let isVisible = true;
        let isTabVisible = !document.hidden;
        const intersectionObserver = new IntersectionObserver(
            (entries) => {
                isVisible = entries[0]?.isIntersecting ?? true;
            },
            { threshold: 0.05 }
        );
        intersectionObserver.observe(container);

        const onVisibilityChange = () => {
            isTabVisible = !document.hidden;
        };
        document.addEventListener('visibilitychange', onVisibilityChange);

        const timer = new THREE.Timer();
        let rafId = 0;

        const animate = (timestamp) => {
            rafId = requestAnimationFrame(animate);
            timer.update(timestamp);
            if (!isVisible || !isTabVisible) {
                return;
            }

            const delta = Math.min(timer.getDelta(), 0.05);
            if (companionRef.current) {
                companionRef.current.mixer.update(delta);
            }

            // Smooth look-at cursor tilt + gentle idle sway
            const sway = Math.sin(timer.getElapsed() * 0.8) * 0.08;
            rootGroup.rotation.y += (targetRotY + sway - rootGroup.rotation.y) * Math.min(1, delta * 5.5);
            rootGroup.rotation.x += (targetRotX - rootGroup.rotation.x) * Math.min(1, delta * 5.5);

            renderer.render(scene, camera);
        };

        rafId = requestAnimationFrame(animate);

        return () => {
            disposed = true;
            clearTimeout(introTimer);
            clearTimeout(clickRevertTimer);
            cancelAnimationFrame(rafId);
            resizeObserver.disconnect();
            intersectionObserver.disconnect();
            document.removeEventListener('visibilitychange', onVisibilityChange);
            container.removeEventListener('pointermove', onPointerMove);
            container.removeEventListener('pointerleave', onPointerLeave);
            container.removeEventListener('pointerdown', onPointerDown);

            if (companionRef.current) {
                companionRef.current.dispose();
                companionRef.current = null;
            }
            renderer.dispose();
            if (renderer.domElement.parentNode === container) {
                container.removeChild(renderer.domElement);
            }
        };
    }, [size, interactive, brain]);

    return (
        <div
            ref={containerRef}
            onClick={onClick}
            className={`relative select-none ${interactive ? 'cursor-pointer' : ''} ${className}`}
            role={onClick ? 'button' : undefined}
            tabIndex={onClick ? 0 : undefined}
            onKeyDown={
                onClick
                    ? (e) => {
                          if (e.key === 'Enter' || e.key === ' ') {
                              e.preventDefault();
                              onClick(e);
                          }
                      }
                    : undefined
            }
            aria-label="S.P.I.D.E.Y. 3D AI Companion"
        >
            {!loaded && !loadError && (
                <div className="pointer-events-none absolute inset-0 flex items-center justify-center font-mono text-[10px] uppercase tracking-[0.18em] text-[#9C968E]">
                    Loading 3D Core...
                </div>
            )}
            {loadError && (
                <div className="pointer-events-none absolute inset-0 flex items-center justify-center font-mono text-[10px] uppercase tracking-[0.16em] text-[#D95D24]">
                    3D Model Unavailable
                </div>
            )}
        </div>
    );
}
