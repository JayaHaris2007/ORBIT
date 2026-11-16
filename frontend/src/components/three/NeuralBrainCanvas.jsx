import { useEffect, useRef, useState } from 'react';
import * as THREE from 'three';
import { useSpideyBrain } from '../../context/SpideyBrainContext';
import { getSharedAudioQueue } from '../../services/voiceService';

const PRESETS = {
    compact: {
        particles: 1150,
        hubs: 135,
        neighbors: 2,
        ringParticles: 160,
        basePointSize: 2.8,
        cameraZ: 3.35,
    },
    hero: {
        particles: 2400,
        hubs: 210,
        neighbors: 3,
        ringParticles: 260,
        basePointSize: 3.1,
        cameraZ: 3.25,
    },
    overlay: {
        particles: 3000,
        hubs: 250,
        neighbors: 3,
        ringParticles: 320,
        basePointSize: 3.4,
        cameraZ: 3.2,
    },
};

const PARTICLE_VERTEX_SHADER = /* glsl */ `
    uniform float uTime;
    uniform float uPixelRatio;
    uniform float uBaseSize;
    uniform float uAudio;
    uniform float uThinking;
    uniform float uSpeaking;
    uniform float uListening;
    uniform float uPulse;

    attribute float aSize;
    attribute float aPhase;
    attribute float aLayer;
    attribute vec3 aColor;

    varying vec3 vColor;
    varying float vAlpha;

    void main() {
        vec3 pos = position;
        vec3 dir = normalize(pos + vec3(0.0001));

        // Organic harmonic surface waves
        float wave1 = sin(pos.x * 3.1 + uTime * (1.2 + uThinking * 2.2) + aPhase);
        float wave2 = cos(pos.y * 3.5 - uTime * (1.0 + uSpeaking * 1.8) + aPhase * 0.7);
        float wave3 = sin(pos.z * 2.9 + uTime * 0.9);
        float harmonic = (wave1 + wave2 + wave3) * 0.333;

        // Breathing + audio + thinking contraction + speaking/listening wave
        float breathe = sin(uTime * 1.4 + aLayer * 2.0) * 0.025;
        float listenRipple = uListening * (0.045 * sin(pos.y * 6.0 - uTime * 5.0) + uAudio * 0.16);
        float speakExpand = uSpeaking * (0.075 + uAudio * 0.24) * (0.6 + 0.4 * harmonic);
        float thinkFlux = uThinking * (0.055 * harmonic - 0.035);
        float pulseWave = uPulse * 0.12 * sin(length(pos) * 5.0 - uTime * 8.0);

        float displacement = breathe + harmonic * (0.03 + uThinking * 0.04) + listenRipple + speakExpand + thinkFlux + pulseWave;
        pos += dir * displacement * (0.55 + aLayer * 0.55);

        vec4 mvPosition = modelViewMatrix * vec4(pos, 1.0);
        gl_Position = projectionMatrix * mvPosition;

        float twinkle = 0.78 + 0.22 * sin(uTime * 2.6 + aPhase * 3.1);
        float energyBoost = 1.0 + uAudio * 0.65 + uThinking * 0.35 + uSpeaking * 0.3 + uPulse * 0.45;
        gl_PointSize = (uBaseSize * aSize * energyBoost * twinkle * uPixelRatio) * (2.6 / max(-mvPosition.z, 1.2));

        // Shift slightly toward warm cream when active without neon bloom
        vec3 creamHighlight = vec3(0.949, 0.937, 0.914);
        float excite = clamp(uAudio * 0.4 + uThinking * 0.28 + uPulse * 0.35, 0.0, 0.65);
        vColor = mix(aColor, creamHighlight, excite * (0.3 + 0.7 * twinkle));
        vAlpha = clamp(0.62 + aLayer * 0.3 + uAudio * 0.2 + uPulse * 0.15, 0.32, 0.98);
    }
`;

