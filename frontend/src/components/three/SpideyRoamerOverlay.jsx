import { useEffect, useRef } from 'react';
import * as THREE from 'three';
import { useSpideyBrain } from '../../context/SpideyBrainContext';
import { getSharedAudioQueue } from '../../services/voiceService';
import { loadSpideyAICompanion } from './spideyLoader';

const SPRITE_SIZE = 104;
const PERCH_OFFSET_Y = 30;

const PET_LINES = [
    '*happy leg wiggle*',
    'heyy that tickles!',
    'good spidey!',
    'at your service!',
];

const CLICK_LINES = [
    'boop! *happy bounce*',
    'thwip! *web ready*',
    'hi!! *waves front legs*',
];

function easeOutCubic(t) {
    return 1 - Math.pow(1 - t, 3);
}

function easeInOutCubic(t) {
    return t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2;
}

function getAnchorRect(name) {
    if (typeof document === 'undefined') return null;
    const el = document.querySelector(`[data-spidey-anchor="${name}"]`);
    if (!el) return null;
    const rect = el.getBoundingClientRect();
    if (rect.width < 40 || rect.height < 10) return null;
    return rect;
}

/**
 * Persistent, smooth 3D S.P.I.D.E.Y companion with web-shooting & zip/swing locomotion:
 * - Never destroys/reloads on brain state changes (reads brain via stable ref).
 * - Never randomly wanders across empty screen space.
 * - Moves between UI perches (input box shoulders, navbar silk-hang spots, section card corners)
 *   by shooting a luminous silk web line and zipping/swinging smoothly along a graceful arc!
 * - Smooth, grounded, natural speaking animation synced to live TTS audio.
 */
