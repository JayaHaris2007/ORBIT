import { useEffect, useRef, useState } from 'react';
import * as THREE from 'three';
import { useSpideyBrain } from '../../context/SpideyBrainContext';
import { getSharedAudioQueue } from '../../services/voiceService';

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

        float wave1 = sin(pos.x * 3.0 + uTime * (1.2 + uThinking * 2.4) + aPhase);
        float wave2 = cos(pos.y * 3.3 - uTime * (1.0 + uSpeaking * 2.0) + aPhase * 0.7);
        float wave3 = sin(pos.z * 2.8 + uTime * 0.95);
        float harmonic = (wave1 + wave2 + wave3) * 0.333;

        float breathe = sin(uTime * 1.4 + aLayer * 2.1) * 0.03;
        float listenRipple = uListening * (0.065 * sin(pos.y * 5.8 - uTime * 5.4) + uAudio * 0.24);
        float speakExpand = uSpeaking * (0.085 + uAudio * 0.32) * (0.55 + 0.45 * harmonic);
        float thinkFlux = uThinking * (0.06 * harmonic - 0.045);
        float pulseWave = uPulse * 0.15 * sin(length(pos) * 4.8 - uTime * 8.5);

        float displacement = breathe + harmonic * (0.036 + uThinking * 0.045) + listenRipple + speakExpand + thinkFlux + pulseWave;
        pos += dir * displacement * (0.52 + aLayer * 0.55);

        vec4 mvPosition = modelViewMatrix * vec4(pos, 1.0);
        gl_Position = projectionMatrix * mvPosition;

        float twinkle = 0.76 + 0.24 * sin(uTime * 2.7 + aPhase * 3.1);
        float energyBoost = 1.0 + uAudio * 0.75 + uThinking * 0.36 + uSpeaking * 0.35 + uListening * 0.28 + uPulse * 0.55;
        gl_PointSize = (uBaseSize * aSize * energyBoost * twinkle * uPixelRatio) * (3.0 / max(-mvPosition.z, 1.2));

        vec3 creamHighlight = vec3(0.949, 0.937, 0.914);
        float excite = clamp(uAudio * 0.48 + uThinking * 0.32 + uPulse * 0.42 + uListening * 0.22, 0.0, 0.78);
        vColor = mix(aColor, creamHighlight, excite * (0.3 + 0.7 * twinkle));
        vAlpha = clamp(0.58 + aLayer * 0.32 + uAudio * 0.24 + uPulse * 0.16, 0.30, 0.98);
    }
`;

const PARTICLE_FRAGMENT_SHADER = /* glsl */ `
    varying vec3 vColor;
    varying float vAlpha;

    void main() {
        vec2 uv = gl_PointCoord - vec2(0.5);
        float dist = length(uv);
        if (dist > 0.5) discard;

        float dotShape = smoothstep(0.5, 0.18, dist);
        gl_FragColor = vec4(vColor, dotShape * vAlpha);
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

        float wave = (sin(pos.x * 3.0 + uTime * (1.2 + uThinking * 2.4) + aPhase)
                    + cos(pos.y * 3.3 - uTime * (1.0 + uSpeaking * 2.0) + aPhase * 0.7)
                    + sin(pos.z * 2.8 + uTime * 0.95)) * 0.333;

        float breathe = sin(uTime * 1.4 + 2.0) * 0.03;
        float listenRipple = uListening * (0.065 * sin(pos.y * 5.8 - uTime * 5.4) + uAudio * 0.24);
        float speakExpand = uSpeaking * (0.085 + uAudio * 0.32) * (0.55 + 0.45 * wave);
        float thinkFlux = uThinking * (0.06 * wave - 0.045);
        float pulseWave = uPulse * 0.15 * sin(length(pos) * 4.8 - uTime * 8.5);

        pos += dir * (breathe + wave * (0.036 + uThinking * 0.045) + listenRipple + speakExpand + thinkFlux + pulseWave);

        gl_Position = projectionMatrix * modelViewMatrix * vec4(pos, 1.0);
        vColor = aColor;
        vSignal = 0.5 + 0.5 * sin(uTime * (2.5 + uThinking * 4.4 + uListening * 2.2) + pos.y * 4.4 + aPhase);
    }