const PARTICLE_FRAGMENT_SHADER = /* glsl */ `
    varying vec3 vColor;
    varying float vAlpha;

    void main() {
        vec2 uv = gl_PointCoord - vec2(0.5);
        float dist = length(uv);
        if (dist > 0.5) discard;

        // Crisp architectural dot with restrained anti-aliased edge (no neon bloom)
        float dotShape = smoothstep(0.5, 0.22, dist);
        float alpha = dotShape * vAlpha;
        gl_FragColor = vec4(vColor, alpha);
    }
`;

const FILAMENT_VERTEX_SHADER = /* glsl */ `
    uniform float uTime;
    uniform float uAudio;
    uniform float uThinking;
    uniform float uSpeaking;
    uniform float uListening;
    uniform float uPulse;

    attribute vec3 aColor;
    attribute float aPhase;

    varying vec3 vColor;
    varying float vSignal;

    void main() {
        vec3 pos = position;
        vec3 dir = normalize(pos + vec3(0.0001));

        float wave = (sin(pos.x * 3.1 + uTime * (1.2 + uThinking * 2.2) + aPhase)
                    + cos(pos.y * 3.5 - uTime * (1.0 + uSpeaking * 1.8) + aPhase * 0.7)
                    + sin(pos.z * 2.9 + uTime * 0.9)) * 0.333;

        float breathe = sin(uTime * 1.4 + 2.0) * 0.025;
        float listenRipple = uListening * (0.045 * sin(pos.y * 6.0 - uTime * 5.0) + uAudio * 0.16);
        float speakExpand = uSpeaking * (0.075 + uAudio * 0.24) * (0.6 + 0.4 * wave);
        float thinkFlux = uThinking * (0.055 * wave - 0.035);
        float pulseWave = uPulse * 0.12 * sin(length(pos) * 5.0 - uTime * 8.0);

        pos += dir * (breathe + wave * (0.03 + uThinking * 0.04) + listenRipple + speakExpand + thinkFlux + pulseWave);

        gl_Position = projectionMatrix * modelViewMatrix * vec4(pos, 1.0);
        vColor = aColor;
        vSignal = 0.5 + 0.5 * sin(uTime * (2.2 + uThinking * 4.0) + pos.y * 4.5 + aPhase);
    }
`;

const FILAMENT_FRAGMENT_SHADER = /* glsl */ `
    uniform float uLineAlpha;
    uniform float uThinking;
    uniform float uAudio;
    uniform float uPulse;

    varying vec3 vColor;
    varying float vSignal;

    void main() {
        float boost = 1.0 + uThinking * 0.8 + uAudio * 0.9 + uPulse * 0.9;
        float alpha = uLineAlpha * (0.45 + 0.55 * vSignal) * boost;
        vec3 color = mix(vColor, vec3(1.0, 0.94, 0.88), vSignal * (0.25 + uThinking * 0.35));
        gl_FragColor = vec4(color, clamp(alpha, 0.04, 0.72));
    }
`;

