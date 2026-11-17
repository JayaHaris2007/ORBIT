import { useEffect, useRef } from 'react';
import * as THREE from 'three';
import { useSpideyBrain } from '../../context/SpideyBrainContext';
import { loadSpideyAICompanion } from './spideyLoader';

const SPRITE_SIZE = 132;

const PET_LINES = [
    '*purrs in binary*',
    'meow~ (8-legged edition)',
    'woof? wait— *happy click*',
    'heyy that tickles!',
    'good spidey! ♡',
    '*happy leg wiggle*',
    '*contented spider chirps*',
    'more pets pls!',
];

const CLICK_LINES = [
    'boop! *happy bounce*',
    '*wags abdomen*',
    'at your service, boss!',
    'hi!! *waves front legs*',
];

/**
 * Autonomous 3D S.P.I.D.E.Y. companion that crawls around the web page,
 * turns toward its walking direction, pauses to breathe or wave,
 * and reacts to AI state and clicks.
 */
export default function SpideyCrawlerOverlay() {
    const wrapperRef = useRef(null);
    const canvasHostRef = useRef(null);
    const badgeRef = useRef(null);
    const companionRef = useRef(null);
    const brain = useSpideyBrain();

    useEffect(() => {
        const wrapper = wrapperRef.current;
        const host = canvasHostRef.current;
        if (!wrapper || !host) return undefined;

        const prefersReducedMotion = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches;

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

        const dpr = Math.min(window.devicePixelRatio || 1, 1.5);
        renderer.setPixelRatio(dpr);
        renderer.setSize(SPRITE_SIZE, SPRITE_SIZE, false);
        renderer.setClearColor(0x000000, 0);
        renderer.outputColorSpace = THREE.SRGBColorSpace;
        renderer.toneMapping = THREE.ACESFilmicToneMapping;
        renderer.toneMappingExposure = 1.25;
        renderer.domElement.style.width = '100%';
        renderer.domElement.style.height = '100%';
        renderer.domElement.style.display = 'block';
        host.appendChild(renderer.domElement);

        const scene = new THREE.Scene();
        const camera = new THREE.PerspectiveCamera(34, 1, 0.1, 20);
        // Top-down angle looking down onto the page surface
        camera.position.set(0, 3.35, 0.72);
        camera.lookAt(0, 0, 0);

        // Studio lighting matching matte black + burnt-orange + cream theme
        scene.add(new THREE.HemisphereLight('#F2EFE9', '#1b1715', 1.35));

        const keyLight = new THREE.DirectionalLight('#F2EFE9', 2.3);
        keyLight.position.set(2.2, 4.5, 2.0);
        scene.add(keyLight);

        const rimLight = new THREE.DirectionalLight('#D95D24', 2.0);
        rimLight.position.set(-2.4, 3.0, -2.2);
        scene.add(rimLight);

        const rootGroup = new THREE.Group();
        scene.add(rootGroup);

        let disposed = false;

        // Roaming state
        const getSafeBounds = () => {
            const w = window.innerWidth;
            const h = window.innerHeight;
            const leftPad = w >= 768 ? 260 : 12;
            const rightPad = w >= 1280 ? 402 : 12;
            const minX = leftPad;
            const maxX = Math.max(minX + 40, w - rightPad - SPRITE_SIZE);
            const minY = 18;
            const maxY = Math.max(minY + 40, h - SPRITE_SIZE - (w < 768 ? 72 : 14));
            return { minX, maxX, minY, maxY };
        };

        const pickNextWaypoint = (currentX, currentY) => {
            const { minX, maxX, minY, maxY } = getSafeBounds();
            const spanX = maxX - minX;
            const spanY = maxY - minY;
            const roll = Math.random();

            // Prefer crawling along the floor, edges, or open corners so it feels like a page crawler
            let tx;
            let ty;
            if (roll < 0.45) {
                // Bottom floor patrol
                tx = minX + Math.random() * spanX;
                ty = maxY - Math.random() * 28;
            } else if (roll < 0.7) {
                // Left or right edge climb
                tx = Math.random() < 0.5 ? minX + Math.random() * 24 : maxX - Math.random() * 24;
                ty = minY + Math.random() * spanY;
            } else if (roll < 0.88) {
                // Top rail crawl
                tx = minX + Math.random() * spanX;
                ty = minY + Math.random() * 26;
            } else {
                // Diagonal roam across page
                tx = minX + Math.random() * spanX;
                ty = minY + Math.random() * spanY;
            }

            // Ensure meaningful travel distance
            if (Math.hypot(tx - currentX, ty - currentY) < 90) {
                tx = currentX < minX + spanX * 0.5 ? maxX - 20 : minX + 20;
            }
            return { x: tx, y: ty };
        };

        const initBounds = getSafeBounds();
        const walker = {
            x: initBounds.minX + 24,
            y: initBounds.maxY - 12,
            tx: initBounds.minX + 220,
            ty: initBounds.maxY - 12,
            facingYaw: 0.45,
            mode: 'intro', // 'intro' | 'walk' | 'pause' | 'click_react' | 'mission_crawl' | 'mission_mark'
            timer: 2.2,
            speed: 68, // px/sec
            layer: 'over', // 'over' (z-25 above <main z-10>) | 'below' (z-5 under cards)
            missionTargetEl: null,
        };

        const setLayer = (nextLayer) => {
            walker.layer = nextLayer;
            wrapper.style.zIndex = nextLayer === 'below' ? '5' : '25';
        };

        const setBadge = (label) => {
            const badge = badgeRef.current;
            if (!badge) return;
            if (label) {
                badge.textContent = label;
                badge.style.opacity = '1';
                badge.style.transform = 'translateY(0)';
            } else {
                badge.style.opacity = '0';
                badge.style.transform = 'translateY(4px)';
            }
        };

        setLayer('over');
        wrapper.style.transform = `translate3d(${walker.x}px, ${walker.y}px, 0)`;

        const setClip = (clipName, fade = 0.3) => {
            companionRef.current?.playClip(clipName, fade);
        };

        const findMissionTarget = (sections = [], text = '') => {
            const lowerText = String(text || '').toLowerCase();
            const cardTypes = [];
            if (sections.includes('habits')) cardTypes.push('habit');
            if (sections.includes('tasks')) cardTypes.push('task');

            // 1. Try matching a specific card title mentioned in prompt/reply
            if (lowerText && cardTypes.length > 0) {
                for (const cardType of cardTypes) {
                    const cards = Array.from(document.querySelectorAll(`[data-spidey-card="${cardType}"]`));
                    const matched = cards.find((el) => {
                        const title = (el.getAttribute('data-spidey-title') || '').trim().toLowerCase();
                        return title.length >= 3 && lowerText.includes(title);
                    });
                    if (matched) return matched;
                }
            }

            // 2. Otherwise pick a completed card or first card inside the refreshed section
            for (const sec of sections) {
                const sectionEl = document.querySelector(`[data-spidey-section="${sec}"]`);
                if (sectionEl) {
                    const completedCard = sectionEl.querySelector('[data-spidey-completed="true"]');
                    if (completedCard) return completedCard;
                    const anyCard = sectionEl.querySelector('[data-spidey-card]');
                    if (anyCard) return anyCard;
                    return sectionEl;
                }
            }

            return document.querySelector('[data-spidey-section]');
        };

        const startMissionToElement = (el, sections = []) => {
            if (!el) return;
            const rect = el.getBoundingClientRect();
            if (rect.top < 24 || rect.bottom > window.innerHeight - 24) {
                el.scrollIntoView({ behavior: 'smooth', block: 'center' });
            }
            const freshRect = el.getBoundingClientRect();
            const { minX, maxX, minY, maxY } = getSafeBounds();
            const targetX = Math.max(minX, Math.min(maxX, freshRect.left + Math.min(48, freshRect.width * 0.28) - SPRITE_SIZE * 0.35));
            const targetY = Math.max(minY, Math.min(maxY, freshRect.top + Math.min(28, freshRect.height * 0.4) - SPRITE_SIZE * 0.42));

            setLayer('over');
            setBadge(null);
            walker.missionTargetEl = el;
            walker.missionLabel = sections.includes('habits')
                ? '✓ HABIT DONE'
                : sections.includes('tasks')
                ? '✓ TASK DONE'
                : '✓ UPDATED';
            walker.tx = targetX;
            walker.ty = targetY;
            walker.mode = 'mission_crawl';
            setClip('Tetrapod_Walk', 0.2);
        };

        let missionRetryTimer = 0;
        const onCrawlerAction = (event) => {
            const detail = event?.detail || {};
            const sections = Array.isArray(detail.sections) ? detail.sections : [];
            const text = detail.text || '';
            if (missionRetryTimer) window.clearTimeout(missionRetryTimer);

            const target = findMissionTarget(sections, text);
            if (target) {
                startMissionToElement(target, sections);
            } else {
                // Retry shortly in case a route navigation is still mounting the target section
                missionRetryTimer = window.setTimeout(() => {
                    if (disposed) return;
                    const delayedTarget = findMissionTarget(sections, text);
                    if (delayedTarget) startMissionToElement(delayedTarget, sections);
                }, 260);
            }
        };
        window.addEventListener('spidey:crawler_action', onCrawlerAction);

        loadSpideyAICompanion(rootGroup, '/spidey-ai-companion-animated.glb')
            .then((companion) => {
                if (disposed) {
                    companion.dispose();
                    return;
                }
                companionRef.current = companion;
                setClip('Front_Wave', 0.25);
            })
            .catch((err) => {
                console.error('Spidey crawler GLB load failed:', err);
            });

        let petDistance = 0;
        let lastPointer = null;
        let lastPetAt = 0;

        const pickRandom = (arr) => arr[Math.floor(Math.random() * arr.length)];

        const onClickCrawler = () => {
            if (!companionRef.current) return;
            brain?.triggerPulse?.(1.25);
            setLayer('over');
            setBadge(pickRandom(CLICK_LINES));
            walker.mode = 'click_react';
            walker.timer = 2.1;
            setClip('Happy_Bounce', 0.2);
        };

        const onPointerMoveCrawler = (event) => {
            if (!companionRef.current) return;
            if (walker.mode === 'mission_crawl' || walker.mode === 'mission_mark') return;

            const now = performance.now();
            if (lastPointer) {
                petDistance += Math.hypot(event.clientX - lastPointer.x, event.clientY - lastPointer.y);
            }
            lastPointer = { x: event.clientX, y: event.clientY };

            if (petDistance >= 42 && now - lastPetAt > 1800) {
                petDistance = 0;
                lastPetAt = now;
                brain?.triggerPulse?.(1.15);
                setLayer('over');
                setBadge(pickRandom(PET_LINES));
                walker.mode = 'click_react';
                walker.timer = 2.3;
                setClip(Math.random() < 0.7 ? 'Happy_Bounce' : 'Front_Wave', 0.22);
            }
        };

        const onPointerLeaveCrawler = () => {
            petDistance = 0;
            lastPointer = null;
        };

        wrapper.addEventListener('click', onClickCrawler);
        wrapper.addEventListener('pointermove', onPointerMoveCrawler);
        wrapper.addEventListener('pointerleave', onPointerLeaveCrawler);

        const onResize = () => {
            const { minX, maxX, minY, maxY } = getSafeBounds();
            walker.x = Math.max(minX, Math.min(maxX, walker.x));
            walker.y = Math.max(minY, Math.min(maxY, walker.y));
            walker.tx = Math.max(minX, Math.min(maxX, walker.tx));
            walker.ty = Math.max(minY, Math.min(maxY, walker.ty));
        };
        window.addEventListener('resize', onResize);

        const clock = new THREE.Clock();
        let rafId = 0;
        let lastAiState = 'idle';

        const animate = () => {
            rafId = requestAnimationFrame(animate);
            if (document.hidden) {
                clock.getDelta();
                return;
            }

            const dt = Math.min(clock.getDelta(), 0.05);
            if (companionRef.current) {
                companionRef.current.mixer.update(dt);
            }

            const aiState = brain?.brainStateRef?.current || 'idle';
            if (aiState !== lastAiState) {
                lastAiState = aiState;
                if (aiState === 'listening') {
                    setClip('Front_Wave', 0.25);
                } else if (aiState === 'streaming' || aiState === 'speaking') {
                    setClip('Happy_Bounce', 0.25);
                } else if (aiState === 'thinking' || aiState === 'transcribing') {
                    setClip('Tetrapod_Walk', 0.25);
                } else if (walker.mode === 'walk') {
                    setClip('Tetrapod_Walk', 0.35);
                } else {
                    setClip('Idle_Breath', 0.35);
                }
            }

            if (!prefersReducedMotion) {
                // Handle AI-reactive overrides (unless actively executing a mission crawl/mark)
                if (walker.mode === 'mission_crawl') {
                    // Refresh target position in case smooth scroll shifted the element
                    if (walker.missionTargetEl && walker.missionTargetEl.isConnected) {
                        const rect = walker.missionTargetEl.getBoundingClientRect();
                        const { minX, maxX, minY, maxY } = getSafeBounds();
                        walker.tx = Math.max(minX, Math.min(maxX, rect.left + Math.min(48, rect.width * 0.28) - SPRITE_SIZE * 0.35));
                        walker.ty = Math.max(minY, Math.min(maxY, rect.top + Math.min(28, rect.height * 0.4) - SPRITE_SIZE * 0.42));
                    }

                    const dx = walker.tx - walker.x;
                    const dy = walker.ty - walker.y;
                    const dist = Math.hypot(dx, dy);
                    const missionSpeed = 185;

                    if (dist < 8) {
                        walker.x = walker.tx;
                        walker.y = walker.ty;
                        walker.mode = 'mission_mark';
                        walker.timer = 1.65;
                        setClip('Happy_Bounce', 0.18);
                        setBadge(walker.missionLabel || '✓ DONE');
                        brain?.triggerPulse?.(1.3);

                        // Subtle burnt-orange stamp outline on the target element
                        const targetEl = walker.missionTargetEl;
                        if (targetEl && targetEl.isConnected) {
                            const prevOutline = targetEl.style.outline;
                            const prevOffset = targetEl.style.outlineOffset;
                            targetEl.style.outline = '2px solid #D95D24';
                            targetEl.style.outlineOffset = '2px';
                            window.setTimeout(() => {
                                if (targetEl.isConnected) {
                                    targetEl.style.outline = prevOutline;
                                    targetEl.style.outlineOffset = prevOffset;
                                }
                            }, 1500);
                        }
                    } else {
                        walker.x += (dx / dist) * missionSpeed * dt;
                        walker.y += (dy / dist) * missionSpeed * dt;
                        const targetYaw = Math.atan2(dx, dy);
                        let diff = targetYaw - walker.facingYaw;
                        while (diff < -Math.PI) diff += Math.PI * 2;
                        while (diff > Math.PI) diff -= Math.PI * 2;
                        walker.facingYaw += diff * Math.min(1, dt * 8);
                    }
                } else if (walker.mode === 'mission_mark') {
                    walker.timer -= dt;
                    let diff = 0 - walker.facingYaw;
                    while (diff < -Math.PI) diff += Math.PI * 2;
                    while (diff > Math.PI) diff -= Math.PI * 2;
                    walker.facingYaw += diff * Math.min(1, dt * 6);

                    if (walker.timer <= 0) {
                        setBadge(null);
                        walker.missionTargetEl = null;
                        const next = pickNextWaypoint(walker.x, walker.y);
                        walker.tx = next.x;
                        walker.ty = next.y;
                        setLayer(Math.random() < 0.35 ? 'below' : 'over');
                        walker.mode = 'walk';
                        setClip('Tetrapod_Walk', 0.3);
                    }
                } else if (aiState === 'listening' || aiState === 'streaming' || aiState === 'speaking') {
                    setLayer('over');
                    // Face the user while talking/listening
                    let diff = 0 - walker.facingYaw;
                    while (diff < -Math.PI) diff += Math.PI * 2;
                    while (diff > Math.PI) diff -= Math.PI * 2;
                    walker.facingYaw += diff * Math.min(1, dt * 6);
                } else if (walker.mode === 'intro' || walker.mode === 'click_react') {
                    walker.timer -= dt;
                    // Face user
                    let diff = 0 - walker.facingYaw;
                    while (diff < -Math.PI) diff += Math.PI * 2;
                    while (diff > Math.PI) diff -= Math.PI * 2;
                    walker.facingYaw += diff * Math.min(1, dt * 6);

                    if (walker.timer <= 0) {
                        setBadge(null);
                        const next = pickNextWaypoint(walker.x, walker.y);
                        walker.tx = next.x;
                        walker.ty = next.y;
                        setLayer(Math.random() < 0.35 ? 'below' : 'over');
                        walker.mode = 'walk';
                        setClip('Tetrapod_Walk', 0.3);
                    }
                } else if (walker.mode === 'pause') {
                    walker.timer -= dt;
                    if (walker.timer <= 0) {
                        setBadge(null);
                        const next = pickNextWaypoint(walker.x, walker.y);
                        walker.tx = next.x;
                        walker.ty = next.y;
                        // Randomly crawl over or slip below components/sections
                        setLayer(Math.random() < 0.38 ? 'below' : 'over');
                        walker.mode = 'walk';
                        setClip('Tetrapod_Walk', 0.3);
                    }
                } else if (walker.mode === 'walk') {
                    const dx = walker.tx - walker.x;
                    const dy = walker.ty - walker.y;
                    const dist = Math.hypot(dx, dy);
                    const moveSpeed = aiState === 'thinking' || aiState === 'transcribing' ? 105 : walker.speed;

                    if (dist < 6) {
                        walker.x = walker.tx;
                        walker.y = walker.ty;
                        walker.mode = 'pause';
                        walker.timer = 2.6 + Math.random() * 3.4;
                        setClip(Math.random() < 0.35 ? 'Front_Wave' : 'Idle_Breath', 0.35);
                    } else {
                        const vx = (dx / dist) * moveSpeed;
                        const vy = (dy / dist) * moveSpeed;
                        walker.x += vx * dt;
                        walker.y += vy * dt;

                        // Turn 3D spider head-first toward its 2D crawl direction (+X right, +Z down)
                        const targetYaw = Math.atan2(dx, dy);
                        let diff = targetYaw - walker.facingYaw;
                        while (diff < -Math.PI) diff += Math.PI * 2;
                        while (diff > Math.PI) diff -= Math.PI * 2;
                        walker.facingYaw += diff * Math.min(1, dt * 5);
                    }
                }

                wrapper.style.transform = `translate3d(${walker.x.toFixed(1)}px, ${walker.y.toFixed(1)}px, 0)`;
                rootGroup.rotation.y = walker.facingYaw;
            }

            renderer.render(scene, camera);
        };

        rafId = requestAnimationFrame(animate);

        return () => {
            disposed = true;
            cancelAnimationFrame(rafId);
            if (missionRetryTimer) window.clearTimeout(missionRetryTimer);
            window.removeEventListener('spidey:crawler_action', onCrawlerAction);
            wrapper.removeEventListener('click', onClickCrawler);
            wrapper.removeEventListener('pointermove', onPointerMoveCrawler);
            wrapper.removeEventListener('pointerleave', onPointerLeaveCrawler);
            window.removeEventListener('resize', onResize);
            if (companionRef.current) {
                companionRef.current.dispose();
                companionRef.current = null;
            }
            renderer.dispose();
            if (renderer.domElement.parentNode === host) {
                host.removeChild(renderer.domElement);
            }
        };
    }, [brain]);

    return (
        <div
            ref={wrapperRef}
            title="S.P.I.D.E.Y. Companion · Click to interact"
            className="fixed left-0 top-0 h-[132px] w-[132px] cursor-pointer select-none will-change-transform"
        >
            <div
                ref={badgeRef}
                style={{ opacity: 0, transform: 'translateY(4px)' }}
                className="pointer-events-none absolute -top-2 left-1/2 -translate-x-1/2 whitespace-nowrap border border-[#D95D24] bg-[#111111] px-2 py-0.5 font-mono text-[9px] font-bold uppercase tracking-[0.16em] text-[#D95D24] transition-all duration-200"
            />
            <div ref={canvasHostRef} className="h-full w-full" />
        </div>
    );
}