export default function SpideyRoamerOverlay() {
    const wrapperRef = useRef(null);
    const canvasHostRef = useRef(null);
    const silkSvgRef = useRef(null);
    const zipLineRef = useRef(null);
    const zipAnchorDotRef = useRef(null);
    const hangLineRef = useRef(null);
    const hangAnchorDotRef = useRef(null);
    const eqWrapRef = useRef(null);
    const eqBarRefs = useRef([]);
    const badgeRef = useRef(null);

    const brain = useSpideyBrain();
    const brainRef = useRef(brain);
    useEffect(() => {
        brainRef.current = brain;
    }, [brain]);

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

        const dpr = Math.min(window.devicePixelRatio || 1, 1.75);
        renderer.setPixelRatio(dpr);
        renderer.setSize(SPRITE_SIZE, SPRITE_SIZE, false);
        renderer.setClearColor(0x000000, 0);
        renderer.outputColorSpace = THREE.SRGBColorSpace;
        renderer.toneMapping = THREE.ACESFilmicToneMapping;
        renderer.toneMappingExposure = 1.24;
        renderer.domElement.style.width = '100%';
        renderer.domElement.style.height = '100%';
        renderer.domElement.style.display = 'block';
        host.appendChild(renderer.domElement);

        const scene = new THREE.Scene();
        const camera = new THREE.PerspectiveCamera(34, 1, 0.1, 25);
        camera.position.set(0, 0.58, 3.65);
        camera.lookAt(0, -0.02, 0);

        scene.add(new THREE.HemisphereLight('#F2EFE9', '#1b1613', 1.35));

        const keyLight = new THREE.DirectionalLight('#F2EFE9', 2.3);
        keyLight.position.set(2.4, 3.6, 3.0);
        scene.add(keyLight);

        const rimLight = new THREE.DirectionalLight('#D95D24', 2.1);
        rimLight.position.set(-2.6, 1.5, -2.0);
        scene.add(rimLight);

        const speechGlowLight = new THREE.PointLight('#E07A48', 0, 4.5);
        speechGlowLight.position.set(0, 0.35, 1.5);
        scene.add(speechGlowLight);

        const rootGroup = new THREE.Group();
        scene.add(rootGroup);

        let disposed = false;
        let companion = null;
        let headNode = null;

        let badgeTimeout = null;
        const showBadge = (text, duration = 1650) => {
            if (!badgeRef.current) return;
            badgeRef.current.textContent = text;
            badgeRef.current.style.opacity = '1';
            badgeRef.current.style.transform = 'translate(-50%, 0px)';
            clearTimeout(badgeTimeout);
            badgeTimeout = setTimeout(() => {
                if (badgeRef.current) {
                    badgeRef.current.style.opacity = '0';
                    badgeRef.current.style.transform = 'translate(-50%, 4px)';
                }
            }, duration);
        };

        loadSpideyAICompanion(rootGroup, '/spidey-ai-companion-animated.glb')
            .then((loaded) => {
                if (disposed) {
                    loaded.dispose();
                    return;
                }
                companion = loaded;
                loaded.spidey.traverse((obj) => {
                    if (obj.name === 'SpideyHead') headNode = obj;
                });
                loaded.playClip('Idle_Breath', 0.25);
            })
            .catch((err) => {
                console.warn('SpideyRoamerOverlay GLB failed to load:', err);
            });

        // Compute clean anchor coordinates for each named UI perch
        const computePerchPoint = (perchKey, customXRatio = null) => {
            const composer = getAnchorRect('composer');
            const navbar = getAnchorRect('navbar');
            const card = getAnchorRect('section-card');

            if (perchKey === 'composer_left' && composer) {
                return {
                    x: composer.left + Math.min(82, composer.width * 0.16),
                    y: composer.top - PERCH_OFFSET_Y,
                    hangAnchorX: null,
                    hangAnchorY: null,
                };
            }
            if (perchKey === 'composer_right' && composer) {
                return {
                    x: composer.right - Math.min(82, composer.width * 0.16),
                    y: composer.top - PERCH_OFFSET_Y,
                    hangAnchorX: null,
                    hangAnchorY: null,
                };
            }
            if (perchKey === 'navbar_hang' && navbar) {
                const minX = Math.max(navbar.left + 120, window.innerWidth * 0.22);
                const maxX = Math.min(navbar.right - 150, window.innerWidth * 0.80);
                const ratio = customXRatio ?? (0.2 + Math.random() * 0.65);
                const hangX = minX < maxX ? minX + (maxX - minX) * ratio : navbar.left + navbar.width * 0.62;
                const dropDist = 66 + (customXRatio != null ? 24 : Math.random() * 34);
                return {
                    x: hangX,
                    y: navbar.bottom + dropDist,
                    hangAnchorX: hangX,
                    hangAnchorY: navbar.bottom - 2,
                };
            }
            if (perchKey === 'card_left' && card) {
                return {
                    x: card.left + 72,
                    y: card.top - PERCH_OFFSET_Y,
                    hangAnchorX: null,
                    hangAnchorY: null,
                };
            }
            if (perchKey === 'card_right' && card) {
                return {
                    x: card.right - 72,
                    y: card.top - PERCH_OFFSET_Y,
                    hangAnchorX: null,
                    hangAnchorY: null,
                };
            }
            if (composer) {
                return {
                    x: composer.left + Math.min(82, composer.width * 0.16),
                    y: composer.top - PERCH_OFFSET_Y,
                    hangAnchorX: null,
                    hangAnchorY: null,
                };
            }
            return {
                x: window.innerWidth * 0.3,
                y: window.innerHeight - 125,
                hangAnchorX: null,
                hangAnchorY: null,
            };
        };

        const initialPt = computePerchPoint('composer_left');

        // Smooth Web-Shoot & Zip State Machine
        const state = {
            x: initialPt.x,
            y: initialPt.y,
            perchKey: 'composer_left',
            hangAnchorX: null,
            hangAnchorY: null,
            hangRatio: 0.65,
            // Locomotion phase: 'perched' | 'shooting_web' | 'web_zipping'
            locomotion: 'perched',
            startX: initialPt.x,
            startY: initialPt.y,
            targetX: initialPt.x,
            targetY: initialPt.y,
            targetPerchKey: 'composer_left',
            targetHangAnchorX: null,
            targetHangAnchorY: null,
            phaseElapsed: 0,
            shootDuration: 0.28,
            zipDuration: 0.65,
            arcHeight: 44,
            idleTimer: 7.0,
            facingAngle: 0.15,
            cursorX: window.innerWidth * 0.5,
            cursorY: window.innerHeight * 0.5,
            petCooldown: 0,
            clickBounceTimer: 0,
            wasSpeaking: false,
            speakIntroWaveTimer: 0,
            settleTimer: 0,
        };

        const launchWebZipTo = (perchKey, opts = {}) => {
            const ratio = perchKey === 'navbar_hang' ? (opts.ratio ?? (0.18 + Math.random() * 0.68)) : null;
            const pt = computePerchPoint(perchKey, ratio);
            const dist = Math.hypot(pt.x - state.x, pt.y - state.y);

            // Already right at the destination perch? No need to shoot web!
            if (dist < 26) {
                state.perchKey = perchKey;
                state.hangAnchorX = pt.hangAnchorX;
                state.hangAnchorY = pt.hangAnchorY;
                if (ratio !== null) state.hangRatio = ratio;
                state.locomotion = 'perched';
                return;
            }

            state.startX = state.x;
            state.startY = state.y;
            state.targetX = pt.x;
            state.targetY = pt.y;
            state.targetPerchKey = perchKey;
            state.targetHangAnchorX = pt.hangAnchorX;
            state.targetHangAnchorY = pt.hangAnchorY;
            if (ratio !== null) state.hangRatio = ratio;

            state.locomotion = 'shooting_web';
            state.phaseElapsed = 0;
            state.shootDuration = opts.fast ? 0.18 : 0.28;
            // Smooth proportional zip duration (fast & snappy when summoned to speak/listen)
            const speedPx = opts.fast ? 1150 : 760;
            state.zipDuration = Math.max(0.34, Math.min(opts.fast ? 0.55 : 0.92, dist / speedPx));
            // Graceful spider-swing sag/arc: swings slightly downward when crossing horizontally, arches smoothly when ascending
            const verticalDelta = pt.y - state.y;
            state.arcHeight = verticalDelta > 80 ? -36 : verticalDelta < -80 ? -24 : Math.min(72, Math.max(28, dist * 0.16));
        };

        const pickNextPerch = () => {
            const composer = getAnchorRect('composer');
            const navbar = getAnchorRect('navbar');
            const card = getAnchorRect('section-card');

            const candidates = [];
            if (composer) candidates.push('composer_left', 'composer_right');
            if (navbar) candidates.push('navbar_hang');
            if (card) candidates.push('card_left', 'card_right');

            const others = candidates.filter((k) => k !== state.perchKey);
            const pool = others.length ? others : candidates;
            if (!pool.length) return;

            const chosen = pool[Math.floor(Math.random() * pool.length)];
            launchWebZipTo(chosen);
            state.idleTimer = 7.5 + Math.random() * 5.0;
        };

        const onWindowPointerMove = (e) => {
            state.cursorX = e.clientX;
            state.cursorY = e.clientY;
        };

        const onSpideyEnter = () => {
            const now = performance.now();
            if (now - state.petCooldown > 2400 && state.locomotion === 'perched') {
                state.petCooldown = now;
                state.clickBounceTimer = 1.25;
                companion?.playClip('Front_Wave', 0.25);
                showBadge(PET_LINES[Math.floor(Math.random() * PET_LINES.length)], 1450);
            }
        };

        const onSpideyClick = () => {
            if (state.locomotion === 'perched') {
                state.clickBounceTimer = 1.45;
                companion?.playClip('Happy_Bounce', 0.22);
                brainRef.current?.triggerPulse?.(1.3);
                showBadge(CLICK_LINES[Math.floor(Math.random() * CLICK_LINES.length)], 1500);
            }
        };

        window.addEventListener('pointermove', onWindowPointerMove, { passive: true });
        wrapper.addEventListener('pointerenter', onSpideyEnter);
        wrapper.addEventListener('click', onSpideyClick);

        let isTabVisible = !document.hidden;
        const onVisibility = () => {
            isTabVisible = !document.hidden;
        };
        document.addEventListener('visibilitychange', onVisibility);

        let rafId = 0;
        let lastTime = performance.now();
        let simTime = 0;
        let smoothAudio = 0;

        const animate = (now) => {
            rafId = requestAnimationFrame(animate);
            if (!isTabVisible) {
                lastTime = now;
                return;
            }

            const dt = Math.min((now - lastTime) / 1000, 0.05);
            lastTime = now;
            simTime += dt;

            if (state.clickBounceTimer > 0) {
                state.clickBounceTimer = Math.max(0, state.clickBounceTimer - dt);
            }
            if (state.settleTimer > 0) {
                state.settleTimer = Math.max(0, state.settleTimer - dt);
            }

            const currentBrain = brainRef.current?.brainStateRef?.current || 'idle';
            const audioQueue = getSharedAudioQueue();
            const ttsLevel = audioQueue?.getOutputLevel?.() || 0;
            const micLevel = brainRef.current?.audioLevelRef?.current || 0;
            const isSpeaking = currentBrain === 'speaking' || currentBrain === 'streaming' || Boolean(audioQueue?.playing);
            const isListening = !isSpeaking && currentBrain === 'listening';
            const isThinking = !isSpeaking && !isListening && (currentBrain === 'thinking' || currentBrain === 'transcribing');

            if (isSpeaking && !state.wasSpeaking) {
                state.speakIntroWaveTimer = 1.05;
            }
            state.wasSpeaking = isSpeaking;
            if (state.speakIntroWaveTimer > 0) {
                state.speakIntroWaveTimer = Math.max(0, state.speakIntroWaveTimer - dt);
            }

            let liveEnergy = isSpeaking ? ttsLevel : isListening ? micLevel : 0;
            if (isSpeaking && liveEnergy < 0.08) {
                liveEnergy = 0.18 + 0.14 * Math.abs(Math.sin(simTime * 7.0));
            }
            smoothAudio += (liveEnergy - smoothAudio) * Math.min(1, dt * 9.0);

            // If AI starts speaking or listening while Spidey is on navbar/card, smoothly web-zip to composer_left!
            const needsComposerPerch = isSpeaking || isListening;
            if (
                needsComposerPerch
                && state.perchKey !== 'composer_left'
                && state.perchKey !== 'composer_right'
                && state.targetPerchKey !== 'composer_left'
            ) {
                launchWebZipTo('composer_left', { fast: true });
            }

            let desiredClip = 'Idle_Breath';
            let targetPitchX = 0;
            let targetRollZ = 0;
            let desiredFacingY = 0;
            let speakBobY = 0;

            let showZipLine = false;
            let zipX1 = 0;
            let zipY1 = 0;
            let zipX2 = 0;
            let zipY2 = 0;
            let showZipDot = false;

            let showHangLine = false;
            let hangX1 = 0;
            let hangY1 = 0;

            if (state.locomotion === 'shooting_web') {
                // Phase 1: Shoot silk web from Spidey out to the target perch
                state.phaseElapsed += dt;
                const p = Math.min(1, state.phaseElapsed / state.shootDuration);
                const eased = easeOutCubic(p);

                const dx = state.targetX - state.x;
                const dy = state.targetY - state.y;
                desiredFacingY = dx >= 0 ? 0.9 : -0.9;
                targetPitchX = Math.max(-0.38, Math.min(0.38, dy / 420));
                desiredClip = 'Front_Wave';

                showZipLine = true;
                zipX1 = state.x;
                zipY1 = state.y - 6;
                zipX2 = state.x + (state.targetX - state.x) * eased;
                zipY2 = state.y - 6 + (state.targetY - state.y) * eased;
                showZipDot = p >= 0.85;

                // Keep navbar hang silk attached until zip launches
                if (state.perchKey === 'navbar_hang' && state.hangAnchorX != null) {
                    showHangLine = true;
                    hangX1 = state.hangAnchorX;
                    hangY1 = state.hangAnchorY;
                }

                if (p >= 1) {
                    state.locomotion = 'web_zipping';
                    state.phaseElapsed = 0;
                }
            } else if (state.locomotion === 'web_zipping') {
                // Phase 2: Zip smoothly along a graceful spider-swing arc to the target anchor!
                state.phaseElapsed += dt;
                const p = Math.min(1, state.phaseElapsed / state.zipDuration);
                const t = easeInOutCubic(p);

                const prevX = state.x;
                const prevY = state.y;

                // Quadratic Bezier arc with gentle swing sag
                const midX = (state.startX + state.targetX) * 0.5;
                const midY = (state.startY + state.targetY) * 0.5 + state.arcHeight;
                const inv = 1 - t;
                state.x = inv * inv * state.startX + 2 * inv * t * midX + t * t * state.targetX;
                state.y = inv * inv * state.startY + 2 * inv * t * midY + t * t * state.targetY;

                const vx = state.x - prevX;
                const vy = state.y - prevY;
                desiredFacingY = vx >= 0 ? 1.05 : -1.05;
                targetRollZ = Math.max(-0.32, Math.min(0.32, -vx * 0.02));
                targetPitchX = Math.max(-0.35, Math.min(0.35, vy * 0.025));
                desiredClip = 'Front_Wave';

                // Silk web line stays taut from Spidey to target anchor as it reels in!
                showZipLine = p < 0.96;
                zipX1 = state.x;
                zipY1 = state.y - 8;
                zipX2 = state.targetX;
                zipY2 = state.targetY;
                showZipDot = p < 0.96;

                if (p >= 1) {
                    state.x = state.targetX;
                    state.y = state.targetY;
                    state.perchKey = state.targetPerchKey;
                    state.hangAnchorX = state.targetHangAnchorX;
                    state.hangAnchorY = state.targetHangAnchorY;
                    state.locomotion = 'perched';
                    state.settleTimer = 0.28;
                }
            } else {
                // Phase 3: Perched cleanly on a real UI landmark
                // Follow live layout shifts (sidebar toggle, window resize, card close) smoothly
                if ((state.perchKey === 'card_left' || state.perchKey === 'card_right') && !getAnchorRect('section-card')) {
                    launchWebZipTo('composer_left', { fast: true });
                } else {
                    const livePt = computePerchPoint(state.perchKey, state.hangRatio);
                    if (state.perchKey === 'navbar_hang') {
                        const sway = Math.sin(simTime * 1.75) * 9;
                        const targetHangX = livePt.x + sway;
                        state.x += (targetHangX - state.x) * Math.min(1, dt * 8);
                        state.y += (livePt.y - state.y) * Math.min(1, dt * 8);
                        state.hangAnchorX = livePt.hangAnchorX;
                        state.hangAnchorY = livePt.hangAnchorY;
                        showHangLine = true;
                        hangX1 = livePt.hangAnchorX;
                        hangY1 = livePt.hangAnchorY;
                        targetRollZ = -Math.cos(simTime * 1.75) * 0.1;
                        targetPitchX = 0.18;
                    } else {
                        state.x += (livePt.x - state.x) * Math.min(1, dt * 10);
                        state.y += (livePt.y - state.y) * Math.min(1, dt * 10);
                    }
                }

                // Soft landing cushion bounce
                if (state.settleTimer > 0) {
                    speakBobY = -Math.sin((state.settleTimer / 0.28) * Math.PI) * 0.06;
                }

                if (isSpeaking) {
                    desiredClip = state.speakIntroWaveTimer > 0 ? 'Front_Wave' : 'Idle_Breath';
                    desiredFacingY = (state.perchKey === 'composer_right' ? -0.2 : 0.2) + Math.sin(simTime * 2.1) * 0.1;
                    targetRollZ = Math.sin(simTime * 2.4) * (0.035 + smoothAudio * 0.055);
                    targetPitchX = -0.02 - smoothAudio * 0.07;
                    speakBobY += smoothAudio * 0.05;
                } else if (isListening) {
                    desiredClip = 'Front_Wave';
                    desiredFacingY = state.perchKey === 'composer_right' ? -0.18 : 0.18;
                    targetRollZ = Math.sin(simTime * 2.0) * 0.07;
                } else if (isThinking) {
                    desiredClip = 'Idle_Breath';
                    desiredFacingY = Math.sin(simTime * 2.2) * 0.35;
                    targetPitchX = -0.06;
                } else {
                    const lookNorm = Math.max(-1, Math.min(1, (state.cursorX - state.x) / 380));
                    desiredFacingY = lookNorm * 0.45;
                    desiredClip = state.idleTimer < 2.2 && state.idleTimer > 0.9 ? 'Front_Wave' : 'Idle_Breath';

                    if (!prefersReducedMotion) {
                        state.idleTimer -= dt;
                        if (state.idleTimer <= 0) {
                            pickNextPerch();
                        }
                    }
                }
            }

            if (state.clickBounceTimer > 0 && !isSpeaking && state.locomotion === 'perched') {
                desiredClip = 'Happy_Bounce';
                desiredFacingY = 0;
            }

            // Clamp smoothly within viewport
            const half = SPRITE_SIZE * 0.5;
            const clampedX = Math.max(half + 6, Math.min(window.innerWidth - half - 6, state.x));
            const clampedY = Math.max(half - 8, Math.min(window.innerHeight - half + 8, state.y));
            wrapper.style.transform = `translate3d(${(clampedX - half).toFixed(1)}px, ${(clampedY - half).toFixed(1)}px, 0)`;

            // Render silk web threads (web-shoot zip strand + navbar hang thread)
            if (silkSvgRef.current) {
                silkSvgRef.current.style.opacity = showZipLine || showHangLine ? '1' : '0';
            }
            if (zipLineRef.current && zipAnchorDotRef.current) {
                if (showZipLine) {
                    zipLineRef.current.style.opacity = '1';
                    zipLineRef.current.setAttribute('x1', zipX1.toFixed(1));
                    zipLineRef.current.setAttribute('y1', zipY1.toFixed(1));
                    zipLineRef.current.setAttribute('x2', zipX2.toFixed(1));
                    zipLineRef.current.setAttribute('y2', zipY2.toFixed(1));
                    zipAnchorDotRef.current.style.opacity = showZipDot ? '1' : '0';
                    zipAnchorDotRef.current.setAttribute('cx', zipX2.toFixed(1));
                    zipAnchorDotRef.current.setAttribute('cy', zipY2.toFixed(1));
                } else {
                    zipLineRef.current.style.opacity = '0';
                    zipAnchorDotRef.current.style.opacity = '0';
                }
            }
            if (hangLineRef.current && hangAnchorDotRef.current) {
                if (showHangLine) {
                    hangLineRef.current.style.opacity = '1';
                    hangLineRef.current.setAttribute('x1', hangX1.toFixed(1));
                    hangLineRef.current.setAttribute('y1', hangY1.toFixed(1));
                    hangLineRef.current.setAttribute('x2', clampedX.toFixed(1));
                    hangLineRef.current.setAttribute('y2', (clampedY - 10).toFixed(1));
                    hangAnchorDotRef.current.style.opacity = '1';
                    hangAnchorDotRef.current.setAttribute('cx', hangX1.toFixed(1));
                    hangAnchorDotRef.current.setAttribute('cy', hangY1.toFixed(1));
                } else {
                    hangLineRef.current.style.opacity = '0';
                    hangAnchorDotRef.current.style.opacity = '0';
                }
            }

            // Update crisp 4-bar equalizer pill above Spidey while speaking
            if (eqWrapRef.current) {
                if (isSpeaking && state.locomotion === 'perched') {
                    eqWrapRef.current.style.opacity = '1';
                    eqWrapRef.current.style.transform = 'translate(-50%, 0px)';
                    const phases = [0, 1.3, 2.5, 3.8];
                    for (let i = 0; i < 4; i++) {
                        const bar = eqBarRefs.current[i];
                        if (!bar) continue;
                        const wave = 0.35 + 0.65 * Math.abs(Math.sin(simTime * (8.5 + i * 1.4) + phases[i]));
                        const h = Math.round(4 + (0.25 + smoothAudio * 0.95) * wave * 11);
                        bar.style.height = `${Math.min(15, h)}px`;
                    }
                } else {
                    eqWrapRef.current.style.opacity = '0';
                    eqWrapRef.current.style.transform = 'translate(-50%, 4px)';
                }
            }

            // Update 3D animation mixer cleanly
            if (companion) {
                companion.playClip(desiredClip, 0.26);
                companion.mixer.timeScale = 1.0;
                companion.mixer.update(dt);

                if (isSpeaking && state.locomotion === 'perched' && headNode) {
                    const gentleNod = Math.sin(simTime * 8.2) * smoothAudio * 0.13;
                    headNode.rotation.x += gentleNod;
                }
            }

            speechGlowLight.intensity = isSpeaking
                ? 0.45 + smoothAudio * 1.1
                : isListening
                ? 0.25 + smoothAudio * 0.6
                : 0;

            state.facingAngle += (desiredFacingY - state.facingAngle) * Math.min(1, dt * 8.0);
            rootGroup.rotation.y = state.facingAngle;
            rootGroup.rotation.x += (targetPitchX - rootGroup.rotation.x) * Math.min(1, dt * 7.0);
            rootGroup.rotation.z += (targetRollZ - rootGroup.rotation.z) * Math.min(1, dt * 7.0);
            rootGroup.position.y += (speakBobY - rootGroup.position.y) * Math.min(1, dt * 10.0);

            renderer.render(scene, camera);
        };

        rafId = requestAnimationFrame(animate);

        return () => {
            disposed = true;
            clearTimeout(badgeTimeout);
            cancelAnimationFrame(rafId);
            window.removeEventListener('pointermove', onWindowPointerMove);
            wrapper.removeEventListener('pointerenter', onSpideyEnter);
            wrapper.removeEventListener('click', onSpideyClick);
            document.removeEventListener('visibilitychange', onVisibility);
            if (companion) {
                companion.dispose();
                companion = null;
            }
            renderer.dispose();
            if (renderer.domElement.parentNode === host) {
                host.removeChild(renderer.domElement);
            }
        };
    }, []); // Mount ONCE — never tear down WebGL on brainState changes!

    return (
        <>
            {/* Silk Web Thread Layer (web-shoot zip line + navbar hang silk) */}
            <svg
                ref={silkSvgRef}
                aria-hidden="true"
                className="pointer-events-none fixed inset-0 z-30 h-full w-full transition-opacity duration-150"
                style={{ opacity: 0 }}
            >
                {/* Active Web-Shoot / Zip Strand */}
                <line
                    ref={zipLineRef}
                    x1="0"
                    y1="0"
                    x2="0"
                    y2="0"
                    stroke="rgba(242, 239, 233, 0.72)"
                    strokeWidth="1.5"
                    strokeLinecap="round"
                    style={{ opacity: 0 }}
                />
                <circle
                    ref={zipAnchorDotRef}
                    cx="0"
                    cy="0"
                    r="3.2"
                    fill="#D95D24"
                    stroke="#F2EFE9"
                    strokeWidth="1"
                    style={{ opacity: 0 }}
                />

                {/* Navbar Hanging Silk Thread */}
                <line
                    ref={hangLineRef}
                    x1="0"
                    y1="0"
                    x2="0"
                    y2="0"
                    stroke="rgba(242, 239, 233, 0.45)"
                    strokeWidth="1.25"
                    strokeDasharray="3 2"
                    style={{ opacity: 0 }}
                />
                <circle
                    ref={hangAnchorDotRef}
                    cx="0"
                    cy="0"
                    r="2.6"
                    fill="#D95D24"
                    style={{ opacity: 0 }}
                />
            </svg>

            {/* Persistent Web-Swinging 3D Spidey Sprite */}
            <div
                ref={wrapperRef}
                className="fixed left-0 top-0 z-40 select-none cursor-pointer will-change-transform"
                style={{ width: SPRITE_SIZE, height: SPRITE_SIZE }}
                title="S.P.I.D.E.Y — click to say hi!"
                aria-label="S.P.I.D.E.Y 3D companion"
            >
                {/* Crisp Micro 4-Bar Voice Equalizer Pill (above head while speaking) */}
                <div
                    ref={eqWrapRef}
                    aria-hidden="true"
                    className="pointer-events-none absolute -top-2 left-1/2 flex h-5 items-center gap-[3px] rounded-full border border-[#D95D24]/45 bg-[#141312]/90 px-2 shadow-md transition-all duration-200"
                    style={{ opacity: 0, transform: 'translate(-50%, 4px)' }}
                >
                    {[0, 1, 2, 3].map((idx) => (
                        <span
                            key={idx}
                            ref={(el) => {
                                eqBarRefs.current[idx] = el;
                            }}
                            className="w-[2.5px] rounded-full bg-[#E07A48] transition-[height] duration-75"
                            style={{ height: '5px' }}
                        />
                    ))}
                </div>

                {/* Micro Interaction Speech Bubble */}
                <div
                    ref={badgeRef}
                    aria-live="polite"
                    className="pointer-events-none absolute -top-7 left-1/2 whitespace-nowrap rounded-full border border-[#D95D24]/45 bg-[#151312]/95 px-2.5 py-0.5 font-mono text-[10px] text-[#F2EFE9] shadow-lg transition-all duration-200"
                    style={{ opacity: 0, transform: 'translate(-50%, 4px)' }}
                />

                {/* 3D WebGL Canvas Host */}
                <div ref={canvasHostRef} className="h-full w-full" />
            </div>
        </>
    );
}