function buildSphereGeometryData(preset) {
    const count = preset.particles;
    const positions = new Float32Array(count * 3);
    const colors = new Float32Array(count * 3);
    const sizes = new Float32Array(count);
    const phases = new Float32Array(count);
    const layers = new Float32Array(count);

    const orange = new THREE.Color('#D95D24');
    const amber = new THREE.Color('#E07A48');
    const white = new THREE.Color('#F2EFE9');
    const tmpColor = new THREE.Color();

    const goldenAngle = Math.PI * (3 - Math.sqrt(5));

    for (let i = 0; i < count; i++) {
        const t = (i + 0.5) / count;
        const y = 1 - 2 * t;
        const radiusAtY = Math.sqrt(Math.max(0, 1 - y * y));
        const theta = goldenAngle * i;

        const rRand = (i * 1.6180339) % 1;
        let radius = 1.0;
        let layerVal = 0.8;

        if (rRand < 0.18) {
            // Inner nucleus
            radius = 0.42 + ((i * 0.37) % 1) * 0.34;
            layerVal = 0.35;
        } else if (rRand > 0.90) {
            // Outer corona wisps
            radius = 1.07 + ((i * 0.73) % 1) * 0.16;
            layerVal = 1.0;
        } else {
            // Main cortical shell
            radius = 0.96 + (((i * 0.53) % 1) - 0.5) * 0.07;
            layerVal = 0.75;
        }

        const x = Math.cos(theta) * radiusAtY * radius;
        const z = Math.sin(theta) * radiusAtY * radius;
        const py = y * radius;

        positions[i * 3] = x;
        positions[i * 3 + 1] = py;
        positions[i * 3 + 2] = z;

        // Mix signature orange, warm amber, and crisp white highlights
        const colorRoll = (i * 0.754877) % 1;
        if (colorRoll > 0.76) {
            tmpColor.copy(white);
            sizes[i] = 1.15 + (colorRoll - 0.76) * 2.2;
        } else if (colorRoll > 0.42) {
            tmpColor.copy(amber);
            sizes[i] = 0.85 + (colorRoll - 0.42) * 1.1;
        } else {
            tmpColor.copy(orange);
            sizes[i] = 0.75 + colorRoll * 1.2;
        }

        colors[i * 3] = tmpColor.r;
        colors[i * 3 + 1] = tmpColor.g;
        colors[i * 3 + 2] = tmpColor.b;

        phases[i] = (i % 97) * 0.19;
        layers[i] = layerVal;
    }

    // Build interconnected cortical hubs + synaptic filaments
    const hubCount = preset.hubs;
    const hubPoints = [];
    for (let i = 0; i < hubCount; i++) {
        const t = (i + 0.5) / hubCount;
        const y = 1 - 2 * t;
        const r = Math.sqrt(Math.max(0, 1 - y * y));
        const theta = goldenAngle * i * 1.05;
        const radius = 0.98;
        hubPoints.push(new THREE.Vector3(Math.cos(theta) * r * radius, y * radius, Math.sin(theta) * r * radius));
    }

    const edgeSet = new Set();
    const linePositions = [];
    const lineColors = [];
    const linePhases = [];

    for (let i = 0; i < hubCount; i++) {
        const distances = [];
        for (let j = 0; j < hubCount; j++) {
            if (i === j) continue;
            const d = hubPoints[i].distanceToSquared(hubPoints[j]);
            if (d < 0.34) {
                distances.push({ j, d });
            }
        }
        distances.sort((a, b) => a.d - b.d);
        const picks = distances.slice(0, preset.neighbors);
        for (const { j } of picks) {
            const key = i < j ? `${i}-${j}` : `${j}-${i}`;
            if (edgeSet.has(key)) continue;
            edgeSet.add(key);

            const a = hubPoints[i];
            const b = hubPoints[j];
            linePositions.push(a.x, a.y, a.z, b.x, b.y, b.z);

            const cA = i % 4 === 0 ? white : orange;
            const cB = j % 4 === 0 ? white : amber;
            lineColors.push(cA.r, cA.g, cA.b, cB.r, cB.g, cB.b);

            const p = (i % 41) * 0.25;
            linePhases.push(p, p);
        }
    }

    // Dual orbital energy rings
    const ringCount = preset.ringParticles;
    const ringPositions = new Float32Array(ringCount * 3);
    const ringColors = new Float32Array(ringCount * 3);
    for (let i = 0; i < ringCount; i++) {
        const angle = (i / ringCount) * Math.PI * 2;
        const ringRadius = i % 2 === 0 ? 1.38 : 1.54;
        const tilt = i % 2 === 0 ? 0.38 : -0.52;
        const x = Math.cos(angle) * ringRadius;
        const z = Math.sin(angle) * ringRadius;
        const y = Math.sin(angle) * ringRadius * Math.sin(tilt);
        const zz = z * Math.cos(tilt);
        ringPositions[i * 3] = x;
        ringPositions[i * 3 + 1] = y;
        ringPositions[i * 3 + 2] = zz;

        const c = i % 5 === 0 ? white : orange;
        ringColors[i * 3] = c.r;
        ringColors[i * 3 + 1] = c.g;
        ringColors[i * 3 + 2] = c.b;
    }

    return {
        particles: { positions, colors, sizes, phases, layers },
        lines: {
            positions: new Float32Array(linePositions),
            colors: new Float32Array(lineColors),
            phases: new Float32Array(linePhases),
        },
        rings: { positions: ringPositions, colors: ringColors },
    };
}