`;

const FILAMENT_FRAGMENT_SHADER = /* glsl */ `
    uniform float uLineAlpha;
    uniform float uThinking;
    uniform float uAudio;
    uniform float uPulse;
    uniform float uListening;

    varying vec3 vColor;
    varying float vSignal;

    void main() {
        float boost = 1.0 + uThinking * 0.9 + uAudio * 1.1 + uPulse * 0.95 + uListening * 0.6;
        float alpha = uLineAlpha * (0.38 + 0.62 * vSignal) * boost;
        vec3 color = mix(vColor, vec3(0.98, 0.94, 0.88), vSignal * (0.28 + uThinking * 0.36 + uListening * 0.22));
        gl_FragColor = vec4(color, clamp(alpha, 0.04, 0.72));
    }
`;

function buildNeuralCoreData() {
    const count = 2100;
    const positions = new Float32Array(count * 3);
    const colors = new Float32Array(count * 3);
    const sizes = new Float32Array(count);
    const phases = new Float32Array(count);
    const layers = new Float32Array(count);

    const orange = new THREE.Color('#D95D24');
    const amber = new THREE.Color('#E07A48');
    const cream = new THREE.Color('#F2EFE9');
    const tmpColor = new THREE.Color();

    const goldenAngle = Math.PI * (3 - Math.sqrt(5));

    for (let i = 0; i < count; i++) {
        const t = (i + 0.5) / count;
        const y = 1 - 2 * t;
        const radiusAtY = Math.sqrt(Math.max(0, 1 - y * y));
        const theta = goldenAngle * i;

        const rRand = (i * 1.6180339) % 1;
        let radius = 1.08;
        let layerVal = 0.78;

        if (rRand < 0.14) {
            // Subtle inner synaptic nodes (no clumped center disc)
            radius = 0.52 + ((i * 0.37) % 1) * 0.34;
            layerVal = 0.4;
        } else if (rRand > 0.88) {
            // Outer wispy corona
            radius = 1.24 + ((i * 0.73) % 1) * 0.24;
            layerVal = 1.0;
        } else {
            // Main cortical neural shell
            radius = 1.04 + (((i * 0.53) % 1) - 0.5) * 0.12;
            layerVal = 0.76;
        }

        positions[i * 3] = Math.cos(theta) * radiusAtY * radius;
        positions[i * 3 + 1] = y * radius;
        positions[i * 3 + 2] = Math.sin(theta) * radiusAtY * radius;

        const colorRoll = (i * 0.754877) % 1;
        if (colorRoll > 0.80) {
            tmpColor.copy(cream);
            sizes[i] = 1.1 + (colorRoll - 0.80) * 2.1;
        } else if (colorRoll > 0.42) {
            tmpColor.copy(amber);
            sizes[i] = 0.86 + (colorRoll - 0.42) * 1.15;
        } else {
            tmpColor.copy(orange);
            sizes[i] = 0.76 + colorRoll * 1.2;
        }

        colors[i * 3] = tmpColor.r;
        colors[i * 3 + 1] = tmpColor.g;
        colors[i * 3 + 2] = tmpColor.b;

        phases[i] = (i % 97) * 0.19;
        layers[i] = layerVal;
    }

    // Synaptic cortical filaments + inner core synapses
    const hubCount = 172;
    const hubPoints = [];
    for (let i = 0; i < hubCount; i++) {
        const t = (i + 0.5) / hubCount;
        const y = 1 - 2 * t;
        const r = Math.sqrt(Math.max(0, 1 - y * y));
        const theta = goldenAngle * i * 1.05;
        const radius = i % 5 === 0 ? 0.52 : 1.06;
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
            if (d < 0.44) distances.push({ j, d });
        }
        distances.sort((a, b) => a.d - b.d);
        for (const { j } of distances.slice(0, 3)) {
            const key = i < j ? `${i}-${j}` : `${j}-${i}`;
            if (edgeSet.has(key)) continue;
            edgeSet.add(key);

            const a = hubPoints[i];
            const b = hubPoints[j];
            linePositions.push(a.x, a.y, a.z, b.x, b.y, b.z);

            const cA = i % 5 === 0 ? cream : orange;
            const cB = j % 5 === 0 ? cream : amber;
            lineColors.push(cA.r, cA.g, cA.b, cB.r, cB.g, cB.b);

            const p = (i % 41) * 0.25;
            linePhases.push(p, p);
        }
    }

    return {
        particles: { positions, colors, sizes, phases, layers },
        lines: {
            positions: new Float32Array(linePositions),
            colors: new Float32Array(lineColors),
            phases: new Float32Array(linePhases),
        },
    };
}

/**
 * Pure Neural Link 3D Orb: glowing burnt-orange/amber/cream particle cortex,
 * synaptic filaments, inner energy nucleus, and kinetic orbital ribbons.
 * Spidey 3D roams freely over the UI in SpideyRoamerOverlay.
 */
export default function SpideyNeuralCoreCanvas({
    variant = 'hero', // 'hero' | 'docked'
    interactive = true,
    className = '',
    onClick,
}) {
    const containerRef = useRef(null);
    const variantRef = useRef(variant);
    const brain = useSpideyBrain();
    const brainRef = useRef(brain);
    const [webglSupported] = useState(() => {
        if (typeof document === 'undefined') return true;
        try {
            const c = document.createElement('canvas');
            return Boolean(c.getContext('webgl2') || c.getContext('webgl'));
        } catch {
            return false;
        }
    });

    useEffect(() => {
        variantRef.current = variant;
    }, [variant]);

    useEffect(() => {
        brainRef.current = brain;
    }, [brain]);

    useEffect(() => {
        const container = containerRef.current;
        if (!container || !webglSupported) return undefined;

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

        const initW = Math.max(container.clientWidth, 64);
        const initH = Math.max(container.clientHeight, 64);
        renderer.setSize(initW, initH, false);
        renderer.domElement.style.width = '100%';
        renderer.domElement.style.height = '100%';
        renderer.domElement.style.display = 'block';
        container.appendChild(renderer.domElement);

        const scene = new THREE.Scene();
        const camera = new THREE.PerspectiveCamera(40, initW / initH, 0.1, 30);
        camera.position.set(0, 0, variantRef.current === 'docked' ? 3.55 : 4.0);
        camera.lookAt(0, 0, 0);

        const masterGroup = new THREE.Group();
        scene.add(masterGroup);

        // 1. Neural Link Particle & Synaptic Filament Sphere
        const neuralGroup = new THREE.Group();
        masterGroup.add(neuralGroup);

        const coreData = buildNeuralCoreData();
        const sharedUniforms = {
            uTime: { value: 0 },
            uPixelRatio: { value: pixelRatio },
            uBaseSize: { value: 2.55 },
            uAudio: { value: 0 },
            uThinking: { value: 0 },
            uSpeaking: { value: 0 },
            uListening: { value: 0 },
            uPulse: { value: 0 },
            uLineAlpha: { value: 0.2 },
        };

        const particleGeom = new THREE.BufferGeometry();
        particleGeom.setAttribute('position', new THREE.BufferAttribute(coreData.particles.positions, 3));
        particleGeom.setAttribute('aColor', new THREE.BufferAttribute(coreData.particles.colors, 3));
        particleGeom.setAttribute('aSize', new THREE.BufferAttribute(coreData.particles.sizes, 1));
        particleGeom.setAttribute('aPhase', new THREE.BufferAttribute(coreData.particles.phases, 1));
        particleGeom.setAttribute('aLayer', new THREE.BufferAttribute(coreData.particles.layers, 1));

        const particleMat = new THREE.ShaderMaterial({
            uniforms: sharedUniforms,
            vertexShader: PARTICLE_VERTEX_SHADER,
            fragmentShader: PARTICLE_FRAGMENT_SHADER,
            transparent: true,
            depthWrite: false,
            blending: THREE.AdditiveBlending,
        });
        neuralGroup.add(new THREE.Points(particleGeom, particleMat));

        const lineGeom = new THREE.BufferGeometry();
        lineGeom.setAttribute('position', new THREE.BufferAttribute(coreData.lines.positions, 3));
        lineGeom.setAttribute('aColor', new THREE.BufferAttribute(coreData.lines.colors, 3));
        lineGeom.setAttribute('aPhase', new THREE.BufferAttribute(coreData.lines.phases, 1));

        const lineMat = new THREE.ShaderMaterial({
            uniforms: sharedUniforms,
            vertexShader: FILAMENT_VERTEX_SHADER,
            fragmentShader: FILAMENT_FRAGMENT_SHADER,
            transparent: true,
            depthWrite: false,
            blending: THREE.AdditiveBlending,
        });
        neuralGroup.add(new THREE.LineSegments(lineGeom, lineMat));

        // 3. Four Kinetic Hedwig-Inspired Orbital Neural Link Ribbons
        const ribbonConfigs = [
            { radius: 1.18, tube: 0.013, color: '#D95D24', opacity: 0.62, rx: 0.68, ry: 0.2, rz: 0.45, speed: 0.48 },
            { radius: 1.32, tube: 0.009, color: '#E07A48', opacity: 0.46, rx: -0.58, ry: 0.88, rz: -0.35, speed: -0.38 },
            { radius: 0.86, tube: 0.010, color: '#E07A48', opacity: 0.48, rx: 1.25, ry: 0.5, rz: -0.7, speed: 0.55 },
            { radius: 1.46, tube: 0.006, color: '#F2EFE9', opacity: 0.24, rx: 1.12, ry: -0.42, rz: 0.9, speed: -0.26 },
        ];
        const ribbons = ribbonConfigs.map((cfg) => {
            const geom = new THREE.TorusGeometry(cfg.radius, cfg.tube, 10, 128);
            const mat = new THREE.MeshBasicMaterial({
                color: cfg.color,
                transparent: true,
                opacity: cfg.opacity,
                depthWrite: false,
                blending: THREE.AdditiveBlending,
            });
            const mesh = new THREE.Mesh(geom, mat);
            mesh.rotation.set(cfg.rx, cfg.ry, cfg.rz);
            masterGroup.add(mesh);
            return { mesh, geom, mat, cfg };
        });

        let targetRotX = 0;
        let targetRotY = 0;
        let localPulse = 0;

        const onPointerMove = (e) => {
            if (!interactive) return;
            const rect = container.getBoundingClientRect();
            const nx = ((e.clientX - rect.left) / Math.max(rect.width, 1) - 0.5) * 2;
            const ny = ((e.clientY - rect.top) / Math.max(rect.height, 1) - 0.5) * 2;
            targetRotY = nx * 0.46;
            targetRotX = ny * 0.26;
        };

        const onPointerLeave = () => {
            targetRotX = 0;
            targetRotY = 0;
        };

        const onPointerDown = () => {
            if (!interactive) return;
            localPulse = 1.25;
            brainRef.current?.triggerPulse?.(1.2);
        };

        container.addEventListener('pointermove', onPointerMove, { passive: true });
        container.addEventListener('pointerleave', onPointerLeave, { passive: true });
        container.addEventListener('pointerdown', onPointerDown, { passive: true });

        const resizeObserver = new ResizeObserver((entries) => {
            for (const entry of entries) {
                const { width, height } = entry.contentRect;
                if (width > 12 && height > 12) {
                    renderer.setSize(width, height, false);
                    camera.aspect = width / height;
                    camera.updateProjectionMatrix();
                    sharedUniforms.uBaseSize.value = width < 130 ? 1.85 : 2.65;
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
            { threshold: 0.02 }
        );
        intersectionObserver.observe(container);

        const onVisibility = () => {
            isTabVisible = !document.hidden;
        };
        document.addEventListener('visibilitychange', onVisibility);

        let rafId = 0;
        let lastTime = performance.now();
        let simTime = 0;
        let spinY = 0;
        let lastSeenPulseTime = 0;

        const animate = (now) => {
            rafId = requestAnimationFrame(animate);
            if (!isVisible || !isTabVisible) {
                lastTime = now;
                return;
            }

            const dt = Math.min((now - lastTime) / 1000, 0.05);
            lastTime = now;

            const currentBrain = brainRef.current;
            const currentState = currentBrain?.brainStateRef?.current || 'idle';
            const isListening = currentState === 'listening';
            const isThinking = currentState === 'thinking' || currentState === 'transcribing';
            const isStreaming = currentState === 'streaming';
            const isSpeaking = currentState === 'speaking';

            const micLevel = currentBrain?.audioLevelRef?.current || 0;
            const ttsLevel = getSharedAudioQueue()?.getOutputLevel?.() || 0;
            let reactiveAudio = Math.max(micLevel, ttsLevel);

            if ((isSpeaking || isStreaming) && reactiveAudio < 0.08) {
                reactiveAudio = 0.18 + 0.12 * Math.sin(simTime * 8.0);
            } else if (isListening && reactiveAudio < 0.06) {
                reactiveAudio = 0.1 + 0.05 * Math.sin(simTime * 4.5);
            }

            const ctxPulse = currentBrain?.pulseRef?.current;
            if (ctxPulse && ctxPulse.time > lastSeenPulseTime) {
                lastSeenPulseTime = ctxPulse.time;
                localPulse = Math.max(localPulse, ctxPulse.intensity * 0.75);
            }
            localPulse = Math.max(0, localPulse - dt * 2.3);

            const lerpRate = Math.min(1, dt * 6.5);
            sharedUniforms.uAudio.value += (reactiveAudio - sharedUniforms.uAudio.value) * lerpRate;
            sharedUniforms.uThinking.value += ((isThinking || isStreaming ? 1 : 0) - sharedUniforms.uThinking.value) * lerpRate;
            sharedUniforms.uSpeaking.value += ((isSpeaking || isStreaming ? 1 : 0) - sharedUniforms.uSpeaking.value) * lerpRate;
            sharedUniforms.uListening.value += ((isListening ? 1 : 0) - sharedUniforms.uListening.value) * lerpRate;
            sharedUniforms.uPulse.value = localPulse;

            const targetLineAlpha = isThinking ? 0.34 : isListening ? 0.3 : isSpeaking || isStreaming ? 0.28 : 0.19;
            sharedUniforms.uLineAlpha.value += (targetLineAlpha - sharedUniforms.uLineAlpha.value) * lerpRate;

            const targetZ = variantRef.current === 'docked' ? 3.55 : 4.0;
            camera.position.z += (targetZ - camera.position.z) * Math.min(1, dt * 5.0);

            if (!prefersReducedMotion) {
                const timeScale = isThinking ? 1.65 : isSpeaking || isStreaming ? 1.45 : isListening ? 1.3 : 0.85;
                simTime += dt * timeScale;
                sharedUniforms.uTime.value = simTime;

                const rotSpeed = isThinking ? 0.62 : isStreaming ? 0.48 : isListening ? 0.36 : isSpeaking ? 0.38 : 0.16;
                spinY += dt * rotSpeed;

                neuralGroup.rotation.y = spinY + targetRotY * 0.55;
                neuralGroup.rotation.x += (targetRotX * 0.6 - neuralGroup.rotation.x) * Math.min(1, dt * 4.2);

                const ribbonSpeedBoost = 1 + sharedUniforms.uThinking.value * 1.5 + sharedUniforms.uListening.value * 1.0 + sharedUniforms.uAudio.value * 1.8;
                for (let i = 0; i < ribbons.length; i++) {
                    const r = ribbons[i];
                    r.mesh.rotation.z += dt * r.cfg.speed * ribbonSpeedBoost;
                    r.mesh.rotation.x += dt * r.cfg.speed * 0.36 * (i % 2 === 0 ? 1 : -1) * ribbonSpeedBoost;
                    const breathScale = 1 + sharedUniforms.uAudio.value * 0.14 + localPulse * 0.06;
                    r.mesh.scale.setScalar(breathScale);
                    r.mat.opacity = Math.min(0.92, r.cfg.opacity + sharedUniforms.uAudio.value * 0.34 + sharedUniforms.uListening.value * 0.18);
                }
            }

            renderer.render(scene, camera);
        };

        rafId = requestAnimationFrame(animate);

        return () => {
            cancelAnimationFrame(rafId);
            resizeObserver.disconnect();
            intersectionObserver.disconnect();
            document.removeEventListener('visibilitychange', onVisibility);
            container.removeEventListener('pointermove', onPointerMove);
            container.removeEventListener('pointerleave', onPointerLeave);
            container.removeEventListener('pointerdown', onPointerDown);

            particleGeom.dispose();
            particleMat.dispose();
            lineGeom.dispose();
            lineMat.dispose();
            for (const r of ribbons) {
                r.geom.dispose();
                r.mat.dispose();
            }
            renderer.dispose();
            if (renderer.domElement.parentNode === container) {
                container.removeChild(renderer.domElement);
            }
        };
    }, [interactive, webglSupported]);

    const activeState = brain?.brainState || 'idle';

    if (!webglSupported) {
        return (
            <div
                onClick={onClick}
                className={`relative flex items-center justify-center rounded-full ${className}`}
                aria-label={`S.P.I.D.E.Y Neural Core (${activeState})`}
            >
                <div className="h-3/4 w-3/4 rounded-full bg-radial from-[#E07A48]/45 via-[#D95D24]/30 to-transparent blur-md animate-pulse" />
                <div className="absolute h-1/2 w-1/2 rounded-full border border-[#D95D24]/60" />
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
            aria-label={`S.P.I.D.E.Y Neural Link 3D Core (${activeState})`}
        />
    );
}