export default function NeuralBrainCanvas({
    size = 'hero',
    stateOverride = null,
    interactive = true,
    className = '',
    onClick,
}) {
    const containerRef = useRef(null);
    const brain = useSpideyBrain();
    const stateOverrideRef = useRef(stateOverride);
    const [webglSupported] = useState(() => {
        if (typeof document === 'undefined') return true;
        try {
            const testCanvas = document.createElement('canvas');
            return Boolean(testCanvas.getContext('webgl2') || testCanvas.getContext('webgl'));
        } catch {
            return false;
        }
    });

    useEffect(() => {
        stateOverrideRef.current = stateOverride;
    }, [stateOverride]);

    const activeState = stateOverride || brain?.brainState || 'idle';

    useEffect(() => {
        const container = containerRef.current;
        if (!container || !webglSupported) return undefined;

        const preset = PRESETS[size] || PRESETS.hero;
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

        const pixelRatio = Math.min(window.devicePixelRatio || 1, 1.75);
        renderer.setPixelRatio(pixelRatio);
        renderer.setClearColor(0x000000, 0);

        const initialWidth = Math.max(container.clientWidth, 120);
        const initialHeight = Math.max(container.clientHeight, 120);
        renderer.setSize(initialWidth, initialHeight, false);
        renderer.domElement.style.width = '100%';
        renderer.domElement.style.height = '100%';
        renderer.domElement.style.display = 'block';
        container.appendChild(renderer.domElement);

        const scene = new THREE.Scene();
        const camera = new THREE.PerspectiveCamera(42, initialWidth / initialHeight, 0.1, 25);
        camera.position.z = preset.cameraZ;

        const brainGroup = new THREE.Group();
        scene.add(brainGroup);

        const data = buildSphereGeometryData(preset);

        // 1. Particle Sphere
        const particleGeom = new THREE.BufferGeometry();
        particleGeom.setAttribute('position', new THREE.BufferAttribute(data.particles.positions, 3));
        particleGeom.setAttribute('aColor', new THREE.BufferAttribute(data.particles.colors, 3));
        particleGeom.setAttribute('aSize', new THREE.BufferAttribute(data.particles.sizes, 1));
        particleGeom.setAttribute('aPhase', new THREE.BufferAttribute(data.particles.phases, 1));
        particleGeom.setAttribute('aLayer', new THREE.BufferAttribute(data.particles.layers, 1));

        const sharedUniforms = {
            uTime: { value: 0 },
            uPixelRatio: { value: pixelRatio },
            uBaseSize: { value: preset.basePointSize },
            uAudio: { value: 0 },
            uThinking: { value: 0 },
            uSpeaking: { value: 0 },
            uListening: { value: 0 },
            uPulse: { value: 0 },
            uLineAlpha: { value: 0.22 },
        };

        const particleMat = new THREE.ShaderMaterial({
            uniforms: sharedUniforms,
            vertexShader: PARTICLE_VERTEX_SHADER,
            fragmentShader: PARTICLE_FRAGMENT_SHADER,
            transparent: true,
            depthWrite: false,
            blending: THREE.NormalBlending,
        });
        const points = new THREE.Points(particleGeom, particleMat);
        brainGroup.add(points);

        // 2. Interconnected Neural Filaments
        const lineGeom = new THREE.BufferGeometry();
        lineGeom.setAttribute('position', new THREE.BufferAttribute(data.lines.positions, 3));
        lineGeom.setAttribute('aColor', new THREE.BufferAttribute(data.lines.colors, 3));
        lineGeom.setAttribute('aPhase', new THREE.BufferAttribute(data.lines.phases, 1));

        const lineMat = new THREE.ShaderMaterial({
            uniforms: sharedUniforms,
            vertexShader: FILAMENT_VERTEX_SHADER,
            fragmentShader: FILAMENT_FRAGMENT_SHADER,
            transparent: true,
            depthWrite: false,
            blending: THREE.NormalBlending,
        });
        const filaments = new THREE.LineSegments(lineGeom, lineMat);
        brainGroup.add(filaments);

        // 3. Orbital Micro-Particle Rings
        const ringGeom = new THREE.BufferGeometry();
        ringGeom.setAttribute('position', new THREE.BufferAttribute(data.rings.positions, 3));
        ringGeom.setAttribute('color', new THREE.BufferAttribute(data.rings.colors, 3));
        const ringMat = new THREE.PointsMaterial({
            size: 0.02,
            vertexColors: true,
            transparent: true,
            opacity: 0.36,
            depthWrite: false,
            blending: THREE.NormalBlending,
        });
        const rings = new THREE.Points(ringGeom, ringMat);
        brainGroup.add(rings);

        // Pointer interactivity
        let targetRotX = 0;
        let targetRotY = 0;
        let pointerRotY = 0;
        let localPulse = 0;

        const handlePointerMove = (e) => {
            if (!interactive) return;
            const rect = container.getBoundingClientRect();
            const nx = ((e.clientX - rect.left) / Math.max(rect.width, 1) - 0.5) * 2;
            const ny = ((e.clientY - rect.top) / Math.max(rect.height, 1) - 0.5) * 2;
            targetRotY = nx * 0.42;
            targetRotX = ny * 0.32;
        };

        const handlePointerLeave = () => {
            targetRotX = 0;
            targetRotY = 0;
        };

        const handlePointerDown = () => {
            if (!interactive) return;
            localPulse = 1.15;
            brain?.triggerPulse?.(1.1);
        };

        container.addEventListener('pointermove', handlePointerMove, { passive: true });
        container.addEventListener('pointerleave', handlePointerLeave, { passive: true });
        container.addEventListener('pointerdown', handlePointerDown, { passive: true });

        // ResizeObserver keeps viewport crisp without tearing down WebGL
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

        // Visibility / intersection pause to conserve laptop battery & GPU
        let isVisible = true;
        let isTabVisible = !document.hidden;
        let rafId = 0;
        let lastTime = performance.now();
        let simTime = 0;
        let spinY = 0;
        let ringSpin = 0;
        let lastSeenPulseTime = 0;

        const intersectionObserver = new IntersectionObserver(
            (entries) => {
                isVisible = entries[0]?.isIntersecting ?? true;
            },
            { threshold: 0.05 }
        );
        intersectionObserver.observe(container);

        const handleVisibility = () => {
            isTabVisible = !document.hidden;
            if (isTabVisible) lastTime = performance.now();
        };
        document.addEventListener('visibilitychange', handleVisibility);

        const animate = (now) => {
            rafId = requestAnimationFrame(animate);
            if (!isVisible || !isTabVisible) {
                lastTime = now;
                return;
            }

            const dt = Math.min((now - lastTime) / 1000, 0.05);
            lastTime = now;

            const currentState = stateOverrideRef.current || brain?.brainStateRef?.current || 'idle';
            const isListening = currentState === 'listening';
            const isThinking = currentState === 'thinking' || currentState === 'transcribing';
            const isStreaming = currentState === 'streaming';
            const isSpeaking = currentState === 'speaking';

            // Read live mic level or TTS playback output level
            const micLevel = brain?.audioLevelRef?.current || 0;
            const ttsLevel = getSharedAudioQueue()?.getOutputLevel?.() || 0;
            let reactiveAudio = Math.max(micLevel, ttsLevel);

            // Provide subtle organic cadence during active voice states even between syllables
            if ((isSpeaking || isStreaming) && reactiveAudio < 0.08) {
                reactiveAudio = 0.16 + 0.1 * Math.sin(simTime * 7.5);
            } else if (isListening && reactiveAudio < 0.05) {
                reactiveAudio = 0.08 + 0.04 * Math.sin(simTime * 4.2);
            }

            // Pick up external token/event pulses
            const ctxPulse = brain?.pulseRef?.current;
            if (ctxPulse && ctxPulse.time > lastSeenPulseTime) {
                lastSeenPulseTime = ctxPulse.time;
                localPulse = Math.max(localPulse, ctxPulse.intensity * 0.7);
            }
            localPulse = Math.max(0, localPulse - dt * 2.4);

            // Smooth uniform transitions
            const lerpRate = Math.min(1, dt * 6.5);
            sharedUniforms.uAudio.value += (reactiveAudio - sharedUniforms.uAudio.value) * lerpRate;
            sharedUniforms.uThinking.value += ((isThinking || isStreaming ? 1 : 0) - sharedUniforms.uThinking.value) * lerpRate;
            sharedUniforms.uSpeaking.value += ((isSpeaking || isStreaming ? 1 : 0) - sharedUniforms.uSpeaking.value) * lerpRate;
            sharedUniforms.uListening.value += ((isListening ? 1 : 0) - sharedUniforms.uListening.value) * lerpRate;
            sharedUniforms.uPulse.value = localPulse;

            const targetAlpha = isThinking ? 0.34 : isSpeaking || isStreaming ? 0.3 : isListening ? 0.28 : 0.2;
            sharedUniforms.uLineAlpha.value += (targetAlpha - sharedUniforms.uLineAlpha.value) * lerpRate;

            if (!prefersReducedMotion) {
                const timeScale = isThinking ? 1.55 : isSpeaking || isStreaming ? 1.35 : isListening ? 1.2 : 0.85;
                simTime += dt * timeScale;
                sharedUniforms.uTime.value = simTime;

                const rotSpeed = isThinking ? 0.58 : isStreaming ? 0.45 : isSpeaking ? 0.34 : isListening ? 0.28 : 0.14;
                spinY += dt * rotSpeed;
                ringSpin -= dt * (rotSpeed * 1.45);
            }

            pointerRotY += (targetRotY - pointerRotY) * Math.min(1, dt * 4.5);
            brainGroup.rotation.y = spinY + pointerRotY;
            brainGroup.rotation.x += (targetRotX - brainGroup.rotation.x) * Math.min(1, dt * 4.5);
            rings.rotation.y = ringSpin;
            rings.rotation.z = Math.sin(simTime * 0.25) * 0.14;
            ringMat.opacity = 0.32 + sharedUniforms.uAudio.value * 0.4 + sharedUniforms.uThinking.value * 0.18;

            renderer.render(scene, camera);
        };

        rafId = requestAnimationFrame(animate);

        return () => {
            cancelAnimationFrame(rafId);
            resizeObserver.disconnect();
            intersectionObserver.disconnect();
            document.removeEventListener('visibilitychange', handleVisibility);
            container.removeEventListener('pointermove', handlePointerMove);
            container.removeEventListener('pointerleave', handlePointerLeave);
            container.removeEventListener('pointerdown', handlePointerDown);

            particleGeom.dispose();
            particleMat.dispose();
            lineGeom.dispose();
            lineMat.dispose();
            ringGeom.dispose();
            ringMat.dispose();
            renderer.dispose();
            if (renderer.domElement.parentNode === container) {
                container.removeChild(renderer.domElement);
            }
        };
    }, [size, interactive, brain, webglSupported]);

    if (!webglSupported) {
        return (
            <div
                onClick={onClick}
                className={`relative flex items-center justify-center rounded-full ${className}`}
                aria-label={`S.P.I.D.E.Y. Neural Core (${activeState})`}
            >
                <div className="h-3/4 w-3/4 rounded-full bg-radial from-white/40 via-orange-500/40 to-transparent blur-md animate-pulse" />
                <div className="absolute h-1/2 w-1/2 rounded-full border border-orange-400/60 shadow-[0_0_32px_rgba(255,106,26,0.45)]" />
            </div>
        );
    }

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
            aria-label={`S.P.I.D.E.Y. 3D Neural Core (${activeState})`}
        />
    );
}
